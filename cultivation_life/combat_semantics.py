"""Version-three, data-only combat semantics. No content, RNG or game objects.

Versions one/two keep their existing evaluator in combat_rule_engine. This
version uses typed facts, explicit phases and preview/commit transactions so
that an unaffordable/cancelled action cannot spend a mark or a charge.
"""
from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass, field


SCHEMA_VERSION = 3
MAX_RULES = 128
MAX_STATES = 512
MAX_STACKS = 99
MAX_DURATION = 10000
STATS = ('might', 'guard', 'mobility', 'sense', 'sustain', 'breach')
PHASES = (
    'round_start', 'field_prepare', 'field_established', 'contest_prepare',
    'contest_resolved', 'pressure_resolved', 'effect_prepare', 'effect_before_apply', 'effect_resolved',
    'intervention_resolved', 'ordinary_start',
    'initiative_resolved', 'ordinary_before_damage', 'ordinary_after_damage', 'round_end',
)
TARGET_PHASES = {'contest_prepare', 'contest_resolved', 'effect_before_apply',
                 'effect_resolved', 'pressure_resolved', 'intervention_resolved',
                 'ordinary_before_damage', 'ordinary_after_damage'}
RESTRICTIONS = ('artifact', 'technique', 'supply', 'support', 'communication', 'voisinage', 'ordinary')
EFFECTS = ('strike', 'suppress', 'seal', 'restrict', 'isolate', 'restore_body', 'restore_spirit', 'restore_field')

# Public catalogs are also used by validation and documentation; unsupported
# facts never silently evaluate to zero/False (especially inside NOT).
ACTOR_FACTS = {
    'id': str, 'side': str, 'rank': float, 'power': float, 'state': float,
    'body': float, 'morale': float, 'energy': float, 'capacity': float,
    'energy_ratio': float, 'mp_ratio': float, 'pressure': float, 'strain': float,
    'seal_progress': float, 'sustained_rounds': float, 'active_field': bool,
    'field_id': str, 'stance': str, 'fighting': bool, 'suppressed': bool,
    'escaped': bool, 'escape_locked': bool, 'dominated': bool,
    'has_field': bool, 'field_sealed': bool, 'force_tier': float,
    'ward_tier': float, 'resource_tier': float, 'technique_tier': float,
    'artifact_tier': float, 'ally_count': float, 'enemy_count': float,
    **{f'restricted_{key}': bool for key in RESTRICTIONS},
    **{f'ordinary_{key}': float for key in ('dealt', 'received')},
    **{f'field_{key}': float for key in ('dealt', 'received')},
    **{f'pressure_{key}': float for key in ('dealt', 'received')},
}
FACTS = {'round': (float, set(PHASES)), 'role': (str, set(PHASES))}
for _prefix in ('self', 'target', 'previous.self', 'previous.target'):
    FACTS.update({f'{_prefix}.{k}': (v, TARGET_PHASES if _prefix.endswith('target') else set(PHASES)) for k, v in ACTOR_FACTS.items()})
FACTS.update({
    'rank_delta': (float, TARGET_PHASES),
    'event.first': (bool, {'initiative_resolved', 'ordinary_before_damage', 'ordinary_after_damage', 'round_end'}),
    'event.relation': (str, {'contest_resolved'}),
    'event.incursion': (float, {'contest_resolved'}),
    'event.stability': (float, {'contest_resolved'}),
    'event.continued': (bool, {'field_prepare', 'field_established'}),
    'event.cost': (float, {'field_established', 'effect_resolved'}),
    'event.effect': (str, {'effect_prepare', 'effect_before_apply', 'effect_resolved'}),
    'event.restriction': (str, {'effect_prepare', 'effect_before_apply', 'effect_resolved'}),
    'event.damage_source': (str, {'ordinary_before_damage', 'ordinary_after_damage', 'effect_resolved', 'pressure_resolved'}),
    'event.amount': (float, {'ordinary_before_damage', 'ordinary_after_damage', 'effect_resolved', 'pressure_resolved'}),
    'event.actual_loss': (float, {'ordinary_after_damage', 'effect_resolved', 'pressure_resolved'}),
    'event.body_loss': (float, {'ordinary_after_damage', 'effect_resolved', 'pressure_resolved'}),
    'event.restored': (float, {'effect_resolved'}),
    'event.terminal': (bool, {'effect_before_apply', 'effect_resolved'}),
    'event.intervention': (str, {'intervention_resolved'}),
    'environment.terrain': (str, set(PHASES)),
    'environment.forbidden_flight': (bool, set(PHASES)),
    'environment.forbidden_sense': (bool, set(PHASES)),
    'environment.formation': (bool, set(PHASES)),
})
CHANNELS = {
    **{f'ordinary.{s}': {'ordinary_start', 'initiative_resolved'} if s in ('might', 'guard', 'breach')
       else {'ordinary_start'} for s in STATS},
    'ordinary.dealt': {'ordinary_before_damage'},
    'ordinary.received': {'ordinary_before_damage'},
    'ordinary.received_cap': {'ordinary_before_damage'},
    'field.opening_cost': {'field_prepare'}, 'field.upkeep_cost': {'field_prepare'},
    'field.extra_target_cost': {'field_prepare'},
    'field.incursion': {'contest_prepare'}, 'field.stability': {'contest_prepare'},
    'field.effect_cost': {'effect_prepare'}, 'field.authority': {'effect_before_apply'},
    'field.received': {'effect_before_apply'}, 'field.received_cap': {'effect_before_apply'},
    **{f'field.{kind}': {'effect_before_apply'} for kind in EFFECTS if kind not in ('restrict', 'isolate')},
}
ADJUSTMENTS = {'state', 'body', 'morale', 'pressure', 'strain', 'seal_progress'}


def _number(value, low=-math.inf, high=math.inf):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _keys(obj, allowed, required=()):
    if not isinstance(obj, dict) or set(obj) - set(allowed) or set(required) - set(obj):
        raise ValueError('Unknown or missing semantic fields')


def _identifier(value):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError('Semantic identifiers must be nonempty strings of at most 128 characters')


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid semantic integer')


def _condition(expr, phase, depth=0, budget=None):
    budget = [0] if budget is None else budget
    budget[0] += 1
    if depth > 8 or budget[0] > 64:
        raise ValueError('Condition expression is too large')
    if type(expr) is bool:
        return
    if not isinstance(expr, dict):
        raise ValueError('Condition must be a boolean or a finite expression')
    if set(expr) in ({'all'}, {'any'}):
        children = next(iter(expr.values()))
        if not isinstance(children, list) or not 1 <= len(children) <= 16:
            raise ValueError('Boolean groups require 1..16 conditions')
        for child in children:
            _condition(child, phase, depth + 1, budget)
        return
    if set(expr) == {'not'}:
        _condition(expr['not'], phase, depth + 1, budget)
        return
    if 'counter' in expr or 'status' in expr:
        _keys(expr, ('counter', 'status', 'op', 'value'), ('op', 'value'))
        if ('counter' in expr) == ('status' in expr):
            raise ValueError('Choose counter or status')
        _identifier(expr.get('counter', expr.get('status')))
        expected = float
    else:
        _keys(expr, ('fact', 'op', 'value'), ('fact', 'op'))
        if expr['fact'] not in FACTS or phase not in FACTS[expr['fact']][1]:
            raise ValueError(f"Unavailable fact {expr['fact']} at {phase}")
        expected = FACTS[expr['fact']][0]
    op = expr['op']
    if op == 'exists' and 'fact' in expr and 'value' not in expr:
        return
    if op not in ('eq', 'ne', 'lt', 'le', 'gt', 'ge', 'in', 'not_in') or 'value' not in expr:
        raise ValueError('Unknown comparison')
    if expected != float and op in ('lt', 'le', 'gt', 'ge'):
        raise ValueError('Ordered comparisons require numeric facts')
    values = expr['value'] if op in ('in', 'not_in') else [expr['value']]
    if not isinstance(values, list) or not 1 <= len(values) <= 32:
        raise ValueError('Membership needs a bounded list')
    for value in values:
        if not (_number(value) if expected == float else type(value) is expected):
            raise ValueError('Comparison value has the wrong type')


def _modifier(row, phase=None):
    _keys(row, ('channel', 'value'), ('channel', 'value'))
    channel = row['channel']
    if channel not in CHANNELS or (phase is not None and phase not in CHANNELS[channel]):
        raise ValueError('Modifier cannot affect this phase')
    if not _number(row['value'], 0 if channel.endswith('_cap') else -.75, 1):
        raise ValueError('Modifier value is outside the finite budget')


def _parse_rule(raw):
    """Validate completely, returning a detached JSON-safe rule snapshot."""
    _keys(raw, ('schema_version', 'id', 'source_id', 'trigger', 'when', 'scope',
                'schedule', 'limits', 'actions', 'name', 'reset_on_target_change'),
          ('schema_version', 'id', 'source_id', 'trigger', 'actions'))
    if type(raw['schema_version']) is not int or raw['schema_version'] != SCHEMA_VERSION:
        raise ValueError('Expected combat semantics version three')
    for key in ('id', 'source_id'):
        _identifier(raw[key])
    if 'name' in raw:
        _identifier(raw['name'])
    phase = raw['trigger']
    if phase not in PHASES or raw.get('scope', 'self') not in ('self', 'target'):
        raise ValueError('Unknown trigger or scope')
    if raw.get('scope') == 'target' and phase not in TARGET_PHASES:
        raise ValueError('Target-scoped rules require a directional event')
    if type(raw.get('reset_on_target_change', False)) is not bool or (raw.get('reset_on_target_change') and raw.get('scope') != 'target'):
        raise ValueError('Target-change reset requires target scope')
    _condition(raw.get('when', True), phase)
    schedule = raw.get('schedule', {})
    _keys(schedule, ('start', 'end', 'every'))
    for value in schedule.values():
        _integer(value, 1, 1000000000)
    if schedule.get('end', 1000000000) < schedule.get('start', 1):
        raise ValueError('Reversed round window')
    limits = raw.get('limits', {})
    _keys(limits, ('per_round', 'per_battle', 'cooldown'))
    for key, value in limits.items():
        _integer(value, 0 if key == 'cooldown' else 1, 10000)
    actions = raw['actions']
    if not isinstance(actions, list) or not 1 <= len(actions) <= 16:
        raise ValueError('Rules require 1..16 actions')
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError('Action must be an object')
        kind = action.get('op')
        if kind == 'modify':
            _keys(action, ('op', 'channel', 'value'), ('channel', 'value'))
            _modifier({k: v for k, v in action.items() if k != 'op'}, phase)
        elif kind in ('counter_add', 'counter_set', 'counter_consume'):
            _keys(action, ('op', 'key', 'value', 'max'), ('key', 'value'))
            _identifier(action['key'])
            _integer(action['value'], 0, MAX_STACKS)
            _integer(action.get('max', MAX_STACKS), 1, MAX_STACKS)
        elif kind in ('clear_status', 'consume_status'):
            _keys(action, ('op', 'key', 'stacks'), ('key',))
            _identifier(action['key'])
            _integer(action.get('stacks', 1), 1, MAX_STACKS)
        elif kind == 'status':
            _keys(action, ('op', 'key', 'duration', 'delay', 'stacks', 'max_stacks',
                          'modifiers', 'consume_on', 'recipient', 'bind_target', 'stacking'),
                  ('key', 'duration'))
            _identifier(action['key'])
            _integer(action['duration'], 1, MAX_DURATION)
            _integer(action.get('delay', 0), 0, MAX_DURATION)
            _integer(action.get('stacks', 1), 1, MAX_STACKS)
            _integer(action.get('max_stacks', 1), 1, MAX_STACKS)
            if action.get('recipient', 'self') not in ('self', 'target'):
                raise ValueError('Unknown status recipient')
            if (action.get('recipient') == 'target' or action.get('bind_target')) and phase not in TARGET_PHASES:
                raise ValueError('Targeted status requires a directional event')
            if type(action.get('bind_target', False)) is not bool:
                raise ValueError('Target binding must be boolean')
            if action.get('stacking', 'refresh') not in ('refresh', 'extend', 'keep'):
                raise ValueError('Unknown duration stacking policy')
            modifiers = action.get('modifiers', [])
            if not isinstance(modifiers, list) or len(modifiers) > 16:
                raise ValueError('Too many status modifiers')
            for modifier in modifiers:
                _modifier(modifier)
            if 'consume_on' in action:
                consume = action['consume_on']
                if consume not in PHASES or not any(consume in CHANNELS[m['channel']] for m in modifiers):
                    raise ValueError('A consuming status must contribute to its consuming phase')
        elif kind == 'adjust':
            _keys(action, ('op', 'stat', 'value', 'recipient'), ('stat', 'value'))
            if phase not in ('round_start', 'round_end') or action['stat'] not in ADJUSTMENTS:
                raise ValueError('Direct adjustments require a round boundary and an existing resource')
            if not _number(action['value'], -24 if action['stat'] == 'morale' else -.25,
                           24 if action['stat'] == 'morale' else .25):
                raise ValueError('Adjustment exceeds finite budget')
            if action.get('recipient', 'self') != 'self':
                raise ValueError('Boundary adjustments apply to their owner')
        else:
            raise ValueError('Unknown semantic action')
    return json.loads(json.dumps(raw, allow_nan=False))


def parse_rule(raw):
    try:
        return _parse_rule(raw)
    except (TypeError, KeyError, OverflowError, RecursionError) as exc:
        raise ValueError('Malformed combat semantic rule') from exc


def parse_rules(rows):
    if not isinstance(rows, (list, tuple)) or len(rows) > MAX_RULES:
        raise ValueError('Too many semantic rules')
    rules = tuple(parse_rule(row) for row in rows)
    ids = [(r['source_id'], r['id']) for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate semantic rule within source')
    return rules


def semantic_catalog():
    """Machine-readable vocabulary for editors/providers; no gameplay entries."""
    return {
        'schema_version': SCHEMA_VERSION, 'triggers': list(PHASES),
        'facts': {key: {'type': 'number' if kind is float else kind.__name__,
                        'phases': sorted(phases)} for key, (kind, phases) in FACTS.items()},
        'modifiers': {key: {'phases': sorted(phases), 'mode': 'cap' if key.endswith('_cap') else 'relative',
                            'min': 0 if key.endswith('_cap') else -.75, 'max': 1}
                      for key, phases in CHANNELS.items()},
        'comparisons': ['eq', 'ne', 'lt', 'le', 'gt', 'ge', 'in', 'not_in', 'exists'],
        'logic': ['all', 'any', 'not'],
        'actions': ['modify', 'counter_add', 'counter_set', 'counter_consume',
                    'status', 'clear_status', 'consume_status', 'adjust'],
        'adjustments': sorted(ADJUSTMENTS),
        'scopes': ['self', 'target'], 'stacking': ['refresh', 'extend', 'keep'],
    }


_MISSING = object()


@dataclass
class Evaluation:
    actor: str
    target: str | None
    trigger: str
    token: int
    round: int
    rules: list = field(default_factory=list)
    modifiers: list = field(default_factory=list)
    statuses: list = field(default_factory=list)
    resets: list = field(default_factory=list)

    def factor(self, channel):
        return max(.25, min(2., 1 + sum(m['value'] for m in self.modifiers if m['channel'] == channel)))

    def cap(self, channel, default=1.):
        return min([default, *(m['value'] for m in self.modifiers if m['channel'] == channel)])


class SemanticRuntime:
    """Per-actor/source/target state, bounded and serializable for resumed fights."""

    def __init__(self, rules):
        if not isinstance(rules, dict) or len(rules) > MAX_STATES:
            raise ValueError('Unbounded semantic actor set')
        self.rules = {str(actor): parse_rules(rows) for actor, rows in rules.items()}
        self.round = 0
        self.serial = 0
        self.counters = {}
        self.statuses = {}
        self.usage = {}
        self.previous = {}
        self.bindings = {}
        self.committed = set()
        self.log = []

    @staticmethod
    def key(*parts):
        return json.dumps(parts, ensure_ascii=False, separators=(',', ':'))

    def begin_round(self, number):
        _integer(number, 1, 1000000000)
        if number <= self.round:
            raise ValueError('Semantic round numbers must increase')
        self.round = number
        self.committed.clear()
        self.log = []
        self.statuses = {k: v for k, v in self.statuses.items() if v['expires'] >= number}

    def _namespace(self, actor, target, rule):
        return self.key(actor, rule['source_id'], target if rule.get('scope') == 'target' else None)

    def _can_spend(self, rule, namespace, fresh=False, balances=None):
        counters, marks = ({}, {}) if balances is None else (dict(balances[0]), dict(balances[1]))
        for action in rule['actions']:
            op, name = action['op'], action.get('key')
            key = self.key(namespace, name)
            if op.startswith('counter_'):
                value = counters.get(key, 0 if fresh else self.counters.get(key, 0))
                if op == 'counter_consume' and value < action['value']:
                    return False
                counters[key] = max(0, min(action.get('max', MAX_STACKS), action['value'] if op == 'counter_set'
                                           else value + (-action['value'] if op == 'counter_consume' else action['value'])))
            elif op in ('status', 'consume_status', 'clear_status'):
                value = marks.get(key, 0 if fresh else sum(s['stacks'] for s in self.statuses.values()
                    if s['namespace'] == namespace and s['key'] == name and s['starts'] <= self.round <= s['expires']))
                if op == 'consume_status' and value < action.get('stacks', 1):
                    return False
                marks[key] = (min(action.get('max_stacks', 1), value + action.get('stacks', 1)) if op == 'status'
                               else max(0, value - action.get('stacks', 1)) if op == 'consume_status' else 0)
        if balances is not None:
            balances[0].update(counters)
            balances[1].update(marks)
        return True

    def _matches(self, expr, facts, namespace, fresh=False):
        if type(expr) is bool:
            return expr
        if 'all' in expr or 'any' in expr:
            values = [self._matches(e, facts, namespace, fresh) for e in expr.get('all', expr.get('any'))]
            if 'all' in expr:
                return False if False in values else None if None in values else True
            return True if True in values else None if None in values else False
        if 'not' in expr:
            value = self._matches(expr['not'], facts, namespace, fresh)
            return None if value is None else not value
        if 'counter' in expr:
            value = 0 if fresh else self.counters.get(self.key(namespace, expr['counter']), 0)
        elif 'status' in expr:
            value = 0 if fresh else sum(s['stacks'] for s in self.statuses.values()
                        if s['namespace'] == namespace and s['key'] == expr['status']
                        and s['starts'] <= self.round <= s['expires'])
        else:
            value = facts.get(expr['fact'], _MISSING)
        op = expr['op']
        if op == 'exists':
            return value is not _MISSING
        if value is _MISSING:
            return None
        other = expr['value']
        if op == 'eq': return value == other
        if op == 'ne': return value != other
        if op == 'lt': return value < other
        if op == 'le': return value <= other
        if op == 'gt': return value > other
        if op == 'ge': return value >= other
        if op == 'in': return value in other
        return value not in other

    def preview(self, actor, target, trigger, facts):
        if trigger not in PHASES:
            raise ValueError('Unknown semantic event')
        self.serial += 1
        result = Evaluation(actor, target, trigger, self.serial, self.round)
        reservations = ({}, {})
        if target is not None:
            result.resets = list(dict.fromkeys(rule['source_id'] for rule in self.rules.get(actor, ())
                if rule['trigger'] == trigger and rule.get('reset_on_target_change')
                and self.bindings.get(self.key(actor, rule['source_id'])) != target))
        facts = dict(facts, round=self.round)
        for prefix, who in (('self', actor), ('target', target)):
            facts.update({f'previous.{prefix}.{k}': v for k, v in self.previous.get(who, {}).items()})
        for key, status in self.statuses.items():
            if status['origin'] == actor and json.loads(status['namespace'])[1] in result.resets:
                continue
            if (status['owner'] != actor or not status['starts'] <= self.round <= status['expires']
                    or (status['bound_target'] is not None and status['bound_target'] != target)):
                continue
            mods = [dict(m, value=m['value'] if m['channel'].endswith('_cap') else m['value'] * status['stacks'])
                    for m in status['modifiers'] if trigger in CHANNELS[m['channel']]]
            result.modifiers.extend(mods)
            if mods and status['consume_on'] == trigger:
                result.statuses.append((key, {m['channel'] for m in mods}))
                mark_key = self.key(status['namespace'], status['key'])
                reservations[1].setdefault(mark_key, sum(s['stacks'] for s in self.statuses.values()
                    if s['namespace'] == status['namespace'] and s['key'] == status['key']
                    and s['starts'] <= self.round <= s['expires']))
                reservations[1][mark_key] -= 1
        for rule in self.rules.get(actor, ()):
            if rule['trigger'] != trigger or (rule.get('scope') == 'target' and target is None):
                continue
            if (rule.get('reset_on_target_change') and self.bindings.get(self.key(actor, rule['source_id'])) != target
                    and rule['source_id'] not in result.resets):
                result.resets.append(rule['source_id'])
            schedule = rule.get('schedule', {})
            start = schedule.get('start', 1)
            if self.round < start or self.round > schedule.get('end', 1000000000) or (self.round - start) % schedule.get('every', 1):
                continue
            namespace = self._namespace(actor, target, rule)
            # Trigger limits are actor/source/rule scoped, never per victim.
            usage_key = self.key(actor, rule['source_id'], rule['id'])
            used = self.usage.get(usage_key, {})
            limits = rule.get('limits', {})
            if used.get('total', 0) >= limits.get('per_battle', 1000000000):
                continue
            if used.get('round') == self.round and used.get('count', 0) >= limits.get('per_round', 1):
                continue
            if used and self.round <= used['round'] + limits.get('cooldown', 0) and used['round'] != self.round:
                continue
            fresh = rule.get('reset_on_target_change') and self.bindings.get(self.key(actor, rule['source_id'])) != target
            if self._matches(rule.get('when', True), facts, namespace, fresh) is not True:
                continue
            if not self._can_spend(rule, namespace, fresh, reservations):
                continue
            result.rules.append((rule, namespace, usage_key))
            result.modifiers.extend({k: v for k, v in a.items() if k != 'op'}
                                    for a in rule['actions'] if a['op'] == 'modify')
        return result

    def commit(self, evaluation, *, channels=()):
        """Call only after an action has legal targets and has actually executed."""
        if evaluation.token in self.committed:
            return []
        if evaluation.round != self.round:
            raise ValueError('Cannot commit a preview from another round')
        self.committed.add(evaluation.token)
        adjustments = []
        for source_id in evaluation.resets:
            binding = self.key(evaluation.actor, source_id)
            for key in list(self.counters):
                ns, _ = json.loads(key)
                owner, source, _ = json.loads(ns)
                if (owner, source) == (evaluation.actor, source_id):
                    del self.counters[key]
            self.statuses = {k: s for k, s in self.statuses.items()
                             if json.loads(s['namespace'])[:2] != [evaluation.actor, source_id]}
            self.bindings[binding] = evaluation.target
        for key, used_channels in evaluation.statuses:
            if used_channels.intersection(channels) and key in self.statuses:
                self.statuses[key]['stacks'] -= 1
                if self.statuses[key]['stacks'] <= 0:
                    del self.statuses[key]
        for rule, namespace, usage_key in evaluation.rules:
            modified = {a['channel'] for a in rule['actions'] if a['op'] == 'modify'}
            if modified and not modified.intersection(channels):
                continue
            limits = rule.get('limits', {})
            prior = self.usage.get(usage_key, {})
            if (prior.get('total', 0) >= limits.get('per_battle', 1000000000)
                    or (prior.get('round') == self.round and prior.get('count', 0) >= limits.get('per_round', 1))
                    or (prior and prior['round'] != self.round and self.round <= prior['round'] + limits.get('cooldown', 0))):
                continue
            if not self._can_spend(rule, namespace):
                continue
            used = self.usage.setdefault(usage_key, {'round': self.round, 'count': 0, 'total': 0})
            used['count'] = (used['count'] if used['round'] == self.round else 0) + 1
            used['round'], used['total'] = self.round, used['total'] + 1
            for action in rule['actions']:
                op = action['op']
                key = self.key(namespace, action.get('key'))
                if op.startswith('counter_'):
                    if key not in self.counters and len(self.counters) >= MAX_STATES:
                        continue
                    current, value = self.counters.get(key, 0), action['value']
                    self.counters[key] = max(0, min(action.get('max', MAX_STACKS),
                        value if op == 'counter_set' else current - value if op == 'counter_consume' else current + value))
                elif op == 'status':
                    owner = evaluation.actor if action.get('recipient', 'self') == 'self' else evaluation.target
                    if owner is None:
                        continue
                    key = self.key(namespace, action['key'], owner)
                    if key not in self.statuses and len(self.statuses) >= MAX_STATES:
                        continue
                    old = self.statuses.get(key, {})
                    starts = self.round + action.get('delay', 0)
                    expires = starts + action['duration'] - 1
                    stacking = action.get('stacking', 'refresh')
                    if old and stacking == 'keep':
                        starts, expires = old['starts'], old['expires']
                    elif old and stacking == 'extend':
                        starts, expires = old['starts'], min(self.round + MAX_DURATION, old['expires'] + action['duration'])
                    self.statuses[key] = dict(namespace=namespace, key=action['key'], owner=owner,
                        origin=evaluation.actor, bound_target=(evaluation.target if owner == evaluation.actor else evaluation.actor)
                        if action.get('bind_target', False) else None,
                        starts=starts, expires=expires,
                        stacks=min(action.get('max_stacks', 1), old.get('stacks', 0) + action.get('stacks', 1)),
                        modifiers=copy.deepcopy(action.get('modifiers', [])), consume_on=action.get('consume_on'))
                elif op in ('clear_status', 'consume_status'):
                    remaining = action.get('stacks', 1)
                    for status_key, status in sorted(list(self.statuses.items())):
                        if status['namespace'] == namespace and status['key'] == action['key']:
                            if op == 'clear_status':
                                del self.statuses[status_key]
                            elif remaining and status['starts'] <= self.round <= status['expires']:
                                spent = min(remaining, status['stacks'])
                                remaining -= spent
                                status['stacks'] -= spent
                                if not status['stacks']:
                                    del self.statuses[status_key]
                elif op == 'adjust':
                    recipient = evaluation.actor if action.get('recipient', 'self') == 'self' else evaluation.target
                    if recipient is not None:
                        adjustments.append((recipient, action['stat'], action['value']))
            self.log.append(dict(round=self.round, actor=evaluation.actor, target=evaluation.target,
                                 source=rule['source_id'], rule=rule['id'], trigger=evaluation.trigger, token=evaluation.token))
            self.log = self.log[-128:]
        return adjustments

    def finish_round(self, snapshots):
        self.previous = copy.deepcopy(snapshots)
        self.statuses = {k: v for k, v in self.statuses.items() if v['expires'] > self.round}

    def dump(self):
        return copy.deepcopy(dict(version=SCHEMA_VERSION, round=self.round, serial=self.serial,
            counters=self.counters, statuses=self.statuses, usage=self.usage, previous=self.previous, bindings=self.bindings))

    def restore(self, snapshot):
        _keys(snapshot, ('version', 'round', 'serial', 'counters', 'statuses', 'usage', 'previous', 'bindings'),
              ('version', 'round', 'serial', 'counters', 'statuses', 'usage', 'previous'))
        if snapshot['version'] != SCHEMA_VERSION:
            raise ValueError('Unknown semantic runtime version')
        _integer(snapshot['round'], 0, 1000000000)
        _integer(snapshot['serial'], 0, 1000000000000)
        for key in ('counters', 'statuses', 'usage', 'previous', 'bindings'):
            if key == 'bindings' and key not in snapshot:
                continue
            if not isinstance(snapshot[key], dict) or len(snapshot[key]) > (MAX_RULES * max(1, len(self.rules)) if key in ('usage', 'bindings') else MAX_STATES):
                raise ValueError('Unbounded semantic snapshot')
        # Round-trip through strict JSON rejects NaN and arbitrary Python objects.
        def reject(value):
            raise ValueError(f'Non-finite runtime value: {value}')
        clean = json.loads(json.dumps(snapshot, allow_nan=False), parse_constant=reject)
        clean.setdefault('bindings', {})
        sources = {(actor, row['source_id']) for actor, rows in self.rules.items() for row in rows}
        ids = {(actor, row['source_id'], row['id']) for actor, rows in self.rules.items() for row in rows}

        def parts(key, size):
            try:
                value = json.loads(key)
            except (ValueError, TypeError) as exc:
                raise ValueError('Malformed runtime namespace') from exc
            if not isinstance(value, list) or len(value) != size:
                raise ValueError('Malformed runtime namespace')
            return value

        def namespace(key):
            actor, source, target = parts(key, 3)
            if not isinstance(actor, str) or not isinstance(source, str) or (actor, source) not in sources:
                raise ValueError('Runtime refers to an unknown source')
            if target is not None:
                _identifier(target)

        for key, value in clean['counters'].items():
            ns, name = parts(key, 2)
            namespace(ns)
            _identifier(name)
            _integer(value, 0, MAX_STACKS)
        for key, value in clean['bindings'].items():
            actor, source = parts(key, 2)
            if not isinstance(actor, str) or not isinstance(source, str) or (actor, source) not in sources:
                raise ValueError('Unknown binding source')
            _identifier(value)
        for key, value in clean['usage'].items():
            identity = parts(key, 3)
            if any(not isinstance(v, str) for v in identity) or tuple(identity) not in ids:
                raise ValueError('Unknown runtime rule')
            _keys(value, ('round', 'count', 'total'), ('round', 'count', 'total'))
            _integer(value['round'], 1, clean['round'])
            _integer(value['count'], 1, 10000)
            _integer(value['total'], value['count'], 1000000000000)
        for key, s in clean['statuses'].items():
            _keys(s, ('namespace', 'key', 'owner', 'origin', 'bound_target', 'starts', 'expires',
                      'stacks', 'modifiers', 'consume_on'),
                     ('namespace', 'key', 'owner', 'origin', 'bound_target', 'starts', 'expires',
                      'stacks', 'modifiers', 'consume_on'))
            namespace(s['namespace'])
            for name in ('key', 'owner', 'origin'):
                _identifier(s[name])
            if s['origin'] != parts(s['namespace'], 3)[0] or key != self.key(s['namespace'], s['key'], s['owner']):
                raise ValueError('Inconsistent status identity')
            if s['bound_target'] is not None:
                _identifier(s['bound_target'])
            _integer(s['starts'], 1, clean['round'] + MAX_DURATION)
            _integer(s['expires'], s['starts'], clean['round'] + 2 * MAX_DURATION)
            _integer(s['stacks'], 1, MAX_STACKS)
            if not isinstance(s['modifiers'], list) or len(s['modifiers']) > 16:
                raise ValueError('Unbounded status modifiers')
            for m in s['modifiers']:
                _modifier(m)
            if s['consume_on'] is not None and (s['consume_on'] not in PHASES
                    or not any(s['consume_on'] in CHANNELS[m['channel']] for m in s['modifiers'])):
                raise ValueError('Invalid consuming status')
        for actor, facts in clean['previous'].items():
            _identifier(actor)
            if not isinstance(facts, dict) or set(facts) - set(ACTOR_FACTS):
                raise ValueError('Unknown previous facts')
            for key, value in facts.items():
                expected = ACTOR_FACTS[key]
                if not (_number(value) if expected == float else type(value) is expected):
                    raise ValueError('Previous fact has the wrong type')
        for key in ('round', 'serial', 'counters', 'statuses', 'usage', 'previous', 'bindings'):
            setattr(self, key, clean[key])
        self.committed.clear()
        self.log = []

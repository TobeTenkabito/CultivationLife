"""Synthetic semantic fixtures, not gameplay content or authored buff designs."""
import copy
import json
import random
from dataclasses import replace

import pytest

from cultivation_life.combat_semantics import (
    SemanticRuntime, parse_rule, parse_rules, CHANNELS, FACTS, PHASES, semantic_catalog,
)
from cultivation_life.system.combat.contracts import (
    CombatCapabilities, CapabilitySource, resolve_source, VoisinageEffect, Intervention,
)
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.trials import dump_battle, load_battle
from test_voisinage_effects import domain, caster, actor, begin
from test_domain_combat import fight


def rule(phase, *actions, **kw):
    return dict(schema_version=3, id=kw.pop('id', phase), source_id='test-source',
                trigger=phase, actions=list(actions), **kw)


def modifier(channel, value):
    return dict(op='modify', channel=channel, value=value)


def status(key='s', **kw):
    return dict(op='status', key=key, duration=kw.pop('duration', 2), **kw)


def count(key='n', **kw):
    return dict(op='counter_add', key=key, value=1, **kw)


def runtime(*rows, actors=('p',)):
    rt = SemanticRuntime({actor: rows for actor in actors})
    rt.begin_round(1)
    return rt


def execute(rt, phase, target=None, actor='p', facts=None, channels=()):
    ev = rt.preview(actor, target, phase, facts or {})
    rt.commit(ev, channels=channels)
    return ev


@pytest.mark.parametrize('channel,phases', CHANNELS.items())
def test_every_advertised_modifier_parses_only_at_its_real_phase(channel, phases):
    for phase in phases:
        parse_rule(rule(phase, modifier(channel, .2)))
    illegal = next(p for p in PHASES if p not in phases)
    with pytest.raises(ValueError):
        parse_rule(rule(illegal, modifier(channel, .2)))


@pytest.mark.parametrize('bad', [
    rule('round_start', count(), when={'fact': 'event.actual_loss', 'op': 'gt', 'value': 0}),
    rule('round_start', count(), when={'fact': 'made_up', 'op': 'eq', 'value': 0}),
    rule('round_start', count(), when={'fact': 'self.state', 'op': 'eq', 'value': True}),
    rule('round_start', count(), when={'fact': 'self.fighting', 'op': 'lt', 'value': True}),
    rule('round_start', modifier('field.incursion', .2)),
    rule('round_start', status(duration=0)),
    rule('round_start', status(consume_on='field_prepare')),
    rule('round_start', {'op': 'python', 'code': 'raise SystemExit'}),
    rule('round_start', modifier('ordinary.might', float('nan'))),
    rule('round_start', count(), scope='target'),
    rule('round_start', status(recipient='target')),
    rule('round_start', count(), limits={'per_round': 0}),
    rule('round_start', count(), schedule={'start': 3, 'end': 2}),
    rule('round_start', count(), unknown=True),
])
def test_bad_or_acausal_content_is_rejected(bad):
    with pytest.raises(ValueError):
        parse_rule(bad)


def test_no_python_no_unknown_fields_no_unbounded_boolean_tree():
    expr = True
    for _ in range(10):
        expr = {'not': expr}
    with pytest.raises(ValueError):
        parse_rule(rule('round_start', count(), when=expr))
    with pytest.raises(ValueError):
        parse_rules([rule('round_start', count())] * 2)
    original = rule('round_start', count())
    parsed = parse_rule(original)
    original['actions'][0]['value'] = 80
    assert parsed['actions'][0]['value'] == 1


def test_missing_previous_facts_are_unknown_even_inside_negation():
    row = rule('round_start', count(), when={'not': {'fact': 'previous.self.state', 'op': 'gt', 'value': .5}})
    rt = runtime(row)
    assert not execute(rt, 'round_start').rules
    rt.finish_round({'p': {'state': .4}})
    rt.begin_round(2)
    assert execute(rt, 'round_start').rules


def test_boolean_membership_and_round_schedule():
    row = rule('round_start', count(), schedule={'start': 2, 'end': 6, 'every': 2}, when={'all': [
        {'fact': 'self.state', 'op': 'le', 'value': .5},
        {'any': [{'fact': 'self.stance', 'op': 'in', 'value': ['guard', 'press']}, False]},
    ]})
    rt = runtime(row)
    hits = []
    for n in range(1, 8):
        if n > 1:
            rt.begin_round(n)
        if execute(rt, 'round_start', facts={'self.state': .4, 'self.stance': 'guard'}).rules:
            hits.append(n)
    assert hits == [2, 4, 6]


def test_actor_source_target_isolation_and_nonrecursive_conditions():
    setup = rule('ordinary_after_damage', count(), scope='target', limits={'per_round': 8})
    payoff = rule('ordinary_after_damage', count('paid'), id='payoff', scope='target',
                 when={'counter': 'n', 'op': 'ge', 'value': 1})
    rt = runtime(setup, payoff, actors=('p', 'ally', 'enemy'))
    first = execute(rt, 'ordinary_after_damage', 'x')
    assert len(first.rules) == 1  # no same-event recursive trigger
    assert len(execute(rt, 'ordinary_after_damage', 'y').rules) == 1
    assert len(execute(rt, 'ordinary_after_damage', 'x', actor='ally').rules) == 1
    assert len(execute(rt, 'ordinary_after_damage', 'x').rules) == 2
    assert len(rt.counters) == 4


def test_preview_never_consumes_and_unused_channel_never_spends_status():
    rt = runtime(rule('round_start', status(modifiers=[{'channel': 'field.effect_cost', 'value': -.5}],
                                          consume_on='effect_prepare')))
    execute(rt, 'round_start')
    ev = rt.preview('p', None, 'effect_prepare', {})
    assert ev.factor('field.effect_cost') == .5
    assert next(iter(rt.statuses.values()))['stacks'] == 1
    rt.commit(ev)  # no actual effect channel was used
    assert rt.statuses
    execute(rt, 'effect_prepare', channels={'field.effect_cost'})
    assert not rt.statuses


def test_duration_delay_cooldown_and_per_battle_limit_are_exact():
    rt = runtime(rule('round_start', status(delay=1, duration=1), limits={'cooldown': 1, 'per_battle': 2}))
    execute(rt, 'round_start')
    assert next(iter(rt.statuses.values()))['starts'] == 2
    rt.finish_round({})
    rt.begin_round(2)
    assert not execute(rt, 'round_start').rules
    assert rt.statuses
    rt.finish_round({})
    assert not rt.statuses
    rt.begin_round(3)
    assert execute(rt, 'round_start').rules
    rt.begin_round(5)
    assert not execute(rt, 'round_start').rules


def test_target_bound_status_does_not_leak_to_another_opponent():
    rt = runtime(rule('ordinary_after_damage', status(bind_target=True,
        modifiers=[{'channel': 'field.incursion', 'value': .4}]), scope='target'))
    execute(rt, 'ordinary_after_damage', 'x')
    assert rt.preview('p', 'x', 'contest_prepare', {}).factor('field.incursion') == 1.4
    assert rt.preview('p', 'y', 'contest_prepare', {}).factor('field.incursion') == 1


def test_cancelled_or_unaffordable_field_preserves_consumable():
    rows = (rule('round_start', status(modifiers=[{'channel': 'field.upkeep_cost', 'value': -.5}],
                                      consume_on='field_prepare')) ,)
    b = VoisinageBattle([actor('player', 'player', caster(domain(), current=.1, semantic_rules=rows)), actor('e', 'enemy')])
    begin(b)
    assert not b.fields and b.semantics.statuses
    assert b.units['player'].current == .1


def test_field_discount_is_applied_before_affordability_and_only_after_paid():
    rows = (rule('round_start', status(modifiers=[{'channel': 'field.upkeep_cost', 'value': -.5}],
                                      consume_on='field_prepare')) ,)
    b = VoisinageBattle([actor('player', 'player', caster(domain(), current=1.5, semantic_rules=rows)), actor('e', 'enemy')])
    begin(b)
    assert b.fields and not b.semantics.statuses
    assert b.units['player'].current == 0


def test_contest_modifier_changes_real_dominance_not_ordinary_power():
    buff = rule('contest_prepare', modifier('field.incursion', .5), when={'fact': 'role', 'op': 'eq', 'value': 'attacker'})
    d = domain(stability=100, incursion=100)
    b = VoisinageBattle([actor('player', 'player', caster(d, semantic_rules=(buff,))), actor('e', 'enemy', caster(d))])
    frame = begin(b)
    assert frame.relations['e']['relation'] == 'dominated'
    assert frame.relations['e']['attack_strength'] == 120  # coverage dilution still applies
    assert frame.relations['player']['relation'] == 'contested'


def test_effect_discount_and_power_change_actual_resource_and_damage():
    rows = (rule('effect_prepare', modifier('field.effect_cost', -.5)),
            rule('effect_before_apply', modifier('field.strike', .5)))
    d = domain(VoisinageEffect('strike', 4, .2))
    b = VoisinageBattle([actor('player', 'player', caster(d, current=4, semantic_rules=rows)), actor('e', 'enemy')])
    begin(b)
    assert b.units['player'].current == 0
    assert b.units['e'].vitality == pytest.approx(.7)


def test_intervention_cancellation_does_not_consume_cast_or_hit_status():
    rows = (rule('round_start', status(modifiers=[{'channel': 'field.effect_cost', 'value': -.5}], consume_on='effect_prepare')),
            rule('round_start', status('hit', modifiers=[{'channel': 'field.strike', 'value': .5}], consume_on='effect_before_apply'), id='hit'))
    d = domain(VoisinageEffect('strike', 4, .2))
    response = Intervention('resist', ('strike',), strength=1)
    b = VoisinageBattle([actor('player', 'player', caster(d, semantic_rules=rows)),
                        actor('e', 'enemy', CombatCapabilities(interventions=(response,)))])
    begin(b)
    assert b.units['e'].vitality == 1 and len(b.semantics.statuses) == 2
    assert b.units['player'].current == 98


def test_damage_is_actual_and_distinguishes_field_pressure_and_ordinary():
    rows = (rule('ordinary_after_damage', count('ordinary'), when={'all': [
        {'fact': 'role', 'op': 'eq', 'value': 'defender'},
        {'fact': 'event.actual_loss', 'op': 'gt', 'value': 0},
    ]}), rule('effect_resolved', count('field'), when={'fact': 'event.damage_source', 'op': 'eq', 'value': 'field'}))
    b = VoisinageBattle([actor('player', 'player', CombatCapabilities(ward_tier=2, semantic_rules=rows)), actor('e', 'enemy')])
    begin(b)
    b.ordinary_damage(.1, .1)
    assert not b.semantics.counters  # blocked by real ward, not a received hit
    b.finish_round(player_mp=1, enemy_mp=1)
    assert b.semantics.previous['player']['ordinary_received'] == 0


def test_ordinary_modifier_reaches_player_driver_and_boundaries_restore_real_state():
    base = CombatCapabilities(force_tier=2, current=20, capacity=20, resource_tier=2)
    rows = (rule('ordinary_start', modifier('ordinary.might', .5)),
            rule('ordinary_before_damage', modifier('ordinary.dealt', .5), when={'fact': 'role', 'op': 'eq', 'value': 'attacker'}),
            rule('round_end', dict(op='adjust', stat='state', value=.1)))
    baseline, _ = fight(base, base, rounds=1)
    modified, b = fight(replace(base, semantic_rules=rows), base, rounds=1)
    assert modified.enemy_hp_ratio < baseline.enemy_hp_ratio
    assert modified.player_combat_state > baseline.player_combat_state
    assert modified.rounds[0]['player_hp_ratio'] == round(b.units['player'].vitality, 4)


def test_per_round_damage_cap_is_shared_across_multiple_attackers():
    rows = (rule('ordinary_before_damage', modifier('ordinary.received_cap', .08),
                 limits={'per_round': 16}, when={'fact': 'role', 'op': 'eq', 'value': 'defender'}),)
    b = VoisinageBattle([actor('player', 'player', CombatCapabilities(semantic_rules=rows)),
                        actor('a', 'enemy'), actor('b', 'enemy')])
    begin(b)
    dealt, received = b.ordinary_damage(0, .4)
    assert received == pytest.approx(.08)
    assert b._semantic_totals['player', 'ordinary', 'received'] == pytest.approx(.08)
    assert b._semantic_totals['a', 'ordinary', 'dealt'] == pytest.approx(.04)


def test_pure_field_round_expires_status_and_roundtrip_matches_uninterrupted():
    rows = (rule('round_start', count(), limits={'per_battle': 1}),
            rule('contest_resolved', status(modifiers=[{'channel': 'field.incursion', 'value': .1}],
                 delay=1, duration=1), when={'fact': 'role', 'op': 'eq', 'value': 'attacker'}, limits={'per_battle': 1}))
    d = domain(VoisinageEffect('seal', 1, .01), incursion=300)
    b = VoisinageBattle([actor('player', 'player', caster(d, semantic_rules=rows)), actor('e', 'enemy')])
    begin(b)
    b.finish_round(player_mp=1, enemy_mp=1)
    loaded = load_battle(json.loads(json.dumps(dump_battle(b))))
    for candidate in (b, loaded):
        begin(candidate, 2)
        candidate.finish_round(player_mp=1, enemy_mp=1)
    assert json.loads(json.dumps(dump_battle(b))) == json.loads(json.dumps(dump_battle(loaded)))
    assert b.report() == loaded.report()
    assert not b.semantics.statuses
    assert list(b.semantics.counters.values()) == [1]


def test_source_injection_and_old_snapshots_remain_compatible():
    rows = (rule('round_start', count()),)
    caps = resolve_source(None, {}, CapabilitySource(semantic_rules=rows))
    assert caps.semantic_rules == rows
    b = VoisinageBattle([actor('player', 'player'), actor('e', 'enemy')])
    assert load_battle(dump_battle(b)).semantics is None


def test_no_resurrection_via_boundary_adjustment():
    rows = (rule('round_end', dict(op='adjust', stat='state', value=.25)),)
    b = VoisinageBattle([actor('player', 'player', CombatCapabilities(semantic_rules=rows)), actor('e', 'enemy')])
    begin(b)
    b.units['player'].vitality = 0
    b.finish_round(player_mp=1, enemy_mp=1)
    assert b.units['player'].vitality == 0


def test_catalog_is_json_safe_and_every_fact_has_a_typed_comparison():
    assert json.loads(json.dumps(semantic_catalog())) == semantic_catalog()
    for fact, (kind, phases) in FACTS.items():
        for phase in phases:
            value = .5 if kind is float else True if kind is bool else 'test'
            parse_rule(rule(phase, count(), when={'fact': fact, 'op': 'eq', 'value': value}))


@pytest.mark.parametrize('change', [
    lambda s: s['counters'].update({'bad-json': 1}),
    lambda s: s['statuses'].update({'s': {'stacks': 100000}}),
    lambda s: s['previous'].update({'p': {'state': float('nan')}}),
    lambda s: s['previous'].update({'p': {'unknown': 1}}),
    lambda s: s['usage'].update({'["p","test-source","round_start"]': {'round': 2, 'count': 1, 'total': 1}}),
    lambda s: s.update(version=99),
    lambda s: s.update(round=-1),
    lambda s: s.update(unrecognized=True),
])
def test_invalid_runtime_snapshot_is_rejected_without_mutation(change):
    rt = runtime(rule('round_start', count()))
    execute(rt, 'round_start')
    old = rt.dump()
    bad = copy.deepcopy(old)
    change(bad)
    with pytest.raises(ValueError):
        rt.restore(bad)
    assert rt.dump() == old


def test_atomic_consumption_requires_enough_counters():
    row = rule('ordinary_before_damage', modifier('ordinary.dealt', .5),
               dict(op='counter_consume', key='charge', value=3))
    rt = runtime(row)
    assert not execute(rt, 'ordinary_before_damage', 'e', channels={'ordinary.dealt'}).rules


def test_two_rules_cannot_both_spend_the_same_last_charge():
    charge = rule('round_start', count())
    one = rule('ordinary_before_damage', modifier('ordinary.dealt', .2),
               dict(op='counter_consume', key='n', value=1), id='one')
    two = dict(one, id='two')
    rt = runtime(charge, one, two)
    execute(rt, 'round_start')
    result = execute(rt, 'ordinary_before_damage', 'e', channels={'ordinary.dealt'})
    assert result.factor('ordinary.dealt') == 1.2
    assert list(rt.counters.values()) == [0]


def test_earlier_round_report_is_not_changed_by_later_status_consumption():
    rows = (rule('round_start', status(stacks=2, max_stacks=2,
        modifiers=[{'channel': 'ordinary.dealt', 'value': .1}], consume_on='ordinary_before_damage')) ,)
    b = VoisinageBattle([actor('player', 'player', CombatCapabilities(semantic_rules=rows)), actor('e', 'enemy')])
    begin(b)
    report = b.report()
    b.ordinary_damage(.1, .1)
    assert report['semantics']['statuses'][0]['stacks'] == 2
    assert b.report()['semantics']['statuses'][0]['stacks'] == 1


def test_target_change_clears_old_progress_even_when_payoff_condition_fails():
    rows = (rule('ordinary_after_damage', count(), scope='target', reset_on_target_change=True,
                 limits={'per_round': 8}),)
    rt = runtime(*rows)
    execute(rt, 'ordinary_after_damage', 'a')
    execute(rt, 'ordinary_after_damage', 'a')
    assert list(rt.counters.values()) == [2]
    execute(rt, 'ordinary_after_damage', 'b')
    execute(rt, 'ordinary_after_damage', 'a')
    assert list(rt.counters.values()) == [1]


def test_target_switch_clears_old_status_before_previewing_the_new_attack():
    row = rule('ordinary_before_damage', status(modifiers=[{'channel': 'ordinary.dealt', 'value': .5}]),
               scope='target', reset_on_target_change=True, limits={'per_round': 8})
    rt = runtime(row)
    execute(rt, 'ordinary_before_damage', 'a')
    assert rt.preview('p', 'a', 'ordinary_before_damage', {}).factor('ordinary.dealt') == 1.5
    assert rt.preview('p', 'b', 'ordinary_before_damage', {}).factor('ordinary.dealt') == 1


def test_targeted_debuff_attaches_to_actual_recipient_not_the_whole_side():
    row = rule('ordinary_after_damage', status(recipient='target',
        modifiers=[{'channel': 'ordinary.might', 'value': -.3}]), scope='target')
    rt = runtime(row)
    execute(rt, 'ordinary_after_damage', 'enemy-a')
    assert rt.preview('p', None, 'ordinary_start', {}).factor('ordinary.might') == 1
    assert rt.preview('enemy-a', None, 'ordinary_start', {}).factor('ordinary.might') == .7
    assert rt.preview('enemy-b', None, 'ordinary_start', {}).factor('ordinary.might') == 1


def test_stale_preview_cannot_be_committed_and_success_is_idempotent():
    rt = runtime(rule('round_start', count()))
    ev = rt.preview('p', None, 'round_start', {})
    rt.commit(ev)
    rt.commit(ev)
    assert list(rt.counters.values()) == [1]
    stale = rt.preview('p', None, 'round_start', {})
    rt.begin_round(2)
    with pytest.raises(ValueError):
        rt.commit(stale)


def test_all_three_status_stacking_policies_and_stack_bound():
    expected = {'refresh': 4, 'extend': 6, 'keep': 3}
    for policy in expected:
        rt = runtime(rule('round_start', status(duration=3, stacking=policy, stacks=2, max_stacks=3)))
        execute(rt, 'round_start')
        rt.finish_round({})
        rt.begin_round(2)
        execute(rt, 'round_start')
        value = next(iter(rt.statuses.values()))
        assert value['stacks'] == 3 and value['expires'] == expected[policy]


def test_field_received_modifier_is_applied_only_to_field_damage():
    row = rule('effect_before_apply', modifier('field.received', -.5),
               when={'fact': 'role', 'op': 'eq', 'value': 'recipient'})
    d = domain(VoisinageEffect('strike', 2, .2))
    b = VoisinageBattle([actor('player', 'player', caster(d)), actor('e', 'enemy', CombatCapabilities(semantic_rules=(row,)))])
    begin(b)
    assert b.units['e'].vitality == pytest.approx(.9)
    assert b._semantic_totals['e', 'field', 'received'] == pytest.approx(.1)


def test_counter_to_later_field_buff_works_across_rounds_without_retroactivity():
    rows = (rule('ordinary_after_damage', count(), when={'fact': 'role', 'op': 'eq', 'value': 'attacker'}),
            rule('contest_prepare', modifier('field.incursion', .5), dict(op='counter_consume', key='n', value=1),
                 when={'all': [{'counter': 'n', 'op': 'ge', 'value': 1}, {'fact': 'role', 'op': 'eq', 'value': 'attacker'}]}))
    d = domain(stability=100, incursion=100)
    b = VoisinageBattle([actor('player', 'player', caster(d, semantic_rules=rows)), actor('e', 'enemy', caster(d))])
    begin(b)
    assert b.frame.relations['e']['relation'] == 'contested'
    b.ordinary_damage(.1, .1)
    assert b.frame.relations['e']['relation'] == 'contested'
    b.finish_round(player_mp=1, enemy_mp=1)
    begin(b, 2)
    assert b.frame.relations['e']['relation'] == 'dominated'
    assert list(b.semantics.counters.values()) == [0]


def test_semantic_morale_and_mp_follow_real_driver_context():
    rows = (rule('round_start', count(), when={'fact': 'self.morale', 'op': 'le', 'value': 20}),
            rule('round_end', dict(op='adjust', stat='morale', value=20)))
    b = VoisinageBattle([actor('player', 'player', CombatCapabilities(semantic_rules=rows)), actor('e', 'enemy')])
    b.begin_round(1, player_condition=1, enemy_condition=1, player_mp=.7, enemy_mp=1,
                  player_morale=20, enemy_morale=80)
    assert list(b.semantics.counters.values()) == [1]
    b.semantic_context(player_mp=.3, enemy_mp=.8, player_morale=30, enemy_morale=70)
    assert b._semantic_snapshot('player')['mp_ratio'] == .3
    assert b._semantic_snapshot('player')['morale'] == 30
    b.finish_round(player_mp=.3, enemy_mp=.8)
    assert b.semantics.previous['player']['morale'] == 50


def test_v3_is_not_silently_evaluated_as_a_legacy_rule():
    from cultivation_life.combat_rule_engine import evaluate_rules
    with pytest.raises(ValueError):
        evaluate_rules([rule('round_start', count())], trigger='round_start', context={'round_no': 1})


def test_npc_engagement_uses_the_same_modifier_and_real_damage_events():
    from cultivation_life.content_registry import WORLD_SYSTEMS
    from cultivation_life.models import SectNpc
    from cultivation_life.system.combat.npc_battle import resolve_npc_engagement
    def run(rows):
        a = SectNpc('a', 'a', '', 4, 1, 100, None)
        b = SectNpc('b', 'b', '', 4, 1, 100, None)
        return resolve_npc_engagement([(a, 100)], [(b, 100)], WORLD_SYSTEMS['transcendent_combat'],
            random.Random(3), max_rounds=1, sources={'a': CapabilitySource(semantic_rules=rows)})
    plain = (rule('round_start', count()),)
    strong = (*plain, rule('ordinary_before_damage', modifier('ordinary.dealt', .5),
                           when={'fact': 'role', 'op': 'eq', 'value': 'attacker'}))
    old, new = run(plain), run(strong)
    assert new.rounds[0]['voisinage']['semantics']['events'][-1]['trigger'] == 'ordinary_before_damage'
    assert len(new.rounds[0]['voisinage']['semantics']['events']) > len(old.rounds[0]['voisinage']['semantics']['events'])

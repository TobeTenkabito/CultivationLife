"""Bounded effect selection and explicit intervention; no content/actor lookup.

One action per established field, independent of ordinary actions, and one
response per protector per round. Effects
and responses never recursively dispatch one another. Resources are reserved
before simultaneous actions execute; ordinary initiative cannot undo control.
"""
from dataclasses import dataclass, replace

from .contracts import VoisinageEffect


@dataclass(frozen=True)
class EffectIntent:
    field: object
    effect: VoisinageEffect
    targets: tuple[str, ...]
    terminal: tuple[str, ...] = ()
    ordinary: bool = False
    semantic: object = None


class VoisinageEffects:
    def attack_tier(self, state, *, pay=False):
        c = state.unit.capabilities
        tier = max(1, c.artifact_tier if 'artifact' not in state.restrictions else 1,
                   c.technique_tier if 'technique' not in state.restrictions else 1)
        if (c.resource_tier >= 2 and state.current > 0 and state.current >= c.attack_cost
                and 'technique' not in state.restrictions and c.force_tier > tier):
            tier = c.force_tier
            if pay:
                state.current -= c.attack_cost
        return tier

    def _crush(self, field, key):
        target, source = self.units[key], self.units[field.owner]
        return (source.unit.cultivation_rank > target.unit.cultivation_rank >= 0
                and not target.unit.capabilities.voisinages
                and self.frame.relations[key]['protector'] is None)

    def _effect_power(self, field, effect, target, semantic=None):
        power = effect.power
        d = field.definition
        if semantic is None:
            semantic = self._semantic_preview(field.owner, 'effect_before_apply', target.unit.id,
                                               'caster', effect=effect.kind, restriction=effect.restriction or '', terminal=False)
        power *= self._semantic_factor(semantic, f'field.{effect.kind}')
        if d.authority is not None:
            power = min(1, power * field.authority * self._semantic_factor(semantic, 'field.authority') / d.authority_reference)
            if target.vitality < .5 and effect.kind == 'strike':
                power = min(1, power * (1 + next((f['value'] for f in d.features if f['kind'] == 'execution'), 0)))
        if effect.target == 'enemy':
            power *= 1 - target.unit.capabilities.body_voisinage_resistance
        return min(1., power)

    def _select_effect(self, field, previous):
        owner = self.units[field.owner]
        victims = [k for k in field.targets if self._dominated.get(k) == field.owner]
        purpose = self.objectives[owner.unit.side]
        ready = [k for k in victims if self._crush(field, k) and previous.get(k) == field.owner]
        normal = [k for k in victims if not self._crush(field, k)]
        candidates = []
        # A helpless opponent is not immune to an actual usable ordinary weapon.
        # Only eligible attack sources count; an objective never fabricates one.
        tier = self.attack_tier(owner)
        terminal_targets = tuple(k for k in ready if tier >= self.units[k].unit.capabilities.ward_tier)
        if terminal_targets and 'ordinary' not in owner.restrictions:
            c = owner.unit.capabilities
            passive = max(c.artifact_tier if 'artifact' not in owner.restrictions else 1,
                          c.technique_tier if 'technique' not in owner.restrictions else 1)
            cost = c.attack_cost if tier > passive else 0
            # This internal execution uses no voisinage fee: maintenance already
            # paid for control. Ordinary source fees, if any, still apply.
            effect = VoisinageEffect('strike' if purpose == 'kill' else 'suppress', cost, 1,
                                      defense='ward', tier=tier)
            candidates.append((-1, 0, EffectIntent(field, effect, terminal_targets, terminal_targets, True)))
        for index, effect in enumerate(field.definition.actions()):
            semantic = self._semantic_preview(field.owner, 'effect_prepare', role='caster',
                                               effect=effect.kind, restriction=effect.restriction or '')
            effect = replace(effect, cost=effect.cost * self._semantic_factor(semantic, 'field.effect_cost'))
            if effect.cost > owner.current:
                continue
            if effect.target == 'enemy':
                keys = [*normal, *ready]
                if effect.defense == 'ward':
                    keys = [k for k in keys if effect.tier >= self.units[k].unit.capabilities.ward_tier]
                if effect.kind in {'restrict', 'isolate'}:
                    keys = [k for k in keys if effect.restriction not in self.units[k].restrictions]
                priority = {'kill': {'strike': 1, 'suppress': 3, 'seal': 4},
                            'capture': {'suppress': 1, 'seal': 2, 'strike': 5}}.get(purpose, {'suppress': 1, 'seal': 2, 'strike': 5}).get(effect.kind, 3)
            else:
                keys = [field.owner] if effect.target == 'self' else list(field.protects)
                keys = [k for k in keys if self.units[k].fighting]
                if effect.kind == 'restore_body':
                    keys = [k for k in keys if self.units[k].body < 1 or self.units[k].vitality < 1]
                elif effect.kind == 'restore_spirit':
                    keys = [k for k in keys if self.units[k].pressure > 0 or self.units[k].morale < 100]
                else:
                    keys = [k for k in keys if self.units[k].field_strain > 0 and self.units[k].active_voisinage]
                priority = 0 if any(self.units[k].body < .5 or self.units[k].vitality < .5 for k in keys) else 2
            if keys:
                terminal = tuple(k for k in keys if k in ready and effect.target == 'enemy'
                                 and effect.kind in {'strike', 'suppress', 'seal'})
                candidates.append((priority, index + 1, EffectIntent(field, effect, tuple(keys), terminal, semantic=semantic)))
        return min(candidates, key=lambda row: row[:2])[2] if candidates else None

    def _intervene(self, intent, victim, responded):
        """An explicit response can protect only its owner or declared allies."""
        target = self.units[victim]
        if intent.effect.target != 'enemy':
            return False
        for key in self._responders:
            protector = self.units[key]
            c = protector.unit.capabilities
            if (key in responded or not protector.fighting or protector.unit.side != target.unit.side
                    or (key != victim and (victim not in c.protect_ids or not self._can_reach(protector, victim)
                                          or 'support' in protector.restrictions
                                          or 'support' in target.restrictions))):
                continue
            for response in c.interventions:
                if (response.source in protector.restrictions or response.cost > protector.current
                        or (intent.effect.kind not in response.effects
                            and not (victim in intent.terminal and 'execute' in response.effects))):
                    continue
                required = intent.field.strength if response.kind in {'shelter', 'disrupt'} else self._effect_power(intent.field, intent.effect, target)
                if response.strength < required:
                    continue
                if response.kind == 'escape' and (key != victim or target.unit.side in self.escape_forbidden_sides):
                    continue
                protector.current -= response.cost
                responded.add(key)
                if response.kind == 'escape':
                    target.escaped = True
                    self._released.add(victim)
                elif response.kind == 'shelter':
                    self._released.add(victim)
                elif response.kind == 'disrupt':
                    self._disrupted.add(intent.field.owner)
                    self.units[intent.field.owner].active_voisinage = None
                self.frame.events.append(f'{protector.unit.name}以明确的特殊能力介入，阻止对{target.unit.name}的邻域效果。')
                self._semantic_event(key, 'intervention_resolved', intent.field.owner, 'protector', intervention=response.kind)
                self._semantic_event(intent.field.owner, 'intervention_resolved', key, 'caster', intervention=response.kind)
                return True
        return False

    def _resolve_effects(self, previous):
        plans = []
        for field in sorted(self.fields, key=lambda f: f.owner):
            mutual = self._dominated.get(self._dominated.get(field.owner)) == field.owner
            if field.owner in self._dominated and not mutual:
                continue
            intent = self._select_effect(field, previous)
            if intent:
                plans.append(intent)
        responded, pending = set(), []
        for intent in plans:
            keys = tuple(k for k in intent.targets if not self._intervene(intent, k, responded))
            if keys:
                pending.append((intent, keys))
        self._refresh_relations()
        paid = []
        for intent, keys in pending:
            owner = self.units[intent.field.owner]
            if intent.field.owner in self._disrupted:
                continue
            if intent.effect.target == 'enemy':
                keys = tuple(k for k in keys if self._dominated.get(k) == intent.field.owner)
            if not keys:
                continue
            cost = intent.effect.cost
            if intent.ordinary:
                tier = self.attack_tier(owner)
                keys = tuple(k for k in keys if tier >= self.units[k].unit.capabilities.ward_tier)
                if not keys:
                    continue
                self.attack_tier(owner, pay=True)
                # A weapon execution spends the ordinary action; a field effect
                # (including restoration) leaves ordinary combat available.
                self._ordinary_acted.add(intent.field.owner)
            elif owner.current >= cost:
                owner.current -= cost
                self._semantic_commit(intent.semantic, {'field.effect_cost'})
            else:
                continue
            paid.append((intent, keys))
        # Simultaneous qualified actions survive a mutual breach; no list-order advantage.
        for intent, keys in sorted(paid, key=lambda row: row[0].effect.kind.startswith('restore_')):
            for key in keys:
                self._apply_effect(intent, key)
        self._refresh_relations()

    def _apply_effect(self, intent, key):
        target = self.units[key]
        effect, field = intent.effect, intent.field
        kind = effect.kind
        if kind.startswith('restore_') and not target.fighting:
            return
        semantic = None if intent.ordinary else self._semantic_preview(field.owner, 'effect_before_apply', key,
            'caster', effect=effect.kind, restriction=effect.restriction or '', terminal=key in intent.terminal)
        incoming = None if intent.ordinary else self._semantic_preview(key, 'effect_before_apply', field.owner,
            'recipient', effect=effect.kind, restriction=effect.restriction or '', terminal=key in intent.terminal)
        power = effect.power if intent.ordinary else self._effect_power(field, effect, target, semantic)
        before, body_before = target.vitality, target.body
        channels = {f'field.{kind}'} if kind in {'strike', 'suppress', 'seal', 'restore_body', 'restore_spirit', 'restore_field'} else set()
        if field.definition.authority is not None:
            channels.add('field.authority')
        if key in intent.terminal or kind in {'restrict', 'isolate'} or (kind in {'suppress', 'seal'} and field.definition.authority is None):
            channels.clear()
        self._semantic_commit(semantic, channels)
        mitigation = self._semantic_factor(incoming, 'field.received')
        cap = incoming.cap('field.received_cap') if incoming else 1.
        if kind in {'strike', 'suppress'} and key not in intent.terminal:
            self._semantic_commit(incoming, {'field.received', 'field.received_cap'})
        else:
            self._semantic_commit(incoming)
        purpose = self.objectives[self.units[field.owner].unit.side]
        if key in intent.terminal:
            if kind == 'strike' and purpose == 'kill':
                amount = target.vitality if intent.ordinary else max(target.vitality, effect.power) * (1 - target.unit.capabilities.body_voisinage_resistance)
                self._lose(key, amount)
            else:
                target.suppressed = True
            self.frame.events.append(f'{self.units[field.owner].unit.name}连续支配第二轮，以实际可用手段完成' +
                                     ('诛杀。' if kind == 'strike' and purpose == 'kill' else '制伏。'))
            self._semantic_effect_result(intent, key, before, body_before)
            return
        if kind == 'strike':
            amount = min(cap, power * mitigation)
            amount = amount if purpose == 'kill' else min(amount, max(0, target.vitality - .13))
            self._lose(key, amount)
        elif kind == 'suppress':
            amount = target.vitality * (1 - target.unit.capabilities.body_voisinage_resistance) if field.definition.authority is None else power
            self._lose(key, min(cap, amount * mitigation), physical=False)
            target.suppressed = target.vitality <= .12
        elif kind == 'seal':
            if field.definition.authority is not None:
                target.seal_progress = min(1, target.seal_progress + power)
                target.suppressed = target.seal_progress >= 1
            target.controls['communication'] = field.owner
            target.controls['support'] = field.owner
        elif kind in {'restrict', 'isolate'}:
            target.controls[effect.restriction] = field.owner
            if effect.restriction == 'voisinage':
                self._disrupted.add(key)
                target.active_voisinage = None
        elif kind == 'restore_body':
            if not target.fighting:
                return
            restored = min(power, 1 - target.body)
            target.body += restored
            if key == 'player':
                self.frame.primary_restore += restored
            self._restore_state(key, power)
        elif kind == 'restore_spirit':
            target.pressure = max(0, target.pressure - power)
            gain = min(100 - target.morale, power * 80)
            target.morale += gain
            side = target.unit.side
            self.frame.morale_loss[side] = self.frame.morale_loss.get(side, 0) - gain * target.unit.power / self.totals[side]
            self._restore_state(key, power)
        elif kind == 'restore_field':
            target.field_strain = max(0, target.field_strain - power)
        labels = {'strike': '杀伤', 'suppress': '镇压' if target.suppressed else '镇压侵蚀', 'seal': '封锁传讯与支援', 'restrict': '禁制',
                  'isolate': '隔离', 'restore_body': '修复肉身', 'restore_spirit': '稳定心神', 'restore_field': '修复邻域稳固'}
        self.frame.events.append(f'{self.units[field.owner].unit.name}的【{field.definition.name}】对{target.unit.name}施行{labels[kind]}。')
        self._semantic_effect_result(intent, key, before, body_before)

    def _semantic_effect_result(self, intent, key, before, body_before):
        if self.semantics is None:
            return
        target = self.units[key]
        source = 'ordinary' if intent.ordinary else 'field'
        loss = max(0., before - target.vitality)
        self._semantic_record_loss(intent.field.owner, key, loss, source)
        event = dict(effect=intent.effect.kind, restriction=intent.effect.restriction or '',
                     cost=intent.effect.cost, damage_source=source, amount=intent.effect.power,
                     actual_loss=loss, body_loss=max(0., body_before - target.body),
                     restored=max(0., target.vitality - before), terminal=key in intent.terminal)
        self._semantic_event(intent.field.owner, 'effect_resolved', key, 'caster', **event)
        if key != intent.field.owner:
            self._semantic_event(key, 'effect_resolved', intent.field.owner, 'recipient', **event)

    def _restore_state(self, key, amount):
        target = self.units[key]
        if not target.fighting:
            return
        gain = min(amount, 1 - target.vitality)
        target.vitality += gain
        attr = 'player_loss' if target.unit.side == 'player' else 'enemy_loss'
        setattr(self.frame, attr, getattr(self.frame, attr) - gain * target.unit.power / self.totals[target.unit.side])

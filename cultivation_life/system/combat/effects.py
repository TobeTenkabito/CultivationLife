"""Bounded effect selection and explicit intervention; no content/actor lookup.

Each established field consumes causal action allowances, with
one response per protector per round. Effects
and responses dispatch through the shared event queue. Resources are reserved
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
    allowance: object = None
    critical: bool = False
    direct_power: bool = False
    segment_scale: float = 1.
    discipline_action: str = ''
    discipline_data: dict | None = None


class VoisinageEffects:
    def attack_tier(self, state, *, pay=False):
        c = state.unit.capabilities
        if c.attack_resource_owner is not None:
            return self.pay_operating_attack(state) if pay else self.operating_attack(state)[0]
        tier = max(1, c.artifact_tier if 'artifact' not in state.restrictions else 1,
                   c.technique_tier if 'technique' not in state.restrictions else 1)
        if (c.resource_tier >= 2 and state.current > 0 and state.current >= c.attack_cost
                and 'technique' not in state.restrictions and c.force_tier > tier):
            tier = c.force_tier
            if pay:
                self._energy(state.unit.id,state.current-c.attack_cost)
        return tier

    def _crush(self, field, key):
        target, source = self.units[key], self.units[field.owner]
        return (source.unit.cultivation_rank > target.unit.cultivation_rank >= 0
                and not target.unit.capabilities.voisinages
                and self.frame.relations[key]['protector'] is None)

    def _effect_power(self, field, effect, target, semantic=None, *, critical=False):
        power = effect.power
        d = field.definition
        if semantic is None:
            semantic = self._semantic_preview(field.owner, 'effect_before_apply', target.unit.id,
                                               'caster', effect=effect.kind, restriction=effect.restriction or '', terminal=False)
        power *= self._semantic_factor(semantic, f'field.{effect.kind}')
        if d.authority is None:
            power *= 1+self._body_round.value(field.owner,'authority')
        if d.authority is not None:
            power = min(1, power * field.authority * self._semantic_factor(semantic, 'field.authority') / d.authority_reference)
            if target.vitality < .5 and effect.kind == 'strike':
                power = min(1, power * (1 + next((f['value'] for f in d.features if f['kind'] == 'execution'), 0)))
        if effect.target == 'enemy':
            power *= 1 - target.unit.capabilities.body_voisinage_resistance
        if critical:power *= self._body_round.value(field.owner,'critical')
        return min(1., power)

    def _select_effect(self, field, previous, allowance):
        owner = self.units[field.owner]
        if field.owner in self._light_muted or not owner.fighting or self._action_paused(field.owner):return None
        if allowance.requires_evade:
            selected=self._reaction_effect(field,allowance)
            if selected is None:return None
            effect,targets=selected
            return EffectIntent(field,effect,targets,allowance=allowance,
                critical=bool(self._body_round.channel(field.owner,'critical',allowance.chain)))
        victims = [k for k in field.targets if self.units[k].fighting and self._covered_by(field,k)]
        purpose = self.objectives[owner.unit.side]
        ready = [k for k in victims if self._crush(field, k) and previous.get(k) == field.owner]
        normal = [k for k in victims if not self._crush(field, k) or self._light_resists.get((k,field.owner),False)]
        candidates = []
        # A helpless opponent is not immune to an actual usable ordinary weapon.
        # Only eligible attack sources count; an objective never fabricates one.
        tier = self.attack_tier(owner)
        terminal_targets = tuple(k for k in ready if tier >= self.ward_tier(k))
        if terminal_targets and not allowance.source and 'ordinary' not in owner.restrictions and field.owner not in self._ordinary_acted:
            c = owner.unit.capabilities
            passive = max(c.artifact_tier if 'artifact' not in owner.restrictions else 1,
                          c.technique_tier if 'technique' not in owner.restrictions else 1)
            cost = c.attack_cost if tier > passive else 0
            # This internal execution uses no voisinage fee: maintenance already
            # paid for control. Ordinary source fees, if any, still apply.
            effect = VoisinageEffect('strike' if purpose == 'kill' else 'suppress', cost, 1,
                                      defense='ward', tier=tier)
            candidates.append((-1, 0, EffectIntent(field, effect, terminal_targets, terminal_targets, True)))
        for index, option in enumerate(self._field_options(field,allowance)):
            effect=option.effect
            semantic = self._semantic_preview(field.owner, 'effect_prepare', role='caster',
                                               effect=effect.kind, restriction=effect.restriction or '')
            effect = replace(effect, cost=effect.cost * self._semantic_factor(semantic, 'field.effect_cost'))
            if allowance.free:effect=replace(effect,cost=0)
            if not self._field_can_quote(field.owner,effect.cost,dict(option.data,chain=allowance.chain)):
                continue
            if effect.target == 'enemy':
                keys = [*normal, *ready]
                if effect.defense == 'ward':
                    keys = [k for k in keys if effect.tier >= self.ward_tier(k,damage=effect.kind=='strike')]
                if effect.kind in {'restrict', 'isolate'}:
                    keys = [k for k in keys if effect.restriction not in self.units[k].restrictions]
                priority = {'kill': {'strike': 1, 'suppress': 3, 'seal': 4},
                            'capture': {'suppress': 1, 'seal': 2, 'strike': 5}}.get(purpose, {'suppress': 1, 'seal': 2, 'strike': 5}).get(effect.kind, 3)
            else:
                if not self.light_value(field.owner,'zhen') and (field.owner in self._ordinary_acted or field.owner in self._dominated or 'ordinary' in owner.restrictions):
                    continue
                keys = [field.owner] if effect.target == 'self' else list(field.protects)
                keys = [k for k in keys if self.units[k].fighting]
                threshold=field.definition.restore_threshold
                if effect.kind == 'restore_body':
                    keys = [k for k in keys if min(self.units[k].body,self.units[k].vitality) < threshold]
                elif effect.kind == 'restore_spirit':
                    d=self._discipline(field.owner)
                    keys = [k for k in keys if self.units[k].pressure > 1-threshold or self.units[k].morale < 100*threshold or
                            d and (d.kind=='echo' or option.data.get('state_only')) and self.units[k].vitality<threshold]
                else:
                    keys = [k for k in keys if self.units[k].field_strain > 1-threshold and self.units[k].active_voisinage]
                if not keys and threshold<1 and not allowance.source:
                    self.frame.events.append(f'{owner.unit.name}的【{field.definition.name}】未达{threshold:.0%}自动修复阈值，本次不施疗，普通出手仍按原资格结算。')
                priority = 0 if any(self.units[k].body < .5 or self.units[k].vitality < .5 for k in keys) else 2
            keys=self._field_option_targets(field,option,keys)
            if keys and (not option.action or self._field_action_path(field.owner,option.action,allowance.chain) is not None):
                terminal = tuple(k for k in keys if k in ready and effect.target == 'enemy'
                                 and effect.kind in {'strike', 'suppress', 'seal'})
                candidates.append((priority if option.priority is None else option.priority, index + 1,
                    EffectIntent(field,effect,tuple(keys),terminal,semantic=semantic,
                                 discipline_action=option.action,discipline_data=option.data)))
        if not candidates:
            self._field_idle(field.owner,allowance)
            return None
        intent=min(candidates,key=lambda row:row[:2])[2]
        numeric=(intent.effect.kind=='strike' or intent.effect.kind.startswith('restore_') or
                 intent.effect.kind in {'suppress','seal'} and field.definition.authority is not None)
        critical=bool(not intent.ordinary and numeric and self._body_round.channel(field.owner,'critical',allowance.chain)
                      and any(k not in intent.terminal for k in intent.targets))
        return replace(intent,allowance=allowance,critical=critical)

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
                required = intent.field.strength if response.kind in {'shelter', 'disrupt'} else self._effect_power(intent.field, intent.effect, target,critical=intent.critical)
                if response.strength < required:
                    continue
                if response.kind == 'escape' and (key != victim or target.unit.side in self.escape_forbidden_sides):
                    continue
                self._energy(key,protector.current-response.cost,intent.allowance.chain)
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
                if self.animation is not None:
                    self.animation['interventions'].append(dict(owner=key, target=victim,
                        attacker=intent.field.owner, kind=response.kind))
                self._semantic_event(key, 'intervention_resolved', intent.field.owner, 'protector', intervention=response.kind)
                self._semantic_event(intent.field.owner, 'intervention_resolved', key, 'caster', intervention=response.kind)
                return True
        return False

    def _resolve_effects(self, previous):
        plans = []
        priority={key:i for i,key in enumerate(self._unit_order())}
        for field in sorted(self.fields, key=lambda f:priority[f.owner]):
            allowance=self._body_round.take(field.owner)
            if allowance is None:continue
            mutual = self._dominated.get(self._dominated.get(field.owner)) == field.owner
            if field.owner in self._dominated and not mutual and not allowance.requires_evade:
                continue
            intent = self._select_effect(field, previous,allowance)
            if intent and not self._field_hold(intent):
                plans.append(intent)
        responded, pending = self._responded, []
        for intent in plans:
            keys=intent.targets
            if intent.effect.target!='self' and intent.effect.target_mode=='single' and keys:
                split=not intent.ordinary and not intent.terminal and self._split_entry(intent.field.owner,intent.allowance.chain)
                index=min(len(keys)-1,int(self._light_rng.random()*len(keys))) if split else 0
                keys=(keys[index],)
            keys = tuple(k for k in keys if not self._intervene(intent, k, responded))
            if keys:
                pending.append((intent, keys))
        self._refresh_relations()
        paid = []
        for intent, keys in pending:
            owner = self.units[intent.field.owner]
            if intent.field.owner in self._disrupted:
                continue
            if intent.effect.target == 'enemy':
                if intent.allowance.requires_evade:
                    keys=tuple(k for k in keys if k==intent.allowance.target and self.units[k].fighting and self._can_reach(owner,k))
                else:keys = tuple(k for k in keys if self._covered_by(intent.field,k))
            if not keys:
                continue
            cost = intent.effect.cost
            if intent.ordinary:
                tier = self.attack_tier(owner)
                keys = tuple(k for k in keys if tier >= self.ward_tier(k))
                if not keys:
                    continue
                self.attack_tier(owner, pay=True)
                self._ordinary_acted.add(intent.field.owner)
            else:
                intent=self._pay_field_intent(intent)
                if intent is None:continue
                cost=intent.discipline_data['actual_cost']
                channels = set() if intent.allowance.free else {'field.effect_cost'}
                self._semantic_commit(intent.semantic, channels)
            if intent.effect.kind.startswith('restore_'):
                zhen=self.light_value(intent.field.owner,'zhen')
                if not zhen and not intent.allowance.requires_evade:self._ordinary_acted.add(intent.field.owner)
                name=owner.unit.name
                if intent.allowance.requires_evade:self._light_note('body_reaction',intent.field.owner,f'{name}以烈脏兑现免费治疗，不占普通出手或基础邻域行动。',cost=0,ordinary_spent=False)
                elif zhen:self._light_note('zhen_action',intent.field.owner,f'{name}以震合缥光维持治疗：消耗一次邻域行动与{cost:g}元力，保留普通出手。',cost=cost,ordinary_spent=False)
                else:self.frame.events.append(f'{name}尚未解锁震合缥光，邻域治疗占用本回合一次普通出手，并消耗{cost:g}元力。')
            if not intent.ordinary:
                source='额外' if intent.allowance.source else '基础'
                message=f'{owner.unit.name}完成一次{source}邻域施权，元力消耗{cost:g}'
                if intent.critical:message+='，轮首暴击生效，数值为基础的200%'
                if intent.allowance.free and not intent.allowance.requires_evade:message+='（该份额外施权免费判定成功）'
                if intent.allowance.requires_evade:message+=f'，烈脏本次择一执行{self._body_effect_label(intent.effect)}'
                self._light_note('body_action',intent.field.owner,message+'。',source=intent.allowance.source,
                                 cost=cost,critical=intent.critical,free=intent.allowance.free)
            paid.append((intent, keys))
        # Simultaneous qualified actions survive a mutual breach; no list-order advantage.
        completed=[]
        for intent, keys in sorted(paid, key=lambda row: row[0].effect.kind.startswith('restore_')):
            applied,chain=self._perform_body_intent(intent,keys)
            self._field_action_completed(intent,chain)
            if not intent.ordinary:completed.append((intent.field.owner,replace(intent.allowance,chain=chain),intent.critical and applied))
        self._refresh_relations()
        self._complete_body_actions(completed)
        self._drain_body_events()

    def _apply_effect(self, intent, key):
        target = self.units[key]
        effect, field = intent.effect, intent.field
        kind = effect.kind
        if not intent.ordinary and field.owner in self._light_muted:return
        if effect.target=='enemy' and self._body_evade(intent,key):return False
        if (intent.allowance and intent.allowance.requires_evade and
                (kind in {'seal','restrict','isolate'} or kind=='suppress' and field.definition.authority is None)):
            configured=any('retaliate_control' in row['effects'] for row in self._body_round.records[field.owner].values())
            chance=min(1.,self._body_round.value(field.owner,'retaliate_control')) if configured else 1.
            success=chance>=1 or chance>0 and self._light_rng.random()<chance
            self._light_note('reaction_control',field.owner,
                f'{self.units[field.owner].unit.name}的烈脏控制反击判定'+('成功' if success else '未成')+f'（概率{chance:.1%}）。',
                target=key,probability=chance,success=success)
            if not success:return False
        if (intent.segment_scale<1 and (kind in {'restrict','isolate'} or
                kind in {'suppress','seal'} and field.definition.authority is None)
                and self._light_rng.random()>=intent.segment_scale):return False
        if kind in {'seal','restrict','isolate'} and self._resist_light_seal(key,field.owner):return
        if kind.startswith('restore_') and not target.fighting:
            return
        semantic = None if intent.ordinary else self._semantic_preview(field.owner, 'effect_before_apply', key,
            'caster', effect=effect.kind, restriction=effect.restriction or '', terminal=key in intent.terminal)
        incoming = None if intent.ordinary else self._semantic_preview(key, 'effect_before_apply', field.owner,
            'recipient', effect=effect.kind, restriction=effect.restriction or '', terminal=key in intent.terminal)
        power = effect.power if intent.ordinary or intent.direct_power else self._effect_power(field, effect, target, semantic,critical=intent.critical)
        if kind.startswith('restore_'):
            bonus=self.light_value(field.owner,'zhen_heal')
            if bonus:
                original=power;power=min(1.,power*(1+bonus))
                self._light_note('zhen_heal',field.owner,f'{self.units[field.owner].unit.name}的震合缥光令治疗比例提高{bonus:.0%}，本次治疗强度由{original:.2%}提升至{power:.2%}。',target=key,bonus=bonus,before=original,after=power)
        power*=intent.segment_scale
        before, body_before = target.vitality, target.body
        power_before=dict(state=before,body=body_before,pressure=target.pressure,morale=target.morale,
            strain=target.field_strain,seal=target.seal_progress,restrictions=tuple(target.restrictions))
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
            injury=amount
            if effect.tier>=2:amount=self._guard_state(key,amount)
            self._lose(key, amount,body_amount=injury)
            extra=min(max(0,cap-amount),amount*self._body_round.amplification(field.owner,key))
            if purpose!='kill':extra=min(extra,max(0,target.vitality-.13))
            if extra:
                self._lose(key,extra,physical=False)
                self.frame.events.append(f'{self.units[field.owner].unit.name}的炼体增幅额外削弱{target.unit.name}战斗态势{extra:.2%}，不增加肉身伤害。')
        elif kind == 'suppress':
            amount = target.vitality * (1 - target.unit.capabilities.body_voisinage_resistance) if field.definition.authority is None else power
            amount *= 1+self._body_round.amplification(field.owner,key)
            amount=min(cap,amount*mitigation)
            if effect.tier>=2:amount=self._guard_state(key,amount)
            self._lose(key, amount, physical=False,lethal=False)
            target.suppressed = target.vitality <= .12
        elif kind == 'seal':
            if field.definition.authority is not None:
                target.seal_progress = min(1, target.seal_progress + power)
                target.suppressed = target.seal_progress >= 1
            target.controls['communication'] = field.owner
            target.controls['support'] = field.owner
        elif kind in {'restrict', 'isolate'}:
            if (intent.discipline_data or {}).get('timed'):self._install_field_control(intent,key)
            else:target.controls[effect.restriction] = field.owner
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
            if not (intent.discipline_data or {}).get('state_only'):
                target.pressure = max(0, target.pressure - power)
                gain = min(100 - target.morale, power * 80)
                target.morale += gain
                side = target.unit.side
                self.frame.morale_loss[side] = self.frame.morale_loss.get(side, 0) - gain * target.unit.power / self.totals[side]
            self._restore_state(key, power)
        elif kind == 'restore_field':
            target.field_strain = max(0, target.field_strain - self._body_recovery(key,power))
        labels = {'strike': '杀伤', 'suppress': '镇压' if target.suppressed else '镇压侵蚀', 'seal': '封锁传讯与支援', 'restrict': '禁制',
                  'isolate': '隔离', 'restore_body': '修复肉身', 'restore_spirit': '稳定心神', 'restore_field': '修复邻域稳固'}
        self.frame.events.append(f'{self.units[field.owner].unit.name}的【{field.definition.name}】对{target.unit.name}施行{labels[kind]}。')
        self._semantic_effect_result(intent, key, before, body_before)
        self._field_after_effect(intent,key,power_before,power)
        return True

    def _semantic_effect_result(self, intent, key, before, body_before):
        if self.animation is not None:
            target = self.units[key]
            self.animation['effects'].append(dict(owner=intent.field.owner, target=key,
                kind=intent.effect.kind, restriction=intent.effect.restriction or '',
                source='ordinary' if intent.ordinary else 'field',
                loss=max(0., before-target.vitality), body_loss=max(0., body_before-target.body),
                restored=max(0., target.vitality-before)))
        if self.semantics is None:
            return
        target = self.units[key]
        source = 'ordinary' if intent.ordinary else 'field'
        loss = max(0., before - target.vitality)
        self._semantic_record_loss(intent.field.owner, key, loss, source)
        event = dict(effect=intent.effect.kind, restriction=intent.effect.restriction or '',
                     cost=intent.effect.cost, damage_source=source, amount=intent.effect.power*intent.segment_scale,
                     actual_loss=loss, body_loss=max(0., body_before - target.body),
                     restored=max(0., target.vitality - before), terminal=key in intent.terminal)
        self._semantic_event(intent.field.owner, 'effect_resolved', key, 'caster', **event)
        if key != intent.field.owner:
            self._semantic_event(key, 'effect_resolved', intent.field.owner, 'recipient', **event)

    def _restore_state(self, key, amount, *, maximum_gain=None):
        target = self.units[key]
        if not target.fighting:
            return
        gain = min(self._body_recovery(key,amount), 1 - target.vitality)
        if maximum_gain is not None:
            gain = min(gain, max(0., maximum_gain))
        target.vitality += gain
        self._field_healed(key,gain)
        attr = 'player_loss' if target.unit.side == 'player' else 'enemy_loss'
        setattr(self.frame, attr, getattr(self.frame, attr) - gain * target.unit.power / self.totals[target.unit.side])

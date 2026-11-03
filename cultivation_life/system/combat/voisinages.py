"""Deterministic voisinage arbitration with per-unit coverage and resource ledgers.

There is no game-state mutation, world lookup or cultivation progression here.
Probabilistic divine lights use only the caller's explicit battle RNG.
Definitions express capabilities, not executable content or callbacks.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Any

from .effects import VoisinageEffects
from .semantics import CombatSemantics
from .divine_lights import DivineLights
from .body_events import BodyEvents
from .field_powers import FieldPowers
from .field_events import FieldEvents
from .field_economy import FieldEconomy
from .contracts import Combatant, VoisinageDefinition, PhaseRound, ResourceSupply, VoisinageSeal, number


@dataclass
class UnitState:
    unit: Combatant
    current: float
    vitality: float
    active_voisinage: str | None = None
    suppressed: bool = False
    escape_locked: bool = False
    sustained_rounds: int = 0
    resisted: bool = False
    seal_progress: float = 0.0
    pressure: float = 0.0
    body: float = 1.0
    morale: float = 100.0
    field_strain: float = 0.0
    escaped: bool = False
    controls: dict[str, str] = field(default_factory=dict)
    exchange_used: bool = False
    karma_spent: float = 0.
    last_attack_targets: tuple | None = None
    death_observed: bool = False
    release_recovery_round: int = 0
    field_memory: dict = field(default_factory=dict)
    timed_controls: dict = field(default_factory=dict)
    field_debts: dict = field(default_factory=dict)

    @property
    def restrictions(self):
        return tuple(sorted(set(self.controls)|set(self.timed_controls)))

    @property
    def fighting(self) -> bool:
        threshold = 0.0 if self.unit.id == "player" else 0.12
        return self.vitality > threshold and self.body>0 and not self.suppressed and not self.escaped


@dataclass(frozen=True)
class Field:
    owner: str
    definition: VoisinageDefinition
    strength: float
    protects: tuple[str, ...]
    targets: tuple[str, ...]
    stability: float = 0
    authority: float | None = None


class VoisinageBattle(CombatSemantics, VoisinageEffects, DivineLights, BodyEvents, FieldPowers, FieldEvents, FieldEconomy):
    """One battle's upper layer. Ordinary combat remains the damage provider."""

    def __init__(self, units: list[Combatant], *, contest_ratio: float = 1.25,
                 supplies: tuple[ResourceSupply, ...] = (), seals: tuple[VoisinageSeal, ...] = ()):
        self.contest_ratio = number(contest_ratio, "contest_ratio", minimum=1.0)
        if len({u.id for u in units}) != len(units):
            raise ValueError("Combatant ids must be unique")
        if any(u.side not in {"player", "enemy"} for u in units):
            raise ValueError("Unknown combatant side")
        self.units = {u.id: UnitState(u, u.capabilities.current, u.integrity, body=u.body_integrity) for u in units}
        self._responders = tuple(sorted(u.id for u in units if u.capabilities.interventions))
        for supply in supplies:
            if supply.owner not in self.units or (supply.source_id is not None and supply.source_id not in self.units):
                raise ValueError("Supply owner and source must be present in the battle")
        self.supplies = supplies
        if any(seal.owner not in self.units for seal in seals):
            raise ValueError("Seal owner must be present in the battle")
        self.seals = seals
        self._applied_seals: set[int] = set()
        self.totals = {side: max(1.0, sum(u.power for u in units if u.side == side))
                       for side in ("player", "enemy")}
        self.fields: list[Field] = []
        self.animation = None
        self.frame = PhaseRound(0)
        self._ordinary_acted: set[str] = set()
        self._dominated: dict[str, str] = {}
        self._blocked_pairs: set[tuple[str, str]] = set()
        self._released: set[str] = set()
        self._disrupted: set[str] = set()
        self._light_muted={};self._light_trace=[];self._light_resists={};self._light_extra={}
        self._light_rng=None;self._responded=set()
        self._body_round=None
        self._init_body_events()
        self._init_field_powers()
        for state in self.units.values():state.death_observed=state.vitality<=0 or state.body<=0
        self.primary_ordinary_loss = 0.0
        self.primary_ordinary_body_loss = 0.0
        self.objectives = {"player": "kill", "enemy": "kill"}
        self.escape_forbidden_sides: frozenset[str] = frozenset()
        self._init_semantics()

    def set_objectives(self, player: str, enemy: str) -> None:
        if player not in {'kill', 'capture', 'repel', 'defeat'} or enemy not in {'kill', 'capture', 'repel', 'defeat'}:
            raise ValueError('Unknown battle objective')
        self.objectives = {"player": player, "enemy": enemy}

    def _unit_order(self):
        return self._body_round.order if self._body_round is not None else sorted(self.units)

    @property
    def enabled(self) -> bool:
        return self.semantics is not None or any(s.unit.capabilities.body_mechanisms or s.unit.capabilities.divine_lights or s.unit.capabilities.voisinages or s.unit.capabilities.force_tier > 1
                   or s.unit.capabilities.ward_tier > 1 or s.unit.capabilities.technique_tier > 1
                   or s.unit.capabilities.artifact_tier > 1 for s in self.units.values())

    def _can_reach(self, owner: UnitState, target: str) -> bool:
        reach = owner.unit.capabilities.reachable_ids
        return reach is None or target == owner.unit.id or target in reach

    def _field(self, owner: UnitState, condition: float) -> Field | None:
        c = owner.unit.capabilities
        if not owner.fighting or c.sealed or c.stance == "off" or c.resource_tier < 2 or "voisinage" in owner.restrictions:
            owner.active_voisinage = None
            return None
        candidates = sorted((d for d in c.voisinages if c.attainments.get(d.attainment, 0) >= d.required_level), key=lambda d: (
            d.strength + d.strength_per_level * max(0, c.attainments.get(d.attainment, 0) - d.required_level), d.id),
            reverse=True)
        for definition in candidates:
            if self._action_paused(owner.unit.id) and owner.active_voisinage!=definition.id:
                continue
            features = {row["kind"]: row["value"] for row in definition.features}
            continued = owner.active_voisinage == definition.id
            semantic = self._semantic_preview(owner.unit.id, 'field_prepare', continued=continued)
            opening_factor = self._semantic_factor(semantic, 'field.opening_cost')
            upkeep_factor = self._semantic_factor(semantic, 'field.upkeep_cost')
            extra_factor = self._semantic_factor(semantic, 'field.extra_target_cost')
            rounds = owner.sustained_rounds + 1 if continued else 1
            protects = [owner.unit.id]
            if c.stance == "protect" and "support" not in owner.restrictions:
                protects += [key for key in c.protect_ids if key in self.units and key != owner.unit.id
                             and self.units[key].unit.side == owner.unit.side
                             and self.units[key].fighting and "support" not in self.units[key].restrictions and self._can_reach(owner, key)]
            targets = []
            if c.stance == "press":
                preferred = c.target_ids or tuple(sorted(self.units))
                targets = [key for key in preferred if key in self.units
                           and self.units[key].unit.side != owner.unit.side
                           and self.units[key].fighting and self._can_reach(owner, key)]
                targets=self._field_coverage_targets(owner,definition,targets)
            protects = list(dict.fromkeys(protects))[:definition.max_targets]
            targets = list(dict.fromkeys(targets))[:definition.max_targets]
            opening = definition.opening_cost * opening_factor if not continued else 0.0
            # Shrink optional coverage before giving up protection of the caster.
            while True:
                extras = len(protects) - 1 + len(targets)
                upkeep = definition.upkeep_cost * upkeep_factor * (1 - features.get("frugal", 0) if rounds > 1 else 1)
                cost = opening + upkeep + extras * definition.extra_target_cost * extra_factor
                if cost <= owner.current:
                    break
                if targets:
                    targets.pop()
                elif len(protects) > 1:
                    protects.pop()
                else:
                    break
            if cost > owner.current:
                continue
            limit = definition.max_investment if c.investment_limit is None else c.investment_limit
            investment = min(c.investment, limit, owner.current - cost)
            self._energy(owner.unit.id,owner.current-cost-investment)
            used = {'field.upkeep_cost'}
            if not continued:
                used.add('field.opening_cost')
            if extras:
                used.add('field.extra_target_cost')
            self._semantic_commit(semantic, used)
            base = definition.strength + definition.strength_per_level * max(
                0.0, c.attainments.get(definition.attainment, 0) - definition.required_level)
            factor = max(0.0, condition) * (1 + investment / max(1.0, definition.max_investment))
            factor /= 1 + 0.25 * (1 - features.get("shelter", 0)) * (len(protects) - 1 + len(targets))
            strength = (base if definition.incursion is None else definition.incursion) * factor
            stability = (base if definition.stability is None else definition.stability) * factor
            stability *= (1 + features.get("fortify", 0) * min(3, rounds - 1)) * (1 - owner.field_strain)
            strength *= 1 + (features.get("opening", 0) if rounds == 1 else 0)
            strength *= 1 + (features.get("retaliate", 0) if owner.resisted and continued else 0)
            strength *= 1 + features.get("sacrifice", 0)
            strength *= 1+self._body_round.value(owner.unit.id,'incursion')
            stability *= 1 - features.get("sacrifice", 0)
            owner.active_voisinage = definition.id
            owner.sustained_rounds = rounds
            self._semantic_event(owner.unit.id, 'field_established', continued=continued, cost=cost + investment)
            self.frame.events.append(f"{owner.unit.name}维持【{definition.name}】，仙灵力消耗 {cost + investment:g}。")
            authority = definition.authority
            if authority is not None:
                authority *= 1 + investment / max(1.0, definition.max_investment)
                authority *= 1 + self._body_round.value(owner.unit.id,'authority')
            return Field(owner.unit.id, definition, strength, tuple(protects), tuple(targets), stability, authority)
        if candidates and self._action_paused(owner.unit.id) and owner.active_voisinage is None:
            self.frame.events.append(f"{owner.unit.name}沸血调息中，本回合不能新展开邻域。")
        elif candidates:
            self.frame.events.append(f"{owner.unit.name}仙灵力不足，无法展开或维持仙域。")
        owner.active_voisinage = None
        return None

    def begin_round(self, round_no: int, *, player_condition: float, enemy_condition: float,
                    player_mp: float, enemy_mp: float, player_morale=None, enemy_morale=None,
                    rng=None, first_side=None) -> PhaseRound:
        self.frame = PhaseRound(round_no)
        self.animation = {'version': 1, 'opening': [max(0., 1 - self.ordinary_loss(side))
                          for side in ('player', 'enemy')], 'effects': [], 'interventions': []}
        self._ordinary_acted.clear()
        self._released.clear()
        self._disrupted.clear()
        self._responded.clear()
        for state in self.units.values():
            if state.unit.capabilities.resource_link=='legacy_mp':
                ratio=player_mp if state.unit.side=='player' else enemy_mp
                state.current=min(state.current,max(0.,ratio)*state.unit.capabilities.capacity)
        self._begin_lights(rng,first_side)
        self._begin_field_powers()
        self._swap_body_energy()
        self._semantic_begin(round_no, player_mp, enemy_mp, player_morale, enemy_morale)
        # Scripted interventions happen before maintenance, coverage or effects.
        # Only this battle's immutable snapshot changes, never the saved owner.
        for index, seal in enumerate(self.seals):
            if round_no >= seal.first_round and index not in self._applied_seals:
                state = self.units[seal.owner]
                state.unit = replace(state.unit, capabilities=replace(state.unit.capabilities, sealed=True))
                state.active_voisinage = None
                self._disrupted.add(seal.owner)
                self._applied_seals.add(index)
                self.frame.events.append(seal.message)
        if self._disrupted:
            self._refresh_relations()
        previous = self._dominated.copy()
        self._dominated.clear()
        self._blocked_pairs.clear()
        self.fields = []
        for state in self.units.values():
            state.escape_locked = False
        for supply in self.supplies:
            owner = self.units[supply.owner]
            if (not owner.fighting or "supply" in owner.restrictions or owner.unit.capabilities.resource_tier < 2
                    or round_no < supply.first_round
                    or (supply.last_round is not None and round_no > supply.last_round)
                    or (supply.source_id is not None and (not self.units[supply.source_id].fighting
                                                        or "supply" in self.units[supply.source_id].restrictions))):
                continue
            c = owner.unit.capabilities
            limit = c.capacity if c.usable_capacity is None else c.usable_capacity
            gained = min(supply.amount, max(0.0, limit - owner.current))
            owner.current += gained
            if gained:
                self.frame.events.append(f"{owner.unit.name}获得明确仙力供给 {gained:g}。")
        # All affordable fields are established before any domination effects.
        held_fields={key for key,s in self.units.items() if 'voisinage' in s.timed_controls}
        for key in self._unit_order():
            state=self.units[key]
            field = self._field(state, state.vitality)
            if field:
                self.fields.append(field)
        self._expire_field_controls(live=True)
        for key in self._unit_order():
            state=self.units[key]
            if key in held_fields and 'voisinage' not in state.restrictions and state.active_voisinage is None:
                field=self._field(state,state.vitality)
                if field:self.fields.append(field)
        for key in self._unit_order():
            state=self.units[key]
            attackers = [f for f in self.fields if key in f.targets]
            defenders = [f for f in self.fields if key in f.protects]
            attack = max(attackers, key=lambda f: (f.strength, f.owner), default=None)
            defense = max(defenders, key=lambda f: (f.stability, f.owner), default=None)
            relation = "uncovered"
            attack_strength = attack.strength if attack else 0.
            defense_strength = defense.stability if defense else 0.
            if attack:
                attack_plan = self._semantic_preview(attack.owner, 'contest_prepare', key, 'attacker')
                defense_plan = self._semantic_preview(defense.owner, 'contest_prepare', attack.owner, 'defender') if defense else None
                attack_strength *= self._semantic_factor(attack_plan, 'field.incursion')
                defense_strength *= self._semantic_factor(defense_plan, 'field.stability')
                self._semantic_commit(attack_plan, {'field.incursion'})
                self._semantic_commit(defense_plan, {'field.stability'})
                if defense and attack_strength <= defense_strength * self.contest_ratio:
                    relation = "pressed" if attack_strength > defense_strength else "contested"
                else:
                    if attack.owner in self._light_muted:
                        relation='silenced'
                        self.frame.events.append(f'{self.units[attack.owner].unit.name}的邻域封禁被乾古素光静默，未作用于{state.unit.name}。')
                    elif self._resist_light_seal(key,attack.owner):relation='resisted'
                    else:
                        relation = "dominated"
                        self._dominated[key] = attack.owner
                        state.escape_locked = True
                        self.frame.events.append(f"{self.units[attack.owner].unit.name}封禁{state.unit.name}的神识、身法与退路。")
            self.frame.relations[key] = {
                "relation": relation, "attacker": attack.owner if attack else None,
                "protector": defense.owner if defense else None,
                "attack_strength": round(attack_strength, 4),
                "defense_strength": round(defense_strength, 4),
            }
            state.resisted = relation in {"pressed", "contested"}
        self._release_body_domination()
        # Publish only after every directional contest has settled; newly gained
        # marks cannot retroactively change this round's contests.
        for key, relation in self.frame.relations.items():
            if relation['attacker']:
                event = dict(relation=relation['relation'], incursion=relation['attack_strength'], stability=relation['defense_strength'])
                self._semantic_event(relation['attacker'], 'contest_resolved', key, 'attacker', **event)
                self._semantic_event(key, 'contest_resolved', relation['attacker'], 'defender', **event)
        # Maintenance pays for dominance itself; it is not contingent on an
        # additional active effect being affordable.
        for key, owner in self._dominated.items():
            if previous.get(key) != owner:
                continue
            target = self.units[key]
            gap = self.frame.relations[key]['attack_strength'] / max(1.0, self.frame.relations[key]['defense_strength'])
            erosion = min(.55, .12 + .08 * max(0, gap - self.contest_ratio))
            erosion *= 1 - target.unit.capabilities.body_voisinage_resistance
            erosion *= 1+self._body_round.amplification(owner,key)
            target.pressure = min(.85, target.pressure + erosion)
            before_pressure_loss = target.vitality
            state_loss=min(max(0,target.vitality-.13),erosion)
            source_field=next(f for f in self.fields if f.owner==owner)
            if max(e.tier for e in source_field.definition.actions())>=2:state_loss=self._guard_state(key,state_loss)
            self._lose(key,state_loss,physical=False)
            lost = min(target.morale, erosion * 80)
            target.morale -= lost
            side = target.unit.side
            self.frame.morale_loss[side] = self.frame.morale_loss.get(side, 0) + lost * target.unit.power / self.totals[side]
            self.frame.events.append(f"连续支配侵蚀战意与战斗态势，威能差距 {gap:.2f} 倍。")
            actual = before_pressure_loss - target.vitality
            self._semantic_record_loss(owner, key, actual, 'pressure')
            event = dict(damage_source='pressure', amount=erosion, actual_loss=actual, body_loss=0.)
            self._semantic_event(owner, 'pressure_resolved', key, 'attacker', **event)
            self._semantic_event(key, 'pressure_resolved', owner, 'defender', **event)
        for key, relation in self.frame.relations.items():
            if relation['relation'] in {'pressed', 'dominated'} and self.units[key].active_voisinage:
                source=relation.get('attacker')
                bonus=self._body_round.amplification(source,key) if source else 0
                self.units[key].field_strain = min(.5, self.units[key].field_strain + .05*(1+bonus))
        # Capture established coverage before effects can release or destroy it.
        # This is a bounded report projection, never an input to settlement.
        self.animation['fields'] = self.report()['fields']
        self.animation['relations'] = {key: dict(value) for key, value in self.frame.relations.items()}
        self._field_lights()
        self._drain_body_events()
        self._execute_field_actions(previous)
        self.animation['after'] = [max(0., 1 - self.ordinary_loss(side)) for side in ('player', 'enemy')]
        for side in ('player', 'enemy'):
            members = [self.units[key] for key in sorted(self.units) if self.units[key].unit.side == side]
            # Lingering disruption survives loss of the field, within this battle.
            factor = sum(s.unit.power * (0 if s.unit.id in self._dominated else 1 - s.pressure)
                         for s in members) / self.totals[side]
            self.frame.stat_factors[side] = {'sense': factor, 'mobility': factor}
        self.frame.ordinary_player = self._has_ordinary("player")
        self.frame.ordinary_enemy = self._has_ordinary("enemy")
        self.frame.blocked_actions = {key: tuple(s.restrictions) for key, s in self.units.items() if s.restrictions}
        return self.frame

    def _available(self, key: str) -> bool:
        return (self.units[key].fighting and not self._action_paused(key) and key not in self._dominated and key not in self._ordinary_acted
                and "ordinary" not in self.units[key].restrictions)

    def _has_ordinary(self, side: str) -> bool:
        return (any(self._available(key) and s.unit.side == side for key, s in self.units.items())
                and any(s.fighting and s.unit.side != side and key not in self._dominated
                        for key, s in self.units.items()))

    def _lose(self, key: str, amount: float, *, physical=True,body_amount=None,lethal=True) -> float:
        state = self.units[key]
        before=state.vitality
        actual = min(state.vitality, max(0.0, amount))
        state.vitality -= actual
        if physical:
            injury=actual if body_amount is None else min(before,max(0,body_amount))
            state.body = max(0, state.body - injury * .46)
            if key == "player":
                self.frame.primary_loss += injury
        weighted = actual * state.unit.power / self.totals[state.unit.side]
        if state.unit.side == "player":
            self.frame.player_loss += weighted
        else:
            self.frame.enemy_loss += weighted
        if lethal:self._body_death(key)
        return weighted

    def ordinary_damage(self, dealt: float, received: float) -> tuple[float, float]:
        """Allocate contributions before tier gating; mortal allies never inherit tiers.

        Values are fractions of the opposing side's original durability, matching
        the existing six-stat exchange. No new minimum-damage floor is applied.
        """
        amounts: dict[str, float] = {}
        primary_body_before=self.units['player'].body if 'player' in self.units else 0.
        body_amounts: dict[str,float] = {}
        body_hit_weights = {}
        semantic_hits, semantic_caps = [], {}
        attack_targets={}
        # Reserve both sides' attack resources before resolving either side's wards.
        tiers: dict[str, int] = {}
        ordinary_sides = {side: self._has_ordinary(side) for side in ("player", "enemy")}
        attempted={key for key,s in self.units.items() if self._available(key) and ordinary_sides[s.unit.side]}
        for key in self._unit_order():
            state=self.units[key]
            if not self._available(key) or not ordinary_sides[state.unit.side]:
                continue
            tiers[key] = self.attack_tier(state, pay=True)
        # Golden light belongs to the body; an empty energy pool cannot remove it.
        ward_tiers = {key: self.ward_tier(key) for key in self.units}
        for side, damage in (("player", dealt), ("enemy", received)):
            if damage <= 0:
                continue
            opponents = [self.units[key] for key in self._unit_order() if self.units[key].unit.side != side
                         and self.units[key].fighting and key not in self._dominated]
            target_total = sum(s.unit.power for s in opponents)
            if target_total <= 0:
                continue
            for key, tier in tiers.items():
                source = self.units[key]
                if source.unit.side != side:
                    continue
                contribution = damage * source.unit.power / self.totals[side]
                attack_targets[key]=tuple(sorted(s.unit.id for s in opponents))
                for target in opponents:
                    target_key = target.unit.id
                    ward_tier = ward_tiers[target_key]
                    if tier < ward_tier:
                        self._blocked_pairs.add((key, target_key))
                        pair=(key,target_key)
                        self._light_prevented[pair]=self._light_prevented.get(pair,0.)+contribution*self.totals[target.unit.side]/target_total
                        continue
                    amount = contribution * self.totals[target.unit.side] / target_total
                    if self.semantics is not None:
                        event = dict(amount=amount, damage_source='ordinary')
                        outgoing = self._semantic_preview(key, 'ordinary_before_damage', target_key, 'attacker', **event)
                        incoming = self._semantic_preview(target_key, 'ordinary_before_damage', key, 'defender', **event)
                        amount *= outgoing.factor('ordinary.dealt') * incoming.factor('ordinary.received')
                        semantic_caps[target_key] = min(semantic_caps.get(target_key, 1.), incoming.cap('ordinary.received_cap'))
                        self._semantic_commit(outgoing, {'ordinary.dealt'})
                        self._semantic_commit(incoming, {'ordinary.received', 'ordinary.received_cap'})
                    body_amounts[target_key]=body_amounts.get(target_key,0.)+amount
                    body_hit_weights[key,target_key]=amount
                    if tier>=2:amount=self._guard_state(target_key,amount)
                    semantic_hits.append((key,target_key,amount))
                    amounts[target_key] = amounts.get(target_key, 0.0) + amount
        before_p, before_e = self.frame.player_loss, self.frame.enemy_loss
        primary_before = self.units["player"].vitality if "player" in self.units else 0.0
        actual_losses, actual_body_losses = {}, {}
        for key, amount in amounts.items():
            target = self.units[key]
            before = target.vitality
            body_before = target.body
            self._lose(key, min(amount, semantic_caps.get(key, amount)),
                       body_amount=min(body_amounts[key],semantic_caps.get(key,body_amounts[key])))
            actual_losses[key] = before - target.vitality
            actual_body_losses[key] = body_before - target.body
        # Damage is simultaneous. Post-damage facts contain actual, tier-gated
        # losses, attributed proportionally rather than duplicated for allies.
        for source, target, amount in semantic_hits:
            actual = actual_losses[target] * amount / max(1e-12, amounts[target])
            self._semantic_record_loss(source, target, actual, 'ordinary')
        for source, target, amount in semantic_hits:
            actual = actual_losses[target] * amount / max(1e-12, amounts[target])
            body_loss = actual_body_losses[target] * amount / max(1e-12, amounts[target])
            event = dict(damage_source='ordinary', amount=amount, actual_loss=actual, body_loss=body_loss)
            self._semantic_event(source, 'ordinary_after_damage', target, 'attacker', **event)
            self._semantic_event(target, 'ordinary_after_damage', source, 'defender', **event)
        self.primary_ordinary_loss = (primary_before - self.units["player"].vitality
                                      if "player" in self.units else 0.0)
        self.primary_ordinary_body_loss=(actual_body_losses.get('player',0.) if self._body_round.value('player','state_guard') else self.primary_ordinary_loss*.46)
        for source in sorted(attack_targets):
            hits=[(target,actual_losses[target]*amount/max(1e-12,amounts[target]))
                  for s,target,amount in semantic_hits if s==source]
            body_hits={target:actual_body_losses[target]*amount/max(1e-12,body_amounts[target])
                       for (origin,target),amount in body_hit_weights.items() if origin==source}
            self._queue_forget(source,attack_targets[source],dict(hits),())
            self._field_ordinary_hits(source,dict(hits),body_hits)
        self._field_attempted_ordinary(attempted)
        self._drain_body_events()
        self._execute_field_actions(dict(self._dominated))
        self.primary_ordinary_body_loss=(primary_body_before-self.units['player'].body if 'player' in self.units else 0.)
        for source, target in sorted(self._blocked_pairs):
            if self.light_value(target,'kun'):
                amount=self._light_prevented.get((source,target),0.)
                self._light_note('kun',target,f'{self.units[target].unit.name}的{self._body_name(target,"ward")}免疫了{self.units[source].unit.name}的凡属性伤害，拦下预计{amount:.2%}战斗态势损耗（{amount*self.units[target].unit.power:.1f}点）。',source=source,prevented=amount)
            else:self.frame.events.append(f"{self.units[source].unit.name}的作用至道不足，无法撼动{self.units[target].unit.name}的护体金光。")
        return self.frame.enemy_loss - before_e, self.frame.player_loss - before_p

    def mp_ratio(self, side: str, fallback: float) -> float:
        primary='player' if side=='player' else 'enemy-0'
        linked = next((self.units[key] for key in sorted(self.units,key=lambda k:(k!=primary,k)) if self.units[key].unit.side == side
                       and self.units[key].unit.capabilities.resource_link == "legacy_mp"), None)
        return linked.current / max(1.0, linked.unit.capabilities.capacity) if linked else fallback

    def sync_resources(self, *, player_mp: float, enemy_mp: float) -> None:
        self._semantic_mp = {'player': player_mp, 'enemy': enemy_mp}
        for key in self._unit_order():
            state=self.units[key]
            if state.unit.capabilities.resource_link == "legacy_mp":
                ratio = player_mp if state.unit.side == "player" else enemy_mp
                self._energy(state.unit.id,min(state.current,max(0.0,ratio)*state.unit.capabilities.capacity))
            if not state.fighting:
                state.active_voisinage = None
        self._refresh_relations()

    def finish_round(self, *, player_mp: float, enemy_mp: float) -> None:
        self.sync_resources(player_mp=player_mp, enemy_mp=enemy_mp)
        self._semantic_mp = {'player': player_mp, 'enemy': enemy_mp}
        self._semantic_end()
        self._drain_body_events()
        self._execute_field_actions(dict(self._dominated))
        self._finish_field_powers()
        self._refresh_relations()

    def _refresh_relations(self):
        """Release only field-dependent control; damage/pressure remain real."""
        self.fields = [f for f in self.fields if self.units[f.owner].fighting
                       and f.owner not in self._disrupted]
        live = {f.owner for f in self.fields}
        self._expire_field_controls(live=True)
        for key, state in self.units.items():
            state.controls = {kind: owner for kind, owner in state.controls.items()
                              if owner in live and owner not in self._light_muted and key not in self._released}
            owner = self._dominated.get(key)
            if owner not in live or owner in self._light_muted or key in self._released:
                self._dominated.pop(key, None)
                state.escape_locked = False
                if key in self.frame.relations and self.frame.relations[key]['relation'] == 'dominated':
                    self.frame.relations[key] = {**self.frame.relations[key], 'relation': 'uncovered', 'attacker': None}
            else:
                state.escape_locked = not state.escaped
        for relation in self.frame.relations.values():
            if relation.get('protector') not in live:
                relation['protector'] = None
                relation['defense_strength'] = 0

    def ordinary_loss(self, side: str) -> float:
        return 1.0 - sum(self.units[key].unit.power * self.units[key].vitality for key in sorted(self.units)
                         if self.units[key].unit.side == side) / self.totals[side]

    def restore_ordinary(self, side: str, amount: float) -> None:
        """Apply conventional recovery only to survivors, never resurrect a captive."""
        survivors = [s for s in self.units.values() if s.unit.side == side and s.fighting]
        weight = sum(s.unit.power for s in survivors)
        if weight <= 0 or amount <= 0:
            return
        for state in survivors:
            state.vitality = min(1.0, state.vitality + amount * self.totals[side] / weight)

    def revive_primary(self, vitality: float) -> None:
        state = self.units.get("player")
        if state is not None and not state.suppressed and "player" not in self._dominated:
            state.vitality = max(state.vitality, vitality)

    def primary_suppressed(self) -> bool:
        return bool(self.units.get("player") and self.units["player"].suppressed)

    def primary_dead(self) -> bool:
        return bool(self.units.get("player") and self.units["player"].vitality <= 0
                    and not self.units["player"].suppressed and not self.units["player"].escaped)

    def enemy_killed(self) -> bool:
        enemies = [s for s in self.units.values() if s.unit.side == "enemy"]
        return bool(enemies and all(s.vitality <= 0 and not s.suppressed and not s.escaped for s in enemies))

    def enemy_suppressed(self) -> bool:
        enemies = [s for s in self.units.values() if s.unit.side == "enemy"]
        return bool(enemies and all(s.suppressed for s in enemies))

    def verdict(self) -> str | None:
        primary = self.units.get("player")
        if primary and not primary.fighting:
            return "defeat"
        if not any(s.fighting for s in self.units.values()):
            return "stalemate"
        if not any(s.fighting for s in self.units.values() if s.unit.side == "enemy"):
            return "victory"
        if not any(s.fighting for s in self.units.values() if s.unit.side == "player"):
            return "defeat"
        return None

    def report(self) -> dict[str, Any]:
        return {
            **({'body_mechanisms':self._body_round.report()} if self._body_round and any(self._body_round.records.values()) else {}),
            **({'divine_lights':dict(events=list(self._light_trace),silenced_by=dict(self._light_muted),first_side=self.frame.divine_first)} if self._light_trace else {}),
            **({'animation': self.animation} if self.animation and self.animation.get('fields') else {}),
            **({'semantics': self.semantic_report()} if self.semantics is not None else {}),
            "relations": self.frame.relations,
            "release_recovery": {k:s.release_recovery_round for k,s in self.units.items() if self._action_paused(k)},
            "restrictions": {k: list(s.restrictions) for k, s in self.units.items() if s.restrictions},
            **({'field_powers':{k:dict(discipline=s.unit.capabilities.field_discipline.id,
                    level=s.unit.capabilities.field_discipline.level,memory=copy.deepcopy(s.field_memory))
                    for k,s in self.units.items() if s.unit.capabilities.field_discipline},
                'timed_controls':{k:dict(s.timed_controls) for k,s in self.units.items() if s.timed_controls},
                'field_debts':{k:dict(s.field_debts) for k,s in self.units.items() if s.field_debts}}
               if any(s.unit.capabilities.field_discipline for s in self.units.values()) else {}),
            "morale": {k: s.morale for k, s in self.units.items()},
            "pressure": {key: s.pressure for key, s in self.units.items() if s.pressure},
            "stat_factors": self.frame.stat_factors,
            "fields": [{"owner": f.owner, "voisinage_id": f.definition.id,
                        "name": f.definition.name, "effect": f.definition.effect,
                        "effects": [e.kind for e in f.definition.actions()],
                        "stability": round(f.stability, 4), "incursion": round(f.strength, 4),
                        "authority": f.authority, "sustained_rounds": self.units[f.owner].sustained_rounds,
                        "strength": round(f.strength, 4), "protects": list(f.protects),
                        "targets": list(f.targets)} for f in self.fields],
            "resources": {key: round(s.current, 6) for key, s in self.units.items()},
            "seal_progress": {key: round(s.seal_progress, 4) for key, s in self.units.items() if s.seal_progress > 0},
            "participants": {key: {"name": s.unit.name, "side": s.unit.side} for key, s in self.units.items()},
            "ordinary": {"player": self.frame.ordinary_player, "enemy": self.frame.ordinary_enemy},
        }

    def updates(self) -> list[dict[str, Any]]:
        return [{"id": key, "side": s.unit.side, "current": max(0.0, s.current), "vitality": s.vitality,
                 "suppressed": s.suppressed, "escape_locked": s.escape_locked,
                 "escaped": s.escaped, "body": s.body,
                 "resource_link": s.unit.capabilities.resource_link}
                for key, s in self.units.items()]

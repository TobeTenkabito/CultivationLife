"""Deterministic voisinage arbitration with per-unit coverage and resource ledgers.

There is no game-state mutation, RNG, world lookup or cultivation progression
here. Definitions express capabilities, not executable content or callbacks.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .effects import VoisinageEffects
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

    @property
    def restrictions(self):
        return self.controls.keys()

    @property
    def fighting(self) -> bool:
        threshold = 0.0 if self.unit.id == "player" else 0.12
        return self.vitality > threshold and not self.suppressed and not self.escaped


@dataclass(frozen=True)
class Field:
    owner: str
    definition: VoisinageDefinition
    strength: float
    protects: tuple[str, ...]
    targets: tuple[str, ...]
    stability: float = 0
    authority: float | None = None


class VoisinageBattle(VoisinageEffects):
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
        self.frame = PhaseRound(0)
        self._acted: set[str] = set()
        self._dominated: dict[str, str] = {}
        self._blocked_pairs: set[tuple[str, str]] = set()
        self._released: set[str] = set()
        self._disrupted: set[str] = set()
        self.primary_ordinary_loss = 0.0
        self.objectives = {"player": "kill", "enemy": "kill"}
        self.escape_forbidden_sides: frozenset[str] = frozenset()

    def set_objectives(self, player: str, enemy: str) -> None:
        if player not in {'kill', 'capture', 'repel', 'defeat'} or enemy not in {'kill', 'capture', 'repel', 'defeat'}:
            raise ValueError('Unknown battle objective')
        self.objectives = {"player": player, "enemy": enemy}

    @property
    def enabled(self) -> bool:
        return any(s.unit.capabilities.voisinages or s.unit.capabilities.force_tier > 1
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
            features = {row["kind"]: row["value"] for row in definition.features}
            continued = owner.active_voisinage == definition.id
            rounds = owner.sustained_rounds + 1 if continued else 1
            protects = [owner.unit.id]
            if c.stance == "protect" and "support" not in owner.restrictions:
                protects += [key for key in c.protect_ids if key in self.units and key != owner.unit.id
                             and self.units[key].unit.side == owner.unit.side
                             and self.units[key].fighting and "support" not in self.units[key].restrictions and self._can_reach(owner, key)]
            targets = []
            if c.stance == "press":
                preferred = c.target_ids or tuple(self.units)
                targets = [key for key in preferred if key in self.units
                           and self.units[key].unit.side != owner.unit.side
                           and self.units[key].fighting and self._can_reach(owner, key)]
            protects = list(dict.fromkeys(protects))[:definition.max_targets]
            targets = list(dict.fromkeys(targets))[:definition.max_targets]
            opening = definition.opening_cost if owner.active_voisinage != definition.id else 0.0
            # Shrink optional coverage before giving up protection of the caster.
            while True:
                extras = len(protects) - 1 + len(targets)
                upkeep = definition.upkeep_cost * (1 - features.get("frugal", 0) if rounds > 1 else 1)
                cost = opening + upkeep + extras * definition.extra_target_cost
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
            owner.current -= cost + investment
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
            stability *= 1 - features.get("sacrifice", 0)
            owner.active_voisinage = definition.id
            owner.sustained_rounds = rounds
            self.frame.events.append(f"{owner.unit.name}维持【{definition.name}】，仙灵力消耗 {cost + investment:g}。")
            authority = definition.authority
            if authority is not None:
                authority *= 1 + investment / max(1.0, definition.max_investment)
            return Field(owner.unit.id, definition, strength, tuple(protects), tuple(targets), stability, authority)
        if candidates:
            self.frame.events.append(f"{owner.unit.name}仙灵力不足，无法展开或维持仙域。")
        owner.active_voisinage = None
        return None

    def begin_round(self, round_no: int, *, player_condition: float, enemy_condition: float,
                    player_mp: float, enemy_mp: float) -> PhaseRound:
        self.frame = PhaseRound(round_no)
        self._acted.clear()
        self._released.clear()
        self._disrupted.clear()
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
            if state.unit.capabilities.resource_link == "legacy_mp":
                ratio = player_mp if state.unit.side == "player" else enemy_mp
                state.current = min(state.current, max(0.0, ratio) * state.unit.capabilities.capacity)
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
        for state in self.units.values():
            field = self._field(state, state.vitality)
            if field:
                self.fields.append(field)
        for key, state in self.units.items():
            attackers = [f for f in self.fields if key in f.targets]
            defenders = [f for f in self.fields if key in f.protects]
            attack = max(attackers, key=lambda f: (f.strength, f.owner), default=None)
            defense = max(defenders, key=lambda f: (f.stability, f.owner), default=None)
            relation = "uncovered"
            if attack:
                if defense and attack.strength <= defense.stability * self.contest_ratio:
                    relation = "pressed" if attack.strength > defense.stability else "contested"
                else:
                    relation = "dominated"
                    self._dominated[key] = attack.owner
                    state.escape_locked = True
                    self.frame.events.append(f"{self.units[attack.owner].unit.name}封禁{state.unit.name}的神识、身法与退路。")
            self.frame.relations[key] = {
                "relation": relation, "attacker": attack.owner if attack else None,
                "protector": defense.owner if defense else None,
                "attack_strength": round(attack.strength, 4) if attack else 0,
                "defense_strength": round(defense.stability, 4) if defense else 0,
            }
            state.resisted = relation in {"pressed", "contested"}
        # Maintenance pays for dominance itself; it is not contingent on an
        # additional active effect being affordable.
        by_owner = {f.owner: f for f in self.fields}
        for key, owner in self._dominated.items():
            if previous.get(key) != owner:
                continue
            target = self.units[key]
            gap = by_owner[owner].strength / max(1.0, self.frame.relations[key]['defense_strength'])
            erosion = min(.55, .12 + .08 * max(0, gap - self.contest_ratio))
            erosion *= 1 - target.unit.capabilities.body_voisinage_resistance
            target.pressure = min(.85, target.pressure + erosion)
            self._lose(key, min(max(0, target.vitality - .13), erosion), physical=False)
            lost = min(target.morale, erosion * 80)
            target.morale -= lost
            side = target.unit.side
            self.frame.morale_loss[side] = self.frame.morale_loss.get(side, 0) + lost * target.unit.power / self.totals[side]
            self.frame.events.append(f"连续支配侵蚀战意与战斗态势，威能差距 {gap:.2f} 倍。")
        for key, relation in self.frame.relations.items():
            if relation['relation'] in {'pressed', 'dominated'} and self.units[key].active_voisinage:
                self.units[key].field_strain = min(.5, self.units[key].field_strain + .05)
        self._resolve_effects(previous)
        for side in ('player', 'enemy'):
            members = [s for s in self.units.values() if s.unit.side == side]
            # Lingering disruption survives loss of the field, within this battle.
            factor = sum(s.unit.power * (0 if s.unit.id in self._dominated else 1 - s.pressure)
                         for s in members) / self.totals[side]
            self.frame.stat_factors[side] = {'sense': factor, 'mobility': factor}
        self.frame.ordinary_player = self._has_ordinary("player")
        self.frame.ordinary_enemy = self._has_ordinary("enemy")
        self.frame.blocked_actions = {key: tuple(s.restrictions) for key, s in self.units.items() if s.controls}
        return self.frame

    def _available(self, key: str) -> bool:
        return (self.units[key].fighting and key not in self._dominated and key not in self._acted
                and "ordinary" not in self.units[key].restrictions)

    def _has_ordinary(self, side: str) -> bool:
        return (any(self._available(key) and s.unit.side == side for key, s in self.units.items())
                and any(s.fighting and s.unit.side != side and key not in self._dominated
                        for key, s in self.units.items()))

    def _lose(self, key: str, amount: float, *, physical=True) -> float:
        state = self.units[key]
        actual = min(state.vitality, max(0.0, amount))
        state.vitality -= actual
        if physical:
            state.body = max(0, state.body - actual * .46)
            if key == "player":
                self.frame.primary_loss += actual
        weighted = actual * state.unit.power / self.totals[state.unit.side]
        if state.unit.side == "player":
            self.frame.player_loss += weighted
        else:
            self.frame.enemy_loss += weighted
        return weighted

    def ordinary_damage(self, dealt: float, received: float) -> tuple[float, float]:
        """Allocate contributions before tier gating; mortal allies never inherit tiers.

        Values are fractions of the opposing side's original durability, matching
        the existing six-stat exchange. No new minimum-damage floor is applied.
        """
        amounts: dict[str, float] = {}
        # Reserve both sides' attack resources before resolving either side's wards.
        tiers: dict[str, int] = {}
        ordinary_sides = {side: self._has_ordinary(side) for side in ("player", "enemy")}
        for key, state in self.units.items():
            if not self._available(key) or not ordinary_sides[state.unit.side]:
                continue
            tiers[key] = self.attack_tier(state, pay=True)
        # Golden light belongs to the body; an empty energy pool cannot remove it.
        ward_tiers = {key: s.unit.capabilities.ward_tier for key, s in self.units.items()}
        for side, damage in (("player", dealt), ("enemy", received)):
            opponents = [s for key, s in self.units.items() if s.unit.side != side
                         and s.fighting and key not in self._dominated]
            target_total = sum(s.unit.power for s in opponents)
            if target_total <= 0:
                continue
            for key, tier in tiers.items():
                source = self.units[key]
                if source.unit.side != side:
                    continue
                contribution = damage * source.unit.power / self.totals[side]
                for target in opponents:
                    target_key = target.unit.id
                    ward_tier = ward_tiers[target_key]
                    if tier < ward_tier:
                        self._blocked_pairs.add((key, target_key))
                        continue
                    amount = contribution * self.totals[target.unit.side] / target_total
                    amounts[target_key] = amounts.get(target_key, 0.0) + amount
        before_p, before_e = self.frame.player_loss, self.frame.enemy_loss
        primary_before = self.units["player"].vitality if "player" in self.units else 0.0
        for key, amount in amounts.items():
            target = self.units[key]
            self._lose(key, amount)
        self.primary_ordinary_loss = (primary_before - self.units["player"].vitality
                                      if "player" in self.units else 0.0)
        for source, target in sorted(self._blocked_pairs):
            self.frame.events.append(f"{self.units[source].unit.name}的作用至道不足，无法撼动{self.units[target].unit.name}的护体金光。")
        return self.frame.enemy_loss - before_e, self.frame.player_loss - before_p

    def mp_ratio(self, side: str, fallback: float) -> float:
        linked = next((s for s in self.units.values() if s.unit.side == side
                       and s.unit.capabilities.resource_link == "legacy_mp"), None)
        return linked.current / max(1.0, linked.unit.capabilities.capacity) if linked else fallback

    def finish_round(self, *, player_mp: float, enemy_mp: float) -> None:
        for state in self.units.values():
            if state.unit.capabilities.resource_link == "legacy_mp":
                ratio = player_mp if state.unit.side == "player" else enemy_mp
                state.current = min(state.current, max(0.0, ratio) * state.unit.capabilities.capacity)
            if not state.fighting:
                state.active_voisinage = None
        self._refresh_relations()

    def _refresh_relations(self):
        """Release only field-dependent control; damage/pressure remain real."""
        self.fields = [f for f in self.fields if self.units[f.owner].fighting
                       and f.owner not in self._disrupted]
        live = {f.owner for f in self.fields}
        for key, state in self.units.items():
            state.controls = {kind: owner for kind, owner in state.controls.items()
                              if owner in live and key not in self._released}
            owner = self._dominated.get(key)
            if owner not in live or key in self._released:
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
        return 1.0 - sum(s.unit.power * s.vitality for s in self.units.values()
                         if s.unit.side == side) / self.totals[side]

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
            "relations": self.frame.relations,
            "restrictions": {k: list(s.restrictions) for k, s in self.units.items() if s.controls},
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

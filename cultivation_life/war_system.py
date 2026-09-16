from __future__ import annotations

import copy
import random
import uuid
from typing import Any

from .content_registry import ITEM_CATALOG, MARKET_GOODS, RACE_DEFINITIONS, REALMS, WORLD_SYSTEMS
from .formation_system import formation_config
from .models import GameState, HistoryRecord, SectNpc
from .npc_system import npc_team_combat_power
from .rules import add_item, remove_item
from .runtime import decode_rng, encode_rng, now_iso
from .world_state import RELATION_LABELS, race_pair


WAR_TERM_DEFS = {
    "execute": ("处死指定修士", 30),
    "alliance": ("确立同盟", 18),
    "vassal": ("迫使对方依附", 55),
    "change_relation": ("迫使对方改变外交关系", 25),
    "stones": ("上供大量灵石", 20),
    "supplies": ("缴纳丹药与装备", 25),
    "dissolve": ("解散对方势力", 70),
    "annex": ("合并对方势力", 90),
    "white_peace": ("无条件和平", 0),
}


class WarSystemMixin:
    """行动单位制战争。年度模拟不遍历战争，避免后期按数百年放大成本。"""

    @staticmethod
    def _war_rules() -> dict[str, Any]:
        return WORLD_SYSTEMS.get("war_system", {})

    def _war_relation(self, game: GameState, kind: str, first: str, second: str) -> dict[str, Any]:
        relations = game.race_relations if kind == "race" else game.sect_relations
        return relations.setdefault(race_pair(first, second), {
            "affinity": 0.0, "status": "neutral", "since_age": game.player.age,
        })

    def _active_war(self, game: GameState, kind: str, first: str, second: str) -> dict[str, Any] | None:
        sides = {first, second}
        for war in game.wars:
            if war.get("status") not in {"active", "peace_ready"} or war.get("kind") != kind:
                continue
            self._ensure_war_shape(game, war)
            participants = {row["id"] for side in ("attacker", "defender") for row in war["coalitions"][side]}
            if sides.issubset(participants):
                return war
        return None

    def _war_world(self, game: GameState, kind: str, side_id: str) -> str:
        if kind == "sect" and side_id in game.sects:
            return game.sects[side_id].world
        worlds = list(RACE_DEFINITIONS.get(side_id, {}).get("worlds", []))
        if game.player.world in worlds:
            return game.player.world
        return next((world for world in worlds if world in {"spirit", "true_demon"}), game.player.world)

    def _war_side_name(self, game: GameState, kind: str, side_id: str) -> str:
        if kind == "race":
            return str(RACE_DEFINITIONS.get(side_id, {}).get("name") or side_id or "未知势力")
        sect = game.sects.get(side_id)
        return str(sect.name if sect and sect.name else side_id or "未知势力")

    def _war_side_members(self, game: GameState, kind: str, side_id: str, world: str) -> list[SectNpc]:
        if kind == "sect":
            sect = game.sects.get(side_id)
            people = self._sect_members(game, sect) if sect and not sect.extinct else []
        else:
            people = [npc for npc in self._all_world_npcs(game) if npc.race == side_id]
        # 战场只记录最强二十四人；这是可解释的参战名册，也是稳定的性能上限。
        unique = {
            npc.id: npc for npc in people
            if npc.alive and npc.world == world and not self._intrigue_is_imprisoned(game, npc.id)
        }
        return sorted(unique.values(), key=self._npc_power, reverse=True)[:int(self._war_rules().get("roster_cap", 24))]

    def _ensure_war_shape(self, game: GameState, war: dict[str, Any]) -> bool:
        """Lazily migrate pre-coalition wars without invalidating existing saves."""
        changed = False
        raw_coalitions = war.get("coalitions") if isinstance(war.get("coalitions"), dict) else {}
        coalitions: dict[str, list[dict[str, Any]]] = {}
        for side in ("attacker", "defender"):
            leader = str(war.get(f"{side}_id", ""))
            normalized: list[dict[str, Any]] = []
            seen: set[str] = set()
            raw_rows = raw_coalitions.get(side, []) if isinstance(raw_coalitions.get(side, []), list) else []
            for raw in raw_rows:
                row = {"id": raw} if isinstance(raw, str) else dict(raw) if isinstance(raw, dict) else {}
                power_id = str(row.get("id") or "")
                if not power_id or power_id in seen:
                    changed = True
                    continue
                seen.add(power_id)
                normalized.append({
                    "id": power_id, "role": "leader" if power_id == leader else "ally",
                    "joined_unit": int(row.get("joined_unit", war.get("start_unit", 0))),
                    "called_by": row.get("called_by"),
                })
            if leader and leader not in seen:
                normalized.insert(0, {"id": leader, "role": "leader", "joined_unit": int(war.get("start_unit", 0)), "called_by": None})
                changed = True
            normalized.sort(key=lambda row: (row["role"] != "leader", row["joined_unit"], row["id"]))
            coalitions[side] = normalized
        if coalitions != raw_coalitions:
            war["coalitions"] = coalitions
            changed = True
        if not isinstance(war.get("roster_owner"), dict):
            war["roster_owner"] = {}
            changed = True
        roster_owner = war["roster_owner"]
        for side in ("attacker", "defender"):
            leader = war.get(f"{side}_id", "")
            for npc_id in war.get("roster", {}).get(side, []):
                if npc_id not in roster_owner:
                    roster_owner[npc_id] = leader
                    changed = True
        for key, default, expected_type in (
            ("called_allies", {}, dict), ("call_log", [], list), ("peace_offer", None, (dict, type(None))),
        ):
            if key not in war or not isinstance(war.get(key), expected_type):
                war[key] = copy.deepcopy(default)
                changed = True
        return changed

    def _coalition_ids(self, war: dict[str, Any], side: str) -> list[str]:
        return [str(row.get("id", "")) for row in war.get("coalitions", {}).get(side, []) if row.get("id")]

    def _participant_side(self, war: dict[str, Any], power_id: str | None) -> str | None:
        if not power_id:
            return None
        for side in ("attacker", "defender"):
            if power_id in self._coalition_ids(war, side):
                return side
        return None

    def _power_exists_in_world(self, game: GameState, kind: str, power_id: str, world: str) -> bool:
        if kind == "sect":
            sect = game.sects.get(power_id)
            return bool(sect and not sect.extinct and sect.world == world)
        return world in RACE_DEFINITIONS.get(power_id, {}).get("worlds", [])

    def _allied_powers(self, game: GameState, war: dict[str, Any], side: str) -> list[dict[str, Any]]:
        relations = game.race_relations if war["kind"] == "race" else game.sect_relations
        own = set(self._coalition_ids(war, side))
        enemy = set(self._coalition_ids(war, "defender" if side == "attacker" else "attacker"))
        candidates: dict[str, dict[str, Any]] = {}
        for caller in own:
            for key, relation in relations.items():
                if relation.get("status") not in {"alliance", "vassal"}:
                    continue
                first, second = key.split("|") if "|" in key else key.split(":")
                if caller not in {first, second}:
                    continue
                candidate = second if caller == first else first
                if candidate in own or candidate in enemy or not self._power_exists_in_world(game, war["kind"], candidate, war["world"]):
                    continue
                base = float(self._war_rules().get("ally_call_base_chance", 0.68))
                chance = base + max(-0.18, min(0.18, float(relation.get("affinity", 0)) / 400.0))
                own_power = self._war_total_power(game, war, side)
                enemy_power = self._war_total_power(game, war, "defender" if side == "attacker" else "attacker")
                if side == "defender":
                    chance += 0.06
                if enemy_power > own_power * 1.5:
                    chance -= 0.12
                elif own_power > enemy_power * 1.35:
                    chance += 0.05
                if relation.get("status") == "vassal":
                    chance += 0.25 if relation.get("overlord") == caller else 0.08
                candidates[candidate] = {"id": candidate, "caller_id": caller, "chance": max(0.10, min(0.98, chance))}
        return list(candidates.values())

    def _add_war_participant(self, game: GameState, war: dict[str, Any], side: str, power_id: str, caller_id: str) -> None:
        war["coalitions"][side].append({"id": power_id, "role": "ally", "joined_unit": game.diplomacy_unit, "called_by": caller_id})
        side_roster = war["roster"][side]
        total_cap = int(self._war_rules().get("coalition_roster_cap", 48))
        ally_cap = int(self._war_rules().get("ally_roster_cap", 12))
        for npc in self._war_side_members(game, war["kind"], power_id, war["world"])[:ally_cap]:
            if len(side_roster) >= total_cap:
                break
            if npc.id not in side_roster:
                side_roster.append(npc.id)
                war["roster_owner"][npc.id] = power_id

    def _call_war_allies(self, game: GameState, war: dict[str, Any], side: str, rng: random.Random,
                         *, ally_id: str = "", limit: int | None = None) -> list[str]:
        self._ensure_war_shape(game, war)
        outcomes: list[str] = []
        cooldown = int(self._war_rules().get("ally_call_cooldown_units", 3))
        for row in self._allied_powers(game, war, side):
            if ally_id and row["id"] != ally_id:
                continue
            call_key = f"{side}:{row['id']}"
            prior = war["called_allies"].get(call_key)
            if prior and (prior.get("accepted") or game.diplomacy_unit - int(prior.get("unit", 0)) < cooldown):
                continue
            accepted = rng.random() < row["chance"]
            result = {
                "id": row["id"], "caller_id": row["caller_id"], "side": side, "accepted": accepted,
                "unit": game.diplomacy_unit, "chance": round(row["chance"], 3),
            }
            war["called_allies"][call_key] = result
            war["call_log"].append(result)
            caller_name = self._war_side_name(game, war["kind"], row["caller_id"])
            ally_name = self._war_side_name(game, war["kind"], row["id"])
            if accepted:
                self._add_war_participant(game, war, side, row["id"], row["caller_id"])
                text = f"{ally_name}接受{caller_name}的召集，加入{('进攻' if side == 'attacker' else '防御')}阵营。"
            else:
                text = f"{ally_name}拒绝了{caller_name}的参战请求。"
            outcomes.append(text)
            self._append_war_log(game, war, "召集盟友", text)
            if limit is not None and len(outcomes) >= limit:
                break
        war["call_log"] = war["call_log"][-40:]
        return outcomes

    def _player_war_side(self, game: GameState, war: dict[str, Any]) -> str | None:
        if game.player.world != war.get("world"):
            return None
        self._ensure_war_shape(game, war)
        own_id = game.player.faction_id if war["kind"] == "sect" else self._player_allegiance_race(game.player)
        return self._participant_side(war, own_id) or self._intrigue_player_guest_side(game, war)

    def _player_has_war_voice(self, game: GameState, war: dict[str, Any]) -> bool:
        side = self._player_war_side(game, war)
        if not side:
            return False
        own_id = game.player.faction_id if war["kind"] == "sect" else self._player_allegiance_race(game.player)
        if own_id != war.get(f"{side}_id"):
            return False
        return self._has_race_voice(game) if war["kind"] == "race" else self._has_sect_voice(game)

    def _start_war(self, game: GameState, kind: str, attacker: str, defender: str) -> dict[str, Any]:
        current = self._active_war(game, kind, attacker, defender)
        if current:
            return current
        relation = self._war_relation(game, kind, attacker, defender)
        truce_until = max(int(relation.get("truce_until_unit", 0)), int(relation.get("war_truce_until_unit", 0)))
        if game.diplomacy_unit < truce_until:
            raise ValueError(f"系统停战期尚余 {truce_until - game.diplomacy_unit} 个行动单位，不能宣战")
        world = self._war_world(game, kind, attacker)
        attacker_roster = [npc.id for npc in self._war_side_members(game, kind, attacker, world)]
        defender_roster = [npc.id for npc in self._war_side_members(game, kind, defender, world)]
        # DLC guest elders / family retainers / race guests are defensive
        # guarantees.  They enter the defending roster, never the attacker's
        # compulsory levy.
        defensive_guests = self._intrigue_defensive_guest_ids(game, kind, defender, world)
        attacker_roster = [npc_id for npc_id in attacker_roster if npc_id not in defensive_guests]
        defender_roster.extend(npc_id for npc_id in defensive_guests if npc_id not in defender_roster)
        war = {
            "id": f"war_{uuid.uuid4().hex[:12]}", "kind": kind, "world": world,
            "attacker_id": attacker, "defender_id": defender, "status": "active",
            "start_age": game.player.age, "start_unit": game.diplomacy_unit,
            "morale": {"attacker": 100.0, "defender": 100.0},
            "exhaustion": {"attacker": 0.0, "defender": 0.0},
            "war_score": 0.0, "battles": 0, "abstract_rounds": 0,
            "preliminary_resolved": False,
            "roster": {"attacker": attacker_roster, "defender": defender_roster},
            "roster_owner": {**{npc_id: attacker for npc_id in attacker_roster}, **{npc_id: defender for npc_id in defender_roster}},
            "coalitions": {
                "attacker": [{"id": attacker, "role": "leader", "joined_unit": game.diplomacy_unit, "called_by": None}],
                "defender": [{"id": defender, "role": "leader", "joined_unit": game.diplomacy_unit, "called_by": None}],
            },
            "called_allies": {}, "call_log": [], "peace_offer": None,
            "escaped": {"attacker": [], "defender": []}, "logs": [],
        }
        war["player_side"] = self._player_war_side(game, war)
        war["controller"] = "player" if self._player_has_war_voice(game, war) else "ai"
        game.wars.append(war)
        self._append_war_log(game, war, "宣战", f"{self._war_side_name(game, kind, attacker)}向{self._war_side_name(game, kind, defender)}正式宣战。")
        game.history.append(HistoryRecord(
            "SYS_WAR_DECLARED", 1, game.player.age, "势力宣战", war["id"], "war_started",
            war["logs"][-1]["text"], {"war_id": war["id"], "kind": kind, "sides": [attacker, defender]},
            ["system", "war", "diplomacy", "world_news", f"world:{world}"],
        ))
        return war

    def _ensure_wars(self, game: GameState) -> bool:
        """Upgrade old saves whose diplomatic relation was already marked as war."""
        before = len(game.wars)
        changed = False
        for war in game.wars:
            changed = self._ensure_war_shape(game, war) or changed
        for kind, relations in (("race", game.race_relations), ("sect", game.sect_relations)):
            for key, relation in relations.items():
                if relation.get("status") != "war":
                    continue
                first, second = key.split("|") if "|" in key else key.split(":")
                if not self._active_war(game, kind, first, second):
                    self._start_war(game, kind, first, second)
        return changed or len(game.wars) != before

    def _append_war_log(self, game: GameState, war: dict[str, Any], title: str, text: str) -> None:
        war.setdefault("logs", []).append({"unit": game.diplomacy_unit, "age": game.player.age, "title": title, "text": text})
        # 单场战争仅保留最近八十条，避免长期战争令存档和渲染无限膨胀。
        war["logs"] = war["logs"][-80:]

    def _war_npc(self, game: GameState, npc_id: str) -> SectNpc | None:
        return self._find_npc(game, npc_id)

    def _available_warriors(self, game: GameState, war: dict[str, Any], side: str, power_id: str = "") -> list[SectNpc]:
        self._ensure_war_shape(game, war)
        escaped = set(war.get("escaped", {}).get(side, []))
        return [npc for npc_id in war.get("roster", {}).get(side, [])
                if npc_id not in escaped and (not power_id or war["roster_owner"].get(npc_id) == power_id)
                and (npc := self._war_npc(game, npc_id)) and npc.alive
                and not self._intrigue_is_imprisoned(game, npc.id)]

    def _war_total_power(
        self, game: GameState, war: dict[str, Any], side: str, *, include_player: bool = True,
    ) -> float:
        members = self._available_warriors(game, war, side)
        powers = [
            self._npc_power(npc) * self._npc_formation_power_multiplier(game, npc.id)
            for npc in members
        ]
        own_id = game.player.faction_id if war["kind"] == "sect" else self._player_allegiance_race(game.player)
        if (
            include_player and game.player.alive and game.player.world == war.get("world")
            and own_id in self._coalition_ids(war, side)
        ):
            powers.append(self._player_intrinsic_combat_power(game.player))
        guard_power = 0.0
        if side == "defender" and war.get("kind") == "sect":
            for sect_id in self._coalition_ids(war, side):
                guard_power += self._sect_guard_power(game, sect_id)
        # Guard arrays are anchored battlefield infrastructure, not a fourth
        # cultivator competing for one of the aggregate roster's three slots.
        power = (npc_team_combat_power(powers) if powers else 0.0) + guard_power
        if side == "defender":
            power *= 1 + float(self._war_rules().get("defender_power_bonus", 0.10))
        return power

    @staticmethod
    def _war_formation_metric_score(profile: dict[str, Any], side: str) -> float:
        metrics = {
            key: max(0.0, min(1.0, float(value) / 100.0))
            for key, value in profile.get("metrics", {}).items()
        }
        weights = (
            {"kill": .34, "focus": .20, "change": .18, "cycle": .14, "balance": .08, "growth": .06}
            if side == "attacker"
            else {"growth": .28, "balance": .26, "cycle": .16, "focus": .12, "change": .10, "kill": .08}
        )
        return sum(metrics.get(key, 0.0) * weight for key, weight in weights.items())

    def _war_side_formation(self, game: GameState, war: dict[str, Any], side: str) -> dict[str, Any]:
        """Pick one command array for the side; formations never stack by headcount."""
        candidates: list[dict[str, Any]] = []
        for npc in self._available_warriors(game, war, side):
            entry = game.npc_formations.get(npc.id, {})
            profile = self._npc_formation_profile(game, npc.id)
            if profile.get("active") and float(entry.get("durability", 0.0)) > 0:
                candidates.append({
                    "profile": profile, "name": profile.get("name", "九宫阵"),
                    "owner_name": npc.name, "source_kind": "npc", "source_id": npc.id,
                    "integrity": max(0.0, min(1.0, float(entry.get("durability", 0.0)) / 100.0)),
                })
        if side == "defender" and war.get("kind") == "sect":
            for sect_id in self._coalition_ids(war, side):
                array = self._sect_guard_array(game, sect_id)
                if not array:
                    continue
                profile = self._ground_profile(game.player, array)
                if profile.get("active"):
                    candidates.append({
                        "profile": profile, "name": profile.get("name", "护山阵"),
                        "owner_name": self._war_side_name(game, war["kind"], sect_id),
                        "source_kind": "sect_guard", "source_id": str(array.get("id", "")),
                        "integrity": max(0.0, min(1.0, float(array.get("durability", 0.0)) / 100.0)),
                    })
        if not candidates:
            return {
                "active": False, "name": "无阵", "owner_name": "", "source_kind": "none",
                "source_id": "", "integrity": 0.0, "modifier": 1.0, "conditions": [],
                "stability": "未成阵", "core_nature": "", "metrics": {}, "profile": {},
            }

        def command_score(row: dict[str, Any]) -> float:
            profile = row["profile"]
            static = sum(
                max(0.0, float(value) - 1.0)
                for value in profile.get("static_player_multipliers", {}).values()
            ) / 6.0
            return row["integrity"] * (
                self._war_formation_metric_score(profile, side) + min(.14, static)
            )

        selected = max(candidates, key=command_score)
        profile = selected["profile"]
        selected.update({
            "active": True,
            "conditions": [
                str(value) for value in profile.get("artificial_conditions", []) if str(value) != "大阵"
            ],
            "stability": str(profile.get("stability", "低")),
            "core_nature": str((profile.get("core_node") or {}).get("nature", "")),
            "metrics": copy.deepcopy(profile.get("metrics", {})),
        })
        return selected

    def _war_formation_modifier(
        self, own: dict[str, Any], opponent: dict[str, Any], side: str,
    ) -> float:
        if not own.get("active"):
            return 1.0
        profile = own["profile"]
        rules = self._war_rules()
        metric_score = self._war_formation_metric_score(profile, side)
        static_score = min(1.0, sum(
            max(0.0, float(value) - 1.0)
            for value in profile.get("static_player_multipliers", {}).values()
        ) / (6.0 * .14))
        round_rules = profile.get("round_rules", {})
        rule_score = min(1.0, (
            float(round_rules.get("dealt_bonus", 0.0)) / .025
            + float(round_rules.get("enemy_morale_loss", 0.0)) / 2.4
            + float(round_rules.get("player_morale_loss_reduction", 0.0)) / .20
        ) / 3.0)
        integrity = max(0.0, min(1.0, float(own.get("integrity", 0.0))))
        bonus = integrity * (
            float(rules.get("formation_metric_weight", .075)) * metric_score
            + float(rules.get("formation_static_weight", .025)) * static_score
            + float(rules.get("formation_round_rule_weight", .015)) * rule_score
            + float(rules.get("formation_condition_weight", .010)) * len(own.get("conditions", []))
        )
        stability = own.get("stability")
        bonus += integrity * ({"高": .008, "中": .004, "低": 0.0}.get(stability, 0.0))
        if opponent.get("active") and own.get("core_nature") and opponent.get("core_nature"):
            relation = float(
                formation_config().get("relations", {})
                .get(own["core_nature"], {})
                .get(opponent["core_nature"], 0.0)
            )
            bonus += (
                float(rules.get("formation_relation_weight", .015))
                * relation * integrity * float(opponent.get("integrity", 0.0))
            )
        cap = max(0.0, float(rules.get("formation_war_bonus_cap", .12)))
        return round(1.0 + max(-cap, min(cap, bonus)), 6)

    def _war_formation_contexts(self, game: GameState, war: dict[str, Any]) -> dict[str, dict[str, Any]]:
        contexts = {
            side: self._war_side_formation(game, war, side) for side in ("attacker", "defender")
        }
        contexts["attacker"]["modifier"] = self._war_formation_modifier(
            contexts["attacker"], contexts["defender"], "attacker",
        )
        contexts["defender"]["modifier"] = self._war_formation_modifier(
            contexts["defender"], contexts["attacker"], "defender",
        )
        return contexts

    @staticmethod
    def _war_formation_text(contexts: dict[str, dict[str, Any]]) -> str:
        labels = {"attacker": "攻方", "defender": "守方"}
        details = []
        for side in ("attacker", "defender"):
            row = contexts[side]
            if not row.get("active"):
                details.append(f"{labels[side]}无统御阵势")
                continue
            conditions = f"，条件：{'、'.join(row['conditions'])}" if row.get("conditions") else ""
            details.append(
                f"{labels[side]}“{row['name']}”完整度 {float(row['integrity']):.0%}，"
                f"战役修正 {(float(row['modifier']) - 1.0):+.1%}{conditions}"
            )
        return "阵势权重：" + "；".join(details) + "。"

    def _war_power_profile(
        self, game: GameState, war: dict[str, Any], side: str, *, include_player: bool = True,
    ) -> dict[str, float | int]:
        members = self._available_warriors(game, war, side)
        total = self._war_total_power(game, war, side, include_player=include_player)
        elite_rows = [(
            npc.realm_index,
            self._npc_power(npc) * self._npc_formation_power_multiplier(game, npc.id),
        ) for npc in members]
        own_id = game.player.faction_id if war["kind"] == "sect" else self._player_allegiance_race(game.player)
        if (
            include_player and game.player.alive and game.player.world == war.get("world")
            and own_id in self._coalition_ids(war, side)
        ):
            elite_rows.append((game.player.realm_index, self._player_intrinsic_combat_power(game.player)))
        elites = sorted(elite_rows, reverse=True)[:3]
        elite = npc_team_combat_power(power for _, power in elites) if elites else 0.0
        if side == "defender":
            elite *= 1 + float(self._war_rules().get("defender_power_bonus", 0.10))
        total_weight = float(self._war_rules().get("ai_total_power_weight", 0.68))
        composite = total * total_weight + elite * (1 - total_weight)
        return {
            "total": round(total, 1), "elite": round(elite, 1), "composite": round(composite, 1),
            "highest_realm": max((realm_index for realm_index, _ in elite_rows), default=0), "members": len(elite_rows),
        }

    def _war_entity_power(self, game: GameState, war: dict[str, Any], side: str, power_id: str) -> float:
        powers = [
            self._npc_power(npc) * self._npc_formation_power_multiplier(game, npc.id)
            for npc in self._available_warriors(game, war, side, power_id)
        ]
        own_id = game.player.faction_id if war["kind"] == "sect" else self._player_allegiance_race(game.player)
        if game.player.alive and game.player.world == war.get("world") and own_id == power_id:
            powers.append(self._player_intrinsic_combat_power(game.player))
        guard_power = (
            self._sect_guard_power(game, power_id)
            if side == "defender" and war.get("kind") == "sect" else 0.0
        )
        return (npc_team_combat_power(powers) if powers else 0.0) + guard_power

    def _resolve_abstract_defeat(self, game: GameState, war: dict[str, Any], loser: str, rng: random.Random) -> str:
        candidates = self._available_warriors(game, war, loser)
        if not candidates or rng.random() >= float(self._war_rules().get("ai_casualty_roll_chance", 0.34)):
            return ""
        weights = [max(0.25, (len(REALMS) - npc.realm_index) ** 1.15) for npc in candidates]
        target = rng.choices(candidates, weights=weights, k=1)[0]
        death_chance, escape_chance = self._war_defeat_probabilities(target.realm_index)
        roll = rng.random()
        if roll < death_chance:
            target.alive = False
            target.death_reason = "势力征伐中阵亡"
            return f"{target.name}在溃阵中陨落。"
        winner_side = "defender" if loser == "attacker" else "attacker"
        victors = self._available_warriors(game, war, winner_side)
        victor = max(victors, key=self._npc_power, default=None)
        transfer = (
            self._maybe_transfer_player_dependency(game, target, victor, rng, context="war_defeat")
            if victor else ""
        )
        if roll < death_chance + escape_chance:
            war.setdefault("escaped", {}).setdefault(loser, []).append(target.id)
            return f"{target.name}败退后脱离战场。" + (f" {transfer}" if transfer else "")
        target.wounds = min(4, target.wounds + 2)
        return f"{target.name}在败退中遭到重创。" + (f" {transfer}" if transfer else "")

    @staticmethod
    def _war_defeat_probabilities(realm_index: int) -> tuple[float, float]:
        highness = max(0.0, min(1.0, realm_index / max(1, len(REALMS) - 1)))
        return max(0.04, 0.34 - highness * 0.28), min(0.82, 0.30 + highness * 0.48)

    def _shift_war_morale(self, war: dict[str, Any], loser: str, loss: float, gain: float, *, attacker_kill: bool = False) -> None:
        winner = "defender" if loser == "attacker" else "attacker"
        if winner == "attacker" and attacker_kill:
            gain *= 1 + float(self._war_rules().get("attacker_morale_shock_bonus", 0.10))
        war["morale"][loser] = max(0.0, float(war["morale"][loser]) - loss)
        war["morale"][winner] = min(150.0, float(war["morale"][winner]) + gain)
        signed = loss + gain
        war["war_score"] = max(-100.0, min(100.0, float(war["war_score"]) + (signed if winner == "attacker" else -signed)))

    def _resolve_field_attack(
        self, game: GameState, war: dict[str, Any], attacking: str, rng: random.Random,
        formation_contexts: dict[str, dict[str, Any]] | None = None,
    ) -> str:
        defending = "defender" if attacking == "attacker" else "attacker"
        attackers = self._available_warriors(game, war, attacking)
        defenders = self._available_warriors(game, war, defending)
        if not attackers or not defenders:
            war["morale"][defending if not defenders else attacking] = 0.0
            return "一方已经无可出阵之人。"
        striker = rng.choice(attackers[:min(8, len(attackers))])
        target = rng.choice(defenders[:min(12, len(defenders))])
        defense_bonus = 1 + float(self._war_rules().get("defender_power_bonus", 0.10))
        attack_power = self._npc_power(striker) * self._npc_formation_power_multiplier(game, striker.id)
        defend_power = self._npc_power(target) * self._npc_formation_power_multiplier(game, target.id)
        attack_power *= defense_bonus if attacking == "defender" else 1.0
        defend_power *= defense_bonus if defending == "defender" else 1.0
        contexts = formation_contexts or self._war_formation_contexts(game, war)
        attack_power *= float(contexts[attacking].get("modifier", 1.0))
        defend_power *= float(contexts[defending].get("modifier", 1.0))
        ratio = attack_power * rng.uniform(0.85, 1.18) / max(1.0, defend_power)
        if ratio < 1:
            return f"{striker.name}攻势受阻，{target.name}守住阵线。"
        highness = target.realm_index / max(1, len(REALMS) - 1)
        threshold = max(1.25, REALMS[target.realm_index].kill_threshold * (0.50 + highness * 0.20))
        kill_chance = min(0.90, 0.64 + (ratio - threshold) * 0.15) * (1 - highness * 0.58)
        if ratio >= threshold and rng.random() < kill_chance:
            target.alive = False
            target.death_reason = "势力征伐中阵亡"
            self._shift_war_morale(war, defending, 19.0, 5.0, attacker_kill=True)
            return f"{striker.name}击杀{target.name}；战场杀机令击杀门槛显著降低。"
        if ratio >= 1.35 and rng.random() < max(0.28, 0.68 - highness * 0.34):
            target.wounds = min(4, target.wounds + 2)
            self._shift_war_morale(war, defending, 9.0, 2.0)
            transfer = self._maybe_transfer_player_dependency(
                game, target, striker, rng, context="war_field",
            )
            return f"{striker.name}重创{target.name}，后者被迫退入后阵。" + (f" {transfer}" if transfer else "")
        war.setdefault("escaped", {}).setdefault(defending, []).append(target.id)
        self._shift_war_morale(war, defending, 12.0, 3.0)
        transfer = self._maybe_transfer_player_dependency(
            game, target, striker, rng, context="war_field",
        )
        return f"{target.name}不敌{striker.name}，脱离战场逃遁。" + (f" {transfer}" if transfer else "")

    def _resolve_player_war_round(
        self, game: GameState, war: dict[str, Any], side: str, rng: random.Random,
    ) -> None:
        enemy = "defender" if side == "attacker" else "attacker"
        candidates = self._available_warriors(game, war, enemy)
        if not candidates:
            war["morale"][enemy] = 0.0
            self._finish_war_by_morale(game, war)
            return
        if not war.get("preliminary_resolved"):
            war["preliminary_resolved"] = True
            war["vanguard_skipped"] = True
            self._append_war_log(
                game, war, "转入主力会战",
                "你越过单独先锋战，选择直接在本轮主力会战中亲自出阵。",
            )
        contexts = self._war_formation_contexts(game, war)
        pool = candidates[:min(12, len(candidates))]
        team_size = min(len(pool), rng.randint(1, 3))
        opponents = rng.sample(pool, team_size)
        formation_owner = str(contexts[enemy].get("source_id", ""))
        if formation_owner and contexts[enemy].get("source_kind") == "npc":
            bearer = next((npc for npc in pool if npc.id == formation_owner), None)
            if bearer and bearer not in opponents:
                opponents[-1] = bearer
        required = npc_team_combat_power(self._npc_power(npc) for npc in opponents)
        if enemy == "defender":
            required *= 1 + float(self._war_rules().get("defender_power_bonus", 0.10))
        members = [{
            "name": npc.name, "power": self._npc_power(npc),
            "realm_index": npc.realm_index, "layer": npc.layer, "npc_id": npc.id,
            "faction_id": self._npc_faction_id(game, npc.id), "path": npc.path, "race": npc.race,
        } for npc in opponents]
        target = {
            "target_name": f"{self._war_side_name(game, war['kind'], war[f'{enemy}_id'])}会战队",
            "target_power": max(1.0, required),
            "target_realm_index": max((npc.realm_index for npc in opponents), default=game.player.realm_index),
            "target_layer": max((npc.layer for npc in opponents), default=1),
            "combat_type": "cultivator", "members": members, "action": "repel",
            "enemy_objective": "repel", "max_rounds": 8,
        }
        # A portable/player-local formation still takes precedence inside the
        # detailed resolver. Without one, the side's command array supports the
        # player so that both armies retain their formation identity.
        if contexts[side].get("active"):
            target["allied_formation_profile"] = copy.deepcopy(contexts[side]["profile"])
            target["formation_initial_integrity"] = float(contexts[side]["integrity"])
        result, combat_text = self._combat(game, target, False, rng)
        won = result == "victory"
        if won:
            self._shift_war_morale(war, enemy, 12.0, 3.0)
            outcome = "你亲自击退敌方会战队，我方取得本轮主动。"
        else:
            self._shift_war_morale(war, side, 10.0, 2.0)
            outcome = "你未能击穿敌阵，本方主力接应后退守下一道战线。"
        if not self._finish_war_by_morale(game, war):
            counter = self._resolve_field_attack(game, war, enemy, rng, contexts)
        else:
            counter = ""
        war["battles"] = int(war.get("battles", 0)) + 1
        self._wear_war_guard_arrays(game, war)
        for battle_side in ("attacker", "defender"):
            war["exhaustion"][battle_side] = min(
                100.0, float(war["exhaustion"][battle_side]) + 7.0,
            )
        self._finish_war_by_morale(game, war)
        formation_text = self._war_formation_text(contexts)
        self._append_war_log(
            game, war, f"玩家参战·第{war['battles']}场会战",
            f"{formation_text} {outcome} {combat_text}" + (f" 其余战线：{counter}" if counter else ""),
        )

    def _finish_war_by_morale(self, game: GameState, war: dict[str, Any]) -> bool:
        if war.get("status") == "peace_ready":
            return True
        if war["morale"]["attacker"] > 0 and war["morale"]["defender"] > 0:
            return False
        winner = "defender" if war["morale"]["attacker"] <= 0 else "attacker"
        loser = "attacker" if winner == "defender" else "defender"
        war["status"] = "peace_ready"
        war["winner"] = winner
        war["loser"] = loser
        decisive = max(20.0, abs(float(war.get("war_score", 0))))
        war["war_score"] = decisive if winner == "attacker" else -decisive
        self._append_war_log(game, war, "士气崩溃", f"{self._war_side_name(game, war['kind'], war[f'{loser}_id'])}阵营士气归零，战争胜负已定，等待签订和约。")
        if war.get("controller") == "player" and self._player_war_side(game, war) == loser:
            war["peace_offer"] = self._generate_ai_peace_offer(game, war, winner)
            demands = "、".join(row["label"] for row in war["peace_offer"]["demands"])
            self._append_war_log(game, war, "敌方提出和约", f"敌方依据 {war['peace_offer']['budget']} 点战争分数提出：{demands}。")
        return True

    def war_action(self, game_id: str, war_id: str, action: str, *, ally_id: str = "") -> dict[str, Any]:
        game = self._load(game_id)
        war = next((row for row in game.wars if row.get("id") == war_id), None)
        if not war or war.get("status") not in {"active", "peace_ready"}:
            raise ValueError("这场战争已经结束或不存在")
        if game.pending_event or not game.player.alive or game.player.imprisonment:
            raise ValueError("当前状态无法处理征伐")
        side = self._player_war_side(game, war)
        if not side:
            raise ValueError("你并非这场战争的参战方")
        if action != "participate_round" and (
            war.get("controller") != "player" or not self._player_has_war_voice(game, war)
        ):
            raise ValueError("你尚未取得本势力的战争指挥权")
        rng = decode_rng(game.seed, game.rng_state)
        if action == "participate_round":
            if war.get("status") != "active":
                raise ValueError("战场胜负已定，无法再次参战")
            self._resolve_player_war_round(game, war, side, rng)
        elif action == "call_allies":
            if war.get("status") != "active":
                raise ValueError("胜负已定后不能再召集盟友")
            if not ally_id:
                raise ValueError("请选择要邀请参战的盟友")
            outcomes = self._call_war_allies(game, war, side, rng, ally_id=ally_id, limit=1)
            if not outcomes:
                raise ValueError("该势力并非可邀请盟友，或仍处于重邀冷却")
        elif action == "accept_ai_peace":
            offer = war.get("peace_offer")
            if war.get("status") != "peace_ready" or not offer or offer.get("recipient_side") != side:
                raise ValueError("当前没有需要接受的敌方和约")
            self._conclude_war_bundle(game, war, offer["demands"], offer["proposer_side"], automatic=True)
        elif action == "conquest":
            if war.get("preliminary_resolved"):
                raise ValueError("先锋出阵已经结算")
            enemy = "defender" if side == "attacker" else "attacker"
            candidates = self._available_warriors(game, war, enemy)
            if not candidates:
                war["morale"][enemy] = 0.0
                self._finish_war_by_morale(game, war)
                game.rng_state = encode_rng(rng)
                self.store.save(game)
                return self.present(game)
            team_size = min(len(candidates), rng.randint(1, 3))
            opponents = rng.sample(candidates[:min(12, len(candidates))], team_size)
            # Player-involved vanguard combat resolves the strongest enemy
            # formation through the detailed bilateral broadcaster.  Keep the
            # base team power raw here so that the same array is not counted a
            # second time by the off-screen abstraction multiplier.
            required = npc_team_combat_power(self._npc_power(npc) for npc in opponents)
            if enemy == "defender":
                required *= 1 + float(self._war_rules().get("defender_power_bonus", 0.10))
            event = self._instantiate_event(self.events_by_id["EVT_WAR_VANGUARD_001"], game, rng)
            event["body"] = event["body"].replace("{attacker}", self._war_side_name(game, war["kind"], war["attacker_id"])).replace("{defender}", self._war_side_name(game, war["kind"], war["defender_id"]))
            event["body"] += f" 敌方先锋为{'、'.join(npc.name for npc in opponents)}，队伍战力约 {required:.0f}。"
            event["runtime"] = {"war_id": war["id"], "enemy_ids": [npc.id for npc in opponents], "required_power": round(required, 1)}
            game.pending_event = event
        elif action == "round":
            if war.get("status") != "active":
                raise ValueError("战场胜负已定，只能进行和谈")
            if not war.get("preliminary_resolved"):
                war["preliminary_resolved"] = True
                war["vanguard_skipped"] = True
                self._append_war_log(game, war, "放弃先锋战", "你没有亲自参加先锋遭遇，直接命双方主力推进会战；本场不获得先锋士气修正。")
            contexts = self._war_formation_contexts(game, war)
            lines = [self._war_formation_text(contexts)]
            lines.append(self._resolve_field_attack(game, war, "attacker", rng, contexts))
            if not self._finish_war_by_morale(game, war):
                lines.append(self._resolve_field_attack(game, war, "defender", rng, contexts))
            war["battles"] = int(war.get("battles", 0)) + 1
            self._wear_war_guard_arrays(game, war)
            war["exhaustion"]["attacker"] = min(100.0, float(war["exhaustion"]["attacker"]) + 7.0)
            war["exhaustion"]["defender"] = min(100.0, float(war["exhaustion"]["defender"]) + 7.0)
            self._finish_war_by_morale(game, war)
            self._append_war_log(game, war, f"第{war['battles']}场会战", " ".join(lines))
        elif action == "retreat":
            if war.get("status") != "active":
                raise ValueError("战场胜负已经确定")
            war["morale"][side] = 0.0
            self._append_war_log(game, war, "主动撤退", f"{self._war_side_name(game, war['kind'], war[f'{side}_id'])}主动撤出战场，视为战败。")
            self._finish_war_by_morale(game, war)
        else:
            raise ValueError("未知战争行动")
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _resolve_war_vanguard(self, game: GameState, pending: dict[str, Any], mode: str, rng: random.Random) -> tuple[str, str]:
        war_id = str(pending.get("runtime", {}).get("war_id", ""))
        war = next((row for row in game.wars if row.get("id") == war_id and row.get("status") == "active"), None)
        if not war or war.get("preliminary_resolved"):
            return "war_absent", "战阵已经变化，这次先锋对阵不再有效。"
        if mode == "delay":
            return "delayed", "你暂缓出阵；先锋战尚未结算，整备后仍可再次征伐。"
        side = self._player_war_side(game, war)
        if not side or not self._player_has_war_voice(game, war):
            return "authority_lost", "你已经失去代表本势力出阵的权力。"
        required = max(1.0, float(pending.get("runtime", {}).get("required_power", 1.0)))
        enemy_ids = [str(npc_id) for npc_id in pending.get("runtime", {}).get("enemy_ids", [])]
        opponents = [self._find_npc(game, npc_id) for npc_id in enemy_ids]
        opponents = [npc for npc in opponents if npc is not None]
        enemy_name = "、".join(npc.name for npc in opponents) or "敌方先锋"
        members = [{
            "name": npc.name, "power": self._npc_power(npc),
            "realm_index": npc.realm_index, "layer": npc.layer, "npc_id": npc.id,
            "faction_id": self._npc_faction_id(game, npc.id), "path": npc.path, "race": npc.race,
        } for npc in opponents]
        result, combat_text = self._combat(game, {
            "target_name": enemy_name, "target_power": required,
            "target_realm_index": max((npc.realm_index for npc in opponents), default=game.player.realm_index),
            "target_layer": max((npc.layer for npc in opponents), default=1),
            "combat_type": "cultivator", "members": members, "action": "repel",
            "enemy_objective": "repel", "max_rounds": 5,
        }, False, rng)
        won = result == "victory"
        if won:
            war["morale"][side] = min(150.0, float(war["morale"][side]) + 30.0)
            text = f"{combat_text} 先锋目标达成，我方士气提升初始值的 30%。"
        else:
            war["morale"][side] = max(0.0, float(war["morale"][side]) - 20.0)
            text = f"{combat_text} 先锋目标未能达成，我方士气降低初始值的 20%。"
        war["preliminary_resolved"] = True
        self._append_war_log(game, war, "玩家先锋战", text)
        return "victory" if won else "defeat", text

    def _advance_wars_unit(self, game: GameState, rng: random.Random) -> list[str]:
        news: list[str] = []
        for war in game.wars:
            if war.get("status") != "active":
                continue
            self._ensure_war_shape(game, war)
            if self._finish_war_by_morale(game, war):
                if war.get("controller") == "ai":
                    winner = str(war["winner"])
                    offer = self._generate_ai_peace_offer(game, war, winner)
                    war["peace_offer"] = offer
                    self._conclude_war_bundle(game, war, offer["demands"], winner, automatic=True)
                continue
            player_side = self._player_war_side(game, war)
            if player_side and self._player_has_war_voice(game, war) and war.get("controller") != "player":
                war["controller"] = "player"
                war["player_side"] = player_side
                self._append_war_log(game, war, "指挥权移交", f"你取得势力话语权，接管战争；此前 {war.get('abstract_rounds', 0)} 个行动单位的战报已经补录。")
                continue
            if war.get("controller") == "player":
                # 自动推进只替玩家下达主力会战命令，不会把玩家本人编入先锋或参战队伍。
                enemy_side = "defender" if player_side == "attacker" else "attacker"
                enemy_score = float(war.get("war_score", 0)) * (1 if enemy_side == "attacker" else -1)
                if enemy_score < float(self._war_rules().get("ai_call_ally_score_threshold", -25)):
                    self._call_war_allies(game, war, enemy_side, rng, limit=1)
                if game.settings.get("auto_advance_player_wars", False):
                    if not war.get("preliminary_resolved"):
                        war["preliminary_resolved"] = True
                        war["vanguard_skipped"] = True
                        self._append_war_log(game, war, "自动略过先锋战", "自动推进仅调度势力主力，玩家本人没有出阵。")
                    contexts = self._war_formation_contexts(game, war)
                    lines = [self._war_formation_text(contexts)]
                    lines.append(self._resolve_field_attack(game, war, "attacker", rng, contexts))
                    if not self._finish_war_by_morale(game, war):
                        lines.append(self._resolve_field_attack(game, war, "defender", rng, contexts))
                    war["battles"] = int(war.get("battles", 0)) + 1
                    self._wear_war_guard_arrays(game, war)
                    for side in ("attacker", "defender"):
                        war["exhaustion"][side] = min(100.0, float(war["exhaustion"][side]) + 7.0)
                    self._finish_war_by_morale(game, war)
                    self._append_war_log(game, war, f"第{war['battles']}场自动会战", " ".join(lines))
                else:
                    for side in ("attacker", "defender"):
                        war["exhaustion"][side] = min(100.0, float(war["exhaustion"][side]) + 2.0)
                continue
            threshold = float(self._war_rules().get("ai_call_ally_score_threshold", -25))
            if float(war.get("war_score", 0)) < threshold:
                self._call_war_allies(game, war, "attacker", rng, limit=1)
            if -float(war.get("war_score", 0)) < threshold:
                self._call_war_allies(game, war, "defender", rng, limit=1)
            # The player contributes personal combat power only after choosing
            # to participate through the detailed battle action.
            attack_profile = self._war_power_profile(game, war, "attacker", include_player=False)
            defend_profile = self._war_power_profile(game, war, "defender", include_player=False)
            contexts = self._war_formation_contexts(game, war)
            attack_power = max(
                1.0, float(attack_profile["composite"]) * float(contexts["attacker"]["modifier"]),
            )
            defend_power = max(
                1.0, float(defend_profile["composite"]) * float(contexts["defender"]["modifier"]),
            )
            ratio = attack_power * rng.uniform(0.86, 1.16) / defend_power
            if ratio >= 1:
                loss = min(24.0, 7.0 + (ratio - 1) * 9.0)
                self._shift_war_morale(war, "defender", loss, 2.5)
                victor = "attacker"
            else:
                loss = min(24.0, 7.0 + (1 / max(0.1, ratio) - 1) * 9.0)
                self._shift_war_morale(war, "attacker", loss, 2.5)
                victor = "defender"
            war["abstract_rounds"] = int(war.get("abstract_rounds", 0)) + 1
            war["battles"] = int(war.get("battles", 0)) + 1
            self._wear_war_guard_arrays(game, war)
            for side in ("attacker", "defender"):
                war["exhaustion"][side] = min(100.0, float(war["exhaustion"][side]) + rng.uniform(6, 10))
            loser = "defender" if victor == "attacker" else "attacker"
            outcome = self._resolve_abstract_defeat(game, war, loser, rng)
            text = (
                f"综合双方总战力、前三位高阶修士与阵势条件权重结算。"
                f"{self._war_formation_text(contexts)} "
                f"{self._war_side_name(game, war['kind'], war[f'{victor}_id'])}在本行动单位占据上风。"
                + (f" {outcome}" if outcome else "")
            )
            self._append_war_log(game, war, "AI 战报", text)
            finished = self._finish_war_by_morale(game, war)
            if finished:
                winner = str(war["winner"])
                offer = self._generate_ai_peace_offer(game, war, winner)
                war["peace_offer"] = offer
                self._conclude_war_bundle(game, war, offer["demands"], winner, automatic=True)
            elif min(war["exhaustion"].values()) >= float(self._war_rules().get("white_peace_exhaustion", 78)):
                self._conclude_war(game, war, "white_peace", "attacker", automatic=True)
            if game.player.world == war.get("world"):
                news.append(f"{game.player.age}岁：{text}")
        return news

    def _generate_ai_peace_offer(self, game: GameState, war: dict[str, Any], proposer: str) -> dict[str, Any]:
        """Build a score-priced demand package instead of always asking for one execution."""
        recipient = "defender" if proposer == "attacker" else "attacker"
        target_power_id = war[f"{recipient}_id"]
        budget = int(min(100, max(0, round(abs(float(war.get("war_score", 0)))))))
        demands: list[dict[str, Any]] = []

        def add(term: str, *, target_id: str = "") -> bool:
            cost = WAR_TERM_DEFS[term][1]
            if sum(row["cost"] for row in demands) + cost > budget:
                return False
            demands.append({
                "term": term, "label": WAR_TERM_DEFS[term][0], "cost": cost,
                "target_power_id": target_power_id, "target_id": target_id,
            })
            return True

        winner_power = self._war_total_power(game, war, proposer)
        if proposer == "defender":
            winner_power /= 1 + float(self._war_rules().get("defender_power_bonus", 0.10))
        target_power = self._war_entity_power(game, war, recipient, target_power_id)
        ratio = winner_power / max(1.0, target_power)
        if war["kind"] == "sect" and budget >= WAR_TERM_DEFS["annex"][1]:
            if ratio >= float(self._war_rules().get("annex_power_ratio", 2.5)):
                add("annex")
            elif ratio >= float(self._war_rules().get("dissolve_power_ratio", 1.35)):
                add("dissolve")
            else:
                add("vassal")
        elif (war["kind"] == "sect" and budget >= WAR_TERM_DEFS["dissolve"][1]
              and ratio >= float(self._war_rules().get("dissolve_power_ratio", 1.35))):
            add("dissolve")
        elif budget >= WAR_TERM_DEFS["vassal"][1]:
            add("vassal")

        spent = sum(row["cost"] for row in demands)
        candidates = self._available_warriors(game, war, recipient, target_power_id)
        if budget - spent >= WAR_TERM_DEFS["execute"][1] and candidates:
            add("execute", target_id=candidates[0].id)
        for term in ("supplies", "stones", "alliance"):
            if term == "alliance" and any(row["term"] in {"annex", "dissolve", "vassal"} for row in demands):
                continue
            add(term)
        if not demands:
            add("white_peace")
        return {
            "proposer_side": proposer, "recipient_side": recipient, "budget": budget,
            "total_cost": sum(row["cost"] for row in demands), "demands": demands,
            "created_unit": game.diplomacy_unit,
        }

    def _conclude_war_bundle(self, game: GameState, war: dict[str, Any], demands: list[dict[str, Any]],
                             beneficiary: str, *, automatic: bool = False) -> str:
        if not demands:
            demands = [{"term": "white_peace", "target_power_id": war[f"{'defender' if beneficiary == 'attacker' else 'attacker'}_id"]}]
        details: list[str] = []
        ordered = [row for row in demands if row.get("term") not in {"dissolve", "annex"}]
        ordered.extend(row for row in demands if row.get("term") in {"dissolve", "annex"})
        for index, demand in enumerate(ordered):
            details.append(self._conclude_war(
                game, war, str(demand.get("term", "white_peace")), beneficiary,
                automatic=automatic, target_id=str(demand.get("target_id", "")),
                target_power_id=str(demand.get("target_power_id", "")),
                third_party_id=str(demand.get("third_party_id", "")),
                third_status=str(demand.get("third_status", "neutral")),
                finalize=index == len(ordered) - 1,
            ))
        war["peace_terms"] = copy.deepcopy(demands)
        if len(details) > 1:
            combined = "；".join(details)
            war["logs"][-1]["text"] = ("敌方依据战争分数提出并执行组合和约；" if automatic else "双方签订组合和约；") + combined
        return "；".join(details)

    def _conclude_war(self, game: GameState, war: dict[str, Any], term: str, beneficiary: str, *, automatic: bool = False,
                      target_id: str = "", target_power_id: str = "", third_party_id: str = "",
                      third_status: str = "neutral", finalize: bool = True) -> str:
        self._ensure_war_shape(game, war)
        loser = "defender" if beneficiary == "attacker" else "attacker"
        winner_id = war[f"{beneficiary}_id"]
        loser_id = target_power_id or war[f"{loser}_id"]
        if loser_id not in self._coalition_ids(war, loser):
            raise ValueError("和谈目标不属于敌方参战阵营")
        winner_name = self._war_side_name(game, war["kind"], winner_id)
        loser_name = self._war_side_name(game, war["kind"], loser_id)
        relation = self._war_relation(game, war["kind"], winner_id, loser_id)
        detail = "双方恢复和平"
        if term == "execute":
            candidates = self._available_warriors(game, war, loser, loser_id)
            victim = self._find_npc(game, target_id) if target_id else (candidates[0] if candidates else None)
            if not victim or victim not in candidates:
                raise ValueError("指定处死的修士不属于战败方参战名册")
            victim.alive = False
            victim.death_reason = "战败和约指定处死"
            detail = f"{victim.name}依约被处死"
        elif term == "alliance":
            self._set_diplomatic_relation(game, relation, "alliance", winner_id, loser_id, war["kind"], 72)
            detail = "双方被和约确立为同盟"
        elif term == "vassal":
            relation.update(status="vassal", affinity=45.0, since_age=game.player.age, overlord=winner_id, subject=loser_id)
            detail = f"{loser_name}成为{winner_name}的附庸"
        elif term == "change_relation":
            if not third_party_id or third_party_id in {winner_id, loser_id}:
                raise ValueError("必须指定第三方势力")
            third = self._war_relation(game, war["kind"], loser_id, third_party_id)
            self._set_diplomatic_relation(game, third, third_status, loser_id, third_party_id, war["kind"], 65 if third_status == "alliance" else 0)
            detail = f"{loser_name}被迫对第三方改为{RELATION_LABELS.get(third_status, third_status)}"
        elif term == "stones":
            amount = int(self._war_rules().get("stone_tribute", 10000))
            own_id = game.player.faction_id if war["kind"] == "sect" else self._player_allegiance_race(game.player)
            if own_id == winner_id:
                add_item(game.player, "spirit_stone", amount)
            elif own_id == loser_id:
                held = next((item.quantity for item in game.player.inventory if item.id == "spirit_stone"), 0)
                paid = min(held, amount)
                if paid:
                    remove_item(game.player, "spirit_stone", paid)
                amount = paid
            detail = f"{loser_name}向{winner_name}上供灵石 {amount}"
        elif term == "supplies":
            own_id = game.player.faction_id if war["kind"] == "sect" else self._player_allegiance_race(game.player)
            supplied: list[str] = []
            if own_id == winner_id:
                pool = [row["content_id"] for row in MARKET_GOODS if row["kind"] == "item" and row["content_id"] in ITEM_CATALOG
                        and "currency" not in ITEM_CATALOG[row["content_id"]].tags]
                for item_id in list(dict.fromkeys(pool))[:3]:
                    add_item(game.player, item_id)
                    supplied.append(ITEM_CATALOG[item_id].name)
            elif own_id == loser_id:
                for item in list(game.player.inventory):
                    if len(supplied) >= 3:
                        break
                    if item.id != "spirit_stone" and remove_item(game.player, item.id):
                        supplied.append(item.name)
            detail = f"{loser_name}缴纳丹药与装备" + (f"（{'、'.join(supplied)}）" if supplied else "")
        elif term in {"dissolve", "annex"}:
            if war["kind"] != "sect":
                raise ValueError("种族与界面势力不能被解散或合并")
            loser_sect = game.sects.get(loser_id)
            winner_sect = game.sects.get(winner_id)
            if not loser_sect:
                raise ValueError("战败宗门已经不存在")
            winner_power = self._war_total_power(game, war, beneficiary)
            if beneficiary == "defender":
                winner_power /= 1 + float(self._war_rules().get("defender_power_bonus", 0.10))
            target_power = self._war_entity_power(game, war, loser, loser_id)
            ratio = winner_power / max(1.0, target_power)
            if term == "annex":
                if ratio < float(self._war_rules().get("annex_power_ratio", 2.5)):
                    raise ValueError("双方战力差距尚不足以执行合并")
                if winner_sect:
                    for npc in self._sect_members(game, loser_sect):
                        if npc.alive:
                            npc.faction_id = winner_id
                            if all(existing.id != npc.id for existing in winner_sect.npcs):
                                winner_sect.npcs.append(npc)
                detail = f"{loser_name}并入{winner_name}"
            else:
                if ratio < float(self._war_rules().get("dissolve_power_ratio", 1.35)):
                    raise ValueError("胜方总战力尚不足以强制解散对方势力")
                for npc in self._sect_members(game, loser_sect):
                    if npc.alive:
                        npc.faction_id = None
                        game.notable_npcs.setdefault(npc.id, npc)
                detail = f"{loser_name}就地解散"
            loser_sect.extinct = True
            own_id = game.player.faction_id
            if own_id == winner_id and term == "annex":
                game.player.milestones["annexed_faction"] = 1
            wanted_key = f"sect:{loser_id}"
            if (
                own_id == winner_id and term == "dissolve"
                and float(game.player.hostility.get(wanted_key, 0))
                > float(WORLD_SYSTEMS["faction_conflict"]["wanted_threshold"])
            ):
                game.player.milestones["became_wanted_target"] = 1
                game.player.milestones["dissolved_wanted_power"] = 1
            if game.player.faction_id == loser_id:
                game.player.faction_id = winner_id if term == "annex" else None
        elif term != "white_peace":
            raise ValueError("未知战争条款")
        if not finalize:
            return detail
        war["status"] = "ended"
        war["end_age"] = game.player.age
        war["peace_term"] = term
        war["winner"] = None if term == "white_peace" else beneficiary
        truce_until = game.diplomacy_unit + int(self._war_rules().get("truce_units", 5))
        for attacker_id in self._coalition_ids(war, "attacker"):
            for defender_id in self._coalition_ids(war, "defender"):
                cross_relation = self._war_relation(game, war["kind"], attacker_id, defender_id)
                cross_relation["war_truce_until_unit"] = truce_until
                if cross_relation.get("status") not in {"alliance", "vassal"}:
                    cross_relation.update(status="truce", affinity=max(-20.0, float(cross_relation.get("affinity", -40))), since_age=game.player.age)
                    cross_relation["truce_until_unit"] = truce_until
        text = ("厌战迫使双方签订无条件和平；" if automatic else f"双方签订和约；") + detail + f"，停战 {int(self._war_rules().get('truce_units', 5))} 个行动单位。"
        self._append_war_log(game, war, "战争结束", text)
        game.history.append(HistoryRecord(
            "SYS_WAR_PEACE", 1, game.player.age, "战争和约", term, "ended", text,
            {"war_id": war["id"], "term": term}, ["system", "war", "diplomacy", f"world:{war['world']}"],
        ))
        return text

    def war_peace(self, game_id: str, war_id: str, term: str, *, target_id: str = "", target_power_id: str = "",
                  third_party_id: str = "", third_status: str = "neutral", concede: bool = False) -> dict[str, Any]:
        game = self._load(game_id)
        war = next((row for row in game.wars if row.get("id") == war_id), None)
        if not war or war.get("status") not in {"active", "peace_ready"}:
            raise ValueError("当前没有可供和谈的战争")
        if war.get("controller") != "player" or not self._player_has_war_voice(game, war):
            raise ValueError("你没有代表势力签署和约的权力")
        if term not in WAR_TERM_DEFS:
            raise ValueError("未知战争条款")
        if int(war.get("battles", 0)) < 2 and war.get("status") != "peace_ready" and term != "white_peace":
            raise ValueError("至少经历两场战事后才能提出有条件和谈")
        player_side = self._player_war_side(game, war)
        beneficiary = ("defender" if player_side == "attacker" else "attacker") if concede else player_side
        if not beneficiary:
            raise ValueError("你并非参战方")
        effective_score = float(war.get("war_score", 0)) * (1 if beneficiary == "attacker" else -1)
        cost = WAR_TERM_DEFS[term][1]
        loser = "defender" if beneficiary == "attacker" else "attacker"
        selected_power = target_power_id if not concede else ""
        selected_power = selected_power or war[f"{loser}_id"]
        if selected_power not in self._coalition_ids(war, loser):
            raise ValueError("和谈目标不属于战败阵营")
        if selected_power != war[f"{loser}_id"] and term != "white_peace":
            cost = int(round(cost * float(self._war_rules().get("ally_term_cost_multiplier", 1.25))))
        if not concede and term != "white_peace" and effective_score < cost:
            raise ValueError(f"当前战争分数 {effective_score:.0f}，不足以提出该条款（需要 {cost}）")
        if self._intrigue_enabled():
            own_id = str(war[f"{player_side}_id"])
            opposing_id = str(war[f"{'defender' if player_side == 'attacker' else 'attacker'}_id"])
            vote_rng = decode_rng(game.seed, game.rng_state)
            resolution = self._intrigue_resolve(
                game, str(war["kind"]), own_id, "make_peace", opposing_id, True, "player", vote_rng,
            )
            game.rng_state = encode_rng(vote_rng)
            if resolution["result"] != "passed":
                game.updated_at = now_iso()
                self.store.save(game)
                return self.present(game)
        self._conclude_war(game, war, term, beneficiary, target_id=target_id, target_power_id=selected_power,
                           third_party_id=third_party_id, third_status=third_status)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _public_war_system(self, game: GameState) -> dict[str, Any]:
        wars = []
        visible_wars = [war for war in game.wars if war.get("world") == game.player.world]
        for war in reversed(visible_wars[-20:]):
            self._ensure_war_shape(game, war)
            public = copy.deepcopy(war)
            public["attacker_name"] = self._war_side_name(game, war["kind"], war["attacker_id"])
            public["defender_name"] = self._war_side_name(game, war["kind"], war["defender_id"])
            public["player_side"] = self._player_war_side(game, war)
            public["player_controls"] = war.get("status") in {"active", "peace_ready"} and self._player_has_war_voice(game, war)
            public["can_participate"] = bool(
                war.get("status") == "active" and public["player_side"]
                and game.player.alive and not game.player.imprisonment and not game.pending_event
            )
            public["can_negotiate"] = int(war.get("battles", 0)) >= 2 or war.get("status") == "peace_ready"
            public["coalitions"] = {
                side: [{**row, "name": self._war_side_name(game, war["kind"], row["id"])}
                       for row in war["coalitions"][side]]
                for side in ("attacker", "defender")
            }
            cooldown = int(self._war_rules().get("ally_call_cooldown_units", 3))
            player_side = public["player_side"]
            callable_allies: list[dict[str, Any]] = []
            if player_side:
                for row in self._allied_powers(game, war, player_side):
                    prior = war["called_allies"].get(f"{player_side}:{row['id']}")
                    if prior and (prior.get("accepted") or game.diplomacy_unit - int(prior.get("unit", 0)) < cooldown):
                        continue
                    callable_allies.append({
                        **row, "name": self._war_side_name(game, war["kind"], row["id"]),
                        "caller_name": self._war_side_name(game, war["kind"], row["caller_id"]),
                        "chance_percent": round(float(row["chance"]) * 100),
                    })
            public["callable_allies"] = callable_allies
            public["can_call_allies"] = bool(callable_allies)
            public["power_summary"] = {
                side: self._war_power_profile(game, war, side) for side in ("attacker", "defender")
            }
            formation_contexts = self._war_formation_contexts(game, war)
            public["formation_summary"] = {}
            for formation_side in ("attacker", "defender"):
                context = formation_contexts[formation_side]
                public["formation_summary"][formation_side] = {
                    key: copy.deepcopy(context.get(key)) for key in (
                        "active", "name", "owner_name", "source_kind", "source_id", "integrity",
                        "modifier", "conditions", "stability", "core_nature", "metrics",
                    )
                }
                public["power_summary"][formation_side]["formation_modifier"] = float(context["modifier"])
                public["power_summary"][formation_side]["effective_composite"] = round(
                    float(public["power_summary"][formation_side]["composite"])
                    * float(context["modifier"]), 1,
                )
            if war["kind"] == "race":
                public["third_parties"] = [
                    {"id": race_id, "name": row["name"]} for race_id, row in RACE_DEFINITIONS.items()
                    if war["world"] in row.get("worlds", []) and not self._participant_side(war, race_id)
                ]
            else:
                public["third_parties"] = [
                    {"id": sect.id, "name": sect.name} for sect in game.sects.values()
                    if not sect.extinct and sect.world == war["world"] and not self._participant_side(war, sect.id)
                ]
            public["roster"] = {
                side: [{"id": npc.id, "name": npc.name, "realm_name": self._npc_realm_name(npc),
                        "combat_power": round(self._npc_power(npc), 1), "alive": npc.alive,
                        "escaped": npc.id in set(war.get("escaped", {}).get(side, [])), "wounds": npc.wounds,
                        "owner_id": war["roster_owner"].get(npc.id, war[f"{side}_id"]),
                        "owner_name": self._war_side_name(game, war["kind"], war["roster_owner"].get(npc.id, war[f"{side}_id"]))}
                       for npc_id in war.get("roster", {}).get(side, []) if (npc := self._find_npc(game, npc_id))]
                for side in ("attacker", "defender")
            }
            if public.get("peace_offer"):
                for demand in public["peace_offer"].get("demands", []):
                    demand["target_power_name"] = self._war_side_name(game, war["kind"], demand.get("target_power_id", ""))
                    victim = self._find_npc(game, demand.get("target_id", ""))
                    demand["target_name"] = victim.name if victim else ""
            wars.append(public)
        return {
            "wars": wars,
            "active_count": sum(
                war.get("status") in {"active", "peace_ready"} and war.get("world") == game.player.world
                for war in game.wars
            ),
            "terms": {
                key: {
                    "name": value[0], "cost": value[1],
                    "power_ratio": (
                        float(self._war_rules().get("dissolve_power_ratio", 1.35)) if key == "dissolve"
                        else float(self._war_rules().get("annex_power_ratio", 2.5)) if key == "annex" else None
                    ),
                }
                for key, value in WAR_TERM_DEFS.items()
            },
        }

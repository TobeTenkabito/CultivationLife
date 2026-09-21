from __future__ import annotations

import copy
import math
import random
from typing import Any

from .content_registry import (
    ACTIONS, GUIXU_TIDE_CONTENT, ITEM_CATALOG, REALMS, TECHNIQUE_CATALOG,
    WORLD_SYSTEMS,
)
from .models import GameState, HistoryRecord, SectNpc
from .rules import (
    acquire_technique, add_item, divine_sense_level, expected_combat_power, has_item,
    max_hp, max_mp, opportunity_multiplier, remove_item,
)
from .runtime import decode_rng, encode_rng, now_iso
from .possession_system import advance_player_age


LAYER_ORDER = ("outer", "middle", "inner", "final")
MOVE_COSTS = {
    frozenset(("outer", "middle")): 3,
    frozenset(("middle", "inner")): 4,
    frozenset(("inner", "final")): 5,
    frozenset(("inner", "secret")): 2,
}


def guixu_content_available() -> bool:
    return bool(GUIXU_TIDE_CONTENT.get("dungeons"))


class GuixuSystemMixin:
    """Periodic Guixu dungeons using one additive state container."""

    @staticmethod
    def _guixu_definitions() -> dict[str, dict[str, Any]]:
        return {
            str(row["id"]): row for row in GUIXU_TIDE_CONTENT.get("dungeons", [])
        }

    @staticmethod
    def _guixu_settings() -> dict[str, Any]:
        return GUIXU_TIDE_CONTENT.get("settings", {})

    @staticmethod
    def _next_guixu_open(definition: dict[str, Any], age: int) -> int:
        first = int(definition.get("first_open_year", definition["period_years"]))
        period = int(definition["period_years"])
        if age <= first:
            return first
        return first + math.ceil((age - first) / period) * period

    def _ensure_guixu_state(self, game: GameState) -> bool:
        state = game.guixu_state
        changed = False
        if not isinstance(state, dict):
            game.guixu_state = state = {}
            changed = True
        defaults = {
            "schema_version": 1, "cycles": {}, "entered_cycles": {},
            "external_treasures": [], "player_session": None,
        }
        for key, default in defaults.items():
            if key not in state:
                state[key] = copy.deepcopy(default)
                changed = True
        definitions = self._guixu_definitions()
        if not definitions:
            session = state.get("player_session")
            if session:
                game.player.location_id = str(session.get("entry_location_id") or game.player.location_id)
                state["player_session"] = None
                game.history.append(HistoryRecord(
                    "SYS_GUIXU_DISABLED_EJECT", 1, game.player.age, "归墟规则冻结", None,
                    "ejected", "归墟扩展未启用，你被安全送回原入口；既有周期状态保持冻结。",
                    {}, ["system", "guixu", "migration"],
                ))
                changed = True
            return changed
        cycles = state["cycles"]
        for dungeon_id, definition in definitions.items():
            if dungeon_id in cycles:
                continue
            next_open = self._next_guixu_open(definition, game.player.age)
            cycles[dungeon_id] = {
                "phase": "closed", "cycle_index": 0,
                "next_open_age": next_open,
                "next_announce_age": next_open - int(definition["announce_lead_years"]),
                "pool_remaining": [str(row["id"]) for row in definition["treasure_pool"]],
                "round_entries": [], "roster": [], "last_report": None,
                "opened_age": None,
            }
            changed = True
        return changed

    def _guixu_entry_definition(
        self, dungeon: dict[str, Any], pool_entry_id: str,
    ) -> dict[str, Any]:
        entry = next(
            (row for row in dungeon["treasure_pool"] if row["id"] == pool_entry_id), None,
        )
        if entry is None:
            raise ValueError("归墟宝物定义已经不存在")
        return entry

    @staticmethod
    def _guixu_weighted_key(weights: dict[str, Any], rng: random.Random) -> str:
        keys = list(weights)
        return rng.choices(keys, weights=[float(weights[key]) for key in keys], k=1)[0]

    def _announce_guixu_cycle(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any], rng: random.Random,
    ) -> None:
        available = list(cycle["pool_remaining"])
        draw_count = min(int(self._guixu_settings()["draw_per_cycle"]), len(available))
        selected = rng.sample(available, draw_count) if draw_count else []
        for entry_id in selected:
            cycle["pool_remaining"].remove(entry_id)
        cycle["cycle_index"] = int(cycle.get("cycle_index", 0)) + 1
        pool_exhausted = not cycle["pool_remaining"]
        cycle["round_entries"] = [{
            "pool_entry_id": entry_id, "layer_id": None, "claim_at_day": None,
            "holder_id": None, "resolution": "announced",
            "pool_last": bool(pool_exhausted and entry_id == selected[-1]),
        } for entry_id in selected]
        cycle["roster"] = []
        cycle["phase"] = "announced"
        majors = [
            self._guixu_entry_definition(dungeon, entry_id)["name"]
            for entry_id in selected
            if self._guixu_entry_definition(dungeon, entry_id).get("tier") == "major"
        ]
        if not majors and selected:
            ranked = sorted(
                (self._guixu_entry_definition(dungeon, entry_id) for entry_id in selected),
                key=lambda row: float(row.get("value", 0)), reverse=True,
            )
            majors = [str(row["name"]) for row in ranked[:1]]
        game.history.append(HistoryRecord(
            "SYS_GUIXU_ANNOUNCE", 1, game.player.age, "归墟预告", dungeon["id"],
            "announced", f"{dungeon['name']}将在{dungeon['announce_lead_years']}年后开启；"
            + (f"本届重宝疑为{'、'.join(majors[:2])}。" if majors else "主宝物池已经搬空。"),
            {"cycle_index": cycle["cycle_index"], "entries": selected},
            ["system", "guixu", "announcement", f"world:{dungeon['world']}"],
        ))
        if (
            game.settings.get("guixu_event_popup", True)
            and game.player.world == dungeon["world"] and not game.pending_event
        ):
            event = self._instantiate_event(self.events_by_id["EVT_GUIXU_ANNOUNCE"], game, rng)
            event["body"] = (
                event["body"].replace("{dungeon_name}", str(dungeon["name"]))
                .replace("{lead_years}", str(dungeon["announce_lead_years"]))
                .replace("{major_treasures}", "、".join(majors[:2]) or "无")
            )
            event["runtime"] = {"dungeon_id": dungeon["id"], "cycle_index": cycle["cycle_index"]}
            game.pending_event = event

    def _guixu_relation_ids(self, game: GameState) -> set[str]:
        player = game.player
        return {
            str(row.get("id")) for row in [
                player.master, player.dao_companion, *player.dao_friends,
                *player.disciples, *player.concubines,
            ] if row and row.get("id")
        }

    def _generate_guixu_roster(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any], rng: random.Random,
    ) -> list[dict[str, Any]]:
        maximum = tuple(map(int, dungeon["max_entry_rank"]))
        fixed_candidates = [
            npc for npc in self._all_world_npcs(game)
            if npc.alive and npc.world == dungeon["world"]
            and (npc.realm_index, npc.layer) <= maximum
        ]
        rng.shuffle(fixed_candidates)
        used_fixed: set[str] = set()
        roster: list[dict[str, Any]] = []
        rank_bands = {
            "outer": (5, 11), "middle": (3, 8), "inner": (1, 5), "final": (0, 3),
        }
        for layer in dungeon["layers"]:
            layer_id = str(layer["id"])
            if layer_id == "secret":
                continue
            size = int(layer.get("roster_size", 0))
            fixed = [npc for npc in fixed_candidates if npc.id not in used_fixed][:min(2, size)]
            for npc in fixed:
                used_fixed.add(npc.id)
                power = self._npc_power(npc)
                roster.append({
                    "actor_id": f"fixed:{npc.id}", "actor_kind": "fixed", "npc_id": npc.id,
                    "name": npc.name, "layer_id": layer_id, "realm_index": npc.realm_index,
                    "layer": npc.layer, "power": round(power, 1), "status": "active",
                    "protected": npc.id in self._guixu_relation_ids(game),
                })
            low, high = rank_bands[layer_id]
            for index in range(size - len(fixed)):
                offset = rng.randint(low, high)
                realm_index, realm_layer = maximum
                realm_layer -= offset
                while realm_layer < 1 and realm_index > 1:
                    realm_index -= 1
                    realm_layer += REALMS[realm_index].layers
                realm_index = max(1, realm_index)
                realm_layer = max(1, min(REALMS[realm_index].layers, realm_layer))
                power = expected_combat_power(realm_index, realm_layer) * rng.uniform(.88, 1.16)
                actor_id = f"anon:{cycle['cycle_index']}:{layer_id}:{index}"
                roster.append({
                    "actor_id": actor_id, "actor_kind": "anonymous", "npc_id": None,
                    "name": f"{layer['name']}修士·{index + 1}", "layer_id": layer_id,
                    "realm_index": realm_index, "layer": realm_layer,
                    "power": round(power, 1), "status": "active", "protected": False,
                })
        return roster

    def _open_guixu_cycle(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any], rng: random.Random,
    ) -> None:
        if cycle["phase"] == "closed":
            self._announce_guixu_cycle(game, dungeon, cycle, rng)
            game.pending_event = None
        cycle["roster"] = self._generate_guixu_roster(game, dungeon, cycle, rng)
        window = int(dungeon["window_days"])
        for row in cycle["round_entries"]:
            definition = self._guixu_entry_definition(dungeon, str(row["pool_entry_id"]))
            row["layer_id"] = self._guixu_weighted_key(definition["layer_weights"], rng)
            row["claim_at_day"] = rng.randint(3, max(3, window - 5))
            row["holder_id"] = None
            row["resolution"] = "unclaimed"
        cycle["phase"] = "open"
        cycle["opened_age"] = game.player.age
        session = game.guixu_state.get("player_session")
        if session and session.get("dungeon_id") == dungeon["id"] and session.get("trapped"):
            session["trapped"] = False
            session["remaining_days"] = window
            session["cycle_index"] = cycle["cycle_index"]
            session["carried_entry_ids"] = []
            session["recruited_actor_ids"] = []
        game.history.append(HistoryRecord(
            "SYS_GUIXU_OPEN", 1, game.player.age, "归墟开启", dungeon["id"], "opened",
            f"{dungeon['name']}开启，本届潮门可稳定{window}天。",
            {"cycle_index": cycle["cycle_index"]},
            ["system", "guixu", "open", f"world:{dungeon['world']}"],
        ))
        if (
            game.settings.get("guixu_event_popup", True)
            and game.player.world == dungeon["world"] and not game.pending_event
            and not (session and session.get("dungeon_id") == dungeon["id"])
        ):
            event = self._instantiate_event(self.events_by_id["EVT_GUIXU_OPEN"], game, rng)
            entry_name = self.maps.location(dungeon["world"], dungeon["entry_location_id"])["name"]
            event["body"] = (
                event["body"].replace("{dungeon_name}", str(dungeon["name"]))
                .replace("{window_days}", str(window)).replace("{entry_name}", str(entry_name))
            )
            event["runtime"] = {"dungeon_id": dungeon["id"], "cycle_index": cycle["cycle_index"]}
            game.pending_event = event

    def _assign_due_guixu_entries(
        self, dungeon: dict[str, Any], cycle: dict[str, Any], elapsed_days: int, rng: random.Random,
    ) -> None:
        active_by_layer: dict[str, list[dict[str, Any]]] = {}
        for actor in cycle.get("roster", []):
            if actor.get("status") == "active":
                active_by_layer.setdefault(str(actor["layer_id"]), []).append(actor)
        for row in cycle.get("round_entries", []):
            if row.get("resolution") != "unclaimed" or int(row.get("claim_at_day") or 10**9) > elapsed_days:
                continue
            candidates = active_by_layer.get(str(row.get("layer_id")), [])
            if candidates:
                row["holder_id"] = rng.choice(candidates)["actor_id"]
                row["resolution"] = "held"

    def _close_guixu_cycle(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any], rng: random.Random,
    ) -> None:
        if cycle.get("phase") != "open":
            return
        self._assign_due_guixu_entries(dungeon, cycle, int(dungeon["window_days"]), rng)
        roster = {row["actor_id"]: row for row in cycle.get("roster", [])}
        report = {"lost": [], "carried": [], "trapped": [], "returned": [], "player": []}
        for row in cycle.get("round_entries", []):
            definition = self._guixu_entry_definition(dungeon, str(row["pool_entry_id"]))
            resolution = str(row.get("resolution", "unclaimed"))
            if resolution == "player":
                report["player"].append(definition["name"])
                continue
            holder = roster.get(str(row.get("holder_id")))
            if holder is None:
                cycle["pool_remaining"].append(row["pool_entry_id"])
                row["resolution"] = "returned"
                report["returned"].append(definition["name"])
                continue
            if holder["actor_kind"] == "anonymous":
                holder["status"] = "departed"
                row["resolution"] = "lost"
                report["lost"].append(definition["name"])
                continue
            outcome = rng.choices(["carried", "trapped", "lost"], weights=[.62, .25, .13], k=1)[0]
            row["resolution"] = outcome
            holder["status"] = "trapped" if outcome == "trapped" else "departed"
            report[outcome].append(definition["name"])
            if outcome in {"carried", "trapped"}:
                game.guixu_state["external_treasures"].append({
                    "dungeon_id": dungeon["id"], "pool_entry_id": row["pool_entry_id"],
                    "holder_npc_id": holder.get("npc_id"), "status": outcome,
                })
        session = game.guixu_state.get("player_session")
        if session and session.get("dungeon_id") == dungeon["id"] and not session.get("exited"):
            session["trapped"] = True
            session["remaining_days"] = 0
        cycle["phase"] = "closed"
        # The closing tide ejects every other explorer.  Keep only the outcome
        # report and external treasure records; a trapped player must not keep
        # seeing stale actors from the finished expedition.
        cycle["roster"] = []
        cycle["last_report"] = report
        cycle["next_open_age"] = int(cycle["next_open_age"]) + int(dungeon["period_years"])
        cycle["next_announce_age"] = int(cycle["next_open_age"]) - int(dungeon["announce_lead_years"])
        game.history.append(HistoryRecord(
            "SYS_GUIXU_CLOSE", 1, game.player.age, "归墟闭合", dungeon["id"], "closed",
            f"{dungeon['name']}闭合：玩家取得{len(report['player'])}件，NPC携出{len(report['carried'])}件，"
            f"被困{len(report['trapped'])}件，永久失落{len(report['lost'])}件，回池{len(report['returned'])}件。",
            copy.deepcopy(report), ["system", "guixu", "report", f"world:{dungeon['world']}"],
        ))

    def _advance_guixu_calendar(
        self, game: GameState, rng: random.Random, era_news: list[str],
    ) -> bool:
        """Advance yearly Guixu boundaries; return True when player input is required."""
        self._ensure_guixu_state(game)
        definitions = self._guixu_definitions()
        requires_input = False
        for dungeon_id, dungeon in definitions.items():
            cycle = game.guixu_state["cycles"][dungeon_id]
            if cycle.get("phase") == "open" and game.player.age > int(cycle.get("opened_age") or -1):
                session = game.guixu_state.get("player_session")
                if not session or session.get("dungeon_id") != dungeon_id or not session.get("trapped"):
                    self._close_guixu_cycle(game, dungeon, cycle, rng)
                    era_news.append(f"{game.player.age}岁：{dungeon['name']}闭合。")
            if cycle.get("phase") == "closed" and game.player.age >= int(cycle["next_announce_age"]):
                self._announce_guixu_cycle(game, dungeon, cycle, rng)
                era_news.append(f"{game.player.age}岁：收到{dungeon['name']}预告。")
                if game.pending_event:
                    requires_input = True
            if cycle.get("phase") == "announced" and game.player.age >= int(cycle["next_open_age"]):
                self._open_guixu_cycle(game, dungeon, cycle, rng)
                era_news.append(f"{game.player.age}岁：{dungeon['name']}开启。")
                if game.pending_event:
                    requires_input = True
        return requires_input

    def _guixu_cycle_and_definition(
        self, game: GameState, dungeon_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        dungeon = self._guixu_definitions().get(dungeon_id)
        if not dungeon:
            raise ValueError("未知归墟副本")
        return dungeon, game.guixu_state["cycles"][dungeon_id]

    def _enforce_guixu_rank_boundary(self, game: GameState, reason: str) -> str:
        """Eject an explorer whose effective cultivation reaches the dungeon boundary."""
        session = game.guixu_state.get("player_session") if isinstance(game.guixu_state, dict) else None
        if not session:
            return ""
        dungeon = self._guixu_definitions().get(str(session.get("dungeon_id", "")))
        if not dungeon or (game.player.realm_index, game.player.layer) < tuple(dungeon["eject_rank"]):
            return ""
        game.player.location_id = str(dungeon["entry_location_id"])
        game.guixu_state["player_session"] = None
        game.history.append(HistoryRecord(
            "SYS_GUIXU_EJECT", 1, game.player.age, "归墟界限传出", dungeon["id"], reason,
            f"你的当前修为达到{dungeon['name']}承载界限，被潮眼送回入口。",
            {"dungeon_id": dungeon["id"], "reason": reason},
            ["system", "guixu", "eject", f"world:{dungeon['world']}"],
        ))
        return f" 复原后的修为超过{dungeon['name']}承载界限，你随即被潮眼送回入口。"

    def _guixu_grant_entry(
        self, game: GameState, dungeon: dict[str, Any], row: dict[str, Any], source: str,
    ) -> str:
        definition = self._guixu_entry_definition(dungeon, str(row["pool_entry_id"]))
        kind, content_id = str(definition["kind"]), str(definition["content_id"])
        if kind == "technique":
            acquire_technique(game.player, TECHNIQUE_CATALOG[content_id])
        else:
            add_item(game.player, content_id, int(definition.get("quantity", 1)))
        row["holder_id"] = "player"
        row["resolution"] = "player"
        session = game.guixu_state.get("player_session")
        if session is not None:
            session.setdefault("carried_entry_ids", []).append(row["pool_entry_id"])
        treasure_result = "last_treasure" if row.get("pool_last") else source
        game.history.append(HistoryRecord(
            "SYS_GUIXU_TREASURE", 1, game.player.age, "归墟得宝", row["pool_entry_id"], treasure_result,
            f"你取得了{definition['name']}。", {"dungeon_id": dungeon["id"], "entry_id": row["pool_entry_id"]},
            ["system", "guixu", "treasure"],
        ))
        return str(definition["name"])

    def _guixu_elapsed_days(
        self, dungeon: dict[str, Any], session: dict[str, Any],
    ) -> int:
        return int(dungeon["window_days"]) - int(session.get("remaining_days", 0))

    def _consume_guixu_days(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        session: dict[str, Any], days: int, rng: random.Random,
    ) -> None:
        session["remaining_days"] = max(0, int(session.get("remaining_days", 0)) - int(days))
        self._assign_due_guixu_entries(dungeon, cycle, self._guixu_elapsed_days(dungeon, session), rng)
        if session["remaining_days"] <= 0:
            self._close_guixu_cycle(game, dungeon, cycle, rng)

    @staticmethod
    def _guixu_return_days(layer_id: str) -> int:
        return {"outer": 1, "middle": 4, "inner": 8, "final": 13, "secret": 10}[layer_id]

    def _guixu_actor(self, cycle: dict[str, Any], actor_id: str) -> dict[str, Any]:
        actor = next((row for row in cycle.get("roster", []) if row["actor_id"] == actor_id), None)
        if not actor or actor.get("status") not in {"active", "trapped"}:
            raise ValueError("目标修士已经不在当前归墟")
        return actor

    def _guixu_relationship_role(self, game: GameState, npc_id: str) -> str | None:
        player = game.player
        if player.master and str(player.master.get("id")) == npc_id:
            return "师父"
        if player.dao_companion and str(player.dao_companion.get("id")) == npc_id:
            return "道侣"
        if any(str(row.get("id")) == npc_id for row in player.dao_friends):
            return "道友"
        if any(str(row.get("id")) == npc_id for row in player.disciples):
            return "弟子"
        if any(str(row.get("id")) == npc_id for row in player.concubines):
            return "侍妾"
        return None

    def _break_guixu_relationship(self, game: GameState, npc_id: str) -> None:
        player = game.player
        player.party = [row for row in player.party if str(row.get("id")) != npc_id]
        if player.master and str(player.master.get("id")) == npc_id:
            player.master = None
        if player.dao_companion and str(player.dao_companion.get("id")) == npc_id:
            player.dao_companion = None
        player.dao_friends = [row for row in player.dao_friends if str(row.get("id")) != npc_id]
        player.disciples = [row for row in player.disciples if str(row.get("id")) != npc_id]
        player.concubines = [row for row in player.concubines if str(row.get("id")) != npc_id]
        player.karma += 60
        player.fame += 25

    def _guixu_fight(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        session: dict[str, Any], actor: dict[str, Any], rng: random.Random,
    ) -> tuple[str, str]:
        allies = []
        for ally_id in session.get("recruited_actor_ids", []):
            ally = next((row for row in cycle.get("roster", []) if row["actor_id"] == ally_id), None)
            if ally and ally.get("status") == "recruited":
                allies.append({
                    "name": ally["name"], "power_ratio": float(ally["power"]) / max(1.0, float(actor["power"])),
                    "realm_offset": int(ally["realm_index"]) - game.player.realm_index,
                })
        target = {
            "target_name": actor["name"], "target_power": float(actor["power"]),
            "primary_power": float(actor["power"]), "target_realm_index": int(actor["realm_index"]),
            "target_layer": int(actor["layer"]), "combat_type": "cultivator", "action": "slay",
            "npc_id": actor.get("npc_id") or actor["actor_id"], "kill_karma": True,
            "non_story_combat": True, "player_allies": allies,
            "natural_terrain": "狭窄", "artificial_conditions": [],
            "kill_pursuit_threshold": float(
                self._guixu_settings().get("combat_kill_pursuit_threshold", .58)
            ),
            "pursuit_chance_bonus": float(
                self._guixu_settings().get("combat_pursuit_chance_bonus", .22)
            ),
        }
        result, summary = self._combat(game, target, True, rng)
        if result == "killed":
            actor["status"] = "dead"
            for row in cycle.get("round_entries", []):
                if row.get("holder_id") == actor["actor_id"]:
                    self._guixu_grant_entry(game, dungeon, row, "combat")
            if actor.get("npc_id") and self._guixu_relationship_role(game, str(actor["npc_id"])):
                self._break_guixu_relationship(game, str(actor["npc_id"]))
        self._consume_guixu_days(
            game, dungeon, cycle, session,
            int(self._guixu_settings()["action_days"]["combat"]), rng,
        )
        return result, summary

    def guixu_action(self, game_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        game = self._load(game_id)
        if not guixu_content_available():
            raise ValueError("归墟之潮 DLC 当前未启用")
        self._ensure_guixu_state(game)
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        if not game.player.alive:
            raise ValueError("此生已经结束")
        rng = decode_rng(game.seed, game.rng_state)
        session = game.guixu_state.get("player_session")
        result, summary = action, ""
        history_event = "SYS_GUIXU_ACTION"

        if action == "enter":
            dungeon_id = str(payload.get("dungeon_id", ""))
            dungeon, cycle = self._guixu_cycle_and_definition(game, dungeon_id)
            if session:
                raise ValueError("你已经身在归墟之中")
            if cycle.get("phase") != "open":
                raise ValueError("这座归墟当前没有开启")
            if game.player.world != dungeon["world"] or game.player.location_id != dungeon["entry_location_id"]:
                raise ValueError("你必须先抵达归墟入口地域")
            if (game.player.realm_index, game.player.layer) > tuple(dungeon["max_entry_rank"]):
                raise ValueError("你的修为已经超过这座归墟的入场上限")
            key = f"{dungeon_id}:{cycle['cycle_index']}"
            if key in game.guixu_state["entered_cycles"]:
                raise ValueError("每人每届只能进入一次")
            game.guixu_state["entered_cycles"][key] = True
            session = {
                "dungeon_id": dungeon_id, "cycle_index": cycle["cycle_index"], "layer_id": "outer",
                "remaining_days": max(0, int(dungeon["window_days"]) - 1), "trapped": False,
                "entry_location_id": dungeon["entry_location_id"], "clue_count": 0,
                "secret_unlocked": False, "carried_entry_ids": [], "recruited_actor_ids": [],
                "negotiation_attempts": {}, "pending_betrayal": None,
            }
            game.guixu_state["player_session"] = session
            result, summary, history_event = "entered", f"你踏入{dungeon['name']}，抵达外层。", "SYS_GUIXU_ENTER"
        else:
            if not session:
                raise ValueError("你当前不在归墟之中")
            dungeon, cycle = self._guixu_cycle_and_definition(game, str(session["dungeon_id"]))
            if action == "move":
                target = str(payload.get("target_layer_id", ""))
                current = str(session["layer_id"])
                edge = frozenset((current, target))
                if edge not in MOVE_COSTS:
                    raise ValueError("两层之间没有直接通路")
                if target == "secret" and not session.get("secret_unlocked"):
                    raise ValueError("尚未找到秘层通道")
                if session.get("trapped"):
                    cost = 0
                else:
                    cost = MOVE_COSTS[edge]
                    self._consume_guixu_days(game, dungeon, cycle, session, cost, rng)
                session["layer_id"] = target
                result = "secret" if target == "secret" else "moved"
                summary = f"你移动到{next(row['name'] for row in dungeon['layers'] if row['id'] == target)}，耗时{cost}天。"
                history_event = "SYS_GUIXU_MOVE"
            elif action == "search":
                if session.get("trapped"):
                    raise ValueError("被困期只能静修、移动或等待下一届开启")
                days = int(self._guixu_settings()["action_days"]["search"])
                elapsed_after = self._guixu_elapsed_days(dungeon, session) + days
                candidates = [
                    row for row in cycle.get("round_entries", [])
                    if row.get("layer_id") == session["layer_id"] and row.get("resolution") == "unclaimed"
                    and int(row.get("claim_at_day") or 0) > elapsed_after
                ]
                if candidates:
                    row = rng.choice(candidates)
                    name = self._guixu_grant_entry(game, dungeon, row, "searched")
                    result, summary = "found", f"你赶在其他修士之前找到了{name}。"
                else:
                    if not session.get("secret_unlocked") and rng.random() < .35:
                        session["clue_count"] = int(session.get("clue_count", 0)) + 1
                        threshold = int(self._guixu_settings().get("secret_clue_threshold", 3))
                        if session["clue_count"] >= threshold:
                            session["secret_unlocked"] = True
                            result, summary = "secret_clue_complete", "你拼合潮纹，找到了秘层通道。"
                        else:
                            result, summary = "secret_clue", f"你发现一条秘层线索（{session['clue_count']}/{threshold}）。"
                    else:
                        result, summary = "empty", "这一带只剩破碎禁制，没有找到无主宝物。"
                self._consume_guixu_days(game, dungeon, cycle, session, days, rng)
                history_event = "SYS_GUIXU_SEARCH"
            elif action == "return":
                if session.get("trapped"):
                    raise ValueError("潮门已经闭合，只能等待下一届或突破传出")
                cost = self._guixu_return_days(str(session["layer_id"]))
                before = int(session["remaining_days"])
                if before < cost:
                    self._consume_guixu_days(game, dungeon, cycle, session, cost, rng)
                    session["layer_id"] = "outer"
                    result, summary = "trapped", "潮门在返程途中闭合，你被困在归墟之内。"
                else:
                    session["remaining_days"] = before - cost
                    carried = len(session.get("carried_entry_ids", []))
                    result = "narrow_escape" if session["remaining_days"] < 3 else "full_return" if carried >= 3 else "returned"
                    summary = f"你耗时{cost}天返回入口，携出{carried}件归墟宝物。"
                    session["exited"] = True
                    game.guixu_state["player_session"] = None
                history_event = "SYS_GUIXU_RETURN"
            elif action == "rest":
                hp_before, mp_before = game.player.hp, game.player.mp
                hp_max, mp_max = max_hp(game.player), max_mp(game.player)
                game.player.hp = min(hp_max, game.player.hp + hp_max * .35)
                game.player.mp = min(mp_max, game.player.mp + mp_max * .45)
                if not session.get("trapped"):
                    self._consume_guixu_days(
                        game, dungeon, cycle, session,
                        int(self._guixu_settings()["action_days"]["rest"]), rng,
                    )
                result = "rested"
                summary = (
                    f"你在归墟内就地调息，气血恢复{game.player.hp - hp_before:.0f}，"
                    f"法力恢复{game.player.mp - mp_before:.0f}。"
                )
                history_event = "SYS_GUIXU_REST"
            elif action in {"fight", "flee", "recruit", "negotiate"}:
                actor = self._guixu_actor(cycle, str(payload.get("actor_id", "")))
                if actor["layer_id"] != session["layer_id"]:
                    raise ValueError("目标修士不在当前层")
                if action == "fight":
                    role = self._guixu_relationship_role(game, str(actor.get("npc_id") or ""))
                    confirmed = bool(payload.get("confirm_betrayal", False))
                    marker = {"actor_id": actor["actor_id"], "role": role} if role else None
                    if role and not confirmed:
                        session["pending_betrayal"] = marker
                        result, summary = "confirmation_required", f"{actor['name']}是你的{role}。再次确认才会进入致命夺宝战。"
                    elif role and session.get("pending_betrayal") != marker:
                        raise ValueError("背叛确认已经失效")
                    else:
                        result, summary = self._guixu_fight(game, dungeon, cycle, session, actor, rng)
                        session["pending_betrayal"] = None
                    history_event = "SYS_GUIXU_COMBAT"
                elif action == "flee":
                    gap = game.player.realm_index - int(actor["realm_index"])
                    settings = self._guixu_settings()
                    chance = max(
                        float(settings.get("flee_min_chance", .04)),
                        min(
                            float(settings.get("flee_max_chance", .68)),
                            float(settings.get("flee_base_chance", .28))
                            + gap * float(settings.get("flee_realm_gap_bonus", .07)),
                        ),
                    )
                    if rng.random() < chance:
                        result, summary = "escaped", f"你摆脱了{actor['name']}（遁走率{chance:.0%}）。"
                        self._consume_guixu_days(game, dungeon, cycle, session, 1, rng)
                    else:
                        result, summary = self._guixu_fight(game, dungeon, cycle, session, actor, rng)
                    history_event = "SYS_GUIXU_FLEE"
                elif action == "recruit":
                    if len(session.get("recruited_actor_ids", [])) >= int(self._guixu_settings().get("recruit_cap", 2)):
                        raise ValueError("临时队友已经达到上限")
                    chance = max(.05, min(.82, .24 + game.player.fame / 1000 + max(0, game.player.realm_index - int(actor["realm_index"])) * .08))
                    if rng.random() < chance:
                        actor["status"] = "recruited"
                        session["recruited_actor_ids"].append(actor["actor_id"])
                        result, summary = "joined", f"{actor['name']}同意临时同行（成功率{chance:.0%}）。"
                    else:
                        result, summary = "rejected", f"{actor['name']}拒绝同行（成功率{chance:.0%}）。"
                    self._consume_guixu_days(game, dungeon, cycle, session, 1, rng)
                    history_event = "SYS_GUIXU_RECRUIT"
                else:
                    entry_id = str(payload.get("pool_entry_id", ""))
                    row = next((entry for entry in cycle.get("round_entries", []) if entry["pool_entry_id"] == entry_id), None)
                    if not row or row.get("holder_id") != actor["actor_id"] or row.get("resolution") != "held":
                        raise ValueError("对方当前并未持有这件宝物")
                    key = f"{actor['actor_id']}:{entry_id}"
                    if key in session["negotiation_attempts"]:
                        raise ValueError("本届已经为这件宝物正式议价过")
                    definition = self._guixu_entry_definition(dungeon, entry_id)
                    offer = int(payload.get("offer_stones", 0))
                    if offer <= 0:
                        raise ValueError("正式议价必须提出正数灵石报价")
                    wallet = next(
                        (int(item.quantity) for item in game.player.inventory if item.id == "spirit_stone"), 0,
                    )
                    if wallet < offer:
                        raise ValueError("你没有足够的下品灵石支付报价")
                    session["negotiation_attempts"][key] = True
                    ratio = offer / max(1.0, float(definition.get("value", 1)))
                    npc = self._find_npc(game, str(actor.get("npc_id"))) if actor.get("npc_id") else None
                    affinity = float(npc.affinity or 0) if npc else 0.0
                    chance = max(.03, min(.90, .12 + ratio * .55 + max(-.15, affinity / 400)))
                    if rng.random() < chance:
                        remove_item(game.player, "spirit_stone", offer)
                        name = self._guixu_grant_entry(game, dungeon, row, "traded")
                        result, summary = "traded", f"{actor['name']}接受报价，你以{offer}枚灵石换得{name}。"
                    else:
                        result, summary = "refused", f"{actor['name']}拒绝了报价（成交率{chance:.0%}）。"
                    self._consume_guixu_days(game, dungeon, cycle, session, 1, rng)
                    history_event = "SYS_GUIXU_NEGOTIATE"
            elif action == "trapped_cultivate":
                if not session.get("trapped"):
                    raise ValueError("只有被困后才能按年静修")
                layer = next(row for row in dungeon["layers"] if row["id"] == session["layer_id"])
                low, high = ACTIONS["cultivate"]["opportunity"]
                gain = rng.randint(low, high) * opportunity_multiplier(
                    game.player, dict(layer["qi_concentrations"]),
                )
                self._add_opportunity(
                    game.player, gain, dict(layer["qi_gain_efficiencies"]),
                )
                era_news: list[str] = []
                advance_player_age(game.player)
                self._advance_world_year(game, rng, era_news, encounters=False)
                if not game.player.alive and any(
                    record.event_id == "SYS_LIFESPAN" and record.age == game.player.age
                    for record in game.history[-3:]
                ):
                    game.history.append(HistoryRecord(
                        "SYS_GUIXU_TRAPPED_DEATH", 1, game.player.age, "坐化归墟", dungeon["id"],
                        "dead", f"你被困于{dungeon['name']}期间寿尽坐化。", {},
                        ["system", "guixu", "death"],
                    ))
                if game.player.alive and (game.player.realm_index, game.player.layer) >= tuple(dungeon["eject_rank"]):
                    game.player.location_id = dungeon["entry_location_id"]
                    game.guixu_state["player_session"] = None
                    result, summary, history_event = "breakthrough", "你突破归墟界限，被潮眼送回入口。", "SYS_GUIXU_EJECT"
                else:
                    result, summary = "cultivated", f"你在{layer['name']}静修一年，获得机缘{gain:.1f}。"
                    history_event = "SYS_GUIXU_TRAPPED_CULTIVATE"
            else:
                raise ValueError("未知归墟操作")

        game.history.append(HistoryRecord(
            history_event, 1, game.player.age, "归墟行动", action, result, summary,
            {"action": action}, ["action", "guixu", f"result:{result}"],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def _guixu_trapped_training(
        self, game_id: str, action: str, units: int = 1,
    ) -> dict[str, Any]:
        """Run only inward-facing training while the player is trapped."""
        game = self._load(game_id)
        session = (
            game.guixu_state.get("player_session")
            if isinstance(game.guixu_state, dict) else None
        )
        if not session or not session.get("trapped"):
            raise ValueError("你当前并未被困归墟")
        if action not in {"cultivate", "body_train", "sense_train", "rest"}:
            raise ValueError("被困归墟期间只能修炼、炼体、锻炼神识或调息")
        dungeon, _ = self._guixu_cycle_and_definition(game, str(session["dungeon_id"]))
        layer = next(row for row in dungeon["layers"] if row["id"] == session["layer_id"])
        rng = decode_rng(game.seed, game.rng_state)
        action_units = max(1, min(10, int(units)))
        requested_years = action_units * int(WORLD_SYSTEMS["time_units"][str(game.player.realm_index)])
        start_age = game.player.age
        total_opportunity = 0.0
        total_body = 0.0
        total_sense = 0.0
        hp_before, mp_before = game.player.hp, game.player.mp
        concentrations = dict(layer["qi_concentrations"])
        efficiencies = dict(layer["qi_gain_efficiencies"])
        for elapsed in range(requested_years):
            advance_player_age(game.player)
            low, high = ACTIONS[action]["opportunity"]
            gain = rng.randint(low, high) * opportunity_multiplier(game.player, concentrations)
            total_opportunity += self._add_opportunity(game.player, gain, efficiencies)
            if action == "body_train":
                body_gain = self._body_training_step(game.player, rng, concentrations)
                required = self._body_progress_required(game.player)
                before = game.player.body_progress
                game.player.body_progress = min(required, before + body_gain)
                total_body += game.player.body_progress - before
                if game.player.body_progress >= required:
                    game.player.awaiting_body_breakthrough = True
            elif action == "sense_train":
                sense_gain = self._sense_training_step(
                    game.player, efficiencies, concentrations,
                )
                game.player.divine_sense_experience += sense_gain
                total_sense += sense_gain
            elif action == "rest" and game.player.heart_demon > 0:
                game.player.heart_demon = max(0.0, game.player.heart_demon - .5)
            self._apply_action_resources(game.player, action, elapsed == 0)
            self._advance_world_year(game, rng, [], encounters=False)
            if game.player.alive:
                self._advance_soul_erosion_time(game, 1)
            if (
                not game.player.alive or game.pending_event
                or not (game.guixu_state.get("player_session") or {}).get("trapped")
            ):
                break

        if not game.player.alive and any(
            record.event_id == "SYS_LIFESPAN" and record.age == game.player.age
            for record in game.history[-3:]
        ):
            game.history.append(HistoryRecord(
                "SYS_GUIXU_TRAPPED_DEATH", 1, game.player.age, "坐化归墟", dungeon["id"],
                "dead", f"你被困于{dungeon['name']}期间寿尽坐化。", {},
                ["system", "guixu", "death"],
            ))
        elapsed_years = max(1, game.player.age - start_age)
        if action == "body_train":
            detail = f"炼体积累 +{total_body:.1f}，当前炼体{game.player.body_training}层"
        elif action == "sense_train":
            detail = f"神识经验 +{total_sense:.1f}，当前神识{divine_sense_level(game.player)}级"
        elif action == "rest":
            detail = (
                f"气血恢复{game.player.hp - hp_before:.0f}，"
                f"法力恢复{game.player.mp - mp_before:.0f}"
            )
        else:
            detail = f"机缘 +{total_opportunity:.1f}"
        game.history.append(HistoryRecord(
            "SYS_GUIXU_TRAPPED_TRAIN", 1, game.player.age, "困守修行", action, "completed",
            f"你在{layer['name']}闭关{elapsed_years}年，{detail}。",
            {"action": action, "years": elapsed_years, "opportunity": round(total_opportunity, 1)},
            ["action", "guixu", "trapped", action],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def assert_guixu_operation_allowed(self, game_id: str, operation: str) -> None:
        # When the DLC is disabled, let the requested operation reach ``_load``;
        # its compatibility migration safely returns an active explorer first.
        if not guixu_content_available():
            return
        game = self.store.load(game_id)
        session = game.guixu_state.get("player_session") if isinstance(game.guixu_state, dict) else None
        if not session:
            return
        allowed = {
            "guixu-action", "choice", "use-item", "equip-technique", "technique-upgrade",
            "technique-manual-merge", "settings", "formation-save", "formation-activate",
            "formation-deactivate", "formation-delete", "secret-art",
        }
        if session.get("trapped"):
            allowed.update({"advance", "breakthrough", "body-breakthrough", "sense-breakthrough"})
        if operation not in allowed:
            raise ValueError("身在归墟时无法进行外界操作")

    def _public_guixu(self, game: GameState) -> dict[str, Any]:
        self._ensure_guixu_state(game)
        if not guixu_content_available():
            return {"available": False, "dungeons": [], "session": None}
        definitions = self._guixu_definitions()
        rows = []
        for dungeon_id, dungeon in definitions.items():
            if dungeon["world"] != game.player.world:
                continue
            cycle = game.guixu_state["cycles"][dungeon_id]
            entry_key = f"{dungeon_id}:{cycle['cycle_index']}"
            location_matches = bool(
                game.player.world == dungeon["world"]
                and game.player.location_id == dungeon["entry_location_id"]
            )
            rank_matches = (
                game.player.realm_index, game.player.layer,
            ) <= tuple(dungeon["max_entry_rank"])
            not_entered = entry_key not in game.guixu_state["entered_cycles"]
            no_active_session = not game.guixu_state.get("player_session")
            phase_open = cycle["phase"] == "open"
            max_rank_name = self._npc_realm_name(SectNpc(
                "guixu-entry-limit", "", "", *map(int, dungeon["max_entry_rank"]),
                game.player.age, None, path=game.player.path, world=dungeon["world"],
            ))
            current_rank_name = self._npc_realm_name(SectNpc(
                "guixu-player-rank", game.player.name, "", game.player.realm_index,
                game.player.layer, game.player.age, game.player.lifespan,
                path=game.player.path, world=game.player.world,
            ))
            round_entries = []
            for row in cycle.get("round_entries", []):
                definition = self._guixu_entry_definition(dungeon, str(row["pool_entry_id"]))
                holder = next((actor for actor in cycle.get("roster", []) if actor["actor_id"] == row.get("holder_id")), None)
                round_entries.append({
                    **copy.deepcopy(row), "name": definition["name"], "tier": definition["tier"],
                    "category": definition["category"], "value": definition.get("value", 0),
                    "holder_name": holder.get("name") if holder else None,
                })
            rows.append({
                "id": dungeon_id, "name": dungeon["name"], "world": dungeon["world"],
                "entry_location_id": dungeon["entry_location_id"],
                "entry_location_name": self.maps.location(dungeon["world"], dungeon["entry_location_id"])["name"],
                "max_entry_rank": dungeon["max_entry_rank"], "eject_rank": dungeon["eject_rank"],
                "window_days": dungeon["window_days"], "phase": cycle["phase"],
                "cycle_index": cycle["cycle_index"], "next_open_age": cycle["next_open_age"],
                "next_announce_age": cycle["next_announce_age"], "pool_remaining": len(cycle["pool_remaining"]),
                "round_entries": round_entries, "last_report": copy.deepcopy(cycle.get("last_report")),
                "entry_requirements": {
                    "phase_open": phase_open, "location_matches": location_matches,
                    "rank_matches": rank_matches, "not_entered": not_entered,
                    "no_active_session": no_active_session,
                    "player_available": bool(game.player.alive and not game.pending_event),
                    "max_rank_name": max_rank_name, "current_rank_name": current_rank_name,
                    "suppression_active": bool(game.player.cultivation_suppression),
                },
                "can_enter": bool(
                    phase_open and location_matches and rank_matches and not_entered
                    and no_active_session and game.player.alive and not game.pending_event
                ),
            })
        session = copy.deepcopy(game.guixu_state.get("player_session"))
        if session:
            dungeon, cycle = self._guixu_cycle_and_definition(game, str(session["dungeon_id"]))
            session["dungeon_name"] = dungeon["name"]
            session["return_days"] = self._guixu_return_days(str(session["layer_id"]))
            session["layers"] = [{
                **copy.deepcopy(layer),
                "current": layer["id"] == session["layer_id"],
                "locked": layer["id"] == "secret" and not session.get("secret_unlocked"),
            } for layer in dungeon["layers"]]
            expedition_open = cycle.get("phase") == "open"
            session["actors"] = ([
                copy.deepcopy(actor) for actor in cycle.get("roster", [])
                if actor.get("layer_id") == session["layer_id"] and actor.get("status") in {"active", "recruited"}
            ] if expedition_open else [])
            session["treasures"] = ([
                row for row in next(item for item in rows if item["id"] == dungeon["id"])["round_entries"]
                if row["layer_id"] == session["layer_id"] and row["resolution"] in {"unclaimed", "held"}
            ] if expedition_open else [])
        return {"available": bool(rows or session), "dungeons": rows, "session": session}

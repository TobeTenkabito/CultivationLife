from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any
    from ...content_registry import RACE_DEFINITIONS
    from ...models import GameState, HistoryRecord, SectNpc
    from ...rules import expected_combat_power
    from ...runtime import now_iso
    from ..intrigue_system import intrigue_rules
    from .. import intrigue_system as _source
    PLAYER_ID = _source.PLAYER_ID


class IntrigueGovernanceMethods:
    def _intrigue_auto_appoint_player(
        self, game: GameState, kind: str, faction_id: str,
        record: dict[str, Any], members: list[SectNpc],
    ) -> None:
        """Let cultivation order, rather than voting rights, drive ordinary offices.

        The controller still occupies the first (leader) office.  Remaining
        offices follow the faction's cultivation order, while guest offices
        remain reserved for external retainers.  This makes a powerful member
        eligible for office even when their realm is below the independent
        decision-authority threshold.
        """
        if kind not in {"sect", "family"}:
            return
        positions = record.setdefault("positions", {})
        specs = self._intrigue_position_specs(kind)
        office_ids = [
            position_id for position_id in specs
            if position_id not in {"leader", "family_head", "guest_elder", "guest_retainer"}
        ]
        existing = next((position_id for position_id in office_ids if positions.get(position_id) == PLAYER_ID), None)
        player_is_member = self._intrigue_player_faction_id(game, kind) == faction_id and game.player.alive
        entity = self._intrigue_entity(game, kind, faction_id)
        player_is_local = not entity or entity.world == game.player.world
        if not player_is_member or not player_is_local or record.get("controller_id") == PLAYER_ID:
            if existing:
                positions[existing] = None
            record["player_auto_office"] = None
            return

        player_realm, player_layer = self._actual_player_realm(game.player)
        order = [
            (PLAYER_ID, player_realm, player_layer, self._player_intrinsic_combat_power(game.player)),
            *[
                (npc.id, npc.realm_index, npc.layer, expected_combat_power(npc.realm_index, npc.layer) * npc.combat_factor)
                for npc in members if npc.alive and not self._intrigue_is_imprisoned(game, npc.id)
            ],
        ]
        order.sort(key=lambda row: (-row[1], -row[2], -row[3], row[0]))
        player_rank = next((index + 1 for index, row in enumerate(order) if row[0] == PLAYER_ID), len(order) + 1)
        rank_limit = max(1, int(intrigue_rules().get("player_office_rank_limit", 7)))
        desired: str | None = None
        if player_rank <= rank_limit and office_ids:
            start = max(0, player_rank - 2)
            candidates = office_ids[start:] + office_ids[:start]
            rank_by_id = {row[0]: index + 1 for index, row in enumerate(order)}
            for position_id in candidates:
                if player_realm < int(specs[position_id].get("minimum_realm", 0)):
                    continue
                holder_id = positions.get(position_id)
                if not holder_id or holder_id == PLAYER_ID or rank_by_id.get(str(holder_id), 10**6) > player_rank:
                    desired = position_id
                    break

        previous = str(record.get("player_auto_office") or "") or None
        if existing and existing != desired:
            positions[existing] = None
        if desired:
            positions[desired] = PLAYER_ID
        record["player_auto_office"] = desired
        record["player_power_rank"] = player_rank
        if desired and desired != previous:
            game.history.append(HistoryRecord(
                "SYS_INTRIGUE_OFFICE_GRANTED", 1, game.player.age, "位列前席", desired, "appointed",
                f"你在{self._intrigue_faction_name(game, kind, faction_id)}修为顺位第{player_rank}，获授{specs[desired].get('name', desired)}。",
                {"kind": kind, "faction_id": faction_id, "position_id": desired, "power_rank": player_rank},
                ["intrigue", "faction", "office"],
            ))

    def _intrigue_is_imprisoned(self, game: GameState, npc_id: str) -> bool:
        if not self._intrigue_enabled():
            return False
        return npc_id in self._intrigue_state(game).get("npc_prisons", {})

    def _intrigue_decision_threshold(self, kind: str) -> int:
        return int(intrigue_rules().get("decision_thresholds", {}).get(kind, {"sect": 4, "family": 3, "race": 8}.get(kind, 99)))

    def _intrigue_has_control(self, game: GameState, kind: str, faction_id: str) -> bool:
        if kind == "race" or self._intrigue_player_faction_id(game, kind) != faction_id:
            return False
        return self._ensure_intrigue_faction(game, kind, faction_id).get("controller_id") == PLAYER_ID

    @staticmethod
    def _intrigue_player_relation(game: GameState, npc_id: str) -> dict[str, Any] | None:
        relations = [
            game.player.master, game.player.dao_companion,
            *game.player.dao_friends, *game.player.disciples,
        ]
        return next(
            (row for row in relations if row and str(row.get("id", "")) == npc_id),
            None,
        )

    def _intrigue_position_specs(self, kind: str) -> dict[str, dict[str, Any]]:
        return dict(intrigue_rules().get("positions", {}).get(kind, {}))

    def _intrigue_faction_name(self, game: GameState, kind: str, faction_id: str) -> str:
        if kind == "race":
            return str(RACE_DEFINITIONS.get(faction_id, {}).get("name", faction_id))
        entity = self._intrigue_entity(game, kind, faction_id)
        return entity.name if entity else faction_id

    def intrigue_personnel_action(
        self, game_id: str, kind: str, action: str, npc_id: str,
        position_id: str = "", years: int = 1, reason: str = "",
    ) -> dict[str, Any]:
        game = self._load(game_id)
        if not self._intrigue_enabled():
            raise ValueError("《明争暗斗：合纵连横》DLC 尚未启用")
        faction_id = self._intrigue_player_faction_id(game, kind)
        if not faction_id or not self._intrigue_has_control(game, kind, faction_id):
            raise ValueError("你没有该势力的控制权")
        if game.pending_event or game.player.imprisonment:
            raise ValueError("当前状态无法处理势力人事")
        record = self._ensure_intrigue_faction(game, kind, faction_id)
        npc = self._intrigue_find_npc(game, npc_id)
        member_ids = {row.id for row in self._intrigue_members(game, kind, faction_id)}
        if not npc or npc.id not in member_ids or not npc.alive:
            raise ValueError("目标不是在册的存活成员")
        if npc.id == record.get("controller_id"):
            raise ValueError("不能对当前控制顺位第一直接执行此操作")
        summary = ""
        if action == "appoint":
            specs = self._intrigue_position_specs(kind)
            if position_id not in specs or position_id in {"leader", "family_head"}:
                raise ValueError("该职位不可由此处任命")
            if npc.realm_index < int(specs[position_id].get("minimum_realm", 0)):
                raise ValueError("目标修为尚未达到职位要求")
            if self._intrigue_is_imprisoned(game, npc.id):
                raise ValueError("囚犯不能担任职位")
            for pid, holder in list(record["positions"].items()):
                if holder == npc.id:
                    record["positions"][pid] = None
            former = record["positions"].get(position_id)
            if former and former != npc.id:
                old = self._intrigue_find_npc(game, str(former))
                if old:
                    old.affinity = float(old.affinity or 0) - 8
                record["unrest"] = min(100.0, float(record.get("unrest", 0)) + 3)
            record["positions"][position_id] = npc.id
            npc.affinity = min(
                100.0, float(npc.affinity or 0) + self._sage_affinity_gain(game.player, 5),
            )
            summary = f"你任命{npc.name}为{specs[position_id]['name']}。"
        elif action == "dismiss":
            held = next((pid for pid, holder in record["positions"].items() if holder == npc.id), None)
            if not held:
                raise ValueError("目标当前没有正式职位")
            record["positions"][held] = None
            npc.affinity = float(npc.affinity or 0) - 12
            record["unrest"] = min(100.0, float(record.get("unrest", 0)) + 5)
            summary = f"你撤去了{npc.name}的{self._intrigue_position_specs(kind).get(held, {}).get('name', '职位')}，此举引发不满。"
        elif action == "expel":
            for pid, holder in list(record["positions"].items()):
                if holder == npc.id:
                    record["positions"][pid] = None
            entity = self._intrigue_entity(game, kind, faction_id)
            if entity:
                entity.npcs = [row for row in entity.npcs if row.id != npc.id]
            npc.faction_id = None
            npc.affinity = float(npc.affinity or 0) - 30
            game.world_npcs.setdefault(npc.id, npc)
            record["unrest"] = min(100.0, float(record.get("unrest", 0)) + 12)
            summary = f"你将{npc.name}逐出{self._intrigue_faction_name(game, kind, faction_id)}；对方已心生怨恨。"
        elif action == "imprison":
            if self._intrigue_is_imprisoned(game, npc.id):
                raise ValueError("目标已经被关押")
            years = max(1, min(1000, int(years)))
            entry = {"prisoner_id": npc.id, "name": npc.name, "faction_id": faction_id, "kind": kind,
                     "sentence_remaining": years, "sentence_years": years,
                     "reason": (reason.strip()[:40] or "违抗势力法令"), "imprisoned_by": PLAYER_ID}
            record["prison"].append(entry)
            self._intrigue_state(game)["npc_prisons"][npc.id] = self._intrigue_key(kind, faction_id)
            npc.affinity = float(npc.affinity or 0) - 25
            record["fear"] = min(100.0, float(record.get("fear", 0)) + 12)
            record["unrest"] = min(100.0, float(record.get("unrest", 0)) + 7)
            summary = f"你以“{entry['reason']}”为由，将{npc.name}关押 {years} 年。"
        elif action == "release":
            before = len(record["prison"])
            record["prison"] = [row for row in record["prison"] if row.get("prisoner_id") != npc.id]
            if len(record["prison"]) == before:
                raise ValueError("目标不在本势力监狱")
            self._intrigue_state(game)["npc_prisons"].pop(npc.id, None)
            record["fear"] = max(0.0, float(record.get("fear", 0)) - 3)
            summary = f"你下令释放{npc.name}。"
        elif action in {"reward", "punish"}:
            delta = 10 if action == "reward" else -10
            record["member_contribution"][npc.id] = int(record["member_contribution"].get(npc.id, 0)) + delta
            npc.affinity = max(-100.0, min(100.0, float(npc.affinity or 0) + (6 if action == "reward" else -8)))
            if action == "punish":
                record["fear"] = min(100.0, float(record.get("fear", 0)) + 3)
            summary = f"你{'奖赏' if action == 'reward' else '惩处'}了{npc.name}，其内部贡献{'增加' if delta > 0 else '扣除'} {abs(delta)}。"
        else:
            raise ValueError("未知人事操作")
        game.history.append(HistoryRecord(
            "SYS_INTRIGUE_PERSONNEL", 1, game.player.age, "势力人事", action, "executed", summary,
            {"kind": kind, "faction_id": faction_id, "npc_id": npc.id}, ["system", "intrigue", kind, "faction"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _intrigue_pressure_position_occupied(self, game: GameState, faction_id: str) -> bool:
        """DLC pressure requires an actually occupied office, never a phantom rival."""
        if not self._intrigue_enabled():
            return True
        record = self._ensure_intrigue_faction(game, "sect", faction_id)
        specs = self._intrigue_position_specs("sect")
        relevant = [pid for pid, spec in specs.items() if pid not in {"leader", "guest_elder"} and game.player.realm_index >= int(spec.get("minimum_realm", 0))]
        return any(record.get("positions", {}).get(pid) for pid in relevant)

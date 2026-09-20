from __future__ import annotations

import copy
import random
import uuid
from typing import Any

from .content_registry import (
    FACTION_SYSTEMS, PATH_NAMES, RACE_DEFINITIONS, REALMS, ROOT_DEFINITIONS,
    WORLD_SYSTEMS,
)
from .models import GameState, HistoryRecord, SectNpc, SectState
from .npc_system import attitude_label
from .rules import expected_combat_power
from .runtime import decode_rng, encode_rng, now_iso
from .world_state import race_pair


PLAYER_ID = "player"
PERSONALITY_LABELS = {
    "paranoid": "偏执", "fanatical": "狂热", "cautious": "谨慎", "smooth": "圆滑",
    "forceful": "强硬", "generous": "宽厚", "suspicious": "多疑", "greedy": "贪婪",
    "restrained": "克制", "warlike": "好战", "conservative": "保守", "open": "开放",
}
STYLE_LABELS = {
    "balance": "平衡型", "internal": "内政型", "diplomacy": "外交型", "military": "军事型",
}
RESOLUTION_LABELS = {
    "declare_war": "宣战", "make_peace": "停战", "form_alliance": "缔结联盟",
    "break_alliance": "解除联盟", "intervene_war": "介入战争",
    "mass_recruitment": "大规模招收成员", "relocate": "迁移主要驻地",
    "investment": "重大资源投资", "policy": "长期政策",
    "disciple_recruitment": "扩招徒弟",
}


def intrigue_rules() -> dict[str, Any]:
    value = WORLD_SYSTEMS.get("intrigue_dlc", {})
    return value if isinstance(value, dict) and value.get("enabled") else {}


def intrigue_content_available() -> bool:
    return bool(intrigue_rules())


class IntrigueSystemMixin:
    """Generic runtime hook for 《明争暗斗：合纵连横》.

    The rules live in the DLC's world.json overlay.  Without that document all
    methods become inert and existing faction behavior stays untouched.
    """

    @staticmethod
    def _intrigue_enabled() -> bool:
        return intrigue_content_available()

    @staticmethod
    def _intrigue_state(game: GameState) -> dict[str, Any]:
        state = game.intrigue_state
        state.setdefault("schema_version", 1)
        state.setdefault("npcs", {})
        state.setdefault("factions", {})
        state.setdefault("resolutions", [])
        state.setdefault("npc_prisons", {})
        state.setdefault("pending_guest_invitation", None)
        state.setdefault("sequence", 0)
        state.setdefault("ai_cursor", 0)
        return state

    @staticmethod
    def _intrigue_key(kind: str, faction_id: str) -> str:
        return f"{kind}:{faction_id}"

    def _intrigue_entity(self, game: GameState, kind: str, faction_id: str) -> SectState | None:
        if kind == "sect":
            return game.sects.get(faction_id)
        if kind == "family" and game.family and game.family.id == faction_id:
            return game.family
        return None

    def _intrigue_find_npc(self, game: GameState, npc_id: str) -> SectNpc | None:
        if game.family:
            member = next((row for row in game.family.npcs if row.id == npc_id), None)
            if member:
                return member
        return self._find_npc(game, npc_id)

    def _intrigue_members(self, game: GameState, kind: str, faction_id: str) -> list[SectNpc]:
        if kind == "sect":
            entity = game.sects.get(faction_id)
            return self._sect_members(game, entity) if entity and not entity.extinct else []
        if kind == "family":
            return list(game.family.npcs) if game.family and game.family.id == faction_id and not game.family.extinct else []
        if kind == "race":
            return [npc for npc in self._all_world_npcs(game) if npc.race == faction_id and npc.world == game.player.world]
        return []

    def _intrigue_player_faction_id(self, game: GameState, kind: str) -> str | None:
        if kind == "sect":
            return game.player.faction_id
        if kind == "family":
            return (
                game.family.id
                if game.family and not game.family.extinct and game.family.world == game.player.world
                else None
            )
        if kind == "race":
            return self._player_allegiance_race(game.player)
        return None

    def _ensure_intrigue_personality(self, game: GameState, npc: SectNpc) -> dict[str, Any]:
        state = self._intrigue_state(game)
        existing = state["npcs"].get(npc.id)
        if isinstance(existing, dict) and existing.get("primary") in PERSONALITY_LABELS:
            return existing
        rng = random.Random(f"intrigue-personality:{game.seed}:{npc.id}")
        keys = list(PERSONALITY_LABELS)
        primary = rng.choice(keys)
        secondary = rng.choice([key for key in keys if key != primary]) if rng.random() < 0.22 else None
        record = {"primary": primary, "secondary": secondary, "governance_style": None}
        state["npcs"][npc.id] = record
        return record

    def _intrigue_governance_style(self, game: GameState, npc: SectNpc) -> str:
        record = self._ensure_intrigue_personality(game, npc)
        if record.get("governance_style") in STYLE_LABELS:
            return str(record["governance_style"])
        weights = {"balance": 25.0, "internal": 25.0, "diplomacy": 25.0, "military": 25.0}
        shifts = {
            "paranoid": {"balance": 10, "military": 8, "diplomacy": -8},
            "fanatical": {"military": 16, "balance": -6},
            "cautious": {"balance": 14, "military": -10},
            "smooth": {"diplomacy": 16, "military": -6},
            "forceful": {"military": 14, "internal": 4},
            "generous": {"internal": 10, "diplomacy": 8},
            "suspicious": {"balance": 10, "diplomacy": -8},
            "greedy": {"internal": 12, "military": 5},
            "restrained": {"balance": 13, "military": -8},
            "warlike": {"military": 22, "diplomacy": -10},
            "conservative": {"internal": 10, "balance": 10, "military": -5},
            "open": {"diplomacy": 13, "internal": 7},
        }
        for trait in (record.get("primary"), record.get("secondary")):
            for style, change in shifts.get(str(trait), {}).items():
                weights[style] = max(1.0, weights[style] + change)
        rng = random.Random(f"intrigue-style:{game.seed}:{npc.id}")
        record["governance_style"] = rng.choices(list(weights), weights=list(weights.values()), k=1)[0]
        return str(record["governance_style"])

    def _ensure_intrigue_faction(self, game: GameState, kind: str, faction_id: str) -> dict[str, Any]:
        state = self._intrigue_state(game)
        key = self._intrigue_key(kind, faction_id)
        record = state["factions"].setdefault(key, {
            "kind": kind, "id": faction_id, "controller_id": None, "positions": {},
            "guests": [], "prison": [], "member_contribution": {}, "unrest": 0.0,
            "fear": 0.0, "resources": 0, "policy": "balance",
        })
        record.setdefault("positions", {})
        record.setdefault("guests", [])
        record.setdefault("prison", [])
        record.setdefault("member_contribution", {})
        members = [npc for npc in self._intrigue_members(game, kind, faction_id) if npc.alive]
        for npc in members:
            self._ensure_intrigue_personality(game, npc)
        if kind == "race":
            record["controller_id"] = None
            return record
        entity = self._intrigue_entity(game, kind, faction_id)
        controller = str(record.get("controller_id") or "")
        valid_npc_ids = {npc.id for npc in members}
        player_controls = bool(
            entity and entity.world == game.player.world
            and entity.founded_by_player and entity.founder_player_id == game.id and game.player.alive
        )
        player_is_member = self._intrigue_player_faction_id(game, kind) == faction_id and game.player.alive
        player_realm, player_layer = self._actual_player_realm(game.player)
        npc_first = max(((npc.realm_index, npc.layer) for npc in members), default=(-1, -1))
        if player_is_member and (player_realm, player_layer) >= npc_first:
            player_controls = True
        if player_controls:
            controller = PLAYER_ID
        elif controller == PLAYER_ID or controller not in valid_npc_ids:
            controller = max(members, key=lambda row: (row.realm_index, row.layer, -row.age)).id if members else ""
        record["controller_id"] = controller or None
        position_ids = list(intrigue_rules().get("positions", {}).get(kind, {}))
        leader_id = position_ids[0] if position_ids else ""
        if leader_id:
            record["positions"][leader_id] = controller or None
        if not record.get("positions_initialized"):
            if controller != PLAYER_ID:
                claimed = {controller}
                ordered = sorted(members, key=lambda row: (-row.realm_index, -row.layer, row.age, row.id))
                for position_id, spec in self._intrigue_position_specs(kind).items():
                    if position_id == leader_id or position_id in {"guest_elder", "guest_retainer"}:
                        continue
                    candidate = next((npc for npc in ordered if npc.id not in claimed and npc.realm_index >= int(spec.get("minimum_realm", 0))), None)
                    if candidate:
                        record["positions"][position_id] = candidate.id
                        claimed.add(candidate.id)
            record["positions_initialized"] = True
        self._intrigue_auto_appoint_player(game, kind, faction_id, record, members)
        if controller and controller != PLAYER_ID:
            ruler = next((npc for npc in members if npc.id == controller), None)
            if ruler:
                record["policy"] = self._intrigue_governance_style(game, ruler)
        return record

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

    def _intrigue_has_decision_authority(self, game: GameState, kind: str, faction_id: str, member_id: str = PLAYER_ID) -> bool:
        threshold = self._intrigue_decision_threshold(kind)
        if member_id == PLAYER_ID:
            own_id = self._intrigue_player_faction_id(game, kind)
            realm_index, _ = self._actual_player_realm(game.player)
            entity = self._intrigue_entity(game, kind, faction_id)
            same_world = not entity or entity.world == game.player.world
            return bool(own_id == faction_id and same_world and game.player.alive and realm_index >= threshold)
        npc = self._intrigue_find_npc(game, member_id)
        return bool(npc and npc.alive and npc.realm_index >= threshold and not self._intrigue_is_imprisoned(game, npc.id))

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

    def _intrigue_can_invite_guest(
        self, game: GameState, npc_id: str, kind: str = "sect",
    ) -> bool:
        if not self._intrigue_enabled() or not npc_id or kind == "race":
            return False
        faction_id = self._intrigue_player_faction_id(game, kind)
        if not faction_id or not self._intrigue_has_control(game, kind, faction_id):
            return False
        record = self._ensure_intrigue_faction(game, kind, faction_id)
        if any(str(row.get("npc_id", "")) == npc_id for row in record.get("guests", [])):
            return False
        if any(row.id == npc_id for row in self._intrigue_members(game, kind, faction_id)):
            return False
        npc = self._intrigue_find_npc(game, npc_id)
        relation = self._intrigue_player_relation(game, npc_id)
        source: Any = npc or relation
        if not source:
            return False
        alive = source.alive if isinstance(source, SectNpc) else bool(source.get("alive", True))
        world = source.world if isinstance(source, SectNpc) else str(source.get("world", game.player.world))
        if not alive or world != game.player.world or self._intrigue_is_imprisoned(game, npc_id):
            return False
        npc_affinity = float(npc.affinity or 0) if npc else -100.0
        relation_affinity = float(relation.get("affinity", 0)) if relation else -100.0
        is_friend = any(str(row.get("id", "")) == npc_id for row in game.player.dao_friends)
        return is_friend or max(npc_affinity, relation_affinity) >= 30.0

    def _intrigue_position_specs(self, kind: str) -> dict[str, dict[str, Any]]:
        return dict(intrigue_rules().get("positions", {}).get(kind, {}))

    def _intrigue_faction_name(self, game: GameState, kind: str, faction_id: str) -> str:
        if kind == "race":
            return str(RACE_DEFINITIONS.get(faction_id, {}).get("name", faction_id))
        entity = self._intrigue_entity(game, kind, faction_id)
        return entity.name if entity else faction_id

    def _intrigue_public_member(self, game: GameState, npc: SectNpc, record: dict[str, Any]) -> dict[str, Any]:
        personality = self._ensure_intrigue_personality(game, npc)
        position = next((pid for pid, holder in record.get("positions", {}).items() if holder == npc.id), None)
        spec = self._intrigue_position_specs(record["kind"]).get(position or "", {})
        return {
            "id": npc.id, "name": npc.name, "realm_index": npc.realm_index,
            "realm_name": f"{REALMS[npc.realm_index].name}{npc.layer}层" if npc.realm_index else REALMS[0].name,
            "affinity": round(float(npc.affinity or 0), 1), "attitude": attitude_label(float(npc.affinity or 0), 0),
            "primary": PERSONALITY_LABELS[personality["primary"]],
            "secondary": PERSONALITY_LABELS.get(personality.get("secondary"), ""),
            "governance_style": STYLE_LABELS.get(personality.get("governance_style"), ""),
            "position_id": position, "position": spec.get("name", npc.title or "普通成员"),
            "decision_authority": self._intrigue_has_decision_authority(game, record["kind"], record["id"], npc.id),
            "imprisoned": self._intrigue_is_imprisoned(game, npc.id),
            "contribution": int(record.get("member_contribution", {}).get(npc.id, 0)),
        }

    @staticmethod
    def _intrigue_recruitment_config() -> dict[str, Any]:
        return dict(intrigue_rules().get("disciple_recruitment", {}))

    def _intrigue_recruitment_realm_options(self, world: str) -> list[int]:
        distributions = FACTION_SYSTEMS.get("recruitment_distribution_by_world", {})
        rows = distributions.get(world, FACTION_SYSTEMS.get("recruitment_distribution", []))
        threshold = self._intrigue_decision_threshold("sect")
        return sorted({
            int(row.get("realm_index", 0)) for row in rows
            if 0 <= int(row.get("realm_index", 0)) < threshold
        })

    def _normalize_intrigue_recruitment_filters(
        self, game: GameState, filters: dict[str, Any] | None,
    ) -> dict[str, Any]:
        raw = filters if isinstance(filters, dict) else {}
        root = str(raw.get("spirit_root", "any"))
        if root not in {"any", "heavenly"}:
            raise ValueError("灵根筛选只能选择不筛选或天灵根")
        realm_raw = raw.get("realm_index", "any")
        if realm_raw in {None, "", "any"}:
            realm: int | None = None
        else:
            try:
                realm = int(realm_raw)
            except (TypeError, ValueError) as error:
                raise ValueError("修为筛选无效") from error
            allowed_realms = self._intrigue_recruitment_realm_options(game.player.world)
            if realm not in allowed_realms:
                raise ValueError("所选修为不属于当前界面可招收的弟子境界，或已经拥有决策权")
        path = str(raw.get("path", "any"))
        if path != "any" and path not in PATH_NAMES:
            raise ValueError("修炼功法路线筛选无效")
        combat = str(raw.get("combat", "any"))
        combat_filters = self._intrigue_recruitment_config().get("combat_filters", {})
        if combat not in combat_filters:
            raise ValueError("战斗力筛选无效")
        gender = str(raw.get("gender", "any"))
        if gender not in {"any", "male", "female"}:
            raise ValueError("性别筛选无效")
        return {
            "spirit_root": root, "realm_index": realm, "path": path,
            "combat": combat, "gender": gender,
        }

    def _intrigue_recruitment_filter_summary(self, filters: dict[str, Any]) -> str:
        combat_filters = self._intrigue_recruitment_config().get("combat_filters", {})
        realm = filters.get("realm_index")
        return " · ".join((
            "天灵根" if filters.get("spirit_root") == "heavenly" else "灵根不限",
            REALMS[int(realm)].name if realm is not None else "修为不限",
            PATH_NAMES.get(str(filters.get("path")), "功法不限"),
            str(combat_filters.get(str(filters.get("combat")), {}).get("name", "战力不限")),
            {"male": "男修", "female": "女修"}.get(str(filters.get("gender")), "性别不限"),
        ))

    def _generate_intrigue_recruitment_session(
        self, game: GameState, faction_id: str, filters: dict[str, Any], rng: random.Random,
    ) -> dict[str, Any]:
        sect = game.sects.get(faction_id)
        if not sect or sect.extinct:
            raise ValueError("当前宗门已经不存在")
        config = self._intrigue_recruitment_config()
        maximum = max(1, min(5, int(config.get("max_candidates", 5))))
        pool_low, pool_high = config.get("applicant_pool", [6, 12])
        applicant_count = rng.randint(max(1, int(pool_low)), max(int(pool_low), int(pool_high)))
        appearance_chance = max(0.05, min(1.0, float(config.get("appearance_chance", .78))))
        combat_spec = config.get("combat_filters", {}).get(str(filters.get("combat")), {})
        minimum_ratio = max(0.0, min(1.5, float(combat_spec.get("minimum_ratio", 0))))
        allowed_realms = set(self._intrigue_recruitment_realm_options(sect.world))
        state = self._intrigue_state(game)
        state["recruitment_sequence"] = int(state.get("recruitment_sequence", 0)) + 1
        sequence = int(state["recruitment_sequence"])
        surnames = ["顾", "叶", "陆", "楚", "白", "谢", "云", "林", "江", "闻", "苏", "沈"]
        given = ["玄", "宁", "川", "微", "岳", "霜", "澄", "昭", "离", "砚", "青", "禾"]
        candidates: list[dict[str, Any]] = []
        for attempt in range(applicant_count):
            if rng.random() >= appearance_chance:
                continue
            realm_index = self._recruit_realm_index(rng.random(), sect.world)
            if realm_index not in allowed_realms:
                continue
            if filters.get("realm_index") is not None and realm_index != int(filters["realm_index"]):
                continue
            path = self._random_npc_path(sect.id, rng)
            if filters.get("path") != "any" and path != filters.get("path"):
                continue
            spirit_root = self._random_npc_root(realm_index, rng) if realm_index else "none"
            if (
                filters.get("spirit_root") == "heavenly"
                and ROOT_DEFINITIONS.get(spirit_root, {}).get("tier") != "天灵根"
            ):
                continue
            gender = rng.choice(("male", "female"))
            if filters.get("gender") != "any" and gender != filters.get("gender"):
                continue
            layer = 1 if realm_index == 0 else rng.randint(1, REALMS[realm_index].layers)
            age, lifespan = self._roll_recruit_age_lifespan(realm_index, path, rng, young=True)
            npc = SectNpc(
                id=f"{sect.id}_disciple_{sequence}_{attempt}",
                name=rng.choice(surnames) + rng.choice(given), title="候选弟子",
                realm_index=realm_index, layer=layer, age=age, lifespan=lifespan,
                spirit_root=spirit_root, path=path,
                race=sect.allegiance_race or game.player.race, world=sect.world,
                affinity=rng.uniform(8, 26), combat_factor=rng.uniform(.68, 1.34),
                faction_id=sect.id, gender=gender,
            )
            npc.treasure_item_id = self._select_npc_treasure(npc, rng)
            power = self._npc_power(npc)
            ratio = power / max(1.0, expected_combat_power(realm_index, layer))
            if ratio < minimum_ratio:
                continue
            candidates.append({
                "npc": npc.to_dict(), "combat_power": round(power, 1),
                "combat_ratio": round(ratio, 3),
            })
            if len(candidates) >= maximum:
                break
        return {
            "id": f"disciple_recruitment_{sequence}",
            "created_unit": game.diplomacy_unit,
            "filters": copy.deepcopy(filters), "filter_summary": self._intrigue_recruitment_filter_summary(filters),
            "candidates": candidates,
            "message": (
                f"共有 {len(candidates)} 名散修通过初筛，请任意选择录取。"
                if candidates else "宗门要求太苛刻，暂无散修符合。"
            ),
        }

    def _public_intrigue_recruitment(
        self, game: GameState, faction_id: str, record: dict[str, Any],
    ) -> dict[str, Any]:
        config = self._intrigue_recruitment_config()
        pending = record.get("pending_recruitment")
        public_pending = None
        if isinstance(pending, dict):
            rows = []
            for candidate in pending.get("candidates", []):
                npc = SectNpc.from_dict(candidate["npc"])
                rows.append({
                    "id": npc.id, "name": npc.name,
                    "realm_index": npc.realm_index,
                    "realm_name": REALMS[npc.realm_index].name if npc.realm_index == 0 else f"{REALMS[npc.realm_index].name}{npc.layer}层",
                    "spirit_root": npc.spirit_root, "spirit_root_name": self._npc_root_name(npc.spirit_root),
                    "path": npc.path, "path_name": PATH_NAMES.get(npc.path, npc.path),
                    "gender": npc.gender, "gender_name": "男" if npc.gender == "male" else "女",
                    "age": npc.age, "lifespan": npc.lifespan,
                    "combat_power": float(candidate.get("combat_power", self._npc_power(npc))),
                    "combat_ratio": float(candidate.get("combat_ratio", 0)),
                })
            public_pending = {
                "id": pending.get("id"), "message": pending.get("message"),
                "filter_summary": pending.get("filter_summary"), "candidates": rows,
            }
        return {
            "available": self._intrigue_has_decision_authority(game, "sect", faction_id),
            "max_candidates": min(5, int(config.get("max_candidates", 5))),
            "pending": public_pending,
            "spirit_root_options": [
                {"id": "any", "name": "不筛选"}, {"id": "heavenly", "name": "天灵根"},
            ],
            "realm_options": [
                {"id": "any", "name": "不筛选"},
                *[{"id": str(index), "name": REALMS[index].name} for index in self._intrigue_recruitment_realm_options(game.player.world)],
            ],
            "path_options": [{"id": "any", "name": "不筛选"}, *[
                {"id": path, "name": name} for path, name in PATH_NAMES.items()
            ]],
            "combat_options": [
                {"id": key, "name": str(value.get("name", key))}
                for key, value in config.get("combat_filters", {}).items()
            ],
            "gender_options": [
                {"id": "any", "name": "不筛选"}, {"id": "male", "name": "男"}, {"id": "female", "name": "女"},
            ],
        }

    def _public_guest_invitation(self, game: GameState) -> dict[str, Any] | None:
        invitation = self._intrigue_state(game).get("pending_guest_invitation")
        if not isinstance(invitation, dict):
            return None
        entity = self._intrigue_entity(
            game, str(invitation.get("kind", "")), str(invitation.get("faction_id", "")),
        )
        if game.debug_world_news or (entity and not entity.extinct and entity.world == game.player.world):
            return copy.deepcopy(invitation)
        return None

    def _public_intrigue_system(self, game: GameState) -> dict[str, Any]:
        if not self._intrigue_enabled():
            return {"enabled": False, "name": "明争暗斗：合纵连横"}
        sections: list[dict[str, Any]] = []
        for kind in ("sect", "family", "race"):
            if kind == "race" and not self._world_supports(game.player.world, "races"):
                continue
            faction_id = self._intrigue_player_faction_id(game, kind)
            if game.debug_world_news and kind == "family" and game.family and not game.family.extinct:
                faction_id = game.family.id
            if not faction_id:
                continue
            entity = self._intrigue_entity(game, kind, faction_id)
            if entity and (entity.extinct or (entity.world != game.player.world and not game.debug_world_news)):
                continue
            record = self._ensure_intrigue_faction(game, kind, faction_id)
            members = [self._intrigue_public_member(game, npc, record) for npc in self._intrigue_members(game, kind, faction_id) if npc.alive]
            if kind == "race" and self._intrigue_has_decision_authority(game, kind, faction_id):
                player_realm, player_layer = self._actual_player_realm(game.player)
                player_position = next(
                    (position_id for position_id, holder_id in record.get("positions", {}).items() if holder_id == PLAYER_ID),
                    None,
                )
                player_position_name = (
                    self._intrigue_position_specs(kind).get(player_position, {}).get("name")
                    if player_position else None
                )
                members.append({
                    "id": PLAYER_ID, "name": game.player.name, "realm_index": player_realm,
                    "realm_name": (
                        f"{REALMS[player_realm].name}{player_layer}层"
                        if player_realm else REALMS[0].name
                    ),
                    "affinity": None, "attitude": "本人", "primary": "玩家本人",
                    "secondary": "", "governance_style": "", "position_id": player_position,
                    "position": player_position_name or ("种族议事成员" if kind == "race" else "普通成员"),
                    "decision_authority": True,
                    "imprisoned": False, "contribution": 0, "is_player": True,
                })
            members.sort(key=lambda row: (-row["realm_index"], -int(row.get("layer", 0)), row["name"]))
            positions = []
            for position_id, spec in self._intrigue_position_specs(kind).items():
                holder_id = record.get("positions", {}).get(position_id)
                if holder_id == PLAYER_ID:
                    holder_name = game.player.name
                else:
                    holder = self._intrigue_find_npc(game, str(holder_id or ""))
                    holder_name = holder.name if holder else "空缺"
                positions.append({"id": position_id, **copy.deepcopy(spec), "holder_id": holder_id, "holder_name": holder_name})
            guests = []
            for guest in record.get("guests", []):
                npc = self._intrigue_find_npc(game, str(guest.get("npc_id", "")))
                name = game.player.name if guest.get("npc_id") == PLAYER_ID else npc.name if npc else str(guest.get("name", "失联客卿"))
                guests.append({**copy.deepcopy(guest), "name": name})
            candidates = []
            if kind != "race" and self._intrigue_has_control(game, kind, faction_id):
                sources: dict[str, Any] = {npc.id: npc for npc in self._all_world_npcs(game)}
                for relation in [
                    game.player.master, game.player.dao_companion,
                    *game.player.dao_friends, *game.player.disciples,
                ]:
                    if relation:
                        sources.setdefault(str(relation.get("id", "")), relation)
                for npc_id, source in sources.items():
                    if not self._intrigue_can_invite_guest(game, npc_id, kind):
                        continue
                    relation = self._intrigue_player_relation(game, npc_id)
                    if isinstance(source, SectNpc):
                        name, realm_index = source.name, source.realm_index
                        affinity = float(source.affinity or 0)
                    else:
                        name = str(source.get("name", "无名修士"))
                        realm_index = int(source.get("realm_index", 0))
                        affinity = float(source.get("affinity", 0))
                    if relation:
                        affinity = max(affinity, float(relation.get("affinity", 0)))
                    candidates.append({
                        "id": npc_id, "name": name, "affinity": round(affinity, 1),
                        "realm_index": realm_index,
                        "relationship": "道友" if any(str(row.get("id", "")) == npc_id for row in game.player.dao_friends) else "故交",
                    })
                candidates.sort(key=lambda row: (-row["affinity"], -row["realm_index"]))
            sections.append({
                "kind": kind, "kind_name": {"sect": "宗门", "family": "家族", "race": "种族"}[kind],
                "id": faction_id, "name": self._intrigue_faction_name(game, kind, faction_id),
                "control_authority": self._intrigue_has_control(game, kind, faction_id),
                "decision_authority": self._intrigue_has_decision_authority(game, kind, faction_id),
                "decision_threshold": self._intrigue_decision_threshold(kind),
                "controller_name": game.player.name if record.get("controller_id") == PLAYER_ID else next((row["name"] for row in members if row["id"] == record.get("controller_id")), "无"),
                "policy": STYLE_LABELS.get(record.get("policy"), "平衡型"), "policy_id": record.get("policy", "balance"),
                "unrest": round(float(record.get("unrest", 0)), 1), "fear": round(float(record.get("fear", 0)), 1),
                "positions": positions, "members": members, "guests": guests,
                "player_power_rank": record.get("player_power_rank"),
                "player_office_id": record.get("player_auto_office"),
                "guest_candidates": candidates[:16], "prison": copy.deepcopy(record.get("prison", [])),
                "positionless_race": kind == "race",
                "resolution_targets": (
                    [{"id": row.id, "name": row.name} for row in game.sects.values()
                     if not row.extinct and row.id != faction_id and row.world == game.player.world]
                    if kind == "sect" else
                    [{"id": race_id, "name": definition.get("name", race_id)}
                     for race_id, definition in RACE_DEFINITIONS.items()
                     if race_id != faction_id and game.player.world in definition.get("worlds", [])]
                    if kind == "race" else []
                ),
                "war_targets": [
                    {"id": str(war.get("id", "")), "name": f"{war.get('attacker_id')} 对 {war.get('defender_id')}"}
                    for war in game.wars if war.get("status") in {"active", "peace_ready"}
                ],
                "disciple_recruitment": (
                    self._public_intrigue_recruitment(game, faction_id, record)
                    if kind == "sect" else None
                ),
            })
        recent = []
        for row in reversed(self._intrigue_state(game).get("resolutions", [])[-48:]):
            entity = self._intrigue_entity(game, str(row.get("kind", "")), str(row.get("faction_id", "")))
            if game.debug_world_news or not entity or entity.world == game.player.world:
                recent.append(copy.deepcopy(row))
            if len(recent) >= 16:
                break
        player_guest_roles = []
        for record in self._intrigue_state(game).get("factions", {}).values():
            if any(row.get("npc_id") == PLAYER_ID for row in record.get("guests", [])):
                entity = self._intrigue_entity(game, str(record.get("kind", "")), str(record.get("id", "")))
                if not game.debug_world_news and entity and entity.world != game.player.world:
                    continue
                player_guest_roles.append({
                    "kind": record.get("kind"), "faction_id": record.get("id"),
                    "faction_name": self._intrigue_faction_name(game, str(record.get("kind")), str(record.get("id"))),
                    "title": "卿族" if record.get("kind") == "race" else "供奉" if record.get("kind") == "family" else "客卿长老",
                })
        return {
            "enabled": True, "name": "明争暗斗：合纵连横", "sections": sections,
            "resolutions": recent,
            "pending_guest_invitation": self._public_guest_invitation(game),
            "player_guest_roles": player_guest_roles,
            "resolution_types": RESOLUTION_LABELS, "styles": STYLE_LABELS,
            "available_worlds": [
                {"id": world_id, "name": WORLD_SYSTEMS.get("world_names", {}).get(world_id, world_id)}
                for world_id, profile in WORLD_SYSTEMS.get("world_profiles", {}).items() if profile.get("enabled", True)
            ],
        }

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

    def intrigue_guest_action(self, game_id: str, kind: str, action: str, npc_id: str = "") -> dict[str, Any]:
        game = self._load(game_id)
        if not self._intrigue_enabled():
            raise ValueError("《明争暗斗：合纵连横》DLC 尚未启用")
        state = self._intrigue_state(game)
        rng = decode_rng(game.seed, game.rng_state)
        if action in {"accept_invitation", "decline_invitation"}:
            invitation = state.get("pending_guest_invitation")
            if not invitation:
                raise ValueError("当前没有待回应的客卿邀请")
            entity = self._intrigue_entity(game, str(invitation["kind"]), str(invitation["faction_id"]))
            if not entity or entity.extinct or entity.world != game.player.world:
                state["pending_guest_invitation"] = None
                game.updated_at = now_iso()
                self.store.save(game)
                raise ValueError("这份客卿邀请来自其他界面，已经失效")
            record = self._ensure_intrigue_faction(game, str(invitation["kind"]), str(invitation["faction_id"]))
            if action == "accept_invitation":
                record["guests"].append({"npc_id": PLAYER_ID, "name": game.player.name, "defense_required": True, "offense_opt_in": False})
                summary = f"你接受了{invitation['faction_name']}的{invitation['title']}之邀。"
            else:
                summary = f"你谢绝了{invitation['faction_name']}的{invitation['title']}之邀。"
            state["pending_guest_invitation"] = None
        elif action == "resign":
            faction_id = npc_id
            record = self._intrigue_state(game).get("factions", {}).get(self._intrigue_key(kind, faction_id))
            if not record:
                raise ValueError("没有找到这份客卿身份")
            before = len(record.get("guests", []))
            record["guests"] = [row for row in record.get("guests", []) if row.get("npc_id") != PLAYER_ID]
            if len(record["guests"]) == before:
                raise ValueError("你并非该势力客卿")
            summary = f"你辞去了{self._intrigue_faction_name(game, kind, faction_id)}的客卿身份。"
        else:
            faction_id = self._intrigue_player_faction_id(game, kind)
            if not faction_id or not self._intrigue_has_control(game, kind, faction_id):
                raise ValueError("你没有该势力的客卿任免权")
            record = self._ensure_intrigue_faction(game, kind, faction_id)
            guests = record["guests"]
            if action == "invite":
                if not self._intrigue_can_invite_guest(game, npc_id, kind):
                    raise ValueError("目标不是当前界面的高好感人物或道友，或其身份不符合客卿邀请条件")
                npc = self._intrigue_find_npc(game, npc_id)
                relation = self._intrigue_player_relation(game, npc_id)
                if not npc and relation:
                    npc = self._persist_relationship_npc(game, relation, "受邀担任客卿")
                if not npc:
                    raise ValueError("目标人物已经失联")
                if relation:
                    npc.affinity = max(float(npc.affinity or 0), float(relation.get("affinity", 0)))
                personality = self._ensure_intrigue_personality(game, npc)
                chance = 0.48 + float(npc.affinity or 0) / 180 + (0.08 if personality["primary"] in {"smooth", "open", "greedy"} else 0) - (0.12 if personality["primary"] in {"suspicious", "conservative"} else 0)
                source_faction = self._npc_faction_id(game, npc.id)
                if kind == "sect" and source_faction and source_faction != faction_id:
                    relation = game.sect_relations.get(race_pair(source_faction, faction_id), {})
                    if relation.get("status") == "war":
                        raise ValueError("目标对本势力负有敌对义务，不会接受客卿邀请")
                    chance += .06 if relation.get("status") == "alliance" else -.08
                chance = max(0.12, min(0.95, chance))
                if rng.random() >= chance:
                    npc.affinity = float(npc.affinity or 0) - 2
                    summary = f"{npc.name}权衡职责与旧有关系后，婉拒了客卿邀请（接受率 {chance:.0%}）。"
                else:
                    guests.append({"npc_id": npc.id, "name": npc.name, "defense_required": True, "offense_opt_in": False, "joined_age": game.player.age})
                    npc.affinity = min(
                        100.0, float(npc.affinity or 0) + self._sage_affinity_gain(game.player, 4),
                    )
                    for war in game.wars:
                        if (war.get("status") in {"active", "peace_ready"} and war.get("kind") == kind
                                and faction_id in self._coalition_ids(war, "defender")):
                            if npc.id not in war.get("roster", {}).get("defender", []):
                                war["roster"]["defender"].append(npc.id)
                                war.setdefault("roster_owner", {})[npc.id] = faction_id
                    summary = f"{npc.name}接受邀请，成为{self._intrigue_faction_name(game, kind, faction_id)}的{'供奉' if kind == 'family' else '客卿长老'}；防御战争必须出战，进攻战争可拒绝。"
            elif action == "remove":
                before = len(guests)
                guests[:] = [row for row in guests if row.get("npc_id") != npc_id]
                if len(guests) == before:
                    raise ValueError("目标不是本势力客卿")
                npc = self._intrigue_find_npc(game, npc_id)
                if npc:
                    npc.affinity = float(npc.affinity or 0) - 10
                for war in game.wars:
                    if war.get("status") in {"active", "peace_ready"} and war.get("roster_owner", {}).get(npc_id) == faction_id:
                        defender_roster = war.get("roster", {}).get("defender", [])
                        if npc_id in defender_roster:
                            defender_roster.remove(npc_id)
                        war.get("roster_owner", {}).pop(npc_id, None)
                summary = f"你撤销了{npc.name if npc else '该修士'}的客卿身份。"
            elif action == "regularize":
                guest = next((row for row in guests if row.get("npc_id") == npc_id), None)
                npc = self._intrigue_find_npc(game, npc_id)
                if not guest or not npc:
                    raise ValueError("目标客卿不存在")
                if game.player.faction_contribution < 30:
                    raise ValueError("转正需要消耗 30 点势力贡献")
                specs = self._intrigue_position_specs(kind)
                vacancy = next((pid for pid, spec in specs.items() if pid not in {"leader", "family_head"} and not record["positions"].get(pid) and npc.realm_index >= int(spec.get("minimum_realm", 0))), None)
                if not vacancy:
                    raise ValueError("没有符合其修为的正式职位空缺")
                game.player.faction_contribution -= 30
                guests.remove(guest)
                entity = self._intrigue_entity(game, kind, faction_id)
                if entity and not any(row.id == npc.id for row in entity.npcs):
                    entity.npcs.append(npc)
                npc.faction_id = faction_id if kind == "sect" else npc.faction_id
                record["positions"][vacancy] = npc.id
                summary = f"{npc.name}消耗举荐名额转为正式成员，并出任{specs[vacancy]['name']}。"
            else:
                raise ValueError("未知客卿操作")
        game.history.append(HistoryRecord(
            "SYS_INTRIGUE_GUEST", 1, game.player.age, "客卿往来", action, "resolved", summary,
            {"npc_id": npc_id}, ["system", "intrigue", "guest", "faction"],
        ))
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _intrigue_vote_chance(
        self, game: GameState, npc: SectNpc, resolution_type: str, kind: str,
        faction_id: str, target_id: str, proposer_id: str,
    ) -> tuple[float, list[str]]:
        traits = self._ensure_intrigue_personality(game, npc)
        if resolution_type == "make_peace":
            return 1.0, ["战争已经发生，停战提案优先止损"]
        faction_record = self._ensure_intrigue_faction(game, kind, faction_id)
        style = self._intrigue_governance_style(game, npc) if npc.id == faction_record.get("controller_id") else traits.get("governance_style") or faction_record.get("policy")
        chance = 0.5
        reasons: list[str] = []
        style_bias = {
            "balance": {"make_peace": .14, "investment": .08, "declare_war": -.10},
            "internal": {"mass_recruitment": .18, "disciple_recruitment": .18, "investment": .16, "declare_war": -.12},
            "diplomacy": {"form_alliance": .20, "make_peace": .18, "declare_war": -.18, "break_alliance": -.10},
            "military": {"declare_war": .22, "intervene_war": .16, "make_peace": -.10},
        }
        if style in style_bias:
            chance += style_bias[style].get(resolution_type, 0)
            reasons.append(STYLE_LABELS[str(style)])
        if target_id and kind in {"sect", "race"} and resolution_type in {"declare_war", "form_alliance", "break_alliance"}:
            relations = game.sect_relations if kind == "sect" else game.race_relations
            relation_affinity = float(relations.get(race_pair(faction_id, target_id), {}).get("affinity", 0))
            relation_bias = max(-.22, min(.22, relation_affinity / 320.0))
            if resolution_type == "form_alliance":
                chance += relation_bias
            elif resolution_type == "declare_war":
                chance -= relation_bias
            else:
                chance -= relation_bias * .7
            if abs(relation_bias) >= .04:
                reasons.append("既有外交关系良好" if relation_affinity > 0 else "既有外交关系恶劣")
        primary = str(traits.get("primary"))
        if resolution_type in {"declare_war", "intervene_war"}:
            if primary in {"fanatical", "forceful", "warlike"}:
                chance += .16; reasons.append(PERSONALITY_LABELS[primary] + "倾向强硬")
            if primary in {"cautious", "restrained", "smooth"}:
                chance -= .15; reasons.append(PERSONALITY_LABELS[primary] + "厌恶冒险")
            if target_id and kind == "sect" and target_id in game.sects:
                own_power = sum(self._npc_power(row) for row in self._intrigue_members(game, kind, faction_id) if row.alive)
                target_power = sum(self._npc_power(row) for row in self._intrigue_members(game, kind, target_id) if row.alive)
                target_power += sum(self._npc_power(npc2) for npc2 in self._intrigue_guest_npcs(game, kind, target_id))
                if own_power < target_power:
                    chance -= min(.28, (target_power / max(1.0, own_power) - 1) * .12); reasons.append("敌强且有客卿威慑")
        elif resolution_type in {"form_alliance", "make_peace"} and primary in {"smooth", "generous", "open"}:
            chance += .12; reasons.append(PERSONALITY_LABELS[primary] + "重视关系")
        if float(npc.affinity or 0) > 40 and proposer_id == PLAYER_ID:
            chance += .08; reasons.append("与提案人交好")
        if self._intrigue_is_imprisoned(game, npc.id):
            chance = 0
        return max(.05, min(.95, chance)), reasons

    def _intrigue_resolve(
        self, game: GameState, kind: str, faction_id: str, resolution_type: str,
        target_id: str, player_vote: bool | None, proposer_id: str, rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if resolution_type not in RESOLUTION_LABELS:
            raise ValueError("未知重大决议")
        record = self._ensure_intrigue_faction(game, kind, faction_id)
        ballots: list[dict[str, Any]] = []
        if self._intrigue_has_decision_authority(game, kind, faction_id) and player_vote is not None:
            ballots.append({"id": PLAYER_ID, "name": game.player.name, "vote": bool(player_vote), "player": True, "reasons": ["一人一票"]})
        voters = {npc.id: npc for npc in self._intrigue_members(game, kind, faction_id)}
        for guest in self._intrigue_guest_npcs(game, kind, faction_id):
            voters.setdefault(guest.id, guest)
        for npc in voters.values():
            if not self._intrigue_has_decision_authority(game, kind, faction_id, npc.id):
                continue
            chance, reasons = self._intrigue_vote_chance(game, npc, resolution_type, kind, faction_id, target_id, proposer_id)
            ballots.append({"id": npc.id, "name": npc.name, "vote": rng.random() < chance, "chance": round(chance, 3), "player": False, "reasons": reasons})
        if not ballots:
            raise ValueError("当前势力没有具备决策权的成员")
        yes = sum(bool(row["vote"]) for row in ballots)
        passed = yes > len(ballots) / 2
        state = self._intrigue_state(game)
        state["sequence"] = int(state.get("sequence", 0)) + 1
        resolution = {
            "id": f"resolution_{state['sequence']}", "faction_id": faction_id, "faction_name": self._intrigue_faction_name(game, kind, faction_id),
            "kind": kind, "type": resolution_type, "type_name": RESOLUTION_LABELS[resolution_type],
            "proposer_id": proposer_id, "target_id": target_id, "votes": ballots,
            "yes": yes, "total": len(ballots), "result": "passed" if passed else "rejected", "age": game.player.age,
        }
        if passed:
            self._intrigue_apply_resolution(game, record, resolution_type, target_id, rng, context=context)
            if resolution_type == "disciple_recruitment":
                pending = record.get("pending_recruitment") or {}
                resolution["candidate_count"] = len(pending.get("candidates", []))
        state["resolutions"].append(resolution)
        state["resolutions"] = state["resolutions"][-80:]
        summary = f"{resolution['faction_name']}就“{resolution['type_name']}”议决：{yes}/{len(ballots)} 票赞成，决议{'通过' if passed else '未通过'}。"
        diplomacy_resolution = resolution_type in {"declare_war", "make_peace", "form_alliance", "break_alliance"}
        event_id = (
            "SYS_PLAYER_SECT_VOTE" if diplomacy_resolution and proposer_id == PLAYER_ID and kind == "sect" else
            "SYS_PLAYER_RACE_VOTE" if diplomacy_resolution and proposer_id == PLAYER_ID and kind == "race" else
            "SYS_INTRIGUE_RESOLUTION"
        )
        state_diff = copy.deepcopy(resolution)
        if diplomacy_resolution and target_id:
            state_diff["races" if kind == "race" else "sects"] = [faction_id, target_id]
        entity = self._intrigue_entity(game, kind, faction_id)
        event_world = entity.world if entity else game.player.world
        game.history.append(HistoryRecord(
            event_id, 1, game.player.age, "势力决议", resolution_type,
            "passed" if passed else "rejected", summary, state_diff,
            ["system", "intrigue", "vote", kind, *( ["diplomacy"] if diplomacy_resolution else [] ), "world_news", f"world:{event_world}"],
        ))
        return resolution

    def _intrigue_apply_resolution(
        self, game: GameState, record: dict[str, Any], resolution_type: str,
        target_id: str, rng: random.Random, *, context: dict[str, Any] | None = None,
    ) -> None:
        kind, faction_id = str(record["kind"]), str(record["id"])
        if resolution_type in {"declare_war", "make_peace", "form_alliance", "break_alliance"}:
            status = {"declare_war": "war", "make_peace": "truce", "form_alliance": "alliance", "break_alliance": "neutral"}[resolution_type]
            relations = game.race_relations if kind == "race" else game.sect_relations
            if kind not in {"sect", "race"} or not target_id:
                return
            relation = relations.setdefault(race_pair(faction_id, target_id), {"affinity": 0.0, "status": "neutral", "since_age": game.player.age})
            if relation.get("status") == "war" and status != "war":
                # Field wars still use the established war-peace settlement flow.
                return
            self._set_diplomatic_relation(game, relation, status, faction_id, target_id, kind,
                                           {"war": -75.0, "truce": -5.0, "alliance": 80.0, "neutral": 0.0}[status])
        elif resolution_type == "mass_recruitment" and kind in {"sect", "family"}:
            entity = self._intrigue_entity(game, kind, faction_id)
            if not entity:
                return
            for _ in range(rng.randint(2, 4)):
                index = uuid.uuid4().hex[:10]
                realm_index = rng.choices([0, 1, 2], weights=[4, 5, 1], k=1)[0]
                lifespan_range = REALMS[realm_index].lifespan
                age = rng.randint(16, 42)
                lifespan = max(age + 1, rng.randint(*lifespan_range)) if lifespan_range else None
                npc = SectNpc(f"intrigue_recruit_{index}", rng.choice(["宁川", "苏砚", "沈禾", "顾霜", "陆迟", "叶青"]),
                              "新晋成员", realm_index, 1, age, lifespan, path=entity.path,
                              race=entity.allegiance_race or "human", world=entity.world,
                              affinity=rng.uniform(8, 28), faction_id=faction_id if kind == "sect" else None)
                entity.npcs.append(npc)
                self._ensure_intrigue_personality(game, npc)
            record["unrest"] = max(0.0, float(record.get("unrest", 0)) - 2)
        elif resolution_type == "disciple_recruitment" and kind == "sect":
            filters = self._normalize_intrigue_recruitment_filters(
                game, (context or {}).get("filters"),
            )
            record["pending_recruitment"] = self._generate_intrigue_recruitment_session(
                game, faction_id, filters, rng,
            )
            record["unrest"] = max(0.0, float(record.get("unrest", 0)) - 1)
        elif resolution_type == "investment":
            record["resources"] = int(record.get("resources", 0)) + 25
            record["unrest"] = max(0.0, float(record.get("unrest", 0)) - 4)
        elif resolution_type == "relocate" and kind in {"sect", "family"} and target_id in WORLD_SYSTEMS.get("world_profiles", {}):
            entity = self._intrigue_entity(game, kind, faction_id)
            if entity:
                entity.world = target_id
                for npc in entity.npcs:
                    npc.world = target_id
        elif resolution_type == "policy" and target_id in STYLE_LABELS:
            record["policy"] = target_id
        elif resolution_type == "intervene_war":
            record["intervention_target"] = target_id
            war = next((row for row in game.wars if row.get("id") == target_id and row.get("status") in {"active", "peace_ready"}), None)
            if war and war.get("kind") == kind and not self._participant_side(war, faction_id):
                self._add_war_participant(game, war, "defender", faction_id, str(war.get("defender_id", "")))
                self._append_war_log(
                    game, war, "介入战争",
                    f"{self._intrigue_faction_name(game, kind, faction_id)}经决议介入战局，加入防御阵营。",
                )

    def intrigue_propose_resolution(
        self, game_id: str, kind: str, resolution_type: str, target_id: str = "", player_vote: bool = True,
    ) -> dict[str, Any]:
        game = self._load(game_id)
        if not self._intrigue_enabled():
            raise ValueError("《明争暗斗：合纵连横》DLC 尚未启用")
        if game.pending_event or game.player.imprisonment:
            raise ValueError("当前状态无法召开势力议事")
        faction_id = self._intrigue_player_faction_id(game, kind)
        if not faction_id or not self._intrigue_has_decision_authority(game, kind, faction_id):
            raise ValueError("你没有该势力的决策权")
        if resolution_type == "disciple_recruitment":
            raise ValueError("扩招徒弟需要先设置筛选条件")
        if resolution_type in {"declare_war", "make_peace", "form_alliance", "break_alliance"}:
            if kind == "sect" and (target_id not in game.sects or target_id == faction_id):
                raise ValueError("目标宗门无效")
            if kind == "race" and (target_id not in RACE_DEFINITIONS or target_id == faction_id):
                raise ValueError("目标种族无效")
            if resolution_type == "make_peace" and self._active_war(game, kind, faction_id, target_id):
                raise ValueError("战争已经进入征伐阶段，请在战争窗口提交和约；和约仍会先经过势力表决")
        rng = decode_rng(game.seed, game.rng_state)
        self._intrigue_resolve(game, kind, faction_id, resolution_type, target_id, bool(player_vote), PLAYER_ID, rng)
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def intrigue_recruitment_action(
        self, game_id: str, action: str, filters: dict[str, Any] | None = None,
        candidate_ids: list[str] | None = None, player_vote: bool = True,
    ) -> dict[str, Any]:
        game = self._load(game_id)
        if not self._intrigue_enabled():
            raise ValueError("《明争暗斗：合纵连横》DLC 尚未启用")
        if game.pending_event or game.player.imprisonment:
            raise ValueError("当前状态无法处理宗门扩招")
        faction_id = self._intrigue_player_faction_id(game, "sect")
        if not faction_id or not self._intrigue_has_decision_authority(game, "sect", faction_id):
            raise ValueError("你没有当前宗门的决策权")
        sect = game.sects.get(faction_id)
        if not sect or sect.extinct:
            raise ValueError("当前宗门已经不存在")
        record = self._ensure_intrigue_faction(game, "sect", faction_id)
        rng = decode_rng(game.seed, game.rng_state)
        if action == "propose":
            if record.get("pending_recruitment"):
                raise ValueError("请先处理上一轮扩招候选人")
            normalized = self._normalize_intrigue_recruitment_filters(game, filters)
            self._intrigue_resolve(
                game, "sect", faction_id, "disciple_recruitment", "",
                bool(player_vote), PLAYER_ID, rng, context={"filters": normalized},
            )
        elif action == "confirm":
            pending = record.get("pending_recruitment")
            if not isinstance(pending, dict):
                raise ValueError("当前没有待选择的扩招候选人")
            raw_candidate_ids = candidate_ids if isinstance(candidate_ids, list) else []
            requested = list(dict.fromkeys(str(value) for value in raw_candidate_ids))
            available = {
                str(row.get("npc", {}).get("id", "")): row
                for row in pending.get("candidates", []) if row.get("npc", {}).get("id")
            }
            if any(candidate_id not in available for candidate_id in requested):
                raise ValueError("所选候选人不属于本轮扩招名单")
            maximum = min(5, int(self._intrigue_recruitment_config().get("max_candidates", 5)))
            if len(requested) > maximum:
                raise ValueError(f"每轮最多录取 {maximum} 名弟子")
            capacity = max(0, int(FACTION_SYSTEMS.get("max_members", 36)) - len([
                npc for npc in self._sect_members(game, sect) if npc.alive
            ]))
            if len(requested) > capacity:
                raise ValueError(f"宗门名册仅余 {capacity} 个空位")
            joined: list[SectNpc] = []
            for candidate_id in requested:
                npc = SectNpc.from_dict(copy.deepcopy(available[candidate_id]["npc"]))
                npc.title = "新入门弟子"
                npc.faction_id = faction_id
                sect.npcs.append(npc)
                self._ensure_intrigue_personality(game, npc)
                joined.append(npc)
            record["pending_recruitment"] = None
            names = "、".join(npc.name for npc in joined)
            result = "recruited" if joined else "closed"
            summary = (
                f"你从本轮候选中录取了 {len(joined)} 名弟子：{names}。"
                if joined else "本轮没有录取任何候选人，扩招名册已经关闭。"
            )
            game.history.append(HistoryRecord(
                "SYS_INTRIGUE_DISCIPLE_RECRUITMENT", 1, game.player.age,
                "宗门扩招", action, result, summary,
                {
                    "faction_id": faction_id, "candidate_ids": requested,
                    "filter_summary": pending.get("filter_summary"),
                },
                ["system", "intrigue", "sect", "recruitment", "disciple"],
            ))
        else:
            raise ValueError("未知的宗门扩招操作")
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _intrigue_guest_npcs(self, game: GameState, kind: str, faction_id: str) -> list[SectNpc]:
        if not self._intrigue_enabled():
            return []
        record = self._ensure_intrigue_faction(game, kind, faction_id)
        result = []
        for guest in record.get("guests", []):
            if guest.get("npc_id") == PLAYER_ID:
                continue
            npc = self._intrigue_find_npc(game, str(guest.get("npc_id", "")))
            if npc and npc.alive and not self._intrigue_is_imprisoned(game, npc.id):
                result.append(npc)
        return result

    def _intrigue_defensive_guest_ids(self, game: GameState, kind: str, faction_id: str, world: str) -> list[str]:
        return [npc.id for npc in self._intrigue_guest_npcs(game, kind, faction_id) if npc.world == world]

    def _intrigue_player_guest_side(self, game: GameState, war: dict[str, Any]) -> str | None:
        if not self._intrigue_enabled() or game.player.world != war.get("world"):
            return None
        for faction_id in self._coalition_ids(war, "defender"):
            record = self._ensure_intrigue_faction(game, str(war.get("kind")), faction_id)
            if any(row.get("npc_id") == PLAYER_ID and row.get("defense_required", True) for row in record.get("guests", [])):
                return "defender"
        return None

    def _intrigue_record_player_prison(self, game: GameState, key: str, years: int) -> None:
        if not self._intrigue_enabled() or ":" not in key:
            return
        kind, faction_id = key.split(":", 1)
        if kind not in {"sect", "family"}:
            return
        if kind == "sect" and faction_id not in game.sects:
            return
        if kind == "family" and (not game.family or game.family.id != faction_id):
            return
        record = self._ensure_intrigue_faction(game, kind, faction_id)
        record["prison"] = [row for row in record["prison"] if row.get("prisoner_id") != PLAYER_ID]
        record["prison"].append({
            "prisoner_id": PLAYER_ID, "name": game.player.name, "faction_id": faction_id,
            "kind": kind, "sentence_remaining": years, "sentence_years": years,
            "reason": "接受通缉处罚", "imprisoned_by": faction_id,
        })
        game.player.imprisonment.update({"faction_id": faction_id, "faction_kind": kind, "facility": "faction_prison"})

    def _intrigue_sync_player_prison(self, game: GameState) -> None:
        if not self._intrigue_enabled():
            return
        for record in self._intrigue_state(game).get("factions", {}).values():
            for row in record.get("prison", []):
                if row.get("prisoner_id") == PLAYER_ID and game.player.imprisonment:
                    row["sentence_remaining"] = int(game.player.imprisonment.get("remaining_years", 0))
            if not game.player.imprisonment:
                record["prison"] = [row for row in record.get("prison", []) if row.get("prisoner_id") != PLAYER_ID]

    def _advance_intrigue_unit(self, game: GameState, rng: random.Random) -> list[str]:
        if not self._intrigue_enabled():
            return []
        state = self._intrigue_state(game)
        # Re-evaluate the player's cultivation-order office every action unit,
        # so appointments and later promotions survive even if the panel was
        # never opened before advancing time.
        for kind in ("sect", "family"):
            faction_id = self._intrigue_player_faction_id(game, kind)
            if faction_id:
                self._ensure_intrigue_faction(game, kind, faction_id)
        # Sentences share the existing action-unit clock and do not scan NPC pairs.
        for record in state.get("factions", {}).values():
            remaining = []
            for prisoner in record.get("prison", []):
                if prisoner.get("prisoner_id") == PLAYER_ID:
                    remaining.append(prisoner)
                    continue
                prisoner["sentence_remaining"] = max(0, int(prisoner.get("sentence_remaining", 0)) - 1)
                if prisoner["sentence_remaining"] > 0:
                    remaining.append(prisoner)
                else:
                    state["npc_prisons"].pop(str(prisoner.get("prisoner_id", "")), None)
            record["prison"] = remaining
        self._intrigue_sync_player_prison(game)
        news: list[str] = []
        if self._world_supports(game.player.world, "races"):
            race_id = self._player_allegiance_race(game.player)
            race_record = self._ensure_intrigue_faction(game, "race", race_id)
            if not race_record.get("qingzu_initialized"):
                candidates = [
                    npc for npc in self._all_world_npcs(game)
                    if npc.alive and npc.world == game.player.world and npc.race != race_id
                    and npc.realm_index >= self._intrigue_decision_threshold("race")
                ]
                if candidates:
                    candidates.sort(key=lambda row: (-row.realm_index, -row.layer, row.id))
                    guest = candidates[0]
                    race_record["guests"].append({
                        "npc_id": guest.id, "name": guest.name, "title": "卿族",
                        "defense_required": True, "offense_opt_in": False,
                    })
                    race_record["qingzu_initialized"] = True
                    news.append(f"{RACE_DEFINITIONS.get(race_id, {}).get('name', race_id)}议事者延请{guest.name}为卿族。")
        # High-realm players occasionally receive a weak-sect guest invitation.
        realm_index, _ = self._actual_player_realm(game.player)
        if not state.get("pending_guest_invitation") and realm_index >= 4 and rng.random() < .08:
            candidates = []
            for sect in game.sects.values():
                if sect.extinct or sect.world != game.player.world or sect.id == game.player.faction_id:
                    continue
                strongest = max((npc.realm_index for npc in self._sect_members(game, sect) if npc.alive), default=0)
                record = self._ensure_intrigue_faction(game, "sect", sect.id)
                if strongest + 2 <= realm_index and not any(row.get("npc_id") == PLAYER_ID for row in record.get("guests", [])):
                    candidates.append(sect)
            if candidates:
                sect = rng.choice(candidates)
                state["pending_guest_invitation"] = {"kind": "sect", "faction_id": sect.id, "faction_name": sect.name, "title": "客卿长老", "world": sect.world}
                news.append(f"{sect.name}看重你的修为，遣使邀你担任客卿长老。")
        # One NPC-led faction may act per three units: O(members), never O(N²).
        if game.diplomacy_unit % 3 == 0:
            candidates = [sect for sect in game.sects.values() if not sect.extinct and not sect.founded_by_player and sect.id != game.player.faction_id]
            if candidates:
                state["ai_cursor"] = (int(state.get("ai_cursor", 0)) + 1) % len(candidates)
                sect = candidates[state["ai_cursor"]]
                record = self._ensure_intrigue_faction(game, "sect", sect.id)
                controller = self._intrigue_find_npc(game, str(record.get("controller_id", "")))
                eligible_voters = [
                    npc for npc in self._intrigue_members(game, "sect", sect.id)
                    if self._intrigue_has_decision_authority(game, "sect", sect.id, npc.id)
                ]
                if controller and eligible_voters and rng.random() < .16:
                    style = self._intrigue_governance_style(game, controller)
                    resolution_type = {"internal": "mass_recruitment", "balance": "investment", "diplomacy": "form_alliance", "military": "declare_war"}[style]
                    target_id = ""
                    if resolution_type in {"form_alliance", "declare_war"}:
                        possible = [row.id for row in candidates if row.id != sect.id and row.world == sect.world]
                        if not possible:
                            resolution_type = "investment"
                        else:
                            target_id = rng.choice(possible)
                    resolution = self._intrigue_resolve(game, "sect", sect.id, resolution_type, target_id, None, controller.id, rng)
                    if game.debug_world_news or sect.world == game.player.world:
                        news.append(f"{sect.name}在{STYLE_LABELS[style]}主政下提出{RESOLUTION_LABELS[resolution_type]}，决议{('通过' if resolution['result'] == 'passed' else '遭否决')}。")
        return news

    def _intrigue_pressure_position_occupied(self, game: GameState, faction_id: str) -> bool:
        """DLC pressure requires an actually occupied office, never a phantom rival."""
        if not self._intrigue_enabled():
            return True
        record = self._ensure_intrigue_faction(game, "sect", faction_id)
        specs = self._intrigue_position_specs("sect")
        relevant = [pid for pid, spec in specs.items() if pid not in {"leader", "guest_elder"} and game.player.realm_index >= int(spec.get("minimum_realm", 0))]
        return any(record.get("positions", {}).get(pid) for pid in relevant)

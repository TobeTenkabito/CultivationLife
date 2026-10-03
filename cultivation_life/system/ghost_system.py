from __future__ import annotations

from .ghost.progression import (
    grant_intrinsic_growth as grant_intrinsic_growth,
    grant_intrinsic_progression_if_new_highwater as grant_intrinsic_progression_if_new_highwater,
    grant_wangsheng as grant_wangsheng,
    reincarnation_effective_marks as reincarnation_effective_marks,
    reincarnation_breakthrough_bonus as reincarnation_breakthrough_bonus,
    can_reincarnate as can_reincarnate,
    perform_reincarnation as perform_reincarnation,
    apply_soul_erosion as apply_soul_erosion,
    accumulate_soul_erosion_time as accumulate_soul_erosion_time,
    spend_wangsheng_energy as spend_wangsheng_energy,
    soul_integrity_label as soul_integrity_label,
)

import copy
import math
import random
from typing import Any

from ..content_registry import REALMS, WORLD_SYSTEMS
from ..ghost_soul_traits import generate_soul_trait, validate_generated_soul_trait
from ..models import GameState, HistoryRecord, Player, SectNpc
from ..runtime import now_iso
from .possession_system import (
    advance_player_age, can_possess, current_body_age, enter_host_body, has_ghost_core,
    is_possessed, leave_host_body, possession_limit,
)


from .ghost_resources import (
    GHOST_DLC_NAME as GHOST_DLC_NAME,
    SOUL_SLOTS as SOUL_SLOTS,
    THREE_SOUL_STATS as THREE_SOUL_STATS,
    SOUL_TRAIT_RULES as SOUL_TRAIT_RULES,
    ghost_cultivation_config as ghost_cultivation_config,
    ghost_cultivation_active as ghost_cultivation_active,
    ghost_phase_two_config as ghost_phase_two_config,
    active_bound_souls as active_bound_souls,
    active_soul_traits as active_soul_traits,
    active_generated_soul_traits as active_generated_soul_traits,
    ghost_soul_effects as ghost_soul_effects,
    ghost_soul_pressure as ghost_soul_pressure,
    ghost_external_hp_bonus as ghost_external_hp_bonus,
    ghost_external_mp_bonus as ghost_external_mp_bonus,
    ghost_opportunity_multiplier as ghost_opportunity_multiplier,
    canonical_intrinsic_hp as canonical_intrinsic_hp,
    canonical_intrinsic_mp as canonical_intrinsic_mp,
    ensure_ghost_cultivation_state as ensure_ghost_cultivation_state,
    intrinsic_hp_reference as intrinsic_hp_reference,
    intrinsic_mp_reference as intrinsic_mp_reference,
    effective_intrinsic_hp as effective_intrinsic_hp,
    effective_intrinsic_mp as effective_intrinsic_mp,
    hp_carry_ratio as hp_carry_ratio,
    mp_carry_ratio as mp_carry_ratio,
)


class GhostSystemMixin:
    def assert_ghost_operation_allowed(self, game_id: str, operation: str) -> None:
        """Enforce the controlled-state boundary at the HTTP command gateway."""
        game = self._load(game_id)
        if game.player.ghost_captor and operation not in {
            "advance", "choice", "use-item", "settings", "ghost-soul", "ghost-constraint",
        }:
            raise ValueError("魂印受制于拘魂者，当前功能要求自由行动主体，因而不可使用")


    def _ensure_ghost_parade(self, game: GameState, rng: random.Random) -> None:
        config = ghost_phase_two_config().get("parade", {})
        if not config.get("enabled", False) or game.ghost_parade:
            return
        # World ecology owns a deterministic sub-stream so enabling the DLC
        # cannot perturb existing event/combat rolls in the base game.
        parade_rng = random.Random(f"{game.seed}:ghost-parade:{game.player.age}:{game.player.world}")
        unit = max(1, int(WORLD_SYSTEMS["time_units"][str(game.player.realm_index)]))
        gap_units = parade_rng.randint(
            max(3, int(config.get("min_interval_units", 5))),
            max(3, int(config.get("max_interval_units", 9))),
        )
        locations = [row["id"] for row in self.maps.public_map(
            game.player.world, game.player.location_id, game.player.realm_index,
            WORLD_SYSTEMS["world_names"].get(game.player.world, game.player.world),
        ).get("locations", [])]
        game.ghost_parade = {
            "status": "scheduled", "world": game.player.world,
            "location_id": parade_rng.choice(locations) if locations else game.player.location_id,
            "start_age": game.player.age + gap_units * unit,
            "end_age": game.player.age + (gap_units + int(config.get("duration_units", 2))) * unit,
            "announced": False, "participated": False, "souls": [],
        }

    def _generate_parade_souls(self, game: GameState, rng: random.Random) -> list[dict[str, Any]]:
        from ..rules import expected_combat_power

        surnames = "沈顾谢陆萧楚苏宁白叶"
        given = ("无咎", "照夜", "忘川", "玄衣", "引灯", "归尘", "青冥", "幽篁")
        count = max(3, int(ghost_phase_two_config().get("parade", {}).get("soul_count", 6)))
        souls = []
        for index in range(count):
            realm_index = max(0, min(len(REALMS) - 1, game.player.realm_index + rng.choice((-1, 0, 0, 1))))
            layer = rng.randint(1, REALMS[realm_index].layers)
            soul_trait = generate_soul_trait(rng)
            soul_power = round(expected_combat_power(realm_index, layer) * rng.uniform(0.72, 1.18), 1)
            pressure_rules = ghost_phase_two_config().get("soul_pressure", {})
            pressure = (
                float(pressure_rules.get("base", 0.5))
                + float(pressure_rules.get("power_cap", 2.0))
                * (1.0 - math.exp(-soul_power / max(1.0, float(pressure_rules.get("power_scale", 5000.0)))))
            )
            souls.append({
                "id": f"soul_{game.seed}_{game.player.age}_{index}",
                "npc_id": f"parade_{game.seed}_{game.player.age}_{index}",
                "name": f"{rng.choice(surnames)}{rng.choice(given)}", "path": "ghost", "race": "human",
                "realm_index": realm_index, "layer": layer,
                "combat_power": soul_power,
                "affinity": rng.randint(-15, 25), "defeated": False, "befriended": False,
                "is_bound_soul": False,
                "personality": rng.choice(("执拗", "温和", "凶厉", "多疑", "洒脱")),
                "npc_relations": [], "skills": [soul_trait["name"]],
                "faction_inclination": rng.choice(("散魂", "阴司", "宗门故旧", "无阵营")),
                "original_identity": f"{REALMS[realm_index].name}遗魂",
                "soul_pressure": round(pressure, 2),
                "soul_trait": soul_trait,
            })
        return souls


    def ghost_parade_action(self, game_id: str, soul_id: str, action: str) -> dict[str, Any]:
        from ..rules import combat_power
        from ..runtime import decode_rng, encode_rng

        game = self._load(game_id)
        player = game.player
        if not player.alive:
            raise ValueError("此生已经结束")
        if not ghost_cultivation_active(player) or player.ghost_captor or is_possessed(player):
            raise ValueError("只有自由鬼修能够参与百鬼夜行")
        parade = game.ghost_parade
        if parade.get("status") != "active" or parade.get("world") != player.world \
                or parade.get("location_id") != player.location_id:
            raise ValueError("当前所在地没有正在发生的百鬼夜行")
        rng = decode_rng(game.seed, game.rng_state)
        if action == "participate":
            if parade.get("participated"):
                raise ValueError("本次百鬼夜行已经参悟过")
            parade["participated"] = True
            reduction = max(0.0, float(ghost_phase_two_config().get("parade", {}).get("participate_reduction_pp", 0.005)))
            before = player.ghost_soul_erosion_rate_pp
            player.ghost_soul_erosion_rate_pp = max(0.0, before - reduction)
            result, summary = "participated", f"你观百鬼执念流转，未来魂蚀率降低 {before-player.ghost_soul_erosion_rate_pp:.4f} 个百分点。"
        else:
            soul = next((row for row in parade.get("souls", []) if row.get("id") == soul_id), None)
            if not soul:
                raise ValueError("这道游魂已经离开夜行")
            if action == "befriend":
                if soul.get("befriended"):
                    raise ValueError("本次百鬼夜行已经与这道游魂结交过")
                soul["befriended"] = True
                soul["affinity"] = min(100, float(soul.get("affinity", 0)) + rng.randint(8, 18))
                personality_bonus = 0.10 if soul.get("personality") in {"温和", "洒脱"} else -0.08 if soul.get("personality") in {"凶厉", "多疑"} else 0
                realm_bonus = max(-0.08, min(0.08, (player.realm_index - int(soul.get("realm_index", 0))) * 0.02))
                chance = max(0.05, min(0.75, 0.18 + soul["affinity"] / 200 + personality_bonus + realm_bonus))
                healed = rng.random() < chance
                reduction = float(ghost_phase_two_config().get("parade", {}).get("befriend_reduction_pp", 0.002)) if healed else 0
                player.ghost_soul_erosion_rate_pp = max(0.0, player.ghost_soul_erosion_rate_pp - reduction)
                result, summary = "befriended", f"你与{soul['name']}交换前尘，亲近有所增长" + (f"，魂蚀率降低 {reduction:.4f} 个百分点。" if healed else "。")
            elif action in {"fight", "capture"}:
                own = combat_power(player)
                chance = max(0.08, min(0.95, own / max(1.0, own + float(soul["combat_power"]))))
                combat_result, combat_summary = self._combat(game, {
                    "target_name": soul["name"], "target_power": float(soul["combat_power"]),
                    "target_realm_index": int(soul["realm_index"]), "target_layer": int(soul["layer"]),
                    "combat_type": "cultivator", "race": "human", "path": "ghost",
                    "capture": False, "kill_karma": False, "npc_id": soul.get("npc_id"),
                }, lethal=False, rng=rng)
                if combat_result != "victory":
                    result, summary = combat_result, f"{combat_summary} 你未能拘住{soul['name']}（战前估算 {chance:.0%}）。"
                else:
                    soul["defeated"] = True
                    result, summary = "victory", f"{combat_summary} 你击溃{soul['name']}的外层魂衣。"
                    if action == "capture":
                        soul["is_bound_soul"] = True
                        player.ghost_bound_souls.append(copy.deepcopy(soul))
                        parade["souls"].remove(soul)
                        player.milestones["ghost_souls_bound"] = int(player.milestones.get("ghost_souls_bound", 0)) + 1
                        result, summary = "captured", f"你击溃并拘住{soul['name']}；其姓名、修为、魂压与魂性被永久保存。"
            elif action == "bind":
                if not soul.get("defeated"):
                    raise ValueError("必须先在交锋中击溃这道游魂")
                soul["is_bound_soul"] = True
                player.ghost_bound_souls.append(copy.deepcopy(soul))
                parade["souls"].remove(soul)
                player.milestones["ghost_souls_bound"] = int(player.milestones.get("ghost_souls_bound", 0)) + 1
                result, summary = "captured", f"你将{soul['name']}收入魂册，其身份与魂性均被保留。"
            else:
                raise ValueError("未知的百鬼夜行行动")
        game.history.append(HistoryRecord(
            "SYS_GHOST_PARADE_ACTION", 1, player.age, "夜行抉择", action, result, summary,
            {"soul_id": soul_id}, ["action", "ghost", "parade"],
        ))
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def ghost_soul_action(self, game_id: str, soul_id: str, action: str, slot: str = "") -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not player.alive:
            raise ValueError("此生已经结束")
        if not ghost_phase_two_config().get("enabled", False) or not has_ghost_core(player):
            raise ValueError("只有鬼魂核心能够管理拘魂")
        soul = next((row for row in player.ghost_bound_souls if str(row.get("id")) == soul_id), None)
        if action == "equip":
            if is_possessed(player):
                raise ValueError("夺舍期间十魂全部沉寂，不能更换")
            if not soul or slot not in SOUL_SLOTS:
                raise ValueError("魂魄或魂位不存在")
            for occupied, equipped_id in list(player.ghost_soul_slots.items()):
                if equipped_id == soul_id:
                    player.ghost_soul_slots.pop(occupied, None)
            player.ghost_soul_slots[slot] = soul_id
            if len(player.ghost_soul_slots) == len(SOUL_SLOTS):
                player.milestones["ghost_ten_soul_slots"] = 1
            summary = f"{soul['name']}入驻{slot}，立即以该魂位规则生效。"
        elif action == "unequip":
            target_slot = slot or next((key for key, value in player.ghost_soul_slots.items() if value == soul_id), "")
            if target_slot not in player.ghost_soul_slots:
                raise ValueError("该魂魄没有入驻魂位")
            player.ghost_soul_slots.pop(target_slot)
            summary = f"你撤下了{target_slot}魂位，不消耗时间。"
        elif action == "release":
            if not soul:
                raise ValueError("魂册中没有这道魂魄")
            player.ghost_soul_slots = {key: value for key, value in player.ghost_soul_slots.items() if value != soul_id}
            player.ghost_bound_souls.remove(soul)
            summary = f"你解开魂印，放归{soul['name']}；此操作不可撤销。"
        else:
            raise ValueError("未知魂魄操作")
        game.history.append(HistoryRecord(
            "SYS_GHOST_SOUL_ACTION", 1, player.age, "十魂轮转", action, "success", summary,
            {"soul_id": soul_id, "slot": slot}, ["action", "ghost", "bound_soul"],
        ))
        game.updated_at = now_iso(); self.store.save(game)
        return self.present(game)

    def ghost_attachment_action(self, game_id: str, action: str, item_id: str = "") -> dict[str, Any]:
        game = self._load(game_id); player = game.player
        if not player.alive:
            raise ValueError("此生已经结束")
        if not ghost_cultivation_active(player) or player.ghost_captor or is_possessed(player):
            raise ValueError("当前魂体不能进行附灵")
        if action == "leave":
            if not player.ghost_attachment:
                raise ValueError("当前没有附着任何器物")
            name = player.ghost_attachment.get("name", "器物")
            player.ghost_attachment = None
            summary = f"你从{name}中逸出，恢复自由魂体。"
        elif action == "attach":
            item = next((row for row in player.inventory if row.id == item_id and row.quantity > 0), None)
            if not item:
                raise ValueError("行囊中没有该器物")
            quality = max(0.0, item.combat_bonus + item.hp_bonus + item.mp_bonus + item.opportunity_bonus * 100)
            if quality <= 0 and "ghost_vessel" not in item.tags and not any(key in item.name for key in ("器", "剑", "刀", "鼎", "炉", "珠", "灯", "匣", "舟")):
                raise ValueError("只能附着兵器、法器或魂器")
            player.ghost_attachment = {
                "item_id": item.id, "name": item.name, "spirit_name": f"{item.name}器灵·{player.name}",
                "erosion_growth_multiplier": (
                    float(item.erosion_growth_multiplier) if item.erosion_growth_multiplier != 1.0
                    else max(0.45, 0.92 - min(0.47, quality / 5000))
                ),
                "cultivation_efficiency_multiplier": (
                    float(item.cultivation_efficiency_multiplier) if item.cultivation_efficiency_multiplier != 1.0
                    else max(0.68, 0.94 - min(0.26, quality / 10000))
                ),
            }
            summary = f"你附入{item.name}成为器灵；仍可自由行动并随时离器。"
        else:
            raise ValueError("未知附灵操作")
        game.history.append(HistoryRecord(
            "SYS_GHOST_ATTACHMENT", 1, player.age, "附灵", action, "success", summary,
            {"item_id": item_id}, ["action", "ghost", "attachment"],
        ))
        game.updated_at = now_iso(); self.store.save(game)
        return self.present(game)


    def _public_ghost_phase_two(self, game: GameState) -> dict[str, Any]:
        player = game.player
        effects = ghost_soul_effects(player)
        pressure, pressure_modifier = ghost_soul_pressure(player)
        by_id = {str(row.get("id")): row for row in player.ghost_bound_souls}
        def public_soul(raw: dict[str, Any] | None) -> dict[str, Any] | None:
            if not raw:
                return None
            result = copy.deepcopy(raw)
            trait = result.get("soul_trait") or {}
            trait_name = str(trait.get("name", ""))
            if trait_name in SOUL_TRAIT_RULES:
                trait["description"] = SOUL_TRAIT_RULES[trait_name]
                trait["rule"] = SOUL_TRAIT_RULES[trait_name]
                result["soul_trait"] = trait
            elif trait.get("generated"):
                reasons = validate_generated_soul_trait(trait)
                trait["valid"] = not reasons
                trait["invalid_reasons"] = reasons
                result["soul_trait"] = trait
            return result
        slots = [{
            "id": slot, "stat": stat, "stat_name": label,
            "soul_id": player.ghost_soul_slots.get(slot),
            "effect": round(effects.get(stat, 0.0), 6),
            "curve": "unbounded_diminishing" if stat in THREE_SOUL_STATS else "capped_saturation",
            "soul": public_soul(by_id.get(player.ghost_soul_slots.get(slot, ""))),
        } for slot, (stat, label) in SOUL_SLOTS.items()]
        parade = copy.deepcopy(game.ghost_parade)
        if parade and not parade.get("announced"):
            parade = {"status": "dormant", "announced": False}
        elif parade:
            parade["souls"] = [public_soul(row) for row in parade.get("souls", [])]
            parade["at_location"] = bool(
                parade.get("world") == player.world and parade.get("location_id") == player.location_id
            )
            try:
                parade["location_name"] = self.maps.location(
                    str(parade.get("world")), str(parade.get("location_id")),
                )["name"]
            except Exception:
                parade["location_name"] = str(parade.get("location_id", "未知"))
        attachable = [{
            "id": item.id, "name": item.name, "quantity": item.quantity,
        } for item in player.inventory if item.quantity > 0 and (
            item.combat_bonus + item.hp_bonus + item.mp_bonus + item.opportunity_bonus * 100 > 0
            or "ghost_vessel" in item.tags
            or any(key in item.name for key in ("器", "剑", "刀", "鼎", "炉", "珠", "灯", "匣", "舟"))
        )]
        state = "possessed" if is_possessed(player) else "controlled" if player.ghost_captor \
            else "attached" if player.ghost_attachment else "free"
        return {
            "enabled": bool(ghost_phase_two_config().get("enabled", False)), "state": state,
            "state_name": {"free": "自由魂体", "attached": "附灵器魂", "controlled": "受制拘魂", "possessed": "夺舍寄身"}[state],
            "slots": slots, "bound_souls": [public_soul(row) for row in player.ghost_bound_souls],
            "effects": {key: round(value, 6) for key, value in effects.items()},
            "pressure": round(pressure, 4), "pressure_modifier": round(pressure_modifier, 6),
            "parade": parade, "attachment": copy.deepcopy(player.ghost_attachment),
            "attachable_items": attachable, "captor": copy.deepcopy(player.ghost_captor),
            "host": copy.deepcopy(player.ghost_host_body),
            "possession_count": player.possession_count, "possession_limit": possession_limit(player),
            "souls_suspended": is_possessed(player),
        }

    def _public_map_with_ghost_parade(self, game: GameState, location_id: str) -> dict[str, Any]:
        data = self.maps.public_map(
            game.player.world, location_id, game.player.realm_index,
            WORLD_SYSTEMS["world_names"].get(game.player.world, game.player.world),
            lambda destination: self._monster_travel_multiplier(game.player, destination),
        )
        from .faction_geography import ensure_faction_sites, war_site
        ensure_faction_sites(game)
        factions = [*game.sects.values(), *([game.family] if game.family else [])]
        from ..content_registry import RACE_DEFINITIONS
        import hashlib
        safe = [row for row in data.get("locations", []) if not row.get("min_realm_index", 0)]
        race_sites = {}
        for race_id, definition in RACE_DEFINITIONS.items():
            if safe and game.player.world in definition.get("worlds", []):
                index = int.from_bytes(hashlib.sha256(f"{game.player.world}:{race_id}".encode()).digest()[:4], "big") % len(safe)
                race_sites.setdefault(safe[index]["id"], []).append({"id": race_id, "name": definition["name"], "kind": "race", "owned": False})
        for location in data.get("locations", []):
            location["factions"] = [{"id": f.id, "name": f.name, "kind": f.kind,
                                      "owned": f.founded_by_player}
                                     for f in factions if not f.extinct and f.world == game.player.world
                                     and f.location_id == location["id"]]
            location["factions"].extend(race_sites.get(location["id"], []))
            location["wars"] = [{"id": w["id"], "attacker": self._war_side_name(game, "sect", w["attacker_id"]),
                                  "defender": self._war_side_name(game, "sect", w["defender_id"])}
                                 for w in game.wars if w.get("status") == "active" and w.get("kind") == "sect"
                                 and w.get("world") == game.player.world
                                 and war_site(self.maps, w)["id"] == location["id"]]
        parade = game.ghost_parade
        if parade and parade.get("announced") and parade.get("world") == game.player.world:
            for location in data.get("locations", []):
                if location.get("id") == parade.get("location_id"):
                    location["ghost_parade"] = {
                        "status": parade.get("status"), "start_age": parade.get("start_age"),
                        "end_age": parade.get("end_age"), "label": "百鬼夜行",
                    }
        # V2 ground arrays are map fixtures rather than invisible status
        # bonuses. Publish a compact marker without copying their material
        # snapshots into every map row.
        for location in data.get("locations", []):
            arrays = [
                row for row in game.player.formation_ground_arrays
                if row.get("world") == game.player.world
                and row.get("location_id") == location.get("id")
            ]
            if arrays:
                location["ground_formations"] = [{
                    "id": str(row.get("id", "")), "name": str(row.get("name", "镇地阵")),
                    "owner_kind": str(row.get("owner_kind", "player")),
                    "owner_name": str(row.get("owner_name", game.player.name)),
                    "durability": round(float(row.get("durability", 0.0)), 1),
                } for row in arrays]
        from .teleport_system import public_teleport
        data['teleport'] = public_teleport(game, self.maps)
        return data

    def _public_ghost_system(self, game: GameState) -> dict[str, Any]:
        from ..rules import raw_external_hp_bonus, raw_external_mp_bonus

        player = game.player
        if not has_ghost_core(player) or (not ghost_cultivation_config().get("enabled", False) and not is_possessed(player)):
            return {"available": False, "name": GHOST_DLC_NAME}
        if is_possessed(player):
            core = player.ghost_core_state or {}
            hp_reference = max(0.0, float(player.ghost_intrinsic_hp_reference or 0.0))
            mp_reference = max(0.0, float(player.ghost_intrinsic_mp_reference or 0.0))
            hp_current = max(0.0, float(player.ghost_intrinsic_hp_current or 0.0))
            mp_current = max(0.0, float(player.ghost_intrinsic_mp_current or 0.0))
            return {
                "available": True, "name": GHOST_DLC_NAME, "suspended": True,
                "suspension_reason": "夺舍期间鬼魂核心完全沉寂；魂蚀、往生、轮回、印记、十魂与魂压全部冻结。",
                "erosion_rate_pp": round(player.ghost_soul_erosion_rate_pp, 6),
                "wangsheng": player.ghost_wangsheng_energy,
                "intrinsic_hp": {"current": hp_current, "reference": hp_reference, "carry_ratio": hp_current / max(1e-12, hp_reference)},
                "intrinsic_mp": {"current": mp_current, "reference": mp_reference, "carry_ratio": mp_current / max(1e-12, mp_reference)},
                "can_spend_wangsheng": False, "can_reincarnate": False,
                "breakthrough_probability_cap": 0.98,
                "original_realm_index": int(core.get("realm_index", 0)),
                "phase_two": self._public_ghost_phase_two(game),
            }
        ensure_ghost_cultivation_state(player)
        config = ghost_cultivation_config()
        hp_ratio, mp_ratio = hp_carry_ratio(player), mp_carry_ratio(player)
        imprints = [
            {
                "realm_index": index,
                "realm_name": REALMS[index].name,
                "layer": REALMS[index].layers,
                "count": int(player.ghost_reincarnation_imprints.get(str(index), 0)),
            }
            for index in range(1, len(REALMS))
        ]
        at_bottleneck = can_reincarnate(player)
        effective_marks = reincarnation_effective_marks(player, player.realm_index)
        total_imprints = sum(max(0, int(row["count"])) for row in imprints)
        integrity_ratio = min(hp_ratio, mp_ratio)
        probability_cap = min(
            0.98, max(0.005, float(config.get("reincarnation_final_probability_cap", 0.98))),
        )
        time_unit_years = max(1, int(WORLD_SYSTEMS["time_units"][str(player.realm_index)]))
        erosion_time_progress = max(0.0, min(
            0.999999999999, float(player.ghost_soul_erosion_time_progress),
        ))
        reincarnation_preview = None
        if at_bottleneck:
            source_count = int(player.ghost_reincarnation_imprints.get(str(player.realm_index), 0))
            reincarnation_preview = {
                "source": f"{REALMS[player.realm_index].name}{player.layer}层",
                "destination": f"{REALMS[1].name}1层",
                "next_imprint_count": source_count + 1,
                "added_bonus": float(config.get("reincarnation_bonus_per_mark", 0.05)),
                "affected_road": f"{REALMS[player.realm_index].name}及以下道路",
                "wangsheng_before": player.ghost_wangsheng_energy,
                "erosion_rate_pp": round(player.ghost_soul_erosion_rate_pp, 6),
                "intrinsic_hp_current": round(effective_intrinsic_hp(player), 4),
                "intrinsic_mp_current": round(effective_intrinsic_mp(player), 4),
                "highwater": (
                    f"{REALMS[int(player.ghost_intrinsic_highwater_realm)].name}"
                    f"{int(player.ghost_intrinsic_highwater_layer or 1)}层"
                ),
                "repeated_realm_growth_frozen": True,
            }
        return {
            "available": True,
            "name": GHOST_DLC_NAME,
            "erosion_rate_pp": round(player.ghost_soul_erosion_rate_pp, 6),
            "erosion_time": {
                "progress_ratio": round(erosion_time_progress, 8),
                "elapsed_equivalent_years": round(erosion_time_progress * time_unit_years, 6),
                "time_unit_years": time_unit_years,
                "remaining_equivalent_years": round((1.0 - erosion_time_progress) * time_unit_years, 6),
            },
            "wangsheng": player.ghost_wangsheng_energy,
            "wangsheng_cost": int(config.get("wangsheng_cost", 2)),
            "wangsheng_reduction_pp": float(config.get("wangsheng_erosion_reduction_pp", 0.02)),
            "wangsheng_available_uses": player.ghost_wangsheng_energy // max(
                1, int(config.get("wangsheng_cost", 2)),
            ),
            "can_spend_wangsheng": bool(
                player.alive and not game.pending_event and not player.imprisonment
                and player.ghost_wangsheng_energy >= int(config.get("wangsheng_cost", 2))
            ),
            "can_reincarnate": bool(
                player.alive and at_bottleneck and not game.pending_event and not game.active_trial
                and not player.imprisonment and not player.sealed_cultivation
            ),
            "intrinsic_hp": {
                "current": round(effective_intrinsic_hp(player), 4),
                "reference": round(intrinsic_hp_reference(player), 4),
                "carry_ratio": round(hp_ratio, 6),
                "external_raw": round(raw_external_hp_bonus(player), 4),
                "external_effective": round(raw_external_hp_bonus(player) * hp_ratio, 4),
            },
            "intrinsic_mp": {
                "current": round(effective_intrinsic_mp(player), 4),
                "reference": round(intrinsic_mp_reference(player), 4),
                "carry_ratio": round(mp_ratio, 6),
                "external_raw": round(raw_external_mp_bonus(player), 4),
                "external_effective": round(raw_external_mp_bonus(player) * mp_ratio, 4),
            },
            "imprints": imprints,
            "total_imprints": total_imprints,
            "effective_marks": effective_marks,
            "breakthrough_bonus": reincarnation_breakthrough_bonus(player, player.realm_index),
            "breakthrough_probability_cap": probability_cap,
            "soul_integrity": {
                "ratio": round(integrity_ratio, 6),
                "label": soul_integrity_label(integrity_ratio),
            },
            "reincarnation_preview": reincarnation_preview,
            "highwater": {
                "realm_index": player.ghost_intrinsic_highwater_realm,
                "layer": player.ghost_intrinsic_highwater_layer,
                "name": (
                    f"{REALMS[int(player.ghost_intrinsic_highwater_realm)].name}"
                    f"{int(player.ghost_intrinsic_highwater_layer or 1)}层"
                ),
            },
            "last_anchor": (
                {
                    "realm_index": player.ghost_last_reincarnation_realm,
                    "layer": player.ghost_last_reincarnation_layer,
                    "name": (
                        f"{REALMS[int(player.ghost_last_reincarnation_realm)].name}"
                        f"{int(player.ghost_last_reincarnation_layer or 1)}层"
                    ),
                }
                if player.ghost_last_reincarnation_realm is not None else None
            ),
            "suspended": False,
            "phase_two": self._public_ghost_phase_two(game),
        }

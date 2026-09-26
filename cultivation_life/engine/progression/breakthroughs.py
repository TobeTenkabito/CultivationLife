from __future__ import annotations

import copy
import random
from typing import Any
from ...content_registry import (
    ITEM_CATALOG,
    REALMS,
    TECHNIQUE_CATALOG,
    TECHNIQUE_ELEMENT_NAMES,
    WORLD_SYSTEMS,
)
from ...models import GameState, HistoryRecord, Player, SectNpc
from ...rules import (
    assign_technique,
    expected_combat_power,
    learn_technique,
    max_hp,
    max_mp,
    opportunity_required,
    public_player,
    realm,
    root_definition,
    root_elements,
    roll_lifespan,
)
from ...system.crafting_system import crafted_artifact_bonuses
from ...monster_general_traits import grant_random_general_monster_trait
from ...system.ghost_system import (
    ghost_cultivation_active,
    grant_intrinsic_progression_if_new_highwater,
    grant_wangsheng,
    reincarnation_breakthrough_bonus,
)
from ..dependencies import BreakthroughDependencies


def _resolve_breakthroughs(deps: BreakthroughDependencies, game: GameState, rng: random.Random) -> None:
    player = game.player
    if player.cultivation_suppression:
        return
    if player.sealed_cultivation:
        player.opportunity = min(player.opportunity, opportunity_required(player))
        return
    if player.spirit_root == "none":
        player.opportunity = 0
        return
    safety = 0
    while player.alive and player.opportunity >= opportunity_required(player) and safety < 32:
        safety += 1
        required = opportunity_required(player)
        # 仙境没有层级与前中后期；后续升级规则尚未开放，不能误走旧突破链。
        if player.realm_index >= 9:
            player.opportunity = min(player.opportunity, required)
            player.awaiting_major_breakthrough = False
            player.awaiting_minor_breakthrough = False
            return
        if player.world == "spirit" and player.realm_index == 8 and player.layer >= REALMS[8].layers:
            player.awaiting_ascension = True
            player.awaiting_major_breakthrough = False
            player.opportunity = min(player.opportunity, required)
            if not any(entry.event_id == "SYS_CELESTIAL_ASCENSION_READY" for entry in game.history):
                game.history.append(HistoryRecord(
                    "SYS_CELESTIAL_ASCENSION_READY", 1, player.age, "仙门可叩", None, "ready",
                    "大乘九层道果与机缘均已圆满，可以发动专属的九重渡劫飞升。",
                    {"awaiting_ascension":True}, ["system", "ascension", "celestial", "milestone"],
                ))
            return
        if (
            player.path == "demonic" and player.world == "true_demon"
            and player.realm_index == 8 and player.layer >= REALMS[8].layers
        ):
            player.awaiting_ascension = True
            player.awaiting_major_breakthrough = False
            player.opportunity = min(player.opportunity, required)
            if not any(entry.event_id == "SYS_ASURA_ASCENSION_READY" for entry in game.history):
                game.history.append(HistoryRecord(
                    "SYS_ASURA_ASCENSION_READY", 1, player.age, "修罗天关可叩", None, "ready",
                    "魔尊九层道果与机缘均已圆满，可以发动九重修罗天魔劫。",
                    {"awaiting_ascension":True}, ["system", "ascension", "asura", "demonic", "milestone"],
                ))
            return
        if (
            player.path == "demonic" and player.world == "human"
            and player.realm_index == 5 and player.layer >= 3
        ):
            player.awaiting_ascension = True
            player.opportunity = min(player.opportunity, required)
            if not any(entry.event_id == "SYS_HUMAN_DEMONIC_LIMIT" for entry in game.history):
                game.history.append(HistoryRecord(
                    "SYS_HUMAN_DEMONIC_LIMIT", 1, player.age, "魔界飞升瓶颈", None, "blocked",
                    "你已在人界修至化魔初期；下一步须飞升魔界。",
                    {"awaiting_ascension": True}, ["system", "realm_limit", "demonic", "milestone"],
                ))
            return
        if (
            player.path == "demonic" and player.world == "demon"
            and player.realm_index == 5 and player.layer >= REALMS[5].layers
        ):
            player.awaiting_ascension = True
            player.opportunity = min(player.opportunity, required)
            if not any(entry.event_id == "SYS_DEMON_REALM_LIMIT" for entry in game.history):
                game.history.append(HistoryRecord(
                    "SYS_DEMON_REALM_LIMIT", 1, player.age, "魔界绝巅", None, "blocked",
                    "你已修至化魔后期九层；炼魔境须先飞升真魔界。",
                    {"awaiting_ascension": True}, ["system", "realm_limit", "demonic", "milestone"],
                ))
            return
        if player.world == "human" and player.realm_index == 5 and player.layer >= 3:
            player.opportunity = min(player.opportunity, required)
            if not player.awaiting_spirit_realm_crossing:
                player.awaiting_spirit_realm_crossing = True
                game.history.append(HistoryRecord(
                    "SYS_HUMAN_REALM_LIMIT", 1, player.age, "人界绝巅", None, "blocked",
                    "人界法则不足以支撑化神中期。你只能停留在化神初期，等待未来寻得偷渡灵界之法。",
                    {"awaiting_spirit_realm_crossing": True}, ["system", "realm_limit", "milestone"],
                ))
            return
        if player.realm_index == len(REALMS) - 1 and player.layer == REALMS[-1].layers:
            player.awaiting_ascension = True
            player.opportunity = min(player.opportunity, required)
            return
        old_realm = realm(player)
        old_label = public_player(player)["realm_name"]
        if player.layer >= old_realm.layers:
            player.opportunity = min(player.opportunity, required)
            if not player.awaiting_major_breakthrough:
                player.awaiting_major_breakthrough = True
                game.history.append(HistoryRecord(
                    "SYS_BOTTLENECK_READY", 1, player.age, "大境界瓶颈", None, "ready",
                    f"{old_label}机缘已经圆满。你可以继续准备，并在合适时主动突破瓶颈。",
                    {"awaiting_major_breakthrough": True}, ["system", "breakthrough", "major"],
                ))
            return
        if player.layer in deps._manual_minor_layers(player):
            player.opportunity = min(player.opportunity, required)
            if not player.awaiting_minor_breakthrough:
                player.awaiting_minor_breakthrough = True
                target_name = deps._minor_layer_target(player)
                game.history.append(HistoryRecord(
                    "SYS_MINOR_BOTTLENECK_READY", 1, player.age, "小境界瓶颈", None, "ready",
                    f"{old_label}机缘已经圆满。你可以服用对应丹药并手动冲击{target_name}。",
                    {"awaiting_minor_breakthrough": True},
                    ["system", "breakthrough", "minor"],
                ))
            return
        # 练气层级仍沿用自动检定；筑基以后所有层级均停留等待手动冲击。
        chance = deps._breakthrough_chance(player, major=False, allow_aids=False)
        player.natal_origin_penalty = 0.0
        if rng.random() >= chance["final"]:
            player.opportunity = required * float(WORLD_SYSTEMS["breakthrough"]["minor_failure_retention"])
            gain = deps._sage_scaled_gain(
                player, float(WORLD_SYSTEMS["breakthrough"]["minor_failure_heart_demon"]),
                "heart_demon_gain_reduction",
            )
            player.heart_demon += gain
            game.history.append(HistoryRecord(
                "SYS_MINOR_BREAKTHROUGH_FAILED", 1, player.age, "小境界冲关失利", None, "failed",
                f"从{old_label}继续破境失败（成功率 {chance['final']:.1%}）；心魔 +{gain:g}。",
                {"chance": chance, "heart_demon_gain": gain}, ["system", "breakthrough", "minor", "negative"],
            ))
            return
        player.opportunity = max(0.0, player.opportunity - required)
        if player.realm_index >= 6:
            deps._start_breakthrough_trial(
                game, "traditional", player.realm_index, player.realm_index, old_label,
                major=False, rng=rng,
            )
            return
        deps._complete_minor_breakthrough(game, rng, old_label)


def _manual_minor_layers(player: Player) -> set[int]:
    if player.realm_index < 2:
        return set()
    if player.world == "human" and player.realm_index == 5:
        return set()
    return set(range(1, realm(player).layers))


def _manual_breakthrough_kind(deps: BreakthroughDependencies, player: Player) -> str | None:
    monster_upper_evolution = bool(
        player.path == "monster" and deps.bloodline_content_available()
        and WORLD_SYSTEMS.get("world_profiles", {}).get("nether", {}).get("enabled")
        and player.layer >= realm(player).layers
        and (
            (player.realm_index == 8 and player.world in {"monster_realm", "phantom_underworld"})
            or (9 <= player.realm_index < len(REALMS) - 1 and player.world == "nether")
        )
    )
    if monster_upper_evolution:
        return "major"
    if player.realm_index >= 9 or (player.realm_index == 8 and player.layer >= REALMS[8].layers):
        return None
    if player.layer >= realm(player).layers and player.realm_index < len(REALMS) - 1:
        return "major"
    if player.layer in deps._manual_minor_layers(player):
        return "minor"
    return None


def _minor_stage_target(player: Player) -> str:
    stage = "中期" if player.layer == 3 else "后期"
    return f"{realm(player).name}{stage}"


def _minor_layer_target(deps: BreakthroughDependencies, player: Player) -> str:
    shell = SectNpc("target", "", "", player.realm_index, player.layer + 1, 0, 1, path=player.path)
    return deps._npc_realm_name(shell)


def _minor_pity_key(player: Player) -> str:
    return f"minor:{player.realm_index}:{player.layer}"


def _minor_pity_bonus(deps: BreakthroughDependencies, player: Player) -> float:
    config = WORLD_SYSTEMS["breakthrough"].get("minor_pity", {})
    if player.layer not in {int(layer) for layer in config.get("eligible_source_layers", [])}:
        return 0.0
    failures = int(player.breakthrough_pity.get(deps._minor_pity_key(player), 0))
    return min(float(config.get("max_bonus", 0)), failures * float(config.get("bonus_per_failure", 0)))


def _record_minor_pity_failure(deps: BreakthroughDependencies, player: Player) -> float:
    if deps._minor_pity_bonus(player) == 0 and player.layer not in set(
        WORLD_SYSTEMS["breakthrough"].get("minor_pity", {}).get("eligible_source_layers", [])
    ):
        return 0.0
    key = deps._minor_pity_key(player)
    player.breakthrough_pity[key] = int(player.breakthrough_pity.get(key, 0)) + 1
    return deps._minor_pity_bonus(player)


def _clear_minor_pity(deps: BreakthroughDependencies, player: Player) -> None:
    player.breakthrough_pity.pop(deps._minor_pity_key(player), None)


def _major_breakthrough_requirement(player: Player) -> dict[str, Any]:
    if player.path == "demonic" and player.world == "demon" and player.realm_index == 5:
        return {
            "met": False,
            "reason": "炼魔境必须先飞升真魔界。",
            "missing_affinities": [],
        }
    if player.realm_index == 5:
        five = {"metal", "wood", "water", "fire", "earth"}
        owned = set(root_elements(player.spirit_root)) | set(player.additional_roots)
        missing = [TECHNIQUE_ELEMENT_NAMES[element] for element in ("metal", "wood", "water", "fire", "earth") if element not in owned]
        return {
            "met": not missing,
            "reason": "突破炼虚必须具备完整五行灵根；当前尚缺" + "、".join(missing) + "灵根。" if missing else "五行灵根齐备。",
            "missing_affinities": missing,
        }
    return {"met": True, "reason": "机缘圆满后可主动突破。", "missing_affinities": []}


def _root_probability_group(player: Player) -> str:
    if player.spirit_root.startswith("acquired_"):
        return "acquired"
    tier = str(root_definition(player.spirit_root).get("tier", ""))
    return {
        "伪灵根": "pseudo", "天灵根": "heavenly", "极品灵根": "supreme",
        "变异灵根": "mutated", "法则灵根": "law", "异世界灵根": "otherworld",
        "后天灵根": "acquired", "后天变异灵根": "acquired",
    }.get(tier, "acquired")


def _breakthrough_chance(deps: BreakthroughDependencies, player: Player, major: bool, allow_aids: bool = True) -> dict[str, float]:
    config = WORLD_SYSTEMS["breakthrough"]
    source = player.realm_index
    if major and source == 0:
        base = 1.0
    elif major:
        table = config["major_base"][str(source)]
        base = float(table.get(deps._root_probability_group(player), table.get("default", 0.01)))
    else:
        base = 1.0 if source == 1 else float(config["minor_base"].get(str(source), 1.0))
    dependent_bonus = 0.0
    if player.concubine_status:
        owner_rank = (
            int(player.concubine_status.get("owner_realm_index", 0)),
            int(player.concubine_status.get("owner_layer", 1)),
        )
        if (player.realm_index, player.layer) < owner_rank:
            dependent_bonus = 0.02
    concubine_base_bonus = min(0.02, player.concubine_breakthrough_bonus) + dependent_bonus
    base += concubine_base_bonus
    scope = f"{'major' if major else 'minor'}:{source}"
    aid_bonus = sum(
        float(ITEM_CATALOG[item_id].breakthrough_bonus)
        for item_id in player.active_breakthrough_aids
        if item_id in ITEM_CATALOG and ITEM_CATALOG[item_id].breakthrough_scope == scope
    ) if (
        allow_aids
        and player.path != "demonic"
        and (
            not ghost_cultivation_active(player)
            or (
                player.realm_index >= 4
                and (not major or player.realm_index >= 6)
            )
        )
    ) else 0.0
    devouring_bonus = player.devouring_breakthrough_bonus if player.path == "demonic" else 0.0
    companion_bonus = (
        float(WORLD_SYSTEMS["relationship"]["companion_breakthrough_bonus"])
        if deps._joint_companion_eligible(player) else 0.0
    )
    artifact_bonus = sum(
        float(item.passive_breakthrough_bonus) * item.quantity for item in player.inventory
        if item.passive_breakthrough_bonus > 0
        and item.passive_breakthrough_max_realm is not None
        and source <= int(item.passive_breakthrough_max_realm)
    )
    artifact_bonus += crafted_artifact_bonuses(player)["breakthrough_bonus"]
    penalty = min(
        float(config["heart_demon_penalty_cap"]),
        player.heart_demon * float(config["heart_demon_penalty_per_point"]),
    )
    pity_bonus = 0.0 if major else deps._minor_pity_bonus(player)
    body_training_bonus = (
        player.body_training // 20
        * float(WORLD_SYSTEMS["body_cultivation"]["cultivation_breakthrough_bonus_per_20_layers"])
    )
    optimal = config.get("optimal_state", {})
    optimal_state_bonus = (
        float(optimal.get("bonus", 0))
        if player.hp >= max_hp(player) * float(optimal.get("hp_ratio", 0.8))
        and player.mp >= max_mp(player) * float(optimal.get("mp_ratio", 0.8))
        else 0.0
    )
    reincarnation_bonus = reincarnation_breakthrough_bonus(player, source)
    sage_bonus = max(-0.08, min(0.05, float(player.sage_effects.get("breakthrough_bonus", 0.0))))
    # 轮回经验本身不封顶，但所有流派的最终有效突破率都必须保留
    # 至少 2% 的失败风险；扩展配置也不能绕过这一全局硬上限。
    configured_cap = float(
        WORLD_SYSTEMS.get("ghost_cultivation", {}).get("reincarnation_final_probability_cap", 0.98)
    ) if ghost_cultivation_active(player) else 0.98
    final_cap = min(0.98, max(0.01, configured_cap))
    final = max(0.01, min(
        final_cap, base + aid_bonus + companion_bonus + artifact_bonus + pity_bonus
        + body_training_bonus + optimal_state_bonus + devouring_bonus + reincarnation_bonus + sage_bonus - penalty,
    ))
    final = max(0.01, final - max(0.0, player.natal_origin_penalty))
    return {
        "base": base, "aid_bonus": aid_bonus, "companion_bonus": companion_bonus,
        "concubine_base_bonus": concubine_base_bonus,
        "artifact_bonus": artifact_bonus, "pity_bonus": pity_bonus,
        "devouring_bonus": devouring_bonus,
        "reincarnation_bonus": reincarnation_bonus,
        "sage_bonus": sage_bonus,
        "body_training_bonus": body_training_bonus, "optimal_state_bonus": optimal_state_bonus,
        "heart_demon_penalty": penalty, "final": final,
        "natal_origin_penalty": player.natal_origin_penalty,
    }


def _joint_companion_eligible(player: Player) -> dict[str, Any] | None:
    companion = player.dao_companion
    if not companion or not companion.get("alive", True) or companion.get("world", player.world) != player.world:
        return None
    if not player.technique or companion.get("main_technique_id") != player.technique.id:
        return None
    if int(companion.get("realm_index", -1)) != player.realm_index:
        return None
    return companion


def _complete_joint_companion_breakthrough(deps: BreakthroughDependencies, game: GameState, rng: random.Random) -> None:
    joint = game.player.joint_companion_breakthrough
    companion = game.player.dao_companion
    if not joint:
        return
    game.player.joint_companion_breakthrough = None
    if not companion or companion.get("id") != joint.get("id") or not companion.get("alive", True):
        return
    old_label = str(companion.get("realm_name", "原境界"))
    companion["realm_index"] = game.player.realm_index
    companion["layer"] = game.player.layer
    shell = SectNpc("joint", companion["name"], "", game.player.realm_index, game.player.layer, 0, 1)
    companion["realm_name"] = deps._npc_realm_name(shell)
    companion["cultivation_progress"] = 0.0
    lifespan_gain = 0
    if bool(joint.get("major")):
        span = REALMS[game.player.realm_index].lifespan
        if span is None:
            companion["lifespan"] = None
        else:
            old_lifespan = int(companion.get("lifespan") or 0)
            rolled = rng.randint(*span) * deps._npc_lifespan_multiplier(str(companion.get("path", "dao")))
            companion["lifespan"] = max(old_lifespan, rolled, int(companion.get("age", 0)) + 1)
            lifespan_gain = max(0, int(companion["lifespan"]) - old_lifespan)
    elif game.player.layer in {4, 7} and companion.get("lifespan") is not None:
        stage = "middle" if game.player.layer == 4 else "late"
        stage_range = WORLD_SYSTEMS.get("stage_lifespan_bonus", {}).get(REALMS[game.player.realm_index].id, {}).get(stage)
        if stage_range:
            lifespan_gain = rng.randint(*stage_range) * deps._npc_lifespan_multiplier(str(companion.get("path", "dao")))
            companion["lifespan"] = int(companion["lifespan"]) + lifespan_gain
    if game.player.realm_index >= 6 and companion.get("next_tribulation_age") is None:
        thunder = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
        companion["next_tribulation_age"] = int(companion.get("age", game.player.age)) + int(thunder["interval_years"])
        companion["tribulation_count"] = int(companion.get("tribulation_count", 0))
        companion["tribulation_power"] = float(thunder["base_power"]) * float(thunder["power_multiplier"]) ** int(companion["tribulation_count"])
    npc = deps._find_npc(game, str(companion.get("id", "")))
    if npc:
        npc.realm_index = game.player.realm_index
        npc.layer = game.player.layer
        npc.cultivation_progress = 0.0
        npc.lifespan = companion.get("lifespan")
        npc.next_tribulation_age = companion.get("next_tribulation_age")
        npc.tribulation_count = int(companion.get("tribulation_count", 0))
        npc.tribulation_power = companion.get("tribulation_power")
    game.history.append(HistoryRecord(
        "SYS_COMPANION_JOINT_BREAKTHROUGH", 1, game.player.age, "同心破境", None, "success",
        f"{companion['name']}与你运转同一主修功法，一同从{old_label}突破至{companion['realm_name']}。"
        + (" 寿元自此无尽。" if companion.get("lifespan") is None else f" 寿元增长 {lifespan_gain} 年。" if lifespan_gain else ""),
        {"companion_id": companion["id"], "realm": [old_label, companion["realm_name"]]},
        ["system", "relationship", "dao_companion", "breakthrough"],
    ))


def _consume_breakthrough_aids(player: Player, scope: str) -> None:
    player.active_breakthrough_aids = [
        item_id for item_id in player.active_breakthrough_aids
        if ITEM_CATALOG.get(item_id) and ITEM_CATALOG[item_id].breakthrough_scope != scope
    ]


def _start_breakthrough_trial(
    deps: BreakthroughDependencies, game: GameState, kind: str, source: int, target: int, old_label: str,
    major: bool, rng: random.Random,
) -> None:
    event_ids = {
        "traditional": [
            "EVT_BREAKTHROUGH_TRADITIONAL_001", "EVT_BREAKTHROUGH_TRADITIONAL_002",
            "EVT_BREAKTHROUGH_TRADITIONAL_003",
        ],
        "heavenly": [
            "EVT_BREAKTHROUGH_HEAVENLY_001", "EVT_BREAKTHROUGH_HEAVENLY_002",
            "EVT_BREAKTHROUGH_HEAVENLY_003", "EVT_BREAKTHROUGH_HEAVENLY_004",
            "EVT_BREAKTHROUGH_HEAVENLY_005",
        ],
        "heavenly_demon": ["EVT_HEAVENLY_DEMON_TRIBULATION_001"],
    }[kind]
    game.active_trial = {
        "kind": kind, "source_realm": source, "target_realm": target,
        "target_layer": 1 if major else game.player.layer + 1,
        "major": major, "old_label": old_label, "step_index": 0,
        "event_ids": event_ids,
        "lethal": bool(source == 3 or source >= 6),
    }
    if kind == "heavenly_demon":
        game.active_trial.update(base_rounds_completed=0, total_battles=0, soul_battles=0)
        deps._queue_heavenly_demon_battle(game, rng, soul=None)
    else:
        game.pending_event = deps._instantiate_event(deps.events_by_id[event_ids[0]], game, rng)


def _queue_heavenly_demon_battle(
    deps: BreakthroughDependencies, game: GameState, rng: random.Random, soul: dict[str, Any] | None,
) -> None:
    trial = game.active_trial or {}
    config = WORLD_SYSTEMS["demonic_cultivation"]["heavenly_demon_tribulation"]
    if soul is None:
        round_index = int(trial.get("base_rounds_completed", 0))
        ratios = list(config["outer_demon_power_ratios"])
        ratio = float(ratios[min(round_index, len(ratios) - 1)])
        target_power = expected_combat_power(int(trial["target_realm"]), 1) * ratio
        event_id = "EVT_HEAVENLY_DEMON_TRIBULATION_001"
        label = f"第 {round_index + 1}/{int(config['base_rounds'])} 重域外天魔"
        runtime = {"battle_kind":"outer_demon", "target_name":label, "target_power":round(target_power, 1)}
    else:
        realm_index = int(soul.get("realm_index", 1))
        inherited_power = float(soul.get("combat_power", 0))
        if inherited_power <= 0:
            inherited_power = expected_combat_power(realm_index, REALMS[realm_index].layers)
        target_power = inherited_power * 0.50
        event_id = "EVT_HEAVENLY_DEMON_SOUL_001"
        label = f"{soul.get('name', '无名元神')}的反噬元神"
        runtime = {
            "battle_kind":"foreign_soul", "target_name":label,
            "target_power":round(target_power, 1), "soul_id":soul.get("id"),
        }
    event = deps._instantiate_event(deps.events_by_id[event_id], game, rng)
    event["runtime"] = runtime
    trial["battle_runtime"] = copy.deepcopy(runtime)
    event["body"] += f" 当前对手：{label}，战力约 {target_power:.0f}。"
    game.pending_event = event


def _resolve_heavenly_demon_battle(
    deps: BreakthroughDependencies, game: GameState, step: str, rng: random.Random,
) -> tuple[str, str]:
    player = game.player
    trial = game.active_trial
    if not trial:
        raise ValueError("当前没有进行中的天魔劫")
    runtime = dict(trial.get("battle_runtime", {}))
    target_power = max(1.0, float(runtime.get("target_power", 1)))
    own_power = deps._player_battle_power(game)
    ratio = own_power / target_power
    target_name = str(runtime.get("target_name", "域外天魔"))
    hp_before, mp_before = player.hp, player.mp
    combat_result, combat_summary = deps._combat(game, {
        **runtime,
        "target_name": target_name,
        "target_power": target_power,
        "target_realm_index": int(trial.get("target_realm", player.realm_index)),
        "target_layer": 1,
        "combat_type": "trial",
        "path": "demonic",
        "action": "repel",
        "enemy_objective": "kill",
        "max_rounds": 5,
    }, False, rng)
    won = combat_result == "victory"
    if not won:
        player.joint_companion_breakthrough = None
        game.active_trial = None
        deps._die(game, f"天魔劫中不敌{target_name}，肉身与元神尽被魔影吞没", "SYS_HEAVENLY_DEMON_TRIBULATION_FAILED")
        if game.last_combat_report:
            game.last_combat_report["result"] = "dead"
            game.last_combat_report["result_grade"] = "溃败"
        return "dead", f"{combat_summary} 天魔劫无法撤退，你在交战失败后陨落。"

    config = WORLD_SYSTEMS["demonic_cultivation"]["heavenly_demon_tribulation"]
    hp_loss = max(0.0, hp_before - player.hp)
    mp_loss = max(0.0, mp_before - player.mp)
    gain = float(REALMS[int(trial["target_realm"])].opportunity_base) * float(config["victory_opportunity_ratio"])
    deps._add_opportunity(player, gain)
    trial["total_battles"] = int(trial.get("total_battles", 0)) + 1
    if runtime.get("battle_kind") == "foreign_soul" or step == "heavenly_demon_soul":
        trial["soul_battles"] = int(trial.get("soul_battles", 0)) + 1
    else:
        trial["base_rounds_completed"] = int(trial.get("base_rounds_completed", 0)) + 1

    souls = list(player.foreign_souls)
    if souls and rng.random() < float(config["soul_lure_chance"]):
        soul = rng.choice(souls)
        deps._queue_heavenly_demon_battle(game, rng, soul=soul)
        return "trial_step_success", (
            f"{combat_summary} 天魔劫阶段胜利（初始综合评分比 {ratio:.2f}），"
            f"机缘 +{gain:.0f}；域外天魔又勾起了{soul.get('name', '一道元神')}的反噬。"
        )
    if int(trial.get("base_rounds_completed", 0)) < int(config["base_rounds"]):
        deps._queue_heavenly_demon_battle(game, rng, soul=None)
        return "trial_step_success", (
            f"{combat_summary} 天魔劫阶段胜利（初始综合评分比 {ratio:.2f}），"
            f"机缘 +{gain:.0f}；下一重域外天魔已经显形。"
        )

    old_label = str(trial.get("old_label", public_player(player)["realm_name"]))
    total_battles = int(trial.get("total_battles", 0))
    soul_battles = int(trial.get("soul_battles", 0))
    deps._complete_major_breakthrough(game, rng, old_label)
    game.active_trial = None
    return "trial_completed", (
        f"你击溃最后一重魔影，HP -{hp_loss:.0f}、MP -{mp_loss:.0f}，机缘 +{gain:.0f}；"
        f"本次天魔劫共交战 {total_battles} 次，其中元神反噬 {soul_battles} 次。"
    )


def _complete_major_breakthrough(deps: BreakthroughDependencies, game: GameState, rng: random.Random, old_label: str) -> None:
    player = game.player
    player.awaiting_major_breakthrough = False
    player.awaiting_minor_breakthrough = False
    player.heart_demon = max(0.0, player.heart_demon - 5)
    player.realm_index += 1
    player.layer = 1
    grant_intrinsic_progression_if_new_highwater(player)
    grant_wangsheng(player)
    deps._raise_divine_sense_one_level(player)
    if player.path == "demonic" and player.realm_index in {4, 7}:
        technique_id = "TECH_HEAVENLY_DEMON_SENSE" if player.realm_index == 4 else "TECH_MYRIAD_SOUL_SENSE"
        unlocked = copy.deepcopy(TECHNIQUE_CATALOG[technique_id])
        learn_technique(player, unlocked)
        assign_technique(player, unlocked, "divine_sense")
    rolled_lifespan = roll_lifespan(player, rng)
    if ghost_cultivation_active(player):
        player.lifespan = None
    elif rolled_lifespan is None:
        player.lifespan = None
    elif player.lifespan is None:
        player.lifespan = rolled_lifespan
    else:
        player.lifespan = max(player.lifespan, rolled_lifespan)
    if realm(player).id == "void" and player.next_tribulation_age is None:
        thunder = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
        player.next_tribulation_age = player.age + int(thunder["interval_years"])
        player.tribulation_power = float(thunder["base_power"]) * float(thunder["power_multiplier"]) ** player.tribulation_count
    player.hp = max_hp(player)
    player.mp = max_mp(player)
    target_label = public_player(player)["realm_name"]
    game.history.append(HistoryRecord(
        "SYS_MAJOR_BREAKTHROUGH", 1, player.age, "突破瓶颈", None, "success",
        f"你通过全部关隘，从{old_label}突破至{target_label}。",
        {"realm": [old_label, target_label]}, ["system", "breakthrough", "major"],
    ))
    general_trait = grant_random_general_monster_trait(
        player, rng, bloodline_available=deps.bloodline_content_available(),
    )
    if general_trait:
        game.history.append(HistoryRecord(
            "SYS_MONSTER_GENERAL_TRAIT", 1, player.age, "凡妖蜕性",
            general_trait["id"], "acquired",
            f"血脉谱系未启用，你在大境界蜕变中获得通用特质【{general_trait['name']}】：{general_trait['description']}",
            {"trait_id": general_trait["id"], "realm_index": player.realm_index},
            ["system", "monster", "trait", "breakthrough", "major", "milestone"],
        ))
    deps._complete_joint_companion_breakthrough(game, rng)


def _complete_minor_breakthrough(deps: BreakthroughDependencies, game: GameState, rng: random.Random, old_label: str) -> None:
    player = game.player
    player.awaiting_minor_breakthrough = False
    player.heart_demon = max(0.0, player.heart_demon - 1)
    old_realm = realm(player)
    player.layer += 1
    grant_intrinsic_progression_if_new_highwater(player)
    grant_wangsheng(player)
    deps._raise_divine_sense_one_level(player)
    lifespan_gain = 0
    stage = "middle" if player.layer == 4 else "late" if player.layer == 7 else None
    stage_ranges = WORLD_SYSTEMS.get("stage_lifespan_bonus", {}).get(old_realm.id, {})
    if stage and player.lifespan is not None and stage in stage_ranges:
        lifespan_gain = rng.randint(*stage_ranges[stage])
        if player.path == "monster":
            lifespan_gain *= int(WORLD_SYSTEMS.get("monster_cultivation", {}).get("lifespan_multiplier", 3))
        player.lifespan += lifespan_gain
    player.hp = max_hp(player)
    player.mp = max_mp(player)
    game.history.append(HistoryRecord(
        "SYS_BREAKTHROUGH", 1, player.age, "破境", None, "success",
        f"冲关成功，从{old_label}突破至{public_player(player)['realm_name']}。"
        + (f"境界阶段蜕变令寿元增长 {lifespan_gain} 年。" if lifespan_gain else ""),
        {"realm": [old_label, public_player(player)["realm_name"]], **({"lifespan_gain": lifespan_gain} if lifespan_gain else {})},
        ["system", "breakthrough", "minor"],
    ))
    deps._complete_joint_companion_breakthrough(game, rng)

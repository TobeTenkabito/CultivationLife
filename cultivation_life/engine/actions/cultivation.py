from __future__ import annotations

from typing import Any
from ...content_registry import REALMS, WORLD_SYSTEMS
from ...models import HistoryRecord, Player, SectNpc
from ...rules import (
    max_hp,
    max_mp,
    opportunity_required,
    public_player,
    realm,
    divine_sense_breakthrough_cost,
    divine_sense_level,
)
from ...runtime import decode_rng, encode_rng, now_iso
from ...system.ghost_system import grant_intrinsic_growth
from ..dependencies import CultivationActionDependencies


def _cultivation_sense_requirement(realm_index: int, layer: int) -> int:
    """Natural divine-sense rank earned by reaching one cultivation layer."""
    bounded_realm = max(0, min(int(realm_index), len(REALMS) - 1))
    bounded_layer = max(1, min(int(layer), REALMS[bounded_realm].layers))
    return sum(definition.layers for definition in REALMS[:bounded_realm]) + bounded_layer - 1


def _secret_art_realm_name(deps: CultivationActionDependencies, player: Player, realm_index: int, layer: int = 1) -> str:
    shell = SectNpc(
        "secret-art", player.name, "", int(realm_index), int(layer),
        player.age, player.lifespan, path=player.path, world=player.world,
    )
    return deps._npc_realm_name(shell)


def manage_secret_art(
    deps: CultivationActionDependencies, game_id: str, art: str, action: str, realm_index: int | None = None,
    layer: int | None = None,
) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if not player.alive:
        raise ValueError("此生已经结束")
    if art not in {"conceal", "suppress"} or action not in {"activate", "cancel"}:
        raise ValueError("未知秘法操作")

    if art == "conceal" and action == "cancel":
        if not player.cultivation_concealment:
            raise ValueError("当前没有运转收敛修为")
        old_name = deps._secret_art_realm_name(
            player, player.cultivation_concealment["realm_index"],
            player.cultivation_concealment.get("layer", 1),
        )
        player.cultivation_concealment = None
        title, result = "散去敛息", "cancelled"
        summary = f"你散去收敛修为，对外气机不再停留于{old_name}。"
    elif art == "suppress" and action == "cancel":
        suppression = player.cultivation_suppression
        if not suppression:
            raise ValueError("当前没有运转压制修为")
        hp_ratio = player.hp / max(1.0, max_hp(player))
        mp_ratio = player.mp / max(1.0, max_mp(player))
        suppressed_name = deps._secret_art_realm_name(player, player.realm_index, player.layer)
        accrued_opportunity = max(0.0, float(player.opportunity))
        player.realm_index = int(suppression["realm_index"])
        player.layer = int(suppression["layer"])
        player.opportunity = float(suppression.get("opportunity", 0.0)) + accrued_opportunity
        player.awaiting_ascension = bool(suppression.get("awaiting_ascension", False))
        player.awaiting_major_breakthrough = bool(suppression.get("awaiting_major_breakthrough", False))
        player.awaiting_minor_breakthrough = bool(suppression.get("awaiting_minor_breakthrough", False))
        player.awaiting_spirit_realm_crossing = bool(
            suppression.get("awaiting_spirit_realm_crossing", False)
        )
        player.active_breakthrough_aids = list(suppression.get("active_breakthrough_aids", []))
        if player.next_tribulation_age is None:
            due_age = suppression.get("next_tribulation_age")
            remaining = suppression.get("tribulation_remaining")
            player.next_tribulation_age = (
                int(due_age) if due_age is not None else
                player.age + int(remaining) if remaining is not None else None
            )
        player.cultivation_suppression = None
        player.hp = max(1.0, max_hp(player) * max(0.0, min(1.0, hp_ratio)))
        player.mp = max(0.0, max_mp(player) * max(0.0, min(1.0, mp_ratio)))
        true_name = deps._secret_art_realm_name(player, player.realm_index, player.layer)
        title, result = "解开修为", "cancelled"
        summary = f"你解除秘法，将真正修为从{suppressed_name}完整复原至{true_name}；神识等级始终未变。"
        guixu_ejection = deps._enforce_guixu_rank_boundary(game, "suppression_released")
        if guixu_ejection:
            summary += guixu_ejection
    else:
        if game.pending_event or game.active_trial or player.imprisonment:
            raise ValueError("事件、劫数或服刑期间不能改换修为秘法")
        if realm_index is None:
            raise ValueError("请选择目标境界")
        target_realm = int(realm_index)
        if not 0 <= target_realm < len(REALMS):
            raise ValueError("秘法目标境界不存在")
        target_layer = int(layer if layer is not None else 1)
        if not 1 <= target_layer <= REALMS[target_realm].layers:
            raise ValueError("秘法目标层数不存在")
        if (target_realm, target_layer) >= (player.realm_index, player.layer):
            raise ValueError("秘法目标必须低于当前生效修为")
        target_name = deps._secret_art_realm_name(player, target_realm, target_layer)
        if art == "conceal":
            player.cultivation_concealment = {
                "realm_index": target_realm, "layer": target_layer,
            }
            title, result = "收敛修为", "activated"
            summary = (
                f"你将对外气机收敛为{target_name}。自身属性与突破状态不变，"
                "主动遭遇会更偏向这一层次的推荐战力。"
            )
        else:
            if player.sealed_cultivation:
                raise ValueError("下界法则正在封印真实道果，不能再叠加压制修为")
            if player.cultivation_suppression:
                raise ValueError("当前已经处于压制修为状态")
            hp_ratio = player.hp / max(1.0, max_hp(player))
            mp_ratio = player.mp / max(1.0, max_mp(player))
            player.cultivation_suppression = {
                "realm_index": player.realm_index,
                "layer": player.layer,
                "opportunity": player.opportunity,
                "awaiting_ascension": player.awaiting_ascension,
                "awaiting_major_breakthrough": player.awaiting_major_breakthrough,
                "awaiting_minor_breakthrough": player.awaiting_minor_breakthrough,
                "awaiting_spirit_realm_crossing": player.awaiting_spirit_realm_crossing,
                "active_breakthrough_aids": list(player.active_breakthrough_aids),
                "next_tribulation_age": player.next_tribulation_age,
                "tribulation_remaining": (
                    max(0, player.next_tribulation_age - player.age)
                    if player.next_tribulation_age is not None else None
                ),
            }
            player.realm_index = target_realm
            player.layer = target_layer
            player.opportunity = 0.0
            player.awaiting_ascension = False
            player.awaiting_major_breakthrough = False
            player.awaiting_minor_breakthrough = False
            player.awaiting_spirit_realm_crossing = False
            player.active_breakthrough_aids = []
            if (
                player.cultivation_concealment
                and (
                    int(player.cultivation_concealment["realm_index"]),
                    int(player.cultivation_concealment.get("layer", 1)),
                ) >= (target_realm, target_layer)
            ):
                player.cultivation_concealment = None
            player.hp = max(1.0, max_hp(player) * max(0.0, min(1.0, hp_ratio)))
            player.mp = max(0.0, max_mp(player) * max(0.0, min(1.0, mp_ratio)))
            title, result = "压制修为", "activated"
            summary = (
                f"你将自身修为真正压制至{target_name}；境界属性与条件均按压制后结算，"
                "但神识等级和神识经验完整保留。"
            )

    game.history.append(HistoryRecord(
        "SYS_SECRET_ART", 1, player.age, title, art, result, summary,
        {"art": art, "action": action, "target_realm_index": realm_index,
         "target_layer": layer},
        ["system", "secret_art", art],
    ))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def _public_secret_arts(deps: CultivationActionDependencies, player: Player) -> dict[str, Any]:
    concealment = player.cultivation_concealment
    suppression = player.cultivation_suppression
    current_name = deps._secret_art_realm_name(player, player.realm_index, player.layer)
    true_name = (
        deps._secret_art_realm_name(
            player, int(suppression["realm_index"]), int(suppression["layer"]),
        ) if suppression else current_name
    )
    targets = []
    for index, definition in enumerate(REALMS):
        for target_layer in range(1, definition.layers + 1):
            if (index, target_layer) >= (player.realm_index, player.layer):
                continue
            targets.append({
                "realm_index": index, "layer": target_layer,
                "name": deps._secret_art_realm_name(player, index, target_layer),
                "sense_requirement": deps._cultivation_sense_requirement(index, target_layer),
            })
    return {
        "divine_sense_level": divine_sense_level(player),
        "natural_sense_level": deps._cultivation_sense_requirement(
            int(suppression["realm_index"]) if suppression else player.realm_index,
            int(suppression["layer"]) if suppression else player.layer,
        ),
        "current_realm_name": current_name,
        "true_realm_name": true_name,
        "targets": targets,
        "concealment": {
            "active": bool(concealment),
            "realm_index": concealment.get("realm_index") if concealment else None,
            "layer": concealment.get("layer") if concealment else None,
            "realm_name": (
                deps._secret_art_realm_name(
                    player, concealment["realm_index"], concealment.get("layer", 1),
                ) if concealment else None
            ),
        },
        "suppression": {
            "active": bool(suppression),
            "realm_name": current_name if suppression else None,
            "true_realm_name": true_name if suppression else None,
        },
    }


def breakthrough(deps: CultivationActionDependencies, game_id: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if not player.alive:
        raise ValueError("此生已经结束")
    if game.pending_event:
        raise ValueError("请先处理当前事件")
    if player.imprisonment:
        raise ValueError("身陷牢狱时无法正常突破")
    if player.sealed_cultivation:
        raise ValueError("当前修为受下界法则压制，不能在封印状态下突破")
    if player.cultivation_suppression:
        raise ValueError("当前修为受秘法压制，解除压制后方可突破")
    current = realm(player)
    required = opportunity_required(player)
    breakthrough_kind = deps._manual_breakthrough_kind(player)
    if not breakthrough_kind or player.opportunity < required:
        raise ValueError("尚未抵达需要手动突破的境界瓶颈")
    major = breakthrough_kind == "major"
    if major and player.path == "monster" and deps.bloodline_content_available():
        raise ValueError("妖修大境界不进行概率冲关，请在【血脉】面板选择不可逆进化形态")
    if major and player.realm_index >= len(REALMS) - 1:
        raise ValueError("大乘之后的飞升体系尚未开放")
    requirement = deps._major_breakthrough_requirement(player) if major else {"met": True, "reason": ""}
    if not requirement["met"]:
        raise ValueError(requirement["reason"])

    rng = decode_rng(game.seed, game.rng_state)
    old_label = public_player(player)["realm_name"]
    chance = deps._breakthrough_chance(player, major=major)
    player.natal_origin_penalty = 0.0
    player.concubine_breakthrough_bonus = 0.0
    if player.path == "demonic":
        player.devouring_breakthrough_bonus = 0.0
    if major:
        player.awaiting_major_breakthrough = False
    else:
        player.awaiting_minor_breakthrough = False
    deps._consume_breakthrough_aids(player, f"{'major' if major else 'minor'}:{player.realm_index}")
    if rng.random() >= chance["final"]:
        player.joint_companion_breakthrough = None
        failure_type = "major" if major else "minor"
        player.opportunity = required * float(WORLD_SYSTEMS["breakthrough"][f"{failure_type}_failure_retention"])
        gain = deps._sage_scaled_gain(
            player, float(WORLD_SYSTEMS["breakthrough"][f"{failure_type}_failure_heart_demon"]),
            "heart_demon_gain_reduction",
        )
        player.heart_demon += gain
        target_index = player.realm_index + 1
        target_name = (
            WORLD_SYSTEMS.get("demonic_cultivation", {}).get("realm_names", {}).get(str(target_index), REALMS[target_index].name)
            if major and player.path == "demonic" else REALMS[target_index].name
            if major else deps._minor_layer_target(player)
        )
        pity_gain = deps._record_minor_pity_failure(player) if not major else 0
        game.history.append(HistoryRecord(
            "SYS_MAJOR_BREAKTHROUGH_FAILED" if major else "SYS_MINOR_BREAKTHROUGH_FAILED",
            1, player.age, "冲关失利", None, "failed",
            f"冲击{target_name}的基础关隘失败（成功率 {chance['final']:.1%}）；"
            f"你保住性命，但心魔 +{gain:g}。"
            + (f" 连续失败使下次基础成功率额外提高 {pity_gain:.0%}。" if pity_gain else ""),
            {"chance": chance, "heart_demon_gain": gain, "pity_bonus_next": pity_gain},
            ["system", "breakthrough", failure_type, "negative"],
        ))
    else:
        if not major:
            deps._clear_minor_pity(player)
        companion = deps._joint_companion_eligible(player)
        player.joint_companion_breakthrough = (
            {"id": companion["id"], "source_realm": player.realm_index, "source_layer": player.layer, "major": major}
            if companion else None
        )
        player.opportunity = max(0.0, player.opportunity - required)
        source = player.realm_index
        if major:
            if source >= 3:
                kind = (
                    "heavenly_demon" if player.path == "demonic" and source >= 6
                    else "heavenly" if source >= 6 else "traditional"
                )
                deps._start_breakthrough_trial(game, kind, source, source + 1, old_label, major=True, rng=rng)
            else:
                deps._complete_major_breakthrough(game, rng, old_label)
        elif source >= 6 and player.layer in {3, 6}:
            deps._start_breakthrough_trial(game, "traditional", source, source, old_label, major=False, rng=rng)
        else:
            deps._complete_minor_breakthrough(game, rng, old_label)
    game.updated_at = now_iso()
    deps._enforce_guixu_rank_boundary(game, "breakthrough")
    deps._ensure_market(game, rng)
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def _body_progress_required(player: Player) -> float:
    config = WORLD_SYSTEMS["body_cultivation"]
    return float(config["progress_base"]) + player.body_training * float(config["progress_per_layer"])


def _body_pity_key(player: Player) -> str:
    return f"body:{player.body_training + 1}"


def _body_breakthrough_chance(deps: CultivationActionDependencies, player: Player) -> dict[str, float]:
    config = WORLD_SYSTEMS["body_cultivation"]
    target = player.body_training + 1
    ranges = config["base_chance"]
    base = next(
        float(chance) for span, chance in ranges.items()
        if int(span.split("-", 1)[0]) <= target <= int(span.split("-", 1)[1])
    )
    technique_bonus = 0.0
    if player.body_technique and target <= int(player.body_technique.body_bonus_max_layer or 0):
        technique_bonus = (
            float(player.body_technique.body_breakthrough_bonus)
            * player.body_technique.level_multiplier
        )
    failures = int(player.body_breakthrough_pity.get(deps._body_pity_key(player), 0))
    pity_bonus = 0.0
    if target >= int(config["pity_start_target"]):
        pity_bonus = min(
            float(config["pity_max_bonus"]),
            failures * float(config["pity_bonus_per_failure"]),
        )
    final = min(0.98, base + technique_bonus + pity_bonus)
    return {
        "base":base, "technique_bonus":technique_bonus, "pity_bonus":pity_bonus,
        "failures":failures, "final":final,
    }


def body_breakthrough(deps: CultivationActionDependencies, game_id: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if not player.alive or game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法冲击炼体境界")
    if player.body_technique is None:
        raise ValueError("必须先配置一部炼体功法")
    maximum = int(WORLD_SYSTEMS["body_cultivation"]["max_layer"])
    required = deps._body_progress_required(player)
    if player.body_training >= maximum:
        raise ValueError("炼体已经达到一百层极限")
    if not player.awaiting_body_breakthrough or player.body_progress < required:
        raise ValueError("炼体积累尚未圆满")
    rng = decode_rng(game.seed, game.rng_state)
    chance = deps._body_breakthrough_chance(player)
    target = player.body_training + 1
    key = deps._body_pity_key(player)
    if rng.random() >= chance["final"]:
        player.body_progress = required * float(WORLD_SYSTEMS["body_cultivation"]["failure_retention"])
        player.awaiting_body_breakthrough = False
        if target >= int(WORLD_SYSTEMS["body_cultivation"]["pity_start_target"]):
            player.body_breakthrough_pity[key] = int(player.body_breakthrough_pity.get(key, 0)) + 1
        next_chance = deps._body_breakthrough_chance(player)
        result = "failed"
        summary = (
            f"冲击炼体{target}层失败（成功率 {chance['final']:.1%}），保留七成积累。"
            + (f" 此层累计失败 {next_chance['failures']} 次，下次保底 +{next_chance['pity_bonus']:.1%}。" if target >= 21 else "")
        )
    else:
        old = player.body_training
        player.body_training = target
        grant_intrinsic_growth(player, hp=12.0)
        player.body_progress = 0.0
        player.awaiting_body_breakthrough = False
        player.body_breakthrough_pity.pop(key, None)
        player.hp = max_hp(player)
        reduction = deps._body_tribulation_damage_reduction(player)
        result = "success"
        summary = f"你将肉身由炼体{old}层锤炼至{target}层，气血完全恢复。"
        if target % 20 == 0:
            summary += " 此后修仙大小境界的基础成功率永久增加1个百分点。"
        if target >= 50 and target % 5 == 0:
            summary += f" 肉身对雷劫与天劫的累计减伤提升至{reduction:.1%}。"
    game.history.append(HistoryRecord(
        "SYS_BODY_BREAKTHROUGH", 1, player.age, "肉身破境", str(target), result, summary,
        {"target_layer":target,"chance":chance,"body_training":player.body_training},
        ["system","body_training","breakthrough",result],
    ))
    game.rng_state = encode_rng(rng)
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def divine_sense_breakthrough(deps: CultivationActionDependencies, game_id: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if not player.alive or game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法突破神识")
    if player.divine_sense_technique is None:
        raise ValueError("必须先配置一部神识功法")
    cost = divine_sense_breakthrough_cost(player)
    if player.divine_sense_experience < cost:
        raise ValueError("神识经验尚未达到手动突破要求")
    old_level = divine_sense_level(player)
    player.divine_sense_experience -= cost
    player.divine_sense_rank = old_level + 1
    game.history.append(HistoryRecord(
        "SYS_DIVINE_SENSE_BREAKTHROUGH", 1, player.age, "神识破境", str(old_level + 1), "success",
        f"你消耗 {cost:.0f} 神识经验，将神识由 {old_level} 级突破至 {old_level + 1} 级；多余经验完整保留。",
        {"level":[old_level, old_level + 1], "experience_cost":cost},
        ["system", "divine_sense", "breakthrough"],
    ))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)

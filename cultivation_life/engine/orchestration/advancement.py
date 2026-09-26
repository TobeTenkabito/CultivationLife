from __future__ import annotations

import random
from typing import Any
from ...content_registry import ACTIONS, MARKET_SETTINGS, REALMS, WORLD_SYSTEMS
from ...models import GameState, HistoryRecord, Player
from ...rules import (
    add_item,
    can_player_practice_technique,
    max_hp,
    max_mp,
    opportunity_multiplier,
    technique_environment_multiplier,
    grant_qi_experience,
    divine_sense_level,
    technique_scale,
)
from ...simulation import ActionUnitLedger
from ...runtime import decode_rng, encode_rng, now_iso
from ...system.crafting_system import crafted_artifact_bonuses
from ...system.possession_system import advance_player_age, current_body_age
from ..dependencies import AdvancementDependencies


def advance(deps: AdvancementDependencies, game_id: str, action: str, years: int = 1) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if not player.alive:
        raise ValueError("此生已经结束")
    if game.pending_event:
        raise ValueError("请先处理当前事件")
    if game.heavenly_court.get("open_election"):
        raise ValueError("天庭大选正在进行；选举不流逝时间，请先在天庭界面完成投票")
    if player.world == "celestial" and not player.immortal_power_converted and action not in {"cultivate", "rest", "commission"}:
        raise ValueError("仙灵力尚未完全转化，当前只能修行、调息或承接坊市委托")
    if player.imprisonment:
        raise ValueError("你身陷大牢，只能选择服刑或尝试越狱")
    if player.ghost_captor and action not in {"cultivate", "rest"}:
        raise ValueError("魂印受制时只能等待、有限修炼、反抗或夺舍拘魂者")
    if action not in ACTIONS:
        raise ValueError("未知行动")
    guixu_session = (
        game.guixu_state.get("player_session")
        if isinstance(game.guixu_state, dict) else None
    )
    trapped_in_guixu = bool(guixu_session and guixu_session.get("trapped"))
    if player.cultivation_suppression and action == "cultivate" and not trapped_in_guixu:
        raise ValueError("压制修为期间不能运转主修功法；可修炼神识、炼体或进行其他行动")
    if action == "commission" and player.realm_index == 0:
        raise ValueError("凡人尚无法承接修仙坊市委托")
    if action == "body_train" and not trapped_in_guixu:
        if player.body_technique is None:
            raise ValueError("必须先获得并配置一部炼体功法")
        if player.body_training >= int(WORLD_SYSTEMS["body_cultivation"]["max_layer"]):
            raise ValueError("炼体已经达到一百层极限")
        if player.awaiting_body_breakthrough or player.body_progress >= deps._body_progress_required(player):
            raise ValueError("炼体积累已经圆满，请先手动冲击下一层")
    if action == "sense_train" and player.divine_sense_technique is None and not trapped_in_guixu:
        raise ValueError("必须先获得并配置一部神识功法")
    if trapped_in_guixu:
        if action not in {"cultivate", "body_train", "sense_train", "rest"}:
            raise ValueError("被困归墟期间只能修炼、炼体、锻炼神识或调息")
        return deps._guixu_trapped_training(game_id, action, years)
    if ACTIONS[action].get("combat") and player.realm_index == 0:
        raise ValueError("凡人尚无力参与修士层面的猎杀与斗法")
    deps._prepare_sage_action(game, action)
    if action == "cultivate" and player.technique and not can_player_practice_technique(player, player.technique.element):
        raise ValueError("灵根属性与五行功法不合，无法修炼")
    units = max(1, min(10, int(years)))
    time_unit = int(WORLD_SYSTEMS["time_units"][str(player.realm_index)])
    years = units * time_unit
    rng = decode_rng(game.seed, game.rng_state)
    total_gain = 0.0
    total_body_gain = 0.0
    total_sense_gain = 0.0
    total_fame_reduction = 0.0
    treasure_results: list[str] = []
    commission_results: list[str] = []
    combat_results: list[str] = []
    era_news: list[str] = []
    start_world_age = player.age
    start_age = current_body_age(player)
    ledger = ActionUnitLedger(action, years)
    for elapsed_index in range(years):
        ledger.begin_year()
        advance_player_age(player)
        low, high = ACTIONS[action]["opportunity"]
        gain = rng.randint(low, high) * opportunity_multiplier(player)
        if action == "cultivate" and player.path == "demonic":
            gain *= float(WORLD_SYSTEMS["demonic_cultivation"]["natural_cultivation_multiplier"])
        if player.world == "celestial" and deps._court_law_active(game, "immortal_twofold"):
            gain *= 1.10
        deps._add_opportunity(player, gain)
        total_gain += gain
        if action == "sense_train":
            sense_gain = deps._sense_training_step(player)
            player.divine_sense_experience += sense_gain
            total_sense_gain += sense_gain
            deps._apply_action_resources(player, action, ledger.claim_resource_cost())
        elif action == "body_train":
            training_gain = deps._body_training_step(player, rng)
            player.body_progress = min(deps._body_progress_required(player), player.body_progress + training_gain)
            total_body_gain += training_gain
            deps._apply_action_resources(player, action, ledger.claim_resource_cost())
            if player.body_progress >= deps._body_progress_required(player):
                player.awaiting_body_breakthrough = True
        elif action == "treasure":
            if ledger.claim_resource_cost():
                treasure_results.append(deps._treasure_step(game, rng))
                if not player.alive:
                    break
        elif action == "commission":
            commission_results.append(deps._commission_step(game, rng))
            deps._apply_action_resources(player, action, ledger.claim_resource_cost())
        elif ACTIONS[action].get("combat"):
            # 一个行动单位只结算一次主动遭遇；高境界的一次点击虽跨越多年，
            # 不会因此把组队概率重复抽取五十或一百次。
            if ledger.claim_combat():
                combat_results.append(deps._personal_combat_step(game, action, rng))
                if not player.alive:
                    break
        else:
            paid_cost = ledger.claim_resource_cost()
            deps._apply_action_resources(player, action, paid_cost)
            if action == "befriend_neighbors" and paid_cost:
                fame_rules = WORLD_SYSTEMS["fame"]
                reduction = max(0.0, min(
                    player.fame,
                    float(fame_rules["reconciliation_base"])
                    + player.realm_index * float(fame_rules["reconciliation_realm_scale"]),
                ))
                player.fame = max(0.0, player.fame - reduction)
                total_fame_reduction += reduction
            if action == "rest" and player.heart_demon > 0:
                player.heart_demon = max(0.0, player.heart_demon - 0.5)
        continue_world = deps._advance_world_year(game, rng, era_news)
        if player.alive:
            deps._advance_soul_erosion_time(game, 1)
        if not continue_world or not player.alive:
            break
    if player.alive:
        action_title = "打熬筋骨" if action == "cultivate" and player.spirit_root == "none" else ACTIONS[action]["name"]
        action_summary = (
            f"完成一个教化行动单位：外在影响 {game.sage_state.get('action_result', {}).get('external', 0):+.2f}，内在影响 +{game.sage_state.get('action_result', {}).get('inner', 0):.2f}，门人出师 {game.sage_state.get('action_result', {}).get('graduated', 0)} 人。"
            if ACTIONS[action].get("sage_action")
            else
            f"从 {start_age} 岁炼体至 {current_body_age(player)} 岁；无灵根无法由吐纳获得机缘。"
            if action == "cultivate" and player.spirit_root == "none"
            else f"从 {start_age} 岁摸索至 {current_body_age(player)} 岁；尚无主修功法，无法炼化机缘。"
            if action == "cultivate" and player.technique is None
            else f"获得微量机缘 {total_gain:.1f}；{deps._condense_action_results(treasure_results)}"
            if action == "treasure"
            else deps._condense_action_results(commission_results)
            if action == "commission"
            else deps._condense_action_results(combat_results)
            if ACTIONS[action].get("combat")
            else f"从 {start_age} 岁锻炼识海至 {current_body_age(player)} 岁，神识经验 +{total_sense_gain:.1f}；当前为 {divine_sense_level(player)} 级。"
            if action == "sense_train"
            else f"从 {start_age} 岁淬炼肉身至 {current_body_age(player)} 岁，炼体积累 +{total_body_gain:.1f}；当前为 {player.body_training} 层。"
            if action == "body_train"
            else f"你主动收敛声势、修复近邻关系，威名 -{total_fame_reduction:.0f}；当前威名 {player.fame:.0f}。"
            if action == "befriend_neighbors"
            else f"从 {start_age} 岁修行至 {current_body_age(player)} 岁，获得 {total_gain:.1f} 点机缘。"
        )
        game.history.append(HistoryRecord(
            "ACT_" + action.upper(), 1, player.age, action_title, action, "completed",
            action_summary,
            {
                "age": [start_age, current_body_age(player)], "world_age": [start_world_age, player.age],
                "opportunity": round(total_gain, 1),
                **({"fame_reduction": round(total_fame_reduction, 1)} if action == "befriend_neighbors" else {}),
            }, ["action", action],
        ))
        if action == "treasure":
            deps._queue_followup_event(game, deps._prepare_treasure_reward_event(game, rng))
        completed_years = max(1, player.age - start_world_age)
        completed_units = max(1, (completed_years + time_unit - 1) // time_unit)
        artifact_news = deps._advance_natal_artifact(game, action, completed_units)
        if artifact_news:
            era_news.append(artifact_news)
        for _ in range(completed_units):
            era_news.extend(deps._advance_diplomacy_unit(game, rng))
            deps._advance_concubine_aftermath(game, rng)
            era_news.extend(deps._advance_heavenly_court_unit(game, rng))
            era_news.extend(deps._advance_intrigue_unit(game, rng))
            tianji_news = deps._maybe_tianji_intelligence_event(game, rng)
            if tianji_news:
                era_news.append(tianji_news)
        drained = deps._advance_concubine_status(game, completed_units)
        if drained:
            era_news.append(f"{player.age}岁：侍妾名分被抽走机缘 {drained:.1f}")
        deps._advance_player_bounties(game, rng)
        if game.pending_event is None and player.ghost_captor:
            deps._maybe_relationship_sanction(game, rng)
        elif game.pending_event is None:
            if deps._maybe_relationship_sanction(game, rng):
                pass
            elif deps._maybe_immortal_conversion_event(game, rng):
                pass
            elif deps._maybe_concubine_proposal(game, rng):
                pass
            elif deps._maybe_personal_revenge(game, rng):
                pass
            elif deps._maybe_probability_story_event(game, rng):
                pass
            elif deps._maybe_xiang_node_event(game, rng):
                pass
            elif deps._maybe_founded_sect_pressure(game, rng):
                pass
            elif deps._maybe_affinity_gift(game, rng):
                pass
            elif not deps._maybe_faction_event(game, rng):
                event = deps._select_event(game, action, rng)
                if event:
                    game.pending_event = deps._instantiate_event(event, game, rng)
        elapsed_years = player.age - start_world_age
        if elapsed_years >= 5:
            deps._record_era_summary(game, start_world_age, era_news)

        deps._advance_auction_clock(game, rng)
        deps._advance_exchange_clock(game, rng)

    deps._finish_sage_action(game)
    # 坊市只在一次玩家操作结束时刷新。旧逻辑在大乘一次行动的 1000 个
    # 年度中重建 1000 次相同规模的随机货架，最终只有最后一次可见。
    deps._ensure_market(game, rng)

    deps._compact_world_history(game)
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def _add_opportunity(
    deps: AdvancementDependencies, player: Player, amount: float,
    regional_efficiencies: dict[str, float] | None = None,
) -> float:
    before = player.opportunity
    player.opportunity = max(0.0, before + float(amount))
    actual_gain = player.opportunity - before
    if actual_gain > 0:
        grant_qi_experience(
            player, actual_gain,
            regional_efficiencies
            if regional_efficiencies is not None
            else deps.maps.qi_gain_efficiencies(player.world, player.location_id),
        )
    return actual_gain


def _sense_training_step(
    deps: AdvancementDependencies, player: Player, regional: dict[str, float] | None = None,
    concentrations: dict[str, float] | None = None,
) -> float:
    """Calculate one year of sense training for every training context."""
    sense = player.divine_sense_technique
    if sense is None:
        return 0.0
    regional = (
        regional if regional is not None
        else deps.maps.qi_gain_efficiencies(player.world, player.location_id)
    )
    regional_multiplier = sum(
        float(weight) * float(regional.get(source, 0))
        for source, weight in sense.sources.items()
    )
    return (
        float(WORLD_SYSTEMS["demonic_cultivation"]["divine_sense_training_base"])
        * (1 + sense.divine_sense_bonus * technique_scale(sense))
        * technique_environment_multiplier(sense, player.world, concentrations)
        * regional_multiplier
        * (1 + crafted_artifact_bonuses(player)["divine_sense_efficiency"])
        * (1 + max(0.0, float(player.sage_effects.get("sense_multiplier", 0.0))))
    )


def _body_training_step(
    deps: AdvancementDependencies, player: Player, rng: random.Random,
    concentrations: dict[str, float] | None = None,
) -> float:
    """Calculate one year of body training for every training context."""
    if player.body_technique is None:
        return 0.0
    body_rules = WORLD_SYSTEMS["body_cultivation"]
    return (
        rng.randint(*body_rules["progress_per_year"])
        * (1 + 0.04 * max(0, player.body_technique.grade - 1))
        * player.body_technique.level_multiplier
        * technique_environment_multiplier(player.body_technique, player.world, concentrations)
        * (
            float(WORLD_SYSTEMS.get("monster_cultivation", {}).get("body_training_multiplier", 1.5))
            if player.path == "monster" else 1.0
        )
        * (1 + crafted_artifact_bonuses(player)["body_training_efficiency"])
    )


def _apply_action_resources(player: Player, action: str, pay_cost: bool) -> None:
    """Apply annual gains but charge negative HP/MP modifiers once per action unit."""
    for resource, maximum in (("hp", max_hp(player)), ("mp", max_mp(player))):
        if resource == "mp" and player.world == "celestial" and not player.immortal_power_converted:
            maximum *= max(0, min(5, player.immortal_conversion_stage)) / 5
        ratio = float(ACTIONS[action].get(resource, 0))
        if ratio < 0 and not pay_cost:
            continue
        value = getattr(player, resource) + maximum * ratio
        floor = 1 if action == "commission" and resource == "hp" else 0
        setattr(player, resource, min(maximum, max(floor, value)))


def _condense_action_results(results: list[str]) -> str:
    if len(results) <= 4:
        return " ".join(results)
    return " ".join(results[:3]) + f" ……其余 {len(results) - 3} 年的同类经历已并入本期结算。"


def _record_era_summary(game: GameState, start_age: int, news: list[str]) -> None:
    distinct_news = list(dict.fromkeys(news))
    if game.pending_event:
        distinct_news.append(f"{game.player.age}岁：大事件“{game.pending_event['title']}”发生")
    if distinct_news:
        shown = distinct_news[:12]
        summary = "；".join(shown)
        if len(distinct_news) > len(shown):
            summary += f"；另有 {len(distinct_news) - len(shown)} 项人事变动记入各年档案"
    else:
        summary = "本期未发生足以传遍各地的突破、陨落或大事件。"
    game.history.append(HistoryRecord(
        "SYS_ERA_SUMMARY", 1, game.player.age, f"{game.player.age - start_age}年纪要", None, "summarized",
        summary, {"age": [start_age, game.player.age], "news_count": len(distinct_news)},
        ["system", "era_summary", "world_news", f"world:{game.player.world}"],
    ))


def _commission_step(deps: AdvancementDependencies, game: GameState, rng: random.Random) -> str:
    tier = deps._market_tier(game.player)
    quantity = rng.randint(*MARKET_SETTINGS["commission_stones"][str(tier)])
    add_item(game.player, "spirit_stone", quantity)
    world_name = WORLD_SYSTEMS["world_names"].get(game.player.world, game.player.world)
    return f"完成一项{world_name}{REALMS[tier].name}坊市委托，获得下品灵石 ×{quantity}。"

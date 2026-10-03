"""Explicit operations for immortal system."""

from __future__ import annotations
from ..content_registry import REALMS
from ..rules import breakthrough_opportunity_required
from ..runtime import decode_rng, encode_rng
from .doctrine.provider import config, player_record
from .doctrine.cultivation import AXES, vein_cost, training_cost
from .immortal_cultivation import vein_probability, vein_ready, vein_intrinsic_bonus
from .cultivation_dependencies import ImmortalActionDependencies, ImmortalViewDependencies
from .cultivation_session import _save_cultivation

def item_quantity(player, item_id):
    return sum(item.quantity for item in player.inventory if item.id == item_id)


def immortal_action(deps: ImmortalActionDependencies, game_id, action, doctrine_id=None, axis=None, supply_id=None):
    if action in {'buy_body_manual', 'buy_body_supply'}:
        return deps.yaochi_action(game_id, 'buy', supply_id)
    game = deps._cultivation_game(game_id)
    p, record, rules = game.player, player_record(game), config()["cultivation"]
    if action == "gather":
        return deps.advance(game_id, "cultivate", 1)
    if action == 'temper_golden_light':
        return deps._temper_golden_light(game)
    if action in {'train_body', 'buy_body_manual', 'select_body_manual', 'buy_body_supply'}:
        return deps._immortal_body_action(game, action, supply_id)
    if action == 'breakthrough':
        if not vein_ready(p):
            raise ValueError(f'本层须先开启 {p.layer * 3} 条仙脉（本境共 27 条）')
        return deps.breakthrough(game_id)
    if p.sealed_cultivation or p.cultivation_suppression:
        raise ValueError('修为受压制，不能开启仙脉或温养邻域')
    if not p.immortal_power_converted:
        raise ValueError("须先完成仙灵力转化")
    opened = p.immortal_veins.get(str(p.realm_index), 0)
    if action == "open_vein":
        if opened >= min(rules["veins_per_realm"], p.layer * rules["veins_per_layer"]):
            raise ValueError("本层仙脉已经贯通，请先手动突破境界")
        cost = vein_cost(p.realm_index, opened, rules)
        probability = vein_probability(p)
        deps._spend_cultivation(p, cost)
        rng = decode_rng(game.seed, game.rng_state)
        success = rng.random() < probability
        game.rng_state = encode_rng(rng)
        key = f'{p.realm_index}:{opened + 1}'
        if success:
            p.immortal_veins[str(p.realm_index)] = opened + 1
            from .ghost_system import grant_intrinsic_progression_if_new_highwater
            grant_intrinsic_progression_if_new_highwater(p)
            p.immortal_vein_pity.pop(key, None)
            summary = f"开启本境第 {opened + 1}/27 条仙脉（成功率 {probability:.0%}）。境界不自动进阶。"
            summary += f" 本源气血上限 +{rules['vein_intrinsic']['hp'][p.realm_index - 9]}，本源法力上限 +{rules['vein_intrinsic']['mp'][p.realm_index - 9]}。"
        else:
            p.immortal_vein_pity[key] = p.immortal_vein_pity.get(key, 0) + 1
            summary = f"开脉失败，本次机缘与仙痕已消耗；下次成功率 {vein_probability(p):.0%}。"
    elif action == 'advance_voisinage':
        from .doctrine.voisinage_training import rank, cost, label, BOUNDARIES
        if record['progress'].get(doctrine_id, {}).get('level', 0) < 4:
            raise ValueError('须先激发此邻域')
        training = record.setdefault('voisinage_training', {}).setdefault(doctrine_id, {})
        current = rank(training)
        if current >= 13:
            raise ValueError('此邻域已达至臻')
        deps._spend_cultivation(p, cost(training, rules))
        if current in BOUNDARIES:
            deps._start_voisinage_backlash(game, doctrine_id)
            summary = f'冲击{label(current + 1)}引发道统反噬，须以此邻域迎战天域，存活五轮。失败可能被道统同化而亡。'
        else:
            training['rank'] = current + 1
            summary = f'邻域修至{label(current + 1)}。'
    elif action == "train_voisinage":
        level = record["progress"].get(doctrine_id, {}).get("level", 0)
        if level < 4 or axis not in AXES:
            raise ValueError("须选择已激发的邻域与有效培养维度")
        training = record.setdefault("voisinage_training", {}).setdefault(doctrine_id, {})
        rank = training.get(axis, 0)
        if rank >= rules["voisinage_max_training"]:
            raise ValueError("此维度已达当前培养上限")
        deps._spend_cultivation(p, training_cost(rank, rules))
        training[axis] = rank + 1
        summary = f"温养邻域：{ {'stability':'稳固','incursion':'侵夺','authority':'权能'}[axis]}达到 {rank + 1} 重。"
    else:
        raise ValueError("未知仙道修持操作")
    return _save_cultivation(deps.commit, game, summary)


def _spend_cultivation(player, cost):
    if player.opportunity < cost["opportunity"] or player.immortal_traces < cost["traces"]:
        raise ValueError("机缘或仙痕不足")
    player.immortal_traces -= cost["traces"]
    player.opportunity -= cost["opportunity"]


def _public_immortal(deps: ImmortalViewDependencies, game):
    rules, p = config()["cultivation"], game.player
    opened = p.immortal_veins.get(str(p.realm_index), 0)
    major = p.layer >= REALMS[p.realm_index].layers
    ready = vein_ready(p) and (not major or p.realm_index < len(REALMS) - 1)
    requirement = deps._major_breakthrough_requirement(p) if major else {"met": True, "reason": "每层三脉贯通后手动冲关。"}
    return {"phase": rules["vein_phases"][min(3, max(0, p.realm_index - 9))], "names": rules["vein_names"], "opened": opened, "total": rules["veins_per_realm"], "per_layer": rules["veins_per_layer"],
            "realm": REALMS[p.realm_index].name, "realm_index": p.realm_index, "layer": p.layer, "opportunity": p.opportunity,
            "traces": p.immortal_traces, "converted": p.immortal_power_converted,
            "intrinsic_total": {r: vein_intrinsic_bonus(p, r) for r in ('hp', 'mp')},
            "intrinsic_per_vein": {r: rules['vein_intrinsic'][r][max(0, min(3, p.realm_index - 9))] for r in ('hp', 'mp')},
            "next_cost": vein_cost(p.realm_index, opened, rules) if opened < min(rules["veins_per_realm"], p.layer * rules["veins_per_layer"]) else None,
            "can_breakthrough": ready and requirement["met"] and p.immortal_power_converted and p.opportunity >= breakthrough_opportunity_required(p),
            "ready": ready, "major": major, "requirement": requirement["reason"],
            "breakthrough_cost": breakthrough_opportunity_required(p),
            "trial": {9:'人五衰：独战天道，存活五轮', 10:'天五衰：天道展开天域，存活五轮',
                      11:'斩三尸：三尸同时出场，无轮数限制，须全部击杀'}.get(p.realm_index) if major else None,
            "breakthrough_chance": deps._breakthrough_chance(p, major=major)["final"] if ready and not major else None,
            "chance": vein_probability(p), "pity_step": rules["vein_pity_step"],
            "trace_chance": rules["trace_gain_chance"]}

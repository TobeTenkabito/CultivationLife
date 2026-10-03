"""Explicit operations for immortal body system."""

from __future__ import annotations
from ..content_registry import ITEM_CATALOG
from ..rules import remove_item, max_hp, max_mp
from ..runtime import decode_rng, encode_rng
from .immortal_cultivation import rules, body_manual, body_probability, body_recipe, golden_light
from .cultivation_dependencies import ImmortalBodyDependencies
from .cultivation_session import _save_cultivation

def quantity(player, key):
    return sum(item.quantity for item in player.inventory if item.id == key)


def _temper_golden_light(deps: ImmortalBodyDependencies, game):
    from .immortal_cultivation import golden_light_rank
    p, cfg = game.player, rules()['golden_light']
    rank = golden_light_rank(p)
    if not rank or rank >= len(cfg['stages']):
        raise ValueError('须先解锁护体金光，且尚未达到大圆满')
    if p.sealed_cultivation or p.cultivation_suppression:
        raise ValueError('修为受压制，不能锤炼护体金光')
    stage = cfg['stages'][rank]
    if any(quantity(p, key) < count for key, count in stage['recipe'].items()):
        raise ValueError('锤炼护体金光的材料不足')
    for key, count in stage['recipe'].items():
        remove_item(p, key, count)
    p.immortal_body['golden_light_rank'] = rank + 1
    return _save_cultivation(deps.commit, game, f"护体金光锤炼至{stage['name']}，肉身承受邻域影响减弱 {stage['resistance']:.0%}。")


def _public_golden_light(game):
    from .immortal_cultivation import golden_light_rank, golden_light_resistance
    p, cfg = game.player, rules()['golden_light']
    rank = golden_light_rank(p)
    next_stage = cfg['stages'][rank] if 0 < rank < 5 else None
    recipe = [{'id':key, 'name':ITEM_CATALOG[key].name, 'needed':count, 'owned':quantity(p,key)}
              for key,count in (next_stage['recipe'] if next_stage else {}).items()]
    return dict(available=bool(rank), rank=rank, stages=cfg['stages'], resistance=golden_light_resistance(p),
                next_name=next_stage['name'] if next_stage else None, recipe=recipe,
                can_train=bool(next_stage and p.world=='celestial' and not p.sealed_cultivation
                               and not p.cultivation_suppression and all(r['owned']>=r['needed'] for r in recipe)))


def _immortal_body_action(deps: ImmortalBodyDependencies, game, action, key):
    p, cfg = game.player, rules()['body']
    state = p.immortal_body
    manuals = {m['id']: m for m in cfg['manuals']}
    if action == 'select_body_manual':
        if key not in manuals or key not in state.get('manuals', []):
            raise ValueError('须先取得此仙躯功法')
        state['active_manual'] = key
        summary = f"改修《{manuals[key]['name']}》，仙躯层数与失败保底保留。"
    elif action == 'train_body':
        if p.body_training < cfg['required_training']:
            raise ValueError('须先将炼体修至 100 层')
        if p.sealed_cultivation or p.cultivation_suppression:
            raise ValueError('修为受压制，不能淬炼真仙之躯')
        if not p.immortal_power_converted:
            raise ValueError('须先完成仙灵力转化')
        if not body_manual(p):
            raise ValueError('须取得并选用仙躯功法，凡间炼体功法不能用于仙躯')
        level = state.get('level', 0)
        if level >= cfg['max_level']:
            raise ValueError('仙躯已达当前修炼上限')
        recipe = body_recipe(p)
        if any(quantity(p, item) < count for item, count in recipe.items()):
            raise ValueError('仙草灵药不足')
        probability = body_probability(p)
        hp_ratio, mp_ratio = p.hp / max_hp(p), p.mp / max_mp(p)
        for item, count in recipe.items():
            remove_item(p, item, count)
        rng = decode_rng(game.seed, game.rng_state)
        success = rng.random() < probability
        game.rng_state = encode_rng(rng)
        if success:
            state.update(level=level + 1, failures=0)
            from .ghost_system import grant_intrinsic_progression_if_new_highwater
            grant_intrinsic_progression_if_new_highwater(p)
            p.hp, p.mp = max_hp(p) * min(1, hp_ratio), max_mp(p) * min(1, mp_ratio)
            summary = f'真仙之躯修至第 {level + 1} 层（成功率 {probability:.0%}）。'
            if level + 1 == cfg['golden_light_level']:
                summary += ' 护体金光已成，满足冲击金仙的仙躯条件。'
        else:
            state['failures'] = state.get('failures', 0) + 1
            summary = f'淬体未成，本次药材已消耗；下次成功率 {body_probability(p):.0%}。'
    else:
        raise ValueError('未知仙躯操作')
    return _save_cultivation(deps.commit, game, summary)


def _public_immortal_body(game):
    p, cfg = game.player, rules()['body']
    level, manual = p.immortal_body.get('level', 0), body_manual(p)
    recipe = [{'id': key, 'name': ITEM_CATALOG[key].name, 'needed': count,
               'owned': quantity(p, key)} for key, count in body_recipe(p).items()]
    return {
        'level': level, 'max_level': cfg['max_level'], 'required_training': cfg['required_training'],
        'body_training': p.body_training, 'golden_light': golden_light(p),
        'golden_light_level': cfg['golden_light_level'], 'chance': body_probability(p),
        'pity_step': cfg['pity_step'], 'failures': p.immortal_body.get('failures', 0),
        'manual': manual['id'] if manual else None, 'recipe': recipe,
        'hp_bonus': level * cfg['hp_per_level'], 'mp_bonus': level * cfg['mp_per_level'],
        'can_train': p.body_training >= cfg['required_training'] and p.immortal_power_converted
            and bool(manual) and level < cfg['max_level'] and not p.cultivation_suppression
            and not p.sealed_cultivation and all(r['owned'] >= r['needed'] for r in recipe),
        'manuals': [{**m, 'owned': m['id'] in p.immortal_body.get('manuals', [])} for m in cfg['manuals']],
        'supplies': [{**s, 'name': ITEM_CATALOG[s['id']].name, 'owned': quantity(p, s['id'])}
                     for s in cfg['supplies']],
    }

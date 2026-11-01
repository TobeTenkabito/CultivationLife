"""Explicit operations for immortal body system."""

from __future__ import annotations
from ..content_registry import ITEM_CATALOG
from ..rules import remove_item, max_hp, max_mp
from ..runtime import decode_rng, encode_rng
from ..cultivation_coordinates import body_rank,describe
from .immortal_cultivation import rules, body_manual, body_probability, body_recipe, golden_light
from .cultivation_dependencies import ImmortalBodyDependencies
from .cultivation_session import _save_cultivation

def quantity(player, key):
    return sum(item.quantity for item in player.inventory if item.id == key)


def _divine_training_reason(game):
    from .cultivation_session import cultivation_blocked
    p=game.player
    if p.world!='celestial' or p.realm_index<9:return '须在仙界达到真仙境界'
    if cultivation_blocked(game):return '当前状态无法修持，请先处理事件或脱离拘束'
    if p.sealed_cultivation or p.cultivation_suppression:return '修为受压制，不能修炼神光'
    if game.map_journey:return '请先完成当前旅行'
    if game.guixu_state.get('player_session'):return '请先离开归墟再修炼神光'
    runtime=game.heavens_state.get('runtime')
    if runtime:
        from .heavens.state import active_task
        if active_task(runtime):return '请先完成或结束诸天亲自任务'
    return ''


def _temper_golden_light(deps: ImmortalBodyDependencies, game, key=None, expected_level=None):
    from .divine_lights import definitions, profile, recipe
    p=game.player
    reason=_divine_training_reason(game)
    if reason:raise ValueError(reason)
    row=next((r for r in definitions() if r['id']==key),None)
    _,levels=profile(p,player=True)
    if row is None:raise ValueError('旧金光锤炼已改为五色神光，请刷新后选择已解锁神光')
    if key not in levels:raise ValueError(f"仙躯达到{row['unlock_level']}层才能解锁{row['name']}")
    level=levels[key]
    if type(expected_level) is not int or expected_level!=level:raise ValueError('神光修炼等级已变化，请刷新后再修炼')
    if level>=10:raise ValueError('此神光已修炼至十重上限')
    if p.sealed_cultivation or p.cultivation_suppression:raise ValueError('修为受压制，不能修炼神光')
    costs=recipe(row,level)
    if any(quantity(p,k)<n for k,n in costs.items()):raise ValueError('神光修炼资材不足')
    for material,count in costs.items():remove_item(p,material,count)
    p.immortal_body.setdefault('divine_lights',{})[key]=level+1
    summary=f"{row['name']}修炼至{level+1}重；消耗"+'、'.join(f'{ITEM_CATALOG[k].name}×{n}' for k,n in costs.items())+'。'
    return _save_cultivation(deps.commit,game,summary)


def _public_golden_light(game):
    from .divine_lights import definitions, profile, recipe, body_record
    from ..cultivation_coordinates import body_rank,describe
    p=game.player;record,_=body_record(p,player=True);effects,levels=profile(p,player=True)
    reason=_divine_training_reason(game)
    rows=[]
    for row in definitions():
        key=row['id'];unlocked=key in levels;level=levels.get(key,0)
        costs=[dict(id=k,name=ITEM_CATALOG[k].name,needed=n,owned=quantity(p,k)) for k,n in recipe(row,level).items()] if level<10 else []
        blocked=('仙躯尚未达到解锁层数' if not unlocked else reason or
                 ('已修炼至十重' if level>=10 else '神光修炼资材不足' if any(r['owned']<r['needed'] for r in costs) else ''))
        rows.append(dict(id=key,name=row['name'],unlock_level=row['unlock_level'],description=row['description'],
            unlocked=unlocked,level=level,max_level=10,recipe=costs,can_train=not blocked,reason=blocked,
            value=effects.get('kun_resist' if key=='kun' else 'zhen_heal' if key=='zhen' else key,0)))
    return dict(available=bool(levels),body_level=record.get('level',0),body_stage=describe(body_rank(p.body_training,record.get('level',0)))['name'],
                unlocked_count=len(levels),lights=rows,maximum_body_level=50)


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
            from .divine_lights import definitions
            unlocked=next((r for r in definitions() if r['unlock_level']==level+1),None)
            if unlocked:summary+=f" {unlocked['name']}已解锁，可独立修炼。"
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
        'body_stage': describe(body_rank(p.body_training,level))['name'],
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

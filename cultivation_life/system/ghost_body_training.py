"""World-local ghost-body cultivation on existing body and material ledgers."""
from ..content_registry import CONTENT_DOCUMENTS,ITEM_CATALOG
from ..ghost_body_content import IDS,NAMES,build,recipe
from .ghost_body import enabled_for
from .cultivation_guard import cultivation_blocked
from .upper_voisinage_rules import config


def reason(game):
    p=game.player
    if not enabled_for(p) or p.world!='reincarnation' or p.realm_index<9:return '须开启鬼修道途并在轮回界达到第九阶'
    if cultivation_blocked(game):return '请先处理事件、劫战或拘束；寄身期间无法修持本魂鬼躯'
    if p.spirit_state.get('mode')=='wandering':return '神游期间不能修持原鬼躯，请先返回或取得肉身'
    if p.sealed_cultivation or p.cultivation_suppression:return '修为受压制，不能修持鬼躯'
    if game.map_journey or game.guixu_state.get('player_session'):return '请先完成旅行或离开归墟'
    if game.heavens_state.get('runtime'):
        from .heavens.state import active_task
        if active_task(game.heavens_state['runtime']):return '请先结束诸天亲自任务'
    return ''


def stock(player):
    material=config()['worlds']['reincarnation']['material_id']
    return sorted((m for m in player.crafting_materials if m.get('material_id')==material
        and not m.get('dynamic_definition')),key=lambda m:(m.get('quality',1),str(m.get('id',''))))


def bill(rank,multiplier=1):
    base=CONTENT_DOCUMENTS['doctrines.json']['cultivation']['vein_opportunity_base']
    return dict(opportunity=base*(rank+1)*multiplier,materials=rank+1)


def public(game):
    p=game.player
    if not enabled_for(p):return dict(available=False)
    level=p.immortal_body.get('level',0);ranks=p.immortal_body.get('ghost_training',{})
    blocked=reason(game);owned=len(stock(p));rows=[]
    material_id=config()['worlds']['reincarnation']['material_id']
    material=next(m for m in CONTENT_DOCUMENTS['crafting.json']['materials'] if m['id']==material_id)
    def problem(cost,extra=''):
        return blocked or extra or ('机缘或轮回界筑域材料不足' if cost and (p.opportunity<cost['opportunity'] or owned<cost['materials']) else '')
    for i,key in enumerate(IDS,1):
        rank=ranks.get(key,0);cost=dict(opportunity=bill(rank,i)['opportunity'],materials=recipe(key,rank)) if rank<10 else None
        materials=[dict(id=k,name=ITEM_CATALOG[k].name,needed=n if cost else 0,
            owned=sum(item.quantity for item in p.inventory if item.id==k or item.artifact_origin_id==k),
            asset='material.'+k,origin_name='轮回界') for k,n in recipe(key,rank).items()]
        error=blocked or ('鬼躯层数尚未解锁' if level<i*10 else '已达十重' if rank>=10 else '')
        if not error and (p.opportunity<cost['opportunity'] or any(m['owned']<m['needed'] for m in materials)):
            error='机缘或鬼躯专属培养材料不足；五种材料仅轮回界产出'
        rows.append(dict(id=key,name=NAMES[i-1],level=rank,unlock_level=i*10,unlocked=level>=i*10,
            effects=build(key,rank).effects,cost=cost,materials=materials,reason=error,can_train=not error))
    cost=bill(level) if level<50 else None
    body_reason=problem(cost,'须普通炼体100层' if p.body_training<100 else '鬼躯已达50层' if level>=50 else '')
    return dict(available=True,level=level,max_level=50,rows=rows,body_cost=cost,body_reason=body_reason,
        can_train_body=not body_reason,material_name=material['name'],material_owned=owned,reason=blocked)


def act(game,action,key,expected_level,*,has_item,remove_item):
    data=public(game)
    if not data['available']:raise ValueError('鬼修道途未开启')
    p=game.player
    if action=='ghost_body_train':
        rank=data['level'];cost=data['body_cost'];error=data['body_reason'];label='鬼躯'
    elif action=='ghost_body_refine':
        row=next((r for r in data['rows'] if r['id']==key),None)
        if row is None:raise ValueError('未知鬼躯机制')
        rank=row['level'];cost=row['cost'];error=row['reason'];label=row['name']
    else:raise ValueError('未知鬼躯操作')
    if error:raise ValueError(error)
    if type(expected_level) is not int or expected_level!=rank:raise ValueError('鬼躯等级已变化，请刷新后重试')
    if action=='ghost_body_refine' and any(not has_item(p,k,n) for k,n in cost['materials'].items()):
        raise ValueError('鬼躯专属培养材料不足')
    materials=stock(p)[:cost['materials']] if action=='ghost_body_train' else []
    for material in materials:p.crafting_materials.remove(material)
    if action=='ghost_body_refine':
        for material,amount in cost['materials'].items():remove_item(p,material,amount)
    p.opportunity-=cost['opportunity']
    if action=='ghost_body_train':
        from ..rules import max_hp,max_mp
        hp_ratio=p.hp/max(1,max_hp(p));mp_ratio=p.mp/max(1,max_mp(p))
        p.immortal_body['level']=rank+1
        from .ghost_system import grant_intrinsic_progression_if_new_highwater
        grant_intrinsic_progression_if_new_highwater(p)
        p.hp=max_hp(p)*min(1,hp_ratio);p.mp=max_mp(p)*min(1,mp_ratio)
    else:p.immortal_body.setdefault('ghost_training',{})[key]=rank+1
    paid=f'{data["material_name"]}×{len(materials)}' if action=='ghost_body_train' else '、'.join(f'{ITEM_CATALOG[k].name}×{n}' for k,n in cost['materials'].items())
    return f'{label}修至{rank+1}'+('层' if action=='ghost_body_train' else '重')+f'，消耗{cost["opportunity"]:g}机缘及{paid}。'

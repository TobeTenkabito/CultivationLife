"""Five-change cultivation quotes and inventory-backed commands."""
from ..content_registry import CONTENT_DOCUMENTS,ITEM_CATALOG
from ..monster_body_content import UNLOCKS
from .monster_body import enabled_for,record,config,profile
from .cultivation_guard import cultivation_blocked

MODE_NAMES=dict(auto='自动择一',heal='治疗肉身与态势',spirit='稳定心神',field='修复邻域',
    suppress='镇压',seal='封锁',technique='禁制功法',artifact='禁制法宝',support='隔绝支援',supply='截断供给',voisinage='封禁邻域')


def reason(game):
    p=game.player
    if not enabled_for(p) or p.world!='nether' or p.realm_index<9:return '须开启万妖归宗并在幽冥界达到第九阶'
    if cultivation_blocked(game):return '请先处理事件、劫战或拘束；寄身期间不能培养原妖躯'
    if p.spirit_state.get('mode')=='wandering' and not p.spirit_state.get('body_intact'):return '肉身已毁，须先取得肉身'
    if p.sealed_cultivation or p.cultivation_suppression:return '修为受压制，不能修炼妖躯五蜕'
    if game.map_journey:return '请先完成当前旅行'
    if game.guixu_state.get('player_session'):return '请先离开归墟'
    if game.heavens_state.get('runtime'):
        from .heavens.state import active_task
        if active_task(game.heavens_state['runtime']):return '请先结束诸天亲自任务'
    return ''


def quote(level,recipe,multiplier=1):
    base=CONTENT_DOCUMENTS['doctrines.json']['cultivation']['vein_opportunity_base']
    return dict(opportunity=base*multiplier*(level+1),materials={k:n*(level+1) for k,n in recipe.items()})


def material_rows(player,bill):
    return [dict(id=k,name=ITEM_CATALOG[k].name,needed=n,
        owned=sum(i.quantity for i in player.inventory if i.id==k or i.artifact_origin_id==k),
        asset='material.'+k,origin_name='幽冥界') for k,n in bill['materials'].items()]


def public(game):
    p=game.player
    if not enabled_for(p):return dict(available=False)
    data=record(p);level=data.get('level',0);blocked=reason(game)
    body_bill=quote(level,{config()['body_material']:1}) if level<50 else None
    body_materials=material_rows(p,body_bill) if body_bill else []
    body_reason=blocked or ('须先将普通炼体修至100层' if p.body_training<100 else '妖躯已达50层' if level>=50 else '')
    if not body_reason and (p.opportunity<body_bill['opportunity'] or any(r['owned']<r['needed'] for r in body_materials)):body_reason='机缘或妖躯材料不足'
    owned={r.id:r for r in profile(p,player=True)};rows=[]
    for row in config()['mechanisms']:
        mechanism=owned.get(row['id']);rank=mechanism.level if mechanism else 0
        bill=quote(rank,row['recipe'],row['opportunity_multiplier']) if rank<10 else None
        materials=material_rows(p,bill or dict(materials={k:0 for k in row['recipe']}))
        problem=blocked or ('妖躯层数尚未解锁' if mechanism is None else '已达十重' if rank>=10 else '')
        if not problem and (p.opportunity<bill['opportunity'] or any(r['owned']<r['needed'] for r in materials)):problem='机缘或五蜕材料不足'
        rows.append(dict(id=row['id'],name=row['name'],level=rank,unlock_level=row['unlock_level'],
            unlocked=mechanism is not None,effects=dict(mechanism.effects) if mechanism else {},cost=bill,materials=materials,reason=problem,can_train=not problem))
    rank=data.get('training',{}).get('liezang',0)
    return dict(available=True,level=level,max_level=50,body_cost=body_bill,body_materials=body_materials,
        body_reason=body_reason,can_train_body=not body_reason,rows=rows,reaction=data.get('reaction','auto'),
        choices=[dict(id=k,name=v,unlocked=k=='auto' or rank>=UNLOCKS[k]) for k,v in MODE_NAMES.items()],
        can_select=not blocked and level>=30,reason=blocked)


def act(game,action,key,expected_level,*,has_item,remove_item):
    problem=reason(game)
    if problem:raise ValueError(problem)
    p=game.player;data=record(p);level=data.get('level',0)
    if action=='monster_body_select':
        rank=data.get('training',{}).get('liezang',0)
        if level<30 or key not in MODE_NAMES or (key!='auto' and rank<UNLOCKS[key]):raise ValueError('烈脏功能尚未解锁')
        p.immortal_body.setdefault('monster',{})['reaction']=key
        return f'烈脏改为{MODE_NAMES[key]}，每次闪避仍只兑现一项免费施权。'
    if action=='monster_body_train':
        if p.body_training<100 or level>=50:raise ValueError('须普通炼体100层，妖躯上限50层')
        rank=level;bill=quote(rank,{config()['body_material']:1});label='妖躯'
    elif action=='monster_body_refine':
        row=next((r for r in config()['mechanisms'] if r['id']==key),None)
        if row is None or level<row['unlock_level']:raise ValueError('此蜕尚未解锁')
        rank=data.get('training',{}).get(key,0)
        if rank>=10:raise ValueError('此蜕已达十重')
        bill=quote(rank,row['recipe'],row['opportunity_multiplier']);label=row['name']
    else:raise ValueError('未知妖躯修持操作')
    if type(expected_level) is not int or expected_level!=rank:raise ValueError('修炼等级已变化，请刷新后重试')
    if p.opportunity<bill['opportunity'] or any(not has_item(p,k,n) for k,n in bill['materials'].items()):raise ValueError('机缘或妖躯培养材料不足；材料仅幽冥界产出')
    for material,amount in bill['materials'].items():remove_item(p,material,amount)
    p.opportunity-=bill['opportunity'];data=p.immortal_body.setdefault('monster',{})
    if action=='monster_body_train':
        data['level']=rank+1
        p.hp+=config()['hp_per_level'];p.mp+=config()['mp_per_level']
    else:data.setdefault('training',{})[key]=rank+1
    return f'{label}修至{rank+1}'+('层' if action=='monster_body_train' else '重')+f'，实付{bill["opportunity"]:g}机缘及'+ '、'.join(f'{ITEM_CATALOG[k].name}×{n}' for k,n in bill['materials'].items())+'。'

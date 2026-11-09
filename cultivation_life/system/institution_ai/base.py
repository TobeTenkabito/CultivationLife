"""Base-game sect/family needs and original depot/building delivery adapters."""
from . import rules,procurement
from .buildings import BuildingActor
from ..economy.ledger import balance
from ..economy import depot
from ..economy.enterprise_state import owner_allowed
from ..building_assets import rows_at
from .. import building_projects
from ..building_destruction import rebuild
from ..faction_geography import faction_site
from ...economy_content import BASE_PRICES

ID='base-institutions'

def entity_for(game,scope):
    entity=game.family if scope['kind']=='family' else game.sects.get(scope['identity'])
    return entity if entity and entity.id==scope['identity'] and not entity.extinct else None

def scopes(game,maps):
    result=[]
    for account,row in game.economy_v2.get('organizations',{}).items():
        if row['kind'] not in {'sect','family'}:continue
        entity=game.family if row['kind']=='family' else game.sects.get(row['identity'])
        if not entity or entity.id!=row['identity'] or entity.extinct or entity.kind=='institution':continue
        if entity.world not in maps.worlds or entity.world!=row['world']:continue
        location=faction_site(entity,persist=False)['id']
        people=sorted(n.id for n in entity.npcs if n.alive and n.world==entity.world)
        if not people:continue
        reserve=int(row.get('expected_upkeep',0)*3)
        available=max(0,balance(game,account)-reserve)
        controlled=owner_allowed(game,row['kind'],entity.id,entity.world)
        if row['kind']=='family':
            from ..organization_heritage import decision
            controlled=decision(game,entity)
        result.append(dict(id=account,provider=ID,kind=row['kind'],identity=entity.id,name=entity.name,world=entity.world,
            location=location,payer=account,people=people,controlled=bool(controlled),available=available,
            reserve=reserve,automatic_budget=available//10))
    return result

def actor(game,scope,person=None,assignment=None):
    job=rules.record(game,scope['id']).get('job')
    assignment=assignment or (job['id'] if job else 'institution-delegate:'+scope['id'])
    person=person or next((n for n in scope['people'] if not rules.person_reason(game,n,scope['world'],scope['location'],assignment=assignment)),None)
    if not person:return None
    return BuildingActor(scope['world'],scope['location'],scope['kind'],scope['identity'],person,assignment)

def offers(game,maps,scope):
    entity=entity_for(game,scope);market=game.economy_v2['markets'].get(scope['world']+':'+scope['location'])
    if not entity or not market:return []
    result=[];store=depot.find(game,entity)
    goods=depot.catalog(scope['world'])
    tier=max((n.realm_index for n in entity.npcs if n.alive),default=1)
    wage=max(1,BASE_PRICES[min(11,max(0,tier-1))]//10000)
    desired=min(8,max(2,len(scope['people'])//4))
    choices=[(key,g) for key,g in goods.items() if g['kind']=='item' and g['tier']<=tier+1
        and ('pill' in g['id'] or 'medicine' in g['id']) and g['id'] in market['commodities']]
    selections=sorted(choices,key=lambda x:(x[1]['tier'],x[0]))[:2]
    teaching=next(((key,g) for key,g in goods.items() if g['kind']=='item' and g['id'].startswith('npc_training_dao_cultivation_')
                   and g['tier']<=tier+1 and g['id'] in market['commodities']),None)
    if teaching:selections.append(teaching)
    for key,good in selections:
        missing=max(0,desired-(store or {}).get('stock',{}).get(key,0))
        if not missing:continue
        materials={good['id']:missing}
        try:purchase=procurement.cost(market,materials);reason=''
        except ValueError as error:purchase=0;reason=str(error)
        if store and depot.occupied(store)+missing>10000:reason='原府库仓储容量不足'
        result.append(dict(key='supply:'+key,name='补足府库 · '+good['name'],category='teaching' if good['id'].startswith('npc_training_') else 'supply',kind='supply',target=key,
            quantity=missing,materials=materials,coins=0,purchase=purchase,years=5,wage=wage,budget=purchase+5*wage,
            urgency=50,reason=reason))
    who=actor(game,scope)
    if who:
        place=dict(world=scope['world'],location_id=scope['location'],instance_id=None)
        for building in rows_at(game,place):
            if building['status']!='destroyed' or building['owner']!=dict(kind=scope['kind'],id=scope['identity']) or building.get('subtype')=='temple':continue
            bill=building_projects.quote(game,'rebuild',building,payer=scope['payer'],stock={},actor=who)
            reason=bill['reason'] if bill['reason']!='灵石或筑城材料不足' else ''
            try:purchase=procurement.cost(market,bill['materials'])
            except ValueError as error:purchase=0;reason=str(error)
            result.append(dict(key='repair:'+building['id'],name='原址修缮 · '+building['name'],category='repair',kind='repair',target=building['id'],
                materials=bill['materials'],coins=bill['coins'],building_token=bill['token'],purchase=purchase,years=10,wage=wage,
                budget=purchase+bill['coins']+10*wage,urgency=90,reason=reason))
    return result[:5]

def validate(game,maps,scope,job):
    if not entity_for(game,scope):return '原机构已经失效'
    offer=job['offer']
    if offer['kind']=='supply':
        store=depot.find(game,entity_for(game,scope))
        if store and depot.occupied(store)+offer['quantity']>10000:return '原府库容量不足'
        if store and store['stock'].get(offer['target'],0)>=min(8,max(2,len(scope['people'])//4)):return '原物资缺口已经解决，请交接避免重复采购'
    else:
        place=dict(world=scope['world'],location_id=scope['location'],instance_id=None)
        building=next((r for r in rows_at(game,place) if r['id']==offer['target']),None)
        if not building or building['status']!='destroyed' or building['owner']!=dict(kind=scope['kind'],id=scope['identity']):return '原建筑状态或产权已经变化'
    return ''

def deliver(game,maps,scope,job):
    if blocked:=validate(game,maps,scope,job):raise ValueError(blocked)
    offer=job['offer'];market=game.economy_v2['markets'][scope['world']+':'+scope['location']]
    price=procurement.cost(market,offer['materials'])
    if price+offer['coins']>balance(game,job['wallet']):raise ValueError('当前实货价格超出原预算，须交接或追加授权')
    if offer['kind']=='supply':
        paid=depot.purchase(game,maps,entity_for(game,scope),offer['target'],offer['quantity'],project_payer=job['wallet'])
        job['spent']+=paid
        return '原市场实货已入本机构原府库；人物、库存和资金均沿原账。'
    place=dict(world=scope['world'],location_id=scope['location'],instance_id=None)
    building=next(r for r in rows_at(game,place) if r['id']==offer['target'])
    who=actor(game,scope,job['person'],job['id'])
    bill=building_projects.quote(game,'rebuild',building,payer=job['wallet'],stock=offer['materials'],actor=who)
    if bill['reason'] or bill['token']!=offer['building_token']:raise ValueError('原工程报价或执行权限已经变化')
    cargo,paid=procurement.buy(game,market,offer['materials'],job['wallet'],party=job['source'])
    rebuild(game,building,None,payer=job['wallet'],stock=cargo,actor=who)
    job['spent']+=paid+bill['coins']
    return '原机构建筑按原工程价格复建，原产权、活动次数与产业库存保留。'

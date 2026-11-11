"""Asura public-building needs executed by the shared base agenda engine."""
import sys
from . import rules as province
from .. import institution_authority as authority
from ..institution_ai import rules, runtime, commands, procurement
from ..institution_ai.buildings import BuildingActor
from ..building_assets import rows_at
from .. import building_projects
from ..building_destruction import rebuild
from ..economy.ledger import balance

ID = province.ID


def reconcile_crown(game, identity):
    if not identity:return
    for row in province.offices(game):
        if row['status'] in {'appointed','active'} and identity in (row['holder'],row['nominee']):
            authority.revoke(game,row)


def scopes(game, maps):
    result = []
    for row in province.offices(game):
        if not authority.effective(game, row, row['holder']) or not row['holder']:
            continue
        available = balance(game, row['wallet'])
        result.append(dict(id=row['id'], provider=ID, kind='administration', identity=row['id'], name=row['name'],
            world=row['world'], location=row['location'], payer=row['wallet'], people=list(row['people']),
            controlled=row['holder']=='player', available=available, reserve=0, automatic_budget=available//10))
    return result


def offers(game, maps, scope):
    if not province.enabled():
        return []
    row = authority.records(game)[scope['id']]
    city = next((c for c in province.cities(game) if c['id']==row['city_id']), None)
    if not city or not province.legal_city(game,city):
        return []
    market = game.economy_v2['markets'].get(scope['world']+':'+scope['location'])
    person = next((i for i in scope['people'] if not rules.person_reason(game,i,scope['world'],scope['location'],
                   assignment='institution-delegate:'+scope['id'])), None)
    if not person or not market:
        return []
    actor = BuildingActor(scope['world'],scope['location'],row['owner']['kind'],row['owner']['id'],person,'institution-delegate:'+scope['id'])
    place = dict(world=scope['world'],location_id=scope['location'],instance_id=None)
    result = []
    for building in rows_at(game,place):
        if building['owner']!=row['owner'] or building['status']!='destroyed' or building.get('subtype')=='temple':
            continue
        bill = building_projects.quote(game,'rebuild',building,payer=scope['payer'],stock={},actor=actor)
        reason = bill['reason'] if bill['reason']!='灵石或筑城材料不足' else ''
        try:
            purchase=procurement.cost(market,bill['materials'])
        except ValueError as error:
            purchase=0; reason=str(error)
        result.append(dict(key='repair:'+building['id'],name='原址修缮 · '+building['name'],category='repair',kind='repair',
            target=building['id'],materials=bill['materials'],coins=bill['coins'],building_token=bill['token'],
            purchase=purchase,years=10,wage=1000,budget=purchase+bill['coins']+10000,urgency=90,reason=reason))
    return result[:3]


def validate(game,maps,scope,job):
    row=authority.records(game).get(scope['id'])
    if not province.enabled():return '修罗DLC停用，暂停新履约，只允许交接'
    if not row or not authority.effective(game,row,row['holder']):return '任职授权已失效'
    if job['person'] not in row['people']:return '原属员已离任'
    place=dict(world=scope['world'],location_id=scope['location'],instance_id=None)
    target=next((b for b in rows_at(game,place) if b['id']==job['offer']['target']),None)
    if not target or target['owner']!=row['owner'] or target['status']!='destroyed':return '原建筑已修复或产权已经变化'
    city=next((c for c in province.cities(game) if c['id']==row['city_id']),None)
    if not city or not province.legal_city(game,city):return '原城市或设府许可失效'
    return ''


def deliver(game,maps,scope,job):
    if reason:=validate(game,maps,scope,job):raise ValueError(reason)
    row=authority.records(game)[scope['id']];offer=job['offer']
    place=dict(world=scope['world'],location_id=scope['location'],instance_id=None)
    target=next(b for b in rows_at(game,place) if b['id']==offer['target'])
    actor=BuildingActor(scope['world'],scope['location'],row['owner']['kind'],row['owner']['id'],job['person'],job['id'])
    bill=building_projects.quote(game,'rebuild',target,payer=job['wallet'],stock=offer['materials'],actor=actor)
    market=game.economy_v2['markets'][scope['world']+':'+scope['location']]
    cost=procurement.cost(market,offer['materials'])
    if bill['reason'] or bill['token']!=offer['building_token'] or balance(game,job['wallet'])<cost+bill['coins']:
        raise ValueError('原工程报价或公款不足，请示追加或交接')
    cargo,paid=procurement.buy(game,market,offer['materials'],job['wallet'],party=row['source'])
    rebuild(game,target,None,payer=job['wallet'],stock=cargo,actor=actor)
    job['spent']+=paid+bill['coins']
    authority.log(game,row,'属员完成原址修缮，工料与工资从唯一公款实付。')
    return '原建筑恢复使用，原产权、库存与履历保留。'


def public(game):
    return commands.public(game,None,sys.modules[__name__])


def command(game,payload):
    if not province.enabled() and payload.get('action')!='institution_cancel':
        raise ValueError('修罗DLC停用，仅可交接原项目')
    commands.command(game,None,payload,sys.modules[__name__])


def advance(game,maps):
    from ...regional_context import ordinary_year,region
    if not ordinary_year(game) or (region(game) or game.player.world)!='asura':return
    for row in province.offices(game):
        authority.expire(game,row)
        if row['controller'] and row['controller']!='player':
            from ...relationship_records import find_person
            controller=find_person(game,row['controller'])
            if controller and not controller.alive:
                authority.relinquish(game,row,row['controller'])
                authority.log(game,row,'原任身故，结束本人职责；府署与未耗公款仍归原机构。')
            elif row['status']=='handover' and not rules.person_reason(game,row['controller'],row['world'],row['location']):
                authority.relinquish(game,row,row['controller'])
                authority.log(game,row,'原任在原址完成交接，未耗公款留在本府供继任核验。')
        if province.enabled() and row['status']=='appointed' and row['nominee']!='player':
            if not rules.person_reason(game,row['nominee'],row['world'],row['location']):
                authority.assume(game,row,row['nominee'],row['world'],row['location'])
        if row['status']=='active' and row['holder']!='player':
            from ...relationship_records import find_person
            from ...npc_custody import is_free
            npc=find_person(game,row['holder'])
            if not npc or not is_free(npc) or npc.world!=row['world']:
                authority.revoke(game,row)
    runtime.advance(game,maps,sys.modules[__name__])

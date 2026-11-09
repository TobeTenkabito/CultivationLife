"""DLC duties on the base institutional agenda, with original temple/deed facts."""
import sys
from .institution_ai import rules,runtime,commands,procurement
from .institution_ai.buildings import BuildingActor
from .economy.ledger import balance,transfer_value
from .building_assets import rows_at
from .building_projects import quote as building_quote
from .building_destruction import rebuild
from .earth_temple_rules import ledgers,temple,city
from .earth_temple import DUTIES,bill,settle_service
from .immortal_identity_rules import official,primary
from .westward_rules import enabled,record as westward
from .purple_east_rules import BUILDING
from .faction_geography import person_site
from ..relationship_records import find_person
from ..npc_custody import is_free
from ..building_rules import may_use
from ..content_registry import ITEM_CATALOG

ID='westward-management'

def known_people(game,location):
    ids=set(game.world_npcs)|set(game.notable_npcs)|set(game.heavenly_court.get('officials',{}))
    ids.update(n.id for s in game.sects.values() if s.world=='celestial' for n in s.npcs)
    if game.family and game.family.world=='celestial':ids.update(n.id for n in game.family.npcs)
    return sorted(i for i in ids if (n:=find_person(game,i)) and n.alive and is_free(n) and n.world=='celestial'
                  and n.realm_index>=9 and person_site(game,n)==location)

def scopes(game,maps):
    # Disabled content retains local cancellation controls, but offers/annual work stop.
    result=[]
    for ledger in ledgers(game):
        row=temple(game,ledger['temple_id'])
        if not row or row['owner']!=dict(kind='player',id=game.id):continue
        result.append(dict(id='temple:'+row['id'],provider=ID,kind='temple',identity=row['id'],name=row['name']+' · 驻庙经营',
            world='celestial',location=row['address']['location_id'],payer='player',people=known_people(game,row['address']['location_id']),
            controlled=True,available=balance(game,'player'),reserve=0,automatic_budget=0))
    chapter=westward(game).get('purple_east',{});row=game.building_state.get('records',{}).get(BUILDING)
    if chapter.get('phase')=='complete' and row and (may_use(row,'player',game.id) or row['owner']==dict(kind='player',id=game.id)):
        people=known_people(game,row['address']['location_id'])
        if chapter['plan']=='shared':people=[i for i in people if i==chapter.get('companion')]
        result.append(dict(id='estate-service:'+BUILDING,provider=ID,kind='estate',identity=BUILDING,name=row['name']+' · '+{'guard':'济民经营','public':'公共修持','yaochi':'瑶池承办','shared':'同道共修'}[chapter['plan']],
            world='celestial',location=row['address']['location_id'],payer='player',people=people,
            controlled=True,available=balance(game,'player'),reserve=0,automatic_budget=0,plan=chapter['plan']))
    return result

def ledger_for(game,scope):return next((s for s in ledgers(game) if s['temple_id']==scope['identity']),None)

def target(game,scope):
    return next((r for r in rows_at(game,dict(world=scope['world'],location_id=scope['location'],instance_id=None)) if r['id']==scope['identity']),None)

def available_reason(game,scope):
    if not enabled():return 'DLC停用：只办理交接，不新增收益'
    row=target(game,scope)
    if not row or row['status']!='intact':return '原建筑不可用，须先原址修复'
    if scope['kind']=='temple':
        ledger=ledger_for(game,scope);original=city(game,row)
        if not original or original['status']!='intact' or not may_use(original,'player',game.id):return '依托原城市或使用许可失效'
        if official(game) or not ledger.get('active'):return '须由实际地仙主持，玄仙任职期间不代领香火'
        if ledger.get('duty') or ledger.get('works') or ledger.get('cases',{}).get('active'):return '原庙已有本人待办，须先交接'
        if ledger.get('allowance',0)>0 and game.player.age<ledger.get('until',0):return '当前有效香火尚未用尽，不重复安排同轮护民'
    return ''

def offers(game,maps,scope):
    if not enabled():return []
    blocked=available_reason(game,scope)
    market=game.economy_v2['markets'].get('celestial:'+scope['location'])
    if not market:return []
    result=[]
    if scope['kind']=='temple':
        for kind,spec in DUTIES.items():
            from .westward_fair_benefits import credential
            prize=credential(game,'guard') if kind=='watch' else None
            cost=bill(game,kind=kind)
            result.append(dict(key='duty:'+kind,kind='duty',category={'watch':'repair','care':'supply','teach':'teaching'}[kind],
                name='执事筹办 · '+spec['name'],target=scope['identity'],duty=kind,materials=cost['materials'],coins=cost['coins'],
                years=95 if prize else 100,fair_credential=prize['id'] if prize else None,wage=1000,urgency=50,reason=blocked))
    else:
        # Ending rights determine which real local service can be hosted.
        plan=scope['plan'];names={'guard':'居民济用供货','public':'公开修持备料','yaochi':'仙会承办备料','shared':'共修伙伴备料'}
        # Original stock can relieve even a completely empty market.
        for estate in game.economy_v2.get('estates',{}).values():
            if estate['world']!='celestial' or estate['location']!=scope['location'] or estate['owner_kind']!='player' or estate['owner_id']!=game.id:continue
            for item,n in sorted(estate['stock'].items()):
                product=market['commodities'].get(item)
                if n>=2 and product and item in ITEM_CATALOG and product['stock']<product['target']:
                    result.append(dict(key='estate-supply:'+estate['id']+':'+item,kind='estate_supply',category='supply',name=names[plan]+' · '+ITEM_CATALOG[item].name,
                        target=estate['id'],item=item,quantity=min(8,n),materials={},coins=0,years=10,wage=1000,urgency=60,reason=blocked))
        # Finite original-property reconstruction gives the deed continuing practical use.
        for building in rows_at(game,dict(world='celestial',location_id=scope['location'],instance_id=None)):
            if building['status']!='destroyed' or building['owner']!=dict(kind='player',id=game.id) or building.get('subtype')=='temple':continue
            person=next((i for i in scope['people'] if not rules.person_reason(game,i,'celestial',scope['location'],assignment='institution-delegate:'+scope['id'])),None)
            if not person:continue
            who=BuildingActor('celestial',scope['location'],'player',game.id,person,'institution-delegate:'+scope['id'])
            q=building_quote(game,'rebuild',building,payer='background:celestial',stock={},actor=who)
            result.append(dict(key='estate-repair:'+building['id'],kind='estate_repair',category='repair',name='仙府主持修缮 · '+building['name'],
                target=building['id'],building_token=q['token'],materials=q['materials'],coins=q['coins'],years=20,wage=1000,urgency=90,reason=blocked))
    for offer in result:
        try:purchase=procurement.cost(market,offer['materials'])
        except ValueError as error:purchase=0;offer['reason']=offer['reason'] or str(error)
        offer['purchase']=purchase;offer['budget']=purchase+offer['coins']+offer['years']*offer['wage']
    return result[:5]

def validate(game,maps,scope,job):
    if blocked:=available_reason(game,scope):return blocked
    offer=job['offer']
    if offer['kind']=='estate_supply':
        e=game.economy_v2.get('estates',{}).get(offer['target'])
        if not e or e['owner_kind']!='player' or e['owner_id']!=game.id or e['world']!='celestial' or e['location']!=scope['location']:return '原产业产权或地点变化'
        if e['stock'].get(offer['item'],0)<offer['quantity']:return '原产业现货不足，请补足或交接'
    elif offer['kind']=='estate_repair':
        row=next((r for r in rows_at(game,dict(world='celestial',location_id=scope['location'],instance_id=None)) if r['id']==offer['target']),None)
        if not row or row['status']!='destroyed' or row['owner']!=dict(kind='player',id=game.id):return '原建筑已修复或产权失效'
    return ''

def deliver(game,maps,scope,job):
    if blocked:=validate(game,maps,scope,job):raise ValueError(blocked)
    offer=job['offer'];market=game.economy_v2['markets']['celestial:'+scope['location']]
    cost=procurement.cost(market,offer['materials'])
    if balance(game,job['wallet'])<cost+offer['coins']:raise ValueError('工料涨价超出原托管，请示追加授权')
    if offer['kind']=='estate_supply':
        from .economy.enterprise_operations import market_trade
        estate=game.economy_v2['estates'][offer['target']]
        market_trade(game,estate,market,offer['item'],offer['quantity'],'sell')
        return '原产业实货已进入本地市场，货款进入原产业账户；仙府仅组织履约，不额外复制奖励。'
    who=None;building=None
    if offer['kind']=='estate_repair':
        building=next(r for r in rows_at(game,dict(world='celestial',location_id=scope['location'],instance_id=None)) if r['id']==offer['target'])
        who=BuildingActor('celestial',scope['location'],'player',game.id,job['person'],job['id'])
        q=building_quote(game,'rebuild',building,payer=job['wallet'],stock=offer['materials'],actor=who)
        if q['reason'] or q['token']!=offer['building_token']:raise ValueError('原工程已经变化')
    cargo,paid=procurement.buy(game,market,offer['materials'],job['wallet'],party=job['source'])
    if who:rebuild(game,building,None,payer=job['wallet'],stock=cargo,actor=who)
    else:
        transfer_value(game,job['wallet'],'operator:'+market['id'],offer['coins'],'驻庙筹办原工料与施工交付')
        cargo.clear() # Actual construction consumption, not a second inventory.
        ledger=ledger_for(game,scope)
        settle_service(game,ledger,offer['duty'],job['started'])
        ledger['revision']=ledger.get('revision',0)+1
    job['spent']+=paid+offer['coins']
    return '原址实际履约完成；原庙香火期限按立项年计算，不叠加功德功勋。' if offer['kind']=='duty' else '原建筑已复建，旧产权和原库存保留。'

def advance(game,maps):
    runtime.advance(game,maps,sys.modules[__name__])

def public(game,maps):return commands.public(game,maps,sys.modules[__name__])

def command(game,maps,payload):
    from .earth_temple_rules import reason
    if blocked:=reason(game,recovery=payload.get('action') in {'institution_cancel','institution_configure'}):raise ValueError(blocked)
    if not enabled() and (payload.get('action')!='institution_cancel' and not (payload.get('action')=='institution_configure' and not payload.get('automatic') and not payload.get('person'))):raise ValueError('停用后只允许解除执事与交接')
    commands.command(game,maps,payload,sys.modules[__name__])

def on_start(game,scope,job):
    if job['offer'].get('fair_credential'):
        from .westward_fair_benefits import consume
        consume(game,job['offer']['fair_credential'],'驻庙护境筹办')

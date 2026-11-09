"""Concrete public targets and original quotes, with no private grants."""
import copy
from ..relationship_records import find_person
from ..content_registry import ITEM_CATALOG
from .court_bureau_projects import offers as bureau_offers
from .court_bureau_rules import digest
from .court_case_facts import relation
from .economy.state import local_market
from .economy.local_market import quote as market_quote
from .npc_development.targets import Target
from .npc_development.service import quote as training_quote
from .earth_temple_rules import ledgers,temple,city
from .faction_geography import person_site

KINDS={'training':'公共修持预算','repair':'地方修缮优先序','procurement':'公开采购规则','service':'地仙神位与服务协议'}

def beneficiary(game,identity):
    n=find_person(game,identity)
    if not n or n.world!='celestial' or person_site(game,n)!=game.player.location_id:raise ValueError('受益人须在原地点当面接受修持')
    if relation(game,identity) or n.family_traits.get('kin'):raise ValueError('公共修持不得指定本人亲属、道侣或师徒')
    return Target('npc',identity,n,n,('公共修持',))

def training(game,identity,stock=None):
    target=beneficiary(game,identity)
    plan=training_quote(game,'npc',identity,'cultivation','material',1,_target=target,stock=stock)
    return target,plan

def offers(game,maps):
    market=local_market(game)
    if game.player.world!='celestial' or not market:return []
    rows=[]
    for r in bureau_offers(game,maps,'land'):
        rows.append(dict(r,policy='repair',benefit='恢复原公共城市，私人地产不列支'))
    for r in bureau_offers(game,maps,'works'):
        rows.append(dict(r,policy='procurement',benefit='实货运抵原短缺市场；限量采购并公开回执'))
    for key in sorted(set(game.world_npcs)|set(game.notable_npcs)):
        n=find_person(game,key)
        if not n or n.realm_index<9 or n.path!='dao' or person_site(game,n)!=game.player.location_id:continue
        try:target,plan=training(game,key)
        except ValueError:continue
        material=plan['material_id']
        if not material or material not in market['commodities']:continue
        rows.append(dict(policy='training',kind='works',target=key,location=game.player.location_id,origin=game.player.location_id,
            name=n.name+' · 公共修持',years=10,materials={material:plan['material_count']},coins=0,reason='',
            before=[n.realm_index,n.layer],benefit=plan['label']+'：'+str(plan['before'])+' → '+str(plan['after'])))
    for ledger in ledgers(game):
        row=temple(game,ledger['temple_id']);original=city(game,row)
        if not row or row['owner']!=dict(kind='player',id=game.id) or row['address']['location_id']!=game.player.location_id or row['status']!='intact' or not original or original['status']!='intact':continue
        rows.append(dict(policy='service',kind='patrol',target=row['id'],location=game.player.location_id,origin=game.player.location_id,
            name=row['name']+' · 公开护民协议',years=10,materials={},coins=0,reason='',completed=ledger.get('completed',0),
            benefit='原庙公开使用，并新完成一次原护民庙务；产权不转让，庙务工料由庙主原价承担'))
    for r in rows:
        if r['policy']=='procurement':
            limit=game.heavenly_court.get('projects',{}).get('batch_limit',20)
            r['materials']={k:min(n,limit) for k,n in r['materials'].items()}
        r['purchase']=0
        for k,n in r['materials'].items():
            item=market['commodities'].get(k)
            if not item or item['stock']<n:r['reason']='原市场实际工料不足'
            else:r['purchase']+=market_quote(item,'buy',n)['total']
        r['budget']=r['purchase']+r['coins']+(r['years']+5)*1000
        cap=game.heavenly_court.get('projects',{}).get('project_cap',0)
        if cap and r['budget']>cap:r['reason']=r['reason'] or '超过当前施政单项预算上限'
        r['key']=digest([r['policy'],r['target'],game.player.age//500])
        r['token']=digest(r)
    return rows

def validate(game,row):
    offer=row['offer'];policy=offer['policy']
    if game.player.location_id!=offer['location']:raise ValueError('须沿原地图亲赴项目交付地点')
    if policy=='training':
        target,plan=training(game,offer['target'],row['cargo'])
        if [target.person.realm_index,target.person.layer]!=offer['before']:raise ValueError('原受益人修为已变化，请交接原项目后重议')
        if not plan['can_train']:raise ValueError(plan['reason'])
    elif policy=='repair':
        from .building_assets import local_rows
        from .building_projects import quote,owns
        building=next((b for b in local_rows(game) if b['id']==offer['target']),None)
        if not building or building['type']!='city' or not building.get('public') or owns(game,building):raise ValueError('原公共城址或权限已经变化')
        bill=quote(game,'rebuild',building,payer=row['wallet'],stock=row['cargo'])
        if bill['reason']:raise ValueError(bill['reason'])
        if bill['token']!=offer['building_token']:raise ValueError('原工程报价已经变化，请交接后重议')
    elif policy=='procurement':
        market=local_market(game)
        if not market or market['id']!=offer['destination_market']:raise ValueError('原交付市场已失效')
        if any(row['cargo'].get(k,0)<n or k not in market['commodities'] for k,n in offer['materials'].items()):raise ValueError('原公物不足或商品目录已经失效')
    elif policy=='service':
        ledger=next((s for s in ledgers(game) if s['temple_id']==offer['target']),{})
        building=temple(game,offer['target']);original=city(game,building) if building else None
        if not building or building['owner']!=dict(kind='player',id=game.id) or building['status']!='intact' or not original or original['status']!='intact':raise ValueError('原庙产权或城市已经失效')
        if not building.get('public') or ledger.get('completed',0)<=offer['completed']:raise ValueError('须保持原庙公开，并完成一项新护民庙务，再办理协议验收')

def deliver(game,row):
    validate(game,row);offer=row['offer']
    if offer['policy']=='training':
        from .npc_development.service import apply
        target,_=training(game,offer['target'],row['cargo'])
        return apply(game,'npc',offer['target'],'cultivation','material',1,_target=target,stock=row['cargo'])
    if offer['policy']=='service':return '原庙公开与新增护民成果已核验；原神位、香火、产权及个人投入保持原规则。'
    from .court_bureau_projects import deliver as original
    return original(game,row)

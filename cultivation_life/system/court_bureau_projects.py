"""Finite public procurement and delivery against original markets/buildings."""
import copy
import math
from ..content_registry import ITEM_CATALOG, restricted_acquisition
from ..building_schema import address
from .building_assets import local_rows
from . import building_projects as buildings
from .economy.ledger import account, balance, transfer_value
from .economy.state import local_market, reprice
from .economy.local_market import quote
from .court_bureau_rules import OFFICES, COURT, state, jobs, digest

def offers(game,maps,kind):
    if kind not in OFFICES:return []
    p=game.player; result=[]; market=local_market(game)
    if p.world!='celestial' or not market:return result
    if kind=='patrol':
        for edge in maps.worlds['celestial']['routes']:
            if p.location_id not in (edge['from'],edge['to']):continue
            dest=edge['to'] if edge['from']==p.location_id else edge['from']
            if maps.travel_plan('celestial',p.location_id,dest,p.realm_index).status!='ok':continue
            result.append(dict(target=dest,location=dest,name=maps.location('celestial',dest)['name']+'道路巡检',materials={},coins=0))
        from .court_enforcement import offers as patrol_offers
        result.extend(patrol_offers(game,maps))
    elif kind=='land':
        for row in local_rows(game):
            if row['type']!='city' or not row.get('public') or row['status']!='destroyed' or buildings.owns(game,row):continue
            bill=buildings.quote(game,'rebuild',row)
            result.append(dict(target=row['id'],location=p.location_id,name=row['name']+'复建',materials=bill['materials'],coins=bill['coins'],building_token=bill['token']))
    elif kind=='works':
        adjacent={e['to'] if e['from']==p.location_id else e['from'] for e in maps.worlds['celestial']['routes'] if p.location_id in (e['from'],e['to'])}
        for dest in sorted(adjacent):
            other=game.economy_v2['markets'].get('celestial:'+dest)
            if not other or maps.travel_plan('celestial',p.location_id,dest,p.realm_index).status!='ok':continue
            candidates=[(k,v) for k,v in other['commodities'].items() if k in ITEM_CATALOG and not restricted_acquisition('item',k)
                and v['tier']<=p.realm_index+1 and v['stock']<v['target']*.5 and market['commodities'].get(k,{}).get('stock',0)>=1]
            if not candidates:continue
            key,row=min(candidates,key=lambda x:(x[1]['stock']/max(1,x[1]['target']),x[0]))
            count=min(20,int(market['commodities'][key]['stock']),max(1,math.ceil(row['target']*.5-row['stock'])))
            result.append(dict(target=dest+':'+key,location=dest,name=maps.location('celestial',dest)['name']+' · '+ITEM_CATALOG[key].name,
                materials={key:count},coins=0,item=key,destination_market=other['id']))
    else:
        for job in jobs(game):
            if job['status']!='closed' or job['kind']=='audit' or job.get('audited'):continue
            result.append(dict(target=job['id'],location=p.location_id,name=job['name']+'收支复核',materials={},coins=0,
                evidence=copy.deepcopy(job.get('receipt',{}))))
    used=state(game).get('accepted',{})
    for row in result:
        row.update(kind=kind,origin=p.location_id,years=row.get('years',OFFICES[kind]['years']))
        row['key']=digest([kind,row['target'],p.location_id,p.age//500])
        row['reason']='本期已承接此项，取消或调任不刷新' if row['key'] in used else ''
        cost=0
        for item,n in row['materials'].items():
            product=market['commodities'].get(item)
            if not product or product['stock']<n:row['reason']=row['reason'] or '本地原市场工料库存不足'
            else:cost+=quote(product,'buy',n)['total']
        row['purchase']=cost
        row['token']=digest([row,[(k,market['commodities'].get(k)) for k in row['materials']]])
    return result

def reserve(game,job,offer,budget):
    wallet=job['wallet'];account(game,wallet)
    transfer_value(game,COURT,wallet,budget,'职司公务定额托管')
    market=local_market(game);job['cargo']={};job['purchase']=0
    for item,n in offer['materials'].items():
        product=market['commodities'][item];bill=quote(product,'buy',n)
        if product['stock']<n:raise ValueError('本地实际库存不足')
        transfer_value(game,wallet,'market:'+market['id'],bill['total'],'职司原市场采购实货')
        transfer_value(game,'market:'+market['id'],'operator:'+market['id'],bill['fee'],'职司采购手续费')
        product['stock']-=n;product['volume']+=n;market['turnover']+=bill['gross'];market['fees']+=bill['fee'];reprice(game,market,product)
        job['cargo'][item]=n;job['purchase']+=bill['total']

def deliver(game,job):
    kind=job['kind'];offer=job['offer'];location=job['location']
    if game.player.location_id!=location:raise ValueError('须亲临公务交付地点复核')
    if offer.get('operation'):
        from .court_enforcement import delivery
        return delivery(game,job)
    if kind=='patrol':
        from .earth_temple_rules import ledgers
        changed=0
        for ledger in ledgers(game):
            case=ledger.get('cases',{}).get('reports',{}).get('road')
            if case and set(case['edge'])=={job['origin'],location} and game.player.age<case['until']:
                case['delay']=0;changed+=1
        return f'原道路巡检完成，清除{changed}份仍有效的阻断记录；未生成战斗或战利品。'
    if kind=='land':
        row=next((r for r in local_rows(game) if r['id']==offer['target']),None)
        if not row or row['type']!='city' or not row.get('public') or buildings.owns(game,row):raise ValueError('原公共城址或权限已经变化')
        bill=buildings.quote(game,'rebuild',row,payer=job['wallet'],stock=job['cargo'])
        if bill['token']!=offer['building_token']:raise ValueError('原工程报价已经变化，请交接余款与公物')
        from .building_destruction import rebuild
        rebuild(game,row,None,payer=job['wallet'],stock=job['cargo']);job['engineering']=bill['coins']
        return '原公开城市复建，沿原规则回到一级；旧权属和活动次数保留。'
    if kind=='works':
        market=local_market(game)
        if not market or market['id']!=offer['destination_market']:raise ValueError('原交付市场已失效')
        if any(job['cargo'].get(k,0)<n for k,n in offer['materials'].items()):raise ValueError('原合同实物不足，不能以空货单验收；须交接并进入监察补交')
        for item,n in list(job['cargo'].items()):
            product=market['commodities'].get(item)
            if not product:raise ValueError('原商品已不在市场目录')
            product['stock']+=n;reprice(game,market,product)
        job['cargo'].clear()
        return '公物已进入原目的地市场库存；不发货款，不计个人销售收入。'
    source=next((j for j in jobs(game) if j['id']==offer['target']),None)
    if not source or source.get('audited') or source['status']!='closed':raise ValueError('原案卷已变化或已经复核')
    receipt=source['receipt'];difference=receipt['reserved']-sum(receipt[k] for k in ('purchase','labor','engineering','refunded'))
    source['audited']=dict(age=game.player.age,auditor=job['person'],difference=difference)
    return f'原案卷已复核，收支差额{difference}灵石。'+('记录账差，须按实际回执追查，不自动认定人物有罪。' if difference else '款项结清，采购及交付凭据保留。')

def close(game,job,*,cancel=False):
    if cancel:
        from ..relationship_records import find_person
        from .court_bureau_rules import officer_reason
        obstruction=officer_reason(game,find_person(game,job['person']),assigned=True) if job['person']!='player' else ''
        if job.get('offer',{}).get('operation'):
            from .court_enforcement import action_reason
            obstruction=obstruction or action_reason(game,job)
        job['closure_obstruction']=obstruction
    if job['cargo']:
        market=local_market(game)
        if not market or market['location']!=game.player.location_id:raise ValueError('此地缺少接收公物的原市场')
        for item,n in job['cargo'].items():
            if item not in market['commodities']:raise ValueError('原市场不能接收此公物')
            market['commodities'][item]['stock']+=n;reprice(game,market,market['commodities'][item])
        job['cargo'].clear()
    refund=balance(game,job['wallet']);transfer_value(game,job['wallet'],COURT,refund,'公务结清余款退回原天庭府库')
    job['receipt']=dict(reserved=job['budget'],purchase=job['purchase'],labor=job['spent'],engineering=job.get('engineering',0),refunded=refund,
        result='交接取消' if cancel else job.get('result',''),location=game.player.location_id)
    job.update(status='closed',phase='closed',closed=game.player.age,cancelled=cancel)

def diversion_reason(game,job):
    if job['kind']!='works' or job['person']!='player' or job.get('delivered') or job.get('diversion') or not job['cargo']:return '仅本人未交付的实货调拨案可应急改拨一次'
    if game.player.location_id==job['location']:return '已经在原交付地点，应按原合同交付'
    market=local_market(game)
    if not market or any(market['commodities'].get(k,{}).get('stock',0)>=market['commodities'].get(k,{}).get('target',0)*.5 for k in job['cargo']):return '当前原市场没有对应实物短缺，不得挪作私人用途'
    return ''

def divert(game,job):
    if blocked:=diversion_reason(game,job):raise ValueError(blocked)
    market=local_market(game);goods=dict(job['cargo'])
    for key,n in goods.items():
        row=market['commodities'][key];row['stock']+=n;reprice(game,market,row)
    job['cargo'].clear();job['diversion']=dict(age=game.player.age,location=game.player.location_id,market=market['id'],goods=goods,shortage=True)
    return '原公物已实际用于此地应急补缺；原合同仍欠交，交接后须接受用途监察并补交或接受经办资格处分。'

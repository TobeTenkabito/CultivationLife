"""Narrow civic adapters write original stocks, rights, jobs and fixed road facts."""
import math
from ..content_registry import CONTENT_DOCUMENTS, ITEM_CATALOG
from ..economy_content import BASE_PRICES, material_id
from ..rules import remove_item
from . import building_projects as projects
from .earth_dispute_facts import original, stale_reason
from .earth_temple_facilities import fingerprint
from .earth_temple_rules import state


def quote(game, case, option):
    row=original(game,case); kind=case['kind']
    names = {
        'water': [('release','分水停耕',10,6,'药田暂停新投产10年，在制批次延后10年；维护费照常。'),('canal','出资修渠',30,10,'投入工程工料解决本期用水诉求，保留原批次与生产安排。')],
        'supply': [('donate','实物补缺',10,8,'从行囊实交约定数量，进入原市场库存；不另收货款。'),('retain','保留自用物资',5,-6,'保留全部物资，明确不承担这次补货，接受地方信任损失。')],
        'road': [('clear','完整清障',20,8,'清除本期道路额外耗时；不会降低原地域境界门槛。'),('bypass','标出缓行道',10,3,'降低工料投入；本期该路仍额外耗时2年。')],
        'property': [('open','开放公共使用',10,8,'原庙开放使用；所有权、设施、香火仍留原记录。'),('private','维持自用边界',5,-4,'原庙设为非公开，保留已有具名许可；不转移产权。')],
        'guard': [('repair','修复原阵',10,8,'投入修阵资源，修复此地镇地阵的完整度。'),('suspend','暂停护境承诺',5,-3,'暂停本庙主持及助修，受损镇地阵仍留原地，待以后修复。')],
        'rebuild': [('restore','完整原址复建',20,10,'沿原建筑重建；城市依原规则回到一级且清空发展与设施。'),('relief','先作应急安置',10,3,'支付应急工料，登记本期安置支出；遗址仍须另行完整重建。')],
    }
    spec=next((r for r in names[kind] if r[0]==option),None)
    if not spec: raise ValueError('未知争议处理方案')
    key,name,years,trust,effect=spec
    labor,ore = {('water','canal'):(160,24),('road','clear'):(100,16),('road','bypass'):(30,4),('rebuild','relief'):(20,4)}.get((kind,key),(0,0))
    bill=dict(coins=int(BASE_PRICES[8]*labor),materials={material_id('celestial',9,'ore_structure'):ore} if ore else {},reason='')
    extra={}; reason=stale_reason(game,case)
    if row and kind=='rebuild' and key=='restore': bill=projects.quote(game,'rebuild',row)
    if row and kind=='supply' and key=='donate':
        bill['materials']={case['target']:case['quantity']}
    if row and kind=='guard' and key=='repair':
        definition=next(d for d in CONTENT_DOCUMENTS['formations.json']['maintenance_resources'] if d['world']=='celestial')
        qty=min(10,max(1,math.ceil((100-row['durability'])/definition['repair_value'])))
        extra=dict(supply=definition['id'],quantity=qty,name=definition['name'])
        if game.player.formation_repair_supplies.get(definition['id'],0)<qty: reason=reason or '原修阵资源不足'
    held={i.id:i.quantity for i in game.player.inventory}
    if held.get('spirit_stone',0)<bill['coins'] or any(held.get(k,0)<n for k,n in bill['materials'].items()): reason=reason or '灵石或实物工料不足'
    reason=reason or bill['reason']
    if kind=='water' and row:
        # Exclude annual account churn: settlement still rechecks ownership and current job.
        facts=[row['id'],row['owner_kind'],row['owner_id'],row.get('building_status'),row.get('job'),row.get('public_water_until')]
    elif kind=='road': facts=[case.get('delay'),case['until']]
    else: facts=row
    return dict(id=key,name=name,years=years,trust=trust,effect=effect,bill=bill,extra=extra,reason=reason,
                cost=projects.bill_text(bill)+(f"；{extra['name']} ×{extra['quantity']}" if extra else ''),
                token=fingerprint([case['id'],key,facts,bill,extra,reason]))


def options(game,case):
    keys={'water':('release','canal'),'supply':('donate','retain'),'road':('clear','bypass'),
          'property':('open','private'),'guard':('repair','suspend'),'rebuild':('restore','relief')}
    return [quote(game,case,k) for k in keys[case['kind']]]


def settle(game,case,plan):
    if plan['reason']: raise ValueError(plan['reason'])
    row=original(game,case); kind=case['kind']; choice=plan['id']
    if kind=='supply' and choice=='donate':
        from .economy.state import local_market, reprice
        # A donation is actual stock, not a fabricated sale or an extra money pool.
        if not remove_item(game.player,case['target'],case['quantity']): raise ValueError('持有商品不足')
        market=local_market(game); row['stock']+=case['quantity']; reprice(game,market,row)
    elif kind=='guard' and choice=='repair':
        from .formation.maintenance import repair
        extra=plan['extra']; definition=next(d for d in CONTENT_DOCUMENTS['formations.json']['maintenance_resources'] if d['id']==extra['supply'])
        repair(game,row,extra['supply'],definition,extra['quantity'])
    elif kind=='rebuild' and choice=='restore':
        from .building_destruction import rebuild
        rebuild(game,row,None)
    else:
        if plan['bill']['coins'] or plan['bill']['materials']: projects.pay(game,plan['bill'],'地方争议：'+plan['name'])
        if kind=='water' and choice=='release':
            from .economy.enterprise_state import log
            row['public_water_until']=max(game.player.age,row.get('public_water_until',0))+10
            if row.get('job'): row['job']['finish']+=10
            row['revision']+=1; log(row,game.player.age,'地方分水约定：停开新批次10年，在制批次延后10年；维护照常')
        elif kind=='road': case['delay']=0 if choice=='clear' else 2
        elif kind=='property': projects.set_public(game,row,choice=='open')
        elif kind=='guard': state(game)['active']=False
    return plan['effect']

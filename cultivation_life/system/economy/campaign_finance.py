"""Economic backing for the existing, authorized Lanjiang expedition only.

The campaign's original source/carried/target counters own the purchased goods;
these receipts never hold a second copy. Its transport and people remain unchanged.
"""
from math import ceil
from .ledger import account, balance, transfer_value
from .organizations import register
from .state import ensure_regional_market, reprice
from .local_market import quote


def address(identity, side):
    return f'campaign:{identity}:{side}'


def purchase(game,market,source,item,quantity,reason):
    product=market['commodities'][item];bill=quote(product,'buy',quantity)
    transfer_value(game,source,f'market:{market["id"]}',bill['total'],reason)
    transfer_value(game,f'market:{market["id"]}',f'operator:{market["id"]}',bill['fee'],'远征采购手续费')
    product['stock']-=quantity;product['volume']+=quantity
    market['turnover']+=bill['gross'];market['fees']+=bill['fee']
    market['war_income']=market.get('war_income',0)+bill['total']
    from .market_power import record_trade
    record_trade(game,market,item,source,'buy',quantity)
    reprice(game,market,product)
    return bill['total']


def prepare(game,maps,identity,side,owner,world,location,budget,quantity=0,materials=0):
    """No money or goods appear when a sponsor cannot fund the whole commitment."""
    key=address(identity,side)
    books=game.economy_v2.get('campaigns',{})
    if key in books:return True
    entity=game.sects.get(owner)
    if not entity or entity.extinct or entity.world!=world:return False
    register(game,'sect',owner,world)
    ensure_regional_market(game,maps,world,location)
    market=game.economy_v2['markets'][f'{world}:{location}'];source=f'organization:sect:{owner}'
    goods=sorted((k for k,v in market['commodities'].items() if int(v['stock'])>=quantity),key=lambda k:market['commodities'][k]['price'])
    if quantity and not goods:return False
    item=goods[0] if quantity else None
    bill=quote(market['commodities'][item],'buy',quantity)['total'] if item else 0
    if balance(game,source)<budget+bill+materials:return False
    account(game,key)
    if item:purchase(game,market,source,item,quantity,'远征初始实物筹备')
    if materials:
        transfer_value(game,source,f'market:{market["id"]}',materials,'当地阵坊承制有限远征界门组件')
        market['turnover']+=materials;market['war_income']=market.get('war_income',0)+materials
    transfer_value(game,source,key,budget,'远征专项经费真实预留')
    game.economy_v2.setdefault('campaigns',{})[key]=dict(owner=owner,world=world,location=location,
        supply_item=item,quantity=quantity,procurement=bill+materials,opening=budget,charged=0,
        extra=0,purchased=0,destroyed=0,coverage=1.,gate_opened=False,refunded=False)
    return True


def settle(game,maps,identity,side,spent,world,location,*,portal_scale=0,finished=False):
    key=address(identity,side);book=game.economy_v2.get('campaigns',{}).get(key)
    if not book or book['refunded']:return 1.
    ensure_regional_market(game,maps,world,location)
    market=game.economy_v2['markets'][f'{world}:{location}']
    cost=max(0,spent-book['charged'])
    extra=ceil(portal_scale*100) if portal_scale else 0
    if portal_scale and not book['gate_opened']:
        extra+=ceil(portal_scale*1000);book['gate_opened']=True
    wanted=cost+extra;available=min(wanted,balance(game,key));budget=int(available*(.1 if side=='attacker' else .2))
    purchased=0
    # Real local consumption: procurement immediately consumes these supplies,
    # separate from the expedition's already-purchased transported stock.
    for item,product in sorted(market['commodities'].items(),key=lambda p:p[1]['price'])[:6]:
        lo,hi=0,min(10000,int(product['stock']))
        while lo<hi:
            mid=(lo+hi+1)//2
            if quote(product,'buy',mid)['total']<=budget-purchased:lo=mid
            else:hi=mid-1
        if lo:purchased+=purchase(game,market,key,item,lo,'远征前线军需采购并消耗')
    energy=min(balance(game,key),available-purchased)
    sink=f'war-consumed-stones:{world}';account(game,sink)
    transfer_value(game,key,sink,energy,'远征军用灵石与界门能源实际消耗')
    # A missed commodity order is not fabricated market revenue.
    book['charged']=spent;book['extra']+=extra;book['purchased']+=purchased;book['destroyed']+=purchased+energy
    book['coverage']=min(1,(purchased+energy)/max(1,wanted)) if wanted else 1.
    if finished:
        register(game,'sect',book['owner'],book['world'])
        transfer_value(game,key,f'organization:sect:{book["owner"]}',balance(game,key),'远征结束退还原赞助府库余款')
        book['refunded']=True
    return book['coverage']

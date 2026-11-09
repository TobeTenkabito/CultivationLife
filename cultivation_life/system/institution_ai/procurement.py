"""Shared exact-stock purchase; quotes never reserve or synthesize materials."""
from ..economy.local_market import quote
from ..economy.ledger import balance,transfer_value
from ..economy.state import reprice

def cost(market,materials):
    if not market:raise ValueError('原址市场尚未建立')
    bills={}
    for item,n in materials.items():
        product=market['commodities'].get(item)
        if not product or product['stock']<n:raise ValueError('原市场实际工料不足')
        bills[item]=quote(product,'buy',n)
    return sum(b['total'] for b in bills.values())

def buy(game,market,materials,wallet,*,party):
    total=cost(market,materials)
    if balance(game,wallet)<total:raise ValueError('原托管款不足以支付当前实货报价，请示后重新立项')
    cargo={}
    for item,n in materials.items():
        product=market['commodities'][item];bill=quote(product,'buy',n)
        transfer_value(game,wallet,'market:'+market['id'],bill['total'],'机构项目采购原市场实货')
        transfer_value(game,'market:'+market['id'],'operator:'+market['id'],bill['fee'],'机构项目采购手续费')
        product['stock']-=n;product['volume']+=n;market['turnover']+=bill['gross'];market['fees']+=bill['fee']
        from ..economy.market_power import record_trade
        record_trade(game,market,item,party,'buy',n)
        reprice(game,market,product);cargo[item]=n
    return cargo,total

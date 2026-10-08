"""Physical military stock. Value is a projection, never an additional wallet."""
from math import ceil
from ...content_registry import ITEM_CATALOG, MARKET_GOODS
from ..economy import depot
from ..economy.ledger import account, balance, transfer_value
from ..economy.state import ensure_regional_market, reprice
from ..economy.local_market import quote


def wallet(war,side):
    return f'war-supply:{war["id"]}:{side}'


def category(item):
    tags=set(ITEM_CATALOG[item].tags) if item in ITEM_CATALOG else set()
    if tags & {'pill','healing','medicine','elixir'}:return 'medical'
    if tags & {'equipment','artifact','weapon'}:return 'arms'
    if tags & {'talisman','formation_material','material','herb'}:return 'material'
    return 'general'


def price(game,row,item):
    market=game.economy_v2['markets'].get(f"{row['world']}:{row['location']}",{})
    product=market.get('commodities',{}).get(item)
    if product:return max(1,float(product['price']))
    return max(1,next((g['price'] for g in MARKET_GOODS if g['kind']=='item' and g['content_id']==item),1))


def goods_value(game,row):
    return sum(price(game,row,k)*n for k,n in row.get('items',{}).items())


def total(game,war,side):
    row=war.get('logistics',{}).get('sides',{}).get(side)
    return round(goods_value(game,row)+balance(game,wallet(war,side))) if row else 0


def add_shipment(game,row,item,quantity,loss):
    lost=min(quantity,round(quantity*loss))
    row['items'][item]=row['items'].get(item,0)+quantity-lost
    value=price(game,row,item)*lost
    row['transport_loss']+=round(value)
    row['destroyed']+=round(value)
    return quantity-lost


def purchase(game,maps,war,side,world,location,budget,*,loss=0):
    ensure_regional_market(game,maps,world,location)
    market=game.economy_v2['markets'][f'{world}:{location}'];row=war['logistics']['sides'][side]
    budget=min(max(0,int(budget)),balance(game,wallet(war,side)))
    spent=0
    goods=sorted((k for k,v in market['commodities'].items() if k in ITEM_CATALOG and v['stock']>=1),
                 key=lambda k:(market['commodities'][k]['price'],k))
    # At most six finite orders, no per-soldier or per-year buying loop.
    for item in goods[:6]:
        product=market['commodities'][item];low,high=0,min(1000000,int(product['stock']))
        while low<high:
            mid=(low+high+1)//2
            if quote(product,'buy',mid)['total']<=budget-spent:low=mid
            else:high=mid-1
        if not low:continue
        bill=quote(product,'buy',low)
        transfer_value(game,wallet(war,side),f'market:{market["id"]}',bill['total'],'军队采购真实战备商品')
        transfer_value(game,f'market:{market["id"]}',f'operator:{market["id"]}',bill['fee'],'军需商品交易手续费')
        product['stock']-=low;product['volume']+=low
        market['turnover']+=bill['gross'];market['fees']+=bill['fee']
        market['war_income']=market.get('war_income',0)+bill['total']
        from ..economy.market_power import record_trade
        record_trade(game,market,item,wallet(war,side),'buy',low)
        reprice(game,market,product)
        add_shipment(game,row,item,low,loss)
        row['purchased']+=bill['total'];spent+=bill['total']
    return spent


def mobilize(game,maps,war,side,entity,amount,distance):
    row=war['logistics']['sides'][side];stock=depot.find(game,entity)
    loss=min(.7,.02+distance*.003+(.2 if row.get('cross_realm') else 0))
    value=0
    if stock:
        for key in sorted(stock['stock']):
            if not key.startswith('item:') or stock['stock'][key]<=0:continue
            item=key[5:]
            if item not in ITEM_CATALOG:continue
            quantity=min(stock['stock'][key],int(max(0,amount-value)/price(game,row,item)))
            if not quantity:continue
            stock['stock'][key]-=quantity
            add_shipment(game,row,item,quantity,loss)
            value+=price(game,row,item)*quantity
            depot.record(stock,game,f'调拨前线：{ITEM_CATALOG[item].name} ×{quantity}，运输损耗按距离结算')
    cash=min(max(0,int(amount-value)),balance(game,depot.treasury(game,entity)))
    transfer_value(game,depot.treasury(game,entity),wallet(war,side),cash,'势力筹备战争采购金与灵石能源')
    if cash:
        purchase(game,maps,war,side,entity.world,entity.location_id,int(cash*.8),loss=loss)
    return round(value)+cash


def take_items(game,row,value):
    removed={};remaining=max(0,float(value));paid=0.
    for item in sorted(row['items'],key=lambda k:price(game,row,k)):
        count=row['items'][item]
        if not count or remaining<=0:continue
        unit=price(game,row,item)
        n=min(count,max(1,ceil(remaining/unit)))
        row['items'][item]-=n;removed[item]=n
        paid+=unit*n;remaining-=unit*n
    return removed,paid


def consume(game,war,side,amount,reason,*,cash_only=False):
    row=war['logistics']['sides'][side];amount=max(0,int(amount))
    # Stones power arrays, but cannot replace all medicines, arms and supplies.
    removed,goods=( {},0) if cash_only else take_items(game,row,amount*.75)
    cash=min(balance(game,wallet(war,side)),amount if cash_only else max(0,int(amount-min(amount,goods))),
             amount if cash_only else ceil(amount*.25))
    sink=f'war-consumed-stones:{row["world"]}';account(game,sink)
    transfer_value(game,wallet(war,side),sink,cash,reason+'：灵石能源实际耗尽')
    actual=round(goods)+cash
    row['spent']+=actual;row['destroyed']+=actual
    row['consumed_items']={k:row.get('consumed_items',{}).get(k,0)+n for k,n in removed.items()} | {
        k:n for k,n in row.get('consumed_items',{}).items() if k not in removed}
    return min(amount,actual)


def raid(game,war,side,value):
    enemy='defender' if side=='attacker' else 'attacker'
    source=war['logistics']['sides'][enemy];target=war['logistics']['sides'][side]
    removed,lost=take_items(game,source,value)
    received=0
    for item,count in removed.items():
        kept=int(count*.6)
        target['items'][item]=target['items'].get(item,0)+kept
        received+=price(game,target,item)*kept
        source['destroyed']+=round(price(game,source,item)*(count-kept))
    # Cash is physical spirit stones: stolen portion transfers, the rest shatters.
    cash=min(balance(game,wallet(war,enemy)),max(0,int(value-lost)))
    kept=int(cash*.6)
    transfer_value(game,wallet(war,enemy),wallet(war,side),kept,'因粮于敌：缴获原军需灵石')
    consume(game,war,enemy,cash-kept,'劫粮中损毁',cash_only=True)
    return round(received)+kept


def return_items(game,war,side,entities):
    row=war['logistics']['sides'][side]
    # Keep goods at their actual battlefield. Returning money is not permission
    # to teleport stock to a former headquarters.
    owner=next((e for e in entities if e.world==row['world'] and e.location_id==row['location']),None)
    if owner:
        stock=depot.ensure(game,owner)
        for item,n in row['items'].items():
            room=max(0,10000-depot.occupied(stock))
            retained=min(n,room)
            stock['stock']['item:'+item]=stock['stock'].get('item:'+item,0)+retained
            row['items'][item]-=retained
        depot.record(stock,game,'停战接收本地未消耗军需；异地物资未遥移')
    # Unreturned goods remain in the original war pool as demobilized stores.

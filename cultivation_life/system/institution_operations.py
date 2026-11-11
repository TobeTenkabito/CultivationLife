"""Original public assets, consignment receipts and paid personnel development.

Content adapters own eligibility, prices and policy. No faction-specific rules.
"""
from .institution_ai import procurement, contracts
from .institution_ai.rules import digest, person_reason
from .economy.ledger import balance, transfer_value


def book(row):
    return row.get('operations', dict(income=0, expense=0, salary=0, settlements=0,
        deliveries=0, sequence=0, last_signed=0, last_training=0, last_reward=0,last_performance=0,
        term_baseline=0,policy='reserve', contract=None))


def mutable(row):
    return row.setdefault('operations', book(row))


def market(game, row):
    return game.economy_v2['markets'].get(row['world']+':'+row['location'])


def purchase_quote(game, row, materials, coins=0):
    reason=''
    try: total=procurement.cost(market(game,row),materials)+coins
    except ValueError as error: total=0;reason=str(error)
    if not reason and balance(game,row['wallet'])<total:reason='本府公款不足'
    return dict(total=total,coins=coins,materials=materials,reason=reason)


def facility_quote(game,row,building,identity,spec):
    from .building_projects import grade
    from ..economy_content import BASE_PRICES, material_id
    rank=grade(row['world'])
    materials={material_id(row['world'],rank,k):n for k,n in
               zip(('ore_structure','ore_conduct','ore_store'),spec['materials'])}
    q=purchase_quote(game,row,materials,int(BASE_PRICES[rank-1]*spec['labor_units']))
    installed=building.get('office_facilities',[])
    if any(f['id']==identity for f in installed):q['reason']='该设施已经建成'
    elif len(installed)>=2:q['reason']='府署两个专项设施位已满'
    return q


def install(game,row,building,identity,q):
    from .building_projects import pay
    cargo,paid=procurement.buy(game,market(game,row),q['materials'],row['wallet'],party=row['source'])
    pay(game,q,'原公署专项设施营造',payer=row['wallet'],stock=cargo)
    building.setdefault('office_facilities',[]).append(dict(id=identity,coins=q['coins'],materials=dict(q['materials'])))
    mutable(row)['expense']+=paid+q['coins']


def training(game,row,identity,axis):
    from ..relationship_records import find_person
    from .npc_development.targets import Target
    from .npc_development.service import quote
    if identity not in row['people']:raise ValueError('须为本府原名册属员')
    if reason:=person_reason(game,identity,row['world'],row['location']):raise ValueError(reason)
    person=find_person(game,identity)
    target=Target('npc',identity,person,person,('原机构属员',))
    plan=quote(game,'npc',identity,axis,'material',1,_target=target,stock={})
    materials={plan['material_id']:plan['material_count']}
    q=purchase_quote(game,row,materials)
    q['growth']=f"{plan['label']}：{plan['before']} → {plan['after']}"
    q['facts']=digest(target.facts(game))
    return target,q


def train(game,row,identity,axis,q):
    from .npc_development.service import apply
    target,current=training(game,row,identity,axis)
    if current!=q or q['reason']:raise ValueError(q['reason'] or '原人物培养报价已变化')
    cargo,paid=procurement.buy(game,market(game,row),q['materials'],row['wallet'],party=row['source'])
    result=apply(game,'npc',identity,axis,'material',1,_target=target,stock=cargo)
    state=mutable(row);state['expense']+=paid;state['last_training']=game.player.age
    return result


def supply_quote(game,row,item,quantity,periods,interval,service_percent):
    from .economy.local_market import quote
    from ..content_registry import ITEM_CATALOG, restricted_acquisition
    m=market(game,row);p=m['commodities'].get(item) if m else None
    if type(service_percent) is not int or not 0<=service_percent<=100:raise ValueError('供货经办费率无效')
    if item not in ITEM_CATALOG or restricted_acquisition('item',item) or not p:
        raise ValueError('原市场没有此项合法供货需求')
    if p['stock']+quantity*periods>p['target']:raise ValueError('原市场真实缺口不足本次合同总量')
    bill=quote(p,'sell',quantity)
    q=dict(item=item,quantity=quantity,periods=periods,interval=interval,price=bill['gross'],fee=bill['fee'],
           total=bill['gross']*periods,service_percent=service_percent,materials={},reason='')
    if q['price']<=q['fee']:q['reason']='供货金额不足以支付交易费用'
    elif balance(game,'market:'+m['id'])<q['total']:q['reason']='原采购市场实款不足，不能签发欠资合同'
    elif game.player.age+periods*interval>=row['expires']:q['reason']='剩余任期不足以完成各期交货'
    return q


def sign(game,row,q):
    state=mutable(row);sequence=state['sequence']+1;m=market(game,row)
    contract=contracts.reserve(game,row['id']+':supply:'+str(sequence),'market:'+m['id'],row['world'],row['location'],
        q['item'],q['quantity'],q['price'],q['periods'],q['interval'],row['expires'])
    contract.update(fee=q['fee'],service_percent=q['service_percent'],supplier=game.id)
    state.update(contract=contract,sequence=sequence,last_signed=game.player.age)


def deliver(game,row):
    from ..rules import remove_item
    from .economy.state import reprice
    from .economy.market_power import record_trade
    state=mutable(row);c=state['contract'];m=market(game,row)
    if not c or not m or c['item'] not in m['commodities']:raise ValueError('原合同或交付市场已失效')
    if c['supplier']!=game.id:raise ValueError('不能冒领原供货人的合同')
    product=m['commodities'][c['item']]
    available=sum(i.quantity for i in game.player.inventory if i.id==c['item'])
    def receive(n):product['stock']+=n
    def consume(n):
        if not remove_item(game.player,c['item'],n):raise ValueError('原供货实物未能扣除，交货与货款均未结算')
    contracts.deliver(game,c,row['wallet'],available,consume,receive)
    net=c['price']-c['fee'];service=net*c['service_percent']//100
    transfer_value(game,row['wallet'],'player',net-service,'原供货人实物货款')
    transfer_value(game,row['wallet'],'operator:'+m['id'],c['fee'],'供货原交易手续费')
    product['volume']+=c['quantity'];m['turnover']+=c['price'];m['fees']+=c['fee']
    record_trade(game,m,c['item'],'player','sell',c['quantity']);reprice(game,m,product)
    state['income']+=service;state['deliveries']+=1;state['last_performance']=game.player.age
    return service


def distribute(game,row,profit,*,tribute_percent,salary_percent):
    """Only new realized surplus can fund remuneration, never grants or deposits."""
    tribute=profit*tribute_percent//100;salary=profit*salary_percent//100
    if tribute+salary>profit or min(tribute,salary)<0:raise ValueError('收益分配比例无效')
    if salary and row['holder']!='player':raise ValueError('个人待遇须由原在任人当面领取')
    transfer_value(game,row['wallet'],row['source'],tribute,'原经营盈余实缴')
    transfer_value(game,row['wallet'],'player',salary,'原经营盈余总督待遇')
    row['returned']+=tribute;mutable(row)['salary']+=salary
    return tribute,salary

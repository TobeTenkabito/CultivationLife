"""Asura local development policy over original cities, people and receipts."""
import copy
from . import rules
from .. import institution_authority as authority, institution_operations as operations
from ..institution_ai import contracts, procurement
from ..institution_ai.rules import digest
from ..economy.ledger import balance


def config():return rules.config().get('development',{})


def enabled():return rules.enabled() and bool(config())


def require(game,row):
    if not enabled():raise ValueError('修罗经营内容未启用，仅可交接原供货合同')
    if not rules.local(game,row) or not authority.effective(game,row):raise ValueError('须由在任总督亲临原府办理')
    city=next((c for c in rules.cities(game) if c['id']==row['city_id']),None)
    b=rules.building(game,row)
    if not city or not rules.legal_city(game,city):raise ValueError('原城市或设府许可失效')
    if not b or b['status']!='intact' or b['owner']!=row['owner']:raise ValueError('须先修复原府署并核验公产归属')
    return city,b


def quote(game,row,operation):
    city,b=require(game,row);state=operations.book(row);cfg=config()
    q=dict(total=0,coins=0,materials={},reason='')
    installed={f['id'] for f in b.get('office_facilities',[])}
    if operation.startswith('facility:'):
        key=operation.split(':',1)[1]
        if key not in cfg['facilities']:raise ValueError('未知府署设施')
        q=operations.facility_quote(game,row,b,key,cfg['facilities'][key])
    elif operation.startswith('city:'):
        from ..building_management import quote as city_quote
        kind=operation.split(':',1)[1]
        if kind not in {'exchange','settle','aid'}:raise ValueError('未知公产经办事项')
        q=city_quote(game,city,kind,administration=row,stock={})
        purchase=operations.purchase_quote(game,row,q['materials'],q['coins'])
        q.update(total=purchase['total'],reason=(q['reason'] if q['reason']!='灵石或设施工料不足' else '') or purchase['reason'])
    elif operation.startswith('train:'):
        axis=operation.split(':',1)[1]
        if axis not in {'cultivation','body','sense'}:raise ValueError('未知演武方向')
        if 'training' not in installed:raise ValueError('须先建成演武院')
        if not row['people']:raise ValueError('须先登记一名原址属员')
        _,q=operations.training(game,row,row['people'][0],axis)
        if state['last_training'] and game.player.age<state['last_training']+cfg['training_interval']:
            q['reason']='本府本轮演武已用，须度过二十个真实年份'
    elif operation.startswith('supply:'):
        from ...economy_content import material_id
        key=operation.split(':',1)[1]
        if key not in {'ore_structure','ore_conduct','ore_store'}:raise ValueError('未知供货种类')
        if state['contract'] and state['contract']['status']=='active':raise ValueError('须先履行或交接原供货合同')
        if state['sequence'] and game.player.age<state['last_signed']+cfg['contract_cycle']:raise ValueError('本府本期已经签约，取消也不刷新五十年周期')
        q=operations.supply_quote(game,row,material_id(row['world'],9,key),8 if 'supply' in installed else 4,
                                  3 if 'supply' in installed else 1,cfg['contract_interval'],cfg['consignment_fee_percent'])
    elif operation=='deliver':
        c=state['contract']
        if not c or c['status']!='active':raise ValueError('没有待履行合同')
        if game.player.age<c['next'] or game.player.age>c['deadline']:q['reason']='尚未到交货期或合同已逾期'
        elif sum(i.quantity for i in game.player.inventory if i.id==c['item'])<c['quantity']:q['reason']='原行囊供货实物不足'
    elif operation=='reward':
        period=cfg['reward_interval']
        if state['settlements']+state['deliveries']-state['term_baseline']<3 or state['income']<=0:q['reason']='本任须完成至少三笔真实经营或交货并取得收入'
        elif game.player.age<max(row['appointed'],state['last_reward'])+period:q['reason']='本任须满五十年，两次考绩也须间隔五十年'
        elif state['last_reward']>=state['last_performance']:q['reason']='上次考绩后尚无新增履约，不能重复申领'
    elif operation.startswith('policy:'):
        if operation.split(':',1)[1] not in cfg['policies']:raise ValueError('未知地方经营方针')
        if state['policy']==operation.split(':',1)[1]:q['reason']='当前已采用该方针'
    else:raise ValueError('未知地方经营事项')
    m=operations.market(game,row)
    q['token']=digest([operation,row,b,city,q,game.player.age,balance(game,row['wallet']),m.get('revision') if m else None])
    return q


def distribute(game,row,profit):
    policy=config()['policies'][operations.book(row)['policy']]
    tribute,salary=operations.distribute(game,row,profit,tribute_percent=policy['tribute'],salary_percent=policy['salary'])
    from .. import institution_garrisons as troops
    units=troops.active(row);military=profit*policy['garrison']//100
    from ..institution_deliberation import book as mandates
    if mandates(row)['mandate']['funding']=='local' and military and units and len(troops.stationed(game,row,row['location']))==len(units):
        troops.provision(game,row,military)
    else:military=0
    return f'新增净盈余 {profit:,}，实缴 {tribute:,}，在任待遇 {salary:,}，原军营务 {military:,}；其余留府。'


def command(game,row,payload):
    operation=payload.get('operation')
    if not isinstance(operation,str):raise ValueError('地方经营请求无效')
    if operation=='cancel':
        if not rules.local(game,row) or row['controller']!='player':raise ValueError('须由原任在原址交接合同')
        c=operations.book(row)['contract']
        if not c or c['status']!='active':raise ValueError('没有待交接供货合同')
        contracts.cancel(game,c);text='未交付货款退原采购市场，已交实物和已付报酬不回滚。'
    else:
        q=quote(game,row,operation)
        if q['token']!=payload.get('quote'):raise ValueError('经营报价、市场或人员状态已变化，请刷新')
        if q['reason']:raise ValueError(q['reason'])
        state=operations.mutable(row);city,b=require(game,row)
        if operation.startswith('facility:'):
            key=operation.split(':',1)[1];operations.install(game,row,b,key,q)
            text=config()['facilities'][key]['name']+'已在原府建成，公款和实际材料已支付；损毁后须连同设施全额重建。'
        elif operation.startswith('city:'):
            from ..building_management import settle
            cargo,paid=procurement.buy(game,operations.market(game,row),q['materials'],row['wallet'],party=row['source'])
            settle(game,city,operation.split(':',1)[1],q,payer=row['wallet'],stock=cargo)
            state['expense']+=paid+q['coins'];state['income']+=q['receipt']
            if operation=='city:settle':state['settlements']+=1;state['last_performance']=game.player.age
            text='按原城市账本完成经办。'+distribute(game,row,max(0,q['receipt']-q['coins']-paid))
        elif operation.startswith('train:'):
            text=operations.train(game,row,row['people'][0],operation.split(':',1)[1],{k:v for k,v in q.items() if k!='token'})
        elif operation.startswith('supply:'):
            operations.sign(game,row,q);text=f"原市场全额备款，按期交付行囊实物；净货款 {100-q['service_percent']}% 归原供货人，{q['service_percent']}% 经办收入留府再按方针分配。"
        elif operation=='deliver':text='本期实货交付。'+distribute(game,row,operations.deliver(game,row))
        elif operation=='reward':
            state['last_reward']=game.player.age
            court=rules.court(game);court['earned']+=config()['reward_merit'];court['merit']+=config()['reward_merit'];court['regard']=min(100,court['regard']+1)
            text=f"本任新增实绩核验，功勋 +{config()['reward_merit']}，王庭观感 +1；下次须有新增履约并满五十年。"
        else:
            state['policy']=operation.split(':',1)[1];text='地方方针改为'+config()['policies'][state['policy']]['name']+'；只影响以后新取得的净盈余。'
    authority.log(game,row,text)
    return text


def public(game,row):
    if not rules.local(game,row) or 'player' not in (row['holder'],row['controller']):return None
    if not config() and 'operations' not in row:return None
    state=operations.book(row);options=[]
    names={'city:exchange':'公产 · 营造市舶会馆','city:settle':'公产 · 核办当年市集','city:aid':'民生 · 实付赈济街坊',
           'train:cultivation':'演武 · 属员修为','train:body':'演武 · 属员炼体','train:sense':'演武 · 属员神识',
           'supply:ore_structure':'供货 · 结构矿材','supply:ore_conduct':'供货 · 导灵矿材','supply:ore_store':'供货 · 蓄灵矿材',
           'deliver':'供货 · 交付本期实物','reward':'考绩 · 呈报本任实绩'}
    names.update({'facility:'+k:'府署 · 营造'+s['name'] for k,s in config().get('facilities',{}).items()})
    names.update({'policy:'+k:'方针 · '+s['name'] for k,s in config().get('policies',{}).items()})
    if enabled() and authority.effective(game,row):
        for identity,name in names.items():
            try:q=quote(game,row,identity)
            except ValueError as error:q=dict(total=0,reason=str(error),token='')
            if identity.startswith('facility:'):q['description']=config()['facilities'][identity.split(':',1)[1]]['description']
            elif identity.startswith('policy:'):q['description']=config()['policies'][identity.split(':',1)[1]]['description']
            elif identity.startswith('supply:') and 'price' in q:
                net=q['price']-q['fee'];fee=net*q['service_percent']//100
                q['description']=f"每期 {q['quantity']} 件，间隔 {q['interval']} 年，共 {q['periods']} 期。原供货人实收 {net-fee:,}，本府经办收入 {fee:,}，原交易费 {q['fee']:,} 灵石；按实际交货结算。"
            options.append(dict(id=identity,name=name,**q))
    c=state['contract']
    if c and c['status']=='active':options.append(dict(id='cancel',name='交接 · 退回未交付货款',reason='',token='',total=0))
    from ...content_registry import ITEM_CATALOG
    contract=copy.deepcopy(c)
    if contract:contract['item_name']=ITEM_CATALOG[c['item']].name
    return dict(income=state['income'],expense=state['expense'],salary=state['salary'],
        policy=config().get('policies',{}).get(state['policy'],{}).get('name','留府交接'),
        policy_description=config().get('policies',{}).get(state['policy'],{}).get('description',''),
        contract=contract,options=options,facilities=[f['id'] for f in (rules.building(game,row) or {}).get('office_facilities',[])])


def advance(game,row):
    c=operations.book(row)['contract']
    if c and c['status']=='active' and (not enabled() or game.player.age>c['deadline'] or not authority.effective(game,row)):
        contracts.cancel(game,c)
        authority.log(game,row,'原供货许可终止，未交付预付款退原市场；原货与既有履约记录保留。')

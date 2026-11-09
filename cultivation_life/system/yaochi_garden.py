"""One paid Yaochi farm deed, fixed-term operation and escrow-backed orders."""
import copy
from ..content_registry import ITEM_CATALOG
from ..models import HistoryRecord
from ..runtime import now_iso
from ..relationship_records import find_person
from .yaochi_rules import config,spend
from .westward_rules import record,enabled
from .westward_finance import YAOCHI
from .yaochi_fair_rules import people
from .court_bureau_rules import digest
from .economy.enterprise_state import estates,payer,take,encumbered
from .economy.operating_license import allowed,production_reason,steward_reason
from .economy.enterprise_acquisition import acquire,price
from .economy.enterprise_actions import command as estate_command
from .economy.enterprise_rules import recipes
from .economy.resource_access import permits
from .economy.ledger import account,balance,transfer_value
from .economy.state import local_market,commodity_catalog,reprice
from .economy.local_market import quote

def identity():return f"celestial:{config()['location_id']}:farm"
def estate(game):return estates(game).get(identity())
def lease(game):return (estate(game) or {}).get('operating_lease')
def root(game):return record(game).get('garden',{})

def begin(game):
    if blocked:=reason(game,True):raise ValueError(blocked)
    row=estate(game)
    if not row or not allowed(game,row) or not row['job']:raise ValueError('没有本人仙圃的在制批次')
    if row.get('building_status')=='destroyed':raise ValueError('须先修复损毁仙圃，再巡护原批次')
    return max(1,row['job']['finish']-game.player.age)

def finish(game,elapsed,unit):
    s=game.yaochi_state.setdefault('westward',{})
    count,s['settlement_years']=divmod(s.get('settlement_years',0)+elapsed,unit)
    return count

def reason(game,recovery=False):
    from .yaochi_westward import reason as local_reason
    return local_reason(game,cancelling=recovery)

def choices(game):
    row=estate(game) or dict(world='celestial',location=config()['location_id'],kind='farm')
    catalog=commodity_catalog('celestial')
    return {k:v for k,v in recipes('celestial',catalog).items() if v['kind']=='farm' and permits(row,v) and catalog[v['output']]['tier']<=game.player.realm_index+1}

def token(game):
    return digest([game.player.age,game.player.world,game.player.location_id,game.player.realm_index,
        game.yaochi_state.get('merit',0),estate(game),root(game),local_market(game).get('revision') if local_market(game) else None])

def repair_offer(game):
    from .building_assets import local_rows
    from .building_projects import quote
    row=next((r for r in local_rows(game) if r.get('source_id')==identity()),None)
    return (row,quote(game,'rebuild',row)) if row and row['status']=='destroyed' else (None,None)

def estate_call(game,maps,row,action,**kw):
    estate_command(game,maps,dict(action='estate_'+action,estate_id=row['id'],revision=row['revision'],**kw))

def order_close(game,row,delivered=False):
    order=row['operating_lease']['order']
    transfer_value(game,order['wallet'],YAOCHI,balance(game,order['wallet']),'仙圃供货余款退回瑶池')
    root(game).setdefault('receipts',[]).append(dict(order,delivered=delivered,closed=game.player.age))
    row['operating_lease'].pop('order')

def command(deps,game,action,target,amount):
    if type(amount) is not int or not 1<=amount<=10**12:raise ValueError('数量须为有效正整数')
    expected,_,value=target.partition('|')
    if expected!=token(game):raise ValueError('仙圃状态或报价已变化，请刷新')
    recovery=action in {'garden_close','garden_cancel_order','garden_release','garden_withdraw','garden_cash','garden_fund','garden_arrears','garden_work','garden_rebuild'}
    if blocked:=reason(game,recovery):raise ValueError(blocked)
    row=estate(game)
    if action=='garden_lease':
        if lease(game):raise ValueError('请先结清当前经营许可')
        if row and row['owner_kind'] not in {'background','yaochi'}:raise ValueError('原药田已有其他产权人，瑶池不能征用')
        if row and (row['stock'] or row['job'] or row['arrears'] or row.get('building_status')=='destroyed'):raise ValueError('原地块尚未完成交接或重建')
        priority=record(game).get('fair',{}).get('priority',{})
        discount=priority and not priority['used'] and game.player.age<priority['until']
        deposit=100 if discount else 200
        if game.yaochi_state.get('merit',0)<deposit or balance(game,'player')<5000:raise ValueError('须备足保证功勋与5000灵石租金')
        if not row or row['owner_kind']=='background':
            row=acquire(game,deps.maps,'celestial',config()['location_id'],'farm','yaochi','yaochi',YAOCHI,game.player.realm_index)
        s=game.yaochi_state.setdefault('westward',{}).setdefault('garden',{})
        serial=s.get('sequence',0)+1;s['sequence']=serial
        wallet=f'garden:{game.id}:{serial}';account(game,wallet)
        spend(game,deposit);transfer_value(game,'player',YAOCHI,5000,'仙圃二百五十年实际租金')
        row['operating_lease']=dict(operator=game.id,started=game.player.age,until=game.player.age+250,
            deposit=deposit,wallet=wallet,steward=None,wages=0)
        row.update(enabled=False,auto_buy=False,auto_sell=False,entrusted=False,last_year=game.player.age)
        row['revision']+=1
        if discount:priority['used']=True
        summary='取得二百五十年仙圃经营许可，产权仍归瑶池；请投入周转金并配置配方。'
    else:
        if not row or not allowed(game,row):raise ValueError('没有本人承办的原仙圃')
        l=row['operating_lease']
        if not recovery and (blocked:=production_reason(game,row)):raise ValueError(blocked)
        if action=='garden_work':
            begin(game);return deps.advance(game.id,'yaochi_garden',1)
        elif action=='garden_rebuild':
            building,bill=repair_offer(game)
            if not building:raise ValueError('原仙圃没有损毁')
            from .building_destruction import rebuild
            rebuild(game,building,None);summary='自费原址修复完成，原产权、批次、库存及合同保留。'
        elif action=='garden_fund':estate_call(game,deps.maps,row,'fund',amount=amount);summary='周转金已实付原仙圃账户。'
        elif action=='garden_cash':estate_call(game,deps.maps,row,'withdraw_cash',amount=amount);summary='已提取原经营现金。'
        elif action=='garden_arrears':estate_call(game,deps.maps,row,'pay_arrears');summary='原产业养护欠费已结清。'
        elif action=='garden_configure':
            if value not in choices(game):raise ValueError('请选择原地块允许的配方')
            estate_call(game,deps.maps,row,'configure',recipe=value,batches=amount,enabled=True,auto_buy=True,auto_sell=False,buy_limit=10**12,sell_limit=0,expense_limit=10**9,reserve_cash=10000)
            summary='已按原配方配置种植；自动经营仍检查市场需求、完整成本与养护储备。'
        elif action=='garden_start':estate_call(game,deps.maps,row,'start');summary='原料和劳务已实付，按原产业工期生产。'
        elif action=='garden_mode':
            if value not in {'retain','market'}:raise ValueError('请选择留存或市场销售')
            if l.get('order') or l.get('steward'):raise ValueError('请先交接定向订单或协作者再修改销售方案')
            row.update(enabled=True,auto_sell=value=='market');summary='已选择留存成品。' if value=='retain' else '成品按原市场报价、收购资金与销售限额出售，实际收入归经营账户。'
        elif action=='garden_withdraw':estate_call(game,deps.maps,row,'withdraw',item=value,quantity=amount);summary='原仓库实物已提入行囊。'
        elif action=='garden_steward':
            if l.get('order'):raise ValueError('请先交接定向供货，再安排自由合作经营')
            npc=next((n for n in people(game) if n.id==value and n.realm_index>=9),None)
            if not npc:raise ValueError('须选择当面、自由且未被占用的真仙人物')
            if l.get('steward'):raise ValueError('须先交接原协作者')
            l['steward']=npc.id;row.update(entrusted=True,enabled=True,auto_buy=True,auto_sell=True)
            summary='原协作者接任；每实际年100灵石，缺款或失联停止合作经营。'
        elif action=='garden_release':
            l['steward']=None;row.update(entrusted=False,enabled=False,auto_buy=False,auto_sell=False)
            summary='已交接合作经营，原人物解除占用；已付批次保留。'
        elif action=='garden_order':
            if l.get('steward'):raise ValueError('请先交接协作者，再亲自承办定向供货')
            if l.get('order'):raise ValueError('已有待交供货合同')
            if root(game).get('order_cycle')==game.player.age//50:raise ValueError('本期供货额度已用，五十年一期')
            recipe=choices(game).get(row['recipe'])
            if not recipe:raise ValueError('须先配置合法药田产物')
            item=recipe['output'];market=local_market(game);number=8
            total=quote(market['commodities'][item],'buy',number)['total']
            wallet=f'garden-order:{game.id}:{game.player.age//50}';account(game,wallet)
            transfer_value(game,YAOCHI,wallet,total,'瑶池有限供货合同实款托管')
            l['order']=dict(item=item,quantity=number,total=total,deadline=min(l['until'],game.player.age+50),wallet=wallet)
            root(game)['order_cycle']=game.player.age//50
            row.update(auto_sell=False,entrusted=False);summary='八件定向供货已签约并备款；关闭自动销售，成品留在原仓库。'
        elif action=='garden_deliver':
            o=l.get('order')
            if not o or game.player.age>o['deadline']:raise ValueError('没有有效供货合同，请先交接逾期合同')
            market=local_market(game);take(row,o['item'],o['quantity'])
            market['commodities'][o['item']]['stock']+=o['quantity'];reprice(game,market,market['commodities'][o['item']])
            transfer_value(game,o['wallet'],payer(row),o['total'],'瑶池收到仙圃原仓库实货后结款');row['income']+=o['total']
            order_close(game,row,True);summary='原库存实交，货款进入仙圃经营账户；不重复发整份劳务功勋。'
        elif action=='garden_cancel_order':
            if not l.get('order'):raise ValueError('没有待交合同')
            l['deposit']=max(0,l['deposit']-40);order_close(game,row);summary='未履约合同交接，扣除最多40保证功勋，未付货款退原府库。'
        elif action=='garden_close':
            if row['job'] or row['stock'] or row['arrears'] or l.get('order') or encumbered(game,row['id']):raise ValueError('请先结清在制、库存、欠费及供货合同')
            transfer_value(game,l['wallet'],'player',balance(game,l['wallet']),'仙圃交接提回剩余经营现金')
            game.yaochi_state['merit']+=l['deposit'];root(game)['last_lease']=copy.deepcopy(l)
            row.pop('operating_lease');row.update(enabled=False,auto_buy=False,auto_sell=False,entrusted=False)
            summary='原仙圃与账目交接完成，退回剩余保证功勋及经营现金，租金不退。'
        else:raise ValueError('未知仙圃事务')
        row['revision']+=1
    game.history.append(HistoryRecord('SYS_YAOCHI_GARDEN',1,game.player.age,'瑶池仙圃',action,'completed',summary,{},['yaochi','economy']))
    game.updated_at=now_iso();deps.store.save(game);return deps.present(game)

def public(game):
    if game.player.world!='celestial':return None
    local=game.player.location_id==config()['location_id'];r=estate(game) if local else None
    l=copy.deepcopy(r.get('operating_lease')) if r else None
    if l:
        if l.get('order'):l['order']['item_name']=ITEM_CATALOG[l['order']['item']].name
        steward=find_person(game,l.get('steward')) if l.get('steward') else None
        l['steward_name']=steward.name if steward else '原人物已失效'
    _,repair=repair_offer(game) if l else (None,None)
    return dict(enabled=enabled(),local=local,building_id='estate:'+identity() if local else '',token=token(game) if local else '',reason=reason(game),recovery_reason=reason(game,True),
        occupied=bool(r and r['owner_kind'] not in {'background','yaochi'}),lease=copy.deepcopy(l),repair=repair,
        estate=dict(id=r['id'],stock=[dict(id=k,name=ITEM_CATALOG[k].name,quantity=n) for k,n in r['stock'].items()],
            job=copy.deepcopy(r['job']),cash=balance(game,payer(r)),income=r['income'],expense=r['expense'],arrears=r['arrears'],recipe=r['recipe'],batches=r['batches'],auto_sell=r['auto_sell'],
            reason=production_reason(game,r),steward_reason=steward_reason(game,r) if l and l.get('steward') else '',
            history=copy.deepcopy(r['history'])) if r else None,
        recipes=[dict(id=k,name=v['name'],years=v['years'],quantity=v['quantity'],inputs='、'.join(f'{ITEM_CATALOG[i].name} ×{n}' for i,n in v['inputs'].items())) for k,v in choices(game).items()] if local else [],
        people=[dict(id=n.id,name=n.name) for n in people(game) if n.realm_index>=9] if local else [],
        receipts=copy.deepcopy(root(game).get('receipts',[])[-4:]) if local else [])

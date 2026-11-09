"""DLC supply terms and independent-cultivator contracts use base escrow logic."""
import copy
from .institution_ai import contracts
from .institution_ai.rules import digest
from .economy.ledger import balance
from .economy.state import local_market,reprice
from .economy.local_market import quote
from .economy.enterprise_state import take,payer
from .westward_rules import record,enabled
from .westward_finance import YAOCHI
from .yaochi_rules import require_market
from .yaochi_garden_state import estate,lease,choices
from .immortal_identity_rules import primary
from ..rules import remove_item
from ..content_registry import ITEM_CATALOG

def state(game):return record(game).get('contracts',{})
def current(game):return state(game).get('active')
def token(game):
    return digest([state(game),game.player.age,game.player.world,game.player.location_id,primary(game),estate(game),
        [(i.id,i.quantity) for i in game.player.inventory],balance(game,YAOCHI),local_market(game)])

def offers(game):
    market=local_market(game)
    if not enabled() or not market:return []
    l=lease(game);r=estate(game);rows=[]
    if l and l['operator']==game.id and not l.get('order') and not l.get('steward') and l['until']>=game.player.age+150:
        recipe=choices(game).get(r['recipe'])
        if recipe:
            from .westward_fair_benefits import credential
            prize=credential(game,'supply')
            item=recipe['output'];rows.append(dict(id='garden',name='仙圃三期供货',item=item,quantity=12 if prize else 8,fair_credential=prize['id'] if prize else None,interval=50,periods=3,deadline=min(l['until'],game.player.age+200),source='estate',estate=r['id']))
    if primary(game)=='free':
        candidates=[(k,p) for k,p in market['commodities'].items() if k in ITEM_CATALOG and 9<=p['tier']<=game.player.realm_index+1 and p['stock']<p['target']*.6]
        if candidates:
            item,_=min(candidates,key=lambda kv:(kv[1]['stock']/max(1,kv[1]['target']),kv[0]))
            rows.append(dict(id='free',name='散仙独立补缺契约',item=item,quantity=4,interval=10,periods=1,deadline=game.player.age+100,source='inventory'))
    for row in rows:
        row['item_name']=ITEM_CATALOG[row['item']].name
        row['price']=quote(market['commodities'][row['item']],'buy',row['quantity'])['total']
        row['reason']='瑶池原采购款不足' if balance(game,YAOCHI)<row['price']*row['periods'] else ''
        if state(game).get('last_cycle')==game.player.age//50:row['reason']='本期供货额度已用，取消不刷新'
    return rows

def command(game,action,value):
    require_market(game)
    expected,_,choice=value.partition('|')
    if expected!=token(game):raise ValueError('供货契约或原报价变化，请刷新')
    s=game.yaochi_state.setdefault('westward',{}).setdefault('contracts',{})
    row=current(game)
    if action=='contract_open':
        from .earth_temple_rules import reason
        if blocked:=reason(game):raise ValueError(blocked)
        if row:raise ValueError('须先结清或交接原合同')
        if s.get('last_cycle')==game.player.age//50:raise ValueError('本期独立或长期供货额度已用，取消不刷新')
        offer=next((o for o in offers(game) if o['id']==choice),None)
        if not offer or offer['reason']:raise ValueError(offer['reason'] if offer else '原供货条件已失效')
        serial=s.get('sequence',0)+1
        row=contracts.reserve(game,'westward-'+str(serial),YAOCHI,'celestial',game.player.location_id,offer['item'],offer['quantity'],offer['price'],offer['periods'],offer['interval'],offer['deadline'])
        row.update(source_kind=offer['source'],estate=offer.get('estate'),name=offer['name'])
        s.update(active=row,sequence=serial,last_cycle=game.player.age//50)
        if offer.get('fair_credential'):
            from .westward_fair_benefits import consume
            consume(game,offer['fair_credential'],'长期供货扩额')
        if offer['source']=='estate':estate(game).update(auto_sell=False,entrusted=False)
    elif not row:raise ValueError('没有原供货契约')
    elif action=='contract_deliver':
        if not enabled():raise ValueError('停用后请交接未完成合同')
        from .earth_temple_rules import reason
        if blocked:=reason(game):raise ValueError(blocked)
        market=local_market(game);product=market['commodities'].get(row['item'])
        if not product:raise ValueError('原交付商品已失效')
        if row['source_kind']=='estate':
            r=estate(game);l=lease(game)
            if not r or r['id']!=row['estate'] or not l or l['operator']!=game.id or game.player.age>=l['until']:raise ValueError('原仙圃经营许可失效')
            if r.get('building_status')=='destroyed':raise ValueError('原仙圃损毁，须先原址修复')
            available=r['stock'].get(row['item'],0);destination=payer(r)
            consume=lambda n:take(r,row['item'],n)
        else:
            available=sum(i.quantity for i in game.player.inventory if i.id==row['item']);destination='player'
            consume=lambda n:remove_item(game.player,row['item'],n)
        def receive(n):product['stock']+=n;reprice(game,market,product)
        contracts.deliver(game,row,destination,available,consume,receive)
        if row['source_kind']=='estate':estate(game)['income']+=row['price']
        if row['status']=='completed':
            s['history']=(s.get('history',[])+[copy.deepcopy(row)])[-12:];s.pop('active')
    elif action=='contract_cancel':
        contracts.cancel(game,row);s['history']=(s.get('history',[])+[copy.deepcopy(row)])[-12:];s.pop('active')
    else:raise ValueError('未知供货契约操作')

def public(game):
    if game.player.world!='celestial':return None
    from .yaochi_rules import config
    if game.player.location_id!=config()['location_id']:return None
    row=current(game);blocked=''
    if row:
        from .earth_temple_rules import reason
        blocked=reason(game) or ('扩展停用，请交接余款' if not enabled() else '')
        if not blocked and not row['next']<=game.player.age<=row['deadline']:blocked='尚未到交货期或合同已逾期'
        if row['source_kind']=='estate':
            r=estate(game);l=lease(game)
            if not blocked and (not r or not l or l['operator']!=game.id or game.player.age>=l['until'] or r.get('building_status')=='destroyed'):blocked='原仙圃许可或设施不可用'
            available=(r or {}).get('stock',{}).get(row['item'],0)
        else:available=sum(i.quantity for i in game.player.inventory if i.id==row['item'])
        if not blocked and available<row['quantity']:blocked='原实货不足'
    return dict(token=token(game),offers=offers(game),active=copy.deepcopy(row),delivery_reason=blocked,history=copy.deepcopy(state(game).get('history',[])[-4:]))

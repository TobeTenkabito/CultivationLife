"""Personal merit purchases part of an original repair, never withdrawable cash."""
from ..building_schema import address
from ..content_registry import ITEM_CATALOG
from ..models import HistoryRecord
from ..rules import remove_item
from ..runtime import now_iso
from .building_assets import local_rows
from .building_projects import owns,quote
from .building_destruction import rebuild
from .court_bureau_rules import digest
from .earth_temple_rules import reason as actor_reason
from .westward_rules import enabled,merit_balance
from .westward_finance import budget,reserve
from .economy.ledger import balance,transfer_value

def offers(game):
    if actor_reason(game):return []
    rows=[];b=budget(game);held={i.id:i.quantity for i in game.player.inventory}
    for row in local_rows(game):
        if row['status']!='destroyed' or not owns(game,row) or row.get('subtype')=='temple':continue
        bill=quote(game,'rebuild',row)
        # Existing 40 merit / court-merit and 250 stones / merit, same finite window.
        units=min(bill['coins']//10000,merit_balance(game),b['remaining']//10000,b['funding']//10000)
        subsidy=max(0,units)*10000;personal=bill['coins']-subsidy
        blocked=bill['reason'] if bill['reason']!='灵石或筑城材料不足' else ''
        blocked=blocked or ('请先确认功德账本' if 'merit_account' not in game.heavenly_court else '')
        blocked=blocked or ('原承兑预算或可用功德不足以支付一份修缮服务' if not subsidy else '')
        blocked=blocked or ('本人补款或原工程材料不足' if balance(game,'player')<personal or any(held.get(k,0)<n for k,n in bill['materials'].items()) else '')
        r=dict(id=row['id'],name=row['name'],coins=bill['coins'],personal=personal,subsidy=subsidy,merit=units,
            materials=bill['materials'],reason=blocked,building_token=bill['token'],
            recipe=[dict(name=ITEM_CATALOG[k].name,needed=n,held=held.get(k,0)) for k,n in bill['materials'].items()])
        r['token']=digest([r,game.player.age,address(game),b,merit_balance(game)]);rows.append(r)
    return rows

def command(deps,game,action,target,amount):
    if action!='relief_rebuild' or type(amount) is not int or amount!=1:raise ValueError('请选择一处原址修缮')
    if blocked:=actor_reason(game):raise ValueError(blocked)
    offer=next((r for r in offers(game) if r['token']==target),None)
    if not offer:raise ValueError('原建筑或功德承兑报价已变化，请刷新')
    if offer['reason']:raise ValueError(offer['reason'])
    row=next(r for r in local_rows(game) if r['id']==offer['id'])
    # No public policy budget is paid to a private beneficiary: this consumes personal
    # merit within the SAME limited public service procurement window as cultivation.
    order=dict(id='repair:'+game.id+':'+offer['token'])
    reserve(game,order,offer['subsidy']//250,'court')
    transfer_value(game,'player',order['escrow'],offer['personal'],'功德修缮本人实付差额')
    stock={}
    for key,n in offer['materials'].items():
        if not remove_item(game.player,key,n):raise ValueError('原工程材料已变化')
        stock[key]=n
    rebuild(game,row,None,payer=order['escrow'],stock=stock)
    if stock or balance(game,order['escrow']):raise ValueError('原修缮账目未平，拒绝结项')
    del game.economy_v2['accounts'][order['escrow']]
    summary=f"原址重建{row['name']}：消费{offer['merit']}可用功德，承兑{offer['subsidy']}灵石，本人补款{offer['personal']}灵石。原工程完整收款，材料实际消耗，官品资历不减少。"
    game.history.append(HistoryRecord('SYS_IMMORTAL_RELIEF',1,game.player.age,'功德修缮',row['id'],'completed',summary,
        dict(building_id=row['id'],merit=offer['merit'],subsidy=offer['subsidy'],personal=offer['personal']),['yaochi','building']))
    game.updated_at=now_iso();deps.store.save(game);return deps.present(game)

def public(game):
    if not enabled() or game.player.world!='celestial' or game.guixu_state.get('player_session'):return None
    return dict(reason=actor_reason(game),offers=offers(game),budget=budget(game),merit=merit_balance(game))

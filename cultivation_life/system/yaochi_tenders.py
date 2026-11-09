"""Actual institutional bidders for the one original farm, using base contract evaluation."""
import copy
from .institution_ai.contracts import rank
from .institution_ai.rules import person_reason
from .economy.ledger import account,balance,transfer_value
from .economy.enterprise_rules import recipes
from .economy.enterprise_costs import production_cost,annual_maintenance
from .economy.resource_access import permits
from .economy.state import commodity_catalog,local_market
from .economy.enterprise_acquisition import acquire
from .westward_rules import record,enabled
from .westward_finance import YAOCHI
from .yaochi_rules import config
from ..relationship_records import find_person

def state(game):return record(game).get('garden',{}).get('tender',{})

def bids(game,rent=5000):
    from .yaochi_garden_state import estate
    place=config()['location_id'];r=estate(game)
    if not enabled() or game.player.world!='celestial' or game.player.location_id!=place or r and r.get('operating_lease'):return []
    market=local_market(game)
    if not market:return []
    history=record(game).get('garden',{}).get('receipts',[])
    reputation=min(40,20+4*sum(bool(h.get('delivered')) for h in history)-4*sum(not h.get('delivered') for h in history))
    entries=record(game).get('fair',{}).get('entries',[])
    if any(e['kind']=='supply' and e['status']=='won' and game.player.age<(e['cycle']+2)*500 for e in entries):reputation=min(40,reputation+12)
    results=[dict(id='player',name=game.player.name,price=rent,reference=10000,reliability=reputation,ability=min(20,game.player.realm_index),
        available=balance(game,'player'),required=rent,payer='player')]
    for key,org in game.economy_v2.get('organizations',{}).items():
        if org['kind'] not in {'sect','family'} or org['world']!='celestial':continue
        entity=game.family if org['kind']=='family' else game.sects.get(org['identity'])
        if not entity or entity.extinct:continue
        eligible=[n for n in entity.npcs if n.realm_index>=9 and not person_reason(game,n.id,'celestial',place)]
        if not eligible:continue
        n=max(eligible,key=lambda n:(n.realm_index,n.layer,n.id))
        options=[(k,p) for k,p in recipes('celestial',commodity_catalog('celestial')).items() if p['kind']=='farm'
            and permits(r or dict(world='celestial',location=place,kind='farm'),p) and market['commodities'].get(p['output'],{}).get('tier',99)<=n.realm_index+1]
        if not options:continue
        recipe,definition=min(options,key=lambda kv:(market['commodities'][kv[1]['output']]['reference'],kv[0]))
        if not r:
            # Exact carrying estimate requires the original acquired estate. Bidders wait until it exists.
            continue
        capital=production_cost(r,market,definition)+annual_maintenance(r,market)*250+25000
        reserve=int(org.get('expected_upkeep',0)*3);available=max(0,balance(game,key)-reserve)
        results.append(dict(id=n.id,name=n.name+' · '+entity.name,price=5000,reference=10000,reliability=20,ability=min(20,n.realm_index),
            available=available,required=5000+50000+capital,payer=key,recipe=recipe,capital=capital))
    return rank(results)

def award(game,maps,rent,ranked=None):
    from .yaochi_garden_state import estate
    ranked=bids(game,rent) if ranked is None else ranked
    if not ranked or not any(b['id']=='player' for b in ranked):raise ValueError('本人竞租款不足')
    winner=ranked[0]
    garden=game.yaochi_state.setdefault('westward',{}).setdefault('garden',{})
    garden['tender']=dict(age=game.player.age,until=game.player.age+250,winner=winner['id'],name=winner['name'],rent=winner['price'],
        bids=[{k:b[k] for k in ('id','name','price','score')} for b in ranked])
    if winner['id']=='player':return False
    row=estate(game)
    if not row or row['owner_kind']!='yaochi' or row['stock'] or row['job'] or row['arrears'] or row.get('building_status')=='destroyed':raise ValueError('原仙圃尚未完成产权与经营交接')
    serial=garden.get('sequence',0)+1;wallet=f'garden:{game.id}:{serial}';deposit=wallet+':deposit'
    account(game,wallet);account(game,deposit)
    transfer_value(game,winner['payer'],YAOCHI,winner['price'],'原机构竞得仙圃实际租金')
    transfer_value(game,winner['payer'],deposit,50000,'NPC承办原机构现金保证金')
    transfer_value(game,winner['payer'],wallet,winner['capital'],'原机构注入原仙圃唯一经营账户')
    garden['sequence']=serial
    row['operating_lease']=dict(operator=winner['id'],operator_kind='npc',source=winner['payer'],deposit_wallet=deposit,
        started=game.player.age,until=game.player.age+250,deposit=0,wallet=wallet,steward=winner['id'],wages=0)
    row.update(recipe=winner['recipe'],batches=1,enabled=True,auto_buy=True,auto_sell=True,entrusted=True,
        buy_limit=10**12,sell_limit=0,expense_limit=winner['capital'],reserve_cash=10000,last_year=game.player.age,revision=row['revision']+1)
    return True

def advance(game,maps):
    from .yaochi_garden_state import estate
    from ..regional_context import region,ordinary_year
    if (region(game) or game.player.world)!='celestial' or not ordinary_year(game):return
    row=estate(game);lease=(row or {}).get('operating_lease')
    if not row:return
    if not lease:
        # The owner liquidates handed-back goods from the same estate, never a copied stock.
        if row['owner_kind']=='yaochi' and not row['job'] and row.get('building_status')!='destroyed':
            from .economy.enterprise_operations import market_trade
            market=game.economy_v2['markets'].get('celestial:'+row['location'])
            for item,n in list(row['stock'].items()):
                try:market_trade(game,row,market,item,n,'sell')
                except ValueError:break
        return
    if lease.get('operator_kind')!='npc':return
    from .economy.operating_license import npc_allowed
    if enabled() and game.player.age<lease['until'] and npc_allowed(game,row) and row.get('building_status')!='destroyed':return
    row.update(enabled=False,auto_buy=False,entrusted=False,auto_sell=False)
    # Paid batches and stock belong to this original owner's estate. Hand back the permit,
    # not the assets; missing operators and ruined batches must not imprison an NPC forever.
    for wallet in (lease['wallet'],lease['deposit_wallet']):
        paid=min(row['arrears'],balance(game,wallet))
        transfer_value(game,wallet,'background:celestial',paid,'原NPC经营交接清偿欠费')
        row['arrears']-=paid;row['expense']+=paid
    transfer_value(game,lease['wallet'],lease['source'],balance(game,lease['wallet']),'NPC承办剩余经营款归原机构')
    transfer_value(game,lease['deposit_wallet'],lease['source'],balance(game,lease['deposit_wallet']),'NPC承办保证金退原机构')
    record(game)['garden']['last_npc_lease']=copy.deepcopy(lease);row.pop('operating_lease');row['revision']+=1

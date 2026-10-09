"""Member supplies: realm buckets use the existing depot, then real purchases."""
from .basket_rules import purpose_candidates, purpose, REALM_WEIGHTS
from .demand_profiles import rates
from .basket_trade import purchase
from .ledger import balance
from .depot import ensure, treasury, record
from ...content_registry import REALMS
from ...npc_custody import is_free

def consume(game, market, entity, finance, years, budget):
    stock = ensure(game, entity)
    source = treasury(game, entity)
    credits = finance.setdefault('demand_credit', {})
    due = fulfilled = spent = consumed = 0
    growth={};maintenance={};breakthrough={};longevity={}
    # Sparse existing holdings are grouped once, before demand settlement.
    # Approved requests were already removed from this authoritative stock.
    held={}
    for key,number in stock['stock'].items():
        item=key.removeprefix('item:')
        use=purpose(item)
        if not number or not key.startswith('item:') or not use or item not in market['commodities']:continue
        group=f'{use}:{market["commodities"][item]["tier"]}'
        held.setdefault(group,[]).append(item)
    for rank, count in finance.get('workforce', {}).items():
        growth_due=growth_paid=repair_due=repair_paid=0
        for category, rate in sorted(rates(int(rank)).items(),key=lambda pair:-pair[1]):
            if not rate:continue
            group = f'{category}:{max(1, int(rank))}'
            items = purpose_candidates(market, group, rotation=game.player.age//20)
            items=tuple(dict.fromkeys([*held.get(group,[])[:2],*items]))
            if not items:
                continue
            demand = round(credits.get(group,0.)+count*REALM_WEIGHTS[int(rank)]*rate*years,9)
            wanted = min(1000000, int(demand))
            credits[group] = demand-int(demand)
            due += wanted
            left = wanted
            for item in items:
                key = 'item:'+item
                used = min(left, stock['stock'].get(key, 0))
                stock['stock'][key] = stock['stock'].get(key, 0)-used
                left -= used; consumed += used
                if left:
                    number, cost = purchase(game, market, source, item, left,
                        min(max(0, budget-spent), balance(game, source)), '成员供养采购并实际消耗')
                    spent += cost; left -= number; consumed += number
                if not left:
                    break
            fulfilled += wanted-left
            if category in {'cultivation','healing'}:
                growth_due+=wanted;growth_paid+=wanted-left
            if category in {'repair','energy','artifact'}:
                repair_due+=wanted;repair_paid+=wanted-left
            if category=='breakthrough':breakthrough[rank]=(wanted-left)/wanted if wanted else 0.
            if category=='longevity':longevity[rank]=min(5.*years,(wanted-left)*5/max(1,count))
        growth[rank]=growth_paid/growth_due if growth_due else 0.
        maintenance[rank]=repair_paid/repair_due if repair_due else 0.
    finance['supply_coverage'] = fulfilled/due if due else 1.
    finance['supplies_consumed'] = finance.get('supplies_consumed', 0)+consumed
    finance['supply_expense'] = spent
    finance['cultivation_support']=growth
    finance['maintenance_support']=maintenance
    finance['breakthrough_support']=breakthrough
    finance['longevity_support']=longevity
    finance['provision_year']=game.player.age
    if consumed:
        record(stock, game, f'成员境界组实际消耗 {consumed} 件，采购支出 {spent} 灵石')
    return spent


def support(game,kind,identity,rank,field='cultivation_support'):
    row=game.economy_v2.get('organizations',{}).get(f'organization:{kind}:{identity}',{})
    if row.get('last_year') != game.player.age:
        return 0.
    return row.get(field,{}).get(str(rank),0.)


def apply_longevity(game,npc,kind,identity):
    """Use the existing yearly lifecycle, not a per-person shopping pass."""
    if not is_free(npc) or npc.lifespan is None or not 1<=npc.realm_index<=5:return
    row=game.economy_v2.get('organizations',{}).get(f'organization:{kind}:{identity}',{})
    if row.get('world')!=npc.world or row.get('last_year')!=game.player.age:return
    if npc.economic_provision_year==game.player.age:return
    npc.economic_provision_year=game.player.age
    years=row.get('longevity_support',{}).get(str(npc.realm_index),0.)
    cap=REALMS[npc.realm_index].lifespan[1]*.10
    previous=npc.economic_lifespan_bonus
    total=max(previous,round(min(cap,previous+max(0.,years)),9))
    npc.lifespan+=int(total)-int(previous)
    npc.economic_lifespan_bonus=total

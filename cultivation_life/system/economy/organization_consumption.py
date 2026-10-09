"""Member supplies: realm buckets use the existing depot, then real purchases."""
from .basket_rules import candidates, REALM_WEIGHTS
from .basket_trade import purchase
from .ledger import balance
from .depot import ensure, treasury, record

RATES = dict(medical=.025, training=.04, material=.02, arms=.002, energy=.02, general=.01)


def consume(game, market, entity, finance, years, budget):
    stock = ensure(game, entity)
    source = treasury(game, entity)
    credits = finance.setdefault('demand_credit', {})
    due = fulfilled = spent = consumed = 0
    growth={};maintenance={}
    for rank, count in finance.get('workforce', {}).items():
        growth_due=growth_paid=repair_due=repair_paid=0
        for category, rate in RATES.items():
            group = f'{category}:{max(1, int(rank))}'
            items = candidates(market, group)
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
            if category in {'training','medical'}:
                growth_due+=wanted;growth_paid+=wanted-left
            if category in {'material','energy'}:
                repair_due+=wanted;repair_paid+=wanted-left
        growth[rank]=growth_paid/growth_due if growth_due else 0.
        maintenance[rank]=repair_paid/repair_due if repair_due else 0.
    finance['supply_coverage'] = fulfilled/due if due else 1.
    finance['supplies_consumed'] = finance.get('supplies_consumed', 0)+consumed
    finance['supply_expense'] = spent
    finance['cultivation_support']=growth
    finance['maintenance_support']=maintenance
    if consumed:
        record(stock, game, f'成员境界组实际消耗 {consumed} 件，采购支出 {spent} 灵石')
    return spent


def support(game,kind,identity,rank,field='cultivation_support'):
    row=game.economy_v2.get('organizations',{}).get(f'organization:{kind}:{identity}',{})
    if row.get('last_year') != game.player.age:
        return 0.
    return row.get(field,{}).get(str(rank),0.)

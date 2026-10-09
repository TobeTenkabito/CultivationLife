"""Paid workshops share actual raw inputs; extraction is explicitly classified."""
import math
from ...content_registry import ITEM_CATALOG
from ...economy_content import specification, inputs as native_inputs, material_id
from .basket_rules import kind, index, candidates, is_raw, raw_candidates
from .basket_trade import quote, affordable, purchase, reprice, _commit_purchase
from .ledger import balance, transfer_value


def recipe(market, item):
    definition = ITEM_CATALOG.get(item)
    if definition is None:
        return None
    tags = set(definition.tags)
    # Seeds/herbs/ordinary mineral supplies are the extraction stage. Puppet
    # cores and talisman paper are processed goods even when tagged material.
    if is_raw(item):
        return {}
    tier = market['commodities'][item]['tier']
    spec=specification(item)
    if spec:
        result=native_inputs(spec['world'],tier,spec['template'])
        return result if all(k in market['commodities'] for k in result) else None
    # Ordinary legacy goods join a small purpose recipe, never a search over
    # all possible combinations. Plot/instance recipes stay in their own systems.
    from .basket_rules import purpose
    use=purpose(item)
    template=dict(healing='healing',cultivation='cultivation',breakthrough='breakthrough',
                  artifact='artifact_attack',repair='repair',energy='energy',general='repair').get(use)
    world=market.get('world')
    if world and template:
        result=native_inputs(world,tier,template)
        if all(k in market['commodities'] for k in result):
            cost=sum(market['commodities'][k]['reference'] for k in result)
            price=market['commodities'][item]['reference']
            if cost <= price*.65:
                units=max(1,math.floor(price*.45/cost))
                return {k:units for k in result}
    raw = raw_candidates(market,tier)
    raw = [k for k in raw if k != item and is_raw(k)]
    if not raw:
        return None  # Catalog-only specials keep their initial stock/black-market fallback.
    material = min(raw, key=lambda k: market['commodities'][k]['reference'])
    units = max(1, math.ceil(market['commodities'][item]['reference'] * .45 / market['commodities'][material]['reference']))
    return {material:units}


def produce(game, market, owner, item, wanted, *, labor_credit=None, allow_loss=False):
    row = market['commodities'][item]
    if row.get('imported'):
        return 0, 0
    wanted = min(int(wanted), max(0, int(row['target']*1.5-row['stock'])))
    if labor_credit is not None:
        wanted = min(wanted, int(labor_credit / row['reference']))
    if wanted <= 0:
        return 0, 0
    inputs = recipe(market, item)
    if inputs is None:
        return 0, 0
    from .resource_access import public_allowance,record_extraction
    if not inputs:
        quota=public_allowance(game,market,item)
        if quota is not None:wanted=min(wanted,quota)
        if wanted<=0:return 0,0
    dealer = f'market:{market["id"]}'
    for key, units in inputs.items():
        wanted = min(wanted, int(market['commodities'][key]['stock']) // units, 1000000 // units)
    wanted = affordable(row, 'sell', wanted, balance(game, dealer))
    # Workers can reinvest only existing money; a dealer order does not grant
    # a free advance or use future profit to pay today's missing inputs.
    low, high = 0, wanted
    owner_funds = balance(game, owner)
    background_owner = owner == f'background:{market["world"]}'
    input_bills=None
    if background_owner and len(inputs) <= 1:
        # Internal labour has no wage/profit constraint. A single raw input
        # reduces to its exact affordable quantity, avoiding nested quote
        # searches and output-price calculations for each midpoint.
        if inputs:
            material, units = next(iter(inputs.items()))
            low = affordable(market['commodities'][material], 'buy', wanted*units, owner_funds) // units
        else:
            low = wanted
        high = low
    elif background_owner and wanted:
        input_bills={k:quote(market['commodities'][k],'buy',wanted*q) for k,q in inputs.items()}
        if sum(b['total'] for b in input_bills.values())<=owner_funds:
            low=high=wanted
        else:input_bills=None
    while low < high:
        n = (low+high+1)//2
        cost = sum(quote(market['commodities'][k], 'buy', n*q)['total'] for k,q in inputs.items())
        if background_owner:
            valid=cost<=owner_funds
        else:
            revenue=quote(row,'sell',n)['total']
            wage=math.ceil(revenue*.70) if not inputs else math.ceil(row['reference']*n*.12)
            valid=cost+(wage if inputs else 0)<=owner_funds and wage<=revenue and (allow_loss or revenue>=(cost+wage)*1.05)
        if valid: low=n
        else: high=n-1
    if not low:
        return 0, 0
    bill = quote(row, 'sell', low)
    expense = 0
    for key, units in inputs.items():
        input_bill=input_bills[key] if input_bills is not None else quote(market['commodities'][key],'buy',low*units)
        count, cost = _commit_purchase(game,market,owner,key,low*units,input_bill,'作坊采购并实际消耗原料')
        assert count == low*units
        market['input_consumed'] = market.get('input_consumed', 0)+count
        expense += cost
    wage = (math.ceil(bill['total']*.70) if not inputs else math.ceil(row['reference']*low*.12)) if owner != f'background:{market["world"]}' else 0
    transfer_value(game, dealer, owner, bill['total'], '完成本地真实生产订单')
    transfer_value(game, owner, f'background:{market["world"]}', wage, '组织实际生产劳务') if wage else None
    expense += wage
    if bill['fee']:transfer_value(game, dealer, f'operator:{market["id"]}', bill['fee'], '生产订单手续费')
    row['stock'] += low; row['volume'] += low
    if not inputs:record_extraction(game,market,item,low)
    market['turnover'] += bill['gross']; market['fees'] += bill['fee']
    reprice(game, market, row)
    return low, bill['total']-expense

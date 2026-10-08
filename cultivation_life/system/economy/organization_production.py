"""One realm histogram and a bounded local sales portfolio per organization."""
from collections import Counter
from ...npc_custody import is_free
from ...content_registry import WORLD_SYSTEMS
from ..faction_geography import faction_site
from .state import ensure_regional_market, commodity_catalog, reprice
from .local_market import quote
from .ledger import balance, transfer_value
from .industry import supplier_delivery


def workforce(entity):
    # A single tally, not a business simulation per NPC. Only 13 realm buckets
    # enter the economic calculation; births/deaths are already authoritative.
    return Counter(n.realm_index for n in entity.npcs if is_free(n) and n.world == entity.world)


def produce(game, maps, entity, row, *, years=1, extra=False):
    world, location = entity.world, faction_site(entity)['id']
    ensure_regional_market(game, maps, world, location)
    market = game.economy_v2['markets'][f'{world}:{location}']
    groups = workforce(entity)
    tier = WORLD_SYSTEMS['world_profiles'][world]['tier']
    row['expected_upkeep'] = sum(count*(25*tier+rank**2*12) for rank,count in groups.items())
    row['workforce'] = {str(k):v for k,v in sorted(groups.items())}
    row['workforce_year'] = game.player.age
    capacity = sum(count * (60 + 60 * rank ** 3) for rank,count in groups.items()) * 5 ** (tier-1)
    row['labor_capacity'] = capacity
    if not capacity:
        return 0
    capacity *= .25 if extra else 1
    capacity *= min(1000, game.economy_v2['worlds'][world]['scale'])
    capacity *= (1 + row.get('industry_level', 0) * .25) * row.get('industry_utilization', 1)
    native = commodity_catalog(world, commercial=False)
    # Demand and realm capability determine the portfolio, not repeated random
    # choices. Local cash/stock constrain every accepted dealer order.
    goods = [k for k,p in market['commodities'].items() if k in native and not p.get('imported')
             and p['tier'] <= max(groups)+1 and p['stock'] < p['target']*1.5]
    goods.sort(key=lambda k:(market['commodities'][k]['stock']/market['commodities'][k]['target'],
                             -market['commodities'][k]['tier'],k))
    credit = min(10**12, row.get('production_credit', 0) + capacity * years)
    earned = 0
    dealer = f'market:{market["id"]}'
    goods = [k for k in goods if market['commodities'][k]['reference'] <= credit
             and quote(market['commodities'][k],'sell',1)['gross'] <= balance(game,dealer)]
    for item in goods[:4]:
        product = market['commodities'][item]
        wanted = min(1000000, int(credit / product['reference']), max(0,int(product['target']*1.5-product['stock'])))
        dealer = f'market:{market["id"]}'
        low, high = 0, wanted
        while low < high:
            mid = (low+high+1)//2
            if quote(product,'sell',mid)['gross'] <= balance(game,dealer): low=mid
            else: high=mid-1
        if not low:
            continue
        bill = quote(product,'sell',low)
        source = f'organization:{row["kind"]}:{entity.id}'
        transfer_value(game,dealer,source,bill['total'],'门内分境界产能完成本地订单')
        transfer_value(game,dealer,f'operator:{market["id"]}',bill['fee'],'组织产出交易手续费')
        product['stock'] += low
        product['production'] += low / max(1,years)
        product['volume'] += low
        market['turnover'] += bill['gross'];market['fees'] += bill['fee']
        reprice(game,market,product)
        supplier_delivery(market,source,low,game=game,item=item)
        earned += bill['total'];credit -= low*product['reference']
        row['produced'] += low;row['commodity'] = item
    row['production_credit'] = max(0,credit)
    row['expected_upkeep'] = sum(count*(25*WORLD_SYSTEMS['world_profiles'][world]['tier']+rank**2*12) for rank,count in groups.items())
    return earned

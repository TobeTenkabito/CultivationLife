"""Paid industrial capacity, physical war supply, and observable supplier shares."""
from .ledger import balance, transfer_value
from .local_market import quote
from .state import ensure_regional_market, reprice


def participating_wars(game, identity, world):
    return [w for w in game.wars if w.get('kind') == 'sect' and w.get('world') == world
            and w.get('status') in {'active', 'peace_ready'}
            and identity in {w.get('attacker_id'), w.get('defender_id'),
                *(r['id'] for side in ('attacker', 'defender') for r in w.get('coalitions', {}).get(side, []))}]


def supplier_delivery(market, owner, quantity, *, game=None, item=None):
    suppliers = market.setdefault('suppliers', {})
    suppliers[owner] = suppliers.get(owner, 0.) + quantity
    if game is not None and item is not None:
        from .market_power import record_trade
        record_trade(game, market, item, owner, 'sell', quantity)


def settle_industry(game, maps, entity, row, years):
    from ..faction_geography import faction_site
    world, site = entity.world, faction_site(entity)['id']
    ensure_regional_market(game, maps, world, site)
    market = game.economy_v2['markets'][f'{world}:{site}']
    source = f'organization:{row["kind"]}:{entity.id}'
    wars = participating_wars(game, entity.id, world)
    level = row.get('industry_level', 0)
    due = round(100 * (level + 1) * years * sum(r['price'] / r['reference'] for r in market['commodities'].values()) / max(1, len(market['commodities']))) if level else 0
    paid = min(due, balance(game, source))
    transfer_value(game, source, f'background:{world}', paid, '组织产业原料与设备养护')
    row['expense'] += paid
    row['industry_utilization'] = paid / due if due else 1.
    row['war_funding'] = 1.
    if not wars:
        return
    desired = min(1000000, max(1, len(entity.npcs) * years))
    goods = sorted(market['commodities'], key=lambda k: (market['commodities'][k]['tier'], k))
    bought = 0
    for item in goods[:3]:
        product = market['commodities'][item]
        low, high = 0, min(desired - bought, int(product['stock']))
        while low < high:
            mid = (low + high + 1) // 2
            if quote(product, 'buy', mid)['total'] <= balance(game, source):
                low = mid
            else:
                high = mid - 1
        if not low:
            continue
        bill = quote(product, 'buy', low)
        transfer_value(game, source, f'market:{market["id"]}', bill['total'], '参战组织采购军需并消耗')
        transfer_value(game, f'market:{market["id"]}', f'operator:{market["id"]}', bill['fee'], '军需采购手续费')
        product['stock'] -= low
        from .market_power import record_trade
        record_trade(game, market, item, source, 'buy', low)
        product['consumption'] += low / max(1, years)
        product['volume'] += low
        market['turnover'] += bill['gross']
        market['fees'] += bill['fee']
        reprice(game, market, product)
        row['expense'] += bill['total']
        bought += low
        if bought >= desired:
            break
    row['war_funding'] = bought / desired
    row['military_consumed'] = row.get('military_consumed', 0) + bought
    row['industry_utilization'] *= .6


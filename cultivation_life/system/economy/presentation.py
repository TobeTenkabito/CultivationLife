"""Read-only, world-local projections; no hidden remote market data."""
from ...content_registry import ITEM_CATALOG, WORLD_SYSTEMS, restricted_acquisition
from .state import local_market, settings
from .ledger import balance
from .local_market import quote, trade_available


def public_economy(game):
    market = local_market(game)
    if not market or game.player.world in {'lost', 'rift'}:
        return {'available': False}
    world = game.economy_v2['worlds'][game.player.world]
    rows = []
    holdings = {i.id: i.quantity for i in game.player.inventory}
    for item, row in market['commodities'].items():
        if item not in ITEM_CATALOG or restricted_acquisition('item', item):
            continue
        if row['tier'] > game.player.realm_index + 1 and not holdings.get(item):
            continue
        ratio = row['stock'] / row['target']
        prices = {str(q): {side: quote(row, side, q) for side in ('buy', 'sell')} for q in (1, 10, 100)}
        previous = row['history'][-1][1] if row['history'] else row['reference']
        rows.append(dict(id=item, name=ITEM_CATALOG[item].name, stock=int(row['stock']),
            held=holdings.get(item, 0), can_buy=row['tier'] <= game.player.realm_index + 1,
            price=round(row['price'], 2), quotes=prices,
            status='紧缺' if ratio < .6 else '充足' if ratio > 1.3 else '正常',
            trend='↑' if row['price'] > previous * 1.01 else '↓' if row['price'] < previous * .99 else '→',
            production=round(row['production'], 1), consumption=round(row['consumption'], 1),
            volume=row['volume'], history=list(row['history'])))
    return dict(available=True, market_id=market['id'], revision=market['revision'], name=market['name'],
        world_name=WORLD_SYSTEMS['world_names'][game.player.world], year=game.player.age,
        scale=round(world['scale'], 4), growth_cap=settings()['growth_cap'],
        price_level=world['price_level'], fee_rate=settings()['transaction_fee'],
        liquidity=balance(game, f'market:{market["id"]}'),
        operator_balance=balance(game, f'operator:{market["id"]}'),
        world_treasury=balance(game, f'world:{game.player.world}'),
        turnover=market['turnover'], fees=market['fees'], rows=rows,
        can_trade=trade_available(game))

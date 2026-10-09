"""Six bounded baskets, actual household payments, no elapsed-year/item loops."""
from .basket_rules import index, candidates, RATES
from .basket_trade import purchase
from .basket_production import produce
from .ledger import balance
from ...content_registry import MARKET_SETTINGS


def settle(game, market, years):
    groups = index(market)
    source = f'background:{market["world"]}'
    # A fixed two-item basket per category/grade. Rotating between catalog
    # entries is a policy change and is deliberately not replayed for skipped years.
    rotation = 0
    purchases = production = expense = 0
    rate = MARKET_SETTINGS['economy_v2']['annual_consumption'] / .08
    for group in sorted(groups):
        category = group.split(':')[0]
        for item in candidates(market, group, rotation=rotation):
            row = market['commodities'][item]
            population = min(3., game.economy_v2['worlds'][market['world']]['scale'] ** .15)
            demand = row['initial_target'] * RATES[category] * population * years * rate
            fraction = round(row.get('demand_credit', 0.)+demand,9)
            wanted = min(1000000, int(fraction))
            row['demand_credit'] = fraction-int(fraction)
            made, _ = produce(game, market, source, item, min(wanted, row['initial_target']*.10*years))
            production += made
            quantity, paid = purchase(game, market, source, item, wanted, balance(game, source), '居民实际购买并消费')
            purchases += quantity; expense += paid
            row.update(production=made/max(1, years), consumption=quantity/max(1, years))
            row['history'].append([game.player.age, round(row['price'],2)])
            del row['history'][:-12]
    market['household_spending'] = market.get('household_spending',0)+expense
    market['terminal_consumed'] = market.get('terminal_consumed',0)+purchases
    market['actual_produced'] = market.get('actual_produced',0)+production
    return expense

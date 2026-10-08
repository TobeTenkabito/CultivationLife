"""Shared fixed-site market adoption for production and deed valuation."""
from .state import ensure_regional_market, commodity_catalog


def market_at(game, maps, row):
    ensure_regional_market(game, maps, row['world'], row['location'])
    market = game.economy_v2['markets'][f'{row["world"]}:{row["location"]}']
    # Added commercial materials start empty in an already existing market.
    for item, definition in commodity_catalog(row['world']).items():
        if item not in market['commodities']:
            market['commodities'][item] = dict(stock=0., target=120., price=float(definition['base_price']),
                reference=definition['base_price'], tier=definition['tier'], initial_target=120.,
                production=0., consumption=0., volume=0, history=[], imported=True)
            market['revision'] += 1
    return market


"""Shared fixed-site market adoption for production and deed valuation."""
from .state import ensure_regional_market, commodity_catalog
from collections import OrderedDict

_COMPLETE=OrderedDict()


def market_at(game, maps, row):
    ensure_regional_market(game, maps, row['world'], row['location'])
    market = game.economy_v2['markets'][f'{row["world"]}:{row["location"]}']
    catalog=commodity_catalog(row['world'])
    cache=_COMPLETE.get(id(market))
    if cache and cache[0] is market and cache[1] is catalog and cache[2]==len(market['commodities']):
        _COMPLETE.move_to_end(id(market))
        return market
    # Added commercial materials start empty in an already existing market.
    for item, definition in catalog.items():
        if item not in market['commodities']:
            market['commodities'][item] = dict(stock=0., target=120., price=float(definition['base_price']),
                reference=definition['base_price'], tier=definition['tier'], initial_target=120.,
                production=0., consumption=0., volume=0, history=[], imported=True)
            market['revision'] += 1
    _COMPLETE[id(market)]=(market,catalog,len(market['commodities']))
    while len(_COMPLETE)>64:_COMPLETE.popitem(last=False)
    return market


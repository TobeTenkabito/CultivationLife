"""World economy and persistent local inventories, with lazy regional settlement."""
import hashlib
import math

from ...content_registry import ITEM_CATALOG, MARKET_GOODS, MARKET_SETTINGS, WORLD_SYSTEMS, restricted_acquisition
from .pricing import growth, price_multiplier
from .ledger import account, transfer_value


def settings():
    return MARKET_SETTINGS['economy_v2']


def market_id(world, location):
    return f'{world}:{location}'


def local_market(game):
    return game.economy_v2.get('markets', {}).get(market_id(game.player.world, game.player.location_id))


def ensure_state(game):
    if game.economy_v2:
        return False
    from ...economy_schema import validate_economy_settings
    validate_economy_settings(settings())
    game.economy_v2 = dict(schema_version=1, base_year=game.player.age, last_year=game.player.age,
                           worlds={}, markets={}, accounts={}, ledger=[])
    for world, profile in WORLD_SYSTEMS['world_profiles'].items():
        if int(profile['tier']) <= 0:
            continue
        game.economy_v2['worlds'][world] = dict(scale=1., price_level=1., money_supply_index=1.,
            last_year=game.player.age, history=[], black_market_volume=0, black_market_quantity=0)
        account(game, f'background:{world}', settings()['background_opening'] * int(profile['tier']))
        account(game, f'world:{world}')
    return True


def advance_economy(game):
    """One world clock, also used in isolated spaces; no travel or RNG effects."""
    ensure_state(game)
    state = game.economy_v2
    years = game.player.age - state['last_year']
    if years <= 0:
        return False
    for world, row in state['worlds'].items():
        previous = row['scale']
        row['scale'] = growth(previous, years, settings()['growth_rate'], settings()['growth_cap'])
        row['money_supply_index'] = row['scale']
        row['last_year'] = game.player.age
        # Explicit macro issue, proportional to actual expansion, not flat annual gifts.
        pool = account(game, f'background:{world}')
        amount = int(settings()['background_opening'] * (row['scale'] - previous))
        pool['balance'] += amount
        state.setdefault('issued', 0)
        state['issued'] += amount
        row['history'].append([game.player.age, round(row['scale'], 6)])
        del row['history'][:-24]
    state['last_year'] = game.player.age
    market = local_market(game)
    if market:
        settle_market(game, market)
    return True


def commodity_catalog(world=None):
    result = {}
    for good in MARKET_GOODS:
        key = good['content_id']
        if ((world is not None and good.get('world', 'human') != world) or good['kind'] != 'item' or key == 'spirit_stone'
                or key not in ITEM_CATALOG or restricted_acquisition('item', key)):
            continue
        result[key] = dict(id=key, name=ITEM_CATALOG[key].name, base_price=int(good['price']),
                           tier=int(good['tier']))
    from ...puppet_content import definitions
    from ...talisman_content import catalog
    for definition in [*definitions().values(), *catalog()[0].values()]:
        key = definition['id']
        if (world is None or definition['world'] == world) and key in ITEM_CATALOG:
            result[key] = dict(id=key, name=definition['name'],
                base_price=int(definition.get('base_value', definition.get('price'))), tier=int(definition['tier']))
    return result


def _variation(world, location, item):
    value = int.from_bytes(hashlib.blake2b(f'{world}:{location}:{item}'.encode(), digest_size=4).digest(), 'big')
    return .75 + (value % 501) / 1000


def ensure_regional_market(game, maps, world, location):
    """Create/settle one real address without borrowing the player's address."""
    changed = ensure_state(game)
    if world not in game.economy_v2['worlds']:
        return changed
    # Validate the actual address; never turn an unknown world into human.
    maps.location(world, location)
    key = market_id(world, location)
    if key not in game.economy_v2['markets']:
        scale = game.economy_v2['worlds'][world]['scale']
        commodities = {}
        for item, definition in commodity_catalog(world).items():
            target = settings()['base_stock'] * _variation(world, location, item) * scale
            commodities[item] = dict(stock=target, target=target, price=float(definition['base_price']),
                reference=definition['base_price'], tier=definition['tier'],
                production=target * settings()['annual_consumption'], consumption=target * settings()['annual_consumption'],
                volume=0, history=[], initial_target=target / scale)
        game.economy_v2['markets'][key] = dict(id=key, world=world, location=location,
            name=maps.location(world, location)['name'], last_year=game.player.age,
            revision=0, commodities=commodities, turnover=0, fees=0, unique_sales=0)
        account(game, f'market:{key}')
        opening = min(settings()['market_opening'], account(game, f'background:{world}')['balance'])
        transfer_value(game, f'background:{world}', f'market:{key}', opening, '市场开业周转金')
        account(game, f'operator:{key}')
        changed = True
    return settle_market(game, game.economy_v2['markets'][key]) or changed


def ensure_market(game, maps):
    world, location = game.player.world, game.player.location_id
    changed = ensure_regional_market(game, maps, world, location)
    if world not in game.economy_v2['worlds']:
        return changed
    key = market_id(world, location)
    market = game.economy_v2['markets'][key]
    missing = [item.id for item in game.player.inventory if item.quantity > 0
               and item.id != 'spirit_stone' and item.id not in market['commodities']]
    if missing:
        catalog = commodity_catalog()
        for item in missing:
            definition = catalog.get(item)
            if not definition:
                continue
            target = settings()['base_stock'] * .25
            reference = max(1, round(definition['base_price'] * _variation(world, location, item)))
            market['commodities'][item] = dict(stock=0., target=target, price=reference * price_multiplier(0,target),
                reference=reference, tier=definition['tier'], production=0., consumption=0.,
                volume=0, history=[], initial_target=target, imported=True)
            market['revision'] += 1
            changed = True
    return settle_market(game, market) or changed


def settle_market(game, market):
    """Analytical local production/consumption; never transfers goods between towns.

    Background workshops replace consumed stock and respond gradually to shortages.
    A return after centuries costs O(commodities), not O(years * commodities).
    """
    years = game.player.age - market['last_year']
    if years <= 0:
        return False
    world = game.economy_v2['worlds'][market['world']]
    for item, row in market['commodities'].items():
        old_stock = row['stock']
        target = row['initial_target'] * world['scale']
        # Stable local specialisation creates supply differences; no goods teleport.
        supply = target * (.4 + (_variation(market['world'], market['location'], item) - .75) * 3.2)
        new_stock = supply + (old_stock - supply) * math.exp(-settings()['recovery_rate'] * years)
        consumed = target * settings()['annual_consumption'] * years + max(0., old_stock - new_stock)
        produced = consumed + new_stock - old_stock
        if row.get('imported'):
            new_stock = old_stock * math.exp(-settings()['annual_consumption'] * years)
            produced, consumed = 0., old_stock - new_stock
        row.update(stock=max(0., new_stock), target=target,
                   production=max(0., produced) / years, consumption=max(0., consumed) / years)
        target_price = row['reference'] * world['price_level'] * price_multiplier(row['stock'], target)
        row['price'] = target_price + (row['price'] - target_price) * math.exp(-.5 * years)
        row['history'].append([game.player.age, round(row['price'], 2)])
        del row['history'][:-12]
    # Background household purchases replenish finite dealer liquidity, sourced explicitly.
    key = market['id']
    cash = account(game, f'market:{key}')
    desired = int(settings()['market_opening'] * world['scale'])
    top_up = min(max(0, desired - cash['balance']), account(game, f'background:{market["world"]}')['balance'])
    if top_up:
        transfer_value(game, f'background:{market["world"]}', f'market:{key}', top_up, '背景消费回款')
    market['last_year'] = game.player.age
    market['revision'] += 1
    return True


def reprice(game, market, row):
    row['price'] = row['reference'] * game.economy_v2['worlds'][market['world']]['price_level'] * price_multiplier(row['stock'], row['target'])
    market['revision'] += 1


def operator_account(game, world=None, location=None):
    ensure_state(game)
    key = f'operator:{market_id(world or game.player.world, location or game.player.location_id)}'
    account(game, key)
    return key

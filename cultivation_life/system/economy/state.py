"""World economy and persistent local inventories, with lazy regional settlement."""
import hashlib
import math
from functools import lru_cache

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
        from .personal import ensure_personal
        changed = ensure_personal(game)
        if 'consumption_policy' not in game.economy_v2:
            game.economy_v2.update(consumption_policy=2, policy_year=game.player.age)
            for row in game.economy_v2['markets'].values():
                row['last_year'] = game.player.age
            for row in game.economy_v2.get('organizations',{}).values():
                row['last_year'] = game.player.age
            for row in game.economy_v2.get('estates',{}).values():
                row['last_year'] = game.player.age
            changed = True
        if game.economy_v2.get('demand_policy') != 1:
            game.economy_v2.update(demand_policy=1,demand_policy_year=game.player.age)
            for row in game.economy_v2['markets'].values():row.update(last_year=game.player.age,household_year=game.player.age)
            for row in game.economy_v2.get('organizations',{}).values():
                row.update(last_year=game.player.age,demand_credit={},cultivation_support={},
                           maintenance_support={},breakthrough_support={},longevity_support={})
            for row in game.economy_v2.get('estates',{}).values():row['last_year']=game.player.age
            changed=True
        return changed
    from ...economy_schema import validate_economy_settings
    validate_economy_settings(settings())
    game.economy_v2 = dict(schema_version=1, base_year=game.player.age, last_year=game.player.age,
                           worlds={}, markets={}, accounts={}, ledger=[], consumption_policy=2, policy_year=game.player.age,
                           demand_policy=1,demand_policy_year=game.player.age)
    for world, profile in WORLD_SYSTEMS['world_profiles'].items():
        if int(profile['tier']) <= 0:
            continue
        game.economy_v2['worlds'][world] = dict(scale=1., price_level=1., money_supply_index=1.,
            last_year=game.player.age, history=[], black_market_volume=0, black_market_quantity=0)
        account(game, f'background:{world}', settings()['background_opening'] * int(profile['tier']))
        account(game, f'world:{world}')
    from .personal import ensure_personal
    ensure_personal(game)
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
        row['last_year'] = game.player.age
        # Issue only against completed terminal purchases, and only when the
        # existing background pool is short of operating liquidity.
        pool = account(game, f'background:{world}')
        eligible = int(row.pop('unfunded_growth_sales', 0))
        amount = min(int(eligible * .02), max(0, settings()['market_opening'] - pool['balance']))
        pool['balance'] += amount
        row['issued'] = row.get('issued', 0)+amount
        row['money_supply_index'] = 1+row['issued']/max(1,settings()['background_opening'])
        state.setdefault('issued', 0)
        state['issued'] += amount
        row['history'].append([game.player.age, round(row['scale'], 6)])
        del row['history'][:-24]
    state['last_year'] = game.player.age
    market = local_market(game)
    if market:
        settle_market(game, market)
    return True


@lru_cache(maxsize=32)
def commodity_catalog(world=None, *, commercial=True):
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
    from .enterprise_rules import farm_goods
    for place in (([world] if world else WORLD_SYSTEMS['world_profiles']) if commercial else []):
        for key, row in farm_goods(place).items():
            result.setdefault(key, row)
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
            target = settings()['base_stock'] * _variation(world, location, item)
            commodities[item] = dict(stock=target, target=target, price=float(definition['base_price']),
                reference=definition['base_price'], tier=definition['tier'],
                production=0., consumption=0.,
                volume=0, history=[], initial_target=target)
        game.economy_v2['markets'][key] = dict(id=key, world=world, location=location,
            name=maps.location(world, location)['name'], last_year=game.player.age,
            revision=0, commodities=commodities, turnover=0, fees=0, unique_sales=0)
        account(game, f'market:{key}')
        opening = min(settings()['market_opening'], account(game, f'background:{world}')['balance'])
        transfer_value(game, f'background:{world}', f'market:{key}', opening, '市场开业周转金')
        account(game, f'operator:{key}')
        changed = True
    market=game.economy_v2['markets'][key]
    if market.get('goods_policy') != 1:
        # Existing schema-10 markets acquire a catalogue, not free stock or
        # historical production. New markets above already have opening stock.
        for item,definition in commodity_catalog(world).items():
            if item in market['commodities']:continue
            target=settings()['base_stock']*_variation(world,location,item)
            market['commodities'][item]=dict(stock=0.,target=target,price=float(definition['base_price']),
                reference=definition['base_price'],tier=definition['tier'],production=0.,consumption=0.,
                volume=0,history=[],initial_target=target)
        market['goods_policy']=1
        changed=True
    if 'household_year' not in market:
        market['household_year']=game.player.age
        changed=True
    return settle_market(game, market) or changed


def ensure_market(game, maps):
    world, location = game.player.world, game.player.location_id
    changed = ensure_regional_market(game, maps, world, location)
    if world not in game.economy_v2['worlds']:
        return changed
    key = market_id(world, location)
    market = game.economy_v2['markets'][key]
    from .enterprise_rules import farm_goods
    for item, definition in farm_goods(world).items():
        if item not in market['commodities']:
            target = settings()['base_stock']
            market['commodities'][item] = dict(stock=0., target=target, price=float(definition['base_price']),
                reference=definition['base_price'], tier=definition['tier'], production=0., consumption=0.,
                volume=0, history=[], initial_target=target, imported=True)
            market['revision'] += 1
            changed = True
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
    """Settle bounded real baskets once for the observed interval."""
    years = game.player.age - market['last_year']
    if years <= 0:
        return False
    market['war_pressure'] = any(w.get('status') in {'active', 'peace_ready'} and w.get('world') == market['world']
        and w.get('location_id') == market['location'] for w in game.wars)
    world = game.economy_v2['worlds'][market['world']]
    from .market_power import settle
    competitive_supply = settle(game, market, years)
    for item, quantity in competitive_supply.items():
        row = market['commodities'][item]
        row['production'] += quantity / years
        reprice(game, market, row)
    from .basket_consumption import settle as settle_baskets
    # The background household sector batches procurement over five real
    # years. NPC provisions/jobs/combat/events still tick annually. This is an
    # explicit transaction-timing approximation, not a replay of skipped years.
    household_years=game.player.age-market.get('household_year',market['last_year'])
    spent=0
    if household_years>=5:
        spent=settle_baskets(game,market,household_years)
        market['household_year']=game.player.age
    world['unfunded_growth_sales'] = world.get('unfunded_growth_sales', 0)+spent
    market['last_year'] = game.player.age
    for owner in list(market.get('suppliers', {})):
        market['suppliers'][owner] *= math.exp(-.1 * years)
        if market['suppliers'][owner] < .01:
            del market['suppliers'][owner]
    market['revision'] += 1
    return True


def reprice(game, market, row):
    from .basket_trade import reprice as update_price
    update_price(game, market, row)


def operator_account(game, world=None, location=None):
    ensure_state(game)
    key = f'operator:{market_id(world or game.player.world, location or game.player.location_id)}'
    account(game, key)
    return key

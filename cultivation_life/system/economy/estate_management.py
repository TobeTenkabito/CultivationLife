"""Bounded organization investment and local stewards using real market orders."""
from ...content_registry import WORLD_SYSTEMS, FACTION_DEFINITIONS
from .ledger import balance
from .enterprise_state import estates, owner_allowed, payer
from .enterprise_rules import recipes, KINDS
from .enterprise_market import market_at
from .state import commodity_catalog
from .local_market import quote


def settlement_interval(game, row):
    """Bound autonomous small-settlement aggregation to five actual years."""
    if row['kind'] != 'sect' or game.player.faction_id == row['identity']:
        return 1
    interval = FACTION_DEFINITIONS.get(row['identity'], {}).get('npc_economy', {}).get('settlement_years', 1)
    if interval <= 1:
        return 1
    from .industry import participating_wars
    if owner_allowed(game, 'sect', row['identity'], row['world']) or participating_wars(game, row['identity'], row['world']):
        return 1
    return min(5, max(1, int(interval)))


def recruitment_ready(game, entity):
    kind = 'family' if entity is game.family else 'sect'
    address = f'organization:{kind}:{entity.id}'
    row = game.economy_v2.get('organizations', {}).get(address, {})
    from .organization_production import workforce, annual_upkeep
    tier = WORLD_SYSTEMS['world_profiles'][entity.world]['tier']
    upkeep = row.get('expected_upkeep')
    if upkeep is None:
        upkeep = annual_upkeep(workforce(entity), tier)
    return not row.get('shortfall') and game.intrigue_state.get('factions', {}).get(f'{kind}:{entity.id}', {}).get('resources', 0) >= (upkeep + 100 * tier) * 3


def plan(game, maps, row):
    """A resident steward configures at most one real batch per annual tick."""
    # Paid batches have fixed inputs/output; reassess after they finish.
    if row['job']:
        row.update(enabled=True, auto_sell=True)
        return
    market = market_at(game, maps, row)
    options = recipes(row['world'], commodity_catalog(row['world']))
    cash = balance(game, payer(row))
    if row['owner_kind'] in {'sect', 'family'}:
        org = game.economy_v2.get('organizations', {}).get(payer(row), {})
        cash = max(0, cash - org.get('expected_upkeep', 0) * 3)
    budget = cash // 10
    dealer_cash = balance(game,f'market:{market["id"]}')
    candidates = []
    from .resource_access import permits
    for identity, recipe in options.items():
        if recipe['kind'] != row['kind'] or not permits(row,recipe):
            continue
        product = market['commodities'][recipe['output']]
        room = max(0,int(product['target']*1.5-product['stock']))
        if recipe['quantity'] > room:
            continue
        sale = quote(product,'sell',recipe['quantity'])
        if sale['gross'] > dealer_cash:
            continue
        cost = max(1, int(product['price'] * recipe['quantity'] * recipe['labor'] + .999))
        cost += sum(quote(market['commodities'][k], 'buy', q)['total'] for k, q in recipe['inputs'].items())
        revenue = sale['total']
        if revenue >= cost*1.05 and cost <= budget:
            candidates.append(((revenue - cost) / recipe['years'], identity))
    if not row['job'] and candidates:
        row['recipe'] = max(candidates)[1]
    # Shop stewards liquidate actual holdings. They do not buy and resell the
    # same local goods at a guaranteed spread loss simply to show activity.
    row.update(enabled=True, auto_buy=bool(candidates) and row['kind'] != 'shop',
               auto_sell=True, batches=1, buy_limit=max(1, budget), sell_limit=0,
               sale_quota=1000000, expense_limit=budget)
    if not candidates and not row['job'] and row['kind'] != 'shop':
        row['enabled'] = bool(row['stock'])


def invest_surplus(game, maps, entity, finance):
    kind = finance['kind']
    if owner_allowed(game, kind, entity.id, entity.world) or finance.get('shortfall'):
        return
    from .industry import participating_wars
    if participating_wars(game,entity.id,entity.world):
        return
    initial_limit = FACTION_DEFINITIONS.get(entity.id, {}).get('npc_economy', {}).get('estate_limit')
    if initial_limit is not None:
        members = sum(finance.get('workforce', {}).values())
        limit = min(5, initial_limit + max(0, members - 4) // 4)
        owned = sum(e['owner_kind'] == kind and e['owner_id'] == entity.id
                    for e in estates(game).values())
        if owned >= limit:
            return
    from ..faction_geography import faction_site
    from .enterprise_acquisition import acquire, price
    location = faction_site(entity)['id']
    source = f'organization:{kind}:{entity.id}'
    funds = balance(game, source)
    reserve = max(10000, finance.get('expected_upkeep', 0) * 5)
    if funds < reserve * 2:
        return
    # One purchase per organization settlement; six fixed plots per map.
    for asset in ('farm', 'mine', 'hunt', 'alchemy', 'forge'):
        identity = f'{entity.world}:{location}:{asset}'
        existing = estates(game).get(identity)
        if existing and existing['owner_kind'] != 'background':
            continue
        offer = existing or dict(world=entity.world, location=location, kind=asset, level=1)
        cost = price(game, maps, offer)
        if cost > (funds - reserve) // 3:
            continue
        row = acquire(game, maps, entity.world, location, asset, kind, entity.id, source,
                      max((int(r) for r in finance.get('workforce', {})), default=1))
        row['entrusted'] = True
        finance['expense'] += cost
        plan(game, maps, row)
        break

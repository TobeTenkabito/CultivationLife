"""Same-world freight: merchant-owned cash, unique cargo and elapsed-year arrivals."""
import hashlib
import math

from ...content_registry import ITEM_CATALOG, WORLD_SYSTEMS
from ..teleport_system import arrays, separated
from .ledger import account, balance, transfer_value
from .local_market import quote
from .state import ensure_state, ensure_regional_market, market_id, reprice
from .fleet_network import (ensure_network, ensure_routes, advance_network, owner_key,
    owner_sites, seed_organization_fleets, guard_required)


def treasury(world, identity):
    return f'alliance:{world}:{identity}'


def _cash(fleet):
    return f'caravan:{fleet["id"]}'


def _roll(game, fleet, suffix):
    value = f'freight:{game.seed}:{fleet["id"]}:{fleet["voyages"]}:{suffix}'
    return int.from_bytes(hashlib.blake2s(value.encode(), digest_size=8).digest(), 'big') / 2**64


def ensure_caravans(game, maps, *, _world=None, _linked=True):
    """Adopt a visited realm without spending, dispatching, or drawing game RNG."""
    ensure_state(game)
    state = game.economy_v2.setdefault('transport', dict(version=1, worlds={}))
    world = _world or game.player.world
    alliances = game.merchant_state.get('worlds', {}).get(world, [])
    if not alliances or world in state['worlds']:
        changed = ensure_network(game, maps)
        route_change = ensure_routes(game)
        if _linked:
            for home in sorted({a['home_world'] for a in alliances if a['cross_world']} - {world}):
                changed = ensure_caravans(game, maps, _world=home, _linked=False) or changed
        return route_change or changed
    adopted_year = max(game.player.age, game.economy_v2['last_year'])
    state['worlds'][world] = dict(last_year=adopted_year, fleets={}, history=[])
    region = state['worlds'][world]
    for alliance in alliances:
        key = f'{world}:{alliance["id"]}:1'
        fleet = dict(id=key, alliance_id=alliance['id'], world=world,
            name=f'{alliance["name"]}第一商队', location=alliance['hq'], status='waiting',
            capacity=24, investment=0, profit=0, dividends=0, voyages=0, delivered=0,
            lost=0, loss_streak=0, idle_years=0, cargo=None, operating_costs=0, last_result='等待本地商机',
            next_departure=adopted_year + 1)
        region['fleets'][key] = fleet
        account(game, _cash(fleet))
    ensure_network(game, maps)
    ensure_routes(game)
    if _linked:
        for home in sorted({a['home_world'] for a in alliances if a['cross_world']} - {world}):
            ensure_caravans(game, maps, _world=home, _linked=False)
    return True


def route_quote(game, maps, world, origin, destination, value):
    """Commercial array access is paid by cargo; no player permit or movement."""
    realm = max(1, int(WORLD_SYSTEMS['world_profiles'][world].get('npc_realm_cap', 5)) - 2)
    normal = maps.travel_plan(world, origin, destination, realm)
    if normal.status != 'ok':
        return None
    years, via, operator = normal.years, None, None
    network = arrays(game, maps, world)
    if origin in network:
        for node in sorted(network):
            if not separated(maps, world, origin, node):
                continue
            onward = None if node == destination else maps.travel_plan(world, node, destination, realm)
            if onward is not None and onward.status != 'ok':
                continue
            candidate = 1 + (onward.years if onward else 0)
            if candidate < years:
                years, via, operator = candidate, node, network[origin]['owner_id']
    normal_cost = max(1, math.ceil(value * .003 * normal.years))
    saved_ratio = (normal.years - years) / normal.years
    array_fee = math.floor(normal_cost * saved_ratio)
    return dict(origin=origin, destination=destination, route=list(normal.route),
        normal_years=normal.years, years=years, saved_ratio=saved_ratio,
        transport_cost=normal_cost - array_fee, array_fee=array_fee,
        array_via=via, array_operator=operator,
        risk=min(.3, .015 + years * .006), cost=normal_cost)


def _market(game, world, location):
    return game.economy_v2['markets'][market_id(world, location)]


def _history(region, year, fleet, message):
    region['history'].append(dict(year=year, fleet_id=fleet['id'], message=message))
    del region['history'][:-36]
    fleet['last_result'] = message


def _candidate(game, maps, alliance, fleet):
    if fleet.get('trade_order', {}).get('mode', 'auto') != 'auto':
        from .trade_orders import candidate
        return candidate(game, maps, fleet, route_quote)
    world, origin = fleet['world'], fleet['location']
    # Use existing branch geography. Never create a cross-world route from an ID.
    sites = sorted({alliance['hq'], *(row['location_id'] for row in alliance['offices'])})
    from .market_power import rival_targets
    sites = sorted(set(sites) | set(rival_targets(game, world)))
    for site in {origin, *sites}:
        ensure_regional_market(game, maps, world, site)
    source = _market(game, world, origin)
    # Trade only standard goods already present in both actual markets.
    goods = sorted(source['commodities'], key=lambda item: (
        source['commodities'][item]['stock'] / source['commodities'][item]['target'], item), reverse=True)
    budget = balance(game, _cash(fleet))
    best = None
    for destination in sites:
        if destination == origin:
            continue
        target = _market(game, world, destination)
        geography = route_quote(game, maps, world, origin, destination, 1)
        if not geography:
            continue
        # Bounded search; never scan millions of units individually.
        candidates = sorted((item for item in goods if item in target['commodities']),
            key=lambda item: target['commodities'][item]['price'] / source['commodities'][item]['price'], reverse=True)[:12]
        for item in candidates:
            row, other = source['commodities'][item], target['commodities'][item]
            maximum = min(fleet['capacity'], int(row['stock']))
            for quantity in sorted({maximum, maximum // 2, maximum // 4}, reverse=True):
                if quantity <= 0:
                    continue
                purchase = quote(row, 'buy', quantity)
                transport = dict(geography)
                coverage = fleet.get('guard_power', guard_required(world)) / guard_required(world)
                transport['risk'] = min(.9, transport['risk'] + max(0, 1 - coverage) * .65)
                if any(w.get('status') in {'active', 'peace_ready'} and w.get('world') == world
                       and w.get('location_id') in transport['route'] for w in game.wars):
                    transport['risk'] = min(.95, transport['risk'] + .2)
                transport['cost'] = max(1, math.ceil(purchase['total'] * .003 * transport['normal_years']))
                transport['array_fee'] = math.floor(transport['cost'] * transport['saved_ratio'])
                transport['transport_cost'] = transport['cost'] - transport['array_fee']
                cost = purchase['total'] + transport['cost']
                sale = quote(other, 'sell', quantity)
                expected = math.floor(sale['total'] * (1 - transport['risk'] * .55)) - cost
                if cost > budget or sale['gross'] > balance(game, f'market:{target["id"]}') or expected <= max(2, cost * .02):
                    continue
                score = expected / transport['years']
                if best is None or score > best['score']:
                    best = dict(item=item, quantity=quantity, purchase=purchase, transport=transport,
                        expected=expected, cost=cost, score=score, quoted_sale=sale['total'])
    return best


def _dispatch(game, maps, alliance, fleet, region):
    world = fleet['world']
    candidate = _candidate(game, maps, alliance, fleet)
    if candidate is None:
        fleet['idle_years'] += 1
        fleet['next_departure'] = game.player.age + 3
        fleet['last_result'] = '价差不足以覆盖运输与风险，留驻等候'
        return
    item, quantity = candidate['item'], candidate['quantity']
    plan, purchase = candidate['transport'], candidate['purchase']
    source = _market(game, world, fleet['location'])
    row = source['commodities'][item]
    cash = _cash(fleet)
    transfer_value(game, cash, f'market:{source["id"]}', purchase['total'], '商队采购实货')
    transfer_value(game, f'market:{source["id"]}', f'operator:{source["id"]}', purchase['fee'], '商队采购手续费')
    transfer_value(game, cash, f'background:{world}', plan['transport_cost'], '商队沿途运输支出')
    if plan['array_fee']:
        receiver = f'transport:{world}:{plan["array_operator"]}'
        account(game, receiver)
        transfer_value(game, cash, receiver, plan['array_fee'], '商队传送阵运输费')
    if candidate.get('source_estate') and not candidate.get('empty_return'):
        from .enterprise_state import estates, take
        estate = estates(game)[candidate['source_estate']]
        take(estate, item, quantity)
        estate['revision'] += 1
    else:
        row['stock'] -= quantity
        from .market_power import record_trade
        record_trade(game, source, item, _cash(fleet), 'buy', quantity)
        row['volume'] += quantity
    source['turnover'] += purchase['gross']
    source['fees'] += purchase['fee']
    source['freight_out'] = source.get('freight_out', 0) + quantity
    reprice(game, source, row)
    fleet['voyages'] += 1
    fleet.update(status='travelling', idle_years=0,
        cargo={**plan, 'item':item, 'quantity':quantity, 'purchased':quantity, 'departure':game.player.age,
            'arrival':game.player.age + plan['years'], 'cost':candidate['cost'], 'revenue':0,
            'expected_profit':candidate['expected'], 'quoted_sale':candidate['quoted_sale']})
    for key in ('sell_limit', 'empty_return', 'source_estate', 'target_estate'):
        if key in candidate:
            fleet['cargo'][key] = candidate[key]
    _history(region, game.player.age, fleet, f"购入{ITEM_CATALOG[item].name} ×{quantity}，启程运往{maps.location(world, plan['destination'])['name']}")


def _arrival(game, maps, fleet, region):
    cargo = fleet['cargo']
    world = fleet['world']
    if cargo['destination'] not in maps._locations.get(world, {}):
        fleet['status'] = 'stranded'
        fleet['last_result'] = '目的地暂不可达，货物仍由商队保管'
        return
    if fleet['status'] in {'travelling', 'stranded'}:
        # A deterministic voyage roll is consumed once, persisted with arrival status.
        lost = 0
        if _roll(game, fleet, 'risk') < cargo['risk']:
            fraction = 1 if _roll(game, fleet, 'disaster') < .1 else .25 + _roll(game, fleet, 'loss') * .6
            lost = min(cargo['quantity'], math.ceil(cargo['quantity'] * fraction))
        cargo['quantity'] -= lost
        fleet['lost'] += lost
        fleet.update(status='selling', location=cargo['destination'])
    ensure_regional_market(game, maps, world, fleet['location'])
    target = _market(game, world, fleet['location'])
    row = target['commodities'].get(cargo['item'])
    if cargo.get('target_estate') and not cargo.get('empty_return'):
        from .trade_orders import unload
        unload(game, fleet, cargo)
    if row is None and cargo['quantity']:
        fleet['last_result'] = '当地暂不收购，货物留在商队'
        return
    quantity = cargo['quantity']
    liquidity = balance(game, f'market:{target["id"]}')
    # Find the largest affordable delivery, keeping unpaid goods on the caravan.
    low, high = 0, quantity
    while low < high:
        middle = (low + high + 1) // 2
        sale = quote(row, 'sell', middle)
        if sale['gross'] <= liquidity and sale['total'] >= middle * cargo.get('sell_limit', 0) and not cargo.get('target_estate'):
            low = middle
        else:
            high = middle - 1
    if low:
        sale = quote(row, 'sell', low)
        transfer_value(game, f'market:{target["id"]}', _cash(fleet), sale['total'], '商队到货售出')
        transfer_value(game, f'market:{target["id"]}', f'operator:{target["id"]}', sale['fee'], '商队售货手续费')
        row['stock'] += low
        row['volume'] += low
        target['turnover'] += sale['gross']
        target['fees'] += sale['fee']
        target['freight_in'] = target.get('freight_in', 0) + low
        reprice(game, target, row)
        cargo['quantity'] -= low
        cargo['revenue'] += sale['total']
        fleet['delivered'] += low
        from .industry import supplier_delivery
        supplier_delivery(target, _cash(fleet), low, game=game, item=cargo['item'])
    if cargo['quantity']:
        fleet['last_result'] = f"抵达后留存 {cargo['quantity']} 件，等待限价、收购资金或目标仓库空位"
        return
    profit = cargo['revenue'] - cargo['cost']
    fleet['profit'] += profit
    fleet['loss_streak'] = fleet['loss_streak'] + 1 if profit < 0 else 0
    dividend = min(balance(game, _cash(fleet)), max(0, profit) // 4)
    if dividend:
        transfer_value(game, _cash(fleet), owner_key(fleet), dividend, '商队实得利润分红')
        fleet['dividends'] += dividend
    _history(region, game.player.age, fleet, f"本趟交割完成，净收益 {profit:+,} 灵石，上缴 {dividend:,} 灵石")
    from .trade_orders import finish
    finish(fleet, cargo)
    fleet.update(status='waiting', cargo=None, next_departure=game.player.age + 1)
    if fleet['loss_streak'] >= 2:
        fleet['capacity'] = max(6, fleet['capacity'] // 2)
    elif balance(game, _cash(fleet)) >= max(100, fleet['investment'] * 2) and fleet['capacity'] < 240:
        cost = max(20, fleet['investment'] // 4)
        transfer_value(game, _cash(fleet), f'background:{world}', cost, '商队扩充运力')
        fleet['operating_costs'] += cost
        fleet['profit'] -= cost
        fleet['investment'] += cost
        fleet['capacity'] = min(240, fleet['capacity'] + 12)


def advance_caravans(game, maps):
    ensure_caravans(game, maps)
    advance_network(game, maps)
    state = game.economy_v2['transport']
    for world, region in state['worlds'].items():
        years = game.player.age - region['last_year']
        if years <= 0:
            continue
        region['last_year'] = game.player.age
        seed_organization_fleets(game, maps, world, region)
        for fleet in list(region['fleets'].values()):
            if fleet['status'] == 'retired':
                continue
            alliance = owner_sites(game, maps, fleet)
            if alliance is None:
                # No fabricated replacement owner or treasury.
                fleet['last_result'] = '所属组织失效，停止派货；既有货物仍由原队伍保管'
                if fleet['cargo'] and game.player.age >= fleet['cargo']['arrival']:
                    _arrival(game, maps, fleet, region)
                continue
            if not fleet['investment']:
                funding = min(balance(game, owner_key(fleet)) // 4, 50000 * WORLD_SYSTEMS['world_profiles'][world]['tier'])
                if funding < 40:
                    fleet.update(status='retired', last_result='商盟无力出资，商队解散')
                    continue
                transfer_value(game, owner_key(fleet), _cash(fleet), int(funding), '所属方出资组建商队')
                fleet['investment'] = funding
            from .cross_freight import advance_freight
            if advance_freight(game, maps, fleet, region):
                continue
            if fleet['cargo']:
                if game.player.age >= fleet['cargo']['arrival']:
                    _arrival(game, maps, fleet, region)
                continue
            # An inactive interval pays actual elapsed upkeep, but never invents
            # round trips that were not dispatched during those years.
            upkeep = min(balance(game, _cash(fleet)), max(1, fleet['capacity'] // 12) * years)
            transfer_value(game, _cash(fleet), f'background:{world}', upkeep, '商队留驻养护')
            fleet['operating_costs'] += upkeep
            fleet['profit'] -= upkeep
            wages = max(1, round(fleet.get('guard_power', 0) ** .5)) * years if fleet.get('guard_power') else 0
            paid = min(wages, balance(game, _cash(fleet)))
            transfer_value(game, _cash(fleet), f'background:{world}', paid, '商队护卫薪饷')
            fleet['operating_costs'] += paid
            fleet['profit'] -= paid
            if paid < wages:
                fleet['guard_power'] = round(fleet['guard_power'] * paid / wages)
            if balance(game, _cash(fleet)) < 20 or (fleet['loss_streak'] >= 4 and fleet['capacity'] == 6):
                transfer_value(game, _cash(fleet), owner_key(fleet), balance(game, _cash(fleet)), '商队清算归还余额')
                fleet.update(status='retired', last_result='连续亏损或资金耗尽，商队已清算解散')
                _history(region, game.player.age, fleet, fleet['last_result'])
            elif game.player.age >= fleet['next_departure']:
                if fleet.get('trade_order', {}).get('mode') == 'hold':
                    continue
                try:
                    _dispatch(game, maps, alliance, fleet, region)
                except ValueError as exc:
                    fleet['last_result'] = str(exc)
                    fleet['next_departure'] = game.player.age + 1


def _cross_view(game, maps, fleet):
    from .fleet_network import alliance_at
    trip = fleet['cross_trip']
    returning = trip['phase'] in {'return', 'return_selling'}
    path = trip.get('path') or ([trip['destination'], fleet['world']] if returning else [fleet['world'], trip['destination']])
    index = trip.get('index', 1 if trip['phase'] in {'selling', 'return_selling'} else 0)
    current, next_world = path[index], path[min(index + 1, len(path) - 1)]
    owner = alliance_at(game, fleet['world'], fleet['alliance_id'])
    identity = owner.get('network_id', owner['id'])
    def address(world):
        location = (trip.get('source_location', fleet['location']) if world == fleet['world'] else
                    trip['location'] if world == trip['destination'] else alliance_at(game, world, identity)['hq'])
        return (world, location)
    first, second = address(current), address(next_world)
    def title(place):
        return WORLD_SYSTEMS['world_names'][place[0]] + ' · ' + maps.location(*place)['name']
    return dict(status='selling' if trip['phase'] in {'selling', 'return_selling'} else 'travelling',
                location=title(first), origin=title(first), destination=title(second), arrival=trip['arrival']), {first, second}


def public_caravans(game, maps, alliance_id=None, *, local=False):
    """Only current-world rows; cargo values are known only to this alliance's member."""
    world = game.player.world
    region = game.economy_v2.get('transport', {}).get('worlds', {}).get(world)
    result = []
    member = game.merchant_state.get('membership') or {}
    for fleet in (region or {}).get('fleets', {}).values():
        if alliance_id is not None and fleet['alliance_id'] != alliance_id:
            continue
        cargo = fleet['cargo']
        if local:
            if fleet.get('cross_trip'):
                if (world, game.player.location_id) not in _cross_view(game, maps, fleet)[1]:
                    continue
            elif game.player.location_id not in ({cargo['origin'], cargo['destination']} if cargo else {fleet['location']}):
                continue
        owned_alliance = fleet.get('owner_kind') == 'alliance' and any(
            a['id'] == fleet['alliance_id'] and a.get('player_owned')
            for a in game.merchant_state.get('worlds', {}).get(world, []))
        owned = fleet.get('player_controlled') or owned_alliance or (member.get('world') == world and member.get('alliance_id') == fleet['alliance_id'])
        row = {key: fleet[key] for key in ('id','name','alliance_id','status','capacity','voyages','last_result')}
        row.update(location=maps.location(world, fleet['location'])['name'],
            origin_id=cargo['origin'] if cargo else None,
            destination_id=cargo['destination'] if cargo else None,
            departure=cargo['departure'] if cargo else None,
            route=list(cargo.get('route', [cargo['origin'], cargo['destination']])) if cargo else [],
            origin=maps.location(world, cargo['origin'])['name'] if cargo else None,
            destination=maps.location(world, cargo['destination'])['name'] if cargo else None,
            arrival=cargo['arrival'] if cargo else None, detail=owned and not local)
        row.update(owner_kind=fleet.get('owner_kind', 'alliance'), guard_power=fleet.get('guard_power', 0),
                   guard_required=guard_required(world), pledged=fleet.get('pledged', False),
                   player_controlled=fleet.get('player_controlled', False), location_id=fleet['location'],
                   cross_trip=({k: fleet['cross_trip'][k] for k in ('destination', 'phase', 'arrival')}
                               if fleet.get('cross_trip') and owned else None))
        if owned and not local:
            row.update(cash=balance(game, _cash(fleet)), profit=fleet['profit'], dividends=fleet['dividends'],
                delivered=fleet['delivered'], lost=fleet['lost'], investment=fleet['investment'])
            row['operating_costs'] = fleet['operating_costs']
            if cargo:
                row['cargo'] = {key:cargo[key] for key in ('quantity','cost','expected_profit','normal_years','years',
                    'transport_cost','array_fee','risk','saved_ratio')}
                row['cargo']['name'] = ITEM_CATALOG[cargo['item']].name
        else:
            row.pop('last_result')
        result.append(row)
        trip = fleet.get('cross_trip')
        if trip:
            row.update(_cross_view(game, maps, fleet)[0])
    if local:
        # The receiving map can see an incoming shipment, never the foreign wallet.
        for home_world, remote in game.economy_v2.get('transport', {}).get('worlds', {}).items():
            if home_world == world:
                continue
            for fleet in remote['fleets'].values():
                trip = fleet.get('cross_trip')
                if not trip:
                    continue
                view, addresses = _cross_view(game, maps, fleet)
                if (world, game.player.location_id) not in addresses:
                    continue
                result.append(dict(id=fleet['id'], name=fleet['name'], alliance_id=fleet['alliance_id'],
                    capacity=fleet['capacity'], voyages=fleet['voyages'], detail=False, **view))
    return result

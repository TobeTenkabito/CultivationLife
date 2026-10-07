"""Bidirectional freight, physical passage legs and HQ-only cash collection."""
import math
import hashlib
from .fleet_network import alliance_at, route_path, route_key, routes, owner_key, leg_years, guard_required
from .ledger import account, balance, transfer_value
from .freight_trade import market, buy, sell


def _identity(home):
    return home.get('network_id', home['id'])


def _adopt(fleet):
    """Existing paid voyages keep their cargo, arrival and RNG, without rebilling."""
    trip = fleet['cross_trip']
    if 'path' not in trip:
        returning = trip['phase'] == 'return'
        trip.update(path=[trip['destination'], fleet['world']] if returning else [fleet['world'], trip['destination']],
                    index=0 if trip['phase'] != 'selling' else 1, tariff=0, leg_paid=True,
                    source_location=fleet['location'], remittance_percent=25, recalled=False)
    return trip


def _edge_open(game, fleet, first, second):
    owner = alliance_at(game, fleet['world'], fleet['alliance_id'])
    if not owner:
        return False
    local = alliance_at(game, first, _identity(owner))
    route = routes(game).get(route_key(_identity(owner), first, second))
    return bool(route and route['open'] and route_path(game, local, second) == [first, second])


def _schedule(game, fleet):
    trip = fleet['cross_trip']
    if trip['index'] == len(trip['path']) - 1:
        trip['arrival'] = game.player.age
        return True
    first, second = trip['path'][trip['index']:trip['index'] + 2]
    if not _edge_open(game, fleet, first, second):
        fleet['last_result'] = '通道关闭或坐镇资格不足，商队与实货在当前端等候'
        return False
    if not trip['leg_paid']:
        cash = f'caravan:{fleet["id"]}'
        if balance(game, cash) < trip['tariff']:
            fleet['last_result'] = '商队周转金不足以支付下一段关税，留驻等候'
            return False
        owner = alliance_at(game, fleet['world'], fleet['alliance_id'])
        local = alliance_at(game, first, _identity(owner))
        transfer_value(game, cash, f'alliance:{first}:{local["id"]}', trip['tariff'], '跨界货运本段出发地关税')
        trip['cost'] += trip['tariff']
        trip.update(leg_paid=True, arrival=game.player.age + leg_years(first, second))
    return True


def dispatch(game, maps, fleet, destination, *, remittance_percent=25, order=None):
    if type(remittance_percent) is not int or remittance_percent not in {0, 25, 50, 100}:
        raise ValueError('索款比例须为 0、25、50 或 100')
    owner = alliance_at(game, fleet['world'], fleet['alliance_id'])
    path = route_path(game, owner, destination)
    if (not owner or fleet.get('owner_kind') != 'alliance' or fleet['status'] != 'waiting'
            or fleet['cargo'] or fleet.get('cross_trip') or fleet['location'] != owner['hq'] or len(path) < 2):
        raise ValueError('需由本地总部或分总部的空闲商队沿开放通道出发')
    target = alliance_at(game, destination, _identity(owner))
    source_market = market(game, maps, fleet['world'], fleet['location'])
    target_market = market(game, maps, destination, target['hq'])
    cargo = buy(game, fleet, source_market, target_market, len(path) - 1, order)
    if cargo is None:
        raise ValueError('现有资金、库存和跨界价差不足以支持盈利运输')
    fleet['voyages'] += 1
    fleet['cross_trip'] = dict(**cargo, destination=destination, location=target['hq'], phase='outbound',
        path=path, index=0, leg_paid=False, source_location=fleet['location'], arrival=game.player.age,
        revenue=0, remittance=0, remittance_percent=remittance_percent, recalled=False)
    if order:
        fleet['cross_trip'].update(sell_limit=order['sell_limit'], return_item=order.get('return_item'),
                                  buy_limit=order['buy_limit'], order_quantity=order['quantity'])
    account(game, f'freight:{fleet["id"]}')
    _schedule(game, fleet)
    fleet['last_result'] = '实货已装载，沿现有通道逐段运输；返程自动采购有利可图的当地货物'


def recall(game, fleet):
    if not fleet.get('cross_trip'):
        raise ValueError('商队没有跨界货单')
    trip = _adopt(fleet)
    account(game, f'freight:{fleet["id"]}')
    if trip['phase'] in {'return', 'return_selling'}:
        raise ValueError('商队已经在返程')
    if trip['phase'] == 'outbound' and trip['leg_paid'] and game.player.age < trip['arrival']:
        raise ValueError('商队仍在运输途中，须抵达或确认通道受阻后才能撤回')
    trip.update(path=list(reversed(trip['path'][:trip['index'] + 1])), index=0,
                phase='return', leg_paid=False, recalled=True, arrival=game.player.age)
    _schedule(game, fleet)
    fleet['last_result'] = '已下达撤回：保留现有实货，沿已走通道返回原驻地后售货清算'


def _risk(game, fleet, trip, first, second):
    coverage = fleet.get('guard_power', 0) / max(guard_required(first), guard_required(second))
    risk = .05 + .65 * max(0, 1 - coverage)
    seed = f'freight:{game.seed}:{fleet["id"]}:{fleet["voyages"]}:{trip["phase"]}:{trip["index"]}'
    roll = int.from_bytes(hashlib.blake2s(seed.encode(), digest_size=8).digest(), 'big') / 2**64
    if roll < risk:
        lost = math.ceil(trip['quantity'] * .6)
        trip['quantity'] -= lost
        fleet['lost'] += lost


def _finish(game, fleet):
    trip = fleet['cross_trip']
    transfer_value(game, f'freight:{fleet["id"]}', owner_key(fleet), trip['remittance'], '跨界商队实际返抵总部交回托运款')
    profit = trip['revenue'] - trip['cost']
    fleet['profit'] += profit
    dividend = min(balance(game, f'caravan:{fleet["id"]}'), max(0, profit) // 4)
    transfer_value(game, f'caravan:{fleet["id"]}', owner_key(fleet), dividend, '跨界贸易利润上缴本界所属商盟')
    fleet['dividends'] += dividend
    fleet['last_result'] = f'跨界返航完成，贸易净收益 {profit:+,}，带回款项 {trip["remittance"]:,}'
    from .trade_orders import finish
    finish(fleet, trip)
    fleet.update(cross_trip=None, next_cross=game.player.age + 10, next_departure=game.player.age + 1)


def advance_freight(game, maps, fleet, region):
    trip = fleet.get('cross_trip')
    if not trip:
        order = fleet.get('trade_order', {})
        if order.get('mode', 'auto') != 'auto':
            if order.get('mode') in {'once', 'repeat'} and order.get('kind') == 'cross' and not fleet['cargo'] and game.player.age >= fleet.get('next_cross', 0):
                try:
                    dispatch(game, maps, fleet, order['destination'], remittance_percent=0, order=order)
                except ValueError as exc:
                    fleet['last_result'] = str(exc)
                    fleet['next_cross'] = game.player.age + 1
                return bool(fleet.get('cross_trip'))
            return False
        owner = alliance_at(game, fleet['world'], fleet['alliance_id'])
        if (owner and owner['cross_world'] and fleet['location'] == owner['hq'] and fleet['status'] == 'waiting'
                and not fleet['cargo'] and game.player.age >= fleet.get('next_cross', 0)):
            fleet['next_cross'] = game.player.age + 10
            for destination in owner['linked_worlds']:
                if destination == fleet['world']:
                    continue
                try:
                    dispatch(game, maps, fleet, destination)
                    return True
                except ValueError:
                    continue
        return False
    if game.player.age < trip['arrival']:
        return True
    trip = _adopt(fleet)
    owner = alliance_at(game, fleet['world'], fleet['alliance_id'])
    account(game, f'freight:{fleet["id"]}')
    if trip['phase'] in {'outbound', 'return'}:
        if trip['index'] < len(trip['path']) - 1:
            if not _schedule(game, fleet) or game.player.age < trip['arrival']:
                return True
            first, second = trip['path'][trip['index']:trip['index'] + 2]
            _risk(game, fleet, trip, first, second)
            trip['index'] += 1
            trip['leg_paid'] = False
            if trip['index'] < len(trip['path']) - 1:
                _schedule(game, fleet)
                return True
        trip['phase'] = 'selling' if trip['phase'] == 'outbound' else 'return_selling'
    returning = trip['phase'] == 'return_selling'
    world = fleet['world'] if returning else trip['destination']
    location = trip['source_location'] if returning else trip['location']
    target = market(game, maps, world, location)
    if trip['quantity']:
        sell(game, fleet, trip, target)
    if trip['quantity']:
        fleet['last_result'] = '所在地市场收购资金不足，余货留在商队等待交割'
        return True
    if returning:
        _finish(game, fleet)
        return True
    branch = alliance_at(game, trip['destination'], _identity(owner))
    path = route_path(game, branch, fleet['world'])
    if not path:
        fleet['last_result'] = '去程货物售罄，等待通道恢复后装货返航'
        return True
    source = market(game, maps, fleet['world'], trip['source_location'])
    selection = None
    if trip.get('return_item'):
        selection = dict(item=trip['return_item'], quantity=trip['order_quantity'], buy_limit=trip['buy_limit'])
    cargo = buy(game, fleet, target, source, len(path) - 1, selection)
    if cargo:
        trip.update(item=cargo['item'], quantity=cargo['quantity'], purchased=cargo['purchased'], tariff=cargo['tariff'])
        trip['cost'] += cargo['cost']
    else:
        trip['tariff'] = 0
    if owner['home_world'] == fleet['world']:
        key = f'alliance:{branch["world"]}:{branch["id"]}'
        trip['remittance'] = balance(game, key) * trip['remittance_percent'] // 100
        transfer_value(game, key, f'freight:{fleet["id"]}', trip['remittance'], '分总部实付托运款，由总部派出的商队携回')
    trip.update(phase='return', path=path, index=0, leg_paid=False, arrival=game.player.age)
    _schedule(game, fleet)
    fleet['last_result'] = '当地交割完成，返程货物与托运款在途，所属府库尚未入账'
    return True

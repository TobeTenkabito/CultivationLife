"""Finite HQ round trips; local branch money is collected only at physical arrival."""
import math
import hashlib
from .fleet_network import alliance_at, route_open, owner_key
from .ledger import account, balance, transfer_value
from .state import ensure_regional_market, reprice
from .local_market import quote


def dispatch(game, maps, fleet, destination):
    home = alliance_at(game, fleet['world'], fleet['alliance_id'])
    if (not home or home['home_world'] != fleet['world'] or fleet.get('owner_kind') != 'alliance'
            or fleet['status'] != 'waiting' or fleet['cargo'] or fleet.get('cross_trip')
            or fleet['location'] != home['hq'] or not route_open(game, home, destination)
            or destination == fleet['world']):
        raise ValueError('需由总部所在地的空闲商队沿开放通道出发')
    branch = alliance_at(game, destination, home['id'])
    ensure_regional_market(game, maps, home['world'], home['hq'])
    ensure_regional_market(game, maps, destination, branch['hq'])
    source = game.economy_v2['markets'][f'{home["world"]}:{home["hq"]}']
    target = game.economy_v2['markets'][f'{destination}:{branch["hq"]}']
    cash = f'caravan:{fleet["id"]}'
    best = None
    for item, row in source['commodities'].items():
        if row['stock'] < 1 or row.get('imported'):
            continue
        other = target['commodities'].get(item) or dict(row, stock=0., production=0., consumption=0.,
            volume=0, history=[], imported=True)
        for quantity in sorted({min(fleet['capacity'], int(row['stock'])), 1}, reverse=True):
            purchase = quote(row, 'buy', quantity)
            tariff = max(10, math.ceil(purchase['total'] * .15))
            cost = purchase['total'] + tariff
            sale = quote(other, 'sell', quantity)
            profit = sale['total'] - cost
            if cost <= balance(game, cash) and profit > 0 and sale['gross'] <= balance(game, f'market:{target["id"]}'):
                if best is None or profit > best['profit']:
                    best = dict(item=item, row=row, target=other, quantity=quantity, purchase=purchase,
                                tariff=tariff, cost=cost, profit=profit)
    if best is None:
        raise ValueError('现有资金、库存和跨界价差不足以支持盈利运输')
    row = best['row']
    target['commodities'].setdefault(best['item'], best['target'])
    transfer_value(game, cash, f'market:{source["id"]}', best['purchase']['total'], '跨界商队采购')
    transfer_value(game, f'market:{source["id"]}', f'operator:{source["id"]}', best['purchase']['fee'], '跨界采购手续费')
    transfer_value(game, cash, owner_key(fleet), best['tariff'], '跨界货运出境关税')
    row['stock'] -= best['quantity']
    source['freight_out'] = source.get('freight_out', 0) + best['quantity']
    reprice(game, source, row)
    fleet['voyages'] += 1
    fleet['cross_trip'] = dict(destination=destination, location=branch['hq'], phase='outbound',
        arrival=game.player.age + 3, item=best['item'], quantity=best['quantity'],
        purchased=best['quantity'], cost=best['cost'], revenue=0, remittance=0)
    fleet['last_result'] = '已装载实货经逆灵通道出发，三年后抵达分总部'


def advance_freight(game, maps, fleet, region):
    trip = fleet.get('cross_trip')
    if not trip:
        # A headquarters requests funds only by dispatching its own funded fleet.
        home = alliance_at(game, fleet['world'], fleet['alliance_id'])
        if (home and home['home_world'] == fleet['world'] and home['cross_world']
                and fleet['location'] == home['hq'] and fleet['status'] == 'waiting'
                and game.player.age >= fleet.get('next_cross', 0)):
            fleet['next_cross'] = game.player.age + 10
            for destination in home['linked_worlds']:
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
    home = alliance_at(game, fleet['world'], fleet['alliance_id'])
    if trip['phase'] != 'selling' and not route_open(game, home, trip['destination']):
        fleet['last_result'] = '逆灵通道关闭，商队在原端等候；货物与款项未转移'
        return True
    escrow = f'freight:{fleet["id"]}'
    account(game, escrow)
    if trip['phase'] == 'return':
        transfer_value(game, escrow, owner_key(fleet), trip['remittance'], '跨界商队返抵总部交回分部款项')
        profit = trip['revenue'] - trip['cost']
        fleet['profit'] += profit
        dividend = min(balance(game, f'caravan:{fleet["id"]}'), max(0, profit) // 4)
        transfer_value(game, f'caravan:{fleet["id"]}', owner_key(fleet), dividend, '跨界贸易利润上缴')
        fleet['dividends'] += dividend
        fleet['last_result'] = f'跨界返航完成，贸易净收益 {profit:+,}，带回分部款项 {trip["remittance"]:,}'
        fleet['cross_trip'] = None
        fleet['next_cross'] = game.player.age + 10
        fleet['next_departure'] = game.player.age + 1
        return True
    ensure_regional_market(game, maps, trip['destination'], trip['location'])
    target = game.economy_v2['markets'][f'{trip["destination"]}:{trip["location"]}']
    row = target['commodities'][trip['item']]
    if trip['phase'] == 'outbound':
        from .fleet_network import guard_required
        risk = .05 + .65 * max(0, 1 - fleet.get('guard_power', 0) / guard_required(fleet['world']))
        seed = f'freight:{game.seed}:{fleet["id"]}:{fleet["voyages"]}:cross-risk'
        roll = int.from_bytes(hashlib.blake2s(seed.encode(), digest_size=8).digest(), 'big') / 2**64
        if roll < risk:
            lost = math.ceil(trip['quantity'] * .6)
            trip['quantity'] -= lost
            fleet['lost'] += lost
        trip['phase'] = 'selling'
    low, high = 0, trip['quantity']
    while low < high:
        middle = (low + high + 1) // 2
        if quote(row, 'sell', middle)['gross'] <= balance(game, f'market:{target["id"]}'):
            low = middle
        else:
            high = middle - 1
    if low:
        sale = quote(row, 'sell', low)
        transfer_value(game, f'market:{target["id"]}', f'caravan:{fleet["id"]}', sale['total'], '跨界实货交割')
        transfer_value(game, f'market:{target["id"]}', f'operator:{target["id"]}', sale['fee'], '跨界到货交易手续费')
        row['stock'] += low
        target['freight_in'] = target.get('freight_in', 0) + low
        trip['quantity'] -= low
        trip['revenue'] += sale['total']
        fleet['delivered'] += low
        reprice(game, target, row)
    if trip['quantity']:
        fleet['last_result'] = '异界市场收购资金不足，余货保留在商队'
        return True
    if not route_open(game, home, trip['destination']):
        fleet['last_result'] = '货物已在分总部售罄，等待通道重开后装款返航'
        return True
    branch = alliance_at(game, trip['destination'], fleet['alliance_id'])
    branch_key = f'alliance:{trip["destination"]}:{branch["id"]}'
    remittance = balance(game, branch_key) // 4
    transfer_value(game, branch_key, escrow, remittance, '分总部将四分之一余款交由总部商队携回')
    trip.update(phase='return', remittance=remittance, arrival=game.player.age + 3)
    fleet['last_result'] = '分总部交割完成，携款返航；总部尚未入账'
    return True

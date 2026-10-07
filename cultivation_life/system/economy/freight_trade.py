"""Actual purchases and partial sales for the unique cross-world cargo."""
import math
from .ledger import balance, transfer_value
from .state import ensure_regional_market, reprice
from .local_market import quote


def market(game, maps, world, location):
    ensure_regional_market(game, maps, world, location)
    return game.economy_v2['markets'][f'{world}:{location}']


def buy(game, fleet, source, target, hops, order=None):
    cash = f'caravan:{fleet["id"]}'
    best = None
    for item, row in source['commodities'].items():
        if row['stock'] < 1 or (row.get('imported') and not order) or (order and item != order['item']):
            continue
        other = target['commodities'].get(item) or dict(row, stock=0., production=0., consumption=0.,
            volume=0, history=[], imported=True)
        maximum = min(fleet['capacity'], int(row['stock']))
        for quantity in ([order['quantity']] if order else sorted({maximum, maximum // 2, maximum // 4, 1}, reverse=True)):
            if quantity < 1 or quantity > maximum:
                continue
            purchase = quote(row, 'buy', quantity)
            if order and purchase['total'] > quantity * order['buy_limit']:
                continue
            tariff = max(10, math.ceil(purchase['total'] * .15))
            sale = quote(other, 'sell', quantity)
            total = purchase['total'] + tariff * hops
            profit = sale['total'] - total
            # Keep enough working cash to bring this cargo back if a later edge
            # closes before a sale. This is retained cash, never a second wallet.
            if total + tariff * hops <= balance(game, cash) and (order or (profit > 0 and sale['gross'] <= balance(game, f'market:{target["id"]}'))):
                if best is None or profit > best['profit']:
                    best = dict(item=item, row=row, target=other, quantity=quantity, purchase=purchase, tariff=tariff, profit=profit)
    if best is None:
        return None
    row, purchase, quantity = best['row'], best['purchase'], best['quantity']
    target['commodities'].setdefault(best['item'], best['target'])
    transfer_value(game, cash, f'market:{source["id"]}', purchase['total'], '跨界商队采购实货')
    transfer_value(game, f'market:{source["id"]}', f'operator:{source["id"]}', purchase['fee'], '跨界采购手续费')
    row['stock'] -= quantity
    from .market_power import record_trade
    record_trade(game, source, best['item'], cash, 'buy', quantity)
    row['volume'] += quantity
    source['turnover'] += purchase['gross']
    source['fees'] += purchase['fee']
    source['freight_out'] = source.get('freight_out', 0) + quantity
    reprice(game, source, row)
    return dict(item=best['item'], quantity=quantity, purchased=quantity, tariff=best['tariff'], cost=purchase['total'])


def sell(game, fleet, trip, target):
    row = target['commodities'][trip['item']]
    low, high = 0, trip['quantity']
    while low < high:
        middle = (low + high + 1) // 2
        sale = quote(row, 'sell', middle)
        if sale['gross'] <= balance(game, f'market:{target["id"]}') and sale['total'] >= middle * trip.get('sell_limit', 0):
            low = middle
        else:
            high = middle - 1
    if low:
        sale = quote(row, 'sell', low)
        transfer_value(game, f'market:{target["id"]}', f'caravan:{fleet["id"]}', sale['total'], '跨界实货交割')
        transfer_value(game, f'market:{target["id"]}', f'operator:{target["id"]}', sale['fee'], '跨界到货手续费')
        row['stock'] += low
        row['volume'] += low
        target['turnover'] += sale['gross']
        target['fees'] += sale['fee']
        target['freight_in'] = target.get('freight_in', 0) + low
        trip['quantity'] -= low
        trip['revenue'] += sale['total']
        fleet['delivered'] += low
        reprice(game, target, row)
        from .industry import supplier_delivery
        from .fleet_network import owner_key
        supplier_delivery(target, f'caravan:{fleet["id"]}', low, game=game, item=trip['item'])

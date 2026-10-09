"""Shared finite standard-good transactions, without facade dependency cycles."""
import math
from ...content_registry import MARKET_SETTINGS
from .pricing import total_price, price_multiplier
from .ledger import balance, transfer_value


def quote(row, side, quantity):
    if side not in {'buy', 'sell'} or type(quantity) is not int or not 1 <= quantity <= 1000000:
        raise ValueError('交易方向或数量无效')
    gross = total_price(row['reference'], row['stock'], quantity, row['target'], side)
    fee = math.floor(gross * MARKET_SETTINGS['economy_v2']['transaction_fee'])
    return dict(gross=gross, fee=fee, total=gross if side == 'buy' else gross-fee)


def affordable(row, side, wanted, funds):
    low, high = 0, min(1000000, max(0, int(wanted)))
    while low < high:
        mid = (low+high+1)//2
        if quote(row, side, mid)['gross'] <= funds:
            low = mid
        else:
            high = mid-1
    return low


def reprice(game, market, row):
    row['price'] = row['reference'] * game.economy_v2['worlds'][market['world']]['price_level'] * price_multiplier(row['stock'], row['target'])
    market['revision'] += 1


def purchase(game, market, source, item, wanted, budget, reason):
    row = market['commodities'][item]
    amount = affordable(row, 'buy', min(int(row['stock']), wanted), min(budget, balance(game, source)))
    if not amount:
        return 0, 0
    bill = quote(row, 'buy', amount)
    dealer = f'market:{market["id"]}'
    transfer_value(game, source, dealer, bill['total'], reason)
    transfer_value(game, dealer, f'operator:{market["id"]}', bill['fee'], reason+'手续费')
    row['stock'] -= amount
    row['volume'] += amount
    market['turnover'] += bill['gross']; market['fees'] += bill['fee']
    reprice(game, market, row)
    return amount, bill['total']

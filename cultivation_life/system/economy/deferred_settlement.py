"""Entry-time application of remote receipts through original economy ports."""
from .deferred import state, owner, posting

def _repay(game, key, amount):
    from .ledger import account, balance, transfer_value
    sink = 'regional:repaid'
    paid = min(amount, balance(game, key))
    account(game, sink)
    transfer_value(game, key, sink, paid, '入界核销系统垫款')
    game.economy_v2['accounts'][sink]['balance'] -= paid
    state(game)['repaid'] += paid
    game.economy_v2['issued'] -= paid
    return amount-paid


def apply(game, world, year):
    """Only the entered society consumes its own due receipts, once."""
    book = state(game)
    from .ledger import transfer_value
    from .state import reprice
    with posting():
        rows = book['pending'].get(world, [])
        due = sorted((r for r in rows if r['year'] <= year), key=lambda r:(r['year'], r['id']))
        retained = []
        for row in due:
            kind = row['kind']
            if kind in {'debit', 'credit'}:
                key, amount = row['account'], row['amount']
                if kind == 'credit':
                    transfer_value(game, f'regional:escrow:{world}', key, amount, row['reason']+'（入界入账）')
                    book['cash_delta'][key] -= amount
                else:
                    remaining = _repay(game, key, amount)
                    book['cash_delta'][key] += amount
                    book['debts'][key] = book['debts'].get(key, 0) + remaining
            elif kind == 'goods':
                market = game.economy_v2['markets'][row['market']]
                product = market['commodities'].setdefault(row['item'], dict(row['definition'],
                    stock=0., production=0., consumption=0., volume=0, history=[], imported=True))
                quantity = row['quantity']
                shortage = max(0, -quantity-product['stock'])
                if shortage:
                    key = world+':'+row['item']
                    book['goods_issued'][key] = book['goods_issued'].get(key, 0)+shortage
                product['stock'] = max(0, product['stock']+quantity)
                product['volume'] += abs(quantity)
                market['turnover'] += row['gross']; market['fees'] += row['fee']
                if row.get('direction'):
                    key = 'freight_'+row['direction']
                    market[key] = market.get(key, 0)+abs(quantity)
                if row.get('trader'):
                    if quantity > 0:
                        from .industry import supplier_delivery
                        supplier_delivery(market, row['trader'], quantity, game=game, item=row['item'])
                    else:
                        from .market_power import record_trade
                        record_trade(game, market, row['item'], row['trader'], 'buy', -quantity)
                reprice(game, market, product)
            elif kind == 'service':
                market = game.economy_v2['markets'][row['market']]
                market['turnover'] += row['amount']
                market['war_income'] = market.get('war_income', 0)+row['amount']
            elif kind == 'depot':
                from . import depot
                entity = game.family if row['owner_kind']=='family' and game.family and game.family.id==row['owner'] else game.sects.get(row['owner'])
                if entity is None:
                    retained.append(row)
                    continue
                stock = depot.ensure(game, entity)
                n = min(row['quantity'], max(0, 10000-depot.occupied(stock)))
                key = 'item:'+row['item']
                stock['stock'][key] = stock['stock'].get(key, 0)+n
                row['quantity'] -= n
                if row['quantity']:
                    retained.append(row)
                    continue
            book['applied'] += 1
        book['pending'][world] = retained+[r for r in rows if r['year'] > year]
        for key, debt in list(book['debts'].items()):
            if debt and owner(game, key) == world:
                book['debts'][key] = _repay(game, key, debt)
        book['cash_delta'] = {k:v for k,v in book['cash_delta'].items() if v}
        book['debts'] = {k:v for k,v in book['debts'].items() if v}

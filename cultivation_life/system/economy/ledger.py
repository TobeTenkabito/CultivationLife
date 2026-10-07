"""Integer spirit-stone transfers; the player's inventory stays authoritative."""
from ...rules import add_item, remove_item


def balance(game, account):
    if account == 'player':
        return sum(i.quantity for i in game.player.inventory if i.id == 'spirit_stone')
    return game.economy_v2['accounts'][account]['balance']


def account(game, key, opening=0):
    return game.economy_v2['accounts'].setdefault(key, {
        'balance': opening, 'income': 0, 'expense': 0,
    })


def transfer_value(game, source, destination, amount, reason):
    if type(amount) is not int or amount < 0 or source == destination:
        raise ValueError('资金转移参数无效')
    if any(key != 'player' and key not in game.economy_v2['accounts'] for key in (source, destination)):
        raise ValueError('资金账户不存在')
    if balance(game, source) < amount:
        raise ValueError('付款方灵石不足')
    if not amount:
        return
    if source == 'player':
        if not remove_item(game.player, 'spirit_stone', amount):
            raise ValueError('灵石不足')
    else:
        row = game.economy_v2['accounts'][source]
        row['balance'] -= amount
        row['expense'] += amount
    if destination == 'player':
        add_item(game.player, 'spirit_stone', amount)
    else:
        row = game.economy_v2['accounts'][destination]
        row['balance'] += amount
        row['income'] += amount
    entries = game.economy_v2['ledger']
    entries.append(dict(year=game.player.age, source=source, destination=destination,
                        amount=amount, reason=reason))
    del entries[:-80]


def record_external(game, source, destination, amount, reason):
    """Bridge legacy settled cash without paying the player a second time.

    These explicit background sources/sinks are allowed during staged adoption.
    They never represent an already modelled organization's treasury.
    """
    if type(amount) is not int or amount < 0:
        raise ValueError('经济入账金额无效')
    row = account(game, destination)
    row['balance'] += amount
    row['income'] += amount
    entries = game.economy_v2['ledger']
    entries.append(dict(year=game.player.age, source=source, destination=destination,
                        amount=amount, reason=reason))
    del entries[:-80]

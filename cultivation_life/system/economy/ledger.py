"""Integer spirit-stone transfers; the player's inventory stays authoritative."""
from ...rules import add_item, remove_item


def _organization(game, key):
    if not key.startswith('organization:'):
        return None
    _, kind, identity = key.split(':', 2)
    if kind in {'sect', 'family'}:
        row = game.intrigue_state.get('factions', {}).get(f'{kind}:{identity}')
        return (row, 'resources') if row is not None else None
    if kind == 'court' and identity == 'heavenly':
        return (game.heavenly_court, 'treasury') if game.heavenly_court else None
    if kind == 'upper':
        row = game.upper_institutions.get(identity)
        return (row, 'treasury') if row is not None else None
    return None


def _merchant(game, key):
    if not key.startswith('alliance:'):
        return None
    _, world, identity = key.split(':', 2)
    return next((row for row in game.merchant_state.get('worlds', {}).get(world, [])
                 if row['id'] == identity), None)


def balance(game, account):
    if account == 'player':
        return sum(i.quantity for i in game.player.inventory if i.id == 'spirit_stone')
    organization = _organization(game, account)
    if organization is not None:
        return int(organization[0][organization[1]])
    merchant = _merchant(game, account)
    if merchant is not None:
        return merchant['reserves']
    return game.economy_v2['accounts'][account]['balance']


def account(game, key, opening=0):
    if key.startswith(('alliance:', 'organization:')):
        raise ValueError('组织资金使用原府库字段，不能建立重复账户')
    return game.economy_v2['accounts'].setdefault(key, {
        'balance': opening, 'income': 0, 'expense': 0,
    })


def transfer_value(game, source, destination, amount, reason):
    if type(amount) is not int or amount < 0 or source == destination:
        raise ValueError('资金转移参数无效')
    accounts=game.economy_v2['accounts']
    direct_source=accounts.get(source) if source!='player' and not source.startswith(('organization:','alliance:')) else None
    direct_destination=accounts.get(destination) if destination!='player' and not destination.startswith(('organization:','alliance:')) else None
    if direct_source is not None and direct_destination is not None:
        if direct_source['balance']<amount:raise ValueError('付款方灵石不足')
        if not amount:return
        direct_source['balance']-=amount;direct_source['expense']+=amount
        direct_destination['balance']+=amount;direct_destination['income']+=amount
        _record_transfer(game,source,destination,amount,reason)
        return
    if any(key != 'player' and key not in accounts and _merchant(game, key) is None and _organization(game, key) is None
           for key in (source, destination)):
        raise ValueError('资金账户不存在')
    balance(game, destination)  # Validate the receiving treasury before any debit.
    if balance(game, source) < amount:
        raise ValueError('付款方灵石不足')
    if not amount:
        return
    if source == 'player':
        if not remove_item(game.player, 'spirit_stone', amount):
            raise ValueError('灵石不足')
    elif _organization(game, source) is not None:
        row, field = _organization(game, source)
        row[field] -= amount
    elif _merchant(game, source) is not None:
        _merchant(game, source)['reserves'] -= amount
    else:
        row = game.economy_v2['accounts'][source]
        row['balance'] -= amount
        row['expense'] += amount
    if destination == 'player':
        add_item(game.player, 'spirit_stone', amount)
    elif _organization(game, destination) is not None:
        row, field = _organization(game, destination)
        row[field] += amount
    elif _merchant(game, destination) is not None:
        _merchant(game, destination)['reserves'] += amount
    else:
        row = game.economy_v2['accounts'][destination]
        row['balance'] += amount
        row['income'] += amount
    _record_transfer(game,source,destination,amount,reason)


def _record_transfer(game,source,destination,amount,reason):
    entries = game.economy_v2['ledger']
    entries.append(dict(year=game.player.age, source=source, destination=destination,
                        amount=amount, reason=reason))
    del entries[:-80]
    from .personal import record
    record(game, entries[-1])


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
    from .personal import record
    record(game, entries[-1])

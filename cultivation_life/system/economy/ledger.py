"""Integer spirit-stone transfers; the player's inventory stays authoritative."""
from ...rules import add_item, remove_item
from .personal import record as record_personal


def _organization(game, key):
    if not key.startswith('organization:'):
        return None
    key=game.economy_v2.get('organization_aliases',{}).get(key,key)
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
    source_org = _organization(game, source)
    destination_org = _organization(game, destination)
    source_merchant = _merchant(game, source) if source_org is None else None
    destination_merchant = _merchant(game, destination) if destination_org is None else None
    if any(key != 'player' and key not in accounts and organization is None and merchant is None
           for key, organization, merchant in ((source, source_org, source_merchant),
                                               (destination, destination_org, destination_merchant))):
        raise ValueError('资金账户不存在')
    # Resolve original treasuries once per transfer. Never retain these mutable
    # records beyond the transaction or create a second organization wallet.
    if destination_org is not None:
        int(destination_org[0][destination_org[1]])
    elif destination_merchant is not None:
        destination_merchant['reserves']
    else:
        balance(game, destination)
    if source_org is not None:
        available = int(source_org[0][source_org[1]])
    elif source_merchant is not None:
        available = source_merchant['reserves']
    else:
        available = balance(game, source)
    if available < amount:
        raise ValueError('付款方灵石不足')
    if not amount:
        return
    if source == 'player':
        if not remove_item(game.player, 'spirit_stone', amount):
            raise ValueError('灵石不足')
    elif source_org is not None:
        row, field = source_org
        row[field] -= amount
    elif source_merchant is not None:
        source_merchant['reserves'] -= amount
    else:
        row = game.economy_v2['accounts'][source]
        row['balance'] -= amount
        row['expense'] += amount
    if destination == 'player':
        add_item(game.player, 'spirit_stone', amount)
    elif destination_org is not None:
        row, field = destination_org
        row[field] += amount
    elif destination_merchant is not None:
        destination_merchant['reserves'] += amount
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
    record_personal(game, entries[-1])


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
    record_personal(game, entries[-1])

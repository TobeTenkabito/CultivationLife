"""Dated remote receipts; a frozen treasury is never used as a second wallet.

Goods/cash already delivered to an active task are not delivered again on entry.
The clearing account holds real incoming escrow. Outgoing remote payments are
explicit system advances, repaid from the original treasury during catch-up.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache

from ...regional_context import CalendarGame

_posting = ContextVar('deferred_posting', default=False)


def state(game):
    return game.world_simulation.setdefault('deferred', dict(
        sequence=0, pending={}, cash_delta={}, debts={}, advanced=0, repaid=0,
        goods_issued={}, applied=0))


def frozen(game, world):
    if _posting.get():
        return False
    root, active = _scope(game)
    return bool(root.world_simulation and world != active and world in root.world_simulation['regions'])


def _scope(game):
    # Unwrap only for reads. Receipts still use the original dated view below.
    if isinstance(game, CalendarGame):
        return game._game, game._region_world
    return game, game.player.world


@lru_cache(maxsize=4096)
def _address(key):
    """Cache immutable account syntax only, never ownership or freeze state."""
    parts = key.split(':')
    if parts[0] in {'background', 'world', 'market', 'operator', 'alliance', 'transport'}:
        return 'fixed', parts[1]
    if parts[0] == 'organization':
        kind, identity = parts[1:3]
        if kind in {'sect', 'family'}:
            return 'entity', identity
        return 'fixed', 'celestial' if kind in {'court', 'yaochi'} else identity if kind == 'upper' else None
    return 'fixed', None


def owner(game, key):
    if isinstance(game, CalendarGame):
        game = game._game
    return _owner(game, key)


def _owner(game, key):
    # Aliases and the original entity's world are live reads: adoption,
    # relocation, replacement and loading another save cannot stale this cache.
    key = game.economy_v2.get('organization_aliases', {}).get(key, key)
    kind, identity = _address(key)
    if kind == 'entity':
        entity = game.family if game.family and game.family.id == identity else game.sects.get(identity)
        return entity.world if entity else None
    # Task cargo, fleet working capital and military escrow have one global
    # owner. They are not a duplicate of the frozen organization's treasury.
    return identity


@contextmanager
def posting():
    token = _posting.set(True)
    try:
        yield
    finally:
        _posting.reset(token)


def append(game, world, kind, **payload):
    book = state(game)
    book['sequence'] += 1
    row = dict(id=book['sequence'], year=game.player.age, kind=kind, **payload)
    book['pending'].setdefault(world, []).append(row)
    return row


def projected_balance(game, key, actual):
    if _posting.get():
        return actual
    root, active = _scope(game)
    sim = root.world_simulation
    if not sim:
        return actual
    world = _owner(root, key)
    if world != active and world in sim['regions']:
        book = sim.get('deferred', {})
        return max(0, actual + book.get('cash_delta', {}).get(key, 0)-book.get('debts', {}).get(key, 0))
    return actual


def transfer(game, source, destination, amount, reason, *, account, transfer_value, balance):
    if _posting.get():
        return False
    root, active = _scope(game)
    sim = root.world_simulation
    if not sim:
        return False
    first, second = _owner(root, source), _owner(root, destination)
    regions = sim['regions']
    outgoing = first != active and first in regions
    incoming = second != active and second in regions
    if not (outgoing or incoming):
        return False
    try:
        balance(game, source); balance(game, destination)
    except KeyError as exc:
        raise ValueError('资金账户不存在') from exc
    book = state(game)
    clearing = 'regional:clearing'
    with posting():
        pool = account(game, clearing)
        if outgoing:
            pool['balance'] += amount
            pool['income'] += amount
            book['advanced'] += amount
            game.economy_v2['issued'] = game.economy_v2.get('issued', 0) + amount
            append(game, first, 'debit', account=source, amount=amount, reason=reason)
            book['cash_delta'][source] = book['cash_delta'].get(source, 0) - amount
        else:
            # Validate before adding a receipt. Failed commands retain their
            # usual outer transaction rollback, including these new receipts.
            if balance(game, source) < amount:
                raise ValueError('付款方灵石不足')
            transfer_value(game, source, clearing, amount, reason)
        if incoming:
            escrow = f'regional:escrow:{second}'
            account(game, escrow)
            transfer_value(game, clearing, escrow, amount, reason)
            append(game, second, 'credit', account=destination, amount=amount, reason=reason)
            book['cash_delta'][destination] = book['cash_delta'].get(destination, 0) + amount
        else:
            transfer_value(game, clearing, destination, amount, reason)
    return True


def market_change(game, market, item, quantity, *, gross, fee, direction=None, trader=None):
    """Record one fixed trade; the original remote stock is untouched."""
    if not frozen(game, market['world']):
        return False
    append(game, market['world'], 'goods', market=market['id'], item=item,
           quantity=quantity, gross=gross, fee=fee, direction=direction, trader=trader,
           definition={k:v for k,v in market['commodities'][item].items()
                       if k in {'reference','target','tier','price','initial_target'}})
    return True


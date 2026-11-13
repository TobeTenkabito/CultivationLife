"""Lazy ordinary mana on the original NPC. Reading a page never replenishes it."""
from ..content_registry import REALMS
from ..npc_mana_schema import validate
from ..combat_costs import mana_reference
from .combat.actor_state import read, _write


def capacity(owner):
    rank = max(0, min(len(REALMS)-1, int(read(owner, 'realm_index', read(owner, 'target_realm_index', 0)))))
    if not rank:
        return 0.
    # Same intrinsic foundation as canonical_intrinsic_mp; do not fabricate
    # player-only elixirs, soul bindings, roots or immortal veins for an NPC.
    return mana_reference(REALMS[rank].base_power,max(1,int(read(owner,'layer',1))),
                          max(0,int(read(owner,'body_training',0) or 0)))


def prepare(owner, now=None):
    old = validate(read(owner, 'ordinary_mana'))
    cap, world = capacity(owner), read(owner, 'world', '')
    if old is None:
        ledger = dict(capacity=cap, current=cap, at=now, world=world)
    else:
        current = old['current']
        if now is not None and old['at'] is not None:
            if now < old['at']:
                raise ValueError('人物普通法力时钟不能倒退')
            if old['world'] == world and read(owner, 'alive', True):
                current += min(5., now-old['at']) * old['capacity'] * .2
        # Growth increases the ceiling, never grants a free refill. An unknown
        # cross-world interval grants no recovery; the new anchor starts here.
        ledger = dict(capacity=cap, current=min(cap, current), at=now if now is not None else old['at'], world=world)
    ledger = validate(ledger)
    _write(owner, 'ordinary_mana', ledger)
    return ledger


def commit(owner, current):
    ledger = validate(read(owner, 'ordinary_mana'))
    if ledger is None:
        raise ValueError('缺少原人物普通法力账本')
    ledger['current'] = current
    _write(owner, 'ordinary_mana', validate(ledger))

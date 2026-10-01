"""Bulk exchanges preserve prices, pack sizes and unique/manual ownership."""
import pytest

from test_immortal_cultivation import prepared
from test_yaochi_governance_1511 import pool
from cultivation_life.rules import technique_copy_count
from cultivation_life.system.yaochi_system import offers, lock_price
from cultivation_life.system.immortal_system import item_quantity


def test_bulk_material_packs_charge_and_grant_exact_total(prepared):
    e, g, _ = prepared
    pool(e, g)
    offer = next(o for o in offers(g) if o['kind'] == 'item' and o['quantity'] > 1)
    before = item_quantity(g.player, offer['id'])
    age = g.player.age
    e.yaochi_action(g.id, 'buy', offer['id'], 7)
    saved = e._load(g.id)
    assert saved.yaochi_state['merit'] == 100000 - 7 * offer['price']
    assert item_quantity(saved.player, offer['id']) == before + 7 * offer['quantity']
    assert saved.player.age == age
    assert f"×{7 * offer['quantity']}" in saved.history[-1].summary


def test_bulk_locked_manual_learns_first_and_stores_every_duplicate(prepared):
    e, g, _ = prepared
    pool(e, g)
    offer = next(o for o in offers(g) if o['kind'] == 'doctrine')
    g.player.known_techniques = [t for t in g.player.known_techniques if t.id != offer['id']]
    before = technique_copy_count(g.player, offer['id'])
    e.store.save(g)
    e.yaochi_action(g.id, 'lock', offer['id'])
    saved = e._load(g.id)
    saved.player.age += 300
    e.store.save(saved)
    e.yaochi_action(g.id, 'buy', offer['id'], 4)
    saved = e._load(g.id)
    assert len([t for t in saved.player.known_techniques if t.id == offer['id']]) == 1
    assert technique_copy_count(saved.player, offer['id']) == before + 3
    assert saved.yaochi_state['merit'] == 100000 - lock_price(offer) - 4 * offer['price']
    assert offer['id'] not in saved.yaochi_state['locked_offers']
    # A second purchase of an already-known book consists entirely of copies.
    current = next(o for o in offers(saved) if o['kind'] == 'doctrine')
    from cultivation_life.models import Technique
    from cultivation_life.rules import learn_technique
    learn_technique(saved.player, Technique(**current['payload']))
    before = technique_copy_count(saved.player, current['id'])
    e.store.save(saved)
    e.yaochi_action(g.id, 'buy', current['id'], 5)
    assert technique_copy_count(e._load(g.id).player, current['id']) == before + 5


@pytest.mark.parametrize('amount', [0, -1, 1.5, True, '3', 1000001])
def test_invalid_bulk_quantity_never_charges_or_releases_lock(prepared, amount):
    e, g, _ = prepared
    pool(e, g)
    offer = offers(g)[0]
    e.yaochi_action(g.id, 'lock', offer['id'])
    before = e.store.load(g.id).to_dict()
    with pytest.raises(ValueError, match='整数'):
        e.yaochi_action(g.id, 'buy', offer['id'], amount)
    assert e.store.load(g.id).to_dict() == before


def test_insufficient_bulk_balance_preserves_entire_order_and_lock(prepared):
    e, g, _ = prepared
    pool(e, g)
    offer = offers(g)[0]
    e.yaochi_action(g.id, 'lock', offer['id'])
    before = e.store.load(g.id).to_dict()
    with pytest.raises(ValueError, match='功勋不足'):
        e.yaochi_action(g.id, 'buy', offer['id'], 1000000)
    assert e.store.load(g.id).to_dict() == before


def test_unique_body_manual_and_single_commission_reject_bulk(prepared):
    e, g, _ = prepared
    pool(e, g)
    manual = next(o for o in offers(g) if o['kind'] == 'body_manual')
    e._load(g.id)  # normalize the newly selected market before the transaction
    before = e.store.load(g.id).to_dict()
    with pytest.raises(ValueError, match='只能兑换一份'):
        e.yaochi_action(g.id, 'buy', manual['id'], 2)
    with pytest.raises(ValueError, match='每次发布一份'):
        e.yaochi_action(g.id, 'publish', offers(g)[0]['id'], 2)
    assert e.store.load(g.id).to_dict() == before

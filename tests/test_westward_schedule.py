"""Reject conflicting real contracts atomically in either submission order."""
import copy

import pytest

from test_immortal_cultivation import prepared
from test_yaochi_westward import pool, quote, start, token
from test_earth_temple import command, build
from cultivation_life.rules import add_item
from cultivation_life.system.earth_temple import bill
from cultivation_life.system.yaochi_rules import config


def accept_commission(e, gid):
    return e.yaochi_action(gid, 'accept', config()['commissions'][0]['id'])


def reject_unchanged(e, gid, operation):
    before = copy.deepcopy(e._load(gid).to_dict())
    with pytest.raises(ValueError):
        operation()
    assert e._load(gid).to_dict() == before


def make_temple(e, gid):
    g = e._load(gid)
    add_item(g.player, 'spirit_stone', 10**12)
    for key in bill(g)['materials']:
        add_item(g.player, key, 1000)
    e.store.save(g)
    build(e, gid)


def test_commission_blocks_previously_quoted_training_without_charge(pool):
    e, gid = pool
    old = quote(e, gid)['token']
    accept_commission(e, gid)
    reject_unchanged(e, gid, lambda: e.yaochi_action(gid, 'westward_start_merit', old))
    assert quote(e, gid)['reason']
    assert e._load(gid).yaochi_state['job']['progress'] == 0


def test_training_blocks_commission_then_cancel_releases_schedule(pool):
    e, gid = pool
    start(e, gid)
    assert e.get_game(gid)['yaochi']['commission_reason']
    reject_unchanged(e, gid, lambda: accept_commission(e, gid))
    e.yaochi_action(gid, 'westward_cancel', token(e, gid))
    accept_commission(e, gid)
    assert e._load(gid).yaochi_state['job']


def test_refund_requires_physical_actor_even_with_valid_project_token(pool):
    e, gid = pool
    start(e, gid)
    old = token(e, gid)
    g = e._load(gid)
    original_spirit = copy.deepcopy(g.player.spirit_state)
    from cultivation_life.building_schema import address
    g.player.spirit_state = dict(mode='wandering', body_intact=True, entered=g.player.age,
                                deadline=g.player.age+10, address=address(g))
    e.store.save(g)
    reject_unchanged(e, gid, lambda: e.yaochi_action(gid, 'westward_cancel', old))
    assert e.get_game(gid)['yaochi']['westward']['project']['cancel_reason']
    g = e._load(gid)
    g.player.spirit_state = original_spirit
    e.store.save(g)
    e.yaochi_action(gid, 'westward_cancel', token(e, gid))
    assert e._load(gid).yaochi_state.get('westward', {}).get('project') is None


@pytest.mark.parametrize('first', ['training', 'commission', 'temple'])
def test_temple_contract_excludes_training_and_commission(pool, first):
    e, gid = pool
    make_temple(e, gid)
    if first == 'temple':
        command(e, gid, 'accept', 'watch')
        reject_unchanged(e, gid, lambda: start(e, gid))
        reject_unchanged(e, gid, lambda: accept_commission(e, gid))
    else:
        (start if first == 'training' else accept_commission)(e, gid)
        reject_unchanged(e, gid, lambda: command(e, gid, 'accept', 'watch'))

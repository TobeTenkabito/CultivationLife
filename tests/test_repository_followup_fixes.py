"""Real HTTP submit, owned parcels, canonical crossing and host-body qualification."""
import copy
import random

import pytest

from test_other_systems_audit_fixes import api, new_game, snapshot
from test_spirit_inheritance import prepared
from cultivation_life.models import SectNpc
from cultivation_life.rules import add_item
from cultivation_life.runtime import encode_rng
from cultivation_life.system.immortal_cultivation import golden_light, golden_light_rank
from test_inheritance_audit_fixes import battle


def cross(engine, game, destination, location=None):
    plan = engine._plan_world_transition(game, destination, 'rift',
        route_id=f'rift:{game.player.world}:{destination}', arrival_location=location,
        reason='test_delivery_address')
    engine._apply_world_transition(game, plan)
    engine.store.save(game)


def join(engine, act, game):
    alliance = game.merchant_state['worlds'][game.player.world][0]
    game.player.location_id = alliance['hq']
    add_item(game.player, 'spirit_stone', 10**9)
    engine.store.save(game)
    act(game.id, 'merchant-action', action='join', alliance_id=alliance['id'])
    return engine._load(game.id)


def post_working(engine, act, game, kind='supply', worker_id=None, stars=2):
    world = game.player.world
    definitions = engine._crafting_material_defs()
    payload = dict(kind=kind, stars=stars, quantity=2,
        definition_id=next(d['id'] for d in definitions.values() if d['world'] == world),
        material_category='crafting', material_tier=1, mold_id='sword')
    if kind == 'talisman':
        from cultivation_life.talisman_content import catalog
        payload['definition_id'] = next(k for k, d in catalog()[1].items() if d['world'] == world)
    if kind == 'spirit_manual':
        from cultivation_life.system.spirit_voisinage import catalog
        payload['definition_id'] = next(iter(catalog(game)))
    act(game.id, 'merchant-action', action='post', **payload)
    saved = engine._load(game.id)
    order = saved.merchant_state['posted'][-1]
    worker = worker_id or next(n.id for n in engine._all_world_npcs(saved) if n.alive and n.world == world)
    order.update(status='working', started_age=saved.player.age, finish_age=saved.player.age+1,
                 will_finish=True, worker='验收承接人', worker_id=worker, execution_stage=0)
    engine.store.save(saved)
    return saved, order['id']


@pytest.mark.parametrize('kind', ['supply', 'weapon', 'formation', 'talisman', 'spirit_manual'])
def test_crossed_delivery_retains_exact_goods_until_local_claim(api, kind):
    engine, act = api
    if kind == 'spirit_manual':
        made = engine.create_game('残解托管', 'supreme_metal', 'dao', 8712,
            custom_start=dict(world='spirit', realm_index=8, layer=1))
        game = engine._load(made['id'])
        game.pending_event = None
        game.settings['silent_events'] = True
        game.player.next_tribulation_age = None
        destination = 'true_demon'
    else:
        game = new_game(engine, realm=4)
        destination = 'demon'
    game = join(engine, act, game)
    original_world, original_location = game.player.world, game.player.location_id
    game, identity = post_working(engine, act, game, kind)
    before_ids = {r['id'] for r in game.player.crafting_materials}
    cross(engine, game, destination)
    act(game.id, 'advance', action='rest', years=1)
    finished = engine._load(game.id)
    assert finished.merchant_state['posted'][-1]['status'] == 'working'
    # Actual entry catches up the original order before moving the player.
    # Its resulting parcel stays at the issuing site until explicitly claimed.
    cross(engine, finished, original_world, original_location)
    finished = engine._load(game.id)
    cross(engine, finished, destination)
    finished = engine._load(game.id)
    order = next(row for row in finished.merchant_state['posted'] if row['id'] == identity)
    assert order['status'] == 'completed' and order['delivery_goods']
    parcel = copy.deepcopy(order['delivery_goods'])
    assert {r['id'] for r in finished.player.crafting_materials} == before_ids
    public = engine.get_game(game.id)['merchant_system']['posted'][-1]
    assert public['delivery_pending'] and not public['can_claim'] and 'delivery_goods' not in public
    frozen = snapshot(engine, game.id)
    act(game.id, 'merchant-action', action='claim', order_id=identity, status=400)
    assert engine.store._path(game.id).read_bytes() == frozen
    act(game.id, 'advance', action='rest', years=1)
    returned = engine._load(game.id)
    assert returned.merchant_state['posted'][-1]['delivery_goods'] == parcel
    cross(engine, returned, original_world, original_location)
    # A paid parcel belongs to this player even after leaving the membership.
    act(game.id, 'merchant-action', action='leave')
    before_rng = engine._load(game.id).rng_state
    act(game.id, 'merchant-action', action='claim', order_id=identity)
    received = engine._load(game.id)
    assert received.rng_state == before_rng
    claimed = received.merchant_state['posted'][-1]
    assert claimed['delivery_claimed'] and 'delivery_goods' not in claimed
    for name in ('crafting_materials','formation_materials','crafted_artifacts','formation_loadouts','talismans'):
        actual = {r['id']: r for r in getattr(received.player, name)}
        for row in parcel[name]:
            assert actual[row['id']] == row
    for row in parcel['inventory']:
        assert any(i.id == row['id'] and i.quantity >= row['quantity'] for i in received.player.inventory)
    if kind == 'spirit_manual':
        assert any(t.id == parcel['techniques'][0]['id'] for t in received.player.known_techniques)
    frozen = snapshot(engine, game.id)
    act(game.id, 'merchant-action', action='claim', order_id=identity, status=400)
    assert engine.store._path(game.id).read_bytes() == frozen


@pytest.mark.parametrize('during_work', [False, True])
def test_imprisonment_blocks_acceptance_or_refunds_current_job(api, during_work):
    engine, act = api
    game = new_game(engine, realm=4)
    add_item(game.player, 'spirit_stone', 10**9)
    engine.store.save(game)
    act(game.id, 'create-faction', name='关押验收宗')
    game = engine._load(game.id)
    worker = game.sects[game.player.faction_id].npcs[0]
    for person in engine._all_world_npcs(game):
        if person.world == 'human' and person.id != worker.id:
            person.alive = False
    game = join(engine, act, game)
    game, identity = post_working(engine, act, game, worker_id=worker.id, stars=1)
    if not during_work:
        game.merchant_state['posted'][-1].update(status='open', check_age=game.player.age+1)
        engine.store.save(game)
    act(game.id, 'intrigue-personnel', kind='sect', action='imprison', npc_id=worker.id, years=1000)
    act(game.id, 'advance', action='rest', years=1)
    saved = engine._load(game.id)
    order = saved.merchant_state['posted'][-1]
    assert engine._intrigue_is_imprisoned(saved, worker.id)
    if during_work:
        assert order['status'] == 'failed' and order['refund_principal'] == order['principal']
        assert order['refund_fee'] == (order['fee']+1)//2
        assert not order.get('delivery_goods') and not order.get('delivery_claimed')
    else:
        assert order['status'] != 'completed' and not (order['status'] == 'working' and order.get('worker_id') == worker.id)


@pytest.mark.parametrize('original_level,host_level', [(20,0), (0,20), (20,20)])
def test_host_ward_uses_host_fact_and_original_returns_after_leave(api, original_level, host_level):
    engine, act = api
    game, _ = prepared(engine, path='ghost')
    game.player.body_training = 100
    game.player.immortal_body.update(level=original_level, golden_light_rank=5)
    original = copy.deepcopy(game.player.immortal_body)
    npc = SectNpc('ward-host-'+game.id, '宿身', '', 9, 1, 100, None, world='celestial',
        path='dao', race='human', spirit_root='supreme_metal', body_training=100 if host_level else 0,
        immortal_body_level=host_level)
    game.notable_npcs[npc.id] = npc
    game.player.prisoners.append(game.detain_person(dict(id=npc.id, combat_power=1)))
    game.player.immortal_aperture['current'] = 0
    game.rng_state = encode_rng(random.Random(1))
    engine.store.save(game)
    act(game.id, 'captive-action', action='possess', target_id=npc.id)
    possessed = engine._load(game.id)
    assert golden_light(possessed.player) == bool(host_level)
    assert golden_light_rank(possessed.player) == (1 if host_level else 0)
    assert battle(possessed).battle.units['player'].unit.capabilities.ward_tier == (2 if host_level else 1)
    assert engine.get_game(game.id)['aperture']['suspended']
    frozen = snapshot(engine, game.id)
    act(game.id, 'aperture-action', action='refine', status=400)
    assert engine.store._path(game.id).read_bytes() == frozen
    act(game.id, 'ghost-leave-host')
    restored = engine._load(game.id)
    assert restored.player.immortal_body == original
    assert golden_light(restored.player) == bool(original_level)
    assert golden_light_rank(restored.player) == (5 if original_level else 0)
    assert restored.player.immortal_aperture['current'] == 0
    act(game.id, 'aperture-action', action='refine')
    assert engine._load(game.id).player.immortal_aperture['current'] == 250

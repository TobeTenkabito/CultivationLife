"""Real HTTP commands for rank snapshots, completed lives and local delivery."""
import copy
import random

import pytest

from test_other_systems_audit_fixes import api, new_game, snapshot
from cultivation_life.content_registry import REALMS
from cultivation_life.models import SectNpc
from cultivation_life.rules import add_item
from cultivation_life.runtime import encode_rng
from cultivation_life.system.possession_system import can_possess, enter_host_body


def captive_game(engine):
    game = new_game(engine, 'ghost', 4, 5)
    game.player.opportunity = 321
    npc = SectNpc('host-' + game.id, '宿身', '', 3, 1, 20, 900, path='dao', race='human', spirit_root='supreme_metal')
    game.notable_npcs[npc.id] = npc
    game.player.prisoners.append(game.detain_person(dict(id=npc.id, combat_power=1)))
    game.rng_state = encode_rng(random.Random(1))
    engine.store.save(game)
    return game, npc.id


@pytest.mark.parametrize('restriction', ['suppressed', 'sealed'])
@pytest.mark.parametrize('entry', ['captive-action', 'ghost-constraint', 'post-battle-possession'])
def test_every_possession_entry_rejects_rank_restore_states_atomically(api, restriction, entry):
    engine, act = api
    game, target = captive_game(engine)
    if restriction == 'suppressed':
        act(game.id, 'secret-art', art='suppress', action='activate', realm_index=3, layer=1)
        game = engine._load(game.id)
    else:
        game.player.sealed_cultivation = dict(realm_index=8, layer=1, lifespan=9000,
            return_world='spirit', suppressed_world='human', upper_world='spirit', lower_world='human')
    if entry == 'ghost-constraint':
        game.player.ghost_captor = copy.deepcopy(game.player.prisoners[0])
    elif entry == 'post-battle-possession':
        game.player.alive = False
        game.player.death_reason = '普通战斗陨落'
        game.pending_event = dict(id='SYS_POST_BATTLE_POSSESSION', version=1, title='战陨夺舍',
            body='', choices=[dict(id=target, text='夺舍', enabled=True)], runtime=dict(prisoner_ids=[target]))
    engine.store.save(game)
    frozen = snapshot(engine, game.id)
    payload = dict(action='possess') if entry == 'ghost-constraint' else dict(target_id=target, action='possess')
    result = act(game.id, entry, status=400, **payload)
    assert '压制' in result['error'] if restriction == 'suppressed' else '封印' in result['error']
    assert engine.store._path(game.id).read_bytes() == frozen
    restored = engine._load(game.id)
    before = copy.deepcopy(restored.player.to_dict())
    assert not can_possess(restored.player, restored.player.prisoners[0])[0]
    with pytest.raises(ValueError):
        enter_host_body(restored.player, restored.player.prisoners[0])
    assert restored.player.to_dict() == before


def test_release_suppression_then_possess_and_leave_preserves_true_rank(api):
    engine, act = api
    game, target = captive_game(engine)
    act(game.id, 'secret-art', art='suppress', action='activate', realm_index=3, layer=1)
    frozen = snapshot(engine, game.id)
    assert not engine.get_game(game.id)['demonic_system']['prisoners'][0]['can_possess']
    act(game.id, 'captive-action', target_id=target, action='possess', status=400)
    assert engine.store._path(game.id).read_bytes() == frozen
    act(game.id, 'secret-art', art='suppress', action='cancel')
    # This case verifies rank restoration, not a random possession loss.
    # Hydration after the restored rank may consume the market RNG; establish
    # the intended successful draw at the actual attempt boundary.
    prepared = engine._load(game.id)
    prepared.rng_state = encode_rng(random.Random(1))
    engine.store.save(prepared)
    act(game.id, 'captive-action', target_id=target, action='possess')
    possessed = engine._load(game.id)
    assert possessed.player.ghost_host_body
    assert possessed.player.ghost_core_state['realm_index'] == 4
    frozen = snapshot(engine, game.id)
    act(game.id, 'secret-art', status=400, art='suppress', action='activate', realm_index=1, layer=1)
    assert engine.store._path(game.id).read_bytes() == frozen
    act(game.id, 'ghost-leave-host')
    final = engine._load(game.id).player
    assert (final.realm_index, final.layer, final.opportunity) == (4, 5, 321)
    assert final.cultivation_suppression is None
    assert final.possession_count == 1


def test_saved_old_suppressed_host_must_leave_before_restoring_original_rank(api):
    engine, act = api
    game, target = captive_game(engine)
    act(game.id, 'secret-art', art='suppress', action='activate', realm_index=3, layer=1)
    game = engine._load(game.id)
    suppression = copy.deepcopy(game.player.cultivation_suppression)
    # Schema10 state the old unrestricted possession command could save.
    game.player.cultivation_suppression = None
    host = game.player.prisoners.pop()
    enter_host_body(game.player, host)
    game.player.cultivation_suppression = suppression
    engine.store.save(game)
    frozen = snapshot(engine, game.id)
    act(game.id, 'secret-art', status=400, art='suppress', action='cancel')
    assert engine.store._path(game.id).read_bytes() == frozen
    assert engine.get_game(game.id)['secret_arts']['suppression_block_reason']
    act(game.id, 'ghost-leave-host')
    act(game.id, 'secret-art', art='suppress', action='cancel')
    final = engine._load(game.id).player
    assert (final.realm_index, final.layer, final.opportunity) == (4, 5, 321)


def relationship_game(engine, world='human'):
    path = 'monster' if world == 'monster_realm' else 'dao'
    realm = 5 if world == 'monster_realm' else 8 if world == 'spirit' else 4
    shown = engine.create_game('关系边界验收', 'supreme_metal', path, 8712,
        monster_species_id='fox' if path == 'monster' else None,
        custom_start=dict(world=world, realm_index=realm, layer=1))
    game = engine._load(shown['id'])
    game.pending_event = None
    game.player.next_tribulation_age = None
    game.settings['silent_events'] = True
    for identity, realm, layer in [('disciple', 1, 1), ('master', 8, REALMS[8].layers), ('request', 1, 1)]:
        npc = SectNpc(identity, identity, '', realm, layer, 30, 9000, world=world, path='dao', spirit_root='supreme_metal')
        game.notable_npcs[identity] = npc
    game.player.disciples.append(game.link_relationship(dict(id='disciple')))
    game.player.master = game.link_relationship(dict(id='master'))
    game.player.disciple_requests.append(game.link_relationship(dict(id='request')))
    game.player.faction_id = next((k for k, sect in game.sects.items() if not sect.extinct and sect.world == world), None)
    game.player.faction_contribution = 10000
    add_item(game.player, 'healing_pill')
    game.rng_state = encode_rng(random.Random(1))
    engine.store.save(game)
    snapshot(engine, game.id)
    return engine._load(game.id)


@pytest.mark.parametrize('operation,payload', [
    ('faction-dispatch', dict(target='item')),
    ('disciple-request', dict(request_id='request', accept=True)),
    ('disciple-gift', dict(disciple_id='disciple', kind='item', content_id='healing_pill')),
])
def test_user_deferred_relationship_mortality_checks_preserve_prior_behavior(api, operation, payload):
    engine, act = api
    game = relationship_game(engine)
    game.player.lifespan = game.player.age
    engine.store.save(game)
    act(game.id, 'advance', action='rest', years=1)
    dead = engine._load(game.id)
    assert not dead.player.alive and dead.pending_event is None
    before = dead.player.faction_contribution
    act(game.id, operation, **payload)
    saved = engine._load(game.id)
    assert not saved.player.alive
    if operation == 'faction-dispatch':
        assert saved.player.faction_contribution < before
    elif operation == 'disciple-request':
        assert any(row['id'] == 'request' for row in saved.player.disciples)
    else:
        assert saved.player.disciples[0]['items']['healing_pill'] == 1


@pytest.mark.parametrize('operation,payload', [
    ('disciple-gift',dict(disciple_id='disciple',kind='item',content_id='healing_pill')),
    ('disciple-gift',dict(disciple_id='disciple',kind='technique',content_id='test')),
    ('master-request',dict(kind='item')), ('master-request',dict(kind='technique')), ('master-request',dict(kind='consult')),
    ('disciple-request',dict(request_id='request',accept=True)),
])
def test_real_descent_blocks_remote_delivery_without_changing_relations(api, operation, payload):
    engine, act = api
    game = relationship_game(engine, 'spirit')
    act(game.id, 'secret-art', art='suppress', action='activate', realm_index=1, layer=1)
    act(game.id, 'cross-world', destination='human')
    shown = engine.get_game(game.id)
    assert shown['player']['world'] == 'human'
    assert not shown['player']['master']['can_interact']
    assert not shown['player']['disciples'][0]['can_interact']
    assert not shown['player']['disciple_requests'][0]['can_interact']
    frozen = snapshot(engine, game.id)
    result = act(game.id, operation, status=400, **payload)
    assert '当前界面' in result['error']
    assert engine.store._path(game.id).read_bytes() == frozen


def test_real_reversible_crossing_restores_local_actions_on_return(api):
    engine, act = api
    game = relationship_game(engine, 'monster_realm')
    act(game.id, 'cross-world', destination='phantom_underworld')
    frozen = snapshot(engine, game.id)
    act(game.id, 'disciple-gift', status=400, disciple_id='disciple', kind='item', content_id='healing_pill')
    assert engine.store._path(game.id).read_bytes() == frozen
    act(game.id, 'cross-world', destination='monster_realm')
    returned = engine.get_game(game.id)
    assert b'can_interact' not in engine.store._path(game.id).read_bytes()
    assert returned['player']['master']['can_interact']
    assert returned['player']['disciples'][0]['can_interact']
    assert returned['player']['disciple_requests'][0]['can_interact']
    # Real local inventory transfer remains exact and usable after returning.
    act(game.id, 'disciple-gift', disciple_id='disciple', kind='item', content_id='healing_pill')
    saved = engine._load(game.id)
    assert saved.player.disciples[0]['items']['healing_pill'] == 1
    act(game.id, 'disciple-request', request_id='request', accept=True)
    assert len(engine._load(game.id).player.disciples) == 2


@pytest.mark.parametrize('address', ['different_world', 'different_instance', 'same_instance', 'unknown_world'])
def test_person_access_is_world_and_instance_specific(address):
    from cultivation_life.models import Player, GameState
    from cultivation_life.spatial_people import require_access
    game = GameState('geometry', 1, Player('主角', 'supreme_metal'), '', '')
    npc = SectNpc('person', '故人', '', 1, 1, 30, 200, world='spirit' if address == 'different_world' else 'human')
    if address == 'unknown_world':
        npc.world = 'unknown'
    elif address in {'different_instance', 'same_instance'}:
        game.player.world = npc.world = 'lost'
        game.spatial_state = dict(current='here',instances={'here':dict(npc_ids=['person'] if address == 'same_instance' else []), 'away':dict(npc_ids=['person'] if address == 'different_instance' else [])})
    if address == 'same_instance':
        require_access(game, npc)
    else:
        with pytest.raises(ValueError):
            require_access(game, npc)

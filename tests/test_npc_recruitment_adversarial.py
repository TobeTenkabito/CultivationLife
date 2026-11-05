"""Recruitment paths must keep one real person and recheck stale requests."""
import copy
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.engine.actions.relationships import manage_faction_relationship, respond_disciple_request
from cultivation_life.models import GameState
from cultivation_life.system.npc_development import service
from cultivation_life.system.npc_contacts import availability
from cultivation_life.spatial_people import accessible, instance_of
from test_npc_development import game


def deps(game):
    return SimpleNamespace(_load=lambda _: game, store=SimpleNamespace(save=lambda _: None),
        present=lambda g: g, _find_npc=lambda g, identity: g.world_npcs.get(identity),
        _sect_members=lambda g, s: s.npcs)


@pytest.fixture
def request_game(game):
    game.player.disciple_requests = game.player.disciples
    game.player.disciples = []
    return game


@pytest.mark.parametrize('route', ['request', 'contact'])
@pytest.mark.parametrize('attack', ['higher_rank', 'dead', 'custody', 'prison', 'duplicate',
    'companion', 'foreign_world', 'other_instance', 'assignment', 'trial', 'pending'])
def test_recruitment_rejects_stale_or_illegal_targets_atomically(request_game, route, attack):
    g = request_game; p = g.player; n = g.world_npcs['student']
    if route == 'contact': p.disciple_requests = []
    if attack == 'higher_rank': n.realm_index = p.realm_index + 1
    elif attack == 'dead': n.alive = False
    elif attack == 'custody': n.custody = dict(kind='prisoner', holder_id='another')
    elif attack == 'prison': g.intrigue_state['npc_prisons'] = {n.id: {}}
    elif attack == 'duplicate': p.disciples = [g.link_relationship({'id': n.id})]
    elif attack == 'companion': p.dao_companion = g.link_relationship({'id': n.id})
    elif attack == 'foreign_world': n.world = 'spirit'
    elif attack == 'other_instance':
        p.world = n.world = 'lost'
        g.spatial_state = dict(current='a', instances={'a': dict(npc_ids=[]), 'b': dict(npc_ids=[n.id])})
    elif attack == 'assignment':
        g.wars = [dict(id='war', strategic_war_id='deployment', status='active',
            journeys={'army': [dict(person_id=n.id, phase='outbound')]})]
    elif attack == 'trial': g.active_trial = {'kind': 'battle'}
    else: g.pending_event = {'id': 'pending'}
    before = copy.deepcopy(g.to_dict())
    with pytest.raises(ValueError):
        if route == 'request': respond_disciple_request(deps(g), g.id, n.id, True)
        else: manage_faction_relationship(deps(g), g.id, n.id, 'disciple', known_target=True)
    assert g.to_dict() == before


@pytest.mark.parametrize('value', ['false', 1, [], None])
def test_request_requires_boolean_without_consuming_letter(request_game, value):
    before = copy.deepcopy(request_game.to_dict())
    with pytest.raises(ValueError): respond_disciple_request(deps(request_game), request_game.id, 'student', value)
    assert request_game.to_dict() == before


def test_pending_request_cannot_be_recruited_twice(request_game):
    g = request_game; n = g.world_npcs['student']
    assert availability(g, n)['disciple']
    assert not availability(g, n, accepting_request=True)['disciple']
    respond_disciple_request(deps(g), g.id, n.id, True)
    assert len(g.player.disciples) == 1 and not g.player.disciple_requests
    assert g.player.disciples[0].person is n


def test_full_reserved_slots_can_accept_and_remote_acceptance_does_not_move_person(request_game):
    from cultivation_life.content_registry import WORLD_SYSTEMS
    g = request_game; n = g.world_npcs['student']; n.location_id = 'distant'
    count = int(WORLD_SYSTEMS['relationship']['max_disciples'])
    for i in range(count - 1):
        row = n.to_dict(); row['id'] = f'request-{i}'
        g.player.disciple_requests.append(g.link_relationship(row))
    respond_disciple_request(deps(g), g.id, n.id, True)
    assert n.location_id == 'distant' and len(g.player.disciple_requests) == count - 1
    with pytest.raises(ValueError, match='地点'): service.apply(g, 'npc', n.id, 'body')


@pytest.mark.parametrize('world', ['human', 'spirit', 'celestial', 'asura', 'reincarnation', 'nether', 'lost', 'rift'])
def test_generated_request_preserves_encounter_address_and_instance(tmp_path, game, world):
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path)
    game.player.disciples = []; game.player.world = world
    if world in {'lost', 'rift'}:
        game.spatial_state = dict(current='scene', instances={'scene': dict(kind=world, npc_ids=[], location_id='place')})
    result, _ = engine._effect({'type': 'gain_generated_disciple'}, game, {}, random.Random(7))
    assert result == 'disciple_requested'
    row = game.player.disciple_requests[0]; person = row.person
    assert row['location_id'] == person.location_id == game.player.location_id
    assert accessible(game, person)
    if world in {'lost', 'rift'}: assert instance_of(game, person.id) == 'scene'
    loaded = GameState.from_dict(game.to_dict())
    assert loaded.player.disciple_requests[0].person.location_id == 'place'
    assert 'location_id' not in loaded.player.disciple_requests[0].reference()


def test_relationship_address_always_reads_original_person(game):
    n = game.world_npcs['student']; row = game.player.disciples[0]
    n.location_id = 'moved'
    assert row['location_id'] == 'moved'
    loaded = GameState.from_dict(game.to_dict())
    assert loaded.player.disciples[0]['location_id'] == 'moved'


@pytest.mark.parametrize('world', ['human', 'lost'])
def test_cached_encounter_keeps_birth_address_when_promoted_later(tmp_path, game, world):
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path)
    game.player.world = world
    if world == 'lost':
        game.spatial_state = dict(current='scene', instances={'scene': dict(kind=world, npc_ids=[], location_id='place')})
    target = dict(combat_type='cultivator', target_name='偶遇修士', members=[dict(realm_index=2, layer=1, power=100, race='human')])
    engine._cache_encounter_target(game, target, random.Random(11))
    identity = target['members'][0]['npc_id']
    if world == 'lost':
        assert game.notable_npcs[identity].location_id == 'place'
        assert not game.encounter_npc_cache
    else:
        assert game.encounter_npc_cache[0]['npc']['location_id'] == 'place'
    game.player.location_id = 'later-place'
    npc = engine._promote_cached_npc(game, identity, '师徒之请')
    assert npc.location_id == 'place' and npc.world == world
    assert not game.encounter_npc_cache
    if world == 'lost': assert instance_of(game, identity) == 'scene'


@pytest.mark.parametrize('world', ['human', 'lost'])
def test_generated_household_uses_source_person_address_not_player(game, world):
    from unittest.mock import patch
    from cultivation_life.system.npc_social import instantiate_social
    n = game.world_npcs['student']; n.world = world
    game.player.location_id = 'distant-player'
    if world == 'lost':
        game.spatial_state = dict(current='other', instances={'scene': dict(kind='lost', npc_ids=[n.id])})
    with patch('cultivation_life.system.npc_social.social_hint', return_value=dict(companion_name='家眷', concubine_count=0)):
        instantiate_social(game, n)
    partner = game.notable_npcs['partner_student']
    assert partner.location_id == n.location_id == 'place'
    if world == 'lost': assert instance_of(game, partner.id) == 'scene'


def test_disciple_pill_discount_uses_original_relation_and_is_consumed_once(game):
    from cultivation_life.rules import add_item
    from cultivation_life.content_registry import ITEM_CATALOG
    pill = next(i for i in ITEM_CATALOG.values() if 'pill' in i.tags)
    relation = game.player.disciples[0]
    # A second role must not drop the disciple's original discount ledger.
    game.player.dao_companion = game.link_relationship({'id': 'student'})
    add_item(game.player, pill.id, 1)
    full = service.quote(game, 'npc', 'student', 'body')['opportunity']
    service.gift(game, 'npc', 'student', pill.id, relation=relation)
    bonus = relation['breakthrough_bonus']
    assert bonus > 0
    discounted = service.quote(game, 'npc', 'student', 'body')
    assert discounted['opportunity'] == round(full * (1 - bonus), 2)
    add_item(game.player, 'npc_training_dao_body_1', 1)
    service.apply(game, 'npc', 'student', 'body', 'material')
    assert relation['breakthrough_bonus'] == bonus
    service.apply(game, 'npc', 'student', 'body')
    assert relation['breakthrough_bonus'] == 0
    assert not hasattr(game.world_npcs['student'], 'breakthrough_bonus')


@pytest.mark.parametrize('conversion', [0, .1, .99])
def test_partial_conversion_cannot_learn_or_equip_immortal_technique(game, conversion):
    from cultivation_life.content_registry import TECHNIQUE_CATALOG
    from cultivation_life.system.npc_techniques import equipped
    book = copy.deepcopy(next(t for t in TECHNIQUE_CATALOG.values() if t.requires_immortal_power))
    # Isolate the conversion requirement from root/body prerequisites.
    from unittest.mock import patch
    book.required_body_training = 0
    game.player.known_techniques = [book]
    n = game.world_npcs['student']; n.transcendence = {'conversion': conversion}
    before = copy.deepcopy(game.to_dict())
    with patch('cultivation_life.system.npc_development.service.can_practice_technique', return_value=True):
        with pytest.raises(ValueError, match='转化'): service.teach(game, 'npc', n.id, book.id)
    assert game.to_dict() == before
    n.technique_levels[book.id] = 1; n.main_technique_id = book.id
    with patch('cultivation_life.system.npc_techniques.can_practice_technique', return_value=True):
        assert not equipped(game, n)

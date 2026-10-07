"""Single-authority people, reference persistence, and lifecycle regressions."""
import copy
import json
import random
from pathlib import Path
from unittest.mock import Mock

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Player, SectNpc, SectState
from cultivation_life.relationship_records import bind_relationships
from cultivation_life.relationship_schema import LABEL_FIELDS, PERSON_FIELDS
from cultivation_life.save_schema import SAVE_SCHEMA_VERSION, migrate_document
from cultivation_life.storage import SaveStore
from tools.check_module_dependencies import violations

ROOT = Path(__file__).resolve().parents[1]


def person(identity='person', **changes):
    return SectNpc(**(dict(id=identity, name='故人', title='', realm_index=2, layer=1,
                          age=50, lifespan=200, affinity=30.0, faction_id='old') | changes))


def state():
    npc = person()
    game = GameState('relations', 17, Player('Player', 'supreme_fire'), '', '',
                     sects={'old': SectState('old', '旧宗', npcs=[npc])})
    seed = dict(id=npc.id, name='过时姓名', realm_index=1, layer=2, age=1,
                alive=True, world='human', source='old', last_requests={'gift': 3})
    game.player.dao_companion = game.link_relationship(seed)
    return game, npc


@pytest.mark.parametrize('field,value', [('alive', False), ('world', 'spirit'), ('realm_index', 3),
    ('layer', 4), ('age', 51), ('lifespan', 300), ('name', '新姓名'), ('faction_id', 'new'),
    ('affinity', 41.0), ('main_technique_id', 'new-art')])
def test_person_changes_are_visible_without_snapshot_synchronization(field, value):
    game, npc = state()
    record = game.player.dao_companion
    setattr(npc, field, value)
    assert record[field] == value
    assert field not in record.reference()


@pytest.mark.parametrize('field,value', [('alive', False), ('world', 'celestial'),
    ('cultivation_progress', 12.5), ('affinity', 44), ('main_technique_id', 'taught-art')])
def test_relationship_writes_reach_the_same_authoritative_person(field, value):
    game, npc = state()
    game.player.dao_companion[field] = value
    assert getattr(npc, field) == value
    assert field not in dict.keys(game.player.dao_companion)


def test_reference_resolves_replaced_npc_by_id_and_preserves_relationship_metadata():
    game, _ = state()
    replacement = person(name='换宗后的同一人', world='spirit', faction_id='new')
    game.sects['old'].npcs.clear()
    game.notable_npcs[replacement.id] = replacement
    record = game.player.dao_companion
    assert record.person is replacement
    assert record['name'] == replacement.name
    assert record['world'] == 'spirit'
    assert record['last_requests'] == {'gift': 3}


def test_persistence_contains_only_reference_and_relationship_fields():
    game, npc = state()
    before = npc.to_dict()
    document = game.to_dict()
    relation = document['player']['dao_companion']
    assert relation == {'id': npc.id, 'npc_id': npc.id, 'source': 'old', 'last_requests': {'gift': 3}}
    assert not (PERSON_FIELDS | LABEL_FIELDS).intersection(relation)
    assert npc.to_dict() == before
    restored = GameState.from_dict(json.loads(json.dumps(document)))
    assert restored.player.dao_companion.person is restored.sects['old'].npcs[0]
    restored.sects['old'].npcs[0].alive = False
    assert not restored.player.dao_companion['alive']


def test_display_copy_is_detached_but_game_clone_has_its_own_authoritative_person():
    game, npc = state()
    display = copy.deepcopy(game.player.dao_companion)
    display['alive'] = False
    assert npc.alive
    assert json.loads(json.dumps(game.player.dao_companion))['name'] == npc.name
    clone = copy.deepcopy(game)
    clone.player.dao_companion['alive'] = False
    assert not clone.sects['old'].npcs[0].alive
    assert npc.alive


def test_two_roles_share_person_but_not_cooldowns():
    game, npc = state()
    game.player.disciples.append(game.link_relationship({'id': npc.id, 'last_requests': {'gift': 8}}))
    game.player.dao_companion['age'] += 1
    assert game.player.disciples[0]['age'] == npc.age == 51
    assert game.player.dao_companion['last_requests']['gift'] == 3
    assert game.player.disciples[0]['last_requests']['gift'] == 8


def test_event_person_is_persisted_once_and_survives_roundtrip():
    game, _ = state()
    seed = {'id': 'event', 'name': '事件故人', 'age': 25, 'lifespan': 90, 'realm_index': 1}
    game.player.master = game.link_relationship(seed)
    game.player.dao_friends.append(game.link_relationship(seed))
    document = game.to_dict()
    assert list(document['relationship_npcs']) == ['event']
    assert set(document['player']['master']) == {'id', 'npc_id'}
    loaded = GameState.from_dict(document)
    loaded.player.master['age'] = 26
    assert loaded.player.dao_friends[0]['age'] == 26


def test_missing_reference_rejects_instead_of_recreating_a_dead_person():
    game, _ = state()
    document = game.to_dict()
    document['sects']['old']['npcs'].clear()
    with pytest.raises(ValueError, match='身份'):
        GameState.from_dict(document)




def test_v8_save_migrates_once_and_keeps_opaque_extensions(tmp_path, monkeypatch):
    game, _ = state()
    document = game.to_dict()
    document.pop('heavens_state', None)
    document.update(version=8, opaque_mod_state={'keep': [1, 2]})
    store = SaveStore(tmp_path)
    store._path(game.id).write_text(json.dumps(document), encoding='utf-8')
    store.load(game.id)
    saved = store._path(game.id).read_bytes()
    assert json.loads(saved)['opaque_mod_state'] == {'keep': [1, 2]}
    monkeypatch.setattr(store, '_write_document', Mock(side_effect=AssertionError('Repeated migration')))
    store.load(game.id)
    assert store._path(game.id).read_bytes() == saved


def test_captive_concubine_uses_authoritative_life_and_separate_roster():
    game, npc = state()
    game.player.dao_companion = None
    captive = dict(id=npc.id, npc_id=npc.id, source='captive')
    game.player.concubines = [game.detain_person(captive, kind='concubine')]
    restored = GameState.from_dict(game.to_dict())
    assert restored.player.concubines[0].person is restored.inactive_npcs[npc.id]
    assert restored.player.concubines[0]['alive']
    assert not restored.sects['old'].npcs
    assert restored.inactive_npcs[npc.id].roster_state == 'held'


def test_party_cannot_use_stale_snapshot_to_resurrect_or_relocate_npc(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    game, npc = state()
    game.player.party = [{'id': npc.id}]
    npc.alive = False
    assert engine._sync_party_state(game)
    assert not game.player.party
    npc.alive, npc.world = True, 'spirit'
    game.player.party = [{'id': npc.id}]
    assert engine._sync_party_state(game)
    assert not game.player.party


def test_event_person_has_exactly_one_annual_tick_and_no_world_tick(tmp_path, monkeypatch):
    engine = GameEngine(ROOT, tmp_path)
    game, _ = state()
    game.player.master = game.link_relationship({'id': 'event', 'name': '师父', 'age': 20, 'lifespan': 100})
    game.player.disciples.append(game.link_relationship({'id': 'event'}))
    monkeypatch.setattr(engine, '_resolve_npc_periodic_tribulation', lambda *args: None)
    monkeypatch.setattr(engine, '_advance_npc_cultivation', lambda *args, **kwargs: None)
    engine._annual_relationship_update(game, random.Random(1))
    assert game.relationship_npcs['event'].age == 21
    assert engine._find_npc(game, 'event') is game.relationship_npcs['event']
    assert game.relationship_npcs['event'] not in engine._all_world_npcs(game)


def test_promoting_event_person_changes_roster_without_breaking_reference(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    game, _ = state()
    game.player.master = game.link_relationship({'id': 'event', 'name': '师父', 'age': 20, 'lifespan': 100})
    reference = game.player.master
    npc = engine._persist_relationship_npc(game, reference, '受邀入宗')
    assert 'event' not in game.relationship_npcs
    assert game.notable_npcs['event'] is npc is reference.person


def test_dictionary_operations_cannot_hide_facts_or_rebind_identity():
    game, npc = state()
    record = game.player.dao_companion
    record.update(age=70)
    record |= {'world': 'spirit'}
    assert record == copy.deepcopy(record)
    assert dict(record)['age'] == npc.age == 70
    assert (record | {'extra': 1})['world'] == npc.world == 'spirit'
    with pytest.raises(ValueError, match='身份'):
        record['npc_id'] = 'other'


def test_duplicate_event_registry_cannot_create_a_second_annual_owner():
    game, npc = state()
    game.relationship_npcs[npc.id] = person(age=1)
    bind_relationships(game, SectNpc)
    assert not game.relationship_npcs
    assert game.player.dao_companion.person is npc




def test_affinity_change_does_not_promote_event_person_or_spawn_social_npcs(tmp_path, monkeypatch):
    engine = GameEngine(ROOT, tmp_path)
    game, _ = state()
    game.player.master = game.link_relationship({'id': 'event', 'name': '师父', 'affinity': 25})
    spawn = Mock(side_effect=AssertionError('An affinity update must not promote a relationship'))
    monkeypatch.setattr('cultivation_life.system.npc_social.instantiate_social', spawn)
    engine._adjust_person_affinity(game, 'event', 2)
    assert game.player.master['affinity'] == 27
    assert 'event' in game.relationship_npcs and 'event' not in game.notable_npcs
    spawn.assert_not_called()


@pytest.mark.parametrize('source,target', [
    ('relationship_schema', 'models'), ('relationship_schema', 'content_registry'),
    ('relationship_records', 'engine'), ('relationship_records', 'system.npc_system'),
])
def test_relationship_foundations_do_not_import_gameplay(source, target):
    assert violations([('cultivation_life.' + source, 'cultivation_life.' + target, 1)])


@pytest.mark.parametrize('event_person', [False, True])
def test_entourage_commit_moves_each_authoritative_person_once(event_person):
    from cultivation_life.system.world_transition_system import EntourageManifest
    game, npc = state()
    if event_person:
        game.sects['old'].npcs.clear()
        game.relationship_npcs[npc.id] = npc
    record = game.player.dao_companion
    manifest = EntourageManifest(True, frozenset(), (), (), ((npc.id, True, '同行飞升'),))
    def move(actual, world, age):
        assert actual is npc
        actual.world = world
    movement = Mock(side_effect=move)
    manifest.commit(game, 'spirit', move_npc=movement)
    movement.assert_called_once_with(npc, 'spirit', game.player.age)
    assert record['world'] == npc.world == 'spirit'
    assert npc.departure_reason == '同行飞升'

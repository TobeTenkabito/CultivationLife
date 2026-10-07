"""Captivity keeps one living person while excluding free-world participation."""
import copy
import random
from pathlib import Path
from unittest.mock import Mock

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Player, SectNpc, SectState
from cultivation_life.npc_custody import is_free, kill_person, release_person, settle_puppet_person
from cultivation_life.relationship_schema import PERSON_FIELDS
from cultivation_life.save_schema import SAVE_SCHEMA_VERSION, migrate_document
from cultivation_life.system.world_transition_system import (
    WorldTransitionPlan, WorldTransitionPorts, TransitionMode, TransitionDirection,
    apply_world_transition,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def held_game(tmp_path, monkeypatch):
    engine = GameEngine(ROOT, tmp_path)
    npc = SectNpc('target', '故人', '弟子', 1, 1, 30, 200, affinity=35,
                  gender='female', faction_id='old', body_training=20)
    player = Player('主角', 'supreme_fire', path='demonic', realm_index=4)
    game = GameState('custody', 17, player, '', '',
                     sects={'old': SectState('old', '旧宗', npcs=[npc])})
    player.dao_companion = game.link_relationship(dict(id=npc.id, last_interactions={}))
    player.prisoners.append(game.detain_person(dict(id=npc.id, combat_power=1, source='combat')))
    monkeypatch.setattr(engine, '_load', lambda _: game)
    monkeypatch.setattr(engine.store, 'save', Mock())
    monkeypatch.setattr(engine, 'present', lambda g: g.to_dict())
    return engine, game, npc


def test_capture_preserves_life_identity_and_excludes_all_free_rosters(held_game):
    engine, game, npc = held_game
    assert npc.alive and npc.death_reason is None
    assert not is_free(npc) and npc.custody['kind'] == 'prisoner'
    assert game.player.dao_companion.person is game.player.prisoners[0].person is npc
    assert not game.sects['old'].npcs
    assert engine._find_npc(game, npc.id) is None
    assert npc not in engine._all_world_npcs(game)
    game.player.party = [{'id': npc.id}]
    engine._sync_party_state(game)
    assert not game.player.party
    assert not engine._public_dao_companion(game)['can_invite_party']
    assert not engine._relationship_can_join_faction(game, game.player.dao_companion)
    with pytest.raises(ValueError, match='名册'):
        engine._persist_relationship_npc(game, game.player.dao_companion, '重入江湖')


def test_actual_combat_capture_detaches_npc_without_killing(held_game):
    engine, game, npc = held_game
    release_person(game, npc.id)
    game.player.prisoners.clear()
    target = dict(target_name=npc.name, target_power=1, target_realm_index=1,
                  npc_id=npc.id, resolved_capture_ids=[npc.id])
    result, _ = engine._capture_cultivator(game, target, 10000, random.Random(1))
    assert result == 'captured'
    assert npc.alive and npc.affinity == 23
    assert game.player.prisoners[0].person is npc
    assert not game.sects['old'].npcs


def test_release_restores_same_person_and_training_and_never_revives(held_game):
    engine, game, npc = held_game
    prisoner = game.player.prisoners[0]
    prisoner['body_training'], prisoner['realm_index'] = 42, 2
    engine.captive_action(game.id, npc.id, 'release')
    assert game.sects['old'].npcs[0] is npc
    assert npc.body_training == 42 and npc.realm_index == 2 and npc.affinity == 45
    assert is_free(npc) and npc.custody is None
    assert not game.inactive_npcs and not game.player.prisoners
    game.player.prisoners.append(game.detain_person(dict(id=npc.id)))
    kill_person(game, npc.id, '真正死亡')
    with pytest.raises(ValueError):
        engine.captive_action(game.id, npc.id, 'release')
    with pytest.raises(ValueError):
        release_person(game, npc.id)
    assert not npc.alive and npc.death_reason == '真正死亡'


@pytest.mark.parametrize('destroy_group', [False, True])
def test_release_never_returns_to_wrong_world_or_extinct_faction(held_game, destroy_group):
    _, game, npc = held_game
    if destroy_group:
        game.sects['old'].extinct = True
    else:
        npc.world = 'spirit'
    release_person(game, npc.id)
    assert game.notable_npcs[npc.id] is npc
    assert npc.faction_id is None and not game.sects['old'].npcs


def test_roundtrip_and_clone_keep_one_authority_and_relationship_metadata(held_game):
    _, game, npc = held_game
    original = copy.deepcopy(npc.to_dict())
    data = game.to_dict()
    assert not PERSON_FIELDS.intersection(data['player']['prisoners'][0])
    assert npc.to_dict() == original
    for cloned in (GameState.from_dict(data), copy.deepcopy(game)):
        other = cloned.inactive_npcs[npc.id]
        assert cloned.player.prisoners[0].person is cloned.player.dao_companion.person is other
        assert other is not npc and other.alive and not is_free(other)
        cloned.player.prisoners[0]['affinity'] = -60
        assert other.affinity == -60 and npc.affinity == 35


def test_prisoner_does_not_gain_free_relationship_annual_tick(held_game, monkeypatch):
    engine, game, npc = held_game
    grow = Mock()
    monkeypatch.setattr(engine, '_advance_npc_cultivation', grow)
    engine._annual_relationship_update(game, random.Random(1))
    assert npc.age == 30
    grow.assert_not_called()


def test_captive_concubine_grows_once_then_releases_authority(held_game, monkeypatch):
    engine, game, npc = held_game
    engine.manage_concubine(game.id, npc.id, 'recruit')
    assert not game.player.prisoners
    assert npc.alive and npc.custody['kind'] == 'concubine'
    assert game.player.concubines[0].person is npc
    monkeypatch.setattr(engine, '_advance_npc_cultivation', lambda *a, **k: None)
    monkeypatch.setattr(engine, '_resolve_npc_periodic_tribulation', lambda *a, **k: None)
    engine._annual_relationship_update(game, random.Random(1))
    assert npc.age == 31
    engine.manage_concubine(game.id, npc.id, 'dismiss')
    assert is_free(npc) and npc.age == 31 and npc.affinity == 0


def test_captive_concubine_death_and_dismissal_cannot_resurrect(held_game):
    engine, game, npc = held_game
    engine.manage_concubine(game.id, npc.id, 'recruit')
    npc.lifespan = npc.age + 1
    engine._annual_relationship_update(game, random.Random(1))
    assert not npc.alive and npc.custody is None and npc.roster_state == 'retired'
    engine.manage_concubine(game.id, npc.id, 'dismiss')
    assert not npc.alive and engine._find_npc(game, npc.id) is None


@pytest.mark.parametrize('kind,roll,alive', [('corpse', 0, False), ('corpse', 1, False),
                                           ('living', 0, True), ('living', 1, True)])
def test_conversion_only_corpse_process_ends_life(held_game, kind, roll, alive):
    engine, game, npc = held_game
    result, _ = engine._convert_to_puppet(game, game.player.prisoners[0], kind,
                                         Mock(random=lambda: roll), False)
    assert npc.alive is alive
    if result == 'created':
        puppet = game.player.puppets[0]
        assert puppet['source_npc_id'] == npc.id
        assert not game.player.prisoners
        if kind == 'living':
            assert npc.custody['kind'] == 'living_puppet'
            puppet['body_training'] = 60
            engine.puppet_action(game.id, puppet['id'], 'dismiss')
            assert is_free(npc) and npc.body_training == 60
    elif kind == 'corpse':
        assert npc.roster_state == 'retired' and not game.player.prisoners
    else:
        assert npc.custody['kind'] == 'prisoner' and game.player.prisoners


@pytest.mark.parametrize('outcome', ['escape', 'devour', 'combat_death'])
def test_living_puppet_lifecycle_updates_source(held_game, outcome):
    engine, game, npc = held_game
    engine._convert_to_puppet(game, game.player.prisoners[0], 'living', Mock(random=lambda: 0), False)
    puppet = game.player.puppets[0]
    if outcome == 'escape':
        puppet['control'] = 0
        engine._annual_demonic_update(game, Mock(random=lambda: 0))
        assert is_free(npc) and not game.player.puppets
    elif outcome == 'devour':
        engine.puppet_action(game.id, puppet['id'], 'devour')
        assert not npc.alive and not game.player.puppets
    else:
        engine._apply_support_damage(game.player, [dict(id=puppet['id'], field='combat_power', after=0, destroyed=True)])
        settle_puppet_person(game, puppet, outcome='dead', reason='战斗死亡')
        assert not npc.alive
        settle_puppet_person(game, puppet, outcome='released')
        assert not npc.alive and npc.roster_state == 'retired'


def test_execution_marks_true_death_and_prevents_second_reward(held_game):
    engine, game, npc = held_game
    engine.relationship_violence(game.id, 'captive', npc.id)
    assert not npc.alive and npc.custody is None
    assert not game.player.dao_companion['alive'] and not game.player.prisoners
    fame, karma = game.player.fame, game.player.karma
    with pytest.raises(ValueError):
        engine.relationship_violence(game.id, 'companion', npc.id)
    assert (game.player.fame, game.player.karma) == (fame, karma)


def test_permanent_departure_retires_without_death(held_game):
    engine, game, npc = held_game
    engine._prepare_permanent_world_transition(game)
    assert npc.alive and npc.roster_state == 'retired' and npc.custody is None
    assert not game.player.prisoners
    loaded = GameState.from_dict(game.to_dict())
    assert loaded.inactive_npcs[npc.id].alive


def test_temporary_passage_carries_held_authority(held_game):
    _, game, npc = held_game
    p = game.player
    plan = WorldTransitionPlan(p.world, 'spirit', TransitionDirection.ASCEND, TransitionMode.PASSAGE,
                               'test', '', 'arrival', (p.realm_index, p.layer),
                               (p.realm_index, p.layer), '', None)
    moves = []
    def move(person, world, age):
        moves.append(person.id)
        person.world = world
    ports = WorldTransitionPorts(lambda g: None, lambda g: None, Mock(), move)
    apply_world_transition(game, plan, ports)
    assert moves == [npc.id] and npc.world == game.player.world == 'spirit'
    assert game.player.prisoners[0]['world'] == 'spirit'
    release_person(game, npc.id)
    assert npc.faction_id is None and game.notable_npcs[npc.id] is npc






def test_held_descendant_cannot_rejoin_family_or_tick_twice(held_game):
    engine, game, npc = held_game
    release_person(game, npc.id)
    game.player.prisoners.clear()
    game.player.offspring.append(dict(npc.to_dict(), cultivation_started=True))
    game.family = SectState('family', '家族', npcs=[npc], kind='family')
    game.player.prisoners.append(game.detain_person(dict(id=npc.id)))
    assert game.player.offspring[0]['roster_state'] == 'held'
    engine._family_register_children(game)
    assert not game.family.npcs
    engine._annual_offspring_and_family_update(game, random.Random(1))
    assert game.player.offspring[0]['age'] == npc.age == 30
    kill_person(game, npc.id, '处决')
    assert not game.player.offspring[0]['alive']






def test_prisoner_also_recorded_as_disciple_can_still_be_released(held_game):
    engine, game, npc = held_game
    game.player.disciples.append(game.link_relationship({'id': npc.id}))
    engine.captive_action(game.id, npc.id, 'release')
    assert is_free(npc) and not game.player.prisoners
    assert game.player.disciples[0].person is npc

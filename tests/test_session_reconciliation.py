"""Session repairs commit once on disk and remain stable across real reloads."""
import copy
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.engine.persistence import reconciliation
from cultivation_life.engine.transactions import request_games, request_scope
from cultivation_life.models import SectNpc
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system import spatial


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(params=['ordinary', 'spatial'])
def session(tmp_path, request):
    engine = GameEngine(ROOT, tmp_path / 'saves')
    identity = engine.create_game('读档提交验证', 'mutated_yin', 'ghost', 20261018)['id']
    if request.param == 'spatial':
        game = engine._load(identity)
        game.player.realm_index, game.player.layer = 4, 1
        game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
        target = spatial.new_rift(game, random.Random(8), engine.maps, controlled=True)
        engine.store.save(game)
        with patch.object(spatial, 'outcome_weights', return_value={'secluded': 1}):
            engine.spatial_action(identity, 'enter', {'target_id': target['id']})
    engine.get_game(identity)
    engine.get_game(identity)
    return engine, identity


def prepare_repairs(engine, identity, repair):
    game = engine.store.load(identity)
    if repair in {'captor', 'combined'}:
        npc = SectNpc('session-dead-captor', '已故拘魂者', '', 3, 1, 100, 100,
                      alive=False, death_reason='已故', world=game.player.world,
                      location_id=game.player.location_id)
        game.notable_npcs[npc.id] = npc
        game.player.ghost_captor = dict(id=npc.id, npc_id=npc.id, name=npc.name,
            realm_index=3, layer=1, combat_power=10000, followed_years=0,
            controlled_form='拘魂', source='defeat_capture', location_id=npc.location_id)
    if repair in {'field', 'combined'}:
        game.player.spirit_field.update(reclaimed_qing=1)
        game.player.spirit_field.pop('owner', None)
        game.player.spirit_field.pop('settled_year', None)
    if repair in {'parade', 'combined'}:
        engine._ensure_ghost_parade(game, random.Random(17))
        # An active external parade can also remain archived on the player while
        # visiting an instance. Its original world is never changed on load.
        if not game.ghost_parade:
            game.ghost_parade = dict(world='human', status='dormant', announced=False)
        for key in ('settled_year', 'realm_index', 'unit_years'):
            game.ghost_parade.pop(key, None)
    engine.store.save(game)
    return game.to_dict()


@pytest.mark.parametrize('repair', ['captor', 'field', 'parade', 'combined'])
def test_view_commits_repairs_once_and_fresh_engine_reads_the_same_state(session, repair):
    engine, identity = session
    before = prepare_repairs(engine, identity, repair)
    with patch.object(engine.store, 'save', wraps=engine.store.save) as save:
        shown = engine.get_game(identity)
    save.assert_called_once()
    saved = engine.store.load(identity).to_dict()
    expected = copy.deepcopy(before)
    if repair in {'captor', 'combined'}:
        assert shown['ghost_system']['phase_two']['captor'] is None
        expected['player']['ghost_captor'] = None
        assert saved['history'][-1]['event_id'] == 'SYS_GHOST_CAPTOR_DIED'
        expected['history'].append(saved['history'][-1])
    if repair in {'field', 'combined'}:
        field = expected['player']['spirit_field']
        field['owner'] = dict(world=before['player']['world'],
            location_id=before['player']['location_id'],
            instance_id=before['spatial_state'].get('current')
                        if before['player']['world'] in {'lost', 'rift'} else None)
        field['settled_year'] = before['player']['age']
    if repair in {'parade', 'combined'}:
        expected['ghost_parade'].update(settled_year=before['player']['age'],
            realm_index=before['player']['realm_index'],
            unit_years=int(WORLD_SYSTEMS['time_units'][str(before['player']['realm_index'])]))
    # Everything else, including all people, resources, calendars and RNG, stays
    # byte-for-byte equivalent in the decoded structure-10 document.
    assert saved == expected
    original_bytes = engine.store._path(identity).read_bytes()
    replacement = GameEngine(ROOT, engine.store.directory)
    with patch.object(replacement.store, 'save', wraps=replacement.store.save) as save:
        replacement.get_game(identity)
        replacement.get_game(identity)
    save.assert_not_called()
    assert replacement.store._path(identity).read_bytes() == original_bytes


@pytest.mark.parametrize('failure', ['reconciliation', 'save'])
def test_failed_final_reconciliation_or_save_leaves_disk_and_request_cache_clean(session, failure):
    engine, identity = session
    prepare_repairs(engine, identity, 'combined')
    game = engine.store.load(identity)
    game.player.sage_effects = {'outdated': 1.0}
    engine.store.save(game)
    original = engine.store._path(identity).read_bytes()
    original_prepare = reconciliation.prepare_reconciliation

    def fail_after_repairs(game):
        original_prepare(game)
        raise RuntimeError('Interrupted final reconciliation')

    context = (patch.object(reconciliation, 'prepare_reconciliation', side_effect=fail_after_repairs)
               if failure == 'reconciliation' else patch.object(Path, 'replace', side_effect=OSError('Disk unavailable')))
    with request_scope(engine), context:
        with pytest.raises((RuntimeError, OSError)):
            engine.get_game(identity)
        assert request_games(engine) == {}
    assert engine.store._path(identity).read_bytes() == original
    assert not list(engine.store.directory.glob('*.tmp'))
    with patch.object(engine.store, 'save', wraps=engine.store.save) as save:
        engine.get_game(identity)
    save.assert_called_once()
    saved = engine.store.load(identity)
    assert saved.player.ghost_captor is None
    assert saved.player.sage_effects == {}
    assert sum(row.event_id == 'SYS_GHOST_CAPTOR_DIED' for row in saved.history) == 1


@pytest.mark.parametrize('repair', ['sage', 'natal', 'attachment'])
def test_preparation_changes_commit_without_event_or_final_reconciliation_changes(session, repair):
    engine, identity = session
    game = engine.store.load(identity)
    if repair == 'sage':
        game.player.sage_effects = {'outdated': 1.0}
    elif repair == 'natal':
        game.natal_artifact = dict(crafted_artifact_id='missing-artifact', item_id='missing-artifact')
    else:
        game.player.ghost_attachment = dict(item_id='missing-vessel')
    engine.store.save(game)
    rng, age, world = game.rng_state, game.player.age, game.player.world
    with patch.object(engine.store, 'save', wraps=engine.store.save) as save:
        engine.get_game(identity)
    save.assert_called_once()
    saved = engine.store.load(identity)
    assert saved.player.sage_effects == {}
    assert saved.natal_artifact == {}
    assert saved.player.ghost_attachment is None
    assert (saved.rng_state, saved.player.age, saved.player.world) == (rng, age, world)
    with patch.object(engine.store, 'save', wraps=engine.store.save) as save:
        engine.get_game(identity)
    save.assert_not_called()

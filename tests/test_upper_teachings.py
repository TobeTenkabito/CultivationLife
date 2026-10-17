import copy
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.content_registry import TECHNIQUE_CATALOG, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.rules import add_technique_copy
from cultivation_life.system.buddhist_wish import nirvana_target
from cultivation_life.system.sage_system import sage_config
from fixtures.upper_teachings_release import prepare_upper_teachings, WORLDS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def engine(tmp_path):
    return GameEngine(ROOT, tmp_path / 'saves')


def ready(engine, world, path):
    made = engine.create_game('上界修持', 'supreme_wood', path, 2143, preset_id='core')
    return prepare_upper_teachings(engine, made['id'], world, path)


@pytest.mark.parametrize('world', WORLDS)
def test_buddhist_upper_retains_wish_but_rejects_nirvana(engine, world):
    game = ready(engine, world, 'buddhist')
    game.player.opportunity = 12345
    engine.store.save(game)
    assert nirvana_target(engine, game)[0] is None
    with pytest.raises(ValueError):
        engine.buddhist_action(game.id, 'nirvana')
    saved = engine._load(game.id)
    assert (saved.player.realm_index, saved.player.layer) == (9, 1)
    assert saved.buddhist_state['wish']['value'] == 100
    assert saved.buddhist_state['wish']['nirvana_units'] == 0
    assert saved.player.immortal_veins['9'] == 27
    assert saved.player.opportunity == 12345
    assert saved.active_trial is None


@pytest.mark.parametrize('world', WORLDS)
def test_upper_schools_lazily_adopt_old_version_two_state(engine, world):
    game = ready(engine, 'celestial', 'confucian')
    game.sage_state['worlds'].pop('celestial')
    old = copy.deepcopy(game.sage_state)
    game.player.world = world
    game.player.location_id = engine.maps.default_location(world)
    rng = game.rng_state
    engine._ensure_sage_state(game)
    assert set(game.sage_state['worlds']) == {'human', 'spirit', world}
    assert all(game.sage_state['worlds'][k] == v for k, v in old['worlds'].items())
    first = copy.deepcopy(game.sage_state)
    engine._ensure_sage_state(game)
    assert game.sage_state == first and game.rng_state == rng
    engine.store.save(game)
    doctrine = game.sage_state['worlds'][world]['doctrines'][0]
    shown = engine.sage_doctrine_action(game.id, 'join', {'doctrine_id': doctrine['id']})
    assert shown['sage_system']['membership_id'] == doctrine['id']
    assert shown['sage_system']['teaching_available']
    saved = engine._load(game.id)
    engine._prepare_sage_action(saved, 'sage_answer')
    before = saved.player.opportunity
    engine._advance_sage_year(saved, random.Random(1))
    assert saved.player.opportunity > before
    assert saved.sage_state['action_result']['years'] == 1
    assert len(saved.sage_state['worlds'][world]['doctrines']) <= 5


@pytest.mark.parametrize('world', WORLDS)
def test_outer_king_upper_retains_rewards_but_rejects_advance(engine, world):
    game = ready(engine, world, 'confucian')
    assert engine._outer_cost('advance', game.player) == 0
    with pytest.raises(ValueError, match='上界'):
        engine.sage_outer_king(game.id, 'advance')
    saved = engine._load(game.id)
    assert saved.player.haoran_exp == 1_000_000
    assert saved.active_trial is None and saved.player.layer == 1
    before = saved.player.opportunity
    engine.sage_outer_king(game.id, 'opportunity')
    saved = engine._load(game.id)
    assert saved.player.opportunity > before
    assert saved.player.haoran_exp == 1_000_000 - 150
    engine.sage_outer_king(game.id, 'combat')
    assert engine._load(game.id).player.outer_king_fixed_combat_power > 0


@pytest.mark.parametrize('world', WORLDS)
@pytest.mark.parametrize('source', [9, 10, 11])
def test_upper_major_cannot_bypass_base_progression(engine, world, source):
    game = ready(engine, world, 'confucian')
    game.player.realm_index, game.player.layer = source, 9
    engine.store.save(game)
    with pytest.raises(ValueError, match='上界'):
        engine.sage_outer_king(game.id, 'advance')
    saved = engine._load(game.id)
    assert saved.active_trial is None
    assert saved.player.haoran_exp == 1_000_000
    assert saved.player.realm_index == source


@pytest.mark.parametrize('path', ['buddhist', 'confucian'])
@pytest.mark.parametrize('gate', ['conversion', 'veins', 'sealed', 'suppressed', 'captor', 'trapped'])
def test_upper_gate_rejection_is_atomic(engine, path, gate):
    game = ready(engine, 'celestial', path)
    if gate == 'conversion': game.player.immortal_power_converted = False
    if gate == 'veins': game.player.immortal_veins = {}
    if gate == 'sealed': game.player.sealed_cultivation = {'return_world': 'celestial', 'suppressed_world': 'human'}
    if gate == 'suppressed': game.player.cultivation_suppression = {'realm_index': 9, 'layer': 1}
    if gate == 'captor': game.player.ghost_captor = 'test-captor'
    if gate == 'trapped': game.guixu_state['player_session'] = {'trapped': True}
    engine.store.save(game)
    file = engine.store.directory / (game.id + '.json')
    before = file.read_bytes()
    # The crafted custody snapshots are intentionally not persistence-repair
    # fixtures. Test the command transaction against this authoritative snapshot.
    with patch.object(engine, '_load', return_value=game), pytest.raises(ValueError):
        if path == 'buddhist': engine.buddhist_action(game.id, 'nirvana')
        else: engine.sage_outer_king(game.id, 'advance')
    assert file.read_bytes() == before


@pytest.mark.parametrize('grade', [9, 10, 11, 12])
def test_upper_classics_real_grade_exact_gain_and_duplicate_guard(engine, grade):
    game = ready(engine, 'nether', 'confucian')
    game.player.inventory.clear()
    art = next(t for t in TECHNIQUE_CATALOG.values() if t.grade == grade)
    add_technique_copy(game.player, copy.deepcopy(art), level=2)
    manual = next(i for i in game.player.inventory if i.technique_id == art.id)
    engine.store.save(game)
    view = engine._public_inner_outer(game)['manuals'][0]
    assert view['origin_realm_index'] == grade
    gain = 20 * 2 ** (grade - 1)
    assert view['gain'] == gain
    engine.sage_refine_manual(game.id, manual.id)
    saved = engine._load(game.id)
    assert saved.player.haoran_exp == 1_000_000 + gain
    add_technique_copy(saved.player, copy.deepcopy(art), level=2)
    manual = next(i for i in saved.player.inventory if i.technique_id == art.id)
    engine.store.save(saved)
    with pytest.raises(ValueError, match='不能重复'):
        engine.sage_refine_manual(game.id, manual.id)


def test_sage_dlc_off_does_not_adopt_or_mutate_upper_school(engine):
    game = ready(engine, 'celestial', 'confucian')
    game.sage_state['worlds'].pop('celestial')
    before = copy.deepcopy(game.sage_state)
    with patch.dict(sage_config(), enabled=False):
        engine._ensure_sage_state(game)
        engine._advance_sage_year(game, random.Random(1))
        assert game.sage_state == before
    engine._ensure_sage_state(game)
    assert len(game.sage_state['worlds']['celestial']['doctrines']) == 1


@pytest.mark.parametrize('path', ['buddhist', 'confucian'])
def test_major_boundary_and_final_cap(engine, path):
    game = ready(engine, 'celestial', path)
    game.player.realm_index, game.player.layer = 12, 9
    assert nirvana_target(engine, game)[0] is None
    assert engine._outer_advance_block_reason(game)
    game.player.realm_index = 8
    assert engine._outer_target(game.player) is None
    game.player.realm_index = 9
    if path == 'buddhist':
        assert nirvana_target(engine, game)[0] is None
    else:
        assert '上界' in engine._outer_advance_block_reason(game)


def test_sage_memberships_stay_in_original_world(engine):
    game = ready(engine, 'celestial', 'confucian')
    first = game.sage_state['worlds']['celestial']['doctrines'][0]
    engine.sage_doctrine_action(game.id, 'join', {'doctrine_id': first['id']})
    game = engine._load(game.id)
    game.player.world = 'nether'
    game.player.location_id = engine.maps.default_location('nether')
    engine._ensure_sage_state(game)
    assert engine._player_doctrine(game) is None
    before = copy.deepcopy(game.sage_state['worlds']['celestial'])
    engine._advance_sage_year(game, random.Random(1))
    player = next(m for m in game.sage_state['worlds']['celestial']['doctrines'][0]['members'] if m.get('is_player'))
    old = next(m for m in before['doctrines'][0]['members'] if m.get('is_player'))
    assert player['inner'] == old['inner'] and player['frozen']
    loaded = GameState.from_dict(game.to_dict())
    loaded.player.world = 'celestial'
    assert engine._player_doctrine(loaded)['id'] == first['id']


@pytest.mark.parametrize('world', WORLDS)
def test_upper_assembly_real_three_stage_clock_and_saved_event(engine, world):
    game = ready(engine, world, 'buddhist')
    art = next(t for t in game.player.known_techniques if t.path == 'buddhist')
    age = game.player.age
    unit = WORLD_SYSTEMS['time_units']['9']
    shown = engine.buddhist_action(game.id, 'start', technique=art.id)
    original = copy.deepcopy(engine.store.load(game.id).pending_event)
    engine.get_game(game.id)
    assert engine.store.load(game.id).pending_event == original
    for stage in range(3):
        assert shown['buddhist_system']['assembly']['stage'] == stage
        assert shown['pending_event']['id'].startswith('EVT_DHARMA_')
        shown = engine.choose(game.id, shown['pending_event']['choices'][0]['id'])
        if stage < 2:
            shown = engine.buddhist_action(game.id, 'continue')
    saved = engine.store.load(game.id)
    assert saved.buddhist_state['assembly'] is None
    assert saved.player.age == age + 3 * unit
    assert saved.player.world == world


@pytest.mark.parametrize('world', WORLDS)
def test_upper_temple_cost_and_local_ownership(engine, world):
    game = ready(engine, world, 'buddhist')
    before = engine._spirit_stones(game.player)
    shown = engine._public_buddhist(game)
    assert shown['temple_cost'] == 1500 * 20 ** 2
    engine.buddhist_action(game.id, 'temple')
    saved = engine._load(game.id)
    assert engine._spirit_stones(saved.player) == before - shown['temple_cost']
    temple = saved.buddhist_state['worlds'][world]['sites'][saved.player.location_id]
    assert temple['temple'] == 1
    saved.player.world = 'spirit'
    saved.player.location_id = engine.maps.default_location('spirit')
    assert engine._public_buddhist(saved)['site']['temple'] == 0
    assert saved.buddhist_state['worlds'][world]['sites'][game.player.location_id] == temple


@pytest.mark.parametrize('world', WORLDS)
@pytest.mark.parametrize('path', ['buddhist', 'confucian'])
def test_upper_breakthrough_and_tribulation_passives_remain_active(engine, world, path):
    from cultivation_life.system.path_modifiers import modifier
    game = ready(engine, world, path)
    engine._refresh_sage_effects(game)
    if path == 'buddhist':
        assert modifier(game.player, 'breakthrough_base_bonus', 0) == .05
        assert modifier(game.player, 'thunder_damage_reduction', 0) == .1
    else:
        assert game.player.sage_effects['breakthrough_bonus'] == .03
        assert game.player.sage_effects['heavenly_tribulation_reduction'] == .12
    assert engine._tribulation_damage_reduction(game.player) > 0


@pytest.mark.parametrize('world', WORLDS)
def test_upper_debate_uses_current_school_member_rank_and_path(engine, world):
    game = ready(engine, world, 'confucian')
    doctrine = game.sage_state['worlds'][world]['doctrines'][0]
    engine.sage_doctrine_action(game.id, 'join', {'doctrine_id': doctrine['id']})
    game = engine._load(game.id)
    member = game.sage_state['worlds'][world]['doctrines'][0]['members'][0]
    member['layer'] = 4
    engine.store.save(game)
    targets = []
    def combat(game, target, lethal, rng):
        targets.append(copy.deepcopy(target))
        assert lethal is False
        return 'victory', '论辩胜出'
    with patch.object(engine, '_combat', side_effect=combat):
        engine.sage_debate(game.id, doctrine['id'], member['id'])
    assert targets[0]['target_layer'] == 4
    assert targets[0]['path'] == 'confucian' and targets[0]['world'] == world
    with pytest.raises(ValueError, match='再次'):
        engine.sage_debate(game.id, doctrine['id'], member['id'])

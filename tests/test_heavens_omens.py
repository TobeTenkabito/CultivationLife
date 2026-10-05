"""Low-rank perceptions share actual-century windows without granting higher powers."""
import copy
from dataclasses import replace
from unittest.mock import patch

import pytest

from test_heavens_m1 import local, issue
from cultivation_life.models import GameState
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system.heavens import operations, omens
from cultivation_life.system.heavens.calendar import year_step, YearContext
from cultivation_life.system.heavens.schema import validate_state


@pytest.fixture
def site(local):
    engine, game, deps = local
    p = game.player
    p.world, p.location_id, p.realm_index = 'human', 'wudi_plain', 2
    p.immortal_power_converted = False
    p.hp, p.mp = max_hp(p), max_mp(p)
    game.settings['silent_events'] = True
    return engine, game, deps


def advance(site, count):
    _, game, deps = site
    for _ in range(count):
        year_step(deps, game, YearContext(game.heavens_state['runtime']['last_year_key']+1))


def discovered(site):
    # Fixed full-century fixture. The RNG draw itself is tested independently below.
    advance(site, 100)
    if not omens.get(site[1], 'stone_resonance'):
        omens.discover(site[2], site[1], 'stone_resonance')
    site[0].store.save(site[1])
    return site


@pytest.mark.parametrize('rank', [0, 1, 2, 3, 4, 5, 6, 7, 8])
def test_real_century_perception_probability_and_old_rng_untouched(site, rank):
    from hashlib import sha256
    engine, game, deps = site
    game.player.realm_index = rank
    # Find a reproducible success in the least probable supported tier (2%).
    game.seed = next(seed for seed in range(1000) if int.from_bytes(sha256(f'{seed}:heavens:perception:v1:0'.encode()).digest()[:8], 'big') / 2**64 < .02)
    before = game.rng_state
    advance(site, 99)
    runtime = game.heavens_state['runtime']
    assert 'omens' not in runtime and runtime['rng_counter'] == 0
    advance(site, 1)
    assert set(runtime['omens']) == {'stone_resonance'}
    assert runtime['rng_counter'] == 1 and game.rng_state == before
    assert not runtime['pause_requested']
    assert game.player.world == 'human' and not game.player.formation_materials
    assert 'ruins' not in runtime and runtime['sea_echo'] is None
    validate_state(game.heavens_state)


def test_closed_generation_missing_candidate_and_duplicate_window_do_not_redraw(site):
    _, game, deps = site
    game.player.location_id = 'not-a-candidate'
    advance(site, 100)
    assert game.heavens_state['runtime']['rng_counter'] == 0
    game.player.location_id = 'wudi_plain'
    year_step(deps, game, YearContext(100))
    assert game.heavens_state['runtime']['rng_counter'] == 0
    game.heavens_state['generation_enabled'] = False
    advance(site, 100)
    assert game.heavens_state['runtime']['rng_counter'] == 0
    game.heavens_state['generation_enabled'] = True
    year_step(deps, game, YearContext(200))
    assert game.heavens_state['runtime']['rng_counter'] == 0


def test_real_local_study_records_knowledge_no_rewards_or_entry_bypass(site):
    engine, game, deps = discovered(site)
    start = engine.store.load(game.id)
    result = issue(site, 'omen_study', target='stone_resonance')
    saved = engine.store.load(game.id)
    assert result['status'] == 'completed'
    assert saved.player.age == start.player.age+2
    assert omens.get(saved, 'stone_resonance')['studied']
    assert saved.player.opportunity == start.player.opportunity
    assert saved.player.formation_materials == start.player.formation_materials
    assert saved.player.mp == start.player.mp
    assert not saved.heavens_state['runtime']['notifications']
    assert 'ruins' not in saved.heavens_state['runtime']
    view = operations.view(deps, game.id, 'known', 'stone_resonance')
    assert view['omens'][0]['anomaly_id'] == 'causal_ruins' and view['omens'][0]['finding']
    with pytest.raises(ValueError): operations.preview(deps, game.id, 'ruins_enter', 'causal_ruins', {})
    with pytest.raises(ValueError, match='重复'): issue(site, 'omen_study', target='stone_resonance')
    assert GameState.from_dict(saved.to_dict()).to_dict() == saved.to_dict()


def test_cooldown_expiry_saved_knowledge_and_no_duplicate_notice(site):
    engine, game, deps = discovered(site)
    runtime = game.heavens_state['runtime']
    runtime['notifications'].clear()
    advance(site, 100)
    assert omens.candidates(deps, game) == []
    advance(site, 1)
    # Still inside the 200-year cooldown from first contact, even after dismissal.
    assert omens.candidates(deps, game) == []
    game.player.location_id = 'not-a-candidate'
    advance(site, 500)
    assert not runtime['notifications'] and omens.get(game, 'stone_resonance')
    game.player.location_id = 'wudi_plain'
    assert omens.candidates(deps, game) == ['stone_resonance']
    engine.store.save(game)
    with pytest.raises(ValueError, match='消退'): issue(site, 'omen_study', target='stone_resonance')
    assert operations.view(deps, game.id, 'known')['omens'][0]['remaining'] == 0


def test_discovery_does_not_displace_three_pending_candidates(site):
    from cultivation_life.system.heavens.state import create_echo, visible_notice
    _, game, deps = site
    for target in ('sea_echo','asura_echo','nether_echo'):
        create_echo(deps, game, target)
        visible_notice(game, 'existing', target)
    before = copy.deepcopy(game.heavens_state['runtime']['notifications'])
    advance(site, 100)
    assert game.heavens_state['runtime']['notifications'] == before
    assert game.heavens_state['runtime']['rng_counter'] == 0


def test_paused_task_resume_cancel_and_receipt_replay(site):
    engine, game, deps = discovered(site)
    def pause(work, rng, news):
        year_step(deps, work, YearContext(work.heavens_state['runtime']['last_year_key']+1))
        return False
    state = copy.deepcopy(game.heavens_state)
    paused = (engine, game, replace(deps, advance_year=pause))
    result = issue(paused, 'omen_study', target='stone_resonance')
    assert result['status'] == 'paused' and result['progress'] == 1
    saved = engine.store._path(game.id).read_bytes()
    assert operations.command(deps, game.id, state['command_seq']+1, state['revision'], 'omen_study', 'stone_resonance', {}) == result
    assert saved == engine.store._path(game.id).read_bytes()
    issue(site, 'cancel', target=result['task_id'])
    assert not omens.get(engine.store.load(game.id), 'stone_resonance')['studied']
    result = issue(paused, 'omen_study', target='stone_resonance')
    issue(site, 'resume', target=result['task_id'])
    assert omens.get(engine.store.load(game.id), 'stone_resonance')['studied']


def test_preview_and_views_are_pure_and_do_not_invent_unseen_omens(site):
    engine, game, deps = site
    engine.store.save(game)
    assert operations.view(deps, game.id, 'known')['omens'] == []
    with pytest.raises(ValueError): operations.view(deps, game.id, 'known', 'sand_glimmer')
    with pytest.raises(ValueError): operations.preview(deps, game.id, 'omen_study', 'stone_resonance', {})
    discovered(site)
    before = engine.store._path(game.id).read_bytes()
    view = operations.view(deps, game.id, 'known')['omens'][0]
    assert view['finding'] is None and view['anomaly_id'] is None
    operations.preview(deps, game.id, 'omen_study', 'stone_resonance', {})
    assert before == engine.store._path(game.id).read_bytes()


@pytest.mark.parametrize('condition', ['moved','dead','event','custody','space'])
def test_local_study_requires_actual_eligible_presence(site, condition):
    engine, game, deps = discovered(site)
    if condition == 'moved': game.player.location_id = 'muling_desert'
    if condition == 'dead': game.player.alive = False
    if condition == 'event': game.pending_event = {'id':'test'}
    if condition == 'custody': game.player.imprisonment = {'holder_id':'test'}
    if condition == 'space': game.spatial_state['current'] = 'a-scene'
    with pytest.raises(ValueError): omens.quote(deps, game, 'omen_study', 'stone_resonance', {})


@pytest.mark.parametrize('damage', ['future','identity','definition','notification','task'])
def test_corrupt_omen_contract_rejected(site, damage):
    engine, game, deps = discovered(site)
    row = omens.get(game, 'stone_resonance')
    if damage == 'future': row['last_seen'] = 10000
    if damage == 'identity': row['id'] = 'sand_glimmer'
    if damage == 'definition': row['definition']['anomaly_id'] = 'mirror_field'
    if damage == 'notification': game.heavens_state['runtime']['notifications'][0]['id'] = 'unseen'
    if damage == 'task':
        issue(site, 'omen_study', target='stone_resonance')
        game = engine.store.load(game.id)
        game.heavens_state['runtime']['tasks'][-1]['escrow']['mp_paid'] = 10
    with pytest.raises(ValueError): validate_state(game.heavens_state)


def test_failed_save_rolls_back_study_and_actual_time(site):
    engine, game, deps = discovered(site)
    before = engine.store._path(game.id).read_bytes()
    with patch.object(engine.store, 'save', side_effect=OSError('disk full')):
        with pytest.raises(OSError): issue(site, 'omen_study', target='stone_resonance')
    assert before == engine.store._path(game.id).read_bytes()


@pytest.mark.parametrize('rank,chance', [(0,.02),(3,.02),(4,.08),(5,.12),(6,.16),(7,.24),(8,.32)])
def test_perception_threshold_matches_real_rank(site, rank, chance):
    _, game, deps = site
    game.player.realm_index = rank
    # Just above the configured threshold must fail, even for a legal candidate.
    raw = int((chance+.00001)*2**64).to_bytes(8,'big') + bytes(24)
    with patch('cultivation_life.system.heavens.calendar.sha256') as digest:
        digest.return_value.digest.return_value = raw
        advance(site, 100)
    assert game.heavens_state['runtime']['rng_counter'] == 1
    assert 'omens' not in game.heavens_state['runtime']


def test_repeated_discovery_respects_dismissal_cooldown_and_completed_knowledge(site):
    engine, game, deps = site
    game.seed = 927  # First two actual draws both below 2%.
    advance(site,100)
    runtime = game.heavens_state['runtime']
    assert len(runtime['notifications']) == 1
    runtime['notifications'].clear()
    advance(site,100)
    assert runtime['rng_counter'] == 1
    advance(site,100)
    saved = omens.get(game,'stone_resonance')
    assert saved['first_seen'] == 100 and saved['last_seen'] == 300
    assert runtime['rng_counter'] == 2 and len(runtime['notifications']) == 1
    engine.store.save(game)
    issue(site,'omen_study',target='stone_resonance')
    game = engine.store.load(game.id)
    game.heavens_state['generation_enabled'] = False
    engine.store.save(game)
    before = copy.deepcopy(omens.get(game,'stone_resonance'))
    advance((engine,game,deps),700)
    assert omens.get(game,'stone_resonance') == before
    assert not omens.candidates(deps,game)
    validate_state(game.heavens_state)


def test_dying_during_ground_study_does_not_complete_knowledge(site):
    engine, game, deps = discovered(site)
    game.player.lifespan = game.player.age+1
    engine.store.save(game)
    result = issue(site,'omen_study',target='stone_resonance')
    assert result['status'] == 'failed' and result['progress'] == 1
    assert not omens.get(engine.store.load(game.id),'stone_resonance')['studied']

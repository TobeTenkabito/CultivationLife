"""Finite mirror exploration, isolated actual time and resource ownership."""
import copy
from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

from test_heavens_m1 import local, quiet, issue
from cultivation_life.models import GameState
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system import spatial
from cultivation_life.system.heavens import operations, mirror
from cultivation_life.system.heavens.calendar import year_step, YearContext
from cultivation_life.system.heavens.schema import validate_state, validate_references
from cultivation_life.system.heavens.definitions import MIRROR_ID


@pytest.fixture
def site(local):
    engine, game, deps = local
    p = game.player
    p.world, p.location_id, p.realm_index = 'human', 'muling_desert', 4
    p.immortal_power_converted = False
    p.hp, p.mp = max_hp(p), max_mp(p)
    game.settings['silent_events'] = True
    engine.store.save(game)
    return engine, game, deps


def act(site, action, **options):
    return issue(site, action, options, target=MIRROR_ID)


def entered(site):
    act(site, 'mirror_enter')
    return site


def prepared(site):
    entered(site)
    act(site, 'mirror_probe')
    return site


def load(site):
    return site[0].store.load(site[1].id)


def test_real_peaceful_path_two_materials_record_and_stable_revisit(site):
    engine, game, deps = site
    initial = load(site)
    entered(site)
    first = load(site)
    assert first.player.world == 'rift' and first.player.age == initial.player.age
    actual = mirror.get(first)
    original_rewards = copy.deepcopy([row['reward'] for row in actual['chambers'][:2]])
    assert len({row['id'] for row in original_rewards}) == 2
    initial_cap = actual['mana_capacity']
    for action, options in [('mirror_probe', {}), *[('mirror_decipher', {'chamber': str(i)}) for i in range(3)]]:
        assert act(site, action, **options)['status'] == 'completed'
    work = load(site)
    data = mirror.get(work)
    assert work.player.age == initial.player.age + 14
    assert work.player.opportunity == initial.player.opportunity
    assert work.player.formation_materials == original_rewards
    assert data['record_acquired'] and all(row['opened'] for row in data['chambers'])
    assert data['collected_mana'] == pytest.approx(max_mp(first.player)*.05)
    assert data['stored_mana'] == data['collected_mana']
    assert data['mana_capacity'] == initial_cap
    with pytest.raises(ValueError, match='不会刷新'):
        act(site, 'mirror_decipher', chamber='0')
    snapshot = copy.deepcopy(data)
    act(site, 'mirror_leave')
    outside = load(site)
    assert (outside.player.world, outside.player.location_id) == ('human', 'muling_desert')
    assert outside.spatial_state['current'] is None
    act(site, 'mirror_enter')
    assert mirror.get(load(site)) == snapshot
    assert load(site).player.formation_materials == original_rewards
    assert GameState.from_dict(load(site).to_dict()).to_dict() == load(site).to_dict()


def test_views_previews_are_pure_and_hide_unearned_materials(site):
    engine, game, deps = site
    before = engine.store._path(game.id).read_bytes()
    v = operations.view(deps, game.id, 'known')
    assert v['mirror']['known'] is False
    assert operations.preview(deps, game.id, 'mirror_enter', MIRROR_ID, {})['years'] == 0
    assert engine.store._path(game.id).read_bytes() == before
    entered(site)
    before = engine.store._path(game.id).read_bytes()
    projection = operations.view(deps, game.id, 'known', MIRROR_ID)
    assert projection['target_id'] == MIRROR_ID and projection['records'][0]['id'] == MIRROR_ID
    view = projection['mirror']
    assert 'stored_mana' not in view
    assert all(row['reward'] is None for row in view['chambers'])
    assert operations.preview(deps, game.id, 'mirror_probe', MIRROR_ID, {})['costs']['mp'] == max_mp(load(site).player)*.05
    assert engine.store._path(game.id).read_bytes() == before


@pytest.mark.parametrize('change', ['rank', 'world', 'location', 'suppression', 'custody', 'event', 'generation'])
def test_entry_requires_real_free_local_body(site, change):
    engine, game, deps = site
    work = load(site)
    if change == 'rank': work.player.realm_index = 3
    if change == 'world': work.player.world = 'celestial'
    if change == 'location': work.player.location_id = 'wudi_plain'
    if change == 'suppression': work.player.cultivation_suppression = {'realm_index': 9, 'layer': 1}
    if change == 'custody': work.player.imprisonment = {'holder_id': 'test'}
    if change == 'event': work.pending_event = {'id': 'test'}
    if change == 'generation': work.heavens_state['generation_enabled'] = False
    with pytest.raises(ValueError):
        mirror.quote(deps, work, 'mirror_enter', MIRROR_ID, {})
    assert mirror.get(work) is None


def test_cancel_keeps_actual_mana_and_time_and_retry_cannot_collect_twice(site):
    site = quiet(site)
    engine, game, deps = entered(site)
    before = load(site)
    def pause(work, rng, news):
        year_step(deps, work, YearContext(work.heavens_state['runtime']['last_year_key']+1))
        return False
    interrupted = (engine, game, replace(deps, advance_year=pause))
    state = before.heavens_state
    response = act(interrupted, 'mirror_probe')
    saved = load(site)
    assert response['progress'] == 1 and response['status'] == 'paused'
    assert saved.player.age == before.player.age+1
    assert not mirror.get(saved)['probed']
    assert mirror.get(saved)['paid_mana'] == pytest.approx(max_mp(saved.player)*.05)
    assert operations.command(deps, game.id, state['command_seq']+1, state['revision'], 'mirror_probe', MIRROR_ID, {}) == response
    assert load(site).to_dict() == saved.to_dict()
    issue(site, 'cancel', target=response['task_id'])
    after = load(site)
    assert after.player.mp == saved.player.mp
    assert mirror.get(after)['stored_mana'] == mirror.get(saved)['stored_mana']
    assert not mirror.get(after)['probed']


def test_isolation_consumes_real_material_and_stops_only_its_connection(site):
    site = quiet(site)
    prepared(site)
    engine, game, deps = site
    work = load(site)
    material = dict(id='cut-material', material_id='human_quiet_soul_mirror', acquired_tier=4)
    work.player.formation_materials.append(material)
    engine.store.save(work)
    before = mirror.get(work)['collected_mana']
    act(site, 'mirror_isolate', chamber='0', material_id=material['id'])
    assert not load(site).player.formation_materials
    act(site, 'mirror_decipher', chamber='0')
    assert mirror.get(load(site))['collected_mana'] == before
    act(site, 'mirror_decipher', chamber='1')
    assert mirror.get(load(site))['collected_mana'] > before
    with pytest.raises(ValueError):
        act(site, 'mirror_isolate', chamber='2', material_id='missing')


def test_cancelled_construction_does_not_refund_consumed_material(site):
    site = quiet(site)
    prepared(site)
    engine, game, deps = site
    work = load(site)
    work.player.formation_materials.append(dict(id='cut', material_id='human_quiet_soul_mirror', acquired_tier=4))
    engine.store.save(work)
    def pause(work, rng, news):
        year_step(deps, work, YearContext(work.heavens_state['runtime']['last_year_key']+1))
        return False
    response = act((engine, game, replace(deps, advance_year=pause)), 'mirror_isolate', chamber='0', material_id='cut')
    issue(site, 'cancel', target=response['task_id'])
    assert not load(site).player.formation_materials
    assert not mirror.get(load(site))['chambers'][0]['isolated']


def test_guardian_snapshot_supply_is_funded_frozen_and_battle_cost_feeds_next_guardian(site):
    site = quiet(site)
    prepared(site)
    engine, game, deps = site
    def fight(work, data, chamber, rng):
        work.player.mp -= 100
        return 'defeat', '负伤退回入口', 2
    armed = (engine, game, replace(deps, fight_mirror=fight))
    before = mirror.get(load(site))['stored_mana']
    act(armed, 'mirror_assault', chamber='0')
    data = mirror.get(load(site))
    original = copy.deepcopy(data['chambers'][0]['guardian'])
    assert original['mana'] == before and original['wounds'] == 2
    assert data['stored_mana'] == 25
    assert data['chambers'][0]['opened'] is False
    act(armed, 'mirror_assault', chamber='0')
    data = mirror.get(load(site))
    assert data['chambers'][0]['guardian']['power'] == original['power']
    assert data['chambers'][0]['guardian']['mana'] == before
    assert data['stored_mana'] == 50
    act(armed, 'mirror_assault', chamber='1')
    data = mirror.get(load(site))
    assert data['chambers'][1]['guardian']['mana'] == 50
    assert data['stored_mana'] + sum(row['guardian']['mana'] for row in data['chambers'] if row['guardian']) == pytest.approx(data['collected_mana'])
    validate_state(load(site).heavens_state)


def test_mana_collection_is_bounded_and_unrelated_costs_do_not_supply(site):
    prepared(site)
    work = load(site)
    data = mirror.get(work)
    before = copy.deepcopy(data)
    work.player.mp -= 30  # An unrelated cost is deliberately outside the collection port.
    assert mirror.get(work) == before
    for _ in range(100): mirror.collect(data, 1000, 0)
    assert data['collected_mana'] == data['stored_mana'] == data['mana_capacity']
    validate_state(work.heavens_state)


def test_real_combat_has_report_actual_cost_no_cultivator_kill_or_duplicate_loot(site):
    prepared(site)
    engine, game, deps = site
    work = load(site)
    work.player.realm_index = 5
    work.player.hp, work.player.mp = max_hp(work.player), max_mp(work.player)
    engine.store.save(work)
    before = load(site)
    with patch.object(engine, '_combat', wraps=engine._combat) as combat:
        act(site, 'mirror_assault', chamber='0')
    combat.assert_called_once()
    after = load(site)
    assert after.last_combat_report['objective'] == 'repel'
    assert after.last_combat_report['enemy_roster'][0]['kind'] == 'mechanical'
    assert after.last_combat_report['result'] == 'victory'
    assert len(after.player.formation_materials) == 1
    assert after.player.fame == before.player.fame
    assert after.player.opportunity == before.player.opportunity
    data = mirror.get(after)
    assert data['collected_mana'] - mirror.get(before)['collected_mana'] == pytest.approx((before.player.mp-after.player.mp)*.25)
    with pytest.raises(ValueError, match='不会刷新'):
        act(site, 'mirror_assault', chamber='0')


@pytest.mark.parametrize('action,options', [('mirror_enter', {}), ('mirror_probe', {}), ('mirror_decipher', {'chamber': '0'}), ('mirror_assault', {'chamber': '1'}), ('mirror_leave', {})])
def test_whole_command_rollback_on_save_failure(site, action, options):
    engine, game, deps = site
    if action == 'mirror_probe': entered(site)
    elif action != 'mirror_enter': prepared(site)
    before = engine.store._path(game.id).read_bytes()
    with patch.object(engine.store, 'save', side_effect=OSError('disk full')):
        with pytest.raises(OSError): act(site, action, **options)
    assert engine.store._path(game.id).read_bytes() == before


def test_independent_space_no_external_clocks_or_random_exploration(site):
    engine, game, deps = entered(site)
    before = load(site)
    npc_ages = {key: npc.age for key, npc in before.world_npcs.items()}
    with patch.object(engine, '_advance_auction_clock', wraps=engine._advance_auction_clock) as auction, patch.object(engine, '_annual_world_npc_update', wraps=engine._annual_world_npc_update) as npcs:
        act(site, 'mirror_probe')
        act(site, 'mirror_decipher', chamber='0')
    auction.assert_not_called()
    npcs.assert_not_called()
    assert {key: npc.age for key, npc in load(site).world_npcs.items()} == npc_ages
    for action in ('open', 'explore', 'enter', 'descend', 'move'):
        with pytest.raises(ValueError, match='诸天'):
            engine.spatial_action(game.id, action, {})
    with pytest.raises(ValueError, match='机关'):
        spatial.explore(load(site), Mock())


def test_event_at_preparation_boundary_does_not_start_combat_until_resumed(site):
    site = quiet(site)
    prepared(site)
    engine, game, deps = site
    def pause(work, rng, news):
        year_step(deps, work, YearContext(work.heavens_state['runtime']['last_year_key']+1))
        work.pending_event = {'id': 'test-event'}
        return False
    fight = Mock(return_value=('victory', '机关已解除', 0))
    response = act((engine, game, replace(deps, advance_year=pause, fight_mirror=fight)), 'mirror_assault', chamber='0')
    assert response['progress'] == 1 and response['status'] == 'paused'
    fight.assert_not_called()
    work = load(site)
    work.pending_event = None
    engine.store.save(work)
    issue((engine, game, replace(deps, fight_mirror=fight)), 'resume', target=response['task_id'])
    fight.assert_called_once()
    assert mirror.get(load(site))['chambers'][0]['opened']


@pytest.mark.parametrize('damage', ['capacity', 'supply', 'reward', 'record', 'scene', 'task', 'trace'])
def test_corrupt_anomaly_is_rejected(site, damage):
    prepared(site)
    work = load(site)
    data = mirror.get(work)
    if damage == 'capacity': data['collected_mana'] = data['mana_capacity'] + 1
    if damage == 'supply': data['stored_mana'] += 1
    if damage == 'reward': work.player.formation_materials.append(copy.deepcopy(data['chambers'][0]['reward']))
    if damage == 'record': data['record_acquired'] = True
    if damage == 'scene': work.spatial_state['instances'].clear()
    if damage == 'task': work.heavens_state['runtime']['tasks'][-1]['chamber'] = 3
    if damage == 'trace': data['traces'][-1]['year'] = 999999
    with pytest.raises(ValueError):
        validate_state(work.heavens_state)
        validate_references(work)


def test_generation_off_preserves_existing_instance_and_material_definition_snapshot(site):
    prepared(site)
    engine, game, deps = site
    work = load(site)
    work.heavens_state['generation_enabled'] = False
    snapshot = copy.deepcopy(mirror.get(work)['chambers'][0]['reward'])
    engine.store.save(work)
    act(site, 'mirror_leave')
    act(site, 'mirror_enter')
    act(site, 'mirror_decipher', chamber='0')
    assert load(site).player.formation_materials == [snapshot]


def test_death_during_research_does_not_award_or_refund_mana(site):
    entered(site)
    engine, game, deps = site
    work = load(site)
    work.player.lifespan = work.player.age + 1
    before = work.player.mp
    engine.store.save(work)
    result = act(site, 'mirror_probe')
    after = load(site)
    assert result['status'] == 'failed' and result['progress'] == 1
    assert not after.player.alive and after.player.mp < before
    assert not mirror.get(after)['probed'] and not after.player.formation_materials


def test_ordinary_training_is_not_sixfold_and_does_not_feed_mirror(site):
    from cultivation_life.engine.actions import exploration
    entered(site)
    engine, game, deps = site
    work = load(site)
    work.player.opportunity = 0
    engine.store.save(work)
    before = copy.deepcopy(mirror.get(work))
    with patch.object(engine, '_advance_world_year', return_value=False), patch.object(exploration, 'opportunity_multiplier', return_value=1), patch.dict(exploration.ACTIONS, {'cultivate': {'name': '修炼', 'opportunity': [100, 100]}}):
        engine.advance(game.id, 'cultivate', 1)
    assert load(site).player.opportunity == 100
    assert mirror.get(load(site)) == before


def test_orphaned_scene_cannot_be_loaded_as_an_exitless_space(site):
    entered(site)
    work = load(site)
    work.heavens_state = {}
    with pytest.raises(ValueError, match='缺少'):
        validate_references(work)

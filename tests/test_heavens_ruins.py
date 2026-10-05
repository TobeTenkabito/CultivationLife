"""Causal ruins: unique ownership, real ward outages and non-revocable evidence."""
import copy
from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

from test_heavens_m1 import local, quiet, issue
from cultivation_life.models import GameState
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system import spatial
from cultivation_life.system.heavens import operations, ruins
from cultivation_life.system.heavens.calendar import year_step, YearContext
from cultivation_life.system.heavens.definitions import RUINS_ID
from cultivation_life.system.heavens.schema import validate_state, validate_references


@pytest.fixture
def site(local):
    engine, game, deps = local
    p = game.player
    p.world, p.location_id, p.realm_index = 'human', 'wudi_plain', 4
    p.immortal_power_converted = False
    p.hp, p.mp = max_hp(p), max_mp(p)
    game.settings['silent_events'] = True
    engine.store.save(game)
    return engine, game, deps


def act(site, action, **options):
    return issue(site, action, options, target=RUINS_ID)


def load(site):
    return site[0].store.load(site[1].id)


def entered(site):
    act(site, 'ruins_enter')
    return site


def prepared(site):
    entered(site)
    act(site, 'ruins_observe')
    act(site, 'ruins_verify')
    return site


def stones(game):
    return sum(row.quantity for row in game.player.inventory if row.id == 'spirit_stone')


def test_real_peaceful_reading_is_finite_and_revisitable(site):
    start = load(site)
    prepared(site)
    initial = copy.deepcopy(ruins.get(load(site)))
    assert initial['ward']['world'] == 'demon' and initial['ward']['location_id'] == 'red_marrow_city'
    act(site, 'ruins_read')
    work = load(site)
    assert work.player.age == start.player.age+12
    assert work.player.opportunity == start.player.opportunity
    assert work.player.formation_materials == [initial['reward']]
    assert ruins.get(work)['core']['owner'] == 'ward'
    assert ruins.get(work)['record_acquired']
    with pytest.raises(ValueError, match='不会刷新'):
        act(site, 'ruins_read')
    act(site, 'ruins_contact')
    snapshot = copy.deepcopy(ruins.get(load(site)))
    act(site, 'ruins_leave')
    assert (load(site).player.world, load(site).player.location_id) == ('human', 'wudi_plain')
    act(site, 'ruins_enter')
    assert ruins.get(load(site)) == snapshot
    assert load(site).player.formation_materials == [initial['reward']]
    assert GameState.from_dict(load(site).to_dict()).to_dict() == load(site).to_dict()
    assert not load(site).wars


def test_replacement_costs_and_unique_return_transfer(site):
    site = quiet(site)
    prepared(site)
    act(site, 'ruins_read')
    before = load(site)
    material_id = before.player.formation_materials[0]['id']
    result = act(site, 'ruins_replace', material_id=material_id)
    work = load(site)
    data = ruins.get(work)
    assert result['status'] == 'completed'
    assert work.player.age == before.player.age+8
    assert stones(work) == stones(before)-500
    assert work.player.mp == pytest.approx(before.player.mp-max_mp(before.player)*.05)
    assert not work.player.formation_materials
    assert data['core']['owner'] == 'player' and data['ward']['component'] == 'replacement'
    assert data['guardian']['encounters'] == 0
    assert 'ruins_replace' in data['guardian_records']
    act(site, 'ruins_contact')
    act(site, 'ruins_return')
    data = ruins.get(load(site))
    assert data['core']['owner'] == 'ward' and data['ward']['component'] == 'core'
    for action in ('ruins_take', 'ruins_replace', 'ruins_return'):
        with pytest.raises(ValueError):
            act(site, action, **({'material_id': material_id} if action == 'ruins_replace' else {}))


def test_direct_take_real_combat_outage_then_restoration(site):
    prepared(site)
    engine, game, deps = site
    work = load(site)
    work.player.realm_index = 5
    work.player.hp, work.player.mp = max_hp(work.player), max_mp(work.player)
    engine.store.save(work)
    before = load(site)
    with patch.object(engine, '_combat', wraps=engine._combat) as combat:
        act(site, 'ruins_take')
    combat.assert_called_once()
    work = load(site)
    data = ruins.get(work)
    assert data['core']['owner'] == 'player' and data['ward']['component'] is None
    assert data['guardian']['encounters'] == 1
    assert work.last_combat_report['objective'] == 'repel'
    assert work.last_combat_report['enemy_roster'][0]['kind'] == 'mechanical'
    assert work.player.opportunity == before.player.opportunity and work.player.fame == before.player.fame
    assert 'ruins_take' in data['guardian_records']
    with pytest.raises(ValueError, match='通信中断'):
        act(site, 'ruins_contact')
    held = copy.deepcopy(data['guardian_records'])
    act(site, 'ruins_read')
    data = ruins.get(load(site))
    assert not data['sent_records']  # The remote ward cannot transmit while its component is absent.
    act(site, 'ruins_return')
    act(site, 'ruins_contact')
    data = ruins.get(load(site))
    assert data['contact_known'] and data['ward']['component'] == 'core'
    assert set(held).issubset(data['sent_records'])
    assert not load(site).wars


def test_erase_only_unread_residue_while_held_and_sent_evidence_persists(site):
    site = quiet(site)
    entered(site)
    act(site, 'ruins_observe')
    before = load(site)
    assert ruins.get(before)['local_traces'] == {'ruins_observe': 0}
    act(site, 'ruins_erase')
    assert not ruins.get(load(site))['local_traces']
    assert not ruins.get(load(site))['guardian_records']
    assert stones(load(site)) == stones(before)-300
    act(site, 'ruins_verify')
    act(site, 'ruins_read')
    data = ruins.get(load(site))
    assert data['sent_records'] and data['guardian_records']
    act(site, 'ruins_contact')  # New trace; completing erasure lets the scanner read it first.
    before = copy.deepcopy(ruins.get(load(site)))
    act(site, 'ruins_erase')
    after = ruins.get(load(site))
    assert all(after['sent_records'][key] == value for key, value in before['sent_records'].items())
    assert all(after['guardian_records'][key] == value for key, value in before['guardian_records'].items())
    assert 'ruins_contact' in after['guardian_records']
    assert not after['local_traces']


def test_pure_projection_does_not_reveal_unearned_remote_endpoint(site):
    engine, game, deps = site
    before = engine.store._path(game.id).read_bytes()
    value = operations.view(deps, game.id, 'known', RUINS_ID)
    assert not value['ruins']['known'] and not value['records']
    operations.preview(deps, game.id, 'ruins_enter', RUINS_ID, {})
    assert before == engine.store._path(game.id).read_bytes()
    entered(site)
    before = engine.store._path(game.id).read_bytes()
    value = operations.view(deps, game.id, 'known', RUINS_ID)
    assert value['target_id'] == RUINS_ID
    assert not value['ruins']['contact']
    assert 'red_marrow_city' not in str(value)
    assert 'reward' not in value['ruins']
    assert before == engine.store._path(game.id).read_bytes()


@pytest.mark.parametrize('change', ['rank', 'world', 'location', 'suppression', 'seal', 'custody', 'event', 'generation'])
def test_entry_requires_real_free_local_body(site, change):
    work = load(site)
    if change == 'rank': work.player.realm_index = 3
    if change == 'world': work.player.world = 'celestial'
    if change == 'location': work.player.location_id = 'muling_desert'
    if change == 'suppression': work.player.cultivation_suppression = {'realm_index': 9, 'layer': 1}
    if change == 'seal': work.player.sealed_cultivation = {'realm_index': 9, 'layer': 1}
    if change == 'custody': work.player.imprisonment = {'holder_id': 'test'}
    if change == 'event': work.pending_event = {'id': 'test'}
    if change == 'generation': work.heavens_state['generation_enabled'] = False
    with pytest.raises(ValueError): ruins.quote(site[2], work, 'ruins_enter', RUINS_ID, {})
    assert ruins.get(work) is None


def test_cancelled_replacement_refunds_only_unspent_stones_and_retry_is_idempotent(site):
    site = quiet(site)
    prepared(site)
    act(site, 'ruins_read')
    engine, game, deps = site
    before = load(site)
    def pause(work, rng, news):
        year_step(deps, work, YearContext(work.heavens_state['runtime']['last_year_key']+1))
        return False
    material = before.player.formation_materials[0]['id']
    interrupted = (engine, game, replace(deps, advance_year=pause))
    result = act(interrupted, 'ruins_replace', material_id=material)
    saved = load(site)
    assert result['status'] == 'paused' and result['progress'] == 1
    assert not saved.player.formation_materials
    state = before.heavens_state
    assert operations.command(deps, game.id, state['command_seq']+1, state['revision'], 'ruins_replace', RUINS_ID, {'material_id': material}) == result
    assert load(site).to_dict() == saved.to_dict()
    for action in ('ruins_leave', 'ruins_read'):
        with pytest.raises(ValueError, match='继续或取消'): act(site, action)
    issue(site, 'cancel', target=result['task_id'])
    final = load(site)
    assert stones(final) == stones(before)-500//8
    assert final.player.mp == saved.player.mp
    assert not final.player.formation_materials
    assert ruins.get(final)['core']['acquisition'] is None and ruins.get(final)['ward']['component'] == 'core'


def test_event_at_take_boundary_defers_transfer_and_combat_until_resume(site):
    site = quiet(site)
    entered(site)
    engine, game, deps = site
    def pause(work, rng, news):
        year_step(deps, work, YearContext(work.heavens_state['runtime']['last_year_key']+1))
        work.pending_event = {'id': 'test-event'}
        return False
    fight = Mock(return_value=('defeat', '你受伤退开', 2))
    result = act((engine, game, replace(deps, advance_year=pause, fight_ruins=fight)), 'ruins_take')
    assert result['progress'] == 1 and result['status'] == 'paused'
    fight.assert_not_called()
    work = load(site)
    assert ruins.get(work)['core']['owner'] == 'ward'
    work.pending_event = None
    engine.store.save(work)
    issue((engine, game, replace(deps, fight_ruins=fight)), 'resume', target=result['task_id'])
    fight.assert_called_once()
    assert ruins.get(load(site))['core']['owner'] == 'player'
    assert ruins.get(load(site))['guardian']['wounds'] == 2
    act(site, 'ruins_leave')


@pytest.mark.parametrize('action', ['ruins_enter', 'ruins_observe', 'ruins_read', 'ruins_take', 'ruins_replace', 'ruins_return', 'ruins_leave'])
def test_whole_command_save_failure_rolls_back_ownership_evidence_and_resources(site, action):
    engine, game, deps = site
    options = {}
    if action == 'ruins_observe': entered(site)
    elif action != 'ruins_enter': prepared(site)
    if action in {'ruins_replace', 'ruins_return'}:
        act(site, 'ruins_read')
        options = {'material_id': load(site).player.formation_materials[0]['id']}
    if action == 'ruins_return':
        act(site, 'ruins_replace', **options)
        options = {}
    before = engine.store._path(game.id).read_bytes()
    with patch.object(engine.store, 'save', side_effect=OSError('disk full')):
        with pytest.raises(OSError): act(site, action, **options)
    assert before == engine.store._path(game.id).read_bytes()


@pytest.mark.parametrize('damage', ['owner', 'ward', 'endpoint', 'reward', 'core_inventory', 'record', 'future', 'sent', 'scene', 'task', 'guardian'])
def test_corrupt_ownership_or_evidence_is_rejected(site, damage):
    prepared(site)
    work = load(site)
    data = ruins.get(work)
    if damage == 'owner': data['core']['owner'] = 'player'
    if damage == 'ward': data['ward']['component'] = None
    if damage == 'endpoint': data['ward']['location_id'] = 'random'
    if damage == 'reward': work.player.formation_materials.append(copy.deepcopy(data['reward']))
    if damage == 'core_inventory': work.player.formation_materials.append(dict(id=data['core']['id']))
    if damage == 'record': data['contact_known'], data['verified'] = True, False
    if damage == 'future': data['local_traces']['ruins_verify'] = 999999
    if damage == 'sent': data['sent_records']['ruins_take'] = dict(year=0, read_at=1, sent_at=5)
    if damage == 'scene': work.spatial_state['instances'].clear()
    if damage == 'task': work.heavens_state['runtime']['tasks'][-1]['duration'] = 55
    if damage == 'guardian': data['guardian']['encounters'] = 1
    with pytest.raises(ValueError):
        validate_state(work.heavens_state)
        validate_references(work)


def test_spatial_isolation_death_and_no_random_loot(site):
    entered(site)
    engine, game, deps = site
    before = load(site)
    ages = {key: npc.age for key, npc in before.world_npcs.items()}
    with patch.object(engine, '_advance_auction_clock', wraps=engine._advance_auction_clock) as auction, patch.object(engine, '_annual_world_npc_update', wraps=engine._annual_world_npc_update) as npcs:
        act(site, 'ruins_observe')
        act(site, 'ruins_read')
    auction.assert_not_called()
    npcs.assert_not_called()
    assert {key: npc.age for key, npc in load(site).world_npcs.items()} == ages
    with pytest.raises(ValueError): spatial.explore(load(site), Mock())
    work = load(site)
    work.player.lifespan = work.player.age+1
    engine.store.save(work)
    result = act(site, 'ruins_verify')
    assert result['status'] == 'failed'
    assert not load(site).player.alive and not ruins.get(load(site))['verified']


def test_generation_off_preserves_link_and_orphaned_scene_rejected(site):
    entered(site)
    engine, game, deps = site
    work = load(site)
    work.heavens_state['generation_enabled'] = False
    snapshot = copy.deepcopy(ruins.get(work))
    engine.store.save(work)
    act(site, 'ruins_leave')
    act(site, 'ruins_enter')
    assert ruins.get(load(site)) == snapshot
    work = load(site)
    work.heavens_state = {}
    with pytest.raises(ValueError, match='缺少'): validate_references(work)


def test_rejected_combat_cannot_award_free_core(site):
    entered(site)
    engine, game, deps = site
    before = engine.store._path(game.id).read_bytes()
    blocked = replace(deps, fight_ruins=Mock(return_value=('technique_blocked', '无法运转功法', 0)))
    with pytest.raises(ValueError, match='功法'):
        act((engine, game, blocked), 'ruins_take')
    assert before == engine.store._path(game.id).read_bytes()


def test_shared_task_limit_and_each_anomaly_has_distinct_reward_identity(site):
    site = quiet(site)
    entered(site)
    engine, game, deps = site
    def pause(work, rng, news):
        year_step(deps, work, YearContext(work.heavens_state['runtime']['last_year_key']+1))
        return False
    result = act((engine, game, replace(deps, advance_year=pause)), 'ruins_observe')
    with pytest.raises(ValueError, match='继续或取消'):
        issue(site, 'mirror_enter', target='mirror_field')
    issue(site, 'resume', target=result['task_id'])
    act(site, 'ruins_read')
    act(site, 'ruins_leave')
    work = load(site)
    work.player.location_id = 'muling_desert'
    engine.store.save(work)
    for action, options in [('mirror_enter', {}), ('mirror_probe', {}), ('mirror_decipher', {'chamber': '0'})]:
        issue(site, action, options, target='mirror_field')
    final = load(site)
    assert len(final.player.formation_materials) == 2
    assert len({row['id'] for row in final.player.formation_materials}) == 2
    # Fourteen actual years at rank 4 (five years per unit) leave four fifths.
    assert final.heavens_state['runtime']['unit_credit'] == {'numerator': 4, 'denominator': 5}

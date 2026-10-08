"""Four-world prepaid facilities: one authoritative clock and conserved inputs."""
import copy
from unittest.mock import patch

import pytest

from cultivation_life.models import GameState
from cultivation_life.rules import add_item, max_hp, max_mp
from cultivation_life.runtime import decode_rng, encode_rng
from cultivation_life.system.formation_system import make_formation_material_instance
from cultivation_life.system.heavens import operations, upkeep
from cultivation_life.system.heavens.calendar import YearContext, year_step
from cultivation_life.system.heavens.definitions import CONTACT_SITES
from cultivation_life.system.heavens.schema import validate_state, validate_references
from cultivation_life.system.heavens.state import get_echo, phase
from test_heavens_m1 import local, issue
from test_heavens_visits import ready as contact_ready, stones


def load(local):
    return local[0].store.load(local[1].id)


def ready(local, site=CONTACT_SITES[0]):
    game = contact_ready(local, site)
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    echo = get_echo(game.heavens_state['runtime'], site.id)
    echo['observed_cycle'] = echo['cycle']
    definition = next(d for d in local[0]._formation_material_defs().values() if d.get('world') == site.world and d.get('tier') == 9)
    material = make_formation_material_instance(definition, source='护持测试', origin_world=site.world)
    game.player.formation_materials.append(material)
    local[0].store.save(game)
    return game, material['id']


def start(local, material, target='sea_echo'):
    return issue(local, 'upkeep_start', {'material_id':material}, target=target)


def annual(local, years=1):
    game = load(local)
    rng = decode_rng(game.seed, game.rng_state)
    for _ in range(years):
        game.player.age += 1
        local[0]._advance_world_year(game, rng, [], encounters=False)
    game.rng_state = encode_rng(rng)
    local[0].store.save(game)
    return game


@pytest.mark.parametrize('site', CONTACT_SITES, ids=lambda s:s.world)
def test_all_four_worlds_finish_real_maintenance_without_new_people(local, site):
    before, material = ready(local, site)
    preview = operations.preview(local[2], before.id, 'upkeep_start', site.id, {'material_id':material})
    assert preview['years'] == 0 and preview['duration'] == 50
    assert preview['costs']['stones'] == 30000 and preview['costs']['mp'] > 0
    start(local, material, site.id)
    deployed = load(local)
    echo = get_echo(deployed.heavens_state['runtime'], site.id)
    assert echo['maintenance_started'] and not echo['maintained']
    assert deployed.player.age == before.player.age
    assert stones(deployed) == stones(before) - 30000
    assert deployed.player.mp == pytest.approx(before.player.mp-preview['costs']['mp'])
    assert material not in {m['id'] for m in deployed.player.formation_materials}
    assert deployed.heavens_state['runtime']['tasks'] == []
    # This verifies living-person clock accounting, independent of an optional
    # ruin adventure which can now kill this visitor as organization RNG changes.
    with patch.object(local[0], '_advance_guixu_calendar', return_value=False):
        during = annual(local, 17)
    row = get_echo(during.heavens_state['runtime'], site.id)['upkeep']
    assert row['progress'] == 17 and row['escrow']['spent'] == 10200
    with patch.object(local[0], '_advance_guixu_calendar', return_value=False):
        done = annual(local, 33)
    echo = get_echo(done.heavens_state['runtime'], site.id)
    assert echo['upkeep']['status'] == 'completed' and echo['maintained']
    assert echo['upkeep']['escrow']['spent'] == 30000 and echo['upkeep']['escrow']['refunded'] == 0
    assert phase(done.heavens_state['runtime'], echo)[2] == 1800
    assert set(done.world_npcs) == set(before.world_npcs)
    assert done.world_npcs[echo['visitor_id']].age == before.world_npcs[echo['visitor_id']].age + 50
    assert echo['project_stones'] == get_echo(before.heavens_state['runtime'], site.id)['project_stones']
    assert echo['application'] is None and echo['reward_claimed'] == 0
    assert GameState.from_dict(done.to_dict()).to_dict() == done.to_dict()
    with pytest.raises(ValueError, match='维护'):
        issue(local, 'maintain', {'material_id':material}, target=site.id)


@pytest.mark.parametrize('years', [0, 1, 17])
def test_cancel_refunds_only_unused_funding_and_cannot_redeploy(local, years):
    before, material = ready(local)
    start(local, material)
    annual(local, years)
    issue(local, 'upkeep_cancel')
    done = load(local)
    row = get_echo(done.heavens_state['runtime'])['upkeep']
    assert row['status'] == 'cancelled'
    assert row['escrow']['spent'] == years * 600
    assert row['escrow']['refunded'] == 30000 - years * 600
    assert stones(done) == stones(before) - years * 600
    assert done.player.formation_materials == []
    assert get_echo(done.heavens_state['runtime'])['maintenance_started']
    with pytest.raises(ValueError): issue(local, 'upkeep_cancel')
    with pytest.raises(ValueError, match='一次'): start(local, material)


def test_old_personal_maintenance_reserves_the_same_quota(local):
    game, material = ready(local)
    get_echo(game.heavens_state['runtime'])['maintenance_started'] = True
    local[0].store.save(game)
    with pytest.raises(ValueError, match='名额'): start(local, material)


def test_ordinary_years_away_continue_and_cancellation_is_available_remotely(local):
    _, material = ready(local)
    start(local, material)
    game = load(local)
    game.player.world, game.player.location_id = 'asura', 'destruction_sea'
    game.heavens_state['generation_enabled'] = False
    local[0].store.save(game)
    game = annual(local, 2)
    assert get_echo(game.heavens_state['runtime'])['upkeep']['progress'] == 2
    issue(local, 'upkeep_cancel')
    assert get_echo(load(local).heavens_state['runtime'])['upkeep']['escrow']['refunded'] == 28800


def test_spatial_years_freeze_funding_but_real_deadline_still_closes_it(local):
    before, material = ready(local)
    start(local, material)
    game = load(local)
    game.player.world, game.player.location_id, game.player.realm_index = 'human', 'muling_desert', 4
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    local[0].store.save(game)
    issue(local, 'mirror_enter', target='mirror_field')
    issue(local, 'mirror_probe', target='mirror_field')
    game = load(local)
    row = get_echo(game.heavens_state['runtime'])['upkeep']
    assert row['progress'] == 0 and row['escrow']['spent'] == 0
    game.heavens_state['runtime'].update(processed_years=1199, last_year_key=1199)
    local[0].store.save(game)
    issue(local, 'mirror_decipher', {'chamber':'0'}, target='mirror_field')
    done = load(local)
    row = get_echo(done.heavens_state['runtime'])['upkeep']
    assert row['status'] == 'expired' and row['progress'] == 0
    assert row['escrow']['refunded'] == 30000
    assert stones(done) == stones(before)
    assert not get_echo(done.heavens_state['runtime'])['maintained']


@pytest.mark.parametrize('target,location', [('mirror_field','muling_desert'), ('causal_ruins','wudi_plain')])
def test_explicit_remote_facility_view_inside_anomaly_and_cancellation(local, target, location):
    _, material = ready(local)
    start(local, material)
    game = load(local)
    game.player.world, game.player.location_id, game.player.realm_index = 'human', location, 4
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    local[0].store.save(game)
    issue(local, 'mirror_enter' if target == 'mirror_field' else 'ruins_enter', target=target)
    before = local[0].store._path(game.id).read_bytes()
    assert operations.view(local[2], game.id, 'known')['target_id'] == target
    view = operations.view(local[2], game.id, 'known', 'sea_echo')
    assert view['target_id'] == 'sea_echo' and view['upkeep']['status'] == 'active'
    assert next(a for a in view['upkeep']['actions'] if a['action'] == 'upkeep_cancel')['enabled']
    assert local[0].store._path(game.id).read_bytes() == before
    issue(local, 'upkeep_cancel')
    done = load(local)
    assert done.player.world == 'rift'
    assert get_echo(done.heavens_state['runtime'])['upkeep']['escrow']['refunded'] == 30000


def test_death_before_world_settlement_refunds_without_one_extra_year(local):
    _, material = ready(local)
    start(local, material)
    game = load(local)
    game.player.lifespan = game.player.age + 1
    local[0].store.save(game)
    dead = annual(local)
    row = get_echo(dead.heavens_state['runtime'])['upkeep']
    assert not dead.player.alive and row['status'] == 'failed'
    assert row['progress'] == 0 and row['escrow']['refunded'] == 30000


def test_same_year_replay_and_ended_facility_do_not_repeat_effects(local):
    _, material = ready(local)
    start(local, material)
    game = load(local)
    upkeep.year_step(local[2], game)
    before = copy.deepcopy(get_echo(game.heavens_state['runtime'])['upkeep'])
    upkeep.year_step(local[2], game)
    assert get_echo(game.heavens_state['runtime'])['upkeep'] == before
    year_step(local[2], game, YearContext(1))
    local[0].store.save(game)
    done = annual(local, 49)
    row = copy.deepcopy(get_echo(done.heavens_state['runtime'])['upkeep'])
    assert get_echo(annual(local).heavens_state['runtime'])['upkeep'] == row


@pytest.mark.parametrize('offset,allowed', [(1149, True), (1150, False), (1200, False)])
def test_deployment_must_finish_before_known_deadline(local, offset, allowed):
    game, material = ready(local)
    game.heavens_state['runtime'].update(processed_years=offset, last_year_key=offset)
    local[0].store.save(game)
    if allowed:
        start(local, material)
        done = annual(local, 50)
        assert get_echo(done.heavens_state['runtime'])['maintained']
    else:
        with pytest.raises(ValueError, match='窗口'): start(local, material)


def test_completed_facility_cannot_carry_maintenance_to_next_cycle(local):
    _, material = ready(local)
    start(local, material)
    game = annual(local, 50)
    game.heavens_state['runtime'].update(processed_years=1999, last_year_key=1999)
    local[0].store.save(game)
    changed = annual(local)
    echo = get_echo(changed.heavens_state['runtime'])
    assert echo['cycle'] == 1 and not echo['maintained'] and not echo['maintenance_started']
    assert phase(changed.heavens_state['runtime'], echo)[2] == 1200
    assert echo['upkeep']['status'] == 'completed'
    assert not upkeep.project(local[2], changed, 'sea_echo')['effective']


@pytest.mark.parametrize('missing', ['evidence', 'observation', 'money', 'mana', 'material', 'location', 'seal'])
def test_deployment_gates_do_not_reserve_inputs(local, missing):
    game, material = ready(local)
    echo = get_echo(game.heavens_state['runtime'])
    if missing == 'evidence': echo['exchanged'] = echo['correspondence_completed'] = False
    if missing == 'observation': echo['observed_cycle'] = -1
    if missing == 'money': next(i for i in game.player.inventory if i.id == 'spirit_stone').quantity = 1
    if missing == 'mana': game.player.mp = 0
    if missing == 'material': game.player.formation_materials = []
    if missing == 'location': game.player.location_id = 'elsewhere'
    if missing == 'seal': game.player.sealed_cultivation = {'realm_index': 9, 'layer': 1}
    local[0].store.save(game)
    before = local[0].store._path(game.id).read_bytes()
    with pytest.raises(ValueError): start(local, material)
    assert local[0].store._path(game.id).read_bytes() == before


def test_queries_and_command_retry_preserve_budget_and_material(local):
    game, material = ready(local)
    before = game.to_dict()
    for _ in range(3):
        operations.project(game, 'known', 'sea_echo', deps=local[2])
        operations.preview(local[2], game.id, 'upkeep_start', 'sea_echo', {'material_id':material})
    assert game.to_dict() == before
    result = start(local, material)
    saved = local[0].store._path(game.id).read_bytes()
    assert operations.command(local[2], game.id, result['command_seq'], game.heavens_state['revision'],
                              'upkeep_start', 'sea_echo', {'material_id':material}) == result
    assert local[0].store._path(game.id).read_bytes() == saved


@pytest.mark.parametrize('kind', ['spent', 'refunded', 'progress', 'effect', 'material', 'duplicate', 'deadline'])
def test_corrupt_facility_rejected(local, kind):
    _, material = ready(local)
    start(local, material)
    game = annual(local)
    echo = get_echo(game.heavens_state['runtime'])
    row = echo['upkeep']
    if kind == 'spent': row['escrow']['spent'] += 1
    if kind == 'refunded': row['escrow']['refunded'] = 1
    if kind == 'progress': row['progress'] += 1
    if kind == 'effect': echo['maintained'] = True
    if kind == 'material': row['material']['origin_world'] = 'human'
    if kind == 'duplicate': game.player.formation_materials.append(copy.deepcopy(row['material']))
    if kind == 'deadline': game.heavens_state['runtime'].update(processed_years=1200, last_year_key=1200)
    with pytest.raises(ValueError):
        validate_state(game.heavens_state)
        validate_references(game)


def test_deployment_save_failure_rolls_back_all_inputs(local, monkeypatch):
    game, material = ready(local)
    before = local[0].store._path(game.id).read_bytes()
    def fail(work):
        assert get_echo(work.heavens_state['runtime'])['upkeep']['material']['id'] == material
        assert not work.player.formation_materials
        raise OSError('disk full')
    monkeypatch.setattr(local[0].store, 'save', fail)
    with pytest.raises(OSError): start(local, material)
    assert local[0].store._path(game.id).read_bytes() == before


def test_completion_save_failure_does_not_publish_paid_years_or_maintenance(local, monkeypatch):
    game, material = ready(local)
    start(local, material)
    engine = local[0]
    engine._load(game.id)
    engine._load(game.id)
    before = engine.store._path(game.id).read_bytes()
    def fail(work):
        assert get_echo(work.heavens_state['runtime'])['upkeep']['status'] == 'completed'
        assert get_echo(work.heavens_state['runtime'])['maintained']
        raise OSError('disk full')
    monkeypatch.setattr(engine.store, 'save', fail)
    with pytest.raises(OSError): engine.advance(game.id, 'rest', 1)
    assert engine.store._path(game.id).read_bytes() == before


def test_four_facilities_share_one_world_year_without_npc_duplication(local):
    game = load(local)
    add_item(game.player, 'spirit_stone', 100000)
    local[0].store.save(game)
    for site in CONTACT_SITES:
        _, material = ready(local, site)
        start(local, material, site.id)
    before = load(local)
    after = annual(local)
    assert set(after.world_npcs) == set(before.world_npcs)
    for site in CONTACT_SITES:
        assert get_echo(after.heavens_state['runtime'], site.id)['upkeep']['escrow']['spent'] == 600

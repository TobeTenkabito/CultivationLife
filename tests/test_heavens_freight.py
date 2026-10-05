"""Finite real cargo, authoritative carrier, project money and retry conservation."""
import copy
from dataclasses import replace
from unittest.mock import Mock

import pytest

from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.models import GameState, SectNpc
from cultivation_life.npc_custody import detain_person, release_person
from cultivation_life.runtime import decode_rng
from cultivation_life.person_assignments import research_assignment
from cultivation_life.system.heavens import operations, missions
from cultivation_life.system.heavens.definitions import CONTACT_SITES, VISIT_DESTINATIONS, default_site
from cultivation_life.system.heavens.schema import validate_state, validate_references
from cultivation_life.system.heavens.state import get_echo
from test_heavens_m1 import local, issue
from test_heavens_missions import prepared, wait
from test_heavens_visits import stones
from test_heavens_upper_worlds import MATERIALS


def ready(local, site=CONTACT_SITES[0]):
    prepared(local, site)
    issue(local, 'mission_start', target=site.id)
    game = wait(local, 8, site.id)
    material = dict(id='original-freight-material', material_id=MATERIALS[CONTACT_SITES.index(site)],
                    name='托运的原阵材', acquired_tier=9, origin_world=site.world, base_value=5000)
    game.player.formation_materials.append(material)
    local[0].store.save(game)
    return game


def start(local, site=CONTACT_SITES[0]):
    return issue(local, 'freight_start', {'material_id': 'original-freight-material'}, target=site.id)


@pytest.mark.parametrize('site', CONTACT_SITES, ids=lambda site: site.world)
def test_actual_four_world_delivery_and_return(local, site):
    before = ready(local, site)
    engine, original, deps = local
    identity = get_echo(before.heavens_state['runtime'], site.id)['visitor_id']
    disk = engine.store._path(original.id).read_bytes()
    quote = operations.preview(deps, original.id, 'freight_start', site.id, {'material_id': 'original-freight-material'})
    assert quote['project_cost'] == 7000
    operations.project(before, 'known', site.id, deps=deps)
    assert engine.store._path(original.id).read_bytes() == disk
    result = start(local, site)
    assert operations.command(deps, original.id, result['command_seq'], before.heavens_state['revision'],
                              'freight_start', site.id, {'material_id': 'original-freight-material'}) == result
    underway = wait(local, 1, site.id)
    assert not underway.player.formation_materials
    assert underway.world_npcs[identity].world == site.world
    assert engine._find_npc(underway, identity) is None
    assert research_assignment(underway, identity)['cargo_owner'] == 'carrier'
    assert get_echo(underway.heavens_state['runtime'], site.id)['project_stones'] == 4500
    arrived = wait(local, 1, site.id)
    cargo = get_echo(arrived.heavens_state['runtime'], site.id)['freight']
    destination = default_site(VISIT_DESTINATIONS[site.id])
    assert arrived.world_npcs[identity].world == destination.world
    assert cargo['cargo_owner'] == 'destination' and cargo['delivered'] and not cargo['claimed']
    assert stones(arrived) == stones(before)
    issue(local, 'freight_collect', target=site.id)
    returned = wait(local, 2, site.id)
    cargo = get_echo(returned.heavens_state['runtime'], site.id)['freight']
    assert cargo['status'] == 'completed' and cargo['spent'] == 4000 and cargo['refunded'] == 0
    assert cargo['material'] == before.player.formation_materials[0]
    assert returned.world_npcs[identity].world == site.world
    assert returned.world_npcs[identity].age == before.world_npcs[identity].age+4
    assert returned.player.age == before.player.age+4 and stones(returned) == stones(before)+3000
    assert returned.player.opportunity == before.player.opportunity
    assert set(returned.world_npcs) == set(before.world_npcs)
    assert GameState.from_dict(returned.to_dict()).to_dict() == returned.to_dict()
    with pytest.raises(ValueError, match='一次'):
        start(local, site)
    with pytest.raises(ValueError, match='没有'):
        issue(local, 'freight_collect', target=site.id)


def test_cancel_stores_original_locally_and_refunds_only_project(local):
    before = ready(local)
    start(local)
    wait(local, 1)
    issue(local, 'freight_cancel')
    engine, initial, _ = local
    saved = engine.store.load(initial.id)
    echo = get_echo(saved.heavens_state['runtime'])
    assert echo['freight']['refunded'] == 6000 and echo['project_stones'] == 10500
    assert not saved.player.formation_materials and stones(saved) == stones(before)
    saved.player.location_id = 'celestial_city'
    engine.store.save(saved)
    with pytest.raises(ValueError):
        issue(local, 'freight_collect')
    saved.player.location_id = 'law_sea'
    engine.store.save(saved)
    issue(local, 'freight_collect')
    saved = engine.store.load(initial.id)
    assert saved.player.formation_materials == before.player.formation_materials
    assert get_echo(saved.heavens_state['runtime'])['freight']['cargo_owner'] == 'player'
    with pytest.raises(ValueError):
        issue(local, 'freight_collect')


@pytest.mark.parametrize('after_delivery', [False, True])
def test_carrier_death_keeps_real_goods_and_reward_history(local, after_delivery):
    before = ready(local)
    start(local)
    game = wait(local, 2 if after_delivery else 1)
    engine, initial, _ = local
    echo = get_echo(game.heavens_state['runtime'])
    game.world_npcs[echo['visitor_id']].alive = False
    engine.store.save(game)
    saved = wait(local, 1)
    cargo = get_echo(saved.heavens_state['runtime'])['freight']
    assert cargo['status'] == 'failed'
    assert cargo['cargo_owner'] == ('destination' if after_delivery else 'lost')
    assert cargo['refunded'] == (2000 if after_delivery else 6000)
    assert not saved.player.formation_materials
    if after_delivery:
        issue(local, 'freight_collect')
        assert stones(engine.store.load(initial.id)) == stones(before)+3000
    else:
        with pytest.raises(ValueError):
            issue(local, 'freight_collect')


@pytest.mark.parametrize('field,value', [('civilian_material_capacity', 0), ('research_visitors', False), ('enabled', False), ('source', 'human')])
def test_civilian_permit_is_separate_and_pauses_without_spending(local, monkeypatch, field, value):
    ready(local)
    start(local)
    route = next(r for r in WORLD_SYSTEMS['world_transition_routes'] if r['id']=='study:celestial:reincarnation')
    monkeypatch.setitem(route, field, value)
    saved = wait(local, 1)
    cargo = get_echo(saved.heavens_state['runtime'])['freight']
    assert cargo['elapsed'] == cargo['spent'] == 0
    issue(local, 'freight_cancel')
    assert get_echo(local[0].store.load(local[1].id).heavens_state['runtime'])['freight']['refunded'] == 7000


def test_save_failure_rolls_back_goods_funds_and_identity(local):
    before = ready(local)
    engine, initial, deps = local
    disk = engine.store._path(initial.id).read_bytes()
    broken = replace(deps, get_store=lambda: Mock(save=Mock(side_effect=OSError('disk full'))))
    with pytest.raises(OSError):
        start((engine, initial, broken))
    assert engine.store._path(initial.id).read_bytes() == disk
    assert engine.store.load(initial.id).player.formation_materials == before.player.formation_materials


@pytest.mark.parametrize('key,value', [('spent', 1000), ('claimed', True), ('cargo_owner', 'destination'),
                                     ('progress', 2), ('delivered', True), ('refunded', 1), ('last_year', 999999)])
def test_corrupt_freight_refused(local, key, value):
    ready(local)
    start(local)
    game = local[0].store.load(local[1].id)
    get_echo(game.heavens_state['runtime'])['freight'][key] = value
    with pytest.raises(ValueError):
        validate_state(game.heavens_state)


def test_inventory_cannot_duplicate_cargo_even_after_delivery(local):
    ready(local)
    start(local)
    game = wait(local, 2)
    cargo = get_echo(game.heavens_state['runtime'])['freight']
    game.player.formation_materials.append(copy.deepcopy(cargo['material']))
    with pytest.raises(ValueError, match='重复所有权'):
        validate_references(game)


def test_duplicate_year_callback_does_not_spend_or_age_twice(local):
    ready(local)
    start(local)
    game = local[0].store.load(local[1].id)
    local[2].advance_researchers(game)
    once = copy.deepcopy(game.heavens_state)
    local[2].advance_researchers(game)
    assert game.heavens_state == once


def test_captivity_preserves_cargo_until_actual_release(local):
    ready(local)
    start(local)
    engine, initial, _ = local
    game = wait(local, 1)
    identity = get_echo(game.heavens_state['runtime'])['visitor_id']
    detain_person(game, {'id': identity}, SectNpc)
    engine.store.save(game)
    game = wait(local, 2)
    cargo = get_echo(game.heavens_state['runtime'])['freight']
    assert cargo['spent'] == 1000 and cargo['cargo_owner'] == 'carrier'
    with pytest.raises(ValueError, match='恢复自由'):
        issue(local, 'freight_cancel')
    release_person(game, identity)
    engine.store.save(game)
    game = wait(local, 3)
    assert get_echo(game.heavens_state['runtime'])['freight']['status'] == 'completed'


def test_isolation_freezes_cargo_and_disabled_generation_keeps_it(local):
    ready(local)
    start(local)
    engine, initial, _ = local
    game = engine.store.load(initial.id)
    before = copy.deepcopy(get_echo(game.heavens_state['runtime'])['freight'])
    game.player.world = 'rift'
    engine._advance_world_year(game, decode_rng(game.seed, game.rng_state), [], encounters=False)
    assert get_echo(game.heavens_state['runtime'])['freight'] == before
    game = engine.store.load(initial.id)
    game.heavens_state['generation_enabled'] = False
    engine.store.save(game)
    assert get_echo(wait(local, 4).heavens_state['runtime'])['freight']['status'] == 'completed'


def test_delivery_save_failure_does_not_lose_goods_or_repeat_payment(local, monkeypatch):
    ready(local)
    start(local)
    wait(local, 1)
    engine, initial, _ = local
    disk = engine.store._path(initial.id).read_bytes()
    save = engine.store.save
    monkeypatch.setattr(engine.store, 'save', Mock(side_effect=OSError('full')))
    with pytest.raises(OSError):
        wait(local, 1)
    assert engine.store._path(initial.id).read_bytes() == disk
    monkeypatch.setattr(engine.store, 'save', save)
    game = wait(local, 1)
    state = game.heavens_state
    before = stones(game)
    result = issue(local, 'freight_collect')
    assert operations.command(local[2], initial.id, result['command_seq'], state['revision'],
                              'freight_collect', 'sea_echo', {}) == result
    assert stones(engine.store.load(initial.id)) == before+3000


def test_freight_blocks_relationships_war_and_maintenance_material(local):
    ready(local)
    start(local)
    engine, initial, deps = local
    game = engine.store.load(initial.id)
    identity = get_echo(game.heavens_state['runtime'])['visitor_id']
    npc = game.world_npcs[identity]
    with pytest.raises(ValueError):
        engine.manage_party(initial.id, identity, 'invite')
    assert identity not in {row.id for row in engine._war_side_members(game, 'race', npc.race, npc.world)}
    assert not deps.quote_materials(game, 'sea_echo')
    assert not deps.person_available(game, identity)


def test_lifespan_death_precedes_delivery(local):
    ready(local)
    engine, initial, _ = local
    game = engine.store.load(initial.id)
    npc = game.world_npcs[get_echo(game.heavens_state['runtime'])['visitor_id']]
    npc.lifespan = npc.age+2
    engine.store.save(game)
    start(local)
    game = wait(local, 2)
    cargo = get_echo(game.heavens_state['runtime'])['freight']
    assert cargo['status'] == 'failed' and not cargo['delivered']
    assert cargo['spent'] == 1000 and game.world_npcs[npc.id].world == 'celestial'

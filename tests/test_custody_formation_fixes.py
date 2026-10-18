"""Real HTTP regressions for sentence years, prison ownership and formation writes."""
import copy
import random

import pytest

from test_other_systems_audit_fixes import api, new_game, snapshot
from test_ownership_prison_fixes import organization_game
from test_crafting_field_audit_fixes import blocking_state
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.system.formation_system import formation_material_definitions, make_formation_material_instance


def formation_game(engine, act, *, ground=False):
    game = new_game(engine)
    definitions = formation_material_definitions()
    rows = [make_formation_material_instance(definitions[k], source='隔离验收', origin_world='human')
            for k in ('human_greenwood_stake', 'human_red_sun_sand', 'human_xuanyin_stone')]
    game.player.formation_materials.extend(rows)
    engine.store.save(game)
    act(game.id, 'formation-save', name='刑期阵法验收', slots=[r['id'] for r in rows]+[None]*6, activate=True)
    if ground:
        act(game.id, 'formation-ground-deploy', owner_kind='player')
    return engine._load(game.id), {r['id'] for r in rows}


def prepare_operation(engine, act, operation):
    game, identities = formation_game(engine, act, ground='ground' in operation)
    payload = {}
    if 'ground' in operation:
        payload['ground_formation_id'] = game.player.formation_ground_arrays[0]['id']
    if operation.endswith('repair'):
        supply = next(r for r in engine._formation_maintenance_defs().values() if r['world']=='human')
        game.player.formation_ground_arrays[0]['durability'] = 20
        game.player.formation_repair_supplies[supply['id']] = 2
        payload.update(supply_id=supply['id'], quantity=1)
    if operation == 'formation-delete': payload['formation_id'] = game.player.active_formation_id
    engine.store.save(game)
    return game, payload, identities


@pytest.mark.parametrize('kind', ['sect', 'family'])
def test_sentence_expires_by_actual_years_not_action_units(api, kind):
    engine, act = api
    game, identity = organization_game(engine, kind)
    game.player.next_tribulation_age = None
    engine.store.save(game)
    act(game.id, 'intrigue-resolution', kind=kind, resolution_type='imprison_member', target_id=identity, years=2)
    before = engine._load(game.id)
    for _ in range(2): engine.get_game(game.id)
    assert engine._load(game.id).intrigue_state['factions'][kind+':audit_org']['prison'][0]['sentence_remaining']==2
    act(game.id, 'advance', action='rest', years=1)
    saved = engine._load(game.id)
    assert saved.player.age-before.player.age > 2
    assert not engine._intrigue_is_imprisoned(saved, identity)
    assert saved.intrigue_state['factions'][kind+':audit_org']['prison']==[]


def test_interrupted_year_counts_once_and_unit_settlement_never_deducts_again(api, monkeypatch):
    engine, act = api
    game, identity = organization_game(engine)
    act(game.id, 'intrigue-personnel', kind='sect', action='imprison', npc_id=identity, years=3)
    before = engine._load(game.id)
    original = engine._resolve_breakthroughs
    def interrupt(actual, rng):
        original(actual, rng)
        actual.pending_event = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], actual, random.Random(1))
    with monkeypatch.context() as patch:
        patch.setattr(engine, '_resolve_breakthroughs', interrupt)
        act(game.id, 'advance', action='rest', years=1)
    saved = engine._load(game.id)
    assert saved.player.age-before.player.age==1
    assert saved.intrigue_state['factions']['sect:audit_org']['prison'][0]['sentence_remaining']==2
    act(game.id, 'choice', event_id=saved.pending_event['id'], choice_id='acknowledge')
    saved = engine._load(game.id)
    assert saved.intrigue_state['factions']['sect:audit_org']['prison'][0]['sentence_remaining']==2


@pytest.mark.parametrize('action', ['endure','wait','cultivate'])
def test_player_prison_year_ticks_npc_sentence_without_double_deducting_player(api, action):
    engine, act = api
    game, identity = organization_game(engine)
    act(game.id, 'intrigue-personnel', kind='sect', action='imprison', npc_id=identity, years=2)
    game = blocking_state(engine, engine._load(game.id), 'imprisonment')
    assert game.player.imprisonment['facility']=='faction_prison'
    remaining = game.player.imprisonment['remaining_years']
    age = game.player.age
    act(game.id, 'prison-action', action=action)
    saved = engine._load(game.id)
    assert saved.player.age==age+1
    assert saved.player.imprisonment['remaining_years']==remaining-1
    assert saved.intrigue_state['factions']['sect:audit_org']['prison'][0]['sentence_remaining']==1


def test_spatial_year_defers_original_world_prison_until_catchup(api):
    from test_spatial_talismans import occupy
    engine, act = api
    game, identity = organization_game(engine)
    act(game.id, 'intrigue-personnel', kind='sect', action='imprison', npc_id=identity, years=2)
    game = engine._load(game.id)
    occupy(engine, game, 'secluded')
    before = engine._load(game.id)
    act(game.id, 'spatial-action', action='explore')
    saved = engine._load(game.id)
    assert saved.player.age==before.player.age+1
    # The isolated player has no live task depending on this original prison.
    # Its society and sentence freeze together, then settle the real year once.
    assert saved.intrigue_state['factions']['sect:audit_org']['prison'][0]['sentence_remaining']==2
    from cultivation_life.engine.world import regions
    regions.synchronize(engine._dependencies.regions, saved, ['human'])
    regions.synchronize(engine._dependencies.regions, saved, ['human'])
    assert saved.intrigue_state['factions']['sect:audit_org']['prison'][0]['sentence_remaining']==1


def test_closed_intrigue_dlc_preserves_original_remaining_sentence(api, monkeypatch):
    engine, act = api
    game, identity = organization_game(engine)
    act(game.id, 'intrigue-personnel', kind='sect', action='imprison', npc_id=identity, years=2)
    with monkeypatch.context() as patch:
        patch.setitem(WORLD_SYSTEMS['intrigue_dlc'], 'enabled', False)
        act(game.id, 'advance', action='rest', years=1)
    saved = engine._load(game.id)
    assert saved.intrigue_state['factions']['sect:audit_org']['prison'][0]['sentence_remaining']==2


def test_partial_unit_map_trip_deducts_only_actual_travel_years(api):
    engine, act = api
    game, identity = organization_game(engine)
    plans = [engine.maps.travel_plan(game.player.world, game.player.location_id, row['id'], game.player.realm_index)
             for row in engine.maps.worlds[game.player.world]['locations'] if row['id']!=game.player.location_id]
    plan = min((p for p in plans if p.status=='ok'), key=lambda p:p.years)
    assert 0 < plan.years < WORLD_SYSTEMS['time_units'][str(game.player.realm_index)]
    act(game.id,'intrigue-personnel',kind='sect',action='imprison',npc_id=identity,years=10)
    before = engine._load(game.id)
    act(game.id,'map-travel',destination=plan.destination)
    saved = engine._load(game.id)
    assert saved.player.age-before.player.age==plan.years
    assert saved.intrigue_state['factions']['sect:audit_org']['prison'][0]['sentence_remaining']==10-plan.years


def detached_prisoner(engine, act, kind='sect', state='alive'):
    game, identity = organization_game(engine, kind)
    act(game.id, 'intrigue-personnel', kind=kind, action='imprison', npc_id=identity, years=10)
    game = engine._load(game.id)
    entity = game.sects['audit_org'] if kind=='sect' else game.family
    npc = entity.npcs.pop()
    npc.faction_id = None
    if state != 'missing':
        npc.alive = state != 'dead'
        game.world_npcs[npc.id] = npc
    engine.store.save(game)
    snapshot(engine, game.id)
    return engine._load(game.id), identity


@pytest.mark.parametrize('kind', ['sect', 'family'])
@pytest.mark.parametrize('state', ['alive', 'dead', 'missing'])
def test_original_prison_releases_detached_records_without_recreating_or_reviving_people(api, kind, state):
    engine, act = api
    game, identity = detached_prisoner(engine, act, kind, state)
    before_people = copy.deepcopy(game.world_npcs)
    before_rng = game.rng_state
    act(game.id, 'intrigue-personnel', kind=kind, action='release', npc_id=identity)
    saved = engine._load(game.id)
    assert not engine._intrigue_is_imprisoned(saved, identity)
    assert saved.intrigue_state['factions'][kind+':audit_org']['prison']==[]
    assert saved.world_npcs==before_people and saved.rng_state==before_rng
    frozen = snapshot(engine, game.id)
    act(game.id, 'intrigue-personnel', status=400, kind=kind, action='release', npc_id=identity)
    assert engine.store._path(game.id).read_bytes()==frozen


@pytest.mark.parametrize('kind', ['sect','family'])
def test_jailed_member_cannot_be_expelled_until_released(api, kind):
    engine, act = api
    game, identity = organization_game(engine, kind)
    act(game.id, 'intrigue-personnel', kind=kind, action='imprison', npc_id=identity, years=10)
    frozen = snapshot(engine, game.id)
    act(game.id, 'intrigue-personnel', status=400, kind=kind, action='expel', npc_id=identity)
    assert engine.store._path(game.id).read_bytes()==frozen
    if kind=='family':
        for action in ['expel','send_sect']:
            act(game.id, 'family-action', status=400, action=action, npc_id=identity)
            assert engine.store._path(game.id).read_bytes()==frozen
    act(game.id, 'intrigue-personnel', kind=kind, action='release', npc_id=identity)
    act(game.id, 'intrigue-personnel', kind=kind, action='expel', npc_id=identity)
    assert not engine._intrigue_is_imprisoned(engine._load(game.id), identity)


def test_prison_release_cannot_clear_another_organizations_record(api):
    engine, act = api
    game, identity = detached_prisoner(engine, act)
    own = copy.deepcopy(game.sects['audit_org'])
    own.id = 'different_org'; own.name = '其它组织'
    game.sects[own.id] = own
    game.player.faction_id = own.id
    engine.store.save(game)
    frozen = snapshot(engine, game.id)
    act(game.id, 'intrigue-personnel', status=400, kind='sect', action='release', npc_id=identity)
    assert engine.store._path(game.id).read_bytes()==frozen
    assert engine._intrigue_is_imprisoned(engine._load(game.id), identity)


OPERATIONS = ['formation-deactivate','formation-delete','formation-ground-withdraw','formation-ground-repair']


@pytest.mark.parametrize('mode', ['event','imprisonment'])
@pytest.mark.parametrize('operation', OPERATIONS)
def test_formation_writes_refuse_busy_states_without_moving_materials_or_losing_followup(api, mode, operation):
    engine, act = api
    game, payload, _ = prepare_operation(engine, act, operation)
    game = blocking_state(engine, game, mode, followup=mode=='event')
    frozen = snapshot(engine, game.id)
    act(game.id, operation, status=400, **payload)
    assert engine.store._path(game.id).read_bytes()==frozen
    assert not engine.get_game(game.id)['formation_system']['operation_available']


@pytest.mark.parametrize('operation', OPERATIONS)
def test_formation_writes_restore_after_real_followup_and_return_each_material_once(api, operation):
    engine, act = api
    game, payload, identities = prepare_operation(engine, act, operation)
    game = blocking_state(engine, game, followup=True)
    reward = copy.deepcopy(game.pending_event['_followup_event'])
    act(game.id, 'choice', event_id=game.pending_event['id'], choice_id='acknowledge')
    assert engine._load(game.id).pending_event['runtime']==reward['runtime']
    act(game.id, 'choice', event_id=reward['id'], choice_id='pill')
    act(game.id, operation, **payload)
    saved = engine._load(game.id)
    if operation.endswith('repair'):
        assert saved.player.formation_repair_supplies[payload['supply_id']]==1
        assert saved.player.formation_ground_arrays[0]['durability']>20
    else:
        rows = [r for r in saved.player.formation_materials if r['id'] in identities]
        assert len(rows)==len(identities)==3

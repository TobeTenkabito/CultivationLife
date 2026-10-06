"""M3 second round: real identities, finite gates, logistics and combat."""
import copy
from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

from test_heavens_m1 import local
from test_heavens_ruins import site, act, load
from test_heavens_frontier import ready
from cultivation_life.models import GameState
from cultivation_life.person_assignments import deployment_assignment
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system.heavens import campaign, campaign_actions, frontier, operations
from cultivation_life.system.heavens.campaign_definitions import CAMPAIGN_ID, BUDGET, INITIAL_SUPPLY, SOURCE
from cultivation_life.system.heavens.calendar import year_step, YearContext


def annual(bundle, work):
    deps = bundle[2]
    if not work.spatial_state.get('current'):
        frontier.year_step(deps, work)
        campaign.year_step(deps, work)
    year_step(deps, work, YearContext(work.heavens_state['runtime']['last_year_key']+1))


def issue(bundle, action, target=CAMPAIGN_ID):
    state = load(bundle).heavens_state
    return operations.command(bundle[2], bundle[1].id, state['command_seq']+1, state['revision'], action, target, {})


def advance(bundle, count=1, until=None):
    work = load(bundle)
    for _ in range(count):
        work.player.age += 1
        annual(bundle, work)
        if until and until(work):
            break
    bundle[0].store.save(work)
    return work


@pytest.fixture
def military(ready):
    engine, game, deps = ready
    def step(work, rng, news):
        annual(bundle, work)
        return True
    bundle = engine, game, replace(deps, advance_year=step, settle_activity_units=Mock())
    # The ruin encounter belongs to M2. This fixture retains its real ownership
    # transfer and time while isolating that unrelated guardian's outcome.
    issue(bundle, 'frontier_inquire', 'lanjiang_frontier')
    act(bundle, 'ruins_enter')
    with patch.object(engine, '_combat', return_value=('victory', '机关交锋已结算')):
        act(bundle, 'ruins_take')
    act(bundle, 'ruins_leave')
    work = advance(bundle, 200, until=lambda g: campaign.get(g) is not None)
    assert campaign.get(work) is not None
    return bundle


def construction(bundle):
    work = load(bundle)
    work.player.location_id = 'lanjiang_steppe'
    bundle[0].store.save(work)
    work = advance(bundle, 200, until=lambda g: campaign.get(g)['gate']['target_progress'] >= 1)
    assert campaign.get(work)['known']
    return work


def opened(bundle):
    construction(bundle)
    work = advance(bundle, 100, until=lambda g: campaign.get(g)['gate']['state'] == 'open')
    assert campaign.get(work)['gate']['state'] == 'open'
    return work


def test_two_end_construction_real_roads_and_exclusive_assets(military):
    before = load(military)
    row = campaign.get(before)
    assert len(row['units']) == 3
    for unit in row['units']:
        npc = before.world_npcs[unit['person_id']]
        assert npc.world == 'demon' and npc.location_id == unit['home']
        assert deployment_assignment(before, npc.id)
        assert all(n.id != npc.id for s in before.sects.values() for n in s.npcs)
    work = construction(military)
    row = campaign.get(work)
    assert row['gate']['target_progress'] == 1 and row['gate']['source_progress'] > 1
    assert not row['shipment'] and not row['deliveries']
    assert row['materials']['target']['owner'] == 'target_gate'
    work = opened(military)
    row = campaign.get(work)
    assert row['shipment']['kind'] == 'troop' and row['shipment']['progress'] == 0
    assert GameState.from_dict(work.to_dict()).to_dict() == work.to_dict()
    assert not work.wars and not work.player.formation_materials


def test_military_lane_cannot_deliver_before_sixteen_actual_years(military):
    work = opened(military)
    identity = campaign.get(work)['shipment']['person_id']
    work = advance(military, 15)
    assert work.world_npcs[identity].world == 'demon'
    work = advance(military)
    assert work.world_npcs[identity].world == 'human'
    assert work.world_npcs[identity].location_id == 'lanjiang_steppe'
    row = campaign.get(work)
    assert row['deliveries'] == 1
    work = advance(military, 18)
    row = campaign.get(work)
    assert row['deliveries'] >= 2
    assert sum(row['supply'].values())+(row['shipment']['quantity'] if row['shipment'] else 0) == INITIAL_SUPPLY


def test_closing_route_freezes_manifest_and_does_not_duplicate_people(military):
    work = opened(military)
    before = copy.deepcopy(campaign.get(work)['shipment'])
    blocked = military[0], military[1], replace(military[2], campaign_world_open=lambda _: False)
    work = advance(blocked, 3)
    assert campaign.get(work)['shipment'] == before
    assert campaign.get(work)['deliveries'] == 0
    work = advance(military, 16)
    assert campaign.get(work)['deliveries'] == 1


def test_authority_revocation_stops_lift_and_returns_actual_people(military):
    work = opened(military)
    work.intrigue_state.setdefault('factions', {})['sect:blood_prison'] = {'controller_id':'player'}
    military[0].store.save(work)
    work = advance(military)
    assert campaign.get(work)['status'] == 'withdrawing'
    assert campaign.get(work)['shipment'] is None
    builder = next(u for u in campaign.get(work)['units'] if u['role'] == 'builder')
    assert work.world_npcs[builder['person_id']].world == 'human'
    work = advance(military, 250, until=lambda g: campaign.get(g)['status'] == 'withdrawn')
    row = campaign.get(work)
    assert row['status'] == 'withdrawn'
    assert row['budget']['spent']+row['budget']['refunded'] == BUDGET
    for unit in row['units']:
        assert work.world_npcs[unit['person_id']].location_id == unit['home']


def test_custody_preserves_actual_builder_and_interruption_is_repairable(military):
    work = opened(military)
    builder = next(u for u in campaign.get(work)['units'] if u['role'] == 'builder')
    npc = work.world_npcs[builder['person_id']]
    npc.roster_state = 'held'
    military[0].store.save(work)
    work = advance(military, 6)
    assert campaign.get(work)['gate']['state'] == 'interrupted'
    assert campaign.get(work)['shipment']['progress'] == 0
    work.world_npcs[npc.id].roster_state = 'active'
    military[0].store.save(work)
    work = advance(military, 4)
    row = campaign.get(work)
    assert row['gate']['state'] == 'open' and row['gate']['stability'] == 100
    assert row['materials']['reserve']['owner'] == 'spent'


def test_death_never_replaces_engineer_or_revives_person(military):
    work = construction(military)
    unit = next(u for u in campaign.get(work)['units'] if u['role'] == 'builder')
    identity = unit['person_id']
    work.world_npcs[identity].alive = False
    military[0].store.save(work)
    work = advance(military, 200)
    assert not work.world_npcs[identity].alive
    assert next(u for u in campaign.get(work)['units'] if u['role'] == 'builder')['person_id'] == identity
    assert campaign.get(work)['status'] == 'withdrawn'


def test_reports_are_pure_and_never_disclose_remote_manifests(military):
    work = construction(military)
    issue(military, 'campaign_scout')
    work = load(military)
    work.player.location_id = 'wudi_plain'
    military[0].store.save(work)
    before = military[0].store._path(work.id).read_bytes()
    public = operations.view(military[2], work.id, 'known', CAMPAIGN_ID)['campaign']
    assert public['known'] and not public['local']
    assert not {'gate','people','budget','shipment','authorization'} & set(public)
    assert military[0].store._path(work.id).read_bytes() == before


def test_defense_requires_named_approval_and_walks_real_road(military):
    construction(military)
    work = load(military); work.player.location_id = 'wudi_plain'; military[0].store.save(work)
    issue(military, 'campaign_report')
    work = load(military)
    row = campaign.get(work)
    assert row['defense']['authorization']['scope'] == 'guard_lanjiang'
    unit = next(u for u in row['units'] if u['role'] == 'defender')
    assert work.world_npcs[unit['person_id']].location_id == unit['home']
    assert unit['road_years'] > 0
    work = advance(military, unit['road_years'])
    assert work.world_npcs[unit['person_id']].location_id == 'lanjiang_steppe'


def test_limited_spirit_aid_has_unique_material_and_real_transport(military):
    construction(military)
    work = load(military); work.player.location_id = 'wudi_plain'; military[0].store.save(work)
    issue(military, 'campaign_report'); issue(military, 'campaign_aid')
    work = load(military)
    aid = campaign.get(work)['aid']
    assert aid['authorization']['scope'] == 'one_material_aid'
    assert aid['material']['origin_world'] == 'spirit'
    with pytest.raises(ValueError): issue(military, 'campaign_collect')
    work = advance(military, 15)
    assert campaign.get(work)['aid']['status'] == 'transit'
    advance(military)
    issue(military, 'campaign_collect')
    work = load(military)
    assert [m['id'] for m in work.player.formation_materials].count(aid['material']['id']) == 1
    assert campaign.get(work)['aid']['spent'] == 8000
    with pytest.raises(ValueError): issue(military, 'campaign_collect')
    assert GameState.from_dict(work.to_dict()).to_dict() == work.to_dict()


@pytest.mark.parametrize('action', ['campaign_assault','campaign_capture','campaign_sabotage'])
def test_remote_military_actions_are_rejected(military, action):
    construction(military)
    work = load(military); work.player.location_id = 'wudi_plain'; military[0].store.save(work)
    with pytest.raises(ValueError): issue(military, action)


@pytest.mark.parametrize('damage', ['budget','supply','capacity','issuer','gate','duplicate','material','route','clock','evidence'])
def test_invalid_military_saves_are_rejected(military, damage):
    work = load(military); row = campaign.get(work)
    if damage == 'budget': row['budget']['spent'] = BUDGET+100
    elif damage == 'supply': row['supply']['source'] += 1
    elif damage == 'capacity': row['authorization']['capacity'] = 20
    elif damage == 'issuer': row['authorization']['issuer_id'] = 'player'
    elif damage == 'gate': row['gate']['state'] = 'open'
    elif damage == 'duplicate': row['units'][1]['person_id'] = row['units'][0]['person_id']
    elif damage == 'material': work.player.formation_materials.append(row['materials']['source']['item'])
    elif damage == 'route': row['units'][0]['road'][-1] = 'fake'
    elif damage == 'clock': row['last_year'] += 20
    elif damage == 'evidence': row['evidence']['location'] = 'fake'
    with pytest.raises(ValueError): GameState.from_dict(work.to_dict())


def test_actual_detailed_combat_and_capture_use_authoritative_person(military):
    construction(military)
    work = load(military)
    p = work.player
    p.realm_index, p.layer = 8, 9
    p.hp, p.mp = max_hp(p), max_mp(p)
    military[0].store.save(work)
    identity = campaign_actions.guards(military[2],work)[0]['person_id']
    issue(military, 'campaign_capture')
    work = load(military)
    assert work.last_combat_report
    npc = military[2].resolve_person(work,identity)
    assert npc and npc.id == identity
    assert npc.roster_state == 'held' or next(u for u in campaign.get(work)['units'] if u['person_id'] == identity)['phase'] != 'stationed'
    if npc.roster_state == 'held':
        assert identity in work.inactive_npcs and identity not in work.world_npcs


def test_save_failure_rolls_back_combat_and_duplicate_command_is_idempotent(military):
    construction(military)
    state = load(military).heavens_state
    args = (military[1].id,state['command_seq']+1,state['revision'],'campaign_scout',CAMPAIGN_ID,{})
    before = military[0].store._path(military[1].id).read_bytes()
    with patch.object(military[0].store,'save',side_effect=OSError('full')):
        with pytest.raises(OSError): operations.command(military[2],*args)
    assert military[0].store._path(military[1].id).read_bytes() == before
    result = operations.command(military[2],*args)
    after = military[0].store._path(military[1].id).read_bytes()
    assert operations.command(military[2],*args) == result
    assert military[0].store._path(military[1].id).read_bytes() == after


def test_detailed_repelling_then_demolition_stops_construction_and_keeps_real_return(military):
    construction(military)
    work = load(military)
    work.player.realm_index, work.player.layer = 8, 9
    work.player.hp, work.player.mp = max_hp(work.player), max_mp(work.player)
    military[0].store.save(work)
    issue(military, 'campaign_assault')
    work = load(military)
    assert work.last_combat_report and campaign.get(work)['status'] == 'withdrawing'
    assert not campaign_actions.guards(military[2],work)
    issue(military, 'campaign_sabotage')
    work = load(military)
    assert campaign.get(work)['gate']['state'] == 'destroyed'
    assert not campaign.get(work)['deliveries'] and not work.wars
    advance(military,200)
    assert campaign.get(load(military))['status'] == 'withdrawn'


def test_actual_npc_engagement_preserves_wounds_and_does_not_change_political_ownership(military):
    construction(military)
    work = load(military); work.player.location_id = 'wudi_plain'; military[0].store.save(work)
    issue(military,'campaign_report')
    work = advance(military,200,until=lambda g: bool(campaign.get(g)['battles']))
    row = campaign.get(work)
    assert row['battles']
    battle = row['battles'][0]
    assert military[2].resolve_person(work,battle['attacker']).wounds > 0
    assert military[2].resolve_person(work,battle['defender']).wounds > 0
    assert work.sects['tianjian'].world == 'human' and not work.sects['tianjian'].extinct
    assert not work.wars


def test_normal_annual_grows_each_transferred_person_once(military):
    work = load(military)
    identities = [u['person_id'] for u in campaign.get(work)['units']]
    ages = {key:work.world_npcs[key].age for key in identities}
    # Keep the actual NPC year; isolate unrelated Guixu and cultivation rolls.
    engine = military[0]
    real = engine, military[1], engine._dependencies.heavens
    with patch.object(engine,'_advance_guixu_calendar',return_value=False), patch.object(engine,'_advance_npc_cultivation',return_value=None):
        issue(real,'campaign_wait')
    work = load(real)
    assert all(work.world_npcs[key].age == ages[key]+1 for key in identities)
    assert all(u['progress'] == 1 for u in campaign.get(work)['units'])


def test_generation_off_and_isolated_years_never_catch_up_deployment(military):
    work = load(military)
    row = copy.deepcopy(campaign.get(work))
    work.heavens_state['generation_enabled'] = False
    for _ in range(20):
        year_step(military[2],work,YearContext(work.heavens_state['runtime']['last_year_key']+1))
    assert campaign.get(work) == row
    military[0].store.save(work)
    work = advance(military)
    assert all(u['progress'] == 1 for u in campaign.get(work)['units'])


def test_same_annual_callback_never_double_spends(military):
    work = load(military)
    legacy_rng = work.rng_state
    campaign.year_step(military[2],work)
    after = copy.deepcopy(campaign.get(work))
    campaign.year_step(military[2],work)
    assert campaign.get(work) == after and work.rng_state == legacy_rng


def test_aid_can_be_declined_without_generating_material(military):
    construction(military)
    work = load(military); work.player.location_id = 'wudi_plain'; military[0].store.save(work)
    issue(military,'campaign_report')
    before = load(military).player.age
    issue(military,'campaign_decline')
    work = load(military)
    assert work.player.age == before and campaign.get(work)['aid']['material'] is None
    with pytest.raises(ValueError): issue(military,'campaign_aid')


def test_donor_change_revokes_only_undelivered_aid(military):
    construction(military)
    work = load(military); work.player.location_id = 'wudi_plain'; military[0].store.save(work)
    issue(military,'campaign_report'); issue(military,'campaign_aid')
    work = advance(military,3)
    work.intrigue_state.setdefault('factions',{})['sect:taixuan'] = {'controller_id':'player'}
    military[0].store.save(work)
    work = advance(military)
    aid = campaign.get(work)['aid']
    assert aid['status'] == 'cancelled' and aid['spent'] == 1500 and aid['refunded'] == 10500
    assert not work.player.formation_materials
    assert not campaign_actions.project(military[2],work)['aid']['cancelled']
    work = advance(military,16)
    assert campaign_actions.project(military[2],work)['aid']['cancelled']
    assert campaign.get(work)['reports'][-1]['kind'] == 'aid_cancelled'


def test_warning_comes_from_actual_presence_and_pauses_only_after_receipt(military):
    work = load(military)
    assert not campaign.get(work)['known']
    work.heavens_state['watch'] = True
    work.heavens_state['runtime']['pause_on_opportunity'] = True
    military[0].store.save(work)
    work = advance(military,10)
    assert not campaign.get(work)['warning_received']
    work = construction(military)
    assert campaign.get(work)['warning_received']
    assert any(n['id'] == CAMPAIGN_ID for n in work.heavens_state['runtime']['notifications'])


def test_last_year_event_requires_zero_year_resume_before_scout_facts(military):
    construction(military)
    calls = []
    def advance_paused(work,rng,news):
        annual(military,work)
        calls.append(1)
        if len(calls) == 2:
            work.pending_event = {'id':'pause'}
            return False
        return True
    delayed = military[0],military[1],replace(military[2],advance_year=advance_paused)
    result = issue(delayed,'campaign_scout')
    work = load(delayed)
    assert result['status'] == 'paused' and not campaign.get(work)['surveyed']
    age = work.player.age
    work.pending_event = None; military[0].store.save(work)
    issue(delayed,'resume',result['task_id'])
    work = load(delayed)
    assert campaign.get(work)['surveyed'] and work.player.age == age


def test_transport_arrival_save_failure_restores_same_manifest_and_person(military):
    work = opened(military)
    identity = campaign.get(work)['shipment']['person_id']
    advance(military,15)
    before = military[0].store._path(work.id).read_bytes()
    with patch.object(military[0].store,'save',side_effect=OSError('disk full')):
        with pytest.raises(OSError): issue(military,'campaign_wait')
    assert military[0].store._path(work.id).read_bytes() == before
    assert load(military).world_npcs[identity].world == 'demon'
    issue(military,'campaign_wait')
    assert load(military).world_npcs[identity].world == 'human'


def test_return_lane_admits_only_one_actual_person_per_year(military):
    work = opened(military); work = advance(military,16)
    work.intrigue_state.setdefault('factions',{})['sect:blood_prison'] = {'controller_id':'player'}
    military[0].store.save(work)
    work = advance(military)
    returning = [u for u in campaign.get(work)['units'] if u['phase'] == 'returning']
    assert len(returning) == 2 and sum(u['progress'] for u in returning) == 1


def test_broken_original_ward_cannot_send_new_inquiry(ready):
    act(ready,'ruins_enter')
    with patch.object(ready[0],'_combat',return_value=('victory','fixture')):
        act(ready,'ruins_take')
    act(ready,'ruins_leave')
    with pytest.raises(ValueError,match='阵眼'):
        issue(ready,'frontier_inquire','lanjiang_frontier')


def legacy_recon_save(military):
    work = load(military)
    row = work.heavens_state['runtime'].pop('campaign')
    work.heavens_state['definition_versions'].pop(CAMPAIGN_ID)
    for unit in row['units']:
        if unit['person_id'] != frontier.get(work)['person_id']:
            npc = work.world_npcs.pop(unit['person_id'])
            work.sects[unit['faction_id']].npcs.append(npc)
    frontier.get(work).pop('landing_evidence')
    military[0].store.save(work)
    return work


def test_legacy_completed_recon_is_read_only_then_derives_only_existing_survey(military):
    work = legacy_recon_save(military)
    before = military[0].store._path(work.id).read_bytes()
    operations.view(military[2],work.id,'known')
    assert military[0].store._path(work.id).read_bytes() == before
    assert 'landing_evidence' not in frontier.get(load(military))
    work = advance(military)
    assert campaign.get(work) and frontier.get(work)['landing_evidence']['observer_id'] == frontier.get(work)['person_id']


@pytest.mark.parametrize('block', ['player_office','extinct','no_people','no_budget','generation_off','ward_restored'])
def test_no_military_order_without_real_approval_people_or_motive(military, block):
    work = legacy_recon_save(military)
    if block == 'player_office': work.intrigue_state.setdefault('factions',{})['sect:blood_prison'] = {'controller_id':'player'}
    elif block == 'extinct': work.sects[SOURCE].extinct = True
    elif block == 'no_people':
        for npc in work.sects[SOURCE].npcs: npc.realm_index = 6
        work.world_npcs[frontier.get(work)['person_id']].realm_index = 6
    elif block == 'generation_off': work.heavens_state['generation_enabled'] = False
    elif block == 'ward_restored':
        # Reuse the real return action and unique core ownership rather than
        # writing a replacement component into an unrelated asset ledger.
        military[0].store.save(work)
        act(military,'ruins_enter'); act(military,'ruins_return'); act(military,'ruins_leave')
        work = load(military)
    military[0].store.save(work)
    bundle = military
    if block == 'no_budget':
        original = military[2].campaign_roster
        def expensive(game,faction,roles):
            plan = original(game,faction,roles)
            for unit in plan['units']: unit['road_years'] = 500
            return plan
        bundle = military[0],military[1],replace(military[2],campaign_roster=expensive)
    work = advance(bundle)
    assert campaign.get(work) is None


def test_late_original_warning_still_reaches_defender_after_campaign_started(ready):
    issue(ready,'frontier_inquire','lanjiang_frontier')
    work = advance(ready,100,until=lambda g: frontier.get(g)['phase'] == 'scouting')
    work.player.location_id = 'lanjiang_steppe'; ready[0].store.save(work)
    issue(ready,'frontier_scout','lanjiang_frontier')
    work = load(ready); work.player.location_id = 'wudi_plain'; ready[0].store.save(work)
    act(ready,'ruins_enter')
    with patch.object(ready[0],'_combat',return_value=('victory','fixture')):
        act(ready,'ruins_take')
    act(ready,'ruins_leave')
    work = advance(ready,100,until=lambda g: campaign.get(g) is not None)
    assert campaign.get(work)['defense'] is None
    issue(ready,'frontier_report','lanjiang_frontier')
    work = advance(ready)
    assert campaign.get(work)['defense']['status'] == 'approved'
    assert campaign.get(work)['defense_requested']

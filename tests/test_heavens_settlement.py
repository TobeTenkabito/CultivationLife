"""M3 final acceptance: scoped rule, real outcomes, recovery and old-save seams."""
import copy
from dataclasses import replace
from unittest.mock import patch

import pytest

from test_heavens_campaign import local, site, ready, military, construction, opened, advance, issue, load, annual
from cultivation_life.system.heavens import operations
from cultivation_life.models import GameState
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system.heavens import campaign, campaign_actions, settlement
from cultivation_life.system.heavens.local_control import occupied, resource_reason, arrival_notice
from cultivation_life.system.heavens.campaign_definitions import SOURCE, DEFENDER, BUDGET
from cultivation_life.content_registry import WORLD_SYSTEMS, FACTION_SYSTEMS
from test_heavens_ruins import act


def occupation(bundle):
    opened(bundle)
    work = advance(bundle, 16)
    assert campaign.get(work)['settlement']['control'] == 'occupied'
    return work


def delegates(bundle):
    # Fixed early-warning input: exercise the real separate defense approval
    # before either army starts its original road, never teleport a delegate.
    work = load(bundle)
    row = campaign.get(work)
    row['defense_requested'] = True
    campaign.request_defense(bundle[2], work, work.heavens_state['runtime']['processed_years'])
    bundle[0].store.save(work)
    construction(bundle)
    work = advance(bundle, 100, until=lambda g: any(u['role'] == 'defender' and u['phase'] == 'stationed' for u in campaign.get(g)['units']))
    work.player.location_id = 'lanjiang_steppe'
    bundle[0].store.save(work)
    return work


def test_actual_garrison_and_finite_admin_no_whole_world_seizure(military):
    work = occupation(military)
    row = campaign.get(work); state = row['settlement']
    assert state['garrison_id'] != state['governor_id']
    assert state['administration_spent'] == 100
    assert work.sects['tianjian'].world == 'human'
    assert not work.intrigue_state.get('factions') and not work.wars
    assert occupied(work) and resource_reason(work, 'treasure')
    assert not occupied(work, 'human', 'muling_desert')
    assert not occupied(work, 'demon', 'lanjiang_steppe')
    assert not resource_reason(work, 'cultivate') and not resource_reason(work, 'rest')
    assert arrival_notice(work)
    before = row['budget']['spent']
    work = advance(military)
    assert campaign.get(work)['settlement']['administration_spent'] == 200
    assert campaign.get(work)['budget']['spent'] > before
    assert GameState.from_dict(work.to_dict()).to_dict() == work.to_dict()


@pytest.mark.parametrize('cause', ['death', 'held', 'wounds', 'moved', 'rank', 'supply'])
def test_losing_real_garrison_immediately_removes_resource_restriction(military, cause):
    work = occupation(military); row = campaign.get(work)
    npc = work.world_npcs[row['settlement']['garrison_id']]
    if cause == 'death': npc.alive = False
    if cause == 'held': npc.roster_state = 'held'
    if cause == 'wounds': npc.wounds = 3
    if cause == 'moved': npc.location_id = 'wudi_plain'
    if cause == 'rank': npc.realm_index = 6
    if cause == 'supply':
        row['supply']['spent'] += row['supply']['target']; row['supply']['target'] = 0
    assert not resource_reason(work, 'treasure')
    assert settlement.control(military[2], work, row)[0] == 'uncontrolled'


def test_occupation_exhausts_without_rebel_generation_and_refunds_once(military):
    work = occupation(military)
    identities = {u['person_id'] for u in campaign.get(work)['units']}
    work = advance(military, 400)
    row = campaign.get(work)
    assert row['status'] == 'withdrawn'
    assert row['settlement']['outcome'] == 'occupation_ended'
    assert row['settlement']['control'] == 'uncontrolled'
    assert row['budget']['spent']+row['budget']['refunded'] == BUDGET
    assert identities == {u['person_id'] for u in row['units']}
    ledger = copy.deepcopy(row['budget'])
    work = advance(military, 30)
    assert campaign.get(work)['budget'] == ledger


def test_local_truce_named_delegates_and_actual_return(military):
    delegates(military)
    issue(military, 'campaign_truce')
    row = campaign.get(load(military)); treaty = row['settlement']['treaty']
    assert row['status'] == 'withdrawing'
    assert set(treaty['signatories']) == {SOURCE, DEFENDER}
    assert treaty['location'] == 'lanjiang_steppe'
    assert not row['battles']
    with pytest.raises(ValueError): issue(military, 'campaign_vassal')
    work = advance(military, 250)
    row = campaign.get(work)
    assert row['status'] == 'withdrawn' and row['settlement']['outcome'] == 'truce'
    assert all(work.world_npcs[u['person_id']].location_id == u['home'] for u in row['units'])
    assert not work.wars and not work.intrigue_state.get('factions')


def test_vassal_requires_real_guards_and_expires_without_scope_expansion(military):
    delegates(military)
    work = advance(military, 60, until=lambda g: campaign.get(g)['gate']['state'] == 'open')
    assert not campaign.get(work)['battles']
    issue(military, 'campaign_vassal')
    work = advance(military, 20)
    row = campaign.get(work)
    assert row['settlement']['control'] == 'vassal'
    assert not row['battles']
    governor = next(u for u in row['units'] if u['role'] == 'defender')
    assert row['settlement']['governor_id'] == governor['person_id']
    assert row['defense']['budget']['spent'] > 0
    work = advance(military, 250)
    assert campaign.get(work)['settlement']['treaty']['status'] == 'expired'
    assert campaign.get(work)['settlement']['outcome'] == 'vassal'
    assert campaign.get(work)['status'] == 'withdrawn'


def test_successor_does_not_inherit_treaty_and_original_ids_survive(military):
    delegates(military)
    advance(military, 60, until=lambda g: campaign.get(g)['gate']['state'] == 'open')
    issue(military, 'campaign_vassal')
    work = load(military); row = campaign.get(work)
    mandates = copy.deepcopy(row['settlement']['mandates'])
    work.intrigue_state.setdefault('factions', {})['sect:blood_prison'] = {'controller_id': 'player'}
    military[0].store.save(work)
    work = advance(military)
    assert campaign.get(work)['status'] == 'withdrawing'
    assert campaign.get(work)['settlement']['treaty']['status'] == 'review'
    assert campaign.get(work)['settlement']['mandates'] == mandates
    assert work.intrigue_state['factions']['sect:blood_prison'] == {'controller_id': 'player'}


def test_old_campaign_load_is_pure_and_does_not_forge_remote_delegation(military):
    work = construction(military)
    campaign.get(work).pop('settlement')
    military[0].store.save(work)
    before = military[0].store._path(work.id).read_bytes()
    campaign_actions.project(military[2], load(military))
    assert military[0].store._path(work.id).read_bytes() == before
    work = advance(military)
    assert not campaign.get(work)['settlement']['mandates']
    assert campaign.get(work)['settlement']['treaty'] is None


def test_evacuate_real_road_duration_and_same_world_no_political_changes(military):
    occupation(military)
    work = load(military)
    work.player.realm_index = 4
    military[0].store.save(work)
    plan = military[2].campaign_escape_plan(work)
    before = work.player.age
    issue(military, 'campaign_evacuate')
    work = load(military)
    assert work.player.age == before+plan['years']
    assert work.player.location_id == 'wudi_plain' and work.player.world == 'human'
    assert not work.player.imprisonment
    assert campaign.get(work)['reports'][-1]['kind'] == 'evacuation'
    with pytest.raises(ValueError): issue(military, 'campaign_evacuate')


def test_relief_changes_original_wound_once_without_money_or_new_people(military):
    delegates(military)
    work = load(military); row = campaign.get(work)
    unit = next(u for u in row['units'] if u['role'] == 'defender')
    work.world_npcs[unit['person_id']].wounds = 2
    military[0].store.save(work)
    issue(military, 'campaign_relief')
    work = load(military)
    assert work.world_npcs[unit['person_id']].wounds == 1
    assert campaign.get(work)['settlement']['treated'] == [unit['person_id']]
    with pytest.raises(ValueError): issue(military, 'campaign_relief')


def test_prisoner_release_uses_real_custody_and_retains_original_return(military):
    construction(military)
    work = load(military)
    work.player.realm_index, work.player.layer = 8, 9
    work.player.hp, work.player.mp = max_hp(work.player), max_mp(work.player)
    military[0].store.save(work)
    issue(military, 'campaign_capture')
    work = load(military)
    identity = work.player.prisoners[0]['npc_id']
    assert identity in work.inactive_npcs
    issue(military, 'campaign_release')
    work = load(military)
    assert identity not in work.inactive_npcs and not work.player.prisoners
    assert work.world_npcs[identity].alive and work.world_npcs[identity].roster_state == 'active'
    work = advance(military, 200)
    assert campaign.get(work)['status'] == 'withdrawn'


@pytest.mark.parametrize('field,value', [
    ('control', 'whole_world'), ('administration_spent', 1000000), ('governor_id', 'fabricated'),
    ('treated', ['fake']), ('outcome', 'truce'), ('concluded_at', 1), ('ever_occupied', 1),
    ('control', []), ('governor_id', []), ('outcome', {}),
])
def test_invalid_settlement_save_rejected(military, field, value):
    work = occupation(military)
    campaign.get(work)['settlement'][field] = value
    with pytest.raises(ValueError): GameState.from_dict(work.to_dict())


def test_world_closure_freezes_returns_then_recovers_without_new_people(military):
    occupation(military)
    blocked = military[0], military[1], replace(military[2], campaign_world_open=lambda _: False)
    work = advance(blocked, 30)
    assert campaign.get(work)['status'] == 'withdrawing'
    ids = {u['person_id'] for u in campaign.get(work)['units']}
    work = advance(military, 250)
    assert campaign.get(work)['status'] == 'withdrawn'
    assert ids == {u['person_id'] for u in campaign.get(work)['units']}


def test_signed_document_does_not_leak_remote_budgets_or_live_control(military):
    delegates(military); issue(military, 'campaign_truce')
    work = load(military); work.player.location_id = 'wudi_plain'
    before = work.to_dict()
    view = campaign_actions.project(military[2], work)['settlement']
    assert view['treaty']['name'] == '岚疆停战'
    assert view['control'] is None and not view['duties'] and not view['patients']
    assert 'budget' not in view and 'status' not in view['treaty']
    assert work.to_dict() == before


def test_truce_last_year_event_then_zero_time_resume(military):
    delegates(military)
    calls = []
    def pause(work, rng, news):
        annual(military, work); calls.append(1)
        if len(calls) == 2:
            work.pending_event = {'id': 'settlement-pause'}
            return False
        return True
    delayed = military[0], military[1], replace(military[2], advance_year=pause)
    result = issue(delayed, 'campaign_truce')
    work = load(military)
    assert result['status'] == 'paused' and campaign.get(work)['settlement']['treaty'] is None
    age = work.player.age
    work.pending_event = None; military[0].store.save(work)
    issue(delayed, 'resume', result['task_id'])
    work = load(military)
    assert work.player.age == age and campaign.get(work)['settlement']['treaty']['kind'] == 'truce'


def test_evacuate_failure_rollback_and_duplicate_receipt(military):
    construction(military)
    work = load(military); state = work.heavens_state
    args = military[2], work.id, state['command_seq']+1, state['revision'], 'campaign_evacuate', 'lanjiang_gate', {}
    before = military[0].store._path(work.id).read_bytes()
    with patch.object(military[0].store, 'save', side_effect=OSError('full')):
        with pytest.raises(OSError): operations.command(*args)
    assert military[0].store._path(work.id).read_bytes() == before
    result = operations.command(*args)
    after = military[0].store._path(work.id).read_bytes()
    assert operations.command(*args) == result
    assert military[0].store._path(work.id).read_bytes() == after


def test_real_ordinary_resource_action_obeys_garrison_and_rest_stays_available(military):
    work = occupation(military)
    work.player.realm_index = 4
    military[0].store.save(work)
    # The ordinary engine prepares legacy player/market fields on first load.
    military[0]._load(work.id)
    military[0]._load(work.id)
    before = military[0].store._path(work.id).read_bytes()
    with pytest.raises(ValueError, match='驻军'): military[0].advance(work.id, 'treasure', 1)
    assert military[0].store._path(work.id).read_bytes() == before
    with patch.object(military[0], '_advance_guixu_calendar', return_value=False):
        result = military[0].advance(work.id, 'rest', 1)
    assert result['player']['alive']
    assert load(military).player.age > work.player.age


def test_refusal_no_missing_delegate_substitute_and_no_ward_forgery(military):
    delegates(military)
    with pytest.raises(ValueError, match='修复'): issue(military, 'campaign_withdrawal')
    work = load(military)
    unit = next(u for u in campaign.get(work)['units'] if u['role'] == 'defender')
    work.world_npcs[unit['person_id']].alive = False
    military[0].store.save(work)
    before = military[0].store._path(work.id).read_bytes()
    with pytest.raises(ValueError): issue(military, 'campaign_truce')
    assert military[0].store._path(work.id).read_bytes() == before


def test_returning_actual_ward_allows_scoped_withdrawal_agreement(military):
    delegates(military)
    work = load(military); work.player.location_id = 'wudi_plain'; military[0].store.save(work)
    act(military, 'ruins_enter'); act(military, 'ruins_return'); act(military, 'ruins_leave')
    work = load(military)
    assert work.heavens_state['runtime']['ruins']['ward']['component'] == 'core'
    work.player.location_id = 'lanjiang_steppe'; military[0].store.save(work)
    issue(military, 'campaign_withdrawal')
    work = advance(military, 250)
    assert campaign.get(work)['settlement']['outcome'] == 'withdrawal'
    assert campaign.get(work)['status'] == 'withdrawn'


def test_real_early_warning_to_gate_aid_and_peace_without_synthetic_delegates(ready):
    bundle = None
    def step(work, rng, news):
        annual(bundle, work)
        return True
    bundle = ready[0], ready[1], replace(ready[2], advance_year=step)
    issue(bundle, 'frontier_inquire', 'lanjiang_frontier')
    act(bundle, 'ruins_enter')
    with patch.object(bundle[0], '_combat', return_value=('victory', 'fixture guardian')):
        act(bundle, 'ruins_take')
    act(bundle, 'ruins_leave')
    work = advance(bundle, 100, until=lambda g: g.heavens_state['runtime']['frontier']['phase'] == 'scouting')
    work.player.location_id = 'lanjiang_steppe'; bundle[0].store.save(work)
    issue(bundle, 'frontier_scout', 'lanjiang_frontier')
    work = load(bundle); work.player.location_id = 'wudi_plain'; bundle[0].store.save(work)
    issue(bundle, 'frontier_report', 'lanjiang_frontier')
    advance(bundle, 200, until=lambda g: campaign.get(g) is not None)
    assert campaign.get(load(bundle))['defense_requested']
    work = construction(bundle)
    original = {u['person_id'] for u in campaign.get(work)['units']}
    work.player.location_id = 'wudi_plain'; bundle[0].store.save(work)
    issue(bundle, 'campaign_aid'); advance(bundle, 16); issue(bundle, 'campaign_collect')
    work = load(bundle); work.player.location_id = 'lanjiang_steppe'; bundle[0].store.save(work)
    issue(bundle, 'campaign_truce')
    work = advance(bundle, 250)
    row = campaign.get(work)
    assert row['settlement']['outcome'] == 'truce'
    assert row['aid']['status'] == 'claimed' and len(work.player.formation_materials) == 1
    assert original == {u['person_id'] for u in row['units']}
    assert all(work.world_npcs[u['person_id']].location_id == u['home'] for u in row['units'])


def test_vassal_lapses_when_actual_guard_is_lost(military):
    delegates(military)
    advance(military, 60, until=lambda g: campaign.get(g)['gate']['state'] == 'open')
    issue(military, 'campaign_vassal')
    work = advance(military, 20)
    row = campaign.get(work)
    guard = work.world_npcs[row['settlement']['garrison_id']]
    guard.alive = False
    military[0].store.save(work)
    work = advance(military)
    assert campaign.get(work)['settlement']['treaty']['status'] == 'lapsed'
    assert campaign.get(work)['status'] == 'withdrawing'
    assert campaign.get(work)['settlement']['control'] != 'vassal'


def test_new_occupation_stops_long_exploration_only_at_paid_unit_boundary(military):
    opened(military)
    work = advance(military, 15)
    assert campaign.get(work)['shipment']['progress'] == 15
    work.player.realm_index = 4
    work.heavens_state['watch'] = False
    work.settings['silent_events'] = True
    military[0].store.save(work)
    engine = military[0]
    original_year = engine._advance_world_year
    def quiet_year(game, rng, news):
        return original_year(game, rng, news, encounters=False)
    with (patch.object(engine, '_advance_world_year', side_effect=quiet_year),
          patch.object(engine, '_advance_guixu_calendar', return_value=False),
          patch.object(engine, '_advance_npc_cultivation', return_value=None),
          patch.dict(FACTION_SYSTEMS['npc_cultivation'], accident_death_chance=0)):
        engine.advance(work.id, 'travel', 3)
    after = load(military)
    assert occupied(after)
    assert after.player.age-work.player.age == int(WORLD_SYSTEMS['time_units']['4'])
    with pytest.raises(ValueError, match='驻军'): engine.advance(work.id, 'travel', 1)

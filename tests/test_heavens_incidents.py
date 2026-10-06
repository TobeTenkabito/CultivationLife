"""All-world incident branches, shared transactions and actual-year benefits."""
import copy
import json
from dataclasses import replace
from unittest.mock import Mock

import pytest

from test_heavens_m1 import local, quiet, issue, ROOT
from cultivation_life.models import GameState
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system.heavens import operations
from cultivation_life.system.heavens.incident_definitions import INCIDENTS, response
from cultivation_life.system.heavens.cultivation import activity_gain
from cultivation_life.system.heavens.schema import validate_state


def positioned(bundle, desc, field=False):
    engine, initial, _ = bundle
    work = engine.store.load(initial.id)
    work.player.world = desc.world
    work.player.location_id = desc.field if field else desc.location
    work.player.realm_index = desc.rank
    work.player.mp = max_mp(work.player)
    engine.store.save(work)
    return work


def finish(bundle, desc, action):
    positioned(bundle, desc)
    issue(bundle, 'incident_survey', target=desc.id)
    positioned(bundle, desc, True)
    issue(bundle, action, target=desc.id)
    positioned(bundle, desc)
    issue(bundle, 'incident_review', target=desc.id)
    return bundle[0].store.load(bundle[1].id)


def test_every_major_world_has_distinct_real_locations():
    maps = json.loads((ROOT/'content/maps.json').read_text(encoding='utf-8'))['worlds']
    assert {d.world for d in INCIDENTS} == maps.keys()-{'rift', 'lost'}
    assert len({d.glimpse for d in INCIDENTS}) == len(INCIDENTS)
    for desc in INCIDENTS:
        locations = {p['id']: p['name'] for p in maps[desc.world]['locations']}
        assert locations[desc.location] == desc.location_name
        assert locations[desc.field] == desc.field_name
        assert desc.location != desc.field
        assert desc.responses[0].effect != desc.responses[1].effect


@pytest.mark.parametrize('desc', INCIDENTS, ids=lambda d:d.world)
@pytest.mark.parametrize('action', ['incident_preserve', 'incident_seal'])
def test_all_world_branches_real_time_resources_and_unique_conclusion(local, desc, action):
    bundle = quiet(local)
    start = positioned(bundle, desc)
    before = sum(i.quantity for i in start.player.inventory if i.id == 'spirit_stone')
    work = finish(bundle, desc, action)
    result = response(desc, action)
    assert work.player.age-start.player.age == desc.survey_years+result.years+2
    assert sum(i.quantity for i in work.player.inventory if i.id == 'spirit_stone') == before-result.stones
    row = work.heavens_state['runtime']['incidents'][desc.id]
    assert row['stage'] == 'closed' and row['choice'] == action
    assert row['remaining'] == result.allowance
    assert GameState.from_dict(work.to_dict()).to_dict() == work.to_dict()
    with pytest.raises(ValueError): issue(bundle, 'incident_review', target=desc.id)
    with pytest.raises(ValueError): issue(bundle, 'incident_survey', target=desc.id)


def test_read_only_directory_old_save_and_remote_action_denial(local):
    engine, initial, deps = local
    start = engine.store._path(initial.id).read_bytes()
    view = operations.view(deps, initial.id, 'known')
    assert len(view['incidents']) == 11
    assert all(row['evidence'] is None for row in view['incidents'])
    for desc in INCIDENTS:
        operations.view(deps, initial.id, 'known', desc.id)
    assert engine.store._path(initial.id).read_bytes() == start
    with pytest.raises(ValueError): issue(local, 'incident_survey', target='human_beacon')
    assert 'incidents' not in engine.store.load(initial.id).heavens_state['runtime']


def test_final_year_event_resume_zero_and_cancel_proportional_refund(local):
    bundle = quiet(local); desc = INCIDENTS[0]
    positioned(bundle, desc)
    original = bundle[2].advance_year
    def pause(work, rng, news):
        original(work, rng, news)
        return False
    paused = (*bundle[:2], replace(bundle[2], advance_year=pause))
    result = issue(paused, 'incident_survey', target=desc.id)
    assert result['status'] == 'paused' and result['progress'] == 1
    result = issue(paused, 'resume', target=result['task_id'])
    # Returning False on the last year keeps the task paused, too.
    assert result['status'] == 'paused'
    work = bundle[0].store.load(bundle[1].id); age = work.player.age
    result = issue(bundle, 'resume', target=result['task_id'])
    assert result['status'] == 'completed'
    assert bundle[0].store.load(bundle[1].id).player.age == age
    positioned(bundle, desc, True)
    result = issue(paused, 'incident_preserve', target=desc.id)
    issue(bundle, 'cancel', target=result['task_id'])
    row = bundle[0].store.load(bundle[1].id).heavens_state['runtime']['tasks'][-1]
    assert row['escrow']['spent'] == 100 and row['escrow']['refunded'] == 300


def test_disabled_generation_preserves_existing_work_and_location_rechecked(local):
    bundle = quiet(local); desc = INCIDENTS[0]
    positioned(bundle, desc); issue(bundle, 'incident_survey', target=desc.id)
    issue(bundle, 'configure', {'generation_enabled':False}, target=None)
    with pytest.raises(ValueError): issue(bundle, 'incident_preserve', target=desc.id)
    positioned(bundle, desc, True); issue(bundle, 'incident_seal', target=desc.id)
    positioned(bundle, desc); issue(bundle, 'incident_review', target=desc.id)
    positioned(bundle, INCIDENTS[1])
    with pytest.raises(ValueError): issue(bundle, 'incident_survey', target=INCIDENTS[1].id)


def test_bounded_local_effect_no_remote_or_isolated_grant(local):
    bundle = quiet(local); desc = INCIDENTS[0]
    work = finish(bundle, desc, 'incident_preserve')
    row = work.heavens_state['runtime']['incidents'][desc.id]
    # Capture one grant rather than changing ordinary progression twice.
    grant = Mock(side_effect=lambda _player, gain: gain)
    deps = replace(bundle[2], grant_progress=grant)
    work.player.location_id = desc.field
    activity_gain(deps, work, 100, 'cultivate')
    assert row['remaining'] == 12 and row['claimed'] == 0
    work.player.location_id = desc.location
    for _ in range(20): activity_gain(deps, work, 100, 'cultivate')
    assert row['remaining'] == 0 and 0 < row['claimed'] <= row['base']*.02
    assert grant.call_count == 21
    validate_state(work.heavens_state)


def test_relief_and_rest_are_real_and_finite(local):
    bundle = quiet(local); desc = INCIDENTS[1]
    positioned(bundle, desc)
    work = bundle[0].store.load(bundle[1].id); work.player.hp = max_hp(work.player)*.2; bundle[0].store.save(work)
    work = finish(bundle, desc, 'incident_seal')
    assert work.player.hp == pytest.approx(max_hp(work.player)*.4)
    work = finish(bundle, INCIDENTS[0], 'incident_seal')
    work.player.hp = max_hp(work.player)*.2
    start = work.player.hp
    activity_gain(bundle[2], work, 0, 'rest')
    assert work.player.hp > start
    assert work.heavens_state['runtime']['incidents']['human_beacon']['remaining'] == 7


def test_atomic_save_failure_and_invalid_state(local):
    bundle = quiet(local); positioned(bundle, INCIDENTS[0])
    before = bundle[0].store._path(bundle[1].id).read_bytes()
    original = bundle[0].store.save
    bundle[0].store.save = Mock(side_effect=OSError('disk full'))
    try:
        with pytest.raises(OSError): issue(bundle, 'incident_survey', target=INCIDENTS[0].id)
    finally:
        bundle[0].store.save = original
    assert bundle[0].store._path(bundle[1].id).read_bytes() == before
    work = finish(bundle, INCIDENTS[0], 'incident_preserve')
    bad = copy.deepcopy(work.heavens_state)
    bad['runtime']['incidents']['human_beacon']['remaining'] = 100000
    with pytest.raises(ValueError): validate_state(bad)

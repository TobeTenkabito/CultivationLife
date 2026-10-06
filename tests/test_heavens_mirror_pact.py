"""A finite repair agreement shares the original mirror record and core ownership."""
import copy
from dataclasses import replace
from unittest.mock import patch

import pytest

from test_heavens_m1 import local, issue
from test_heavens_mirror import site, act, load, prepared, entered
from cultivation_life.models import GameState
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system.formation_system import make_formation_material_instance
from cultivation_life.system.heavens import mirror, operations
from cultivation_life.system.heavens.definitions import MIRROR_ID
from cultivation_life.system.heavens.schema import validate_state, validate_references


def material(site):
    work = load(site)
    definition = next(d for d in site[0]._formation_material_defs().values() if d.get('world') == 'human' and d.get('tier') == 4)
    item = make_formation_material_instance(definition, source='守约验收', origin_world='human')
    work.player.formation_materials.append(item)
    site[0].store.save(work)
    return item['id']


def ready(site):
    prepared(site)
    return material(site)


def repair(site, identity):
    return act(site, 'mirror_repair', material_id=identity)


def interrupted(site, *, last_year=False, death=False):
    engine, game, deps = site
    def step(work, rng, news):
        if death: work.player.alive = False
        proceed = deps.advance_year(work, rng, news)
        task = work.heavens_state['runtime']['tasks'][-1]
        if not last_year or task['progress'] == task['duration']:
            if not death: work.pending_event = {'id':'pact-event'}
            return False
        return proceed
    return engine, game, replace(deps, advance_year=step)


def clear_event(site):
    work = load(site)
    work.pending_event = None
    site[0].store.save(work)


def test_real_repair_preserves_cores_original_record_and_independent_clock(site):
    identity = ready(site)
    before = load(site)
    before.player.mp = 0
    site[0].store.save(before)
    projection = operations.preview(site[2], before.id, 'mirror_repair', MIRROR_ID, {'material_id':identity})
    assert projection['years'] == 3 and projection['costs']['mp'] == 0 and projection['material_consumed']
    result = repair(site, identity)
    after = load(site)
    data = mirror.get(after)
    assert result['status'] == 'completed' and after.player.age == before.player.age+3
    assert after.player.opportunity == before.player.opportunity
    assert {k:n.age for k,n in before.world_npcs.items()} == {k:n.age for k,n in after.world_npcs.items()}
    assert after.player.formation_materials == []
    assert data['pact']['status'] == 'kept' and data['pact']['material']['id'] == identity
    assert [c['opened'] for c in data['chambers']] == [False, False, True]
    assert data['record_acquired'] and data['stored_mana'] == mirror.get(before)['stored_mana']
    assert data['paid_mana'] == mirror.get(before)['paid_mana']
    for action in ('mirror_decipher','mirror_isolate','mirror_assault'):
        for index in (0,1):
            with pytest.raises(ValueError,match='承诺'): act(site, action, chamber=str(index), **({'material_id':'missing'} if action=='mirror_isolate' else {}))
    act(site, 'mirror_leave')
    assert operations.view(site[2], after.id, 'known', MIRROR_ID)['mirror']['pact']['status'] == 'kept'
    act(site, 'mirror_enter')
    assert mirror.get(load(site)) == data
    assert GameState.from_dict(load(site).to_dict()).to_dict() == load(site).to_dict()


def test_release_requires_explicit_local_choice_then_real_combat_without_duplicate_rewards(site):
    repair(site, ready(site))
    act(site, 'mirror_leave')
    with pytest.raises(ValueError,match='进入'): act(site, 'mirror_release')
    act(site, 'mirror_enter')
    work = load(site)
    work.player.realm_index = 5
    work.player.hp, work.player.mp = max_hp(work.player), max_mp(work.player)
    site[0].store.save(work)
    act(site, 'mirror_release')
    for action in ('mirror_decipher','mirror_isolate'):
        with pytest.raises(ValueError,match='强攻'): act(site, action, chamber='0', **({'material_id':'missing'} if action=='mirror_isolate' else {}))
    with pytest.raises(ValueError): act(site, 'mirror_release')
    with patch.object(site[0], '_combat', wraps=site[0]._combat) as battle:
        act(site, 'mirror_assault', chamber='0')
        act(site, 'mirror_assault', chamber='1')
    assert battle.call_count == 2
    after = load(site)
    data = mirror.get(after)
    assert data['pact']['status'] == 'released' and data['record_acquired']
    assert len(after.player.formation_materials) == 2
    assert {m['id'] for m in after.player.formation_materials} == {c['reward']['id'] for c in data['chambers'][:2]}
    with pytest.raises(ValueError): act(site, 'mirror_decipher', chamber='2')
    with pytest.raises(ValueError): repair(site, data['pact']['material']['id'])
    assert data['stored_mana']+sum(c['guardian']['mana'] for c in data['chambers'] if c['guardian']) == pytest.approx(data['collected_mana'])


@pytest.mark.parametrize('action', ['mirror_decipher','mirror_isolate','mirror_assault'])
def test_prior_intervention_closes_offer(site, action):
    identity = ready(site)
    extra = material(site)
    if action == 'mirror_assault':
        altered = (*site[:2], replace(site[2], fight_mirror=lambda *a: ('defeat','暂退',1)))
        act(altered, action, chamber='0')
    else:
        act(site, action, chamber='0', **({'material_id':extra} if action=='mirror_isolate' else {}))
    before = site[0].store._path(site[1].id).read_bytes()
    with pytest.raises(ValueError,match='尚未'): repair(site, identity)
    assert site[0].store._path(site[1].id).read_bytes() == before


@pytest.mark.parametrize('gate', ['probe','material','rank','seal','custody','event','outside'])
def test_real_eligibility_and_no_input_loss(site, gate):
    if gate == 'probe': entered(site)
    else: prepared(site)
    identity = material(site)
    if gate == 'outside': act(site, 'mirror_leave')
    work = load(site)
    if gate == 'material': identity = 'absent'
    if gate == 'rank': work.player.realm_index = 3
    if gate == 'seal': work.player.sealed_cultivation = {'realm_index':4, 'layer':1}
    if gate == 'custody': work.player.imprisonment = {'holder_id':'test'}
    if gate == 'event': work.pending_event = {'id':'test'}
    site[0].store.save(work)
    before = site[0].store._path(work.id).read_bytes()
    with pytest.raises(ValueError): repair(site, identity)
    assert site[0].store._path(work.id).read_bytes() == before


def test_final_year_event_defers_record_and_resume_does_not_charge_again(site):
    identity = ready(site)
    before = load(site)
    result = repair(interrupted(site, last_year=True), identity)
    paused = load(site)
    assert result['status'] == 'paused' and result['progress'] == 3
    assert mirror.get(paused)['pact']['status'] == 'repairing' and not mirror.get(paused)['record_acquired']
    assert not paused.player.formation_materials
    clear_event(site)
    issue(site, 'resume', target=result['task_id'])
    after = load(site)
    assert after.player.age == before.player.age+3
    assert mirror.get(after)['pact']['status'] == 'kept'
    assert mirror.get(after)['paid_mana'] == mirror.get(before)['paid_mana']


@pytest.mark.parametrize('last_year', [False, True])
def test_cancel_keeps_installed_material_and_restores_original_exploration(site, last_year):
    identity = ready(site)
    result = repair(interrupted(site, last_year=last_year), identity)
    issue(site, 'cancel', target=result['task_id'])
    work = load(site)
    assert mirror.get(work)['pact']['status'] == 'cancelled'
    assert not work.player.formation_materials and not mirror.get(work)['record_acquired']
    clear_event(site)
    with pytest.raises(ValueError,match='一次'): repair(site, material(site))
    act(site, 'mirror_decipher', chamber='0')
    assert mirror.get(load(site))['chambers'][0]['opened']


def test_death_ends_pending_repair_without_record_or_material_refund(site):
    result = repair(interrupted(site, death=True), ready(site))
    after = load(site)
    assert result['status'] == 'failed' and mirror.get(after)['pact']['status'] == 'failed'
    assert not mirror.get(after)['record_acquired'] and not after.player.formation_materials


def test_old_save_pure_view_and_disabled_generation_preserve_choices(site):
    identity = ready(site)
    work = load(site)
    assert 'pact' not in mirror.get(work)
    work.heavens_state['generation_enabled'] = False
    site[0].store.save(work)
    before = site[0].store._path(work.id).read_bytes()
    for _ in range(3):
        operations.view(site[2], work.id, 'known', MIRROR_ID)
        operations.preview(site[2], work.id, 'mirror_repair', MIRROR_ID, {'material_id':identity})
    assert site[0].store._path(work.id).read_bytes() == before
    result = repair(site, identity)
    disk = site[0].store._path(work.id).read_bytes()
    assert operations.command(site[2], work.id, result['command_seq'], work.heavens_state['revision'], 'mirror_repair', MIRROR_ID, {'material_id':identity}) == result
    assert site[0].store._path(work.id).read_bytes() == disk


@pytest.mark.parametrize('action', ['repair','resume','release'])
def test_atomic_save_failure_keeps_material_record_and_permissions(site, action):
    identity = ready(site)
    task = None
    if action == 'resume':
        task = repair(interrupted(site), identity)['task_id']
        clear_event(site)
    if action == 'release': repair(site, identity)
    before = site[0].store._path(site[1].id).read_bytes()
    with patch.object(site[0].store, 'save', side_effect=OSError('disk full')):
        with pytest.raises(OSError):
            if action == 'repair': repair(site, identity)
            elif action == 'resume': issue(site, 'resume', target=task)
            else: act(site, 'mirror_release')
    assert site[0].store._path(site[1].id).read_bytes() == before


def test_completed_promise_survives_task_history_eviction(site):
    repair(site, ready(site))
    original = copy.deepcopy(mirror.get(load(site))['pact'])
    act(site, 'mirror_leave')
    work = load(site)
    work.player.location_id = 'wudi_plain'
    work.player.mp = max_mp(work.player)
    site[0].store.save(work)
    identity = material(site)
    for action in ('ruins_enter', 'ruins_observe', 'ruins_verify', 'ruins_read', 'ruins_replace'):
        issue(site, action, {'material_id':identity} if action == 'ruins_replace' else {}, target='causal_ruins')
    after = load(site)
    assert all(t['id'] != original['task_id'] for t in after.heavens_state['runtime']['tasks'])
    assert mirror.get(after)['pact'] == original
    assert GameState.from_dict(after.to_dict()).to_dict() == after.to_dict()


@pytest.mark.parametrize('kind', ['core','record','time','material','duplicate','task','status','release','no_pact','false_victory'])
def test_corrupt_contract_rejected_without_repairing_the_document(site, kind):
    repair(site, ready(site))
    work = load(site)
    data = mirror.get(work)
    pact = data['pact']
    if kind == 'core': data['chambers'][0]['opened'] = True
    if kind == 'record': data['record_acquired'] = data['chambers'][2]['opened'] = False
    if kind == 'time': pact['settled_at'] = pact['started_at']+2
    if kind == 'material': pact['material']['origin_world'] = 'celestial'
    if kind == 'duplicate': work.player.formation_materials.append(copy.deepcopy(pact['material']))
    if kind == 'task': pact['task_id'] = 'heavens-task-999'
    if kind == 'status': pact['status'] = 'repairing'
    if kind == 'release': pact['released_at'] = pact['settled_at']
    if kind == 'no_pact': del data['pact']
    if kind == 'false_victory':
        pact.update(status='released', released_at=pact['settled_at'])
        data['chambers'][0].update(opened=True, guardian=dict(mana=0, power=data['definition']['guardian_power'], wounds=1, encounters=1, result='defeat'))
    before = copy.deepcopy(work.heavens_state)
    with pytest.raises(ValueError):
        validate_state(work.heavens_state)
        validate_references(work)
    assert work.heavens_state == before

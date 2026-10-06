"""Two anomaly destinations, real residents and independently owned knowledge."""
import copy
from dataclasses import replace
from hashlib import sha256

import pytest

from cultivation_life.models import GameState, SectNpc
from cultivation_life.npc_custody import detain_person, release_person
from cultivation_life.person_assignments import research_assignment
from cultivation_life.system.heavens import autonomy, operations, survey
from cultivation_life.system.heavens.calendar import YearContext, year_step
from cultivation_life.system.heavens.definitions import MIRROR_ID, RUINS_ID
from cultivation_life.system.heavens.schema import validate_state, validate_references
from test_heavens_m1 import local, issue
from test_heavens_ruins import site, load, act
from test_heavens_autonomy import setup, annual


def command(site, action, **options):
    return issue(site, action, options, target=MIRROR_ID)


def wait(site, years):
    for _ in range(years):
        command(site, 'survey_wait')
    return load(site)


def ready(site, *, autonomous=False, location='muling_desert'):
    game, identity = setup(site)
    game.world_npcs[identity].location_id = location
    game.world_npcs[identity].affinity = 0 if autonomous else 30
    site[0].store.save(game)
    command(site, 'mirror_enter')
    command(site, 'mirror_leave')
    if autonomous:
        game = load(site)
        game.player.location_id = 'wudi_plain'
        site[0].store.save(game)
    else:
        command(site, 'survey_start', person_id=identity)
    return load(site), identity


def enter(site):
    game = load(site)
    game.player.location_id = 'muling_desert'
    site[0].store.save(game)
    command(site, 'mirror_enter')
    return load(site)


def test_mirror_survey_preserves_mechanisms_mana_and_unique_rewards(site):
    before, identity = ready(site)
    original = copy.deepcopy(before.heavens_state['runtime']['mirror'])
    arrived = wait(site, 2)
    npc = arrived.world_npcs[identity]
    assert (npc.world, npc.location_id) == ('rift', 'mirror_hall')
    assert npc.age == before.world_npcs[identity].age + 2
    assert research_assignment(arrived, identity) is survey.get(arrived, MIRROR_ID)
    frozen = wait(site, 2)
    assert frozen.world_npcs[identity].to_dict() == npc.to_dict()
    enter(site)
    learned = wait(site, 8)
    mirror = learned.heavens_state['runtime']['mirror']
    assert survey.get(learned, MIRROR_ID)['learned']
    assert not survey.get(learned, MIRROR_ID)['shared']
    assert {key:value for key,value in mirror.items() if key != 'survey'} == {key:value for key,value in original.items() if key != 'survey'}
    assert learned.player.formation_materials == []
    command(site, 'survey_share')
    with pytest.raises(ValueError, match='试探'):
        command(site, 'mirror_decipher', chamber='0')
    returned = wait(site, 1)
    assert returned.world_npcs[identity].location_id == 'muling_desert'
    assert returned.world_npcs[identity].age == before.world_npcs[identity].age + 11
    assert not research_assignment(returned, identity)
    command(site, 'mirror_probe')
    state = load(site)
    proposal = operations.preview(site[2], state.id, 'mirror_decipher', MIRROR_ID, {'chamber':'0'})
    assert proposal['years'] == 2 and proposal['costs']['mp'] > 0
    paid = state.heavens_state['runtime']['mirror']['paid_mana']
    command(site, 'mirror_decipher', chamber='0')
    done = load(site)
    assert done.player.age == state.player.age + 2
    assert done.heavens_state['runtime']['mirror']['paid_mana'] == pytest.approx(paid + proposal['costs']['mp'])
    assert len(done.player.formation_materials) == 1
    assert GameState.from_dict(done.to_dict()).to_dict() == done.to_dict()
    with pytest.raises(ValueError, match='已解开'):
        command(site, 'mirror_decipher', chamber='0')


@pytest.mark.parametrize('location,target', [('muling_desert', MIRROR_ID), ('wudi_plain', RUINS_ID)])
def test_autonomous_destination_prefers_residents_actual_local_entrance(site, location, target):
    before, identity = ready(site, autonomous=True, location=location)
    game = annual(site)
    row = survey.get(game, target)
    assert row and row['autonomous'] and row['person_id'] == identity
    other = RUINS_ID if target == MIRROR_ID else MIRROR_ID
    assert not survey.get(game, other)
    assert set(game.world_npcs) == set(before.world_npcs)


def test_autonomous_mirror_only_discloses_after_actual_meeting(site):
    before, identity = ready(site, autonomous=True)
    game = annual(site, 3)
    assert survey.get(game, MIRROR_ID)['phase'] == 'studying'
    assert not survey.get(game, MIRROR_ID)['introduced']
    hidden = operations.project(game, 'known', deps=site[2])['mirror']['survey']
    assert hidden == dict(status='unmet', actions=[], candidates=[])
    assert game.heavens_state['runtime']['history'] == before.heavens_state['runtime']['history']
    met = enter(site)
    assert survey.get(met, MIRROR_ID)['introduced']
    with pytest.raises(ValueError, match='交情'):
        command(site, 'survey_recall')
    learned = wait(site, 8)
    with pytest.raises(ValueError, match='交情'):
        command(site, 'survey_share')
    learned.world_npcs[identity].affinity = 20
    site[0].store.save(learned)
    command(site, 'survey_share')
    with pytest.raises(ValueError, match='尚无新的'):
        command(site, 'survey_share')


def test_other_anomaly_clock_cannot_advance_mirror_resident(site):
    _, identity = ready(site)
    arrived = wait(site, 2)
    game = load(site)
    game.player.location_id = 'wudi_plain'
    site[0].store.save(game)
    act(site, 'ruins_enter')
    act(site, 'ruins_observe')
    frozen = load(site)
    assert frozen.world_npcs[identity].to_dict() == arrived.world_npcs[identity].to_dict()
    assert survey.get(frozen, MIRROR_ID) == survey.get(arrived, MIRROR_ID)


@pytest.mark.parametrize('years', [0, 2, 7])
def test_early_return_uses_one_spatial_year_and_preserves_partial_notes(site, years):
    before, identity = ready(site)
    wait(site, 2)
    enter(site)
    wait(site, years)
    command(site, 'survey_recall')
    game = wait(site, 1)
    row = survey.get(game, MIRROR_ID)
    assert row['status'] == 'completed' and row['observed'] == (years >= 2)
    assert not row['learned'] and not row['shared']
    assert row['elapsed'] == 3 + years
    assert game.world_npcs[identity].age == before.world_npcs[identity].age + 3 + years


def test_death_is_not_replaced_and_spatial_reference_retained(site):
    _, identity = ready(site)
    wait(site, 2)
    game = enter(site)
    game.world_npcs[identity].lifespan = game.world_npcs[identity].age + 1
    site[0].store.save(game)
    dead = wait(site, 1)
    assert not dead.world_npcs[identity].alive
    assert survey.get(dead, MIRROR_ID)['status'] == 'failed'
    validate_references(dead)
    assert dead.heavens_state['runtime']['mirror']['paid_mana'] == 0


def test_custody_pauses_mirror_research_and_disabling_generation_preserves_it(site):
    _, identity = ready(site)
    wait(site, 2)
    game = enter(site)
    game.heavens_state['generation_enabled'] = False
    detain_person(game, game.world_npcs[identity].to_dict(), SectNpc)
    site[0].store.save(game)
    paused = wait(site, 2)
    assert survey.get(paused, MIRROR_ID)['progress'] == 0
    release_person(paused, identity)
    site[0].store.save(paused)
    continued = wait(site, 2)
    assert survey.get(continued, MIRROR_ID)['progress'] == 2
    assert survey.get(continued, MIRROR_ID)['observed']


def test_mirror_notes_do_not_shorten_ruins_reading(site):
    ready(site)
    wait(site, 2)
    enter(site)
    wait(site, 8)
    command(site, 'survey_share')
    wait(site, 1)
    command(site, 'mirror_leave')
    game = load(site)
    game.player.location_id = 'wudi_plain'
    site[0].store.save(game)
    act(site, 'ruins_enter')
    act(site, 'ruins_observe')
    act(site, 'ruins_verify')
    assert operations.preview(site[2], game.id, 'ruins_read', RUINS_ID, {})['years'] == 6


def test_nonlocal_destination_choice_is_stable_and_does_not_draw_rng(site):
    game, _ = ready(site, autonomous=True, location='green_stone_town')
    another = copy.deepcopy(game)
    rng, counter = game.rng_state, game.heavens_state['runtime']['rng_counter']
    autonomy.year_step(site[2], game)
    autonomy.year_step(site[2], another)
    chosen = next(t for t in survey.SITES if survey.get(game, t))
    assert survey.get(game, chosen) == survey.get(another, chosen)
    assert game.rng_state == rng and game.heavens_state['runtime']['rng_counter'] == counter


def test_cannot_assign_a_second_anomaly_or_reuse_the_same_resident(site):
    _, identity = ready(site)
    command(site, 'survey_recall')
    game = load(site)
    game.player.location_id = 'wudi_plain'
    site[0].store.save(game)
    act(site, 'ruins_enter')
    act(site, 'ruins_leave')
    with pytest.raises(ValueError, match='选择'):
        act(site, 'survey_start', person_id=identity)
    game = load(site)
    npc = SectNpc('second-resident', '研纹客', '', 4, 1, 80, 1000,
                  spirit_root='supreme_water', world='human', affinity=30, location_id='wudi_plain')
    game.world_npcs[npc.id] = npc
    site[0].store.save(game)
    act(site, 'survey_start', person_id=npc.id)
    validate_state(load(site).heavens_state)


def test_manual_ongoing_survey_blocks_other_destination(site):
    ready(site)
    game = load(site)
    game.player.location_id = 'wudi_plain'
    site[0].store.save(game)
    act(site, 'ruins_enter')
    act(site, 'ruins_leave')
    with pytest.raises(ValueError, match='同时'):
        act(site, 'survey_start', person_id='independent-resident')
    assert site[2].survey_candidates(load(site), autonomous=True) == []


def test_navigation_queries_and_duplicate_command_are_pure(site):
    ready(site)
    game = load(site)
    before = copy.deepcopy(game.to_dict())
    for target in (MIRROR_ID, RUINS_ID):
        operations.project(game, 'known', target, deps=site[2])
    assert before == game.to_dict()
    seq, revision = game.heavens_state['command_seq'] + 1, game.heavens_state['revision']
    one = operations.command(site[2], game.id, seq, revision, 'survey_wait', MIRROR_ID, {})
    saved = site[0].store._path(game.id).read_bytes()
    two = operations.command(site[2], game.id, seq, revision, 'survey_wait', MIRROR_ID, {})
    assert one == two and site[0].store._path(game.id).read_bytes() == saved


def test_persistence_failure_cannot_commit_survey_arrival(site, monkeypatch):
    _, identity = ready(site)
    wait(site, 1)
    game = load(site)
    saved = site[0].store._path(game.id).read_bytes()
    def fail(work):
        assert work.world_npcs[identity].location_id == 'mirror_hall'
        raise OSError('save failure')
    monkeypatch.setattr(site[0].store, 'save', fail)
    with pytest.raises(OSError):
        command(site, 'survey_wait')
    assert site[0].store._path(game.id).read_bytes() == saved


@pytest.mark.parametrize('corrupt', ['duplicate', 'progress', 'shared', 'wait_mana', 'wait_duration', 'membership'])
def test_strict_schema_rejects_unearned_or_duplicate_facts(site, corrupt):
    ready(site)
    game = wait(site, 1)
    runtime = game.heavens_state['runtime']
    row = survey.get(game, MIRROR_ID)
    if corrupt == 'duplicate':
        from cultivation_life.system.heavens import ruins
        r = ruins.create(site[2], game)
        site[2].prepare_ruins(game, r)
        r['survey'] = copy.deepcopy(row)
    if corrupt == 'progress': row['progress'] = 2
    if corrupt == 'shared': row['shared'] = True
    if corrupt == 'wait_mana': runtime['tasks'][-1]['escrow']['mp_paid'] = 1
    if corrupt == 'wait_duration': runtime['tasks'][-1]['duration'] = 2
    if corrupt == 'membership':
        game.spatial_state['instances'][runtime['mirror']['scene_id']]['npc_ids'].append(row['person_id'])
    with pytest.raises(ValueError):
        validate_state(game.heavens_state)
        validate_references(game)


def test_later_discovery_window_accepts_old_completed_autonomous_survey(site):
    _, identity = ready(site, autonomous=True, location='wudi_plain')
    game = annual(site)
    # The ruins traveler can be encountered and asked to stop at the actual entrance.
    game.world_npcs[identity].affinity = 30
    site[0].store.save(game)
    act(site, 'survey_recall')
    game = load(site)
    second = SectNpc('later-resident', '照纹客', '', 4, 1, 80, 1000,
                     spirit_root='supreme_water', world='human', affinity=0, location_id='muling_desert')
    game.world_npcs[second.id] = second
    window = next(w for w in range(2,100) if int.from_bytes(sha256(
        f'{game.seed}:heavens:resident-survey:v1:{w}'.encode()).digest()[:8], 'big') < 2**62)
    game.heavens_state['runtime'].update(processed_years=window*100-1,last_year_key=window*100-1)
    autonomy.year_step(site[2], game)
    year_step(site[2], game, YearContext(window*100))
    assert survey.get(game, MIRROR_ID)['person_id'] == second.id
    assert survey.get(game)['status'] == 'cancelled'
    validate_state(game.heavens_state)
    validate_references(game)


def test_wait_interruption_can_resume_without_duplicate_npc_year(site):
    ready(site)
    calls = []
    actual = site[2].advance_year
    def interrupted(game, rng, news):
        calls.append(1)
        actual(game, rng, news)
        game.pending_event = {'type':'test'}
        return False
    paused = (site[0], site[1], replace(site[2], advance_year=interrupted))
    command(paused, 'survey_wait')
    game = load(site)
    task = game.heavens_state['runtime']['tasks'][-1]
    progress = survey.get(game, MIRROR_ID)['progress']
    game.pending_event = None
    site[0].store.save(game)
    if task['status'] == 'paused':
        issue(site, 'resume', target=task['id'])
    assert survey.get(load(site), MIRROR_ID)['progress'] == progress

"""Resident-first mirror discovery without remote player knowledge or MP anchoring."""
import copy
from dataclasses import replace
from unittest.mock import Mock

import pytest

from cultivation_life.models import GameState
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system import spatial
from cultivation_life.system.heavens import autonomy, mirror, operations, survey
from cultivation_life.system.heavens.calendar import YearContext, year_step
from cultivation_life.system.heavens.definitions import MIRROR_ID
from cultivation_life.system.heavens.schema import validate_state, validate_references
from test_heavens_m1 import local
from test_heavens_ruins import site, load
from test_heavens_autonomy import setup, annual
from test_heavens_mirror_survey import command, enter, wait


def undiscovered(site, *, local_resident=True, success=True):
    game, identity = setup(site, success=success)
    game.player.location_id = 'wudi_plain'
    game.world_npcs[identity].location_id = 'muling_desert' if local_resident else 'wudi_plain'
    site[0].store.save(game)
    return game, identity


def test_resident_discovers_hidden_mirror_without_player_entry_or_new_person(site):
    before, identity = undiscovered(site)
    game = annual(site)
    m = mirror.get(game)
    assert m['created_year'] == 100 and not m['player_known']
    assert m['capacity_pending'] and m['mana_capacity'] == 0
    assert game.heavens_state['runtime']['history'] == []
    assert game.heavens_state['definition_versions'][MIRROR_ID] == 1
    assert (game.player.world, game.player.location_id) == ('human', 'wudi_plain')
    assert game.spatial_state.get('current') is None
    assert game.spatial_state['instances'][m['scene_id']]['visits'] == 0
    assert game.spatial_state['instances'][m['scene_id']]['npc_ids'] == []
    assert set(game.world_npcs) == set(before.world_npcs)
    assert survey.get(game, MIRROR_ID)['person_id'] == identity
    assert not survey.get(game)
    hidden = operations.project(game, 'known', MIRROR_ID, deps=site[2])
    assert not hidden['mirror']['known']
    assert hidden['mirror']['survey'] == dict(status='unmet', actions=[], candidates=[])
    assert not any(key in hidden['mirror'] for key in ('scene_id', 'chambers', 'traces', 'mana_capacity', 'capacity_pending'))
    assert not any(row['id'] == MIRROR_ID for row in hidden['records'])
    assert spatial.public(game)['scene'] is None
    assert not spatial.public(game)['visited']
    assert GameState.from_dict(game.to_dict()).to_dict() == game.to_dict()


def test_real_arrival_then_first_player_entry_anchors_capacity_once(site):
    _, identity = undiscovered(site)
    arrived = annual(site, 3)
    m = mirror.get(arrived)
    assert arrived.world_npcs[identity].location_id == 'mirror_hall'
    assert not m['player_known'] and m['mana_capacity'] == 0
    assert arrived.spatial_state['instances'][m['scene_id']]['npc_ids'] == [identity]
    frozen = annual(site, 2)
    assert frozen.world_npcs[identity].to_dict() == arrived.world_npcs[identity].to_dict()
    frozen.player.permanent_intrinsic_mp_bonus += 1000
    frozen.player.hp, frozen.player.mp = max_hp(frozen.player), max_mp(frozen.player)
    expected = max_mp(frozen.player) * m['definition']['capacity_fraction']
    site[0].store.save(frozen)
    met = enter(site)
    assert mirror.get(met)['mana_capacity'] == expected
    assert 'capacity_pending' not in mirror.get(met)
    assert mirror.get(met)['player_known'] and survey.get(met, MIRROR_ID)['introduced']
    assert not mirror.get(met)['probed'] and met.player.formation_materials == []
    command(site, 'mirror_leave')
    changed = load(site)
    changed.player.permanent_intrinsic_mp_bonus += 9000
    site[0].store.save(changed)
    assert mirror.get(enter(site))['mana_capacity'] == expected


def test_meeting_at_entrance_reveals_person_but_does_not_anchor_capacity(site):
    game, _ = undiscovered(site)
    game.player.location_id = 'muling_desert'
    site[0].store.save(game)
    met = annual(site)
    assert survey.get(met, MIRROR_ID)['introduced']
    m = mirror.get(met)
    assert m['player_known'] and m['capacity_pending'] and m['mana_capacity'] == 0
    snapshot = copy.deepcopy(met.to_dict())
    for _ in range(3):
        public = operations.project(met, 'known', MIRROR_ID, deps=site[2])
        assert public['mirror']['known'] and public['mirror']['capacity_pending']
        operations.preview(site[2], met.id, 'mirror_enter', MIRROR_ID, {})
    assert met.to_dict() == snapshot
    assert load(site).to_dict() == snapshot


@pytest.mark.parametrize('world', ['celestial', 'asura', 'nether', 'reincarnation'])
def test_distant_highest_world_player_cannot_supply_discovery_capacity(site, world):
    game, identity = undiscovered(site)
    game.player.world, game.player.realm_index = world, 9
    def no_remote_mana(_):
        raise AssertionError('autonomous generation must not read player mirror MP')
    deps = replace(site[2], read_mirror_facts=no_remote_mana)
    # Reveal must ask about actual ability to perceive only after generation.
    # A distant player cannot meet this resident, so their MP remains irrelevant.
    original = game.rng_state
    autonomy.year_step(site[2], game)
    assert mirror.get(game)['mana_capacity'] == 0
    assert game.world_npcs[identity].world == 'human'
    assert not mirror.get(game)['player_known']
    assert game.rng_state == original
    # Direct hidden creation also never consults player-derived capacity.
    duplicate = copy.deepcopy(game)
    duplicate.heavens_state['runtime'].pop('mirror')
    hidden = mirror.create(deps, duplicate, known=False, year=100)
    assert hidden['mana_capacity'] == 0


def test_nonlocal_resident_does_not_discover_an_unseen_mirror(site):
    undiscovered(site, local_resident=False)
    game = annual(site)
    assert mirror.get(game) is None and survey.get(game)


def test_failed_window_is_spent_even_if_resident_is_later_available(site):
    undiscovered(site, success=False)
    game = annual(site)
    assert not mirror.get(game)
    assert game.heavens_state['runtime']['survey_discovery_window'] == 1
    assert mirror.get(annual(site, 3)) is None


def test_discovery_scans_roster_once_and_preserves_both_rng_streams(site):
    game, _ = undiscovered(site)
    read = Mock(wraps=site[2].survey_candidates)
    deps = replace(site[2], survey_candidates=read)
    rng = game.rng_state
    counter = game.heavens_state['runtime']['rng_counter']
    autonomy.year_step(deps, game)
    autonomy.year_step(deps, game)
    assert read.call_count == 1
    assert game.rng_state == rng and game.heavens_state['runtime']['rng_counter'] == counter
    year_step(site[2], game, YearContext(100))
    validate_state(game.heavens_state)
    validate_references(game)


def test_disabling_generation_preserves_hidden_scene_and_real_research(site):
    _, identity = undiscovered(site)
    game = annual(site)
    game.heavens_state['generation_enabled'] = False
    site[0].store.save(game)
    annual(site, 2)
    enter(site)
    learned = wait(site, 8)
    assert survey.get(learned, MIRROR_ID)['learned']
    assert mirror.get(learned)['paid_mana'] == 0
    assert learned.player.formation_materials == []
    learned.world_npcs[identity].affinity = 20
    site[0].store.save(learned)
    command(site, 'survey_share')
    wait(site, 1)
    command(site, 'mirror_probe')
    command(site, 'mirror_decipher', chamber='0')
    done = load(site)
    assert len(done.player.formation_materials) == 1
    assert done.heavens_state['runtime']['tasks'][-1]['duration'] == 2


def test_death_before_arrival_leaves_hidden_scene_without_replacement(site):
    _, identity = undiscovered(site)
    game = annual(site)
    scene_id = mirror.get(game)['scene_id']
    game.world_npcs[identity].lifespan = game.world_npcs[identity].age + 1
    site[0].store.save(game)
    failed = annual(site)
    assert survey.get(failed, MIRROR_ID)['status'] == 'failed'
    assert not mirror.get(failed)['player_known']
    assert mirror.get(failed)['mana_capacity'] == 0
    entered = enter(site)
    assert mirror.get(entered)['scene_id'] == scene_id
    assert mirror.get(entered)['mana_capacity'] > 0
    assert not survey.get(entered, MIRROR_ID)['introduced']
    assert not entered.world_npcs[identity].alive


@pytest.mark.parametrize('gate', ['setting', 'content', 'space', 'early'])
def test_discovery_gates_do_not_prepare_hidden_scenes(site, gate):
    game, _ = undiscovered(site)
    deps = site[2]
    if gate == 'setting': game.heavens_state['generation_enabled'] = False
    if gate == 'content': deps = replace(deps, get_definitions=lambda:replace(site[2].get_definitions(),generation_available=False))
    if gate == 'space': game.player.world = 'rift'
    if gate == 'early': game.heavens_state['runtime'].update(processed_years=98, last_year_key=98)
    before = copy.deepcopy(game.to_dict())
    autonomy.year_step(deps, game)
    assert game.to_dict() == before


def test_rejected_low_rank_entry_does_not_freeze_capacity(site):
    undiscovered(site)
    game = annual(site, 3)
    game.player.realm_index = 3
    game.player.location_id = 'muling_desert'
    site[0].store.save(game)
    with pytest.raises(ValueError): command(site, 'mirror_enter')
    assert mirror.get(load(site))['capacity_pending']
    assert mirror.get(load(site))['mana_capacity'] == 0


def test_entry_save_failure_rolls_back_knowledge_capacity_and_visits(site, monkeypatch):
    undiscovered(site)
    game = annual(site, 3)
    game.player.location_id = 'muling_desert'
    site[0].store.save(game)
    before = site[0].store._path(game.id).read_bytes()
    def fail(work):
        assert mirror.get(work)['mana_capacity'] > 0
        assert mirror.get(work)['player_known'] and survey.get(work, MIRROR_ID)['introduced']
        assert work.player.world == 'rift'
        raise OSError('disk full')
    monkeypatch.setattr(site[0].store, 'save', fail)
    with pytest.raises(OSError): command(site, 'mirror_enter')
    assert site[0].store._path(game.id).read_bytes() == before


def test_first_entry_retry_cannot_reanchor_after_player_mana_changes(site):
    undiscovered(site)
    game = annual(site, 3)
    game.player.location_id = 'muling_desert'
    site[0].store.save(game)
    seq, revision = game.heavens_state['command_seq'] + 1, game.heavens_state['revision']
    original = operations.command(site[2], game.id, seq, revision, 'mirror_enter', MIRROR_ID, {})
    game = load(site)
    capacity = mirror.get(game)['mana_capacity']
    game.player.permanent_intrinsic_mp_bonus += 9000
    site[0].store.save(game)
    before = site[0].store._path(game.id).read_bytes()
    repeated = operations.command(site[2], game.id, seq, revision, 'mirror_enter', MIRROR_ID, {})
    assert repeated == original and site[0].store._path(game.id).read_bytes() == before
    assert mirror.get(load(site))['mana_capacity'] == capacity


def test_normal_action_save_failure_rolls_back_hidden_generation(site, monkeypatch):
    game, identity = undiscovered(site)
    engine = site[0]
    engine._load(game.id)
    loaded = engine._load(game.id)
    # Retain the original catalog identities but leave only this witness alive,
    # so the real public rest transaction has a deterministic eligible resident.
    for key, npc in loaded.world_npcs.items():
        if key != identity:
            npc.alive, npc.death_reason = False, '测试寿尽'
    engine.store.save(loaded)
    engine._load(game.id)
    before = engine.store._path(game.id).read_bytes()
    def fail(work):
        assert mirror.get(work)['capacity_pending']
        assert survey.get(work, MIRROR_ID)['person_id'] == identity
        assert not mirror.get(work)['player_known']
        raise OSError('disk full')
    monkeypatch.setattr(engine.store, 'save', fail)
    with pytest.raises(OSError): engine.advance(game.id, 'rest', 1)
    assert engine.store._path(game.id).read_bytes() == before


@pytest.mark.parametrize('kind', ['capacity', 'paid', 'pending_bool', 'missing_pending', 'missing_visibility',
                                  'visibility_bool', 'known_without_meeting', 'introduced', 'probed', 'visit', 'current'])
def test_hidden_or_unanchored_mirror_rejects_impossible_facts(site, kind):
    undiscovered(site)
    game = annual(site)
    m = mirror.get(game)
    if kind == 'capacity': m['mana_capacity'] = 100
    if kind == 'paid': m['paid_mana'] = 1
    if kind == 'pending_bool': m['capacity_pending'] = 1
    if kind == 'missing_pending': m.pop('capacity_pending')
    if kind == 'missing_visibility': m.pop('player_known')
    if kind == 'visibility_bool': m['player_known'] = 1
    if kind == 'known_without_meeting': m['player_known'] = True
    if kind == 'introduced': m['survey']['introduced'] = True
    if kind == 'probed': m['probed'] = True
    if kind == 'visit': game.spatial_state['instances'][m['scene_id']]['visits'] = 1
    if kind == 'current': game.spatial_state['current'] = m['scene_id']
    with pytest.raises(ValueError):
        validate_state(game.heavens_state)
        validate_references(game)


def test_legacy_mirror_keeps_existing_capacity_and_optional_field_shape(site):
    game = load(site)
    game.player.location_id = 'muling_desert'
    site[0].store.save(game)
    command(site, 'mirror_enter')
    command(site, 'mirror_leave')
    original = copy.deepcopy(mirror.get(load(site)))
    assert 'player_known' not in original and 'capacity_pending' not in original
    game = load(site)
    game.player.permanent_intrinsic_mp_bonus += 9000
    site[0].store.save(game)
    assert mirror.get(enter(site)) == original

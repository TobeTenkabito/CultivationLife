"""Seven original learned books, immutable first sightings, legitimate selection."""
import copy
import json
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

from cultivation_life.content_registry import TECHNIQUE_CATALOG, ROOT_DEFINITIONS
from cultivation_life.models import Player, SectNpc, Technique
from cultivation_life.rules import learn_technique, assign_technique, can_practice_technique
from cultivation_life.system.duel_techniques import select, ensure_npc, target_count, npc_books, public, prepare_visible
from cultivation_life.system.technique_effect_provider import project
from cultivation_life.system.npc_techniques import learn
from test_technique_effect_foundation import effect


def books():
    return [Technique(id=f'duel-test-{i}', name=f'试法{i}', category='spiritual', grade=1,
                      opportunity_bonus=1, hp_bonus=1, mp_bonus=1, combat_bonus=1,
                      combat_effect=effect(), sources={'spirit':1}, combat_requirements={}) for i in range(9)]


def player():
    return Player('试法者', 'supreme_metal', realm_index=6)


def npc(identity='fixed-person', rank=6, root='supreme_metal'):
    return SectNpc(identity, '试法人物', '', rank, 1, 30, None, spirit_root=root)


def context():
    return SimpleNamespace(doctrine_state={}, authored_techniques={})


def test_player_requires_successful_combat_equipment_not_just_learning_or_main():
    p = player()
    b = books()[0]
    learn_technique(p, b)
    assign_technique(p, b, 'main')
    with pytest.raises(ValueError, match='先成功装备'):
        select(p, b.id)
    assert not project(context(), p, player=True)
    assign_technique(p, b, 'combat')
    select(p, b.id)
    assert [row['id'] for row in project(context(), p, player=True)] == [b.id]


def test_seven_limit_duplicate_rejection_removal_and_retained_original_pool():
    p = player()
    for b in books():
        assign_technique(p, b, 'combat')
    for b in p.combat_techniques[:7]:
        select(p, b.id)
    before = copy.deepcopy(p.to_dict())
    for identity in (books()[0].id, books()[7].id):
        with pytest.raises(ValueError):
            select(p, identity)
        assert p.to_dict() == before
    assert len(project(context(), p, player=True)) == 7
    select(p, books()[0].id, remove=True)
    select(p, books()[7].id)
    assert len(p.combat_techniques) == 9 and len(p.duel_technique_ids) == 7
    restored = Player.from_dict(json.loads(json.dumps(p.to_dict())))
    assert restored.duel_technique_ids == p.duel_technique_ids


def test_failed_base_combat_assignment_never_adds_duel_candidate():
    p = player()
    b = books()[0]
    b.required_affinities = ['water', 'fire']
    learn_technique(p, b)
    with pytest.raises(ValueError):
        assign_technique(p, b, 'combat')
    with pytest.raises(ValueError):
        select(p, b.id)
    assert not public(p)['candidates']


def test_lost_qualification_suspends_effect_without_reroll_or_free_slot():
    p, b = player(), books()[0]
    b.effective_worlds = ['human']
    assign_technique(p, b, 'combat'); select(p, b.id)
    p.world = 'spirit'
    assert not project(context(), p, player=True)
    assert p.duel_technique_ids == [b.id]
    assert not public(p)['candidates'][0]['active']
    select(p, b.id, remove=True)
    assert not p.duel_technique_ids


@pytest.mark.parametrize('bad', [['x']*2, [str(i) for i in range(8)], [1], 'x', None])
def test_invalid_player_selection_save_rejected(bad):
    raw = player().to_dict(); raw['duel_technique_ids'] = bad
    with pytest.raises(ValueError):
        Player.from_dict(raw)


@pytest.mark.parametrize('rank,floor', [(0,0),(1,1),(2,1),(3,1),(4,3),(5,5),(6,7),(9,7),(12,7)])
def test_npc_floor_upper_bound_root_and_realm(rank, floor):
    for index in range(12):
        person = npc(f'person-{rank}-{index}', rank)
        ensure_npc(person)
        assert floor <= len(person.duel_technique_ids) <= (0 if rank == 0 else 7)
        if rank >= 6:
            assert len(person.duel_technique_ids) == 7
        for key in person.duel_technique_ids:
            b = TECHNIQUE_CATALOG[key]
            assert b.grade <= rank and can_practice_technique(person.spirit_root, b)
            assert key in person.technique_levels


def test_filling_probability_increases_by_realm_without_global_rng():
    counts = [sum(target_count(rank, random.Random(index)) for index in range(1000)) for rank in range(1, 7)]
    assert counts == sorted(counts) and len(set(counts)) == 6


def test_each_root_has_seven_legal_books_at_void_realm():
    for root in ROOT_DEFINITIONS:
        person = npc('root-' + root, 6, root)
        ensure_npc(person)
        assert len(person.duel_technique_ids) == 7, root
        assert all(can_practice_technique(root, TECHNIQUE_CATALOG[k]) for k in person.duel_technique_ids)


def test_scripted_person_without_known_root_uses_only_unconditional_neutral_books():
    person = npc('unrecorded-root', 6, '')
    ensure_npc(person)
    assert len(person.duel_technique_ids) == 7 and person.spirit_root == ''
    assert all(TECHNIQUE_CATALOG[k].element == 'neutral' and not TECHNIQUE_CATALOG[k].required_affinities
               for k in person.duel_technique_ids)


def test_fixed_person_does_not_reroll_on_reencounter_levelup_order_or_reload():
    person = npc('persistent', 4)
    state = random.getstate()
    assert ensure_npc(person)
    before = copy.deepcopy(person.duel_technique_ids)
    twin = npc('persistent', 4)
    ensure_npc(npc('unrelated')); ensure_npc(twin)
    assert before == twin.duel_technique_ids and random.getstate() == state
    person.realm_index = 12
    assert not ensure_npc(person) and person.duel_technique_ids == before
    restored = SectNpc.from_dict(json.loads(json.dumps(person.to_dict())))
    assert not ensure_npc(restored) and restored.duel_technique_ids == before


def test_existing_legal_low_grade_book_preferred_and_illegal_high_grade_excluded():
    person = npc(rank=1)
    low = next(t for t in TECHNIQUE_CATALOG.values() if t.grade == 1 and t.category == 'spiritual' and t.element == 'neutral')
    high = next(t for t in TECHNIQUE_CATALOG.values() if t.grade == 5 and t.category == 'spiritual')
    learn(person, low, level=5); learn(person, high)
    ensure_npc(person)
    assert low.id in person.duel_technique_ids and high.id not in person.duel_technique_ids
    assert person.technique_levels[low.id] == 5


def test_cultivation_updates_existing_book_level_without_randomizing_loadout():
    person = npc()
    ensure_npc(person)
    before = list(person.duel_technique_ids)
    selected = TECHNIQUE_CATALOG[before[0]]
    learn(person, selected, level=4)
    assert person.duel_technique_ids == before
    assert next(b for b in npc_books(context(), person) if b.id == selected.id).level == 4


def test_explicit_combat_training_replaces_only_one_slot_and_rejects_illegal_book():
    person = npc()
    ensure_npc(person)
    before = list(person.duel_technique_ids)
    new = next(t for t in TECHNIQUE_CATALOG.values() if t.id not in before
               and t.category == 'spiritual' and t.grade == 1 and t.element == 'neutral')
    learn(person, new, slot='combat')
    assert person.duel_technique_ids == before[:-1] + [new.id]
    saved = copy.deepcopy(person.to_dict())
    illegal = copy.deepcopy(new); illegal.grade = 12
    with pytest.raises(ValueError):
        learn(person, illegal, slot='combat')
    assert person.to_dict() == saved


def test_readonly_projection_never_initializes_person():
    person = npc()
    before = copy.deepcopy(person.to_dict())
    assert not project(context(), person)
    assert person.to_dict() == before


def test_first_seen_applicant_and_household_owner_are_frozen():
    from cultivation_life.models import GameState
    game = GameState('visible-relations', 1, player(), 'created', 'updated')
    applicant, owner = npc('applicant', 4), npc('household-owner', 6)
    game.relationship_npcs.update({applicant.id:applicant, owner.id:owner})
    game.player.disciple_requests.append(game.link_relationship({'id':applicant.id}))
    game.player.concubine_status = {'owner_id':owner.id}
    assert prepare_visible(game)
    assert 3 <= len(applicant.duel_technique_ids) <= 7
    assert len(owner.duel_technique_ids) == 7
    assert not prepare_visible(game)


def test_body_snapshot_restores_selection_without_lending_to_host():
    from cultivation_life.system.possession_system import enter_host_body, leave_host_body
    p = player()
    p.spirit_state['mode'] = 'wandering'
    b = books()[0]
    assign_technique(p, b, 'combat'); select(p, b.id)
    enter_host_body(p, dict(id='host', name='宿主', race='human', path='dao', spirit_root='supreme_metal',
                           realm_index=1, layer=1, age=20, lifespan=100))
    assert not p.duel_technique_ids and not p.combat_techniques
    restored = Player.from_dict(json.loads(json.dumps(p.to_dict())))
    leave_host_body(restored)
    assert restored.duel_technique_ids == [b.id]
    assert restored.combat_techniques[0].id == b.id


def test_cached_original_dictionary_keeps_same_loadout_after_promotion():
    raw = npc('cached-person').to_dict()
    ensure_npc(raw)
    promoted = SectNpc.from_dict(raw)
    assert promoted.duel_technique_ids == raw['duel_technique_ids']
    assert not ensure_npc(promoted)


def test_hidden_rank_does_not_use_disguise_or_leak_new_books():
    from cultivation_life.system.cultivation_ranks import mask_unrevealed
    person = npc(rank=6); person.concealed_realm_index = 1; person.concealed_layer = 1
    ensure_npc(person)
    assert len(person.duel_technique_ids) == 7
    raw = person.to_dict()
    mask_unrevealed(raw, {'revealed':False, 'realm_name':'练气'})
    assert 'duel_technique_ids' not in raw and 'technique_levels' not in raw


@pytest.fixture(scope='module')
def engine(tmp_path_factory):
    from cultivation_life.engine import GameEngine
    return GameEngine(Path(__file__).resolve().parents[1], tmp_path_factory.mktemp('duel'))


def test_real_command_round_trip_and_first_sight_freezes_before_growth(engine):
    made = engine.create_game('斗法验收', 'supreme_metal', 'dao', seed=712, preset_id='core')
    game = engine.store.load(made['id'])
    original = books()[0]
    learn_technique(game.player, original)
    person = npc('seen-person', 4); game.notable_npcs[person.id] = person
    engine.store.save(game)
    with pytest.raises(ValueError, match='先成功装备'):
        engine.equip_known_technique(game.id, original.id, 'duel')
    engine.equip_known_technique(game.id, original.id, 'combat')
    shown = engine.equip_known_technique(game.id, original.id, 'duel')
    assert shown['player']['duel_techniques']['selected'] == [original.id]
    loaded = engine.store.load(game.id)
    frozen = list(loaded.notable_npcs[person.id].duel_technique_ids)
    assert 3 <= len(frozen) <= 7
    loaded.notable_npcs[person.id].realm_index = 12
    engine.store.save(loaded)
    engine.get_game(game.id)
    assert engine.store.load(game.id).notable_npcs[person.id].duel_technique_ids == frozen
    engine.equip_known_technique(game.id, original.id, 'duel_remove')
    assert not engine.store.load(game.id).player.duel_technique_ids


def test_shared_battle_preparation_commits_original_person_once(engine):
    from cultivation_life.system.doctrine.provider import battle_sources
    made = engine.create_game('原身参战', 'supreme_metal', 'dao', seed=714, preset_id='core')
    game = engine.store.load(made['id'])
    person = npc('original-battle-person', 6)
    game.notable_npcs[person.id] = person
    battle_sources(game, {person.id: person})
    assert len(person.duel_technique_ids) == 7
    before = copy.deepcopy(person.duel_technique_ids)
    engine.store.save(game)
    game = engine.store.load(game.id)
    person = game.notable_npcs[person.id]
    battle_sources(game, {person.id: person})
    assert person.duel_technique_ids == before


def test_relationship_selection_is_an_original_person_reference(engine):
    made = engine.create_game('关系原身', 'supreme_metal', 'dao', seed=715, preset_id='core')
    game = engine.store.load(made['id'])
    person = npc('related-person', 6)
    game.relationship_npcs[person.id] = person
    game.player.dao_friends.append(game.link_relationship({'id':person.id}))
    friend = game.player.dao_friends[-1]
    ensure_npc(friend, game=game)
    assert friend['duel_technique_ids'] == person.duel_technique_ids
    assert len(person.duel_technique_ids) == 7
    raw = game.to_dict()
    assert 'duel_technique_ids' not in raw['player']['dao_friends'][-1]
    engine.store.save(game)
    loaded = engine.store.load(game.id)
    assert loaded.player.dao_friends[-1]['duel_technique_ids'] == person.duel_technique_ids

"""Fatal entry gates and audited soul regressions, using isolated real saves."""
import copy
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc, Item, Player
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.rules import can_player_practice_technique
from cultivation_life.soul_rules import wandering, body_cap, soul_cap
from cultivation_life.system import soul_lifecycle as life
from cultivation_life.system.second_nascent import power, unit
from cultivation_life.system.possession_system import current_body_age

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def base(tmp_path_factory):
    e = GameEngine(ROOT, tmp_path_factory.mktemp('survival') / 'saves')
    g = e._load(e.create_game('存活结算', 'supreme_metal', 'dao', 320, preset_id='core')['id'])
    g.pending_event = None
    p = g.player
    p.realm_index, p.layer, p.lifespan = 4, 2, 10000
    p.body_training, p.divine_sense_rank = 12, 80
    p.body_energy, p.soul_energy = body_cap(p), soul_cap(p)
    return e, g


@pytest.fixture
def ready(base):
    e, original = base
    g = copy.deepcopy(original)
    e.store.save(g)
    return e, g


def attach_second(g, control=100, *, remaining=1000, rank=4):
    n = SectNpc('survival-second', '副魂', '散修', rank, 2, 50, 50+remaining,
                spirit_root='supreme_metal')
    g.world_npcs[n.id] = n
    g.detain_person(n.to_dict(), kind='second_nascent')
    g.player.nascent_state['second'] = dict(id=n.id, due=g.player.age+5, interval=5,
        integrity=100., control=control, age_year=g.player.age, auto=True, equipment=[])
    return n


@pytest.mark.parametrize('rank', [3, 4])
@pytest.mark.parametrize('stage', ['body', 'spirit_failed', 'special'])
@pytest.mark.parametrize('control', [None, 49, 50])
@pytest.mark.parametrize('expired', [False, True])
def test_survival_gate_matrix(ready, rank, stage, control, expired):
    e, g = ready
    p = g.player
    p.realm_index = rank
    if expired:
        p.lifespan = p.age
    if control is not None:
        attach_second(g, control)
    e._die(g, '致命结果', 'SYS_TEST_FATAL', survival_stage=stage, offer_captive_possession=True)
    eligible = rank >= 4 and not expired and stage != 'special'
    survives_body = eligible and stage == 'body'
    survives_second = eligible and stage == 'spirit_failed' and control == 50
    assert p.alive == (survives_body or survives_second)
    assert ('second' in p.nascent_state) == (control is not None and not survives_second)
    assert g.pending_event is None
    if p.alive:
        assert wandering(p) and p.body_training == 0 and p.body_energy == 0
    else:
        assert p.hp == 0 and sum(r.result == 'dead' for r in g.history) == 1
        before = g.to_dict()
        e._die(g, '重复提交', 'SYS_TEST_FATAL')
        assert g.to_dict() == before


@pytest.mark.parametrize('event', ['SYS_LIFESPAN', 'SYS_PRISON_LIFESPAN',
    'EVT_STORY_FATAL', 'SYS_TRIAL_FAILED', 'SYS_HEAVENLY_DEMON_TRIBULATION_FAILED'])
def test_special_death_never_consumes_second_or_grants_life(ready, event):
    e, g = ready
    attach_second(g)
    span = g.player.lifespan
    e._die(g, '特殊死亡', event)
    assert not g.player.alive and 'second' in g.player.nascent_state
    assert g.player.lifespan == span


@pytest.mark.parametrize('remaining,control,alive', [(0,100,False),(1,49,False),(1,50,True)])
def test_wandering_failure_requires_live_controlled_second(ready, remaining, control, alive):
    e, g = ready
    n = attach_second(g, control, remaining=remaining)
    life.leave_body(g, destroyed=True)
    g.player.nascent_state['second']['equipment'] = [Item('escrow','托管剑',combat_bonus=10).to_dict()]
    e._die(g, '神游中陨落', 'SYS_COMBAT')
    assert g.player.alive == alive
    if alive or remaining == 0:
        assert not n.alive and 'second' not in g.player.nascent_state
        assert sum(i.quantity for i in g.player.inventory if i.id == 'escrow') == 1
    if alive:
        assert g.player.lifespan-g.player.age == remaining
        g.player.age += remaining
        life.tick(g, random.Random(3), e._die)
        assert not g.player.alive


def test_second_aging_control_and_reload_are_idempotent(ready):
    e, g = ready
    n = attach_second(g)
    row = g.player.nascent_state['second']
    row.update(control=30., integrity=50.)
    g.player.age += 5
    before = g.player.soul_energy
    life.tick(g, random.Random(3), e._die)
    assert n.age == 55 and row['control'] == 50 and row['integrity'] == 70
    assert g.player.soul_energy == before-15
    e.store.save(g)
    loaded = e.store.load(g.id)
    life.tick(loaded, random.Random(3), e._die)
    assert loaded.to_dict() == g.to_dict()
    loaded.player.nascent_state['second']['auto'] = False
    loaded.player.age += 5
    with patch.object(random.Random, 'random', return_value=.99):
        life.tick(loaded, random.Random(3), e._die)
    assert loaded.player.nascent_state['second']['control'] == 48
    e.store.save(loaded)
    e.soul_action(g.id, 'assimilate', {'revision':0})
    loaded = e.store.load(g.id)
    assert loaded.player.nascent_state['second']['control'] == 68
    assert life.second_person(loaded).age == 60


@pytest.mark.parametrize('rank,remaining', [(4,1),(5,1),(6,0)])
def test_second_finite_life_and_void_exemption(ready, rank, remaining):
    e, g = ready
    n = attach_second(g, remaining=remaining, rank=rank)
    g.player.age += 1
    life.tick(g, random.Random(3), e._die)
    assert n.age == 51
    assert (life.second_person(g) is not None) == (rank >= 6)
    assert g.player.alive


def test_integrity_is_applied_once_in_combat(ready):
    _, g = ready
    attach_second(g)
    full = power(g)
    g.player.nascent_state['second']['integrity'] = 50.
    battle = unit(g)
    assert power(g) == pytest.approx(full*.5, abs=.1)
    assert battle.power*battle.integrity == pytest.approx(power(g), abs=.1)


@pytest.mark.parametrize('entry', ['ordinary','space','guixu','breakthrough'])
def test_bodyless_training_rejects_before_cost_rng_or_time(ready, entry):
    e, g = ready
    p = g.player
    p.path = 'ghost'
    life.leave_body(g, destroyed=True)
    p.body_technique = copy.deepcopy(next(t for t in TECHNIQUE_CATALOG.values()
        if t.category == 'body' and can_player_practice_technique(p,t)))
    e.store.save(g)
    g = e._load(g.id)
    before = g.to_dict()
    with pytest.raises(ValueError, match='肉身'):
        if entry == 'ordinary': e.advance(g.id, 'body_train', 1)
        elif entry == 'space': e._spatial_training(g, 'body_train', 1)
        elif entry == 'guixu': e._guixu_trapped_training(g.id, 'body_train', 1)
        else: e.body_breakthrough(g.id)
    assert e.store.load(g.id).to_dict() == before


@pytest.mark.parametrize('path', ['buddhist', 'confucian'])
def test_stagnant_alternative_advancement_is_atomic(ready, path):
    e, g = ready
    p = g.player
    p.path, p.realm_index, p.layer = path, 2, 1
    p.nascent_state['stagnant'] = True
    p.haoran_exp = 100000
    g.buddhist_state.setdefault('wish', {})['value'] = 100
    e.store.save(g)
    e._load(g.id)
    before = e.store.load(g.id).to_dict()
    with pytest.raises(ValueError, match='停滞'):
        if path == 'buddhist': e.buddhist_action(g.id, 'nirvana')
        else: e.sage_outer_king(g.id, 'advance')
    assert e.store.load(g.id).to_dict() == before


def test_actual_possession_inherits_host_coordinates_life_and_book_level(ready):
    e, g = ready
    p = g.player
    life.leave_body(g)
    book = next(t for t in TECHNIQUE_CATALOG.values() if t.category=='spiritual' and t.grade==1 and t.path=='dao')
    n = SectNpc('host-check','宿主','散修',3,2,196,812,spirit_root='supreme_metal',
        body_training=8,divine_sense_rank=60,main_technique_id=book.id,main_technique_level=7,
        technique_levels={book.id:7})
    g.world_npcs[n.id] = n
    p.prisoners.append(g.detain_person(n.to_dict()))
    world_age = p.age
    e.store.save(g)
    with patch.object(random.Random, 'random', return_value=0.):
        e.captive_action(g.id,n.id,'possess')
    after = e.store.load(g.id)
    p = after.player
    assert (p.realm_index,p.layer,p.body_training,p.divine_sense_rank) == (3,2,8,60)
    assert (p.age,current_body_age(p),p.lifespan) == (world_age,196,812)
    assert p.technique.level == 7 and p.known_techniques[0].level == 7
    assert not after.inactive_npcs[n.id].alive and not p.prisoners


def test_failed_possession_reports_survival_and_preserves_target(ready):
    e, g = ready
    attach_second(g,50)
    n = SectNpc('failure-target','宿主','散修',4,1,80,900,spirit_root='supreme_metal')
    g.world_npcs[n.id] = n
    g.player.prisoners.append(g.detain_person(n.to_dict()))
    life.leave_body(g)
    e.store.save(g)
    with patch.object(random.Random,'random',return_value=.999):
        result = e.captive_action(g.id,n.id,'possess')
    after = e.store.load(g.id)
    assert result['player']['alive'] and wandering(after.player)
    assert after.history[-1].result == 'survived'
    assert '魂飞魄散' not in after.history[-1].summary
    assert after.inactive_npcs[n.id].alive and len(after.player.prisoners)==1
    assert 'second' not in after.player.nascent_state


def test_schema_rejects_control_and_clock_tampering(ready):
    _, g = ready
    attach_second(g)
    for key,value in [('control',101),('control',-1),('control',float('nan')),('age_year',g.player.age+1)]:
        raw = g.player.to_dict()
        raw['nascent_state']['second'][key] = value
        with pytest.raises(ValueError): Player.from_dict(raw)


def test_second_clock_survives_real_world_transition_and_space_tick(ready):
    e, g = ready
    n = attach_second(g, 50)
    g.player.realm_index, g.player.layer = 5, 3
    before = copy.deepcopy(g.player.nascent_state['second'])
    plan = e._plan_world_transition(g, 'spirit', 'progression')
    e._apply_world_transition(g, plan)
    assert life.second_person(g) is n and n.world == 'spirit'
    assert g.player.nascent_state['second'] == before
    g.player.age += 2
    life.tick(g, random.Random(3), e._die)
    assert n.age == 52
    life.tick(g, random.Random(3), e._die)
    assert n.age == 52 and g.player.nascent_state['second']['control'] == 50


def test_second_is_not_aged_again_through_old_relationship_reference(ready):
    e, g = ready
    n = attach_second(g)
    from cultivation_life.relationship_records import bind_relationship
    g.player.concubines.append(bind_relationship(g, dict(n.to_dict(), source='captive'), SectNpc))
    g.player.age += 1
    life.tick(g, random.Random(3), e._die)
    e._annual_relationship_update(g, random.Random(3))
    assert n.age == 51


def test_combat_energy_collapse_settles_once(ready):
    e, g = ready
    g.player.body_energy = .01
    with patch.object(e, '_die', wraps=e._die) as die:
        result, _ = e._combat(g, dict(target_name='致命强敌',
            target_power=e._player_battle_power(g)*100, target_realm_index=4, target_layer=9,
            combat_type='cultivator', path='dao', enemy_objective='kill', non_story_combat=True),
            True, random.Random(17))
    assert result == 'defeat_survived' and g.player.alive and wandering(g.player)
    assert die.call_count == 1


def test_body_training_collapse_stops_paid_action(ready):
    e, g = ready
    p = g.player
    p.body_technique = copy.deepcopy(next(t for t in TECHNIQUE_CATALOG.values()
        if t.category=='body' and t.grade==1 and can_player_practice_technique(p,t)))
    p.body_energy = 1.
    before = p.age
    e.store.save(g)
    result = e.advance(g.id, 'body_train', 3)
    after = e.store.load(g.id).player
    assert result['player']['alive'] and wandering(after)
    assert after.age == before+1 and after.body_training == 0 and after.body_progress == 0


def test_story_failure_real_submission_cannot_use_phoenix_or_second(ready):
    e, g = ready
    attach_second(g)
    p = g.player
    book = copy.deepcopy(TECHNIQUE_CATALOG['TECH_BEAST_TRANSFORMATION'])
    p.transformation_technique = book
    p.known_techniques.append(copy.deepcopy(book))
    p.known_transformations = ['FORM_PHOENIX']
    p.transformation_mastery = {'FORM_PHOENIX':dict(purity=1.,stats={})}
    p.transformation_loadouts = {book.id:dict(stored=['FORM_PHOENIX'],active=['FORM_PHOENIX'])}
    from cultivation_life.system.transformation_system import active_transformation_profile
    assert 'prevent_defeat_once' in active_transformation_profile(p)['traits']
    event = e.events_by_id['EVT_MA_LIANG_005']
    g.pending_event = e._instantiate_event(event,g,random.Random(3))
    e.store.save(g)
    assert e.get_game(g.id)['pending_event']['id'] == event['id']
    # Force only the battle outcome; use real event loading, submitting and settlement.
    with patch.object(e, '_combat', return_value=('defeat','剧情战败。')):
        view = e.choose(g.id,'attack_bottle',event_id=event['id'])
    after = e.store.load(g.id)
    assert not view['player']['alive'] and not after.player.alive
    assert 'second' in after.player.nascent_state


def test_second_remaining_life_updates_sealed_return_snapshot(ready):
    e, g = ready
    attach_second(g,remaining=3)
    g.player.sealed_cultivation=dict(realm_index=8,layer=9,lifespan=10000)
    e._die(g,'神游失败','SYS_TEST',survival_stage='spirit_failed')
    assert g.player.alive
    assert g.player.sealed_cultivation['lifespan'] == g.player.lifespan == g.player.age+3


def test_missing_host_coordinate_does_not_overwrite_explicit_other_coordinate(ready):
    _, g = ready
    life.leave_body(g)
    from cultivation_life.system.possession_system import enter_host_body
    enter_host_body(g.player, dict(id='partial-host',name='宿主',realm_index=3,layer=1,
        age=30,lifespan=900,body_training=None,divine_sense_rank=1,spirit_root='supreme_metal'))
    assert g.player.divine_sense_rank == 1 and g.player.body_training >= 0


def test_treasure_fatal_summary_matches_survival(ready):
    e, g = ready
    g.player.hp, g.player.mp = 1., 0.
    summary = e._treasure_step(g, random.Random(3))
    assert g.player.alive and wandering(g.player)
    assert '未能生还' not in summary and '神游' in summary


def test_failed_prison_escape_real_command_records_survival(ready):
    e, g = ready
    g.player.hp = 1.
    g.player.imprisonment = dict(key='world:human',name='大牢',remaining_years=5,
        captured_age=g.player.age,hostility=100.,sentence_years=5,hostility_reduction_per_year=4.)
    e.store.save(g)
    with patch.object(random.Random, 'random', return_value=.999):
        view = e.prison_action(g.id,'escape')
    after = e.store.load(g.id)
    assert view['player']['alive'] and wandering(after.player)
    assert after.history[-1].result == 'survived'


def test_destroyed_ghost_core_cannot_pass_wandering_gate(ready):
    e, g = ready
    g.player.path = 'ghost'
    g.player.ghost_intrinsic_hp_current = 0.
    e._die(g,'本魂已无法承载致命损伤','SYS_COMBAT')
    assert not g.player.alive and not wandering(g.player)

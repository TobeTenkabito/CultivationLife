import copy
from dataclasses import replace
import random

import pytest

from scripts.calibrate_immortal_trials import fixture, ADAPTER
from cultivation_life.engine.progression.immortal_trials import initialize, target_for, chosen_field, start
from cultivation_life.system.combat.trials import run_batch, dump_battle, load_battle
from cultivation_life.system.doctrine.voisinage_training import label, rank, dao_ancestor
from cultivation_life.system.doctrine.progression import source
from cultivation_life.system.combat.contracts import Combatant, CombatCapabilities
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.rules import max_hp, max_mp, opportunity_required
from test_immortal_cultivation import prepared


def test_stages_have_twelve_numbered_layers_then_unlevelled_perfection():
    assert [label(n) for n in (1,4,5,8,9,12,13)] == ['初成1层','初成4层','化境1层','化境4层','大成1层','大成4层','至臻']
    assert rank({'stability':8}) == 1


def test_perfection_reward_does_not_inflate_backlash_or_superego():
    from cultivation_life.system.doctrine.voisinage_training import project
    game = fixture('voisinage_backlash', field_rank=12, doctrine_level=8)
    trial = game.active_trial
    key = trial['doctrine_id']
    original = game.doctrine_state['definitions'][key]['stages'][7]['voisinage']
    target = target_for(game, trial)
    assert target['voisinages'][0]['stability'] == pytest.approx(original['stability'] * 3.64 * 1.42)
    definition = chosen_field(game, cap=1)
    factors = (1, 1.22, 1.44, 1.66, 1.88, 2.10, 2.32, 2.54,
               2.76, 3.06, 3.36, 3.66, 4.55)
    for value, factor in enumerate(factors, 1):
        projected = project(definition, {'rank': value})
        for axis in ('stability', 'incursion', 'authority'):
            assert getattr(projected, axis) == pytest.approx(getattr(definition, axis) * factor)
        assert projected.actions() == definition.actions()
        assert projected.upkeep_cost == definition.upkeep_cost
    record = game.doctrine_state['player']
    record['voisinage_training'][key]['rank'] = 13
    start(ADAPTER, game, 'three_corpses')
    copied = game.active_trial['corpse_field']
    own = chosen_field(game)
    for axis in ('stability', 'incursion', 'authority'):
        assert getattr(own, axis) / copied[axis] == pytest.approx(4.55 / 2.54)


def test_legacy_tempering_is_preserved_and_projection_matches_ui(prepared):
    engine, game, definition = prepared
    key = definition['id']
    record = game.doctrine_state['player']
    record['progress'][key] = {'level':4,'experience':0}
    record['active'] = key
    record['voisinage_training'][key] = {'stability':3}
    before = chosen_field(game).stability
    game.player.immortal_traces = 10000
    engine.store.save(game)
    shown = engine.immortal_action(game.id, 'advance_voisinage', doctrine_id=key)
    saved = engine.store.load(game.id)
    assert saved.doctrine_state['player']['voisinage_training'][key] == {'stability':3,'rank':2}
    row = next(f for f in shown['doctrines']['voisinages'] if f['id']==key)
    assert row['cultivation']['label'] == '初成2层'
    assert row['axes'][0]['value'] == pytest.approx(before * 1.22)


def test_crossing_stage_starts_trial_and_does_not_grant_rank_before_victory(prepared):
    engine, game, definition = prepared
    key = definition['id']
    record = game.doctrine_state['player']
    record['progress'][key] = {'level':4,'experience':0}
    record['active'] = key
    record['voisinage_training'][key] = {'rank':4,'stability':10}
    game.player.immortal_traces = 10000
    game.player.combat_plan = {'manual':True,'stance':'guard','investment':40}
    game.player.immortal_aperture['current'] = 1000
    engine.store.save(game)
    shown = engine.immortal_action(game.id,'advance_voisinage',doctrine_id=key)
    assert shown['pending_event']['id'] == 'EVT_IMMORTAL_TRIAL_VOISINAGE_BACKLASH'
    assert engine.store.load(game.id).doctrine_state['player']['voisinage_training'][key]['rank']==4
    with pytest.raises(ValueError):
        engine.immortal_action(game.id,'advance_voisinage',doctrine_id=key)
    shown = engine.choose(game.id,'fight')
    assert shown['player']['alive']
    assert engine.store.load(game.id).doctrine_state['player']['voisinage_training'][key]['rank']==5
    assert len(shown['last_combat_report']['rounds'])==5


def test_backlash_never_calls_ordinary_damage(monkeypatch):
    game = fixture('voisinage_backlash',field_rank=4,temper=10,stance='guard',investment=40)
    battle = initialize(game,game.active_trial)
    monkeypatch.setattr(battle,'ordinary_damage',lambda *a: pytest.fail('ordinary combat in backlash'))
    result, rows = run_batch(battle,game.active_trial['battle_state'],random.Random(1))
    assert result=='victory' and len(rows)==5
    assert all(r['initiative']=='voisinage' for r in rows)


def test_empty_energy_and_high_combat_power_cannot_bypass_heaven_field():
    game = fixture('heaven_decline',field_rank=4,energy=0,power_ratio=1000)
    battle = initialize(game,game.active_trial)
    result, rows = run_batch(battle,game.active_trial['battle_state'],random.Random(1))
    assert result=='defeat' and len(rows)<5


def test_five_rounds_required_even_if_manifestation_is_destroyed_early():
    game = fixture('human_decline',field_rank=0,power_ratio=1000)
    battle = initialize(game,game.active_trial)
    result, rows = run_batch(battle,game.active_trial['battle_state'],random.Random(1))
    assert result=='victory' and [r['round'] for r in rows]==list(range(1,6))


@pytest.mark.parametrize('field_index', [0, 1, 2, 13, 24])
def test_corpse_roster_and_capped_copy_are_fixed_at_start(field_index):
    game = fixture('three_corpses',field_rank=13,doctrine_level=8,field_index=field_index)
    expected = chosen_field(game,cap=8)
    # The equipment selection at trial entry is locked for both sides, even
    # if the saved active selection later changes before the first round.
    record = game.doctrine_state['player']
    other = next(key for key in game.doctrine_state['definitions'] if key != record['active'])
    record['progress'][other] = {'level': 4, 'experience': 0}
    record['active'] = other
    game.player.dao_friends = [{'id':'cheat','name':'援军','combat_power':1e99,'realm_index':12}]
    game.player.puppets = [{'id':'puppet','alive':True,'combat_power':1e99}]
    battle = initialize(game,game.active_trial)
    assert len(battle.units)==4
    assert [s.unit.name for k,s in battle.units.items() if k!='player']==[f'{game.player.name}·{name}' for name in ('自我尸','本我尸','超我尸')]
    assert target_for(game, game.active_trial)['target_name'] == f'{game.player.name}的三尸'
    assert not battle.units['enemy-0'].unit.capabilities.voisinages
    assert not battle.units['enemy-1'].unit.capabilities.voisinages
    copied = battle.units['enemy-2'].unit.capabilities.voisinages[0]
    assert battle.units['player'].unit.capabilities.voisinages[0].id == expected.id
    assert copied.stability == pytest.approx(expected.stability)
    assert copied.stability < battle.units['player'].unit.capabilities.voisinages[0].stability
    old_power = game.active_trial['power']
    game.player.outer_king_fixed_combat_power += 1e12
    assert sum(m['power'] for m in target_for(game,game.active_trial)['members']) == pytest.approx(old_power*1.4)


def test_resuming_a_snapshot_matches_uninterrupted_rounds():
    game = fixture('heaven_decline',field_rank=8,temper=5,stance='guard',investment=40)
    whole = initialize(game,game.active_trial)
    split = load_battle(dump_battle(whole))
    a = copy.deepcopy(game.active_trial['battle_state']); b = copy.deepcopy(a)
    rng_a=random.Random(7); rng_b=random.Random(7)
    expected, rows = run_batch(whole,a,rng_a)
    ongoing, first = run_batch(split,b,rng_b,batch_size=2)
    assert ongoing=='ongoing'
    split = load_battle(dump_battle(split))
    actual, last = run_batch(split,b,rng_b)
    assert actual==expected
    assert first+last==rows
    assert dump_battle(whole)==dump_battle(split)


def test_three_corpses_has_no_round_limit_and_suppression_is_not_victory():
    caps = CombatCapabilities(ward_tier=2)
    units = [Combatant('player','你','player',100,caps)] + [Combatant(str(i),'尸','enemy',40,caps) for i in range(3)]
    battle = VoisinageBattle(units)
    state={'mode':'three_corpses','round':0,'mp_ratio':1,
           'stats':{side:{k:100 for k in ('might','guard','mobility','sense','sustain','breach')} for side in ('player','enemy')}}
    for enemy in list(battle.units.values())[1:]:
        enemy.suppressed=True
    for _ in range(5):
        result, rows=run_batch(battle,state,random.Random(1))
        assert result=='ongoing'
        battle=load_battle(dump_battle(battle))
    assert state['round']==120 and not battle.enemy_killed()


@pytest.mark.parametrize('mode', ['three_corpses', 'human_decline', 'heaven_decline', 'voisinage_backlash'])
def test_trial_enemies_cannot_escape_even_with_a_special_intervention(mode):
    from cultivation_life.system.combat.contracts import Intervention, VoisinageEffect
    from test_voisinage_effects import actor, caster, domain, begin
    battle = VoisinageBattle([
        actor('player', 'player', caster(domain(VoisinageEffect('strike', 1, .1)))),
        actor('enemy', 'enemy', CombatCapabilities(capacity=10, current=10,
            interventions=(Intervention('escape', ('strike',), cost=5, strength=1000),))),
    ])
    ordinary = load_battle(dump_battle(battle))
    begin(ordinary)
    assert ordinary.units['enemy'].escaped  # Ordinary encounters keep this ability.
    assert ordinary.units['enemy'].current == 5
    state = {'mode':mode, 'round':0, 'mp_ratio':1,
             'stats':{side:{k:100 for k in ('might','guard','mobility','sense','sustain','breach')}
                      for side in ('player','enemy')}}
    result, _ = run_batch(battle, state, random.Random(1), batch_size=1)
    assert result == 'ongoing'
    assert not battle.units['enemy'].escaped
    assert battle.units['enemy'].body < 1
    assert battle.units['enemy'].current == 10  # No fee for the prohibited response.
    snapshot = dump_battle(battle)
    snapshot.pop('escape_forbidden_sides')  # An older unfinished save.
    snapshot['states']['enemy']['escaped'] = True
    resumed = load_battle(snapshot)
    prior_body = resumed.units['enemy'].body
    result, _ = run_batch(resumed, state, random.Random(1), batch_size=1)
    assert result == 'ongoing' and not resumed.units['enemy'].escaped
    if mode == 'three_corpses':
        assert resumed.units['enemy'].body < prior_body
    assert load_battle(dump_battle(resumed)).escape_forbidden_sides == {'enemy'}


def test_suppressed_zero_vitality_corpse_requires_an_actual_finishing_attack():
    game=fixture('three_corpses',field_rank=8,doctrine_level=8)
    battle=initialize(game,game.active_trial)
    for key,s in battle.units.items():
        if key!='player': s.vitality=0; s.suppressed=True
    result,_=run_batch(battle,game.active_trial['battle_state'],random.Random(1))
    assert result=='victory' and battle.enemy_killed()


def test_dao_ancestor_requires_all_three_facts():
    game=fixture('three_corpses',field_rank=13,doctrine_level=8)
    record=game.doctrine_state['player']; key=record['active']
    assert not dao_ancestor(game)
    game.player.realm_index=12
    assert not dao_ancestor(game)
    record['progress'][key]['level']=9
    assert dao_ancestor(game)
    record['voisinage_training'][key]['rank']=12
    assert not dao_ancestor(game)


def test_dao_ancestor_is_a_persisted_base_achievement(prepared):
    engine, game, _ = prepared
    profile = fixture('three_corpses', field_rank=13, doctrine_level=8)
    game.player, game.doctrine_state = profile.player, profile.doctrine_state
    game.player.realm_index = 12
    game.player.location_id = engine.maps.default_location('celestial')
    record = game.doctrine_state['player']
    record['progress'][record['active']]['level'] = 9
    shown = engine.present(game)
    assert shown['player']['dao_ancestor']
    assert '道祖' in {a['name'] for a in shown['new_achievements']}
    achievement = next(a for a in engine.list_achievements()['achievements'] if a['id']=='cultivation_dao_ancestor')
    assert achievement['unlocked'] and achievement['source']['kind']=='base'


def test_three_corpses_real_choice_finishes_only_after_all_three_die(prepared):
    engine, game, _ = prepared
    profile = fixture('three_corpses', field_rank=12, doctrine_level=8, temper=10, field_index=1)
    game.player, game.doctrine_state = profile.player, profile.doctrine_state
    game.active_trial, game.pending_event = profile.active_trial, profile.pending_event
    engine.store.save(game)
    shown = engine.choose(game.id, 'fight')
    assert shown['player']['realm_index']==12 and shown['player']['alive']
    assert shown['last_combat_report']['result']=='victory'
    assert len(shown['last_combat_report']['enemy_roster'])==3
    assert not engine.store.load(game.id).active_trial


def test_unlimited_battle_survives_real_save_reload_without_resource_reset(prepared):
    engine, game, _ = prepared
    profile = fixture('three_corpses', field_rank=0)
    game.player, game.doctrine_state = profile.player, profile.doctrine_state
    game.player.location_id = engine.maps.default_location('celestial')
    game.active_trial, game.pending_event = profile.active_trial, profile.pending_event
    battle = initialize(game, game.active_trial)
    for actor in battle.units.values():
        actor.unit = replace(actor.unit, capabilities=CombatCapabilities(ward_tier=99))
        actor.current = 0
    game.active_trial['snapshot'] = dump_battle(battle)
    engine.store.save(game)
    for expected in (24, 48, 72, 96):
        shown = engine.choose(game.id, 'fight')
        assert shown['last_combat_report']['result']=='ongoing'
        assert shown['last_combat_report']['total_rounds']==expected
        assert len(shown['last_combat_report']['rounds'])==min(72, expected)
        saved = engine.store.load(game.id)
        assert saved.player.realm_index==11
        assert saved.active_trial['battle_state']['round']==expected
        assert saved.active_trial['snapshot']['states']['player']['current']==0
    with pytest.raises(ValueError):
        engine.use_item(game.id, 'small_recovery_pill')


def test_final_backlash_death_does_not_grant_perfection(prepared):
    engine, game, _=prepared
    profile=fixture('voisinage_backlash',field_rank=12,energy=0)
    game.player=profile.player; game.doctrine_state=profile.doctrine_state
    game.active_trial=profile.active_trial; game.pending_event=profile.pending_event
    engine.store.save(game)
    shown=engine.choose(game.id,'fight')
    assert not shown['player']['alive']
    assert '同化' in shown['player']['death_reason']
    saved=engine.store.load(game.id)
    assert saved.doctrine_state['player']['voisinage_training'][profile.active_trial['doctrine_id']]['rank']==12

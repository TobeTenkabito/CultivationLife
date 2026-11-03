"""Balance projections and the numeric gates used by the real settlement engine."""
from dataclasses import replace
import pytest

from scripts.calibrate_high_body_balance import configuration,profile,evaluate,FAMILIES
from scripts.simulate_high_body_combat import profile as live_profile
from cultivation_life.system.combat.body_mechanisms import mechanisms
from cultivation_life.system.combat.contracts import CombatCapabilities,VoisinageEffect
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.trials import dump_battle,load_battle
from test_voisinage_effects import actor,caster,domain
from test_body_round_wuyun import start,m
from test_monster_body import encounter


@pytest.mark.parametrize('family',FAMILIES)
@pytest.mark.parametrize('rank',[0,5,10])
def test_calibration_profiles_match_real_player_projections(family,rank):
    actual=mechanisms(CombatCapabilities(**live_profile(family,rank)))
    simulated=profile(family,rank,50,configuration())
    assert [r.id for r in simulated]==[r.id for r in actual]
    for a,b in zip(actual,simulated):
        assert (a.level,a.requires,a.priority)==(b.level,b.requires,b.priority)
        assert a.chance==pytest.approx(b.chance)
        assert a.effects==pytest.approx(b.effects)


def test_all_training_steps_are_bounded_and_preserve_original_unlocks():
    cfg=configuration()
    for family in FAMILIES:
        for rank in range(11):
            for level in (9,10,19,20,29,30,39,40,49,50):
                assert len(profile(family,rank,level,cfg))==level//10
    assert profile('demonic',10,50,cfg)[1].effects['critical']==2
    assert profile('ghost',0,50,cfg)[1].effects['split']==.4
    assert profile('ghost',10,50,cfg)[1].effects['split']==.65


@pytest.mark.parametrize('scale',[1,10,100])
def test_default_authority_reference_preserves_equal_grade_damage(scale):
    d=domain(VoisinageEffect('strike',3,.1),strength=100*scale,
             authority=110*scale,authority_reference=None)
    assert d.authority_reference==100*scale
    b=VoisinageBattle([actor('player','player',caster(d)),actor('enemy','enemy')])
    start(b)
    assert b.units['enemy'].vitality==pytest.approx(.89)
    frozen=load_battle(dump_battle(b))
    assert frozen.units['player'].unit.capabilities.voisinages[0].authority_reference==100*scale


def test_explicit_authority_reference_is_never_rewritten():
    d=domain(VoisinageEffect('strike',3,.1),strength=1000,authority=1100,authority_reference=100)
    assert d.authority_reference==100
    b=VoisinageBattle([actor('player','player',caster(d)),actor('enemy','enemy')]);start(b)
    assert b.units['enemy'].vitality==0
    assert load_battle(dump_battle(b)).units['player'].unit.capabilities.voisinages[0].authority_reference==100


@pytest.mark.parametrize('silenced',[False,True])
def test_colour_incursion_uses_original_contest_and_obeys_silence(silenced):
    d=domain(VoisinageEffect('strike',999,.1),strength=100,incursion=120,stability=120)
    c=caster(d,body_mechanisms=(m('se',ward=2,incursion=.35),))
    e=caster(d,body_mechanisms=(m('qian',silence=1),) if silenced else ())
    b=VoisinageBattle([actor('player','player',c),actor('enemy','enemy',e)])
    start(b,first='enemy')
    fields={r.owner:r for r in b.fields}
    assert fields['player'].strength/fields['enemy'].strength==pytest.approx(1 if silenced else 1.35)
    assert b.frame.relations['enemy']['relation']==('contested' if silenced else 'dominated')
    assert b.units['player'].current==98  # Incursion does not waive opening/upkeep.


def test_overlapping_erosion_uses_only_the_selected_attacking_field():
    d=domain(VoisinageEffect('strike',999,.1))
    caps=caster(d,body_mechanisms=(m('li',erosion=.02),))
    b=VoisinageBattle([actor('a','player',caps),actor('b','player',caps),actor('enemy','enemy')]);start(b)
    notes=[e for e in b._light_trace if e['kind']=='li']
    assert len(notes)==1
    assert notes[0]['owner']==b.frame.relations['enemy']['attacker']
    assert b.units['enemy'].vitality==pytest.approx(.98)


class FixedDice:
    def __init__(self,value):self.value=value;self.calls=0
    def random(self):self.calls+=1;return self.value


def control_probability(b,chance):
    unit=b.units['player'].unit
    rows=tuple(replace(r,effects={**r.effects,'retaliate_control':chance,'retaliate_voisinage':1})
               if r.id=='liezang' else r for r in unit.capabilities.body_mechanisms)
    b.units['player'].unit=replace(unit,capabilities=replace(unit.capabilities,body_mechanisms=rows))


@pytest.mark.parametrize('choice',[5,10])
@pytest.mark.parametrize('roll,success',[(.05,True),(.95,False)])
def test_free_control_has_a_visible_success_gate_and_keeps_one_free_action(choice,roll,success):
    b=encounter(choice=choice);control_probability(b,.2);dice=FixedDice(roll)
    start(b,rng=dice)
    notes=[e for e in b._light_trace if e['kind']=='reaction_control']
    assert len(notes)==1 and notes[0]['success']==success and notes[0]['probability']==.2
    enemy=b.units['enemy']
    assert (enemy.seal_progress>0 if choice==5 else 'voisinage' in enemy.controls)==success
    assert len([e for e in b._light_trace if e['kind']=='body_action' and e['owner']=='player'])==1
    assert b.units['player'].current==98
    assert dice.calls==1
    frozen=load_battle(dump_battle(b))
    assert next(r for r in frozen.units['player'].unit.capabilities.body_mechanisms if r.id=='liezang').effects['retaliate_control']==.2


@pytest.mark.parametrize('choice',[1,4])
def test_control_gate_does_not_randomly_cancel_numeric_healing_or_suppression(choice):
    b=encounter(choice=choice);control_probability(b,0);start(b,rng=FixedDice(.95))
    assert not any(e['kind']=='reaction_control' for e in b._light_trace)
    assert (b.units['player'].vitality if choice==1 else b.units['enemy'].vitality)==pytest.approx(.8 if choice==1 else .9)


def test_frozen_legacy_reaction_without_new_channel_retains_its_explicit_behaviour():
    b=encounter(choice=5);start(b,rng=FixedDice(.95))
    assert b.units['enemy'].seal_progress==pytest.approx(.1)
    assert next(e for e in b._light_trace if e['kind']=='reaction_control')['probability']==1


def test_equal_resource_full_unlock_matrix_keeps_the_requested_overall_order():
    # Independent validation seeds, all three ranks, four field styles and 1v1/2v2/3v3.
    result=evaluate(configuration(),seeds=16,seed_offset=128,sizes=(1,2,3))
    scores=result['overall']
    assert scores['demonic']>scores['immortal']>max(scores['monster'],scores['ghost'])
    assert max(scores.values())-min(scores.values())<.12
    assert abs(scores['monster']-scores['ghost'])<.05
    assert all(.43<score<.58 for score in scores.values())
    assert .4<result['matrix']['monster/ghost']<.6
    for rank in (0,5,10):
        totals={family:[] for family in FAMILIES}
        for pair,score in result['splits'][f'rank:{rank}'].items():
            a,b=pair.split('/');totals[a].append(score);totals[b].append(1-score)
        averages=[sum(rows)/len(rows) for rows in totals.values()]
        assert max(averages)-min(averages)<.20
    assert result['round_limit_draws']==0

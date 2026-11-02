"""Cross-family regression cases found by the high-body combat audit."""
from dataclasses import replace
from types import SimpleNamespace
import pytest

from cultivation_life.ghost_body_content import build
from cultivation_life.system.combat.contracts import CombatCapabilities,VoisinageEffect,Intervention
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.divine_lights import profile as lights
from cultivation_life.system.wuyun import profile as aggregates
from cultivation_life.system.monster_body import profile as changes
from cultivation_life.system.ghost_body import profile as ghost_body
from cultivation_life.system.combat.trials import dump_battle,load_battle
from cultivation_life.system.combat.contracts import ResourceSupply,VoisinageSeal
from test_voisinage_effects import actor,caster,domain
from test_body_round_wuyun import start


def test_zhaoye_inherits_capped_original_power_instead_of_capping_each_scaled_part():
    d=domain(VoisinageEffect('strike',3,.2),authority=1000)
    b=VoisinageBattle([actor('player','player',caster(d,body_mechanisms=(build('zhaoye'),))),actor('e','enemy')])
    start(b)
    hits=[r['loss'] for r in b.animation['effects'] if r['kind']=='strike' and r['target']=='e']
    assert hits==pytest.approx([.4,.4,.2])


@pytest.mark.parametrize('path,project',[('dao',lights),('demonic',aggregates),('monster',changes),('ghost',ghost_body)])
@pytest.mark.parametrize('intact',[False,True])
def test_unpossessed_wandering_soul_does_not_borrow_original_body(path,project,intact):
    p=SimpleNamespace(path=path,immortal_body={'level':50,'monster':{'level':50}},asura_cultivation={'body_level':50},
        ghost_host_body=None,ghost_core_state=None,spirit_state={'mode':'wandering','body_intact':intact})
    result=project(p,player=True)
    assert not (result[0] if path=='dao' else result)


@pytest.mark.parametrize('path,project',[('dao',lights),('demonic',aggregates),('monster',changes),('ghost',ghost_body)])
def test_npc_wandering_soul_loses_body_mechanisms_and_legacy_ward(path,project):
    from cultivation_life.system.npc_cultivation import npc_golden_light
    npc=dict(path=path,immortal_body_level=50,spirit_state={'mode':'wandering','body_intact':True})
    result=project(npc)
    assert not (result[0] if path=='dao' else result)
    assert not npc_golden_light(npc)


def test_sheltered_target_is_not_hit_by_later_zhaoye_segments_after_coverage_is_released():
    d=domain(VoisinageEffect('strike',3,.1),max_targets=3)
    defense=CombatCapabilities(interventions=(Intervention('shelter',('strike',),strength=10000),))
    b=VoisinageBattle([actor('player','player',caster(d,body_mechanisms=(build('zhaoye'),))),
        actor('a','enemy',defense),actor('b','enemy')])
    start(b)
    assert b.units['a'].vitality==1
    assert b.units['b'].vitality==pytest.approx(.88)


def test_body_death_is_not_fabricated_by_pure_state_suppression():
    d=domain(VoisinageEffect('suppress',3,1))
    own=caster(d,body_mechanisms=(build('yuhun'),))
    b=VoisinageBattle([actor('player','player',own,integrity=.5),actor('e','enemy')])
    start(b)
    assert b.units['e'].suppressed
    assert not b.units['e'].death_observed
    assert not any(r['kind']=='death_restore' for r in b._light_trace)


def test_snapshot_preserves_capture_objective_contest_supply_and_applied_seal():
    d=domain(VoisinageEffect('strike',3,.05))
    b=VoisinageBattle([actor('player','player',caster(d)),actor('e','enemy',caster(d))],contest_ratio=1.8,
        supplies=(ResourceSupply('player',5),),seals=(VoisinageSeal('e',1,'封域验收'),))
    b.set_objectives('capture','repel');start(b)
    resumed=load_battle(dump_battle(b))
    assert resumed.objectives==b.objectives and resumed.contest_ratio==1.8
    assert resumed.supplies==b.supplies and resumed.seals==b.seals
    assert resumed._applied_seals=={0}
    start(resumed,n=2)
    assert not any('封域验收' in text for text in resumed.frame.events)


@pytest.mark.parametrize('family',["immortal","demonic","monster","ghost"])
def test_mortal_damage_is_immune_for_each_unsilenced_family(family):
    from scripts.simulate_high_body_combat import profile
    caps=CombatCapabilities(**profile(family,0))
    b=VoisinageBattle([actor('player','player',caps),actor('e','enemy')])
    start(b);b.ordinary_damage(0,.2)
    assert b.units['player'].vitality==1 and b.units['player'].body==1


@pytest.mark.parametrize('scenario',['strike','single','heal','suppress','low_energy','capture'])
def test_cross_family_production_profiles_resume_with_identical_resources_targets_and_rng(scenario):
    from scripts.simulate_high_body_combat import run_case
    for left,right in [('immortal','demonic'),('demonic','monster'),('monster','ghost'),('ghost','immortal')]:
        run_case(left,right,10,True,scenario,3,max_rounds=8)


def trial_state(mode):
    return dict(mode=mode,round=0,mp_ratio=1.,stats={side:{k:100 for k in
        ('might','guard','breach','mobility','sense','sustain')} for side in ('player','enemy')})


def test_trial_legacy_mp_tracks_real_maintenance_plus_ordinary_spending():
    import random
    from cultivation_life.system.combat.trials import run_batch
    d=domain(VoisinageEffect('strike',999,.1),stability=1000)
    own=caster(d,resource_link='legacy_mp',artifact_tier=2)
    b=VoisinageBattle([actor('player','player',own),actor('e','enemy',caster(d,artifact_tier=2))])
    state=trial_state('upper_final');_,rows=run_batch(b,state,random.Random(18),batch_size=1)
    assert state['mp_ratio']==pytest.approx(.945)
    assert rows[0]['player_mp_ratio']==pytest.approx(b.units['player'].current/100)


def test_reforming_endurance_manifestation_never_grants_yuhun_death_reward():
    import random
    from cultivation_life.system.combat.trials import run_batch
    d=domain(VoisinageEffect('strike',3,1))
    b=VoisinageBattle([actor('player','player',caster(d,body_mechanisms=(build('yuhun'),)),integrity=.5),actor('e','enemy')])
    run_batch(b,trial_state('voisinage_backlash'),random.Random(18),batch_size=1)
    assert not any(e['kind']=='death_restore' for e in b._light_trace)
    assert not b.units['e'].death_observed


def test_reforming_manifestation_does_not_unlock_sealed_energy_capacity():
    import random
    from cultivation_life.system.combat.trials import run_batch
    enemy=CombatCapabilities(capacity=1000,current=200,usable_capacity=200)
    b=VoisinageBattle([actor('player','player',CombatCapabilities()),actor('e','enemy',enemy)])
    run_batch(b,trial_state('voisinage_backlash'),random.Random(18),batch_size=1)
    assert b.units['e'].current==200


@pytest.mark.parametrize('left,right',[('ghost','ghost'),('ghost','monster'),('demonic','ghost'),('immortal','ghost')])
def test_roster_serialization_order_does_not_decide_causal_attack_outcome(left,right):
    import random
    from scripts.simulate_high_body_combat import make_battle,step,canonical
    first=make_battle(left,right,10,True,'low_energy',1)
    second=VoisinageBattle([s.unit for s in reversed(tuple(first.units.values()))])
    rng=random.Random(1);other=random.Random(1)
    for n in range(1,7):
        step(first,rng,n);step(second,other,n)
        assert canonical(dump_battle(first)['states'])==canonical(dump_battle(second)['states'])
        assert first.verdict()==second.verdict() and rng.getstate()==other.getstate()
        if first.verdict() is not None:break

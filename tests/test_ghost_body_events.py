"""Causal branches, live target sets, ghost mechanisms and resumable ledgers."""
import copy,json,random
from dataclasses import replace
import pytest

from cultivation_life.ghost_body_content import build
from cultivation_life.system.combat.body_mechanisms import enter,ActionAllowance
from cultivation_life.system.combat.contracts import CombatCapabilities,VoisinageEffect
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.trials import dump_battle,load_battle
from test_voisinage_effects import actor,caster,domain
from test_body_round_wuyun import start,m


def fight(rows=(),enemies=3,field=None):
    caps=caster(field,body_mechanisms=rows) if field else CombatCapabilities(capacity=100,current=100,artifact_tier=2,body_mechanisms=rows)
    return VoisinageBattle([actor('player','player',caps),*[actor(k,'enemy') for k in ('a','b','c')[:enemies]]])


def emit(b,*,chain=(),scope='all',targets=(),power=.1,extra=True):
    b._body_queue.append(('attack',dict(owner='player',scope=scope,targets=targets,power=power,chain=chain,label='测试攻击',extra=extra)))
    b._drain_body_events()


def test_actor_mechanism_path_is_branch_local_and_owner_specific():
    parent=enter((),'a','x');child=enter(parent,'b','x')
    assert enter(child,'a','x') is None
    assert enter(parent,'a','y')==enter(parent,'a','y')
    assert parent==(('a','x'),)


def test_karma_invokes_three_aoe_segments_and_one_extra_action():
    counter=CombatCapabilities(capacity=100,current=10,body_mechanisms=(m('shi',restore_state=.01,restore_energy=.01),))
    b=fight((build('yinguo'),build('zhaoye')))
    for k in ('a','b','c'):
        b.units[k].unit=replace(b.units[k].unit,capabilities=counter);b.units[k].current=10
    start(b);b._energy('player',50);b._drain_body_events()
    notes=[e for e in b._light_trace if e['kind']=='body_attack']
    assert len(notes)==3 and all(e['targets']==['a','b','c'] for e in notes)
    for k in ('a','b','c'):
        assert b.units[k].current==11
        assert b.units[k].vitality==pytest.approx(1-.12*.4*3+.01)
    assert len([e for e in b._light_trace if e['kind']=='counter_restore'])==3


def test_karma_counts_actual_cumulative_depletion_not_replenishment_or_capacity():
    b=fight((build('yinguo'),),1);start(b)
    b._energy('player',70);b._energy('player',100);b._energy('player',80)
    b._drain_body_events()
    assert len([e for e in b._light_trace if e['kind']=='karma'])==1
    assert b.units['player'].karma_spent==pytest.approx(0)
    b._energy('player',80);assert not b._body_queue
    b._energy('player',20);b._drain_body_events()
    assert b.units['player'].karma_spent==pytest.approx(.1)


def test_karma_own_chain_cannot_reenter_but_crossing_is_consumed():
    b=fight((build('yinguo'),),1);start(b)
    b._energy('player',0,(('player','yinguo'),));b._drain_body_events()
    assert not any(e['kind']=='karma' for e in b._light_trace)
    assert b.units['player'].karma_spent==0


def test_forget_exact_sets_ignore_order_and_do_not_rewrite_after_death():
    b=fight((build('wangqing'),));start(b)
    emit(b,scope='fixed',targets=('b','a'))
    emit(b,scope='fixed',targets=('a','b'))
    note=[e for e in b._light_trace if e['kind']=='forget'][-1]
    assert note['same'] and note['previous']==['a','b']
    b._lose('b',1);b._drain_body_events()
    assert b.units['player'].last_attack_targets==('a','b')
    emit(b,scope='fixed',targets=('a',))
    note=[e for e in b._light_trace if e['kind']=='forget'][-1]
    assert not note['same'] and note['spill_targets']==['c']


def test_aoe_death_changes_set_without_any_other_spill_target():
    b=fight((build('zhaoye'),build('wangqing')));start(b)
    b.units['c'].vitality=.15
    emit(b,power=.2)
    notes=[e for e in b._light_trace if e['kind']=='forget']
    assert notes[0]['same']
    assert notes[-1]['previous']==['a','b','c'] and notes[-1]['targets']==['a','b']
    assert not notes[-1]['same'] and not notes[-1]['spill_targets']
    assert len([e for e in b._light_trace if e['kind']=='body_attack' and e['owner']=='player'])==4


def test_sibling_segments_can_each_invoke_forget_without_recursive_self_damage():
    b=fight((build('zhaoye'),build('wangqing')),1);start(b)
    emit(b,power=.1)
    assert len([e for e in b._light_trace if e['kind']=='forget'])==2
    assert len([e for e in b._light_trace if e['kind']=='body_attack'])==5
    assert b.units['a'].vitality==pytest.approx(1-.04*3-.04*.15*2)


def test_single_target_split_locks_a_b_b_and_each_sibling_observes_history():
    class Dice:
        values=iter((.05,.4,.4))
        def random(self):return next(self.values)
    d=domain(VoisinageEffect('strike',3,.1,target_mode='single'))
    b=fight((build('zhaoye'),build('wangqing')),field=d)
    start(b,rng=Dice())
    notes=[e for e in b._light_trace if e['kind']=='forget']
    assert [(e['previous'],e['targets'],e['same']) for e in notes]==[(['a'],['b'],False),(['b'],['b'],True)]
    assert b.units['player'].current==95


def test_wuxiang_improves_field_recovery_without_restoring_energy():
    b=fight((build('wuxiang',10),),1);start(b)
    s=b.units['player'];s.vitality=.5;s.field_strain=.5;s.current=10
    b._restore_state('player',.1)
    assert s.vitality==pytest.approx(.63) and s.current==10


def test_energy_exchange_counts_real_loss_and_karma_uses_usable_capacity():
    own=CombatCapabilities(capacity=200,current=100,usable_capacity=100,body_mechanisms=(build('yinguo'),))
    other=CombatCapabilities(capacity=100,current=10,body_mechanisms=(m('shenhun',exchange_threshold=.4),))
    b=VoisinageBattle([actor('player','player',own),actor('a','enemy',other)])
    start(b,first='enemy')
    assert b.units['player'].current==10 and b.units['a'].current==100
    assert b.units['player'].karma_spent==pytest.approx(.4)
    assert len([e for e in b._light_trace if e['kind']=='karma'])==1


@pytest.mark.parametrize('state_field,value',[('karma_spent',float('nan')),('karma_spent',-.1),('last_attack_targets',['missing']),('death_observed',1)])
def test_bad_body_snapshot_is_rejected(state_field,value):
    b=fight((build('yinguo'),));frozen=dump_battle(b);frozen['states']['player'][state_field]=value
    with pytest.raises(ValueError):load_battle(frozen)


def test_forget_can_trigger_split_and_split_can_trigger_forget_but_not_cycle():
    b=fight((build('zhaoye'),build('wangqing')),1);start(b)
    # Ordinary attacks do not themselves split. Their forget reaction may split.
    b.ordinary_damage(.1,0);b.ordinary_damage(.1,0)
    assert len([e for e in b._light_trace if e['kind']=='split'])==1
    assert len([e for e in b._light_trace if e['kind']=='forget'])==1
    assert len([e for e in b._light_trace if e['kind']=='body_attack'])==3


def test_deaths_are_deduplicated_never_suppression_escape_or_resurrection():
    b=fight((build('yuhun'),build('wuxiang',10)));start(b)
    own=b.units['player'];own.current=0;own.vitality=.5
    b.units['a'].suppressed=True;b.units['b'].escaped=True
    b._body_death('a');b._body_death('b');b._drain_body_events()
    assert own.current==0
    b._lose('a',1);b._lose('a',1);b._drain_body_events()
    assert own.current==3 and own.vitality==pytest.approx(.539)
    own.vitality=0;b._lose('c',1);b._drain_body_events()
    assert own.vitality==0 and own.current==3


def test_karma_death_triggers_yuhun_and_wuxiang_without_permanent_body_restore():
    b=fight((build('yinguo'),build('yuhun'),build('wuxiang',10)),1);start(b)
    own=b.units['player'];own.vitality=.5;own.body=.6;b.units['a'].vitality=.1
    b._energy('player',50);b._drain_body_events()
    assert b.units['a'].vitality==0 and own.current==53
    assert own.vitality==pytest.approx(.539) and own.body==.6


def test_early_kill_in_three_segments_still_counts_one_action_for_living_observer():
    b=fight((build('zhaoye'),),1)
    observer=CombatCapabilities(capacity=100,current=10,body_mechanisms=(m('shi',restore_state=.01,restore_energy=.01),),reachable_ids=())
    b.units['observer']=type(b.units['a'])(actor('observer','enemy',observer),10,1)
    # The caster can reach only a; the observer still sees the extra action.
    own=b.units['player'];own.unit=replace(own.unit,capabilities=replace(own.unit.capabilities,reachable_ids=('a',)))
    start(b);b.units['a'].vitality=.03
    emit(b,power=.1)
    assert b.units['a'].vitality==0
    assert b.units['observer'].current==11
    assert len([e for e in b._light_trace if e['kind']=='counter_restore'])==1


def test_multiple_roots_can_each_crit_and_award_extra_without_reentering_ancestors():
    d=domain(VoisinageEffect('strike',1,.02))
    rows=(m('kan',extra=1),m('shou',critical=2),m('xiang',critical_extra=1,free=1))
    b=fight(rows,1,field=d);start(b)
    notes=[e for e in b._light_trace if e['kind']=='body_action']
    assert len(notes)==4 and sum(e['critical'] for e in notes)==2
    assert all(len(t.chain)==len(set(t.chain)) for t in b._body_round.allowances['player'])


def test_json_snapshot_and_saved_rng_replay_identical_target_and_evade_results():
    d=domain(VoisinageEffect('strike',3,.03,target_mode='single'))
    b=fight((build('zhaoye'),build('wangqing')),field=d)
    rng=random.Random(313);start(b,rng=rng)
    frozen=json.loads(json.dumps(dump_battle(b)));rng_state=rng.getstate()
    resumed=load_battle(frozen);other=random.Random();other.setstate(rng_state)
    start(b,n=2,rng=rng);start(resumed,n=2,rng=other)
    assert json.loads(json.dumps(b.report()))==json.loads(json.dumps(resumed.report()))
    assert json.loads(json.dumps(dump_battle(b)))==json.loads(json.dumps(dump_battle(resumed)))
    assert rng.getstate()==other.getstate()


def test_paid_field_splits_once_and_does_not_consume_three_fees():
    d=domain(VoisinageEffect('strike',3,.1))
    b=fight((build('zhaoye'),),field=d);start(b)
    assert b.units['player'].current==95
    assert all(b.units[k].vitality==pytest.approx(.88) for k in ('a','b','c'))
    assert len([e for e in b._light_trace if e['kind']=='body_action'])==1


def test_snapshot_restores_cumulative_energy_history_and_death_dedup():
    b=fight((build('yinguo'),build('wangqing'),build('yuhun')),2);start(b)
    b._energy('player',70);emit(b,power=.1)
    b._lose('b',1);b._drain_body_events()
    frozen=json.loads(json.dumps(dump_battle(b)));restored=load_battle(frozen)
    assert restored.units['b'].death_observed
    start(restored,n=2);restored._energy('player',53);restored._drain_body_events()
    assert restored.units['player'].karma_spent==pytest.approx(0)
    assert restored.units['player'].last_attack_targets==('a',)
    assert len([e for e in restored._light_trace if e['kind']=='death_restore'])==0


def test_silence_blocks_ghost_mechanisms_but_keeps_original_plan():
    b=fight((build('yinguo'),build('zhaoye'),build('wangqing'),build('yuhun'),build('wuxiang')))
    s=b.units['a'];s.unit=replace(s.unit,capabilities=CombatCapabilities(body_mechanisms=(m('qian',silence=1),)))
    start(b,first='enemy');b._energy('player',0);b._drain_body_events()
    assert b._body_round.triggered_count('player')==5
    assert not any(e['kind'] in {'karma','split','forget','death_restore'} for e in b._light_trace)

"""Round-start facts, bounded allowances, real settlement and paid five aggregates."""
import copy,random
from dataclasses import replace
import pytest

from cultivation_life.system.combat.body_mechanisms import BodyMechanism,BodyRound
from cultivation_life.system.combat.contracts import CombatCapabilities,Intervention,VoisinageEffect
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.trials import dump_battle,load_battle
from cultivation_life.system.wuyun import profile,definitions
from cultivation_life.body_mechanism_content import build,validate_config
from test_voisinage_effects import actor,caster,domain
from test_asura_manifestation import ready


def m(key,**effects):return BodyMechanism(key,key,effects)


def start(b,n=1,rng=None,first='player'):
    return b.begin_round(n,player_condition=1,enemy_condition=1,player_mp=1,enemy_mp=1,rng=rng or random.Random(71),first_side=first)


def offensive(*,free=0,extra=1,cost=3,current=100,enemy=None,targets=1):
    rows=(m('critical',critical=2),BodyMechanism('extra','想蕴',{'critical_extra':extra,'free':free},requires=('critical',)))
    d=domain(VoisinageEffect('strike',cost,.1),stability=200)
    return VoisinageBattle([actor('player','player',caster(d,current=current,body_mechanisms=rows)),
        *[actor(f'enemy-{i}','enemy',enemy) for i in range(targets)]])


def test_critical_and_extra_are_paid_once_per_cast_not_per_victim():
    b=offensive(targets=3);start(b)
    assert all(s.vitality==pytest.approx(.7) for k,s in b.units.items() if k!='player')
    assert b.units['player'].current==92
    assert len([e for e in b._light_trace if e['kind']=='body_action'])==2
    assert sum(t.spent for t in b._body_round.allowances['player'])==2


@pytest.mark.parametrize('free,expected',[(0,.8),(1,.7)])
def test_free_extra_is_quoted_before_affordability_with_zero_remaining_energy(free,expected):
    b=offensive(free=free,current=5);start(b)
    assert b.units['player'].current==0
    assert b.units['enemy-0'].vitality==pytest.approx(expected)
    assert b.units['player'].vitality==1


def test_no_actual_critical_means_no_conditional_allowance_or_counter_recovery():
    defense=CombatCapabilities(capacity=100,current=20,body_mechanisms=(m('counter',restore_state=.1,restore_energy=.1),),
        interventions=(Intervention('resist',('strike',),strength=1),))
    b=offensive(free=1,enemy=defense);start(b)
    assert b.units['player'].current==98 and b.units['enemy-0'].current==20
    assert b.units['enemy-0'].vitality==1
    assert 'player' not in b._body_round.critical_completed
    assert not any(e['kind']=='counter_restore' for e in b._light_trace)


def test_generic_budget_supports_multiple_declared_extra_actions_without_new_rolls():
    d=domain(VoisinageEffect('strike',3,.05))
    b=VoisinageBattle([actor('player','player',caster(d,body_mechanisms=(m('future-route',extra=3),))),actor('e','enemy')])
    start(b)
    assert b.units['e'].vitality==pytest.approx(.8) and b.units['player'].current==86
    assert len([e for e in b._light_trace if e['kind']=='body_action'])==4


def test_critical_is_frozen_and_free_is_sampled_once_when_extra_is_created():
    class Dice:
        calls=0
        def random(self):self.calls+=1;return .1
    dice=Dice();b=offensive()
    rows=(BodyMechanism('critical','受蕴',{'critical':2},chance=.5),
          BodyMechanism('extra','想蕴',{'critical_extra':1,'free':.5},requires=('critical',)))
    b.units['player'].unit=replace(b.units['player'].unit,capabilities=replace(b.units['player'].unit.capabilities,body_mechanisms=rows))
    start(b,rng=dice)
    assert dice.calls==2
    assert b.units['enemy-0'].vitality==pytest.approx(.7)


def test_counter_heals_state_and_usable_energy_once_for_a_free_multi_target_cast():
    counter=CombatCapabilities(capacity=100,current=20,usable_capacity=60,
                              body_mechanisms=(m('shi',restore_state=.1,restore_energy=.1),))
    b=offensive(free=1,enemy=counter,targets=2);start(b)
    for key in ('enemy-0','enemy-1'):
        assert b.units[key].vitality==pytest.approx(.8)
        assert b.units[key].current==26
        assert b.units[key].body==pytest.approx(1-.3*.46)
    notes=[e for e in b._light_trace if e['kind']=='counter_restore']
    assert len(notes)==2 and all(e['count']==1 for e in notes)


def test_counter_never_resurrects_a_unit_killed_by_the_extra_action():
    counter=CombatCapabilities(capacity=100,current=20,body_mechanisms=(m('shi',restore_state=1,restore_energy=1),))
    b=offensive(free=1,enemy=counter)
    b.units['enemy-0'].vitality=.3;start(b)
    assert not b.units['enemy-0'].fighting and b.units['enemy-0'].current==20
    assert not any(e['kind']=='counter_restore' for e in b._light_trace)


def test_raw_trigger_counts_survive_silence_and_amplify_state_without_extra_body_injury():
    d=domain(VoisinageEffect('strike',3,.1))
    mine=(m('xing',exploit=.1),m('silencer',silence=1))
    theirs=(m('first',authority=.1),m('second',critical=2))
    b=VoisinageBattle([actor('player','player',caster(d,body_mechanisms=mine)),actor('enemy','enemy',CombatCapabilities(body_mechanisms=theirs))])
    start(b)
    assert b._body_round.triggered_count('enemy')==2
    assert b._body_round.effective['enemy']=={}
    assert b._body_round.amplification('player','enemy')==pytest.approx(.2)
    assert b.units['enemy'].vitality==pytest.approx(.88)
    assert b.units['enemy'].body==pytest.approx(1-.1*.46)


def test_silenced_xing_retains_full_candidate_but_executes_no_amplification():
    rows=tuple(replace(build(row,0),chance=1,effects={'exploit':.1} if row['id']=='xing' else build(row,0).effects)
               for row in definitions())
    d=domain(VoisinageEffect('strike',3,.1),stability=200)
    lights=dict(kun=1,zhen=1,kan=1,li=.01,qian=1)
    b=VoisinageBattle([actor('player','player',caster(d,body_mechanisms=rows)),
                      actor('enemy','enemy',caster(d,divine_lights=lights))])
    start(b,first='enemy')
    assert b._body_round.triggered_count('player')==5 and b._body_round.triggered_count('enemy')==5
    assert b._body_round.amplification('player','enemy',raw=True)==pytest.approx(.5)
    assert b._body_round.amplification('player','enemy')==0
    assert b.ward_tier('player')==1
    assert any('候选削弱增幅50%' in e and '实际增幅0%' in e for e in b.frame.events)
    assert not any(e['kind'] in {'body_action','counter_restore'} and e['owner']=='player' for e in b._light_trace)


@pytest.mark.parametrize('first',['player','enemy'])
def test_both_silencers_roll_before_arbitration_but_only_first_can_execute(first):
    class Dice:
        calls=0
        def random(self):self.calls+=1;return .1
    dice=Dice();caps=CombatCapabilities(body_mechanisms=(BodyMechanism('silence','乾古',{'silence':1},chance=.5),))
    b=VoisinageBattle([actor(s,s,caps) for s in ('player','enemy')]);start(b,rng=dice,first=first)
    assert dice.calls==2 and all(b._body_round.records[k]['silence']['triggered'] for k in b.units)
    other='enemy' if first=='player' else 'player'
    assert b._light_muted=={other:first}


def test_no_field_and_lost_field_do_not_spin_the_allowance_executor():
    caps=CombatCapabilities(body_mechanisms=(m('extra',extra=8),))
    b=VoisinageBattle([actor('player','player',caps),actor('e','enemy')]);start(b)
    assert b.units['e'].vitality==1


def test_silencing_unrelated_body_outputs_does_not_remove_independent_ward():
    mine=CombatCapabilities(ward_tier=2,body_mechanisms=(m('critical',critical=2),))
    theirs=CombatCapabilities(body_mechanisms=(m('silence',silence=1),))
    b=VoisinageBattle([actor('player','player',mine),actor('enemy','enemy',theirs)])
    start(b,first='enemy')
    assert b._body_round.value('player','critical')==0 and b.ward_tier('player')==2


def test_real_snapshot_roundtrip_preserves_mechanisms_costs_and_rng():
    b=offensive(free=.4);rng=random.Random(194)
    start(b,rng=rng);b.finish_round(player_mp=1,enemy_mp=1)
    restored=load_battle(dump_battle(b));other=random.Random();other.setstate(rng.getstate())
    start(b,2,rng=rng);start(restored,2,rng=other)
    assert b.report()==restored.report() and b.updates()==restored.updates()
    assert rng.getstate()==other.getstate()


def test_actor_storage_order_does_not_change_rolls_or_effective_mechanisms():
    rows=(BodyMechanism('critical','受',{'critical':2},chance=.5),)
    actors=[actor(k,s,CombatCapabilities(body_mechanisms=rows)) for k,s in [('a','player'),('b','enemy')]]
    states=[]
    for roster in (actors,list(reversed(actors))):
        b=VoisinageBattle(roster);start(b,rng=random.Random(93));states.append(b._body_round.report())
    assert states[0]==states[1]


@pytest.mark.parametrize('rows',[(m('duplicate',extra=1),m('duplicate',extra=1)),
    (BodyMechanism('loop','循环',{'extra':1},requires=('loop',)),),
    (BodyMechanism('missing','缺失',{'extra':1},requires=('other',)),)])
def test_invalid_dependency_graphs_fail_before_combat(rows):
    with pytest.raises(ValueError):CombatCapabilities(body_mechanisms=rows)


def test_paid_training_is_independent_stale_safe_and_time_rng_neutral(ready):
    from cultivation_life.rules import add_item
    e,g=ready;g.player.asura_cultivation['body_level']=50;g.player.opportunity=10**12
    for row in definitions():
        for key in row['recipe']:add_item(g.player,key,100)
    e.store.save(g)
    e.get_game(g.id);before=e.store.load(g.id);shown=e.asura_action(g.id,'train_aggregate','shou',expected_level=0)
    saved=e.store.load(g.id);assert saved.player.asura_cultivation['aggregates']=={'shou':1}
    assert saved.player.age==before.player.age and saved.rng_state==before.rng_state
    assert saved.player.asura_cultivation['souls']<before.player.asura_cultivation['souls']
    assert saved.player.opportunity<before.player.opportunity
    assert next(r for r in profile(saved.player,player=True) if r.id=='shou').chance==pytest.approx(.13)
    path=e.store._path(g.id);data=path.read_bytes()
    with pytest.raises(ValueError,match='等级已变化'):e.asura_action(g.id,'train_aggregate','shou',expected_level=0)
    assert path.read_bytes()==data and len(shown['asura']['aggregates'])==5


@pytest.mark.parametrize('level,count',[(9,0),(10,1),(20,2),(30,3),(40,4),(50,5)])
def test_actual_magic_body_unlocks_and_fifty_layer_cap(ready,level,count):
    e,g=ready;g.player.asura_cultivation['body_level']=level
    assert len(profile(g.player,player=True))==count
    assert len(profile({'path':'demonic','immortal_body_level':level,'realm_index':12}))==count
    if level==50:
        e.store.save(g);e.get_game(g.id);path=e.store._path(g.id);before=path.read_bytes()
        with pytest.raises(ValueError,match='50'):e.asura_action(g.id,'train_body')
        assert path.read_bytes()==before


def test_magic_mirrors_copy_exact_body_mechanisms_and_freeze_training(ready):
    from cultivation_life.engine.progression import asura_trials
    e,g=ready;g.player.asura_cultivation.update(body_level=50,aggregates=dict(se=1,shou=2,xiang=3,xing=4,shi=5))
    asura_trials.start(e._dependencies.asura_trials,g,'asura_breakthrough')
    b=load_battle(g.active_trial['snapshot']);own=b.units['player'].unit.capabilities.body_mechanisms
    assert len(own)==5 and [r.level for r in own]==[1,2,3,4,5]
    assert all(s.unit.capabilities.body_mechanisms==own for s in b.units.values())
    g.player.asura_cultivation['aggregates']['shou']=10
    assert load_battle(g.active_trial['snapshot']).units['enemy-0'].unit.capabilities.body_mechanisms==own


def test_busy_training_cannot_spend_resources_or_rng(ready):
    from cultivation_life.system.wuyun_cultivation import train
    from cultivation_life.rules import has_item,remove_item
    _,g=ready;g.map_journey={'destination':'busy'};before=copy.deepcopy(g)
    with pytest.raises(ValueError,match='旅行'):train(g,'se',0,has_item=has_item,remove_item=remove_item)
    assert g==before


def test_asura_condensation_and_fusion_are_available_at_ten_not_nine(ready):
    e,g=ready;g.player.asura_cultivation['body_level']=9
    g.player.puppets=[dict(id=f'b{i}',name='机关',alive=True,body_training=100,type='mechanical',form='heavenly_statue') for i in range(2)]
    e.store.save(g)
    with pytest.raises(ValueError,match='10层'):e.asura_action(g.id,'condense','b0')
    g=e.store.load(g.id);g.player.asura_cultivation['body_level']=10;e.store.save(g)
    for i in range(2):e.asura_action(g.id,'condense',f'b{i}')
    e.asura_action(g.id,'fuse',body_ids=['b0','b1'])
    assert e.store.load(g.id).active_trial['kind']=='asura_fusion'


def test_real_npc_combat_uses_its_own_magic_body_without_player_growth():
    from cultivation_life.models import SectNpc
    from cultivation_life.content_registry import WORLD_SYSTEMS
    from cultivation_life.system.combat.npc_battle import resolve_npc_engagement
    magic=SectNpc('magic-body','五蕴修士','',9,1,100,None,path='demonic',world='asura',body_training=100,immortal_body_level=50)
    other=SectNpc('other-body','寻常修士','',12,9,100,None,body_training=100,immortal_body_level=0)
    report=resolve_npc_engagement([(magic,100)],[(other,100)],WORLD_SYSTEMS['transcendent_combat'],random.Random(81),max_rounds=2)
    assert report is not None
    raw=report.rounds[0]['voisinage']['body_mechanisms']['raw']
    assert len(raw['magic-body'])==5 and all(r['level']==10 for r in raw['magic-body'].values())
    assert not raw['other-body']


def test_wuyun_record_survives_canonical_sealed_descent_and_return(ready):
    from cultivation_life.runtime import decode_rng,encode_rng
    from cultivation_life.rules import add_item,has_item
    from cultivation_life.system.world_transition_system import finish_world_transition
    e,g=ready;g.player.asura_cultivation.update(body_level=50,aggregates=dict(se=1,shou=2,xiang=3,xing=4,shi=5))
    original=copy.deepcopy(g.player.asura_cultivation);expected=profile(g.player,player=True)
    material=next(iter(definitions()[0]['recipe']));add_item(g.player,material,27)
    rng=decode_rng(g.seed,g.rng_state)
    for destination,mode in [('true_demon','sealed_descent'),('asura','sealed_return')]:
        before=g.to_dict();plan=e._plan_world_transition(g,destination,mode)
        assert g.to_dict()==before
        e._apply_world_transition(g,plan);finish_world_transition(g,rng,e._refresh_world_market)
        assert g.player.asura_cultivation==original and profile(g.player,player=True)==expected
        assert has_item(g.player,material,27) and not has_item(g.player,material,28)
    g.rng_state=encode_rng(rng);e.store.save(g)
    assert e.store.load(g.id).player.asura_cultivation==original


@pytest.mark.parametrize('malformation',['cycle','probability','unknown_output','cost'])
def test_optional_content_rejects_invalid_aggregate_definitions(malformation):
    from cultivation_life.system.asura import config
    cfg=copy.deepcopy(config())
    if malformation=='cycle':cfg['five_aggregates'][0]['requires']=['se']
    elif malformation=='probability':cfg['five_aggregates'][1]['chance']['growth']=10
    elif malformation=='unknown_output':cfg['five_aggregates'][0]['effects']['execute_script']={'base':1,'growth':0}
    else:cfg['five_aggregates'][0]['cost']['souls']=-1
    with pytest.raises(ValueError):validate_config(cfg)


def test_free_extra_preserves_a_cost_discount_for_the_next_paid_cast():
    from test_combat_semantics import rule,status
    discount=rule('effect_resolved',status('next-paid',
        modifiers=[{'channel':'field.effect_cost','value':-.5}],consume_on='effect_prepare'),
        limits={'per_battle':1})
    b=offensive(free=1)
    b=VoisinageBattle([replace(s.unit,capabilities=replace(s.unit.capabilities,semantic_rules=(discount,)))
        if key=='player' else s.unit for key,s in b.units.items()])
    own=b.units['player']
    start(b)
    assert own.current==95 and len(b.semantics.statuses)==1
    b.finish_round(player_mp=1,enemy_mp=1)
    start(b,2)
    assert own.current==pytest.approx(92.5) and not b.semantics.statuses

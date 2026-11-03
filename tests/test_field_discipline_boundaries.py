"""Causal boundaries, ownership, finite leases and frozen field techniques."""
import copy,json,random
from dataclasses import asdict,replace
from types import SimpleNamespace
import pytest

from cultivation_life.asura_discipline_content import build,validate,select_plan
from cultivation_life.system import asura
from cultivation_life.system.combat.contracts import VoisinageEffect,CombatCapabilities
from cultivation_life.system.combat.field_contracts import FieldDiscipline
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.trials import dump_battle,load_battle,run_batch
from scripts.calibrate_upper_breakthroughs import prepare
from scripts.simulate_high_body_combat import profile
from test_field_disciplines import fight,descriptor,actions,NATIVE
from test_voisinage_effects import actor,caster,domain
from test_body_round_wuyun import start,m
from test_asura_manifestation import ready,route


@pytest.mark.parametrize('route_id',NATIVE)
@pytest.mark.parametrize('level',[1,2,3,4,6,7,9])
def test_authored_unlocks_are_three_distinct_mechanisms_not_extra_body_trigger_types(route_id,level):
    b=fight(route_id,level=level,extra=(m('body',ward=2),));start(b)
    d=b.units['player'].unit.capabilities.field_discipline
    assert sum(level>=n for n in (2,4,7))==len([name for name,n in zip(d.names,(2,4,7)) if level>=n])
    assert b._body_round.triggered_count('player')==1
    assert len(b._body_round.records['player'])==1


@pytest.mark.parametrize('route_id',NATIVE)
def test_silence_and_release_recovery_block_new_active_mechanisms(route_id):
    b=fight(route_id,extra=(m('shou',critical=2),),enemy_body=(m('qian',silence=1),))
    b.units['player'].body=b.units['player'].vitality=.5;start(b,first='enemy')
    assert not actions(b)
    c=fight(route_id);c.units['player'].release_recovery_round=1
    start(c)
    assert not actions(c) and c.units['player'].body==1


def test_timed_artifact_control_is_consumed_after_the_restricted_ordinary_attempt():
    b=fight('mahoraga',enemy_body=(m('feixue',release_cost=.1),),
        enemy_field=domain(VoisinageEffect('seal',999,.1),strength=1,stability=1))
    e=b.units['e0'];e.unit=replace(e.unit,capabilities=replace(e.unit.capabilities,artifact_tier=2))
    e.timed_controls['artifact']=dict(source='player',expires=3,attempt=True)
    start(b,2);before=b.units['player'].body
    b.ordinary_damage(0,.1)
    assert b.units['player'].body==before and 'artifact' not in e.restrictions
    start(b,3);b.ordinary_damage(0,.1)
    assert b.units['player'].body<before


def test_lost_control_source_does_not_leave_a_field_closed_or_charge_opening_twice():
    b=fight('mahoraga',current=0)
    e=b.units['e0'];e.timed_controls['voisinage']=dict(source='player',expires=2,attempt=False)
    start(b)
    assert not e.timed_controls and e.active_voisinage
    assert e.current==98


def test_break_and_interdict_are_resisted_normally_and_cancelled_intents_do_not_consume_marks():
    b=fight('mahoraga',mode='artifact',enemy_body=(m('kun',seal_resist=1),))
    b._field_memory('player')['marks']['e0']=dict(count=2,expires=5)
    start(b)
    assert not b.units['e0'].timed_controls and b._field_memory('player')['marks']['e0']['count']==0
    # The paid attempt consumed the imprints, but did not fabricate a successful control.
    assert b.units['player'].current==95
    from cultivation_life.system.combat.contracts import Intervention
    c=fight('mahoraga',mode='artifact')
    e=c.units['e0'];e.unit=replace(e.unit,capabilities=replace(e.unit.capabilities,
        interventions=(Intervention('resist',('restrict',),strength=1000),)))
    c=VoisinageBattle([s.unit for s in c.units.values()])
    c._field_memory('player')['marks']['e0']=dict(count=2,expires=5)
    start(c)
    assert c.units['player'].current==98 and c._field_memory('player')['marks']['e0']['count']==2


def test_free_blood_action_does_not_sacrifice_hp_to_manufacture_six_arms():
    b=fight('asura',mode='blood');start(b)
    # Six-arms has already been used. A fresh free token cannot pay a zero fee with HP.
    from cultivation_life.system.combat.body_mechanisms import ActionAllowance
    rows=b._body_round.allowances['player'];rows.append(ActionAllowance(source='other',free=True,slot=len(rows)))
    before=b.units['player'].body;b._execute_field_actions(dict(b._dominated))
    assert b.units['player'].body==before
    assert sum('六臂' in t and '取得一份' in t for t in b.frame.events)==1


def test_hunter_waits_for_actual_recovery_not_an_evaded_or_empty_treatment():
    b=fight('yaksha',mode='ambush')
    start(b);assert not actions(b)
    b._field_healed('e0',0);assert not b._body_round.allowances['player'][0].ready
    b._field_healed('e0',.01);b._execute_field_actions(dict(b._dominated))
    assert len(actions(b))==1
    b._field_healed('e0',.5);b._execute_field_actions(dict(b._dominated))
    assert len(actions(b))==1


@pytest.mark.parametrize('family',['immortal','demonic','monster','ghost'])
def test_field_action_uses_other_body_mechanisms_without_recursive_source_reentry(family):
    caps=profile(family,10)
    from cultivation_life.system.combat.body_mechanisms import mechanisms
    body=mechanisms(CombatCapabilities(**caps))
    b=fight('asura',mode='blood',count=2,extra=body,enemy_body=body)
    for n in range(1,7):
        start(b,n,rng=random.Random(n));b.ordinary_damage(.05,.05);b.finish_round(player_mp=1,enemy_mp=1)
        assert all(len(t.chain)==len(set(t.chain)) for rows in b._body_round.allowances.values() for t in rows)
        assert all(0<=s.current<=b._usable_energy(s) and 0<=s.body<=1 and 0<=s.vitality<=1 for s in b.units.values())
        if b.verdict():break


@pytest.mark.parametrize('route_id',NATIVE)
def test_json_and_reversed_rosters_preserve_memories_costs_reports_and_rng(route_id):
    b=fight(route_id,body=.6,state=.6,count=2,extra=(m('shou',critical=2),m('xiang',critical_extra=1,free=.5)))
    b.units['player'].field_strain=.3
    reverse=load_battle(json.loads(json.dumps(dump_battle(b))))
    reverse.units=dict(reversed(tuple(reverse.units.items())))
    rng=random.Random(823);other=random.Random(823)
    for n in range(1,9):
        if n%2==0:
            b=load_battle(json.loads(json.dumps(dump_battle(b))))
        for battle,dice in ((b,rng),(reverse,other)):
            start(battle,n,rng=dice);battle.ordinary_damage(.05,.05);battle.finish_round(player_mp=1,enemy_mp=1)
        a=json.loads(json.dumps(dump_battle(b)));c=json.loads(json.dumps(dump_battle(reverse)))
        a['units'].sort(key=lambda r:r['id']);c['units'].sort(key=lambda r:r['id'])
        assert a==c
        assert b.report()==reverse.report() and rng.getstate()==other.getstate()
        if b.verdict():break


@pytest.mark.parametrize('route_id',NATIVE)
def test_actual_breakthrough_freezes_full_disciplines_including_plans_for_all_mirrors(route_id):
    trial,_=prepare('demonic',11,'peak',route_id,930211)
    battle=load_battle(trial['snapshot']);own=battle.units['player'].unit.capabilities.field_discipline
    assert own and own.level==9 and own.id=='asura:'+route_id
    assert all(s.unit.capabilities.field_discipline==own for s in battle.units.values())
    frozen=json.loads(json.dumps(trial['snapshot']));after=load_battle(frozen)
    assert after.units['player'].unit.capabilities.field_discipline==own


@pytest.mark.parametrize('field,value',[
 ('charge',float('nan')),('charge',-1),('charge',.2),('chorus',True),('notes',8),('echo',[]),
 ('echo',{'kind':'strike','restriction':None,'source':'missing'}),('hunt','missing'),
 ('marks',{'missing':{'count':2,'expires':2}}),('unknown',1),
])
def test_malformed_memory_is_rejected_instead_of_rebuilt(field,value):
    b=fight('deva');raw=dump_battle(b);raw['states']['player']['field_memory']={field:value}
    with pytest.raises(ValueError):load_battle(raw)


def test_old_snapshot_without_new_descriptor_keeps_its_explicit_original_rules():
    b=fight('deva');raw=json.loads(json.dumps(dump_battle(b)))
    for row in raw['units']:row['capabilities'].pop('field_discipline')
    for state in raw['states'].values():
        for key in ('field_memory','timed_controls','field_debts'):state.pop(key)
    restored=load_battle(raw)
    assert all(s.unit.capabilities.field_discipline is None for s in restored.units.values())
    start(restored)
    assert 'field_powers' not in restored.report()


def test_real_plan_is_free_stale_safe_locked_and_preserved_by_snapshot(ready):
    e,g=ready;route(g.player,'deva',level=2,rank=8);e.store.save(g);e.get_game(g.id);g=e.store.load(g.id)
    path=e.store._path(g.id);before=path.read_bytes()
    with pytest.raises(ValueError):e.asura_action(g.id,'set_field_plan','mode:judgment',expected_level=2)
    assert path.read_bytes()==before
    with pytest.raises(ValueError,match='等级已变化'):e.asura_action(g.id,'set_field_plan','mode:heal',expected_level=1)
    assert path.read_bytes()==before
    result=e.asura_action(g.id,'set_field_plan','mode:heal',expected_level=2)
    now=e.store.load(g.id)
    assert now.player.asura_cultivation['discipline_plan']=={'mode':'heal'}
    assert now.player.age==g.player.age and now.rng_state==g.rng_state
    assert now.player.asura_cultivation['souls']==g.player.asura_cultivation['souls']
    assert result['asura']['field_discipline']['mode']=='heal'


@pytest.mark.parametrize('state_field,value',[('spirit_state',{'mode':'wandering'}),('ghost_host_body',{})])
def test_bodiless_or_possessed_player_does_not_borrow_original_eightfold_body(ready,state_field,value):
    _,g=ready;route(g.player,'asura',level=9,rank=13)
    setattr(g.player,state_field,value)
    if state_field=='ghost_host_body':g.player.ghost_core_state={}
    assert asura.source(g.player).field_discipline is None


def test_report_does_not_mutate_after_later_imprint_or_resource_changes():
    b=fight('mahoraga',mode='seal');start(b)
    old=b.report();canonical=json.loads(json.dumps(old))
    start(b,2)
    assert json.loads(json.dumps(old))==canonical


@pytest.mark.parametrize('route_id,family,scenario,rank,size',[
 ('yaksha','immortal','strain',10,1),('yaksha','monster','low_energy',10,1),
 ('deva','immortal','normal',5,3),('mahoraga','immortal','strain',10,3),
 ('asura','ghost','low_energy',10,3),
])
def test_production_roster_permutation_keeps_resistance_guard_text_and_rng_order(route_id,family,scenario,rank,size):
    from scripts.simulate_field_disciplines import run
    result=run(route_id,route_id,rank,size,scenario,12000,limit=12,check=True,families=(family,family))
    assert result['permutations']>=1


@pytest.mark.parametrize('route_id,families,scenario,rank',[
 ('yaksha',('monster','immortal'),'strain',5),
 ('gandharva',('monster','demonic'),'strain',5),
 ('gandharva',('monster','monster'),'strain',10),
 ('kinnara',('immortal','demonic'),'normal',10),
 ('kinnara',('immortal','demonic'),'low_energy',10),
])
def test_group_state_projection_sums_are_independent_of_roster_order(route_id,families,scenario,rank):
    from scripts.simulate_field_disciplines import run
    run(route_id,route_id,rank,3,scenario,12000,limit=48,check=True,families=families)


@pytest.mark.parametrize('action',['set_field_plan','train_route'])
@pytest.mark.parametrize('busy',['trial','journey','wandering'])
def test_real_training_and_plan_requests_obey_original_busy_guards(ready,action,busy):
    e,g=ready;route(g.player,'deva',level=2,rank=8)
    if busy=='trial':
        from cultivation_life.engine.progression import asura_trials
        asura_trials.start(e._dependencies.asura_trials,g,'asura_breakthrough')
    elif busy=='journey':g.map_journey={'status':'travelling'}
    else:g.player.spirit_state={'mode':'wandering'}
    e.store.save(g);path=e.store._path(g.id)
    # Use store load at the business boundary: an intentionally minimal travel
    # fixture is not a real journey to be progressed by presentation.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(e,'_load',e.store.load)
        before=path.read_bytes()
        with pytest.raises(ValueError):e.asura_action(g.id,action,'mode:heal',expected_level=2)
        assert path.read_bytes()==before


def test_imprint_count_is_actual_bounded_and_empty_seals_do_not_add_marks():
    b=fight('mahoraga',mode='seal');start(b)
    assert b._field_memory('player')['marks']['e0']['count']==2
    before=copy.deepcopy(b._field_memory('player')['marks'])
    b.units['player'].current=0;start(b,2)
    assert b._field_memory('player')['marks']==before


def test_blood_field_damage_writes_to_the_original_player_hp_once(ready):
    from cultivation_life.rules import max_hp,max_mp
    e,g=ready;route(g.player,'asura',level=9,rank=13)
    g.player.asura_cultivation['discipline_plan']={'mode':'blood'}
    g.player.hp=max_hp(g.player);g.player.mp=max_mp(g.player);before=g.player.hp
    e._combat(g,dict(target_name='实血验收',target_power=e._player_battle_power(g),target_realm_index=9,
        target_layer=1,kind='environment',combat_type='cultivator',max_rounds=1),False,random.Random(1))
    events=[event for row in g.last_combat_report['rounds']
        for event in row.get('voisinage',{}).get('divine_lights',{}).get('events',[])]
    paid=sum(event.get('body_cost',0) for event in events if event.get('owner')=='player')
    assert paid>0 and g.player.hp<before
    assert before-g.player.hp==pytest.approx(paid*max_hp(g.player),abs=2)

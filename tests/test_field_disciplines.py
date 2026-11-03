"""Eight different field loops use the real field effects and original ledgers."""
import copy,json,random
from dataclasses import replace
import pytest

from cultivation_life.system import asura
from cultivation_life.asura_discipline_content import build
from cultivation_life.system.combat.contracts import CombatCapabilities,VoisinageEffect
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.trials import dump_battle,load_battle
from test_voisinage_effects import actor,caster,domain
from test_body_round_wuyun import start,m

NATIVE={'deva':'restore_body','naga':'suppress','yaksha':'strike','gandharva':'restore_spirit',
    'mahoraga':'seal','kinnara':'restore_field','garuda':'strike','asura':'strike'}


def descriptor(route,level=9,mode='auto',opening=0):
    return build(dict(route=route,level=level,discipline_plan=dict(mode=mode,opening=opening),branches={route:[]}),asura.config())


def fight(route,*,level=9,mode='auto',opening=0,body=1,state=1,extra=(),enemy_body=(),count=1,
          own_field=None,enemy_field=None,current=100,enemy_current=100,stance='press',allies=()):
    kind=NATIVE[route]
    d=own_field or domain(VoisinageEffect(kind,3,.2,target='self' if kind.startswith('restore') else 'enemy'),effect_cost=3,restore_threshold=.85)
    weak=enemy_field or domain(VoisinageEffect('seal',999,.1),strength=1,stability=1,effect_cost=3)
    own=caster(d,current=current,artifact_tier=2,ward_tier=2,body_mechanisms=extra,
        field_discipline=descriptor(route,level,mode,opening),stance=stance,protect_ids=tuple(a.id for a in allies))
    enemy=caster(weak,current=enemy_current,body_mechanisms=enemy_body)
    return VoisinageBattle([actor('player','player',own,integrity=state,body_integrity=body),
        *[actor(f'e{i}','enemy',enemy) for i in range(count)],*allies])


def actions(b,key='player'):
    return [e for e in b._light_trace if e['kind']=='body_action' and e['owner']==key]


def test_tian_real_healing_accumulates_once_and_judgment_consumes_instead_of_healing():
    b=fight('deva',body=.4,state=.4)
    start(b);p=b.units['player']
    assert p.body==pytest.approx(.6) and p.field_memory['charge']==pytest.approx(.13)
    start(b,2);assert p.body==pytest.approx(.8) and p.field_memory['charge']==pytest.approx(.26)
    start(b,3)
    assert p.body==pytest.approx(.8) and p.field_memory['charge']==pytest.approx(.02)
    assert b.units['e0'].body<1 and any('天罚' in s for s in b.frame.events)


def test_tian_empty_healing_never_produces_charge_and_no_attack_source_is_blocked():
    b=fight('deva');frame=start(b)
    assert b.units['player'].field_memory['charge']==0 and not actions(b)
    assert next(f for f in b.fields if f.owner=='player').targets==()
    assert frame.ordinary_player


def test_tian_actual_ordinary_hit_spends_charge_without_granting_an_extra_action():
    own=domain(VoisinageEffect('restore_body',3,.2,target='self'),stability=200,effect_cost=3)
    enemy=domain(VoisinageEffect('seal',999,.1),stability=200,effect_cost=3)
    b=fight('deva',level=2,body=.8,state=.8,extra=(m('zhen',heal_preserve=1),),own_field=own,enemy_field=enemy)
    start(b);b.ordinary_damage(.1,0)
    assert b.units['e0'].vitality==pytest.approx(.84)
    assert b.units['player'].field_memory['charge']==pytest.approx(.07)
    assert len(actions(b))==1 and len(b._body_round.allowances['player'])==1


def test_tian_guardian_heals_only_one_covered_ally_and_charges_the_caster():
    ally=actor('friend','player',integrity=.2,body_integrity=.2)
    b=fight('deva',level=4,mode='guardian',stance='protect',allies=(ally,))
    start(b)
    assert b.units['friend'].body==pytest.approx(.4) and b.units['player'].body==1
    assert b.units['player'].field_memory['charge']==pytest.approx(.13)
    assert not b.frame.ordinary_player or 'player' in b._ordinary_acted


def test_naga_actual_suppression_adds_pressure_and_burst_consumes_the_shared_pressure():
    b=fight('naga',mode='suppress');start(b)
    assert b.units['e0'].pressure==pytest.approx(.12)
    assert b.units['e0'].field_debts['player']['ratio']==.2
    s=b.units['player'];s.unit=replace(s.unit,capabilities=replace(s.unit.capabilities,field_discipline=descriptor('naga',mode='burst')))
    b.units['e0'].pressure=.4
    start(b,2)
    spent=next(e for e in b._light_trace if e.get('spent')==.25)
    assert spent['before']-spent['after']==pytest.approx(.25) and b.units['e0'].body<1
    assert any('决堤' in text for text in b.frame.events)


def test_naga_paid_cost_obligation_uses_the_original_energy_pool():
    heal=domain(VoisinageEffect('restore_body',3,.2,target='self'),strength=1,incursion=1000,stability=1,effect_cost=3)
    b=fight('naga',level=4,mode='suppress',enemy_field=heal,enemy_body=(m('zhen',heal_preserve=1),))
    b.units['e0'].body=.5;start(b)
    before=b.units['e0'].current;b.units['e0'].body=.5
    start(b,2)
    assert b.units['e0'].current==pytest.approx(before-1-3*1.2)
    assert any(e['kind']=='field_tithe' for e in b._light_trace)


def test_naga_unaffordable_tithe_cancels_one_attempt_without_partial_payment():
    heal=domain(VoisinageEffect('restore_body',3,.2,target='self'),strength=1,incursion=1000,stability=1,effect_cost=3)
    b=fight('naga',level=4,mode='suppress',enemy_field=heal,enemy_body=(m('zhen',heal_preserve=1),))
    b.units['e0'].body=.5;start(b)
    b.units['player'].current=2;b.units['e0'].current=4.4;b.units['e0'].body=.5
    start(b,2)
    assert b.units['e0'].current==pytest.approx(3.4)
    assert not b.units['e0'].field_debts
    assert any(e['kind']=='field_tithe_failed' for e in b._light_trace)


def test_yaksha_focuses_one_live_hunted_target_instead_of_copying_damage_to_every_enemy():
    b=fight('yaksha',level=2,count=2);b.units['e1'].vitality=.6;start(b)
    assert b.units['player'].field_memory['hunt']=='e1'
    assert b.units['e0'].vitality==1 and b.units['e1'].vitality==pytest.approx(.4)


def test_yaksha_reserved_base_action_wakes_after_real_healing_and_does_not_count_as_extra():
    heal=domain(VoisinageEffect('restore_body',3,.2,target='self'),strength=1,incursion=1000,stability=1,effect_cost=3)
    b=fight('yaksha',mode='ambush',enemy_field=heal,enemy_body=(m('zhen',heal_preserve=1),m('shi',restore_energy=.1,restore_state=.1)))
    b.units['e0'].body=b.units['e0'].vitality=.5;start(b)
    assert b.units['e0'].vitality==pytest.approx(.5)
    assert len(actions(b))==1 and actions(b)[0]['source']==''
    assert b.units['e0'].current==95 and not b._field_reserved


def test_yaksha_untriggered_reservation_expires_without_payment_or_free_followup():
    b=fight('yaksha',mode='ambush');start(b)
    assert not actions(b) and b.units['player'].current==98
    b.finish_round(player_mp=1,enemy_mp=1)
    assert not b._field_reserved and any('额度过期' in text for text in b.frame.events)


def test_yaksha_real_death_rewards_once_but_suppression_is_not_a_kill():
    b=fight('yaksha',current=50);b.units['e0'].vitality=.15;start(b)
    assert b.units['e0'].death_observed and b.units['player'].current==55
    assert b.units['player'].field_memory['hunt'] is None
    old=b.units['player'].current;b._body_death('e0');b._drain_body_events()
    assert b.units['player'].current==old
    suppression=domain(VoisinageEffect('suppress',3,1),effect_cost=3)
    c=fight('yaksha',current=50,own_field=suppression)
    c._field_memory('player')['hunt']='e0';start(c)
    assert c.units['e0'].suppressed and c.units['player'].current==45


def test_gandharva_cleanses_state_deficit_without_fabricating_hp_healing():
    b=fight('gandharva',level=2,state=.6,body=.5);start(b)
    assert b.units['player'].vitality==pytest.approx(.8) and b.units['player'].body==.5


def test_gandharva_hears_an_enemys_actual_self_heal_and_rupture_uses_own_power():
    heal=domain(VoisinageEffect('restore_body',3,.2,target='self'),strength=1,stability=1,effect_cost=3)
    b=fight('gandharva',mode='rupture',enemy_field=heal);b.units['e0'].body=.5
    start(b);assert b.units['player'].field_memory['echo']['kind']=='restore_body'
    b.units['e0'].current=1
    start(b,2)
    assert b.units['e0'].body<.7 and not b.units['player'].field_memory['echo']
    assert any('断弦' in text for text in b.frame.events)


def test_gandharva_reflects_one_control_with_a_deadline_and_never_copies_attack_qualification():
    b=fight('gandharva',level=4,mode='echo')
    b._field_memory('player')['echo']=dict(kind='restrict',restriction='artifact',source='e0')
    start(b)
    assert 'artifact' in b.units['e0'].timed_controls
    assert not b.units['player'].field_memory['echo'] and b.units['player'].current==95
    assert b.units['e0'].timed_controls['artifact']['expires']==2


def test_mahoraga_spends_real_imprints_on_one_short_control_and_cannot_extend_it_with_extras():
    b=fight('mahoraga',level=4,mode='artifact')
    b._field_memory('player')['marks']['e0']=dict(count=2,expires=5)
    start(b)
    assert set(b.units['e0'].timed_controls)=={'artifact'}
    assert b.units['player'].field_memory['marks']['e0']['count']==0
    deadline=b.units['e0'].timed_controls['artifact']['expires']
    b.units['player'].current=2;start(b,2);b.finish_round(player_mp=1,enemy_mp=1)
    assert deadline==2 and not b.units['e0'].timed_controls


def test_mahoraga_closes_domain_only_after_unlock_and_only_for_a_finite_lease():
    b=fight('mahoraga',mode='voisinage')
    b._field_memory('player')['marks']['e0']=dict(count=2,expires=5);start(b)
    assert 'voisinage' in b.units['e0'].restrictions and b.units['e0'].active_voisinage is None
    assert set(b.units['e0'].restrictions)=={'voisinage'}


def test_melody_completes_three_actual_tunes_then_uses_one_paid_group_cast():
    b=fight('kinnara',mode='cycle',body=.7,state=.7,count=2);b.units['player'].field_strain=.3
    for n in (1,2,3):start(b,n)
    assert b.units['player'].field_memory['chorus']==1
    assert b.units['player'].body==.7
    start(b,4);assert not actions(b)  # Empty repair curve is skipped, not healed.
    before=[b.units[k].vitality for k in ('e0','e1')]
    start(b,5)
    assert len(actions(b))==1 and b.units['player'].field_memory['chorus']==0
    assert all(b.units[k].vitality<old for k,old in zip(('e0','e1'),before))


def test_melody_paid_shift_and_idle_skip_have_different_costs_and_never_fake_chorus():
    b=fight('kinnara',mode='shift');start(b)
    assert b.units['player'].current==pytest.approx(98-3-12)
    assert b.units['player'].field_memory['notes']==2
    c=fight('kinnara',level=2,mode='cycle');start(c)
    assert c.units['player'].current==98 and not actions(c)
    assert c.units['player'].field_memory['notes']==0 and c.units['player'].field_memory['melody']==1


def test_garuda_converts_damage_to_real_strain_then_breaks_and_spends_next_base_action_on_pursuit():
    b=fight('garuda',enemy_body=(m('guard',state_guard=.95),))
    start(b);assert b.units['e0'].body<1 and b.units['e0'].field_strain>.05
    start(b,2);assert b.units['e0'].field_strain>=.25
    start(b,3);assert 'voisinage' in b.units['e0'].timed_controls
    assert b.units['player'].field_memory['breaks']['e0']==4
    start(b,4)
    assert len(actions(b))==1 and not b.units['player'].field_memory['breaks']
    assert any('摧巢' in text for text in b.frame.events)


def test_asura_blood_is_real_hp_and_six_arms_does_not_pay_again_or_create_a_loop():
    b=fight('asura',mode='blood',extra=(m('shou',critical=2),m('xiang',critical_extra=1,free=1)),
        enemy_body=(m('shi',restore_energy=.01,restore_state=.01),),enemy_current=50)
    start(b)
    assert len(actions(b))==3 and sum(bool(a['source']) for a in actions(b))==2
    assert b.units['player'].body==pytest.approx(.955) and b.units['player'].current==95
    assert b.units['e0'].current==50
    assert sum('六臂' in text and '取得一份' in text for text in b.frame.events)==1
    assert all(len(t.chain)==len(set(t.chain)) for t in b._body_round.allowances['player'])


def test_asura_aoe_pays_an_unwaivable_body_cost_once_for_the_whole_cast():
    b=fight('asura',mode='annihilate',count=2);start(b)
    assert b.units['player'].body==pytest.approx(1-.09-.045)
    assert all(b.units[k].body<1 for k in ('e0','e1'))
    assert len([e for e in b._light_trace if e.get('action')=='annihilate'])==1


def test_asura_cannot_self_sacrifice_to_death_and_uses_mana_when_blood_is_unaffordable():
    b=fight('asura',mode='blood',body=.03);start(b)
    assert b.units['player'].body==.03 and b.units['player'].current==95
    c=fight('asura',mode='blood',body=.03,current=2);start(c)
    assert c.units['player'].body==.03 and not actions(c)


def test_real_hp_damage_still_breaks_fields_and_is_heard_under_complete_state_guard():
    b=fight('garuda',enemy_body=(m('guard',state_guard=1),))
    start(b)
    assert b.units['e0'].vitality==1 and b.units['e0'].body<1
    assert b.units['e0'].field_strain>.05
    own=domain(VoisinageEffect('restore_spirit',3,.2,target='self'),stability=200,restore_threshold=.85)
    enemy=domain(VoisinageEffect('strike',3,.2),strength=1000,stability=200)
    c=fight('gandharva',extra=(m('guard',state_guard=1),),own_field=own,enemy_field=enemy)
    start(c)
    assert c.units['player'].vitality==1 and c.units['player'].body<1
    assert c._field_memory('player')['echo']['kind']=='strike'


def test_tian_ordinary_charge_recognizes_real_hp_hits_even_if_state_loss_is_zero():
    own=domain(VoisinageEffect('restore_body',3,.2,target='self'),stability=200,effect_cost=3)
    enemy=domain(VoisinageEffect('seal',999,.1),stability=200,effect_cost=3)
    b=fight('deva',level=2,body=.8,state=.8,extra=(m('zhen',heal_preserve=1),),
        enemy_body=(m('guard',state_guard=1),),own_field=own,enemy_field=enemy)
    start(b);b.ordinary_damage(.1,0)
    assert b.units['e0'].vitality==1 and b.units['e0'].body==pytest.approx(1-.1*.46-.06*.46)
    assert b._field_memory('player')['charge']==pytest.approx(.07)

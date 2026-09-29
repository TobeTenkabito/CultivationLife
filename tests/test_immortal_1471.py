"""Minor release behavior across pure phases, saved choices and game actions."""
import random
from dataclasses import replace
from unittest.mock import patch

import pytest

from test_immortal_cultivation import prepared
from test_domain_combat import voisinage, capability, begin
from cultivation_life.system.combat.contracts import Combatant, CombatCapabilities
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat_system import BattleUnit, PlayerCombatSystem
from cultivation_life.system.immortal_aperture import energy_state, investment_multiplier
from cultivation_life.system.teleport_system import public_teleport
from cultivation_life.system.combat_plan import effective_plan
from cultivation_life.rules import public_player


def battle(*, enemy_rank=89, enemy_caps=None, energy=800, owner_rank=101, objective='kill'):
    b=VoisinageBattle([
        Combatant('player','仙人','player',1,capability(current=energy),cultivation_rank=owner_rank),
        Combatant('enemy','对手','enemy',10**8,enemy_caps or CombatCapabilities(),cultivation_rank=enemy_rank),
    ])
    b.set_objectives(objective,'kill')
    return b


@pytest.mark.parametrize('objective',['kill','capture','repel'])
@pytest.mark.parametrize('enemy_rank',[0,89,100])
def test_true_cultivation_crush_takes_two_rounds_and_respects_purpose(objective,enemy_rank):
    b=battle(objective=objective,enemy_rank=enemy_rank)
    first=begin(b)
    assert b.verdict() is None and b.units['enemy'].vitality==1
    assert b.units['enemy'].escape_locked and first.stat_factors['enemy']=={'sense':0,'mobility':0}
    second=begin(b,2)
    assert b.verdict()=='victory' and second.morale_loss['enemy']>0
    assert b.units['player'].current==560
    assert (b.units['enemy'].vitality==0) == (objective=='kill')
    assert b.units['enemy'].suppressed == (objective!='kill')


def test_insufficient_second_round_energy_cannot_fake_terminal():
    b=battle(energy=180)
    begin(b);begin(b,2)
    assert b.verdict() is None and not b.units['enemy'].escape_locked


def test_domain_owner_or_equal_cultivation_does_not_use_crush_shortcut():
    definition=voisinage(effect='seal',effect_power=.01,authority=1)
    caster=capability(definition=definition)
    for enemy_caps,rank in [(CombatCapabilities(),101),(capability(stance='off'),89)]:
        b=VoisinageBattle([Combatant('player','甲','player',100,caster,cultivation_rank=101),
                           Combatant('enemy','乙','enemy',100,enemy_caps,cultivation_rank=rank)])
        begin(b);begin(b,2)
        assert b.verdict() is None
        assert b.units['enemy'].pressure>0 and b.units['enemy'].vitality<1


def test_pressure_break_and_reentry_retains_debuff_but_resets_streak():
    definition=voisinage(effect='seal',effect_power=.01,authority=1,opening_cost=1,upkeep_cost=1,effect_cost=1)
    b=VoisinageBattle([Combatant('player','甲','player',100,capability(definition=definition,current=5)),
                      Combatant('enemy','乙','enemy',100)])
    begin(b);begin(b,2)
    pressure=b.units['enemy'].pressure
    f=begin(b,3)
    assert f.ordinary and f.stat_factors['enemy']['sense']==pytest.approx(1-pressure)
    assert not b.units['enemy'].escape_locked
    b.units['player'].current=20
    f=begin(b,4)
    assert not f.morale_loss and b.units['enemy'].pressure==pressure


def test_capacity_stage_growth_and_sealed_cultivation_conserve_resources(prepared):
    _,g,_=prepared;p=g.player;p.immortal_aperture['current']=17
    for realm,layer,cap in [(9,1,1000),(9,3,1000),(9,4,2000),(9,6,2000),(9,7,3000),(10,1,4000)]:
        p.realm_index,p.layer=realm,layer
        assert energy_state(p)['capacity']==cap
        assert energy_state(p)['current']==17
        assert investment_multiplier(p)==1+.5*(cap/1000-1)
    p.sealed_cultivation={'realm_index':10,'layer':1};p.realm_index=8;p.layer=1;p.world='spirit'
    assert energy_state(p)['capacity']==60 and p.immortal_aperture['current']==17
    assert public_player(p)['resource_kind']=='mana'
    p.world='celestial';p.realm_index=10
    assert energy_state(p)['capacity']==4000 and energy_state(p)['current']==17
    assert public_player(p)['resource_kind']=='immortal'


def test_expanded_investment_improves_dimensions_and_consumes_extra():
    d=voisinage(max_investment=20,authority=10)
    strengths=[]
    for limit in (20,60):
        c=capability(definition=d,investment=60,investment_limit=limit)
        b=VoisinageBattle([Combatant('player','甲','player',100,c),Combatant('enemy','乙','enemy',100)])
        begin(b);strengths.append(b.report()['fields'][0]['strength'])
        assert b.units['player'].current==800-180-limit
    assert strengths[1]>strengths[0]


def test_manual_plan_persists_auto_ignores_it_and_invalid_values_rejected(prepared):
    e,g,_=prepared
    with pytest.raises(ValueError):e.update_combat_plan(g.id,{'stance':'off'})
    e.update_setting(g.id,'manual_combat_plan',True)
    e.update_combat_plan(g.id,{'stance':'off','investment':300,'burst':'never','transformations':False})
    p=e.store.load(g.id).player
    assert effective_plan(p)['stance']=='off'
    for bad in ({'investment':float('nan')},{'stance':'anything'},{'mp_reserve':2},{'manual':False}):
        with pytest.raises(ValueError):e.update_combat_plan(g.id,bad)
    e.update_setting(g.id,'manual_combat_plan',False)
    p=e.store.load(g.id).player
    assert effective_plan(p)['stance']=='press' and p.combat_plan['stance']=='off'
    e.update_setting(g.id,'manual_combat_plan',True)
    assert effective_plan(e.store.load(g.id).player)['stance']=='off'


def test_player_manual_stance_reaches_battle_boundary(prepared):
    from cultivation_life.engine.combat_capabilities import bind_capabilities
    from cultivation_life.content_registry import WORLD_SYSTEMS
    e,g,d=prepared;g.doctrine_state['player']['active']=d['id'];g.doctrine_state['player']['progress'][d['id']]['level']=4
    g.player.combat_plan={'manual':True,'stance':'off','investment':100}
    binding=bind_capabilities(g,[BattleUnit('player','甲','player',100,9)],{'target_name':'乙','target_realm_index':8,'target_power':100},WORLD_SYSTEMS['transcendent_combat'])
    begin(binding.battle)
    assert not binding.battle.fields


@pytest.mark.parametrize('method',['bribe','assassinate'])
@pytest.mark.parametrize('exposed',[True,False])
def test_teleport_smuggling_uses_existing_wanted_and_does_not_advance_age(prepared,method,exposed):
    e,g,_=prepared;info=public_teleport(g,e.maps);dest=info['destinations'][0]['id']
    age,fame=g.player.age,g.player.fame
    with patch('random.Random.random',return_value=0 if exposed else .99):
        shown=e.teleport_action(g.id,method,dest)
    p=e.store.load(g.id).player
    assert p.age==age and p.location_id==dest and not p.teleport_permissions
    assert (p.fame>fame)==exposed
    if exposed:assert shown['wanted']


def test_two_round_terminal_propagates_to_combat_report(prepared):
    _,g,_=prepared
    b=battle()
    result=PlayerCombatSystem.resolve(g.player,[BattleUnit('player','仙人','player',1,9)],
        {'target_name':'敌','target_power':10**8,'target_realm_index':8},True,random.Random(1),
        current_hp_ratio=1,current_mp_ratio=1,phases=b)
    assert len(result.rounds)==2 and result.outcome=='victory' and result.kill_ready
    assert result.rounds[1]['enemy_morale']<result.rounds[0]['enemy_morale']

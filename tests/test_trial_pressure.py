"""Authored trial pressure changes numbers, never copied body qualifications."""
import copy,json
from unittest.mock import patch
import pytest

from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.system.combat.trial_difficulty import stage,copied_field,validate
from cultivation_life.system.combat.trials import dump_battle,load_battle
from cultivation_life.system.combat.contracts import VoisinageEffect
from scripts.calibrate_upper_breakthroughs import prepare,variants
from test_voisinage_effects import domain


@pytest.mark.parametrize('config',[
 {'12':{}},{'10':{'unknown':1}},{'10':{'enemy_ratios':[1]}},
 {'10':{'enemy_ratios':[1,False]}},{'10':{'enemy_ratios':[1,float('nan')]}},
 {'10':{'enemy_ratios':[1,0]}},{'10':{'field_copy_cap':True}},
 {'10':{'field_copy_cap':14}},{'10':{'field_copy_scale':0}},
 {'10':{'field_copy_scale':1.1}},{'10':{'field_copy_scale':True}},
])
def test_pressure_rejects_invalid_or_ambiguous_authoring(config):
    with pytest.raises(ValueError):stage(config,10,(1.,.8))


def test_no_override_keeps_original_difficulty_and_copying_reference_is_frozen():
    assert stage({},10,(1.,.8))==((1.,.8),8,1.)
    field=domain(VoisinageEffect('strike',3,.1),strength=1000,incursion=1200,stability=900,authority=800)
    assert copied_field(field,1) is field
    reduced=copied_field(field,.65)
    for key in ('strength','incursion','stability','authority'):
        assert getattr(reduced,key)==pytest.approx(getattr(field,key)*.65)
    for key in ('authority_reference','effects','upkeep_cost','opening_cost','extra_target_cost','features','required_level'):
        assert getattr(reduced,key)==getattr(field,key)


@pytest.mark.parametrize('family,realm',[('demonic',10),('demonic',11),('monster',10),('monster',11),('ghost',11)])
def test_authoritative_roster_totals_six_attributes_and_full_body_mirrors_agree(family,realm):
    trial,_=prepare(family,realm,'peak',variants(family)[0],930211)
    battle=load_battle(trial['snapshot']);own=battle.units['player'].unit
    target=trial['target'];total=sum(m['power'] for m in target['members'])
    assert target['target_power']==pytest.approx(total)
    assert battle.totals['enemy']==pytest.approx(total)
    ratio=total/own.power
    for key,value in trial['battle_state']['stats']['player'].items():
        assert trial['battle_state']['stats']['enemy'][key]==pytest.approx(value*ratio)
    for state in battle.units.values():
        caps=state.unit.capabilities
        assert caps.body_mechanisms==own.capabilities.body_mechanisms
        assert caps.divine_lights==own.capabilities.divine_lights
        assert caps.usable_capacity==own.capabilities.usable_capacity
    frozen=json.loads(json.dumps(trial['snapshot']))
    with patch.dict(WORLD_SYSTEMS,upper_voisinages={},asura_manifestation={}):
        assert json.loads(json.dumps(dump_battle(load_battle(frozen))))==frozen


@pytest.mark.parametrize('family',['monster','ghost'])
def test_other_stages_default_to_original_enemy_pressure(family):
    upper=copy.deepcopy(WORLD_SYSTEMS['upper_voisinages']);upper.pop('breakthrough_trials',None)
    with patch.dict(WORLD_SYSTEMS,upper_voisinages=upper):
        trial,_=prepare(family,11,'peak',variants(family)[0],930211)
        battle=load_battle(trial['snapshot'])
        assert battle.totals['enemy']==2*battle.totals['player']


@pytest.mark.parametrize('factor',[0,-1,True,float('inf'),4])
def test_content_validation_rejects_invalid_field_strength(factor):
    systems={'upper_voisinages':{'worlds':{'nether':{'fields':[{'strength_factor':factor}]}}}}
    with pytest.raises(ValueError):validate(systems)

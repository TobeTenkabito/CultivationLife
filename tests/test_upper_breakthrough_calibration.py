"""Sampling fixtures use real body/loadout projections and original trial rules."""
import copy,json
import pytest

from scripts.calibrate_upper_breakthroughs import prepare,sample,variants,world,extend,FAMILIES
from cultivation_life.system.combat.trials import load_battle
from cultivation_life.system import asura


@pytest.mark.parametrize('family',FAMILIES)
@pytest.mark.parametrize('realm',[9,10,11])
def test_prepared_profiles_keep_actual_equipment_body_and_enemy_counts(family,realm):
    trial,meta=prepare(family,realm,'peak',variants(family)[0],930211)
    battle=load_battle(trial['snapshot']);own=battle.units['player'].unit.capabilities
    assert own.artifact_tier==2 and meta['artifact_tier']==2
    assert meta['body']==50 and meta['training']==10
    assert meta['field_rank']=={9:4,10:8,11:13}[realm]
    assert meta['source_layer']==(1 if family=='monster' else 9)
    assert own.current==own.capacity
    expected=(3 if family=='immortal' else 2) if realm==11 else 2 if family=='demonic' and realm==10 else 1
    assert len(battle.units)==expected+1
    if family in {'demonic','monster','ghost'} or realm==11:
        assert trial['battle_state']['stats']['enemy']['might']>0
        for key,state in battle.units.items():
            if key!='player':
                assert state.unit.capabilities.body_mechanisms==own.body_mechanisms
                assert state.unit.capabilities.divine_lights==own.divine_lights
                assert state.unit.capabilities.current==own.current


@pytest.mark.parametrize('family',FAMILIES)
@pytest.mark.parametrize('profile,ratio',[('low_energy',.25),('zero_energy',0)])
def test_low_resources_apply_to_both_actual_ledgers(family,profile,ratio):
    trial,meta=prepare(family,11,profile,variants(family)[0],930211)
    own=load_battle(trial['snapshot']).units['player'].unit.capabilities
    assert own.current==pytest.approx(own.capacity*ratio)
    assert trial['battle_state']['mp_ratio']==ratio
    assert meta['energy_ratio']==ratio


@pytest.mark.parametrize('ordinary,pool',[(0,1),(1,0)])
def test_resource_isolation_does_not_change_the_other_pool(ordinary,pool):
    trial,_=prepare('immortal',11,'ready',0,930211,mp_ratio=ordinary,aperture_ratio=pool)
    own=load_battle(trial['snapshot']).units['player'].unit.capabilities
    assert own.current==pytest.approx(own.capacity*pool)
    assert trial['battle_state']['mp_ratio']==ordinary


@pytest.mark.parametrize('family',['monster','ghost'])
def test_dynamic_catalog_profiles_are_accepted_by_original_blueprint_validation(family):
    for variant in variants(family,'dynamic'):
        trial,meta=prepare(family,11,'peak',variant,930211)
        fields=load_battle(trial['snapshot']).units['player'].unit.capabilities.voisinages
        assert len(fields)==1 and fields[0].id.startswith(('true-form:','soul-form:'))
        assert meta['field_rank']==13


def test_preparation_does_not_mutate_cached_world_and_json_sampling_is_reproducible():
    baseline=copy.deepcopy(world('immortal',930211).to_dict())
    trial,_=prepare('immortal',11,'ready',0,930211)
    assert world('immortal',930211).to_dict()==baseline
    assert sample(trial,6000)==sample(json.loads(json.dumps(trial)),6000)


def test_budget_exhaustion_is_ongoing_and_five_round_survival_is_a_real_win():
    route=next(k for k,v in asura.config()['routes'].items() if v['effect'].startswith('restore'))
    trial,_=prepare('demonic',10,'ready',route,930211)
    result=sample(trial,6000,max_rounds=5)
    assert result['outcome']=='ongoing' and result['rounds']==5
    row={**prepare('demonic',10,'ready',route,930211)[1],**result}
    before=copy.deepcopy(row)
    resumed=extend([row,row],24)
    fresh=sample(trial,6000,24)
    assert all(all(r[k]==value for k,value in fresh.items()) for r in resumed)
    assert row==before
    trial,_=prepare('immortal',9,'ready',0,930211)
    result=sample(trial,6000,max_rounds=5)
    assert result['outcome']=='victory' and result['rounds']==5

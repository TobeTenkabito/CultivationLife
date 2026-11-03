"""Real pressure thresholds, generated rule projection and frozen battle ownership."""
import copy,json,random
from dataclasses import replace
from types import SimpleNamespace
import pytest

from cultivation_life.system import asura
from cultivation_life.system.combat.contracts import VoisinageEffect
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.trials import dump_battle,load_battle
from test_voisinage_effects import actor,caster,domain,begin
from test_asura_manifestation import ready,route


def source(route_id,level=9,**values):
    # The repaired templates remain available as generated powers; fixed
    # eightfold abilities now use their separate discipline descriptors.
    indices=(1,5,9) if route_id=='naga' else (5,9,1)
    powers=[]
    for i,index in enumerate(indices):
        if level<(2,4,7)[i]:continue
        r=copy.deepcopy(asura.config()['semantic_templates'][index])
        r.update(schema_version=3,id=f'base:{i}',source_id=f'asura:power:pressure:{i}');powers.append(r)
    state=dict(route=route_id,level=level,domain_rank=8,domain_name='承压验收',
        branches={route_id:[]},powers=powers)
    state.update(values)
    p=SimpleNamespace(asura_cultivation=state,path='demonic',world='asura',realm_index=10)
    return asura.source(p)


@pytest.mark.parametrize('pressure,power',[(0,.1),(.199999,.1),(.2,.13),(.200001,.13),(.85,.13)])
@pytest.mark.parametrize('owner',['player','npc'])
def test_pressure_authority_changes_real_paid_effect_at_twenty_percent(pressure,power,owner):
    other='enemy' if owner=='player' else 'player'
    s=caster(domain(VoisinageEffect('suppress',3,.1)),semantic_rules=source('naga').semantic_rules)
    b=VoisinageBattle([actor(owner,'player' if owner=='player' else 'enemy',s),
        actor(other,'enemy' if owner=='player' else 'player')])
    b.units[other].pressure=pressure;begin(b)
    assert b.units[other].vitality==pytest.approx(1-power)
    assert b.units[owner].current==95
    assert any('base:0' in event for event in b.frame.events)==(pressure>=.2)


@pytest.mark.parametrize('pressure,defense,dominated',[(0,80,True),(.149999,80,True),(.15,100,False),(.150001,100,False),(.85,100,False)])
def test_pressure_stability_changes_real_directional_contest_at_fifteen_percent(pressure,defense,dominated):
    own=caster(domain(VoisinageEffect('seal',999,.1)),semantic_rules=source('kinnara',2).semantic_rules)
    enemy=caster(domain(VoisinageEffect('seal',999,.1),incursion=140,stability=1000))
    b=VoisinageBattle([actor('player','player',own),actor('enemy','enemy',enemy)])
    b.units['player'].pressure=pressure;frame=begin(b)
    assert frame.relations['player']['defense_strength']==defense
    assert ('player' in b._dominated)==dominated
    assert b.units['player'].current==98


def legacy(index,key):
    row=copy.deepcopy(asura.config()['semantic_templates'][index])
    row.update(schema_version=3,id=key,source_id=key)
    row['when']['value']*=100
    return row


def test_generated_branches_powers_and_display_are_corrected_without_mutating_saved_records(ready):
    engine,g=ready;route(g.player,'naga',level=9,rank=8);state=g.player.asura_cultivation
    branch=state['branches']['naga'][0]
    branch['rules']=[legacy(1,'asura:naga:0:0'),legacy(5,'asura:naga:0:1')]
    state.update(branch=branch['id'],branch_level=4,
        powers=[legacy(1,'asura:power:0'),legacy(5,'asura:power:1')],locked_power_ids=['asura:power:0'])
    # Existing random magnitudes and branch training are preserved.
    state['powers'][0]['actions'][0]['value']=.27
    original=copy.deepcopy(state);rng=g.rng_state;engine.store.save(g)
    path=engine.store._path(g.id);saved=path.read_bytes()
    projected=asura.source(g.player).semantic_rules
    for r in projected:
        if r['name']=='承压增威':assert r['when']['value']==.2
        if r['name']=='逆势守域':assert r['when']['value']==.15
    power=next(r for r in projected if r['id']=='asura:power:0')
    assert power['actions'][0]['value']==.27
    assert next(r for r in projected if r['id']=='asura:naga:0:0')['actions'][0]['value']==.345
    public=asura.public(g)
    assert all('达到20%' in r['description'] for r in public['powers'] if r['name']=='承压增威')
    assert all('达到15%' in r['description'] for r in public['powers'] if r['name']=='逆势守域')
    assert state==original and g.rng_state==rng and path.read_bytes()==saved


@pytest.mark.parametrize('change',[
 {'name':'other'}, {'trigger':'round_start'},
 {'when':{'fact':'target.pressure','op':'gt','value':20}},
 {'when':{'fact':'self.pressure','op':'ge','value':20}},
 {'when':{'fact':'target.pressure','op':'ge','value':.3}},
])
def test_projection_does_not_reinterpret_unknown_rule_conditions(change):
    row=legacy(1,'asura:power:0');row.update(change)
    assert asura._project_pressure_rule(row)==row


def test_new_random_rules_all_use_fractional_pressure_thresholds():
    templates=asura.config()['semantic_templates']
    assert templates[1]['when']['value']==.2 and templates[5]['when']['value']==.15
    rng=random.Random(211)
    for i in range(80):
        rule=asura.generate_rule(rng,f'probe:{i}',i%len(templates))
        when=rule['when']
        if when['fact'].endswith('.pressure'):assert 0<=when['value']<=1


@pytest.mark.parametrize('frozen',[False,True])
def test_json_resume_keeps_original_frozen_rules_instead_of_reprojecting_growth(frozen):
    rules=(legacy(1,'asura:power:0'),) if frozen else source('naga').semantic_rules
    b=VoisinageBattle([actor('player','player',caster(domain(VoisinageEffect('suppress',3,.1)),semantic_rules=rules)),actor('enemy','enemy')])
    b.units['enemy'].pressure=.85
    restored=load_battle(json.loads(json.dumps(dump_battle(b))))
    begin(restored)
    assert restored.units['enemy'].vitality==pytest.approx(.9 if frozen else .87)

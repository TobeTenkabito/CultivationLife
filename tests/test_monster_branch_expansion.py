"""Five expanded origins: graph, compatibility, real evolution and ascension."""
import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from cultivation_life.content_registry import MONSTER_EVOLUTIONS as NODES, MONSTER_BLOODLINE_SETTINGS, REALMS
from cultivation_life.engine import GameEngine
from cultivation_life.models import Player
from cultivation_life.rules import opportunity_required, qi_level_threshold
from cultivation_life.system import monster_bloodline_system as bloodline
from cultivation_life.system.combat_system import BattleUnit, PlayerCombatSystem

ROOT=Path(__file__).resolve().parents[1]
LEGACY=json.loads((ROOT/'tests/fixtures/monster_evolutions_4152.json').read_text(encoding='utf-8'))
NEW=sorted(set(NODES)-set(LEGACY))
TERMINALS=[key for key in NEW if NODES[key]['realm_index']==8]
FAMILIES={'fox':('MYSTIC','MOON'),'turtle':('MOUNTAIN','TIDE'),'insect':('ARMOR','CICADA'),
          'aquatic':('KOI','WHALE'),'flora':('ANCIENT','FLOWER','THORN')}


def ancestry(key):
    parents=NODES[key]['parents']
    return (ancestry(parents[0]) if parents else [])+[key]


@pytest.fixture(scope='module')
def sandbox(tmp_path_factory):
    engine=GameEngine(ROOT,tmp_path_factory.mktemp('monster-branches'))
    templates={}
    for species in FAMILIES:
        made=engine.create_game('分支验收','supreme_water','monster',seed=4160,
                                start_world='monster_realm',monster_species_id=species)
        templates[species]=engine.store.load(made['id'])
    return engine,templates


def ready(sandbox,key,world='monster_realm'):
    engine,templates=sandbox
    n=NODES[key];g=copy.deepcopy(templates[n['species']]);p=g.player
    p.monster_evolution_id=key;p.monster_evolution_history=ancestry(key)
    p.realm_index=n['realm_index'];p.layer=REALMS[p.realm_index].layers
    p.world=world;p.location_id=engine.maps.default_location(world)
    p.awaiting_major_breakthrough=True;p.opportunity=opportunity_required(p)
    p.monster_adaptations=list(MONSTER_BLOODLINE_SETTINGS['adaptations'])
    p.monster_bloodline_imprints=list(MONSTER_BLOODLINE_SETTINGS['imprints'])
    p.qi_experience['monster']=qi_level_threshold(20)
    engine.store.save(g)
    return g


def test_old_nodes_attributes_and_all_old_edges_survive():
    assert len(NODES)==265 and len(NEW)==65
    for key,prior in LEGACY.items():
        node=NODES[key]
        raw=json.dumps({k:v for k,v in node.items() if k!='parents'},sort_keys=True,ensure_ascii=False).encode()
        assert hashlib.sha256(raw).hexdigest()==prior['sha256'],key
        assert set(prior['parents'])<=set(node['parents']),key
    assert {s:sum(n['species']==s and n['realm_index']<=8 for n in NODES.values()) for s in FAMILIES}=={
        'fox':26,'turtle':26,'insect':26,'aquatic':26,'flora':31}


def test_every_node_reachable_has_adjacent_stable_successor_and_distinct_high_routes():
    for key,n in NODES.items():
        assert all(NODES[p]['realm_index']==n['realm_index']-1 and NODES[p]['species']==n['species'] for p in n['parents'])
        assert NODES[ancestry(key)[0]]['realm_index']==0
        if n['realm_index']<12:
            assert any(key in c['parents'] and not c.get('requirements') and not c['monster_qi_level'] for c in NODES.values()),key
    for species,branches in FAMILIES.items():
        for realm in range(5,9):
            rows=[NODES[f'{species.upper()}_{b}_{realm}'] for b in branches]
            assert len({tuple(n['profile'].values()) for n in rows})==len(rows)
            assert len({tuple(n['traits']) for n in rows})==len(rows)
        for branch in branches:
            for realm in range(6,9):
                n=NODES[f'{species.upper()}_{branch}_{realm}'];prev=f'{species.upper()}_{branch}_{realm-1}'
                assert n['parents']==[prev]
                assert all(n['profile'][k]>=NODES[prev]['profile'][k] for k in n['profile'])


@pytest.mark.parametrize('key',NEW)
def test_every_new_node_executes_real_evolution_once_and_roundtrips(sandbox,key):
    engine,_=sandbox;n=NODES[key];g=ready(sandbox,n['parents'][0]);before=copy.deepcopy(g.player)
    offered=engine.get_game(g.id)['monster_bloodline']['candidates']
    assert next(c for c in offered if c['id']==key)['enabled']
    result=engine.evolve_monster(g.id,key);after=engine.store.load(g.id)
    assert result['monster_bloodline']['current']['id']==key
    assert after.player.realm_index==n['realm_index'] and after.player.opportunity==0
    assert after.player.age==before.age and after.player.world==before.world
    assert after.player.monster_evolution_history==before.monster_evolution_history+[key]
    assert len(after.player.monster_generated_bloodline_traits)==1
    assert len(after.player.monster_acquired_bloodline_traits)==1
    if n['realm_index']>=6:
        assert after.player.lifespan is None  # Existing immortal-lifespan rule.
    else:
        assert after.player.lifespan>before.lifespan
    snapshot=after.to_dict()
    with pytest.raises(ValueError):engine.evolve_monster(g.id,key)
    assert engine.store.load(g.id).to_dict()==snapshot
    restored=engine.get_game(g.id)
    assert restored['monster_bloodline']['current']['profile']==n['profile']
    assert set(t['id'] for t in restored['monster_bloodline']['current']['traits'])>=set(n['traits'])
    assert engine.store.load(g.id).player.monster_evolution_history==after.player.monster_evolution_history


@pytest.mark.parametrize('key',[k for k in NEW if NODES[k].get('requirements')])
def test_new_adaptation_and_qi_gates_reject_atomically(sandbox,key):
    engine,_=sandbox;n=NODES[key];g=ready(sandbox,n['parents'][0])
    required=n['requirements']['value']
    for adaptations,qi in [([],20),([required],3)]:
        g.player.monster_adaptations=adaptations;g.player.qi_experience['monster']=qi_level_threshold(qi)
        engine.store.save(g)
        shown=engine.get_game(g.id)
        assert not next(c for c in shown['monster_bloodline']['candidates'] if c['id']==key)['enabled']
        snapshot=engine.store.load(g.id).to_dict()
        with pytest.raises(ValueError,match='进化条件'):engine.evolve_monster(g.id,key)
        assert engine.store.load(g.id).to_dict()==snapshot


@pytest.mark.parametrize('key',TERMINALS)
@pytest.mark.parametrize('route,world',[('TRUE','monster_realm'),('SELF','phantom_underworld')])
def test_new_mahayana_endpoints_use_existing_ancestral_or_self_ascension(sandbox,key,route,world):
    engine,_=sandbox;g=ready(sandbox,key,world);prefix=NODES[key]['species'].upper()
    target=f'{prefix}_NETHER_{route}_1'
    if route=='TRUE':
        g.player.monster_bloodline_imprints=[];engine.store.save(g)
        with pytest.raises(ValueError,match='进化条件'):engine.evolve_monster(g.id,target)
        g.player.monster_bloodline_imprints=list(MONSTER_BLOODLINE_SETTINGS['imprints']);engine.store.save(g)
        result=engine.evolve_monster(g.id,target)
    else:
        g.player.monster_bloodline_imprints=[];g.player.qi_experience['monster']=0;engine.store.save(g)
        prepared=engine.prepare_custom_lineage(g.id,target)
        assert prepared['monster_bloodline']['custom_lineage_editor']['deeds']['total']==24
        with pytest.raises(ValueError,match='自成血脉'):engine.evolve_monster(g.id,target)
        rules=[dict(phase='round_start',schedule='every',condition='always',target='player',effect='might',value=.03)]
        result=engine.confirm_custom_lineage(g.id,target,'分支新祖',rules)
    assert (result['player']['world'],result['player']['realm_index'])==('nether',9)
    saved=engine.store.load(g.id)
    assert saved.player.monster_evolution_history[-2:]==[key,target]
    assert saved.player.monster_species_id==NODES[key]['species']
    assert any(r.event_id=='SYS_MONSTER_NETHER_ASCENSION' for r in saved.history)


@pytest.mark.parametrize('species',FAMILIES)
def test_legacy_defaults_and_new_state_survive_disabled_dlc(sandbox,species):
    # The old condition-free default remains first; no silent rebasing of births.
    history=bloodline._stable_history_for_realm(species,12)
    assert all(k in LEGACY for k in history)
    engine,_=sandbox;key=f'{species.upper()}_{FAMILIES[species][0]}_5'
    g=ready(sandbox,key);p=Player.from_dict(g.player.to_dict());before=p.to_dict()
    with patch.object(bloodline,'bloodline_content_available',return_value=False):
        assert not bloodline.ensure_monster_bloodline_state(p)
        assert not bloodline.public_monster_bloodline(p)['available']
        active=bloodline.active_bloodline_profile(p)
        assert active['id'] is None and not active['traits']
        assert set(active['stat_multipliers'].values())=={1.0}
        assert p.to_dict()==before
    assert bloodline.public_monster_bloodline(p)['current']['id']==key
    assert p.monster_evolution_history==before['monster_evolution_history']


def test_cross_species_and_wrong_branch_rejected(sandbox):
    engine,_=sandbox;g=ready(sandbox,'FOX_MYSTIC_5')
    engine.get_game(g.id)  # Initialize the isolated fixture's newly selected realm.
    snapshot=engine.store.load(g.id).to_dict()
    for target in ['FOX_MOON_6','INSECT_ARMOR_6']:
        with pytest.raises(ValueError,match='进化支系'):engine.evolve_monster(g.id,target)
        assert engine.store.load(g.id).to_dict()==snapshot


@pytest.mark.parametrize('key',TERMINALS)
def test_branch_profile_reaches_real_combat_without_history_stacking(sandbox,key):
    _,templates=sandbox;n=NODES[key];p=copy.deepcopy(templates[n['species']].player)
    p.realm_index=8;p.technique=None;p.known_techniques=[]
    unit=[BattleUnit('player',p.name,'player',100.0,8,'monster')]
    base=p.monster_evolution_id
    original=PlayerCombatSystem._aggregate_stats(unit,player=p,terrain_tags=[])
    p.monster_evolution_id=key;p.monster_evolution_history=ancestry(key)
    evolved=PlayerCombatSystem._aggregate_stats(unit,player=p,terrain_tags=[])
    for stat,value in n['profile'].items():
        assert evolved[stat]/original[stat]==pytest.approx(value/NODES[base]['profile'][stat])


def test_new_high_profiles_trade_stats_within_old_same_realm_budgets():
    baselines={
        'fox':['FOX_DREAM_EMPEROR','FOX_VOID_NINE_TAIL','FOX_ANCESTRAL_DREAM','FOX_MAHAYANA_HEAVENLY'],
        'turtle':['TURTLE_OCEAN_EMPEROR','TURTLE_WORLD_SHELL','TURTLE_ANCESTRAL_XUANWU','TURTLE_MAHAYANA_WORLD'],
        'insect':['INSECT_MYRIAD_EMPEROR','INSECT_VOID_HIVE','INSECT_ANCESTRAL_MOTHER','INSECT_MAHAYANA_SWARM'],
        'aquatic':['AQUATIC_OCEAN_EMPEROR','AQUATIC_WORLD_KUN','AQUATIC_ANCESTRAL_KUN','AQUATIC_MAHAYANA_KUN'],
        'flora':['FLORA_EVERGREEN_EMPEROR','FLORA_WORLD_CANOPY','FLORA_ANCESTRAL_WORLD_TREE','FLORA_MAHAYANA_ORIGIN_TREE'],
    }
    for key in NEW:
        n=NODES[key]
        if n['realm_index']<5:continue
        baseline=NODES[baselines[n['species']][n['realm_index']-5]]
        assert sum(n['profile'].values())<=sum(baseline['profile'].values())+1e-8
        assert n['lifespan_gain']==baseline['lifespan_gain']
        assert len(n['traits'])==(3 if n['realm_index']==5 else 4)
        assert any(n['profile'][k]<baseline['profile'][k] for k in n['profile'])


@pytest.mark.parametrize('key',[k for k in NEW if NODES[k].get('travel_themes')])
def test_new_water_travel_bonus_uses_real_map_themes_without_moving(sandbox,key):
    engine,templates=sandbox;n=NODES[key];p=copy.deepcopy(templates[n['species']].player)
    p.monster_evolution_id=key
    locations=engine.maps.worlds[p.world]['locations'];themes=set(n['travel_themes'])
    land=[r['id'] for r in locations if not themes.intersection(r.get('themes',[]))]
    water=next(r['id'] for r in locations if themes.intersection(r.get('themes',[])))
    p.location_id=land[0];before=p.to_dict()
    assert engine._monster_travel_multiplier(p,land[1])==1.0
    assert engine._monster_travel_multiplier(p,water)==n['travel_multiplier']
    assert p.to_dict()==before
    p.location_id=water;before=p.to_dict()
    assert engine._monster_travel_multiplier(p,land[0])==n['travel_multiplier']
    assert p.to_dict()==before

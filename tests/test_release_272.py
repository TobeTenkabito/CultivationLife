"""Economic grades never grant upper attack qualification to mortal equipment."""
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import ITEM_CATALOG, MARKET_GOODS
from cultivation_life.economy_content import specification
from cultivation_life.models import Item, Player, SectNpc
from cultivation_life.system.combat.contracts import Combatant, CombatCapabilities, resolve_source
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat_loadout import project_loadout

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module',autouse=True)
def loaded_catalog(tmp_path_factory):
    GameEngine(ROOT,tmp_path_factory.mktemp('force-catalog'))

CASES=[(world,grade,kind) for world,cap in (
    ('human',5),('demon',5),('spirit',8),('true_demon',8),('monster_realm',8),
    ('phantom_underworld',8),('hell',8),('celestial',12),('asura',12),
    ('nether',12),('reincarnation',12))
    for grade in (1,2,5,8,9,12) if grade<=cap
    for kind in ('artifact_attack','artifact_guard')]

def hit(caps):
    battle=VoisinageBattle([
        Combatant('player','持器者','player',1000,caps),
        Combatant('enemy','护体金光目标','enemy',1000,CombatCapabilities(ward_tier=2))])
    battle.begin_round(1,player_condition=1,enemy_condition=1,player_mp=1,enemy_mp=1)
    damage,_=battle.ordinary_damage(.2,0)
    return damage

@pytest.mark.parametrize('world,grade,kind',CASES)
def test_economic_equipment_real_damage_respects_upper_threshold(world,grade,kind):
    item=copy.deepcopy(ITEM_CATALOG[f'econ_{world}_{grade}_{kind}'])
    p=Player('资材边界','none',world=world)
    p.inventory=[item]
    caps=resolve_source(None,{},project_loadout(None,p,player=True))
    assert hit(caps)==pytest.approx(.2 if grade>=9 else 0)
    assert caps.artifact_tier==(2 if grade>=9 else 1)
    # The bug shipped copied grades into saved items; their stale values must
    # not bypass the same rule after a normal serialization roundtrip.
    item.force_tier=grade
    saved=Player.from_dict(p.to_dict())
    before=saved.to_dict()
    caps=resolve_source(None,{},project_loadout(None,saved,player=True))
    assert hit(caps)==pytest.approx(.2 if grade>=9 else 0)
    assert saved.to_dict()==before

def test_every_economic_item_keeps_commercial_grade_separate_from_combat():
    goods={row['content_id']:row for row in MARKET_GOODS if row['kind']=='item' and specification(row['content_id'])}
    assert len(goods)==1666
    for identity,good in goods.items():
        spec=specification(identity)
        item=ITEM_CATALOG[identity]
        assert good['tier']==spec['grade']
        assert item.force_tier in (1,2)
        if spec['raw'] or spec['use']!='artifact':
            assert item.force_tier==1
        if spec['grade']<=8:
            assert item.force_tier==1

@pytest.mark.parametrize('world,grade',[('human',2),('spirit',8),('asura',8),('asura',9),('nether',12),('reincarnation',9)])
def test_npc_main_artifact_obeys_same_damage_gate(world,grade):
    item=ITEM_CATALOG[f'econ_{world}_{grade}_artifact_attack']
    npc=SectNpc('gear-audit','持器者',world,9,1,100,None,combat_artifact_id=item.id)
    caps=resolve_source(None,{},project_loadout(SimpleNamespace(doctrine_state={}),npc))
    assert hit(caps)==pytest.approx(.2 if grade>=9 else 0)

def test_upper_energy_and_explicit_immortal_artifacts_still_work():
    p=Player('攻击资格','none')
    p.inventory=[copy.deepcopy(ITEM_CATALOG['econ_human_2_artifact_attack'])]
    source=project_loadout(None,p,player=True)
    state=dict(conversion=1,capacity=100,current=100,force_tier=2,attack_cost=10)
    assert hit(resolve_source(state,{},source))==pytest.approx(.2)
    assert hit(resolve_source(dict(state,current=0),{},source))==0
    p.inventory=[copy.deepcopy(ITEM_CATALOG['heavenly_river_sword_embryo'])]
    assert hit(resolve_source(None,{},project_loadout(None,p,player=True)))==pytest.approx(.2)
    p.inventory=[Item('local-custom-weapon','显式上界武器',force_tier=2,tags=['equipment'])]
    assert hit(resolve_source(None,{},project_loadout(None,p,player=True)))==pytest.approx(.2)

def test_old_structure_10_inventory_stays_unchanged_during_projection(tmp_path):
    engine=GameEngine(ROOT,tmp_path)
    result=engine.create_game('已购法宝','otherworld','dao',272)
    game=engine.store.load(result['id'])
    item=copy.deepcopy(ITEM_CATALOG['econ_human_2_artifact_attack'])
    item.force_tier=2
    game.player.inventory.append(item)
    engine.store.save(game)
    before=engine.store._path(game.id).read_bytes()
    loaded=engine.store.load(game.id)
    loaded.player.technique=None
    loaded.player.combat_techniques=[]
    caps=resolve_source(None,{},project_loadout(loaded,loaded.player,player=True))
    assert hit(caps)==0
    assert engine.store._path(game.id).read_bytes()==before
    assert next(i for i in loaded.player.inventory if i.id==item.id).force_tier==2

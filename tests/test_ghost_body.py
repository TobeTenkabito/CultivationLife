"""Real ghost cultivation transactions, host ownership and loadout freezing."""
import copy,random
from pathlib import Path
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.system.ghost_body import profile
from cultivation_life.system.ghost_body_training import public,stock
from cultivation_life.system.upper_voisinage_rules import config
from cultivation_life.system.crafting_system import crafting_material_definitions,make_crafting_material_instance
from cultivation_life.system.combat_loadout import project_loadout
from cultivation_life.cultivation_coordinates import validate_immortal_body

ROOT=Path(__file__).resolve().parents[1]


def supply_materials(g,count=80):
    definition=crafting_material_definitions()[config()['worlds']['reincarnation']['material_id']]
    rng=random.Random(17)
    g.player.crafting_materials.extend(make_crafting_material_instance(definition,rng,source='test',origin_world='reincarnation') for _ in range(count))


@pytest.fixture
def ready_ghost(tmp_path):
    e=GameEngine(ROOT,tmp_path/'saves')
    g=e._load(e.create_game('鬼躯验收','supreme_metal','ghost',221,preset_id='reincarnation_upper')['id'])
    g.pending_event=None;g.player.body_training=100;g.player.opportunity=10**12;g.player.next_tribulation_age=None
    g.player.immortal_body={'level':9};supply_materials(g)
    e.store.save(g);e.get_game(g.id)
    return e,e._load(g.id)


def test_body_unlock_and_independent_training_spend_exactly_once(ready_ghost):
    e,g=ready_ghost;before=public(g);op=g.player.opportunity;count=len(stock(g.player));age=g.player.age;rng=g.rng_state
    e.upper_voisinage_action(g.id,'ghost_body_train',None,expected_level=9)
    saved=e._load(g.id)
    assert saved.player.immortal_body['level']==10 and len(profile(saved.player,player=True))==1
    assert saved.player.opportunity==op-before['body_cost']['opportunity']
    assert len(stock(saved.player))==count-10
    e.upper_voisinage_action(g.id,'ghost_body_refine','wuxiang',expected_level=0)
    trained=e._load(g.id);assert profile(trained.player,player=True)[0].effects['recovery_bonus']==pytest.approx(.03)
    assert trained.player.age==age and trained.rng_state==rng
    e.get_game(g.id);path=e.store._path(g.id);blob=path.read_bytes()
    with pytest.raises(ValueError,match='等级已变化'):e.upper_voisinage_action(g.id,'ghost_body_refine','wuxiang',expected_level=0)
    assert path.read_bytes()==blob


def test_missing_materials_and_unlocked_requirements_are_atomic(ready_ghost):
    e,g=ready_ghost;g.player.crafting_materials.clear();e.store.save(g);e.get_game(g.id)
    path=e.store._path(g.id);blob=path.read_bytes()
    with pytest.raises(ValueError,match='材料不足'):e.upper_voisinage_action(g.id,'ghost_body_train',None,expected_level=9)
    with pytest.raises(ValueError,match='尚未解锁'):e.upper_voisinage_action(g.id,'ghost_body_refine','yinguo',expected_level=0)
    assert path.read_bytes()==blob


def test_all_five_values_freeze_in_loadout_and_do_not_stack_with_lights(ready_ghost):
    e,g=ready_ghost;p=g.player;p.immortal_body={'level':50,'ghost_training':{'yinguo':4,'zhaoye':3},'divine_lights':{'qian':10}}
    caps=project_loadout(g,p,player=True)
    assert not caps.divine_lights and len(caps.body_mechanisms)==5
    assert next(r for r in caps.body_mechanisms if r.id=='yinguo').effects['karma_threshold']==pytest.approx(.4)
    p.immortal_body['ghost_training']['yinguo']=10
    assert next(r for r in caps.body_mechanisms if r.id=='yinguo').level==4
    assert profile(dict(path='ghost',immortal_body_level=20))[-1].id=='zhaoye'
    assert profile(dict(path='ghost',immortal_body_level=0))==()


def test_destroyed_body_and_possession_do_not_borrow_original_ghost_body(ready_ghost):
    e,g=ready_ghost;p=g.player;p.immortal_body={'level':50,'ghost_training':{'yinguo':10}}
    p.spirit_state={'mode':'wandering','body_intact':False}
    assert not profile(p,player=True)
    p.ghost_host_body=dict(id='host',path='ghost',immortal_body_level=10)
    p.ghost_core_state={}
    assert [r.id for r in profile(p,player=True)]==['wuxiang']


def test_real_npc_ghost_uses_independent_body_and_all_five_mechanisms():
    from cultivation_life.models import SectNpc
    from cultivation_life.content_registry import WORLD_SYSTEMS
    from cultivation_life.system.combat.npc_battle import resolve_npc_engagement
    a=SectNpc('ghost-body-owner','鬼躯修士','',9,1,100,None,path='ghost',world='reincarnation',body_training=100,immortal_body_level=50)
    b=SectNpc('ordinary-owner','凡体修士','',12,9,100,None,immortal_body_level=0)
    report=resolve_npc_engagement([(a,100)],[(b,100)],WORLD_SYSTEMS['transcendent_combat'],random.Random(19),max_rounds=2)
    raw=report.rounds[0]['voisinage']['body_mechanisms']['raw']
    assert len(raw[a.id])==5 and not raw[b.id]
    assert raw[a.id]['yinguo']['effects']['karma_threshold']==pytest.approx(.25)


@pytest.mark.parametrize('training',[{'nope':1},{'yinguo':11},{'zhaoye':True},{'wuxiang':float('nan')}])
def test_bad_persisted_training_is_rejected(training):
    with pytest.raises(ValueError):validate_immortal_body({'level':50,'ghost_training':training})

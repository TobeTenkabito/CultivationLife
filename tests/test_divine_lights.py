"""Five-light ordering, real action costs, targets, snapshots and cultivation."""
import copy
import random
from dataclasses import replace

import pytest

from cultivation_life.system.combat.contracts import CombatCapabilities, VoisinageEffect
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.trials import dump_battle,load_battle
from cultivation_life.system.divine_lights import definitions,profile,recipe
from cultivation_life.rules import add_item
from cultivation_life.save_schema import SAVE_SCHEMA_VERSION,migrate_document
from cultivation_life.cultivation_coordinates import body_rank,describe
from test_voisinage_effects import actor,caster,domain
from test_immortal_cultivation import prepared


def start(b,n=1,first='player',rng=None):
    return b.begin_round(n,player_condition=1,enemy_condition=1,player_mp=1,enemy_mp=1,
                         first_side=first,rng=rng or random.Random(7))


def healer(lights):
    d=domain(VoisinageEffect('restore_body',3,.2,target='self'),stability=200)
    return VoisinageBattle([actor('player','player',caster(d,divine_lights=lights),integrity=.6,body_integrity=.6),
                           actor('enemy','enemy',caster(domain(VoisinageEffect('seal',3,.1),stability=200)))])


def test_healing_spends_ordinary_action_before_zhen():
    b=healer({});frame=start(b)
    assert not frame.ordinary_player and frame.ordinary_enemy
    assert b.units['player'].current==95 and b.units['player'].body==pytest.approx(.8)
    assert any('占用本回合一次普通出手' in s for s in frame.events)


def test_zhen_preserves_ordinary_action_but_still_pays_and_boosts_healing():
    b=healer({'kun':1,'zhen':1,'zhen_heal':.5});frame=start(b)
    assert frame.ordinary_player and frame.ordinary_enemy
    assert b.units['player'].current==95
    assert b.units['player'].body==pytest.approx(.9)
    assert any('治疗比例提高50%' in s for s in frame.events)


def test_kan_adds_one_paid_field_action():
    d=domain(VoisinageEffect('strike',3,.2))
    b=VoisinageBattle([actor('player','player',caster(d,divine_lights={'kan':1})),actor('enemy','enemy')])
    frame=start(b)
    assert b.units['enemy'].vitality==pytest.approx(.6)
    assert b.units['player'].current==92
    assert sum('施行杀伤' in s for s in frame.events)==2
    assert any('行动次数由1增至2' in s for s in frame.events)


def test_li_uses_field_authority_once_and_never_damages_body():
    d=domain(VoisinageEffect('seal',1,0),authority=100)
    b=VoisinageBattle([actor('player','player',caster(d,divine_lights={'li':.04,'kan':1})),actor('enemy','enemy')])
    frame=start(b)
    assert b.units['enemy'].vitality==pytest.approx(.96)
    assert b.units['enemy'].body==1
    assert sum('离上朱光随' in s for s in frame.events)==1
    assert any('4.00%' in s and '4.0点' in s for s in frame.events)


@pytest.mark.parametrize('first',('player','enemy'))
def test_first_successful_qian_prevents_later_qian_and_disables_kun(first):
    lights={'kun':1,'qian':1}
    b=VoisinageBattle([actor(s,s,CombatCapabilities(divine_lights=lights)) for s in ('player','enemy')])
    frame=start(b,first=first);other='enemy' if first=='player' else 'player'
    assert b._light_muted=={other:first}
    assert b.ward_tier(first)==2 and b.ward_tier(other)==1
    assert sum(e['kind']=='qian' for e in b._light_trace)==1
    assert any('抢先静默' in s for s in frame.events)
    start(b,n=2,first=other)
    assert b._light_muted=={first:other} and b.ward_tier(other)==2


def test_failed_first_qian_allows_later_counter():
    class Dice:
        def __init__(self):self.values=iter((.9,.1));self.calls=0
        def random(self):self.calls+=1;return next(self.values)
    dice=Dice();lights={'qian':.5}
    b=VoisinageBattle([actor(s,s,CombatCapabilities(divine_lights=lights)) for s in ('player','enemy')])
    start(b,rng=dice)
    assert b._light_muted=={'player':'enemy'} and dice.calls==2


def test_qian_silences_field_healing_and_all_other_lights_for_round():
    b=healer({'kun':1,'zhen':1,'zhen_heal':.5,'kan':1,'li':.1,'qian':1})
    b.units['enemy'].unit=replace(b.units['enemy'].unit,capabilities=replace(b.units['enemy'].unit.capabilities,divine_lights={'qian':1}))
    start(b,first='enemy')
    assert b.units['player'].body==.6 and b.units['player'].current==98
    assert not any(e['kind'] in {'kan','li','zhen_heal'} and e['owner']=='player' for e in b._light_trace)


def test_kun_resists_control_without_canceling_qualified_field_damage():
    d=domain(VoisinageEffect('strike',3,.2))
    b=VoisinageBattle([actor('player','player',CombatCapabilities(divine_lights={'kun':1,'kun_resist':1})),
                           actor('enemy','enemy',caster(d))])
    frame=start(b)
    assert frame.ordinary_player and not b.units['player'].escape_locked
    assert b.units['player'].vitality==pytest.approx(.8)
    assert frame.relations['player']['relation']=='resisted'


def test_kun_immunity_is_damage_only_and_visible_in_text():
    b=VoisinageBattle([actor('player','player',CombatCapabilities(divine_lights={'kun':1})),actor('enemy','enemy')])
    start(b);b.ordinary_damage(.1,.1)
    assert b.units['player'].vitality==1 and b.units['enemy'].vitality==pytest.approx(.9)
    assert b.ward_tier('player',damage=False)==1
    assert any('坤元缃光免疫' in s for s in b.frame.events)


def test_continuation_keeps_light_profiles_and_rng_results():
    b=healer({'kun':1,'zhen':1,'kan':.4,'qian':.3})
    rng=random.Random(941);start(b,rng=rng)
    restored=load_battle(dump_battle(b));other=random.Random();other.setstate(rng.getstate())
    start(b,2,rng=rng);start(restored,2,rng=other)
    assert b.updates()==restored.updates() and b.report()==restored.report()
    assert rng.getstate()==other.getstate()


@pytest.mark.parametrize('level,expected',[(0,'大乘后期'),(1,'真仙初期'),(10,'真仙后期'),(20,'金仙中期'),(30,'太乙中期'),(40,'大罗初期'),(50,'大罗后期')])
def test_fifty_layer_body_coordinates(level,expected):
    assert describe(body_rank(100,level))['name']==expected


def test_independent_training_pays_once_and_rejects_stale_level(prepared):
    e,g,_=prepared;g.player.immortal_body['level']=50
    row=definitions()[0]
    for key,count in recipe(row,0).items():add_item(g.player,key,count*2)
    e.store.save(g)
    before=copy.deepcopy(g.rng_state);age=g.player.age
    shown=e.immortal_action(g.id,'train_divine_light',axis='kun',expected_level=0)
    saved=e.store.load(g.id)
    assert saved.player.immortal_body['divine_lights']=={'kun':1}
    assert saved.rng_state==before and saved.player.age==age
    assert profile(saved.player,player=True)[0]['kun_resist']==.03
    path=e.store._path(g.id);snapshot=path.read_bytes()
    with pytest.raises(ValueError,match='等级已变化'):e.immortal_action(g.id,'train_divine_light',axis='kun',expected_level=0)
    assert path.read_bytes()==snapshot
    assert len(shown['golden_light']['lights'])==5


@pytest.mark.parametrize('version',range(1,12))
def test_old_save_structures_rejected_without_conversion(version):
    raw={'version':version,'id':'preserved','player':{'immortal_body':{'level':100}}};before=copy.deepcopy(raw)
    assert SAVE_SCHEMA_VERSION==12
    with pytest.raises(ValueError,match='结构 12'):migrate_document(raw)
    assert raw==before


def test_three_corpses_copy_exact_light_values_and_keep_snapshot():
    from scripts.calibrate_immortal_trials import fixture
    from cultivation_life.engine.progression.immortal_trials import initialize
    g=fixture('three_corpses',field_rank=8,doctrine_level=8)
    g.player.immortal_body={'level':50,'divine_lights':dict(kun=7,zhen=6,kan=5,li=4,qian=3)}
    b=initialize(g,g.active_trial);own=b.units['player'].unit.capabilities
    for key,state in b.units.items():
        assert state.unit.capabilities.divine_lights==own.divine_lights
        assert state.unit.capabilities.divine_light_levels==own.divine_light_levels
        if key in {'enemy-0','enemy-1'}:assert not state.unit.capabilities.voisinages
    saved=dump_battle(b);g.player.immortal_body['divine_lights']['qian']=10
    resumed=load_battle(saved)
    assert resumed.units['enemy-2'].unit.capabilities.divine_light_levels['qian']==3
    assert resumed.units['enemy-2'].unit.capabilities.divine_lights['qian']==pytest.approx(.0575)


@pytest.mark.parametrize('world,path', [('nether','monster'),('reincarnation','ghost')])
def test_other_path_mirrors_copy_light_values_and_freeze_them(prepared,world,path):
    e,g,_=prepared;p=g.player
    # Fixture placement only; production trial entry uses its existing eligibility gate.
    p.world=world;p.path=path;p.realm_index=11;p.layer=9
    p.location_id=e.maps.normalize_location(world,None)
    p.immortal_body={'level':50,'divine_lights':dict(kun=7,zhen=6,kan=5,li=4,qian=3)}
    if path=='monster':p.immortal_body['monster']={'level':50,'training':{'shenhun':3}}
    if path=='ghost':p.immortal_body['ghost_training']={'yinguo':3}
    e._start_upper_trial(g,path+'_upper')
    battle=load_battle(g.active_trial['snapshot']);own=battle.units['player'].unit.capabilities
    assert len(own.body_mechanisms)==5 and not own.divine_light_levels
    enemies=[s.unit.capabilities for s in battle.units.values() if s.unit.side=='enemy']
    assert len(enemies)==2
    for cap in enemies:
        assert cap.divine_lights==own.divine_lights
        assert cap.divine_light_levels==own.divine_light_levels
        assert cap.body_mechanisms==own.body_mechanisms
    p.immortal_body['divine_lights']['qian']=10
    resumed=load_battle(g.active_trial['snapshot'])
    if path=='monster':
        p.immortal_body['monster']['training']['shenhun']=10
        assert all(next(r for r in s.unit.capabilities.body_mechanisms if r.id=='shenhun').effects['exchange_threshold']==pytest.approx(.43) for s in resumed.units.values())
    else:
        p.immortal_body['ghost_training']['yinguo']=10
        assert all(next(r for r in s.unit.capabilities.body_mechanisms if r.id=='yinguo').effects['karma_threshold']==pytest.approx(.395) for s in resumed.units.values())


def test_real_npc_combat_uses_body_lights_and_same_text():
    from cultivation_life.models import SectNpc
    from cultivation_life.content_registry import WORLD_SYSTEMS
    from cultivation_life.system.combat.npc_battle import resolve_npc_engagement
    a=SectNpc('divine-npc','练体者','',9,1,100,None,body_training=100,immortal_body_level=50)
    b=SectNpc('ordinary-npc','凡体者','',12,9,100,None,body_training=100,immortal_body_level=0)
    report=resolve_npc_engagement([(a,100)],[(b,100)],WORLD_SYSTEMS['transcendent_combat'],random.Random(51),max_rounds=2)
    assert report is not None
    text='\n'.join(s for row in report.rounds for s in row['events'])
    assert '练体者的五色神光' in text and '乾古素光' in text
    assert '凡体者的五色神光' not in text


def test_npc_default_body_initializes_once_and_preserves_explicit_growth():
    from cultivation_life.models import SectNpc
    from cultivation_life.system.npc_cultivation import ensure_npc
    npc=SectNpc('late-body-default','后期修士','',12,9,100,None)
    ensure_npc(npc);original=npc.immortal_body_level
    assert 46<=original<=50
    npc.realm_index=10;npc.layer=1;ensure_npc(npc)
    assert npc.immortal_body_level==original
    npc.immortal_body_level=9;ensure_npc(npc)
    assert profile(npc)[0]=={}


def test_kan_does_not_create_free_actions_when_resources_run_out():
    d=domain(VoisinageEffect('strike',3,.2))
    b=VoisinageBattle([actor('player','player',caster(d,capacity=5,current=5,divine_lights={'kan':1})),actor('enemy','enemy')])
    start(b)
    assert b.units['enemy'].vitality==pytest.approx(.8)
    assert b.units['player'].current==0


def test_fifty_is_hard_cultivation_and_custom_start_limit(prepared):
    e,g,_=prepared;g.player.immortal_body.update(level=50,manuals=['jade_marrows'],active_manual='jade_marrows')
    e.store.save(g);e.get_game(g.id);path=e.store._path(g.id);before=path.read_bytes()
    with pytest.raises(ValueError,match='上限'):e.immortal_action(g.id,'train_body')
    assert path.read_bytes()==before
    with pytest.raises(ValueError):e.create_game('超上限','supreme_metal','dao',351,custom_start=dict(world='celestial',realm_index=9,immortal_body_level=51))
    from cultivation_life.models import Player
    data=g.player.to_dict();data['immortal_body']['level']=51
    with pytest.raises(ValueError,match='0至50'):Player.from_dict(data)


def test_light_training_survives_real_sealed_descent_and_return(prepared):
    from cultivation_life.system.world_transition_system import finish_world_transition
    from cultivation_life.runtime import decode_rng,encode_rng
    e,g,_=prepared;g.player.immortal_body.update(level=50,divine_lights=dict(kun=9,zhen=8,kan=7,li=6,qian=5))
    original=copy.deepcopy(g.player.immortal_body);expected=profile(g.player,player=True)
    rng=decode_rng(g.seed,g.rng_state)
    for destination,mode in [('spirit','sealed_descent'),('celestial','sealed_return')]:
        before=g.to_dict();plan=e._plan_world_transition(g,destination,mode)
        assert g.to_dict()==before
        e._apply_world_transition(g,plan);finish_world_transition(g,rng,e._refresh_world_market)
        assert g.player.immortal_body==original and profile(g.player,player=True)==expected
        if destination=='spirit':assert not any(r['can_train'] for r in e._public_golden_light(g)['lights'])
    g.rng_state=encode_rng(rng);e.store.save(g)
    assert e.store.load(g.id).player.immortal_body==original


@pytest.mark.parametrize('scope',('journey','guixu','heavens'))
def test_training_busy_scopes_reject_without_material_or_rng_changes(prepared,scope):
    from cultivation_life.system.immortal_body_system import _temper_golden_light
    e,g,_=prepared;g.player.immortal_body['level']=50;add_item(g.player,'great_sun_divine_light',100)
    if scope=='journey':g.map_journey={'destination':'test'}
    elif scope=='guixu':g.guixu_state['player_session']={'id':'test-session'}
    else:g.heavens_state={'runtime':{'tasks':[{'status':'paused','id':'test'}]}}
    before=copy.deepcopy(g)
    with pytest.raises(ValueError):_temper_golden_light(e._dependencies.cultivation.body,g,'kun',0)
    assert g==before

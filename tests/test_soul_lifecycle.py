"""Body/soul ownership, command persistence and fatal boundary regressions."""
import copy
import random
from pathlib import Path
from unittest.mock import patch
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.models import Player, SectNpc, Item
from cultivation_life.rules import add_item, combat_power, opportunity_multiplier
from cultivation_life.soul_rules import body_cap, soul_cap, wandering
from cultivation_life.system import soul_lifecycle as life
from cultivation_life.system.second_nascent import power, unit
from cultivation_life.system.soul_actions import conversion_quote
from cultivation_life.system.possession_system import can_possess
from cultivation_life.save_schema import migrate_document

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def ready(tmp_path):
    e=GameEngine(ROOT,tmp_path/'saves')
    g=e._load(e.create_game('身魂验收','supreme_metal','dao',320,preset_id='core')['id'])
    g.pending_event=None
    p=g.player
    p.realm_index=4;p.layer=2;p.lifespan=10000;p.divine_sense_rank=20
    p.body_training=12;p.body_energy=body_cap(p);p.soul_energy=soul_cap(p)
    add_item(p,'spirit_stone',100000)
    e.store.save(g)
    return e,g

def act(e,g,action,**kw):
    return e.soul_action(g.id,action,dict(revision=e.store.load(g.id).player.nascent_state.get('revision',0),**kw))


@pytest.mark.parametrize('path',['dao','demonic','ghost','monster','confucian','buddhist'])
@pytest.mark.parametrize('rank',[3,4])
def test_leave_secret_auto_unlock_and_authoritative_rank(ready,path,rank):
    from cultivation_life.system.soul_presentation import public
    e,g=ready;p=g.player;p.path=path;p.realm_index=rank
    e.store.save(g)
    # Normalize the deliberately edited fixture before checking command atomicity.
    e.get_game(g.id);g=e.store.load(g.id);p=g.player
    assert public(g)['leave_unlocked'] is (rank>=4)
    assert public(g)['can_leave'] is (rank>=4)
    before=e.store._path(g.id).read_bytes()
    if rank<4:
        with pytest.raises(ValueError,match='元婴期'):
            act(e,g,'leave')
        assert e.store._path(g.id).read_bytes()==before
    else:
        act(e,g,'leave');after=e.store.load(g.id)
        assert wandering(after.player)
        assert after.player.soul_energy==p.soul_energy-10
        assert after.player.age==p.age
        assert after.player.inventory==p.inventory
        assert not public(after)['can_leave']
        act(e,after,'return');after=e.store.load(g.id)
        assert not wandering(after.player)
        assert after.player.soul_energy==p.soul_energy-10

def prisoner(g):
    n=SectNpc('second-test','清澜','散修',4,2,50,10000,spirit_root='supreme_metal')
    g.world_npcs[n.id]=n
    g.player.prisoners.append(g.detain_person(n.to_dict()))
    return n

def ready_second(e,g):
    n=prisoner(g);g.player.nascent_state['known']=['second_nascent'];e.store.save(g)
    # Exercise the real elapsed-time entry, suppress only unrelated event rolls.
    for _ in range(3):
        act(e,g,'refine',id=n.id)
        g=e.store.load(g.id);g.pending_event=None;e.store.save(g)
    return e.store.load(g.id)

def test_energy_caps_and_rest(ready):
    e,g=ready;p=g.player
    assert body_cap(p)==340 and soul_cap(p)==600
    p.body_energy=p.soul_energy=1
    life.restore(p)
    assert p.body_energy==69 and p.soul_energy==121
    life.leave_body(g,destroyed=True);life.restore(p)
    assert p.body_energy==0 and p.body_training==0

def test_collapse_mortal_and_nascent(ready):
    e,g=ready;p=g.player;p.body_energy=0
    life.resolve_energy(g,random.Random(1),e._die)
    assert p.alive and wandering(p) and p.body_training==0
    p.spirit_state={};p.realm_index=3
    life.resolve_energy(g,random.Random(1),e._die)
    assert not p.alive

def test_leave_return_stale_and_no_teleport(ready):
    e,g=ready
    view=act(e,g,'leave');assert view['soul']['mode']=='神游'
    before=e.store.load(g.id).to_dict()
    with pytest.raises(ValueError,match='过期'):e.soul_action(g.id,'return',dict(revision=0))
    assert e.store.load(g.id).to_dict()==before
    p=e.store.load(g.id);p.player.spirit_state['address']['location']='elsewhere';e.store.save(p)
    with pytest.raises(ValueError,match='地点'):act(e,g,'return')
    p.player.spirit_state['address']['location']=before['player']['location_id'];e.store.save(p)
    assert act(e,g,'return')['soul']['mode']=='普通'

def test_timeout_and_ghost_exemption_without_dlc(ready):
    e,g=ready;life.leave_body(g);deadline=g.player.spirit_state['deadline']
    g.player.age=deadline
    assert life.tick(g,random.Random(1),e._die)
    g.player.age+=1;life.tick(g,random.Random(1),e._die)
    assert not g.player.alive
    g.player.alive=True;g.player.path='ghost';g.player.age+=100
    with patch('cultivation_life.content_registry.EXTENSION_REPORT',[]):
        assert life.tick(g,random.Random(1),e._die)

@pytest.mark.parametrize('outcome',[0,1,2])
def test_soul_depletion_once_per_episode(ready,outcome):
    e,g=ready;p=g.player;p.soul_energy=0
    rng=random.Random(2)
    with patch.object(rng,'randrange',return_value=outcome) as roll:
        life.resolve_energy(g,rng,e._die);life.resolve_energy(g,rng,e._die)
        assert roll.call_count==1
    assert p.nascent_state.get('stagnant') if outcome==0 else p.nascent_state.get('crisis') if outcome==1 else (p.realm_index,p.layer)==(3,8)

def test_refine_original_npc_equipment_and_rescue(ready):
    e,g=ready;g=ready_second(e,g)
    assert not g.player.prisoners
    npc=life.second_person(g)
    assert npc and npc.id=='second-test' and npc.roster_state=='held'
    assert unit(g).id==npc.id and power(g)>0
    add_item(g.player,Item('soul-sword','验收剑',combat_bonus=500,tags=['artifact']))
    e.store.save(g);act(e,g,'equip',id='soul-sword');g=e.store.load(g.id)
    assert not any(i.id=='soul-sword' for i in g.player.inventory)
    assert g.player.nascent_state['second']['equipment'][0]['id']=='soul-sword'
    e._die(g,'普通斗法死亡','SYS_COMBAT')
    assert g.player.alive and wandering(g.player) and g.player.realm_index==4
    assert g.player.nascent_state.get('second') and g.inactive_npcs[npc.id].alive
    e._die(g,'神游中再次遭遇致命攻击','SYS_COMBAT')
    assert g.player.alive and wandering(g.player)
    assert not g.player.nascent_state.get('second') and not g.inactive_npcs[npc.id].alive
    assert sum(i.quantity for i in g.player.inventory if i.id=='soul-sword')==1

@pytest.mark.parametrize('event',['EVT_STORY_FATAL','SYS_TRIAL_FAILED','SYS_HEAVENLY_DEMON_TRIBULATION_FAILED'])
def test_second_cannot_save_story_or_tribulation(ready,event):
    e,g=ready;n=prisoner(g)
    n.custody['kind']='second_nascent';g.player.prisoners=[]
    g.player.nascent_state['second']=dict(id=n.id,due=100,interval=10,integrity=100.,auto=True,equipment=[])
    e._die(g,'必死结局',event)
    assert not g.player.alive

def test_assimilation_is_once_and_persistent(ready):
    e,g=ready;g=ready_second(e,g);row=g.player.nascent_state['second']
    g.player.age=row['due'];before=g.player.soul_energy
    life.tick(g,random.Random(2),e._die);after=g.player.soul_energy
    assert after==before-15
    e.store.save(g);g=e.store.load(g.id)
    life.tick(g,random.Random(2),e._die)
    assert g.player.soul_energy==after

def test_possession_requires_wandering_and_lower_realm(ready):
    e,g=ready;n=prisoner(g)
    assert not can_possess(g.player,n.to_dict())[0]
    life.leave_body(g)
    assert can_possess(g.player,n.to_dict())[0]
    n.realm_index=5
    assert not can_possess(g.player,n.to_dict())[0]

def test_old_schema_rejected_without_mutating():
    old={'version':10,'id':'untouched'};before=copy.deepcopy(old)
    with pytest.raises(ValueError,match='结构 11'):migrate_document(old)
    assert old==before


def test_conversion_real_command_cost_and_shortfall(ready):
    from cultivation_life.models import Technique
    from cultivation_life.rules import qi_level_threshold, qi_levels
    e,g=ready;p=g.player
    p.nascent_state['known']=['path_ghost']
    p.known_techniques.append(Technique(id='soul-test-ghost',name='阴魂经',path='ghost'))
    p.qi_experience['yin']=qi_level_threshold(4)
    expected=conversion_quote(p,'ghost')
    life.leave_body(g,destroyed=True);e.store.save(g)
    act(e,g,'convert',id='ghost');p=e.store.load(g.id).player
    assert p.path=='ghost' and (p.realm_index,p.layer)==(expected['rank'],expected['layer'])
    assert qi_levels(p)['yin']==0 and wandering(p)
    assert p.realm_index<4
    with pytest.raises(ValueError):conversion_quote(p,'monster')


def test_stagnation_blocks_real_training_and_breakthrough(ready):
    e,g=ready;p=g.player;p.nascent_state['stagnant']=True
    p.opportunity=10**9;p.awaiting_minor_breakthrough=True;e.store.save(g)
    before=(p.realm_index,p.layer)
    e._resolve_breakthroughs(g,random.Random(1))
    assert (p.realm_index,p.layer)==before
    with pytest.raises(ValueError):e.breakthrough(g.id)
    assert opportunity_multiplier(p)==0


def test_npc_body_escape_penalty_and_deadline(ready):
    from cultivation_life.system.npc_soul import escape_body,settle
    from cultivation_life.system.npc_system import npc_combat_power
    from cultivation_life.combat_benchmarks import expected_combat_power
    e,g=ready;n=prisoner(g);n.custody=None;n.roster_state='active'
    base=npc_combat_power(n,expected_combat_power,1)
    assert escape_body(n,g.player.age)
    assert npc_combat_power(n,expected_combat_power,1)==pytest.approx(base*.35,abs=.1)
    assert settle(n,n.spirit_state['deadline'])
    assert not settle(n,n.spirit_state['deadline']+1)


def test_unpaid_second_rebels_and_cannot_save_own_killer(ready):
    e,g=ready;g=ready_second(e,g)
    g.player.nascent_state['second']['auto']=False
    g.player.nascent_state['second']['control']=40
    g.player.age=g.player.nascent_state['second']['due']
    rng=random.Random(1)
    with patch.object(rng,'random',return_value=0.):
        assert not life.tick(g,rng,e._die)
    assert not g.player.alive and 'second' not in g.player.nascent_state


def test_explicit_story_combat_cannot_use_soul_escape(ready):
    e,g=ready
    e._die(g,'剧情强敌','SYS_COMBAT',death_cause='story')
    assert not g.player.alive


def test_second_loadout_uses_original_npc_levels(ready):
    from cultivation_life.system.combat_adapter import persistent_owner
    from cultivation_life.system.combat_loadout import project_loadout
    e,g=ready;g=ready_second(e,g);npc=life.second_person(g)
    book=g.player.known_techniques[0];book.level=5;e.store.save(g)
    act(e,g,'technique',id=book.id,slot='main');g=e.store.load(g.id);npc=life.second_person(g)
    assert persistent_owner(g,npc.id) is npc and npc.main_technique_level==5
    assert project_loadout(g,npc).technique_tier>=1


def test_soul_rank_loss_updates_restorable_rank(ready):
    e,g=ready;p=g.player
    p.cultivation_suppression=dict(realm_index=6,layer=9,opportunity=500)
    p.realm_index,p.layer=3,1;p.soul_energy=0
    rng=random.Random(1)
    with patch.object(rng,'randrange',return_value=2):life.resolve_energy(g,rng,e._die)
    assert p.cultivation_suppression['layer']==6 and p.cultivation_suppression['opportunity']==0
    assert (p.realm_index,p.layer)==(3,1)


def test_bodyless_npc_is_not_a_possession_body(ready):
    e,g=ready;n=prisoner(g);life.leave_body(g)
    n.spirit_state=dict(mode='wandering',body_intact=False,entered=0,deadline=1,address={})
    assert not can_possess(g.player,n.to_dict())[0]

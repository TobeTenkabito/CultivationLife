"""Monster body plans, actual reactions, ownership, payments and saved battles."""
import copy,random
from dataclasses import replace
from pathlib import Path
import pytest

from cultivation_life.engine import GameEngine
from cultivation_life import content_registry as registry
from cultivation_life.rules import add_item,has_item
from cultivation_life.system.combat.body_mechanisms import BodyMechanism
from cultivation_life.system.combat.contracts import CombatCapabilities,VoisinageEffect
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.trials import dump_battle,load_battle
from cultivation_life.system.monster_body import profile,config
from test_voisinage_effects import actor,caster,domain
from test_body_round_wuyun import start,m

ROOT=Path(__file__).resolve().parents[1]


def encounter(*,evade=1,reaction=True,choice=1,release=0,enemy_body=(),own_field=True):
    rows=[m('nigu',evade=evade)]
    if reaction:rows.append(BodyMechanism('liezang','烈脏',dict(retaliate_heal=1,retaliate_suppress=1,retaliate_seal=1,retaliate_power=.1,retaliate_choice=choice),requires=('nigu',)))
    if release:rows.append(m('feixue',release_cost=release))
    weak=domain(VoisinageEffect('seal',999,.1),strength=1,stability=1)
    strong=domain(VoisinageEffect('strike',3,.2),strength=1000,stability=1000)
    own=caster(weak,body_mechanisms=tuple(rows)) if own_field else CombatCapabilities(body_mechanisms=tuple(rows))
    return VoisinageBattle([actor('player','player',own,integrity=.7,body_integrity=.7),
        actor('enemy','enemy',caster(strong,body_mechanisms=enemy_body))])


def test_xuanfu_mortal_immunity_and_immortal_state_guard_preserve_physical_injury():
    caps=CombatCapabilities(artifact_tier=2,ward_tier=2,body_mechanisms=(m('xuanfu',ward=2,state_guard=.5),))
    b=VoisinageBattle([actor('player','player',caps),actor('enemy','enemy',CombatCapabilities(artifact_tier=2))])
    start(b);b.ordinary_damage(.2,.2)
    assert b.units['player'].vitality==pytest.approx(.9)
    assert b.units['player'].body==pytest.approx(1-.2*.46) and b.frame.primary_loss==pytest.approx(.2)
    assert b.primary_ordinary_body_loss==pytest.approx(.2*.46)
    enemy=replace(b.units['enemy'].unit,capabilities=CombatCapabilities())
    mortal=VoisinageBattle([actor('player','player',caps),enemy]);start(mortal);mortal.ordinary_damage(.2,.2)
    assert mortal.units['player'].vitality==1


def test_xuanfu_field_strike_keeps_original_body_damage():
    attacker=caster(domain(VoisinageEffect('strike',3,.2)))
    defender=CombatCapabilities(body_mechanisms=(m('xuanfu',ward=2,state_guard=.5),))
    b=VoisinageBattle([actor('player','player',attacker),actor('enemy','enemy',defender)])
    start(b);assert b.units['enemy'].vitality==pytest.approx(.9)
    assert b.units['enemy'].body==pytest.approx(1-.2*.46)


def test_actual_evade_unlocks_one_free_heal_even_under_domination_and_counts_for_shi():
    b=encounter(enemy_body=(m('shi',restore_state=.01,restore_energy=.01),));start(b)
    assert b.units['player'].vitality==pytest.approx(.8) and b.units['player'].body==pytest.approx(.8)
    assert b.units['player'].current==98 and b.units['enemy'].current==96
    actions=[r for r in b._light_trace if r['kind']=='body_action']
    assert len(actions)==2 and actions[-1]['free'] and actions[-1]['cost']==0
    assert [r for r in b._light_trace if r['kind']=='counter_restore'][0]['count']==1


@pytest.mark.parametrize('choice,kind',[(4,'suppress'),(5,'seal')])
def test_liezang_chooses_one_hostile_effect_against_the_actual_attacker(choice,kind):
    b=encounter(choice=choice);start(b)
    assert b.units['player'].vitality==.7 and b.units['player'].body==.7
    if kind=='suppress':assert b.units['enemy'].vitality==pytest.approx(.9)
    else:assert b.units['enemy'].seal_progress==pytest.approx(.1)
    own=[r for r in b._light_trace if r['kind']=='body_action' and r['owner']=='player']
    assert len(own)==1 and own[0]['cost']==0


def test_reaction_can_trigger_other_actors_reaction_without_owner_reentry():
    other=(m('nigu',evade=1),BodyMechanism('liezang','烈脏',dict(retaliate_heal=1,retaliate_power=.1),requires=('nigu',)))
    b=encounter(choice=4,enemy_body=other);start(b)
    assert b.units['enemy'].vitality==1
    assert len([e for e in b._light_trace if e['kind']=='reaction_ready'])==2
    assert all(len(t.chain)==len(set(t.chain)) for rows in b._body_round.allowances.values() for t in rows)


def test_sibling_evades_each_award_a_reaction_without_shared_round_truncation():
    b=encounter();p=b.units['player'];p.vitality=p.body=.01
    enemy=b.units['enemy'];enemy.unit=replace(enemy.unit,capabilities=replace(enemy.unit.capabilities,body_mechanisms=(m('many',extra=8),)))
    start(b)
    assert len([e for e in b._light_trace if e['kind']=='field_evade' and e['success']])==9
    assert len([e for e in b._light_trace if e['kind']=='body_action' and e['owner']=='player'])==9
    assert len(b._body_round.allowances['player'])==10 and p.current==98


def test_evade_requires_an_actual_maintained_field():
    b=encounter(own_field=False);start(b)
    assert b.units['player'].vitality==pytest.approx(.5)
    assert not any(r['kind']=='field_evade' for r in b._light_trace)


def test_evade_randomness_only_samples_actual_incoming_segments():
    class Dice:
        calls=0
        def random(self):
            self.calls+=1
            if self.calls>1:raise AssertionError('unused evade roll')
            return .1
    dice=Dice();b=encounter(evade=.5);start(b,rng=dice)
    assert dice.calls==1 and b.units['player'].vitality==pytest.approx(.8)


def test_feixue_spends_once_releases_domination_and_does_not_rerun_contest():
    b=encounter(evade=0,reaction=False,release=.1);frame=start(b)
    assert b.units['player'].current==88 and 'player' not in b._dominated
    assert frame.relations['player']['relation']=='released' and frame.ordinary_player
    assert b.units['player'].vitality==.7
    assert len([e for e in b._light_trace if e['kind']=='domination_release'])==1


def test_insufficient_feixue_does_not_partially_pay_or_clear_control():
    b=encounter(evade=0,reaction=False,release=1);start(b)
    assert b.units['player'].current==98 and b._dominated['player']=='enemy'
    assert not next(r for r in b._light_trace if r['kind']=='domination_release')['success']


def test_shenhun_swaps_percentages_using_usable_capacity_once_across_save_reload():
    mine=CombatCapabilities(capacity=100,current=10,usable_capacity=50,body_mechanisms=(m('shenhun',exchange_threshold=.4),))
    other=CombatCapabilities(capacity=1000,current=800)
    b=VoisinageBattle([actor('player','player',mine),actor('enemy','enemy',other)]);start(b)
    assert b.units['player'].current==40 and b.units['enemy'].current==200 and b.units['player'].exchange_used
    restored=load_battle(dump_battle(b));restored.units['player'].current=5;restored.units['enemy'].current=900
    start(restored,2)
    assert restored.units['player'].current==5 and restored.units['enemy'].current==900


@pytest.mark.parametrize('mine,theirs',[(40,80),(20,10),(20,20)])
def test_shenhun_requires_both_strict_inequalities(mine,theirs):
    b=VoisinageBattle([actor('player','player',CombatCapabilities(capacity=100,current=mine,body_mechanisms=(m('shenhun',exchange_threshold=.4),))),
        actor('enemy','enemy',CombatCapabilities(capacity=100,current=theirs))]);start(b)
    assert not b.units['player'].exchange_used


def test_qian_keeps_raw_monster_plans_but_blocks_exchange_evade_and_release():
    b=encounter(release=.1,enemy_body=(m('qian',silence=1),))
    p=b.units['player'];p.current=20
    p.unit=replace(p.unit,capabilities=replace(p.unit.capabilities,body_mechanisms=(*p.unit.capabilities.body_mechanisms,m('shenhun',exchange_threshold=.4))))
    start(b,first='enemy')
    assert not p.exchange_used and p.current==18 and 'player' in b._light_muted
    assert b._body_round.records['player']['shenhun']['triggered']
    assert not any(e['kind']=='field_evade' for e in b._light_trace)


@pytest.fixture
def ready_monster(tmp_path):
    e=GameEngine(ROOT,tmp_path/'saves')
    g=e._load(e.create_game('五蜕验收','supreme_metal','monster',111,preset_id='nether_upper',monster_species_id='serpent')['id'])
    g.pending_event=None;g.player.body_training=100;g.player.opportunity=10**12;g.player.next_tribulation_age=None
    for row in config()['mechanisms']:
        for key in row['recipe']:add_item(g.player,key,10000)
    e.store.save(g);e.get_game(g.id);return e,e.store.load(g.id)


def test_actual_body_training_unlocks_at_ten_and_real_materials_pay_once(ready_monster):
    e,g=ready_monster;g.player.immortal_body['monster']={'level':9};e.store.save(g)
    before=e.get_game(g.id);bill=before['upper_voisinages']['monster_body']['body_cost']
    e.upper_voisinage_action(g.id,'monster_body_train',None,expected_level=9)
    after=e.store.load(g.id);assert after.player.immortal_body['monster']['level']==10
    assert len(profile(after.player,player=True))==1 and after.player.opportunity==g.player.opportunity-bill['opportunity']
    assert after.rng_state==g.rng_state and after.player.age==g.player.age
    e.get_game(g.id);path=e.store._path(g.id);snapshot=path.read_bytes()
    with pytest.raises(ValueError,match='等级已变化'):e.upper_voisinage_action(g.id,'monster_body_train',None,expected_level=9)
    assert path.read_bytes()==snapshot


def test_liezang_training_unlocks_options_and_freezes_choice_in_combat_capabilities(ready_monster):
    e,g=ready_monster;g.player.immortal_body['monster']={'level':50,'training':{'liezang':4}};e.store.save(g)
    with pytest.raises(ValueError,match='尚未解锁'):e.upper_voisinage_action(g.id,'monster_body_select','seal')
    e.upper_voisinage_action(g.id,'monster_body_refine','liezang',expected_level=4)
    e.upper_voisinage_action(g.id,'monster_body_select','seal');p=e.store.load(g.id).player
    assert next(r for r in profile(p,player=True) if r.id=='liezang').effects['retaliate_choice']==5
    from cultivation_life.system.combat_loadout import project_loadout
    frozen=project_loadout(g,p,player=True).body_mechanisms
    p.immortal_body['monster']['reaction']='heal'
    assert next(r for r in frozen if r.id=='liezang').effects['retaliate_choice']==5


def test_missing_materials_do_not_partially_spend_or_advance(ready_monster):
    e,g=ready_monster;g.player.immortal_body['monster']={'level':50};g.player.inventory.clear();e.store.save(g)
    e.get_game(g.id);path=e.store._path(g.id);before=path.read_bytes()
    with pytest.raises(ValueError,match='材料不足'):e.upper_voisinage_action(g.id,'monster_body_refine','xuanfu',expected_level=0)
    assert path.read_bytes()==before


def test_five_monster_materials_only_have_nether_natural_supply():
    keys={key for r in config()['mechanisms'] for key in r['recipe']};assert len(keys)==5
    for key in keys:
        rows=[r for r in registry.MARKET_GOODS if r['content_id']==key]
        assert {r['world'] for r in rows}=={'nether'} and {r['tier'] for r in rows}=={9,10,11,12}


def test_real_npc_uses_only_its_own_monster_body_coordinate():
    from cultivation_life.models import SectNpc
    from cultivation_life.system.combat.npc_battle import resolve_npc_engagement
    npc=SectNpc('body-owner','五蜕修士','',9,1,100,None,path='monster',world='nether',body_training=100,immortal_body_level=50)
    other=SectNpc('other-owner','普通修士','',12,9,100,None,immortal_body_level=0)
    report=resolve_npc_engagement([(npc,100)],[(other,100)],registry.WORLD_SYSTEMS['transcendent_combat'],random.Random(19),max_rounds=2)
    assert report is not None
    raw=report.rounds[0]['voisinage']['body_mechanisms']['raw']
    assert len(raw[npc.id])==5 and not raw[other.id]
    assert raw[npc.id]['nigu']['level']==10


def test_possessed_host_qualification_does_not_borrow_original_body(ready_monster):
    from cultivation_life.system.immortal_cultivation import body_intrinsic_bonus
    _,g=ready_monster;p=g.player;p.immortal_body['monster']={'level':50,'training':{'nigu':9}}
    before=copy.deepcopy(p.immortal_body);p.ghost_core_state={};p.ghost_host_body={'path':'monster','immortal_body_level':0}
    assert not profile(p,player=True) and body_intrinsic_bonus(p,'hp')==0
    p.ghost_host_body['immortal_body_level']=20
    rows=profile(p,player=True);assert len(rows)==2 and rows[-1].level==4
    assert p.immortal_body==before


def test_destroyed_original_body_loses_five_changes_without_rewriting_other_records(ready_monster):
    from cultivation_life.system.soul_lifecycle import leave_body
    _,g=ready_monster;p=g.player;p.immortal_body.update(monster={'level':50},divine_lights={'kun':2})
    leave_body(g,destroyed=True)
    assert 'monster' not in p.immortal_body and p.immortal_body['divine_lights']=={'kun':2}
    assert not profile(p,player=True)


def test_canonical_descent_and_return_preserve_body_and_carried_materials(ready_monster):
    from cultivation_life.runtime import decode_rng
    from cultivation_life.system.world_transition_system import finish_world_transition
    e,g=ready_monster;p=g.player;p.immortal_body['monster']={'level':50,'training':{'nigu':3}}
    original=copy.deepcopy(p.immortal_body);key=config()['body_material'];amount=next(i.quantity for i in p.inventory if i.id==key)
    route=next(r for r in registry.WORLD_SYSTEMS['world_transition_routes'] if r.get('generic_cross_world') and r['source']=='nether')
    rng=decode_rng(g.seed,g.rng_state)
    for destination,mode in [(route['destination'],'sealed_descent'),('nether','sealed_return')]:
        plan=e._plan_world_transition(g,destination,mode);e._apply_world_transition(g,plan);finish_world_transition(g,rng,e._refresh_world_market)
        assert p.immortal_body==original and has_item(p,key,amount) and not has_item(p,key,amount+1)


def test_monster_material_art_and_disabled_package_access():
    import hashlib
    from PIL import Image
    from cultivation_life.visual_assets import public_catalog,extension_asset
    from cultivation_life.errors import NotFoundError
    enabled=public_catalog(ROOT,registry.EXTENSION_REPORT);disabled=public_catalog(ROOT,[])
    for row in config()['mechanisms']:
        for key in row['recipe']:
            assert key in enabled['items'] and key not in disabled['items']
            entry=enabled['assets']['material.'+key+'.portrait']
            path=extension_asset(ROOT,ROOT,registry.EXTENSION_REPORT,entry['file'])
            assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
            with Image.open(path) as image:assert image.size==(128,128) and set(image.getchannel('A').getdata())<={0,255}
            with pytest.raises(NotFoundError):extension_asset(ROOT,ROOT,[],entry['file'])

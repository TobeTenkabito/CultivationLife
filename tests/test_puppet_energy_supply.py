"""One actual payment per puppet attack; finite, replaceable energy modules."""
import copy
import pytest
from test_npc_development import game
from cultivation_life.rules import add_item
from cultivation_life.system import puppet_energy as energy
from cultivation_life.system.combat_plan import effective_plan, validate_plan
from cultivation_life.system.npc_development import service, presentation
from cultivation_life.system.combat.contracts import CombatCapabilities, Combatant
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.trials import dump_battle, load_battle


def battle(*, high=True, grade=1, charge=100, supply=True, mana=20, yuan=20, count=1):
    units=[Combatant('player','主人','player',100,CombatCapabilities(
        capacity=100,current=yuan,resource_tier=2,mana_capacity=100)),
        Combatant('enemy-0','敌人','enemy',100,CombatCapabilities())]
    units += [Combatant(f'puppet-{i}','傀儡','player',100,CombatCapabilities(
        force_tier=2 if high else 1,operating_tier=grade,operating_energy=charge,
        operating_cost=5,attack_resource_owner='player',sponsored_attack_cost=10,allow_sponsor=supply)) for i in range(count)]
    b=VoisinageBattle(units)
    b.begin_round(1,player_condition=1,enemy_condition=1,player_mp=mana/100,enemy_mp=1)
    return b


@pytest.mark.parametrize('high,grade,charge,supply,mana,yuan,tier,left,mp_left,yuan_left',[
    (False,1,100,True,20,20,1,95,20,20),
    (True,2,100,True,20,20,2,95,20,20),
    (True,2,100,False,20,20,2,95,20,20),
    (True,1,100,True,20,20,2,100,20,10),
    (True,1,100,False,20,20,1,95,20,20),
    (True,1,100,True,20,9,1,95,20,9),
    (True,2,4,True,20,20,2,4,20,10),
    (True,2,4,False,20,20,0,4,20,20),
    (True,2,4,True,20,9,1,4,15,9),
    (True,2,4,True,4,9,0,4,4,9),
    (False,1,0,True,20,20,1,0,15,20),
    (False,1,0,False,20,20,0,0,20,20),
    (False,2,100,True,20,20,1,95,20,20),
])
def test_single_attack_funding(high,grade,charge,supply,mana,yuan,tier,left,mp_left,yuan_left):
    b=battle(high=high,grade=grade,charge=charge,supply=supply,mana=mana,yuan=yuan)
    s=b.units['puppet-0'];before=dump_battle(b)
    assert b.attack_tier(s,pay=False)==tier
    assert dump_battle(b)==before
    assert b.attack_tier(s,pay=True)==tier
    assert s.operating_energy==left
    assert b.units['player'].mana_current==mp_left
    assert b.units['player'].current==yuan_left


def test_shared_mp_budget_and_snapshot_preserve_real_remainders():
    b=battle(high=False,charge=3,mana=7,count=2)
    b.ordinary_damage(.1,0)
    assert b.units['player'].mana_current==pytest.approx(2)
    assert b.units['player'].supply_mp_spent==5
    assert all(b.units[f'puppet-{i}'].operating_energy==3 for i in range(2))
    snap=dump_battle(b);restored=load_battle(snap)
    assert restored.units['player'].mana_current==pytest.approx(2)
    assert restored.units['player'].supply_mp_spent==5
    assert not restored._available('puppet-0')
    snap['states']['player']['mana_current']=101
    with pytest.raises(ValueError,match='mana'):load_battle(snap)


@pytest.mark.parametrize('restriction',['supply','dead','suppressed'])
def test_unavailable_sponsor_cannot_pay(restriction):
    b=battle(charge=0);owner=b.units['player']
    if restriction=='supply':owner.controls['supply']='enemy-0'
    elif restriction=='dead':owner.vitality=0
    else:owner.suppressed=True
    assert b.attack_tier(b.units['puppet-0'],pay=True)==0
    assert owner.current==owner.mana_current==20


def asset_game(game):
    game.player.world='celestial'
    asset=dict(id='asset',name='守卫',type='mechanical',realm_index=9,layer=1,
        body_training=100,immortal_body_level=0,divine_sense_rank=101,combat_power=500,
        alive=True,durability=72,operating_energy=65,energy_source_id='npc_training_puppet_energy_rank_7')
    game.player.puppets=[asset]
    add_item(game.player,'npc_training_puppet_energy_3',2)
    return asset


def test_replace_and_restore_keeps_used_durability_and_original_inventory(game):
    asset=asset_game(game);before=copy.deepcopy(game.to_dict())
    presentation.public(game);energy.replacements(game,asset)
    assert game.to_dict()==before
    service.charge(game,'puppet','asset','bag:npc_training_puppet_energy_3')
    assert asset['operating_energy']==100 and energy.force_tier(asset)==2
    assert asset['energy_spares'][0]['durability']==65
    assert asset['durability']==72
    asset['operating_energy']=35
    spare=asset['energy_spares'][0]['id']
    service.charge(game,'puppet','asset','spare:'+spare)
    assert asset['operating_energy']==65 and energy.force_tier(asset)==1
    assert [s['durability'] for s in asset['energy_spares']]==[35]
    assert sum(i.quantity for i in game.player.inventory if i.id=='npc_training_puppet_energy_3')==1
    assert game.player.age==before['player']['age'] and game.rng_state==before['rng_state']
    snapshot=copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError):service.charge(game,'puppet','asset','spare:'+spare)
    assert game.to_dict()==snapshot


@pytest.mark.parametrize('failure',['unknown','world','dead','busy','full'])
def test_replacement_rejections_are_atomic(game,failure):
    asset=asset_game(game);key='bag:npc_training_puppet_energy_3'
    if failure=='unknown':key='bag:spirit_stone'
    if failure=='world':game.player.world='human'
    if failure=='dead':asset['alive']=False
    if failure=='busy':game.pending_event={'id':'pending'}
    if failure=='full':asset.update(operating_energy=100,energy_source_id='npc_training_puppet_energy_3')
    snapshot=copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError):service.charge(game,'puppet','asset',key)
    assert game.to_dict()==snapshot


def test_grade_requires_a_real_equipped_source(game):
    from cultivation_life.puppet_content import definitions
    assert energy.force_tier({'realm_index':12,'operating_energy':100})==1
    source=next(r for r in definitions().values() if r['slot']=='energy' and r['tier']>=9)
    assert energy.force_tier({'components':[dict(id=source['id'],slot='energy')]})==2
    assert energy.force_tier({'energy_source_id':None,'components':[dict(id=source['id'],slot='energy')]})==1
    asset=asset_game(game);add_item(game.player,source['id'],1)
    service.charge(game,'puppet','asset','bag:'+source['id'])
    assert energy.force_tier(asset)==2


def test_supply_setting_is_independent_of_manual_mode(game):
    assert effective_plan(game.player)['puppet_supply']
    for manual in (True,False):
        game.player.combat_plan=dict(manual=manual,puppet_supply=False)
        assert not effective_plan(game.player)['puppet_supply']
    assert validate_plan({'puppet_supply':False})=={'puppet_supply':False}
    with pytest.raises(ValueError):validate_plan({'puppet_supply':'false'})


@pytest.mark.parametrize('high,grade,charge,supply,yuan,expected_yuan,expected_charge,mp_cost',[
    (True,3,100,True,35,25,95,0),
    (True,1,100,True,35,5,100,0),
    (True,1,100,False,35,25,100,0),
    (True,3,0,False,35,25,0,0),
    (False,1,0,True,0,0,0,10),
    (True,3,0,True,0,0,0,10),
])
def test_real_battle_payments_and_save_reload(tmp_path,high,grade,charge,supply,yuan,expected_yuan,expected_charge,mp_cost):
    import random
    from pathlib import Path
    from cultivation_life.engine import GameEngine
    from cultivation_life.rules import combat_power,max_hp,max_mp
    engine=GameEngine(Path(__file__).resolve().parents[1],tmp_path/'saves')
    g=engine.store.load(engine.create_game('供能验收','supreme_metal','dao',811,
        custom_start=dict(world='celestial',realm_index=9,layer=1))['id'])
    g.pending_event=None;p=g.player
    p.immortal_power_converted=True;p.immortal_conversion_stage=5
    p.immortal_aperture=dict(version=1,capacity=1000,current=yuan,imitation_capacity=60,imitation_current=0)
    p.hp=max_hp(p);p.mp=max_mp(p);initial_mp=p.mp
    p.combat_plan=dict(manual=False,puppet_supply=supply)
    p.puppets=[dict(id=f'puppet-{i}',name='守卫',type='mechanical',realm_index=9 if high else 2,
        layer=1,body_training=0,immortal_body_level=0,divine_sense_rank=1,combat_power=combat_power(p),
        durability=100,alive=True,operating_energy=charge,energy_source_id=f'npc_training_puppet_energy_{grade}') for i in range(2)]
    engine._combat(g,dict(target_name='试炼对手',target_power=combat_power(p)*3,
        target_realm_index=9,target_layer=1,combat_type='cultivator',max_rounds=1,mp_loss_scale=0),False,random.Random(18))
    assert p.immortal_aperture['current']==expected_yuan
    assert p.mp==pytest.approx(initial_mp-mp_cost)
    assert [a['operating_energy'] for a in p.puppets]==[expected_charge]*2
    engine.store.save(g);loaded=engine.store.load(g.id)
    assert loaded.player.mp==p.mp
    assert loaded.player.immortal_aperture['current']==expected_yuan
    assert loaded.player.puppets==p.puppets
    assert loaded.player.combat_plan['puppet_supply']==supply


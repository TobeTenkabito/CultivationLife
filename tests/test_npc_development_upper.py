import copy
import random
from pathlib import Path
import pytest
from test_npc_development import game
from cultivation_life.content_registry import REALMS, WORLD_SYSTEMS
from cultivation_life.rules import add_item
from cultivation_life.system.npc_development import service, presentation
from cultivation_life.system.combat.contracts import CombatCapabilities, Combatant
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.trials import dump_battle, load_battle


@pytest.mark.parametrize('path,world',[('dao','celestial'),('demonic','asura'),('monster','nether'),('ghost','reincarnation')])
def test_upper_steps_and_conversion_preserve_original_ledger(game,path,world):
    n=game.world_npcs['student'];n.path=path;n.world=game.player.world=world
    n.realm_index=9;n.layer=8;n.body_training=100;n.immortal_body_level=0
    game.player.realm_index=12;game.player.layer=9
    material=f'npc_training_{path}_cultivation_3';add_item(game.player,material,10)
    before=copy.deepcopy(game.to_dict())
    q=service.quote(game,'npc',n.id,'cultivation','material',5)
    assert q['rounds']==5 and (q['result']['realm_index'],q['result']['layer'])==(10,4)
    assert game.to_dict()==before
    service.apply(game,'npc',n.id,'cultivation','material',5)
    assert n.immortal_body_level==0 and n.transcendence is None
    add_item(game.player,f'npc_training_{path}_conversion_3',5)
    service.apply(game,'npc',n.id,'conversion','material',5)
    assert n.transcendence['conversion']==1 and n.transcendence['current']==0
    assert n.transcendence['capacity']==5000
    n.transcendence['current']=123
    service.apply(game,'npc',n.id,'cultivation','material',1)
    assert n.transcendence['current']==123
    add_item(game.player,f'npc_training_{path}_body_3',1)
    service.apply(game,'npc',n.id,'body','material',1)
    assert n.immortal_body_level==2
    assert n.world==world and game.player.age==before['player']['age']


def test_upper_entry_does_not_move_and_wrong_world_is_atomic(game):
    n=game.world_npcs['student'];n.realm_index=8;n.layer=9
    n.world=game.player.world='spirit';add_item(game.player,'npc_training_dao_cultivation_3',1)
    before=copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError):service.apply(game,'npc',n.id,'cultivation','material')
    assert game.to_dict()==before
    n.world=game.player.world='asura'
    with pytest.raises(ValueError,match='对应'):service.apply(game,'npc',n.id,'cultivation','material')
    n.world=game.player.world='celestial'
    service.apply(game,'npc',n.id,'cultivation','material')
    assert (n.realm_index,n.layer,n.world)==(9,1,'celestial')
    n.realm_index=12;n.layer=REALMS[12].layers
    with pytest.raises(ValueError):service.apply(game,'npc',n.id,'cultivation','material')


def test_energy_capacity_growth_settles_old_interval_once(game):
    n=game.world_npcs['student'];n.world=game.player.world='celestial';n.realm_index=9;n.layer=3
    n.transcendence=dict(conversion=1,capacity=1000,current=10,force_tier=2,
        lifecycle=dict(at=game.player.age-2,world='celestial',rate=10))
    add_item(game.player,'npc_training_dao_cultivation_3',2)
    service.apply(game,'npc',n.id,'cultivation','material')
    assert n.transcendence['current']==30 and n.transcendence['capacity']==2000
    service.apply(game,'npc',n.id,'cultivation','material')
    assert n.transcendence['current']==30


def test_partial_native_conversion_reaches_full_without_refill(game):
    n=game.world_npcs['student'];n.world=game.player.world='celestial';n.realm_index=9
    n.transcendence=dict(conversion=.9,capacity=1000,current=17,force_tier=2)
    add_item(game.player,'npc_training_dao_conversion_3',1)
    service.apply(game,'npc',n.id,'conversion','material')
    assert n.transcendence['conversion']==1 and n.transcendence['current']==17


@pytest.mark.parametrize('kind',['corpse','mechanical','living'])
def test_asset_materials_and_charge_are_original_and_separate(game,kind):
    asset=dict(id='asset',name='守卫',type=kind,realm_index=9,layer=1,body_training=100,
               immortal_body_level=0,divine_sense_rank=101,combat_power=500,alive=True)
    game.player.puppets=[asset];game.player.world='asura'
    add_item(game.player,'npc_training_puppet_cultivation_3',1)
    add_item(game.player,'npc_training_puppet_energy_3',2)
    service.apply(game,'puppet','asset','cultivation','material')
    assert asset['layer']==2 and 'operating_energy' not in asset
    snapshot=copy.deepcopy(game.to_dict());presentation.public(game)
    assert game.to_dict()==snapshot
    service.charge(game,'puppet','asset')
    assert asset['operating_energy']==100
    snapshot=copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError,match='已满'):service.charge(game,'puppet','asset')
    assert game.to_dict()==snapshot
    asset['alive']=False
    with pytest.raises(ValueError):service.charge(game,'puppet','asset')


def test_corpse_body_does_not_inherit_departed_source_soul(game):
    source=game.world_npcs['student'];source.alive=False;source.spirit_state={'mode':'wandering'}
    game.player.puppets=[dict(id='corpse',source_npc_id=source.id,name='尸卫',type='corpse',
        realm_index=2,layer=1,body_training=10,divine_sense_rank=17,corpse_integrity=100,combat_power=100)]
    add_item(game.player,'npc_training_puppet_body_1',1)
    service.apply(game,'puppet','corpse','body','material')
    assert game.player.puppets[0]['body_training']==20
    assert not source.alive and source.spirit_state['mode']=='wandering'


def battle(energy=15,charge=10,count=2):
    units=[Combatant('player','主人','player',10,CombatCapabilities(capacity=100,current=energy,resource_tier=2)),
           Combatant('enemy','敌人','enemy',100,CombatCapabilities(ward_tier=2))]
    units += [Combatant(f'puppet-{i}','傀儡','player',100,CombatCapabilities(force_tier=2,
              operating_energy=charge,operating_cost=5,attack_resource_owner='player',sponsored_attack_cost=10)) for i in range(count)]
    return VoisinageBattle(units)


def test_two_puppets_share_real_owner_budget_and_resume_without_refill():
    b=battle()
    b.begin_round(1,player_condition=1,enemy_condition=1,player_mp=1,enemy_mp=1)
    b.ordinary_damage(.1,0)
    assert b.units['player'].current==5
    assert [b.units[f'puppet-{i}'].operating_energy for i in range(2)]==[10,5]
    assert ('puppet-1','enemy') in b._blocked_pairs
    assert ('puppet-0','enemy') not in b._blocked_pairs
    assert any('垫付10元力' in row for row in b.frame.events)
    saved=dump_battle(b);b=load_battle(saved)
    b.begin_round(2,player_condition=1,enemy_condition=1,player_mp=1,enemy_mp=1)
    before=b.units['enemy'].vitality;b.ordinary_damage(.1,0)
    assert b.units['enemy'].vitality==before and b.units['player'].current==5
    assert b.units['puppet-0'].operating_energy==5
    b.begin_round(3,player_condition=1,enemy_condition=1,player_mp=1,enemy_mp=1)
    b.ordinary_damage(.1,0)
    assert not b._available('puppet-0') and b.units['player'].current==5
    saved['states']['puppet-0']['operating_energy']=999
    with pytest.raises(ValueError,match='operating'):load_battle(saved)


def test_disabled_or_empty_puppet_does_not_pay():
    b=battle(energy=0,charge=0)
    b.begin_round(1,player_condition=1,enemy_condition=1,player_mp=1,enemy_mp=1)
    b.ordinary_damage(.1,0)
    assert b.units['player'].current==0
    b=battle(energy=50)
    b.units['puppet-0'].suppressed=True;b.units['puppet-1'].escaped=True
    b.begin_round(1,player_condition=1,enemy_condition=1,player_mp=1,enemy_mp=1)
    b.ordinary_damage(.1,0)
    assert b.units['player'].current==50


def test_real_combat_settles_player_aperture_and_asset_charge(tmp_path):
    from cultivation_life.engine import GameEngine
    from cultivation_life.rules import combat_power,max_hp,max_mp
    engine=GameEngine(Path(__file__).resolve().parents[1],tmp_path/'saves')
    game=engine.store.load(engine.create_game('傀儡结算','supreme_metal','dao',811,
        custom_start=dict(world='celestial',realm_index=9,layer=1))['id'])
    p=game.player;p.immortal_power_converted=True;p.immortal_conversion_stage=5
    p.immortal_aperture=dict(version=1,capacity=1000,current=35,imitation_capacity=60,imitation_current=0)
    p.hp=max_hp(p);p.mp=max_mp(p)
    p.puppets=[dict(id=f'puppet-{i}',name='守卫',type='mechanical',realm_index=9,layer=1,
        body_training=0,immortal_body_level=0,divine_sense_rank=1,combat_power=combat_power(p),
        durability=100,alive=True,operating_energy=100) for i in range(2)]
    game.pending_event=None
    engine._combat(game,dict(target_name='试炼对手',target_power=combat_power(p)*3,
        target_realm_index=9,target_layer=1,combat_type='cultivator',max_rounds=1),False,random.Random(18))
    assert p.immortal_aperture['current']==5
    assert [a['operating_energy'] for a in p.puppets]==[100,100]
    engine.store.save(game);loaded=engine.store.load(game.id)
    assert loaded.player.immortal_aperture['current']==5
    assert loaded.player.puppets[0]['operating_energy']==100

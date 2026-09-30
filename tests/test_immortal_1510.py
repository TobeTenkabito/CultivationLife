"""Economy deadlines, intrinsic growth and passive combat qualifications."""
import copy
from dataclasses import replace
from unittest.mock import patch

import pytest

from test_immortal_cultivation import prepared
from test_voisinage_effects import actor, caster, domain, begin
from cultivation_life.models import GameState, SectNpc
from cultivation_life.rules import add_item, max_hp, max_mp
from cultivation_life.system.combat.contracts import CombatCapabilities, VoisinageEffect
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat_loadout import project_loadout
from cultivation_life.system.doctrine.provider import battle_sources
from cultivation_life.system.immortal_cultivation import rules, golden_light_resistance, vein_intrinsic_bonus
from cultivation_life.system.ghost_system import canonical_intrinsic_hp, canonical_intrinsic_mp
from cultivation_life.system.teleport_system import public_teleport
from cultivation_life.system.tianji.tiers import artifact_force_tier, migrate_tiers
from cultivation_life.system.yaochi_system import offers


def at_pool(engine, game):
    game.player.location_id = 'expanse_celestial_8'
    game.yaochi_state['merit'] = 100000
    engine.store.save(game)


def test_golden_light_unlock_training_costs_and_reload(prepared):
    e,g,_=prepared
    assert not e.present(g)['golden_light']['available']
    with pytest.raises(ValueError, match='解锁'):
        e.immortal_action(g.id,'temper_golden_light')
    g.player.immortal_body['level']=20
    assert golden_light_resistance(g.player)==.01
    for stage in rules()['golden_light']['stages'][1:]:
        for key,count in stage['recipe'].items(): add_item(g.player,key,count)
    e.store.save(g)
    for rank in range(2,6):
        shown=e.immortal_action(g.id,'temper_golden_light')['golden_light']
        assert shown['rank']==rank
        assert shown['resistance']==[.01,.02,.04,.06,.10][rank-1]
    saved=e._load(g.id)
    assert project_loadout(saved,saved.player,player=True).body_voisinage_resistance==.1
    assert all(i.quantity==0 for i in saved.player.inventory if i.id in {k for s in rules()['golden_light']['stages'] for k in s['recipe']})
    with pytest.raises(ValueError,match='大圆满'):e.immortal_action(g.id,'temper_golden_light')


@pytest.mark.parametrize('resistance',[.01,.02,.04,.06,.1])
def test_golden_body_reduces_effect_without_changing_field_contest(resistance):
    d=domain(VoisinageEffect('strike',1,.4))
    battles=[]
    for value in (0,resistance):
        b=VoisinageBattle([actor('player','player',caster(d)),actor('enemy','enemy',CombatCapabilities(body_voisinage_resistance=value))])
        begin(b);battles.append(b)
    a,b=battles
    assert a.frame.relations==b.frame.relations
    assert b.units['enemy'].body==pytest.approx(1-(1-a.units['enemy'].body)*(1-resistance))
    # The same passive does not reduce an ordinary immortal-tier weapon.
    c=VoisinageBattle([actor('player','player',CombatCapabilities(artifact_tier=2)),actor('enemy','enemy',CombatCapabilities(ward_tier=2,body_voisinage_resistance=resistance))])
    begin(c);assert c.ordinary_damage(.4,0)[0]==.4


def test_gold_dominance_erosion_and_recovery_are_separate():
    def run(resistance):
        b=VoisinageBattle([actor('player','player',caster(domain(),current=3)),actor('enemy','enemy',CombatCapabilities(body_voisinage_resistance=resistance))])
        begin(b);begin(b,2);return b
    a,b=run(0),run(.1)
    assert b.units['enemy'].pressure==pytest.approx(a.units['enemy'].pressure*.9)
    d=domain(VoisinageEffect('restore_body',1,.3,target='self'))
    a=VoisinageBattle([actor('player','player',caster(d,body_voisinage_resistance=.1)),actor('enemy','enemy')])
    a.units['player'].body=.4;a.units['player'].vitality=.4
    begin(a)
    assert a.units['player'].body==pytest.approx(.7)


def test_veins_increase_intrinsic_maxima_once_without_healing(prepared):
    e,g,_=prepared
    p=g.player;p.immortal_vein_pity['9:1']=100
    hp,mp=canonical_intrinsic_hp(p),canonical_intrinsic_mp(p)
    p.hp=max_hp(p)*.4;p.mp=max_mp(p)*.3;current=p.hp,p.mp
    e.store.save(g);shown=e.immortal_action(g.id,'open_vein')
    loaded=e._load(g.id).player
    assert canonical_intrinsic_hp(loaded)-hp==1200
    assert canonical_intrinsic_mp(loaded)-mp==1000
    assert (loaded.hp,loaded.mp)==current
    assert shown['doctrines']['veins']['intrinsic_total']=={'hp':1200,'mp':1000}
    for _ in range(3):
        loaded=e._load(g.id).player
        assert canonical_intrinsic_hp(loaded)==hp+1200
    old=GameState.from_dict(g.to_dict());old.player.immortal_veins={'9':27,'10':3}
    assert vein_intrinsic_bonus(old.player,'hp')==27*1200+3*6000
    assert vein_intrinsic_bonus(GameState.from_dict(old.to_dict()).player,'hp')==50400


def test_pool_currency_and_legacy_buy_cannot_bypass_local_merit(prepared):
    e,g,_=prepared;book=offers(g)[0]
    with pytest.raises(ValueError,match='亲临'):e.doctrine_action(g.id,'buy',manual_id=book['id'])
    g.player.location_id='expanse_celestial_8';e.store.save(g)
    with pytest.raises(ValueError,match='功勋'):e.yaochi_action(g.id,'buy',book['id'])
    at_pool(e,g);stones=sum(i.quantity for i in g.player.inventory if i.id=='spirit_stone')
    e.doctrine_action(g.id,'buy',manual_id=book['id'])
    saved=e._load(g.id)
    assert saved.yaochi_state['merit']==100000-book['price']
    assert sum(i.quantity for i in saved.player.inventory if i.id=='spirit_stone')==stones
    e.yaochi_action(g.id,'exchange_stones',amount=3)
    e.yaochi_action(g.id,'exchange_court_merit',amount=2)
    saved=e._load(g.id)
    assert saved.heavenly_court['player_merit']==g.heavenly_court['player_merit']+2
    assert saved.yaochi_state['merit']==100000-book['price']-203
    with pytest.raises(ValueError):e.yaochi_action(g.id,'stones_to_merit')


def test_pool_commission_escrow_survives_reload_and_rotating_stock(prepared):
    e,g,_=prepared;at_pool(e,g)
    current={x['id'] for x in offers(g)}
    requested=next(o for o in offers(g,commission=True) if o['id'] not in current)
    e.yaochi_action(g.id,'publish',requested['id']);saved=e._load(g.id)
    order=saved.yaochi_state['orders'][0];balance=saved.yaochi_state['merit']
    with pytest.raises(ValueError,match='尚未'):e.yaochi_action(g.id,'claim_order',order['id'])
    saved.player.age=order['ready_age']+1000;e.store.save(saved)
    e.yaochi_action(g.id,'claim_order',order['id']);saved=e._load(g.id)
    assert saved.yaochi_state['merit']==balance and not saved.yaochi_state['orders']
    assert any(t.id==requested['id'] for t in saved.player.known_techniques)
    with pytest.raises(ValueError):e.yaochi_action(g.id,'claim_order',order['id'])


def test_pool_job_counts_only_actual_work_and_claims_once(prepared):
    e,g,_=prepared;at_pool(e,g)
    e.yaochi_action(g.id,'accept','tend_gardens');g=e._load(g.id)
    e._finish_yaochi_action(g,'rest',10000)
    assert g.yaochi_state['job']['progress']==0
    e._finish_yaochi_action(g,'yaochi_work',7)
    assert g.yaochi_state['job']['progress']==7
    e.store.save(g)
    with pytest.raises(ValueError,match='尚未'):e.yaochi_action(g.id,'claim_job')
    e._finish_yaochi_action(g,'yaochi_work',93);e.store.save(g)
    result=e.yaochi_action(g.id,'claim_job')
    assert result['yaochi']['merit']==100400
    with pytest.raises(ValueError):e.yaochi_action(g.id,'claim_job')


def test_pool_work_uses_real_advance_hook(prepared):
    from cultivation_life.content_registry import WORLD_SYSTEMS
    e,g,_=prepared;at_pool(e,g)
    with patch.dict(WORLD_SYSTEMS['time_units'], {'9':1}), patch.object(e,'_advance_guixu_calendar',return_value=False):
        e.yaochi_action(g.id,'accept','copy_records')
        shown=e.yaochi_action(g.id,'work')
    assert shown['yaochi']['job']['progress']==1
    assert shown['player']['age']==g.player.age+1


def test_pool_election_tickets_charge_once_and_control_real_votes(prepared):
    import random
    e,g,_=prepared;at_pool(e,g)
    e._sync_player_court_identity(g)
    court=g.heavenly_court
    court['open_election']={'office_id':next(iter(court['offices'])), 'round':1,'candidates':['player'],'opened_unit':court['unit']}
    e.store.save(g)
    ticket=court['seats'][0]['id']
    e.yaochi_action(g.id,'buy_vote',ticket)
    with pytest.raises(ValueError):e.yaochi_action(g.id,'buy_vote',ticket)
    saved=e._load(g.id)
    assert saved.yaochi_state['merit']==99500
    election=saved.heavenly_court['open_election']
    e._court_resolve_election_round(saved,random.Random(1),'none','')
    assert election['votes']['player']==49


def test_temporary_pass_deadlines_and_single_use(prepared):
    e,g,_=prepared
    info=public_teleport(g,e.maps);assert info['origin'] and info['destinations']
    destination=info['destinations'][0]['id'];origin=g.player.location_id;age=g.player.age
    e.teleport_action(g.id,'request_temporary')
    with pytest.raises(ValueError):e.teleport_action(g.id,'temporary',destination)
    g=e._load(g.id);g.player.age=age+100;e.store.save(g)
    assert e.present(g)['map']['teleport']['temporary']['status']=='ready'
    e.teleport_action(g.id,'temporary',destination)
    g=e._load(g.id);assert g.player.age==age+100
    g.player.location_id=origin;e.store.save(g)
    with pytest.raises(ValueError):e.teleport_action(g.id,'temporary',destination)
    e.teleport_action(g.id,'request_temporary');g=e._load(g.id)
    g.player.realm_index=10;g.player.age=age+300;e.store.save(g)
    assert public_teleport(g,e.maps)['temporary']['status']=='expired'
    with pytest.raises(ValueError):e.teleport_action(g.id,'temporary',destination)


def test_forgery_skill_roll_and_bad_destination_no_cost(prepared):
    e,g,_=prepared;p=g.player
    before=public_teleport(g,e.maps)['forge_chance'];p.art_experience['talisman']=100*40**2
    info=public_teleport(g,e.maps);assert info['forge_chance']>before
    e.store.save(g)
    with pytest.raises(ValueError):e.teleport_action(g.id,'forge',p.location_id)
    assert e._load(g.id).player.inventory==g.player.inventory
    with patch('cultivation_life.system.teleport_system.decode_rng') as rng:
        import random
        rng.return_value=random.Random(2) # .956 > capped .95
        e.teleport_action(g.id,'forge',info['destinations'][0]['id'])
    saved=e._load(g.id)
    assert saved.player.location_id==p.location_id and saved.player.hostility
    with patch('cultivation_life.system.teleport_system.decode_rng') as rng:
        rng.return_value=random.Random(1)
        e.teleport_action(g.id,'forge',info['destinations'][0]['id'])
    assert e._load(g.id).player.location_id==info['destinations'][0]['id']


def test_tianji_template_tier_and_actual_equipment_ownership(prepared):
    e,g,_=prepared
    assert artifact_force_tier({'base_combat_power':179999999})==1
    assert artifact_force_tier({'base_combat_power':180000000})==2
    d=next(d for d in g.tianji_state['artifacts'] if d['force_tier']==2)
    instance=dict(id='test_artifact',tianji={'definition_id':d['id'],'kind':'replica','replica_ratio':.01})
    g.player.inventory=[]
    g.player.crafted_artifacts=[instance];g.player.equipped_crafted_artifact_ids=['test_artifact']
    g.tianji_state.pop('force_tiers_version',None);migrate_tiers(g)
    assert instance['force_tier']==2
    assert project_loadout(g,g.player,player=True).artifact_tier==2
    g.player.equipped_crafted_artifact_ids=[]
    assert project_loadout(g,g.player,player=True).artifact_tier==1
    npc=SectNpc('actual_holder','持宝者','',1,1,500,None,world='human')
    g.tianji_state['holders']={d['id']:{'npc_id':npc.id}}
    assert battle_sources(g,{npc.id:npc})[npc.id].artifact_tier==2
    g.tianji_state['holders']={}
    assert npc.id not in battle_sources(g,{npc.id:npc})


def test_heavenly_court_and_pool_have_physical_locations(prepared):
    from cultivation_life.system.faction_geography import faction_site
    e,g,_=prepared
    assert faction_site(g.sects['heavenly_court'])['id']=='jade_capital'
    assert faction_site(g.sects['yaochi'])['id']=='expanse_celestial_8'
    assert len(g.heavenly_court['seats'])==49

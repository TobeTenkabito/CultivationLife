import copy
import random
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc, SectState
from cultivation_life.content_registry import ITEM_CATALOG, MARKET_GOODS, REALMS, GUIXU_EXCLUSIVE_ITEM_IDS, GUIXU_EXCLUSIVE_TECHNIQUE_IDS, ROOT_DEFINITIONS
from cultivation_life.rules import add_item, has_item
from cultivation_life.world_state import race_pair

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def engine(tmp_path):return GameEngine(ROOT,tmp_path/'saves')

def wallet(game):return sum(i.quantity for i in game.player.inventory if i.id=='spirit_stone')

def family_game(engine,world='human',root='supreme_wood'):
    shown=engine.create_game('家族验收','supreme_metal','dao',1400,preset_id='core')
    g=engine.store.load(shown['id']);g.player.world=world;g.player.realm_index=5;g.player.layer=3
    g.player.opportunity=100000;g.player.lifespan=10000;g.pending_event=None
    child={'id':'family_heir','name':'沈宁','realm_index':1,'layer':1,'age':20,'lifespan':110,'world':world,
        'alive':True,'spirit_root':root,'path':'dao','gender':'male','cultivation_started':True}
    g.player.offspring=[child];add_item(g.player,'spirit_stone',100000)
    g.family=SectState('test_family','沈氏',world,[engine._family_child_npc(child)],founded_by_player=True,founder_player_id=g.id,kind='family')
    engine.store.save(g);return g

@pytest.mark.parametrize('preset',[None,'core','spirit','mahayana'])
def test_all_starts_receive_one_elixir(engine,preset):
    shown=engine.create_game('初始药','supreme_metal','dao',11,preset_id=preset)
    g=engine.store.load(shown['id'])
    assert sum(i.quantity for i in g.player.inventory if i.id=='heroic_progeny_elixir')==1
    assert engine._catalog_price('item','heroic_progeny_elixir')==985
    assert not any(r['content_id']=='heroic_progeny_elixir' for r in MARKET_GOODS)

def test_elixir_persists_consumes_once_and_bypasses_infertility(engine):
    g=family_game(engine)
    engine.use_item(g.id,'heroic_progeny_elixir')
    g=engine.store.load(g.id);assert g.player.guaranteed_progeny
    assert not has_item(g.player,'heroic_progeny_elixir')
    assert engine._try_conceive_child(g,random.Random(1))==''
    assert g.player.guaranteed_progeny  # No valid partner must not spend the guarantee.
    g.player.dao_companion={'id':'mother','name':'顾清','alive':True,'realm_index':8,'world':g.player.world,'spirit_root':'none'}
    rng=Mock();rng.random.return_value=.999999;rng.choice.side_effect=lambda values:values[0];rng.randint.return_value=90
    engine._try_conceive_child(g,rng)
    assert not g.player.guaranteed_progeny
    assert g.player.offspring[-1]['spirit_root'].startswith(('supreme_','mutated_'))
    count=len(g.player.offspring);engine._try_conceive_child(g,rng);assert len(g.player.offspring)==count

def test_exclusive_sources_and_stale_market_shelf(engine):
    assert len(GUIXU_EXCLUSIVE_ITEM_IDS)>=440 and len(GUIXU_EXCLUSIVE_TECHNIQUE_IDS)>=110
    banned=set(GUIXU_EXCLUSIVE_ITEM_IDS)|set(GUIXU_EXCLUSIVE_TECHNIQUE_IDS)|{'heroic_progeny_elixir'}
    assert not banned.intersection(r['content_id'] for r in MARKET_GOODS)
    g=family_game(engine)
    for cid in [next(iter(GUIXU_EXCLUSIVE_ITEM_IDS)),'heroic_progeny_elixir']:
        g.market_offers.append({'id':'old','kind':'item','content_id':cid,'locked':True,'world':'human'})
        engine._ensure_market(g,random.Random(1))
        assert not any(o['content_id']==cid for o in g.market_offers)
        assert not engine._is_world_market_good('human','item',cid)
        assert not engine._merchant_commission_available({'kind':'item','definition_id':cid})

def test_teaching_adds_exact_power_and_cannot_duplicate(engine):
    g=family_game(engine);tech=next(t for t in g.player.known_techniques if t.combat_bonus>0)
    before=engine._npc_power(g.family.npcs[0])
    engine.family_action(g.id,'teach',{'npc_id':'family_heir','technique_id':tech.id})
    g=engine.store.load(g.id);assert engine._npc_power(g.family.npcs[0])==pytest.approx(before+tech.combat_bonus)
    with pytest.raises(ValueError,match='重复'):engine.family_action(g.id,'teach',{'npc_id':'family_heir','technique_id':tech.id})

def test_gift_transfers_equipment_and_party_survives_reload(engine):
    g=family_game(engine);before=engine._npc_power(g.family.npcs[0]);quantity=sum(i.quantity for i in g.player.inventory if i.id=='spirit_sword')
    engine.family_action(g.id,'gift_equipment',{'npc_id':'family_heir','item_id':'spirit_sword'})
    g=engine.store.load(g.id);assert engine._npc_power(g.family.npcs[0])==pytest.approx(before+ITEM_CATALOG['spirit_sword'].combat_bonus)
    assert sum(i.quantity for i in g.player.inventory if i.id=='spirit_sword')==quantity-1
    shown=engine.family_action(g.id,'invite',{'npc_id':'family_heir'})
    assert any(m['id']=='family_heir' for m in shown['party'])
    assert any(m['id']=='family_heir' for m in engine.get_game(g.id)['party'])

@pytest.mark.parametrize('world,root,cap',[('human','supreme_wood',2),('spirit','supreme_wood',3),('celestial','supreme_wood',4),
    ('human','heavenly_metal_wood',3),('spirit','heavenly_metal_wood',4),('celestial','heavenly_metal_wood',5)])
def test_infusion_caps_and_exact_cost(engine,world,root,cap):
    g=family_game(engine,world,root);npc=g.family.npcs[0];npc.realm_index=cap;npc.layer=REALMS[cap].layers-1
    g.player.realm_index=5 if world=='human' else 8;engine.store.save(g)
    expected=engine._family_infusion(g,npc);assert expected['cap_realm']==cap
    engine.family_action(g.id,'infuse',{'npc_id':npc.id})
    g=engine.store.load(g.id);assert g.family.npcs[0].layer==REALMS[cap].layers
    assert g.player.opportunity==100000-expected['cost']
    with pytest.raises(ValueError,match='上限'):engine.family_action(g.id,'infuse',{'npc_id':npc.id})

def test_no_interaction_before_adulthood_or_equal_rank(engine):
    g=family_game(engine);g.family.npcs[0].age=15;engine.store.save(g)
    with pytest.raises(ValueError,match='16'):engine.family_action(g.id,'invite',{'npc_id':'family_heir'})
    g.family.npcs[0].age=16;g.player.realm_index=1;g.player.layer=1;engine.store.save(g)
    with pytest.raises(ValueError,match='严格高于'):engine.family_action(g.id,'infuse',{'npc_id':'family_heir'})

def test_marriage_birth_guaranteed_roots_and_stop_decision(engine):
    g=family_game(engine);engine.family_action(g.id,'marry',{'npc_id':'family_heir'})
    g=engine.store.load(g.id);assert len(g.family.npcs)==2
    rng=Mock();rng.random.return_value=0;rng.choice.side_effect=lambda v:v[0];rng.randint.return_value=90
    engine._family_annual_governance(g,rng)
    assert len(g.player.offspring)==2 and g.player.offspring[-1]['spirit_root']!='none'
    count=len(g.player.offspring);engine._family_annual_governance(g,rng);assert len(g.player.offspring)==count
    g.player.age+=1;g.family_state['reproduction_enabled']=False
    engine._family_annual_governance(g,rng);assert len(g.player.offspring)==count
    g.player.age+=1;g.family_state['reproduction_enabled']=True;g.family.npcs[1].realm_index=5
    engine._family_annual_governance(g,rng);assert len(g.player.offspring)==count

def test_finance_in_base_game_and_only_local_cash(engine):
    from cultivation_life.system.economy import organizations as finance
    g=family_game(engine);g.family.npcs[0].realm_index=4
    finance.ensure_organizations(g)
    before=wallet(g)
    with patch.object(engine,'_intrigue_enabled',return_value=False):
        engine._family_annual_governance(g,random.Random(2))
        assert wallet(g)==before and 'ledger' in g.family_state
        engine.store.save(g)
        engine.family_action(g.id,'fund',{'amount':100})
        g=engine._load(g.id)
        assert wallet(g)==before-100
    g.player.age+=1
    finance.advance_organizations(g,engine.maps)
    before=wallet(g)
    engine._family_annual_governance(g,random.Random(2));assert wallet(g)>before
    g.player.world='spirit';g.player.age+=1;before=wallet(g)
    finance.advance_organizations(g,engine.maps)
    engine._family_annual_governance(g,random.Random(2));assert wallet(g)==before
    assert g.family_state['ledger']['dividend']==0


def test_weak_family_annexation_and_official_protection(engine):
    g=family_game(engine);g.family.npcs[0].realm_index=4
    sect=SectState('host_sect','强宗','human',[SectNpc(f'host_{i}','长老','长老',5,1,100,1000) for i in range(4)])
    g.sects[sect.id]=sect
    relation=engine._family_relation(g,sect);relation.update(status='vassal',overlord=sect.id,vassal=g.family.id)
    safe=copy.deepcopy(g);safe.family.npcs[0].faction_id=sect.id
    for _ in range(3):
        g.player.age+=1;engine._family_annual_governance(g,random.Random(2))
        safe.player.age+=1;engine._family_annual_governance(safe,random.Random(2))
    assert g.family.extinct
    assert not safe.family.extinct
    assert all(n.alive for n in g.family.npcs)

def test_family_diplomacy_war_uses_family_roster(engine):
    g=family_game(engine);target=next(s for s in g.sects.values() if s.world=='human' and s.kind=='sect' and not s.extinct)
    shown=engine.family_action(g.id,'diplomacy',{'target_id':target.id,'status':'war'})
    g=engine.store.load(g.id);war=g.wars[-1]
    assert war['attacker_id']==g.family.id and war['controller']=='player'
    assert engine._war_side_name(g,'sect',g.family.id)==g.family.name
    assert any(n.id=='family_heir' for n in engine._war_side_members(g,'sect',g.family.id,'human'))

def test_npc_families_are_in_family_directory_not_sect_directory(engine):
    g=family_game(engine);g.sects['npc_family']=SectState('npc_family','顾氏','human',[],kind='family')
    assert any(f['id']=='npc_family' for f in engine._public_family(g)['other_families'])
    g.player.faction_id=None
    assert not any(s['id']=='npc_family' for s in engine._public_faction(g)['available'])


def test_sect_appointment_preserves_family_and_ages_member_once(engine):
    g=family_game(engine);npc=g.family.npcs[0];npc.realm_index=4
    sect=next(s for s in g.sects.values() if s.world=='human' and s.kind=='sect' and not s.extinct)
    engine._family_relation(g,sect)['status']='alliance';engine.store.save(g)
    engine.family_action(g.id,'send_sect',{'npc_id':npc.id,'sect_id':sect.id})
    g=engine.store.load(g.id);npc=g.family.npcs[0];before=npc.age
    assert npc.id in {n.id for n in engine._sect_members(g,g.sects[sect.id])}
    from cultivation_life.system.economy.organizations import advance_organizations
    g.player.age+=1;advance_organizations(g,engine.maps);engine._annual_sect_update(g,random.Random(23))
    assert npc.age==before+1
    assert g.player.offspring[0]['age']==npc.age
    assert g.family_state['ledger']['office_income']>0
    engine._family_relation(g,g.sects[sect.id])['status']='war';g.player.age+=1
    engine._family_annual_governance(g,random.Random(23))
    assert g.family_state['ledger']['office_income']==0


def test_financial_debt_funding_and_expulsion_persist(engine):
    g=family_game(engine);g.family_state['debt']=500
    record=engine._ensure_intrigue_faction(g,'family',g.family.id);record['resources']=0
    before=wallet(g);engine.store.save(g)
    engine.family_action(g.id,'fund',{'amount':700})
    g=engine.store.load(g.id)
    assert wallet(g)==before-700 and g.family_state['debt']==0
    assert engine._ensure_intrigue_faction(g,'family',g.family.id)['resources']==200
    engine.family_action(g.id,'expel',{'npc_id':'family_heir'})
    g=engine.store.load(g.id);engine._family_register_children(g)
    assert not g.family.npcs and g.player.offspring[0]['family_traits']['expelled']


def test_refounding_does_not_restore_old_treasury_or_stale_officials(engine):
    g=family_game(engine);old_id=g.family.id
    sect=next(s for s in g.sects.values() if s.world=='human' and s.kind=='sect')
    engine._family_dissolve(g,'兼并',sect)
    engine.store.save(g);g=engine.store.load(g.id)
    actual=next(n for n in g.sects[sect.id].npcs if n.id=='family_heir')
    actual.age=25
    assert engine._intrigue_find_npc(g,'family_heir') is actual
    engine.store.save(g)
    engine.create_family(g.id,'沈氏新族')
    g=engine.store.load(g.id)
    assert g.family.id!=old_id
    assert g.family_state=={}
    assert g.family.npcs[0].age==25 and g.family.npcs[0].faction_id==sect.id
    assert not any(n.id=='family_heir' for n in g.sects[sect.id].npcs)


def test_elixir_can_be_consigned_but_legacy_npc_lot_is_refunded(engine):
    g=family_game(engine)
    g.auction_state={'id':'sale','status':'open','world':g.player.world,'location_id':g.player.location_id,
        'location_name':'坊市','round':0,'lots':[],'consignments':[],'attendees':[]}
    engine.store.save(g)
    engine.consign_auction_item(g.id,'heroic_progeny_elixir',985)
    g=engine.store.load(g.id);lot=g.auction_state['lots'][0]
    assert lot['seller']=='player' and lot['rated_price']==985
    assert not has_item(g.player,'heroic_progeny_elixir')
    legacy={'id':'old','seller':'npc','kind':'item','content_id':'heroic_progeny_elixir',
        'name':'英姿神武口服液','current_bidder':'player','current_bid':985}
    g.auction_state['lots']=[legacy];before=wallet(g)
    engine._finish_auction(g,random.Random(10))
    assert wallet(g)==before+985 and not has_item(g.player,'heroic_progeny_elixir')

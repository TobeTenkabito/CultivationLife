"""Actual commands, conservation, clan lineage and bounded inheritance study."""
import copy
from pathlib import Path
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, SectNpc
from cultivation_life.rules import learn_technique
from cultivation_life.content_registry import TECHNIQUE_CATALOG, MARKET_GOODS, WORLD_SYSTEMS
from cultivation_life.system.economy import depot, organizations
from cultivation_life.system.economy.ledger import balance, transfer_value, account
from cultivation_life.system.economy.state import ensure_regional_market
from cultivation_life.system.organization_heritage import public, ensure, ceiling, advance_member
from cultivation_life.system.family_membership import resolve_line, player_kin
from cultivation_life.system.teleport_construction import requirements
from cultivation_life.system.teleport_system import arrays

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def engine(tmp_path): return GameEngine(ROOT,tmp_path)

def game_at(engine,world='human',path='dao',rank=4):
    view=engine.create_game('传承验收','supreme_earth',path,2901,custom_start=dict(
        world=world,realm_index=rank,sect='new',sect_name='传承验收宗'),monster_species_id='fox' if path=='monster' else None)
    game=engine._load(view['id']);game.pending_event=None;game.active_trial=None
    entity=game.sects[game.player.faction_id]
    game.player.location_id=entity.location_id
    organizations.register(game,'sect',entity.id,world)
    transfer_value(game,f'background:{world}',depot.treasury(game,entity),10000000,'测试拨款')
    return game,entity

def total_cash(game):
    return sum(r['balance'] for r in game.economy_v2['accounts'].values())+sum(r.get('resources',0) for r in game.intrigue_state['factions'].values())+balance(game,'player')

def heritage_command(engine,game,entity,action,identity):
    revision=public(engine._load(game.id),entity)['revision']
    return engine.fleet_action(game.id,dict(action=action,owner_id=entity.id,revision=revision,technique_id=identity))

def test_free_first_learning_paid_copy_and_real_treasury(engine):
    game,entity=game_at(engine)
    identity='TECH_HUMAN_HERITAGE_2';state=ensure(entity);state['books']=[identity]
    game.player.known_techniques[:]=[t for t in game.player.known_techniques if t.id!=identity]
    transfer_value(game,'background:human','player',10000,'测试私人资本');engine.store.save(game)
    before=total_cash(game);wallet=balance(game,'player');treasury=balance(game,depot.treasury(game,entity))
    heritage_command(engine,game,entity,'heritage_learn',identity)
    actual=engine._load(game.id);assert balance(actual,'player')==wallet
    before_replay=actual.to_dict()
    with pytest.raises(ValueError,match='已经领悟'):heritage_command(engine,actual,actual.sects[entity.id],'heritage_learn',identity)
    assert engine.store.load(game.id).to_dict()==before_replay
    heritage_command(engine,actual,actual.sects[entity.id],'heritage_copy',identity)
    actual=engine._load(game.id);assert balance(actual,'player')==wallet-1500
    assert balance(actual,depot.treasury(actual,actual.sects[entity.id]))==treasury+1500
    assert any(i.technique_id==identity and i.technique_level==1 for i in actual.player.inventory)
    assert total_cash(actual)==before

@pytest.mark.parametrize('world,path,rank', [('human','dao',4),('demon','demonic',4),('spirit','dao',7),
 ('true_demon','demonic',7),('monster_realm','monster',7),('phantom_underworld','ghost',7),('hell','ghost',7),
 ('celestial','dao',11),('asura','demonic',11),('nether','monster',11),('reincarnation','ghost',11)])
def test_initial_library_caps_and_all_world_new_inheritances(engine,world,path,rank):
    game,entity=game_at(engine,world,path,rank)
    before=game.to_dict();view=public(game,entity)
    assert 1<=len(view['books'])<=3 and game.to_dict()==before
    for book in view['books']:
        assert TECHNIQUE_CATALOG[book['id']].grade<=ceiling(world)
    assert sum(g.get('world','human')==world and '_HERITAGE_' in g['content_id'] for g in MARKET_GOODS)==7
    assert all(TECHNIQUE_CATALOG[g['content_id']].force_tier==(2 if g['tier']>=9 else 1)
               for g in MARKET_GOODS if g.get('world','human')==world and '_HERITAGE_' in g['content_id'])

def test_decision_holder_can_add_but_cannot_build_and_cap_is_authoritative(engine):
    game,entity=game_at(engine);entity.founded_by_player=False
    entity.npcs[0].realm_index=5;entity.npcs[0].layer=1
    identity='TECH_HUMAN_HERITAGE_4';learn_technique(game.player,TECHNIQUE_CATALOG[identity]);ensure(entity)['books']=['TECH_HUMAN_HERITAGE_1']
    game.player.location_id=next(l['id'] for l in engine.maps.worlds['human']['locations'] if not l.get('teleport_array') and not l.get('min_realm_index'))
    engine.store.save(game);before=engine._load(game.id).to_dict()
    with pytest.raises(ValueError,match='控制权'):engine.teleport_action(game.id,'build',owner_id=entity.id)
    assert engine.store.load(game.id).to_dict()==before
    game=engine._load(game.id);game.player.location_id=entity.location_id;engine.store.save(game)
    heritage_command(engine,game,game.sects[entity.id],'heritage_add',identity)
    game=engine._load(game.id);learn_technique(game.player,TECHNIQUE_CATALOG['TECH_SPIRIT_HERITAGE_4']);engine.store.save(game)
    with pytest.raises(ValueError,match='上限'):heritage_command(engine,game,game.sects[entity.id],'heritage_add','TECH_SPIRIT_HERITAGE_4')

def test_build_consumes_local_materials_and_cash_and_connects_existing_network(engine):
    game,entity=game_at(engine)
    site=next(l['id'] for l in engine.maps.worlds['human']['locations'] if not l.get('teleport_array') and not l.get('min_realm_index'))
    game.player.location_id=site;ensure_regional_market(game,engine.maps,'human',site)
    market=game.economy_v2['markets'][f'human:{site}']
    for identity,qty in requirements('human').items(): market['commodities'][identity]['stock']=qty+30
    stocks={k:market['commodities'][k]['stock'] for k in requirements('human')}
    before_cash=total_cash(game);age=game.player.age;engine.store.save(game)
    engine.teleport_action(game.id,'build',owner_id=entity.id)
    game=engine._load(game.id);assert total_cash(game)==before_cash and game.player.age==age
    for identity,qty in requirements('human').items():assert game.economy_v2['markets'][f'human:{site}']['commodities'][identity]['stock']==stocks[identity]-qty
    assert arrays(game,engine.maps)[site]['owner_id']==entity.id
    before=game.to_dict()
    with pytest.raises(ValueError,match='已有'):engine.teleport_action(game.id,'build',owner_id=entity.id)
    assert engine.store.load(game.id).to_dict()==before
    info=engine.get_game(game.id)['map']['teleport'];assert info['origin']['licensed']
    assert info['destinations']
    destination=info['destinations'][0]['id'];engine.teleport_action(game.id,'travel',destination)
    actual=engine.store.load(game.id);assert actual.player.location_id==destination and actual.player.age==age and actual.player.world=='human'
    assert GameState.from_dict(actual.to_dict()).economy_v2['teleport_arrays']==actual.economy_v2['teleport_arrays']

def test_contribution_reserved_refunded_and_spent_once(engine):
    game,entity=game_at(engine);game.player.faction_contribution=10
    stock=depot.ensure(game,entity);key=next(k for k,v in depot.catalog('human').items() if v['kind']=='item' and v['tier']==1)
    depot.purchase(game,engine.maps,entity,key,2);engine.store.save(game)
    def command(action,**payload):
        actual=engine._load(game.id);e=actual.sects[entity.id];row=depot.find(actual,e)
        return engine.fleet_action(game.id,dict(action=action,owner_id=e.id,revision=row['revision'],**payload))
    command('depot_request',item=key,quantity=1)
    game=engine._load(game.id);assert game.player.faction_contribution==9
    request=depot.find(game,game.sects[entity.id])['requests'][-1]
    command('depot_cancel',request_id=request['id']);assert engine._load(game.id).player.faction_contribution==10
    command('depot_request',item=key,quantity=1)
    game=engine._load(game.id);game.diplomacy_unit+=1;engine.store.save(game)
    request=depot.find(game,game.sects[entity.id])['requests'][-1]
    command('depot_approve',request_id=request['id']);command('depot_collect',request_id=request['id'])
    assert engine._load(game.id).player.faction_contribution==9

def clan_game(engine):
    game,_=game_at(engine)
    family=next(s for s in game.sects.values() if s.kind=='family' and s.world=='human')
    organizations.register(game,'sect',family.id,'human');transfer_value(game,'background:human',depot.treasury(game,family),100000,'测试家族资本')
    game.player.location_id=family.location_id;engine.store.save(game)
    return game,family

def test_external_join_keeps_original_npcs_assets_and_pays_actual_wage(engine):
    game,family=clan_game(engine);ids=[n.id for n in family.npcs];funds=balance(game,depot.treasury(game,family));money=total_cash(game)
    view=engine.family_action(game.id,'join',dict(target_id=family.id))
    actual=engine._load(game.id);assert actual.family.id==family.id and family.id not in actual.sects
    assert [n.id for n in actual.family.npcs]==ids and not player_kin(actual,actual.family)
    assert balance(actual,depot.treasury(actual,actual.family))==funds and total_cash(actual)==money
    assert view['family']['player_member_type']=='外姓修士'
    wallet=balance(actual,'player');actual.player.age+=1
    organizations.advance_organizations(actual,engine.maps)
    assert balance(actual,'player')>wallet
    after=total_cash(actual);wallet=balance(actual,'player');organizations.advance_organizations(actual,engine.maps)
    assert total_cash(actual)==after and balance(actual,'player')==wallet
    assert GameState.from_dict(actual.to_dict()).family.id==family.id

def test_extinct_bloodline_player_succeeds_and_renames_once(engine):
    game,family=clan_game(engine);engine.family_action(game.id,'join',dict(target_id=family.id));game=engine._load(game.id)
    for n in game.family.npcs:n.alive=False
    resolve_line(game,game.family);assert player_kin(game,game.family) and not game.family.extinct
    identity=game.family.id;engine.store.save(game)
    engine.family_action(game.id,'rename',dict(name='新传承仙族'))
    game=engine._load(game.id);assert game.family.id==identity and game.family.name=='新传承仙族'
    with pytest.raises(ValueError,match='一次'):engine.family_action(game.id,'rename',dict(name='重复更名'))

def test_living_player_founder_and_absent_living_kin_block_extinction(engine):
    game,family=clan_game(engine)
    # Born into the original clan: the player belongs to its bloodline.
    game.sects.pop(family.id);game.family=family;game.family_state={}
    for n in family.npcs:n.alive=False
    resolve_line(game,family);assert not family.extinct and 'line_successor' not in ensure(family)
    game.family_state['membership']={'kin':False};n=family.npcs[0];n.alive=True;n.world='spirit';n.family_traits['kin']=True
    resolve_line(game,family);assert 'line_successor' not in family.heritage

def test_npc_free_study_upgrade_donation_are_funded_and_idempotent(engine):
    game,entity=game_at(engine);state=ensure(entity);state['books']=['TECH_HUMAN_HERITAGE_1']
    npc=entity.npcs[0];npc.path='dao';npc.realm_index=4;npc.main_technique_id='TECH_HUMAN_HERITAGE_2'
    account(game,f'study:sect:{entity.id}');transfer_value(game,'background:human',f'study:sect:{entity.id}',100000,'测试已付劳务津贴')
    cash=total_cash(game);initial_power=engine._npc_power(npc)
    for year in range(23,1023,10):
        game.player.age=year;advance_member(game,entity,npc)
        before=copy.deepcopy(game.to_dict());advance_member(game,entity,npc);assert game.to_dict()==before
    learned=npc.family_traits['heritage_study']['levels'];assert learned['TECH_HUMAN_HERITAGE_1']>1
    assert 'TECH_HUMAN_HERITAGE_2' in state['books']
    assert total_cash(game)==cash and len(state['history'])<=16
    assert engine._npc_power(npc)>initial_power

@pytest.mark.parametrize('failure',['funds','materials','dead'])
def test_build_failure_keeps_entire_saved_state(engine,failure):
    game,entity=game_at(engine)
    site=next(l['id'] for l in engine.maps.worlds['human']['locations'] if not l.get('teleport_array') and not l.get('min_realm_index'))
    game.player.location_id=site;ensure_regional_market(game,engine.maps,'human',site)
    for identity,qty in requirements('human').items():game.economy_v2['markets']['human:'+site]['commodities'][identity]['stock']=qty+1
    if failure=='funds':transfer_value(game,depot.treasury(game,entity),'background:human',balance(game,depot.treasury(game,entity)),'测试缺款')
    elif failure=='materials':
        identity=next(iter(requirements('human')));game.economy_v2['markets']['human:'+site]['commodities'][identity]['stock']=0
    else:game.player.alive=False
    engine.store.save(game);engine._load(game.id);before=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):engine.teleport_action(game.id,'build',owner_id=entity.id)
    assert engine.store._path(game.id).read_bytes()==before

def test_family_handover_preserves_depot_and_old_receipt_payer(engine):
    game,family=clan_game(engine)
    item=next(k for k,v in depot.catalog('human').items() if v['kind']=='item' and v['tier']==1)
    depot.purchase(game,engine.maps,family,item,2);stock=copy.deepcopy(depot.find(game,family)['stock'])
    old=depot.treasury(game,family);funds=balance(game,old);money=total_cash(game);engine.store.save(game)
    engine.family_action(game.id,'join',dict(target_id=family.id));game=engine._load(game.id)
    assert depot.find(game,game.family)['stock']==stock
    transfer_value(game,old,'player',10,'交接前收据的实际付款')
    assert balance(game,depot.treasury(game,game.family))==funds-10 and total_cash(game)==money
    assert old not in game.economy_v2['organizations']
    GameState.from_dict(game.to_dict())

def test_family_handover_keeps_real_estate_and_fleet_ids(engine):
    from cultivation_life.system.economy.enterprise_acquisition import acquire
    from cultivation_life.system.economy.fleet_network import active_fleets
    game,family=clan_game(engine);game.player.faction_id=family.id
    transfer_value(game,'background:human',depot.treasury(game,family),1000000,'测试既有族产')
    ensure_regional_market(game,engine.maps,'human',family.location_id)
    acquire(game,engine.maps,'human',family.location_id,'farm','sect',family.id,depot.treasury(game,family),4)
    engine.store.save(game)
    if not active_fleets(game,'human','sect',family.id):
        engine.fleet_action(game.id,dict(action='create',owner_kind='sect'))
    game=engine._load(game.id);family=game.sects[family.id]
    properties=copy.deepcopy(game.economy_v2['estates'])
    fleets={f['id']:copy.deepcopy(f) for f in active_fleets(game,'human','sect',family.id)}
    funds=balance(game,depot.treasury(game,family));engine.store.save(game)
    engine.family_action(game.id,'join',dict(target_id=family.id));game=engine._load(game.id)
    assert balance(game,depot.treasury(game,game.family))==funds
    for key,before in properties.items():
        if before['owner_id']==family.id:
            before['owner_kind']='family';assert game.economy_v2['estates'][key]==before
    for identity,before in fleets.items():
        before['owner_kind']='family';assert game.economy_v2['transport']['worlds']['human']['fleets'][identity]==before
    GameState.from_dict(game.to_dict())

def test_strongest_absent_outsider_and_descendants_inherit_without_moving(engine):
    game,family=clan_game(engine);engine.family_action(game.id,'join',dict(target_id=family.id));game=engine._load(game.id);family=game.family
    for n in family.npcs:n.alive=False
    winner=family.npcs[0];winner.alive=True;winner.realm_index=5;winner.world='spirit';winner.family_traits={'kin':False}
    child=copy.deepcopy(winner);child.id+='child';child.realm_index=0;child.world='human';child.family_traits={'kin':False,'parents':[winner.id]};family.npcs.append(child)
    resolve_line(game,family)
    assert family.heritage['line_successor']==winner.id and winner.world=='spirit' and child.family_traits['kin']
    assert not player_kin(game,family) and not family.heritage['rename_available']

def test_outsider_clan_child_starts_cultivation_without_becoming_player_offspring(engine):
    import random
    game,family=clan_game(engine);engine.family_action(game.id,'join',dict(target_id=family.id));game=engine._load(game.id)
    child=SectNpc('actual-clan-child','家族后辈','嫡系后人',0,1,
        int(WORLD_SYSTEMS['family']['cultivation_start_age'])-1,100,spirit_root='supreme_earth',world='human',
        family_traits={'kin':True,'parents':[game.family.npcs[0].id]})
    game.family.npcs.append(child)
    engine._annual_offspring_and_family_update(game,random.Random(290))
    assert child.realm_index==1 and child.layer==1
    assert all(c['id']!=child.id for c in game.player.offspring)

def test_children_of_two_outsiders_do_not_gain_bloodline_from_player_membership(engine):
    from unittest.mock import Mock
    game,family=clan_game(engine);engine.family_action(game.id,'join',dict(target_id=family.id));game=engine._load(game.id)
    game.family_state['membership']['kin']=True;game.family_state['reproduction_enabled']=True
    for n in game.family.npcs:n.alive=False
    parents=game.family.npcs[:2]
    for n,other in zip(parents,reversed(parents)):
        n.alive=True;n.realm_index=1;n.age=20;n.world='human';n.family_traits={'kin':False,'spouse_id':other.id}
    ids={n.id for n in game.family.npcs};rng=Mock();rng.random.return_value=0.;rng.choice.side_effect=lambda values:values[0];rng.randint.side_effect=lambda lo,hi:lo
    engine._family_annual_governance(game,rng)
    children=[n for n in game.family.npcs if n.id not in ids]
    assert len(children)==1 and not children[0].family_traits['kin']
    assert all(c['id']!=children[0].id for c in game.player.offspring)

def test_wage_shortfall_and_absence_never_create_cash_or_arrears(engine):
    from unittest.mock import patch
    from cultivation_life.system.family_membership import wage
    game,family=clan_game(engine);engine.family_action(game.id,'join',dict(target_id=family.id));game=engine._load(game.id);family=game.family
    row=organizations.register(game,'family',family.id,family.world);row['expected_upkeep']=0
    source=depot.treasury(game,family)
    transfer_value(game,source,'background:human',balance(game,source)-5,'测试有限府库')
    wallet=balance(game,'player');cash=total_cash(game)
    with patch.object(organizations,'produce',return_value=0),patch('cultivation_life.system.economy.industry.settle_industry'),patch('cultivation_life.system.economy.organization_consumption.consume',return_value=0),patch('cultivation_life.system.economy.estate_management.invest_surplus'):
        organizations.settle_faction(game,engine.maps,row,1)
        assert balance(game,'player')==wallet+5 and total_cash(game)==cash
        row['benefit_due']=row['benefit_paid']=0;game.player.world='spirit'
        organizations.settle_faction(game,engine.maps,row,100)
        assert balance(game,'player')==wallet+5 and row['benefit_due']==0
        game.player.world='human';transfer_value(game,'background:human',source,1000,'测试续付')
        organizations.settle_faction(game,engine.maps,row,1)
        assert row['benefit_due']==wage('human',4) and row['benefit_paid']==wage('human',4)

def test_insufficient_contribution_and_wrong_rejoin_cannot_refund(engine):
    game,entity=game_at(engine);game.player.faction_contribution=0
    item=next(k for k,v in depot.catalog('human').items() if v['kind']=='item' and v['tier']==1)
    depot.purchase(game,engine.maps,entity,item,1);engine.store.save(game);before=engine.store._path(game.id).read_bytes()
    payload=dict(action='depot_request',owner_id=entity.id,revision=depot.find(game,entity)['revision'],item=item,quantity=1)
    with pytest.raises(ValueError,match='贡献'):engine.fleet_action(game.id,payload)
    assert engine.store._path(game.id).read_bytes()==before
    game.player.faction_contribution=10;game.player.faction_join_age=game.player.age;engine.store.save(game)
    engine.fleet_action(game.id,payload);game=engine._load(game.id);entity=game.sects[entity.id]
    row=depot.find(game,entity);game.player.faction_join_age+=1;engine.store.save(game)
    engine.fleet_action(game.id,dict(action='depot_cancel',owner_id=entity.id,revision=row['revision'],request_id=row['requests'][-1]['id']))
    assert engine._load(game.id).player.faction_contribution==9

@pytest.mark.parametrize('bad',[{'books':['x','x'],'revision':0,'history':[]},{'books':[],'revision':-1,'history':[]},[]])
def test_invalid_persistent_inheritance_rejected(engine,bad):
    game,entity=game_at(engine);raw=game.to_dict();raw['sects'][entity.id]['heritage']=bad
    with pytest.raises(ValueError,match='传承'):GameState.from_dict(raw)

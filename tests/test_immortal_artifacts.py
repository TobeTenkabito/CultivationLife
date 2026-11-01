"""Real ownership, costs, attack qualification and independent grade boundaries."""
import copy
from pathlib import Path

import pytest
from cultivation_life.engine import GameEngine
from cultivation_life import content_registry as registry
from cultivation_life.models import GameState,HistoryRecord,Item
from cultivation_life.rules import add_item,combat_power,has_item,remove_item
from cultivation_life.system import immortal_artifacts as ia
from cultivation_life.system.combat_loadout import project_loadout

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def ready(tmp_path):
    e=GameEngine(ROOT,tmp_path/'saves')
    g=e._load(e.create_game('三铸养器','supreme_metal','dao',1101,preset_id='core')['id'])
    g.pending_event=None;g.player.inventory.clear()
    add_item(g.player,'starfall_blade');add_item(g.player,'spirit_stone',10**12)
    for key,_ in ia.MATERIALS:add_item(g.player,key,30)
    e.store.save(g)
    return e,g


def upper(e,g,world='celestial'):
    g.player.world=world;g.player.location_id=e.maps.default_location(world)
    g.player.realm_index=9;g.player.next_tribulation_age=None
    g.pending_event=None;g.active_trial=None;e.store.save(g)
    return g


def immortal_item():
    return copy.deepcopy(next(i for i in registry.ITEM_CATALOG.values()
        if {'artifact','equipment'} & set(i.tags) and ia.tier(i)>=2 and not i.crafted_artifact_id))


def test_36_rejected_37_promotes_without_power_or_level_change(ready):
    e,g=ready;e.natal_artifact_action(g.id,'bind','starfall_blade')
    g=e._load(g.id);g.natal_artifact['refinement_count']=36;e.store.save(g)
    path=e.store._path(g.id);before=path.read_bytes()
    with pytest.raises(ValueError,match='37'):e.natal_artifact_action(g.id,'promote')
    assert path.read_bytes()==before
    e.natal_artifact_action(g.id,'refine')
    before=e._load(g.id);power=combat_power(before.player);level=before.natal_artifact['level']
    quantity=next(i.quantity for i in before.player.inventory if i.id==ia.MATERIALS[0][0])
    result=e.natal_artifact_action(g.id,'promote');after=e._load(g.id)
    assert result['natal_artifact']['damage_type']=='仙'
    assert after.natal_artifact['refinement_count']==37
    assert after.natal_artifact['immortal_grade']==5
    assert level==after.natal_artifact['level'] and combat_power(after.player)==power
    assert next(i.quantity for i in after.player.inventory if i.id==ia.MATERIALS[0][0])==quantity-1
    assert project_loadout(after,after.player,player=True).artifact_tier>=2
    snapshot=path.read_bytes()
    with pytest.raises(ValueError,match='已具备'):e.natal_artifact_action(g.id,'promote')
    assert path.read_bytes()==snapshot


def test_levels_and_passive_experience_do_not_invent_manual_count(ready):
    e,g=ready;e.natal_artifact_action(g.id,'bind','starfall_blade')
    g=e._load(g.id);g.natal_artifact.update(level=100,experience=40000)
    assert ia.refinement_count(g)==0
    e.store.save(g)
    with pytest.raises(ValueError,match='37'):e.natal_artifact_action(g.id,'promote')


def test_old_current_binding_receipts_only_are_counted(ready):
    e,g=ready;e.natal_artifact_action(g.id,'bind','starfall_blade');g=e._load(g.id)
    g.natal_artifact.pop('refinement_count')
    g.history.append(HistoryRecord('SYS_NATAL_ARTIFACT',1,g.player.age,'温养',None,'refined_all','连续温养 36 次',{'artifact':dict(g.natal_artifact)}))
    assert ia.refinement_count(g)==36
    g.history.append(HistoryRecord('SYS_NATAL_ARTIFACT',1,g.player.age,'温养',None,'refined','温养一次',{'artifact':dict(g.natal_artifact)}))
    assert ia.refinement_count(g)==37


def test_inventory_stack_splits_one_and_duplicate_page_rejected(ready):
    e,g=ready;upper(e,g);item=immortal_item();add_item(g.player,item,2);e.store.save(g)
    shown=e.get_game(g.id);row=next(r for r in shown['immortal_artifacts']['equipment'] if r['id']=='bag:'+item.id)
    before=e._load(g.id);power=combat_power(before.player)
    args=(g.id,row['id'],5,shown['immortal_artifacts']['revision'])
    e.immortal_artifact_action(*args)
    after=e._load(g.id)
    assert combat_power(after.player)==power and after.rng_state==before.rng_state and after.player.age==before.player.age
    assert next(i.quantity for i in after.player.inventory if i.id==item.id)==1
    refined=next(i for i in after.player.inventory if i.artifact_origin_id==item.id)
    assert refined.immortal_grade==4 and refined.quantity==1
    snapshot=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError,match='过期'):e.immortal_artifact_action(*args)
    assert e.store._path(g.id).read_bytes()==snapshot
    add_item(after.player,item);assert next(i for i in after.player.inventory if i.id==item.id).immortal_grade is None


def test_original_item_requirements_consume_real_refined_units(ready):
    e,g=ready;upper(e,g);item=immortal_item();add_item(g.player,item,2)
    ia.cultivate(g,'bag:'+item.id,5)
    assert has_item(g.player,item.id,2) and not has_item(g.player,item.id,3)
    before=g.player.to_dict()
    assert not remove_item(g.player,item.id,3) and g.player.to_dict()==before
    assert remove_item(g.player,item.id,2)
    assert not has_item(g.player,item.id)
    assert not any(i.id==item.id or i.artifact_origin_id==item.id for i in g.player.inventory)


def test_refining_attached_vessel_keeps_same_real_anchor(ready):
    from cultivation_life.system.ghost_resources import reconcile_ghost_attachment
    e,g=ready;upper(e,g);item=immortal_item();add_item(g.player,item)
    g.player.ghost_attachment={'item_id':item.id,'cultivation_efficiency_multiplier':1.1}
    ia.cultivate(g,'bag:'+item.id,5)
    refined=next(i for i in g.player.inventory if i.artifact_origin_id==item.id)
    assert g.player.ghost_attachment['item_id']==refined.id
    assert not reconcile_ghost_attachment(g.player)
    assert remove_item(g.player,item.id)
    assert g.player.ghost_attachment is None


def test_original_achievement_conditions_survive_refining_and_rebinding(ready):
    from cultivation_life.achievements import AchievementSystem
    e,g=ready;upper(e,g);item=immortal_item();add_item(g.player,item)
    ia.cultivate(g,'bag:'+item.id,5)
    checker=AchievementSystem((),e.store.directory)
    assert checker._matches({'item':item.id},g,player_rank=None)
    refined=next(i for i in g.player.inventory if i.artifact_origin_id==item.id)
    from cultivation_life.system.natal_binding import bind_standard
    bind_standard(g,refined.id)
    assert checker._matches({'natal_artifact':{'item_id':item.id}},g,player_rank=None)


def test_crafted_promotion_quality_has_one_authority(ready):
    _,g=ready
    artifact={'id':'original-forge','name':'原物剑','force_tier':1}
    g.player.crafted_artifacts=[artifact]
    g.natal_artifact={'item_id':artifact['id'],'crafted_artifact_id':artifact['id'],'refinement_count':37}
    ia.promote_natal(g)
    assert artifact['force_tier']==2 and ia.grade(artifact)==5
    assert 'immortal_grade' not in g.natal_artifact


def test_grade_one_limit_and_real_materials(ready):
    e,g=ready;upper(e,g);add_item(g.player,immortal_item());e.store.save(g)
    for rank in (5,4,3,2):
        shown=e.get_game(g.id);row=shown['immortal_artifacts']['equipment'][0]
        assert row['grade']==rank
        before=e._load(g.id);key=ia.MATERIALS[5-rank][0]
        qty=next(i.quantity for i in before.player.inventory if i.id==key)
        e.immortal_artifact_action(g.id,row['id'],rank,shown['immortal_artifacts']['revision'])
        after=e._load(g.id)
        assert next(i.quantity for i in after.player.inventory if i.id==key)==qty-3
    shown=e.get_game(g.id);row=shown['immortal_artifacts']['equipment'][0]
    assert row['grade']==1 and not row['can_refine']
    snapshot=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError,match='一品'):e.immortal_artifact_action(g.id,row['id'],1,shown['immortal_artifacts']['revision'])
    assert snapshot==e.store._path(g.id).read_bytes()


@pytest.mark.parametrize('world',list(registry.WORLD_SYSTEMS['world_names']))
def test_only_four_third_tier_worlds_and_only_immortal_equipment(ready,world):
    e,g=ready;g.player.world=world
    add_item(g.player,immortal_item())
    data=ia.public(g)
    assert data['available']==(world in {'celestial','asura','nether','reincarnation'})
    assert all(r['damage_type']=='仙' and not r['id'].endswith('starfall_blade') for r in data['equipment'])


@pytest.mark.parametrize('world',('lost','rift','unknown-world'))
def test_spaces_do_not_inherit_outer_world_training(ready,world):
    _,g=ready;g.player.world=world;assert not ia.public(g)['available']
    with pytest.raises(ValueError,match='三级'):ia.cultivate(g,'bag:starfall_blade',5)


def test_bound_promoted_item_roundtrips_without_duplication(ready):
    e,g=ready;e.natal_artifact_action(g.id,'bind','starfall_blade');g=e._load(g.id)
    g.natal_artifact['refinement_count']=37;e.store.save(g)
    e.natal_artifact_action(g.id,'promote');g=e._load(g.id);upper(e,g)
    shown=e.get_game(g.id);row=shown['immortal_artifacts']['equipment'][0]
    assert row['source']=='natal'
    e.immortal_artifact_action(g.id,row['id'],5,shown['immortal_artifacts']['revision'])
    e.natal_artifact_action(g.id,'unbind');g=e._load(g.id)
    item=next(i for i in g.player.inventory if i.artifact_origin_id=='starfall_blade')
    assert item.immortal_grade==4 and ia.tier(item)==2 and item.quantity==1
    assert project_loadout(g,g.player,player=True).artifact_tier>=2
    e.natal_artifact_action(g.id,'bind',item.id)
    g=e._load(g.id);assert ia.natal_tier(g)==2
    assert ia.grade(g.natal_artifact)==4 and ia.refinement_count(g)==0
    assert GameState.from_dict(g.to_dict()).natal_artifact==g.natal_artifact


def test_material_origin_tiers_and_neutral_attack_qualification():
    for n,(key,_) in enumerate(ia.MATERIALS):
        rows=[r for r in registry.MARKET_GOODS if r['content_id']==key]
        worlds={r.get('world','human') for r in rows}
        assert worlds==(set(registry.WORLD_SYSTEMS['world_names']) if n==0 else {'celestial','asura','nether','reincarnation'})
        assert ia.tier(registry.ITEM_CATALOG[key])==1


@pytest.mark.parametrize('path,expected',(('dao','仙器'),('demonic','魔器'),('monster','妖器'),('ghost','魂器'),('buddhist','佛器'),('confucian','儒器')))
def test_path_names_follow_loaded_dlc_only(ready,monkeypatch,path,expected):
    _,g=ready;g.player.path=path
    monkeypatch.setattr(registry,'EXTENSION_REPORT',[]);assert ia.title(g)=='仙器'
    owners=['official.asura-manifestation','official.monster-bloodlines','official.ghost-reincarnation','official.buddhist-dharma','official.sage-way']
    monkeypatch.setattr(registry,'EXTENSION_REPORT',[dict(id=k,status='loaded') for k in owners]);assert ia.title(g)==expected


def test_crafted_item_is_not_duplicated_in_equipment_list(ready):
    from cultivation_life.system.crafting_system import store_crafted_artifact
    e,g=ready;upper(e,g)
    artifact=dict(id='original-forge',name='原物仙剑',mold_id='sword',force_tier=2,actual_stats={'combat_power':900})
    store_crafted_artifact(g.player,artifact);e.store.save(g)
    shown=e.get_game(g.id);rows=[r for r in shown['immortal_artifacts']['equipment'] if r['id']=='crafted:original-forge']
    assert len(rows)==1
    power=combat_power(e._load(g.id).player)
    e.immortal_artifact_action(g.id,rows[0]['id'],5,shown['immortal_artifacts']['revision'])
    saved=e._load(g.id)
    assert len(saved.player.crafted_artifacts)==1 and len([i for i in saved.player.inventory if i.crafted_artifact_id=='original-forge'])==1
    assert saved.player.crafted_artifacts[0]['immortal_grade']==4 and combat_power(saved.player)==power


def test_tianji_natal_does_not_bypass_equipment_or_dlc_switch(ready,monkeypatch):
    _,g=ready
    source=dict(id='held-divine',name='原神机',tianji={},force_tier=2)
    # A real Tianji carries nonempty template metadata.
    source['tianji']={'template_id':'fixture'}
    g.player.crafted_artifacts=[source];g.natal_artifact={'item_id':source['id'],'crafted_artifact_id':source['id'],'force_tier':2}
    assert ia.active_natal_tier(g)==1
    g.player.equipped_crafted_artifact_ids=[source['id']]
    monkeypatch.setitem(registry.WORLD_SYSTEMS,'tianji_artifacts',{'enabled':True})
    assert ia.active_natal_tier(g)==2
    monkeypatch.setitem(registry.WORLD_SYSTEMS,'tianji_artifacts',{'enabled':False})
    assert ia.active_natal_tier(g)==1


@pytest.mark.parametrize('busy',('event','trial','journey','prison','heavens'))
def test_busy_rejection_keeps_materials_and_original_file(ready,busy):
    e,g=ready;upper(e,g);add_item(g.player,immortal_item())
    if busy=='event':g.pending_event={'id':'test_pending'}
    elif busy=='trial':g.active_trial={'kind':'test'}
    elif busy=='journey':g.map_journey={'destination':'test'}
    elif busy=='prison':g.player.imprisonment={'kind':'test'}
    else:g.heavens_state={'runtime':{'tasks':[{'status':'paused','id':'test'}]}}
    before=(g.player.to_dict(),copy.deepcopy(g.natal_artifact),g.rng_state,g.updated_at,copy.deepcopy(g.history));rng=g.rng_state
    with pytest.raises(ValueError):ia.cultivate(g,'bag:'+immortal_item().id,5)
    assert (g.player.to_dict(),g.natal_artifact,g.rng_state,g.updated_at,g.history)==before and g.rng_state==rng


def test_missing_materials_and_guixu_context_are_rejected(ready):
    e,g=ready;upper(e,g);add_item(g.player,immortal_item())
    g.player.inventory=[i for i in g.player.inventory if i.id!=ia.MATERIALS[0][0]]
    before=g.to_dict()
    with pytest.raises(ValueError,match='三铸'):ia.cultivate(g,'bag:'+immortal_item().id,5)
    assert g.to_dict()==before
    g.guixu_state['player_session']={'dungeon_id':'real-instance'}
    assert not ia.public(g)['available']


def test_refined_equipment_auction_escrow_returns_original_once(ready):
    e,g=ready;upper(e,g);add_item(g.player,immortal_item());e.store.save(g)
    shown=e.get_game(g.id);row=shown['immortal_artifacts']['equipment'][0]
    e.immortal_artifact_action(g.id,row['id'],5,shown['immortal_artifacts']['revision'])
    g=e._load(g.id);item=next(i for i in g.player.inventory if i.artifact_origin_id)
    g.auction_state=dict(id='actual-escrow',status='scheduled',world=g.player.world,location_id=g.player.location_id,
                         location_name=e.maps.location(g.player.world,g.player.location_id)['name'],consignments=[],lots=[],actions_until_open=1)
    e.store.save(g)
    e.consign_auction_item(g.id,item.id)
    saved=e._load(g.id)
    assert not any(i.id==item.id for i in saved.player.inventory)
    assert saved.auction_state['consignments'][0]['item_instance']['immortal_grade']==4
    import random
    e._open_auction(saved,random.Random(1101))
    lot=next(r for r in saved.auction_state['lots'] if r['seller']=='player')
    assert lot['content_id']==item.id and lot['item_instance']['immortal_grade']==4
    e._cancel_auction_for_world_change(saved)
    returned=[i for i in saved.player.inventory if i.id==item.id]
    assert len(returned)==1 and returned[0].immortal_grade==4 and returned[0].quantity==1
    e._cancel_auction_for_world_change(saved)
    assert len([i for i in saved.player.inventory if i.id==item.id])==1


@pytest.mark.parametrize('world',('human','demon','spirit','true_demon','monster_realm','phantom_underworld','hell','celestial','asura','nether','reincarnation'))
def test_actual_existing_market_can_buy_each_local_first_material(ready,world):
    e,g=ready
    g.player.world=world;g.player.location_id=e.maps.default_location(world)
    g.player.realm_index=int(registry.WORLD_SYSTEMS['world_profiles'][world]['npc_realm_cap'])
    g.player.next_tribulation_age=None
    g.market_world=world;g.market_location_id=g.player.location_id;g.market_age=g.player.age;g.market_realm_index=g.player.realm_index
    key=ia.MATERIALS[0][0]
    offer=next(r for r in registry.MARKET_GOODS if r['content_id']==key and r['world']==world)
    g.market_offers=[dict(id='local-existing-source',kind='item',content_id=key,name=registry.ITEM_CATALOG[key].name,
                         description='本地真实来源',market_name='本地器材坊市',tier=offer['tier'],price=offer['price'],world=world,
                         location_id=g.player.location_id,sold=False,locked=False)]
    qty=next(i.quantity for i in g.player.inventory if i.id==key)
    money=next(i.quantity for i in g.player.inventory if i.id=='spirit_stone')
    e.store.save(g);e.buy_market_offer(g.id,'local-existing-source')
    saved=e._load(g.id)
    assert next(i.quantity for i in saved.player.inventory if i.id==key)==qty+1
    assert next(i.quantity for i in saved.player.inventory if i.id=='spirit_stone')==money-offer['price']

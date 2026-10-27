"""Creation, real persisted commerce, one-generation transfer and shared NPC combat."""
import copy
import random
from pathlib import Path
from unittest.mock import patch
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, SectNpc
from cultivation_life import content_registry as registry
from cultivation_life.rules import acquire_technique, add_item, technique_manual_item_id
from cultivation_life.system import authored_techniques as author
from cultivation_life.system.npc_techniques import learn, levels
from cultivation_life.system.combat_loadout import project_loadout
from cultivation_life.system.combat.contracts import resolve_source, Combatant
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.authored_technique_schema import EFFECTS, validate_library

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def ready(tmp_path):
    e=GameEngine(ROOT,tmp_path/'saves')
    g=e._load(e.create_game('著经验收','supreme_metal','dao',310,preset_id='core')['id'])
    g.pending_event=None
    for t in g.player.known_techniques:t.level=9
    add_item(g.player,'spirit_stone',10**10)
    e.store.save(g)
    return e,g

def design(name='回澜新经',effect='restore',level=1):
    return dict(name=name,grade=1,category='support',element='neutral',
        allocations=dict(opportunity_bonus=10,hp_bonus=10,mp_bonus=10,combat_bonus=10),
        buffs=[dict(slot='support',effect=effect,value=5,level=level,condition='from_round',round=3)])

def create(e,g,**kw):
    view=e.authored_technique_action(g.id,'create',dict(design=design(**kw),revision=g.authored_techniques.get('revision',0)))
    key=view['authored_techniques']['books'][-1]['id']
    return e.store.load(g.id),key

def black(e,g):
    g.pending_event=None
    g.auction_state=dict(id='authored-test-fair',status='black_market',world=g.player.world,
        location_id=g.player.location_id,location_name='验收会场',lots=[],attendees=[],black_market_results=[])
    add_item(g.player,'spirit_stone',10**10);e.store.save(g)

def test_creation_preview_points_manual_upgrade_reload_and_stale(ready):
    e,g=ready
    before=e.store.load(g.id).to_dict()
    q=e.authored_technique_action(g.id,'preview',dict(design=design()))
    assert q['cost']==85
    assert e.store.load(g.id).player.creation_insights=={}
    g,key=create(e,g)
    assert key not in registry.TECHNIQUE_CATALOG
    facts=author.insight_projection(g.player)
    assert facts['earned']==sum(10*t.grade**2*t.level**2 for t in g.player.known_techniques if t.id!=key)
    assert facts['spent']==85
    with pytest.raises(ValueError,match='更新'):
        e.authored_technique_action(g.id,'create',dict(design=design('第二经书'),revision=0))
    assert len(e.store.load(g.id).authored_techniques['own'])==1
    e.authored_technique_action(g.id,'manual',dict(id=key,level=1,revision=1))
    assert e.store.load(g.id).player.creation_insights['spent']==128
    e.upgrade_technique(g.id,key)
    g=e.store.load(g.id)
    assert next(t.level for t in g.player.known_techniques if t.id==key)==2
    assert author.insight_projection(g.player)['earned']==facts['earned']
    for t in g.player.known_techniques:
        if t.id!=key:t.level=8
    assert author.insight_projection(g.player)['earned']==facts['earned']
    assert GameState.from_dict(g.to_dict()).authored_techniques==g.authored_techniques

@pytest.mark.parametrize('change',[{'name':'a'}, {'grade':12}, {'allocations':{}}, {'name':next(iter(registry.TECHNIQUE_CATALOG.values())).name}, {'buffs':[dict(slot='support',effect='restore',value=11,level=1,condition='always',round=1)]}])
def test_invalid_command_does_not_spend(ready,change):
    e,g=ready;d=design();d.update(change)
    with pytest.raises(ValueError):e.authored_technique_action(g.id,'create',dict(design=d,revision=0))
    assert e.store.load(g.id).player.creation_insights=={}


def test_only_immediate_parent_own_books_and_source_is_frozen(ready):
    e,a=ready;a,first=create(e,a)
    b=e._load(e.create_game('第二世','supreme_metal','dao',311,preset_id='core',inherit_from=a.id)['id']);b.pending_event=None
    assert not any(t.id==first for t in b.player.known_techniques)
    for t in b.player.known_techniques:t.level=9
    e.store.save(b);b,second=create(e,b,name='次世新章')
    c=e._load(e.create_game('第三世','supreme_metal','dao',312,preset_id='core',inherit_from=b.id)['id'])
    assert set(author.definitions(c))=={second}
    a.authored_techniques['own'][first]['technique']['name']='修改源档';e.store.save(a)
    assert author.template(b,first).name=='回澜新经'
    assert not author.local_books(a)
    assert set(author.local_books(b))=={first}
    with pytest.raises(ValueError,match='这里只能'):e.authored_technique_action(b.id,'manual',dict(id=first,level=1,revision=1))


def test_black_market_real_buy_only_inherited_with_local_and_duplicate_guards(ready):
    e,a=ready;a,key=create(e,a);black(e,a)
    assert not any(r['content_id']==key for r in e.search_black_market(a.id,'回澜')['auction_system']['black_market_results'])
    b=e._load(e.create_game('后世','supreme_metal','dao',311,preset_id='core',inherit_from=a.id)['id']);black(e,b)
    view=e.search_black_market(b.id,'回澜');row=next(r for r in view['auction_system']['black_market_results'] if r['content_id']==key)
    e.buy_black_market_item(b.id,row['id'])
    assert next(t for t in e.store.load(b.id).player.known_techniques if t.id==key).level==1
    e.buy_black_market_item(b.id,row['id'])
    assert any(i.id==technique_manual_item_id(key,1) for i in e.store.load(b.id).player.inventory)
    b=e.store.load(b.id);b.auction_state['location_id']='wrong-place';e.store.save(b)
    with pytest.raises(ValueError,match='抵达'):e.buy_black_market_item(b.id,row['id'])


def test_fair_private_trade_records_real_npc_level_and_consumes_stock(ready):
    e,a=ready;a,key=create(e,a)
    b=e._load(e.create_game('后世','supreme_metal','dao',311,preset_id='core',inherit_from=a.id)['id']);b.pending_event=None
    add_item(b.player,'spirit_stone',10**10)
    b.auction_state=dict(id='test-fair',status='open',world=b.player.world,location_id=b.player.location_id,location_name='验收会场',lots=[],attendees=[],consignments=[],rank_band=[1,2,3])
    e._open_auction(b,random.Random(31))
    assert any(l['content_id']==key for l in b.auction_state['lots'])
    attendee=b.auction_state['attendees'][0];attendee['private_trade_unlocked']=True
    offer=next(o for o in attendee['trade_offers'] if o['content_id']==key)
    e.store.save(b);e.buy_private_trade_item(b.id,attendee['id'],offer['id'])
    b=e.store.load(b.id)
    assert any(t.id==key for t in b.player.known_techniques)
    with pytest.raises(ValueError,match='易主'):e.buy_private_trade_item(b.id,attendee['id'],offer['id'])
    eligible=[n for n in e._all_world_npcs(b) if key in levels(n)]
    assert eligible and all(1<=levels(n)[key]<=9 for n in eligible)

@pytest.mark.parametrize('effect',list(EFFECTS))
def test_effects_use_real_semantics_on_both_actors_with_slot_and_level_gates(ready,effect):
    e,g=ready;g,key=create(e,g,effect=effect,level=2)
    book=next(t for t in g.player.known_techniques if t.id==key)
    g.player.support_technique=book
    assert not author.combat_rules(g,g.player,player=True)
    book.level=2
    player=project_loadout(g,g.player,player=True)
    assert player.semantic_rules
    npc=SectNpc('buff-npc','试法女修','同道',3,1,50,500,spirit_root='supreme_metal',world='human')
    learn(npc,book,1,'support');assert not project_loadout(g,npc).semantic_rules
    learn(npc,book,2,'support');source=project_loadout(g,npc)
    assert source.semantic_rules==player.semantic_rules
    assert SectNpc.from_dict(npc.to_dict()).technique_levels[key]==2
    old=npc.family_combat_bonus;learn(npc,book,2,'support');assert npc.family_combat_bonus==old
    g.player.support_technique=None;g.player.technique=book
    assert not author.combat_rules(g,g.player,player=True)

@pytest.mark.parametrize('side',['player','enemy'])
def test_round_three_restores_five_percent_in_actual_battle(ready,side):
    e,g=ready;g,key=create(e,g)
    book=next(t for t in g.player.known_techniques if t.id==key);g.player.support_technique=book
    cap=resolve_source({}, {},project_loadout(g,g.player,player=True))
    actors=[Combatant(k,k,k,100,cap if k==side else resolve_source({}, {},project_loadout(g,SectNpc('n','甲','',1,1,20,100))),integrity=.5) for k in ['player','enemy']]
    battle=VoisinageBattle(actors)
    for n in range(1,5):
        battle.begin_round(n,player_condition=battle.units['player'].vitality,enemy_condition=battle.units['enemy'].vitality,player_mp=1,enemy_mp=1)
        assert battle.units[side].vitality==pytest.approx(.5+max(0,n-2)*.05)


def test_offline_dlc_rejects_creating_and_disables_buffs_without_erasing(ready):
    e,g=ready;g,key=create(e,g);g.player.support_technique=next(t for t in g.player.known_techniques if t.id==key)
    with patch.object(author,'enabled',return_value=False):
        assert not author.combat_rules(g,g.player,player=True)
        assert not author.local_books(g)
        with pytest.raises(ValueError,match='DLC'):author.create(g,design('不该成功'),1)
    assert key in author.definitions(g)


def test_inherited_definitions_reject_nonfinite_or_executable_extensions(ready):
    e,g=ready;g,key=create(e,g)
    for field,value in [('hp_bonus',float('nan')),('combat_interventions',[{}]),('grade',False)]:
        bad=copy.deepcopy(g.authored_techniques);bad['own'][key]['technique'][field]=value
        with pytest.raises(ValueError):validate_library(bad)


def test_anonymous_exchange_requires_real_materials_and_rejects_replay(ready):
    from cultivation_life.system.crafting_system import make_crafting_material_instance
    e,a=ready;a,key=create(e,a)
    b=e._load(e.create_game('换简后世','supreme_metal','dao',313,preset_id='core',inherit_from=a.id)['id']);b.pending_event=None
    rng=random.Random(310);e._schedule_exchange(b,rng);e._open_exchange(b,rng)
    b.player.location_id=b.exchange_state['location_id'];b.exchange_state['alias']='青笠客'
    offer=next(r for r in b.exchange_state['offers'] if r.get('manual_id')==key)
    demand=offer['demands'][0];selected=[]
    for _ in range(demand['quantity']):
        item=make_crafting_material_instance(e._crafting_material_defs()[demand['definition_id']],rng,source='测试',origin_world='human')
        b.player.crafting_materials.append(item);selected.append(dict(id=item['id'],quantity=1))
    e.store.save(b)
    e.exchange_action(b.id,'trade',dict(offer_id=offer['id'],materials=selected))
    after=e.store.load(b.id)
    assert any(t.id==key for t in after.player.known_techniques)
    assert not set(r['id'] for r in selected)&set(r['id'] for r in after.player.crafting_materials)
    with pytest.raises(ValueError,match='结束'):e.exchange_action(b.id,'trade',dict(offer_id=offer['id'],materials=selected))


def test_pending_event_blocks_creation_and_preview_without_spending(ready):
    e,g=ready
    g.pending_event=e._instantiate_event(e.events_by_id['EVT_XIANG_NODE_001'],g,random.Random(1));e.store.save(g)
    for action in ['create','preview']:
        with pytest.raises(ValueError,match='当前事件'):e.authored_technique_action(g.id,action,dict(design=design(),revision=0))
    assert e.store.load(g.id).player.creation_insights=={}


def test_all_supported_realms_quote_and_restrictions_disable_effects(ready):
    from cultivation_life.combat_semantics import SemanticRuntime
    e,g=ready
    g.player.known_techniques.append(copy.deepcopy(next(t for t in registry.TECHNIQUE_CATALOG.values() if t.grade==12)))
    for grade in range(1,13):
        d=design();d['grade']=grade
        assert author.quote(g.player,d)['technique']['grade']==grade
    g,key=create(e,g)
    g.player.support_technique=author.template(g,key)
    runtime=SemanticRuntime({'p':author.combat_rules(g,g.player,player=True)});runtime.begin_round(3)
    result=runtime.preview('p',None,'round_start',{'self.restricted_technique':True,'self.restricted_support':False})
    assert runtime.commit(result)==[]

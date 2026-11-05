"""School identity, conservation, clocks, old entry points and original actors."""
import copy
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

from cultivation_life.models import GameState, SectNpc
from cultivation_life.engine import GameEngine
from cultivation_life.engine.actions.mentorship import act
from cultivation_life.system import mentorship as m
from cultivation_life.system.npc_development import service
from cultivation_life.rules import add_item
from cultivation_life.content_registry import ITEM_CATALOG
from test_npc_development import game


@pytest.fixture
def school(game):
    teacher = SectNpc('teacher', '师父', '散修', 5, 8, 150, 1000,
                      spirit_root='supreme_metal', world='human', location_id='place', affinity=90)
    game.world_npcs[teacher.id] = teacher
    game.player.master = game.link_relationship({'id':teacher.id})
    return game


@pytest.fixture
def engine(game, tmp_path):
    e = GameEngine(Path(__file__).resolve().parents[1], tmp_path)
    # These domain tests exercise real persistence and command code; full UI
    # projection is covered by browser_mentorship.py against a valid map save.
    e.present = lambda g: m.public(g)
    e.store.save(game)
    return e


def run(game, action, **kwargs):
    saved = []
    engine = SimpleNamespace(_load=lambda _:game, store=SimpleNamespace(save=lambda g:saved.append(g.to_dict())),
                             present=m.public)
    return act(engine, game.id, action, **kwargs)


def test_reads_do_not_generate_peers_or_touch_rng(school):
    before = copy.deepcopy(school.to_dict())
    for _ in range(3):
        view = m.public(school)
        assert view['master']['rank'] == 'true' and view['peers'] == []
    assert school.to_dict() == before
    m.admit(school, 'teacher', 'player')
    assert len(m.rows(school, 'teacher')) == 3
    peers = set(school.notable_npcs)
    m.admit(school, 'teacher', 'player')
    restored = GameState.from_dict(school.to_dict())
    m.admit(restored, 'teacher', 'player')
    assert set(restored.notable_npcs) == peers
    assert restored.rng_state == before['rng_state']
    for key in peers:
        assert restored.notable_npcs[key].location_id == 'place'
        assert m.public(restored)['peers'][0]['portrait']['age'] >= 18


def test_unlimited_registered_but_hard_elite_caps(game):
    for i in range(12):
        n = SectNpc('extra'+str(i), '弟子', '', 1, 1, 20, 200, location_id='place')
        game.world_npcs[n.id] = n
        game.player.disciples.append(game.link_relationship({'id':n.id}))
        m.admit(game, 'player', n.id)
    ranks = [r['rank'] for r in m.rows(game, 'player').values()]
    assert ranks.count('true') == m.capacity(game, 'player', 'true')
    assert ranks.count('registered') == 13 - ranks.count('true')
    run(game, 'appoint', npc_id='student', rank='heir')
    before = copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError, match='名额'): run(game, 'appoint', npc_id='extra0', rank='heir')
    assert game.to_dict() == before
    for i in range(3): run(game, 'appoint', npc_id='extra'+str(i), rank='personal')
    with pytest.raises(ValueError, match='名额'): run(game, 'appoint', npc_id='extra3', rank='personal')
    game.player.sealed_cultivation = {'realm_index':8}
    assert m.capacity(game, 'player', 'true') == 8


def test_registered_cannot_claim_or_owe_but_can_voluntarily_honor(school):
    row = m.admit(school, 'teacher', 'player');row['rank'] = 'registered'
    before = copy.deepcopy(school.to_dict())
    for kind in ['consult', 'item', 'technique']:
        with pytest.raises(ValueError, match='记名'): m.request_support(school, kind)
    with pytest.raises(ValueError, match='记名'): run(school, 'fulfill')
    assert school.to_dict() == before
    school.player.age += row['period'];m.advance(school)
    assert row['discontent'] == 0
    run(school, 'honor')
    assert row['honored'] == row['cycle'] and row['merit'] == 0
    with pytest.raises(ValueError): run(school, 'honor')


def test_duplicate_master_and_cycle_rejected(school):
    m.admit(school, 'teacher', 'player')
    peer = next(key for key in m.rows(school, 'teacher') if key != 'player')
    assert '师承' in m.admission_reason(school, 'player', peer)
    assert '循环' in m.admission_reason(school, 'player', 'teacher')


@pytest.mark.parametrize('block', ['world', 'location', 'instance', 'dead', 'held', 'pending', 'trial', 'prison', 'trapped', 'assignment'])
def test_new_and_old_actions_reject_unreachable_without_mutation(school, block):
    m.admit(school, 'teacher', 'player')
    npc=school.world_npcs['teacher']
    if block=='world': npc.world='spirit'
    elif block=='location': npc.location_id='elsewhere'
    elif block=='instance':
        school.player.world=npc.world='lost'
        school.spatial_state={'current':'one','instances':{'one':{'npc_ids':[], 'location_id':'place'},'two':{'npc_ids':['teacher'], 'location_id':'place'}}}
    elif block=='dead': npc.alive=False
    elif block=='held': npc.roster_state='held'
    elif block=='pending': school.pending_event={'id':'pending'}
    elif block=='trial': school.active_trial={'id':'battle'}
    elif block=='prison': school.player.imprisonment={'id':'prison'}
    elif block=='trapped': school.guixu_state={'player_session':{'trapped':True}}
    else: school.wars=[dict(id='war',strategic_war_id='deployment',status='active',journeys={'army':[dict(person_id='teacher',phase='outbound')]})]
    before=copy.deepcopy(school.mentorship_state);op=school.player.opportunity
    with pytest.raises(ValueError): run(school,'fulfill')
    with pytest.raises(ValueError): m.request_support(school,'consult')
    assert school.mentorship_state==before and school.player.opportunity==op


def test_loyalty_cap_and_repeated_gift_return_cannot_farm(game):
    item=next(key for key,item in ITEM_CATALOG.items() if 'pill' in item.tags)
    relation=game.player.disciples[0]
    add_item(game.player,item,10)
    for _ in range(8): service.gift(game,'npc','student',item,relation)
    row=m.record(game,'player','student')
    assert row['loyalty']==62
    run(game,'collect',npc_id='student')
    service.gift(game,'npc','student',item,relation)
    assert row['loyalty']==54
    for index in range(30): m.benefit(game,'student','test'+str(index),4)
    assert row['benefit_gain']==12 and row['loyalty']==64


def test_support_uses_actual_unique_treasure(school):
    m.admit(school,'teacher','player')
    npc=school.world_npcs['teacher'];item_id=next(iter(ITEM_CATALOG));npc.treasure_item_id=item_id
    before=sum(i.quantity for i in school.player.inventory if i.id==item_id)
    m.request_support(school,'item')
    assert npc.treasure_looted and npc.treasure_item_id is None
    assert sum(i.quantity for i in school.player.inventory if i.id==item_id)==before+1
    row=m.record(school,'teacher','player');school.player.age+=row['period'];m.advance(school)
    with pytest.raises(ValueError,match='实际随身'): m.request_support(school,'item')


def test_fixed_clock_pause_warning_and_expulsion(school):
    row=m.admit(school,'teacher','player');row['rank']='heir'
    period=row['period'];due=row['due']
    school.world_npcs['teacher'].world='spirit'
    school.player.age+=100;m.advance(school)
    assert row['due']==due+100 and row['discontent']==0
    school.world_npcs['teacher'].world='human'
    for expected in [45,90]:
        school.player.age+=period;m.advance(school)
        assert row['discontent']==expected and school.player.master
    assert row['warned']
    before=copy.deepcopy(row);m.advance(school);assert row==before
    school.player.age+=period;m.advance(school)
    assert row['status']=='expelled' and school.player.master is None


def test_duty_and_promotion_preserve_cycles(school):
    row=m.admit(school,'teacher','player')
    row['merit']=2
    due=row['due'];period=row['period']
    run(school,'fulfill');assert row['fulfilled']==0
    with pytest.raises(ValueError): run(school,'fulfill')
    run(school,'promote')
    assert row['rank']=='personal' and row['due']==due and row['period']==period
    with pytest.raises(ValueError): run(school,'promote')


def test_graduation_keeps_original_growth_and_no_active_seat(game):
    npc=game.world_npcs['student'];before=npc.to_dict()
    run(game,'graduate',npc_id=npc.id)
    assert not game.player.disciples and npc.to_dict()==before
    assert m.record(game,'player',npc.id)['status']=='graduated'
    assert not m.rows(game,'player')


def test_invalid_ledger_fails_load_and_read_roundtrip(school):
    m.admit(school,'teacher','player')
    raw=school.to_dict()
    assert GameState.from_dict(raw).mentorship_state==school.mentorship_state
    raw=copy.deepcopy(raw);raw['mentorship_state']['schools']['teacher']['students']['player']['loyalty']=101
    with pytest.raises(ValueError): GameState.from_dict(raw)


def test_registered_bypass_through_party_and_friend_is_rejected(engine, game):
    npc=game.world_npcs['student'];game.player.master=game.link_relationship({'id':npc.id});game.player.disciples=[]
    m.admit(game,npc.id,'player')['rank']='registered'
    game.player.dao_friends=[game.link_relationship({'id':npc.id})]
    engine.store.save(game)
    for action in ['invite','interact']:
        with pytest.raises(ValueError,match='记名'): engine.manage_party(game.id,npc.id,action)
    for action in ['discuss','spar']:
        with pytest.raises(ValueError,match='记名'): engine.manage_dao_friend(game.id,npc.id,action)


@pytest.mark.parametrize('win',[True,False])
def test_contest_uses_real_nonlethal_battle_and_swap(school, tmp_path, win):
    engine=GameEngine(Path(__file__).resolve().parents[1],tmp_path)
    engine.present=lambda g:m.public(g)
    row=m.admit(school,'teacher','player');row.update(rank='personal',merit=5)
    rival_id=next(key for key in m.rows(school,'teacher') if key!='player')
    m.record(school,'teacher',rival_id)['rank']='heir'
    rival=school.notable_npcs[rival_id];rival.realm_index=0;rival.layer=1
    if not win:
        rival.realm_index=8;rival.combat_factor=1000;school.player.realm_index=1
    from cultivation_life.rules import max_hp,max_mp
    school.player.hp=max_hp(school.player);school.player.mp=max_mp(school.player)
    engine.store.save(school)
    loaded=engine._load(school.id)
    for npc in [*loaded.world_npcs.values(),*loaded.notable_npcs.values()]: npc.location_id=loaded.player.location_id
    engine.store.save(loaded)
    result=engine.mentorship_action(school.id,'promote',rival_id=rival_id)
    saved=engine.store.load(school.id)
    assert result['master']['rank']==('heir' if win else 'personal')
    assert m.record(saved,'teacher',rival_id)['rank']==('personal' if win else 'heir')
    assert saved.player.alive and saved.notable_npcs[rival_id].alive
    assert saved.last_combat_report and saved.last_combat_report.get('rounds')


def test_graduation_and_reentry_preserve_original_gifts_without_duplication(game):
    item=next(iter(ITEM_CATALOG));relation=game.player.disciples[0]
    relation['items']={item:2};relation['breakthrough_bonus']=.2
    run(game,'graduate',npc_id='student')
    row=m.record(game,'player','student')
    assert row['former_relation']['items']=={item:2}
    assert not game.player.disciples
    game.player.disciples.append(game.link_relationship({'id':'student'}))
    m.admit(game,'player','student')
    assert 'former_relation' not in row
    assert game.player.disciples[0]['items']=={item:2}
    assert game.player.disciples[0]['breakthrough_bonus']==.2
    assert row['rank']=='registered'


def test_peer_conflict_is_bounded_and_registered_has_no_passive_obligation(school):
    row=m.admit(school,'teacher','player');row['rank']='registered'
    peer=next(k for k in m.rows(school,'teacher') if k!='player')
    for _ in range(10):m.displease(school,peer)
    assert row['discontent']==15 and row['discord_gain']==15
    school.player.age+=row['period'];m.advance(school)
    assert row['discontent']==15
    run(school,'honor');assert row['discontent']==5


def test_historical_regional_replay_cannot_punish_player(school):
    from cultivation_life.regional_context import CalendarGame
    row=m.admit(school,'teacher','player')
    school.player.age+=row['period']*4
    before=copy.deepcopy(row)
    m.advance(CalendarGame(school,'human',school.player.age-1))
    m.advance(CalendarGame(school,'spirit',school.player.age))
    assert row==before


def test_real_time_command_advances_school_clock(tmp_path):
    engine=GameEngine(Path(__file__).resolve().parents[1],tmp_path)
    shown=engine.create_game('学徒时钟','supreme_metal','dao',574,custom_start=dict(world='human',realm_index=1,sect=''))
    game=engine.store.load(shown['id']);p=game.player
    npc=SectNpc('clock-teacher','时钟师父','',2,3,35,400,world=p.world,location_id=p.location_id,spirit_root=p.spirit_root)
    game.notable_npcs[npc.id]=npc;p.master=game.link_relationship({'id':npc.id});game.pending_event=None
    row=m.admit(game,npc.id,'player');row['due']=p.age+1
    engine.store.save(game)
    engine.advance(game.id,'cultivate')
    after=engine.store.load(game.id)
    assert m.record(after,npc.id,'player')['cycle']>=1


def test_random_disciple_event_caps_pending_letters_not_all_students(engine, game):
    for index in range(10):
        npc=SectNpc('event-student'+str(index),'弟子','',1,1,20,200,location_id='place')
        game.world_npcs[npc.id]=npc;game.player.disciples.append(game.link_relationship({'id':npc.id}))
    event=engine.events_by_id['EVT_DISCIPLE_ENCOUNTER_001']
    assert engine._condition(event['conditions'],game)
    game.player.disciple_requests=[{'id':'pending'+str(i)} for i in range(8)]
    assert not engine._condition(event['conditions'],game)


@pytest.mark.parametrize('kind',['lost','secluded'])
def test_real_isolated_training_pauses_outside_master_obligations(tmp_path,kind):
    from test_npc_development_special_areas import make_game, enter_rift
    engine=GameEngine(Path(__file__).resolve().parents[1],tmp_path)
    game=make_game(engine);game.player.disciples=[]
    npc=game.notable_npcs.get('outside-student') or game.world_npcs.get('outside-student')
    if npc is None:
        from cultivation_life.relationship_records import find_person
        npc=find_person(game,'outside-student')
    game.player.master=game.link_relationship({'id':npc.id});m.admit(game,npc.id,'player')
    engine.store.save(game)
    game=enter_rift(engine,game,kind)
    before=copy.deepcopy(m.record(game,npc.id,'player'));age=game.player.age
    engine.advance(game.id,'cultivate')
    after=engine.store.load(game.id);row=m.record(after,npc.id,'player')
    assert after.player.age>age
    assert row['last_tick']==after.player.age
    assert row['due']>=before['due']+(after.player.age-age)
    assert row['discontent']==before['discontent']

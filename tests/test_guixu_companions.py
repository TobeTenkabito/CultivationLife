import random
from unittest.mock import patch, Mock

import pytest

from test_family_expansion import engine
from cultivation_life.content_registry import GUIXU_TIDE_CONTENT


@pytest.fixture
def expedition(engine):
    gid = engine.create_game('临时同行', 'supreme_water', 'dao', 260, 'water')['id']
    game = engine.store.load(gid)
    dungeon = next(d for d in GUIXU_TIDE_CONTENT['dungeons'] if d['world']=='human')
    cycle = game.guixu_state['cycles'][dungeon['id']]
    engine._open_guixu_cycle(game, dungeon, cycle, random.Random(260))
    game.pending_event = None
    game.player.location_id = dungeon['entry_location_id']
    game.player.realm_index = 1
    game.player.layer = 1
    engine.store.save(game)
    return gid, dungeon


def enter_team(engine, expedition):
    gid, dungeon = expedition
    shown = engine.guixu_action(gid, 'enter', {'dungeon_id':dungeon['id']})
    assert shown['guixu_tide']['session']['pending_team_offer']
    engine.guixu_action(gid, 'team_accept', {})
    game = engine.store.load(gid)
    cycle = game.guixu_state['cycles'][dungeon['id']]
    session = game.guixu_state['player_session']
    actor = next(a for a in cycle['roster'] if a['actor_id'] in session['recruited_actor_ids'])
    return game, cycle, session, actor


def give_player_treasure(engine, game, dungeon, cycle):
    item_ids = {d['id'] for d in dungeon['treasure_pool'] if d['kind']=='item'}
    row = next(r for r in cycle['round_entries'] if r['pool_entry_id'] in item_ids)
    engine._guixu_grant_entry(game, dungeon, row, 'test')
    return row


def test_only_solo_player_gets_offer_and_response_takes_no_time(engine, expedition):
    gid, dungeon = expedition
    game = engine.store.load(gid)
    cycle = game.guixu_state['cycles'][dungeon['id']]
    session = {'layer_id':'outer'}
    game.player.party = [{'id':'friend'}]
    engine._guixu_offer_team(game, cycle, session)
    assert not session.get('pending_team_offer')
    game.player.party = []
    game.player.realm_index = 8
    engine._guixu_offer_team(game, cycle, session)
    assert not session.get('pending_team_offer')
    game, cycle, session, actor = enter_team(engine, expedition)
    assert (actor['realm_index'],actor['layer']) > (game.player.realm_index,game.player.layer)
    assert session['remaining_days'] == dungeon['window_days']-1
    assert not session.get('action_serial')
    assert not session.get('pending_team_offer')


def test_same_major_realm_higher_layer_can_invite(engine, expedition):
    gid, dungeon = expedition
    game=engine.store.load(gid)
    cycle={'phase':'open','roster':[{'actor_id':'senior','status':'active','name':'前辈','realm_index':1,'layer':2}]}
    session={}
    engine._guixu_offer_team(game,cycle,session)
    assert session['pending_team_offer']['actor_id']=='senior'


def test_legacy_carried_treasure_starts_clock_when_invitation_is_accepted(engine, expedition):
    gid, dungeon=expedition
    engine.guixu_action(gid,'enter',{'dungeon_id':dungeon['id']})
    game=engine.store.load(gid);cycle=game.guixu_state['cycles'][dungeon['id']]
    give_player_treasure(engine,game,dungeon,cycle)
    game.guixu_state['player_session'].pop('player_ever_claimed')
    engine.store.save(game);engine.guixu_action(gid,'team_accept',{})
    with patch.object(engine,'_assign_due_guixu_entries'),patch.object(engine,'_maybe_guixu_npc_threat'), \
         patch.object(engine,'_guixu_fight',return_value=('victory_escape','脱身')) as fight:
        for _ in range(2):
            engine.guixu_action(gid,'rest',{});assert not fight.called
        engine.guixu_action(gid,'rest',{});assert fight.call_count==1


def test_betrayal_on_third_subsequent_action_and_reading_does_not_advance(engine, expedition):
    gid, dungeon = expedition
    game, cycle, session, actor = enter_team(engine, expedition)
    give_player_treasure(engine, game, dungeon, cycle)
    engine._guixu_team_tick(game, dungeon, cycle, session, random.Random(1))
    engine.store.save(game)
    with patch.object(engine, '_assign_due_guixu_entries'), patch.object(engine, '_maybe_guixu_npc_threat'), \
         patch.object(engine, '_guixu_fight', return_value=('victory_escape','脱身')) as fight:
        engine.get_game(gid); engine.get_game(gid)
        assert engine.store.load(gid).guixu_state['player_session']['action_serial']==1
        for index in range(2):
            engine.guixu_action(gid, 'rest', {})
            assert not fight.called
        engine.guixu_action(gid, 'rest', {})
        assert fight.call_count==1
        assert fight.call_args.kwargs == {'player_defending':True,'enemy_first_round':True}
    game = engine.store.load(gid)
    assert actor['actor_id'] not in game.guixu_state['player_session']['recruited_actor_ids']
    assert any(h.event_id=='SYS_GUIXU_TEAM_BETRAYAL' for h in game.history)


def test_gifting_transfers_real_inventory_and_prevents_betrayal(engine, expedition):
    gid, dungeon = expedition
    game, cycle, session, actor = enter_team(engine, expedition)
    row = give_player_treasure(engine, game, dungeon, cycle)
    content_id = engine._guixu_entry_definition(dungeon,row['pool_entry_id'])['content_id']
    before = sum(i.quantity for i in game.player.inventory if i.id==content_id)
    engine._guixu_team_tick(game, dungeon, cycle, session, random.Random(1))
    engine.store.save(game)
    shown = engine.guixu_action(gid, 'gift_treasure', {'actor_id':actor['actor_id'],'pool_entry_id':row['pool_entry_id']})
    assert shown['guixu_tide']['session']['action_serial']==1
    game = engine.store.load(gid)
    assert sum(i.quantity for i in game.player.inventory if i.id==content_id)==before-1
    with patch.object(engine,'_assign_due_guixu_entries'), patch.object(engine,'_maybe_guixu_npc_threat'), \
         patch.object(engine,'_guixu_fight') as fight:
        for _ in range(4):engine.guixu_action(gid,'rest',{})
        assert not fight.called
    with pytest.raises(ValueError, match='可转移'):
        engine.guixu_action(gid, 'gift_treasure', {'actor_id':actor['actor_id'],'pool_entry_id':row['pool_entry_id']})


def test_threats_leave_a_full_action_gap(engine, expedition):
    gid, dungeon = expedition
    engine.guixu_action(gid,'enter',{'dungeon_id':dungeon['id']})
    engine.guixu_action(gid,'team_decline',{})
    game = engine.store.load(gid)
    cycle = game.guixu_state['cycles'][dungeon['id']]
    session = game.guixu_state['player_session']
    give_player_treasure(engine,game,dungeon,cycle)
    for actor in cycle['roster']:
        actor.update(status='active',realm_index=2,layer_id='outer')
    rng=Mock();rng.random.return_value=0
    session['threat_cooldown']=1
    engine._maybe_guixu_npc_threat(game,dungeon,cycle,session,rng)
    assert not session.get('pending_threat')
    engine._maybe_guixu_npc_threat(game,dungeon,cycle,session,rng)
    assert session['pending_threat']
    engine.store.save(game)
    engine.guixu_action(gid,'threat_surrender',{})
    session=engine.store.load(gid).guixu_state['player_session']
    assert session['threat_cooldown']==1 and not session.get('pending_threat')


def test_first_round_betrayal_initiative_overrides_player_speed(engine, expedition):
    gid, _ = expedition
    game=engine.store.load(gid)
    engine._combat(game, {'target_name':'背刺修士','target_power':1,'target_realm_index':1,
        'target_layer':1,'combat_type':'cultivator','path':'dao','action':'spar',
        'enemy_first_round':True}, False, random.Random(17))
    assert game.last_combat_report['rounds'][0]['initiative']=='enemy'

"""Real commands, original peer assets, cooldowns and contact boundaries."""
import copy
from pathlib import Path

import pytest

from test_mentorship_adversarial import live
from cultivation_life.models import SectNpc, GameState
from cultivation_life.content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG
from cultivation_life.rules import can_player_practice_technique, opportunity_required
from cultivation_life.system import mentorship as m
from cultivation_life.system.npc_techniques import learn


@pytest.fixture
def peers(live):
    engine, game, _ = live
    p = game.player
    teacher = SectNpc('peer-teacher', '同门师父', '', 5, 8, 150, 1000,
                      world=p.world, location_id=p.location_id, spirit_root=p.spirit_root)
    game.world_npcs[teacher.id] = teacher
    p.master = game.link_relationship({'id':teacher.id})
    m.admit(game, teacher.id, 'player')
    npc = m.person(game, next(k for k in m.rows(game, teacher.id) if k != 'player'))
    npc.affinity = 60
    npc.treasure_item_id = next(iter(ITEM_CATALOG));npc.treasure_looted = False
    known = {t.id for t in p.known_techniques}
    art = next(t for t in TECHNIQUE_CATALOG.values() if t.id not in known and can_player_practice_technique(p, t))
    learn(npc, art)
    p.opportunity = 0
    engine.store.save(game)
    return engine, game, npc, art


def test_all_peer_commands_transfer_original_assets_and_animate(peers):
    engine, game, npc, art = peers
    item_id = npc.treasure_item_id
    quantity = sum(i.quantity for i in game.player.inventory if i.id == item_id)
    reward = round(max(1, opportunity_required(game.player) * .01), 1)
    for action in m.PEER_ACTIONS:
        engine.mentorship_action(game.id, action, npc.id)
    saved = engine.store.load(game.id)
    assert saved.player.opportunity == reward * 2
    original = m.person(saved, npc.id)
    assert original.treasure_looted and original.treasure_item_id is None
    assert sum(i.quantity for i in saved.player.inventory if i.id == item_id) == quantity + 1
    assert art.id in {t.id for t in saved.player.known_techniques}
    assert art.id in original.technique_levels
    assert original.alive and saved.player.alive
    report = saved.last_combat_report
    assert [u['id'] for u in report['visual']['teams']['hero']] == ['player']
    assert report['visual']['teams']['npc'][0]['id'] == npc.id
    assert report['visual']['teams']['npc'][0]['asset']
    assert m.record(saved, 'peer-teacher', 'player')['rank'] == 'true'
    assert m.record(saved, 'peer-teacher', 'player')['support_used'] == 0
    before = copy.deepcopy(saved.to_dict())
    for action in m.PEER_ACTIONS:
        with pytest.raises(ValueError, match='本周期'):
            engine.mentorship_action(game.id, action, npc.id)
    assert engine.store.load(game.id).to_dict() == before


@pytest.mark.parametrize('change', [
    lambda g,n:setattr(n, 'world', 'spirit'),
    lambda g,n:setattr(n, 'location_id', 'remote'),
    lambda g,n:setattr(n, 'alive', False),
    lambda g,n:setattr(n, 'affinity', -1),
    lambda g,n:m.record(g,'peer-teacher','player').update(rank='registered'),
    lambda g,n:m.record(g,'peer-teacher',n.id).update(rank='registered'),
    lambda g,n:m.record(g,'peer-teacher',n.id).update(joined=g.player.age+1),
    lambda g,n:setattr(g,'pending_event',{'id':'EVT_MASTER_ENCOUNTER_001'}),
    lambda g,n:g.guixu_state.update(player_session={'trapped':True}),
    lambda g,n:setattr(g.player,'master',None),
    lambda g,n:setattr(n,'roster_state','held'),
    lambda g,n:setattr(g,'active_trial',{'id':'battle'}),
    lambda g,n:setattr(g,'wars',[dict(id='war',strategic_war_id='deployment',status='active',
                                    journeys={'army':[dict(person_id=n.id,phase='outbound')]})]),
])
def test_peer_boundary_rejects_without_any_mutation(peers, change):
    engine, game, npc, _ = peers
    change(game,npc)
    before = copy.deepcopy(game.to_dict())
    import random
    for action in m.PEER_ACTIONS:
        with pytest.raises(ValueError): m.interact_peer(engine,game,npc.id,action,random.Random(1))
    assert game.to_dict() == before


@pytest.mark.parametrize('world',['lost','rift'])
def test_same_space_type_different_instance_is_not_contact(peers,world):
    engine,game,npc,_ = peers
    game.player.world = npc.world = world
    site = game.player.location_id
    game.spatial_state = {'current':'one','instances':{
        'one':{'kind':world,'npc_ids':[],'location_id':site},
        'two':{'kind':world,'npc_ids':[npc.id],'location_id':site}}}
    import random
    before = copy.deepcopy(game.to_dict())
    for action in m.PEER_ACTIONS:
        with pytest.raises(ValueError,match='空间'):
            m.interact_peer(engine,game,npc.id,action,random.Random(1))
    assert game.to_dict() == before


def test_reads_are_pure_and_missing_assets_do_not_consume_quota(peers):
    engine, game, npc, _ = peers
    npc.treasure_item_id = None;npc.technique_levels = {};npc.main_technique_id = None
    before = copy.deepcopy(game.to_dict())
    for _ in range(2):
        view = m.public(game)
        peer = next(r for r in view['peers'] if r['id'] == npc.id)
        assert peer['kinship'] == '师兄'
        assert all(r['reason'] for r in peer['interactions'] if r['action'] in {'peer_item','peer_technique'})
    import random
    for action in ['peer_item','peer_technique']:
        with pytest.raises(ValueError): m.interact_peer(engine,game,npc.id,action,random.Random(1))
    assert game.to_dict() == before


def test_cycle_persists_across_rank_change_rejoin_and_save(peers):
    engine, game, npc, _ = peers
    engine.mentorship_action(game.id, 'peer_consult', npc.id)
    saved = engine.store.load(game.id)
    row = m.record(saved,'peer-teacher','player');row['rank'] = 'heir'
    assert '本周期' in m.peer_reason(saved,npc.id,'peer_consult')
    m.end(saved,'peer-teacher','player','departed')
    saved.player.master = saved.link_relationship({'id':'peer-teacher'})
    m.admit(saved,'peer-teacher','player')['rank'] = 'true'
    saved = GameState.from_dict(saved.to_dict())
    assert '本周期' in m.peer_reason(saved,npc.id,'peer_consult')
    row = m.record(saved,'peer-teacher','player')
    saved.player.age += row['period'];m.advance(saved)
    assert not m.peer_reason(saved,npc.id,'peer_consult')


@pytest.mark.parametrize('value', [True, -1, 99, '0'])
def test_invalid_peer_receipts_rejected(peers,value):
    _,game,npc,_ = peers
    m.record(game,'peer-teacher','player')['peer_requests'] = {npc.id:{'peer_consult':value}}
    with pytest.raises(ValueError,match='同门交流'): GameState.from_dict(game.to_dict())


def test_debug_peer_command_uses_same_receipt_without_changing_source(peers,tmp_path):
    from cultivation_life.debug.runtime import Runtime
    engine,game,npc,_ = peers
    runtime = Runtime(Path(__file__).resolve().parents[1],tmp_path/'debug',engine.store)
    sid = runtime.start(game.id)['session_id']
    source = engine.store._path(game.id).read_bytes()
    args = {'action':'peer_consult','npc_id':npc.id}
    result = runtime.execute('mentorship action',session_id=sid,arguments=args,
                             expected_revision=runtime.load(sid)['revision'],request_key='consult')
    assert result
    current = GameState.from_dict(runtime.load(sid)['current']['game'])
    assert current.player.opportunity > 0
    assert m.peer_reason(current,npc.id,'peer_consult').startswith('本周期')
    assert engine.store._path(game.id).read_bytes() == source


def test_late_registration_does_not_turn_existing_peers_into_juniors(live):
    _,game,_ = live
    teacher = SectNpc('late-master','师父','',5,8,150,1000,world=game.player.world,
                      location_id=game.player.location_id,spirit_root=game.player.spirit_root)
    game.world_npcs[teacher.id] = teacher
    game.player.master = game.link_relationship({'id':teacher.id})
    own = m._admit(game,teacher.id,'player')
    joined = own['joined'];game.player.age += 30
    m.admit(game,teacher.id,'player')
    for row in m.public(game)['peers']:
        assert row['joined'] == joined
        assert row['kinship'] in {'师兄','师姐'}
        assert not m.peer_reason(game,row['id'],'peer_consult')

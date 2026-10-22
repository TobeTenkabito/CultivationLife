"""Disposable real references, original item commands and real settled group CG."""
import random

from cultivation_life.rules import add_item, max_hp, max_mp
from cultivation_life.system.tianji_system import tianji_content_available


def prepare_alpha2(engine, identity, kind='replica', enabled=None):
    game = engine.store.load(identity)
    game.pending_event = None
    game.settings.update(silent_events=True, combat_popup=True)
    npc = next(n for n in game.world_npcs.values() if n.alive and n.world==game.player.world)
    npc.name = '验收持宝道友'
    npc.affinity = 100
    game.player.dao_friends = []
    add_item(game.player, 'starfall_blade', 10000)
    for category in ('equipment','consumable','plant','material'):
        add_item(game.player, f'guixu_canghai_{category}_01', 2)
    game.player.hp,game.player.mp = max_hp(game.player)*.1,max_mp(game.player)*.1
    artifact_id = None
    if tianji_content_available() and enabled is not False:
        artifact = next(a for a in reversed(game.tianji_state['artifacts']) if a['origin_world']==game.player.world)
        artifact_id = artifact['id']
        game.tianji_state['holders'] = {artifact_id:dict(npc_id=npc.id,world=game.player.world,kind=kind,replica_ratio=.4 if kind=='replica' else 1.)}
        if kind=='true_body':
            game.tianji_state['true_body_states'][artifact_id] = dict(status='npc',holder_ref=npc.id)
        game.tianji_state['knowledge'][artifact_id] = 4
    engine.store.save(game)
    return dict(id=identity,artifact_id=artifact_id,npc_id=npc.id,kind=kind)


def inspect_alpha2(engine, expected):
    game = engine.store.load(expected['id'])
    assert game.last_combat_report and game.last_combat_report['rounds']
    assert expected['npc_id'] in {r['id'] for r in game.last_combat_report['enemy_roster']}
    if expected['artifact_id']:
        assert game.tianji_state['knowledge'][expected['artifact_id']] == 5
        clues=[r for r in game.tianji_state['discovery_log'] if r['artifact_id']==expected['artifact_id'] and '实际交战' in r['source']]
        assert len(clues)==1 and clues[0]['from']==4 and clues[0]['to']==5
    return game


def prepare_alpha2_group(engine, identity):
    game = engine.store.load(identity)
    game.pending_event = None
    game.settings.update(silent_events=True,combat_popup=True)
    game.player.dao_friends = []
    # This scenario is independent of the single-opponent intelligence check.
    game.tianji_state['holders'] = {}
    power = engine._player_battle_power(game)
    game.player.puppets = [dict(id='alpha2-corpse',name='炼尸',type='corpse',gender='female',
        combat_power=power*.2,realm_index=game.player.realm_index,alive=True,corpse_integrity=100,control=100),
        dict(id='alpha2-mechanism',name='机关',type='mechanical',combat_power=power*.2,
        realm_index=game.player.realm_index,alive=True,durability=100)]
    total = sum(u.power*u.integrity for u in engine._player_combat_units(game))
    target = dict(target_name='三方联合演武',target_power=total*20,target_realm_index=game.player.realm_index,
        combat_type='cultivator',max_rounds=2,members=[dict(npc_id=f'alpha2-opponent-{i}',name=f'对手{i}',
        power=total*20/3,gender=('male','female','male')[i],path='dao') for i in range(3)])
    engine._combat(game,target,False,random.Random(151))
    engine.store.save(game)

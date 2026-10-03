"""Run inside the signed Android test APK; creates only named verification saves."""
import copy
import json

from cultivation_life.server import ENGINE
from cultivation_life.npc_custody import is_free
from cultivation_life.save_schema import SAVE_SCHEMA_VERSION

created = ENGINE.create_game('受控状态验收', 'supreme_fire', 'demonic', seed=1570)
game = ENGINE.store.load(created['id'])
game.pending_event = None
game.player.realm_index = 4
game.player.layer = 1
npc = next(n for n in game.world_npcs.values() if n.alive and n.world == game.player.world)
npc.realm_index, npc.layer, npc.gender = 1, 1, 'female'
game.player.dao_friends = [game.link_relationship({'id': npc.id, 'source': 'world'})]
game.player.prisoners = [game.detain_person({'id': npc.id, 'source': 'combat', 'combat_power': 1})]
assert npc.alive and not is_free(npc) and game.player.dao_friends[0]['alive']
ENGINE.store.save(game)
loaded = ENGINE.store.load(game.id)
assert loaded.version == SAVE_SCHEMA_VERSION == 8
assert loaded.player.prisoners[0].person is loaded.player.dao_friends[0].person
assert ENGINE._find_npc(loaded, npc.id) is None
assert loaded.inactive_npcs[npc.id].custody['kind'] == 'prisoner'

# Exercise the actual device's on-disk 6/7 -> 8 path, keeping the original ID.
canonical = loaded.to_dict()
for version in (6, 7):
    old = copy.deepcopy(canonical)
    old['version'] = version
    person = old.pop('inactive_npcs')[npc.id]
    person.update(alive=False, death_reason='被玩家生擒')
    for field in ('roster_state', 'custody', 'roster_origin'):
        person.pop(field, None)
    old['world_npcs'][npc.id] = person
    old['player']['prisoners'] = [dict(id=npc.id, npc_id=npc.id, name=npc.name,
        alive=True, world=npc.world, source='combat', body_training=42, combat_power=1)]
    ENGINE.store._path(game.id).write_text(json.dumps(old), encoding='utf-8')
    migrated = ENGINE.store.load(game.id)
    assert migrated.version == 8 and migrated.inactive_npcs[npc.id].alive
    assert migrated.player.prisoners[0]['body_training'] == 42
    assert json.loads(ENGINE.store._path(game.id).read_bytes())['version'] == 8

ENGINE.captive_action(game.id, npc.id, 'release')
released = ENGINE.store.load(game.id)
assert is_free(ENGINE._find_npc(released, npc.id))
assert ENGINE._find_npc(released, npc.id).body_training == 42
assert not released.player.prisoners

# A rejected schema 5 file remains byte-for-byte intact on the device.
legacy = released.to_dict()
legacy['version'] = 5
path = ENGINE.store._path(game.id)
path.write_text(json.dumps(legacy), encoding='utf-8')
original = path.read_bytes()
try:
    ENGINE.store.load(game.id)
except ValueError:
    pass
else:
    raise AssertionError('Unsupported schema 5 was accepted')
assert path.read_bytes() == original
ENGINE.store.save(released)

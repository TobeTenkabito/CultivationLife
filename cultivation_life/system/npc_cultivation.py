"""Deterministic NPC cultivation defaults and coordinate limits."""
import hashlib
from ..cultivation_coordinates import rank_for, body_rank


def ensure_npc(npc):
    from .combat.actor_state import read, _write
    realm, layer = read(npc, 'realm_index', 0), read(npc, 'layer', 1)
    seed = 0
    if read(npc, 'body_training') is None or read(npc, 'divine_sense_rank') is None or (realm>=10 and not read(npc,'immortal_body_level',0)):
        seed = int.from_bytes(hashlib.blake2s(str(read(npc, 'id', '')).encode(), digest_size=4).digest(), 'big')
    if read(npc, 'body_training') is None:
        ceiling = min(100, rank_for(min(8, realm), layer))
        _write(npc, 'body_training', seed % (ceiling + 1))
    if read(npc, 'divine_sense_rank') is None:
        _write(npc, 'divine_sense_rank', rank_for(realm, layer) + seed % 9)
    else:
        _write(npc, 'divine_sense_rank', max(read(npc, 'divine_sense_rank'), rank_for(realm, layer)))
    if realm >= 10:
        _write(npc, 'body_training', 100)
        if not read(npc,'immortal_body_level',0):
            stage=min(2,max(0,(layer-1)//3))
            starts={10:(13,17,21),11:(25,29,33),12:(37,41,46)}
            ends={10:(16,20,24),11:(28,32,36),12:(40,45,50)}
            low,high=starts[min(12,realm)][stage],ends[min(12,realm)][stage]
            _write(npc,'immortal_body_level',low+seed%(high-low+1))


def npc_voisinage_limit(npc):
    """Only rare late true immortals have a field. Stable identity, no rerolls."""
    from .combat.actor_state import read
    realm = read(npc, 'realm_index', 0)
    if realm > 9:
        return 9
    if realm < 9 or read(npc, 'layer', 1) < 7:
        return 3
    seed = int.from_bytes(hashlib.blake2s(('voisinage:' + str(read(npc, 'id', ''))).encode(), digest_size=4).digest(), 'big')
    return 5 if seed % 100 < 12 else 3


def npc_golden_light(npc):
    from .combat.actor_state import read
    return int(read(npc, 'immortal_body_level', 0) or 0)>=10

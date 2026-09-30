"""Independent cultivation, body and sense coordinates. No annual simulation."""
import hashlib

# Inclusive starts: mortal 0–3; qi 4–16; seven 12-rank realms through 100.
STARTS = (0, 4, 17, 29, 41, 53, 65, 77, 89, 101, 128, 155, 182)
NAMES = ('凡人', '炼气', '筑基', '结丹', '元婴', '化神', '炼虚', '合体', '大乘', '真仙', '金仙', '太乙', '大罗')


def rank_for(realm, layer=1):
    realm = max(0, min(12, realm))
    width = (STARTS[realm + 1] if realm < 12 else 209) - STARTS[realm]
    layers = 1 if realm == 0 else 13 if realm == 1 else 9
    return STARTS[realm] + min(width - 1, max(0, layer - 1) * width // layers)


def describe(rank):
    rank = max(0, int(rank))
    realm = max(i for i, start in enumerate(STARTS) if rank >= start)
    width = (STARTS[realm + 1] if realm < 12 else 209) - STARTS[realm]
    fraction = min(width - 1, rank - STARTS[realm])
    stage = min(2, fraction * 3 // width)
    return {'rank': rank, 'realm_index': realm, 'name': NAMES[realm] + (('初期', '中期', '后期')[stage] if realm else '')}


def body_rank(mortal, immortal):
    if not immortal:
        return min(100, mortal)
    realm = min(12, 9 + (immortal - 1) // 20)
    offset = min(19, immortal - 1 - (realm - 9) * 20)
    return rank_for(realm, min(9, 1 + offset * 9 // 20))


def legacy_sense(rank):
    if rank <= 0:
        return 0
    if rank <= 13:
        return rank_for(1, rank)
    if rank >= 104:
        return STARTS[12] + (rank - 104) * 3
    return rank_for(min(12, 2 + (rank - 14) // 9), 1 + (rank - 14) % 9)


def ensure_npc(npc):
    from .combat.npc_lifecycle import read, _write
    realm, layer = read(npc, 'realm_index', 0), read(npc, 'layer', 1)
    seed = 0
    if read(npc, 'body_training') is None or read(npc, 'divine_sense_rank') is None:
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
        _write(npc, 'immortal_body_level', max(20, read(npc, 'immortal_body_level', 0)))


def public_ranks(actor, *, player=False):
    from .combat.npc_lifecycle import read
    if not player:
        ensure_npc(actor)
    immortal = actor.immortal_body.get('level', 0) if player else read(actor, 'immortal_body_level', 0)
    return {'cultivation': describe(rank_for(read(actor, 'realm_index', 0), read(actor, 'layer', 1))),
            'body': describe(body_rank(read(actor, 'body_training', 0), immortal)),
            'sense': describe(read(actor, 'divine_sense_rank', 0))}


def npc_voisinage_limit(npc):
    """Only rare late true immortals have a field. Stable identity, no rerolls."""
    from .combat.npc_lifecycle import read
    realm = read(npc, 'realm_index', 0)
    if realm > 9:
        return 9
    if realm < 9 or read(npc, 'layer', 1) < 7:
        return 3
    seed = int.from_bytes(hashlib.blake2s(('voisinage:' + str(read(npc, 'id', ''))).encode(), digest_size=4).digest(), 'big')
    return 5 if seed % 100 < 12 else 3


def npc_golden_light(npc):
    from .combat.npc_lifecycle import read
    return body_rank(read(npc, 'body_training', 0) or 0, read(npc, 'immortal_body_level', 0)) >= rank_for(9, 7)


def mask_unrevealed(public, perception):
    if perception and not perception.get('revealed'):
        public['cultivation_ranks'] = {
            'cultivation': {'name': perception['realm_name']},
            'body': {'name': '未探明'}, 'sense': {'name': '未探明'}}
        for key in ('body_training', 'immortal_body_level', 'divine_sense_rank'):
            public[key] = None

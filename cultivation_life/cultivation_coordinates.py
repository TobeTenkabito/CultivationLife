"""Pure cultivation coordinates, usable while decoding models before content loads."""


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

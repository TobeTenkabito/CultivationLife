"""Pure cultivation coordinates, usable while decoding models before content loads."""


# Inclusive starts: mortal 0–3; qi 4–16; seven 12-rank realms through 100.
STARTS = (0, 4, 17, 29, 41, 53, 65, 77, 89, 101, 128, 155, 182)
END_RANK = 209


NAMES = ('凡人', '炼气', '筑基', '结丹', '元婴', '化神', '炼虚', '合体', '大乘', '真仙', '金仙', '太乙', '大罗')


def rank_for(realm, layer=1):
    realm = max(0, min(12, realm))
    width = (STARTS[realm + 1] if realm < 12 else END_RANK) - STARTS[realm]
    layers = 1 if realm == 0 else 13 if realm == 1 else 9
    return STARTS[realm] + min(width - 1, max(0, layer - 1) * width // layers)


def describe(rank):
    rank = max(0, int(rank))
    realm = max(i for i, start in enumerate(STARTS) if rank >= start)
    width = (STARTS[realm + 1] if realm < 12 else END_RANK) - STARTS[realm]
    fraction = min(width - 1, rank - STARTS[realm])
    stage = min(2, fraction * 3 // width)
    return {'rank': rank, 'realm_index': realm, 'name': NAMES[realm] + (('初期', '中期', '后期')[stage] if realm else '')}


def body_rank(mortal, immortal):
    if not immortal:
        return min(100, mortal)
    value=max(1,min(50,int(immortal)))
    intervals=((1,4,9,1),(5,8,9,4),(9,12,9,7),
               (13,16,10,1),(17,20,10,4),(21,24,10,7),
               (25,28,11,1),(29,32,11,4),(33,36,11,7),
               (37,40,12,1),(41,45,12,4),(46,50,12,7))
    low,high,realm,layer=next(row for row in intervals if row[0]<=value<=row[1])
    return rank_for(realm,layer+min(2,(value-low)*3//(high-low+1)))


def legacy_sense(rank):
    if rank <= 0:
        return 0
    if rank <= 13:
        return rank_for(1, rank)
    if rank >= 104:
        return STARTS[12] + (rank - 104) * 3
    return rank_for(min(12, 2 + (rank - 14) // 9), 1 + (rank - 14) % 9)


def validate_immortal_body(record):
    if not isinstance(record,dict):raise ValueError('仙躯记录须为对象')
    level=record.get('level',0)
    if type(level) is not int or not 0<=level<=50:raise ValueError('仙躯层数须为0至50')
    lights=record.get('divine_lights',{})
    if not isinstance(lights,dict) or set(lights)-{'kun','zhen','kan','li','qian'}:
        raise ValueError('五色神光记录无效')
    if any(type(v) is not int or not 0<=v<=10 for v in lights.values()):raise ValueError('神光修炼等级须为0至10')
    if 'monster' in record:
        from .monster_body_content import validate_record
        validate_record(record['monster'])
    if 'ghost_training' in record:
        from .ghost_body_content import validate_training
        validate_training(record['ghost_training'])
    return record

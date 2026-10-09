"""Bounded category indexes. Lists are indexes into real stock, never stock copies."""
from functools import lru_cache
from collections import OrderedDict
from ...content_registry import ITEM_CATALOG, restricted_acquisition

CATEGORIES = ('medical', 'training', 'material', 'arms', 'energy', 'general')
RATES = dict(medical=.10, training=.08, material=.08, arms=.008, energy=.06, general=.02)
REALM_WEIGHTS = tuple(((r + 1) / 2) ** 1.6 for r in range(13))
_INDEXES = OrderedDict()


@lru_cache(maxsize=4096)
def category(item, registry, definition_identity):
    definition = ITEM_CATALOG.get(item)
    tags = set(definition.tags) if definition else set()
    name = definition.name if definition else ''
    if tags & {'healing', 'medicine', 'elixir'} or item == 'healing_pill' or any(s in name for s in ('疗伤', '回春', '养魂', '魂泉', '甘露')):
        return 'medical'
    if 'pill' in tags:
        return 'training'
    if tags & {'energy', 'formation_supply', 'formation_material'} or any(s in name for s in ('阵盘', '阵材', '阵旗', '灵珠')):
        return 'energy'
    if tags & {'equipment', 'artifact', 'weapon'} or any(s in name for s in ('剑', '刀', '刃', '靴', '甲', '炉', '旗', '幡', '尺', '法印')):
        return 'arms'
    if tags & {'material', 'herb', 'seed', 'puppet_material', 'talisman_material', 'natal_artifact_material'} or any(s in name for s in ('草', '参', '莲', '花', '果', '芝', '晶', '铜', '铁', '砂', '玉', '矿', '木', '髓')):
        return 'material'
    return 'general'


def kind(item):
    return category(item, id(ITEM_CATALOG), id(ITEM_CATALOG.get(item)))


def is_raw(item):
    definition=ITEM_CATALOG.get(item)
    if definition is None:return False
    tags=set(definition.tags)
    if tags & {'herb','seed'}:return True
    if 'talisman_material' in tags and item.endswith('_jade'):
        return True  # Unengraved jade is mineral stock; paper/ink are processed.
    # Legacy market entries lack purpose tags: iron in a finished talisman's
    # name does not turn it into a mine, nor jade in a prepared elixir.
    processed=tags & {'pill','equipment','artifact','weapon','puppet_material','talisman_material'}
    processed=processed or 'talisman' in item or definition.name.endswith(('符','露','丹','液','丸'))
    return kind(item)=='material' and not processed


def index(market, *, rebuild=False):
    """Rebuild only when the catalog changes, not when quantities change."""
    key=id(market)
    cached=_INDEXES.get(key)
    if not rebuild and cached and cached[0] is market and cached[1] == len(market['commodities']):
        _INDEXES.move_to_end(key)
        return cached[2]
    groups = {};raw = {}
    for item, row in market['commodities'].items():
        if item not in ITEM_CATALOG or restricted_acquisition('item',item):continue
        groups.setdefault(f'{kind(item)}:{row["tier"]}', []).append(item)
        if is_raw(item):raw.setdefault(row['tier'],[]).append(item)
    for group,keys in groups.items():
        keys.sort(key=lambda k: (market['commodities'][k]['reference'], k))
        if group.startswith('material:'):
            natural=[k for k in keys if is_raw(k)]
            processed=[k for k in keys if not is_raw(k)]
            selected=natural[:1]+processed[:1]
            keys[:]=selected+[k for k in keys if k not in selected]
    for keys in raw.values():keys.sort(key=lambda k:(market['commodities'][k]['reference'],k))
    _INDEXES[key]=(market,len(market['commodities']),groups,raw)
    _INDEXES.move_to_end(key)
    while len(_INDEXES)>64:_INDEXES.popitem(last=False)
    return groups


def raw_candidates(market,rank,limit=2):
    index(market)
    chosen=tuple(_INDEXES[id(market)][3].get(rank,())[:limit])
    if any(k not in market['commodities'] or market['commodities'][k]['tier'] != rank for k in chosen):
        index(market,rebuild=True)
        return raw_candidates(market,rank,limit)
    return chosen


def candidates(market, group, *, limit=2, rotation=0):
    keys = index(market).get(group, ())
    if not keys:
        return ()
    start = rotation % len(keys)
    chosen=tuple(keys[(start+i) % len(keys)] for i in range(min(limit,len(keys))))
    if any(k not in market['commodities'] or market['commodities'][k]['tier'] != int(group.split(':')[1]) for k in chosen):
        index(market,rebuild=True)
        return candidates(market,group,limit=limit,rotation=rotation)
    return chosen



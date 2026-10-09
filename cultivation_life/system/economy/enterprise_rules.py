"""Bounded commercial recipes using existing standard goods, never unique items."""
import math
from collections import OrderedDict
from ...content_registry import ITEM_CATALOG, WORLD_SYSTEMS

KINDS = dict(farm='药田', mine='矿区', alchemy='丹坊', forge='器坊', shop='商铺仓库')
MAX_LEVEL = 5
_RECIPES=OrderedDict()


def farm_goods(world):
    if WORLD_SYSTEMS['world_profiles'].get(world, {}).get('tier', 0) <= 0:
        return {}
    plant = WORLD_SYSTEMS['spirit_field']['plants']['dew_grass']
    harvest = plant['harvest']['ten']
    return {key: dict(id=key, name=ITEM_CATALOG[key].name, base_price=price, tier=1)
            for key, price in [(plant['seed_id'], 6), (harvest['item_id'], int(harvest['value']))]}


def recipes(world, catalog):
    key=(world,id(catalog),len(catalog))
    cached=_RECIPES.get(key)
    if cached and cached[0] is catalog:
        _RECIPES.move_to_end(key)
        return cached[1]
    result=_compile_recipes(world,catalog)
    _RECIPES[key]=(catalog,result)
    while len(_RECIPES)>32:_RECIPES.popitem(last=False)
    return result


def _compile_recipes(world,catalog):
    if WORLD_SYSTEMS['world_profiles'].get(world, {}).get('tier', 0) <= 0:
        return {}
    native = {k:v for k,v in catalog.items() if k in ITEM_CATALOG}
    minimum = {1:1, 2:5, 3:9}[WORLD_SYSTEMS['world_profiles'][world]['tier']]
    crop = 'dew_grass_ten'
    # Advanced estates grow a local ordinary herb, not a restricted reward.
    if WORLD_SYSTEMS['world_profiles'][world]['tier'] > 1:
        plants = [k for k,v in native.items() if v['tier'] >= minimum and 'seed' not in ITEM_CATALOG[k].tags
                  and any(c in v['name'] for c in ('参','莲','花','草','果','芝'))]
        if plants:
            crop = min(plants, key=lambda k: native[k]['base_price'])
    from .basket_rules import is_raw
    ores = [k for k,v in native.items() if v['tier'] >= minimum and k != crop and is_raw(k) and 'herb' not in ITEM_CATALOG[k].tags
            and 'seed' not in ITEM_CATALOG[k].tags and any(c in v['name'] for c in ('晶','铜','铁','砂','玉','矿'))]
    ore = min(ores, key=lambda k: (native[k]['tier'], native[k]['base_price']))
    result = dict(farm=dict(kind='farm', name='种植' + native[crop]['name'], inputs={'dew_grass_seed': 1},
                           output=crop, quantity=4, years=10 if crop == 'dew_grass_ten' else 3, labor=.35),
                  mine=dict(kind='mine', name='开采' + native[ore]['name'], inputs={},
                           output=ore, quantity=4, years=2, labor=.35))
    for kind, material, goods in [
        ('alchemy', crop, [k for k in native if 'pill' in ITEM_CATALOG[k].tags]),
        ('forge', ore, [k for k,v in native.items() if k != ore and
                       (('puppet_material' in ITEM_CATALOG[k].tags and 'core' in ITEM_CATALOG[k].tags)
                        or any(c in v['name'] for c in ('刀','剑','靴','甲','盘','印')))])]:
        for item in sorted(goods, key=lambda k: (native[k]['tier'], native[k]['base_price'], k))[:8]:
            units = max(1, math.ceil(native[item]['base_price'] * 4 * .5 / native[material]['base_price']))
            if units > 1000:
                continue
            result[f'{kind}:{item}'] = dict(kind=kind, name='批量生产' + native[item]['name'], inputs={material:units},
                                            output=item, quantity=4, years=1, labor=.15)
    return result


def capacity(estate):
    return 1000 * estate['level']


def title_cost(world, kind, level=1):
    return 10000 * WORLD_SYSTEMS['world_profiles'][world]['tier'] * level ** 2 * (2 if kind in {'alchemy', 'forge'} else 1)

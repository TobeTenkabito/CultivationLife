"""Bounded commercial recipes using existing standard goods, never unique items."""
import math
from collections import OrderedDict
from ...content_registry import ITEM_CATALOG, WORLD_SYSTEMS
from ...economy_content import specification, material_id, inputs as native_inputs

KINDS = dict(farm='药田', mine='矿区', hunt='猎场', alchemy='丹坊', forge='器坊', shop='商铺仓库')
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
        plants = [k for k,v in native.items() if not specification(k) and v['tier'] >= minimum and 'seed' not in ITEM_CATALOG[k].tags
                  and any(c in v['name'] for c in ('参','莲','花','草','果','芝'))]
        if plants:
            crop = min(plants, key=lambda k: native[k]['base_price'])
    from .basket_rules import is_raw
    ores = [k for k,v in native.items() if not specification(k) and v['tier'] >= minimum and k != crop and is_raw(k) and 'herb' not in ITEM_CATALOG[k].tags
            and 'seed' not in ITEM_CATALOG[k].tags and any(c in v['name'] for c in ('晶','铜','铁','砂','玉','矿'))]
    ore = min(ores, key=lambda k: (native[k]['tier'], native[k]['base_price']))
    result = dict(farm=dict(kind='farm', name='种植' + native[crop]['name'], inputs={'dew_grass_seed': 1},
                           output=crop, quantity=4, years=10 if crop == 'dew_grass_ten' else 3, labor=.35),
                  mine=dict(kind='mine', name='开采' + native[ore]['name'], inputs={},
                           output=ore, quantity=4, years=2, labor=.35))
    # Legacy starter licenses remain intact; advanced ordinary workshops use
    # the same multi-input recipes as the aggregate production authority.
    from .basket_production import recipe as workshop_recipe
    recipe_market=dict(world=world,commodities={k:dict(tier=v['tier'],reference=v['base_price']) for k,v in native.items()})
    for kind, material, goods in [
        ('alchemy', crop, [k for k in native if not specification(k) and 'pill' in ITEM_CATALOG[k].tags]),
        ('forge', ore, [k for k,v in native.items() if not specification(k) and k != ore and
                       (('puppet_material' in ITEM_CATALOG[k].tags and 'core' in ITEM_CATALOG[k].tags)
                        or any(c in v['name'] for c in ('刀','剑','靴','甲','盘','印')))])]:
        for item in sorted(goods, key=lambda k: (native[k]['tier'], native[k]['base_price'], k))[:8]:
            units = max(1, math.ceil(native[item]['base_price'] * 4 * .5 / native[material]['base_price']))
            if units > 1000:
                continue
            components=workshop_recipe(recipe_market,item) if native[item]['tier']>1 else None
            components={k:n*4 for k,n in components.items()} if components else {material:units}
            result[f'{kind}:{item}'] = dict(kind=kind, name='批量生产' + native[item]['name'], inputs=components,
                                            output=item, quantity=4, years=1, labor=.15)
    for item,good in native.items():
        spec=specification(item)
        if not spec:continue
        if spec['raw']:
            family=spec['role'].split('_')[0]
            kind=dict(ore='mine',herb='farm',core='hunt')[family]
            inputs={} if kind=='mine' else {material_id(world,spec['grade'],'core_energy' if kind=='farm' else 'herb_heal'):1}
            years=dict(mine=2,farm=3,hunt=3)[kind]
        else:
            kind='alchemy' if spec['use'] in {'healing','cultivation','longevity','breakthrough'} else 'forge'
            inputs={k:n*4 for k,n in native_inputs(world,spec['grade'],spec['template']).items()}
            years=1
        result[f'{kind}:{item}']=dict(kind=kind,name='生产'+good['name'],inputs=inputs,
            output=item,quantity=4,years=years,labor=.35 if spec['raw'] else .15)
    return result


def capacity(estate):
    return 1000 * estate['level']


def title_cost(world, kind, level=1):
    return 10000 * WORLD_SYSTEMS['world_profiles'][world]['tier'] * level ** 2 * (2 if kind in {'alchemy', 'forge'} else 1)

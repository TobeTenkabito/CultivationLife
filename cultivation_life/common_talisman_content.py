"""Standard commodities become ordinary finite-charge talismans when unpacked."""
import math

from .talisman_content import WORLD_TIERS, DIMENSIONS

SLOTS = dict(talisman_power=('破敌符', 'power'),
             talisman_protection=('护身符', 'protection'),
             talisman_assistance=('助行符', 'assistance'))


def price(grade):
    material = round(6 * 3.2 ** (grade - 1))
    inputs = material + round(material * 1.2)
    artisan = (inputs + 24 * 4 ** (grade - 1)) * .85 * .65 * (1 + 13 * grade * .65 / 100)
    return math.ceil(max(inputs * 2, artisan * .2))


def product(identity, world, grade, slot, name):
    return dict(name=name, method_id=identity, tier=grade, pricing_version=2,
                origin_world=world, quality='poor', element='neutral',
                material_value=price(grade), enabled=False, uses=3, max_uses=3,
                **{d: float(4 * grade if d == SLOTS[slot][1] else 0) for d in DIMENSIONS})


def build():
    items, goods = [], []
    for world, (prefix, grades) in WORLD_TIERS.items():
        for grade in grades:
            for slot, (label, dimension) in SLOTS.items():
                identity = f'econ_{world}_{grade}_{slot}'
                name = f'{prefix}{label}（{grade}阶）'
                items.append(dict(id=identity, name=name,
                    tags=['economic_product', 'economic_use:talisman', 'talisman', f'native_world:{world}'],
                    description=f'通用制式符箓，{dict(power="威力",protection="防护",assistance="辅助")[dimension]} {4*grade}，可调用3次；收入符箓后沿原启停与消耗规则使用。属性与次数低于同阶手制符箓。'))
                goods.append(dict(world=world, kind='item', content_id=identity, tier=grade, price=price(grade)))
    return items, goods

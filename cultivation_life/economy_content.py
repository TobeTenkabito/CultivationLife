"""Native economic definitions compiled once, before the content registry exists.

Roles describe actual ingredients; uses describe finished demand. Neither is a
second inventory. Special/quest crafting definitions remain independent.
"""
from .definition_data import definition as _content_definition
from functools import lru_cache
from .common_talisman_content import SLOTS as TALISMAN_SLOTS



ROLES = ('ore_structure', 'ore_conduct', 'ore_store', 'herb_nurture',
         'herb_heal', 'herb_spirit', 'core_energy', 'core_blood', 'core_soul')
WORLD_MATERIALS = _content_definition(__name__, "WORLD_MATERIALS")
THEMES = dict(human='玄门', demon='血煞', spirit='清虚', true_demon='渊魔',
              monster_realm='祖灵', phantom_underworld='幻冥', hell='镇狱',
              celestial='太清', asura='战魂', nether='黄泉', reincarnation='三生')
# Prices follow the existing order of magnitude, with no extra realm exponent.
BASE_PRICES = (2, 8, 35, 180, 900, 4500, 22500, 110000,
               1400000, 100000000, 800000000, 6000000000)
# At most three same-grade inputs. Every one of the nine roles has a sink.
TEMPLATES = _content_definition(__name__, "TEMPLATES")

# Names describe a world's craft tradition; use and grade remain explicit in
# the specification, tags and market. Keep this separate from recipe roles.
PRODUCT_NAMES = _content_definition(__name__, "PRODUCT_NAMES")


def material_id(world, grade, role):
    return f'econ_{world}_{grade}_{role}'


def product_id(world, grade, template):
    return f'econ_{world}_{grade}_{template}'


@lru_cache(maxsize=4096)
def specification(item):
    """Parse only our registered namespace, never infer a core from 丹 in a name."""
    for world in WORLD_MATERIALS:
        prefix = f'econ_{world}_'
        if not item.startswith(prefix):
            continue
        tail = item[len(prefix):].split('_', 1)
        if len(tail) != 2 or not tail[0].isdigit():
            return None
        grade, slot = int(tail[0]), tail[1]
        if not 1 <= grade <= 12 or slot not in (*ROLES, *TEMPLATES, *TALISMAN_SLOTS):
            return None
        if slot in ROLES:
            return dict(world=world, grade=grade, role=slot, raw=True, use=None)
        if slot in TALISMAN_SLOTS:
            from .talisman_content import WORLD_TIERS
            if grade not in WORLD_TIERS[world][1]:
                return None
            return dict(world=world, grade=grade, role=None, raw=False, use='talisman', template=slot)
        use = 'artifact' if slot.startswith('artifact_') else slot
        return dict(world=world, grade=grade, role=None, raw=False, use=use, template=slot)
    return None


def inputs(world, grade, template):
    if template in TALISMAN_SLOTS:
        return {f'talisman_{world}_{grade}_paper': 1, f'talisman_{world}_{grade}_ink': 1}
    roles = TEMPLATES[template][2]
    # Yin-world medical practice nourishes the soul rather than beast blood.
    if world in {'phantom_underworld', 'hell', 'nether', 'reincarnation'}:
        roles = tuple('core_soul' if r == 'core_blood' and template in {'healing', 'longevity'} else r for r in roles)
    return {material_id(world, grade, r): 1 for r in roles}


def build(profiles, realms):
    definitions, goods = [], []
    for world, names in WORLD_MATERIALS.items():
        profile = profiles.get(world)
        if not profile or int(profile['tier']) <= 0:
            raise ValueError(f'经济材料缺少常规界面定义：{world}')
        cap = {1: 5, 2: 8, 3: 12}[int(profile['tier'])]
        for grade in range(1, cap + 1):
            base = BASE_PRICES[grade - 1]
            for role, name in zip(ROLES, names):
                family = role.split('_', 1)[0]
                item = material_id(world, grade, role)
                definitions.append(dict(id=item, name=f'{name}（{grade}阶）', force_tier=1,
                    tags=['material', 'economic_raw', f'economic_role:{role}', f'native_world:{world}'],
                    description=f'{THEMES[world]}本界{grade}阶{dict(ore="矿石",herb="草药",core="内丹")[family]}，用于同阶有限加工配方。' + (
                        {'core_energy':'服用获得固定机缘；', 'core_blood':'服用恢复固定当前HP，不增加上限；',
                         'core_soul':'服用恢复固定当前MP，不增加上限；'}[role]
                        + '仅限同阶弱效服用，与养元丹共享每年一次消化限制。'
                        if family == 'core' else
                        {'ore_structure':'可作炼器主材，通用成器属性较低。', 'ore_conduct':'可作炼器辅材，允许两份同种实物。',
                         'ore_store':'可作炼器淬火材料。'}.get(role, ''))))
                goods.append(dict(world=world, kind='item', content_id=item, tier=grade, price=base))
            for (template, (name, category, roles, multiplier)), product_name in zip(TEMPLATES.items(), PRODUCT_NAMES[world], strict=True):
                item = product_id(world, grade, template)
                use = 'artifact' if template.startswith('artifact_') else template
                tags = [f'economic_use:{use}', f'native_world:{world}', 'economic_product']
                tags += ['pill'] if category in {'medical', 'training'} else ['artifact'] if category == 'arms' else ['material']
                # Commercial grade lives in the specification and market good.
                # Combat force is a separate mortal/upper qualification.
                row = dict(id=item, name=f'{product_name}（{grade}阶）',
                    force_tier=2 if use == 'artifact' and grade >= 9 else 1, tags=tags,
                    description=f'本界同阶原料加工的标准{ name }；居民供养按用途消费，军需仅接受适用用途及品阶。')
                if use == 'artifact':
                    row['combat_bonus'] = float(realms[grade]['base_power']) * .025
                if use == 'breakthrough':
                    row.update(breakthrough_bonus=.05, breakthrough_scope=f'{"minor" if grade == 12 else "major"}:{grade}')
                if use == 'healing':
                    row.update(trial_restore_hp=.12, trial_restore_mp=.06)
                definitions.append(row)
                goods.append(dict(world=world, kind='item', content_id=item, tier=grade, price=base * multiplier))
    from .common_talisman_content import build as talisman_goods
    items, offers = talisman_goods()
    return definitions + items, goods + offers

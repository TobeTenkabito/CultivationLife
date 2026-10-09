"""Native economic definitions compiled once, before the content registry exists.

Roles describe actual ingredients; uses describe finished demand. Neither is a
second inventory. Special/quest crafting definitions remain independent.
"""
from functools import lru_cache

ROLES = ('ore_structure', 'ore_conduct', 'ore_store', 'herb_nurture',
         'herb_heal', 'herb_spirit', 'core_energy', 'core_blood', 'core_soul')
WORLD_MATERIALS = {
    'human': ('玄铁矿', '导灵铜', '蓄灵玉', '养元芝', '回春藤', '凝神莲', '灵兽元丹', '赤兽血丹', '幽兽魂丹'),
    'demon': ('煞铁矿', '蚀灵铜', '封煞晶', '血元芝', '续骨藤', '镇魔花', '魔兽煞丹', '狂兽血丹', '梦魇魂丹'),
    'spirit': ('空冥矿', '通玄银', '纳虚石', '玄元参', '玉髓草', '清虚莲', '玄兽元丹', '麟兽血丹', '灵犀魂丹'),
    'true_demon': ('渊魔矿', '引煞金', '锁魔晶', '渊血芝', '魔髓藤', '定魄花', '渊兽魔丹', '冥犼血丹', '噬梦魂丹'),
    'monster_realm': ('蛮骨矿', '雷纹铜', '地脉玉', '祖灵果', '生肌木', '启智花', '荒兽元丹', '祖兽血丹', '慧兽魂丹'),
    'phantom_underworld': ('幻冥矿', '映魂银', '藏影石', '幻生芝', '聚形草', '醒梦莲', '幻兽元丹', '影兽血丹', '梦兽魂丹'),
    'hell': ('狱骨矿', '引魂铁', '镇狱晶', '冥生果', '续魂藤', '净业花', '狱兽元丹', '恶兽血丹', '罪兽魂丹'),
    'celestial': ('仙罡矿', '天纹金', '太清玉', '长生芝', '琼华草', '悟道莲', '仙兽元丹', '天麟血丹', '云鹤魂丹'),
    'asura': ('修罗矿', '战纹铜', '藏煞晶', '战血果', '不屈藤', '止杀花', '战兽煞丹', '罗犼血丹', '怒兽魂丹'),
    'nether': ('幽冥矿', '渡魂银', '黄泉玉', '还阳芝', '补魂草', '忘川莲', '冥兽元丹', '冥龙血丹', '渡厄魂丹'),
    'reincarnation': ('轮回矿', '因果金', '宿命晶', '三生果', '返生藤', '照心莲', '劫兽元丹', '转生血丹', '忆世魂丹'),
}
THEMES = dict(human='玄门', demon='血煞', spirit='清虚', true_demon='渊魔',
              monster_realm='祖灵', phantom_underworld='幻冥', hell='镇狱',
              celestial='太清', asura='战魂', nether='黄泉', reincarnation='三生')
# Prices follow the existing order of magnitude, with no extra realm exponent.
BASE_PRICES = (2, 8, 35, 180, 900, 4500, 22500, 110000,
               1400000, 100000000, 800000000, 6000000000)
# At most three same-grade inputs. Every one of the nine roles has a sink.
TEMPLATES = {
    'healing': ('疗伤丹', 'medical', ('herb_heal', 'core_blood'), 5),
    'cultivation': ('养元丹', 'training', ('herb_nurture', 'core_energy'), 5),
    'longevity': ('延寿丹', 'training', ('herb_nurture', 'herb_heal', 'core_blood'), 7),
    'breakthrough': ('破境丹', 'training', ('herb_spirit', 'core_soul', 'core_energy'), 8),
    'artifact_attack': ('攻伐法宝', 'arms', ('ore_structure', 'ore_conduct', 'core_blood'), 9),
    'artifact_guard': ('护身法宝', 'arms', ('ore_structure', 'ore_store', 'core_soul'), 9),
    'repair': ('修补资材', 'material', ('ore_structure', 'herb_heal'), 5),
    'energy': ('阵能灵珠', 'energy', ('ore_conduct', 'ore_store', 'core_energy'), 7),
}


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
        if not 1 <= grade <= 12 or slot not in (*ROLES, *TEMPLATES):
            return None
        if slot in ROLES:
            return dict(world=world, grade=grade, role=slot, raw=True, use=None)
        use = 'artifact' if slot.startswith('artifact_') else slot
        return dict(world=world, grade=grade, role=None, raw=False, use=use, template=slot)
    return None


def inputs(world, grade, template):
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
                    description=f'{THEMES[world]}本界{grade}阶{dict(ore="矿石",herb="草药",core="内丹")[family]}，用于同阶有限加工配方；内丹是原料，不能作为成品丹药服用。'))
                goods.append(dict(world=world, kind='item', content_id=item, tier=grade, price=base))
            for template, (name, category, roles, multiplier) in TEMPLATES.items():
                item = product_id(world, grade, template)
                use = 'artifact' if template.startswith('artifact_') else template
                tags = [f'economic_use:{use}', f'native_world:{world}', 'economic_product']
                tags += ['pill'] if category in {'medical', 'training'} else ['artifact'] if category == 'arms' else ['material']
                # Commercial grade lives in the specification and market good.
                # Combat force is a separate mortal/upper qualification.
                row = dict(id=item, name=f'{THEMES[world]}{name}（{grade}阶）',
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
    return definitions, goods

"""Shared Guixu item formulae and factual, catalog-derived descriptions."""
from __future__ import annotations

import math


def recovery_profile(item):
    if 'guixu_consumable' in item.tags:
        potency = max(1, int(item.id.rsplit('_', 1)[-1]))
        return min(.55, .18 + potency * .035), .20 + potency * .04
    potency = max(1.0, math.log10(max(10.0, float(item.plant_value or 10))))
    return min(.45, .08 + potency * .04), min(.90, .10 + potency * .06)


def material_potency(item):
    return max(.02, min(.30, math.log10(max(10.0, float(item.plant_value or item.combat_bonus or 10))) * .035))


def describe(item):
    if 'guixu_tide' not in item.tags:
        return item.description
    parts = [f'{item.name}，归墟所产奇物。']
    labels = [('combat_bonus', '战斗力'), ('hp_bonus', 'HP上限'), ('mp_bonus', 'MP上限')]
    passive = [f'{label} +{getattr(item, key):,g}' for key, label in labels if getattr(item, key)]
    if item.opportunity_bonus:
        passive.append(f'机缘效率 +{item.opportunity_bonus:.1%}')
    if passive:
        parts.append('携带每件提供：' + '、'.join(passive) + '；实际收益按当前境界的外物承载规则结算。')
    if 'guixu_consumable' in item.tags or 'spirit_plant' in item.tags:
        recovery, opportunity = recovery_profile(item)
        verb = '炼化' if 'spirit_plant' in item.tags else '使用'
        parts.append(f'{verb}消耗1件，恢复当前HP、MP各约{recovery:.2%}上限，获得当前真实境界基础机缘的{opportunity:.2%}；'
                     '恢复不超过上限、不永久增加上限，机缘仍受实际效率和原有储存上限影响。')
    if {'crafting_material', 'spirit_plant'}.intersection(item.tags):
        potency = material_potency(item)
        parts.append(f'炼器可作主材、辅材或淬火材料：主材战力设计值 +{potency:.2%}，'
                     f'辅材HP、MP设计值各 +{potency/2:.2%}，淬火破法 +{potency/3:.2%}；'
                     '这是材料增益，成器还取决于配方与品质。也可作为布阵材料，使用会消耗原物。')
    if 'equipment' in item.tags or 'crafting_material' in item.tags:
        parts.append('不可直接服用。')
    if 'crafting_material' in item.tags:
        parts.append('还可作本命镶嵌材料，须满足对应境界门槛；实际镶嵌收益见本命面板。')
    if 'equipment' in item.tags:
        parts.append('可在满足原有资格时绑定为本命法宝。')
    return ''.join(parts)

"""Author complete player-facing sentences from the reviewed rule fields."""

from cultivation_life.technique_effect_copy import LORE, mechanics


def description(row, effect, pricing):
    original=row['original_definition']
    lore = LORE[effect['payload']]
    if row['original_category']!='spiritual':
        purpose={
            'body':f'炼体心法，配置于炼体栏，以周天淬炼筋骨、温养肉身。炼体突破助益 {original.get("body_breakthrough_bonus",0):.0%}。',
            'divine_sense':f'神识心法，配置于神识栏，凝练神念、温养识海。神识修炼助益 {original.get("divine_sense_bonus",0):.0%}。',
            'transformation':f'变身法门，配置于变身栏，修习血脉变化之术。形态容量增加 {original.get("transformation_capacity",0):g}，变身空间增加 {original.get("transformation_space",0):g}。',
        }[row['original_category']]
        return (purpose+
                '功法等级提升修习助益，最高 Lv.9；同名同级传承玉简或对应道途、品阶的万能玉简均可用于合参。')
    if effect['prestige']:
        core=('伤及敌人后留下隙印，下次攻击同一目标时引动归墟剑意。'
              'Lv.1—9剑意追加本次交锋基础伤害的 8%—16%；期间破尽敌方临时护持时，提高至 12%—24%。'
              '换敌或两轮后隙印消散。')
    else:
        core=mechanics(effect)
    return (lore+core+pricing+'。'
            f'每战至多 {effect["uses"]} 次，冷却 {effect["cooldown"]} 个完整轮，待用招式保留 {effect["duration"]} 轮。'
            'Lv.1—9逐步降低灵力消耗，最高降低 16%；修习后依自身修为与当前界面的灵力施展。')

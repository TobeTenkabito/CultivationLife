"""Pure ghost-body descriptors, shared by player and NPC projections."""
from .system.combat.body_mechanisms import BodyMechanism

IDS=('wuxiang','zhaoye','yuhun','wangqing','yinguo')
NAMES=('无相','照业','御魂','忘情','因果')
MATERIAL_IDS=('ghost_formless_amber','ghost_karma_mirror','ghost_returning_lotus','ghost_oblivion_crystal','ghost_causality_thread')
MATERIAL_NAMES=('无相空珀','照业冥镜','归魂幽莲','忘川泪晶','因果赤丝')
MATERIAL_COUNTS=(4,6,8,10,12)
EFFECTS={
    'wuxiang':{'ward':(2,0),'recovery_bonus':(0,.03)},
    'zhaoye':{'split':(.4,.025)},
    'yuhun':{'death_restore':(.03,.003)},
    'wangqing':{'forget':(.25,.035)},
    'yinguo':{'karma_threshold':(.5,-.035),'karma_power':(.18,0)}
}


def recipe(key,rank):
    index=IDS.index(key)
    return {MATERIAL_IDS[index]:MATERIAL_COUNTS[index]*(rank+1)}


def validate_material_content(items,goods):
    for key in MATERIAL_IDS:
        if key not in items or 'ghost_body_material' not in items[key].tags:
            raise ValueError('鬼躯五法培养材料缺失')
        rows=[r for r in goods if r['kind']=='item' and r['content_id']==key]
        if {r['world'] for r in rows}!={'reincarnation'} or {r['tier'] for r in rows}!={9,10,11,12}:
            raise ValueError('鬼躯五法材料只能在轮回界九至十二阶货架产出')


def build(key,rank=0,*,effects=None):
    values=(EFFECTS if effects is None else effects)[key]
    index=IDS.index(key)
    return BodyMechanism(key,NAMES[index],{k:round(base+growth*rank,10) for k,(base,growth) in values.items()},priority=index*10,level=rank)


def validate_training(value):
    if (not isinstance(value,dict) or set(value)-set(IDS) or
            any(type(v) is not int or not 0<=v<=10 for v in value.values())):
        raise ValueError('鬼躯机制修炼记录须为五法各0至10重')
    return value

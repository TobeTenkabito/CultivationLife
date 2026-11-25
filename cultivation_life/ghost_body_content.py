"""Pure ghost-body descriptors, shared by player and NPC projections."""
from .definition_data import definition as _content_definition
from .system.combat.body_mechanisms import BodyMechanism

IDS=_content_definition(__name__, "IDS")
NAMES=_content_definition(__name__, "NAMES")
MATERIAL_IDS=_content_definition(__name__, "MATERIAL_IDS")
MATERIAL_NAMES=_content_definition(__name__, "MATERIAL_NAMES")
MATERIAL_COUNTS=_content_definition(__name__, "MATERIAL_COUNTS")
EFFECTS=_content_definition(__name__, "EFFECTS")


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

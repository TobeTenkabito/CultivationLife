"""Pure ghost-body descriptors, shared by player and NPC projections."""
from .system.combat.body_mechanisms import BodyMechanism

IDS=('wuxiang','zhaoye','yuhun','wangqing','yinguo')
NAMES=('无相','照业','御魂','忘情','因果')


def build(key,rank=0):
    effects=(dict(ward=2,recovery_bonus=.03*rank),dict(split=.4+.02*rank),
        dict(death_restore=.03+.003*rank),dict(forget=.15+.015*rank),
        dict(karma_threshold=.5-.025*rank,karma_power=.12))
    index=IDS.index(key)
    return BodyMechanism(key,NAMES[index],effects[index],priority=index*10,level=rank)


def validate_training(value):
    if (not isinstance(value,dict) or set(value)-set(IDS) or
            any(type(v) is not int or not 0<=v<=10 for v in value.values())):
        raise ValueError('鬼躯机制修炼记录须为五法各0至10重')
    return value

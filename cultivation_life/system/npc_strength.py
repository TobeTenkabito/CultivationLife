"""Shared original equipment, cultivation and wound estimate; never troop counts."""
from ..content_registry import ROOT_DEFINITIONS, ITEM_CATALOG
from ..rules import expected_combat_power
from .npc_system import npc_combat_power


def power(npc):
    root=ROOT_DEFINITIONS.get(npc.spirit_root,{})
    return npc_combat_power(npc,expected_combat_power,float(root.get('efficiency',1)),
        ITEM_CATALOG.get(npc.treasure_item_id or ''))*max(.1,npc.combat_factor)*max(.35,1-npc.wounds*.15)+npc.family_combat_bonus

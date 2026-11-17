"""Shared original equipment, cultivation and wound estimate; never troop counts."""
from ..content_registry import ROOT_DEFINITIONS, ITEM_CATALOG
from ..rules import expected_combat_power
from .npc_system import npc_combat_power


def power(npc):
    from .npc_techniques import family_combat_bonus
    root=ROOT_DEFINITIONS.get(npc.spirit_root,{})
    return npc_combat_power(npc,expected_combat_power,float(root.get('efficiency',1)),
        ITEM_CATALOG.get(npc.treasure_item_id or ''))*max(.1,npc.combat_factor)*max(.35,1-npc.wounds*.15)+family_combat_bonus(npc)

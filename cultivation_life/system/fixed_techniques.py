"""Catalog metadata adoption; never replaces learned levels or seeded manuals."""
import copy
from ..content_registry import TECHNIQUE_CATALOG
from .combat.actor_state import read, _write


def refresh_player(player):
    changed=False
    def refresh(owner):
        nonlocal changed
        if not owner:return
        books=[read(owner,k) for k in ('technique','support_technique','body_technique',
                                      'divine_sense_technique','transformation_technique')]
        books+=list(read(owner,'known_techniques',[]) or [])+list(read(owner,'combat_techniques',[]) or [])
        for book in books:
            if not book:continue
            original=TECHNIQUE_CATALOG.get(read(book,'id'))
            if not original or not original.combat_effect or original.combat_effect.get('version')!=3:continue
            from ..technique_evolution import FROST, evolve
            if original.id==FROST:
                original=copy.deepcopy(original);original.level=read(book,'level',1);evolve(original)
            for key in ('combat_effect','description'):
                value=getattr(original,key)
                if read(book,key)!=value:
                    _write(book,key,copy.deepcopy(value));changed=True
    refresh(player)
    refresh(player.ghost_core_state)
    return changed

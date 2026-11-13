"""Project frozen manual effects from original equipped/learned records."""
import copy

from .combat.npc_lifecycle import read
from .technique_context import context
from ..rules import can_player_practice_technique, combat_requirement_met, qi_levels


def project(game, owner, *, player=False):
    from .duel_techniques import player_books, npc_books
    if player:
        candidates = player_books(owner)
    else:
        candidates = npc_books(game, owner)
    result, seen = [], set()
    for book in candidates:
        if not book or not book.combat_effect or book.id in seen or not book.active_in(read(owner, 'world')):
            continue
        if player and (not can_player_practice_technique(owner, book)
                       or not combat_requirement_met(book.combat_requirements, qi_levels(owner))
                       or owner.body_training < book.required_body_training
                       or book.requires_immortal_power and not owner.immortal_power_converted):
            continue
        seen.add(book.id)
        from ..content_registry import REALMS, WORLD_SYSTEMS
        from ..combat_costs import mana_reference
        effect=copy.deepcopy(book.combat_effect)
        grade=book.grade
        if effect.get('resource')=='mana':
            fixed=effect.get('mana_cost',mana_reference(REALMS[grade].base_power)*effect['cost_bp']/10000)
        else:
            # Use the native energy denomination, including the original
            # lower-world imitation pool; never charge MP as immortal energy.
            lower=WORLD_SYSTEMS['world_profiles'].get(read(owner,'world'),{}).get('tier',1)<3
            reference=60. if lower else 1000.*(1+3*max(0,grade-9))
            fixed=reference*effect['cost_bp']/10000
        terms=dict(grade=grade,realm=int(read(owner,'realm_index',0)),fixed=fixed)
        result.append(dict(id=book.id, name=book.name, level=book.level, effect=effect,cost_model=terms))
    return tuple(result)

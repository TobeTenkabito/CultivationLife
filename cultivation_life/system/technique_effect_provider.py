"""Project frozen manual effects from original equipped/learned records."""
import copy

from .combat.npc_lifecycle import read
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
        if book.category == 'transformation':
            # This batch generates spiritual doctrine books only. Form-dependent
            # fixed books must wait for their explicit original-form adapter.
            continue
        seen.add(book.id)
        result.append(dict(id=book.id, name=book.name, level=book.level, effect=copy.deepcopy(book.combat_effect)))
    return tuple(result)

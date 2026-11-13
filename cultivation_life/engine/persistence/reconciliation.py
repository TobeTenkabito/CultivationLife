"""Final session repairs on original state, committed by the load coordinator."""
from ...models import GameState
from ...system.economy.spirit_fields import adopt_field
from ...system.ghost.captors import release_dead_captor
from ...system.ghost.parades import adopt


def prepare_reconciliation(game: GameState) -> bool:
    # Keep the original post-preparation order without a second save boundary.
    changed = adopt(game)
    changed = release_dead_captor(game) or changed
    changed = adopt_field(game) or changed
    from ...character_skins import remember
    changed = remember(game.player) or changed
    from ...system.fixed_techniques import refresh_player
    changed = refresh_player(game.player) or changed
    from ...system.duel_techniques import prepare_visible
    changed = prepare_visible(game) or changed
    return changed

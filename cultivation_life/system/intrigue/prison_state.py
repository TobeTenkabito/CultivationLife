"""Read-only access to the original prison index, without settlement imports."""
from ...content_registry import WORLD_SYSTEMS


def is_imprisoned(game, npc_id, *, enabled=None):
    if enabled is None:
        enabled = bool(WORLD_SYSTEMS.get('intrigue_dlc', {}).get('enabled'))
    return bool(enabled and npc_id in game.intrigue_state.get('npc_prisons', {}))

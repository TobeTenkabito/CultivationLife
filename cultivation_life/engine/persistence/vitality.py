from __future__ import annotations
from ...models import GameState
from ...content_registry import WORLD_SYSTEMS
from ...system.ghost_system import ensure_ghost_cultivation_state
from ...system.ghost_system import ghost_cultivation_active
from ...system.ghost_system import grant_intrinsic_progression_if_new_highwater
from ...system.possession_system import migrate_possession_timeline
from .dependencies import VitalityPreparationDependencies


def prepare_vitality(deps: VitalityPreparationDependencies, game: GameState) -> bool:
    possession_timeline_migrated = migrate_possession_timeline(game.player)
    ghost_migrated = ensure_ghost_cultivation_state(game.player)
    if ghost_cultivation_active(game.player):
        old_intrinsic_state = (
            game.player.ghost_intrinsic_hp_reference,
            game.player.ghost_intrinsic_hp_current,
            game.player.ghost_intrinsic_mp_reference,
            game.player.ghost_intrinsic_mp_current,
            game.player.ghost_intrinsic_highwater_realm,
            game.player.ghost_intrinsic_highwater_layer,
        )
        grant_intrinsic_progression_if_new_highwater(game.player)
        ghost_migrated = ghost_migrated or old_intrinsic_state != (
            game.player.ghost_intrinsic_hp_reference,
            game.player.ghost_intrinsic_hp_current,
            game.player.ghost_intrinsic_mp_reference,
            game.player.ghost_intrinsic_mp_current,
            game.player.ghost_intrinsic_highwater_realm,
            game.player.ghost_intrinsic_highwater_layer,
        )
    ghost_floor = float(WORLD_SYSTEMS.get("ghost_cultivation", {}).get("soul_death_intrinsic_floor", 1.0))
    if (
        ghost_cultivation_active(game.player) and game.player.alive
        and (
            float(game.player.ghost_intrinsic_hp_current or 0.0) < ghost_floor
            or float(game.player.ghost_intrinsic_mp_current or 0.0) < ghost_floor
        )
    ):
        deps._die(game, "本体魂基已经低于存在界限，魂魄彻底消散", "SYS_GHOST_SOUL_DISPERSAL")
        ghost_migrated = True
    return bool(possession_timeline_migrated or ghost_migrated)

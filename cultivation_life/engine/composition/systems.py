"""Connect system contracts while preserving the original configuration hooks.

Only this composition boundary knows both the host and compatibility modules.
All configuration callbacks resolve on use, including after construction.
"""
from ...system import tianji_system as tianji_compat
from ...system import intrigue_system as intrigue_compat
from ...system.tianji.wiring import bind_tianji
from ...system.intrigue.wiring import bind_intrigue
from ...system.tianji.dependencies import TianjiDependencies
from ...system.intrigue.dependencies import IntrigueDependencies
from ...system.economy.wiring import bind_economy
from ...system.economy.dependencies import EconomyDependencies
from ...system import exchange_system, crafting_system, formation_system
from ...system.economy.dependencies import ExchangeDependencies
from ...system.crafting.dependencies import CraftingDependencies
from ...system.formation.dependencies import FormationDependencies


def bind_economy_dependencies(host) -> EconomyDependencies:
    return bind_economy(host)


def bind_exchange_dependencies(host) -> ExchangeDependencies:
    return exchange_system.bind_exchange_compatibility(host)


def bind_crafting_dependencies(host) -> CraftingDependencies:
    return crafting_system.bind_crafting_compatibility(host)


def bind_formation_dependencies(host) -> FormationDependencies:
    return formation_system.bind_formation_compatibility(host)


def bind_tianji_dependencies(host) -> TianjiDependencies:
    return bind_tianji(
        host,
        _get_PRIMITIVES=lambda: tianji_compat.PRIMITIVES,
        _get_SLOT_WEIGHTS=lambda: tianji_compat.SLOT_WEIGHTS,
        _get_TIANJI_GENERATION_VERSION=lambda: tianji_compat.TIANJI_GENERATION_VERSION,
        _get_TIANJI_WINDOW_SCHEDULES=lambda: tianji_compat.TIANJI_WINDOW_SCHEDULES,
        _scaled_effects=lambda *args, **kwargs: tianji_compat._scaled_effects(*args, **kwargs),
        _stable_rng=lambda *args, **kwargs: tianji_compat._stable_rng(*args, **kwargs),
        _tianji_effect_description=lambda *args, **kwargs: tianji_compat._tianji_effect_description(*args, **kwargs),
        tianji_content_available=lambda *args, **kwargs: tianji_compat.tianji_content_available(*args, **kwargs),
    )


def bind_intrigue_dependencies(host) -> IntrigueDependencies:
    return bind_intrigue(
        host,
        _get_PERSONALITY_LABELS=lambda: intrigue_compat.PERSONALITY_LABELS,
        _get_PLAYER_ID=lambda: intrigue_compat.PLAYER_ID,
        _get_RESOLUTION_LABELS=lambda: intrigue_compat.RESOLUTION_LABELS,
        _get_STYLE_LABELS=lambda: intrigue_compat.STYLE_LABELS,
        intrigue_rules=lambda *args, **kwargs: intrigue_compat.intrigue_rules(*args, **kwargs),
    )

"""Compose buddhist flows; collaborators resolve at call time."""
from ...system.buddhist.dependencies import (
    BuddhistActionDependencies,
    BuddhistAssemblyDependencies,
    BuddhistFlowDependencies,
    NirvanaDependencies,
)


def bind_actions(host) -> BuddhistActionDependencies:
    return BuddhistActionDependencies(
        _buddhist_burden=lambda *args, **kwargs: host._buddhist_burden(*args, **kwargs),
        _buddhist_permissions=lambda *args, **kwargs: host._buddhist_permissions(*args, **kwargs),
        _buddhist_record=lambda *args, **kwargs: host._buddhist_record(*args, **kwargs),
        _continue_buddhist_assembly=lambda *args, **kwargs: host._continue_buddhist_assembly(*args, **kwargs),
        _ensure_buddhist_state=lambda *args, **kwargs: host._ensure_buddhist_state(*args, **kwargs),
        _ensure_market=lambda *args, **kwargs: host._ensure_market(*args, **kwargs),
        _finish_buddhist_assembly=lambda *args, **kwargs: host._finish_buddhist_assembly(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _public_buddhist=lambda *args, **kwargs: host._public_buddhist(*args, **kwargs),
        _get_maps=lambda: host.maps,
        nirvana=bind_nirvana(host),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_assembly(host) -> BuddhistAssemblyDependencies:
    return BuddhistAssemblyDependencies(
        _advance_soul_erosion_time=lambda *args, **kwargs: host._advance_soul_erosion_time(*args, **kwargs),
        _advance_world_year=lambda *args, **kwargs: host._advance_world_year(*args, **kwargs),
        _buddhist_permissions=lambda *args, **kwargs: host._buddhist_permissions(*args, **kwargs),
        _buddhist_record=lambda *args, **kwargs: host._buddhist_record(*args, **kwargs),
        _combat=lambda *args, **kwargs: host._combat(*args, **kwargs),
        _finish_buddhist_assembly=lambda *args, **kwargs: host._finish_buddhist_assembly(*args, **kwargs),
        _instantiate_event=lambda *args, **kwargs: host._instantiate_event(*args, **kwargs),
        _get_events_by_id=lambda: host.events_by_id,
    )


def bind_nirvana(host) -> NirvanaDependencies:
    return NirvanaDependencies(
        _buddhist_record=lambda *args, **kwargs: host._buddhist_record(*args, **kwargs),
        _complete_minor_breakthrough=lambda *args, **kwargs: host._complete_minor_breakthrough(*args, **kwargs),
    )


def bind_buddhist_flows(host) -> BuddhistFlowDependencies:
    return BuddhistFlowDependencies(
        actions=bind_actions(host),
        assembly=bind_assembly(host),
        nirvana=bind_nirvana(host),
    )

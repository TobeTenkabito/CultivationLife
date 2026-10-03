"""Explicit composition; callbacks and resources resolve on use."""

from typing import Any, Callable


from .dependencies import (
    TianjiForgingDependencies,
    TianjiGenerationDependencies,
    TianjiIntelligenceDependencies,
    TianjiNpcsDependencies,
    TianjiPresentationDependencies,
    TianjiStateDependencies,
    TianjiDependencies,
)


def bind_forging(
    host,
    *,
    _get_SLOT_WEIGHTS: Callable[[], Any],
    _scaled_effects: Callable[..., Any],
    _stable_rng: Callable[..., Any],
    tianji_content_available: Callable[..., Any],
) -> TianjiForgingDependencies:
    return TianjiForgingDependencies(
        _get_SLOT_WEIGHTS=_get_SLOT_WEIGHTS,
        _ensure_tianji_state=lambda *args, **kwargs: host._ensure_tianji_state(
            *args, **kwargs
        ),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _resolve_crafting_selection=lambda *args,
        **kwargs: host._resolve_crafting_selection(*args, **kwargs),
        _scaled_effects=_scaled_effects,
        _stable_rng=_stable_rng,
        _tianji_artifact=lambda *args, **kwargs: host._tianji_artifact(*args, **kwargs),
        _tianji_closeness_factor=lambda *args, **kwargs: host._tianji_closeness_factor(
            *args, **kwargs
        ),
        _tianji_config=lambda *args, **kwargs: host._tianji_config(*args, **kwargs),
        _tianji_material_instance=lambda *args,
        **kwargs: host._tianji_material_instance(*args, **kwargs),
        _tianji_public_effect=lambda *args, **kwargs: host._tianji_public_effect(
            *args, **kwargs
        ),
        _tianji_reveal=lambda *args, **kwargs: host._tianji_reveal(*args, **kwargs),
        _tianji_tag_similarity=lambda *args, **kwargs: host._tianji_tag_similarity(
            *args, **kwargs
        ),
        _tianji_target_preview=lambda *args, **kwargs: host._tianji_target_preview(
            *args, **kwargs
        ),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
        tianji_content_available=tianji_content_available,
    )


def bind_generation(
    host,
    *,
    _get_PRIMITIVES: Callable[[], Any],
    _get_TIANJI_GENERATION_VERSION: Callable[[], Any],
    _stable_rng: Callable[..., Any],
    _tianji_effect_description: Callable[..., Any],
) -> TianjiGenerationDependencies:
    return TianjiGenerationDependencies(
        _get_PRIMITIVES=_get_PRIMITIVES,
        _get_TIANJI_GENERATION_VERSION=_get_TIANJI_GENERATION_VERSION,
        _next_tianji_buff_name=lambda *args, **kwargs: host._next_tianji_buff_name(
            *args, **kwargs
        ),
        _next_tianji_name=lambda *args, **kwargs: host._next_tianji_name(
            *args, **kwargs
        ),
        _stable_rng=_stable_rng,
        _tianji_config=lambda *args, **kwargs: host._tianji_config(*args, **kwargs),
        _tianji_effect_description=_tianji_effect_description,
        _tianji_rule_effects=lambda *args, **kwargs: host._tianji_rule_effects(
            *args, **kwargs
        ),
    )


def bind_intelligence(
    host, *, tianji_content_available: Callable[..., Any]
) -> TianjiIntelligenceDependencies:
    return TianjiIntelligenceDependencies(
        _ensure_tianji_state=lambda *args, **kwargs: host._ensure_tianji_state(
            *args, **kwargs
        ),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _tianji_artifact=lambda *args, **kwargs: host._tianji_artifact(*args, **kwargs),
        _tianji_config=lambda *args, **kwargs: host._tianji_config(*args, **kwargs),
        _tianji_reveal=lambda *args, **kwargs: host._tianji_reveal(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
        tianji_content_available=tianji_content_available,
    )


def bind_npcs(
    host,
    *,
    _scaled_effects: Callable[..., Any],
    _stable_rng: Callable[..., Any],
    tianji_content_available: Callable[..., Any],
) -> TianjiNpcsDependencies:
    return TianjiNpcsDependencies(
        _ensure_tianji_state=lambda *args, **kwargs: host._ensure_tianji_state(
            *args, **kwargs
        ),
        _scaled_effects=_scaled_effects,
        _stable_rng=_stable_rng,
        _tianji_artifact=lambda *args, **kwargs: host._tianji_artifact(*args, **kwargs),
        _tianji_config=lambda *args, **kwargs: host._tianji_config(*args, **kwargs),
        _tianji_persistent_npcs=lambda *args, **kwargs: host._tianji_persistent_npcs(
            *args, **kwargs
        ),
        _tianji_reveal=lambda *args, **kwargs: host._tianji_reveal(*args, **kwargs),
        tianji_content_available=tianji_content_available,
    )


def bind_presentation(
    host, *, tianji_content_available: Callable[..., Any]
) -> TianjiPresentationDependencies:
    return TianjiPresentationDependencies(
        _ensure_tianji_state=lambda *args, **kwargs: host._ensure_tianji_state(
            *args, **kwargs
        ),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _natal_artifact_candidate=lambda *args,
        **kwargs: host._natal_artifact_candidate(*args, **kwargs),
        _tianji_config=lambda *args, **kwargs: host._tianji_config(*args, **kwargs),
        _tianji_public_effect=lambda *args, **kwargs: host._tianji_public_effect(
            *args, **kwargs
        ),
        tianji_content_available=tianji_content_available,
    )


def bind_state(
    host,
    *,
    _get_PRIMITIVES: Callable[[], Any],
    _get_TIANJI_GENERATION_VERSION: Callable[[], Any],
    _get_TIANJI_WINDOW_SCHEDULES: Callable[[], Any],
    _stable_rng: Callable[..., Any],
    tianji_content_available: Callable[..., Any],
) -> TianjiStateDependencies:
    return TianjiStateDependencies(
        _get_PRIMITIVES=_get_PRIMITIVES,
        _get_TIANJI_GENERATION_VERSION=_get_TIANJI_GENERATION_VERSION,
        _get_TIANJI_WINDOW_SCHEDULES=_get_TIANJI_WINDOW_SCHEDULES,
        _assign_tianji_holders_for_world=lambda *args,
        **kwargs: host._assign_tianji_holders_for_world(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _generate_tianji_artifacts=lambda *args,
        **kwargs: host._generate_tianji_artifacts(*args, **kwargs),
        _generate_tianji_materials=lambda *args,
        **kwargs: host._generate_tianji_materials(*args, **kwargs),
        _next_tianji_buff_name=lambda *args, **kwargs: host._next_tianji_buff_name(
            *args, **kwargs
        ),
        _next_tianji_name=lambda *args, **kwargs: host._next_tianji_name(
            *args, **kwargs
        ),
        _refresh_tianji_artifact_names=lambda *args,
        **kwargs: host._refresh_tianji_artifact_names(*args, **kwargs),
        _refresh_tianji_buff_names=lambda *args,
        **kwargs: host._refresh_tianji_buff_names(*args, **kwargs),
        _stable_rng=_stable_rng,
        _tianji_config=lambda *args, **kwargs: host._tianji_config(*args, **kwargs),
        tianji_content_available=tianji_content_available,
    )


def bind_tianji(
    host,
    *,
    _get_PRIMITIVES: Callable[[], Any],
    _get_SLOT_WEIGHTS: Callable[[], Any],
    _get_TIANJI_GENERATION_VERSION: Callable[[], Any],
    _get_TIANJI_WINDOW_SCHEDULES: Callable[[], Any],
    _scaled_effects: Callable[..., Any],
    _stable_rng: Callable[..., Any],
    _tianji_effect_description: Callable[..., Any],
    tianji_content_available: Callable[..., Any],
) -> TianjiDependencies:
    return TianjiDependencies(
        forging=bind_forging(
            host,
            _get_SLOT_WEIGHTS=_get_SLOT_WEIGHTS,
            _scaled_effects=_scaled_effects,
            _stable_rng=_stable_rng,
            tianji_content_available=tianji_content_available,
        ),
        generation=bind_generation(
            host,
            _get_PRIMITIVES=_get_PRIMITIVES,
            _get_TIANJI_GENERATION_VERSION=_get_TIANJI_GENERATION_VERSION,
            _stable_rng=_stable_rng,
            _tianji_effect_description=_tianji_effect_description,
        ),
        intelligence=bind_intelligence(
            host, tianji_content_available=tianji_content_available
        ),
        npcs=bind_npcs(
            host,
            _scaled_effects=_scaled_effects,
            _stable_rng=_stable_rng,
            tianji_content_available=tianji_content_available,
        ),
        presentation=bind_presentation(
            host, tianji_content_available=tianji_content_available
        ),
        state=bind_state(
            host,
            _get_PRIMITIVES=_get_PRIMITIVES,
            _get_TIANJI_GENERATION_VERSION=_get_TIANJI_GENERATION_VERSION,
            _get_TIANJI_WINDOW_SCHEDULES=_get_TIANJI_WINDOW_SCHEDULES,
            _stable_rng=_stable_rng,
            tianji_content_available=tianji_content_available,
        ),
    )

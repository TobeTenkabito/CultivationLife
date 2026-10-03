"""Resolve named collaborators at call time, preserving late overrides."""

from typing import Any, Callable
from .dependencies import (
    CraftingMarketDependencies,
    CraftingMaterialsDependencies,
    CraftingForgingDependencies,
    CraftingPreviewDependencies,
    CraftingArtifactsDependencies,
    CraftingPresentationDependencies,
    CraftingDependencies,
)


def bind_crafting_market(
    host, *, make_crafting_material_instance: Callable[..., Any]
) -> CraftingMarketDependencies:
    return CraftingMarketDependencies(
        _crafting_material_defs=lambda *args, **kwargs: host._crafting_material_defs(
            *args, **kwargs
        ),
        _crafting_rules=lambda *args, **kwargs: host._crafting_rules(*args, **kwargs),
        make_crafting_material_instance=make_crafting_material_instance,
        _get_append_tianji_market_offers=lambda: getattr(
            host, "_append_tianji_market_offers", None
        ),
        _get_tianji_material_bought=lambda: getattr(
            host, "_tianji_material_bought", None
        ),
    )


def bind_crafting_materials(host) -> CraftingMaterialsDependencies:
    return CraftingMaterialsDependencies(
        _crafting_material_candidates=lambda *args,
        **kwargs: host._crafting_material_candidates(*args, **kwargs),
        _crafting_material_defs=lambda *args, **kwargs: host._crafting_material_defs(
            *args, **kwargs
        ),
        _crafting_molds=lambda *args, **kwargs: host._crafting_molds(*args, **kwargs),
        _crafting_plant_defs=lambda *args, **kwargs: host._crafting_plant_defs(
            *args, **kwargs
        ),
    )


def bind_crafting_preview(host) -> CraftingPreviewDependencies:
    return CraftingPreviewDependencies(
        _crafting_preview=lambda *args, **kwargs: host._crafting_preview(
            *args, **kwargs
        ),
        _crafting_rules=lambda *args, **kwargs: host._crafting_rules(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _quality_probabilities=lambda *args, **kwargs: host._quality_probabilities(
            *args, **kwargs
        ),
        _resolve_crafting_selection=lambda *args,
        **kwargs: host._resolve_crafting_selection(*args, **kwargs),
        _resolve_mold_rule=lambda *args, **kwargs: host._resolve_mold_rule(
            *args, **kwargs
        ),
    )


def bind_crafting_forging(
    host, *, store_crafted_artifact: Callable[..., Any]
) -> CraftingForgingDependencies:
    return CraftingForgingDependencies(
        _crafting_preview=lambda *args, **kwargs: host._crafting_preview(
            *args, **kwargs
        ),
        _crafting_rules=lambda *args, **kwargs: host._crafting_rules(*args, **kwargs),
        _grant_art_experience=lambda *args, **kwargs: host._grant_art_experience(
            *args, **kwargs
        ),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _weighted_choice=lambda *args, **kwargs: host._weighted_choice(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
        store_crafted_artifact=store_crafted_artifact,
    )


def bind_crafting_artifacts(
    host,
    *,
    artifact_summary: Callable[..., Any],
    name_or_artifact: Callable[..., Any],
    remove_crafted_artifact: Callable[..., Any],
) -> CraftingArtifactsDependencies:
    return CraftingArtifactsDependencies(
        _auction_rng=lambda *args, **kwargs: host._auction_rng(*args, **kwargs),
        _auction_rules=lambda *args, **kwargs: host._auction_rules(*args, **kwargs),
        _bind_crafted_natal_artifact=lambda *args,
        **kwargs: host._bind_crafted_natal_artifact(*args, **kwargs),
        _consign_crafted_artifact=lambda *args,
        **kwargs: host._consign_crafted_artifact(*args, **kwargs),
        _crafting_rules=lambda *args, **kwargs: host._crafting_rules(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _make_crafted_auction_lot=lambda *args,
        **kwargs: host._make_crafted_auction_lot(*args, **kwargs),
        _require_auction_access=lambda *args, **kwargs: host._require_auction_access(
            *args, **kwargs
        ),
        _unbind_crafted_natal_artifact=lambda *args,
        **kwargs: host._unbind_crafted_natal_artifact(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
        artifact_summary=artifact_summary,
        name_or_artifact=name_or_artifact,
        remove_crafted_artifact=remove_crafted_artifact,
    )


def bind_crafting_presentation(
    host, *, crafting_config: Callable[..., Any]
) -> CraftingPresentationDependencies:
    return CraftingPresentationDependencies(
        _auction_location_matches=lambda *args,
        **kwargs: host._auction_location_matches(*args, **kwargs),
        _crafting_material_candidates=lambda *args,
        **kwargs: host._crafting_material_candidates(*args, **kwargs),
        _crafting_molds=lambda *args, **kwargs: host._crafting_molds(*args, **kwargs),
        _crafting_rules=lambda *args, **kwargs: host._crafting_rules(*args, **kwargs),
        crafting_config=crafting_config,
    )


def bind_crafting(
    host,
    *,
    artifact_summary: Callable[..., Any],
    crafting_config: Callable[..., Any],
    make_crafting_material_instance: Callable[..., Any],
    name_or_artifact: Callable[..., Any],
    remove_crafted_artifact: Callable[..., Any],
    store_crafted_artifact: Callable[..., Any],
) -> CraftingDependencies:
    return CraftingDependencies(
        market=bind_crafting_market(
            host, make_crafting_material_instance=make_crafting_material_instance
        ),
        materials=bind_crafting_materials(host),
        preview=bind_crafting_preview(host),
        forging=bind_crafting_forging(
            host, store_crafted_artifact=store_crafted_artifact
        ),
        artifacts=bind_crafting_artifacts(
            host,
            artifact_summary=artifact_summary,
            name_or_artifact=name_or_artifact,
            remove_crafted_artifact=remove_crafted_artifact,
        ),
        presentation=bind_crafting_presentation(host, crafting_config=crafting_config),
    )

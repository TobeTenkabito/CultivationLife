"""Named dependencies for independently testable algorithms."""

from dataclasses import dataclass
from typing import Any, Callable
from ...models import GameState
from ...ports import SavePort, MapPort


@dataclass(frozen=True, slots=True)
class CraftingMarketDependencies:
    _crafting_material_defs: Callable[..., Any]
    _crafting_rules: Callable[..., Any]
    make_crafting_material_instance: Callable[..., Any]
    _get_append_tianji_market_offers: Callable[[], Callable[..., Any] | None]
    _get_tianji_material_bought: Callable[[], Callable[..., Any] | None]

    @property
    def _append_tianji_market_offers(self) -> Callable[..., Any] | None:
        return self._get_append_tianji_market_offers()

    @property
    def _tianji_material_bought(self) -> Callable[..., Any] | None:
        return self._get_tianji_material_bought()


@dataclass(frozen=True, slots=True)
class CraftingMaterialsDependencies:
    _crafting_material_candidates: Callable[..., Any]
    _crafting_material_defs: Callable[..., Any]
    _crafting_molds: Callable[..., Any]
    _crafting_plant_defs: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class CraftingPreviewDependencies:
    _crafting_preview: Callable[..., Any]
    _crafting_rules: Callable[..., Any]
    _load: Callable[[str], GameState]
    _quality_probabilities: Callable[..., Any]
    _resolve_crafting_selection: Callable[..., Any]
    _resolve_mold_rule: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class CraftingForgingDependencies:
    _crafting_preview: Callable[..., Any]
    _crafting_rules: Callable[..., Any]
    _grant_art_experience: Callable[..., Any]
    _load: Callable[[str], GameState]
    _weighted_choice: Callable[..., Any]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]
    store_crafted_artifact: Callable[..., Any]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class CraftingArtifactsDependencies:
    _auction_rng: Callable[..., Any]
    _auction_rules: Callable[..., Any]
    _bind_crafted_natal_artifact: Callable[..., Any]
    _consign_crafted_artifact: Callable[..., Any]
    _crafting_rules: Callable[..., Any]
    _load: Callable[[str], GameState]
    _make_crafted_auction_lot: Callable[..., Any]
    _require_auction_access: Callable[..., Any]
    _unbind_crafted_natal_artifact: Callable[..., Any]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]
    artifact_summary: Callable[..., Any]
    name_or_artifact: Callable[..., Any]
    remove_crafted_artifact: Callable[..., Any]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class CraftingPresentationDependencies:
    _auction_location_matches: Callable[..., Any]
    _crafting_material_candidates: Callable[..., Any]
    _crafting_molds: Callable[..., Any]
    _crafting_rules: Callable[..., Any]
    crafting_config: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class CraftingDependencies:
    market: CraftingMarketDependencies
    materials: CraftingMaterialsDependencies
    preview: CraftingPreviewDependencies
    forging: CraftingForgingDependencies
    artifacts: CraftingArtifactsDependencies
    presentation: CraftingPresentationDependencies

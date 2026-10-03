"""Named ports for demonic workflows."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ...models import GameState
from ...ports import SavePort


@dataclass(frozen=True, slots=True)
class DemonicRefinementDependencies:
    _advance_world_year: Callable[..., Any]
    _compact_world_history: Callable[..., Any]
    _complete_soul_refinement: Callable[..., Any]
    _demonic_rules: Callable[..., Any]
    _ensure_market: Callable[..., Any]
    _load: Callable[[str], GameState]
    _record_era_summary: Callable[..., Any]
    _secluded_refining_years: Callable[..., Any]
    _soul_refine_gain: Callable[..., Any]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class DemonicAnnualDependencies:
    _add_opportunity: Callable[..., Any]
    _demonic_rules: Callable[..., Any]
    _die: Callable[..., Any]
    _sage_scaled_gain: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class DemonicFlowDependencies:
    refinement: DemonicRefinementDependencies
    annual: DemonicAnnualDependencies


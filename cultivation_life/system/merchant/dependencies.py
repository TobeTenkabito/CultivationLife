"""Named capabilities for independently executable game operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ...models import GameState
from ...ports import MapPort, SavePort


@dataclass(frozen=True, slots=True)
class MerchantStateDependencies:
    _crafting_material_defs: Callable[..., Any]
    _merchant_realm_cap: Callable[..., Any]
    _migrate_merchant_routes: Callable[..., Any]
    _get_maps: Callable[[], MapPort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()


@dataclass(frozen=True, slots=True)
class MerchantCatalogDependencies:
    _formation_material_defs: Callable[..., Any]
    _merchant_materials: Callable[..., Any]
    _merchant_power: Callable[..., Any]
    _merchant_realm_cap: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class MerchantCalendarDependencies:
    _ensure_intrigue_personality: Callable[..., Any]
    _ensure_merchant: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _intrigue_enabled: Callable[..., Any]
    _merchant_alliance: Callable[..., Any]
    _merchant_commission_available: Callable[..., Any]
    _merchant_refund: Callable[..., Any]
    _merchant_route_exists: Callable[..., Any]
    _merchant_start_order: Callable[..., Any]
    _merchant_tick_order: Callable[..., Any]
    _get_maps: Callable[[], MapPort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()


@dataclass(frozen=True, slots=True)
class MerchantSettlementDependencies:
    _add_opportunity: Callable[..., Any]
    _all_world_npcs: Callable[..., Any]
    _apply_cultivator_kill: Callable[..., Any]
    _crafting_material_defs: Callable[..., Any]
    _ensure_tianji_state: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _formation_material_defs: Callable[..., Any]
    _merchant_deliver_commission: Callable[..., Any]
    _merchant_intelligence: Callable[..., Any]
    _merchant_log: Callable[..., Any]
    _merchant_notice: Callable[..., Any]
    _merchant_procurement_bonus: Callable[..., Any]
    _tianji_handle_npc_kill: Callable[..., Any]
    _tianji_reveal: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class MerchantWorkDependencies:
    _add_opportunity: Callable[..., Any]
    _advance_soul_erosion_time: Callable[..., Any]
    _advance_world_year: Callable[..., Any]
    _combat: Callable[..., Any]
    _crafting_material_defs: Callable[..., Any]
    _grant_art_experience: Callable[..., Any]
    _merchant_alliance: Callable[..., Any]
    _merchant_intelligence: Callable[..., Any]
    _merchant_notice: Callable[..., Any]
    _merchant_task_ready: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class MerchantPassageDependencies:
    _apply_world_transition: Callable[..., Any]
    _merchant_alliance: Callable[..., Any]
    _merchant_notice: Callable[..., Any]
    _merchant_passage_cost: Callable[..., Any]
    _merchant_route_exists: Callable[..., Any]
    _merchant_site: Callable[..., Any]
    _plan_world_transition: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class MerchantActionDependencies:
    _ensure_market: Callable[..., Any]
    _ensure_merchant: Callable[..., Any]
    _instant_arrival: Callable[..., Any]
    _load: Callable[[str], GameState]
    _merchant_alliance: Callable[..., Any]
    _merchant_board: Callable[..., Any]
    _merchant_influence_key: Callable[..., Any]
    _merchant_notice: Callable[..., Any]
    _merchant_passage: Callable[..., Any]
    _merchant_post: Callable[..., Any]
    _merchant_quote: Callable[..., Any]
    _merchant_realm_cap: Callable[..., Any]
    _merchant_site: Callable[..., Any]
    _merchant_work: Callable[..., Any]
    _get_maps: Callable[[], MapPort]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class MerchantViewDependencies:
    _crafting_molds: Callable[..., Any]
    _ensure_merchant: Callable[..., Any]
    _merchant_alliance: Callable[..., Any]
    _merchant_board: Callable[..., Any]
    _merchant_influence_key: Callable[..., Any]
    _merchant_passage_cost: Callable[..., Any]
    _merchant_power: Callable[..., Any]
    _merchant_procurement_catalog: Callable[..., Any]
    _merchant_site: Callable[..., Any]
    _get_maps: Callable[[], MapPort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()


@dataclass(frozen=True, slots=True)
class MerchantCommissionDependencies:
    _all_world_npcs: Callable[..., Any]
    _crafting_material_defs: Callable[..., Any]
    _crafting_molds: Callable[..., Any]
    _crafting_preview: Callable[..., Any]
    _crafting_rules: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _formation_material_defs: Callable[..., Any]
    _load: Callable[[str], GameState]
    _merchant_alliance: Callable[..., Any]
    _merchant_formation_spec: Callable[..., Any]
    _merchant_influence_key: Callable[..., Any]
    _merchant_items: Callable[..., Any]
    _merchant_materials: Callable[..., Any]
    _merchant_notice: Callable[..., Any]
    _merchant_quote: Callable[..., Any]
    _merchant_route_exists: Callable[..., Any]
    _merchant_weapon_spec: Callable[..., Any]
    _npc_power: Callable[..., Any]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class MerchantExecutionDependencies:
    _all_world_npcs: Callable[..., Any]
    _apply_world_transition: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _merchant_alliance: Callable[..., Any]
    _merchant_deliver_order: Callable[..., Any]
    _merchant_failure_chance: Callable[..., Any]
    _merchant_log: Callable[..., Any]
    _merchant_notice: Callable[..., Any]
    _merchant_realm_cap: Callable[..., Any]
    _merchant_refund: Callable[..., Any]
    _merchant_route_exists: Callable[..., Any]
    _plan_world_transition: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class MerchantDependencies:
    state: MerchantStateDependencies
    catalog: MerchantCatalogDependencies
    calendar: MerchantCalendarDependencies
    settlement: MerchantSettlementDependencies
    work: MerchantWorkDependencies
    passage: MerchantPassageDependencies
    actions: MerchantActionDependencies
    view: MerchantViewDependencies
    commissions: MerchantCommissionDependencies
    execution: MerchantExecutionDependencies

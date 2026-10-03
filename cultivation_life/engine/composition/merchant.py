"""Composition of merchant operations through explicit, late-bound ports."""
from ...system.merchant.dependencies import (
    MerchantActionDependencies,
    MerchantCalendarDependencies,
    MerchantCatalogDependencies,
    MerchantCommissionDependencies,
    MerchantDependencies,
    MerchantExecutionDependencies,
    MerchantPassageDependencies,
    MerchantSettlementDependencies,
    MerchantStateDependencies,
    MerchantViewDependencies,
    MerchantWorkDependencies,
)


def bind_merchant_state(host) -> MerchantStateDependencies:
    return MerchantStateDependencies(
        _crafting_material_defs=lambda *args, **kwargs: host._crafting_material_defs(*args, **kwargs),
        _merchant_realm_cap=lambda *args, **kwargs: host._merchant_realm_cap(*args, **kwargs),
        _migrate_merchant_routes=lambda *args, **kwargs: host._migrate_merchant_routes(*args, **kwargs),
        _get_maps=lambda: host.maps,
    )


def bind_merchant_catalog(host) -> MerchantCatalogDependencies:
    return MerchantCatalogDependencies(
        _formation_material_defs=lambda *args, **kwargs: host._formation_material_defs(*args, **kwargs),
        _merchant_materials=lambda *args, **kwargs: host._merchant_materials(*args, **kwargs),
        _merchant_power=lambda *args, **kwargs: host._merchant_power(*args, **kwargs),
        _merchant_realm_cap=lambda *args, **kwargs: host._merchant_realm_cap(*args, **kwargs),
    )


def bind_merchant_calendar(host) -> MerchantCalendarDependencies:
    return MerchantCalendarDependencies(
        _ensure_intrigue_personality=lambda *args, **kwargs: host._ensure_intrigue_personality(*args, **kwargs),
        _ensure_merchant=lambda *args, **kwargs: host._ensure_merchant(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _intrigue_enabled=lambda *args, **kwargs: host._intrigue_enabled(*args, **kwargs),
        _merchant_alliance=lambda *args, **kwargs: host._merchant_alliance(*args, **kwargs),
        _merchant_commission_available=lambda *args, **kwargs: host._merchant_commission_available(*args, **kwargs),
        _merchant_refund=lambda *args, **kwargs: host._merchant_refund(*args, **kwargs),
        _merchant_route_exists=lambda *args, **kwargs: host._merchant_route_exists(*args, **kwargs),
        _merchant_start_order=lambda *args, **kwargs: host._merchant_start_order(*args, **kwargs),
        _merchant_tick_order=lambda *args, **kwargs: host._merchant_tick_order(*args, **kwargs),
        _get_maps=lambda: host.maps,
    )


def bind_merchant_settlement(host) -> MerchantSettlementDependencies:
    return MerchantSettlementDependencies(
        _add_opportunity=lambda *args, **kwargs: host._add_opportunity(*args, **kwargs),
        _all_world_npcs=lambda *args, **kwargs: host._all_world_npcs(*args, **kwargs),
        _apply_cultivator_kill=lambda *args, **kwargs: host._apply_cultivator_kill(*args, **kwargs),
        _crafting_material_defs=lambda *args, **kwargs: host._crafting_material_defs(*args, **kwargs),
        _ensure_tianji_state=lambda *args, **kwargs: host._ensure_tianji_state(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _formation_material_defs=lambda *args, **kwargs: host._formation_material_defs(*args, **kwargs),
        _merchant_deliver_commission=lambda *args, **kwargs: host._merchant_deliver_commission(*args, **kwargs),
        _merchant_intelligence=lambda *args, **kwargs: host._merchant_intelligence(*args, **kwargs),
        _merchant_log=lambda *args, **kwargs: host._merchant_log(*args, **kwargs),
        _merchant_notice=lambda *args, **kwargs: host._merchant_notice(*args, **kwargs),
        _merchant_procurement_bonus=lambda *args, **kwargs: host._merchant_procurement_bonus(*args, **kwargs),
        _tianji_handle_npc_kill=lambda *args, **kwargs: host._tianji_handle_npc_kill(*args, **kwargs),
        _tianji_reveal=lambda *args, **kwargs: host._tianji_reveal(*args, **kwargs),
    )


def bind_merchant_work(host) -> MerchantWorkDependencies:
    return MerchantWorkDependencies(
        _add_opportunity=lambda *args, **kwargs: host._add_opportunity(*args, **kwargs),
        _advance_soul_erosion_time=lambda *args, **kwargs: host._advance_soul_erosion_time(*args, **kwargs),
        _advance_world_year=lambda *args, **kwargs: host._advance_world_year(*args, **kwargs),
        _combat=lambda *args, **kwargs: host._combat(*args, **kwargs),
        _crafting_material_defs=lambda *args, **kwargs: host._crafting_material_defs(*args, **kwargs),
        _grant_art_experience=lambda *args, **kwargs: host._grant_art_experience(*args, **kwargs),
        _merchant_alliance=lambda *args, **kwargs: host._merchant_alliance(*args, **kwargs),
        _merchant_intelligence=lambda *args, **kwargs: host._merchant_intelligence(*args, **kwargs),
        _merchant_notice=lambda *args, **kwargs: host._merchant_notice(*args, **kwargs),
        _merchant_task_ready=lambda *args, **kwargs: host._merchant_task_ready(*args, **kwargs),
    )


def bind_merchant_passage(host) -> MerchantPassageDependencies:
    return MerchantPassageDependencies(
        _apply_world_transition=lambda *args, **kwargs: host._apply_world_transition(*args, **kwargs),
        _merchant_alliance=lambda *args, **kwargs: host._merchant_alliance(*args, **kwargs),
        _merchant_notice=lambda *args, **kwargs: host._merchant_notice(*args, **kwargs),
        _merchant_passage_cost=lambda *args, **kwargs: host._merchant_passage_cost(*args, **kwargs),
        _merchant_route_exists=lambda *args, **kwargs: host._merchant_route_exists(*args, **kwargs),
        _merchant_site=lambda *args, **kwargs: host._merchant_site(*args, **kwargs),
        _plan_world_transition=lambda *args, **kwargs: host._plan_world_transition(*args, **kwargs),
    )


def bind_merchant_actions(host) -> MerchantActionDependencies:
    return MerchantActionDependencies(
        _ensure_market=lambda *args, **kwargs: host._ensure_market(*args, **kwargs),
        _ensure_merchant=lambda *args, **kwargs: host._ensure_merchant(*args, **kwargs),
        _instant_arrival=lambda *args, **kwargs: host._instant_arrival(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _merchant_alliance=lambda *args, **kwargs: host._merchant_alliance(*args, **kwargs),
        _merchant_board=lambda *args, **kwargs: host._merchant_board(*args, **kwargs),
        _merchant_influence_key=lambda *args, **kwargs: host._merchant_influence_key(*args, **kwargs),
        _merchant_notice=lambda *args, **kwargs: host._merchant_notice(*args, **kwargs),
        _merchant_passage=lambda *args, **kwargs: host._merchant_passage(*args, **kwargs),
        _merchant_post=lambda *args, **kwargs: host._merchant_post(*args, **kwargs),
        _merchant_quote=lambda *args, **kwargs: host._merchant_quote(*args, **kwargs),
        _merchant_realm_cap=lambda *args, **kwargs: host._merchant_realm_cap(*args, **kwargs),
        _merchant_site=lambda *args, **kwargs: host._merchant_site(*args, **kwargs),
        _merchant_work=lambda *args, **kwargs: host._merchant_work(*args, **kwargs),
        _get_maps=lambda: host.maps,
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_merchant_view(host) -> MerchantViewDependencies:
    return MerchantViewDependencies(
        _crafting_molds=lambda *args, **kwargs: host._crafting_molds(*args, **kwargs),
        _ensure_merchant=lambda *args, **kwargs: host._ensure_merchant(*args, **kwargs),
        _merchant_alliance=lambda *args, **kwargs: host._merchant_alliance(*args, **kwargs),
        _merchant_board=lambda *args, **kwargs: host._merchant_board(*args, **kwargs),
        _merchant_influence_key=lambda *args, **kwargs: host._merchant_influence_key(*args, **kwargs),
        _merchant_passage_cost=lambda *args, **kwargs: host._merchant_passage_cost(*args, **kwargs),
        _merchant_power=lambda *args, **kwargs: host._merchant_power(*args, **kwargs),
        _merchant_procurement_catalog=lambda *args, **kwargs: host._merchant_procurement_catalog(*args, **kwargs),
        _merchant_site=lambda *args, **kwargs: host._merchant_site(*args, **kwargs),
        _get_maps=lambda: host.maps,
    )


def bind_merchant_commissions(host) -> MerchantCommissionDependencies:
    return MerchantCommissionDependencies(
        _all_world_npcs=lambda *args, **kwargs: host._all_world_npcs(*args, **kwargs),
        _crafting_material_defs=lambda *args, **kwargs: host._crafting_material_defs(*args, **kwargs),
        _crafting_molds=lambda *args, **kwargs: host._crafting_molds(*args, **kwargs),
        _crafting_preview=lambda *args, **kwargs: host._crafting_preview(*args, **kwargs),
        _crafting_rules=lambda *args, **kwargs: host._crafting_rules(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _formation_material_defs=lambda *args, **kwargs: host._formation_material_defs(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _merchant_alliance=lambda *args, **kwargs: host._merchant_alliance(*args, **kwargs),
        _merchant_formation_spec=lambda *args, **kwargs: host._merchant_formation_spec(*args, **kwargs),
        _merchant_influence_key=lambda *args, **kwargs: host._merchant_influence_key(*args, **kwargs),
        _merchant_items=lambda *args, **kwargs: host._merchant_items(*args, **kwargs),
        _merchant_materials=lambda *args, **kwargs: host._merchant_materials(*args, **kwargs),
        _merchant_notice=lambda *args, **kwargs: host._merchant_notice(*args, **kwargs),
        _merchant_quote=lambda *args, **kwargs: host._merchant_quote(*args, **kwargs),
        _merchant_route_exists=lambda *args, **kwargs: host._merchant_route_exists(*args, **kwargs),
        _merchant_weapon_spec=lambda *args, **kwargs: host._merchant_weapon_spec(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: host._npc_power(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_merchant_execution(host) -> MerchantExecutionDependencies:
    return MerchantExecutionDependencies(
        _all_world_npcs=lambda *args, **kwargs: host._all_world_npcs(*args, **kwargs),
        _apply_world_transition=lambda *args, **kwargs: host._apply_world_transition(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _merchant_alliance=lambda *args, **kwargs: host._merchant_alliance(*args, **kwargs),
        _merchant_deliver_order=lambda *args, **kwargs: host._merchant_deliver_order(*args, **kwargs),
        _merchant_failure_chance=lambda *args, **kwargs: host._merchant_failure_chance(*args, **kwargs),
        _merchant_log=lambda *args, **kwargs: host._merchant_log(*args, **kwargs),
        _merchant_notice=lambda *args, **kwargs: host._merchant_notice(*args, **kwargs),
        _merchant_realm_cap=lambda *args, **kwargs: host._merchant_realm_cap(*args, **kwargs),
        _merchant_refund=lambda *args, **kwargs: host._merchant_refund(*args, **kwargs),
        _merchant_route_exists=lambda *args, **kwargs: host._merchant_route_exists(*args, **kwargs),
        _plan_world_transition=lambda *args, **kwargs: host._plan_world_transition(*args, **kwargs),
    )


def bind_merchant(host) -> MerchantDependencies:
    return MerchantDependencies(
        state=bind_merchant_state(host),
        catalog=bind_merchant_catalog(host),
        calendar=bind_merchant_calendar(host),
        settlement=bind_merchant_settlement(host),
        work=bind_merchant_work(host),
        passage=bind_merchant_passage(host),
        actions=bind_merchant_actions(host),
        view=bind_merchant_view(host),
        commissions=bind_merchant_commissions(host),
        execution=bind_merchant_execution(host),
    )

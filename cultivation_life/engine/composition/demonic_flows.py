"""Compose demonic flows; collaborators resolve at call time."""
from ...system.demonic.dependencies import (
    DemonicAnnualDependencies,
    DemonicFlowDependencies,
    DemonicRefinementDependencies,
)


def bind_refinement(host) -> DemonicRefinementDependencies:
    return DemonicRefinementDependencies(
        _advance_world_year=lambda *args, **kwargs: host._advance_world_year(*args, **kwargs),
        _compact_world_history=lambda *args, **kwargs: host._compact_world_history(*args, **kwargs),
        _complete_soul_refinement=lambda *args, **kwargs: host._complete_soul_refinement(*args, **kwargs),
        _demonic_rules=lambda *args, **kwargs: host._demonic_rules(*args, **kwargs),
        _ensure_market=lambda *args, **kwargs: host._ensure_market(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _record_era_summary=lambda *args, **kwargs: host._record_era_summary(*args, **kwargs),
        _secluded_refining_years=lambda *args, **kwargs: host._secluded_refining_years(*args, **kwargs),
        _soul_refine_gain=lambda *args, **kwargs: host._soul_refine_gain(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_annual(host) -> DemonicAnnualDependencies:
    return DemonicAnnualDependencies(
        _add_opportunity=lambda *args, **kwargs: host._add_opportunity(*args, **kwargs),
        _demonic_rules=lambda *args, **kwargs: host._demonic_rules(*args, **kwargs),
        _die=lambda *args, **kwargs: host._die(*args, **kwargs),
        _sage_scaled_gain=lambda *args, **kwargs: host._sage_scaled_gain(*args, **kwargs),
    )


def bind_demonic_flows(host) -> DemonicFlowDependencies:
    return DemonicFlowDependencies(
        refinement=bind_refinement(host),
        annual=bind_annual(host),
    )

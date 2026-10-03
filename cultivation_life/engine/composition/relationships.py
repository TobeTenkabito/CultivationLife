"""Compose relationships flows; collaborators resolve at call time."""
from ...system.relationships.dependencies import (
    CaptivityDependencies,
    ConcubineActionDependencies,
    DependentLifecycleDependencies,
    RelationshipFlowDependencies,
    RelationshipSanctionDependencies,
    RelationshipViolenceDependencies,
)


def bind_captivity(host) -> CaptivityDependencies:
    return CaptivityDependencies(
        _break_capture_relationship=lambda *args, **kwargs: host._break_capture_relationship(*args, **kwargs),
        _convert_to_puppet=lambda *args, **kwargs: host._convert_to_puppet(*args, **kwargs),
        _demonic_rules=lambda *args, **kwargs: host._demonic_rules(*args, **kwargs),
        _die=lambda *args, **kwargs: host._die(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _instantiate_event=lambda *args, **kwargs: host._instantiate_event(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _npc_realm_name=lambda *args, **kwargs: host._npc_realm_name(*args, **kwargs),
        _player_intrinsic_combat_power=lambda *args, **kwargs: host._player_intrinsic_combat_power(*args, **kwargs),
        _relationship_combat_power=lambda *args, **kwargs: host._relationship_combat_power(*args, **kwargs),
        _remove_conversion_target=lambda *args, **kwargs: host._remove_conversion_target(*args, **kwargs),
        _restore_captive_npc=lambda *args, **kwargs: host._restore_captive_npc(*args, **kwargs),
        _stable_gender=lambda *args, **kwargs: host._stable_gender(*args, **kwargs),
        _get_events_by_id=lambda: host.events_by_id,
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        relationship_violence=lambda *args, **kwargs: host.relationship_violence(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_sanctions(host) -> RelationshipSanctionDependencies:
    return RelationshipSanctionDependencies(
        _end_sanctioned_relationship=lambda *args, **kwargs: host._end_sanctioned_relationship(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _instantiate_event=lambda *args, **kwargs: host._instantiate_event(*args, **kwargs),
        _record_revenge_trigger=lambda *args, **kwargs: host._record_revenge_trigger(*args, **kwargs),
        _relationship_sanction_candidates=lambda *args, **kwargs: host._relationship_sanction_candidates(*args, **kwargs),
        _sage_scaled_gain=lambda *args, **kwargs: host._sage_scaled_gain(*args, **kwargs),
        _set_person_affinity=lambda *args, **kwargs: host._set_person_affinity(*args, **kwargs),
        _get_events_by_id=lambda: host.events_by_id,
    )


def bind_dependents(host) -> DependentLifecycleDependencies:
    return DependentLifecycleDependencies(
        _all_world_npcs=lambda *args, **kwargs: host._all_world_npcs(*args, **kwargs),
        _default_npc_main_technique=lambda *args, **kwargs: host._default_npc_main_technique(*args, **kwargs),
        _escape_chance=lambda *args, **kwargs: host._escape_chance(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _instantiate_event=lambda *args, **kwargs: host._instantiate_event(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: host._npc_power(*args, **kwargs),
        _npc_realm_name=lambda *args, **kwargs: host._npc_realm_name(*args, **kwargs),
        _owner_equipment_candidates=lambda *args, **kwargs: host._owner_equipment_candidates(*args, **kwargs),
        _owner_request_chance=lambda *args, **kwargs: host._owner_request_chance(*args, **kwargs),
        _owner_technique_candidates=lambda *args, **kwargs: host._owner_technique_candidates(*args, **kwargs),
        _proposal_revenge_chance=lambda *args, **kwargs: host._proposal_revenge_chance(*args, **kwargs),
        _rank=lambda *args, **kwargs: host._rank(*args, **kwargs),
        _record_revenge_trigger=lambda *args, **kwargs: host._record_revenge_trigger(*args, **kwargs),
        _revenge_ready=lambda *args, **kwargs: host._revenge_ready(*args, **kwargs),
        _runtime_from_status=lambda *args, **kwargs: host._runtime_from_status(*args, **kwargs),
        _set_concubine_status=lambda *args, **kwargs: host._set_concubine_status(*args, **kwargs),
        _world_realm_cap=lambda *args, **kwargs: host._world_realm_cap(*args, **kwargs),
        _get_events_by_id=lambda: host.events_by_id,
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_concubines(host) -> ConcubineActionDependencies:
    return ConcubineActionDependencies(
        _add_opportunity=lambda *args, **kwargs: host._add_opportunity(*args, **kwargs),
        _concubine_target=lambda *args, **kwargs: host._concubine_target(*args, **kwargs),
        _convert_to_puppet=lambda *args, **kwargs: host._convert_to_puppet(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _normalize_concubine=lambda *args, **kwargs: host._normalize_concubine(*args, **kwargs),
        _rank=lambda *args, **kwargs: host._rank(*args, **kwargs),
        _set_person_affinity=lambda *args, **kwargs: host._set_person_affinity(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_violence(host) -> RelationshipViolenceDependencies:
    return RelationshipViolenceDependencies(
        _apply_cultivator_kill=lambda *args, **kwargs: host._apply_cultivator_kill(*args, **kwargs),
        _combat=lambda *args, **kwargs: host._combat(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: host._npc_power(*args, **kwargs),
        _promote_cached_npc=lambda *args, **kwargs: host._promote_cached_npc(*args, **kwargs),
        _public_party=lambda *args, **kwargs: host._public_party(*args, **kwargs),
        assert_buddhist_operation_allowed=lambda *args, **kwargs: host.assert_buddhist_operation_allowed(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_relationships(host) -> RelationshipFlowDependencies:
    return RelationshipFlowDependencies(
        captivity=bind_captivity(host),
        sanctions=bind_sanctions(host),
        dependents=bind_dependents(host),
        concubines=bind_concubines(host),
        violence=bind_violence(host),
    )

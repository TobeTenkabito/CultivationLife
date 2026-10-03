"""Explicit wiring; resolve host methods and storage at the time of use."""
from .dependencies import (
    CourtStateDependencies,
    CourtGovernanceDependencies,
    CourtLifecycleDependencies,
    YaochiDependencies,
)

def bind_state(host) -> CourtStateDependencies:
    return CourtStateDependencies(
        _court_autonomous_votes=lambda *args, **kwargs: host._court_autonomous_votes(*args, **kwargs),
        _court_config=lambda *args, **kwargs: host._court_config(*args, **kwargs),
        _court_conflicts=lambda *args, **kwargs: host._court_conflicts(*args, **kwargs),
        _court_enact_decree=lambda *args, **kwargs: host._court_enact_decree(*args, **kwargs),
        _court_examination=lambda *args, **kwargs: host._court_examination(*args, **kwargs),
        _court_finish_unattended=lambda *args, **kwargs: host._court_finish_unattended(*args, **kwargs),
        _court_govern=lambda *args, **kwargs: host._court_govern(*args, **kwargs),
        _court_grade_for_realm=lambda *args, **kwargs: host._court_grade_for_realm(*args, **kwargs),
        _court_holder_ids=lambda *args, **kwargs: host._court_holder_ids(*args, **kwargs),
        _court_honor_pledge=lambda *args, **kwargs: host._court_honor_pledge(*args, **kwargs),
        _court_normalize=lambda *args, **kwargs: host._court_normalize(*args, **kwargs),
        _court_open_election=lambda *args, **kwargs: host._court_open_election(*args, **kwargs),
        _court_open_next_queued_election=lambda *args, **kwargs: host._court_open_next_queued_election(*args, **kwargs),
        _court_pay_stipend=lambda *args, **kwargs: host._court_pay_stipend(*args, **kwargs),
        _court_player_controls=lambda *args, **kwargs: host._court_player_controls(*args, **kwargs),
        _court_prune_decrees=lambda *args, **kwargs: host._court_prune_decrees(*args, **kwargs),
        _court_resolve_election_round=lambda *args, **kwargs: host._court_resolve_election_round(*args, **kwargs),
        _court_retire_unavailable=lambda *args, **kwargs: host._court_retire_unavailable(*args, **kwargs),
        _court_schedule_elections=lambda *args, **kwargs: host._court_schedule_elections(*args, **kwargs),
        _court_spend_influence=lambda *args, **kwargs: host._court_spend_influence(*args, **kwargs),
        _court_vote_law=lambda *args, **kwargs: host._court_vote_law(*args, **kwargs),
        _ensure_heavenly_court=lambda *args, **kwargs: host._ensure_heavenly_court(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _npc_faction_id=lambda *args, **kwargs: host._npc_faction_id(*args, **kwargs),
        _npc_realm_name=lambda *args, **kwargs: host._npc_realm_name(*args, **kwargs),
        _player_court_representative=lambda *args, **kwargs: host._player_court_representative(*args, **kwargs),
        _sect_members=lambda *args, **kwargs: host._sect_members(*args, **kwargs),
        _sync_player_court_identity=lambda *args, **kwargs: host._sync_player_court_identity(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )

def bind_governance(host) -> CourtGovernanceDependencies:
    return CourtGovernanceDependencies(
        _court_config=lambda *args, **kwargs: host._court_config(*args, **kwargs),
        _court_conflicts=lambda *args, **kwargs: host._court_conflicts(*args, **kwargs),
        _court_enact_decree=lambda *args, **kwargs: host._court_enact_decree(*args, **kwargs),
        _court_retire_unavailable=lambda *args, **kwargs: host._court_retire_unavailable(*args, **kwargs),
        _court_vote_law=lambda *args, **kwargs: host._court_vote_law(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
    )

def bind_lifecycle(host) -> CourtLifecycleDependencies:
    return CourtLifecycleDependencies(
        _court_config=lambda *args, **kwargs: host._court_config(*args, **kwargs),
        _court_open_election=lambda *args, **kwargs: host._court_open_election(*args, **kwargs),
        _court_open_next_queued_election=lambda *args, **kwargs: host._court_open_next_queued_election(*args, **kwargs),
        _court_prune_decrees=lambda *args, **kwargs: host._court_prune_decrees(*args, **kwargs),
        _court_resolve_election_round=lambda *args, **kwargs: host._court_resolve_election_round(*args, **kwargs),
    )

def bind_yaochi(host) -> YaochiDependencies:
    return YaochiDependencies(
        _add_court_merit=lambda *args, **kwargs: host._add_court_merit(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _sync_player_court_identity=lambda *args, **kwargs: host._sync_player_court_identity(*args, **kwargs),
        advance=lambda *args, **kwargs: host.advance(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


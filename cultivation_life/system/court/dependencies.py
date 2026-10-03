"""Capabilities required by each court responsibility, independent of an engine."""
from dataclasses import dataclass
from typing import Any, Callable
from ...models import GameState
from ...ports import SavePort

@dataclass(frozen=True, slots=True)
class CourtStateDependencies:
    _court_autonomous_votes: Callable[..., Any]
    _court_config: Callable[..., Any]
    _court_conflicts: Callable[..., Any]
    _court_enact_decree: Callable[..., Any]
    _court_examination: Callable[..., Any]
    _court_finish_unattended: Callable[..., Any]
    _court_govern: Callable[..., Any]
    _court_grade_for_realm: Callable[..., Any]
    _court_holder_ids: Callable[..., Any]
    _court_honor_pledge: Callable[..., Any]
    _court_normalize: Callable[..., Any]
    _court_open_election: Callable[..., Any]
    _court_open_next_queued_election: Callable[..., Any]
    _court_pay_stipend: Callable[..., Any]
    _court_player_controls: Callable[..., Any]
    _court_prune_decrees: Callable[..., Any]
    _court_resolve_election_round: Callable[..., Any]
    _court_retire_unavailable: Callable[..., Any]
    _court_schedule_elections: Callable[..., Any]
    _court_spend_influence: Callable[..., Any]
    _court_vote_law: Callable[..., Any]
    _ensure_heavenly_court: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _load: Callable[[str], GameState]
    _npc_faction_id: Callable[..., Any]
    _npc_realm_name: Callable[..., Any]
    _player_court_representative: Callable[..., Any]
    _sect_members: Callable[..., Any]
    _sync_player_court_identity: Callable[..., Any]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()

@dataclass(frozen=True, slots=True)
class CourtGovernanceDependencies:
    _court_config: Callable[..., Any]
    _court_conflicts: Callable[..., Any]
    _court_enact_decree: Callable[..., Any]
    _court_retire_unavailable: Callable[..., Any]
    _court_vote_law: Callable[..., Any]
    _find_npc: Callable[..., Any]

@dataclass(frozen=True, slots=True)
class CourtLifecycleDependencies:
    _court_config: Callable[..., Any]
    _court_open_election: Callable[..., Any]
    _court_open_next_queued_election: Callable[..., Any]
    _court_prune_decrees: Callable[..., Any]
    _court_resolve_election_round: Callable[..., Any]

@dataclass(frozen=True, slots=True)
class YaochiDependencies:
    _add_court_merit: Callable[..., Any]
    _load: Callable[[str], GameState]
    _sync_player_court_identity: Callable[..., Any]
    advance: Callable[..., Any]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()


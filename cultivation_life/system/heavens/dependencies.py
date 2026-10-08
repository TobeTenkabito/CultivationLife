"""Explicit capabilities for persistence and local M1 gameplay."""
from dataclasses import dataclass
from typing import Callable

from ...models import GameState
from ...ports import SavePort
from .definitions import HeavensDefinitions


@dataclass(frozen=True, slots=True)
class HeavensDependencies:
    load_game: Callable[[str], GameState]
    get_store: Callable[[], SavePort]
    get_definitions: Callable[[], HeavensDefinitions]
    accept_committed: Callable[[GameState], None]
    invalidate_game: Callable[[str], None]
    read_actor_facts: Callable | None = None
    create_visitor: Callable | None = None
    resolve_person: Callable | None = None
    person_available: Callable | None = None
    quote_materials: Callable | None = None
    reserve_resources: Callable | None = None
    refund_resources: Callable | None = None
    advance_year: Callable | None = None
    settle_activity_units: Callable | None = None
    unit_years: Callable | None = None
    opportunity_base: Callable | None = None
    grant_progress: Callable | None = None
    reconcile_tasks: Callable | None = None
    grant_stones: Callable | None = None
    read_mirror_facts: Callable | None = None
    mirror_materials: Callable | None = None
    enter_mirror: Callable | None = None
    leave_mirror: Callable | None = None
    fight_mirror: Callable | None = None
    read_ruins_facts: Callable | None = None
    ruins_material: Callable | None = None
    enter_ruins: Callable | None = None
    leave_ruins: Callable | None = None
    fight_ruins: Callable | None = None
    read_omen_facts: Callable | None = None
    read_visit_facts: Callable | None = None
    move_visit: Callable | None = None
    read_mission_facts: Callable | None = None
    move_researcher: Callable | None = None
    advance_researchers: Callable | None = None
    migration_candidates: Callable | None = None

    read_survey_facts: Callable | None = None
    survey_candidates: Callable | None = None
    move_surveyor: Callable | None = None
    advance_survey: Callable | None = None
    prepare_ruins: Callable | None = None
    prepare_mirror: Callable | None = None

    frontier_authority: Callable | None = None
    frontier_candidate: Callable | None = None
    frontier_deploy: Callable | None = None
    frontier_player_reason: Callable | None = None
    frontier_route_reason: Callable | None = None
    frontier_move: Callable | None = None

    campaign_authority: Callable | None = None
    campaign_roster: Callable | None = None
    campaign_deploy: Callable | None = None
    campaign_facts: Callable | None = None
    campaign_road: Callable | None = None
    campaign_move: Callable | None = None
    campaign_materials: Callable | None = None
    campaign_fight: Callable | None = None
    campaign_battle: Callable | None = None
    campaign_finance: Callable | None = None
    campaign_world_open: Callable | None = None
    campaign_escape_plan: Callable | None = None
    campaign_escape: Callable | None = None
    campaign_relief: Callable | None = None
    campaign_release: Callable | None = None
    incident_facts: Callable | None = None
    incident_relief: Callable | None = None
    incident_restore: Callable | None = None
    incident_field_effect: Callable | None = None
    incident_mana: Callable | None = None

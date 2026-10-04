from __future__ import annotations

from ..system import realm_ascension  # register base-world route defaults first
from ..system.buddhist_system import BuddhistSystemMixin
from ..system.path_modifiers import modifier

import random
from pathlib import Path
from typing import Any
from ..content_registry import WORLD_SYSTEMS, STORY_COMBAT_SCENARIOS, CONTENT_DOCUMENTS, ContentError
from ..system.combat_system import BattleUnit
from ..event_repository import EventRepository
from ..system.demonic_system import DemonicSystemMixin
from ..models import GameState, HistoryRecord, Item, Player, SectNpc, SectState
from ..system.map_system import MapCatalog
from ..storage import SaveStore
from ..achievements import AchievementSystem, load_achievement_definitions
from ..runtime import decode_rng, encode_rng, now_iso
from ..system.upper_institutions import UpperInstitutionMixin
from ..system.natal_artifact_system import NatalArtifactSystemMixin
from ..system.monster_bloodline_system import MonsterBloodlineSystemMixin, bloodline_content_available
from ..system.ghost_system import GhostSystemMixin
from ..system.sage_system import SageSystemMixin
from ..system.concubine_system import ConcubineSystemMixin
from ..system.family_system import FamilySystemMixin
from . import engine_world_runtime as world_runtime
from . import engine_event_runtime as event_runtime
from . import engine_combat_runtime as combat_runtime
from . import engine_presentation as presentation_runtime
from . import engine_persistence as persistence_runtime
from .orchestration import session as session
from .orchestration import advancement as advancement
from .actions import cultivation as cultivation_actions
from .actions import world_travel as world_travel_actions
from .actions import factions as faction_actions
from .actions import encounters as encounter_actions
from .actions import inventory as inventory_actions
from .actions import relationships as relationship_actions
from .actions import asura as asura_actions
from .events import choices as choices
from .progression import breakthroughs as breakthroughs
from .progression import trials as trials
from .events import encounters as encounters
from .events import effects as effects
from .world import npcs as npcs
from .world import relationships as world_relationships
from .world import factions as world_factions
from .world import hostility as hostility_runtime
from .presentation import character as character_view
from .presentation import world as world_view
from .presentation import factions as faction_view
from .wiring import bind_dependencies, bind_npc_class_dependencies
from .transactions import serialized_commands
from ..system.court import state as court_state
from ..system.court import governance as court_governance
from ..system.court import lifecycle as court_lifecycle
from ..system.court import yaochi as court_yaochi


from ..system import tianji_system as tianji_compat
from ..system.tianji import forging as tianji_forging
from ..system.tianji import generation as tianji_generation
from ..system.tianji import intelligence as tianji_intelligence
from ..system.tianji import npcs as tianji_npcs
from ..system.tianji import presentation as tianji_presentation
from ..system.tianji import state as tianji_state
from ..system import intrigue_system as intrigue_compat
from ..system.intrigue import governance as intrigue_governance
from ..system.intrigue import guests as intrigue_guests
from ..system.intrigue import presentation as intrigue_presentation
from ..system.intrigue import recruitment as intrigue_recruitment
from ..system.intrigue import resolutions as intrigue_resolutions
from ..system.intrigue import runtime as intrigue_runtime
from ..system.intrigue import state as intrigue_state


from ..system.economy import exchange as economy_exchange
from ..system.economy import arts as economy_arts
from ..system.economy import market as economy_market
from ..system.economy import private_trade as economy_private_trade
from ..system.economy import spirit_fields as economy_spirit_fields
from ..system.economy import treasure as economy_treasure
from ..system import exchange_system as exchange_compat
from ..system.crafting import market as crafting_market
from ..system.crafting import materials as crafting_materials
from ..system.crafting import forging as crafting_forging
from ..system.crafting import preview as crafting_preview
from ..system.crafting import artifacts as crafting_artifacts
from ..system.crafting import presentation as crafting_presentation
from ..system import crafting_system as crafting_compat
from ..system.formation import market as formation_market
from ..system.formation import loadouts as formation_loadouts
from ..system.formation import ground as formation_ground
from ..system.formation import npcs as formation_npcs
from ..system.formation import presentation as formation_presentation
from ..system import formation_system as formation_compat
from ..system.economy import auctions as economy_auctions
from ..system.economy import black_market as economy_black_market
from ..system import economy_system as economy_compat


from ..system.guixu import state as guixu_state
from ..system.guixu import calendar as guixu_calendar
from ..system.guixu import npcs as guixu_npcs
from ..system.guixu import rewards as guixu_rewards
from ..system.guixu import encounters as guixu_encounters
from ..system.guixu import actions as guixu_actions
from ..system.guixu import presentation as guixu_presentation
from ..system import guixu_system as guixu_compat
from ..system.war import state as war_state
from ..system.war import diplomacy as war_diplomacy
from ..system.war import power as war_power
from ..system.war import combat as war_combat
from ..system.war import lifecycle as war_lifecycle
from ..system.war import peace as war_peace
from ..system.war import actions as war_actions
from ..system.war import presentation as war_presentation
from ..system import war_system as war_compat


from .orchestration import world_time as world_time
from .. import map_runtime as map_travel
from ..system import teleport_system as teleport_actions
from ..system.merchant import state as merchant_state
from ..system.merchant import catalog as merchant_catalog
from ..system.merchant import calendar as merchant_calendar
from ..system.merchant import settlement as merchant_settlement
from ..system.merchant import work as merchant_work
from ..system.merchant import passage as merchant_passage
from ..system import merchant_system as merchant_actions
from ..system.merchant import presentation as merchant_view
from ..system import merchant_commission_system as merchant_commissions
from ..system import merchant_execution_system as merchant_execution
from ..system import doctrine_system as doctrine_actions
from ..system import doctrine_fusion_system as doctrine_fusion
from ..system import cultivation_session as cultivation_session
from ..system import immortal_system as immortal_actions
from ..system import immortal_body_system as immortal_body
from ..system import immortal_aperture as immortal_aperture


from ..system.ghost import identity as ghost_identity
from ..system.ghost import calendar as ghost_calendar
from ..system.ghost import erosion as ghost_erosion
from ..system.ghost import reincarnation as ghost_reincarnation
from ..system.relationships import captivity as relationships_captivity
from ..system.demonic import refinement as demonic_refinement
from ..system.demonic import annual as demonic_annual
from ..system import relationship_rules
from ..system.relationships import sanctions as relationships_sanctions
from ..system.relationships import dependents as relationships_dependents
from ..system.relationships import concubines as relationships_concubines
from ..system.relationships import violence as relationships_violence
from ..system.buddhist import actions as buddhist_actions
from ..system.buddhist import assembly as buddhist_assembly


@serialized_commands
class GameEngine(UpperInstitutionMixin, BuddhistSystemMixin, FamilySystemMixin, SageSystemMixin, ConcubineSystemMixin, GhostSystemMixin, MonsterBloodlineSystemMixin, NatalArtifactSystemMixin, DemonicSystemMixin):
    def __init__(self, project_root: Path, save_directory: Path | None = None):
        self.root = project_root
        self.store = SaveStore(save_directory or project_root / "data" / "saves")
        achievement_document = CONTENT_DOCUMENTS.get(
            "achievements.json", {"schema_version": 1, "achievements": []}
        )
        self.achievements = AchievementSystem(
            load_achievement_definitions(achievement_document), self.store.directory,
        )
        map_document = CONTENT_DOCUMENTS.get("maps.json")
        self.maps = (
            MapCatalog(map_document, set(WORLD_SYSTEMS.get("world_profiles", {})))
            if map_document else MapCatalog.load(
                project_root / "content" / "maps.json", set(WORLD_SYSTEMS.get("world_profiles", {}))
            )
        )
        event_documents = [
            (name, document) for name, document in CONTENT_DOCUMENTS.items()
            if name == "events.json" or name.endswith("_events.json")
        ]
        event_repository = (
            EventRepository.from_documents(event_documents, allow_overrides=True)
            if event_documents else EventRepository.load(project_root / "content")
        )
        self.events = event_repository.events
        self.events_by_id = event_repository.by_id
        missing_scenarios = set(STORY_COMBAT_SCENARIOS) - set(self.events_by_id)
        if missing_scenarios:
            raise ContentError(f"剧情战斗编队引用不存在的事件：{sorted(missing_scenarios)}")
        self._dependencies = bind_dependencies(
            self, bloodline_content_available=lambda: bloodline_content_available(),
        )

    def _advance_world_year(self, game: GameState, rng: random.Random, era_news: list[str], *, encounters: bool=True) -> bool:
        from ..system import spatial
        spatial.tick(game, rng, self.maps)
        if game.player.world in spatial.SPECIAL_WORLDS:
            return world_time.advance_spatial_year(self._dependencies.time.world_year, game, rng)
        return world_time._advance_world_year(self._dependencies.time.world_year, game, rng, era_news, encounters=encounters)

    def travel_map(self, game_id: str, destination: str) -> dict[str, Any]:
        return map_travel.travel_map(self._dependencies.time.travel, game_id, destination)

    def _instant_arrival(self, game, destination):
        return teleport_actions._instant_arrival(self._dependencies.time.teleport, game, destination)

    def teleport_action(self, game_id, action, destination=None):
        return teleport_actions.teleport_action(self._dependencies.time.teleport, game_id, action, destination)

    @staticmethod
    def _merchant_realm_cap(world):
        return merchant_state._merchant_realm_cap(world)

    def _ensure_merchant(self, game) -> bool:
        return merchant_state._ensure_merchant(self._dependencies.merchant.state, game)

    def _merchant_alliance(self, game, world, alliance_id):
        return merchant_state._merchant_alliance(game, world, alliance_id)

    def _merchant_site(self, game, alliance):
        return merchant_state._merchant_site(game, alliance)

    @staticmethod
    def _merchant_influence_key(member):
        return merchant_state._merchant_influence_key(member)

    def _merchant_power(self, alliance):
        return merchant_state._merchant_power(alliance)

    def _merchant_notice(self, game, message):
        return merchant_state._merchant_notice(game, message)

    def _merchant_materials(self, world):
        return merchant_state._merchant_materials(self._dependencies.merchant.state, world)

    def _merchant_board(self, game, alliance):
        return merchant_catalog._merchant_board(self._dependencies.merchant.catalog, game, alliance)

    def _advance_merchant_year(self, game):
        return merchant_calendar._advance_merchant_year(self._dependencies.merchant.calendar, game)

    def _merchant_deliver_order(self, game, order):
        return merchant_settlement._merchant_deliver_order(self._dependencies.merchant.settlement, game, order)

    def _merchant_task_ready(self, game, task):
        return merchant_work._merchant_task_ready(game, task)

    def _merchant_work(self, game, rng):
        return merchant_work._merchant_work(self._dependencies.merchant.work, game, rng)

    def _merchant_passage(self, game, alliance, destination):
        return merchant_passage._merchant_passage(self._dependencies.merchant.passage, game, alliance, destination)

    @staticmethod
    def _merchant_passage_cost(game, destination):
        return merchant_passage._merchant_passage_cost(game, destination)

    def merchant_action(self, game_id, action, payload=None):
        return merchant_actions.merchant_action(self._dependencies.merchant.actions, game_id, action, payload)

    def _merchant_post(self, game, alliance, payload):
        return merchant_actions._merchant_post(self._dependencies.merchant.actions, game, alliance, payload)

    def _public_merchant(self, game):
        return merchant_view._public_merchant(self._dependencies.merchant.view, game)

    def _merchant_intelligence(self, game, world, stars, rng):
        return merchant_settlement._merchant_intelligence(self._dependencies.merchant.settlement, game, world, stars, rng)

    def _merchant_commission_available(self, order):
        return merchant_commissions._merchant_commission_available(self._dependencies.merchant.commissions, order)

    def _merchant_items(self, world):
        return merchant_commissions._merchant_items(world)

    def _merchant_procurement_catalog(self, game, alliance):
        return merchant_commissions._merchant_procurement_catalog(self._dependencies.merchant.commissions, game, alliance)

    def _merchant_formation_spec(self, game, world, payload):
        return merchant_commissions._merchant_formation_spec(self._dependencies.merchant.commissions, game, world, payload)

    def _merchant_weapon_spec(self, world, payload):
        return merchant_commissions._merchant_weapon_spec(self._dependencies.merchant.commissions, world, payload)

    def _merchant_quote(self, game, alliance, payload):
        return merchant_commissions._merchant_quote(self._dependencies.merchant.commissions, game, alliance, payload)

    def preview_merchant_commission(self, game_id, payload):
        return merchant_commissions.preview_merchant_commission(self._dependencies.merchant.commissions, game_id, payload)

    def _merchant_deliver_commission(self, game, order):
        return merchant_settlement._merchant_deliver_commission(self._dependencies.merchant.settlement, game, order)

    def _merchant_procurement_bonus(self, game, order, rng):
        return merchant_settlement._merchant_procurement_bonus(self._dependencies.merchant.settlement, game, order, rng)

    def debug_merchant_hq(self, game_id, alliance_id):
        return merchant_commissions.debug_merchant_hq(self._dependencies.merchant.commissions, game_id, alliance_id)

    def _merchant_route_exists(self, game, alliance, world):
        return merchant_execution._merchant_route_exists(self._dependencies.merchant.execution, game, alliance, world)

    def _migrate_merchant_routes(self, game):
        return merchant_execution._migrate_merchant_routes(self._dependencies.merchant.execution, game)

    @staticmethod
    def _merchant_log(order, age, message):
        return merchant_settlement._merchant_log(order, age, message)

    def _merchant_refund(self, game, order, status, reason, fee_refund=0):
        return merchant_settlement._merchant_refund(self._dependencies.merchant.settlement, game, order, status, reason, fee_refund)

    @staticmethod
    def _merchant_failure_chance(stars, worker_realm, required_realm):
        return merchant_execution._merchant_failure_chance(stars, worker_realm, required_realm)

    def _merchant_start_order(self, game, order, rng):
        return merchant_execution._merchant_start_order(self._dependencies.merchant.execution, game, order, rng)

    def _merchant_tick_order(self, game, order):
        return merchant_execution._merchant_tick_order(self._dependencies.merchant.execution, game, order)

    def _ensure_doctrines(self, game):
        return doctrine_actions._ensure_doctrines(game)

    def _begin_doctrine_action(self, game, action, *, commit=False):
        return doctrine_actions._begin_doctrine_action(self._dependencies.cultivation.study, game, action, commit=commit)

    def _finish_doctrine_action(self, game, action, elapsed):
        return doctrine_actions._finish_doctrine_action(self._dependencies.cultivation.study, game, action, elapsed)

    def doctrine_action(self, game_id, action, doctrine_id=None, manual_id=None, confirm_origin=False, npc_id=None):
        return doctrine_actions.doctrine_action(self._dependencies.cultivation.actions, game_id, action, doctrine_id, manual_id, confirm_origin, npc_id)

    def _public_doctrines(self, game):
        return doctrine_actions._public_doctrines(self._dependencies.cultivation.view, game)

    def _fusion_requirements(self, game, key, *, study=False):
        return doctrine_fusion._fusion_requirements(game, key, study=study)

    def _fuse_doctrine(self, game, key):
        return doctrine_fusion._fuse_doctrine(self._dependencies.cultivation.fusion, game, key)

    def _begin_fusion_study(self, game, *, commit=False):
        return doctrine_fusion._begin_fusion_study(self._dependencies.cultivation.fusion, game, commit=commit)

    def _finish_fusion_study(self, game, elapsed):
        return doctrine_fusion._finish_fusion_study(game, elapsed)

    def _public_fusion(self, game, definition):
        return doctrine_fusion._public_fusion(game, definition)

    def _cultivation_game(self, game_id):
        return cultivation_session._cultivation_game(self._dependencies.cultivation.session, game_id)

    def _save_cultivation(self, game, summary):
        return cultivation_session._save_cultivation(self._dependencies.cultivation.commit, game, summary)

    def immortal_action(self, game_id, action, doctrine_id=None, axis=None, supply_id=None):
        return immortal_actions.immortal_action(self._dependencies.cultivation.immortal_actions, game_id, action, doctrine_id, axis, supply_id)

    @staticmethod
    def _spend_cultivation(player, cost):
        return immortal_actions._spend_cultivation(player, cost)

    def _public_immortal(self, game):
        return immortal_actions._public_immortal(self._dependencies.cultivation.immortal_view, game)

    def _temper_golden_light(self, game):
        return immortal_body._temper_golden_light(self._dependencies.cultivation.body, game)

    @staticmethod
    def _public_golden_light(game):
        return immortal_body._public_golden_light(game)

    def _immortal_body_action(self, game, action, key):
        return immortal_body._immortal_body_action(self._dependencies.cultivation.body, game, action, key)

    @staticmethod
    def _public_immortal_body(game):
        return immortal_body._public_immortal_body(game)

    def upper_voisinage_action(self, game_id, action, voisinage_id):
        return immortal_aperture.upper_voisinage_action(self._dependencies.cultivation.aperture, game_id, action, voisinage_id)

    def aperture_action(self, game_id, action, manual_id=None):
        return immortal_aperture.aperture_action(self._dependencies.cultivation.aperture, game_id, action, manual_id)

    def _finish_travel_time(self, game, start_age, institution_world, institution_unit, era_news, rng):
        return world_time._finish_travel_time(self._dependencies.time.elapsed_travel, game, start_age, institution_world, institution_unit, era_news, rng)

    @staticmethod
    def _post_battle_possession_candidates(game: GameState) -> list[dict[str, Any]]:
        return ghost_identity._post_battle_possession_candidates(game)

    def _prepare_post_battle_possession(self, game: GameState, source_event: str) -> bool:
        return ghost_identity._prepare_post_battle_possession(self._dependencies.ghost_flows.identity, game, source_event)

    def post_battle_possess(self, game_id: str, target_id: str) -> dict[str, Any]:
        return ghost_identity.post_battle_possess(self._dependencies.ghost_flows.identity, game_id, target_id)

    def _advance_ghost_phase_two_year(self, game: GameState, rng: random.Random) -> None:
        return ghost_calendar._advance_ghost_phase_two_year(self._dependencies.ghost_flows.calendar, game, rng)

    def ghost_constraint_action(self, game_id: str, action: str) -> dict[str, Any]:
        return ghost_identity.ghost_constraint_action(self._dependencies.ghost_flows.identity, game_id, action)

    def _capture_defeated_ghost(self, game: GameState, target: dict[str, Any], rng: random.Random) -> bool:
        return ghost_identity._capture_defeated_ghost(game, target, rng)

    def leave_possessed_body(self, game_id: str) -> dict[str, Any]:
        return ghost_identity.leave_possessed_body(self._dependencies.ghost_flows.identity, game_id)

    def _advance_soul_erosion_time(self, game: GameState, elapsed_years: int=1) -> bool:
        return ghost_erosion._advance_soul_erosion_time(self._dependencies.ghost_flows.erosion, game, elapsed_years)

    def _apply_soul_erosion_units(self, game: GameState, units: int=1) -> bool:
        return ghost_erosion._apply_soul_erosion_units(self._dependencies.ghost_flows.erosion, game, units)

    def spend_wangsheng(self, game_id: str, spend_all: bool=False) -> dict[str, Any]:
        return ghost_erosion.spend_wangsheng(self._dependencies.ghost_flows.erosion, game_id, spend_all)

    def prepare_ghost_reincarnation(self, game_id: str) -> dict[str, Any]:
        return ghost_reincarnation.prepare_ghost_reincarnation(self._dependencies.ghost_flows.reincarnation, game_id)

    def _complete_ghost_reincarnation(self, game: GameState, *, record_history: bool) -> dict[str, Any]:
        return ghost_reincarnation._complete_ghost_reincarnation(game, record_history=record_history)

    def reincarnate_ghost(self, game_id: str) -> dict[str, Any]:
        return ghost_reincarnation.reincarnate_ghost(self._dependencies.ghost_flows.reincarnation, game_id)

    def _capture_cultivator(self, game: GameState, target: dict[str, Any], own_power: float, rng: random.Random) -> tuple[str, str]:
        return relationships_captivity._capture_cultivator(self._dependencies.relationships.captivity, game, target, own_power, rng)

    def begin_relationship_capture(self, game_id: str, kind: str, target_id: str='') -> dict[str, Any]:
        return relationships_captivity.begin_relationship_capture(self._dependencies.relationships.captivity, game_id, kind, target_id)

    def _relationship_capture_step(self, game: GameState, pending: dict[str, Any], stage: str, method: str, rng: random.Random) -> tuple[str, str]:
        return relationships_captivity._relationship_capture_step(self._dependencies.relationships.captivity, game, pending, stage, method, rng)

    def _break_capture_relationship(self, game: GameState, relation: dict[str, Any], kind: str, captured: bool) -> None:
        return relationships_captivity._break_capture_relationship(self._dependencies.relationships.captivity, game, relation, kind, captured)

    def captive_action(self, game_id: str, target_id: str, action: str) -> dict[str, Any]:
        return relationships_captivity.captive_action(self._dependencies.relationships.captivity, game_id, target_id, action)

    def _restore_captive_npc(self, game: GameState, target: dict[str, Any], affinity_gain: float) -> None:
        return relationships_captivity._restore_captive_npc(self._dependencies.relationships.captivity, game, target, affinity_gain)

    def _convert_to_puppet(self, game: GameState, target: dict[str, Any], kind: str, rng: random.Random, disciple: bool) -> tuple[str, str]:
        return relationships_captivity._convert_to_puppet(self._dependencies.relationships.captivity, game, target, kind, rng, disciple)

    @staticmethod
    def _remove_conversion_target(player: Player, target: dict[str, Any], disciple: bool) -> None:
        return relationships_captivity._remove_conversion_target(player, target, disciple)

    def secluded_refine_foreign_souls(self, game_id: str) -> dict[str, Any]:
        return demonic_refinement.secluded_refine_foreign_souls(self._dependencies.demonic_flows.refinement, game_id)

    def _annual_demonic_update(self, game: GameState, rng: random.Random) -> None:
        return demonic_annual._annual_demonic_update(self._dependencies.demonic_flows.annual, game, rng)

    @staticmethod
    def _rank(value: Player | SectNpc | dict[str, Any]) -> tuple[int, int]:
        return relationship_rules._rank(value)

    @staticmethod
    def _stable_gender(identity: str, name: str='') -> str:
        return relationship_rules._stable_gender(identity, name)

    def _maybe_relationship_sanction(self, game: GameState, rng: random.Random) -> bool:
        return relationships_sanctions._maybe_relationship_sanction(self._dependencies.relationships.sanctions, game, rng)

    def _end_sanctioned_relationship(self, game: GameState, role: str, name: str) -> tuple[str, str]:
        return relationships_sanctions._end_sanctioned_relationship(self._dependencies.relationships.sanctions, game, role, name)

    def _resolve_relationship_sanction(self, game: GameState, pending: dict[str, Any], role: str, mode: str, rng: random.Random) -> tuple[str, str]:
        return relationships_sanctions._resolve_relationship_sanction(self._dependencies.relationships.sanctions, game, pending, role, mode, rng)

    def _maybe_transfer_player_dependency(self, game: GameState, loser: SectNpc, winner: SectNpc, rng: random.Random, *, context: str) -> str:
        return relationships_dependents._maybe_transfer_player_dependency(self._dependencies.relationships.dependents, game, loser, winner, rng, context=context)

    def manage_concubine(self, game_id: str, target_id: str, action: str) -> dict[str, Any]:
        return relationships_concubines.manage_concubine(self._dependencies.relationships.concubines, game_id, target_id, action)

    def _maybe_concubine_proposal(self, game: GameState, rng: random.Random) -> bool:
        return relationships_dependents._maybe_concubine_proposal(self._dependencies.relationships.dependents, game, rng)

    def _resolve_concubine_proposal(self, game: GameState, pending: dict[str, Any], accept: bool) -> tuple[str, str]:
        return relationships_dependents._resolve_concubine_proposal(self._dependencies.relationships.dependents, game, pending, accept)

    def _advance_concubine_aftermath(self, game: GameState, rng: random.Random) -> bool:
        return relationships_dependents._advance_concubine_aftermath(self._dependencies.relationships.dependents, game, rng)

    @staticmethod
    def _runtime_from_status(status: dict[str, Any]) -> dict[str, Any]:
        return relationships_dependents._runtime_from_status(status)

    def _set_concubine_status(self, game: GameState, runtime: dict[str, Any], *, forced: bool=False) -> None:
        return relationships_dependents._set_concubine_status(self._dependencies.relationships.dependents, game, runtime, forced=forced)

    def _resolve_concubine_revenge(self, game: GameState, pending: dict[str, Any], method: str, rng: random.Random) -> tuple[str, str]:
        return relationships_dependents._resolve_concubine_revenge(self._dependencies.relationships.dependents, game, pending, method, rng)

    def _resolve_concubine_escape(self, game: GameState, pending: dict[str, Any], method: str, rng: random.Random) -> tuple[str, str]:
        return relationships_dependents._resolve_concubine_escape(self._dependencies.relationships.dependents, game, pending, method, rng)

    def manage_concubine_status(self, game_id: str, action: str) -> dict[str, Any]:
        return relationships_dependents.manage_concubine_status(self._dependencies.relationships.dependents, game_id, action)

    def relationship_violence(self, game_id, kind, target_id, *, capture=False):
        return relationships_violence.relationship_violence(self._dependencies.relationships.violence, game_id, kind, target_id, capture=capture)

    def buddhist_action(self, game_id, action, **payload):
        return buddhist_actions.buddhist_action(self._dependencies.buddhist_flows.actions, game_id, action, **payload)

    def _continue_buddhist_assembly(self, game, rng):
        return buddhist_assembly._continue_buddhist_assembly(self._dependencies.buddhist_flows.assembly, game, rng)

    def _resolve_buddhist_assembly(self, effect, game, pending, rng):
        return buddhist_assembly._resolve_buddhist_assembly(self._dependencies.buddhist_flows.assembly, effect, game, pending, rng)

    def _finish_buddhist_assembly(self, game, rng=None, forced_failure=False):
        return buddhist_assembly._finish_buddhist_assembly(self._dependencies.buddhist_flows.assembly, game, rng, forced_failure)

    def _advance_concubine_status(self, game: GameState, units: int = 1) -> float:
        return relationships_dependents._advance_concubine_status(self._dependencies.relationships.dependents, game, units)

    def asura_action(self, game_id, action, target_id='', body_ids=None, name=''):
        return asura_actions.asura_action(self._dependencies.asura_actions, game_id, action, target_id, body_ids, name)

    def _asura_cultivate(self, game, action, target_id, body_ids, name, rng):
        return asura_actions._asura_cultivate(self._dependencies.asura_actions, game, action, target_id, body_ids, name, rng)

    @staticmethod
    def _spend_asura_souls(state, cost):
        return asura_actions._spend_asura_souls(state, cost)

    def _plan_world_transition(self, game, destination, mode="progression", *, route_id=None, arrival_location=None, reason=""):
        from ..system.world_transition_system import WorldTransitionRequest, TransitionMode, plan_world_transition
        route_id = route_id or ("sealed_return" if mode == "sealed_return" else f"{mode}:{game.player.world}:{destination}")
        request = WorldTransitionRequest(destination, TransitionMode(mode), route_id, reason, arrival_location)
        return plan_world_transition(game, request, WORLD_SYSTEMS, self.maps)

    def _apply_world_transition(self, game, plan, *, entourage=None):
        from ..system.world_transition_system import WorldTransitionPorts, apply_world_transition
        from ..system.combat.npc_lifecycle import move_world
        ports = WorldTransitionPorts(self._cancel_auction_for_world_change, self._clear_market,
                                     self._prepare_permanent_world_transition,
                                     lambda npc, world, now: move_world(npc, world, now, WORLD_SYSTEMS.get("transcendent_combat", {})))
        return apply_world_transition(game, plan, ports, entourage=entourage)

    def get_game(self, game_id: str) -> dict[str, Any]:
        return self.present(self._load(game_id))

    def delete_game(self, game_id: str) -> None:
        self.store.delete(game_id)

    def list_games(self) -> list[dict[str, str]]:
        return self.store.list_games()

    def list_achievements(self) -> dict[str, Any]:
        return self.achievements.public_catalog()

    def set_world_news_debug(self, game_id: str, enabled: bool) -> dict[str, Any]:
        """Debug only changes what the chronology exposes; simulation remains global."""
        game = self._load(game_id)
        game.debug_world_news = bool(enabled)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def update_setting(self, game_id: str, setting: str, enabled: bool) -> dict[str, Any]:
        game = self._load(game_id)
        if setting == 'manual_combat_plan':
            if game.pending_event or game.active_trial:
                raise ValueError('请先结束当前事件或试炼，再切换战斗预案')
            game.player.combat_plan['manual'] = bool(enabled)
            game.updated_at = now_iso()
            self.store.save(game)
            return self.present(game)
        if setting not in {
            "combat_popup", "achievement_popup", "auto_advance_player_wars",
            "guixu_event_popup", "court_election_popup", "silent_events",
        }:
            raise ValueError("未知设置项")
        game.settings[setting] = bool(enabled)
        if setting == "court_election_popup" and not enabled:
            rng = decode_rng(game.seed, game.rng_state)
            self._court_finish_unattended(game, rng)
            game.rng_state = encode_rng(rng)
        if (
            setting == "guixu_event_popup" and not enabled and game.pending_event
            and str(game.pending_event.get("id", "")) in {"EVT_GUIXU_ANNOUNCE", "EVT_GUIXU_OPEN"}
        ):
            game.pending_event = None
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def update_combat_plan(self, game_id, payload):
        from ..system.combat_plan import validate_plan
        game = self._load(game_id)
        if (not game.player.alive or game.pending_event or game.active_trial
                or game.player.imprisonment or game.player.ghost_captor):
            raise ValueError('当前状态不能调整战斗预案')
        if not game.player.combat_plan.get('manual'):
            raise ValueError('请在设置中启用手动战斗预案')
        game.player.combat_plan.update(validate_plan(payload))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def tutorial_action(self, game_id, action, step=None, target_id=None):
        from ..system.tutorial_system import perform
        return perform(self, game_id, action, step, target_id)

    @staticmethod
    def _new_sects() -> dict[str, SectState]:
        return world_runtime._new_sects()

    def _ensure_sects(self, game: GameState) -> None:
        return world_runtime._ensure_sects(self._dependencies.world_runtime, game)

    def _compact_sect_roster(self, game: GameState, sect: SectState) -> bool:
        "Discard only stale dead recruit records once a sect's simulation roster is full."
        return world_runtime._compact_sect_roster(self._dependencies.world_runtime, game, sect)

    @staticmethod
    def _compact_world_history(game: GameState) -> bool:
        "Bound old ambient world news while preserving the player's personal chronicle."
        return world_runtime._compact_world_history(game)

    @staticmethod
    def _new_world_npcs() -> dict[str, SectNpc]:
        return world_runtime._new_world_npcs()

    def _ensure_world_npcs(self, game: GameState) -> bool:
        return world_runtime._ensure_world_npcs(self._dependencies.world_runtime, game)

    def _enforce_world_realm_caps(self, game: GameState) -> bool:
        'Migrate pre-V8 saves so lower worlds cannot retain upper-world NPCs.'
        return world_runtime._enforce_world_realm_caps(self._dependencies.world_runtime, game)

    def _migrate_true_demon_races(self, game: GameState) -> bool:
        'Move pre-V9 true-demon residents off the former shared spirit race table.'
        return world_runtime._migrate_true_demon_races(self._dependencies.world_runtime, game)

    @staticmethod
    def _actual_player_realm(player: Player) -> tuple[int, int]:
        return world_runtime._actual_player_realm(player)

    @staticmethod
    def _world_supports(world: str, feature: str) -> bool:
        return world_runtime._world_supports(world, feature)

    @staticmethod
    def _world_realm_cap(world: str) -> int:
        return world_runtime._world_realm_cap(world)

    def _select_event(self, game: GameState, action: str, rng: random.Random) -> dict[str, Any] | None:
        return event_runtime._select_event(self._dependencies.event_runtime, game, action, rng)

    @staticmethod
    def _event_weight(event: dict[str, Any], game: GameState, action: str) -> float:
        return event_runtime._event_weight(event, game, action)

    def _instantiate_event(self, event: dict[str, Any], game: GameState, rng: random.Random) -> dict[str, Any]:
        return event_runtime._instantiate_event(self._dependencies.event_runtime, event, game, rng)

    def _condition(self, condition: dict[str, Any], game: GameState) -> bool:
        return event_runtime._condition(self._dependencies.event_runtime, condition, game)

    def _path(self, path: str, game: GameState) -> Any:
        return event_runtime._path(self._dependencies.event_runtime, path, game)

    @staticmethod
    def _base_affinities(player: Player) -> list[str]:
        return event_runtime._base_affinities(player)

    @staticmethod
    def _is_story_combat_check(event_id: str, effect: dict[str, Any]) -> bool:
        return event_runtime._is_story_combat_check(event_id, effect)

    def _resolve_story_combat_check(self, effect: dict[str, Any], game: GameState, pending: dict[str, Any], rng: random.Random) -> tuple[str, str]:
        return event_runtime._resolve_story_combat_check(self._dependencies.event_runtime, effect, game, pending, rng)

    @staticmethod
    def _story_unit_full_power(definition: dict[str, Any], realm_index: int, effective_power: float) -> float:
        return event_runtime._story_unit_full_power(definition, realm_index, effective_power)

    def _player_combat_units(self, game: GameState, target: dict[str, Any] | None=None) -> list[BattleUnit]:
        'Build independent units for player combat; each brings full power.'
        return combat_runtime._player_combat_units(self._dependencies.combat_runtime, game, target)

    def _combat_battlefield_tags(self, game: GameState, target: dict[str, Any]) -> list[str]:
        return combat_runtime._combat_battlefield_tags(self._dependencies.combat_runtime, game, target)

    @staticmethod
    def _apply_support_damage(player: Player, updates: list[dict[str, Any]]) -> None:
        return combat_runtime._apply_support_damage(player, updates)

    def _record_player_combat(self, game: GameState, target: dict[str, Any], resolution: Any, result: str) -> None:
        return combat_runtime._record_player_combat(self._dependencies.combat_runtime, game, target, resolution, result)

    @staticmethod
    def _combat_report_lead(resolution: Any, hp_loss: float, mp_loss: float) -> str:
        return combat_runtime._combat_report_lead(resolution, hp_loss, mp_loss)

    def _combat(self, game: GameState, target: dict[str, Any], lethal: bool, rng: random.Random) -> tuple[str, str]:
        'Resolve player-involved combat through the detailed automatic system.\n\n        NPC-only field battles deliberately remain in ``WarSystemMixin`` and use\n        their legacy aggregate-power logic.\n        '
        return combat_runtime._combat(self._dependencies.combat_runtime, game, target, lethal, rng)

    def _apply_cultivator_kill(self, game: GameState, victim: dict[str, Any], rng: random.Random) -> None:
        return combat_runtime._apply_cultivator_kill(self._dependencies.combat_runtime, game, victim, rng)

    def _kill_generates_hostility(self, game: GameState, kind: str, target_id: str, victim_realm: int) -> bool:
        'Routine wartime and low-rank deaths do not mobilise an entire power.'
        return combat_runtime._kill_generates_hostility(self._dependencies.combat_runtime, game, kind, target_id, victim_realm)

    def _is_wartime_opponent(self, game: GameState, faction_id: str | None, race_id: str) -> bool:
        return combat_runtime._is_wartime_opponent(self._dependencies.combat_runtime, game, faction_id, race_id)

    def _handle_same_sect_kill(self, game: GameState, faction_id: str, current_victim_id: str | None=None) -> None:
        return combat_runtime._handle_same_sect_kill(self._dependencies.combat_runtime, game, faction_id, current_victim_id)

    @staticmethod
    def _race_alliance(game: GameState, world: str, first: str, second: str) -> dict[str, Any] | None:
        return combat_runtime._race_alliance(game, world, first, second)

    def _die(self, game: GameState, reason: str, event_id: str, *, offer_captive_possession: bool=False) -> None:
        return combat_runtime._die(self._dependencies.combat_runtime, game, reason, event_id, offer_captive_possession=offer_captive_possession)

    @staticmethod
    def _snapshot(player: Player) -> dict[str, Any]:
        return combat_runtime._snapshot(player)

    @staticmethod
    def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        return combat_runtime._diff(before, after)

    def present(self, game: GameState) -> dict[str, Any]:
        from .actions.exploration import reconcile_boundary
        from ..system import spatial, talismans
        if reconcile_boundary(self._exploration_dependencies(), game):
            self.store.save(game)
        result = presentation_runtime.present(self._dependencies.presentation_runtime, game)
        result["buddhist_system"] = self._public_buddhist(game)
        result['spatial'] = spatial.public(game)
        result['talismans'] = talismans.public(game)
        spatial_limit = spatial.cultivation_block_reason(game)
        if spatial_limit:
            result['breakthrough'].update(ready=False, enabled=False, met=False, reason=spatial_limit)
        if spatial.current(game):
            scene = spatial.current(game)
            result['player']['world_name'] = scene['name']
            result['player']['location_name'] = next(r['name'] for r in scene['locations'] if r['id']==scene['location_id'])
            result['player']['qi_gain_efficiencies'] = spatial.current_qi(game)
            result['map'] = spatial.public_map(game)
            result['market'] = []
        return result

    @staticmethod
    def _history_visible_in_world(record: HistoryRecord, game: GameState) -> bool:
        return presentation_runtime._history_visible_in_world(record, game)

    def _load(self, game_id: str) -> GameState:
        from .transactions import request_games, active_command
        from ..system.spatial import guard
        games = request_games(self)
        if games is not None and game_id in games:
            if active_command():
                guard(games[game_id], active_command())
            return games[game_id]
        game = persistence_runtime._load(self._dependencies.persistence_runtime, game_id)
        if active_command():
            guard(game, active_command())
        if games is not None:
            games[game_id] = game
        return game

    def create_game(self, name: str, spirit_root: str, path: str, seed: int | None=None, technique_element: str | None=None, preset_id: str | None=None, start_world: str | None=None, monster_species_id: str | None=None, gender: str='male') -> dict[str, Any]:
        return session.create_game(self._dependencies.session, name, spirit_root, path, seed, technique_element, preset_id, start_world, monster_species_id, gender)

    def advance(self, game_id: str, action: str, years: int=1) -> dict[str, Any]:
        return advancement.advance(self._dependencies.advancement, game_id, action, years)

    def _spatial_training(self, game, action, units):
        from .actions.exploration import train
        return train(self._exploration_dependencies(), game, action, units)

    def _exploration_dependencies(self):
        from .actions.exploration import ExplorationDependencies
        return ExplorationDependencies(self._load, self.store.save, self.present, self.maps,
            self._plan_world_transition, self._apply_world_transition, self._ensure_market,
            self._die, self._advance_world_year,
            self._body_training_step, self._body_progress_required, self._sense_training_step, self._advance_soul_erosion_time,
            self._prepare_sage_action, self._finish_sage_action, self._advance_natal_artifact)

    def spatial_action(self, game_id, action, payload=None):
        from .actions.exploration import spatial_action
        return spatial_action(self._exploration_dependencies(), game_id, action, payload or {})

    def talisman_action(self, game_id, action, payload=None):
        from .actions.exploration import talisman_action
        return talisman_action(self._exploration_dependencies(), game_id, action, payload or {})

    def _add_opportunity(self, player: Player, amount: float, regional_efficiencies: dict[str, float] | None=None) -> float:
        return advancement._add_opportunity(self._dependencies.advancement, player, amount, regional_efficiencies)

    def _sense_training_step(self, player: Player, regional: dict[str, float] | None=None, concentrations: dict[str, float] | None=None) -> float:
        'Calculate one year of sense training for every training context.'
        return advancement._sense_training_step(self._dependencies.advancement, player, regional, concentrations)

    def _body_training_step(self, player: Player, rng: random.Random, concentrations: dict[str, float] | None=None) -> float:
        'Calculate one year of body training for every training context.'
        return advancement._body_training_step(self._dependencies.advancement, player, rng, concentrations)

    @staticmethod
    def _apply_action_resources(player: Player, action: str, pay_cost: bool) -> None:
        'Apply annual gains but charge negative HP/MP modifiers once per action unit.'
        return advancement._apply_action_resources(player, action, pay_cost)

    @staticmethod
    def _condense_action_results(results: list[str]) -> str:
        return advancement._condense_action_results(results)

    @staticmethod
    def _record_era_summary(game: GameState, start_age: int, news: list[str]) -> None:
        return advancement._record_era_summary(game, start_age, news)

    def _commission_step(self, game: GameState, rng: random.Random) -> str:
        return advancement._commission_step(self._dependencies.advancement, game, rng)

    @staticmethod
    def _cultivation_sense_requirement(realm_index: int, layer: int) -> int:
        'Natural divine-sense rank earned by reaching one cultivation layer.'
        return cultivation_actions._cultivation_sense_requirement(realm_index, layer)

    def _secret_art_realm_name(self, player: Player, realm_index: int, layer: int=1) -> str:
        return cultivation_actions._secret_art_realm_name(self._dependencies.cultivation_actions, player, realm_index, layer)

    def manage_secret_art(self, game_id: str, art: str, action: str, realm_index: int | None=None, layer: int | None=None) -> dict[str, Any]:
        return cultivation_actions.manage_secret_art(self._dependencies.cultivation_actions, game_id, art, action, realm_index, layer)

    def _public_secret_arts(self, player: Player) -> dict[str, Any]:
        return cultivation_actions._public_secret_arts(self._dependencies.cultivation_actions, player)

    def breakthrough(self, game_id: str) -> dict[str, Any]:
        return cultivation_actions.breakthrough(self._dependencies.cultivation_actions, game_id)

    @staticmethod
    def _body_progress_required(player: Player) -> float:
        return cultivation_actions._body_progress_required(player)

    @staticmethod
    def _body_pity_key(player: Player) -> str:
        return cultivation_actions._body_pity_key(player)

    def _body_breakthrough_chance(self, player: Player) -> dict[str, float]:
        return cultivation_actions._body_breakthrough_chance(self._dependencies.cultivation_actions, player)

    def body_breakthrough(self, game_id: str) -> dict[str, Any]:
        return cultivation_actions.body_breakthrough(self._dependencies.cultivation_actions, game_id)

    def divine_sense_breakthrough(self, game_id: str) -> dict[str, Any]:
        return cultivation_actions.divine_sense_breakthrough(self._dependencies.cultivation_actions, game_id)

    def _handover_faction_for_ascension(self, game: GameState) -> dict[str, Any] | None:
        'Remove the player from a lower-world faction and leave a real NPC ruler.'
        return world_travel_actions._handover_faction_for_ascension(self._dependencies.world_travel_actions, game)

    def _prepare_permanent_world_transition(self, game: GameState, *, keep_companion: bool=False, keep_friend_ids: set[str] | None=None) -> dict[str, Any]:
        'Apply the shared, irreversible cleanup required by every ascension.'
        return world_travel_actions._prepare_permanent_world_transition(self._dependencies.world_travel_actions, game, keep_companion=keep_companion, keep_friend_ids=keep_friend_ids)

    def _resolve_selected_ascension_entourage(self, game: GameState, destination: str, rng: random.Random) -> tuple[bool, set[str], list[str], list[str]]:
        'Resolve explicitly invited partner/friends before permanent cleanup.'
        from copy import deepcopy
        from ..system.world_transition_system import EntourageManifest
        shadow = deepcopy(game)
        result = world_travel_actions._resolve_selected_ascension_entourage(self._dependencies.world_travel_actions, shadow, destination, rng)
        kept, survivors, names, fallen = result
        selected = [*shadow.player.dao_friends, *([shadow.player.dao_companion] if kept else [])]
        original = {str(row.get("id")): row for row in [*game.player.dao_friends, *([game.player.dao_companion] if game.player.dao_companion else [])]}
        snapshots = []
        for row in selected:
            npc_id = str(row.get("id", ""))
            before = original.get(npc_id, {})
            if row.get("world") != before.get("world") or row.get("alive", True) != before.get("alive", True):
                snapshots.append((npc_id, row.get("alive", True), row.get("death_reason") or f"与{game.player.name}共同飞升{WORLD_SYSTEMS['world_names'][destination]}"))
        return EntourageManifest(kept, frozenset(survivors), tuple(names), tuple(fallen), tuple(snapshots))

    def _maybe_founder_return_event(self, game: GameState, rng: random.Random) -> bool:
        return world_travel_actions._maybe_founder_return_event(self._dependencies.world_travel_actions, game, rng)

    def begin_spirit_crossing(self, game_id: str) -> dict[str, Any]:
        return world_travel_actions.begin_spirit_crossing(self._dependencies.world_travel_actions, game_id)

    def begin_celestial_ascension(self, game_id: str) -> dict[str, Any]:
        'Start the dedicated nine-stage Mahayana ascension trial.'
        return world_travel_actions.begin_celestial_ascension(self._dependencies.world_travel_actions, game_id)

    def begin_asura_ascension(self, game_id: str) -> dict[str, Any]:
        'Start the nine-stage demonic ascension from the True Demon Realm.'
        return world_travel_actions.begin_asura_ascension(self._dependencies.world_travel_actions, game_id)

    def _complete_demonic_ascension(self, game: GameState) -> dict[str, Any]:
        '魔界路线直接渡界；飞升真魔界时必须承受魔气纯度判定。'
        return world_travel_actions._complete_demonic_ascension(self._dependencies.world_travel_actions, game)

    def cross_world(self, game_id: str, destination: str) -> dict[str, Any]:
        'Let Mahayana/Mozun cultivators visit their corresponding lower world.'
        return world_travel_actions.cross_world(self._dependencies.world_travel_actions, game_id, destination)

    def create_faction(self, game_id: str, name: str) -> dict[str, Any]:
        return faction_actions.create_faction(self._dependencies.faction_actions, game_id, name)

    def create_family(self, game_id: str, name: str) -> dict[str, Any]:
        return faction_actions.create_family(self._dependencies.faction_actions, game_id, name)

    @staticmethod
    def _vote_probability(current_affinity: float, requested_status: str, voter_affinity: float=0.0) -> float:
        return faction_actions._vote_probability(current_affinity, requested_status, voter_affinity)

    def propose_race_diplomacy(self, game_id: str, target_race: str, status: str) -> dict[str, Any]:
        return faction_actions.propose_race_diplomacy(self._dependencies.faction_actions, game_id, target_race, status)

    def propose_sect_diplomacy(self, game_id: str, target_faction: str, status: str) -> dict[str, Any]:
        return faction_actions.propose_sect_diplomacy(self._dependencies.faction_actions, game_id, target_faction, status)

    def transfer_vassal_personnel(self, game_id: str, kind: str, target_id: str, npc_id: str) -> dict[str, Any]:
        return faction_actions.transfer_vassal_personnel(self._dependencies.faction_actions, game_id, kind, target_id, npc_id)

    def _power_name(self, game: GameState, kind: str, entity_id: str) -> str:
        return faction_actions._power_name(self._dependencies.faction_actions, game, kind, entity_id)

    @staticmethod
    def _player_allegiance_race(player: Player) -> str:
        return faction_actions._player_allegiance_race(player)

    def leave_faction(self, game_id: str) -> dict[str, Any]:
        return faction_actions.leave_faction(self._dependencies.faction_actions, game_id)

    def arrange_faction_succession(self, game_id: str) -> dict[str, Any]:
        return faction_actions.arrange_faction_succession(self._dependencies.faction_actions, game_id)

    def set_faction_reward(self, game_id: str, reward_id: str) -> dict[str, Any]:
        return faction_actions.set_faction_reward(self._dependencies.faction_actions, game_id, reward_id)

    @staticmethod
    def _remember_faction_prison_release(player: Player, prison: dict[str, Any]) -> None:
        'Persist the exact former jailer so a later dissolution can match it.'
        return encounter_actions._remember_faction_prison_release(player, prison)

    @staticmethod
    def _record_former_jailer_dissolved(player: Player, kind: str, faction_id: str) -> bool:
        return encounter_actions._record_former_jailer_dissolved(player, kind, faction_id)

    def prison_action(self, game_id: str, action: str) -> dict[str, Any]:
        return encounter_actions.prison_action(self._dependencies.encounter_actions, game_id, action)

    def _available_bounty_authorities(self, game: GameState) -> list[dict[str, str]]:
        return encounter_actions._available_bounty_authorities(self._dependencies.encounter_actions, game)

    def issue_bounty(self, game_id: str, npc_id: str, authority: str='') -> dict[str, Any]:
        return encounter_actions.issue_bounty(self._dependencies.encounter_actions, game_id, npc_id, authority)

    def intercept_faction_npc(self, game_id: str, npc_id: str) -> dict[str, Any]:
        "Explicitly attack a member shown in the player's current faction roster."
        return encounter_actions.intercept_faction_npc(self._dependencies.encounter_actions, game_id, npc_id)

    def _personal_combat_step(self, game: GameState, action: str, rng: random.Random) -> str:
        return encounter_actions._personal_combat_step(self._dependencies.encounter_actions, game, action, rng)

    def _apply_combat_action_rewards(self, game: GameState, action: str, result: str, summary: str, rng: random.Random, *, player_defending: bool=False) -> str:
        return encounter_actions._apply_combat_action_rewards(self._dependencies.encounter_actions, game, action, result, summary, rng, player_defending=player_defending)

    def _known_npc_encounter_target(self, game: GameState, settings: dict[str, Any], rng: random.Random) -> dict[str, Any] | None:
        return encounter_actions._known_npc_encounter_target(self._dependencies.encounter_actions, game, settings, rng)

    def use_item(self, game_id: str, item_id: str) -> dict[str, Any]:
        return inventory_actions.use_item(self._dependencies.inventory_actions, game_id, item_id)

    def buy_market_offer(self, game_id: str, offer_id: str) -> dict[str, Any]:
        return inventory_actions.buy_market_offer(self._dependencies.inventory_actions, game_id, offer_id)

    def equip_known_technique(self, game_id: str, technique_id: str, slot: str) -> dict[str, Any]:
        return inventory_actions.equip_known_technique(self._dependencies.inventory_actions, game_id, technique_id, slot)

    def upgrade_technique(self, game_id: str, technique_id: str) -> dict[str, Any]:
        return inventory_actions.upgrade_technique(self._dependencies.inventory_actions, game_id, technique_id)

    def merge_technique_manuals(self, game_id: str, technique_id: str, level: int) -> dict[str, Any]:
        return inventory_actions.merge_technique_manuals(self._dependencies.inventory_actions, game_id, technique_id, level)

    def absorb_transformation_material(self, game_id: str, item_id: str, purify: bool=False, stat_id: str='') -> dict[str, Any]:
        return inventory_actions.absorb_transformation_material(self._dependencies.inventory_actions, game_id, item_id, purify, stat_id)

    def batch_absorb_transformation_material(self, game_id: str, item_id: str, mode: str='direct', stat_id: str='') -> dict[str, Any]:
        return inventory_actions.batch_absorb_transformation_material(self._dependencies.inventory_actions, game_id, item_id, mode, stat_id)

    def manage_transformation(self, game_id: str, form_id: str, action: str) -> dict[str, Any]:
        return inventory_actions.manage_transformation(self._dependencies.inventory_actions, game_id, form_id, action)

    def dispatch_disciple(self, game_id: str, target: str) -> dict[str, Any]:
        return relationship_actions.dispatch_disciple(self._dependencies.relationship_actions, game_id, target)

    def manage_faction_relationship(self, game_id: str, npc_id: str, role: str) -> dict[str, Any]:
        return relationship_actions.manage_faction_relationship(self._dependencies.relationship_actions, game_id, npc_id, role)

    def contact_action(self, game_id, npc_id, action):
        from ..system.npc_contacts import act
        return act(self._dependencies.npc_contacts, game_id, npc_id, action)

    def respond_disciple_request(self, game_id: str, request_id: str, accept: bool) -> dict[str, Any]:
        return relationship_actions.respond_disciple_request(self._dependencies.relationship_actions, game_id, request_id, accept)

    def request_from_master(self, game_id: str, kind: str) -> dict[str, Any]:
        return relationship_actions.request_from_master(self._dependencies.relationship_actions, game_id, kind)

    def gift_disciple(self, game_id: str, disciple_id: str, kind: str, content_id: str) -> dict[str, Any]:
        return relationship_actions.gift_disciple(self._dependencies.relationship_actions, game_id, disciple_id, kind, content_id)

    def manage_dao_companion(self, game_id: str, action: str, npc_id: str='', kind: str='', content_id: str='') -> dict[str, Any]:
        return relationship_actions.manage_dao_companion(self._dependencies.relationship_actions, game_id, action, npc_id, kind, content_id)

    def manage_dao_friend(self, game_id: str, npc_id: str, action: str) -> dict[str, Any]:
        return relationship_actions.manage_dao_friend(self._dependencies.relationship_actions, game_id, npc_id, action)

    def invite_relationship_to_faction(self, game_id: str, npc_id: str) -> dict[str, Any]:
        return relationship_actions.invite_relationship_to_faction(self._dependencies.relationship_actions, game_id, npc_id)

    def leave_relationship(self, game_id: str, kind: str, npc_id: str='') -> dict[str, Any]:
        return relationship_actions.leave_relationship(self._dependencies.relationship_actions, game_id, kind, npc_id)

    def manage_party(self, game_id: str, npc_id: str, action: str) -> dict[str, Any]:
        return relationship_actions.manage_party(self._dependencies.relationship_actions, game_id, npc_id, action)

    def choose(self, game_id: str, choice_id: str) -> dict[str, Any]:
        return choices.choose(self._dependencies.choices, game_id, choice_id)

    @staticmethod
    def _queue_followup_event(game: GameState, event: dict[str, Any]) -> None:
        '将必得奖励接到当前事件链末端，避免被渡劫或剧情事件覆盖。'
        return choices._queue_followup_event(game, event)

    def _resolve_breakthroughs(self, game: GameState, rng: random.Random) -> None:
        from .actions.exploration import reconcile_boundary
        reconcile_boundary(self._exploration_dependencies(), game, rng)
        return breakthroughs._resolve_breakthroughs(self._dependencies.breakthroughs, game, rng)

    @staticmethod
    def _manual_minor_layers(player: Player) -> set[int]:
        return breakthroughs._manual_minor_layers(player)

    def _manual_breakthrough_kind(self, player: Player) -> str | None:
        return breakthroughs._manual_breakthrough_kind(self._dependencies.breakthroughs, player)

    @staticmethod
    def _minor_stage_target(player: Player) -> str:
        return breakthroughs._minor_stage_target(player)

    def _minor_layer_target(self, player: Player) -> str:
        return breakthroughs._minor_layer_target(self._dependencies.breakthroughs, player)

    @staticmethod
    def _minor_pity_key(player: Player) -> str:
        return breakthroughs._minor_pity_key(player)

    def _minor_pity_bonus(self, player: Player) -> float:
        return breakthroughs._minor_pity_bonus(self._dependencies.breakthroughs, player)

    def _record_minor_pity_failure(self, player: Player) -> float:
        return breakthroughs._record_minor_pity_failure(self._dependencies.breakthroughs, player)

    def _clear_minor_pity(self, player: Player) -> None:
        return breakthroughs._clear_minor_pity(self._dependencies.breakthroughs, player)

    @staticmethod
    def _major_breakthrough_requirement(player: Player) -> dict[str, Any]:
        return breakthroughs._major_breakthrough_requirement(player)

    @staticmethod
    def _root_probability_group(player: Player) -> str:
        return breakthroughs._root_probability_group(player)

    def _breakthrough_chance(self, player: Player, major: bool, allow_aids: bool=True) -> dict[str, float]:
        return breakthroughs._breakthrough_chance(self._dependencies.breakthroughs, player, major, allow_aids)

    @staticmethod
    def _joint_companion_eligible(player: Player) -> dict[str, Any] | None:
        return breakthroughs._joint_companion_eligible(player)

    def _complete_joint_companion_breakthrough(self, game: GameState, rng: random.Random) -> None:
        return breakthroughs._complete_joint_companion_breakthrough(self._dependencies.breakthroughs, game, rng)

    @staticmethod
    def _consume_breakthrough_aids(player: Player, scope: str) -> None:
        return breakthroughs._consume_breakthrough_aids(player, scope)

    def _start_voisinage_backlash(self, game: GameState, doctrine_id: str) -> None:
        from .progression.immortal_trials import start
        start(self._dependencies.immortal_trials, game, 'voisinage_backlash', doctrine_id=doctrine_id)

    def _start_breakthrough_trial(self, game: GameState, kind: str, source: int, target: int, old_label: str, major: bool, rng: random.Random) -> None:
        from .progression import asura_trials
        if kind in asura_trials.KINDS:
            return asura_trials.start(self._dependencies.asura_trials, game, kind)
        from .progression.immortal_trials import KINDS, start
        if kind in KINDS:
            return start(self._dependencies.immortal_trials, game, kind)
        return breakthroughs._start_breakthrough_trial(self._dependencies.breakthroughs, game, kind, source, target, old_label, major, rng)

    def _queue_heavenly_demon_battle(self, game: GameState, rng: random.Random, soul: dict[str, Any] | None) -> None:
        return breakthroughs._queue_heavenly_demon_battle(self._dependencies.breakthroughs, game, rng, soul)

    def _resolve_heavenly_demon_battle(self, game: GameState, step: str, rng: random.Random) -> tuple[str, str]:
        return breakthroughs._resolve_heavenly_demon_battle(self._dependencies.breakthroughs, game, step, rng)

    def _complete_major_breakthrough(self, game: GameState, rng: random.Random, old_label: str) -> None:
        return breakthroughs._complete_major_breakthrough(self._dependencies.breakthroughs, game, rng, old_label)

    def _complete_minor_breakthrough(self, game: GameState, rng: random.Random, old_label: str) -> None:
        return breakthroughs._complete_minor_breakthrough(self._dependencies.breakthroughs, game, rng, old_label)

    def _resolve_trial_step(self, game: GameState, step: str, rng: random.Random) -> tuple[str, str]:
        from .progression import asura_trials
        if (game.active_trial or {}).get("kind") in asura_trials.KINDS:
            return asura_trials.resolve(self._dependencies.asura_trials, game, step, rng)
        from .progression.immortal_trials import KINDS, resolve
        if (game.active_trial or {}).get('kind') in KINDS:
            return resolve(self._dependencies.immortal_trials, game, step, rng)
        return trials._resolve_trial_step(self._dependencies.trials, game, step, rng)

    def _resolve_celestial_ascension_step(self, game: GameState, step: str, rng: random.Random) -> tuple[str, str]:
        return trials._resolve_celestial_ascension_step(self._dependencies.trials, game, step, rng)

    def _resolve_asura_ascension_step(self, game: GameState, step: str, rng: random.Random) -> tuple[str, str]:
        return trials._resolve_asura_ascension_step(self._dependencies.trials, game, step, rng)

    def _maybe_immortal_conversion_event(self, game: GameState, rng: random.Random) -> bool:
        return trials._maybe_immortal_conversion_event(self._dependencies.trials, game, rng)

    def _complete_immortal_conversion_stage(self, game: GameState, expected_stage: int) -> tuple[str, str]:
        return trials._complete_immortal_conversion_stage(self._dependencies.trials, game, expected_stage)

    @staticmethod
    def _body_tribulation_damage_reduction(player: Player) -> float:
        return trials._body_tribulation_damage_reduction(player)

    def _tribulation_damage_reduction(self, player: Player, kind: str='heavenly') -> float:
        return trials._tribulation_damage_reduction(self._dependencies.trials, player, kind)

    @staticmethod
    def _tribulation_base_power_cap(world: str) -> float | None:
        return trials._tribulation_base_power_cap(world)

    def _check_tribulation(self, game: GameState, rng: random.Random) -> None:
        return trials._check_tribulation(self._dependencies.trials, game, rng)

    def _generate_cultivator_target(self, player: Player, target_name: str, settings: dict[str, Any], rng: random.Random, game: GameState | None=None, forced_race: str | None=None, use_player_concealment: bool=False) -> dict[str, Any]:
        return encounters._generate_cultivator_target(self._dependencies.encounters, player, target_name, settings, rng, game, forced_race, use_player_concealment)

    @staticmethod
    def _encounter_person_name(race_id: str, rng: random.Random) -> str:
        return encounters._encounter_person_name(race_id, rng)

    def _cache_encounter_target(self, game: GameState, target: dict[str, Any], rng: random.Random) -> None:
        'Stage disposable strangers; promote only repeat/important characters.'
        return encounters._cache_encounter_target(self._dependencies.encounters, game, target, rng)

    def _would_enter_spirit_ranking(self, game: GameState, npc: SectNpc, power: float) -> bool:
        return encounters._would_enter_spirit_ranking(self._dependencies.encounters, game, npc, power)

    def _promote_cached_npc(self, game: GameState, npc_id: str, reason: str) -> SectNpc | None:
        return encounters._promote_cached_npc(self._dependencies.encounters, game, npc_id, reason)

    def _add_enemy_party(self, target: dict[str, Any], settings: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        return encounters._add_enemy_party(self._dependencies.encounters, target, settings, rng)

    def _maybe_probability_story_event(self, game: GameState, rng: random.Random) -> bool:
        return encounters._maybe_probability_story_event(self._dependencies.encounters, game, rng)

    def _maybe_artifact_synthesis(self, game: GameState, rng: random.Random) -> bool:
        return encounters._maybe_artifact_synthesis(self._dependencies.encounters, game, rng)

    def _maybe_xiang_node_event(self, game: GameState, rng: random.Random) -> bool:
        return encounters._maybe_xiang_node_event(self._dependencies.encounters, game, rng)

    def _roll_escalating_event(self, game: GameState, event: dict[str, Any], rng: random.Random) -> bool:
        return encounters._roll_escalating_event(self._dependencies.encounters, game, event, rng)

    def _maybe_faction_event(self, game: GameState, rng: random.Random) -> bool:
        return encounters._maybe_faction_event(self._dependencies.encounters, game, rng)

    def _effect(self, effect: dict[str, Any], game: GameState, pending: dict[str, Any], rng: random.Random) -> tuple[str | None, str]:
        if effect["type"] == "buddhist_assembly":
            return self._resolve_buddhist_assembly(effect, game, pending, rng)
        return effects._effect(self._dependencies.effects, effect, game, pending, rng)

    @staticmethod
    def _select_npc_treasure(npc: SectNpc, rng: random.Random) -> str | None:
        return npcs._select_npc_treasure(npc, rng)

    def _npc_power(self, npc: SectNpc) -> float:
        return npcs._npc_power(self._dependencies.npcs, npc)

    def _npc_breakthrough_probability(self, npc: SectNpc) -> float:
        return npcs._npc_breakthrough_probability(self._dependencies.npcs, npc)

    def _npc_faction_id(self, game: GameState, npc_id: str) -> str | None:
        return npcs._npc_faction_id(self._dependencies.npcs, game, npc_id)

    def _sect_members(self, game: GameState, sect: SectState) -> list[SectNpc]:
        return npcs._sect_members(self._dependencies.npcs, game, sect)

    def _find_npc(self, game: GameState, npc_id: str) -> SectNpc | None:
        return npcs._find_npc(self._dependencies.npcs, game, npc_id)

    @staticmethod
    def _random_npc_path(faction_id: str, rng: random.Random) -> str:
        return npcs._random_npc_path(faction_id, rng)

    @staticmethod
    def _random_npc_root(realm_index: int, rng: random.Random) -> str:
        '人界 NPC 只生成常规五行或变异灵根，且高境界自然筛去伪灵根。'
        return npcs._random_npc_root(realm_index, rng)

    @staticmethod
    def _npc_root_name(root_id: str) -> str:
        return npcs._npc_root_name(root_id)

    @staticmethod
    def _npc_root_efficiency(root_id: str) -> float:
        return npcs._npc_root_efficiency(root_id)

    @staticmethod
    def _mortal_root_completion_chance(player: Player) -> float:
        return npcs._mortal_root_completion_chance(player)

    def _maybe_mortal_root_completion(self, game: GameState, rng: random.Random) -> bool:
        return npcs._maybe_mortal_root_completion(self._dependencies.npcs, game, rng)

    def _annual_world_npc_update(self, game: GameState, rng: random.Random) -> list[str]:
        return npcs._annual_world_npc_update(self._dependencies.npcs, game, rng)

    def _maybe_notorious_npc_killing(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        return npcs._maybe_notorious_npc_killing(self._dependencies.npcs, game, rng, news)

    @staticmethod
    def _all_world_npcs(game: GameState) -> list[SectNpc]:
        return npcs._all_world_npcs(game)

    @staticmethod
    def _npc_lethal_chance(world: str, realm_index: int, context: str) -> float:
        return npcs._npc_lethal_chance(world, realm_index, context)

    @staticmethod
    def _npc_lifespan_multiplier(path: str) -> int:
        return npcs._npc_lifespan_multiplier(path)

    @classmethod
    def _scale_npc_lifespan(cls, lifespan: int | None, path: str, age: int=0) -> int | None:
        return npcs._scale_npc_lifespan(bind_npc_class_dependencies(cls), lifespan, path, age)

    def _maybe_npc_found_power(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        return npcs._maybe_npc_found_power(self._dependencies.npcs, game, rng, news)

    def _advance_npc_cultivation(self, npc: SectNpc, rng: random.Random, allow_spirit_crossing: bool=True, breakthrough_bonus: float=0.0) -> dict[str, str] | None:
        return npcs._advance_npc_cultivation(self._dependencies.npcs, npc, rng, allow_spirit_crossing, breakthrough_bonus)

    def _resolve_npc_periodic_tribulation(self, game: GameState, npc: SectNpc, rng: random.Random, affiliation: str='') -> str | None:
        'Resolve one NPC thunder tribulation; immortal lifespan does not mean immortal NPCs.'
        return npcs._resolve_npc_periodic_tribulation(self._dependencies.npcs, game, npc, rng, affiliation)

    @staticmethod
    def _ascension_destination(path: str, player=None) -> str:
        default = npcs._ascension_destination(path)
        return modifier(player, "ascension_destination", default) if player else default

    @staticmethod
    def _npc_realm_name(npc: SectNpc) -> str:
        return npcs._npc_realm_name(npc)

    @staticmethod
    def _stable_secret_art_roll(identity: str) -> int:
        return npcs._stable_secret_art_roll(identity)

    def _ensure_npc_concealment(self, npc: SectNpc) -> tuple[int, int] | None:
        return npcs._ensure_npc_concealment(self._dependencies.npcs, npc)

    def _npc_cultivation_perception(self, game: GameState, npc: SectNpc, require_realm_visibility: bool=False) -> dict[str, Any]:
        return npcs._npc_cultivation_perception(self._dependencies.npcs, game, npc, require_realm_visibility)

    @staticmethod
    def _dynamic_sect_title(npc: SectNpc, sect: SectState) -> str:
        '随修为投影宗门职位，同时保留掌门等唯一职衔。'
        return npcs._dynamic_sect_title(npc, sect)

    @staticmethod
    def _default_npc_main_technique(npc: SectNpc) -> str | None:
        return npcs._default_npc_main_technique(npc)

    @staticmethod
    def _recruit_realm_index(roll: float, world: str='human') -> int:
        return npcs._recruit_realm_index(roll, world)

    @classmethod
    def _roll_recruit_age_lifespan(cls, realm_index: int, path: str, rng: random.Random, *, young: bool=False) -> tuple[int, int | None]:
        'Generate recruits with a meaningful amount of lifespan still remaining.'
        return npcs._roll_recruit_age_lifespan(bind_npc_class_dependencies(cls), realm_index, path, rng, young=young)

    def _recruit_sect_npc(self, sect: SectState, world_age: int, rng: random.Random) -> SectNpc:
        return npcs._recruit_sect_npc(self._dependencies.npcs, sect, world_age, rng)

    @staticmethod
    def _party_invitation_chance(player: Player, npc: SectNpc, global_hostility: float=0.0) -> float:
        return world_relationships._party_invitation_chance(player, npc, global_hostility)

    def _party_crossing_candidate(self, game: GameState, npc_id: str) -> dict[str, Any] | None:
        return world_relationships._party_crossing_candidate(self._dependencies.world_relationships, game, npc_id)

    def _persist_relationship_npc(self, game: GameState, relation: dict[str, Any], reason: str) -> SectNpc:
        return world_relationships._persist_relationship_npc(self._dependencies.world_relationships, game, relation, reason)

    def _adjust_person_affinity(self, game: GameState, npc_id: str, delta: float) -> float:
        return world_relationships._adjust_person_affinity(self._dependencies.world_relationships, game, npc_id, delta)

    def _set_person_affinity(self, game: GameState, npc_id: str, value: float) -> float:
        'Set, rather than add, affinity on both the persistent NPC and relation snapshot.'
        return world_relationships._set_person_affinity(self._dependencies.world_relationships, game, npc_id, value)

    @staticmethod
    def _revenge_cooldown_key(scope: str, family: str='', adversary_id: str='') -> str:
        return world_relationships._revenge_cooldown_key(scope, family, adversary_id)

    def _revenge_ready(self, game: GameState, family: str, adversary_id: str) -> bool:
        'All revenge sources share one global gate and also retain per-source gates.'
        return world_relationships._revenge_ready(self._dependencies.world_relationships, game, family, adversary_id)

    def _record_revenge_trigger(self, game: GameState, family: str, adversary_id: str) -> int:
        'Start an escalating action-unit cooldown after a revenge event is opened.'
        return world_relationships._record_revenge_trigger(self._dependencies.world_relationships, game, family, adversary_id)

    def _personal_npcs(self, game: GameState) -> list[SectNpc]:
        return world_relationships._personal_npcs(self._dependencies.world_relationships, game)

    def _high_affinity_npcs(self, game: GameState, exclude_id: str='') -> list[SectNpc]:
        return world_relationships._high_affinity_npcs(self._dependencies.world_relationships, game, exclude_id)

    def _maybe_affinity_gift(self, game: GameState, rng: random.Random) -> bool:
        return world_relationships._maybe_affinity_gift(self._dependencies.world_relationships, game, rng)

    def _maybe_personal_revenge(self, game: GameState, rng: random.Random) -> bool:
        return world_relationships._maybe_personal_revenge(self._dependencies.world_relationships, game, rng)

    def _try_conceive_child(self, game: GameState, rng: random.Random) -> str:
        return world_relationships._try_conceive_child(self._dependencies.world_relationships, game, rng)

    def _annual_offspring_and_family_update(self, game: GameState, rng: random.Random) -> list[str]:
        self._family_register_children(game)
        news = world_relationships._annual_offspring_and_family_update(self._dependencies.world_relationships, game, rng)
        news.extend(self._family_annual_governance(game, rng))
        return news

    def _relationship_cultivation_perception(self, game: GameState, person: dict[str, Any], title: str='故交') -> dict[str, Any]:
        'Apply the same secret-art visibility rules to compact relationship snapshots.'
        return world_relationships._relationship_cultivation_perception(self._dependencies.world_relationships, game, person, title)

    def _relationship_snapshot(self, person_id: str, name: str, realm_index: int, layer: int, source: str, age: int, lifespan: int | None, alive: bool=True, death_reason: str | None=None, spirit_root: str='', cultivation_progress: float=0.0, path: str='dao', race: str='human', world: str='human', main_technique_id: str | None=None, affinity: float=20.0, gender: str='') -> dict[str, Any]:
        return world_relationships._relationship_snapshot(self._dependencies.world_relationships, person_id, name, realm_index, layer, source, age, lifespan, alive, death_reason, spirit_root, cultivation_progress, path, race, world, main_technique_id, affinity, gender)

    def _generated_relationship(self, player: Player, role: str, rng: random.Random) -> dict[str, Any]:
        return world_relationships._generated_relationship(self._dependencies.world_relationships, player, role, rng)

    def _sync_relationship_records(self, game: GameState) -> bool:
        '补齐旧存档字段，并让宗门师徒信息跟随真实 NPC。'
        return world_relationships._sync_relationship_records(self._dependencies.world_relationships, game)

    def _annual_relationship_update(self, game: GameState, rng: random.Random | None=None) -> None:
        return world_relationships._annual_relationship_update(self._dependencies.world_relationships, game, rng)

    def _sync_party_state(self, game: GameState) -> bool:
        'Discard references that can no longer represent an active companion.'
        return world_relationships._sync_party_state(self._dependencies.world_relationships, game)

    @staticmethod
    def _ensure_race_relations(game: GameState) -> bool:
        return world_factions._ensure_race_relations(game)

    @staticmethod
    def _governance_threshold(world: str) -> int:
        return world_factions._governance_threshold(world)

    @staticmethod
    def _faction_meta(game: GameState, faction_id: str) -> dict[str, Any]:
        return world_factions._faction_meta(game, faction_id)

    @staticmethod
    def _ensure_sect_relations(game: GameState) -> bool:
        return world_factions._ensure_sect_relations(game)

    def _has_race_voice(self, game: GameState) -> bool:
        return world_factions._has_race_voice(self._dependencies.world_factions, game)

    def _has_sect_voice(self, game: GameState) -> bool:
        return world_factions._has_sect_voice(self._dependencies.world_factions, game)

    def _has_family_voice(self, game: GameState) -> bool:
        return world_factions._has_family_voice(self._dependencies.world_factions, game)

    def _check_sect_extinction(self, game: GameState, sect: SectState) -> bool:
        return world_factions._check_sect_extinction(self._dependencies.world_factions, game, sect)

    def _dissolve_player_sect(self, game: GameState, sect: SectState, reason: str) -> None:
        'Disband a weak player sect without falsely killing every former member.'
        return world_factions._dissolve_player_sect(self._dependencies.world_factions, game, sect, reason)

    def _maybe_founded_sect_pressure(self, game: GameState, rng: random.Random) -> bool:
        return world_factions._maybe_founded_sect_pressure(self._dependencies.world_factions, game, rng)

    def _annual_sect_update(self, game: GameState, rng: random.Random) -> list[str]:
        return world_factions._annual_sect_update(self._dependencies.world_factions, game, rng)

    def _annual_race_diplomacy_update(self, game: GameState, rng: random.Random) -> list[str]:
        'Compatibility wrapper. Diplomacy now advances once per action unit, not once per year.'
        return world_factions._annual_race_diplomacy_update(self._dependencies.world_factions, game, rng)

    def _advance_diplomacy_unit(self, game: GameState, rng: random.Random) -> list[str]:
        return world_factions._advance_diplomacy_unit(self._dependencies.world_factions, game, rng)

    def _random_race_diplomacy_event(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        return world_factions._random_race_diplomacy_event(self._dependencies.world_factions, game, rng, news)

    def _random_sect_diplomacy_event(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        return world_factions._random_sect_diplomacy_event(self._dependencies.world_factions, game, rng, news)

    def _pressure_weak_npc_powers(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        return world_factions._pressure_weak_npc_powers(self._dependencies.world_factions, game, rng, news)

    def _simulate_cultivator_duel(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        return world_factions._simulate_cultivator_duel(self._dependencies.world_factions, game, rng, news)

    def _set_diplomatic_relation(self, game: GameState, relation: dict[str, Any], status: str, first: str, second: str, kind: str, affinity: float) -> None:
        return world_factions._set_diplomatic_relation(self._dependencies.world_factions, game, relation, status, first, second, kind, affinity)

    def _race_power(self, game: GameState, race_id: str) -> float:
        return world_factions._race_power(self._dependencies.world_factions, game, race_id)

    def _sect_power(self, game: GameState, sect_id: str) -> float:
        return world_factions._sect_power(self._dependencies.world_factions, game, sect_id)

    def _simulate_war_casualties(self, game: GameState, rng: random.Random, kind: str) -> list[str]:
        return world_factions._simulate_war_casualties(self._dependencies.world_factions, game, rng, kind)

    def _maybe_race_war_ambush(self, game: GameState, rng: random.Random) -> bool:
        return self._maybe_map_war_encounter(game, rng) or world_factions._maybe_race_war_ambush(self._dependencies.world_factions, game, rng)

    @staticmethod
    def _hostility_key(kind: str, entity_id: str) -> str:
        return hostility_runtime._hostility_key(kind, entity_id)

    def _maybe_wanted_encounter(self, game: GameState, rng: random.Random) -> bool:
        return hostility_runtime._maybe_wanted_encounter(self._dependencies.hostility, game, rng)

    @staticmethod
    def _world_coalition_amnesty_fame(player: Player, world: str) -> float:
        return hostility_runtime._world_coalition_amnesty_fame(player, world)

    @staticmethod
    def _record_world_coalition_amnesty(player: Player, world: str) -> None:
        return hostility_runtime._record_world_coalition_amnesty(player, world)

    def _player_protected_npc_ids(self, game: GameState) -> set[str]:
        return hostility_runtime._player_protected_npc_ids(self._dependencies.hostility, game)

    def _hostility_entity_members(self, game: GameState, kind: str, entity_id: str) -> list[SectNpc]:
        return hostility_runtime._hostility_entity_members(self._dependencies.hostility, game, kind, entity_id)

    def _hostility_entity_state(self, game: GameState, key: str) -> dict[str, Any]:
        return hostility_runtime._hostility_entity_state(self._dependencies.hostility, game, key)

    def _queue_wanted_settlement(self, game: GameState, key: str, state: dict[str, Any], rng: random.Random, *, fallen: bool) -> None:
        return hostility_runtime._queue_wanted_settlement(self._dependencies.hostility, game, key, state, rng, fallen=fallen)

    def _resolve_wanted_settlement(self, game: GameState, pending: dict[str, Any], mode: str, rng: random.Random) -> tuple[str, str]:
        return hostility_runtime._resolve_wanted_settlement(self._dependencies.hostility, game, pending, mode, rng)

    def _wanted_target(self, game: GameState, kind: str, entity_id: str, hostility: float, rng: random.Random) -> dict[str, Any]:
        return hostility_runtime._wanted_target(self._dependencies.hostility, game, kind, entity_id, hostility, rng)

    def _resolve_wanted_response(self, game: GameState, pending: dict[str, Any], response: str, rng: random.Random) -> tuple[str, str]:
        return hostility_runtime._resolve_wanted_response(self._dependencies.hostility, game, pending, response, rng)

    def _imprison_or_execute(self, game: GameState, key: str, rng: random.Random, surrendered: bool=False) -> str:
        return hostility_runtime._imprison_or_execute(self._dependencies.hostility, game, key, rng, surrendered)

    def _hostility_name(self, key: str, game: GameState | None=None) -> str:
        return hostility_runtime._hostility_name(self._dependencies.hostility, key, game)

    def _advance_player_bounties(self, game: GameState, rng: random.Random) -> None:
        return hostility_runtime._advance_player_bounties(self._dependencies.hostility, game, rng)

    def _public_major_breakthrough(self, player: Player) -> dict[str, Any]:
        return character_view._public_major_breakthrough(self._dependencies.character_view, player)

    def _public_body_cultivation(self, player: Player) -> dict[str, Any]:
        return character_view._public_body_cultivation(self._dependencies.character_view, player)

    def _public_dao_companion(self, game: GameState) -> dict[str, Any] | None:
        return character_view._public_dao_companion(self._dependencies.character_view, game)

    def _public_dao_friends(self, game: GameState) -> list[dict[str, Any]]:
        return character_view._public_dao_friends(self._dependencies.character_view, game)

    def _relationship_can_join_faction(self, game: GameState, relation: dict[str, Any]) -> bool:
        return character_view._relationship_can_join_faction(self._dependencies.character_view, game, relation)

    def _public_personal_relations(self, game: GameState) -> dict[str, list[dict[str, Any]]]:
        return character_view._public_personal_relations(self._dependencies.character_view, game)

    def _relationship_combat_power(self, relation: dict[str, Any]) -> float:
        return character_view._relationship_combat_power(self._dependencies.character_view, relation)

    def _public_party(self, game: GameState) -> list[dict[str, Any]]:
        return character_view._public_party(self._dependencies.character_view, game)

    def _public_wanted(self, game: GameState) -> list[dict[str, Any]]:
        return character_view._public_wanted(self._dependencies.character_view, game)

    def _public_world_npcs(self, game: GameState) -> list[dict[str, Any]]:
        return world_view._public_world_npcs(self._dependencies.world_view, game)

    def _public_spirit_ranking(self, game: GameState) -> dict[str, Any]:
        return world_view._public_spirit_ranking(self._dependencies.world_view, game)

    def _public_race_system(self, game: GameState) -> dict[str, Any]:
        return world_view._public_race_system(self._dependencies.world_view, game)

    def _public_world_route(self, game: GameState) -> dict[str, Any]:
        return world_view._public_world_route(self._dependencies.world_view, game)

    def _public_family(self, game: GameState) -> dict[str, Any]:
        return self._family_presentation(game, faction_view._public_family(self._dependencies.faction_view, game))

    def _public_governance(self, game: GameState) -> dict[str, Any]:
        return faction_view._public_governance(self._dependencies.faction_view, game)

    def _public_faction(self, game: GameState) -> dict[str, Any]:
        result = faction_view._public_faction(self._dependencies.faction_view, game)
        result["total_power"] = sum(float(row.get("combat_power", 0)) for row in result.get("roster", []))
        return result

    def _public_sect_diplomacy(self, game: GameState, sect: SectState) -> list[dict[str, Any]]:
        return faction_view._public_sect_diplomacy(self._dependencies.faction_view, game, sect)

    def _vassal_transfer_candidates(self, game: GameState, kind: str, own_id: str, target_id: str, relation: dict[str, Any]) -> list[dict[str, Any]]:
        return faction_view._vassal_transfer_candidates(self._dependencies.faction_view, game, kind, own_id, target_id, relation)

    @staticmethod
    def _court_config() -> dict[str, Any]:
        return court_state._court_config()

    @staticmethod
    def _court_grade_for_realm(realm_index: int) -> int:
        return court_state._court_grade_for_realm(realm_index)

    def _ensure_heavenly_court(self, game: GameState, rng: Any) -> bool:
        return court_state._ensure_heavenly_court(self._dependencies.court_state, game, rng)

    def _player_court_representative(self, game: GameState) -> bool:
        return court_state._player_court_representative(self._dependencies.court_state, game)

    def _sync_player_court_identity(self, game: GameState) -> None:
        return court_state._sync_player_court_identity(self._dependencies.court_state, game)

    @staticmethod
    def _court_holder_ids(court: dict[str, Any]) -> list[str]:
        return court_state._court_holder_ids(court)

    @staticmethod
    def _court_player_controls(court: dict[str, Any]) -> int:
        return court_state._court_player_controls(court)

    def _court_open_election(self, game: GameState, office_id: str, rng: Any) -> None:
        return court_state._court_open_election(self._dependencies.court_state, game, office_id, rng)

    def _court_open_next_queued_election(self, game: GameState, rng: Any) -> None:
        return court_state._court_open_next_queued_election(self._dependencies.court_state, game, rng)

    def _court_resolve_election_round(
        self, game: GameState, rng: Any, method: str, pledge_id: str,
    ) -> tuple[bool, str]:
        return court_state._court_resolve_election_round(self._dependencies.court_state, game, rng, method, pledge_id)

    def _advance_heavenly_court_unit(self, game: GameState, rng: Any) -> list[str]:
        return court_state._advance_heavenly_court_unit(self._dependencies.court_state, game, rng)

    def resolve_heavenly_election(self, game_id: str, method: str = "none", pledge_id: str = "") -> dict[str, Any]:
        return court_state.resolve_heavenly_election(self._dependencies.court_state, game_id, method, pledge_id)

    @staticmethod
    def _court_honor_pledge(court: dict[str, Any], kind: str, policy_id: str) -> None:
        return court_state._court_honor_pledge(court, kind, policy_id)

    def heavenly_court_action(
        self, game_id: str, action: str, target_id: str = "", enact: bool | None = None,
        influence_spend: int = 0,
    ) -> dict[str, Any]:
        return court_state.heavenly_court_action(self._dependencies.court_state, game_id, action, target_id, enact, influence_spend)

    def _court_examination(self, game: GameState, rng: Any) -> tuple[str, str]:
        return court_state._court_examination(self._dependencies.court_state, game, rng)

    def _court_enact_decree(
        self, game: GameState, decree_id: str, target_id: str, rng: Any, influence_spend: int = 0, *, actor_id: str = "player",
    ) -> tuple[str, str]:
        return court_state._court_enact_decree(self._dependencies.court_state, game, decree_id, target_id, rng, influence_spend, actor_id=actor_id)

    def _court_vote_law(
        self, game: GameState, law_id: str, enact: bool | None, rng: Any, influence_spend: int = 0, *, actor_id: str = "player",
    ) -> tuple[str, str]:
        return court_state._court_vote_law(self._dependencies.court_state, game, law_id, enact, rng, influence_spend, actor_id=actor_id)

    def _court_spend_influence(self, game: GameState, requested: int) -> int:
        return court_state._court_spend_influence(self._dependencies.court_state, game, requested)

    def _add_court_merit(self, game: GameState, amount: int) -> str:
        return court_state._add_court_merit(self._dependencies.court_state, game, amount)

    def _public_heavenly_court(self, game: GameState) -> dict[str, Any]:
        return court_state._public_heavenly_court(self._dependencies.court_state, game)

    def _court_law_active(self, game: GameState, law_id: str) -> bool:
        return court_state._court_law_active(self._dependencies.court_state, game, law_id)

    def _court_retire_unavailable(self, game):
        return court_governance._court_retire_unavailable(self._dependencies.court_governance, game)

    def _court_autonomous_votes(self, court, actor_id, law_id, desired, rng):
        return court_governance._court_autonomous_votes(self._dependencies.court_governance, court, actor_id, law_id, desired, rng)

    def _court_govern(self, game, rng):
        return court_governance._court_govern(self._dependencies.court_governance, game, rng)

    def _court_conflicts(self, law_id):
        return court_lifecycle._court_conflicts(self._dependencies.court_lifecycle, law_id)

    def _court_normalize(self, game):
        return court_lifecycle._court_normalize(self._dependencies.court_lifecycle, game)

    def _court_prune_decrees(self, court):
        return court_lifecycle._court_prune_decrees(self._dependencies.court_lifecycle, court)

    def _court_finish_unattended(self, game, rng):
        return court_lifecycle._court_finish_unattended(self._dependencies.court_lifecycle, game, rng)

    def _court_schedule_elections(self, game, rng):
        return court_lifecycle._court_schedule_elections(self._dependencies.court_lifecycle, game, rng)

    def _court_pay_stipend(self, game):
        return court_lifecycle._court_pay_stipend(self._dependencies.court_lifecycle, game)

    def _begin_yaochi_action(self, game, action):
        return court_yaochi._begin_yaochi_action(self._dependencies.court_yaochi, game, action)

    def _finish_yaochi_action(self, game, action, elapsed):
        return court_yaochi._finish_yaochi_action(self._dependencies.court_yaochi, game, action, elapsed)

    def yaochi_action(self, game_id, action, target_id='', amount=1):
        return court_yaochi.yaochi_action(self._dependencies.court_yaochi, game_id, action, target_id, amount)

    def _public_yaochi(self, game):
        return court_yaochi._public_yaochi(self._dependencies.court_yaochi, game)


    @staticmethod
    def _tianji_tag_similarity(
        required: dict[str, float], supplied: dict[str, float]
    ) -> float:
        return tianji_compat._tianji_tag_similarity(required, supplied)

    @staticmethod
    def _tianji_closeness_factor(closeness: float) -> float:
        return tianji_compat._tianji_closeness_factor(closeness)

    @staticmethod
    def _tianji_public_effect(effect: dict[str, Any]) -> dict[str, Any]:
        return tianji_compat._tianji_public_effect(effect)

    @staticmethod
    def _tianji_config() -> dict[str, Any]:
        return tianji_compat._tianji_config()

    @staticmethod
    def _tianji_artifact(state: dict[str, Any], artifact_id: str) -> dict[str, Any]:
        return tianji_compat._tianji_artifact(state, artifact_id)

    @property
    def _tianji_dependencies(self):
        """Compatibility view of the explicitly composed system contracts."""
        return self._dependencies.tianji

    def _tianji_material_instance(
        self,
        game: GameState,
        definition: dict[str, Any],
        rng: random.Random,
        source: str,
    ) -> dict[str, Any]:
        return tianji_forging._tianji_material_instance(
            self._dependencies.tianji.forging, game, definition, rng, source
        )

    def _append_tianji_market_offers(
        self,
        game: GameState,
        offers: list[dict[str, Any]],
        *,
        tier: int,
        market_name: str,
        location_id: str,
    ) -> None:
        return tianji_forging._append_tianji_market_offers(
            self._dependencies.tianji.forging,
            game,
            offers,
            tier=tier,
            market_name=market_name,
            location_id=location_id,
        )

    def _tianji_material_bought(
        self, game: GameState, instance: dict[str, Any]
    ) -> None:
        return tianji_forging._tianji_material_bought(
            self._dependencies.tianji.forging, game, instance
        )

    def _tianji_target_preview(
        self, game: GameState, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return tianji_forging._tianji_target_preview(
            self._dependencies.tianji.forging, game, payload
        )

    def preview_tianji_forge(
        self, game_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return tianji_forging.preview_tianji_forge(
            self._dependencies.tianji.forging, game_id, payload
        )

    def forge_tianji_artifact(
        self, game_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return tianji_forging.forge_tianji_artifact(
            self._dependencies.tianji.forging, game_id, payload
        )

    def _generate_tianji_materials(self, game: GameState) -> list[dict[str, Any]]:
        return tianji_generation._generate_tianji_materials(
            self._dependencies.tianji.generation, game
        )

    def _next_tianji_name(
        self,
        rng: random.Random,
        theme: dict[str, Any],
        mold_id: str,
        used_names: set[str],
        used_stems: set[str],
        used_prefixes: set[str],
        index: int,
    ) -> tuple[str, str]:
        return tianji_generation._next_tianji_name(
            self._dependencies.tianji.generation,
            rng,
            theme,
            mold_id,
            used_names,
            used_stems,
            used_prefixes,
            index,
        )

    def _next_tianji_buff_name(
        self,
        rng: random.Random,
        theme: dict[str, Any],
        core: str,
        used_names: set[str],
        index: int,
    ) -> str:
        return tianji_generation._next_tianji_buff_name(
            self._dependencies.tianji.generation, rng, theme, core, used_names, index
        )

    def _tianji_rule_effects(
        self, seed: int, artifact_id: str, theme: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return tianji_generation._tianji_rule_effects(
            self._dependencies.tianji.generation, seed, artifact_id, theme
        )

    def _generate_tianji_artifacts(
        self, game: GameState, materials: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return tianji_generation._generate_tianji_artifacts(
            self._dependencies.tianji.generation, game, materials
        )

    def _tianji_reveal(
        self, game: GameState, artifact_id: str, level: int, source: str
    ) -> bool:
        return tianji_intelligence._tianji_reveal(
            self._dependencies.tianji.intelligence, game, artifact_id, level, source
        )

    def _tianji_npc_conversation_clue(
        self, game: GameState, npc_id: str, rng: random.Random
    ) -> str:
        "Occasionally turn an actual NPC conversation into persistent intel."
        return tianji_intelligence._tianji_npc_conversation_clue(
            self._dependencies.tianji.intelligence, game, npc_id, rng
        )

    def _maybe_tianji_intelligence_event(
        self, game: GameState, rng: random.Random
    ) -> str | None:
        "Resolve a rare, non-clickable clue event after a real time action."
        return tianji_intelligence._maybe_tianji_intelligence_event(
            self._dependencies.tianji.intelligence, game, rng
        )

    def tianji_action(
        self, game_id: str, action: str, artifact_id: str
    ) -> dict[str, Any]:
        return tianji_intelligence.tianji_action(
            self._dependencies.tianji.intelligence, game_id, action, artifact_id
        )

    def debug_reveal_all_tianji(self, game_id: str) -> dict[str, Any]:
        return tianji_intelligence.debug_reveal_all_tianji(
            self._dependencies.tianji.intelligence, game_id
        )

    def _tianji_persistent_npcs(self, game: GameState, world: str) -> list[Any]:
        return tianji_npcs._tianji_persistent_npcs(
            self._dependencies.tianji.npcs, game, world
        )

    def _assign_tianji_holders_for_world(self, game: GameState, world: str) -> bool:
        return tianji_npcs._assign_tianji_holders_for_world(
            self._dependencies.tianji.npcs, game, world
        )

    def _inject_tianji_npc_artifacts(
        self, game: GameState, target: dict[str, Any]
    ) -> None:
        return tianji_npcs._inject_tianji_npc_artifacts(
            self._dependencies.tianji.npcs, game, target
        )

    def _tianji_observe_npc(self, game: GameState, npc_id: str) -> None:
        return tianji_npcs._tianji_observe_npc(
            self._dependencies.tianji.npcs, game, npc_id
        )

    def _tianji_preview_npc_power(
        self, game: GameState, target: dict[str, Any]
    ) -> None:
        return tianji_npcs._tianji_preview_npc_power(
            self._dependencies.tianji.npcs, game, target
        )

    def _tianji_handle_npc_kill(self, game: GameState, npc_id: str) -> str:
        return tianji_npcs._tianji_handle_npc_kill(
            self._dependencies.tianji.npcs, game, npc_id
        )

    def _public_tianji(self, game: GameState) -> dict[str, Any]:
        return tianji_presentation._public_tianji(
            self._dependencies.tianji.presentation, game
        )

    def debug_tianji_gameplay(self, game_id: str) -> list[dict[str, Any]]:
        "Return blueprint diagnostics without mutating the frozen definitions."
        return tianji_presentation.debug_tianji_gameplay(
            self._dependencies.tianji.presentation, game_id
        )

    def _refresh_tianji_artifact_names(self, game: GameState) -> None:
        "Migrate only generated names while preserving every frozen rule and recipe."
        return tianji_state._refresh_tianji_artifact_names(
            self._dependencies.tianji.state, game
        )

    def _refresh_tianji_buff_names(self, game: GameState) -> None:
        "Expand old saves' repeated effect labels without changing any rule."
        return tianji_state._refresh_tianji_buff_names(
            self._dependencies.tianji.state, game
        )

    def _ensure_tianji_state(self, game: GameState) -> bool:
        return tianji_state._ensure_tianji_state(self._dependencies.tianji.state, game)

    def _intrigue_has_decision_authority(
        self, game: GameState, kind: str, faction_id: str, member_id: str = intrigue_compat.PLAYER_ID
    ) -> bool:
        return intrigue_governance._intrigue_has_decision_authority(
            self._dependencies.intrigue.governance, game, kind, faction_id, member_id
        )

    @staticmethod
    def _intrigue_player_relation(
        game: GameState, npc_id: str
    ) -> dict[str, Any] | None:
        return intrigue_compat._intrigue_player_relation(game, npc_id)

    @staticmethod
    def _intrigue_recruitment_config() -> dict[str, Any]:
        return intrigue_compat._intrigue_recruitment_config()

    @staticmethod
    def _intrigue_enabled() -> bool:
        return intrigue_compat._intrigue_enabled()

    @staticmethod
    def _intrigue_state(game: GameState) -> dict[str, Any]:
        return intrigue_compat._intrigue_state(game)

    @staticmethod
    def _intrigue_key(kind: str, faction_id: str) -> str:
        return intrigue_compat._intrigue_key(kind, faction_id)

    @property
    def _intrigue_dependencies(self):
        """Compatibility view of the explicitly composed system contracts."""
        return self._dependencies.intrigue

    def _intrigue_auto_appoint_player(
        self,
        game: GameState,
        kind: str,
        faction_id: str,
        record: dict[str, Any],
        members: list[SectNpc],
    ) -> None:
        "Let cultivation order, rather than voting rights, drive ordinary offices.\n\n        The controller still occupies the first (leader) office.  Remaining\n        offices follow the faction's cultivation order, while guest offices\n        remain reserved for external retainers.  This makes a powerful member\n        eligible for office even when their realm is below the independent\n        decision-authority threshold.\n"
        return intrigue_governance._intrigue_auto_appoint_player(
            self._dependencies.intrigue.governance,
            game,
            kind,
            faction_id,
            record,
            members,
        )

    def _intrigue_is_imprisoned(self, game: GameState, npc_id: str) -> bool:
        return intrigue_governance._intrigue_is_imprisoned(
            self._dependencies.intrigue.governance, game, npc_id
        )

    def _intrigue_decision_threshold(self, kind: str) -> int:
        return intrigue_governance._intrigue_decision_threshold(
            self._dependencies.intrigue.governance, kind
        )

    def _intrigue_has_control(
        self, game: GameState, kind: str, faction_id: str
    ) -> bool:
        return intrigue_governance._intrigue_has_control(
            self._dependencies.intrigue.governance, game, kind, faction_id
        )

    def _intrigue_position_specs(self, kind: str) -> dict[str, dict[str, Any]]:
        return intrigue_governance._intrigue_position_specs(
            self._dependencies.intrigue.governance, kind
        )

    def _intrigue_faction_name(
        self, game: GameState, kind: str, faction_id: str
    ) -> str:
        return intrigue_governance._intrigue_faction_name(
            self._dependencies.intrigue.governance, game, kind, faction_id
        )

    def intrigue_personnel_action(
        self,
        game_id: str,
        kind: str,
        action: str,
        npc_id: str,
        position_id: str = "",
        years: int = 1,
        reason: str = "",
    ) -> dict[str, Any]:
        return intrigue_governance.intrigue_personnel_action(
            self._dependencies.intrigue.governance,
            game_id,
            kind,
            action,
            npc_id,
            position_id,
            years,
            reason,
        )

    def _intrigue_pressure_position_occupied(
        self, game: GameState, faction_id: str
    ) -> bool:
        "DLC pressure requires an actually occupied office, never a phantom rival."
        return intrigue_governance._intrigue_pressure_position_occupied(
            self._dependencies.intrigue.governance, game, faction_id
        )

    def _intrigue_can_invite_guest(
        self, game: GameState, npc_id: str, kind: str = "sect"
    ) -> bool:
        return intrigue_guests._intrigue_can_invite_guest(
            self._dependencies.intrigue.guests, game, npc_id, kind
        )

    def intrigue_guest_action(
        self, game_id: str, kind: str, action: str, npc_id: str = ""
    ) -> dict[str, Any]:
        return intrigue_guests.intrigue_guest_action(
            self._dependencies.intrigue.guests, game_id, kind, action, npc_id
        )

    def _intrigue_guest_npcs(
        self, game: GameState, kind: str, faction_id: str
    ) -> list[SectNpc]:
        return intrigue_guests._intrigue_guest_npcs(
            self._dependencies.intrigue.guests, game, kind, faction_id
        )

    def _intrigue_defensive_guest_ids(
        self, game: GameState, kind: str, faction_id: str, world: str
    ) -> list[str]:
        return intrigue_guests._intrigue_defensive_guest_ids(
            self._dependencies.intrigue.guests, game, kind, faction_id, world
        )

    def _intrigue_player_guest_side(
        self, game: GameState, war: dict[str, Any]
    ) -> str | None:
        return intrigue_guests._intrigue_player_guest_side(
            self._dependencies.intrigue.guests, game, war
        )

    def _intrigue_public_member(
        self, game: GameState, npc: SectNpc, record: dict[str, Any]
    ) -> dict[str, Any]:
        return intrigue_presentation._intrigue_public_member(
            self._dependencies.intrigue.presentation, game, npc, record
        )

    def _public_intrigue_recruitment(
        self, game: GameState, faction_id: str, record: dict[str, Any]
    ) -> dict[str, Any]:
        return intrigue_presentation._public_intrigue_recruitment(
            self._dependencies.intrigue.presentation, game, faction_id, record
        )

    def _public_guest_invitation(self, game: GameState) -> dict[str, Any] | None:
        return intrigue_presentation._public_guest_invitation(
            self._dependencies.intrigue.presentation, game
        )

    def _public_intrigue_system(self, game: GameState) -> dict[str, Any]:
        return intrigue_presentation._public_intrigue_system(
            self._dependencies.intrigue.presentation, game
        )

    def _intrigue_recruitment_realm_options(self, world: str) -> list[int]:
        return intrigue_recruitment._intrigue_recruitment_realm_options(
            self._dependencies.intrigue.recruitment, world
        )

    def _normalize_intrigue_recruitment_filters(
        self, game: GameState, filters: dict[str, Any] | None
    ) -> dict[str, Any]:
        return intrigue_recruitment._normalize_intrigue_recruitment_filters(
            self._dependencies.intrigue.recruitment, game, filters
        )

    def _intrigue_recruitment_filter_summary(self, filters: dict[str, Any]) -> str:
        return intrigue_recruitment._intrigue_recruitment_filter_summary(
            self._dependencies.intrigue.recruitment, filters
        )

    def _generate_intrigue_recruitment_session(
        self,
        game: GameState,
        faction_id: str,
        filters: dict[str, Any],
        rng: random.Random,
    ) -> dict[str, Any]:
        return intrigue_recruitment._generate_intrigue_recruitment_session(
            self._dependencies.intrigue.recruitment, game, faction_id, filters, rng
        )

    def intrigue_recruitment_action(
        self,
        game_id: str,
        action: str,
        filters: dict[str, Any] | None = None,
        candidate_ids: list[str] | None = None,
        player_vote: bool = True,
    ) -> dict[str, Any]:
        return intrigue_recruitment.intrigue_recruitment_action(
            self._dependencies.intrigue.recruitment,
            game_id,
            action,
            filters,
            candidate_ids,
            player_vote,
        )

    def _intrigue_vote_chance(
        self,
        game: GameState,
        npc: SectNpc,
        resolution_type: str,
        kind: str,
        faction_id: str,
        target_id: str,
        proposer_id: str,
    ) -> tuple[float, list[str]]:
        return intrigue_resolutions._intrigue_vote_chance(
            self._dependencies.intrigue.resolutions,
            game,
            npc,
            resolution_type,
            kind,
            faction_id,
            target_id,
            proposer_id,
        )

    def _intrigue_resolve(
        self,
        game: GameState,
        kind: str,
        faction_id: str,
        resolution_type: str,
        target_id: str,
        player_vote: bool | None,
        proposer_id: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return intrigue_resolutions._intrigue_resolve(
            self._dependencies.intrigue.resolutions,
            game,
            kind,
            faction_id,
            resolution_type,
            target_id,
            player_vote,
            proposer_id,
            rng,
            context,
        )

    def _intrigue_apply_resolution(
        self,
        game: GameState,
        record: dict[str, Any],
        resolution_type: str,
        target_id: str,
        rng: random.Random,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        return intrigue_resolutions._intrigue_apply_resolution(
            self._dependencies.intrigue.resolutions,
            game,
            record,
            resolution_type,
            target_id,
            rng,
            context=context,
        )

    def intrigue_propose_resolution(
        self,
        game_id: str,
        kind: str,
        resolution_type: str,
        target_id: str = "",
        player_vote: bool = True,
    ) -> dict[str, Any]:
        return intrigue_resolutions.intrigue_propose_resolution(
            self._dependencies.intrigue.resolutions,
            game_id,
            kind,
            resolution_type,
            target_id,
            player_vote,
        )

    def _intrigue_record_player_prison(
        self, game: GameState, key: str, years: int
    ) -> None:
        return intrigue_runtime._intrigue_record_player_prison(
            self._dependencies.intrigue.runtime, game, key, years
        )

    def _intrigue_sync_player_prison(self, game: GameState) -> None:
        return intrigue_runtime._intrigue_sync_player_prison(
            self._dependencies.intrigue.runtime, game
        )

    def _advance_intrigue_unit(self, game: GameState, rng: random.Random) -> list[str]:
        return intrigue_runtime._advance_intrigue_unit(
            self._dependencies.intrigue.runtime, game, rng
        )

    def _intrigue_entity(
        self, game: GameState, kind: str, faction_id: str
    ) -> SectState | None:
        return intrigue_state._intrigue_entity(
            self._dependencies.intrigue.state, game, kind, faction_id
        )

    def _intrigue_find_npc(self, game: GameState, npc_id: str) -> SectNpc | None:
        return intrigue_state._intrigue_find_npc(
            self._dependencies.intrigue.state, game, npc_id
        )

    def _intrigue_members(
        self, game: GameState, kind: str, faction_id: str
    ) -> list[SectNpc]:
        return intrigue_state._intrigue_members(
            self._dependencies.intrigue.state, game, kind, faction_id
        )

    def _intrigue_player_faction_id(self, game: GameState, kind: str) -> str | None:
        return intrigue_state._intrigue_player_faction_id(
            self._dependencies.intrigue.state, game, kind
        )

    def _ensure_intrigue_personality(
        self, game: GameState, npc: SectNpc
    ) -> dict[str, Any]:
        return intrigue_state._ensure_intrigue_personality(
            self._dependencies.intrigue.state, game, npc
        )

    def _intrigue_governance_style(self, game: GameState, npc: SectNpc) -> str:
        return intrigue_state._intrigue_governance_style(
            self._dependencies.intrigue.state, game, npc
        )

    def _ensure_intrigue_faction(
        self, game: GameState, kind: str, faction_id: str
    ) -> dict[str, Any]:
        return intrigue_state._ensure_intrigue_faction(
            self._dependencies.intrigue.state, game, kind, faction_id
        )


    def _exchange_location(self, world):
        return economy_exchange._exchange_location(self._dependencies.exchange, world)

    def _schedule_exchange(self, game, rng):
        return economy_exchange._schedule_exchange(self._dependencies.exchange, game, rng)

    def _open_exchange(self, game, rng):
        return economy_exchange._open_exchange(self._dependencies.exchange, game, rng)

    def _advance_exchange_clock(self, game, rng):
        return economy_exchange._advance_exchange_clock(self._dependencies.exchange, game, rng)

    def _exchange_materials(self, game):
        return economy_exchange._exchange_materials(self._dependencies.exchange, game)

    def exchange_action(self, game_id: str, action: str, payload: dict[str, Any]):
        return economy_exchange.exchange_action(self._dependencies.exchange, game_id, action, payload)

    def _public_exchange(self, game):
        return economy_exchange._public_exchange(self._dependencies.exchange, game)

    @property
    def _exchange_dependencies(self):
        return self._dependencies.exchange

    def _append_crafting_market_offers(
        self, game: GameState, rng: random.Random, offers: list[dict[str, Any]], *,
        tier: int, market_name: str, location_id: str,
    ) -> None:
        # New crafting stock must not move the story/combat RNG stream.  Its
        # condition remains deterministic for the same save, place and year.
        return crafting_market._append_crafting_market_offers(self._dependencies.crafting.market, game, rng, offers, tier=tier, market_name=market_name, location_id=location_id)

    def _buy_crafting_material_offer(self, game: GameState, offer: dict[str, Any], price: int) -> str:
        return crafting_market._buy_crafting_material_offer(self._dependencies.crafting.market, game, offer, price)

    def _crafting_material_candidates(self, player: Player) -> list[dict[str, Any]]:
        return crafting_materials._crafting_material_candidates(self._dependencies.crafting.materials, player)

    def _resolve_crafting_selection(self, player: Player, payload: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
        return crafting_materials._resolve_crafting_selection(self._dependencies.crafting.materials, player, payload)

    def _crafting_preview(self, player: Player, payload: dict[str, Any]) -> dict[str, Any]:
        return crafting_preview._crafting_preview(self._dependencies.crafting.preview, player, payload)

    def preview_crafting(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return crafting_preview.preview_crafting(self._dependencies.crafting.preview, game_id, payload)

    def forge_crafted_artifact(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return crafting_forging.forge_crafted_artifact(self._dependencies.crafting.forging, game_id, payload)

    def save_crafting_blueprint(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return crafting_forging.save_crafting_blueprint(self._dependencies.crafting.forging, game_id, payload)

    def crafted_artifact_action(self, game_id: str, artifact_id: str, action: str, start_price: int = 0) -> dict[str, Any]:
        return crafting_artifacts.crafted_artifact_action(self._dependencies.crafting.artifacts, game_id, artifact_id, action, start_price)

    def _consign_crafted_artifact(self, game: GameState, artifact: dict[str, Any], start_price: int) -> None:
        return crafting_artifacts._consign_crafted_artifact(self._dependencies.crafting.artifacts, game, artifact, start_price)

    def _make_crafted_auction_lot(self, game: GameState, rng: random.Random, consignment: dict[str, Any], suffix: str) -> dict[str, Any]:
        return crafting_artifacts._make_crafted_auction_lot(self._dependencies.crafting.artifacts, game, rng, consignment, suffix)

    def _public_crafting_system(self, game: GameState) -> dict[str, Any]:
        return crafting_presentation._public_crafting_system(self._dependencies.crafting.presentation, game)

    @staticmethod
    def _crafting_rules() -> dict[str, Any]:
        return crafting_compat._crafting_rules()

    @staticmethod
    def _crafting_molds() -> dict[str, dict[str, Any]]:
        return crafting_compat._crafting_molds()

    @staticmethod
    def _crafting_material_defs() -> dict[str, dict[str, Any]]:
        return crafting_compat._crafting_material_defs()

    @staticmethod
    def _crafting_plant_defs() -> dict[str, dict[str, Any]]:
        return crafting_compat._crafting_plant_defs()

    @staticmethod
    def _quality_probabilities(refining_level: int, average_quality: float) -> dict[str, float]:
        return crafting_compat._quality_probabilities(refining_level, average_quality)

    @staticmethod
    def _weighted_choice(rng: random.Random, probabilities: dict[str, float]) -> str:
        return crafting_compat._weighted_choice(rng, probabilities)

    @staticmethod
    def _resolve_mold_rule(
        player: Player, mold: dict[str, Any], selected: list[tuple[str, dict[str, Any]]],
    ) -> dict[str, Any]:
        return crafting_compat._resolve_mold_rule(player, mold, selected)

    @property
    def _crafting_dependencies(self):
        return self._dependencies.crafting

    def _append_formation_market_offers(
        self, game: GameState, rng: random.Random, offers: list[dict[str, Any]], *,
        tier: int, market_name: str, location_id: str,
    ) -> None:
        return formation_market._append_formation_market_offers(self._dependencies.formation.market, game, rng, offers, tier=tier, market_name=market_name, location_id=location_id)

    def _buy_formation_material_offer(self, game: GameState, offer: dict[str, Any], price: int) -> str:
        return formation_market._buy_formation_material_offer(self._dependencies.formation.market, game, offer, price)

    def _buy_formation_supply_offer(self, game: GameState, offer: dict[str, Any], price: int) -> str:
        return formation_market._buy_formation_supply_offer(self._dependencies.formation.market, game, offer, price)

    def _formation_candidates(
        self, player: Player, *, include_active: bool = True, include_ground: bool = True,
    ) -> list[dict[str, Any]]:
        return formation_loadouts._formation_candidates(self._dependencies.formation.loadouts, player, include_active=include_active, include_ground=include_ground)

    def _nodes_from_candidate_ids(self, player: Player, slot_ids: list[Any]) -> tuple[list[dict[str, Any] | None], list[str | None]]:
        return formation_loadouts._nodes_from_candidate_ids(self._dependencies.formation.loadouts, player, slot_ids)

    def preview_formation(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return formation_loadouts.preview_formation(self._dependencies.formation.loadouts, game_id, payload)

    def save_formation(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return formation_loadouts.save_formation(self._dependencies.formation.loadouts, game_id, payload)

    def activate_formation(self, game_id: str, loadout_id: str) -> dict[str, Any]:
        return formation_loadouts.activate_formation(self._dependencies.formation.loadouts, game_id, loadout_id)

    def deactivate_formation(self, game_id: str) -> dict[str, Any]:
        return formation_loadouts.deactivate_formation(self._dependencies.formation.loadouts, game_id)

    def delete_formation(self, game_id: str, loadout_id: str) -> dict[str, Any]:
        return formation_loadouts.delete_formation(self._dependencies.formation.loadouts, game_id, loadout_id)

    def _activate_loadout(self, player: Player, loadout: dict[str, Any]) -> None:
        # First build a virtual pool containing the currently occupied material.
        # This makes switching presets atomic and permits reusing the same rare
        # instance without ever cloning it.
        return formation_loadouts._activate_loadout(self._dependencies.formation.loadouts, player, loadout)

    def _ground_array_public(self, player: Player, array: dict[str, Any]) -> dict[str, Any]:
        return formation_ground._ground_array_public(self._dependencies.formation.ground, player, array)

    def deploy_ground_formation(self, game_id: str, owner_kind: str = "player") -> dict[str, Any]:
        return formation_ground.deploy_ground_formation(self._dependencies.formation.ground, game_id, owner_kind)

    def _require_ground_array_access(self, game: GameState, ground_id: str) -> dict[str, Any]:
        return formation_ground._require_ground_array_access(self._dependencies.formation.ground, game, ground_id)

    def withdraw_ground_formation(self, game_id: str, ground_id: str) -> dict[str, Any]:
        return formation_ground.withdraw_ground_formation(self._dependencies.formation.ground, game_id, ground_id)

    def repair_ground_formation(self, game_id: str, ground_id: str, supply_id: str, quantity: int = 1) -> dict[str, Any]:
        return formation_ground.repair_ground_formation(self._dependencies.formation.ground, game_id, ground_id, supply_id, quantity)

    def _local_ground_formation(self, game: GameState) -> dict[str, Any] | None:
        return formation_ground._local_ground_formation(self._dependencies.formation.ground, game)

    def _sect_guard_array(self, game: GameState, sect_id: str) -> dict[str, Any] | None:
        return formation_ground._sect_guard_array(self._dependencies.formation.ground, game, sect_id)

    def _sect_guard_power(self, game: GameState, sect_id: str) -> float:
        return formation_ground._sect_guard_power(self._dependencies.formation.ground, game, sect_id)

    def _wear_war_guard_arrays(self, game: GameState, war: dict[str, Any], amount: float | None = None) -> None:
        return formation_ground._wear_war_guard_arrays(self._dependencies.formation.ground, game, war, amount)

    def _npc_formation_profile(
        self, game: GameState, npc_id: str, *, detailed_spectrum: bool = False,
    ) -> dict[str, Any]:
        return formation_npcs._npc_formation_profile(self._dependencies.formation.npcs, game, npc_id, detailed_spectrum=detailed_spectrum)

    def _npc_formation_power_multiplier(self, game: GameState, npc_id: str) -> float:
        return formation_npcs._npc_formation_power_multiplier(self._dependencies.formation.npcs, game, npc_id)

    def _ensure_npc_formations(self, game: GameState) -> bool:
        return formation_npcs._ensure_npc_formations(self._dependencies.formation.npcs, game)

    def _public_formation_system(self, game: GameState) -> dict[str, Any]:
        return formation_presentation._public_formation_system(self._dependencies.formation.presentation, game)

    @staticmethod
    def _formation_rules() -> dict[str, Any]:
        return formation_compat._formation_rules()

    @staticmethod
    def _formation_material_defs() -> dict[str, dict[str, Any]]:
        return formation_compat._formation_material_defs()

    @staticmethod
    def _formation_maintenance_defs() -> dict[str, dict[str, Any]]:
        return formation_compat._formation_maintenance_defs()

    @staticmethod
    def _formation_candidate(source: dict[str, Any], definition: dict[str, Any], source_kind: str, candidate_id: str) -> dict[str, Any]:
        return formation_compat._formation_candidate(source, definition, source_kind, candidate_id)

    @staticmethod
    def _extract_candidate(player: Player, candidate: dict[str, Any]) -> dict[str, Any]:
        return formation_compat._extract_candidate(player, candidate)

    @staticmethod
    def _release_active_formation(player: Player) -> None:
        return formation_compat._release_active_formation(player)

    @staticmethod
    def _release_bindings(player: Player, bindings: list[dict[str, Any] | None]) -> None:
        return formation_compat._release_bindings(player, bindings)

    @staticmethod
    def _ground_profile(player: Player, array: dict[str, Any]) -> dict[str, Any]:
        return formation_compat._ground_profile(player, array)

    @property
    def _formation_dependencies(self):
        return self._dependencies.formation

    def _cancel_auction_for_world_change(self, game: GameState) -> None:
        return economy_auctions._cancel_auction_for_world_change(self._dependencies.economy.auctions, game)

    def search_black_market(self, game_id: str, pattern: str) -> dict[str, Any]:
        return economy_black_market.search_black_market(self._dependencies.economy.black_market, game_id, pattern)

    @staticmethod
    def _alchemy_targets(player: Player) -> dict[str, dict[str, Any]]:
        return economy_compat._alchemy_targets(player)

    @staticmethod
    def _art_names() -> dict[str, str]:
        return economy_compat._art_names()

    def _grant_art_experience(self, player: Player, art_id: str, amount: float) -> None:
        return economy_arts._grant_art_experience(self._dependencies.economy.arts, player, art_id, amount)

    def _public_art_skills(self, player: Player) -> list[dict[str, Any]]:
        return economy_arts._public_art_skills(self._dependencies.economy.arts, player)

    def refine_pill(self, game_id: str, target_item_id: str, materials: list[dict[str, Any]]) -> dict[str, Any]:
        return economy_arts.refine_pill(self._dependencies.economy.arts, game_id, target_item_id, materials)

    @staticmethod
    def _auction_rules() -> dict[str, Any]:
        return economy_compat._auction_rules()

    @staticmethod
    def _auction_rng(game: GameState, purpose: str) -> random.Random:
        return economy_compat._auction_rng(game, purpose)

    @staticmethod
    def _auction_content(kind: str, content_id: str) -> tuple[str, str]:
        return economy_compat._auction_content(kind, content_id)

    def _auction_location_matches(self, game: GameState) -> bool:
        return economy_auctions._auction_location_matches(self._dependencies.economy.auctions, game)

    def _require_auction_access(self, game: GameState, statuses: set[str]) -> dict[str, Any]:
        return economy_auctions._require_auction_access(self._dependencies.economy.auctions, game, statuses)

    def _schedule_auction(self, game: GameState, rng: Any) -> None:
        return economy_auctions._schedule_auction(self._dependencies.economy.auctions, game, rng)

    def _auction_goods_pool(self, world: str) -> list[dict[str, Any]]:
        return economy_auctions._auction_goods_pool(self._dependencies.economy.auctions, world)

    def _auction_good_weight(self, world: str, tier: int) -> float:
        return economy_auctions._auction_good_weight(self._dependencies.economy.auctions, world, tier)

    def _make_auction_lot(self, game: GameState, rng: Any, *, kind: str, content_id: str, tier: int, start_price: int, seller: str='npc', suffix: str, rated_price: int | None=None) -> dict[str, Any]:
        return economy_auctions._make_auction_lot(self._dependencies.economy.auctions, game, rng, kind=kind, content_id=content_id, tier=tier, start_price=start_price, seller=seller, suffix=suffix, rated_price=rated_price)

    def _open_auction(self, game: GameState, rng: Any) -> None:
        return economy_auctions._open_auction(self._dependencies.economy.auctions, game, rng)

    def _advance_auction_clock(self, game: GameState, rng: Any) -> None:
        return economy_auctions._advance_auction_clock(self._dependencies.economy.auctions, game, rng)

    def _auction_increment(self, lot: dict[str, Any]) -> int:
        return economy_auctions._auction_increment(self._dependencies.economy.auctions, lot)

    def _auction_bid_ceiling(self, lot: dict[str, Any]) -> int:
        return economy_auctions._auction_bid_ceiling(self._dependencies.economy.auctions, lot)

    def consign_auction_item(self, game_id: str, item_id: str, start_price: int=0) -> dict[str, Any]:
        return economy_auctions.consign_auction_item(self._dependencies.economy.auctions, game_id, item_id, start_price)

    def place_auction_bid(self, game_id: str, lot_id: str) -> dict[str, Any]:
        return economy_auctions.place_auction_bid(self._dependencies.economy.auctions, game_id, lot_id)

    def advance_auction_round(self, game_id: str) -> dict[str, Any]:
        return economy_auctions.advance_auction_round(self._dependencies.economy.auctions, game_id)

    def _grant_auction_content(self, player: Player, kind: str, content_id: str) -> None:
        return economy_auctions._grant_auction_content(self._dependencies.economy.auctions, player, kind, content_id)

    def _finish_auction(self, game: GameState, rng: Any, reason: str='') -> None:
        return economy_auctions._finish_auction(self._dependencies.economy.auctions, game, rng, reason)

    def negotiate_at_auction(self, game_id: str, npc_id: str) -> dict[str, Any]:
        return economy_auctions.negotiate_at_auction(self._dependencies.economy.auctions, game_id, npc_id)

    def choose_auction_identity(self, game_id: str, alias: str) -> dict[str, Any]:
        return economy_auctions.choose_auction_identity(self._dependencies.economy.auctions, game_id, alias)

    def _public_auction(self, game: GameState) -> dict[str, Any]:
        return economy_auctions._public_auction(self._dependencies.economy.auctions, game)

    def buy_black_market_item(self, game_id: str, result_id: str, quantity: int=1) -> dict[str, Any]:
        return economy_black_market.buy_black_market_item(self._dependencies.economy.black_market, game_id, result_id, quantity)

    def sell_black_market_asset(self, game_id: str, kind: str, asset_id: str) -> dict[str, Any]:
        return economy_black_market.sell_black_market_asset(self._dependencies.economy.black_market, game_id, kind, asset_id)

    def leave_black_market(self, game_id: str) -> dict[str, Any]:
        return economy_black_market.leave_black_market(self._dependencies.economy.black_market, game_id)

    @staticmethod
    def _market_tier(player: Player) -> int:
        return economy_compat._market_tier(player)

    @staticmethod
    def _clear_market(game: GameState) -> None:
        return economy_compat._clear_market(game)

    @staticmethod
    def _market_offer_group(offer: dict[str, Any]) -> str:
        return economy_compat._market_offer_group(offer)

    def _ensure_market(self, game: GameState, rng: Any) -> bool:
        return economy_market._ensure_market(self._dependencies.economy.market, game, rng)

    def _refresh_world_market(self, game: GameState, rng: Any) -> bool:
        return economy_market._refresh_world_market(self._dependencies.economy.market, game, rng)

    def _public_market(self, game: GameState) -> dict[str, Any]:
        return economy_market._public_market(self._dependencies.economy.market, game)

    def toggle_market_offer_lock(self, game_id: str, offer_id: str) -> dict[str, Any]:
        return economy_market.toggle_market_offer_lock(self._dependencies.economy.market, game_id, offer_id)

    @staticmethod
    def _spirit_stones(player: Player) -> int:
        return economy_compat._spirit_stones(player)

    @staticmethod
    def _catalog_price(kind: str, content_id: str) -> int:
        return economy_compat._catalog_price(kind, content_id)

    def _is_world_market_good(self, world: str, kind: str, content_id: str) -> bool:
        return economy_market._is_world_market_good(self._dependencies.economy.market, world, kind, content_id)

    def _private_trade_attendee(self, game: GameState, npc_id: str) -> dict[str, Any]:
        return economy_private_trade._private_trade_attendee(self._dependencies.economy.private_trade, game, npc_id)

    def buy_private_trade_item(self, game_id: str, npc_id: str, offer_id: str) -> dict[str, Any]:
        return economy_private_trade.buy_private_trade_item(self._dependencies.economy.private_trade, game_id, npc_id, offer_id)

    def sell_private_trade_item(self, game_id: str, npc_id: str, item_id: str) -> dict[str, Any]:
        return economy_private_trade.sell_private_trade_item(self._dependencies.economy.private_trade, game_id, npc_id, item_id)

    def bargain_private_trade(self, game_id: str, npc_id: str, side: str, asset_id: str) -> dict[str, Any]:
        return economy_private_trade.bargain_private_trade(self._dependencies.economy.private_trade, game_id, npc_id, side, asset_id)

    @staticmethod
    def _spirit_field_rules() -> dict[str, Any]:
        return economy_compat._spirit_field_rules()

    @staticmethod
    def _rounded_plant_years(years: float) -> int:
        return economy_compat._rounded_plant_years(years)

    @staticmethod
    def _plant_quality(years: int, optimal_years: int) -> float:
        return economy_compat._plant_quality(years, optimal_years)

    def _plant_item_value(self, item_or_id: Item | str) -> int | None:
        return economy_spirit_fields._plant_item_value(self._dependencies.economy.spirit_fields, item_or_id)

    def _add_harvested_plant(self, player: Player, plant_id: str, actual_years: float) -> Item:
        return economy_spirit_fields._add_harvested_plant(self._dependencies.economy.spirit_fields, player, plant_id, actual_years)

    def _annual_spirit_field_update(self, player: Player) -> None:
        return economy_spirit_fields._annual_spirit_field_update(self._dependencies.economy.spirit_fields, player)

    def _public_spirit_field(self, player: Player) -> dict[str, Any]:
        return economy_spirit_fields._public_spirit_field(self._dependencies.economy.spirit_fields, player)

    def reclaim_spirit_field(self, game_id: str) -> dict[str, Any]:
        return economy_spirit_fields.reclaim_spirit_field(self._dependencies.economy.spirit_fields, game_id)

    def plant_spirit_crop(self, game_id: str, plant_id: str, slot: int | None=None) -> dict[str, Any]:
        return economy_spirit_fields.plant_spirit_crop(self._dependencies.economy.spirit_fields, game_id, plant_id, slot)

    def irrigate_spirit_crop(self, game_id: str, plot_id: str, mp_amount: float=0, booster_id: str='') -> dict[str, Any]:
        return economy_spirit_fields.irrigate_spirit_crop(self._dependencies.economy.spirit_fields, game_id, plot_id, mp_amount, booster_id)

    def harvest_spirit_crop(self, game_id: str, plot_id: str) -> dict[str, Any]:
        return economy_spirit_fields.harvest_spirit_crop(self._dependencies.economy.spirit_fields, game_id, plot_id)

    def use_harvested_plant(self, game_id: str, item_id: str) -> dict[str, Any]:
        return economy_spirit_fields.use_harvested_plant(self._dependencies.economy.spirit_fields, game_id, item_id)

    def sell_spirit_plant(self, game_id: str, item_id: str, *, black_market: bool=False) -> dict[str, Any]:
        return economy_spirit_fields.sell_spirit_plant(self._dependencies.economy.spirit_fields, game_id, item_id, black_market=black_market)

    def _treasure_reward_pool(self, game: GameState, category: str) -> list[dict[str, Any]]:
        return economy_treasure._treasure_reward_pool(self._dependencies.economy.treasure, game, category)

    def _treasure_step(self, game: GameState, rng: Any) -> str:
        return economy_treasure._treasure_step(self._dependencies.economy.treasure, game, rng)

    def _prepare_treasure_reward_event(self, game: GameState, rng: Any) -> dict[str, Any]:
        return economy_treasure._prepare_treasure_reward_event(self._dependencies.economy.treasure, game, rng)

    def _claim_treasure_reward(self, game: GameState, pending: dict[str, Any], category: str) -> tuple[str, str]:
        return economy_treasure._claim_treasure_reward(self._dependencies.economy.treasure, game, pending, category)

    @property
    def _economy_dependencies(self):
        return self._dependencies.economy


    def _ensure_guixu_state(self, game: GameState) -> bool:
        return guixu_state._ensure_guixu_state(self._dependencies.guixu.state, game)

    def _guixu_entry_definition(
        self, dungeon: dict[str, Any], pool_entry_id: str,
    ) -> dict[str, Any]:
        return guixu_state._guixu_entry_definition(self._dependencies.guixu.state, dungeon, pool_entry_id)

    def _guixu_cycle_and_definition(
        self, game: GameState, dungeon_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return guixu_state._guixu_cycle_and_definition(self._dependencies.guixu.state, game, dungeon_id)

    def _enforce_guixu_rank_boundary(self, game: GameState, reason: str) -> str:
        return guixu_state._enforce_guixu_rank_boundary(self._dependencies.guixu.state, game, reason)

    def assert_guixu_operation_allowed(self, game_id: str, operation: str) -> None:
        # When the DLC is disabled, let the requested operation reach ``_load``;
        # its compatibility migration safely returns an active explorer first.
        return guixu_state.assert_guixu_operation_allowed(self._dependencies.guixu.state, game_id, operation)

    def _announce_guixu_cycle(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any], rng: random.Random,
    ) -> None:
        return guixu_calendar._announce_guixu_cycle(self._dependencies.guixu.calendar, game, dungeon, cycle, rng)

    def _open_guixu_cycle(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any], rng: random.Random,
    ) -> None:
        return guixu_calendar._open_guixu_cycle(self._dependencies.guixu.calendar, game, dungeon, cycle, rng)

    def _close_guixu_cycle(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any], rng: random.Random,
    ) -> None:
        return guixu_calendar._close_guixu_cycle(self._dependencies.guixu.calendar, game, dungeon, cycle, rng)

    def _advance_guixu_calendar(
        self, game: GameState, rng: random.Random, era_news: list[str],
    ) -> bool:
        return guixu_calendar._advance_guixu_calendar(self._dependencies.guixu.calendar, game, rng, era_news)

    def _guixu_elapsed_days(
        self, dungeon: dict[str, Any], session: dict[str, Any],
    ) -> int:
        return guixu_calendar._guixu_elapsed_days(self._dependencies.guixu.calendar, dungeon, session)

    def _consume_guixu_days(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        session: dict[str, Any], days: int, rng: random.Random,
    ) -> None:
        return guixu_calendar._consume_guixu_days(self._dependencies.guixu.calendar, game, dungeon, cycle, session, days, rng)

    def _guixu_relation_ids(self, game: GameState) -> set[str]:
        return guixu_npcs._guixu_relation_ids(self._dependencies.guixu.npcs, game)

    def _generate_guixu_roster(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any], rng: random.Random,
    ) -> list[dict[str, Any]]:
        return guixu_npcs._generate_guixu_roster(self._dependencies.guixu.npcs, game, dungeon, cycle, rng)

    def _form_guixu_npc_teams(
        self, cycle: dict[str, Any], rng: random.Random,
    ) -> None:
        return guixu_npcs._form_guixu_npc_teams(self._dependencies.guixu.npcs, cycle, rng)

    def _dissolve_guixu_npc_team(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        team_id: str | None, reason: str,
    ) -> None:
        return guixu_npcs._dissolve_guixu_npc_team(self._dependencies.guixu.npcs, game, dungeon, cycle, team_id, reason)

    def _guixu_npc_claim_entry(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        row: dict[str, Any], actor: dict[str, Any], source: str,
    ) -> None:
        return guixu_npcs._guixu_npc_claim_entry(self._dependencies.guixu.npcs, game, dungeon, cycle, row, actor, source)

    def _assign_due_guixu_entries(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        elapsed_days: int, rng: random.Random,
    ) -> None:
        return guixu_npcs._assign_due_guixu_entries(self._dependencies.guixu.npcs, game, dungeon, cycle, elapsed_days, rng)

    def _simulate_guixu_npc_conflict(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        day: int, rng: random.Random,
    ) -> None:
        return guixu_npcs._simulate_guixu_npc_conflict(self._dependencies.guixu.npcs, game, dungeon, cycle, day, rng)

    def _resolve_guixu_npc_kill(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        killer: dict[str, Any], victim: dict[str, Any], day: int,
    ) -> None:
        return guixu_npcs._resolve_guixu_npc_kill(self._dependencies.guixu.npcs, game, dungeon, cycle, killer, victim, day)

    def _guixu_grant_entry(
        self, game: GameState, dungeon: dict[str, Any], row: dict[str, Any], source: str,
    ) -> str:
        return guixu_rewards._guixu_grant_entry(self._dependencies.guixu.rewards, game, dungeon, row, source)

    def _guixu_transferable_player_entries(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        session: dict[str, Any],
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        return guixu_rewards._guixu_transferable_player_entries(self._dependencies.guixu.rewards, game, dungeon, cycle, session)

    def _surrender_guixu_treasure(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        session: dict[str, Any], threat: dict[str, Any], actor: dict[str, Any],
    ) -> str:
        return guixu_rewards._surrender_guixu_treasure(self._dependencies.guixu.rewards, game, dungeon, cycle, session, threat, actor)

    def _maybe_guixu_npc_threat(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        session: dict[str, Any], rng: random.Random,
    ) -> None:
        return guixu_encounters._maybe_guixu_npc_threat(self._dependencies.guixu.encounters, game, dungeon, cycle, session, rng)

    def _guixu_actor(self, cycle: dict[str, Any], actor_id: str) -> dict[str, Any]:
        return guixu_encounters._guixu_actor(self._dependencies.guixu.encounters, cycle, actor_id)

    def _guixu_relationship_role(self, game: GameState, npc_id: str) -> str | None:
        return guixu_encounters._guixu_relationship_role(self._dependencies.guixu.encounters, game, npc_id)

    def _break_guixu_relationship(self, game: GameState, npc_id: str, *, player_defending: bool = False) -> None:
        return guixu_encounters._break_guixu_relationship(self._dependencies.guixu.encounters, game, npc_id, player_defending=player_defending)

    def _guixu_fight(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        session: dict[str, Any], actor: dict[str, Any], rng: random.Random,
        *, player_defending: bool = False, enemy_first_round: bool = False,
    ) -> tuple[str, str]:
        return guixu_encounters._guixu_fight(self._dependencies.guixu.encounters, game, dungeon, cycle, session, actor, rng, player_defending=player_defending, enemy_first_round=enemy_first_round)

    def _guixu_offer_team(self, game, cycle, session):
        return guixu_encounters._guixu_offer_team(self._dependencies.guixu.encounters, game, cycle, session)

    def _guixu_team_tick(self, game, dungeon, cycle, session, rng):
        return guixu_encounters._guixu_team_tick(self._dependencies.guixu.encounters, game, dungeon, cycle, session, rng)

    def guixu_action(self, game_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        return guixu_actions.guixu_action(self._dependencies.guixu.actions, game_id, action, payload)

    def _guixu_trapped_training(
        self, game_id: str, action: str, units: int = 1,
    ) -> dict[str, Any]:
        return guixu_actions._guixu_trapped_training(self._dependencies.guixu.actions, game_id, action, units)

    def _public_guixu(self, game: GameState) -> dict[str, Any]:
        return guixu_presentation._public_guixu(self._dependencies.guixu.presentation, game)

    @staticmethod
    def _guixu_definitions() -> dict[str, dict[str, Any]]:
        return guixu_compat._guixu_definitions()

    @staticmethod
    def _guixu_settings() -> dict[str, Any]:
        return guixu_compat._guixu_settings()

    @staticmethod
    def _next_guixu_open(definition: dict[str, Any], age: int) -> int:
        return guixu_compat._next_guixu_open(definition, age)

    @staticmethod
    def _guixu_weighted_key(weights: dict[str, Any], rng: random.Random) -> str:
        return guixu_compat._guixu_weighted_key(weights, rng)

    @staticmethod
    def _guixu_return_days(layer_id: str) -> int:
        return guixu_compat._guixu_return_days(layer_id)

    @staticmethod
    def _guixu_active_team(cycle, actor):
        return guixu_compat._guixu_active_team(cycle, actor)

    @property
    def _guixu_dependencies(self):
        return self._dependencies.guixu

    def _war_player_identity(self, game, war):
        return war_state._war_player_identity(self._dependencies.war.state, game, war)

    def _war_relation(self, game: GameState, kind: str, first: str, second: str) -> dict[str, Any]:
        return war_state._war_relation(self._dependencies.war.state, game, kind, first, second)

    def _active_war(self, game: GameState, kind: str, first: str, second: str) -> dict[str, Any] | None:
        return war_state._active_war(self._dependencies.war.state, game, kind, first, second)

    def _war_world(self, game: GameState, kind: str, side_id: str) -> str:
        return war_state._war_world(self._dependencies.war.state, game, kind, side_id)

    def _war_side_name(self, game: GameState, kind: str, side_id: str) -> str:
        return war_state._war_side_name(self._dependencies.war.state, game, kind, side_id)

    def _war_side_members(self, game: GameState, kind: str, side_id: str, world: str) -> list[SectNpc]:
        return war_state._war_side_members(self._dependencies.war.state, game, kind, side_id, world)

    def _ensure_war_shape(self, game: GameState, war: dict[str, Any]) -> bool:
        return war_state._ensure_war_shape(self._dependencies.war.state, game, war)

    def _coalition_ids(self, war: dict[str, Any], side: str) -> list[str]:
        return war_state._coalition_ids(self._dependencies.war.state, war, side)

    def _participant_side(self, war: dict[str, Any], power_id: str | None) -> str | None:
        return war_state._participant_side(self._dependencies.war.state, war, power_id)

    def _power_exists_in_world(self, game: GameState, kind: str, power_id: str, world: str) -> bool:
        return war_state._power_exists_in_world(self._dependencies.war.state, game, kind, power_id, world)

    def _append_war_log(self, game: GameState, war: dict[str, Any], title: str, text: str) -> None:
        return war_state._append_war_log(self._dependencies.war.state, game, war, title, text)

    def _war_npc(self, game: GameState, npc_id: str) -> SectNpc | None:
        return war_state._war_npc(self._dependencies.war.state, game, npc_id)

    def _available_warriors(self, game: GameState, war: dict[str, Any], side: str, power_id: str = "") -> list[SectNpc]:
        return war_state._available_warriors(self._dependencies.war.state, game, war, side, power_id)

    def _ensure_wars(self, game: GameState) -> bool:
        return war_state._ensure_wars(self._dependencies.war.state, game)

    def _allied_powers(self, game: GameState, war: dict[str, Any], side: str) -> list[dict[str, Any]]:
        return war_diplomacy._allied_powers(self._dependencies.war.diplomacy, game, war, side)

    def _add_war_participant(self, game: GameState, war: dict[str, Any], side: str, power_id: str, caller_id: str) -> None:
        return war_diplomacy._add_war_participant(self._dependencies.war.diplomacy, game, war, side, power_id, caller_id)

    def _call_war_allies(self, game: GameState, war: dict[str, Any], side: str, rng: random.Random,
                         *, ally_id: str = "", limit: int | None = None) -> list[str]:
        return war_diplomacy._call_war_allies(self._dependencies.war.diplomacy, game, war, side, rng, ally_id=ally_id, limit=limit)

    def _player_war_side(self, game: GameState, war: dict[str, Any]) -> str | None:
        return war_diplomacy._player_war_side(self._dependencies.war.diplomacy, game, war)

    def _player_has_war_voice(self, game: GameState, war: dict[str, Any]) -> bool:
        return war_diplomacy._player_has_war_voice(self._dependencies.war.diplomacy, game, war)

    def _start_war(self, game: GameState, kind: str, attacker: str, defender: str) -> dict[str, Any]:
        return war_diplomacy._start_war(self._dependencies.war.diplomacy, game, kind, attacker, defender)

    def _war_total_power(
        self, game: GameState, war: dict[str, Any], side: str, *, include_player: bool = True,
    ) -> float:
        return war_power._war_total_power(self._dependencies.war.power, game, war, side, include_player=include_player)

    def _war_side_formation(self, game: GameState, war: dict[str, Any], side: str) -> dict[str, Any]:
        return war_power._war_side_formation(self._dependencies.war.power, game, war, side)

    def _war_formation_modifier(
        self, own: dict[str, Any], opponent: dict[str, Any], side: str,
    ) -> float:
        return war_power._war_formation_modifier(self._dependencies.war.power, own, opponent, side)

    def _war_formation_contexts(self, game: GameState, war: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return war_power._war_formation_contexts(self._dependencies.war.power, game, war)

    def _war_power_profile(
        self, game: GameState, war: dict[str, Any], side: str, *, include_player: bool = True,
    ) -> dict[str, float | int]:
        return war_power._war_power_profile(self._dependencies.war.power, game, war, side, include_player=include_player)

    def _war_entity_power(self, game: GameState, war: dict[str, Any], side: str, power_id: str) -> float:
        return war_power._war_entity_power(self._dependencies.war.power, game, war, side, power_id)

    def _resolve_abstract_defeat(self, game: GameState, war: dict[str, Any], loser: str, rng: random.Random) -> str:
        return war_combat._resolve_abstract_defeat(self._dependencies.war.combat, game, war, loser, rng)

    def _shift_war_morale(self, war: dict[str, Any], loser: str, loss: float, gain: float, *, attacker_kill: bool = False) -> None:
        return war_combat._shift_war_morale(self._dependencies.war.combat, war, loser, loss, gain, attacker_kill=attacker_kill)

    def _resolve_field_attack(
        self, game: GameState, war: dict[str, Any], attacking: str, rng: random.Random,
        formation_contexts: dict[str, dict[str, Any]] | None = None,
    ) -> str:
        return war_combat._resolve_field_attack(self._dependencies.war.combat, game, war, attacking, rng, formation_contexts)

    def _resolve_player_war_round(
        self, game: GameState, war: dict[str, Any], side: str, rng: random.Random,
    ) -> None:
        return war_combat._resolve_player_war_round(self._dependencies.war.combat, game, war, side, rng)

    def _resolve_war_vanguard(self, game: GameState, pending: dict[str, Any], mode: str, rng: random.Random) -> tuple[str, str]:
        return war_combat._resolve_war_vanguard(self._dependencies.war.combat, game, pending, mode, rng)

    def _advance_wars_unit(self, game: GameState, rng: random.Random) -> list[str]:
        return war_lifecycle._advance_wars_unit(self._dependencies.war.lifecycle, game, rng)

    def _finish_war_by_morale(self, game: GameState, war: dict[str, Any]) -> bool:
        return war_lifecycle._finish_war_by_morale(self._dependencies.war.lifecycle, game, war)

    def _generate_ai_peace_offer(self, game: GameState, war: dict[str, Any], proposer: str) -> dict[str, Any]:
        return war_peace._generate_ai_peace_offer(self._dependencies.war.peace, game, war, proposer)

    def _conclude_war_bundle(self, game: GameState, war: dict[str, Any], demands: list[dict[str, Any]],
                             beneficiary: str, *, automatic: bool = False) -> str:
        return war_peace._conclude_war_bundle(self._dependencies.war.peace, game, war, demands, beneficiary, automatic=automatic)

    def _conclude_war(self, game: GameState, war: dict[str, Any], term: str, beneficiary: str, *, automatic: bool = False,
                      target_id: str = "", target_power_id: str = "", third_party_id: str = "",
                      third_status: str = "neutral", finalize: bool = True) -> str:
        return war_peace._conclude_war(self._dependencies.war.peace, game, war, term, beneficiary, automatic=automatic, target_id=target_id, target_power_id=target_power_id, third_party_id=third_party_id, third_status=third_status, finalize=finalize)

    def war_peace(self, game_id: str, war_id: str, term: str, *, target_id: str = "", target_power_id: str = "",
                  third_party_id: str = "", third_status: str = "neutral", concede: bool = False) -> dict[str, Any]:
        return war_peace.war_peace(self._dependencies.war.peace, game_id, war_id, term, target_id=target_id, target_power_id=target_power_id, third_party_id=third_party_id, third_status=third_status, concede=concede)

    def war_action(self, game_id: str, war_id: str, action: str, *, ally_id: str = "") -> dict[str, Any]:
        return war_actions.war_action(self._dependencies.war.actions, game_id, war_id, action, ally_id=ally_id)

    def _maybe_map_war_encounter(self, game, rng):
        return war_actions._maybe_map_war_encounter(self._dependencies.war.actions, game, rng)

    def _public_war_system(self, game: GameState) -> dict[str, Any]:
        return war_presentation._public_war_system(self._dependencies.war.presentation, game)

    @staticmethod
    def _war_sect(game, power_id):
        return war_compat._war_sect(game, power_id)

    @staticmethod
    def _war_rules() -> dict[str, Any]:
        return war_compat._war_rules()

    @staticmethod
    def _war_formation_metric_score(profile: dict[str, Any], side: str) -> float:
        return war_compat._war_formation_metric_score(profile, side)

    @staticmethod
    def _war_formation_text(contexts: dict[str, dict[str, Any]]) -> str:
        return war_compat._war_formation_text(contexts)

    @staticmethod
    def _war_defeat_probabilities(realm_index: int) -> tuple[float, float]:
        return war_compat._war_defeat_probabilities(realm_index)

    @property
    def _war_dependencies(self):
        return self._dependencies.war

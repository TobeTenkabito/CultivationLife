from __future__ import annotations

import random
from pathlib import Path
from typing import Any
from ..content_registry import WORLD_SYSTEMS, STORY_COMBAT_SCENARIOS, CONTENT_DOCUMENTS, ContentError
from ..system.combat_system import BattleUnit
from ..event_repository import EventRepository
from ..system.economy_system import EconomySystemMixin
from ..system.demonic_system import DemonicSystemMixin
from ..map_runtime import MapTravelMixin
from ..models import GameState, HistoryRecord, Player, SectNpc, SectState
from ..system.map_system import MapCatalog
from ..storage import SaveStore
from ..achievements import AchievementSystem, load_achievement_definitions
from ..runtime import encode_rng, now_iso
from ..system.war_system import WarSystemMixin
from ..system.heavenly_court_system import HeavenlyCourtSystemMixin
from ..system.natal_artifact_system import NatalArtifactSystemMixin
from ..system.crafting_system import CraftingSystemMixin
from ..system.formation_system import FormationSystemMixin
from ..system.monster_bloodline_system import MonsterBloodlineSystemMixin, bloodline_content_available
from ..system.ghost_system import GhostSystemMixin
from ..system.intrigue_system import IntrigueSystemMixin
from ..system.sage_system import SageSystemMixin
from ..system.concubine_system import ConcubineSystemMixin
from ..system.guixu_system import GuixuSystemMixin
from ..system.tianji_system import TianjiSystemMixin
from ..system.merchant_system import MerchantSystemMixin
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


class GameEngine(MerchantSystemMixin, TianjiSystemMixin, GuixuSystemMixin, SageSystemMixin, ConcubineSystemMixin, IntrigueSystemMixin, FormationSystemMixin, CraftingSystemMixin, GhostSystemMixin, MonsterBloodlineSystemMixin, NatalArtifactSystemMixin, HeavenlyCourtSystemMixin, WarSystemMixin, MapTravelMixin, EconomySystemMixin, DemonicSystemMixin):
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

    def get_game(self, game_id: str) -> dict[str, Any]:
        return self.present(self._load(game_id))

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
        if setting not in {
            "combat_popup", "achievement_popup", "auto_advance_player_wars",
            "guixu_event_popup",
        }:
            raise ValueError("未知设置项")
        game.settings[setting] = bool(enabled)
        if (
            setting == "guixu_event_popup" and not enabled and game.pending_event
            and str(game.pending_event.get("id", "")) in {"EVT_GUIXU_ANNOUNCE", "EVT_GUIXU_OPEN"}
        ):
            game.pending_event = None
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

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
        return presentation_runtime.present(self._dependencies.presentation_runtime, game)

    @staticmethod
    def _history_visible_in_world(record: HistoryRecord, game: GameState) -> bool:
        return presentation_runtime._history_visible_in_world(record, game)

    def _load(self, game_id: str) -> GameState:
        return persistence_runtime._load(self._dependencies.persistence_runtime, game_id)

    def create_game(self, name: str, spirit_root: str, path: str, seed: int | None=None, technique_element: str | None=None, preset_id: str | None=None, start_world: str | None=None, monster_species_id: str | None=None, gender: str='male') -> dict[str, Any]:
        return session.create_game(self._dependencies.session, name, spirit_root, path, seed, technique_element, preset_id, start_world, monster_species_id, gender)

    def advance(self, game_id: str, action: str, years: int=1) -> dict[str, Any]:
        return advancement.advance(self._dependencies.advancement, game_id, action, years)

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
        return world_travel_actions._resolve_selected_ascension_entourage(self._dependencies.world_travel_actions, game, destination, rng)

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

    def _start_breakthrough_trial(self, game: GameState, kind: str, source: int, target: int, old_label: str, major: bool, rng: random.Random) -> None:
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
    def _ascension_destination(path: str) -> str:
        return npcs._ascension_destination(path)

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
        return world_relationships._annual_offspring_and_family_update(self._dependencies.world_relationships, game, rng)

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
        return world_factions._maybe_race_war_ambush(self._dependencies.world_factions, game, rng)

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
        return faction_view._public_family(self._dependencies.faction_view, game)

    def _public_governance(self, game: GameState) -> dict[str, Any]:
        return faction_view._public_governance(self._dependencies.faction_view, game)

    def _public_faction(self, game: GameState) -> dict[str, Any]:
        return faction_view._public_faction(self._dependencies.faction_view, game)

    def _public_sect_diplomacy(self, game: GameState, sect: SectState) -> list[dict[str, Any]]:
        return faction_view._public_sect_diplomacy(self._dependencies.faction_view, game, sect)

    def _vassal_transfer_candidates(self, game: GameState, kind: str, own_id: str, target_id: str, relation: dict[str, Any]) -> list[dict[str, Any]]:
        return faction_view._vassal_transfer_candidates(self._dependencies.faction_view, game, kind, own_id, target_id, relation)

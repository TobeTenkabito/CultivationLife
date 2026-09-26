from __future__ import annotations

import copy
import math
import operator
import random
import uuid
from pathlib import Path
from types import FunctionType
from typing import Any

# Runtime components are rebound to this module's globals. Keep these imports
# here even when their callers live in subpackages; see README.md.
from ..content_registry import (
    ACTIONS, FACTION_DEFINITIONS, FACTION_NPC_TEMPLATES, FACTION_REWARDS, FACTION_SYSTEMS,
    GUIXU_EXCLUSIVE_TECHNIQUE_IDS, ITEM_CATALOG, KARMA_FACTORS, MARKET_GOODS,
    MARKET_SETTINGS, PATH_NAMES, REALMS,
    RACE_DEFINITIONS, RACE_SYSTEMS, ROOT_DEFINITIONS, ROOT_NAMES, TECHNIQUE_CATALOG,
    TECHNIQUE_ELEMENT_NAMES, TRANSFORMATION_CATALOG, WORLD_NPC_TEMPLATES, WORLD_SYSTEMS,
    STORY_COMBAT_SCENARIOS, CONTENT_DOCUMENTS, MONSTER_BLOODLINE_SETTINGS, MONSTER_SPECIES, ContentError,
)
from ..system.combat_system import BattleUnit, PlayerCombatSystem, stat_comparison
from ..event_repository import EventRepository
from ..system.economy_system import EconomySystemMixin
from ..system.demonic_system import DemonicSystemMixin
from ..map_runtime import MapTravelMixin
from ..models import GameState, HistoryRecord, Player, SectNpc, SectState, Technique
from ..system.map_system import MapCatalog
from ..system.npc_system import attitude_label, npc_breakthrough_chance, npc_combat_power, npc_team_combat_power, party_combat_power
from ..rules import (
    add_item,
    assign_technique,
    can_practice_technique,
    can_player_practice_technique,
    combat_root_mana_cost_multiplier,
    combat_power,
    combat_power_assessment_value,
    expected_combat_power,
    effective_karma,
    has_item,
    acquire_technique,
    learn_technique,
    max_hp,
    max_mp,
    negative_event_multiplier,
    opportunity_multiplier,
    opportunity_required,
    public_player,
    realm,
    remove_item,
    root_definition,
    root_elements,
    roll_lifespan,
    ensure_technique_set,
    technique_environment_multiplier,
    QI_NAMES,
    grant_qi_experience,
    qi_level,
    qi_level_threshold,
    recommended_combat_power,
    divine_sense_breakthrough_cost,
    divine_sense_level,
    divine_sense_level_threshold,
    technique_scale,
    add_technique_copy,
    merge_technique_copies,
    upgrade_known_technique,
)
from ..system.transformation_system import (
    absorption_gain, active_transformation_profile, ensure_transformation_state,
    form_purity, form_stat_progress, forms_are_incompatible, public_transformation_system,
    transformation_technique_limits,
)


from ..storage import SaveStore
from ..achievements import AchievementSystem, load_achievement_definitions
from ..simulation import ActionUnitLedger
from ..runtime import decode_rng, encode_rng, now_iso
from ..world_state import (
    RELATION_LABELS, choose_weighted_race, encounter_weight, push_fifo_cache,
    race_pair, relation_status, split_race_pair,
)
from ..system.war_system import WarSystemMixin
from ..system.heavenly_court_system import HeavenlyCourtSystemMixin
from ..system.natal_artifact_system import NatalArtifactSystemMixin
from ..system.crafting_system import CraftingSystemMixin, crafted_artifact_bonuses, crafted_combat_effects
from ..system.formation_system import (
    FormationSystemMixin, active_formation_profile, ensure_formation_state,
    formation_battle_experience_gain,
)
from ..system.monster_bloodline_system import (
    MonsterBloodlineSystemMixin, bloodline_content_available,
    ensure_monster_bloodline_state, initialize_monster_bloodline,
    public_monster_bloodline,
)
from ..monster_general_traits import grant_random_general_monster_trait
from ..system.ghost_system import (
    GhostSystemMixin, ensure_ghost_cultivation_state, ghost_cultivation_active,
    grant_intrinsic_growth, grant_intrinsic_progression_if_new_highwater,
    grant_wangsheng, reincarnation_breakthrough_bonus,
)
from ..system.intrigue_system import IntrigueSystemMixin
from ..system.sage_system import SageSystemMixin
from ..system.concubine_system import ConcubineSystemMixin, gender_name
from ..system.guixu_system import GuixuSystemMixin
from ..system.tianji_system import TianjiSystemMixin
from ..system.merchant_system import MerchantSystemMixin
from ..system.possession_system import (
    advance_player_age, current_body_age, migrate_possession_timeline,
)
from .engine_constants import LEGACY_TRUE_DEMON_RACE_MAP, OPS


from .engine_world_runtime import EngineWorldRuntimeMixin
from .engine_event_runtime import EngineEventRuntimeMixin
from .engine_combat_runtime import EngineCombatRuntimeMixin
from .engine_presentation import EnginePresentationMixin
from .engine_persistence import EnginePersistenceMixin
from .orchestration.session import EngineSessionMixin
from .orchestration.advancement import EngineAdvancementMixin
from .actions.cultivation import EngineCultivationActionsMixin
from .actions.world_travel import EngineWorldTravelActionsMixin
from .actions.factions import EngineFactionActionsMixin
from .actions.encounters import EngineEncounterActionsMixin
from .actions.inventory import EngineInventoryActionsMixin
from .actions.relationships import EngineRelationshipActionsMixin
from .events.choices import EngineEventChoicesMixin
from .progression.breakthroughs import EngineBreakthroughsMixin
from .progression.trials import EngineTrialsMixin
from .events.encounters import EngineEventEncountersMixin
from .events.effects import EngineEventEffectsMixin
from .world.npcs import EngineWorldNpcsMixin
from .world.relationships import EngineWorldRelationshipsMixin
from .world.factions import EngineWorldFactionsMixin
from .world.hostility import EngineWorldHostilityMixin
from .presentation.character import EngineCharacterPresentationMixin
from .presentation.world import EngineWorldPresentationMixin
from .presentation.factions import EngineFactionPresentationMixin


def _runtime_method(member: Any, target: type, name: str) -> Any:
    descriptor = None
    function = member
    if isinstance(member, staticmethod):
        descriptor = staticmethod
        function = member.__func__
    elif isinstance(member, classmethod):
        descriptor = classmethod
        function = member.__func__
    if not isinstance(function, FunctionType):
        return member
    rebound = FunctionType(
        function.__code__, globals(), function.__name__, function.__defaults__, function.__closure__,
    )
    rebound.__kwdefaults__ = function.__kwdefaults__
    rebound.__annotations__ = dict(function.__annotations__)
    rebound.__dict__.update(function.__dict__)
    rebound.__doc__ = function.__doc__
    rebound.__module__ = target.__module__
    rebound.__qualname__ = f"{target.__qualname__}.{name}"
    return descriptor(rebound) if descriptor else rebound


def _include_runtime_methods(*components: type):
    """Attach moved methods without changing GameEngine's established MRO."""
    def decorate(target: type) -> type:
        for component in components:
            for name, member in vars(component).items():
                if name.startswith("__"):
                    continue
                if name in vars(target):
                    raise RuntimeError(f"duplicate GameEngine runtime method: {name}")
                setattr(target, name, _runtime_method(member, target, name))
        return target
    return decorate


@_include_runtime_methods(
    EngineWorldRuntimeMixin,
    EngineEventRuntimeMixin,
    EngineCombatRuntimeMixin,
    EnginePresentationMixin,
    EnginePersistenceMixin,
    EngineSessionMixin,
    EngineAdvancementMixin,
    EngineCultivationActionsMixin,
    EngineWorldTravelActionsMixin,
    EngineFactionActionsMixin,
    EngineEncounterActionsMixin,
    EngineInventoryActionsMixin,
    EngineRelationshipActionsMixin,
    EngineEventChoicesMixin,
    EngineBreakthroughsMixin,
    EngineTrialsMixin,
    EngineEventEncountersMixin,
    EngineEventEffectsMixin,
    EngineWorldNpcsMixin,
    EngineWorldRelationshipsMixin,
    EngineWorldFactionsMixin,
    EngineWorldHostilityMixin,
    EngineCharacterPresentationMixin,
    EngineWorldPresentationMixin,
    EngineFactionPresentationMixin,
)
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

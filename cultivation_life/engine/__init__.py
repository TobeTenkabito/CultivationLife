from __future__ import annotations

import copy
import math
import operator
import random
import uuid
from pathlib import Path
from types import FunctionType
from typing import Any

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
from ..system.possession_system import (
    advance_player_age, current_body_age, migrate_possession_timeline,
)
from .engine_constants import LEGACY_TRUE_DEMON_RACE_MAP, OPS


from .engine_world_runtime import EngineWorldRuntimeMixin
from .engine_event_runtime import EngineEventRuntimeMixin
from .engine_combat_runtime import EngineCombatRuntimeMixin
from .engine_presentation import EnginePresentationMixin
from .engine_persistence import EnginePersistenceMixin


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
)
class GameEngine(TianjiSystemMixin, GuixuSystemMixin, SageSystemMixin, ConcubineSystemMixin, IntrigueSystemMixin, FormationSystemMixin, CraftingSystemMixin, GhostSystemMixin, MonsterBloodlineSystemMixin, NatalArtifactSystemMixin, HeavenlyCourtSystemMixin, WarSystemMixin, MapTravelMixin, EconomySystemMixin, DemonicSystemMixin):
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

    def create_game(
        self, name: str, spirit_root: str, path: str, seed: int | None = None,
        technique_element: str | None = None, preset_id: str | None = None,
        start_world: str | None = None, monster_species_id: str | None = None,
        gender: str = "male",
    ) -> dict[str, Any]:
        preset = next(
            (entry for entry in WORLD_SYSTEMS.get("quick_start_presets", []) if entry["id"] == preset_id),
            None,
        ) if preset_id else None
        if preset_id and preset is None:
            raise ValueError("未知快速开局预设")
        if preset and not preset.get("enabled"):
            raise ValueError(preset.get("status", "该快速开局尚未开放"))
        if preset:
            spirit_root = str(preset["spirit_root"])
            path = str(preset["path"])
        if spirit_root not in ROOT_NAMES:
            raise ValueError("未知灵根")
        if path not in PATH_NAMES:
            raise ValueError("未知主修类型")
        if gender not in {"male", "female"}:
            raise ValueError("未知性别")
        allowed_start_worlds = WORLD_SYSTEMS.get("start_worlds", {}).get(path, ["human"])
        selected_start_world = str(start_world or "human")
        if not preset and selected_start_world not in allowed_start_worlds:
            raise ValueError("该修行道统无法从所选界面开局")
        clean_name = name.strip()[:16] or "无名散修"
        actual_seed = seed if seed is not None else random.SystemRandom().randrange(1, 2**31)
        rng = random.Random(actual_seed)
        player = Player(
            name=clean_name, spirit_root=spirit_root, path=path, gender=gender,
            born_rootless=spirit_root == "none",
            world=selected_start_world,
        )
        if path == "monster" and bloodline_content_available():
            player.race = "monster"
            initialize_monster_bloodline(player, monster_species_id)
            starter_id = str(MONSTER_BLOODLINE_SETTINGS.get("starter_technique_id", ""))
            if starter_id in TECHNIQUE_CATALOG:
                starter = copy.deepcopy(TECHNIQUE_CATALOG[starter_id])
                learn_technique(player, starter)
                assign_technique(player, starter, "main")
        if path == "demonic":
            starter = copy.deepcopy(TECHNIQUE_CATALOG["TECH_DEMON_BREATHING"])
            learn_technique(player, starter)
            assign_technique(player, starter, "main")
            sense = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BLOOD_SOUL_SENSE"])
            learn_technique(player, sense)
            assign_technique(player, sense, "divine_sense")
            player.divine_sense_rank = 1
            player.divine_sense_experience = 0.0
        if path == "ghost":
            starter = copy.deepcopy(TECHNIQUE_CATALOG["TECH_GHOST_BREATHING"])
            learn_technique(player, starter)
            assign_technique(player, starter, "main")
            sense = copy.deepcopy(TECHNIQUE_CATALOG["TECH_SOUL_ECHO_SENSE"])
            learn_technique(player, sense)
            assign_technique(player, sense, "divine_sense")
            player.divine_sense_rank = 1
            player.divine_sense_experience = 0.0
        if preset:
            player.realm_index = int(preset["realm_index"])
            player.layer = int(preset["layer"])
            player.age = int(preset["age"])
            player.world = str(preset["world"])
            player.race = str(preset["race"])
            player.karma = float(preset.get("karma", 0))
            player.sha_qi = int(preset.get("sha_qi", 0))
            player.fame = float(preset.get("fame", 0))
            player.body_training = max(0, int(preset.get("body_training", player.body_training)))
            player.body_progress = max(0.0, float(preset.get("body_progress", player.body_progress)))
            player.divine_sense_rank = max(0, int(preset.get("divine_sense_rank", player.divine_sense_rank)))
            player.divine_sense_experience = max(
                0.0, float(preset.get("divine_sense_experience", player.divine_sense_experience)),
            )
            player.story_flags = list(dict.fromkeys(str(flag) for flag in preset.get("story_flags", [])))
            player.additional_roots = list(dict.fromkeys(preset.get("additional_roots", [])))
            player.immortal_power_converted = bool(preset.get("immortal_power_converted", False))
            player.immortal_conversion_stage = 5 if player.immortal_power_converted else 0
            player.immortal_conversion_last_age = player.age if player.world == "celestial" else None
            starting_qi_level = {3: 5, 4: 8, 5: 12, 6: 17, 7: 23, 8: 30, 9: 30}.get(player.realm_index, 0)
            starting_source = "demon" if path == "demonic" else "monster" if path == "monster" else "yin" if path == "ghost" else "spirit"
            player.qi_experience[starting_source] = qi_level_threshold(starting_qi_level)
            # Compatibility presets may combine a path-native circulation with
            # neutral upper-realm arts.  Seed spirit mastery as well so every
            # equipped starting technique is immediately usable.
            if starting_qi_level and starting_source != "spirit":
                player.qi_experience["spirit"] = qi_level_threshold(starting_qi_level)
            if player.realm_index >= 6:
                for affinity in ("metal", "wood", "water", "fire", "earth"):
                    if affinity not in self._base_affinities(player) and affinity not in player.additional_roots:
                        player.additional_roots.append(affinity)
            assign_technique(player, copy.deepcopy(TECHNIQUE_CATALOG[preset["main_technique"]]), "main")
            assign_technique(player, copy.deepcopy(TECHNIQUE_CATALOG[preset["support_technique"]]), "support")
            if preset.get("body_technique"):
                assign_technique(player, copy.deepcopy(TECHNIQUE_CATALOG[preset["body_technique"]]), "body")
            if preset.get("divine_sense_technique"):
                assign_technique(
                    player, copy.deepcopy(TECHNIQUE_CATALOG[preset["divine_sense_technique"]]), "divine_sense",
                )
            for technique_id in preset.get("combat_techniques", []):
                assign_technique(player, copy.deepcopy(TECHNIQUE_CATALOG[technique_id]), "combat")
            for item in preset.get("inventory", []):
                add_item(player, item["id"], int(item["quantity"]))
            player.opportunity = round(opportunity_required(player) * float(preset.get("opportunity_fraction", 0)), 1)
        player.divine_sense_rank = max(
            player.divine_sense_rank,
            self._cultivation_sense_requirement(player.realm_index, player.layer),
        )
        # Every life begins with one ordinary weapon already in the equipment
        # section, including mortal creation and every quick-start preset.
        if not has_item(player, "spirit_sword"):
            add_item(player, "spirit_sword")
        player.lineage_race = player.race
        player.allegiance_race = player.race
        player.location_id = self.maps.default_location(player.world)
        ensure_ghost_cultivation_state(player)
        player.lifespan = roll_lifespan(player, rng)
        if ghost_cultivation_active(player):
            player.lifespan = None
        if player.lifespan is not None:
            player.lifespan = max(player.lifespan, player.age + 1)
        player.hp = max_hp(player)
        player.mp = max_mp(player)
        if preset:
            # Preserve the authored quick-start/benchmark ratio when DLCs raise
            # every realm's standard.  combat_power() applies the live summed
            # DLC percentage to this base reference, so configuration changes
            # never leave a stale permanent bonus in the save.
            player.quick_start_base_combat_power = combat_power(player)
        if player.realm_index >= 6 and player.world != "celestial":
            thunder = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
            player.next_tribulation_age = player.age + int(thunder["interval_years"])
            player.tribulation_power = float(thunder["base_power"])
        created = now_iso()
        game = GameState(str(uuid.uuid4()), actual_seed, player, created, created)
        game.sects = self._new_sects()
        game.world_npcs = self._new_world_npcs()
        self._ensure_sects(game)
        self._ensure_world_npcs(game)
        self._ensure_npc_formations(game)
        self._ensure_sage_state(game)
        self._ensure_guixu_state(game)
        self._ensure_tianji_state(game)
        if player.world == "celestial":
            self._ensure_heavenly_court(game, rng)
        self._ensure_race_relations(game)
        self._ensure_sect_relations(game)
        game.history.append(HistoryRecord(
            "SYS_BIRTH", 1, player.age, "问道之始", None, "created",
            (
                f"{clean_name}以快速开局承接既有因果，当前为{self._npc_realm_name(SectNpc('', '', '', player.realm_index, player.layer, 0, 1))}，"
                f"身具{ROOT_NAMES[spirit_root]}，已配置默认功法、属性与行囊。"
                if preset else
                f"{clean_name}以{'女' if gender == 'female' else '男'}身生于{WORLD_SYSTEMS['world_names'].get(player.world, player.world)}，身具{ROOT_NAMES[spirit_root]}，"
                f"心向{PATH_NAMES[path]}，但尚未获得任何功法。"
            ),
            {"lifespan": player.lifespan}, ["system", "milestone"],
        ))
        self._ensure_market(game, rng)
        self._ensure_ghost_parade(game, rng)
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        self.achievements.ensure_global_metadata()
        return self.present(game)

    def get_game(self, game_id: str) -> dict[str, Any]:
        return self.present(self._load(game_id))

    def list_games(self) -> list[dict[str, str]]:
        return self.store.list_games()

    def list_achievements(self) -> dict[str, Any]:
        return self.achievements.public_catalog()

    @staticmethod
    def _cultivation_sense_requirement(realm_index: int, layer: int) -> int:
        """Natural divine-sense rank earned by reaching one cultivation layer."""
        bounded_realm = max(0, min(int(realm_index), len(REALMS) - 1))
        bounded_layer = max(1, min(int(layer), REALMS[bounded_realm].layers))
        return sum(definition.layers for definition in REALMS[:bounded_realm]) + bounded_layer - 1

    def _secret_art_realm_name(self, player: Player, realm_index: int, layer: int = 1) -> str:
        shell = SectNpc(
            "secret-art", player.name, "", int(realm_index), int(layer),
            player.age, player.lifespan, path=player.path, world=player.world,
        )
        return self._npc_realm_name(shell)

    def manage_secret_art(
        self, game_id: str, art: str, action: str, realm_index: int | None = None,
        layer: int | None = None,
    ) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not player.alive:
            raise ValueError("此生已经结束")
        if art not in {"conceal", "suppress"} or action not in {"activate", "cancel"}:
            raise ValueError("未知秘法操作")

        if art == "conceal" and action == "cancel":
            if not player.cultivation_concealment:
                raise ValueError("当前没有运转收敛修为")
            old_name = self._secret_art_realm_name(
                player, player.cultivation_concealment["realm_index"],
                player.cultivation_concealment.get("layer", 1),
            )
            player.cultivation_concealment = None
            title, result = "散去敛息", "cancelled"
            summary = f"你散去收敛修为，对外气机不再停留于{old_name}。"
        elif art == "suppress" and action == "cancel":
            suppression = player.cultivation_suppression
            if not suppression:
                raise ValueError("当前没有运转压制修为")
            hp_ratio = player.hp / max(1.0, max_hp(player))
            mp_ratio = player.mp / max(1.0, max_mp(player))
            suppressed_name = self._secret_art_realm_name(player, player.realm_index, player.layer)
            accrued_opportunity = max(0.0, float(player.opportunity))
            player.realm_index = int(suppression["realm_index"])
            player.layer = int(suppression["layer"])
            player.opportunity = float(suppression.get("opportunity", 0.0)) + accrued_opportunity
            player.awaiting_ascension = bool(suppression.get("awaiting_ascension", False))
            player.awaiting_major_breakthrough = bool(suppression.get("awaiting_major_breakthrough", False))
            player.awaiting_minor_breakthrough = bool(suppression.get("awaiting_minor_breakthrough", False))
            player.awaiting_spirit_realm_crossing = bool(
                suppression.get("awaiting_spirit_realm_crossing", False)
            )
            player.active_breakthrough_aids = list(suppression.get("active_breakthrough_aids", []))
            if player.next_tribulation_age is None:
                due_age = suppression.get("next_tribulation_age")
                remaining = suppression.get("tribulation_remaining")
                player.next_tribulation_age = (
                    int(due_age) if due_age is not None else
                    player.age + int(remaining) if remaining is not None else None
                )
            player.cultivation_suppression = None
            player.hp = max(1.0, max_hp(player) * max(0.0, min(1.0, hp_ratio)))
            player.mp = max(0.0, max_mp(player) * max(0.0, min(1.0, mp_ratio)))
            true_name = self._secret_art_realm_name(player, player.realm_index, player.layer)
            title, result = "解开修为", "cancelled"
            summary = f"你解除秘法，将真正修为从{suppressed_name}完整复原至{true_name}；神识等级始终未变。"
            guixu_ejection = self._enforce_guixu_rank_boundary(game, "suppression_released")
            if guixu_ejection:
                summary += guixu_ejection
        else:
            if game.pending_event or game.active_trial or player.imprisonment:
                raise ValueError("事件、劫数或服刑期间不能改换修为秘法")
            if realm_index is None:
                raise ValueError("请选择目标境界")
            target_realm = int(realm_index)
            if not 0 <= target_realm < len(REALMS):
                raise ValueError("秘法目标境界不存在")
            target_layer = int(layer if layer is not None else 1)
            if not 1 <= target_layer <= REALMS[target_realm].layers:
                raise ValueError("秘法目标层数不存在")
            if (target_realm, target_layer) >= (player.realm_index, player.layer):
                raise ValueError("秘法目标必须低于当前生效修为")
            target_name = self._secret_art_realm_name(player, target_realm, target_layer)
            if art == "conceal":
                player.cultivation_concealment = {
                    "realm_index": target_realm, "layer": target_layer,
                }
                title, result = "收敛修为", "activated"
                summary = (
                    f"你将对外气机收敛为{target_name}。自身属性与突破状态不变，"
                    "主动遭遇会更偏向这一层次的推荐战力。"
                )
            else:
                if player.sealed_cultivation:
                    raise ValueError("下界法则正在封印真实道果，不能再叠加压制修为")
                if player.cultivation_suppression:
                    raise ValueError("当前已经处于压制修为状态")
                hp_ratio = player.hp / max(1.0, max_hp(player))
                mp_ratio = player.mp / max(1.0, max_mp(player))
                player.cultivation_suppression = {
                    "realm_index": player.realm_index,
                    "layer": player.layer,
                    "opportunity": player.opportunity,
                    "awaiting_ascension": player.awaiting_ascension,
                    "awaiting_major_breakthrough": player.awaiting_major_breakthrough,
                    "awaiting_minor_breakthrough": player.awaiting_minor_breakthrough,
                    "awaiting_spirit_realm_crossing": player.awaiting_spirit_realm_crossing,
                    "active_breakthrough_aids": list(player.active_breakthrough_aids),
                    "next_tribulation_age": player.next_tribulation_age,
                    "tribulation_remaining": (
                        max(0, player.next_tribulation_age - player.age)
                        if player.next_tribulation_age is not None else None
                    ),
                }
                player.realm_index = target_realm
                player.layer = target_layer
                player.opportunity = 0.0
                player.awaiting_ascension = False
                player.awaiting_major_breakthrough = False
                player.awaiting_minor_breakthrough = False
                player.awaiting_spirit_realm_crossing = False
                player.active_breakthrough_aids = []
                if (
                    player.cultivation_concealment
                    and (
                        int(player.cultivation_concealment["realm_index"]),
                        int(player.cultivation_concealment.get("layer", 1)),
                    ) >= (target_realm, target_layer)
                ):
                    player.cultivation_concealment = None
                player.hp = max(1.0, max_hp(player) * max(0.0, min(1.0, hp_ratio)))
                player.mp = max(0.0, max_mp(player) * max(0.0, min(1.0, mp_ratio)))
                title, result = "压制修为", "activated"
                summary = (
                    f"你将自身修为真正压制至{target_name}；境界属性与条件均按压制后结算，"
                    "但神识等级和神识经验完整保留。"
                )

        game.history.append(HistoryRecord(
            "SYS_SECRET_ART", 1, player.age, title, art, result, summary,
            {"art": art, "action": action, "target_realm_index": realm_index,
             "target_layer": layer},
            ["system", "secret_art", art],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _public_secret_arts(self, player: Player) -> dict[str, Any]:
        concealment = player.cultivation_concealment
        suppression = player.cultivation_suppression
        current_name = self._secret_art_realm_name(player, player.realm_index, player.layer)
        true_name = (
            self._secret_art_realm_name(
                player, int(suppression["realm_index"]), int(suppression["layer"]),
            ) if suppression else current_name
        )
        targets = []
        for index, definition in enumerate(REALMS):
            for target_layer in range(1, definition.layers + 1):
                if (index, target_layer) >= (player.realm_index, player.layer):
                    continue
                targets.append({
                    "realm_index": index, "layer": target_layer,
                    "name": self._secret_art_realm_name(player, index, target_layer),
                    "sense_requirement": self._cultivation_sense_requirement(index, target_layer),
                })
        return {
            "divine_sense_level": divine_sense_level(player),
            "natural_sense_level": self._cultivation_sense_requirement(
                int(suppression["realm_index"]) if suppression else player.realm_index,
                int(suppression["layer"]) if suppression else player.layer,
            ),
            "current_realm_name": current_name,
            "true_realm_name": true_name,
            "targets": targets,
            "concealment": {
                "active": bool(concealment),
                "realm_index": concealment.get("realm_index") if concealment else None,
                "layer": concealment.get("layer") if concealment else None,
                "realm_name": (
                    self._secret_art_realm_name(
                        player, concealment["realm_index"], concealment.get("layer", 1),
                    ) if concealment else None
                ),
            },
            "suppression": {
                "active": bool(suppression),
                "realm_name": current_name if suppression else None,
                "true_realm_name": true_name if suppression else None,
            },
        }

    def advance(self, game_id: str, action: str, years: int = 1) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not player.alive:
            raise ValueError("此生已经结束")
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        if game.heavenly_court.get("open_election"):
            raise ValueError("天庭大选正在进行；选举不流逝时间，请先在天庭界面完成投票")
        if player.world == "celestial" and not player.immortal_power_converted and action not in {"cultivate", "rest", "commission"}:
            raise ValueError("仙灵力尚未完全转化，当前只能修行、调息或承接坊市委托")
        if player.imprisonment:
            raise ValueError("你身陷大牢，只能选择服刑或尝试越狱")
        if player.ghost_captor and action not in {"cultivate", "rest"}:
            raise ValueError("魂印受制时只能等待、有限修炼、反抗或夺舍拘魂者")
        if action not in ACTIONS:
            raise ValueError("未知行动")
        guixu_session = (
            game.guixu_state.get("player_session")
            if isinstance(game.guixu_state, dict) else None
        )
        trapped_in_guixu = bool(guixu_session and guixu_session.get("trapped"))
        if player.cultivation_suppression and action == "cultivate" and not trapped_in_guixu:
            raise ValueError("压制修为期间不能运转主修功法；可修炼神识、炼体或进行其他行动")
        if action == "commission" and player.realm_index == 0:
            raise ValueError("凡人尚无法承接修仙坊市委托")
        if action == "body_train" and not trapped_in_guixu:
            if player.body_technique is None:
                raise ValueError("必须先获得并配置一部炼体功法")
            if player.body_training >= int(WORLD_SYSTEMS["body_cultivation"]["max_layer"]):
                raise ValueError("炼体已经达到一百层极限")
            if player.awaiting_body_breakthrough or player.body_progress >= self._body_progress_required(player):
                raise ValueError("炼体积累已经圆满，请先手动冲击下一层")
        if action == "sense_train" and player.divine_sense_technique is None and not trapped_in_guixu:
            raise ValueError("必须先获得并配置一部神识功法")
        if trapped_in_guixu:
            if action not in {"cultivate", "body_train", "sense_train", "rest"}:
                raise ValueError("被困归墟期间只能修炼、炼体、锻炼神识或调息")
            return self._guixu_trapped_training(game_id, action, years)
        if ACTIONS[action].get("combat") and player.realm_index == 0:
            raise ValueError("凡人尚无力参与修士层面的猎杀与斗法")
        self._prepare_sage_action(game, action)
        if action == "cultivate" and player.technique and not can_player_practice_technique(player, player.technique.element):
            raise ValueError("灵根属性与五行功法不合，无法修炼")
        units = max(1, min(10, int(years)))
        time_unit = int(WORLD_SYSTEMS["time_units"][str(player.realm_index)])
        years = units * time_unit
        rng = decode_rng(game.seed, game.rng_state)
        total_gain = 0.0
        total_body_gain = 0.0
        total_sense_gain = 0.0
        total_fame_reduction = 0.0
        treasure_results: list[str] = []
        commission_results: list[str] = []
        combat_results: list[str] = []
        era_news: list[str] = []
        start_world_age = player.age
        start_age = current_body_age(player)
        ledger = ActionUnitLedger(action, years)
        for elapsed_index in range(years):
            ledger.begin_year()
            advance_player_age(player)
            low, high = ACTIONS[action]["opportunity"]
            gain = rng.randint(low, high) * opportunity_multiplier(player)
            if action == "cultivate" and player.path == "demonic":
                gain *= float(WORLD_SYSTEMS["demonic_cultivation"]["natural_cultivation_multiplier"])
            if player.world == "celestial" and self._court_law_active(game, "immortal_twofold"):
                gain *= 1.10
            self._add_opportunity(player, gain)
            total_gain += gain
            if action == "sense_train":
                sense_gain = self._sense_training_step(player)
                player.divine_sense_experience += sense_gain
                total_sense_gain += sense_gain
                self._apply_action_resources(player, action, ledger.claim_resource_cost())
            elif action == "body_train":
                training_gain = self._body_training_step(player, rng)
                player.body_progress = min(self._body_progress_required(player), player.body_progress + training_gain)
                total_body_gain += training_gain
                self._apply_action_resources(player, action, ledger.claim_resource_cost())
                if player.body_progress >= self._body_progress_required(player):
                    player.awaiting_body_breakthrough = True
            elif action == "treasure":
                if ledger.claim_resource_cost():
                    treasure_results.append(self._treasure_step(game, rng))
                    if not player.alive:
                        break
            elif action == "commission":
                commission_results.append(self._commission_step(game, rng))
                self._apply_action_resources(player, action, ledger.claim_resource_cost())
            elif ACTIONS[action].get("combat"):
                # 一个行动单位只结算一次主动遭遇；高境界的一次点击虽跨越多年，
                # 不会因此把组队概率重复抽取五十或一百次。
                if ledger.claim_combat():
                    combat_results.append(self._personal_combat_step(game, action, rng))
                    if not player.alive:
                        break
            else:
                paid_cost = ledger.claim_resource_cost()
                self._apply_action_resources(player, action, paid_cost)
                if action == "befriend_neighbors" and paid_cost:
                    fame_rules = WORLD_SYSTEMS["fame"]
                    reduction = max(0.0, min(
                        player.fame,
                        float(fame_rules["reconciliation_base"])
                        + player.realm_index * float(fame_rules["reconciliation_realm_scale"]),
                    ))
                    player.fame = max(0.0, player.fame - reduction)
                    total_fame_reduction += reduction
                if action == "rest" and player.heart_demon > 0:
                    player.heart_demon = max(0.0, player.heart_demon - 0.5)
            continue_world = self._advance_world_year(game, rng, era_news)
            if player.alive:
                self._advance_soul_erosion_time(game, 1)
            if not continue_world or not player.alive:
                break
        if player.alive:
            action_title = "打熬筋骨" if action == "cultivate" and player.spirit_root == "none" else ACTIONS[action]["name"]
            action_summary = (
                f"完成一个教化行动单位：外在影响 {game.sage_state.get('action_result', {}).get('external', 0):+.2f}，内在影响 +{game.sage_state.get('action_result', {}).get('inner', 0):.2f}，门人出师 {game.sage_state.get('action_result', {}).get('graduated', 0)} 人。"
                if ACTIONS[action].get("sage_action")
                else
                f"从 {start_age} 岁炼体至 {current_body_age(player)} 岁；无灵根无法由吐纳获得机缘。"
                if action == "cultivate" and player.spirit_root == "none"
                else f"从 {start_age} 岁摸索至 {current_body_age(player)} 岁；尚无主修功法，无法炼化机缘。"
                if action == "cultivate" and player.technique is None
                else f"获得微量机缘 {total_gain:.1f}；{self._condense_action_results(treasure_results)}"
                if action == "treasure"
                else self._condense_action_results(commission_results)
                if action == "commission"
                else self._condense_action_results(combat_results)
                if ACTIONS[action].get("combat")
                else f"从 {start_age} 岁锻炼识海至 {current_body_age(player)} 岁，神识经验 +{total_sense_gain:.1f}；当前为 {divine_sense_level(player)} 级。"
                if action == "sense_train"
                else f"从 {start_age} 岁淬炼肉身至 {current_body_age(player)} 岁，炼体积累 +{total_body_gain:.1f}；当前为 {player.body_training} 层。"
                if action == "body_train"
                else f"你主动收敛声势、修复近邻关系，威名 -{total_fame_reduction:.0f}；当前威名 {player.fame:.0f}。"
                if action == "befriend_neighbors"
                else f"从 {start_age} 岁修行至 {current_body_age(player)} 岁，获得 {total_gain:.1f} 点机缘。"
            )
            game.history.append(HistoryRecord(
                "ACT_" + action.upper(), 1, player.age, action_title, action, "completed",
                action_summary,
                {
                    "age": [start_age, current_body_age(player)], "world_age": [start_world_age, player.age],
                    "opportunity": round(total_gain, 1),
                    **({"fame_reduction": round(total_fame_reduction, 1)} if action == "befriend_neighbors" else {}),
                }, ["action", action],
            ))
            if action == "treasure":
                self._queue_followup_event(game, self._prepare_treasure_reward_event(game, rng))
            completed_years = max(1, player.age - start_world_age)
            completed_units = max(1, (completed_years + time_unit - 1) // time_unit)
            artifact_news = self._advance_natal_artifact(game, action, completed_units)
            if artifact_news:
                era_news.append(artifact_news)
            for _ in range(completed_units):
                era_news.extend(self._advance_diplomacy_unit(game, rng))
                self._advance_concubine_aftermath(game, rng)
                era_news.extend(self._advance_heavenly_court_unit(game, rng))
                era_news.extend(self._advance_intrigue_unit(game, rng))
                tianji_news = self._maybe_tianji_intelligence_event(game, rng)
                if tianji_news:
                    era_news.append(tianji_news)
            drained = self._advance_concubine_status(game, completed_units)
            if drained:
                era_news.append(f"{player.age}岁：侍妾名分被抽走机缘 {drained:.1f}")
            self._advance_player_bounties(game, rng)
            if game.pending_event is None and player.ghost_captor:
                self._maybe_relationship_sanction(game, rng)
            elif game.pending_event is None:
                if self._maybe_relationship_sanction(game, rng):
                    pass
                elif self._maybe_immortal_conversion_event(game, rng):
                    pass
                elif self._maybe_concubine_proposal(game, rng):
                    pass
                elif self._maybe_personal_revenge(game, rng):
                    pass
                elif self._maybe_probability_story_event(game, rng):
                    pass
                elif self._maybe_xiang_node_event(game, rng):
                    pass
                elif self._maybe_founded_sect_pressure(game, rng):
                    pass
                elif self._maybe_affinity_gift(game, rng):
                    pass
                elif not self._maybe_faction_event(game, rng):
                    event = self._select_event(game, action, rng)
                    if event:
                        game.pending_event = self._instantiate_event(event, game, rng)
            elapsed_years = player.age - start_world_age
            if elapsed_years >= 5:
                self._record_era_summary(game, start_world_age, era_news)

            self._advance_auction_clock(game, rng)
            self._advance_exchange_clock(game, rng)

        self._finish_sage_action(game)
        # 坊市只在一次玩家操作结束时刷新。旧逻辑在大乘一次行动的 1000 个
        # 年度中重建 1000 次相同规模的随机货架，最终只有最后一次可见。
        self._ensure_market(game, rng)

        self._compact_world_history(game)
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def _add_opportunity(
        self, player: Player, amount: float,
        regional_efficiencies: dict[str, float] | None = None,
    ) -> float:
        before = player.opportunity
        player.opportunity = max(0.0, before + float(amount))
        actual_gain = player.opportunity - before
        if actual_gain > 0:
            grant_qi_experience(
                player, actual_gain,
                regional_efficiencies
                if regional_efficiencies is not None
                else self.maps.qi_gain_efficiencies(player.world, player.location_id),
            )
        return actual_gain

    def _sense_training_step(
        self, player: Player, regional: dict[str, float] | None = None,
        concentrations: dict[str, float] | None = None,
    ) -> float:
        """Calculate one year of sense training for every training context."""
        sense = player.divine_sense_technique
        if sense is None:
            return 0.0
        regional = (
            regional if regional is not None
            else self.maps.qi_gain_efficiencies(player.world, player.location_id)
        )
        regional_multiplier = sum(
            float(weight) * float(regional.get(source, 0))
            for source, weight in sense.sources.items()
        )
        return (
            float(WORLD_SYSTEMS["demonic_cultivation"]["divine_sense_training_base"])
            * (1 + sense.divine_sense_bonus * technique_scale(sense))
            * technique_environment_multiplier(sense, player.world, concentrations)
            * regional_multiplier
            * (1 + crafted_artifact_bonuses(player)["divine_sense_efficiency"])
            * (1 + max(0.0, float(player.sage_effects.get("sense_multiplier", 0.0))))
        )

    def _body_training_step(
        self, player: Player, rng: random.Random,
        concentrations: dict[str, float] | None = None,
    ) -> float:
        """Calculate one year of body training for every training context."""
        if player.body_technique is None:
            return 0.0
        body_rules = WORLD_SYSTEMS["body_cultivation"]
        return (
            rng.randint(*body_rules["progress_per_year"])
            * (1 + 0.04 * max(0, player.body_technique.grade - 1))
            * player.body_technique.level_multiplier
            * technique_environment_multiplier(player.body_technique, player.world, concentrations)
            * (
                float(WORLD_SYSTEMS.get("monster_cultivation", {}).get("body_training_multiplier", 1.5))
                if player.path == "monster" else 1.0
            )
            * (1 + crafted_artifact_bonuses(player)["body_training_efficiency"])
        )

    @staticmethod
    def _apply_action_resources(player: Player, action: str, pay_cost: bool) -> None:
        """Apply annual gains but charge negative HP/MP modifiers once per action unit."""
        for resource, maximum in (("hp", max_hp(player)), ("mp", max_mp(player))):
            if resource == "mp" and player.world == "celestial" and not player.immortal_power_converted:
                maximum *= max(0, min(5, player.immortal_conversion_stage)) / 5
            ratio = float(ACTIONS[action].get(resource, 0))
            if ratio < 0 and not pay_cost:
                continue
            value = getattr(player, resource) + maximum * ratio
            floor = 1 if action == "commission" and resource == "hp" else 0
            setattr(player, resource, min(maximum, max(floor, value)))

    @staticmethod
    def _remember_faction_prison_release(player: Player, prison: dict[str, Any]) -> None:
        """Persist the exact former jailer so a later dissolution can match it."""
        key = str(prison.get("key", ""))
        if ":" not in key:
            return
        kind, faction_id = key.split(":", 1)
        if kind not in {"sect", "family"} or not faction_id:
            return
        flag = f"released_faction_prison:{kind}:{faction_id}"
        if flag not in player.story_flags:
            player.story_flags.append(flag)

    @staticmethod
    def _record_former_jailer_dissolved(player: Player, kind: str, faction_id: str) -> bool:
        flag = f"released_faction_prison:{kind}:{faction_id}"
        if flag not in player.story_flags:
            return False
        player.milestones["dissolved_former_jailer"] = max(
            1, int(player.milestones.get("dissolved_former_jailer", 0)),
        )
        return True

    def prison_action(self, game_id: str, action: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        prison = player.imprisonment
        if not prison:
            raise ValueError("你当前并未被关押")
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        rng = decode_rng(game.seed, game.rng_state)
        key = str(prison["key"])
        if action == "endure":
            advance_player_age(player)
            hp_loss = max_hp(player) * rng.uniform(0.08, 0.18)
            mp_loss = max_mp(player) * rng.uniform(0.06, 0.14)
            player.hp = max(1.0, player.hp - hp_loss)
            player.mp = max(0.0, player.mp - mp_loss)
            degraded = False
            if (
                player.realm_index < 9
                and rng.random() < float(WORLD_SYSTEMS["faction_conflict"]["prison_breakthrough_loss_chance"])
            ):
                if player.layer > 1:
                    player.layer -= 1
                elif player.realm_index > 1:
                    player.realm_index -= 1
                    player.layer = REALMS[player.realm_index].layers
                player.opportunity = 0
                degraded = True
            prison["remaining_years"] = max(0, int(prison["remaining_years"]) - 1)
            hostility_reduction = float(prison.get("hostility_reduction_per_year", 4.0))
            player.hostility[key] = max(0.0, player.hostility.get(key, 0) - hostility_reduction)
            prison["hostility"] = round(player.hostility[key], 1)
            self._annual_sect_update(game, rng)
            self._annual_world_npc_update(game, rng)
            if player.lifespan is not None and current_body_age(player) >= player.lifespan:
                self._die(game, "囚禁期间寿元耗尽", "SYS_PRISON_LIFESPAN")
                result, summary = "dead", "你未能熬到刑满，在大牢中寿尽坐化。"
            else:
                self._check_tribulation(game, rng)
            if not player.alive:
                pass
            elif prison["remaining_years"] <= 0:
                player.hostility[key] = 0.0
                if key.startswith("world:"):
                    self._record_world_coalition_amnesty(player, key.split(":", 1)[1])
                self._remember_faction_prison_release(player, prison)
                player.imprisonment = None
                self._intrigue_sync_player_prison(game)
                result = "released"
                summary = "刑期已满，旧案已经服结，对你的敌意与通缉归零。"
            else:
                result = "degraded" if degraded else "endured"
                summary = f"你熬过一年刑狱折磨，尚余 {prison['remaining_years']} 年。" + (" 酷刑令你的修为倒退。" if degraded else "")
        elif action in {"wait", "cultivate"}:
            if prison.get("facility") != "faction_prison":
                raise ValueError("当前牢狱不允许此项行动")
            advance_player_age(player)
            gain = 0.0
            if action == "cultivate":
                gain = self._add_opportunity(player, max(0.2, opportunity_required(player) * 0.01))
                player.mp = max(0.0, player.mp - max_mp(player) * 0.04)
            prison["remaining_years"] = max(0, int(prison["remaining_years"]) - 1)
            hostility_reduction = float(prison.get("hostility_reduction_per_year", 4.0))
            player.hostility[key] = max(0.0, player.hostility.get(key, 0) - hostility_reduction)
            prison["hostility"] = round(player.hostility[key], 1)
            self._annual_sect_update(game, rng)
            self._annual_world_npc_update(game, rng)
            if player.lifespan is not None and current_body_age(player) >= player.lifespan:
                self._die(game, "囚禁期间寿元耗尽", "SYS_PRISON_LIFESPAN")
                result, summary = "dead", "你未能熬到刑满，在大牢中寿尽坐化。"
            elif prison["remaining_years"] <= 0:
                player.hostility[key] = 0.0
                self._remember_faction_prison_release(player, prison)
                player.imprisonment = None
                self._intrigue_sync_player_prison(game)
                result, summary = "released", "刑期已满，你获准离开势力监狱。"
            else:
                result = "cultivated" if action == "cultivate" else "waited"
                summary = (f"你在禁制下完成一年受限修炼，机缘 +{gain:.1f}；" if action == "cultivate" else "你静待一年；") + f"尚余 {prison['remaining_years']} 年刑期。"
        elif action == "escape":
            if prison.get("facility") == "faction_prison":
                raise ValueError("势力监狱 V1 暂不开放越狱")
            guard_power = expected_combat_power(player.realm_index, max(1, player.layer)) * (1 + player.hostility.get(key, 0) / 160)
            own_power = self._player_intrinsic_combat_power(player)
            chance = max(0.05, min(0.78, 0.18 + own_power / max(1.0, guard_power) * 0.28))
            player.hostility[key] = player.hostility.get(key, 0) + float(WORLD_SYSTEMS["faction_conflict"]["escape_hostility_gain"])
            if rng.random() < chance:
                player.imprisonment = None
                self._intrigue_sync_player_prison(game)
                result, summary = "escaped", f"你趁守卫换岗杀出大牢（成功率 {chance:.0%}），但通缉进一步加重。"
            else:
                damage = max_hp(player) * rng.uniform(0.25, 0.45)
                player.hp = max(0.0, player.hp - damage)
                if player.hp <= 0:
                    self._die(game, "越狱失败，被狱卒当场格杀", "SYS_PRISON_ESCAPE")
                    result, summary = "dead", "越狱失败，你被当场格杀。"
                else:
                    result, summary = "failed", f"越狱失败，HP -{damage:.0f}，敌对值继续上升。"
        else:
            raise ValueError("未知牢狱行动")
        if action in {"endure", "wait", "cultivate"} and player.alive and not self._advance_soul_erosion_time(game, 1):
            result = "dead"
            summary = "刑狱岁月令魂蚀越过最后界限，你在出狱前魂飞魄散。"
        if action in {"endure", "wait", "cultivate"} and player.alive:
            drained = self._advance_concubine_status(game, 1)
            if drained:
                summary += f" 侍妾名分仍在，机缘又被抽走 {drained:.1f}。"
        self._intrigue_sync_player_prison(game)
        game.history.append(HistoryRecord(
            "SYS_PRISON_ACTION", 1, player.age, "身陷囹圄", action, result, summary,
            {"imprisonment": copy.deepcopy(player.imprisonment)}, ["system", "prison", "wanted"],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    @staticmethod
    def _condense_action_results(results: list[str]) -> str:
        if len(results) <= 4:
            return " ".join(results)
        return " ".join(results[:3]) + f" ……其余 {len(results) - 3} 年的同类经历已并入本期结算。"

    @staticmethod
    def _record_era_summary(game: GameState, start_age: int, news: list[str]) -> None:
        distinct_news = list(dict.fromkeys(news))
        if game.pending_event:
            distinct_news.append(f"{game.player.age}岁：大事件“{game.pending_event['title']}”发生")
        if distinct_news:
            shown = distinct_news[:12]
            summary = "；".join(shown)
            if len(distinct_news) > len(shown):
                summary += f"；另有 {len(distinct_news) - len(shown)} 项人事变动记入各年档案"
        else:
            summary = "本期未发生足以传遍各地的突破、陨落或大事件。"
        game.history.append(HistoryRecord(
            "SYS_ERA_SUMMARY", 1, game.player.age, f"{game.player.age - start_age}年纪要", None, "summarized",
            summary, {"age": [start_age, game.player.age], "news_count": len(distinct_news)},
            ["system", "era_summary", "world_news", f"world:{game.player.world}"],
        ))

    def choose(self, game_id: str, choice_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        if not game.player.alive:
            raise ValueError("此生已经结束")
        pending = game.pending_event
        if not pending:
            raise ValueError("当前没有待处理事件")
        followup_event = pending.get("_followup_event")
        event = self.events_by_id[pending["id"]]
        tags = event.get("tags", [])
        history_tags = pending.get("_history_tags", tags)
        shareholder_option = (
            game.player.realm_index >= 4 and "faction" in tags and "duty" in tags and "war" not in tags
        )
        synthetic_choices = {
            "__delegate_faction_task": {
                "id": "__delegate_faction_task",
                "effects": [{"type": "add_faction_contribution", "value": -int(FACTION_SYSTEMS["shareholder_delegate_cost"])}],
            },
            "__decline_faction_task": {
                "id": "__decline_faction_task",
                "effects": [{"type": "add_faction_contribution", "value": -int(FACTION_SYSTEMS["shareholder_decline_cost"])}],
            },
        }
        choice = synthetic_choices.get(choice_id) if shareholder_option else None
        choice = choice or next((entry for entry in event["choices"] if entry["id"] == choice_id), None)
        if choice is None:
            raise ValueError("事件选项不存在")
        if choice.get("conditions") and not self._condition(choice["conditions"], game):
            raise ValueError(choice.get("disabled_reason", "当前条件不满足"))

        rng = decode_rng(game.seed, game.rng_state)
        pending["_choice_id"] = choice_id
        before = self._snapshot(game.player)
        summaries: list[str] = []
        result = "resolved"
        # 先摘下旧事件，使通用 queue_event 效果可以安全接续剧情链。
        game.pending_event = None
        for effect in choice.get("effects", []):
            required_result = effect.get("if_result")
            if required_result and result not in required_result:
                continue
            outcome, text = self._effect(effect, game, pending, rng)
            summaries.append(text)
            if outcome:
                result = outcome
            if not game.player.alive:
                break
        after = self._snapshot(game.player)
        game.history.append(HistoryRecord(
            event["id"], event.get("version", 1), game.player.age, event["title"], choice_id, result,
            " ".join(filter(None, summaries)) or choice.get("result_text", "你做出了选择。"),
            self._diff(before, after), history_tags,
        ))
        self._resolve_breakthroughs(game, rng)
        self._enforce_guixu_rank_boundary(game, "breakthrough")
        self._ensure_market(game, rng)
        if game.pending_event is None:
            self._maybe_artifact_synthesis(game, rng)
        if followup_event and game.player.alive:
            self._queue_followup_event(game, followup_event)
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    @staticmethod
    def _queue_followup_event(game: GameState, event: dict[str, Any]) -> None:
        """将必得奖励接到当前事件链末端，避免被渡劫或剧情事件覆盖。"""
        if game.pending_event is None:
            game.pending_event = event
            return
        tail = game.pending_event
        while tail.get("_followup_event"):
            tail = tail["_followup_event"]
        tail["_followup_event"] = event

    def _handover_faction_for_ascension(self, game: GameState) -> dict[str, Any] | None:
        """Remove the player from a lower-world faction and leave a real NPC ruler."""
        player = game.player
        sect = game.sects.get(player.faction_id or "")
        if not sect or sect.extinct:
            return None
        record = self._intrigue_state(game).get("factions", {}).get(self._intrigue_key("sect", sect.id), {})
        controlled = bool(sect.founded_by_player or record.get("controller_id") == "player")
        plan = self._intrigue_state(game).setdefault("succession_plans", {}).get(sect.id, {})
        successor_id = str(plan.get("successor_id", "")) if plan.get("arranged") else ""
        members = [npc for npc in self._sect_members(game, sect) if npc.alive and npc.world == sect.world]
        successor = next((npc for npc in members if npc.id == successor_id), None)
        if not successor:
            successor = max(members, key=lambda npc: (npc.realm_index, npc.layer, -npc.age), default=None)
        if controlled:
            was_founder = bool(sect.founded_by_player and sect.founder_player_id == game.id)
            arranged = bool(plan.get("arranged") and successor)
            sect.founded_by_player = False
            sect.founded_by_npc = bool(successor)
            sect.founder_npc_id = successor.id if successor else None
            # Only an explicitly arranged succession preserves the historical
            # founder link required by the later 寻觅祖师 event.
            sect.founder_player_id = game.id if was_founder and arranged else None
            if record:
                record["controller_id"] = successor.id if successor else None
                positions = record.setdefault("positions", {})
                if positions:
                    leader = next(iter(self._intrigue_position_specs("sect")), "")
                    if leader:
                        positions[leader] = successor.id if successor else None
            plan.update({
                "arranged": arranged, "eligible_return": bool(was_founder and arranged),
                "successor_id": successor.id if successor else None,
                "origin_world": sect.world, "ascended_age": player.age,
            })
            self._intrigue_state(game).setdefault("succession_plans", {})[sect.id] = plan
        return {
            "sect_id": sect.id, "sect_name": sect.name, "controlled": controlled,
            "arranged": bool(plan.get("arranged")),
            "successor_name": successor.name if successor else None,
        }

    def _prepare_permanent_world_transition(
        self, game: GameState, *, keep_companion: bool = False,
        keep_friend_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        """Apply the shared, irreversible cleanup required by every ascension."""
        player = game.player
        keep_friend_ids = keep_friend_ids or set()
        handover = self._handover_faction_for_ascension(game)
        removed = {
            "puppets": len(player.puppets), "prisoners": len(player.prisoners),
            "concubines": len(player.concubines),
        }
        player.puppets = []
        player.prisoners = []
        player.concubines = []
        player.concubine_status = None
        player.concubine_rejection_aftermath = []
        player.master = None
        player.disciples = []
        player.disciple_requests = []
        player.relationship_attempts = []
        player.dao_friends = [
            row for row in player.dao_friends if str(row.get("id")) in keep_friend_ids
        ]
        if not keep_companion:
            player.dao_companion = None
        player.joint_spirit_crossing = None
        player.joint_friend_crossing = []
        player.party = []
        player.faction_id = None
        player.faction_join_age = None
        player.faction_contribution = 0
        player.faction_reward_preference = None
        player.allegiance_race = player.lineage_race or player.race
        player.fame = 0.0
        if player.imprisonment:
            player.imprisonment = None
            self._intrigue_sync_player_prison(game)
        for record in self._intrigue_state(game).get("factions", {}).values():
            record["guests"] = [
                row for row in record.get("guests", []) if row.get("npc_id") != "player"
            ]
        self._intrigue_state(game)["pending_guest_invitation"] = None
        self._cancel_auction_for_world_change(game)
        return {"removed": removed, "faction_handover": handover}

    def _resolve_selected_ascension_entourage(
        self, game: GameState, destination: str, rng: random.Random,
    ) -> tuple[bool, set[str], list[str], list[str]]:
        """Resolve explicitly invited partner/friends before permanent cleanup."""
        player = game.player
        companion = player.dao_companion
        companion_kept = bool(
            companion and player.joint_spirit_crossing
            and str(companion.get("id")) == str(player.joint_spirit_crossing.get("id"))
            and not player.joint_spirit_crossing.get("declined")
            and self._party_crossing_candidate(game, str(companion.get("id", "")))
        )
        if companion_kept and companion:
            companion["world"] = destination
            npc = self._find_npc(game, str(companion.get("id", "")))
            if npc:
                npc.world = destination
                npc.departed_age = npc.age
                npc.departure_reason = f"与{player.name}共同飞升{WORLD_SYSTEMS['world_names'][destination]}"
        survivors: set[str] = set()
        survivor_names: list[str] = []
        fallen_names: list[str] = []
        chance = float(WORLD_SYSTEMS["relationship"]["friend_crossing_survival_chance"])
        selected = {str(row.get("id", "")) for row in player.joint_friend_crossing}
        for npc_id in selected:
            if not any(str(row.get("id")) == npc_id for row in player.party):
                continue
            candidate = self._party_crossing_candidate(game, npc_id)
            friend = next((row for row in player.dao_friends if str(row.get("id")) == npc_id), None)
            if not candidate or not friend:
                continue
            npc = self._find_npc(game, npc_id)
            if rng.random() < chance:
                friend["world"] = destination
                survivors.add(npc_id)
                survivor_names.append(str(friend.get("name", candidate["name"])))
                if npc:
                    npc.world = destination
                    npc.departed_age = npc.age
                    npc.departure_reason = f"与{player.name}共同飞升{WORLD_SYSTEMS['world_names'][destination]}"
            else:
                friend["alive"] = False
                friend["death_reason"] = "飞升界壁时迷失于空间风暴"
                fallen_names.append(str(friend.get("name", candidate["name"])))
                if npc:
                    npc.alive = False
                    npc.death_reason = "飞升界壁时迷失于空间风暴"
        return companion_kept, survivors, survivor_names, fallen_names

    def _maybe_founder_return_event(self, game: GameState, rng: random.Random) -> bool:
        if game.pending_event or game.player.faction_id:
            return False
        plans = self._intrigue_state(game).get("succession_plans", {})
        candidates = [
            (sect_id, plan) for sect_id, plan in plans.items()
            if plan.get("eligible_return")
            and (sect := game.sects.get(sect_id)) is not None
            and not sect.extinct and sect.world == game.player.world
            and sect.founder_player_id == game.id
        ]
        if not candidates or rng.random() >= 0.5:
            return False
        sect_id, _ = candidates[0]
        sect = game.sects[sect_id]
        event = self._instantiate_event(self.events_by_id["EVT_FOUNDER_RETURN_001"], game, rng)
        event["body"] = str(event.get("body", "")).replace("{sect_name}", sect.name)
        event["runtime"] = {"sect_id": sect.id, "sect_name": sect.name}
        game.pending_event = event
        return True

    def begin_spirit_crossing(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not player.alive:
            raise ValueError("此生已经结束")
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        if player.sealed_cultivation:
            raise ValueError("当前身处下界且真实道果处于封印中，只能重返原上界")
        if player.path == "demonic":
            if player.imprisonment:
                raise ValueError("服刑期间只能尝试人界偷渡，无法走魔界飞升通道")
            return self._complete_demonic_ascension(game)
        if player.world != "human":
            raise ValueError("你已经脱离人界")
        if player.realm_index != 5 or player.layer > 3:
            raise ValueError("只有达到人界化神初期，方能尝试偷渡灵界")
        if player.spirit_realm_attempted:
            raise ValueError("偷渡灵界的机会只有一次")
        rng = decode_rng(game.seed, game.rng_state)
        player.spirit_realm_attempted = True
        companion = player.dao_companion
        can_cross_together = bool(
            companion and companion.get("alive", True)
            and companion.get("world", player.world) == "human"
            and int(companion.get("realm_index", -1)) == 5
            and int(companion.get("layer", 99)) <= 3
        )
        companion_selected = bool(
            can_cross_together
            and (
                player.joint_spirit_crossing is None
                or (
                    str(player.joint_spirit_crossing.get("id")) == str(companion.get("id"))
                    and not player.joint_spirit_crossing.get("declined")
                )
            )
        )
        player.joint_spirit_crossing = (
            {"id": companion["id"], "name": companion["name"]} if companion_selected else None
        )
        selected_ids = {str(entry.get("id")) for entry in player.joint_friend_crossing}
        player.joint_friend_crossing = [
            candidate for npc_id in selected_ids
            if (candidate := self._party_crossing_candidate(game, npc_id)) is not None
            and any(str(member.get("id")) == npc_id for member in player.party)
        ]
        destination = self._ascension_destination(player.path)
        destination_name = WORLD_SYSTEMS["world_names"][destination]
        event = self.events_by_id["EVT_SPIRIT_CROSSING_001"]
        game.pending_event = self._instantiate_event(event, game, rng)
        if player.path in {"monster", "ghost"}:
            game.pending_event["title"] = f"偷渡{destination_name}"
            game.pending_event["body"] = str(game.pending_event.get("body", "")).replace("灵界", destination_name)
        game.history.append(HistoryRecord(
            "SYS_SPIRIT_CROSSING_BEGIN", 1, player.age, "破界之举", None, "started",
            f"你已锁定空间乱流，踏出后便再无回头路。偷渡{destination_name}的机会只有这一次。"
            + (f" {companion['name']}接受了你的邀请，将与你共同闯过界壁。" if companion_selected else "")
            + (f" 你还邀上了{len(player.joint_friend_crossing)}位同境队友；他们没有道侣契约庇护，极可能陨落。" if player.joint_friend_crossing else ""),
            {"spirit_realm_attempted": [False, True]}, ["system", "ascension", "milestone"],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def begin_celestial_ascension(self, game_id: str) -> dict[str, Any]:
        """Start the dedicated nine-stage Mahayana ascension trial."""
        game = self._load(game_id)
        player = game.player
        if not player.alive:
            raise ValueError("此生已经结束")
        if game.pending_event or game.active_trial:
            raise ValueError("请先处理当前事件")
        if player.imprisonment:
            raise ValueError("身陷牢狱时无法渡劫飞升")
        if player.sealed_cultivation:
            raise ValueError("真实道果正受下界压制，不能在封印状态下飞升")
        if player.path not in {"dao", "buddhist", "confucian"}:
            raise ValueError("当前道统尚未开放飞升仙界路线")
        if player.world != "spirit" or player.realm_index != 8 or player.layer != REALMS[8].layers:
            raise ValueError("只有身处灵界且大乘九层圆满，方可渡劫飞升")
        if player.opportunity < opportunity_required(player):
            raise ValueError("大乘九层机缘尚未圆满")
        event_ids = [f"EVT_CELESTIAL_ASCENSION_{index:03d}" for index in range(1, 10)]
        rng = decode_rng(game.seed, game.rng_state)
        game.active_trial = {
            "kind":"celestial_ascension", "source_realm":8, "target_realm":9,
            "target_layer":1, "major":True, "old_label":public_player(player)["realm_name"],
            "step_index":0, "event_ids":event_ids, "lethal":True,
        }
        game.pending_event = self._instantiate_event(self.events_by_id[event_ids[0]], game, rng)
        game.history.append(HistoryRecord(
            "SYS_CELESTIAL_ASCENSION_BEGIN", 1, player.age, "渡劫飞升", None, "started",
            "你以大乘九层圆满道果叩问仙门；九重判定已经开始，其中第三、六、九关皆为仙雷。",
            {"trial_steps":9}, ["system", "ascension", "celestial", "milestone"],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def begin_asura_ascension(self, game_id: str) -> dict[str, Any]:
        """Start the nine-stage demonic ascension from the True Demon Realm."""
        game = self._load(game_id)
        player = game.player
        if not player.alive:
            raise ValueError("此生已经结束")
        if game.pending_event or game.active_trial:
            raise ValueError("请先处理当前事件")
        if player.imprisonment:
            raise ValueError("身陷牢狱时无法渡劫飞升")
        if player.sealed_cultivation:
            raise ValueError("真实道果正受下界压制，不能在封印状态下飞升")
        if player.path != "demonic":
            raise ValueError("只有魔修可以飞升修罗界")
        if player.world != "true_demon" or player.realm_index != 8 or player.layer != REALMS[8].layers:
            raise ValueError("只有身处真魔界且魔尊九层圆满，方可渡劫飞升")
        if player.opportunity < opportunity_required(player):
            raise ValueError("魔尊九层机缘尚未圆满")
        event_ids = [f"EVT_ASURA_ASCENSION_{index:03d}" for index in range(1, 10)]
        rng = decode_rng(game.seed, game.rng_state)
        game.active_trial = {
            "kind":"asura_ascension", "source_realm":8, "target_realm":9,
            "target_layer":1, "major":True, "old_label":public_player(player)["realm_name"],
            "step_index":0, "event_ids":event_ids, "lethal":True,
        }
        game.pending_event = self._instantiate_event(self.events_by_id[event_ids[0]], game, rng)
        game.history.append(HistoryRecord(
            "SYS_ASURA_ASCENSION_BEGIN", 1, player.age, "九重修罗天魔劫", None, "started",
            "你以魔尊九层圆满道果叩问修罗天关；九重判定已经开始，第三、六、九关皆为修罗兵雷。",
            {"trial_steps":9}, ["system", "ascension", "asura", "demonic", "milestone"],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def _complete_demonic_ascension(self, game: GameState) -> dict[str, Any]:
        """魔界路线直接渡界；飞升真魔界时必须承受魔气纯度判定。"""
        player = game.player
        if player.world == "human" and player.realm_index == 5 and player.layer >= 3:
            destination = "demon"
        elif player.world == "demon" and player.realm_index == 5 and player.layer >= 1:
            destination = "true_demon"
            required_qi = int(WORLD_SYSTEMS["demonic_cultivation"]["true_demon_ascension_demon_qi_level"])
            current_qi = qi_level(player.qi_experience.get("demon", 0.0))
            if current_qi < required_qi:
                self._die(
                    game,
                    f"魔气等级仅有 {current_qi} 级，未达飞升真魔界所需的 {required_qi} 级；肉身与元神在界壁魔潮中一同崩解",
                    "SYS_TRUE_DEMON_ASCENSION_QI_DEATH",
                )
                game.updated_at = now_iso()
                self.store.save(game)
                return self.present(game)
        else:
            raise ValueError("当前境界尚未触及下一魔界的飞升门槛")
        origin = player.world
        old_fame = player.fame
        lost_puppets = len(player.puppets)
        rng = decode_rng(game.seed, game.rng_state)
        companion_kept, friend_ids, friend_names, fallen_names = self._resolve_selected_ascension_entourage(
            game, destination, rng,
        )
        self._prepare_permanent_world_transition(
            game, keep_companion=companion_kept, keep_friend_ids=friend_ids,
        )
        player.world = destination
        player.location_id = self.maps.default_location(destination)
        player.awaiting_ascension = False
        player.awaiting_spirit_realm_crossing = False
        self._clear_market(game)
        self._ensure_market(game, rng)
        origin_name = WORLD_SYSTEMS["world_names"][origin]
        destination_name = WORLD_SYSTEMS["world_names"][destination]
        puppet_text = f" 受界壁排斥，{lost_puppets}具傀儡全部遗失。" if lost_puppets else ""
        entourage_text = (
            (f" 道侣与你一同抵达。" if companion_kept else "")
            + (f" 道友{'、'.join(friend_names)}成功同行。" if friend_names else "")
            + (f" 道友{'、'.join(fallen_names)}陨落于界壁。" if fallen_names else "")
        )
        game.history.append(HistoryRecord(
            "SYS_DEMONIC_ASCENSION", 1, player.age, f"飞升{destination_name}", destination, "ascended",
            f"你撕开{origin_name}界壁，降临{destination_name}。{puppet_text}{entourage_text}",
            {"world": [origin, destination], "lost_puppets": lost_puppets, "fame": [old_fame, 0]},
            ["system", "ascension", "demonic", "world:global"],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def cross_world(self, game_id: str, destination: str) -> dict[str, Any]:
        """Let Mahayana/Mozun cultivators visit their corresponding lower world."""
        game = self._load(game_id)
        player = game.player
        if not player.alive or game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法跨越界面")
        pairs = {
            "spirit": "human", "true_demon": "demon", "celestial": "spirit",
            "asura": "true_demon", "nether": "phantom_underworld", "hell": "human",
        }
        nether_lower_worlds = {"monster_realm", "phantom_underworld"}
        reverse_pairs = {lower: upper for upper, lower in pairs.items()}
        if destination not in {*pairs, *reverse_pairs, *nether_lower_worlds} or destination == player.world:
            raise ValueError("目标界面无效")
        travel_rules = WORLD_SYSTEMS["world_travel"]
        descending = bool(
            (player.world == "nether" and destination in nether_lower_worlds)
            or (player.world in pairs and destination == pairs[player.world])
        )
        if descending:
            upper_world, lower_world = player.world, destination
            if upper_world == "celestial" and not player.immortal_power_converted:
                raise ValueError("仙灵力尚未完全转化，无法承受逆行界壁的消耗")
            required_realm = int(
                travel_rules["celestial_required_realm"] if upper_world in {"celestial", "asura", "nether"}
                else travel_rules["required_realm"]
            )
            if player.realm_index < required_realm or player.sealed_cultivation:
                realm_name = "真仙" if upper_world == "celestial" else "迦楼罗" if upper_world == "asura" else "幽冥真灵" if upper_world == "nether" else "魔尊" if upper_world == "true_demon" else "大乘"
                raise ValueError(f"只有身处上界的{realm_name}修士才能重返对应下界")
            self._cancel_auction_for_world_change(game)
            player.sealed_cultivation = {
                "realm_index": player.realm_index,
                "layer": player.layer,
                "upper_world": upper_world,
                "lower_world": lower_world,
                "hp_ratio": player.hp / max(1.0, max_hp(player)),
                "mp_ratio": player.mp / max(1.0, max_mp(player)),
                "lifespan": player.lifespan,
                "tribulation_remaining": (
                    max(0, player.next_tribulation_age - player.age)
                    if player.next_tribulation_age is not None else None
                ),
            }
            player.world = lower_world
            player.location_id = self.maps.default_location(lower_world)
            player.realm_index = int(
                travel_rules["spirit_suppression_realm"] if upper_world in {"celestial", "asura", "nether"}
                else travel_rules["human_suppression_realm"]
            )
            player.layer = int(
                travel_rules["spirit_suppression_layer"] if upper_world in {"celestial", "asura", "nether"}
                else travel_rules["human_suppression_layer"]
            )
            player.awaiting_major_breakthrough = False
            player.awaiting_minor_breakthrough = False
            player.awaiting_spirit_realm_crossing = False
            player.active_breakthrough_aids = []
            player.hp = max_hp(player) * float(player.sealed_cultivation["hp_ratio"])
            player.mp = max_mp(player) * float(player.sealed_cultivation["mp_ratio"])
            player.party = []
            upper_realm = "仙境" if upper_world == "celestial" else "修罗道果" if upper_world == "asura" else "真灵道果" if upper_world == "nether" else "魔尊" if upper_world == "true_demon" else "大乘"
            lower_realm = "大乘九层" if lower_world in {"spirit", "monster_realm", "phantom_underworld"} else "魔尊九层" if lower_world == "true_demon" else "化魔初期三层" if lower_world == "demon" else "化神初期三层"
            summary = f"你逆穿界壁重返{WORLD_SYSTEMS['world_names'][lower_world]}。天地法则立刻压下，{upper_realm}修为被封至{lower_realm}，但真实道果仍在。"
            result = f"returned_{lower_world}"
        else:
            sealed = player.sealed_cultivation
            # 兼容旧存档：旧封印没有记录上下界时，按灵界—人界处理。
            expected_upper = str((sealed or {}).get("upper_world", reverse_pairs.get(player.world, "")))
            expected_lower = str((sealed or {}).get("lower_world", "human"))
            if not sealed or player.world != expected_lower or destination != expected_upper or int(sealed.get("realm_index", 0)) < 8:
                raise ValueError("你没有可在目标上界复原的封存道果")
            self._cancel_auction_for_world_change(game)
            hp_ratio = player.hp / max(1.0, max_hp(player))
            mp_ratio = player.mp / max(1.0, max_mp(player))
            player.world = expected_upper
            player.location_id = self.maps.default_location(expected_upper)
            player.realm_index = int(sealed["realm_index"])
            player.layer = int(sealed["layer"])
            player.lifespan = sealed.get("lifespan")
            remaining = sealed.get("tribulation_remaining")
            player.next_tribulation_age = player.age + int(remaining) if remaining is not None else None
            player.sealed_cultivation = None
            player.hp = max_hp(player) * hp_ratio
            player.mp = max_mp(player) * mp_ratio
            player.party = []
            true_realm = "仙境" if expected_upper == "celestial" else "修罗道果" if expected_upper == "asura" else "真灵道果" if expected_upper == "nether" else "魔尊" if expected_upper == "true_demon" else "大乘"
            summary = f"你再入{WORLD_SYSTEMS['world_names'][expected_upper]}，界面压制尽去，被封存的{true_realm}道果与法力层次完全复原。"
            result = f"returned_{expected_upper}"
        self._clear_market(game)
        game.history.append(HistoryRecord(
            "SYS_CROSS_WORLD", 1, player.age, "跨界往返", destination, result, summary,
            {"world": player.world, "cultivation_suppressed": bool(player.sealed_cultivation)},
            ["system", "world_crossing", "world:global"],
        ))
        rng = decode_rng(game.seed, game.rng_state)
        if descending:
            self._maybe_founder_return_event(game, rng)
        self._ensure_market(game, rng)
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def breakthrough(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not player.alive:
            raise ValueError("此生已经结束")
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        if player.imprisonment:
            raise ValueError("身陷牢狱时无法正常突破")
        if player.sealed_cultivation:
            raise ValueError("当前修为受下界法则压制，不能在封印状态下突破")
        if player.cultivation_suppression:
            raise ValueError("当前修为受秘法压制，解除压制后方可突破")
        current = realm(player)
        required = opportunity_required(player)
        breakthrough_kind = self._manual_breakthrough_kind(player)
        if not breakthrough_kind or player.opportunity < required:
            raise ValueError("尚未抵达需要手动突破的境界瓶颈")
        major = breakthrough_kind == "major"
        if major and player.path == "monster" and bloodline_content_available():
            raise ValueError("妖修大境界不进行概率冲关，请在【血脉】面板选择不可逆进化形态")
        if major and player.realm_index >= len(REALMS) - 1:
            raise ValueError("大乘之后的飞升体系尚未开放")
        requirement = self._major_breakthrough_requirement(player) if major else {"met": True, "reason": ""}
        if not requirement["met"]:
            raise ValueError(requirement["reason"])

        rng = decode_rng(game.seed, game.rng_state)
        old_label = public_player(player)["realm_name"]
        chance = self._breakthrough_chance(player, major=major)
        player.natal_origin_penalty = 0.0
        player.concubine_breakthrough_bonus = 0.0
        if player.path == "demonic":
            player.devouring_breakthrough_bonus = 0.0
        if major:
            player.awaiting_major_breakthrough = False
        else:
            player.awaiting_minor_breakthrough = False
        self._consume_breakthrough_aids(player, f"{'major' if major else 'minor'}:{player.realm_index}")
        if rng.random() >= chance["final"]:
            player.joint_companion_breakthrough = None
            failure_type = "major" if major else "minor"
            player.opportunity = required * float(WORLD_SYSTEMS["breakthrough"][f"{failure_type}_failure_retention"])
            gain = self._sage_scaled_gain(
                player, float(WORLD_SYSTEMS["breakthrough"][f"{failure_type}_failure_heart_demon"]),
                "heart_demon_gain_reduction",
            )
            player.heart_demon += gain
            target_index = player.realm_index + 1
            target_name = (
                WORLD_SYSTEMS.get("demonic_cultivation", {}).get("realm_names", {}).get(str(target_index), REALMS[target_index].name)
                if major and player.path == "demonic" else REALMS[target_index].name
                if major else self._minor_layer_target(player)
            )
            pity_gain = self._record_minor_pity_failure(player) if not major else 0
            game.history.append(HistoryRecord(
                "SYS_MAJOR_BREAKTHROUGH_FAILED" if major else "SYS_MINOR_BREAKTHROUGH_FAILED",
                1, player.age, "冲关失利", None, "failed",
                f"冲击{target_name}的基础关隘失败（成功率 {chance['final']:.1%}）；"
                f"你保住性命，但心魔 +{gain:g}。"
                + (f" 连续失败使下次基础成功率额外提高 {pity_gain:.0%}。" if pity_gain else ""),
                {"chance": chance, "heart_demon_gain": gain, "pity_bonus_next": pity_gain},
                ["system", "breakthrough", failure_type, "negative"],
            ))
        else:
            if not major:
                self._clear_minor_pity(player)
            companion = self._joint_companion_eligible(player)
            player.joint_companion_breakthrough = (
                {"id": companion["id"], "source_realm": player.realm_index, "source_layer": player.layer, "major": major}
                if companion else None
            )
            player.opportunity = max(0.0, player.opportunity - required)
            source = player.realm_index
            if major:
                if source >= 3:
                    kind = (
                        "heavenly_demon" if player.path == "demonic" and source >= 6
                        else "heavenly" if source >= 6 else "traditional"
                    )
                    self._start_breakthrough_trial(game, kind, source, source + 1, old_label, major=True, rng=rng)
                else:
                    self._complete_major_breakthrough(game, rng, old_label)
            elif source >= 6 and player.layer in {3, 6}:
                self._start_breakthrough_trial(game, "traditional", source, source, old_label, major=False, rng=rng)
            else:
                self._complete_minor_breakthrough(game, rng, old_label)
        game.updated_at = now_iso()
        self._enforce_guixu_rank_boundary(game, "breakthrough")
        self._ensure_market(game, rng)
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    @staticmethod
    def _body_progress_required(player: Player) -> float:
        config = WORLD_SYSTEMS["body_cultivation"]
        return float(config["progress_base"]) + player.body_training * float(config["progress_per_layer"])

    @staticmethod
    def _body_pity_key(player: Player) -> str:
        return f"body:{player.body_training + 1}"

    def _body_breakthrough_chance(self, player: Player) -> dict[str, float]:
        config = WORLD_SYSTEMS["body_cultivation"]
        target = player.body_training + 1
        ranges = config["base_chance"]
        base = next(
            float(chance) for span, chance in ranges.items()
            if int(span.split("-", 1)[0]) <= target <= int(span.split("-", 1)[1])
        )
        technique_bonus = 0.0
        if player.body_technique and target <= int(player.body_technique.body_bonus_max_layer or 0):
            technique_bonus = (
                float(player.body_technique.body_breakthrough_bonus)
                * player.body_technique.level_multiplier
            )
        failures = int(player.body_breakthrough_pity.get(self._body_pity_key(player), 0))
        pity_bonus = 0.0
        if target >= int(config["pity_start_target"]):
            pity_bonus = min(
                float(config["pity_max_bonus"]),
                failures * float(config["pity_bonus_per_failure"]),
            )
        final = min(0.98, base + technique_bonus + pity_bonus)
        return {
            "base":base, "technique_bonus":technique_bonus, "pity_bonus":pity_bonus,
            "failures":failures, "final":final,
        }

    def body_breakthrough(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not player.alive or game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法冲击炼体境界")
        if player.body_technique is None:
            raise ValueError("必须先配置一部炼体功法")
        maximum = int(WORLD_SYSTEMS["body_cultivation"]["max_layer"])
        required = self._body_progress_required(player)
        if player.body_training >= maximum:
            raise ValueError("炼体已经达到一百层极限")
        if not player.awaiting_body_breakthrough or player.body_progress < required:
            raise ValueError("炼体积累尚未圆满")
        rng = decode_rng(game.seed, game.rng_state)
        chance = self._body_breakthrough_chance(player)
        target = player.body_training + 1
        key = self._body_pity_key(player)
        if rng.random() >= chance["final"]:
            player.body_progress = required * float(WORLD_SYSTEMS["body_cultivation"]["failure_retention"])
            player.awaiting_body_breakthrough = False
            if target >= int(WORLD_SYSTEMS["body_cultivation"]["pity_start_target"]):
                player.body_breakthrough_pity[key] = int(player.body_breakthrough_pity.get(key, 0)) + 1
            next_chance = self._body_breakthrough_chance(player)
            result = "failed"
            summary = (
                f"冲击炼体{target}层失败（成功率 {chance['final']:.1%}），保留七成积累。"
                + (f" 此层累计失败 {next_chance['failures']} 次，下次保底 +{next_chance['pity_bonus']:.1%}。" if target >= 21 else "")
            )
        else:
            old = player.body_training
            player.body_training = target
            grant_intrinsic_growth(player, hp=12.0)
            player.body_progress = 0.0
            player.awaiting_body_breakthrough = False
            player.body_breakthrough_pity.pop(key, None)
            player.hp = max_hp(player)
            reduction = self._body_tribulation_damage_reduction(player)
            result = "success"
            summary = f"你将肉身由炼体{old}层锤炼至{target}层，气血完全恢复。"
            if target % 20 == 0:
                summary += " 此后修仙大小境界的基础成功率永久增加1个百分点。"
            if target >= 50 and target % 5 == 0:
                summary += f" 肉身对雷劫与天劫的累计减伤提升至{reduction:.1%}。"
        game.history.append(HistoryRecord(
            "SYS_BODY_BREAKTHROUGH", 1, player.age, "肉身破境", str(target), result, summary,
            {"target_layer":target,"chance":chance,"body_training":player.body_training},
            ["system","body_training","breakthrough",result],
        ))
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def divine_sense_breakthrough(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not player.alive or game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法突破神识")
        if player.divine_sense_technique is None:
            raise ValueError("必须先配置一部神识功法")
        cost = divine_sense_breakthrough_cost(player)
        if player.divine_sense_experience < cost:
            raise ValueError("神识经验尚未达到手动突破要求")
        old_level = divine_sense_level(player)
        player.divine_sense_experience -= cost
        player.divine_sense_rank = old_level + 1
        game.history.append(HistoryRecord(
            "SYS_DIVINE_SENSE_BREAKTHROUGH", 1, player.age, "神识破境", str(old_level + 1), "success",
            f"你消耗 {cost:.0f} 神识经验，将神识由 {old_level} 级突破至 {old_level + 1} 级；多余经验完整保留。",
            {"level":[old_level, old_level + 1], "experience_cost":cost},
            ["system", "divine_sense", "breakthrough"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def set_world_news_debug(self, game_id: str, enabled: bool) -> dict[str, Any]:
        """Debug only changes what the chronology exposes; simulation remains global."""
        game = self._load(game_id)
        game.debug_world_news = bool(enabled)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def create_faction(self, game_id: str, name: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        clean_name = name.strip()[:18]
        if not clean_name:
            raise ValueError("请为新宗门题名")
        if game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法开宗立派")
        if player.faction_id:
            raise ValueError("你已有宗门归属，不能同时另立山门")
        if any(sect.name == clean_name and not sect.extinct for sect in game.sects.values()):
            raise ValueError("此宗门名号已经存在")
        sect_id = f"player_sect_{game.id.replace('-', '')[:10]}"
        path = player.technique.path if player.technique else player.path
        sect = SectState(
            sect_id, clean_name, player.world, [],
            description=f"由{player.name}于{player.age}岁开创的宗门。", path=path,
            founded_by_player=True, founder_player_id=game.id,
            allegiance_race=player.allegiance_race or player.race,
        )
        rng = decode_rng(game.seed, game.rng_state)
        for index in range(int(WORLD_SYSTEMS["player_faction"]["initial_followers"])):
            realm_index = 0 if player.realm_index == 0 else max(1, player.realm_index - 1)
            layer = 1 if realm_index == 0 else rng.randint(1, min(REALMS[realm_index].layers, 3))
            age, lifespan = self._roll_recruit_age_lifespan(realm_index, path, rng, young=True)
            npc = SectNpc(
                f"{sect_id}_founder_{index}", rng.choice(["沈砚", "叶舟", "顾青", "陆遥", "白川", "楚宁"]),
                "开山门人", realm_index, layer, age, lifespan,
                spirit_root=self._random_npc_root(realm_index, rng) if realm_index else "none",
                path=path, race=player.race, world=player.world, affinity=rng.uniform(28, 48),
            )
            npc.treasure_item_id = self._select_npc_treasure(npc, rng)
            sect.npcs.append(npc)
        game.sects[sect_id] = sect
        player.faction_id = sect_id
        player.allegiance_race = sect.allegiance_race
        player.faction_join_age = player.age
        player.faction_contribution = 0
        self._ensure_sect_relations(game)
        threshold = self._governance_threshold(player.world)
        pressured = player.realm_index < threshold
        summary = (
            f"你立下{clean_name}山门。当前修为低于本界公认的立派底线，周边势力已经开始排挤试探。"
            if pressured else f"你立下{clean_name}山门，各方承认了这座新势力的存在。"
        )
        game.history.append(HistoryRecord(
            "SYS_FOUND_FACTION", 1, player.age, "开宗立派", sect_id, "founded", summary,
            {"faction_id": sect_id, "under_pressure": pressured},
            ["system", "faction", "founding", f"world:{player.world}"],
        ))
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def create_family(self, game_id: str, name: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        clean_name = name.strip()[:18]
        if not clean_name:
            raise ValueError("请为修仙家族题名")
        if game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法建立家族")
        if game.family and not game.family.extinct:
            raise ValueError("你已经建立修仙家族")
        heirs = [child for child in player.offspring if child.get("alive", True) and child.get("cultivation_started")]
        if not heirs:
            raise ValueError("至少要有一名拥有灵根并已经踏入仙途的后代，才能建立修仙家族")
        family_id = f"family_{game.id.replace('-', '')[:10]}"
        family = SectState(
            family_id, clean_name, player.world, [],
            description=f"由{player.name}与后代共同建立的修仙家族，亦接纳外姓门人。",
            path=player.technique.path if player.technique else player.path,
            founded_by_player=True, founder_player_id=game.id,
            allegiance_race=self._player_allegiance_race(player),
        )
        for child in heirs:
            root = str(child.get("spirit_root", "none"))
            npc = SectNpc(
                str(child["id"]), str(child["name"]), "嫡系后人", int(child.get("realm_index", 1)),
                int(child.get("layer", 1)), int(child.get("age", 8)), child.get("lifespan"),
                spirit_root=root, path=str(child.get("path", family.path)), race=player.race,
                world=player.world, affinity=60.0,
                gender=str(child.get("gender") or self._stable_gender(str(child.get("id", "")))),
            )
            family.npcs.append(npc)
        game.family = family
        game.history.append(HistoryRecord(
            "SYS_FOUND_FAMILY", 1, player.age, "仙族初立", family_id, "founded",
            f"你以{clean_name}为号建立修仙家族，{len(heirs)}名踏入仙途的后代列入族谱，山门同时向外姓低阶修士开放。",
            {"family_id": family_id, "heirs": [child["id"] for child in heirs]},
            ["system", "family", "founding", f"world:{player.world}"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    @staticmethod
    def _vote_probability(current_affinity: float, requested_status: str, voter_affinity: float = 0.0) -> float:
        if requested_status == "war":
            base = 0.48 - current_affinity / 220
        elif requested_status in {"alliance", "vassal"}:
            base = 0.48 + current_affinity / 220
        elif requested_status == "truce":
            base = 0.68 if current_affinity < 0 else 0.48
        else:
            base = 0.56
        return max(0.08, min(0.92, base + voter_affinity / 500))

    def propose_race_diplomacy(self, game_id: str, target_race: str, status: str) -> dict[str, Any]:
        if self._intrigue_enabled():
            resolution_type = {"war": "declare_war", "alliance": "form_alliance", "truce": "make_peace", "neutral": "break_alliance"}.get(status)
            if resolution_type:
                return self.intrigue_propose_resolution(game_id, "race", resolution_type, target_race, True)
        game = self._load(game_id)
        player = game.player
        if game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法召开族议")
        if not self._has_race_voice(game):
            raise ValueError("只有身处种族上界的人族大乘才能发起人族外交表决")
        current_world = player.world
        if target_race == "human" or target_race not in RACE_DEFINITIONS or current_world not in RACE_DEFINITIONS[target_race].get("worlds", []):
            raise ValueError("目标种族无效")
        if status not in {"war", "alliance", "truce", "neutral", "vassal"}:
            raise ValueError("未知外交决议")
        key = race_pair("human", target_race)
        relation = game.race_relations.setdefault(key, {"affinity": 0.0, "status": "neutral", "since_age": player.age})
        if relation.get("status") == "war" and status != "war":
            raise ValueError("战争已经进入征伐阶段，请在战争窗口依据战果进行和谈")
        voters: dict[str, SectNpc] = {}
        for npc in [*game.world_npcs.values(), *game.notable_npcs.values(), *(n for s in game.sects.values() for n in s.npcs)]:
            if npc.alive and npc.world == current_world and npc.race == "human" and npc.realm_index >= 8:
                voters[npc.id] = npc
        rng = decode_rng(game.seed, game.rng_state)
        ballots = [{"name": player.name, "vote": True, "player": True}]
        for npc in voters.values():
            chance = self._vote_probability(float(relation.get("affinity", 0)), status, float(npc.affinity or 0))
            ballots.append({"name": npc.name, "vote": rng.random() < chance, "chance": round(chance, 3), "player": False})
        yes = sum(bool(ballot["vote"]) for ballot in ballots)
        passed = yes > len(ballots) / 2
        old_status = str(relation.get("status", "neutral"))
        if passed:
            affinity = {"war": -75, "alliance": 80, "truce": -5, "neutral": 0, "vassal": 65}[status]
            self._set_diplomatic_relation(game, relation, status, "human", target_race, "race", affinity)
        relation["last_vote"] = {"age": player.age, "proposal": status, "yes": yes, "total": len(ballots), "passed": passed, "ballots": ballots}
        action_name = {"war":"宣战","alliance":"结盟","truce":"停战","neutral":"恢复中立","vassal":"确立依附"}[status]
        target_name = RACE_DEFINITIONS[target_race]["name"]
        summary = f"你提议人族与{target_name}{action_name}；{yes}/{len(ballots)}票赞成，决议{'通过' if passed else '未通过'}。"
        game.history.append(HistoryRecord(
            "SYS_PLAYER_RACE_VOTE", 1, player.age, "人族大乘议会", status, "passed" if passed else "rejected",
            summary, {"races":["human", target_race], "status":[old_status, relation.get("status")], "vote":relation["last_vote"]},
            ["system", "diplomacy", "race", "vote", "world_news", f"world:{current_world}"],
        ))
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def propose_sect_diplomacy(self, game_id: str, target_faction: str, status: str) -> dict[str, Any]:
        if self._intrigue_enabled():
            resolution_type = {"war": "declare_war", "alliance": "form_alliance", "truce": "make_peace", "neutral": "break_alliance"}.get(status)
            if resolution_type:
                return self.intrigue_propose_resolution(game_id, "sect", resolution_type, target_faction, True)
        game = self._load(game_id)
        player = game.player
        if game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法召开宗门议事")
        if not self._has_sect_voice(game):
            raise ValueError("你尚未取得当前宗门的外交话语权")
        own = game.sects[player.faction_id]
        target = game.sects.get(target_faction)
        if not target or target.extinct or target.id == own.id or target.world != own.world:
            raise ValueError("目标宗门无效")
        if status not in {"war", "alliance", "truce", "neutral", "vassal"}:
            raise ValueError("未知外交决议")
        self._ensure_sect_relations(game)
        key = race_pair(own.id, target.id)
        relation = game.sect_relations.setdefault(key, {"affinity":0.0,"status":"neutral","since_age":player.age})
        if relation.get("status") == "war" and status != "war":
            raise ValueError("战争已经进入征伐阶段，请在战争窗口依据战果进行和谈")
        threshold = self._governance_threshold(own.world)
        voters = [npc for npc in own.npcs if npc.alive and npc.world == own.world and npc.realm_index >= threshold]
        rng = decode_rng(game.seed, game.rng_state)
        ballots = [{"name":player.name,"vote":True,"player":True}]
        for npc in voters:
            chance = self._vote_probability(float(relation.get("affinity", 0)), status, float(npc.affinity or 0))
            ballots.append({"name":npc.name,"vote":rng.random() < chance,"chance":round(chance,3),"player":False})
        yes = sum(bool(ballot["vote"]) for ballot in ballots)
        passed = yes > len(ballots) / 2
        old_status = str(relation.get("status", "neutral"))
        if passed:
            self._set_diplomatic_relation(
                game, relation, status, own.id, target.id, "sect",
                float({"war":-75,"alliance":80,"truce":-5,"neutral":0,"vassal":65}[status]),
            )
        relation["last_vote"] = {"age":player.age,"proposal":status,"yes":yes,"total":len(ballots),"passed":passed,"ballots":ballots}
        action_name = {"war":"宣战","alliance":"结盟","truce":"停战","neutral":"恢复中立","vassal":"确立依附"}[status]
        summary = f"你提议{own.name}与{target.name}{action_name}；{yes}/{len(ballots)}票赞成，决议{'通过' if passed else '未通过'}。"
        game.history.append(HistoryRecord(
            "SYS_PLAYER_SECT_VOTE",1,player.age,"宗门外交议事",status,"passed" if passed else "rejected",summary,
            {"sects":[own.id,target.id],"status":[old_status,relation.get("status")],"vote":relation["last_vote"]},
            ["system","diplomacy","faction","vote","world_news",f"world:{player.world}"],
        ))
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def transfer_vassal_personnel(
        self, game_id: str, kind: str, target_id: str, npc_id: str,
    ) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法调动人事")
        if kind not in {"race", "sect"}:
            raise ValueError("未知势力类型")
        own_id = self._player_allegiance_race(player) if kind == "race" else player.faction_id
        if not own_id or (kind == "race" and not self._has_race_voice(game)) or (kind == "sect" and not self._has_sect_voice(game)):
            raise ValueError("你尚未取得该势力的话语权")
        relations = game.race_relations if kind == "race" else game.sect_relations
        relation = relations.get(race_pair(str(own_id), target_id), {})
        if relation.get("status") != "vassal" or relation.get("overlord") != own_id or relation.get("subject") != target_id:
            raise ValueError("只有被依附方可以从附庸势力调动同级以下人事")
        source_sect: SectState | None = None
        if kind == "sect":
            source_sect = game.sects.get(target_id)
            candidates = list(source_sect.npcs) if source_sect else []
        else:
            candidates = []
            for sect in game.sects.values():
                for npc in sect.npcs:
                    if npc.race == target_id:
                        candidates.append(npc)
                        if npc.id == npc_id:
                            source_sect = sect
        npc = next((row for row in candidates if row.id == npc_id and row.alive and row.world == player.world), None)
        player_rank = self._actual_player_realm(player)
        if not npc or (npc.realm_index, npc.layer) > player_rank:
            raise ValueError("只能调动当前界面内、修为不高于你的附庸修士")
        if source_sect:
            source_sect.npcs = [row for row in source_sect.npcs if row.id != npc.id]
            self._check_sect_extinction(game, source_sect)
        npc.title = "附庸外援"
        if kind == "sect":
            destination = game.sects[str(own_id)]
            npc.faction_id = destination.id
            destination.npcs.append(npc)
            destination_name = destination.name
        else:
            npc.faction_id = f"race_support:{own_id}"
            game.notable_npcs[npc.id] = npc
            destination_name = RACE_DEFINITIONS[str(own_id)]["name"]
        summary = f"你以被依附方的名义，将{npc.name}从{self._power_name(game, kind, target_id)}调为{destination_name}外援。"
        game.history.append(HistoryRecord(
            "SYS_VASSAL_TRANSFER", 1, player.age, "附庸人事调动", npc.id, "transferred", summary,
            {"kind":kind,"overlord":own_id,"subject":target_id,"npc_id":npc.id},
            ["system","diplomacy","vassal","personnel",f"world:{player.world}"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _power_name(self, game: GameState, kind: str, entity_id: str) -> str:
        if kind == "race":
            return RACE_DEFINITIONS.get(entity_id, {"name":entity_id})["name"]
        return game.sects.get(entity_id, SectState(entity_id, entity_id)).name

    @staticmethod
    def _player_allegiance_race(player: Player) -> str:
        return str(player.allegiance_race or player.lineage_race or player.race)

    def _available_bounty_authorities(self, game: GameState) -> list[dict[str, str]]:
        authorities: list[dict[str, str]] = []
        if self._has_race_voice(game):
            race_id = self._player_allegiance_race(game.player)
            race_name = RACE_DEFINITIONS.get(race_id, {"name":race_id})["name"]
            authorities.append({"id":"race","name":f"{race_name}大乘议会"})
        if self._has_sect_voice(game):
            sect = game.sects[game.player.faction_id]
            authorities.append({"id":"sect","name":sect.name})
        if self._has_family_voice(game):
            authorities.append({"id":"family","name":game.family.name})
        return authorities

    def issue_bounty(self, game_id: str, npc_id: str, authority: str = "") -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法颁布通缉令")
        authorities = self._available_bounty_authorities(game)
        if not authorities:
            raise ValueError("至少取得种族、宗门或家族其中一方的话语权，才能颁布通缉令")
        authority_row = next((row for row in authorities if row["id"] == authority), None)
        if authority and not authority_row:
            raise ValueError("你尚未掌握所选势力的通缉权")
        authority_row = authority_row or authorities[0]
        if any(row.get("target_id") == npc_id and row.get("status") == "active" for row in game.player_bounties):
            raise ValueError("此人已经在你的通缉令上")
        npc = game.world_npcs.get(npc_id) or game.notable_npcs.get(npc_id)
        if not npc:
            npc = self._promote_cached_npc(game, npc_id, "被玩家颁布通缉令")
        if not npc or not npc.alive or npc.world != player.world:
            raise ValueError("只能通缉当前界面的固定人物或缓存人物")
        bounty = {
            "id":f"bounty_{player.age}_{len(game.player_bounties)}", "target_id":npc.id,
            "name":npc.name, "world":npc.world, "status":"active", "issued_age":player.age,
            "attempts":0, "target_power":round(self._npc_power(npc),1),
            "authority":authority_row["id"], "issuer_name":authority_row["name"],
        }
        game.player_bounties.append(bounty)
        game.history.append(HistoryRecord(
            "SYS_PLAYER_BOUNTY",1,player.age,"三权通缉令",npc.id,"issued",
            f"你以{authority_row['name']}的名义通缉{npc.name}。",
            {"bounty":copy.deepcopy(bounty)},["system","wanted","player_order",f"world:{player.world}"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def intercept_faction_npc(self, game_id: str, npc_id: str) -> dict[str, Any]:
        """Explicitly attack a member shown in the player's current faction roster."""
        game = self._load(game_id)
        player = game.player
        if not player.alive or game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法截杀宗门修士")
        sect = game.sects.get(player.faction_id or "")
        if not sect or sect.extinct or sect.world != player.world:
            raise ValueError("当前没有可供截杀的宗门名册")
        npc = next(
            (row for row in self._sect_members(game, sect) if row.id == npc_id and row.alive and row.world == player.world),
            None,
        )
        if not npc:
            raise ValueError("目标已不在当前宗门名册中")
        rng = decode_rng(game.seed, game.rng_state)
        power = self._npc_power(npc)
        race = RACE_DEFINITIONS.get(npc.race, RACE_DEFINITIONS["human"])
        target = {
            "target_name":npc.name, "target_power":power, "primary_power":power,
            "target_realm_index":npc.realm_index, "target_layer":npc.layer,
            "target_realm_visible":True, "target_realm_display":self._npc_realm_name(npc),
            "combat_type":"cultivator", "race":npc.race, "race_name":race["name"],
            "race_description":race["description"], "world":npc.world, "npc_id":npc.id,
            "faction_id":sect.id, "path":npc.path, "treasure_item_id":npc.treasure_item_id,
            "kill_karma":True, "action":"slay", "non_story_combat":True,
        }
        result, summary = self._combat(game, target, True, rng)
        summary = self._apply_combat_action_rewards(game, "slay", result, summary, rng)
        game.history.append(HistoryRecord(
            "SYS_FACTION_INTERCEPT", 1, player.age, "宗门截杀", npc.id, result, summary,
            {"npc_id":npc.id, "faction_id":sect.id},
            ["system","combat","slay","faction","intercept",f"world:{player.world}"],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def use_item(self, game_id: str, item_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        item = ITEM_CATALOG.get(item_id)
        if not item or not has_item(game.player, item_id):
            raise ValueError("物品不存在")
        if game.player.cultivation_suppression and item.breakthrough_bonus > 0:
            raise ValueError("压制修为期间不能服用突破丹药")
        if ghost_cultivation_active(game.player) and item.breakthrough_bonus > 0:
            scope_type = str(item.breakthrough_scope or "").split(":", 1)[0]
            if game.player.realm_index < 4:
                raise ValueError("凝婴入体前，阴魂无法承受突破丹药；达到元婴期后方可服用当前境界适用的小境界丹药。")
            if scope_type == "major" and game.player.realm_index < 6:
                raise ValueError("炼虚以前魂婴尚不能借丹药跨越大境界；达到炼虚期后方可服用当前境界适用的大境界丹药。")
        if game.pending_event:
            if not game.active_trial or (item.trial_restore_hp <= 0 and item.trial_restore_mp <= 0):
                raise ValueError("当前事件中只能使用渡劫恢复道具")
            remove_item(game.player, item_id)
            hp_gain = max_hp(game.player) * float(item.trial_restore_hp)
            mp_gain = max_mp(game.player) * float(item.trial_restore_mp)
            game.player.hp = min(max_hp(game.player), game.player.hp + hp_gain)
            game.player.mp = min(max_mp(game.player), game.player.mp + mp_gain)
            game.history.append(HistoryRecord(
                "SYS_TRIAL_RECOVERY", 1, game.player.age, "劫中服药", item_id, "recovered",
                f"你在劫隙中使用{item.name}，恢复 HP {hp_gain:.0f}、MP {mp_gain:.0f}。",
                {"hp_gain": hp_gain, "mp_gain": mp_gain}, ["system", "item", "tribulation"],
            ))
        elif item.conception_bonus > 0:
            companion = game.player.dao_companion
            if not companion or not companion.get("alive", True):
                raise ValueError("须先有一位仍在世的道侣，才能服用此类孕育丹药")
            if game.player.next_companion_conception_bonus > 0:
                raise ValueError("下一次缠绵的孕育药力尚未消散，不能重复服用")
            remove_item(game.player, item_id)
            bonus = min(0.95, float(item.conception_bonus))
            game.player.next_companion_conception_bonus = bonus
            game.history.append(HistoryRecord(
                "SYS_USE_CONCEPTION_PILL", 1, game.player.age, "服丹蕴嗣", item_id, "activated",
                f"你服下{item.name}，下一次与道侣缠绵时的孕育概率 +{bonus:.0%}。",
                {"bonus": bonus}, ["system", "item", "family", "offspring"],
            ))
        elif item.permanent_intrinsic_hp_bonus > 0 or item.permanent_intrinsic_mp_bonus > 0:
            player = game.player
            ensure_ghost_cultivation_state(player)
            hp_gain = max(0.0, float(item.permanent_intrinsic_hp_bonus))
            mp_gain = max(0.0, float(item.permanent_intrinsic_mp_bonus))
            remove_item(player, item_id)
            player.permanent_intrinsic_hp_bonus += hp_gain
            player.permanent_intrinsic_mp_bonus += mp_gain
            grant_intrinsic_growth(player, hp_gain, mp_gain)
            game.history.append(HistoryRecord(
                "SYS_USE_PERMANENT_INTRINSIC_PILL", 1, player.age, "本源新生", item_id, "strengthened",
                f"你服下{item.name}，永久获得本体 HP +{hp_gain:g}、MP +{mp_gain:g}；既有魂蚀损失没有恢复。",
                {"intrinsic_hp_gain": hp_gain, "intrinsic_mp_gain": mp_gain},
                ["system", "item", "pill", "intrinsic", "permanent"],
            ))
        elif "guixu_consumable" in item.tags:
            remove_item(game.player, item_id)
            potency = max(1, int(item_id.rsplit("_", 1)[-1]))
            hp_gain = max_hp(game.player) * min(.55, .18 + potency * .035)
            mp_gain = max_mp(game.player) * min(.55, .18 + potency * .035)
            opportunity_gain = REALMS[game.player.realm_index].opportunity_base * (.20 + potency * .04)
            game.player.hp = min(max_hp(game.player), game.player.hp + hp_gain)
            game.player.mp = min(max_mp(game.player), game.player.mp + mp_gain)
            self._add_opportunity(game.player, opportunity_gain)
            game.history.append(HistoryRecord(
                "SYS_USE_GUIXU_CONSUMABLE", 1, game.player.age, "服用归墟奇物", item_id, "consumed",
                f"你使用{item.name}，恢复 HP {hp_gain:.0f}、MP {mp_gain:.0f}，并获得机缘 {opportunity_gain:.1f}。",
                {"hp_gain": round(hp_gain, 1), "mp_gain": round(mp_gain, 1),
                 "opportunity_gain": round(opportunity_gain, 1)},
                ["system", "item", "guixu", "consumable"],
            ))
        elif "guixu_tide" in item.tags and "spirit_plant" in item.tags:
            remove_item(game.player, item_id)
            potency = max(1.0, math.log10(max(10.0, float(item.plant_value or 10))))
            hp_gain = max_hp(game.player) * min(.45, .08 + potency * .04)
            mp_gain = max_mp(game.player) * min(.45, .08 + potency * .04)
            opportunity_gain = REALMS[game.player.realm_index].opportunity_base * min(.90, .10 + potency * .06)
            game.player.hp = min(max_hp(game.player), game.player.hp + hp_gain)
            game.player.mp = min(max_mp(game.player), game.player.mp + mp_gain)
            self._add_opportunity(game.player, opportunity_gain)
            game.history.append(HistoryRecord(
                "SYS_REFINE_GUIXU_PLANT", 1, game.player.age, "炼化归墟灵植", item_id, "refined",
                f"你炼化{item.name}，恢复 HP {hp_gain:.0f}、MP {mp_gain:.0f}，并获得机缘 {opportunity_gain:.1f}。",
                {"hp_gain": round(hp_gain, 1), "mp_gain": round(mp_gain, 1),
                 "opportunity_gain": round(opportunity_gain, 1)},
                ["system", "item", "guixu", "spirit_plant"],
            ))
        elif item.breakthrough_bonus > 0 and item.breakthrough_scope:
            if game.player.path == "demonic":
                raise ValueError("魔修不能依靠突破丹药提高自身突破率；可将丹药用于培养傀儡或弟子")
            scope_type, source_text = item.breakthrough_scope.split(":", 1)
            if game.player.path == "monster" and scope_type == "major" and bloodline_content_available():
                raise ValueError("妖修大境界由血脉条件与生命经历决定，突破丹药不会开启进化路线")
            if int(source_text) != game.player.realm_index:
                raise ValueError("这枚丹药不适用于当前境界")
            if scope_type == "major" and game.player.layer < realm(game.player).layers:
                raise ValueError("尚未抵达大境界瓶颈，不能提前服用此丹")
            if scope_type == "minor" and not (
                game.player.awaiting_minor_breakthrough
                and game.player.layer in self._manual_minor_layers(game.player)
                and game.player.opportunity >= opportunity_required(game.player)
            ):
                raise ValueError("此丹须在初期或中期圆满、停留小境界瓶颈时服用")
            if item_id in game.player.active_breakthrough_aids:
                raise ValueError("本次冲关已经服用过同一种丹药")
            remove_item(game.player, item_id)
            game.player.active_breakthrough_aids.append(item_id)
            game.history.append(HistoryRecord(
                "SYS_USE_BREAKTHROUGH_PILL", 1, game.player.age, "服丹备关", item_id, "activated",
                f"你服下{item.name}，下次对应突破成功率 +{item.breakthrough_bonus:.0%}。",
                {"scope": item.breakthrough_scope, "bonus": item.breakthrough_bonus}, ["system", "item", "breakthrough"],
            ))
        elif item_id.startswith(("jinque_", "zique_", "moque_", "yaoque_", "mingque_")):
            is_zique = item_id.startswith("zique_")
            is_moque = item_id.startswith("moque_")
            is_yaoque = item_id.startswith("yaoque_")
            is_mingque = item_id.startswith("mingque_")
            if is_zique and (game.player.world != "spirit" or game.player.realm_index < 5):
                raise ValueError("紫阙玉书须在灵界达到化神期后方能参悟")
            if is_moque and (game.player.world != "true_demon" or game.player.realm_index < 5):
                raise ValueError("魔阙须在真魔界达到化魔期后方能参悟")
            if is_yaoque and (game.player.world not in {"monster_realm", "phantom_underworld"} or game.player.realm_index < 5):
                raise ValueError("妖阙骨书须在妖界或幻冥界达到化神期后方能参悟")
            if is_mingque and (game.player.world != "hell" or game.player.realm_index < 5):
                raise ValueError("冥阙魂书须在地狱界达到化神期后方能参悟")
            if not any((is_zique, is_moque, is_yaoque, is_mingque)) and game.player.realm_index < 4:
                raise ValueError("上面记载的法门或者材料不是你现阶段能集齐的")
            affinity = item.root_grant
            if affinity in game.player.additional_roots or affinity in self._base_affinities(game.player):
                raise ValueError("你已经拥有对应灵根")
            remove_item(game.player, item_id)
            game.player.additional_roots.append(str(affinity))
            summary = f"你依《{item.name}》补全了{TECHNIQUE_ELEMENT_NAMES[str(affinity)]}灵根；原有灵根效率保持不变。"
            game.history.append(HistoryRecord(
                (
                    "SYS_USE_MOQUE" if is_moque else "SYS_USE_ZIQUE" if is_zique
                    else "SYS_USE_YAOQUE" if is_yaoque else "SYS_USE_MINGQUE" if is_mingque
                    else "SYS_USE_JINQUE"
                ), 1, game.player.age,
                (
                    "魔阙补灵" if is_moque else "紫阙补灵" if is_zique
                    else "妖阙补灵" if is_yaoque else "冥阙补灵" if is_mingque
                    else "补全天缺"
                ), item_id, "root_added", summary,
                {"additional_root": affinity}, ["system", "item", "root"],
            ))
        elif item_id == "healing_pill" and remove_item(game.player, item_id):
            restored = max_hp(game.player) * 0.35
            game.player.hp = min(max_hp(game.player), game.player.hp + restored)
            game.history.append(HistoryRecord(
                "SYS_USE_ITEM", 1, game.player.age, "服用丹药", item_id, "healed",
                f"服下回春丹，恢复了 {restored:.0f} 点 HP。", {"hp": round(restored, 1)}, ["system", "item"],
            ))
        else:
            raise ValueError("该物品当前不能使用")
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def buy_market_offer(self, game_id: str, offer_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        if game.player.realm_index == 0:
            raise ValueError("凡人无法进入修仙坊市")
        offer = next((entry for entry in game.market_offers if entry["id"] == offer_id), None)
        if not offer or offer.get("sold"):
            raise ValueError("该货物已经售出或不在本期坊市")
        if offer.get("world", "human") != game.player.world:
            raise ValueError("此物不属于当前世界的坊市货池")
        price = int(offer["price"])
        if not remove_item(game.player, "spirit_stone", price):
            raise ValueError(f"需要 {price} 枚下品灵石")
        if offer["kind"] == "crafting_material":
            summary = self._buy_crafting_material_offer(game, offer, price)
        elif offer["kind"] == "formation_material":
            summary = self._buy_formation_material_offer(game, offer, price)
        elif offer["kind"] == "formation_supply":
            summary = self._buy_formation_supply_offer(game, offer, price)
        elif offer["kind"] == "item":
            add_item(game.player, offer["content_id"])
            summary = f"你在{offer['market_name']}支付 {price} 枚灵石，购得{offer['name']}。"
        else:
            learned = acquire_technique(game.player, TECHNIQUE_CATALOG[offer["content_id"]])
            destination = "已悟功法" if learned else "包裹，可用于升级"
            summary = f"你在{offer['market_name']}支付 {price} 枚灵石，购得《{offer['name']}》传承玉简，收入{destination}。"
        offer["sold"] = True
        offer["locked"] = False
        game.history.append(HistoryRecord(
            "SYS_MARKET_BUY", 1, game.player.age, "坊市交易", offer_id, "purchased", summary,
            {"spirit_stone": -price, "content_id": offer["content_id"]}, ["system", "market"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def equip_known_technique(self, game_id: str, technique_id: str, slot: str) -> dict[str, Any]:
        game = self._load(game_id)
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        known = next((technique for technique in game.player.known_techniques if technique.id == technique_id), None)
        if not known:
            raise ValueError("你尚未掌握这部功法")
        assign_technique(game.player, copy.deepcopy(known), slot)
        slot_name = {
            "main": "主修", "support": "辅修", "combat": "战斗", "body": "炼体",
            "divine_sense": "神识", "transformation": "变身",
        }.get(slot)
        if not slot_name:
            raise ValueError("未知功法槽位")
        game.history.append(HistoryRecord(
            "SYS_EQUIP_KNOWN_TECHNIQUE", 1, game.player.age, "重整功法", technique_id, "equipped",
            f"你将《{known.name}》配置为{slot_name}功法。", {"slot": slot, "technique_id": technique_id},
            ["system", "technique"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def upgrade_technique(self, game_id: str, technique_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        if game.pending_event or not game.player.alive or game.player.imprisonment:
            raise ValueError("当前状态无法升级功法")
        known = next(
            (entry for entry in game.player.known_techniques if entry.id == technique_id), None,
        )
        if known is None:
            raise ValueError("你尚未掌握这部功法")
        technique_name = known.name
        old_level = known.level
        new_level = upgrade_known_technique(game.player, technique_id)
        game.history.append(HistoryRecord(
            "SYS_TECHNIQUE_UPGRADE", 1, game.player.age, "合参功法", technique_id, "upgraded",
            f"你消耗一份《{technique_name}》Lv.{old_level} 传承玉简，将功法提升至 Lv.{new_level}。",
            {"technique_id":technique_id, "level":[old_level, new_level]},
            ["system", "technique", "upgrade"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def merge_technique_manuals(
        self, game_id: str, technique_id: str, level: int,
    ) -> dict[str, Any]:
        game = self._load(game_id)
        if game.pending_event or not game.player.alive or game.player.imprisonment:
            raise ValueError("当前状态无法合成传承玉简")
        known = next(
            (entry for entry in game.player.known_techniques if entry.id == technique_id), None,
        )
        template = TECHNIQUE_CATALOG.get(technique_id)
        technique_name = known.name if known else (template.name if template else "无名功法")
        new_level = merge_technique_copies(game.player, technique_id, int(level))
        game.history.append(HistoryRecord(
            "SYS_TECHNIQUE_MANUAL_MERGE", 1, game.player.age, "合炼玉简", technique_id, "merged",
            f"你将两份《{technique_name}》Lv.{level} 传承玉简合为一份 Lv.{new_level} 玉简。",
            {"technique_id":technique_id, "level":[int(level), new_level]},
            ["system", "technique", "manual", "merge"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def absorb_transformation_material(
        self, game_id: str, item_id: str, purify: bool = False, stat_id: str = "",
    ) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if player.path == "monster":
            raise ValueError("妖修不能炼化真灵素材进行变身；请通过血脉进化强化本体")
        if game.pending_event or not player.alive or player.imprisonment:
            raise ValueError("当前状态无法炼化真灵素材")
        item = next((entry for entry in player.inventory if entry.id == item_id and entry.quantity > 0), None)
        if not item or item.transformation_form_id not in TRANSFORMATION_CATALOG or item.transformation_purity <= 0:
            raise ValueError("行囊中没有可炼化的真灵素材")
        quantity = 2 if purify else 1
        if item.quantity < quantity:
            raise ValueError("提纯需要两份相同的真灵素材")
        form_id = str(item.transformation_form_id)
        ensure_transformation_state(player)
        progress = form_stat_progress(player, form_id)
        if stat_id not in progress:
            stat_id = min(progress, key=progress.get)
        current = progress[stat_id]
        if current >= 1 - 1e-9:
            raise ValueError("所选变身属性已经圆满，请改选其他属性")
        gain = absorption_gain(float(item.transformation_purity), purify)
        improved = min(1.0, current + gain)
        if not remove_item(player, item_id, quantity):
            raise ValueError("真灵素材数量不足")
        form = TRANSFORMATION_CATALOG[form_id]
        progress[stat_id] = improved
        mastery = player.transformation_mastery.setdefault(form_id, {})
        mastery.update({
            "stats": {key: round(value, 8) for key, value in progress.items()},
            "purity": round(sum(progress.values()) / len(progress), 8),
            "material_id": item_id,
            "source_type": f"提纯{item.transformation_source}" if purify else str(item.transformation_source),
        })
        if form_id not in player.known_transformations:
            player.known_transformations.append(form_id)
        ensure_transformation_state(player)
        action = "purified" if purify else "absorbed"
        verb = "合炼两份并提纯" if purify else "炼化"
        stat_name = {"might":"威能", "guard":"防护", "mobility":"身法", "sense":"神识", "sustain":"续航", "breach":"破法"}[stat_id]
        game.history.append(HistoryRecord(
            "SYS_TRANSFORMATION_MATERIAL", 1, player.age, "炼化真灵素材", item_id, action,
            f"你{verb}{item.name}，将{form.name}的{stat_name}圆满度由 {current:.2%} 提升至 {improved:.2%}。",
            {"form_id":form_id, "stat_id":stat_id, "old_progress":current, "new_progress":improved, "quantity":-quantity},
            ["system", "transformation", "true_spirit"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def batch_absorb_transformation_material(
        self, game_id: str, item_id: str, mode: str = "direct", stat_id: str = "",
    ) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if player.path == "monster":
            raise ValueError("妖修不能炼化真灵素材进行变身；请通过血脉进化强化本体")
        if game.pending_event or not player.alive or player.imprisonment:
            raise ValueError("当前状态无法炼化真灵素材")
        if mode not in {"direct", "purified"}:
            raise ValueError("未知的一键培养方式")
        item = next((entry for entry in player.inventory if entry.id == item_id and entry.quantity > 0), None)
        if not item or item.transformation_form_id not in TRANSFORMATION_CATALOG or item.transformation_purity <= 0:
            raise ValueError("行囊中没有可炼化的真灵素材")
        if mode == "purified" and item.quantity < 2:
            raise ValueError("一键合炼至少需要两份相同的真灵素材")
        form_id = str(item.transformation_form_id)
        ensure_transformation_state(player)
        progress = form_stat_progress(player, form_id)
        if stat_id not in progress:
            stat_id = min(progress, key=progress.get)
        current = progress[stat_id]
        if current >= 1 - 1e-9:
            raise ValueError("所选变身属性已经圆满，请改选其他属性")

        available = int(item.quantity)
        remaining = available
        consumed = 0
        pair_count = 0
        single_count = 0
        improved = current
        pair_bonus_active = mode == "purified" and available > 2
        direct_gain = absorption_gain(float(item.transformation_purity), False)
        pair_gain = absorption_gain(float(item.transformation_purity), True)
        if pair_bonus_active:
            pair_gain *= 1.30

        if mode == "purified":
            while remaining >= 2 and improved < 1 - 1e-9:
                improved = min(1.0, improved + pair_gain)
                remaining -= 2
                consumed += 2
                pair_count += 1
            if remaining and improved < 1 - 1e-9:
                improved = min(1.0, improved + direct_gain)
                remaining -= 1
                consumed += 1
                single_count += 1
        else:
            while remaining and improved < 1 - 1e-9:
                improved = min(1.0, improved + direct_gain)
                remaining -= 1
                consumed += 1
                single_count += 1

        if consumed <= 0 or not remove_item(player, item_id, consumed):
            raise ValueError("真灵素材数量不足")
        form = TRANSFORMATION_CATALOG[form_id]
        progress[stat_id] = improved
        mastery = player.transformation_mastery.setdefault(form_id, {})
        mastery.update({
            "stats": {key: round(value, 8) for key, value in progress.items()},
            "purity": round(sum(progress.values()) / len(progress), 8),
            "material_id": item_id,
            "source_type": f"批量合炼{item.transformation_source}" if mode == "purified" else f"批量炼化{item.transformation_source}",
        })
        if form_id not in player.known_transformations:
            player.known_transformations.append(form_id)
        ensure_transformation_state(player)
        stat_name = {"might":"威能", "guard":"防护", "mobility":"身法", "sense":"神识", "sustain":"续航", "breach":"破法"}[stat_id]
        process = (
            f"合炼 {pair_count} 组" + ("（每组额外提升 30%）" if pair_bonus_active else "")
            + (f"，并炼化余下 {single_count} 份" if single_count else "")
            if mode == "purified" else f"连续炼化 {single_count} 份"
        )
        game.history.append(HistoryRecord(
            "SYS_TRANSFORMATION_MATERIAL_BATCH", 1, player.age, "一键培养精魄", item_id,
            "batch_purified" if mode == "purified" else "batch_absorbed",
            f"你以{item.name}{process}，将{form.name}的{stat_name}圆满度由 {current:.2%} 提升至 {improved:.2%}。",
            {
                "form_id":form_id, "stat_id":stat_id, "old_progress":current,
                "new_progress":improved, "quantity":-consumed, "pairs":pair_count,
                "singles":single_count, "pair_bonus":0.30 if pair_bonus_active else 0.0,
            },
            ["system", "transformation", "true_spirit", "batch"],
        ))
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

    def manage_transformation(self, game_id: str, form_id: str, action: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if player.path == "monster":
            raise ValueError("妖修不能使用变身系统")
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        if not player.transformation_technique:
            raise ValueError("请先配置一部变身功法")
        ensure_transformation_state(player)
        if form_id not in player.known_transformations or form_id not in TRANSFORMATION_CATALOG:
            raise ValueError("你尚未掌握这种变身")
        technique = player.transformation_technique
        loadout = player.transformation_loadouts[technique.id]
        stored, active = loadout["stored"], loadout["active"]
        capacity, space = transformation_technique_limits(technique)
        form = TRANSFORMATION_CATALOG[form_id]
        if action == "store":
            if form_id in stored:
                raise ValueError("该变身已经存入本功法")
            if len(stored) >= capacity:
                raise ValueError("该功法的变身容量已满")
            stored.append(form_id)
            summary = f"你将{form.name}存入《{technique.name}》。"
        elif action == "remove":
            if form_id not in stored:
                raise ValueError("该变身不在本功法中")
            if form_id in active:
                active.remove(form_id)
            stored.remove(form_id)
            summary = f"你从《{technique.name}》中移除{form.name}，所悟变身本身仍然保留。"
        elif action == "activate":
            if form_id not in stored:
                raise ValueError("需要先将该变身存入功法")
            if form_id in active:
                raise ValueError("该变身已经列入战斗预案")
            if len(active) >= space:
                raise ValueError("该功法的变身空间已满")
            conflict = next((other for other in active if forms_are_incompatible(form_id, other)), None)
            if conflict:
                raise ValueError(f"{form.name}与{TRANSFORMATION_CATALOG[conflict].name}互斥")
            active.append(form_id)
            summary = f"你将{form.name}列入自动战斗预案。"
        elif action == "deactivate":
            if form_id not in active:
                raise ValueError("该变身当前没有启用")
            active.remove(form_id)
            summary = f"你将{form.name}移出自动战斗预案。"
        elif action in {"promote", "demote"}:
            if form_id not in active:
                raise ValueError("只有已启用的变身可以调整权重顺序")
            index = active.index(form_id)
            target = index - 1 if action == "promote" else index + 1
            if not 0 <= target < len(active):
                raise ValueError("该变身已经位于权重顺序边界")
            active[index], active[target] = active[target], active[index]
            summary = f"你调整了{form.name}在融合预案中的权重顺序。"
        else:
            raise ValueError("未知变身管理操作")
        game.history.append(HistoryRecord(
            "SYS_TRANSFORMATION_MANAGE", 1, player.age, "调配变身", form_id, action,
            summary, {"technique_id": technique.id, "form_id": form_id, "action": action},
            ["system", "technique", "transformation"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def dispatch_disciple(self, game_id: str, target: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        if not player.faction_id or player.realm_index < 4:
            raise ValueError("成为元婴期宗门股东后方可派遣弟子")
        if target not in {"item", "technique"}:
            raise ValueError("未知派遣目标")
        if player.last_disciple_dispatch_age == player.age:
            raise ValueError("本年度已经派遣过弟子")
        dispatch_cost = int(FACTION_SYSTEMS["disciple_dispatch_cost"])
        if player.faction_contribution < dispatch_cost:
            raise ValueError(f"派遣弟子需要 {dispatch_cost} 点宗门贡献")
        rng = decode_rng(game.seed, game.rng_state)
        player.faction_contribution -= dispatch_cost
        player.last_disciple_dispatch_age = player.age
        tier = self._market_tier(player)
        pool = [
            entry for entry in MARKET_GOODS
            if entry["kind"] == target and entry["tier"] == tier
            and entry.get("world", "human") == player.world
        ]
        if target == "technique":
            pool = [
                entry for entry in pool
                if entry["content_id"] not in {known.id for known in player.known_techniques}
                and can_player_practice_technique(player, TECHNIQUE_CATALOG[entry["content_id"]].element)
            ]
        success = bool(pool) and rng.random() < float(FACTION_SYSTEMS["disciple_dispatch_success"])
        if success:
            found = rng.choice(pool)
            if target == "item":
                add_item(player, found["content_id"])
                found_name = ITEM_CATALOG[found["content_id"]].name
            else:
                technique = TECHNIQUE_CATALOG[found["content_id"]]
                learn_technique(player, technique)
                found_name = f"《{technique.name}》"
            result = "found"
            summary = f"你派出的弟子数月后归山，带回了{found_name}。宗门贡献 -{dispatch_cost}。"
        else:
            result = "empty_handed"
            summary = f"弟子循线查访数月，却未找到足以入眼的目标。宗门贡献 -{dispatch_cost}。"
        game.history.append(HistoryRecord(
            "SYS_DISCIPLE_DISPATCH", 1, player.age, "派遣弟子", target, result, summary,
            {"faction_contribution": -dispatch_cost}, ["system", "faction", "disciple"],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def manage_faction_relationship(self, game_id: str, npc_id: str, role: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        if not player.faction_id:
            raise ValueError("只有加入宗门后才能直接向宗门 NPC 提出师徒请求")
        if role not in {"master", "disciple"}:
            raise ValueError("未知师徒关系类型")
        if any(str(entry.get("id")) == npc_id for entry in player.concubines):
            raise ValueError("侍妾不是道侣或师徒，必须先解除侍妾名分")
        sect = game.sects.get(player.faction_id)
        npc = next(
            (entry for entry in self._sect_members(game, sect) if entry.id == npc_id and entry.alive),
            None,
        ) if sect and not sect.extinct else None
        if not npc:
            raise ValueError("该宗门人物不存在或已经陨落")
        attempt_key = f"{role}:{npc_id}"
        if attempt_key in player.relationship_attempts:
            raise ValueError("你已经向此人提出过同类请求")
        player_rank = (player.realm_index, player.layer)
        npc_rank = (npc.realm_index, npc.layer)
        max_disciples = int(WORLD_SYSTEMS["relationship"]["max_disciples"])
        if role == "master":
            if player.master:
                raise ValueError("你已经拜有师承")
            if npc_rank <= player_rank:
                raise ValueError("只能拜修为严格高于自己的修士为师")
        else:
            if len(player.disciples) + len(player.disciple_requests) >= max_disciples:
                raise ValueError(f"当前师徒系统最多记录{max_disciples}名弟子或待决拜师帖")
            if npc_rank >= player_rank:
                raise ValueError("只能收修为严格低于自己的修士为徒")
            if any(entry["id"] == npc_id for entry in player.disciples):
                raise ValueError("此人已经是你的弟子")

        rng = decode_rng(game.seed, game.rng_state)
        player.relationship_attempts.append(attempt_key)
        realm_gap = abs(player.realm_index - npc.realm_index)
        accept_chance = min(0.82, (0.28 + realm_gap * 0.10) if role == "master" else (0.62 + realm_gap * 0.06))
        accepted = rng.random() < accept_chance
        relation = self._relationship_snapshot(
            npc.id, npc.name, npc.realm_index, npc.layer, player.faction_id,
            npc.age, npc.lifespan, npc.alive, npc.death_reason,
            spirit_root=npc.spirit_root, cultivation_progress=npc.cultivation_progress,
            path=npc.path, race=npc.race, world=npc.world,
        )
        if accepted and role == "master":
            player.master = relation
            summary = f"{npc.name}认可了你的心性与根基，正式收你为徒。"
            result = "master_accepted"
        elif accepted:
            player.disciples.append(relation)
            summary = f"{npc.name}愿执弟子礼，正式拜入你的门下。"
            result = "disciple_accepted"
        else:
            summary = f"{npc.name}拒绝了你的{'拜师' if role == 'master' else '收徒'}请求。"
            result = "rejected"
        game.history.append(HistoryRecord(
            "SYS_FACTION_RELATIONSHIP", 1, player.age, "师徒之请", npc_id, result, summary,
            {"npc_id": npc_id, "role": role, "accept_chance": round(accept_chance, 2)},
            ["system", "relationship", role],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def respond_disciple_request(self, game_id: str, request_id: str, accept: bool) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        request = next((entry for entry in player.disciple_requests if entry.get("id") == request_id), None)
        if not request:
            raise ValueError("这份拜师帖已经不存在")
        if accept and not request.get("alive", True):
            raise ValueError("求道者已经陨落，无法再收入门下")
        max_disciples = int(WORLD_SYSTEMS["relationship"]["max_disciples"])
        if accept and len(player.disciples) >= max_disciples:
            raise ValueError(f"当前最多记录{max_disciples}名弟子")
        player.disciple_requests.remove(request)
        if accept:
            player.disciples.append(request)
            result = "disciple_accepted"
            summary = f"你亲自收下{request['name']}的拜师帖，正式将其收入门下。"
        else:
            result = "disciple_declined"
            summary = f"你退回了{request['name']}的拜师帖，此段师徒缘分就此作罢。"
        game.history.append(HistoryRecord(
            "SYS_DISCIPLE_REQUEST", 1, player.age, "拜师帖决断", request_id, result, summary,
            {"request_id": request_id, "accepted": bool(accept)}, ["system", "relationship", "disciple"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def request_from_master(self, game_id: str, kind: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        master = player.master
        if not master:
            raise ValueError("你尚无师承")
        if not master.get("alive", True):
            raise ValueError("师父已经陨落，无法回应请求")
        if kind not in {"item", "technique"}:
            raise ValueError("未知索取类型")
        last_requests = master.setdefault("last_requests", {})
        if last_requests.get(kind) == player.age:
            raise ValueError("本年度已经向师父提出过这类请求")

        master_realm = int(master["realm_index"])
        if kind == "item":
            candidates = list(dict.fromkeys(
                entry["content_id"] for entry in MARKET_GOODS
                if entry["kind"] == "item" and int(entry["tier"]) <= max(1, master_realm)
                and entry.get("world", "human") == master.get("world", player.world)
            ))
        else:
            candidates = list(dict.fromkeys(
                entry["content_id"] for entry in MARKET_GOODS
                if entry["kind"] == "technique" and int(entry["tier"]) <= max(1, master_realm)
                and entry.get("world", "human") == master.get("world", player.world)
                and can_player_practice_technique(player, TECHNIQUE_CATALOG[entry["content_id"]].element)
                and all(known.id != entry["content_id"] for known in player.known_techniques)
            ))
        if not candidates:
            raise ValueError("师父手中已无适合你的新物品或功法")

        rng = decode_rng(game.seed, game.rng_state)
        last_requests[kind] = player.age
        chance = float(WORLD_SYSTEMS["relationship"]["master_request_acceptance"][kind])
        accepted = rng.random() < chance
        content_id: str | None = None
        if not accepted:
            result = "master_refused"
            summary = f"{master['name']}认为你不该过度依赖师门，拒绝了这次{'赐物' if kind == 'item' else '传功'}请求。"
        elif kind == "item":
            content_id = rng.choice(candidates)
            add_item(player, content_id)
            result = "master_gave_item"
            summary = f"{master['name']}应允所求，赐下{ITEM_CATALOG[content_id].name}一件。"
        else:
            content_id = rng.choice(candidates)
            learn_technique(player, TECHNIQUE_CATALOG[content_id])
            result = "master_taught_technique"
            summary = f"{master['name']}为你讲授《{TECHNIQUE_CATALOG[content_id].name}》，功法已收入已悟列表。"
        game.history.append(HistoryRecord(
            "SYS_MASTER_REQUEST", 1, player.age, "求取师门恩赐", kind, result, summary,
            {"kind": kind, "accept_chance": chance, "content_id": content_id},
            ["system", "relationship", "master"],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def gift_disciple(self, game_id: str, disciple_id: str, kind: str, content_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        disciple = next((entry for entry in player.disciples if entry.get("id") == disciple_id), None)
        if not disciple:
            raise ValueError("此人并非你的弟子")
        if not disciple.get("alive", True):
            raise ValueError("弟子已经陨落，无法接受赠予")
        if kind == "item":
            if content_id not in ITEM_CATALOG or not remove_item(player, content_id):
                raise ValueError("物品栏中没有这件物品")
            gifts = disciple.setdefault("items", {})
            gifts[content_id] = int(gifts.get(content_id, 0)) + 1
            if "pill" in ITEM_CATALOG[content_id].tags:
                disciple["breakthrough_bonus"] = min(
                    0.35, float(disciple.get("breakthrough_bonus", 0))
                    + float(WORLD_SYSTEMS["demonic_cultivation"]["pill_breakthrough_bonus"]),
                )
            result = "disciple_gifted_item"
            summary = f"你将{ITEM_CATALOG[content_id].name}赠予弟子{disciple['name']}。" + (
                f" 其突破率提高至额外 +{float(disciple.get('breakthrough_bonus', 0)):.0%}。"
                if "pill" in ITEM_CATALOG[content_id].tags else ""
            )
        elif kind == "technique":
            technique = next((entry for entry in player.known_techniques if entry.id == content_id), None)
            if not technique:
                raise ValueError("你尚未掌握这部功法")
            taught = disciple.setdefault("techniques", [])
            if content_id in taught:
                raise ValueError("这名弟子已经受过此法")
            taught.append(content_id)
            result = "disciple_taught_technique"
            summary = f"你为弟子{disciple['name']}拓印并讲授《{technique.name}》；你自身的功法不会失去。"
        else:
            raise ValueError("未知赠予类型")
        game.history.append(HistoryRecord(
            "SYS_DISCIPLE_GIFT", 1, player.age, "赐予门下", kind, result, summary,
            {"disciple_id": disciple_id, "kind": kind, "content_id": content_id},
            ["system", "relationship", "disciple"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def manage_dao_companion(
        self, game_id: str, action: str, npc_id: str = "", kind: str = "", content_id: str = "",
    ) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法与道侣互动")
        rng = decode_rng(game.seed, game.rng_state)
        companion = player.dao_companion
        if action == "propose":
            if companion and companion.get("alive", True):
                raise ValueError("你已经有道侣")
            npc = self._find_npc(game, npc_id) or self._promote_cached_npc(game, npc_id, "结为道侣")
            if not npc or not npc.alive or npc.world != player.world:
                raise ValueError("此人当前无法回应结侣请求")
            if any(str(entry.get("id")) == npc.id for entry in player.concubines):
                raise ValueError("侍妾不是道侣，必须先解除侍妾名分")
            if player.master and player.master.get("id") == npc.id or any(entry.get("id") == npc.id for entry in player.disciples):
                raise ValueError("已有师徒名分，不能再结为道侣")
            realm_gap = abs(npc.realm_index - player.realm_index)
            chance = max(0.05, min(0.9, float(WORLD_SYSTEMS["relationship"]["companion_proposal_base"]) + (npc.affinity or 0) / 180 - realm_gap * 0.12))
            if rng.random() >= chance:
                npc.affinity = (npc.affinity or 0) - 3
                result, summary = "proposal_refused", f"{npc.name}认为缘分未至，婉拒了结为道侣的请求（同意率 {chance:.0%}）。"
            else:
                npc.affinity = (npc.affinity or 0) + self._sage_affinity_gain(player, 12)
                source = self._npc_faction_id(game, npc.id) or "world"
                player.dao_companion = self._relationship_snapshot(
                    npc.id, npc.name, npc.realm_index, npc.layer, source, npc.age, npc.lifespan,
                    npc.alive, npc.death_reason, npc.spirit_root, npc.cultivation_progress,
                    npc.path, npc.race, npc.world,
                    main_technique_id=self._default_npc_main_technique(npc), affinity=npc.affinity,
                )
                result, summary = "companion_joined", f"{npc.name}应下誓约，与你结为道侣（同意率 {chance:.0%}）。"
        else:
            if not companion:
                raise ValueError("你尚无道侣")
            if not companion.get("alive", True) or companion.get("world", player.world) != player.world:
                raise ValueError("道侣当前无法回应")
            last = companion.setdefault("last_interactions", {})
            cooldown = int(WORLD_SYSTEMS["relationship"]["companion_interaction_cooldown_years"])
            if action in {"intimacy", "entwine", "request_item", "request_technique"} and player.age - int(last.get(action, -10**9)) < cooldown:
                raise ValueError("本年度已经进行过这项道侣互动")
            if action == "intimacy":
                last[action] = player.age
                low, high = WORLD_SYSTEMS["relationship"]["companion_heart_demon_intimacy"]
                reduction = min(player.heart_demon, rng.randint(int(low), int(high)))
                player.heart_demon -= reduction
                companion["affinity"] = float(companion.get("affinity", 20)) + self._sage_affinity_gain(player, 1)
                dialogue = rng.choice([
                    "对方与你谈起初次相遇时的窘事，洞府中久违地有了笑声。",
                    "你们互相复盘近年的得失，许多执念在言语间自然散去。",
                    "二人并肩看了一夜星河，没有论道，却比闭关更觉心境安宁。",
                    "对方提醒你莫把长生路走成孤身苦役，你默然许久。",
                ])
                result, summary = "companion_intimacy", f"{dialogue} 心魔 -{reduction:g}。"
            elif action == "entwine":
                last[action] = player.age
                low, high = WORLD_SYSTEMS["relationship"]["companion_heart_demon_entwine"]
                reduction = min(player.heart_demon, rng.randint(int(low), int(high)))
                player.heart_demon -= reduction
                companion["affinity"] = float(companion.get("affinity", 20)) + self._sage_affinity_gain(player, 2)
                sex_ids = {technique.id for technique in [player.technique] if technique and technique.element == "sex"}
                if companion.get("main_technique_id") in TECHNIQUE_CATALOG and TECHNIQUE_CATALOG[companion["main_technique_id"]].element == "sex":
                    sex_ids.add(str(companion["main_technique_id"]))
                gain = 0.0
                if sex_ids:
                    gain = round(opportunity_required(player) * 0.04 * opportunity_multiplier(player), 1)
                    self._add_opportunity(player, gain)
                gain_text = f" 合欢功法运转，机缘 +{gain:g}。" if gain else ""
                child_text = self._try_conceive_child(game, rng)
                result, summary = "companion_entwined", f"你与{companion['name']}缠绵共参，心魔 -{reduction:g}。{gain_text}{child_text}"
            elif action in {"request_item", "request_technique"}:
                last[action] = player.age
                request_kind = action.removeprefix("request_")
                chance = float(WORLD_SYSTEMS["relationship"][f"companion_request_{request_kind}"]) + float(companion.get("affinity", 20)) / 250
                chance = max(0.08, min(0.9, chance))
                candidates = list(dict.fromkeys(
                    entry["content_id"] for entry in MARKET_GOODS
                    if entry["kind"] == request_kind and int(entry["tier"]) <= max(1, int(companion["realm_index"]))
                    and entry.get("world", "human") == player.world
                    and (request_kind == "item" or (
                        can_player_practice_technique(player, TECHNIQUE_CATALOG[entry["content_id"]].element)
                        and all(known.id != entry["content_id"] for known in player.known_techniques)
                    ))
                ))
                if not candidates:
                    raise ValueError("道侣手中没有适合你的新物品或功法")
                if rng.random() >= chance:
                    companion["affinity"] = float(companion.get("affinity", 20)) - 1
                    result, summary = "companion_refused", f"{companion['name']}拒绝了这次索取（同意率 {chance:.0%}）。"
                else:
                    selected = rng.choice(candidates)
                    if request_kind == "item":
                        add_item(player, selected)
                        summary = f"{companion['name']}将{ITEM_CATALOG[selected].name}交给了你。"
                    else:
                        learn_technique(player, TECHNIQUE_CATALOG[selected])
                        summary = f"{companion['name']}与你分享《{TECHNIQUE_CATALOG[selected].name}》。"
                    result = f"companion_gave_{request_kind}"
            elif action == "gift_item":
                if content_id not in ITEM_CATALOG or not remove_item(player, content_id):
                    raise ValueError("物品栏中没有这件物品")
                items = companion.setdefault("items", {})
                items[content_id] = int(items.get(content_id, 0)) + 1
                companion["affinity"] = float(companion.get("affinity", 20)) + self._sage_affinity_gain(player, 3)
                result, summary = "companion_gifted", f"你将{ITEM_CATALOG[content_id].name}赠予{companion['name']}，情意更深。"
            elif action == "teach_technique":
                technique = next((entry for entry in player.known_techniques if entry.id == content_id), None)
                if not technique:
                    raise ValueError("你尚未掌握这部功法")
                if not can_practice_technique(str(companion.get("spirit_root", "none")), technique.element):
                    raise ValueError("道侣的灵根无法修习这部功法")
                companion["main_technique_id"] = technique.id
                taught = companion.setdefault("techniques", [])
                if technique.id not in taught:
                    taught.append(technique.id)
                companion["affinity"] = float(companion.get("affinity", 20)) + self._sage_affinity_gain(player, 2)
                result, summary = "companion_technique_replaced", f"{companion['name']}废去旧法，将《{technique.name}》改作主修功法。"
            else:
                raise ValueError("未知道侣互动")
        if player.dao_companion:
            source_npc = self._find_npc(game, str(player.dao_companion.get("id", "")))
            if source_npc:
                source_npc.affinity = float(player.dao_companion.get("affinity", source_npc.affinity or 0))
        if action == "intimacy" and player.dao_companion:
            summary += self._tianji_npc_conversation_clue(game, str(player.dao_companion.get("id", "")), rng)
        game.history.append(HistoryRecord(
            "SYS_DAO_COMPANION", 1, player.age, "道侣缘法", action, result, summary,
            {"companion": player.dao_companion.get("id") if player.dao_companion else None},
            ["system", "relationship", "dao_companion"],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def manage_dao_friend(self, game_id: str, npc_id: str, action: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法与道友互动")
        friend = next((row for row in player.dao_friends if row.get("id") == npc_id), None)
        rng = decode_rng(game.seed, game.rng_state)
        if action == "befriend":
            if friend:
                raise ValueError("此人已经是你的道友")
            npc = self._find_npc(game, npc_id) or self._promote_cached_npc(game, npc_id, "结为道友")
            if not npc or not npc.alive or npc.world != player.world:
                raise ValueError("此人当前无法回应")
            if any(str(entry.get("id")) == npc.id for entry in player.concubines):
                raise ValueError("已有侍妾名分，不能同时结为道友")
            if (player.dao_companion and player.dao_companion.get("id") == npc.id) or (player.master and player.master.get("id") == npc.id) or any(row.get("id") == npc.id for row in player.disciples):
                raise ValueError("你们已经有更紧密的人际名分")
            required = float(WORLD_SYSTEMS["relationship"]["friend_affinity_required"])
            if float(npc.affinity or 0) < required:
                raise ValueError(f"对方好感至少达到 {required:g} 才愿与你结为道友")
            chance = min(0.95, float(WORLD_SYSTEMS["relationship"]["friend_invite_base"]) + float(npc.affinity or 0) / 200)
            if rng.random() >= chance:
                result, summary = "friend_refused", f"{npc.name}认为交情尚浅，婉拒了道友之约（同意率 {chance:.0%}）。"
            else:
                source = self._npc_faction_id(game, npc.id) or "world"
                friend = self._relationship_snapshot(
                    npc.id,npc.name,npc.realm_index,npc.layer,source,npc.age,npc.lifespan,
                    npc.alive,npc.death_reason,npc.spirit_root,npc.cultivation_progress,
                    npc.path,npc.race,npc.world,main_technique_id=self._default_npc_main_technique(npc),affinity=npc.affinity or 0,
                )
                player.dao_friends.append(friend)
                result, summary = "friend_joined", f"{npc.name}与你交换信符，自此以道友相称。"
        else:
            if not friend or not friend.get("alive", True) or friend.get("world") != player.world:
                raise ValueError("这位道友当前无法回应")
            last = friend.setdefault("last_interactions", {})
            cooldown = int(WORLD_SYSTEMS["relationship"]["friend_interaction_cooldown_years"])
            if player.age - int(last.get(action, -10**9)) < cooldown:
                raise ValueError("本年度已经进行过这项道友互动")
            last[action] = player.age
            if action == "spar":
                low, high = WORLD_SYSTEMS["relationship"]["friend_spar_opportunity"]
                gain = rng.randint(int(low), int(high))
                self._add_opportunity(player, gain)
                self._adjust_person_affinity(game, npc_id, 1)
                result, summary = "friend_sparred", f"你与{friend['name']}点到为止地切磋数场，彼此印证招式，机缘 +{gain}。"
            elif action == "discuss":
                low, high = WORLD_SYSTEMS["relationship"]["friend_discuss_opportunity"]
                gain = rng.randint(int(low), int(high))
                self._add_opportunity(player, gain)
                self._adjust_person_affinity(game, npc_id, 2)
                result, summary = "friend_discussed", f"你与{friend['name']}交换修炼心得，解开数处疑难，机缘 +{gain}。"
            else:
                raise ValueError("未知道友互动")
        if action in {"befriend", "discuss", "spar"}:
            summary += self._tianji_npc_conversation_clue(game, npc_id, rng)
        game.history.append(HistoryRecord(
            "SYS_DAO_FRIEND",1,player.age,"道友往来",action,result,summary,
            {"friend_id":npc_id},["system","relationship","friend"],
        ))
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def invite_relationship_to_faction(self, game_id: str, npc_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        sect = game.sects.get(player.faction_id or "")
        if game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法引荐入宗")
        if not sect or sect.extinct or sect.world != player.world:
            raise ValueError("你当前没有可以引荐他人的宗门")
        relations = [entry for entry in [player.master, player.dao_companion, *player.dao_friends] if entry]
        relation = next((entry for entry in relations if str(entry.get("id")) == npc_id), None)
        if not relation or not relation.get("alive", True) or relation.get("world") != player.world:
            raise ValueError("只能邀请当前界面中存活的师父、道侣或道友")
        existing = self._npc_faction_id(game, npc_id)
        if existing:
            raise ValueError("此人已经有所属宗门")
        npc = self._persist_relationship_npc(game, relation, "受邀加入宗门")
        npc.faction_id = sect.id
        relation["source"] = "world"
        npc.affinity = max(
            float(npc.affinity or 0), float(relation.get("affinity", 0)),
        ) + self._sage_affinity_gain(player, 4)
        relation["affinity"] = npc.affinity
        game.history.append(HistoryRecord(
            "SYS_RELATION_JOIN_FACTION",1,player.age,"引荐入宗",npc_id,"joined",
            f"{relation['name']}接受你的引荐，加入{sect.name}，成为宗门中真实在册的一员。",
            {"npc_id":npc_id,"faction_id":sect.id},["system","relationship","faction"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def leave_relationship(self, game_id: str, kind: str, npc_id: str = "") -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法了断人际关系")
        rules = WORLD_SYSTEMS["relationship"]
        if kind == "companion":
            relation = player.dao_companion
            if not relation:
                raise ValueError("你当前没有道侣")
            npc = self._persist_relationship_npc(game, relation, "道侣决裂")
            player.heart_demon += self._sage_scaled_gain(
                player, float(rules["companion_separation_heart_demon"]), "heart_demon_gain_reduction",
            )
            npc.affinity = float(rules.get("relationship_release_affinity", 0))
            player.dao_companion = None
            summary = f"你与{relation['name']}斩断道侣誓约，双方好感重置为中立；心魔骤增 {rules['companion_separation_heart_demon']:g}。"
            tags = ["system","relationship","dao_companion","negative"]
        elif kind == "master":
            relation = player.master
            if not relation:
                raise ValueError("你当前没有师父")
            npc = self._persist_relationship_npc(game, relation, "脱离师门")
            npc.affinity = float(rules.get("relationship_release_affinity", 0))
            player.master = None
            summary = f"你脱离{relation['name']}门下，双方好感重置为中立，不会因这次离门立即遭到寻仇。"
            tags = ["system","relationship","master","negative"]
        elif kind == "friend":
            relation = next((entry for entry in player.dao_friends if entry.get("id") == npc_id), None)
            if not relation:
                raise ValueError("此人并非你的道友")
            player.dao_friends.remove(relation)
            self._set_person_affinity(game, str(relation.get("id", "")), float(rules.get("relationship_release_affinity", 0)))
            summary = f"你与{relation['name']}收回道友信符，双方好感重置为中立，此后只是寻常相识。"
            tags = ["system","relationship","friend"]
        elif kind == "disciple":
            relation = next((entry for entry in player.disciples if entry.get("id") == npc_id), None)
            if not relation:
                raise ValueError("此人并非你的弟子")
            npc = self._persist_relationship_npc(game, relation, "逐出师门")
            npc.affinity = float(rules.get("relationship_release_affinity", 0))
            player.disciples.remove(relation)
            summary = f"你将{relation['name']}逐出门下，双方好感重置为中立。"
            tags = ["system","relationship","disciple","negative"]
        else:
            raise ValueError("未知人际关系类型")
        player.party = [entry for entry in player.party if entry.get("id") != relation.get("id")]
        game.history.append(HistoryRecord(
            "SYS_RELATION_EXIT",1,player.age,"缘尽于此",kind,"departed",summary,
            {"npc_id":relation.get("id"),"kind":kind},tags,
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def leave_faction(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        sect = game.sects.get(player.faction_id or "")
        if game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法退出宗门")
        if not sect or sect.extinct:
            raise ValueError("你当前没有可以退出的宗门")
        release_affinity = float(WORLD_SYSTEMS["relationship"].get("relationship_release_affinity", 0))
        members = self._sect_members(game, sect)
        for npc in members:
            npc.affinity = release_affinity
        self._sync_relationship_records(game)
        old_id, old_name = sect.id, sect.name
        if sect.founded_by_player:
            successor = max((npc for npc in members if npc.alive), key=lambda npc:(npc.realm_index,npc.layer), default=None)
            sect.founded_by_player = False
            sect.founder_player_id = None
            sect.founded_by_npc = True
            sect.founder_npc_id = successor.id if successor else None
        player.faction_id = None
        player.allegiance_race = player.lineage_race or player.race
        player.faction_join_age = None
        player.faction_contribution = 0
        player.faction_reward_preference = None
        game.history.append(HistoryRecord(
            "SYS_PLAYER_LEAVE_FACTION",1,player.age,"退出宗门",old_id,"left",
            f"你退出{old_name}，与旧日同门的好感统一重置为中立，不会因退宗立即遭到寻仇。",
            {"faction_id":old_id,"affinity_reset":release_affinity},["system","faction","relationship"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def arrange_faction_succession(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        sect = game.sects.get(player.faction_id or "")
        if game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法安排宗门后事")
        if not sect or sect.extinct or not sect.founded_by_player or sect.founder_player_id != game.id:
            raise ValueError("只有仍在执掌亲手创建宗门时才能安排让权")
        members = [npc for npc in self._sect_members(game, sect) if npc.alive and npc.world == sect.world]
        successor = max(members, key=lambda npc: (npc.realm_index, npc.layer, -npc.age), default=None)
        if not successor:
            raise ValueError("宗门中没有能够承接权柄的在世门人")
        plan = {
            "arranged": True, "eligible_return": False,
            "successor_id": successor.id, "successor_name": successor.name,
            "origin_world": sect.world, "arranged_age": player.age,
        }
        self._intrigue_state(game).setdefault("succession_plans", {})[sect.id] = plan
        game.history.append(HistoryRecord(
            "SYS_FACTION_SUCCESSION_PLAN", 1, player.age, "安排宗门后事", sect.id, "arranged",
            f"你指定{successor.name}在自己飞升后接掌{sect.name}；若宗门延续至你重返下界，门人可能寻觅祖师，请你重新执掌大权。",
            {"sect_id": sect.id, "successor_id": successor.id},
            ["system", "faction", "succession", f"world:{sect.world}"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def set_faction_reward(self, game_id: str, reward_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        if not player.faction_id:
            raise ValueError("你尚未加入宗门")
        if player.realm_index < 4:
            raise ValueError("进入元婴初期后方可参与宗门议事并固定年度奖励")
        if reward_id not in FACTION_REWARDS:
            raise ValueError("未知宗门奖励")
        player.faction_reward_preference = reward_id
        reward = FACTION_REWARDS[reward_id]
        game.history.append(HistoryRecord(
            "SYS_FACTION_REWARD", 1, player.age, "宗门议事", reward_id, "selected",
            f"你在议事册上选定“{reward['name']}”，今后的年度分红将固定为此项。",
            {"faction_reward_preference": reward_id}, ["system", "faction"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def manage_party(self, game_id: str, npc_id: str, action: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法调整队伍")
        if action == "interact":
            if not any(entry.get("id") == npc_id for entry in player.party):
                raise ValueError("只有当前队友可以进行同行互动")
            key = f"party_interaction:{npc_id}"
            if game.governance_actions.get(key) == player.age:
                raise ValueError("本行动单位已经与这位队友交流过")
            rng = decode_rng(game.seed, game.rng_state)
            gain_range = WORLD_SYSTEMS["party"].get("interaction_affinity", [4, 8])
            gain = rng.randint(int(gain_range[0]), int(gain_range[1]))
            affinity = self._adjust_person_affinity(game, npc_id, gain)
            game.governance_actions[key] = player.age
            game.rng_state = encode_rng(rng)
            result, summary = "interacted", f"你与队友交流沿途见闻、互证修炼心得，好感 +{gain}，当前为 {affinity:.0f}。"
            summary += self._tianji_npc_conversation_clue(game, npc_id, rng)
            game.rng_state = encode_rng(rng)
        elif action in {"crossing_add", "crossing_remove"}:
            if not any(entry.get("id") == npc_id for entry in player.party):
                raise ValueError("只有当前队友可以随行飞升")
            candidate = self._party_crossing_candidate(game, npc_id)
            if not candidate:
                raise ValueError("此队友尚未达到可共同飞升的境界")
            is_companion = bool(player.dao_companion and str(player.dao_companion.get("id")) == npc_id)
            if is_companion:
                player.joint_spirit_crossing = (
                    {"id": npc_id, "name": candidate["name"]}
                    if action == "crossing_add"
                    else {"id": npc_id, "name": candidate["name"], "declined": True}
                )
            else:
                player.joint_friend_crossing = [entry for entry in player.joint_friend_crossing if entry.get("id") != npc_id]
                if action == "crossing_add":
                    player.joint_friend_crossing.append({"id":npc_id, "name":candidate["name"]})
            if action == "crossing_add":
                result, summary = "crossing_selected", f"你邀请{candidate['name']}在飞升时与你一同闯过界壁。"
            else:
                result, summary = "crossing_removed", f"你取消了与{candidate['name']}共同飞升的安排。"
        elif action == "leave":
            before = len(player.party)
            player.party = [entry for entry in player.party if entry.get("id") != npc_id]
            player.joint_friend_crossing = [entry for entry in player.joint_friend_crossing if entry.get("id") != npc_id]
            if player.dao_companion and str(player.dao_companion.get("id")) == npc_id:
                player.joint_spirit_crossing = {
                    "id": npc_id, "name": str(player.dao_companion.get("name", "道侣")), "declined": True,
                }
            if len(player.party) == before:
                raise ValueError("此人不在队伍中")
            summary = "你与队友暂且分别。"
            result = "left"
        elif action == "invite":
            if len(player.party) >= int(WORLD_SYSTEMS["party"]["max_companions"]):
                raise ValueError("当前队伍已经满员")
            if any(entry.get("id") == npc_id for entry in player.party):
                raise ValueError("此人已经在队伍中")
            companion = player.dao_companion
            if companion and companion.get("id") == npc_id:
                if not companion.get("alive", True) or companion.get("world") != player.world:
                    raise ValueError("道侣当前无法同行")
                player.party.append({"id": npc_id, "name": companion.get("name", "道侣")})
                result, summary = "joined", f"{companion.get('name', '道侣')}与你心意相通，加入了队伍。"
                game.history.append(HistoryRecord(
                    "SYS_PARTY_MANAGE", 1, player.age, "道侣同行", npc_id, result, summary,
                    {"party": [entry.get("id") for entry in player.party]}, ["system", "party", "companion"],
                ))
                game.updated_at = now_iso()
                self.store.save(game)
                return self.present(game)
            friend = next((row for row in player.dao_friends if row.get("id") == npc_id), None)
            if friend:
                if not friend.get("alive", True) or friend.get("world") != player.world:
                    raise ValueError("道友当前无法同行")
                player.party.append({"id":npc_id,"name":friend.get("name","道友")})
                result, summary = "joined", f"道友{friend.get('name','无名')}应邀加入队伍。"
                game.history.append(HistoryRecord(
                    "SYS_PARTY_MANAGE",1,player.age,"道友同行",npc_id,result,summary,
                    {"party":[entry.get("id") for entry in player.party]},["system","party","friend"],
                ))
                game.updated_at = now_iso()
                self.store.save(game)
                return self.present(game)
            npc = self._find_npc(game, npc_id) or self._promote_cached_npc(game, npc_id, "结伴同行")
            if not npc or not npc.alive or npc.world != player.world:
                raise ValueError("此人当前无法同行")
            rng = decode_rng(game.seed, game.rng_state)
            faction_id = self._npc_faction_id(game, npc.id)
            global_hostility = max(
                player.hostility.get(self._hostility_key("race", npc.race), 0),
                player.hostility.get(self._hostility_key("sect", faction_id), 0) if faction_id else 0,
            )
            chance = self._party_invitation_chance(player, npc, global_hostility)
            if rng.random() >= chance:
                npc.affinity = (npc.affinity or 0) - 2
                result, summary = "rejected", f"{npc.name}婉拒了同行邀请（同意率 {chance:.0%}）。"
            else:
                npc.affinity = (npc.affinity or 0) + self._sage_affinity_gain(player, 4)
                player.party.append({"id": npc.id, "name": npc.name})
                result, summary = "joined", f"{npc.name}同意加入队伍（同意率 {chance:.0%}）。"
            game.rng_state = encode_rng(rng)
        else:
            raise ValueError("未知队伍操作")
        game.history.append(HistoryRecord(
            "SYS_PARTY_MANAGE", 1, player.age, "结伴同行", npc_id, result, summary,
            {"party": [entry.get("id") for entry in player.party]}, ["system", "party", "npc"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _commission_step(self, game: GameState, rng: random.Random) -> str:
        tier = self._market_tier(game.player)
        quantity = rng.randint(*MARKET_SETTINGS["commission_stones"][str(tier)])
        add_item(game.player, "spirit_stone", quantity)
        world_name = WORLD_SYSTEMS["world_names"].get(game.player.world, game.player.world)
        return f"完成一项{world_name}{REALMS[tier].name}坊市委托，获得下品灵石 ×{quantity}。"

    def _personal_combat_step(self, game: GameState, action: str, rng: random.Random) -> str:
        player = game.player
        settings = ACTIONS[action]["combat"]
        target_name = rng.choice(settings["target_names"])
        if settings.get("combat_type") == "beast":
            encounter_power = self._player_intrinsic_combat_power(player)
            if player.cultivation_concealment:
                concealment = player.cultivation_concealment
                encounter_power = recommended_combat_power(
                    int(concealment["realm_index"]), int(concealment.get("layer", 1)),
                )
            target = {
                "target_name": target_name,
                "target_power": max(1.0, encounter_power * rng.uniform(*settings["power_multiplier"])),
                "target_realm_index": max(1, player.realm_index - 1),
                "combat_type": "beast",
                "success_threshold": settings.get("success_threshold"),
            }
        else:
            target = self._known_npc_encounter_target(game, settings, rng)
            if target is None:
                target = self._generate_cultivator_target(
                    player, target_name, settings, rng, game=game,
                    use_player_concealment=True,
                )
                self._cache_encounter_target(game, target, rng)
        target["kill_karma"] = bool(settings.get("kill_karma", True))
        target["capture"] = bool(settings.get("capture", False))
        target["action"] = action
        target["non_story_combat"] = True
        if target.get("combat_type") == "cultivator" and len(target.get("members", [])) > 1 and action in {"spar", "slay"}:
            event_id = "EVT_TEAM_SPAR_PREVIEW_001" if action == "spar" else "EVT_TEAM_SLAY_PREVIEW_001"
            event = self.events_by_id[event_id]
            game.pending_event = self._instantiate_event(event, game, rng)
            game.pending_event["runtime"] = copy.deepcopy(target)
            player_power = self._player_battle_power(game)
            body = game.pending_event["body"]
            replacements = {
                "{team_size}": str(len(target["members"])),
                "{target_realm}": str(target["target_realm_display"]),
                "{target_power}": f"{target.get('target_power_display', target['target_power']):.0f}",
                "{player_power}": f"{player_power:.0f}",
            }
            for marker, value in replacements.items():
                body = body.replace(marker, value)
            if target.get("treasure_rumored") and target.get("treasure_item_id") in ITEM_CATALOG:
                body += f" 传闻为首者携带了{ITEM_CATALOG[target['treasure_item_id']].name}。"
            game.pending_event["body"] = body
            return f"你遇到一支{len(target['members'])}人修士队伍，已先观察其修为与合计战力，尚未交手。"
        result, summary = self._combat(game, target, bool(settings.get("lethal")), rng)
        if target.get("combat_type") == "cultivator":
            race_text = (
                f"对方属于{target['race_name']}（{target['race_description']}），"
                if self._world_supports(player.world, "races") else ""
            )
            team_text = f"，同行共 {len(target.get('members', []))} 人" if len(target.get("members", [])) > 1 else ""
            rumor = (
                f" 传闻中这个人携带了{ITEM_CATALOG[target['treasure_item_id']].name}。"
                if target.get("treasure_rumored") and target.get("treasure_item_id") in ITEM_CATALOG else ""
            )
            summary = (
                f"{race_text}你判断对方修为为{target['target_realm_display']}{team_text}，"
                f"表面战斗力约 {target.get('target_power_display', target['target_power']):.0f}。"
                f"{rumor}" + summary
            )
        return self._apply_combat_action_rewards(game, action, result, summary, rng)

    def _apply_combat_action_rewards(
        self, game: GameState, action: str, result: str, summary: str, rng: random.Random,
        *, player_defending: bool = False,
    ) -> str:
        player = game.player
        settings = ACTIONS[action]["combat"]
        if action == "hunt_beast" and result == "killed" and not player_defending:
            sha_gain = rng.randint(*settings["sha_qi_gain"])
            sha_gain = self._sage_scaled_gain(player, sha_gain, "sha_qi_gain_reduction")
            player.sha_qi += sha_gain
            summary += f" 妖血淬身，煞气 +{sha_gain}。"
        if result in {"victory", "killed"} and settings.get("reward_stones"):
            reward = rng.randint(*settings["reward_stones"])
            add_item(player, "spirit_stone", reward)
            summary += f" 你从战利品中获得下品灵石 ×{reward}。"
        if action == "spar" and result == "victory":
            bonus = round(2 * opportunity_multiplier(player), 1)
            self._add_opportunity(player, bonus)
            summary += f" 印证所学使机缘 +{bonus}。"
        return summary

    def _known_npc_encounter_target(
        self, game: GameState, settings: dict[str, Any], rng: random.Random,
    ) -> dict[str, Any] | None:
        player = game.player
        config = WORLD_SYSTEMS["faction_conflict"]
        protected = self._player_protected_npc_ids(game)
        candidates: list[tuple[SectNpc, str | None, bool]] = [
            (npc, None, False) for npc in [*game.world_npcs.values(), *game.notable_npcs.values()]
            if npc.alive and npc.world == player.world and npc.id not in protected
        ]
        for sect_id, sect in game.sects.items():
            candidates.extend(
                (npc, sect_id, False) for npc in sect.npcs
                if npc.alive and npc.world == player.world and npc.id not in protected
            )
        for cached in game.encounter_npc_cache:
            raw = cached.get("npc", {})
            if raw.get("alive", True) and raw.get("world") == player.world and str(raw.get("id", "")) not in protected:
                candidates.append((SectNpc.from_dict(raw), None, True))
        known_chance = float(config["world_npc_encounter_chance"])
        if player.faction_id:
            known_chance += float(config["sect_npc_encounter_chance"])
        if game.encounter_npc_cache:
            known_chance += min(0.18, len(game.encounter_npc_cache) * 0.005)
        if not candidates or rng.random() >= known_chance:
            return None
        weights = [
            (3.5 if npc.notorious else 1.0) * encounter_weight(
                str(game.race_relations.get(race_pair(self._player_allegiance_race(player), npc.race), {}).get("status", "neutral")),
                float(game.race_relations.get(race_pair(self._player_allegiance_race(player), npc.race), {}).get("affinity", 0)),
            ) if self._world_supports(player.world, "races") and npc.race != self._player_allegiance_race(player) else 1.25
            for npc, _, _ in candidates
        ]
        npc, faction_id, from_cache = rng.choices(candidates, weights=weights, k=1)[0]
        if from_cache:
            cached = next(row for row in game.encounter_npc_cache if row.get("id") == npc.id)
            cached["seen_count"] = int(cached.get("seen_count", 1)) + 1
            cached["last_seen_age"] = player.age
            npc = self._promote_cached_npc(game, npc.id, "再度相逢") or npc
        npc.encountered_player = True
        self._tianji_observe_npc(game, npc.id)
        perception = self._npc_cultivation_perception(game, npc, True)
        visible = perception["realm_name"] != "无法看清"
        race_definition = RACE_DEFINITIONS.get(npc.race, RACE_DEFINITIONS["human"])
        target = {
            "target_name": npc.name, "target_power": self._npc_power(npc), "primary_power": self._npc_power(npc),
            "target_power_display": perception["display_power"] or self._npc_power(npc),
            "target_expected_power": expected_combat_power(npc.realm_index, npc.layer),
            "target_realm_index": npc.realm_index, "target_layer": npc.layer,
            "target_realm_visible": visible,
            "target_realm_display": perception["realm_name"],
            "combat_type": "cultivator", "race": npc.race,
            "race_name": race_definition["name"], "race_description": race_definition["description"],
            "world": npc.world, "npc_id": npc.id, "faction_id": faction_id, "path": npc.path,
            "treasure_item_id": npc.treasure_item_id,
            "treasure_rumored": rng.random() < float(config["treasure_rumor_chance"]),
            "notorious": npc.notorious, "notoriety": npc.notoriety,
        }
        target = self._add_enemy_party(target, settings, rng)
        self._tianji_preview_npc_power(game, target)
        return target

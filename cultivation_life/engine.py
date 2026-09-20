from __future__ import annotations

import copy
import operator
import random
import uuid
from pathlib import Path
from typing import Any

from .content_registry import (
    ACTIONS, FACTION_DEFINITIONS, FACTION_NPC_TEMPLATES, FACTION_REWARDS, FACTION_SYSTEMS,
    ITEM_CATALOG, KARMA_FACTORS, MARKET_GOODS, MARKET_SETTINGS, PATH_NAMES, REALMS,
    RACE_DEFINITIONS, RACE_SYSTEMS, ROOT_DEFINITIONS, ROOT_NAMES, TECHNIQUE_CATALOG,
    TECHNIQUE_ELEMENT_NAMES, TRANSFORMATION_CATALOG, WORLD_NPC_TEMPLATES, WORLD_SYSTEMS,
    STORY_COMBAT_SCENARIOS, CONTENT_DOCUMENTS, MONSTER_BLOODLINE_SETTINGS, MONSTER_SPECIES, ContentError,
)
from .combat_system import BattleUnit, PlayerCombatSystem, stat_comparison
from .event_repository import EventRepository
from .economy_system import EconomySystemMixin
from .demonic_system import DemonicSystemMixin
from .map_runtime import MapTravelMixin
from .models import GameState, HistoryRecord, Player, SectNpc, SectState, Technique
from .map_system import MapCatalog
from .npc_system import attitude_label, npc_breakthrough_chance, npc_combat_power, npc_team_combat_power, party_combat_power
from .rules import (
    add_item,
    assign_technique,
    can_practice_technique,
    can_player_practice_technique,
    combat_power,
    combat_power_assessment_value,
    expected_combat_power,
    effective_karma,
    has_item,
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
    grant_qi_experience,
    qi_level,
    qi_level_threshold,
    recommended_combat_power,
    divine_sense_breakthrough_cost,
    divine_sense_level,
    divine_sense_level_threshold,
    technique_scale,
)
from .transformation_system import (
    absorption_gain, active_transformation_profile, ensure_transformation_state,
    form_purity, form_stat_progress, forms_are_incompatible, public_transformation_system,
)


from .storage import SaveStore
from .achievements import AchievementSystem, load_achievement_definitions
from .simulation import ActionUnitLedger
from .runtime import decode_rng, encode_rng, now_iso
from .world_state import (
    RELATION_LABELS, choose_weighted_race, encounter_weight, push_fifo_cache,
    race_pair, relation_status, split_race_pair,
)
from .war_system import WarSystemMixin
from .heavenly_court_system import HeavenlyCourtSystemMixin
from .natal_artifact_system import NatalArtifactSystemMixin
from .crafting_system import CraftingSystemMixin, crafted_artifact_bonuses, crafted_combat_effects
from .formation_system import (
    FormationSystemMixin, active_formation_profile, ensure_formation_state,
    formation_battle_experience_gain,
)
from .monster_bloodline_system import (
    MonsterBloodlineSystemMixin, bloodline_content_available,
    ensure_monster_bloodline_state, initialize_monster_bloodline,
    public_monster_bloodline,
)
from .monster_general_traits import grant_random_general_monster_trait
from .ghost_system import (
    GhostSystemMixin, ensure_ghost_cultivation_state, ghost_cultivation_active,
    grant_intrinsic_growth, grant_intrinsic_progression_if_new_highwater,
    grant_wangsheng, reincarnation_breakthrough_bonus,
)
from .intrigue_system import IntrigueSystemMixin
from .sage_system import SageSystemMixin
from .concubine_system import ConcubineSystemMixin, gender_name
from .possession_system import (
    advance_player_age, current_body_age, migrate_possession_timeline,
)


OPS = {
    "eq": operator.eq,
    "neq": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "in": lambda left, right: left in right,
    "contains": lambda left, right: right in left,
}

LEGACY_TRUE_DEMON_RACE_MAP = {
    "monster": "ancient_demon",
    "spirit": "heaven_demon",
    "woodborn": "blood_demon",
    "seafolk": "sea_demon",
    "featherfolk": "winged_demon",
    "stoneborn": "rock_demon",
    "cloudkin": "shadow_demon",
    "thunderkin": "flame_demon",
    "crystalfolk": "bone_demon",
    "starborn": "void_demon",
    "moonfolk": "soul_demon",
    "magnetfolk": "horn_demon",
    "silkkin": "corpse_demon",
    "miragefolk": "nightmare_demon",
    "sunwing": "flame_demon",
    "horned_drake": "horn_demon",
    "frostfolk": "frost_demon",
    "sandkin": "abyss_demon",
    "insectkin": "insect_demon",
}

class GameEngine(SageSystemMixin, ConcubineSystemMixin, IntrigueSystemMixin, FormationSystemMixin, CraftingSystemMixin, GhostSystemMixin, MonsterBloodlineSystemMixin, NatalArtifactSystemMixin, HeavenlyCourtSystemMixin, WarSystemMixin, MapTravelMixin, EconomySystemMixin, DemonicSystemMixin):
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
        if action == "commission" and player.realm_index == 0:
            raise ValueError("凡人尚无法承接修仙坊市委托")
        if action == "body_train":
            if player.body_technique is None:
                raise ValueError("必须先获得并配置一部炼体功法")
            if player.body_training >= int(WORLD_SYSTEMS["body_cultivation"]["max_layer"]):
                raise ValueError("炼体已经达到一百层极限")
            if player.awaiting_body_breakthrough or player.body_progress >= self._body_progress_required(player):
                raise ValueError("炼体积累已经圆满，请先手动冲击下一层")
        if action == "sense_train" and player.divine_sense_technique is None:
            raise ValueError("必须先获得并配置一部神识功法")
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
                sense = player.divine_sense_technique
                regional = self.maps.qi_gain_efficiencies(player.world, player.location_id)
                regional_multiplier = sum(
                    float(weight) * float(regional.get(source, 0))
                    for source, weight in sense.sources.items()
                )
                sense_gain = (
                    float(WORLD_SYSTEMS["demonic_cultivation"]["divine_sense_training_base"])
                    * (1 + sense.divine_sense_bonus * technique_scale(sense))
                    * technique_environment_multiplier(sense, player.world)
                    * regional_multiplier
                    * (1 + crafted_artifact_bonuses(player)["divine_sense_efficiency"])
                    * (1 + max(0.0, float(player.sage_effects.get("sense_multiplier", 0.0))))
                )
                player.divine_sense_experience += sense_gain
                total_sense_gain += sense_gain
                self._apply_action_resources(player, action, ledger.claim_resource_cost())
            elif action == "body_train":
                body_rules = WORLD_SYSTEMS["body_cultivation"]
                training_gain = (
                    rng.randint(*body_rules["progress_per_year"])
                    * (1 + 0.04 * max(0, player.body_technique.grade - 1))
                    * technique_environment_multiplier(player.body_technique, player.world)
                    * (
                        float(WORLD_SYSTEMS.get("monster_cultivation", {}).get("body_training_multiplier", 1.5))
                        if player.path == "monster" else 1.0
                    )
                    * (1 + crafted_artifact_bonuses(player)["body_training_efficiency"])
                )
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

        self._finish_sage_action(game)
        # 坊市只在一次玩家操作结束时刷新。旧逻辑在大乘一次行动的 1000 个
        # 年度中重建 1000 次相同规模的随机货架，最终只有最后一次可见。
        self._ensure_market(game, rng)

        self._compact_world_history(game)
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def _add_opportunity(self, player: Player, amount: float) -> float:
        before = player.opportunity
        player.opportunity = max(0.0, before + float(amount))
        actual_gain = player.opportunity - before
        if actual_gain > 0:
            grant_qi_experience(
                player, actual_gain,
                self.maps.qi_gain_efficiencies(player.world, player.location_id),
            )
        return actual_gain

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
            gain = float(WORLD_SYSTEMS["breakthrough"][f"{failure_type}_failure_heart_demon"])
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
            technique_bonus = float(player.body_technique.body_breakthrough_bonus)
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
        if ghost_cultivation_active(game.player) and item.breakthrough_bonus > 0:
            raise ValueError("阴魂不受血肉丹火重塑，此物无法助你破境。鬼修唯有自渡轮回，方能熟悉来路。")
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
        if offer["kind"] == "technique" and any(
            known.id == offer["content_id"] for known in game.player.known_techniques
        ):
            raise ValueError("你已经掌握这部功法")
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
            learn_technique(game.player, TECHNIQUE_CATALOG[offer["content_id"]])
            summary = f"你在{offer['market_name']}支付 {price} 枚灵石，购得《{offer['name']}》传承玉简。"
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
        if setting not in {"combat_popup", "achievement_popup", "auto_advance_player_wars"}:
            raise ValueError("未知设置项")
        game.settings[setting] = bool(enabled)
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
        form = TRANSFORMATION_CATALOG[form_id]
        if action == "store":
            if form_id in stored:
                raise ValueError("该变身已经存入本功法")
            if len(stored) >= technique.transformation_capacity:
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
            if len(active) >= technique.transformation_space:
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
                npc.affinity = (npc.affinity or 0) + 12
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
                companion["affinity"] = float(companion.get("affinity", 20)) + 1
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
                companion["affinity"] = float(companion.get("affinity", 20)) + 2
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
                companion["affinity"] = float(companion.get("affinity", 20)) + 3
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
                companion["affinity"] = float(companion.get("affinity", 20)) + 2
                result, summary = "companion_technique_replaced", f"{companion['name']}废去旧法，将《{technique.name}》改作主修功法。"
            else:
                raise ValueError("未知道侣互动")
        if player.dao_companion:
            source_npc = self._find_npc(game, str(player.dao_companion.get("id", "")))
            if source_npc:
                source_npc.affinity = float(player.dao_companion.get("affinity", source_npc.affinity or 0))
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
        npc.affinity = max(float(npc.affinity or 0), float(relation.get("affinity", 0))) + 4
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
            player.heart_demon += float(rules["companion_separation_heart_demon"])
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
                npc.affinity = (npc.affinity or 0) + 4
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

    @staticmethod
    def _party_invitation_chance(player: Player, npc: SectNpc, global_hostility: float = 0.0) -> float:
        config = WORLD_SYSTEMS["party"]
        realm_gap = max(0, npc.realm_index - player.realm_index)
        confidence_bonus = 0.0
        if player.realm_index >= npc.realm_index:
            confidence_bonus = min(
                float(config.get("lower_realm_bonus_cap", 0.22)),
                float(config.get("same_or_lower_realm_bonus", 0.12))
                + max(0, player.realm_index - npc.realm_index) * float(config.get("lower_realm_bonus_per_gap", 0.04)),
            )
        return max(0.02, min(
            0.9,
            float(config["invite_base_chance"]) + confidence_bonus
            + float(npc.affinity or 0) / 200 - global_hostility / 120 - realm_gap * 0.12,
        ))

    def _party_crossing_candidate(self, game: GameState, npc_id: str) -> dict[str, Any] | None:
        player = game.player
        npc = self._find_npc(game, npc_id)
        relation = next((entry for entry in [player.dao_companion, *player.dao_friends] if entry and str(entry.get("id")) == npc_id), None)
        source = relation or (npc.to_dict() if npc else None)
        if not source or not source.get("alive", True) or source.get("world") != player.world:
            return None
        requirements = {
            "human": (5, lambda layer: layer <= 3),
            "demon": (5, lambda layer: layer >= 1),
            "spirit": (8, lambda layer: layer == REALMS[8].layers),
            "true_demon": (8, lambda layer: layer == REALMS[8].layers),
        }
        required = requirements.get(player.world)
        if (
            not required or player.realm_index != required[0]
            or not required[1](player.layer)
        ):
            return None
        if not required or int(source.get("realm_index", -1)) != required[0] or not required[1](int(source.get("layer", 99))):
            return None
        return {"id":npc_id, "name":str(source.get("name", "无名队友"))}

    @staticmethod
    def _new_sects() -> dict[str, SectState]:
        sects = {
            sect_id: SectState(
                id=sect_id,
                name=FACTION_DEFINITIONS[sect_id]["name"],
                world=FACTION_DEFINITIONS[sect_id].get("world", "human"),
                npcs=[SectNpc(**copy.deepcopy(npc)) for npc in templates],
                description=FACTION_DEFINITIONS[sect_id].get("description", ""),
                path=FACTION_DEFINITIONS[sect_id].get("path", "dao"),
                allegiance_race=FACTION_DEFINITIONS[sect_id].get("allegiance_race"),
            )
            for sect_id, templates in FACTION_NPC_TEMPLATES.items()
        }
        for sect_id, sect in sects.items():
            for npc in sect.npcs:
                npc.faction_id = sect_id
                npc.world = sect.world
        return sects

    def _ensure_sects(self, game: GameState) -> None:
        fresh = self._new_sects()
        if game.world_rules_version < 2:
            game.sects = fresh
            game.world_rules_version = 6
        for sect_id, new_sect in fresh.items():
            if sect_id not in game.sects:
                game.sects[sect_id] = new_sect
                continue
            game.sects[sect_id].world = new_sect.world
            game.sects[sect_id].allegiance_race = new_sect.allegiance_race
            known_ids = {npc.id for npc in game.sects[sect_id].npcs}
            game.sects[sect_id].npcs.extend(npc for npc in new_sect.npcs if npc.id not in known_ids)
            templates = {npc.id: npc for npc in new_sect.npcs}
            for npc in game.sects[sect_id].npcs:
                if not npc.faction_id:
                    npc.faction_id = sect_id
                template = templates.get(npc.id)
                if not npc.spirit_root:
                    npc.spirit_root = (
                        template.spirit_root if template and template.spirit_root
                        else self._random_npc_root(npc.realm_index, random.Random(f"{game.seed}:{npc.id}"))
                    )
                if game.world_rules_version < 4 and template:
                    npc.path = template.path
                elif not npc.path or npc.path not in PATH_NAMES:
                    npc.path = template.path if template else self._random_npc_path(sect_id, random.Random(f"path:{game.seed}:{npc.id}"))
                npc.world = getattr(npc, "world", new_sect.world) or new_sect.world
                npc.race = getattr(npc, "race", "human") or "human"
                if not npc.treasure_item_id and not npc.treasure_looted:
                    npc.treasure_item_id = self._select_npc_treasure(
                        npc, random.Random(f"treasure:{game.seed}:{npc.id}")
                    )
                if npc.affinity is None:
                    npc.affinity = random.Random(f"affinity:{game.seed}:{npc.id}").uniform(-8, 12)
            self._compact_sect_roster(game, game.sects[sect_id])
        game.world_rules_version = max(game.world_rules_version, 7)

    def _compact_sect_roster(self, game: GameState, sect: SectState) -> bool:
        """Discard only stale dead recruit records once a sect's simulation roster is full."""
        cap = int(FACTION_SYSTEMS.get("max_roster_records", 48))
        if len(sect.npcs) <= cap:
            return False
        protected = {str(npc.get("id")) for npc in FACTION_NPC_TEMPLATES.get(sect.id, [])}
        protected.update(str(row.get("id")) for row in [
            game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples,
        ] if row and row.get("id"))
        for war in game.wars:
            if war.get("status") in {"active", "peace_ready"}:
                protected.update(war.get("roster", {}).get("attacker", []))
                protected.update(war.get("roster", {}).get("defender", []))
        removable = [npc for npc in sect.npcs if not npc.alive and npc.id not in protected]
        remove_ids = {npc.id for npc in removable[:max(0, len(sect.npcs) - cap)]}
        if not remove_ids:
            return False
        sect.npcs = [npc for npc in sect.npcs if npc.id not in remove_ids]
        return True

    @staticmethod
    def _compact_world_history(game: GameState) -> bool:
        """Bound old ambient world news while preserving the player's personal chronicle."""
        cap = int(WORLD_SYSTEMS.get("performance", {}).get("max_world_history_records", 6000))
        world_news = [record for record in game.history if "world_news" in record.tags]
        excess = len(world_news) - cap
        if excess <= 0:
            return False
        discard = {id(record) for record in world_news[:excess]}
        game.history = [record for record in game.history if id(record) not in discard]
        return True

    @staticmethod
    def _new_world_npcs() -> dict[str, SectNpc]:
        return {npc_id: copy.deepcopy(npc) for npc_id, npc in WORLD_NPC_TEMPLATES.items()}

    def _ensure_world_npcs(self, game: GameState) -> bool:
        fresh = self._new_world_npcs()
        changed = False
        # V6 以前没有保存固定 NPC 的模板基准。这里只记录真正发生过
        # 变更的旧基准；其后的 JSON 年龄调整均可通过存档里的基准通用迁移。
        legacy_initial_ages = {"xiang_zhili": 2810}
        for npc_id, npc in fresh.items():
            if npc_id not in game.world_npcs:
                game.world_npcs[npc_id] = npc
                changed = True
            current = game.world_npcs[npc_id]
            template_age = int(npc.age)
            recorded_age = game.world_npc_template_ages.get(npc_id)
            if recorded_age is None:
                legacy_age = legacy_initial_ages.get(npc_id)
                if legacy_age is not None and current.age >= legacy_age and template_age != legacy_age:
                    elapsed = max(0, int(current.age) - legacy_age)
                    current.age = template_age + elapsed
                    changed = True
                game.world_npc_template_ages[npc_id] = template_age
                changed = True
            elif recorded_age != template_age:
                elapsed = max(0, int(current.age) - int(recorded_age))
                current.age = template_age + elapsed
                game.world_npc_template_ages[npc_id] = template_age
                changed = True
            if not current.treasure_item_id and not current.treasure_looted:
                current.treasure_item_id = self._select_npc_treasure(
                    current, random.Random(f"treasure:{game.seed}:{current.id}")
                )
                changed = True
            if current.affinity is None:
                current.affinity = random.Random(f"affinity:{game.seed}:{current.id}").uniform(-12, 8)
                changed = True
        if game.world_rules_version < 7:
            game.world_rules_version = 7
            changed = True
        return changed

    def _enforce_world_realm_caps(self, game: GameState) -> bool:
        """Migrate pre-V8 saves so lower worlds cannot retain upper-world NPCs."""
        if game.world_rules_version >= 8:
            return False
        changed = False
        migrated_names: list[str] = []

        # This NPC used to have an invalid world id and a lower placeholder realm.
        # Preserve elapsed age and mutable state while applying the new fixed identity.
        template = WORLD_NPC_TEMPLATES.get("wu_xingyun")
        current = game.world_npcs.get("wu_xingyun")
        if template and current and (current.world != template.world or current.realm_index != template.realm_index):
            elapsed_age = max(0, current.age - 1210)
            for field_name in (
                "name", "title", "realm_index", "layer", "lifespan", "spirit_root",
                "cultivation_progress", "path", "race", "world",
            ):
                setattr(current, field_name, copy.deepcopy(getattr(template, field_name)))
            current.age = template.age + elapsed_age
            game.world_npc_template_ages[current.id] = template.age
            changed = True
            migrated_names.append(current.name)

        demon_cap = self._world_realm_cap("demon")
        for sect in game.sects.values():
            if sect.world != "demon":
                continue
            upper_members = [npc for npc in sect.npcs if npc.realm_index > demon_cap]
            if not upper_members:
                continue
            if sect.founded_by_npc:
                sect.world = "true_demon"
                for npc in sect.npcs:
                    npc.world = "true_demon"
                migrated_names.append(sect.name)
            else:
                upper_ids = {npc.id for npc in upper_members}
                sect.npcs = [npc for npc in sect.npcs if npc.id not in upper_ids]
                for npc in upper_members:
                    npc.world = "true_demon"
                    npc.faction_id = None
                    npc.departed_age = npc.departed_age or npc.age
                    npc.departure_reason = npc.departure_reason or "飞升真魔界"
                    game.notable_npcs.setdefault(npc.id, npc)
                    migrated_names.append(npc.name)
            changed = True

        for collection in (game.world_npcs.values(), game.notable_npcs.values()):
            for npc in collection:
                if npc.world == "demon" and npc.realm_index > demon_cap:
                    npc.world = "true_demon"
                    npc.departed_age = npc.departed_age or npc.age
                    npc.departure_reason = npc.departure_reason or "飞升真魔界"
                    migrated_names.append(npc.name)
                    changed = True

        related_people = [
            game.player.master, game.player.dao_companion,
            *game.player.dao_friends, *game.player.disciples, *game.player.disciple_requests,
        ]
        for person in related_people:
            if person and person.get("world") == "demon" and int(person.get("realm_index", 0)) > demon_cap:
                person["world"] = "true_demon"
                migrated_names.append(str(person.get("name", "无名修士")))
                changed = True
        for cached in game.encounter_npc_cache:
            cached_npc = cached.get("npc") if isinstance(cached.get("npc"), dict) else cached
            if cached_npc.get("world") == "demon" and int(cached_npc.get("realm_index", 0)) > demon_cap:
                cached_npc["world"] = "true_demon"
                changed = True

        game.world_rules_version = 8
        if migrated_names:
            names = "、".join(dict.fromkeys(migrated_names))
            game.history.append(HistoryRecord(
                "SYS_WORLD_REALM_CAP_MIGRATION", 1, game.player.age, "界面境界校正", None,
                "migrated", f"旧存档中超出魔界境界上限的{names}已迁入真魔界。",
                {"destination": "true_demon", "npc_count": len(set(migrated_names))},
                ["system", "migration", "ascension", "world:true_demon"],
            ))
        return changed or bool(migrated_names)

    def _migrate_true_demon_races(self, game: GameState) -> bool:
        """Move pre-V9 true-demon residents off the former shared spirit race table."""
        if game.world_rules_version >= 9:
            return False
        true_demon_races = {
            race_id for race_id, definition in RACE_DEFINITIONS.items()
            if "true_demon" in definition.get("worlds", [])
        }
        migrated = 0

        def migrate_record(record: Any) -> None:
            nonlocal migrated
            if isinstance(record, SectNpc):
                if record.world != "true_demon" or record.race in true_demon_races:
                    return
                record.race = LEGACY_TRUE_DEMON_RACE_MAP.get(record.race, "human")
                migrated += 1
                return
            if not isinstance(record, dict) or record.get("world") != "true_demon":
                return
            old_race = str(record.get("race", "human"))
            if old_race not in true_demon_races:
                record["race"] = LEGACY_TRUE_DEMON_RACE_MAP.get(old_race, "human")
                migrated += 1

        # Fixed sect characters adopt their redesigned canonical race while all
        # mutable cultivation, affinity and survival state remains untouched.
        fixed_races = {
            str(template["id"]): str(template.get("race", "human"))
            for sect_id, templates in FACTION_NPC_TEMPLATES.items()
            if FACTION_DEFINITIONS[sect_id].get("world") == "true_demon"
            for template in templates
        }
        for sect in game.sects.values():
            if sect.world != "true_demon":
                continue
            old_allegiance = str(sect.allegiance_race or "human")
            if old_allegiance not in true_demon_races:
                sect.allegiance_race = LEGACY_TRUE_DEMON_RACE_MAP.get(old_allegiance, "human")
                migrated += 1
            for npc in sect.npcs:
                canonical_race = fixed_races.get(npc.id)
                if canonical_race and npc.race != canonical_race:
                    npc.race = canonical_race
                    migrated += 1
                else:
                    migrate_record(npc)

        for collection in (game.world_npcs.values(), game.notable_npcs.values()):
            for npc in collection:
                migrate_record(npc)
        for cached in game.encounter_npc_cache:
            migrate_record(cached.get("npc") if isinstance(cached.get("npc"), dict) else cached)
        for person in (
            game.player.master, game.player.dao_companion,
            *game.player.dao_friends, *game.player.disciples, *game.player.disciple_requests,
            *game.player.offspring, *game.player.prisoners, *game.player.puppets,
        ):
            if person:
                migrate_record(person)
        if game.family and game.family.world == "true_demon":
            old_allegiance = str(game.family.allegiance_race or "human")
            if old_allegiance not in true_demon_races:
                game.family.allegiance_race = LEGACY_TRUE_DEMON_RACE_MAP.get(old_allegiance, "human")
                migrated += 1
            for npc in game.family.npcs:
                migrate_record(npc)

        player = game.player
        if player.world == "true_demon":
            for field_name in ("race", "lineage_race", "allegiance_race"):
                old_race = str(getattr(player, field_name) or player.race)
                if old_race not in true_demon_races:
                    setattr(player, field_name, LEGACY_TRUE_DEMON_RACE_MAP.get(old_race, "human"))
                    migrated += 1

        game.world_rules_version = 9
        if migrated:
            game.history.append(HistoryRecord(
                "SYS_TRUE_DEMON_RACE_MIGRATION", 1, player.age, "真魔诸族重订", None,
                "migrated", f"真魔界族谱已独立重订，旧存档中的 {migrated} 项族属记录完成迁移。",
                {"migrated_records": migrated},
                ["system", "migration", "race", "world_news", "world:true_demon"],
            ))
        return True

    @staticmethod
    def _ensure_race_relations(game: GameState) -> bool:
        changed = False
        diplomacy = RACE_SYSTEMS.get("diplomacy", {})
        for row in diplomacy.get("initial_relations", []):
            members = list(row.get("members", []))
            if len(members) != 2:
                continue
            key = race_pair(str(members[0]), str(members[1]))
            if key not in game.race_relations:
                game.race_relations[key] = {
                    "affinity": float(row.get("affinity", 0)),
                    "status": str(row.get("status", "neutral")),
                    "since_age": game.player.age,
                    "name": row.get("name"),
                }
                changed = True
        return changed

    @staticmethod
    def _actual_player_realm(player: Player) -> tuple[int, int]:
        if player.sealed_cultivation:
            return int(player.sealed_cultivation["realm_index"]), int(player.sealed_cultivation["layer"])
        return player.realm_index, player.layer

    @staticmethod
    def _governance_threshold(world: str) -> int:
        thresholds = WORLD_SYSTEMS["player_faction"]["governance_threshold"]
        # 新增界面按界面层级沿用人界/上界治理门槛，避免每开一个界面都
        # 必须复制一份纯数值配置。
        fallback = "human" if world == "human" else "spirit"
        return int(thresholds.get(world, thresholds[fallback]))

    @staticmethod
    def _world_supports(world: str, feature: str) -> bool:
        profile = WORLD_SYSTEMS.get("world_profiles", {}).get(world, {})
        return feature in profile.get("supports", [])

    @staticmethod
    def _world_realm_cap(world: str) -> int:
        profile = WORLD_SYSTEMS.get("world_profiles", {}).get(world, {})
        return max(0, min(len(REALMS) - 1, int(profile.get("npc_realm_cap", len(REALMS) - 1))))

    @staticmethod
    def _faction_meta(game: GameState, faction_id: str) -> dict[str, Any]:
        if faction_id in FACTION_DEFINITIONS:
            return dict(FACTION_DEFINITIONS[faction_id])
        sect = game.sects.get(faction_id)
        if not sect:
            return {"name": faction_id, "world": "human", "path": "dao", "description": "自立势力"}
        return {
            "name": sect.name, "world": sect.world, "path": sect.path,
            "description": sect.description or "由玩家开创的新宗门。",
            "allegiance_race": sect.allegiance_race or "human",
        }

    @staticmethod
    def _ensure_sect_relations(game: GameState) -> bool:
        changed = False
        active = [sect for sect in game.sects.values() if not sect.extinct]
        for index, first in enumerate(active):
            for second in active[index + 1:]:
                if first.world != second.world:
                    continue
                key = race_pair(first.id, second.id)
                if key not in game.sect_relations:
                    game.sect_relations[key] = {
                        "affinity": 0.0, "status": "neutral", "since_age": game.player.age,
                    }
                    changed = True
        return changed

    def _has_race_voice(self, game: GameState) -> bool:
        if self._intrigue_enabled():
            race_id = self._player_allegiance_race(game.player)
            return self._world_supports(game.player.world, "races") and self._intrigue_has_decision_authority(game, "race", race_id)
        realm_index, _ = self._actual_player_realm(game.player)
        required = int(WORLD_SYSTEMS["world_travel"]["required_realm"])
        return self._world_supports(game.player.world, "races") and self._player_allegiance_race(game.player) == "human" and realm_index >= required

    def _has_sect_voice(self, game: GameState) -> bool:
        player = game.player
        sect = game.sects.get(player.faction_id or "")
        if self._intrigue_enabled():
            return bool(sect and self._intrigue_has_decision_authority(game, "sect", sect.id))
        realm_index, _ = self._actual_player_realm(player)
        return bool(
            sect and not sect.extinct and sect.world == player.world
            and (sect.founded_by_player or realm_index >= self._governance_threshold(player.world))
        )

    def _has_family_voice(self, game: GameState) -> bool:
        family = game.family
        if self._intrigue_enabled():
            return bool(
                family and family.world == game.player.world
                and self._intrigue_has_decision_authority(game, "family", family.id)
            )
        return bool(
            family and not family.extinct and family.founded_by_player
            and family.world == game.player.world
        )

    @staticmethod
    def _select_npc_treasure(npc: SectNpc, rng: random.Random) -> str | None:
        tier = max(1, min(8, npc.realm_index))
        market_worlds = {str(row.get("world", "human")) for row in MARKET_GOODS}
        world = npc.world if npc.world in market_worlds else ("spirit" if npc.realm_index >= 6 else "human")
        candidates = [
            row for row in MARKET_GOODS
            if row["kind"] == "item" and row.get("world", "human") == world
            and int(row["tier"]) == tier
            and "currency" not in ITEM_CATALOG[row["content_id"]].tags
            and "root_manual" not in ITEM_CATALOG[row["content_id"]].tags
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda row: int(row["price"]), reverse=True)
        return str(rng.choice(candidates[: min(4, len(candidates))])["content_id"])

    def _npc_power(self, npc: SectNpc) -> float:
        treasure = ITEM_CATALOG.get(npc.treasure_item_id or "")
        return npc_combat_power(
            npc, expected_combat_power, self._npc_root_efficiency(npc.spirit_root), treasure
        ) * max(0.1, float(getattr(npc, "combat_factor", 1.0))) * max(0.35, 1 - int(getattr(npc, "wounds", 0)) * 0.15)

    def _npc_breakthrough_probability(self, npc: SectNpc) -> float:
        if npc.realm_index >= 9 or (npc.realm_index == 8 and npc.layer >= REALMS[8].layers):
            return 0.0
        return npc_breakthrough_chance(
            npc, FACTION_SYSTEMS["npc_cultivation"], self._npc_root_efficiency(npc.spirit_root)
        )

    @staticmethod
    def _hostility_key(kind: str, entity_id: str) -> str:
        return f"{kind}:{entity_id}"

    def _npc_faction_id(self, game: GameState, npc_id: str) -> str | None:
        npc = self._find_npc(game, npc_id)
        if npc and npc.faction_id and npc.faction_id in game.sects and not game.sects[npc.faction_id].extinct:
            return npc.faction_id
        return next(
            (sect_id for sect_id, sect in game.sects.items() if any(npc.id == npc_id for npc in sect.npcs)),
            None,
        )

    def _sect_members(self, game: GameState, sect: SectState) -> list[SectNpc]:
        members = {npc.id:npc for npc in sect.npcs}
        for npc in [*game.world_npcs.values(), *game.notable_npcs.values()]:
            if npc.faction_id == sect.id:
                members[npc.id] = npc
        return list(members.values())

    def _find_npc(self, game: GameState, npc_id: str) -> SectNpc | None:
        if npc_id in game.world_npcs:
            return game.world_npcs[npc_id]
        if npc_id in game.notable_npcs:
            return game.notable_npcs[npc_id]
        return next((npc for sect in game.sects.values() for npc in sect.npcs if npc.id == npc_id), None)

    def _persist_relationship_npc(self, game: GameState, relation: dict[str, Any], reason: str) -> SectNpc:
        existing = self._find_npc(game, str(relation.get("id", "")))
        if existing:
            return existing
        npc = SectNpc(
            id=str(relation.get("id") or f"relation_{uuid.uuid4().hex[:12]}"),
            name=str(relation.get("name", "无名修士")), title=reason,
            realm_index=int(relation.get("realm_index", 0)), layer=int(relation.get("layer", 1)),
            age=int(relation.get("age", 18)), lifespan=relation.get("lifespan"),
            spirit_root=str(relation.get("spirit_root", "none")),
            cultivation_progress=float(relation.get("cultivation_progress", 0)),
            path=str(relation.get("path", "dao")), race=str(relation.get("race", "human")),
            world=str(relation.get("world", game.player.world)), alive=bool(relation.get("alive", True)),
            death_reason=relation.get("death_reason"), affinity=float(relation.get("affinity", 0)),
            gender=str(relation.get("gender", "")),
            treasure_item_id=next(iter(relation.get("items", {})), None),
            next_tribulation_age=relation.get("next_tribulation_age"),
            tribulation_count=int(relation.get("tribulation_count", 0)),
            tribulation_power=relation.get("tribulation_power"),
        )
        game.notable_npcs[npc.id] = npc
        relation["id"] = npc.id
        relation["source"] = "world"
        return npc

    def _adjust_person_affinity(self, game: GameState, npc_id: str, delta: float) -> float:
        npc = self._find_npc(game, npc_id)
        relation = next((entry for entry in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples] if entry and str(entry.get("id")) == npc_id), None)
        base = float(relation.get("affinity", 0)) if relation else float(npc.affinity or 0) if npc else 0.0
        value = base + float(delta)
        if npc:
            npc.affinity = value
        for relation in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples]:
            if relation and str(relation.get("id")) == npc_id:
                relation["affinity"] = value
        return value

    def _set_person_affinity(self, game: GameState, npc_id: str, value: float) -> float:
        """Set, rather than add, affinity on both the persistent NPC and relation snapshot."""
        affinity = max(-100.0, min(100.0, float(value)))
        npc = self._find_npc(game, npc_id)
        if npc:
            npc.affinity = affinity
        for relation in [
            game.player.master, game.player.dao_companion,
            *game.player.dao_friends, *game.player.disciples,
        ]:
            if relation and str(relation.get("id")) == npc_id:
                relation["affinity"] = affinity
        return affinity

    @staticmethod
    def _revenge_cooldown_key(scope: str, family: str = "", adversary_id: str = "") -> str:
        suffix = ":".join(part for part in (family, adversary_id) if part)
        return f"revenge_cooldown:{scope}" + (f":{suffix}" if suffix else "")

    def _revenge_ready(self, game: GameState, family: str, adversary_id: str) -> bool:
        """All revenge sources share one global gate and also retain per-source gates."""
        global_next = int(game.governance_actions.get(self._revenge_cooldown_key("next"), -1))
        source_next = int(game.governance_actions.get(
            self._revenge_cooldown_key("next", family, adversary_id), -1,
        ))
        return game.diplomacy_unit >= max(global_next, source_next)

    def _record_revenge_trigger(self, game: GameState, family: str, adversary_id: str) -> int:
        """Start an escalating action-unit cooldown after a revenge event is opened."""
        rules = WORLD_SYSTEMS["relationship"]
        base = max(1, int(rules.get("revenge_cooldown_base_units", 3)))
        increment = max(0, int(rules.get("revenge_cooldown_increment_units", 2)))
        maximum = max(base, int(rules.get("revenge_cooldown_max_units", 15)))
        global_count_key = self._revenge_cooldown_key("count")
        source_count_key = self._revenge_cooldown_key("count", family, adversary_id)
        global_count = int(game.governance_actions.get(global_count_key, 0)) + 1
        source_count = int(game.governance_actions.get(source_count_key, 0)) + 1
        game.governance_actions[global_count_key] = global_count
        game.governance_actions[source_count_key] = source_count
        interval = min(maximum, base + (global_count - 1) * increment)
        next_unit = game.diplomacy_unit + interval
        game.governance_actions[self._revenge_cooldown_key("next")] = next_unit
        game.governance_actions[
            self._revenge_cooldown_key("next", family, adversary_id)
        ] = next_unit
        return interval

    @staticmethod
    def _random_npc_path(faction_id: str, rng: random.Random) -> str:
        weights = FACTION_SYSTEMS["npc_path_distribution"].get(
            faction_id, {"dao": 0.55, "confucian": 0.15, "buddhist": 0.10, "demonic": 0.10, "ghost": 0.05, "monster": 0.05},
        )
        roll = rng.random()
        selected = next(reversed(weights))
        for path, weight in weights.items():
            roll -= float(weight)
            if roll <= 0:
                selected = path
                break
        return selected

    @staticmethod
    def _random_npc_root(realm_index: int, rng: random.Random) -> str:
        """人界 NPC 只生成常规五行或变异灵根，且高境界自然筛去伪灵根。"""
        distributions = FACTION_SYSTEMS["npc_root_distribution"]
        weights = distributions.get(str(min(5, max(1, realm_index))), distributions["1"])
        families = list(weights)
        roll = rng.random() * sum(float(weights[name]) for name in families)
        family = families[-1]
        for name in families:
            weight = float(weights[name])
            if weight <= 0:
                continue
            roll -= weight
            if roll <= 0:
                family = name
                break
        pools = {
            "pseudo": [root_id for root_id in ROOT_DEFINITIONS if root_id.startswith("pseudo_")],
            "heavenly": [root_id for root_id in ROOT_DEFINITIONS if root_id.startswith("heavenly_")],
            "supreme": [root_id for root_id in ROOT_DEFINITIONS if root_id.startswith("supreme_")],
            "mutated": [root_id for root_id in ROOT_DEFINITIONS if root_id.startswith("mutated_")],
        }
        return rng.choice(pools[family])

    @staticmethod
    def _npc_root_name(root_id: str) -> str:
        return ROOT_DEFINITIONS.get(root_id, {"name": "灵根未明"})["name"]

    @staticmethod
    def _npc_root_efficiency(root_id: str) -> float:
        return float(ROOT_DEFINITIONS.get(root_id, {"efficiency": 1.0})["efficiency"])

    @staticmethod
    def _mortal_root_completion_chance(player: Player) -> float:
        if player.age < 35 or not player.born_rootless or player.spirit_root != "none":
            return 0.0
        if not any(item.id.startswith("jinque_") and item.quantity > 0 for item in player.inventory):
            return 0.0
        return min(1.0, (player.age - 34) * 0.01)

    def _maybe_mortal_root_completion(self, game: GameState, rng: random.Random) -> bool:
        chance = self._mortal_root_completion_chance(game.player)
        if chance <= 0 or rng.random() >= chance:
            return False
        event = self.events_by_id["EVT_MORTAL_ROOT_COMPLETE_001"]
        game.pending_event = self._instantiate_event(event, game, rng)
        game.pending_event["body"] += f"（本年逆天改命机率 {chance:.0%}）"
        return True

    def _maybe_probability_story_event(self, game: GameState, rng: random.Random) -> bool:
        for event in self.events:
            if "probability_gate" not in event.get("tags", []) or event["id"] == "EVT_XIANG_NODE_001":
                continue
            world_tags = {tag for tag in event.get("tags", []) if tag.startswith("world:")}
            if world_tags and f"world:{game.player.world}" not in world_tags:
                continue
            event_id = event["id"]
            if any(record.event_id == event_id for record in game.history):
                continue
            if not self._condition(event.get("conditions", {}), game):
                continue
            if self._roll_escalating_event(game, event, rng):
                return True
        return False

    def _maybe_artifact_synthesis(self, game: GameState, rng: random.Random) -> bool:
        event = self.events_by_id["EVT_FIVE_POLES_CRAFT_001"]
        if has_item(game.player, "yuanhe_five_poles_mountain"):
            return False
        if any(record.event_id == event["id"] and record.age == game.player.age for record in game.history[-2:]):
            return False
        if not self._condition(event["conditions"], game):
            return False
        game.pending_event = self._instantiate_event(event, game, rng)
        return True

    def _maybe_xiang_node_event(self, game: GameState, rng: random.Random) -> bool:
        event = self.events_by_id["EVT_XIANG_NODE_001"]
        if any(record.event_id == event["id"] for record in game.history):
            return False
        if has_item(game.player, "spirit_node_info") or not self._condition(event["conditions"], game):
            return False
        return self._roll_escalating_event(game, event, rng)

    def _roll_escalating_event(self, game: GameState, event: dict[str, Any], rng: random.Random) -> bool:
        trigger = event["trigger"]
        milestone = str(trigger["milestone"])
        game.player.milestones.setdefault(milestone, game.player.age)
        attempts = int(game.story_trigger_attempts.get(milestone, 0))
        increment = float(trigger.get("unit_increment", trigger.get("annual_increment", 0)))
        chance = min(1.0, float(trigger["base_chance"]) + attempts * increment)
        if rng.random() >= chance:
            game.story_trigger_attempts[milestone] = attempts + 1
            return False
        game.pending_event = self._instantiate_event(event, game, rng)
        game.pending_event["body"] += f"（本行动单位触发概率 {chance:.0%}）"
        return True

    def _maybe_faction_event(self, game: GameState, rng: random.Random) -> bool:
        faction_id = game.player.faction_id
        if (
            not faction_id
            or faction_id not in game.sects
            or game.sects[faction_id].extinct
            or self._faction_meta(game, faction_id).get("world", "human") != game.player.world
            or rng.random() >= 0.30
        ):
            return False
        candidates: list[tuple[dict[str, Any], float]] = []
        for event in self.events:
            tags = event.get("tags", [])
            world_tags = [tag for tag in tags if tag.startswith("world:")]
            if (
                int(WORLD_SYSTEMS.get("world_profiles", {}).get(game.player.world, {}).get("tier", 1)) >= 3
                and f"world:{game.player.world}" not in world_tags
            ):
                continue
            if world_tags and f"world:{game.player.world}" not in world_tags:
                continue
            if "faction" not in tags or "faction_join" in tags:
                continue
            if "revenge" in tags and not self._revenge_ready(game, "faction", str(event["id"])):
                continue
            if self._intrigue_enabled() and any(
                marker in f"{event.get('title', '')}{event.get('body', '')}"
                for marker in ("争位", "夺位", "排挤", "竞争")
            ) and not self._intrigue_pressure_position_occupied(game, faction_id):
                # With the DLC, political rivals must occupy a scarce office;
                # an empty seat never invents an imaginary competitor.
                continue
            if "faction_unique" in tags and f"faction:{faction_id}" not in tags:
                continue
            if not self._condition(event.get("conditions", {}), game):
                continue
            if event.get("repeat") == "once" and any(h.event_id == event["id"] for h in game.history):
                continue
            candidates.append((event, max(0.0, float(event.get("weight", 1)))))
        total = sum(weight for _, weight in candidates)
        if total <= 0:
            return False
        roll = rng.random() * total
        for event, weight in candidates:
            roll -= weight
            if roll <= 0:
                game.pending_event = self._instantiate_event(event, game, rng)
                if "revenge" in event.get("tags", []):
                    interval = self._record_revenge_trigger(game, "faction", str(event["id"]))
                    game.pending_event.setdefault("runtime", {})["revenge_cooldown_units"] = interval
                return True
        selected = candidates[-1][0]
        game.pending_event = self._instantiate_event(selected, game, rng)
        if "revenge" in selected.get("tags", []):
            interval = self._record_revenge_trigger(game, "faction", str(selected["id"]))
            game.pending_event.setdefault("runtime", {})["revenge_cooldown_units"] = interval
        return True

    def _maybe_wanted_encounter(self, game: GameState, rng: random.Random) -> bool:
        player = game.player
        config = WORLD_SYSTEMS["faction_conflict"]
        coalition_threshold = float(
            config["demonic_coalition_fame_threshold"]
            if player.path == "demonic" else config["coalition_fame_threshold"]
        )
        key = self._hostility_key("world", player.world)
        subdued_flag = f"world_coalition_subdued:{player.world}"
        if subdued_flag in player.story_flags:
            # “全界”不是会重建组织结构的实体；一旦被玩家压服，本界不能
            # 仅因威名仍高就立即重发同一份围杀令。
            player.hostility[key] = 0.0
        else:
            amnesty_fame = self._world_coalition_amnesty_fame(player, player.world)
            issue_threshold = max(coalition_threshold, amnesty_fame)
            if player.fame > issue_threshold:
                player.hostility[key] = max(
                    player.hostility.get(key, 0),
                    player.fame - issue_threshold + float(config["wanted_threshold"]),
                )
        hostiles: list[tuple[str, float]] = []
        for key, value in list(player.hostility.items()):
            if value <= float(config["wanted_threshold"]):
                continue
            player.milestones["became_wanted_target"] = 1
            state = self._hostility_entity_state(game, key)
            if state["status"] == "inactive":
                continue
            if state["status"] == "friendly":
                player.hostility[key] = 0.0
                continue
            if state["status"] == "fallen":
                self._queue_wanted_settlement(game, key, state, rng, fallen=True)
                return True
            if (
                self._player_battle_power(game) >= float(state["power"])
                or int(state["max_realm"]) <= self._actual_player_realm(player)[0]
            ):
                self._queue_wanted_settlement(game, key, state, rng, fallen=False)
                return True
            if not self._revenge_ready(game, "wanted", key):
                continue
            hostiles.append((key, value))
        if not hostiles:
            return False
        chance = min(0.92, float(config["encounter_base_chance"]) + max(value for _, value in hostiles) * float(config["encounter_hostility_scale"]))
        if rng.random() >= chance:
            return False
        key, hostility = rng.choices(hostiles, weights=[value for _, value in hostiles], k=1)[0]
        kind, entity_id = key.split(":", 1)
        target = self._wanted_target(game, kind, entity_id, hostility, rng)
        self._cache_encounter_target(game, target, rng)
        event = self.events_by_id["EVT_WANTED_ENCOUNTER_001"]
        game.pending_event = self._instantiate_event(event, game, rng)
        game.pending_event["runtime"] = {"hostility_key": key, "hostility": hostility, "target": target}
        game.pending_event["body"] = game.pending_event["body"].replace("{pursuer}", self._hostility_name(key, game))
        if len(target.get("members", [])) > 1:
            game.pending_event["body"] += f" 此次追兵共有{len(target['members'])}人，合计战斗力约{target['target_power']:.0f}。"
        interval = self._record_revenge_trigger(game, "wanted", key)
        game.pending_event["runtime"]["revenge_cooldown_units"] = interval
        return True

    @staticmethod
    def _world_coalition_amnesty_fame(player: Player, world: str) -> float:
        prefix = f"world_coalition_amnesty:{world}:"
        values = []
        for flag in player.story_flags:
            if not flag.startswith(prefix):
                continue
            try:
                values.append(float(flag[len(prefix):]))
            except ValueError:
                continue
        return max(values, default=0.0)

    @staticmethod
    def _record_world_coalition_amnesty(player: Player, world: str) -> None:
        prefix = f"world_coalition_amnesty:{world}:"
        player.story_flags = [flag for flag in player.story_flags if not flag.startswith(prefix)]
        player.story_flags.append(f"{prefix}{max(0.0, player.fame):.1f}")

    def _player_protected_npc_ids(self, game: GameState) -> set[str]:
        player = game.player
        protected = {
            str(row.get("id")) for row in [
                player.master, player.dao_companion, *player.dao_friends, *player.disciples,
            ] if row and row.get("id")
        }
        own_sect = game.sects.get(player.faction_id or "")
        if own_sect and not own_sect.extinct:
            protected.update(npc.id for npc in self._sect_members(game, own_sect) if npc.alive)
        if game.family and not game.family.extinct:
            protected.update(npc.id for npc in game.family.npcs if npc.alive)
        protected.update(self._retaliatory_relationship_ids(game))
        return protected

    def _hostility_entity_members(self, game: GameState, kind: str, entity_id: str) -> list[SectNpc]:
        world = game.player.world
        if kind in {"sect", "family"}:
            entity = game.sects.get(entity_id)
            if entity is None and game.family and game.family.id == entity_id:
                entity = game.family
            return [
                npc for npc in self._sect_members(game, entity)
                if npc.alive and npc.world == world
            ] if entity else []
        people = list({npc.id:npc for npc in self._all_world_npcs(game)}.values())
        if kind == "race":
            return [npc for npc in people if npc.alive and npc.world == world and npc.race == entity_id]
        if kind == "world":
            return [npc for npc in people if npc.alive and npc.world == world]
        return []

    def _hostility_entity_state(self, game: GameState, key: str) -> dict[str, Any]:
        kind, entity_id = key.split(":", 1)
        player = game.player
        if kind == "world" and entity_id != player.world:
            return {"status":"inactive"}
        if kind == "race" and (
            not self._world_supports(player.world, "races")
            or player.world not in RACE_DEFINITIONS.get(entity_id, {}).get("worlds", [])
        ):
            return {"status":"inactive"}
        entity = None
        if kind in {"sect", "family"}:
            entity = game.sects.get(entity_id)
            if entity is None and game.family and game.family.id == entity_id:
                entity = game.family
            if entity and entity.world != player.world:
                return {"status":"inactive"}
        own_entity = (
            (kind == "sect" and entity_id == player.faction_id)
            or (kind == "family" and game.family and entity_id == game.family.id)
            or (kind == "race" and entity_id == self._player_allegiance_race(player))
        )
        if own_entity:
            return {"status":"friendly"}
        raw_members = self._hostility_entity_members(game, kind, entity_id)
        if (entity and entity.extinct) or not raw_members:
            return {"status":"fallen", "kind":kind, "entity_id":entity_id, "members":[]}
        members = [npc for npc in raw_members if npc.id not in self._player_protected_npc_ids(game)]
        if not members:
            return {"status":"friendly"}
        powers = sorted((self._npc_power(npc) for npc in members), reverse=True)[:5]
        return {
            "status":"active", "kind":kind, "entity_id":entity_id, "members":members,
            "power":sum(powers), "max_realm":max(npc.realm_index for npc in members),
        }

    def _queue_wanted_settlement(
        self, game: GameState, key: str, state: dict[str, Any], rng: random.Random, *, fallen: bool,
    ) -> None:
        event_id = "EVT_POWER_FALL_001" if fallen else "EVT_WANTED_NEGOTIATION_001"
        event = self._instantiate_event(self.events_by_id[event_id], game, rng)
        name = self._hostility_name(key, game)
        event["body"] = event["body"].replace("{pursuer}", name)
        event["runtime"] = {
            "hostility_key":key, "kind":state.get("kind", key.split(":", 1)[0]),
            "entity_id":state.get("entity_id", key.split(":", 1)[1]), "entity_name":name,
            "member_ids":[npc.id for npc in state.get("members", [])],
            "power":round(float(state.get("power", 0)), 1),
        }
        if fallen:
            titles = {"sect":"宗门的陨落", "family":"家族的陨落", "race":"种族势力的陨落", "world":"围杀令的陨落"}
            event["title"] = titles.get(event["runtime"]["kind"], "势力的陨落")
            game.player.hostility[key] = 0.0
        else:
            kind = event["runtime"]["kind"]
            own_sect = game.sects.get(game.player.faction_id or "")
            for choice in event["choices"]:
                if choice["id"] == "dissolve" and kind not in {"sect", "family"}:
                    choice["enabled"] = False
                    choice["disabled_reason"] = "种族与全界势力不能以解散宗门的方式处置"
                if choice["id"] == "sect_vassal" and (not own_sect or kind not in {"sect", "family"}):
                    choice["enabled"] = False
                    choice["disabled_reason"] = "需要拥有当前宗门，且谈判对象必须是宗门或家族"
        game.pending_event = event

    def _resolve_wanted_settlement(
        self, game: GameState, pending: dict[str, Any], mode: str, rng: random.Random,
    ) -> tuple[str, str]:
        runtime = pending.get("runtime", {})
        key = str(runtime.get("hostility_key", ""))
        if not key or ":" not in key:
            raise ValueError("议和对象已经不存在")
        kind = str(runtime.get("kind", key.split(":", 1)[0]))
        entity_id = str(runtime.get("entity_id", key.split(":", 1)[1]))
        name = str(runtime.get("entity_name", self._hostility_name(key, game)))
        game.player.hostility[key] = 0.0
        if kind == "world":
            subdued_flag = f"world_coalition_subdued:{entity_id}"
            if subdued_flag not in game.player.story_flags:
                game.player.story_flags.append(subdued_flag)
        if mode == "fallen":
            return "pursuit_ended", f"{name}已经覆灭，针对你的追杀与通缉至此自动终止。"

        members = self._hostility_entity_members(game, kind, entity_id)
        target = max(members, key=self._npc_power, default=None)
        if mode == "compensation":
            amount = max(500, int(max(1.0, float(runtime.get("power", 1))) ** 0.5) * 80)
            add_item(game.player, "spirit_stone", amount)
            return "compensated", f"{name}交出下品灵石 ×{amount}作为巨额赔偿，并撤销全部追杀令。"
        if mode == "dissolve":
            entity = game.sects.get(entity_id)
            if entity is None and game.family and game.family.id == entity_id:
                entity = game.family
            if not entity or kind not in {"sect", "family"}:
                raise ValueError("该类势力不能就地解散")
            entity.extinct = True
            game.player.milestones["became_wanted_target"] = 1
            game.player.milestones["dissolved_wanted_power"] = 1
            for npc in members:
                npc.faction_id = None
                game.notable_npcs.setdefault(npc.id, npc)
            return "dissolved", f"你勒令{name}撤下门庭、解散传承；幸存者各自散去，旧通缉令失效。"
        if mode in {"personal_vassal", "sect_vassal"}:
            own_sect = game.sects.get(game.player.faction_id or "")
            if mode == "sect_vassal" and (not own_sect or kind not in {"sect", "family"}):
                raise ValueError("当前条件无法将对方纳为本宗附庸")
            if mode == "sect_vassal" and own_sect:
                relation = game.sect_relations.setdefault(
                    race_pair(own_sect.id, entity_id), {"affinity":0.0, "since_age":game.player.age},
                )
                relation.update(status="vassal", affinity=70.0, since_age=game.player.age,
                                overlord=own_sect.id, subject=entity_id)
                return "sect_vassal", f"{name}交出外交与征召权，成为{own_sect.name}的附庸。"
            flag = f"personal_vassal:{kind}:{entity_id}"
            if flag not in game.player.story_flags:
                game.player.story_flags.append(flag)
            return "personal_vassal", f"{name}向你本人奉上臣服契约，承诺不再追杀并听候你的号令。"
        if mode == "hostages":
            amount = max(200, int(max(1.0, float(runtime.get("power", 1))) ** 0.5) * 35)
            add_item(game.player, "spirit_stone", amount)
            if target:
                game.player.prisoners.append({
                    "id":target.id, "npc_id":target.id, "name":target.name,
                    "realm_index":target.realm_index, "layer":target.layer,
                    "realm_name":self._npc_realm_name(target), "path":target.path,
                    "path_name":PATH_NAMES.get(target.path, target.path), "race":target.race,
                    "affinity":-80.0, "combat_power":round(self._npc_power(target), 1),
                    "main_technique_id":self._default_npc_main_technique(target),
                    "captured_age":game.player.age, "source":f"settlement:{kind}",
                })
                target.alive = False
                target.death_reason = f"被{game.player.name}扣作议和人质"
                return "hostages", f"{name}交出灵石 ×{amount}，并将最强者{target.name}交给你作为人质。"
            return "hostages", f"{name}已无强者可交，只得献上灵石 ×{amount}并永远撤销追杀。"
        raise ValueError("未知议和条件")

    def _personal_npcs(self, game: GameState) -> list[SectNpc]:
        return list({
            npc.id:npc for npc in self._all_world_npcs(game)
            if npc.alive and npc.world == game.player.world and npc.id != "player"
        }.values())

    def _high_affinity_npcs(self, game: GameState, exclude_id: str = "") -> list[SectNpc]:
        threshold = float(WORLD_SYSTEMS["relationship"]["positive_affinity_threshold"])
        people = [npc for npc in self._personal_npcs(game) if npc.id != exclude_id and float(npc.affinity or 0) >= threshold]
        known = {npc.id for npc in people}
        for relation in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples]:
            if not relation or str(relation.get("id")) in known or str(relation.get("id")) == exclude_id:
                continue
            if relation.get("alive", True) and relation.get("world") == game.player.world and float(relation.get("affinity", 0)) >= threshold:
                people.append(self._persist_relationship_npc(game, relation, "交好修士"))
        return people

    def _maybe_affinity_gift(self, game: GameState, rng: random.Random) -> bool:
        people = self._high_affinity_npcs(game)
        if not people:
            return False
        rules = WORLD_SYSTEMS["relationship"]
        chance = min(0.32, float(rules["positive_event_base_chance"]) + len(people) * float(rules["positive_event_per_person"]))
        if rng.random() >= chance:
            return False
        npc = rng.choices(people, weights=[max(1.0,float(person.affinity or 0)) for person in people], k=1)[0]
        event = self.events_by_id["EVT_PERSONAL_AFFINITY_GIFT_001"]
        game.pending_event = self._instantiate_event(event, game, rng)
        game.pending_event["runtime"] = {"npc_id":npc.id,"npc_name":npc.name,"npc_realm_index":npc.realm_index}
        game.pending_event["body"] = game.pending_event["body"].replace("{npc_name}",npc.name)
        return True

    def _maybe_personal_revenge(self, game: GameState, rng: random.Random) -> bool:
        rules = WORLD_SYSTEMS["relationship"]
        threshold = float(rules["hostile_affinity_threshold"])
        protected_ids = self._retaliatory_relationship_ids(game)
        enemies = [
            npc for npc in self._personal_npcs(game)
            if float(npc.affinity or 0) <= threshold and npc.id not in protected_ids
            and self._revenge_ready(game, "personal", npc.id)
        ]
        enemies = self._filter_personal_revenge_by_protection(game, enemies, rng)
        if not enemies:
            return False
        allies = self._high_affinity_npcs(game)
        protection = min(float(rules["ally_protection_cap"]), len(allies) * float(rules["ally_protection_per_person"]))
        severity = max(abs(float(npc.affinity or 0) - threshold) for npc in enemies)
        chance = min(0.75, float(rules["revenge_base_chance"]) + severity * float(rules["revenge_affinity_scale"])) * (1 - protection)
        if rng.random() >= chance:
            return False
        enemy = rng.choices(enemies, weights=[max(1.0,abs(float(npc.affinity or 0))) for npc in enemies], k=1)[0]
        race_definition = RACE_DEFINITIONS.get(enemy.race,RACE_DEFINITIONS["human"])
        target = {
            "target_name":enemy.name,"target_power":self._npc_power(enemy),"primary_power":self._npc_power(enemy),
            "target_realm_index":enemy.realm_index,"target_layer":enemy.layer,
            "target_realm_visible":enemy.realm_index <= game.player.realm_index + 1,
            "target_realm_display":self._npc_realm_name(enemy) if enemy.realm_index <= game.player.realm_index + 1 else "无法看清",
            "combat_type":"cultivator","race":enemy.race,"race_name":race_definition["name"],
            "race_description":race_definition["description"],"world":enemy.world,"npc_id":enemy.id,
            "faction_id":self._npc_faction_id(game,enemy.id),"treasure_item_id":enemy.treasure_item_id,
            "kill_karma":False,"action":"revenge",
        }
        event = self.events_by_id["EVT_PERSONAL_REVENGE_001"]
        game.pending_event = self._instantiate_event(event, game, rng)
        best_ally = max((npc for npc in allies if npc.id != enemy.id),key=self._npc_power,default=None)
        sect = game.sects.get(game.player.faction_id or "")
        sect_defenders = [npc for npc in self._sect_members(game,sect) if npc.alive and npc.id != enemy.id] if sect else []
        game.pending_event["runtime"] = {
            "target":target,"npc_id":enemy.id,
            "ally_id":best_ally.id if best_ally else None,"ally_name":best_ally.name if best_ally else None,
            "sect_support_power":max((self._npc_power(npc) for npc in sect_defenders),default=0.0),
            "chance":round(chance,3),"protection":round(protection,3),
        }
        game.pending_event["body"] = game.pending_event["body"].replace("{npc_name}",enemy.name).replace("{target_power}",f"{target['target_power']:.0f}")
        for choice in game.pending_event["choices"]:
            if choice["id"] == "ally":
                choice["enabled"] = best_ally is not None
                if best_ally is None: choice["disabled_reason"] = "当前没有愿意驰援的高好感修士"
                else: choice["text"] += f"（{best_ally.name}）"
            elif choice["id"] == "sect":
                choice["enabled"] = bool(sect_defenders)
                if not sect_defenders: choice["disabled_reason"] = "当前没有可接应你的宗门同道"
        interval = self._record_revenge_trigger(game, "personal", enemy.id)
        game.pending_event["runtime"]["revenge_cooldown_units"] = interval
        return True

    def _wanted_target(
        self, game: GameState, kind: str, entity_id: str, hostility: float, rng: random.Random,
    ) -> dict[str, Any]:
        player = game.player
        desired_realm = min(8, player.realm_index + max(0, int(hostility // 45)))
        candidates = [
            npc for npc in self._hostility_entity_members(game, kind, entity_id)
            if npc.id not in self._player_protected_npc_ids(game) and npc.realm_index >= player.realm_index
        ]
        if candidates:
            candidates.sort(key=lambda npc: (abs(npc.realm_index - desired_realm), -npc.realm_index, -npc.layer))
            npc = candidates[0]
            race_def = RACE_DEFINITIONS.get(npc.race, RACE_DEFINITIONS["human"])
            target = {
                "target_name": npc.name, "target_power": self._npc_power(npc), "primary_power": self._npc_power(npc),
                "target_realm_index": npc.realm_index, "target_layer": npc.layer,
                "target_realm_visible": npc.realm_index <= player.realm_index + 1,
                "target_realm_display": self._npc_realm_name(npc) if npc.realm_index <= player.realm_index + 1 else "无法看清",
                "combat_type": "cultivator", "race": npc.race, "race_name": race_def["name"],
                "race_description": race_def["description"], "world": player.world,
                "npc_id": npc.id, "faction_id": self._npc_faction_id(game, npc.id),
                "treasure_item_id": npc.treasure_item_id, "path":npc.path,
            }
            return self._add_enemy_party(target, ACTIONS["slay"]["combat"], rng)
        race_id = entity_id if kind == "race" and entity_id in RACE_DEFINITIONS else "human"
        settings = dict(ACTIONS["slay"]["combat"])
        offset = desired_realm - player.realm_index
        settings["realm_offsets"] = [[offset, 1.0]]
        target = self._generate_cultivator_target(player, "追缉使", settings, rng, game=game, forced_race=race_id)
        target["race"] = race_id
        target["race_name"] = RACE_DEFINITIONS[race_id]["name"]
        target["race_description"] = RACE_DEFINITIONS[race_id]["description"]
        target["faction_id"] = entity_id if kind in {"sect", "family"} else None
        for member in target.get("members", []):
            member["race"] = race_id
            member["faction_id"] = target.get("faction_id")
        return target

    def _resolve_wanted_response(
        self, game: GameState, pending: dict[str, Any], response: str, rng: random.Random,
    ) -> tuple[str, str]:
        runtime = pending.get("runtime", {})
        key = str(runtime.get("hostility_key", "world:unknown"))
        target = runtime.get("target") or {}
        config = WORLD_SYSTEMS["faction_conflict"]
        if response == "fight":
            target["kill_karma"] = True
            target["non_story_combat"] = True
            result, summary = self._combat(game, target, True, rng)
            game.player.hostility[key] = game.player.hostility.get(key, 0) + float(config["fight_hostility_gain"])
            if result == "defeat" and game.player.alive:
                custody = self._imprison_or_execute(game, key, rng)
                summary += " " + custody
            return result, summary
        if response == "surrender":
            return "surrendered", self._imprison_or_execute(game, key, rng, surrendered=True)
        if response == "escape":
            own_power = self._player_battle_power(game)
            chance = max(0.08, min(0.8, 0.22 + own_power / max(1.0, float(target.get("target_power", own_power))) * 0.25))
            game.player.hostility[key] = game.player.hostility.get(key, 0) + float(config["escape_hostility_gain"])
            if rng.random() < chance:
                return "escaped", f"你付出代价甩脱追兵（成功率 {chance:.0%}），敌对值却进一步上升。"
            return "captured", f"突围失败（成功率 {chance:.0%}）。" + self._imprison_or_execute(game, key, rng)
        raise ValueError("未知通缉应对方式")

    def _imprison_or_execute(
        self, game: GameState, key: str, rng: random.Random, surrendered: bool = False,
    ) -> str:
        player = game.player
        config = WORLD_SYSTEMS["faction_conflict"]
        hostility = player.hostility.get(key, 0)
        execution_threshold = float(config["execution_threshold"])
        execution_chance = 0.0 if hostility < execution_threshold else min(0.9, 0.35 + (hostility - execution_threshold) / 100)
        if not surrendered:
            execution_chance = min(0.95, execution_chance + 0.12)
        if rng.random() < execution_chance:
            self._die(game, f"落入{self._hostility_name(key, game)}之手，被当场处决", "SYS_WANTED_EXECUTION")
            return f"敌对值 {hostility:.0f}，对方拒绝收押，将你当场处决。"
        low, high = config["prison_years"]
        years = rng.randint(int(low), int(high)) + min(8, int(hostility // 35))
        player.imprisonment = {
            "key": key, "name": self._hostility_name(key, game), "remaining_years": years,
            "captured_age": player.age, "hostility": round(hostility, 1),
            "sentence_years": years,
            "hostility_reduction_per_year": max(4.0, hostility / max(1, years)),
        }
        self._intrigue_record_player_prison(game, key, years)
        player.party = []
        return f"你被押入{self._hostility_name(key, game)}大牢，刑期 {years} 年。"

    def _hostility_name(self, key: str, game: GameState | None = None) -> str:
        kind, entity_id = key.split(":", 1)
        if kind in {"sect", "family"}:
            if game and entity_id in game.sects:
                return game.sects[entity_id].name
            if game and game.family and entity_id == game.family.id:
                return game.family.name
            return FACTION_DEFINITIONS.get(entity_id, {"name": entity_id})["name"]
        if kind == "race":
            return RACE_DEFINITIONS.get(entity_id, {"name": entity_id})["name"]
        return WORLD_SYSTEMS["world_names"].get(entity_id, entity_id) + "修仙界"

    def _try_conceive_child(self, game: GameState, rng: random.Random) -> str:
        player = game.player
        companion = player.dao_companion
        if not companion or not companion.get("alive", True):
            return ""
        player_realm, _ = self._actual_player_realm(player)
        # 生育难度取双方较高的生命层次；任一方达到化神，概率即归零。
        realm_index = max(player_realm, int(companion.get("realm_index", player_realm)))
        family_rules = WORLD_SYSTEMS["family"]
        natural_chance = float(family_rules["conception_chance_by_realm"].get(str(realm_index), 0.0))
        medicine_bonus = max(0.0, float(player.next_companion_conception_bonus))
        chance = min(0.95, natural_chance + medicine_bonus)
        # 药力只绑定一次有效的缠绵互动；即使本次未能诞下后代也会消耗。
        player.next_companion_conception_bonus = 0.0
        if chance <= 0 or rng.random() >= chance:
            if chance > 0:
                source = f"（自然 {natural_chance:.1%} + 丹药 {medicine_bonus:.1%}）" if medicine_bonus else ""
                return f" 本次孕育后代概率 {chance:.1%}{source}，未有血脉诞生。"
            return " 化神以后生命层次过高，已无法自然孕育后代；可借孕育丹药暂时提高下一次概率。"
        player_innate = player.spirit_root != "none" and not player.acquired_root
        companion_root = str(companion.get("spirit_root", "none"))
        companion_innate = companion_root != "none" and not companion.get("acquired_root", False)
        has_root = player_innate and companion_innate and rng.random() < float(family_rules["spirit_root_inheritance_chance"])
        child_root = rng.choice([player.spirit_root, companion_root]) if has_root else "none"
        surn = player.name[:1] if player.name else "韩"
        child = {
            "id":f"child_{game.id.replace('-', '')[:8]}_{len(player.offspring)}", "name":surn + rng.choice(["宁","安","澄","昭","遥","真","元","清"]),
            "age":0, "alive":True, "world":player.world, "spirit_root":child_root,
            "spirit_root_name":self._npc_root_name(child_root), "cultivation_started":False,
            "realm_index":0, "layer":1, "path":player.technique.path if player.technique else player.path,
            "lifespan":rng.randint(80, 100), "parents":[player.name, str(companion.get("name", "道侣"))],
            "gender":rng.choice(["male", "female"]),
        }
        lineage_text = ""
        inheritance = MONSTER_BLOODLINE_SETTINGS.get("inheritance", {})
        if player.path == "monster" and bloodline_content_available() and rng.random() < float(inheritance.get("species_chance", 1.0)):
            species = MONSTER_SPECIES.get(str(player.monster_species_id or ""), {})
            base_evolution_id = species.get("base_evolution_id")
            child.update(
                path="monster", monster_species_id=player.monster_species_id,
                monster_evolution_id=base_evolution_id,
                monster_evolution_history=[base_evolution_id] if base_evolution_id else [],
                monster_bloodline_imprints=[
                    imprint for imprint in player.monster_bloodline_imprints
                    if rng.random() < float(inheritance.get("imprint_chance", 0.45))
                ],
                monster_lineage_origin=player.monster_evolution_id,
            )
            child["lifespan"] *= int(WORLD_SYSTEMS.get("monster_cultivation", {}).get("lifespan_multiplier", 3))
            lineage_text = f"并继承了{species.get('name', '妖族')}本源血脉"
            lineage_candidates: list[dict[str, Any]] = []
            for parent in (player.to_dict(), companion):
                lineage = parent.get("monster_custom_lineage")
                lineage_id = parent.get("monster_custom_lineage_id") or (
                    lineage.get("id") if isinstance(lineage, dict) else None
                )
                if not isinstance(lineage, dict) or not lineage_id or not isinstance(lineage.get("rules"), list):
                    continue
                if any(row["id"] == str(lineage_id) for row in lineage_candidates):
                    continue
                lineage_candidates.append({"id": str(lineage_id), "lineage": lineage})
            if lineage_candidates:
                inherited = rng.choice(lineage_candidates)
                child["monster_custom_lineage_id"] = inherited["id"]
                child["monster_custom_lineage"] = copy.deepcopy(inherited["lineage"])
                child["monster_custom_lineage"]["id"] = inherited["id"]
                lineage_text += f"，并承袭了祖血【{child['monster_custom_lineage'].get('name', inherited['id'])}】的定型规则"
        player.offspring.append(child)
        player.children += 1
        return f" 你们诞下一名后代{child['name']}；其{'身具' + child['spirit_root_name'] if has_root else '没有显现灵根'}{lineage_text}。"

    def _annual_offspring_and_family_update(self, game: GameState, rng: random.Random) -> list[str]:
        news: list[str] = []
        player = game.player
        family_ids = {npc.id for npc in game.family.npcs} if game.family else set()
        for child in player.offspring:
            if not child.get("alive", True) or child.get("id") in family_ids:
                continue
            child["age"] = int(child.get("age", 0)) + 1
            if child.get("lifespan") is not None and child["age"] >= int(child["lifespan"]):
                child["alive"] = False
                child["death_reason"] = "寿元耗尽"
                summary = f"后代{child['name']}寿元耗尽，安然辞世。"
                if child.get("world", player.world) == player.world:
                    news.append(f"{player.age}岁：{summary}")
                game.history.append(HistoryRecord(
                    "SYS_CHILD_FALL",1,player.age,"血脉凋零",child["id"],"child_fallen",summary,
                    {"child_id":child["id"],"alive":[True,False]},
                    ["system","family","offspring","world_news",f"world:{child.get('world',player.world)}"],
                ))
                continue
            if child.get("spirit_root", "none") != "none" and not child.get("cultivation_started") and child["age"] >= int(WORLD_SYSTEMS["family"]["cultivation_start_age"]):
                child.update(cultivation_started=True, realm_index=1, layer=1, lifespan=rng.randint(100, 120))
                summary = f"后代{child['name']}在{child['age']}岁正式引气入体，踏入练气一层。"
                news.append(f"{player.age}岁：{summary}")
                game.history.append(HistoryRecord(
                    "SYS_CHILD_CULTIVATION",1,player.age,"血脉问道",child["id"],"cultivator",summary,
                    {"child_id":child["id"],"realm_index":1},["system","family","offspring",f"world:{child.get('world',player.world)}"],
                ))
            if child.get("cultivation_started"):
                descendant = SectNpc(
                    str(child["id"]), str(child["name"]), "后代",
                    int(child.get("realm_index", 1)), int(child.get("layer", 1)),
                    int(child["age"]), child.get("lifespan"),
                    spirit_root=str(child.get("spirit_root", "none")),
                    cultivation_progress=float(child.get("cultivation_progress", 0)),
                    path=str(child.get("path", player.path)), race=player.race,
                    world=str(child.get("world", player.world)),
                    gender=str(child.get("gender") or self._stable_gender(str(child.get("id", "")))),
                    next_tribulation_age=child.get("next_tribulation_age"),
                    tribulation_count=int(child.get("tribulation_count", 0)),
                    tribulation_power=child.get("tribulation_power"),
                )
                tribulation = self._resolve_npc_periodic_tribulation(game, descendant, rng, "后代")
                result = None if not descendant.alive else self._advance_npc_cultivation(descendant, rng)
                child.update(
                    age=descendant.age, alive=descendant.alive, realm_index=descendant.realm_index,
                    layer=descendant.layer, lifespan=descendant.lifespan, world=descendant.world,
                    cultivation_progress=descendant.cultivation_progress,
                    next_tribulation_age=descendant.next_tribulation_age,
                    tribulation_count=descendant.tribulation_count,
                    tribulation_power=descendant.tribulation_power,
                    death_reason=descendant.death_reason,
                )
                if tribulation and child.get("world") == player.world:
                    news.append(f"{player.age}岁：{tribulation}")
                if result:
                    summary = f"后代{child['name']}由{result['old']}突破至{result['new']}。"
                    if child.get("world") == player.world:
                        news.append(f"{player.age}岁：{summary}")
                    game.history.append(HistoryRecord(
                        "SYS_CHILD_BREAKTHROUGH",1,player.age,"后辈破境",child["id"],result["type"],summary,
                        {"child_id":child["id"],"realm":[result["old"],result["new"]]},
                        ["system","family","offspring","world_news",f"world:{child.get('world',player.world)}"],
                    ))
        family = game.family
        if not family or family.extinct:
            return news
        for npc in family.npcs:
            if not npc.alive:
                continue
            child = next((row for row in player.offspring if row.get("id") == npc.id), None)
            npc.age += 1
            tribulation = self._resolve_npc_periodic_tribulation(game, npc, rng, family.name)
            if tribulation and family.world == player.world:
                news.append(f"{player.age}岁：{tribulation}")
            if not npc.alive:
                if child:
                    child.update(age=npc.age,alive=False,death_reason=npc.death_reason)
                continue
            if npc.lifespan is not None and npc.age >= npc.lifespan:
                npc.alive = False
                npc.death_reason = "寿元耗尽，族谱除名"
                if child:
                    child.update(age=npc.age,alive=False,death_reason=npc.death_reason)
                summary = f"{family.name}{npc.title}{npc.name}寿尽坐化。"
                news.append(f"{player.age}岁：{summary}")
                game.history.append(HistoryRecord(
                    "SYS_FAMILY_MEMBER_FALL",1,player.age,"家族讣告",npc.id,"npc_fallen",summary,
                    {"npc_id":npc.id},["system","family","npc","world_news",f"world:{family.world}"],
                ))
                continue
            result = self._advance_npc_cultivation(npc, rng)
            if child:
                child.update(
                    age=npc.age,alive=npc.alive,realm_index=npc.realm_index,layer=npc.layer,
                    lifespan=npc.lifespan,world=npc.world,cultivation_progress=npc.cultivation_progress,
                    next_tribulation_age=npc.next_tribulation_age,tribulation_count=npc.tribulation_count,
                    tribulation_power=npc.tribulation_power,death_reason=npc.death_reason,
                )
            if result:
                summary = f"{family.name}{npc.title}{npc.name}由{result['old']}突破至{result['new']}。"
                if family.world == player.world:
                    news.append(f"{player.age}岁：{summary}")
                game.history.append(HistoryRecord(
                    "SYS_FAMILY_MEMBER_BREAKTHROUGH",1,player.age,"家族喜报",npc.id,result["type"],summary,
                    {"npc_id":npc.id,"realm":[result["old"],result["new"]]},
                    ["system","family","npc","world_news",f"world:{family.world}"],
                ))
        if not any(npc.alive for npc in family.npcs):
            family.extinct = True
            game.history.append(HistoryRecord(
                "SYS_FAMILY_EXTINCT",1,player.age,"家族断绝",family.id,"extinct",
                f"{family.name}最后一名在册修士陨落，修仙家族传承断绝。",
                {"family_id":family.id,"extinct":True},
                ["system","family","extinction","world_news",f"world:{family.world}"],
            ))
            return news
        family_rules = WORLD_SYSTEMS["family"]
        if (
            player.age % int(family_rules["recruitment_interval_years"]) == 0
            and len([npc for npc in family.npcs if npc.alive]) < int(family_rules["max_members"])
        ):
            newcomer = self._recruit_sect_npc(family, player.age, rng)
            newcomer.title = "外姓门人"
            summary = f"低阶散修{newcomer.name}请求依附{family.name}，列入外门。"
            game.history.append(HistoryRecord(
                "SYS_FAMILY_RECRUIT",1,player.age,"家族收录外姓",newcomer.id,"npc_joined",summary,
                {"npc_id":newcomer.id},["system","family","recruitment",f"world:{family.world}"],
            ))
        return news

    def _check_sect_extinction(self, game: GameState, sect: SectState) -> bool:
        if sect.extinct or any(npc.alive and npc.world == sect.world for npc in self._sect_members(game, sect)):
            return False
        sect.extinct = True
        summary = f"{sect.name}最后一盏 NPC 魂灯熄灭，传承断绝，宗门正式灭亡。"
        if game.player.faction_id == sect.id:
            game.player.faction_id = None
            game.player.faction_join_age = None
            game.player.faction_contribution = 0
            game.player.faction_reward_preference = None
        game.history.append(HistoryRecord(
            "SYS_SECT_EXTINCT",1,game.player.age,"宗门灭亡",sect.id,"extinct",summary,
            {"sect_id":sect.id,"extinct":True},["system","faction","extinction","world_news",f"world:{sect.world}"],
        ))
        return True

    def _dissolve_player_sect(self, game: GameState, sect: SectState, reason: str) -> None:
        """Disband a weak player sect without falsely killing every former member."""
        sect.extinct = True
        for npc in self._sect_members(game, sect):
            if npc.alive:
                npc.faction_id = None
                game.notable_npcs.setdefault(npc.id, npc)
        if game.player.faction_id == sect.id:
            game.player.faction_id = None
            game.player.faction_join_age = None
            game.player.faction_contribution = 0
            game.player.faction_reward_preference = None
        game.history.append(HistoryRecord(
            "SYS_PLAYER_SECT_DISSOLVED",1,game.player.age,"山门解散",sect.id,"dissolved",
            f"{sect.name}因{reason}而解散；幸存门人散入天下，并未凭空陨落。",
            {"sect_id":sect.id,"pressure":sect.pressure},
            ["system","faction","player_faction","extinction","world_news",f"world:{sect.world}"],
        ))

    def _maybe_founded_sect_pressure(self, game: GameState, rng: random.Random) -> bool:
        player = game.player
        sect = game.sects.get(player.faction_id or "")
        if not sect or sect.extinct or not sect.founded_by_player or sect.world != player.world:
            return False
        actual_realm, _ = self._actual_player_realm(player)
        governance_threshold = self._governance_threshold(player.world)
        qualified_members = [
            npc for npc in self._sect_members(game, sect)
            if npc.alive and npc.world == sect.world and npc.realm_index >= governance_threshold
        ]
        if actual_realm >= governance_threshold or qualified_members:
            # 排挤针对的是“无人坐镇”的弱小山门。只要玩家或任一正式门人
            # 达到本界治理门槛，旧的守山失败记录也应立即失效。
            sect.pressure = 0
            return False
        faction_rules = WORLD_SYSTEMS["player_faction"]
        if rng.random() >= float(faction_rules["pressure_chance_per_unit"]):
            return False
        event_id = f"EVT_PLAYER_SECT_DEFENSE_{min(3, sect.pressure + 1):03d}"
        game.pending_event = self._instantiate_event(self.events_by_id[event_id], game, rng)
        threshold_realm = governance_threshold
        required_power = expected_combat_power(threshold_realm, 1) * (0.58 + sect.pressure * 0.12)
        game.pending_event["runtime"] = {
            "sect_id":sect.id, "required_power":round(required_power, 1),
            "failure_number":sect.pressure + 1,
        }
        game.pending_event["_history_tags"] = [
            tag for tag in self.events_by_id[event_id].get("tags", []) if not tag.startswith("world:")
        ] + [f"world:{player.world}"]
        game.pending_event["body"] += f"（正面守山建议战力 {required_power:.0f}；此前护山失败 {sect.pressure}/3 次。）"
        return True

    def _advance_player_bounties(self, game: GameState, rng: random.Random) -> None:
        active = [row for row in game.player_bounties if row.get("status") == "active" and row.get("world") == game.player.world]
        if not active:
            return
        bounty = active[0]
        bounty["attempts"] = int(bounty.get("attempts", 0)) + 1
        npc = self._find_npc(game, str(bounty.get("target_id", "")))
        if not npc or not npc.alive:
            bounty["status"] = "closed"
            return
        authority = str(bounty.get("authority", ""))
        available = {row["id"]:row for row in self._available_bounty_authorities(game)}
        if authority not in available:
            bounty["status"] = "suspended"
            return
        if authority == "race":
            allegiance_race = self._player_allegiance_race(game.player)
            members = [
                member for member in [*game.world_npcs.values(), *game.notable_npcs.values(), *(npc for sect in game.sects.values() for npc in sect.npcs)]
                if member.alive and member.world == game.player.world and member.race == allegiance_race
            ]
        elif authority == "sect":
            sect = game.sects.get(game.player.faction_id or "")
            members = [member for member in sect.npcs if member.alive] if sect else []
        else:
            members = [member for member in game.family.npcs if member.alive] if game.family else []
        # 同一 NPC 可能同时出现在宗门与世界人物集合中，只允许出战一次；
        # 发布者本人不自动参战，通缉令依靠玩家实际掌握的同僚执行。
        unique_members = {
            member.id: member for member in members
            if member.id != npc.id and member.alive and member.world == game.player.world
        }
        candidates = sorted(unique_members.values(), key=self._npc_power, reverse=True)
        if not candidates:
            game.history.append(HistoryRecord(
                "SYS_PLAYER_BOUNTY_NO_HUNTERS",1,game.player.age,"通缉无人可遣",npc.id,"delayed",
                f"{bounty.get('issuer_name','麾下势力')}暂时没有可跨界执行追杀的弟子或同僚，通缉令仍然有效。",
                {"bounty_id":bounty["id"],"attempts":bounty["attempts"]},["system","wanted","player_order",f"world:{npc.world}"],
            ))
            return

        # 每个行动单位派出一至三人。优先从最强的五人中抽调，兼顾势力会认真
        # 执行命令与同一位高层不会机械地永远出战两种表现。
        pool = candidates[: min(5, len(candidates))]
        team_size = min(len(pool), rng.randint(1, 3))
        hunters = rng.sample(pool, team_size)
        hunter_powers = {member.id: self._npc_power(member) for member in hunters}
        pursuit_power = npc_team_combat_power(hunter_powers.values())
        target_power = max(1.0, self._npc_power(npc))
        ratio = pursuit_power / target_power
        victory_chance = max(0.06, min(0.94, 0.18 + ratio * 0.34))
        hunter_names = "、".join(member.name for member in hunters)

        if rng.random() < victory_chance:
            target_threshold = float(REALMS[npc.realm_index].kill_threshold)
            can_kill = ratio >= target_threshold
            killed = can_kill and rng.random() < min(0.92, 0.55 + (ratio - target_threshold) * 0.12)
            if killed:
                npc.alive = False
                npc.death_reason = f"被{bounty.get('issuer_name','麾下势力')}通缉后伏诛"
                bounty["status"] = "completed"
                bounty["completed_age"] = game.player.age
                reward_text = "其身上并无可入眼的重宝"
                if npc.treasure_item_id and not npc.treasure_looted:
                    add_item(game.player, npc.treasure_item_id)
                    npc.treasure_looted = True
                    reward_text = f"其重宝《{ITEM_CATALOG[npc.treasure_item_id].name}》已交由你接收"
                for candidate_sect in game.sects.values():
                    if any(member.id == npc.id for member in candidate_sect.npcs):
                        self._check_sect_extinction(game, candidate_sect)
                game.history.append(HistoryRecord(
                    "SYS_PLAYER_BOUNTY_COMPLETE",1,game.player.age,"通缉伏诛",npc.id,"completed",
                    f"{hunter_names}组成{team_size}人追缉队（结算战力 {pursuit_power:.0f}），围杀{npc.name}（战力 {target_power:.0f}）；{reward_text}。",
                    {"bounty_id":bounty["id"],"target_id":npc.id,"hunter_ids":[row.id for row in hunters],"pursuit_power":pursuit_power,"target_power":target_power},
                    ["system","wanted","player_order",f"world:{npc.world}"],
                ))
                return
            npc.wounds = min(4, npc.wounds + (2 if ratio >= 1 else 1))
            for hunter in hunters:
                if ratio < 1.6 and rng.random() < 0.30:
                    hunter.wounds = min(4, hunter.wounds + 1)
            game.history.append(HistoryRecord(
                "SYS_PLAYER_BOUNTY_TARGET_WOUNDED",1,game.player.age,"通缉重创",npc.id,"target_wounded",
                f"{hunter_names}组成{team_size}人追缉队（结算战力 {pursuit_power:.0f}）重创了{npc.name}（战力 {target_power:.0f}），但未满足击杀条件；通缉令继续执行。",
                {"bounty_id":bounty["id"],"hunter_ids":[row.id for row in hunters],"target_wounds":npc.wounds},
                ["system","wanted","player_order",f"world:{npc.world}"],
            ))
            return

        outcomes: list[str] = []
        for hunter in hunters:
            hunter_power = max(1.0, hunter_powers[hunter.id])
            counter_ratio = target_power / hunter_power
            kill_threshold = float(REALMS[hunter.realm_index].kill_threshold)
            if counter_ratio >= kill_threshold and rng.random() < 0.55:
                hunter.alive = False
                hunter.death_reason = f"执行对{npc.name}的通缉令时反遭灭杀"
                outcomes.append(f"{hunter.name}阵亡")
                for candidate_sect in game.sects.values():
                    if any(member.id == hunter.id for member in candidate_sect.npcs):
                        self._check_sect_extinction(game, candidate_sect)
            elif rng.random() < min(0.85, 0.38 + max(0.0, counter_ratio - 1) * 0.18):
                hunter.wounds = min(4, hunter.wounds + 2)
                outcomes.append(f"{hunter.name}重伤遁回")
            else:
                outcomes.append(f"{hunter.name}及时脱身")
        if ratio >= 0.65:
            npc.wounds = min(4, npc.wounds + 1)
        game.history.append(HistoryRecord(
            "SYS_PLAYER_BOUNTY_COUNTERED",1,game.player.age,"通缉反噬",npc.id,"hunters_defeated",
            f"{hunter_names}组成{team_size}人追缉队（结算战力 {pursuit_power:.0f}）截住{npc.name}（战力 {target_power:.0f}），却被对方击退：{'、'.join(outcomes)}。通缉令仍然有效。",
            {"bounty_id":bounty["id"],"hunter_ids":[row.id for row in hunters],"outcomes":outcomes},
            ["system","wanted","player_order",f"world:{npc.world}"],
        ))

    def _annual_sect_update(self, game: GameState, rng: random.Random) -> list[str]:
        news: list[str] = []
        player = game.player
        living_spirit_npcs = sum(
            npc.alive and npc.world == "human" and npc.realm_index == 5
            for sect in game.sects.values()
            for npc in sect.npcs
        ) + sum(npc.alive and npc.world == "human" and npc.realm_index == 5 for npc in game.world_npcs.values())
        for sect_id, sect in game.sects.items():
            if sect.extinct:
                continue
            for npc in sect.npcs:
                if not npc.alive or npc.world != sect.world:
                    continue
                npc.age += 1
                if self._intrigue_is_imprisoned(game, npc.id):
                    if npc.lifespan is not None and npc.age >= npc.lifespan:
                        npc.alive = False
                        npc.death_reason = "服刑期间寿元耗尽"
                    continue
                if npc.wounds > 0 and rng.random() < 0.35:
                    npc.wounds -= 1
                tribulation = self._resolve_npc_periodic_tribulation(game, npc, rng, sect.name)
                if tribulation:
                    if sect.world == player.world:
                        news.append(f"{player.age}岁：{tribulation}")
                    if not npc.alive:
                        continue
                death_reason: str | None = None
                if npc.lifespan is not None and npc.age >= npc.lifespan:
                    death_reason = "寿元耗尽，坐化于宗门祖庭"
                elif rng.random() < float(FACTION_SYSTEMS["npc_cultivation"]["accident_death_chance"]):
                    death_reason = rng.choice(["外出历练时失踪，魂灯熄灭", "冲关失败，道消身殒", 
                                               "遭逢旧敌伏杀，未能归山", "秘境陨落，身死道消", 
                                               "遭遇魔道，元神不测", "走火入魔，爆体而亡"])
                if death_reason:
                    npc.alive = False
                    npc.death_reason = death_reason
                    if sect.world == player.world:
                        news.append(f"{player.age}岁：{sect.name}{npc.name}{death_reason}")
                    game.history.append(HistoryRecord(
                        "SYS_SECT_NPC_FALL", 1, player.age, "宗门讣告", None, "npc_fallen",
                        f"{sect.name}{npc.title}{npc.name}{death_reason}。",
                        {"npc_id": npc.id, "alive": [True, False]},
                        ["system", "faction", "npc", "world_news", f"world:{sect.world}"],
                    ))
                    continue
                crossing_to_spirit = npc.world == "human" and npc.realm_index == 4 and npc.layer == REALMS[4].layers
                can_cross = not crossing_to_spirit or living_spirit_npcs < 1
                old_title = self._dynamic_sect_title(npc, sect)
                breakthrough = self._advance_npc_cultivation(npc, rng, can_cross)
                if breakthrough:
                    old_name, new_name = breakthrough["old"], breakthrough["new"]
                    new_title = self._dynamic_sect_title(npc, sect)
                    title_change = f"，职衔由{old_title}晋为{new_title}" if new_title != old_title else ""
                    if breakthrough["type"] == "breakthrough" and npc.world == "human" and npc.realm_index == 5:
                        living_spirit_npcs += 1
                    if breakthrough["type"] == "departure":
                        living_spirit_npcs = max(0, living_spirit_npcs - 1)
                        if sect.world == player.world:
                            news.append(f"{player.age}岁：{sect.name}{npc.name}{new_name}，人界魂灯熄灭")
                    else:
                        if sect.world == player.world:
                            news.append(f"{player.age}岁：{sect.name}{npc.name}由{old_name}突破至{new_name}")
                    game.history.append(HistoryRecord(
                        "SYS_SECT_NPC_DEPART" if breakthrough["type"] == "departure" else "SYS_SECT_NPC_BREAKTHROUGH",
                        1, player.age, "宗门魂灯" if breakthrough["type"] == "departure" else "宗门喜报", None,
                        "npc_departed" if breakthrough["type"] == "departure" else "npc_breakthrough",
                        f"{sect.name}{old_title}{npc.name}{new_name}。" if breakthrough["type"] == "departure" else f"{sect.name}{old_title}{npc.name}由{old_name}突破至{new_name}{title_change}。",
                        {"npc_id": npc.id, "realm": [old_name, new_name]},
                        ["system", "faction", "npc", "world_news", f"world:{sect.world}"],
                    ))
            if self._check_sect_extinction(game, sect):
                continue
            self._compact_sect_roster(game, sect)
            if (
                player.age % int(FACTION_SYSTEMS["recruitment_interval_years"]) == 0
                and len([npc for npc in self._sect_members(game, sect) if npc.alive])
                < int(FACTION_SYSTEMS.get("max_members", 36))
            ):
                newcomer = self._recruit_sect_npc(sect, player.age, rng)
                if newcomer.realm_index >= 3:
                    if sect.world == player.world:
                        news.append(f"{player.age}岁：{newcomer.name}以{self._npc_realm_name(newcomer)}修为加入{sect.name}")
                    game.history.append(HistoryRecord(
                        "SYS_SECT_RECRUIT", 1, player.age, "宗门招新", None, "npc_joined",
                        f"{newcomer.name}以{self._npc_realm_name(newcomer)}修为加入{sect.name}，列为{newcomer.title}。",
                        {"npc_id": newcomer.id, "realm_index": newcomer.realm_index},
                        ["system", "faction", "npc", "recruitment", "world_news", f"world:{sect.world}"],
                    ))
                elif player.faction_id == sect_id:
                    game.history.append(HistoryRecord(
                        "SYS_SECT_RECRUIT", 1, player.age, "宗门招新", None, "npc_joined",
                        f"{newcomer.name}以{self._npc_realm_name(newcomer)}修为加入{sect.name}，列为{newcomer.title}。",
                        {"npc_id": newcomer.id, "realm_index": newcomer.realm_index},
                        ["system", "faction", "npc", "recruitment"],
                    ))
                self._compact_sect_roster(game, sect)

        news.extend(self._annual_offspring_and_family_update(game, rng))
        self._annual_relationship_update(game, rng)
        faction_meta = self._faction_meta(game, player.faction_id or "")
        if (
            not player.faction_id
            or player.faction_id not in game.sects
            or game.sects[player.faction_id].extinct
            or faction_meta.get("world", "human") != player.world
        ):
            return news
        reward_id = (
            player.faction_reward_preference
            if player.realm_index >= 4 and player.faction_reward_preference in FACTION_REWARDS
            else rng.choice(sorted(FACTION_REWARDS))
        )
        reward_name = FACTION_REWARDS[reward_id]["name"]
        if reward_id == "opportunity":
            self._add_opportunity(player, 3)
            reward_text = "机缘 +3"
        elif reward_id == "vitality":
            player.faction_hp_bonus += 2
            player.hp = min(max_hp(player), player.hp + 2)
            reward_text = "HP 上限永久 +2"
        elif reward_id == "mana":
            player.faction_mp_bonus += 2
            player.mp = min(max_mp(player), player.mp + 2)
            reward_text = "MP 上限永久 +2"
        else:
            player.faction_combat_bonus += 3
            reward_text = "独立战斗力永久 +3"
        player.faction_contribution += 1
        sect_name = faction_meta["name"]
        game.history.append(HistoryRecord(
            "SYS_FACTION_WELFARE", 1, player.age, f"{sect_name}年度结算", reward_id, "rewarded",
            f"宗门发放{reward_name}：{reward_text}；年度履职记宗门贡献 +1。",
            {"reward": reward_id, "faction_contribution": player.faction_contribution},
            ["system", "faction", "annual"],
        ))
        return news

    def _annual_world_npc_update(self, game: GameState, rng: random.Random) -> list[str]:
        news: list[str] = []
        living_human_spirits = sum(
            npc.alive and npc.world == "human" and npc.realm_index == 5
            for npc in game.world_npcs.values()
        ) + sum(
            npc.alive and npc.world == "human" and npc.realm_index == 5
            for sect in game.sects.values() for npc in sect.npcs
        )
        simulated_npcs = [*game.world_npcs.values(), *game.notable_npcs.values()]
        for npc in simulated_npcs:
            if not npc.alive:
                continue
            npc.age += 1
            if self._intrigue_is_imprisoned(game, npc.id):
                if npc.lifespan is not None and npc.age >= npc.lifespan:
                    npc.alive = False
                    npc.death_reason = "服刑期间寿元耗尽"
                continue
            if npc.wounds > 0 and rng.random() < 0.35:
                npc.wounds -= 1
            tribulation = self._resolve_npc_periodic_tribulation(game, npc, rng, npc.title)
            if tribulation:
                if npc.world == game.player.world:
                    news.append(f"{game.player.age}岁：{tribulation}")
                if not npc.alive:
                    continue
            if npc.lifespan is not None and npc.age >= npc.lifespan:
                event_world = npc.world
                npc.alive = False
                npc.death_reason = "寿元耗尽，坐化于世间"
                summary = f"{npc.title}{npc.name}寿元耗尽，此后再无音讯。"
                if event_world == game.player.world:
                    news.append(f"{game.player.age}岁：{summary}")
                game.history.append(HistoryRecord(
                    "SYS_WORLD_NPC_FALL", 1, game.player.age, "天下讣闻", None, "npc_fallen", summary,
                    {"npc_id": npc.id, "alive": [True, False]},
                    ["system", "world_npc", "world_news", f"world:{event_world}"],
                ))
                continue
            crossing_to_spirit = npc.world == "human" and npc.realm_index == 4 and npc.layer == REALMS[4].layers
            event_world = npc.world
            result = self._advance_npc_cultivation(npc, rng, not crossing_to_spirit or living_human_spirits < 1)
            if not result:
                continue
            if result["type"] == "departure":
                living_human_spirits = max(0, living_human_spirits - 1)
                summary = f"{npc.title}{npc.name}{result['new']}；在人界看来，其魂灯已熄，等同陨落。"
                outcome = "npc_departed"
            else:
                if npc.realm_index == 5:
                    living_human_spirits += 1
                summary = f"{npc.title}{npc.name}由{result['old']}突破至{result['new']}。"
                outcome = "npc_breakthrough"
            if event_world == game.player.world:
                news.append(f"{game.player.age}岁：{summary}")
            game.history.append(HistoryRecord(
                "SYS_WORLD_NPC_CHANGE", 1, game.player.age, "天下异动", None, outcome, summary,
                {"npc_id": npc.id, "realm": [result["old"], result["new"]]},
                ["system", "world_npc", "world_news", f"world:{event_world}"],
            ))
        self._maybe_notorious_npc_killing(game, rng, news)
        return news

    def _maybe_notorious_npc_killing(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        protected = {
            str(row.get("id")) for row in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples]
            if row
        }
        villains = [
            npc for npc in game.world_npcs.values()
            if npc.alive and not npc.encountered_player and not self._intrigue_is_imprisoned(game, npc.id)
            and (npc.notorious or npc.path == "demonic")
            and rng.random() < (0.014 if npc.path == "demonic" else 0.004)
        ]
        for villain in villains:
            villain_faction = self._npc_faction_id(game, villain.id)
            victims = [
                npc for npc in self._all_world_npcs(game)
                if npc.alive and not npc.notorious and npc.world == villain.world
                and npc.id not in protected and npc.realm_index < villain.realm_index
                and not (
                    villain.path == "demonic" and villain_faction
                    and self._npc_faction_id(game, npc.id) == villain_faction
                )
            ]
            if not victims:
                continue
            victim = rng.choice(victims)
            victim.alive = False
            victim.death_reason = f"遭{villain.name}截杀"
            summary = f"臭名昭著的{villain.name}又造血案，{victim.name}（{self._npc_realm_name(victim)}）遭其截杀。"
            game.history.append(HistoryRecord(
                "SYS_NOTORIOUS_KILLING", 1, game.player.age, "凶名远播", villain.id, "npc_murdered", summary,
                {"villain_id":villain.id,"victim_id":victim.id},
                ["system","world_npc","notorious","world_news",f"world:{villain.world}"],
            ))
            if game.player.world == villain.world:
                news.append(f"{game.player.age}岁：{summary}")

    def _annual_race_diplomacy_update(self, game: GameState, rng: random.Random) -> list[str]:
        """Compatibility wrapper. Diplomacy now advances once per action unit, not once per year."""
        return self._advance_diplomacy_unit(game, rng)

    def _advance_diplomacy_unit(self, game: GameState, rng: random.Random) -> list[str]:
        self._ensure_race_relations(game)
        self._ensure_sect_relations(game)
        game.diplomacy_unit += 1
        news: list[str] = []
        config = RACE_SYSTEMS.get("diplomacy", {})

        for kind, relations in (("race", game.race_relations), ("sect", game.sect_relations)):
            for key, relation in relations.items():
                if relation.get("status") != "truce" or game.diplomacy_unit < int(relation.get("truce_until_unit", 0)):
                    continue
                first, second = split_race_pair(key)
                if kind == "race" and not all(
                    game.player.world in RACE_DEFINITIONS.get(side, {}).get("worlds", [])
                    for side in (first, second)
                ):
                    continue
                relation.update(status="neutral", affinity=max(-10.0, float(relation.get("affinity", 0))), since_age=game.player.age)
                relation.pop("truce_until_unit", None)
                first_name, second_name = self._power_name(game, kind, first), self._power_name(game, kind, second)
                world = game.player.world if kind == "race" and self._world_supports(game.player.world, "races") else "spirit" if kind == "race" else game.sects.get(first, SectState(first, first)).world
                summary = f"{first_name}与{second_name}的停战期结束，双方暂时恢复中立。"
                game.history.append(HistoryRecord(
                    "SYS_TRUCE_EXPIRED", 1, game.player.age, "停战期届满", None, "neutral", summary,
                    {"kind":kind,"sides":[first,second]}, ["system","diplomacy","truce","world_news",f"world:{world}"],
                ))
                if game.player.world == world:
                    news.append(f"{game.player.age}岁：{summary}")

        news.extend(self._advance_wars_unit(game, rng))

        allied_race = any(
            relation.get("status") in {"alliance", "vassal"}
            and self._player_allegiance_race(game.player) in split_race_pair(key)
            and all(
                game.player.world in RACE_DEFINITIONS.get(side, {}).get("worlds", [])
                for side in split_race_pair(key)
            )
            for key, relation in game.race_relations.items()
        )
        allied_sect = bool(game.player.faction_id) and any(
            relation.get("status") in {"alliance", "vassal"} and game.player.faction_id in split_race_pair(key)
            for key, relation in game.sect_relations.items()
        )
        if self._world_supports(game.player.world, "races") and allied_race:
            reward = float(config.get("alliance_opportunity_reward", 2))
            self._add_opportunity(game.player, reward)
            summary = f"盟族互市与情报共享为你带来机缘 +{reward:g}。"
            news.append(f"{game.player.age}岁：{summary}")
            game.history.append(HistoryRecord("SYS_RACE_ALLIANCE_BENEFIT", 1, game.player.age, "盟族互惠", None, "rewarded", summary, {"opportunity":reward}, ["system","diplomacy","alliance","reward",f"world:{game.player.world}"]))
        if allied_sect:
            game.player.faction_contribution += 1
            summary = "盟宗协作使你的宗门贡献 +1。"
            news.append(f"{game.player.age}岁：{summary}")
            game.history.append(HistoryRecord("SYS_SECT_ALLIANCE_BENEFIT", 1, game.player.age, "盟宗协作", None, "rewarded", summary, {"faction_contribution":1}, ["system","diplomacy","alliance","reward",f"world:{game.player.world}"]))

        if rng.random() < float(config.get("unit_event_chance", 0.08)):
            self._random_race_diplomacy_event(game, rng, news)
        if rng.random() < float(config.get("unit_event_chance", 0.08)):
            self._random_sect_diplomacy_event(game, rng, news)
        self._maybe_npc_found_power(game, rng, news)
        self._pressure_weak_npc_powers(game, rng, news)
        self._simulate_cultivator_duel(game, rng, news)
        return news

    def _random_race_diplomacy_event(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        world = game.player.world if self._world_supports(game.player.world, "races") else "spirit"
        race_ids = [race_id for race_id, row in RACE_DEFINITIONS.items() if world in row.get("worlds", [])]
        first, second = rng.sample(race_ids, 2)
        key = race_pair(first, second)
        relation = game.race_relations.setdefault(key, {"affinity": 0.0, "status": "neutral", "since_age": game.player.age})
        old_status = str(relation.get("status", "neutral"))
        if game.diplomacy_unit < max(int(relation.get("truce_until_unit", 0)), int(relation.get("war_truce_until_unit", 0))):
            return
        if old_status == "war":
            return  # 战争由士气、厌战和和谈系统决定，不再被普通外交骰直接终止。
        elif old_status in {"alliance", "vassal"}:
            new_status, affinity, action = "neutral", rng.uniform(8, 34), "断盟" if old_status == "alliance" else "脱离依附"
        else:
            roll = rng.random()
            if roll < 0.44:
                new_status, affinity, action = "war", rng.uniform(-82, -56), "宣战"
            elif roll < 0.86:
                new_status, affinity, action = "alliance", rng.uniform(72, 90), "结盟"
            else:
                new_status, affinity, action = "vassal", rng.uniform(62, 84), "确立依附"
        self._set_diplomatic_relation(game, relation, new_status, first, second, "race", affinity)
        first_name, second_name = RACE_DEFINITIONS[first]["name"], RACE_DEFINITIONS[second]["name"]
        summary = f"{first_name}与{second_name}{action}，双方关系转为{RELATION_LABELS[new_status]}（好感 {affinity:.0f}）。"
        game.history.append(HistoryRecord(
            "SYS_RACE_DIPLOMACY", 1, game.player.age, f"{WORLD_SYSTEMS['world_names'][world]}族群大事", action, new_status, summary,
            {"races": [first, second], "status": [old_status, new_status], "affinity": round(affinity, 1)},
            ["system", "diplomacy", "race", "world_news", f"world:{world}"],
        ))
        if game.player.world == world:
            news.append(f"{game.player.age}岁：{summary}")

    def _random_sect_diplomacy_event(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        active = [sect for sect in game.sects.values() if not sect.extinct]
        worlds = [world for world in {sect.world for sect in active} if sum(sect.world == world for sect in active) >= 2]
        if not worlds:
            return
        world = rng.choice(worlds)
        first, second = rng.sample([sect for sect in active if sect.world == world], 2)
        key = race_pair(first.id, second.id)
        relation = game.sect_relations.setdefault(key, {"affinity":0.0,"status":"neutral","since_age":game.player.age})
        old_status = str(relation.get("status", "neutral"))
        if game.diplomacy_unit < max(int(relation.get("truce_until_unit", 0)), int(relation.get("war_truce_until_unit", 0))):
            return
        if old_status == "war":
            return
        elif old_status in {"alliance", "vassal"}:
            new_status, affinity, action = "neutral", rng.uniform(5, 30), "断绝盟约"
        else:
            roll = rng.random()
            if roll < 0.42:
                new_status, affinity, action = "war", rng.uniform(-82, -55), "正式宣战"
            elif roll < 0.86:
                new_status, affinity, action = "alliance", rng.uniform(68, 90), "缔结盟约"
            else:
                new_status, affinity, action = "vassal", rng.uniform(58, 82), "确立依附"
        self._set_diplomatic_relation(game, relation, new_status, first.id, second.id, "sect", affinity)
        summary = f"{first.name}与{second.name}{action}，宗门关系转为{RELATION_LABELS[new_status]}（好感 {affinity:.0f}）。"
        game.history.append(HistoryRecord(
            "SYS_SECT_DIPLOMACY",1,game.player.age,"宗门外交大事",action,new_status,summary,
            {"sects":[first.id,second.id],"status":[old_status,new_status],"affinity":round(affinity,1)},
            ["system","diplomacy","faction","world_news",f"world:{world}"],
        ))
        if game.player.world == world:
            news.append(f"{game.player.age}岁：{summary}")

    def _pressure_weak_npc_powers(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        rules = WORLD_SYSTEMS["player_faction"]
        for sect in game.sects.values():
            if sect.extinct or not sect.founded_by_npc:
                continue
            threshold = self._governance_threshold(sect.world)
            if any(npc.alive and npc.world == sect.world and npc.realm_index >= threshold for npc in self._sect_members(game, sect)):
                sect.pressure = max(0, sect.pressure - 1)
                continue
            if rng.random() >= float(rules["pressure_chance_per_unit"]):
                continue
            sect.pressure += 1
            if sect.pressure < int(rules["pressure_limit"]):
                continue
            sect.extinct = True
            for npc in self._sect_members(game, sect):
                if npc.alive:
                    npc.faction_id = None
                    game.notable_npcs.setdefault(npc.id, npc)
            summary = f"{sect.name}失去足够修为的坐镇者后，接连遭到排挤，山门很快烟消云散。"
            game.history.append(HistoryRecord(
                "SYS_NPC_POWER_DISSOLVED",1,game.player.age,"新势力消散",sect.id,"dissolved",summary,
                {"sect_id":sect.id},["system","faction","npc","extinction","world_news",f"world:{sect.world}"],
            ))
            if game.player.world == sect.world:
                news.append(f"{game.player.age}岁：{summary}")

    def _simulate_cultivator_duel(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        world = game.player.world
        people = list({npc.id:npc for npc in self._all_world_npcs(game) if npc.alive and npc.world == world}.values())
        if len(people) < 2:
            return
        demonic = [npc for npc in people if npc.path == "demonic"]
        if rng.random() >= min(0.42, 0.18 + len(demonic) * 0.025):
            return
        if demonic and rng.random() < 0.72:
            first = rng.choice(demonic)
            first_faction = self._npc_faction_id(game, first.id)
            opponents = [
                npc for npc in people if npc.id != first.id
                and not (first_faction and self._npc_faction_id(game, npc.id) == first_faction)
            ]
            if not opponents:
                return
            second = rng.choice(opponents)
        else:
            pairs = [
                (first, second) for index, first in enumerate(people) for second in people[index + 1:]
                if not (
                    (first.path == "demonic" or second.path == "demonic")
                    and self._npc_faction_id(game, first.id)
                    and self._npc_faction_id(game, first.id) == self._npc_faction_id(game, second.id)
                )
            ]
            if not pairs:
                return
            first, second = rng.choice(pairs)
        first_power, second_power = self._npc_power(first), self._npc_power(second)
        winner, loser = (first, second) if first_power * rng.uniform(0.85, 1.15) >= second_power else (second, first)
        ratio = max(first_power, second_power) / max(1.0, min(first_power, second_power))
        lethal_chance = self._npc_lethal_chance(world, loser.realm_index, "duel")
        lethal = ratio >= REALMS[loser.realm_index].kill_threshold and rng.random() < lethal_chance
        if lethal:
            loser.alive = False
            loser.death_reason = f"与{winner.name}斗法时陨落"
            outcome = f"{loser.name}未能脱身，当场陨落"
            transfer_summary = ""
        else:
            loser.wounds = min(4, loser.wounds + 1)
            outcome = f"{loser.name}负伤退走"
            transfer_summary = self._maybe_transfer_player_dependency(
                game, loser, winner, rng, context="cultivator_duel",
            )
        faction_ids = {self._npc_faction_id(game, first.id), self._npc_faction_id(game, second.id)} - {None}
        tags = ["system","world_npc","duel","world_news",f"world:{world}"]
        if game.player.faction_id in faction_ids:
            tags.append("faction")
        duel_ids = {first.id, second.id}
        if game.player.dao_companion and str(game.player.dao_companion.get("id")) in duel_ids:
            tags.extend(["relationship", "dao_companion"])
        if any(str(row.get("id")) in duel_ids for row in game.player.dao_friends):
            tags.extend(["relationship", "friend"])
        if (game.player.master and str(game.player.master.get("id")) in duel_ids) or any(
            str(row.get("id")) in duel_ids for row in game.player.disciples
        ):
            tags.extend(["relationship", "master"])
        cause = "由魔修主动挑衅引发斗法" if first.path == "demonic" else "因旧怨斗法"
        summary = (
            f"{first.name}（{self._npc_realm_name(first)}）与{second.name}（{self._npc_realm_name(second)}）"
            f"{cause}，{winner.name}占据上风，{outcome}。"
            + (f" {transfer_summary}" if transfer_summary else "")
        )
        game.history.append(HistoryRecord(
            "SYS_CULTIVATOR_DUEL",1,game.player.age,"修士斗法",winner.id,"fatal" if lethal else "injured",summary,
            {"npcs":[first.id,second.id],"winner":winner.id,"loser":loser.id},tags,
        ))
        news.append(f"{game.player.age}岁：{summary}")

    def _set_diplomatic_relation(
        self, game: GameState, relation: dict[str, Any], status: str,
        first: str, second: str, kind: str, affinity: float,
    ) -> None:
        if status == "war":
            self._start_war(game, kind, first, second)
        relation.update(status=status, affinity=round(float(affinity), 1), since_age=game.player.age)
        relation.pop("overlord", None)
        relation.pop("subject", None)
        relation.pop("truce_until_unit", None)
        if status == "truce":
            relation["truce_until_unit"] = game.diplomacy_unit + int(RACE_SYSTEMS.get("diplomacy", {}).get("truce_units", 3))
        elif status == "vassal":
            power = self._race_power if kind == "race" else self._sect_power
            first_power, second_power = power(game, first), power(game, second)
            relation["overlord"], relation["subject"] = ((first, second) if first_power >= second_power else (second, first))

    def _race_power(self, game: GameState, race_id: str) -> float:
        world = game.player.world if self._world_supports(game.player.world, "races") else "spirit"
        members = [npc for npc in self._all_world_npcs(game) if npc.alive and npc.world == world and npc.race == race_id]
        return sum(sorted((self._npc_power(npc) for npc in members), reverse=True)[:5])

    def _sect_power(self, game: GameState, sect_id: str) -> float:
        sect = game.sects.get(sect_id)
        return sum(sorted((self._npc_power(npc) for npc in self._sect_members(game, sect) if npc.alive), reverse=True)[:5]) if sect else 0.0

    @staticmethod
    def _all_world_npcs(game: GameState) -> list[SectNpc]:
        return [*game.world_npcs.values(), *game.notable_npcs.values(), *(npc for sect in game.sects.values() for npc in sect.npcs)]

    def _simulate_war_casualties(self, game: GameState, rng: random.Random, kind: str) -> list[str]:
        relations = game.race_relations if kind == "race" else game.sect_relations
        chance = float(RACE_SYSTEMS.get("diplomacy", {}).get("war_casualty_chance", 0.42))
        news: list[str] = []
        protected_ids = {
            str(row.get("id")) for row in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples]
            if row
        }
        for key, relation in relations.items():
            if relation.get("status") != "war" or rng.random() >= chance:
                continue
            first, second = split_race_pair(key)
            if kind == "race" and not all(
                game.player.world in RACE_DEFINITIONS.get(side, {}).get("worlds", [])
                for side in (first, second)
            ):
                continue
            fallen: list[str] = []
            for side in (first, second):
                if kind == "race":
                    world = game.player.world if self._world_supports(game.player.world, "races") else "spirit"
                    candidates = [npc for npc in self._all_world_npcs(game) if npc.alive and npc.world == world and npc.race == side]
                    side_name = RACE_DEFINITIONS.get(side, {"name": side})["name"]
                else:
                    sect = game.sects.get(side)
                    candidates = [npc for npc in (sect.npcs if sect else []) if npc.alive]
                    side_name = sect.name if sect else side
                    world = sect.world if sect else game.player.world
                candidates = [npc for npc in candidates if npc.id not in protected_ids]
                elite_realm = 4 if world == "human" else 6
                ordinary = [npc for npc in candidates if npc.realm_index < elite_realm]
                if not ordinary:
                    ordinary = candidates
                if not ordinary:
                    continue
                victim = rng.choices(ordinary, weights=[1 / max(1, npc.realm_index) for npc in ordinary], k=1)[0]
                if victim.realm_index >= elite_realm and rng.random() >= self._npc_lethal_chance(world, victim.realm_index, "war"):
                    continue
                victim.alive = False
                victim.death_reason = "势力大战中陨落"
                fallen.append(f"{side_name}{victim.name}（{self._npc_realm_name(victim)}）")
                for sect in game.sects.values():
                    if victim in sect.npcs:
                        self._check_sect_extinction(game, sect)
            if fallen:
                title = f"{WORLD_SYSTEMS['world_names'].get(world, world)}族战" if kind == "race" else "宗门大战"
                summary = f"{title}持续，本行动单位战报：" + "、".join(fallen) + "陨落。"
                tags = ["system", "diplomacy", kind, "war", "world_news", f"world:{world}"]
                game.history.append(HistoryRecord("SYS_POWER_WAR", 1, game.player.age, title, None, "casualties", summary, {"sides":[first, second]}, tags))
                if game.player.world == world:
                    news.append(f"{game.player.age}岁：{summary}")
        return news

    @staticmethod
    def _npc_lethal_chance(world: str, realm_index: int, context: str) -> float:
        config = WORLD_SYSTEMS.get("npc_mortality", {})
        if context == "duel":
            protected = config.get("protected_duel_chance", {}).get(world, {})
            if str(realm_index) in protected:
                return float(protected[str(realm_index)])
            return float(config.get("duel_lethal_chance", 0.16))
        table = config.get("elite_war_chance", {}).get(world, {})
        return float(table.get(str(realm_index), 0.02))

    @staticmethod
    def _npc_lifespan_multiplier(path: str) -> int:
        if path != "monster":
            return 1
        return int(WORLD_SYSTEMS.get("monster_cultivation", {}).get("lifespan_multiplier", 3))

    @classmethod
    def _scale_npc_lifespan(cls, lifespan: int | None, path: str, age: int = 0) -> int | None:
        if lifespan is None:
            return None
        return max(age + 1, int(lifespan) * cls._npc_lifespan_multiplier(path))

    def _maybe_npc_found_power(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        if rng.random() >= 0.012 or sum(sect.founded_by_npc and not sect.extinct for sect in game.sects.values()) >= 8:
            return
        world = game.player.world
        realm_cap = self._world_realm_cap(world)
        realm_index = (
            (5 if rng.random() < 0.02 else 4)
            if realm_cap <= 5 else (8 if rng.random() < 0.10 else 7)
        )
        kind = rng.choice(["sect", "family"])
        serial = sum(sect.founded_by_npc for sect in game.sects.values()) + 1
        surname = rng.choice(["顾", "叶", "陆", "楚", "白", "谢", "云", "林"])
        founder_name = surname + rng.choice(["玄岳", "长风", "照夜", "问天", "清河"])
        power_name = (founder_name[0] + "氏仙族") if kind == "family" else rng.choice(["玄岳门", "长风谷", "照夜宫", "问天盟"]) + str(serial)
        sect_id = f"npc_{kind}_{game.diplomacy_unit}_{serial}"
        layer = rng.randint(1, REALMS[realm_index].layers)
        age = rng.randint(500, 1200) if realm_cap <= 5 else rng.randint(8000, 30000)
        founder = SectNpc(
            f"{sect_id}_founder", founder_name, "开山祖师" if kind == "sect" else "始祖",
            realm_index, layer, age, None if realm_index >= 6 else max(age + 1, REALMS[realm_index].lifespan[1]),
            spirit_root=self._random_npc_root(realm_index, rng), path=rng.choice(list(PATH_NAMES)),
            race="human", world=world, faction_id=sect_id, affinity=0,
        )
        founder.lifespan = self._scale_npc_lifespan(founder.lifespan, founder.path, founder.age)
        sect = SectState(
            sect_id, power_name, world, [founder], f"由{founder_name}自行建立的{'修仙家族' if kind == 'family' else '宗门'}。",
            path=founder.path, kind=kind, founded_by_npc=True, founder_npc_id=founder.id,
            allegiance_race=founder.race,
        )
        for _ in range(2):
            self._recruit_sect_npc(sect, game.player.age, rng)
        game.sects[sect_id] = sect
        self._ensure_sect_relations(game)
        summary = f"{founder_name}建立了{power_name}，一座新的{'修仙家族' if kind == 'family' else '宗门'}进入天下势力谱。"
        game.history.append(HistoryRecord("SYS_NPC_FOUND_POWER", 1, game.player.age, "新势力崛起", sect_id, "founded", summary, {"faction_id":sect_id,"kind":kind}, ["system","faction","founding","npc",f"world:{world}"]))
        news.append(f"{game.player.age}岁：{summary}")

    def _maybe_race_war_ambush(self, game: GameState, rng: random.Random) -> bool:
        player = game.player
        if not self._world_supports(player.world, "races") or game.pending_event:
            return False
        enemies = []
        player_race = self._player_allegiance_race(player)
        for key, relation in game.race_relations.items():
            first, second = split_race_pair(key)
            if player_race not in {first, second} or relation.get("status") != "war":
                continue
            enemy = second if first == player_race else first
            if player.world not in RACE_DEFINITIONS.get(enemy, {}).get("worlds", []):
                continue
            if not self._revenge_ready(game, "race_war", enemy):
                continue
            enemies.append(enemy)
        chance = float(RACE_SYSTEMS.get("diplomacy", {}).get("war_ambush_chance", 0.08))
        if not enemies or rng.random() >= chance:
            return False
        enemy = rng.choice(enemies)
        target = self._generate_cultivator_target(player, "边境截杀者", ACTIONS["slay"]["combat"], rng, game=game, forced_race=enemy)
        target["kill_karma"] = True
        target["action"] = "slay"
        self._cache_encounter_target(game, target, rng)
        ambush = self._instantiate_event(self.events_by_id["EVT_ENCOUNTER_AMBUSH_001"], game, rng)
        ambush["title"] = f"{RACE_DEFINITIONS[enemy]['name']}边境截杀"
        ambush["runtime"] = target
        ambush["body"] = (
            f"两族正在交战，{RACE_DEFINITIONS[enemy]['name']}修士循踪截住了你。"
            f"来者修为{target['target_realm_display']}，战斗力约{target['target_power']:.0f}。你必须立即应对。"
        )
        interval = self._record_revenge_trigger(game, "race_war", enemy)
        ambush.setdefault("runtime", {})["revenge_cooldown_units"] = interval
        game.pending_event = ambush
        return True

    def _advance_npc_cultivation(
        self, npc: SectNpc, rng: random.Random, allow_spirit_crossing: bool = True,
        breakthrough_bonus: float = 0.0,
    ) -> dict[str, str] | None:
        if not npc.alive or npc.realm_index <= 0:
            return None
        if npc.realm_index >= len(REALMS):
            return None
        if npc.realm_index >= 9 or (npc.realm_index == 8 and npc.layer >= REALMS[8].layers):
            return None
        realm_cap = self._world_realm_cap(npc.world)
        if npc.realm_index > realm_cap or (
            npc.world != "human" and npc.realm_index == realm_cap and npc.layer >= REALMS[realm_cap].layers
        ):
            return None
        if npc.realm_index == len(REALMS) - 1 and npc.layer >= REALMS[-1].layers:
            return None
        settings = FACTION_SYSTEMS["npc_cultivation"]
        rate = float(settings["progress_per_year"][str(npc.realm_index)])
        root_efficiency = self._npc_root_efficiency(npc.spirit_root)
        npc.cultivation_progress += rate * root_efficiency * rng.uniform(0.82, 1.18)
        threshold = float(settings["threshold"]) * (1 + 0.06 * (npc.layer - 1))
        if npc.cultivation_progress < threshold:
            return None
        crossing_to_spirit = npc.world == "human" and npc.realm_index == 4 and npc.layer == REALMS[4].layers
        leaving_human_world = npc.world == "human" and npc.realm_index == 5 and npc.layer >= 3
        if crossing_to_spirit and not allow_spirit_crossing:
            npc.cultivation_progress = min(npc.cultivation_progress, threshold)
            return None
        success_chance = min(0.98, self._npc_breakthrough_probability(npc) + max(0.0, float(breakthrough_bonus)))
        if rng.random() >= success_chance:
            npc.cultivation_progress = threshold * float(settings["failed_progress_retained"])
            return None
        old_name = self._npc_realm_name(npc)
        npc.cultivation_progress = max(0.0, npc.cultivation_progress - threshold)
        if leaving_human_world:
            destination = self._ascension_destination(npc.path)
            npc.world = destination
            npc.departed_age = npc.age
            npc.departure_reason = f"飞升{WORLD_SYSTEMS['world_names'][destination]}"
            return {"type": "departure", "old": old_name, "new": npc.departure_reason}
        current = REALMS[npc.realm_index]
        if npc.layer < current.layers:
            npc.layer += 1
            stage = "middle" if npc.layer == 4 else "late" if npc.layer == 7 else None
            stage_ranges = WORLD_SYSTEMS.get("stage_lifespan_bonus", {}).get(current.id, {})
            if stage and stage in stage_ranges and npc.lifespan is not None:
                npc.lifespan += rng.randint(*stage_ranges[stage]) * self._npc_lifespan_multiplier(npc.path)
        else:
            npc.realm_index += 1
            npc.layer = 1
            span = REALMS[npc.realm_index].lifespan
            if span:
                rolled = rng.randint(*span) * self._npc_lifespan_multiplier(npc.path)
                npc.lifespan = max(npc.lifespan or 0, rolled, npc.age + 1)
            else:
                npc.lifespan = None
        return {"type": "breakthrough", "old": old_name, "new": self._npc_realm_name(npc)}

    def _resolve_npc_periodic_tribulation(
        self, game: GameState, npc: SectNpc, rng: random.Random, affiliation: str = "",
    ) -> str | None:
        """Resolve one NPC thunder tribulation; immortal lifespan does not mean immortal NPCs."""
        if not npc.alive or not self._world_supports(npc.world, "ranking") or npc.realm_index < 6:
            return None
        config = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
        if npc.next_tribulation_age is None:
            npc.next_tribulation_age = npc.age + int(config["interval_years"])
            npc.tribulation_power = float(config["base_power"]) * float(config["power_multiplier"]) ** npc.tribulation_count
            return None
        if npc.age < npc.next_tribulation_age:
            return None
        expected = expected_combat_power(npc.realm_index, npc.layer)
        own_power = self._npc_power(npc)
        uncapped_pressure = max(1.0, float(npc.tribulation_power or config["base_power"]))
        world_cap = self._tribulation_base_power_cap(npc.world)
        pressure = min(uncapped_pressure, world_cap) if world_cap is not None else uncapped_pressure
        preparedness = own_power / max(1.0, expected * 0.72 + pressure * 16)
        success_chance = max(0.48, min(0.985, 0.62 + preparedness * 0.24))
        old_count = npc.tribulation_count
        npc.tribulation_count += 1
        npc.next_tribulation_age += int(config["interval_years"])
        npc.tribulation_power = float(config["base_power"]) * float(config["power_multiplier"]) ** npc.tribulation_count
        prefix = f"{affiliation}{npc.name}" if affiliation else npc.name
        if rng.random() >= success_chance:
            npc.alive = False
            npc.death_reason = f"第{old_count + 1}次大天劫下灰飞烟灭"
            summary = f"{prefix}迎击第{old_count + 1}次大天劫失败，灰飞烟灭。"
            result = "npc_tribulation_fallen"
        else:
            summary = f"{prefix}扛过第{old_count + 1}次大天劫（渡过概率 {success_chance:.0%}），下一劫威力再增一倍。"
            if world_cap is not None and uncapped_pressure > world_cap:
                summary += f" 本界将实际基础雷威压制在 {world_cap:.0f}。"
            result = "npc_tribulation_survived"
        game.history.append(HistoryRecord(
            "SYS_NPC_TRIBULATION", 1, game.player.age,
            f"{WORLD_SYSTEMS['world_names'].get(npc.world, npc.world)}天劫", None, result, summary,
            {
                "npc_id": npc.id, "tribulation_count": npc.tribulation_count,
                "chance": round(success_chance, 3), "base_power": pressure,
                "uncapped_base_power": uncapped_pressure, "world_base_power_cap": world_cap,
            },
            ["system", "npc", "tribulation", "world_news", f"world:{npc.world}"],
        ))
        return summary

    @staticmethod
    def _ascension_destination(path: str) -> str:
        if path == "demonic":
            return "demon"
        if path == "ghost":
            return "hell"
        if path == "monster" and "monster_realm" in WORLD_SYSTEMS.get("world_profiles", {}):
            return "monster_realm"
        return "spirit"

    @staticmethod
    def _npc_realm_name(npc: SectNpc) -> str:
        definition = REALMS[npc.realm_index]
        if npc.world == "asura" and npc.realm_index >= 9:
            return WORLD_SYSTEMS.get("demonic_cultivation", {}).get("realm_names", {}).get(
                str(npc.realm_index), definition.name,
            )
        if definition.layers == 1:
            return definition.name
        if npc.path == "demonic" and definition.id != "mortal":
            name = WORLD_SYSTEMS.get("demonic_cultivation", {}).get("realm_names", {}).get(
                str(npc.realm_index), definition.name,
            )
            if definition.id == "qi":
                return f"{name}{npc.layer}层"
            stage = "初期" if npc.layer <= 3 else "中期" if npc.layer <= 6 else "后期"
            return f"{name}{stage}"
        if definition.id == "qi":
            return f"{definition.name}{npc.layer}层"
        if definition.id == "mortal":
            return definition.name
        stage = "初期" if npc.layer <= 3 else "中期" if npc.layer <= 6 else "后期"
        return f"{definition.name}{stage}"

    @staticmethod
    def _dynamic_sect_title(npc: SectNpc, sect: SectState) -> str:
        """随修为投影宗门职位，同时保留掌门等唯一职衔。"""
        if any(marker in npc.title for marker in ("宗主","掌门","台主","住持","方丈","太上","宫主","山主","族长","祭酒","老祖","尊者")):
            return npc.title
        if sect.world == "human":
            return {0:"杂役",1:"外门弟子",2:"宗门执事",3:"结丹护法",4:"元婴长老",5:"供奉老祖"}.get(npc.realm_index,"门人")
        return {0:"杂役",1:"外门弟子",2:"内门弟子",3:"真传弟子",4:"宗门执事",5:"化神护法",6:"炼虚长老",7:"合体太上",8:"大乘老祖"}.get(npc.realm_index,"门人")

    def _relationship_snapshot(
        self, person_id: str, name: str, realm_index: int, layer: int, source: str,
        age: int, lifespan: int | None, alive: bool = True, death_reason: str | None = None,
        spirit_root: str = "", cultivation_progress: float = 0.0,
        path: str = "dao", race: str = "human", world: str = "human",
        main_technique_id: str | None = None, affinity: float = 20.0,
        gender: str = "",
    ) -> dict[str, Any]:
        shell = SectNpc(
            person_id, name, "", realm_index, layer, age, int(lifespan or age + 1),
            spirit_root=spirit_root, cultivation_progress=cultivation_progress,
            path=path, race=race, world=world, gender=gender,
        )
        return {
            "id": person_id, "name": name, "realm_index": realm_index, "layer": layer,
            "realm_name": self._npc_realm_name(shell), "source": source,
            "age": age, "lifespan": lifespan, "alive": alive, "death_reason": death_reason,
            "spirit_root": spirit_root, "spirit_root_name": self._npc_root_name(spirit_root),
            "cultivation_progress": cultivation_progress,
            "path": path, "path_name": PATH_NAMES.get(path, path), "race": race,
            "race_name": RACE_DEFINITIONS.get(race, {"name": race})["name"], "world": world,
            "items": {}, "techniques": [], "last_requests": {}, "last_interactions": {},
            "main_technique_id": main_technique_id, "affinity": affinity,
            "gender": shell.gender, "gender_name": gender_name(shell.gender),
            "next_tribulation_age": None, "tribulation_count": 0, "tribulation_power": None,
        }

    def _generated_relationship(self, player: Player, role: str, rng: random.Random) -> dict[str, Any]:
        surnames = ["顾", "叶", "陆", "楚", "白", "谢", "云", "林"]
        given = ["玄真", "清微", "问岳", "照霜", "长离", "守一", "青崖", "明河"]
        name = rng.choice(surnames) + rng.choice(given)
        if role == "master":
            realm_index = min(5, player.realm_index + 1)
            layer = rng.randint(1, 3)
        elif role == "companion":
            realm_index = player.realm_index
            layer = player.layer
        elif player.layer > 1:
            realm_index = player.realm_index
            layer = rng.randint(1, player.layer - 1)
        else:
            realm_index = max(0, player.realm_index - 1)
            layer = 1
        person_id = f"event_{role}_{player.age}_{rng.randrange(1_000_000)}"
        age_ranges = {
            0: (14, 55), 1: (18, 90), 2: (55, 190), 3: (180, 450),
            4: (450, 1200), 5: (1200, 2600), 6: (2800, 7000),
            7: (7000, 18000), 8: (18000, 80000),
        }
        age = rng.randint(*age_ranges[realm_index])
        span = REALMS[realm_index].lifespan
        lifespan = max(age + 1, rng.randint(*span)) if span else None
        spirit_root = self._random_npc_root(realm_index, rng) if realm_index > 0 else "none"
        path = (player.technique.path if player.technique else player.path) if role == "companion" else rng.choice(list(PATH_NAMES))
        lifespan = self._scale_npc_lifespan(lifespan, path, age)
        return self._relationship_snapshot(
            person_id, name, realm_index, layer, "event", age, lifespan,
            spirit_root=spirit_root, path=path, race="human", world=player.world,
            main_technique_id=player.technique.id if role == "companion" and player.technique else None,
            affinity=28.0 if role == "companion" else 20.0,
        )

    @staticmethod
    def _default_npc_main_technique(npc: SectNpc) -> str | None:
        candidates = [
            technique for technique in TECHNIQUE_CATALOG.values()
            if technique.path == npc.path and technique.grade <= max(1, npc.realm_index)
            and technique.element != "sex" and can_practice_technique(npc.spirit_root, technique.element)
        ]
        if not candidates:
            candidates = [technique for technique in TECHNIQUE_CATALOG.values() if technique.element == "neutral"]
        return max(candidates, key=lambda technique: (technique.grade, technique.combat_bonus)).id if candidates else None

    def _sync_relationship_records(self, game: GameState) -> bool:
        """补齐旧存档字段，并让宗门师徒信息跟随真实 NPC。"""
        changed = False
        relations = [entry for entry in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.concubines, *game.player.disciples, *game.player.disciple_requests] if entry]
        for relation in relations:
            before = copy.deepcopy(relation)
            source = relation.get("source", "event")
            npc = self._find_npc(game, str(relation.get("npc_id") or relation.get("id")))
            if not npc and source not in {"world", "event", "captive", "relationship"}:
                npc = next((entry for entry in game.sects.get(source, SectState(source, "")).npcs if entry.id == relation.get("id")), None)
            if npc:
                relation.update(
                    realm_index=npc.realm_index, layer=npc.layer, realm_name=self._npc_realm_name(npc),
                    age=npc.age, lifespan=npc.lifespan, alive=npc.alive, death_reason=npc.death_reason,
                    spirit_root=npc.spirit_root, spirit_root_name=self._npc_root_name(npc.spirit_root),
                    cultivation_progress=npc.cultivation_progress,
                    path=npc.path, path_name=PATH_NAMES.get(npc.path, npc.path), race=npc.race,
                    race_name=RACE_DEFINITIONS.get(npc.race, {"name": npc.race})["name"], world=npc.world,
                    affinity=npc.affinity if npc.affinity is not None else relation.get("affinity", 20.0),
                    next_tribulation_age=npc.next_tribulation_age,
                    tribulation_count=npc.tribulation_count,
                    tribulation_power=npc.tribulation_power,
                )
            else:
                realm_index = int(relation.get("realm_index", 0))
                age = int(relation.get("age", {0: 30, 1: 50, 2: 120, 3: 300, 4: 800, 5: 1800}.get(realm_index, 30)))
                span = REALMS[realm_index].lifespan
                relation.setdefault("age", age)
                relation.setdefault("lifespan", max(age + 1, span[1]) if span else None)
                relation.setdefault("alive", True)
                relation.setdefault("death_reason", None)
                relation.setdefault(
                    "spirit_root",
                    self._random_npc_root(realm_index, random.Random(f"relation:{relation.get('id', '')}"))
                    if realm_index > 0 else "none",
                )
                relation.setdefault("cultivation_progress", 0.0)
                relation.setdefault("path", "dao")
                relation.setdefault("race", "human")
                relation.setdefault("world", "human")
                shell = SectNpc(
                    str(relation.get("id", "relation")), str(relation.get("name", "无名")), "",
                    realm_index, int(relation.get("layer", 1)), age, int(relation.get("lifespan") or age + 1),
                    path=str(relation.get("path", "dao")),
                )
                relation["realm_name"] = self._npc_realm_name(shell)
                relation["spirit_root_name"] = self._npc_root_name(relation["spirit_root"])
                relation["path_name"] = PATH_NAMES.get(relation["path"], relation["path"])
                relation["race_name"] = RACE_DEFINITIONS.get(relation["race"], {"name": relation["race"]})["name"]
            relation.setdefault("items", {})
            relation.setdefault("techniques", [])
            relation.setdefault("last_requests", {})
            relation.setdefault("last_interactions", {})
            relation.setdefault("affinity", 20.0)
            relation.setdefault("main_technique_id", None)
            relation.setdefault("breakthrough_bonus", 0.0)
            relation.setdefault("next_tribulation_age", None)
            relation.setdefault("tribulation_count", 0)
            relation.setdefault("tribulation_power", None)
            changed = changed or relation != before
        return changed

    def _annual_relationship_update(self, game: GameState, rng: random.Random | None = None) -> None:
        self._sync_relationship_records(game)
        player = game.player
        rng = rng or random.Random(f"relationships:{game.seed}:{player.age}")
        event_relations = [
            entry for entry in [player.master, player.dao_companion, *player.dao_friends, *player.concubines, *player.disciples, *player.disciple_requests]
            if entry and not self._find_npc(game, str(entry.get("npc_id") or entry.get("id", "")))
        ]
        for relation in event_relations:
            if not relation.get("alive", True):
                continue
            relation["age"] = int(relation.get("age", 0)) + 1
            lifespan = relation.get("lifespan")
            if lifespan is not None and relation["age"] >= lifespan:
                relation["alive"] = False
                relation["death_reason"] = "寿元耗尽，坐化尘世"
                is_companion = relation is player.dao_companion
                is_friend = relation in player.dao_friends
                is_concubine = relation in player.concubines
                game.history.append(HistoryRecord(
                    "SYS_RELATION_FALL", 1, player.age, "道侣坐化" if is_companion else "道友坐化" if is_friend else "侍妾坐化" if is_concubine else "师门故人坐化", None, "relation_fallen",
                    f"{relation['name']}寿元已尽，这段尘缘只余旧忆。",
                    {"relation_id": relation["id"], "alive": [True, False]}, ["system", "relationship", "friend" if is_friend else "dao_companion" if is_companion else "concubine" if is_concubine else "master", "death"],
                ))
                continue
            shell = SectNpc(
                id=str(relation["id"]), name=str(relation["name"]), title="",
                realm_index=int(relation["realm_index"]), layer=int(relation["layer"]),
                age=int(relation["age"]), lifespan=relation.get("lifespan"),
                spirit_root=str(relation.get("spirit_root", "")),
                cultivation_progress=float(relation.get("cultivation_progress", 0.0)),
                path=str(relation.get("path", "dao")), race=str(relation.get("race", "human")),
                world=str(relation.get("world", "human")),
                next_tribulation_age=relation.get("next_tribulation_age"),
                tribulation_count=int(relation.get("tribulation_count", 0)),
                tribulation_power=relation.get("tribulation_power"),
            )
            tribulation = self._resolve_npc_periodic_tribulation(game, shell, rng, "道侣" if relation is player.dao_companion else "")
            if tribulation and not shell.alive:
                relation.update(alive=False, death_reason=shell.death_reason)
                continue
            breakthrough = self._advance_npc_cultivation(
                shell, rng, allow_spirit_crossing=True,
                breakthrough_bonus=float(relation.get("breakthrough_bonus", 0)),
            )
            relation.update(
                realm_index=shell.realm_index, layer=shell.layer, realm_name=self._npc_realm_name(shell),
                lifespan=shell.lifespan, cultivation_progress=shell.cultivation_progress,
                spirit_root=shell.spirit_root, spirit_root_name=self._npc_root_name(shell.spirit_root),
                path=shell.path, path_name=PATH_NAMES.get(shell.path, shell.path), race=shell.race,
                race_name=RACE_DEFINITIONS.get(shell.race, {"name": shell.race})["name"], world=shell.world,
                next_tribulation_age=shell.next_tribulation_age,
                tribulation_count=shell.tribulation_count,
                tribulation_power=shell.tribulation_power,
            )
            if breakthrough:
                is_companion = relation is player.dao_companion
                is_friend = relation in player.dao_friends
                is_concubine = relation in player.concubines
                game.history.append(HistoryRecord(
                    "SYS_RELATION_BREAKTHROUGH", 1, player.age, "道侣破境" if is_companion else "道友破境" if is_friend else "侍妾破境" if is_concubine else "师门破境", None, "npc_breakthrough",
                    f"{relation['name']}凭借{relation['spirit_root_name']}由{breakthrough['old']}突破至{breakthrough['new']}。",
                    {"relation_id": relation["id"], "realm": [breakthrough["old"], breakthrough["new"]]}, ["system", "relationship", "friend" if is_friend else "dao_companion" if is_companion else "concubine" if is_concubine else "master", "npc"],
                ))
        expired = [entry for entry in player.disciple_requests if not entry.get("alive", True)]
        if expired:
            expired_ids = {entry["id"] for entry in expired}
            player.disciple_requests = [entry for entry in player.disciple_requests if entry["id"] not in expired_ids]
        self._sync_relationship_records(game)

    @staticmethod
    def _recruit_realm_index(roll: float, world: str = "human") -> int:
        distributions = FACTION_SYSTEMS.get("recruitment_distribution_by_world", {})
        rows = distributions.get(world, FACTION_SYSTEMS["recruitment_distribution"])
        for entry in rows:
            if roll < float(entry["upper"]):
                return int(entry["realm_index"])
        raise ValueError("宗门招募概率表未覆盖完整区间")

    @classmethod
    def _roll_recruit_age_lifespan(
        cls, realm_index: int, path: str, rng: random.Random, *, young: bool = False,
    ) -> tuple[int, int | None]:
        """Generate recruits with a meaningful amount of lifespan still remaining."""
        age_ranges = {
            0: (16, 36), 1: (18, 72), 2: (45, 150), 3: (120, 330),
            4: (280, 850), 5: (750, 2300), 6: (2200, 5800),
            7: (6000, 21000), 8: (14000, 80000), 9: (40000, 150000),
            10: (120000, 520000), 11: (420000, 1500000), 12: (1000000, 4200000),
        }
        low, high = age_ranges.get(realm_index, (18, 80))
        if young:
            high = low + max(6, (high - low) // 2)
        lifespan_range = REALMS[realm_index].lifespan
        if lifespan_range is None:
            return rng.randint(low, high), None
        lifespan = rng.randint(*lifespan_range) * cls._npc_lifespan_multiplier(path)
        minimum_remaining = max(12, int(lifespan * 0.25))
        safe_high = max(low, min(high, lifespan - minimum_remaining))
        safe_low = min(low, safe_high)
        age = rng.randint(safe_low, safe_high)
        return age, lifespan

    def _recruit_sect_npc(self, sect: SectState, world_age: int, rng: random.Random) -> SectNpc:
        realm_index = self._recruit_realm_index(rng.random(), sect.world)
        surnames = ["顾", "叶", "陆", "楚", "白", "谢", "云", "林", "江", "闻"]
        given = ["玄", "宁", "川", "微", "岳", "霜", "澄", "昭", "离", "砚"]
        name = rng.choice(surnames) + rng.choice(given)
        layer = rng.randint(1, REALMS[realm_index].layers)
        title = "仙宫供奉" if realm_index >= 9 else "跨域客卿" if realm_index >= 5 else "加盟客卿" if realm_index >= 3 else "新晋内门" if realm_index == 2 else "新入门弟子"
        path = self._random_npc_path(sect.id, rng)
        age, lifespan = self._roll_recruit_age_lifespan(realm_index, path, rng)
        race = "human"
        if self._world_supports(sect.world, "races"):
            race = rng.choice([
                race_id for race_id, definition in RACE_DEFINITIONS.items()
                if sect.world in definition.get("worlds", [])
            ])
        npc = SectNpc(
            id=f"{sect.id}_recruit_{world_age}_{len(sect.npcs)}", name=name, title=title,
            realm_index=realm_index, layer=layer, age=age, lifespan=lifespan,
            spirit_root=self._random_npc_root(realm_index, rng),
            path=path, race=race, world=sect.world,
        )
        npc.affinity = rng.uniform(-6, 10)
        npc.treasure_item_id = self._select_npc_treasure(npc, rng)
        sect.npcs.append(npc)
        return npc

    def _select_event(self, game: GameState, action: str, rng: random.Random) -> dict[str, Any] | None:
        # 无灵根开局的第一节点是路线入口，不能被普通随机事件淹没。
        if game.player.spirit_root == "none" and game.player.realm_index == 0 and game.player.body_training == 0:
            return self.events_by_id["EVT_MORTAL_BODY_BEGIN_001"]
        if (
            game.player.realm_index == 0 and game.player.born_rootless and game.player.age >= 25
            and game.player.body_training < 3 and game.player.mortal_aspiration is None
        ):
            return self.events_by_id["EVT_MORTAL_ASPIRATION_001"]
        candidates: list[tuple[dict[str, Any], float]] = []
        for event in sorted(self.events, key=lambda value: value["id"]):
            tags = event.get("tags", [])
            world_tags = [tag for tag in tags if tag.startswith("world:")]
            if (
                int(WORLD_SYSTEMS.get("world_profiles", {}).get(game.player.world, {}).get("tier", 1)) >= 3
                and f"world:{game.player.world}" not in world_tags
            ):
                continue
            if world_tags and f"world:{game.player.world}" not in world_tags:
                continue
            if "manual_only" in tags:
                continue
            if "revenge" in tags and not self._revenge_ready(game, "ambient", str(event["id"])):
                continue
            if "jinque_acquisition" in tags and game.player.realm_index >= 3:
                continue
            if "probability_gate" in tags:
                continue
            if (
                game.player.world != "human" and "faction" in tags
                and f"world:{game.player.world}" not in tags
            ):
                continue
            if event["id"] == "EVT_MORTAL_ROOT_COMPLETE_001":
                continue
            if "faction" in tags and "faction_join" not in tags:
                continue
            is_mortal_event = "mortal" in tags
            if game.player.realm_index == 0 and not is_mortal_event:
                continue
            if game.player.realm_index > 0 and is_mortal_event:
                continue
            if not self._condition(event.get("conditions", {}), game):
                continue
            if event.get("repeat") == "once" and any(h.event_id == event["id"] for h in game.history):
                continue
            weight = self._event_weight(event, game, action)
            candidates.append((event, max(0, weight)))
        total = sum(weight for _, weight in candidates)
        if total <= 0:
            return None
        roll = rng.random() * total
        for event, weight in candidates:
            roll -= weight
            if roll <= 0:
                if "revenge" in event.get("tags", []):
                    self._record_revenge_trigger(game, "ambient", str(event["id"]))
                return event
        selected = candidates[-1][0]
        if "revenge" in selected.get("tags", []):
            self._record_revenge_trigger(game, "ambient", str(selected["id"]))
        return selected

    @staticmethod
    def _event_weight(event: dict[str, Any], game: GameState, action: str) -> float:
        tags = event.get("tags", [])
        weight = float(event.get("weight", 1)) * event.get("intent_weights", {}).get(action, 1.0)
        if "jinque_acquisition" in tags and any(
            "jinque_acquisition" in record.tags for record in game.history
        ):
            weight *= 0.20
        if "negative" in tags:
            weight *= negative_event_multiplier(game.player)
        return max(0.0, weight)

    def _instantiate_event(self, event: dict[str, Any], game: GameState, rng: random.Random) -> dict[str, Any]:
        result = {key: copy.deepcopy(event[key]) for key in ("id", "title", "body", "choices")}
        for choice in result["choices"]:
            original = next(item for item in event["choices"] if item["id"] == choice["id"])
            choice["enabled"] = self._condition(original.get("conditions", {}), game)
            choice.pop("effects", None)
            choice.pop("conditions", None)
        tags = event.get("tags", [])
        if game.player.realm_index >= 4 and "faction" in tags and "duty" in tags and "war" not in tags:
            delegate_cost = int(FACTION_SYSTEMS["shareholder_delegate_cost"])
            decline_cost = int(FACTION_SYSTEMS["shareholder_decline_cost"])
            result["choices"].extend([
                {"id": "__delegate_faction_task", "text": f"派遣门下弟子代为完成（宗门贡献 -{delegate_cost}）", "enabled": True},
                {"id": "__decline_faction_task", "text": f"以议事席身份拒绝任务（宗门贡献 -{decline_cost}）", "enabled": True},
            ])
        if event.get("combat"):
            combat = event["combat"]
            target = self._generate_cultivator_target(game.player, combat["target_name"], combat, rng, game=game)
            combat_type = str(combat.get("combat_type", "cultivator"))
            if combat_type != "cultivator":
                target["combat_type"] = combat_type
                target["action"] = str(combat.get("action", "hunt_beast" if combat_type == "beast" else "slay"))
                if combat.get("success_threshold") is not None:
                    target["success_threshold"] = float(combat["success_threshold"])
                target["members"] = [{
                    "name": target["target_name"], "power": target["target_power"],
                    "realm_index": target["target_realm_index"], "layer": target["target_layer"],
                    "kind": "beast" if combat_type == "beast" else combat_type,
                    "path": "monster" if combat_type == "beast" else "dao",
                }]
            self._cache_encounter_target(game, target, rng)
            result["runtime"] = target
            result["body"] = (
                result["body"]
                .replace("{target_power}", f"{target['target_power']:.0f}")
                .replace("{target_realm}", target["target_realm_display"])
            )
            if self._world_supports(game.player.world, "races"):
                result["body"] += f" 对方属于{target['race_name']}：{target['race_description']}"
            if len(target.get("members", [])) > 1:
                result["body"] += f" 对方实际共有{len(target['members'])}人结队，显示战斗力为全队合计值。"
        return result

    def _generate_cultivator_target(
        self, player: Player, target_name: str, settings: dict[str, Any], rng: random.Random,
        game: GameState | None = None, forced_race: str | None = None,
    ) -> dict[str, Any]:
        offsets = settings.get("realm_offsets", [[0, 1.0]])
        offset = int(rng.choices([entry[0] for entry in offsets], weights=[entry[1] for entry in offsets], k=1)[0])
        target_realm_index = max(1, min(self._world_realm_cap(player.world), player.realm_index + offset))
        target_layer = rng.randint(1, REALMS[target_realm_index].layers)
        expected = expected_combat_power(target_realm_index, target_layer)
        mean = expected * float(settings.get("expectation_multiplier", 1.0))
        sigma = expected * float(settings.get("power_sigma", 0.16))
        lower, upper = settings.get("power_bounds", [0.55, 1.5])
        sampled = rng.gauss(mean, sigma)
        target_power = max(expected * float(lower), min(expected * float(upper), sampled))
        shell = SectNpc("encounter", target_name, "", target_realm_index, target_layer, 0, 1)
        visible = target_realm_index <= player.realm_index + 1
        target_race = forced_race or "human"
        if self._world_supports(player.world, "races"):
            race_pool = [race_id for race_id, definition in RACE_DEFINITIONS.items() if player.world in definition.get("worlds", [])]
            target_race = forced_race or choose_weighted_race(
                race_pool, self._player_allegiance_race(player), game.race_relations if game else {}, rng,
            )
            target_name = f"{RACE_DEFINITIONS[target_race]['name']}{target_name}"
        target = {
            "target_name": target_name,
            "target_power": round(max(1.0, target_power), 1),
            "primary_power": round(max(1.0, target_power), 1),
            "target_expected_power": round(expected, 1),
            "target_realm_index": target_realm_index,
            "target_layer": target_layer,
            "target_realm_visible": visible,
            "target_realm_display": self._npc_realm_name(shell) if visible else "无法看清",
            "combat_type": "cultivator",
            "race": target_race,
            "race_name": RACE_DEFINITIONS[target_race]["name"],
            "race_description": RACE_DEFINITIONS[target_race]["description"],
            "world": player.world,
        }
        return self._add_enemy_party(target, settings, rng)

    @staticmethod
    def _encounter_person_name(race_id: str, rng: random.Random) -> str:
        surnames = ["顾", "叶", "陆", "楚", "白", "谢", "云", "林", "闻", "景", "苍", "月"]
        given = ["玄", "宁", "川", "微", "岳", "霜", "澄", "昭", "离", "砚", "烬", "渊"]
        base = rng.choice(surnames) + rng.choice(given)
        return base if race_id == "human" else f"{RACE_DEFINITIONS.get(race_id, {'name': race_id})['name']}·{base}"

    def _cache_encounter_target(self, game: GameState, target: dict[str, Any], rng: random.Random) -> None:
        """Stage disposable strangers; promote only repeat/important characters."""
        if target.get("combat_type") != "cultivator":
            return
        cache_limit = int(RACE_SYSTEMS.get("diplomacy", {}).get("encounter_cache_limit", 36))
        for index, member in enumerate(target.get("members", [])):
            if member.get("npc_id"):
                continue
            realm_index = int(member["realm_index"])
            layer = int(member["layer"])
            race_id = str(member.get("race", target.get("race", "human")))
            age_ranges = {
                1: (18, 95), 2: (55, 190), 3: (170, 470), 4: (420, 1350),
                5: (1000, 2900), 6: (2500, 9000), 7: (7000, 24000), 8: (15000, 90000),
            }
            age = rng.randint(*age_ranges.get(realm_index, (18, 70)))
            span = REALMS[realm_index].lifespan
            lifespan = max(age + 1, rng.randint(*span)) if span else None
            npc_id = f"encounter_{game.player.world}_{uuid.uuid4().hex[:12]}"
            name = self._encounter_person_name(race_id, rng)
            npc = SectNpc(
                npc_id, name, str(target.get("target_name", "偶遇修士")) if index == 0 else "同行修士",
                realm_index, layer, age, lifespan,
                spirit_root=self._random_npc_root(realm_index, rng), path=rng.choice(list(PATH_NAMES)),
                race=race_id, world=game.player.world, affinity=rng.uniform(-18, 12),
            )
            npc.lifespan = self._scale_npc_lifespan(npc.lifespan, npc.path, npc.age)
            npc.treasure_item_id = self._select_npc_treasure(npc, rng)
            base_power = max(1.0, self._npc_power(npc))
            npc.combat_factor = max(0.1, float(member["power"]) / base_power)
            member.update(
                name=name, npc_id=npc_id, treasure_item_id=npc.treasure_item_id, path=npc.path,
                age=npc.age, lifespan=npc.lifespan, spirit_root=npc.spirit_root,
                gender=npc.gender,
            )
            entry = {
                "id": npc_id, "npc": npc.to_dict(), "combat_power": float(member["power"]),
                "seen_count": 1, "first_seen_age": game.player.age, "last_seen_age": game.player.age,
            }
            push_fifo_cache(game.encounter_npc_cache, entry, cache_limit)
            if self._would_enter_spirit_ranking(game, npc, float(member["power"])):
                self._promote_cached_npc(game, npc_id, "天榜战力")
        if target.get("members"):
            primary = target["members"][0]
            target.update(
                target_name=primary["name"], npc_id=primary.get("npc_id"),
                treasure_item_id=primary.get("treasure_item_id"), primary_power=primary["power"],
            )

    def _would_enter_spirit_ranking(self, game: GameState, npc: SectNpc, power: float) -> bool:
        ranking_world = npc.world
        if not self._world_supports(ranking_world, "ranking"):
            return False
        keys = [
            (entry.realm_index, entry.layer, self._npc_power(entry))
            for entry in [
                *game.world_npcs.values(), *game.notable_npcs.values(),
                *(member for sect in game.sects.values() if sect.world == ranking_world for member in sect.npcs),
            ]
            if entry.alive and entry.world == ranking_world
        ]
        keys.append((game.player.realm_index, game.player.layer, self._player_intrinsic_combat_power(game.player)))
        keys.sort(reverse=True)
        cutoff = keys[19] if len(keys) >= 20 else (-1, -1, -1.0)
        return (npc.realm_index, npc.layer, power) > cutoff

    def _promote_cached_npc(self, game: GameState, npc_id: str, reason: str) -> SectNpc | None:
        entry = next((row for row in game.encounter_npc_cache if row.get("id") == npc_id), None)
        if not entry:
            return game.notable_npcs.get(npc_id)
        npc = SectNpc.from_dict(entry["npc"])
        npc.age += max(0, game.player.age - int(entry.get("last_seen_age", game.player.age)))
        game.notable_npcs[npc.id] = npc
        game.encounter_npc_cache = [row for row in game.encounter_npc_cache if row.get("id") != npc_id]
        game.history.append(HistoryRecord(
            "SYS_NPC_PROMOTED", 1, game.player.age, "人物留名", reason, "promoted",
            f"曾经偶遇的{npc.title}{npc.name}因{reason}不再只是过客，其后续命数将持续演算。",
            {"npc_id": npc.id, "reason": reason}, ["system", "npc", "world_state"],
        ))
        return npc

    def _add_enemy_party(
        self, target: dict[str, Any], settings: dict[str, Any], rng: random.Random,
    ) -> dict[str, Any]:
        members = [{
            "name": target["target_name"], "power": float(target.get("primary_power", target["target_power"])),
            "realm_index": int(target["target_realm_index"]), "layer": int(target["target_layer"]),
            "npc_id": target.get("npc_id"), "faction_id": target.get("faction_id"), "path": target.get("path", "dao"),
            "race": target.get("race", "human"), "treasure_item_id": target.get("treasure_item_id"),
            "notorious": bool(target.get("notorious", False)), "notoriety": int(target.get("notoriety", 0)),
        }]
        if rng.random() < float(WORLD_SYSTEMS["faction_conflict"]["npc_team_chance"]):
            total = rng.randint(2, 3)
            realm_cap = self._world_realm_cap(str(target.get("world", "human")))
            for index in range(1, total):
                realm_index = max(1, min(realm_cap, int(target["target_realm_index"]) + rng.choice([-1, 0, 0, 1])))
                layer = rng.randint(1, REALMS[realm_index].layers)
                expected = expected_combat_power(realm_index, layer)
                members.append({
                    "name": f"同行修士{index}", "power": round(max(1.0, rng.gauss(expected, expected * 0.12)), 1),
                    "realm_index": realm_index, "layer": layer, "npc_id": None,
                    "faction_id": target.get("faction_id"), "race": target.get("race", "human"),
                    "path": target.get("path", "dao"),
                    "treasure_item_id": None,
                })
        target["members"] = members
        target["target_power"] = npc_team_combat_power(member["power"] for member in members)
        return target

    def _condition(self, condition: dict[str, Any], game: GameState) -> bool:
        if not condition:
            return True
        if "all" in condition:
            return all(self._condition(entry, game) for entry in condition["all"])
        if "any" in condition:
            return any(self._condition(entry, game) for entry in condition["any"])
        if "not" in condition:
            return not self._condition(condition["not"], game)
        if "happened" in condition:
            return any(entry.event_id == condition["happened"] for entry in game.history)
        if "has_item" in condition:
            return has_item(game.player, condition["has_item"], int(condition.get("quantity", 1)))
        if "knows_technique" in condition:
            technique_id = str(condition["knows_technique"])
            player = game.player
            return any(
                technique is not None and technique.id == technique_id
                for technique in [player.technique, player.support_technique, player.body_technique, *player.combat_techniques, *player.known_techniques]
            )
        if "has_flag" in condition:
            return condition["has_flag"] in game.player.story_flags
        if "world_npc" in condition:
            spec = condition["world_npc"]
            npc = game.world_npcs.get(str(spec.get("id")))
            return bool(npc) and all(getattr(npc, key, None) == value for key, value in spec.items() if key != "id")
        if "has_affinity" in condition:
            return condition["has_affinity"] in [*self._base_affinities(game.player), *game.player.additional_roots]
        left = self._path(condition["path"], game)
        return OPS[condition.get("op", "eq")](left, condition.get("value"))

    def _path(self, path: str, game: GameState) -> Any:
        mapping = {
            "player.alive": game.player.alive,
            "player.age": game.player.age,
            "player.karma": game.player.karma,
            "player.effective_karma": effective_karma(game.player),
            "player.realm_index": game.player.realm_index,
            "player.layer": game.player.layer,
            "player.hp_ratio": game.player.hp / max_hp(game.player),
            "player.mp_ratio": game.player.mp / max_mp(game.player),
            "player.path": game.player.technique.path if game.player.technique else game.player.path,
            "player.has_main_technique": game.player.technique is not None,
            "player.monster_species_id": game.player.monster_species_id,
            "player.monster.evolution_id": game.player.monster_evolution_id,
            "player.monster.adaptations": game.player.monster_adaptations,
            "player.monster.imprints": game.player.monster_bloodline_imprints,
            "player.monster.history": game.player.monster_evolution_history,
            "player.has_master": game.player.master is not None,
            "player.master_available": bool(
                game.player.master and game.player.master.get("alive", True)
                and game.player.master.get("world", game.player.world) == game.player.world
            ),
            "player.has_companion": bool(
                game.player.dao_companion and game.player.dao_companion.get("alive", True)
                and game.player.dao_companion.get("world", game.player.world) == game.player.world
            ),
            "player.disciple_count": len(game.player.disciples),
            "player.disciple_total": len(game.player.disciples) + len(game.player.disciple_requests),
            "player.living_disciple_count": sum(
                entry.get("alive", True) and entry.get("world", game.player.world) == game.player.world
                for entry in game.player.disciples
            ),
            "player.sha_qi": game.player.sha_qi,
            "player.fame": game.player.fame,
            "player.born_rootless": game.player.born_rootless,
            "player.mortal_aspiration": game.player.mortal_aspiration,
            "player.spouse": game.player.spouse,
            "player.children": game.player.children,
            "player.official_rank": game.player.official_rank,
            "player.military_merit": game.player.military_merit,
            "player.jianghu_reputation": game.player.jianghu_reputation,
            "player.spirit_root": game.player.spirit_root,
            "player.body_training": game.player.body_training,
            "player.faction_id": game.player.faction_id,
            "player.faction_contribution": game.player.faction_contribution,
            "player.world": game.player.world,
        }
        if path not in mapping:
            raise ValueError(f"未知条件路径：{path}")
        return mapping[path]

    @staticmethod
    def _base_affinities(player: Player) -> list[str]:
        return root_elements(player.spirit_root)

    @staticmethod
    def _is_story_combat_check(event_id: str, effect: dict[str, Any]) -> bool:
        return bool(
            event_id in STORY_COMBAT_SCENARIOS
            and effect.get("type") == "attribute_check"
            and any(check.get("stat") == "combat_power" for check in effect.get("checks", []))
        )

    def _resolve_story_combat_check(
        self, effect: dict[str, Any], game: GameState, pending: dict[str, Any], rng: random.Random,
    ) -> tuple[str, str]:
        power_check = next(check for check in effect["checks"] if check.get("stat") == "combat_power")
        target_power = float(power_check["value"])
        # The scripted power already expresses the authored threat. Reusing an
        # inferred higher realm would count the same advantage twice through
        # both raw power and realm suppression.
        realm_index, layer = game.player.realm_index, game.player.layer
        event_id = str(pending["id"])
        scenario = copy.deepcopy(STORY_COMBAT_SCENARIOS[event_id])
        members = []
        for member in scenario["enemy_members"]:
            effective_power = target_power * float(member["share"])
            member_realm = max(0, min(len(REALMS) - 1, realm_index + int(member.get("realm_offset", 0))))
            members.append({
                "name": str(member["name"]),
                "power": effective_power,
                "full_power": self._story_unit_full_power(member, member_realm, effective_power),
                "realm_index": member_realm,
                "path": str(member.get("path", "dao")),
                "kind": str(member.get("kind", "cultivator")),
            })
        target = {
            "target_name": scenario["target_name"],
            "target_power": target_power,
            "target_realm_index": realm_index,
            "target_layer": layer,
            "combat_type": "story",
            "objective": "repel",
            "enemy_objective": "kill",
            "natural_terrain": scenario["natural_terrain"],
            "artificial_conditions": list(scenario.get("artificial_conditions", [])),
            "max_rounds": int(scenario.get("max_rounds", 6)),
            "members": members,
            "player_allies": scenario.get("player_allies", []),
            "story_beats": scenario["story_beats"],
            "story_choice_id": pending.get("_choice_id"),
            # Epic chains contain several consecutive encounters and their own
            # resource gates. Keep the detailed battle state, but convert only
            # part of it into persistent character injury between scenes.
            "loss_scale": 0.25,
            "mp_loss_scale": 0.0,
        }
        result, combat_summary = self._combat(game, target, False, rng)
        if result == "victory":
            return "check_success", f"{combat_summary}{effect.get('success_text', '')}"
        transformation_revives = "prevent_defeat_once" in active_transformation_profile(game.player)["traits"]
        reason = str(effect.get("failure_reason", "未能战胜剧情强敌"))
        if transformation_revives:
            game.player.hp = max(1.0, game.player.hp)
            if game.last_combat_report:
                game.last_combat_report["death_prevented"] = True
                game.last_combat_report["result"] = "defeat_survived"
                game.last_combat_report.setdefault("key_events", []).append("凤凰变涅槃替你承受了剧情中本应发生的一次陨落。")
            return "check_failed", f"{combat_summary}{reason}；凤凰变涅槃保住了性命，但本次剧情目标失败。"
        self._die(game, reason, event_id)
        if game.last_combat_report:
            game.last_combat_report["result"] = "dead"
            game.last_combat_report["result_grade"] = "溃败"
        return "dead", f"{combat_summary}{reason}。"

    @staticmethod
    def _story_unit_full_power(
        definition: dict[str, Any], realm_index: int, effective_power: float,
    ) -> float:
        if definition.get("full_power") is not None:
            return max(effective_power, float(definition["full_power"]))
        middle_layer = max(1, (REALMS[realm_index].layers + 1) // 2)
        baseline = expected_combat_power(realm_index, int(definition.get("layer", middle_layer)))
        return max(effective_power, baseline * float(definition.get("full_power_multiplier", 1.0)))

    def _effect(self, effect: dict[str, Any], game: GameState, pending: dict[str, Any], rng: random.Random) -> tuple[str | None, str]:
        player = game.player
        kind = effect["type"]
        value = effect.get("value", 0)
        if "range" in effect:
            value = rng.randint(*effect["range"])
        if kind == "add_opportunity":
            amount = round(float(value) * opportunity_multiplier(player), 1)
            if player.world == "celestial" and self._court_law_active(game, "immortal_twofold"):
                amount = round(amount * 1.10, 1)
            self._add_opportunity(player, amount)
            sign = "+" if amount >= 0 else ""
            return None, f"机缘 {sign}{amount}。"
        if kind == "concubine_proposal":
            return self._resolve_concubine_proposal(game, pending, bool(effect.get("accept", False)))
        if kind == "concubine_revenge":
            return self._resolve_concubine_revenge(game, pending, str(effect.get("method", "")), rng)
        if kind == "concubine_escape":
            return self._resolve_concubine_escape(game, pending, str(effect.get("method", "")), rng)
        if kind == "relationship_sanction":
            return self._resolve_relationship_sanction(
                game, pending, str(effect.get("role", "")), str(effect.get("mode", "")), rng,
            )
        if kind == "add_karma":
            player.karma = max(0, player.karma + float(value))
            sign = "+" if value >= 0 else ""
            return None, f"因果 {sign}{value}。"
        if kind == "add_fame":
            player.fame = max(0.0, player.fame + float(value))
            sign = "+" if value >= 0 else ""
            return None, f"威名 {sign}{value}。"
        if kind == "add_sha_qi":
            player.sha_qi = max(0.0, player.sha_qi + float(value))
            sign = "+" if value >= 0 else ""
            return None, f"煞气 {sign}{value}。"
        if kind == "add_heart_demon":
            player.heart_demon = max(0.0, player.heart_demon + float(value))
            sign = "+" if value >= 0 else ""
            return None, f"心魔 {sign}{value}。"
        if kind == "relationship_affinity":
            role = str(effect.get("role", "companion"))
            if role == "master":
                relation = player.master
            elif role == "companion":
                relation = player.dao_companion
            elif role == "disciple":
                living = [entry for entry in player.disciples if entry.get("alive", True) and entry.get("world", player.world) == player.world]
                relation = rng.choice(living) if living else None
            else:
                raise ValueError("未知关系角色")
            if not relation:
                return "relationship_absent", "对应之人当前不在身边。"
            relation["affinity"] = float(relation.get("affinity", 20)) + float(value)
            source_npc = self._find_npc(game, str(relation.get("id", "")))
            if source_npc:
                source_npc.affinity = float(relation["affinity"])
            return "relationship_changed", f"{relation.get('name', '对方')}好感 {float(value):+g}。"
        if kind == "add_hostility":
            entity = player.world if effect.get("entity") == "current" else str(effect.get("entity"))
            key = self._hostility_key(str(effect.get("kind", "world")), entity)
            player.hostility[key] = max(0.0, player.hostility.get(key, 0) + float(value))
            return None, f"{key} 敌对值 +{float(value):g}。"
        if kind == "wanted_response":
            return self._resolve_wanted_response(game, pending, str(effect["response"]), rng)
        if kind == "war_vanguard":
            return self._resolve_war_vanguard(game, pending, str(effect.get("mode", "fight")), rng)
        if kind == "wanted_settlement":
            return self._resolve_wanted_settlement(game, pending, str(effect.get("mode", "")), rng)
        if kind == "runtime_combat":
            target = copy.deepcopy(pending.get("runtime") or {})
            if not target:
                raise ValueError("遭遇目标已经不存在")
            event_tags = self.events_by_id.get(str(pending.get("id", "")), {}).get("tags", [])
            target["non_story_combat"] = "story_chain" not in event_tags
            action = str(target.get("action", "slay"))
            result, summary = self._combat(game, target, bool(effect.get("lethal", False)), rng)
            return result, self._apply_combat_action_rewards(game, action, result, summary, rng)
        if kind == "cultivator_reaction":
            threshold = float(WORLD_SYSTEMS["faction_conflict"]["fame_deterrence_threshold"])
            if player.fame >= threshold:
                return "deterred", "你的威名足以压住贪念，对方最终不敢追来。"
            chance = float(effect.get("chance", 0.2)) * max(0.0, 1 - player.fame / max(1.0, threshold))
            if rng.random() >= chance:
                return "ignored", "对方虽有不满，最终没有节外生枝。"
            target = self._generate_cultivator_target(player, "心生贪念的修士", ACTIONS["slay"]["combat"], rng, game=game)
            self._cache_encounter_target(game, target, rng)
            target["kill_karma"] = True
            target["action"] = "slay"
            ambush = self._instantiate_event(self.events_by_id["EVT_ENCOUNTER_AMBUSH_001"], game, rng)
            ambush["runtime"] = target
            ambush["body"] = (
                ambush["body"].replace("{target_realm}", str(target["target_realm_display"]))
                .replace("{target_power}", f"{target['target_power']:.0f}")
            )
            if len(target.get("members", [])) > 1:
                ambush["body"] += f" 对方共有{len(target['members'])}人，显示战力为小队合计值。"
            game.pending_event = ambush
            return "ambushed", "你的拒绝激起了对方的贪念，一场杀人夺宝的恶战紧随而来。"
        if kind == "affinity_gift":
            runtime = pending.get("runtime", {})
            npc_id = str(runtime.get("npc_id", ""))
            npc = self._find_npc(game, npc_id)
            if not npc or not npc.alive:
                return "visitor_absent", "故人临时有事，只留下一封问候信。"
            mode = str(effect.get("mode", "accept"))
            if mode == "decline":
                affinity = self._adjust_person_affinity(game,npc_id,1)
                return "declined", f"你未收礼物，但{npc.name}仍领会了你的礼数（好感 {affinity:.0f}）。"
            if mode in {"discuss","share"}:
                gain = rng.randint(5,10) * max(1,npc.realm_index)
                self._add_opportunity(player, gain)
                if mode == "share":
                    player.mp = min(max_mp(player),player.mp + max_mp(player) * 0.08)
                affinity = self._adjust_person_affinity(game,npc_id,2)
                return "discussed", f"你与{npc.name}论道互证，机缘 +{gain}，彼此好感升至 {affinity:.0f}。"
            eligible_goods = [
                row for row in MARKET_GOODS
                if row["kind"] == "item" and row.get("world","human") == player.world
                and int(row["tier"]) <= max(1,npc.realm_index)
                and row["content_id"] in ITEM_CATALOG
                and not {"currency","root_manual"}.intersection(ITEM_CATALOG[row["content_id"]].tags)
            ]
            candidates = list(dict.fromkeys(row["content_id"] for row in eligible_goods))
            if candidates and rng.random() < 0.68:
                best_tier = max(int(row["tier"]) for row in eligible_goods)
                suitable = list(dict.fromkeys(
                    row["content_id"] for row in eligible_goods if int(row["tier"]) == best_tier
                ))
                item_id = rng.choice(suitable or candidates)
                add_item(player,item_id)
                gift_text = ITEM_CATALOG[item_id].name
            else:
                amount = rng.randint(3,8) * max(1,npc.realm_index)
                add_item(player,"spirit_stone",amount)
                gift_text = f"下品灵石 ×{amount}"
            affinity = self._adjust_person_affinity(game,npc_id,3)
            return "gift_received", f"{npc.name}赠予你{gift_text}；对方境界越高，来礼层次也越高（好感 {affinity:.0f}）。"
        if kind == "treasure_reward_choice":
            return self._claim_treasure_reward(game, pending, str(effect["category"]))
        if kind == "personal_revenge_response":
            runtime = pending.get("runtime", {})
            target = copy.deepcopy(runtime.get("target") or {})
            if not target:
                return "revenge_absent", "仇家已不知所踪。"
            mode = str(effect.get("mode", "fight"))
            if mode == "escape":
                mp_ratio = player.mp / max(1.0,max_mp(player))
                player.mp = max(0.0,player.mp - max_mp(player) * 0.16)
                chance = min(0.85,0.30 + mp_ratio * 0.45)
                if rng.random() < chance:
                    return "escaped", f"你以遁术摆脱追杀（成功率 {chance:.0%}），MP 消耗 16%。"
                target["target_power"] *= 1.08
                result, text = self._combat(game,target,True,rng)
                return result, f"遁术失败，你被迫仓促接战。{text}"
            support_text = ""
            if mode == "ally":
                ally = self._find_npc(game,str(runtime.get("ally_id", "")))
                if not ally or not ally.alive:
                    raise ValueError("能够驰援的故交已经不在")
                support = self._npc_power(ally) * 0.50
                target["target_power"] = max(1.0,float(target["target_power"]) - support)
                support_text = f"{ally.name}及时驰援，以约 {support:.0f} 支援战力分担攻势。"
            elif mode == "sect":
                support = float(runtime.get("sect_support_power",0)) * 0.35
                if support <= 0:
                    raise ValueError("当前没有宗门同道可以接应")
                target["target_power"] = max(1.0,float(target["target_power"]) - support)
                support_text = f"宗门接应分担约 {support:.0f} 战力压力。"
            result, text = self._combat(game,target,True,rng)
            return result, support_text + text
        if kind == "heal":
            amount = max_hp(player) * float(value)
            player.hp = min(max_hp(player), player.hp + amount)
            return None, f"HP 恢复 {amount:.0f}。"
        if kind == "restore_mp":
            amount = max_mp(player) * float(value)
            player.mp = min(max_mp(player), max(0, player.mp + amount))
            return None, f"MP {'恢复' if amount >= 0 else '消耗'} {abs(amount):.0f}。"
        if kind == "damage":
            amount = max_hp(player) * float(value)
            player.hp = max(0, player.hp - amount)
            if player.hp <= 0:
                self._die(game, effect.get("reason", "伤势过重"), pending["id"])
            return "dead" if not player.alive else "injured", f"受到 {amount:.0f} 点伤害。"
        if kind == "add_item":
            add_item(player, effect["item_id"], int(effect.get("quantity", 1)))
            return None, f"获得{ITEM_CATALOG[effect['item_id']].name}。"
        if kind == "remove_item":
            removed = remove_item(player, effect["item_id"], int(effect.get("quantity", 1)))
            return None, "失去了一件物品。" if removed else "你身上没有可失去的东西。"
        if kind == "set_flag":
            flag = str(effect["flag"])
            if flag not in player.story_flags:
                player.story_flags.append(flag)
            return None, effect.get("text", "命运的轨迹悄然延伸。")
        if kind == "set_milestone":
            milestone = str(effect["milestone"])
            player.milestones.setdefault(milestone, player.age)
            return None, effect.get("text", "这一年被记入命途节点。")
        if kind == "restore_faction_control":
            sect_id = str(pending.get("runtime", {}).get("sect_id", ""))
            sect = game.sects.get(sect_id)
            plan = self._intrigue_state(game).get("succession_plans", {}).get(sect_id, {})
            if not sect or sect.extinct or sect.world != player.world or not plan.get("eligible_return"):
                return "faction_return_expired", "旧宗已经不复存在，祖师之约就此作罢。"
            plan["eligible_return"] = False
            if not bool(effect.get("accept", False)):
                return "faction_return_declined", f"你谢绝了{sect.name}门人的迎请，让后辈继续执掌宗门。"
            player.faction_id = sect.id
            player.faction_join_age = player.age
            player.faction_contribution = 0
            player.allegiance_race = sect.allegiance_race or player.race
            sect.founded_by_player = True
            sect.founder_player_id = game.id
            sect.founded_by_npc = False
            record = self._ensure_intrigue_faction(game, "sect", sect.id)
            record["controller_id"] = "player"
            positions = record.setdefault("positions", {})
            leader = next(iter(self._intrigue_position_specs("sect")), "")
            if leader:
                positions[leader] = "player"
            return "faction_control_restored", f"你重返{sect.name}祖庭，门人奉还印玺，你重新执掌宗门大权。"
        if kind == "grant_monster_imprint":
            imprint_id = str(effect["imprint_id"])
            gained = self.grant_monster_imprint(player, imprint_id)
            name = MONSTER_BLOODLINE_SETTINGS.get("imprints", {}).get(imprint_id, {}).get("name", imprint_id)
            return ("imprint_acquired" if gained else "imprint_known"), (
                f"获得血脉印记【{name}】；它只会开启新的进化可能，不增加突破概率。"
                if gained else f"血脉印记【{name}】早已存在，这次回响没有叠加任何数值。"
            )
        if kind == "remove_flag":
            flag = str(effect["flag"])
            if flag in player.story_flags:
                player.story_flags.remove(flag)
            return None, effect.get("text", "这条因果至此断绝。")
        if kind == "attribute_check":
            if self._is_story_combat_check(str(pending["id"]), effect):
                return self._resolve_story_combat_check(effect, game, pending, rng)
            failures: list[str] = []
            displays: list[str] = []
            for check in effect.get("checks", []):
                stat = check["stat"]
                target = check.get("value")
                if stat == "has_item":
                    passed = has_item(player, str(check["item_id"]), int(check.get("quantity", 1)))
                    displays.append(f"必要信物：{'具备' if passed else '缺失'}")
                else:
                    actual = {
                        "hp": player.hp,
                        "mp": player.mp,
                        "combat_power": self._player_intrinsic_combat_power(player),
                        "hp_ratio": player.hp / max_hp(player),
                        "mp_ratio": player.mp / max_mp(player),
                        "combat_ratio": self._player_intrinsic_combat_power(player) / max(1.0, expected_combat_power(player.realm_index, player.layer)),
                        "karma": effective_karma(player),
                        "sha_qi": player.sha_qi,
                        "heart_demon": player.heart_demon,
                        "fame": player.fame,
                    }.get(stat)
                    if actual is None:
                        raise ValueError(f"未知属性判定：{stat}")
                    passed = OPS[check.get("op", "gte")](actual, target)
                    labels = {
                        "hp": "当前HP", "mp": "当前MP", "combat_power": "当前战斗力",
                        "hp_ratio": "HP比例", "mp_ratio": "MP比例",
                        "combat_ratio": "期望战力倍率", "karma": "有效因果",
                        "sha_qi": "煞气", "heart_demon": "心魔", "fame": "威名",
                    }
                    displays.append(f"{labels[stat]} {actual:.2f}/{float(target):.2f}")
                if not passed:
                    failures.append(stat)
            detail = "，".join(displays)
            if failures:
                reason = effect.get("failure_reason", "未能通过生死判定，身死道消")
                self._die(game, reason, pending["id"])
                return "dead", f"判定失败（{detail}）。{reason}。"
            return "check_success", f"判定通过（{detail}）。{effect.get('success_text', '')}".strip()
        if kind == "trial_step":
            return self._resolve_trial_step(game, str(effect["step"]), rng)
        if kind == "advance_immortal_conversion":
            return self._complete_immortal_conversion_stage(game, int(effect["stage"]))
        if kind == "add_court_merit":
            return None, self._add_court_merit(game, int(value))
        if kind == "relationship_capture_step":
            return self._relationship_capture_step(
                game, pending, str(effect.get("stage", "")), str(effect.get("method", "")), rng,
            )
        if kind == "ghost_reincarnate":
            transition = self._complete_ghost_reincarnation(game, record_history=False)
            return "reincarnated", str(transition["summary"])
        if kind == "queue_event":
            event_id = str(effect["event_id"])
            event = self.events_by_id.get(event_id)
            if event is None:
                raise ValueError(f"后续事件不存在：{event_id}")
            game.pending_event = self._instantiate_event(event, game, rng)
            return None, effect.get("text", "新的险局接踵而至。")
        if kind == "enter_spirit_realm":
            destination = self._ascension_destination(player.path)
            lost_puppets = len(player.puppets)
            player.awaiting_spirit_realm_crossing = False
            joint_crossing = player.joint_spirit_crossing
            companion = player.dao_companion
            crossed_together = bool(
                joint_crossing and companion and companion.get("alive", True)
                and companion.get("id") == joint_crossing.get("id")
            )
            if crossed_together:
                companion["world"] = destination
                npc = self._find_npc(game, str(companion.get("id", "")))
                if npc:
                    npc.world = destination
                    npc.departed_age = npc.age
                    npc.departure_reason = f"与{player.name}共同偷渡{WORLD_SYSTEMS['world_names'][destination]}"
            else:
                player.dao_companion = None
            crossing_friends = list(player.joint_friend_crossing)
            friend_survivors: list[str] = []
            friend_survivor_ids: set[str] = set()
            friend_fallen: list[str] = []
            survival_chance = float(WORLD_SYSTEMS["relationship"]["friend_crossing_survival_chance"])
            for candidate in crossing_friends:
                friend = next((row for row in player.dao_friends if row.get("id") == candidate.get("id")), None)
                npc = self._find_npc(game, str(candidate.get("id", "")))
                if friend and not friend.get("alive", True):
                    continue
                if not friend and (not npc or not npc.alive):
                    continue
                name = str((friend or candidate).get("name", npc.name if npc else "无名队友"))
                if rng.random() < survival_chance:
                    if friend:
                        friend["world"] = destination
                    friend_survivors.append(name)
                    friend_survivor_ids.add(str(candidate.get("id", "")))
                    if npc:
                        npc.world = destination
                        npc.departed_age = npc.age
                        npc.departure_reason = f"与{player.name}共同偷渡{WORLD_SYSTEMS['world_names'][destination]}"
                else:
                    if friend:
                        friend["alive"] = False
                        friend["death_reason"] = "偷渡界壁时迷失于空间风暴"
                    friend_fallen.append(name)
                    if npc:
                        npc.alive = False
                        npc.death_reason = "偷渡界壁时迷失于空间风暴"
            self._prepare_permanent_world_transition(
                game, keep_companion=crossed_together,
                keep_friend_ids=friend_survivor_ids,
            )
            player.world = destination
            player.location_id = self.maps.default_location(destination)
            self._clear_market(game)
            destination_name = WORLD_SYSTEMS["world_names"][destination]
            companion_text = f" {companion['name']}也与你一同落地，道侣关系得以保留。" if crossed_together else ""
            friend_text = ""
            if friend_survivors:
                friend_text += f" 队友{'、'.join(friend_survivors)}侥幸穿过空间风暴，与你在此界重聚。"
            if friend_fallen:
                friend_text += f" 队友{'、'.join(friend_fallen)}未能熬过界壁，自此魂灯熄灭。"
            if crossing_friends:
                game.history.append(HistoryRecord(
                    "SYS_FRIEND_CROSSING",1,player.age,"队友越界",None,"resolved",
                    (f"随行队友中，{'、'.join(friend_survivors) if friend_survivors else '无人'}成功抵达{destination_name}；"
                     f"{'、'.join(friend_fallen) if friend_fallen else '无人'}陨落于空间风暴。"),
                    {"survivors":friend_survivors,"fallen":friend_fallen},
                    ["system","relationship","friend","world_crossing","world:global"],
                ))
            puppet_text = f" 受界壁排斥，{lost_puppets}具傀儡全部遗失。" if lost_puppets else ""
            return "entered_spirit_realm", f"你穿透界壁落入{destination_name}，人界宗门与师徒名册从此再无法感应。{puppet_text}{companion_text}{friend_text}"
        if kind == "technique_level":
            if player.technique is None:
                return "no_technique", "你尚无主修功法，无法参悟。"
            player.technique.level = max(1, player.technique.level + int(value))
            return None, f"功法等级提升至 {player.technique.level}。"
        if kind == "equip_technique":
            template = copy.deepcopy(TECHNIQUE_CATALOG[effect["technique_id"]])
            template.path = player.technique.path if player.technique else player.path
            assign_technique(player, template, effect["slot"])
            slot_name = {
                "main": "主修", "support": "辅修", "combat": "战斗", "body": "炼体",
                "divine_sense": "神识", "transformation": "变身",
            }[effect["slot"]]
            return "technique_equipped", f"你将《{template.name}》设为{slot_name}功法。"
        if kind == "learn_technique":
            template = copy.deepcopy(TECHNIQUE_CATALOG[effect["technique_id"]])
            learned = learn_technique(player, template)
            return ("technique_learned" if learned else "already_known"), (
                f"你悟得《{template.name}》，功法已收入已悟列表，并未改变当前配置。"
                if learned else f"你已经掌握《{template.name}》，此次重温又有所得。"
            )
        if kind == "gain_generated_master":
            if player.master:
                return "already_has_master", "你已有师承，没有再行拜师。"
            relation = self._generated_relationship(player, "master", rng)
            if rng.random() >= float(effect.get("accept_chance", 0.55)):
                return "rejected", f"{relation['name']}认为缘分未至，婉拒了你的拜师请求。"
            player.master = relation
            return "master_accepted", f"{relation['name']}收你为徒，你自此有了师承。"
        if kind == "gain_generated_companion":
            if player.dao_companion and player.dao_companion.get("alive", True):
                return "already_has_companion", "你已有道侣，没有另结新缘。"
            relation = self._generated_relationship(player, "companion", rng)
            player.dao_companion = relation
            return "companion_joined", f"你与{relation['name']}立下同道誓约，自此结为道侣。"
        if kind == "gain_generated_disciple":
            max_disciples = int(WORLD_SYSTEMS["relationship"]["max_disciples"])
            if len(player.disciples) + len(player.disciple_requests) >= max_disciples:
                return "disciple_limit", "你暂时无意再扩大师门。"
            relation = self._generated_relationship(player, "disciple", rng)
            player.disciple_requests.append(relation)
            return "disciple_requested", f"{relation['name']}呈上拜师帖；是否收入门下，仍须由你亲自决定。"
        if kind == "body_training":
            if player.body_technique is None:
                return "no_body_technique", "你没有可用的炼体功法，无法真正踏入炼体之门。"
            player.body_training = min(
                int(WORLD_SYSTEMS["body_cultivation"]["max_layer"]),
                max(0, player.body_training + int(value)),
            )
            player.body_progress = 0.0
            player.awaiting_body_breakthrough = False
            player.hp = min(max_hp(player), player.hp + max_hp(player) * 0.15)
            return None, f"炼体境界提升至 {player.body_training} 层。"
        if kind == "add_body_progress":
            if player.body_technique is None:
                return "no_body_technique", "你没有配置炼体功法，这番苦熬只留下了暗伤。"
            maximum = int(WORLD_SYSTEMS["body_cultivation"]["max_layer"])
            if player.body_training >= maximum:
                return "body_training_max", "炼体已达一百层极限。"
            required = self._body_progress_required(player)
            player.body_progress = min(required, player.body_progress + float(value))
            player.awaiting_body_breakthrough = player.body_progress >= required
            return None, f"炼体积累 +{float(value):g}（{player.body_progress:.1f}/{required:.1f}）。"
        if kind == "extend_lifespan":
            if player.realm_index != 0:
                return None, "你已踏入仙途，凡俗炼体不再改变寿元。"
            amount = int(value)
            body_age = current_body_age(player)
            old = int(player.lifespan or body_age)
            player.lifespan = min(300, max(old, body_age + 1) + amount)
            return None, f"炼体延寿，寿元上限由 {old} 提升至 {player.lifespan} 岁。"
        if kind == "acquire_root":
            if player.spirit_root != "none":
                return None, "你的灵根已经完整。"
            affinity = effect["affinity"]
            player.spirit_root = f"acquired_{affinity}"
            player.acquired_root = True
            return "root_repaired", f"残缺经脉中生出一缕{TECHNIQUE_ELEMENT_NAMES[affinity]}灵性，你获得了对应的后天灵根。"
        if kind == "add_random_jinque":
            affinity = rng.choice(["wind", "thunder", "yin", "yang", "fire", "water", "wood", "metal", "earth"])
            item_id = f"jinque_{affinity}"
            add_item(player, item_id)
            return "jinque_found", f"你获得了《{ITEM_CATALOG[item_id].name}》。"
        if kind == "set_mortal_aspiration":
            player.mortal_aspiration = str(effect["aspiration"])
            names = {"family": "娶妻荫子", "scholar": "考试当官", "military": "沙场效忠", "jianghu": "江湖驰骋"}
            return "aspiration_set", f"你立志走上“{names[player.mortal_aspiration]}”之路。"
        if kind == "mortal_progress":
            field = effect["field"]
            if field not in {"children", "official_rank", "military_merit", "jianghu_reputation"}:
                raise ValueError("未知凡人进度")
            setattr(player, field, max(0, int(getattr(player, field)) + int(value)))
            return None, effect.get("text", "凡尘经历又添一笔。")
        if kind == "set_spouse":
            player.spouse = bool(effect.get("value", True))
            return None, "你与良人结为夫妻。"
        if kind == "join_faction":
            faction_id = str(effect["faction_id"])
            if faction_id not in FACTION_DEFINITIONS:
                raise ValueError("未知宗门")
            if player.faction_id:
                return None, f"你已是{FACTION_DEFINITIONS[player.faction_id]['name']}门人。"
            if FACTION_DEFINITIONS[faction_id].get("world", "human") != player.world:
                return "wrong_world", "这座宗门并不位于你当前所在的界面。"
            player.faction_id = faction_id
            player.allegiance_race = FACTION_DEFINITIONS[faction_id].get("allegiance_race")
            player.faction_join_age = player.age
            player.faction_contribution = 0
            return "faction_joined", f"你正式拜入{FACTION_DEFINITIONS[faction_id]['name']}，自此共享宗门福祸。"
        if kind == "add_faction_contribution":
            if not player.faction_id:
                return None, "你尚无宗门身份。"
            player.faction_contribution = max(0, player.faction_contribution + int(value))
            sign = "+" if value >= 0 else ""
            return None, f"宗门贡献 {sign}{int(value)}。"
        if kind == "sect_defense":
            runtime = pending.get("runtime", {})
            sect = game.sects.get(str(runtime.get("sect_id", player.faction_id or "")))
            if not sect or sect.extinct or player.faction_id != sect.id:
                return "sect_absent", "山门已经不复存在。"
            mode = str(effect.get("mode", "fight"))
            success = False
            detail = ""
            if mode == "fight":
                required = float(runtime.get("required_power", 1))
                combat_result, combat_summary = self._combat(game, {
                    "target_name": "来犯山门的敌修", "target_power": required,
                    "target_realm_index": player.realm_index, "target_layer": player.layer,
                    "combat_type": "cultivator", "action": "repel",
                    "enemy_objective": "break_formation",
                }, False, rng)
                success = combat_result == "victory"
                detail = combat_summary
            elif mode == "formation":
                guard_array = self._sect_guard_array(game, sect.id)
                required = float(runtime.get("required_power", 1))
                if guard_array:
                    profile = self._ground_profile(player, guard_array)
                    defense_power = self._sect_guard_power(game, sect.id)
                    variance = rng.uniform(
                        float(self._formation_rules().get("sect_defense_variance_min", 0.94)),
                        float(self._formation_rules().get("sect_defense_variance_max", 1.06)),
                    )
                    effective_power = defense_power * variance
                    success = effective_power >= required
                    wear = float(self._formation_rules().get(
                        "sect_defense_success_wear" if success else "sect_defense_failure_wear",
                        7.0 if success else 15.0,
                    ))
                    # A badly outmatched assault strains the anchor further,
                    # but one event can never delete more than 25 durability.
                    wear *= min(1.65, max(0.75, required / max(1.0, defense_power)))
                    guard_array["durability"] = round(max(
                        0.0, float(guard_array.get("durability", 0.0)) - min(25.0, wear),
                    ), 4)
                    guard_array["battles"] = int(guard_array.get("battles", 0)) + 1
                    detail = (
                        f"真实护山阵“{guard_array['name']}”以 {effective_power:.0f} 阵力对抗"
                        f" {required:.0f} 来犯战力，永久完整度降至 {guard_array['durability']:.1f}%"
                    )
                    if success:
                        gain = min(
                            float(self._formation_rules().get("ground_experience_cap", 55.0)),
                            18.0 + profile.get("occupied_count", 0) * 2.5 + min(12.0, required / max(1.0, defense_power) * 8.0),
                        )
                        self._grant_art_experience(player, "formation", gain)
                else:
                    success = False
                    detail = "宗门没有以真实阵材镇下护山阵；旧阵盘不能再直接替代整座大阵"
            elif mode == "appease":
                cost = 80 if player.world == "human" else 800
                success = remove_item(player, "spirit_stone", cost)
                detail = f"支付灵石 {cost}" if success else f"灵石不足 {cost}"
            elif mode == "abandon":
                self._dissolve_player_sect(game, sect, "你主动撤下山门匾额，门人各寻出路")
                return "sect_dissolved", "你不愿门人为一座虚名送死，主动解散了宗门。"
            if success:
                player.faction_contribution += 5
                return "defended", f"{detail}；你成功护住山门，既有失败次数仍为 {sect.pressure}/3，宗门贡献 +5。"
            sect.pressure += 1
            if sect.pressure >= int(WORLD_SYSTEMS["player_faction"]["pressure_limit"]):
                self._dissolve_player_sect(game, sect, "连续三次未能抵御外部打压")
                return "sect_dissolved", f"{detail}；这是第三次护山失败，门人信心尽失，宗门就此解散。"
            return "defense_failed", f"{detail}；护山失败累计 {sect.pressure}/3，宗门仍在，但下一次来犯会更加凶险。"
        if kind == "faction_war":
            if not player.faction_id:
                return None, "战帖与你无关。"
            veteran = player.realm_index > 4 or (player.realm_index == 4 and player.layer > 3)
            target_power = expected_combat_power(player.realm_index, max(1, player.layer))
            target_power *= rng.uniform(0.68, 0.88) if veteran else rng.uniform(0.95, 1.25)
            formation_duty = int(effect.get("contribution", 12)) <= 9
            combat_result, summary = self._combat(game, {
                "target_name": "敌宗会战修士",
                "target_power": target_power,
                "target_realm_index": player.realm_index,
                "target_layer": max(1, player.layer),
                "combat_type": "cultivator",
                "objective": "repel",
                "enemy_objective": "repel",
                "max_rounds": 5,
                "non_story_combat": True,
                "artificial_conditions": ["大阵"] if formation_duty else [],
            }, True, rng)
            if combat_result == "dead":
                return "dead", summary
            if combat_result == "defeat":
                player.faction_contribution += max(1, int(effect.get("contribution", 8)) // 2)
                return "survived", summary + " 你虽未夺得阵地，仍因完成撤离与接应获得部分宗门贡献。"
            player.faction_contribution += int(effect.get("contribution", 12))
            return "victory", summary + " 你完成会战目标，宗门贡献有所增加。"
        if kind == "combat":
            target = pending["runtime"]
            event_tags = self.events_by_id.get(str(pending.get("id", "")), {}).get("tags", [])
            target["non_story_combat"] = "story_chain" not in event_tags
            return self._combat(game, target, bool(effect.get("lethal")), rng)
        raise ValueError(f"未知效果类型：{kind}")

    def _player_combat_units(self, game: GameState, target: dict[str, Any] | None = None) -> list[BattleUnit]:
        """Build independent units for player combat; each brings full power."""
        player = game.player
        units = [BattleUnit(
            "player", player.name, "player", max(1.0, combat_power(player)),
            player.realm_index, player.path,
        )]
        for puppet in player.puppets:
            kind = str(puppet.get("type", "mechanical"))
            if not puppet.get("alive", True) or kind not in {"mechanical", "corpse"}:
                continue
            field = "durability" if kind == "mechanical" else "corpse_integrity"
            integrity = max(0.0, min(1.0, float(puppet.get(field, 100.0)) / 100.0))
            units.append(BattleUnit(
                str(puppet.get("id")), str(puppet.get("name", "无名傀儡")), kind,
                max(0.0, float(puppet.get("combat_power", 0))),
                int(puppet.get("realm_index", player.realm_index)),
                "ghost" if kind == "corpse" else "dao", integrity, field,
            ))

        for relation in self._public_party(game):
            power = max(0.0, float(relation.get("combat_power", 0)))
            units.append(BattleUnit(
                str(relation.get("id", "companion")), str(relation.get("name", "同行者")),
                "companion", power, int(relation.get("realm_index", player.realm_index)),
                str(relation.get("path", "dao")),
            ))
        for puppet in player.puppets:
            if not puppet.get("alive", True) or puppet.get("type") != "living":
                continue
            effective = max(0.0, float(puppet.get("combat_power", 0)))
            control = max(0.2, min(1.0, float(puppet.get("control", 100)) / 100.0))
            units.append(BattleUnit(
                str(puppet.get("id")), str(puppet.get("name", "无名活傀")), "living",
                effective, int(puppet.get("realm_index", player.realm_index)),
                str(puppet.get("path", "demonic")), control, "control",
            ))
        target = target or {}
        target_power = max(1.0, float(target.get("target_power", 1.0)))
        selected_choice = str(target.get("story_choice_id", ""))
        for index, ally in enumerate(target.get("player_allies", [])):
            if selected_choice in ally.get("exclude_choices", []):
                continue
            effective_power = target_power * float(ally["power_ratio"])
            ally_realm = max(0, min(len(REALMS) - 1, player.realm_index + int(ally.get("realm_offset", 0))))
            units.append(BattleUnit(
                f"story-ally-{index}", str(ally["name"]), "story_ally",
                effective_power, ally_realm, str(ally.get("path", "dao")),
                full_power=self._story_unit_full_power(ally, ally_realm, effective_power),
            ))
        return units

    def _combat_battlefield_tags(self, game: GameState, target: dict[str, Any]) -> list[str]:
        explicit = list(target.get("battlefield_tags", target.get("combat_tags", [])))
        location_id = self.maps.normalize_location(game.player.world, game.player.location_id)
        location = self.maps.location(game.player.world, location_id)
        natural = str(target.get("natural_terrain") or location["combat_terrain"])
        artificial = [*target.get("artificial_conditions", []), *explicit]
        return [natural, *dict.fromkeys(str(tag) for tag in artificial)]

    @staticmethod
    def _apply_support_damage(player: Player, updates: list[dict[str, Any]]) -> None:
        by_id = {str(entry.get("id")): entry for entry in player.puppets}
        for update in updates:
            puppet = by_id.get(str(update.get("id")))
            field = update.get("field")
            if not puppet or not field:
                continue
            puppet[str(field)] = round(float(update.get("after", 0)), 1)
            if update.get("destroyed"):
                puppet["alive"] = False

    def _record_player_combat(
        self, game: GameState, target: dict[str, Any], resolution: Any, result: str,
    ) -> None:
        report = resolution.to_dict()
        report.update({
            "title": f"与{target.get('target_name', '未知对手')}的战报",
            "target_name": target.get("target_name", "未知对手"),
            "result": result,
            "stat_comparison": stat_comparison(resolution),
            "age": game.player.age,
        })
        game.last_combat_report = report
        longest_enemy_streak = 0
        current_enemy_streak = 0
        for combat_round in report.get("rounds", []):
            if combat_round.get("initiative") == "enemy":
                current_enemy_streak += 1
                longest_enemy_streak = max(longest_enemy_streak, current_enemy_streak)
            else:
                current_enemy_streak = 0
        if longest_enemy_streak:
            game.player.milestones["enemy_initiative_streak"] = max(
                int(game.player.milestones.get("enemy_initiative_streak", 0)),
                longest_enemy_streak,
            )

    @staticmethod
    def _combat_report_lead(resolution: Any, hp_loss: float, mp_loss: float) -> str:
        turns = "；".join(resolution.key_events[:3])
        artificial = (
            f"，人工条件：{'、'.join(resolution.artificial_conditions)}"
            if resolution.artificial_conditions else "，无人工战场条件"
        )
        terrain = f"，自然场地：{resolution.natural_terrain}{artificial}"
        return (
            f"【{resolution.result_grade}·{resolution.mode}】战前判断为{resolution.assessment}{terrain}。"
            f"自动交战 {len(resolution.rounds)} 轮，HP -{hp_loss:.0f}、MP -{mp_loss:.0f}。"
            f"关键转折：{turns} "
        )

    def _combat(self, game: GameState, target: dict[str, Any], lethal: bool, rng: random.Random) -> tuple[str, str]:
        """Resolve player-involved combat through the detailed automatic system.

        NPC-only field battles deliberately remain in ``WarSystemMixin`` and use
        their legacy aggregate-power logic.
        """
        player = game.player
        ensure_formation_state(player)
        portable_formation = active_formation_profile(player)
        ground_array = None if portable_formation.get("active") else self._local_ground_formation(game)
        if ground_array:
            ground_profile = self._ground_profile(player, ground_array)
            target["allied_formation_profile"] = ground_profile
            target["formation_initial_integrity"] = float(ground_array.get("durability", 0.0)) / 100.0
            target["ground_formation_id"] = str(ground_array["id"])
        ground_array_id = str(ground_array.get("id", "")) if ground_array else ""
        npc_ids = [str(target.get("npc_id", "")), *(
            str(member.get("npc_id", "")) for member in target.get("members", [])
        )]
        npc_ids = [npc_id for npc_id in dict.fromkeys(npc_ids) if npc_id in game.npc_formations]
        enemy_formation_id = max(
            npc_ids, key=lambda npc_id: self._npc_formation_power_multiplier(game, npc_id), default="",
        )
        if enemy_formation_id:
            enemy_entry = game.npc_formations[enemy_formation_id]
            enemy_profile = self._npc_formation_profile(
                game, enemy_formation_id, detailed_spectrum=True,
            )
            if enemy_profile.get("active"):
                target["enemy_formation_profile"] = enemy_profile
                target["enemy_formation_initial_integrity"] = float(enemy_entry.get("durability", 0.0)) / 100.0
                target["enemy_formation_npc_id"] = enemy_formation_id
        target["natal_artifact_effects"] = [
            *self._natal_artifact_combat_effects(game), *crafted_combat_effects(game.player),
        ]
        if player.world == "celestial":
            if self._court_law_active(game, "martial_gods"):
                target["global_damage_multiplier"] = 1.10
            wanted_ids = set(game.heavenly_court.get("wanted_ids", []))
            target_ids = {str(target.get("npc_id", "")), *(
                str(member.get("npc_id", "")) for member in target.get("members", [])
            )}
            if wanted_ids.intersection(target_ids):
                target["player_damage_multiplier"] = 1.10
            if "player" in wanted_ids:
                target["enemy_damage_multiplier"] = 1.10
            if self._court_law_active(game, "immortal_slaughter"):
                player.karma -= 10
            if (
                self._court_law_active(game, "universal_protection")
                and target.get("combat_type") == "cultivator"
                and rng.random() < (0.80 if lethal else 0.25)
                and "player" not in wanted_ids
            ):
                game.heavenly_court["wanted_ids"].append("player")
                player.milestones["became_wanted_target"] = 1
        equipped = [entry for entry in [player.technique, *(player.combat_techniques or [])] if entry]
        if any(not can_player_practice_technique(player, entry.element) for entry in equipped):
            return "technique_blocked", "灵根属性与五行功法不合，无法运转功法迎战。"

        hp_max = max_hp(player)
        mp_max = max_mp(player)
        player_units = self._player_combat_units(game, target)
        own_power = max(1.0, sum(unit.power * unit.integrity for unit in player_units))
        target_power = max(1.0, float(target["target_power"]))
        ratio = own_power / target_power
        resolution = PlayerCombatSystem.resolve(
            player, player_units, target, lethal, rng,
            current_hp_ratio=player.hp / max(1.0, hp_max),
            current_mp_ratio=player.mp / max(1.0, mp_max),
            battlefield_tags=self._combat_battlefield_tags(game, target),
        )
        used_formation = (
            target.get("allied_formation_profile", {})
            if ground_array else portable_formation
        )
        formation_gain = formation_battle_experience_gain(used_formation, len(resolution.rounds), ratio)
        if formation_gain > 0:
            self._grant_art_experience(player, "formation", formation_gain)
            # Formation experience changes long-range attenuation. Rebuild the
            # cached matrix on the next read, never in the middle of this fight.
            player.formation_profile_cache = {}
            resolution.formation_experience_gain = formation_gain
        if ground_array_id and resolution.formation_integrity_end is not None:
            # Combat profile reads normalize old formation state and may
            # replace list dictionaries. Reacquire the persistent object by
            # identity before writing permanent wear.
            ground_array = next(
                (row for row in player.formation_ground_arrays if row.get("id") == ground_array_id), None,
            )
        if ground_array and resolution.formation_integrity_end is not None:
            before = max(0.0, min(100.0, float(ground_array.get("durability", 0.0))))
            simulated = max(0.0, min(100.0, float(resolution.formation_integrity_end) * 100.0))
            raw_wear = max(0.0, before - simulated)
            settings = self._formation_rules()
            wear = min(float(settings.get("ground_battle_max_wear", 26.0)), raw_wear)
            if before > 0:
                wear = max(float(settings.get("ground_battle_min_wear", 1.0)), wear)
            ground_array["durability"] = round(max(0.0, before - wear), 4)
            ground_array["battles"] = int(ground_array.get("battles", 0)) + 1
        if enemy_formation_id and resolution.enemy_formation_integrity_end is not None:
            enemy_entry = game.npc_formations.get(enemy_formation_id)
            if enemy_entry:
                before = max(0.0, min(100.0, float(enemy_entry.get("durability", 0.0))))
                simulated = max(0.0, min(100.0, float(resolution.enemy_formation_integrity_end) * 100.0))
                raw_wear = max(0.0, before - simulated)
                settings = self._formation_rules()
                wear = min(float(settings.get("ground_battle_max_wear", 26.0)), raw_wear)
                if before > 0:
                    wear = max(float(settings.get("ground_battle_min_wear", 1.0)), wear)
                enemy_entry["durability"] = round(max(0.0, before - wear), 4)
                enemy_entry["battles"] = int(enemy_entry.get("battles", 0)) + 1
        loss_scale = max(0.0, float(target.get("loss_scale", 1.0)))
        hp_loss = hp_max * resolution.hp_loss_ratio * float(target.get("hp_loss_scale", loss_scale))
        mp_loss = mp_max * resolution.mp_loss_ratio * float(target.get("mp_loss_scale", loss_scale))
        player.hp = max(0.0 if lethal else 1.0, player.hp - hp_loss)
        if resolution.retreat_impossible and not resolution.death_prevented:
            # Ordinary battle injury is capped, but an overwhelmingly stronger
            # lethal pursuer leaves no valid route for that generic retreat.
            player.hp = 0.0
        if resolution.death_prevented:
            player.hp = max(1.0, player.hp)
        player.mp = max(0.0, player.mp - mp_loss)
        self._apply_support_damage(player, resolution.support_updates)
        lead = self._combat_report_lead(resolution, hp_loss, mp_loss)

        if target.get("combat_type") == "beast":
            threshold = float(target.get("success_threshold", 1.2))
            if resolution.outcome == "victory":
                fame_config = WORLD_SYSTEMS["fame"]
                fame_gain = (
                    float(fame_config["kill_gain_base"])
                    + int(target.get("target_realm_index", 0)) * float(fame_config["kill_realm_scale"])
                )
                player.fame += fame_gain
                demonic_gain = self._grant_demonic_kill_opportunity(
                    player, int(target.get("target_realm_index", 0)),
                )
                result = "killed"
                self._record_player_combat(game, target, resolution, result)
                return result, lead + (
                    f"你在复杂交锋中建立压制并击杀了{target['target_name']}；狩猎准备要求为对手战力的 {threshold:.1f} 倍。"
                    f" 威名 +{fame_gain:.0f}。"
                    + (f" 杀戮炼化机缘 +{demonic_gain:.0f}。" if demonic_gain else "")
                )
            if resolution.retreat_impossible and resolution.death_prevented:
                result = "defeat_survived"
                self._record_player_combat(game, target, resolution, result)
                return result, lead + (
                    f"{target['target_name']}以三倍以上战力封死退路，逃脱预案失败；"
                    "涅槃类能力替你承受了必死一击，但狩猎目标未能完成。"
                )
            if player.hp <= 0:
                self._die(
                    game, f"猎妖时不敌{target['target_name']}，身死道消", "SYS_BEAST_HUNT",
                    offer_captive_possession=bool(target.get("non_story_combat")),
                )
                result = "dead"
                self._record_player_combat(game, target, resolution, result)
                return result, lead + f"你未能完成对妖兽的压制，反被{target['target_name']}所杀。"
            result = "defeat"
            self._record_player_combat(game, target, resolution, result)
            return result, lead + f"你未达到狩猎所需的 {threshold:.1f} 倍准备优势，预案自动护送你负伤退走。"

        if resolution.outcome != "victory":
            if not lethal:
                result = "defeat"
                self._record_player_combat(game, target, resolution, result)
                return result, lead + f"你在切磋中败给了{target['target_name']}，预案及时收手，无人伤及性命。"
            if resolution.retreat_impossible and resolution.death_prevented:
                result = "defeat_survived"
                self._record_player_combat(game, target, resolution, result)
                return result, lead + (
                    f"{target['target_name']}以三倍以上战力封死所有退路，逃脱预案失败；"
                    "涅槃类能力替你承受了必死一击，才没有当场陨落。"
                )
            if player.hp <= 0:
                can_take_captive = bool(
                    target.get("non_story_combat")
                    and self._post_battle_possession_candidates(game)
                )
                captured = False if can_take_captive else self._capture_defeated_ghost(game, target, rng)
                if not captured:
                    self._die(
                        game, f"不敌{target['target_name']}，身死道消", "SYS_COMBAT",
                        offer_captive_possession=can_take_captive,
                    )
                result = "controlled" if captured else "dead"
                self._record_player_combat(game, target, resolution, result)
                return result, lead + (
                    f"你败给{target['target_name']}，魂体被拘入禁制。"
                    if captured else (
                        f"敌方战力达到你方三倍以上，保命预案必定失败；你败给{target['target_name']}并身死。"
                        if resolution.retreat_impossible
                        else f"保命预案未能撕开退路，你败给{target['target_name']}并身死。"
                    )
                )
            result = "defeat"
            self._record_player_combat(game, target, resolution, result)
            return result, lead + f"你败给了{target['target_name']}，预案保存主要力量后自动脱离。"

        if target.get("capture"):
            if not resolution.capture_ready:
                result = "victory_escape"
                self._record_player_combat(game, target, resolution, result)
                return result, lead + "你虽取得战场控制权，但神识、身法与封锁态势不足，对方仍然遁走。"
            result, capture_summary = self._capture_cultivator(game, target, own_power, rng)
            self._record_player_combat(game, target, resolution, result)
            return result, lead + capture_summary
        if not lethal or resolution.objective == "repel":
            result = "victory"
            self._record_player_combat(game, target, resolution, result)
            return result, lead + f"你达成击退目标，{target['target_name']}失去战意后退出交锋。"

        members = target.get("members") or [{
            "name": target["target_name"], "power": target_power,
            "realm_index": target["target_realm_index"], "npc_id": target.get("npc_id"),
            "faction_id": target.get("faction_id"), "race": target.get("race", "human"),
            "treasure_item_id": target.get("treasure_item_id"),
        }]
        victim = min(members, key=lambda member: float(member["power"]))
        victim_ratio = own_power / max(1.0, float(victim["power"]))
        pursuit_chance = min(0.94, 0.52 + max(0.0, victim_ratio - 1.0) * 0.11)
        if resolution.kill_ready and rng.uniform(0.0, 1.0) < pursuit_chance:
            target["killed_member"] = victim
            fame_before = player.fame
            treasure_id = victim.get("treasure_item_id")
            self._apply_cultivator_kill(game, victim, rng)
            demonic_gain = self._grant_demonic_kill_opportunity(player, int(victim["realm_index"]))
            spoils = (
                f" 你夺得{ITEM_CATALOG[treasure_id].name}。"
                if treasure_id in ITEM_CATALOG and victim.get("npc_id") else ""
            )
            fame_text = f" 威名 +{player.fame - fame_before:.0f}。"
            victim_path = str(victim.get("path", "dao"))
            if player.path == "monster" and victim_path != "monster":
                sha_text = ""
                if victim_path == "dao":
                    fame_rules = WORLD_SYSTEMS["fame"]
                    sha_gain = round(
                        float(fame_rules["monster_dao_kill_sha_base"])
                        + int(victim["realm_index"]) * float(fame_rules["monster_dao_kill_sha_realm_scale"])
                    )
                    player.sha_qi += sha_gain
                    sha_text = f" 煞气 +{sha_gain}。"
                result = "killed"
                self._record_player_combat(game, target, resolution, result)
                return (
                    result,
                    lead + f"你在追击阶段击杀了{victim['name']}；妖修猎杀异道不沾因果。"
                    + sha_text + fame_text + spoils
                    + (f" 杀戮炼化机缘 +{demonic_gain:.0f}。" if demonic_gain else ""),
                )
            if target.get("kill_karma", True):
                if victim.get("notorious"):
                    reduction = min(player.karma, max(35.0, float(victim.get("notoriety", 0)) * 0.45))
                    player.karma = max(0.0, player.karma - reduction)
                    result = "killed"
                    self._record_player_combat(game, target, resolution, result)
                    return result, lead + f"你在追击阶段诛杀恶贯满盈的{victim['name']}，因果 -{reduction:.0f}。{fame_text}{spoils}" + (f" 杀戮炼化机缘 +{demonic_gain:.0f}。" if demonic_gain else "")
                karma_gain = round(18 + int(victim["realm_index"]) * 7)
                alliance = self._race_alliance(game, player.world, self._player_allegiance_race(player), str(victim.get("race", "human")))
                if alliance:
                    karma_gain = round(karma_gain * float(alliance["kill_karma_multiplier"]) + float(alliance["kill_karma_flat"]))
                player.karma += karma_gain
                warning = f" 你违背了{alliance['name']}。" if alliance else ""
                result = "killed"
                self._record_player_combat(game, target, resolution, result)
                return result, lead + f"你在追击阶段击杀了{victim['name']}，因果 +{karma_gain}。{warning}{fame_text}{spoils}" + (f" 杀戮炼化机缘 +{demonic_gain:.0f}。" if demonic_gain else "")
            result = "killed"
            self._record_player_combat(game, target, resolution, result)
            return result, lead + f"你在追击阶段击杀了{victim['name']}。{fame_text}{spoils}" + (f" 杀戮炼化机缘 +{demonic_gain:.0f}。" if demonic_gain else "")
        result = "victory_escape"
        self._record_player_combat(game, target, resolution, result)
        return result, lead + f"你已击溃对方，但{victim['name']}仍在追击阶段摆脱封锁。"

    def _apply_cultivator_kill(self, game: GameState, victim: dict[str, Any], rng: random.Random) -> None:
        player = game.player
        config = WORLD_SYSTEMS["faction_conflict"]
        fame_config = WORLD_SYSTEMS["fame"]
        player.fame += float(fame_config["kill_gain_base"]) + int(victim["realm_index"]) * float(fame_config["kill_realm_scale"])
        if victim.get("notorious"):
            player.fame += max(40.0, float(victim.get("notoriety", 0)) * 0.55)
        npc_id = victim.get("npc_id")
        npc = self._find_npc(game, str(npc_id)) if npc_id else None
        if npc:
            npc.alive = False
            npc.death_reason = f"被{player.name}击杀夺宝"
            player.party = [entry for entry in player.party if entry.get("id") != npc.id]
            if player.dao_companion and player.dao_companion.get("id") == npc.id:
                player.dao_companion["alive"] = False
                player.dao_companion["death_reason"] = npc.death_reason
            treasure_id = npc.treasure_item_id
            if treasure_id in ITEM_CATALOG:
                add_item(player, treasure_id)
                npc.treasure_item_id = None
                npc.treasure_looted = True
        elif npc_id:
            cached = next((row for row in game.encounter_npc_cache if row.get("id") == npc_id), None)
            if cached:
                treasure_id = cached.get("npc", {}).get("treasure_item_id")
                if treasure_id in ITEM_CATALOG:
                    add_item(player, str(treasure_id))
                game.encounter_npc_cache = [row for row in game.encounter_npc_cache if row.get("id") != npc_id]
        faction_id = victim.get("faction_id")
        race = str(victim.get("race", "human"))
        wartime_opponent = self._is_wartime_opponent(game, str(faction_id) if faction_id else None, race)
        if faction_id:
            key = self._hostility_key("sect", str(faction_id))
            if faction_id == player.faction_id:
                self._handle_same_sect_kill(game, str(faction_id), str(npc_id) if npc_id else None)
            elif not wartime_opponent and self._kill_generates_hostility(game, "sect", str(faction_id), int(victim["realm_index"])):
                player.hostility[key] = player.hostility.get(key, 0) + float(config["kill_hostility_gain"])
            sect = game.sects.get(str(faction_id))
            if sect:
                self._check_sect_extinction(game, sect)
        if (
            self._world_supports(player.world, "races") and race != self._player_allegiance_race(player)
            and not wartime_opponent
            and self._kill_generates_hostility(game, "race", race, int(victim["realm_index"]))
        ):
            key = self._hostility_key("race", race)
            player.hostility[key] = player.hostility.get(key, 0) + float(config["kill_hostility_gain"])

    def _kill_generates_hostility(self, game: GameState, kind: str, target_id: str, victim_realm: int) -> bool:
        """Routine wartime and low-rank deaths do not mobilise an entire power."""
        player = game.player
        minimum = int(WORLD_SYSTEMS["faction_conflict"].get("kill_hostility_min_realm", {}).get(player.world, 0))
        if victim_realm < minimum:
            return False
        if kind == "race":
            relation = game.race_relations.get(race_pair(self._player_allegiance_race(player), target_id), {})
            return relation.get("status") != "war"
        if kind == "sect" and player.faction_id and target_id in game.sects:
            relation = game.sect_relations.get(race_pair(player.faction_id, target_id), {})
            return relation.get("status") != "war"
        return True

    def _is_wartime_opponent(self, game: GameState, faction_id: str | None, race_id: str) -> bool:
        player = game.player
        player_race = self._player_allegiance_race(player)
        for war in game.wars:
            if war.get("status") not in {"active", "peace_ready"}:
                continue
            self._ensure_war_shape(game, war)
            own_id = player.faction_id if war.get("kind") == "sect" else player_race
            target_id = faction_id if war.get("kind") == "sect" else race_id
            own_side = self._participant_side(war, own_id)
            target_side = self._participant_side(war, target_id)
            if own_side and target_side and own_side != target_side:
                return True
        if race_id != player_race and game.race_relations.get(race_pair(player_race, race_id), {}).get("status") == "war":
            return True
        return bool(
            faction_id and player.faction_id and faction_id != player.faction_id
            and game.sect_relations.get(race_pair(player.faction_id, faction_id), {}).get("status") == "war"
        )

    def _handle_same_sect_kill(self, game: GameState, faction_id: str, current_victim_id: str | None = None) -> None:
        player = game.player
        config = WORLD_SYSTEMS["faction_conflict"]
        control_realm = int(config["control_realm"].get(player.world, 4))
        living = [
            npc for npc in game.sects[faction_id].npcs
            if npc.world == player.world and (npc.alive or npc.id == current_victim_id)
        ]
        is_first = not living or (player.realm_index, player.layer) >= max((npc.realm_index, npc.layer) for npc in living)
        warning_key = f"same_sect_kill:{faction_id}"
        hostility_key = self._hostility_key("sect", faction_id)
        if player.realm_index < control_realm:
            player.faction_id = None
            player.hostility[hostility_key] = max(60.0, player.hostility.get(hostility_key, 0) + 45)
            summary = "你残杀同门，被当场逐出宗门并列入全宗通缉。"
            result = "expelled"
        elif not is_first and warning_key not in player.faction_warnings:
            player.faction_warnings.append(warning_key)
            summary = "宗门顺位第一的强者亲自降下法旨，警告你下不为例。"
            result = "warned"
            event = self.events_by_id.get("EVT_SECT_FIRST_WARNING_001")
            if event:
                game.pending_event = self._instantiate_event(event, game, random.Random(f"warning:{game.seed}:{player.age}"))
        elif not is_first:
            player.faction_id = None
            player.hostility[hostility_key] = max(90.0, player.hostility.get(hostility_key, 0) + 55)
            summary = "你无视顺位第一的警告再杀同门，宗门上下奉诛杀令追索你的性命。"
            result = "hunted"
        else:
            summary = "你位列宗门顺位第一，无人敢当面追究这次同门血案。"
            result = "suppressed"
        game.history.append(HistoryRecord(
            "SYS_SAME_SECT_KILL", 1, player.age, "同门血案", faction_id, result, summary,
            {"hostility": player.hostility.get(hostility_key, 0)}, ["system", "faction", "combat", "wanted"],
        ))

    @staticmethod
    def _race_alliance(game: GameState, world: str, first: str, second: str) -> dict[str, Any] | None:
        if first == second:
            return None
        dynamic = game.race_relations.get(race_pair(first, second))
        if "races" in WORLD_SYSTEMS.get("world_profiles", {}).get(world, {}).get("supports", []) and dynamic is not None:
            if dynamic.get("status") in {"alliance", "vassal"}:
                return {
                    "name": dynamic.get("name") or f"{RACE_DEFINITIONS[first]['name']}与{RACE_DEFINITIONS[second]['name']}盟约",
                    "kill_karma_multiplier": 3.0, "kill_karma_flat": 60,
                }
            return None
        for alliance in RACE_SYSTEMS.get("alliances", []):
            if alliance.get("world") == world and {first, second} <= set(alliance.get("members", [])):
                return alliance
        return None

    def _resolve_breakthroughs(self, game: GameState, rng: random.Random) -> None:
        player = game.player
        if player.sealed_cultivation:
            player.opportunity = min(player.opportunity, opportunity_required(player))
            return
        if player.spirit_root == "none":
            player.opportunity = 0
            return
        safety = 0
        while player.alive and player.opportunity >= opportunity_required(player) and safety < 32:
            safety += 1
            required = opportunity_required(player)
            # 仙境没有层级与前中后期；后续升级规则尚未开放，不能误走旧突破链。
            if player.realm_index >= 9:
                player.opportunity = min(player.opportunity, required)
                player.awaiting_major_breakthrough = False
                player.awaiting_minor_breakthrough = False
                return
            if player.world == "spirit" and player.realm_index == 8 and player.layer >= REALMS[8].layers:
                player.awaiting_ascension = True
                player.awaiting_major_breakthrough = False
                player.opportunity = min(player.opportunity, required)
                if not any(entry.event_id == "SYS_CELESTIAL_ASCENSION_READY" for entry in game.history):
                    game.history.append(HistoryRecord(
                        "SYS_CELESTIAL_ASCENSION_READY", 1, player.age, "仙门可叩", None, "ready",
                        "大乘九层道果与机缘均已圆满，可以发动专属的九重渡劫飞升。",
                        {"awaiting_ascension":True}, ["system", "ascension", "celestial", "milestone"],
                    ))
                return
            if (
                player.path == "demonic" and player.world == "true_demon"
                and player.realm_index == 8 and player.layer >= REALMS[8].layers
            ):
                player.awaiting_ascension = True
                player.awaiting_major_breakthrough = False
                player.opportunity = min(player.opportunity, required)
                if not any(entry.event_id == "SYS_ASURA_ASCENSION_READY" for entry in game.history):
                    game.history.append(HistoryRecord(
                        "SYS_ASURA_ASCENSION_READY", 1, player.age, "修罗天关可叩", None, "ready",
                        "魔尊九层道果与机缘均已圆满，可以发动九重修罗天魔劫。",
                        {"awaiting_ascension":True}, ["system", "ascension", "asura", "demonic", "milestone"],
                    ))
                return
            if (
                player.path == "demonic" and player.world == "human"
                and player.realm_index == 5 and player.layer >= 3
            ):
                player.awaiting_ascension = True
                player.opportunity = min(player.opportunity, required)
                if not any(entry.event_id == "SYS_HUMAN_DEMONIC_LIMIT" for entry in game.history):
                    game.history.append(HistoryRecord(
                        "SYS_HUMAN_DEMONIC_LIMIT", 1, player.age, "魔界飞升瓶颈", None, "blocked",
                        "你已在人界修至化魔初期；下一步须飞升魔界。",
                        {"awaiting_ascension": True}, ["system", "realm_limit", "demonic", "milestone"],
                    ))
                return
            if (
                player.path == "demonic" and player.world == "demon"
                and player.realm_index == 5 and player.layer >= REALMS[5].layers
            ):
                player.awaiting_ascension = True
                player.opportunity = min(player.opportunity, required)
                if not any(entry.event_id == "SYS_DEMON_REALM_LIMIT" for entry in game.history):
                    game.history.append(HistoryRecord(
                        "SYS_DEMON_REALM_LIMIT", 1, player.age, "魔界绝巅", None, "blocked",
                        "你已修至化魔后期九层；炼魔境须先飞升真魔界。",
                        {"awaiting_ascension": True}, ["system", "realm_limit", "demonic", "milestone"],
                    ))
                return
            if player.world == "human" and player.realm_index == 5 and player.layer >= 3:
                player.opportunity = min(player.opportunity, required)
                if not player.awaiting_spirit_realm_crossing:
                    player.awaiting_spirit_realm_crossing = True
                    game.history.append(HistoryRecord(
                        "SYS_HUMAN_REALM_LIMIT", 1, player.age, "人界绝巅", None, "blocked",
                        "人界法则不足以支撑化神中期。你只能停留在化神初期，等待未来寻得偷渡灵界之法。",
                        {"awaiting_spirit_realm_crossing": True}, ["system", "realm_limit", "milestone"],
                    ))
                return
            if player.realm_index == len(REALMS) - 1 and player.layer == REALMS[-1].layers:
                player.awaiting_ascension = True
                player.opportunity = min(player.opportunity, required)
                return
            old_realm = realm(player)
            old_label = public_player(player)["realm_name"]
            if player.layer >= old_realm.layers:
                player.opportunity = min(player.opportunity, required)
                if not player.awaiting_major_breakthrough:
                    player.awaiting_major_breakthrough = True
                    game.history.append(HistoryRecord(
                        "SYS_BOTTLENECK_READY", 1, player.age, "大境界瓶颈", None, "ready",
                        f"{old_label}机缘已经圆满。你可以继续准备，并在合适时主动突破瓶颈。",
                        {"awaiting_major_breakthrough": True}, ["system", "breakthrough", "major"],
                    ))
                return
            if player.layer in self._manual_minor_layers(player):
                player.opportunity = min(player.opportunity, required)
                if not player.awaiting_minor_breakthrough:
                    player.awaiting_minor_breakthrough = True
                    target_name = self._minor_layer_target(player)
                    game.history.append(HistoryRecord(
                        "SYS_MINOR_BOTTLENECK_READY", 1, player.age, "小境界瓶颈", None, "ready",
                        f"{old_label}机缘已经圆满。你可以服用对应丹药并手动冲击{target_name}。",
                        {"awaiting_minor_breakthrough": True},
                        ["system", "breakthrough", "minor"],
                    ))
                return
            # 练气层级仍沿用自动检定；筑基以后所有层级均停留等待手动冲击。
            chance = self._breakthrough_chance(player, major=False, allow_aids=False)
            if rng.random() >= chance["final"]:
                player.opportunity = required * float(WORLD_SYSTEMS["breakthrough"]["minor_failure_retention"])
                gain = float(WORLD_SYSTEMS["breakthrough"]["minor_failure_heart_demon"])
                player.heart_demon += gain
                game.history.append(HistoryRecord(
                    "SYS_MINOR_BREAKTHROUGH_FAILED", 1, player.age, "小境界冲关失利", None, "failed",
                    f"从{old_label}继续破境失败（成功率 {chance['final']:.1%}）；心魔 +{gain:g}。",
                    {"chance": chance, "heart_demon_gain": gain}, ["system", "breakthrough", "minor", "negative"],
                ))
                return
            player.opportunity = max(0.0, player.opportunity - required)
            if player.realm_index >= 6:
                self._start_breakthrough_trial(
                    game, "traditional", player.realm_index, player.realm_index, old_label,
                    major=False, rng=rng,
                )
                return
            self._complete_minor_breakthrough(game, rng, old_label)

    @staticmethod
    def _manual_minor_layers(player: Player) -> set[int]:
        if player.realm_index < 2:
            return set()
        if player.world == "human" and player.realm_index == 5:
            return set()
        return set(range(1, realm(player).layers))

    def _manual_breakthrough_kind(self, player: Player) -> str | None:
        monster_upper_evolution = bool(
            player.path == "monster" and bloodline_content_available()
            and WORLD_SYSTEMS.get("world_profiles", {}).get("nether", {}).get("enabled")
            and player.layer >= realm(player).layers
            and (
                (player.realm_index == 8 and player.world in {"monster_realm", "phantom_underworld"})
                or (9 <= player.realm_index < len(REALMS) - 1 and player.world == "nether")
            )
        )
        if monster_upper_evolution:
            return "major"
        if player.realm_index >= 9 or (player.realm_index == 8 and player.layer >= REALMS[8].layers):
            return None
        if player.layer >= realm(player).layers and player.realm_index < len(REALMS) - 1:
            return "major"
        if player.layer in self._manual_minor_layers(player):
            return "minor"
        return None

    @staticmethod
    def _minor_stage_target(player: Player) -> str:
        stage = "中期" if player.layer == 3 else "后期"
        return f"{realm(player).name}{stage}"

    def _minor_layer_target(self, player: Player) -> str:
        shell = SectNpc("target", "", "", player.realm_index, player.layer + 1, 0, 1, path=player.path)
        return self._npc_realm_name(shell)

    @staticmethod
    def _minor_pity_key(player: Player) -> str:
        return f"minor:{player.realm_index}:{player.layer}"

    def _minor_pity_bonus(self, player: Player) -> float:
        config = WORLD_SYSTEMS["breakthrough"].get("minor_pity", {})
        if player.layer not in {int(layer) for layer in config.get("eligible_source_layers", [])}:
            return 0.0
        failures = int(player.breakthrough_pity.get(self._minor_pity_key(player), 0))
        return min(float(config.get("max_bonus", 0)), failures * float(config.get("bonus_per_failure", 0)))

    def _record_minor_pity_failure(self, player: Player) -> float:
        if self._minor_pity_bonus(player) == 0 and player.layer not in set(
            WORLD_SYSTEMS["breakthrough"].get("minor_pity", {}).get("eligible_source_layers", [])
        ):
            return 0.0
        key = self._minor_pity_key(player)
        player.breakthrough_pity[key] = int(player.breakthrough_pity.get(key, 0)) + 1
        return self._minor_pity_bonus(player)

    def _clear_minor_pity(self, player: Player) -> None:
        player.breakthrough_pity.pop(self._minor_pity_key(player), None)

    @staticmethod
    def _major_breakthrough_requirement(player: Player) -> dict[str, Any]:
        if player.path == "demonic" and player.world == "demon" and player.realm_index == 5:
            return {
                "met": False,
                "reason": "炼魔境必须先飞升真魔界。",
                "missing_affinities": [],
            }
        if player.realm_index == 5:
            five = {"metal", "wood", "water", "fire", "earth"}
            owned = set(root_elements(player.spirit_root)) | set(player.additional_roots)
            missing = [TECHNIQUE_ELEMENT_NAMES[element] for element in ("metal", "wood", "water", "fire", "earth") if element not in owned]
            return {
                "met": not missing,
                "reason": "突破炼虚必须具备完整五行灵根；当前尚缺" + "、".join(missing) + "灵根。" if missing else "五行灵根齐备。",
                "missing_affinities": missing,
            }
        return {"met": True, "reason": "机缘圆满后可主动突破。", "missing_affinities": []}

    @staticmethod
    def _root_probability_group(player: Player) -> str:
        if player.spirit_root.startswith("acquired_"):
            return "acquired"
        tier = str(root_definition(player.spirit_root).get("tier", ""))
        return {
            "伪灵根": "pseudo", "天灵根": "heavenly", "极品灵根": "supreme",
            "变异灵根": "mutated", "法则灵根": "law", "异世界灵根": "otherworld",
            "后天灵根": "acquired", "后天变异灵根": "acquired",
        }.get(tier, "acquired")

    def _breakthrough_chance(self, player: Player, major: bool, allow_aids: bool = True) -> dict[str, float]:
        config = WORLD_SYSTEMS["breakthrough"]
        source = player.realm_index
        if major and source == 0:
            base = 1.0
        elif major:
            table = config["major_base"][str(source)]
            base = float(table.get(self._root_probability_group(player), table.get("default", 0.01)))
        else:
            base = 1.0 if source == 1 else float(config["minor_base"].get(str(source), 1.0))
        dependent_bonus = 0.0
        if player.concubine_status:
            owner_rank = (
                int(player.concubine_status.get("owner_realm_index", 0)),
                int(player.concubine_status.get("owner_layer", 1)),
            )
            if (player.realm_index, player.layer) < owner_rank:
                dependent_bonus = 0.02
        concubine_base_bonus = min(0.02, player.concubine_breakthrough_bonus) + dependent_bonus
        base += concubine_base_bonus
        scope = f"{'major' if major else 'minor'}:{source}"
        aid_bonus = sum(
            float(ITEM_CATALOG[item_id].breakthrough_bonus)
            for item_id in player.active_breakthrough_aids
            if item_id in ITEM_CATALOG and ITEM_CATALOG[item_id].breakthrough_scope == scope
        ) if allow_aids and player.path != "demonic" and not ghost_cultivation_active(player) else 0.0
        devouring_bonus = player.devouring_breakthrough_bonus if player.path == "demonic" else 0.0
        companion_bonus = (
            float(WORLD_SYSTEMS["relationship"]["companion_breakthrough_bonus"])
            if self._joint_companion_eligible(player) else 0.0
        )
        artifact_bonus = sum(
            float(item.passive_breakthrough_bonus) * item.quantity for item in player.inventory
            if item.passive_breakthrough_bonus > 0
            and item.passive_breakthrough_max_realm is not None
            and source <= int(item.passive_breakthrough_max_realm)
        )
        artifact_bonus += crafted_artifact_bonuses(player)["breakthrough_bonus"]
        penalty = min(
            float(config["heart_demon_penalty_cap"]),
            player.heart_demon * float(config["heart_demon_penalty_per_point"]),
        )
        pity_bonus = 0.0 if major else self._minor_pity_bonus(player)
        body_training_bonus = (
            player.body_training // 20
            * float(WORLD_SYSTEMS["body_cultivation"]["cultivation_breakthrough_bonus_per_20_layers"])
        )
        optimal = config.get("optimal_state", {})
        optimal_state_bonus = (
            float(optimal.get("bonus", 0))
            if player.hp >= max_hp(player) * float(optimal.get("hp_ratio", 0.8))
            and player.mp >= max_mp(player) * float(optimal.get("mp_ratio", 0.8))
            else 0.0
        )
        reincarnation_bonus = reincarnation_breakthrough_bonus(player, source)
        sage_bonus = max(-0.08, min(0.05, float(player.sage_effects.get("breakthrough_bonus", 0.0))))
        # 轮回经验本身不封顶，但所有流派的最终有效突破率都必须保留
        # 至少 2% 的失败风险；扩展配置也不能绕过这一全局硬上限。
        configured_cap = float(
            WORLD_SYSTEMS.get("ghost_cultivation", {}).get("reincarnation_final_probability_cap", 0.98)
        ) if ghost_cultivation_active(player) else 0.98
        final_cap = min(0.98, max(0.005, configured_cap))
        final = max(0.005, min(
            final_cap, base + aid_bonus + companion_bonus + artifact_bonus + pity_bonus
            + body_training_bonus + optimal_state_bonus + devouring_bonus + reincarnation_bonus + sage_bonus - penalty,
        ))
        return {
            "base": base, "aid_bonus": aid_bonus, "companion_bonus": companion_bonus,
            "concubine_base_bonus": concubine_base_bonus,
            "artifact_bonus": artifact_bonus, "pity_bonus": pity_bonus,
            "devouring_bonus": devouring_bonus,
            "reincarnation_bonus": reincarnation_bonus,
            "sage_bonus": sage_bonus,
            "body_training_bonus": body_training_bonus, "optimal_state_bonus": optimal_state_bonus,
            "heart_demon_penalty": penalty, "final": final,
        }

    @staticmethod
    def _joint_companion_eligible(player: Player) -> dict[str, Any] | None:
        companion = player.dao_companion
        if not companion or not companion.get("alive", True) or companion.get("world", player.world) != player.world:
            return None
        if not player.technique or companion.get("main_technique_id") != player.technique.id:
            return None
        if int(companion.get("realm_index", -1)) != player.realm_index:
            return None
        return companion

    def _complete_joint_companion_breakthrough(self, game: GameState, rng: random.Random) -> None:
        joint = game.player.joint_companion_breakthrough
        companion = game.player.dao_companion
        if not joint:
            return
        game.player.joint_companion_breakthrough = None
        if not companion or companion.get("id") != joint.get("id") or not companion.get("alive", True):
            return
        old_label = str(companion.get("realm_name", "原境界"))
        companion["realm_index"] = game.player.realm_index
        companion["layer"] = game.player.layer
        shell = SectNpc("joint", companion["name"], "", game.player.realm_index, game.player.layer, 0, 1)
        companion["realm_name"] = self._npc_realm_name(shell)
        companion["cultivation_progress"] = 0.0
        lifespan_gain = 0
        if bool(joint.get("major")):
            span = REALMS[game.player.realm_index].lifespan
            if span is None:
                companion["lifespan"] = None
            else:
                old_lifespan = int(companion.get("lifespan") or 0)
                rolled = rng.randint(*span) * self._npc_lifespan_multiplier(str(companion.get("path", "dao")))
                companion["lifespan"] = max(old_lifespan, rolled, int(companion.get("age", 0)) + 1)
                lifespan_gain = max(0, int(companion["lifespan"]) - old_lifespan)
        elif game.player.layer in {4, 7} and companion.get("lifespan") is not None:
            stage = "middle" if game.player.layer == 4 else "late"
            stage_range = WORLD_SYSTEMS.get("stage_lifespan_bonus", {}).get(REALMS[game.player.realm_index].id, {}).get(stage)
            if stage_range:
                lifespan_gain = rng.randint(*stage_range) * self._npc_lifespan_multiplier(str(companion.get("path", "dao")))
                companion["lifespan"] = int(companion["lifespan"]) + lifespan_gain
        if game.player.realm_index >= 6 and companion.get("next_tribulation_age") is None:
            thunder = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
            companion["next_tribulation_age"] = int(companion.get("age", game.player.age)) + int(thunder["interval_years"])
            companion["tribulation_count"] = int(companion.get("tribulation_count", 0))
            companion["tribulation_power"] = float(thunder["base_power"]) * float(thunder["power_multiplier"]) ** int(companion["tribulation_count"])
        npc = self._find_npc(game, str(companion.get("id", "")))
        if npc:
            npc.realm_index = game.player.realm_index
            npc.layer = game.player.layer
            npc.cultivation_progress = 0.0
            npc.lifespan = companion.get("lifespan")
            npc.next_tribulation_age = companion.get("next_tribulation_age")
            npc.tribulation_count = int(companion.get("tribulation_count", 0))
            npc.tribulation_power = companion.get("tribulation_power")
        game.history.append(HistoryRecord(
            "SYS_COMPANION_JOINT_BREAKTHROUGH", 1, game.player.age, "同心破境", None, "success",
            f"{companion['name']}与你运转同一主修功法，一同从{old_label}突破至{companion['realm_name']}。"
            + (" 寿元自此无尽。" if companion.get("lifespan") is None else f" 寿元增长 {lifespan_gain} 年。" if lifespan_gain else ""),
            {"companion_id": companion["id"], "realm": [old_label, companion["realm_name"]]},
            ["system", "relationship", "dao_companion", "breakthrough"],
        ))

    @staticmethod
    def _consume_breakthrough_aids(player: Player, scope: str) -> None:
        player.active_breakthrough_aids = [
            item_id for item_id in player.active_breakthrough_aids
            if ITEM_CATALOG.get(item_id) and ITEM_CATALOG[item_id].breakthrough_scope != scope
        ]

    def _start_breakthrough_trial(
        self, game: GameState, kind: str, source: int, target: int, old_label: str,
        major: bool, rng: random.Random,
    ) -> None:
        event_ids = {
            "traditional": [
                "EVT_BREAKTHROUGH_TRADITIONAL_001", "EVT_BREAKTHROUGH_TRADITIONAL_002",
                "EVT_BREAKTHROUGH_TRADITIONAL_003",
            ],
            "heavenly": [
                "EVT_BREAKTHROUGH_HEAVENLY_001", "EVT_BREAKTHROUGH_HEAVENLY_002",
                "EVT_BREAKTHROUGH_HEAVENLY_003", "EVT_BREAKTHROUGH_HEAVENLY_004",
                "EVT_BREAKTHROUGH_HEAVENLY_005",
            ],
            "heavenly_demon": ["EVT_HEAVENLY_DEMON_TRIBULATION_001"],
        }[kind]
        game.active_trial = {
            "kind": kind, "source_realm": source, "target_realm": target,
            "target_layer": 1 if major else game.player.layer + 1,
            "major": major, "old_label": old_label, "step_index": 0,
            "event_ids": event_ids,
            "lethal": bool(source == 3 or source >= 6),
        }
        if kind == "heavenly_demon":
            game.active_trial.update(base_rounds_completed=0, total_battles=0, soul_battles=0)
            self._queue_heavenly_demon_battle(game, rng, soul=None)
        else:
            game.pending_event = self._instantiate_event(self.events_by_id[event_ids[0]], game, rng)

    def _queue_heavenly_demon_battle(
        self, game: GameState, rng: random.Random, soul: dict[str, Any] | None,
    ) -> None:
        trial = game.active_trial or {}
        config = WORLD_SYSTEMS["demonic_cultivation"]["heavenly_demon_tribulation"]
        if soul is None:
            round_index = int(trial.get("base_rounds_completed", 0))
            ratios = list(config["outer_demon_power_ratios"])
            ratio = float(ratios[min(round_index, len(ratios) - 1)])
            target_power = expected_combat_power(int(trial["target_realm"]), 1) * ratio
            event_id = "EVT_HEAVENLY_DEMON_TRIBULATION_001"
            label = f"第 {round_index + 1}/{int(config['base_rounds'])} 重域外天魔"
            runtime = {"battle_kind":"outer_demon", "target_name":label, "target_power":round(target_power, 1)}
        else:
            realm_index = int(soul.get("realm_index", 1))
            inherited_power = float(soul.get("combat_power", 0))
            if inherited_power <= 0:
                inherited_power = expected_combat_power(realm_index, REALMS[realm_index].layers)
            target_power = inherited_power * 0.50
            event_id = "EVT_HEAVENLY_DEMON_SOUL_001"
            label = f"{soul.get('name', '无名元神')}的反噬元神"
            runtime = {
                "battle_kind":"foreign_soul", "target_name":label,
                "target_power":round(target_power, 1), "soul_id":soul.get("id"),
            }
        event = self._instantiate_event(self.events_by_id[event_id], game, rng)
        event["runtime"] = runtime
        trial["battle_runtime"] = copy.deepcopy(runtime)
        event["body"] += f" 当前对手：{label}，战力约 {target_power:.0f}。"
        game.pending_event = event

    def _resolve_heavenly_demon_battle(
        self, game: GameState, step: str, rng: random.Random,
    ) -> tuple[str, str]:
        player = game.player
        trial = game.active_trial
        if not trial:
            raise ValueError("当前没有进行中的天魔劫")
        runtime = dict(trial.get("battle_runtime", {}))
        target_power = max(1.0, float(runtime.get("target_power", 1)))
        own_power = self._player_battle_power(game)
        ratio = own_power / target_power
        target_name = str(runtime.get("target_name", "域外天魔"))
        hp_before, mp_before = player.hp, player.mp
        combat_result, combat_summary = self._combat(game, {
            **runtime,
            "target_name": target_name,
            "target_power": target_power,
            "target_realm_index": int(trial.get("target_realm", player.realm_index)),
            "target_layer": 1,
            "combat_type": "trial",
            "path": "demonic",
            "action": "repel",
            "enemy_objective": "kill",
            "max_rounds": 5,
        }, False, rng)
        won = combat_result == "victory"
        if not won:
            player.joint_companion_breakthrough = None
            game.active_trial = None
            self._die(game, f"天魔劫中不敌{target_name}，肉身与元神尽被魔影吞没", "SYS_HEAVENLY_DEMON_TRIBULATION_FAILED")
            if game.last_combat_report:
                game.last_combat_report["result"] = "dead"
                game.last_combat_report["result_grade"] = "溃败"
            return "dead", f"{combat_summary} 天魔劫无法撤退，你在交战失败后陨落。"

        config = WORLD_SYSTEMS["demonic_cultivation"]["heavenly_demon_tribulation"]
        hp_loss = max(0.0, hp_before - player.hp)
        mp_loss = max(0.0, mp_before - player.mp)
        gain = float(REALMS[int(trial["target_realm"])].opportunity_base) * float(config["victory_opportunity_ratio"])
        self._add_opportunity(player, gain)
        trial["total_battles"] = int(trial.get("total_battles", 0)) + 1
        if runtime.get("battle_kind") == "foreign_soul" or step == "heavenly_demon_soul":
            trial["soul_battles"] = int(trial.get("soul_battles", 0)) + 1
        else:
            trial["base_rounds_completed"] = int(trial.get("base_rounds_completed", 0)) + 1

        souls = list(player.foreign_souls)
        if souls and rng.random() < float(config["soul_lure_chance"]):
            soul = rng.choice(souls)
            self._queue_heavenly_demon_battle(game, rng, soul=soul)
            return "trial_step_success", (
                f"{combat_summary} 天魔劫阶段胜利（初始综合评分比 {ratio:.2f}），"
                f"机缘 +{gain:.0f}；域外天魔又勾起了{soul.get('name', '一道元神')}的反噬。"
            )
        if int(trial.get("base_rounds_completed", 0)) < int(config["base_rounds"]):
            self._queue_heavenly_demon_battle(game, rng, soul=None)
            return "trial_step_success", (
                f"{combat_summary} 天魔劫阶段胜利（初始综合评分比 {ratio:.2f}），"
                f"机缘 +{gain:.0f}；下一重域外天魔已经显形。"
            )

        old_label = str(trial.get("old_label", public_player(player)["realm_name"]))
        total_battles = int(trial.get("total_battles", 0))
        soul_battles = int(trial.get("soul_battles", 0))
        self._complete_major_breakthrough(game, rng, old_label)
        game.active_trial = None
        return "trial_completed", (
            f"你击溃最后一重魔影，HP -{hp_loss:.0f}、MP -{mp_loss:.0f}，机缘 +{gain:.0f}；"
            f"本次天魔劫共交战 {total_battles} 次，其中元神反噬 {soul_battles} 次。"
        )

    def _complete_major_breakthrough(self, game: GameState, rng: random.Random, old_label: str) -> None:
        player = game.player
        player.awaiting_major_breakthrough = False
        player.awaiting_minor_breakthrough = False
        player.heart_demon = max(0.0, player.heart_demon - 5)
        player.realm_index += 1
        player.layer = 1
        grant_intrinsic_progression_if_new_highwater(player)
        grant_wangsheng(player)
        self._raise_divine_sense_one_level(player)
        if player.path == "demonic" and player.realm_index in {4, 7}:
            technique_id = "TECH_HEAVENLY_DEMON_SENSE" if player.realm_index == 4 else "TECH_MYRIAD_SOUL_SENSE"
            unlocked = copy.deepcopy(TECHNIQUE_CATALOG[technique_id])
            learn_technique(player, unlocked)
            assign_technique(player, unlocked, "divine_sense")
        rolled_lifespan = roll_lifespan(player, rng)
        if ghost_cultivation_active(player):
            player.lifespan = None
        elif rolled_lifespan is None:
            player.lifespan = None
        elif player.lifespan is None:
            player.lifespan = rolled_lifespan
        else:
            player.lifespan = max(player.lifespan, rolled_lifespan)
        if realm(player).id == "void" and player.next_tribulation_age is None:
            thunder = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
            player.next_tribulation_age = player.age + int(thunder["interval_years"])
            player.tribulation_power = float(thunder["base_power"]) * float(thunder["power_multiplier"]) ** player.tribulation_count
        player.hp = max_hp(player)
        player.mp = max_mp(player)
        target_label = public_player(player)["realm_name"]
        game.history.append(HistoryRecord(
            "SYS_MAJOR_BREAKTHROUGH", 1, player.age, "突破瓶颈", None, "success",
            f"你通过全部关隘，从{old_label}突破至{target_label}。",
            {"realm": [old_label, target_label]}, ["system", "breakthrough", "major"],
        ))
        general_trait = grant_random_general_monster_trait(
            player, rng, bloodline_available=bloodline_content_available(),
        )
        if general_trait:
            game.history.append(HistoryRecord(
                "SYS_MONSTER_GENERAL_TRAIT", 1, player.age, "凡妖蜕性",
                general_trait["id"], "acquired",
                f"血脉谱系未启用，你在大境界蜕变中获得通用特质【{general_trait['name']}】：{general_trait['description']}",
                {"trait_id": general_trait["id"], "realm_index": player.realm_index},
                ["system", "monster", "trait", "breakthrough", "major", "milestone"],
            ))
        self._complete_joint_companion_breakthrough(game, rng)

    def _complete_minor_breakthrough(self, game: GameState, rng: random.Random, old_label: str) -> None:
        player = game.player
        player.awaiting_minor_breakthrough = False
        player.heart_demon = max(0.0, player.heart_demon - 1)
        old_realm = realm(player)
        player.layer += 1
        grant_intrinsic_progression_if_new_highwater(player)
        grant_wangsheng(player)
        self._raise_divine_sense_one_level(player)
        lifespan_gain = 0
        stage = "middle" if player.layer == 4 else "late" if player.layer == 7 else None
        stage_ranges = WORLD_SYSTEMS.get("stage_lifespan_bonus", {}).get(old_realm.id, {})
        if stage and player.lifespan is not None and stage in stage_ranges:
            lifespan_gain = rng.randint(*stage_ranges[stage])
            if player.path == "monster":
                lifespan_gain *= int(WORLD_SYSTEMS.get("monster_cultivation", {}).get("lifespan_multiplier", 3))
            player.lifespan += lifespan_gain
        player.hp = max_hp(player)
        player.mp = max_mp(player)
        game.history.append(HistoryRecord(
            "SYS_BREAKTHROUGH", 1, player.age, "破境", None, "success",
            f"冲关成功，从{old_label}突破至{public_player(player)['realm_name']}。"
            + (f"境界阶段蜕变令寿元增长 {lifespan_gain} 年。" if lifespan_gain else ""),
            {"realm": [old_label, public_player(player)["realm_name"]], **({"lifespan_gain": lifespan_gain} if lifespan_gain else {})},
            ["system", "breakthrough", "minor"],
        ))
        self._complete_joint_companion_breakthrough(game, rng)

    def _resolve_trial_step(self, game: GameState, step: str, rng: random.Random) -> tuple[str, str]:
        player = game.player
        trial = game.active_trial
        if not trial:
            raise ValueError("当前没有进行中的突破或雷劫")
        kind = str(trial["kind"])
        if kind == "heavenly_demon":
            return self._resolve_heavenly_demon_battle(game, step, rng)
        if kind == "celestial_ascension":
            return self._resolve_celestial_ascension_step(game, step, rng)
        if kind == "asura_ascension":
            return self._resolve_asura_ascension_step(game, step, rng)
        passed = False
        detail = ""
        if kind == "traditional":
            config = WORLD_SYSTEMS["breakthrough"]["traditional"]
            target = str(trial["target_realm"])
            if step == "vitality":
                hp_ratio, mp_ratio = player.hp / max_hp(player), player.mp / max_mp(player)
                passed = hp_ratio >= float(config["hp_ratio"]) and mp_ratio >= float(config["mp_ratio"])
                detail = f"HP {hp_ratio:.0%}/{float(config['hp_ratio']):.0%}，MP {mp_ratio:.0%}/{float(config['mp_ratio']):.0%}"
            elif step == "karma":
                limit = float(config["karma_limits"].get(target, 60))
                actual = effective_karma(player)
                passed, detail = actual <= limit, f"有效因果 {actual:.1f}/{limit:.0f}"
            elif step == "heart_demon":
                limit = float(config["heart_demon_limits"].get(target, 25))
                passed, detail = player.heart_demon <= limit, f"心魔 {player.heart_demon:.1f}/{limit:.0f}"
            drain_hp, drain_mp = config["drain_hp"], config["drain_mp"]
        elif kind == "heavenly":
            config = WORLD_SYSTEMS["breakthrough"]["heavenly"]
            if step == "heaven_vitality":
                ratio = (player.hp + player.mp) / (max_hp(player) + max_mp(player))
                passed, detail = ratio >= float(config["vitality_ratio"]), f"HP+MP 总量 {ratio:.0%}/{float(config['vitality_ratio']):.0%}"
            elif step == "heaven_combat":
                threshold = expected_combat_power(int(trial["target_realm"]), 1) * float(config["combat_ratio"])
                actual = self._player_intrinsic_combat_power(player)
                passed, detail = actual >= threshold, f"战斗力 {actual:.0f}/{threshold:.0f}"
            elif step == "heaven_karma":
                actual, limit = effective_karma(player), float(config["karma_limit"])
                passed, detail = actual <= limit, f"有效因果 {actual:.1f}/{limit:.0f}"
            elif step == "heaven_sha":
                active_path = player.technique.path if player.technique else player.path
                if active_path in {"demonic", "ghost"}:
                    passed, detail = True, "魔修或鬼修以煞入道，本关跳过"
                else:
                    limit = float(config["sha_qi_limit"])
                    passed, detail = player.sha_qi <= limit, f"煞气 {player.sha_qi}/{limit:.0f}"
            elif step == "heaven_heart":
                limit = float(config["heart_demon_limit"])
                passed, detail = player.heart_demon <= limit, f"心魔 {player.heart_demon:.1f}/{limit:.0f}"
            drain_hp, drain_mp = config["drain_hp"], config["drain_mp"]
        else:
            config = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
            strike_index = int(step.rsplit("_", 1)[1]) - 1
            multiplier = float(config["strike_multipliers"][strike_index])
            power = float(trial["power"]) * multiplier
            hp_need = max(max_hp(player) * float(config["hp_ratio"]), power * float(config["power_hp_scale"]))
            mp_need = max(max_mp(player) * float(config["mp_ratio"]), power * float(config["power_mp_scale"]))
            passed = player.hp >= hp_need and player.mp >= mp_need
            detail = f"HP {player.hp:.0f}/{hp_need:.0f}，MP {player.mp:.0f}/{mp_need:.0f}，雷威 {power:.0f}"
            drain_hp, drain_mp = config["drain_hp"], config["drain_mp"]

        if not passed:
            gain = float(WORLD_SYSTEMS["breakthrough"]["trial_failure_heart_demon"])
            player.heart_demon += gain
            player.joint_companion_breakthrough = None
            lethal = bool(trial.get("lethal"))
            game.active_trial = None
            if kind == "periodic_thunder":
                player.next_thunder_damage_reduction = 0.0
            if lethal:
                self._die(game, f"未能渡过{self.events_by_id[game.pending_event['id']]['title'] if game.pending_event else '劫难'}", "SYS_TRIAL_FAILED")
                return "dead", f"判定失败（{detail}），心魔 +{gain:g}，你在劫中陨落。"
            return "breakthrough_failed", f"判定失败（{detail}），你保住性命但冲关中止，心魔 +{gain:g}。"

        reduction = self._tribulation_damage_reduction(player, kind) if kind in {"heavenly", "periodic_thunder"} else 0.0
        damage_multiplier = (
            float(WORLD_SYSTEMS["demonic_cultivation"].get("periodic_thunder_damage_multiplier", 1.0))
            if kind == "periodic_thunder" and player.path == "demonic" else 1.0
        )
        hp_loss = max_hp(player) * rng.uniform(*drain_hp) * (1 - reduction) * damage_multiplier
        mp_loss = max_mp(player) * rng.uniform(*drain_mp) * (1 - reduction) * damage_multiplier
        player.hp = max(1.0, player.hp - hp_loss)
        player.mp = max(0.0, player.mp - mp_loss)
        trial["step_index"] = int(trial["step_index"]) + 1
        event_ids = list(trial["event_ids"])
        if trial["step_index"] < len(event_ids):
            next_event = self.events_by_id[event_ids[trial["step_index"]]]
            game.pending_event = self._instantiate_event(next_event, game, rng)
            reduction_text = f"（法宝减伤 {reduction:.0%}）" if reduction else ""
            if damage_multiplier > 1:
                reduction_text += "（魔修承受雷劫伤害 +20%）"
            return "trial_step_success", f"判定通过（{detail}）；劫力消耗 HP {hp_loss:.0f}、MP {mp_loss:.0f}{reduction_text}。"

        old_label = str(trial.get("old_label", public_player(player)["realm_name"]))
        if kind == "periodic_thunder":
            thunder = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
            player.tribulation_count += 1
            player.next_tribulation_age = player.age + int(thunder["interval_years"])
            player.tribulation_power = float(
                trial.get("uncapped_base_power", trial.get("base_power", trial["power"]))
            ) * float(thunder["power_multiplier"])
            player.next_thunder_damage_reduction = 0.0
            game.history.append(HistoryRecord(
                "SYS_PERIODIC_TRIBULATION", 1, player.age, "三千年雷劫", None, "success",
                f"你连续承受三道真雷，渡过第 {player.tribulation_count} 次雷劫；下一劫威力升至 {player.tribulation_power:.0f}。",
                {"tribulation_count": player.tribulation_count, "next_power": player.tribulation_power}, ["system", "tribulation"],
            ))
        elif bool(trial["major"]):
            self._complete_major_breakthrough(game, rng, old_label)
        else:
            self._complete_minor_breakthrough(game, rng, old_label)
        game.active_trial = None
        reduction_text = f"（法宝减伤 {reduction:.0%}）" if reduction else ""
        if damage_multiplier > 1:
            reduction_text += "（魔修承受雷劫伤害 +20%）"
        return "trial_completed", f"最后一道判定通过（{detail}）；劫力消耗 HP {hp_loss:.0f}、MP {mp_loss:.0f}{reduction_text}。"

    def _resolve_celestial_ascension_step(
        self, game: GameState, step: str, rng: random.Random,
    ) -> tuple[str, str]:
        player = game.player
        trial = game.active_trial
        if not trial:
            raise ValueError("当前没有进行中的飞升劫")
        hp_ratio = player.hp / max(1.0, max_hp(player))
        mp_ratio = player.mp / max(1.0, max_mp(player))
        thunder_index = {
            "ascension_thunder_1":0, "ascension_thunder_2":1, "ascension_thunder_3":2,
        }.get(step)
        reduction = 0.0
        if step == "ascension_body":
            passed, detail, drain_hp, drain_mp = hp_ratio >= 0.75, f"HP {hp_ratio:.0%}/75%", (0.03, 0.06), (0.02, 0.04)
        elif step == "ascension_space":
            passed, detail, drain_hp, drain_mp = mp_ratio >= 0.68, f"MP {mp_ratio:.0%}/68%", (0.03, 0.05), (0.05, 0.08)
        elif thunder_index is not None:
            hp_need = (0.58, 0.48, 0.38)[thunder_index]
            mp_need = (0.52, 0.42, 0.32)[thunder_index]
            passed = hp_ratio >= hp_need and mp_ratio >= mp_need
            detail = f"HP {hp_ratio:.0%}/{hp_need:.0%}，MP {mp_ratio:.0%}/{mp_need:.0%}"
            drain_hp = ((0.08, 0.13), (0.10, 0.16), (0.12, 0.19))[thunder_index]
            drain_mp = ((0.07, 0.11), (0.08, 0.13), (0.10, 0.15))[thunder_index]
            reduction = self._tribulation_damage_reduction(player, "celestial_ascension")
        elif step == "ascension_karma":
            actual = effective_karma(player)
            passed, detail, drain_hp, drain_mp = actual <= 120, f"有效因果 {actual:.1f}/120", (0.02, 0.04), (0.03, 0.05)
        elif step == "ascension_demon":
            threshold = expected_combat_power(8, 9) * 0.75
            actual = self._player_intrinsic_combat_power(player)
            passed = player.heart_demon <= 50 and actual >= threshold
            detail = f"心魔 {player.heart_demon:.1f}/50，战斗力 {actual:.0f}/{threshold:.0f}"
            drain_hp, drain_mp = (0.05, 0.09), (0.07, 0.11)
        elif step == "ascension_law":
            threshold = expected_combat_power(8, 9) * 0.80
            actual = self._player_intrinsic_combat_power(player)
            passed, detail = actual >= threshold, f"战斗力 {actual:.0f}/{threshold:.0f}"
            drain_hp, drain_mp = (0.04, 0.08), (0.06, 0.10)
        elif step == "ascension_heart":
            passed, detail, drain_hp, drain_mp = player.heart_demon <= 45, f"心魔 {player.heart_demon:.1f}/45", (0.02, 0.04), (0.04, 0.07)
        else:
            raise ValueError("未知的飞升劫关隘")
        if not passed:
            player.heart_demon += float(WORLD_SYSTEMS["breakthrough"]["trial_failure_heart_demon"])
            player.next_thunder_damage_reduction = 0.0
            game.active_trial = None
            self._die(game, f"九重飞升劫的{step}判定失败，肉身与元神一同崩解", "SYS_CELESTIAL_ASCENSION_FAILED")
            return "dead", f"飞升判定失败（{detail}），你在仙门之前陨落。"
        hp_loss = max_hp(player) * rng.uniform(*drain_hp) * (1 - reduction)
        mp_loss = max_mp(player) * rng.uniform(*drain_mp) * (1 - reduction)
        player.hp = max(1.0, player.hp - hp_loss)
        player.mp = max(0.0, player.mp - mp_loss)
        trial["step_index"] = int(trial["step_index"]) + 1
        if int(trial["step_index"]) < len(trial["event_ids"]):
            event_id = trial["event_ids"][int(trial["step_index"])]
            game.pending_event = self._instantiate_event(self.events_by_id[event_id], game, rng)
            reduction_text = f"，雷伤减免 {reduction:.0%}" if reduction else ""
            return "trial_step_success", f"第 {trial['step_index']}/9 关通过（{detail}），HP -{hp_loss:.0f}、MP -{mp_loss:.0f}{reduction_text}。"

        origin = player.world
        companion_kept, friend_ids, friend_names, fallen_names = self._resolve_selected_ascension_entourage(
            game, "celestial", rng,
        )
        self._prepare_permanent_world_transition(
            game, keep_companion=companion_kept, keep_friend_ids=friend_ids,
        )
        player.world = "celestial"
        player.location_id = self.maps.default_location("celestial")
        player.realm_index = 9
        player.layer = 1
        player.opportunity = 0.0
        player.awaiting_ascension = False
        player.awaiting_major_breakthrough = False
        player.awaiting_minor_breakthrough = False
        player.immortal_power_converted = False
        player.immortal_conversion_stage = 0
        player.immortal_conversion_last_age = player.age
        player.immortal_conversion_checked_units = 0
        player.next_thunder_damage_reduction = 0.0
        player.next_tribulation_age = None
        player.tribulation_power = None
        player.hp = max_hp(player)
        player.mp = 0.0
        self._clear_market(game)
        self._ensure_heavenly_court(game, rng)
        game.active_trial = None
        game.pending_event = None
        game.history.append(HistoryRecord(
            "SYS_CELESTIAL_ASCENSION_COMPLETE", 1, player.age, "飞升仙界", None, "ascended",
            "你渡过九重飞升劫，自灵界登临仙界并成就真仙；下界法力暂时归零，此后需经过五个长期阶段逐步转化为仙灵力。首次机缘最早在十个仙界时间单位后出现。"
            + (" 道侣与你一同登临仙界。" if companion_kept else "")
            + (f" 道友{'、'.join(friend_names)}成功同行。" if friend_names else "")
            + (f" 道友{'、'.join(fallen_names)}陨落于界壁。" if fallen_names else ""),
            {"world":[origin, "celestial"], "realm_index":[8, 9]},
            ["system", "ascension", "celestial", "milestone"],
        ))
        reduction_text = f"，雷伤减免 {reduction:.0%}" if reduction else ""
        return "trial_completed", f"第 9/9 关通过（{detail}），HP -{hp_loss:.0f}、MP -{mp_loss:.0f}{reduction_text}；你已登临仙界。"

    def _resolve_asura_ascension_step(
        self, game: GameState, step: str, rng: random.Random,
    ) -> tuple[str, str]:
        player = game.player
        trial = game.active_trial
        if not trial:
            raise ValueError("当前没有进行中的修罗飞升劫")
        config = WORLD_SYSTEMS["demonic_cultivation"]["asura_ascension"]
        hp_ratio = player.hp / max(1.0, max_hp(player))
        mp_ratio = player.mp / max(1.0, max_mp(player))
        thunder_index = {
            "asura_thunder_1":0, "asura_thunder_2":1, "asura_thunder_3":2,
        }.get(step)
        reduction = 0.0
        if step == "asura_body":
            passed, detail, drain_hp, drain_mp = hp_ratio >= 0.75, f"HP {hp_ratio:.0%}/75%", (0.04, 0.07), (0.02, 0.04)
        elif step == "asura_boundary":
            current_qi = qi_level(player.qi_experience.get("demon", 0.0))
            required_qi = int(config["required_demon_qi_level"])
            passed = mp_ratio >= 0.68 and current_qi >= required_qi
            detail = f"MP {mp_ratio:.0%}/68%，魔气等级 {current_qi}/{required_qi}"
            drain_hp, drain_mp = (0.03, 0.06), (0.06, 0.10)
        elif thunder_index is not None:
            hp_need = (0.60, 0.50, 0.40)[thunder_index]
            mp_need = (0.54, 0.44, 0.34)[thunder_index]
            passed = hp_ratio >= hp_need and mp_ratio >= mp_need
            detail = f"HP {hp_ratio:.0%}/{hp_need:.0%}，MP {mp_ratio:.0%}/{mp_need:.0%}"
            drain_hp = ((0.09, 0.14), (0.11, 0.17), (0.13, 0.20))[thunder_index]
            drain_mp = ((0.07, 0.12), (0.09, 0.14), (0.11, 0.16))[thunder_index]
            reduction = self._tribulation_damage_reduction(player, "asura_ascension")
        elif step == "asura_karma":
            actual = effective_karma(player)
            limit = float(config["karma_limit"])
            passed, detail = actual <= limit, f"有效因果 {actual:.1f}/{limit:.0f}"
            drain_hp, drain_mp = (0.03, 0.06), (0.04, 0.07)
        elif step == "asura_demon":
            threshold = expected_combat_power(8, 9) * float(config["combat_ratio"])
            actual = self._player_intrinsic_combat_power(player)
            heart_limit = float(config["heart_demon_limit"])
            passed = player.heart_demon <= heart_limit and actual >= threshold
            detail = f"心魔 {player.heart_demon:.1f}/{heart_limit:.0f}，战斗力 {actual:.0f}/{threshold:.0f}"
            drain_hp, drain_mp = (0.06, 0.10), (0.08, 0.12)
        elif step == "asura_sha":
            minimum = int(config["sha_qi_min"])
            passed, detail = player.sha_qi >= minimum, f"煞气 {player.sha_qi}/{minimum}"
            drain_hp, drain_mp = (0.04, 0.08), (0.05, 0.09)
        elif step == "asura_heart":
            limit = float(config["heart_demon_limit"])
            passed, detail = player.heart_demon <= limit, f"心魔 {player.heart_demon:.1f}/{limit:.0f}"
            drain_hp, drain_mp = (0.03, 0.05), (0.05, 0.08)
        else:
            raise ValueError("未知的修罗飞升劫关隘")
        if not passed:
            player.heart_demon += float(WORLD_SYSTEMS["breakthrough"]["trial_failure_heart_demon"])
            player.next_thunder_damage_reduction = 0.0
            game.active_trial = None
            self._die(game, f"九重修罗天魔劫的{step}判定失败，魔躯与元神一同崩解", "SYS_ASURA_ASCENSION_FAILED")
            return "dead", f"修罗飞升判定失败（{detail}），你在天关之前陨落。"
        hp_loss = max_hp(player) * rng.uniform(*drain_hp) * (1 - reduction)
        mp_loss = max_mp(player) * rng.uniform(*drain_mp) * (1 - reduction)
        player.hp = max(1.0, player.hp - hp_loss)
        player.mp = max(0.0, player.mp - mp_loss)
        trial["step_index"] = int(trial["step_index"]) + 1
        if int(trial["step_index"]) < len(trial["event_ids"]):
            event_id = trial["event_ids"][int(trial["step_index"])]
            game.pending_event = self._instantiate_event(self.events_by_id[event_id], game, rng)
            reduction_text = f"，雷伤减免 {reduction:.0%}" if reduction else ""
            return "trial_step_success", f"第 {trial['step_index']}/9 关通过（{detail}），HP -{hp_loss:.0f}、MP -{mp_loss:.0f}{reduction_text}。"

        origin = player.world
        lost_puppets = len(player.puppets)
        companion_kept, friend_ids, friend_names, fallen_names = self._resolve_selected_ascension_entourage(
            game, "asura", rng,
        )
        self._prepare_permanent_world_transition(
            game, keep_companion=companion_kept, keep_friend_ids=friend_ids,
        )
        player.world = "asura"
        player.location_id = self.maps.default_location("asura")
        player.realm_index = 9
        player.layer = 1
        player.opportunity = 0.0
        player.awaiting_ascension = False
        player.awaiting_major_breakthrough = False
        player.awaiting_minor_breakthrough = False
        player.next_thunder_damage_reduction = 0.0
        player.next_tribulation_age = None
        player.tribulation_power = None
        player.hp = max_hp(player)
        player.mp = max_mp(player)
        self._clear_market(game)
        self._ensure_market(game, rng)
        game.active_trial = None
        game.pending_event = None
        game.history.append(HistoryRecord(
            "SYS_ASURA_ASCENSION_COMPLETE", 1, player.age, "飞升修罗界", None, "ascended",
            "你渡过九重修罗天魔劫，自真魔界登临修罗界并成就迦楼罗。四大修罗境界已经确立，但境界突破规则暂未开放。"
            + (f" 受天关排斥，{lost_puppets}具傀儡未能同行。" if lost_puppets else "")
            + (" 道侣与你一同登临修罗界。" if companion_kept else "")
            + (f" 道友{'、'.join(friend_names)}成功同行。" if friend_names else "")
            + (f" 道友{'、'.join(fallen_names)}陨落于界壁。" if fallen_names else ""),
            {"world":[origin, "asura"], "realm_index":[8, 9], "lost_puppets":lost_puppets},
            ["system", "ascension", "asura", "demonic", "milestone"],
        ))
        reduction_text = f"，雷伤减免 {reduction:.0%}" if reduction else ""
        return "trial_completed", f"第 9/9 关通过（{detail}），HP -{hp_loss:.0f}、MP -{mp_loss:.0f}{reduction_text}；你已登临修罗界。"

    def _maybe_immortal_conversion_event(self, game: GameState, rng: random.Random) -> bool:
        player = game.player
        if (
            player.world != "celestial" or player.realm_index < 9 or player.immortal_power_converted
            or player.immortal_conversion_stage >= 5 or game.pending_event or game.active_trial
        ):
            return False
        config = WORLD_SYSTEMS["immortal_power_conversion"]
        unit_years = int(config["time_unit_years"])
        min_gap = int(config["min_gap_units"])
        if player.immortal_conversion_last_age is None:
            player.immortal_conversion_last_age = player.age
            player.immortal_conversion_checked_units = 0
            return False
        elapsed_units = max(0, (player.age - player.immortal_conversion_last_age) // unit_years)
        checked_units = min(elapsed_units, max(0, player.immortal_conversion_checked_units))
        for unit in range(checked_units + 1, elapsed_units + 1):
            player.immortal_conversion_checked_units = unit
            if unit < min_gap:
                continue
            chance = min(0.98, float(config["base_chance"]) + float(config["chance_per_unit"]) * (unit - min_gap))
            if rng.random() >= chance:
                continue
            stage = player.immortal_conversion_stage + 1
            event_id = f"EVT_IMMORTAL_CONVERSION_{stage:03d}"
            event = self._instantiate_event(self.events_by_id[event_id], game, rng)
            event["body"] += f"\n\n你已等待 {unit} 个仙界时间单位，本次触发概率为 {chance:.0%}。"
            event["runtime"] = {"conversion_stage": stage, "waited_units": unit, "trigger_chance": chance}
            game.pending_event = event
            return True
        return False

    def _complete_immortal_conversion_stage(self, game: GameState, expected_stage: int) -> tuple[str, str]:
        player = game.player
        if player.world != "celestial" or player.immortal_power_converted:
            raise ValueError("当前没有可完成的仙灵力转化")
        if expected_stage != player.immortal_conversion_stage + 1 or not 1 <= expected_stage <= 5:
            raise ValueError("仙灵力转化次序不符")
        player.immortal_conversion_stage = expected_stage
        player.immortal_conversion_last_age = player.age
        player.immortal_conversion_checked_units = 0
        player.mp = max_mp(player) * expected_stage / 5
        game.history.append(HistoryRecord(
            f"SYS_IMMORTAL_CONVERSION_{expected_stage}", 1, player.age,
            f"仙灵力转化·{expected_stage * 20}%", None, "completed",
            f"第 {expected_stage}/5 阶段完成，可用仙灵力上限提升至原完整 MP 基准的 {expected_stage * 20}%。",
            {"conversion_stage": expected_stage, "usable_ratio": expected_stage / 5},
            ["system", "celestial", "immortal_power"],
        ))
        if expected_stage < 5:
            return "immortal_conversion_stage", (
                f"第 {expected_stage}/5 阶段完成，可用仙灵力上限现为 {expected_stage * 20}%。"
                "下一阶段需再间隔至少 10 个仙界时间单位。"
            )
        player.immortal_power_converted = True
        learn_technique(player, copy.deepcopy(TECHNIQUE_CATALOG["TECH_CELESTIAL_BREATHING"]))
        add_item(player, "immortal_origin_stone", 3)
        player.hp = max_hp(player)
        player.mp = max_mp(player)
        game.history.append(HistoryRecord(
            "SYS_IMMORTAL_POWER_CONVERTED", 1, player.age, "仙元初成", None, "completed",
            "五个长期阶段全部完成：原有 MP 基准已整体蜕变为仙灵力。你获得《真仙引灵经》与三枚仙元石。",
            {"immortal_power_converted":[False, True], "conversion_stage":5},
            ["system", "celestial", "immortal_power", "milestone"],
        ))
        return "immortal_conversion_completed", "最后阶段完成，仙灵力条已完整开放；仙界行动与仙家功法现已解锁。"

    @staticmethod
    def _body_tribulation_damage_reduction(player: Player) -> float:
        config = WORLD_SYSTEMS["body_cultivation"]
        start = int(config["tribulation_reduction_start"])
        if player.body_training < start:
            return 0.0
        steps = 1 + (player.body_training - start) // int(config["tribulation_reduction_step_layers"])
        return steps * float(config["tribulation_reduction_per_step"])

    def _tribulation_damage_reduction(self, player: Player, kind: str = "heavenly") -> float:
        item_reduction = (
            sum(item.tribulation_damage_reduction * item.quantity for item in player.inventory)
            + player.natal_artifact_tribulation_reduction
            + crafted_artifact_bonuses(player)["tribulation_reduction"]
        )
        one_time = player.next_thunder_damage_reduction if kind in {"periodic_thunder", "celestial_ascension", "asura_ascension"} else 0.0
        return min(0.75, item_reduction + self._body_tribulation_damage_reduction(player) + one_time)

    @staticmethod
    def _tribulation_base_power_cap(world: str) -> float | None:
        raw = WORLD_SYSTEMS["world_profiles"].get(world, {}).get("tribulation_base_power_cap")
        if raw is None:
            return None
        cap = float(raw)
        return cap if cap > 0 else None

    def _check_tribulation(self, game: GameState, rng: random.Random) -> None:
        player = game.player
        if (
            player.realm_index < 6 or game.pending_event or game.active_trial
            or player.next_tribulation_age is None or player.age < player.next_tribulation_age
        ):
            return
        thunder = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
        uncapped_base_power = float(player.tribulation_power or thunder["base_power"])
        world_cap = self._tribulation_base_power_cap(player.world)
        base_power = min(uncapped_base_power, world_cap) if world_cap is not None else uncapped_base_power
        sealed = player.sealed_cultivation or {}
        current_tier = int(WORLD_SYSTEMS["world_profiles"].get(player.world, {}).get("tier", 1))
        upper_tier = int(WORLD_SYSTEMS["world_profiles"].get(str(sealed.get("upper_world", player.world)), {}).get("tier", current_tier))
        world_multiplier = (
            float(WORLD_SYSTEMS["world_travel"].get("lower_world_tribulation_multiplier", 1.0))
            if upper_tier > current_tier else 1.0
        )
        power = base_power * world_multiplier
        event_ids = ["EVT_PERIODIC_THUNDER_001", "EVT_PERIODIC_THUNDER_002", "EVT_PERIODIC_THUNDER_003"]
        game.active_trial = {
            "kind": "periodic_thunder", "source_realm": player.realm_index,
            "target_realm": player.realm_index, "target_layer": player.layer,
            "major": False, "old_label": public_player(player)["realm_name"],
            "step_index": 0, "event_ids": event_ids, "lethal": True, "power": power,
            "base_power":base_power, "uncapped_base_power":uncapped_base_power,
            "world_base_power_cap":world_cap, "world_power_multiplier":world_multiplier,
        }
        game.pending_event = self._instantiate_event(self.events_by_id[event_ids[0]], game, rng)
        game.history.append(HistoryRecord(
            "SYS_TRIBULATION_BEGINS", 1, player.age, "雷劫倒计时归零", None, "started",
            f"第 {player.tribulation_count + 1} 次三千年雷劫降临，当前雷威 {power:.0f}，共需承受三道判定。"
            + (f" 本界法则将基础雷威限制在 {world_cap:.0f}。" if world_cap is not None and uncapped_base_power > world_cap else "")
            + (" 真实道果所在界面高于当前界面，雷劫威力额外增加 50%。" if world_multiplier > 1 else ""),
            {
                "power": power, "base_power":base_power,
                "uncapped_base_power":uncapped_base_power,
                "world_base_power_cap":world_cap,
                "world_power_multiplier":world_multiplier,
                "tribulation_count": player.tribulation_count,
            }, ["system", "tribulation"],
        ))

    def _die(
        self, game: GameState, reason: str, event_id: str, *,
        offer_captive_possession: bool = False,
    ) -> None:
        if not game.player.alive:
            return
        from .possession_system import is_possessed, leave_host_body
        if is_possessed(game.player):
            from .rules import max_hp, max_mp
            host = leave_host_body(game.player)
            game.player.hp = max(1.0, min(game.player.hp, max_hp(game.player)))
            game.player.mp = max(0.0, min(game.player.mp, max_mp(game.player)))
            game.pending_event = None
            game.history.append(HistoryRecord(
                "SYS_POSSESSED_BODY_DESTROYED", 1, game.player.age, "宿身崩毁", None, "returned_to_ghost",
                f"{host.get('name', '宿主')}的肉身因“{reason}”毁灭；你的本魂脱出，夺舍次数不返还。",
                {"host_id": host.get("id"), "source_event": event_id}, ["system", "ghost", "possession"],
            ))
            return
        game.player.alive = False
        game.player.hp = 0
        game.player.death_reason = reason
        game.pending_event = None
        game.history.append(HistoryRecord(
            event_id, 1, game.player.age, "此生落幕", None, "dead", reason,
            {"alive": [True, False]}, ["system", "death"],
        ))
        if offer_captive_possession:
            self._prepare_post_battle_possession(game, event_id)

    @staticmethod
    def _snapshot(player: Player) -> dict[str, Any]:
        return {
            "hp": round(player.hp, 2), "mp": round(player.mp, 2),
            "opportunity": round(player.opportunity, 2), "karma": round(player.karma, 2),
            "sha_qi": player.sha_qi,
            "fame": round(player.fame, 2),
            "hostility": dict(player.hostility),
            "imprisonment": copy.deepcopy(player.imprisonment),
            "party": [entry.get("id") for entry in player.party],
            "heart_demon": round(player.heart_demon, 2),
            "active_breakthrough_aids": list(player.active_breakthrough_aids),
            "awaiting_minor_breakthrough": player.awaiting_minor_breakthrough,
            "technique_level": player.technique.level if player.technique else None,
            "main_technique": player.technique.id if player.technique else None,
            "support_technique": player.support_technique.id if player.support_technique else None,
            "combat_techniques": [entry.id for entry in player.combat_techniques],
            "spirit_root": player.spirit_root, "body_training": player.body_training,
            "body_progress": round(player.body_progress, 2),
            "body_technique": player.body_technique.id if player.body_technique else None,
            "divine_sense_level": divine_sense_level(player),
            "divine_sense_technique": player.divine_sense_technique.id if player.divine_sense_technique else None,
            "prisoners": [entry.get("id") for entry in player.prisoners],
            "puppets": [entry.get("id") for entry in player.puppets],
            "foreign_souls": [entry.get("id") for entry in player.foreign_souls],
            "devouring_breakthrough_bonus": round(player.devouring_breakthrough_bonus, 4),
            "awaiting_body_breakthrough": player.awaiting_body_breakthrough,
            "lifespan": player.lifespan,
            "faction_id": player.faction_id,
            "faction_contribution": player.faction_contribution,
            "faction_reward_preference": player.faction_reward_preference,
            "faction_hp_bonus": player.faction_hp_bonus,
            "faction_mp_bonus": player.faction_mp_bonus,
            "faction_combat_bonus": player.faction_combat_bonus,
            "master": player.master.get("id") if player.master else None,
            "dao_companion": player.dao_companion.get("id") if player.dao_companion else None,
            "disciples": [entry.get("id") for entry in player.disciples],
            "disciple_requests": [entry.get("id") for entry in player.disciple_requests],
            "story_flags": list(player.story_flags),
            "world": player.world,
            "spirit_realm_attempted": player.spirit_realm_attempted,
            "tribulation_count": player.tribulation_count,
            "next_tribulation_age": player.next_tribulation_age,
            "inventory": {item.id: item.quantity for item in player.inventory},
            "alive": player.alive,
        }

    @staticmethod
    def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        return {key: [before.get(key), value] for key, value in after.items() if before.get(key) != value}

    def present(self, game: GameState) -> dict[str, Any]:
        history = [entry for entry in game.history if self._history_visible_in_world(entry, game)]
        self._ensure_natal_artifact(game)
        player_data = public_player(game.player)
        natal_inventory_item = self._natal_artifact_inventory_item(game)
        if natal_inventory_item:
            player_data["inventory"].insert(0, natal_inventory_item)
        location_id = self.maps.normalize_location(game.player.world, game.player.location_id)
        player_data["location_id"] = location_id
        player_data["location_name"] = self.maps.location(game.player.world, location_id)["name"]
        player_data["qi_gain_efficiencies"] = self.maps.qi_gain_efficiencies(game.player.world, location_id)
        for relation in [player_data.get("master"), *player_data.get("disciples", [])]:
            if relation:
                relation["can_invite_faction"] = self._relationship_can_join_faction(game, relation)
                relation["can_invite_guest"] = self._intrigue_can_invite_guest(
                    game, str(relation.get("id", "")),
                )
                relation["gender"] = str(relation.get("gender") or self._stable_gender(str(relation.get("id", ""))))
                relation["gender_name"] = gender_name(relation["gender"])
                relation["can_recruit_concubine"] = bool(
                    relation["gender"] == "female" and self._rank(relation) <= self._rank(game.player)
                    and not any(str(row.get("id")) == str(relation.get("id")) for row in game.player.concubines)
                )
        sealed = game.player.sealed_cultivation
        player_data["cultivation_suppressed"] = bool(sealed)
        if sealed:
            true_shell = SectNpc(
                "true-player", game.player.name, "", int(sealed["realm_index"]), int(sealed["layer"]),
                game.player.age, None,
            )
            player_data["true_realm_index"] = int(sealed["realm_index"])
            player_data["true_layer"] = int(sealed["layer"])
            player_data["true_realm_name"] = self._npc_realm_name(true_shell)
            lower_name = WORLD_SYSTEMS["world_names"].get(game.player.world, game.player.world)
            player_data["realm_name"] += f"（{lower_name}压制；真实{player_data['true_realm_name']}）"
        fame_config = WORLD_SYSTEMS["fame"]
        coalition_threshold = float(
            WORLD_SYSTEMS["faction_conflict"]["demonic_coalition_fame_threshold"]
            if game.player.path == "demonic"
            else WORLD_SYSTEMS["faction_conflict"]["coalition_fame_threshold"]
        )
        player_data["fame_assessment"] = (
            "威压全界，本界围杀势力已经低头"
            if f"world_coalition_subdued:{game.player.world}" in game.player.story_flags else
            "凶名震世，各方势力正在酝酿包围网"
            if game.player.fame > coalition_threshold else
            "威名过盛，修仙界已经明显警觉"
            if game.player.fame >= float(fame_config["alarmed_threshold"]) else
            "声名足以使同道敬重"
            if game.player.fame >= float(fame_config["respected_threshold"]) else
            "尚未在修仙界留下显赫名声"
        )
        party = self._public_party(game)
        player_data["combat_power"] = self._player_intrinsic_combat_power(game.player)
        player_data["battle_power"] = self._player_battle_power(game)
        player_data["expected_combat_power"] = recommended_combat_power(game.player.realm_index, game.player.layer)
        player_data["combat_power_assessment"] = combat_power_assessment_value(
            player_data["combat_power"], player_data["expected_combat_power"],
        )
        if game.debug_world_news:
            player_data["heart_demon"] = round(game.player.heart_demon, 1)
        years_to_tribulation = (
            max(0, game.player.next_tribulation_age - game.player.age)
            if game.player.next_tribulation_age is not None else None
        )
        trial_data = {
            "active": bool(game.active_trial),
            "kind": game.active_trial.get("kind") if game.active_trial else None,
            "step": game.active_trial.get("step_index", 0) + 1 if game.active_trial else None,
            "total_steps": len(game.active_trial.get("event_ids", [])) if game.active_trial else None,
            "allows_recovery_items": bool(game.active_trial),
        }
        if game.active_trial and game.active_trial.get("kind") == "heavenly_demon":
            completed = int(game.active_trial.get("base_rounds_completed", 0))
            minimum = int(WORLD_SYSTEMS["demonic_cultivation"]["heavenly_demon_tribulation"]["base_rounds"])
            queued_soul = game.active_trial.get("battle_runtime", {}).get("battle_kind") == "foreign_soul"
            trial_data.update(
                step=int(game.active_trial.get("total_battles", 0)) + 1,
                total_steps=minimum + int(game.active_trial.get("soul_battles", 0)) + int(queued_soul),
                minimum_rounds=minimum,
                base_rounds_completed=completed,
                total_battles=int(game.active_trial.get("total_battles", 0)),
                soul_battles=int(game.active_trial.get("soul_battles", 0)),
            )
        ranking_data = self._public_spirit_ranking(game)
        new_achievements = self.achievements.evaluate(
            game, player_rank=ranking_data.get("player_rank"),
        )
        return {
            "id": game.id,
            "seed": game.seed,
            "created_at": game.created_at,
            "updated_at": game.updated_at,
            "player": player_data,
            "pending_event": game.pending_event,
            "last_combat_report": copy.deepcopy(game.last_combat_report),
            "settings": dict(game.settings),
            "new_achievements": new_achievements,
            "transformation_system": public_transformation_system(game.player),
            "monster_bloodline": public_monster_bloodline(game.player),
            "history": [entry.to_dict() for entry in reversed(history[-80:])],
            "debug_world_news": game.debug_world_news,
            "actions": ACTIONS,
            "rules": {"karma_factors": KARMA_FACTORS},
            "faction": self._public_faction(game),
            "market": self._public_market(game),
            "auction_system": self._public_auction(game),
            "spirit_field": self._public_spirit_field(game.player),
            "art_skills": self._public_art_skills(game.player),
            "map": self._public_map_with_ghost_parade(game, location_id),
            "world_npcs": self._public_world_npcs(game),
            "spirit_ranking": ranking_data,
            "race_system": self._public_race_system(game),
            "war_system": self._public_war_system(game),
            "world_route": self._public_world_route(game),
            "heavenly_court": self._public_heavenly_court(game),
            "natal_artifact": self._public_natal_artifact(game),
            "crafting_system": self._public_crafting_system(game),
            "formation_system": self._public_formation_system(game),
            "intrigue_system": self._public_intrigue_system(game),
            "sage_system": self._public_sage_system(game),
            "family": self._public_family(game),
            "governance": self._public_governance(game),
            "dao_companion": self._public_dao_companion(game),
            "dao_friends": self._public_dao_friends(game),
            "personal_relations": self._public_personal_relations(game),
            "concubine_system": self._public_concubine_system(game),
            "party": party,
            "wanted": self._public_wanted(game),
            "imprisonment": copy.deepcopy(game.player.imprisonment),
            "demonic_system": self._public_demonic_system(game.player),
            "ghost_system": self._public_ghost_system(game),
            "breakthrough": self._public_major_breakthrough(game.player),
            "body_cultivation": self._public_body_cultivation(game.player),
            "world_travel": {
                "can_ascend_celestial": bool(
                    game.player.world == "spirit" and game.player.realm_index == 8
                    and game.player.layer == REALMS[8].layers
                    and game.player.opportunity >= opportunity_required(game.player)
                    and game.player.path in {"dao", "buddhist", "confucian"}
                    and not game.player.sealed_cultivation and not game.pending_event
                    and not game.active_trial and game.player.alive
                ),
                "can_ascend_asura": bool(
                    game.player.world == "true_demon" and game.player.realm_index == 8
                    and game.player.layer == REALMS[8].layers
                    and game.player.opportunity >= opportunity_required(game.player)
                    and game.player.path == "demonic"
                    and not game.player.sealed_cultivation and not game.pending_event
                    and not game.active_trial and game.player.alive
                ),
                "can_return_human": bool(
                    game.player.world in {"spirit", "hell"}
                    and game.player.realm_index == int(WORLD_SYSTEMS["world_travel"]["required_realm"])
                    and not game.player.sealed_cultivation and game.player.alive
                ),
                "can_return_spirit": bool(
                    game.player.world == "human" and game.player.sealed_cultivation
                    and game.player.sealed_cultivation.get("upper_world") == "spirit" and game.player.alive
                ),
                "can_return_hell": bool(
                    game.player.world == "human" and game.player.sealed_cultivation
                    and game.player.sealed_cultivation.get("upper_world") == "hell" and game.player.alive
                ),
                "can_return_demon": bool(
                    game.player.world == "true_demon"
                    and game.player.realm_index == int(WORLD_SYSTEMS["world_travel"]["required_realm"])
                    and not game.player.sealed_cultivation and game.player.alive
                ),
                "can_return_true_demon": bool(
                    game.player.world == "demon" and game.player.sealed_cultivation
                    and game.player.sealed_cultivation.get("upper_world") == "true_demon" and game.player.alive
                ),
                "can_descend_spirit": bool(
                    game.player.world == "celestial" and game.player.realm_index >= 9
                    and game.player.immortal_power_converted
                    and not game.player.sealed_cultivation and game.player.alive
                ),
                "can_return_celestial": bool(
                    game.player.world == "spirit" and game.player.sealed_cultivation
                    and game.player.sealed_cultivation.get("upper_world") == "celestial" and game.player.alive
                ),
                "can_descend_true_demon": bool(
                    game.player.world == "asura" and game.player.realm_index >= 9
                    and not game.player.sealed_cultivation and game.player.alive
                ),
                "can_return_asura": bool(
                    game.player.world == "true_demon" and game.player.sealed_cultivation
                    and game.player.sealed_cultivation.get("upper_world") == "asura" and game.player.alive
                ),
                "can_descend_phantom": bool(
                    game.player.world == "nether" and game.player.realm_index >= 9
                    and not game.player.sealed_cultivation and game.player.alive
                ),
                "can_descend_monster": bool(
                    game.player.world == "nether" and game.player.realm_index >= 9
                    and not game.player.sealed_cultivation and game.player.alive
                ),
                "can_return_nether": bool(
                    game.player.world in {"monster_realm", "phantom_underworld"} and game.player.sealed_cultivation
                    and game.player.sealed_cultivation.get("upper_world") == "nether" and game.player.alive
                ),
                "suppressed": bool(game.player.sealed_cultivation),
            },
            "trial": trial_data,
            "tribulation": {
                "active": bool(game.active_trial and game.active_trial.get("kind") == "periodic_thunder"),
                "count": game.player.tribulation_count,
                "power": game.player.tribulation_power,
                "world_base_power_cap": self._tribulation_base_power_cap(game.player.world),
                "next_age": game.player.next_tribulation_age,
                "years_remaining": years_to_tribulation,
            },
        }

    @staticmethod
    def _history_visible_in_world(record: HistoryRecord, game: GameState) -> bool:
        if game.debug_world_news:
            return True
        legacy_sect_news = record.event_id in {
            "SYS_SECT_NPC_FALL", "SYS_SECT_NPC_DEPART", "SYS_SECT_NPC_BREAKTHROUGH", "SYS_SECT_RECRUIT",
        }
        if "world_news" not in record.tags and not legacy_sect_news:
            return True
        world_tags = {tag for tag in record.tags if tag.startswith("world:")}
        if not world_tags and legacy_sect_news:
            inferred_worlds = {
                definition.get("world", "human") for definition in FACTION_DEFINITIONS.values()
                if definition["name"] in record.summary
            }
            return not inferred_worlds or game.player.world in inferred_worlds
        if not world_tags:
            # A legacy aggregate may contain mixed-world news and cannot be safely
            # projected. Debug mode still exposes the original record verbatim.
            return False
        return "world:global" in world_tags or f"world:{game.player.world}" in world_tags

    def _public_major_breakthrough(self, player: Player) -> dict[str, Any]:
        if player.sealed_cultivation:
            upper_world = str(player.sealed_cultivation.get("upper_world", "spirit"))
            return {
                "kind": None, "ready": False, "enabled": False, "target_realm": None,
                "action_label": "突破瓶颈", "chance": None, "active_aids": [],
                "met": False, "reason": f"真实道果正受下界压制，返回{WORLD_SYSTEMS['world_names'].get(upper_world, upper_world)}后方可继续修行。",
                "missing_affinities": [],
            }
        kind = self._manual_breakthrough_kind(player)
        at_bottleneck = kind is not None
        major = kind == "major"
        deterministic_monster_evolution = bool(major and player.path == "monster" and bloodline_content_available())
        waiting = player.awaiting_major_breakthrough if major else player.awaiting_minor_breakthrough
        requirement = self._major_breakthrough_requirement(player) if major else {
            "met": True, "reason": "尚未抵达大境界瓶颈。", "missing_affinities": [],
        }
        chance = (
            None if deterministic_monster_evolution
            else self._breakthrough_chance(player, major=major) if at_bottleneck else None
        )
        active_aids = [
            {"id": item_id, "name": ITEM_CATALOG[item_id].name, "bonus": ITEM_CATALOG[item_id].breakthrough_bonus}
            for item_id in player.active_breakthrough_aids if item_id in ITEM_CATALOG
        ]
        if major:
            target_index = player.realm_index + 1
            target_name = (
                WORLD_SYSTEMS.get("demonic_cultivation", {}).get("realm_names", {}).get(str(target_index), REALMS[target_index].name)
                if target_index < len(REALMS) else None
            ) if player.path == "demonic" else (REALMS[target_index].name if target_index < len(REALMS) else None)
            action_label = "选择血脉进化" if deterministic_monster_evolution else "突破大境界"
        elif at_bottleneck:
            target_name = self._minor_layer_target(player)
            action_label = "突破小境界"
            requirement["reason"] = (
                "阶段关隘已经圆满，可以服丹整备后手动冲关。"
                if player.layer in {3, 6} else
                "层级瓶颈已经圆满；本层冲击失败会为下一次累积专属成功率。"
            )
        else:
            target_name = None
            action_label = "突破瓶颈"
        return {
            "kind": kind,
            "ready": bool(waiting and at_bottleneck and player.opportunity >= opportunity_required(player)),
            "enabled": bool(
                player.alive and waiting and at_bottleneck
                and player.opportunity >= opportunity_required(player) and requirement["met"]
            ),
            "target_realm": target_name,
            "action_label": action_label,
            "chance": chance,
            "active_aids": active_aids,
            **requirement,
        }

    def _public_body_cultivation(self, player: Player) -> dict[str, Any]:
        maximum = int(WORLD_SYSTEMS["body_cultivation"]["max_layer"])
        required = self._body_progress_required(player)
        ready = bool(
            player.body_technique and player.body_training < maximum
            and player.awaiting_body_breakthrough and player.body_progress >= required
        )
        return {
            "layer":player.body_training, "max_layer":maximum,
            "progress":round(player.body_progress, 1), "required":round(required, 1),
            "technique":copy.deepcopy(player.body_technique.__dict__) if player.body_technique else None,
            "ready":ready, "chance":self._body_breakthrough_chance(player) if ready else None,
            "target_layer":player.body_training + 1 if player.body_training < maximum else None,
            "tribulation_damage_reduction":self._body_tribulation_damage_reduction(player),
            "cultivation_breakthrough_bonus":player.body_training // 20 * float(WORLD_SYSTEMS["body_cultivation"]["cultivation_breakthrough_bonus_per_20_layers"]),
            "training_speed_multiplier":(
                float(WORLD_SYSTEMS.get("monster_cultivation", {}).get("body_training_multiplier", 1.5))
                if player.path == "monster" else 1.0
            ),
        }

    def _public_world_npcs(self, game: GameState) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        world_people = {**game.world_npcs, **game.notable_npcs}
        for cached in game.encounter_npc_cache:
            saved = cached.get("npc")
            if isinstance(saved, dict):
                npc = SectNpc.from_dict(saved)
                world_people.setdefault(npc.id, npc)
        for npc in sorted(world_people.values(), key=lambda value: (-value.realm_index, -value.layer, value.name)):
            same_world = npc.world == game.player.world
            if not same_world and npc.departed_age is None:
                continue
            perceived_alive = npc.alive and same_world
            if perceived_alive:
                status = "存活"
            elif not npc.alive:
                status = npc.death_reason or "已经陨落"
            elif npc.departure_reason:
                status = "魂灯熄灭，当前界面将其记录为死亡"
            else:
                status = "不在当前界面，生死不明"
            public_npc = npc.to_dict()
            if not same_world:
                public_npc["departure_reason"] = None
            result.append({
                **public_npc, "realm_name": self._npc_realm_name(npc),
                "gender_name": gender_name(npc.gender),
                "spirit_root_name": self._npc_root_name(npc.spirit_root),
                "path_name": PATH_NAMES.get(npc.path, npc.path),
                "race_name": RACE_DEFINITIONS.get(npc.race, {"name": npc.race})["name"],
                "world": npc.world if same_world else None,
                "world_name": WORLD_SYSTEMS["world_names"].get(npc.world, npc.world) if same_world else "去向不明",
                "perceived_alive": perceived_alive, "status": status,
                "combat_power": (
                    self._npc_power(npc) * self._npc_formation_power_multiplier(game, npc.id)
                    if same_world and npc.alive else None
                ),
                "formation": (
                    {
                        "name": game.npc_formations[npc.id]["name"],
                        "durability": round(float(game.npc_formations[npc.id].get("durability", 0.0)), 1),
                        "bonus": round((self._npc_formation_power_multiplier(game, npc.id) - 1.0) * 100.0, 2),
                    }
                    if same_world and npc.alive and npc.id in game.npc_formations else None
                ),
                "attitude": attitude_label(
                    npc.affinity or 0,
                    game.player.hostility.get(self._hostility_key("race", npc.race), 0),
                ) if same_world else "生死不明",
                "in_party": any(entry.get("id") == npc.id for entry in game.player.party),
                "can_invite_party": bool(
                    same_world and npc.alive
                    and len(game.player.party) < int(WORLD_SYSTEMS["party"]["max_companions"])
                    and not any(entry.get("id") == npc.id for entry in game.player.party)
                ),
                "can_propose_companion": bool(
                    same_world and npc.alive
                    and not (game.player.dao_companion and game.player.dao_companion.get("alive", True))
                    and not (game.player.master and game.player.master.get("id") == npc.id)
                    and not any(entry.get("id") == npc.id for entry in game.player.disciples)
                    and not any(str(entry.get("id")) == npc.id for entry in game.player.concubines)
                ),
                "can_befriend": bool(
                    same_world and npc.alive
                    and float(npc.affinity or 0) >= float(WORLD_SYSTEMS["relationship"]["friend_affinity_required"])
                    and not any(entry.get("id") == npc.id for entry in game.player.dao_friends)
                    and not (game.player.dao_companion and game.player.dao_companion.get("id") == npc.id)
                    and not (game.player.master and game.player.master.get("id") == npc.id)
                    and not any(entry.get("id") == npc.id for entry in game.player.disciples)
                    and not any(str(entry.get("id")) == npc.id for entry in game.player.concubines)
                ),
                "can_recruit_concubine": bool(
                    same_world and npc.alive and npc.gender == "female"
                    and (npc.realm_index, npc.layer) <= (game.player.realm_index, game.player.layer)
                    and not any(str(entry.get("id")) == npc.id for entry in game.player.concubines)
                ),
                "can_invite_guest": self._intrigue_can_invite_guest(game, npc.id),
            })
        return result

    def _public_dao_companion(self, game: GameState) -> dict[str, Any] | None:
        companion = game.player.dao_companion
        if not companion:
            return None
        result = copy.deepcopy(companion)
        result["gender"] = str(result.get("gender") or self._stable_gender(str(result.get("id", ""))))
        result["gender_name"] = gender_name(result["gender"])
        result["can_recruit_concubine"] = bool(
            result["gender"] == "female" and self._rank(result) <= self._rank(game.player)
            and not any(str(row.get("id")) == str(result.get("id")) for row in game.player.concubines)
        )
        technique_id = result.get("main_technique_id")
        result["main_technique_name"] = (
            TECHNIQUE_CATALOG[technique_id].name if technique_id in TECHNIQUE_CATALOG else "尚无主修功法"
        )
        result["same_cultivation"] = bool(self._joint_companion_eligible(game.player))
        result["breakthrough_bonus"] = (
            float(WORLD_SYSTEMS["relationship"]["companion_breakthrough_bonus"])
            if result["same_cultivation"] else 0.0
        )
        result["combat_power"] = self._relationship_combat_power(companion)
        result["in_party"] = any(entry.get("id") == companion.get("id") for entry in game.player.party)
        result["can_invite_party"] = bool(
            companion.get("alive", True) and companion.get("world") == game.player.world
            and not result["in_party"]
            and len(game.player.party) < int(WORLD_SYSTEMS["party"]["max_companions"])
        )
        result["can_invite_faction"] = self._relationship_can_join_faction(game, companion)
        result["can_invite_guest"] = self._intrigue_can_invite_guest(
            game, str(companion.get("id", "")),
        )
        return result

    def _public_dao_friends(self, game: GameState) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for friend in game.player.dao_friends:
            row = copy.deepcopy(friend)
            row["gender"] = str(row.get("gender") or self._stable_gender(str(row.get("id", ""))))
            row["gender_name"] = gender_name(row["gender"])
            row["can_recruit_concubine"] = bool(
                row["gender"] == "female" and self._rank(row) <= self._rank(game.player)
                and not any(str(entry.get("id")) == str(row.get("id")) for entry in game.player.concubines)
            )
            technique_id = str(row.get("main_technique_id", ""))
            row["main_technique_name"] = (
                TECHNIQUE_CATALOG[technique_id].name if technique_id in TECHNIQUE_CATALOG else "主修未明"
            )
            row["combat_power"] = self._relationship_combat_power(friend)
            row["in_party"] = any(entry.get("id") == row.get("id") for entry in game.player.party)
            row["can_invite_party"] = bool(
                row.get("alive", True) and row.get("world") == game.player.world and not row["in_party"]
                and len(game.player.party) < int(WORLD_SYSTEMS["party"]["max_companions"])
            )
            row["can_invite_faction"] = self._relationship_can_join_faction(game, friend)
            row["can_invite_guest"] = self._intrigue_can_invite_guest(
                game, str(friend.get("id", "")),
            )
            result.append(row)
        return result

    def _relationship_can_join_faction(self, game: GameState, relation: dict[str, Any]) -> bool:
        sect = game.sects.get(game.player.faction_id or "")
        return bool(
            sect and not sect.extinct and sect.world == game.player.world
            and relation.get("alive", True) and relation.get("world") == game.player.world
            and not self._npc_faction_id(game, str(relation.get("id", "")))
        )

    def _public_personal_relations(self, game: GameState) -> dict[str, list[dict[str, Any]]]:
        rules = WORLD_SYSTEMS["relationship"]
        high_threshold = float(rules["positive_affinity_threshold"])
        low_threshold = float(rules["hostile_affinity_threshold"])
        people = {npc.id:npc for npc in self._all_world_npcs(game) if npc.alive and npc.world == game.player.world}
        relationship_labels: dict[str, str] = {}
        for label, entries in (
            ("师父", [game.player.master] if game.player.master else []),
            ("道侣", [game.player.dao_companion] if game.player.dao_companion else []),
            ("道友", game.player.dao_friends), ("弟子", game.player.disciples),
        ):
            for relation in entries:
                if relation and relation.get("alive", True) and relation.get("world") == game.player.world:
                    relationship_labels[str(relation.get("id"))] = label
                    if str(relation.get("id")) not in people:
                        people[str(relation.get("id"))] = SectNpc(
                            str(relation.get("id")),str(relation.get("name","无名修士")),"旧识",
                            int(relation.get("realm_index",0)),int(relation.get("layer",1)),
                            int(relation.get("age",18)),relation.get("lifespan"),
                            spirit_root=str(relation.get("spirit_root","none")),path=str(relation.get("path","dao")),
                            race=str(relation.get("race","human")),world=str(relation.get("world",game.player.world)),
                            affinity=float(relation.get("affinity",0)),
                        )
        rows = [{
            "id":npc.id,"name":npc.name,"affinity":round(float(npc.affinity or 0),1),
            "attitude":attitude_label(npc.affinity or 0,0),"realm_name":self._npc_realm_name(npc),
            "gender":npc.gender,"gender_name":gender_name(npc.gender),
            "can_recruit_concubine":bool(
                npc.gender == "female" and self._rank(npc) <= self._rank(game.player)
                and not any(str(entry.get("id")) == npc.id for entry in game.player.concubines)
            ),
            "can_invite_guest":self._intrigue_can_invite_guest(game, npc.id),
            "relationship":relationship_labels.get(npc.id,"相识"),
            "faction_name":self._faction_meta(game, self._npc_faction_id(game,npc.id))["name"] if self._npc_faction_id(game,npc.id) else None,
        } for npc in people.values() if float(npc.affinity or 0) >= high_threshold or float(npc.affinity or 0) <= low_threshold]
        return {
            "high":sorted((row for row in rows if row["affinity"] >= high_threshold),key=lambda row:-row["affinity"]),
            "low":sorted((row for row in rows if row["affinity"] <= low_threshold),key=lambda row:row["affinity"]),
        }

    def _relationship_combat_power(self, relation: dict[str, Any]) -> float:
        shell = SectNpc(
            str(relation.get("id", "relation")), str(relation.get("name", "无名")), "",
            int(relation.get("realm_index", 0)), int(relation.get("layer", 1)),
            int(relation.get("age", 1)), relation.get("lifespan"),
            spirit_root=str(relation.get("spirit_root", "none")),
            path=str(relation.get("path", "dao")), race=str(relation.get("race", "human")),
            world=str(relation.get("world", "human")), affinity=float(relation.get("affinity", 0)),
        )
        base = self._npc_power(shell)
        technique = TECHNIQUE_CATALOG.get(str(relation.get("main_technique_id", "")))
        technique_bonus = technique.combat_bonus if technique else 0.0
        item_bonus = sum(
            ITEM_CATALOG[item_id].combat_bonus * int(quantity)
            for item_id, quantity in relation.get("items", {}).items() if item_id in ITEM_CATALOG
        )
        return round(base + technique_bonus + item_bonus, 1)

    def _public_spirit_ranking(self, game: GameState) -> dict[str, Any]:
        ranking_world = game.player.world
        if not self._world_supports(ranking_world, "ranking"):
            return {"available": False, "entries": [], "player_rank": None}
        rows: list[dict[str, Any]] = []
        npcs = [
            *game.world_npcs.values(),
            *game.notable_npcs.values(),
            *(npc for sect in game.sects.values() if sect.world == ranking_world for npc in sect.npcs),
        ]
        seen_ids: set[str] = set()
        for npc in npcs:
            if not npc.alive or npc.world != ranking_world or npc.id in seen_ids:
                continue
            seen_ids.add(npc.id)
            rows.append({
                "id": npc.id, "name": npc.name, "title": npc.title,
                "realm_index": npc.realm_index, "layer": npc.layer,
                "realm_name": self._npc_realm_name(npc), "race": npc.race,
                "race_name": RACE_DEFINITIONS.get(npc.race, {"name": npc.race})["name"],
                "combat_power": self._npc_power(npc), "is_player": False,
            })
        companion = game.player.dao_companion
        if companion and companion.get("alive", True) and companion.get("world") == ranking_world and companion.get("id") not in seen_ids:
            rows.append({
                "id": companion["id"], "name": companion["name"], "title": "玩家道侣",
                "realm_index": int(companion["realm_index"]), "layer": int(companion["layer"]),
                "realm_name": str(companion.get("realm_name", "修为未明")), "race": companion.get("race", "human"),
                "race_name": RACE_DEFINITIONS.get(companion.get("race", "human"), {"name": "种族未明"})["name"],
                "combat_power": self._relationship_combat_power(companion), "is_player": False,
            })
            seen_ids.add(str(companion["id"]))
        for friend in game.player.dao_friends:
            if not friend.get("alive", True) or friend.get("world") != ranking_world or friend.get("id") in seen_ids:
                continue
            seen_ids.add(str(friend["id"]))
            shell = SectNpc(
                str(friend["id"]), str(friend.get("name", "无名道友")), "玩家道友",
                int(friend.get("realm_index", 0)), int(friend.get("layer", 1)),
                int(friend.get("age", 1)), friend.get("lifespan"),
            )
            rows.append({
                "id": friend["id"], "name": friend.get("name", "无名道友"), "title": "玩家道友",
                "realm_index": int(friend.get("realm_index", 0)), "layer": int(friend.get("layer", 1)),
                "realm_name": self._npc_realm_name(shell), "race": friend.get("race", "human"),
                "race_name": RACE_DEFINITIONS.get(friend.get("race", "human"), {"name": "种族未明"})["name"],
                "combat_power": self._relationship_combat_power(friend), "is_player": False,
            })
        player_shell = SectNpc(
            "player", game.player.name, "", game.player.realm_index, game.player.layer,
            current_body_age(game.player), game.player.lifespan,
        )
        rows.append({
            "id": f"player:{game.id}", "name": game.player.name, "title": "玩家",
            "realm_index": game.player.realm_index, "layer": game.player.layer,
            "realm_name": self._npc_realm_name(player_shell), "race": game.player.race,
            "race_name": RACE_DEFINITIONS.get(game.player.race, {"name": game.player.race})["name"],
            "combat_power": self._player_intrinsic_combat_power(game.player), "is_player": True,
        })
        rows.sort(key=lambda entry: (-entry["combat_power"], -entry["realm_index"], -entry["layer"], entry["name"]))
        player_rank = next(index for index, entry in enumerate(rows, 1) if entry["is_player"])
        entries = [{**entry, "rank": index} for index, entry in enumerate(rows[:20], 1)]
        world_name = WORLD_SYSTEMS["world_names"].get(ranking_world, ranking_world)
        return {
            "available": True, "entries": entries, "player_rank": player_rank, "on_board": player_rank <= 20,
            "world": ranking_world, "world_name": world_name, "title": f"{world_name}天榜前二十",
        }

    def _public_party(self, game: GameState) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for reference in game.player.party:
            companion = game.player.dao_companion
            if companion and companion.get("id") == reference.get("id"):
                if companion.get("alive", True) and companion.get("world") == game.player.world:
                    result.append({
                        "id": companion["id"], "name": companion["name"],
                        "realm_index":int(companion.get("realm_index",0)), "layer":int(companion.get("layer",1)),
                        "realm_name": companion.get("realm_name", "修为未明"),
                        "combat_power": self._relationship_combat_power(companion),
                        "affinity": round(float(companion.get("affinity", 0)), 1), "attitude": "道侣",
                        "can_interact":game.governance_actions.get(f"party_interaction:{companion['id']}") != game.player.age,
                        "can_cross_spirit":bool(self._party_crossing_candidate(game, str(companion["id"]))),
                        "selected_for_crossing":bool(
                            game.player.joint_spirit_crossing
                            and str(game.player.joint_spirit_crossing.get("id")) == str(companion["id"])
                            and not game.player.joint_spirit_crossing.get("declined")
                        ),
                    })
                continue
            npc = self._find_npc(game, str(reference.get("id", "")))
            relation = next((entry for entry in [game.player.master, *game.player.dao_friends, *game.player.disciples] if entry and str(entry.get("id")) == str(reference.get("id"))), None)
            if npc and npc.alive and npc.world == game.player.world:
                row = {
                    "id": npc.id, "name": npc.name, "realm_index":npc.realm_index, "layer":npc.layer,
                    "realm_name": self._npc_realm_name(npc), "combat_power": self._npc_power(npc),
                    "affinity": round(npc.affinity or 0, 1), "attitude": attitude_label(npc.affinity or 0, 0),
                }
            elif relation and relation.get("alive", True) and relation.get("world") == game.player.world:
                row = {
                    "id":str(relation["id"]), "name":str(relation["name"]),
                    "realm_index":int(relation.get("realm_index",0)), "layer":int(relation.get("layer",1)),
                    "realm_name":str(relation.get("realm_name","修为未明")),
                    "combat_power":self._relationship_combat_power(relation),
                    "affinity":round(float(relation.get("affinity",0)),1),
                    "attitude":attitude_label(float(relation.get("affinity",0)),0),
                }
            else:
                continue
            row["can_interact"] = game.governance_actions.get(f"party_interaction:{row['id']}") != game.player.age
            row["can_cross_spirit"] = bool(self._party_crossing_candidate(game, row["id"]))
            row["selected_for_crossing"] = any(str(entry.get("id")) == row["id"] for entry in game.player.joint_friend_crossing)
            result.append(row)
        return result

    def _sync_party_state(self, game: GameState) -> bool:
        """Discard references that can no longer represent an active companion."""
        valid: list[dict[str, Any]] = []
        seen: set[str] = set()
        for reference in game.player.party:
            npc_id = str(reference.get("id", ""))
            companion = game.player.dao_companion
            if companion and companion.get("id") == npc_id:
                if npc_id and npc_id not in seen and companion.get("alive", True) and companion.get("world") == game.player.world:
                    seen.add(npc_id)
                    valid.append({"id": npc_id})
                continue
            npc = self._find_npc(game, npc_id)
            relation = next((entry for entry in [game.player.master, *game.player.dao_friends, *game.player.disciples] if entry and str(entry.get("id")) == npc_id), None)
            available = bool(
                (npc and npc.alive and npc.world == game.player.world)
                or (relation and relation.get("alive", True) and relation.get("world") == game.player.world)
            )
            if not npc_id or npc_id in seen or not available:
                continue
            seen.add(npc_id)
            valid.append({"id": npc_id})
        if valid == game.player.party:
            return False
        game.player.party = valid
        return True

    def _public_wanted(self, game: GameState) -> list[dict[str, Any]]:
        player = game.player
        threshold = float(WORLD_SYSTEMS["faction_conflict"]["wanted_threshold"])
        labels = {"sect": "宗门", "family": "家族", "race": "种族", "world": "修仙界包围网"}
        result = []
        for key, value in sorted(player.hostility.items()):
            if value <= threshold:
                continue
            kind, entity_id = key.split(":", 1)
            if self._hostility_entity_state(game, key).get("status") != "active":
                continue
            display_name = (
                self._hostility_name(key, game)
                if kind in {"sect", "family"} else
                RACE_DEFINITIONS.get(entity_id, {"name": entity_id})["name"]
                if kind == "race" else WORLD_SYSTEMS["world_names"].get(entity_id, entity_id) + "包围网"
            )
            result.append({
                "key": key, "kind": kind, "id": entity_id,
                "name": labels.get(kind, "势力"), "display_name": display_name,
                "hostility": round(value, 1),
            })
        return result

    def _public_race_system(self, game: GameState) -> dict[str, Any]:
        race_world = game.player.world
        available = self._world_supports(race_world, "races")
        player_race = self._player_allegiance_race(game.player)
        lineage_race = str(game.player.lineage_race or game.player.race)
        if not available:
            return {
                "available": False, "implemented": True, "player_race": player_race,
                "player_race_name": RACE_DEFINITIONS.get(player_race, {"name": player_race})["name"],
                "lineage_race": lineage_race,
                "lineage_race_name": RACE_DEFINITIONS.get(lineage_race, {"name":lineage_race})["name"],
                "races": {}, "alliances": [],
            }
        self._ensure_race_relations(game)
        diplomacy_history = [
            record for record in reversed(game.history)
            if "diplomacy" in record.tags and f"world:{race_world}" in record.tags
        ]
        races: dict[str, dict[str, Any]] = {}
        for race_id, definition in RACE_DEFINITIONS.items():
            if race_world not in definition.get("worlds", []):
                continue
            relations = []
            for other_id, other_definition in RACE_DEFINITIONS.items():
                if other_id == race_id or race_world not in other_definition.get("worlds", []):
                    continue
                relation = game.race_relations.get(race_pair(race_id, other_id), {})
                relations.append({
                    "race": other_id, "race_name": other_definition["name"],
                    "affinity": round(float(relation.get("affinity", 0)), 1),
                    "status": str(relation.get("status", "neutral")),
                    "status_name": RELATION_LABELS.get(str(relation.get("status", "neutral")), "中立"),
                    "overlord": relation.get("overlord"), "subject": relation.get("subject"),
                    "truce_units_remaining": max(0, max(int(relation.get("truce_until_unit", 0)), int(relation.get("war_truce_until_unit", 0))) - game.diplomacy_unit),
                    "transfer_candidates": self._vassal_transfer_candidates(game, "race", race_id, other_id, relation),
                })
            recent_events = [
                {"age": record.age, "title": record.title, "summary": record.summary, "result": record.result}
                for record in diplomacy_history
                if race_id in record.state_diff.get("races", [])
            ][:12]
            supported_factions: list[dict[str, Any]] = []
            seen_factions: set[str] = set()
            for sect in game.sects.values():
                allegiance = sect.allegiance_race or (sect.npcs[0].race if sect.npcs else "human")
                if sect.world != race_world or allegiance != race_id or sect.extinct:
                    continue
                elders = [
                    npc.name for npc in sorted(
                        (npc for npc in sect.npcs if npc.alive),
                        key=lambda npc: (-npc.realm_index, -npc.layer, npc.name),
                    )[:2]
                ]
                supported_factions.append({"id":sect.id, "name":sect.name, "elders":elders, "active":True})
                seen_factions.add(sect.id)
            for preset in RACE_SYSTEMS.get("faction_presets", {}).get(race_id, []):
                if preset.get("world") != race_world:
                    continue
                if preset["id"] not in seen_factions:
                    supported_factions.append({**copy.deepcopy(preset), "active":False})
            races[race_id] = {
                "id": race_id, **definition,
                "relations": sorted(relations, key=lambda row: (row["status"] == "neutral", -abs(row["affinity"]), row["race_name"])),
                "recent_events": recent_events,
                "supported_factions": supported_factions,
            }
        alliances = []
        races_in_world = set(races)
        for key, relation in game.race_relations.items():
            if relation.get("status") not in {"alliance", "vassal"}:
                continue
            first, second = split_race_pair(key)
            if first not in races_in_world or second not in races_in_world:
                continue
            alliances.append({
                "members": [first, second],
                "name": relation.get("name") or f"{RACE_DEFINITIONS[first]['name']}—{RACE_DEFINITIONS[second]['name']}盟约",
                "status": relation["status"],
                "overlord": relation.get("overlord"), "subject": relation.get("subject"),
            })
        return {
            "available": available, "implemented": True,
            "player_race": player_race,
            "player_race_name": RACE_DEFINITIONS.get(player_race, {"name": player_race})["name"],
            "lineage_race": lineage_race,
            "lineage_race_name": RACE_DEFINITIONS.get(lineage_race, {"name":lineage_race})["name"],
            "races": races, "alliances": alliances,
            "world": race_world,
            "world_name": WORLD_SYSTEMS["world_names"].get(race_world, race_world),
            "has_diplomatic_voice": self._has_race_voice(game),
            "vassal_transfers": [
                {"target_id": other_id, "target_name": RACE_DEFINITIONS[other_id]["name"], "candidates": self._vassal_transfer_candidates(game, "race", player_race, other_id, relation)}
                for key, relation in game.race_relations.items()
                for first, second in [split_race_pair(key)]
                for other_id in [second if first == player_race else first]
                if (
                    player_race in {first, second} and other_id in races_in_world
                    and self._vassal_transfer_candidates(game, "race", player_race, other_id, relation)
                )
            ],
        }

    def _public_world_route(self, game: GameState) -> dict[str, Any]:
        player = game.player
        route_id, route = next(
            (
                (route_id, definition)
                for route_id, definition in WORLD_SYSTEMS.get("cultivation_routes", {}).items()
                if player.path in definition.get("paths", [])
            ),
            ("orthodox", WORLD_SYSTEMS.get("cultivation_routes", {}).get("orthodox", {})),
        )
        stages = []
        for stage in route.get("stages", []):
            is_system = bool(stage.get("system"))
            profile = WORLD_SYSTEMS.get("world_profiles", {}).get(stage.get("world", ""), {})
            stages.append({
                **copy.deepcopy(stage),
                "current": not is_system and stage.get("world") == player.world,
                "kind": "system" if is_system else "world",
                "world_name": (
                    WORLD_SYSTEMS.get("world_names", {}).get(stage.get("world"), stage.get("label", "未知界面"))
                    if not is_system else WORLD_SYSTEMS.get("heavens_framework", {}).get("name", "诸天")
                ),
                "description": (
                    WORLD_SYSTEMS.get("heavens_framework", {}).get("description", "") if is_system else ""
                ),
                "supports": list(profile.get("supports", [])),
                "tier": profile.get("tier"),
            })
        return {
            "route_id": route_id,
            "name": route.get("name", PATH_NAMES.get(player.path, player.path)),
            "path": player.path,
            "path_name": PATH_NAMES.get(player.path, player.path),
            "current_world": player.world,
            "current_world_name": WORLD_SYSTEMS.get("world_names", {}).get(player.world, player.world),
            "lineage_race_name": RACE_DEFINITIONS.get(player.lineage_race or player.race, {"name":player.race})["name"],
            "allegiance_race_name": RACE_DEFINITIONS.get(self._player_allegiance_race(player), {"name":self._player_allegiance_race(player)})["name"],
            "stages": stages,
        }

    def _public_family(self, game: GameState) -> dict[str, Any]:
        player = game.player
        offspring = [
            {
                **copy.deepcopy(child),
                "gender_name": gender_name(str(child.get("gender") or self._stable_gender(str(child.get("id", ""))))),
                "spirit_root_name": self._npc_root_name(str(child.get("spirit_root", "none"))),
                "realm_name": (
                    self._npc_realm_name(SectNpc(
                        str(child.get("id", "child")), str(child.get("name", "后代")), "",
                        int(child.get("realm_index", 0)), int(child.get("layer", 1)),
                        int(child.get("age", 0)), child.get("lifespan"),
                    )) if child.get("cultivation_started") else "尚未踏入仙途"
                ),
            }
            for child in player.offspring
        ]
        family = game.family
        if not family:
            return {
                "exists":False, "can_found":any(child.get("cultivation_started") for child in player.offspring),
                "offspring":offspring, "world":player.world, "has_voice":False, "roster":[],
            }
        roster = []
        visible_family = family.world == player.world or game.debug_world_news
        for npc in sorted(family.npcs if visible_family else [], key=lambda row:(-row.realm_index,-row.layer,row.name)):
            roster.append({
                **npc.to_dict(), "realm_name":self._npc_realm_name(npc),
                "spirit_root_name":self._npc_root_name(npc.spirit_root),
                "combat_power":self._npc_power(npc) if npc.alive else 0,
                "member_type":"本家" if npc.id in {child.get('id') for child in player.offspring} else "外姓门人",
            })
        return {
            "exists":True, "id":family.id, "name":family.name, "description":family.description,
            "world":family.world, "same_world":family.world == player.world, "extinct":family.extinct,
            "has_voice":self._has_family_voice(game), "offspring":offspring, "roster":roster,
            "living_count":sum(npc.alive for npc in family.npcs) if visible_family else None,
        }

    def _public_governance(self, game: GameState) -> dict[str, Any]:
        candidates: dict[str, dict[str, Any]] = {}
        for npc in [*game.world_npcs.values(), *game.notable_npcs.values()]:
            if npc.alive and npc.world == game.player.world:
                candidates[npc.id] = {
                    "id":npc.id,"name":npc.name,"realm_name":self._npc_realm_name(npc),
                    "source":"固定人物" if npc.id in game.world_npcs else "留名人物",
                    "combat_power":round(self._npc_power(npc),1),
                }
        for row in game.encounter_npc_cache:
            raw = row.get("npc", {})
            if raw.get("alive", True) and raw.get("world") == game.player.world:
                npc = SectNpc.from_dict(raw)
                candidates[npc.id] = {
                    "id":npc.id,"name":npc.name,"realm_name":self._npc_realm_name(npc),
                    "source":"路人缓存池","combat_power":round(float(row.get("combat_power",self._npc_power(npc))),1),
                }
        race_voice = self._has_race_voice(game)
        sect_voice = self._has_sect_voice(game)
        family_voice = self._has_family_voice(game)
        authorities = self._available_bounty_authorities(game)
        return {
            "race_voice":race_voice,"sect_voice":sect_voice,"family_voice":family_voice,
            "can_issue_bounty":bool(authorities), "bounty_authorities":authorities,
            "bounty_candidates":sorted(candidates.values(),key=lambda row:(-row["combat_power"],row["name"])),
            "bounties":copy.deepcopy(game.player_bounties),
            "diplomacy_statuses":{
                "war":"宣战","alliance":"结盟","truce":"停战","neutral":"恢复中立","vassal":"确立依附",
            },
        }

    def _public_faction(self, game: GameState) -> dict[str, Any]:
        player = game.player
        world_name = WORLD_SYSTEMS["world_names"].get(player.world, player.world)
        available = [
            {"id": sect.id, **self._faction_meta(game, sect.id), "extinct": sect.extinct}
            for sect in game.sects.values()
            if sect.world == player.world and not sect.extinct
        ]
        if not player.faction_id:
            return {
                "member": False, "available": available, "world": player.world,
                "world_name": world_name, "system_available": bool(available),
                "departed_human_world": player.world != "human",
                "can_found": player.alive, "founding_threshold": self._governance_threshold(player.world),
            }
        if (
            player.faction_id not in game.sects or game.sects[player.faction_id].extinct
            or self._faction_meta(game, player.faction_id).get("world", "human") != player.world
        ):
            return {
                "member": False, "available": available, "world": player.world,
                "world_name": world_name, "system_available": bool(available),
                "departed_human_world": player.world != "human",
                "can_found": False, "founding_threshold": self._governance_threshold(player.world),
            }
        sect = game.sects[player.faction_id]
        definition = self._faction_meta(game, sect.id)
        unlocked = player.realm_index >= 4
        sect_members = self._sect_members(game, sect)
        roster = [
            {
                **npc.to_dict(),
                "title": self._dynamic_sect_title(npc, sect),
                "realm_name": self._npc_realm_name(npc),
                "spirit_root_name": self._npc_root_name(npc.spirit_root),
                "race_name": RACE_DEFINITIONS.get(npc.race, {"name": npc.race})["name"],
                "is_player": False,
            }
            for npc in sect_members if npc.alive and npc.world == sect.world
        ]
        sect_hostility = player.hostility.get(self._hostility_key("sect", sect.id), 0)
        npc_by_id = {npc.id: npc for npc in sect_members}
        player_rank = (player.realm_index, player.layer)
        master_id = player.master["id"] if player.master else None
        disciple_ids = {entry["id"] for entry in player.disciples}
        friend_ids = {entry["id"] for entry in player.dao_friends}
        concubine_ids = {str(entry.get("id")) for entry in player.concubines}
        for entry in roster:
            npc = npc_by_id[entry["id"]]
            npc_rank = (entry["realm_index"], entry["layer"])
            entry["is_master"] = entry["id"] == master_id
            entry["is_disciple"] = entry["id"] in disciple_ids
            entry["is_friend"] = entry["id"] in friend_ids
            entry["path_name"] = PATH_NAMES.get(entry.get("path", "dao"), entry.get("path", "dao"))
            entry["affinity"] = round(npc.affinity or 0, 1)
            entry["attitude"] = attitude_label(npc.affinity or 0, sect_hostility)
            entry["combat_power"] = self._npc_power(npc)
            entry["breakthrough_chance"] = self._npc_breakthrough_probability(npc)
            entry["treasure_name"] = ITEM_CATALOG[npc.treasure_item_id].name if npc.treasure_item_id in ITEM_CATALOG else None
            entry["in_party"] = any(member.get("id") == npc.id for member in player.party)
            entry["can_invite_party"] = bool(
                not entry["in_party"]
                and len(player.party) < int(WORLD_SYSTEMS["party"]["max_companions"])
            )
            entry["can_propose_companion"] = bool(
                not (player.dao_companion and player.dao_companion.get("alive", True))
                and not entry["is_master"] and not entry["is_disciple"]
                and entry["id"] not in concubine_ids
            )
            unrelated = not entry["is_master"] and not entry["is_disciple"]
            entry["can_befriend"] = bool(
                unrelated and not entry["is_friend"] and entry["id"] not in concubine_ids
                and not (player.dao_companion and player.dao_companion.get("id") == entry["id"])
                and float(npc.affinity or 0) >= float(WORLD_SYSTEMS["relationship"]["friend_affinity_required"])
            )
            entry["gender_name"] = gender_name(npc.gender)
            entry["can_recruit_concubine"] = bool(
                npc.gender == "female" and npc_rank <= player_rank
                and not any(str(row.get("id")) == npc.id for row in player.concubines)
            )
            entry["can_intercept"] = True
            entry["can_request_master"] = (
                unrelated and entry["id"] not in concubine_ids
                and player.master is None and npc_rank > player_rank
                and f"master:{entry['id']}" not in player.relationship_attempts
            )
            entry["can_accept_disciple"] = (
                unrelated and entry["id"] not in concubine_ids
                and len(player.disciples) + len(player.disciple_requests) < int(WORLD_SYSTEMS["relationship"]["max_disciples"])
                and npc_rank < player_rank
                and f"disciple:{entry['id']}" not in player.relationship_attempts
            )
        roster.append({
            "id": f"player:{game.id}",
            "name": player.name,
            "gender": player.gender,
            "gender_name": gender_name(player.gender),
            "title": "议事长老" if unlocked else "门下弟子",
            "realm_index": player.realm_index,
            "layer": player.layer,
            "age": current_body_age(player),
            "lifespan": player.lifespan,
            "alive": player.alive,
            "death_reason": player.death_reason,
            "realm_name": public_player(player)["realm_name"],
            "spirit_root": player.spirit_root,
            "spirit_root_name": public_player(player)["spirit_root_display"],
            "path": player.technique.path if player.technique else player.path,
            "path_name": public_player(player)["path_name"],
            "race": player.race,
            "race_name": RACE_DEFINITIONS.get(player.race, {"name": player.race})["name"],
            "is_player": True,
            "is_master": False,
            "is_disciple": False,
            "is_friend": False,
            "can_request_master": False,
            "can_accept_disciple": False,
            "affinity": None,
            "attitude": "自身",
            "combat_power": self._player_intrinsic_combat_power(player),
            "breakthrough_chance": self._breakthrough_chance(player, self._manual_breakthrough_kind(player) == "major")["final"] if self._manual_breakthrough_kind(player) else None,
            "treasure_name": None,
            "in_party": False,
            "can_invite_party": False,
            "can_propose_companion": False,
            "can_befriend": False,
            "can_invite_faction": False,
            "can_intercept": False,
        })
        roster.sort(key=lambda entry: (-entry["realm_index"], -entry["layer"], entry["name"]))
        return {
            "member": True,
            "world": player.world,
            "world_name": world_name,
            "id": sect.id,
            "name": sect.name,
            "description": definition["description"],
            "allegiance_race": sect.allegiance_race or definition.get("allegiance_race", "human"),
            "allegiance_race_name": RACE_DEFINITIONS.get(
                sect.allegiance_race or definition.get("allegiance_race", "human"),
                {"name":sect.allegiance_race or definition.get("allegiance_race", "human")},
            )["name"],
            "role": "开山祖师" if sect.founded_by_player else "议事长老" if unlocked else "宗门弟子",
            "join_age": player.faction_join_age,
            "contribution": player.faction_contribution,
            "fixed_reward_unlocked": unlocked,
            "can_dispatch": unlocked,
            "dispatch_used": player.last_disciple_dispatch_age == player.age,
            "dispatch_cost": int(FACTION_SYSTEMS["disciple_dispatch_cost"]),
            "dispatch_success": float(FACTION_SYSTEMS["disciple_dispatch_success"]),
            "reward_preference": player.faction_reward_preference,
            "reward_options": FACTION_REWARDS,
            "roster": roster,
            "fallen_count": sum(not npc.alive or npc.world != sect.world for npc in sect_members),
            "can_leave": True,
            "hostility": round(sect_hostility, 1),
            "founded_by_player": sect.founded_by_player,
            "can_arrange_succession": bool(
                sect.founded_by_player and sect.founder_player_id == game.id
                and any(npc.alive and npc.world == sect.world for npc in sect_members)
            ),
            "succession_plan": copy.deepcopy(
                self._intrigue_state(game).get("succession_plans", {}).get(sect.id)
            ),
            "pressure": sect.pressure,
            "pressure_limit": int(WORLD_SYSTEMS["player_faction"]["pressure_limit"]),
            "has_diplomatic_voice": self._has_sect_voice(game),
            "diplomacy": self._public_sect_diplomacy(game, sect),
            "diplomacy_events": [
                entry.to_dict() for entry in reversed(game.history)
                if "faction" in entry.tags and "diplomacy" in entry.tags
                and (sect.id in entry.state_diff.get("sects", []) or sect.name in entry.summary)
            ][:12],
        }

    def _public_sect_diplomacy(self, game: GameState, sect: SectState) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for other in game.sects.values():
            if other.id == sect.id or other.world != sect.world or other.extinct:
                continue
            relation = game.sect_relations.get(race_pair(sect.id, other.id), {})
            status = str(relation.get("status", "neutral"))
            living = [npc for npc in other.npcs if npc.alive and npc.world == other.world]
            living.sort(key=lambda npc: (-self._npc_power(npc), -npc.realm_index, -npc.layer))
            recent = [
                record.to_dict() for record in reversed(game.history)
                if "faction" in record.tags and "diplomacy" in record.tags
                and (
                    set(record.state_diff.get("sects", [])) >= {sect.id, other.id}
                    or (sect.name in record.summary and other.name in record.summary)
                )
            ][:4]
            rows.append({
                "target_id": other.id, "target_name": other.name,
                "status": status, "status_name": RELATION_LABELS.get(status, "中立"),
                "affinity": round(float(relation.get("affinity", 0)), 1),
                "overlord": relation.get("overlord"), "subject": relation.get("subject"),
                "since_age": relation.get("since_age"), "last_vote": copy.deepcopy(relation.get("last_vote")),
                "truce_units_remaining": max(0, max(int(relation.get("truce_until_unit", 0)), int(relation.get("war_truce_until_unit", 0))) - game.diplomacy_unit),
                "living_count": len(living),
                "combined_power": round(sum(self._npc_power(npc) for npc in living), 1),
                "leaders": [f"{npc.name}（{self._npc_realm_name(npc)}）" for npc in living[:3]],
                "recent_events": recent,
                "transfer_candidates": self._vassal_transfer_candidates(game, "sect", sect.id, other.id, relation),
            })
        return rows

    def _vassal_transfer_candidates(
        self, game: GameState, kind: str, own_id: str, target_id: str, relation: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if relation.get("status") != "vassal" or relation.get("overlord") != own_id or relation.get("subject") != target_id:
            return []
        player_rank = self._actual_player_realm(game.player)
        if kind == "sect":
            source = game.sects.get(target_id)
            members = list(source.npcs) if source else []
        else:
            members = [
                npc for sect in game.sects.values() for npc in sect.npcs
                if npc.race == target_id
            ]
        return [
            {"id":npc.id,"name":npc.name,"realm_name":self._npc_realm_name(npc)}
            for npc in members
            if npc.alive and npc.world == game.player.world and (npc.realm_index, npc.layer) <= player_rank
        ]

    def _load(self, game_id: str) -> GameState:
        game = self.store.load(game_id)
        conversion_migrated = False
        monster_lifespan_migrated = False
        possession_timeline_migrated = migrate_possession_timeline(game.player)
        ghost_migrated = ensure_ghost_cultivation_state(game.player)
        if ghost_cultivation_active(game.player):
            old_intrinsic_state = (
                game.player.ghost_intrinsic_hp_reference,
                game.player.ghost_intrinsic_hp_current,
                game.player.ghost_intrinsic_mp_reference,
                game.player.ghost_intrinsic_mp_current,
                game.player.ghost_intrinsic_highwater_realm,
                game.player.ghost_intrinsic_highwater_layer,
            )
            grant_intrinsic_progression_if_new_highwater(game.player)
            ghost_migrated = ghost_migrated or old_intrinsic_state != (
                game.player.ghost_intrinsic_hp_reference,
                game.player.ghost_intrinsic_hp_current,
                game.player.ghost_intrinsic_mp_reference,
                game.player.ghost_intrinsic_mp_current,
                game.player.ghost_intrinsic_highwater_realm,
                game.player.ghost_intrinsic_highwater_layer,
            )
        ghost_floor = float(WORLD_SYSTEMS.get("ghost_cultivation", {}).get("soul_death_intrinsic_floor", 1.0))
        if (
            ghost_cultivation_active(game.player) and game.player.alive
            and (
                float(game.player.ghost_intrinsic_hp_current or 0.0) < ghost_floor
                or float(game.player.ghost_intrinsic_mp_current or 0.0) < ghost_floor
            )
        ):
            self._die(game, "本体魂基已经低于存在界限，魂魄彻底消散", "SYS_GHOST_SOUL_DISPERSAL")
            ghost_migrated = True
        if ghost_cultivation_active(game.player) and game.player.active_breakthrough_aids:
            game.player.active_breakthrough_aids = []
            ghost_migrated = True
        if (
            game.player.path == "ghost" and not ghost_cultivation_active(game.player)
            and game.player.ghost_intrinsic_hp_reference is not None
            and game.player.lifespan is None and REALMS[game.player.realm_index].lifespan is not None
        ):
            game.player.lifespan = max(game.player.age + 1, int(REALMS[game.player.realm_index].lifespan[1]))
            ghost_migrated = True
        if game.player.path == "monster" and not game.player.monster_lifespan_scaled:
            if game.player.lifespan is not None:
                game.player.lifespan *= int(
                    WORLD_SYSTEMS.get("monster_cultivation", {}).get("lifespan_multiplier", 3)
                )
            game.player.monster_lifespan_scaled = True
            monster_lifespan_migrated = True
        if game.player.world not in self.maps.worlds:
            game.player.world = "human"
            game.player.location_id = None
            self._clear_market(game)
            monster_lifespan_migrated = True
        if game.player.world == "celestial":
            if game.player.immortal_power_converted:
                if game.player.immortal_conversion_stage != 5:
                    game.player.immortal_conversion_stage = 5
                    conversion_migrated = True
            else:
                if game.player.immortal_conversion_last_age is None:
                    game.player.immortal_conversion_last_age = game.player.age
                    game.player.immortal_conversion_checked_units = 0
                    conversion_migrated = True
                cap = max_mp(game.player) * game.player.immortal_conversion_stage / 5
                if game.player.mp > cap:
                    game.player.mp = cap
                    conversion_migrated = True
                legacy_conversion_trial = bool(
                    game.active_trial and game.active_trial.get("kind") == "immortal_conversion"
                )
                if legacy_conversion_trial:
                    game.active_trial = None
                    conversion_migrated = True
                if legacy_conversion_trial and game.pending_event and str(game.pending_event.get("id", "")).startswith("EVT_IMMORTAL_CONVERSION_"):
                    game.pending_event = None
                    conversion_migrated = True
        normalized_location = self.maps.normalize_location(game.player.world, game.player.location_id)
        location_changed = normalized_location != game.player.location_id
        if location_changed:
            game.player.location_id = normalized_location
            self._clear_market(game)
        elif (
            game.market_location_id is None and game.market_world == game.player.world
            and game.market_offers
        ):
            game.market_location_id = normalized_location
            for offer in game.market_offers:
                offer.setdefault("location_id", normalized_location)
            location_changed = True
        before_known = tuple(technique.id for technique in game.player.known_techniques)
        ensure_technique_set(game.player)
        bloodline_changed = ensure_monster_bloodline_state(game.player)
        if game.player.path == "monster" and bloodline_content_available() and game.player.technique is None:
            starter_id = str(MONSTER_BLOODLINE_SETTINGS.get("starter_technique_id", ""))
            if starter_id in TECHNIQUE_CATALOG:
                starter = copy.deepcopy(TECHNIQUE_CATALOG[starter_id])
                learn_technique(game.player, starter)
                assign_technique(game.player, starter, "main")
                bloodline_changed = True
        version_changed = game.version < 5
        if version_changed:
            legacy_experience = max(0.0, game.player.divine_sense_experience)
            legacy_level = max(
                1 if game.player.path == "demonic" else 0,
                int((legacy_experience / max(1.0, float(WORLD_SYSTEMS["demonic_cultivation"]["divine_sense_experience_base"]))) ** 0.5),
            )
            game.player.divine_sense_rank = max(game.player.divine_sense_rank, legacy_level)
            game.player.divine_sense_experience = max(
                0.0, legacy_experience - divine_sense_level_threshold(legacy_level),
            )
            game.version = 5
        if game.player.path == "demonic" and game.player.divine_sense_technique is None:
            starter = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BLOOD_SOUL_SENSE"])
            learn_technique(game.player, starter)
            assign_technique(game.player, starter, "divine_sense")
            game.player.divine_sense_rank = max(game.player.divine_sense_rank, 1)
        if game.player.path == "demonic" and game.player.technique is None:
            starter = copy.deepcopy(TECHNIQUE_CATALOG["TECH_DEMON_BREATHING"])
            learn_technique(game.player, starter)
            assign_technique(game.player, starter, "main")
            version_changed = True
        changed = ghost_migrated or conversion_migrated or monster_lifespan_migrated or possession_timeline_migrated or version_changed or location_changed or bloodline_changed or before_known != tuple(technique.id for technique in game.player.known_techniques)
        if (
            game.player.body_technique and game.player.body_training < int(WORLD_SYSTEMS["body_cultivation"]["max_layer"])
            and game.player.body_progress >= self._body_progress_required(game.player)
            and not game.player.awaiting_body_breakthrough
        ):
            game.player.awaiting_body_breakthrough = True
            changed = True
        current_realm = realm(game.player)
        if (
            game.player.alive and self._manual_breakthrough_kind(game.player) == "major"
            and game.player.layer >= current_realm.layers
            and game.player.opportunity >= opportunity_required(game.player)
            and not game.player.awaiting_major_breakthrough
        ):
            game.player.awaiting_major_breakthrough = True
            changed = True
        if (
            game.player.alive and game.player.layer in self._manual_minor_layers(game.player)
            and game.player.opportunity >= opportunity_required(game.player)
            and not game.player.awaiting_minor_breakthrough
        ):
            game.player.awaiting_minor_breakthrough = True
            changed = True
        before_world_version = game.world_rules_version
        before_roster = {sect_id: tuple(npc.id for npc in sect.npcs) for sect_id, sect in game.sects.items()}
        before_world_npcs = tuple(game.world_npcs)
        self._ensure_sects(game)
        changed = self._ensure_world_npcs(game) or changed
        changed = self._enforce_world_realm_caps(game) or changed
        changed = self._ensure_npc_formations(game) or changed
        if self._ensure_sage_state(game):
            changed = True
        self._refresh_sage_effects(game)
        changed = self._migrate_true_demon_races(game) or changed
        if game.player.faction_id in game.sects:
            sect_allegiance = game.sects[game.player.faction_id].allegiance_race
            if sect_allegiance and game.player.allegiance_race != sect_allegiance:
                game.player.allegiance_race = sect_allegiance
                changed = True
        elif not game.player.allegiance_race:
            game.player.allegiance_race = game.player.lineage_race or game.player.race
            changed = True
        changed = self._ensure_race_relations(game) or changed
        changed = self._ensure_sect_relations(game) or changed
        changed = self._ensure_wars(game) or changed
        changed = self._compact_world_history(game) or changed
        after_roster = {sect_id: tuple(npc.id for npc in sect.npcs) for sect_id, sect in game.sects.items()}
        changed = (
            changed or after_roster != before_roster or tuple(game.world_npcs) != before_world_npcs
            or game.world_rules_version != before_world_version
        )
        changed = self._sync_party_state(game) or changed
        changed = self._sync_relationship_records(game) or changed
        rng = decode_rng(game.seed, game.rng_state)
        if self._ensure_natal_artifact(game):
            changed = True
        if game.player.world == "celestial" and self._ensure_heavenly_court(game, rng):
            game.rng_state = encode_rng(rng)
            changed = True
        if self._ensure_market(game, rng):
            game.rng_state = encode_rng(rng)
            changed = True
        if changed:
            self.store.save(game)
        if game.pending_event:
            post_battle_possession = game.pending_event.get("id") == "SYS_POST_BATTLE_POSSESSION"
            event = self.events_by_id.get(game.pending_event.get("id"))
            is_mortal_event = bool(event and "mortal" in event.get("tags", []))
            saved_choices = {choice.get("id") for choice in game.pending_event.get("choices", [])}
            current_choices = {choice.get("id") for choice in event.get("choices", [])} if event else set()
            if event:
                tags = event.get("tags", [])
                if game.player.realm_index >= 4 and "faction" in tags and "duty" in tags and "war" not in tags:
                    current_choices.update({"__delegate_faction_task", "__decline_faction_task"})
            incompatible = not post_battle_possession and (
                event is None or ("all_realms" not in (event.get("tags", []) if event else []) and (game.player.realm_index == 0) != is_mortal_event)
                or not saved_choices <= current_choices
            )
            if incompatible:
                game.pending_event = None
                game.active_trial = None
                game.history.append(HistoryRecord(
                    "SYS_CONTENT_MIGRATION", 1, game.player.age, "命途校正", None, "migrated",
                    "旧版本中与当前境界不相容的待处理事件已移出事件池。", {}, ["system", "migration"],
                ))
                self.store.save(game)
        elif game.active_trial:
            game.active_trial = None
            game.history.append(HistoryRecord(
                "SYS_TRIAL_MIGRATION", 1, game.player.age, "劫数校正", None, "migrated",
                "旧存档中失去对应事件的突破或雷劫状态已经清理，可以继续行动。", {},
                ["system", "migration", "tribulation"],
            ))
            self.store.save(game)
        return game

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
            target = {
                "target_name": target_name,
                "target_power": max(1.0, self._player_intrinsic_combat_power(player) * rng.uniform(*settings["power_multiplier"])),
                "target_realm_index": max(1, player.realm_index - 1),
                "combat_type": "beast",
                "success_threshold": settings.get("success_threshold"),
            }
        else:
            target = self._known_npc_encounter_target(game, settings, rng)
            if target is None:
                target = self._generate_cultivator_target(player, target_name, settings, rng, game=game)
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
                "{target_power}": f"{target['target_power']:.0f}",
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
            summary = f"{race_text}你判断对方修为为{target['target_realm_display']}{team_text}，队伍战斗力约 {target['target_power']:.0f}。{rumor}" + summary
        return self._apply_combat_action_rewards(game, action, result, summary, rng)

    def _apply_combat_action_rewards(
        self, game: GameState, action: str, result: str, summary: str, rng: random.Random,
    ) -> str:
        player = game.player
        settings = ACTIONS[action]["combat"]
        if action == "hunt_beast" and result == "killed":
            sha_gain = rng.randint(*settings["sha_qi_gain"])
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
        visible = npc.realm_index <= player.realm_index + 1
        race_definition = RACE_DEFINITIONS.get(npc.race, RACE_DEFINITIONS["human"])
        target = {
            "target_name": npc.name, "target_power": self._npc_power(npc), "primary_power": self._npc_power(npc),
            "target_expected_power": expected_combat_power(npc.realm_index, npc.layer),
            "target_realm_index": npc.realm_index, "target_layer": npc.layer,
            "target_realm_visible": visible,
            "target_realm_display": self._npc_realm_name(npc) if visible else "无法看清",
            "combat_type": "cultivator", "race": npc.race,
            "race_name": race_definition["name"], "race_description": race_definition["description"],
            "world": npc.world, "npc_id": npc.id, "faction_id": faction_id, "path": npc.path,
            "treasure_item_id": npc.treasure_item_id,
            "treasure_rumored": rng.random() < float(config["treasure_rumor_chance"]),
            "notorious": npc.notorious, "notoriety": npc.notoriety,
        }
        return self._add_enemy_party(target, settings, rng)

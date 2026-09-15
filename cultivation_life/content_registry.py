from __future__ import annotations

import json
import copy
import math
import sys
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from .models import Item, RealmDef, SectNpc, Technique, TransformationForm
from .combat_traits import COMBAT_TRAIT_REGISTRY
from .monster_bloodline_traits import BLOODLINE_TRAIT_REGISTRY
from .monster_bloodline_rules import validate_rule_catalog


class ContentError(ValueError):
    """内容包格式或跨表引用不合法。"""


@dataclass(frozen=True)
class ContentRegistry:
    items: dict[str, Item]
    techniques: dict[str, Technique]
    transformations: dict[str, TransformationForm]
    market_goods: tuple[dict[str, Any], ...]
    realms: tuple[RealmDef, ...]
    path_names: dict[str, str]
    karma_factors: dict[str, float]
    affinity_names: dict[str, str]
    root_definitions: dict[str, dict[str, Any]]
    faction_definitions: dict[str, dict[str, Any]]
    faction_rewards: dict[str, dict[str, Any]]
    faction_npc_templates: dict[str, list[dict[str, Any]]]
    actions: dict[str, dict[str, Any]]
    market_settings: dict[str, Any]
    faction_systems: dict[str, Any]
    world_systems: dict[str, Any]
    race_definitions: dict[str, dict[str, Any]]
    race_systems: dict[str, Any]
    world_npc_templates: dict[str, SectNpc]
    story_combat_scenarios: dict[str, dict[str, Any]]
    monster_species: dict[str, dict[str, Any]]
    monster_evolutions: dict[str, dict[str, Any]]
    monster_bloodline_settings: dict[str, Any]

    @classmethod
    def load(cls, content_root: Path, extension_root: Path | None = None) -> "ContentRegistry":
        from .extension_system import load_extensions

        def validate(documents: dict[str, dict[str, Any]]) -> "ContentRegistry":
            registry = cls._from_documents(documents)
            if "achievements.json" in documents:
                from .achievements import load_achievement_definitions

                load_achievement_definitions(documents["achievements.json"])
            event_documents = [
                (name, document) for name, document in documents.items()
                if name == "events.json" or name.endswith("_events.json")
            ]
            if event_documents:
                from .event_repository import EventRepository

                EventRepository.from_documents(
                    event_documents, allow_overrides=True,
                    catalogs={
                        "items":registry.items, "techniques":registry.techniques,
                        "factions":registry.faction_definitions, "world_npcs":registry.world_npc_templates,
                        "monster_imprints":registry.monster_bloodline_settings.get("imprints", {}),
                    },
                )
            return registry

        registry, documents, report = load_extensions(content_root, validate, extension_root)
        cls.loaded_documents = documents
        cls.extension_report = report
        return registry

    @classmethod
    def _from_documents(cls, documents: dict[str, dict[str, Any]]) -> "ContentRegistry":
        items_doc = copy.deepcopy(documents["items.json"])
        techniques_doc = copy.deepcopy(documents["techniques.json"])
        transformations_doc = copy.deepcopy(documents["transformations.json"])
        market_doc = copy.deepcopy(documents["market.json"])
        world_doc = copy.deepcopy(documents["world.json"])
        factions_doc = copy.deepcopy(documents["factions.json"])
        races_doc = copy.deepcopy(documents["races.json"])
        world_npcs_doc = copy.deepcopy(documents["world_npcs.json"])
        story_combat_doc = copy.deepcopy(documents["story_combat_scenarios.json"])
        monster_bloodline_doc = copy.deepcopy(documents.get("monster_bloodlines.json", {"schema_version": 1}))

        items = cls._index_models(items_doc, "items", Item)
        source_defaults = techniques_doc.get("source_defaults_by_path", {})
        expected_source_paths = {"dao", "demonic", "ghost", "monster", "buddhist", "confucian"}
        if set(source_defaults) != expected_source_paths:
            raise ContentError("功法内容必须为每种修炼道路配置默认先天源")
        requirement_levels = techniques_doc.get("combat_requirement_levels_by_grade", {})
        if set(requirement_levels) != {str(grade) for grade in range(1, 9)}:
            raise ContentError("功法内容必须为一至八品配置战斗气等级门槛")
        purity_caps = techniques_doc.get("combat_purity_caps_by_path", {})
        for row in techniques_doc.get("techniques", []):
            if "sources" not in row:
                row["sources"] = dict(source_defaults.get(row.get("path"), {}))
            if "combat_requirements" not in row:
                required_level = int(requirement_levels.get(str(row.get("grade", 1)), 0))
                source_requirements = [
                    {"source": {"id": source, "op": ">=", "level": required_level}}
                    for source in row["sources"]
                ]
                source_expression = (
                    source_requirements[0]
                    if len(source_requirements) == 1
                    else {"any": source_requirements}
                )
                caps = [
                    {"source": {"id": source, "op": "<=", "level": int(level)}}
                    for source, level in purity_caps.get(row.get("path"), {}).items()
                ]
                row["combat_requirements"] = (
                    {"all": [source_expression, *caps]} if caps else source_expression
                )
        techniques = cls._index_models(techniques_doc, "techniques", Technique)
        transformations = cls._index_models(transformations_doc, "forms", TransformationForm)
        market_goods = tuple(market_doc.get("goods", []))
        realms = tuple(cls._realm(row) for row in world_doc.get("realms", []))
        paths = world_doc.get("paths", {})
        path_names = {key: value["name"] for key, value in paths.items()}
        karma_factors = {key: float(value["karma_factor"]) for key, value in paths.items()}
        affinity_names = dict(world_doc.get("affinities", {}))
        root_definitions = cls._build_roots(world_doc.get("roots", {}), affinity_names)
        faction_definitions, faction_npc_templates = cls._build_factions(factions_doc)
        faction_rewards = factions_doc.get("rewards", {})
        race_definitions = {
            row["id"]: {key: value for key, value in row.items() if key != "id"}
            for row in races_doc.get("races", [])
        }
        world_npc_templates = cls._index_models(world_npcs_doc, "npcs", SectNpc)
        story_combat_scenarios = cls._build_story_combat_scenarios(story_combat_doc)
        event_ids = {
            str(row.get("id"))
            for name, document in documents.items()
            if name == "events.json" or name.endswith("_events.json")
            for row in document.get("events", [])
            if isinstance(row, dict) and row.get("id")
        }
        monster_species, monster_evolutions, monster_bloodline_settings = cls._build_monster_bloodlines(
            monster_bloodline_doc, event_ids=event_ids,
        )
        starter_technique = monster_bloodline_settings.get("starter_technique_id")
        if starter_technique and starter_technique not in techniques:
            raise ContentError(f"妖修血脉引用不存在的入门功法：{starter_technique}")
        profiles = world_doc.get("systems", {}).get("world_profiles", {})
        cls._validate(
            items, techniques, transformations, market_goods, realms,
            root_definitions, faction_definitions, set(profiles),
        )
        race_worlds = {
            world_id for world_id, profile in profiles.items()
            if "races" in profile.get("supports", [])
        }
        for faction_id, templates in faction_npc_templates.items():
            faction_world = faction_definitions[faction_id].get("world", "human")
            if faction_world not in profiles:
                raise ContentError(f"宗门 {faction_id} 的世界标签不合法：{faction_world}")
            allegiance_race = faction_definitions[faction_id].get("allegiance_race")
            if (
                allegiance_race not in race_definitions
                or (
                    faction_world in race_worlds
                    and faction_world not in race_definitions[allegiance_race].get("worlds", [])
                )
            ):
                raise ContentError(f"宗门 {faction_id} 的归属种族不属于其所在界面：{allegiance_race}")
            realm_cap = int(profiles[faction_world].get("npc_realm_cap", len(realms) - 1))
            for npc in templates:
                root_id = npc.get("spirit_root")
                if root_id not in root_definitions:
                    raise ContentError(f"宗门 {faction_id} 的 NPC 灵根不合法：{root_id}")
                if faction_world == "human" and root_id.startswith(("law_", "otherworld", "acquired_")):
                    raise ContentError(f"人界宗门 {faction_id} 的 NPC 不得拥有法则、异世界或后天灵根：{root_id}")
                if npc.get("path") not in path_names:
                    raise ContentError(f"宗门 {faction_id} 的 NPC 功法流派不合法：{npc.get('path')}")
                if npc.get("world", faction_world) != faction_world:
                    raise ContentError(f"宗门 {faction_id} 的 NPC 世界标签与宗门不一致")
                if npc.get("race", "human") not in race_definitions:
                    raise ContentError(f"宗门 {faction_id} 的 NPC 种族不存在：{npc.get('race')}")
                if (
                    faction_world in race_worlds
                    and faction_world not in race_definitions[npc.get("race", "human")].get("worlds", [])
                ):
                    raise ContentError(f"宗门 {faction_id} 的 NPC 种族不属于其所在界面：{npc.get('race')}")
                if int(npc.get("realm_index", 0)) > realm_cap:
                    raise ContentError(f"宗门 {faction_id} 的 NPC 超过{faction_world}的境界上限")
        forbidden_races = {"demon", "ghost", "asura"}
        if forbidden_races & set(race_definitions):
            raise ContentError("种族 ID 不得与修行道统或后续界面名称混用")
        spirit_races = {
            race_id for race_id, definition in race_definitions.items()
            if "spirit" in definition.get("worlds", [])
        }
        true_demon_races = {
            race_id for race_id, definition in race_definitions.items()
            if "true_demon" in definition.get("worlds", [])
        }
        if len(spirit_races) != 20 or len(true_demon_races) != 20:
            raise ContentError("灵界与真魔界必须各自配置恰好 20 个种族")
        if spirit_races & true_demon_races != {"human"}:
            raise ContentError("灵界与真魔界仅允许飞升人族作为共有种族")
        faction_presets = races_doc.get("systems", {}).get("faction_presets", {})
        if set(faction_presets) != set(race_definitions):
            raise ContentError("每个上界种族都必须配置宗门预设")
        preset_ids: set[str] = set()
        for race_id, presets in faction_presets.items():
            if not presets:
                raise ContentError(f"种族 {race_id} 至少需要一个宗门预设")
            preset_worlds: set[str] = set()
            for preset in presets:
                elders = preset.get("elders", [])
                if not preset.get("id") or not preset.get("name") or not 1 <= len(elders) <= 2:
                    raise ContentError(f"种族 {race_id} 的宗门预设必须有名称和一至两位长老")
                preset_world = str(preset.get("world", ""))
                if preset_world not in race_worlds or preset_world not in race_definitions[race_id].get("worlds", []):
                    raise ContentError(f"种族 {race_id} 的宗门预设世界标签不合法：{preset_world}")
                preset_worlds.add(preset_world)
                if preset["id"] in preset_ids:
                    raise ContentError(f"宗门预设 ID 重复：{preset['id']}")
                preset_ids.add(preset["id"])
            required_preset_worlds = set(race_definitions[race_id].get("worlds", [])) & race_worlds
            if preset_worlds != required_preset_worlds:
                raise ContentError(f"种族 {race_id} 必须为其所在的每个上界配置宗门预设")
        race_systems = races_doc.get("systems", {})
        diplomatic_rows = [
            *(race_systems.get("alliances", [])),
            *(race_systems.get("diplomacy", {}).get("initial_relations", [])),
        ]
        for row in diplomatic_rows:
            world = str(row.get("world", ""))
            members = [str(member) for member in row.get("members", [])]
            if world not in race_worlds or len(members) != 2 or len(set(members)) != 2:
                raise ContentError("种族外交配置必须指定一个上界和两个不同种族")
            if any(member not in race_definitions or world not in race_definitions[member].get("worlds", []) for member in members):
                raise ContentError(f"种族外交配置包含不属于 {world} 的种族：{members}")
        for npc in world_npc_templates.values():
            if npc.spirit_root not in root_definitions or npc.path not in path_names or npc.race not in race_definitions:
                raise ContentError(f"世界 NPC {npc.id} 的灵根、功法流派或种族不合法")
            if npc.world not in profiles:
                raise ContentError(f"世界 NPC {npc.id} 的世界标签不合法：{npc.world}")
            if npc.world in race_worlds and npc.world not in race_definitions[npc.race].get("worlds", []):
                raise ContentError(f"世界 NPC {npc.id} 的种族不属于其所在界面：{npc.race}")
            realm_cap = int(profiles[npc.world].get("npc_realm_cap", len(realms) - 1))
            if npc.realm_index > realm_cap:
                raise ContentError(f"世界 NPC {npc.id} 超过{npc.world}的境界上限")
        cls._validate_systems(
            world_doc.get("actions", {}), world_doc.get("systems", {}),
            market_doc.get("settings", {}), factions_doc.get("systems", {}), items,
            faction_definitions,
        )
        cls._validate_quick_starts(
            world_doc.get("systems", {}).get("quick_start_presets", []), items, techniques,
            realms, root_definitions, path_names, race_definitions,
        )
        if "crafting.json" in documents:
            cls._validate_crafting(documents["crafting.json"])
        if "formations.json" in documents:
            cls._validate_formations(
                documents["formations.json"], documents.get("crafting.json", {}), items,
            )
        registry = cls(
            items=items, techniques=techniques, transformations=transformations,
            market_goods=market_goods, realms=realms,
            path_names=path_names, karma_factors=karma_factors, affinity_names=affinity_names,
            root_definitions=root_definitions, faction_definitions=faction_definitions,
            faction_rewards=faction_rewards, faction_npc_templates=faction_npc_templates,
            actions=world_doc.get("actions", {}), market_settings=market_doc.get("settings", {}),
            faction_systems=factions_doc.get("systems", {}),
            world_systems=world_doc.get("systems", {}),
            race_definitions=race_definitions, race_systems=races_doc.get("systems", {}),
            world_npc_templates=world_npc_templates,
            story_combat_scenarios=story_combat_scenarios,
            monster_species=monster_species,
            monster_evolutions=monster_evolutions,
            monster_bloodline_settings=monster_bloodline_settings,
        )
        if "maps.json" in documents:
            from .map_system import MapCatalog

            MapCatalog(documents["maps.json"], set(registry.world_systems.get("world_profiles", {})))
        return registry

    @staticmethod
    def _validate_crafting(document: dict[str, Any]) -> None:
        settings = document.get("settings", {})
        stat_keys = {
            "combat_power", "max_hp", "max_mp", "opportunity_efficiency",
            "body_training_efficiency", "divine_sense_efficiency",
            "tribulation_reduction", "breakthrough_bonus",
        }
        quality_keys = {"damaged", "rough", "normal", "excellent", "refined", "epic", "legendary"}
        if (
            len(settings.get("budget_by_realm", [])) != 13
            or set(settings.get("stat_costs", {})) != stat_keys
            or set(settings.get("stat_caps", {})) != stat_keys
            or set(settings.get("quality_multipliers", {})) != quality_keys
            or set(settings.get("quality_names", {})) != quality_keys
        ):
            raise ContentError("炼器配置必须完整声明十三境预算、八类属性与七档品质")
        if float(settings["stat_caps"]["breakthrough_bonus"]) != 0.05:
            raise ContentError("炼器法宝的单件突破属性硬上限必须为 5%")
        molds = document.get("molds", [])
        mold_ids = [str(row.get("id", "")) for row in molds]
        if len(molds) != 12 or len(set(mold_ids)) != 12 or any(not row.get("rule", {}).get("description") for row in molds):
            raise ContentError("炼器内容必须配置十二种唯一胎模及固定规则")
        roles = {"primary", "secondary", "quench"}
        material_ids: set[str] = set()
        covered_worlds: set[str] = set()
        for material in document.get("materials", []):
            material_id = str(material.get("id", ""))
            declared_roles = set(material.get("roles", []))
            if (
                not material_id or material_id in material_ids or not declared_roles
                or not declared_roles <= roles or int(material.get("base_material_value", 0)) <= 0
                or set(material.get("role_effects", {})) != declared_roles
            ):
                raise ContentError(f"炼器材料定义不合法：{material_id or material}")
            material_ids.add(material_id)
            covered_worlds.add(str(material.get("world", "")))
        required_worlds = {
            "human", "spirit", "demon", "true_demon", "monster_realm",
            "phantom_underworld", "hell", "reincarnation",
        }
        if not required_worlds <= covered_worlds:
            raise ContentError("炼器材料没有覆盖四条道途的本界与上位一界")
        for plant in document.get("spirit_plants", []):
            declared_roles = set(plant.get("roles", []))
            if not plant.get("plant_id") or not declared_roles or not declared_roles <= roles or set(plant.get("role_effects", {})) != declared_roles:
                raise ContentError("灵田炼器材料的位置效果定义不完整")

    @staticmethod
    def _validate_formations(
        document: dict[str, Any], crafting: dict[str, Any], items: dict[str, Item],
    ) -> None:
        settings = document.get("settings", {})
        required_settings = {
            "experience_base", "alpha_min", "alpha_max", "alpha_level_scale",
            "market_material_offers", "metric_softcap_per_node", "stat_bonus_cap",
            "enemy_stat_reduction_cap", "change_round_cap", "field_structure_threshold",
            "field_node_ratio", "cycle_weights",
        }
        if set(settings) != required_settings:
            raise ContentError("阵法设置必须完整声明熟练度、广播软上限、效果硬上限与场域阈值")
        if not (
            0 < float(settings["alpha_min"]) < float(settings["alpha_max"]) < 1
            and 0 < float(settings["stat_bonus_cap"]) <= 0.16
            and 0 <= float(settings["enemy_stat_reduction_cap"]) <= 0.08
            and 0 <= float(settings["change_round_cap"]) <= 0.10
            and set(settings["cycle_weights"]) == {"2", "3", "4"}
            and abs(sum(map(float, settings["cycle_weights"].values())) - 1.0) <= 1e-9
        ):
            raise ContentError("阵法传导系数或双侧广播硬上限不合法")
        natures = {
            "metal", "wood", "water", "fire", "earth", "yin", "yang",
            "wind", "thunder", "soul", "space", "star", "law", "neutral",
        }
        stat_keys = {"might", "guard", "mobility", "sense", "sustain", "breach"}
        if set(document.get("relations", {})) != natures:
            raise ContentError("阵法关系表必须为十四种阵性各声明一个有向关系行")
        if set(document.get("nature_channels", {})) != natures or any(
            set(channels) - stat_keys for channels in document.get("nature_channels", {}).values()
        ):
            raise ContentError("阵性到六维战斗通道的映射不完整")
        for source, targets in document["relations"].items():
            if set(targets) - natures or any(not -1.0 <= float(value) <= 1.0 for value in targets.values()):
                raise ContentError(f"阵性 {source} 的有向关系超出 V1 档位")

        identifiers: set[str] = set()
        hooks = {None, "forbidden_air", "forbidden_sense"}

        def validate_profile(row: dict[str, Any], label: str) -> None:
            identifier = str(row.get("id", ""))
            nature = str(row.get("nature", ""))
            if (
                not identifier or identifier in identifiers or nature not in natures
                or float(row.get("formation_value", 0)) <= 0
                or row.get("field_hook") not in hooks
                or set(row.get("relation_overrides", {})) - natures
                or any(not -1.2 <= float(value) <= 1.2 for value in row.get("relation_overrides", {}).values())
            ):
                raise ContentError(f"{label}阵法 Profile 不合法：{identifier or row}")
            identifiers.add(identifier)

        covered_worlds: set[str] = set()
        for material in document.get("materials", []):
            validate_profile(material, "专用")
            if int(material.get("base_value", 0)) <= 0 or int(material.get("tier", -1)) not in range(13):
                raise ContentError(f"阵材价格或境界不合法：{material.get('id')}")
            covered_worlds.add(str(material.get("world", "")))
        required_worlds = {
            "human", "spirit", "celestial", "demon", "true_demon", "asura",
            "phantom_underworld", "nether", "hell", "reincarnation",
        }
        if not required_worlds <= covered_worlds:
            raise ContentError("专用阵材没有覆盖本体十个可达界面")

        crafting_ids = {str(row.get("id")) for row in crafting.get("materials", [])}
        for row in document.get("crafting_materials", []):
            validate_profile(row, "炼器共用")
            if str(row.get("crafting_material_id")) not in crafting_ids:
                raise ContentError(f"阵法引用了不存在的炼器材料：{row.get('crafting_material_id')}")
        for row in document.get("inventory_items", []):
            validate_profile(row, "行囊共用")
            if str(row.get("item_id")) not in items:
                raise ContentError(f"阵法引用了不存在的行囊物品：{row.get('item_id')}")
        for row in document.get("spirit_plants", []):
            validate_profile(row, "灵植共用")
            if not row.get("plant_id"):
                raise ContentError("阵法灵植 Profile 缺少 plant_id")

    @staticmethod
    def _build_monster_bloodlines(
        document: dict[str, Any],
        *, event_ids: set[str] | None = None,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
        species_rows = document.get("species", [])
        evolution_rows = document.get("evolutions", [])
        settings = copy.deepcopy(document.get("settings", {}))
        if not species_rows and not evolution_rows:
            return {}, {}, settings
        if not isinstance(species_rows, list) or not isinstance(evolution_rows, list):
            raise ContentError("妖修血脉的 species 与 evolutions 必须是数组")

        def index(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
            result: dict[str, dict[str, Any]] = {}
            for source in rows:
                if not isinstance(source, dict) or not source.get("id") or source["id"] in result:
                    raise ContentError(f"{label}存在缺失或重复 ID")
                result[str(source["id"])] = copy.deepcopy(source)
            return result

        species = index(species_rows, "妖修本源种")
        evolutions = index(evolution_rows, "妖修进化节点")
        stat_keys = {"might", "guard", "mobility", "sense", "sustain", "breach"}
        allowed_paths = {
            "player.realm_index", "player.layer", "player.world", "player.monster_species_id",
            "player.monster.evolution_id", "player.monster.adaptations", "player.monster.imprints",
            "player.monster.history", "player.monster.qi_level",
        }
        allowed_ops = {"eq", "neq", "gt", "gte", "lt", "lte", "contains", "in"}

        def valid_requirement(requirement: Any) -> bool:
            if not requirement:
                return True
            if not isinstance(requirement, dict):
                return False
            if set(requirement) == {"all"} or set(requirement) == {"any"}:
                children = requirement[next(iter(requirement))]
                return isinstance(children, list) and bool(children) and all(valid_requirement(child) for child in children)
            if set(requirement) == {"not"}:
                return valid_requirement(requirement["not"])
            return (
                "path" in requirement and requirement["path"] in allowed_paths
                and requirement.get("op", "eq") in allowed_ops and "value" in requirement
                and set(requirement) <= {"path", "op", "value"}
            )

        adaptations = settings.get("adaptations", {})
        imprints = settings.get("imprints", {})
        if not isinstance(adaptations, dict) or not isinstance(imprints, dict):
            raise ContentError("妖修适应印记与血脉印记必须使用对象定义")
        if any(
            not definition.get("name") or int(definition.get("years", 0)) <= 0
            or (not definition.get("themes") and not definition.get("locations"))
            for definition in adaptations.values()
        ):
            raise ContentError("妖修适应印记必须声明名称、正数年限以及地域主题或地点")
        if any(not definition.get("name") for definition in imprints.values()):
            raise ContentError("妖修血脉印记必须声明名称")
        default_species = settings.get("default_species_id")
        if default_species not in species:
            raise ContentError("妖修血脉必须指定存在的默认本源种")
        starter = settings.get("starter_technique_id")
        if starter is not None and not isinstance(starter, str):
            raise ContentError("妖修入门功法 ID 必须是字符串")
        custom = settings.get("custom_lineage", {})
        if not isinstance(custom, dict):
            raise ContentError("自创血脉 custom_lineage 必须是对象")

        def nonnegative_integer(value: Any) -> bool:
            return isinstance(value, int) and not isinstance(value, bool) and value >= 0

        if not nonnegative_integer(custom.get("founder_base_points")):
            raise ContentError("自创血脉 founder_base_points 必须是非负整数")
        if not nonnegative_integer(custom.get("minimum_rule_cost")) or custom["minimum_rule_cost"] <= 0:
            raise ContentError("自创血脉 minimum_rule_cost 必须是正整数")
        rule_slots = custom.get("rule_slots")
        if not isinstance(rule_slots, dict) or set(rule_slots) != {"1", "2", "3", "4"}:
            raise ContentError("自创血脉 rule_slots 必须完整声明 1 至 4 阶段")
        slot_values = [rule_slots[str(stage)] for stage in range(1, 5)]
        if any(not nonnegative_integer(value) or value < stage for stage, value in enumerate(slot_values, 1)) or any(
            later <= earlier for earlier, later in zip(slot_values, slot_values[1:])
        ):
            raise ContentError("自创血脉 rule_slots 必须是随阶段严格递增且不少于阶段数的整数")
        stage_names = custom.get("stage_names")
        if not isinstance(stage_names, dict) or set(stage_names) != set(rule_slots) or any(
            not isinstance(name, str) or not name.strip() for name in stage_names.values()
        ):
            raise ContentError("自创血脉 stage_names 必须为全部四阶段提供名称")
        component_keys = ("phases", "schedules", "conditions", "targets", "effects")
        for key in component_keys:
            rows = custom.get(key)
            if not isinstance(rows, list) or not rows or any(not isinstance(row, dict) or not row.get("id") for row in rows):
                raise ContentError(f"自创血脉组件 {key} 不能为空且必须具有 ID")
            if len({str(row["id"]) for row in rows}) != len(rows):
                raise ContentError(f"自创血脉组件 {key} 存在重复 ID")
        phase_ids = {str(row["id"]) for row in custom["phases"]}
        target_ids = {str(row["id"]) for row in custom["targets"]}
        if phase_ids != {"round_start", "round_end"} or target_ids != {"player", "enemy"}:
            raise ContentError("自创血脉只允许轮次起止时点和敌我整体目标")
        if any(not isinstance(row.get("name"), str) or not row["name"].strip() for row in custom["phases"]):
            raise ContentError("自创血脉 phase 必须具有可显示名称")
        supported_schedules = {
            "round_1", "round_2", "round_3", "round_4", "round_5",
            "first_two", "first_three", "odd", "even", "every",
        }
        if {str(row["id"]) for row in custom["schedules"]} != supported_schedules or any(
            not isinstance(row.get("name"), str) or not row["name"].strip()
            or not nonnegative_integer(row.get("cost"))
            for row in custom["schedules"]
        ):
            raise ContentError("自创血脉 schedule 必须完整使用受支持的十种轮次计划，并配置非负整数费用")
        for condition in custom["conditions"]:
            kind = condition.get("kind")
            if (
                not isinstance(condition.get("name"), str) or not condition["name"].strip()
                or not nonnegative_integer(condition.get("discount"))
                or kind not in {"always", "terrain", "artificial", "state", "morale"}
            ):
                raise ContentError(f"自创血脉 condition/{condition.get('id')} 的类型、名称或折扣不合法")
            if kind == "always" and ("value" in condition or "subject" in condition):
                raise ContentError("自创血脉 always 条件不能声明 value 或 subject")
            if kind == "terrain" and condition.get("value") not in {"narrow", "open", "dangerous"}:
                raise ContentError(f"自创血脉 condition/{condition['id']} 使用了未知自然地形")
            if kind == "artificial" and condition.get("value") not in {"forbidden_air", "forbidden_sense", "formation"}:
                raise ContentError(f"自创血脉 condition/{condition['id']} 使用了未知人为战场条件")
            if kind in {"terrain", "artificial"} and "subject" in condition:
                raise ContentError(f"自创血脉 condition/{condition['id']} 不应声明 subject")
            if kind in {"state", "morale"}:
                value = condition.get("value")
                upper = 1 if kind == "state" else 100
                if (
                    condition.get("subject") not in target_ids
                    or not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not math.isfinite(float(value)) or not 0 < float(value) <= upper
                ):
                    raise ContentError(f"自创血脉 condition/{condition['id']} 的 subject 或阈值不合法")
        if any(
            not isinstance(row.get("name"), str) or not row["name"].strip()
            or not nonnegative_integer(row.get("cost"))
            for row in custom["targets"]
        ):
            raise ContentError("自创血脉 target 必须具有名称与非负整数费用")
        value_pools = custom.get("values", {})
        if not isinstance(value_pools, dict) or set(value_pools) != {"percent", "morale"}:
            raise ContentError("自创血脉 value_pool 必须且只能声明 percent 与 morale")
        for pool_id, rows in value_pools.items():
            if not isinstance(rows, list) or not rows:
                raise ContentError(f"自创血脉 value_pool/{pool_id} 不能为空")
            seen_values: set[float] = set()
            for row in rows:
                value = row.get("value") if isinstance(row, dict) else None
                if (
                    not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not math.isfinite(float(value)) or float(value) <= 0
                    or not isinstance(row.get("label"), str) or not row["label"].strip()
                    or not nonnegative_integer(row.get("cost"))
                    or float(value) in seen_values
                    or (pool_id == "percent" and float(value) >= 1)
                ):
                    raise ContentError(f"自创血脉 value_pool/{pool_id} 含有非法或重复档位")
                seen_values.add(float(value))
        supported_effects = {"modify_stat", "restore_combat_state", "modify_morale"}
        for effect in custom["effects"]:
            effect_targets = effect.get("targets", [])
            effect_phases = effect.get("phases", [])
            if (
                not isinstance(effect.get("name"), str) or not effect["name"].strip()
                or not nonnegative_integer(effect.get("cost"))
                or effect.get("kind") not in supported_effects
                or effect.get("value_pool") not in value_pools
                or not isinstance(effect_targets, list) or len(effect_targets) != len(set(effect_targets))
                or not isinstance(effect_phases, list) or len(effect_phases) != len(set(effect_phases))
                or not set(effect_targets) <= target_ids or not set(effect_phases) <= phase_ids
                or not effect_targets or not effect_phases
                or (effect.get("kind") == "modify_stat" and effect.get("stat") not in stat_keys)
            ):
                raise ContentError("自创血脉效果超出有限规则白名单")
            kind = effect["kind"]
            if kind == "modify_stat" and effect["value_pool"] != "percent":
                raise ContentError(f"自创血脉 effect/{effect['id']} 的六维效果必须使用 percent 档位")
            if kind == "restore_combat_state" and (
                effect["value_pool"] != "percent" or set(effect_targets) != {"player"}
            ):
                raise ContentError(f"自创血脉 effect/{effect['id']} 的态势恢复只能作用于自身并使用 percent 档位")
            if kind == "modify_morale" and effect["value_pool"] != "morale":
                raise ContentError(f"自创血脉 effect/{effect['id']} 的战意效果必须使用 morale 档位")
        supported_pairs = {
            (phase, target)
            for effect in custom["effects"]
            for phase in effect["phases"]
            for target in effect["targets"]
        }
        if supported_pairs != {(phase, target) for phase in phase_ids for target in target_ids}:
            raise ContentError("自创血脉 effect 未覆盖全部 phase/target 编辑组合")
        deed_definitions = custom.get("deed_definitions", [])
        cost_rules = custom.get("cost_rules")
        if (
            not isinstance(cost_rules, dict)
            or cost_rules.get("formula") != "schedule + effect + value + target - condition_discount"
            or cost_rules.get("minimum") != custom["minimum_rule_cost"]
        ):
            raise ContentError("自创血脉 cost_rules 必须使用受支持的固定公式，且 minimum 与 minimum_rule_cost 一致")
        compatibility = custom.get("compatibility")
        required_compatibility = {"enforce_effect_phases", "enforce_effect_targets", "immutable_existing_rules"}
        if not isinstance(compatibility, dict) or set(compatibility) != required_compatibility or any(
            compatibility[key] is not True for key in required_compatibility
        ):
            raise ContentError("自创血脉 compatibility 的三项安全约束必须全部开启")
        if not isinstance(deed_definitions, list) or not deed_definitions:
            raise ContentError("自创血脉 deed_definitions 必须是非空数组")
        deed_ids: set[str] = set()
        deed_keys: set[tuple[Any, ...]] = set()
        for deed in deed_definitions:
            if (
                not isinstance(deed, dict) or not isinstance(deed.get("id"), str) or not deed["id"]
                or deed["id"] in deed_ids or not isinstance(deed.get("name"), str) or not deed["name"].strip()
                or deed.get("kind") not in {"evolution", "tribulation", "history", "recorded"}
                or not nonnegative_integer(deed.get("points")) or deed["points"] <= 0
            ):
                raise ContentError("自创血脉 deed_definitions 存在重复 ID 或非法基础字段")
            deed_ids.add(deed["id"])
            kind = deed["kind"]
            if kind == "evolution":
                key = (kind, deed.get("evolution_id"))
                if deed.get("evolution_id") not in evolutions:
                    raise ContentError(f"自创血脉功业 {deed['id']} 引用了不存在的特殊进化")
            elif kind == "tribulation":
                key = (kind, deed.get("threshold"))
                if not nonnegative_integer(deed.get("threshold")) or deed["threshold"] <= 0:
                    raise ContentError(f"自创血脉功业 {deed['id']} 的渡劫阈值必须是正整数")
            elif kind == "history":
                key = (kind, deed.get("event_id"), deed.get("result"), deed.get("choice_id"))
                if (
                    not isinstance(deed.get("event_id"), str) or not deed["event_id"]
                    or not isinstance(deed.get("result"), str) or not deed["result"]
                    or (deed.get("choice_id") is not None and not isinstance(deed["choice_id"], str))
                    or (event_ids is not None and deed["event_id"] not in event_ids)
                ):
                    raise ContentError(f"自创血脉功业 {deed['id']} 的历史事件引用不合法")
            else:
                key = (kind, deed["id"])
                if not nonnegative_integer(deed.get("cap")) or deed["cap"] <= 0:
                    raise ContentError(f"自创血脉功业 {deed['id']} 的记录上限必须是正整数")
            if key in deed_keys:
                raise ContentError(f"自创血脉功业 {deed['id']} 与另一功业重复计数同一来源")
            deed_keys.add(key)

        signature_traits = settings.get("species_signature_traits", [])
        if not isinstance(signature_traits, list):
            raise ContentError("妖修 species_signature_traits 必须是数组")
        signature_pairs: set[tuple[str, str]] = set()
        for unlock in signature_traits:
            if not isinstance(unlock, dict) or set(unlock) != {"species_id", "trait_id", "minimum_realm"}:
                raise ContentError("妖修种族特质解锁必须且只能声明 species_id、trait_id 与 minimum_realm")
            species_id, trait_id = str(unlock["species_id"]), str(unlock["trait_id"])
            minimum_realm = unlock["minimum_realm"]
            pair = (species_id, trait_id)
            if (
                species_id not in species or trait_id not in BLOODLINE_TRAIT_REGISTRY
                or not isinstance(minimum_realm, int) or isinstance(minimum_realm, bool)
                or not 0 <= minimum_realm <= 12 or pair in signature_pairs
            ):
                raise ContentError(f"妖修种族特质解锁不合法：{species_id}/{trait_id}")
            signature_pairs.add(pair)

        species_trait_pools = settings.get("species_trait_pools", {})
        try:
            validate_rule_catalog()
        except ValueError as error:
            raise ContentError(f"妖修复合血脉规则库非法：{error}") from error
        if not isinstance(species_trait_pools, dict) or set(species_trait_pools) != set(species):
            raise ContentError("妖修 species_trait_pools 必须为每个本源种定义独立血脉库")
        pooled_traits: set[str] = set()
        for species_id, trait_ids in species_trait_pools.items():
            if (
                not isinstance(trait_ids, list) or len(trait_ids) < 13
                or len(trait_ids) != len(set(trait_ids))
            ):
                raise ContentError(f"妖修 {species_id} 血脉库必须至少包含 13 项不重复特质")
            for trait_id in map(str, trait_ids):
                definition = BLOODLINE_TRAIT_REGISTRY.get(trait_id)
                if (
                    not definition or definition.get("pool_species") != species_id
                    or trait_id in pooled_traits
                ):
                    raise ContentError(f"妖修 {species_id} 血脉库引用未知、跨族或重复特质：{trait_id}")
                pooled_traits.add(trait_id)
        signature_trait_ids = {trait_id for _, trait_id in signature_pairs}
        if pooled_traits & signature_trait_ids:
            raise ContentError("妖修族群血脉库不得与永久种族特质重复")

        for species_id, definition in species.items():
            base_id = definition.get("base_evolution_id")
            if not definition.get("name") or base_id not in evolutions:
                raise ContentError(f"妖修本源种 {species_id} 缺少名称或基础形态")
            if evolutions[base_id].get("species") != species_id:
                raise ContentError(f"妖修本源种 {species_id} 的基础形态属于其他谱系")
        for node_id, node in evolutions.items():
            profile = node.get("profile", {})
            parents = node.get("parents", [])
            if (
                node.get("species") not in species or not node.get("name")
                or not isinstance(parents, list) or len(parents) != len(set(parents))
                or set(profile) != stat_keys
                or any(not isinstance(value, (int, float)) or not 0.5 <= float(value) <= 1.5 for value in profile.values())
                or not 0 <= int(node.get("realm_index", -1)) <= 12
                or int(node.get("monster_qi_level", 0)) < 0
                or int(node.get("lifespan_gain", 0)) < 0
                or not 0.05 <= float(node.get("travel_multiplier", 1.0)) <= 3.0
            ):
                raise ContentError(f"妖修进化节点 {node_id} 的谱系、六维、境界或生存数值不合法")
            if any(parent not in evolutions or evolutions[parent].get("species") != node.get("species") for parent in parents):
                raise ContentError(f"妖修进化节点 {node_id} 引用了不存在或跨谱系的父节点")
            if any(int(evolutions[parent].get("realm_index", -1)) >= int(node.get("realm_index", 0)) for parent in parents):
                raise ContentError(f"妖修进化节点 {node_id} 的父节点必须来自更低境界")
            if int(node.get("realm_index", 0)) == 0 and parents:
                raise ContentError(f"妖修基础节点 {node_id} 不应拥有父节点")
            if int(node.get("realm_index", 0)) > 0 and not parents:
                raise ContentError(f"妖修进化节点 {node_id} 缺少父节点")
            if set(node.get("traits", [])) - set(BLOODLINE_TRAIT_REGISTRY):
                raise ContentError(f"妖修进化节点 {node_id} 引用了未知血脉特质")
            if set(node.get("traits", [])) & pooled_traits:
                raise ContentError(f"妖修进化节点 {node_id} 不得直接占用随机族群血脉库")
            if not valid_requirement(node.get("requirements", {})):
                raise ContentError(f"妖修进化节点 {node_id} 使用了不合法的条件表达式")
        for node_id, node in evolutions.items():
            children = [child for child in evolutions.values() if node_id in child.get("parents", [])]
            if children and not any(
                int(child["realm_index"]) == int(node["realm_index"]) + 1
                and int(child.get("monster_qi_level", 0)) == 0
                and not child.get("requirements")
                for child in children
            ):
                raise ContentError(f"妖修进化节点 {node_id} 缺少不会卡死玩家的下一境界稳态进化")
        return species, evolutions, settings

    @staticmethod
    def _build_story_combat_scenarios(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
        rows = document.get("scenarios", [])
        if not isinstance(rows, list) or not rows:
            raise ContentError("剧情战斗编队表不得为空")
        result: dict[str, dict[str, Any]] = {}
        natural_terrains = {"狭窄", "开阔", "险要"}
        artificial_conditions = {"禁空", "禁神识", "大阵"}
        for source in rows:
            row = dict(source)
            event_id = str(row.pop("event_id", ""))
            enemies = row.get("enemy_members", [])
            allies = row.get("player_allies", [])
            if not event_id or event_id in result:
                raise ContentError(f"剧情战斗事件 ID 缺失或重复：{event_id}")
            if not row.get("target_name") or row.get("natural_terrain") not in natural_terrains:
                raise ContentError(f"剧情战斗 {event_id} 缺少目标名或自然场地不合法")
            if any(value not in artificial_conditions for value in row.get("artificial_conditions", [])):
                raise ContentError(f"剧情战斗 {event_id} 包含未知人工场地属性")
            if not enemies or any(
                not member.get("name") or float(member.get("share", 0)) <= 0
                or float(member.get("full_power_multiplier", 1)) <= 0
                for member in enemies
            ):
                raise ContentError(f"剧情战斗 {event_id} 的敌方编队不完整")
            if abs(sum(float(member["share"]) for member in enemies) - 1.0) > 1e-6:
                raise ContentError(f"剧情战斗 {event_id} 的敌方战力占比总和必须为 1")
            if any(
                not ally.get("name") or float(ally.get("power_ratio", 0)) <= 0
                or float(ally.get("full_power_multiplier", 1)) <= 0
                for ally in allies
            ):
                raise ContentError(f"剧情战斗 {event_id} 的友方编队不完整")
            if not row.get("story_beats") or any(not str(beat).strip() for beat in row["story_beats"]):
                raise ContentError(f"剧情战斗 {event_id} 至少需要一条逐轮剧情")
            result[event_id] = row
        return result

    @staticmethod
    def _realm(row: dict[str, Any]) -> RealmDef:
        value = dict(row)
        lifespan = value.get("lifespan")
        value["lifespan"] = tuple(lifespan) if lifespan is not None else None
        try:
            return RealmDef(**value)
        except TypeError as error:
            raise ContentError(f"境界字段不合法：{error}") from error

    @staticmethod
    def _build_roots(spec: dict[str, Any], affinity_names: dict[str, str]) -> dict[str, dict[str, Any]]:
        roots = {row["id"]: {key: value for key, value in row.items() if key != "id"} for row in spec.get("fixed", [])}
        elements = [key for key in ("metal", "wood", "water", "fire", "earth") if key in affinity_names]
        for family in spec.get("five_element_families", []):
            for count in family["counts"]:
                for group in combinations(elements, count):
                    key = "_".join(group) if count < 5 else "all"
                    label = "·".join(affinity_names[element] for element in group)
                    if family["prefix"] == "supreme":
                        name = f"极品{label}灵根"
                    elif family["prefix"] == "pseudo" and count == 5:
                        name = "伪灵根（五行俱全）"
                    else:
                        name = f"{family['tier']}（{label}）"
                    roots[f"{family['prefix']}_{key}"] = {
                        "name": name, "tier": family["tier"],
                        "efficiency": float(family["efficiencies"][str(count)]),
                        "elements": list(group), "creation": True,
                    }
        acquired = spec.get("acquired", {})
        for affinity in ("metal", "wood", "water", "fire", "earth", "wind", "thunder", "yin", "yang"):
            affinity_name = affinity_names[affinity]
            mutated = affinity not in elements
            roots[f"acquired_{affinity}"] = {
                "name": f"后天{'变异' if mutated else '补'}灵根（{affinity_name}）",
                "tier": "后天变异灵根" if mutated else "后天灵根",
                "efficiency": float(acquired["mutated_efficiency" if mutated else "element_efficiency"]),
                "elements": [affinity], "creation": bool(acquired.get("creation", False)),
            }
        return roots

    @staticmethod
    def _build_factions(document: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        definitions: dict[str, dict[str, Any]] = {}
        templates: dict[str, list[dict[str, Any]]] = {}
        for row in document.get("factions", []):
            faction_id = row["id"]
            definitions[faction_id] = {key: value for key, value in row.items() if key not in {"id", "npcs"}}
            templates[faction_id] = list(row.get("npcs", []))
        return definitions, templates

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        duplicate_keys: list[str] = []

        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    duplicate_keys.append(key)
                result[key] = value
            return result

        try:
            value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
        except FileNotFoundError as error:
            raise ContentError(f"缺少内容文件：{path.name}") from error
        except json.JSONDecodeError as error:
            raise ContentError(f"内容文件 {path.name} 不是有效 JSON：{error}") from error
        if duplicate_keys:
            raise ContentError(f"内容文件 {path.name} 存在重复字段：{duplicate_keys[0]}")
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise ContentError(f"内容文件 {path.name} 的 schema_version 必须为 1")
        return value

    @staticmethod
    def _validate_quick_starts(
        presets: list[dict[str, Any]], items: dict[str, Item], techniques: dict[str, Technique],
        realms: tuple[RealmDef, ...], roots: dict[str, dict[str, Any]], paths: dict[str, str],
        races: dict[str, dict[str, Any]],
    ) -> None:
        required_ids = {"core", "demonic_core", "ghost_core", "nascent", "spirit", "void", "integration", "mahayana", "true_immortal"}
        if {str(entry.get("id", "")) for entry in presets} != required_ids:
            raise ContentError("快速开局必须覆盖正统修仙七档、魔界魔丹与地狱界鬼修预设")
        if not all(bool(entry.get("enabled")) for entry in presets):
            raise ContentError("九项快速开局预设均应处于开放状态")
        for entry in presets:
            if not entry.get("enabled"):
                continue
            if entry.get("spirit_root") not in roots or entry.get("path") not in paths:
                raise ContentError(f"快速开局 {entry['id']} 的灵根或道路不存在")
            if entry.get("race") not in races or entry.get("world") not in {"human", "demon", "spirit", "true_demon", "hell", "celestial", "asura"}:
                raise ContentError(f"快速开局 {entry['id']} 的种族或世界不存在")
            if not 1 <= int(entry.get("layer", 0)) <= realms[int(entry["realm_index"])].layers:
                raise ContentError(f"快速开局 {entry['id']} 的层数不合法")
            technique_ids = [entry.get("main_technique"), entry.get("support_technique"), *entry.get("combat_techniques", [])]
            if any(technique_id not in techniques for technique_id in technique_ids):
                raise ContentError(f"快速开局 {entry['id']} 引用了不存在的功法")
            if any(item.get("id") not in items or int(item.get("quantity", 0)) <= 0 for item in entry.get("inventory", [])):
                raise ContentError(f"快速开局 {entry['id']} 引用了不存在或数量错误的物品")
            if not isinstance(entry.get("story_flags", []), list) or any(
                not isinstance(flag, str) or not flag for flag in entry.get("story_flags", [])
            ):
                raise ContentError(f"快速开局 {entry['id']} 的既有剧情标记不合法")
            if int(entry["realm_index"]) >= 6:
                five = {"metal", "wood", "water", "fire", "earth"}
                if entry.get("world") not in {"spirit", "celestial"} or not five <= set(entry.get("additional_roots", [])):
                    raise ContentError(f"快速开局 {entry['id']} 必须出生于对应上界并补齐五行")

    @staticmethod
    def _index_models(document: dict[str, Any], field: str, model: type[Item] | type[Technique] | type[SectNpc]) -> dict[str, Any]:
        rows = document.get(field)
        if not isinstance(rows, list):
            raise ContentError(f"内容字段 {field} 必须是数组")
        indexed: dict[str, Any] = {}
        for row in rows:
            if not isinstance(row, dict) or not row.get("id"):
                raise ContentError(f"{field} 中存在缺少 id 的条目")
            if row["id"] in indexed:
                raise ContentError(f"{field} 中存在重复 id：{row['id']}")
            try:
                indexed[row["id"]] = model(**row)
            except TypeError as error:
                raise ContentError(f"{field}/{row['id']} 字段不合法：{error}") from error
        return indexed

    @staticmethod
    def _validate(
        items: dict[str, Item], techniques: dict[str, Technique],
        transformations: dict[str, TransformationForm], market_goods: tuple[dict[str, Any], ...],
        realms: tuple[RealmDef, ...], root_definitions: dict[str, dict[str, Any]],
        faction_definitions: dict[str, dict[str, Any]], world_ids: set[str],
    ) -> None:
        affinities = {"neutral", "sex", "five_elements", "metal", "wood", "water", "fire", "earth", "wind", "thunder", "yin", "yang"}
        paths = {"dao", "demonic", "ghost", "monster", "buddhist", "confucian"}
        allowed_sources = {"spirit", "demon", "monster", "yin"}

        def valid_requirement(requirement: Any) -> bool:
            if not isinstance(requirement, dict) or len(requirement) != 1:
                return False
            if "all" in requirement or "any" in requirement:
                key = "all" if "all" in requirement else "any"
                children = requirement[key]
                return isinstance(children, list) and bool(children) and all(valid_requirement(child) for child in children)
            if "not" in requirement:
                return valid_requirement(requirement["not"])
            leaf = requirement.get("source")
            return bool(
                isinstance(leaf, dict)
                and set(leaf) == {"id", "op", "level"}
                and leaf["id"] in allowed_sources
                and leaf["op"] in {">=", ">", "<=", "<", "==", "!="}
                and isinstance(leaf["level"], int)
                and leaf["level"] >= 0
            )
        for item in items.values():
            if item.breakthrough_bonus < 0 or item.trial_restore_hp < 0 or item.trial_restore_mp < 0:
                raise ContentError(f"物品 {item.id} 的突破或渡劫恢复数值不得为负")
            if item.permanent_intrinsic_hp_bonus < 0 or item.permanent_intrinsic_mp_bonus < 0:
                raise ContentError(f"物品 {item.id} 的永久本体增益不得为负")
            if (
                item.permanent_intrinsic_hp_bonus > 0 or item.permanent_intrinsic_mp_bonus > 0
            ) and not {"pill", "permanent_intrinsic"} <= set(item.tags):
                raise ContentError(f"永久本体丹药 {item.id} 必须标记 pill 与 permanent_intrinsic")
            if not 0 <= item.conception_bonus < 1:
                raise ContentError(f"物品 {item.id} 的下一次孕育概率加成必须位于 [0, 1) 区间")
            if item.conception_bonus > 0 and not {"pill", "conception"} <= set(item.tags):
                raise ContentError(f"孕育丹药 {item.id} 必须同时标记 pill 与 conception")
            if not 0 < item.erosion_growth_multiplier <= 1 or not 0 < item.cultivation_efficiency_multiplier <= 1:
                raise ContentError(f"物品 {item.id} 的附灵倍率必须位于 (0, 1] 区间")
            if (
                item.erosion_growth_multiplier != 1 or item.cultivation_efficiency_multiplier != 1
            ) and "ghost_vessel" not in item.tags:
                raise ContentError(f"附灵专属载体 {item.id} 必须标记 ghost_vessel")
            if not 0 <= item.tribulation_damage_reduction < 1 or item.passive_breakthrough_bonus < 0:
                raise ContentError(f"物品 {item.id} 的减伤或常驻突破加成不合法")
            if item.passive_breakthrough_bonus > 0 and item.passive_breakthrough_max_realm is None:
                raise ContentError(f"常驻突破法宝 {item.id} 缺少适用境界上限")
            if item.breakthrough_bonus > 0:
                if not item.breakthrough_scope or not item.breakthrough_scope.startswith(("major:", "minor:")):
                    raise ContentError(f"突破丹药 {item.id} 缺少合法 breakthrough_scope")
                try:
                    source_realm = int(item.breakthrough_scope.split(":", 1)[1])
                except ValueError as error:
                    raise ContentError(f"突破丹药 {item.id} 的境界范围不合法") from error
                scope_type = item.breakthrough_scope.split(":", 1)[0]
                upper = len(realms) - 2 if scope_type == "major" else len(realms) - 1
                if not 1 <= source_realm <= upper:
                    raise ContentError(f"突破丹药 {item.id} 的境界范围越界")
            if item.transformation_form_id is not None and (
                item.transformation_form_id not in transformations
                or item.transformation_source not in {"真灵之血", "精魄", "元神"}
                or not 0 < item.transformation_purity <= 1
                or "true_spirit_material" not in item.tags
            ):
                raise ContentError(f"真灵素材 {item.id} 的形态、来源或纯度不合法")
        for technique in techniques.values():
            if technique.element not in affinities or technique.path not in paths:
                raise ContentError(f"功法 {technique.id} 的流派或属性未知")
            required = (
                technique.opportunity_bonus, technique.hp_bonus,
                technique.mp_bonus, technique.combat_bonus,
            )
            if any(value <= 0 for value in required) or technique.karma_multiplier <= 0:
                raise ContentError(f"功法 {technique.id} 必须具有四项正数属性和正数因果倍率")
            if technique.category not in {"spiritual", "body", "divine_sense", "transformation"}:
                raise ContentError(f"功法 {technique.id} 的类型未知")
            if technique.category == "body" and technique.element != "neutral":
                raise ContentError(f"炼体功法 {technique.id} 必须对所有灵根开放")
            if technique.category == "body" and (
                technique.body_breakthrough_bonus <= 0
                or not 1 <= int(technique.body_bonus_max_layer or 0) <= 100
            ):
                raise ContentError(f"炼体功法 {technique.id} 缺少合法的突破加成范围")
            if technique.category == "divine_sense" and technique.divine_sense_bonus <= 0:
                raise ContentError(f"神识功法 {technique.id} 缺少合法的神识修炼加成")
            if technique.category == "transformation" and (
                technique.transformation_capacity <= 0
                or technique.transformation_space <= 0
                or technique.transformation_space > technique.transformation_capacity
                or bool(technique.initial_transformations)
            ):
                raise ContentError(f"变身功法 {technique.id} 只能声明容量与空间，不能预设变身")
            if technique.requires_immortal_power and not 0 < technique.immortal_power_cost < 1:
                raise ContentError(f"仙家功法 {technique.id} 缺少合法的仙灵力消耗")
            if not technique.requires_immortal_power and technique.immortal_power_cost != 0:
                raise ContentError(f"普通功法 {technique.id} 不能声明仙灵力消耗")
            if not 0 <= int(technique.required_body_training) <= 100:
                raise ContentError(f"功法 {technique.id} 的炼体门槛必须位于零至一百层")
            if int(technique.possession_limit_bonus) < 0:
                raise ContentError(f"功法 {technique.id} 的夺舍次数加成不能为负数")
            if (
                not technique.sources
                or set(technique.sources) - allowed_sources
                or any(weight <= 0 for weight in technique.sources.values())
                or abs(sum(technique.sources.values()) - 1.0) > 1e-9
            ):
                raise ContentError(f"功法 {technique.id} 的先天源或利用权重不合法")
            if not valid_requirement(technique.combat_requirements):
                raise ContentError(f"功法 {technique.id} 的战斗气等级门槛不合法")
        stat_keys = {"might", "guard", "mobility", "sense", "sustain", "breach"}
        for form in transformations.values():
            if set(form.stat_multipliers) != stat_keys or any(value <= 0 for value in form.stat_multipliers.values()):
                raise ContentError(f"变身 {form.id} 必须完整声明六项正数倍率")
            if (
                not 1 <= form.realm_index <= 12 or form.layer <= 0
                or len(form.traits) != len(form.trait_descriptions)
                or len(form.traits) != len(form.trait_purity_requirements)
                or any(not 0 <= value <= 1 for value in form.trait_purity_requirements)
            ):
                raise ContentError(f"变身 {form.id} 的特质与说明数量不一致")
            if any(other not in transformations for other in form.incompatible_with):
                raise ContentError(f"变身 {form.id} 引用了不存在的互斥变身")
            if set(form.traits) - set(COMBAT_TRAIT_REGISTRY):
                raise ContentError(f"变身 {form.id} 引用了未知变身特质")
        seen_market_ids: set[tuple[str, str, int, str]] = set()
        for good in market_goods:
            kind = good.get("kind")
            content_id = good.get("content_id")
            tier = good.get("tier")
            world = good.get("world", "human")
            key = (str(kind), str(content_id), int(tier or 0), str(world))
            if world not in world_ids:
                raise ContentError(f"坊市货物世界标签不合法：{good}")
            if kind not in {"item", "technique"} or not isinstance(tier, int) or not 1 <= tier < len(realms):
                raise ContentError(f"坊市货物定义不合法：{good}")
            catalog = items if kind == "item" else techniques
            if content_id not in catalog:
                raise ContentError(f"坊市引用不存在的{kind}：{content_id}")
            if not isinstance(good.get("price"), int) or good["price"] <= 0:
                raise ContentError(f"坊市货物 {content_id} 的价格必须为正整数")
            if key in seen_market_ids:
                raise ContentError(f"坊市货物重复：{content_id}")
            seen_market_ids.add(key)
        expected_realms = (
            "mortal", "qi", "foundation", "core", "nascent", "spirit", "void", "integration", "mahayana",
            "true_immortal", "golden_immortal", "taiyi", "daluo",
        )
        if tuple(realm.id for realm in realms) != expected_realms:
            raise ContentError("境界顺序或境界 ID 不完整")
        if not root_definitions or any(root["efficiency"] < 0 for root in root_definitions.values()):
            raise ContentError("灵根定义为空或存在负数效率")
        expected_factions = {
            "tianjian", "wanmo", "puti", "taixuan", "wanlingshan", "xinghe",
            "blood_prison", "corpse_hall", "heaven_demon_palace", "myriad_soul_abyss", "black_sun_temple",
            "cloud_immortal_palace", "taiyi_pill_sect", "law_sea_pavilion",
            "asura_war_court", "blood_moon_palace", "annihilation_sea_sect",
            "ghost_passage_court", "forgetful_river_archive", "iron_tree_prison_sect",
        }
        if not expected_factions <= set(faction_definitions):
            raise ContentError("人界、魔界、灵界与真魔界宗门定义不完整")
        worlds = [definition.get("world") for definition in faction_definitions.values()]
        if (
            worlds.count("human") < 3 or worlds.count("spirit") < 3 or worlds.count("demon") < 2
            or worlds.count("true_demon") < 3 or worlds.count("celestial") < 3 or worlds.count("asura") < 3
            or worlds.count("hell") < 3
        ):
            raise ContentError("宗门数量必须覆盖人界、魔界、灵界、真魔界、地狱界、仙界与修罗界的既定下限")

    @staticmethod
    def _validate_systems(
        actions: dict[str, Any], world: dict[str, Any], market: dict[str, Any], factions: dict[str, Any],
        items: dict[str, Item], faction_definitions: dict[str, dict[str, Any]],
    ) -> None:
        required_actions = {"cultivate", "travel", "rest", "treasure", "commission", "befriend_neighbors", "hunt_beast", "spar", "slay"}
        if not required_actions <= set(actions):
            raise ContentError("年度行动定义不完整")
        for action_id, action in actions.items():
            if not action.get("name") or len(action.get("opportunity", [])) != 2:
                raise ContentError(f"年度行动 {action_id} 字段不完整")
            combat = action.get("combat")
            if combat and not combat.get("target_names"):
                raise ContentError(f"年度行动 {action_id} 的战斗目标配置不合法")
            if combat and combat.get("combat_type") == "beast" and (
                len(combat.get("power_multiplier", [])) != 2
                or combat["power_multiplier"][0] <= 0
                or combat["power_multiplier"][0] > combat["power_multiplier"][1]
                or
                float(combat.get("success_threshold", 0)) <= 1
                or len(combat.get("sha_qi_gain", [])) != 2
                or combat["sha_qi_gain"][0] <= 0
                or combat["sha_qi_gain"][0] > combat["sha_qi_gain"][1]
            ):
                raise ContentError(f"年度行动 {action_id} 的猎妖或煞气配置不合法")
            if combat and combat.get("combat_type") == "cultivator" and not combat.get("realm_offsets"):
                raise ContentError(f"年度行动 {action_id} 缺少修士境界分布")
        expectations = world.get("combat_expectations", {})
        expected_realms = {
            "mortal", "qi", "foundation", "core", "nascent", "spirit", "void", "integration", "mahayana",
            "true_immortal", "golden_immortal", "taiyi", "daluo",
        }
        if set(expectations) != expected_realms:
            raise ContentError("境界期望战斗力配置不完整")
        for realm_id, values in expectations.items():
            expected_fields = (
                {"value"} if realm_id in {"mortal", "true_immortal", "golden_immortal", "taiyi", "daluo"}
                else {"base", "layer_step"} if realm_id == "qi" else {"early", "middle", "late"}
            )
            if set(values) != expected_fields or any(not isinstance(value, (int, float)) or value <= 0 for value in values.values()):
                raise ContentError(f"境界 {realm_id} 的期望战斗力配置不合法")
        recommendations = world.get("player_combat_recommendations", {})
        if recommendations != expectations:
            raise ContentError("NPC 世界战力与玩家推荐战力必须使用同一套境界基准")
        auction = world.get("auction_system", {})
        required_auction_fields = {
            "trigger_chance_per_action", "notice_actions", "cooldown_actions", "npc_lot_count",
            "auction_rounds", "commission_rate", "starting_price_multiplier",
            "consignment_min_price_ratio", "consignment_max_price_ratio", "consignment_listing_fee_ratio",
            "minimum_increment_start_ratio", "minimum_increment_current_ratio", "npc_outbid_chance",
            "lower_world_tier_five_weight", "lower_world_higher_tier_weight",
            "black_market_buy_multiplier", "black_market_sell_ratio", "black_market_result_limit",
            "player_aliases", "bidder_aliases", "negotiation_affinity_gain",
            "private_trade_buy_multiplier", "private_trade_sell_multiplier",
            "private_trade_buy_affinity_gain",
            "private_trade_offer_count", "bargain_success_base", "bargain_affinity_factor",
            "bargain_buy_discount", "bargain_sell_bonus",
        }
        if not required_auction_fields <= set(auction):
            raise ContentError("拍卖会与黑市配置不完整")
        for field in ("trigger_chance_per_action", "commission_rate", "npc_outbid_chance"):
            if not 0 <= float(auction[field]) <= 1:
                raise ContentError(f"拍卖配置 {field} 必须位于 0 到 1")
        if not (
            0 < float(auction["consignment_min_price_ratio"]) <= 1
            < float(auction["consignment_max_price_ratio"])
            and 0 < float(auction["consignment_listing_fee_ratio"]) <= 1
        ):
            raise ContentError("寄拍限价或占位费配置不合法")
        if len(auction["starting_price_multiplier"]) != 2 or any(float(value) <= 0 for value in auction["starting_price_multiplier"]):
            raise ContentError("拍卖起拍价倍率配置不合法")
        if len(auction["player_aliases"]) < 4 or len(auction["bidder_aliases"]) < 7:
            raise ContentError("拍卖匿名身份或竞价者名录不足")
        spirit_field = world.get("spirit_field", {})
        required_field_keys = {
            "max_qing", "reclaim_base_stones", "reclaim_stone_growth", "reclaim_years_per_qing",
            "irrigation_mp_ratio", "irrigation_target_fraction", "irrigation_min_mp_ratio",
            "irrigation_max_mp_ratio", "irrigation_years_by_realm", "art_experience_base",
            "market_sell_ratio", "black_market_sell_ratio", "plants",
        }
        if not required_field_keys <= set(spirit_field) or int(spirit_field.get("max_qing", 0)) <= 0:
            raise ContentError("灵田配置不完整")
        for plant_id, plant in spirit_field["plants"].items():
            if plant.get("seed_id") not in items or float(plant.get("optimal_years", 0)) <= 0 or float(plant.get("base_value", 0)) <= 0:
                raise ContentError(f"灵植 {plant_id} 的种子、最佳药龄或价值配置不完整")
            if any(row.get("item_id") not in items or float(row.get("value", 0)) <= 0 for row in plant.get("harvest", {}).values()):
                raise ContentError(f"灵植 {plant_id} 的旧版收获物配置不合法")
        if set(spirit_field["irrigation_years_by_realm"]) != {str(index) for index in range(13)}:
            raise ContentError("灵田催熟境界倍率配置不完整")
        stage_bonuses = world.get("stage_lifespan_bonus", {})
        if not {"foundation", "core", "nascent", "spirit"} <= set(stage_bonuses):
            raise ContentError("筑基至化神的阶段延寿配置不完整")
        if float(world.get("qi_mastery", {}).get("experience_base", 0)) <= 0:
            raise ContentError("气经验等级曲线必须配置正数 experience_base")
        monster_cultivation = world.get("monster_cultivation", {})
        if (
            float(monster_cultivation.get("lifespan_multiplier", 0)) < 1
            or float(monster_cultivation.get("body_training_multiplier", 0)) < 1
        ):
            raise ContentError("妖修寿元与炼体速度倍率不得低于普通修士")
        for realm_id, stages in stage_bonuses.items():
            if set(stages) != {"middle", "late"}:
                raise ContentError(f"境界 {realm_id} 的阶段延寿必须同时定义中期与后期")
            if any(
                len(value) != 2 or value[0] <= 0 or value[0] > value[1]
                for value in stages.values()
            ):
                raise ContentError(f"境界 {realm_id} 的阶段延寿区间不合法")
        relationship = world.get("relationship", {})
        acceptance = relationship.get("master_request_acceptance", {})
        if int(relationship.get("max_disciples", 0)) <= 0 or set(acceptance) != {"item", "technique"}:
            raise ContentError("师徒系统配置不完整")
        if any(not isinstance(chance, (int, float)) or not 0 <= chance <= 1 for chance in acceptance.values()):
            raise ContentError("师父请求接受率必须位于 0 到 1")
        chance = market.get("next_tier_chance")
        if not isinstance(chance, (int, float)) or not 0 <= chance <= 1:
            raise ContentError("坊市跨阶概率必须位于 0 到 1")
        if int(market.get("offer_count", 0)) <= 0 or set(market.get("commission_stones", {})) != {str(index) for index in range(1, 13)}:
            raise ContentError("坊市刷新或委托配置不完整")
        distribution = factions.get("recruitment_distribution", [])
        if not distribution or float(distribution[-1].get("upper", 0)) != 1.0:
            raise ContentError("宗门招募概率表必须覆盖完整概率区间")
        root_distribution = factions.get("npc_root_distribution", {})
        if set(root_distribution) != {str(index) for index in range(1, 9)}:
            raise ContentError("NPC 灵根分布必须覆盖练气至大乘")
        for realm_index, weights in root_distribution.items():
            if set(weights) != {"pseudo", "heavenly", "supreme", "mutated"}:
                raise ContentError(f"人界 NPC 境界 {realm_index} 的灵根类别不完整")
            if any(not isinstance(value, (int, float)) or value < 0 for value in weights.values()) or abs(sum(weights.values()) - 1.0) > 1e-9:
                raise ContentError(f"人界 NPC 境界 {realm_index} 的灵根权重必须为非负且总和为 1")
        cultivation = factions.get("npc_cultivation", {})
        rates = cultivation.get("progress_per_year", {})
        if set(rates) != {str(index) for index in range(1, 9)} or any(float(value) <= 0 for value in rates.values()):
            raise ContentError("NPC 修炼进度配置不完整")
        for field in ("threshold", "base_success", "root_success_scale", "failed_progress_retained", "spirit_breakthrough_chance", "human_ascension_chance"):
            if not isinstance(cultivation.get(field), (int, float)) or float(cultivation[field]) <= 0:
                raise ContentError(f"人界 NPC 修炼参数 {field} 必须为正数")
        time_units = world.get("time_units", {})
        if time_units != {"0": 1, "1": 1, "2": 1, "3": 1, "4": 5, "5": 10, "6": 20, "7": 50, "8": 100, "9": 500, "10": 500, "11": 500, "12": 500}:
            raise ContentError("境界时间单位配置不符合 1/5/10/20/50/100 年规则")
        conversion = world.get("immortal_power_conversion", {})
        if (
            int(conversion.get("time_unit_years", 0)) != 500
            or int(conversion.get("min_gap_units", 0)) < 10
            or int(conversion.get("stages", 0)) != 5
            or not 0 < float(conversion.get("base_chance", 0)) <= 1
            or not 0 < float(conversion.get("chance_per_unit", 0)) <= 1
        ):
            raise ContentError("仙灵力长期转化的时间、概率或阶段配置不合法")
        court = world.get("heavenly_court", {})
        office_ids = [row.get("id") for row in court.get("offices", [])]
        decree_ids = [row.get("id") for row in court.get("decrees", [])]
        law_ids = [row.get("id") for row in court.get("laws", [])]
        if (
            int(court.get("seat_count", 0)) != 49
            or int(court.get("term_units", 0)) != 7
            or int(court.get("decree_duration_units", 0)) != 5
            or office_ids != ["sun", "moon", "jupiter", "mars", "saturn", "venus", "mercury"]
            or len(decree_ids) != len(set(decree_ids)) or len(law_ids) != len(set(law_ids))
            or not {"wanted", "protect", "direct_appointment", "recommend_official"} <= set(decree_ids)
            or not {"universal_protection", "immortal_slaughter", "martial_gods",
                    "official_system", "assistant_officials"} <= set(law_ids)
            or set(court.get("grade_merit_thresholds", {})) != {str(index) for index in range(1, 9)}
        ):
            raise ContentError("天庭席位、七曜任期、决议、天条或官阶配置不合法")
        natal = world.get("natal_artifact", {})
        natal_materials = natal.get("materials", [])
        if (
            int(natal.get("minimum_realm", 0)) != 3
            or int(natal.get("max_level", 0)) < 10
            or not natal.get("slot_unlocks")
            or any(item_id not in items for item_id in natal.get("eligible_item_ids", []))
            or any(row.get("item_id") not in items for row in natal_materials)
            or len({row.get("item_id") for row in natal_materials}) != len(natal_materials)
            or any(not row.get("effect") and not row.get("combat_effect") for row in natal_materials)
        ):
            raise ContentError("本命法宝的境界、等级、槽位或材料配置不合法")
        combat_stats = {"might", "guard", "mobility", "sense", "sustain", "breach"}
        combat_traits = {
            "enemy_escape_lock", "player_debuff_immunity", "enemy_buff_dispel",
            "even_round_might_40", "odd_round_enemy_might_down_40",
        }
        for material in natal_materials:
            if not 3 <= int(material.get("minimum_realm", 0)) <= 12:
                raise ContentError("本命法宝材料的适用境界必须位于结丹至大罗")
            combat_effect = material.get("combat_effect", {})
            if any(
                set(combat_effect.get(field, {})) - combat_stats
                for field in ("player_stat_multipliers", "enemy_stat_multipliers")
            ):
                raise ContentError("本命法宝材料引用了未知战斗属性")
            if set(combat_effect.get("traits", [])) - combat_traits:
                raise ContentError("本命法宝材料引用了未知战斗特质")
        breakthrough = world.get("breakthrough", {})
        if set(breakthrough.get("major_base", {})) != {str(index) for index in range(1, 8)}:
            raise ContentError("大境界基础突破概率必须覆盖练气至合体")
        if set(breakthrough.get("minor_base", {})) != {str(index) for index in range(2, 9)}:
            raise ContentError("小境界基础突破概率必须覆盖筑基至大乘")
        all_chances = [
            float(value) for table in breakthrough.get("major_base", {}).values() for value in table.values()
        ] + [float(value) for value in breakthrough.get("minor_base", {}).values()]
        if any(not 0 < chance <= 1 for chance in all_chances):
            raise ContentError("突破基础概率必须位于 0 到 1")
        thunder = breakthrough.get("periodic_thunder", {})
        if len(thunder.get("strike_multipliers", [])) != 3 or int(thunder.get("interval_years", 0)) != 3000:
            raise ContentError("周期雷劫必须配置三道判定和三千年周期")
        required_worlds = {
            "human", "demon", "spirit", "true_demon", "phantom_underworld", "hell",
            "celestial", "asura", "nether", "reincarnation",
        }
        if not required_worlds <= set(world.get("world_names", {})):
            raise ContentError("界面名称配置不完整")
        profiles = world.get("world_profiles", {})
        if (
            not required_worlds <= set(profiles)
            or not set(profiles) <= set(world.get("world_names", {}))
            or any(profile.get("kind") != "world" for profile in profiles.values())
        ):
            raise ContentError("所有真实界面都必须具有独立的界面配置")
        qi_sources = {"spirit", "demon", "monster", "yin"}
        if any(
            set(profile.get("qi_concentrations", {})) != qi_sources
            or any(not isinstance(value, (int, float)) or value < 0 for value in profile["qi_concentrations"].values())
            for profile in profiles.values()
        ):
            raise ContentError("每个界面都必须完整配置非负的灵气、魔气、妖气与阴气浓度")
        routes = world.get("cultivation_routes", {})
        if set(routes) != {"orthodox", "demonic", "monster", "ghost"}:
            raise ContentError("多修炼道路的界面路线配置不完整")
        routed_paths = [path for route in routes.values() for path in route.get("paths", [])]
        expected_paths = {"dao", "demonic", "ghost", "monster", "buddhist", "confucian"}
        if set(routed_paths) != expected_paths or len(routed_paths) != len(set(routed_paths)):
            raise ContentError("每种主修道路必须且只能归属一条界面路线")
        start_worlds = world.get("start_worlds", {})
        if (
            set(start_worlds) != expected_paths
            or any(
                not worlds or worlds[0] != "human" or len(worlds) < 2
                or any(start_world not in profiles for start_world in worlds)
                for worlds in start_worlds.values()
            )
        ):
            raise ContentError("每种修炼道路都必须同时配置人界与本界开局")
        heavens = world.get("heavens_framework", {})
        if (
            heavens.get("kind") != "cross_world_system"
            or set(heavens.get("member_worlds", [])) != {"celestial", "asura", "nether", "reincarnation"}
        ):
            raise ContentError("诸天必须作为四个上界之上的跨界系统框架")
        if any(
            len(route.get("stages", [])) < 4
            or route["stages"][-1].get("system") != "heavens"
            or any(stage.get("world") not in profiles for stage in route["stages"][:-1])
            for route_id, route in routes.items()
        ):
            raise ContentError("普通路线须由三个真实界面、魔修路线须由四个真实界面通往诸天系统")
        path_distributions = factions.get("npc_path_distribution", {})
        if set(path_distributions) != set(faction_definitions):
            raise ContentError("宗门 NPC 功法流派分布不完整")
        for faction_id, weights in path_distributions.items():
            if abs(sum(float(value) for value in weights.values()) - 1.0) > 1e-9:
                raise ContentError(f"宗门 {faction_id} 的功法流派权重总和必须为 1")
        distributions_by_world = factions.get("recruitment_distribution_by_world", {})
        required_distribution_worlds = {
            "human", "spirit", "demon", "true_demon", "celestial", "asura",
            *(str(definition.get("world", "human")) for definition in faction_definitions.values()),
        }
        if not required_distribution_worlds <= set(distributions_by_world):
            raise ContentError("宗门招募概率必须分别配置人界、魔界、灵界、真魔界、仙界与修罗界")
        if any(not rows or float(rows[-1].get("upper", 0)) != 1.0 for rows in distributions_by_world.values()):
            raise ContentError("各世界宗门招募概率表必须覆盖完整概率区间")


def default_content_root() -> Path:
    source_root = Path(__file__).resolve().parent.parent
    if getattr(sys, "frozen", False):
        editable_content = Path(sys.executable).resolve().parent / "content"
        if editable_content.is_dir():
            return editable_content
        source_root = Path(getattr(sys, "_MEIPASS", source_root))
    return source_root / "content"


def default_extension_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


CONTENT = ContentRegistry.load(default_content_root(), default_extension_root())
CONTENT_DOCUMENTS = ContentRegistry.loaded_documents
EXTENSION_REPORT = ContentRegistry.extension_report
ITEM_CATALOG = CONTENT.items
TECHNIQUE_CATALOG = CONTENT.techniques
TRANSFORMATION_CATALOG = CONTENT.transformations
MARKET_GOODS = CONTENT.market_goods
REALMS = CONTENT.realms
PATH_NAMES = CONTENT.path_names
KARMA_FACTORS = CONTENT.karma_factors
AFFINITY_NAMES = CONTENT.affinity_names
ELEMENT_NAMES = {key: AFFINITY_NAMES[key] for key in ("metal", "wood", "water", "fire", "earth")}
MUTATED_NAMES = {key: AFFINITY_NAMES[key] for key in ("wind", "thunder", "yin", "yang")}
TECHNIQUE_ELEMENT_NAMES = {"neutral": "无属性", **AFFINITY_NAMES}
ROOT_DEFINITIONS = CONTENT.root_definitions
ROOT_NAMES = {key: value["name"] for key, value in ROOT_DEFINITIONS.items() if value["creation"]}
FACTION_DEFINITIONS = CONTENT.faction_definitions
FACTION_REWARDS = CONTENT.faction_rewards
FACTION_NPC_TEMPLATES = CONTENT.faction_npc_templates
ACTIONS = CONTENT.actions
MARKET_SETTINGS = CONTENT.market_settings
FACTION_SYSTEMS = CONTENT.faction_systems
WORLD_SYSTEMS = CONTENT.world_systems
RACE_DEFINITIONS = CONTENT.race_definitions
RACE_SYSTEMS = CONTENT.race_systems
WORLD_NPC_TEMPLATES = CONTENT.world_npc_templates
STORY_COMBAT_SCENARIOS = CONTENT.story_combat_scenarios
MONSTER_SPECIES = CONTENT.monster_species
MONSTER_EVOLUTIONS = CONTENT.monster_evolutions
MONSTER_BLOODLINE_SETTINGS = CONTENT.monster_bloodline_settings

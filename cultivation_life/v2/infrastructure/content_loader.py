from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any

from ..domain.definitions import (
    ExtensionDefinition,
    FactionDefinition,
    GameDefinitions,
    ItemDefinition,
    LocationDefinition,
    MarketGoodDefinition,
    QI_SOURCES,
    RealmDefinition,
    RootDefinition,
    TechniqueDefinition,
    StoryChoiceDefinition,
    StoryEffectDefinition,
    StoryEventDefinition,
    TransformationDefinition,
    WorldDefinition,
)
from .extension_loader import load_extension_documents, read_json_document


class V2ContentError(ValueError):
    pass


class V2ContentLoader:
    """Strict adapter from immutable V1 content documents to V2 definitions."""

    REQUIRED_FILES = (
        "world.json", "maps.json", "factions.json", "techniques.json",
        "items.json", "market.json", "transformations.json",
    )

    @classmethod
    def load(
        cls, directory: Path, *, project_root: Path | None = None,
    ) -> GameDefinitions:
        directory = Path(directory)
        documents = {name: cls._read(directory / name) for name in cls.REQUIRED_FILES}
        event_paths = [directory / "events.json", *sorted(directory.glob("*_events.json"))]
        for path in event_paths:
            if path.is_file():
                documents[path.name] = cls._read(path)
        documents, extensions = load_extension_documents(
            documents,
            Path(project_root) if project_root is not None else directory.parent,
            validator=lambda candidate: cls._build(candidate, ()),
        )
        return cls._build(documents, extensions)

    @classmethod
    def _build(
        cls,
        documents: dict[str, dict[str, Any]],
        extensions: tuple[ExtensionDefinition, ...],
    ) -> GameDefinitions:
        world_doc = documents["world.json"]
        maps_doc = documents["maps.json"]
        faction_doc = documents["factions.json"]
        technique_doc = documents["techniques.json"]
        item_doc = documents["items.json"]
        transformation_doc = documents["transformations.json"]
        market_doc = documents["market.json"]

        realms = tuple(cls._realm(row) for row in world_doc.get("realms", []))
        if not realms or len({realm.id for realm in realms}) != len(realms):
            raise V2ContentError("境界表为空或包含重复ID")
        paths = {
            str(path_id): str(definition["name"])
            for path_id, definition in dict(world_doc.get("paths", {})).items()
        }
        roots = cls._roots(dict(world_doc.get("roots", {})), dict(world_doc.get("affinities", {})))
        techniques = cls._techniques(technique_doc, paths)
        transformations = cls._transformations(transformation_doc, len(realms))
        items = cls._items(item_doc, transformations)
        market_goods = cls._market_goods(market_doc, items, techniques)
        worlds = cls._worlds(world_doc, maps_doc)
        factions = cls._factions(faction_doc, worlds)
        story_events = cls._story_events(documents, items, techniques, factions)
        faction_rewards = {
            str(reward_id): dict(reward)
            for reward_id, reward in dict(faction_doc.get("rewards", {})).items()
        }
        if not faction_rewards or any(
            not str(reward.get("name", "")) or not dict(reward.get("effect", {}))
            for reward in faction_rewards.values()
        ):
            raise V2ContentError("势力年度奖励定义无效")
        systems = dict(world_doc.get("systems", {}))
        time_units = {int(index): int(years) for index, years in dict(systems["time_units"]).items()}
        travel_speeds = {
            int(index): float(multiplier)
            for index, multiplier in dict(maps_doc["settings"]["travel_speed_by_realm"]).items()
        }
        expected_indexes = set(range(len(realms)))
        if set(time_units) != expected_indexes or set(travel_speeds) != expected_indexes:
            raise V2ContentError("行动时间与移动速度必须覆盖全部境界")
        start_worlds = {
            str(path): tuple(map(str, world_ids))
            for path, world_ids in dict(systems.get("start_worlds", {})).items()
        }
        for path, world_ids in start_worlds.items():
            if path not in paths or set(world_ids) - set(worlds):
                raise V2ContentError(f"开局世界引用无效：{path}")
        stage_bonus = {
            str(realm_id): {
                str(stage): (int(span[0]), int(span[1]))
                for stage, span in dict(stages).items()
            }
            for realm_id, stages in dict(systems.get("stage_lifespan_bonus", {})).items()
        }
        return GameDefinitions(
            realms=realms,
            roots=roots,
            paths=paths,
            techniques=techniques,
            worlds=worlds,
            factions=factions,
            faction_rewards=faction_rewards,
            items=items,
            transformations=transformations,
            market_goods=market_goods,
            market_settings=dict(market_doc.get("settings", {})),
            actions={str(key): dict(value) for key, value in dict(world_doc["actions"]).items()},
            time_units=time_units,
            travel_speeds=travel_speeds,
            start_worlds=start_worlds,
            breakthrough=dict(systems["breakthrough"]),
            stage_lifespan_bonus=stage_bonus,
            systems=systems,
            extensions=extensions,
            extension_documents={
                name: document
                for name, document in documents.items()
                if name not in cls.REQUIRED_FILES
            },
            story_events=story_events,
        )

    @staticmethod
    def _story_events(
        documents: dict[str, dict[str, Any]],
        items: dict[str, ItemDefinition],
        techniques: dict[str, TechniqueDefinition],
        factions: dict[str, FactionDefinition],
    ) -> dict[str, StoryEventDefinition]:
        result: dict[str, StoryEventDefinition] = {}
        queue_references: list[tuple[str, str]] = []
        for filename in sorted(
            name for name in documents
            if name == "events.json" or name.endswith("_events.json")
        ):
            document = documents[filename]
            rows = document.get("events", [])
            if not isinstance(rows, list):
                raise V2ContentError(f"事件文件 {filename} 缺少events数组")
            document_world = str(document.get("world", ""))
            for raw in rows:
                if not isinstance(raw, dict):
                    raise V2ContentError(f"事件文件 {filename} 包含非对象事件")
                event_id = str(raw.get("id", ""))
                if not event_id or event_id in result:
                    raise V2ContentError(f"事件ID缺失或重复：{event_id}")
                raw_choices = raw.get("choices", [])
                if not raw.get("title") or not isinstance(raw_choices, list) or not raw_choices:
                    raise V2ContentError(f"事件 {event_id} 缺少标题或选项")
                choices: list[StoryChoiceDefinition] = []
                choice_ids: set[str] = set()
                for raw_choice in raw_choices:
                    if not isinstance(raw_choice, dict):
                        raise V2ContentError(f"事件 {event_id} 包含非对象选项")
                    choice_id = str(raw_choice.get("id", ""))
                    if not choice_id or choice_id in choice_ids:
                        raise V2ContentError(f"事件 {event_id} 的选项ID缺失或重复")
                    choice_ids.add(choice_id)
                    effects: list[StoryEffectDefinition] = []
                    for raw_effect in raw_choice.get("effects", []):
                        if not isinstance(raw_effect, dict) or not raw_effect.get("type"):
                            raise V2ContentError(f"事件 {event_id} 包含无类型效果")
                        payload = {
                            str(key): value for key, value in raw_effect.items()
                            if key != "type"
                        }
                        kind = str(raw_effect["type"])
                        if kind in {"add_item", "remove_item"} and str(payload.get("item_id")) not in items:
                            raise V2ContentError(f"事件 {event_id} 引用未知物品")
                        if kind in {"learn_technique", "equip_technique"} and str(payload.get("technique_id")) not in techniques:
                            raise V2ContentError(f"事件 {event_id} 引用未知功法")
                        if kind == "join_faction" and str(payload.get("faction_id")) not in factions:
                            raise V2ContentError(f"事件 {event_id} 引用未知势力")
                        if kind == "queue_event":
                            queue_references.append((event_id, str(payload.get("event_id", ""))))
                        effects.append(StoryEffectDefinition(kind=kind, payload=payload))
                    choices.append(StoryChoiceDefinition(
                        id=choice_id,
                        text=str(raw_choice.get("text", choice_id)),
                        effects=tuple(effects),
                        conditions=dict(raw_choice.get("conditions", {})),
                        disabled_reason=str(raw_choice.get("disabled_reason", "当前条件不满足")),
                        result_text=str(raw_choice.get("result_text", "你做出了选择。")),
                    ))
                tags = list(map(str, raw.get("tags", [])))
                if document_world:
                    tags.append(f"world:{document_world}")
                result[event_id] = StoryEventDefinition(
                    id=event_id,
                    version=int(raw.get("version", 1)),
                    title=str(raw["title"]),
                    body=str(raw.get("body", "")),
                    category=str(raw.get("category", "story")),
                    tags=tuple(dict.fromkeys(tags)),
                    weight=float(raw.get("weight", 1)),
                    intent_weights={
                        str(key): float(value)
                        for key, value in dict(raw.get("intent_weights", {})).items()
                    },
                    repeat=str(raw.get("repeat", "repeatable")),
                    conditions=dict(raw.get("conditions", {})),
                    choices=tuple(choices),
                )
        for source_id, target_id in queue_references:
            if target_id not in result:
                raise V2ContentError(f"事件 {source_id} 排入未知后续事件：{target_id}")
        return result

    @staticmethod
    def _realm(row: dict[str, Any]) -> RealmDefinition:
        lifespan = row.get("lifespan")
        return RealmDefinition(
            id=str(row["id"]),
            name=str(row["name"]),
            layers=int(row["layers"]),
            base_power=float(row["base_power"]),
            opportunity_base=int(row["opportunity_base"]),
            lifespan=(int(lifespan[0]), int(lifespan[1])) if lifespan is not None else None,
            kill_threshold=float(row["kill_threshold"]),
        )

    @staticmethod
    def _roots(spec: dict[str, Any], affinities: dict[str, Any]) -> dict[str, RootDefinition]:
        rows: list[dict[str, Any]] = [dict(row) for row in spec.get("fixed", [])]
        elements = [element for element in ("metal", "wood", "water", "fire", "earth") if element in affinities]
        for family in spec.get("five_element_families", []):
            for count in family["counts"]:
                for group in combinations(elements, int(count)):
                    key = "_".join(group) if int(count) < 5 else "all"
                    label = "·".join(str(affinities[element]) for element in group)
                    if family["prefix"] == "supreme":
                        name = f"极品{label}灵根"
                    elif family["prefix"] == "pseudo" and int(count) == 5:
                        name = "伪灵根（五行俱全）"
                    else:
                        name = f"{family['tier']}（{label}）"
                    rows.append({
                        "id": f"{family['prefix']}_{key}",
                        "name": name,
                        "tier": family["tier"],
                        "efficiency": family["efficiencies"][str(count)],
                        "elements": list(group),
                        "creation": True,
                    })
        acquired = dict(spec.get("acquired", {}))
        for element in (*elements, "wind", "thunder", "yin", "yang"):
            mutated = element not in elements
            rows.append({
                "id": f"acquired_{element}",
                "name": f"后天{'变异' if mutated else '补'}灵根（{affinities[element]}）",
                "tier": "后天变异灵根" if mutated else "后天灵根",
                "efficiency": acquired["mutated_efficiency" if mutated else "element_efficiency"],
                "elements": [element],
                "creation": bool(acquired.get("creation", False)),
            })
        result = {
            str(row["id"]): RootDefinition(
                id=str(row["id"]),
                name=str(row["name"]),
                tier=str(row["tier"]),
                efficiency=float(row["efficiency"]),
                elements=tuple(map(str, row.get("elements", []))),
                creation=bool(row.get("creation", False)),
            )
            for row in rows
        }
        if len(result) != len(rows):
            raise V2ContentError("灵根表包含重复ID")
        return result

    @staticmethod
    def _techniques(document: dict[str, Any], paths: dict[str, str]) -> dict[str, TechniqueDefinition]:
        defaults = dict(document.get("source_defaults_by_path", {}))
        result: dict[str, TechniqueDefinition] = {}
        for source in document.get("techniques", []):
            row = dict(source)
            technique_id = str(row["id"])
            path = str(row["path"])
            sources = {
                str(key): float(value)
                for key, value in dict(row.get("sources") or defaults.get(path, {})).items()
            }
            if (
                technique_id in result or path not in paths
                or not sources or set(sources) - set(QI_SOURCES)
                or abs(sum(sources.values()) - 1.0) > 1e-9
            ):
                raise V2ContentError(f"功法定义无效：{technique_id}")
            result[technique_id] = TechniqueDefinition(
                id=technique_id,
                name=str(row["name"]),
                path=path,
                element=str(row["element"]),
                grade=int(row.get("grade", 1)),
                level=int(row.get("level", 1)),
                opportunity_bonus=float(row.get("opportunity_bonus", 0)),
                hp_bonus=float(row.get("hp_bonus", 0)),
                mp_bonus=float(row.get("mp_bonus", 0)),
                combat_bonus=float(row.get("combat_bonus", 0)),
                category=str(row.get("category", "spiritual")),
                sources=sources,
                body_breakthrough_bonus=float(row.get("body_breakthrough_bonus", 0)),
                body_bonus_max_layer=int(row.get("body_bonus_max_layer", 0)),
                divine_sense_bonus=float(row.get("divine_sense_bonus", 0)),
                transformation_capacity=int(row.get("transformation_capacity", 0)),
                transformation_space=int(row.get("transformation_space", 0)),
            )
        return result

    @staticmethod
    def _items(
        document: dict[str, Any], transformations: dict[str, TransformationDefinition],
    ) -> dict[str, ItemDefinition]:
        result: dict[str, ItemDefinition] = {}
        for source in document.get("items", []):
            row = dict(source)
            item_id = str(row["id"])
            if item_id in result:
                raise V2ContentError(f"物品ID重复：{item_id}")
            result[item_id] = ItemDefinition(
                id=item_id,
                name=str(row["name"]),
                description=str(row.get("description", "")),
                tags=tuple(map(str, row.get("tags", []))),
                combat_bonus=float(row.get("combat_bonus", 0)),
                hp_bonus=float(row.get("hp_bonus", 0)),
                mp_bonus=float(row.get("mp_bonus", 0)),
                opportunity_bonus=float(row.get("opportunity_bonus", 0)),
                transformation_form_id=(
                    str(row["transformation_form_id"])
                    if row.get("transformation_form_id") else None
                ),
                transformation_source=str(row.get("transformation_source", "")),
                transformation_purity=float(row.get("transformation_purity", 0)),
            )
            form_id = result[item_id].transformation_form_id
            if form_id is not None and (
                form_id not in transformations
                or not 0 < result[item_id].transformation_purity <= 1
            ):
                raise V2ContentError(f"真灵素材定义无效：{item_id}")
        if "spirit_stone" not in result or "currency" not in result["spirit_stone"].tags:
            raise V2ContentError("物品表缺少灵石货币定义")
        return result

    @staticmethod
    def _transformations(
        document: dict[str, Any], realm_count: int,
    ) -> dict[str, TransformationDefinition]:
        stats = {"might", "guard", "mobility", "sense", "sustain", "breach"}
        result: dict[str, TransformationDefinition] = {}
        for source in document.get("forms", []):
            row = dict(source)
            form_id = str(row["id"])
            multipliers = {
                str(key): float(value)
                for key, value in dict(row.get("stat_multipliers", {})).items()
            }
            traits = tuple(map(str, row.get("traits", [])))
            descriptions = tuple(map(str, row.get("trait_descriptions", [])))
            requirements = tuple(map(float, row.get("trait_purity_requirements", [])))
            if not requirements:
                requirements = tuple(0.5 for _ in traits)
            realm_index = int(row.get("realm_index", 0))
            if (
                form_id in result or set(multipliers) != stats
                or any(value < 1 for value in multipliers.values())
                or len(traits) != len(descriptions) or len(traits) != len(requirements)
                or not 0 <= realm_index < realm_count
                or any(not 0 <= value <= 1 for value in requirements)
            ):
                raise V2ContentError(f"变化形态定义无效：{form_id}")
            result[form_id] = TransformationDefinition(
                id=form_id,
                name=str(row["name"]),
                description=str(row.get("description", "")),
                realm_index=realm_index,
                layer=int(row.get("layer", 1)),
                stat_multipliers=multipliers,
                traits=traits,
                trait_descriptions=descriptions,
                trait_purity_requirements=requirements,
                incompatible_with=tuple(map(str, row.get("incompatible_with", []))),
            )
        if not result:
            raise V2ContentError("变化形态表为空")
        for form in result.values():
            if set(form.incompatible_with) - set(result):
                raise V2ContentError(f"变化形态互斥引用无效：{form.id}")
        return result

    @staticmethod
    def _market_goods(
        document: dict[str, Any],
        items: dict[str, ItemDefinition],
        techniques: dict[str, TechniqueDefinition],
    ) -> tuple[MarketGoodDefinition, ...]:
        result: list[MarketGoodDefinition] = []
        seen: set[tuple[str, str, str, int]] = set()
        for source in document.get("goods", []):
            row = dict(source)
            kind = str(row["kind"])
            content_id = str(row["content_id"])
            world_id = str(row.get("world", "human"))
            tier = int(row["tier"])
            price = int(row["price"])
            key = (world_id, kind, content_id, tier)
            catalog = items if kind == "item" else techniques if kind == "technique" else None
            if key in seen or catalog is None or content_id not in catalog or tier < 1 or price <= 0:
                raise V2ContentError(f"坊市货物定义无效：{key}")
            seen.add(key)
            result.append(MarketGoodDefinition(
                world_id=world_id,
                kind=kind,
                content_id=content_id,
                tier=tier,
                price=price,
            ))
        return tuple(result)

    @staticmethod
    def _worlds(world_doc: dict[str, Any], maps_doc: dict[str, Any]) -> dict[str, WorldDefinition]:
        systems = dict(world_doc["systems"])
        profiles = dict(systems["world_profiles"])
        names = dict(systems["world_names"])
        map_worlds = dict(maps_doc["worlds"])
        if set(profiles) != set(map_worlds):
            raise V2ContentError("世界规则与地图世界不一致")
        result: dict[str, WorldDefinition] = {}
        for world_id, profile_source in profiles.items():
            profile = dict(profile_source)
            map_source = dict(map_worlds[world_id])
            locations = {
                str(row["id"]): LocationDefinition(
                    id=str(row["id"]),
                    name=str(row["name"]),
                    min_realm_index=int(row.get("min_realm_index", 0)),
                    failure=str(row.get("failure", "blocked")),
                    failure_reason=str(row.get("failure_reason", "")),
                    qi_gain_efficiencies={
                        source: float(dict(row["qi_gain_efficiencies"])[source])
                        for source in QI_SOURCES
                    },
                )
                for row in map_source.get("locations", [])
            }
            default = str(map_source["default"])
            if default not in locations:
                raise V2ContentError(f"世界缺少默认地点：{world_id}")
            graph: dict[str, list[tuple[str, int]]] = {location_id: [] for location_id in locations}
            for route in map_source.get("routes", []):
                first, second, years = str(route["from"]), str(route["to"]), int(route["years"])
                if first not in graph or second not in graph or first == second or years <= 0:
                    raise V2ContentError(f"世界包含无效路线：{world_id}")
                graph[first].append((second, years))
                graph[second].append((first, years))
            result[world_id] = WorldDefinition(
                id=world_id,
                name=str(names[world_id]),
                tier=int(profile["tier"]),
                enabled=bool(profile["enabled"]),
                qi_concentrations={
                    source: float(dict(profile["qi_concentrations"])[source])
                    for source in QI_SOURCES
                },
                default_location=default,
                locations=locations,
                routes={key: tuple(value) for key, value in graph.items()},
            )
        return result

    @staticmethod
    def _factions(document: dict[str, Any], worlds: dict[str, WorldDefinition]) -> dict[str, FactionDefinition]:
        result: dict[str, FactionDefinition] = {}
        for source in document.get("factions", []):
            row = dict(source)
            faction_id = str(row["id"])
            world_id = str(row["world"])
            if faction_id in result or world_id not in worlds:
                raise V2ContentError(f"势力定义无效：{faction_id}")
            result[faction_id] = FactionDefinition(
                id=faction_id,
                name=str(row["name"]),
                world_id=world_id,
                path=str(row.get("path", "")),
                allegiance_race=str(row.get("allegiance_race", "human")),
                description=str(row.get("description", "")),
                color=str(row.get("color", "")),
            )
        return result

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise V2ContentError(f"缺少V2内容文件：{path.name}")
        try:
            return read_json_document(path)
        except ValueError as error:
            raise V2ContentError(str(error)) from error
    MarketGoodDefinition,

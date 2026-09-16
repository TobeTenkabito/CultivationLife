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
    WorldDefinition,
)
from .extension_loader import load_extension_documents, read_json_document


class V2ContentError(ValueError):
    pass


class V2ContentLoader:
    """Strict adapter from immutable V1 content documents to V2 definitions."""

    REQUIRED_FILES = (
        "world.json", "maps.json", "factions.json", "techniques.json",
        "items.json", "market.json",
    )

    @classmethod
    def load(
        cls, directory: Path, *, project_root: Path | None = None,
    ) -> GameDefinitions:
        directory = Path(directory)
        documents = {name: cls._read(directory / name) for name in cls.REQUIRED_FILES}
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
        items = cls._items(item_doc)
        market_goods = cls._market_goods(market_doc, items, techniques)
        worlds = cls._worlds(world_doc, maps_doc)
        factions = cls._factions(faction_doc, worlds)
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
            items=items,
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
        )

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
            )
        return result

    @staticmethod
    def _items(document: dict[str, Any]) -> dict[str, ItemDefinition]:
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
            )
        if "spirit_stone" not in result or "currency" not in result["spirit_stone"].tags:
            raise V2ContentError("物品表缺少灵石货币定义")
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

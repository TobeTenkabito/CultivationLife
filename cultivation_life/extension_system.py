from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


REGISTRY_DOCUMENTS = (
    "items.json", "techniques.json", "transformations.json", "market.json",
    "world.json", "factions.json", "races.json", "world_npcs.json",
    "story_combat_scenarios.json",
)
CORE_DOCUMENTS = (*REGISTRY_DOCUMENTS, "maps.json")
OPTIONAL_DOCUMENTS = ("monster_bloodlines.json", "achievements.json", "crafting.json", "formations.json")
PACKAGE_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
PREFERENCES_FILE = "extension_preferences.json"


class ExtensionError(ValueError):
    pass


@dataclass(frozen=True)
class ExtensionPackage:
    id: str
    name: str
    version: str
    kind: str
    enabled: bool
    load_order: int
    requires: tuple[str, ...]
    description: str
    root: Path

    def public(self, status: str, error: str = "") -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "version": self.version,
            "kind": self.kind, "kind_name": "DLC" if self.kind == "dlc" else "MOD",
            "enabled": self.enabled, "load_order": self.load_order,
            "requires": list(self.requires), "description": self.description,
            "status": status, "error": error,
        }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExtensionError(f"JSON 含重复字段：{key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, json.JSONDecodeError, ExtensionError) as error:
        raise ExtensionError(f"{path.name} 无法读取：{error}") from error
    if not isinstance(value, dict):
        raise ExtensionError(f"{path.name} 顶层必须是对象")
    return value


def read_extension_preferences(project_root: Path) -> dict[str, bool]:
    """Read user-owned extension switches without mutating package manifests."""
    path = project_root / "data" / PREFERENCES_FILE
    if not path.is_file():
        return {}
    try:
        document = read_json(path)
        if document.get("schema_version") != 1 or not isinstance(document.get("enabled", {}), dict):
            return {}
        return {
            str(package_id): enabled for package_id, enabled in document["enabled"].items()
            if PACKAGE_ID.fullmatch(str(package_id)) and isinstance(enabled, bool)
        }
    except ExtensionError:
        return {}


def write_extension_preference(project_root: Path, package_id: str, enabled: bool) -> None:
    if not PACKAGE_ID.fullmatch(package_id):
        raise ExtensionError("扩展 ID 不合法")
    packages, _ = discover_packages(project_root)
    if package_id not in {package.id for package in packages}:
        raise ExtensionError("未找到该 DLC 或 MOD")
    preferences = read_extension_preferences(project_root)
    preferences[package_id] = bool(enabled)
    target = project_root / "data" / PREFERENCES_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"schema_version": 1, "enabled": preferences}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


def base_documents(content_root: Path) -> dict[str, dict[str, Any]]:
    documents = {name: read_json(content_root / name) for name in REGISTRY_DOCUMENTS}
    maps_path = content_root / "maps.json"
    if maps_path.is_file():
        documents[maps_path.name] = read_json(maps_path)
    achievements_path = content_root / "achievements.json"
    if achievements_path.is_file():
        documents[achievements_path.name] = read_json(achievements_path)
    crafting_path = content_root / "crafting.json"
    if crafting_path.is_file():
        documents[crafting_path.name] = read_json(crafting_path)
    formations_path = content_root / "formations.json"
    if formations_path.is_file():
        documents[formations_path.name] = read_json(formations_path)
    for path in sorted(content_root.glob("*_events.json")):
        documents[path.name] = read_json(path)
    events_path = content_root / "events.json"
    if events_path.is_file():
        documents[events_path.name] = read_json(events_path)
    invalid = next((name for name, document in documents.items() if document.get("schema_version") != 1), None)
    if invalid:
        raise ExtensionError(f"{invalid} 的 schema_version 必须为 1")
    return documents


def discover_packages(project_root: Path) -> tuple[list[ExtensionPackage], list[dict[str, Any]]]:
    packages: list[ExtensionPackage] = []
    report: list[dict[str, Any]] = []
    seen: set[str] = set()
    preferences = read_extension_preferences(project_root)
    for kind in ("dlc", "mods"):
        package_kind = "dlc" if kind == "dlc" else "mod"
        package_root = project_root / kind
        if not package_root.is_dir():
            continue
        for manifest_path in sorted(package_root.glob("*/manifest.json")):
            try:
                manifest = read_json(manifest_path)
                package_id = str(manifest.get("id", ""))
                if manifest.get("schema_version") != 1 or int(manifest.get("api_version", 0)) != 1:
                    raise ExtensionError("清单须声明 schema_version=1 与 api_version=1")
                if not PACKAGE_ID.fullmatch(package_id):
                    raise ExtensionError("扩展 ID 只能使用小写字母、数字、点、横线或下划线")
                if package_id in seen:
                    raise ExtensionError(f"扩展 ID 重复：{package_id}")
                if manifest.get("kind") != package_kind:
                    raise ExtensionError(f"清单 kind 必须为 {package_kind}")
                requires = tuple(map(str, manifest.get("requires", [])))
                if not isinstance(manifest.get("enabled"), bool) or any(not PACKAGE_ID.fullmatch(dep) for dep in requires):
                    raise ExtensionError("enabled 或 requires 字段不合法")
                package = ExtensionPackage(
                    id=package_id, name=str(manifest.get("name") or package_id),
                    version=str(manifest.get("version") or "0.0.0"), kind=package_kind,
                    enabled=preferences.get(package_id, manifest["enabled"]), load_order=int(manifest.get("load_order", 100)),
                    requires=requires, description=str(manifest.get("description") or ""),
                    root=manifest_path.parent,
                )
                packages.append(package)
                seen.add(package_id)
            except (ExtensionError, TypeError, ValueError) as error:
                report.append({
                    "id": manifest_path.parent.name, "name": manifest_path.parent.name,
                    "version": "?", "kind": package_kind,
                    "kind_name": "DLC" if package_kind == "dlc" else "MOD",
                    "enabled": False, "load_order": 0, "requires": [], "description": "",
                    "status": "error", "error": str(error),
                })
    packages.sort(key=lambda row: (0 if row.kind == "dlc" else 1, row.load_order, row.id))
    return packages, report


def _entry_key(value: Any) -> tuple[Any, ...] | None:
    if not isinstance(value, dict):
        return None
    if "id" in value:
        return ("id", str(value["id"]))
    if "event_id" in value:
        return ("event_id", str(value["event_id"]))
    if "kind" in value and "content_id" in value:
        return (
            "market", str(value.get("world", "human")), str(value["kind"]),
            str(value["content_id"]), int(value.get("tier", 0)),
        )
    return None


def merge_content(base: Any, overlay: Any) -> Any:
    """Deep merge JSON. Keyed object arrays merge by id; primitive arrays replace.

    `{ "$replace": value }` forces replacement. A keyed array entry with
    `"$delete": true` removes the matching entry.
    """
    if isinstance(overlay, dict) and set(overlay) == {"$replace"}:
        return copy.deepcopy(overlay["$replace"])
    if isinstance(base, dict) and isinstance(overlay, dict):
        result = copy.deepcopy(base)
        for key, value in overlay.items():
            if key == "schema_version":
                continue
            result[key] = merge_content(result[key], value) if key in result else copy.deepcopy(value)
        return result
    if isinstance(base, list) and isinstance(overlay, list):
        keyed = bool(base or overlay) and all(_entry_key(row) is not None for row in [*base, *overlay])
        if not keyed:
            return copy.deepcopy(overlay)
        result = copy.deepcopy(base)
        positions = {_entry_key(row): index for index, row in enumerate(result)}
        for row in overlay:
            key = _entry_key(row)
            if row.get("$delete") is True:
                if key in positions:
                    result.pop(positions[key])
                    positions = {_entry_key(item): index for index, item in enumerate(result)}
                continue
            clean = {name: value for name, value in row.items() if name != "$delete"}
            if key in positions:
                result[positions[key]] = merge_content(result[positions[key]], clean)
            else:
                positions[key] = len(result)
                result.append(copy.deepcopy(clean))
        return result
    return copy.deepcopy(overlay)


def package_documents(package: ExtensionPackage) -> dict[str, dict[str, Any]]:
    content_root = package.root / "content"
    if not content_root.is_dir():
        raise ExtensionError("扩展缺少 content 目录")
    documents: dict[str, dict[str, Any]] = {}
    for path in sorted(content_root.glob("*.json")):
        if path.name not in (*CORE_DOCUMENTS, *OPTIONAL_DOCUMENTS) and path.name != "events.json" and not path.name.endswith("_events.json"):
            raise ExtensionError(f"不支持的内容文件：{path.name}")
        document = read_json(path)
        if document.get("schema_version") != 1:
            raise ExtensionError(f"{path.name} 须声明 schema_version=1")
        if path.name == "achievements.json" and isinstance(document.get("achievements"), list):
            for achievement in document["achievements"]:
                if isinstance(achievement, dict):
                    achievement["source"] = {
                        "kind": package.kind, "id": package.id, "name": package.name,
                    }
        documents[path.name] = document
    if not documents:
        raise ExtensionError("扩展 content 目录中没有 JSON 内容")
    return documents


def load_extensions(
    content_root: Path,
    validator: Callable[[dict[str, dict[str, Any]]], Any],
    project_root: Path | None = None,
) -> tuple[Any, dict[str, dict[str, Any]], list[dict[str, Any]]]:
    active_documents = base_documents(content_root)
    registry = validator(copy.deepcopy(active_documents))
    packages, report = discover_packages(project_root or content_root.parent)
    enabled_ids = {package.id for package in packages if package.enabled}
    loaded_ids: set[str] = set()
    pending: list[ExtensionPackage] = []
    for package in packages:
        if not package.enabled:
            report.append(package.public("disabled"))
        elif package.kind == "dlc" and any(kinds.get(dependency) == "mod" for dependency in package.requires):
            report.append(package.public("error", "DLC 不能反向依赖 MOD"))
        else:
            missing = [dependency for dependency in package.requires if dependency not in enabled_ids]
            if missing:
                report.append(package.public("error", f"依赖未安装或未启用：{', '.join(missing)}"))
            else:
                pending.append(package)
    while pending:
        progressed = False
        for package in list(pending):
            if any(dependency not in loaded_ids for dependency in package.requires):
                continue
            try:
                candidate = copy.deepcopy(active_documents)
                for name, overlay in package_documents(package).items():
                    candidate[name] = merge_content(candidate.get(name, {"schema_version": 1}), overlay)
                candidate_registry = validator(copy.deepcopy(candidate))
            except Exception as error:
                report.append(package.public("error", str(error)))
            else:
                active_documents = candidate
                registry = candidate_registry
                loaded_ids.add(package.id)
                report.append(package.public("loaded"))
            pending.remove(package)
            progressed = True
        if not progressed:
            for package in pending:
                blocked = [dependency for dependency in package.requires if dependency not in loaded_ids]
                report.append(package.public("error", f"循环依赖或依赖加载失败：{', '.join(blocked)}"))
            pending.clear()
    report.sort(key=lambda row: (0 if row["kind"] == "dlc" else 1, int(row["load_order"]), row["id"]))
    return registry, active_documents, report

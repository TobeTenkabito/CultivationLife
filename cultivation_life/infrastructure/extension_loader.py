from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from ..domain.definitions import ExtensionDefinition


PACKAGE_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


class V2ExtensionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _Package:
    definition: ExtensionDefinition
    root: Path
    requires: tuple[str, ...]


def read_json_document(path: Path) -> dict[str, Any]:
    duplicates: list[str] = []

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                duplicates.append(key)
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (OSError, json.JSONDecodeError) as error:
        raise V2ExtensionError(f"{path.name} 无法读取：{error}") from error
    if duplicates:
        raise V2ExtensionError(f"{path.name} 包含重复键：{sorted(set(duplicates))}")
    if not isinstance(value, dict):
        raise V2ExtensionError(f"{path.name} 顶层必须为对象")
    if value.get("schema_version") != 1:
        raise V2ExtensionError(f"{path.name} 必须声明 schema_version=1")
    return value


def _entry_key(value: Any) -> tuple[Any, ...] | None:
    if not isinstance(value, dict):
        return None
    if "id" in value:
        return ("id", str(value["id"]))
    if "event_id" in value:
        return ("event_id", str(value["event_id"]))
    if "kind" in value and "content_id" in value:
        return (
            "market",
            str(value.get("world", "human")),
            str(value["kind"]),
            str(value["content_id"]),
            int(value.get("tier", 0)),
        )
    return None


def merge_documents(base: Any, overlay: Any) -> Any:
    if isinstance(overlay, dict) and set(overlay) == {"$replace"}:
        return copy.deepcopy(overlay["$replace"])
    if isinstance(base, dict) and isinstance(overlay, dict):
        result = copy.deepcopy(base)
        for key, value in overlay.items():
            if key == "schema_version":
                continue
            result[key] = merge_documents(result[key], value) if key in result else copy.deepcopy(value)
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
                result[positions[key]] = merge_documents(result[positions[key]], clean)
            else:
                positions[key] = len(result)
                result.append(copy.deepcopy(clean))
        return result
    return copy.deepcopy(overlay)


def _preferences(project_root: Path) -> dict[str, bool]:
    path = project_root / "data" / "extension_preferences.json"
    if not path.is_file():
        return {}
    try:
        document = read_json_document(path)
    except V2ExtensionError:
        return {}
    enabled = document.get("enabled", {})
    if not isinstance(enabled, dict):
        return {}
    return {
        str(package_id): value
        for package_id, value in enabled.items()
        if PACKAGE_ID.fullmatch(str(package_id)) and isinstance(value, bool)
    }


def _discover(project_root: Path) -> tuple[list[_Package], list[ExtensionDefinition]]:
    preferences = _preferences(project_root)
    packages: list[_Package] = []
    errors: list[ExtensionDefinition] = []
    seen: set[str] = set()
    for kind, folder in (("dlc", "dlc"), ("mod", "mods")):
        root = project_root / folder
        if not root.is_dir():
            continue
        for manifest_path in sorted(root.glob("*/manifest.json")):
            try:
                manifest = read_json_document(manifest_path)
                package_id = str(manifest.get("id", ""))
                if int(manifest.get("api_version", 0)) != 1:
                    raise V2ExtensionError("仅支持 api_version=1")
                if not PACKAGE_ID.fullmatch(package_id) or package_id in seen:
                    raise V2ExtensionError("扩展ID非法或重复")
                if manifest.get("kind") != kind:
                    raise V2ExtensionError(f"扩展 kind 必须为 {kind}")
                default_enabled = manifest.get("enabled")
                requires = tuple(map(str, manifest.get("requires", [])))
                if not isinstance(default_enabled, bool) or any(not PACKAGE_ID.fullmatch(dep) for dep in requires):
                    raise V2ExtensionError("enabled 或 requires 非法")
                definition = ExtensionDefinition(
                    id=package_id,
                    name=str(manifest.get("name") or package_id),
                    version=str(manifest.get("version") or "0.0.0"),
                    kind=kind,
                    enabled=preferences.get(package_id, default_enabled),
                    status="pending",
                    load_order=int(manifest.get("load_order", 100)),
                    description=str(manifest.get("description") or ""),
                )
                packages.append(_Package(definition, manifest_path.parent, requires))
                seen.add(package_id)
            except (V2ExtensionError, TypeError, ValueError) as error:
                errors.append(ExtensionDefinition(
                    id=manifest_path.parent.name,
                    name=manifest_path.parent.name,
                    version="?",
                    kind=kind,
                    enabled=False,
                    status="error",
                    load_order=0,
                    description="",
                    error=str(error),
                ))
    packages.sort(key=lambda package: (
        0 if package.definition.kind == "dlc" else 1,
        package.definition.load_order,
        package.definition.id,
    ))
    return packages, errors


def load_extension_documents(
    base_documents: dict[str, dict[str, Any]],
    project_root: Path,
    *,
    validator: Callable[[dict[str, dict[str, Any]]], None] | None = None,
) -> tuple[dict[str, dict[str, Any]], tuple[ExtensionDefinition, ...]]:
    documents = copy.deepcopy(base_documents)
    packages, report = _discover(project_root)
    enabled_ids = {package.definition.id for package in packages if package.definition.enabled}
    loaded_ids: set[str] = set()
    pending = list(packages)
    while pending:
        progressed = False
        for package in list(pending):
            definition = package.definition
            if not definition.enabled:
                report.append(replace(definition, status="disabled"))
                pending.remove(package)
                progressed = True
                continue
            missing = [dependency for dependency in package.requires if dependency not in enabled_ids]
            if missing:
                report.append(replace(
                    definition, status="error", error=f"依赖未启用：{', '.join(missing)}"
                ))
                pending.remove(package)
                progressed = True
                continue
            if any(dependency not in loaded_ids for dependency in package.requires):
                continue
            try:
                candidate = copy.deepcopy(documents)
                content_root = package.root / "content"
                if not content_root.is_dir():
                    raise V2ExtensionError("扩展缺少 content 目录")
                content_files = sorted(content_root.glob("*.json"))
                if not content_files:
                    raise V2ExtensionError("扩展没有JSON内容")
                for path in content_files:
                    overlay = read_json_document(path)
                    candidate[path.name] = merge_documents(
                        candidate.get(path.name, {"schema_version": 1}), overlay
                    )
                if validator is not None:
                    validator(candidate)
            except Exception as error:
                report.append(replace(definition, status="error", error=str(error)))
            else:
                documents = candidate
                loaded_ids.add(definition.id)
                report.append(replace(definition, status="loaded"))
            pending.remove(package)
            progressed = True
        if not progressed:
            for package in pending:
                definition = package.definition
                report.append(replace(
                    definition, status="error", error="循环依赖或依赖加载失败"
                ))
            break
    report.sort(key=lambda definition: (
        0 if definition.kind == "dlc" else 1,
        definition.load_order,
        definition.id,
    ))
    return documents, tuple(report)

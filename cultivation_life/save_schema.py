"""Save-document versions and pure, sequential migrations.

Release versions are independent. Schema 6 starts a new supported lineage;
schema 7 stores NPC identity references. Schemas 1--5 have no upgrade path.
Future schema changes register
one step per version here, before any GameState or runtime system is loaded.
"""
from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from .relationship_schema import migrate_relationships_v6

SAVE_SCHEMA_VERSION = 7
MIN_SAVE_SCHEMA_VERSION = 6
Migration = Callable[[dict[str, Any]], None]
# Key N transforms schema N into N + 1; the runner owns version advancement.
SAVE_MIGRATIONS: Mapping[int, Migration] = MappingProxyType({6: migrate_relationships_v6})


def schema_version(document: object) -> int:
    if not isinstance(document, dict) or type(document.get('version')) is not int:
        raise ValueError('存档结构版本无效')
    return document['version']


def migration_path(version: int, *, target: int = SAVE_SCHEMA_VERSION,
                   steps: Mapping[int, Migration] = SAVE_MIGRATIONS) -> tuple[Migration, ...]:
    if type(version) is not int:
        raise ValueError('存档结构版本无效')
    if version < MIN_SAVE_SCHEMA_VERSION:
        raise ValueError('该存档使用已停止支持的旧结构，请新建角色')
    if version > target:
        raise ValueError('此存档来自更高结构版本，请先更新游戏')
    path = []
    for current in range(version, target):
        if current not in steps:
            raise ValueError(f'缺少存档结构 {current} 到 {current + 1} 的迁移步骤')
        path.append(steps[current])
    return tuple(path)


def migrate_document(document: dict[str, Any], *, target: int = SAVE_SCHEMA_VERSION,
                     steps: Mapping[int, Migration] = SAVE_MIGRATIONS) -> dict[str, Any]:
    """Transform a copy only when necessary; failures never mutate the input.

Validate the entire path before running any step. Never infer a schema from
missing fields, call gameplay code, consume RNG, or write files in a migration.
"""
    version = schema_version(document)
    path = migration_path(version, target=target, steps=steps)
    if not path:
        return document
    result = copy.deepcopy(document)
    identity = result.get('id')
    for current, step in enumerate(path, start=version):
        step(result)
        if result.get('id') != identity or result.get('version') != current:
            raise RuntimeError('存档迁移步骤不得修改存档编号或结构版本')
        result['version'] = current + 1
    return result

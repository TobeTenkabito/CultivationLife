from __future__ import annotations
from typing import Any
from ...models import HistoryRecord
from ...models import Player
import copy
from ...runtime import now_iso
from .dependencies import FormationLoadoutsDependencies


def _formation_candidates(
    deps: FormationLoadoutsDependencies,
    player: Player,
    *,
    include_active: bool = True,
    include_ground: bool = True,
) -> list[dict[str, Any]]:
    deps.ensure_formation_state(player)
    dedicated = deps._formation_material_defs()
    shared = deps.formation_shared_definitions()
    candidates: list[dict[str, Any]] = []
    for instance in player.formation_materials:
        definition = dedicated.get(str(instance.get("material_id", "")))
        if definition:
            candidates.append(
                deps._formation_candidate(
                    instance, definition, "formation_material", instance["id"]
                )
            )
    for instance in player.crafting_materials:
        definition = next(
            (
                row
                for row in shared.values()
                if row.get("crafting_material_id") == instance.get("material_id")
            ),
            None,
        )
        if definition:
            candidates.append(
                deps._formation_candidate(
                    instance, definition, "crafting_material", instance["id"]
                )
            )
    for item in player.inventory:
        definitions = [
            row
            for row in shared.values()
            if row.get("item_id") == item.id
            or (row.get("plant_id") and row.get("plant_id") == item.plant_id)
        ]
        for definition in definitions:
            for index in range(max(0, int(item.quantity))):
                candidates.append(
                    deps._formation_candidate(
                        item.to_dict() | {"name": item.name},
                        definition,
                        "inventory",
                        f"inventory:{item.id}:{index}",
                    )
                    | {"inventory_item_id": item.id}
                )
    if include_active:
        for binding in player.formation_active_bindings:
            if binding:
                candidates.append(copy.deepcopy(binding) | {"occupied": True})
    if include_ground:
        for array in player.formation_ground_arrays:
            for binding in array.get("bindings", []):
                if binding:
                    candidates.append(
                        copy.deepcopy(binding)
                        | {
                            "occupied": True,
                            "locked": True,
                            "occupied_scope": "ground",
                            "ground_array_id": array["id"],
                            "source": f"镇于{array.get('owner_name', '阵域')} · {array.get('world')}/{array.get('location_id')}",
                        }
                    )
    candidates.sort(
        key=lambda row: (
            bool(row.get("occupied")),
            str(row.get("name")),
            str(row.get("id")),
        )
    )
    return candidates


def _nodes_from_candidate_ids(
    deps: FormationLoadoutsDependencies, player: Player, slot_ids: list[Any]
) -> tuple[list[dict[str, Any] | None], list[str | None]]:
    slots = list(slot_ids[:9])
    slots.extend([None] * (9 - len(slots)))
    candidates = {str(row["id"]): row for row in deps._formation_candidates(player)}
    used: set[str] = set()
    nodes: list[dict[str, Any] | None] = []
    definitions: list[str | None] = []
    for raw_id in slots:
        if not raw_id:
            nodes.append(None)
            definitions.append(None)
            continue
        candidate_id = str(raw_id)
        if candidate_id in used or candidate_id not in candidates:
            raise ValueError("九宫中的阵材实例不存在，或同一实例被重复放置")
        used.add(candidate_id)
        candidate = candidates[candidate_id]
        nodes.append(copy.deepcopy(candidate))
        definitions.append(str(candidate["definition_id"]))
    return nodes, definitions


def preview_formation(
    deps: FormationLoadoutsDependencies, game_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    game = deps._load(game_id)
    nodes, _ = deps._nodes_from_candidate_ids(
        game.player, list(payload.get("slots", []))
    )
    return deps.calculate_formation_profile(
        nodes,
        alpha=deps.formation_alpha(game.player),
        name=str(payload.get("name", "无名阵"))[:20] or "无名阵",
    )


def save_formation(
    deps: FormationLoadoutsDependencies, game_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    game = deps._load(game_id)
    if game.pending_event or not game.player.alive or game.player.imprisonment:
        raise ValueError("当前状态无法重排九宫")
    nodes, definitions = deps._nodes_from_candidate_ids(
        game.player, list(payload.get("slots", []))
    )
    profile = deps.calculate_formation_profile(
        nodes,
        alpha=deps.formation_alpha(game.player),
        name=str(payload.get("name", "无名阵"))[:20] or "无名阵",
    )
    if not profile.get("active"):
        raise ValueError("至少需要两份能够建立灵流关系的阵材才能成阵")
    player = game.player
    loadout_id = str(payload.get("loadout_id", ""))
    loadout = next(
        (row for row in player.formation_loadouts if row["id"] == loadout_id), None
    )
    name = str(payload.get("name", "")).strip()[:20] or (
        loadout["name"] if loadout else "无名阵"
    )
    if loadout:
        loadout.update(name=name, slots=definitions)
    else:
        player.formation_sequence += 1
        loadout = {
            "id": f"formation-{game.id}-{player.formation_sequence}",
            "name": name,
            "slots": definitions,
            "created_year": player.age,
        }
        player.formation_loadouts.append(loadout)
    should_activate = (
        bool(payload.get("activate", False))
        or player.active_formation_id == loadout["id"]
    )
    if should_activate:
        deps._activate_loadout(player, loadout)
    game.history.append(
        HistoryRecord(
            "SYS_FORMATION_SAVE",
            1,
            player.age,
            "推演九宫",
            loadout["id"],
            "saved",
            f"你将九宫灵流定名为“{name}”并保存阵法预设；预设只记录阵材类型，不复制任何实例。",
            {"formation_id": loadout["id"], "active": should_activate},
            ["system", "formation", "art:formation"],
        )
    )
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def activate_formation(
    deps: FormationLoadoutsDependencies, game_id: str, loadout_id: str
) -> dict[str, Any]:
    game = deps._load(game_id)
    if game.pending_event or not game.player.alive or game.player.imprisonment:
        raise ValueError("当前状态无法启阵")
    loadout = next(
        (row for row in game.player.formation_loadouts if row["id"] == loadout_id), None
    )
    if not loadout:
        raise ValueError("未找到这份阵法预设")
    deps._activate_loadout(game.player, loadout)
    profile = deps.active_formation_profile(game.player)
    game.history.append(
        HistoryRecord(
            "SYS_FORMATION_ACTIVATE",
            1,
            game.player.age,
            "九宫启阵",
            loadout_id,
            "activated",
            f"你以真实阵材实例展开“{loadout['name']}”，阵眼落在第 {profile['core_node']['position']} 宫。",
            {"formation_id": loadout_id, "occupied_count": profile["occupied_count"]},
            ["system", "formation", "art:formation"],
        )
    )
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def deactivate_formation(
    deps: FormationLoadoutsDependencies, game_id: str
) -> dict[str, Any]:
    game = deps._load(game_id)
    name = deps.active_formation_profile(game.player).get("name", "当前阵法")
    deps._release_active_formation(game.player)
    game.history.append(
        HistoryRecord(
            "SYS_FORMATION_DEACTIVATE",
            1,
            game.player.age,
            "九宫收阵",
            "formation",
            "deactivated",
            f"你收起“{name}”，所有被占用的阵材实例均已原样返回。",
            {},
            ["system", "formation", "art:formation"],
        )
    )
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def delete_formation(
    deps: FormationLoadoutsDependencies, game_id: str, loadout_id: str
) -> dict[str, Any]:
    game = deps._load(game_id)
    loadout = next(
        (row for row in game.player.formation_loadouts if row["id"] == loadout_id), None
    )
    if not loadout:
        raise ValueError("未找到这份阵法预设")
    if game.player.active_formation_id == loadout_id:
        deps._release_active_formation(game.player)
    game.player.formation_loadouts.remove(loadout)
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def _activate_loadout(
    deps: FormationLoadoutsDependencies, player: Player, loadout: dict[str, Any]
) -> None:
    # First build a virtual pool containing the currently occupied material.
    # This makes switching presets atomic and permits reusing the same rare
    # instance without ever cloning it.
    virtual = deps._formation_candidates(
        player, include_active=True, include_ground=False
    )
    by_type: dict[str, list[dict[str, Any]]] = {}
    for candidate in virtual:
        by_type.setdefault(str(candidate["definition_id"]), []).append(candidate)
    selected_types = [value for value in loadout["slots"] if value]
    for definition_id in selected_types:
        pool = by_type.get(str(definition_id), [])
        if not pool:
            raise ValueError(f"缺少启阵所需的阵材：{definition_id}")
        pool.pop(0)

    backup = (
        copy.deepcopy(player.inventory),
        copy.deepcopy(player.crafting_materials),
        copy.deepcopy(player.formation_materials),
        copy.deepcopy(player.formation_active_bindings),
        player.active_formation_id,
        copy.deepcopy(player.formation_profile_cache),
    )
    try:
        deps._release_active_formation(player)
        available = deps._formation_candidates(
            player, include_active=False, include_ground=False
        )
        pools: dict[str, list[dict[str, Any]]] = {}
        for candidate in available:
            pools.setdefault(str(candidate["definition_id"]), []).append(candidate)
        bindings: list[dict[str, Any] | None] = []
        for slot, definition_id in enumerate(loadout["slots"]):
            if not definition_id:
                bindings.append(None)
                continue
            pool = pools.get(str(definition_id), [])
            if not pool:
                raise ValueError(f"缺少启阵所需的阵材：{definition_id}")
            binding = deps._extract_candidate(player, pool.pop(0))
            binding["slot"] = slot
            bindings.append(binding)
        player.active_formation_id = str(loadout["id"])
        player.formation_active_bindings = bindings
        player.formation_profile_cache = deps._profile_from_bindings(player)
        if not player.formation_profile_cache.get("active"):
            raise ValueError("这份预设无法形成有效灵流")
    except Exception:
        (
            player.inventory,
            player.crafting_materials,
            player.formation_materials,
            player.formation_active_bindings,
            player.active_formation_id,
            player.formation_profile_cache,
        ) = backup
        raise

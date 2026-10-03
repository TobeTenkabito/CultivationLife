from __future__ import annotations
from typing import Any
from ...models import GameState
from ...models import HistoryRecord
from ...models import Player
from ...content_registry import WORLD_SYSTEMS
import copy
from ...runtime import now_iso
from .dependencies import FormationGroundDependencies


def _ground_array_public(
    deps: FormationGroundDependencies, player: Player, array: dict[str, Any]
) -> dict[str, Any]:
    profile = deps._ground_profile(player, array)
    world = str(array.get("world", ""))
    location_id = str(array.get("location_id", ""))
    try:
        location_name = str(deps.maps.location(world, location_id)["name"])
    except Exception:
        location_name = location_id
    return {
        key: copy.deepcopy(array.get(key))
        for key in (
            "id",
            "name",
            "loadout_id",
            "owner_kind",
            "owner_id",
            "owner_name",
            "creator_id",
            "creator_name",
            "world",
            "location_id",
            "durability",
            "created_year",
            "last_repaired_year",
            "battles",
        )
    } | {
        "world_name": WORLD_SYSTEMS.get("world_names", {}).get(world, world),
        "location_name": location_name,
        "profile": profile,
        "defense_power": deps.ground_formation_power(array, profile),
        "local": world == player.world
        and location_id == (player.location_id or location_id),
    }


def deploy_ground_formation(
    deps: FormationGroundDependencies, game_id: str, owner_kind: str = "player"
) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    deps.ensure_formation_state(player)
    if game.pending_event or not player.alive or player.imprisonment:
        raise ValueError("当前状态无法镇下阵基")
    profile = deps.active_formation_profile(player)
    if not profile.get("active") or not player.formation_active_bindings:
        raise ValueError("请先启用一座有效的随身九宫阵")
    owner_kind = str(owner_kind or "player")
    location_id = str(
        player.location_id or deps.maps.normalize_location(player.world, None)
    )
    if owner_kind == "sect":
        sect = game.sects.get(player.faction_id or "")
        if not sect or sect.extinct or sect.world != player.world:
            raise ValueError("当前没有可布置护山阵的本界宗门")
        can_manage_sect = (
            deps._intrigue_has_control(game, "sect", sect.id)
            if deps._intrigue_enabled()
            else deps._has_sect_voice(game)
        )
        if not can_manage_sect:
            raise ValueError("只有开山祖师或拥有宗门话语权者才能更换护山阵")
        owner_id, owner_name = sect.id, sect.name
    elif owner_kind == "player":
        owner_id, owner_name = "player", player.name
    else:
        raise ValueError("未知镇地阵归属")
    if any(
        row.get("world") == player.world
        and row.get("location_id") == location_id
        and row.get("owner_kind") == owner_kind
        and row.get("owner_id") == owner_id
        for row in player.formation_ground_arrays
    ):
        raise ValueError("此地已经存在同归属的镇地阵，请先撤阵")
    player.formation_ground_sequence += 1
    ground = {
        "id": f"ground-formation-{game.id}-{player.formation_ground_sequence}",
        "name": profile["name"],
        "loadout_id": player.active_formation_id or "",
        "owner_kind": owner_kind,
        "owner_id": owner_id,
        "owner_name": owner_name,
        "creator_id": game.id,
        "creator_name": player.name,
        "world": player.world,
        "location_id": location_id,
        "bindings": copy.deepcopy(player.formation_active_bindings),
        "durability": 100.0,
        "created_year": player.age,
        "last_repaired_year": player.age,
        "battles": 0,
    }
    player.formation_ground_arrays.append(ground)
    player.active_formation_id = None
    player.formation_active_bindings = []
    player.formation_profile_cache = {}
    public = deps._ground_array_public(player, ground)
    game.history.append(
        HistoryRecord(
            "SYS_FORMATION_GROUND_DEPLOY",
            1,
            player.age,
            "镇地成阵",
            ground["id"],
            "deployed",
            f"你将“{ground['name']}”镇入{public['location_name']}，"
            f"{int(profile.get('occupied_count', 0))}份实物阵基留驻原地；"
            f"当前护阵战力 {public['defense_power']:.0f}。",
            {"ground_formation_id": ground["id"], "owner_kind": owner_kind},
            ["system", "formation", "ground_formation", f"world:{player.world}"],
        )
    )
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def _require_ground_array_access(
    deps: FormationGroundDependencies, game: GameState, ground_id: str
) -> dict[str, Any]:
    deps.ensure_formation_state(game.player)
    array = next(
        (
            row
            for row in game.player.formation_ground_arrays
            if row.get("id") == ground_id
        ),
        None,
    )
    if not array:
        raise ValueError("未找到这座镇地阵")
    if array.get("owner_kind") == "sect":
        # The real materials always belong to the cultivator who carried
        # and deployed them.  Losing a war, changing allegiance or seeing
        # the sect become extinct must not orphan those instances.
        creator_id = str(array.get("creator_id", ""))
        created_by_player = not creator_id or creator_id == game.id
        current_sect_authority = array.get("owner_id") == game.player.faction_id and (
            deps._intrigue_has_control(game, "sect", str(game.player.faction_id))
            if deps._intrigue_enabled()
            else deps._has_sect_voice(game)
        )
        if not created_by_player and not current_sect_authority:
            raise ValueError("你无权处置这座宗门护山阵")
    if (
        array.get("world") != game.player.world
        or array.get("location_id") != game.player.location_id
    ):
        raise ValueError("必须亲临镇地阵所在地域才能维护或撤除")
    return array


def withdraw_ground_formation(
    deps: FormationGroundDependencies, game_id: str, ground_id: str
) -> dict[str, Any]:
    game = deps._load(game_id)
    array = deps._require_ground_array_access(game, ground_id)
    if array.get("owner_kind") == "sect" and any(
        war.get("kind") == "sect"
        and war.get("status") in {"active", "peace_ready"}
        and array.get("owner_id")
        in deps._coalition_ids(war, "attacker") + deps._coalition_ids(war, "defender")
        for war in game.wars
    ):
        raise ValueError("宗门正在交战，不能临阵撤走护山阵")
    name = str(array.get("name", "镇地阵"))
    deps._release_bindings(game.player, list(array.get("bindings", [])))
    game.player.formation_ground_arrays.remove(array)
    game.history.append(
        HistoryRecord(
            "SYS_FORMATION_GROUND_WITHDRAW",
            1,
            game.player.age,
            "拔阵归库",
            ground_id,
            "withdrawn",
            f"你撤去“{name}”，留驻此地的真实阵材已全部原样归还。",
            {},
            ["system", "formation", "ground_formation", f"world:{game.player.world}"],
        )
    )
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def repair_ground_formation(
    deps: FormationGroundDependencies,
    game_id: str,
    ground_id: str,
    supply_id: str,
    quantity: int = 1,
) -> dict[str, Any]:
    game = deps._load(game_id)
    array = deps._require_ground_array_access(game, ground_id)
    definition = deps._formation_maintenance_defs().get(str(supply_id))
    if not definition or str(definition.get("world")) != str(array.get("world")):
        raise ValueError("这份修阵资源无法与当前界面的地脉相合")
    quantity = max(1, min(10, int(quantity)))
    held = int(game.player.formation_repair_supplies.get(str(supply_id), 0))
    if held < quantity:
        raise ValueError("持有的修阵资源不足")
    before = float(array.get("durability", 0.0))
    if before >= 99.999:
        raise ValueError("镇地阵完整度已满，无需修复")
    game.player.formation_repair_supplies[str(supply_id)] = held - quantity
    if game.player.formation_repair_supplies[str(supply_id)] <= 0:
        game.player.formation_repair_supplies.pop(str(supply_id), None)
    array["durability"] = round(
        min(100.0, before + quantity * float(definition["repair_value"])), 4
    )
    array["last_repaired_year"] = game.player.age
    game.history.append(
        HistoryRecord(
            "SYS_FORMATION_GROUND_REPAIR",
            1,
            game.player.age,
            "修补阵基",
            ground_id,
            "repaired",
            f"你消耗{definition['name']} ×{quantity}，令“{array['name']}”完整度由 {before:.1f}% 恢复至 {array['durability']:.1f}%。",
            {"durability_before": before, "durability_after": array["durability"]},
            ["system", "formation", "ground_formation", "repair"],
        )
    )
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def _local_ground_formation(
    deps: FormationGroundDependencies, game: GameState
) -> dict[str, Any] | None:
    player = game.player
    candidates = [
        row
        for row in player.formation_ground_arrays
        if row.get("world") == player.world
        and row.get("location_id") == player.location_id
        and float(row.get("durability", 0.0)) > 0
        and (
            row.get("owner_kind") == "player"
            or (
                row.get("owner_kind") == "sect"
                and row.get("owner_id") == player.faction_id
            )
        )
    ]
    return max(
        candidates,
        key=lambda row: deps.ground_formation_power(
            row, deps._ground_profile(player, row)
        ),
        default=None,
    )


def _sect_guard_array(
    deps: FormationGroundDependencies, game: GameState, sect_id: str
) -> dict[str, Any] | None:
    candidates = [
        row
        for row in game.player.formation_ground_arrays
        if row.get("owner_kind") == "sect"
        and row.get("owner_id") == sect_id
        and float(row.get("durability", 0.0)) > 0
    ]
    return max(
        candidates,
        key=lambda row: deps.ground_formation_power(
            row, deps._ground_profile(game.player, row)
        ),
        default=None,
    )


def _sect_guard_power(
    deps: FormationGroundDependencies, game: GameState, sect_id: str
) -> float:
    array = deps._sect_guard_array(game, sect_id)
    if not array:
        return 0.0
    return deps.ground_formation_power(array, deps._ground_profile(game.player, array))


def _wear_war_guard_arrays(
    deps: FormationGroundDependencies,
    game: GameState,
    war: dict[str, Any],
    amount: float | None = None,
) -> None:
    if war.get("kind") != "sect":
        return
    wear = float(
        amount
        if amount is not None
        else deps._formation_rules().get("war_guard_wear_per_battle", 2.5)
    )
    for sect_id in deps._coalition_ids(war, "defender"):
        array = deps._sect_guard_array(game, sect_id)
        if array:
            array["durability"] = round(
                max(0.0, float(array.get("durability", 0.0)) - wear), 4
            )
            array["battles"] = int(array.get("battles", 0)) + 1

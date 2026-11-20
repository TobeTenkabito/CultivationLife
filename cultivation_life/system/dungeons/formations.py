"""Player ground arrays are anchored to the original encounter node's address."""

from collections import Counter

from ..formation.access import require_access
from ..formation.ground import anchor_active_formation, return_ground_bindings
from ..formation_system import _release_bindings, active_formation_profile
from .trails import here


def at_node(game, site, index):
    if (site["world"], site["location_id"]) != (game.player.world, game.player.location_id):
        return None
    address = site["nodes"][index]["id"]
    return next(
        (
            row
            for row in game.player.formation_ground_arrays
            if row.get("creator_id") == game.id
            and row.get("owner_kind") == "player"
            and row["world"] == site["world"]
            and row["location_id"] == address
        ),
        None,
    )


def local_field(game):
    state = game.dungeon_state
    site = state.get("instances", {}).get(state.get("active"))
    if site and site["status"] == "active":
        array = at_node(game, site, here(site))
        if array and array["durability"] > 0:
            return array
    return None


def place(game, site, loadout_id, deps, log):
    require_access(game)
    if site["pending"] or site["space"]["chase"] or at_node(game, site, here(site)):
        raise ValueError("须在空出的阵位从容布阵")
    player = game.player
    loadout = next((row for row in player.formation_loadouts if row["id"] == loadout_id), None)
    if not loadout:
        raise ValueError("请选择阵法栏中已有的九宫阵")
    portable = None
    if player.active_formation_id and player.active_formation_id != loadout_id:
        free = Counter(
            row["definition_id"]
            for row in deps.formation_candidates(player, include_active=False, include_ground=False)
        )
        needed = Counter(material for material in loadout["slots"] if material)
        if not (needed - free):
            portable = (
                player.active_formation_id,
                player.formation_active_bindings,
                player.formation_profile_cache,
            )
            player.active_formation_id, player.formation_active_bindings, player.formation_profile_cache = (
                None,
                [],
                {},
            )
    try:
        if player.active_formation_id != loadout_id:
            deps.activate_loadout(player, loadout)
        profile = active_formation_profile(player)
        ground = anchor_active_formation(
            game, profile, site["nodes"][here(site)]["id"], "player", "player", player.name
        )
    finally:
        if portable:
            player.active_formation_id, player.formation_active_bindings, player.formation_profile_cache = (
                portable
            )
    log(site, f"你依照「{ground['name']}」的阵图安下阵基，将阵眼藏在此地。")


def withdraw(game, site, log):
    require_access(game)
    ground = at_node(game, site, here(site))
    if not ground or site["pending"] or site["space"]["chase"]:
        raise ValueError("须在阵前收回阵材")
    return_ground_bindings(game.player, ground, _release_bindings)
    log(site, f"你收起「{ground['name']}」，将阵材一一归回行囊。")


def close_arrays(game, site, log):
    addresses = {node["id"] for node in site["nodes"]}
    for array in list(game.player.formation_ground_arrays):
        if (
            array.get("location_id") not in addresses
            or array.get("creator_id") != game.id
            or array["world"] != site["world"]
            or array["owner_kind"] != "player"
        ):
            continue
        return_ground_bindings(game.player, array, _release_bindings)
        log(site, f"「{array['name']}」收阵，阵材归回原处。")

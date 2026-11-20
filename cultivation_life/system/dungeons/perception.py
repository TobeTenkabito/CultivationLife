"""Player-visible portion of a seeded floor. Never publishes unseen actor IDs."""

from ...rules import divine_sense_level
from .people import available
from .trails import AREAS, DIRECTIONS, EVENTS, ABSENT, distance, exits, here, position, bearing
from .topography import sense, detect_snare
from .formations import at_node


def next_sign(game, site, origin, dest):
    """Read the next patrol step without mutating the expedition or creating people."""
    from .topography import arrive, local_actor
    from .people import team_reason

    floor = site["space"]
    projected = {
        **floor,
        "positions": floor["positions"].copy(),
        "visited": floor["visited"][:],
        "echoes": floor["echoes"].copy(),
    }
    future = {**site, "step": dest, "space": projected}
    arrive(game, future, origin, dest)
    node = future["nodes"][dest]
    actor = local_actor(game, future, node)
    if actor and not available(game, future, actor):
        actor = None
    if (
        actor
        and actor["state"] in {"unseen", "observed"}
        and actor["offer_step"] <= dest
        and not team_reason(game, actor)
    ):
        return "岔口有修士收了遁光，正候人结伴"
    if node["kind"] == "core" and actor and actor["state"] not in ABSENT and actor["id"] not in site["party"]:
        return "有人镇守核心阵眼"
    if node["kind"] == "contact":
        return "前路有人驻足" if actor and actor["state"] not in ABSENT else "旧足印伸向岔路，四周静了下来"
    if node["kind"] == "conflict":
        contenders = sum(
            1
            for key, r in site["roles"].items()
            if key not in site["party"]
            and r["state"] not in ABSENT
            and position(future, key) == dest
            and available(game, future, r)
        )
        return "两路修士盯上了同一处遗物" if contenders >= 2 else "争夺处遗下了几样东西"
    return EVENTS[node["kind"]]


def view(game, site):
    space = site["space"]
    center = here(site)
    level = sense(game, site)
    radius = (0, 1, 2, 3, 99)[level]
    adjacent = exits(space, center)
    occupants = {}
    for key, role in site["roles"].items():
        where = position(site, key)
        if (
            where is None
            or key in site["party"]
            or role["state"] in ABSENT
            or not available(game, site, role)
        ):
            continue
        occupants.setdefault(where, []).append(role)
    readings = []
    cells = []
    for idx, (x, y) in enumerate(space["coords"]):
        dist = distance(space, center, idx)
        visible = dist <= radius
        if not visible and idx not in space["visited"] and idx not in adjacent.values():
            continue
        cell = dict(x=x, y=y, here=idx == center, visited=idx in space["visited"], marks=[])
        marks = cell["marks"]
        if idx in space["cleared"]:
            marks.append("已探")
        array = at_node(game,site,idx)
        if array:
            marks.append(f"{array['name']} · 阵势 {array['durability']:g}%")
        if visible:
            if level >= 1 or idx == center:
                cell["area"] = AREAS[min(3, idx * 4 // len(site["nodes"]))]
            if detect_snare(game, site, idx):
                marks.append("暗阵")
            people = occupants.get(idx, [])
            if people:
                hunters = (space["chase"] or {}).get("hunters", [])
                if level >= 2 and any(r["id"] in hunters for r in people):
                    marks.append("追兵")
                if level >= 2 or idx == center:
                    marks.append(str(len(people)) + "人")
                else:
                    readings.append(bearing(space, center, idx) + "面有修士的气息")
                if level >= 3:
                    readings.append(
                        bearing(space, center, idx)
                        + " · "
                        + "、".join(r["name"] if r["known"] else "陌生修士" for r in people)
                    )
            if level >= 3 and idx not in space["cleared"]:
                cell["omen"] = (
                    next_sign(game, site, center, idx)
                    if idx in adjacent.values() and not space["chase"]
                    else EVENTS[site["nodes"][idx]["kind"]]
                )
            if idx == center and (site["pending"] or {}).get("kind") == "conflict":
                marks.append("争斗")
        cells.append(cell)
    by_coord = {(c["x"], c["y"]): c for c in cells}
    for fact in site.get("expedition", {}).get("facts", []):
        signal = space["echoes"].get(fact["id"])
        if not signal:
            continue
        idx, turn = signal
        d = distance(space, idx, center)
        if space["turn"] - turn <= 2 and (d <= radius + 1 or site["quality"] == "legendary"):
            cell = by_coord.get(tuple(space["coords"][idx]))
            if cell and (level >= 2 or idx == center):
                cell["marks"].append("斗法" if turn == space["turn"] else "余波")
            readings.append(
                bearing(space, center, idx)
                + " · "
                + ("两股强横灵压正在碰撞" if turn == space["turn"] else "仍有斗法余波")
            )
        evidence = site["expedition"]["evidence"].get(fact["id"], 0)
        if level >= 3 and d <= radius and evidence >= 2 and fact.get("winner") in site["roles"]:
            winner = site["roles"][fact["winner"]]
            readings.append(
                ("传话认错了夺宝之人。" if fact["mistaken"] else "传话与残留气息吻合。")
                + "宝物落入"
                + winner["sect_name"]
                + "的"
                + winner["name"]
                + "手中。"
            )
    current_array = at_node(game,site,center)
    calm = not site["pending"] and not space["chase"]

    return dict(
        cells=cells,
        directions=[dict(name=d, open=d in adjacent and not site["pending"]) for d in DIRECTIONS],
        sense=divine_sense_level(game.player),
        mastery=level,
        readings=list(dict.fromkeys(readings)),
        chasing=bool(space["chase"]),
        round=space["chase"]["round"] if space["chase"] else 0,
        can_ward=bool(calm and not current_array and game.player.formation_loadouts),
        can_withdraw=bool(calm and current_array),
        array_name=current_array["name"] if current_array else None,
    )

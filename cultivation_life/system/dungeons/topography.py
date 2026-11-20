"""Local eight-way trails. Coordinates and patrols belong to one frozen expedition."""

from ...rules import divine_sense_level
from .formations import local_field
from .ecology import appearance_depth

from .trails import ABSENT, distance, exits, here, position, present


def restore_map(site):
    """Attach geometry to an older frozen blueprint using its own seed and history."""
    if "space" in site:
        return
    from .generation import stream
    from .trails import layout

    space = layout(site, stream(site["seed"], "map"))
    site["space"] = space
    limit = min(site["step"], len(site["nodes"]))
    travelled = {entry["id"] for entry in site["node_history"]}
    receipts = set(site["claims"])
    known = {0, here(site)}
    for index, node in enumerate(site["nodes"]):
        if node["id"] in travelled or node["reward"]["id"] in receipts:
            known.add(index)
    space["visited"] = sorted(known)
    space["cleared"] = list(range(limit))
    space["turn"] = limit
    for key, role in site["roles"].items():
        if (
            key in site["party"]
            or role["state"] == "invited"
            or role["ledger"].get("encounter_step") == site["step"]
        ):
            space["positions"][key] = here(site)
    for key in ("actor", "other"):
        if key in (site["pending"] or {}):
            space["positions"][site["pending"][key]] = here(site)
    if limit < len(site["nodes"]):
        space["positions"][site["nodes"][limit]["actor"]] = limit


def sense(game, site):
    grade = ("ordinary", "rare", "epic", "legendary").index(site["quality"])
    threshold = (3, 7, 13, 21)[grade] + site["realm"] - 1
    from ...cultivation_coordinates import rank_for

    local_pressure = rank_for(site["realm"]) // 2
    rank = divine_sense_level(game.player)
    return sum(rank >= min(208, local_pressure + n * threshold) for n in range(1, 5))


def local_actor(game, site, node):
    from .people import available

    role = site["roles"][node["actor"]]
    if "space" not in site or (present(site, role["id"]) and role["state"] not in ABSENT):
        return role
    return next(
        (
            r
            for k, r in site["roles"].items()
            if present(site, k)
            and r["state"] not in ABSENT
            and k not in site["party"]
            and available(game, site, r)
        ),
        None,
    )


def arrive(game, site, origin, destination):
    from .people import available
    from .generation import stream

    space = site["space"]
    site["depth"] = min(3, destination * 4 // len(site["nodes"]))
    if destination not in space["visited"]:
        space["visited"].append(destination)
    space["turn"] += 1
    rng = stream(site["seed"], "patrol", space["turn"])
    guard = site["nodes"][-1]["actor"]
    meeting = {}
    for fact in site.get("expedition", {}).get("facts", []):
        if fact["id"] in space["echoes"]:
            continue
        a, b = fact["actors"]
        if any(
            k in site["party"]
            or site["roles"][k]["state"] in ABSENT
            or not available(game, site, site["roles"][k])
            for k in (a, b)
        ):
            continue
        anchor = max((a, b), key=lambda k: (k == guard, appearance_depth(site, site["roles"][k])))
        for k in (a, b):
            meeting.setdefault(k, space["positions"][anchor])
        break
    for key, place in list(space["positions"].items()):
        role = site["roles"][key]
        if key in site["party"]:
            space["positions"][key] = destination
            continue
        if key == guard or role["state"] in ABSENT or (space["chase"] and key in space["chase"]["hunters"]):
            continue
        nearby = [
            i
            for i in exits(space, place).values()
            if i * 4 // len(site["nodes"]) >= appearance_depth(site, role)
        ]
        if key in meeting and nearby:
            space["positions"][key] = min([place, *nearby], key=lambda i: distance(space, i, meeting[key]))
        elif destination in nearby and key == site["nodes"][destination]["actor"]:
            space["positions"][key] = destination
        elif place != destination and nearby and rng.random() < 0.32:
            space["positions"][key] = rng.choice(nearby)
    for fact in site.get("expedition", {}).get("facts", []):
        a, b = fact["actors"]
        if (
            a in meeting
            and b in meeting
            and fact["id"] not in space["echoes"]
            and space["turn"] >= fact["occurred"]
            and position(site, a) == position(site, b)
        ):
            space["echoes"][fact["id"]] = [position(site, a), space["turn"]]


def detect_snare(game, site, idx):
    from .people import available

    owner = site["space"]["snares"].get(str(idx))
    return (
        owner
        and owner not in site["party"]
        and site["roles"][owner]["state"] not in ABSENT
        and available(game, site, site["roles"][owner])
        and idx not in site["space"]["spent"]
        and sense(game, site) >= 2 + int(site["roles"][owner]["realm"] > site["realm"])
    )


def encounter_snare(deps, game, site, log, close):
    from .people import available

    space = site["space"]
    idx = here(site)
    owner = space["snares"].get(str(idx))
    if not owner or idx in space["spent"]:
        return
    role = site["roles"][owner]
    if owner in site["party"] or role["state"] in ABSENT or not available(game, site, role):
        return
    detect_before_entry = detect_snare(game, site, idx)
    space["spent"].append(idx)
    if detect_before_entry:
        log(site, "你察觉石缝里伏着一线灵力，挑断阵脚，暗纹随即熄灭。")
        return
    damage = max(1, round(game.player.hp * 0.15))
    game.player.hp = max(0, game.player.hp - damage)
    log(site, f"脚下阵纹骤亮，伏下的暗阵削去你 {damage} 点气血。")
    if game.player.hp <= 0:
        deps.die(game, "探境误入伏阵", "SYS_DUNGEON_SNARE", death_cause="ordinary")
        close(game, site, "伏阵截断了你的探境之路。")


def start_chase(game, site, keys, log):
    space = site["space"]
    place = here(site)
    for key in keys:
        if key in site["party"]:
            site["party"].remove(key)
            from .companions import separate

            separate(game, site["roles"][key])
        space["positions"][key] = place
        site["roles"][key].update(known=True, state="hostile")
    space["chase"] = dict(hunters=keys, round=0)
    site["pending"] = None
    log(site, "你抢先掠出几步。身后遁光一转，追兵已跟了上来。")


def pursuit(game, site, log):
    from .generation import stream
    from .people import available, power
    from ...rules import combat_power

    space = site["space"]
    chase = space["chase"]
    idx = here(site)
    chase["round"] += 1
    rng = stream(site["seed"], "pursuit", space["turn"])
    field = local_field(game)
    caught = []
    remaining = []
    for key in chase["hunters"]:
        role = site["roles"][key]
        if not available(game, site, role) or role["state"] in ABSENT:
            continue
        pos = space["positions"][key]
        gap = role["realm"] - game.player.realm_index
        ratio = power(game, role) / max(1, combat_power(game.player))
        if field and distance(space, pos, idx) <= 1:
            space["positions"][key] = idx
            caught.append(key)
            continue
        # A head start lasts one turn. A determined higher realm closes it on the next.
        if chase["round"] == 1:
            speed = 0
        elif gap > 0:
            speed = 2 if role["resolve"] >= 50 or rng.random() < 0.95 else 1
        else:
            speed = int(
                rng.random()
                < max(0.12, min(0.92, 0.36 + 0.18 * min(2, ratio) + gap * 0.2 + role["resolve"] / 500))
            )
        for _ in range(speed):
            if pos == idx:
                break
            candidates = list(exits(space, pos).values())
            pos = min(candidates, key=lambda n: distance(space, n, idx))
        space["positions"][key] = pos
        if pos == idx:
            caught.append(key)
        elif distance(space, pos, idx) < (3 if gap > 0 else 2) or chase["round"] < 2:
            remaining.append(key)
    if caught:
        key = max(caught, key=lambda k: (site["roles"][k]["realm"], power(game, site["roles"][k])))
        ambush = bool(field)
        space["chase"] = None
        site["pending"] = dict(kind="ambush", actor=key, intercepted=True)
        if len(caught) > 1:
            site["pending"]["pursuers"] = [k for k in caught if k != key]
        if ambush:
            site["pending"]["snared"] = True
        log(
            site,
            site["roles"][key]["name"]
            + (
                f"闯入「{field['name']}」，你已守住阵眼。"
                if ambush
                else "追到身前，截住了你的去路。"
            ),
            actors=[key],
        )
    elif remaining:
        chase["hunters"] = remaining
        log(site, "身后仍有遁光跟来，你听见追兵换了方位。")
    else:
        space["chase"] = None
        if site.get("expedition"):
            site["expedition"]["performance"]["escapes"] += 1
        log(site, "你转过岔道，身后终于没了追兵的声息。")

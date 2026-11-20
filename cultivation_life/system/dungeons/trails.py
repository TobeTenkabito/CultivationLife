"""Frozen local trail geometry; indices refer to original encounter nodes."""

from .ecology import appearance_depth

DIRECTIONS = {
    "西北": (-1, -1),
    "北": (0, -1),
    "东北": (1, -1),
    "西": (-1, 0),
    "东": (1, 0),
    "西南": (-1, 1),
    "南": (0, 1),
    "东南": (1, 1),
}
EVENTS = {
    "contact": "修士在此停步",
    "conflict": "有人在争夺遗物",
    "core": "核心阵眼",
    "seal": "封印下有灵光",
    "hazard": "险阵蓄势",
    "trace": "前人行迹",
    "cache": "藏物之处",
}
AREAS = ("入口", "外围", "深处", "核心")
ABSENT = {"left", "dead", "missing"}


def layout(site, rng):
    size = len(site["nodes"])
    width = rng.choice((3, 4))
    flip_x, flip_y, swap = rng.choice((-1, 1)), rng.choice((-1, 1)), rng.randrange(2)
    coords = []
    for i in range(size):
        y, x = divmod(i, width)
        x = (width - 1 - x if y % 2 else x) * flip_x
        y *= flip_y
        coords.append([y, x] if swap else [x, y])
    home = {}
    guardian = site["nodes"][-1]["actor"]
    for key, role in site["roles"].items():
        eligible = [i for i in range(size) if min(3, i * 4 // size) >= appearance_depth(site, role)]
        home[key] = next((i for i, n in enumerate(site["nodes"]) if n["actor"] == key), rng.choice(eligible))
    home[site["nodes"][0]["actor"]] = 0
    home[guardian] = size - 1
    traps = {}
    for i in range(1, size - 1):
        if rng.random() < 0.25:
            owners = [
                k for k in home if k != guardian and appearance_depth(site, site["roles"][k]) <= i * 4 // size
            ]
            if owners:
                owner = rng.choice(owners)
                traps[str(i)] = owner
    return dict(
        coords=coords,
        positions=home,
        turn=0,
        visited=[0],
        cleared=[],
        snares=traps,
        spent=[],
        chase=None,
        echoes={},
    )


def here(site):
    return min(site["step"], len(site["nodes"]) - 1)


def distance(space, a, b):
    x, y = space["coords"][a]
    u, v = space["coords"][b]
    return max(abs(u - x), abs(v - y))


def exits(space, place):
    x, y = space["coords"][place]
    cells = {tuple(pos): i for i, pos in enumerate(space["coords"])}
    return {
        direction: cells[x + dx, y + dy]
        for direction, (dx, dy) in DIRECTIONS.items()
        if (x + dx, y + dy) in cells
    }


def position(site, key):
    space = site["space"]
    if key in site["party"]:
        return here(site)
    return space["positions"].get(key)


def present(site, key):
    return "space" not in site or position(site, key) == here(site)


def bearing(space, origin, target):
    x, y = space["coords"][origin]
    u, v = space["coords"][target]
    return ("西" if u < x else "东" if u > x else "") + ("北" if v < y else "南" if v > y else "") or "此处"

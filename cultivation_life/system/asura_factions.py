"""Optional royal factions. State belongs to the court, never to Sage DLC."""

import copy
import hashlib
import random

from ..content_registry import ITEM_CATALOG, WORLD_SYSTEMS, restricted_acquisition
from .crafting_system import (
    crafting_material_definitions,
    make_crafting_material_instance,
)
from .formation_system import (
    formation_material_definitions,
    make_formation_material_instance,
)
from ..npc_custody import is_free
from ..rules import add_item, opportunity_required
from . import asura
from .influence import redistribute

FACTIONS = {
    "blood_clans": "血裔诸族",
    "war_hosts": "征伐军府",
    "free_cities": "万战城盟",
}
CATEGORIES = {"political": "政治", "diplomatic": "外交", "military": "军事"}
POLICY_CATEGORIES = {"war": "military", "recruit": "military", "tax": "military"}
RULES = {
    "influence_floor": 5,
    "doctrine_influence_cap": 70,
    "world_influence_pool": 100,
}


def fresh():
    return {
        "rows": [
            dict(id=k, name=v, external=100 / 3, loyalty=60)
            for k, v in FACTIONS.items()
        ],
        "tribute_at": {},
        "target_at": -100,
        "pressure": 0,
    }


def ensure(state):
    if asura.enabled():
        state["court"].setdefault("factions", fresh())


def faction_of(identity):
    return tuple(FACTIONS)[
        hashlib.sha256(identity.encode()).digest()[0] % len(FACTIONS)
    ]


def shift(rows, faction, delta):
    """Unlike schools, a court has no unclaimed influence: freed seats redistribute."""
    redistribute(rows, faction, delta, RULES)
    spare = max(0.0, 100 - sum(row["external"] for row in rows))
    recipients = [r for r in rows if r["id"] != faction and r["external"] < 70]
    room = sum(70 - r["external"] for r in recipients)
    if room:
        for row in recipients:
            row["external"] += spare * (70 - row["external"]) / room


def materials():
    ids = WORLD_SYSTEMS.get("asura_manifestation", {}).get("royal_material_ids", [])
    rows = [
        dict(id=key, name=ITEM_CATALOG[key].name, kind="item")
        for key in ids
        if key in ITEM_CATALOG and not restricted_acquisition("item", key)
    ]
    cfg = WORLD_SYSTEMS.get("asura_manifestation", {})
    for kind, definitions in [
        ("crafting", crafting_material_definitions()),
        ("formation", formation_material_definitions()),
    ]:
        rows.extend(
            dict(id=key, name=definitions[key]["name"], kind=kind)
            for key in cfg.get(f"royal_{kind}_ids", [])
            if key in definitions
        )
    return rows


def tick(game, state, roster):
    """Called once per elapsed royal unit; never on refresh or read."""
    if not asura.enabled():
        return
    ensure(state)
    c, unit = state["court"], state["unit"]
    if c["holders"].get("5") != "player" or not state["joined"]:
        return
    f = c["factions"]
    favored = {
        "war": "war_hosts",
        "tax": "war_hosts",
        "recruit": "war_hosts",
        "prosper": "blood_clans",
        "study": "blood_clans",
        "trade": "free_cities",
        "rest": "free_cities",
    }[state["policy"]]
    shift(f["rows"], favored, 1.5)
    for row in f["rows"]:
        row["loyalty"] = max(
            0, min(100, row["loyalty"] + (1 if row["id"] == favored else -0.4))
        )
    danger = [r for r in f["rows"] if r["external"] >= 48 or r["loyalty"] < 20]
    f["pressure"] = f["pressure"] + 1 if danger else 0
    if (
        f["pressure"] < 4
        or c["challenge"]
        or unit < c["protected_until"]
        or unit - c["last_challenge"] < 12
        or game.pending_event
        or game.active_trial
        or game.player.imprisonment
        or game.player.ghost_captor
        or not game.player.alive
    ):
        return
    faction = max(danger, key=lambda row: row["external"] + 100 - row["loyalty"])
    candidates = [
        n
        for n in roster.values()
        if is_free(n)
        and n.world == "asura"
        and faction_of(n.id) == faction["id"]
        and unit - c["challenger_times"].get(n.id, -100) >= 24
    ]
    if not candidates:
        return
    representative = max(candidates, key=lambda n: (n.realm_index, n.layer))
    c["challenge"] = dict(
        npc_id=representative.id,
        rank=5,
        issued_at=unit,
        deadline=unit + 4,
        faction_id=faction["id"],
        player_score=0,
        challenger_score=0,
    )
    c["last_challenge"] = unit
    c["challenger_times"][representative.id] = unit
    from .institution_state import record

    record(
        game,
        state,
        f"{faction['name']}势力失衡，推举{representative.name}发起换位血战，须于第 {unit + 4} 单位前应战。",
    )


def settle_duel(state, challenge, won):
    if not asura.enabled() or not challenge or not challenge.get("faction_id"):
        return
    f = state["court"]["factions"]
    row = next(r for r in f["rows"] if r["id"] == challenge["faction_id"])
    shift(f["rows"], row["id"], -15 if won else 10)
    row["loyalty"] = (
        min(100, row["loyalty"] + 25) if won else max(0, row["loyalty"] - 10)
    )
    f["pressure"] = 0


def act(game, state, action, target, roster):
    if not asura.enabled():
        raise ValueError("此项王权需要开启修罗界 DLC")
    ensure(state)
    c, unit = state["court"], state["unit"]
    if c["holders"].get("5") != "player" or not state["joined"] or c["challenge"]:
        raise ValueError("须为在位修罗王，并先处理换位战书")
    f = c["factions"]
    if action == "faction_decree":
        policy, _, faction = target.partition(":")
        row = next((r for r in f["rows"] if r["id"] == faction), None)
        if row is None or policy not in {"patronize", "restrain", "mediate"}:
            raise ValueError("请选择派系与政令")
        if unit - f["target_at"] < 4 or state["treasury"] < 100000:
            raise ValueError("派系政令需要十万府库灵石，间隔四单位")
        from .economy import organizations as finance
        finance.register(game, 'upper', 'asura', 'asura')
        finance.procure(game, finance.key('upper', 'asura'), 'asura', 100000, '王庭派系政令支出')
        delta, loyalty = {
            "patronize": (8, 15),
            "restrain": (-12, -10),
            "mediate": (-4, 10),
        }[policy]
        shift(f["rows"], faction, delta)
        row["loyalty"] = max(0, min(100, row["loyalty"] + loyalty))
        f["target_at"] = unit
        return f"对{row['name']}颁行派系政令，影响力 {delta:+}，忠诚 {loyalty:+}。"
    kind, _, identity = target.partition(":")
    if action != "royal_tribute" or kind not in {"material", "opportunity", "prisoner"}:
        raise ValueError("未知王权索取事项")
    key = f"{kind}:{identity}"
    if unit - f["tribute_at"].get(key, -100) < 4:
        raise ValueError("同一贡赋须间隔四个政历单位")
    if kind == "material":
        item = next((i for i in materials() if i["id"] == identity), None)
        if item is None:
            raise ValueError(
                "只可索取修罗界本体资材，其他 DLC 与专属秘境产物不在贡赋范围"
            )
        quantity = 1000000 if identity == "spirit_stone" else 1
        from .economy import organizations as finance
        finance.register(game, 'upper', 'asura', 'asura')
        source = finance.key('upper', 'asura')
        if identity == 'spirit_stone':
            finance.transfer_value(game, source, 'player', quantity, '王庭现金贡赋')
        else:
            if item['kind'] == 'crafting':
                cost = crafting_material_definitions()[identity]['base_material_value']
            elif item['kind'] == 'formation':
                cost = formation_material_definitions()[identity]['base_value']
            else:
                from .economy.state import commodity_catalog
                cost = commodity_catalog('asura').get(identity, {}).get('base_price', 100000)
            finance.procure(game, source, 'asura', int(cost), '王庭资材贡赋采购')
        if item["kind"] == "crafting":
            rng = random.Random(f"{game.seed}:royal:{unit}:{identity}")
            instance = make_crafting_material_instance(
                crafting_material_definitions()[identity],
                rng,
                source="修罗王庭贡赋",
                origin_world="asura",
            )
            instance["id"] = f"royal-{unit}-{identity}"
            game.player.crafting_materials.append(instance)
        elif item["kind"] == "formation":
            instance = make_formation_material_instance(
                formation_material_definitions()[identity],
                source="修罗王庭贡赋",
                origin_world="asura",
            )
            instance["id"] = f"royal-{unit}-{identity}"
            game.player.formation_materials.append(instance)
        elif identity != 'spirit_stone':
            add_item(game.player, identity, quantity)
        text = f"王庭征调{item['name']} × {quantity}。"
        faction = "free_cities"
    else:
        npc = roster.get(identity)
        if not npc or not is_free(npc) or npc.world != "asura":
            raise ValueError("须选择本界在世的自由修士")
        faction = faction_of(identity)
        if kind == "opportunity":
            available = max(0.0, npc.cultivation_progress)
            if available <= 0:
                raise ValueError("此修士暂无可贡献的修行积累")
            amount = min(available, opportunity_required(game.player) * 0.1)
            npc.cultivation_progress -= amount
            from .opportunity import grant
            from .map_system import MapCatalog
            from ..content_registry import CONTENT_DOCUMENTS
            maps = MapCatalog(CONTENT_DOCUMENTS["maps.json"])
            amount = grant(game.player, amount, maps.qi_gain_efficiencies(game.player.world, game.player.location_id))
            text = f"{npc.name}贡献机缘 {amount:,.1f}，其自身修行积累相应减少。"
        else:
            victims = [
                n
                for n in roster.values()
                if is_free(n)
                and n.world == "asura"
                and n.id != identity
                and n.faction_id != "asura_royal_court"
                and (n.realm_index, n.layer) < (npc.realm_index, npc.layer)
            ]
            if not victims:
                raise ValueError("本界没有此修士能够押献的对象")
            victim = min(victims, key=lambda n: (n.realm_index, n.layer, n.id))
            record = game.detain_person(
                dict(
                    victim.to_dict(),
                    captured_age=game.player.age,
                    source="royal_tribute",
                    contributor_id=npc.id,
                )
            )
            game.player.prisoners.append(record)
            text = f"{npc.name}押献{victim.name}，原人物转入你的俘虏名册。"
        npc.affinity = (npc.affinity or 0) - 5
    row = next(r for r in f["rows"] if r["id"] == faction)
    row["loyalty"] = max(0, row["loyalty"] - 6)
    f["tribute_at"][key] = unit
    return text


def public(game, state):
    if not asura.enabled():
        return None
    f = copy.deepcopy(state["court"].get("factions") or fresh())
    f["materials"] = materials()
    f["decrees"] = [
        dict(id="patronize", name="扶植", category="political"),
        dict(id="mediate", name="调停", category="diplomatic"),
        dict(id="restrain", name="削权", category="military"),
    ]
    return f

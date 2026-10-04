"""Four-dimensional, finite-use talismans. Queries never spend charges."""

from collections import Counter
import copy

from ..content_registry import WORLD_SYSTEMS, ROOT_DEFINITIONS
from ..relationship_records import find_person
from ..npc_custody import is_free
from ..rules import has_item, remove_item, player_affinities, root_elements

DIMENSIONS = ("power", "protection", "assistance")


def config():
    return WORLD_SYSTEMS["talismans"]


def read(player, dimension):
    if dimension not in DIMENSIONS:
        raise ValueError("未知符箓属性")
    return sum(
        float(t[dimension]) for t in player.talismans if t["enabled"] and t["uses"] > 0
    )


def consume(player, dimension):
    value = 0.0
    for talisman in player.talismans:
        if talisman["enabled"] and talisman["uses"] > 0 and talisman[dimension] > 0:
            value += talisman[dimension]
            talisman["uses"] -= 1
    return value


def craft(game, payload):
    p = game.player
    method = next(
        (m for m in config()["methods"] if m["id"] == payload.get("method_id")), None
    )
    if not method or method["id"] not in p.talisman_methods:
        raise ValueError("须先学习对应制符法")
    element = payload.get("element")
    if element not in config()["elements"]:
        raise ValueError("请选择对应法术灵力属性")
    ids = [payload.get("material1"), payload.get("material2")]
    definitions = {r["id"]: r for r in config()["materials"]}
    if any(key not in definitions for key in ids):
        raise ValueError("制符必须使用两份符材")
    costs = Counter(ids)
    helper_id = payload.get("npc_id", "")
    helper = find_person(game, helper_id) if helper_id else None
    if game.player.world in {"rift", "lost"}:
        from ..models import SectNpc

        raw = next(
            (
                n
                for n in game.spatial_state.get("instances", {})
                .get(game.spatial_state.get("current"), {})
                .get("npcs", [])
                if n["id"] == helper_id
            ),
            None,
        )
        helper = SectNpc.from_dict(raw) if raw else None
    needs_help = element not in player_affinities(p)
    if needs_help:
        if (
            not helper
            or not is_free(helper)
            or helper.world != p.world
            or element
            not in (
                root_elements(helper.spirit_root)
                if helper.spirit_root in ROOT_DEFINITIONS
                else []
            )
            or (helper.affinity or 0) < 0
        ):
            raise ValueError("缺少对应灵根；须请同界、友善且拥有对应灵根的修士注灵")
        costs["spirit_stone"] += 100 * max(1, p.realm_index)
    if any(not has_item(p, key, quantity) for key, quantity in costs.items()):
        raise ValueError("符材或委托注灵的灵石不足")
    mana = 10 * max(1, p.realm_index)
    if not needs_help and p.mp < mana:
        raise ValueError("注灵法力不足")
    quality = sum(definitions[key]["quality"] for key in ids) / 2
    for key, quantity in costs.items():
        remove_item(p, key, quantity)
    if not needs_help:
        p.mp -= mana
    p.talisman_sequence += 1
    row = dict(
        id=f"talisman_{p.talisman_sequence}",
        name=method["name"],
        element=element,
        enabled=False,
        uses=int(method["uses"]),
        **{dim: round(method[dim] * quality, 3) for dim in DIMENSIONS},
    )
    p.talismans.append(row)
    return f"制成{row['name']}，可调用 {row['uses']} 次；默认未启用。"


def act(game, action, payload):
    p = game.player
    if (
        not p.alive
        or game.pending_event
        or game.active_trial
        or p.imprisonment
        or p.ghost_captor
    ):
        raise ValueError("当前无法办理符箓事务")
    if action == "craft":
        return craft(game, payload)
    if action == "learn":
        method = next(
            (m for m in config()["methods"] if m["id"] == payload.get("method_id")),
            None,
        )
        if not method or method["id"] in p.talisman_methods or p.realm_index < 1:
            raise ValueError("制符法无效、已学会或尚未入道")
        if not remove_item(p, "spirit_stone", method["cost"]):
            raise ValueError("学习制符法的灵石不足")
        p.talisman_methods.append(method["id"])
        return f"习得{method['name']}制符法。"
    row = next((t for t in p.talismans if t["id"] == payload.get("talisman_id")), None)
    if row is None:
        raise ValueError("符箓不存在")
    if action == "toggle":
        if row["uses"] <= 0:
            raise ValueError("此符箓次数已耗尽")
        row["enabled"] = not row["enabled"]
        return f"{row['name']}{'启用' if row['enabled'] else '停用'}。"
    if action == "discard":
        p.talismans.remove(row)
        return "已弃去符箓。"
    raise ValueError("未知符箓操作")


def public(game):
    p = game.player
    people = {
        **game.world_npcs,
        **game.notable_npcs,
        **game.relationship_npcs,
        **{n.id: n for sect in game.sects.values() for n in sect.npcs},
    }
    if p.world in {"rift", "lost"}:
        from ..models import SectNpc

        people = {
            n["id"]: SectNpc.from_dict(n)
            for n in game.spatial_state.get("instances", {})
            .get(game.spatial_state.get("current"), {})
            .get("npcs", [])
        }
    return dict(
        rows=copy.deepcopy(p.talismans),
        methods=[
            dict(m, learned=m["id"] in p.talisman_methods) for m in config()["methods"]
        ],
        elements=config()["elements"],
        materials=[
            dict(
                m,
                quantity=next((i.quantity for i in p.inventory if i.id == m["id"]), 0),
            )
            for m in config()["materials"]
        ],
        helpers=[
            dict(id=n.id, name=n.name, elements=root_elements(n.spirit_root))
            for n in people.values()
            if is_free(n)
            and n.world == p.world
            and n.spirit_root in ROOT_DEFINITIONS
            and (n.affinity or 0) >= 0
        ],
    )

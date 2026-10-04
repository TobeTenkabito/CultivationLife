"""Four-dimensional, finite-use talismans. Queries never spend charges."""

from collections import Counter
import copy
import math

from ..content_registry import WORLD_SYSTEMS, ROOT_DEFINITIONS
from ..relationship_records import find_person
from ..npc_custody import is_free
from ..rules import has_item, remove_item, player_affinities, root_elements, add_item
from ..runtime import decode_rng, encode_rng
from ..talisman_content import DIMENSIONS, QUALITIES, local_catalog

LEGACY_METHODS = {"ward": "talisman_human_1_protection", "strike": "talisman_human_1_power",
                  "balance": "talisman_human_1_power_protection_assistance"}


def learned(player, method):
    return method["id"] in player.talisman_methods or any(
        old in player.talisman_methods and target == method["id"] for old, target in LEGACY_METHODS.items())


def local_materials(game):
    definitions = dict(local_catalog(game)[0])
    if game.player.world == "human":
        for identity, name, quality in [("talisman_paper", "一阶灵纹符纸", 1.), ("talisman_cinnabar", "一阶灵砂朱砂", 1.4)]:
            if has_item(game.player, identity):
                definitions[identity] = dict(id=identity, name=name, quality=quality, tier=1,
                                             world="human", base_value=round(24 * quality))
    return definitions

def skill(player):
    experience = max(0., float(player.art_experience.get("talisman", 0)))
    base = float(WORLD_SYSTEMS["spirit_field"]["art_experience_base"])
    level = math.isqrt(int(experience / base))
    progress = (experience - base * level ** 2) / (base * (2 * level + 1))
    return dict(level=level, experience=experience, progress=progress)


def success_chance(player, tier):
    practice = skill(player)
    return round(min(.98, max(.1, .65 + .045 * practice["level"]
                              + .04 * practice["progress"] - .045 * (tier - 1))), 4)


def grant_experience(player, tier, success):
    amount = tier * (12 if success else 5)
    amount *= 1 + max(0., float(player.sage_effects.get("art_experience_multiplier", 0)))
    player.art_experience["talisman"] = player.art_experience.get("talisman", 0) + amount


def economic_value(row):
    """Remaining charges, all three effects, quality and paid materials matter."""
    if row["uses"] <= 0:
        return 0
    factor = QUALITIES.get(row.get("quality"), QUALITIES["normal"])[1]
    material_value = row.get("material_value", 100 * max(1, row.get("tier", 1)))
    dimensions = sum(max(0., row[d]) for d in DIMENSIONS)
    return max(1, round(material_value * factor * (1 + dimensions / 100)
                        * row["uses"] / max(1, row.get("max_uses", row["uses"]))))


def sale_rows(player, ratio=.55):
    return [dict(id=r["id"], name=r["name"], tier=r.get("tier", 1),
                 quality_name=QUALITIES.get(r.get("quality"), QUALITIES["normal"])[0],
                 uses=r["uses"], value=economic_value(r),
                 price=max(1, round(economic_value(r) * ratio)))
            for r in player.talismans if r["uses"] > 0]


def product(method, materials, quality, element="metal"):
    factor = QUALITIES[quality][1]
    material_quality = sum(m["quality"] for m in materials) / 2
    uses = max(1, round(method["uses"] * (.8 + factor * .2)))
    return dict(name=method["name"], method_id=method["id"], tier=method["tier"],
                origin_world=method["world"], quality=quality, element=element,
                material_value=sum(m["base_value"] for m in materials),
                enabled=False, uses=uses, max_uses=uses,
                **{d: round(method[d] * material_quality * factor, 3) for d in DIMENSIONS})


def receive(player, row):
    player.talisman_sequence += 1
    owned = copy.deepcopy(row)
    owned["id"] = f"talisman_{player.talisman_sequence}"
    player.talismans.append(owned)
    return owned


def market_offers(game, tier, market_name, location_id):
    definitions = local_catalog(game)[0]
    available = sorted({r["tier"] for r in definitions.values() if r["tier"] <= tier})
    if not available:
        return []
    # Follow the same current-tier shelf rule as other crafting materials.
    retained = [copy.deepcopy(r) for r in game.market_offers
                if r.get("kind") == "talisman_material" and r.get("locked") and not r.get("sold")
                and r.get("world") == game.player.world and r.get("location_id") == location_id][:1]
    return retained + [dict(id=f"{location_id}-{game.player.age}-{m['id']}", kind="talisman_material",
                 content_id=m["id"], name=m["name"], description=m["description"],
                 price=m["base_value"], tier=m["tier"], tier_name=f"{m['tier']}阶",
                 world=game.player.world, location_id=location_id, market_name=market_name,
                 sold=False, locked=False, rare_next_tier=False)
            for m in definitions.values() if m["tier"] == available[-1]
            and m["id"] not in {r["content_id"] for r in retained}]


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
    definitions, methods = local_materials(game), local_catalog(game)[1]
    identity = payload.get("method_id")
    method = methods.get(LEGACY_METHODS.get(identity, identity))
    if not method or not learned(p, method):
        raise ValueError("须先学习对应制符法")
    if p.realm_index < method["tier"]:
        raise ValueError("修为不足以炼制此阶符箓")
    element = payload.get("element")
    if element not in config()["elements"]:
        raise ValueError("请选择对应法术灵力属性")
    ids = [payload.get("material1"), payload.get("material2")]
    if any(key not in definitions or definitions[key]["tier"] != method["tier"] for key in ids):
        raise ValueError("制符必须使用当前界面、与制符法同阶的两份符材，不能跨界炼制")
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
    chance = success_chance(p, method["tier"])
    rng = decode_rng(game.seed, game.rng_state)
    for key, quantity in costs.items():
        remove_item(p, key, quantity)
    if not needs_help:
        p.mp -= mana
    succeeded = rng.random() < chance
    quality_score = rng.random() + min(.5, skill(p)["level"] * .025)
    quality = "perfect" if quality_score >= .95 else "fine" if quality_score >= .65 else "normal" if quality_score >= .2 else "poor"
    grant_experience(p, method["tier"], succeeded)
    game.rng_state = encode_rng(rng)
    if not succeeded:
        return "符纹失稳，炼制失败；符材与注灵消耗已扣除，获得制符经验。"
    row = receive(p, product(method, [definitions[key] for key in ids], quality, element))
    row["creator_id"] = game.id
    return f"制成{QUALITIES[quality][0]}{row['name']}，可调用 {row['uses']} 次；默认未启用。"


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
        identity = payload.get("method_id")
        method = local_catalog(game)[1].get(LEGACY_METHODS.get(identity, identity))
        if not method or learned(p, method) or p.realm_index < method["tier"]:
            raise ValueError("制符法不属于当前界面、已学会或修为未达对应阶数")
        if not remove_item(p, "spirit_stone", method["cost"]):
            raise ValueError("学习制符法的灵石不足")
        p.talisman_methods.append(method["id"])
        return f"习得{method['name']}制符法。"
    row = next((t for t in p.talismans if t["id"] == payload.get("talisman_id")), None)
    if row is None:
        raise ValueError("符箓不存在")
    if action == "sell":
        if p.world in {"rift", "lost"} or p.realm_index < 1 or game.guixu_state.get("player_session"):
            raise ValueError("此处无法与外界坊市交易")
        quote = next((r for r in sale_rows(p) if r["id"] == row["id"]), None)
        if not quote:
            raise ValueError("符箓次数耗尽，无法出售")
        p.talismans.remove(row)
        add_item(p, "spirit_stone", quote["price"])
        return f"在坊市售出{row['name']}，获得 {quote['price']} 灵石。"
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
    definitions, methods = local_materials(game), local_catalog(game)[1]
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
        skill=skill(p),
        rows=[dict(copy.deepcopy(r), tier=r.get("tier", 1), value=economic_value(r),
                   quality_name=QUALITIES.get(r.get("quality"), QUALITIES["normal"])[0]) for r in p.talismans],
        methods=[
            dict(m, learned=learned(p, m), available=p.realm_index >= m["tier"],
                 success_chance=success_chance(p, m["tier"])) for m in methods.values()
        ],
        elements=config()["elements"],
        materials=[
            dict(
                m,
                quantity=next((i.quantity for i in p.inventory if i.id == m["id"]), 0),
            )
            for m in definitions.values()
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

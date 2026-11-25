"""Study a lineage from the actual person's books and usable artifacts."""
import copy

from ..combat_attributes import read
from ..content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG
from ..traits import ARTIFACT_TRAITS, BODY_TRAITS, EFFECTS, MASTERY, TRAITS, grant, mastery, state
from .combat.actor_state import has_body
from .combat_loadout import player_equipment
from .npc_techniques import levels


def source_name(source):
    if source.startswith("artifact:"):
        return ITEM_CATALOG[source.removeprefix("artifact:")].name
    book = TECHNIQUE_CATALOG.get(source)
    if book:
        return book.name
    if source.startswith("light:") and source in MASTERY:
        from .divine_lights import definitions
        return next((row["name"] for row in definitions() if row["id"] == source[6:]), source)
    return source


def available_sources(game, owner):
    if owner is game.player:
        books = {book.id: book.level for book in owner.known_techniques}
        _, equipped = player_equipment(game, owner)
        items = {read(item, "id") for item in equipped}
    else:
        books = levels(owner)
        items = {read(owner, "combat_artifact_id")}
        items.update(row["id"] for row in read(owner, "family_traits", {}).get("equipment", []) if row.get("id"))

    record = state(owner)
    result = {book: MASTERY[book] for book, level in books.items()
              if level == 9 and book in MASTERY and book not in record.get("mastery", {})}
    for item in sorted(items.intersection(ARTIFACT_TRAITS)):
        result["artifact:" + item] = ARTIFACT_TRAITS[item]
    return result


def options(game, owner):
    owned = state(owner).get("owned", {})
    rows = []
    for source, key in available_sources(game, owner).items():
        if source in owned.get(key, ()):
            continue
        preview = {"owned": copy.deepcopy(owned)}
        allowed = (key not in BODY_TRAITS or has_body(owner)) and grant(preview, key, source)
        replaced = [TRAITS[k][0] for k in owned if k not in preview["owned"]]
        rows.append(dict(id=source, source=source_name(source), name=TRAITS[key][0], rarity=TRAITS[key][1],
                         effect=EFFECTS[key], allowed=allowed, replaces=replaced))
    return rows


def study(game, owner, source):
    if not isinstance(source, str):
        raise ValueError("参悟来源编号无效")
    key = available_sources(game, owner).get(source)
    if not key:
        raise ValueError("参悟来源已不可用，请重新查看本人法宝与大成功法")
    if key in BODY_TRAITS and not has_body(owner):
        raise ValueError("凝成此特质需要实际肉身")
    record = read(owner, "trait_state")
    if record is None and isinstance(owner, dict):
        record = owner.setdefault("trait_state", {})
    if source in record.get("owned", {}).get(key, ()):
        raise ValueError("已从此来源领悟特质")
    if source.startswith("artifact:"):
        success = grant(record, key, source)
    else:
        # Book mastery also records blocked milestones during normal training. An explicit
        # study request must leave the person untouched when its preview is blocked.
        success = grant({"owned": copy.deepcopy(record.get("owned", {}))}, key, source) and mastery(owner, source)
    if not success:
        raise ValueError("当前特质等级或互斥关系阻止此次领悟")

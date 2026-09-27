"""Persistent faction addresses and admission rules; consumes no simulation RNG."""
from __future__ import annotations

import hashlib

from ..content_registry import CONTENT_DOCUMENTS, REALMS


def faction_site(faction):
    world = CONTENT_DOCUMENTS["maps.json"]["worlds"][faction.world]
    locations = world["locations"]
    current = next((row for row in locations if row["id"] == faction.location_id), None)
    if current and (faction.founded_by_player or faction.player_founded_site or not current.get("min_realm_index", 0)):
        return current
    safe = [row for row in locations if not row.get("min_realm_index", 0)]
    if not safe:
        raise ValueError("此界面没有适合普通势力驻扎的地图")
    # Temples, schools and clans favour inhabited/mountain sites, never lethal regions.
    preferences = {"buddhist": ("寺", "山", "峰"), "confucian": ("城", "院", "书"),
                   "demonic": ("谷", "渊", "城")}.get(faction.path, ("山", "峰", "谷"))
    preferred = [row for row in safe if any(word in row.get("name", "") for word in preferences)]
    pool = preferred or safe
    index = int.from_bytes(hashlib.sha256(faction.id.encode()).digest()[:4], "big") % len(pool)
    faction.location_id = pool[index]["id"]
    return pool[index]


def can_enter_faction(faction, npc):
    site = faction_site(faction)
    rank = int(npc.get("realm_index", 0)) if isinstance(npc, dict) else npc.realm_index
    world = npc.get("world", faction.world) if isinstance(npc, dict) else npc.world
    return world == faction.world and rank >= int(site.get("min_realm_index", 0))


def require_faction_admission(faction, npc):
    if not can_enter_faction(faction, npc):
        site = faction_site(faction)
        rank = int(site.get("min_realm_index", 0))
        raise ValueError(f"{faction.name}位于{site['name']}，来者须身在本界且至少达到{REALMS[rank].name}境")


def ensure_faction_sites(game):
    changed = False
    for faction in [*game.sects.values(), *([game.family] if game.family else [])]:
        old = faction.location_id
        faction_site(faction)
        changed = changed or old != faction.location_id
    return changed


def war_site(maps, war):
    locations = maps.worlds[war["world"]]["locations"]
    safe = [row for row in locations if not row.get("min_realm_index", 0)]
    pool = safe or locations
    current = next((row for row in pool if row["id"] == war.get("location_id")), None)
    if current is None:
        identity = f"{war.get('attacker_id')}|{war.get('defender_id')}|{war.get('start_unit', 0)}"
        index = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:4], "big") % len(pool)
        current = pool[index]
        war["location_id"] = current["id"]
    return current

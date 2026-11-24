"""Read the rank an NPC presents without changing the person or drawing game RNG."""
from ..combat_attributes import read
from ..content_registry import REALMS, WORLD_SYSTEMS


def stable_roll(identity):
    return sum((index + 1) * ord(character) for index, character in enumerate(identity))


def concealed_rank(npc, roll_for=stable_roll):
    realm = read(npc, "realm_index", 0)
    saved = read(npc, "concealed_realm_index")
    if saved is not None and 0 <= int(saved) < realm:
        return int(saved), max(1, min(int(read(npc, "concealed_layer") or 1), REALMS[int(saved)].layers))
    if realm < 2:
        return None
    rules = WORLD_SYSTEMS.get("secret_arts", {})
    roll = roll_for(f"{read(npc, 'id')}|{read(npc, 'name')}|收敛修为")
    chance = max(0.0, min(1.0, float(rules.get("npc_concealment_chance", 0.18))))
    if roll % 10_000 >= round(chance * 10_000):
        return None
    maximum_drop = min(realm, max(1, int(rules.get("npc_max_realm_drop", 3))))
    shown = realm - 1 - (roll // 10_000) % maximum_drop
    return shown, 1 + (roll // 100_000) % REALMS[shown].layers

"""Stable, inexpensive social hints; family actors are created only on interaction."""
from __future__ import annotations

import hashlib
import random
from functools import lru_cache

from ..models import GameState, SectNpc

FIXED_COUPLE = {
    "zeng_canghai": ("曾沧海", "male", "wu_xingyun", "巫行云"),
    "wu_xingyun": ("巫行云", "female", "zeng_canghai", "曾沧海"),
}


@lru_cache(maxsize=4096)
def _hint(seed: int, npc_id: str) -> tuple[str, int]:
    value = int.from_bytes(hashlib.sha256(f"social:{seed}:{npc_id}".encode()).digest()[:8], "big")
    rng = random.Random(value)
    name = rng.choice("沈柳顾陆温谢宁苏") + rng.choice(("知微", "清辞", "云舒", "照水", "望舒", "听澜", "长宁", "怀真")) if rng.random() < .32 else ""
    count = rng.randint(1, 3) if rng.random() < .18 else 0
    return name, count


def social_hint(game: GameState, npc: SectNpc) -> dict:
    """Pure presentation: neither save mutations nor gameplay RNG consumption."""
    if npc.id in FIXED_COUPLE:
        return {"companion_name": FIXED_COUPLE[npc.id][3], "concubine_count": 0}
    partner = game.player.dao_companion
    if partner and partner.get("id") == npc.id and partner.get("alive", True):
        return {"companion_name": game.player.name, "concubine_count": 0}
    if npc.social_profile is not None:
        return {key: npc.social_profile.get(key) for key in ("companion_name", "concubine_count")}
    if npc.age < 16:
        return {"companion_name": "", "concubine_count": 0}
    name, count = _hint(game.seed, npc.id)
    return {"companion_name": name, "concubine_count": count if npc.gender == "male" else 0}


def instantiate_social(game: GameState, npc: SectNpc) -> None:
    """One bounded partner, no recursive family generation and no duplicate actors."""
    if npc.social_profile is not None:
        return
    hint = social_hint(game, npc)
    npc.social_profile = dict(hint)
    if npc.id in FIXED_COUPLE:
        partner_id = FIXED_COUPLE[npc.id][2]
        npc.social_profile["companion_id"] = partner_id
        partner = game.world_npcs.get(partner_id)
        if partner:
            partner.social_profile = {"companion_id": npc.id, "companion_name": npc.name, "concubine_count": 0}
        return
    if not hint["companion_name"] or (game.player.dao_companion and game.player.dao_companion.get("id") == npc.id):
        return
    partner_id = f"partner_{npc.id}"
    npc.social_profile["companion_id"] = partner_id
    if partner_id in game.notable_npcs:
        return
    partner = SectNpc(
        id=partner_id, name=hint["companion_name"], title=f"{npc.name}的道侣",
        realm_index=npc.realm_index, layer=max(1, npc.layer - 1), age=npc.age,
        lifespan=npc.lifespan, spirit_root=npc.spirit_root, path=npc.path,
        race=npc.race, world=npc.world, gender="female" if npc.gender == "male" else "male",
        social_profile={"companion_id": npc.id, "companion_name": npc.name, "concubine_count": 0},
    )
    game.notable_npcs[partner_id] = partner


def migrate_fixed_couple(game: GameState) -> bool:
    changed = False
    for npc_id, (name, gender, _, _) in FIXED_COUPLE.items():
        npc = game.world_npcs.get(npc_id)
        if npc and (npc.name != name or npc.gender != gender):
            npc.name, npc.gender = name, gender
            changed = True
        if npc:
            profile = {"companion_id": FIXED_COUPLE[npc_id][2], "companion_name": FIXED_COUPLE[npc_id][3], "concubine_count": 0}
            if npc.social_profile != profile:
                npc.social_profile = profile
                changed = True
        for relation in [game.player.master, game.player.dao_companion, *game.player.dao_friends,
                         *game.player.disciples, *game.player.concubines, *game.player.party]:
            if relation and relation.get("id") == npc_id and (relation.get("name") != name or relation.get("gender") != gender):
                relation.update(name=name, gender=gender)
                changed = True
    return changed

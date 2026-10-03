"""Explicit demonic annual operations; callers own composition."""
from __future__ import annotations

from ...npc_custody import settle_puppet_person

import random

from ...models import GameState, HistoryRecord
from ...rules import combat_power, max_hp
from .dependencies import DemonicAnnualDependencies


def _annual_demonic_update(deps: DemonicAnnualDependencies, game: GameState, rng: random.Random) -> None:
    player = game.player
    rules = deps._demonic_rules()
    for puppet in player.puppets:
        kind = str(puppet.get("type"))
        if puppet.get("alive", True) and kind in {"corpse", "living"}:
            contribution = max(0.1, int(puppet.get("realm_index", 0)) * (0.16 if kind == "corpse" else 0.34))
            deps._add_opportunity(player, contribution)
    for puppet in list(player.puppets):
        if not puppet.get("alive", True) or puppet.get("type") != "living":
            continue
        growth = 1 + int(puppet.get("realm_index", 0)) * 0.12
        puppet["control"] = max(0.0, float(puppet.get("control", 100)) - float(rules["living_control_loss_per_year"]) * growth)
        if puppet["control"] >= 25:
            continue
        chance = (25 - puppet["control"]) / 100 * 0.18
        if rng.random() >= chance:
            continue
        settle_puppet_person(game, puppet, outcome="released")
        player.puppets.remove(puppet)
        ratio = float(puppet.get("combat_power", 0)) / max(1.0, combat_power(player))
        if ratio > 1.15 and rng.random() < min(0.85, 0.35 + (ratio - 1) * 0.25):
            damage = max_hp(player) * min(0.9, 0.35 + ratio * 0.12)
            player.hp = max(0.0, player.hp - damage)
            if player.hp <= 0:
                deps._die(game, f"活傀{puppet['name']}挣脱控制后反杀主人", "SYS_LIVING_PUPPET_REVOLT")
                return
            outcome = f"反噬令你损失 {damage:.0f} HP"
        else:
            outcome = "其未能反杀你，趁乱遁走"
        game.history.append(HistoryRecord(
            "SYS_LIVING_PUPPET_REVOLT", 1, player.age, "活傀反噬", puppet["id"], "escaped",
            f"{puppet['name']}的控制度降至临界点，挣脱印记；{outcome}。",
            {"puppet_id": puppet["id"], "control": puppet["control"]}, ["system", "puppet", "negative"],
        ))

    unrefined = [entry for entry in player.foreign_souls if not entry.get("refined")]
    if not unrefined:
        return
    burden = sum(float(entry.get("strength", 1)) for entry in unrefined)
    chance = min(0.65, float(rules["soul_backlash_base"]) * burden)
    if rng.random() < chance:
        damage = max_hp(player) * min(0.6, 0.06 + burden * 0.018)
        player.hp = max(0.0, player.hp - damage)
        player.heart_demon += deps._sage_scaled_gain(
            player, burden * 0.5, "heart_demon_gain_reduction",
        )
        game.history.append(HistoryRecord(
            "SYS_SOUL_BACKLASH", 1, player.age, "元神反噬", None, "backlash",
            f"{len(unrefined)}道未炼化元神同时反扑，HP -{damage:.0f}，心魔 +{burden * 0.5:.1f}。",
            {"souls": len(unrefined), "burden": burden}, ["system", "demonic", "soul", "negative"],
        ))
        if player.hp <= 0:
            deps._die(game, "吞噬的外来元神反客为主，撕碎识海", "SYS_SOUL_BACKLASH_DEATH")

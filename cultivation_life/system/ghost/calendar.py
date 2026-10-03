"""Explicit ghost calendar operations; callers own composition."""
from __future__ import annotations

import random

from ...content_registry import WORLD_SYSTEMS
from ...models import GameState, HistoryRecord, SectNpc
from ..ghost_resources import ghost_phase_two_config as ghost_phase_two_config
from .dependencies import GhostCalendarDependencies


def _advance_ghost_phase_two_year(deps: GhostCalendarDependencies, game: GameState, rng: random.Random) -> None:
    if not ghost_phase_two_config().get("enabled", False):
        return
    deps._ensure_ghost_parade(game, rng)
    parade = game.ghost_parade
    if not parade:
        return
    phase_rng = random.Random(f"{game.seed}:ghost-phase-two:{game.player.age}")
    unit = max(1, int(WORLD_SYSTEMS["time_units"][str(game.player.realm_index)]))
    announce_age = int(parade.get("start_age", game.player.age)) - 2 * unit
    if not parade.get("announced") and game.player.age >= announce_age:
        parade["announced"] = True
        parade["status"] = "announced"
        game.history.append(HistoryRecord(
            "SYS_GHOST_PARADE_ANNOUNCED", 1, game.player.age, "百鬼将行", None, "announced",
            "阴风先至，百鬼夜行将在两个游戏时间单位后降临；地图已经标出鬼门所在。",
            {"location_id": parade.get("location_id"), "start_age": parade.get("start_age")},
            ["system", "ghost", "parade", "announcement"],
        ))
    if game.player.age >= int(parade.get("start_age", 10**18)) and parade.get("status") != "active":
        parade["status"] = "active"
        parade["souls"] = deps._generate_parade_souls(game, phase_rng)
        game.history.append(HistoryRecord(
            "SYS_GHOST_PARADE_STARTED", 1, game.player.age, "百鬼夜行", None, "active",
            "鬼门洞开，游魂并非临时数值，而以姓名、修为、魂压与魂性现身世间。",
            {"location_id": parade.get("location_id"), "soul_count": len(parade["souls"])},
            ["system", "ghost", "parade", "world_event"],
        ))
    if game.player.age >= int(parade.get("end_age", 10**18)):
        escaped = len(parade.get("souls", []))
        game.history.append(HistoryRecord(
            "SYS_GHOST_PARADE_ENDED", 1, game.player.age, "鬼门复闭", None, "ended",
            f"夜行散去，仍有 {escaped} 道未被拘束的魂魄归入幽暗。下一次异动将在未来重新孕生。",
            {"escaped_souls": escaped}, ["system", "ghost", "parade"],
        ))
        game.ghost_parade = {}
        deps._ensure_ghost_parade(game, rng)
    captor = game.player.ghost_captor
    if captor:
        captor["followed_years"] = int(captor.get("followed_years", 0)) + 1
        if phase_rng.random() < 0.18:
            locations = [row["id"] for row in deps.maps.public_map(
                game.player.world, game.player.location_id, game.player.realm_index,
                WORLD_SYSTEMS["world_names"].get(game.player.world, game.player.world),
            ).get("locations", []) if row.get("travel_status") in {"ok", "current"}]
            if locations:
                captor["location_id"] = phase_rng.choice(locations)
        game.player.location_id = captor.get("location_id", game.player.location_id)
        if phase_rng.random() < 0.12:
            from ...rules import combat_power
            contribution = combat_power(game.player)
            captor_power = max(1.0, float(captor.get("combat_power", 1.0)))
            owner_id = str(captor.get("npc_id") or captor.get("id", ""))
            owner = deps._find_npc(game, owner_id) or SectNpc(
                owner_id or f"ghost_owner_{game.seed}_{game.player.age}",
                str(captor.get("name", "拘魂者")), "拘魂者",
                int(captor.get("realm_index", game.player.realm_index)),
                int(captor.get("layer", 1)), game.player.age, None,
                spirit_root=str(captor.get("spirit_root", "none")),
                path=str(captor.get("path", "dao")), race=str(captor.get("race", "human")),
                world=game.player.world,
            )
            opponents = [
                npc for npc in deps._all_world_npcs(game)
                if npc.alive and npc.world == game.player.world and npc.id != owner.id
            ]
            opponent = phase_rng.choice(opponents) if opponents else None
            opponent_power = deps._npc_power(opponent) if opponent else captor_power * phase_rng.uniform(0.55, 1.25)
            won = phase_rng.random() < min(
                0.92,
                (captor_power + contribution * 0.45)
                / (captor_power + contribution * 0.45 + opponent_power),
            )
            transfer = (
                deps._maybe_transfer_player_dependency(
                    game, owner, opponent, phase_rng, context="ghost_vassal_battle",
                )
                if not won and opponent else ""
            )
            game.history.append(HistoryRecord(
                "SYS_GHOST_VASSAL_BATTLE", 1, game.player.age, "魂仆随战", None,
                "victory" if won else "defeat",
                f"{captor.get('name', '拘魂者')}卷入争斗，你被魂印强制召出参战；"
                + ("合力压下了对手。" if won else "主仆皆负伤退走。")
                + (f" {transfer}" if transfer else ""),
                {
                    "ghost_contribution": contribution, "captor_power": captor_power,
                    "opponent_id": opponent.id if opponent else None,
                },
                ["system", "ghost", "controlled", "combat"],
            ))

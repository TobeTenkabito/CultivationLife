"""Reproducible incremental costs; timings are diagnostics, not flaky test gates.

Run: python scripts/benchmark_npc_combat.py [--world-step]
The optional world step measures the existing entire 100-year action as well.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import random
from statistics import median
import sys
import tempfile
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.models import SectNpc
from cultivation_life.system.combat import npc_lifecycle
from cultivation_life.system.combat.npc_battle import resolve_npc_engagement


def measure(factory, operation, repeats=7):
    samples = []
    for _ in range(repeats):
        subject = factory()
        started = perf_counter()
        operation(subject)
        samples.append((perf_counter() - started) * 1000)
    return round(median(samples), 3)


def main():
    config = copy.deepcopy(WORLD_SYSTEMS["transcendent_combat"])

    def actors(count):
        rows = [SectNpc(str(index), "NPC", "", 9, 1, 1000, None, world="celestial") for index in range(count)]
        for npc in rows:
            npc_lifecycle.initialize_native(npc, config, now=100)
            npc.transcendence["current"] = 0
        return rows

    result = {}
    for elapsed in (1, 100, 10000):
        result[f"10000_ledgers_{elapsed}_years_ms"] = measure(
            lambda: actors(10000), lambda rows: [npc_lifecycle.settle(npc, 100 + elapsed, config) for npc in rows])
    mortals = [SectNpc(str(index), "NPC", "", 8, 1, 1000, None) for index in range(48)]
    result["1000_mortal_engagement_checks_ms"] = measure(
        lambda: ([(npc, 1000) for npc in mortals[:24]], [(npc, 1000) for npc in mortals[24:]], random.Random(1)),
        lambda args: [resolve_npc_engagement(args[0], args[1], config, args[2], now=200) for _ in range(1000)])
    # Deliberately large coverage: 48 actors each cover up to 48 targets.
    voisinage_config = copy.deepcopy(config)
    voisinage_config["voisinages"] = [dict(id="bench", name="Bench", attainment="bench", required_level=1,
                                      strength=100, opening_cost=10, upkeep_cost=1, effect="suppress",
                                      effect_cost=1, max_targets=48)]

    def voisinage_rosters():
        rows = actors(48)
        for npc in rows:
            npc.transcendence.update(current=1000, voisinage_ids=["bench"], attainments={"bench": 1})
        return ([(npc, 1000) for npc in rows[:24]], [(npc, 1000) for npc in rows[24:]], random.Random(1))

    result["48_voisinage_actors_5_rounds_ms"] = measure(
        voisinage_rosters, lambda args: resolve_npc_engagement(args[0], args[1], voisinage_config, args[2], now=200))
    if "--world-step" in sys.argv:
        from cultivation_life.engine import GameEngine
        from cultivation_life.rules import max_hp, max_mp
        with tempfile.TemporaryDirectory() as directory:
            engine = GameEngine(ROOT, Path(directory))
            created = engine.create_game("Benchmark", "supreme_metal", "dao", seed=7190, preset_id="true_immortal")
            game = engine.store.load(created["id"])
            game.player.world = "celestial"
            game.player.location_id = engine.maps.default_location("celestial")
            game.player.realm_index, game.player.layer = 9, 1
            game.player.lifespan = None
            game.player.immortal_power_converted = True
            game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
            game.player.next_tribulation_age = None
            game.player.fame, game.player.karma, game.player.sha_qi = 0, 0, 0
            game.pending_event = None
            game.heavenly_court = {}
            engine._ensure_heavenly_court(game, random.Random(7190))
            observer = actors(1)[0]
            observer.id = "benchmark_idle_immortal"
            observer.transcendence.pop("lifecycle", None)
            npc_lifecycle.settle(observer, game.player.age, config)
            game.notable_npcs[observer.id] = observer
            engine.store.save(game)
            # Pin the requested 100-year case so future balance changes do not
            # silently change the diagnostic workload.
            with patch.dict(WORLD_SYSTEMS["time_units"], {"9": 100}), \
                    patch.object(engine, "_advance_guixu_calendar", return_value=False), \
                    patch.object(npc_lifecycle, "settle", wraps=npc_lifecycle.settle) as calls:
                started = perf_counter()
                engine.advance(game.id, "rest", 1)
                result["entire_world_action_ms"] = round((perf_counter() - started) * 1000, 3)
                result["lifecycle_settlements_during_action"] = calls.call_count
            after = engine.store.load(game.id)
            result["actual_years_advanced"] = after.player.age - game.player.age
            result["pending_event"] = after.pending_event.get("id") if after.pending_event else None
            result["idle_npc_ledger_untouched"] = (after.notable_npcs[observer.id].transcendence == observer.transcendence)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

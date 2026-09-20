"""Compare every quick-start's observable V1 contract with the V2 runtime.

The baseline must be a checkout of commit
83641711ef1e8f8d5f74dc0ad973d6a07c36932f.  Both runtimes execute in their
own Python processes so importing the identically named packages cannot leak
modules or global content registries across versions.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


V1_COMMIT = "83641711ef1e8f8d5f74dc0ad973d6a07c36932f"
PRESETS = (
    "core", "ghost_core", "demonic_core", "nascent", "spirit", "void",
    "integration", "mahayana", "true_immortal",
)


V1_SCRIPT = r'''
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from cultivation_life.engine import GameEngine

result = {}
with TemporaryDirectory() as directory:
    engine = GameEngine(Path.cwd(), Path(directory) / "saves")
    for preset_id in %r:
        game = engine.create_game(
            "", "none", "dao", seed=100, preset_id=preset_id
        )
        player = game["player"]
        result[preset_id] = {
            "name": player["name"],
            "age": player["age"],
            "world_age": player["world_age"],
            "lifespan": player["lifespan"],
            "world": player["world"],
            "realm_id": player["realm_id"],
            "layer": player["layer"],
            "opportunity": player["opportunity"],
            "karma": player["karma"],
            "sha_qi": player["sha_qi"],
            "fame": player["fame"],
            "max_hp": player["max_hp"],
            "max_mp": player["max_mp"],
            "combat_power": player["combat_power"],
            "qi_mastery": {row["source"]: row["level"] for row in player["qi_mastery"]},
            "known_techniques": [row["id"] for row in player["known_techniques"]],
            "main_technique": (player.get("technique") or {}).get("id"),
            "support_technique": (player.get("support_technique") or {}).get("id"),
            "combat_techniques": [row["id"] for row in player["combat_techniques"]],
            "inventory": {row["id"]: row["quantity"] for row in player["inventory"]},
            "additional_roots": player["additional_roots"],
            "converted": player["immortal_power_converted"],
            "conversion_stage": player["immortal_conversion_stage"],
            "next_tribulation_age": player["next_tribulation_age"],
            "birth_age": game["history"][0]["age"],
            "court_initialized": bool(game["heavenly_court"].get("initialized")),
            "court_seats": int(game["heavenly_court"].get("seat_count", 0)),
        }
print(json.dumps(result, ensure_ascii=False))
''' % (PRESETS,)


V2_SCRIPT = r'''
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from cultivation_life import GameEngine
from cultivation_life.v1_facade import game_view

result = {}
with TemporaryDirectory() as directory:
    engine = GameEngine(Path(directory) / "games.sqlite3")
    for preset_id in %r:
        game = game_view(
            engine.create_game("", seed=100, preset_id=preset_id), {}
        )
        player = game["player"]
        result[preset_id] = {
            "name": player["name"],
            "age": player["age"],
            "world_age": player["world_age"],
            "lifespan": player["lifespan"],
            "world": player["world"],
            "realm_id": player["realm_id"],
            "layer": player["layer"],
            "opportunity": player["opportunity"],
            "karma": player["karma"],
            "sha_qi": player["sha_qi"],
            "fame": player["fame"],
            "max_hp": player["max_hp"],
            "max_mp": player["max_mp"],
            "combat_power": player["combat_power"],
            "qi_mastery": {row["source"]: row["level"] for row in player["qi_mastery"]},
            "known_techniques": [row["id"] for row in player["known_techniques"]],
            "main_technique": (player.get("technique") or {}).get("id"),
            "support_technique": (player.get("support_technique") or {}).get("id"),
            "combat_techniques": [row["id"] for row in player["combat_techniques"]],
            "inventory": {row["id"]: row["quantity"] for row in player["inventory"]},
            "additional_roots": player["additional_roots"],
            "converted": player["immortal_power_converted"],
            "conversion_stage": player["immortal_conversion_stage"],
            "next_tribulation_age": game["tribulation"]["next_age"],
            "birth_age": game["history"][0]["age"],
            "court_initialized": bool(game["heavenly_court"].get("initialized")),
            "court_seats": int(game["heavenly_court"].get("seat_count", 0)),
        }
print(json.dumps(result, ensure_ascii=False))
''' % (PRESETS,)


def run_snapshot(root: Path, source: str) -> dict[str, dict[str, Any]]:
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", source],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return dict(json.loads(completed.stdout))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1-root", type=Path, required=True)
    parser.add_argument(
        "--current-root", type=Path,
        default=Path(__file__).resolve().parent.parent,
    )
    arguments = parser.parse_args()
    old = run_snapshot(arguments.v1_root.resolve(), V1_SCRIPT)
    new = run_snapshot(arguments.current_root.resolve(), V2_SCRIPT)
    mismatches = {
        preset_id: {
            field: {"v1": old[preset_id].get(field), "v2": new[preset_id].get(field)}
            for field in sorted(set(old[preset_id]) | set(new[preset_id]))
            if old[preset_id].get(field) != new[preset_id].get(field)
        }
        for preset_id in PRESETS
    }
    mismatches = {key: value for key, value in mismatches.items() if value}
    if mismatches:
        print(json.dumps(mismatches, ensure_ascii=False, indent=2))
        return 1
    print(
        f"V1/V2 quick-start parity passed: {len(PRESETS)} presets, "
        f"baseline {V1_COMMIT}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

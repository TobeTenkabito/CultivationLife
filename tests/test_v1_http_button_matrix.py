from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Any

from cultivation_life.server import HTTPCommandRegistry


ROOT = Path(__file__).resolve().parent.parent
V1_COMMIT = "83641711ef1e8f8d5f74dc0ad973d6a07c36932f"


class _RecordingEngine:
    """Records adapter calls without replacing any registry parsing logic."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, name: str):
        def method(*args: Any, **kwargs: Any) -> dict[str, Any]:
            self.calls.append((name, args, kwargs))
            return {"operation": name}

        return method


class V1HTTPButtonMatrixTests(unittest.TestCase):
    maxDiff = None

    @staticmethod
    def _frontend_operations() -> set[str]:
        source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        literal = set(re.findall(
            r"/api/games/\$\{game\.id\}/([a-z][a-z0-9-]+)", source
        ))
        # These are the only operation names selected dynamically by the
        # frozen V1 client.  Keep them explicit so a future template edit
        # cannot silently evade the matrix.
        dynamic = {
            "monster-evolve", "spirit-crossing",
            "celestial-ascension", "asura-ascension",
        }
        return literal | dynamic

    def test_all_100_frozen_v1_operations_reach_the_v2_http_adapter(self) -> None:
        engine = _RecordingEngine()
        registry = HTTPCommandRegistry(engine)  # type: ignore[arg-type]
        frontend = self._frontend_operations()
        self.assertEqual(len(frontend), 100, V1_COMMIT)
        self.assertEqual(frontend - set(registry.operations), set())

        payload: dict[str, Any] = {
            "action": "inspect", "units": 1, "years": 1,
            "target_item_id": "item", "materials": [],
            "lot_id": "lot", "asset_id": "asset", "item_id": "item",
            "start_price": 1, "alias": "alias", "npc_id": "npc",
            "target_id": "target", "side": "buy", "offer_id": "offer",
            "result_id": "result", "pattern": "pattern", "choice_id": "choice",
            "method": "none", "artifact_id": "artifact", "name": "name",
            "destination": "human", "destination_world_id": "human",
            "evolution_id": "evolution", "rules": [], "enabled": True,
            "disciple_id": "disciple", "kind": "sect", "content_id": "content",
            "accept": True, "technique_id": "technique", "slot": None,
            "status": "neutral", "reward_id": "reward",
            "formation_id": "formation", "loadout_id": "formation",
            "owner_kind": "player", "ground_formation_id": "ground",
            "supply_id": "supply", "quantity": 1, "soul_id": "soul",
            "all": False, "enact": False, "influence_spend": 0,
            "pledge_id": "pledge", "destination_id": "destination",
            "filters": {}, "candidate_ids": [], "player_vote": True,
            "resolution_type": "policy", "authority": "sect",
            "puppet_id": "puppet", "plot_id": "plot", "mp_ratio": 0.1,
            "booster_id": "", "plant_id": "plant", "form_id": "form",
            "mode": "direct", "stat_id": "might", "character_id": "npc",
            "war_id": "war", "ally_id": "ally", "term": "white_peace",
            "target_power_id": "power", "third_party_id": "third",
            "third_status": "neutral", "concede": False,
            "setting": "combat_popup", "invited_ids": [],
        }
        for operation in sorted(frontend):
            with self.subTest(operation=operation):
                before = len(engine.calls)
                response = registry.dispatch("game", operation, dict(payload))
                self.assertEqual(len(engine.calls), before + 1)
                self.assertIn("operation", response)

    def test_registry_only_additions_are_known_internal_compatibility_routes(self) -> None:
        engine = _RecordingEngine()
        registered = set(
            HTTPCommandRegistry(engine).operations  # type: ignore[arg-type]
        )
        self.assertEqual(
            registered - self._frontend_operations(),
            {"ascend-world", "fight", "ghost-reincarnate", "market-refresh"},
        )


if __name__ == "__main__":
    unittest.main()

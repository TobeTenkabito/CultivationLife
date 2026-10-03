from __future__ import annotations
from functools import cached_property
from .tianji.wiring import bind_tianji
from .tianji import forging as tianji_forging
from .tianji import generation as tianji_generation
from .tianji import intelligence as tianji_intelligence
from .tianji import npcs as tianji_npcs
from .tianji import presentation as tianji_presentation
from .tianji import state as tianji_state

import copy
import random
from typing import Any

from ..content_registry import WORLD_SYSTEMS
from ..combat_rule_engine import describe_rule
from ..monster_bloodline_rules import (
    describe_generated_trait,
)
from ..models import GameState


TIANJI_GENERATION_VERSION = 8
SLOT_WEIGHTS = (0.40, 0.20, 0.20, 0.20)
TIANJI_WINDOW_SCHEDULES = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "last",
    "penultimate",
    "first_two",
    "first_three",
    "first_four",
    "last_two",
    "last_three",
    "after_second",
    "after_third",
    "first_and_last",
    "second_and_fourth",
    "odd",
    "even",
    "random",
    "random_two",
)
TIANJI_ATTRIBUTE_NAMES: dict[str, str] = {
    "might": "威能",
    "guard": "防护",
    "mobility": "身法",
    "sense": "神识",
    "sustain": "续航",
    "breach": "破法",
    "max_hp": "气血上限",
    "max_mp": "法力上限",
    "tribulation_reduction": "雷劫与天劫伤害减免",
    "player_debuff_immunity": "削弱效果免疫",
    "enemy_escape_lock": "敌方遁逃封锁",
}
PRIMITIVES: tuple[dict[str, Any], ...] = (
    {"id": "might", "name": "神威", "stat": "might", "low": 1.06, "high": 1.22},
    {"id": "guard", "name": "镇守", "stat": "guard", "low": 1.06, "high": 1.22},
    {"id": "mobility", "name": "遁空", "stat": "mobility", "low": 1.05, "high": 1.20},
    {"id": "sense", "name": "照神", "stat": "sense", "low": 1.06, "high": 1.22},
    {"id": "sustain", "name": "归元", "stat": "sustain", "low": 1.05, "high": 1.20},
    {"id": "breach", "name": "破界", "stat": "breach", "low": 1.06, "high": 1.22},
    {
        "id": "enemy_guard",
        "name": "蚀甲",
        "enemy_stat": "guard",
        "low": 0.80,
        "high": 0.94,
    },
    {
        "id": "enemy_mobility",
        "name": "锁空",
        "enemy_stat": "mobility",
        "low": 0.82,
        "high": 0.95,
    },
    {
        "id": "enemy_sense",
        "name": "蒙识",
        "enemy_stat": "sense",
        "low": 0.82,
        "high": 0.95,
    },
    {
        "id": "tribulation",
        "name": "渡厄",
        "persistent": "tribulation_reduction",
        "low": 0.05,
        "high": 0.25,
    },
    {
        "id": "vitality",
        "name": "护生",
        "persistent": "max_hp",
        "low": 0.03,
        "high": 0.18,
    },
    {"id": "mana", "name": "法海", "persistent": "max_mp", "low": 0.04, "high": 0.22},
    {
        "id": "debuff_ward",
        "name": "万法不侵",
        "trait": "player_debuff_immunity",
        "low": 0.25,
        "high": 1.0,
    },
    {
        "id": "escape_lock",
        "name": "禁绝虚空",
        "trait": "enemy_escape_lock",
        "low": 0.25,
        "high": 1.0,
    },
)


def tianji_config() -> dict[str, Any]:
    value = WORLD_SYSTEMS.get("tianji_artifacts", {})
    return value if isinstance(value, dict) else {}


def tianji_content_available() -> bool:
    config = tianji_config()
    return bool(config.get("enabled") and int(config.get("artifact_count", 0)) == 100)


def _stable_rng(seed: int, stream: str) -> random.Random:
    return random.Random(
        f"{seed}:tianji-artifacts:v{TIANJI_GENERATION_VERSION}:{stream}"
    )


def _scaled_multiplier(value: float, ratio: float) -> float:
    return round(1.0 + (float(value) - 1.0) * ratio, 6)


def _scaled_effects(
    effects: list[dict[str, Any]], ratio: float
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    combat: list[dict[str, Any]] = []
    persistent: dict[str, float] = {}
    for raw in effects:
        effect = copy.deepcopy(raw)
        result: dict[str, Any] = {
            "source": effect["name"],
            "name": effect["name"],
            "tianji_primitive": effect["primitive"],
            "conditions": list(map(str, effect.get("conditions", []))),
        }
        if isinstance(effect.get("rule"), dict):
            rule = copy.deepcopy(effect["rule"])
            rule["effect_scale"] = round(max(0.0, min(1.20, ratio)), 6)
            result["generated_rules"] = [rule]
            combat.append(result)
            continue
        if effect.get("player_stat_multipliers"):
            result["player_stat_multipliers"] = {
                key: _scaled_multiplier(value, ratio)
                for key, value in effect["player_stat_multipliers"].items()
            }
        if effect.get("enemy_stat_multipliers"):
            result["enemy_stat_multipliers"] = {
                key: _scaled_multiplier(value, ratio)
                for key, value in effect["enemy_stat_multipliers"].items()
            }
        if effect.get("trait"):
            # Boolean rules degrade to a numeric resistance below true-body
            # strength; only a complete true body grants the actual immunity.
            if ratio >= 0.999:
                result["traits"] = [effect["trait"]]
            else:
                result["tianji_resistance"] = round(min(1.0, ratio), 4)
        if effect.get("persistent"):
            key = str(effect["persistent"])
            value = float(effect["magnitude"]) * ratio
            if key in {"max_hp", "max_mp"}:
                # Existing crafted stats are absolute, so the generated item
                # stores a conservative fixed value alongside combat power.
                persistent[key] = persistent.get(key, 0.0) + value * 1_000_000
            else:
                persistent[key] = persistent.get(key, 0.0) + value
        if any(
            key in result
            for key in (
                "player_stat_multipliers",
                "enemy_stat_multipliers",
                "traits",
                "tianji_resistance",
            )
        ):
            combat.append(result)
    return combat, persistent


def _tianji_effect_description(effect: dict[str, Any]) -> str:
    if isinstance(effect.get("rule"), dict):
        rule = effect["rule"]
        return (
            describe_rule(rule)
            if int(rule.get("schema_version", 1)) >= 2
            else describe_generated_trait(rule)
        )
    prefix = ""
    if effect.get("player_stat_multipliers"):
        stat, value = next(iter(effect["player_stat_multipliers"].items()))
        body = f"自身{TIANJI_ATTRIBUTE_NAMES.get(str(stat), str(stat))}提高 {(float(value) - 1):.1%}"
    elif effect.get("enemy_stat_multipliers"):
        stat, value = next(iter(effect["enemy_stat_multipliers"].items()))
        body = f"敌方{TIANJI_ATTRIBUTE_NAMES.get(str(stat), str(stat))}降低 {(1 - float(value)):.1%}"
    elif effect.get("trait"):
        trait = TIANJI_ATTRIBUTE_NAMES.get(str(effect["trait"]), str(effect["trait"]))
        body = f"真体获得完整的{trait}规则，仿品按仿制度转化为对应抗性"
    else:
        stat = str(effect.get("persistent", "未知属性"))
        body = f"{TIANJI_ATTRIBUTE_NAMES.get(stat, stat)}提高 {float(effect.get('magnitude', 0)):.1%}"
    return f"{prefix}{body}。"


class TianjiSystemMixin:
    @staticmethod
    def _tianji_tag_similarity(
        required: dict[str, float], supplied: dict[str, float]
    ) -> float:
        if not required or not supplied:
            return 0.0
        shared = set(required).intersection(supplied)
        if not shared:
            return 0.0
        numerator = sum(
            min(float(required[key]), float(supplied[key])) for key in shared
        )
        denominator = max(1e-9, sum(float(value) for value in required.values()))
        return min(1.0, numerator / denominator)

    @staticmethod
    def _tianji_closeness_factor(closeness: float) -> float:
        points = (
            (0.0, 0.15),
            (0.2, 0.30),
            (0.4, 0.55),
            (0.6, 0.80),
            (0.8, 1.0),
            (1.0, 1.20),
        )
        value = max(0.0, min(1.0, closeness))
        for (left_x, left_y), (right_x, right_y) in zip(points, points[1:]):
            if value <= right_x:
                progress = (value - left_x) / max(0.0001, right_x - left_x)
                return left_y + (right_y - left_y) * progress
        return 1.20

    @staticmethod
    def _tianji_public_effect(effect: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": str(effect["name"]),
            "description": _tianji_effect_description(effect),
            "trigger": str(effect.get("trigger", "combat_start")),
            "replica_scaling": str(effect.get("replica_scaling", "numeric")),
        }

    @staticmethod
    def _tianji_config() -> dict[str, Any]:
        return tianji_config()

    @staticmethod
    def _tianji_artifact(state: dict[str, Any], artifact_id: str) -> dict[str, Any]:
        artifact = next(
            (row for row in state.get("artifacts", []) if row.get("id") == artifact_id),
            None,
        )
        if not artifact:
            raise ValueError("天工神机榜中没有这件法宝")
        return artifact

    @cached_property
    def _tianji_dependencies(self):
        return bind_tianji(
            self,
            _get_PRIMITIVES=lambda: PRIMITIVES,
            _get_SLOT_WEIGHTS=lambda: SLOT_WEIGHTS,
            _get_TIANJI_GENERATION_VERSION=lambda: TIANJI_GENERATION_VERSION,
            _get_TIANJI_WINDOW_SCHEDULES=lambda: TIANJI_WINDOW_SCHEDULES,
            _scaled_effects=lambda *args, **kwargs: _scaled_effects(*args, **kwargs),
            _stable_rng=lambda *args, **kwargs: _stable_rng(*args, **kwargs),
            _tianji_effect_description=lambda *args,
            **kwargs: _tianji_effect_description(*args, **kwargs),
            tianji_content_available=lambda *args, **kwargs: tianji_content_available(
                *args, **kwargs
            ),
        )

    def _tianji_material_instance(
        self,
        game: GameState,
        definition: dict[str, Any],
        rng: random.Random,
        source: str,
    ) -> dict[str, Any]:
        return tianji_forging._tianji_material_instance(
            self._tianji_dependencies.forging, game, definition, rng, source
        )

    def _append_tianji_market_offers(
        self,
        game: GameState,
        offers: list[dict[str, Any]],
        *,
        tier: int,
        market_name: str,
        location_id: str,
    ) -> None:
        return tianji_forging._append_tianji_market_offers(
            self._tianji_dependencies.forging,
            game,
            offers,
            tier=tier,
            market_name=market_name,
            location_id=location_id,
        )

    def _tianji_material_bought(
        self, game: GameState, instance: dict[str, Any]
    ) -> None:
        return tianji_forging._tianji_material_bought(
            self._tianji_dependencies.forging, game, instance
        )

    def _tianji_target_preview(
        self, game: GameState, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return tianji_forging._tianji_target_preview(
            self._tianji_dependencies.forging, game, payload
        )

    def preview_tianji_forge(
        self, game_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return tianji_forging.preview_tianji_forge(
            self._tianji_dependencies.forging, game_id, payload
        )

    def forge_tianji_artifact(
        self, game_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return tianji_forging.forge_tianji_artifact(
            self._tianji_dependencies.forging, game_id, payload
        )

    def _generate_tianji_materials(self, game: GameState) -> list[dict[str, Any]]:
        return tianji_generation._generate_tianji_materials(
            self._tianji_dependencies.generation, game
        )

    def _next_tianji_name(
        self,
        rng: random.Random,
        theme: dict[str, Any],
        mold_id: str,
        used_names: set[str],
        used_stems: set[str],
        used_prefixes: set[str],
        index: int,
    ) -> tuple[str, str]:
        return tianji_generation._next_tianji_name(
            self._tianji_dependencies.generation,
            rng,
            theme,
            mold_id,
            used_names,
            used_stems,
            used_prefixes,
            index,
        )

    def _next_tianji_buff_name(
        self,
        rng: random.Random,
        theme: dict[str, Any],
        core: str,
        used_names: set[str],
        index: int,
    ) -> str:
        return tianji_generation._next_tianji_buff_name(
            self._tianji_dependencies.generation, rng, theme, core, used_names, index
        )

    def _tianji_rule_effects(
        self, seed: int, artifact_id: str, theme: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return tianji_generation._tianji_rule_effects(
            self._tianji_dependencies.generation, seed, artifact_id, theme
        )

    def _generate_tianji_artifacts(
        self, game: GameState, materials: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return tianji_generation._generate_tianji_artifacts(
            self._tianji_dependencies.generation, game, materials
        )

    def _tianji_reveal(
        self, game: GameState, artifact_id: str, level: int, source: str
    ) -> bool:
        return tianji_intelligence._tianji_reveal(
            self._tianji_dependencies.intelligence, game, artifact_id, level, source
        )

    def _tianji_npc_conversation_clue(
        self, game: GameState, npc_id: str, rng: random.Random
    ) -> str:
        "Occasionally turn an actual NPC conversation into persistent intel."
        return tianji_intelligence._tianji_npc_conversation_clue(
            self._tianji_dependencies.intelligence, game, npc_id, rng
        )

    def _maybe_tianji_intelligence_event(
        self, game: GameState, rng: random.Random
    ) -> str | None:
        "Resolve a rare, non-clickable clue event after a real time action."
        return tianji_intelligence._maybe_tianji_intelligence_event(
            self._tianji_dependencies.intelligence, game, rng
        )

    def tianji_action(
        self, game_id: str, action: str, artifact_id: str
    ) -> dict[str, Any]:
        return tianji_intelligence.tianji_action(
            self._tianji_dependencies.intelligence, game_id, action, artifact_id
        )

    def debug_reveal_all_tianji(self, game_id: str) -> dict[str, Any]:
        return tianji_intelligence.debug_reveal_all_tianji(
            self._tianji_dependencies.intelligence, game_id
        )

    def _tianji_persistent_npcs(self, game: GameState, world: str) -> list[Any]:
        return tianji_npcs._tianji_persistent_npcs(
            self._tianji_dependencies.npcs, game, world
        )

    def _assign_tianji_holders_for_world(self, game: GameState, world: str) -> bool:
        return tianji_npcs._assign_tianji_holders_for_world(
            self._tianji_dependencies.npcs, game, world
        )

    def _inject_tianji_npc_artifacts(
        self, game: GameState, target: dict[str, Any]
    ) -> None:
        return tianji_npcs._inject_tianji_npc_artifacts(
            self._tianji_dependencies.npcs, game, target
        )

    def _tianji_observe_npc(self, game: GameState, npc_id: str) -> None:
        return tianji_npcs._tianji_observe_npc(
            self._tianji_dependencies.npcs, game, npc_id
        )

    def _tianji_preview_npc_power(
        self, game: GameState, target: dict[str, Any]
    ) -> None:
        return tianji_npcs._tianji_preview_npc_power(
            self._tianji_dependencies.npcs, game, target
        )

    def _tianji_handle_npc_kill(self, game: GameState, npc_id: str) -> str:
        return tianji_npcs._tianji_handle_npc_kill(
            self._tianji_dependencies.npcs, game, npc_id
        )

    def _public_tianji(self, game: GameState) -> dict[str, Any]:
        return tianji_presentation._public_tianji(
            self._tianji_dependencies.presentation, game
        )

    def debug_tianji_gameplay(self, game_id: str) -> list[dict[str, Any]]:
        "Return blueprint diagnostics without mutating the frozen definitions."
        return tianji_presentation.debug_tianji_gameplay(
            self._tianji_dependencies.presentation, game_id
        )

    def _refresh_tianji_artifact_names(self, game: GameState) -> None:
        "Migrate only generated names while preserving every frozen rule and recipe."
        return tianji_state._refresh_tianji_artifact_names(
            self._tianji_dependencies.state, game
        )

    def _refresh_tianji_buff_names(self, game: GameState) -> None:
        "Expand old saves' repeated effect labels without changing any rule."
        return tianji_state._refresh_tianji_buff_names(
            self._tianji_dependencies.state, game
        )

    def _ensure_tianji_state(self, game: GameState) -> bool:
        return tianji_state._ensure_tianji_state(self._tianji_dependencies.state, game)

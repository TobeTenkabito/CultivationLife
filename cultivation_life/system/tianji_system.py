from __future__ import annotations

import copy
import math
import random
import uuid
from typing import Any

# Moved methods still use this module's globals; retain the imports below.

from ..content_registry import ITEM_CATALOG, REALMS, WORLD_SYSTEMS
from ..combat_rule_engine import describe_rule
from ..monster_bloodline_rules import BLOODLINE_RULE_EFFECTS, describe_generated_trait, generated_trait_id
from ..models import GameState, HistoryRecord
from ..rules import remove_item
from ..runtime import now_iso
from ..tianji_theme_rules import (
    compile_theme_rules, generate_gameplay_blueprint, gameplay_debug_row,
    sample_total_effect_count, validate_theme_consistency,
)
from .crafting_system import (
    effective_tianji_combat_power, store_crafted_artifact,
    tianji_world_combat_power_cap,
)


TIANJI_GENERATION_VERSION = 8
SLOT_WEIGHTS = (0.40, 0.20, 0.20, 0.20)
TIANJI_WINDOW_SCHEDULES = (
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "last", "penultimate",
    "first_two", "first_three", "first_four", "last_two", "last_three",
    "after_second", "after_third", "first_and_last", "second_and_fourth",
    "odd", "even", "random", "random_two",
)
TIANJI_ATTRIBUTE_NAMES: dict[str, str] = {
    "might": "威能", "guard": "防护", "mobility": "身法",
    "sense": "神识", "sustain": "续航", "breach": "破法",
    "max_hp": "气血上限", "max_mp": "法力上限",
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
    {"id": "enemy_guard", "name": "蚀甲", "enemy_stat": "guard", "low": .80, "high": .94},
    {"id": "enemy_mobility", "name": "锁空", "enemy_stat": "mobility", "low": .82, "high": .95},
    {"id": "enemy_sense", "name": "蒙识", "enemy_stat": "sense", "low": .82, "high": .95},
    {"id": "tribulation", "name": "渡厄", "persistent": "tribulation_reduction", "low": .05, "high": .25},
    {"id": "vitality", "name": "护生", "persistent": "max_hp", "low": .03, "high": .18},
    {"id": "mana", "name": "法海", "persistent": "max_mp", "low": .04, "high": .22},
    {"id": "debuff_ward", "name": "万法不侵", "trait": "player_debuff_immunity", "low": .25, "high": 1.0},
    {"id": "escape_lock", "name": "禁绝虚空", "trait": "enemy_escape_lock", "low": .25, "high": 1.0},
)


def tianji_config() -> dict[str, Any]:
    value = WORLD_SYSTEMS.get("tianji_artifacts", {})
    return value if isinstance(value, dict) else {}


def tianji_content_available() -> bool:
    config = tianji_config()
    return bool(config.get("enabled") and int(config.get("artifact_count", 0)) == 100)


def _stable_rng(seed: int, stream: str) -> random.Random:
    return random.Random(f"{seed}:tianji-artifacts:v{TIANJI_GENERATION_VERSION}:{stream}")


def _scaled_multiplier(value: float, ratio: float) -> float:
    return round(1.0 + (float(value) - 1.0) * ratio, 6)


def _scaled_effects(effects: list[dict[str, Any]], ratio: float) -> tuple[list[dict[str, Any]], dict[str, float]]:
    combat: list[dict[str, Any]] = []
    persistent: dict[str, float] = {}
    for raw in effects:
        effect = copy.deepcopy(raw)
        result: dict[str, Any] = {
            "source": effect["name"], "name": effect["name"],
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
        if any(key in result for key in (
            "player_stat_multipliers", "enemy_stat_multipliers", "traits", "tianji_resistance",
        )):
            combat.append(result)
    return combat, persistent


def _tianji_effect_description(effect: dict[str, Any]) -> str:
    if isinstance(effect.get("rule"), dict):
        rule = effect["rule"]
        return describe_rule(rule) if int(rule.get("schema_version", 1)) >= 2 else describe_generated_trait(rule)
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


from ._assembly import include_system_methods as _include_system_methods
from .tianji.generation import TianjiGenerationMethods
from .tianji.state import TianjiStateMethods
from .tianji.intelligence import TianjiIntelligenceMethods
from .tianji.forging import TianjiForgingMethods
from .tianji.presentation import TianjiPresentationMethods
from .tianji.npcs import TianjiNpcMethods


@_include_system_methods(
    TianjiGenerationMethods,
    TianjiStateMethods,
    TianjiIntelligenceMethods,
    TianjiForgingMethods,
    TianjiPresentationMethods,
    TianjiNpcMethods,
    namespace=globals(),
)
class TianjiSystemMixin:
    pass

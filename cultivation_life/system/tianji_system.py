from __future__ import annotations

import copy
import math
import random
import uuid
from typing import Any

from ..content_registry import REALMS, WORLD_SYSTEMS
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


class TianjiSystemMixin:
    @staticmethod
    def _tianji_config() -> dict[str, Any]:
        return tianji_config()

    def _generate_tianji_materials(self, game: GameState) -> list[dict[str, Any]]:
        config = self._tianji_config()
        rng = _stable_rng(game.seed, "materials")
        prefixes = list(config["material_prefixes"])
        roots = list(config["material_roots"])
        themes = list(config["themes"])
        worlds = [world for world in config["base_worlds"] if world in WORLD_SYSTEMS.get("world_profiles", {})]
        result: list[dict[str, Any]] = []
        used_names: set[str] = set()
        for index in range(int(config["material_count"])):
            theme = themes[index % len(themes)] if index < len(themes) else rng.choice(themes)
            root = roots[(index // len(themes)) % len(roots)] if index < len(themes) * 2 else rng.choice(roots)
            prefix = prefixes[index % len(prefixes)] if index < len(prefixes) else rng.choice(prefixes)
            world = rng.choice(worlds)
            tier = int(WORLD_SYSTEMS["world_profiles"].get(world, {}).get("tier", 1))
            roles = rng.sample(["primary", "secondary", "quench"], rng.choice((1, 2, 3)))
            potency = rng.uniform(.05, .11) * (1 + tier * .22)
            material_id = f"tianji-mat-{index + 1:03d}"
            name = f"{prefix}{theme['elements'][index % len(theme['elements'])]}{root}"
            if name in used_names:
                name = f"{name}·{index + 1}"
            used_names.add(name)
            tags = {
                str(theme["id"]): round(rng.uniform(.82, 1.0), 3),
                str(root): 1.0,
                str(prefix): round(rng.uniform(.48, .82), 3),
            }
            role_effects: dict[str, Any] = {}
            if "primary" in roles:
                role_effects["primary"] = {
                    "design_multipliers": {"combat_power": round(1 + potency, 4)},
                    "description": f"主材：{theme['name']}道韵令战力设计值提高 {potency:.0%}。",
                }
            if "secondary" in roles:
                role_effects["secondary"] = {
                    "design_multipliers": {"max_hp": round(1 + potency / 2, 4), "max_mp": round(1 + potency / 2, 4)},
                    "description": f"辅材：气血与法力设计值各提高 {potency / 2:.0%}。",
                }
            if "quench" in roles:
                role_effects["quench"] = {
                    "combat_effect": {"player_stat_multipliers": {"breach": round(1 + potency / 2, 4)}},
                    "description": f"淬火：破法提高 {potency / 2:.0%}。",
                }
            result.append({
                "id": material_id, "name": name,
                "world": world, "tier": tier, "roles": roles,
                "tags": ["tianji_material", str(theme["id"]), str(root), f"world:{world}"],
                "tianji_tags": tags, "allow_duplicate_type": True,
                "base_material_value": round((80_000 ** tier) * rng.uniform(.8, 2.2)),
                "role_effects": role_effects,
                "description": f"诞生于{WORLD_SYSTEMS['world_names'].get(world, world)}的存档级神机材料，兼可用于普通五槽炼器。",
            })
        return result

    def _next_tianji_name(
        self, rng: random.Random, theme: dict[str, Any], mold_id: str,
        used_names: set[str], used_stems: set[str], used_prefixes: set[str], index: int,
    ) -> tuple[str, str]:
        config = self._tianji_config()
        noun = str(config["mold_nouns"][mold_id])
        patterns = list(config.get("name_patterns", ["{word}{style}{noun}"]))
        linkers = list(config.get("name_linkers", ["御"]))
        suffixes = list(config.get("name_suffixes", ["玄"]))
        word = str(theme["words"][0])
        style = str(config["styles"][0])
        element = str(theme["elements"][0])
        for _ in range(600):
            word = str(rng.choice(theme["words"]))
            style = str(rng.choice(config["styles"]))
            element = str(rng.choice(theme["elements"]))
            name = str(rng.choice(patterns)).format(
                word=word, style=style, element=element, noun=noun,
                linker=rng.choice(linkers), suffix=rng.choice(suffixes),
            )
            stem = name[:-len(noun)] if noun and name.endswith(noun) else name
            prefix = name[:4]
            if name not in used_names and stem not in used_stems and prefix not in used_prefixes:
                used_names.add(name)
                used_stems.add(stem)
                used_prefixes.add(prefix)
                return name, style
        # The expanded pools make this practically unreachable.  Keep a
        # deterministic final form so even hostile modded pools cannot collide.
        stem = f"{word}{element}{style}{index + 1}号"
        name = f"{stem}{noun}"
        used_names.add(name)
        used_stems.add(stem)
        used_prefixes.add(name[:4])
        return name, style

    def _next_tianji_buff_name(
        self, rng: random.Random, theme: dict[str, Any], core: str,
        used_names: set[str], index: int,
    ) -> str:
        config = self._tianji_config()
        prefixes = list(config.get("buff_name_prefixes", ["太初", "混元", "无极"]))
        suffixes = list(config.get("buff_name_suffixes", ["神律", "道印", "真解"]))
        patterns = list(config.get("buff_name_patterns", ["{prefix}{core}", "{core}·{suffix}"]))
        words = list(theme.get("words", [theme.get("name", "天工")]))
        elements = list(theme.get("elements", [theme.get("name", "神机")]))
        for _ in range(160):
            name = str(rng.choice(patterns)).format(
                prefix=rng.choice(prefixes), suffix=rng.choice(suffixes), core=core,
                word=rng.choice(words), element=rng.choice(elements), theme=theme.get("name", "天工"),
            )
            if name not in used_names:
                used_names.add(name)
                return name
        fallback = f"{rng.choice(prefixes)}{core}·{rng.choice(suffixes)}{index + 1}"
        used_names.add(fallback)
        return fallback

    def _tianji_rule_effects(
        self, seed: int, artifact_id: str, theme: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        primitive_rng = _stable_rng(seed, f"gameplay-primitive:{artifact_id}")
        preferred = [row for row in PRIMITIVES if row.get("stat") in theme.get("stats", {})]
        pool = list(PRIMITIVES)
        count = sample_total_effect_count(_stable_rng(seed, f"gameplay-rule-count:{artifact_id}"))
        blueprint = generate_gameplay_blueprint(
            blueprint_rng=_stable_rng(seed, f"gameplay-blueprint:{artifact_id}"),
            axis_count_rng=_stable_rng(seed, f"gameplay-axis-count:{artifact_id}"),
            archetype_rng=_stable_rng(seed, f"gameplay-archetype:{artifact_id}"),
            cadence_rng=_stable_rng(seed, f"gameplay-cadence:{artifact_id}"),
            flavor_theme_id=str(theme.get("id", "")),
        )
        primitive = primitive_rng.choice([*pool, *preferred, *preferred])
        magnitude = primitive_rng.uniform(float(primitive["low"]), float(primitive["high"]))
        if primitive.get("stat"):
            payload = {"player_stat_multipliers": {primitive["stat"]: round(magnitude, 5)}}
        elif primitive.get("enemy_stat"):
            payload = {"enemy_stat_multipliers": {primitive["enemy_stat"]: round(max(.65, magnitude), 5)}}
        elif primitive.get("trait"):
            payload = {"trait": primitive["trait"]}
        else:
            payload = {"persistent": primitive["persistent"]}
        used_buff_names: set[str] = set()
        name_rng = _stable_rng(seed, f"gameplay-buff-names:{artifact_id}")
        first_name = self._next_tianji_buff_name(name_rng, theme, str(primitive["name"]), used_buff_names, 0)
        first = {
            "primitive": primitive["id"], "name": first_name,
            "magnitude": round(magnitude, 5), "trigger": "combat_start",
            "conditions": [], "targets": "owner",
            "replica_scaling": "numeric" if not primitive.get("trait") else "resistance_chain",
            **payload,
        }
        first["description"] = _tianji_effect_description(first)
        effects: list[dict[str, Any]] = [first]
        rules = compile_theme_rules(
            blueprint, rule_count=max(0, count - 1),
            rng=_stable_rng(seed, f"gameplay-rules:{artifact_id}"), source_id=artifact_id,
        )
        consistency_errors = validate_theme_consistency(blueprint, rules)
        if consistency_errors:
            raise ValueError(f"神机玩法蓝图编译失败：{'；'.join(consistency_errors)}")
        for effect_index, rule in enumerate(rules, 1):
            display_name = self._next_tianji_buff_name(
                name_rng, theme, str(rule["name"]), used_buff_names, effect_index,
            )
            rule["display_name"] = display_name
            effect = {
                "primitive": f"rule:{rule['theme_axis']}:{rule['theme_slot']}", "name": display_name,
                "description": describe_rule(rule), "trigger": str(rule["trigger"]),
                "conditions": list(map(str, rule["conditions"])), "targets": "owner",
                "replica_scaling": "rule_scale", "rule": rule,
            }
            effects.append(effect)
        return effects, blueprint

    def _generate_tianji_artifacts(self, game: GameState, materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
        config = self._tianji_config()
        flavor_rng = _stable_rng(game.seed, "flavor")
        power_rng = _stable_rng(game.seed, "powers")
        name_rng = _stable_rng(game.seed, "names")
        recipe_rng = _stable_rng(game.seed, "recipes")
        world_rng = _stable_rng(game.seed, "worlds")
        themes = {str(row["id"]): row for row in config["themes"]}
        molds = list(config["mold_nouns"])
        artifacts: list[dict[str, Any]] = []
        preset_rows = list(config.get("preset_artifacts", []))
        random_count = int(config["artifact_count"]) - len(preset_rows)
        used_names = {str(row["name"]) for row in preset_rows}
        used_stems: set[str] = set()
        used_prefixes = {str(row["name"])[:4] for row in preset_rows}

        def recipe_for(theme_id: str) -> list[str]:
            chosen: list[dict[str, Any]] = []
            for role in ("primary", "secondary", "secondary", "quench"):
                candidates = [
                    row for row in materials
                    if role in row.get("roles", []) and row not in chosen
                ]
                aligned = [row for row in candidates if theme_id in row.get("tianji_tags", {})]
                selected = recipe_rng.choice(aligned if aligned else candidates)
                chosen.append(selected)
            return [str(row["id"]) for row in chosen]

        for index in range(random_count):
            theme = flavor_rng.choice(list(themes.values()))
            mold_id = flavor_rng.choice(molds)
            # Log distribution covers Mahayana through top Daluo scales.  The
            # list is sorted only after every raw value has been generated.
            power = round(math.exp(power_rng.uniform(math.log(63_000_000), math.log(34_000_000_000))))
            noun = config["mold_nouns"][mold_id]
            name, style = self._next_tianji_name(
                name_rng, theme, mold_id, used_names, used_stems, used_prefixes, index,
            )
            artifact_id = f"tianji-{index + 1:03d}"
            effects, gameplay_blueprint = self._tianji_rule_effects(game.seed, artifact_id, theme)
            artifacts.append({
                "id": artifact_id, "name": name, "is_preset": False,
                "generation_version": TIANJI_GENERATION_VERSION,
                "base_combat_power": power, "mold_id": mold_id,
                "theme_id": theme["id"], "theme_name": theme["name"],
                "recipe": recipe_for(str(theme["id"])),
                "gameplay_blueprint": gameplay_blueprint, "effects": effects,
                "description": f"以{theme['name']}为核、{style}为势的{noun}形神机，器理与本存档天地法则相扣。",
            })
        for preset in preset_rows:
            theme = themes[str(preset["theme_id"])]
            power = round(float(preset["power"]) * power_rng.uniform(.97, 1.03))
            effects, gameplay_blueprint = self._tianji_rule_effects(game.seed, str(preset["id"]), theme)
            artifacts.append({
                "id": str(preset["id"]), "name": str(preset["name"]), "is_preset": True,
                "generation_version": TIANJI_GENERATION_VERSION,
                "base_combat_power": power, "mold_id": str(preset["mold_id"]),
                "theme_id": theme["id"], "theme_name": theme["name"],
                "recipe": recipe_for(str(theme["id"])),
                "gameplay_blueprint": gameplay_blueprint, "effects": effects,
                "description": str(preset["description"]),
            })
        artifacts.sort(key=lambda row: (-int(row["base_combat_power"]), str(row["id"])))
        worlds = [world for world in config["base_worlds"] if world in WORLD_SYSTEMS.get("world_profiles", {})]
        for rank, artifact in enumerate(artifacts, 1):
            artifact["rank"] = rank
            # A small universal weight preserves the intended possibility of a
            # high treasure falling into a low world.
            desired_tier = 3 if rank <= 20 else 2 if rank <= 80 else 1
            weights = []
            for world in worlds:
                tier = int(WORLD_SYSTEMS["world_profiles"].get(world, {}).get("tier", 1))
                weights.append(.08 + math.exp(-abs(tier - desired_tier) * 1.25))
            artifact["origin_world"] = world_rng.choices(worlds, weights=weights, k=1)[0]
        return artifacts

    def _refresh_tianji_artifact_names(self, game: GameState) -> None:
        """Migrate only generated names while preserving every frozen rule and recipe."""
        state = game.tianji_state
        config = self._tianji_config()
        themes = {str(row["id"]): row for row in config["themes"]}
        preset_ids = {str(row["id"]) for row in config.get("preset_artifacts", [])}
        used_names = {
            str(row["name"]) for row in state.get("artifacts", [])
            if str(row.get("id")) in preset_ids
        }
        used_stems: set[str] = set()
        used_prefixes = {name[:4] for name in used_names}
        rng = _stable_rng(game.seed, "names")
        renamed: dict[str, str] = {}
        generated = sorted(
            (row for row in state.get("artifacts", []) if str(row.get("id")) not in preset_ids),
            key=lambda row: str(row.get("id", "")),
        )
        for index, artifact in enumerate(generated):
            theme = themes[str(artifact["theme_id"])]
            name, style = self._next_tianji_name(
                rng, theme, str(artifact["mold_id"]), used_names, used_stems, used_prefixes, index,
            )
            renamed[str(artifact["id"])] = name
            artifact["name"] = name
            noun = config["mold_nouns"][str(artifact["mold_id"])]
            artifact["description"] = f"以{theme['name']}为核、{style}为势的{noun}形神机，器理与本存档天地法则相扣。"
        for entry in state.get("discovery_log", []):
            artifact_id = str(entry.get("artifact_id", ""))
            if artifact_id in renamed:
                entry["name"] = renamed[artifact_id]

    def _refresh_tianji_buff_names(self, game: GameState) -> None:
        """Expand old saves' repeated effect labels without changing any rule."""
        themes = {str(row["id"]): row for row in self._tianji_config()["themes"]}
        primitives = {str(row["id"]): row for row in PRIMITIVES}
        for artifact in game.tianji_state.get("artifacts", []):
            theme = themes.get(str(artifact.get("theme_id")))
            if not theme:
                continue
            rng = _stable_rng(game.seed, f"buff-names-v7:{artifact.get('id')}")
            used_names: set[str] = set()
            for effect_index, effect in enumerate(artifact.get("effects", [])):
                rule = effect.get("rule")
                if isinstance(rule, dict):
                    definition = BLOODLINE_RULE_EFFECTS.get(str(rule.get("effect", "")), {})
                    core = str(definition.get("name", effect.get("name", "神机")))
                else:
                    primitive = primitives.get(str(effect.get("primitive", "")), {})
                    core = str(primitive.get("name", effect.get("name", "神机")))
                name = self._next_tianji_buff_name(rng, theme, core, used_names, effect_index)
                effect["name"] = name
                if isinstance(rule, dict):
                    rule["display_name"] = name

    def _tianji_persistent_npcs(self, game: GameState, world: str) -> list[Any]:
        values: list[Any] = [
            npc for npc in game.world_npcs.values() if npc.alive and npc.world == world
        ]
        values.extend(npc for npc in game.notable_npcs.values() if npc.alive and npc.world == world)
        for sect in game.sects.values():
            values.extend(npc for npc in sect.npcs if npc.alive and npc.world == world)
        unique: dict[str, Any] = {str(npc.id): npc for npc in values if getattr(npc, "id", None)}
        return list(unique.values())

    def _assign_tianji_holders_for_world(self, game: GameState, world: str) -> bool:
        state = game.tianji_state
        if not state.get("artifacts") or world in state.setdefault("holder_worlds_initialized", []):
            return False
        candidates = self._tianji_persistent_npcs(game, world)
        state["holder_worlds_initialized"].append(world)
        if not candidates:
            return True
        rng = _stable_rng(game.seed, f"holders:{world}")
        available = [
            row for row in state["artifacts"]
            if row["origin_world"] == world and row["id"] not in state["holders"]
            and state["true_body_states"][row["id"]]["status"] == "unmanifested"
        ]
        rng.shuffle(available)
        rng.shuffle(candidates)
        count = min(len(candidates), len(available), max(1, min(4, len(candidates) // 4 + 1)))
        for index, (npc, artifact) in enumerate(zip(candidates[:count], available[:count])):
            true_body = index == 0 and int(artifact["rank"]) <= 30 and rng.random() < .42
            ratio = 1.0 if true_body else round(rng.uniform(.28, .86), 4)
            state["holders"][artifact["id"]] = {
                "npc_id": str(npc.id), "world": world,
                "kind": "true_body" if true_body else "replica", "replica_ratio": ratio,
            }
            if true_body:
                state["true_body_states"][artifact["id"]] = {
                    "status": "npc", "holder_ref": str(npc.id),
                }
        return True

    def _ensure_tianji_state(self, game: GameState) -> bool:
        if not tianji_content_available():
            return False
        state = game.tianji_state
        changed = False
        if not state.get("artifacts"):
            materials = self._generate_tianji_materials(game)
            artifacts = self._generate_tianji_artifacts(game, materials)
            state.clear()
            state.update({
                "generation_version": TIANJI_GENERATION_VERSION,
                "generator_mode": "theme-first-v8",
                "materials": materials, "artifacts": artifacts,
                "knowledge": {row["id"]: 0 for row in artifacts},
                "true_body_states": {
                    row["id"]: {"status": "unmanifested", "holder_ref": None}
                    for row in artifacts
                },
                "holders": {}, "player_artifacts": [], "activated_artifact_id": None,
                "discovered_material_ids": [], "discovery_log": [],
                "holder_worlds_initialized": [],
            })
            changed = True
        # Never regenerate an older version. Missing additive keys are safe to
        # backfill without touching frozen artifact or recipe definitions.
        defaults = {
            "holders": {}, "player_artifacts": [], "activated_artifact_id": None,
            "discovered_material_ids": [], "discovery_log": [],
            "holder_worlds_initialized": [],
        }
        for key, default in defaults.items():
            if key not in state:
                state[key] = copy.deepcopy(default)
                changed = True
        old_generation = int(state.get("generation_version", 1))
        has_theme_blueprints = bool(state.get("artifacts")) and all(
            isinstance(row.get("gameplay_blueprint"), dict) for row in state.get("artifacts", [])
        )
        if has_theme_blueprints and old_generation < TIANJI_GENERATION_VERSION:
            # Repair metadata that was manually downgraded or partially saved;
            # definitions themselves remain untouched.
            state["generation_version"] = TIANJI_GENERATION_VERSION
            state["generator_mode"] = "theme-first-v8"
            old_generation = TIANJI_GENERATION_VERSION
            changed = True
        is_theme_generation = has_theme_blueprints or str(state.get("generator_mode", "")).startswith("theme-first")
        display_migration = 7 if is_theme_generation else int(state.get("display_migration_version", old_generation))
        # Artifact definitions are world facts.  Old saves keep their compiled
        # rules exactly as written; only explicitly display-only migrations are
        # allowed below.  Theme blueprints are generated for new worlds only.
        if old_generation < TIANJI_GENERATION_VERSION:
            if state.get("generator_mode") != f"legacy-v{old_generation}":
                state["generator_mode"] = f"legacy-v{old_generation}"
                changed = True
        if display_migration < 4:
            self._refresh_tianji_artifact_names(game)
            changed = True
        if display_migration < 5:
            for artifact_index, artifact in enumerate(state.get("artifacts", [])):
                for effect_index, effect in enumerate(artifact.get("effects", [])[1:], 1):
                    rule = effect.get("rule")
                    if not isinstance(rule, dict):
                        continue
                    schedule_rng = _stable_rng(
                        game.seed, f"schedule-v5:{artifact.get('id')}:{effect_index}",
                    )
                    offset = schedule_rng.randrange(len(TIANJI_WINDOW_SCHEDULES))
                    rule["schedule"] = TIANJI_WINDOW_SCHEDULES[
                        (artifact_index + effect_index + offset) % len(TIANJI_WINDOW_SCHEDULES)
                    ]
                    rule.pop("power", None)
                    rule["id"] = generated_trait_id(rule)
                    rule["description"] = describe_generated_trait(rule)
                    effect["description"] = rule["description"]
                    effect["conditions"] = list(map(str, rule.get("conditions", [])))
            changed = True
        if display_migration < 7:
            self._refresh_tianji_buff_names(game)
            changed = True
        if display_migration < 7:
            state["display_migration_version"] = 7
            changed = True
        for artifact_id, holder in list(state["holders"].items()):
            npc = self._find_npc(game, str(holder.get("npc_id", "")))
            if npc and npc.alive:
                continue
            del state["holders"][artifact_id]
            if holder.get("kind") == "true_body":
                state["true_body_states"][artifact_id] = {
                    "status": "destroyed", "holder_ref": None,
                }
            changed = True
        if self._assign_tianji_holders_for_world(game, game.player.world):
            changed = True
        active_id = state.get("activated_artifact_id")
        owned = {str(row.get("id")) for row in game.player.crafted_artifacts if row.get("tianji")}
        if active_id not in owned:
            active_id = None
            if state.get("activated_artifact_id") is not None:
                state["activated_artifact_id"] = None
                changed = True
        equipped_without_tianji = [
            item_id for item_id in game.player.equipped_crafted_artifact_ids
            if item_id not in owned
        ]
        expected_equipped = equipped_without_tianji + ([str(active_id)] if active_id else [])
        if expected_equipped != game.player.equipped_crafted_artifact_ids:
            game.player.equipped_crafted_artifact_ids = expected_equipped
            changed = True
        return changed

    @staticmethod
    def _tianji_artifact(state: dict[str, Any], artifact_id: str) -> dict[str, Any]:
        artifact = next((row for row in state.get("artifacts", []) if row.get("id") == artifact_id), None)
        if not artifact:
            raise ValueError("天工神机榜中没有这件法宝")
        return artifact

    def _tianji_reveal(self, game: GameState, artifact_id: str, level: int, source: str) -> bool:
        state = game.tianji_state
        old = int(state["knowledge"].get(artifact_id, 0))
        new = max(old, min(5, int(level)))
        if new == old:
            return False
        state["knowledge"][artifact_id] = new
        artifact = self._tianji_artifact(state, artifact_id)
        state["discovery_log"].append({
            "artifact_id": artifact_id, "name": artifact["name"], "from": old,
            "to": new, "source": source, "age": game.player.age,
        })
        state["discovery_log"] = state["discovery_log"][-200:]
        return True

    def _tianji_npc_conversation_clue(
        self, game: GameState, npc_id: str, rng: random.Random,
    ) -> str:
        """Occasionally turn an actual NPC conversation into persistent intel."""
        if not tianji_content_available():
            return ""
        self._ensure_tianji_state(game)
        state = game.tianji_state
        held = next((
            (artifact_id, holder) for artifact_id, holder in state.get("holders", {}).items()
            if str(holder.get("npc_id", "")) == str(npc_id)
        ), None)
        artifact: dict[str, Any] | None = None
        chance = .12
        if held:
            artifact = self._tianji_artifact(state, held[0])
            chance = .72
        else:
            candidates = [
                row for row in state.get("artifacts", [])
                if int(state["knowledge"].get(row["id"], 0)) < 3
                and row.get("origin_world") == game.player.world
            ]
            if candidates:
                artifact = rng.choice(candidates)
        if not artifact or rng.random() >= chance:
            return ""
        old = int(state["knowledge"].get(artifact["id"], 0))
        target = min(3, old + 1)
        if target <= old or not self._tianji_reveal(
            game, str(artifact["id"]), target, f"与{npc_id}交谈所得口述线索",
        ):
            return ""
        return f" 对方谈及一则不肯写入玉简的秘闻，你对【{artifact['name']}】的情报提升至 Lv{target}。"

    def _maybe_tianji_intelligence_event(
        self, game: GameState, rng: random.Random,
    ) -> str | None:
        """Resolve a rare, non-clickable clue event after a real time action."""
        if not tianji_content_available():
            return None
        self._ensure_tianji_state(game)
        settings = self._tianji_config().get("intelligence_events", {})
        if rng.random() >= float(settings.get("chance_per_action_unit", .018)):
            return None
        state = game.tianji_state
        realm = game.player.realm_index
        max_level = 5 if realm >= int(settings.get("minimum_realm_for_level_5", 8)) else 4
        if realm < int(settings.get("minimum_realm_for_level_4", 6)):
            max_level = 3
        partial = [
            row for row in state.get("artifacts", [])
            if 0 < int(state["knowledge"].get(row["id"], 0)) < max_level
        ]
        unknown = [
            row for row in state.get("artifacts", [])
            if int(state["knowledge"].get(row["id"], 0)) == 0
        ]
        use_partial = bool(partial) and (
            not unknown or rng.random() < float(settings.get("partial_chain_chance", .68))
        )
        candidates = partial if use_partial else unknown
        if not candidates:
            return None
        weights = []
        for artifact in candidates:
            local = 5.0 if artifact.get("origin_world") == game.player.world else 1.0
            rank = int(artifact.get("rank", 100))
            secrecy = .28 if rank <= 10 else .55 if rank <= 30 else 1.0
            current = int(state["knowledge"].get(artifact["id"], 0))
            depth = (1.0, 1.0, .48, .16, .035)[min(4, current)]
            weights.append(local * secrecy * depth)
        artifact = rng.choices(candidates, weights=weights, k=1)[0]
        old = int(state["knowledge"].get(artifact["id"], 0))
        new = min(max_level, old + 1)
        fallback_sources = {
            1: ("残卷露名", "你在一卷残破游记的夹层里发现了器名与模糊形制。"),
            2: ("斗痕辨器", "一处古战场残留的器痕，与坊间密谈相互印证。"),
            3: ("器纹拓影", "流散黑市的器纹拓片补全了关键材料方向。"),
            4: ("真方残页", "一页被多重禁制封存的古方，显出了完整材料次序。"),
            5: ("天机落点", "跨界行商与古阵星图的数处记录，终于指向同一条踪迹。"),
        }
        event_pool = settings.get("event_pool", {}).get(str(new), [])
        source = rng.choice(event_pool) if event_pool else None
        title, body = (
            (str(source["title"]), str(source["body"]))
            if isinstance(source, dict) and source.get("title") and source.get("body")
            else fallback_sources[new]
        )
        if not self._tianji_reveal(game, str(artifact["id"]), new, f"随机事件：{title}"):
            return None
        summary = f"{body}【{artifact['name']}】情报提升至 Lv{new}。"
        game.history.append(HistoryRecord(
            "SYS_TIANJI_INTELLIGENCE", 1, game.player.age, title,
            str(artifact["id"]), f"knowledge_lv{new}", summary,
            {"artifact_id": artifact["id"], "from": old, "to": new},
            ["system", "tianji", "intelligence", "random_event"],
        ))
        return f"{game.player.age}岁：{summary}"

    @staticmethod
    def _tianji_public_effect(effect: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": str(effect["name"]), "description": _tianji_effect_description(effect),
            "trigger": str(effect.get("trigger", "combat_start")),
            "replica_scaling": str(effect.get("replica_scaling", "numeric")),
        }

    def _public_tianji(self, game: GameState) -> dict[str, Any]:
        if not tianji_content_available():
            return {"available": False}
        self._ensure_tianji_state(game)
        state = game.tianji_state
        material_names = {row["id"]: row["name"] for row in state["materials"]}
        world_combat_cap = tianji_world_combat_power_cap(game.player.world)
        rows = []
        for artifact in state["artifacts"]:
            level = int(state["knowledge"].get(artifact["id"], 0))
            public: dict[str, Any] = {
                "id": artifact["id"], "rank": artifact["rank"], "knowledge_level": level,
                "name": artifact["name"] if level >= 1 else "???",
                "mold_id": artifact["mold_id"] if level >= 1 else None,
                "mold_name": self._tianji_config()["mold_nouns"].get(artifact["mold_id"], "未知") if level >= 1 else "???",
                "base_combat_power": artifact["base_combat_power"] if level >= 2 else None,
                "current_world_combat_power": (
                    round(effective_tianji_combat_power(artifact["base_combat_power"], game.player.world))
                    if level >= 2 else None
                ),
                "effects": [self._tianji_public_effect(row) for row in artifact["effects"]] if level >= 2 else None,
                "description": artifact["description"] if level >= 2 else "???",
                "gameplay_tendency": (
                    str(artifact.get("gameplay_blueprint", {}).get("tendency", "")) or None
                ) if level >= 2 else None,
                "effect_groups": ({
                    "foundation": [self._tianji_public_effect(artifact["effects"][0])] if artifact.get("effects") else [],
                    "core": [self._tianji_public_effect(row) for row in artifact.get("effects", [])[1:4]],
                    "derived": [self._tianji_public_effect(row) for row in artifact.get("effects", [])[4:]],
                } if level >= 2 else None),
                "recipe_clues": (
                    [state["materials"][next(i for i, row in enumerate(state["materials"]) if row["id"] == mid)]["tags"][1:3] for mid in artifact["recipe"]]
                    if level == 3 else None
                ),
                "recipe": [material_names[mid] for mid in artifact["recipe"]] if level >= 4 else None,
                "recipe_ids": list(artifact["recipe"]) if level >= 4 else None,
                "origin_world_name": WORLD_SYSTEMS["world_names"].get(artifact["origin_world"], artifact["origin_world"]) if level >= 2 else "???",
                "true_body_status": copy.deepcopy(state["true_body_states"].get(artifact["id"])) if level >= 4 else None,
                "holder": None,
            }
            if level >= 5:
                holder = state["holders"].get(artifact["id"])
                if holder:
                    npc = self._find_npc(game, str(holder["npc_id"]))
                    public["holder"] = {
                        "name": npc.name if npc else "行踪不明", "world_name": WORLD_SYSTEMS["world_names"].get(holder["world"], holder["world"]),
                        "kind": holder["kind"], "replica_ratio": holder["replica_ratio"],
                    }
                else:
                    public["holder"] = {"name": "暂无可追踪持有人"}
            rows.append(public)
        discovered = set(state.get("discovered_material_ids", []))
        owned_definitions = {
            str(row.get("tianji", {}).get("definition_id"))
            for row in game.player.crafted_artifacts if row.get("tianji")
        }
        active_instance = str(state.get("activated_artifact_id") or "")
        active_definition = next((
            str(row.get("tianji", {}).get("definition_id"))
            for row in game.player.crafted_artifacts if str(row.get("id")) == active_instance
        ), None)
        return {
            "available": True, "name": "神机百变：巧夺天工", "generation_version": state["generation_version"],
            "world_name":WORLD_SYSTEMS["world_names"].get(game.player.world, game.player.world),
            "world_combat_power_cap":round(world_combat_cap) if world_combat_cap is not None else None,
            "artifacts": rows, "known_count": sum(int(row["knowledge_level"]) > 0 for row in rows),
            "targets": [{"id": row["id"], "rank": row["rank"], "name": row["name"], "knowledge_level": row["knowledge_level"]} for row in rows if row["knowledge_level"] >= 3],
            "activated_artifact_id": state.get("activated_artifact_id"),
            "owned_artifact_ids": list(state.get("player_artifacts", [])),
            "owned_definition_ids": sorted(owned_definitions),
            "active_definition_id": active_definition,
            "materials": [copy.deepcopy(row) for row in state["materials"] if row["id"] in discovered],
            "discovery_log": copy.deepcopy(state.get("discovery_log", [])[-20:]),
        }

    def _tianji_material_instance(self, game: GameState, definition: dict[str, Any], rng: random.Random, source: str) -> dict[str, Any]:
        quality = round(rng.uniform(.72, 1.25), 4)
        embedded = copy.deepcopy(definition)
        return {
            "id": f"tianji-material-{uuid.uuid4().hex}", "material_id": definition["id"],
            "name": definition["name"], "quality": quality,
            "state": "道韵圆满" if quality >= 1.15 else "灵机充盈" if quality >= .95 else "灵性稍损",
            "source": source, "origin_world": game.player.world,
            "material_value": max(1, round(int(definition["base_material_value"]) * quality)),
            "acquired_tier": int(definition["tier"]), "dynamic_definition": embedded,
            "tianji_tags": copy.deepcopy(definition["tianji_tags"]),
        }

    def _append_tianji_market_offers(self, game: GameState, offers: list[dict[str, Any]], *, tier: int, market_name: str, location_id: str) -> None:
        if not tianji_content_available():
            return
        self._ensure_tianji_state(game)
        rng = _stable_rng(game.seed, f"material-market:{game.player.world}:{location_id}:{game.player.age}")
        definitions = [
            row for row in game.tianji_state["materials"]
            if row["world"] == game.player.world and int(row["tier"]) <= max(tier, game.player.realm_index) + 1
        ]
        if not definitions:
            return
        for index, definition in enumerate(rng.sample(definitions, min(2, len(definitions)))):
            instance = self._tianji_material_instance(game, definition, rng, f"{market_name}购得")
            offers.append({
                "id": f"{game.player.world}-{location_id}-{game.player.age}-tianji-{index}-{definition['id']}",
                "kind": "crafting_material", "content_id": definition["id"], "name": definition["name"],
                "description": f"神机材料 · {instance['state']} · 可参与普通炼器和神机目标炼制。",
                "price": max(1, round(instance["material_value"] * rng.uniform(.9, 1.15))),
                "tier": tier, "tier_name": REALMS[max(0, min(len(REALMS) - 1, tier))].name,
                "market_name": market_name, "world": game.player.world, "location_id": location_id,
                "rare_next_tier": False, "sold": False, "material_instance": instance,
                "tianji_material_id": definition["id"],
            })

    def _tianji_material_bought(self, game: GameState, instance: dict[str, Any]) -> None:
        material_id = str(instance.get("material_id", ""))
        known = game.tianji_state.setdefault("discovered_material_ids", [])
        if material_id.startswith("tianji-mat-") and material_id not in known:
            known.append(material_id)

    @staticmethod
    def _tianji_tag_similarity(required: dict[str, float], supplied: dict[str, float]) -> float:
        if not required or not supplied:
            return 0.0
        shared = set(required).intersection(supplied)
        if not shared:
            return 0.0
        numerator = sum(min(float(required[key]), float(supplied[key])) for key in shared)
        denominator = max(1e-9, sum(float(value) for value in required.values()))
        return min(1.0, numerator / denominator)

    @staticmethod
    def _tianji_closeness_factor(closeness: float) -> float:
        points = ((0.0, .15), (.2, .30), (.4, .55), (.6, .80), (.8, 1.0), (1.0, 1.20))
        value = max(0.0, min(1.0, closeness))
        for (left_x, left_y), (right_x, right_y) in zip(points, points[1:]):
            if value <= right_x:
                progress = (value - left_x) / max(.0001, right_x - left_x)
                return left_y + (right_y - left_y) * progress
        return 1.20

    def _tianji_target_preview(self, game: GameState, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_tianji_state(game)
        artifact = self._tianji_artifact(game.tianji_state, str(payload.get("target_artifact_id", "")))
        knowledge = int(game.tianji_state["knowledge"].get(artifact["id"], 0))
        if knowledge < 3:
            raise ValueError("目标法宝情报至少达到 Lv3 才能进行目标炼制")
        mold, selected = self._resolve_crafting_selection(game.player, payload)
        if mold["id"] != artifact["mold_id"]:
            raise ValueError("胎模错误，无法形成该神机法宝的结构；材料尚未消耗")
        definitions = {row["id"]: row for row in game.tianji_state["materials"]}
        exact = []
        similarities = []
        for (_, supplied), required_id in zip(selected, artifact["recipe"]):
            supplied_id = str(supplied["definition_id"])
            required = definitions[required_id]
            supplied_tags = supplied.get("tianji_tags")
            if not isinstance(supplied_tags, dict):
                embedded = supplied.get("dynamic_definition", {})
                supplied_tags = embedded.get("tianji_tags", {}) if isinstance(embedded, dict) else {}
            is_exact = supplied_id == required_id
            exact.append(is_exact)
            similarities.append(1.0 if is_exact else self._tianji_tag_similarity(required["tianji_tags"], supplied_tags))
        closeness = sum(weight * value for weight, value in zip(SLOT_WEIGHTS, similarities))
        world_cap = float(self._tianji_config()["world_replica_caps"].get(game.player.world, .20))
        quality_factor = max(.82, min(1.0, sum(float(row[1].get("quality", 1.0)) for row in selected) / 4))
        replica_ratio = min(world_cap * 1.20, world_cap * self._tianji_closeness_factor(closeness) * quality_factor)
        forge_kind = str(payload.get("forge_kind", "replica"))
        if forge_kind == "true_body":
            if knowledge < 4:
                raise ValueError("掌握 Lv4 完整真方后才能炼制本体")
            if not all(exact):
                raise ValueError("炼制本体要求四份材料与真方完全一致")
            body = game.tianji_state["true_body_states"][artifact["id"]]
            if body.get("status") not in {"unmanifested", "destroyed"}:
                raise ValueError("此宝真体尚存，天地间无法再铸第二本体")
            minimum_tier = 3 if int(artifact["rank"]) <= 40 else 2
            current_tier = int(WORLD_SYSTEMS["world_profiles"].get(game.player.world, {}).get("tier", 1))
            if current_tier < minimum_tier:
                raise ValueError("当前世界法则不足以承载这件神机真体")
            replica_ratio = 1.0
        elif forge_kind != "replica":
            raise ValueError("未知的目标炼制类型")
        raw_combat_power = round(int(artifact["base_combat_power"]) * replica_ratio)
        combat_power_cap = tianji_world_combat_power_cap(game.player.world)
        return {
            "target": {"id": artifact["id"], "rank": artifact["rank"], "name": artifact["name"], "mold_id": artifact["mold_id"]},
            "selected_materials": [copy.deepcopy(row) | {"role": role} for role, row in selected],
            "slot_similarities": [round(value, 4) for value in similarities],
            "exact_slots": exact, "recipe_closeness": round(closeness, 4),
            "world_cap": world_cap, "quality_factor": round(quality_factor, 4),
            "replica_ratio": round(replica_ratio, 4), "forge_kind": forge_kind,
            "combat_power": raw_combat_power,
            "effective_combat_power":round(effective_tianji_combat_power(raw_combat_power, game.player.world)),
            "combat_power_cap":round(combat_power_cap) if combat_power_cap is not None else None,
            "effects": [self._tianji_public_effect(row) for row in artifact["effects"]],
        }

    def preview_tianji_forge(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._tianji_target_preview(self._load(game_id), payload)

    def forge_tianji_artifact(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        game = self._load(game_id)
        if game.pending_event or not game.player.alive or game.player.imprisonment:
            raise ValueError("当前状态无法开炉炼制神机")
        preview = self._tianji_target_preview(game, payload)
        artifact_def = self._tianji_artifact(game.tianji_state, preview["target"]["id"])
        # Preview validates every condition before a single material is spent.
        for material in preview["selected_materials"]:
            if material.get("source_kind") in {"plant", "inventory"}:
                if not remove_item(game.player, str(material["inventory_item_id"])):
                    raise ValueError("材料数量发生变化，请重新确认配方")
            else:
                stored = next((row for row in game.player.crafting_materials if str(row.get("id")) == str(material["id"])), None)
                if not stored:
                    raise ValueError("材料数量发生变化，请重新确认配方")
                game.player.crafting_materials.remove(stored)
        ratio = float(preview["replica_ratio"])
        is_true = preview["forge_kind"] == "true_body"
        combat_effects, persistent = _scaled_effects(artifact_def["effects"], ratio)
        game.player.crafting_sequence += 1
        instance_id = f"tianji-crafted-{game.id}-{game.player.crafting_sequence}"
        suffix = "真体" if is_true else f"{ratio:.0%}仿品"
        instance = {
            "id": instance_id, "name": artifact_def["name"] if is_true else f"仿·{artifact_def['name']}",
            "mold_id": artifact_def["mold_id"], "mold_name": self._tianji_config()["mold_nouns"][artifact_def["mold_id"]],
            "quality": "tianji_true" if is_true else "tianji_replica", "quality_name": suffix,
            "quality_multiplier": ratio, "creator_name": game.player.name, "creator_id": game.id,
            "created_year": game.player.age, "materials": [
                {key: row.get(key) for key in ("id", "definition_id", "name", "quality", "state", "source", "origin_world", "material_value")}
                for row in preview["selected_materials"]
            ],
            "material_effects": [], "actual_stats": {"combat_power": preview["combat_power"], **persistent},
            "combat_effects": combat_effects, "anchor_value": max(1, round(preview["combat_power"] / 12)),
            "description": f"天工神机榜第 {artifact_def['rank']} 位【{artifact_def['name']}】之{suffix}。目标炼制只继承目标法宝规则，不继承材料普通 Buff。",
            "is_natal": False,
            "tianji": {"definition_id": artifact_def["id"], "kind": "true_body" if is_true else "replica", "replica_ratio": ratio},
        }
        store_crafted_artifact(game.player, instance)
        game.tianji_state["player_artifacts"].append(instance_id)
        if is_true:
            game.tianji_state["true_body_states"][artifact_def["id"]] = {"status": "player", "holder_ref": instance_id}
            self._tianji_reveal(game, artifact_def["id"], 4, "亲手炼成真体")
        game.history.append(HistoryRecord(
            "SYS_TIANJI_FORGE", 1, game.player.age, "巧夺天工", artifact_def["id"],
            "true_body" if is_true else "replica",
            f"你以目标炼制法炼成【{instance['name']}】，配方接近度 {preview['recipe_closeness']:.0%}，最终发挥 {ratio:.1%}。",
            {"artifact_id": instance_id, "replica_ratio": ratio}, ["system", "tianji", "crafting"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def tianji_action(self, game_id: str, action: str, artifact_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        self._ensure_tianji_state(game)
        self._tianji_artifact(game.tianji_state, artifact_id)
        if action in {"activate", "deactivate"}:
            owned_rows = [
                row for row in game.player.crafted_artifacts
                if row.get("tianji", {}).get("definition_id") == artifact_id
            ]
            owned = max(
                owned_rows,
                key=lambda row: float(row.get("tianji", {}).get("replica_ratio", 0.0)),
                default=None,
            )
            if action == "deactivate":
                active_instance = str(game.tianji_state.get("activated_artifact_id") or "")
                active_owned = next((row for row in owned_rows if str(row.get("id")) == active_instance), None)
                owned = active_owned or owned
            if not owned:
                raise ValueError("你尚未持有这件神机的真体或仿品")
            if action == "activate":
                old_ids = {str(row.get("id")) for row in game.player.crafted_artifacts if row.get("tianji")}
                game.player.equipped_crafted_artifact_ids = [value for value in game.player.equipped_crafted_artifact_ids if value not in old_ids]
                game.player.equipped_crafted_artifact_ids.append(str(owned["id"]))
                game.tianji_state["activated_artifact_id"] = str(owned["id"])
            else:
                game.player.equipped_crafted_artifact_ids = [value for value in game.player.equipped_crafted_artifact_ids if value != str(owned["id"])]
                if game.tianji_state.get("activated_artifact_id") == owned["id"]:
                    game.tianji_state["activated_artifact_id"] = None
        else:
            raise ValueError("未知神机操作")
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def debug_reveal_all_tianji(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        if not tianji_content_available():
            raise ValueError("神机百变 DLC 当前未加载")
        self._ensure_tianji_state(game)
        game.tianji_state["knowledge"] = {
            str(artifact["id"]): 5 for artifact in game.tianji_state.get("artifacts", [])
        }
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def debug_tianji_gameplay(self, game_id: str) -> list[dict[str, Any]]:
        """Return blueprint diagnostics without mutating the frozen definitions."""
        game = self._load(game_id)
        if not tianji_content_available():
            return []
        self._ensure_tianji_state(game)
        return [gameplay_debug_row(artifact) for artifact in game.tianji_state.get("artifacts", [])]

    def _inject_tianji_npc_artifacts(self, game: GameState, target: dict[str, Any]) -> None:
        if not tianji_content_available():
            return
        if target.get("_tianji_injected"):
            return
        target["_tianji_injected"] = True
        self._ensure_tianji_state(game)
        holder_by_npc = {str(row["npc_id"]): (artifact_id, row) for artifact_id, row in game.tianji_state["holders"].items()}
        enemy_effects: list[dict[str, Any]] = list(target.get("enemy_artifact_effects", []))
        total_bonus = 0.0
        power_already_injected = bool(target.get("_tianji_power_injected"))
        ids = [str(target.get("npc_id", ""))]
        ids.extend(str(row.get("npc_id", "")) for row in target.get("members", []))
        for npc_id in dict.fromkeys(ids):
            held = holder_by_npc.get(npc_id)
            if not held:
                continue
            artifact_id, holder = held
            artifact = self._tianji_artifact(game.tianji_state, artifact_id)
            ratio = float(holder["replica_ratio"])
            bonus = effective_tianji_combat_power(
                int(artifact["base_combat_power"]) * ratio, game.player.world,
            )
            if not power_already_injected:
                total_bonus += bonus
            combat, _ = _scaled_effects(artifact["effects"], ratio)
            enemy_effects.extend(combat)
            self._tianji_reveal(game, artifact_id, 2, f"与持有者{npc_id}交战")
            for member in target.get("members", []):
                if str(member.get("npc_id", "")) == npc_id:
                    if not power_already_injected:
                        member["power"] = float(member.get("power", 0)) + bonus
                    member["tianji_artifact_name"] = artifact["name"]
        if total_bonus:
            target["target_power"] = float(target.get("target_power", 0)) + total_bonus
            target["enemy_artifact_effects"] = enemy_effects
        elif enemy_effects:
            target["enemy_artifact_effects"] = enemy_effects

    def _tianji_observe_npc(self, game: GameState, npc_id: str) -> None:
        if not tianji_content_available():
            return
        self._ensure_tianji_state(game)
        for artifact_id, holder in game.tianji_state["holders"].items():
            if str(holder.get("npc_id", "")) == str(npc_id):
                self._tianji_reveal(game, artifact_id, 1, f"目睹持宝者{npc_id}")

    def _tianji_preview_npc_power(self, game: GameState, target: dict[str, Any]) -> None:
        if not tianji_content_available() or target.get("_tianji_power_injected"):
            return
        self._ensure_tianji_state(game)
        holder_by_npc = {
            str(row["npc_id"]): (artifact_id, row)
            for artifact_id, row in game.tianji_state["holders"].items()
        }
        total = 0.0
        ids = [str(target.get("npc_id", ""))]
        ids.extend(str(row.get("npc_id", "")) for row in target.get("members", []))
        for npc_id in dict.fromkeys(ids):
            held = holder_by_npc.get(npc_id)
            if not held:
                continue
            artifact_id, holder = held
            artifact = self._tianji_artifact(game.tianji_state, artifact_id)
            bonus = effective_tianji_combat_power(
                int(artifact["base_combat_power"]) * float(holder["replica_ratio"]), game.player.world,
            )
            total += bonus
            for member in target.get("members", []):
                if str(member.get("npc_id", "")) == npc_id:
                    member["power"] = float(member.get("power", 0)) + bonus
        if total:
            target["target_power"] = float(target.get("target_power", 0)) + total
            target["target_power_display"] = float(target.get("target_power_display", target["target_power"])) + total
            target["_tianji_power_injected"] = True

    def _tianji_handle_npc_kill(self, game: GameState, npc_id: str) -> str:
        if not tianji_content_available() or not game.tianji_state:
            return ""
        found = next(((artifact_id, row) for artifact_id, row in game.tianji_state.get("holders", {}).items() if str(row.get("npc_id")) == str(npc_id)), None)
        if not found:
            return ""
        artifact_id, holder = found
        artifact = self._tianji_artifact(game.tianji_state, artifact_id)
        ratio = float(holder["replica_ratio"])
        is_true = holder["kind"] == "true_body"
        combat_effects, persistent = _scaled_effects(artifact["effects"], ratio)
        game.player.crafting_sequence += 1
        instance_id = f"tianji-loot-{game.id}-{game.player.crafting_sequence}"
        instance = {
            "id": instance_id, "name": artifact["name"] if is_true else f"仿·{artifact['name']}",
            "mold_id": artifact["mold_id"], "mold_name": self._tianji_config()["mold_nouns"][artifact["mold_id"]],
            "quality": "tianji_true" if is_true else "tianji_replica",
            "quality_name": "神机真体" if is_true else f"{ratio:.0%}仿品", "quality_multiplier": ratio,
            "creator_name": "未知古修", "created_year": game.player.age, "materials": [], "material_effects": [],
            "actual_stats": {"combat_power": round(int(artifact["base_combat_power"]) * ratio), **persistent},
            "combat_effects": combat_effects, "anchor_value": max(1, round(int(artifact["base_combat_power"]) * ratio / 12)),
            "description": f"你从持有者手中夺得的天工神机榜第 {artifact['rank']} 位法宝。",
            "is_natal": False, "tianji": {"definition_id": artifact_id, "kind": holder["kind"], "replica_ratio": ratio},
        }
        store_crafted_artifact(game.player, instance)
        game.tianji_state["player_artifacts"].append(instance_id)
        del game.tianji_state["holders"][artifact_id]
        if is_true:
            game.tianji_state["true_body_states"][artifact_id] = {"status": "player", "holder_ref": instance_id}
            self._tianji_reveal(game, artifact_id, 4, "击杀持有者并夺得真体")
        else:
            self._tianji_reveal(game, artifact_id, 3, "击杀持有者并取得仿品")
        return f" 你夺得天工神机【{instance['name']}】。"

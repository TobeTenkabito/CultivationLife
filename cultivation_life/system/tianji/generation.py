from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import math
    import random
    from typing import Any
    from ...content_registry import WORLD_SYSTEMS
    from ...combat_rule_engine import describe_rule
    from ...models import GameState
    from ...tianji_theme_rules import (
        compile_theme_rules,
        generate_gameplay_blueprint,
        sample_total_effect_count,
        validate_theme_consistency,
    )
    from ..tianji_system import _stable_rng, _tianji_effect_description
    from .. import tianji_system as _source
    TIANJI_GENERATION_VERSION = _source.TIANJI_GENERATION_VERSION
    PRIMITIVES = _source.PRIMITIVES


class TianjiGenerationMethods:
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
            world = worlds[index % len(worlds)] if index < len(worlds) else rng.choice(worlds)
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

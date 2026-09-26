from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import copy
    from typing import Any
    from ...monster_bloodline_rules import (
        BLOODLINE_RULE_EFFECTS,
        describe_generated_trait,
        generated_trait_id,
    )
    from ...models import GameState
    from ..tianji_system import tianji_config, tianji_content_available, _stable_rng
    from .. import tianji_system as _source
    TIANJI_GENERATION_VERSION = _source.TIANJI_GENERATION_VERSION
    TIANJI_WINDOW_SCHEDULES = _source.TIANJI_WINDOW_SCHEDULES
    PRIMITIVES = _source.PRIMITIVES


class TianjiStateMethods:
    @staticmethod
    def _tianji_config() -> dict[str, Any]:
        return tianji_config()

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
        if not state.get("expanded_world_distribution"):
            # Extend circulation without rerolling old artifact definitions,
            # material qualities, recipes, owned instances or current holders.
            distribution = state.setdefault("world_distribution", {})
            extras = state.setdefault("material_extra_worlds", {})
            worlds = list(self._tianji_config()["base_worlds"])
            existing = {row["origin_world"] for row in state["artifacts"]}
            free = [row for row in state["artifacts"] if row["id"] not in state["holders"]
                    and state["true_body_states"].get(row["id"], {}).get("status") == "unmanifested"]
            for index, world in enumerate(w for w in worlds if w not in existing):
                if index < len(free):
                    distribution[free[index]["id"]] = world
                if world in state["holder_worlds_initialized"]:
                    state["holder_worlds_initialized"].remove(world)
            material_worlds = {row["world"] for row in state["materials"]}
            for index, world in enumerate(w for w in worlds if w not in material_worlds):
                for row in state["materials"][index::len(worlds)]:
                    extras.setdefault(row["id"], []).append(world)
            state["expanded_world_distribution"] = True
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

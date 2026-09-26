from __future__ import annotations

import copy
import random
import uuid
from typing import Any
from ...content_registry import (
    PATH_NAMES,
    ROOT_NAMES,
    TECHNIQUE_CATALOG,
    WORLD_SYSTEMS,
    MONSTER_BLOODLINE_SETTINGS,
)
from ...models import GameState, HistoryRecord, Player, SectNpc
from ...rules import (
    add_item,
    assign_technique,
    combat_power,
    has_item,
    learn_technique,
    max_hp,
    max_mp,
    opportunity_required,
    roll_lifespan,
    qi_level_threshold,
)
from ...runtime import encode_rng, now_iso
from ...system.monster_bloodline_system import initialize_monster_bloodline
from ...system.ghost_system import ensure_ghost_cultivation_state, ghost_cultivation_active
from ..dependencies import SessionDependencies


def create_game(
    deps: SessionDependencies, name: str, spirit_root: str, path: str, seed: int | None = None,
    technique_element: str | None = None, preset_id: str | None = None,
    start_world: str | None = None, monster_species_id: str | None = None,
    gender: str = "male",
) -> dict[str, Any]:
    preset = next(
        (entry for entry in WORLD_SYSTEMS.get("quick_start_presets", []) if entry["id"] == preset_id),
        None,
    ) if preset_id else None
    if preset_id and preset is None:
        raise ValueError("未知快速开局预设")
    if preset and not preset.get("enabled"):
        raise ValueError(preset.get("status", "该快速开局尚未开放"))
    if preset:
        spirit_root = str(preset["spirit_root"])
        path = str(preset["path"])
    if spirit_root not in ROOT_NAMES:
        raise ValueError("未知灵根")
    if path not in PATH_NAMES:
        raise ValueError("未知主修类型")
    if gender not in {"male", "female"}:
        raise ValueError("未知性别")
    allowed_start_worlds = WORLD_SYSTEMS.get("start_worlds", {}).get(path, ["human"])
    selected_start_world = str(start_world or "human")
    if not preset and selected_start_world not in allowed_start_worlds:
        raise ValueError("该修行道统无法从所选界面开局")
    clean_name = name.strip()[:16] or "无名散修"
    actual_seed = seed if seed is not None else random.SystemRandom().randrange(1, 2**31)
    rng = random.Random(actual_seed)
    player = Player(
        name=clean_name, spirit_root=spirit_root, path=path, gender=gender,
        born_rootless=spirit_root == "none",
        world=selected_start_world,
    )
    if path == "monster" and deps.bloodline_content_available():
        player.race = "monster"
        initialize_monster_bloodline(player, monster_species_id)
        starter_id = str(MONSTER_BLOODLINE_SETTINGS.get("starter_technique_id", ""))
        if starter_id in TECHNIQUE_CATALOG:
            starter = copy.deepcopy(TECHNIQUE_CATALOG[starter_id])
            learn_technique(player, starter)
            assign_technique(player, starter, "main")
    if path == "demonic":
        starter = copy.deepcopy(TECHNIQUE_CATALOG["TECH_DEMON_BREATHING"])
        learn_technique(player, starter)
        assign_technique(player, starter, "main")
        sense = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BLOOD_SOUL_SENSE"])
        learn_technique(player, sense)
        assign_technique(player, sense, "divine_sense")
        player.divine_sense_rank = 1
        player.divine_sense_experience = 0.0
    if path == "ghost":
        starter = copy.deepcopy(TECHNIQUE_CATALOG["TECH_GHOST_BREATHING"])
        learn_technique(player, starter)
        assign_technique(player, starter, "main")
        sense = copy.deepcopy(TECHNIQUE_CATALOG["TECH_SOUL_ECHO_SENSE"])
        learn_technique(player, sense)
        assign_technique(player, sense, "divine_sense")
        player.divine_sense_rank = 1
        player.divine_sense_experience = 0.0
    if preset:
        player.realm_index = int(preset["realm_index"])
        player.layer = int(preset["layer"])
        player.age = int(preset["age"])
        player.world = str(preset["world"])
        player.race = str(preset["race"])
        player.karma = float(preset.get("karma", 0))
        player.sha_qi = int(preset.get("sha_qi", 0))
        player.fame = float(preset.get("fame", 0))
        player.body_training = max(0, int(preset.get("body_training", player.body_training)))
        player.body_progress = max(0.0, float(preset.get("body_progress", player.body_progress)))
        player.divine_sense_rank = max(0, int(preset.get("divine_sense_rank", player.divine_sense_rank)))
        player.divine_sense_experience = max(
            0.0, float(preset.get("divine_sense_experience", player.divine_sense_experience)),
        )
        player.story_flags = list(dict.fromkeys(str(flag) for flag in preset.get("story_flags", [])))
        player.additional_roots = list(dict.fromkeys(preset.get("additional_roots", [])))
        player.immortal_power_converted = bool(preset.get("immortal_power_converted", False))
        player.immortal_conversion_stage = 5 if player.immortal_power_converted else 0
        player.immortal_conversion_last_age = player.age if player.world == "celestial" else None
        starting_qi_level = {3: 5, 4: 8, 5: 12, 6: 17, 7: 23, 8: 30, 9: 30}.get(player.realm_index, 0)
        starting_source = "demon" if path == "demonic" else "monster" if path == "monster" else "yin" if path == "ghost" else "spirit"
        player.qi_experience[starting_source] = qi_level_threshold(starting_qi_level)
        # Compatibility presets may combine a path-native circulation with
        # neutral upper-realm arts.  Seed spirit mastery as well so every
        # equipped starting technique is immediately usable.
        if starting_qi_level and starting_source != "spirit":
            player.qi_experience["spirit"] = qi_level_threshold(starting_qi_level)
        if player.realm_index >= 6:
            for affinity in ("metal", "wood", "water", "fire", "earth"):
                if affinity not in deps._base_affinities(player) and affinity not in player.additional_roots:
                    player.additional_roots.append(affinity)
        assign_technique(player, copy.deepcopy(TECHNIQUE_CATALOG[preset["main_technique"]]), "main")
        assign_technique(player, copy.deepcopy(TECHNIQUE_CATALOG[preset["support_technique"]]), "support")
        if preset.get("body_technique"):
            assign_technique(player, copy.deepcopy(TECHNIQUE_CATALOG[preset["body_technique"]]), "body")
        if preset.get("divine_sense_technique"):
            assign_technique(
                player, copy.deepcopy(TECHNIQUE_CATALOG[preset["divine_sense_technique"]]), "divine_sense",
            )
        for technique_id in preset.get("combat_techniques", []):
            assign_technique(player, copy.deepcopy(TECHNIQUE_CATALOG[technique_id]), "combat")
        for item in preset.get("inventory", []):
            add_item(player, item["id"], int(item["quantity"]))
        player.opportunity = round(opportunity_required(player) * float(preset.get("opportunity_fraction", 0)), 1)
    player.divine_sense_rank = max(
        player.divine_sense_rank,
        deps._cultivation_sense_requirement(player.realm_index, player.layer),
    )
    # Every life begins with one ordinary weapon already in the equipment
    # section, including mortal creation and every quick-start preset.
    if not has_item(player, "spirit_sword"):
        add_item(player, "spirit_sword")
    player.lineage_race = player.race
    player.allegiance_race = player.race
    player.location_id = deps.maps.default_location(player.world)
    ensure_ghost_cultivation_state(player)
    player.lifespan = roll_lifespan(player, rng)
    if ghost_cultivation_active(player):
        player.lifespan = None
    if player.lifespan is not None:
        player.lifespan = max(player.lifespan, player.age + 1)
    player.hp = max_hp(player)
    player.mp = max_mp(player)
    if preset:
        # Preserve the authored quick-start/benchmark ratio when DLCs raise
        # every realm's standard.  combat_power() applies the live summed
        # DLC percentage to this base reference, so configuration changes
        # never leave a stale permanent bonus in the save.
        player.quick_start_base_combat_power = combat_power(player)
    if player.realm_index >= 6 and player.world != "celestial":
        thunder = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
        player.next_tribulation_age = player.age + int(thunder["interval_years"])
        player.tribulation_power = float(thunder["base_power"])
    created = now_iso()
    game = GameState(str(uuid.uuid4()), actual_seed, player, created, created)
    game.sects = deps._new_sects()
    game.world_npcs = deps._new_world_npcs()
    deps._ensure_sects(game)
    deps._ensure_world_npcs(game)
    deps._ensure_npc_formations(game)
    deps._ensure_sage_state(game)
    deps._ensure_guixu_state(game)
    deps._ensure_tianji_state(game)
    if player.world == "celestial":
        deps._ensure_heavenly_court(game, rng)
    deps._ensure_race_relations(game)
    deps._ensure_sect_relations(game)
    game.history.append(HistoryRecord(
        "SYS_BIRTH", 1, player.age, "问道之始", None, "created",
        (
            f"{clean_name}以快速开局承接既有因果，当前为{deps._npc_realm_name(SectNpc('', '', '', player.realm_index, player.layer, 0, 1))}，"
            f"身具{ROOT_NAMES[spirit_root]}，已配置默认功法、属性与行囊。"
            if preset else
            f"{clean_name}以{'女' if gender == 'female' else '男'}身生于{WORLD_SYSTEMS['world_names'].get(player.world, player.world)}，身具{ROOT_NAMES[spirit_root]}，"
            f"心向{PATH_NAMES[path]}，但尚未获得任何功法。"
        ),
        {"lifespan": player.lifespan}, ["system", "milestone"],
    ))
    deps._ensure_market(game, rng)
    deps._ensure_ghost_parade(game, rng)
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    deps.achievements.ensure_global_metadata()
    return deps.present(game)

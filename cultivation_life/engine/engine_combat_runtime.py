from __future__ import annotations

import copy
import random
from typing import Any

from ..content_registry import (
    ITEM_CATALOG, REALMS,
    RACE_DEFINITIONS, RACE_SYSTEMS, TECHNIQUE_CATALOG,
    TECHNIQUE_ELEMENT_NAMES, WORLD_SYSTEMS,
)
from ..system.combat_system import BattleUnit, PlayerCombatSystem, stat_comparison
from ..models import GameState, HistoryRecord, Player, SectNpc
from ..rules import (
    add_item,
    assign_technique,
    can_player_practice_technique,
    combat_root_mana_cost_multiplier,
    combat_power,
    expected_combat_power,
    effective_karma,
    learn_technique,
    max_hp,
    max_mp,
    opportunity_required,
    public_player,
    realm,
    root_definition,
    root_elements,
    roll_lifespan,
    qi_level,
    divine_sense_level,
)


from ..world_state import (
    race_pair,
)
from ..system.crafting_system import crafted_artifact_bonuses, crafted_combat_effects
from ..system.formation_system import (
    active_formation_profile, ensure_formation_state,
    formation_battle_experience_gain,
)
from ..system.monster_bloodline_system import (
    bloodline_content_available,
)
from ..monster_general_traits import grant_random_general_monster_trait
from ..system.ghost_system import (
    ghost_cultivation_active,
    grant_intrinsic_progression_if_new_highwater,
    grant_wangsheng, reincarnation_breakthrough_bonus,
)


class EngineCombatRuntimeMixin:
    def _player_combat_units(self, game: GameState, target: dict[str, Any] | None = None) -> list[BattleUnit]:
        """Build independent units for player combat; each brings full power."""
        player = game.player
        units = [BattleUnit(
            "player", player.name, "player", max(1.0, combat_power(player)),
            player.realm_index, player.path,
        )]
        for puppet in player.puppets:
            kind = str(puppet.get("type", "mechanical"))
            if not puppet.get("alive", True) or kind not in {"mechanical", "corpse"}:
                continue
            field = "durability" if kind == "mechanical" else "corpse_integrity"
            integrity = max(0.0, min(1.0, float(puppet.get(field, 100.0)) / 100.0))
            units.append(BattleUnit(
                str(puppet.get("id")), str(puppet.get("name", "无名傀儡")), kind,
                max(0.0, float(puppet.get("combat_power", 0))),
                int(puppet.get("realm_index", player.realm_index)),
                "ghost" if kind == "corpse" else "dao", integrity, field,
            ))

        for relation in self._public_party(game):
            power = max(0.0, float(relation.get("combat_power", 0)))
            units.append(BattleUnit(
                str(relation.get("id", "companion")), str(relation.get("name", "同行者")),
                "companion", power, int(relation.get("realm_index", player.realm_index)),
                str(relation.get("path", "dao")),
            ))
        for puppet in player.puppets:
            if not puppet.get("alive", True) or puppet.get("type") != "living":
                continue
            effective = max(0.0, float(puppet.get("combat_power", 0)))
            control = max(0.2, min(1.0, float(puppet.get("control", 100)) / 100.0))
            units.append(BattleUnit(
                str(puppet.get("id")), str(puppet.get("name", "无名活傀")), "living",
                effective, int(puppet.get("realm_index", player.realm_index)),
                str(puppet.get("path", "demonic")), control, "control",
            ))
        target = target or {}
        target_power = max(1.0, float(target.get("target_power", 1.0)))
        selected_choice = str(target.get("story_choice_id", ""))
        for index, ally in enumerate(target.get("player_allies", [])):
            if selected_choice in ally.get("exclude_choices", []):
                continue
            effective_power = target_power * float(ally["power_ratio"])
            ally_realm = max(0, min(len(REALMS) - 1, player.realm_index + int(ally.get("realm_offset", 0))))
            units.append(BattleUnit(
                f"story-ally-{index}", str(ally["name"]), "story_ally",
                effective_power, ally_realm, str(ally.get("path", "dao")),
                full_power=self._story_unit_full_power(ally, ally_realm, effective_power),
            ))
        return units

    def _combat_battlefield_tags(self, game: GameState, target: dict[str, Any]) -> list[str]:
        explicit = list(target.get("battlefield_tags", target.get("combat_tags", [])))
        location_id = self.maps.normalize_location(game.player.world, game.player.location_id)
        location = self.maps.location(game.player.world, location_id)
        natural = str(target.get("natural_terrain") or location["combat_terrain"])
        artificial = [*target.get("artificial_conditions", []), *explicit]
        return [natural, *dict.fromkeys(str(tag) for tag in artificial)]

    @staticmethod
    def _apply_support_damage(player: Player, updates: list[dict[str, Any]]) -> None:
        by_id = {str(entry.get("id")): entry for entry in player.puppets}
        for update in updates:
            puppet = by_id.get(str(update.get("id")))
            field = update.get("field")
            if not puppet or not field:
                continue
            puppet[str(field)] = round(float(update.get("after", 0)), 1)
            if update.get("destroyed"):
                puppet["alive"] = False

    def _record_player_combat(
        self, game: GameState, target: dict[str, Any], resolution: Any, result: str,
    ) -> None:
        report = resolution.to_dict()
        report.update({
            "title": f"与{target.get('target_name', '未知对手')}的战报",
            "target_name": target.get("target_name", "未知对手"),
            "result": result,
            "player_defending": bool(target.get("player_defending")),
            "stat_comparison": stat_comparison(resolution),
            "age": game.player.age,
        })
        game.last_combat_report = report
        longest_enemy_streak = 0
        current_enemy_streak = 0
        for combat_round in report.get("rounds", []):
            if combat_round.get("initiative") == "enemy":
                current_enemy_streak += 1
                longest_enemy_streak = max(longest_enemy_streak, current_enemy_streak)
            else:
                current_enemy_streak = 0
        if longest_enemy_streak:
            game.player.milestones["enemy_initiative_streak"] = max(
                int(game.player.milestones.get("enemy_initiative_streak", 0)),
                longest_enemy_streak,
            )

    @staticmethod
    def _combat_report_lead(resolution: Any, hp_loss: float, mp_loss: float) -> str:
        turns = "；".join(resolution.key_events[:3])
        artificial = (
            f"，人工条件：{'、'.join(resolution.artificial_conditions)}"
            if resolution.artificial_conditions else "，无人工战场条件"
        )
        terrain = f"，自然场地：{resolution.natural_terrain}{artificial}"
        return (
            f"【{resolution.result_grade}·{resolution.mode}】战前判断为{resolution.assessment}{terrain}。"
            f"自动交战 {len(resolution.rounds)} 轮，HP -{hp_loss:.0f}、MP -{mp_loss:.0f}。"
            f"关键转折：{turns} "
        )

    def _combat(self, game: GameState, target: dict[str, Any], lethal: bool, rng: random.Random) -> tuple[str, str]:
        """Resolve player-involved combat through the detailed automatic system.

        NPC-only field battles deliberately remain in ``WarSystemMixin`` and use
        their legacy aggregate-power logic.
        """
        player = game.player
        self._inject_tianji_npc_artifacts(game, target)
        ensure_formation_state(player)
        portable_formation = active_formation_profile(player)
        ground_array = None if portable_formation.get("active") else self._local_ground_formation(game)
        if ground_array:
            ground_profile = self._ground_profile(player, ground_array)
            target["allied_formation_profile"] = ground_profile
            target["formation_initial_integrity"] = float(ground_array.get("durability", 0.0)) / 100.0
            target["ground_formation_id"] = str(ground_array["id"])
        ground_array_id = str(ground_array.get("id", "")) if ground_array else ""
        npc_ids = [str(target.get("npc_id", "")), *(
            str(member.get("npc_id", "")) for member in target.get("members", [])
        )]
        npc_ids = [npc_id for npc_id in dict.fromkeys(npc_ids) if npc_id in game.npc_formations]
        enemy_formation_id = max(
            npc_ids, key=lambda npc_id: self._npc_formation_power_multiplier(game, npc_id), default="",
        )
        if enemy_formation_id:
            enemy_entry = game.npc_formations[enemy_formation_id]
            enemy_profile = self._npc_formation_profile(
                game, enemy_formation_id, detailed_spectrum=True,
            )
            if enemy_profile.get("active"):
                target["enemy_formation_profile"] = enemy_profile
                target["enemy_formation_initial_integrity"] = float(enemy_entry.get("durability", 0.0)) / 100.0
                target["enemy_formation_npc_id"] = enemy_formation_id
        target["natal_artifact_effects"] = [
            *self._natal_artifact_combat_effects(game), *crafted_combat_effects(game.player),
        ]
        if player.world == "celestial":
            if self._court_law_active(game, "martial_gods"):
                target["global_damage_multiplier"] = 1.10
            wanted_ids = set(game.heavenly_court.get("wanted_ids", []))
            target_ids = {str(target.get("npc_id", "")), *(
                str(member.get("npc_id", "")) for member in target.get("members", [])
            )}
            if wanted_ids.intersection(target_ids):
                target["player_damage_multiplier"] = 1.10
            if "player" in wanted_ids:
                target["enemy_damage_multiplier"] = 1.10
            if self._court_law_active(game, "immortal_slaughter"):
                player.karma -= 10
            if (
                self._court_law_active(game, "universal_protection")
                and target.get("combat_type") == "cultivator"
                and rng.random() < (0.80 if lethal else 0.25)
                and "player" not in wanted_ids
            ):
                game.heavenly_court["wanted_ids"].append("player")
                player.milestones["became_wanted_target"] = 1
        equipped = [entry for entry in [player.technique, *(player.combat_techniques or [])] if entry]
        if any(not can_player_practice_technique(player, entry.element) for entry in equipped):
            return "technique_blocked", "灵根属性与五行功法不合，无法运转功法迎战。"

        hp_max = max_hp(player)
        mp_max = max_mp(player)
        player_units = self._player_combat_units(game, target)
        own_power = max(1.0, sum(unit.power * unit.integrity for unit in player_units))
        target_power = max(1.0, float(target["target_power"]))
        ratio = own_power / target_power
        opponent_ranks = [
            (
                int(target.get("target_realm_index", player.realm_index) or player.realm_index),
                int(target.get("target_layer", 1) or 1),
            ),
            *(
                (int(member.get("realm_index", 0) or 0), int(member.get("layer", 1) or 1))
                for member in target.get("members", [])
            ),
        ]
        opponent_realm, opponent_layer = max(opponent_ranks)
        resolution = PlayerCombatSystem.resolve(
            player, player_units, target, lethal, rng,
            current_hp_ratio=player.hp / max(1.0, hp_max),
            current_mp_ratio=player.mp / max(1.0, mp_max),
            battlefield_tags=self._combat_battlefield_tags(game, target),
            mana_cost_multiplier=combat_root_mana_cost_multiplier(
                player, opponent_realm, opponent_layer,
            ),
        )
        used_formation = (
            target.get("allied_formation_profile", {})
            if ground_array else portable_formation
        )
        formation_gain = formation_battle_experience_gain(used_formation, len(resolution.rounds), ratio)
        if formation_gain > 0:
            self._grant_art_experience(player, "formation", formation_gain)
            # Formation experience changes long-range attenuation. Rebuild the
            # cached matrix on the next read, never in the middle of this fight.
            player.formation_profile_cache = {}
            resolution.formation_experience_gain = formation_gain
        if ground_array_id and resolution.formation_integrity_end is not None:
            # Combat profile reads normalize old formation state and may
            # replace list dictionaries. Reacquire the persistent object by
            # identity before writing permanent wear.
            ground_array = next(
                (row for row in player.formation_ground_arrays if row.get("id") == ground_array_id), None,
            )
        if ground_array and resolution.formation_integrity_end is not None:
            before = max(0.0, min(100.0, float(ground_array.get("durability", 0.0))))
            simulated = max(0.0, min(100.0, float(resolution.formation_integrity_end) * 100.0))
            raw_wear = max(0.0, before - simulated)
            settings = self._formation_rules()
            wear = min(float(settings.get("ground_battle_max_wear", 26.0)), raw_wear)
            if before > 0:
                wear = max(float(settings.get("ground_battle_min_wear", 1.0)), wear)
            ground_array["durability"] = round(max(0.0, before - wear), 4)
            ground_array["battles"] = int(ground_array.get("battles", 0)) + 1
        if enemy_formation_id and resolution.enemy_formation_integrity_end is not None:
            enemy_entry = game.npc_formations.get(enemy_formation_id)
            if enemy_entry:
                before = max(0.0, min(100.0, float(enemy_entry.get("durability", 0.0))))
                simulated = max(0.0, min(100.0, float(resolution.enemy_formation_integrity_end) * 100.0))
                raw_wear = max(0.0, before - simulated)
                settings = self._formation_rules()
                wear = min(float(settings.get("ground_battle_max_wear", 26.0)), raw_wear)
                if before > 0:
                    wear = max(float(settings.get("ground_battle_min_wear", 1.0)), wear)
                enemy_entry["durability"] = round(max(0.0, before - wear), 4)
                enemy_entry["battles"] = int(enemy_entry.get("battles", 0)) + 1
        loss_scale = max(0.0, float(target.get("loss_scale", 1.0)))
        hp_loss = hp_max * resolution.hp_loss_ratio * float(target.get("hp_loss_scale", loss_scale))
        mp_loss = mp_max * resolution.mp_loss_ratio * float(target.get("mp_loss_scale", loss_scale))
        player.hp = max(0.0 if lethal else 1.0, player.hp - hp_loss)
        if resolution.retreat_impossible and not resolution.death_prevented:
            # Ordinary battle injury is capped, but an overwhelmingly stronger
            # lethal pursuer leaves no valid route for that generic retreat.
            player.hp = 0.0
        if resolution.death_prevented:
            player.hp = max(1.0, player.hp)
        player.mp = max(0.0, player.mp - mp_loss)
        self._apply_support_damage(player, resolution.support_updates)
        lead = self._combat_report_lead(resolution, hp_loss, mp_loss)

        if target.get("combat_type") == "beast":
            threshold = float(target.get("success_threshold", 1.2))
            if resolution.outcome == "victory":
                fame_config = WORLD_SYSTEMS["fame"]
                fame_gain = (
                    float(fame_config["kill_gain_base"])
                    + int(target.get("target_realm_index", 0)) * float(fame_config["kill_realm_scale"])
                )
                player.fame += fame_gain
                demonic_gain = self._grant_demonic_kill_opportunity(
                    player, int(target.get("target_realm_index", 0)),
                )
                result = "killed"
                self._record_player_combat(game, target, resolution, result)
                return result, lead + (
                    f"你在复杂交锋中建立压制并击杀了{target['target_name']}；狩猎准备要求为对手战力的 {threshold:.1f} 倍。"
                    f" 威名 +{fame_gain:.0f}。"
                    + (f" 杀戮炼化机缘 +{demonic_gain:.0f}。" if demonic_gain else "")
                )
            if resolution.retreat_impossible and resolution.death_prevented:
                result = "defeat_survived"
                self._record_player_combat(game, target, resolution, result)
                return result, lead + (
                    f"{target['target_name']}以三倍以上战力封死退路，逃脱预案失败；"
                    "涅槃类能力替你承受了必死一击，但狩猎目标未能完成。"
                )
            if player.hp <= 0:
                self._die(
                    game, f"猎妖时不敌{target['target_name']}，身死道消", "SYS_BEAST_HUNT",
                    offer_captive_possession=bool(target.get("non_story_combat")),
                )
                result = "dead"
                self._record_player_combat(game, target, resolution, result)
                return result, lead + f"你未能完成对妖兽的压制，反被{target['target_name']}所杀。"
            result = "defeat"
            self._record_player_combat(game, target, resolution, result)
            return result, lead + f"你未达到狩猎所需的 {threshold:.1f} 倍准备优势，预案自动护送你负伤退走。"

        if resolution.outcome != "victory":
            if not lethal:
                result = "defeat"
                self._record_player_combat(game, target, resolution, result)
                return result, lead + f"你在切磋中败给了{target['target_name']}，预案及时收手，无人伤及性命。"
            if resolution.retreat_impossible and resolution.death_prevented:
                result = "defeat_survived"
                self._record_player_combat(game, target, resolution, result)
                return result, lead + (
                    f"{target['target_name']}以三倍以上战力封死所有退路，逃脱预案失败；"
                    "涅槃类能力替你承受了必死一击，才没有当场陨落。"
                )
            if player.hp <= 0:
                can_take_captive = bool(
                    target.get("non_story_combat")
                    and self._post_battle_possession_candidates(game)
                )
                captured = False if can_take_captive else self._capture_defeated_ghost(game, target, rng)
                if not captured:
                    self._die(
                        game, f"不敌{target['target_name']}，身死道消", "SYS_COMBAT",
                        offer_captive_possession=can_take_captive,
                    )
                result = "controlled" if captured else "dead"
                self._record_player_combat(game, target, resolution, result)
                return result, lead + (
                    f"你败给{target['target_name']}，魂体被拘入禁制。"
                    if captured else (
                        f"敌方战力达到你方三倍以上，保命预案必定失败；你败给{target['target_name']}并身死。"
                        if resolution.retreat_impossible
                        else f"保命预案未能撕开退路，你败给{target['target_name']}并身死。"
                    )
                )
            result = "defeat"
            self._record_player_combat(game, target, resolution, result)
            return result, lead + f"你败给了{target['target_name']}，预案保存主要力量后自动脱离。"

        if target.get("capture"):
            if not resolution.capture_ready:
                result = "victory_escape"
                self._record_player_combat(game, target, resolution, result)
                return result, lead + "你虽取得战场控制权，但神识、身法与封锁态势不足，对方仍然遁走。"
            result, capture_summary = self._capture_cultivator(game, target, own_power, rng)
            self._record_player_combat(game, target, resolution, result)
            return result, lead + capture_summary
        if not lethal or resolution.objective == "repel":
            result = "victory"
            self._record_player_combat(game, target, resolution, result)
            return result, lead + f"你达成击退目标，{target['target_name']}失去战意后退出交锋。"

        members = target.get("members") or [{
            "name": target["target_name"], "power": target_power,
            "realm_index": target["target_realm_index"], "npc_id": target.get("npc_id"),
            "faction_id": target.get("faction_id"), "race": target.get("race", "human"),
            "treasure_item_id": target.get("treasure_item_id"),
        }]
        victim = min(members, key=lambda member: float(member["power"]))
        victim_ratio = own_power / max(1.0, float(victim["power"]))
        pursuit_chance = min(
            0.99,
            0.52 + max(0.0, victim_ratio - 1.0) * 0.11
            + max(0.0, float(target.get("pursuit_chance_bonus", 0.0))),
        )
        if resolution.kill_ready and rng.uniform(0.0, 1.0) < pursuit_chance:
            target["killed_member"] = victim
            fame_before = player.fame
            treasure_id = victim.get("treasure_item_id")
            tianji_spoils = self._tianji_handle_npc_kill(game, str(victim.get("npc_id", "")))
            self._apply_cultivator_kill(game, victim, rng)
            demonic_gain = self._grant_demonic_kill_opportunity(player, int(victim["realm_index"]))
            spoils = (
                f" 你夺得{ITEM_CATALOG[treasure_id].name}。"
                if treasure_id in ITEM_CATALOG and victim.get("npc_id") else ""
            )
            spoils += tianji_spoils
            fame_text = f" 威名 +{player.fame - fame_before:.0f}。"
            victim_path = str(victim.get("path", "dao"))
            if player.path == "monster" and victim_path != "monster" and not target.get("player_defending"):
                sha_text = ""
                if victim_path == "dao":
                    fame_rules = WORLD_SYSTEMS["fame"]
                    sha_gain = round(
                        float(fame_rules["monster_dao_kill_sha_base"])
                        + int(victim["realm_index"]) * float(fame_rules["monster_dao_kill_sha_realm_scale"])
                    )
                    sha_gain = self._sage_scaled_gain(player, sha_gain, "sha_qi_gain_reduction")
                    player.sha_qi += sha_gain
                    sha_text = f" 煞气 +{sha_gain}。"
                result = "killed"
                self._record_player_combat(game, target, resolution, result)
                return (
                    result,
                    lead + f"你在追击阶段击杀了{victim['name']}；妖修猎杀异道不沾因果。"
                    + sha_text + fame_text + spoils
                    + (f" 杀戮炼化机缘 +{demonic_gain:.0f}。" if demonic_gain else ""),
                )
            if target.get("kill_karma", True) and not target.get("player_defending"):
                if victim.get("notorious"):
                    reduction = min(player.karma, max(35.0, float(victim.get("notoriety", 0)) * 0.45))
                    player.karma = max(0.0, player.karma - reduction)
                    result = "killed"
                    self._record_player_combat(game, target, resolution, result)
                    return result, lead + f"你在追击阶段诛杀恶贯满盈的{victim['name']}，因果 -{reduction:.0f}。{fame_text}{spoils}" + (f" 杀戮炼化机缘 +{demonic_gain:.0f}。" if demonic_gain else "")
                karma_gain = round(18 + int(victim["realm_index"]) * 7)
                alliance = self._race_alliance(game, player.world, self._player_allegiance_race(player), str(victim.get("race", "human")))
                if alliance:
                    karma_gain = round(karma_gain * float(alliance["kill_karma_multiplier"]) + float(alliance["kill_karma_flat"]))
                player.karma += karma_gain
                warning = f" 你违背了{alliance['name']}。" if alliance else ""
                result = "killed"
                self._record_player_combat(game, target, resolution, result)
                return result, lead + f"你在追击阶段击杀了{victim['name']}，因果 +{karma_gain}。{warning}{fame_text}{spoils}" + (f" 杀戮炼化机缘 +{demonic_gain:.0f}。" if demonic_gain else "")
            result = "killed"
            self._record_player_combat(game, target, resolution, result)
            return result, lead + f"你在追击阶段击杀了{victim['name']}。{fame_text}{spoils}" + (f" 杀戮炼化机缘 +{demonic_gain:.0f}。" if demonic_gain else "")
        result = "victory_escape"
        self._record_player_combat(game, target, resolution, result)
        return result, lead + f"你已击溃对方，但{victim['name']}仍在追击阶段摆脱封锁。"

    def _apply_cultivator_kill(self, game: GameState, victim: dict[str, Any], rng: random.Random) -> None:
        player = game.player
        config = WORLD_SYSTEMS["faction_conflict"]
        fame_config = WORLD_SYSTEMS["fame"]
        player.fame += float(fame_config["kill_gain_base"]) + int(victim["realm_index"]) * float(fame_config["kill_realm_scale"])
        if victim.get("notorious"):
            player.fame += max(40.0, float(victim.get("notoriety", 0)) * 0.55)
        npc_id = victim.get("npc_id")
        npc = self._find_npc(game, str(npc_id)) if npc_id else None
        if npc:
            npc.alive = False
            npc.death_reason = f"被{player.name}击杀夺宝"
            player.party = [entry for entry in player.party if entry.get("id") != npc.id]
            if player.dao_companion and player.dao_companion.get("id") == npc.id:
                player.dao_companion["alive"] = False
                player.dao_companion["death_reason"] = npc.death_reason
            treasure_id = npc.treasure_item_id
            if treasure_id in ITEM_CATALOG:
                add_item(player, treasure_id)
                npc.treasure_item_id = None
                npc.treasure_looted = True
        elif npc_id:
            cached = next((row for row in game.encounter_npc_cache if row.get("id") == npc_id), None)
            if cached:
                treasure_id = cached.get("npc", {}).get("treasure_item_id")
                if treasure_id in ITEM_CATALOG:
                    add_item(player, str(treasure_id))
                game.encounter_npc_cache = [row for row in game.encounter_npc_cache if row.get("id") != npc_id]
        faction_id = victim.get("faction_id")
        race = str(victim.get("race", "human"))
        wartime_opponent = self._is_wartime_opponent(game, str(faction_id) if faction_id else None, race)
        if faction_id:
            key = self._hostility_key("sect", str(faction_id))
            if faction_id == player.faction_id:
                self._handle_same_sect_kill(game, str(faction_id), str(npc_id) if npc_id else None)
            elif not wartime_opponent and self._kill_generates_hostility(game, "sect", str(faction_id), int(victim["realm_index"])):
                player.hostility[key] = player.hostility.get(key, 0) + float(config["kill_hostility_gain"])
            sect = game.sects.get(str(faction_id))
            if sect:
                self._check_sect_extinction(game, sect)
        if (
            self._world_supports(player.world, "races") and race != self._player_allegiance_race(player)
            and not wartime_opponent
            and self._kill_generates_hostility(game, "race", race, int(victim["realm_index"]))
        ):
            key = self._hostility_key("race", race)
            player.hostility[key] = player.hostility.get(key, 0) + float(config["kill_hostility_gain"])

    def _kill_generates_hostility(self, game: GameState, kind: str, target_id: str, victim_realm: int) -> bool:
        """Routine wartime and low-rank deaths do not mobilise an entire power."""
        player = game.player
        minimum = int(WORLD_SYSTEMS["faction_conflict"].get("kill_hostility_min_realm", {}).get(player.world, 0))
        if victim_realm < minimum:
            return False
        if kind == "race":
            relation = game.race_relations.get(race_pair(self._player_allegiance_race(player), target_id), {})
            return relation.get("status") != "war"
        if kind == "sect" and player.faction_id and target_id in game.sects:
            relation = game.sect_relations.get(race_pair(player.faction_id, target_id), {})
            return relation.get("status") != "war"
        return True

    def _is_wartime_opponent(self, game: GameState, faction_id: str | None, race_id: str) -> bool:
        player = game.player
        player_race = self._player_allegiance_race(player)
        for war in game.wars:
            if war.get("status") not in {"active", "peace_ready"}:
                continue
            self._ensure_war_shape(game, war)
            own_id = player.faction_id if war.get("kind") == "sect" else player_race
            target_id = faction_id if war.get("kind") == "sect" else race_id
            own_side = self._participant_side(war, own_id)
            target_side = self._participant_side(war, target_id)
            if own_side and target_side and own_side != target_side:
                return True
        if race_id != player_race and game.race_relations.get(race_pair(player_race, race_id), {}).get("status") == "war":
            return True
        return bool(
            faction_id and player.faction_id and faction_id != player.faction_id
            and game.sect_relations.get(race_pair(player.faction_id, faction_id), {}).get("status") == "war"
        )

    def _handle_same_sect_kill(self, game: GameState, faction_id: str, current_victim_id: str | None = None) -> None:
        player = game.player
        config = WORLD_SYSTEMS["faction_conflict"]
        control_realm = int(config["control_realm"].get(player.world, 4))
        living = [
            npc for npc in game.sects[faction_id].npcs
            if npc.world == player.world and (npc.alive or npc.id == current_victim_id)
        ]
        is_first = not living or (player.realm_index, player.layer) >= max((npc.realm_index, npc.layer) for npc in living)
        warning_key = f"same_sect_kill:{faction_id}"
        hostility_key = self._hostility_key("sect", faction_id)
        if player.realm_index < control_realm:
            player.faction_id = None
            player.hostility[hostility_key] = max(60.0, player.hostility.get(hostility_key, 0) + 45)
            summary = "你残杀同门，被当场逐出宗门并列入全宗通缉。"
            result = "expelled"
        elif not is_first and warning_key not in player.faction_warnings:
            player.faction_warnings.append(warning_key)
            summary = "宗门顺位第一的强者亲自降下法旨，警告你下不为例。"
            result = "warned"
            event = self.events_by_id.get("EVT_SECT_FIRST_WARNING_001")
            if event:
                game.pending_event = self._instantiate_event(event, game, random.Random(f"warning:{game.seed}:{player.age}"))
        elif not is_first:
            player.faction_id = None
            player.hostility[hostility_key] = max(90.0, player.hostility.get(hostility_key, 0) + 55)
            summary = "你无视顺位第一的警告再杀同门，宗门上下奉诛杀令追索你的性命。"
            result = "hunted"
        else:
            summary = "你位列宗门顺位第一，无人敢当面追究这次同门血案。"
            result = "suppressed"
        game.history.append(HistoryRecord(
            "SYS_SAME_SECT_KILL", 1, player.age, "同门血案", faction_id, result, summary,
            {"hostility": player.hostility.get(hostility_key, 0)}, ["system", "faction", "combat", "wanted"],
        ))

    @staticmethod
    def _race_alliance(game: GameState, world: str, first: str, second: str) -> dict[str, Any] | None:
        if first == second:
            return None
        dynamic = game.race_relations.get(race_pair(first, second))
        if "races" in WORLD_SYSTEMS.get("world_profiles", {}).get(world, {}).get("supports", []) and dynamic is not None:
            if dynamic.get("status") in {"alliance", "vassal"}:
                return {
                    "name": dynamic.get("name") or f"{RACE_DEFINITIONS[first]['name']}与{RACE_DEFINITIONS[second]['name']}盟约",
                    "kill_karma_multiplier": 3.0, "kill_karma_flat": 60,
                }
            return None
        for alliance in RACE_SYSTEMS.get("alliances", []):
            if alliance.get("world") == world and {first, second} <= set(alliance.get("members", [])):
                return alliance
        return None

    def _die(
        self, game: GameState, reason: str, event_id: str, *,
        offer_captive_possession: bool = False,
    ) -> None:
        if not game.player.alive:
            return
        from ..system.possession_system import is_possessed, leave_host_body
        if is_possessed(game.player):
            from ..rules import max_hp, max_mp
            host = leave_host_body(game.player)
            game.player.hp = max(1.0, min(game.player.hp, max_hp(game.player)))
            game.player.mp = max(0.0, min(game.player.mp, max_mp(game.player)))
            game.pending_event = None
            game.history.append(HistoryRecord(
                "SYS_POSSESSED_BODY_DESTROYED", 1, game.player.age, "宿身崩毁", None, "returned_to_ghost",
                f"{host.get('name', '宿主')}的肉身因“{reason}”毁灭；你的本魂脱出，夺舍次数不返还。",
                {"host_id": host.get("id"), "source_event": event_id}, ["system", "ghost", "possession"],
            ))
            return
        game.player.alive = False
        game.player.hp = 0
        game.player.death_reason = reason
        game.pending_event = None
        game.history.append(HistoryRecord(
            event_id, 1, game.player.age, "此生落幕", None, "dead", reason,
            {"alive": [True, False]}, ["system", "death"],
        ))
        if offer_captive_possession:
            self._prepare_post_battle_possession(game, event_id)

    @staticmethod
    def _snapshot(player: Player) -> dict[str, Any]:
        return {
            "hp": round(player.hp, 2), "mp": round(player.mp, 2),
            "opportunity": round(player.opportunity, 2), "karma": round(player.karma, 2),
            "sha_qi": player.sha_qi,
            "fame": round(player.fame, 2),
            "hostility": dict(player.hostility),
            "imprisonment": copy.deepcopy(player.imprisonment),
            "party": [entry.get("id") for entry in player.party],
            "heart_demon": round(player.heart_demon, 2),
            "active_breakthrough_aids": list(player.active_breakthrough_aids),
            "awaiting_minor_breakthrough": player.awaiting_minor_breakthrough,
            "technique_level": player.technique.level if player.technique else None,
            "main_technique": player.technique.id if player.technique else None,
            "support_technique": player.support_technique.id if player.support_technique else None,
            "combat_techniques": [entry.id for entry in player.combat_techniques],
            "spirit_root": player.spirit_root, "body_training": player.body_training,
            "body_progress": round(player.body_progress, 2),
            "body_technique": player.body_technique.id if player.body_technique else None,
            "divine_sense_level": divine_sense_level(player),
            "divine_sense_technique": player.divine_sense_technique.id if player.divine_sense_technique else None,
            "prisoners": [entry.get("id") for entry in player.prisoners],
            "puppets": [entry.get("id") for entry in player.puppets],
            "foreign_souls": [entry.get("id") for entry in player.foreign_souls],
            "devouring_breakthrough_bonus": round(player.devouring_breakthrough_bonus, 4),
            "awaiting_body_breakthrough": player.awaiting_body_breakthrough,
            "lifespan": player.lifespan,
            "faction_id": player.faction_id,
            "faction_contribution": player.faction_contribution,
            "faction_reward_preference": player.faction_reward_preference,
            "faction_hp_bonus": player.faction_hp_bonus,
            "faction_mp_bonus": player.faction_mp_bonus,
            "faction_combat_bonus": player.faction_combat_bonus,
            "master": player.master.get("id") if player.master else None,
            "dao_companion": player.dao_companion.get("id") if player.dao_companion else None,
            "disciples": [entry.get("id") for entry in player.disciples],
            "disciple_requests": [entry.get("id") for entry in player.disciple_requests],
            "story_flags": list(player.story_flags),
            "world": player.world,
            "spirit_realm_attempted": player.spirit_realm_attempted,
            "tribulation_count": player.tribulation_count,
            "next_tribulation_age": player.next_tribulation_age,
            "inventory": {item.id: item.quantity for item in player.inventory},
            "alive": player.alive,
        }

    @staticmethod
    def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        return {key: [before.get(key), value] for key, value in after.items() if before.get(key) != value}

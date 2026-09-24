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
            if player.path == "monster" and victim_path != "monster":
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
            if target.get("kill_karma", True):
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

    def _resolve_breakthroughs(self, game: GameState, rng: random.Random) -> None:
        player = game.player
        if player.cultivation_suppression:
            return
        if player.sealed_cultivation:
            player.opportunity = min(player.opportunity, opportunity_required(player))
            return
        if player.spirit_root == "none":
            player.opportunity = 0
            return
        safety = 0
        while player.alive and player.opportunity >= opportunity_required(player) and safety < 32:
            safety += 1
            required = opportunity_required(player)
            # 仙境没有层级与前中后期；后续升级规则尚未开放，不能误走旧突破链。
            if player.realm_index >= 9:
                player.opportunity = min(player.opportunity, required)
                player.awaiting_major_breakthrough = False
                player.awaiting_minor_breakthrough = False
                return
            if player.world == "spirit" and player.realm_index == 8 and player.layer >= REALMS[8].layers:
                player.awaiting_ascension = True
                player.awaiting_major_breakthrough = False
                player.opportunity = min(player.opportunity, required)
                if not any(entry.event_id == "SYS_CELESTIAL_ASCENSION_READY" for entry in game.history):
                    game.history.append(HistoryRecord(
                        "SYS_CELESTIAL_ASCENSION_READY", 1, player.age, "仙门可叩", None, "ready",
                        "大乘九层道果与机缘均已圆满，可以发动专属的九重渡劫飞升。",
                        {"awaiting_ascension":True}, ["system", "ascension", "celestial", "milestone"],
                    ))
                return
            if (
                player.path == "demonic" and player.world == "true_demon"
                and player.realm_index == 8 and player.layer >= REALMS[8].layers
            ):
                player.awaiting_ascension = True
                player.awaiting_major_breakthrough = False
                player.opportunity = min(player.opportunity, required)
                if not any(entry.event_id == "SYS_ASURA_ASCENSION_READY" for entry in game.history):
                    game.history.append(HistoryRecord(
                        "SYS_ASURA_ASCENSION_READY", 1, player.age, "修罗天关可叩", None, "ready",
                        "魔尊九层道果与机缘均已圆满，可以发动九重修罗天魔劫。",
                        {"awaiting_ascension":True}, ["system", "ascension", "asura", "demonic", "milestone"],
                    ))
                return
            if (
                player.path == "demonic" and player.world == "human"
                and player.realm_index == 5 and player.layer >= 3
            ):
                player.awaiting_ascension = True
                player.opportunity = min(player.opportunity, required)
                if not any(entry.event_id == "SYS_HUMAN_DEMONIC_LIMIT" for entry in game.history):
                    game.history.append(HistoryRecord(
                        "SYS_HUMAN_DEMONIC_LIMIT", 1, player.age, "魔界飞升瓶颈", None, "blocked",
                        "你已在人界修至化魔初期；下一步须飞升魔界。",
                        {"awaiting_ascension": True}, ["system", "realm_limit", "demonic", "milestone"],
                    ))
                return
            if (
                player.path == "demonic" and player.world == "demon"
                and player.realm_index == 5 and player.layer >= REALMS[5].layers
            ):
                player.awaiting_ascension = True
                player.opportunity = min(player.opportunity, required)
                if not any(entry.event_id == "SYS_DEMON_REALM_LIMIT" for entry in game.history):
                    game.history.append(HistoryRecord(
                        "SYS_DEMON_REALM_LIMIT", 1, player.age, "魔界绝巅", None, "blocked",
                        "你已修至化魔后期九层；炼魔境须先飞升真魔界。",
                        {"awaiting_ascension": True}, ["system", "realm_limit", "demonic", "milestone"],
                    ))
                return
            if player.world == "human" and player.realm_index == 5 and player.layer >= 3:
                player.opportunity = min(player.opportunity, required)
                if not player.awaiting_spirit_realm_crossing:
                    player.awaiting_spirit_realm_crossing = True
                    game.history.append(HistoryRecord(
                        "SYS_HUMAN_REALM_LIMIT", 1, player.age, "人界绝巅", None, "blocked",
                        "人界法则不足以支撑化神中期。你只能停留在化神初期，等待未来寻得偷渡灵界之法。",
                        {"awaiting_spirit_realm_crossing": True}, ["system", "realm_limit", "milestone"],
                    ))
                return
            if player.realm_index == len(REALMS) - 1 and player.layer == REALMS[-1].layers:
                player.awaiting_ascension = True
                player.opportunity = min(player.opportunity, required)
                return
            old_realm = realm(player)
            old_label = public_player(player)["realm_name"]
            if player.layer >= old_realm.layers:
                player.opportunity = min(player.opportunity, required)
                if not player.awaiting_major_breakthrough:
                    player.awaiting_major_breakthrough = True
                    game.history.append(HistoryRecord(
                        "SYS_BOTTLENECK_READY", 1, player.age, "大境界瓶颈", None, "ready",
                        f"{old_label}机缘已经圆满。你可以继续准备，并在合适时主动突破瓶颈。",
                        {"awaiting_major_breakthrough": True}, ["system", "breakthrough", "major"],
                    ))
                return
            if player.layer in self._manual_minor_layers(player):
                player.opportunity = min(player.opportunity, required)
                if not player.awaiting_minor_breakthrough:
                    player.awaiting_minor_breakthrough = True
                    target_name = self._minor_layer_target(player)
                    game.history.append(HistoryRecord(
                        "SYS_MINOR_BOTTLENECK_READY", 1, player.age, "小境界瓶颈", None, "ready",
                        f"{old_label}机缘已经圆满。你可以服用对应丹药并手动冲击{target_name}。",
                        {"awaiting_minor_breakthrough": True},
                        ["system", "breakthrough", "minor"],
                    ))
                return
            # 练气层级仍沿用自动检定；筑基以后所有层级均停留等待手动冲击。
            chance = self._breakthrough_chance(player, major=False, allow_aids=False)
            if rng.random() >= chance["final"]:
                player.opportunity = required * float(WORLD_SYSTEMS["breakthrough"]["minor_failure_retention"])
                gain = self._sage_scaled_gain(
                    player, float(WORLD_SYSTEMS["breakthrough"]["minor_failure_heart_demon"]),
                    "heart_demon_gain_reduction",
                )
                player.heart_demon += gain
                game.history.append(HistoryRecord(
                    "SYS_MINOR_BREAKTHROUGH_FAILED", 1, player.age, "小境界冲关失利", None, "failed",
                    f"从{old_label}继续破境失败（成功率 {chance['final']:.1%}）；心魔 +{gain:g}。",
                    {"chance": chance, "heart_demon_gain": gain}, ["system", "breakthrough", "minor", "negative"],
                ))
                return
            player.opportunity = max(0.0, player.opportunity - required)
            if player.realm_index >= 6:
                self._start_breakthrough_trial(
                    game, "traditional", player.realm_index, player.realm_index, old_label,
                    major=False, rng=rng,
                )
                return
            self._complete_minor_breakthrough(game, rng, old_label)

    @staticmethod
    def _manual_minor_layers(player: Player) -> set[int]:
        if player.realm_index < 2:
            return set()
        if player.world == "human" and player.realm_index == 5:
            return set()
        return set(range(1, realm(player).layers))

    def _manual_breakthrough_kind(self, player: Player) -> str | None:
        monster_upper_evolution = bool(
            player.path == "monster" and bloodline_content_available()
            and WORLD_SYSTEMS.get("world_profiles", {}).get("nether", {}).get("enabled")
            and player.layer >= realm(player).layers
            and (
                (player.realm_index == 8 and player.world in {"monster_realm", "phantom_underworld"})
                or (9 <= player.realm_index < len(REALMS) - 1 and player.world == "nether")
            )
        )
        if monster_upper_evolution:
            return "major"
        if player.realm_index >= 9 or (player.realm_index == 8 and player.layer >= REALMS[8].layers):
            return None
        if player.layer >= realm(player).layers and player.realm_index < len(REALMS) - 1:
            return "major"
        if player.layer in self._manual_minor_layers(player):
            return "minor"
        return None

    @staticmethod
    def _minor_stage_target(player: Player) -> str:
        stage = "中期" if player.layer == 3 else "后期"
        return f"{realm(player).name}{stage}"

    def _minor_layer_target(self, player: Player) -> str:
        shell = SectNpc("target", "", "", player.realm_index, player.layer + 1, 0, 1, path=player.path)
        return self._npc_realm_name(shell)

    @staticmethod
    def _minor_pity_key(player: Player) -> str:
        return f"minor:{player.realm_index}:{player.layer}"

    def _minor_pity_bonus(self, player: Player) -> float:
        config = WORLD_SYSTEMS["breakthrough"].get("minor_pity", {})
        if player.layer not in {int(layer) for layer in config.get("eligible_source_layers", [])}:
            return 0.0
        failures = int(player.breakthrough_pity.get(self._minor_pity_key(player), 0))
        return min(float(config.get("max_bonus", 0)), failures * float(config.get("bonus_per_failure", 0)))

    def _record_minor_pity_failure(self, player: Player) -> float:
        if self._minor_pity_bonus(player) == 0 and player.layer not in set(
            WORLD_SYSTEMS["breakthrough"].get("minor_pity", {}).get("eligible_source_layers", [])
        ):
            return 0.0
        key = self._minor_pity_key(player)
        player.breakthrough_pity[key] = int(player.breakthrough_pity.get(key, 0)) + 1
        return self._minor_pity_bonus(player)

    def _clear_minor_pity(self, player: Player) -> None:
        player.breakthrough_pity.pop(self._minor_pity_key(player), None)

    @staticmethod
    def _major_breakthrough_requirement(player: Player) -> dict[str, Any]:
        if player.path == "demonic" and player.world == "demon" and player.realm_index == 5:
            return {
                "met": False,
                "reason": "炼魔境必须先飞升真魔界。",
                "missing_affinities": [],
            }
        if player.realm_index == 5:
            five = {"metal", "wood", "water", "fire", "earth"}
            owned = set(root_elements(player.spirit_root)) | set(player.additional_roots)
            missing = [TECHNIQUE_ELEMENT_NAMES[element] for element in ("metal", "wood", "water", "fire", "earth") if element not in owned]
            return {
                "met": not missing,
                "reason": "突破炼虚必须具备完整五行灵根；当前尚缺" + "、".join(missing) + "灵根。" if missing else "五行灵根齐备。",
                "missing_affinities": missing,
            }
        return {"met": True, "reason": "机缘圆满后可主动突破。", "missing_affinities": []}

    @staticmethod
    def _root_probability_group(player: Player) -> str:
        if player.spirit_root.startswith("acquired_"):
            return "acquired"
        tier = str(root_definition(player.spirit_root).get("tier", ""))
        return {
            "伪灵根": "pseudo", "天灵根": "heavenly", "极品灵根": "supreme",
            "变异灵根": "mutated", "法则灵根": "law", "异世界灵根": "otherworld",
            "后天灵根": "acquired", "后天变异灵根": "acquired",
        }.get(tier, "acquired")

    def _breakthrough_chance(self, player: Player, major: bool, allow_aids: bool = True) -> dict[str, float]:
        config = WORLD_SYSTEMS["breakthrough"]
        source = player.realm_index
        if major and source == 0:
            base = 1.0
        elif major:
            table = config["major_base"][str(source)]
            base = float(table.get(self._root_probability_group(player), table.get("default", 0.01)))
        else:
            base = 1.0 if source == 1 else float(config["minor_base"].get(str(source), 1.0))
        dependent_bonus = 0.0
        if player.concubine_status:
            owner_rank = (
                int(player.concubine_status.get("owner_realm_index", 0)),
                int(player.concubine_status.get("owner_layer", 1)),
            )
            if (player.realm_index, player.layer) < owner_rank:
                dependent_bonus = 0.02
        concubine_base_bonus = min(0.02, player.concubine_breakthrough_bonus) + dependent_bonus
        base += concubine_base_bonus
        scope = f"{'major' if major else 'minor'}:{source}"
        aid_bonus = sum(
            float(ITEM_CATALOG[item_id].breakthrough_bonus)
            for item_id in player.active_breakthrough_aids
            if item_id in ITEM_CATALOG and ITEM_CATALOG[item_id].breakthrough_scope == scope
        ) if (
            allow_aids
            and player.path != "demonic"
            and (
                not ghost_cultivation_active(player)
                or (
                    player.realm_index >= 4
                    and (not major or player.realm_index >= 6)
                )
            )
        ) else 0.0
        devouring_bonus = player.devouring_breakthrough_bonus if player.path == "demonic" else 0.0
        companion_bonus = (
            float(WORLD_SYSTEMS["relationship"]["companion_breakthrough_bonus"])
            if self._joint_companion_eligible(player) else 0.0
        )
        artifact_bonus = sum(
            float(item.passive_breakthrough_bonus) * item.quantity for item in player.inventory
            if item.passive_breakthrough_bonus > 0
            and item.passive_breakthrough_max_realm is not None
            and source <= int(item.passive_breakthrough_max_realm)
        )
        artifact_bonus += crafted_artifact_bonuses(player)["breakthrough_bonus"]
        penalty = min(
            float(config["heart_demon_penalty_cap"]),
            player.heart_demon * float(config["heart_demon_penalty_per_point"]),
        )
        pity_bonus = 0.0 if major else self._minor_pity_bonus(player)
        body_training_bonus = (
            player.body_training // 20
            * float(WORLD_SYSTEMS["body_cultivation"]["cultivation_breakthrough_bonus_per_20_layers"])
        )
        optimal = config.get("optimal_state", {})
        optimal_state_bonus = (
            float(optimal.get("bonus", 0))
            if player.hp >= max_hp(player) * float(optimal.get("hp_ratio", 0.8))
            and player.mp >= max_mp(player) * float(optimal.get("mp_ratio", 0.8))
            else 0.0
        )
        reincarnation_bonus = reincarnation_breakthrough_bonus(player, source)
        sage_bonus = max(-0.08, min(0.05, float(player.sage_effects.get("breakthrough_bonus", 0.0))))
        # 轮回经验本身不封顶，但所有流派的最终有效突破率都必须保留
        # 至少 2% 的失败风险；扩展配置也不能绕过这一全局硬上限。
        configured_cap = float(
            WORLD_SYSTEMS.get("ghost_cultivation", {}).get("reincarnation_final_probability_cap", 0.98)
        ) if ghost_cultivation_active(player) else 0.98
        final_cap = min(0.98, max(0.005, configured_cap))
        final = max(0.005, min(
            final_cap, base + aid_bonus + companion_bonus + artifact_bonus + pity_bonus
            + body_training_bonus + optimal_state_bonus + devouring_bonus + reincarnation_bonus + sage_bonus - penalty,
        ))
        return {
            "base": base, "aid_bonus": aid_bonus, "companion_bonus": companion_bonus,
            "concubine_base_bonus": concubine_base_bonus,
            "artifact_bonus": artifact_bonus, "pity_bonus": pity_bonus,
            "devouring_bonus": devouring_bonus,
            "reincarnation_bonus": reincarnation_bonus,
            "sage_bonus": sage_bonus,
            "body_training_bonus": body_training_bonus, "optimal_state_bonus": optimal_state_bonus,
            "heart_demon_penalty": penalty, "final": final,
        }

    @staticmethod
    def _joint_companion_eligible(player: Player) -> dict[str, Any] | None:
        companion = player.dao_companion
        if not companion or not companion.get("alive", True) or companion.get("world", player.world) != player.world:
            return None
        if not player.technique or companion.get("main_technique_id") != player.technique.id:
            return None
        if int(companion.get("realm_index", -1)) != player.realm_index:
            return None
        return companion

    def _complete_joint_companion_breakthrough(self, game: GameState, rng: random.Random) -> None:
        joint = game.player.joint_companion_breakthrough
        companion = game.player.dao_companion
        if not joint:
            return
        game.player.joint_companion_breakthrough = None
        if not companion or companion.get("id") != joint.get("id") or not companion.get("alive", True):
            return
        old_label = str(companion.get("realm_name", "原境界"))
        companion["realm_index"] = game.player.realm_index
        companion["layer"] = game.player.layer
        shell = SectNpc("joint", companion["name"], "", game.player.realm_index, game.player.layer, 0, 1)
        companion["realm_name"] = self._npc_realm_name(shell)
        companion["cultivation_progress"] = 0.0
        lifespan_gain = 0
        if bool(joint.get("major")):
            span = REALMS[game.player.realm_index].lifespan
            if span is None:
                companion["lifespan"] = None
            else:
                old_lifespan = int(companion.get("lifespan") or 0)
                rolled = rng.randint(*span) * self._npc_lifespan_multiplier(str(companion.get("path", "dao")))
                companion["lifespan"] = max(old_lifespan, rolled, int(companion.get("age", 0)) + 1)
                lifespan_gain = max(0, int(companion["lifespan"]) - old_lifespan)
        elif game.player.layer in {4, 7} and companion.get("lifespan") is not None:
            stage = "middle" if game.player.layer == 4 else "late"
            stage_range = WORLD_SYSTEMS.get("stage_lifespan_bonus", {}).get(REALMS[game.player.realm_index].id, {}).get(stage)
            if stage_range:
                lifespan_gain = rng.randint(*stage_range) * self._npc_lifespan_multiplier(str(companion.get("path", "dao")))
                companion["lifespan"] = int(companion["lifespan"]) + lifespan_gain
        if game.player.realm_index >= 6 and companion.get("next_tribulation_age") is None:
            thunder = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
            companion["next_tribulation_age"] = int(companion.get("age", game.player.age)) + int(thunder["interval_years"])
            companion["tribulation_count"] = int(companion.get("tribulation_count", 0))
            companion["tribulation_power"] = float(thunder["base_power"]) * float(thunder["power_multiplier"]) ** int(companion["tribulation_count"])
        npc = self._find_npc(game, str(companion.get("id", "")))
        if npc:
            npc.realm_index = game.player.realm_index
            npc.layer = game.player.layer
            npc.cultivation_progress = 0.0
            npc.lifespan = companion.get("lifespan")
            npc.next_tribulation_age = companion.get("next_tribulation_age")
            npc.tribulation_count = int(companion.get("tribulation_count", 0))
            npc.tribulation_power = companion.get("tribulation_power")
        game.history.append(HistoryRecord(
            "SYS_COMPANION_JOINT_BREAKTHROUGH", 1, game.player.age, "同心破境", None, "success",
            f"{companion['name']}与你运转同一主修功法，一同从{old_label}突破至{companion['realm_name']}。"
            + (" 寿元自此无尽。" if companion.get("lifespan") is None else f" 寿元增长 {lifespan_gain} 年。" if lifespan_gain else ""),
            {"companion_id": companion["id"], "realm": [old_label, companion["realm_name"]]},
            ["system", "relationship", "dao_companion", "breakthrough"],
        ))

    @staticmethod
    def _consume_breakthrough_aids(player: Player, scope: str) -> None:
        player.active_breakthrough_aids = [
            item_id for item_id in player.active_breakthrough_aids
            if ITEM_CATALOG.get(item_id) and ITEM_CATALOG[item_id].breakthrough_scope != scope
        ]

    def _start_breakthrough_trial(
        self, game: GameState, kind: str, source: int, target: int, old_label: str,
        major: bool, rng: random.Random,
    ) -> None:
        event_ids = {
            "traditional": [
                "EVT_BREAKTHROUGH_TRADITIONAL_001", "EVT_BREAKTHROUGH_TRADITIONAL_002",
                "EVT_BREAKTHROUGH_TRADITIONAL_003",
            ],
            "heavenly": [
                "EVT_BREAKTHROUGH_HEAVENLY_001", "EVT_BREAKTHROUGH_HEAVENLY_002",
                "EVT_BREAKTHROUGH_HEAVENLY_003", "EVT_BREAKTHROUGH_HEAVENLY_004",
                "EVT_BREAKTHROUGH_HEAVENLY_005",
            ],
            "heavenly_demon": ["EVT_HEAVENLY_DEMON_TRIBULATION_001"],
        }[kind]
        game.active_trial = {
            "kind": kind, "source_realm": source, "target_realm": target,
            "target_layer": 1 if major else game.player.layer + 1,
            "major": major, "old_label": old_label, "step_index": 0,
            "event_ids": event_ids,
            "lethal": bool(source == 3 or source >= 6),
        }
        if kind == "heavenly_demon":
            game.active_trial.update(base_rounds_completed=0, total_battles=0, soul_battles=0)
            self._queue_heavenly_demon_battle(game, rng, soul=None)
        else:
            game.pending_event = self._instantiate_event(self.events_by_id[event_ids[0]], game, rng)

    def _queue_heavenly_demon_battle(
        self, game: GameState, rng: random.Random, soul: dict[str, Any] | None,
    ) -> None:
        trial = game.active_trial or {}
        config = WORLD_SYSTEMS["demonic_cultivation"]["heavenly_demon_tribulation"]
        if soul is None:
            round_index = int(trial.get("base_rounds_completed", 0))
            ratios = list(config["outer_demon_power_ratios"])
            ratio = float(ratios[min(round_index, len(ratios) - 1)])
            target_power = expected_combat_power(int(trial["target_realm"]), 1) * ratio
            event_id = "EVT_HEAVENLY_DEMON_TRIBULATION_001"
            label = f"第 {round_index + 1}/{int(config['base_rounds'])} 重域外天魔"
            runtime = {"battle_kind":"outer_demon", "target_name":label, "target_power":round(target_power, 1)}
        else:
            realm_index = int(soul.get("realm_index", 1))
            inherited_power = float(soul.get("combat_power", 0))
            if inherited_power <= 0:
                inherited_power = expected_combat_power(realm_index, REALMS[realm_index].layers)
            target_power = inherited_power * 0.50
            event_id = "EVT_HEAVENLY_DEMON_SOUL_001"
            label = f"{soul.get('name', '无名元神')}的反噬元神"
            runtime = {
                "battle_kind":"foreign_soul", "target_name":label,
                "target_power":round(target_power, 1), "soul_id":soul.get("id"),
            }
        event = self._instantiate_event(self.events_by_id[event_id], game, rng)
        event["runtime"] = runtime
        trial["battle_runtime"] = copy.deepcopy(runtime)
        event["body"] += f" 当前对手：{label}，战力约 {target_power:.0f}。"
        game.pending_event = event

    def _resolve_heavenly_demon_battle(
        self, game: GameState, step: str, rng: random.Random,
    ) -> tuple[str, str]:
        player = game.player
        trial = game.active_trial
        if not trial:
            raise ValueError("当前没有进行中的天魔劫")
        runtime = dict(trial.get("battle_runtime", {}))
        target_power = max(1.0, float(runtime.get("target_power", 1)))
        own_power = self._player_battle_power(game)
        ratio = own_power / target_power
        target_name = str(runtime.get("target_name", "域外天魔"))
        hp_before, mp_before = player.hp, player.mp
        combat_result, combat_summary = self._combat(game, {
            **runtime,
            "target_name": target_name,
            "target_power": target_power,
            "target_realm_index": int(trial.get("target_realm", player.realm_index)),
            "target_layer": 1,
            "combat_type": "trial",
            "path": "demonic",
            "action": "repel",
            "enemy_objective": "kill",
            "max_rounds": 5,
        }, False, rng)
        won = combat_result == "victory"
        if not won:
            player.joint_companion_breakthrough = None
            game.active_trial = None
            self._die(game, f"天魔劫中不敌{target_name}，肉身与元神尽被魔影吞没", "SYS_HEAVENLY_DEMON_TRIBULATION_FAILED")
            if game.last_combat_report:
                game.last_combat_report["result"] = "dead"
                game.last_combat_report["result_grade"] = "溃败"
            return "dead", f"{combat_summary} 天魔劫无法撤退，你在交战失败后陨落。"

        config = WORLD_SYSTEMS["demonic_cultivation"]["heavenly_demon_tribulation"]
        hp_loss = max(0.0, hp_before - player.hp)
        mp_loss = max(0.0, mp_before - player.mp)
        gain = float(REALMS[int(trial["target_realm"])].opportunity_base) * float(config["victory_opportunity_ratio"])
        self._add_opportunity(player, gain)
        trial["total_battles"] = int(trial.get("total_battles", 0)) + 1
        if runtime.get("battle_kind") == "foreign_soul" or step == "heavenly_demon_soul":
            trial["soul_battles"] = int(trial.get("soul_battles", 0)) + 1
        else:
            trial["base_rounds_completed"] = int(trial.get("base_rounds_completed", 0)) + 1

        souls = list(player.foreign_souls)
        if souls and rng.random() < float(config["soul_lure_chance"]):
            soul = rng.choice(souls)
            self._queue_heavenly_demon_battle(game, rng, soul=soul)
            return "trial_step_success", (
                f"{combat_summary} 天魔劫阶段胜利（初始综合评分比 {ratio:.2f}），"
                f"机缘 +{gain:.0f}；域外天魔又勾起了{soul.get('name', '一道元神')}的反噬。"
            )
        if int(trial.get("base_rounds_completed", 0)) < int(config["base_rounds"]):
            self._queue_heavenly_demon_battle(game, rng, soul=None)
            return "trial_step_success", (
                f"{combat_summary} 天魔劫阶段胜利（初始综合评分比 {ratio:.2f}），"
                f"机缘 +{gain:.0f}；下一重域外天魔已经显形。"
            )

        old_label = str(trial.get("old_label", public_player(player)["realm_name"]))
        total_battles = int(trial.get("total_battles", 0))
        soul_battles = int(trial.get("soul_battles", 0))
        self._complete_major_breakthrough(game, rng, old_label)
        game.active_trial = None
        return "trial_completed", (
            f"你击溃最后一重魔影，HP -{hp_loss:.0f}、MP -{mp_loss:.0f}，机缘 +{gain:.0f}；"
            f"本次天魔劫共交战 {total_battles} 次，其中元神反噬 {soul_battles} 次。"
        )

    def _complete_major_breakthrough(self, game: GameState, rng: random.Random, old_label: str) -> None:
        player = game.player
        player.awaiting_major_breakthrough = False
        player.awaiting_minor_breakthrough = False
        player.heart_demon = max(0.0, player.heart_demon - 5)
        player.realm_index += 1
        player.layer = 1
        grant_intrinsic_progression_if_new_highwater(player)
        grant_wangsheng(player)
        self._raise_divine_sense_one_level(player)
        if player.path == "demonic" and player.realm_index in {4, 7}:
            technique_id = "TECH_HEAVENLY_DEMON_SENSE" if player.realm_index == 4 else "TECH_MYRIAD_SOUL_SENSE"
            unlocked = copy.deepcopy(TECHNIQUE_CATALOG[technique_id])
            learn_technique(player, unlocked)
            assign_technique(player, unlocked, "divine_sense")
        rolled_lifespan = roll_lifespan(player, rng)
        if ghost_cultivation_active(player):
            player.lifespan = None
        elif rolled_lifespan is None:
            player.lifespan = None
        elif player.lifespan is None:
            player.lifespan = rolled_lifespan
        else:
            player.lifespan = max(player.lifespan, rolled_lifespan)
        if realm(player).id == "void" and player.next_tribulation_age is None:
            thunder = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
            player.next_tribulation_age = player.age + int(thunder["interval_years"])
            player.tribulation_power = float(thunder["base_power"]) * float(thunder["power_multiplier"]) ** player.tribulation_count
        player.hp = max_hp(player)
        player.mp = max_mp(player)
        target_label = public_player(player)["realm_name"]
        game.history.append(HistoryRecord(
            "SYS_MAJOR_BREAKTHROUGH", 1, player.age, "突破瓶颈", None, "success",
            f"你通过全部关隘，从{old_label}突破至{target_label}。",
            {"realm": [old_label, target_label]}, ["system", "breakthrough", "major"],
        ))
        general_trait = grant_random_general_monster_trait(
            player, rng, bloodline_available=bloodline_content_available(),
        )
        if general_trait:
            game.history.append(HistoryRecord(
                "SYS_MONSTER_GENERAL_TRAIT", 1, player.age, "凡妖蜕性",
                general_trait["id"], "acquired",
                f"血脉谱系未启用，你在大境界蜕变中获得通用特质【{general_trait['name']}】：{general_trait['description']}",
                {"trait_id": general_trait["id"], "realm_index": player.realm_index},
                ["system", "monster", "trait", "breakthrough", "major", "milestone"],
            ))
        self._complete_joint_companion_breakthrough(game, rng)

    def _complete_minor_breakthrough(self, game: GameState, rng: random.Random, old_label: str) -> None:
        player = game.player
        player.awaiting_minor_breakthrough = False
        player.heart_demon = max(0.0, player.heart_demon - 1)
        old_realm = realm(player)
        player.layer += 1
        grant_intrinsic_progression_if_new_highwater(player)
        grant_wangsheng(player)
        self._raise_divine_sense_one_level(player)
        lifespan_gain = 0
        stage = "middle" if player.layer == 4 else "late" if player.layer == 7 else None
        stage_ranges = WORLD_SYSTEMS.get("stage_lifespan_bonus", {}).get(old_realm.id, {})
        if stage and player.lifespan is not None and stage in stage_ranges:
            lifespan_gain = rng.randint(*stage_ranges[stage])
            if player.path == "monster":
                lifespan_gain *= int(WORLD_SYSTEMS.get("monster_cultivation", {}).get("lifespan_multiplier", 3))
            player.lifespan += lifespan_gain
        player.hp = max_hp(player)
        player.mp = max_mp(player)
        game.history.append(HistoryRecord(
            "SYS_BREAKTHROUGH", 1, player.age, "破境", None, "success",
            f"冲关成功，从{old_label}突破至{public_player(player)['realm_name']}。"
            + (f"境界阶段蜕变令寿元增长 {lifespan_gain} 年。" if lifespan_gain else ""),
            {"realm": [old_label, public_player(player)["realm_name"]], **({"lifespan_gain": lifespan_gain} if lifespan_gain else {})},
            ["system", "breakthrough", "minor"],
        ))
        self._complete_joint_companion_breakthrough(game, rng)

    def _resolve_trial_step(self, game: GameState, step: str, rng: random.Random) -> tuple[str, str]:
        player = game.player
        trial = game.active_trial
        if not trial:
            raise ValueError("当前没有进行中的突破或雷劫")
        kind = str(trial["kind"])
        if kind == "heavenly_demon":
            return self._resolve_heavenly_demon_battle(game, step, rng)
        if kind == "celestial_ascension":
            return self._resolve_celestial_ascension_step(game, step, rng)
        if kind == "asura_ascension":
            return self._resolve_asura_ascension_step(game, step, rng)
        passed = False
        detail = ""
        if kind == "traditional":
            config = WORLD_SYSTEMS["breakthrough"]["traditional"]
            target = str(trial["target_realm"])
            if step == "vitality":
                hp_ratio, mp_ratio = player.hp / max_hp(player), player.mp / max_mp(player)
                passed = hp_ratio >= float(config["hp_ratio"]) and mp_ratio >= float(config["mp_ratio"])
                detail = f"HP {hp_ratio:.0%}/{float(config['hp_ratio']):.0%}，MP {mp_ratio:.0%}/{float(config['mp_ratio']):.0%}"
            elif step == "karma":
                limit = float(config["karma_limits"].get(target, 60))
                actual = effective_karma(player)
                passed, detail = actual <= limit, f"有效因果 {actual:.1f}/{limit:.0f}"
            elif step == "heart_demon":
                limit = float(config["heart_demon_limits"].get(target, 25))
                passed, detail = player.heart_demon <= limit, f"心魔 {player.heart_demon:.1f}/{limit:.0f}"
            drain_hp, drain_mp = config["drain_hp"], config["drain_mp"]
        elif kind == "heavenly":
            config = WORLD_SYSTEMS["breakthrough"]["heavenly"]
            if step == "heaven_vitality":
                ratio = (player.hp + player.mp) / (max_hp(player) + max_mp(player))
                passed, detail = ratio >= float(config["vitality_ratio"]), f"HP+MP 总量 {ratio:.0%}/{float(config['vitality_ratio']):.0%}"
            elif step == "heaven_combat":
                threshold = expected_combat_power(int(trial["target_realm"]), 1) * float(config["combat_ratio"])
                actual = self._player_intrinsic_combat_power(player)
                passed, detail = actual >= threshold, f"战斗力 {actual:.0f}/{threshold:.0f}"
            elif step == "heaven_karma":
                actual, limit = effective_karma(player), float(config["karma_limit"])
                passed, detail = actual <= limit, f"有效因果 {actual:.1f}/{limit:.0f}"
            elif step == "heaven_sha":
                active_path = player.technique.path if player.technique else player.path
                if active_path in {"demonic", "ghost"}:
                    passed, detail = True, "魔修或鬼修以煞入道，本关跳过"
                else:
                    limit = float(config["sha_qi_limit"])
                    passed, detail = player.sha_qi <= limit, f"煞气 {player.sha_qi}/{limit:.0f}"
            elif step == "heaven_heart":
                limit = float(config["heart_demon_limit"])
                passed, detail = player.heart_demon <= limit, f"心魔 {player.heart_demon:.1f}/{limit:.0f}"
            drain_hp, drain_mp = config["drain_hp"], config["drain_mp"]
        else:
            config = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
            strike_index = int(step.rsplit("_", 1)[1]) - 1
            multiplier = float(config["strike_multipliers"][strike_index])
            power = float(trial["power"]) * multiplier
            hp_need = max(max_hp(player) * float(config["hp_ratio"]), power * float(config["power_hp_scale"]))
            mp_need = max(max_mp(player) * float(config["mp_ratio"]), power * float(config["power_mp_scale"]))
            passed = player.hp >= hp_need and player.mp >= mp_need
            detail = f"HP {player.hp:.0f}/{hp_need:.0f}，MP {player.mp:.0f}/{mp_need:.0f}，雷威 {power:.0f}"
            drain_hp, drain_mp = config["drain_hp"], config["drain_mp"]

        if not passed:
            gain = self._sage_scaled_gain(
                player, float(WORLD_SYSTEMS["breakthrough"]["trial_failure_heart_demon"]),
                "heart_demon_gain_reduction",
            )
            player.heart_demon += gain
            player.joint_companion_breakthrough = None
            lethal = bool(trial.get("lethal"))
            game.active_trial = None
            if kind == "periodic_thunder":
                player.next_thunder_damage_reduction = 0.0
            if lethal:
                self._die(game, f"未能渡过{self.events_by_id[game.pending_event['id']]['title'] if game.pending_event else '劫难'}", "SYS_TRIAL_FAILED")
                return "dead", f"判定失败（{detail}），心魔 +{gain:g}，你在劫中陨落。"
            return "breakthrough_failed", f"判定失败（{detail}），你保住性命但冲关中止，心魔 +{gain:g}。"

        reduction = self._tribulation_damage_reduction(player, kind) if kind in {"heavenly", "periodic_thunder"} else 0.0
        damage_multiplier = (
            float(WORLD_SYSTEMS["demonic_cultivation"].get("periodic_thunder_damage_multiplier", 1.0))
            if kind == "periodic_thunder" and player.path == "demonic" else 1.0
        )
        hp_loss = max_hp(player) * rng.uniform(*drain_hp) * (1 - reduction) * damage_multiplier
        mp_loss = max_mp(player) * rng.uniform(*drain_mp) * (1 - reduction) * damage_multiplier
        player.hp = max(1.0, player.hp - hp_loss)
        player.mp = max(0.0, player.mp - mp_loss)
        trial["step_index"] = int(trial["step_index"]) + 1
        event_ids = list(trial["event_ids"])
        if trial["step_index"] < len(event_ids):
            next_event = self.events_by_id[event_ids[trial["step_index"]]]
            game.pending_event = self._instantiate_event(next_event, game, rng)
            reduction_text = f"（法宝减伤 {reduction:.0%}）" if reduction else ""
            if damage_multiplier > 1:
                reduction_text += "（魔修承受雷劫伤害 +20%）"
            return "trial_step_success", f"判定通过（{detail}）；劫力消耗 HP {hp_loss:.0f}、MP {mp_loss:.0f}{reduction_text}。"

        old_label = str(trial.get("old_label", public_player(player)["realm_name"]))
        if kind == "periodic_thunder":
            thunder = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
            player.tribulation_count += 1
            player.next_tribulation_age = player.age + int(thunder["interval_years"])
            player.tribulation_power = float(
                trial.get("uncapped_base_power", trial.get("base_power", trial["power"]))
            ) * float(thunder["power_multiplier"])
            player.next_thunder_damage_reduction = 0.0
            game.history.append(HistoryRecord(
                "SYS_PERIODIC_TRIBULATION", 1, player.age, "三千年雷劫", None, "success",
                f"你连续承受三道真雷，渡过第 {player.tribulation_count} 次雷劫；下一劫威力升至 {player.tribulation_power:.0f}。",
                {"tribulation_count": player.tribulation_count, "next_power": player.tribulation_power}, ["system", "tribulation"],
            ))
        elif bool(trial["major"]):
            self._complete_major_breakthrough(game, rng, old_label)
        else:
            self._complete_minor_breakthrough(game, rng, old_label)
        game.active_trial = None
        reduction_text = f"（法宝减伤 {reduction:.0%}）" if reduction else ""
        if damage_multiplier > 1:
            reduction_text += "（魔修承受雷劫伤害 +20%）"
        return "trial_completed", f"最后一道判定通过（{detail}）；劫力消耗 HP {hp_loss:.0f}、MP {mp_loss:.0f}{reduction_text}。"

    def _resolve_celestial_ascension_step(
        self, game: GameState, step: str, rng: random.Random,
    ) -> tuple[str, str]:
        player = game.player
        trial = game.active_trial
        if not trial:
            raise ValueError("当前没有进行中的飞升劫")
        hp_ratio = player.hp / max(1.0, max_hp(player))
        mp_ratio = player.mp / max(1.0, max_mp(player))
        thunder_index = {
            "ascension_thunder_1":0, "ascension_thunder_2":1, "ascension_thunder_3":2,
        }.get(step)
        reduction = 0.0
        if step == "ascension_body":
            passed, detail, drain_hp, drain_mp = hp_ratio >= 0.75, f"HP {hp_ratio:.0%}/75%", (0.03, 0.06), (0.02, 0.04)
        elif step == "ascension_space":
            passed, detail, drain_hp, drain_mp = mp_ratio >= 0.68, f"MP {mp_ratio:.0%}/68%", (0.03, 0.05), (0.05, 0.08)
        elif thunder_index is not None:
            hp_need = (0.58, 0.48, 0.38)[thunder_index]
            mp_need = (0.52, 0.42, 0.32)[thunder_index]
            passed = hp_ratio >= hp_need and mp_ratio >= mp_need
            detail = f"HP {hp_ratio:.0%}/{hp_need:.0%}，MP {mp_ratio:.0%}/{mp_need:.0%}"
            drain_hp = ((0.08, 0.13), (0.10, 0.16), (0.12, 0.19))[thunder_index]
            drain_mp = ((0.07, 0.11), (0.08, 0.13), (0.10, 0.15))[thunder_index]
            reduction = self._tribulation_damage_reduction(player, "celestial_ascension")
        elif step == "ascension_karma":
            actual = effective_karma(player)
            passed, detail, drain_hp, drain_mp = actual <= 120, f"有效因果 {actual:.1f}/120", (0.02, 0.04), (0.03, 0.05)
        elif step == "ascension_demon":
            threshold = expected_combat_power(8, 9) * 0.75
            actual = self._player_intrinsic_combat_power(player)
            passed = player.heart_demon <= 50 and actual >= threshold
            detail = f"心魔 {player.heart_demon:.1f}/50，战斗力 {actual:.0f}/{threshold:.0f}"
            drain_hp, drain_mp = (0.05, 0.09), (0.07, 0.11)
        elif step == "ascension_law":
            threshold = expected_combat_power(8, 9) * 0.80
            actual = self._player_intrinsic_combat_power(player)
            passed, detail = actual >= threshold, f"战斗力 {actual:.0f}/{threshold:.0f}"
            drain_hp, drain_mp = (0.04, 0.08), (0.06, 0.10)
        elif step == "ascension_heart":
            passed, detail, drain_hp, drain_mp = player.heart_demon <= 45, f"心魔 {player.heart_demon:.1f}/45", (0.02, 0.04), (0.04, 0.07)
        else:
            raise ValueError("未知的飞升劫关隘")
        if not passed:
            player.heart_demon += self._sage_scaled_gain(
                player, float(WORLD_SYSTEMS["breakthrough"]["trial_failure_heart_demon"]),
                "heart_demon_gain_reduction",
            )
            player.next_thunder_damage_reduction = 0.0
            game.active_trial = None
            self._die(game, f"九重飞升劫的{step}判定失败，肉身与元神一同崩解", "SYS_CELESTIAL_ASCENSION_FAILED")
            return "dead", f"飞升判定失败（{detail}），你在仙门之前陨落。"
        hp_loss = max_hp(player) * rng.uniform(*drain_hp) * (1 - reduction)
        mp_loss = max_mp(player) * rng.uniform(*drain_mp) * (1 - reduction)
        player.hp = max(1.0, player.hp - hp_loss)
        player.mp = max(0.0, player.mp - mp_loss)
        trial["step_index"] = int(trial["step_index"]) + 1
        if int(trial["step_index"]) < len(trial["event_ids"]):
            event_id = trial["event_ids"][int(trial["step_index"])]
            game.pending_event = self._instantiate_event(self.events_by_id[event_id], game, rng)
            reduction_text = f"，雷伤减免 {reduction:.0%}" if reduction else ""
            return "trial_step_success", f"第 {trial['step_index']}/9 关通过（{detail}），HP -{hp_loss:.0f}、MP -{mp_loss:.0f}{reduction_text}。"

        origin = player.world
        companion_kept, friend_ids, friend_names, fallen_names = self._resolve_selected_ascension_entourage(
            game, "celestial", rng,
        )
        self._prepare_permanent_world_transition(
            game, keep_companion=companion_kept, keep_friend_ids=friend_ids,
        )
        player.world = "celestial"
        player.location_id = self.maps.default_location("celestial")
        player.realm_index = 9
        player.layer = 1
        player.opportunity = 0.0
        player.awaiting_ascension = False
        player.awaiting_major_breakthrough = False
        player.awaiting_minor_breakthrough = False
        player.immortal_power_converted = False
        player.immortal_conversion_stage = 0
        player.immortal_conversion_last_age = player.age
        player.immortal_conversion_checked_units = 0
        player.next_thunder_damage_reduction = 0.0
        player.next_tribulation_age = None
        player.tribulation_power = None
        player.hp = max_hp(player)
        player.mp = 0.0
        self._clear_market(game)
        self._ensure_heavenly_court(game, rng)
        game.active_trial = None
        game.pending_event = None
        game.history.append(HistoryRecord(
            "SYS_CELESTIAL_ASCENSION_COMPLETE", 1, player.age, "飞升仙界", None, "ascended",
            "你渡过九重飞升劫，自灵界登临仙界并成就真仙；下界法力暂时归零，此后需经过五个长期阶段逐步转化为仙灵力。首次机缘最早在十个仙界时间单位后出现。"
            + (" 道侣与你一同登临仙界。" if companion_kept else "")
            + (f" 道友{'、'.join(friend_names)}成功同行。" if friend_names else "")
            + (f" 道友{'、'.join(fallen_names)}陨落于界壁。" if fallen_names else ""),
            {"world":[origin, "celestial"], "realm_index":[8, 9]},
            ["system", "ascension", "celestial", "milestone"],
        ))
        reduction_text = f"，雷伤减免 {reduction:.0%}" if reduction else ""
        return "trial_completed", f"第 9/9 关通过（{detail}），HP -{hp_loss:.0f}、MP -{mp_loss:.0f}{reduction_text}；你已登临仙界。"

    def _resolve_asura_ascension_step(
        self, game: GameState, step: str, rng: random.Random,
    ) -> tuple[str, str]:
        player = game.player
        trial = game.active_trial
        if not trial:
            raise ValueError("当前没有进行中的修罗飞升劫")
        config = WORLD_SYSTEMS["demonic_cultivation"]["asura_ascension"]
        hp_ratio = player.hp / max(1.0, max_hp(player))
        mp_ratio = player.mp / max(1.0, max_mp(player))
        thunder_index = {
            "asura_thunder_1":0, "asura_thunder_2":1, "asura_thunder_3":2,
        }.get(step)
        reduction = 0.0
        if step == "asura_body":
            passed, detail, drain_hp, drain_mp = hp_ratio >= 0.75, f"HP {hp_ratio:.0%}/75%", (0.04, 0.07), (0.02, 0.04)
        elif step == "asura_boundary":
            current_qi = qi_level(player.qi_experience.get("demon", 0.0))
            required_qi = int(config["required_demon_qi_level"])
            passed = mp_ratio >= 0.68 and current_qi >= required_qi
            detail = f"MP {mp_ratio:.0%}/68%，魔气等级 {current_qi}/{required_qi}"
            drain_hp, drain_mp = (0.03, 0.06), (0.06, 0.10)
        elif thunder_index is not None:
            hp_need = (0.60, 0.50, 0.40)[thunder_index]
            mp_need = (0.54, 0.44, 0.34)[thunder_index]
            passed = hp_ratio >= hp_need and mp_ratio >= mp_need
            detail = f"HP {hp_ratio:.0%}/{hp_need:.0%}，MP {mp_ratio:.0%}/{mp_need:.0%}"
            drain_hp = ((0.09, 0.14), (0.11, 0.17), (0.13, 0.20))[thunder_index]
            drain_mp = ((0.07, 0.12), (0.09, 0.14), (0.11, 0.16))[thunder_index]
            reduction = self._tribulation_damage_reduction(player, "asura_ascension")
        elif step == "asura_karma":
            actual = effective_karma(player)
            limit = float(config["karma_limit"])
            passed, detail = actual <= limit, f"有效因果 {actual:.1f}/{limit:.0f}"
            drain_hp, drain_mp = (0.03, 0.06), (0.04, 0.07)
        elif step == "asura_demon":
            threshold = expected_combat_power(8, 9) * float(config["combat_ratio"])
            actual = self._player_intrinsic_combat_power(player)
            heart_limit = float(config["heart_demon_limit"])
            passed = player.heart_demon <= heart_limit and actual >= threshold
            detail = f"心魔 {player.heart_demon:.1f}/{heart_limit:.0f}，战斗力 {actual:.0f}/{threshold:.0f}"
            drain_hp, drain_mp = (0.06, 0.10), (0.08, 0.12)
        elif step == "asura_sha":
            minimum = int(config["sha_qi_min"])
            passed, detail = player.sha_qi >= minimum, f"煞气 {player.sha_qi}/{minimum}"
            drain_hp, drain_mp = (0.04, 0.08), (0.05, 0.09)
        elif step == "asura_heart":
            limit = float(config["heart_demon_limit"])
            passed, detail = player.heart_demon <= limit, f"心魔 {player.heart_demon:.1f}/{limit:.0f}"
            drain_hp, drain_mp = (0.03, 0.05), (0.05, 0.08)
        else:
            raise ValueError("未知的修罗飞升劫关隘")
        if not passed:
            player.heart_demon += self._sage_scaled_gain(
                player, float(WORLD_SYSTEMS["breakthrough"]["trial_failure_heart_demon"]),
                "heart_demon_gain_reduction",
            )
            player.next_thunder_damage_reduction = 0.0
            game.active_trial = None
            self._die(game, f"九重修罗天魔劫的{step}判定失败，魔躯与元神一同崩解", "SYS_ASURA_ASCENSION_FAILED")
            return "dead", f"修罗飞升判定失败（{detail}），你在天关之前陨落。"
        hp_loss = max_hp(player) * rng.uniform(*drain_hp) * (1 - reduction)
        mp_loss = max_mp(player) * rng.uniform(*drain_mp) * (1 - reduction)
        player.hp = max(1.0, player.hp - hp_loss)
        player.mp = max(0.0, player.mp - mp_loss)
        trial["step_index"] = int(trial["step_index"]) + 1
        if int(trial["step_index"]) < len(trial["event_ids"]):
            event_id = trial["event_ids"][int(trial["step_index"])]
            game.pending_event = self._instantiate_event(self.events_by_id[event_id], game, rng)
            reduction_text = f"，雷伤减免 {reduction:.0%}" if reduction else ""
            return "trial_step_success", f"第 {trial['step_index']}/9 关通过（{detail}），HP -{hp_loss:.0f}、MP -{mp_loss:.0f}{reduction_text}。"

        origin = player.world
        lost_puppets = len(player.puppets)
        companion_kept, friend_ids, friend_names, fallen_names = self._resolve_selected_ascension_entourage(
            game, "asura", rng,
        )
        self._prepare_permanent_world_transition(
            game, keep_companion=companion_kept, keep_friend_ids=friend_ids,
        )
        player.world = "asura"
        player.location_id = self.maps.default_location("asura")
        player.realm_index = 9
        player.layer = 1
        player.opportunity = 0.0
        player.awaiting_ascension = False
        player.awaiting_major_breakthrough = False
        player.awaiting_minor_breakthrough = False
        player.next_thunder_damage_reduction = 0.0
        player.next_tribulation_age = None
        player.tribulation_power = None
        player.hp = max_hp(player)
        player.mp = max_mp(player)
        self._clear_market(game)
        self._ensure_market(game, rng)
        game.active_trial = None
        game.pending_event = None
        game.history.append(HistoryRecord(
            "SYS_ASURA_ASCENSION_COMPLETE", 1, player.age, "飞升修罗界", None, "ascended",
            "你渡过九重修罗天魔劫，自真魔界登临修罗界并成就迦楼罗。四大修罗境界已经确立，但境界突破规则暂未开放。"
            + (f" 受天关排斥，{lost_puppets}具傀儡未能同行。" if lost_puppets else "")
            + (" 道侣与你一同登临修罗界。" if companion_kept else "")
            + (f" 道友{'、'.join(friend_names)}成功同行。" if friend_names else "")
            + (f" 道友{'、'.join(fallen_names)}陨落于界壁。" if fallen_names else ""),
            {"world":[origin, "asura"], "realm_index":[8, 9], "lost_puppets":lost_puppets},
            ["system", "ascension", "asura", "demonic", "milestone"],
        ))
        reduction_text = f"，雷伤减免 {reduction:.0%}" if reduction else ""
        return "trial_completed", f"第 9/9 关通过（{detail}），HP -{hp_loss:.0f}、MP -{mp_loss:.0f}{reduction_text}；你已登临修罗界。"

    def _maybe_immortal_conversion_event(self, game: GameState, rng: random.Random) -> bool:
        player = game.player
        if (
            player.world != "celestial" or player.realm_index < 9 or player.immortal_power_converted
            or player.immortal_conversion_stage >= 5 or game.pending_event or game.active_trial
        ):
            return False
        config = WORLD_SYSTEMS["immortal_power_conversion"]
        unit_years = int(config["time_unit_years"])
        min_gap = int(config["min_gap_units"])
        if player.immortal_conversion_last_age is None:
            player.immortal_conversion_last_age = player.age
            player.immortal_conversion_checked_units = 0
            return False
        elapsed_units = max(0, (player.age - player.immortal_conversion_last_age) // unit_years)
        checked_units = min(elapsed_units, max(0, player.immortal_conversion_checked_units))
        for unit in range(checked_units + 1, elapsed_units + 1):
            player.immortal_conversion_checked_units = unit
            if unit < min_gap:
                continue
            chance = min(0.98, float(config["base_chance"]) + float(config["chance_per_unit"]) * (unit - min_gap))
            if rng.random() >= chance:
                continue
            stage = player.immortal_conversion_stage + 1
            event_id = f"EVT_IMMORTAL_CONVERSION_{stage:03d}"
            event = self._instantiate_event(self.events_by_id[event_id], game, rng)
            event["body"] += f"\n\n你已等待 {unit} 个仙界时间单位，本次触发概率为 {chance:.0%}。"
            event["runtime"] = {"conversion_stage": stage, "waited_units": unit, "trigger_chance": chance}
            game.pending_event = event
            return True
        return False

    def _complete_immortal_conversion_stage(self, game: GameState, expected_stage: int) -> tuple[str, str]:
        player = game.player
        if player.world != "celestial" or player.immortal_power_converted:
            raise ValueError("当前没有可完成的仙灵力转化")
        if expected_stage != player.immortal_conversion_stage + 1 or not 1 <= expected_stage <= 5:
            raise ValueError("仙灵力转化次序不符")
        player.immortal_conversion_stage = expected_stage
        player.immortal_conversion_last_age = player.age
        player.immortal_conversion_checked_units = 0
        player.mp = max_mp(player) * expected_stage / 5
        game.history.append(HistoryRecord(
            f"SYS_IMMORTAL_CONVERSION_{expected_stage}", 1, player.age,
            f"仙灵力转化·{expected_stage * 20}%", None, "completed",
            f"第 {expected_stage}/5 阶段完成，可用仙灵力上限提升至原完整 MP 基准的 {expected_stage * 20}%。",
            {"conversion_stage": expected_stage, "usable_ratio": expected_stage / 5},
            ["system", "celestial", "immortal_power"],
        ))
        if expected_stage < 5:
            return "immortal_conversion_stage", (
                f"第 {expected_stage}/5 阶段完成，可用仙灵力上限现为 {expected_stage * 20}%。"
                "下一阶段需再间隔至少 10 个仙界时间单位。"
            )
        player.immortal_power_converted = True
        learn_technique(player, copy.deepcopy(TECHNIQUE_CATALOG["TECH_CELESTIAL_BREATHING"]))
        add_item(player, "immortal_origin_stone", 3)
        player.hp = max_hp(player)
        player.mp = max_mp(player)
        game.history.append(HistoryRecord(
            "SYS_IMMORTAL_POWER_CONVERTED", 1, player.age, "仙元初成", None, "completed",
            "五个长期阶段全部完成：原有 MP 基准已整体蜕变为仙灵力。你获得《真仙引灵经》与三枚仙元石。",
            {"immortal_power_converted":[False, True], "conversion_stage":5},
            ["system", "celestial", "immortal_power", "milestone"],
        ))
        return "immortal_conversion_completed", "最后阶段完成，仙灵力条已完整开放；仙界行动与仙家功法现已解锁。"

    @staticmethod
    def _body_tribulation_damage_reduction(player: Player) -> float:
        config = WORLD_SYSTEMS["body_cultivation"]
        start = int(config["tribulation_reduction_start"])
        if player.body_training < start:
            return 0.0
        steps = 1 + (player.body_training - start) // int(config["tribulation_reduction_step_layers"])
        return steps * float(config["tribulation_reduction_per_step"])

    def _tribulation_damage_reduction(self, player: Player, kind: str = "heavenly") -> float:
        item_reduction = (
            sum(item.tribulation_damage_reduction * item.quantity for item in player.inventory)
            + player.natal_artifact_tribulation_reduction
            + crafted_artifact_bonuses(player)["tribulation_reduction"]
        )
        one_time = player.next_thunder_damage_reduction if kind in {"periodic_thunder", "celestial_ascension", "asura_ascension"} else 0.0
        sage_key = "thunder_tribulation_reduction" if kind == "periodic_thunder" else "heavenly_tribulation_reduction"
        sage_reduction = max(0.0, float(player.sage_effects.get(sage_key, 0.0)))
        return min(
            0.75,
            item_reduction + self._body_tribulation_damage_reduction(player) + one_time + sage_reduction,
        )

    @staticmethod
    def _tribulation_base_power_cap(world: str) -> float | None:
        raw = WORLD_SYSTEMS["world_profiles"].get(world, {}).get("tribulation_base_power_cap")
        if raw is None:
            return None
        cap = float(raw)
        return cap if cap > 0 else None

    def _check_tribulation(self, game: GameState, rng: random.Random) -> None:
        player = game.player
        true_realm_index = int(
            (player.cultivation_suppression or {}).get("realm_index", player.realm_index)
        )
        true_layer = int(
            (player.cultivation_suppression or {}).get("layer", player.layer)
        )
        if (
            true_realm_index < 6 or game.pending_event or game.active_trial
            or player.next_tribulation_age is None or player.age < player.next_tribulation_age
        ):
            return
        thunder = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
        uncapped_base_power = float(player.tribulation_power or thunder["base_power"])
        world_cap = self._tribulation_base_power_cap(player.world)
        base_power = min(uncapped_base_power, world_cap) if world_cap is not None else uncapped_base_power
        sealed = player.sealed_cultivation or {}
        current_tier = int(WORLD_SYSTEMS["world_profiles"].get(player.world, {}).get("tier", 1))
        upper_tier = int(WORLD_SYSTEMS["world_profiles"].get(str(sealed.get("upper_world", player.world)), {}).get("tier", current_tier))
        world_multiplier = (
            float(WORLD_SYSTEMS["world_travel"].get("lower_world_tribulation_multiplier", 1.0))
            if upper_tier > current_tier else 1.0
        )
        power = base_power * world_multiplier
        event_ids = ["EVT_PERIODIC_THUNDER_001", "EVT_PERIODIC_THUNDER_002", "EVT_PERIODIC_THUNDER_003"]
        game.active_trial = {
            "kind": "periodic_thunder", "source_realm": true_realm_index,
            "target_realm": true_realm_index, "target_layer": true_layer,
            "major": False, "old_label": public_player(player)["realm_name"],
            "step_index": 0, "event_ids": event_ids, "lethal": True, "power": power,
            "base_power":base_power, "uncapped_base_power":uncapped_base_power,
            "world_base_power_cap":world_cap, "world_power_multiplier":world_multiplier,
        }
        game.pending_event = self._instantiate_event(self.events_by_id[event_ids[0]], game, rng)
        game.history.append(HistoryRecord(
            "SYS_TRIBULATION_BEGINS", 1, player.age, "雷劫倒计时归零", None, "started",
            f"第 {player.tribulation_count + 1} 次三千年雷劫降临，当前雷威 {power:.0f}，共需承受三道判定。"
            + (f" 本界法则将基础雷威限制在 {world_cap:.0f}。" if world_cap is not None and uncapped_base_power > world_cap else "")
            + (" 真实道果所在界面高于当前界面，雷劫威力额外增加 50%。" if world_multiplier > 1 else ""),
            {
                "power": power, "base_power":base_power,
                "uncapped_base_power":uncapped_base_power,
                "world_base_power_cap":world_cap,
                "world_power_multiplier":world_multiplier,
                "tribulation_count": player.tribulation_count,
            }, ["system", "tribulation"],
        ))

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


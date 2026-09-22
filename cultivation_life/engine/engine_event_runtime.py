from __future__ import annotations

import copy
import random
import uuid
from typing import Any

from ..content_registry import (
    ACTIONS, FACTION_DEFINITIONS, FACTION_SYSTEMS,
    ITEM_CATALOG, MARKET_GOODS,
    PATH_NAMES, REALMS,
    RACE_DEFINITIONS, RACE_SYSTEMS, TECHNIQUE_CATALOG,
    TECHNIQUE_ELEMENT_NAMES, WORLD_SYSTEMS,
    STORY_COMBAT_SCENARIOS, MONSTER_BLOODLINE_SETTINGS,
)
from ..models import GameState, HistoryRecord, Player, SectNpc
from ..npc_system import npc_team_combat_power
from ..rules import (
    add_item,
    assign_technique,
    expected_combat_power,
    effective_karma,
    has_item,
    acquire_technique,
    max_hp,
    max_mp,
    negative_event_multiplier,
    opportunity_multiplier,
    remove_item,
    root_elements,
    add_technique_copy,
)
from ..transformation_system import (
    active_transformation_profile,
)


from ..world_state import (
    choose_weighted_race, push_fifo_cache,
)
from ..possession_system import (
    current_body_age,
)
from .engine_constants import OPS


class EngineEventRuntimeMixin:
    def _select_event(self, game: GameState, action: str, rng: random.Random) -> dict[str, Any] | None:
        # 无灵根开局的第一节点是路线入口，不能被普通随机事件淹没。
        if game.player.spirit_root == "none" and game.player.realm_index == 0 and game.player.body_training == 0:
            return self.events_by_id["EVT_MORTAL_BODY_BEGIN_001"]
        if (
            game.player.realm_index == 0 and game.player.born_rootless and game.player.age >= 25
            and game.player.body_training < 3 and game.player.mortal_aspiration is None
        ):
            return self.events_by_id["EVT_MORTAL_ASPIRATION_001"]
        candidates: list[tuple[dict[str, Any], float]] = []
        for event in sorted(self.events, key=lambda value: value["id"]):
            tags = event.get("tags", [])
            world_tags = [tag for tag in tags if tag.startswith("world:")]
            if (
                int(WORLD_SYSTEMS.get("world_profiles", {}).get(game.player.world, {}).get("tier", 1)) >= 3
                and f"world:{game.player.world}" not in world_tags
            ):
                continue
            if world_tags and f"world:{game.player.world}" not in world_tags:
                continue
            if "manual_only" in tags:
                continue
            if "revenge" in tags and not self._revenge_ready(game, "ambient", str(event["id"])):
                continue
            if "jinque_acquisition" in tags and game.player.realm_index >= 3:
                continue
            if "probability_gate" in tags:
                continue
            if (
                game.player.world != "human" and "faction" in tags
                and f"world:{game.player.world}" not in tags
            ):
                continue
            if event["id"] == "EVT_MORTAL_ROOT_COMPLETE_001":
                continue
            if "faction" in tags and "faction_join" not in tags:
                continue
            is_mortal_event = "mortal" in tags
            if game.player.realm_index == 0 and not is_mortal_event:
                continue
            if game.player.realm_index > 0 and is_mortal_event:
                continue
            if not self._condition(event.get("conditions", {}), game):
                continue
            if event.get("repeat") == "once" and any(h.event_id == event["id"] for h in game.history):
                continue
            weight = self._event_weight(event, game, action)
            candidates.append((event, max(0, weight)))
        total = sum(weight for _, weight in candidates)
        if total <= 0:
            return None
        roll = rng.random() * total
        for event, weight in candidates:
            roll -= weight
            if roll <= 0:
                if "revenge" in event.get("tags", []):
                    self._record_revenge_trigger(game, "ambient", str(event["id"]))
                return event
        selected = candidates[-1][0]
        if "revenge" in selected.get("tags", []):
            self._record_revenge_trigger(game, "ambient", str(selected["id"]))
        return selected

    @staticmethod
    def _event_weight(event: dict[str, Any], game: GameState, action: str) -> float:
        tags = event.get("tags", [])
        weight = float(event.get("weight", 1)) * event.get("intent_weights", {}).get(action, 1.0)
        if "jinque_acquisition" in tags and any(
            "jinque_acquisition" in record.tags for record in game.history
        ):
            weight *= 0.20
        if "negative" in tags:
            weight *= negative_event_multiplier(game.player)
        return max(0.0, weight)

    def _instantiate_event(self, event: dict[str, Any], game: GameState, rng: random.Random) -> dict[str, Any]:
        result = {key: copy.deepcopy(event[key]) for key in ("id", "title", "body", "choices")}
        for choice in result["choices"]:
            original = next(item for item in event["choices"] if item["id"] == choice["id"])
            choice["enabled"] = self._condition(original.get("conditions", {}), game)
            choice.pop("effects", None)
            choice.pop("conditions", None)
        tags = event.get("tags", [])
        if game.player.realm_index >= 4 and "faction" in tags and "duty" in tags and "war" not in tags:
            delegate_cost = int(FACTION_SYSTEMS["shareholder_delegate_cost"])
            decline_cost = int(FACTION_SYSTEMS["shareholder_decline_cost"])
            result["choices"].extend([
                {"id": "__delegate_faction_task", "text": f"派遣门下弟子代为完成（宗门贡献 -{delegate_cost}）", "enabled": True},
                {"id": "__decline_faction_task", "text": f"以议事席身份拒绝任务（宗门贡献 -{decline_cost}）", "enabled": True},
            ])
        if event.get("combat"):
            combat = event["combat"]
            target = self._generate_cultivator_target(game.player, combat["target_name"], combat, rng, game=game)
            combat_type = str(combat.get("combat_type", "cultivator"))
            if combat_type != "cultivator":
                target["combat_type"] = combat_type
                target["action"] = str(combat.get("action", "hunt_beast" if combat_type == "beast" else "slay"))
                if combat.get("success_threshold") is not None:
                    target["success_threshold"] = float(combat["success_threshold"])
                target["members"] = [{
                    "name": target["target_name"], "power": target["target_power"],
                    "realm_index": target["target_realm_index"], "layer": target["target_layer"],
                    "kind": "beast" if combat_type == "beast" else combat_type,
                    "path": "monster" if combat_type == "beast" else "dao",
                }]
            self._cache_encounter_target(game, target, rng)
            result["runtime"] = target
            result["body"] = (
                result["body"]
                .replace("{target_power}", f"{target['target_power']:.0f}")
                .replace("{target_realm}", target["target_realm_display"])
            )
            if self._world_supports(game.player.world, "races"):
                result["body"] += f" 对方属于{target['race_name']}：{target['race_description']}"
            if len(target.get("members", [])) > 1:
                result["body"] += f" 对方实际共有{len(target['members'])}人结队，显示战斗力为全队合计值。"
        return result

    def _generate_cultivator_target(
        self, player: Player, target_name: str, settings: dict[str, Any], rng: random.Random,
        game: GameState | None = None, forced_race: str | None = None,
        use_player_concealment: bool = False,
    ) -> dict[str, Any]:
        offsets = settings.get("realm_offsets", [[0, 1.0]])
        offset = int(rng.choices([entry[0] for entry in offsets], weights=[entry[1] for entry in offsets], k=1)[0])
        anchor_realm = player.realm_index
        concealment = player.cultivation_concealment if use_player_concealment else None
        if concealment:
            bias = float(WORLD_SYSTEMS.get("secret_arts", {}).get("concealed_enemy_bias", 0.82))
            if rng.random() < max(0.0, min(1.0, bias)):
                anchor_realm = int(concealment["realm_index"])
        target_realm_index = max(1, min(self._world_realm_cap(player.world), anchor_realm + offset))
        target_layer = rng.randint(1, REALMS[target_realm_index].layers)
        expected = expected_combat_power(target_realm_index, target_layer)
        mean = expected * float(settings.get("expectation_multiplier", 1.0))
        sigma = expected * float(settings.get("power_sigma", 0.16))
        lower, upper = settings.get("power_bounds", [0.55, 1.5])
        sampled = rng.gauss(mean, sigma)
        target_power = max(expected * float(lower), min(expected * float(upper), sampled))
        shell = SectNpc("encounter", target_name, "", target_realm_index, target_layer, 0, 1)
        npc_rules = WORLD_SYSTEMS.get("secret_arts", {})
        if target_realm_index >= 2 and rng.random() < float(npc_rules.get("npc_concealment_chance", 0.18)):
            maximum_drop = min(target_realm_index, max(1, int(npc_rules.get("npc_max_realm_drop", 3))))
            shell.concealed_realm_index = max(0, target_realm_index - rng.randint(1, maximum_drop))
            shell.concealed_layer = rng.randint(1, REALMS[shell.concealed_realm_index].layers)
        perception = self._npc_cultivation_perception(game, shell, True) if game else None
        visible = (
            perception["realm_name"] != "无法看清" if perception
            else target_realm_index <= player.realm_index + 1
        )
        target_race = forced_race or "human"
        if self._world_supports(player.world, "races"):
            race_pool = [race_id for race_id, definition in RACE_DEFINITIONS.items() if player.world in definition.get("worlds", [])]
            target_race = forced_race or choose_weighted_race(
                race_pool, self._player_allegiance_race(player), game.race_relations if game else {}, rng,
            )
            target_name = f"{RACE_DEFINITIONS[target_race]['name']}{target_name}"
        target = {
            "target_name": target_name,
            "target_power": round(max(1.0, target_power), 1),
            "primary_power": round(max(1.0, target_power), 1),
            "target_expected_power": round(expected, 1),
            "target_realm_index": target_realm_index,
            "target_layer": target_layer,
            "target_realm_visible": visible,
            "target_realm_display": (
                perception["realm_name"] if perception
                else self._npc_realm_name(shell) if visible else "无法看清"
            ),
            "target_power_display": (
                perception["display_power"] if perception and perception["display_power"] is not None
                else round(max(1.0, target_power), 1)
            ),
            "npc_concealed_realm_index": shell.concealed_realm_index,
            "npc_concealed_layer": shell.concealed_layer,
            "combat_type": "cultivator",
            "race": target_race,
            "race_name": RACE_DEFINITIONS[target_race]["name"],
            "race_description": RACE_DEFINITIONS[target_race]["description"],
            "world": player.world,
        }
        return self._add_enemy_party(target, settings, rng)

    @staticmethod
    def _encounter_person_name(race_id: str, rng: random.Random) -> str:
        surnames = ["顾", "叶", "陆", "楚", "白", "谢", "云", "林", "闻", "景", "苍", "月"]
        given = ["玄", "宁", "川", "微", "岳", "霜", "澄", "昭", "离", "砚", "烬", "渊"]
        base = rng.choice(surnames) + rng.choice(given)
        return base if race_id == "human" else f"{RACE_DEFINITIONS.get(race_id, {'name': race_id})['name']}·{base}"

    def _cache_encounter_target(self, game: GameState, target: dict[str, Any], rng: random.Random) -> None:
        """Stage disposable strangers; promote only repeat/important characters."""
        if target.get("combat_type") != "cultivator":
            return
        cache_limit = int(RACE_SYSTEMS.get("diplomacy", {}).get("encounter_cache_limit", 36))
        for index, member in enumerate(target.get("members", [])):
            if member.get("npc_id"):
                continue
            realm_index = int(member["realm_index"])
            layer = int(member["layer"])
            race_id = str(member.get("race", target.get("race", "human")))
            age_ranges = {
                1: (18, 95), 2: (55, 190), 3: (170, 470), 4: (420, 1350),
                5: (1000, 2900), 6: (2500, 9000), 7: (7000, 24000), 8: (15000, 90000),
            }
            age = rng.randint(*age_ranges.get(realm_index, (18, 70)))
            span = REALMS[realm_index].lifespan
            lifespan = max(age + 1, rng.randint(*span)) if span else None
            npc_id = f"encounter_{game.player.world}_{uuid.uuid4().hex[:12]}"
            name = self._encounter_person_name(race_id, rng)
            npc = SectNpc(
                npc_id, name, str(target.get("target_name", "偶遇修士")) if index == 0 else "同行修士",
                realm_index, layer, age, lifespan,
                spirit_root=self._random_npc_root(realm_index, rng), path=rng.choice(list(PATH_NAMES)),
                race=race_id, world=game.player.world, affinity=rng.uniform(-18, 12),
            )
            if index == 0 and target.get("npc_concealed_realm_index") is not None:
                npc.concealed_realm_index = int(target["npc_concealed_realm_index"])
                npc.concealed_layer = int(target.get("npc_concealed_layer") or 1)
            npc.lifespan = self._scale_npc_lifespan(npc.lifespan, npc.path, npc.age)
            npc.treasure_item_id = self._select_npc_treasure(npc, rng)
            base_power = max(1.0, self._npc_power(npc))
            npc.combat_factor = max(0.1, float(member["power"]) / base_power)
            member.update(
                name=name, npc_id=npc_id, treasure_item_id=npc.treasure_item_id, path=npc.path,
                age=npc.age, lifespan=npc.lifespan, spirit_root=npc.spirit_root,
                gender=npc.gender,
            )
            entry = {
                "id": npc_id, "npc": npc.to_dict(), "combat_power": float(member["power"]),
                "seen_count": 1, "first_seen_age": game.player.age, "last_seen_age": game.player.age,
            }
            push_fifo_cache(game.encounter_npc_cache, entry, cache_limit)
            if self._would_enter_spirit_ranking(game, npc, float(member["power"])):
                self._promote_cached_npc(game, npc_id, "天榜战力")
        if target.get("members"):
            primary = target["members"][0]
            target.update(
                target_name=primary["name"], npc_id=primary.get("npc_id"),
                treasure_item_id=primary.get("treasure_item_id"), primary_power=primary["power"],
            )

    def _would_enter_spirit_ranking(self, game: GameState, npc: SectNpc, power: float) -> bool:
        ranking_world = npc.world
        if not self._world_supports(ranking_world, "ranking"):
            return False
        keys = [
            (entry.realm_index, entry.layer, self._npc_power(entry))
            for entry in [
                *game.world_npcs.values(), *game.notable_npcs.values(),
                *(member for sect in game.sects.values() if sect.world == ranking_world for member in sect.npcs),
            ]
            if entry.alive and entry.world == ranking_world
        ]
        keys.append((game.player.realm_index, game.player.layer, self._player_intrinsic_combat_power(game.player)))
        keys.sort(reverse=True)
        cutoff = keys[19] if len(keys) >= 20 else (-1, -1, -1.0)
        return (npc.realm_index, npc.layer, power) > cutoff

    def _promote_cached_npc(self, game: GameState, npc_id: str, reason: str) -> SectNpc | None:
        entry = next((row for row in game.encounter_npc_cache if row.get("id") == npc_id), None)
        if not entry:
            return game.notable_npcs.get(npc_id)
        npc = SectNpc.from_dict(entry["npc"])
        npc.age += max(0, game.player.age - int(entry.get("last_seen_age", game.player.age)))
        game.notable_npcs[npc.id] = npc
        game.encounter_npc_cache = [row for row in game.encounter_npc_cache if row.get("id") != npc_id]
        game.history.append(HistoryRecord(
            "SYS_NPC_PROMOTED", 1, game.player.age, "人物留名", reason, "promoted",
            f"曾经偶遇的{npc.title}{npc.name}因{reason}不再只是过客，其后续命数将持续演算。",
            {"npc_id": npc.id, "reason": reason}, ["system", "npc", "world_state"],
        ))
        return npc

    def _add_enemy_party(
        self, target: dict[str, Any], settings: dict[str, Any], rng: random.Random,
    ) -> dict[str, Any]:
        members = [{
            "name": target["target_name"], "power": float(target.get("primary_power", target["target_power"])),
            "display_power": float(target.get(
                "target_power_display", target.get("primary_power", target["target_power"]),
            )),
            "realm_index": int(target["target_realm_index"]), "layer": int(target["target_layer"]),
            "npc_id": target.get("npc_id"), "faction_id": target.get("faction_id"), "path": target.get("path", "dao"),
            "race": target.get("race", "human"), "treasure_item_id": target.get("treasure_item_id"),
            "notorious": bool(target.get("notorious", False)), "notoriety": int(target.get("notoriety", 0)),
        }]
        if rng.random() < float(WORLD_SYSTEMS["faction_conflict"]["npc_team_chance"]):
            total = rng.randint(2, 3)
            realm_cap = self._world_realm_cap(str(target.get("world", "human")))
            for index in range(1, total):
                realm_index = max(1, min(realm_cap, int(target["target_realm_index"]) + rng.choice([-1, 0, 0, 1])))
                layer = rng.randint(1, REALMS[realm_index].layers)
                expected = expected_combat_power(realm_index, layer)
                members.append({
                    "name": f"同行修士{index}", "power": round(max(1.0, rng.gauss(expected, expected * 0.12)), 1),
                    "realm_index": realm_index, "layer": layer, "npc_id": None,
                    "faction_id": target.get("faction_id"), "race": target.get("race", "human"),
                    "path": target.get("path", "dao"),
                    "treasure_item_id": None,
                })
        target["members"] = members
        target["target_power"] = npc_team_combat_power(member["power"] for member in members)
        target["target_power_display"] = npc_team_combat_power(
            member.get("display_power", member["power"]) for member in members
        )
        return target

    def _condition(self, condition: dict[str, Any], game: GameState) -> bool:
        if not condition:
            return True
        if "all" in condition:
            return all(self._condition(entry, game) for entry in condition["all"])
        if "any" in condition:
            return any(self._condition(entry, game) for entry in condition["any"])
        if "not" in condition:
            return not self._condition(condition["not"], game)
        if "happened" in condition:
            return any(entry.event_id == condition["happened"] for entry in game.history)
        if "has_item" in condition:
            return has_item(game.player, condition["has_item"], int(condition.get("quantity", 1)))
        if "knows_technique" in condition:
            technique_id = str(condition["knows_technique"])
            player = game.player
            return any(
                technique is not None and technique.id == technique_id
                for technique in [player.technique, player.support_technique, player.body_technique, *player.combat_techniques, *player.known_techniques]
            )
        if "has_flag" in condition:
            return condition["has_flag"] in game.player.story_flags
        if "world_npc" in condition:
            spec = condition["world_npc"]
            npc = game.world_npcs.get(str(spec.get("id")))
            return bool(npc) and all(getattr(npc, key, None) == value for key, value in spec.items() if key != "id")
        if "has_affinity" in condition:
            return condition["has_affinity"] in [*self._base_affinities(game.player), *game.player.additional_roots]
        left = self._path(condition["path"], game)
        return OPS[condition.get("op", "eq")](left, condition.get("value"))

    def _path(self, path: str, game: GameState) -> Any:
        mapping = {
            "player.alive": game.player.alive,
            "player.age": game.player.age,
            "player.karma": game.player.karma,
            "player.effective_karma": effective_karma(game.player),
            "player.realm_index": game.player.realm_index,
            "player.layer": game.player.layer,
            "player.hp_ratio": game.player.hp / max_hp(game.player),
            "player.mp_ratio": game.player.mp / max_mp(game.player),
            "player.path": game.player.technique.path if game.player.technique else game.player.path,
            "player.has_main_technique": game.player.technique is not None,
            "player.monster_species_id": game.player.monster_species_id,
            "player.monster.evolution_id": game.player.monster_evolution_id,
            "player.monster.adaptations": game.player.monster_adaptations,
            "player.monster.imprints": game.player.monster_bloodline_imprints,
            "player.monster.history": game.player.monster_evolution_history,
            "player.has_master": game.player.master is not None,
            "player.master_available": bool(
                game.player.master and game.player.master.get("alive", True)
                and game.player.master.get("world", game.player.world) == game.player.world
            ),
            "player.has_companion": bool(
                game.player.dao_companion and game.player.dao_companion.get("alive", True)
                and game.player.dao_companion.get("world", game.player.world) == game.player.world
            ),
            "player.disciple_count": len(game.player.disciples),
            "player.disciple_total": len(game.player.disciples) + len(game.player.disciple_requests),
            "player.living_disciple_count": sum(
                entry.get("alive", True) and entry.get("world", game.player.world) == game.player.world
                for entry in game.player.disciples
            ),
            "player.sha_qi": game.player.sha_qi,
            "player.fame": game.player.fame,
            "player.born_rootless": game.player.born_rootless,
            "player.mortal_aspiration": game.player.mortal_aspiration,
            "player.spouse": game.player.spouse,
            "player.children": game.player.children,
            "player.official_rank": game.player.official_rank,
            "player.military_merit": game.player.military_merit,
            "player.jianghu_reputation": game.player.jianghu_reputation,
            "player.spirit_root": game.player.spirit_root,
            "player.body_training": game.player.body_training,
            "player.faction_id": game.player.faction_id,
            "player.faction_contribution": game.player.faction_contribution,
            "player.world": game.player.world,
        }
        if path not in mapping:
            raise ValueError(f"未知条件路径：{path}")
        return mapping[path]

    @staticmethod
    def _base_affinities(player: Player) -> list[str]:
        return root_elements(player.spirit_root)

    @staticmethod
    def _is_story_combat_check(event_id: str, effect: dict[str, Any]) -> bool:
        return bool(
            event_id in STORY_COMBAT_SCENARIOS
            and effect.get("type") == "attribute_check"
            and any(check.get("stat") == "combat_power" for check in effect.get("checks", []))
        )

    def _resolve_story_combat_check(
        self, effect: dict[str, Any], game: GameState, pending: dict[str, Any], rng: random.Random,
    ) -> tuple[str, str]:
        power_check = next(check for check in effect["checks"] if check.get("stat") == "combat_power")
        target_power = float(power_check["value"])
        # The scripted power already expresses the authored threat. Reusing an
        # inferred higher realm would count the same advantage twice through
        # both raw power and realm suppression.
        realm_index, layer = game.player.realm_index, game.player.layer
        event_id = str(pending["id"])
        scenario = copy.deepcopy(STORY_COMBAT_SCENARIOS[event_id])
        members = []
        for member in scenario["enemy_members"]:
            effective_power = target_power * float(member["share"])
            member_realm = max(0, min(len(REALMS) - 1, realm_index + int(member.get("realm_offset", 0))))
            members.append({
                "name": str(member["name"]),
                "power": effective_power,
                "full_power": self._story_unit_full_power(member, member_realm, effective_power),
                "realm_index": member_realm,
                "path": str(member.get("path", "dao")),
                "kind": str(member.get("kind", "cultivator")),
            })
        target = {
            "target_name": scenario["target_name"],
            "target_power": target_power,
            "target_realm_index": realm_index,
            "target_layer": layer,
            "combat_type": "story",
            "objective": "repel",
            "enemy_objective": "kill",
            "natural_terrain": scenario["natural_terrain"],
            "artificial_conditions": list(scenario.get("artificial_conditions", [])),
            "max_rounds": int(scenario.get("max_rounds", 6)),
            "members": members,
            "player_allies": scenario.get("player_allies", []),
            "story_beats": scenario["story_beats"],
            "story_choice_id": pending.get("_choice_id"),
            # Epic chains contain several consecutive encounters and their own
            # resource gates. Keep the detailed battle state, but convert only
            # part of it into persistent character injury between scenes.
            "loss_scale": 0.25,
            "mp_loss_scale": 0.0,
        }
        result, combat_summary = self._combat(game, target, False, rng)
        if result == "victory":
            return "check_success", f"{combat_summary}{effect.get('success_text', '')}"
        transformation_revives = "prevent_defeat_once" in active_transformation_profile(game.player)["traits"]
        reason = str(effect.get("failure_reason", "未能战胜剧情强敌"))
        if transformation_revives:
            game.player.hp = max(1.0, game.player.hp)
            if game.last_combat_report:
                game.last_combat_report["death_prevented"] = True
                game.last_combat_report["result"] = "defeat_survived"
                game.last_combat_report.setdefault("key_events", []).append("凤凰变涅槃替你承受了剧情中本应发生的一次陨落。")
            return "check_failed", f"{combat_summary}{reason}；凤凰变涅槃保住了性命，但本次剧情目标失败。"
        self._die(game, reason, event_id)
        if game.last_combat_report:
            game.last_combat_report["result"] = "dead"
            game.last_combat_report["result_grade"] = "溃败"
        return "dead", f"{combat_summary}{reason}。"

    @staticmethod
    def _story_unit_full_power(
        definition: dict[str, Any], realm_index: int, effective_power: float,
    ) -> float:
        if definition.get("full_power") is not None:
            return max(effective_power, float(definition["full_power"]))
        middle_layer = max(1, (REALMS[realm_index].layers + 1) // 2)
        baseline = expected_combat_power(realm_index, int(definition.get("layer", middle_layer)))
        return max(effective_power, baseline * float(definition.get("full_power_multiplier", 1.0)))

    def _effect(self, effect: dict[str, Any], game: GameState, pending: dict[str, Any], rng: random.Random) -> tuple[str | None, str]:
        player = game.player
        kind = effect["type"]
        value = effect.get("value", 0)
        if "range" in effect:
            value = rng.randint(*effect["range"])
        if kind == "add_opportunity":
            amount = round(float(value) * opportunity_multiplier(player), 1)
            if player.world == "celestial" and self._court_law_active(game, "immortal_twofold"):
                amount = round(amount * 1.10, 1)
            self._add_opportunity(player, amount)
            sign = "+" if amount >= 0 else ""
            return None, f"机缘 {sign}{amount}。"
        if kind == "concubine_proposal":
            return self._resolve_concubine_proposal(game, pending, bool(effect.get("accept", False)))
        if kind == "concubine_revenge":
            return self._resolve_concubine_revenge(game, pending, str(effect.get("method", "")), rng)
        if kind == "concubine_escape":
            return self._resolve_concubine_escape(game, pending, str(effect.get("method", "")), rng)
        if kind == "relationship_sanction":
            return self._resolve_relationship_sanction(
                game, pending, str(effect.get("role", "")), str(effect.get("mode", "")), rng,
            )
        if kind == "add_karma":
            player.karma = max(0, player.karma + float(value))
            sign = "+" if value >= 0 else ""
            return None, f"因果 {sign}{value}。"
        if kind == "add_fame":
            player.fame = max(0.0, player.fame + float(value))
            sign = "+" if value >= 0 else ""
            return None, f"威名 {sign}{value}。"
        if kind == "add_sha_qi":
            actual = self._sage_scaled_gain(player, float(value), "sha_qi_gain_reduction")
            player.sha_qi = max(0.0, player.sha_qi + actual)
            sign = "+" if actual >= 0 else ""
            return None, f"煞气 {sign}{actual:g}。"
        if kind == "add_heart_demon":
            actual = self._sage_scaled_gain(player, float(value), "heart_demon_gain_reduction")
            player.heart_demon = max(0.0, player.heart_demon + actual)
            sign = "+" if actual >= 0 else ""
            return None, f"心魔 {sign}{actual:g}。"
        if kind == "relationship_affinity":
            role = str(effect.get("role", "companion"))
            if role == "master":
                relation = player.master
            elif role == "companion":
                relation = player.dao_companion
            elif role == "disciple":
                living = [entry for entry in player.disciples if entry.get("alive", True) and entry.get("world", player.world) == player.world]
                relation = rng.choice(living) if living else None
            else:
                raise ValueError("未知关系角色")
            if not relation:
                return "relationship_absent", "对应之人当前不在身边。"
            actual = self._sage_affinity_gain(player, float(value))
            relation["affinity"] = float(relation.get("affinity", 20)) + actual
            source_npc = self._find_npc(game, str(relation.get("id", "")))
            if source_npc:
                source_npc.affinity = float(relation["affinity"])
            return "relationship_changed", f"{relation.get('name', '对方')}好感 {actual:+g}。"
        if kind == "add_hostility":
            entity = player.world if effect.get("entity") == "current" else str(effect.get("entity"))
            key = self._hostility_key(str(effect.get("kind", "world")), entity)
            player.hostility[key] = max(0.0, player.hostility.get(key, 0) + float(value))
            return None, f"{key} 敌对值 +{float(value):g}。"
        if kind == "wanted_response":
            return self._resolve_wanted_response(game, pending, str(effect["response"]), rng)
        if kind == "war_vanguard":
            return self._resolve_war_vanguard(game, pending, str(effect.get("mode", "fight")), rng)
        if kind == "wanted_settlement":
            return self._resolve_wanted_settlement(game, pending, str(effect.get("mode", "")), rng)
        if kind == "runtime_combat":
            target = copy.deepcopy(pending.get("runtime") or {})
            if not target:
                raise ValueError("遭遇目标已经不存在")
            event_tags = self.events_by_id.get(str(pending.get("id", "")), {}).get("tags", [])
            target["non_story_combat"] = "story_chain" not in event_tags
            action = str(target.get("action", "slay"))
            result, summary = self._combat(game, target, bool(effect.get("lethal", False)), rng)
            return result, self._apply_combat_action_rewards(game, action, result, summary, rng)
        if kind == "cultivator_reaction":
            threshold = float(WORLD_SYSTEMS["faction_conflict"]["fame_deterrence_threshold"])
            if player.fame >= threshold:
                return "deterred", "你的威名足以压住贪念，对方最终不敢追来。"
            chance = float(effect.get("chance", 0.2)) * max(0.0, 1 - player.fame / max(1.0, threshold))
            if rng.random() >= chance:
                return "ignored", "对方虽有不满，最终没有节外生枝。"
            target = self._generate_cultivator_target(player, "心生贪念的修士", ACTIONS["slay"]["combat"], rng, game=game)
            self._cache_encounter_target(game, target, rng)
            target["kill_karma"] = True
            target["action"] = "slay"
            ambush = self._instantiate_event(self.events_by_id["EVT_ENCOUNTER_AMBUSH_001"], game, rng)
            ambush["runtime"] = target
            ambush["body"] = (
                ambush["body"].replace("{target_realm}", str(target["target_realm_display"]))
                .replace("{target_power}", f"{target['target_power']:.0f}")
            )
            if len(target.get("members", [])) > 1:
                ambush["body"] += f" 对方共有{len(target['members'])}人，显示战力为小队合计值。"
            game.pending_event = ambush
            return "ambushed", "你的拒绝激起了对方的贪念，一场杀人夺宝的恶战紧随而来。"
        if kind == "affinity_gift":
            runtime = pending.get("runtime", {})
            npc_id = str(runtime.get("npc_id", ""))
            npc = self._find_npc(game, npc_id)
            if not npc or not npc.alive:
                return "visitor_absent", "故人临时有事，只留下一封问候信。"
            mode = str(effect.get("mode", "accept"))
            if mode == "decline":
                affinity = self._adjust_person_affinity(game,npc_id,1)
                return "declined", f"你未收礼物，但{npc.name}仍领会了你的礼数（好感 {affinity:.0f}）。"
            if mode in {"discuss","share"}:
                gain = rng.randint(5,10) * max(1,npc.realm_index)
                self._add_opportunity(player, gain)
                if mode == "share":
                    player.mp = min(max_mp(player),player.mp + max_mp(player) * 0.08)
                affinity = self._adjust_person_affinity(game,npc_id,2)
                return "discussed", f"你与{npc.name}论道互证，机缘 +{gain}，彼此好感升至 {affinity:.0f}。"
            eligible_goods = [
                row for row in MARKET_GOODS
                if row["kind"] == "item" and row.get("world","human") == player.world
                and int(row["tier"]) <= max(1,npc.realm_index)
                and row["content_id"] in ITEM_CATALOG
                and not {"currency","root_manual"}.intersection(ITEM_CATALOG[row["content_id"]].tags)
            ]
            candidates = list(dict.fromkeys(row["content_id"] for row in eligible_goods))
            if candidates and rng.random() < 0.68:
                best_tier = max(int(row["tier"]) for row in eligible_goods)
                suitable = list(dict.fromkeys(
                    row["content_id"] for row in eligible_goods if int(row["tier"]) == best_tier
                ))
                item_id = rng.choice(suitable or candidates)
                add_item(player,item_id)
                gift_text = ITEM_CATALOG[item_id].name
            else:
                amount = rng.randint(3,8) * max(1,npc.realm_index)
                add_item(player,"spirit_stone",amount)
                gift_text = f"下品灵石 ×{amount}"
            affinity = self._adjust_person_affinity(game,npc_id,3)
            return "gift_received", f"{npc.name}赠予你{gift_text}；对方境界越高，来礼层次也越高（好感 {affinity:.0f}）。"
        if kind == "treasure_reward_choice":
            return self._claim_treasure_reward(game, pending, str(effect["category"]))
        if kind == "personal_revenge_response":
            runtime = pending.get("runtime", {})
            target = copy.deepcopy(runtime.get("target") or {})
            if not target:
                return "revenge_absent", "仇家已不知所踪。"
            mode = str(effect.get("mode", "fight"))
            if mode == "escape":
                mp_ratio = player.mp / max(1.0,max_mp(player))
                player.mp = max(0.0,player.mp - max_mp(player) * 0.16)
                chance = min(0.85,0.30 + mp_ratio * 0.45)
                if rng.random() < chance:
                    return "escaped", f"你以遁术摆脱追杀（成功率 {chance:.0%}），MP 消耗 16%。"
                target["target_power"] *= 1.08
                result, text = self._combat(game,target,True,rng)
                return result, f"遁术失败，你被迫仓促接战。{text}"
            support_text = ""
            if mode == "ally":
                ally = self._find_npc(game,str(runtime.get("ally_id", "")))
                if not ally or not ally.alive:
                    raise ValueError("能够驰援的故交已经不在")
                support = self._npc_power(ally) * 0.50
                target["target_power"] = max(1.0,float(target["target_power"]) - support)
                support_text = f"{ally.name}及时驰援，以约 {support:.0f} 支援战力分担攻势。"
            elif mode == "sect":
                support = float(runtime.get("sect_support_power",0)) * 0.35
                if support <= 0:
                    raise ValueError("当前没有宗门同道可以接应")
                target["target_power"] = max(1.0,float(target["target_power"]) - support)
                support_text = f"宗门接应分担约 {support:.0f} 战力压力。"
            result, text = self._combat(game,target,True,rng)
            return result, support_text + text
        if kind == "heal":
            amount = max_hp(player) * float(value)
            player.hp = min(max_hp(player), player.hp + amount)
            return None, f"HP 恢复 {amount:.0f}。"
        if kind == "restore_mp":
            amount = max_mp(player) * float(value)
            player.mp = min(max_mp(player), max(0, player.mp + amount))
            return None, f"MP {'恢复' if amount >= 0 else '消耗'} {abs(amount):.0f}。"
        if kind == "damage":
            amount = max_hp(player) * float(value)
            player.hp = max(0, player.hp - amount)
            if player.hp <= 0:
                self._die(game, effect.get("reason", "伤势过重"), pending["id"])
            return "dead" if not player.alive else "injured", f"受到 {amount:.0f} 点伤害。"
        if kind == "add_item":
            add_item(player, effect["item_id"], int(effect.get("quantity", 1)))
            return None, f"获得{ITEM_CATALOG[effect['item_id']].name}。"
        if kind == "remove_item":
            removed = remove_item(player, effect["item_id"], int(effect.get("quantity", 1)))
            return None, "失去了一件物品。" if removed else "你身上没有可失去的东西。"
        if kind == "set_flag":
            flag = str(effect["flag"])
            if flag not in player.story_flags:
                player.story_flags.append(flag)
            return None, effect.get("text", "命运的轨迹悄然延伸。")
        if kind == "set_milestone":
            milestone = str(effect["milestone"])
            player.milestones.setdefault(milestone, player.age)
            return None, effect.get("text", "这一年被记入命途节点。")
        if kind == "restore_faction_control":
            sect_id = str(pending.get("runtime", {}).get("sect_id", ""))
            sect = game.sects.get(sect_id)
            plan = self._intrigue_state(game).get("succession_plans", {}).get(sect_id, {})
            if not sect or sect.extinct or sect.world != player.world or not plan.get("eligible_return"):
                return "faction_return_expired", "旧宗已经不复存在，祖师之约就此作罢。"
            plan["eligible_return"] = False
            if not bool(effect.get("accept", False)):
                return "faction_return_declined", f"你谢绝了{sect.name}门人的迎请，让后辈继续执掌宗门。"
            player.faction_id = sect.id
            player.faction_join_age = player.age
            player.faction_contribution = 0
            player.allegiance_race = sect.allegiance_race or player.race
            sect.founded_by_player = True
            sect.founder_player_id = game.id
            sect.founded_by_npc = False
            record = self._ensure_intrigue_faction(game, "sect", sect.id)
            record["controller_id"] = "player"
            positions = record.setdefault("positions", {})
            leader = next(iter(self._intrigue_position_specs("sect")), "")
            if leader:
                positions[leader] = "player"
            return "faction_control_restored", f"你重返{sect.name}祖庭，门人奉还印玺，你重新执掌宗门大权。"
        if kind == "grant_monster_imprint":
            imprint_id = str(effect["imprint_id"])
            gained = self.grant_monster_imprint(player, imprint_id)
            name = MONSTER_BLOODLINE_SETTINGS.get("imprints", {}).get(imprint_id, {}).get("name", imprint_id)
            return ("imprint_acquired" if gained else "imprint_known"), (
                f"获得血脉印记【{name}】；它只会开启新的进化可能，不增加突破概率。"
                if gained else f"血脉印记【{name}】早已存在，这次回响没有叠加任何数值。"
            )
        if kind == "remove_flag":
            flag = str(effect["flag"])
            if flag in player.story_flags:
                player.story_flags.remove(flag)
            return None, effect.get("text", "这条因果至此断绝。")
        if kind == "attribute_check":
            if self._is_story_combat_check(str(pending["id"]), effect):
                return self._resolve_story_combat_check(effect, game, pending, rng)
            failures: list[str] = []
            displays: list[str] = []
            for check in effect.get("checks", []):
                stat = check["stat"]
                target = check.get("value")
                if stat == "has_item":
                    passed = has_item(player, str(check["item_id"]), int(check.get("quantity", 1)))
                    displays.append(f"必要信物：{'具备' if passed else '缺失'}")
                else:
                    actual = {
                        "hp": player.hp,
                        "mp": player.mp,
                        "combat_power": self._player_intrinsic_combat_power(player),
                        "hp_ratio": player.hp / max_hp(player),
                        "mp_ratio": player.mp / max_mp(player),
                        "combat_ratio": self._player_intrinsic_combat_power(player) / max(1.0, expected_combat_power(player.realm_index, player.layer)),
                        "karma": effective_karma(player),
                        "sha_qi": player.sha_qi,
                        "heart_demon": player.heart_demon,
                        "fame": player.fame,
                    }.get(stat)
                    if actual is None:
                        raise ValueError(f"未知属性判定：{stat}")
                    passed = OPS[check.get("op", "gte")](actual, target)
                    labels = {
                        "hp": "当前HP", "mp": "当前MP", "combat_power": "当前战斗力",
                        "hp_ratio": "HP比例", "mp_ratio": "MP比例",
                        "combat_ratio": "期望战力倍率", "karma": "有效因果",
                        "sha_qi": "煞气", "heart_demon": "心魔", "fame": "威名",
                    }
                    displays.append(f"{labels[stat]} {actual:.2f}/{float(target):.2f}")
                if not passed:
                    failures.append(stat)
            detail = "，".join(displays)
            if failures:
                reason = effect.get("failure_reason", "未能通过生死判定，身死道消")
                self._die(game, reason, pending["id"])
                return "dead", f"判定失败（{detail}）。{reason}。"
            return "check_success", f"判定通过（{detail}）。{effect.get('success_text', '')}".strip()
        if kind == "trial_step":
            return self._resolve_trial_step(game, str(effect["step"]), rng)
        if kind == "advance_immortal_conversion":
            return self._complete_immortal_conversion_stage(game, int(effect["stage"]))
        if kind == "add_court_merit":
            return None, self._add_court_merit(game, int(value))
        if kind == "relationship_capture_step":
            return self._relationship_capture_step(
                game, pending, str(effect.get("stage", "")), str(effect.get("method", "")), rng,
            )
        if kind == "ghost_reincarnate":
            transition = self._complete_ghost_reincarnation(game, record_history=False)
            return "reincarnated", str(transition["summary"])
        if kind == "queue_event":
            event_id = str(effect["event_id"])
            event = self.events_by_id.get(event_id)
            if event is None:
                raise ValueError(f"后续事件不存在：{event_id}")
            game.pending_event = self._instantiate_event(event, game, rng)
            return None, effect.get("text", "新的险局接踵而至。")
        if kind == "enter_spirit_realm":
            destination = self._ascension_destination(player.path)
            lost_puppets = len(player.puppets)
            player.awaiting_spirit_realm_crossing = False
            joint_crossing = player.joint_spirit_crossing
            companion = player.dao_companion
            crossed_together = bool(
                joint_crossing and companion and companion.get("alive", True)
                and companion.get("id") == joint_crossing.get("id")
            )
            if crossed_together:
                companion["world"] = destination
                npc = self._find_npc(game, str(companion.get("id", "")))
                if npc:
                    npc.world = destination
                    npc.departed_age = npc.age
                    npc.departure_reason = f"与{player.name}共同偷渡{WORLD_SYSTEMS['world_names'][destination]}"
            else:
                player.dao_companion = None
            crossing_friends = list(player.joint_friend_crossing)
            friend_survivors: list[str] = []
            friend_survivor_ids: set[str] = set()
            friend_fallen: list[str] = []
            survival_chance = float(WORLD_SYSTEMS["relationship"]["friend_crossing_survival_chance"])
            for candidate in crossing_friends:
                friend = next((row for row in player.dao_friends if row.get("id") == candidate.get("id")), None)
                npc = self._find_npc(game, str(candidate.get("id", "")))
                if friend and not friend.get("alive", True):
                    continue
                if not friend and (not npc or not npc.alive):
                    continue
                name = str((friend or candidate).get("name", npc.name if npc else "无名队友"))
                if rng.random() < survival_chance:
                    if friend:
                        friend["world"] = destination
                    friend_survivors.append(name)
                    friend_survivor_ids.add(str(candidate.get("id", "")))
                    if npc:
                        npc.world = destination
                        npc.departed_age = npc.age
                        npc.departure_reason = f"与{player.name}共同偷渡{WORLD_SYSTEMS['world_names'][destination]}"
                else:
                    if friend:
                        friend["alive"] = False
                        friend["death_reason"] = "偷渡界壁时迷失于空间风暴"
                    friend_fallen.append(name)
                    if npc:
                        npc.alive = False
                        npc.death_reason = "偷渡界壁时迷失于空间风暴"
            self._prepare_permanent_world_transition(
                game, keep_companion=crossed_together,
                keep_friend_ids=friend_survivor_ids,
            )
            player.world = destination
            player.location_id = self.maps.default_location(destination)
            self._clear_market(game)
            destination_name = WORLD_SYSTEMS["world_names"][destination]
            companion_text = f" {companion['name']}也与你一同落地，道侣关系得以保留。" if crossed_together else ""
            friend_text = ""
            if friend_survivors:
                friend_text += f" 队友{'、'.join(friend_survivors)}侥幸穿过空间风暴，与你在此界重聚。"
            if friend_fallen:
                friend_text += f" 队友{'、'.join(friend_fallen)}未能熬过界壁，自此魂灯熄灭。"
            if crossing_friends:
                game.history.append(HistoryRecord(
                    "SYS_FRIEND_CROSSING",1,player.age,"队友越界",None,"resolved",
                    (f"随行队友中，{'、'.join(friend_survivors) if friend_survivors else '无人'}成功抵达{destination_name}；"
                     f"{'、'.join(friend_fallen) if friend_fallen else '无人'}陨落于空间风暴。"),
                    {"survivors":friend_survivors,"fallen":friend_fallen},
                    ["system","relationship","friend","world_crossing","world:global"],
                ))
            puppet_text = f" 受界壁排斥，{lost_puppets}具傀儡全部遗失。" if lost_puppets else ""
            return "entered_spirit_realm", f"你穿透界壁落入{destination_name}，人界宗门与师徒名册从此再无法感应。{puppet_text}{companion_text}{friend_text}"
        if kind == "technique_level":
            if player.technique is None:
                return "no_technique", "你尚无主修功法，无法参悟。"
            quantity = max(1, int(value))
            add_technique_copy(player, player.technique, quantity)
            return None, f"你将感悟凝成《{player.technique.name}》同源传承玉简 ×{quantity}，已收入包裹。"
        if kind == "equip_technique":
            template = copy.deepcopy(TECHNIQUE_CATALOG[effect["technique_id"]])
            template.path = player.technique.path if player.technique else player.path
            assign_technique(player, template, effect["slot"])
            slot_name = {
                "main": "主修", "support": "辅修", "combat": "战斗", "body": "炼体",
                "divine_sense": "神识", "transformation": "变身",
            }[effect["slot"]]
            return "technique_equipped", f"你将《{template.name}》设为{slot_name}功法。"
        if kind == "learn_technique":
            template = copy.deepcopy(TECHNIQUE_CATALOG[effect["technique_id"]])
            learned = acquire_technique(player, template)
            # Keep the legacy result tag because story chains use it to gate
            # later rewards; only the duplicate's storage semantics changed.
            return ("technique_learned" if learned else "already_known"), (
                f"你悟得《{template.name}》，功法已收入已悟列表，并未改变当前配置。"
                if learned else f"你已经掌握《{template.name}》，同源传承玉简已收入包裹，可用于升级。"
            )
        if kind == "gain_generated_master":
            if player.master:
                return "already_has_master", "你已有师承，没有再行拜师。"
            relation = self._generated_relationship(player, "master", rng)
            if rng.random() >= float(effect.get("accept_chance", 0.55)):
                return "rejected", f"{relation['name']}认为缘分未至，婉拒了你的拜师请求。"
            player.master = relation
            return "master_accepted", f"{relation['name']}收你为徒，你自此有了师承。"
        if kind == "gain_generated_companion":
            if player.dao_companion and player.dao_companion.get("alive", True):
                return "already_has_companion", "你已有道侣，没有另结新缘。"
            relation = self._generated_relationship(player, "companion", rng)
            player.dao_companion = relation
            return "companion_joined", f"你与{relation['name']}立下同道誓约，自此结为道侣。"
        if kind == "gain_generated_disciple":
            max_disciples = int(WORLD_SYSTEMS["relationship"]["max_disciples"])
            if len(player.disciples) + len(player.disciple_requests) >= max_disciples:
                return "disciple_limit", "你暂时无意再扩大师门。"
            relation = self._generated_relationship(player, "disciple", rng)
            player.disciple_requests.append(relation)
            return "disciple_requested", f"{relation['name']}呈上拜师帖；是否收入门下，仍须由你亲自决定。"
        if kind == "body_training":
            if player.body_technique is None:
                return "no_body_technique", "你没有可用的炼体功法，无法真正踏入炼体之门。"
            player.body_training = min(
                int(WORLD_SYSTEMS["body_cultivation"]["max_layer"]),
                max(0, player.body_training + int(value)),
            )
            player.body_progress = 0.0
            player.awaiting_body_breakthrough = False
            player.hp = min(max_hp(player), player.hp + max_hp(player) * 0.15)
            return None, f"炼体境界提升至 {player.body_training} 层。"
        if kind == "add_body_progress":
            if player.body_technique is None:
                return "no_body_technique", "你没有配置炼体功法，这番苦熬只留下了暗伤。"
            maximum = int(WORLD_SYSTEMS["body_cultivation"]["max_layer"])
            if player.body_training >= maximum:
                return "body_training_max", "炼体已达一百层极限。"
            required = self._body_progress_required(player)
            player.body_progress = min(required, player.body_progress + float(value))
            player.awaiting_body_breakthrough = player.body_progress >= required
            return None, f"炼体积累 +{float(value):g}（{player.body_progress:.1f}/{required:.1f}）。"
        if kind == "extend_lifespan":
            if player.realm_index != 0:
                return None, "你已踏入仙途，凡俗炼体不再改变寿元。"
            amount = int(value)
            body_age = current_body_age(player)
            old = int(player.lifespan or body_age)
            player.lifespan = min(300, max(old, body_age + 1) + amount)
            return None, f"炼体延寿，寿元上限由 {old} 提升至 {player.lifespan} 岁。"
        if kind == "acquire_root":
            if player.spirit_root != "none":
                return None, "你的灵根已经完整。"
            affinity = effect["affinity"]
            player.spirit_root = f"acquired_{affinity}"
            player.acquired_root = True
            return "root_repaired", f"残缺经脉中生出一缕{TECHNIQUE_ELEMENT_NAMES[affinity]}灵性，你获得了对应的后天灵根。"
        if kind == "add_random_jinque":
            affinity = rng.choice(["wind", "thunder", "yin", "yang", "fire", "water", "wood", "metal", "earth"])
            item_id = f"jinque_{affinity}"
            add_item(player, item_id)
            return "jinque_found", f"你获得了《{ITEM_CATALOG[item_id].name}》。"
        if kind == "set_mortal_aspiration":
            player.mortal_aspiration = str(effect["aspiration"])
            names = {"family": "娶妻荫子", "scholar": "考试当官", "military": "沙场效忠", "jianghu": "江湖驰骋"}
            return "aspiration_set", f"你立志走上“{names[player.mortal_aspiration]}”之路。"
        if kind == "mortal_progress":
            field = effect["field"]
            if field not in {"children", "official_rank", "military_merit", "jianghu_reputation"}:
                raise ValueError("未知凡人进度")
            setattr(player, field, max(0, int(getattr(player, field)) + int(value)))
            return None, effect.get("text", "凡尘经历又添一笔。")
        if kind == "set_spouse":
            player.spouse = bool(effect.get("value", True))
            return None, "你与良人结为夫妻。"
        if kind == "join_faction":
            faction_id = str(effect["faction_id"])
            if faction_id not in FACTION_DEFINITIONS:
                raise ValueError("未知宗门")
            if player.faction_id:
                return None, f"你已是{FACTION_DEFINITIONS[player.faction_id]['name']}门人。"
            if FACTION_DEFINITIONS[faction_id].get("world", "human") != player.world:
                return "wrong_world", "这座宗门并不位于你当前所在的界面。"
            player.faction_id = faction_id
            player.allegiance_race = FACTION_DEFINITIONS[faction_id].get("allegiance_race")
            player.faction_join_age = player.age
            player.faction_contribution = 0
            return "faction_joined", f"你正式拜入{FACTION_DEFINITIONS[faction_id]['name']}，自此共享宗门福祸。"
        if kind == "add_faction_contribution":
            if not player.faction_id:
                return None, "你尚无宗门身份。"
            player.faction_contribution = max(0, player.faction_contribution + int(value))
            sign = "+" if value >= 0 else ""
            return None, f"宗门贡献 {sign}{int(value)}。"
        if kind == "sect_defense":
            runtime = pending.get("runtime", {})
            sect = game.sects.get(str(runtime.get("sect_id", player.faction_id or "")))
            if not sect or sect.extinct or player.faction_id != sect.id:
                return "sect_absent", "山门已经不复存在。"
            mode = str(effect.get("mode", "fight"))
            success = False
            detail = ""
            if mode == "fight":
                required = float(runtime.get("required_power", 1))
                combat_result, combat_summary = self._combat(game, {
                    "target_name": "来犯山门的敌修", "target_power": required,
                    "target_realm_index": player.realm_index, "target_layer": player.layer,
                    "combat_type": "cultivator", "action": "repel",
                    "enemy_objective": "break_formation",
                }, False, rng)
                success = combat_result == "victory"
                detail = combat_summary
            elif mode == "formation":
                guard_array = self._sect_guard_array(game, sect.id)
                required = float(runtime.get("required_power", 1))
                if guard_array:
                    profile = self._ground_profile(player, guard_array)
                    defense_power = self._sect_guard_power(game, sect.id)
                    variance = rng.uniform(
                        float(self._formation_rules().get("sect_defense_variance_min", 0.94)),
                        float(self._formation_rules().get("sect_defense_variance_max", 1.06)),
                    )
                    effective_power = defense_power * variance
                    success = effective_power >= required
                    wear = float(self._formation_rules().get(
                        "sect_defense_success_wear" if success else "sect_defense_failure_wear",
                        7.0 if success else 15.0,
                    ))
                    # A badly outmatched assault strains the anchor further,
                    # but one event can never delete more than 25 durability.
                    wear *= min(1.65, max(0.75, required / max(1.0, defense_power)))
                    guard_array["durability"] = round(max(
                        0.0, float(guard_array.get("durability", 0.0)) - min(25.0, wear),
                    ), 4)
                    guard_array["battles"] = int(guard_array.get("battles", 0)) + 1
                    detail = (
                        f"真实护山阵“{guard_array['name']}”以 {effective_power:.0f} 阵力对抗"
                        f" {required:.0f} 来犯战力，永久完整度降至 {guard_array['durability']:.1f}%"
                    )
                    if success:
                        gain = min(
                            float(self._formation_rules().get("ground_experience_cap", 55.0)),
                            18.0 + profile.get("occupied_count", 0) * 2.5 + min(12.0, required / max(1.0, defense_power) * 8.0),
                        )
                        self._grant_art_experience(player, "formation", gain)
                else:
                    success = False
                    detail = "宗门没有以真实阵材镇下护山阵；旧阵盘不能再直接替代整座大阵"
            elif mode == "appease":
                cost = 80 if player.world == "human" else 800
                success = remove_item(player, "spirit_stone", cost)
                detail = f"支付灵石 {cost}" if success else f"灵石不足 {cost}"
            elif mode == "abandon":
                self._dissolve_player_sect(game, sect, "你主动撤下山门匾额，门人各寻出路")
                return "sect_dissolved", "你不愿门人为一座虚名送死，主动解散了宗门。"
            if success:
                player.faction_contribution += 5
                return "defended", f"{detail}；你成功护住山门，既有失败次数仍为 {sect.pressure}/3，宗门贡献 +5。"
            sect.pressure += 1
            if sect.pressure >= int(WORLD_SYSTEMS["player_faction"]["pressure_limit"]):
                self._dissolve_player_sect(game, sect, "连续三次未能抵御外部打压")
                return "sect_dissolved", f"{detail}；这是第三次护山失败，门人信心尽失，宗门就此解散。"
            return "defense_failed", f"{detail}；护山失败累计 {sect.pressure}/3，宗门仍在，但下一次来犯会更加凶险。"
        if kind == "faction_war":
            if not player.faction_id:
                return None, "战帖与你无关。"
            veteran = player.realm_index > 4 or (player.realm_index == 4 and player.layer > 3)
            target_power = expected_combat_power(player.realm_index, max(1, player.layer))
            target_power *= rng.uniform(0.68, 0.88) if veteran else rng.uniform(0.95, 1.25)
            formation_duty = int(effect.get("contribution", 12)) <= 9
            combat_result, summary = self._combat(game, {
                "target_name": "敌宗会战修士",
                "target_power": target_power,
                "target_realm_index": player.realm_index,
                "target_layer": max(1, player.layer),
                "combat_type": "cultivator",
                "objective": "repel",
                "enemy_objective": "repel",
                "max_rounds": 5,
                "non_story_combat": True,
                "artificial_conditions": ["大阵"] if formation_duty else [],
            }, True, rng)
            if combat_result == "dead":
                return "dead", summary
            if combat_result == "defeat":
                player.faction_contribution += max(1, int(effect.get("contribution", 8)) // 2)
                return "survived", summary + " 你虽未夺得阵地，仍因完成撤离与接应获得部分宗门贡献。"
            player.faction_contribution += int(effect.get("contribution", 12))
            return "victory", summary + " 你完成会战目标，宗门贡献有所增加。"
        if kind == "combat":
            target = pending["runtime"]
            event_tags = self.events_by_id.get(str(pending.get("id", "")), {}).get("tags", [])
            target["non_story_combat"] = "story_chain" not in event_tags
            return self._combat(game, target, bool(effect.get("lethal")), rng)
        raise ValueError(f"未知效果类型：{kind}")


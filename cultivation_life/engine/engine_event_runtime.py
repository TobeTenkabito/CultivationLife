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
from ..system.npc_system import npc_team_combat_power
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
from ..system.transformation_system import (
    active_transformation_profile,
)


from ..world_state import (
    choose_weighted_race, push_fifo_cache,
)
from ..system.possession_system import (
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
            target["player_defending"] = bool(combat.get("player_defending") or "defense" in tags)
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

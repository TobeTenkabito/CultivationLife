from __future__ import annotations

import copy
import math
import random
import uuid
from typing import Any

from ..content_registry import (
    GUIXU_EXCLUSIVE_TECHNIQUE_IDS, ITEM_CATALOG, PATH_NAMES, REALMS,
    TECHNIQUE_CATALOG, WORLD_SYSTEMS,
)
from ..models import GameState, HistoryRecord, Player, SectNpc
from .npc_system import party_combat_power
from ..rules import (
    combat_power, divine_sense_level, has_item, max_hp, max_mp, qi_level,
    puppet_capacity, remove_item, technique_environment_multiplier, technique_scale,
)
from ..runtime import decode_rng, encode_rng, now_iso
from .possession_system import advance_player_age, current_body_age


PUPPET_NAMES = {"corpse": "炼尸", "living": "活傀", "mechanical": "机关傀儡"}


class DemonicSystemMixin:
    """俘虏、傀儡、吞噬、外来元神与神识的完整领域闭环。"""

    @staticmethod
    def _demonic_rules() -> dict[str, Any]:
        return WORLD_SYSTEMS["demonic_cultivation"]

    @staticmethod
    def _puppet_technique(technique_id: str | None):
        return TECHNIQUE_CATALOG.get(str(technique_id or ""))

    def _capture_cultivator(
        self, game: GameState, target: dict[str, Any], own_power: float, rng: random.Random,
    ) -> tuple[str, str]:
        members = target.get("members") or [{
            "name": target["target_name"], "power": target["target_power"],
            "realm_index": target["target_realm_index"], "layer": target.get("target_layer", 1),
            "npc_id": target.get("npc_id"), "race": target.get("race", "human"),
        }]
        victim = min(members, key=lambda entry: float(entry["power"]))
        ratio = own_power / max(1.0, float(victim["power"]))
        realm_gap = game.player.realm_index - int(victim["realm_index"])
        chance = max(0.08, min(0.92, 0.28 + (ratio - 1) * 0.18 + realm_gap * 0.07))
        if rng.random() >= chance:
            return "victory_escape", f"你虽击败{victim['name']}，却未能封住其遁术（生擒率 {chance:.0%}）。"

        npc_id = victim.get("npc_id")
        npc = self._find_npc(game, str(npc_id)) if npc_id else None
        path = npc.path if npc else str(victim.get("path", "dao"))
        affinity = float(npc.affinity or 0) if npc else 0.0
        technique = next(
            (entry for entry in TECHNIQUE_CATALOG.values() if entry.path == path and entry.category == "spiritual"
             and entry.grade <= max(1, int(victim["realm_index"]))
             and entry.id not in GUIXU_EXCLUSIVE_TECHNIQUE_IDS),
            None,
        )
        prisoner_id = str(npc_id or f"captive_{uuid.uuid4().hex[:12]}")
        captive_age = int(npc.age if npc else victim.get("age", current_body_age(game.player)))
        captive_lifespan = npc.lifespan if npc else victim.get("lifespan")
        game.player.prisoners.append({
            "id": prisoner_id, "npc_id": npc_id, "name": str(victim["name"]),
            "realm_index": int(victim["realm_index"]), "layer": int(victim.get("layer", 1)),
            "realm_name": self._npc_realm_name(npc or SectNpc("", "", "", int(victim["realm_index"]), int(victim.get("layer", 1)), 0, 1, path=path)),
            "path": path, "path_name": PATH_NAMES.get(path, path), "race": str(victim.get("race", "human")),
            "affinity": affinity - 12, "combat_power": round(float(victim["power"]), 1),
            "main_technique_id": technique.id if technique else None,
            "age": captive_age, "lifespan": captive_lifespan,
            "gender": npc.gender if npc else str(victim.get("gender") or self._stable_gender(prisoner_id)),
            "captured_age": game.player.age, "source": "combat",
        })
        if npc:
            npc.alive = False
            npc.death_reason = f"被{game.player.name}生擒"
        if npc_id:
            game.encounter_npc_cache = [row for row in game.encounter_npc_cache if row.get("id") != npc_id]
        return "captured", f"你封住{victim['name']}的修为，将其生擒并收入俘虏名册（生擒率 {chance:.0%}）。"

    def begin_relationship_capture(self, game_id: str, kind: str, target_id: str = "") -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if player.path != "demonic":
            raise ValueError("只有魔修会对亲近之人施展生擒魔禁")
        if not player.alive or game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法对关系人物出手")
        relation = (
            player.master if kind == "master" else
            player.dao_companion if kind == "companion" else
            next((row for row in player.dao_friends if str(row.get("id")) == target_id), None)
            if kind == "friend" else None
        )
        if not relation or not relation.get("alive", True) or relation.get("world", player.world) != player.world:
            raise ValueError("目标关系人物当前不在身边")
        if relation.setdefault("last_interactions", {}).get("capture_attempt") == player.age:
            raise ValueError("本行动年份已经尝试生擒过此人")
        rng = decode_rng(game.seed, game.rng_state)
        event = self._instantiate_event(self.events_by_id["EVT_RELATION_CAPTURE_001"], game, rng)
        event["body"] = event["body"].replace("{target_name}", str(relation["name"]))
        event["runtime"] = {
            "kind":kind, "target_id":str(relation["id"]), "target_name":str(relation["name"]),
            "target_power":self._relationship_combat_power(relation),
        }
        game.pending_event = event
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def _relationship_capture_step(
        self, game: GameState, pending: dict[str, Any], stage: str, method: str, rng: random.Random,
    ) -> tuple[str, str]:
        player = game.player
        runtime = pending.get("runtime", {})
        kind = str(runtime.get("kind", ""))
        relation = (
            player.master if kind == "master" else
            player.dao_companion if kind == "companion" else
            next((row for row in player.dao_friends if str(row.get("id")) == str(runtime.get("target_id"))), None)
            if kind == "friend" else None
        )
        if not relation or str(relation.get("id")) != str(runtime.get("target_id")):
            return "target_absent", "目标已经脱离了这段关系，生擒计划无从继续。"
        relation.setdefault("last_interactions", {})["capture_attempt"] = player.age
        name = str(relation.get("name", "无名修士"))
        if stage == "abandon":
            return "abandoned", f"你最终没有对{name}出手，这段关系暂时维持原状。"

        own_power = self._player_intrinsic_combat_power(player)
        target_power = max(1.0, float(runtime.get("target_power", self._relationship_combat_power(relation))))
        ratio_term = math.log2(max(0.25, own_power / target_power))
        realm_gap = player.realm_index - int(relation.get("realm_index", 0))
        affinity = float(relation.get("affinity", 0))
        if stage == "opening":
            method_bonus = 0.16 if method == "ambush" else 0.03
            chance = max(0.06, min(0.94, 0.30 + method_bonus + ratio_term * 0.11 + realm_gap * 0.06 + max(0.0, affinity) / 500))
            if rng.random() >= chance:
                self._break_capture_relationship(game, relation, kind, captured=False)
                return "escaped", f"{name}识破杀机并断绝关系后遁走（第一重压制成功率 {chance:.0%}）。"
            next_event = self._instantiate_event(self.events_by_id["EVT_RELATION_CAPTURE_002"], game, rng)
            next_event["body"] = next_event["body"].replace("{target_name}", name)
            next_event["runtime"] = copy.deepcopy(runtime)
            game.pending_event = next_event
            return "body_suppressed", f"你成功制住{name}的肉身（第一重压制成功率 {chance:.0%}），接下来必须镇封其元神。"

        if stage == "release":
            self._break_capture_relationship(game, relation, kind, captured=False)
            return "released", f"你放开禁制；{name}惊怒离去，这段关系彻底断绝。"
        if stage != "final":
            raise ValueError("未知关系生擒阶段")
        method_bonus = 0.15 if method == "blood_mark" else 0.04
        if method == "blood_mark":
            damage = max_hp(player) * 0.12
            player.hp = max(1.0, player.hp - damage)
        chance = max(0.05, min(
            0.93,
            0.32 + method_bonus + ratio_term * 0.10 + realm_gap * 0.05
            + max(0, divine_sense_level(player) - int(relation.get("realm_index", 0))) * 0.025,
        ))
        if rng.random() >= chance:
            self._break_capture_relationship(game, relation, kind, captured=False)
            return "escaped", f"{name}的元神撕开魔禁并远遁（封魂成功率 {chance:.0%}），从此与你恩断义绝。"
        prisoner = {
            "id":str(relation["id"]), "npc_id":str(relation["id"]), "name":name,
            "realm_index":int(relation.get("realm_index", 0)), "layer":int(relation.get("layer", 1)),
            "realm_name":str(relation.get("realm_name", "境界未明")),
            "path":str(relation.get("path", "dao")),
            "path_name":PATH_NAMES.get(str(relation.get("path", "dao")), str(relation.get("path", "dao"))),
            "race":str(relation.get("race", "human")), "affinity":-100.0,
            "combat_power":round(target_power, 1), "main_technique_id":relation.get("main_technique_id"),
            "age":int(relation.get("age", player.age)), "lifespan":relation.get("lifespan"),
            "gender":str(relation.get("gender") or self._stable_gender(str(relation.get("id", "")))),
            "captured_age":player.age, "source":f"relationship:{kind}",
        }
        player.prisoners.append(prisoner)
        self._break_capture_relationship(game, relation, kind, captured=True)
        relation_name = {"master":"师父", "companion":"道侣", "friend":"道友"}.get(kind, "故人")
        return "captured", f"你彻底封住{name}的元神，将昔日{relation_name}收入俘虏名册（封魂成功率 {chance:.0%}）。"

    def _break_capture_relationship(
        self, game: GameState, relation: dict[str, Any], kind: str, captured: bool,
    ) -> None:
        player = game.player
        target_id = str(relation.get("id", ""))
        player.party = [entry for entry in player.party if str(entry.get("id")) != target_id]
        if kind == "master":
            player.master = None
        elif kind == "friend":
            player.dao_friends = [row for row in player.dao_friends if str(row.get("id")) != target_id]
        else:
            player.dao_companion = None
        npc = self._find_npc(game, target_id)
        if npc:
            if captured:
                npc.alive = False
                npc.death_reason = f"被{player.name}背叛并生擒"
            else:
                npc.affinity = float(WORLD_SYSTEMS["relationship"].get("relationship_release_affinity", 0))

    def captive_action(self, game_id: str, target_id: str, action: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not player.alive or game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法处置俘虏")
        prisoner = next((entry for entry in player.prisoners if str(entry.get("id")) == target_id), None)
        disciple = next((entry for entry in player.disciples if str(entry.get("id")) == target_id and entry.get("alive", True)), None)
        target = prisoner or disciple
        if not target:
            raise ValueError("目标俘虏或弟子不存在")
        if action not in {"release", "torture", "corpse", "living", "possess"}:
            raise ValueError("未知俘虏处置方式")
        if action in {"corpse", "living"} and player.path != "demonic":
            raise ValueError("只有魔修能够炼尸或种下活傀标记")
        if action in {"corpse", "living"} and len(player.puppets) >= puppet_capacity(player):
            raise ValueError("神识可控傀儡数量已经达到上限")

        rng = decode_rng(game.seed, game.rng_state)
        name = str(target.get("name", "无名修士"))
        if action == "possess":
            if disciple:
                raise ValueError("夺舍入口只接受已经生擒的肉身")
            from .possession_system import can_possess, enter_host_body
            allowed, reason = can_possess(player, target)
            if not allowed:
                raise ValueError(reason)
            target_power = max(1.0, float(target.get("combat_power", 1.0)))
            own_power = max(1.0, combat_power(player))
            chance = max(0.10, min(0.95, 0.55 + (own_power - target_power) / (own_power + target_power) * 0.35))
            if rng.random() < chance:
                player.prisoners.remove(target)
                host = enter_host_body(player, target)
                npc = self._find_npc(game, str(target.get("npc_id") or target.get("id", "")))
                if npc:
                    npc.alive = False
                    npc.death_reason = f"被{player.name}夺舍，原神魂不复存在"
                game.encounter_npc_cache = [
                    row for row in game.encounter_npc_cache
                    if str(row.get("id")) != str(target.get("npc_id") or target.get("id", ""))
                ]
                result, summary = "possessed", f"你以本魂压过{name}，成功夺取肉身（成功率 {chance:.0%}）；原 NPC 永久退场。"
            else:
                self._die(game, f"夺舍{name}失败，神魂遭宿主反噬而灭", "SYS_POSSESSION_FAILED")
                result, summary = "dead", f"夺舍{name}失败，魂飞魄散（成功率 {chance:.0%}）。"
        elif action == "release":
            if disciple:
                raise ValueError("弟子不能通过俘虏释放")
            player.prisoners.remove(target)
            self._restore_captive_npc(game, target, affinity_gain=10)
            result, summary = "released", f"你解开禁制释放{name}，其好感有所回升。"
        elif action == "torture":
            if disciple:
                raise ValueError("弟子不能作为俘虏拷打")
            target["affinity"] = float(target.get("affinity", 0)) - 12
            player.fame += 2
            result, summary = "tortured", f"你拷打{name}逼问情报；好感 -12，威名 +2。"
        else:
            result, summary = self._convert_to_puppet(game, target, action, rng, bool(disciple))

        game.history.append(HistoryRecord(
            "SYS_CAPTIVE_ACTION", 1, player.age, "俘虏处置", action, result, summary,
            {"target_id": target_id, "action": action}, ["system", "captive", "puppet"],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def _restore_captive_npc(self, game: GameState, target: dict[str, Any], affinity_gain: float) -> None:
        npc = self._find_npc(game, str(target.get("npc_id", "")))
        if npc:
            npc.alive = True
            npc.death_reason = None
            npc.affinity = float(target.get("affinity", 0)) + affinity_gain

    def _convert_to_puppet(
        self, game: GameState, target: dict[str, Any], kind: str, rng: random.Random, disciple: bool,
    ) -> tuple[str, str]:
        player = game.player
        rules = self._demonic_rules()
        target_power = float(target.get("combat_power", max(1.0, combat_power(player) * 0.4)))
        realm_gap = player.realm_index - int(target.get("realm_index", 0))
        power_ratio = combat_power(player) / max(1.0, target_power)
        affinity = float(target.get("affinity", 0))
        if kind == "corpse":
            chance = float(rules["corpse_success_base"]) + realm_gap * 0.07 + math.log2(max(0.25, power_ratio)) * 0.06
        else:
            chance = float(rules["living_success_base"]) + realm_gap * 0.06 + math.log2(max(0.25, power_ratio)) * 0.05 + affinity / 300
        chance = max(0.05, min(0.95, chance))
        if rng.random() >= chance:
            target["affinity"] = affinity - 15
            if kind == "corpse":
                npc = self._find_npc(game, str(target.get("npc_id") or target.get("id", "")))
                if npc:
                    npc.alive = False
                    npc.death_reason = f"被{player.name}炼尸失败，形神俱灭"
                self._remove_conversion_target(player, target, disciple)
                return "destroyed", f"你炼制{target['name']}失败，其形神俱灭（成功率 {chance:.0%}）。"
            return "resisted", f"{target['name']}挣脱了活傀标记，好感 -15（成功率 {chance:.0%}）。"

        inherited = float(rules["corpse_power_inheritance"] if kind == "corpse" else rules["living_power_inheritance"])
        technique_id = (
            player.technique.id if kind == "corpse" and player.technique
            else target.get("main_technique_id")
        )
        control = 100.0 if kind == "corpse" else max(15.0, min(92.0, 48 + affinity * 0.28 + realm_gap * 6))
        puppet = {
            "id": f"puppet_{uuid.uuid4().hex[:12]}", "name": str(target["name"]), "type": kind,
            "type_name": PUPPET_NAMES[kind], "realm_index": int(target.get("realm_index", 0)),
            "layer": int(target.get("layer", 1)), "combat_power": round(target_power * inherited, 1),
            "original_power": round(target_power, 1), "main_technique_id": technique_id,
            "control": round(control, 1), "cultivation_progress": 0.0, "breakthrough_bonus": 0.0,
            "created_age": player.age, "last_infusion_age": None, "alive": True,
            "source": str(target.get("source", "combat")),
        }
        player.puppets.append(puppet)
        source = str(target.get("source", ""))
        if kind == "corpse" and source == "relationship:companion":
            player.milestones["companion_turned_corpse"] = 1
        elif kind == "corpse" and source == "relationship:master":
            player.milestones["master_turned_corpse"] = 1
        npc = self._find_npc(game, str(target.get("npc_id") or target.get("id", "")))
        if npc:
            npc.alive = False
            npc.death_reason = f"被{player.name}炼为{PUPPET_NAMES[kind]}"
        self._remove_conversion_target(player, target, disciple)
        return "created", f"{target['name']}已被炼成{PUPPET_NAMES[kind]}，继承 {inherited:.0%} 战力（成功率 {chance:.0%}）。"

    @staticmethod
    def _remove_conversion_target(player: Player, target: dict[str, Any], disciple: bool) -> None:
        if disciple:
            player.disciples = [entry for entry in player.disciples if entry is not target]
        else:
            player.prisoners = [entry for entry in player.prisoners if entry is not target]

    def craft_mechanical_puppet(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not player.alive or game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法合成机关傀儡")
        if len(player.puppets) >= puppet_capacity(player):
            raise ValueError("神识可控傀儡数量已经达到上限")
        recipe = self._demonic_rules()["mechanical_recipe"]
        if any(not has_item(player, item_id, int(quantity)) for item_id, quantity in recipe.items()):
            raise ValueError("机关傀儡需要下品灵石 ×25 与青锋灵剑 ×1")
        for item_id, quantity in recipe.items():
            remove_item(player, item_id, int(quantity))
        power = max(20.0, combat_power(player) * 0.35)
        player.puppets.append({
            "id": f"puppet_{uuid.uuid4().hex[:12]}", "name": "玄铁机关傀儡", "type": "mechanical",
            "type_name": PUPPET_NAMES["mechanical"], "realm_index": max(1, player.realm_index - 1), "layer": 1,
            "combat_power": round(power, 1), "original_power": round(power, 1), "main_technique_id": None,
            "control": 100.0, "cultivation_progress": 0.0, "breakthrough_bonus": 0.0,
            "created_age": player.age, "last_infusion_age": None, "alive": True,
        })
        self._grant_art_experience(player, "refining", 20)
        self._grant_art_experience(player, "formation", 8)
        self._grant_art_experience(player, "spirit_control", 10)
        game.history.append(HistoryRecord(
            "SYS_MECHANICAL_PUPPET", 1, player.age, "机关合傀", None, "created",
            "你以二十五枚灵石驱动阵心、熔入青锋灵剑，制成一具玄铁机关傀儡。",
            {"recipe": recipe}, ["system", "puppet", "craft"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def puppet_action(
        self, game_id: str, puppet_id: str, action: str, content_id: str = "",
    ) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not player.alive or game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法培养傀儡")
        puppet = next((entry for entry in player.puppets if str(entry.get("id")) == puppet_id), None)
        if not puppet:
            raise ValueError("目标傀儡不存在")
        rng = decode_rng(game.seed, game.rng_state)
        if action == "infuse":
            summary = self._infuse_puppet(game, puppet, rng)
            result = "infused"
        elif action == "pill":
            item = ITEM_CATALOG.get(content_id)
            if not item or "pill" not in item.tags or not remove_item(player, content_id):
                raise ValueError("需要选择并持有一枚丹药")
            gain = float(self._demonic_rules()["pill_breakthrough_bonus"])
            puppet["breakthrough_bonus"] = min(0.35, float(puppet.get("breakthrough_bonus", 0)) + gain)
            result, summary = "pill_fed", f"你赐予{puppet['name']}{item.name}，其下次突破率 +{gain:.0%}。"
        elif action == "technique":
            if puppet.get("type") != "living":
                raise ValueError("只有活傀能够更换功法")
            technique = next((entry for entry in player.known_techniques if entry.id == content_id), None)
            if not technique or technique.category != "spiritual":
                raise ValueError("需要选择已掌握的修仙功法")
            puppet["main_technique_id"] = technique.id
            puppet["combat_power"] = round(float(puppet["combat_power"]) + technique.combat_bonus * 0.10, 1)
            result, summary = "technique_changed", f"你令{puppet['name']}改修《{technique.name}》，其战斗力有所提高。"
        elif action == "reinforce_control":
            if player.path != "demonic" or puppet.get("type") != "living":
                raise ValueError("只有魔修能够加固活傀印记")
            rules = self._demonic_rules()
            mp_cost = max(1.0, max_mp(player) * float(rules["control_reinforce_mp_ratio"]))
            if player.mp < mp_cost:
                raise ValueError("当前 MP 不足以加固活傀印记")
            before = float(puppet.get("control", 0))
            gain = float(rules["control_reinforce_base"]) * (1 + max(0, divine_sense_level(player) - 1) * 0.03)
            player.mp -= mp_cost
            puppet["control"] = round(min(100.0, before + gain), 1)
            self._grant_art_experience(player, "spirit_control", 8)
            actual_gain = puppet["control"] - before
            result, summary = (
                "control_reinforced",
                f"你消耗 {mp_cost:.0f} MP 重炼傀印，{puppet['name']}的控制度 +{actual_gain:.1f}。",
            )
        elif action == "devour":
            if player.path != "demonic" or puppet.get("type") == "mechanical":
                raise ValueError("只有魔修能够吞噬炼尸或活傀")
            result, summary = self._devour_puppet(game, puppet)
        elif action == "dismiss":
            player.puppets.remove(puppet)
            result, summary = "dismissed", f"你解除了对{puppet['name']}的控制。"
        else:
            raise ValueError("未知傀儡操作")
        game.history.append(HistoryRecord(
            "SYS_PUPPET_ACTION", 1, player.age, "傀儡术", action, result, summary,
            {"puppet_id": puppet_id, "action": action}, ["system", "puppet", action],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def _infuse_puppet(self, game: GameState, puppet: dict[str, Any], rng: random.Random) -> str:
        player = game.player
        if puppet.get("type") == "mechanical":
            raise ValueError("机关傀儡不能通过灌注气修炼")
        if puppet.get("last_infusion_age") == player.age:
            raise ValueError("本行动年份已经为该傀儡灌注过气")
        mp_cost = max(1.0, max_mp(player) * float(self._demonic_rules()["infusion_mp_ratio"]))
        if player.mp < mp_cost:
            raise ValueError("当前 MP 不足以完成灌注")
        technique = self._puppet_technique(puppet.get("main_technique_id")) or player.technique
        if not technique:
            raise ValueError("该傀儡没有可承载灌注的主修功法")
        regional = self.maps.qi_gain_efficiencies(player.world, player.location_id)
        source_efficiency = sum(float(weight) * float(regional.get(source, 0)) for source, weight in technique.sources.items())
        gain = float(self._demonic_rules()["infusion_base"]) * source_efficiency * (1 + technique.grade * 0.08)
        player.mp -= mp_cost
        self._grant_art_experience(player, "spirit_control", 6)
        puppet["last_infusion_age"] = player.age
        puppet["cultivation_progress"] = float(puppet.get("cultivation_progress", 0)) + gain
        realm_gap = player.realm_index - int(puppet.get("realm_index", 0))
        power_chance = 1.0 if realm_gap > 0 else 0.65 if realm_gap == 0 else 0.35
        power_increased = power_chance >= 1.0 or rng.random() < power_chance
        if power_increased:
            puppet["combat_power"] = round(float(puppet["combat_power"]) * (1 + min(0.08, gain / 1200)), 1)
        breakthrough = self._try_puppet_breakthrough(puppet, rng)
        power_text = (
            "境界压制使本次战力稳定增长"
            if realm_gap > 0 else
            f"本次战力增长成功（概率 {power_chance:.0%}）"
            if power_increased else f"本次仅稳固修为，未转化为战力（增长概率 {power_chance:.0%}）"
        )
        return f"你按《{technique.name}》的{','.join(technique.sources)}源路灌注，培养进度 +{gain:.1f}，MP -{mp_cost:.0f}；{power_text}。{breakthrough}"

    def _try_puppet_breakthrough(self, puppet: dict[str, Any], rng: random.Random) -> str:
        kind = str(puppet.get("type"))
        if kind == "mechanical" or int(puppet.get("realm_index", 0)) >= len(REALMS) - 1:
            return ""
        required = REALMS[int(puppet["realm_index"])].opportunity_base * 0.35
        if float(puppet.get("cultivation_progress", 0)) < required:
            return ""
        base = float(self._demonic_rules()["puppet_breakthrough_base"][kind])
        chance = min(0.90, base + float(puppet.get("breakthrough_bonus", 0)))
        puppet["breakthrough_bonus"] = 0.0
        if rng.random() >= chance:
            puppet["cultivation_progress"] = required * 0.5
            return f"冲关失败（成功率 {chance:.0%}），保留一半积累。"
        puppet["cultivation_progress"] = 0.0
        if int(puppet.get("layer", 1)) >= REALMS[int(puppet["realm_index"])].layers:
            puppet["realm_index"] = int(puppet["realm_index"]) + 1
            puppet["layer"] = 1
        else:
            puppet["layer"] = int(puppet.get("layer", 1)) + 1
        puppet["combat_power"] = round(float(puppet["combat_power"]) * 1.18, 1)
        if kind == "living":
            puppet["control"] = max(0.0, float(puppet.get("control", 100)) - 8)
        return f"傀儡冲关成功（成功率 {chance:.0%}）。"

    def _devour_puppet(self, game: GameState, puppet: dict[str, Any]) -> tuple[str, str]:
        player = game.player
        kind = str(puppet["type"])
        per_realm = float(self._demonic_rules()["devour_bonus_per_realm"][kind])
        potential = per_realm * max(1, int(puppet.get("realm_index", 0))) * (
            1 + min(1.0, float(puppet.get("combat_power", 0)) / max(1.0, combat_power(player))) * 0.3
        )
        # 吞噬本身的总突破潜力提高 5 个百分点；仍按四成即时、六成炼化后
        # 归己，保持“吞噬后必须处理外来元神”的风险闭环。
        potential += float(self._demonic_rules().get("devour_bonus_flat_increase", 0.05))
        immediate = potential * 0.4
        maximum = float(self._demonic_rules()["max_devour_bonus"])
        player.devouring_breakthrough_bonus = min(maximum, player.devouring_breakthrough_bonus + immediate)
        player.foreign_souls.append({
            "id": f"soul_{uuid.uuid4().hex[:12]}", "name": str(puppet["name"]),
            "realm_index": int(puppet.get("realm_index", 0)), "strength": round(max(0.5, potential * 30), 2),
            "combat_power": round(float(puppet.get("combat_power", 0)), 1),
            "progress": 0.0, "required": 100.0, "remaining_bonus": round(potential - immediate, 4),
            "refined": False, "last_refine_age": None,
        })
        player.puppets.remove(puppet)
        return "devoured", f"你吞噬{puppet['name']}，突破率暂增 {immediate:.1%}；其外来元神仍须炼化。"

    def refine_foreign_souls(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if player.path != "demonic":
            raise ValueError("只有魔修能够炼化外来元神")
        soul = next((entry for entry in player.foreign_souls if not entry.get("refined")), None)
        if not soul:
            raise ValueError("当前没有尚未炼化的外来元神")
        if soul.get("last_refine_age") == player.age:
            raise ValueError("本行动年份已经炼化过该元神")
        cost = max(1.0, REALMS[player.realm_index].opportunity_base * 0.04)
        if player.opportunity < cost or player.mp < max_mp(player) * 0.10:
            raise ValueError("炼化元神需要足够机缘与 MP")
        gain = self._soul_refine_gain(player)
        player.opportunity -= cost
        player.mp -= max_mp(player) * 0.10
        soul["progress"] = min(float(soul["required"]), float(soul.get("progress", 0)) + gain)
        soul["last_refine_age"] = player.age
        completed = soul["progress"] >= soul["required"]
        if completed:
            self._complete_soul_refinement(player, soul)
        summary = (
            f"你彻底炼化了{soul['name']}的外来元神，剩余突破潜力已经归己。"
            if completed else f"你消耗 {cost:.0f} 机缘炼化{soul['name']}的外来元神，进度 +{gain:.1f}。"
        )
        game.history.append(HistoryRecord(
            "SYS_SOUL_REFINING", 1, player.age, "炼化元神", soul["id"], "completed" if completed else "progress", summary,
            {"soul_id": soul["id"], "progress": soul["progress"]}, ["system", "demonic", "soul"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def secluded_refine_foreign_souls(self, game_id: str) -> dict[str, Any]:
        """以正常炼魂效率的 1/1.2 逐年闭关，免除主动炼化的机缘与 MP 消耗。"""
        game = self._load(game_id)
        player = game.player
        if player.path != "demonic":
            raise ValueError("只有魔修能够闭关炼化外来元神")
        if not player.alive:
            raise ValueError("此生已经结束")
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        if player.imprisonment:
            raise ValueError("身陷大牢时无法闭关炼魂")
        souls = [entry for entry in player.foreign_souls if not entry.get("refined")]
        if not souls:
            raise ValueError("当前没有尚未炼化的外来元神")

        planned_years = self._secluded_refining_years(player)
        time_multiplier = float(self._demonic_rules().get("soul_seclusion_time_multiplier", 1.2))
        yearly_progress = self._soul_refine_gain(player) / max(1.0, time_multiplier)
        rng = decode_rng(game.seed, game.rng_state)
        start_age = player.age
        era_news: list[str] = []
        completed_count = 0
        for _ in range(planned_years):
            advance_player_age(player)
            if not self._advance_world_year(game, rng, era_news, encounters=False):
                break
            budget = yearly_progress
            for soul in souls:
                if soul.get("refined") or budget <= 0:
                    continue
                remaining = max(0.0, float(soul["required"]) - float(soul.get("progress", 0)))
                applied = min(remaining, budget)
                soul["progress"] = float(soul.get("progress", 0)) + applied
                soul["last_refine_age"] = player.age
                budget -= applied
                if soul["progress"] >= float(soul["required"]):
                    self._complete_soul_refinement(player, soul)
                    completed_count += 1
            if all(entry.get("refined") for entry in souls):
                break

        elapsed_years = player.age - start_age
        fully_completed = all(entry.get("refined") for entry in souls)
        result = "completed" if fully_completed else "dead" if not player.alive else "interrupted"
        summary = (
            f"你闭关 {elapsed_years} 年，将 {completed_count} 道外来元神尽数炼化；全程未消耗机缘与 MP，"
            f"耗时按正常炼化的 {time_multiplier:.0%} 计算。"
            if fully_completed else
            f"闭关炼魂在第 {elapsed_years} 年中断，已炼化 {completed_count}/{len(souls)} 道元神；期间未消耗机缘与 MP。"
        )
        game.history.append(HistoryRecord(
            "SYS_SOUL_SECLUDED_REFINING", 1, player.age, "闭关炼化", None, result, summary,
            {"age":[start_age, player.age], "souls_refined":completed_count, "souls_total":len(souls)},
            ["system", "demonic", "soul", "seclusion"],
        ))
        if elapsed_years >= 5:
            self._record_era_summary(game, start_age, era_news)
        self._ensure_market(game, rng)
        self._compact_world_history(game)
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def _soul_refine_gain(self, player: Player) -> float:
        technique = player.divine_sense_technique
        multiplier = (
            (1 + technique.divine_sense_bonus * technique_scale(technique))
            * technique_environment_multiplier(technique, player.world)
            if technique else 0.5
        )
        return float(self._demonic_rules()["soul_refine_progress"]) * multiplier

    def _secluded_refining_years(self, player: Player) -> int:
        remaining = sum(
            max(0.0, float(entry.get("required", 100)) - float(entry.get("progress", 0)))
            for entry in player.foreign_souls if not entry.get("refined")
        )
        if remaining <= 0:
            return 0
        time_multiplier = float(self._demonic_rules().get("soul_seclusion_time_multiplier", 1.2))
        return max(1, math.ceil(remaining * time_multiplier / max(0.01, self._soul_refine_gain(player))))

    def _complete_soul_refinement(self, player: Player, soul: dict[str, Any]) -> None:
        if soul.get("refined"):
            return
        soul["progress"] = float(soul.get("required", 100))
        soul["refined"] = True
        maximum = float(self._demonic_rules()["max_devour_bonus"])
        player.devouring_breakthrough_bonus = min(
            maximum, player.devouring_breakthrough_bonus + float(soul.get("remaining_bonus", 0)),
        )

    def _annual_demonic_update(self, game: GameState, rng: random.Random) -> None:
        player = game.player
        rules = self._demonic_rules()
        for puppet in player.puppets:
            kind = str(puppet.get("type"))
            if kind in {"corpse", "living"}:
                contribution = max(0.1, int(puppet.get("realm_index", 0)) * (0.16 if kind == "corpse" else 0.34))
                self._add_opportunity(player, contribution)
        for puppet in list(player.puppets):
            if puppet.get("type") != "living":
                continue
            growth = 1 + int(puppet.get("realm_index", 0)) * 0.12
            puppet["control"] = max(0.0, float(puppet.get("control", 100)) - float(rules["living_control_loss_per_year"]) * growth)
            if puppet["control"] >= 25:
                continue
            chance = (25 - puppet["control"]) / 100 * 0.18
            if rng.random() >= chance:
                continue
            player.puppets.remove(puppet)
            ratio = float(puppet.get("combat_power", 0)) / max(1.0, combat_power(player))
            if ratio > 1.15 and rng.random() < min(0.85, 0.35 + (ratio - 1) * 0.25):
                damage = max_hp(player) * min(0.9, 0.35 + ratio * 0.12)
                player.hp = max(0.0, player.hp - damage)
                if player.hp <= 0:
                    self._die(game, f"活傀{puppet['name']}挣脱控制后反杀主人", "SYS_LIVING_PUPPET_REVOLT")
                    return
                outcome = f"反噬令你损失 {damage:.0f} HP"
            else:
                outcome = "其未能反杀你，趁乱遁走"
            game.history.append(HistoryRecord(
                "SYS_LIVING_PUPPET_REVOLT", 1, player.age, "活傀反噬", puppet["id"], "escaped",
                f"{puppet['name']}的控制度降至临界点，挣脱印记；{outcome}。",
                {"puppet_id": puppet["id"], "control": puppet["control"]}, ["system", "puppet", "negative"],
            ))

        unrefined = [entry for entry in player.foreign_souls if not entry.get("refined")]
        if not unrefined:
            return
        burden = sum(float(entry.get("strength", 1)) for entry in unrefined)
        chance = min(0.65, float(rules["soul_backlash_base"]) * burden)
        if rng.random() < chance:
            damage = max_hp(player) * min(0.6, 0.06 + burden * 0.018)
            player.hp = max(0.0, player.hp - damage)
            player.heart_demon += self._sage_scaled_gain(
                player, burden * 0.5, "heart_demon_gain_reduction",
            )
            game.history.append(HistoryRecord(
                "SYS_SOUL_BACKLASH", 1, player.age, "元神反噬", None, "backlash",
                f"{len(unrefined)}道未炼化元神同时反扑，HP -{damage:.0f}，心魔 +{burden * 0.5:.1f}。",
                {"souls": len(unrefined), "burden": burden}, ["system", "demonic", "soul", "negative"],
            ))
            if player.hp <= 0:
                self._die(game, "吞噬的外来元神反客为主，撕碎识海", "SYS_SOUL_BACKLASH_DEATH")

    def _public_demonic_system(self, player: Player) -> dict[str, Any]:
        pill_ids = [item.id for item in player.inventory if "pill" in item.tags and item.quantity > 0]
        techniques = [
            {"id": entry.id, "name": entry.name}
            for entry in player.known_techniques if entry.category == "spiritual"
        ]
        puppets = []
        for entry in player.puppets:
            technique = self._puppet_technique(entry.get("main_technique_id"))
            kind = str(entry.get("type"))
            contribution_ratio = float(
                self._demonic_rules()["puppet_combat_contribution"].get(kind, 0)
            )
            condition = (
                max(0.0, min(1.0, float(entry.get("durability", 100.0)) / 100.0))
                if kind == "mechanical" else
                max(0.0, min(1.0, float(entry.get("corpse_integrity", 100.0)) / 100.0))
                if kind == "corpse" else 1.0
            )
            contribution_mode = "队伍战力" if entry.get("type") == "living" else "本体战力"
            puppets.append(copy.deepcopy(entry) | {
                "type_name": PUPPET_NAMES.get(str(entry.get("type")), str(entry.get("type"))),
                "realm_name": self._npc_realm_name(SectNpc(
                    "", "", "", int(entry.get("realm_index", 0)), int(entry.get("layer", 1)), 0, 1,
                    path="demonic" if entry.get("type") == "corpse" else "dao",
                )),
                "main_technique_name": technique.name if technique else "无",
                "battle_contribution_ratio": contribution_ratio,
                "battle_contribution": round(float(entry.get("combat_power", 0)) * contribution_ratio * condition, 1),
                "battle_contribution_mode": contribution_mode,
                "annual_opportunity": (
                    max(0.1, int(entry.get("realm_index", 0)) * (0.16 if entry.get("type") == "corpse" else 0.34))
                    if entry.get("type") in {"corpse", "living"} else 0.0
                ),
            })
        ascension_required = int(self._demonic_rules()["true_demon_ascension_demon_qi_level"])
        ascension_current = qi_level(player.qi_experience.get("demon", 0.0))
        ascension_available = bool(
            player.path == "demonic" and player.alive and not player.sealed_cultivation and (
                (player.world == "human" and player.realm_index == 5 and player.layer >= 3)
                or (player.world == "demon" and player.realm_index == 5 and player.layer >= 1)
            )
        )
        from .possession_system import can_possess
        prisoners = []
        for entry in player.prisoners:
            allowed, reason = can_possess(player, entry)
            gender = str(entry.get("gender") or self._stable_gender(str(entry.get("id", ""))))
            prisoners.append(copy.deepcopy(entry) | {
                "gender": gender, "gender_name": "女" if gender == "female" else "男",
                "can_possess": allowed, "possession_reason": reason,
                "can_recruit_concubine": gender == "female",
            })
        return {
            "is_demonic": player.path == "demonic", "capacity": puppet_capacity(player),
            "used": len(player.puppets), "prisoners": prisoners, "puppets": puppets,
            "foreign_souls": copy.deepcopy(player.foreign_souls),
            "secluded_refine_years": self._secluded_refining_years(player),
            "secluded_refine_multiplier": float(self._demonic_rules().get("soul_seclusion_time_multiplier", 1.2)),
            "breakthrough_bonus": round(player.devouring_breakthrough_bonus, 4),
            "pill_options": [{"id": item_id, "name": ITEM_CATALOG[item_id].name} for item_id in pill_ids],
            "technique_options": techniques,
            "mechanical_recipe": copy.deepcopy(self._demonic_rules()["mechanical_recipe"]),
            "control_mp_cost": round(max_mp(player) * float(self._demonic_rules()["control_reinforce_mp_ratio"]), 1),
            "true_demon_ascension": {
                "required_demon_qi_level": ascension_required,
                "current_demon_qi_level": ascension_current,
                "satisfied": ascension_current >= ascension_required,
                "available": ascension_available,
            },
            "time_behavior": "年度机缘、控制衰减与反噬按行动年数逐年结算；普通炼魂为即时操作，闭关炼化则会实际推进所示年月。",
        }

    @classmethod
    def _puppet_intrinsic_contribution(cls, player: Player) -> float:
        """机关与炼尸直接强化玩家本体，因而可以参与剧情的个人战力判定。"""
        weights = cls._demonic_rules()["puppet_combat_contribution"]
        total = 0.0
        for entry in player.puppets:
            kind = str(entry.get("type"))
            if not entry.get("alive", True) or kind not in {"mechanical", "corpse"}:
                continue
            field = "durability" if kind == "mechanical" else "corpse_integrity"
            integrity = max(0.0, min(1.0, float(entry.get(field, 100.0)) / 100.0))
            total += float(entry.get("combat_power", 0)) * float(weights.get(kind, 0)) * integrity
        return round(total, 1)

    @classmethod
    def _living_puppet_party_powers(cls, player: Player) -> list[float]:
        ratio = float(cls._demonic_rules()["puppet_combat_contribution"]["living"])
        return [
            round(float(entry.get("combat_power", 0)) * ratio, 1)
            for entry in player.puppets if entry.get("alive", True) and entry.get("type") == "living"
        ]

    def _player_intrinsic_combat_power(self, player: Player) -> float:
        return round(combat_power(player) + self._puppet_intrinsic_contribution(player), 1)

    def _player_battle_power(self, game: GameState) -> float:
        companions = [entry["combat_power"] for entry in self._public_party(game)]
        members = sorted([*companions, *self._living_puppet_party_powers(game.player)], reverse=True)
        return party_combat_power(self._player_intrinsic_combat_power(game.player), members)

    def _grant_demonic_kill_opportunity(self, player: Player, victim_realm_index: int) -> float:
        if player.path != "demonic":
            return 0.0
        rules = self._demonic_rules()
        gain = float(rules["kill_opportunity_base"]) + max(0, int(victim_realm_index)) * float(
            rules["kill_opportunity_per_realm"]
        )
        self._add_opportunity(player, gain)
        return gain

    @staticmethod
    def _raise_divine_sense_one_level(player: Player) -> None:
        player.divine_sense_rank = divine_sense_level(player) + 1

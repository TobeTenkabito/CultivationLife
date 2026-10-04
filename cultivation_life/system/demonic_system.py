from __future__ import annotations

from ..npc_custody import settle_puppet_person

from .demonic_definitions import PUPPET_NAMES as PUPPET_NAMES

from .semantic_events import emit

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


class DemonicSystemMixin:
    """傀儡与炼魂的局部规则、培养操作及展示；身份和年度流程独立装配。"""

    @staticmethod
    def _demonic_rules() -> dict[str, Any]:
        return WORLD_SYSTEMS["demonic_cultivation"]

    @staticmethod
    def _puppet_technique(technique_id: str | None):
        return TECHNIQUE_CATALOG.get(str(technique_id or ""))


    def preview_puppet(self, game_id, form, core, shell, energy):
        from .puppet_crafting import preview
        return preview(self._load(game_id).player, form, core, shell, energy)

    def craft_mechanical_puppet(self, game_id, form='', core='', shell='', energy=''):
        from .puppet_crafting import preview
        game = self._load(game_id)
        player = game.player
        if (not player.alive or game.pending_event or player.imprisonment or game.active_trial
                or player.sealed_cultivation or player.cultivation_suppression or player.ghost_captor
                or (game.guixu_state.get('player_session') or {}).get('trapped')):
            raise ValueError("当前状态无法合成机关傀儡")
        result = preview(player, form, core, shell, energy)
        if not result['can_craft']:
            raise ValueError(result['reason'])
        # Quote validates ownership and distinct roles before consuming any component.
        for component in result['components']:
            remove_item(player, component['id'], 1)
        puppet = {k:v for k,v in result.items() if k not in {'can_craft','reason'}}
        puppet.update(id=f"puppet_{uuid.uuid4().hex[:12]}", type='mechanical',type_name='机关傀儡',
                      main_technique_id=None,control=100.,cultivation_progress=0.,breakthrough_bonus=0.,
                      created_age=player.age,alive=True,durability=100.,path=player.path)
        player.puppets.append(puppet)
        self._grant_art_experience(player, 'refining', 20)
        self._grant_art_experience(player, 'formation', 8)
        self._grant_art_experience(player, 'spirit_control', 10)
        summary=(f"你以{ '、'.join(c['name'] for c in result['components']) }各一份打造{puppet['name']}，"
                 f"成品战力 {puppet['combat_power']:g}，普通炼体 {puppet['body_training']}/100层，"
                 f"高阶肉身 {puppet['immortal_body_level']}层，神识 {puppet['divine_sense_rank']}阶。")
        game.history.append(HistoryRecord('SYS_MECHANICAL_PUPPET',1,player.age,'机关合傀',form,'created',
            summary,{'components':[c['id'] for c in result['components']]},['system','puppet','craft']))
        game.updated_at=now_iso()
        self.store.save(game)
        return self.present(game)

    def train_owned(self, game_id: str, target_id: str, kind: str, axis: str, batches: int = 1):
        from .owned_training import quote
        game = self._load(game_id)
        p = game.player
        if (not p.alive or game.pending_event or p.imprisonment or p.sealed_cultivation
                or p.ghost_captor or p.cultivation_suppression or game.active_trial
                or (game.guixu_state.get('player_session') or {}).get('trapped')):
            raise ValueError("当前状态无法培养")
        if kind not in {"prisoner", "puppet"}:
            raise ValueError("培养对象类型无效")
        entries = p.prisoners if kind == "prisoner" else p.puppets
        target = next((x for x in entries if str(x.get("id")) == target_id and x.get("alive", True)), None)
        if not target:
            raise ValueError("培养对象不存在")
        plan = quote(p, target, axis, batches)
        if not plan['can_train']:
            raise ValueError(plan['reason'])
        p.opportunity -= plan['opportunity']
        p.mp -= plan['mp']
        target.update(plan['result'])
        summary = (f"为{target['name']}{plan['label']} {plan['rounds']}轮：{plan['before']} → {plan['after']}；"
                   f"机缘 -{plan['opportunity']:g}，法力 -{plan['mp']:g}。")
        game.history.append(HistoryRecord('SYS_OWNED_TRAINING', 1, p.age, '培养', axis, 'trained',
                                         summary, {'target_id': target_id, 'rounds': plan['rounds']},
                                         ['system', 'training', kind]))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def puppet_action(
        self, game_id: str, puppet_id: str, action: str, content_id: str = "",
    ) -> dict[str, Any]:
        if action == "infuse":
            return self.train_owned(game_id, puppet_id, "puppet", "cultivation", 1)
        game = self._load(game_id)
        player = game.player
        if not player.alive or game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法培养傀儡")
        puppet = next((entry for entry in player.puppets if str(entry.get("id")) == puppet_id), None)
        if not puppet:
            raise ValueError("目标傀儡不存在")
        rng = decode_rng(game.seed, game.rng_state)
        if action == "pill":
            item = ITEM_CATALOG.get(content_id)
            if not item or "pill" not in item.tags or not remove_item(player, content_id):
                raise ValueError("需要选择并持有一枚丹药")
            gain = float(self._demonic_rules()["pill_breakthrough_bonus"])
            puppet["breakthrough_bonus"] = min(0.35, float(puppet.get("breakthrough_bonus", 0)) + gain)
            result, summary = "pill_fed", f"你赐予{puppet['name']}{item.name}，其下次批量培养机缘费用减免 +{gain:.0%}（最多35%）。"
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
            settle_puppet_person(game, puppet, outcome="released")
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
        settle_puppet_person(game, puppet, outcome="dead", reason="被吞噬元神")
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


    def _soul_refine_gain(self, player: Player) -> float:
        technique = player.divine_sense_technique
        multiplier = (
            (1 + technique.divine_sense_bonus * technique_scale(technique, "divine_sense_bonus"))
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


    def _public_demonic_system(self, player: Player) -> dict[str, Any]:
        from .demonic.soul_risk import refinement_risk
        from .owned_training import public as training_public
        from .puppet_crafting import public as crafting_public
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
                "training": training_public(player, entry),
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
            player.path == "demonic" and player.alive and not player.sealed_cultivation and not player.cultivation_suppression and (
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
                "training": training_public(player, entry),
                "gender": gender, "gender_name": "女" if gender == "female" else "男",
                "can_possess": allowed, "possession_reason": reason,
                "can_recruit_concubine": gender == "female",
            })
        return {
            "is_demonic": player.path == "demonic", "capacity": puppet_capacity(player),
            "used": len(player.puppets), "prisoners": prisoners, "puppets": puppets,
            "foreign_souls": copy.deepcopy(player.foreign_souls),
            "soul_refinement_risk": refinement_risk(player, self._demonic_rules()),
            "secluded_refine_years": self._secluded_refining_years(player),
            "secluded_refine_multiplier": float(self._demonic_rules().get("soul_seclusion_time_multiplier", 1.2)),
            "breakthrough_bonus": round(player.devouring_breakthrough_bonus, 4),
            "pill_options": [{"id": item_id, "name": ITEM_CATALOG[item_id].name} for item_id in pill_ids],
            "technique_options": techniques,
            "puppet_crafting": crafting_public(player),
            "control_mp_cost": round(max_mp(player) * float(self._demonic_rules()["control_reinforce_mp_ratio"]), 1),
            "true_demon_ascension": {
                "required_demon_qi_level": ascension_required,
                "current_demon_qi_level": ascension_current,
                "satisfied": ascension_current >= ascension_required,
                "available": ascension_available,
            },
            "time_behavior": "年度机缘、控制衰减与反噬按行动年数逐年结算；培养按资源即时投入，无每年次数限制；每轮修为提升1—3层、普通炼体10层（高阶肉身2层）、神识8阶，最高不超过玩家对应能力。可选1/5/10轮，到上限自动停止且只收实际轮数费用。闭关炼化会实际推进年月。",
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
        from .cultivation_ranks import rank_for
        player.divine_sense_rank = max(divine_sense_level(player) + 1, rank_for(player.realm_index, player.layer))

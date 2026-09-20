from __future__ import annotations

import operator
from typing import Any

from .advanced_cultivation import BODY, _body_required
from .character import IDENTITY, LIFE, create_character
from .combat import (
    CONDITION, PRISONER, ResolveCombat, _resolve_handler, combat_snapshot,
)
from .cultivation import CULTIVATION, PRACTICE
from .definitions import GameDefinitions
from .extensions import MONSTER_BLOODLINE
from .relations import relationship_affinity, set_relationship_affinity
from .story import (
    EffectOutcome,
    STORY_STATE,
    StoryEffectRegistry,
    _path_value,
    _treasure_runtime,
)
from .war import WANTED_STATE, _change_hostility
from .world import AscendWorld, LOCATION, _ascend_handler
from ..kernel.bus import SimulationContext
from ..kernel.model import EventScope


_OPS = {
    "eq": operator.eq, "neq": operator.ne, "gt": operator.gt,
    "gte": operator.ge, "lt": operator.lt, "lte": operator.le,
}


def _runtime_target(context: SimulationContext, actor_id: str, pending: dict[str, Any]) -> str:
    runtime = dict(pending.get("runtime", {}))
    for key in ("target_id", "npc_id", "enemy_id", "character_id"):
        value = str(runtime.get(key, ""))
        if value and context.state.entities.exists(value):
            return value
    cultivation = context.state.entities.require(actor_id, CULTIVATION)
    identity = context.state.entities.require(actor_id, IDENTITY)
    location = context.state.entities.require(actor_id, LOCATION)
    life = context.state.entities.require(actor_id, LIFE)
    target_id = create_character(
        context,
        name=str(runtime.get("target_name", runtime.get("npc_name", "因果中人"))),
        age=max(16, context.state.clock.year - int(life["birth_year"])),
        gender="female" if identity.get("gender") == "male" else "male",
        race=str(runtime.get("race", identity.get("race", "human"))),
        spirit_root=str(cultivation["spirit_root"]),
        path=str(cultivation["path"]),
        realm_id=str(cultivation["realm_id"]),
        layer=max(1, int(cultivation["layer"]) - 1),
        world_id=str(location["world_id"]),
        lifespan=None,
    )
    context.state.entities.put(target_id, LOCATION, dict(location))
    return target_id


def _role_target(context: SimulationContext, actor_id: str, role: str) -> str | None:
    if role == "master":
        edge = next(iter(context.state.relations.find(
            target_id=actor_id, kind="master_disciple"
        )), None)
        return edge.source_id if edge else None
    if role == "disciple":
        edge = next(iter(context.state.relations.find(
            source_id=actor_id, kind="master_disciple"
        )), None)
        return edge.target_id if edge else None
    kind = "dao_companion" if role == "companion" else "friend"
    edge = next(iter(context.state.relations.involving(actor_id, kind=kind)), None)
    if edge:
        return edge.target_id if edge.source_id == actor_id else edge.source_id
    return None


def _story_extra(context: SimulationContext, actor_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    story = context.state.entities.require(actor_id, STORY_STATE)
    extra = dict(story.get("legacy_effect_state", {}))
    return story, extra


def _save_extra(
    context: SimulationContext, actor_id: str,
    story: dict[str, Any], extra: dict[str, Any],
) -> None:
    story["legacy_effect_state"] = extra
    context.state.entities.put(actor_id, STORY_STATE, story)


def register_story_compat_effects(
    registry: StoryEffectRegistry, definitions: GameDefinitions,
) -> None:
    """Complete the frozen V1 event vocabulary over canonical V2 state.

    These adapters deliberately call the owning domains for combat, travel and
    inventory mutations.  Only narrative counters without a dedicated V2
    aggregate are stored in ``story.legacy_effect_state``.
    """

    def attribute_check(context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any]) -> EffectOutcome:
        condition = context.state.entities.require(actor_id, CONDITION)
        life = context.state.entities.require(actor_id, LIFE)
        cultivation = context.state.entities.require(actor_id, CULTIVATION)
        snapshot = combat_snapshot(context.state, definitions, actor_id)
        story = context.state.entities.require(actor_id, STORY_STATE)
        attributes = dict(story.get("attributes", {}))
        realm = definitions.realms[definitions.realm_index(str(cultivation["realm_id"]))]
        expected_power = float(realm.base_power) * (
            1 + 0.12 * (int(cultivation["layer"]) - 1)
        )
        values = {
            "combat_power": float(snapshot["power"]),
            "hp": float(snapshot["max_hp"]) * float(condition["hp_ratio"]),
            "mp": float(snapshot["max_mp"]) * float(condition["mp_ratio"]),
            "hp_ratio": float(condition["hp_ratio"]),
            "mp_ratio": float(condition["mp_ratio"]),
            "age": context.state.clock.year - int(life["birth_year"]),
            "realm_index": definitions.realm_index(str(cultivation["realm_id"])),
            "layer": int(cultivation["layer"]),
            "heart_demon": float(cultivation.get("heart_demon", 0)),
            "karma": float(_path_value(
                context.state, actor_id, "player.effective_karma", definitions
            )),
            "sha_qi": float(attributes.get("sha_qi", 0)),
            "fame": float(attributes.get("fame", 0)),
            "combat_ratio": float(snapshot["power"]) / max(1.0, expected_power),
        }
        def check(row: dict[str, Any]) -> bool:
            stat = str(row.get("stat"))
            if stat == "has_item":
                inventory = context.state.entities.require(actor_id, "economy.inventory")
                item_id = str(row.get("item_id", ""))
                available = int(dict(inventory.get("items", {})).get(item_id, 0)) - int(
                    dict(inventory.get("reserved", {})).get(item_id, 0)
                )
                return available >= int(row.get("quantity", 1))
            if stat not in values:
                raise ValueError(f"未知属性判定：{stat}")
            return bool(_OPS.get(str(row.get("op", "gte")), operator.ge)(
                values[stat], row.get("value", 0)
            ))

        passed = all(check(dict(row)) for row in effect.payload.get("checks", []))
        if not passed:
            reason = str(effect.payload.get("failure_reason", "未能通过生死判定，身死道消"))
            context.emit(
                "character.lethal_hazard",
                source="story",
                scope=EventScope.entity(actor_id),
                payload={"entity_id": actor_id, "reason": reason},
            )
            return EffectOutcome("dead", f"判定失败。{reason}。")
        return EffectOutcome(
            "check_success",
            str(effect.payload.get("success_text", "判定成功")),
        )

    def simple_progress(context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any]) -> EffectOutcome:
        kind = effect.kind
        payload = effect.payload
        story, extra = _story_extra(context, actor_id)
        if kind == "acquire_root":
            affinity = str(payload.get("affinity", "wood"))
            cultivation = context.state.entities.require(actor_id, CULTIVATION)
            acquired_id = f"acquired_{affinity}"
            if cultivation.get("spirit_root") == "none" and acquired_id in definitions.roots:
                cultivation["spirit_root"] = acquired_id
            else:
                roots = list(map(str, cultivation.get("additional_roots", [])))
                base_elements = definitions.roots[str(cultivation["spirit_root"])].elements
                if affinity in definitions.affinity_names and affinity not in roots and affinity not in base_elements:
                    roots.append(affinity)
                cultivation["additional_roots"] = roots
            context.state.entities.put(actor_id, CULTIVATION, cultivation)
        elif kind in {"add_body_progress", "body_training"}:
            body = context.state.entities.require(actor_id, BODY)
            if not body.get("technique_id"):
                return EffectOutcome(
                    "no_body_technique",
                    "你没有配置炼体功法，这番苦熬只留下了暗伤。",
                )
            value = payload.get("value", 0)
            if "range" in payload:
                low, high = map(int, payload["range"])
                value = context.rng.randint(low, high)
            maximum = int(definitions.systems["body_cultivation"]["max_layer"])
            if kind == "body_training":
                body["layer"] = min(
                    maximum,
                    max(0, int(body.get("layer", 0)) + int(value)),
                )
                body["progress"] = 0.0
                body["ready"] = False
                condition = context.state.entities.require(actor_id, CONDITION)
                condition["hp_ratio"] = min(
                    1.0, float(condition.get("hp_ratio", 1.0)) + 0.15
                )
                context.state.entities.put(actor_id, CONDITION, condition)
                summary = f"炼体境界提升至 {body['layer']} 层。"
            elif int(body.get("layer", 0)) >= maximum:
                return EffectOutcome("body_training_max", "炼体已达一百层极限。")
            else:
                required = _body_required(
                    definitions, int(body.get("layer", 0))
                )
                body["progress"] = min(
                    required,
                    max(0.0, float(body.get("progress", 0)) + float(value)),
                )
                body["ready"] = float(body["progress"]) >= required
                summary = (
                    f"炼体积累 +{float(value):g}"
                    f"（{body['progress']:.1f}/{required:.1f}）。"
                )
            context.state.entities.put(actor_id, BODY, body)
            return EffectOutcome(None, summary)
        elif kind == "add_random_jinque":
            item_id = context.rng.choice(sorted(
                item_id for item_id in definitions.items if item_id.startswith("jinque_")
            ))
            context.emit(
                "story.effect.inventory.changed", source="story",
                scope=EventScope.entity(actor_id),
                payload={"entity_id": actor_id, "item_id": item_id, "quantity": 1, "reason": "story"},
            )
        elif kind == "advance_immortal_conversion":
            cultivation = context.state.entities.require(actor_id, CULTIVATION)
            location = context.state.entities.require(actor_id, LOCATION)
            expected_stage = int(payload.get("stage", 1))
            current_stage = int(cultivation.get("immortal_conversion_stage", 0))
            if (
                location.get("world_id") != "celestial"
                or bool(cultivation.get("immortal_power_converted"))
            ):
                raise ValueError("当前没有可完成的仙灵力转化")
            if expected_stage != current_stage + 1 or not 1 <= expected_stage <= 5:
                raise ValueError("仙灵力转化次序不符")
            cultivation.update(
                immortal_conversion_stage=expected_stage,
                immortal_conversion_last_year=context.state.clock.year,
                immortal_conversion_checked_units=0,
                immortal_power_converted=expected_stage == 5,
            )
            context.state.entities.put(actor_id, CULTIVATION, cultivation)
            condition = context.state.entities.require(actor_id, CONDITION)
            condition["mp_ratio"] = expected_stage / 5
            if expected_stage == 5:
                condition["hp_ratio"] = 1.0
            context.state.entities.put(actor_id, CONDITION, condition)
            if expected_stage == 5:
                context.emit(
                    "story.effect.technique.learned", source="story",
                    scope=EventScope.entity(actor_id),
                    payload={
                        "entity_id": actor_id,
                        "technique_id": "TECH_CELESTIAL_BREATHING",
                    },
                )
                context.emit(
                    "story.effect.inventory.changed", source="story",
                    scope=EventScope.entity(actor_id),
                    payload={
                        "entity_id": actor_id, "item_id": "immortal_origin_stone",
                        "quantity": 3, "reason": "immortal_conversion",
                    },
                )
        elif kind == "grant_monster_imprint":
            bloodline = context.state.entities.require(actor_id, MONSTER_BLOODLINE)
            imprints = list(map(str, bloodline.get("imprints", [])))
            imprint = str(payload["imprint_id"])
            if imprint not in imprints:
                imprints.append(imprint)
            bloodline["imprints"] = imprints
            context.state.entities.put(actor_id, MONSTER_BLOODLINE, bloodline)
        elif kind in {"mortal_progress", "set_mortal_aspiration", "set_spouse"}:
            mortal = dict(extra.get("mortal", {}))
            if kind == "mortal_progress":
                field = str(payload["field"])
                mortal[field] = int(mortal.get(field, 0)) + int(payload.get("value", 1))
            elif kind == "set_mortal_aspiration":
                mortal["aspiration"] = str(payload["aspiration"])
            else:
                mortal["spouse"] = bool(payload.get("value", True))
            extra["mortal"] = mortal
        elif kind == "technique_level":
            practice = context.state.entities.require(actor_id, PRACTICE)
            technique_id = str(practice.get("main_technique_id", ""))
            levels = dict(practice.get("technique_levels", {}))
            if technique_id:
                base_level = definitions.techniques[technique_id].level
                levels[technique_id] = int(
                    levels.get(technique_id, base_level)
                ) + int(payload.get("value", 1))
            practice["technique_levels"] = levels
            context.state.entities.put(actor_id, PRACTICE, practice)
        elif kind == "add_hostility":
            context.emit(
                "war.hostility.changed",
                source="story",
                scope=EventScope.entity(actor_id),
                payload={
                    "actor_id": actor_id,
                    "kind": str(payload.get("kind", "world")),
                    "entity_id": str(payload.get("entity", "current")),
                    "amount": float(payload.get("value", 0)),
                },
            )
        _save_extra(context, actor_id, story, extra)
        if kind == "advance_immortal_conversion":
            stage = int(payload.get("stage", 1))
            return EffectOutcome(
                "immortal_conversion_completed"
                if stage == 5 else "immortal_conversion_stage",
                (
                    "最后阶段完成，仙灵力条已完整开放；仙界行动与仙家功法现已解锁。"
                    if stage == 5 else
                    f"第 {stage}/5 阶段完成，可用仙灵力上限现为 {stage * 20}%。"
                    "下一阶段需再间隔至少 10 个仙界时间单位。"
                ),
            )
        return EffectOutcome(None, str(payload.get("text", "命途状态已经改变。")))

    def relationship_effect(context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any]) -> EffectOutcome:
        role = str(effect.payload.get("role", "friend"))
        if effect.kind == "relationship_sanction":
            runtime = dict(pending.get("runtime", {}))
            actual_role = str(runtime.get("role", role))
            target_id = str(runtime.get("id", runtime.get("target_id", "")))
            name = str(runtime.get("name", "对方"))
            rules = dict(definitions.systems.get("relationship", {}))
            threshold = float(rules.get("hostile_affinity_threshold", -25))
            mode = str(effect.payload.get("mode", "accept"))

            def active_social_edge() -> Any:
                if actual_role == "master":
                    return next((
                        edge for edge in context.state.relations.find(
                            target_id=actor_id, kind="master_disciple"
                        ) if edge.source_id == target_id
                    ), None)
                if actual_role == "companion":
                    return next((
                        edge for edge in context.state.relations.involving(
                            actor_id, kind="dao_companion"
                        ) if target_id in {edge.source_id, edge.target_id}
                    ), None)
                return None

            def end_social(edge: Any) -> EffectOutcome:
                closed = context.state.relations.end(
                    edge.relation_id, ended_year=context.state.clock.year
                )
                metadata = dict(closed.metadata)
                metadata["end_reason"] = "relationship_sanction"
                context.state.relations.replace_metadata(
                    closed.relation_id, metadata
                )
                for party_edge in list(context.state.relations.find(
                    source_id=actor_id, kind="combat.party_member"
                )):
                    if party_edge.target_id == target_id:
                        context.state.relations.end(
                            party_edge.relation_id,
                            ended_year=context.state.clock.year,
                        )
                set_relationship_affinity(
                    context.state,
                    target_id,
                    actor_id,
                    float(rules.get("relationship_release_affinity", 0)),
                )
                if actual_role == "companion":
                    cultivation = context.state.entities.require(
                        actor_id, CULTIVATION
                    )
                    cultivation["heart_demon"] = max(
                        0.0,
                        float(cultivation.get("heart_demon", 0.0))
                        + float(rules.get(
                            "companion_separation_heart_demon", 8
                        )),
                    )
                    context.state.entities.put(
                        actor_id, CULTIVATION, cultivation
                    )
                    return EffectOutcome(
                        "separated",
                        f"{name}收回道侣信物、解散誓约；心魔随之增长。",
                    )
                return EffectOutcome(
                    "expelled", f"{name}将你逐出门墙；师徒关系就此解除。"
                )

            if actual_role in {"master", "companion"}:
                edge = active_social_edge()
                if edge is None:
                    return EffectOutcome(
                        "relationship_absent", "这段关系已经先一步结束。"
                    )
                if mode == "accept":
                    return end_social(edge)
                if mode != "appease":
                    raise ValueError("未知的关系问罪应对")
                affinity = relationship_affinity(
                    context.state, target_id, actor_id
                )
                actor_realm = definitions.realm_index(str(
                    context.state.entities.require(
                        actor_id, CULTIVATION
                    )["realm_id"]
                ))
                chance = max(
                    0.08,
                    min(0.72, 0.34 + affinity / 250 + actor_realm * 0.025),
                )
                if context.rng.random() < chance:
                    set_relationship_affinity(
                        context.state, target_id, actor_id, threshold + 6
                    )
                    return EffectOutcome(
                        "appeased",
                        f"你暂时平息{name}的怒意（成功率 {chance:.0%}）。",
                    )
                return end_social(edge)

            if actual_role not in {"concubine_owner", "ghost_captor"}:
                raise ValueError("未知的主仆问罪来源")
            concubine_edge = next((
                edge for edge in context.state.relations.find(
                    target_id=actor_id, kind="concubine"
                ) if edge.source_id == target_id
            ), None)
            ecology = context.state.entities.get(
                actor_id, "dlc.ghost.ecology"
            ) or {}
            captor = dict(ecology.get("captor") or {})
            status_exists = (
                concubine_edge is not None
                if actual_role == "concubine_owner"
                else str(captor.get("entity_id") or "") == target_id
            )
            if not status_exists:
                return EffectOutcome(
                    "relationship_absent", "主仆约束已经解除，这次索偿作罢。"
                )
            affinity = relationship_affinity(
                context.state, target_id, actor_id
            )
            if mode == "comply":
                from .economy import INVENTORY
                from .cultivation import _opportunity_required

                demand = max(1, int(runtime.get("demand", 5)))
                inventory = context.state.entities.require(actor_id, INVENTORY)
                items = dict(inventory.get("items", {}))
                reserved = dict(inventory.get("reserved", {}))
                stones = max(
                    0,
                    int(items.get("spirit_stone", 0))
                    - int(reserved.get("spirit_stone", 0)),
                )
                paid = min(demand, stones)
                if paid:
                    context.emit(
                        "story.effect.inventory.changed", source="story",
                        scope=EventScope.entity(actor_id),
                        payload={
                            "entity_id": actor_id,
                            "item_id": "spirit_stone",
                            "quantity": -paid,
                            "reason": "relationship_sanction",
                        },
                    )
                shortfall = demand - paid
                opportunity_paid = 0.0
                cultivation = context.state.entities.require(
                    actor_id, CULTIVATION
                )
                if shortfall:
                    opportunity_paid = min(
                        float(cultivation.get("opportunity", 0.0)),
                        _opportunity_required(definitions, cultivation)
                        * min(
                            0.08,
                            0.02 + shortfall / max(1, demand) * 0.04,
                        ),
                    )
                    cultivation["opportunity"] = max(
                        0.0,
                        float(cultivation.get("opportunity", 0.0))
                        - opportunity_paid,
                    )
                    context.state.entities.put(
                        actor_id, CULTIVATION, cultivation
                    )
                set_relationship_affinity(
                    context.state,
                    target_id,
                    actor_id,
                    min(100.0, affinity + (18 if not shortfall else 10)),
                )
                return EffectOutcome(
                    "complied",
                    f"你向{name}交出下品灵石 ×{paid}"
                    + (
                        f"，并以机缘 {opportunity_paid:.1f} 抵偿不足"
                        if shortfall else ""
                    )
                    + "。",
                )
            actor_realm = definitions.realm_index(str(
                context.state.entities.require(actor_id, CULTIVATION)["realm_id"]
            ))
            if mode == "appease":
                chance = max(
                    0.08,
                    min(0.70, 0.30 + affinity / 260 + actor_realm * 0.02),
                )
                if context.rng.random() < chance:
                    set_relationship_affinity(
                        context.state, target_id, actor_id, threshold + 5
                    )
                    return EffectOutcome(
                        "appeased",
                        f"你的解释暂时说动{name}（成功率 {chance:.0%}）。",
                    )
                mode = "defy"
            if mode == "defy":
                relief = float(rules.get("sanction_affinity_relief", 8))
                set_relationship_affinity(
                    context.state,
                    target_id,
                    actor_id,
                    min(100.0, affinity + relief),
                )
                runtime_state = context.state.entities.require(
                    actor_id, "core.action_runtime"
                )
                unit = max(
                    0, int(runtime_state.get("next_sequence", 1)) - 1
                )
                if concubine_edge is not None:
                    metadata = dict(concubine_edge.metadata)
                    metadata["angered_until_unit"] = unit + 2
                    context.state.relations.replace_metadata(
                        concubine_edge.relation_id, metadata
                    )
                elif captor:
                    captor["angered_until_unit"] = unit + 2
                    ecology["captor"] = captor
                    context.state.entities.put(
                        actor_id, "dlc.ghost.ecology", ecology
                    )
                condition = context.state.entities.require(actor_id, CONDITION)
                condition["hp_ratio"] = max(
                    0.01, float(condition.get("hp_ratio", 1.0)) - 0.10
                )
                context.state.entities.put(actor_id, CONDITION, condition)
                return EffectOutcome(
                    "defied",
                    f"{name}以主仆约束惩戒于你；HP 损失 10%，震怒持续两个行动单位。",
                )
            raise ValueError("未知的主仆问罪应对")
        target_id = _role_target(context, actor_id, role)
        if target_id is None:
            target_id = _runtime_target(context, actor_id, pending)
        if effect.kind == "relationship_affinity":
            value = float(effect.payload.get("value", 0))
            current = relationship_affinity(context.state, target_id, actor_id)
            set_relationship_affinity(context.state, target_id, actor_id, current + value)
            return EffectOutcome(None, f"关系好感 {value:+g}")
        mode = str(effect.payload.get("mode", "accept"))
        if mode in {"accept", "appease"}:
            set_relationship_affinity(
                context.state, target_id, actor_id,
                relationship_affinity(context.state, target_id, actor_id) - (5 if mode == "accept" else 2),
            )
        elif mode in {"sever", "leave", "reject"}:
            for edge in context.state.relations.involving(actor_id):
                if target_id in {edge.source_id, edge.target_id}:
                    context.state.relations.end(edge.relation_id, ended_year=context.state.clock.year)
        return EffectOutcome(mode, "这段关系承受了本次因果的后果。")

    def generated_relationship(context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any]) -> EffectOutcome:
        target_id = _runtime_target(context, actor_id, pending)
        if effect.kind == "gain_generated_master":
            chance = float(effect.payload.get("accept_chance", 1))
            if context.rng.random() >= chance:
                return EffectOutcome("rejected", "对方没有收徒。")
            source, target, kind = target_id, actor_id, "master_disciple"
        elif effect.kind == "gain_generated_disciple":
            source, target, kind = actor_id, target_id, "master_disciple"
        else:
            source, target, kind = actor_id, target_id, "dao_companion"
        if not context.state.relations.involving(actor_id, kind=kind):
            context.state.relations.add(
                source_id=source, target_id=target, kind=kind,
                created_year=context.state.clock.year,
                metadata={"affinity": 60.0, "source": "story"},
            )
        set_relationship_affinity(context.state, target_id, actor_id, 60)
        return EffectOutcome("accepted", "新的重要关系已经建立。")

    def combat_effect(context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any]) -> EffectOutcome:
        target_id = _runtime_target(context, actor_id, pending)
        actor_location = context.state.entities.require(actor_id, LOCATION)
        target_location = context.state.entities.require(target_id, LOCATION)
        if target_location.get("world_id") != actor_location.get("world_id"):
            raise ValueError("事件目标已经不在当前世界")
        # V1 encounters are world-scoped rather than tied to a map tile.  Once
        # the event opens, both sides meet at the player's current node.
        context.state.entities.put(target_id, LOCATION, dict(actor_location))
        lethal = bool(effect.payload.get("lethal", effect.kind not in {"cultivator_reaction"}))
        before = set(context.state.entities.with_component("combat.report"))
        _resolve_handler(definitions)(
            context, ResolveCombat(actor_id, target_id, "kill" if lethal else "duel")
        )
        report_ids = set(
            context.state.entities.with_component("combat.report")
        ) - before
        if len(report_ids) != 1:
            raise ValueError("战斗结算没有生成唯一战报")
        report = context.state.entities.require(report_ids.pop(), "combat.report")
        actor_alive = bool(context.state.entities.require(actor_id, LIFE).get("alive"))
        target_alive = bool(context.state.entities.require(target_id, LIFE).get("alive"))
        if not actor_alive:
            result = "dead"
        elif lethal and not target_alive:
            result = "killed"
        else:
            result = str(report["outcome"])
        return EffectOutcome(result, "冲突已经通过实际战斗结算。")

    def cultivator_reaction(
        context: SimulationContext, actor_id: str,
        effect: Any, pending: dict[str, Any],
    ) -> EffectOutcome:
        story = context.state.entities.require(actor_id, STORY_STATE)
        fame = float(dict(story.get("attributes", {})).get("fame", 0))
        threshold = float(dict(definitions.systems.get(
            "faction_conflict", {}
        )).get("fame_deterrence_threshold", 100))
        if fame >= threshold:
            return EffectOutcome("deterred", "你的威名足以压住对方的贪念。")
        chance = float(effect.payload.get("chance", 0.2)) * max(
            0.0, 1 - fame / max(1.0, threshold)
        )
        if context.rng.random() >= chance:
            return EffectOutcome("ignored", "对方虽有不满，最终没有追来。")
        forced = type(effect)(kind="runtime_combat", payload={"lethal": True})
        return combat_effect(context, actor_id, forced, pending)

    def narrative_decision(context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any]) -> EffectOutcome:
        kind = effect.kind
        mode = str(effect.payload.get(
            "mode", effect.payload.get(
                "response", effect.payload.get("method", "resolved")
            )
        ))
        if kind == "faction_war":
            membership = next(iter(context.state.relations.find(
                source_id=actor_id, kind="faction_membership"
            )), None)
            if membership is None:
                return EffectOutcome("faction_absent", "战帖已经与你无关。")
            forced = type(effect)(kind="runtime_combat", payload={"lethal": False})
            outcome = combat_effect(context, actor_id, forced, pending)
            amount = int(effect.payload.get("contribution", 12))
            if outcome.result != "victory":
                amount = max(1, amount // 2)
            metadata = dict(membership.metadata)
            metadata["contribution"] = int(
                metadata.get("contribution", 0)
            ) + amount
            context.state.relations.replace_metadata(
                membership.relation_id, metadata
            )
            return EffectOutcome(
                "victory" if outcome.result == "victory" else "survived",
                f"{outcome.summary.rstrip('。')}；宗门贡献 +{amount}",
            )
        if kind == "wanted_response":
            runtime = dict(pending.get("runtime", {}))
            key = str(runtime.get("hostility_key", ""))
            if not key or ":" not in key:
                raise ValueError("追缉势力已经不存在")
            target_id = _runtime_target(context, actor_id, pending)
            rules = dict(definitions.systems.get("faction_conflict", {}))

            def custody() -> EffectOutcome:
                from .demonic import EnterImprisonment, _enter_prison_handler

                wanted = context.state.entities.require(actor_id, WANTED_STATE)
                hostility = float(dict(wanted.get("hostility", {})).get(key, 0.0))
                execution_threshold = float(rules.get("execution_threshold", 165))
                execution_chance = (
                    0.0 if hostility < execution_threshold
                    else min(0.9, 0.35 + (hostility - execution_threshold) / 100)
                )
                if mode != "surrender":
                    execution_chance = min(0.95, execution_chance + 0.12)
                if context.rng.random() < execution_chance:
                    reason = f"落入{runtime.get('pursuer', '追缉势力')}之手，被当场处决"
                    context.emit(
                        "character.lethal_hazard", source="war",
                        scope=EventScope.entity(actor_id),
                        payload={"entity_id": actor_id, "reason": reason},
                    )
                    return EffectOutcome("dead", reason)
                low, high = map(int, rules.get("prison_years", [3, 12]))
                years = context.rng.randint(low, high) + min(8, int(hostility // 35))
                _enter_prison_handler(context, EnterImprisonment(
                    actor_id, target_id, years,
                    str(runtime.get("pursuer", "追缉势力")),
                    "world_prison", hostility,
                ))
                return EffectOutcome(
                    "surrendered" if mode == "surrender" else "captured",
                    f"你被押入{runtime.get('pursuer', '追缉势力')}大牢，刑期 {years} 年。",
                )

            if mode == "fight":
                _change_hostility(
                    context, actor_id, key,
                    float(rules.get("fight_hostility_gain", 12)),
                )
                outcome = combat_effect(context, actor_id, effect, pending)
                if outcome.result == "dead" or not bool(
                    context.state.entities.require(actor_id, LIFE).get("alive")
                ):
                    return outcome
                if outcome.result not in {"victory", "killed"}:
                    return custody()
                return outcome
            if mode == "surrender":
                return custody()
            if mode == "escape":
                actor_power = float(combat_snapshot(
                    context.state, definitions, actor_id
                )["power"])
                target_power = max(1.0, float(runtime.get("target_power", actor_power)))
                chance = max(0.08, min(0.8, 0.22 + actor_power / target_power * 0.25))
                _change_hostility(
                    context, actor_id, key,
                    float(rules.get("escape_hostility_gain", 18)),
                )
                if context.rng.random() < chance:
                    return EffectOutcome(
                        "escaped",
                        f"你付出代价甩脱追兵（成功率 {chance:.0%}），敌对值进一步上升。",
                    )
                return custody()
            raise ValueError("未知通缉应对方式")
        if kind == "wanted_settlement":
            runtime = dict(pending.get("runtime", {}))
            key = str(runtime.get("hostility_key", ""))
            if not key or ":" not in key:
                raise ValueError("议和对象已经不存在")
            power_kind = str(runtime.get("kind", key.split(":", 1)[0]))
            entity_id = str(runtime.get("entity_id", key.split(":", 1)[1]))
            entity_name = str(runtime.get(
                "entity_name", runtime.get("pursuer", "追缉势力")
            ))
            wanted = context.state.entities.require(actor_id, WANTED_STATE)
            hostility = dict(wanted.get("hostility", {}))
            hostility[key] = 0.0
            wanted["hostility"] = hostility
            if mode == "compensation":
                amount = max(500, int(max(
                    1.0, float(runtime.get("power", runtime.get("target_power", 1)))
                ) ** 0.5) * 80)
                context.emit(
                    "story.effect.inventory.changed", source="story",
                    scope=EventScope.entity(actor_id),
                    payload={
                        "entity_id": actor_id, "item_id": "spirit_stone",
                        "quantity": amount, "reason": "wanted_settlement",
                    },
                )
                result, summary = (
                    "compensated",
                    f"{entity_name}交出下品灵石 ×{amount}并撤销追杀令。",
                )
            elif mode == "dissolve":
                from .factions import FACTION_PROFILE, MEMBERSHIP
                from .family import FAMILY_MEMBERSHIP, FAMILY_PROFILE

                if power_kind == "sect":
                    component, membership_kind = FACTION_PROFILE, MEMBERSHIP
                elif power_kind == "family":
                    component, membership_kind = FAMILY_PROFILE, FAMILY_MEMBERSHIP
                else:
                    raise ValueError("该类势力不能就地解散")
                profile = context.state.entities.get(entity_id, component)
                if profile is None:
                    raise ValueError("议和势力已经不存在")
                profile["active"] = False
                profile["extinct_year"] = context.state.clock.year
                context.state.entities.put(entity_id, component, profile)
                for edge in list(context.state.relations.find(
                    target_id=entity_id, kind=membership_kind
                )):
                    closed = context.state.relations.end(
                        edge.relation_id, ended_year=context.state.clock.year
                    )
                    metadata = dict(closed.metadata)
                    metadata["end_reason"] = "dissolved_by_wanted_target"
                    context.state.relations.replace_metadata(
                        edge.relation_id, metadata
                    )
                story = context.state.entities.require(actor_id, STORY_STATE)
                milestones = dict(story.get("milestones", {}))
                milestones["dissolved_wanted_power"] = 1
                story["milestones"] = milestones
                context.state.entities.put(actor_id, STORY_STATE, story)
                result, summary = (
                    "dissolved",
                    f"你勒令{entity_name}撤下门庭、解散传承；旧通缉令失效。",
                )
            elif mode == "personal_vassal":
                story = context.state.entities.require(actor_id, STORY_STATE)
                flags = list(map(str, story.get("flags", [])))
                flag = f"personal_vassal:{power_kind}:{entity_id}"
                if flag not in flags:
                    flags.append(flag)
                story["flags"] = flags
                context.state.entities.put(actor_id, STORY_STATE, story)
                result, summary = (
                    "personal_vassal",
                    f"{entity_name}向你本人奉上臣服契约。",
                )
            elif mode == "sect_vassal":
                from .factions import (
                    DIPLOMACY_STATE, _active_membership, _diplomacy_key,
                )

                membership = _active_membership(context.state, actor_id)
                if membership is None or power_kind not in {"sect", "family"}:
                    raise ValueError("当前条件无法将对方纳为本宗附庸")
                diplomacy = context.state.entities.require(
                    actor_id, DIPLOMACY_STATE
                )
                relations = dict(diplomacy.get("relations", {}))
                relation_key = _diplomacy_key(
                    "faction", membership.target_id, entity_id
                )
                relations[relation_key] = {
                    "kind": "faction",
                    "first_id": min(membership.target_id, entity_id),
                    "second_id": max(membership.target_id, entity_id),
                    "status": "vassal", "affinity": 70.0,
                    "since_year": context.state.clock.year,
                    "overlord": membership.target_id, "subject": entity_id,
                    "source": "wanted_settlement",
                }
                diplomacy["relations"] = relations
                context.state.entities.put(
                    actor_id, DIPLOMACY_STATE, diplomacy
                )
                own_name = str(context.state.entities.require(
                    membership.target_id, "faction.profile"
                )["name"])
                result, summary = (
                    "sect_vassal",
                    f"{entity_name}交出外交与征召权，成为{own_name}的附庸。",
                )
            elif mode == "hostages":
                amount = max(200, int(max(
                    1.0, float(runtime.get("power", 1))
                ) ** 0.5) * 35)
                context.emit(
                    "story.effect.inventory.changed", source="story",
                    scope=EventScope.entity(actor_id),
                    payload={
                        "entity_id": actor_id, "item_id": "spirit_stone",
                        "quantity": amount, "reason": "wanted_hostages",
                    },
                )
                members = [
                    member_id for member_id in map(
                        str, runtime.get("member_ids", [])
                    )
                    if context.state.entities.exists(member_id)
                    and bool(context.state.entities.require(
                        member_id, LIFE
                    ).get("alive"))
                ]
                target_id = max(
                    members,
                    key=lambda member_id: float(combat_snapshot(
                        context.state, definitions, member_id
                    )["power"]),
                    default="",
                )
                if target_id:
                    held = context.state.relations.find(
                        target_id=target_id, kind=PRISONER
                    )
                    if not held:
                        context.state.relations.add(
                            source_id=actor_id, target_id=target_id,
                            kind=PRISONER, created_year=context.state.clock.year,
                            metadata={
                                "status": "confined",
                                "source": f"wanted_settlement:{power_kind}",
                            },
                        )
                    target_name = str(context.state.entities.require(
                        target_id, IDENTITY
                    )["name"])
                    summary = (
                        f"{entity_name}交出灵石 ×{amount}，并将最强者"
                        f"{target_name}交给你作为人质。"
                    )
                else:
                    summary = (
                        f"{entity_name}已无强者可交，只得献上灵石 ×{amount}。"
                    )
                result = "hostages"
            elif mode == "fallen":
                result, summary = (
                    "pursuit_ended",
                    f"{entity_name}已经覆灭，通缉自动终止。",
                )
            else:
                raise ValueError("当前追缉势力不支持这种议和条件")
            if key.startswith("world:"):
                subdued = list(map(str, wanted.get("subdued", [])))
                if key not in subdued:
                    subdued.append(key)
                wanted["subdued"] = subdued
            context.state.entities.put(actor_id, WANTED_STATE, wanted)
            return EffectOutcome(result, summary)
        if kind == "personal_revenge_response":
            runtime = dict(pending.get("runtime", {}))
            target_id = _runtime_target(context, actor_id, pending)
            if not bool(context.state.entities.require(target_id, LIFE).get("alive")):
                return EffectOutcome("revenge_absent", "仇家已经不知所踪。")
            if mode == "escape":
                condition = context.state.entities.require(actor_id, CONDITION)
                mp_ratio = float(condition.get("mp_ratio", 0.0))
                condition["mp_ratio"] = max(0.0, mp_ratio - 0.16)
                context.state.entities.put(actor_id, CONDITION, condition)
                chance = min(0.85, 0.30 + mp_ratio * 0.45)
                if context.rng.random() < chance:
                    return EffectOutcome(
                        "escaped",
                        f"你以遁术摆脱追杀（成功率 {chance:.0%}），MP 消耗 16%。",
                    )
                forced = type(effect)(
                    kind="runtime_combat", payload={"lethal": True}
                )
                outcome = combat_effect(context, actor_id, forced, pending)
                return EffectOutcome(
                    outcome.result,
                    f"遁术失败，你被迫仓促接战。{outcome.summary}",
                )
            if mode not in {"fight", "ally", "sect", "formation", "resolved"}:
                raise ValueError("未知旧怨应对方式")
            support_id = ""
            support_label = ""
            if mode == "ally":
                support_id = str(runtime.get("ally_id") or "")
                support_label = "能够驰援的故交"
            elif mode == "sect":
                support_id = str(runtime.get("sect_support_id") or "")
                support_label = "能够接应的宗门同道"
            temporary_edge_id = ""
            support_name = ""
            if support_id:
                if (
                    not context.state.entities.exists(support_id)
                    or not bool(context.state.entities.require(support_id, LIFE).get("alive"))
                    or context.state.entities.require(support_id, LOCATION).get("world_id")
                    != context.state.entities.require(actor_id, LOCATION).get("world_id")
                ):
                    raise ValueError(f"{support_label}已经不在")
                support_name = str(
                    context.state.entities.require(support_id, IDENTITY)["name"]
                )
                # 援军赶到伏击地点，并通过统一队伍战力公式参与战斗。
                context.state.entities.put(
                    support_id,
                    LOCATION,
                    dict(context.state.entities.require(actor_id, LOCATION)),
                )
                from .party import PARTY_MEMBER

                existing = next((
                    edge for edge in context.state.relations.find(
                        source_id=actor_id, kind=PARTY_MEMBER
                    )
                    if edge.target_id == support_id
                ), None)
                if existing is None:
                    temporary = context.state.relations.add(
                        source_id=actor_id,
                        target_id=support_id,
                        kind=PARTY_MEMBER,
                        created_year=context.state.clock.year,
                        metadata={"source": "personal_revenge_support", "temporary": True},
                    )
                    temporary_edge_id = temporary.relation_id
            elif mode in {"ally", "sect"}:
                raise ValueError(f"当前没有{support_label}")
            forced = type(effect)(kind="runtime_combat", payload={"lethal": True})
            try:
                outcome = combat_effect(context, actor_id, forced, pending)
            finally:
                if temporary_edge_id:
                    edge = next((
                        row for row in context.state.relations.find()
                        if row.relation_id == temporary_edge_id
                    ), None)
                    if edge is not None:
                        closed = context.state.relations.end(
                            temporary_edge_id, ended_year=context.state.clock.year
                        )
                        metadata = dict(closed.metadata)
                        metadata["end_reason"] = "personal_revenge_resolved"
                        context.state.relations.replace_metadata(
                            temporary_edge_id, metadata
                        )
            if support_name:
                return EffectOutcome(
                    outcome.result,
                    f"{support_name}及时驰援并实际加入战局。{outcome.summary}",
                )
            return outcome
        if kind == "concubine_escape":
            edge = next(iter(context.state.relations.find(
                target_id=actor_id, kind="concubine"
            )), None)
            if edge is None:
                return EffectOutcome("already_free", "你已经不再受侍妾名分约束。")
            runtime = dict(pending.get("runtime", {}))
            owner_id = str(runtime.get("owner_id") or edge.source_id)
            if owner_id != edge.source_id:
                raise ValueError("当前正主与脱身事件不符")
            if mode == "abandon":
                return EffectOutcome("abandoned", "你暂缓脱身计划，关系维持原状。")
            if mode not in {"covert", "plead"}:
                raise ValueError("未知的脱身方式")
            from .actions import ACTION_RUNTIME
            from .concubines import CONCUBINE_STATE

            metadata = dict(edge.metadata)
            owner_cultivation = context.state.entities.require(
                owner_id, CULTIVATION
            )
            actor_cultivation = context.state.entities.require(
                actor_id, CULTIVATION
            )
            owner_rank = definitions.realm_index(str(
                owner_cultivation["realm_id"]
            ))
            actor_rank = definitions.realm_index(str(
                actor_cultivation["realm_id"]
            ))
            gap = max(0, owner_rank - actor_rank)
            chance = 0.18 if mode == "plead" else 0.28
            chance += (
                0.10 if metadata.get("dependent") and mode == "plead" else 0.0
            )
            chance -= gap * 0.04
            chance += min(0.12, int(metadata.get("turns", 0)) * 0.015)
            chance = max(0.05, min(0.78, chance))
            owner_name = str(context.state.entities.require(
                owner_id, IDENTITY
            )["name"])
            if context.rng.random() < chance:
                closed = context.state.relations.end(
                    edge.relation_id, ended_year=context.state.clock.year
                )
                closed_meta = dict(closed.metadata)
                closed_meta["end_reason"] = "escaped"
                context.state.relations.replace_metadata(
                    closed.relation_id, closed_meta
                )
                set_relationship_affinity(
                    context.state, owner_id, actor_id, 0.0
                )
                component = context.state.entities.require(
                    actor_id, CONCUBINE_STATE
                )
                component["escape_reputation"] = int(
                    component.get("escape_reputation", 0)
                ) + 1
                context.state.entities.put(
                    actor_id, CONCUBINE_STATE, component
                )
                return EffectOutcome(
                    "escaped",
                    f"你成功脱离{owner_name}的控制（成功率 {chance:.0%}）。",
                )
            runtime_state = context.state.entities.require(
                actor_id, ACTION_RUNTIME
            )
            unit = max(0, int(runtime_state.get("next_sequence", 1)) - 1)
            metadata["failed_escape_count"] = int(
                metadata.get("failed_escape_count", 0)
            ) + 1
            metadata["angered_until_unit"] = unit + 2
            context.state.relations.replace_metadata(
                edge.relation_id, metadata
            )
            set_relationship_affinity(
                context.state,
                owner_id,
                actor_id,
                relationship_affinity(context.state, owner_id, actor_id) - 18,
            )
            return EffectOutcome(
                "escape_failed",
                f"脱身失败，{owner_name}已经震怒（成功率 {chance:.0%}）。",
            )
        story, extra = _story_extra(context, actor_id)
        history = list(extra.get("decisions", []))
        history.append({"kind": kind, "mode": mode, "year": context.state.clock.year})
        extra["decisions"] = history[-40:]
        _save_extra(context, actor_id, story, extra)
        return EffectOutcome(mode, "该剧情决断已经记入权威状态。")

    def affinity_gift(context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any]) -> EffectOutcome:
        target_id = _runtime_target(context, actor_id, pending)
        if not bool(context.state.entities.require(target_id, LIFE).get("alive")):
            return EffectOutcome(
                "visitor_absent", "故人临时有事，只留下一封问候信。"
            )
        target = context.state.entities.require(target_id, IDENTITY)
        target_name = str(target["name"])
        runtime = dict(pending.get("runtime", {}))
        target_realm = max(1, int(runtime.get(
            "npc_realm_index",
            definitions.realm_index(str(context.state.entities.require(
                target_id, CULTIVATION
            )["realm_id"])),
        )))
        mode = str(effect.payload.get("mode", "accept"))
        if mode == "decline":
            gain = 1
            result = "declined"
            summary = f"你未收礼物，但{target_name}仍领会了你的礼数"
        elif mode in {"discuss", "share"}:
            gain = 2
            opportunity = context.rng.randint(5, 10) * target_realm
            context.emit(
                "story.effect.cultivation.changed",
                source="story",
                scope=EventScope.entity(actor_id),
                payload={
                    "entity_id": actor_id,
                    "field": "opportunity",
                    "amount": opportunity,
                },
            )
            if mode == "share":
                condition = context.state.entities.require(actor_id, CONDITION)
                condition["mp_ratio"] = min(
                    1.0, float(condition.get("mp_ratio", 0.0)) + 0.08
                )
                context.state.entities.put(actor_id, CONDITION, condition)
            result = "discussed"
            summary = f"你与{target_name}论道互证，机缘 +{opportunity}"
        elif mode == "accept":
            gain = 3
            world_id = str(
                context.state.entities.require(actor_id, LOCATION)["world_id"]
            )
            goods = [
                good for good in definitions.market_goods
                if good.kind == "item"
                and good.world_id == world_id
                and good.tier <= target_realm
                and good.content_id in definitions.items
                and not {"currency", "root_manual"}.intersection(
                    definitions.items[good.content_id].tags
                )
            ]
            item_ids = list(dict.fromkeys(good.content_id for good in goods))
            if item_ids and context.rng.random() < 0.68:
                best_tier = max(good.tier for good in goods)
                suitable = list(dict.fromkeys(
                    good.content_id for good in goods if good.tier == best_tier
                ))
                item_id = context.rng.choice(suitable or item_ids)
                quantity = 1
                gift_text = definitions.items[item_id].name
            else:
                item_id = "spirit_stone"
                quantity = context.rng.randint(3, 8) * target_realm
                gift_text = f"下品灵石 ×{quantity}"
            context.emit(
                "story.effect.inventory.changed",
                source="story",
                scope=EventScope.entity(actor_id),
                payload={
                    "entity_id": actor_id,
                    "item_id": item_id,
                    "quantity": quantity,
                    "reason": "personal_affinity_gift",
                },
            )
            result = "gift_received"
            summary = f"{target_name}赠予你{gift_text}"
        else:
            raise ValueError("未知故人来访应对方式")
        affinity = set_relationship_affinity(
            context.state,
            target_id,
            actor_id,
            relationship_affinity(context.state, target_id, actor_id) + gain,
        )
        return EffectOutcome(result, f"{summary}（好感 {affinity:.0f}）。")

    def treasure(context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any]) -> EffectOutcome:
        category = str(effect.payload.get("category", "artifact"))
        rewards = dict(dict(pending.get("runtime", {})).get("rewards", {}))
        # Earlier V2 snapshots could already contain an unopened treasure
        # event from before rewards were persisted at discovery time. Repair
        # that forward so loading such a save cannot strand the interaction.
        if not rewards:
            rewards = dict(
                _treasure_runtime(context, definitions, actor_id)["rewards"]
            )
        reward = dict(rewards.get(category, {}))
        content_id = str(reward.get("content_id", ""))
        if not content_id:
            raise ValueError("这份探宝奖励已经失落")
        if category == "technique":
            if content_id not in definitions.techniques:
                raise ValueError("探宝功法定义已经失效")
            practice = context.state.entities.require(actor_id, PRACTICE)
            known = list(map(str, practice.get("known_techniques", [])))
            name = definitions.techniques[content_id].name
            if content_id not in known:
                context.emit(
                    "story.effect.technique.learned", source="story", scope=EventScope.entity(actor_id),
                    payload={"entity_id": actor_id, "technique_id": content_id},
                )
                return EffectOutcome(
                    "technique_learned", f"你取走功法《{name}》，已收入已悟功法。"
                )
            levels = dict(practice.get("technique_levels", {}))
            current = int(levels.get(
                content_id, definitions.techniques[content_id].level
            ))
            levels[content_id] = current + 1
            practice["technique_levels"] = levels
            context.state.entities.put(actor_id, PRACTICE, practice)
            return EffectOutcome(
                "technique_improved",
                f"你取走《{name}》残篇，功法精进至 {current + 1} 级。",
            )
        if content_id not in definitions.items:
            raise ValueError("探宝物品定义已经失效")
        context.emit(
            "story.effect.inventory.changed", source="story",
            scope=EventScope.entity(actor_id),
            payload={
                "entity_id": actor_id, "item_id": content_id,
                "quantity": 1, "reason": "treasure_reward",
            },
        )
        category_name = "法器" if category == "artifact" else "丹药"
        return EffectOutcome(
            "treasure_claimed",
            f"你取走{category_name}“{definitions.items[content_id].name}” ×1。",
        )

    def enter_spirit(context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any]) -> EffectOutcome:
        story = context.state.entities.require(actor_id, STORY_STATE)
        crossing = dict(story.get("spirit_crossing", {}))
        if not bool(crossing.get("attempted")) or not bool(crossing.get("active")):
            raise ValueError("当前没有进行中的灵界偷渡")
        destination = str(crossing.get("destination") or "spirit")
        if context.state.entities.require(actor_id, LOCATION)["world_id"] != destination:
            _ascend_handler(definitions)(context, AscendWorld(
                actor_id,
                destination,
                tuple(map(str, crossing.get("invited_ids", []))),
            ))
        crossing["active"] = False
        crossing["completed_year"] = context.state.clock.year
        story = context.state.entities.require(actor_id, STORY_STATE)
        story["spirit_crossing"] = crossing
        context.state.entities.put(actor_id, STORY_STATE, story)
        destination_name = definitions.worlds[destination].name
        return EffectOutcome(
            "entered_spirit_realm", f"你已经进入{destination_name}。"
        )

    registry.register("attribute_check", attribute_check)
    for kind in {
        "acquire_root", "add_body_progress", "body_training", "add_random_jinque",
        "advance_immortal_conversion", "grant_monster_imprint", "mortal_progress",
        "set_mortal_aspiration", "set_spouse", "technique_level", "add_hostility",
    }:
        registry.register(kind, simple_progress)
    registry.register("relationship_affinity", relationship_effect)
    registry.register("relationship_sanction", relationship_effect)
    for kind in {"gain_generated_master", "gain_generated_disciple", "gain_generated_companion"}:
        registry.register(kind, generated_relationship)
    for kind in {"combat", "runtime_combat"}:
        registry.register(kind, combat_effect)
    registry.register("cultivator_reaction", cultivator_reaction)
    for kind in {
        "concubine_escape", "personal_revenge_response",
        "faction_war", "wanted_response", "wanted_settlement",
    }:
        registry.register(kind, narrative_decision)
    registry.register("affinity_gift", affinity_gift)
    registry.register("treasure_reward_choice", treasure)
    registry.register("enter_spirit_realm", enter_spirit)

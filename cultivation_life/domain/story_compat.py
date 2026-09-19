from __future__ import annotations

import operator
from typing import Any

from .advanced_cultivation import BODY
from .character import IDENTITY, LIFE, create_character
from .combat import CONDITION, ResolveCombat, _resolve_handler, combat_snapshot
from .cultivation import CULTIVATION, PRACTICE
from .definitions import GameDefinitions
from .extensions import MONSTER_BLOODLINE
from .relations import relationship_affinity, set_relationship_affinity
from .story import EffectOutcome, STORY_STATE, StoryEffectRegistry
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
    return create_character(
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
        runtime = dict(pending.get("runtime", {}))
        target_power = max(1.0, float(runtime.get("target_power", snapshot["power"])))
        values = {
            "combat_power": float(snapshot["power"]),
            "hp": float(snapshot["max_hp"]) * float(condition["hp_ratio"]),
            "mp": float(snapshot["max_mp"]) * float(condition["mp_ratio"]),
            "hp_ratio": float(condition["hp_ratio"]),
            "mp_ratio": float(condition["mp_ratio"]),
            "age": int(life["age"]),
            "realm_index": definitions.realm_index(str(cultivation["realm_id"])),
            "layer": int(cultivation["layer"]),
            "heart_demon": float(cultivation.get("heart_demon", 0)),
            "karma": float(attributes.get("karma", 0)),
            "sha_qi": float(attributes.get("sha_qi", 0)),
            "combat_ratio": float(snapshot["power"]) / target_power,
        }
        def check(row: dict[str, Any]) -> bool:
            stat = str(row.get("stat"))
            if stat == "has_item":
                inventory = context.state.entities.require(actor_id, "economy.inventory")
                item_id = str(row.get("item_id", ""))
                return int(dict(inventory.get("items", {})).get(item_id, 0)) > int(
                    dict(inventory.get("reserved", {})).get(item_id, 0)
                )
            return bool(_OPS.get(str(row.get("op", "gte")), operator.ge)(
                values.get(stat, 0), row.get("value", 0)
            ))

        passed = all(check(dict(row)) for row in effect.payload.get("checks", []))
        return EffectOutcome(
            "check_success" if passed else "check_failure",
            str(effect.payload.get(
                "success_text" if passed else "failure_reason",
                "判定成功" if passed else "判定失败",
            )),
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
            value = payload.get("value", 0)
            if "range" in payload:
                low, high = map(int, payload["range"])
                value = context.rng.randint(low, high)
            body["progress"] = max(0.0, float(body.get("progress", 0)) + float(value))
            context.state.entities.put(actor_id, BODY, body)
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
            extra["immortal_conversion_stage"] = max(
                int(extra.get("immortal_conversion_stage", 0)), int(payload.get("stage", 1))
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
            hostility = dict(extra.get("hostility", {}))
            key = f"{payload.get('kind', 'world')}:{payload.get('entity', 'current')}"
            hostility[key] = int(hostility.get(key, 0)) + int(payload.get("value", 0))
            extra["hostility"] = hostility
        _save_extra(context, actor_id, story, extra)
        return EffectOutcome(None, str(payload.get("text", "命途状态已经改变。")))

    def relationship_effect(context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any]) -> EffectOutcome:
        role = str(effect.payload.get("role", "friend"))
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
        lethal = bool(effect.payload.get("lethal", effect.kind not in {"cultivator_reaction"}))
        _resolve_handler(definitions)(
            context, ResolveCombat(actor_id, target_id, "kill" if lethal else "duel")
        )
        life = context.state.entities.require(actor_id, LIFE)
        report = context.state.entities.get(actor_id, "combat.report") or {}
        outcome = str(report.get("outcome", "resolved"))
        return EffectOutcome("dead" if not life.get("alive") else outcome, "冲突已经通过实际战斗结算。")

    def narrative_decision(context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any]) -> EffectOutcome:
        kind = effect.kind
        mode = str(effect.payload.get("mode", effect.payload.get("response", "resolved")))
        if kind in {"wanted_response", "personal_revenge_response", "sect_defense", "faction_war"} and mode in {"fight", "formation", "resolved"}:
            return combat_effect(context, actor_id, effect, pending)
        if kind == "concubine_escape":
            edges = context.state.relations.find(target_id=actor_id, kind="concubine")
            if mode == "abandon" or context.rng.random() < {"covert": .55, "plead": .42}.get(mode, .35):
                for edge in edges:
                    context.state.relations.end(edge.relation_id, ended_year=context.state.clock.year)
                return EffectOutcome("escaped", "你已经脱离侍妾关系。")
            return EffectOutcome("failed", "脱离尝试失败。")
        story, extra = _story_extra(context, actor_id)
        history = list(extra.get("decisions", []))
        history.append({"kind": kind, "mode": mode, "year": context.state.clock.year})
        extra["decisions"] = history[-40:]
        _save_extra(context, actor_id, story, extra)
        return EffectOutcome(mode, "该剧情决断已经记入权威状态。")

    def affinity_gift(context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any]) -> EffectOutcome:
        target_id = _runtime_target(context, actor_id, pending)
        gain = 6 if effect.payload.get("mode") == "share" else 3
        set_relationship_affinity(
            context.state, target_id, actor_id,
            relationship_affinity(context.state, target_id, actor_id) + gain,
        )
        return EffectOutcome(None, f"对方好感 +{gain}")

    def treasure(context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any]) -> EffectOutcome:
        category = str(effect.payload.get("category", "artifact"))
        candidates = [item_id for item_id, item in definitions.items.items() if (
            category == "pill" and "pill" in item_id
        ) or (category == "artifact" and item_id not in {"spirit_stone"} and "pill" not in item_id)]
        if category == "technique":
            known = set(context.state.entities.require(actor_id, PRACTICE).get("known_techniques", []))
            choices = [value for value in definitions.techniques if value not in known]
            if choices:
                context.emit(
                    "story.effect.technique.learned", source="story", scope=EventScope.entity(actor_id),
                    payload={"entity_id": actor_id, "technique_id": context.rng.choice(choices)},
                )
                return EffectOutcome(None, "获得了一部功法。")
        if candidates:
            context.emit(
                "story.effect.inventory.changed", source="story", scope=EventScope.entity(actor_id),
                payload={"entity_id": actor_id, "item_id": context.rng.choice(candidates), "quantity": 1, "reason": "story"},
            )
        return EffectOutcome(None, "获得了宝物奖励。")

    def enter_spirit(context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any]) -> EffectOutcome:
        if context.state.entities.require(actor_id, LOCATION)["world_id"] != "spirit":
            _ascend_handler(definitions)(context, AscendWorld(actor_id, "spirit"))
        return EffectOutcome("entered", "你已经进入灵界。")

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
    for kind in {"combat", "runtime_combat", "cultivator_reaction"}:
        registry.register(kind, combat_effect)
    for kind in {
        "concubine_escape", "personal_revenge_response", "sect_defense",
        "faction_war", "wanted_response", "wanted_settlement",
    }:
        registry.register(kind, narrative_decision)
    registry.register("affinity_gift", affinity_gift)
    registry.register("treasure_reward_choice", treasure)
    registry.register("enter_spirit_realm", enter_spirit)

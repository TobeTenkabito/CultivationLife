from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from typing import Any

from .character import LIFE
from .combat import CONDITION
from .cultivation import CULTIVATION
from .definitions import GameDefinitions
from .extensions import MONSTER_BLOODLINE, MONSTER_DLC
from .story import STORY_STATE
from .trials import TRIAL
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventScope, WorldState


_SELF_LINEAGE = re.compile(r"_NETHER_SELF_([1-4])$")
_STAT_KEYS = ("might", "guard", "mobility", "sense", "sustain", "breach")


@dataclass(frozen=True, slots=True)
class EvolveMonster:
    actor_id: str
    evolution_id: str


@dataclass(frozen=True, slots=True)
class PrepareCustomLineage:
    actor_id: str
    evolution_id: str


@dataclass(frozen=True, slots=True)
class ConfirmCustomLineage:
    actor_id: str
    evolution_id: str
    name: str
    rules: tuple[dict[str, Any], ...]


def _document(definitions: GameDefinitions) -> dict[str, Any]:
    return dict(definitions.extension_documents.get("monster_bloodlines.json", {}))


def _settings(definitions: GameDefinitions) -> dict[str, Any]:
    return dict(_document(definitions).get("settings", {}))


def _species(definitions: GameDefinitions) -> dict[str, dict[str, Any]]:
    return {
        str(row["id"]): dict(row)
        for row in _document(definitions).get("species", [])
        if isinstance(row, dict) and row.get("id")
    }


def _evolutions(definitions: GameDefinitions) -> dict[str, dict[str, Any]]:
    return {
        str(row["id"]): dict(row)
        for row in _document(definitions).get("evolutions", [])
        if isinstance(row, dict) and row.get("id")
    }


def _loaded(definitions: GameDefinitions) -> bool:
    return any(
        extension.id == MONSTER_DLC and extension.status == "loaded"
        for extension in definitions.extensions
    )


def _stage(evolution_id: str | None) -> int:
    matched = _SELF_LINEAGE.search(str(evolution_id or ""))
    return int(matched.group(1)) if matched else 0


def _required_opportunity(definitions: GameDefinitions, cultivation: dict[str, Any]) -> int:
    realm = definitions.realm(str(cultivation["realm_id"]))
    return round(realm.opportunity_base * (1 + 0.12 * (int(cultivation["layer"]) - 1)))


def _qi_level(definitions: GameDefinitions, experience: float) -> int:
    base = max(1.0, float(definitions.systems.get("qi_mastery", {}).get("experience_base", 25)))
    return max(0, int(math.sqrt(max(0.0, float(experience)) / base)))


def reconcile_monster_state(state: WorldState, definitions: GameDefinitions) -> None:
    if not _loaded(definitions):
        return
    species = _species(definitions)
    evolutions = _evolutions(definitions)
    for entity_id in state.entities.with_component(MONSTER_BLOODLINE):
        bloodline = state.entities.require(entity_id, MONSTER_BLOODLINE)
        defaults = {
            "generated_traits": [], "lineage_deeds": {},
            "custom_lineage_id": None, "custom_lineage": None,
            "pending_lineage_editor": None,
        }
        for key, value in defaults.items():
            bloodline.setdefault(key, copy.deepcopy(value))
        species_id = bloodline.get("species_id")
        if species_id in species and not bloodline.get("evolution_id"):
            base_id = str(species[str(species_id)]["base_evolution_id"])
            bloodline["evolution_id"] = base_id
            bloodline["evolution_history"] = [base_id]
        current = bloodline.get("evolution_id")
        history = list(dict.fromkeys(map(str, bloodline.get("evolution_history", []))))
        if current in evolutions and (not history or history[-1] != current):
            history.append(str(current))
        bloodline["evolution_history"] = history
        lineage = bloodline.get("custom_lineage")
        if isinstance(lineage, dict):
            lineage_id = str(
                lineage.get("id") or bloodline.get("custom_lineage_id")
                or f"custom-lineage:{state.game_id}:{entity_id}"
            )
            lineage["id"] = lineage_id
            bloodline["custom_lineage_id"] = lineage_id
            bloodline["custom_lineage"] = lineage
        elif lineage is None:
            bloodline["custom_lineage_id"] = None
        state.entities.put(entity_id, MONSTER_BLOODLINE, bloodline)


def _path_value(state: WorldState, definitions: GameDefinitions, actor_id: str, path: str) -> Any:
    cultivation = state.entities.require(actor_id, CULTIVATION)
    bloodline = state.entities.require(actor_id, MONSTER_BLOODLINE)
    location = state.entities.require(actor_id, "world.location")
    values = {
        "player.realm_index": definitions.realm_index(str(cultivation["realm_id"])),
        "player.layer": int(cultivation["layer"]),
        "player.world": location["world_id"],
        "player.monster_species_id": bloodline.get("species_id"),
        "player.monster.evolution_id": bloodline.get("evolution_id"),
        "player.monster.adaptations": list(bloodline.get("adaptations", [])),
        "player.monster.imprints": list(bloodline.get("imprints", [])),
        "player.monster.history": list(bloodline.get("evolution_history", [])),
        "player.monster.qi_level": _qi_level(
            definitions, dict(cultivation.get("qi_experience", {})).get("monster", 0.0)
        ),
    }
    if path not in values:
        raise ValueError(f"未知血脉条件路径：{path}")
    return values[path]


def _requirement_met(requirement: dict[str, Any], state: WorldState, definitions: GameDefinitions, actor_id: str) -> bool:
    if not requirement:
        return True
    if "all" in requirement:
        return all(_requirement_met(dict(row), state, definitions, actor_id) for row in requirement["all"])
    if "any" in requirement:
        return any(_requirement_met(dict(row), state, definitions, actor_id) for row in requirement["any"])
    if "not" in requirement:
        return not _requirement_met(dict(requirement["not"]), state, definitions, actor_id)
    left = _path_value(state, definitions, actor_id, str(requirement.get("path", "")))
    right = requirement.get("value")
    operation = str(requirement.get("op", "eq"))
    operations = {
        "eq": lambda a, b: a == b, "neq": lambda a, b: a != b,
        "gt": lambda a, b: a > b, "gte": lambda a, b: a >= b,
        "lt": lambda a, b: a < b, "lte": lambda a, b: a <= b,
        "contains": lambda a, b: b in a, "in": lambda a, b: a in b,
    }
    if operation not in operations:
        raise ValueError(f"未知血脉条件运算：{operation}")
    return bool(operations[operation](left, right))


def evolution_candidates(state: WorldState, definitions: GameDefinitions, actor_id: str) -> list[dict[str, Any]]:
    cultivation = state.entities.require(actor_id, CULTIVATION)
    bloodline = state.entities.require(actor_id, MONSTER_BLOODLINE)
    current_id = str(bloodline.get("evolution_id") or "")
    target_realm = definitions.realm_index(str(cultivation["realm_id"])) + 1
    qi_current = _qi_level(definitions, dict(cultivation.get("qi_experience", {})).get("monster", 0.0))
    rows = [
        row for row in _evolutions(definitions).values()
        if row.get("species") == bloodline.get("species_id")
        and current_id in list(map(str, row.get("parents", [])))
        and int(row.get("realm_index", -1)) == target_realm
    ]
    result = []
    for row in sorted(rows, key=lambda item: (int(item.get("order", 100)), str(item["id"]))):
        requirement = dict(row.get("requirements") or {})
        required_qi = int(row.get("monster_qi_level", 0))
        requirements_met = _requirement_met(requirement, state, definitions, actor_id)
        result.append({
            "id": str(row["id"]), "name": str(row["name"]),
            "description": str(row.get("description", "")),
            "enabled": requirements_met and qi_current >= required_qi,
            "profile": copy.deepcopy(dict(row.get("profile", {}))),
            "traits": list(map(str, row.get("traits", []))),
            "abilities": list(map(str, row.get("abilities", []))),
            "lifespan_gain": int(row.get("lifespan_gain", 0)),
            "monster_qi_level": {"current": qi_current, "required": required_qi, "met": qi_current >= required_qi},
            "requirements_met": requirements_met,
            "custom_lineage": _stage(str(row["id"])) > 0,
            "custom_lineage_stage": _stage(str(row["id"])),
        })
    if not result and current_id in _evolutions(definitions):
        current = _evolutions(definitions)[current_id]
        result.append({
            "id": "__stable__", "name": f"稳固{current['name']}",
            "description": "当前进化树已抵达边界；保持本相继续成长。",
            "enabled": True, "profile": copy.deepcopy(dict(current.get("profile", {}))),
            "traits": list(map(str, current.get("traits", []))),
            "abilities": list(map(str, current.get("abilities", []))),
            "lifespan_gain": 0,
            "monster_qi_level": {"current": qi_current, "required": 0, "met": True},
            "requirements_met": True, "stable_continuation": True,
            "custom_lineage": False, "custom_lineage_stage": 0,
        })
    return result


def _ensure_ready(
    context: SimulationContext, definitions: GameDefinitions,
    actor_id: str, evolution_id: str,
) -> dict[str, Any]:
    if actor_id != context.state.controlled_entity_id:
        raise ValueError("只能控制当前角色进行血脉蜕变")
    if not bool(context.state.entities.require(actor_id, LIFE).get("alive")):
        raise ValueError("死亡角色不能进行血脉蜕变")
    cultivation = context.state.entities.require(actor_id, CULTIVATION)
    bloodline = context.state.entities.get(actor_id, MONSTER_BLOODLINE)
    if cultivation.get("path") != "monster" or bloodline is None or not _loaded(definitions):
        raise ValueError("当前角色没有启用妖修血脉体系")
    if bloodline.get("species_id") is None or bloodline.get("frozen"):
        raise ValueError("妖修本源尚未确定或血脉已冻结")
    story = context.state.entities.get(actor_id, STORY_STATE) or {}
    trial = context.state.entities.get(actor_id, TRIAL) or {}
    if story.get("pending") is not None or trial.get("active") is not None:
        raise ValueError("请先处理当前事件或突破试炼")
    realm = definitions.realm(str(cultivation["realm_id"]))
    required = _required_opportunity(definitions, cultivation)
    if (
        cultivation.get("bottleneck") != "major"
        or int(cultivation["layer"]) < realm.layers
        or float(cultivation["opportunity"]) < required
    ):
        raise ValueError("尚未抵达机缘圆满的大境界瓶颈")
    candidate = next(
        (row for row in evolution_candidates(context.state, definitions, actor_id)
         if row["id"] == evolution_id),
        None,
    )
    if candidate is None:
        raise ValueError("所选形态不属于当前进化支系")
    if not candidate["enabled"]:
        raise ValueError("尚未满足这一形态的进化条件")
    return candidate


def _complete_evolution(
    context: SimulationContext, definitions: GameDefinitions,
    actor_id: str, evolution_id: str, candidate: dict[str, Any],
) -> None:
    cultivation = context.state.entities.require(actor_id, CULTIVATION)
    bloodline = context.state.entities.require(actor_id, MONSTER_BLOODLINE)
    life = context.state.entities.require(actor_id, LIFE)
    condition = context.state.entities.require(actor_id, CONDITION)
    old_realm_id = str(cultivation["realm_id"])
    old_realm_index = definitions.realm_index(old_realm_id)
    old_evolution_id = str(bloodline.get("evolution_id") or "")
    required = _required_opportunity(definitions, cultivation)
    cultivation["opportunity"] = max(0.0, float(cultivation["opportunity"]) - required)
    cultivation["active_breakthrough_aids"] = []
    cultivation["heart_demon"] = max(0.0, float(cultivation.get("heart_demon", 0.0)) - 5.0)
    cultivation["bottleneck"] = None
    target = definitions.realms[old_realm_index + 1]
    cultivation["realm_id"] = target.id
    cultivation["layer"] = 1
    if evolution_id != "__stable__":
        bloodline["evolution_id"] = evolution_id
        history = list(bloodline.get("evolution_history", []))
        if evolution_id not in history:
            history.append(evolution_id)
        bloodline["evolution_history"] = history
    bloodline["pending_lineage_editor"] = None
    lifespan_gain = int(candidate.get("lifespan_gain", 0))
    if target.lifespan is None:
        life["lifespan"] = None
    elif life.get("lifespan") is not None:
        rolled = context.rng.randint(*target.lifespan) * 3
        life["lifespan"] = max(int(life["lifespan"]), rolled) + lifespan_gain
    condition.update(hp_ratio=1.0, mp_ratio=1.0)
    context.state.entities.put(actor_id, CULTIVATION, cultivation)
    context.state.entities.put(actor_id, MONSTER_BLOODLINE, bloodline)
    context.state.entities.put(actor_id, LIFE, life)
    context.state.entities.put(actor_id, CONDITION, condition)
    context.emit(
        "character.lifespan.changed", source=MONSTER_DLC,
        scope=EventScope.entity(actor_id),
        payload={"entity_id": actor_id, "lifespan": life.get("lifespan")},
    )
    context.emit(
        "cultivation.breakthrough.succeeded", source=MONSTER_DLC,
        scope=EventScope.entity(actor_id),
        payload={
            "entity_id": actor_id, "kind": "major", "chance": 1.0,
            "from_realm_id": old_realm_id,
            "from_layer": definitions.realm(old_realm_id).layers,
            "to_realm_id": target.id, "to_layer": 1,
            "lifespan_gain": lifespan_gain, "automatic": False,
        },
    )
    context.emit(
        "dlc.monster.evolution.completed", source=MONSTER_DLC,
        scope=EventScope.entity(actor_id),
        payload={
            "entity_id": actor_id, "from_evolution_id": old_evolution_id,
            "to_evolution_id": bloodline.get("evolution_id"),
            "selected_evolution_id": evolution_id, "lifespan_gain": lifespan_gain,
        },
    )
    if old_realm_index == 8:
        context.emit(
            "world.monster_ascension.requested", source=MONSTER_DLC,
            scope=EventScope.entity(actor_id),
            payload={"actor_id": actor_id, "destination_world_id": "nether"},
        )


def _evolve_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, EvolveMonster):
            raise TypeError("命令类型错误")
        candidate = _ensure_ready(context, definitions, command.actor_id, command.evolution_id)
        if _stage(command.evolution_id):
            raise ValueError("自成血脉必须先进入立祖界面并确认祖血规则")
        _complete_evolution(context, definitions, command.actor_id, command.evolution_id, candidate)

    return handler


def _index(config: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    return {str(row["id"]): dict(row) for row in config.get(key, [])}


def _value(config: dict[str, Any], pool: str, raw: Any) -> dict[str, Any] | None:
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    return next(
        (dict(row) for row in dict(config.get("values", {})).get(pool, [])
         if abs(float(row["value"]) - number) < 1e-9),
        None,
    )


def _deed_budget(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
) -> dict[str, Any]:
    config = dict(_settings(definitions).get("custom_lineage", {}))
    bloodline = state.entities.require(actor_id, MONSTER_BLOODLINE)
    rows = [{
        "id": "founder_base", "name": "立祖根基", "source": "固定",
        "points": max(0, int(config.get("founder_base_points", 0))),
    }]
    history = set(map(str, bloodline.get("evolution_history", [])))
    trial_history = list((state.entities.get(actor_id, TRIAL) or {}).get("history", []))
    completed_trials = sum(1 for row in trial_history if row.get("result") == "completed")
    story_history = list((state.entities.get(actor_id, STORY_STATE) or {}).get("history", []))
    for deed in config.get("deed_definitions", []):
        kind = str(deed.get("kind", ""))
        matched = (
            kind == "evolution" and str(deed.get("evolution_id", "")) in history
            or kind == "tribulation" and completed_trials >= int(deed.get("threshold", 1))
            or kind == "history" and any(
                row.get("event_id") == deed.get("event_id")
                and (not deed.get("result") or row.get("result") == deed.get("result"))
                and (not deed.get("choice_id") or row.get("choice_id") == deed.get("choice_id"))
                for row in story_history if isinstance(row, dict)
            )
        )
        if matched:
            rows.append({
                "id": str(deed["id"]), "name": str(deed["name"]),
                "source": kind, "points": max(0, int(deed.get("points", 0))),
            })
    recorded = {
        str(row["id"]): dict(row) for row in config.get("deed_definitions", [])
        if row.get("kind") == "recorded"
    }
    for deed_id, count in dict(bloodline.get("lineage_deeds", {})).items():
        definition = recorded.get(str(deed_id))
        if definition and int(count) > 0:
            credited = min(max(1, int(definition.get("cap", 1))), int(count))
            rows.append({
                "id": str(deed_id), "name": str(definition["name"]),
                "source": "recorded",
                "points": credited * max(0, int(definition.get("points", 0))),
            })
    return {"total": sum(int(row["points"]) for row in rows), "breakdown": rows}


def _normalize_rules(
    raw_rules: Any, config: dict[str, Any], *, slots: int, budget: int,
    existing: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(raw_rules, (list, tuple)):
        raise ValueError("自创血脉规则必须为数组")
    if len(raw_rules) > slots:
        raise ValueError(f"当前阶段最多铭刻 {slots} 条祖血规则")
    phases, schedules = _index(config, "phases"), _index(config, "schedules")
    conditions, targets, effects = (
        _index(config, "conditions"), _index(config, "targets"), _index(config, "effects")
    )
    normalized = []
    for raw in raw_rules:
        if not isinstance(raw, dict):
            raise ValueError("自创血脉规则格式不合法")
        rule = {key: str(raw.get(key, "")) for key in (
            "phase", "schedule", "condition", "target", "effect"
        )}
        phase, schedule = phases.get(rule["phase"]), schedules.get(rule["schedule"])
        condition, target, effect = (
            conditions.get(rule["condition"]), targets.get(rule["target"]),
            effects.get(rule["effect"]),
        )
        if not all((phase, schedule, condition, target, effect)):
            raise ValueError("自创血脉规则包含未知组件")
        if rule["target"] not in effect.get("targets", []) or rule["phase"] not in effect.get("phases", []):
            raise ValueError("自创血脉规则的作用目标或时点不合法")
        value = _value(config, str(effect["value_pool"]), raw.get("value"))
        if value is None:
            raise ValueError("自创血脉规则的效果档位不合法")
        rule["value"] = float(value["value"])
        rule["cost"] = max(
            int(dict(config.get("cost_rules", {})).get("minimum", config.get("minimum_rule_cost", 1))),
            int(schedule.get("cost", 0)) + int(effect.get("cost", 0))
            + int(value.get("cost", 0)) + int(target.get("cost", 0))
            - int(condition.get("discount", 0)),
        )
        normalized.append(rule)
    frozen = existing or []
    immutable = ("phase", "schedule", "condition", "target", "effect", "value")
    if len(normalized) < len(frozen):
        raise ValueError("已经铭刻的祖血规则不能删除")
    for index, old in enumerate(frozen):
        if any(normalized[index].get(key) != old.get(key) for key in immutable):
            raise ValueError("已经铭刻的祖血规则不能修改")
    spent = sum(int(rule["cost"]) for rule in normalized)
    if spent > budget:
        raise ValueError(f"祖血功业点不足：需要 {spent}，当前仅有 {budget}")
    return normalized, spent


def _editor_payload(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
    evolution_id: str, stage: int, retroactive: bool,
) -> dict[str, Any]:
    config = dict(_settings(definitions).get("custom_lineage", {}))
    bloodline = state.entities.require(actor_id, MONSTER_BLOODLINE)
    return {
        "evolution_id": evolution_id, "retroactive": retroactive,
        "stage": stage,
        "stage_name": dict(config.get("stage_names", {})).get(str(stage), "立祖"),
        "slots": int(dict(config.get("rule_slots", {})).get(str(stage), 0)),
        "deeds": _deed_budget(state, definitions, actor_id),
        "existing": copy.deepcopy(bloodline.get("custom_lineage")),
        "components": {
            key: copy.deepcopy(config.get(key, []))
            for key in ("phases", "schedules", "conditions", "targets", "effects")
        },
        "values": copy.deepcopy(config.get("values", {})),
        "minimum_rule_cost": int(config.get("minimum_rule_cost", 1)),
        "irreversible": True,
    }


def _prepare_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, PrepareCustomLineage):
            raise TypeError("命令类型错误")
        bloodline = context.state.entities.require(command.actor_id, MONSTER_BLOODLINE)
        retroactive = command.evolution_id == "__retroactive__"
        if retroactive:
            stage = _stage(str(bloodline.get("evolution_id")))
            if not stage or isinstance(bloodline.get("custom_lineage"), dict):
                raise ValueError("当前存档不需要补刻祖血")
        else:
            _ensure_ready(context, definitions, command.actor_id, command.evolution_id)
            stage = _stage(command.evolution_id)
            if not stage:
                raise ValueError("所选进化不是自成血脉路线")
            if stage > 1 and not isinstance(bloodline.get("custom_lineage"), dict):
                raise ValueError("旧版自立血脉须先完成一次补刻祖血")
        bloodline["pending_lineage_editor"] = {
            "evolution_id": command.evolution_id, "stage": stage,
            "retroactive": retroactive, "opened_year": context.state.clock.year,
        }
        context.state.entities.put(command.actor_id, MONSTER_BLOODLINE, bloodline)
        context.emit(
            "dlc.monster.custom_lineage.prepared", source=MONSTER_DLC,
            scope=EventScope.entity(command.actor_id),
            payload={"entity_id": command.actor_id, **bloodline["pending_lineage_editor"]},
        )

    return handler


def _confirm_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ConfirmCustomLineage):
            raise TypeError("命令类型错误")
        bloodline = context.state.entities.require(command.actor_id, MONSTER_BLOODLINE)
        pending = bloodline.get("pending_lineage_editor")
        if not isinstance(pending, dict) or pending.get("evolution_id") != command.evolution_id:
            raise ValueError("请先打开对应的立祖界面")
        retroactive = bool(pending.get("retroactive"))
        candidate = None if retroactive else _ensure_ready(
            context, definitions, command.actor_id, command.evolution_id
        )
        clean_name = " ".join(str(command.name).strip().split())
        if not 2 <= len(clean_name) <= 16 or any(ord(char) < 32 for char in clean_name):
            raise ValueError("祖血名称须为2至16个可显示字符")
        existing = bloodline.get("custom_lineage")
        if isinstance(existing, dict) and clean_name != existing.get("name"):
            raise ValueError("立祖后不能改名")
        config = dict(_settings(definitions).get("custom_lineage", {}))
        stage = int(pending["stage"])
        deeds = _deed_budget(context.state, definitions, command.actor_id)
        rules, spent = _normalize_rules(
            command.rules, config,
            slots=int(dict(config.get("rule_slots", {})).get(str(stage), 0)),
            budget=int(deeds["total"]),
            existing=list(existing.get("rules", [])) if isinstance(existing, dict) else None,
        )
        if not isinstance(existing, dict) and not rules:
            raise ValueError("立祖或补刻祖血时至少需要铭刻一条规则")
        lineage = copy.deepcopy(existing) if isinstance(existing, dict) else {
            "id": f"custom-lineage:{context.state.game_id}:{context.state.next_event_sequence:010d}",
            "founder_year": context.state.clock.year,
            "founder_species_id": bloodline.get("species_id"),
            "created_realm_index": definitions.realm_index(
                str(context.state.entities.require(command.actor_id, CULTIVATION)["realm_id"])
            ),
        }
        lineage.update({
            "name": clean_name, "rules": rules, "spent_points": spent,
            "finalized_stage": stage,
        })
        bloodline["custom_lineage_id"] = str(lineage["id"])
        bloodline["custom_lineage"] = lineage
        bloodline["pending_lineage_editor"] = None
        context.state.entities.put(command.actor_id, MONSTER_BLOODLINE, bloodline)
        context.emit(
            "dlc.monster.custom_lineage.inscribed", source=MONSTER_DLC,
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id, "custom_lineage_id": lineage["id"],
                "stage": stage, "spent_points": spent, "retroactive": retroactive,
            },
        )
        if not retroactive:
            assert candidate is not None
            _complete_evolution(
                context, definitions, command.actor_id, command.evolution_id, candidate
            )

    return handler


def monster_combat_profile(
    state: WorldState, definitions: GameDefinitions, entity_id: str,
) -> dict[str, Any] | None:
    bloodline = state.entities.get(entity_id, MONSTER_BLOODLINE)
    if bloodline is None or bloodline.get("frozen") or not _loaded(definitions):
        return None
    node = _evolutions(definitions).get(str(bloodline.get("evolution_id") or ""))
    if node is None:
        return None
    return {
        "evolution_id": node["id"], "name": node["name"],
        "stat_multipliers": {
            key: max(0.01, float(dict(node.get("profile", {})).get(key, 1.0)))
            for key in _STAT_KEYS
        },
        "traits": list(dict.fromkeys([
            *map(str, node.get("traits", [])),
            *map(str, bloodline.get("traits", [])),
        ])),
        "abilities": list(map(str, node.get("abilities", []))),
        "custom_lineage_id": bloodline.get("custom_lineage_id"),
    }


def evaluate_custom_lineage(
    state: WorldState, definitions: GameDefinitions, entity_id: str, *,
    phase: str, round_no: int, terrain: str,
    owner_state: float, enemy_state: float,
    owner_morale: float, enemy_morale: float,
) -> dict[str, Any]:
    output = {
        "owner_stat_multipliers": {}, "enemy_stat_multipliers": {},
        "owner_state_delta": 0.0, "enemy_state_delta": 0.0,
        "owner_morale_delta": 0.0, "enemy_morale_delta": 0.0,
        "events": [],
    }
    bloodline = state.entities.get(entity_id, MONSTER_BLOODLINE) or {}
    lineage = bloodline.get("custom_lineage")
    if not isinstance(lineage, dict):
        return output
    config = dict(_settings(definitions).get("custom_lineage", {}))
    phases, schedules = _index(config, "phases"), _index(config, "schedules")
    conditions, targets, effects = (
        _index(config, "conditions"), _index(config, "targets"), _index(config, "effects")
    )

    def scheduled(schedule_id: str) -> bool:
        return {
            "every": True, "odd": round_no % 2 == 1, "even": round_no % 2 == 0,
            "first_two": round_no <= 2, "first_three": round_no <= 3,
            **{f"round_{number}": round_no == number for number in range(1, 6)},
        }.get(schedule_id, False)

    def condition_met(row: dict[str, Any]) -> bool:
        kind, value = row.get("kind"), row.get("value")
        if kind == "always":
            return True
        if kind == "terrain":
            return terrain == str(value)
        if kind == "artificial":
            return str(value) in terrain
        if kind == "state":
            actual = owner_state if row.get("subject") == "player" else enemy_state
            return actual <= float(value)
        if kind == "morale":
            actual = owner_morale if row.get("subject") == "player" else enemy_morale
            return actual <= float(value)
        return False

    for raw in lineage.get("rules", []):
        if not isinstance(raw, dict) or raw.get("phase") != phase or phase not in phases:
            continue
        schedule = schedules.get(str(raw.get("schedule")))
        condition = conditions.get(str(raw.get("condition")))
        target = targets.get(str(raw.get("target")))
        effect = effects.get(str(raw.get("effect")))
        if not all((schedule, condition, target, effect)):
            continue
        if not scheduled(str(schedule["id"])) or not condition_met(condition):
            continue
        value = _value(config, str(effect.get("value_pool", "")), raw.get("value"))
        target_id = str(target["id"])
        if value is None or target_id not in effect.get("targets", []) or phase not in effect.get("phases", []):
            continue
        amount = float(value["value"])
        prefix = "owner" if target_id == "player" else "enemy"
        if effect["kind"] == "modify_stat" and effect.get("stat") in _STAT_KEYS:
            bucket = output[f"{prefix}_stat_multipliers"]
            bucket[str(effect["stat"])] = (
                1.0 + amount if prefix == "owner" else max(0.0, 1.0 - amount)
            )
        elif effect["kind"] == "restore_combat_state":
            output[f"{prefix}_state_delta"] += amount
        elif effect["kind"] == "modify_morale":
            output[f"{prefix}_morale_delta"] += amount if prefix == "owner" else -amount
        output["events"].append({
            "lineage_id": lineage.get("id"), "rule": copy.deepcopy(raw),
            "owner_id": entity_id, "target": target_id,
        })
    return output


def monster_invariants(definitions: GameDefinitions):
    def validate(state: WorldState) -> list[str]:
        errors = []
        species, evolutions = _species(definitions), _evolutions(definitions)
        for entity_id in state.entities.with_component(MONSTER_BLOODLINE):
            bloodline = state.entities.require(entity_id, MONSTER_BLOODLINE)
            species_id = bloodline.get("species_id")
            current_id = bloodline.get("evolution_id")
            if species_id is not None and species_id not in species:
                errors.append(f"妖修 {entity_id} 的本源谱系非法")
            if current_id is not None:
                node = evolutions.get(str(current_id))
                if node is None or node.get("species") != species_id:
                    errors.append(f"妖修 {entity_id} 的当前进化形态非法")
                history = list(map(str, bloodline.get("evolution_history", [])))
                if not history or history[-1] != current_id:
                    errors.append(f"妖修 {entity_id} 的进化历史未落在当前形态")
            lineage = bloodline.get("custom_lineage")
            if isinstance(lineage, dict) and lineage.get("id") != bloodline.get("custom_lineage_id"):
                errors.append(f"妖修 {entity_id} 的自创血脉标识不一致")
        return errors

    return validate


def register_monster_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(EvolveMonster, _evolve_handler(definitions))
    bus.register(PrepareCustomLineage, _prepare_handler(definitions))
    bus.register(ConfirmCustomLineage, _confirm_handler(definitions))


def monster_view(
    state: WorldState, definitions: GameDefinitions, entity_id: str | None = None,
) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    cultivation = state.entities.require(actor_id, CULTIVATION)
    bloodline = state.entities.get(actor_id, MONSTER_BLOODLINE)
    if cultivation.get("path") != "monster":
        return {"visible": False, "available": _loaded(definitions)}
    if bloodline is None or not _loaded(definitions):
        return {"visible": True, "available": False}
    species = _species(definitions)
    evolutions = _evolutions(definitions)
    current = evolutions.get(str(bloodline.get("evolution_id") or ""))
    realm = definitions.realm(str(cultivation["realm_id"]))
    ready = bool(
        cultivation.get("bottleneck") == "major"
        and int(cultivation["layer"]) >= realm.layers
        and float(cultivation["opportunity"]) >= _required_opportunity(definitions, cultivation)
    )
    pending = bloodline.get("pending_lineage_editor")
    editor = None
    if isinstance(pending, dict):
        editor = _editor_payload(
            state, definitions, actor_id, str(pending["evolution_id"]),
            int(pending["stage"]), bool(pending["retroactive"]),
        )
    return {
        "visible": True, "available": True,
        "species": copy.deepcopy(species.get(str(bloodline.get("species_id")))),
        "current": copy.deepcopy(current),
        "history": [
            {"id": evolution_id, "name": evolutions.get(evolution_id, {}).get("name", evolution_id)}
            for evolution_id in map(str, bloodline.get("evolution_history", []))
        ],
        "adaptations": list(bloodline.get("adaptations", [])),
        "imprints": list(bloodline.get("imprints", [])),
        "acquired_traits": list(bloodline.get("traits", [])),
        "awaiting_evolution": ready,
        "candidates": evolution_candidates(state, definitions, actor_id) if ready else [],
        "custom_lineage": copy.deepcopy(bloodline.get("custom_lineage")),
        "custom_lineage_retroactive_available": bool(
            _stage(str(bloodline.get("evolution_id")))
            and not isinstance(bloodline.get("custom_lineage"), dict)
        ),
        "custom_lineage_editor": editor,
        "irreversible": True,
    }

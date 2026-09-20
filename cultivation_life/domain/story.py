from __future__ import annotations

import copy
import operator
import re
from dataclasses import dataclass
from typing import Any, Callable, ClassVar

from .actions import resume_action
from .character import IDENTITY, LIFE, create_character
from .combat import CONDITION, combat_snapshot
from .cultivation import CULTIVATION, PRACTICE
from .definitions import GameDefinitions, StoryEffectDefinition, StoryEventDefinition
from .economy import INVENTORY, regional_market_goods
from .factions import MEMBERSHIP
from .world import AscendWorld, LOCATION, WORLD_TRANSITION, _ascend_handler
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


STORY_STATE = "story.state"

_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": operator.eq,
    "neq": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "contains": lambda actual, expected: expected in actual,
}


@dataclass(frozen=True, slots=True)
class ResolveStoryChoice:
    actor_id: str
    choice_id: str
    allow_during_interaction: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class QueueStoryEvent:
    actor_id: str
    event_id: str
    reason: str = "scripted"


@dataclass(frozen=True, slots=True)
class RepairPendingStoryEvent:
    """Upgrade a pending event snapshot created by an older runtime."""

    actor_id: str
    allow_during_interaction: ClassVar[bool] = True
    allow_during_court_election: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class BeginSpiritCrossing:
    actor_id: str
    invited_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EffectOutcome:
    result: str | None
    summary: str


EffectHandler = Callable[
    [SimulationContext, str, StoryEffectDefinition, dict[str, Any]], EffectOutcome
]


def _default_story_state() -> dict[str, Any]:
    return {
        "pending": None,
        "queue": [],
        "history": [],
        "flags": [],
        "milestones": {},
        "trigger_attempts": {},
        "attributes": {"karma": 0.0, "fame": 0.0, "sha_qi": 0.0},
        "spirit_crossing": {
            "attempted": False,
            "active": False,
            "destination": None,
            "invited_ids": [],
        },
    }


def reconcile_story_state(state: WorldState) -> None:
    for entity_id in state.entities.with_component(IDENTITY):
        current = state.entities.get(entity_id, STORY_STATE)
        if current is None:
            state.entities.put(entity_id, STORY_STATE, _default_story_state())
            continue
        default = _default_story_state()
        for key, value in default.items():
            current.setdefault(key, copy.deepcopy(value))
        state.entities.put(entity_id, STORY_STATE, current)


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    context.state.entities.put(str(event.payload["entity_id"]), STORY_STATE, _default_story_state())


def _on_character_died(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    story = context.state.entities.get(entity_id, STORY_STATE)
    if story is None:
        return
    crossing = dict(story.get("spirit_crossing", {}))
    if crossing.get("active"):
        crossing["active"] = False
        crossing["failed_year"] = context.state.clock.year
        crossing["failure_reason"] = str(event.payload.get("reason", "偷渡失败"))
        story["spirit_crossing"] = crossing
        context.state.entities.put(entity_id, STORY_STATE, story)


class StoryEffectRegistry:
    """Registry of effect kinds that are safe to execute inside the simulation.

    Event files may contain effects owned by domains that have not migrated
    yet.  Such event chains remain loaded for diagnostics but cannot be
    selected until their effect handlers are registered.
    """

    def __init__(self, definitions: GameDefinitions):
        self.definitions = definitions
        self._handlers: dict[str, EffectHandler] = {}
        self._compatible_cache: frozenset[str] | None = None
        self._register_builtins()

    @property
    def supported_kinds(self) -> frozenset[str]:
        return frozenset(self._handlers)

    def register(self, kind: str, handler: EffectHandler) -> None:
        if not kind or kind in self._handlers:
            raise ValueError(f"剧情效果处理器重复或非法：{kind}")
        self._handlers[kind] = handler
        self._compatible_cache = None

    def compatible_event_ids(self) -> frozenset[str]:
        if self._compatible_cache is None:
            self._compatible_cache = _compatible_event_ids(self.definitions, self)
        return self._compatible_cache

    def execute(
        self,
        context: SimulationContext,
        actor_id: str,
        effect: StoryEffectDefinition,
        pending: dict[str, Any],
    ) -> EffectOutcome:
        handler = self._handlers.get(effect.kind)
        if handler is None:
            raise ValueError(f"剧情效果尚未迁移：{effect.kind}")
        return handler(context, actor_id, effect, pending)

    def _register_builtins(self) -> None:
        for kind in ("add_karma", "add_fame", "add_sha_qi"):
            self.register(kind, self._change_story_attribute)
        self.register("add_heart_demon", self._change_heart_demon)
        self.register("add_opportunity", self._change_opportunity)
        self.register("set_flag", self._set_flag)
        self.register("remove_flag", self._remove_flag)
        self.register("set_milestone", self._set_milestone)
        self.register("add_item", self._change_item)
        self.register("remove_item", self._change_item)
        self.register("learn_technique", self._learn_technique)
        self.register("equip_technique", self._equip_technique)
        for kind in ("heal", "restore_hp", "restore_mp", "damage"):
            self.register(kind, self._change_condition)
        self.register("extend_lifespan", self._extend_lifespan)
        self.register("add_faction_contribution", self._change_contribution)
        self.register("queue_event", self._queue_event)

    @staticmethod
    def _value(context: SimulationContext, effect: StoryEffectDefinition) -> float:
        payload = effect.payload
        if "range" in payload:
            low, high = payload["range"]
            return float(context.rng.randint(int(low), int(high)))
        return float(payload.get("value", 0))

    def _change_story_attribute(
        self, context: SimulationContext, actor_id: str,
        effect: StoryEffectDefinition, pending: dict[str, Any],
    ) -> EffectOutcome:
        state = context.state.entities.require(actor_id, STORY_STATE)
        attributes = dict(state["attributes"])
        key = {
            "add_karma": "karma", "add_fame": "fame", "add_sha_qi": "sha_qi",
        }[effect.kind]
        value = self._value(context, effect)
        attributes[key] = float(attributes.get(key, 0.0)) + value
        state["attributes"] = attributes
        context.state.entities.put(actor_id, STORY_STATE, state)
        label = {"karma": "因果", "fame": "声望", "sha_qi": "煞气"}[key]
        return EffectOutcome(None, f"{label} {value:+g}")

    def _change_heart_demon(
        self, context: SimulationContext, actor_id: str,
        effect: StoryEffectDefinition, pending: dict[str, Any],
    ) -> EffectOutcome:
        value = self._value(context, effect)
        context.emit(
            "story.effect.cultivation.changed",
            source="story",
            scope=EventScope.entity(actor_id),
            payload={"entity_id": actor_id, "field": "heart_demon", "amount": value},
        )
        return EffectOutcome(None, f"心魔 {value:+g}")

    def _change_opportunity(
        self, context: SimulationContext, actor_id: str,
        effect: StoryEffectDefinition, pending: dict[str, Any],
    ) -> EffectOutcome:
        value = self._value(context, effect)
        context.emit(
            "story.effect.cultivation.changed",
            source="story",
            scope=EventScope.entity(actor_id),
            payload={"entity_id": actor_id, "field": "opportunity", "amount": value},
        )
        return EffectOutcome(None, f"机缘 {value:+g}")

    def _set_flag(
        self, context: SimulationContext, actor_id: str,
        effect: StoryEffectDefinition, pending: dict[str, Any],
    ) -> EffectOutcome:
        state = context.state.entities.require(actor_id, STORY_STATE)
        flags = list(map(str, state.get("flags", [])))
        flag = str(effect.payload["flag"])
        if flag not in flags:
            flags.append(flag)
        state["flags"] = flags
        context.state.entities.put(actor_id, STORY_STATE, state)
        return EffectOutcome(None, str(effect.payload.get("text", "命途留下了新的印记。")))

    def _remove_flag(
        self, context: SimulationContext, actor_id: str,
        effect: StoryEffectDefinition, pending: dict[str, Any],
    ) -> EffectOutcome:
        state = context.state.entities.require(actor_id, STORY_STATE)
        flag = str(effect.payload["flag"])
        state["flags"] = [value for value in state.get("flags", []) if value != flag]
        context.state.entities.put(actor_id, STORY_STATE, state)
        return EffectOutcome(None, str(effect.payload.get("text", "一段因果就此了结。")))

    def _set_milestone(
        self, context: SimulationContext, actor_id: str,
        effect: StoryEffectDefinition, pending: dict[str, Any],
    ) -> EffectOutcome:
        state = context.state.entities.require(actor_id, STORY_STATE)
        milestones = dict(state.get("milestones", {}))
        milestones.setdefault(str(effect.payload["milestone"]), context.state.clock.year)
        state["milestones"] = milestones
        context.state.entities.put(actor_id, STORY_STATE, state)
        return EffectOutcome(None, str(effect.payload.get("text", "这一年被记入命途节点。")))

    def _change_item(
        self, context: SimulationContext, actor_id: str,
        effect: StoryEffectDefinition, pending: dict[str, Any],
    ) -> EffectOutcome:
        item_id = str(effect.payload["item_id"])
        quantity = int(effect.payload.get("quantity", 1))
        if quantity <= 0 or item_id not in self.definitions.items:
            raise ValueError("剧情物品效果非法")
        delta = quantity if effect.kind == "add_item" else -quantity
        context.emit(
            "story.effect.inventory.changed",
            source="story",
            scope=EventScope.entity(actor_id),
            payload={
                "entity_id": actor_id, "item_id": item_id,
                "quantity": delta, "reason": "story",
            },
        )
        verb = "获得" if delta > 0 else "失去"
        return EffectOutcome(None, f"{verb}{self.definitions.items[item_id].name} ×{quantity}")

    def _learn_technique(
        self, context: SimulationContext, actor_id: str,
        effect: StoryEffectDefinition, pending: dict[str, Any],
    ) -> EffectOutcome:
        technique_id = str(effect.payload["technique_id"])
        context.emit(
            "story.effect.technique.learned",
            source="story",
            scope=EventScope.entity(actor_id),
            payload={"entity_id": actor_id, "technique_id": technique_id},
        )
        return EffectOutcome(None, f"学会{self.definitions.techniques[technique_id].name}")

    def _equip_technique(
        self, context: SimulationContext, actor_id: str,
        effect: StoryEffectDefinition, pending: dict[str, Any],
    ) -> EffectOutcome:
        technique_id = str(effect.payload["technique_id"])
        context.emit(
            "story.effect.technique.equipped",
            source="story",
            scope=EventScope.entity(actor_id),
            payload={
                "entity_id": actor_id,
                "technique_id": technique_id,
                "slot": str(effect.payload.get("slot", "main")),
            },
        )
        return EffectOutcome(None, f"学会{self.definitions.techniques[technique_id].name}并设为主修")

    def _change_condition(
        self, context: SimulationContext, actor_id: str,
        effect: StoryEffectDefinition, pending: dict[str, Any],
    ) -> EffectOutcome:
        value = self._value(context, effect)
        condition = context.state.entities.require(actor_id, CONDITION)
        snapshot = combat_snapshot(context.state, self.definitions, actor_id)
        context.emit(
            "story.effect.combat_condition.changed",
            source="story",
            scope=EventScope.entity(actor_id),
            payload={
                "entity_id": actor_id, "kind": effect.kind, "amount": value,
                "reason": str(effect.payload.get("reason", "剧情中伤势过重")),
            },
        )
        if effect.kind == "damage":
            points = round(float(snapshot["max_hp"]) * min(
                max(0.0, value), float(condition["hp_ratio"])
            ))
            if float(condition["hp_ratio"]) - value <= 0:
                return EffectOutcome("dead", f"受到 {points} 点伤害并陨落")
            return EffectOutcome("injured", f"受到 {points} 点伤害")
        key = "mp_ratio" if effect.kind == "restore_mp" else "hp_ratio"
        maximum = float(snapshot["max_mp"] if key == "mp_ratio" else snapshot["max_hp"])
        current_ratio = float(condition[key])
        applied_ratio = (
            min(value, 1.0 - current_ratio)
            if value >= 0 else -min(-value, current_ratio)
        )
        points = round(maximum * abs(applied_ratio))
        resource = "MP" if key == "mp_ratio" else "HP"
        verb = "恢复" if applied_ratio >= 0 else "消耗"
        return EffectOutcome(None, f"{resource} {verb} {points}")

    def _extend_lifespan(
        self, context: SimulationContext, actor_id: str,
        effect: StoryEffectDefinition, pending: dict[str, Any],
    ) -> EffectOutcome:
        value = int(self._value(context, effect))
        cultivation = context.state.entities.require(actor_id, CULTIVATION)
        if self.definitions.realm_index(str(cultivation["realm_id"])) != 0:
            return EffectOutcome(None, "你已踏入仙途，凡俗炼体不再改变寿元。")
        life = context.state.entities.require(actor_id, LIFE)
        if life.get("lifespan") is None:
            return EffectOutcome(None, "当前生命形态不受凡俗寿元约束。")
        old = int(life["lifespan"])
        age = context.state.clock.year - int(life["birth_year"])
        life["lifespan"] = min(300, max(old, age + 1) + value)
        context.state.entities.put(actor_id, LIFE, life)
        context.emit(
            "character.lifespan.changed",
            source="story",
            scope=EventScope.entity(actor_id),
            payload={"entity_id": actor_id, "lifespan": life["lifespan"]},
        )
        return EffectOutcome(
            None, f"炼体延寿，寿元上限由 {old} 提升至 {life['lifespan']} 岁。"
        )

    def _change_contribution(
        self, context: SimulationContext, actor_id: str,
        effect: StoryEffectDefinition, pending: dict[str, Any],
    ) -> EffectOutcome:
        value = int(self._value(context, effect))
        context.emit(
            "story.effect.faction_contribution.changed",
            source="story",
            scope=EventScope.entity(actor_id),
            payload={"entity_id": actor_id, "amount": value},
        )
        return EffectOutcome(None, f"势力贡献 {value:+d}")

    def _queue_event(
        self, context: SimulationContext, actor_id: str,
        effect: StoryEffectDefinition, pending: dict[str, Any],
    ) -> EffectOutcome:
        queue_story_event(
            context, self.definitions, actor_id,
            str(effect.payload["event_id"]), reason=f"followup:{pending['id']}",
        )
        return EffectOutcome(None, str(effect.payload.get("text", "新的因果接踵而至。")))


def _path_value(
    state: WorldState, actor_id: str, path: str, definitions: GameDefinitions,
) -> Any:
    cultivation = state.entities.require(actor_id, CULTIVATION)
    location = state.entities.require(actor_id, LOCATION)
    life = state.entities.require(actor_id, LIFE)
    practice = state.entities.require(actor_id, PRACTICE)
    story = state.entities.require(actor_id, STORY_STATE)
    legacy = dict(story.get("legacy_effect_state", {}))
    mortal = dict(legacy.get("mortal", {}))
    body = state.entities.get(actor_id, "cultivation.body") or {}
    monster = state.entities.get(actor_id, "dlc.monster.bloodline") or {}
    membership = next(iter(state.relations.find(source_id=actor_id, kind=MEMBERSHIP)), None)
    raw_karma = float(story["attributes"].get("karma", 0))
    main_id = practice.get("main_technique_id")
    technique = definitions.techniques.get(str(main_id)) if main_id else None
    karma_factor = (
        0.0 if cultivation.get("path") == "demonic" else
        float(definitions.systems.get("karma_factors", {}).get(
            technique.path if technique else cultivation.get("path"), 1.0
        )) * (float(technique.karma_multiplier) if technique else 1.0)
    )
    values = {
        "player.world": location["world_id"],
        "player.path": cultivation["path"],
        "player.spirit_root": cultivation["spirit_root"],
        "player.born_rootless": cultivation["spirit_root"] == "none",
        "player.layer": int(cultivation["layer"]),
        "player.age": state.clock.year - int(life["birth_year"]),
        "player.karma": raw_karma,
        "player.effective_karma": max(0.0, raw_karma) * karma_factor,
        "player.fame": float(story["attributes"].get("fame", 0)),
        "player.has_main_technique": bool(practice.get("main_technique_id")),
        "player.has_companion": bool(state.relations.involving(actor_id, kind="dao_companion")),
        "player.has_master": bool(
            state.relations.find(target_id=actor_id, kind="master_disciple")
        ),
        "player.master_available": bool(
            state.relations.find(target_id=actor_id, kind="master_disciple")
        ),
        "player.disciple_total": len(
            state.relations.find(source_id=actor_id, kind="master_disciple", active_only=False)
        ),
        "player.living_disciple_count": len(
            state.relations.find(source_id=actor_id, kind="master_disciple")
        ),
        "player.faction_id": (
            state.entities.require(membership.target_id, "faction.profile").get("external_id")
            if membership else None
        ),
        "player.faction_contribution": (
            int(membership.metadata.get("contribution", 0)) if membership else 0
        ),
        "player.body_training": int(body.get("layer", 0)),
        "player.monster.imprints": list(monster.get("imprints", [])),
        "player.monster_species_id": monster.get("species_id"),
        "player.mortal_aspiration": mortal.get("aspiration"),
        "player.spouse": bool(mortal.get("spouse", False)),
        "player.children": int(mortal.get("children", 0)),
        "player.official_rank": int(mortal.get("official_rank", 0)),
        "player.military_merit": int(mortal.get("military_merit", 0)),
        "player.jianghu_reputation": int(mortal.get("jianghu_reputation", 0)),
    }
    return values.get(path)


def _condition(
    condition: dict[str, Any], state: WorldState, actor_id: str,
    definitions: GameDefinitions,
) -> bool:
    if not condition:
        return True
    if "all" in condition:
        return all(_condition(dict(child), state, actor_id, definitions) for child in condition["all"])
    if "any" in condition:
        return any(_condition(dict(child), state, actor_id, definitions) for child in condition["any"])
    if "not" in condition:
        return not _condition(dict(condition["not"]), state, actor_id, definitions)
    story = state.entities.require(actor_id, STORY_STATE)
    if "has_flag" in condition:
        return str(condition["has_flag"]) in set(map(str, story.get("flags", [])))
    if "has_item" in condition:
        inventory = state.entities.require(actor_id, INVENTORY)
        item_id = str(condition["has_item"])
        quantity = int(condition.get("quantity", 1))
        owned = int(dict(inventory.get("items", {})).get(item_id, 0))
        reserved = int(dict(inventory.get("reserved", {})).get(item_id, 0))
        return owned - reserved >= quantity
    if "knows_technique" in condition:
        practice = state.entities.require(actor_id, PRACTICE)
        return str(condition["knows_technique"]) in set(map(str, practice.get("known_techniques", [])))
    if "has_affinity" in condition:
        cultivation = state.entities.require(actor_id, CULTIVATION)
        roots = [str(cultivation["spirit_root"])]
        affinities = {
            affinity
            for root_id in roots if root_id in definitions.roots
            for affinity in definitions.roots[root_id].elements
        }
        affinities.update(map(str, cultivation.get("additional_roots", [])))
        return str(condition["has_affinity"]) in affinities
    if "world_npc" in condition:
        wanted = dict(condition["world_npc"])
        for entity_id in state.entities.with_component(IDENTITY):
            identity = state.entities.require(entity_id, IDENTITY)
            if str(identity.get("external_id", "")) != str(wanted.get("id", "")):
                continue
            if "alive" in wanted and bool(
                state.entities.require(entity_id, LIFE).get("alive")
            ) != bool(wanted["alive"]):
                continue
            if "world" in wanted and state.entities.require(
                entity_id, LOCATION
            ).get("world_id") != wanted["world"]:
                continue
            return True
        return False
    path = str(condition.get("path", ""))
    op = _OPS.get(str(condition.get("op", "eq")))
    if not path or op is None:
        return False
    if path == "player.realm_index":
        cultivation = state.entities.require(actor_id, CULTIVATION)
        actual = definitions.realm_index(str(cultivation["realm_id"]))
    else:
        actual = _path_value(state, actor_id, path, definitions)
    if actual is None and condition.get("value") is not None and path not in {
        "player.faction_id", "player.mortal_aspiration", "player.spouse",
    }:
        return False
    try:
        return bool(op(actual, condition.get("value")))
    except TypeError:
        return False


def _compatible_event_ids(
    definitions: GameDefinitions, registry: StoryEffectRegistry,
) -> frozenset[str]:
    compatible = set(definitions.story_events)
    while True:
        invalid: set[str] = set()
        for event_id in compatible:
            event = definitions.story_events[event_id]
            for choice in event.choices:
                for effect in choice.effects:
                    if effect.kind not in registry.supported_kinds:
                        invalid.add(event_id)
                    elif effect.kind == "queue_event" and str(effect.payload.get("event_id")) not in compatible:
                        invalid.add(event_id)
        if not invalid:
            return frozenset(compatible)
        compatible -= invalid


def _public_event(
    state: WorldState, actor_id: str, definitions: GameDefinitions,
    event: StoryEventDefinition,
) -> dict[str, Any]:
    return {
        "id": event.id,
        "version": event.version,
        "title": event.title,
        "body": event.body,
        "category": event.category,
        "choices": [
            {
                "id": choice.id,
                "text": choice.text,
                "enabled": _condition(choice.conditions, state, actor_id, definitions),
                "disabled_reason": choice.disabled_reason,
            }
            for choice in event.choices
        ],
        "queued_year": state.clock.year,
    }


_RUNTIME_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _runtime_text(key: str, value: Any) -> str:
    if key in {"target_power", "player_power"} and isinstance(
        value, (int, float)
    ):
        return f"{float(value):.0f}"
    return str(value)


def _render_event_runtime(
    pending: dict[str, Any], runtime: dict[str, Any],
) -> dict[str, Any]:
    """Render every user-visible event field from one canonical runtime map."""

    rendered = copy.deepcopy(pending)

    def substitute(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return _RUNTIME_PLACEHOLDER.sub(
            lambda match: (
                _runtime_text(match.group(1), runtime[match.group(1)])
                if match.group(1) in runtime
                else match.group(0)
            ),
            value,
        )

    rendered["title"] = substitute(rendered.get("title", ""))
    rendered["body"] = substitute(rendered.get("body", ""))
    choices = []
    for raw in rendered.get("choices", []):
        choice = dict(raw)
        choice["text"] = substitute(choice.get("text", ""))
        choice["disabled_reason"] = substitute(choice.get("disabled_reason"))
        choices.append(choice)
    rendered["choices"] = choices
    rendered["runtime"] = copy.deepcopy(runtime)
    return rendered


def _unresolved_event_fields(pending: dict[str, Any]) -> set[str]:
    fields = [pending.get("title", ""), pending.get("body", "")]
    for choice in pending.get("choices", []):
        fields.extend((choice.get("text", ""), choice.get("disabled_reason", "")))
    return {
        match.group(1)
        for value in fields if isinstance(value, str)
        for match in _RUNTIME_PLACEHOLDER.finditer(value)
    }


def pending_story_needs_repair(
    state: WorldState, definitions: GameDefinitions,
) -> bool:
    actor_id = state.controlled_entity_id
    if actor_id is None:
        return False
    story = state.entities.get(actor_id, STORY_STATE) or {}
    pending = story.get("pending")
    if not isinstance(pending, dict):
        return False
    event = definitions.story_events.get(str(pending.get("id", "")))
    if event is None:
        return False
    runtime = dict(pending.get("runtime", {}))
    target_id = str(runtime.get("target_id", ""))
    if event.combat and (
        not target_id
        or not state.entities.exists(target_id)
        or {"target_realm", "target_power"} - set(runtime)
    ):
        return True
    return bool(_unresolved_event_fields(pending))


def _promote_story_queue(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
) -> None:
    story = context.state.entities.require(actor_id, STORY_STATE)
    if story.get("pending") is not None or not story.get("queue"):
        context.state.entities.put(actor_id, STORY_STATE, story)
        return
    queue = list(story["queue"])
    queued = dict(queue.pop(0))
    event = definitions.story_events[str(queued["event_id"])]
    story["queue"] = queue
    pending = _public_event(context.state, actor_id, definitions, event)
    runtime = queued.get("runtime")
    if not isinstance(runtime, dict):
        runtime = _combat_runtime(context, definitions, actor_id, event)
    if isinstance(runtime, dict):
        pending = _render_event_runtime(pending, runtime)
        if event.id == "EVT_TREASURE_REWARD_SELECT_001":
            rewards = dict(runtime.get("rewards", {}))
            labels = {
                "artifact": ("法器", "“", "”"),
                "technique": ("功法", "《", "》"),
                "pill": ("丹药", "“", "”"),
            }
            for choice in pending["choices"]:
                reward = dict(rewards.get(str(choice["id"]), {}))
                if not reward:
                    continue
                label, left, right = labels[str(choice["id"])]
                choice["text"] = (
                    f"选择{label}：{left}{reward['name']}{right}"
                    f"（{int(reward['tier'])}阶）"
                )
    unresolved = _unresolved_event_fields(pending)
    if unresolved:
        raise ValueError(
            f"剧情事件 {event.id} 缺少运行数据：{', '.join(sorted(unresolved))}"
        )
    story["pending"] = pending
    context.state.entities.put(actor_id, STORY_STATE, story)
    context.emit(
        "story.interaction.opened",
        source="story",
        scope=EventScope.entity(actor_id),
        payload={
            "actor_id": actor_id, "event_id": event.id,
            "reason": queued["reason"], "queue_length": len(queue),
        },
    )
    context.halt_time(f"等待处理事件：{event.title}")


def _combat_runtime(
    context: SimulationContext, definitions: GameDefinitions,
    actor_id: str, event: StoryEventDefinition,
) -> dict[str, Any] | None:
    spec = dict(event.combat)
    if not spec:
        return None
    cultivation = context.state.entities.require(actor_id, CULTIVATION)
    identity = context.state.entities.require(actor_id, IDENTITY)
    location = context.state.entities.require(actor_id, LOCATION)
    actor_realm = definitions.realm_index(str(cultivation["realm_id"]))
    offsets = list(spec.get("realm_offsets", [[0, 1.0]]))
    values = [int(row[0]) for row in offsets]
    weights = [max(0.0, float(row[1])) for row in offsets]
    offset = context.rng.choices(values, weights=weights, k=1)[0]
    target_realm_index = max(
        0, min(len(definitions.realms) - 1, actor_realm + offset)
    )
    target_realm = definitions.realms[target_realm_index]
    if target_realm_index < actor_realm:
        layer = target_realm.layers
    elif target_realm_index > actor_realm:
        layer = 1
    else:
        layer = int(cultivation["layer"])
    target_id = create_character(
        context,
        name=str(spec.get("target_name", "因果中人")),
        age=max(18, context.state.clock.year - int(
            context.state.entities.require(actor_id, LIFE)["birth_year"]
        )),
        gender="female" if identity.get("gender") == "male" else "male",
        race=str(spec.get("race", identity.get("race", "human"))),
        spirit_root=(
            "none" if target_realm_index == 0
            else str(spec.get("spirit_root", "supreme_fire"))
        ),
        path=str(spec.get("path", cultivation["path"])),
        realm_id=target_realm.id,
        layer=layer,
        world_id=str(location["world_id"]),
        lifespan=None,
    )
    context.state.entities.put(target_id, LOCATION, dict(location))
    context.state.entities.put(target_id, "story.encounter", {
        "event_id": event.id, "actor_id": actor_id, "resolved": False,
    })
    snapshot = combat_snapshot(context.state, definitions, target_id)
    return {
        **spec,
        "target_id": target_id,
        "target_name": str(spec.get("target_name", "因果中人")),
        "target_realm_id": target_realm.id,
        "target_layer": layer,
        "target_realm": (
            f"{target_realm.name}{layer}层"
            if target_realm_index <= actor_realm + 1 else "无法看清"
        ),
        "target_power": round(float(snapshot["power"]), 1),
        "generated_encounter": True,
    }


def _repair_pending_event_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, RepairPendingStoryEvent):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能修复当前角色的事件")
        story = context.state.entities.require(command.actor_id, STORY_STATE)
        old_pending = story.get("pending")
        if not isinstance(old_pending, dict):
            return
        event = definitions.story_events.get(str(old_pending.get("id", "")))
        if event is None:
            return

        runtime = dict(old_pending.get("runtime", {}))
        target_id = str(runtime.get("target_id", ""))
        if event.combat and (
            not target_id
            or not context.state.entities.exists(target_id)
            or {"target_realm", "target_power"} - set(runtime)
        ):
            generated = _combat_runtime(
                context, definitions, command.actor_id, event
            )
            if generated is not None:
                runtime = {**runtime, **generated}

        repaired = _public_event(
            context.state, command.actor_id, definitions, event
        )
        repaired["queued_year"] = int(
            old_pending.get("queued_year", context.state.clock.year)
        )
        if runtime:
            repaired = _render_event_runtime(repaired, runtime)
        unresolved = _unresolved_event_fields(repaired)
        if unresolved or repaired == old_pending:
            return
        story["pending"] = repaired
        context.state.entities.put(command.actor_id, STORY_STATE, story)
        context.emit(
            "story.interaction.repaired",
            source="story",
            scope=EventScope.entity(command.actor_id),
            payload={
                "actor_id": command.actor_id,
                "event_id": event.id,
                "repaired_fields": sorted(set(runtime) & {
                    "target_realm", "target_power",
                }),
            },
        )

    return handler


def _treasure_runtime(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
) -> dict[str, Any]:
    cultivation = context.state.entities.require(actor_id, CULTIVATION)
    location = context.state.entities.require(actor_id, LOCATION)
    world_id = str(location["world_id"])
    location_id = str(location["location_id"])
    target_tier = max(
        1, definitions.realm_index(str(cultivation["realm_id"]))
    )
    rewards: dict[str, dict[str, Any]] = {}
    for category in ("artifact", "technique", "pill"):
        eligible_goods = []
        seen: set[tuple[str, str]] = set()
        for good in definitions.market_goods:
            key = (good.kind, good.content_id)
            if (
                good.world_id != world_id
                or good.tier > target_tier
                or key in seen
            ):
                continue
            eligible = False
            if category == "technique":
                eligible = good.kind == "technique"
            elif good.kind == "item":
                item = definitions.items[good.content_id]
                is_pill = "pill" in item.tags
                eligible = (
                    is_pill if category == "pill"
                    else not is_pill and item.combat_bonus > 0
                )
            if eligible:
                eligible_goods.append(good)
                seen.add(key)
        # V1 first builds the category/tier pool and only then partitions it
        # regionally.  Doing this in the opposite order can let pills consume
        # every local item slot and make the artifact choice disappear.
        candidates = regional_market_goods(
            definitions,
            eligible_goods,
            world_id,
            location_id,
            "treasure",
        )
        if not candidates:
            raise ValueError(f"{definitions.worlds[world_id].name}缺少可用的探宝奖励")
        selected = context.rng.choices(
            candidates,
            weights=[max(1, row.tier) for row in candidates],
            k=1,
        )[0]
        name = (
            definitions.techniques[selected.content_id].name
            if selected.kind == "technique"
            else definitions.items[selected.content_id].name
        )
        rewards[category] = {
            "kind": selected.kind,
            "content_id": selected.content_id,
            "name": name,
            "tier": selected.tier,
            "world_id": world_id,
        }
    return {"rewards": rewards}


def queue_story_event(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
    event_id: str, *, reason: str, runtime: dict[str, Any] | None = None,
) -> None:
    if event_id not in definitions.story_events:
        raise ValueError(f"剧情事件不存在：{event_id}")
    story = context.state.entities.require(actor_id, STORY_STATE)
    queue = list(story.get("queue", []))
    queued = {"event_id": event_id, "reason": reason, "queued_year": context.state.clock.year}
    if runtime is not None:
        queued["runtime"] = copy.deepcopy(runtime)
    elif event_id == "EVT_TREASURE_REWARD_SELECT_001":
        queued["runtime"] = _treasure_runtime(
            context, definitions, actor_id
        )
    else:
        generated = _combat_runtime(
            context, definitions, actor_id, definitions.story_events[event_id]
        )
        if generated is not None:
            queued["runtime"] = generated
    queue.append(queued)
    story["queue"] = queue
    context.state.entities.put(actor_id, STORY_STATE, story)
    _promote_story_queue(context, definitions, actor_id)


def _maybe_queue_artifact_synthesis(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
) -> bool:
    story = context.state.entities.require(actor_id, STORY_STATE)
    if story.get("pending") is not None or story.get("queue"):
        return False
    event_id = "EVT_FIVE_POLES_CRAFT_001"
    event = definitions.story_events.get(event_id)
    if event is None or not _condition(
        event.conditions, context.state, actor_id, definitions
    ):
        return False
    inventory = context.state.entities.require(actor_id, INVENTORY)
    if int(dict(inventory.get("items", {})).get(
        "yuanhe_five_poles_mountain", 0
    )) > 0:
        return False
    history = list(story.get("history", []))
    if history and history[-1].get("event_id") == event_id and int(
        history[-1].get("year", -1)
    ) == context.state.clock.year:
        return False
    queue_story_event(
        context, definitions, actor_id, event_id,
        reason="artifact_synthesis_ready",
    )
    return True


def _maybe_queue_mortal_root_completion(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
) -> bool:
    """Preserve the V1 annual, age-scaled Jinque awakening roll.

    This event must not enter the ambient weighted story pool: V1 gives a
    rootless mortal holding a Jinque scroll a 1% chance at age 35, increasing
    by one percentage point for every year thereafter.
    """
    story = context.state.entities.require(actor_id, STORY_STATE)
    if story.get("pending") is not None or story.get("queue"):
        return False
    event = definitions.story_events.get("EVT_MORTAL_ROOT_COMPLETE_001")
    if event is None or not _condition(
        event.conditions, context.state, actor_id, definitions
    ):
        return False
    life = context.state.entities.require(actor_id, LIFE)
    age = context.state.clock.year - int(life["birth_year"])
    chance = min(1.0, max(0, age - 34) * 0.01)
    if chance <= 0 or context.rng.random() >= chance:
        return False
    queue_story_event(
        context, definitions, actor_id, event.id,
        reason="mortal_root_completion",
        runtime={"trigger_chance": round(chance, 4)},
    )
    story = context.state.entities.require(actor_id, STORY_STATE)
    pending = dict(story.get("pending") or {})
    pending["body"] = (
        str(pending.get("body", ""))
        + f"（本年逆天改命机率 {chance:.0%}）"
    )
    story["pending"] = pending
    context.state.entities.put(actor_id, STORY_STATE, story)
    return True


def _maybe_queue_probability_event(
    context: SimulationContext,
    definitions: GameDefinitions,
    registry: StoryEffectRegistry,
    actor_id: str,
) -> bool:
    story = context.state.entities.require(actor_id, STORY_STATE)
    if story.get("pending") is not None or story.get("queue"):
        return False
    compatible = registry.compatible_event_ids()
    history_ids = {
        str(row.get("event_id")) for row in story.get("history", [])
    }
    attempts = dict(story.get("trigger_attempts", {}))
    milestones = dict(story.get("milestones", {}))
    for event in sorted(definitions.story_events.values(), key=lambda row: row.id):
        if (
            "probability_gate" not in set(event.tags)
            or event.id not in compatible
            or event.id in history_ids
            or not _condition(
                event.conditions, context.state, actor_id, definitions
            )
        ):
            continue
        trigger = dict(event.trigger)
        if not trigger:
            continue
        milestone = str(trigger.get("milestone", f"{event.id}:eligible"))
        milestones.setdefault(milestone, context.state.clock.year)
        count = max(0, int(attempts.get(milestone, 0)))
        chance = min(
            1.0,
            float(trigger.get("base_chance", 0.0))
            + count * float(trigger.get(
                "unit_increment", trigger.get("annual_increment", 0.0)
            )),
        )
        if context.rng.random() >= chance:
            attempts[milestone] = count + 1
            continue
        story["trigger_attempts"] = attempts
        story["milestones"] = milestones
        context.state.entities.put(actor_id, STORY_STATE, story)
        queue_story_event(
            context, definitions, actor_id, event.id,
            reason=f"probability_gate:{milestone}",
            runtime={"trigger_chance": round(chance, 4)},
        )
        story = context.state.entities.require(actor_id, STORY_STATE)
        pending = dict(story.get("pending") or {})
        pending["body"] = (
            str(pending.get("body", ""))
            + f"（本行动单位触发概率 {chance:.0%}）"
        )
        story["pending"] = pending
        context.state.entities.put(actor_id, STORY_STATE, story)
        return True
    story["trigger_attempts"] = attempts
    story["milestones"] = milestones
    context.state.entities.put(actor_id, STORY_STATE, story)
    return False


def _eligible_event(
    state: WorldState, actor_id: str, definitions: GameDefinitions,
    compatible: frozenset[str], event: StoryEventDefinition,
) -> bool:
    if (
        event.id not in compatible
        or event.weight <= 0
        or event.id == "EVT_MORTAL_ROOT_COMPLETE_001"
    ):
        return False
    tags = set(event.tags)
    if "manual_only" in tags or "probability_gate" in tags:
        return False
    location = state.entities.require(actor_id, LOCATION)
    cultivation = state.entities.require(actor_id, CULTIVATION)
    world_id = str(location["world_id"])
    realm_index = definitions.realm_index(str(cultivation["realm_id"]))
    world_tags = {tag for tag in tags if tag.startswith("world:")}
    if world_tags and f"world:{world_id}" not in world_tags:
        return False
    if definitions.worlds[world_id].tier >= 3 and f"world:{world_id}" not in world_tags:
        return False
    if realm_index == 0 and "mortal" not in tags:
        return False
    if realm_index > 0 and "mortal" in tags:
        return False
    if "faction" in tags and "faction_join" not in tags:
        return False
    if not _condition(event.conditions, state, actor_id, definitions):
        return False
    story = state.entities.require(actor_id, STORY_STATE)
    if event.repeat == "once" and any(
        str(row.get("event_id")) == event.id for row in story.get("history", [])
    ):
        return False
    return any(_condition(choice.conditions, state, actor_id, definitions) for choice in event.choices)


def _on_action_completed(
    definitions: GameDefinitions, registry: StoryEffectRegistry,
):
    def handler(context: SimulationContext, envelope: EventEnvelope) -> None:
        actor_id = str(envelope.payload["actor_id"])
        story = context.state.entities.require(actor_id, STORY_STATE)
        if story.get("pending") is not None or story.get("queue"):
            return
        if _maybe_queue_artifact_synthesis(
            context, definitions, actor_id
        ) or _maybe_queue_mortal_root_completion(
            context, definitions, actor_id
        ) or _maybe_queue_probability_event(
            context, definitions, registry, actor_id
        ):
            return
        action = str(envelope.payload.get("action", ""))
        candidates = [
            event for event in sorted(definitions.story_events.values(), key=lambda row: row.id)
            if _eligible_event(
                context.state, actor_id, definitions,
                registry.compatible_event_ids(), event,
            )
        ]
        weights = [
            max(0.0, event.weight * float(event.intent_weights.get(action, 1.0)))
            for event in candidates
        ]
        total = sum(weights)
        if total <= 0:
            return
        roll = context.rng.random() * total
        selected = candidates[-1]
        for event, weight in zip(candidates, weights, strict=True):
            roll -= weight
            if roll <= 0:
                selected = event
                break
        queue_story_event(
            context, definitions, actor_id, selected.id,
            reason=f"action:{action}",
        )

    return handler


def _resolve_choice_handler(
    definitions: GameDefinitions, registry: StoryEffectRegistry,
):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ResolveStoryChoice):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能处理当前角色的事件")
        if not bool(context.state.entities.require(command.actor_id, LIFE).get("alive")):
            raise ValueError("此生已经结束")
        story = context.state.entities.require(command.actor_id, STORY_STATE)
        pending = story.get("pending")
        if not isinstance(pending, dict):
            raise ValueError("当前没有待处理事件")
        event = definitions.story_events[str(pending["id"])]
        choice = next((row for row in event.choices if row.id == command.choice_id), None)
        if choice is None:
            raise ValueError("事件选项不存在")
        if not _condition(choice.conditions, context.state, command.actor_id, definitions):
            raise ValueError(choice.disabled_reason)
        unsupported = [effect.kind for effect in choice.effects if effect.kind not in registry.supported_kinds]
        if unsupported:
            raise ValueError(f"该选项包含尚未迁移的效果：{', '.join(sorted(set(unsupported)))}")
        story["pending"] = None
        context.state.entities.put(command.actor_id, STORY_STATE, story)
        result = "resolved"
        summaries: list[str] = []
        for effect in choice.effects:
            required = tuple(map(str, effect.payload.get("if_result", [])))
            if required and result not in required:
                continue
            outcome = registry.execute(context, command.actor_id, effect, pending)
            if outcome.summary:
                summaries.append(outcome.summary)
            if outcome.result:
                result = outcome.result
            if not bool(context.state.entities.require(command.actor_id, LIFE).get("alive")):
                break
        runtime = dict(pending.get("runtime", {}))
        encounter_id = str(runtime.get("target_id", ""))
        if runtime.get("generated_encounter") and context.state.entities.exists(
            encounter_id
        ):
            marker = context.state.entities.get(
                encounter_id, "story.encounter"
            ) or {}
            marker["resolved"] = True
            context.state.entities.put(encounter_id, "story.encounter", marker)
            life = context.state.entities.get(encounter_id, LIFE)
            if life is not None and bool(life.get("alive")):
                life["alive"] = False
                life["death_reason"] = "遭遇已经结束"
                context.state.entities.put(encounter_id, LIFE, life)
        story = context.state.entities.require(command.actor_id, STORY_STATE)
        history = list(story.get("history", []))
        history.append({
            "event_id": event.id,
            "version": event.version,
            "year": context.state.clock.year,
            "title": event.title,
            "choice_id": choice.id,
            "result": result,
            "summary": (
                "。".join(summary.rstrip("。") for summary in summaries) + "。"
                if summaries else choice.result_text
            ),
            "tags": list(event.tags),
        })
        story["history"] = history
        context.state.entities.put(command.actor_id, STORY_STATE, story)
        context.emit(
            "story.interaction.resolved",
            source="story",
            scope=EventScope.entity(command.actor_id),
            payload={
                "actor_id": command.actor_id, "event_id": event.id,
                "choice_id": choice.id, "result": result,
            },
        )
        _promote_story_queue(context, definitions, command.actor_id)
        story = context.state.entities.require(command.actor_id, STORY_STATE)
        if story.get("pending") is None:
            _maybe_queue_artifact_synthesis(
                context, definitions, command.actor_id
            )
            story = context.state.entities.require(
                command.actor_id, STORY_STATE
            )
        if story.get("pending") is None and bool(
            context.state.entities.require(command.actor_id, LIFE).get("alive")
        ):
            resume_action(context, command.actor_id)

    return handler


def _queue_event_handler(
    definitions: GameDefinitions, registry: StoryEffectRegistry,
):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, QueueStoryEvent):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能为当前角色排入事件")
        if command.event_id not in registry.compatible_event_ids():
            raise ValueError("该事件链包含尚未迁移的剧情效果")
        queue_story_event(
            context, definitions, command.actor_id, command.event_id,
            reason=command.reason,
        )

    return handler


def _begin_spirit_crossing_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, BeginSpiritCrossing):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能控制当前角色偷渡")
        if not bool(context.state.entities.require(command.actor_id, LIFE).get("alive")):
            raise ValueError("此生已经结束")
        transition = context.state.entities.require(command.actor_id, WORLD_TRANSITION)
        if transition.get("sealed_cultivation") is not None:
            raise ValueError("当前身处下界且真实道果处于封印中，只能重返原上界")
        cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        location = context.state.entities.require(command.actor_id, LOCATION)
        path = str(cultivation["path"])
        origin = str(location["world_id"])
        if path == "demonic":
            destination = {"human": "demon", "demon": "true_demon"}.get(origin)
            if destination is None:
                raise ValueError("当前魔界路线没有可用的飞升目标")
            if origin == "demon":
                from .cultivation import _qi_level

                required = int(definitions.systems["demonic_cultivation"][
                    "true_demon_ascension_demon_qi_level"
                ])
                current = _qi_level(
                    definitions,
                    float(dict(cultivation.get("qi_experience", {})).get(
                        "demon", 0
                    )),
                )
                if current < required:
                    context.emit(
                        "character.lethal_hazard",
                        source="world",
                        scope=EventScope.entity(command.actor_id),
                        payload={
                            "entity_id": command.actor_id,
                            "reason": (
                                f"魔气等级仅有 {current} 级，未达飞升真魔界"
                                f"所需的 {required} 级；肉身与元神在界壁魔潮中一同崩解"
                            ),
                        },
                    )
                    return
            _ascend_handler(definitions)(
                context, AscendWorld(command.actor_id, destination, command.invited_ids)
            )
            return
        if origin != "human":
            raise ValueError("你已经脱离人界")
        realm_index = definitions.realm_index(str(cultivation["realm_id"]))
        destinations = {
            "dao": "spirit", "buddhist": "spirit", "confucian": "spirit",
            "monster": "monster_realm", "ghost": "hell",
        }
        destination = destinations.get(path)
        destination_name = (
            definitions.worlds[destination].name
            if destination in definitions.worlds else destination or "目标界面"
        )
        if (
            destination is None or destination not in definitions.worlds
            or not definitions.worlds[destination].enabled
            or realm_index != 5 or int(cultivation["layer"]) > 3
        ):
            raise ValueError(f"只有达到人界化神初期，方能尝试偷渡{destination_name}")
        story = context.state.entities.require(command.actor_id, STORY_STATE)
        crossing = dict(story.get("spirit_crossing", {}))
        if bool(crossing.get("attempted")):
            raise ValueError("偷渡灵界的机会只有一次")
        crossing.update({
            "attempted": True,
            "active": True,
            "destination": destination,
            "invited_ids": list(dict.fromkeys(map(str, command.invited_ids))),
            "started_year": context.state.clock.year,
        })
        if len(crossing["invited_ids"]) != len(command.invited_ids):
            raise ValueError("同行邀请不能重复")
        story["spirit_crossing"] = crossing
        context.state.entities.put(command.actor_id, STORY_STATE, story)
        queue_story_event(
            context, definitions, command.actor_id, "EVT_SPIRIT_CROSSING_001",
            reason="spirit_crossing",
            runtime={"destination_name": destination_name},
        )
        if destination != "spirit":
            story = context.state.entities.require(command.actor_id, STORY_STATE)
            pending = dict(story.get("pending") or {})
            pending["title"] = f"偷渡{destination_name}"
            pending["body"] = str(pending.get("body", "")).replace(
                "灵界", destination_name
            )
            story["pending"] = pending
            context.state.entities.put(command.actor_id, STORY_STATE, story)

    return handler


def _interaction_guard(state: WorldState, command: object) -> None:
    actor_id = state.controlled_entity_id
    if actor_id is None or bool(getattr(type(command), "allow_during_interaction", False)):
        return
    story = state.entities.get(actor_id, STORY_STATE)
    if story is not None and story.get("pending") is not None:
        raise ValueError("请先处理当前事件")


def story_invariants(definitions: GameDefinitions):
    def validate(state: WorldState) -> list[str]:
        errors: list[str] = []
        for entity_id in state.entities.with_component(IDENTITY):
            story = state.entities.get(entity_id, STORY_STATE)
            if story is None:
                errors.append(f"角色 {entity_id} 缺少剧情状态")
                continue
            pending = story.get("pending")
            if pending is not None and str(pending.get("id", "")) not in definitions.story_events:
                errors.append(f"角色 {entity_id} 等待未知剧情事件")
            for queued in story.get("queue", []):
                if str(queued.get("event_id", "")) not in definitions.story_events:
                    errors.append(f"角色 {entity_id} 的剧情队列引用未知事件")
            if len(story.get("flags", [])) != len(set(map(str, story.get("flags", [])))):
                errors.append(f"角色 {entity_id} 的剧情标记重复")
            if any(
                not isinstance(value, int) or isinstance(value, bool) or value < 0
                for value in dict(story.get("trigger_attempts", {})).values()
            ):
                errors.append(f"角色 {entity_id} 的概率剧情尝试次数非法")
        return errors

    return validate


def story_view(state: WorldState, entity_id: str | None = None) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    story = state.entities.require(actor_id, STORY_STATE)
    return {
        "pending_event": copy.deepcopy(story.get("pending")),
        "queued_event_count": len(story.get("queue", [])),
        "history": copy.deepcopy(story.get("history", [])),
        "flags": list(story.get("flags", [])),
        "milestones": copy.deepcopy(story.get("milestones", {})),
        "attributes": copy.deepcopy(story.get("attributes", {})),
        "spirit_crossing": copy.deepcopy(story.get(
            "spirit_crossing", _default_story_state()["spirit_crossing"]
        )),
    }


def register_story_domain(
    bus: CommandBus, definitions: GameDefinitions,
) -> StoryEffectRegistry:
    registry = StoryEffectRegistry(definitions)
    bus.register(ResolveStoryChoice, _resolve_choice_handler(definitions, registry))
    bus.register(QueueStoryEvent, _queue_event_handler(definitions, registry))
    bus.register(
        RepairPendingStoryEvent, _repair_pending_event_handler(definitions)
    )
    bus.register(BeginSpiritCrossing, _begin_spirit_crossing_handler(definitions))
    bus.add_guard(_interaction_guard)
    bus.event_bus.register("character.created", _on_character_created)
    bus.event_bus.register("character.died", _on_character_died)
    bus.event_bus.register("core.action.completed", _on_action_completed(definitions, registry))
    return registry

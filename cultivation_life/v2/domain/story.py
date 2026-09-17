from __future__ import annotations

import copy
import operator
from dataclasses import dataclass
from typing import Any, Callable, ClassVar

from .actions import resume_action
from .character import IDENTITY, LIFE
from .combat import CONDITION
from .cultivation import CULTIVATION, PRACTICE
from .definitions import GameDefinitions, StoryEffectDefinition, StoryEventDefinition
from .economy import INVENTORY
from .factions import MEMBERSHIP
from .world import LOCATION
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
        "attributes": {"karma": 0.0, "fame": 0.0, "sha_qi": 0.0},
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


class StoryEffectRegistry:
    """Registry of effect kinds that are safe to execute inside V2.

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
        attributes[key] = max(0.0, float(attributes.get(key, 0.0)) + value)
        state["attributes"] = attributes
        context.state.entities.put(actor_id, STORY_STATE, state)
        return EffectOutcome(None, f"{key} {value:+g}")

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
            payload={"entity_id": actor_id, "technique_id": technique_id},
        )
        return EffectOutcome(None, f"学会{self.definitions.techniques[technique_id].name}并设为主修")

    def _change_condition(
        self, context: SimulationContext, actor_id: str,
        effect: StoryEffectDefinition, pending: dict[str, Any],
    ) -> EffectOutcome:
        value = self._value(context, effect)
        condition = context.state.entities.require(actor_id, CONDITION)
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
            if float(condition["hp_ratio"]) - value <= 0:
                return EffectOutcome("dead", f"受到最大生命 {value:.0%} 的伤害并陨落")
            return EffectOutcome("injured", f"受到最大生命 {value:.0%} 的伤害")
        key = "mp_ratio" if effect.kind == "restore_mp" else "hp_ratio"
        return EffectOutcome(None, f"{key} {value:+.0%}")

    def _extend_lifespan(
        self, context: SimulationContext, actor_id: str,
        effect: StoryEffectDefinition, pending: dict[str, Any],
    ) -> EffectOutcome:
        value = int(self._value(context, effect))
        context.emit(
            "story.effect.lifespan.extended",
            source="story",
            scope=EventScope.entity(actor_id),
            payload={"entity_id": actor_id, "amount": value},
        )
        return EffectOutcome(None, f"寿元 {value:+d}")

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


def _path_value(state: WorldState, actor_id: str, path: str) -> Any:
    cultivation = state.entities.require(actor_id, CULTIVATION)
    location = state.entities.require(actor_id, LOCATION)
    life = state.entities.require(actor_id, LIFE)
    practice = state.entities.require(actor_id, PRACTICE)
    story = state.entities.require(actor_id, STORY_STATE)
    membership = next(iter(state.relations.find(source_id=actor_id, kind=MEMBERSHIP)), None)
    values = {
        "player.world": location["world_id"],
        "player.path": cultivation["path"],
        "player.spirit_root": cultivation["spirit_root"],
        "player.layer": int(cultivation["layer"]),
        "player.age": state.clock.year - int(life["birth_year"]),
        "player.karma": float(story["attributes"].get("karma", 0)),
        "player.effective_karma": float(story["attributes"].get("karma", 0)),
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
        roots = [str(cultivation["spirit_root"]), *map(str, cultivation.get("additional_roots", []))]
        affinities = {
            affinity
            for root_id in roots if root_id in definitions.roots
            for affinity in definitions.roots[root_id].elements
        }
        return str(condition["has_affinity"]) in affinities
    if "world_npc" in condition:
        return False
    path = str(condition.get("path", ""))
    op = _OPS.get(str(condition.get("op", "eq")))
    if not path or op is None:
        return False
    if path == "player.realm_index":
        cultivation = state.entities.require(actor_id, CULTIVATION)
        actual = definitions.realm_index(str(cultivation["realm_id"]))
    else:
        actual = _path_value(state, actor_id, path)
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
    if isinstance(runtime, dict):
        pending["runtime"] = copy.deepcopy(runtime)
        body = str(pending["body"])
        for key, value in runtime.items():
            if isinstance(value, (str, int, float)):
                body = body.replace("{" + str(key) + "}", str(value))
        pending["body"] = body
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
    queue.append(queued)
    story["queue"] = queue
    context.state.entities.put(actor_id, STORY_STATE, story)
    _promote_story_queue(context, definitions, actor_id)


def _eligible_event(
    state: WorldState, actor_id: str, definitions: GameDefinitions,
    compatible: frozenset[str], event: StoryEventDefinition,
) -> bool:
    if event.id not in compatible or event.weight <= 0:
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
        story = context.state.entities.require(command.actor_id, STORY_STATE)
        history = list(story.get("history", []))
        history.append({
            "event_id": event.id,
            "version": event.version,
            "year": context.state.clock.year,
            "title": event.title,
            "choice_id": choice.id,
            "result": result,
            "summary": " ".join(summaries) or choice.result_text,
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
    }


def register_story_domain(
    bus: CommandBus, definitions: GameDefinitions,
) -> StoryEffectRegistry:
    registry = StoryEffectRegistry(definitions)
    bus.register(ResolveStoryChoice, _resolve_choice_handler(definitions, registry))
    bus.register(QueueStoryEvent, _queue_event_handler(definitions, registry))
    bus.add_guard(_interaction_guard)
    bus.event_bus.register("character.created", _on_character_created)
    bus.event_bus.register("core.action.completed", _on_action_completed(definitions, registry))
    return registry

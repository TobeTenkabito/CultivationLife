from __future__ import annotations

from typing import Any

from .actions import ACTION_RUNTIME
from .character import IDENTITY, LIFE, WORLD_NPC_PROFILE, create_character
from .combat import CONDITION, combat_snapshot
from .cultivation import CULTIVATION
from .definitions import GameDefinitions
from .factions import (
    DIPLOMACY_STATE,
    FACTION_GOVERNANCE,
    FACTION_NPC,
    FACTION_PROFILE,
    MEMBERSHIP,
    _add_membership,
    _active_membership,
    _create_faction_entity,
    _dissolve_faction,
    _diplomacy_key,
    _governance_threshold,
    _recruit_faction_npc,
)
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope


def _choose_two(context: SimulationContext, values: list[str]) -> tuple[str, str]:
    """Choose two distinct values without relying on Random.sample.

    Several deterministic domain tests provide a Random subclass whose
    ``random()`` always returns the same value.  CPython's rejection-based
    ``sample`` never terminates for that valid test double.
    """
    if len(values) < 2:
        raise ValueError("至少需要两个候选项")
    first = context.rng.choice(values)
    remaining = [value for value in values if value != first]
    return first, context.rng.choice(remaining)


def _unit(context: SimulationContext, actor_id: str) -> int:
    runtime = context.state.entities.get(actor_id, ACTION_RUNTIME) or {}
    return max(0, int(runtime.get("next_sequence", 1)) - 1)


def _relation(
    relations: dict[str, Any], kind: str, first_id: str, second_id: str, year: int
) -> tuple[str, dict[str, Any]]:
    key = _diplomacy_key(kind, first_id, second_id)
    first, second = sorted((first_id, second_id))
    return key, dict(relations.get(key, {
        "kind": kind,
        "first_id": first,
        "second_id": second,
        "status": "neutral",
        "affinity": 0.0,
        "since_year": year,
    }))


def _on_game_created(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        del event
        actor_id = context.state.controlled_entity_id
        if actor_id is None:
            return
        diplomacy = context.state.entities.require(actor_id, DIPLOMACY_STATE)
        relations = dict(diplomacy.get("relations", {}))
        for raw in definitions.systems.get("race_diplomacy", {}).get(
            "initial_relations", []
        ):
            row = dict(raw)
            members = list(map(str, row.get("members", [])))
            if len(members) != 2:
                continue
            key, relation = _relation(
                relations, "race", members[0], members[1], context.state.clock.year
            )
            relation.update({
                "status": str(row.get("status", "neutral")),
                "affinity": float(row.get("affinity", 0.0)),
                "since_year": context.state.clock.year,
                "world_id": str(row.get("world", "spirit")),
            })
            relations[key] = relation
        diplomacy["relations"] = relations
        context.state.entities.put(actor_id, DIPLOMACY_STATE, diplomacy)

    return handler


def _expire_truces(
    context: SimulationContext,
    actor_id: str,
    relations: dict[str, Any],
) -> None:
    current = _unit(context, actor_id)
    for key, raw in list(relations.items()):
        relation = dict(raw)
        until = max(
            int(relation.get("truce_until_unit", 0)),
            int(relation.get("war_truce_until_unit", 0)),
        )
        if relation.get("status") != "truce" or current < until:
            continue
        relation.update(
            status="neutral",
            affinity=max(-10.0, float(relation.get("affinity", 0.0))),
            since_year=context.state.clock.year,
        )
        relation.pop("truce_until_unit", None)
        relation.pop("war_truce_until_unit", None)
        relations[key] = relation
        context.emit(
            "governance.diplomacy.changed", source="world_simulation",
            scope=EventScope("world", str(relation.get("world_id", "global"))),
            payload={"key": key, "relation": relation, "reason": "truce_expired"},
        )


def _grant_alliance_benefits(
    context: SimulationContext,
    definitions: GameDefinitions,
    actor_id: str,
    relations: dict[str, Any],
) -> None:
    membership = _active_membership(context.state, actor_id)
    identity = context.state.entities.require(actor_id, IDENTITY)
    own_race = str(identity.get("race", "human"))
    current_world = str(
        context.state.entities.require(actor_id, LOCATION)["world_id"]
    )
    faction_allied = False
    race_allied = False
    for relation in relations.values():
        if relation.get("status") not in {"alliance", "vassal"}:
            continue
        if str(relation.get("world_id") or current_world) != current_world:
            continue
        sides = {str(relation.get("first_id")), str(relation.get("second_id"))}
        if relation.get("kind") == "race" and own_race in sides:
            race_allied = True
        if (
            relation.get("kind") == "faction" and membership is not None
            and membership.target_id in sides
        ):
            faction_allied = True
    if race_allied:
        cultivation = context.state.entities.require(actor_id, CULTIVATION)
        reward = float(definitions.systems.get("race_diplomacy", {}).get(
            "alliance_opportunity_reward", 2
        ))
        cultivation["opportunity"] = float(cultivation.get("opportunity", 0.0)) + reward
        context.state.entities.put(actor_id, CULTIVATION, cultivation)
        context.emit(
            "governance.alliance.benefit", source="world_simulation",
            scope=EventScope.entity(actor_id),
            payload={"kind": "race", "opportunity": reward},
        )
    if faction_allied and membership is not None:
        metadata = dict(membership.metadata)
        metadata["contribution"] = int(metadata.get("contribution", 0)) + 1
        context.state.relations.replace_metadata(membership.relation_id, metadata)
        context.emit(
            "governance.alliance.benefit", source="world_simulation",
            scope=EventScope("faction", membership.target_id),
            payload={"kind": "faction", "contribution": 1},
        )


def _change_random_relation(
    context: SimulationContext,
    definitions: GameDefinitions,
    actor_id: str,
    relations: dict[str, Any],
    *,
    kind: str,
) -> None:
    world_id = str(context.state.entities.require(actor_id, LOCATION)["world_id"])
    if kind == "faction":
        powers = [
            faction_id for faction_id in context.state.entities.with_component(FACTION_PROFILE)
            if bool(context.state.entities.require(faction_id, FACTION_PROFILE).get("active"))
            and context.state.entities.require(faction_id, FACTION_PROFILE).get("world_id") == world_id
        ]
    else:
        powers = [
            race_id for race_id, definition in definitions.races.items()
            if world_id in set(map(str, definition.get("worlds", [])))
        ]
    if len(powers) < 2:
        return
    first_id, second_id = _choose_two(context, sorted(powers))
    key, relation = _relation(
        relations, kind, first_id, second_id, context.state.clock.year
    )
    if relation.get("status") == "war":
        return
    if _unit(context, actor_id) < max(
        int(relation.get("truce_until_unit", 0)),
        int(relation.get("war_truce_until_unit", 0)),
    ):
        return
    low, high = definitions.systems.get("race_diplomacy", {}).get(
        "affinity_drift", [-12, 12]
    )
    affinity = max(-100.0, min(
        100.0,
        float(relation.get("affinity", 0.0)) + context.rng.uniform(float(low), float(high)),
    ))
    previous = str(relation.get("status", "neutral"))
    status = previous
    if previous in {"alliance", "vassal"} and affinity < 35:
        status = "neutral"
    elif previous == "neutral" and affinity >= 68:
        status = "alliance"
    elif previous == "neutral" and affinity <= -68:
        status = "war"
    relation.update(
        affinity=round(affinity, 3), status=status,
        since_year=context.state.clock.year, world_id=world_id,
    )
    relations[key] = relation
    if status != previous:
        context.emit(
            "governance.diplomacy.changed", source="world_simulation",
            scope=EventScope("world", world_id),
            payload={"key": key, "relation": relation, "reason": "npc_diplomacy"},
        )
    if status == "war":
        from .war import _create_war

        _create_war(
            context, definitions, actor_id=actor_id, kind=kind,
            attacker_id=first_id, defender_id=second_id, world_id=world_id,
        )


def _ensure_declared_wars(
    context: SimulationContext,
    definitions: GameDefinitions,
    actor_id: str,
    relations: dict[str, Any],
) -> None:
    from .war import _create_war

    current_world = str(context.state.entities.require(actor_id, LOCATION)["world_id"])
    for relation in relations.values():
        if relation.get("status") != "war":
            continue
        world_id = str(relation.get("world_id") or current_world)
        if world_id != current_world:
            continue
        _create_war(
            context, definitions, actor_id=actor_id,
            kind=str(relation.get("kind", "race")),
            attacker_id=str(relation.get("first_id")),
            defender_id=str(relation.get("second_id")),
            world_id=world_id,
        )


def _simulate_npc_duel(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str
) -> None:
    if context.rng.random() >= 0.04:
        return
    world_id = str(context.state.entities.require(actor_id, LOCATION)["world_id"])
    candidates = [
        entity_id for entity_id in context.state.entities.with_component(IDENTITY)
        if entity_id != actor_id
        and bool(context.state.entities.require(entity_id, LIFE).get("alive"))
        and context.state.entities.require(entity_id, LOCATION).get("world_id") == world_id
    ]
    if len(candidates) < 2:
        return
    first_id, second_id = _choose_two(context, sorted(candidates))
    first = float(combat_snapshot(context.state, definitions, first_id)["power"])
    second = float(combat_snapshot(context.state, definitions, second_id)["power"])
    chance = max(0.08, min(0.92, first / max(1.0, first + second)))
    winner_id, loser_id = (
        (first_id, second_id) if context.rng.random() < chance
        else (second_id, first_id)
    )
    lethal = context.rng.random() < float(
        definitions.systems.get("npc_mortality", {}).get("duel_lethal_chance", 0.16)
    )
    context.emit(
        "npc.duel.resolved", source="world_simulation",
        scope=EventScope("world", world_id),
        payload={
            "winner_id": winner_id, "loser_id": loser_id, "lethal": lethal,
            "world_id": world_id,
        },
    )
    if lethal:
        context.emit(
            "character.lethal_hazard", source="world_simulation",
            scope=EventScope.entity(loser_id),
            payload={
                "entity_id": loser_id,
                "reason": f"与{context.state.entities.require(winner_id, IDENTITY)['name']}斗法时陨落",
            },
            immediate=True,
        )


def _recover_npc_conditions(
    context: SimulationContext, definitions: GameDefinitions, years: int
) -> None:
    """Restore the V1 annual natural recovery of wounded NPCs.

    V1 stored wounds as a small integer.  V2 stores the actual remaining HP,
    so each successful recovery year closes one third of the outstanding gap.
    Player recovery remains owned by explicit player actions.
    """
    recovery_chance = float(
        definitions.systems.get("npc_mortality", {}).get(
            "wound_recovery_chance_per_year", 0.35
        )
    )
    for entity_id in context.state.entities.with_component(CONDITION):
        if entity_id == context.state.controlled_entity_id:
            continue
        life = context.state.entities.get(entity_id, LIFE) or {}
        if not bool(life.get("alive")):
            continue
        condition = context.state.entities.require(entity_id, CONDITION)
        hp_ratio = float(condition.get("hp_ratio", 1.0))
        if hp_ratio >= 1.0:
            continue
        recovered = False
        for _ in range(max(0, years)):
            if hp_ratio >= 0.999:
                break
            if context.rng.random() < recovery_chance:
                hp_ratio = min(1.0, hp_ratio + max(0.12, (1.0 - hp_ratio) / 3))
                recovered = True
        if recovered:
            condition["hp_ratio"] = round(hp_ratio, 6)
            context.state.entities.put(entity_id, CONDITION, condition)


def _notorious_npc_killings(
    context: SimulationContext, definitions: GameDefinitions,
    actor_id: str, years: int,
) -> None:
    world_id = str(context.state.entities.require(actor_id, LOCATION)["world_id"])
    protected = {
        edge.target_id if edge.source_id == actor_id else edge.source_id
        for edge in context.state.relations.involving(actor_id)
    }
    candidates = [
        entity_id for entity_id in context.state.entities.with_component(IDENTITY)
        if entity_id != actor_id
        and bool((context.state.entities.get(entity_id, LIFE) or {}).get("alive"))
        and (context.state.entities.get(entity_id, LOCATION) or {}).get("world_id") == world_id
    ]
    villains = []
    for entity_id in candidates:
        cultivation = context.state.entities.require(entity_id, CULTIVATION)
        profile = context.state.entities.get(entity_id, WORLD_NPC_PROFILE) or {}
        if bool(profile.get("notorious")) or cultivation.get("path") == "demonic":
            villains.append(entity_id)
    for villain_id in sorted(villains):
        villain_cultivation = context.state.entities.require(villain_id, CULTIVATION)
        villain_profile = context.state.entities.get(villain_id, WORLD_NPC_PROFILE) or {}
        mortality = definitions.systems.get("npc_mortality", {})
        annual_chance = float(
            mortality.get(
                "demonic_killing_chance_per_year"
                if villain_cultivation.get("path") == "demonic"
                else "notorious_killing_chance_per_year",
                0.014 if villain_cultivation.get("path") == "demonic" else 0.004,
            )
        )
        villain_membership = _active_membership(context.state, villain_id)
        for _ in range(max(0, years)):
            if context.rng.random() >= annual_chance:
                continue
            villain_rank = definitions.realm_index(str(villain_cultivation["realm_id"]))
            victims = []
            for victim_id in candidates:
                if victim_id == villain_id or victim_id in protected:
                    continue
                if not bool(context.state.entities.require(victim_id, LIFE).get("alive")):
                    continue
                victim_profile = context.state.entities.get(
                    victim_id, WORLD_NPC_PROFILE
                ) or {}
                if bool(victim_profile.get("notorious")):
                    continue
                victim_cultivation = context.state.entities.require(
                    victim_id, CULTIVATION
                )
                if definitions.realm_index(str(victim_cultivation["realm_id"])) >= villain_rank:
                    continue
                victim_membership = _active_membership(context.state, victim_id)
                if (
                    villain_cultivation.get("path") == "demonic"
                    and villain_membership is not None
                    and victim_membership is not None
                    and villain_membership.target_id == victim_membership.target_id
                ):
                    continue
                victims.append(victim_id)
            if not victims:
                break
            victim_id = context.rng.choice(victims)
            context.emit(
                "npc.notorious.killing", source="world_simulation",
                scope=EventScope("world", world_id),
                payload={
                    "villain_id": villain_id, "victim_id": victim_id,
                    "world_id": world_id,
                },
            )
            context.emit(
                "character.lethal_hazard", source="world_simulation",
                scope=EventScope.entity(victim_id),
                payload={
                    "entity_id": victim_id,
                    "reason": (
                        f"遭{context.state.entities.require(villain_id, IDENTITY)['name']}"
                        "截杀"
                    ),
                },
                immediate=True,
            )


def _maybe_found_npc_power(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
) -> None:
    active_npc_powers = [
        faction_id for faction_id in context.state.entities.with_component(FACTION_PROFILE)
        if bool(context.state.entities.require(faction_id, FACTION_PROFILE).get("active"))
        and bool(context.state.entities.require(faction_id, FACTION_PROFILE).get("founded_by_npc"))
    ]
    found_chance = float(
        definitions.systems.get("player_faction", {}).get(
            "npc_power_found_chance_per_unit", 0.012
        )
    )
    if len(active_npc_powers) >= 8 or context.rng.random() >= found_chance:
        return
    world_id = str(context.state.entities.require(actor_id, LOCATION)["world_id"])
    cap = int(definitions.worlds[world_id].npc_realm_cap)
    realm_index = (
        (5 if context.rng.random() < 0.02 else 4)
        if cap <= 5 else (8 if context.rng.random() < 0.10 else 7)
    )
    realm_index = max(1, min(cap, realm_index, len(definitions.realms) - 1))
    kind = context.rng.choice(("sect", "family"))
    surname = context.rng.choice("顾叶陆楚白谢云林")
    founder_name = surname + context.rng.choice(
        ("玄岳", "长风", "照夜", "问天", "清河")
    )
    serial = len(active_npc_powers) + 1
    name = (
        f"{surname}氏仙族"
        if kind == "family" else
        f"{context.rng.choice(('玄岳门', '长风谷', '照夜宫', '问天盟'))}{serial}"
    )
    faction_id = _create_faction_entity(
        context, name=name, world_id=world_id, external_id=None,
        creator_id=None, path="npc_created", allegiance_race="human",
        description=(
            f"由{founder_name}自行建立的"
            f"{'修仙家族' if kind == 'family' else '宗门'}。"
        ), color="#6f7b88",
    )
    profile = context.state.entities.require(faction_id, FACTION_PROFILE)
    profile.update(
        founded_by_npc=True, kind=kind, roster_seeded=True,
        last_recruitment_year=context.state.clock.year,
    )
    context.state.entities.put(faction_id, FACTION_PROFILE, profile)
    realm = definitions.realms[realm_index]
    age = context.rng.randint(500, 1200) if cap <= 5 else context.rng.randint(8000, 30000)
    roots = [
        root_id for root_id, root in definitions.roots.items()
        if root_id != "none" and root.creation
    ]
    path = context.rng.choice(tuple(definitions.paths))
    lifespan = None
    if realm.lifespan is not None:
        lifespan = max(age + 1, realm.lifespan[1])
        if path == "monster":
            lifespan *= 3
    founder_id = create_character(
        context, name=founder_name, age=age,
        gender=context.rng.choice(("male", "female")), race="human",
        spirit_root=context.rng.choice(roots), path=path,
        realm_id=realm.id, layer=context.rng.randint(1, realm.layers),
        world_id=world_id, lifespan=lifespan,
    )
    context.state.entities.put(founder_id, FACTION_NPC, {
        "external_id": "", "title": (
            "始祖" if kind == "family" else "开山祖师"
        ), "cultivation_progress": 0.0, "last_dispatch_year": None,
    })
    _add_membership(
        context, character_id=founder_id, faction_id=faction_id, role="founder"
    )
    governance = context.state.entities.require(faction_id, FACTION_GOVERNANCE)
    governance["founder_npc_id"] = founder_id
    context.state.entities.put(faction_id, FACTION_GOVERNANCE, governance)
    _recruit_faction_npc(context, definitions, faction_id)
    _recruit_faction_npc(context, definitions, faction_id)
    context.emit(
        "faction.npc_founded", source="world_simulation",
        scope=EventScope("world", world_id),
        payload={
            "faction_id": faction_id, "founder_id": founder_id,
            "kind": kind, "world_id": world_id,
        },
    )


def _pressure_weak_npc_powers(
    context: SimulationContext, definitions: GameDefinitions,
) -> None:
    rules = dict(definitions.systems.get("player_faction", {}))
    chance = float(rules.get("pressure_chance_per_unit", 0.35))
    limit = int(rules.get("pressure_limit", 3))
    for faction_id in list(context.state.entities.with_component(FACTION_PROFILE)):
        profile = context.state.entities.require(faction_id, FACTION_PROFILE)
        if not bool(profile.get("active")) or not bool(profile.get("founded_by_npc")):
            continue
        threshold = _governance_threshold(definitions, str(profile["world_id"]))
        has_anchor = False
        for edge in context.state.relations.find(
            target_id=faction_id, kind=MEMBERSHIP
        ):
            life = context.state.entities.require(edge.source_id, LIFE)
            location = context.state.entities.require(edge.source_id, LOCATION)
            cultivation = context.state.entities.require(edge.source_id, CULTIVATION)
            if (
                bool(life.get("alive"))
                and location.get("world_id") == profile.get("world_id")
                and definitions.realm_index(str(cultivation["realm_id"])) >= threshold
            ):
                has_anchor = True
                break
        governance = context.state.entities.require(faction_id, FACTION_GOVERNANCE)
        if has_anchor:
            governance["pressure"] = max(0, int(governance.get("pressure", 0)) - 1)
        elif context.rng.random() < chance:
            governance["pressure"] = int(governance.get("pressure", 0)) + 1
        context.state.entities.put(faction_id, FACTION_GOVERNANCE, governance)
        if int(governance.get("pressure", 0)) >= limit:
            _dissolve_faction(
                context, faction_id, reason="lost_governance_anchor"
            )


def _on_action_completed(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = str(event.payload.get("actor_id", ""))
        if (
            actor_id != context.state.controlled_entity_id
            or not event.payload.get("token")
        ):
            return
        player_rng_state = context.rng.getstate()
        diplomacy = context.state.entities.require(actor_id, DIPLOMACY_STATE)
        relations = dict(diplomacy.get("relations", {}))
        _expire_truces(context, actor_id, relations)
        _ensure_declared_wars(context, definitions, actor_id, relations)
        _grant_alliance_benefits(
            context, definitions, actor_id, relations
        )
        chance = float(definitions.systems.get("race_diplomacy", {}).get(
            "unit_event_chance", 0.08
        ))
        if context.rng.random() < chance:
            _change_random_relation(
                context, definitions, actor_id, relations, kind="race"
            )
        if context.rng.random() < chance:
            _change_random_relation(
                context, definitions, actor_id, relations, kind="faction"
            )
        diplomacy["relations"] = relations
        context.state.entities.put(actor_id, DIPLOMACY_STATE, diplomacy)
        _simulate_npc_duel(context, definitions, actor_id)
        years = max(1, int(event.payload.get("years", 1)))
        _recover_npc_conditions(context, definitions, years)
        _notorious_npc_killings(context, definitions, actor_id, years)
        _maybe_found_npc_power(context, definitions, actor_id)
        _pressure_weak_npc_powers(context, definitions)
        context.rng.setstate(player_rng_state)

    return handler


def register_world_simulation_domain(
    bus: CommandBus, definitions: GameDefinitions
) -> None:
    bus.event_bus.register("core.game.created", _on_game_created(definitions))
    bus.event_bus.register("core.action.completed", _on_action_completed(definitions))

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .actions import ACTION_RUNTIME
from .character import IDENTITY, LIFE, character_view
from .combat import combat_snapshot, resolve_team_combat
from .cultivation import CULTIVATION
from .definitions import GameDefinitions
from .economy import INVENTORY
from .factions import (
    DIPLOMACY_STATE,
    FACTION_GOVERNANCE,
    FACTION_PROFILE,
    MEMBERSHIP,
    _active_membership,
    _add_membership,
    _diplomacy_key,
    _has_faction_voice,
)
from .family import FAMILY_PROFILE, LINEAGE
from .party import party_combat_snapshot, party_member_ids
from .presentation import PREFERENCES
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


WAR_PROFILE = "war.profile"
BOUNTY_STATE = "governance.bounties"
WAR_TERMS = {
    "execute": 30,
    "alliance": 18,
    "vassal": 55,
    "change_relation": 25,
    "stones": 20,
    "supplies": 25,
    "dissolve": 70,
    "annex": 90,
    "white_peace": 0,
}


@dataclass(frozen=True, slots=True)
class WarAction:
    actor_id: str
    war_id: str
    action: str
    ally_id: str = ""


@dataclass(frozen=True, slots=True)
class WarPeace:
    actor_id: str
    war_id: str
    term: str = "white_peace"
    target_id: str = ""
    target_power_id: str = ""
    third_party_id: str = ""
    third_status: str = "neutral"
    concede: bool = False


@dataclass(frozen=True, slots=True)
class IssueBounty:
    actor_id: str
    target_id: str
    authority: str = ""


def _default_bounties() -> dict[str, Any]:
    return {"next_sequence": 1, "orders": []}


def reconcile_war_state(state: WorldState) -> None:
    for entity_id in state.entities.with_component(IDENTITY):
        component = state.entities.get(entity_id, BOUNTY_STATE) or _default_bounties()
        component["next_sequence"] = max(1, int(component.get("next_sequence", 1)))
        component["orders"] = [
            dict(row) for row in component.get("orders", [])
            if isinstance(row, dict) and str(row.get("target_id", ""))
        ]
        state.entities.put(entity_id, BOUNTY_STATE, component)
    for war_id in list(state.entities.with_component(WAR_PROFILE)):
        war = state.entities.require(war_id, WAR_PROFILE)
        war.setdefault("coalitions", {
            "attacker": [war.get("attacker_id")],
            "defender": [war.get("defender_id")],
        })
        war.setdefault("roster_owner", {})
        war.setdefault("called_allies", {})
        war.setdefault("logs", [])
        war.setdefault("peace_terms", [])
        state.entities.put(war_id, WAR_PROFILE, war)


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    context.state.entities.put(
        str(event.payload["entity_id"]), BOUNTY_STATE, _default_bounties()
    )


def _action_unit(state: WorldState, actor_id: str) -> int:
    runtime = state.entities.require(actor_id, ACTION_RUNTIME)
    return max(0, int(runtime.get("next_sequence", 1)) - 1)


def _rules(definitions: GameDefinitions) -> dict[str, Any]:
    return dict(definitions.systems.get("war_system", {}))


def _power_name(
    state: WorldState, definitions: GameDefinitions, kind: str, power_id: str,
) -> str:
    if kind == "race":
        return str(definitions.races.get(power_id, {}).get("name", power_id))
    profile = state.entities.get(power_id, FACTION_PROFILE)
    return str(profile.get("name", power_id)) if profile else power_id


def _power_world(
    state: WorldState, definitions: GameDefinitions, kind: str, power_id: str,
) -> str | None:
    if kind == "faction":
        profile = state.entities.get(power_id, FACTION_PROFILE)
        return str(profile["world_id"]) if profile else None
    worlds = list(definitions.races.get(power_id, {}).get("worlds", []))
    return str(worlds[0]) if worlds else None


def _power_members(
    state: WorldState,
    definitions: GameDefinitions,
    kind: str,
    power_id: str,
    world_id: str,
) -> list[str]:
    if kind == "faction":
        ids = [
            edge.source_id
            for edge in state.relations.find(target_id=power_id, kind=MEMBERSHIP)
        ]
    else:
        ids = [
            entity_id for entity_id in state.entities.with_component(IDENTITY)
            if str(state.entities.require(entity_id, IDENTITY).get("race")) == power_id
        ]
    available = [
        entity_id for entity_id in ids
        if bool(state.entities.require(entity_id, LIFE).get("alive"))
        and state.entities.require(entity_id, LOCATION).get("world_id") == world_id
    ]
    available.sort(
        key=lambda entity_id: float(
            combat_snapshot(state, definitions, entity_id)["power"]
        ),
        reverse=True,
    )
    return available[: int(_rules(definitions).get("roster_cap", 24))]


def _participant_side(war: dict[str, Any], power_id: str | None) -> str | None:
    if not power_id:
        return None
    for side in ("attacker", "defender"):
        if power_id in set(map(str, war.get("coalitions", {}).get(side, []))):
            return side
    return None


def _actor_power_id(
    state: WorldState, actor_id: str, kind: str,
) -> str | None:
    if kind == "race":
        return str(state.entities.require(actor_id, IDENTITY)["race"])
    membership = _active_membership(state, actor_id)
    return membership.target_id if membership else None


def _actor_side(state: WorldState, actor_id: str, war: dict[str, Any]) -> str | None:
    if state.entities.require(actor_id, LOCATION).get("world_id") != war.get("world_id"):
        return None
    return _participant_side(
        war, _actor_power_id(state, actor_id, str(war["kind"]))
    )


def _has_voice(
    state: WorldState,
    definitions: GameDefinitions,
    actor_id: str,
    kind: str,
    power_id: str,
) -> bool:
    if kind == "faction":
        return _has_faction_voice(state, definitions, actor_id, power_id)
    cultivation = state.entities.require(actor_id, CULTIVATION)
    world_id = str(state.entities.require(actor_id, LOCATION)["world_id"])
    return (
        str(state.entities.require(actor_id, IDENTITY)["race"]) == power_id
        and definitions.worlds[world_id].tier >= 2
        and definitions.realm_index(str(cultivation["realm_id"]))
        >= int(definitions.systems["world_travel"]["required_realm"])
    )


def _formation_modifier(state: WorldState, member_ids: list[str]) -> tuple[float, dict[str, Any] | None]:
    candidates = []
    for entity_id in member_ids:
        component = state.entities.get(entity_id, "formation.nine_palace") or {}
        active = component.get("active")
        if not isinstance(active, dict):
            continue
        integrity = float(active.get("integrity", active.get("durability", 1.0)))
        if integrity > 1:
            integrity /= 100
        candidates.append((integrity, entity_id, active))
    if not candidates:
        return 1.0, None
    integrity, owner_id, active = max(candidates, key=lambda row: row[0])
    modifier = 1 + min(0.12, max(0.0, integrity) * 0.08)
    return modifier, {
        "owner_id": owner_id,
        "id": active.get("id"),
        "name": active.get("name", "九宫阵"),
        "integrity": round(integrity, 4),
        "modifier": round(modifier, 6),
    }


def _available_roster(state: WorldState, war: dict[str, Any], side: str) -> list[str]:
    escaped = set(map(str, war.get("escaped", {}).get(side, [])))
    world_id = str(war["world_id"])
    return [
        str(entity_id) for entity_id in war.get("roster", {}).get(side, [])
        if str(entity_id) not in escaped
        and state.entities.exists(str(entity_id))
        and bool(state.entities.require(str(entity_id), LIFE).get("alive"))
        and state.entities.require(str(entity_id), LOCATION).get("world_id") == world_id
    ]


def _team_coefficient(count: int) -> float:
    return 0.5 if count == 2 else 0.25 if count >= 3 else 0.0


def _side_power(
    state: WorldState,
    definitions: GameDefinitions,
    war: dict[str, Any],
    side: str,
) -> dict[str, Any]:
    roster = _available_roster(state, war, side)
    actor_id = state.controlled_entity_id
    rows: list[tuple[float, str]] = []
    excluded: set[str] = set()
    if actor_id is not None and _actor_side(state, actor_id, war) == side:
        party = party_combat_snapshot(state, definitions, actor_id)
        rows.append((float(party["power"]), actor_id))
        excluded = {actor_id, *party_member_ids(state, actor_id)}
    rows.extend(
        (float(combat_snapshot(state, definitions, entity_id)["power"]), entity_id)
        for entity_id in roster if entity_id not in excluded
    )
    rows.sort(reverse=True)
    elites = rows[:3]
    coefficient = _team_coefficient(len(elites))
    raw = (
        elites[0][0] + sum(row[0] for row in elites[1:]) * coefficient
        if elites else 1.0
    )
    formation_modifier, formation = _formation_modifier(state, roster)
    defender = 1 + float(_rules(definitions).get("defender_power_bonus", 0.10)) if side == "defender" else 1.0
    return {
        "power": round(raw * formation_modifier * defender, 4),
        "raw_power": round(raw, 4),
        "members": len(roster),
        "elite_ids": [row[1] for row in elites],
        "formation": formation,
        "defender_multiplier": defender,
    }


def _append_log(
    state: WorldState, war: dict[str, Any], title: str, text: str,
) -> None:
    logs = list(war.get("logs", []))
    actor_id = state.controlled_entity_id
    unit = _action_unit(state, actor_id) if actor_id else 0
    logs.append({"unit": unit, "year": state.clock.year, "title": title, "text": text})
    war["logs"] = logs[-80:]


def _create_war(
    context: SimulationContext,
    definitions: GameDefinitions,
    *,
    actor_id: str,
    kind: str,
    attacker_id: str,
    defender_id: str,
    world_id: str,
) -> str:
    for war_id in context.state.entities.with_component(WAR_PROFILE):
        existing = context.state.entities.require(war_id, WAR_PROFILE)
        if (
            existing.get("status") in {"active", "peace_ready"}
            and existing.get("kind") == kind
            and {existing.get("attacker_id"), existing.get("defender_id")}
            == {attacker_id, defender_id}
        ):
            return war_id
    war_id = context.state.entities.create("war")
    attacker_roster = _power_members(
        context.state, definitions, kind, attacker_id, world_id
    )
    defender_roster = _power_members(
        context.state, definitions, kind, defender_id, world_id
    )
    unit = _action_unit(context.state, actor_id)
    war = {
        "kind": kind,
        "world_id": world_id,
        "attacker_id": attacker_id,
        "defender_id": defender_id,
        "status": "active",
        "start_year": context.state.clock.year,
        "start_unit": unit,
        "morale": {"attacker": 100.0, "defender": 100.0},
        "exhaustion": {"attacker": 0.0, "defender": 0.0},
        "war_score": 0.0,
        "battles": 0,
        "abstract_rounds": 0,
        "preliminary_resolved": False,
        "roster": {"attacker": attacker_roster, "defender": defender_roster},
        "roster_owner": {
            **{entity_id: attacker_id for entity_id in attacker_roster},
            **{entity_id: defender_id for entity_id in defender_roster},
        },
        "coalitions": {
            "attacker": [attacker_id], "defender": [defender_id],
        },
        "called_allies": {},
        "escaped": {"attacker": [], "defender": []},
        "logs": [],
        "controller_id": (
            actor_id
            if _has_voice(context.state, definitions, actor_id, kind, attacker_id)
            else None
        ),
        "peace_terms": [],
    }
    _append_log(
        context.state,
        war,
        "宣战",
        f"{_power_name(context.state, definitions, kind, attacker_id)}向"
        f"{_power_name(context.state, definitions, kind, defender_id)}正式宣战。",
    )
    context.state.entities.put(war_id, WAR_PROFILE, war)
    context.emit(
        "war.declared",
        source="war",
        scope=EventScope("world", world_id),
        payload={
            "war_id": war_id,
            "kind": kind,
            "attacker_id": attacker_id,
            "defender_id": defender_id,
        },
    )
    return war_id


def _on_diplomacy_voted(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        if not bool(event.payload.get("passed")):
            return
        relation = dict(event.payload.get("relation", {}))
        if relation.get("status") != "war":
            return
        actor_id = str(event.payload["actor_id"])
        first_id = str(relation["first_id"])
        second_id = str(relation["second_id"])
        kind = str(relation["kind"])
        attacker_id = _actor_power_id(context.state, actor_id, kind)
        if attacker_id not in {first_id, second_id}:
            raise ValueError("宣战发起者不属于外交关系任一方")
        defender_id = second_id if attacker_id == first_id else first_id
        diplomacy = context.state.entities.require(actor_id, DIPLOMACY_STATE)
        relation_key = _diplomacy_key(kind, first_id, second_id)
        persisted_relation = dict(
            diplomacy.get("relations", {}).get(relation_key, relation)
        )
        truce_until = max(
            int(persisted_relation.get("truce_until_unit", 0)),
            int(persisted_relation.get("war_truce_until_unit", 0)),
        )
        current_unit = _action_unit(context.state, actor_id)
        if current_unit < truce_until:
            raise ValueError(
                f"系统停战期尚余 {truce_until - current_unit} 个行动单位，不能宣战"
            )
        world_id = str(context.state.entities.require(actor_id, LOCATION)["world_id"])
        _create_war(
            context,
            definitions,
            actor_id=actor_id,
            kind=kind,
            attacker_id=attacker_id,
            defender_id=defender_id,
            world_id=world_id,
        )

    return handler


def _finish_by_morale(
    state: WorldState, definitions: GameDefinitions, war: dict[str, Any],
) -> bool:
    if war["morale"]["attacker"] > 0 and war["morale"]["defender"] > 0:
        return False
    winner = "defender" if war["morale"]["attacker"] <= 0 else "attacker"
    loser = "attacker" if winner == "defender" else "defender"
    war["status"] = "peace_ready"
    war["winner"] = winner
    war["loser"] = loser
    score = max(20.0, abs(float(war.get("war_score", 0.0))))
    war["war_score"] = score if winner == "attacker" else -score
    _append_log(
        state,
        war,
        "士气崩溃",
        f"{_power_name(state, definitions, str(war['kind']), str(war[f'{loser}_id']))}"
        "阵营士气归零，战争进入和谈。",
    )
    return True


def _resolve_round(
    context: SimulationContext,
    definitions: GameDefinitions,
    war: dict[str, Any],
    *,
    player_side: str | None = None,
) -> str:
    attacker = _side_power(context.state, definitions, war, "attacker")
    defender = _side_power(context.state, definitions, war, "defender")
    ratio = max(0.125, float(attacker["power"]) / max(1.0, float(defender["power"])))
    attacker_chance = max(0.08, min(0.92, 0.5 + math.log2(ratio) * 0.18))
    winner = "attacker" if context.rng.random() < attacker_chance else "defender"
    loser = "defender" if winner == "attacker" else "attacker"
    loss = context.rng.uniform(8.0, 18.0)
    gain = context.rng.uniform(1.0, 4.0)
    war["morale"][loser] = max(0.0, float(war["morale"][loser]) - loss)
    war["morale"][winner] = min(150.0, float(war["morale"][winner]) + gain)
    score_delta = context.rng.uniform(7.0, 15.0)
    war["war_score"] = float(war.get("war_score", 0.0)) + (
        score_delta if winner == "attacker" else -score_delta
    )
    war["battles"] = int(war.get("battles", 0)) + 1
    for side in ("attacker", "defender"):
        war["exhaustion"][side] = min(
            100.0, float(war["exhaustion"][side]) + 7.0
        )
    casualty = ""
    candidates = _available_roster(context.state, war, loser)
    actor_id = context.state.controlled_entity_id
    candidates = [entity_id for entity_id in candidates if entity_id != actor_id]
    if candidates and context.rng.random() < float(
        _rules(definitions).get("ai_casualty_roll_chance", 0.34)
    ):
        victim_id = context.rng.choice(candidates)
        if context.rng.random() < 0.28:
            context.emit(
                "character.lethal_hazard",
                source="war",
                scope=EventScope.entity(victim_id),
                payload={"entity_id": victim_id, "reason": "战场阵亡"},
            )
            casualty = f" {character_view(context.state, victim_id)['name']}阵亡。"
        else:
            escaped = dict(war.get("escaped", {}))
            rows = list(escaped.get(loser, []))
            rows.append(victim_id)
            escaped[loser] = list(dict.fromkeys(rows))
            war["escaped"] = escaped
            casualty = f" {character_view(context.state, victim_id)['name']}负伤退场。"
    winner_name = _power_name(
        context.state, definitions, str(war["kind"]), str(war[f"{winner}_id"])
    )
    text = (
        f"{winner_name}赢得第{war['battles']}场会战；攻守胜率"
        f" {attacker_chance:.0%}/{1 - attacker_chance:.0%}。{casualty}"
    )
    _append_log(
        context.state,
        war,
        "玩家参战" if player_side else "会战",
        text,
    )
    _finish_by_morale(context.state, definitions, war)
    return winner


def _war_action_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, WarAction):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能处理当前角色参与的战争")
        war = context.state.entities.get(command.war_id, WAR_PROFILE)
        if war is None or war.get("status") not in {"active", "peace_ready"}:
            raise ValueError("这场战争已经结束或不存在")
        if context.state.relations.find(target_id=command.actor_id, kind="combat_prisoner"):
            raise ValueError("服刑期间不能处理征伐")
        side = _actor_side(context.state, command.actor_id, war)
        if side is None:
            raise ValueError("你并非这场战争的参战方")
        own_power_id = _actor_power_id(context.state, command.actor_id, str(war["kind"]))
        has_voice = bool(
            own_power_id
            and own_power_id == war.get(f"{side}_id")
            and _has_voice(
                context.state, definitions, command.actor_id,
                str(war["kind"]), own_power_id,
            )
        )
        if command.action != "participate_round" and not has_voice:
            raise ValueError("你尚未取得本势力的战争指挥权")
        if command.action == "conquest":
            if war.get("status") != "active":
                raise ValueError("战场胜负已定，只能进行和谈")
            if bool(war.get("preliminary_resolved")):
                raise ValueError("先锋出阵已经结算")
            enemy = "defender" if side == "attacker" else "attacker"
            opponents = _available_roster(context.state, war, enemy)[:3]
            if not opponents:
                war["morale"][enemy] = 0.0
                _finish_by_morale(context.state, definitions, war)
            else:
                from .story import queue_story_event

                queue_story_event(
                    context,
                    definitions,
                    command.actor_id,
                    "EVT_WAR_VANGUARD_001",
                    reason="war_vanguard",
                    runtime={
                        "war_id": command.war_id,
                        "enemy_ids": opponents,
                        "attacker": _power_name(
                            context.state, definitions, str(war["kind"]),
                            str(war["attacker_id"]),
                        ),
                        "defender": _power_name(
                            context.state, definitions, str(war["kind"]),
                            str(war["defender_id"]),
                        ),
                    },
                )
        elif command.action == "round":
            if war.get("status") != "active":
                raise ValueError("战场胜负已定，只能进行和谈")
            if not bool(war.get("preliminary_resolved")):
                war["preliminary_resolved"] = True
                war["vanguard_skipped"] = True
                _append_log(
                    context.state, war, "放弃先锋战",
                    "双方主力直接推进会战，本场不获得先锋士气修正。",
                )
            _resolve_round(context, definitions, war)
        elif command.action == "participate_round":
            if war.get("status") != "active":
                raise ValueError("战场胜负已定，无法再次参战")
            enemy = "defender" if side == "attacker" else "attacker"
            if not bool(war.get("preliminary_resolved")):
                war["preliminary_resolved"] = True
                war["vanguard_skipped"] = True
            opponents = _available_roster(context.state, war, enemy)[:3]
            if not opponents:
                war["morale"][enemy] = 0.0
                _finish_by_morale(context.state, definitions, war)
            else:
                report = resolve_team_combat(
                    context,
                    definitions,
                    attacker_id=command.actor_id,
                    target_ids=opponents,
                    terrain=str(war["world_id"]),
                    source="war",
                )
                if report["outcome"] == "victory":
                    war["morale"][enemy] = max(
                        0.0, float(war["morale"][enemy]) - 12.0
                    )
                    war["war_score"] = float(war.get("war_score", 0.0)) + (
                        12 if side == "attacker" else -12
                    )
                else:
                    war["morale"][side] = max(
                        0.0, float(war["morale"][side]) - 10.0
                    )
                war["battles"] = int(war.get("battles", 0)) + 1
                _append_log(
                    context.state,
                    war,
                    f"玩家参战·第{war['battles']}场",
                    "你率队击退敌军。" if report["outcome"] == "victory"
                    else "你未能击穿敌阵，在主力接应下退守。",
                )
                _finish_by_morale(context.state, definitions, war)
        elif command.action == "retreat":
            if war.get("status") != "active":
                raise ValueError("战场胜负已经确定")
            war["morale"][side] = 0.0
            _append_log(context.state, war, "主动撤退", "本方主动撤出战场。")
            _finish_by_morale(context.state, definitions, war)
        elif command.action == "call_allies":
            if war.get("status") != "active" or not command.ally_id:
                raise ValueError("请选择仍可参战的盟友")
            state = context.state.entities.require(command.actor_id, DIPLOMACY_STATE)
            key = _diplomacy_key(str(war["kind"]), str(own_power_id), command.ally_id)
            relation = dict(dict(state.get("relations", {})).get(key, {}))
            if relation.get("status") not in {"alliance", "vassal"}:
                raise ValueError("该势力并非可邀请的盟友")
            call_key = f"{side}:{command.ally_id}"
            unit = _action_unit(context.state, command.actor_id)
            prior = dict(war.get("called_allies", {}).get(call_key, {}))
            cooldown = int(_rules(definitions).get("ally_call_cooldown_units", 3))
            if prior and (
                prior.get("accepted")
                or unit - int(prior.get("unit", 0)) < cooldown
            ):
                raise ValueError("盟友已经参战或仍处于重邀冷却")
            chance = max(0.10, min(
                0.98,
                float(_rules(definitions).get("ally_call_base_chance", 0.68))
                + float(relation.get("affinity", 0.0)) / 400,
            ))
            accepted = context.rng.random() < chance
            calls = dict(war.get("called_allies", {}))
            calls[call_key] = {
                "accepted": accepted, "unit": unit, "chance": round(chance, 3),
            }
            war["called_allies"] = calls
            if accepted:
                coalition = dict(war["coalitions"])
                coalition[side] = list(dict.fromkeys([
                    *coalition[side], command.ally_id,
                ]))
                war["coalitions"] = coalition
                rows = _power_members(
                    context.state, definitions, str(war["kind"]),
                    command.ally_id, str(war["world_id"]),
                )[: int(_rules(definitions).get("ally_roster_cap", 12))]
                roster = dict(war["roster"])
                roster[side] = list(dict.fromkeys([*roster[side], *rows]))[: int(
                    _rules(definitions).get("coalition_roster_cap", 48)
                )]
                war["roster"] = roster
                owners = dict(war.get("roster_owner", {}))
                owners.update({entity_id: command.ally_id for entity_id in rows})
                war["roster_owner"] = owners
            _append_log(
                context.state,
                war,
                "召集盟友",
                f"{_power_name(context.state, definitions, str(war['kind']), command.ally_id)}"
                + ("接受召集。" if accepted else "拒绝参战。"),
            )
        else:
            raise ValueError("未知战争行动")
        context.state.entities.put(command.war_id, WAR_PROFILE, war)
        context.emit(
            "war.action.resolved",
            source="war",
            scope=EventScope("world", str(war["world_id"])),
            payload={
                "war_id": command.war_id,
                "actor_id": command.actor_id,
                "action": command.action,
                "status": war["status"],
            },
        )

    return handler


def register_war_story_effects(
    registry: Any, definitions: GameDefinitions,
) -> None:
    from .story import EffectOutcome

    def vanguard(
        context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any],
    ) -> EffectOutcome:
        runtime = dict(pending.get("runtime", {}))
        war_id = str(runtime.get("war_id", ""))
        war = context.state.entities.get(war_id, WAR_PROFILE)
        if (
            war is None or war.get("status") != "active"
            or bool(war.get("preliminary_resolved"))
        ):
            return EffectOutcome("war_absent", "战阵已经变化，先锋对阵不再有效。")
        if str(effect.payload.get("mode", "")) == "delay":
            return EffectOutcome("delayed", "你暂缓出阵，先锋战尚未结算。")
        side = _actor_side(context.state, actor_id, war)
        if side is None:
            return EffectOutcome("authority_lost", "你已经不再属于任一参战阵营。")
        opponents = [
            str(entity_id) for entity_id in runtime.get("enemy_ids", [])
            if context.state.entities.exists(str(entity_id))
            and bool(context.state.entities.require(str(entity_id), LIFE).get("alive"))
        ]
        enemy = "defender" if side == "attacker" else "attacker"
        if not opponents:
            war["morale"][enemy] = 0.0
            war["preliminary_resolved"] = True
            _finish_by_morale(context.state, definitions, war)
            context.state.entities.put(war_id, WAR_PROFILE, war)
            return EffectOutcome("victory", "敌方先锋已经溃散，我方不战而胜。")
        report = resolve_team_combat(
            context,
            definitions,
            attacker_id=actor_id,
            target_ids=opponents,
            terrain=str(war["world_id"]),
            source="war",
        )
        won = report["outcome"] == "victory"
        if won:
            war["morale"][side] = min(
                150.0, float(war["morale"][side]) + 30.0
            )
        else:
            war["morale"][side] = max(
                0.0, float(war["morale"][side]) - 20.0
            )
        war["preliminary_resolved"] = True
        _append_log(
            context.state,
            war,
            "玩家先锋战",
            "先锋目标达成，我方士气大振。" if won
            else "先锋目标未能达成，我方士气受挫。",
        )
        _finish_by_morale(context.state, definitions, war)
        context.state.entities.put(war_id, WAR_PROFILE, war)
        return EffectOutcome(
            "victory" if won else "defeat",
            "你率队击破敌方先锋。" if won else "你未能击穿敌方先锋阵列。",
        )

    registry.register("war_vanguard", vanguard)


def _update_diplomacy_after_peace(
    state: WorldState,
    definitions: GameDefinitions,
    actor_id: str,
    war: dict[str, Any],
    status: str,
    *,
    winner_id: str,
    loser_id: str,
    overlord: str | None = None,
    subject: str | None = None,
) -> None:
    diplomacy = state.entities.require(actor_id, DIPLOMACY_STATE)
    relations = dict(diplomacy.get("relations", {}))
    kind = str(war["kind"])
    key = _diplomacy_key(kind, winner_id, loser_id)
    relation = dict(relations.get(key, {
        "kind": kind,
        "first_id": min(winner_id, loser_id),
        "second_id": max(winner_id, loser_id),
    }))
    relation.update(
        status=status,
        since_year=state.clock.year,
        affinity={"truce": -10.0, "alliance": 72.0, "vassal": 45.0}.get(status, 0.0),
        overlord=overlord,
        subject=subject,
    )
    actor = state.controlled_entity_id
    truce_units = int(_rules(definitions).get("truce_units", 5))
    truce_until = (_action_unit(state, actor) if actor else 0) + truce_units
    relation["truce_until_unit"] = truce_until
    relation["war_truce_until_unit"] = truce_until
    relations[key] = relation
    for attacker_id in map(str, war.get("coalitions", {}).get("attacker", [])):
        for defender_id in map(str, war.get("coalitions", {}).get("defender", [])):
            cross_key = _diplomacy_key(kind, attacker_id, defender_id)
            cross = dict(relations.get(cross_key, {
                "kind": kind,
                "first_id": min(attacker_id, defender_id),
                "second_id": max(attacker_id, defender_id),
                "affinity": -40.0,
            }))
            cross["war_truce_until_unit"] = truce_until
            if cross_key != key and cross.get("status") not in {"alliance", "vassal"}:
                cross.update(
                    status="truce",
                    affinity=max(-20.0, float(cross.get("affinity", -40.0))),
                    since_year=state.clock.year,
                    truce_until_unit=truce_until,
                )
            relations[cross_key] = cross
    diplomacy["relations"] = relations
    state.entities.put(actor_id, DIPLOMACY_STATE, diplomacy)


def _dissolve_or_annex(
    context: SimulationContext,
    loser_id: str,
    winner_id: str,
    *,
    annex: bool,
) -> None:
    loser_profile = context.state.entities.require(loser_id, FACTION_PROFILE)
    loser_profile["active"] = False
    context.state.entities.put(loser_id, FACTION_PROFILE, loser_profile)
    governance = context.state.entities.require(loser_id, FACTION_GOVERNANCE)
    governance["controller_id"] = None
    context.state.entities.put(loser_id, FACTION_GOVERNANCE, governance)
    for edge in list(context.state.relations.find(target_id=loser_id, kind=MEMBERSHIP)):
        ended = context.state.relations.end(
            edge.relation_id, ended_year=context.state.clock.year
        )
        metadata = dict(ended.metadata)
        metadata["end_reason"] = "annexed" if annex else "dissolved"
        context.state.relations.replace_metadata(ended.relation_id, metadata)
        if annex and bool(context.state.entities.require(edge.source_id, LIFE).get("alive")):
            _add_membership(
                context,
                character_id=edge.source_id,
                faction_id=winner_id,
                role=str(edge.metadata.get("role", "member")),
            )


def _war_peace_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, WarPeace):
            raise TypeError("命令类型错误")
        war = context.state.entities.get(command.war_id, WAR_PROFILE)
        if war is None or war.get("status") not in {"active", "peace_ready"}:
            raise ValueError("当前没有可供和谈的战争")
        side = _actor_side(context.state, command.actor_id, war)
        own_power_id = _actor_power_id(context.state, command.actor_id, str(war["kind"]))
        if (
            side is None or own_power_id is None
            or own_power_id != war.get(f"{side}_id")
            or not _has_voice(
                context.state, definitions, command.actor_id,
                str(war["kind"]), own_power_id,
            )
        ):
            raise ValueError("你没有代表势力签署和约的权力")
        if command.term not in WAR_TERMS:
            raise ValueError("未知战争条款")
        if (
            int(war.get("battles", 0)) < 2
            and war.get("status") != "peace_ready"
            and command.term != "white_peace"
        ):
            raise ValueError("至少经历两场战事后才能提出有条件和谈")
        beneficiary = (
            "defender" if side == "attacker" else "attacker"
        ) if command.concede else side
        loser_side = "defender" if beneficiary == "attacker" else "attacker"
        winner_id = str(war[f"{beneficiary}_id"])
        loser_id = command.target_power_id or str(war[f"{loser_side}_id"])
        if loser_id not in set(map(str, war["coalitions"][loser_side])):
            raise ValueError("和谈目标不属于战败阵营")
        effective_score = float(war.get("war_score", 0.0)) * (
            1 if beneficiary == "attacker" else -1
        )
        cost = WAR_TERMS[command.term]
        if loser_id != str(war[f"{loser_side}_id"]):
            cost = int(round(
                cost * float(_rules(definitions).get(
                    "ally_term_cost_multiplier", 1.25
                ))
            ))
        if (
            not command.concede and command.term != "white_peace"
            and effective_score < cost
        ):
            raise ValueError(
                f"当前战争分数 {effective_score:.0f}，不足以提出该条款（需要 {cost}）"
            )
        detail = "双方恢复和平"
        diplomacy_status = "truce"
        if command.term == "execute":
            candidates = [
                entity_id for entity_id in _available_roster(
                    context.state, war, loser_side
                )
                if war.get("roster_owner", {}).get(entity_id) == loser_id
            ]
            victim_id = command.target_id or (candidates[0] if candidates else "")
            if victim_id not in candidates:
                raise ValueError("指定处死的修士不属于战败方参战名册")
            context.emit(
                "character.lethal_hazard",
                source="war",
                scope=EventScope.entity(victim_id),
                payload={"entity_id": victim_id, "reason": "战败和约指定处死"},
            )
            detail = f"{character_view(context.state, victim_id)['name']}依约被处死"
        elif command.term == "alliance":
            diplomacy_status = "alliance"
            detail = "双方被和约确立为同盟"
        elif command.term == "vassal":
            diplomacy_status = "vassal"
            detail = f"{_power_name(context.state, definitions, str(war['kind']), loser_id)}成为附庸"
        elif command.term == "stones":
            amount = int(_rules(definitions).get("stone_tribute", 10000))
            actor_power = _actor_power_id(context.state, command.actor_id, str(war["kind"]))
            if actor_power == winner_id:
                context.emit(
                    "story.effect.inventory.changed",
                    source="war",
                    scope=EventScope.entity(command.actor_id),
                    payload={
                        "entity_id": command.actor_id,
                        "item_id": "spirit_stone",
                        "quantity": amount,
                        "reason": "war_tribute",
                    },
                )
            elif actor_power == loser_id:
                inventory = context.state.entities.require(command.actor_id, INVENTORY)
                amount = min(amount, int(dict(inventory.get("items", {})).get("spirit_stone", 0)))
                if amount:
                    context.emit(
                        "story.effect.inventory.changed",
                        source="war",
                        scope=EventScope.entity(command.actor_id),
                        payload={
                            "entity_id": command.actor_id,
                            "item_id": "spirit_stone",
                            "quantity": -amount,
                            "reason": "war_tribute",
                        },
                    )
            detail = f"战败方向胜方上供灵石 {amount}"
        elif command.term == "supplies":
            actor_power = _actor_power_id(
                context.state, command.actor_id, str(war["kind"])
            )
            supplied: list[str] = []
            if actor_power == winner_id:
                pool = [
                    good.content_id for good in definitions.market_goods
                    if good.kind == "item"
                    and good.content_id in definitions.items
                    and "currency" not in definitions.items[good.content_id].tags
                ]
                for item_id in list(dict.fromkeys(pool))[:3]:
                    context.emit(
                        "story.effect.inventory.changed",
                        source="war",
                        scope=EventScope.entity(command.actor_id),
                        payload={
                            "entity_id": command.actor_id,
                            "item_id": item_id,
                            "quantity": 1,
                            "reason": "war_supplies",
                        },
                    )
                    supplied.append(definitions.items[item_id].name)
            elif actor_power == loser_id:
                inventory = context.state.entities.require(
                    command.actor_id, INVENTORY
                )
                for item_id, quantity in list(
                    dict(inventory.get("items", {})).items()
                ):
                    if len(supplied) >= 3:
                        break
                    if item_id == "spirit_stone" or int(quantity) <= 0:
                        continue
                    context.emit(
                        "story.effect.inventory.changed",
                        source="war",
                        scope=EventScope.entity(command.actor_id),
                        payload={
                            "entity_id": command.actor_id,
                            "item_id": item_id,
                            "quantity": -1,
                            "reason": "war_supplies",
                        },
                    )
                    supplied.append(
                        definitions.items[item_id].name
                        if item_id in definitions.items else item_id
                    )
            detail = "战败方缴纳丹药与装备" + (
                f"（{'、'.join(supplied)}）" if supplied else ""
            )
        elif command.term in {"dissolve", "annex"}:
            if war["kind"] != "faction":
                raise ValueError("种族势力不能被解散或合并")
            winner_power = _side_power(
                context.state, definitions, war, beneficiary
            )["power"]
            loser_power = _side_power(
                context.state, definitions, war, loser_side
            )["power"]
            ratio = float(winner_power) / max(1.0, float(loser_power))
            required = float(_rules(definitions).get(
                "annex_power_ratio" if command.term == "annex" else "dissolve_power_ratio",
                2.5 if command.term == "annex" else 1.35,
            ))
            if ratio < required:
                raise ValueError("胜方总战力尚不足以执行该条款")
            _dissolve_or_annex(
                context, loser_id, winner_id, annex=command.term == "annex"
            )
            detail = (
                f"{_power_name(context.state, definitions, 'faction', loser_id)}并入胜方"
                if command.term == "annex" else "战败宗门就地解散"
            )
        elif command.term == "change_relation":
            if not command.third_party_id or command.third_party_id in {winner_id, loser_id}:
                raise ValueError("必须指定第三方势力")
            if command.third_status not in {"alliance", "truce", "neutral", "vassal"}:
                raise ValueError("第三方外交状态非法")
            diplomacy = context.state.entities.require(
                command.actor_id, DIPLOMACY_STATE
            )
            relations = dict(diplomacy.get("relations", {}))
            third_key = _diplomacy_key(
                str(war["kind"]), loser_id, command.third_party_id
            )
            third = dict(relations.get(third_key, {
                "kind": war["kind"],
                "first_id": min(loser_id, command.third_party_id),
                "second_id": max(loser_id, command.third_party_id),
            }))
            third.update(
                status=command.third_status,
                affinity={
                    "alliance": 65.0, "truce": -5.0,
                    "neutral": 0.0, "vassal": 45.0,
                }[command.third_status],
                since_year=context.state.clock.year,
                overlord=(loser_id if command.third_status == "vassal" else None),
                subject=(
                    command.third_party_id
                    if command.third_status == "vassal" else None
                ),
            )
            relations[third_key] = third
            diplomacy["relations"] = relations
            context.state.entities.put(
                command.actor_id, DIPLOMACY_STATE, diplomacy
            )
            detail = f"战败方被迫对第三方改为{command.third_status}"
        elif command.term != "white_peace":
            raise ValueError("未知战争条款")
        _update_diplomacy_after_peace(
            context.state,
            definitions,
            command.actor_id,
            war,
            diplomacy_status,
            winner_id=winner_id,
            loser_id=loser_id,
            overlord=winner_id if diplomacy_status == "vassal" else None,
            subject=loser_id if diplomacy_status == "vassal" else None,
        )
        war.update(
            status="ended",
            end_year=context.state.clock.year,
            peace_term=command.term,
            winner=None if command.term == "white_peace" else beneficiary,
            peace_terms=[{
                "term": command.term,
                "target_id": command.target_id,
                "target_power_id": loser_id,
                "third_party_id": command.third_party_id,
                "third_status": command.third_status,
            }],
        )
        _append_log(context.state, war, "战争结束", detail)
        context.state.entities.put(command.war_id, WAR_PROFILE, war)
        context.emit(
            "war.peace.concluded",
            source="war",
            scope=EventScope("world", str(war["world_id"])),
            payload={
                "war_id": command.war_id,
                "term": command.term,
                "winner": war["winner"],
            },
        )

    return handler


def _bounty_authorities(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
) -> list[dict[str, str]]:
    authorities: list[dict[str, str]] = []
    membership = _active_membership(state, actor_id)
    if membership and _has_faction_voice(
        state, definitions, actor_id, membership.target_id
    ):
        profile = state.entities.require(membership.target_id, FACTION_PROFILE)
        authorities.append({"id": "sect", "name": str(profile["name"])})
    lineage = state.entities.require(actor_id, LINEAGE)
    family_id = lineage.get("family_id")
    if family_id:
        profile = state.entities.require(str(family_id), FAMILY_PROFILE)
        location = state.entities.require(actor_id, LOCATION)
        if (
            profile.get("controller_id") == actor_id
            and profile.get("world_id") == location.get("world_id")
            and bool(profile.get("active"))
        ):
            authorities.append({"id": "family", "name": str(profile["name"])})
    identity = state.entities.require(actor_id, IDENTITY)
    cultivation = state.entities.require(actor_id, CULTIVATION)
    world_id = str(state.entities.require(actor_id, LOCATION)["world_id"])
    race_id = str(identity["race"])
    if (
        definitions.worlds[world_id].tier >= 2
        and definitions.realm_index(str(cultivation["realm_id"]))
        >= int(definitions.systems["world_travel"]["required_realm"])
    ):
        name = str(definitions.races.get(race_id, {}).get("name", race_id))
        authorities.insert(0, {"id": "race", "name": f"{name}大乘议会"})
    return authorities


def _issue_bounty_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, IssueBounty):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能以当前角色掌握的权力发布通缉")
        if context.state.relations.find(target_id=command.actor_id, kind="combat_prisoner"):
            raise ValueError("服刑期间不能颁布通缉令")
        authorities = _bounty_authorities(
            context.state, definitions, command.actor_id
        )
        if not authorities:
            raise ValueError("至少取得种族、宗门或家族一方话语权才能颁布通缉令")
        authority = next(
            (row for row in authorities if row["id"] == command.authority), None
        ) if command.authority else authorities[0]
        if authority is None:
            raise ValueError("你尚未掌握所选势力的通缉权")
        if (
            not context.state.entities.exists(command.target_id)
            or command.target_id == command.actor_id
            or not bool(context.state.entities.require(command.target_id, LIFE).get("alive"))
            or context.state.entities.require(command.target_id, LOCATION).get("world_id")
            != context.state.entities.require(command.actor_id, LOCATION).get("world_id")
        ):
            raise ValueError("只能通缉当前界面的存活人物")
        component = context.state.entities.require(command.actor_id, BOUNTY_STATE)
        if any(
            row.get("target_id") == command.target_id
            and row.get("status") == "active"
            for row in component.get("orders", [])
        ):
            raise ValueError("此人已经在你的通缉令上")
        sequence = int(component.get("next_sequence", 1))
        target = character_view(context.state, command.target_id)
        bounty = {
            "id": f"bounty:{sequence}",
            "target_id": command.target_id,
            "name": target["name"],
            "world_id": context.state.entities.require(
                command.target_id, LOCATION
            )["world_id"],
            "status": "active",
            "issued_year": context.state.clock.year,
            "attempts": 0,
            "target_power": combat_snapshot(
                context.state, definitions, command.target_id
            )["power"],
            "authority": authority["id"],
            "issuer_name": authority["name"],
        }
        component["next_sequence"] = sequence + 1
        component["orders"] = [*component.get("orders", []), bounty]
        context.state.entities.put(command.actor_id, BOUNTY_STATE, component)
        context.emit(
            "governance.bounty.issued",
            source="war",
            scope=EventScope.entity(command.actor_id),
            payload=bounty,
        )

    return handler


def _on_character_died(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    for actor_id in context.state.entities.with_component(BOUNTY_STATE):
        component = context.state.entities.require(actor_id, BOUNTY_STATE)
        changed = False
        orders = []
        for raw in component.get("orders", []):
            row = dict(raw)
            if row.get("target_id") == entity_id and row.get("status") == "active":
                row["status"] = "completed"
                row["completed_year"] = context.state.clock.year
                changed = True
            orders.append(row)
        if changed:
            component["orders"] = orders
            context.state.entities.put(actor_id, BOUNTY_STATE, component)


def _on_action_completed(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = str(event.payload["actor_id"])
        for war_id in list(context.state.entities.with_component(WAR_PROFILE)):
            war = context.state.entities.require(war_id, WAR_PROFILE)
            if war.get("status") != "active":
                continue
            side = _actor_side(context.state, actor_id, war)
            own_id = _actor_power_id(context.state, actor_id, str(war["kind"]))
            controlled = bool(
                side and own_id and own_id == war.get(f"{side}_id") and _has_voice(
                    context.state, definitions, actor_id, str(war["kind"]), own_id
                )
            )
            preferences = context.state.entities.get(actor_id, PREFERENCES) or {}
            if controlled and not bool(preferences.get("auto_advance_player_wars", False)):
                for war_side in ("attacker", "defender"):
                    war["exhaustion"][war_side] = min(
                        100.0, float(war["exhaustion"][war_side]) + 2.0
                    )
            else:
                _resolve_round(context, definitions, war)
                war["abstract_rounds"] = int(war.get("abstract_rounds", 0)) + 1
            context.state.entities.put(war_id, WAR_PROFILE, war)

    return handler


def war_invariants(definitions: GameDefinitions):
    def validate(state: WorldState) -> list[str]:
        errors: list[str] = []
        for war_id in state.entities.with_component(WAR_PROFILE):
            war = state.entities.require(war_id, WAR_PROFILE)
            if war.get("kind") not in {"faction", "race"}:
                errors.append(f"战争 {war_id} 类型非法")
            if war.get("status") not in {"active", "peace_ready", "ended"}:
                errors.append(f"战争 {war_id} 状态非法")
            if war.get("world_id") not in definitions.worlds:
                errors.append(f"战争 {war_id} 引用未知世界")
            for side in ("attacker", "defender"):
                morale = float(dict(war.get("morale", {})).get(side, -1))
                exhaustion = float(dict(war.get("exhaustion", {})).get(side, -1))
                if not 0 <= morale <= 150 or not 0 <= exhaustion <= 100:
                    errors.append(f"战争 {war_id} 的士气或厌战度非法")
                for entity_id in war.get("roster", {}).get(side, []):
                    if state.entities.get(str(entity_id), IDENTITY) is None:
                        errors.append(f"战争 {war_id} 名册引用未知人物")
        return errors

    return validate


def war_view(
    state: WorldState, definitions: GameDefinitions, entity_id: str | None = None,
) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    world_id = str(state.entities.require(actor_id, LOCATION)["world_id"])
    preferences = state.entities.require(actor_id, PREFERENCES)
    debug = bool(preferences.get("debug_world_news"))
    wars = []
    for war_id in state.entities.with_component(WAR_PROFILE):
        war = state.entities.require(war_id, WAR_PROFILE)
        if not debug and war.get("world_id") != world_id:
            continue
        public = dict(war)
        public["id"] = war_id
        public["attacker_name"] = _power_name(
            state, definitions, str(war["kind"]), str(war["attacker_id"])
        )
        public["defender_name"] = _power_name(
            state, definitions, str(war["kind"]), str(war["defender_id"])
        )
        public["player_side"] = _actor_side(state, actor_id, war)
        public["player_controls"] = bool(
            public["player_side"]
            and (own_id := _actor_power_id(state, actor_id, str(war["kind"])))
            and own_id == war.get(f"{public['player_side']}_id")
            and _has_voice(state, definitions, actor_id, str(war["kind"]), own_id)
        )
        public["can_participate"] = bool(
            public["player_side"] and war.get("status") == "active"
            and bool(state.entities.require(actor_id, LIFE).get("alive"))
            and not state.relations.find(target_id=actor_id, kind="combat_prisoner")
        )
        public["can_negotiate"] = bool(
            public["player_controls"]
            and (int(war.get("battles", 0)) >= 2 or war.get("status") == "peace_ready")
        )
        public["power_summary"] = {
            side: _side_power(state, definitions, war, side)
            for side in ("attacker", "defender")
        }
        public["coalitions"] = {
            side: [
                {
                    "id": power_id,
                    "name": _power_name(
                        state, definitions, str(war["kind"]), str(power_id)
                    ),
                }
                for power_id in war.get("coalitions", {}).get(side, [])
            ]
            for side in ("attacker", "defender")
        }
        public["roster"] = {
            side: [
                {
                    **character_view(state, member_id),
                    "combat_power": combat_snapshot(
                        state, definitions, member_id
                    )["power"],
                    "owner_id": war.get("roster_owner", {}).get(member_id),
                    "escaped": member_id in set(war.get("escaped", {}).get(side, [])),
                }
                for member_id in war.get("roster", {}).get(side, [])
                if state.entities.exists(member_id)
            ]
            for side in ("attacker", "defender")
        }
        wars.append(public)
    wars.sort(key=lambda row: (row.get("start_unit", 0), row["id"]), reverse=True)
    bounties = state.entities.require(actor_id, BOUNTY_STATE)
    authorities = _bounty_authorities(state, definitions, actor_id)
    return {
        "wars": wars[:20],
        "active_count": sum(
            row.get("status") in {"active", "peace_ready"} for row in wars
        ),
        "bounties": [dict(row) for row in bounties.get("orders", [])],
        "bounty_authorities": authorities,
        "can_issue_bounty": bool(authorities),
    }


def register_war_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(WarAction, _war_action_handler(definitions))
    bus.register(WarPeace, _war_peace_handler(definitions))
    bus.register(IssueBounty, _issue_bounty_handler(definitions))
    bus.event_bus.register("character.created", _on_character_created)
    bus.event_bus.register(
        "governance.diplomacy.voted", _on_diplomacy_voted(definitions)
    )
    bus.event_bus.register("character.died", _on_character_died)
    bus.event_bus.register("core.action.completed", _on_action_completed(definitions))

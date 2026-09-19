from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, ClassVar

from .actions import resume_action
from .character import IDENTITY, LIFE
from .cultivation import CULTIVATION
from .definitions import GameDefinitions
from .factions import FACTION_GOVERNANCE, FACTION_PROFILE, MEMBERSHIP
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


CELESTIAL_COURT = "celestial.court"


@dataclass(frozen=True, slots=True)
class ResolveHeavenlyElection:
    actor_id: str
    method: str = "none"
    pledge_id: str = ""
    allow_during_court_election: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class HeavenlyCourtAction:
    actor_id: str
    action: str
    target_id: str = ""
    enact: bool | None = None
    influence_spend: int = 0


def _config(definitions: GameDefinitions) -> dict[str, Any]:
    return dict(definitions.systems["heavenly_court"])


def _court_entity(state: WorldState) -> str | None:
    entities = state.entities.with_component(CELESTIAL_COURT)
    return entities[0] if entities else None


def _court(state: WorldState) -> dict[str, Any] | None:
    entity_id = _court_entity(state)
    return state.entities.require(entity_id, CELESTIAL_COURT) if entity_id else None


def _put_court(state: WorldState, court: dict[str, Any]) -> None:
    entity_id = _court_entity(state)
    if entity_id is None:
        entity_id = state.entities.create("celestial_court")
    state.entities.put(entity_id, CELESTIAL_COURT, court)


def _grade_for_realm(realm_index: int) -> int:
    return 2 if realm_index >= 11 else 4 if realm_index >= 10 else 6


def _celestial_factions(state: WorldState) -> list[tuple[str, dict[str, Any]]]:
    return sorted(
        (
            (entity_id, state.entities.require(entity_id, FACTION_PROFILE))
            for entity_id in state.entities.with_component(FACTION_PROFILE)
            if state.entities.require(entity_id, FACTION_PROFILE).get("world_id") == "celestial"
            and bool(state.entities.require(entity_id, FACTION_PROFILE).get("active", True))
        ),
        key=lambda row: str(row[1].get("external_id") or row[0]),
    )


def _new_court(state: WorldState, definitions: GameDefinitions) -> dict[str, Any]:
    config = _config(definitions)
    rng = random.Random(f"{state.seed}:heavenly_court:v1")
    factions = _celestial_factions(state)
    officials: dict[str, dict[str, Any]] = {}
    faction_members: dict[str, list[str]] = {}
    for edge in state.relations.find(kind=MEMBERSHIP):
        if state.entities.get(edge.source_id, IDENTITY) is None:
            continue
        location = state.entities.get(edge.source_id, LOCATION) or {}
        life = state.entities.get(edge.source_id, LIFE) or {}
        if location.get("world_id") != "celestial" or not bool(life.get("alive")):
            continue
        cultivation = state.entities.get(edge.source_id, CULTIVATION) or {}
        try:
            realm_index = definitions.realm_index(str(cultivation.get("realm_id", "")))
        except KeyError:
            continue
        identity = state.entities.require(edge.source_id, IDENTITY)
        officials[edge.source_id] = {
            "id": edge.source_id,
            "name": str(identity["name"]),
            "grade": _grade_for_realm(realm_index),
            "faction_id": edge.target_id,
            "support": 50.0,
            "source": "npc",
        }
        faction_members.setdefault(edge.target_id, []).append(edge.source_id)

    prefixes = ("玄都", "云海", "青帝", "天河", "万象", "九元", "紫极")
    suffixes = ("宗", "阁", "宫", "院", "门", "府", "观", "殿", "洞")
    names = ("沈观澜", "陆星河", "闻天羽", "顾元真", "苏玄微", "江法明", "凌清风", "白云生")
    seats: list[dict[str, Any]] = []
    for index in range(int(config["seat_count"])):
        if index < len(factions):
            faction_id, profile = factions[index]
            members = faction_members.get(faction_id, [])
            representative_id = members[0] if members else f"court_delegate_{index + 1:02d}"
            name = str(profile["name"])
            influence = rng.randint(92, 138)
            sect_id = faction_id
        else:
            representative_id = f"court_delegate_{index + 1:02d}"
            sect_id = f"court_virtual_sect_{index + 1:02d}"
            name = f"{rng.choice(prefixes)}{rng.choice(suffixes)}"
            influence = rng.randint(22, 105)
        if representative_id not in officials:
            officials[representative_id] = {
                "id": representative_id,
                "name": f"{rng.choice(names)}{index + 1}",
                "grade": rng.randint(3, 8),
                "faction_id": sect_id,
                "support": rng.randint(38, 68),
                "source": "court_pool",
            }
        seats.append({
            "id": f"seat_{index + 1:02d}",
            "sect_id": sect_id,
            "name": name,
            "influence": influence,
            "size": "large" if influence >= 91 else "medium" if influence >= 51 else "small",
            "representative_id": representative_id,
        })
    return {
        "unit": 0,
        "time_progress": 0,
        "authority": float(config["initial_authority"]),
        "treasury": float(config["initial_treasury"]),
        "equipment": 0.0,
        "player_grade": int(config["player_initial_grade"]),
        "player_merit": 0,
        "player_support": 50.0,
        "offices": {row["id"]: None for row in config["offices"]},
        "laws": {row["id"]: False for row in config["laws"]},
        "active_decrees": [],
        "wanted_ids": [],
        "officials": officials,
        "seats": seats,
        "election_queue": [],
        "open_election": None,
        "pledges": [],
        "last_vote": None,
    }


def reconcile_celestial_state(
    state: WorldState, definitions: GameDefinitions, *, force: bool = False,
) -> None:
    state.module_versions["celestial"] = 1
    actor_id = state.controlled_entity_id
    if actor_id is None:
        return
    location = state.entities.get(actor_id, LOCATION) or {}
    court = _court(state)
    if court is None and (force or location.get("world_id") == "celestial"):
        court = _new_court(state, definitions)
        _put_court(state, court)
    if court is not None:
        _sync_player(state, definitions, court)
        _put_court(state, court)


def _player_faction(state: WorldState, actor_id: str) -> str | None:
    edges = state.relations.find(source_id=actor_id, kind=MEMBERSHIP)
    return edges[0].target_id if edges else None


def _player_representative(state: WorldState, actor_id: str, faction_id: str | None) -> bool:
    if not faction_id:
        return False
    governance = state.entities.get(faction_id, FACTION_GOVERNANCE) or {}
    if governance.get("controller_id") == actor_id:
        return True
    members = [edge.source_id for edge in state.relations.find(target_id=faction_id, kind=MEMBERSHIP)]
    living_others = [member for member in members if member != actor_id and bool((state.entities.get(member, LIFE) or {}).get("alive"))]
    return not living_others


def _sync_player(state: WorldState, definitions: GameDefinitions, court: dict[str, Any]) -> None:
    actor_id = state.controlled_entity_id
    if actor_id is None:
        return
    identity = state.entities.require(actor_id, IDENTITY)
    faction_id = _player_faction(state, actor_id)
    court["officials"][actor_id] = {
        "id": actor_id,
        "name": str(identity["name"]),
        "grade": int(court["player_grade"]),
        "faction_id": faction_id,
        "support": float(court["player_support"]),
        "source": "player",
    }
    if _player_representative(state, actor_id, faction_id):
        seat = next((row for row in court["seats"] if row["sect_id"] == faction_id), None)
        if seat:
            seat["representative_id"] = actor_id


def _player_controls(state: WorldState, court: dict[str, Any]) -> int:
    actor_id = state.controlled_entity_id
    return sum(1 for row in court["offices"].values() if row and row.get("holder_id") == actor_id)


def _open_election(context: SimulationContext, definitions: GameDefinitions, court: dict[str, Any], office_id: str) -> None:
    config = _config(definitions)
    _sync_player(context.state, definitions, court)
    court["treasury"] = max(0.0, float(court["treasury"]) - float(config.get("election_treasury_cost", 0)))
    eligible = [row for row in court["officials"].values() if int(row.get("grade", 9)) <= 4]
    actor_id = context.state.controlled_entity_id
    incumbent = court["offices"].get(office_id)
    if (
        incumbent
        and incumbent.get("holder_id") == actor_id
        and float(court["player_support"]) < 25
    ):
        for key, row in court["offices"].items():
            if row and row.get("holder_id") == actor_id:
                court["offices"][key] = None
        eligible = [row for row in eligible if row["id"] != actor_id]
    player = next((row for row in eligible if row["id"] == actor_id), None)
    others = [row for row in eligible if row["id"] != actor_id]
    count = min(context.rng.randint(4, 7), len(others)) if others else 0
    candidates = context.rng.sample(others, count) if count else []
    if player:
        candidates.append(player)
    if not candidates:
        return
    court["open_election"] = {
        "office_id": office_id,
        "round": 1,
        "candidates": [row["id"] for row in candidates],
        "opened_unit": int(court["unit"]),
    }
    if player:
        context.halt_time("天庭七曜选举待决")
    else:
        for _ in range(50):
            if _resolve_election(context, definitions, court, "none", ""):
                break


def _resolve_election(context: SimulationContext, definitions: GameDefinitions, court: dict[str, Any], method: str, pledge_id: str) -> bool:
    election = court.get("open_election")
    if not isinstance(election, dict):
        raise ValueError("当前没有待处理的七曜选举")
    actor_id = str(context.state.controlled_entity_id)
    candidates = list(map(str, election["candidates"]))
    bonus = 0.0
    if actor_id in candidates:
        if method == "relationship":
            from .relations import relationship_affinity

            affinities = [
                relationship_affinity(context.state, entity_id, actor_id)
                for entity_id in context.state.entities.with_component(IDENTITY)
                if entity_id != actor_id
                and (context.state.entities.get(entity_id, LOCATION) or {}).get("world_id") == "celestial"
                and bool((context.state.entities.get(entity_id, LIFE) or {}).get("alive"))
            ]
            bonus = 0.25 + max([0.0, *affinities]) / 180
        elif method == "faction":
            faction_id = _player_faction(context.state, actor_id)
            seat = next((row for row in court["seats"] if row["sect_id"] == faction_id), None)
            if not seat or seat.get("representative_id") != actor_id:
                raise ValueError("你并非宗门的天庭代表，无法调动本宗选票")
            spend = min(15, int(seat["influence"]))
            seat["influence"] -= spend
            bonus = 0.32 + spend / 50
        elif method in {"promise_decree", "promise_law"}:
            table = "decrees" if method == "promise_decree" else "laws"
            if pledge_id not in {row["id"] for row in _config(definitions)[table]}:
                raise ValueError("承诺的决议或天条不存在")
            court["pledges"].append({
                "kind": "decree" if method == "promise_decree" else "law",
                "id": pledge_id,
                "deadline_unit": int(court["unit"]) + 2,
            })
            bonus = 0.62
        elif method != "none":
            raise ValueError("未知竞选方式")
    votes = {candidate: 0 for candidate in candidates}
    for seat in court["seats"]:
        weights: list[float] = []
        for candidate in candidates:
            official = court["officials"][candidate]
            score = 1 + float(official.get("support", 50)) / 100
            if candidate == actor_id:
                score += bonus + float(court["player_support"]) / 180
                if seat.get("representative_id") == actor_id:
                    score += 1.3
            if official.get("faction_id") == seat.get("sect_id"):
                score += 0.7
            weights.append(max(0.05, score))
        votes[context.rng.choices(candidates, weights=weights, k=1)[0]] += 1
    winner, winner_votes = max(votes.items(), key=lambda row: (row[1], row[0]))
    election["votes"] = votes
    if winner_votes < math.ceil(int(_config(definitions)["seat_count"]) / 4):
        election["round"] = int(election["round"]) + 1
        court["open_election"] = election
        return False
    official = court["officials"][winner]
    office_id = str(election["office_id"])
    court["offices"][office_id] = {
        "holder_id": winner,
        "holder_name": official["name"],
        "start_unit": int(court["unit"]),
        "end_unit": int(court["unit"]) + int(_config(definitions)["term_units"]),
        "votes": winner_votes,
    }
    court["open_election"] = None
    context.emit(
        "celestial.court.election.resolved",
        source="celestial",
        scope=EventScope("world", "celestial"),
        payload={"office_id": office_id, "winner_id": winner, "votes": votes},
    )
    return True


def _advance_unit(context: SimulationContext, definitions: GameDefinitions, court: dict[str, Any]) -> None:
    config = _config(definitions)
    court["unit"] = int(court["unit"]) + 1
    unit = int(court["unit"])
    laws = court["laws"]
    court["active_decrees"] = [row for row in court["active_decrees"] if int(row["expires_unit"]) >= unit]
    multiplier = 1.0
    for decree in court["active_decrees"]:
        multiplier *= float(decree.get("income_multiplier", 1))
    if laws.get("wide_domain"):
        multiplier *= .95
        court["authority"] += 5
    if laws.get("traveling_palace"):
        multiplier *= 1.05
        court["authority"] = max(0.0, float(court["authority"]) - 5)
    for law_id in ("direct_appointment_law", "recommendation_law"):
        if laws.get(law_id):
            court["authority"] += 5
    court["treasury"] += round(float(config["base_treasury_income"]) * multiplier, 2)
    for seat in court["seats"]:
        delta = 0
        if laws.get("celestial_sects"):
            delta += -5 if seat["size"] == "large" else 5
        if laws.get("direct_appointment_law"):
            delta -= 5
        if laws.get("recommendation_law"):
            delta += 5
        seat["influence"] = max(0, int(seat["influence"]) + delta)
    broken = [row for row in court["pledges"] if int(row["deadline_unit"]) < unit]
    if broken:
        court["player_support"] = max(0.0, float(court["player_support"]) - 15 * len(broken))
        court["pledges"] = [row for row in court["pledges"] if row not in broken]
    office_id = str(config["offices"][(unit - 1) % len(config["offices"])]["id"])
    _open_election(context, definitions, court, office_id)
    context.emit(
        "celestial.court.unit.advanced",
        source="celestial",
        scope=EventScope("world", "celestial"),
        payload={"unit": unit, "office_id": office_id},
    )


def _on_time_advanced(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = context.state.controlled_entity_id
        if actor_id is None or (context.state.entities.get(actor_id, LOCATION) or {}).get("world_id") != "celestial":
            return
        reconcile_celestial_state(context.state, definitions)
        court = _court(context.state)
        assert court is not None
        elapsed = int(event.payload["to_year"]) - int(event.payload["from_year"])
        realm_id = str(context.state.entities.require(actor_id, CULTIVATION)["realm_id"])
        court["time_progress"] = int(court.get("time_progress", 0)) + elapsed
        unit_years = definitions.action_time(realm_id, 1)
        while int(court["time_progress"]) >= unit_years and not context.time_halted:
            court["time_progress"] -= unit_years
            _advance_unit(context, definitions, court)
        _put_court(context.state, court)
    return handler


def _on_enter_celestial(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        if event.payload.get("destination_world_id") == "celestial":
            reconcile_celestial_state(context.state, definitions)
    return handler


def _resolve_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ResolveHeavenlyElection):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能处理当前角色的选举")
        if (context.state.entities.require(command.actor_id, LOCATION)).get("world_id") != "celestial":
            raise ValueError("只有身处仙界才能处理天庭选举")
        court = _court(context.state)
        if court is None:
            raise ValueError("天庭尚未初始化")
        success = _resolve_election(context, definitions, court, command.method, command.pledge_id)
        if success:
            realm_id = str(
                context.state.entities.require(command.actor_id, CULTIVATION)["realm_id"]
            )
            unit_years = definitions.action_time(realm_id, 1)
            while (
                int(court.get("time_progress", 0)) >= unit_years
                and court.get("open_election") is None
            ):
                court["time_progress"] -= unit_years
                _advance_unit(context, definitions, court)
        _put_court(context.state, court)
        if success and court.get("open_election") is None:
            resume_action(context, command.actor_id)
    return handler


def _spend_influence(state: WorldState, court: dict[str, Any], requested: int) -> int:
    spend = max(0, min(15, int(requested)))
    if not spend:
        return 0
    actor_id = str(state.controlled_entity_id)
    faction_id = _player_faction(state, actor_id)
    seat = next((row for row in court["seats"] if row["sect_id"] == faction_id), None)
    if not seat or seat.get("representative_id") != actor_id:
        raise ValueError("只有本宗天庭代表可以调动宗门影响力")
    if int(seat["influence"]) < spend:
        raise ValueError("本宗影响力不足")
    seat["influence"] -= spend
    return spend


def _honor(court: dict[str, Any], kind: str, policy_id: str) -> None:
    honored = [row for row in court["pledges"] if row["kind"] == kind and row["id"] == policy_id]
    if honored:
        court["player_support"] = min(100.0, float(court["player_support"]) + 5 * len(honored))
        court["pledges"] = [row for row in court["pledges"] if row not in honored]


def _court_action_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, HeavenlyCourtAction):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能处理当前角色的天庭政务")
        if context.state.entities.require(command.actor_id, LOCATION).get("world_id") != "celestial":
            raise ValueError("只有身处仙界才能处理天庭政务")
        court = _court(context.state)
        if court is None:
            raise ValueError("天庭尚未初始化")
        if court.get("open_election"):
            raise ValueError("请先完成当前七曜选举")
        config = _config(definitions)
        result = ""
        if command.action == "examination":
            grade = int(court["player_grade"])
            if grade <= 1:
                raise ValueError("你已位列一品天官")
            target = grade - 1
            needed = int(config["grade_merit_thresholds"][str(target)])
            if int(court["player_merit"]) < needed:
                raise ValueError(f"晋升{target}品需要 {needed} 功德")
            realm = definitions.realm_index(str(context.state.entities.require(command.actor_id, CULTIVATION)["realm_id"]))
            if context.rng.random() < min(.95, .72 + max(0, realm - 9) * .06):
                court["player_grade"] = target
                result = "promoted"
            else:
                result = "failed"
        elif command.action.startswith("decree:"):
            decree_id = command.action.split(":", 1)[1]
            decree = next((row for row in config["decrees"] if row["id"] == decree_id), None)
            if decree is None:
                raise ValueError("未知天庭决议")
            if _player_controls(context.state, court) < 1:
                raise ValueError("只有七曜星君可以推行决议")
            laws = court["laws"]
            if decree.get("requires_law") and not laws.get(decree["requires_law"]):
                raise ValueError("当前天条尚未授予该决议权限")
            if decree.get("forbidden_law") and laws.get(decree["forbidden_law"]):
                raise ValueError("当前天条禁止这项决议")
            slots = int(config["base_decree_slots"]) + int(bool(laws.get("assistant_officials")))
            if len(court["active_decrees"]) >= slots:
                raise ValueError("当前决议槽位已满")
            cost = float(decree.get("authority_cost", config["decree_authority_cost"]))
            if float(court["authority"]) < cost:
                raise ValueError("天庭权威不足")
            spent = _spend_influence(context.state, court, command.influence_spend)
            multiplier = (1.5 if laws.get("official_system") else 1.0) * (1 + spent / 50)
            treasury_delta = float(decree.get("immediate_treasury", 0)) * multiplier - float(config["policy_treasury_cost"])
            if float(court["treasury"]) + treasury_delta < 0:
                raise ValueError("天庭府库不足以执行该决议")
            target = None
            if decree_id in {"direct_appointment", "wanted"}:
                if command.target_id == command.actor_id:
                    raise ValueError("必须指定一名仙界存活 NPC")
                target = context.state.entities.get(command.target_id, IDENTITY)
                life = context.state.entities.get(command.target_id, LIFE) or {}
                location = context.state.entities.get(command.target_id, LOCATION) or {}
                if target is None or not bool(life.get("alive")) or location.get("world_id") != "celestial":
                    raise ValueError("必须指定一名仙界存活 NPC")
            if decree_id == "protect" and command.target_id not in court["wanted_ids"]:
                raise ValueError("该人并不在天庭通缉名单上")
            court["authority"] -= cost
            court["treasury"] += treasury_delta
            court["equipment"] += float(decree.get("immediate_equipment", 0)) * multiplier
            court["player_support"] = max(0.0, min(100.0, float(court["player_support"]) + float(decree.get("support", 0)) * multiplier))
            if decree_id == "direct_appointment" and target:
                court["officials"][command.target_id] = {"id": command.target_id, "name": target["name"], "grade": 9, "faction_id": _player_faction(context.state, command.target_id), "support": 50, "source": "npc"}
            elif decree_id == "wanted" and command.target_id not in court["wanted_ids"]:
                court["wanted_ids"].append(command.target_id)
            elif decree_id == "protect":
                court["wanted_ids"].remove(command.target_id)
            elif decree_id == "recommend_official":
                candidates = [row for row in court["officials"].values() if row["id"] != command.actor_id and int(row.get("grade", 9)) >= 7]
                if candidates:
                    context.rng.choice(candidates)["grade"] = 9
            court["active_decrees"].append({"id": decree_id, "name": decree["name"], "expires_unit": int(court["unit"]) + int(config["decree_duration_units"]), "income_multiplier": decree.get("income_multiplier", 1)})
            _honor(court, "decree", decree_id)
            result = "decree_enacted"
        elif command.action.startswith("law:"):
            law_id = command.action.split(":", 1)[1]
            if law_id not in {row["id"] for row in config["laws"]}:
                raise ValueError("未知天条")
            if _player_controls(context.state, court) < 1:
                raise ValueError("只有七曜星君可以发起天条表决")
            holders = [str(row["holder_id"]) for row in court["offices"].values() if row]
            if len(holders) < len(config["offices"]):
                raise ValueError("七曜尚未全部就位，无法进行天条表决")
            if float(court["treasury"]) < float(config["policy_treasury_cost"]):
                raise ValueError("天庭府库不足以召开天条表决")
            court["treasury"] -= float(config["policy_treasury_cost"])
            spent = _spend_influence(context.state, court, command.influence_spend)
            desired = not bool(court["laws"][law_id]) if command.enact is None else bool(command.enact)
            votes = [holder == command.actor_id or context.rng.random() < .48 + float(court["player_support"]) / 500 + min(.35, spent * .02) for holder in holders]
            passed = _player_controls(context.state, court) >= 4 or sum(votes) >= 4
            court["last_vote"] = {"law_id": law_id, "enact": desired, "yes": sum(votes), "no": len(votes) - sum(votes), "passed": passed}
            if passed:
                court["laws"][law_id] = desired
                _honor(court, "law", law_id)
            result = "law_passed" if passed else "law_rejected"
        else:
            raise ValueError("未知天庭政务")
        _sync_player(context.state, definitions, court)
        _put_court(context.state, court)
        context.emit("celestial.court.action.resolved", source="celestial", scope=EventScope("world", "celestial"), payload={"actor_id": command.actor_id, "action": command.action, "result": result})
    return handler


def _election_guard(state: WorldState, command: object) -> None:
    court = _court(state)
    if court and court.get("open_election") and not bool(getattr(type(command), "allow_during_court_election", False)):
        raise ValueError("请先完成当前七曜选举")


def court_law_active(state: WorldState, law_id: str) -> bool:
    court = _court(state)
    return bool(court and court.get("laws", {}).get(law_id))


def register_celestial_story_effects(registry: Any) -> None:
    from .story import EffectOutcome, StoryEffectRegistry

    if not isinstance(registry, StoryEffectRegistry):
        raise TypeError("剧情效果注册器类型错误")

    def add_merit(context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any]) -> EffectOutcome:
        del pending
        if context.state.entities.require(actor_id, LOCATION).get("world_id") != "celestial":
            return EffectOutcome(None, "天庭功德只在仙界记档。")
        court = _court(context.state)
        if court is None:
            reconcile_celestial_state(context.state, registry.definitions)
            court = _court(context.state)
        assert court is not None
        amount = int(StoryEffectRegistry._value(context, effect))
        court["player_merit"] = max(0, int(court["player_merit"]) + amount)
        _put_court(context.state, court)
        return EffectOutcome(None, f"天庭功德 {amount:+d}。")

    registry.register("add_court_merit", add_merit)


def celestial_invariants(definitions: GameDefinitions):
    def validate(state: WorldState) -> list[str]:
        errors: list[str] = []
        entities = state.entities.with_component(CELESTIAL_COURT)
        if len(entities) > 1:
            errors.append("存在多个天庭权威实体")
        if not entities:
            return errors
        court = state.entities.require(entities[0], CELESTIAL_COURT)
        config = _config(definitions)
        if len(court.get("seats", [])) != int(config["seat_count"]):
            errors.append("天庭议席数量错误")
        seat_ids = [str(row.get("id", "")) for row in court.get("seats", [])]
        if len(seat_ids) != len(set(seat_ids)) or any(not value for value in seat_ids):
            errors.append("天庭议席ID重复或为空")
        if set(court.get("offices", {})) != {row["id"] for row in config["offices"]}:
            errors.append("七曜职位集合错误")
        if set(court.get("laws", {})) != {row["id"] for row in config["laws"]}:
            errors.append("天条集合错误")
        if not 1 <= int(court.get("player_grade", 0)) <= 9:
            errors.append("玩家天官品级非法")
        if not 0 <= float(court.get("player_support", -1)) <= 100:
            errors.append("玩家天庭支持度非法")
        if min(float(court.get("authority", -1)), float(court.get("treasury", -1)), float(court.get("equipment", -1))) < 0:
            errors.append("天庭资源不能为负")
        election = court.get("open_election")
        if election and (election.get("office_id") not in court["offices"] or any(candidate not in court["officials"] for candidate in election.get("candidates", []))):
            errors.append("待决选举引用无效")
        for office_id, holder in court.get("offices", {}).items():
            if holder and str(holder.get("holder_id", "")) not in court.get("officials", {}):
                errors.append(f"七曜职位 {office_id} 引用未知天官")
        decree_ids = {row["id"] for row in config["decrees"]}
        if any(row.get("id") not in decree_ids for row in court.get("active_decrees", [])):
            errors.append("生效决议引用未知定义")
        return errors
    return validate


def celestial_view(state: WorldState, definitions: GameDefinitions) -> dict[str, Any]:
    actor_id = state.controlled_entity_id
    if actor_id is None or state.entities.require(actor_id, LOCATION).get("world_id") != "celestial":
        return {"visible": False}
    court = _court(state)
    if court is None:
        return {"visible": True, "initialized": False}
    config = _config(definitions)
    election = court.get("open_election")
    public_election = None
    if election:
        office_defs = {row["id"]: row for row in config["offices"]}
        public_election = {**election, "office_name": office_defs[election["office_id"]]["name"], "candidates": [court["officials"][candidate] for candidate in election["candidates"]], "player_candidate": actor_id in election["candidates"]}
    controls = _player_controls(state, court)
    laws = [dict(row, active=bool(court["laws"].get(row["id"]))) for row in config["laws"]]
    decrees = []
    for row in config["decrees"]:
        enabled, reason = controls > 0, "" if controls > 0 else "需先当选七曜星君"
        if row.get("requires_law") and not court["laws"].get(row["requires_law"]):
            enabled, reason = False, "缺少前置天条"
        if row.get("forbidden_law") and court["laws"].get(row["forbidden_law"]):
            enabled, reason = False, "被当前天条禁止"
        decrees.append(dict(row, enabled=enabled, disabled_reason=reason))
    targets = []
    if actor_id in court["wanted_ids"]:
        targets.append({
            "id": actor_id,
            "name": state.entities.require(actor_id, IDENTITY)["name"],
            "wanted": True,
            "self": True,
        })
    for entity_id in state.entities.with_component(IDENTITY):
        if entity_id == actor_id:
            continue
        if (state.entities.get(entity_id, LOCATION) or {}).get("world_id") == "celestial" and bool((state.entities.get(entity_id, LIFE) or {}).get("alive")):
            targets.append({"id": entity_id, "name": state.entities.require(entity_id, IDENTITY)["name"], "wanted": entity_id in court["wanted_ids"]})
    faction_id = _player_faction(state, actor_id)
    seat = next((row for row in court["seats"] if row["sect_id"] == faction_id), None)
    seat_sizes = {
        size: sum(1 for row in court["seats"] if row.get("size") == size)
        for size in ("large", "medium", "small")
    }
    return {
        "visible": True, "initialized": True, "unit": int(court["unit"]),
        "authority": round(float(court["authority"]), 2), "treasury": round(float(court["treasury"]), 2), "equipment": round(float(court["equipment"]), 2),
        "player_grade": int(court["player_grade"]), "player_merit": int(court["player_merit"]), "player_support": round(float(court["player_support"]), 1),
        "player_controls": controls, "player_is_representative": bool(seat and seat.get("representative_id") == actor_id), "player_seat_influence": int(seat["influence"]) if seat else 0,
        "seat_count": len(court["seats"]), "seat_sizes": seat_sizes,
        "offices": [dict(row, holder=court["offices"].get(row["id"])) for row in config["offices"]],
        "laws": laws, "decrees": decrees, "active_decrees": list(court["active_decrees"]), "wanted_ids": list(court["wanted_ids"]), "target_npcs": targets,
        "election": public_election, "pledges": list(court["pledges"]), "last_vote": court.get("last_vote"),
        "decree_slots": int(config["base_decree_slots"]) + int(bool(court["laws"].get("assistant_officials"))),
        "next_grade_merit": int(config["grade_merit_thresholds"].get(str(int(court["player_grade"]) - 1), 0)) if int(court["player_grade"]) > 1 else None,
    }


def register_celestial_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(ResolveHeavenlyElection, _resolve_handler(definitions))
    bus.register(HeavenlyCourtAction, _court_action_handler(definitions))
    bus.add_guard(_election_guard)
    bus.event_bus.register("core.time.advanced", _on_time_advanced(definitions))
    bus.event_bus.register("world.permanent_transition.committed", _on_enter_celestial(definitions))

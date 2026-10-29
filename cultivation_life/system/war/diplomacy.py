from __future__ import annotations
from .creation import create, register

from ...race_diplomacy import relations_for
from typing import Any
from ...models import GameState
import random
from .dependencies import WarDiplomacyDependencies
from .policy import system_war_allowed, strategic_conflicts


def _allied_powers(deps: WarDiplomacyDependencies, game: GameState, war: dict[str, Any], side: str) -> list[dict[str, Any]]:
    relations = relations_for(game) if war["kind"] == "race" else game.sect_relations
    own = set(deps._coalition_ids(war, side))
    enemy = set(deps._coalition_ids(war, "defender" if side == "attacker" else "attacker"))
    candidates: dict[str, dict[str, Any]] = {}
    for caller in own:
        for key, relation in relations.items():
            if relation.get("status") not in {"alliance", "vassal"}:
                continue
            first, second = key.split("|") if "|" in key else key.split(":")
            if caller not in {first, second}:
                continue
            candidate = second if caller == first else first
            if candidate in own or candidate in enemy or not deps._power_exists_in_world(game, war["kind"], candidate, war["world"]):
                continue
            from .occupancy import busy, organization
            org = organization(game,candidate) if war['kind']=='sect' else None
            if org and busy(game,org,managed_only=True):
                continue
            from ...world_state import race_pair
            if war['kind']=='sect' and any(game.player.age < game.sect_relations.get(race_pair(candidate,e),{}).get('truce_until_age',0) for e in enemy):
                continue
            if not war.get('strategic_war_id') and any(strategic_conflicts(game,candidate,e) for e in enemy):
                continue
            base = float(deps._war_rules().get("ally_call_base_chance", 0.68))
            chance = base + max(-0.18, min(0.18, float(relation.get("affinity", 0)) / 400.0))
            own_power = deps._war_total_power(game, war, side)
            enemy_power = deps._war_total_power(game, war, "defender" if side == "attacker" else "attacker")
            if side == "defender":
                chance += 0.06
            if enemy_power > own_power * 1.5:
                chance -= 0.12
            elif own_power > enemy_power * 1.35:
                chance += 0.05
            if relation.get("status") == "vassal":
                chance += 0.25 if relation.get("overlord") == caller else 0.08
            candidates[candidate] = {"id": candidate, "caller_id": caller, "chance": max(0.10, min(0.98, chance))}
    return list(candidates.values())


def _add_war_participant(deps: WarDiplomacyDependencies, game: GameState, war: dict[str, Any], side: str, power_id: str, caller_id: str) -> None:
    from ...world_state import race_pair
    enemy='defender' if side=='attacker' else 'attacker'
    if war['kind']=='sect' and any(game.player.age < game.sect_relations.get(race_pair(power_id,e),{}).get('truce_until_age',0) for e in deps._coalition_ids(war,enemy)):
        raise ValueError('仍受和约停战约束的宗门不能借盟军身份参战')
    if not war.get('strategic_war_id') and any(strategic_conflicts(game,power_id,e) for e in deps._coalition_ids(war,enemy)):
        raise ValueError('种族战争尚未收束，不能借独立盟军身份另开同案交锋')
    war["coalitions"][side].append({"id": power_id, "role": "ally", "joined_unit": game.diplomacy_unit, "called_by": caller_id})
    side_roster = war["roster"][side]
    total_cap = int(deps._war_rules().get("coalition_roster_cap", 48))
    ally_cap = int(deps._war_rules().get("ally_roster_cap", 12))
    for npc in deps._war_side_members(game, war["kind"], power_id, war["world"])[:ally_cap]:
        if len(side_roster) >= total_cap:
            break
        if npc.id not in side_roster:
            side_roster.append(npc.id)
            war["roster_owner"][npc.id] = power_id


def _call_war_allies(deps: WarDiplomacyDependencies, game: GameState, war: dict[str, Any], side: str, rng: random.Random,
                     *, ally_id: str = "", limit: int | None = None) -> list[str]:
    deps._ensure_war_shape(game, war)
    outcomes: list[str] = []
    cooldown = int(deps._war_rules().get("ally_call_cooldown_units", 3))
    for row in deps._allied_powers(game, war, side):
        if ally_id and row["id"] != ally_id:
            continue
        call_key = f"{side}:{row['id']}"
        prior = war["called_allies"].get(call_key)
        if prior and (prior.get("accepted") or game.diplomacy_unit - int(prior.get("unit", 0)) < cooldown):
            continue
        accepted = rng.random() < row["chance"]
        result = {
            "id": row["id"], "caller_id": row["caller_id"], "side": side, "accepted": accepted,
            "unit": game.diplomacy_unit, "chance": round(row["chance"], 3),
        }
        war["called_allies"][call_key] = result
        war["call_log"].append(result)
        caller_name = deps._war_side_name(game, war["kind"], row["caller_id"])
        ally_name = deps._war_side_name(game, war["kind"], row["id"])
        if accepted:
            deps._add_war_participant(game, war, side, row["id"], row["caller_id"])
            text = f"{ally_name}接受{caller_name}的召集，加入{('进攻' if side == 'attacker' else '防御')}阵营。"
        else:
            text = f"{ally_name}拒绝了{caller_name}的参战请求。"
        outcomes.append(text)
        deps._append_war_log(game, war, "召集盟友", text)
        if limit is not None and len(outcomes) >= limit:
            break
    war["call_log"] = war["call_log"][-40:]
    return outcomes


def _player_war_side(deps: WarDiplomacyDependencies, game: GameState, war: dict[str, Any]) -> str | None:
    if game.player.world != war.get("world"):
        return None
    deps._ensure_war_shape(game, war)
    return player_side(deps, game, war)


def player_side(deps: WarDiplomacyDependencies, game: GameState, war: dict[str, Any]) -> str | None:
    """Read original membership/guest obligations without preparing faction state."""
    if game.player.world != war.get("world"):
        return None
    own_id = deps._war_player_identity(game, war)
    return deps._participant_side(war, own_id) or deps._intrigue_player_guest_side(game, war)


def _player_has_war_voice(deps: WarDiplomacyDependencies, game: GameState, war: dict[str, Any]) -> bool:
    side = deps._player_war_side(game, war)
    if not side:
        return False
    own_id = deps._war_player_identity(game, war)
    if own_id != war.get(f"{side}_id"):
        return False
    if game.family and own_id == game.family.id:
        return bool(game.family.founded_by_player or deps._has_family_voice(game))
    return deps._has_race_voice(game) if war["kind"] == "race" else deps._has_sect_voice(game)


def _start_war(deps: WarDiplomacyDependencies, game: GameState, kind: str, attacker: str, defender: str, *, initiated_by_player=False, prepare_supplies=True, strategic_war_id='') -> dict[str, Any]:
    if kind == 'race':
        raise ValueError('种族宣战须通过族议建立战略战争，不能直接生成种族军队')
    conflicts=strategic_conflicts(game,attacker,defender)
    authorization=next((row for row in conflicts if row['id']==strategic_war_id and row['status']=='mobilizing'
        and len(row['campaigns'])<2 and any(c['org']['id']==attacker and c['side']=='attacker' for c in row['commitments'])
        and any(c['org']['id']==defender and c['side']=='defender' for c in row['commitments'])),None)
    if (conflicts and not authorization) or (strategic_war_id and not authorization):
        raise ValueError('种族战争尚未收束，组织只能执行原案授权战役，不能另开独立交锋')
    from .occupancy import busy, organization
    if authorization and (prepare_supplies or any(
            not (org:=organization(game,identity)) or org.extinct or org.world!=authorization['world']
            or org.allegiance_race!=authorization[side] for side,identity in [('attacker',attacker),('defender',defender)])):
        raise ValueError('原种族战争承诺已失效，或未由日历部署入口建立战役')
    if any((org:=organization(game,identity)) and busy(game,org,managed_only=True) for identity in (attacker,defender)):
        raise ValueError('宗门仍在战略战役中，行军、交战与撤军结束前不能另开战役')
    if any(w.get('strategic_war_id') and w.get('status')=='withdrawing'
           and {w.get('attacker_id'),w.get('defender_id')}=={attacker,defender} for w in game.wars):
        raise ValueError('原战役仍在撤回，不能重开同一战场')
    current = deps._active_war(game, kind, attacker, defender)
    if current:
        return current
    if not initiated_by_player and not system_war_allowed(game, kind, attacker, defender):
        raise ValueError('系统势力只能在同层级界面之间发起战争')
    relation = deps._war_relation(game, kind, attacker, defender)
    if game.player.age < int(relation.get('truce_until_age',0)):
        raise ValueError(f"和约停战期尚余 {int(relation['truce_until_age'])-game.player.age} 年，不能另开战役")
    truce_until = max(int(relation.get("truce_until_unit", 0)), int(relation.get("war_truce_until_unit", 0)))
    if game.diplomacy_unit < truce_until:
        raise ValueError(f"系统停战期尚余 {truce_until - game.diplomacy_unit} 个行动单位，不能宣战")
    world = deps._war_world(game, kind, attacker)
    attacker_roster = [npc.id for npc in deps._war_side_members(game, kind, attacker, world)]
    defender_roster = [npc.id for npc in deps._war_side_members(game, kind, defender, world)]
    # DLC guest elders / family retainers / race guests are defensive
    # guarantees.  They enter the defending roster, never the attacker's
    # compulsory levy.
    defensive_guests = deps._intrigue_defensive_guest_ids(game, kind, defender, world)
    attacker_roster = [npc_id for npc_id in attacker_roster if npc_id not in defensive_guests]
    defender_roster.extend(npc_id for npc_id in defensive_guests if npc_id not in defender_roster)
    war = create(game, kind, world, attacker, defender, attacker_roster, defender_roster)
    war["player_side"] = deps._player_war_side(game, war)
    if authorization:
        war['strategic_war_id']=authorization['id']
    war["controller"] = "player" if deps._player_has_war_voice(game, war) else "ai"
    from .logistics import initialize
    if prepare_supplies:
        initialize(game, deps.maps, war)
    register(game, war, deps._append_war_log, deps._war_side_name)
    return war

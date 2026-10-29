"""One original war record for ordinary and explicitly authorized campaigns."""
import uuid
from ...models import HistoryRecord


def create(game, kind, world, attacker, defender, attacker_roster, defender_roster):
    war = {
        "id": f"war_{uuid.uuid4().hex[:12]}", "kind": kind, "world": world,
        "attacker_id": attacker, "defender_id": defender, "status": "active",
        "start_age": game.player.age, "start_unit": game.diplomacy_unit,
        "morale": {"attacker": 100.0, "defender": 100.0},
        "exhaustion": {"attacker": 0.0, "defender": 0.0},
        "war_score": 0.0, "battles": 0, "abstract_rounds": 0,
        "preliminary_resolved": False,
        "roster": {"attacker": attacker_roster, "defender": defender_roster},
        "roster_owner": {**{npc_id: attacker for npc_id in attacker_roster}, **{npc_id: defender for npc_id in defender_roster}},
        "coalitions": {
            "attacker": [{"id": attacker, "role": "leader", "joined_unit": game.diplomacy_unit, "called_by": None}],
            "defender": [{"id": defender, "role": "leader", "joined_unit": game.diplomacy_unit, "called_by": None}],
        },
        "called_allies": {}, "call_log": [], "peace_offer": None,
        "escaped": {"attacker": [], "defender": []}, "logs": [],
    }
    return war


def register(game, war, append_log, side_name):
    game.wars.append(war)
    append_log(game, war, "宣战", f"{side_name(game, war['kind'], war['attacker_id'])}向{side_name(game, war['kind'], war['defender_id'])}正式宣战。")
    game.history.append(HistoryRecord(
        "SYS_WAR_DECLARED", 1, game.player.age, "势力宣战", war["id"], "war_started",
        war["logs"][-1]["text"], {"war_id": war["id"], "kind": war["kind"], "sides": [war["attacker_id"], war["defender_id"]]},
        ["system", "war", "diplomacy", "world_news", f"world:{war['world']}"],
    ))

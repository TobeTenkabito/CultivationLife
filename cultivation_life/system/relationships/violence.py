"""Explicit relationships violence operations; callers own composition."""
from __future__ import annotations

from ...npc_custody import is_free
from ...relationship_records import find_person

from ...models import HistoryRecord
from ...rules import expected_combat_power
from ...runtime import decode_rng, encode_rng, now_iso
from .dependencies import RelationshipViolenceDependencies


def relationship_violence(deps: RelationshipViolenceDependencies, game_id, kind, target_id, *, capture=False):
    game = deps._load(game_id)
    player = game.player
    if not player.alive or game.pending_event or game.active_trial or player.imprisonment:
        raise ValueError("请先结束当前事件或战斗")
    deps.assert_buddhist_operation_allowed(game_id, "relationship-violence")
    if capture and (kind != 'npc' or player.path != 'demonic'):
        raise ValueError("生擒修士须修习魔道；亲近之人须走关系生擒流程")
    stranger = None
    if kind == 'npc':
        stranger = deps._find_npc(game, target_id) or deps._promote_cached_npc(game, target_id, '交锋')
    rows = {
        "npc": [stranger.to_dict()] if stranger else [], "friend": player.dao_friends,
        "captive": player.prisoners, "disciple": player.disciples,
        "concubine": player.concubines, "party": deps._public_party(game),
        "master": [player.master] if player.master else [],
        "companion": [player.dao_companion] if player.dao_companion else [],
    }
    if kind not in rows:
        raise ValueError("未知处置对象")
    person = next((row for row in rows[kind] if str(row.get("id")) == str(target_id)), None)
    from ...spatial_people import require_access
    require_access(game, person)
    if not person or not person.get("alive", True) or person.get("world", player.world) != player.world:
        raise ValueError("此人不在身边或已经陨落")
    npc_id = str(person.get("npc_id") or person["id"])
    npc = find_person(game, npc_id)
    # Captivity removes an NPC from the free population, but does not kill them.
    bound = kind == "captive" or (kind == "concubine" and person.get("source") == "captive")
    if not bound and not is_free(person):
        raise ValueError("此人已退出自由活动名册")
    if npc and (npc.world != player.world or not npc.alive):
        raise ValueError("此人不在当前界面或已经陨落")
    rng = decode_rng(game.seed, game.rng_state)
    rank = npc.realm_index if npc and not bound else int(person.get("realm_index", 1))
    layer = npc.layer if npc and not bound else int(person.get("layer", 1))
    power = deps._npc_power(npc) if npc and not bound else float(person.get("combat_power", expected_combat_power(rank, layer)))
    name = str(person.get("name", "无名修士"))
    victim = {"npc_id": npc_id, "name": name, "realm_index": rank,
              "power": power, "faction_id": npc.faction_id if npc else person.get("faction_id"),
              "race": npc.race if npc else person.get("race", "human"),
              "path": npc.path if npc else person.get("path", "dao")}
    if kind in {"captive", "concubine"}:
        victim["execution"] = True
        deps._apply_cultivator_kill(game, victim, rng)
        player.karma += 18 + rank * 7
        result, summary = "killed", f"你处死了{name}。对方受制于你，无需战斗判定。"
    else:
        target = {"target_name": name, "target_power": power, "primary_power": power,
                  "target_realm_index": rank, "target_layer": layer, "combat_type": "cultivator",
                  "npc_id": npc_id, "faction_id": victim["faction_id"], "path": victim["path"],
                  "race": victim["race"], "world": player.world, "kill_karma": not capture,
                  "action": "capture" if capture else "slay", "capture": capture, "non_story_combat": True,
                  "execution": kind == "disciple", "relationship_kind": kind,
                  "exclude_allied_ids": [str(target_id), npc_id]}
        result, summary = deps._combat(game, target, not capture, rng)
        # A betrayed survivor no longer supplies allied combat power or affection.
        player.party = [row for row in player.party if str(row.get("id")) not in {npc_id, str(target_id)}]
        if npc and npc.alive:
            npc.affinity = -100
        if result != "killed":
            person["affinity"] = -100
            identities = {str(target_id), npc_id}
            player.disciples = [row for row in player.disciples if str(row.get("id")) not in identities]
            player.dao_friends = [row for row in player.dao_friends if str(row.get("id")) not in identities]
            if player.master and str(player.master.get("id")) in identities:
                player.master = None
            if player.dao_companion and str(player.dao_companion.get("id")) in identities:
                player.dao_companion = None
    if result == "killed":
        person["alive"] = False
        person["death_reason"] = f"被{player.name}处死" if kind != "party" else f"遭{player.name}背叛击杀"
        if npc:
            npc.death_reason = person["death_reason"]
        player.prisoners = [row for row in player.prisoners if str(row.get("id")) != str(target_id)]
    player.joint_friend_crossing = [row for row in player.joint_friend_crossing if str(row.get("id")) not in {npc_id, str(target_id)}]
    if player.joint_spirit_crossing and str(player.joint_spirit_crossing.get("id")) in {npc_id, str(target_id)}:
        player.joint_spirit_crossing = None
    game.history.append(HistoryRecord(
        "SYS_RELATIONSHIP_VIOLENCE", 1, player.age, "处置亲随" if kind != "party" else "背叛同行",
        str(target_id), result, summary, {"kind": kind}, ["system", "relationship", "combat"],
    ))
    game.rng_state = encode_rng(rng)
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)

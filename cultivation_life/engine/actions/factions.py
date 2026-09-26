from __future__ import annotations

from typing import Any
from ...content_registry import FACTION_REWARDS, REALMS, RACE_DEFINITIONS, WORLD_SYSTEMS
from ...models import GameState, HistoryRecord, Player, SectNpc, SectState
from ...runtime import decode_rng, encode_rng, now_iso
from ...world_state import race_pair
from ..dependencies import FactionActionDependencies


def create_faction(deps: FactionActionDependencies, game_id: str, name: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    clean_name = name.strip()[:18]
    if not clean_name:
        raise ValueError("请为新宗门题名")
    if game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法开宗立派")
    if player.faction_id:
        raise ValueError("你已有宗门归属，不能同时另立山门")
    if any(sect.name == clean_name and not sect.extinct for sect in game.sects.values()):
        raise ValueError("此宗门名号已经存在")
    sect_id = f"player_sect_{game.id.replace('-', '')[:10]}"
    path = player.technique.path if player.technique else player.path
    sect = SectState(
        sect_id, clean_name, player.world, [],
        description=f"由{player.name}于{player.age}岁开创的宗门。", path=path,
        founded_by_player=True, founder_player_id=game.id,
        allegiance_race=player.allegiance_race or player.race,
    )
    rng = decode_rng(game.seed, game.rng_state)
    for index in range(int(WORLD_SYSTEMS["player_faction"]["initial_followers"])):
        realm_index = 0 if player.realm_index == 0 else max(1, player.realm_index - 1)
        layer = 1 if realm_index == 0 else rng.randint(1, min(REALMS[realm_index].layers, 3))
        age, lifespan = deps._roll_recruit_age_lifespan(realm_index, path, rng, young=True)
        npc = SectNpc(
            f"{sect_id}_founder_{index}", rng.choice(["沈砚", "叶舟", "顾青", "陆遥", "白川", "楚宁"]),
            "开山门人", realm_index, layer, age, lifespan,
            spirit_root=deps._random_npc_root(realm_index, rng) if realm_index else "none",
            path=path, race=player.race, world=player.world, affinity=rng.uniform(28, 48),
        )
        npc.treasure_item_id = deps._select_npc_treasure(npc, rng)
        sect.npcs.append(npc)
    game.sects[sect_id] = sect
    player.faction_id = sect_id
    player.allegiance_race = sect.allegiance_race
    player.faction_join_age = player.age
    player.faction_contribution = 0
    deps._ensure_sect_relations(game)
    threshold = deps._governance_threshold(player.world)
    pressured = player.realm_index < threshold
    summary = (
        f"你立下{clean_name}山门。当前修为低于本界公认的立派底线，周边势力已经开始排挤试探。"
        if pressured else f"你立下{clean_name}山门，各方承认了这座新势力的存在。"
    )
    game.history.append(HistoryRecord(
        "SYS_FOUND_FACTION", 1, player.age, "开宗立派", sect_id, "founded", summary,
        {"faction_id": sect_id, "under_pressure": pressured},
        ["system", "faction", "founding", f"world:{player.world}"],
    ))
    game.rng_state = encode_rng(rng)
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def create_family(deps: FactionActionDependencies, game_id: str, name: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    clean_name = name.strip()[:18]
    if not clean_name:
        raise ValueError("请为修仙家族题名")
    if game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法建立家族")
    if game.family and not game.family.extinct:
        raise ValueError("你已经建立修仙家族")
    heirs = [child for child in player.offspring if child.get("alive", True) and child.get("cultivation_started")]
    if not heirs:
        raise ValueError("至少要有一名拥有灵根并已经踏入仙途的后代，才能建立修仙家族")
    family_id = f"family_{game.id.replace('-', '')[:10]}"
    family = SectState(
        family_id, clean_name, player.world, [],
        description=f"由{player.name}与后代共同建立的修仙家族，亦接纳外姓门人。",
        path=player.technique.path if player.technique else player.path,
        founded_by_player=True, founder_player_id=game.id,
        allegiance_race=deps._player_allegiance_race(player),
    )
    for child in heirs:
        root = str(child.get("spirit_root", "none"))
        npc = SectNpc(
            str(child["id"]), str(child["name"]), "嫡系后人", int(child.get("realm_index", 1)),
            int(child.get("layer", 1)), int(child.get("age", 8)), child.get("lifespan"),
            spirit_root=root, path=str(child.get("path", family.path)), race=player.race,
            world=player.world, affinity=60.0,
            gender=str(child.get("gender") or deps._stable_gender(str(child.get("id", "")))),
        )
        family.npcs.append(npc)
    game.family = family
    game.history.append(HistoryRecord(
        "SYS_FOUND_FAMILY", 1, player.age, "仙族初立", family_id, "founded",
        f"你以{clean_name}为号建立修仙家族，{len(heirs)}名踏入仙途的后代列入族谱，山门同时向外姓低阶修士开放。",
        {"family_id": family_id, "heirs": [child["id"] for child in heirs]},
        ["system", "family", "founding", f"world:{player.world}"],
    ))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def _vote_probability(current_affinity: float, requested_status: str, voter_affinity: float = 0.0) -> float:
    if requested_status == "war":
        base = 0.48 - current_affinity / 220
    elif requested_status in {"alliance", "vassal"}:
        base = 0.48 + current_affinity / 220
    elif requested_status == "truce":
        base = 0.68 if current_affinity < 0 else 0.48
    else:
        base = 0.56
    return max(0.08, min(0.92, base + voter_affinity / 500))


def propose_race_diplomacy(deps: FactionActionDependencies, game_id: str, target_race: str, status: str) -> dict[str, Any]:
    if deps._intrigue_enabled():
        resolution_type = {"war": "declare_war", "alliance": "form_alliance", "truce": "make_peace", "neutral": "break_alliance"}.get(status)
        if resolution_type:
            return deps.intrigue_propose_resolution(game_id, "race", resolution_type, target_race, True)
    game = deps._load(game_id)
    player = game.player
    if game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法召开族议")
    if not deps._has_race_voice(game):
        raise ValueError("只有身处种族上界的人族大乘才能发起人族外交表决")
    current_world = player.world
    if target_race == "human" or target_race not in RACE_DEFINITIONS or current_world not in RACE_DEFINITIONS[target_race].get("worlds", []):
        raise ValueError("目标种族无效")
    if status not in {"war", "alliance", "truce", "neutral", "vassal"}:
        raise ValueError("未知外交决议")
    key = race_pair("human", target_race)
    relation = game.race_relations.setdefault(key, {"affinity": 0.0, "status": "neutral", "since_age": player.age})
    if relation.get("status") == "war" and status != "war":
        raise ValueError("战争已经进入征伐阶段，请在战争窗口依据战果进行和谈")
    voters: dict[str, SectNpc] = {}
    for npc in [*game.world_npcs.values(), *game.notable_npcs.values(), *(n for s in game.sects.values() for n in s.npcs)]:
        if npc.alive and npc.world == current_world and npc.race == "human" and npc.realm_index >= 8:
            voters[npc.id] = npc
    rng = decode_rng(game.seed, game.rng_state)
    ballots = [{"name": player.name, "vote": True, "player": True}]
    for npc in voters.values():
        chance = deps._vote_probability(float(relation.get("affinity", 0)), status, float(npc.affinity or 0))
        ballots.append({"name": npc.name, "vote": rng.random() < chance, "chance": round(chance, 3), "player": False})
    yes = sum(bool(ballot["vote"]) for ballot in ballots)
    passed = yes > len(ballots) / 2
    old_status = str(relation.get("status", "neutral"))
    if passed:
        affinity = {"war": -75, "alliance": 80, "truce": -5, "neutral": 0, "vassal": 65}[status]
        deps._set_diplomatic_relation(game, relation, status, "human", target_race, "race", affinity)
    relation["last_vote"] = {"age": player.age, "proposal": status, "yes": yes, "total": len(ballots), "passed": passed, "ballots": ballots}
    action_name = {"war":"宣战","alliance":"结盟","truce":"停战","neutral":"恢复中立","vassal":"确立依附"}[status]
    target_name = RACE_DEFINITIONS[target_race]["name"]
    summary = f"你提议人族与{target_name}{action_name}；{yes}/{len(ballots)}票赞成，决议{'通过' if passed else '未通过'}。"
    game.history.append(HistoryRecord(
        "SYS_PLAYER_RACE_VOTE", 1, player.age, "人族大乘议会", status, "passed" if passed else "rejected",
        summary, {"races":["human", target_race], "status":[old_status, relation.get("status")], "vote":relation["last_vote"]},
        ["system", "diplomacy", "race", "vote", "world_news", f"world:{current_world}"],
    ))
    game.rng_state = encode_rng(rng)
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def propose_sect_diplomacy(deps: FactionActionDependencies, game_id: str, target_faction: str, status: str) -> dict[str, Any]:
    if deps._intrigue_enabled():
        resolution_type = {"war": "declare_war", "alliance": "form_alliance", "truce": "make_peace", "neutral": "break_alliance"}.get(status)
        if resolution_type:
            return deps.intrigue_propose_resolution(game_id, "sect", resolution_type, target_faction, True)
    game = deps._load(game_id)
    player = game.player
    if game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法召开宗门议事")
    if not deps._has_sect_voice(game):
        raise ValueError("你尚未取得当前宗门的外交话语权")
    own = game.sects[player.faction_id]
    target = game.sects.get(target_faction)
    if not target or target.extinct or target.id == own.id or target.world != own.world:
        raise ValueError("目标宗门无效")
    if status not in {"war", "alliance", "truce", "neutral", "vassal"}:
        raise ValueError("未知外交决议")
    deps._ensure_sect_relations(game)
    key = race_pair(own.id, target.id)
    relation = game.sect_relations.setdefault(key, {"affinity":0.0,"status":"neutral","since_age":player.age})
    if relation.get("status") == "war" and status != "war":
        raise ValueError("战争已经进入征伐阶段，请在战争窗口依据战果进行和谈")
    threshold = deps._governance_threshold(own.world)
    voters = [npc for npc in own.npcs if npc.alive and npc.world == own.world and npc.realm_index >= threshold]
    rng = decode_rng(game.seed, game.rng_state)
    ballots = [{"name":player.name,"vote":True,"player":True}]
    for npc in voters:
        chance = deps._vote_probability(float(relation.get("affinity", 0)), status, float(npc.affinity or 0))
        ballots.append({"name":npc.name,"vote":rng.random() < chance,"chance":round(chance,3),"player":False})
    yes = sum(bool(ballot["vote"]) for ballot in ballots)
    passed = yes > len(ballots) / 2
    old_status = str(relation.get("status", "neutral"))
    if passed:
        deps._set_diplomatic_relation(
            game, relation, status, own.id, target.id, "sect",
            float({"war":-75,"alliance":80,"truce":-5,"neutral":0,"vassal":65}[status]),
        )
    relation["last_vote"] = {"age":player.age,"proposal":status,"yes":yes,"total":len(ballots),"passed":passed,"ballots":ballots}
    action_name = {"war":"宣战","alliance":"结盟","truce":"停战","neutral":"恢复中立","vassal":"确立依附"}[status]
    summary = f"你提议{own.name}与{target.name}{action_name}；{yes}/{len(ballots)}票赞成，决议{'通过' if passed else '未通过'}。"
    game.history.append(HistoryRecord(
        "SYS_PLAYER_SECT_VOTE",1,player.age,"宗门外交议事",status,"passed" if passed else "rejected",summary,
        {"sects":[own.id,target.id],"status":[old_status,relation.get("status")],"vote":relation["last_vote"]},
        ["system","diplomacy","faction","vote","world_news",f"world:{player.world}"],
    ))
    game.rng_state = encode_rng(rng)
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def transfer_vassal_personnel(
    deps: FactionActionDependencies, game_id: str, kind: str, target_id: str, npc_id: str,
) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法调动人事")
    if kind not in {"race", "sect"}:
        raise ValueError("未知势力类型")
    own_id = deps._player_allegiance_race(player) if kind == "race" else player.faction_id
    if not own_id or (kind == "race" and not deps._has_race_voice(game)) or (kind == "sect" and not deps._has_sect_voice(game)):
        raise ValueError("你尚未取得该势力的话语权")
    relations = game.race_relations if kind == "race" else game.sect_relations
    relation = relations.get(race_pair(str(own_id), target_id), {})
    if relation.get("status") != "vassal" or relation.get("overlord") != own_id or relation.get("subject") != target_id:
        raise ValueError("只有被依附方可以从附庸势力调动同级以下人事")
    source_sect: SectState | None = None
    if kind == "sect":
        source_sect = game.sects.get(target_id)
        candidates = list(source_sect.npcs) if source_sect else []
    else:
        candidates = []
        for sect in game.sects.values():
            for npc in sect.npcs:
                if npc.race == target_id:
                    candidates.append(npc)
                    if npc.id == npc_id:
                        source_sect = sect
    npc = next((row for row in candidates if row.id == npc_id and row.alive and row.world == player.world), None)
    player_rank = deps._actual_player_realm(player)
    if not npc or (npc.realm_index, npc.layer) > player_rank:
        raise ValueError("只能调动当前界面内、修为不高于你的附庸修士")
    if source_sect:
        source_sect.npcs = [row for row in source_sect.npcs if row.id != npc.id]
        deps._check_sect_extinction(game, source_sect)
    npc.title = "附庸外援"
    if kind == "sect":
        destination = game.sects[str(own_id)]
        npc.faction_id = destination.id
        destination.npcs.append(npc)
        destination_name = destination.name
    else:
        npc.faction_id = f"race_support:{own_id}"
        game.notable_npcs[npc.id] = npc
        destination_name = RACE_DEFINITIONS[str(own_id)]["name"]
    summary = f"你以被依附方的名义，将{npc.name}从{deps._power_name(game, kind, target_id)}调为{destination_name}外援。"
    game.history.append(HistoryRecord(
        "SYS_VASSAL_TRANSFER", 1, player.age, "附庸人事调动", npc.id, "transferred", summary,
        {"kind":kind,"overlord":own_id,"subject":target_id,"npc_id":npc.id},
        ["system","diplomacy","vassal","personnel",f"world:{player.world}"],
    ))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def _power_name(deps: FactionActionDependencies, game: GameState, kind: str, entity_id: str) -> str:
    if kind == "race":
        return RACE_DEFINITIONS.get(entity_id, {"name":entity_id})["name"]
    return game.sects.get(entity_id, SectState(entity_id, entity_id)).name


def _player_allegiance_race(player: Player) -> str:
    return str(player.allegiance_race or player.lineage_race or player.race)


def leave_faction(deps: FactionActionDependencies, game_id: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    sect = game.sects.get(player.faction_id or "")
    if game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法退出宗门")
    if not sect or sect.extinct:
        raise ValueError("你当前没有可以退出的宗门")
    release_affinity = float(WORLD_SYSTEMS["relationship"].get("relationship_release_affinity", 0))
    members = deps._sect_members(game, sect)
    for npc in members:
        npc.affinity = release_affinity
    deps._sync_relationship_records(game)
    old_id, old_name = sect.id, sect.name
    if sect.founded_by_player:
        successor = max((npc for npc in members if npc.alive), key=lambda npc:(npc.realm_index,npc.layer), default=None)
        sect.founded_by_player = False
        sect.founder_player_id = None
        sect.founded_by_npc = True
        sect.founder_npc_id = successor.id if successor else None
    player.faction_id = None
    player.allegiance_race = player.lineage_race or player.race
    player.faction_join_age = None
    player.faction_contribution = 0
    player.faction_reward_preference = None
    game.history.append(HistoryRecord(
        "SYS_PLAYER_LEAVE_FACTION",1,player.age,"退出宗门",old_id,"left",
        f"你退出{old_name}，与旧日同门的好感统一重置为中立，不会因退宗立即遭到寻仇。",
        {"faction_id":old_id,"affinity_reset":release_affinity},["system","faction","relationship"],
    ))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def arrange_faction_succession(deps: FactionActionDependencies, game_id: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    sect = game.sects.get(player.faction_id or "")
    if game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法安排宗门后事")
    if not sect or sect.extinct or not sect.founded_by_player or sect.founder_player_id != game.id:
        raise ValueError("只有仍在执掌亲手创建宗门时才能安排让权")
    members = [npc for npc in deps._sect_members(game, sect) if npc.alive and npc.world == sect.world]
    successor = max(members, key=lambda npc: (npc.realm_index, npc.layer, -npc.age), default=None)
    if not successor:
        raise ValueError("宗门中没有能够承接权柄的在世门人")
    plan = {
        "arranged": True, "eligible_return": False,
        "successor_id": successor.id, "successor_name": successor.name,
        "origin_world": sect.world, "arranged_age": player.age,
    }
    deps._intrigue_state(game).setdefault("succession_plans", {})[sect.id] = plan
    game.history.append(HistoryRecord(
        "SYS_FACTION_SUCCESSION_PLAN", 1, player.age, "安排宗门后事", sect.id, "arranged",
        f"你指定{successor.name}在自己飞升后接掌{sect.name}；若宗门延续至你重返下界，门人可能寻觅祖师，请你重新执掌大权。",
        {"sect_id": sect.id, "successor_id": successor.id},
        ["system", "faction", "succession", f"world:{sect.world}"],
    ))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def set_faction_reward(deps: FactionActionDependencies, game_id: str, reward_id: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if game.pending_event:
        raise ValueError("请先处理当前事件")
    if not player.faction_id:
        raise ValueError("你尚未加入宗门")
    if player.realm_index < 4:
        raise ValueError("进入元婴初期后方可参与宗门议事并固定年度奖励")
    if reward_id not in FACTION_REWARDS:
        raise ValueError("未知宗门奖励")
    player.faction_reward_preference = reward_id
    reward = FACTION_REWARDS[reward_id]
    game.history.append(HistoryRecord(
        "SYS_FACTION_REWARD", 1, player.age, "宗门议事", reward_id, "selected",
        f"你在议事册上选定“{reward['name']}”，今后的年度分红将固定为此项。",
        {"faction_reward_preference": reward_id}, ["system", "faction"],
    ))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)

from __future__ import annotations
from typing import Any
from ...models import GameState
from ...models import HistoryRecord
from ...content_registry import ITEM_CATALOG
from ...content_registry import MARKET_GOODS
from ...world_state import RELATION_LABELS
from ...content_registry import WORLD_SYSTEMS
from ...rules import add_item
from ..faction_geography import can_enter_faction
import copy
from ..semantic_events import emit
from ...runtime import encode_rng
from ...runtime import now_iso
from ...rules import remove_item
from .dependencies import WarPeaceDependencies


def _generate_ai_peace_offer(deps: WarPeaceDependencies, game: GameState, war: dict[str, Any], proposer: str) -> dict[str, Any]:
    """Build a score-priced demand package instead of always asking for one execution."""
    recipient = "defender" if proposer == "attacker" else "attacker"
    target_power_id = war[f"{recipient}_id"]
    budget = int(min(100, max(0, round(abs(float(war.get("war_score", 0)))))))
    demands: list[dict[str, Any]] = []

    def add(term: str, *, target_id: str = "") -> bool:
        cost = deps.WAR_TERM_DEFS[term][1]
        if sum(row["cost"] for row in demands) + cost > budget:
            return False
        demands.append({
            "term": term, "label": deps.WAR_TERM_DEFS[term][0], "cost": cost,
            "target_power_id": target_power_id, "target_id": target_id,
        })
        return True

    winner_power = deps._war_total_power(game, war, proposer)
    if proposer == "defender":
        winner_power /= 1 + float(deps._war_rules().get("defender_power_bonus", 0.10))
    target_power = deps._war_entity_power(game, war, recipient, target_power_id)
    ratio = winner_power / max(1.0, target_power)
    if war["kind"] == "sect" and budget >= deps.WAR_TERM_DEFS["annex"][1]:
        if ratio >= float(deps._war_rules().get("annex_power_ratio", 2.5)):
            add("annex")
        elif ratio >= float(deps._war_rules().get("dissolve_power_ratio", 1.35)):
            add("dissolve")
        else:
            add("vassal")
    elif (war["kind"] == "sect" and budget >= deps.WAR_TERM_DEFS["dissolve"][1]
          and ratio >= float(deps._war_rules().get("dissolve_power_ratio", 1.35))):
        add("dissolve")
    elif budget >= deps.WAR_TERM_DEFS["vassal"][1]:
        add("vassal")

    spent = sum(row["cost"] for row in demands)
    candidates = deps._available_warriors(game, war, recipient, target_power_id)
    if budget - spent >= deps.WAR_TERM_DEFS["execute"][1] and candidates:
        add("execute", target_id=candidates[0].id)
    for term in ("supplies", "stones", "alliance"):
        if term == "alliance" and any(row["term"] in {"annex", "dissolve", "vassal"} for row in demands):
            continue
        add(term)
    if not demands:
        add("white_peace")
    return {
        "proposer_side": proposer, "recipient_side": recipient, "budget": budget,
        "total_cost": sum(row["cost"] for row in demands), "demands": demands,
        "created_unit": game.diplomacy_unit,
    }


def _conclude_war_bundle(deps: WarPeaceDependencies, game: GameState, war: dict[str, Any], demands: list[dict[str, Any]],
                         beneficiary: str, *, automatic: bool = False) -> str:
    if not demands:
        demands = [{"term": "white_peace", "target_power_id": war[f"{'defender' if beneficiary == 'attacker' else 'attacker'}_id"]}]
    details: list[str] = []
    ordered = [row for row in demands if row.get("term") not in {"dissolve", "annex"}]
    ordered.extend(row for row in demands if row.get("term") in {"dissolve", "annex"})
    for index, demand in enumerate(ordered):
        details.append(deps._conclude_war(
            game, war, str(demand.get("term", "white_peace")), beneficiary,
            automatic=automatic, target_id=str(demand.get("target_id", "")),
            target_power_id=str(demand.get("target_power_id", "")),
            third_party_id=str(demand.get("third_party_id", "")),
            third_status=str(demand.get("third_status", "neutral")),
            finalize=index == len(ordered) - 1,
        ))
    war["peace_terms"] = copy.deepcopy(demands)
    if len(details) > 1:
        combined = "；".join(details)
        war["logs"][-1]["text"] = ("敌方依据战争分数提出并执行组合和约；" if automatic else "双方签订组合和约；") + combined
    return "；".join(details)


def _conclude_war(deps: WarPeaceDependencies, game: GameState, war: dict[str, Any], term: str, beneficiary: str, *, automatic: bool = False,
                  target_id: str = "", target_power_id: str = "", third_party_id: str = "",
                  third_status: str = "neutral", finalize: bool = True) -> str:
    deps._ensure_war_shape(game, war)
    loser = "defender" if beneficiary == "attacker" else "attacker"
    winner_id = war[f"{beneficiary}_id"]
    loser_id = target_power_id or war[f"{loser}_id"]
    if loser_id not in deps._coalition_ids(war, loser):
        raise ValueError("和谈目标不属于敌方参战阵营")
    winner_name = deps._war_side_name(game, war["kind"], winner_id)
    loser_name = deps._war_side_name(game, war["kind"], loser_id)
    relation = deps._war_relation(game, war["kind"], winner_id, loser_id)
    detail = "双方恢复和平"
    if term == "execute":
        candidates = deps._available_warriors(game, war, loser, loser_id)
        victim = deps._find_npc(game, target_id) if target_id else (candidates[0] if candidates else None)
        if not victim or victim not in candidates:
            raise ValueError("指定处死的修士不属于战败方参战名册")
        victim.alive = False
        victim.death_reason = "战败和约指定处死"
        if not automatic and deps._player_war_side(game, war) == beneficiary:
            emit(game, "cultivator.killed", npc_id=victim.id, execution=True)
        detail = f"{victim.name}依约被处死"
    elif term == "alliance":
        deps._set_diplomatic_relation(game, relation, "alliance", winner_id, loser_id, war["kind"], 72)
        detail = "双方被和约确立为同盟"
    elif term == "vassal":
        relation.update(status="vassal", affinity=45.0, since_age=game.player.age, overlord=winner_id, subject=loser_id)
        detail = f"{loser_name}成为{winner_name}的附庸"
    elif term == "change_relation":
        if not third_party_id or third_party_id in {winner_id, loser_id}:
            raise ValueError("必须指定第三方势力")
        third = deps._war_relation(game, war["kind"], loser_id, third_party_id)
        deps._set_diplomatic_relation(game, third, third_status, loser_id, third_party_id, war["kind"], 65 if third_status == "alliance" else 0)
        detail = f"{loser_name}被迫对第三方改为{RELATION_LABELS.get(third_status, third_status)}"
    elif term == "stones":
        amount = int(deps._war_rules().get("stone_tribute", 10000))
        from ..economy.war_finance import reparations
        amount = reparations(game, war, winner_id, loser_id, amount)
        detail = f"{loser_name}向{winner_name}上供灵石 {amount}"
    elif term == "supplies":
        own_id = deps._war_player_identity(game, war)
        supplied: list[str] = []
        if own_id == winner_id:
            from ..economy.war_finance import supplies
            supplied = supplies(game, deps.maps, war, loser_id, True)
        elif own_id == loser_id:
            for item in list(game.player.inventory):
                if len(supplied) >= 3:
                    break
                if item.id != "spirit_stone" and remove_item(game.player, item.id):
                    supplied.append(item.name)
        detail = f"{loser_name}缴纳丹药与装备" + (f"（{'、'.join(supplied)}）" if supplied else "")
    elif term in {"dissolve", "annex"}:
        if war["kind"] != "sect":
            raise ValueError("种族与界面势力不能被解散或合并")
        loser_sect = deps._war_sect(game, loser_id)
        winner_sect = deps._war_sect(game, winner_id)
        if not loser_sect:
            raise ValueError("战败宗门已经不存在")
        winner_power = deps._war_total_power(game, war, beneficiary)
        if beneficiary == "defender":
            winner_power /= 1 + float(deps._war_rules().get("defender_power_bonus", 0.10))
        target_power = deps._war_entity_power(game, war, loser, loser_id)
        ratio = winner_power / max(1.0, target_power)
        if term == "annex":
            if ratio < float(deps._war_rules().get("annex_power_ratio", 2.5)):
                raise ValueError("双方战力差距尚不足以执行合并")
            if winner_sect:
                for npc in deps._sect_members(game, loser_sect):
                    if npc.alive and not can_enter_faction(winner_sect, npc):
                        npc.faction_id = None
                        game.notable_npcs.setdefault(npc.id, npc)
                    elif npc.alive:
                        npc.faction_id = winner_id
                        if all(existing.id != npc.id for existing in winner_sect.npcs):
                            winner_sect.npcs.append(npc)
            detail = f"{loser_name}并入{winner_name}"
        else:
            if ratio < float(deps._war_rules().get("dissolve_power_ratio", 1.35)):
                raise ValueError("胜方总战力尚不足以强制解散对方势力")
            for npc in deps._sect_members(game, loser_sect):
                if npc.alive:
                    npc.faction_id = None
                    game.notable_npcs.setdefault(npc.id, npc)
            detail = f"{loser_name}就地解散"
        loser_sect.extinct = True
        own_id = game.player.faction_id
        if own_id == winner_id and term == "annex":
            game.player.milestones["annexed_faction"] = 1
        wanted_key = f"sect:{loser_id}"
        if (
            own_id == winner_id and term == "dissolve"
            and float(game.player.hostility.get(wanted_key, 0))
            > float(WORLD_SYSTEMS["faction_conflict"]["wanted_threshold"])
        ):
            game.player.milestones["became_wanted_target"] = 1
            game.player.milestones["dissolved_wanted_power"] = 1
        if own_id == winner_id and term == "dissolve":
            deps._record_former_jailer_dissolved(game.player, "sect", loser_id)
        if game.player.faction_id == loser_id:
            game.player.faction_id = winner_id if term == "annex" else None
    elif term != "white_peace":
        raise ValueError("未知战争条款")
    if not finalize:
        return detail
    war["status"] = "ended"
    war["end_age"] = game.player.age
    war["peace_term"] = term
    war["winner"] = None if term == "white_peace" else beneficiary
    truce_until = game.diplomacy_unit + int(deps._war_rules().get("truce_units", 5))
    for attacker_id in deps._coalition_ids(war, "attacker"):
        for defender_id in deps._coalition_ids(war, "defender"):
            cross_relation = deps._war_relation(game, war["kind"], attacker_id, defender_id)
            cross_relation["war_truce_until_unit"] = truce_until
            if cross_relation.get("status") not in {"alliance", "vassal"}:
                cross_relation.update(status="truce", affinity=max(-20.0, float(cross_relation.get("affinity", -40))), since_age=game.player.age)
                cross_relation["truce_until_unit"] = truce_until
    text = ("厌战迫使双方签订无条件和平；" if automatic else f"双方签订和约；") + detail + f"，停战 {int(deps._war_rules().get('truce_units', 5))} 个行动单位。"
    deps._append_war_log(game, war, "战争结束", text)
    game.history.append(HistoryRecord(
        "SYS_WAR_PEACE", 1, game.player.age, "战争和约", term, "ended", text,
        {"war_id": war["id"], "term": term}, ["system", "war", "diplomacy", f"world:{war['world']}"],
    ))
    return text


def war_peace(deps: WarPeaceDependencies, game_id: str, war_id: str, term: str, *, target_id: str = "", target_power_id: str = "",
              third_party_id: str = "", third_status: str = "neutral", concede: bool = False) -> dict[str, Any]:
    game = deps._load(game_id)
    war = next((row for row in game.wars if row.get("id") == war_id), None)
    if not war or war.get("status") not in {"active", "peace_ready"}:
        raise ValueError("当前没有可供和谈的战争")
    if war.get("controller") != "player" or not deps._player_has_war_voice(game, war):
        raise ValueError("你没有代表势力签署和约的权力")
    if term not in deps.WAR_TERM_DEFS:
        raise ValueError("未知战争条款")
    if int(war.get("battles", 0)) < 2 and war.get("status") != "peace_ready" and term != "white_peace":
        raise ValueError("至少经历两场战事后才能提出有条件和谈")
    player_side = deps._player_war_side(game, war)
    beneficiary = ("defender" if player_side == "attacker" else "attacker") if concede else player_side
    if not beneficiary:
        raise ValueError("你并非参战方")
    effective_score = float(war.get("war_score", 0)) * (1 if beneficiary == "attacker" else -1)
    cost = deps.WAR_TERM_DEFS[term][1]
    loser = "defender" if beneficiary == "attacker" else "attacker"
    selected_power = target_power_id if not concede else ""
    selected_power = selected_power or war[f"{loser}_id"]
    if selected_power not in deps._coalition_ids(war, loser):
        raise ValueError("和谈目标不属于战败阵营")
    if selected_power != war[f"{loser}_id"] and term != "white_peace":
        cost = int(round(cost * float(deps._war_rules().get("ally_term_cost_multiplier", 1.25))))
    if not concede and term != "white_peace" and effective_score < cost:
        raise ValueError(f"当前战争分数 {effective_score:.0f}，不足以提出该条款（需要 {cost}）")
    if deps._intrigue_enabled():
        own_id = str(war[f"{player_side}_id"])
        opposing_id = str(war[f"{'defender' if player_side == 'attacker' else 'attacker'}_id"])
        vote_rng = deps.decode_rng(game.seed, game.rng_state)
        resolution = deps._intrigue_resolve(
            game, str(war["kind"]), own_id, "make_peace", opposing_id, True, "player", vote_rng,
        )
        game.rng_state = encode_rng(vote_rng)
        if resolution["result"] != "passed":
            game.updated_at = now_iso()
            deps.store.save(game)
            return deps.present(game)
    deps._conclude_war(game, war, term, beneficiary, target_id=target_id, target_power_id=selected_power,
                       third_party_id=third_party_id, third_status=third_status)
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)

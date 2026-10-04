"""Explicit buddhist actions operations; callers own composition."""
from __future__ import annotations
from ..spatial_capabilities import scope_key, site_key, local_names

from ...content_registry import WORLD_SYSTEMS
from ...rules import remove_item
from ...runtime import decode_rng, encode_rng, now_iso
from ..buddhist_wish import nirvana
from .dependencies import BuddhistActionDependencies
from .rules import buddhist_active, buddhist_config, site_state


def buddhist_action(deps: BuddhistActionDependencies, game_id, action, **payload):
    game = deps._load(game_id)
    if not buddhist_active(game) or not game.player.alive or game.player.imprisonment:
        raise ValueError("当前无法主持佛修事务")
    deps._ensure_buddhist_state(game)
    state, player, config = game.buddhist_state, game.player, buddhist_config()
    if game.pending_event:
        raise ValueError("请先处理当前事件")
    rng = decode_rng(game.seed, game.rng_state)
    site = site_state(state, scope_key(game), site_key(game))
    if action == "nirvana":
        nirvana(deps.nirvana, game, rng)
    elif action == "blessing":
        chosen = state["worlds"][scope_key(game)]["blessings"]
        identity = str(payload.get("blessing", ""))
        if identity not in config["blessings"]:
            raise ValueError("未知加持")
        if identity in chosen:
            chosen.remove(identity)
        elif state["dharma_karma"] > 0 and len(chosen) < 3:
            chosen.append(identity)
        else:
            raise ValueError("正业力时最多启用三项加持")
    elif action == "temple":
        view = deps._public_buddhist(game)
        cost = view["temple_cost"]
        if cost is None:
            raise ValueError("寺庙已达三级")
        if not remove_item(player, "spirit_stone", cost):
            raise ValueError(f"需要 {cost} 灵石")
        site["temple"] += 1
        site["followers"] = max(site["followers"], config["temples"][site["temple"]]["floor"])
        deps._buddhist_record(game, f"在{local_names(game, deps.maps, scope_key(game), site_key(game))[1]}修建了{site['temple']}级寺庙。")
    elif action == "permission":
        row = next((row for row in deps._buddhist_permissions(game) if row["id"] == payload.get("authority")), None)
        if not row or row["permitted"]:
            raise ValueError("此势力无需再缴纳弘法许可费")
        if not remove_item(player, "spirit_stone", row["fee"]):
            raise ValueError(f"需要 {row['fee']} 灵石")
        unit = int(WORLD_SYSTEMS["time_units"][str(player.realm_index)])
        site["permissions"][row["id"]] = player.age + max(config["permission_years"], unit * 4)
    elif action == "start":
        if state["assembly"] or state["dharma_karma"] < -25 or game.active_trial:
            raise ValueError("当前不能开坛：业力须不低于 -25，且没有进行中的法会或劫关")
        art = next((row for row in player.known_techniques if row.id == payload.get("technique")), None)
        if not art:
            raise ValueError("请选择已学功法")
        view = deps._public_buddhist(game)
        state["assembly"] = {"world": scope_key(game), "location": site_key(game),
            "technique": art.id, "technique_name": art.name, "level": art.level,
            "started_age": player.age, "stage": 0, "stage_years": 0,
            "unit_years": int(WORLD_SYSTEMS["time_units"][str(player.realm_index)]),
            "attendance": view["attendance"], "burden": deps._buddhist_burden(game),
            "score": art.level * config["technique_level_score"] + art.grade * config.get("technique_grade_score", .5), "events": [], "pending": None}
        deps._continue_buddhist_assembly(game, rng)
    elif action == "continue":
        deps._continue_buddhist_assembly(game, rng)
    elif action == "cancel":
        if not state["assembly"]:
            raise ValueError("没有进行中的法会")
        deps._finish_buddhist_assembly(game, forced_failure=True)
    else:
        raise ValueError("未知佛修操作")
    deps._ensure_market(game, rng)
    game.rng_state = encode_rng(rng)
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)

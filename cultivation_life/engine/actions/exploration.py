"""Explicit entry points for talismans, spatial instances and world ejection."""

from dataclasses import dataclass
from typing import Callable, Any

from ...content_registry import ACTIONS, WORLD_SYSTEMS
from ...runtime import decode_rng, encode_rng, now_iso
from ...rules import max_hp, max_mp, opportunity_multiplier, grant_qi_experience
from ...system import spatial, talismans, world_boundary
from ...system.possession_system import advance_player_age
from ...time_flow import advance_elapsed_year


@dataclass(frozen=True)
class ExplorationDependencies:
    load: Callable
    save: Callable
    present: Callable
    maps: Any
    plan: Callable
    apply: Callable
    refresh_market: Callable
    die: Callable
    _advance_world_year: Callable
    body_step: Callable
    body_required: Callable
    sense_step: Callable
    _advance_soul_erosion_time: Callable
    prepare_sage: Callable
    finish_sage: Callable
    advance_natal: Callable


def move_world(
    deps: ExplorationDependencies, game, destination, rng, *, mode="rift", location=None
):
    source = game.player.world
    if source != destination:
        plan = deps.plan(
            game,
            destination,
            mode,
            arrival_location=location,
            reason="空间通道" if mode == "rift" else "界面排斥",
        )
        deps.apply(game, plan)
    elif location:
        game.player.location_id = location
    game.player.party = []
    game.player.awaiting_ascension = False
    if (
        game.player.realm_index >= 6
        and WORLD_SYSTEMS["world_profiles"][destination]["tier"] < 3
    ):
        if game.player.next_tribulation_age is None:
            game.player.next_tribulation_age = game.player.age + 3000
    if destination not in spatial.SPECIAL_WORLDS:
        deps.refresh_market(game, rng)
    else:
        game.market_offers = []
        if hasattr(game, "_pending_world_market"):
            del game._pending_world_market


def reconcile_boundary(deps: ExplorationDependencies, game, rng=None):
    if not game.player.alive or game.active_trial or game.pending_event:
        return False
    scene = spatial.current(game)
    ceiling = scene.get("power_ceiling", 8) if scene and scene["kind"] == "lost" else None
    destination = world_boundary.destination(game.player, realm_ceiling=ceiling)
    if not destination or destination == game.player.world:
        return False
    rng = rng if rng is not None else decode_rng(game.seed, game.rng_state)
    origin = game.player.world
    spatial.ensure(game)["current"] = None
    move_world(deps, game, destination, rng, mode="expulsion")
    spatial.journal(
        game,
        f"显露道果超出{WORLD_SYSTEMS['world_names'][origin]}的容纳范围，界面排斥使你飞升{WORLD_SYSTEMS['world_names'][destination]}；无需偷渡节点。",
    )
    game.rng_state = encode_rng(rng)
    return True


def commit(deps: ExplorationDependencies, game, rng):
    game.rng_state = encode_rng(rng)
    reconcile_boundary(deps, game)
    game.updated_at = now_iso()
    deps.save(game)
    return deps.present(game)


def talisman_action(deps: ExplorationDependencies, game_id, action, payload):
    if any(
        key
        not in {
            "action",
            "method_id",
            "material1",
            "material2",
            "element",
            "npc_id",
            "talisman_id",
        }
        or not isinstance(value, str)
        for key, value in payload.items()
    ):
        raise ValueError("符箓参数必须使用已声明的文本字段")
    game = deps.load(game_id)
    text = talismans.act(game, action, payload)
    spatial.journal(game, text)
    deps.save(game)
    return deps.present(game)


def require_free(game):
    p = game.player
    if (
        not p.alive
        or game.pending_event
        or game.active_trial
        or p.imprisonment
        or p.ghost_captor
    ):
        raise ValueError("请先处理当前事件、劫战或拘禁状态")
    if game.guixu_state.get("player_session"):
        raise ValueError("身处归墟时不能使用外界空间裂缝")


def enter_scene(deps: ExplorationDependencies, game, scene, rng):
    spatial.ensure(game)["current"] = scene["id"]
    scene["visits"] += 1
    move_world(deps, game, "rift" if scene["kind"] == "secluded" else "lost", rng)
    spatial.journal(game, f"抵达{scene['name']}；此空间与外界隔绝。")


def spatial_action(deps: ExplorationDependencies, game_id, action, payload):
    if any(
        key not in {"action", "target_id"} or not isinstance(value, str)
        for key, value in payload.items()
    ):
        raise ValueError("空间参数必须使用已声明的文本字段")
    game = deps.load(game_id)
    require_free(game)
    if (spatial.current(game) or {}).get('heavens_target'):
        raise ValueError('此处是有限诸天异象，请从诸天面板处理机关或沿原路退出')
    state, p = spatial.ensure(game), game.player
    rng = decode_rng(game.seed, game.rng_state)
    target = payload.get("target_id", "")
    if action == "open":
        if (p.realm_index, p.layer) < (5, 7) or p.mp < max_mp(p) * 0.25:
            raise ValueError("开辟裂缝须化神后期显露修为，并消耗四分之一法力上限")
        p.mp -= max_mp(p) * 0.25
        spatial.new_rift(game, rng, deps.maps, controlled=True)
        spatial.journal(game, "以神通开辟可控裂缝。通往何处仍不可预知。")
    elif action == "enter":
        if not spatial.visible(game):
            raise ValueError("须达到元婴初期，方可感知并进入空间裂缝")
        rift = next(
            (
                r
                for r in state["rifts"]
                if r["id"] == target
                and r["world"] == p.world
                and r["instance_id"] == state["current"]
                and r["expires_age"] > p.age
            ),
            None,
        )
        location_id = (spatial.current(game) or {}).get("location_id", p.location_id)
        if not rift or rift["location_id"] != location_id:
            raise ValueError("此裂缝已经消失或不在当前地图")
        score = spatial.protection(game, consume=True)
        state["rifts"].remove(rift)
        requirement = spatial.rift_requirement(rift, p.age)
        if score["score"] < requirement:
            deps.die(
                game,
                f"空间裂缝撕裂护持：防护判定 {score['score']:.1f} / {requirement}，身死道消。",
                "SYS_RIFT_DEATH",
            )
            return commit(deps, game, rng)
        weights = spatial.outcome_weights(rift)
        outcome = rng.choices(list(weights), weights=list(weights.values()))[0]
        origin = p.world
        if outcome == "secluded":
            enter_scene(deps, game, spatial.create_instance(game, rng, "secluded"), rng)
        elif outcome == "local" and spatial.current(game):
            scene = spatial.current(game)
            scene["location_id"] = rng.choice(scene["locations"])["id"]
            spatial.journal(game, "裂缝将你安全送至当前独立空间内的另一处地图。")
        elif outcome == "local":
            location = rng.choice(deps.maps.worlds[origin]["locations"])["id"]
            # Arrival deliberately does not invoke normal travel's lethal gate.
            p.location_id = location
            spatial.journal(
                game,
                f"裂缝将你安全送往本界地图：{deps.maps.location(origin, location)['name']}。",
            )
        else:
            destinations = [
                w
                for w, profile in WORLD_SYSTEMS["world_profiles"].items()
                if profile["enabled"] and w not in {origin, "rift"}
            ]
            destination = rng.choice(destinations)
            if destination == "lost":
                enter_scene(deps, game, spatial.create_instance(game, rng, "lost"), rng)
            else:
                state["current"] = None
                move_world(deps, game, destination, rng)
                spatial.journal(
                    game,
                    f"单程界面通道将你送至{WORLD_SYSTEMS['world_names'][destination]}。",
                )
    elif action == "descend":
        if p.world in spatial.SPECIAL_WORLDS:
            raise ValueError("独立空间只能经空间裂缝离开，不能借下界入口绕过界壁")
        if not world_boundary.can_descend(p, 0):
            raise ValueError(
                "须具备九阶真实道果，并以压制秘法将显露修为降至大乘九层以内"
            )
        if target:
            scene = state["instances"].get(target)
            if not scene or scene["kind"] != "lost":
                raise ValueError("只能定向进入曾到访的失落界面")
        else:
            scene = spatial.create_instance(game, rng, "lost")
        enter_scene(deps, game, scene, rng)
    elif action == "explore":
        if not spatial.current(game):
            raise ValueError("当前不在独立空间")
        # Searching costs one year and retains normal lifespan and thunder checks.
        advance_player_age(p)
        advance_elapsed_year(deps, game, rng, [], encounters=False)
        if p.alive and not game.pending_event and spatial.current(game):
            spatial.journal(game, spatial.explore(game, rng))
    elif action in {"move", "join", "talk"}:
        text = spatial.local_action(game, action, target)
        advance_player_age(p)
        advance_elapsed_year(deps, game, rng, [], encounters=False)
        spatial.journal(game, text)
    else:
        raise ValueError("未知空间操作")
    return commit(deps, game, rng)


def train(deps: ExplorationDependencies, game, action, units):
    require_free(game)
    local_actions = {"cultivate", "rest", "body_train", "sense_train"}
    if game.player.world == 'lost':
        local_actions |= {'sage_preach', 'sage_teach', 'sage_answer'}
    if action not in local_actions:
        raise ValueError("独立空间仅可修炼、炼体、锻炼神识、调息或使用空间内入口")
    p = game.player
    if action == "cultivate" and spatial.cultivation_block_reason(game):
        raise ValueError(spatial.cultivation_block_reason(game))
    if p.cultivation_suppression and action == "cultivate":
        raise ValueError("请先解除压制秘法，再修炼主修功法")
    if (
        action == "body_train"
        and not p.body_technique
        or action == "sense_train"
        and not p.divine_sense_technique
    ):
        raise ValueError("须先配置对应功法")
    if action == "body_train" and (
        p.body_training >= WORLD_SYSTEMS["body_cultivation"]["max_layer"]
        or p.awaiting_body_breakthrough
        or p.body_progress >= deps.body_required(p)
    ):
        raise ValueError("炼体已至极限或积累已满，请先处理突破")
    from ...rules import can_player_practice_technique

    if (
        action == "cultivate"
        and p.technique
        and not can_player_practice_technique(p, p.technique.element)
    ):
        raise ValueError("灵根与主修功法不合")
    rng = decode_rng(game.seed, game.rng_state)
    deps.prepare_sage(game, action)
    time_unit = int(WORLD_SYSTEMS["time_units"][str(p.realm_index)])
    years = max(1, min(10, int(units))) * time_unit
    origin = p.world
    elapsed = 0
    for _ in range(years):
        advance_player_age(p)
        elapsed += 1
        if action == "cultivate":
            low, high = ACTIONS[action]["opportunity"]
            gain = (
                rng.randint(low, high)
                * opportunity_multiplier(p)
                * (spatial.cfg()["secluded_multiplier"] if spatial.current(game)['kind'] == 'secluded' else 1)
            )
            if p.world == "lost" and p.path == "demonic":
                gain *= WORLD_SYSTEMS["demonic_cultivation"][
                    "natural_cultivation_multiplier"
                ]
            if p.world == "lost":
                gain *= (spatial.current(game).get("population_rules") or {}).get("cultivation_multiplier", 1.)
            if p.technique and p.spirit_root != "none":
                p.opportunity += gain
                grant_qi_experience(
                    p,
                    gain,
                    spatial.current_qi(game),
                )
        elif action == "body_train":
            p.body_progress = min(
                deps.body_required(p), p.body_progress + deps.body_step(p, rng)
            )
            p.awaiting_body_breakthrough = p.body_progress >= deps.body_required(p)
        elif action == "sense_train":
            p.divine_sense_experience += deps.sense_step(p)
        elif action == 'rest':
            p.hp = min(max_hp(p), p.hp + max_hp(p) * 0.05)
            p.mp = min(max_mp(p), p.mp + max_mp(p) * 0.05)
        if (
            not advance_elapsed_year(deps, game, rng, [], encounters=False)
            or p.world != origin
            or (action == "body_train" and p.awaiting_body_breakthrough)
            or (action == "cultivate" and spatial.cultivation_block_reason(game))
        ):
            break
    spatial.journal(game, f"独立空间内{ACTIONS[action]['name']}，经过 {elapsed} 年。")
    deps.finish_sage(game)
    if elapsed and p.alive:
        from ...time_flow import completed_action_units
        deps.advance_natal(game, action, completed_action_units(elapsed, time_unit))
    return commit(deps, game, rng)

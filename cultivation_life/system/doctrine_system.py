"""Explicit operations for doctrine system."""

from __future__ import annotations
import copy
from ..content_registry import REALMS, WORLD_SYSTEMS
from ..models import HistoryRecord
from ..rules import add_technique_copy, remove_item
from ..runtime import now_iso
from .conversion import quote as conversion_quote
from .doctrine.generation import rng_for
from .doctrine.progression import source
from .doctrine.provider import config, ensure, player_record
from .doctrine.cultivation import AXES, prerequisites, attempt, chance, training_cost
from .doctrine.daomen import discover, mentor, public_peers, preview
from .doctrine.fusion import manual_id as fusion_manual_id
from .cultivation_dependencies import DoctrineActionDependencies, DoctrineStudyDependencies, DoctrineViewDependencies

def _known(game, key):
    return any(t.doctrine_id == key for t in game.player.known_techniques)
def _offers(game):
    catalog = game.doctrine_state.get("definitions", {})
    # One stable, shared rotation. Looking at the UI or buying does not reroll it.
    period = int(WORLD_SYSTEMS["time_units"]["9"])
    rng = rng_for(game.seed, game.doctrine_state.get("version", 1), f"bookshop:{game.player.age // period}")
    books = [book for definition in catalog.values() for book in definition["manuals"] if book["grade"] <= game.player.realm_index]
    return rng.sample(books, min(5, len(books)))
def _price(book):
    return 15000 * (int(book["grade"]) - 8) ** 2


def _ensure_doctrines(game):
    from .immortal_aperture import ensure_aperture
    changed = ensure(game)
    return ensure_aperture(game.player) or changed


def _begin_doctrine_action(deps: DoctrineStudyDependencies, game, action, *, commit=False):
    if action == 'doctrine_fusion_study':
        deps._begin_fusion_study(game, commit=commit)
        return
    if action not in {"doctrine_study", "immortal_conversion", "daomen_explore", "immortal_trace_gather"}:
        return
    if game.player.world != "celestial" or game.player.realm_index < 9:
        raise ValueError("道统与仙灵力转化须在仙界、真仙境界开始")
    ensure(game)
    record = player_record(game)
    if action == "immortal_trace_gather":
        return
    if action == "daomen_explore":
        raise ValueError("道门寻访已改为即时预览，请在道门选择寻找同道并确认结识")
    if action == "immortal_conversion":
        raise ValueError("请在左侧仙元面板消耗机缘推进转化")
    key = record.get("study_target")
    definition = game.doctrine_state["definitions"].get(key)
    if not definition or not _known(game, key):
        raise ValueError("须先获得该道统的一门功法，再选择修炼")
    progress = record["progress"].setdefault(key, {"level": 0, "experience": 0})
    level = progress["level"]
    if level >= 9:
        raise ValueError("此道统已达 Lv9")
    if level >= 4 and record.get("origin") not in (None, key):
        raise ValueError("本源已有归属，此道统至多修炼至 Lv4")
    stage = definition["stages"][level]
    prerequisites(record, key, max(t.level for t in game.player.known_techniques if t.doctrine_id == key))
    if game.player.realm_index < stage["realm"]:
        raise ValueError(f"下一阶段须达到{REALMS[stage['realm']].name}")
    if level == 4 and progress["experience"] >= stage["years"] and not record.get("origin"):
        raise ValueError("本源积累已满，请明确选择本源归属后突破")


def _finish_doctrine_action(deps: DoctrineStudyDependencies, game, action, elapsed):
    if action == 'doctrine_fusion_study':
        if elapsed > 0 and game.player.alive and game.player.world == 'celestial':
            deps._finish_fusion_study(game, elapsed)
        return
    if (action not in {"doctrine_study", "immortal_conversion", "daomen_explore", "immortal_trace_gather"} or elapsed <= 0
            or not game.player.alive or game.player.world != "celestial"):
        return
    record = player_record(game)
    if action == "immortal_trace_gather":
        # Legacy action still earns normal opportunity; only the common award
        # boundary may roll for traces. Elapsed time grants no guaranteed traces.
        record.pop("trace_progress", None)
        return
    if action == "daomen_explore":
        key = record["explore_target"]
        # Interrupted visits retain elapsed effort, never reveal an entire roster.
        visits = record.setdefault("explore_progress", {})
        visits[key] = visits.get(key, 0) + elapsed
        if visits[key] >= 100:
            visits[key] -= 100
            npc = discover(game, key, game.doctrine_state["definitions"][key], WORLD_SYSTEMS["transcendent_combat"], config()["words"])
            game.history.append(HistoryRecord("SYS_DAOMEN_DISCOVERY", 1, game.player.age, "访求道门", npc.id,
                                             "discovered", f"循传承线索结识了{npc.name}，可向其请教。", {}, ["system", "daomen"]))
        return
    if action == "immortal_conversion":
        return  # Old elapsed-time completions cannot bypass opportunity payment.
    else:
        key = record["study_target"]
        definition = game.doctrine_state["definitions"][key]
        progress = record["progress"][key]
        prerequisites(record, key, max(t.level for t in game.player.known_techniques if t.doctrine_id == key))
        roll = rng_for(game.seed, game.doctrine_state["version"], f"study:{key}:{progress.get('attempts', 0)}").random()
        result = attempt(progress, definition, elapsed, record.get("origin"), config()["cultivation"], roll)
        completed = [progress["level"]] if result == "success" else []
        message = f"参悟《{definition['name']}》{elapsed:g} 年，现为 Lv{record['progress'][key]['level']}。"
        if result == "failed":
            message += f"本次突破失败，注解保留，下次成功率提升至 {chance(progress, config()['cultivation']):.0%}。"
        elif result == "origin_required":
            message += "积累已满，须先明确选择本源归属，再尝试突破。"
        if completed:
            message += definition["stages"][completed[-1] - 1]["description"]
        if record["progress"][key]["level"] >= 4 and not record.get("active"):
            record["active"] = key
    game.history.append(HistoryRecord("SYS_DOCTRINE_TRAIN", 1, game.player.age, "仙道修持", key,
                                     "trained", message, {"levels": completed}, ["system", "doctrine"]))


def doctrine_action(deps: DoctrineActionDependencies, game_id, action, doctrine_id=None, manual_id=None, confirm_origin=False, npc_id=None):
    if action == "buy":
        return deps.yaochi_action(game_id, "buy", manual_id)
    game = deps._cultivation_game(game_id)
    record = player_record(game)
    definition = game.doctrine_state["definitions"].get(doctrine_id)
    if action == 'fuse':
        return deps._fuse_doctrine(game, doctrine_id)
    if action == 'study_fusion':
        record['fusion_target'] = doctrine_id
        deps._begin_fusion_study(game)
        deps.store.save(game)
        return deps.advance(game_id, 'doctrine_fusion_study', 1)
    if action in {"explore", "retain_peer", "dismiss_peer"}:
        if not definition or not _known(game, doctrine_id):
            raise ValueError("先取得功法，才能循其传承访求道门")
        if action == 'explore':
            preview(game, doctrine_id, definition, config()['words'])
            # A preview is not a historical encounter or a simulated NPC.
            game.updated_at = now_iso()
            deps.store.save(game)
            return deps.present(game)
        candidate = record.get('peer_preview')
        if not candidate or candidate['doctrine_id'] != doctrine_id or candidate['id'] != npc_id:
            raise ValueError('这位同道已离开，请重新寻访')
        if action == 'retain_peer':
            if len(record.get('daomen', {}).get(doctrine_id, [])) >= 9:
                raise ValueError('本门已结识九位同道')
            if not remove_item(game.player, 'spirit_stone', config()['cultivation']['explore_price']):
                raise ValueError('结交同道所需灵石不足')
            npc = discover(game, doctrine_id, definition, WORLD_SYSTEMS['transcendent_combat'], config()['words'], candidate)
            summary = f"结识{npc.name}，其道统修为为 Lv{candidate['level']}。"
        else:
            summary = '与访客辞别，尚未将其列入往来名单。'
        record.pop('peer_preview', None)
    elif action in {"annotation", "teach_manual"}:
        npc = mentor(game, doctrine_id, npc_id)
        if not definition or not _known(game, doctrine_id):
            raise ValueError("尚未取得此门传承")
        mastery = npc.transcendence["doctrine"]["progress"][doctrine_id]["level"]
        if action == "annotation":
            target = record["progress"][doctrine_id]["level"] + 1
            if target > 9 or mastery < target:
                raise ValueError("这位同道尚不能指点目标层次")
            notes = record.setdefault("annotations", {}).setdefault(doctrine_id, [])
            if target in notes:
                raise ValueError("已有此层注解，无需重复索取")
            if not remove_item(game.player, "spirit_stone", config()["cultivation"]["annotation_price"] * target):
                raise ValueError("请教所需灵石不足")
            notes.append(target)
            summary = f"{npc.name}传授《{definition['name']}》Lv{target} 注解，今后可反复参阅。"
        else:
            book = next((t for t in game.player.known_techniques if t.id == manual_id and t.doctrine_id == doctrine_id), None)
            if (not book or book.level >= 9 or mastery <= book.level
                    or book.id not in {b['id'] for b in definition['manuals']}):
                raise ValueError("这位同道不能指导这部功法的下一等级")
            if not remove_item(game.player, "spirit_stone", config()["cultivation"]["annotation_price"] * (book.level + 1) ** 2):
                raise ValueError("请教所需灵石不足")
            add_technique_copy(game.player, book, level=book.level)
            summary = f"{npc.name}交付《{book.name}》Lv{book.level} 功法玉简，可在功法面板合参至下一层，尚未直接升级。"
    elif action == 'convert':
        from .conversion import quote as conversion_quote
        bill = conversion_quote(game)
        if game.player.sealed_cultivation or game.player.cultivation_suppression:
            raise ValueError('修为受压制，不能推进仙灵力转化')
        if not bill['can_convert']:
            raise ValueError('仙灵力已完成转化或机缘不足')
        game.player.opportunity -= bill['cost']
        record['conversion_active'] = True
        record['conversion_progress'] = 0
        _, summary = deps._complete_immortal_conversion_stage(game, bill['stage'] + 1)
        summary += f" 消耗机缘 {bill['cost']}。"
    elif action == "study":
        if action == "study":
            record["study_target"] = doctrine_id
        operation = "doctrine_study" if action == "study" else "immortal_conversion"
        deps._begin_doctrine_action(game, operation)
        deps.store.save(game)
        return deps.advance(game_id, operation, 1)
    elif action in {"activate", "origin"}:
        if not definition or not _known(game, doctrine_id):
            raise ValueError("尚未获得此道统传承")
        if action == "origin":
            if confirm_origin is not True:
                raise ValueError("须明确确认本源唯一归属")
            record["study_target"] = doctrine_id
            progress = record["progress"].get(doctrine_id, {})
            prerequisites(record, doctrine_id, max(t.level for t in game.player.known_techniques if t.doctrine_id == doctrine_id))
            if (record.get("origin") or progress.get("level") != 4
                    or progress.get("experience", 0) < definition["stages"][4]["years"]
                    or game.player.realm_index < definition["stages"][4]["realm"]):
                raise ValueError("须将道统修至 Lv4，并备齐 Lv5 积累后选择唯一本源")
            record["origin"] = doctrine_id
            roll = rng_for(game.seed, game.doctrine_state["version"], f"study:{doctrine_id}:{progress.get('attempts', 0)}").random()
            result = attempt(progress, definition, 0, doctrine_id, config()["cultivation"], roll)
            summary = f"本源归于《{definition['name']}》；Lv5 突破{'成功' if result == 'success' else '失败，注解保底已增加'}，其余道统至多 Lv4。"
        else:
            if record["progress"].get(doctrine_id, {}).get("level", 0) < 4:
                raise ValueError("Lv4 才能激发该道统仙域")
            record["active"] = doctrine_id
            summary = f"斗法时采用《{definition['name']}》的仙域。"
    else:
        raise ValueError("未知道统操作")
    game.history.append(HistoryRecord("SYS_DOCTRINE_ACTION", 1, game.player.age, "道统传承",
                                     doctrine_id or manual_id, action, summary, {}, ["system", "doctrine"]))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def _public_doctrines(deps: DoctrineViewDependencies, game):
    if game.player.world != "celestial" or game.player.realm_index < 9:
        return {"available": False}
    ensure(game)
    if not game.doctrine_state:
        return {"available": False}
    state, record = game.doctrine_state, player_record(game)
    known = {t.id: t for t in game.player.known_techniques}
    rows = []
    for key, definition in state["definitions"].items():
        books = [b for b in definition["manuals"] if b["id"] in known]
        fused = known.get(fusion_manual_id(key))
        if fused:
            books.append({'id':fused.id, 'name':fused.name, 'grade':fused.grade})
        progress = record["progress"].get(key, {"level": 0, "experience": 0})
        level = progress["level"]
        visible = definition["stages"][:min(9, level + 1)] if books else []
        stages = []
        for stage in visible:
            # Explicit whitelist; never send the hidden catalog/seed blueprint.
            voisinage = stage["voisinage"]
            if voisinage and record.get('fusion', {}).get(key, {}).get('level', 0):
                from dataclasses import asdict
                from .combat.contracts import VoisinageDefinition
                from .doctrine.fusion import project as project_fusion
                voisinage = asdict(project_fusion(VoisinageDefinition(**voisinage),
                    min(stage['level'], record['fusion'][key]['level'])))
            stages.append({"level": stage["level"], "title": stage["title"], "years": stage["years"],
                           "realm_name": REALMS[stage["realm"]].name, "description": stage["description"],
                           "features": stage["features"], "ability_name": stage["ability_name"],
                           "voisinage": ({k: voisinage[k] for k in ("name", "stability", "incursion", "authority", "opening_cost",
                                      "upkeep_cost", "effect_cost", "effect", "max_targets")} if voisinage else None)})
        next_stage = definition["stages"][level] if level < 9 else None
        blocked = level >= 4 and record.get("origin") not in (None, key)
        manual_level = max((known[b["id"]].level for b in books), default=0)
        has_annotation = level + 1 in record.get("annotations", {}).get(key, [])
        qualified = manual_level >= level + 1 and has_annotation
        rows.append(dict(id=key, name=definition["name"], description=definition["description"], learned=bool(books),
                         fusion=deps._public_fusion(game, definition),
                         level=level, experience=progress["experience"], stages=stages,
                         manual_level=manual_level, has_annotation=has_annotation,
                         chance=chance(progress, config()["cultivation"]),
                         pity_step=config()["cultivation"]["pity_steps"][min(8, level)],
                         annotations=record.get("annotations", {}).get(key, []),
                         peer_preview=copy.deepcopy(record.get("peer_preview")) if (record.get("peer_preview") or {}).get("doctrine_id") == key else None,
                         peers=public_peers(game, key), explore_progress=record.get("explore_progress", {}).get(key, 0),
                         active=record.get("active") == key, origin=record.get("origin") == key,
                         blocked=blocked, can_train=bool(books and qualified and next_stage and not blocked and game.player.realm_index >= next_stage["realm"]
                            and not (level == 4 and progress["experience"] >= next_stage["years"] and not record.get("origin"))),
                         can_bind=bool(level == 4 and qualified and not record.get("origin") and progress["experience"] >= definition["stages"][4]["years"]),
                         manuals=[dict(id=b["id"], name=b["name"], grade_name=REALMS[b["grade"]].name,
                                       level=known[b["id"]].level, fused=b['id'] == fusion_manual_id(key)) for b in books]))
    stage = game.player.immortal_conversion_stage
    voisinages = []
    rules = config()["cultivation"]
    for row in rows:
        if row["level"] < 4:
            continue
        definition = source({**record, "active": row["id"]}, state["definitions"], "celestial",
                            training_gain=rules["voisinage_training_gain"]).voisinages[0]
        training = record.get("voisinage_training", {}).get(row["id"], {})
        from .doctrine.voisinage_training import public as public_training
        voisinages.append({"id": row["id"], "name": definition.name, "doctrine": row["name"],
                           "active": row["active"], "level": row["level"],
                           "cultivation": public_training(training, rules),
                           "effects": [dict(kind=e.kind, power=e.power, cost=e.cost) for e in definition.actions()],
                           "opening_cost": definition.opening_cost, "upkeep_cost": definition.upkeep_cost,
                           "effect_cost": definition.effect_cost, "max_targets": definition.max_targets,
                           "max_investment": definition.max_investment,
                           "axes": [{"id": axis, "value": getattr(definition, axis), "rank": training.get(axis, 0),
                                     "cost": training_cost(training.get(axis, 0), rules),
                                     "max": rules["voisinage_max_training"]} for axis in AXES]})
    return dict(available=True, count=25, max_level=9, voisinage_level=4, origin_level=5,
                veins=deps._public_immortal(game), immortal_body=deps._public_immortal_body(game), voisinages=voisinages,
                explore_price=rules["explore_price"], annotation_price=rules["annotation_price"],
                unit_years=WORLD_SYSTEMS["time_units"][str(game.player.realm_index)], rows=rows,
                conversion={**conversion_quote(game), "stage": stage, "complete": game.player.immortal_power_converted,
                            "progress": record.get("conversion_progress", 0),
                            "required": config()["conversion_years"][stage] if stage < 5 else 0,
                            "capacity": game.player.immortal_aperture.get('capacity', 1000),
                            "current": game.player.immortal_aperture.get('current', 0)},
                offers=[dict(id=b["id"], name=b["name"], doctrine_name=state["definitions"][b["doctrine_id"]]["name"],
                             origin=state["definitions"][b["doctrine_id"]].get("manual_origins", {}).get(b["id"], "传承玉简"),
                             grade_name=REALMS[b["grade"]].name, price=_price(b), owned=b["id"] in known,
                             stats={k: b[k] for k in ("opportunity_bonus", "hp_bonus", "mp_bonus", "combat_bonus")}) for b in _offers(game)])

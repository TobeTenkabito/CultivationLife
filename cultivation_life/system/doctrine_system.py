"""Application service: acquisition, explicit training, conversion and redacted UI."""
from __future__ import annotations

import copy

from ..content_registry import REALMS, WORLD_SYSTEMS
from ..models import HistoryRecord, Technique
from ..rules import learn_technique, add_technique_copy, remove_item, max_mp
from ..runtime import now_iso
from .doctrine.generation import rng_for
from .doctrine.progression import bind_origin, train
from .doctrine.provider import config, ensure, player_record


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


class DoctrineSystemMixin:
    def _ensure_doctrines(self, game):
        return ensure(game)

    def _begin_doctrine_action(self, game, action):
        if action not in {"doctrine_study", "immortal_conversion"}:
            return
        if game.player.world != "celestial" or game.player.realm_index < 9:
            raise ValueError("道统与仙灵力转化须在仙界、真仙境界开始")
        ensure(game)
        record = player_record(game)
        if action == "immortal_conversion":
            if game.player.immortal_power_converted:
                raise ValueError("仙灵力已完成转化")
            record["conversion_active"] = True
            return
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
        if game.player.realm_index < stage["realm"]:
            raise ValueError(f"下一阶段须达到{REALMS[stage['realm']].name}")
        if level == 4 and progress["experience"] >= stage["years"] and not record.get("origin"):
            raise ValueError("本源积累已满，请明确选择本源归属后突破")

    def _finish_doctrine_action(self, game, action, elapsed):
        if (action not in {"doctrine_study", "immortal_conversion"} or elapsed <= 0
                or not game.player.alive or game.player.world != "celestial"):
            return
        record = player_record(game)
        if action == "immortal_conversion":
            record["conversion_progress"] = record.get("conversion_progress", 0) + elapsed
            completed = []
            for _ in range(5):
                stage = game.player.immortal_conversion_stage
                if stage >= 5:
                    record["conversion_progress"] = 0
                    break
                cost = config()["conversion_years"][stage]
                if record["conversion_progress"] < cost:
                    break
                record["conversion_progress"] -= cost
                self._complete_immortal_conversion_stage(game, stage + 1)
                completed.append(stage + 1)
            if game.player.immortal_power_converted:
                record["conversion_progress"] = 0
            message = (f"转化修炼 {elapsed:g} 年，现完成 {game.player.immortal_conversion_stage}/5 阶段。"
                       "转化提升了可调用的仙灵力。")
            key = "conversion"
        else:
            key = record["study_target"]
            definition = game.doctrine_state["definitions"][key]
            completed = train(record["progress"][key], definition, elapsed, game.player.realm_index, record.get("origin"))
            message = f"参悟《{definition['name']}》{elapsed:g} 年，现为 Lv{record['progress'][key]['level']}。"
            if completed:
                message += definition["stages"][completed[-1] - 1]["description"]
            if record["progress"][key]["level"] >= 4 and not record.get("active"):
                record["active"] = key
        game.history.append(HistoryRecord("SYS_DOCTRINE_TRAIN", 1, game.player.age, "仙道修持", key,
                                         "trained", message, {"levels": completed}, ["system", "doctrine"]))

    def doctrine_action(self, game_id, action, doctrine_id=None, manual_id=None, confirm_origin=False):
        game = self._load(game_id)
        if game.player.world != "celestial" or game.player.realm_index < 9:
            raise ValueError("道统只在仙界生效，须达到真仙境界")
        if not game.player.alive or game.pending_event or game.active_trial or game.player.imprisonment:
            raise ValueError("当前状态无法修持道统")
        ensure(game)
        record = player_record(game)
        definition = game.doctrine_state["definitions"].get(doctrine_id)
        if action == "buy":
            book = next((b for b in _offers(game) if b["id"] == manual_id), None)
            if not book:
                raise ValueError("这部传承当前不在仙界书市中")
            if not remove_item(game.player, "spirit_stone", _price(book)):
                raise ValueError("灵石不足")
            technique = Technique(**copy.deepcopy(book))
            if not learn_technique(game.player, technique):
                add_technique_copy(game.player, technique)
            record["progress"].setdefault(book["doctrine_id"], {"level": 0, "experience": 0})
            summary = f"获得《{book['name']}》，承接《{game.doctrine_state['definitions'][book['doctrine_id']]['name']}》。"
        elif action in {"study", "convert"}:
            if action == "study":
                record["study_target"] = doctrine_id
            operation = "doctrine_study" if action == "study" else "immortal_conversion"
            self._begin_doctrine_action(game, operation)
            self.store.save(game)
            return self.advance(game_id, operation, 1)
        elif action in {"activate", "origin"}:
            if not definition or not _known(game, doctrine_id):
                raise ValueError("尚未获得此道统传承")
            if action == "origin":
                if confirm_origin is not True:
                    raise ValueError("须明确确认本源唯一归属")
                bind_origin(record, definition, game.player.realm_index)
                summary = f"本源归于《{definition['name']}》，突破 Lv5；其余道统至多修炼至 Lv4。"
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
        self.store.save(game)
        return self.present(game)

    def _public_doctrines(self, game):
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
            progress = record["progress"].get(key, {"level": 0, "experience": 0})
            level = progress["level"]
            visible = definition["stages"][:min(9, level + 1)] if books else []
            stages = []
            for stage in visible:
                # Explicit whitelist; never send the hidden catalog/seed blueprint.
                domain = stage["domain"]
                stages.append({"level": stage["level"], "title": stage["title"], "years": stage["years"],
                               "realm_name": REALMS[stage["realm"]].name, "description": stage["description"],
                               "features": stage["features"], "ability_name": stage["ability_name"],
                               "domain": ({k: domain[k] for k in ("name", "stability", "incursion", "authority", "opening_cost",
                                          "upkeep_cost", "effect_cost", "effect", "max_targets")} if domain else None)})
            next_stage = definition["stages"][level] if level < 9 else None
            blocked = level >= 4 and record.get("origin") not in (None, key)
            rows.append(dict(id=key, name=definition["name"], description=definition["description"], learned=bool(books),
                             level=level, experience=progress["experience"], stages=stages,
                             active=record.get("active") == key, origin=record.get("origin") == key,
                             blocked=blocked, can_train=bool(books and next_stage and not blocked and game.player.realm_index >= next_stage["realm"]
                                and not (level == 4 and progress["experience"] >= next_stage["years"] and not record.get("origin"))),
                             can_bind=bool(level == 4 and not record.get("origin") and progress["experience"] >= definition["stages"][4]["years"]),
                             manuals=[dict(id=b["id"], name=b["name"], grade_name=REALMS[b["grade"]].name,
                                           level=known[b["id"]].level) for b in books]))
        stage = game.player.immortal_conversion_stage
        return dict(available=True, count=25, max_level=9, domain_level=4, origin_level=5,
                    unit_years=WORLD_SYSTEMS["time_units"][str(game.player.realm_index)], rows=rows,
                    conversion={"stage": stage, "complete": game.player.immortal_power_converted,
                                "progress": record.get("conversion_progress", 0),
                                "required": config()["conversion_years"][stage] if stage < 5 else 0,
                                "capacity": round(max_mp(game.player) * (1 if game.player.immortal_power_converted else stage / 5)),
                                "current": game.player.mp},
                    offers=[dict(id=b["id"], name=b["name"], doctrine_name=state["definitions"][b["doctrine_id"]]["name"],
                                 origin=state["definitions"][b["doctrine_id"]].get("manual_origins", {}).get(b["id"], "传承玉简"),
                                 grade_name=REALMS[b["grade"]].name, price=_price(b), owned=b["id"] in known,
                                 stats={k: b[k] for k in ("opportunity_bonus", "hp_bonus", "mp_bonus", "combat_bonus")}) for b in _offers(game)])

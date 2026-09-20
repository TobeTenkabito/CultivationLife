from __future__ import annotations

import copy
import random
import uuid
from typing import Any

from .content_registry import CONTENT_DOCUMENTS
from .models import GameState, HistoryRecord
from .runtime import decode_rng, encode_rng


def sage_config() -> dict[str, Any]:
    document = CONTENT_DOCUMENTS.get("sage_way.json", {})
    return document.get("settings", {}) if isinstance(document, dict) else {}


def sage_content_available() -> bool:
    return bool(sage_config().get("enabled", False))


SAGE_EFFECT_LABELS = {
    "breakthrough_bonus": "基础突破概率",
    "combat_multiplier": "战斗力",
    "opportunity_multiplier": "机缘获取",
    "answer_multiplier": "解惑收益",
    "preach_multiplier": "传道影响力",
    "art_experience_multiplier": "百艺经验",
    "sense_multiplier": "神识修炼收益",
    "field_alchemy_multiplier": "灵田生长与炼丹经验",
    "crafting_formation_multiplier": "炼器与阵法收益",
    "technique_learning_multiplier": "功法效果",
}


def sage_effect_text(effects: dict[str, float], scale: float = 1.0) -> list[str]:
    result: list[str] = []
    for key, raw_value in effects.items():
        value = float(raw_value) * scale
        label = SAGE_EFFECT_LABELS.get(key, key)
        amount = value * 100.0
        unit = "个百分点" if key == "breakthrough_bonus" else "%"
        result.append(f"{label} {amount:+g}{unit}")
    return result


def public_sage_choice_details(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    details = config.get("choice_details", {})
    passives = config.get("doctrine_passives", {})
    return {
        str(choice_id): {
            "name": str(spec.get("name", choice_id)),
            "description": str(spec.get("description", "")),
            "effects": copy.deepcopy(passives.get(choice_id, {})),
            "effect_text": sage_effect_text(passives.get(choice_id, {})),
        }
        for choice_id, spec in details.items()
    }


def disciple_curve(active: int, sense_rank: int, config: dict[str, Any] | None = None) -> dict[str, float]:
    rules = config or sage_config()
    n0 = max(1, int(rules.get("disciple_n0_base", 4)) + int(sense_rank) * int(rules.get("disciple_n0_per_sense", 2)))
    n = max(0, int(active))
    bonus = 20.0 * n * (n0 - n) / (n0 * n0)
    return {
        "n0": n0,
        "hard_cap": 3 * n0,
        "breakthrough_pp": max(float(rules.get("disciple_penalty_floor_pp", -8.0)), bonus),
    }


def apply_external_influence(doctrines: list[dict[str, Any]], doctrine_id: str, delta: float,
                             config: dict[str, Any] | None = None) -> float:
    """Apply one ordered influence delta while preserving the shared 100-point pool."""
    rules = config or sage_config()
    floor = float(rules.get("influence_floor", 0.1))
    cap = float(rules.get("doctrine_influence_cap", 60.0))
    pool = float(rules.get("world_influence_pool", 100.0))
    target = next((row for row in doctrines if row.get("id") == doctrine_id), None)
    if target is None:
        return 0.0
    before = float(target.get("external", 0.0))
    wanted = max(floor, min(cap, before + float(delta)))
    if wanted <= before:
        target["external"] = round(wanted, 4)
        return target["external"] - before
    growth = wanted - before
    spare = max(0.0, pool - sum(float(row.get("external", 0.0)) for row in doctrines))
    direct = min(growth, spare)
    target["external"] = before + direct
    remaining = growth - direct
    if remaining > 0:
        donors = [row for row in doctrines if row is not target and float(row.get("external", 0.0)) > floor]
        available = sum(float(row.get("external", 0.0)) - floor for row in donors)
        taken = min(remaining, available)
        if taken > 0 and available > 0:
            for donor in donors:
                room = float(donor.get("external", 0.0)) - floor
                donor["external"] = round(float(donor.get("external", 0.0)) - taken * room / available, 4)
            target["external"] += taken
    target["external"] = round(min(cap, target["external"]), 4)
    overflow = sum(float(row.get("external", 0.0)) for row in doctrines) - pool
    if overflow > 0:
        reducer = max(doctrines, key=lambda row: float(row.get("external", 0.0)) - floor)
        reducer["external"] = max(floor, float(reducer.get("external", 0.0)) - overflow)
    return target["external"] - before


class SageSystemMixin:
    def _ensure_sage_state(self, game: GameState) -> bool:
        if not sage_content_available():
            game.player.sage_effects = {}
            return False
        if game.sage_state.get("version") == 1:
            return False
        cfg = sage_config()
        worlds: dict[str, Any] = {}
        for world in cfg.get("worlds", ["human", "spirit"]):
            presets = copy.deepcopy(cfg.get("initial_doctrines", {}).get(world, []))
            for row in presets:
                row.setdefault("protection_until", game.player.age + int(cfg.get("protection_years", 10)))
                row.setdefault("sage_id", "confucius")
                row.setdefault("sage_cooldown_until", 0)
                row.setdefault("extinct_years", 0)
                row.setdefault("active_disciples", [])
                row.setdefault("graduates", 0)
            worlds[str(world)] = {"doctrines": presets, "ai_found_cooldown_until": 0}
        game.sage_state = {
            "version": 1, "worlds": worlds, "memberships": {}, "quit_cooldown_until": {},
            "recruit_enabled": True, "active_action": None, "action_result": {},
            "total_graduated": 0, "unlocked_sages": ["confucius"],
            "future_hooks": {"faction_ref": None, "tags": []},
        }
        self._refresh_sage_effects(game)
        return True

    def _sage_world(self, game: GameState, world: str | None = None) -> dict[str, Any] | None:
        self._ensure_sage_state(game)
        return game.sage_state.get("worlds", {}).get(world or game.player.world)

    def _player_doctrine(self, game: GameState, world: str | None = None) -> dict[str, Any] | None:
        target_world = world or game.player.world
        state = self._sage_world(game, target_world)
        doctrine_id = game.sage_state.get("memberships", {}).get(target_world)
        return next((row for row in (state or {}).get("doctrines", []) if row.get("id") == doctrine_id), None)

    @staticmethod
    def _rank_members(doctrine: dict[str, Any]) -> list[dict[str, Any]]:
        return sorted(doctrine.get("members", []), key=lambda row: float(row.get("inner", 0.0)), reverse=True)

    def _refresh_sage_effects(self, game: GameState) -> None:
        player = game.player
        if not sage_content_available() or player.world not in sage_config().get("worlds", []):
            player.sage_effects = {}
            return
        doctrine = self._player_doctrine(game, player.world) if game.sage_state.get("version") == 1 else None
        if not doctrine:
            player.sage_effects = {}
            return
        active = len(doctrine.get("active_disciples", []))
        curve = disciple_curve(active, player.divine_sense_rank)
        effects: dict[str, float] = {"breakthrough_bonus": curve["breakthrough_pp"] / 100.0}
        combo = doctrine.get("combo", {})
        passives = sage_config().get("doctrine_passives", {})
        for choice in combo.values():
            for key, value in passives.get(choice, {}).items():
                effects[key] = effects.get(key, 0.0) + float(value)
        sage = sage_config().get("sages", {}).get(doctrine.get("sage_id"), {})
        compatible = sage.get("compatible", [])
        sage_scale = 1.0 if "*" in compatible or any(choice in compatible for choice in combo.values()) else 0.5
        for key, value in sage.get("effects", {}).items():
            effects[key] = effects.get(key, 0.0) + float(value) * sage_scale
        effects["breakthrough_bonus"] = max(-0.08, min(0.05, effects.get("breakthrough_bonus", 0.0)))
        player.sage_effects = effects

    def _prepare_sage_action(self, game: GameState, action: str) -> None:
        if action not in {"sage_preach", "sage_teach", "sage_answer"}:
            return
        if not sage_content_available() or game.player.path != "confucian" or game.player.world not in sage_config().get("worlds", []):
            raise ValueError("只有人界或灵界的儒修可以进行圣人教化")
        if not self._player_doctrine(game):
            raise ValueError("请先加入或创立一个学说")
        game.sage_state["active_action"] = action
        game.sage_state["action_result"] = {"years": 0, "external": 0.0, "inner": 0.0, "graduated": 0}

    def _finish_sage_action(self, game: GameState) -> None:
        if not sage_content_available() or game.sage_state.get("version") != 1:
            return
        game.sage_state["active_action"] = None
        self._refresh_sage_effects(game)

    def _advance_sage_year(self, game: GameState, rng: random.Random) -> list[str]:
        if not sage_content_available():
            return []
        self._ensure_sage_state(game)
        cfg = sage_config()
        news: list[str] = []
        for world, world_state in game.sage_state["worlds"].items():
            doctrines = world_state.get("doctrines", [])
            for doctrine in doctrines:
                for member in doctrine.get("members", []):
                    if member.get("is_player") and world != game.player.world:
                        member["frozen"] = True
                        continue
                    member.pop("frozen", None)
                    member["inner"] = round(max(0.0, float(member.get("inner", 0.0)) * (1.0 - float(cfg.get("inner_decay", 0.03)))), 4)
                    if not member.get("is_player"):
                        member["inner"] = round(member["inner"] + 0.12 * (1 + int(member.get("realm_index", 0))), 4)
                if float(doctrine.get("external", 0.0)) <= float(cfg.get("extinction_threshold", 3.0)):
                    doctrine["extinct_years"] = int(doctrine.get("extinct_years", 0)) + 1
                else:
                    doctrine["extinct_years"] = 0
            # Deterministic AI competition is applied in shuffled order.
            updates = [(row["id"], rng.uniform(-0.16, 0.36)) for row in doctrines]
            rng.shuffle(updates)
            for doctrine_id, delta in updates:
                apply_external_influence(doctrines, doctrine_id, delta, cfg)
            extinct_years = int(cfg.get("extinction_years", 20))
            removed = [row for row in doctrines if int(row.get("extinct_years", 0)) >= extinct_years]
            for row in sorted(removed, key=lambda entry: float(entry.get("external", 0.0))):
                if len(doctrines) <= 1:
                    break
                doctrines.remove(row)
                if game.sage_state.get("memberships", {}).get(world) == row.get("id"):
                    game.sage_state["memberships"].pop(world, None)
            if (
                len(doctrines) < int(cfg.get("max_doctrines", 5))
                and game.player.age >= int(world_state.get("ai_found_cooldown_until", 0))
                and (not doctrines or rng.random() < float(cfg.get("ai_found_chance_per_year", 0.005)))
            ):
                choices = cfg.get("combination_choices", {})
                combo = {key: rng.choice(values) for key, values in choices.items()}
                combo_key = "|".join(combo[key] for key in choices)
                if not any(row.get("combo_key") == combo_key for row in doctrines):
                    seq = int(world_state.get("ai_sequence", 0)) + 1
                    world_state["ai_sequence"] = seq
                    new_doctrine = {
                        "id": f"sage-ai-{world}-{seq}", "name": f"新学{seq}", "combo": combo,
                        "combo_key": combo_key, "external": float(cfg.get("influence_floor", 0.1)),
                        "founded_year": game.player.age, "protection_until": game.player.age + int(cfg.get("protection_years", 10)),
                        "extinct_years": 0, "sage_id": "confucius", "sage_cooldown_until": 0,
                        "controller_id": f"sage-ai-{world}-{seq}-master",
                        "members": [{"id":f"sage-ai-{world}-{seq}-master","name":f"游儒{seq}","inner":10.0,"realm_index":3}],
                        "active_disciples": [], "graduates": 0,
                    }
                    doctrines.append(new_doctrine)
                    apply_external_influence(
                        doctrines, new_doctrine["id"],
                        float(cfg.get("founding_influence", 5.0)) - float(cfg.get("influence_floor", 0.1)), cfg,
                    )
                    world_state["ai_found_cooldown_until"] = game.player.age + int(cfg.get("ai_found_cooldown_years", 50))

        doctrine = self._player_doctrine(game)
        action = game.sage_state.get("active_action")
        if doctrine and action:
            result = game.sage_state.setdefault("action_result", {})
            values = cfg.get("actions", {}).get(action, {})
            external = float(values.get("external", 0.0))
            inner = float(values.get("inner", 0.0))
            if action == "sage_preach":
                external *= 1.0 + float(game.player.sage_effects.get("preach_multiplier", 0.0))
            gained = apply_external_influence(self._sage_world(game)["doctrines"], doctrine["id"], external, cfg)
            if (
                float(doctrine.get("external", 0.0)) >= float(cfg.get("doctrine_influence_cap", 60.0))
                and not doctrine.get("cap_recorded")
            ):
                doctrine["cap_recorded"] = True
                game.history.append(HistoryRecord(
                    "SYS_SAGE_INFLUENCE_CAP", 1, game.player.age, "独树一帜", None, "capped",
                    f"{doctrine['name']}的外在影响力达到本界上限。", {"doctrine_id": doctrine["id"]}, ["sage", "milestone"],
                ))
            member = next((row for row in doctrine.get("members", []) if row.get("is_player")), None)
            if member:
                member["inner"] = round(float(member.get("inner", 0.0)) + inner, 4)
            result["years"] = int(result.get("years", 0)) + 1
            result["external"] = round(float(result.get("external", 0.0)) + gained, 3)
            result["inner"] = round(float(result.get("inner", 0.0)) + inner, 3)
            if action == "sage_teach":
                for pupil in list(doctrine.get("active_disciples", [])):
                    pupil["progress"] = min(100.0, float(pupil.get("progress", 0.0)) + rng.uniform(8.0, 15.0))
                    if pupil["progress"] >= 100.0:
                        doctrine["active_disciples"].remove(pupil)
                        doctrine["graduates"] = int(doctrine.get("graduates", 0)) + 1
                        game.sage_state["total_graduated"] += 1
                        result["graduated"] = int(result.get("graduated", 0)) + 1
                        game.history.append(HistoryRecord(
                            "SYS_SAGE_DISCIPLE_GRADUATED", 1, game.player.age, "桃李初成", None,
                            "graduated", f"{pupil['name']}学成出师，仍尊你为师。", {"doctrine_id": doctrine["id"]},
                            ["sage", "disciple", "milestone"],
                        ))
                if game.sage_state["total_graduated"] >= 10 and not game.player.milestones.get("sage_ten_graduates"):
                    game.player.milestones["sage_ten_graduates"] = 1
            elif action == "sage_preach" and game.player.realm_index >= 3 and game.sage_state.get("recruit_enabled", True):
                curve = disciple_curve(len(doctrine.get("active_disciples", [])), game.player.divine_sense_rank, cfg)
                if len(doctrine.get("active_disciples", [])) < int(curve["hard_cap"]) and rng.random() < float(cfg.get("recruit_chance_per_year", 0.04)):
                    seq = int(doctrine.get("disciple_sequence", 0)) + 1
                    doctrine["disciple_sequence"] = seq
                    doctrine.setdefault("active_disciples", []).append({"id": f"sage-disciple-{seq}", "name": f"游学弟子{seq}", "progress": 0.0})
                    news.append(f"{game.player.age}岁：一名散修受教，拜入你的门墙。")
            elif action == "sage_answer":
                reward = rng.uniform(0.5, 1.5) * (1.0 + float(game.player.sage_effects.get("answer_multiplier", 0.0)))
                game.player.opportunity += reward
                game.player.divine_sense_experience += reward * 0.5 * (
                    1.0 + float(game.player.sage_effects.get("sense_multiplier", 0.0))
                )

            ranks = self._rank_members(doctrine)
            if ranks:
                current = next((row for row in ranks if row.get("id") == doctrine.get("controller_id")), ranks[0])
                challenger = ranks[0]
                if challenger["id"] != current["id"] and float(challenger.get("inner", 0.0)) >= float(current.get("inner", 0.0)) * float(cfg.get("control_hysteresis", 1.10)):
                    doctrine["controller_id"] = challenger["id"]
                    if challenger.get("is_player"):
                        game.history.append(HistoryRecord(
                            "SYS_SAGE_CONTROL_TAKEN", 1, game.player.age, "道统更替", None,
                            "controlled", f"你以内在影响力执掌了{doctrine['name']}。", {"doctrine_id": doctrine["id"]},
                            ["sage", "milestone"],
                        ))
        self._refresh_sage_effects(game)
        return news

    def sage_doctrine_action(self, game_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        game = self._load(game_id)
        self._ensure_sage_state(game)
        player = game.player
        if not sage_content_available() or player.path != "confucian" or player.world not in sage_config().get("worlds", []):
            raise ValueError("当前无法参与圣人教化")
        state = self._sage_world(game)
        cfg = sage_config()
        current = self._player_doctrine(game)
        if action == "join":
            if current:
                raise ValueError("你已经属于一个学说")
            doctrine = next((row for row in state["doctrines"] if row["id"] == payload.get("doctrine_id")), None)
            if not doctrine:
                raise ValueError("学说不存在")
            if player.age < int(game.sage_state.get("quit_cooldown_until", {}).get(player.world, 0)):
                raise ValueError("退出学说后的十年冷静期尚未结束")
            doctrine.setdefault("members", []).append({"id": "player", "name": player.name, "inner": 5.0, "realm_index": player.realm_index, "is_player": True})
            game.sage_state["memberships"][player.world] = doctrine["id"]
            summary = f"你加入了{doctrine['name']}。"
        elif action == "leave":
            if not current:
                raise ValueError("你尚未加入学说")
            current["members"] = [row for row in current.get("members", []) if not row.get("is_player")]
            if current.get("controller_id") == "player" and current["members"]:
                current["controller_id"] = self._rank_members(current)[0]["id"]
            game.sage_state["memberships"].pop(player.world, None)
            game.sage_state["quit_cooldown_until"][player.world] = player.age + int(cfg.get("quit_cooldown_years", 10))
            summary = f"你退出了{current['name']}，内在影响力归零。"
        elif action == "found":
            if current:
                raise ValueError("请先退出当前学说")
            if player.realm_index < 3:
                raise ValueError("至少达到结丹期方可开宗立说")
            if player.age < int(game.sage_state.get("quit_cooldown_until", {}).get(player.world, 0)):
                raise ValueError("退出学说后的十年冷静期尚未结束")
            combo = payload.get("combo", {})
            choices = cfg.get("combination_choices", {})
            if set(combo) != set(choices) or any(combo[key] not in choices[key] for key in choices):
                raise ValueError("四层学说组合不完整")
            key = "|".join(combo[layer] for layer in choices)
            if any(row.get("combo_key") == key for row in state["doctrines"]):
                raise ValueError("本界已有完全相同的学说")
            if len(state["doctrines"]) >= int(cfg.get("max_doctrines", 5)):
                eligible = [row for row in state["doctrines"] if float(row.get("external", 0)) < float(cfg.get("replacement_threshold", 5.0)) and player.age >= int(row.get("protection_until", 0))]
                if not eligible:
                    raise ValueError("本界五家学说皆受保护或影响稳固，暂不可立说")
                state["doctrines"].remove(min(eligible, key=lambda row: float(row.get("external", 0))))
            name = str(payload.get("name", "新学")).strip()[:12] or "新学"
            doctrine = {
                "id": f"sage-{uuid.uuid4().hex[:10]}", "name": name, "combo": dict(combo), "combo_key": key,
                "external": float(cfg.get("influence_floor", 0.1)), "founded_year": player.age,
                "protection_until": player.age + int(cfg.get("protection_years", 10)), "extinct_years": 0,
                "sage_id": "confucius", "sage_cooldown_until": 0, "controller_id": "player",
                "members": [{"id": "player", "name": player.name, "inner": 10.0, "realm_index": player.realm_index, "is_player": True}],
                "active_disciples": [], "graduates": 0, "faction_ref": None, "tags": [],
            }
            state["doctrines"].append(doctrine)
            apply_external_influence(
                state["doctrines"], doctrine["id"],
                float(cfg.get("founding_influence", 5.0)) - float(cfg.get("influence_floor", 0.1)), cfg,
            )
            game.sage_state["memberships"][player.world] = doctrine["id"]
            game.history.append(HistoryRecord(
                "SYS_SAGE_DOCTRINE_FOUNDED", 1, player.age, "开宗立说", None, "founded",
                f"你在人间立下{name}，四层宗旨自成一家。", {"doctrine_id": doctrine["id"]}, ["sage", "milestone"],
            ))
            summary = f"{name}立说成功，获得 {cfg.get('founding_influence', 5)} 点外在影响力。"
        else:
            raise ValueError("未知学说操作")
        self._refresh_sage_effects(game)
        self.store.save(game)
        result = self.present(game)
        result["action_summary"] = summary
        return result

    def sage_toggle_recruitment(self, game_id: str, enabled: bool) -> dict[str, Any]:
        game = self._load(game_id)
        self._ensure_sage_state(game)
        game.sage_state["recruit_enabled"] = bool(enabled)
        self.store.save(game)
        return self.present(game)

    def sage_choose_sage(self, game_id: str, sage_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        self._ensure_sage_state(game)
        doctrine = self._player_doctrine(game)
        if not doctrine:
            raise ValueError("请先加入学说")
        ranks = self._rank_members(doctrine)
        rank = next((i + 1 for i, row in enumerate(ranks) if row.get("is_player")), 999)
        if rank > int(sage_config().get("decision_rank", 3)):
            raise ValueError("只有内在影响力前三名可以提议改祀")
        if game.player.age < int(doctrine.get("sage_cooldown_until", 0)):
            raise ValueError("改祀冷却尚未结束")
        if sage_id not in sage_config().get("sages", {}):
            raise ValueError("未知先贤")
        controller = next((row for row in ranks if row.get("id") == doctrine.get("controller_id")), ranks[0])
        accepted = bool(controller.get("is_player"))
        if not accepted:
            proposer = next(row for row in ranks if row.get("is_player"))
            chance = max(0.15, min(0.85, float(proposer.get("inner", 0.0)) / max(1.0, float(controller.get("inner", 0.0))) * 0.55))
            rng = decode_rng(game.seed, game.rng_state)
            accepted = rng.random() < chance
            game.rng_state = encode_rng(rng)
        if not accepted:
            doctrine["sage_cooldown_until"] = game.player.age + 5
            game.history.append(HistoryRecord(
                "SYS_SAGE_CHANGED", 1, game.player.age, "改祀未决", sage_id, "rejected",
                f"{doctrine['name']}的执掌者驳回了你的改祀提议。", {"doctrine_id": doctrine["id"]}, ["sage"],
            ))
            self.store.save(game)
            result = self.present(game)
            result["action_summary"] = "改祀提议未获通过，五年内不可再议。"
            return result
        doctrine["sage_id"] = sage_id
        doctrine["sage_cooldown_until"] = game.player.age + int(sage_config().get("sage_change_cooldown_years", 10))
        game.history.append(HistoryRecord(
            "SYS_SAGE_CHANGED", 1, game.player.age, "受祀有灵", sage_id, "changed",
            f"{doctrine['name']}改祀{sage_config()['sages'][sage_id]['name']}。", {"doctrine_id": doctrine["id"]}, ["sage", "milestone"],
        ))
        self._refresh_sage_effects(game)
        self.store.save(game)
        return self.present(game)

    def _public_sage_system(self, game: GameState) -> dict[str, Any]:
        enabled = sage_content_available()
        if enabled:
            self._ensure_sage_state(game)
        available = enabled and game.player.path == "confucian" and game.player.world in sage_config().get("worlds", [])
        state = self._sage_world(game) if available else None
        current = self._player_doctrine(game) if available else None
        cfg = sage_config()
        choice_details = public_sage_choice_details(cfg)
        sages = copy.deepcopy(cfg.get("sages", {}))
        for sage in sages.values():
            sage["effect_text"] = sage_effect_text(sage.get("effects", {}))
            sage["reduced_effect_text"] = sage_effect_text(sage.get("effects", {}), 0.5)
            sage["compatible_names"] = [
                "所有学说" if choice == "*" else choice_details.get(str(choice), {}).get("name", str(choice))
                for choice in sage.get("compatible", [])
            ]
            combo_values = set((current or {}).get("combo", {}).values())
            sage["compatible_current"] = bool(
                "*" in sage.get("compatible", []) or combo_values.intersection(sage.get("compatible", []))
            )
            sage["applied_effect_text"] = (
                sage["effect_text"] if sage["compatible_current"] else sage["reduced_effect_text"]
            )
        doctrines = []
        for row in (state or {}).get("doctrines", []):
            ranks = self._rank_members(row)
            combo_details = [choice_details.get(str(choice), {"name": str(choice), "effect_text": []}) for choice in row.get("combo", {}).values()]
            doctrines.append({
                **copy.deepcopy(row), "members": ranks,
                "player_rank": next((i + 1 for i, member in enumerate(ranks) if member.get("is_player")), None),
                "combo_details": copy.deepcopy(combo_details),
                "passive_effect_text": [text for detail in combo_details for text in detail.get("effect_text", [])],
            })
        return {
            "installed": enabled, "available": available, "world": game.player.world,
            "doctrines": doctrines, "membership_id": current.get("id") if current else None,
            "recruit_enabled": bool(game.sage_state.get("recruit_enabled", True)) if enabled else False,
            "combination_choices": copy.deepcopy(cfg.get("combination_choices", {})),
            "choice_details": choice_details,
            "sages": sages,
            "disciple_curve": disciple_curve(len(current.get("active_disciples", [])), game.player.divine_sense_rank) if current else None,
            "effects": dict(game.player.sage_effects),
            "effect_text": sage_effect_text(game.player.sage_effects),
            "last_action": copy.deepcopy(game.sage_state.get("action_result", {})) if enabled else {},
        }

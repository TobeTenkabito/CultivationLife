from __future__ import annotations

import copy
import random
import uuid
from typing import Any

from .content_registry import CONTENT_DOCUMENTS
from .models import GameState, HistoryRecord
from .rules import REALMS, expected_combat_power
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
    @staticmethod
    def _normalize_sage_member(member: dict[str, Any]) -> None:
        member.setdefault("path", "confucian")
        member.setdefault("layer", 1)
        if "combat_factor" not in member:
            seed = sum(ord(char) for char in str(member.get("id", "儒生")))
            member["combat_factor"] = round(0.78 + (seed % 25) / 100.0, 2)

    def _normalize_sage_doctrine(self, doctrine: dict[str, Any], age: int, cfg: dict[str, Any]) -> None:
        doctrine.setdefault("protection_until", age + int(cfg.get("protection_years", 10)))
        doctrine.setdefault("sage_id", "confucius")
        doctrine.setdefault("sage_cooldown_until", 0)
        doctrine.setdefault("extinct_years", 0)
        doctrine.setdefault("active_disciples", [])
        doctrine.setdefault("graduates", 0)
        members = []
        for member in doctrine.setdefault("members", []):
            self._normalize_sage_member(member)
            if member.get("is_player") or member.get("path") == "confucian":
                members.append(member)
        doctrine["members"] = members
        if members and not any(row.get("id") == doctrine.get("controller_id") for row in members):
            doctrine["controller_id"] = max(members, key=lambda row: float(row.get("inner", 0.0)))["id"]

    def _ensure_sage_state(self, game: GameState) -> bool:
        if not sage_content_available():
            game.player.sage_effects = {}
            return False
        cfg = sage_config()
        version = int(game.sage_state.get("version", 0) or 0)
        if version in {1, 2}:
            for world_state in game.sage_state.get("worlds", {}).values():
                for doctrine in world_state.get("doctrines", []):
                    self._normalize_sage_doctrine(doctrine, game.player.age, cfg)
            game.sage_state.setdefault("debate_cooldowns", {})
            game.sage_state["version"] = 2
            if version == 1:
                self._refresh_sage_effects(game)
            return False
        worlds: dict[str, Any] = {}
        for world in cfg.get("worlds", ["human", "spirit"]):
            presets = copy.deepcopy(cfg.get("initial_doctrines", {}).get(world, []))
            for row in presets:
                self._normalize_sage_doctrine(row, game.player.age, cfg)
            worlds[str(world)] = {"doctrines": presets, "ai_found_cooldown_until": 0}
        game.sage_state = {
            "version": 2, "worlds": worlds, "memberships": {}, "quit_cooldown_until": {},
            "recruit_enabled": True, "active_action": None, "action_result": {},
            "total_graduated": 0, "unlocked_sages": ["confucius"],
            "debate_cooldowns": {},
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
        controller_id = doctrine.get("controller_id")
        return sorted(
            doctrine.get("members", []),
            key=lambda row: (row.get("id") != controller_id, -float(row.get("inner", 0.0))),
        )

    def _refresh_sage_effects(self, game: GameState) -> None:
        player = game.player
        if not sage_content_available() or player.world not in sage_config().get("worlds", []):
            player.sage_effects = {}
            return
        doctrine = self._player_doctrine(game, player.world) if game.sage_state.get("version") == 2 else None
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
        if not sage_content_available() or game.sage_state.get("version") != 2:
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
                        "members": [{"id":f"sage-ai-{world}-{seq}-master","name":f"游儒{seq}","inner":10.0,"realm_index":3,"layer":1,"path":"confucian","combat_factor":0.9}],
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
            inner = float(values.get("inner", 0.0)) * (
                1.0 + game.player.realm_index * float(cfg.get("inner_realm_scale_per_realm", 0.08))
            )
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
                    f"{doctrine['name']}的学说声望达到本界上限。", {"doctrine_id": doctrine["id"]}, ["sage", "milestone"],
                ))
            member = next((row for row in doctrine.get("members", []) if row.get("is_player")), None)
            if member:
                member["inner"] = round(float(member.get("inner", 0.0)) + inner, 4)
            result["years"] = int(result.get("years", 0)) + 1
            result["external"] = round(float(result.get("external", 0.0)) + gained, 3)
            result["inner"] = round(float(result.get("inner", 0.0)) + inner, 3)
            if action == "sage_teach":
                for pupil in list(doctrine.get("active_disciples", [])):
                    progress = rng.uniform(
                        float(cfg.get("teaching_progress_min", 8.0)),
                        float(cfg.get("teaching_progress_max", 15.0)),
                    ) + game.player.divine_sense_rank * float(cfg.get("teaching_progress_per_sense", 0.6)) \
                        + game.player.realm_index * float(cfg.get("teaching_progress_per_realm", 0.35))
                    pupil["progress"] = min(100.0, float(pupil.get("progress", 0.0)) + progress)
                    if pupil["progress"] >= 100.0:
                        doctrine["active_disciples"].remove(pupil)
                        doctrine["graduates"] = int(doctrine.get("graduates", 0)) + 1
                        game.sage_state["total_graduated"] += 1
                        result["graduated"] = int(result.get("graduated", 0)) + 1
                        graduation_inner = float(cfg.get("graduation_inner_gain", 1.5))
                        graduation_external = apply_external_influence(
                            self._sage_world(game)["doctrines"], doctrine["id"],
                            float(cfg.get("graduation_external_gain", 0.5)), cfg,
                        )
                        if member:
                            member["inner"] = round(float(member.get("inner", 0.0)) + graduation_inner, 4)
                        result["inner"] = round(float(result.get("inner", 0.0)) + graduation_inner, 3)
                        result["external"] = round(float(result.get("external", 0.0)) + graduation_external, 3)
                        game.history.append(HistoryRecord(
                            "SYS_SAGE_DISCIPLE_GRADUATED", 1, game.player.age, "桃李初成", None,
                            "graduated", f"{pupil['name']}学成出师，仍尊你为师。", {"doctrine_id": doctrine["id"]},
                            ["sage", "disciple", "milestone"],
                        ))
                if game.sage_state["total_graduated"] >= 10 and not game.player.milestones.get("sage_ten_graduates"):
                    game.player.milestones["sage_ten_graduates"] = 1
            elif action == "sage_preach" and game.player.realm_index >= 3 and game.sage_state.get("recruit_enabled", True):
                curve = disciple_curve(len(doctrine.get("active_disciples", [])), game.player.divine_sense_rank, cfg)
                influence_ratio = float(doctrine.get("external", 0.0)) / max(
                    1.0, float(cfg.get("doctrine_influence_cap", 60.0)),
                )
                recruit_scale = float(cfg.get("recruit_external_scale_min", 0.5)) + (
                    float(cfg.get("recruit_external_scale_max", 2.0))
                    - float(cfg.get("recruit_external_scale_min", 0.5))
                ) * influence_ratio
                recruit_chance = float(cfg.get("recruit_chance_per_year", 0.04)) * recruit_scale
                if len(doctrine.get("active_disciples", [])) < int(curve["hard_cap"]) and rng.random() < recruit_chance:
                    seq = int(doctrine.get("disciple_sequence", 0)) + 1
                    doctrine["disciple_sequence"] = seq
                    doctrine.setdefault("active_disciples", []).append({"id": f"sage-disciple-{seq}", "name": f"游学弟子{seq}", "progress": 0.0})
                    news.append(f"{game.player.age}岁：一名散修受教，拜入你的门墙。")
            elif action == "sage_answer":
                reward = rng.uniform(
                    float(cfg.get("answer_opportunity_min", 0.5)),
                    float(cfg.get("answer_opportunity_max", 1.5)),
                ) * (1.0 + float(game.player.sage_effects.get("answer_multiplier", 0.0)))
                game.player.opportunity += reward
                game.player.divine_sense_experience += reward * float(cfg.get("answer_sense_ratio", 0.5)) * (
                    1.0 + float(game.player.sage_effects.get("sense_multiplier", 0.0))
                )

            influence_order = sorted(
                doctrine.get("members", []), key=lambda row: float(row.get("inner", 0.0)), reverse=True,
            )
            if influence_order:
                current = next(
                    (row for row in influence_order if row.get("id") == doctrine.get("controller_id")),
                    influence_order[0],
                )
                challenger = influence_order[0]
                if challenger["id"] != current["id"] and float(challenger.get("inner", 0.0)) >= float(current.get("inner", 0.0)) * float(cfg.get("control_hysteresis", 1.10)):
                    doctrine["controller_id"] = challenger["id"]
                    if challenger.get("is_player"):
                        game.history.append(HistoryRecord(
                            "SYS_SAGE_CONTROL_TAKEN", 1, game.player.age, "道统更替", None,
                            "controlled", f"你凭门内威望执掌了{doctrine['name']}。", {"doctrine_id": doctrine["id"]},
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
            doctrine.setdefault("members", []).append({
                "id": "player", "name": player.name, "inner": 5.0,
                "realm_index": player.realm_index, "layer": player.layer,
                "path": "confucian", "combat_factor": 1.0, "is_player": True,
            })
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
            summary = f"你退出了{current['name']}，门内威望归零。"
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
                "members": [{
                    "id": "player", "name": player.name, "inner": 10.0,
                    "realm_index": player.realm_index, "layer": player.layer,
                    "path": "confucian", "combat_factor": 1.0, "is_player": True,
                }],
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
            summary = f"{name}立说成功，获得 {cfg.get('founding_influence', 5)} 点学说声望。"
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
            raise ValueError("只有门内威望前三名可以提议改祀")
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

    def sage_debate(self, game_id: str, doctrine_id: str, member_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        self._ensure_sage_state(game)
        player = game.player
        if (
            not sage_content_available() or player.path != "confucian"
            or player.world not in sage_config().get("worlds", [])
        ):
            raise ValueError("只有当前界面的儒修可以论道")
        own_doctrine = self._player_doctrine(game)
        if not own_doctrine:
            raise ValueError("请先加入或创立一个学说")
        state = self._sage_world(game)
        target_doctrine = next(
            (row for row in state.get("doctrines", []) if row.get("id") == doctrine_id), None,
        )
        if not target_doctrine:
            raise ValueError("目标学说不存在")
        member = next(
            (row for row in target_doctrine.get("members", []) if row.get("id") == member_id), None,
        )
        if not member or member.get("is_player"):
            raise ValueError("请选择一名学说中的儒修论道")
        if member.get("path") != "confucian":
            raise ValueError("非儒修不能参与学说论道")
        cfg = sage_config()
        debate_cfg = cfg.get("debate", {})
        cooldowns = game.sage_state.setdefault("debate_cooldowns", {})
        cooldown_key = f"{player.world}:{doctrine_id}:{member_id}"
        next_age = int(cooldowns.get(cooldown_key, 0))
        if player.age < next_age:
            raise ValueError(f"与此人的论道需到 {next_age} 岁后方可再次进行")
        target_realm = max(0, min(len(REALMS) - 1, int(member.get("realm_index", 0))))
        target_layer = max(1, min(REALMS[target_realm].layers, int(member.get("layer", 1))))
        target_power = expected_combat_power(target_realm, target_layer) * max(
            0.25, float(member.get("combat_factor", 1.0)),
        )
        rng = decode_rng(game.seed, game.rng_state)
        result, combat_summary = self._combat(game, {
            "target_name": member["name"],
            "target_power": target_power,
            "target_realm_index": target_realm,
            "combat_type": "cultivator",
            "npc_id": str(member["id"]),
            "action": "sage_debate",
            "loss_scale": float(debate_cfg.get("loss_scale", 0.45)),
        }, False, rng)
        cooldowns[cooldown_key] = player.age + max(1, int(debate_cfg.get("cooldown_years", 1)))
        same_doctrine = target_doctrine.get("id") == own_doctrine.get("id")
        gain = 0.0
        if result == "victory":
            if same_doctrine:
                gain = float(debate_cfg.get("same_doctrine_inner_gain", 1.2))
                player_member = next(
                    (row for row in own_doctrine.get("members", []) if row.get("is_player")), None,
                )
                if player_member:
                    player_member["inner"] = round(float(player_member.get("inner", 0.0)) + gain, 4)
                reward_text = f"门内威望 +{gain:g}"
            else:
                gain = apply_external_influence(
                    state["doctrines"], own_doctrine["id"],
                    float(debate_cfg.get("other_doctrine_external_gain", 0.8)), cfg,
                )
                reward_text = f"{own_doctrine['name']}学说声望 +{gain:.2f}"
        else:
            reward_text = "本次未获得影响力"
        game.history.append(HistoryRecord(
            "SYS_SAGE_DEBATE", 1, player.age, "论道争锋", str(member["id"]), result,
            f"你与{target_doctrine['name']}的{member['name']}论道，{reward_text}。",
            {
                "doctrine_id": target_doctrine["id"], "member_id": member["id"],
                "same_doctrine": same_doctrine, "gain": round(gain, 4),
            }, ["sage", "debate", "combat"],
        ))
        game.rng_state = encode_rng(rng)
        self._refresh_sage_effects(game)
        self.store.save(game)
        shown = self.present(game)
        shown["action_summary"] = f"{combat_summary} {reward_text}。"
        return shown

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
            for member in row.get("members", []):
                if member.get("is_player"):
                    member.update({
                        "name": game.player.name, "realm_index": game.player.realm_index,
                        "layer": game.player.layer, "path": "confucian", "combat_factor": 1.0,
                    })
            ranks = self._rank_members(row)
            public_members = []
            for rank, member in enumerate(ranks, 1):
                realm_index = max(0, min(len(REALMS) - 1, int(member.get("realm_index", 0))))
                layer = max(1, min(REALMS[realm_index].layers, int(member.get("layer", 1))))
                cooldown_key = f"{game.player.world}:{row.get('id')}:{member.get('id')}"
                public_members.append({
                    **copy.deepcopy(member), "rank": rank,
                    "realm_name": f"{REALMS[realm_index].name}{'' if REALMS[realm_index].layers == 1 else f'·{layer}层'}",
                    "combat_power": round(
                        expected_combat_power(realm_index, layer) * max(0.25, float(member.get("combat_factor", 1.0))), 1,
                    ),
                    "role_name": "执掌者" if member.get("id") == row.get("controller_id") else (
                        "议事席" if rank <= int(cfg.get("decision_rank", 3)) else "门人"
                    ),
                    "can_debate": bool(
                        current and not member.get("is_player") and member.get("path") == "confucian"
                        and game.player.age >= int(game.sage_state.get("debate_cooldowns", {}).get(cooldown_key, 0))
                    ),
                    "debate_available_age": int(game.sage_state.get("debate_cooldowns", {}).get(cooldown_key, 0)),
                })
            combo_details = [choice_details.get(str(choice), {"name": str(choice), "effect_text": []}) for choice in row.get("combo", {}).values()]
            doctrines.append({
                **copy.deepcopy(row), "members": public_members,
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
            "action_values": copy.deepcopy(cfg.get("actions", {})),
            "debate_values": copy.deepcopy(cfg.get("debate", {})),
            "numeric_rules": {
                "world_pool": float(cfg.get("world_influence_pool", 100.0)),
                "doctrine_cap": float(cfg.get("doctrine_influence_cap", 60.0)),
                "inner_decay_percent": float(cfg.get("inner_decay", 0.03)) * 100.0,
                "inner_realm_scale_percent": float(cfg.get("inner_realm_scale_per_realm", 0.08)) * 100.0,
                "control_lead_percent": (float(cfg.get("control_hysteresis", 1.10)) - 1.0) * 100.0,
                "recruit_base_percent": float(cfg.get("recruit_chance_per_year", 0.04)) * 100.0,
                "teaching_progress": [
                    float(cfg.get("teaching_progress_min", 8.0)),
                    float(cfg.get("teaching_progress_max", 15.0)),
                ],
            },
        }

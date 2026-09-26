from __future__ import annotations

import copy
import random
from ...content_registry import TECHNIQUE_CATALOG, WORLD_SYSTEMS
from ...models import GameState, HistoryRecord, Player
from ...rules import (
    add_item,
    expected_combat_power,
    effective_karma,
    learn_technique,
    max_hp,
    max_mp,
    public_player,
    qi_level,
)
from ...system.crafting_system import crafted_artifact_bonuses


class EngineTrialsMixin:
    def _resolve_trial_step(self, game: GameState, step: str, rng: random.Random) -> tuple[str, str]:
        player = game.player
        trial = game.active_trial
        if not trial:
            raise ValueError("当前没有进行中的突破或雷劫")
        kind = str(trial["kind"])
        if kind == "heavenly_demon":
            return self._resolve_heavenly_demon_battle(game, step, rng)
        if kind == "celestial_ascension":
            return self._resolve_celestial_ascension_step(game, step, rng)
        if kind == "asura_ascension":
            return self._resolve_asura_ascension_step(game, step, rng)
        passed = False
        detail = ""
        if kind == "traditional":
            config = WORLD_SYSTEMS["breakthrough"]["traditional"]
            target = str(trial["target_realm"])
            if step == "vitality":
                hp_ratio, mp_ratio = player.hp / max_hp(player), player.mp / max_mp(player)
                passed = hp_ratio >= float(config["hp_ratio"]) and mp_ratio >= float(config["mp_ratio"])
                detail = f"HP {hp_ratio:.0%}/{float(config['hp_ratio']):.0%}，MP {mp_ratio:.0%}/{float(config['mp_ratio']):.0%}"
            elif step == "karma":
                limit = float(config["karma_limits"].get(target, 60))
                actual = effective_karma(player)
                passed, detail = actual <= limit, f"有效因果 {actual:.1f}/{limit:.0f}"
            elif step == "heart_demon":
                limit = float(config["heart_demon_limits"].get(target, 25))
                passed, detail = player.heart_demon <= limit, f"心魔 {player.heart_demon:.1f}/{limit:.0f}"
            drain_hp, drain_mp = config["drain_hp"], config["drain_mp"]
        elif kind == "heavenly":
            config = WORLD_SYSTEMS["breakthrough"]["heavenly"]
            if step == "heaven_vitality":
                ratio = (player.hp + player.mp) / (max_hp(player) + max_mp(player))
                passed, detail = ratio >= float(config["vitality_ratio"]), f"HP+MP 总量 {ratio:.0%}/{float(config['vitality_ratio']):.0%}"
            elif step == "heaven_combat":
                threshold = expected_combat_power(int(trial["target_realm"]), 1) * float(config["combat_ratio"])
                actual = self._player_intrinsic_combat_power(player)
                passed, detail = actual >= threshold, f"战斗力 {actual:.0f}/{threshold:.0f}"
            elif step == "heaven_karma":
                actual, limit = effective_karma(player), float(config["karma_limit"])
                passed, detail = actual <= limit, f"有效因果 {actual:.1f}/{limit:.0f}"
            elif step == "heaven_sha":
                active_path = player.technique.path if player.technique else player.path
                if active_path in {"demonic", "ghost"}:
                    passed, detail = True, "魔修或鬼修以煞入道，本关跳过"
                else:
                    limit = float(config["sha_qi_limit"])
                    passed, detail = player.sha_qi <= limit, f"煞气 {player.sha_qi}/{limit:.0f}"
            elif step == "heaven_heart":
                limit = float(config["heart_demon_limit"])
                passed, detail = player.heart_demon <= limit, f"心魔 {player.heart_demon:.1f}/{limit:.0f}"
            drain_hp, drain_mp = config["drain_hp"], config["drain_mp"]
        else:
            config = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
            strike_index = int(step.rsplit("_", 1)[1]) - 1
            multiplier = float(config["strike_multipliers"][strike_index])
            power = float(trial["power"]) * multiplier
            hp_need = max(max_hp(player) * float(config["hp_ratio"]), power * float(config["power_hp_scale"]))
            mp_need = max(max_mp(player) * float(config["mp_ratio"]), power * float(config["power_mp_scale"]))
            passed = player.hp >= hp_need and player.mp >= mp_need
            detail = f"HP {player.hp:.0f}/{hp_need:.0f}，MP {player.mp:.0f}/{mp_need:.0f}，雷威 {power:.0f}"
            drain_hp, drain_mp = config["drain_hp"], config["drain_mp"]

        if not passed:
            gain = self._sage_scaled_gain(
                player, float(WORLD_SYSTEMS["breakthrough"]["trial_failure_heart_demon"]),
                "heart_demon_gain_reduction",
            )
            player.heart_demon += gain
            player.joint_companion_breakthrough = None
            lethal = bool(trial.get("lethal"))
            game.active_trial = None
            if kind == "periodic_thunder":
                player.next_thunder_damage_reduction = 0.0
            if lethal:
                self._die(game, f"未能渡过{self.events_by_id[game.pending_event['id']]['title'] if game.pending_event else '劫难'}", "SYS_TRIAL_FAILED")
                return "dead", f"判定失败（{detail}），心魔 +{gain:g}，你在劫中陨落。"
            return "breakthrough_failed", f"判定失败（{detail}），你保住性命但冲关中止，心魔 +{gain:g}。"

        reduction = self._tribulation_damage_reduction(player, kind) if kind in {"heavenly", "periodic_thunder"} else 0.0
        damage_multiplier = (
            float(WORLD_SYSTEMS["demonic_cultivation"].get("periodic_thunder_damage_multiplier", 1.0))
            if kind == "periodic_thunder" and player.path == "demonic" else 1.0
        )
        hp_loss = max_hp(player) * rng.uniform(*drain_hp) * (1 - reduction) * damage_multiplier
        mp_loss = max_mp(player) * rng.uniform(*drain_mp) * (1 - reduction) * damage_multiplier
        player.hp = max(1.0, player.hp - hp_loss)
        player.mp = max(0.0, player.mp - mp_loss)
        trial["step_index"] = int(trial["step_index"]) + 1
        event_ids = list(trial["event_ids"])
        if trial["step_index"] < len(event_ids):
            next_event = self.events_by_id[event_ids[trial["step_index"]]]
            game.pending_event = self._instantiate_event(next_event, game, rng)
            reduction_text = f"（法宝减伤 {reduction:.0%}）" if reduction else ""
            if damage_multiplier > 1:
                reduction_text += "（魔修承受雷劫伤害 +20%）"
            return "trial_step_success", f"判定通过（{detail}）；劫力消耗 HP {hp_loss:.0f}、MP {mp_loss:.0f}{reduction_text}。"

        old_label = str(trial.get("old_label", public_player(player)["realm_name"]))
        if kind == "periodic_thunder":
            thunder = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
            player.tribulation_count += 1
            player.next_tribulation_age = player.age + int(thunder["interval_years"])
            player.tribulation_power = float(
                trial.get("uncapped_base_power", trial.get("base_power", trial["power"]))
            ) * float(thunder["power_multiplier"])
            player.next_thunder_damage_reduction = 0.0
            game.history.append(HistoryRecord(
                "SYS_PERIODIC_TRIBULATION", 1, player.age, "三千年雷劫", None, "success",
                f"你连续承受三道真雷，渡过第 {player.tribulation_count} 次雷劫；下一劫威力升至 {player.tribulation_power:.0f}。",
                {"tribulation_count": player.tribulation_count, "next_power": player.tribulation_power}, ["system", "tribulation"],
            ))
        elif bool(trial["major"]):
            self._complete_major_breakthrough(game, rng, old_label)
        else:
            self._complete_minor_breakthrough(game, rng, old_label)
        game.active_trial = None
        reduction_text = f"（法宝减伤 {reduction:.0%}）" if reduction else ""
        if damage_multiplier > 1:
            reduction_text += "（魔修承受雷劫伤害 +20%）"
        return "trial_completed", f"最后一道判定通过（{detail}）；劫力消耗 HP {hp_loss:.0f}、MP {mp_loss:.0f}{reduction_text}。"

    def _resolve_celestial_ascension_step(
        self, game: GameState, step: str, rng: random.Random,
    ) -> tuple[str, str]:
        player = game.player
        trial = game.active_trial
        if not trial:
            raise ValueError("当前没有进行中的飞升劫")
        hp_ratio = player.hp / max(1.0, max_hp(player))
        mp_ratio = player.mp / max(1.0, max_mp(player))
        thunder_index = {
            "ascension_thunder_1":0, "ascension_thunder_2":1, "ascension_thunder_3":2,
        }.get(step)
        reduction = 0.0
        if step == "ascension_body":
            passed, detail, drain_hp, drain_mp = hp_ratio >= 0.75, f"HP {hp_ratio:.0%}/75%", (0.03, 0.06), (0.02, 0.04)
        elif step == "ascension_space":
            passed, detail, drain_hp, drain_mp = mp_ratio >= 0.68, f"MP {mp_ratio:.0%}/68%", (0.03, 0.05), (0.05, 0.08)
        elif thunder_index is not None:
            hp_need = (0.58, 0.48, 0.38)[thunder_index]
            mp_need = (0.52, 0.42, 0.32)[thunder_index]
            passed = hp_ratio >= hp_need and mp_ratio >= mp_need
            detail = f"HP {hp_ratio:.0%}/{hp_need:.0%}，MP {mp_ratio:.0%}/{mp_need:.0%}"
            drain_hp = ((0.08, 0.13), (0.10, 0.16), (0.12, 0.19))[thunder_index]
            drain_mp = ((0.07, 0.11), (0.08, 0.13), (0.10, 0.15))[thunder_index]
            reduction = self._tribulation_damage_reduction(player, "celestial_ascension")
        elif step == "ascension_karma":
            actual = effective_karma(player)
            passed, detail, drain_hp, drain_mp = actual <= 120, f"有效因果 {actual:.1f}/120", (0.02, 0.04), (0.03, 0.05)
        elif step == "ascension_demon":
            threshold = expected_combat_power(8, 9) * 0.75
            actual = self._player_intrinsic_combat_power(player)
            passed = player.heart_demon <= 50 and actual >= threshold
            detail = f"心魔 {player.heart_demon:.1f}/50，战斗力 {actual:.0f}/{threshold:.0f}"
            drain_hp, drain_mp = (0.05, 0.09), (0.07, 0.11)
        elif step == "ascension_law":
            threshold = expected_combat_power(8, 9) * 0.80
            actual = self._player_intrinsic_combat_power(player)
            passed, detail = actual >= threshold, f"战斗力 {actual:.0f}/{threshold:.0f}"
            drain_hp, drain_mp = (0.04, 0.08), (0.06, 0.10)
        elif step == "ascension_heart":
            passed, detail, drain_hp, drain_mp = player.heart_demon <= 45, f"心魔 {player.heart_demon:.1f}/45", (0.02, 0.04), (0.04, 0.07)
        else:
            raise ValueError("未知的飞升劫关隘")
        if not passed:
            player.heart_demon += self._sage_scaled_gain(
                player, float(WORLD_SYSTEMS["breakthrough"]["trial_failure_heart_demon"]),
                "heart_demon_gain_reduction",
            )
            player.next_thunder_damage_reduction = 0.0
            game.active_trial = None
            self._die(game, f"九重飞升劫的{step}判定失败，肉身与元神一同崩解", "SYS_CELESTIAL_ASCENSION_FAILED")
            return "dead", f"飞升判定失败（{detail}），你在仙门之前陨落。"
        hp_loss = max_hp(player) * rng.uniform(*drain_hp) * (1 - reduction)
        mp_loss = max_mp(player) * rng.uniform(*drain_mp) * (1 - reduction)
        player.hp = max(1.0, player.hp - hp_loss)
        player.mp = max(0.0, player.mp - mp_loss)
        trial["step_index"] = int(trial["step_index"]) + 1
        if int(trial["step_index"]) < len(trial["event_ids"]):
            event_id = trial["event_ids"][int(trial["step_index"])]
            game.pending_event = self._instantiate_event(self.events_by_id[event_id], game, rng)
            reduction_text = f"，雷伤减免 {reduction:.0%}" if reduction else ""
            return "trial_step_success", f"第 {trial['step_index']}/9 关通过（{detail}），HP -{hp_loss:.0f}、MP -{mp_loss:.0f}{reduction_text}。"

        origin = player.world
        companion_kept, friend_ids, friend_names, fallen_names = self._resolve_selected_ascension_entourage(
            game, "celestial", rng,
        )
        self._prepare_permanent_world_transition(
            game, keep_companion=companion_kept, keep_friend_ids=friend_ids,
        )
        player.world = "celestial"
        player.location_id = self.maps.default_location("celestial")
        player.realm_index = 9
        player.layer = 1
        player.opportunity = 0.0
        player.awaiting_ascension = False
        player.awaiting_major_breakthrough = False
        player.awaiting_minor_breakthrough = False
        player.immortal_power_converted = False
        player.immortal_conversion_stage = 0
        player.immortal_conversion_last_age = player.age
        player.immortal_conversion_checked_units = 0
        player.next_thunder_damage_reduction = 0.0
        player.next_tribulation_age = None
        player.tribulation_power = None
        player.hp = max_hp(player)
        player.mp = 0.0
        self._clear_market(game)
        self._ensure_heavenly_court(game, rng)
        game.active_trial = None
        game.pending_event = None
        game.history.append(HistoryRecord(
            "SYS_CELESTIAL_ASCENSION_COMPLETE", 1, player.age, "飞升仙界", None, "ascended",
            "你渡过九重飞升劫，自灵界登临仙界并成就真仙；下界法力暂时归零，此后需经过五个长期阶段逐步转化为仙灵力。首次机缘最早在十个仙界时间单位后出现。"
            + (" 道侣与你一同登临仙界。" if companion_kept else "")
            + (f" 道友{'、'.join(friend_names)}成功同行。" if friend_names else "")
            + (f" 道友{'、'.join(fallen_names)}陨落于界壁。" if fallen_names else ""),
            {"world":[origin, "celestial"], "realm_index":[8, 9]},
            ["system", "ascension", "celestial", "milestone"],
        ))
        reduction_text = f"，雷伤减免 {reduction:.0%}" if reduction else ""
        return "trial_completed", f"第 9/9 关通过（{detail}），HP -{hp_loss:.0f}、MP -{mp_loss:.0f}{reduction_text}；你已登临仙界。"

    def _resolve_asura_ascension_step(
        self, game: GameState, step: str, rng: random.Random,
    ) -> tuple[str, str]:
        player = game.player
        trial = game.active_trial
        if not trial:
            raise ValueError("当前没有进行中的修罗飞升劫")
        config = WORLD_SYSTEMS["demonic_cultivation"]["asura_ascension"]
        hp_ratio = player.hp / max(1.0, max_hp(player))
        mp_ratio = player.mp / max(1.0, max_mp(player))
        thunder_index = {
            "asura_thunder_1":0, "asura_thunder_2":1, "asura_thunder_3":2,
        }.get(step)
        reduction = 0.0
        if step == "asura_body":
            passed, detail, drain_hp, drain_mp = hp_ratio >= 0.75, f"HP {hp_ratio:.0%}/75%", (0.04, 0.07), (0.02, 0.04)
        elif step == "asura_boundary":
            current_qi = qi_level(player.qi_experience.get("demon", 0.0))
            required_qi = int(config["required_demon_qi_level"])
            passed = mp_ratio >= 0.68 and current_qi >= required_qi
            detail = f"MP {mp_ratio:.0%}/68%，魔气等级 {current_qi}/{required_qi}"
            drain_hp, drain_mp = (0.03, 0.06), (0.06, 0.10)
        elif thunder_index is not None:
            hp_need = (0.60, 0.50, 0.40)[thunder_index]
            mp_need = (0.54, 0.44, 0.34)[thunder_index]
            passed = hp_ratio >= hp_need and mp_ratio >= mp_need
            detail = f"HP {hp_ratio:.0%}/{hp_need:.0%}，MP {mp_ratio:.0%}/{mp_need:.0%}"
            drain_hp = ((0.09, 0.14), (0.11, 0.17), (0.13, 0.20))[thunder_index]
            drain_mp = ((0.07, 0.12), (0.09, 0.14), (0.11, 0.16))[thunder_index]
            reduction = self._tribulation_damage_reduction(player, "asura_ascension")
        elif step == "asura_karma":
            actual = effective_karma(player)
            limit = float(config["karma_limit"])
            passed, detail = actual <= limit, f"有效因果 {actual:.1f}/{limit:.0f}"
            drain_hp, drain_mp = (0.03, 0.06), (0.04, 0.07)
        elif step == "asura_demon":
            threshold = expected_combat_power(8, 9) * float(config["combat_ratio"])
            actual = self._player_intrinsic_combat_power(player)
            heart_limit = float(config["heart_demon_limit"])
            passed = player.heart_demon <= heart_limit and actual >= threshold
            detail = f"心魔 {player.heart_demon:.1f}/{heart_limit:.0f}，战斗力 {actual:.0f}/{threshold:.0f}"
            drain_hp, drain_mp = (0.06, 0.10), (0.08, 0.12)
        elif step == "asura_sha":
            minimum = int(config["sha_qi_min"])
            passed, detail = player.sha_qi >= minimum, f"煞气 {player.sha_qi}/{minimum}"
            drain_hp, drain_mp = (0.04, 0.08), (0.05, 0.09)
        elif step == "asura_heart":
            limit = float(config["heart_demon_limit"])
            passed, detail = player.heart_demon <= limit, f"心魔 {player.heart_demon:.1f}/{limit:.0f}"
            drain_hp, drain_mp = (0.03, 0.05), (0.05, 0.08)
        else:
            raise ValueError("未知的修罗飞升劫关隘")
        if not passed:
            player.heart_demon += self._sage_scaled_gain(
                player, float(WORLD_SYSTEMS["breakthrough"]["trial_failure_heart_demon"]),
                "heart_demon_gain_reduction",
            )
            player.next_thunder_damage_reduction = 0.0
            game.active_trial = None
            self._die(game, f"九重修罗天魔劫的{step}判定失败，魔躯与元神一同崩解", "SYS_ASURA_ASCENSION_FAILED")
            return "dead", f"修罗飞升判定失败（{detail}），你在天关之前陨落。"
        hp_loss = max_hp(player) * rng.uniform(*drain_hp) * (1 - reduction)
        mp_loss = max_mp(player) * rng.uniform(*drain_mp) * (1 - reduction)
        player.hp = max(1.0, player.hp - hp_loss)
        player.mp = max(0.0, player.mp - mp_loss)
        trial["step_index"] = int(trial["step_index"]) + 1
        if int(trial["step_index"]) < len(trial["event_ids"]):
            event_id = trial["event_ids"][int(trial["step_index"])]
            game.pending_event = self._instantiate_event(self.events_by_id[event_id], game, rng)
            reduction_text = f"，雷伤减免 {reduction:.0%}" if reduction else ""
            return "trial_step_success", f"第 {trial['step_index']}/9 关通过（{detail}），HP -{hp_loss:.0f}、MP -{mp_loss:.0f}{reduction_text}。"

        origin = player.world
        lost_puppets = len(player.puppets)
        companion_kept, friend_ids, friend_names, fallen_names = self._resolve_selected_ascension_entourage(
            game, "asura", rng,
        )
        self._prepare_permanent_world_transition(
            game, keep_companion=companion_kept, keep_friend_ids=friend_ids,
        )
        player.world = "asura"
        player.location_id = self.maps.default_location("asura")
        player.realm_index = 9
        player.layer = 1
        player.opportunity = 0.0
        player.awaiting_ascension = False
        player.awaiting_major_breakthrough = False
        player.awaiting_minor_breakthrough = False
        player.next_thunder_damage_reduction = 0.0
        player.next_tribulation_age = None
        player.tribulation_power = None
        player.hp = max_hp(player)
        player.mp = max_mp(player)
        self._clear_market(game)
        self._ensure_market(game, rng)
        game.active_trial = None
        game.pending_event = None
        game.history.append(HistoryRecord(
            "SYS_ASURA_ASCENSION_COMPLETE", 1, player.age, "飞升修罗界", None, "ascended",
            "你渡过九重修罗天魔劫，自真魔界登临修罗界并成就迦楼罗。四大修罗境界已经确立，但境界突破规则暂未开放。"
            + (f" 受天关排斥，{lost_puppets}具傀儡未能同行。" if lost_puppets else "")
            + (" 道侣与你一同登临修罗界。" if companion_kept else "")
            + (f" 道友{'、'.join(friend_names)}成功同行。" if friend_names else "")
            + (f" 道友{'、'.join(fallen_names)}陨落于界壁。" if fallen_names else ""),
            {"world":[origin, "asura"], "realm_index":[8, 9], "lost_puppets":lost_puppets},
            ["system", "ascension", "asura", "demonic", "milestone"],
        ))
        reduction_text = f"，雷伤减免 {reduction:.0%}" if reduction else ""
        return "trial_completed", f"第 9/9 关通过（{detail}），HP -{hp_loss:.0f}、MP -{mp_loss:.0f}{reduction_text}；你已登临修罗界。"

    def _maybe_immortal_conversion_event(self, game: GameState, rng: random.Random) -> bool:
        player = game.player
        if (
            player.world != "celestial" or player.realm_index < 9 or player.immortal_power_converted
            or player.immortal_conversion_stage >= 5 or game.pending_event or game.active_trial
        ):
            return False
        config = WORLD_SYSTEMS["immortal_power_conversion"]
        unit_years = int(config["time_unit_years"])
        min_gap = int(config["min_gap_units"])
        if player.immortal_conversion_last_age is None:
            player.immortal_conversion_last_age = player.age
            player.immortal_conversion_checked_units = 0
            return False
        elapsed_units = max(0, (player.age - player.immortal_conversion_last_age) // unit_years)
        checked_units = min(elapsed_units, max(0, player.immortal_conversion_checked_units))
        for unit in range(checked_units + 1, elapsed_units + 1):
            player.immortal_conversion_checked_units = unit
            if unit < min_gap:
                continue
            chance = min(0.98, float(config["base_chance"]) + float(config["chance_per_unit"]) * (unit - min_gap))
            if rng.random() >= chance:
                continue
            stage = player.immortal_conversion_stage + 1
            event_id = f"EVT_IMMORTAL_CONVERSION_{stage:03d}"
            event = self._instantiate_event(self.events_by_id[event_id], game, rng)
            event["body"] += f"\n\n你已等待 {unit} 个仙界时间单位，本次触发概率为 {chance:.0%}。"
            event["runtime"] = {"conversion_stage": stage, "waited_units": unit, "trigger_chance": chance}
            game.pending_event = event
            return True
        return False

    def _complete_immortal_conversion_stage(self, game: GameState, expected_stage: int) -> tuple[str, str]:
        player = game.player
        if player.world != "celestial" or player.immortal_power_converted:
            raise ValueError("当前没有可完成的仙灵力转化")
        if expected_stage != player.immortal_conversion_stage + 1 or not 1 <= expected_stage <= 5:
            raise ValueError("仙灵力转化次序不符")
        player.immortal_conversion_stage = expected_stage
        player.immortal_conversion_last_age = player.age
        player.immortal_conversion_checked_units = 0
        player.mp = max_mp(player) * expected_stage / 5
        game.history.append(HistoryRecord(
            f"SYS_IMMORTAL_CONVERSION_{expected_stage}", 1, player.age,
            f"仙灵力转化·{expected_stage * 20}%", None, "completed",
            f"第 {expected_stage}/5 阶段完成，可用仙灵力上限提升至原完整 MP 基准的 {expected_stage * 20}%。",
            {"conversion_stage": expected_stage, "usable_ratio": expected_stage / 5},
            ["system", "celestial", "immortal_power"],
        ))
        if expected_stage < 5:
            return "immortal_conversion_stage", (
                f"第 {expected_stage}/5 阶段完成，可用仙灵力上限现为 {expected_stage * 20}%。"
                "下一阶段需再间隔至少 10 个仙界时间单位。"
            )
        player.immortal_power_converted = True
        learn_technique(player, copy.deepcopy(TECHNIQUE_CATALOG["TECH_CELESTIAL_BREATHING"]))
        add_item(player, "immortal_origin_stone", 3)
        player.hp = max_hp(player)
        player.mp = max_mp(player)
        game.history.append(HistoryRecord(
            "SYS_IMMORTAL_POWER_CONVERTED", 1, player.age, "仙元初成", None, "completed",
            "五个长期阶段全部完成：原有 MP 基准已整体蜕变为仙灵力。你获得《真仙引灵经》与三枚仙元石。",
            {"immortal_power_converted":[False, True], "conversion_stage":5},
            ["system", "celestial", "immortal_power", "milestone"],
        ))
        return "immortal_conversion_completed", "最后阶段完成，仙灵力条已完整开放；仙界行动与仙家功法现已解锁。"

    @staticmethod
    def _body_tribulation_damage_reduction(player: Player) -> float:
        config = WORLD_SYSTEMS["body_cultivation"]
        start = int(config["tribulation_reduction_start"])
        if player.body_training < start:
            return 0.0
        steps = 1 + (player.body_training - start) // int(config["tribulation_reduction_step_layers"])
        return steps * float(config["tribulation_reduction_per_step"])

    def _tribulation_damage_reduction(self, player: Player, kind: str = "heavenly") -> float:
        item_reduction = (
            sum(item.tribulation_damage_reduction * item.quantity for item in player.inventory)
            + player.natal_artifact_tribulation_reduction
            + crafted_artifact_bonuses(player)["tribulation_reduction"]
        )
        one_time = player.next_thunder_damage_reduction if kind in {"periodic_thunder", "celestial_ascension", "asura_ascension"} else 0.0
        sage_key = "thunder_tribulation_reduction" if kind == "periodic_thunder" else "heavenly_tribulation_reduction"
        sage_reduction = max(0.0, float(player.sage_effects.get(sage_key, 0.0)))
        return min(
            0.75,
            item_reduction + self._body_tribulation_damage_reduction(player) + one_time + sage_reduction,
        )

    @staticmethod
    def _tribulation_base_power_cap(world: str) -> float | None:
        raw = WORLD_SYSTEMS["world_profiles"].get(world, {}).get("tribulation_base_power_cap")
        if raw is None:
            return None
        cap = float(raw)
        return cap if cap > 0 else None

    def _check_tribulation(self, game: GameState, rng: random.Random) -> None:
        player = game.player
        true_realm_index = int(
            (player.cultivation_suppression or {}).get("realm_index", player.realm_index)
        )
        true_layer = int(
            (player.cultivation_suppression or {}).get("layer", player.layer)
        )
        if (
            true_realm_index < 6 or game.pending_event or game.active_trial
            or player.next_tribulation_age is None or player.age < player.next_tribulation_age
        ):
            return
        thunder = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
        uncapped_base_power = float(player.tribulation_power or thunder["base_power"])
        world_cap = self._tribulation_base_power_cap(player.world)
        base_power = min(uncapped_base_power, world_cap) if world_cap is not None else uncapped_base_power
        sealed = player.sealed_cultivation or {}
        current_tier = int(WORLD_SYSTEMS["world_profiles"].get(player.world, {}).get("tier", 1))
        upper_tier = int(WORLD_SYSTEMS["world_profiles"].get(str(sealed.get("upper_world", player.world)), {}).get("tier", current_tier))
        world_multiplier = (
            float(WORLD_SYSTEMS["world_travel"].get("lower_world_tribulation_multiplier", 1.0))
            if upper_tier > current_tier else 1.0
        )
        power = base_power * world_multiplier
        event_ids = ["EVT_PERIODIC_THUNDER_001", "EVT_PERIODIC_THUNDER_002", "EVT_PERIODIC_THUNDER_003"]
        game.active_trial = {
            "kind": "periodic_thunder", "source_realm": true_realm_index,
            "target_realm": true_realm_index, "target_layer": true_layer,
            "major": False, "old_label": public_player(player)["realm_name"],
            "step_index": 0, "event_ids": event_ids, "lethal": True, "power": power,
            "base_power":base_power, "uncapped_base_power":uncapped_base_power,
            "world_base_power_cap":world_cap, "world_power_multiplier":world_multiplier,
        }
        game.pending_event = self._instantiate_event(self.events_by_id[event_ids[0]], game, rng)
        game.history.append(HistoryRecord(
            "SYS_TRIBULATION_BEGINS", 1, player.age, "雷劫倒计时归零", None, "started",
            f"第 {player.tribulation_count + 1} 次三千年雷劫降临，当前雷威 {power:.0f}，共需承受三道判定。"
            + (f" 本界法则将基础雷威限制在 {world_cap:.0f}。" if world_cap is not None and uncapped_base_power > world_cap else "")
            + (" 真实道果所在界面高于当前界面，雷劫威力额外增加 50%。" if world_multiplier > 1 else ""),
            {
                "power": power, "base_power":base_power,
                "uncapped_base_power":uncapped_base_power,
                "world_base_power_cap":world_cap,
                "world_power_multiplier":world_multiplier,
                "tribulation_count": player.tribulation_count,
            }, ["system", "tribulation"],
        ))

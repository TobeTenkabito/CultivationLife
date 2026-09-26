from __future__ import annotations

import random
from typing import Any
from ...content_registry import (
    ACTIONS,
    FACTION_DEFINITIONS,
    FACTION_REWARDS,
    FACTION_SYSTEMS,
    REALMS,
    RACE_DEFINITIONS,
    RACE_SYSTEMS,
    WORLD_SYSTEMS,
)
from ...models import GameState, HistoryRecord, SectState
from ...rules import expected_combat_power, max_hp, max_mp
from ...world_state import RELATION_LABELS, race_pair, split_race_pair


class EngineWorldFactionsMixin:
    @staticmethod
    def _ensure_race_relations(game: GameState) -> bool:
        changed = False
        diplomacy = RACE_SYSTEMS.get("diplomacy", {})
        for row in diplomacy.get("initial_relations", []):
            members = list(row.get("members", []))
            if len(members) != 2:
                continue
            key = race_pair(str(members[0]), str(members[1]))
            if key not in game.race_relations:
                game.race_relations[key] = {
                    "affinity": float(row.get("affinity", 0)),
                    "status": str(row.get("status", "neutral")),
                    "since_age": game.player.age,
                    "name": row.get("name"),
                }
                changed = True
        return changed

    @staticmethod
    def _governance_threshold(world: str) -> int:
        thresholds = WORLD_SYSTEMS["player_faction"]["governance_threshold"]
        # 新增界面按界面层级沿用人界/上界治理门槛，避免每开一个界面都
        # 必须复制一份纯数值配置。
        fallback = "human" if world == "human" else "spirit"
        return int(thresholds.get(world, thresholds[fallback]))

    @staticmethod
    def _faction_meta(game: GameState, faction_id: str) -> dict[str, Any]:
        if faction_id in FACTION_DEFINITIONS:
            return dict(FACTION_DEFINITIONS[faction_id])
        sect = game.sects.get(faction_id)
        if not sect:
            return {"name": faction_id, "world": "human", "path": "dao", "description": "自立势力"}
        return {
            "name": sect.name, "world": sect.world, "path": sect.path,
            "description": sect.description or "由玩家开创的新宗门。",
            "allegiance_race": sect.allegiance_race or "human",
        }

    @staticmethod
    def _ensure_sect_relations(game: GameState) -> bool:
        changed = False
        active = [sect for sect in game.sects.values() if not sect.extinct]
        for index, first in enumerate(active):
            for second in active[index + 1:]:
                if first.world != second.world:
                    continue
                key = race_pair(first.id, second.id)
                if key not in game.sect_relations:
                    game.sect_relations[key] = {
                        "affinity": 0.0, "status": "neutral", "since_age": game.player.age,
                    }
                    changed = True
        return changed

    def _has_race_voice(self, game: GameState) -> bool:
        if self._intrigue_enabled():
            race_id = self._player_allegiance_race(game.player)
            return self._world_supports(game.player.world, "races") and self._intrigue_has_decision_authority(game, "race", race_id)
        realm_index, _ = self._actual_player_realm(game.player)
        required = int(WORLD_SYSTEMS["world_travel"]["required_realm"])
        return self._world_supports(game.player.world, "races") and self._player_allegiance_race(game.player) == "human" and realm_index >= required

    def _has_sect_voice(self, game: GameState) -> bool:
        player = game.player
        sect = game.sects.get(player.faction_id or "")
        if self._intrigue_enabled():
            return bool(sect and self._intrigue_has_decision_authority(game, "sect", sect.id))
        realm_index, _ = self._actual_player_realm(player)
        return bool(
            sect and not sect.extinct and sect.world == player.world
            and (sect.founded_by_player or realm_index >= self._governance_threshold(player.world))
        )

    def _has_family_voice(self, game: GameState) -> bool:
        family = game.family
        if self._intrigue_enabled():
            return bool(
                family and family.world == game.player.world
                and self._intrigue_has_decision_authority(game, "family", family.id)
            )
        return bool(
            family and not family.extinct and family.founded_by_player
            and family.world == game.player.world
        )

    def _check_sect_extinction(self, game: GameState, sect: SectState) -> bool:
        if sect.extinct or any(npc.alive and npc.world == sect.world for npc in self._sect_members(game, sect)):
            return False
        sect.extinct = True
        summary = f"{sect.name}最后一盏 NPC 魂灯熄灭，传承断绝，宗门正式灭亡。"
        if game.player.faction_id == sect.id:
            game.player.faction_id = None
            game.player.faction_join_age = None
            game.player.faction_contribution = 0
            game.player.faction_reward_preference = None
        game.history.append(HistoryRecord(
            "SYS_SECT_EXTINCT",1,game.player.age,"宗门灭亡",sect.id,"extinct",summary,
            {"sect_id":sect.id,"extinct":True},["system","faction","extinction","world_news",f"world:{sect.world}"],
        ))
        return True

    def _dissolve_player_sect(self, game: GameState, sect: SectState, reason: str) -> None:
        """Disband a weak player sect without falsely killing every former member."""
        sect.extinct = True
        for npc in self._sect_members(game, sect):
            if npc.alive:
                npc.faction_id = None
                game.notable_npcs.setdefault(npc.id, npc)
        if game.player.faction_id == sect.id:
            game.player.faction_id = None
            game.player.faction_join_age = None
            game.player.faction_contribution = 0
            game.player.faction_reward_preference = None
        game.history.append(HistoryRecord(
            "SYS_PLAYER_SECT_DISSOLVED",1,game.player.age,"山门解散",sect.id,"dissolved",
            f"{sect.name}因{reason}而解散；幸存门人散入天下，并未凭空陨落。",
            {"sect_id":sect.id,"pressure":sect.pressure},
            ["system","faction","player_faction","extinction","world_news",f"world:{sect.world}"],
        ))

    def _maybe_founded_sect_pressure(self, game: GameState, rng: random.Random) -> bool:
        player = game.player
        sect = game.sects.get(player.faction_id or "")
        if not sect or sect.extinct or not sect.founded_by_player or sect.world != player.world:
            return False
        actual_realm, _ = self._actual_player_realm(player)
        governance_threshold = self._governance_threshold(player.world)
        qualified_members = [
            npc for npc in self._sect_members(game, sect)
            if npc.alive and npc.world == sect.world and npc.realm_index >= governance_threshold
        ]
        if actual_realm >= governance_threshold or qualified_members:
            # 排挤针对的是“无人坐镇”的弱小山门。只要玩家或任一正式门人
            # 达到本界治理门槛，旧的守山失败记录也应立即失效。
            sect.pressure = 0
            return False
        faction_rules = WORLD_SYSTEMS["player_faction"]
        if rng.random() >= float(faction_rules["pressure_chance_per_unit"]):
            return False
        event_id = f"EVT_PLAYER_SECT_DEFENSE_{min(3, sect.pressure + 1):03d}"
        game.pending_event = self._instantiate_event(self.events_by_id[event_id], game, rng)
        threshold_realm = governance_threshold
        required_power = expected_combat_power(threshold_realm, 1) * (0.58 + sect.pressure * 0.12)
        game.pending_event["runtime"] = {
            "sect_id":sect.id, "required_power":round(required_power, 1),
            "failure_number":sect.pressure + 1,
        }
        game.pending_event["_history_tags"] = [
            tag for tag in self.events_by_id[event_id].get("tags", []) if not tag.startswith("world:")
        ] + [f"world:{player.world}"]
        game.pending_event["body"] += f"（正面守山建议战力 {required_power:.0f}；此前护山失败 {sect.pressure}/3 次。）"
        return True

    def _annual_sect_update(self, game: GameState, rng: random.Random) -> list[str]:
        news: list[str] = []
        player = game.player
        living_spirit_npcs = sum(
            npc.alive and npc.world == "human" and npc.realm_index == 5
            for sect in game.sects.values()
            for npc in sect.npcs
        ) + sum(npc.alive and npc.world == "human" and npc.realm_index == 5 for npc in game.world_npcs.values())
        for sect_id, sect in game.sects.items():
            if sect.extinct:
                continue
            for npc in sect.npcs:
                if not npc.alive or npc.world != sect.world:
                    continue
                npc.age += 1
                if self._intrigue_is_imprisoned(game, npc.id):
                    if npc.lifespan is not None and npc.age >= npc.lifespan:
                        npc.alive = False
                        npc.death_reason = "服刑期间寿元耗尽"
                    continue
                if npc.wounds > 0 and rng.random() < 0.35:
                    npc.wounds -= 1
                tribulation = self._resolve_npc_periodic_tribulation(game, npc, rng, sect.name)
                if tribulation:
                    if sect.world == player.world:
                        news.append(f"{player.age}岁：{tribulation}")
                    if not npc.alive:
                        continue
                death_reason: str | None = None
                if npc.lifespan is not None and npc.age >= npc.lifespan:
                    death_reason = "寿元耗尽，坐化于宗门祖庭"
                elif rng.random() < float(FACTION_SYSTEMS["npc_cultivation"]["accident_death_chance"]):
                    death_reason = rng.choice(["外出历练时失踪，魂灯熄灭", "冲关失败，道消身殒", 
                                               "遭逢旧敌伏杀，未能归山", "秘境陨落，身死道消", 
                                               "遭遇魔道，元神不测", "走火入魔，爆体而亡"])
                if death_reason:
                    npc.alive = False
                    npc.death_reason = death_reason
                    if sect.world == player.world:
                        news.append(f"{player.age}岁：{sect.name}{npc.name}{death_reason}")
                    game.history.append(HistoryRecord(
                        "SYS_SECT_NPC_FALL", 1, player.age, "宗门讣告", None, "npc_fallen",
                        f"{sect.name}{npc.title}{npc.name}{death_reason}。",
                        {"npc_id": npc.id, "alive": [True, False]},
                        ["system", "faction", "npc", "world_news", f"world:{sect.world}"],
                    ))
                    continue
                crossing_to_spirit = npc.world == "human" and npc.realm_index == 4 and npc.layer == REALMS[4].layers
                can_cross = not crossing_to_spirit or living_spirit_npcs < 1
                old_title = self._dynamic_sect_title(npc, sect)
                breakthrough = self._advance_npc_cultivation(npc, rng, can_cross)
                if breakthrough:
                    old_name, new_name = breakthrough["old"], breakthrough["new"]
                    new_title = self._dynamic_sect_title(npc, sect)
                    title_change = f"，职衔由{old_title}晋为{new_title}" if new_title != old_title else ""
                    if breakthrough["type"] == "breakthrough" and npc.world == "human" and npc.realm_index == 5:
                        living_spirit_npcs += 1
                    if breakthrough["type"] == "departure":
                        living_spirit_npcs = max(0, living_spirit_npcs - 1)
                        if sect.world == player.world:
                            news.append(f"{player.age}岁：{sect.name}{npc.name}{new_name}，人界魂灯熄灭")
                    else:
                        if sect.world == player.world:
                            news.append(f"{player.age}岁：{sect.name}{npc.name}由{old_name}突破至{new_name}")
                    game.history.append(HistoryRecord(
                        "SYS_SECT_NPC_DEPART" if breakthrough["type"] == "departure" else "SYS_SECT_NPC_BREAKTHROUGH",
                        1, player.age, "宗门魂灯" if breakthrough["type"] == "departure" else "宗门喜报", None,
                        "npc_departed" if breakthrough["type"] == "departure" else "npc_breakthrough",
                        f"{sect.name}{old_title}{npc.name}{new_name}。" if breakthrough["type"] == "departure" else f"{sect.name}{old_title}{npc.name}由{old_name}突破至{new_name}{title_change}。",
                        {"npc_id": npc.id, "realm": [old_name, new_name]},
                        ["system", "faction", "npc", "world_news", f"world:{sect.world}"],
                    ))
            if self._check_sect_extinction(game, sect):
                continue
            self._compact_sect_roster(game, sect)
            if (
                player.age % int(FACTION_SYSTEMS["recruitment_interval_years"]) == 0
                and len([npc for npc in self._sect_members(game, sect) if npc.alive])
                < int(FACTION_SYSTEMS.get("max_members", 36))
            ):
                newcomer = self._recruit_sect_npc(sect, player.age, rng)
                if newcomer.realm_index >= 3:
                    if sect.world == player.world:
                        news.append(f"{player.age}岁：{newcomer.name}以{self._npc_realm_name(newcomer)}修为加入{sect.name}")
                    game.history.append(HistoryRecord(
                        "SYS_SECT_RECRUIT", 1, player.age, "宗门招新", None, "npc_joined",
                        f"{newcomer.name}以{self._npc_realm_name(newcomer)}修为加入{sect.name}，列为{newcomer.title}。",
                        {"npc_id": newcomer.id, "realm_index": newcomer.realm_index},
                        ["system", "faction", "npc", "recruitment", "world_news", f"world:{sect.world}"],
                    ))
                elif player.faction_id == sect_id:
                    game.history.append(HistoryRecord(
                        "SYS_SECT_RECRUIT", 1, player.age, "宗门招新", None, "npc_joined",
                        f"{newcomer.name}以{self._npc_realm_name(newcomer)}修为加入{sect.name}，列为{newcomer.title}。",
                        {"npc_id": newcomer.id, "realm_index": newcomer.realm_index},
                        ["system", "faction", "npc", "recruitment"],
                    ))
                self._compact_sect_roster(game, sect)

        news.extend(self._annual_offspring_and_family_update(game, rng))
        self._annual_relationship_update(game, rng)
        faction_meta = self._faction_meta(game, player.faction_id or "")
        if (
            not player.faction_id
            or player.faction_id not in game.sects
            or game.sects[player.faction_id].extinct
            or faction_meta.get("world", "human") != player.world
        ):
            return news
        reward_id = (
            player.faction_reward_preference
            if player.realm_index >= 4 and player.faction_reward_preference in FACTION_REWARDS
            else rng.choice(sorted(FACTION_REWARDS))
        )
        reward_name = FACTION_REWARDS[reward_id]["name"]
        if reward_id == "opportunity":
            self._add_opportunity(player, 3)
            reward_text = "机缘 +3"
        elif reward_id == "vitality":
            player.faction_hp_bonus += 2
            player.hp = min(max_hp(player), player.hp + 2)
            reward_text = "HP 上限永久 +2"
        elif reward_id == "mana":
            player.faction_mp_bonus += 2
            player.mp = min(max_mp(player), player.mp + 2)
            reward_text = "MP 上限永久 +2"
        else:
            player.faction_combat_bonus += 3
            reward_text = "独立战斗力永久 +3"
        player.faction_contribution += 1
        sect_name = faction_meta["name"]
        game.history.append(HistoryRecord(
            "SYS_FACTION_WELFARE", 1, player.age, f"{sect_name}年度结算", reward_id, "rewarded",
            f"宗门发放{reward_name}：{reward_text}；年度履职记宗门贡献 +1。",
            {"reward": reward_id, "faction_contribution": player.faction_contribution},
            ["system", "faction", "annual"],
        ))
        return news

    def _annual_race_diplomacy_update(self, game: GameState, rng: random.Random) -> list[str]:
        """Compatibility wrapper. Diplomacy now advances once per action unit, not once per year."""
        return self._advance_diplomacy_unit(game, rng)

    def _advance_diplomacy_unit(self, game: GameState, rng: random.Random) -> list[str]:
        self._ensure_race_relations(game)
        self._ensure_sect_relations(game)
        game.diplomacy_unit += 1
        news: list[str] = []
        config = RACE_SYSTEMS.get("diplomacy", {})

        for kind, relations in (("race", game.race_relations), ("sect", game.sect_relations)):
            for key, relation in relations.items():
                if relation.get("status") != "truce" or game.diplomacy_unit < int(relation.get("truce_until_unit", 0)):
                    continue
                first, second = split_race_pair(key)
                if kind == "race" and not all(
                    game.player.world in RACE_DEFINITIONS.get(side, {}).get("worlds", [])
                    for side in (first, second)
                ):
                    continue
                relation.update(status="neutral", affinity=max(-10.0, float(relation.get("affinity", 0))), since_age=game.player.age)
                relation.pop("truce_until_unit", None)
                first_name, second_name = self._power_name(game, kind, first), self._power_name(game, kind, second)
                world = game.player.world if kind == "race" and self._world_supports(game.player.world, "races") else "spirit" if kind == "race" else game.sects.get(first, SectState(first, first)).world
                summary = f"{first_name}与{second_name}的停战期结束，双方暂时恢复中立。"
                game.history.append(HistoryRecord(
                    "SYS_TRUCE_EXPIRED", 1, game.player.age, "停战期届满", None, "neutral", summary,
                    {"kind":kind,"sides":[first,second]}, ["system","diplomacy","truce","world_news",f"world:{world}"],
                ))
                if game.player.world == world:
                    news.append(f"{game.player.age}岁：{summary}")

        news.extend(self._advance_wars_unit(game, rng))

        allied_race = any(
            relation.get("status") in {"alliance", "vassal"}
            and self._player_allegiance_race(game.player) in split_race_pair(key)
            and all(
                game.player.world in RACE_DEFINITIONS.get(side, {}).get("worlds", [])
                for side in split_race_pair(key)
            )
            for key, relation in game.race_relations.items()
        )
        allied_sect = bool(game.player.faction_id) and any(
            relation.get("status") in {"alliance", "vassal"} and game.player.faction_id in split_race_pair(key)
            for key, relation in game.sect_relations.items()
        )
        if self._world_supports(game.player.world, "races") and allied_race:
            reward = float(config.get("alliance_opportunity_reward", 2))
            self._add_opportunity(game.player, reward)
            summary = f"盟族互市与情报共享为你带来机缘 +{reward:g}。"
            news.append(f"{game.player.age}岁：{summary}")
            game.history.append(HistoryRecord("SYS_RACE_ALLIANCE_BENEFIT", 1, game.player.age, "盟族互惠", None, "rewarded", summary, {"opportunity":reward}, ["system","diplomacy","alliance","reward",f"world:{game.player.world}"]))
        if allied_sect:
            game.player.faction_contribution += 1
            summary = "盟宗协作使你的宗门贡献 +1。"
            news.append(f"{game.player.age}岁：{summary}")
            game.history.append(HistoryRecord("SYS_SECT_ALLIANCE_BENEFIT", 1, game.player.age, "盟宗协作", None, "rewarded", summary, {"faction_contribution":1}, ["system","diplomacy","alliance","reward",f"world:{game.player.world}"]))

        if rng.random() < float(config.get("unit_event_chance", 0.08)):
            self._random_race_diplomacy_event(game, rng, news)
        if rng.random() < float(config.get("unit_event_chance", 0.08)):
            self._random_sect_diplomacy_event(game, rng, news)
        self._maybe_npc_found_power(game, rng, news)
        self._pressure_weak_npc_powers(game, rng, news)
        self._simulate_cultivator_duel(game, rng, news)
        return news

    def _random_race_diplomacy_event(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        world = game.player.world if self._world_supports(game.player.world, "races") else "spirit"
        race_ids = [race_id for race_id, row in RACE_DEFINITIONS.items() if world in row.get("worlds", [])]
        first, second = rng.sample(race_ids, 2)
        key = race_pair(first, second)
        relation = game.race_relations.setdefault(key, {"affinity": 0.0, "status": "neutral", "since_age": game.player.age})
        old_status = str(relation.get("status", "neutral"))
        if game.diplomacy_unit < max(int(relation.get("truce_until_unit", 0)), int(relation.get("war_truce_until_unit", 0))):
            return
        if old_status == "war":
            return  # 战争由士气、厌战和和谈系统决定，不再被普通外交骰直接终止。
        elif old_status in {"alliance", "vassal"}:
            new_status, affinity, action = "neutral", rng.uniform(8, 34), "断盟" if old_status == "alliance" else "脱离依附"
        else:
            roll = rng.random()
            if roll < 0.44:
                new_status, affinity, action = "war", rng.uniform(-82, -56), "宣战"
            elif roll < 0.86:
                new_status, affinity, action = "alliance", rng.uniform(72, 90), "结盟"
            else:
                new_status, affinity, action = "vassal", rng.uniform(62, 84), "确立依附"
        self._set_diplomatic_relation(game, relation, new_status, first, second, "race", affinity)
        first_name, second_name = RACE_DEFINITIONS[first]["name"], RACE_DEFINITIONS[second]["name"]
        summary = f"{first_name}与{second_name}{action}，双方关系转为{RELATION_LABELS[new_status]}（好感 {affinity:.0f}）。"
        game.history.append(HistoryRecord(
            "SYS_RACE_DIPLOMACY", 1, game.player.age, f"{WORLD_SYSTEMS['world_names'][world]}族群大事", action, new_status, summary,
            {"races": [first, second], "status": [old_status, new_status], "affinity": round(affinity, 1)},
            ["system", "diplomacy", "race", "world_news", f"world:{world}"],
        ))
        if game.player.world == world:
            news.append(f"{game.player.age}岁：{summary}")

    def _random_sect_diplomacy_event(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        active = [sect for sect in game.sects.values() if not sect.extinct]
        worlds = [world for world in {sect.world for sect in active} if sum(sect.world == world for sect in active) >= 2]
        if not worlds:
            return
        world = rng.choice(worlds)
        first, second = rng.sample([sect for sect in active if sect.world == world], 2)
        key = race_pair(first.id, second.id)
        relation = game.sect_relations.setdefault(key, {"affinity":0.0,"status":"neutral","since_age":game.player.age})
        old_status = str(relation.get("status", "neutral"))
        if game.diplomacy_unit < max(int(relation.get("truce_until_unit", 0)), int(relation.get("war_truce_until_unit", 0))):
            return
        if old_status == "war":
            return
        elif old_status in {"alliance", "vassal"}:
            new_status, affinity, action = "neutral", rng.uniform(5, 30), "断绝盟约"
        else:
            roll = rng.random()
            if roll < 0.42:
                new_status, affinity, action = "war", rng.uniform(-82, -55), "正式宣战"
            elif roll < 0.86:
                new_status, affinity, action = "alliance", rng.uniform(68, 90), "缔结盟约"
            else:
                new_status, affinity, action = "vassal", rng.uniform(58, 82), "确立依附"
        self._set_diplomatic_relation(game, relation, new_status, first.id, second.id, "sect", affinity)
        summary = f"{first.name}与{second.name}{action}，宗门关系转为{RELATION_LABELS[new_status]}（好感 {affinity:.0f}）。"
        game.history.append(HistoryRecord(
            "SYS_SECT_DIPLOMACY",1,game.player.age,"宗门外交大事",action,new_status,summary,
            {"sects":[first.id,second.id],"status":[old_status,new_status],"affinity":round(affinity,1)},
            ["system","diplomacy","faction","world_news",f"world:{world}"],
        ))
        if game.player.world == world:
            news.append(f"{game.player.age}岁：{summary}")

    def _pressure_weak_npc_powers(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        rules = WORLD_SYSTEMS["player_faction"]
        for sect in game.sects.values():
            if sect.extinct or not sect.founded_by_npc:
                continue
            threshold = self._governance_threshold(sect.world)
            if any(npc.alive and npc.world == sect.world and npc.realm_index >= threshold for npc in self._sect_members(game, sect)):
                sect.pressure = max(0, sect.pressure - 1)
                continue
            if rng.random() >= float(rules["pressure_chance_per_unit"]):
                continue
            sect.pressure += 1
            if sect.pressure < int(rules["pressure_limit"]):
                continue
            sect.extinct = True
            for npc in self._sect_members(game, sect):
                if npc.alive:
                    npc.faction_id = None
                    game.notable_npcs.setdefault(npc.id, npc)
            summary = f"{sect.name}失去足够修为的坐镇者后，接连遭到排挤，山门很快烟消云散。"
            game.history.append(HistoryRecord(
                "SYS_NPC_POWER_DISSOLVED",1,game.player.age,"新势力消散",sect.id,"dissolved",summary,
                {"sect_id":sect.id},["system","faction","npc","extinction","world_news",f"world:{sect.world}"],
            ))
            if game.player.world == sect.world:
                news.append(f"{game.player.age}岁：{summary}")

    def _simulate_cultivator_duel(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        world = game.player.world
        people = list({npc.id:npc for npc in self._all_world_npcs(game) if npc.alive and npc.world == world}.values())
        if len(people) < 2:
            return
        demonic = [npc for npc in people if npc.path == "demonic"]
        if rng.random() >= min(0.42, 0.18 + len(demonic) * 0.025):
            return
        if demonic and rng.random() < 0.72:
            first = rng.choice(demonic)
            first_faction = self._npc_faction_id(game, first.id)
            opponents = [
                npc for npc in people if npc.id != first.id
                and not (first_faction and self._npc_faction_id(game, npc.id) == first_faction)
            ]
            if not opponents:
                return
            second = rng.choice(opponents)
        else:
            pairs = [
                (first, second) for index, first in enumerate(people) for second in people[index + 1:]
                if not (
                    (first.path == "demonic" or second.path == "demonic")
                    and self._npc_faction_id(game, first.id)
                    and self._npc_faction_id(game, first.id) == self._npc_faction_id(game, second.id)
                )
            ]
            if not pairs:
                return
            first, second = rng.choice(pairs)
        first_power, second_power = self._npc_power(first), self._npc_power(second)
        winner, loser = (first, second) if first_power * rng.uniform(0.85, 1.15) >= second_power else (second, first)
        ratio = max(first_power, second_power) / max(1.0, min(first_power, second_power))
        lethal_chance = self._npc_lethal_chance(world, loser.realm_index, "duel")
        lethal = ratio >= REALMS[loser.realm_index].kill_threshold and rng.random() < lethal_chance
        if lethal:
            loser.alive = False
            loser.death_reason = f"与{winner.name}斗法时陨落"
            outcome = f"{loser.name}未能脱身，当场陨落"
            transfer_summary = ""
        else:
            loser.wounds = min(4, loser.wounds + 1)
            outcome = f"{loser.name}负伤退走"
            transfer_summary = self._maybe_transfer_player_dependency(
                game, loser, winner, rng, context="cultivator_duel",
            )
        faction_ids = {self._npc_faction_id(game, first.id), self._npc_faction_id(game, second.id)} - {None}
        tags = ["system","world_npc","duel","world_news",f"world:{world}"]
        if game.player.faction_id in faction_ids:
            tags.append("faction")
        duel_ids = {first.id, second.id}
        if game.player.dao_companion and str(game.player.dao_companion.get("id")) in duel_ids:
            tags.extend(["relationship", "dao_companion"])
        if any(str(row.get("id")) in duel_ids for row in game.player.dao_friends):
            tags.extend(["relationship", "friend"])
        if (game.player.master and str(game.player.master.get("id")) in duel_ids) or any(
            str(row.get("id")) in duel_ids for row in game.player.disciples
        ):
            tags.extend(["relationship", "master"])
        cause = "由魔修主动挑衅引发斗法" if first.path == "demonic" else "因旧怨斗法"
        summary = (
            f"{first.name}（{self._npc_realm_name(first)}）与{second.name}（{self._npc_realm_name(second)}）"
            f"{cause}，{winner.name}占据上风，{outcome}。"
            + (f" {transfer_summary}" if transfer_summary else "")
        )
        game.history.append(HistoryRecord(
            "SYS_CULTIVATOR_DUEL",1,game.player.age,"修士斗法",winner.id,"fatal" if lethal else "injured",summary,
            {"npcs":[first.id,second.id],"winner":winner.id,"loser":loser.id},tags,
        ))
        news.append(f"{game.player.age}岁：{summary}")

    def _set_diplomatic_relation(
        self, game: GameState, relation: dict[str, Any], status: str,
        first: str, second: str, kind: str, affinity: float,
    ) -> None:
        if status == "war":
            self._start_war(game, kind, first, second)
        relation.update(status=status, affinity=round(float(affinity), 1), since_age=game.player.age)
        relation.pop("overlord", None)
        relation.pop("subject", None)
        relation.pop("truce_until_unit", None)
        if status == "truce":
            relation["truce_until_unit"] = game.diplomacy_unit + int(RACE_SYSTEMS.get("diplomacy", {}).get("truce_units", 3))
        elif status == "vassal":
            power = self._race_power if kind == "race" else self._sect_power
            first_power, second_power = power(game, first), power(game, second)
            relation["overlord"], relation["subject"] = ((first, second) if first_power >= second_power else (second, first))

    def _race_power(self, game: GameState, race_id: str) -> float:
        world = game.player.world if self._world_supports(game.player.world, "races") else "spirit"
        members = [npc for npc in self._all_world_npcs(game) if npc.alive and npc.world == world and npc.race == race_id]
        return sum(sorted((self._npc_power(npc) for npc in members), reverse=True)[:5])

    def _sect_power(self, game: GameState, sect_id: str) -> float:
        sect = game.sects.get(sect_id)
        return sum(sorted((self._npc_power(npc) for npc in self._sect_members(game, sect) if npc.alive), reverse=True)[:5]) if sect else 0.0

    def _simulate_war_casualties(self, game: GameState, rng: random.Random, kind: str) -> list[str]:
        relations = game.race_relations if kind == "race" else game.sect_relations
        chance = float(RACE_SYSTEMS.get("diplomacy", {}).get("war_casualty_chance", 0.42))
        news: list[str] = []
        protected_ids = {
            str(row.get("id")) for row in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples]
            if row
        }
        for key, relation in relations.items():
            if relation.get("status") != "war" or rng.random() >= chance:
                continue
            first, second = split_race_pair(key)
            if kind == "race" and not all(
                game.player.world in RACE_DEFINITIONS.get(side, {}).get("worlds", [])
                for side in (first, second)
            ):
                continue
            fallen: list[str] = []
            for side in (first, second):
                if kind == "race":
                    world = game.player.world if self._world_supports(game.player.world, "races") else "spirit"
                    candidates = [npc for npc in self._all_world_npcs(game) if npc.alive and npc.world == world and npc.race == side]
                    side_name = RACE_DEFINITIONS.get(side, {"name": side})["name"]
                else:
                    sect = game.sects.get(side)
                    candidates = [npc for npc in (sect.npcs if sect else []) if npc.alive]
                    side_name = sect.name if sect else side
                    world = sect.world if sect else game.player.world
                candidates = [npc for npc in candidates if npc.id not in protected_ids]
                elite_realm = 4 if world == "human" else 6
                ordinary = [npc for npc in candidates if npc.realm_index < elite_realm]
                if not ordinary:
                    ordinary = candidates
                if not ordinary:
                    continue
                victim = rng.choices(ordinary, weights=[1 / max(1, npc.realm_index) for npc in ordinary], k=1)[0]
                if victim.realm_index >= elite_realm and rng.random() >= self._npc_lethal_chance(world, victim.realm_index, "war"):
                    continue
                victim.alive = False
                victim.death_reason = "势力大战中陨落"
                fallen.append(f"{side_name}{victim.name}（{self._npc_realm_name(victim)}）")
                for sect in game.sects.values():
                    if victim in sect.npcs:
                        self._check_sect_extinction(game, sect)
            if fallen:
                title = f"{WORLD_SYSTEMS['world_names'].get(world, world)}族战" if kind == "race" else "宗门大战"
                summary = f"{title}持续，本行动单位战报：" + "、".join(fallen) + "陨落。"
                tags = ["system", "diplomacy", kind, "war", "world_news", f"world:{world}"]
                game.history.append(HistoryRecord("SYS_POWER_WAR", 1, game.player.age, title, None, "casualties", summary, {"sides":[first, second]}, tags))
                if game.player.world == world:
                    news.append(f"{game.player.age}岁：{summary}")
        return news

    def _maybe_race_war_ambush(self, game: GameState, rng: random.Random) -> bool:
        player = game.player
        if not self._world_supports(player.world, "races") or game.pending_event:
            return False
        enemies = []
        player_race = self._player_allegiance_race(player)
        for key, relation in game.race_relations.items():
            first, second = split_race_pair(key)
            if player_race not in {first, second} or relation.get("status") != "war":
                continue
            enemy = second if first == player_race else first
            if player.world not in RACE_DEFINITIONS.get(enemy, {}).get("worlds", []):
                continue
            if not self._revenge_ready(game, "race_war", enemy):
                continue
            enemies.append(enemy)
        chance = float(RACE_SYSTEMS.get("diplomacy", {}).get("war_ambush_chance", 0.08))
        if not enemies or rng.random() >= chance:
            return False
        enemy = rng.choice(enemies)
        target = self._generate_cultivator_target(player, "边境截杀者", ACTIONS["slay"]["combat"], rng, game=game, forced_race=enemy)
        target["player_defending"] = True
        target["kill_karma"] = True
        target["action"] = "slay"
        self._cache_encounter_target(game, target, rng)
        ambush = self._instantiate_event(self.events_by_id["EVT_ENCOUNTER_AMBUSH_001"], game, rng)
        ambush["title"] = f"{RACE_DEFINITIONS[enemy]['name']}边境截杀"
        ambush["runtime"] = target
        ambush["body"] = (
            f"两族正在交战，{RACE_DEFINITIONS[enemy]['name']}修士循踪截住了你。"
            f"来者修为{target['target_realm_display']}，战斗力约{target['target_power']:.0f}。你必须立即应对。"
        )
        interval = self._record_revenge_trigger(game, "race_war", enemy)
        ambush.setdefault("runtime", {})["revenge_cooldown_units"] = interval
        game.pending_event = ambush
        return True

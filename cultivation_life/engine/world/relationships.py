from __future__ import annotations

import copy
import random
import uuid
from typing import Any
from ...content_registry import (
    PATH_NAMES,
    REALMS,
    RACE_DEFINITIONS,
    WORLD_SYSTEMS,
    MONSTER_BLOODLINE_SETTINGS,
    MONSTER_SPECIES,
)
from ...models import GameState, HistoryRecord, Player, SectNpc, SectState
from ...system.monster_bloodline_system import bloodline_content_available
from ...system.concubine_system import gender_name


class EngineWorldRelationshipsMixin:
    @staticmethod
    def _party_invitation_chance(player: Player, npc: SectNpc, global_hostility: float = 0.0) -> float:
        config = WORLD_SYSTEMS["party"]
        realm_gap = max(0, npc.realm_index - player.realm_index)
        confidence_bonus = 0.0
        if player.realm_index >= npc.realm_index:
            confidence_bonus = min(
                float(config.get("lower_realm_bonus_cap", 0.22)),
                float(config.get("same_or_lower_realm_bonus", 0.12))
                + max(0, player.realm_index - npc.realm_index) * float(config.get("lower_realm_bonus_per_gap", 0.04)),
            )
        return max(0.02, min(
            0.9,
            float(config["invite_base_chance"]) + confidence_bonus
            + float(npc.affinity or 0) / 200 - global_hostility / 120 - realm_gap * 0.12,
        ))

    def _party_crossing_candidate(self, game: GameState, npc_id: str) -> dict[str, Any] | None:
        player = game.player
        npc = self._find_npc(game, npc_id)
        relation = next((entry for entry in [player.dao_companion, *player.dao_friends] if entry and str(entry.get("id")) == npc_id), None)
        source = relation or (npc.to_dict() if npc else None)
        if not source or not source.get("alive", True) or source.get("world") != player.world:
            return None
        requirements = {
            "human": (5, lambda layer: layer <= 3),
            "demon": (5, lambda layer: layer >= 1),
            "spirit": (8, lambda layer: layer == REALMS[8].layers),
            "true_demon": (8, lambda layer: layer == REALMS[8].layers),
        }
        required = requirements.get(player.world)
        if (
            not required or player.realm_index != required[0]
            or not required[1](player.layer)
        ):
            return None
        if not required or int(source.get("realm_index", -1)) != required[0] or not required[1](int(source.get("layer", 99))):
            return None
        return {"id":npc_id, "name":str(source.get("name", "无名队友"))}

    def _persist_relationship_npc(self, game: GameState, relation: dict[str, Any], reason: str) -> SectNpc:
        existing = self._find_npc(game, str(relation.get("id", "")))
        if existing:
            return existing
        npc = SectNpc(
            id=str(relation.get("id") or f"relation_{uuid.uuid4().hex[:12]}"),
            name=str(relation.get("name", "无名修士")), title=reason,
            realm_index=int(relation.get("realm_index", 0)), layer=int(relation.get("layer", 1)),
            age=int(relation.get("age", 18)), lifespan=relation.get("lifespan"),
            spirit_root=str(relation.get("spirit_root", "none")),
            cultivation_progress=float(relation.get("cultivation_progress", 0)),
            path=str(relation.get("path", "dao")), race=str(relation.get("race", "human")),
            world=str(relation.get("world", game.player.world)), alive=bool(relation.get("alive", True)),
            death_reason=relation.get("death_reason"), affinity=float(relation.get("affinity", 0)),
            gender=str(relation.get("gender", "")),
            treasure_item_id=next(iter(relation.get("items", {})), None),
            next_tribulation_age=relation.get("next_tribulation_age"),
            tribulation_count=int(relation.get("tribulation_count", 0)),
            tribulation_power=relation.get("tribulation_power"),
        )
        game.notable_npcs[npc.id] = npc
        relation["id"] = npc.id
        relation["source"] = "world"
        return npc

    def _adjust_person_affinity(self, game: GameState, npc_id: str, delta: float) -> float:
        npc = self._find_npc(game, npc_id)
        relation = next((entry for entry in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples] if entry and str(entry.get("id")) == npc_id), None)
        base = float(relation.get("affinity", 0)) if relation else float(npc.affinity or 0) if npc else 0.0
        value = base + self._sage_affinity_gain(game.player, delta)
        if npc:
            npc.affinity = value
        for relation in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples]:
            if relation and str(relation.get("id")) == npc_id:
                relation["affinity"] = value
        return value

    def _set_person_affinity(self, game: GameState, npc_id: str, value: float) -> float:
        """Set, rather than add, affinity on both the persistent NPC and relation snapshot."""
        affinity = max(-100.0, min(100.0, float(value)))
        npc = self._find_npc(game, npc_id)
        if npc:
            npc.affinity = affinity
        for relation in [
            game.player.master, game.player.dao_companion,
            *game.player.dao_friends, *game.player.disciples,
        ]:
            if relation and str(relation.get("id")) == npc_id:
                relation["affinity"] = affinity
        return affinity

    @staticmethod
    def _revenge_cooldown_key(scope: str, family: str = "", adversary_id: str = "") -> str:
        suffix = ":".join(part for part in (family, adversary_id) if part)
        return f"revenge_cooldown:{scope}" + (f":{suffix}" if suffix else "")

    def _revenge_ready(self, game: GameState, family: str, adversary_id: str) -> bool:
        """All revenge sources share one global gate and also retain per-source gates."""
        global_next = int(game.governance_actions.get(self._revenge_cooldown_key("next"), -1))
        source_next = int(game.governance_actions.get(
            self._revenge_cooldown_key("next", family, adversary_id), -1,
        ))
        return game.diplomacy_unit >= max(global_next, source_next)

    def _record_revenge_trigger(self, game: GameState, family: str, adversary_id: str) -> int:
        """Start an escalating action-unit cooldown after a revenge event is opened."""
        rules = WORLD_SYSTEMS["relationship"]
        base = max(1, int(rules.get("revenge_cooldown_base_units", 3)))
        increment = max(0, int(rules.get("revenge_cooldown_increment_units", 2)))
        maximum = max(base, int(rules.get("revenge_cooldown_max_units", 15)))
        global_count_key = self._revenge_cooldown_key("count")
        source_count_key = self._revenge_cooldown_key("count", family, adversary_id)
        global_count = int(game.governance_actions.get(global_count_key, 0)) + 1
        source_count = int(game.governance_actions.get(source_count_key, 0)) + 1
        game.governance_actions[global_count_key] = global_count
        game.governance_actions[source_count_key] = source_count
        interval = min(maximum, base + (global_count - 1) * increment)
        next_unit = game.diplomacy_unit + interval
        game.governance_actions[self._revenge_cooldown_key("next")] = next_unit
        game.governance_actions[
            self._revenge_cooldown_key("next", family, adversary_id)
        ] = next_unit
        return interval

    def _personal_npcs(self, game: GameState) -> list[SectNpc]:
        return list({
            npc.id:npc for npc in self._all_world_npcs(game)
            if npc.alive and npc.world == game.player.world and npc.id != "player"
        }.values())

    def _high_affinity_npcs(self, game: GameState, exclude_id: str = "") -> list[SectNpc]:
        threshold = float(WORLD_SYSTEMS["relationship"]["positive_affinity_threshold"])
        people = [npc for npc in self._personal_npcs(game) if npc.id != exclude_id and float(npc.affinity or 0) >= threshold]
        known = {npc.id for npc in people}
        for relation in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples]:
            if not relation or str(relation.get("id")) in known or str(relation.get("id")) == exclude_id:
                continue
            if relation.get("alive", True) and relation.get("world") == game.player.world and float(relation.get("affinity", 0)) >= threshold:
                people.append(self._persist_relationship_npc(game, relation, "交好修士"))
        return people

    def _maybe_affinity_gift(self, game: GameState, rng: random.Random) -> bool:
        people = self._high_affinity_npcs(game)
        if not people:
            return False
        rules = WORLD_SYSTEMS["relationship"]
        chance = min(0.32, float(rules["positive_event_base_chance"]) + len(people) * float(rules["positive_event_per_person"]))
        if rng.random() >= chance:
            return False
        npc = rng.choices(people, weights=[max(1.0,float(person.affinity or 0)) for person in people], k=1)[0]
        event = self.events_by_id["EVT_PERSONAL_AFFINITY_GIFT_001"]
        game.pending_event = self._instantiate_event(event, game, rng)
        game.pending_event["runtime"] = {"npc_id":npc.id,"npc_name":npc.name,"npc_realm_index":npc.realm_index}
        game.pending_event["body"] = game.pending_event["body"].replace("{npc_name}",npc.name)
        return True

    def _maybe_personal_revenge(self, game: GameState, rng: random.Random) -> bool:
        rules = WORLD_SYSTEMS["relationship"]
        threshold = float(rules["hostile_affinity_threshold"])
        protected_ids = self._retaliatory_relationship_ids(game)
        enemies = [
            npc for npc in self._personal_npcs(game)
            if float(npc.affinity or 0) <= threshold and npc.id not in protected_ids
            and self._revenge_ready(game, "personal", npc.id)
        ]
        enemies = self._filter_personal_revenge_by_protection(game, enemies, rng)
        if not enemies:
            return False
        allies = self._high_affinity_npcs(game)
        protection = min(float(rules["ally_protection_cap"]), len(allies) * float(rules["ally_protection_per_person"]))
        severity = max(abs(float(npc.affinity or 0) - threshold) for npc in enemies)
        chance = min(0.75, float(rules["revenge_base_chance"]) + severity * float(rules["revenge_affinity_scale"])) * (1 - protection)
        if rng.random() >= chance:
            return False
        enemy = rng.choices(enemies, weights=[max(1.0,abs(float(npc.affinity or 0))) for npc in enemies], k=1)[0]
        race_definition = RACE_DEFINITIONS.get(enemy.race,RACE_DEFINITIONS["human"])
        target = {
            "target_name":enemy.name,"target_power":self._npc_power(enemy),"primary_power":self._npc_power(enemy),
            "target_realm_index":enemy.realm_index,"target_layer":enemy.layer,
            "target_realm_visible":enemy.realm_index <= game.player.realm_index + 1,
            "target_realm_display":self._npc_realm_name(enemy) if enemy.realm_index <= game.player.realm_index + 1 else "无法看清",
            "combat_type":"cultivator","race":enemy.race,"race_name":race_definition["name"],
            "race_description":race_definition["description"],"world":enemy.world,"npc_id":enemy.id,
            "faction_id":self._npc_faction_id(game,enemy.id),"treasure_item_id":enemy.treasure_item_id,
            "kill_karma":False,"action":"revenge", "player_defending": True,
        }
        event = self.events_by_id["EVT_PERSONAL_REVENGE_001"]
        game.pending_event = self._instantiate_event(event, game, rng)
        best_ally = max((npc for npc in allies if npc.id != enemy.id),key=self._npc_power,default=None)
        sect = game.sects.get(game.player.faction_id or "")
        sect_defenders = [npc for npc in self._sect_members(game,sect) if npc.alive and npc.id != enemy.id] if sect else []
        game.pending_event["runtime"] = {
            "target":target,"npc_id":enemy.id,
            "ally_id":best_ally.id if best_ally else None,"ally_name":best_ally.name if best_ally else None,
            "sect_support_power":max((self._npc_power(npc) for npc in sect_defenders),default=0.0),
            "chance":round(chance,3),"protection":round(protection,3),
        }
        game.pending_event["body"] = game.pending_event["body"].replace("{npc_name}",enemy.name).replace("{target_power}",f"{target['target_power']:.0f}")
        for choice in game.pending_event["choices"]:
            if choice["id"] == "ally":
                choice["enabled"] = best_ally is not None
                if best_ally is None: choice["disabled_reason"] = "当前没有愿意驰援的高好感修士"
                else: choice["text"] += f"（{best_ally.name}）"
            elif choice["id"] == "sect":
                choice["enabled"] = bool(sect_defenders)
                if not sect_defenders: choice["disabled_reason"] = "当前没有可接应你的宗门同道"
        interval = self._record_revenge_trigger(game, "personal", enemy.id)
        game.pending_event["runtime"]["revenge_cooldown_units"] = interval
        return True

    def _try_conceive_child(self, game: GameState, rng: random.Random) -> str:
        player = game.player
        companion = player.dao_companion
        if not companion or not companion.get("alive", True):
            return ""
        player_realm, _ = self._actual_player_realm(player)
        # 生育难度取双方较高的生命层次；任一方达到化神，概率即归零。
        realm_index = max(player_realm, int(companion.get("realm_index", player_realm)))
        family_rules = WORLD_SYSTEMS["family"]
        natural_chance = float(family_rules["conception_chance_by_realm"].get(str(realm_index), 0.0))
        medicine_bonus = max(0.0, float(player.next_companion_conception_bonus))
        chance = min(0.95, natural_chance + medicine_bonus)
        # 药力只绑定一次有效的缠绵互动；即使本次未能诞下后代也会消耗。
        player.next_companion_conception_bonus = 0.0
        if chance <= 0 or rng.random() >= chance:
            if chance > 0:
                source = f"（自然 {natural_chance:.1%} + 丹药 {medicine_bonus:.1%}）" if medicine_bonus else ""
                return f" 本次孕育后代概率 {chance:.1%}{source}，未有血脉诞生。"
            return " 化神以后生命层次过高，已无法自然孕育后代；可借孕育丹药暂时提高下一次概率。"
        player_innate = player.spirit_root != "none" and not player.acquired_root
        companion_root = str(companion.get("spirit_root", "none"))
        companion_innate = companion_root != "none" and not companion.get("acquired_root", False)
        has_root = player_innate and companion_innate and rng.random() < float(family_rules["spirit_root_inheritance_chance"])
        child_root = rng.choice([player.spirit_root, companion_root]) if has_root else "none"
        surn = player.name[:1] if player.name else "韩"
        child = {
            "id":f"child_{game.id.replace('-', '')[:8]}_{len(player.offspring)}", "name":surn + rng.choice(["宁","安","澄","昭","遥","真","元","清"]),
            "age":0, "alive":True, "world":player.world, "spirit_root":child_root,
            "spirit_root_name":self._npc_root_name(child_root), "cultivation_started":False,
            "realm_index":0, "layer":1, "path":player.technique.path if player.technique else player.path,
            "lifespan":rng.randint(80, 100), "parents":[player.name, str(companion.get("name", "道侣"))],
            "gender":rng.choice(["male", "female"]),
        }
        lineage_text = ""
        inheritance = MONSTER_BLOODLINE_SETTINGS.get("inheritance", {})
        if player.path == "monster" and bloodline_content_available() and rng.random() < float(inheritance.get("species_chance", 1.0)):
            species = MONSTER_SPECIES.get(str(player.monster_species_id or ""), {})
            base_evolution_id = species.get("base_evolution_id")
            child.update(
                path="monster", monster_species_id=player.monster_species_id,
                monster_evolution_id=base_evolution_id,
                monster_evolution_history=[base_evolution_id] if base_evolution_id else [],
                monster_bloodline_imprints=[
                    imprint for imprint in player.monster_bloodline_imprints
                    if rng.random() < float(inheritance.get("imprint_chance", 0.45))
                ],
                monster_lineage_origin=player.monster_evolution_id,
            )
            child["lifespan"] *= int(WORLD_SYSTEMS.get("monster_cultivation", {}).get("lifespan_multiplier", 3))
            lineage_text = f"并继承了{species.get('name', '妖族')}本源血脉"
            lineage_candidates: list[dict[str, Any]] = []
            for parent in (player.to_dict(), companion):
                lineage = parent.get("monster_custom_lineage")
                lineage_id = parent.get("monster_custom_lineage_id") or (
                    lineage.get("id") if isinstance(lineage, dict) else None
                )
                if not isinstance(lineage, dict) or not lineage_id or not isinstance(lineage.get("rules"), list):
                    continue
                if any(row["id"] == str(lineage_id) for row in lineage_candidates):
                    continue
                lineage_candidates.append({"id": str(lineage_id), "lineage": lineage})
            if lineage_candidates:
                inherited = rng.choice(lineage_candidates)
                child["monster_custom_lineage_id"] = inherited["id"]
                child["monster_custom_lineage"] = copy.deepcopy(inherited["lineage"])
                child["monster_custom_lineage"]["id"] = inherited["id"]
                lineage_text += f"，并承袭了祖血【{child['monster_custom_lineage'].get('name', inherited['id'])}】的定型规则"
        player.offspring.append(child)
        player.children += 1
        return f" 你们诞下一名后代{child['name']}；其{'身具' + child['spirit_root_name'] if has_root else '没有显现灵根'}{lineage_text}。"

    def _annual_offspring_and_family_update(self, game: GameState, rng: random.Random) -> list[str]:
        news: list[str] = []
        player = game.player
        family_ids = {npc.id for npc in game.family.npcs} if game.family else set()
        for child in player.offspring:
            if not child.get("alive", True) or child.get("id") in family_ids:
                continue
            child["age"] = int(child.get("age", 0)) + 1
            if child.get("lifespan") is not None and child["age"] >= int(child["lifespan"]):
                child["alive"] = False
                child["death_reason"] = "寿元耗尽"
                summary = f"后代{child['name']}寿元耗尽，安然辞世。"
                if child.get("world", player.world) == player.world:
                    news.append(f"{player.age}岁：{summary}")
                game.history.append(HistoryRecord(
                    "SYS_CHILD_FALL",1,player.age,"血脉凋零",child["id"],"child_fallen",summary,
                    {"child_id":child["id"],"alive":[True,False]},
                    ["system","family","offspring","world_news",f"world:{child.get('world',player.world)}"],
                ))
                continue
            if child.get("spirit_root", "none") != "none" and not child.get("cultivation_started") and child["age"] >= int(WORLD_SYSTEMS["family"]["cultivation_start_age"]):
                child.update(cultivation_started=True, realm_index=1, layer=1, lifespan=rng.randint(100, 120))
                summary = f"后代{child['name']}在{child['age']}岁正式引气入体，踏入练气一层。"
                news.append(f"{player.age}岁：{summary}")
                game.history.append(HistoryRecord(
                    "SYS_CHILD_CULTIVATION",1,player.age,"血脉问道",child["id"],"cultivator",summary,
                    {"child_id":child["id"],"realm_index":1},["system","family","offspring",f"world:{child.get('world',player.world)}"],
                ))
            if child.get("cultivation_started"):
                descendant = SectNpc(
                    str(child["id"]), str(child["name"]), "后代",
                    int(child.get("realm_index", 1)), int(child.get("layer", 1)),
                    int(child["age"]), child.get("lifespan"),
                    spirit_root=str(child.get("spirit_root", "none")),
                    cultivation_progress=float(child.get("cultivation_progress", 0)),
                    path=str(child.get("path", player.path)), race=player.race,
                    world=str(child.get("world", player.world)),
                    gender=str(child.get("gender") or self._stable_gender(str(child.get("id", "")))),
                    next_tribulation_age=child.get("next_tribulation_age"),
                    tribulation_count=int(child.get("tribulation_count", 0)),
                    tribulation_power=child.get("tribulation_power"),
                )
                tribulation = self._resolve_npc_periodic_tribulation(game, descendant, rng, "后代")
                result = None if not descendant.alive else self._advance_npc_cultivation(descendant, rng)
                child.update(
                    age=descendant.age, alive=descendant.alive, realm_index=descendant.realm_index,
                    layer=descendant.layer, lifespan=descendant.lifespan, world=descendant.world,
                    cultivation_progress=descendant.cultivation_progress,
                    next_tribulation_age=descendant.next_tribulation_age,
                    tribulation_count=descendant.tribulation_count,
                    tribulation_power=descendant.tribulation_power,
                    death_reason=descendant.death_reason,
                )
                if tribulation and child.get("world") == player.world:
                    news.append(f"{player.age}岁：{tribulation}")
                if result:
                    summary = f"后代{child['name']}由{result['old']}突破至{result['new']}。"
                    if child.get("world") == player.world:
                        news.append(f"{player.age}岁：{summary}")
                    game.history.append(HistoryRecord(
                        "SYS_CHILD_BREAKTHROUGH",1,player.age,"后辈破境",child["id"],result["type"],summary,
                        {"child_id":child["id"],"realm":[result["old"],result["new"]]},
                        ["system","family","offspring","world_news",f"world:{child.get('world',player.world)}"],
                    ))
        family = game.family
        if not family or family.extinct:
            return news
        for npc in family.npcs:
            if not npc.alive:
                continue
            child = next((row for row in player.offspring if row.get("id") == npc.id), None)
            npc.age += 1
            tribulation = self._resolve_npc_periodic_tribulation(game, npc, rng, family.name)
            if tribulation and family.world == player.world:
                news.append(f"{player.age}岁：{tribulation}")
            if not npc.alive:
                if child:
                    child.update(age=npc.age,alive=False,death_reason=npc.death_reason)
                continue
            if npc.lifespan is not None and npc.age >= npc.lifespan:
                npc.alive = False
                npc.death_reason = "寿元耗尽，族谱除名"
                if child:
                    child.update(age=npc.age,alive=False,death_reason=npc.death_reason)
                summary = f"{family.name}{npc.title}{npc.name}寿尽坐化。"
                news.append(f"{player.age}岁：{summary}")
                game.history.append(HistoryRecord(
                    "SYS_FAMILY_MEMBER_FALL",1,player.age,"家族讣告",npc.id,"npc_fallen",summary,
                    {"npc_id":npc.id},["system","family","npc","world_news",f"world:{family.world}"],
                ))
                continue
            result = self._advance_npc_cultivation(npc, rng)
            if child:
                child.update(
                    age=npc.age,alive=npc.alive,realm_index=npc.realm_index,layer=npc.layer,
                    lifespan=npc.lifespan,world=npc.world,cultivation_progress=npc.cultivation_progress,
                    next_tribulation_age=npc.next_tribulation_age,tribulation_count=npc.tribulation_count,
                    tribulation_power=npc.tribulation_power,death_reason=npc.death_reason,
                )
            if result:
                summary = f"{family.name}{npc.title}{npc.name}由{result['old']}突破至{result['new']}。"
                if family.world == player.world:
                    news.append(f"{player.age}岁：{summary}")
                game.history.append(HistoryRecord(
                    "SYS_FAMILY_MEMBER_BREAKTHROUGH",1,player.age,"家族喜报",npc.id,result["type"],summary,
                    {"npc_id":npc.id,"realm":[result["old"],result["new"]]},
                    ["system","family","npc","world_news",f"world:{family.world}"],
                ))
        if not any(npc.alive for npc in family.npcs):
            family.extinct = True
            game.history.append(HistoryRecord(
                "SYS_FAMILY_EXTINCT",1,player.age,"家族断绝",family.id,"extinct",
                f"{family.name}最后一名在册修士陨落，修仙家族传承断绝。",
                {"family_id":family.id,"extinct":True},
                ["system","family","extinction","world_news",f"world:{family.world}"],
            ))
            return news
        family_rules = WORLD_SYSTEMS["family"]
        if (
            player.age % int(family_rules["recruitment_interval_years"]) == 0
            and len([npc for npc in family.npcs if npc.alive]) < int(family_rules["max_members"])
        ):
            newcomer = self._recruit_sect_npc(family, player.age, rng)
            newcomer.title = "外姓门人"
            summary = f"低阶散修{newcomer.name}请求依附{family.name}，列入外门。"
            game.history.append(HistoryRecord(
                "SYS_FAMILY_RECRUIT",1,player.age,"家族收录外姓",newcomer.id,"npc_joined",summary,
                {"npc_id":newcomer.id},["system","family","recruitment",f"world:{family.world}"],
            ))
        return news

    def _relationship_cultivation_perception(
        self, game: GameState, person: dict[str, Any], title: str = "故交",
    ) -> dict[str, Any]:
        """Apply the same secret-art visibility rules to compact relationship snapshots."""
        realm_index = int(person.get("realm_index", 0))
        layer = int(person.get("layer", 1))
        shell = SectNpc(
            str(person.get("id", person.get("name", "relationship"))),
            str(person.get("name", "无名修士")), title, realm_index, layer,
            int(person.get("age", 1)), person.get("lifespan"),
            path=str(person.get("path", "dao")), race=str(person.get("race", "human")),
            world=str(person.get("world", game.player.world)),
            combat_factor=float(person.get("combat_factor", 1.0)),
            concealed_realm_index=person.get("concealed_realm_index"),
            concealed_layer=person.get("concealed_layer"),
        )
        perception = self._npc_cultivation_perception(game, shell)
        # Persist a deterministic disguise into the relationship snapshot so
        # leaving and re-entering the panel cannot reroll the NPC's public face.
        person["concealed_realm_index"] = shell.concealed_realm_index
        person["concealed_layer"] = shell.concealed_layer
        if perception["display_power"] is not None and person.get("combat_power") is not None:
            actual = max(1.0, self._npc_power(shell))
            perception["display_power"] = round(
                float(person["combat_power"]) * float(perception["display_power"]) / actual, 1,
            )
        return perception

    def _relationship_snapshot(
        self, person_id: str, name: str, realm_index: int, layer: int, source: str,
        age: int, lifespan: int | None, alive: bool = True, death_reason: str | None = None,
        spirit_root: str = "", cultivation_progress: float = 0.0,
        path: str = "dao", race: str = "human", world: str = "human",
        main_technique_id: str | None = None, affinity: float = 20.0,
        gender: str = "",
    ) -> dict[str, Any]:
        shell = SectNpc(
            person_id, name, "", realm_index, layer, age, int(lifespan or age + 1),
            spirit_root=spirit_root, cultivation_progress=cultivation_progress,
            path=path, race=race, world=world, gender=gender,
        )
        return {
            "id": person_id, "name": name, "realm_index": realm_index, "layer": layer,
            "realm_name": self._npc_realm_name(shell), "source": source,
            "age": age, "lifespan": lifespan, "alive": alive, "death_reason": death_reason,
            "spirit_root": spirit_root, "spirit_root_name": self._npc_root_name(spirit_root),
            "cultivation_progress": cultivation_progress,
            "path": path, "path_name": PATH_NAMES.get(path, path), "race": race,
            "race_name": RACE_DEFINITIONS.get(race, {"name": race})["name"], "world": world,
            "items": {}, "techniques": [], "last_requests": {}, "last_interactions": {},
            "main_technique_id": main_technique_id, "affinity": affinity,
            "gender": shell.gender, "gender_name": gender_name(shell.gender),
            "next_tribulation_age": None, "tribulation_count": 0, "tribulation_power": None,
        }

    def _generated_relationship(self, player: Player, role: str, rng: random.Random) -> dict[str, Any]:
        surnames = ["顾", "叶", "陆", "楚", "白", "谢", "云", "林"]
        given = ["玄真", "清微", "问岳", "照霜", "长离", "守一", "青崖", "明河"]
        name = rng.choice(surnames) + rng.choice(given)
        if role == "master":
            realm_index = min(5, player.realm_index + 1)
            layer = rng.randint(1, 3)
        elif role == "companion":
            realm_index = player.realm_index
            layer = player.layer
        elif player.layer > 1:
            realm_index = player.realm_index
            layer = rng.randint(1, player.layer - 1)
        else:
            realm_index = max(0, player.realm_index - 1)
            layer = 1
        person_id = f"event_{role}_{player.age}_{rng.randrange(1_000_000)}"
        age_ranges = {
            0: (14, 55), 1: (18, 90), 2: (55, 190), 3: (180, 450),
            4: (450, 1200), 5: (1200, 2600), 6: (2800, 7000),
            7: (7000, 18000), 8: (18000, 80000),
        }
        age = rng.randint(*age_ranges[realm_index])
        span = REALMS[realm_index].lifespan
        lifespan = max(age + 1, rng.randint(*span)) if span else None
        spirit_root = self._random_npc_root(realm_index, rng) if realm_index > 0 else "none"
        path = (player.technique.path if player.technique else player.path) if role == "companion" else rng.choice(list(PATH_NAMES))
        lifespan = self._scale_npc_lifespan(lifespan, path, age)
        return self._relationship_snapshot(
            person_id, name, realm_index, layer, "event", age, lifespan,
            spirit_root=spirit_root, path=path, race="human", world=player.world,
            main_technique_id=player.technique.id if role == "companion" and player.technique else None,
            affinity=28.0 if role == "companion" else 20.0,
        )

    def _sync_relationship_records(self, game: GameState) -> bool:
        """补齐旧存档字段，并让宗门师徒信息跟随真实 NPC。"""
        changed = False
        relations = [entry for entry in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.concubines, *game.player.disciples, *game.player.disciple_requests] if entry]
        for relation in relations:
            before = copy.deepcopy(relation)
            source = relation.get("source", "event")
            npc = self._find_npc(game, str(relation.get("npc_id") or relation.get("id")))
            if not npc and source not in {"world", "event", "captive", "relationship"}:
                npc = next((entry for entry in game.sects.get(source, SectState(source, "")).npcs if entry.id == relation.get("id")), None)
            if npc:
                relation.update(
                    realm_index=npc.realm_index, layer=npc.layer, realm_name=self._npc_realm_name(npc),
                    age=npc.age, lifespan=npc.lifespan, alive=npc.alive, death_reason=npc.death_reason,
                    spirit_root=npc.spirit_root, spirit_root_name=self._npc_root_name(npc.spirit_root),
                    cultivation_progress=npc.cultivation_progress,
                    path=npc.path, path_name=PATH_NAMES.get(npc.path, npc.path), race=npc.race,
                    race_name=RACE_DEFINITIONS.get(npc.race, {"name": npc.race})["name"], world=npc.world,
                    affinity=npc.affinity if npc.affinity is not None else relation.get("affinity", 20.0),
                    next_tribulation_age=npc.next_tribulation_age,
                    tribulation_count=npc.tribulation_count,
                    tribulation_power=npc.tribulation_power,
                )
            else:
                realm_index = int(relation.get("realm_index", 0))
                age = int(relation.get("age", {0: 30, 1: 50, 2: 120, 3: 300, 4: 800, 5: 1800}.get(realm_index, 30)))
                span = REALMS[realm_index].lifespan
                relation.setdefault("age", age)
                relation.setdefault("lifespan", max(age + 1, span[1]) if span else None)
                relation.setdefault("alive", True)
                relation.setdefault("death_reason", None)
                relation.setdefault(
                    "spirit_root",
                    self._random_npc_root(realm_index, random.Random(f"relation:{relation.get('id', '')}"))
                    if realm_index > 0 else "none",
                )
                relation.setdefault("cultivation_progress", 0.0)
                relation.setdefault("path", "dao")
                relation.setdefault("race", "human")
                relation.setdefault("world", "human")
                shell = SectNpc(
                    str(relation.get("id", "relation")), str(relation.get("name", "无名")), "",
                    realm_index, int(relation.get("layer", 1)), age, int(relation.get("lifespan") or age + 1),
                    path=str(relation.get("path", "dao")),
                )
                relation["realm_name"] = self._npc_realm_name(shell)
                relation["spirit_root_name"] = self._npc_root_name(relation["spirit_root"])
                relation["path_name"] = PATH_NAMES.get(relation["path"], relation["path"])
                relation["race_name"] = RACE_DEFINITIONS.get(relation["race"], {"name": relation["race"]})["name"]
            relation.setdefault("items", {})
            relation.setdefault("techniques", [])
            relation.setdefault("last_requests", {})
            relation.setdefault("last_interactions", {})
            relation.setdefault("affinity", 20.0)
            relation.setdefault("main_technique_id", None)
            relation.setdefault("breakthrough_bonus", 0.0)
            relation.setdefault("next_tribulation_age", None)
            relation.setdefault("tribulation_count", 0)
            relation.setdefault("tribulation_power", None)
            changed = changed or relation != before
        return changed

    def _annual_relationship_update(self, game: GameState, rng: random.Random | None = None) -> None:
        self._sync_relationship_records(game)
        player = game.player
        rng = rng or random.Random(f"relationships:{game.seed}:{player.age}")
        event_relations = [
            entry for entry in [player.master, player.dao_companion, *player.dao_friends, *player.concubines, *player.disciples, *player.disciple_requests]
            if entry and not self._find_npc(game, str(entry.get("npc_id") or entry.get("id", "")))
        ]
        for relation in event_relations:
            if not relation.get("alive", True):
                continue
            relation["age"] = int(relation.get("age", 0)) + 1
            lifespan = relation.get("lifespan")
            if lifespan is not None and relation["age"] >= lifespan:
                relation["alive"] = False
                relation["death_reason"] = "寿元耗尽，坐化尘世"
                is_companion = relation is player.dao_companion
                is_friend = relation in player.dao_friends
                is_concubine = relation in player.concubines
                game.history.append(HistoryRecord(
                    "SYS_RELATION_FALL", 1, player.age, "道侣坐化" if is_companion else "道友坐化" if is_friend else "侍妾坐化" if is_concubine else "师门故人坐化", None, "relation_fallen",
                    f"{relation['name']}寿元已尽，这段尘缘只余旧忆。",
                    {"relation_id": relation["id"], "alive": [True, False]}, ["system", "relationship", "friend" if is_friend else "dao_companion" if is_companion else "concubine" if is_concubine else "master", "death"],
                ))
                continue
            shell = SectNpc(
                id=str(relation["id"]), name=str(relation["name"]), title="",
                realm_index=int(relation["realm_index"]), layer=int(relation["layer"]),
                age=int(relation["age"]), lifespan=relation.get("lifespan"),
                spirit_root=str(relation.get("spirit_root", "")),
                cultivation_progress=float(relation.get("cultivation_progress", 0.0)),
                path=str(relation.get("path", "dao")), race=str(relation.get("race", "human")),
                world=str(relation.get("world", "human")),
                next_tribulation_age=relation.get("next_tribulation_age"),
                tribulation_count=int(relation.get("tribulation_count", 0)),
                tribulation_power=relation.get("tribulation_power"),
            )
            tribulation = self._resolve_npc_periodic_tribulation(game, shell, rng, "道侣" if relation is player.dao_companion else "")
            if tribulation and not shell.alive:
                relation.update(alive=False, death_reason=shell.death_reason)
                continue
            breakthrough = self._advance_npc_cultivation(
                shell, rng, allow_spirit_crossing=True,
                breakthrough_bonus=float(relation.get("breakthrough_bonus", 0)),
            )
            relation.update(
                realm_index=shell.realm_index, layer=shell.layer, realm_name=self._npc_realm_name(shell),
                lifespan=shell.lifespan, cultivation_progress=shell.cultivation_progress,
                spirit_root=shell.spirit_root, spirit_root_name=self._npc_root_name(shell.spirit_root),
                path=shell.path, path_name=PATH_NAMES.get(shell.path, shell.path), race=shell.race,
                race_name=RACE_DEFINITIONS.get(shell.race, {"name": shell.race})["name"], world=shell.world,
                next_tribulation_age=shell.next_tribulation_age,
                tribulation_count=shell.tribulation_count,
                tribulation_power=shell.tribulation_power,
            )
            if breakthrough:
                is_companion = relation is player.dao_companion
                is_friend = relation in player.dao_friends
                is_concubine = relation in player.concubines
                game.history.append(HistoryRecord(
                    "SYS_RELATION_BREAKTHROUGH", 1, player.age, "道侣破境" if is_companion else "道友破境" if is_friend else "侍妾破境" if is_concubine else "师门破境", None, "npc_breakthrough",
                    f"{relation['name']}凭借{relation['spirit_root_name']}由{breakthrough['old']}突破至{breakthrough['new']}。",
                    {"relation_id": relation["id"], "realm": [breakthrough["old"], breakthrough["new"]]}, ["system", "relationship", "friend" if is_friend else "dao_companion" if is_companion else "concubine" if is_concubine else "master", "npc"],
                ))
        expired = [entry for entry in player.disciple_requests if not entry.get("alive", True)]
        if expired:
            expired_ids = {entry["id"] for entry in expired}
            player.disciple_requests = [entry for entry in player.disciple_requests if entry["id"] not in expired_ids]
        self._sync_relationship_records(game)

    def _sync_party_state(self, game: GameState) -> bool:
        """Discard references that can no longer represent an active companion."""
        valid: list[dict[str, Any]] = []
        seen: set[str] = set()
        for reference in game.player.party:
            npc_id = str(reference.get("id", ""))
            companion = game.player.dao_companion
            if companion and companion.get("id") == npc_id:
                if npc_id and npc_id not in seen and companion.get("alive", True) and companion.get("world") == game.player.world:
                    seen.add(npc_id)
                    valid.append({"id": npc_id})
                continue
            npc = self._find_npc(game, npc_id)
            relation = next((entry for entry in [game.player.master, *game.player.dao_friends, *game.player.disciples] if entry and str(entry.get("id")) == npc_id), None)
            available = bool(
                (npc and npc.alive and npc.world == game.player.world)
                or (relation and relation.get("alive", True) and relation.get("world") == game.player.world)
            )
            if not npc_id or npc_id in seen or not available:
                continue
            seen.add(npc_id)
            valid.append({"id": npc_id})
        if valid == game.player.party:
            return False
        game.player.party = valid
        return True

from __future__ import annotations

import copy
import math
import random
from typing import Any

from ..content_registry import REALMS, WORLD_SYSTEMS
from ..models import HistoryRecord, SectNpc
from ..rules import add_item, remove_item, has_item, expected_combat_power, combat_power, max_hp, max_mp
from ..runtime import decode_rng, encode_rng, now_iso
from .crafting_system import make_crafting_material_instance, store_crafted_artifact
from .formation_system import make_formation_material_instance
from .exchange_system import EXCHANGE_VENUES
from .possession_system import advance_player_age


POLICIES = {"economy": "重商兴利", "materials": "积储资材", "cultivation": "尊修育才"}
KINDS = {"supply": "提交特定物品", "escort": "护送雇主", "bounty": "击杀悬赏修士",
         "recruit": "招募人手", "formation": "炼制阵法", "weapon": "炼制武器", "intel": "获取情报"}
RANKS = ["成员", "使节", "特使"]
CROSS_ALLIANCES = {
    "xuanji": ("璇玑商盟", "spirit", ["spirit", "true_demon", "monster_realm", "human"]),
    "jiukun": ("九坤商盟", "phantom_underworld", ["phantom_underworld", "true_demon", "hell"]),
    "taiyuan": ("太元商盟", "celestial", ["celestial", "asura", "nether"]),
}


class MerchantSystemMixin:
    """World-local offices, persistent commissions and independently held membership."""

    @staticmethod
    def _merchant_realm_cap(world):
        profile = WORLD_SYSTEMS["world_profiles"][world]
        return int(profile.get("npc_realm_cap", {1: 5, 2: 8, 3: 12}[int(profile["tier"])]))

    def _ensure_merchant(self, game) -> bool:
        if game.merchant_state.get("version") == 1:
            return False
        state = game.merchant_state = {
            "version": 1, "worlds": {}, "membership": None, "influence": {},
            "posted": [], "active": None, "completed": [], "notices": [],
            "last_age": game.player.age, "sequence": 0,
        }
        for world, geography in self.maps.worlds.items():
            profile = WORLD_SYSTEMS["world_profiles"][world]
            safe = [row["id"] for row in geography["locations"] if not row.get("min_realm_index")]
            headquarters = EXCHANGE_VENUES[world]
            sites = [place for place in safe if place != headquarters]
            ids = [key for key, (_, _, worlds) in CROSS_ALLIANCES.items() if world in worlds]
            ids += [f"{world}-{index}" for index in range(3 - len(ids))]
            alliances = []
            for index, alliance_id in enumerate(ids):
                rng = random.Random(f"merchant:{game.seed}:{world}:{alliance_id}")
                cross = CROSS_ALLIANCES.get(alliance_id)
                name = cross[0] if cross else WORLD_SYSTEMS["world_names"][world] + ["通宝商盟", "万珍商盟", "聚贤商盟"][index]
                realm_index = self._merchant_realm_cap(world)
                leader = SectNpc(f"merchant-{world}-{alliance_id}-leader", rng.choice(["沈", "陆", "宁", "虞"]) + rng.choice(["望舒", "玄衡", "听澜", "怀璧"]),
                                 "分盟主" if cross and world != cross[1] else "盟主", realm_index,
                                 REALMS[realm_index].layers, 100, None, world=world)
                locations = sites[index::3] or sites[:1]
                locations = locations[:3]
                chief_realm = 8 if alliance_id in {"xuanji", "jiukun"} else realm_index
                chief_power = expected_combat_power(chief_realm, REALMS[chief_realm].layers) * 35
                offices = []
                for site in locations:
                    deputy = copy.deepcopy(leader)
                    deputy.id += f"-{site}"
                    deputy.name = rng.choice(["许", "苏", "秦"]) + rng.choice(["青川", "知微", "照月"])
                    deputy.title = "分部主事"
                    deputy.realm_index = max(1, realm_index - 1)
                    deputy.layer = REALMS[deputy.realm_index].layers
                    offices.append({"location_id": site, "leader": deputy.to_dict()})
                alliances.append({
                    "id": alliance_id, "name": name, "world": world, "hq": headquarters,
                    "home_world": cross[1] if cross else world, "linked_worlds": cross[2] if cross else [world],
                    "cross_world": bool(cross), "leader": leader.to_dict(), "offices": offices,
                    "chief_name": {"xuanji": "璇玑子", "jiukun": "九坤上人", "taiyuan": "太元道君"}.get(alliance_id, leader.name),
                    "chief_realm": chief_realm, "chief_power": chief_power if cross else 0,
                    "reserves": (250000 if cross else 8000) * int(profile["tier"]),
                    "policy": list(POLICIES)[index], "next_policy_age": game.player.age + 12 + index * 3,
                    "relation": "互通有无", "board_epoch": 0,
                })
            state["worlds"][world] = alliances
        return True

    def _merchant_alliance(self, game, world, alliance_id):
        return next((row for row in game.merchant_state["worlds"].get(world, []) if row["id"] == alliance_id), None)

    def _merchant_site(self, game, alliance):
        if game.player.world != alliance["world"]:
            return None
        location = game.player.location_id
        if location == alliance["hq"]:
            return "hq"
        if any(row["location_id"] == location for row in alliance["offices"]):
            return location
        return None

    @staticmethod
    def _merchant_influence_key(member):
        return f"{member['world']}:{member['alliance_id']}:{'hq' if member['site'] == 'hq' else 'offices'}"

    def _merchant_power(self, alliance):
        leader = alliance["leader"]
        power = expected_combat_power(leader["realm_index"], leader["layer"])
        power += sum(expected_combat_power(row["leader"]["realm_index"], row["leader"]["layer"]) for row in alliance["offices"])
        return round(power + alliance["chief_power"] + len(alliance["offices"]) * 5000 + alliance["reserves"] * 2)

    def _merchant_notice(self, game, message):
        notices = game.merchant_state["notices"]
        notices.append({"age": game.player.age, "message": message})
        del notices[:-30]
        game.history.append(HistoryRecord("SYS_MERCHANT", 1, game.player.age, "商盟传讯", None, "notice", message, {}, ["system", "merchant", "world:global"]))

    def _merchant_materials(self, world):
        return sorted((row for row in self._crafting_material_defs().values() if row.get("world") == world),
                      key=lambda row: (int(row.get("tier", 1)), row["id"]))

    def _merchant_board(self, game, alliance):
        materials = self._merchant_materials(alliance["world"])
        if not materials:
            return []
        cap = self._merchant_realm_cap(alliance["world"])
        board = []
        for stars in range(1, 6):
            target_realm = max(0, cap - 5 + stars)
            power = expected_combat_power(target_realm, min(3, REALMS[target_realm].layers))
            definition = materials[min(len(materials) - 1, (stars - 1) * len(materials) // 5)]
            for kind_index, (kind, name) in enumerate(KINDS.items()):
                identifier = f"{alliance['world']}:{alliance['id']}:{alliance['board_epoch']}:{kind}:{stars}"
                if identifier in game.merchant_state["completed"]:
                    continue
                base_years = stars * 2 + kind_index % 3
                # Exact year durations, accelerated by realm without rounding to action units.
                years = max(1, math.ceil(base_years / (1 + max(0, game.player.realm_index - target_realm) * .7)))
                material_cost = int(definition["base_material_value"]) * stars
                value = max(100 * stars ** 2, int(power * .1), material_cost * 2)
                scale = 1 + min(.5, math.log10(max(1, self._merchant_power(alliance))) / 20)
                reward = {
                    "stones": round(value * scale * (1.8 if alliance["policy"] == "economy" else 1)),
                    "materials": stars * (2 if alliance["policy"] == "materials" else 1),
                    "opportunity": round((5 * stars + power ** .35) * (2 if alliance["policy"] == "cultivation" else 1), 1),
                    "karma": stars * 3, "influence": stars * 12,
                }
                board.append({"id": identifier, "kind": kind, "name": name, "stars": stars,
                              "realm": target_realm, "power": round(power), "years": years,
                              "definition_id": definition["id"], "material_name": definition["name"],
                              "quantity": stars, "reward": reward, "policy": alliance["policy"],
                              "world": alliance["world"], "alliance_id": alliance["id"]})
        return board

    def _advance_merchant_year(self, game):
        self._ensure_merchant(game)
        state = game.merchant_state
        if game.player.age <= state["last_age"]:
            return
        state["last_age"] = game.player.age
        for world, alliances in state["worlds"].items():
            for alliance in alliances:
                if game.player.age < alliance["next_policy_age"]:
                    continue
                rng = random.Random(f"merchant-policy:{game.seed}:{world}:{alliance['id']}:{alliance['next_policy_age']}")
                policies = [key for key in POLICIES if key != alliance["policy"]]
                weights = [1.0] * len(policies)
                if self._intrigue_enabled():
                    npc = SectNpc.from_dict(alliance["leader"])
                    personality = self._ensure_intrigue_personality(game, npc)["primary"]
                    preferred = "economy" if personality in {"greedy", "smooth", "open"} else "materials" if personality in {"suspicious", "conservative", "paranoid"} else "cultivation"
                    weights = [4.0 if key == preferred else 1.0 for key in policies]
                alliance["policy"] = rng.choices(policies, weights)[0]
                alliance["next_policy_age"] = game.player.age + rng.randint(12, 24)
                alliance["board_epoch"] += 1
                occupied = {alliance["hq"], *(row["location_id"] for row in alliance["offices"])}
                expansion = [row["id"] for row in self.maps.worlds[world]["locations"]
                             if not row.get("min_realm_index") and row["id"] not in occupied]
                if expansion and len(alliance["offices"]) < 4 and alliance["reserves"] >= 20000 and rng.random() < .2:
                    location = rng.choice(expansion)
                    deputy = copy.deepcopy(alliance["offices"][0]["leader"])
                    deputy.update(id=f"merchant-{world}-{alliance['id']}-{location}", name=rng.choice(["叶知秋", "方清和", "江行远"]))
                    alliance["offices"].append({"location_id": location, "leader": deputy})
                    alliance["reserves"] -= 10000
                elif len(alliance["offices"]) > 1 and alliance["reserves"] < 3000:
                    member = state["membership"] or {}
                    removable = [office for office in alliance["offices"] if not (
                        member.get("world") == world and member.get("alliance_id") == alliance["id"]
                        and member.get("site") == office["location_id"])]
                    if removable:
                        alliance["offices"].remove(removable[-1])
                        alliance["reserves"] += 2000
                rival = rng.choice([row for row in alliances if row is not alliance])
                if rng.random() < .5:
                    gain = max(50, min(alliance["reserves"], rival["reserves"]) // 40)
                    alliance["reserves"] += gain
                    rival["reserves"] += gain
                    alliance["relation"] = f"与{rival['name']}合作通商"
                else:
                    transfer = min(rival["reserves"] // 20, max(30, alliance["reserves"] // 100))
                    alliance["reserves"] += transfer
                    rival["reserves"] -= transfer
                    alliance["relation"] = f"与{rival['name']}竞争商路"
        for order in state["posted"]:
            if order["status"] not in {"open", "working"}:
                continue
            if order.get("target_id"):
                target = self._find_npc(game, order["target_id"])
                if not target or not target.alive:
                    order["status"] = "cancelled"
                    add_item(game.player, "spirit_stone", order["principal"])
                    self._merchant_notice(game, f"委托「{order['name']}」目标已失效，取消委托并全额退还本金 {order['principal']:,} 灵石。")
                    continue
            if game.player.age >= order["deadline"]:
                order["status"] = "cancelled"
                add_item(game.player, "spirit_stone", order["principal"])
                self._merchant_notice(game, f"委托「{order['name']}」逾期取消，悬赏本金 {order['principal']:,} 灵石已全额退还；手续费不退。")
                continue
            if order["status"] == "open" and game.player.age >= order["check_age"]:
                rng = random.Random(f"merchant-order:{game.seed}:{order['id']}:{order['check_age']}")
                order["check_age"] = game.player.age + max(1, order["years"] // 3)
                if rng.random() < order["accept_chance"]:
                    order.update(status="working", started_age=game.player.age,
                                 finish_age=game.player.age + order["years"], worker=rng.choice(["青衣散人", "商路行者", "无尘客", "白鹤道人"]))
                    order["will_finish"] = rng.random() < .88
                    self._merchant_notice(game, f"{order['worker']}接取了「{order['name']}」，预计道历第 {order['finish_age']} 年完成。")
            if order["status"] == "working" and game.player.age >= order["finish_age"] and order["will_finish"]:
                self._merchant_deliver_order(game, order)
                order["status"] = "completed"
                alliance = self._merchant_alliance(game, order["world"], order["alliance_id"])
                alliance["reserves"] += max(1, order["fee"] + order["principal"] // 10)
                self._merchant_notice(game, f"委托「{order['name']}」已完成：{order['delivery']}。")

    def _merchant_deliver_order(self, game, order):
        rng = random.Random(f"merchant-delivery:{game.seed}:{order['id']}")
        kind, stars = order["kind"], order["stars"]
        if kind == "supply":
            definition = self._crafting_material_defs()[order["definition_id"]]
            for _ in range(order["quantity"]):
                game.player.crafting_materials.append(make_crafting_material_instance(definition, rng, source="商盟委托", origin_world=order["source_world"]))
            order["delivery"] = f"获得{definition['name']} ×{order['quantity']}"
        elif kind == "weapon":
            power = order["principal"] * .08
            artifact = {"id": f"merchant-weapon-{game.id}-{order['id']}", "name": f"商盟订制灵刃·{stars}星",
                        "mold_id": "merchant_blade", "mold_name": "商盟灵刃", "quality": "normal", "quality_name": "合格",
                        "creator_name": order["worker"], "created_year": game.player.age,
                        "actual_stats": {"combat_power": power}, "designed_stats": {"combat_power": power},
                        "anchor_value": round(order["principal"] * .5), "materials": [], "combat_effects": [], "is_natal": False}
            store_crafted_artifact(game.player, artifact)
            order["delivery"] = f"获得订制灵刃，基础战力 {power:,.0f}"
        elif kind == "formation":
            definitions = [row for row in self._formation_material_defs().values() if row.get("world") == order["source_world"]]
            definition = sorted(definitions, key=lambda row: row.get("base_value", 1))[min(len(definitions) - 1, stars - 1)]
            for _ in range(stars + 1):
                game.player.formation_materials.append(make_formation_material_instance(definition, source="商盟炼阵委托", origin_world=order["source_world"]))
            game.player.formation_sequence += 1
            game.player.formation_loadouts.append({"id": f"formation-{game.id}-{game.player.formation_sequence}",
                "name": f"商盟{stars}星护行阵", "slots": [definition["id"]] * (stars + 1) + [None] * (8 - stars),
                "created_year": game.player.age})
            order["delivery"] = f"获得{stars}星护行阵预设及{definition['name']}阵材套组 ×{stars + 1}，可在阵法面板启用"
        elif kind == "recruit":
            game.merchant_state.setdefault("hired_hands", 0)
            game.merchant_state["hired_hands"] += stars
            order["delivery"] = f"招得 {stars} 名商路人手，可协助后续护送、招募和情报任务"
        else:
            if kind == "bounty":
                target = self._find_npc(game, order["target_id"])
                self._apply_cultivator_kill(game, {"npc_id": target.id, "name": target.name,
                    "realm_index": target.realm_index, "faction_id": target.faction_id, "race": target.race}, rng)
                target.death_reason = f"被{order['worker']}依商盟悬赏击杀"
                self._tianji_handle_npc_kill(game, target.id)
            game.player.opportunity += stars * 20
            game.player.karma = max(0, game.player.karma - stars * 3)
            if kind == "intel":
                world = order["source_world"]
                detail = "、".join(row["name"] for row in self._merchant_materials(world))
                order["delivery"] = f"获得{WORLD_SYSTEMS['world_names'][world]}材料情报：{detail}；机缘 +{stars * 20}"
            else:
                order["delivery"] = f"{KINDS[kind]}完成，机缘 +{stars * 20}，因果 -{stars * 3}"

    def _merchant_task_ready(self, game, task):
        player = game.player
        if task["kind"] == "supply":
            rows = [row for row in player.crafting_materials if row["material_id"] == task["definition_id"]]
            if len(rows) < task["quantity"]:
                raise ValueError(f"需准备 {task['material_name']} ×{task['quantity']}（炼器材料背包）")
            return rows[:task["quantity"]]
        if task["kind"] == "weapon":
            rows = [row for row in player.crafted_artifacts if not row.get("is_natal") and not row.get("tianji")
                    and row.get("creator_id") == game.id and row["id"] not in task["existing_artifacts"]
                    and float(row.get("actual_stats", {}).get("combat_power", 0)) >= task["power"] * .1]
            if not rows:
                raise ValueError(f"需在接取后亲自炼制一件基础战力至少 {task['power'] * .1:,.0f} 的普通法宝，再提交委托")
            return rows[:1]
        if task["kind"] == "formation":
            rows = sorted(player.formation_materials, key=lambda row: row.get("base_value", 1), reverse=True)
            rows = [row for row in rows if row.get("acquired_tier", 1) >= max(1, task["realm"] - 1)]
            if len(rows) < task["stars"] + 1:
                raise ValueError(f"炼阵需 {task['stars'] + 1} 件至少 {max(1, task['realm'] - 1)} 阶闲置阵材，在商盟工坊炼制后交付雇主")
            return rows[:task["stars"] + 1]
        return []

    def _merchant_work(self, game, rng):
        state = game.merchant_state
        task = state["active"]
        if not task:
            raise ValueError("没有待完成的商盟任务")
        if game.player.world != task["world"]:
            raise ValueError("请返回任务所在界面")
        materials = self._merchant_task_ready(game, task)
        news = []
        while task["worked"] < task["years"]:
            advance_player_age(game.player)
            task["worked"] += 1
            continue_world = self._advance_world_year(game, rng, news, encounters=False)
            if game.player.alive:
                self._advance_soul_erosion_time(game, 1)
            if not continue_world or not game.player.alive or game.pending_event:
                self._merchant_notice(game, "商盟任务进度已保留，处理当前状况后可继续。")
                return
        kind = task["kind"]
        succeeded = True
        detail = ""
        if kind in {"bounty", "escort"}:
            target = {"target_name": "悬赏恶修" if kind == "bounty" else "劫道修士", "target_power": task["power"],
                      "target_realm_index": task["realm"], "target_layer": 3, "combat_type": "cultivator",
                      "kill_karma": False, "player_defending": kind == "escort"}
            outcome, detail = self._combat(game, target, kind == "bounty", rng)
            succeeded = outcome == "killed" if kind == "bounty" else outcome in {"victory", "victory_escape", "killed"}
        elif kind in {"recruit", "intel"}:
            hands = state.get("hired_hands", 0)
            chance = min(.98, .65 + (game.player.realm_index - task["realm"]) * .06 + hands * .03)
            succeeded = rng.random() < max(.15, chance)
            if hands:
                state["hired_hands"] -= 1
        if not succeeded:
            state["active"] = None
            self._merchant_notice(game, f"{task['stars']}星「{task['name']}」失败，未获得报酬。{detail}")
            return
        if kind == "supply":
            for row in materials:
                game.player.crafting_materials.remove(row)
        elif kind == "weapon":
            artifact = materials[0]
            remove_item(game.player, artifact["id"])
            game.player.crafted_artifacts.remove(artifact)
        elif kind == "formation":
            for row in materials:
                game.player.formation_materials.remove(row)
            self._grant_art_experience(game.player, "formation", task["stars"] * 20)
        reward = task["reward"]
        add_item(game.player, "spirit_stone", reward["stones"])
        game.player.opportunity += reward["opportunity"]
        game.player.karma = max(0, game.player.karma - reward["karma"])
        definition = self._crafting_material_defs()[task["definition_id"]]
        for _ in range(reward["materials"]):
            game.player.crafting_materials.append(make_crafting_material_instance(definition, rng, source="商盟报酬", origin_world=task["world"]))
        key = task["influence_key"]
        state["influence"][key] = state["influence"].get(key, 0) + reward["influence"]
        alliance = self._merchant_alliance(game, task["world"], task["alliance_id"])
        alliance["reserves"] += max(20, reward["stones"] // 5)
        state["completed"].append(task["id"])
        state["completed"] = state["completed"][-350:]
        state["active"] = None
        self._merchant_notice(game, f"完成{task['stars']}星「{task['name']}」，灵石 +{reward['stones']:,}，材料 +{reward['materials']}，机缘 +{reward['opportunity']}，因果 -{reward['karma']}，商盟影响力 +{reward['influence']}。{detail}")

    def _merchant_passage(self, game, alliance, destination):
        member = game.merchant_state["membership"]
        if member["site"] != "hq" or member["rank"] < 1 or self._merchant_site(game, alliance) != "hq":
            raise ValueError("只有在任总部或分总部使节、特使，可从总部启用逆灵通道")
        if not alliance["cross_world"] or destination not in alliance["linked_worlds"] or destination == game.player.world:
            raise ValueError("商盟没有通往该界面的逆灵通道")
        if not WORLD_SYSTEMS["world_profiles"][destination].get("enabled", True):
            raise ValueError("该界面尚未开放")
        if game.player.cultivation_suppression:
            raise ValueError("请先解除秘法压制")
        price = self._merchant_passage_cost(game, destination)
        if not has_item(game.player, "spirit_stone", price):
            raise ValueError(f"逆灵通道需支付 {price:,} 灵石")
        target_alliance = self._merchant_alliance(game, destination, alliance["id"])
        player = game.player
        hp_ratio, mp_ratio = player.hp / max(1, max_hp(player)), player.mp / max(1, max_mp(player))
        old_world = player.world
        cap = self._merchant_realm_cap(destination)
        cap_layer = 3 if cap == 5 else REALMS[cap].layers
        # The reverse-spirit route into the monster world bears a tighter
        # visitor seal than its native cultivation ceiling. Keep native NPCs
        # and ordinary ascension rules independent of this paid passage.
        if destination == "monster_realm":
            cap, cap_layer = 7, 9
        sealed = player.sealed_cultivation
        original_realm, original_layer = (int(sealed["realm_index"]), int(sealed["layer"])) if sealed else (player.realm_index, player.layer)
        if (original_realm, original_layer) > (cap, cap_layer):
            if not sealed:
                sealed = {"realm_index": original_realm, "layer": original_layer, "upper_world": old_world,
                          "lifespan": player.lifespan, "tribulation_remaining": max(0, player.next_tribulation_age - player.age) if player.next_tribulation_age is not None else None}
            sealed["lower_world"] = destination
            sealed["merchant_passage"] = True
            player.sealed_cultivation = sealed
            player.realm_index, player.layer = cap, cap_layer
        elif sealed:
            player.realm_index, player.layer = original_realm, original_layer
            player.lifespan = sealed.get("lifespan")
            remaining = sealed.get("tribulation_remaining")
            player.next_tribulation_age = player.age + int(remaining) if remaining is not None else None
            player.sealed_cultivation = None
        remove_item(player, "spirit_stone", price)
        self._cancel_auction_for_world_change(game)
        player.world, player.location_id = destination, target_alliance["hq"]
        player.awaiting_major_breakthrough = False
        player.awaiting_minor_breakthrough = False
        player.awaiting_spirit_realm_crossing = False
        player.active_breakthrough_aids = []
        player.party = []
        player.hp, player.mp = max_hp(player) * hp_ratio, max_mp(player) * mp_ratio
        self._clear_market(game)
        # Credentials remain issued by the original regional HQ. Reciprocal
        # offices recognise the rank, but do not silently transfer local influence.
        self._merchant_notice(game, f"支付 {price:,} 灵石，乘{alliance['name']}逆灵通道抵达{WORLD_SYSTEMS['world_names'][destination]}。" + ("修为已按当地界面法则压制。" if player.sealed_cultivation else ""))

    @staticmethod
    def _merchant_passage_cost(game, destination):
        tier = WORLD_SYSTEMS["world_profiles"][destination]["tier"]
        original = game.player.sealed_cultivation or {}
        realm = int(original.get("realm_index", game.player.realm_index))
        return max(1000000, round(expected_combat_power(realm, int(original.get("layer", game.player.layer))) * 20)) * int(tier)

    def merchant_action(self, game_id, action, payload=None):
        game = self._load(game_id)
        self._ensure_merchant(game)
        payload = payload or {}
        player, state = game.player, game.merchant_state
        if not player.alive or game.pending_event or player.imprisonment or player.ghost_captor or game.active_trial or game.guixu_state.get("player_session"):
            raise ValueError("当前状态无法处理商盟事务")
        rng = decode_rng(game.seed, game.rng_state)
        member = state["membership"]
        alliance_id = str(payload.get("alliance_id") or (member or {}).get("alliance_id", ""))
        alliance = self._merchant_alliance(game, player.world, alliance_id)
        if action == "dismiss_notices":
            state["notices"] = []
        elif action == "leave":
            if state["active"]:
                raise ValueError("请先完成或放弃已接委托")
            state["membership"] = None
        else:
            if not alliance or not self._merchant_site(game, alliance):
                raise ValueError("请前往该商盟在本界的总部或分部地图")
            site = self._merchant_site(game, alliance)
            if action == "join":
                if member:
                    raise ValueError("已加入商盟，请先退出原商盟")
                state["membership"] = {"alliance_id": alliance_id, "world": player.world, "site": site, "rank": 0}
                self._merchant_notice(game, f"你已加入{alliance['name']}，成为{'总部' if site == 'hq' else self.maps.location(player.world, site)['name'] + '分部'}成员。宗门、家族和种族身份不受影响。")
            else:
                if not member or member["alliance_id"] != alliance_id or (member["world"] != player.world and not alliance["cross_world"]):
                    raise ValueError("你不是该商盟成员")
                influence_key = self._merchant_influence_key(member)
                influence = state["influence"].get(influence_key, 0)
                if action == "promote":
                    if member["world"] != player.world or (member["site"] == "hq" and member["rank"] == 0):
                        raise ValueError("总部直入成员须先调往本界分部，从分部成员开始历练")
                    threshold = [120, 360][min(member["rank"], 1)]
                    if member["rank"] >= 2 or influence < threshold:
                        raise ValueError(f"晋升所需本部影响力：{threshold}")
                    member["rank"] += 1
                    self._merchant_notice(game, f"盟内考绩通过，晋升为{RANKS[member['rank']]}。")
                elif action == "transfer_branch":
                    if state["active"] or member["world"] != player.world or site == "hq":
                        raise ValueError("请完成当前委托并前往入盟界面的分部申请历练")
                    if member["site"] == "hq":
                        member.update(site=site, rank=0)
                        state["influence"][f"{player.world}:{alliance_id}:offices"] = 0
                    else:
                        member["site"] = site
                    self._merchant_notice(game, "调任分部；同界分部之间共用影响力，总部调出从成员重新历练。")
                elif action == "hq_exam":
                    if state["active"] or member["world"] != player.world or site != "hq" or member["site"] == "hq" or member["rank"] != 2 or influence < 600:
                        raise ValueError("分部特使须累积600影响力、完成当前委托，前往本界总部参加调任考核")
                    required = max(1, self._merchant_realm_cap(player.world) - 3)
                    if player.realm_index < required or combat_power(player) < expected_combat_power(required, 1):
                        raise ValueError(f"考核需至少{REALMS[required].name}修为与相应基础实战能力")
                    state["influence"][influence_key] -= 600
                    member.update(site="hq", rank=1)
                    self._merchant_notice(game, "总部实战资历考核通过，调任总部使节；跨界商盟使节可启用逆灵通道。")
                elif action == "accept":
                    if state["active"]:
                        raise ValueError("一次只能接取一个商盟委托")
                    task = next((row for row in self._merchant_board(game, alliance) if row["id"] == payload.get("task_id")), None)
                    if not task:
                        raise ValueError("委托已刷新或已完成")
                    task.update(worked=0, influence_key=influence_key, existing_artifacts=[row["id"] for row in player.crafted_artifacts])
                    state["active"] = task
                elif action == "work":
                    self._merchant_work(game, rng)
                elif action == "abandon":
                    state["active"] = None
                elif action == "post":
                    self._merchant_post(game, alliance, payload)
                elif action == "passage":
                    if state["active"]:
                        raise ValueError("请先完成或放弃当前商盟任务")
                    self._merchant_passage(game, alliance, str(payload.get("destination", "")))
                else:
                    raise ValueError("未知商盟操作")
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _merchant_post(self, game, alliance, payload):
        state = game.merchant_state
        if sum(row["status"] in {"open", "working"} for row in state["posted"]) >= 12:
            raise ValueError("最多同时发布12个委托")
        kind = str(payload.get("kind", "supply"))
        stars = int(payload.get("stars", 1))
        quantity = int(payload.get("quantity", 1))
        if kind not in KINDS or not 1 <= stars <= 5 or not 1 <= quantity <= 99:
            raise ValueError("任务类型、星级或数量无效")
        world = str(payload.get("source_world") or game.player.world)
        if world not in alliance["linked_worlds"]:
            raise ValueError("普通商盟不承接异界委托，该商盟亦未打通目标商路")
        definitions = self._merchant_materials(world)
        definition = next((row for row in definitions if row["id"] == payload.get("definition_id")), None)
        if kind == "supply" and not definition:
            raise ValueError("请选择目标界面的具体材料")
        if kind == "formation" and not any(row.get("world") == world for row in self._formation_material_defs().values()):
            raise ValueError("目标界面没有可委托的阵材")
        cross = world != game.player.world
        minimum = self._merchant_post_minimum(kind, stars, quantity, definition, cross)
        target = None
        if kind == "bounty":
            target = self._find_npc(game, str(payload.get("target_id", "")))
            if not target or not target.alive or target.world != world:
                raise ValueError("请选择目标界面内仍存活的悬赏修士")
            minimum = max(minimum, math.ceil(self._npc_power(target) * 4) * (4 if cross else 1))
        principal = int(payload.get("principal", minimum))
        if principal < minimum or principal > 10 ** 15:
            raise ValueError(f"此委托悬赏本金至少 {minimum:,} 灵石")
        fee = max(1, math.ceil(principal * (.06 if alliance["policy"] == "economy" else .1)))
        if not has_item(game.player, "spirit_stone", principal + fee):
            raise ValueError(f"发布需悬赏本金 {principal:,} + 手续费 {fee:,} 灵石")
        remove_item(game.player, "spirit_stone", principal + fee)
        state["sequence"] += 1
        years = stars * 3 * (15 if cross else 1)
        name = f"收集{definition['name']} ×{quantity}" if kind == "supply" else KINDS[kind]
        if target:
            name += f" · {target.name}"
        state["posted"].append({"id": state["sequence"], "kind": kind, "name": name, "stars": stars,
                                "world": game.player.world, "alliance_id": alliance["id"], "source_world": world,
                                "definition_id": definition["id"] if definition else "", "quantity": quantity,
                                "target_id": target.id if target else None,
                                "principal": principal, "fee": fee, "years": years, "posted_age": game.player.age,
                                "check_age": game.player.age + max(1, years // 3), "deadline": game.player.age + years * 4,
                                "status": "open", "accept_chance": min(.85, .3 + .15 * principal / minimum), "cross_world": cross})
        terminal = [row for row in state["posted"] if row["status"] not in {"open", "working"}]
        for old in terminal[:-30]:
            state["posted"].remove(old)

    @staticmethod
    def _merchant_post_minimum(kind, stars, quantity, definition, cross):
        base = int(definition["base_material_value"]) * quantity * 3 if kind == "supply" and definition else 2000 * stars ** 3
        return max(100 * stars, base) * (4 if cross else 1)

    def _public_merchant(self, game):
        self._ensure_merchant(game)
        state = game.merchant_state
        member = state["membership"]
        membership = None
        if member:
            home = self._merchant_alliance(game, member["world"], member["alliance_id"])
            world_name = WORLD_SYSTEMS["world_names"][member["world"]]
            office_name = ("总部" if home["home_world"] == member["world"] else "分总部") if member["site"] == "hq" else self.maps.location(member["world"], member["site"])["name"] + "分部"
            membership = copy.deepcopy(member) | {"title": f"{home['name']} {world_name}{office_name} {RANKS[member['rank']]}",
                        "influence": state["influence"].get(self._merchant_influence_key(member), 0)}
        visible = []
        for alliance in state["worlds"][game.player.world]:
            owned = bool(member and member["alliance_id"] == alliance["id"] and (member["world"] == game.player.world or alliance["cross_world"]))
            site = self._merchant_site(game, alliance)
            row = {key: copy.deepcopy(alliance[key]) for key in ("id", "name", "world", "hq", "cross_world", "linked_worlds", "reserves", "relation", "policy", "next_policy_age")}
            row.update(policy_name=POLICIES[alliance["policy"]], power=self._merchant_power(alliance),
                       hq_name=self.maps.location(game.player.world, alliance["hq"])["name"],
                       leader_name=alliance["leader"]["name"], leader_realm=REALMS[alliance["leader"]["realm_index"]].name,
                       chief_name=alliance["chief_name"], chief_realm=REALMS[alliance["chief_realm"]].name,
                       chief_power=round(alliance["chief_power"]), local_site=site, member=owned,
                       offices=[{"location_id": office["location_id"], "name": self.maps.location(game.player.world, office["location_id"])["name"],
                                 "leader": office["leader"]["name"], "realm": REALMS[office["leader"]["realm_index"]].name} for office in alliance["offices"]],
                       tasks=self._merchant_board(game, alliance) if owned else [])
            row["destinations"] = [{"id": world, "name": WORLD_SYSTEMS["world_names"][world],
                                     "cost": self._merchant_passage_cost(game, world)} for world in alliance["linked_worlds"] if world != game.player.world] if owned else []
            row["catalog"] = [{"world": world, "world_name": WORLD_SYSTEMS["world_names"][world],
                               "targets": [{"id": npc.id, "name": npc.name, "realm": REALMS[npc.realm_index].name,
                                            "power": self._npc_power(npc)} for npc in self._all_world_npcs(game)
                                           if npc.alive and npc.world == world][:60],
                               "materials": [{"id": d["id"], "name": d["name"], "value": d["base_material_value"]} for d in self._merchant_materials(world)]}
                              for world in alliance["linked_worlds"]] if owned else []
            visible.append(row)
        orders = copy.deepcopy(state["posted"])
        for order in orders:
            order.pop("will_finish", None)
            order.pop("accept_chance", None)
            order["progress"] = min(.99, max(0, (game.player.age - order.get("started_age", game.player.age)) / order["years"])) if order["status"] == "working" else 1 if order["status"] == "completed" else 0
        return {"alliances": visible, "membership": membership, "active": copy.deepcopy(state["active"]),
                "posted": orders, "notices": copy.deepcopy(state["notices"]), "kinds": KINDS,
                "hired_hands": state.get("hired_hands", 0), "year": game.player.age}

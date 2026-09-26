from __future__ import annotations

import copy
import math
from typing import Any
from ...content_registry import (
    ITEM_CATALOG,
    REALMS,
    TECHNIQUE_CATALOG,
    TECHNIQUE_ELEMENT_NAMES,
    TRANSFORMATION_CATALOG,
)
from ...models import HistoryRecord
from ...rules import (
    add_item,
    assign_technique,
    has_item,
    acquire_technique,
    max_hp,
    max_mp,
    opportunity_required,
    realm,
    remove_item,
    merge_technique_copies,
    upgrade_known_technique,
)
from ...system.transformation_system import (
    absorption_gain,
    ensure_transformation_state,
    form_stat_progress,
    forms_are_incompatible,
    transformation_technique_limits,
)
from ...runtime import now_iso
from ...system.monster_bloodline_system import bloodline_content_available
from ...system.ghost_system import (
    ensure_ghost_cultivation_state,
    ghost_cultivation_active,
    grant_intrinsic_growth,
)


class EngineInventoryActionsMixin:
    def use_item(self, game_id: str, item_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        item = ITEM_CATALOG.get(item_id)
        if not item or not has_item(game.player, item_id):
            raise ValueError("物品不存在")
        if game.player.cultivation_suppression and item.breakthrough_bonus > 0:
            raise ValueError("压制修为期间不能服用突破丹药")
        if ghost_cultivation_active(game.player) and item.breakthrough_bonus > 0:
            scope_type = str(item.breakthrough_scope or "").split(":", 1)[0]
            if game.player.realm_index < 4:
                raise ValueError("凝婴入体前，阴魂无法承受突破丹药；达到元婴期后方可服用当前境界适用的小境界丹药。")
            if scope_type == "major" and game.player.realm_index < 6:
                raise ValueError("炼虚以前魂婴尚不能借丹药跨越大境界；达到炼虚期后方可服用当前境界适用的大境界丹药。")
        if game.pending_event:
            if not game.active_trial or (item.trial_restore_hp <= 0 and item.trial_restore_mp <= 0):
                raise ValueError("当前事件中只能使用渡劫恢复道具")
            remove_item(game.player, item_id)
            hp_gain = max_hp(game.player) * float(item.trial_restore_hp)
            mp_gain = max_mp(game.player) * float(item.trial_restore_mp)
            game.player.hp = min(max_hp(game.player), game.player.hp + hp_gain)
            game.player.mp = min(max_mp(game.player), game.player.mp + mp_gain)
            game.history.append(HistoryRecord(
                "SYS_TRIAL_RECOVERY", 1, game.player.age, "劫中服药", item_id, "recovered",
                f"你在劫隙中使用{item.name}，恢复 HP {hp_gain:.0f}、MP {mp_gain:.0f}。",
                {"hp_gain": hp_gain, "mp_gain": mp_gain}, ["system", "item", "tribulation"],
            ))
        elif item.conception_bonus > 0:
            companion = game.player.dao_companion
            if not companion or not companion.get("alive", True):
                raise ValueError("须先有一位仍在世的道侣，才能服用此类孕育丹药")
            if game.player.next_companion_conception_bonus > 0:
                raise ValueError("下一次缠绵的孕育药力尚未消散，不能重复服用")
            remove_item(game.player, item_id)
            bonus = min(0.95, float(item.conception_bonus))
            game.player.next_companion_conception_bonus = bonus
            game.history.append(HistoryRecord(
                "SYS_USE_CONCEPTION_PILL", 1, game.player.age, "服丹蕴嗣", item_id, "activated",
                f"你服下{item.name}，下一次与道侣缠绵时的孕育概率 +{bonus:.0%}。",
                {"bonus": bonus}, ["system", "item", "family", "offspring"],
            ))
        elif item.permanent_intrinsic_hp_bonus > 0 or item.permanent_intrinsic_mp_bonus > 0:
            player = game.player
            ensure_ghost_cultivation_state(player)
            hp_gain = max(0.0, float(item.permanent_intrinsic_hp_bonus))
            mp_gain = max(0.0, float(item.permanent_intrinsic_mp_bonus))
            remove_item(player, item_id)
            player.permanent_intrinsic_hp_bonus += hp_gain
            player.permanent_intrinsic_mp_bonus += mp_gain
            grant_intrinsic_growth(player, hp_gain, mp_gain)
            game.history.append(HistoryRecord(
                "SYS_USE_PERMANENT_INTRINSIC_PILL", 1, player.age, "本源新生", item_id, "strengthened",
                f"你服下{item.name}，永久获得本体 HP +{hp_gain:g}、MP +{mp_gain:g}；既有魂蚀损失没有恢复。",
                {"intrinsic_hp_gain": hp_gain, "intrinsic_mp_gain": mp_gain},
                ["system", "item", "pill", "intrinsic", "permanent"],
            ))
        elif "guixu_consumable" in item.tags:
            remove_item(game.player, item_id)
            potency = max(1, int(item_id.rsplit("_", 1)[-1]))
            hp_gain = max_hp(game.player) * min(.55, .18 + potency * .035)
            mp_gain = max_mp(game.player) * min(.55, .18 + potency * .035)
            opportunity_gain = REALMS[game.player.realm_index].opportunity_base * (.20 + potency * .04)
            game.player.hp = min(max_hp(game.player), game.player.hp + hp_gain)
            game.player.mp = min(max_mp(game.player), game.player.mp + mp_gain)
            self._add_opportunity(game.player, opportunity_gain)
            game.history.append(HistoryRecord(
                "SYS_USE_GUIXU_CONSUMABLE", 1, game.player.age, "服用归墟奇物", item_id, "consumed",
                f"你使用{item.name}，恢复 HP {hp_gain:.0f}、MP {mp_gain:.0f}，并获得机缘 {opportunity_gain:.1f}。",
                {"hp_gain": round(hp_gain, 1), "mp_gain": round(mp_gain, 1),
                 "opportunity_gain": round(opportunity_gain, 1)},
                ["system", "item", "guixu", "consumable"],
            ))
        elif "guixu_tide" in item.tags and "spirit_plant" in item.tags:
            remove_item(game.player, item_id)
            potency = max(1.0, math.log10(max(10.0, float(item.plant_value or 10))))
            hp_gain = max_hp(game.player) * min(.45, .08 + potency * .04)
            mp_gain = max_mp(game.player) * min(.45, .08 + potency * .04)
            opportunity_gain = REALMS[game.player.realm_index].opportunity_base * min(.90, .10 + potency * .06)
            game.player.hp = min(max_hp(game.player), game.player.hp + hp_gain)
            game.player.mp = min(max_mp(game.player), game.player.mp + mp_gain)
            self._add_opportunity(game.player, opportunity_gain)
            game.history.append(HistoryRecord(
                "SYS_REFINE_GUIXU_PLANT", 1, game.player.age, "炼化归墟灵植", item_id, "refined",
                f"你炼化{item.name}，恢复 HP {hp_gain:.0f}、MP {mp_gain:.0f}，并获得机缘 {opportunity_gain:.1f}。",
                {"hp_gain": round(hp_gain, 1), "mp_gain": round(mp_gain, 1),
                 "opportunity_gain": round(opportunity_gain, 1)},
                ["system", "item", "guixu", "spirit_plant"],
            ))
        elif item.breakthrough_bonus > 0 and item.breakthrough_scope:
            if game.player.path == "demonic":
                raise ValueError("魔修不能依靠突破丹药提高自身突破率；可将丹药用于培养傀儡或弟子")
            scope_type, source_text = item.breakthrough_scope.split(":", 1)
            if game.player.path == "monster" and scope_type == "major" and bloodline_content_available():
                raise ValueError("妖修大境界由血脉条件与生命经历决定，突破丹药不会开启进化路线")
            if int(source_text) != game.player.realm_index:
                raise ValueError("这枚丹药不适用于当前境界")
            if scope_type == "major" and game.player.layer < realm(game.player).layers:
                raise ValueError("尚未抵达大境界瓶颈，不能提前服用此丹")
            if scope_type == "minor" and not (
                game.player.awaiting_minor_breakthrough
                and game.player.layer in self._manual_minor_layers(game.player)
                and game.player.opportunity >= opportunity_required(game.player)
            ):
                raise ValueError("此丹须在初期或中期圆满、停留小境界瓶颈时服用")
            if item_id in game.player.active_breakthrough_aids:
                raise ValueError("本次冲关已经服用过同一种丹药")
            remove_item(game.player, item_id)
            game.player.active_breakthrough_aids.append(item_id)
            game.history.append(HistoryRecord(
                "SYS_USE_BREAKTHROUGH_PILL", 1, game.player.age, "服丹备关", item_id, "activated",
                f"你服下{item.name}，下次对应突破成功率 +{item.breakthrough_bonus:.0%}。",
                {"scope": item.breakthrough_scope, "bonus": item.breakthrough_bonus}, ["system", "item", "breakthrough"],
            ))
        elif item_id.startswith(("jinque_", "zique_", "moque_", "yaoque_", "mingque_")):
            is_zique = item_id.startswith("zique_")
            is_moque = item_id.startswith("moque_")
            is_yaoque = item_id.startswith("yaoque_")
            is_mingque = item_id.startswith("mingque_")
            if is_zique and (game.player.world != "spirit" or game.player.realm_index < 5):
                raise ValueError("紫阙玉书须在灵界达到化神期后方能参悟")
            if is_moque and (game.player.world != "true_demon" or game.player.realm_index < 5):
                raise ValueError("魔阙须在真魔界达到化魔期后方能参悟")
            if is_yaoque and (game.player.world not in {"monster_realm", "phantom_underworld"} or game.player.realm_index < 5):
                raise ValueError("妖阙骨书须在妖界或幻冥界达到化神期后方能参悟")
            if is_mingque and (game.player.world != "hell" or game.player.realm_index < 5):
                raise ValueError("冥阙魂书须在地狱界达到化神期后方能参悟")
            if not any((is_zique, is_moque, is_yaoque, is_mingque)) and game.player.realm_index < 4:
                raise ValueError("上面记载的法门或者材料不是你现阶段能集齐的")
            affinity = item.root_grant
            if affinity in game.player.additional_roots or affinity in self._base_affinities(game.player):
                raise ValueError("你已经拥有对应灵根")
            remove_item(game.player, item_id)
            game.player.additional_roots.append(str(affinity))
            summary = f"你依《{item.name}》补全了{TECHNIQUE_ELEMENT_NAMES[str(affinity)]}灵根；原有灵根效率保持不变。"
            game.history.append(HistoryRecord(
                (
                    "SYS_USE_MOQUE" if is_moque else "SYS_USE_ZIQUE" if is_zique
                    else "SYS_USE_YAOQUE" if is_yaoque else "SYS_USE_MINGQUE" if is_mingque
                    else "SYS_USE_JINQUE"
                ), 1, game.player.age,
                (
                    "魔阙补灵" if is_moque else "紫阙补灵" if is_zique
                    else "妖阙补灵" if is_yaoque else "冥阙补灵" if is_mingque
                    else "补全天缺"
                ), item_id, "root_added", summary,
                {"additional_root": affinity}, ["system", "item", "root"],
            ))
        elif item_id == "healing_pill" and remove_item(game.player, item_id):
            restored = max_hp(game.player) * 0.35
            game.player.hp = min(max_hp(game.player), game.player.hp + restored)
            game.history.append(HistoryRecord(
                "SYS_USE_ITEM", 1, game.player.age, "服用丹药", item_id, "healed",
                f"服下回春丹，恢复了 {restored:.0f} 点 HP。", {"hp": round(restored, 1)}, ["system", "item"],
            ))
        else:
            raise ValueError("该物品当前不能使用")
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def buy_market_offer(self, game_id: str, offer_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        if game.player.realm_index == 0:
            raise ValueError("凡人无法进入修仙坊市")
        offer = next((entry for entry in game.market_offers if entry["id"] == offer_id), None)
        if not offer or offer.get("sold"):
            raise ValueError("该货物已经售出或不在本期坊市")
        if offer.get("world", "human") != game.player.world:
            raise ValueError("此物不属于当前世界的坊市货池")
        price = int(offer["price"])
        if not remove_item(game.player, "spirit_stone", price):
            raise ValueError(f"需要 {price} 枚下品灵石")
        if offer["kind"] == "crafting_material":
            summary = self._buy_crafting_material_offer(game, offer, price)
        elif offer["kind"] == "formation_material":
            summary = self._buy_formation_material_offer(game, offer, price)
        elif offer["kind"] == "formation_supply":
            summary = self._buy_formation_supply_offer(game, offer, price)
        elif offer["kind"] == "item":
            add_item(game.player, offer["content_id"])
            summary = f"你在{offer['market_name']}支付 {price} 枚灵石，购得{offer['name']}。"
        else:
            learned = acquire_technique(game.player, TECHNIQUE_CATALOG[offer["content_id"]])
            destination = "已悟功法" if learned else "包裹，可用于升级"
            summary = f"你在{offer['market_name']}支付 {price} 枚灵石，购得《{offer['name']}》传承玉简，收入{destination}。"
        offer["sold"] = True
        offer["locked"] = False
        game.history.append(HistoryRecord(
            "SYS_MARKET_BUY", 1, game.player.age, "坊市交易", offer_id, "purchased", summary,
            {"spirit_stone": -price, "content_id": offer["content_id"]}, ["system", "market"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def equip_known_technique(self, game_id: str, technique_id: str, slot: str) -> dict[str, Any]:
        game = self._load(game_id)
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        known = next((technique for technique in game.player.known_techniques if technique.id == technique_id), None)
        if not known:
            raise ValueError("你尚未掌握这部功法")
        assign_technique(game.player, copy.deepcopy(known), slot)
        slot_name = {
            "main": "主修", "support": "辅修", "combat": "战斗", "body": "炼体",
            "divine_sense": "神识", "transformation": "变身",
        }.get(slot)
        if not slot_name:
            raise ValueError("未知功法槽位")
        game.history.append(HistoryRecord(
            "SYS_EQUIP_KNOWN_TECHNIQUE", 1, game.player.age, "重整功法", technique_id, "equipped",
            f"你将《{known.name}》配置为{slot_name}功法。", {"slot": slot, "technique_id": technique_id},
            ["system", "technique"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def upgrade_technique(self, game_id: str, technique_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        if game.pending_event or not game.player.alive or game.player.imprisonment:
            raise ValueError("当前状态无法升级功法")
        known = next(
            (entry for entry in game.player.known_techniques if entry.id == technique_id), None,
        )
        if known is None:
            raise ValueError("你尚未掌握这部功法")
        technique_name = known.name
        old_level = known.level
        new_level = upgrade_known_technique(game.player, technique_id)
        game.history.append(HistoryRecord(
            "SYS_TECHNIQUE_UPGRADE", 1, game.player.age, "合参功法", technique_id, "upgraded",
            f"你消耗一份《{technique_name}》Lv.{old_level} 传承玉简，将功法提升至 Lv.{new_level}。",
            {"technique_id":technique_id, "level":[old_level, new_level]},
            ["system", "technique", "upgrade"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def merge_technique_manuals(
        self, game_id: str, technique_id: str, level: int,
    ) -> dict[str, Any]:
        game = self._load(game_id)
        if game.pending_event or not game.player.alive or game.player.imprisonment:
            raise ValueError("当前状态无法合成传承玉简")
        known = next(
            (entry for entry in game.player.known_techniques if entry.id == technique_id), None,
        )
        template = TECHNIQUE_CATALOG.get(technique_id)
        technique_name = known.name if known else (template.name if template else "无名功法")
        new_level = merge_technique_copies(game.player, technique_id, int(level))
        game.history.append(HistoryRecord(
            "SYS_TECHNIQUE_MANUAL_MERGE", 1, game.player.age, "合炼玉简", technique_id, "merged",
            f"你将两份《{technique_name}》Lv.{level} 传承玉简合为一份 Lv.{new_level} 玉简。",
            {"technique_id":technique_id, "level":[int(level), new_level]},
            ["system", "technique", "manual", "merge"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def absorb_transformation_material(
        self, game_id: str, item_id: str, purify: bool = False, stat_id: str = "",
    ) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if player.path == "monster":
            raise ValueError("妖修不能炼化真灵素材进行变身；请通过血脉进化强化本体")
        if game.pending_event or not player.alive or player.imprisonment:
            raise ValueError("当前状态无法炼化真灵素材")
        item = next((entry for entry in player.inventory if entry.id == item_id and entry.quantity > 0), None)
        if not item or item.transformation_form_id not in TRANSFORMATION_CATALOG or item.transformation_purity <= 0:
            raise ValueError("行囊中没有可炼化的真灵素材")
        quantity = 2 if purify else 1
        if item.quantity < quantity:
            raise ValueError("提纯需要两份相同的真灵素材")
        form_id = str(item.transformation_form_id)
        ensure_transformation_state(player)
        progress = form_stat_progress(player, form_id)
        if stat_id not in progress:
            stat_id = min(progress, key=progress.get)
        current = progress[stat_id]
        if current >= 1 - 1e-9:
            raise ValueError("所选变身属性已经圆满，请改选其他属性")
        gain = absorption_gain(float(item.transformation_purity), purify)
        improved = min(1.0, current + gain)
        if not remove_item(player, item_id, quantity):
            raise ValueError("真灵素材数量不足")
        form = TRANSFORMATION_CATALOG[form_id]
        progress[stat_id] = improved
        mastery = player.transformation_mastery.setdefault(form_id, {})
        mastery.update({
            "stats": {key: round(value, 8) for key, value in progress.items()},
            "purity": round(sum(progress.values()) / len(progress), 8),
            "material_id": item_id,
            "source_type": f"提纯{item.transformation_source}" if purify else str(item.transformation_source),
        })
        if form_id not in player.known_transformations:
            player.known_transformations.append(form_id)
        ensure_transformation_state(player)
        action = "purified" if purify else "absorbed"
        verb = "合炼两份并提纯" if purify else "炼化"
        stat_name = {"might":"威能", "guard":"防护", "mobility":"身法", "sense":"神识", "sustain":"续航", "breach":"破法"}[stat_id]
        game.history.append(HistoryRecord(
            "SYS_TRANSFORMATION_MATERIAL", 1, player.age, "炼化真灵素材", item_id, action,
            f"你{verb}{item.name}，将{form.name}的{stat_name}圆满度由 {current:.2%} 提升至 {improved:.2%}。",
            {"form_id":form_id, "stat_id":stat_id, "old_progress":current, "new_progress":improved, "quantity":-quantity},
            ["system", "transformation", "true_spirit"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def batch_absorb_transformation_material(
        self, game_id: str, item_id: str, mode: str = "direct", stat_id: str = "",
    ) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if player.path == "monster":
            raise ValueError("妖修不能炼化真灵素材进行变身；请通过血脉进化强化本体")
        if game.pending_event or not player.alive or player.imprisonment:
            raise ValueError("当前状态无法炼化真灵素材")
        if mode not in {"direct", "purified"}:
            raise ValueError("未知的一键培养方式")
        item = next((entry for entry in player.inventory if entry.id == item_id and entry.quantity > 0), None)
        if not item or item.transformation_form_id not in TRANSFORMATION_CATALOG or item.transformation_purity <= 0:
            raise ValueError("行囊中没有可炼化的真灵素材")
        if mode == "purified" and item.quantity < 2:
            raise ValueError("一键合炼至少需要两份相同的真灵素材")
        form_id = str(item.transformation_form_id)
        ensure_transformation_state(player)
        progress = form_stat_progress(player, form_id)
        if stat_id not in progress:
            stat_id = min(progress, key=progress.get)
        current = progress[stat_id]
        if current >= 1 - 1e-9:
            raise ValueError("所选变身属性已经圆满，请改选其他属性")

        available = int(item.quantity)
        remaining = available
        consumed = 0
        pair_count = 0
        single_count = 0
        improved = current
        pair_bonus_active = mode == "purified" and available > 2
        direct_gain = absorption_gain(float(item.transformation_purity), False)
        pair_gain = absorption_gain(float(item.transformation_purity), True)
        if pair_bonus_active:
            pair_gain *= 1.30

        if mode == "purified":
            while remaining >= 2 and improved < 1 - 1e-9:
                improved = min(1.0, improved + pair_gain)
                remaining -= 2
                consumed += 2
                pair_count += 1
            if remaining and improved < 1 - 1e-9:
                improved = min(1.0, improved + direct_gain)
                remaining -= 1
                consumed += 1
                single_count += 1
        else:
            while remaining and improved < 1 - 1e-9:
                improved = min(1.0, improved + direct_gain)
                remaining -= 1
                consumed += 1
                single_count += 1

        if consumed <= 0 or not remove_item(player, item_id, consumed):
            raise ValueError("真灵素材数量不足")
        form = TRANSFORMATION_CATALOG[form_id]
        progress[stat_id] = improved
        mastery = player.transformation_mastery.setdefault(form_id, {})
        mastery.update({
            "stats": {key: round(value, 8) for key, value in progress.items()},
            "purity": round(sum(progress.values()) / len(progress), 8),
            "material_id": item_id,
            "source_type": f"批量合炼{item.transformation_source}" if mode == "purified" else f"批量炼化{item.transformation_source}",
        })
        if form_id not in player.known_transformations:
            player.known_transformations.append(form_id)
        ensure_transformation_state(player)
        stat_name = {"might":"威能", "guard":"防护", "mobility":"身法", "sense":"神识", "sustain":"续航", "breach":"破法"}[stat_id]
        process = (
            f"合炼 {pair_count} 组" + ("（每组额外提升 30%）" if pair_bonus_active else "")
            + (f"，并炼化余下 {single_count} 份" if single_count else "")
            if mode == "purified" else f"连续炼化 {single_count} 份"
        )
        game.history.append(HistoryRecord(
            "SYS_TRANSFORMATION_MATERIAL_BATCH", 1, player.age, "一键培养精魄", item_id,
            "batch_purified" if mode == "purified" else "batch_absorbed",
            f"你以{item.name}{process}，将{form.name}的{stat_name}圆满度由 {current:.2%} 提升至 {improved:.2%}。",
            {
                "form_id":form_id, "stat_id":stat_id, "old_progress":current,
                "new_progress":improved, "quantity":-consumed, "pairs":pair_count,
                "singles":single_count, "pair_bonus":0.30 if pair_bonus_active else 0.0,
            },
            ["system", "transformation", "true_spirit", "batch"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def manage_transformation(self, game_id: str, form_id: str, action: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if player.path == "monster":
            raise ValueError("妖修不能使用变身系统")
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        if not player.transformation_technique:
            raise ValueError("请先配置一部变身功法")
        ensure_transformation_state(player)
        if form_id not in player.known_transformations or form_id not in TRANSFORMATION_CATALOG:
            raise ValueError("你尚未掌握这种变身")
        technique = player.transformation_technique
        loadout = player.transformation_loadouts[technique.id]
        stored, active = loadout["stored"], loadout["active"]
        capacity, space = transformation_technique_limits(technique)
        form = TRANSFORMATION_CATALOG[form_id]
        if action == "store":
            if form_id in stored:
                raise ValueError("该变身已经存入本功法")
            if len(stored) >= capacity:
                raise ValueError("该功法的变身容量已满")
            stored.append(form_id)
            summary = f"你将{form.name}存入《{technique.name}》。"
        elif action == "remove":
            if form_id not in stored:
                raise ValueError("该变身不在本功法中")
            if form_id in active:
                active.remove(form_id)
            stored.remove(form_id)
            summary = f"你从《{technique.name}》中移除{form.name}，所悟变身本身仍然保留。"
        elif action == "activate":
            if form_id not in stored:
                raise ValueError("需要先将该变身存入功法")
            if form_id in active:
                raise ValueError("该变身已经列入战斗预案")
            if len(active) >= space:
                raise ValueError("该功法的变身空间已满")
            conflict = next((other for other in active if forms_are_incompatible(form_id, other)), None)
            if conflict:
                raise ValueError(f"{form.name}与{TRANSFORMATION_CATALOG[conflict].name}互斥")
            active.append(form_id)
            summary = f"你将{form.name}列入自动战斗预案。"
        elif action == "deactivate":
            if form_id not in active:
                raise ValueError("该变身当前没有启用")
            active.remove(form_id)
            summary = f"你将{form.name}移出自动战斗预案。"
        elif action in {"promote", "demote"}:
            if form_id not in active:
                raise ValueError("只有已启用的变身可以调整权重顺序")
            index = active.index(form_id)
            target = index - 1 if action == "promote" else index + 1
            if not 0 <= target < len(active):
                raise ValueError("该变身已经位于权重顺序边界")
            active[index], active[target] = active[target], active[index]
            summary = f"你调整了{form.name}在融合预案中的权重顺序。"
        else:
            raise ValueError("未知变身管理操作")
        game.history.append(HistoryRecord(
            "SYS_TRANSFORMATION_MANAGE", 1, player.age, "调配变身", form_id, action,
            summary, {"technique_id": technique.id, "form_id": form_id, "action": action},
            ["system", "technique", "transformation"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

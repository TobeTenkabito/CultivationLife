from __future__ import annotations

from typing import Any

from .content_registry import REALMS, WORLD_SYSTEMS
from .models import GameState, HistoryRecord, Player
from .runtime import now_iso


GHOST_DLC_NAME = "百鬼夜行:轮回往生"


def ghost_cultivation_config() -> dict[str, Any]:
    return WORLD_SYSTEMS.get("ghost_cultivation", {})


def ghost_cultivation_active(player: Player) -> bool:
    config = ghost_cultivation_config()
    return bool(config.get("enabled", False) and player.path == "ghost")


def canonical_intrinsic_hp(
    player: Player, *, realm_index: int | None = None, layer: int | None = None,
) -> float:
    definition = REALMS[player.realm_index if realm_index is None else realm_index]
    actual_layer = player.layer if layer is None else layer
    return float(
        100
        + int(definition.base_power ** 0.5 * 16)
        + actual_layer * 8
        + player.body_training * 12
        + player.permanent_intrinsic_hp_bonus
    )


def canonical_intrinsic_mp(
    player: Player, *, realm_index: int | None = None, layer: int | None = None,
) -> float:
    definition = REALMS[player.realm_index if realm_index is None else realm_index]
    actual_layer = player.layer if layer is None else layer
    return float(
        40
        + int(definition.base_power ** 0.5 * 20)
        + actual_layer * 11
        + player.permanent_intrinsic_mp_bonus
    )


def ensure_ghost_cultivation_state(player: Player) -> bool:
    """Initialize new/legacy ghost saves without retroactive erosion."""
    if not ghost_cultivation_active(player):
        return False
    changed = False
    if player.ghost_intrinsic_hp_reference is None:
        player.ghost_intrinsic_hp_reference = canonical_intrinsic_hp(player)
        changed = True
    if player.ghost_intrinsic_mp_reference is None:
        player.ghost_intrinsic_mp_reference = canonical_intrinsic_mp(player)
        changed = True
    if player.ghost_intrinsic_hp_current is None:
        player.ghost_intrinsic_hp_current = player.ghost_intrinsic_hp_reference
        changed = True
    if player.ghost_intrinsic_mp_current is None:
        player.ghost_intrinsic_mp_current = player.ghost_intrinsic_mp_reference
        changed = True
    if player.ghost_intrinsic_highwater_realm is None:
        player.ghost_intrinsic_highwater_realm = player.realm_index
        player.ghost_intrinsic_highwater_layer = player.layer
        changed = True
    # V2 reuses the base milestone map for achievements.  Derive the count from
    # permanent V1 imprints so existing saves receive full credit on first load.
    imprint_total = sum(max(0, int(count)) for count in player.ghost_reincarnation_imprints.values())
    if int(player.milestones.get("ghost_reincarnations", 0)) < imprint_total:
        player.milestones["ghost_reincarnations"] = imprint_total
        changed = True
    if player.lifespan is not None:
        player.lifespan = None
        changed = True
    return changed


def intrinsic_hp_reference(player: Player) -> float:
    if ghost_cultivation_active(player):
        ensure_ghost_cultivation_state(player)
        return max(0.0, float(player.ghost_intrinsic_hp_reference or 0.0))
    return canonical_intrinsic_hp(player)


def intrinsic_mp_reference(player: Player) -> float:
    if ghost_cultivation_active(player):
        ensure_ghost_cultivation_state(player)
        return max(0.0, float(player.ghost_intrinsic_mp_reference or 0.0))
    return canonical_intrinsic_mp(player)


def effective_intrinsic_hp(player: Player) -> float:
    if ghost_cultivation_active(player):
        ensure_ghost_cultivation_state(player)
        return max(0.0, float(player.ghost_intrinsic_hp_current or 0.0))
    return intrinsic_hp_reference(player)


def effective_intrinsic_mp(player: Player) -> float:
    if ghost_cultivation_active(player):
        ensure_ghost_cultivation_state(player)
        return max(0.0, float(player.ghost_intrinsic_mp_current or 0.0))
    return intrinsic_mp_reference(player)


def hp_carry_ratio(player: Player) -> float:
    reference = intrinsic_hp_reference(player)
    return 1.0 if not ghost_cultivation_active(player) else max(
        0.0, min(1.0, effective_intrinsic_hp(player) / max(reference, 1e-12)),
    )


def mp_carry_ratio(player: Player) -> float:
    reference = intrinsic_mp_reference(player)
    return 1.0 if not ghost_cultivation_active(player) else max(
        0.0, min(1.0, effective_intrinsic_mp(player) / max(reference, 1e-12)),
    )


def grant_intrinsic_growth(player: Player, hp: float = 0.0, mp: float = 0.0) -> bool:
    if not ghost_cultivation_active(player):
        return False
    ensure_ghost_cultivation_state(player)
    player.ghost_intrinsic_hp_reference = float(player.ghost_intrinsic_hp_reference or 0.0) + max(0.0, hp)
    player.ghost_intrinsic_mp_reference = float(player.ghost_intrinsic_mp_reference or 0.0) + max(0.0, mp)
    player.ghost_intrinsic_hp_current = float(player.ghost_intrinsic_hp_current or 0.0) + max(0.0, hp)
    player.ghost_intrinsic_mp_current = float(player.ghost_intrinsic_mp_current or 0.0) + max(0.0, mp)
    return bool(hp or mp)


def grant_intrinsic_progression_if_new_highwater(player: Player) -> tuple[float, float]:
    if not ghost_cultivation_active(player):
        return (0.0, 0.0)
    ensure_ghost_cultivation_state(player)
    highwater = (
        int(player.ghost_intrinsic_highwater_realm or 0),
        int(player.ghost_intrinsic_highwater_layer or 1),
    )
    current = (player.realm_index, player.layer)
    if current <= highwater:
        return (0.0, 0.0)
    old_hp = canonical_intrinsic_hp(player, realm_index=highwater[0], layer=highwater[1])
    old_mp = canonical_intrinsic_mp(player, realm_index=highwater[0], layer=highwater[1])
    new_hp = canonical_intrinsic_hp(player)
    new_mp = canonical_intrinsic_mp(player)
    hp_gain, mp_gain = max(0.0, new_hp - old_hp), max(0.0, new_mp - old_mp)
    grant_intrinsic_growth(player, hp_gain, mp_gain)
    player.ghost_intrinsic_highwater_realm = current[0]
    player.ghost_intrinsic_highwater_layer = current[1]
    return (hp_gain, mp_gain)


def grant_wangsheng(player: Player, amount: int | None = None) -> int:
    if not ghost_cultivation_active(player):
        return 0
    actual = max(0, int(
        ghost_cultivation_config().get("wangsheng_per_layer", 1)
        if amount is None else amount
    ))
    player.ghost_wangsheng_energy += actual
    return actual


def reincarnation_effective_marks(player: Player, realm_index: int) -> int:
    if not ghost_cultivation_active(player):
        return 0
    total = 0
    for key, count in player.ghost_reincarnation_imprints.items():
        try:
            source = int(key)
        except (TypeError, ValueError):
            continue
        if source >= int(realm_index):
            total += max(0, int(count))
    return total


def reincarnation_breakthrough_bonus(player: Player, realm_index: int) -> float:
    return (
        reincarnation_effective_marks(player, realm_index)
        * float(ghost_cultivation_config().get("reincarnation_bonus_per_mark", 0.05))
    )


def apply_soul_erosion(player: Player, units: int = 1) -> dict[str, Any]:
    if not ghost_cultivation_active(player):
        return {"active": False, "units": 0, "dead": False, "thresholds": []}
    ensure_ghost_cultivation_state(player)
    config = ghost_cultivation_config()
    growth = max(0.0, float(config.get("erosion_growth_per_time_unit_pp", 0.0002)))
    floor = max(0.0, float(config.get("soul_death_intrinsic_floor", 1.0)))
    thresholds = [int(value) for value in config.get("carry_warning_thresholds", [90, 75, 50, 25, 10])]
    newly_crossed: list[int] = []
    completed = 0
    dead = False
    for _ in range(max(0, int(units))):
        rate = max(0.0, float(player.ghost_soul_erosion_rate_pp))
        factor = max(0.0, 1.0 - rate / 100.0)
        player.ghost_intrinsic_hp_current = float(player.ghost_intrinsic_hp_current or 0.0) * factor
        player.ghost_intrinsic_mp_current = float(player.ghost_intrinsic_mp_current or 0.0) * factor
        completed += 1
        hp_ratio = hp_carry_ratio(player) * 100
        mp_ratio = mp_carry_ratio(player) * 100
        lowest = min(hp_ratio, mp_ratio)
        for threshold in thresholds:
            if threshold not in player.ghost_erosion_thresholds_seen and lowest < threshold:
                player.ghost_erosion_thresholds_seen.append(threshold)
                newly_crossed.append(threshold)
        if (
            float(player.ghost_intrinsic_hp_current or 0.0) < floor
            or float(player.ghost_intrinsic_mp_current or 0.0) < floor
        ):
            dead = True
            break
        player.ghost_soul_erosion_rate_pp = rate + growth
    return {
        "active": True,
        "units": completed,
        "dead": dead,
        "thresholds": newly_crossed,
        "rate_pp": player.ghost_soul_erosion_rate_pp,
    }


def spend_wangsheng_energy(player: Player, uses: int = 1) -> tuple[int, float]:
    if not ghost_cultivation_active(player):
        raise ValueError(f"未启用【{GHOST_DLC_NAME}】或当前并非鬼修")
    config = ghost_cultivation_config()
    unit_cost = max(1, int(config.get("wangsheng_cost", 2)))
    actual_uses = max(1, int(uses))
    cost = unit_cost * actual_uses
    if player.ghost_wangsheng_energy < cost:
        raise ValueError(f"往生不足：需要 {cost} 点")
    before = max(0.0, float(player.ghost_soul_erosion_rate_pp))
    reduction = max(0.0, float(config.get("wangsheng_erosion_reduction_pp", 0.02))) * actual_uses
    player.ghost_wangsheng_energy -= cost
    player.ghost_soul_erosion_rate_pp = max(0.0, before - reduction)
    return cost, before - player.ghost_soul_erosion_rate_pp


def soul_integrity_label(ratio: float) -> str:
    percent = max(0.0, min(1.0, float(ratio))) * 100
    if percent >= 90:
        return "魂火鼎盛"
    if percent >= 75:
        return "魂灯微晦"
    if percent >= 50:
        return "魂基受损"
    if percent >= 25:
        return "魂魄残缺"
    if percent >= 10:
        return "魂灯将熄"
    return "魂飞魄散之兆"


class GhostSystemMixin:
    def _apply_soul_erosion_units(self, game: GameState, units: int = 1) -> bool:
        from .rules import max_hp, max_mp

        result = apply_soul_erosion(game.player, units)
        if not result["active"]:
            return True
        game.player.hp = min(game.player.hp, max_hp(game.player))
        game.player.mp = min(game.player.mp, max_mp(game.player))
        for threshold in result["thresholds"]:
            game.history.append(HistoryRecord(
                f"SYS_GHOST_EROSION_{threshold}", 1, game.player.age, "魂灯渐暗", None, "eroded",
                f"漫长岁月已经永久磨损魂魄本源，本体承载率首次跌破 {threshold}%。",
                {"carry_threshold": threshold, "erosion_rate_pp": game.player.ghost_soul_erosion_rate_pp},
                ["system", "ghost", "soul_erosion", "negative", "milestone"],
            ))
        if result["dead"]:
            self._die(game, "魂蚀已将本体魂基磨灭，纵有外物亦无法阻止魂飞魄散", "SYS_GHOST_SOUL_DISPERSAL")
            return False
        return True

    def spend_wangsheng(self, game_id: str, spend_all: bool = False) -> dict[str, Any]:
        game = self._load(game_id)
        if not game.player.alive or game.pending_event or game.player.imprisonment:
            raise ValueError("当前状态无法行往生法")
        unit_cost = max(1, int(ghost_cultivation_config().get("wangsheng_cost", 2)))
        uses = max(1, game.player.ghost_wangsheng_energy // unit_cost) if spend_all else 1
        cost, reduction = spend_wangsheng_energy(game.player, uses)
        game.player.milestones["ghost_wangsheng_spent"] = (
            int(game.player.milestones.get("ghost_wangsheng_spent", 0)) + cost
        )
        game.history.append(HistoryRecord(
            "SYS_GHOST_WANGSHENG", 1, game.player.age, "往生息蚀", None, "spent",
            f"你施行 {uses} 次往生，消耗 {cost} 点往生，将魂蚀率降低 {reduction:.4f} 个百分点；既有魂伤并未复原。",
            {"cost": cost, "uses": uses, "erosion_reduction_pp": reduction},
            ["system", "ghost", "wangsheng"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def reincarnate_ghost(self, game_id: str) -> dict[str, Any]:
        from .rules import max_hp, max_mp, opportunity_required

        game = self._load(game_id)
        player = game.player
        if not ghost_cultivation_active(player):
            raise ValueError(f"未启用【{GHOST_DLC_NAME}】或当前并非鬼修")
        if not player.alive or game.pending_event or game.active_trial or player.imprisonment or player.sealed_cultivation:
            raise ValueError("当前状态无法进入轮回")
        current_realm = REALMS[player.realm_index]
        if player.realm_index < 1 or player.layer < current_realm.layers or player.opportunity < opportunity_required(player):
            raise ValueError("只有抵达大境界最终瓶颈并将机缘修至圆满，方可入轮回")
        ensure_ghost_cultivation_state(player)
        source_realm, source_layer = player.realm_index, player.layer
        source_label = f"{current_realm.name}{source_layer}层"
        key = str(source_realm)
        player.ghost_reincarnation_imprints[key] = int(player.ghost_reincarnation_imprints.get(key, 0)) + 1
        player.milestones["ghost_reincarnations"] = (
            int(player.milestones.get("ghost_reincarnations", 0)) + 1
        )
        lost_wangsheng = player.ghost_wangsheng_energy
        player.ghost_last_reincarnation_realm = source_realm
        player.ghost_last_reincarnation_layer = source_layer
        player.realm_index = 1
        player.layer = 1
        player.opportunity = 0.0
        player.awaiting_major_breakthrough = False
        player.awaiting_minor_breakthrough = False
        player.awaiting_ascension = False
        player.awaiting_spirit_realm_crossing = False
        player.active_breakthrough_aids = []
        player.breakthrough_pity = {}
        player.joint_companion_breakthrough = None
        player.ghost_wangsheng_energy = 0
        player.lifespan = None
        player.hp = min(player.hp, max_hp(player))
        player.mp = min(player.mp, max_mp(player))
        game.history.append(HistoryRecord(
            "SYS_GHOST_REINCARNATION", 1, player.age, "舍世入轮回", key, "reincarnated",
            f"你舍去{source_label}修为，重归练气一层；留下第 {player.ghost_reincarnation_imprints[key]} 道本境轮回印记，未用往生 {lost_wangsheng} 点尽数散失。魂蚀与既有魂伤均未复原。",
            {
                "source_realm": source_realm, "source_layer": source_layer,
                "imprints": dict(player.ghost_reincarnation_imprints), "wangsheng_lost": lost_wangsheng,
            },
            ["system", "ghost", "reincarnation", "milestone"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _public_ghost_system(self, game: GameState) -> dict[str, Any]:
        from .rules import opportunity_required, raw_external_hp_bonus, raw_external_mp_bonus

        player = game.player
        if not ghost_cultivation_active(player):
            return {"available": False, "name": GHOST_DLC_NAME}
        ensure_ghost_cultivation_state(player)
        config = ghost_cultivation_config()
        hp_ratio, mp_ratio = hp_carry_ratio(player), mp_carry_ratio(player)
        imprints = [
            {
                "realm_index": index,
                "realm_name": REALMS[index].name,
                "layer": REALMS[index].layers,
                "count": int(player.ghost_reincarnation_imprints.get(str(index), 0)),
            }
            for index in range(1, min(9, len(REALMS)))
        ]
        at_bottleneck = bool(
            player.realm_index >= 1
            and player.layer >= REALMS[player.realm_index].layers
            and player.opportunity >= opportunity_required(player)
        )
        effective_marks = reincarnation_effective_marks(player, player.realm_index)
        total_imprints = sum(max(0, int(row["count"])) for row in imprints)
        integrity_ratio = min(hp_ratio, mp_ratio)
        probability_cap = min(
            0.98, max(0.005, float(config.get("reincarnation_final_probability_cap", 0.98))),
        )
        reincarnation_preview = None
        if at_bottleneck:
            source_count = int(player.ghost_reincarnation_imprints.get(str(player.realm_index), 0))
            reincarnation_preview = {
                "source": f"{REALMS[player.realm_index].name}{player.layer}层",
                "destination": f"{REALMS[1].name}1层",
                "next_imprint_count": source_count + 1,
                "added_bonus": float(config.get("reincarnation_bonus_per_mark", 0.05)),
                "affected_road": f"{REALMS[player.realm_index].name}及以下道路",
                "wangsheng_before": player.ghost_wangsheng_energy,
                "erosion_rate_pp": round(player.ghost_soul_erosion_rate_pp, 6),
                "intrinsic_hp_current": round(effective_intrinsic_hp(player), 4),
                "intrinsic_mp_current": round(effective_intrinsic_mp(player), 4),
            }
        return {
            "available": True,
            "name": GHOST_DLC_NAME,
            "erosion_rate_pp": round(player.ghost_soul_erosion_rate_pp, 6),
            "wangsheng": player.ghost_wangsheng_energy,
            "wangsheng_cost": int(config.get("wangsheng_cost", 2)),
            "wangsheng_reduction_pp": float(config.get("wangsheng_erosion_reduction_pp", 0.02)),
            "wangsheng_available_uses": player.ghost_wangsheng_energy // max(
                1, int(config.get("wangsheng_cost", 2)),
            ),
            "can_spend_wangsheng": bool(
                player.alive and not game.pending_event and not player.imprisonment
                and player.ghost_wangsheng_energy >= int(config.get("wangsheng_cost", 2))
            ),
            "can_reincarnate": bool(
                player.alive and at_bottleneck and not game.pending_event and not game.active_trial
                and not player.imprisonment and not player.sealed_cultivation
            ),
            "intrinsic_hp": {
                "current": round(effective_intrinsic_hp(player), 4),
                "reference": round(intrinsic_hp_reference(player), 4),
                "carry_ratio": round(hp_ratio, 6),
                "external_raw": round(raw_external_hp_bonus(player), 4),
                "external_effective": round(raw_external_hp_bonus(player) * hp_ratio, 4),
            },
            "intrinsic_mp": {
                "current": round(effective_intrinsic_mp(player), 4),
                "reference": round(intrinsic_mp_reference(player), 4),
                "carry_ratio": round(mp_ratio, 6),
                "external_raw": round(raw_external_mp_bonus(player), 4),
                "external_effective": round(raw_external_mp_bonus(player) * mp_ratio, 4),
            },
            "imprints": imprints,
            "total_imprints": total_imprints,
            "effective_marks": effective_marks,
            "breakthrough_bonus": reincarnation_breakthrough_bonus(player, player.realm_index),
            "breakthrough_probability_cap": probability_cap,
            "soul_integrity": {
                "ratio": round(integrity_ratio, 6),
                "label": soul_integrity_label(integrity_ratio),
            },
            "reincarnation_preview": reincarnation_preview,
            "highwater": {
                "realm_index": player.ghost_intrinsic_highwater_realm,
                "layer": player.ghost_intrinsic_highwater_layer,
                "name": (
                    f"{REALMS[int(player.ghost_intrinsic_highwater_realm)].name}"
                    f"{int(player.ghost_intrinsic_highwater_layer or 1)}层"
                ),
            },
            "last_anchor": (
                {
                    "realm_index": player.ghost_last_reincarnation_realm,
                    "layer": player.ghost_last_reincarnation_layer,
                    "name": (
                        f"{REALMS[int(player.ghost_last_reincarnation_realm)].name}"
                        f"{int(player.ghost_last_reincarnation_layer or 1)}层"
                    ),
                }
                if player.ghost_last_reincarnation_realm is not None else None
            ),
        }

"""Shared state rules without action or engine dependencies."""
from __future__ import annotations

from typing import Any

from ...content_registry import REALMS, WORLD_SYSTEMS
from ...models import Player
from ..ghost_resources import GHOST_DLC_NAME as GHOST_DLC_NAME
from ..ghost_resources import canonical_intrinsic_hp as canonical_intrinsic_hp
from ..ghost_resources import canonical_intrinsic_mp as canonical_intrinsic_mp
from ..ghost_resources import (
    ensure_ghost_cultivation_state as ensure_ghost_cultivation_state,
)
from ..ghost_resources import ghost_cultivation_active as ghost_cultivation_active
from ..ghost_resources import ghost_cultivation_config as ghost_cultivation_config
from ..ghost_resources import ghost_soul_pressure as ghost_soul_pressure
from ..ghost_resources import hp_carry_ratio as hp_carry_ratio
from ..ghost_resources import mp_carry_ratio as mp_carry_ratio


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
    # Body cultivation and permanent intrinsic consumables are independent new
    # growth.  If they changed while the DLC was disabled, reconcile them on
    # re-enable without touching the historical realm high-water mark.
    highwater_hp = canonical_intrinsic_hp(player, realm_index=highwater[0], layer=highwater[1])
    highwater_mp = canonical_intrinsic_mp(player, realm_index=highwater[0], layer=highwater[1])
    independent_hp = max(0.0, highwater_hp - float(player.ghost_intrinsic_hp_reference or 0.0))
    independent_mp = max(0.0, highwater_mp - float(player.ghost_intrinsic_mp_reference or 0.0))
    grant_intrinsic_growth(player, independent_hp, independent_mp)
    current = (player.realm_index, player.layer)
    if current <= highwater:
        return (independent_hp, independent_mp)
    old_hp = highwater_hp
    old_mp = highwater_mp
    new_hp = canonical_intrinsic_hp(player)
    new_mp = canonical_intrinsic_mp(player)
    realm_hp, realm_mp = max(0.0, new_hp - old_hp), max(0.0, new_mp - old_mp)
    grant_intrinsic_growth(player, realm_hp, realm_mp)
    player.ghost_intrinsic_highwater_realm = current[0]
    player.ghost_intrinsic_highwater_layer = current[1]
    return (independent_hp + realm_hp, independent_mp + realm_mp)


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


def can_reincarnate(player: Player) -> bool:
    if not ghost_cultivation_active(player) or not player.alive or player.realm_index < 1:
        return False
    current_realm = REALMS[player.realm_index]
    from ...rules import opportunity_required

    return bool(
        player.layer >= current_realm.layers
        and player.opportunity >= opportunity_required(player)
    )


def perform_reincarnation(player: Player) -> dict[str, Any]:
    """Apply the player-only, persistent part of reincarnation.

    Game-level blockers and history remain the command flow's responsibility, keeping
    this state transition directly testable and reusable without duplicating
    the three distinct reincarnation records.
    """
    if not can_reincarnate(player):
        raise ValueError("只有抵达大境界最终瓶颈并将机缘修至圆满，方可入轮回")
    ensure_ghost_cultivation_state(player)
    current_realm = REALMS[player.realm_index]
    source_realm, source_layer = player.realm_index, player.layer
    key = str(source_realm)
    player.ghost_reincarnation_imprints[key] = int(player.ghost_reincarnation_imprints.get(key, 0)) + 1
    player.milestones["ghost_reincarnations"] = (
        int(player.milestones.get("ghost_reincarnations", 0)) + 1
    )
    lost_wangsheng = player.ghost_wangsheng_energy
    previous_divine_sense_rank = player.divine_sense_rank
    previous_divine_sense_experience = player.divine_sense_experience
    player.ghost_last_reincarnation_realm = source_realm
    player.ghost_last_reincarnation_layer = source_layer
    player.realm_index = 1
    player.layer = 1
    player.opportunity = 0.0
    # Divine-sense rank participates in cultivation and breakthrough systems;
    # carrying it through repeated reincarnations would turn the reset into an
    # unbounded permanent accelerator.  A ghost starts at rank 1, so return to
    # that baseline and discard partial progress while retaining the manual.
    player.divine_sense_rank = 1
    player.divine_sense_experience = 0.0
    player.awaiting_major_breakthrough = False
    player.awaiting_minor_breakthrough = False
    player.awaiting_ascension = False
    player.awaiting_spirit_realm_crossing = False
    player.active_breakthrough_aids = []
    player.breakthrough_pity = {}
    player.joint_companion_breakthrough = None
    if ghost_cultivation_config().get("clear_wangsheng_on_reincarnation", True):
        player.ghost_wangsheng_energy = 0
    player.lifespan = None
    return {
        "source_realm": source_realm,
        "source_layer": source_layer,
        "source_label": f"{current_realm.name}{source_layer}层",
        "imprint_count": player.ghost_reincarnation_imprints[key],
        "wangsheng_lost": lost_wangsheng - player.ghost_wangsheng_energy,
        "divine_sense_rank_before": previous_divine_sense_rank,
        "divine_sense_experience_lost": previous_divine_sense_experience,
    }


def apply_soul_erosion(player: Player, units: int = 1) -> dict[str, Any]:
    if not ghost_cultivation_active(player):
        return {"active": False, "units": 0, "dead": False, "thresholds": []}
    ensure_ghost_cultivation_state(player)
    config = ghost_cultivation_config()
    growth = max(0.0, float(config.get("erosion_growth_per_time_unit_pp", 0.0002)))
    # The existing intrinsic high-water mark survives reincarnation and suppression.
    if max(player.realm_index, int(player.ghost_intrinsic_highwater_realm or 0)) >= 9:
        growth = 0.0
    _, pressure_modifier = ghost_soul_pressure(player)
    growth *= 1.0 + pressure_modifier
    if player.ghost_attachment:
        growth *= max(0.0, float(player.ghost_attachment.get("erosion_growth_multiplier", 1.0)))
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


def accumulate_soul_erosion_time(player: Player, elapsed_years: int = 1) -> int:
    """Accumulate actual years and return newly completed erosion units.

    The normalized fraction is shared by ordinary actions, travel, prison and
    other time sources. Realm changes preserve the fraction instead of turning
    partial high-realm time into a burst of low-realm erosion.
    """
    if not ghost_cultivation_active(player):
        return 0
    ensure_ghost_cultivation_state(player)
    years = max(0, int(elapsed_years))
    if not years:
        return 0
    time_unit = max(1, int(WORLD_SYSTEMS["time_units"][str(player.realm_index)]))
    total = max(0.0, float(player.ghost_soul_erosion_time_progress)) + years / time_unit
    completed_units = max(0, int(total + 1e-12))
    remainder = total - completed_units
    player.ghost_soul_erosion_time_progress = 0.0 if abs(remainder) < 1e-12 else remainder
    return completed_units


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

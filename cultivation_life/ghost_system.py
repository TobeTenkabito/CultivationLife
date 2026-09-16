from __future__ import annotations

import copy
import math
import random
from typing import Any

from .content_registry import REALMS, WORLD_SYSTEMS
from .ghost_soul_traits import generate_soul_trait, validate_generated_soul_trait
from .models import GameState, HistoryRecord, Player, SectNpc
from .runtime import now_iso
from .possession_system import (
    advance_player_age, can_possess, current_body_age, enter_host_body, has_ghost_core,
    is_possessed, leave_host_body, possession_limit,
)


GHOST_DLC_NAME = "百鬼夜行:轮回往生"

SOUL_SLOTS = {
    "胎光": ("opportunity", "机缘效率"), "爽灵": ("external_mp", "外源 MP"),
    "幽精": ("external_hp", "外源 HP"), "尸狗": ("mobility", "身法"),
    "伏矢": ("might", "威能"), "雀阴": ("resolve", "定力"),
    "吞贼": ("guard", "护御"), "非毒": ("sense", "神识"),
    "除秽": ("breach", "破防"), "臭肺": ("sustain", "续战"),
}
THREE_SOUL_STATS = frozenset({"opportunity", "external_mp", "external_hp"})
# Legacy fixed soul traits remain executable so existing saves keep their exact
# behavior.  Newly spawned night-parade souls use the generated rule grammar in
# ghost_soul_traits.py instead.
SOUL_TRAIT_RULES = {
    "寒魄": "失去先手时，本轮防护提高 12%",
    "执念": "受到的战意损失降低 25%，战意最低保留 8 点",
    "迅影": "前两轮争夺先手时，身法判定提高 12%",
    "噬灵": "每次有效攻势侵蚀敌方 4% 防护，最多叠加三层",
    "宿慧": "所有机缘获取额外提高 8%",
    "不灭": "每场战斗首次陷入危局时，恢复 8% 战斗态势与 5% 法力",
    "凶魂": "敌方战斗态势不高于 35% 时，造成的损耗提高 15%",
    "明识": "禁神识环境的惩罚由 14% 降至 6%",
}
def ghost_cultivation_config() -> dict[str, Any]:
    return WORLD_SYSTEMS.get("ghost_cultivation", {})


def ghost_cultivation_active(player: Player) -> bool:
    config = ghost_cultivation_config()
    return bool(config.get("enabled", False) and player.path == "ghost")


def ghost_phase_two_config() -> dict[str, Any]:
    return ghost_cultivation_config().get("phase_two", {})


def active_bound_souls(player: Player) -> list[tuple[str, dict[str, Any]]]:
    if not ghost_cultivation_active(player) or is_possessed(player):
        return []
    by_id = {str(row.get("id")): row for row in player.ghost_bound_souls}
    return [(slot, by_id[soul_id]) for slot, soul_id in player.ghost_soul_slots.items()
            if slot in SOUL_SLOTS and soul_id in by_id]


def active_soul_traits(player: Player) -> set[str]:
    return {
        str(soul.get("soul_trait", {}).get("name", ""))
        for _, soul in active_bound_souls(player)
        if str(soul.get("soul_trait", {}).get("name", "")) in SOUL_TRAIT_RULES
    }


def active_generated_soul_traits(player: Player) -> list[dict[str, Any]]:
    return [
        copy.deepcopy(trait)
        for _, soul in active_bound_souls(player)
        if isinstance((trait := soul.get("soul_trait")), dict)
        and bool(trait.get("generated"))
        and not validate_generated_soul_trait(trait)
    ]


def ghost_soul_effects(player: Player) -> dict[str, float]:
    config = ghost_phase_two_config().get("soul_slots", {})
    seven_cap = max(0.0, float(config.get("seven_effect_cap", config.get("effect_cap", 0.25))))
    three_coefficient = max(0.0, float(config.get("three_soul_log_coefficient", 0.18)))
    scale = max(1.0, float(config.get("power_scale", 2500.0)))
    result = {key: 0.0 for key in {
        "opportunity", "external_mp", "external_hp", "mobility", "might",
        "resolve", "guard", "sense", "breach", "sustain",
    }}
    for slot, soul in active_bound_souls(player):
        stat = SOUL_SLOTS[slot][0]
        power = max(0.0, float(soul.get("combat_power", 0.0)))
        value = (
            three_coefficient * math.log1p(power / scale)
            if stat in THREE_SOUL_STATS
            else seven_cap * (1.0 - math.exp(-power / scale))
        )
        result[stat] += value
    return result


def ghost_soul_pressure(player: Player) -> tuple[float, float]:
    if not ghost_cultivation_active(player) or is_possessed(player):
        return 0.0, 0.0
    pressure = sum(max(0.0, float(soul.get("soul_pressure", 0.0)))
                   for _, soul in active_bound_souls(player))
    per_point = max(0.0, float(ghost_phase_two_config().get("pressure_modifier_per_point", 0.01)))
    return pressure, pressure * per_point


def ghost_external_hp_bonus(player: Player) -> float:
    return intrinsic_hp_reference(player) * ghost_soul_effects(player)["external_hp"]


def ghost_external_mp_bonus(player: Player) -> float:
    return intrinsic_mp_reference(player) * ghost_soul_effects(player)["external_mp"]


def ghost_opportunity_multiplier(player: Player) -> float:
    multiplier = 1.0 + ghost_soul_effects(player)["opportunity"]
    if "宿慧" in active_soul_traits(player):
        multiplier *= 1.08
    if ghost_cultivation_active(player) and player.ghost_attachment:
        multiplier *= max(0.0, float(player.ghost_attachment.get("cultivation_efficiency_multiplier", 1.0)))
    return multiplier


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
    if ghost_cultivation_config().get("infinite_lifespan", True) and player.lifespan is not None:
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
    from .rules import opportunity_required

    return bool(
        player.layer >= current_realm.layers
        and player.opportunity >= opportunity_required(player)
    )


def perform_reincarnation(player: Player) -> dict[str, Any]:
    """Apply the player-only, persistent part of reincarnation.

    Game-level blockers and history remain the mixin's responsibility, keeping
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


class GhostSystemMixin:
    def assert_ghost_operation_allowed(self, game_id: str, operation: str) -> None:
        """Enforce the controlled-state boundary at the HTTP command gateway."""
        game = self._load(game_id)
        if game.player.ghost_captor and operation not in {
            "advance", "choice", "use-item", "settings", "ghost-soul", "ghost-constraint",
        }:
            raise ValueError("魂印受制于拘魂者，当前功能要求自由行动主体，因而不可使用")

    @staticmethod
    def _post_battle_possession_candidates(game: GameState) -> list[dict[str, Any]]:
        """Return captives that can save a free ghost at a routine battle death."""
        player = game.player
        if not has_ghost_core(player) or player.ghost_captor or is_possessed(player):
            return []
        candidates: list[dict[str, Any]] = []
        for prisoner in player.prisoners:
            allowed, _ = can_possess(player, prisoner)
            if allowed:
                candidates.append(copy.deepcopy(prisoner))
        return candidates

    def _prepare_post_battle_possession(self, game: GameState, source_event: str) -> bool:
        candidates = self._post_battle_possession_candidates(game)
        if not candidates:
            return False
        choices = [{
            "id": str(row.get("id")),
            "text": (
                f"夺舍 {row.get('name', '无名俘虏')} · "
                f"{REALMS[int(row.get('realm_index', 0))].name}{int(row.get('layer', 1))}层 · "
                f"{int(row.get('age', game.player.age))}岁"
            ),
            "enabled": True,
        } for row in candidates]
        game.pending_event = {
            "id": "SYS_POST_BATTLE_POSSESSION",
            "version": 1,
            "title": "战陨夺舍",
            "body": "肉身已在非剧情战中陨灭，但本魂尚有一线余地。你可以消耗一次夺舍次数，占据一名不高于自身境界的俘虏；也可以放弃并结束此生。",
            "choices": choices,
            "runtime": {
                "source_event": source_event,
                "source_realm": game.player.realm_index,
                "prisoner_ids": [choice["id"] for choice in choices],
            },
        }
        return True

    def post_battle_possess(self, game_id: str, target_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        pending = game.pending_event or {}
        if player.alive or pending.get("id") != "SYS_POST_BATTLE_POSSESSION":
            raise ValueError("当前没有可结算的战陨夺舍")
        permitted = {str(value) for value in pending.get("runtime", {}).get("prisoner_ids", [])}
        if target_id not in permitted:
            raise ValueError("该俘虏不在本次战陨夺舍候选中")
        target = next((row for row in player.prisoners if str(row.get("id")) == target_id), None)
        if target is None:
            raise ValueError("目标俘虏已经不存在")
        allowed, reason = can_possess(player, target)
        if not allowed:
            raise ValueError(reason)
        source_event = str(pending.get("runtime", {}).get("source_event", "SYS_COMBAT"))
        player.alive = True
        player.death_reason = None
        player.prisoners.remove(target)
        host = enter_host_body(player, target)
        game.pending_event = None
        game.history.append(HistoryRecord(
            "SYS_POST_BATTLE_POSSESSION", 1, player.age, "借尸还魂", target_id, "possessed",
            f"战陨之际，你舍弃旧躯并夺取{host['name']}的肉身；年龄与寿元均以这具肉身为准。",
            {
                "host_id": host.get("id"), "source_event": source_event,
                "body_age": current_body_age(player), "world_age": player.age,
                "lifespan": player.lifespan,
                "possession_count": player.possession_count,
            },
            ["system", "ghost", "possession", "combat", "resurrection"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _ensure_ghost_parade(self, game: GameState, rng: random.Random) -> None:
        config = ghost_phase_two_config().get("parade", {})
        if not config.get("enabled", False) or game.ghost_parade:
            return
        # World ecology owns a deterministic sub-stream so enabling the DLC
        # cannot perturb existing event/combat rolls in the base game.
        parade_rng = random.Random(f"{game.seed}:ghost-parade:{game.player.age}:{game.player.world}")
        unit = max(1, int(WORLD_SYSTEMS["time_units"][str(game.player.realm_index)]))
        gap_units = parade_rng.randint(
            max(3, int(config.get("min_interval_units", 5))),
            max(3, int(config.get("max_interval_units", 9))),
        )
        locations = [row["id"] for row in self.maps.public_map(
            game.player.world, game.player.location_id, game.player.realm_index,
            WORLD_SYSTEMS["world_names"].get(game.player.world, game.player.world),
        ).get("locations", [])]
        game.ghost_parade = {
            "status": "scheduled", "world": game.player.world,
            "location_id": parade_rng.choice(locations) if locations else game.player.location_id,
            "start_age": game.player.age + gap_units * unit,
            "end_age": game.player.age + (gap_units + int(config.get("duration_units", 2))) * unit,
            "announced": False, "participated": False, "souls": [],
        }

    def _generate_parade_souls(self, game: GameState, rng: random.Random) -> list[dict[str, Any]]:
        from .rules import expected_combat_power

        surnames = "沈顾谢陆萧楚苏宁白叶"
        given = ("无咎", "照夜", "忘川", "玄衣", "引灯", "归尘", "青冥", "幽篁")
        count = max(3, int(ghost_phase_two_config().get("parade", {}).get("soul_count", 6)))
        souls = []
        for index in range(count):
            realm_index = max(0, min(len(REALMS) - 1, game.player.realm_index + rng.choice((-1, 0, 0, 1))))
            layer = rng.randint(1, REALMS[realm_index].layers)
            soul_trait = generate_soul_trait(rng)
            soul_power = round(expected_combat_power(realm_index, layer) * rng.uniform(0.72, 1.18), 1)
            pressure_rules = ghost_phase_two_config().get("soul_pressure", {})
            pressure = (
                float(pressure_rules.get("base", 0.5))
                + float(pressure_rules.get("power_cap", 2.0))
                * (1.0 - math.exp(-soul_power / max(1.0, float(pressure_rules.get("power_scale", 5000.0)))))
            )
            souls.append({
                "id": f"soul_{game.seed}_{game.player.age}_{index}",
                "npc_id": f"parade_{game.seed}_{game.player.age}_{index}",
                "name": f"{rng.choice(surnames)}{rng.choice(given)}", "path": "ghost", "race": "human",
                "realm_index": realm_index, "layer": layer,
                "combat_power": soul_power,
                "affinity": rng.randint(-15, 25), "defeated": False, "befriended": False,
                "is_bound_soul": False,
                "personality": rng.choice(("执拗", "温和", "凶厉", "多疑", "洒脱")),
                "npc_relations": [], "skills": [soul_trait["name"]],
                "faction_inclination": rng.choice(("散魂", "阴司", "宗门故旧", "无阵营")),
                "original_identity": f"{REALMS[realm_index].name}遗魂",
                "soul_pressure": round(pressure, 2),
                "soul_trait": soul_trait,
            })
        return souls

    def _advance_ghost_phase_two_year(self, game: GameState, rng: random.Random) -> None:
        if not ghost_phase_two_config().get("enabled", False):
            return
        self._ensure_ghost_parade(game, rng)
        parade = game.ghost_parade
        if not parade:
            return
        phase_rng = random.Random(f"{game.seed}:ghost-phase-two:{game.player.age}")
        unit = max(1, int(WORLD_SYSTEMS["time_units"][str(game.player.realm_index)]))
        announce_age = int(parade.get("start_age", game.player.age)) - 2 * unit
        if not parade.get("announced") and game.player.age >= announce_age:
            parade["announced"] = True
            parade["status"] = "announced"
            game.history.append(HistoryRecord(
                "SYS_GHOST_PARADE_ANNOUNCED", 1, game.player.age, "百鬼将行", None, "announced",
                "阴风先至，百鬼夜行将在两个游戏时间单位后降临；地图已经标出鬼门所在。",
                {"location_id": parade.get("location_id"), "start_age": parade.get("start_age")},
                ["system", "ghost", "parade", "announcement"],
            ))
        if game.player.age >= int(parade.get("start_age", 10**18)) and parade.get("status") != "active":
            parade["status"] = "active"
            parade["souls"] = self._generate_parade_souls(game, phase_rng)
            game.history.append(HistoryRecord(
                "SYS_GHOST_PARADE_STARTED", 1, game.player.age, "百鬼夜行", None, "active",
                "鬼门洞开，游魂并非临时数值，而以姓名、修为、魂压与魂性现身世间。",
                {"location_id": parade.get("location_id"), "soul_count": len(parade["souls"])},
                ["system", "ghost", "parade", "world_event"],
            ))
        if game.player.age >= int(parade.get("end_age", 10**18)):
            escaped = len(parade.get("souls", []))
            game.history.append(HistoryRecord(
                "SYS_GHOST_PARADE_ENDED", 1, game.player.age, "鬼门复闭", None, "ended",
                f"夜行散去，仍有 {escaped} 道未被拘束的魂魄归入幽暗。下一次异动将在未来重新孕生。",
                {"escaped_souls": escaped}, ["system", "ghost", "parade"],
            ))
            game.ghost_parade = {}
            self._ensure_ghost_parade(game, rng)
        captor = game.player.ghost_captor
        if captor:
            captor["followed_years"] = int(captor.get("followed_years", 0)) + 1
            if phase_rng.random() < 0.18:
                locations = [row["id"] for row in self.maps.public_map(
                    game.player.world, game.player.location_id, game.player.realm_index,
                    WORLD_SYSTEMS["world_names"].get(game.player.world, game.player.world),
                ).get("locations", []) if row.get("travel_status") in {"ok", "current"}]
                if locations:
                    captor["location_id"] = phase_rng.choice(locations)
            game.player.location_id = captor.get("location_id", game.player.location_id)
            if phase_rng.random() < 0.12:
                from .rules import combat_power
                contribution = combat_power(game.player)
                captor_power = max(1.0, float(captor.get("combat_power", 1.0)))
                owner_id = str(captor.get("npc_id") or captor.get("id", ""))
                owner = self._find_npc(game, owner_id) or SectNpc(
                    owner_id or f"ghost_owner_{game.seed}_{game.player.age}",
                    str(captor.get("name", "拘魂者")), "拘魂者",
                    int(captor.get("realm_index", game.player.realm_index)),
                    int(captor.get("layer", 1)), game.player.age, None,
                    spirit_root=str(captor.get("spirit_root", "none")),
                    path=str(captor.get("path", "dao")), race=str(captor.get("race", "human")),
                    world=game.player.world,
                )
                opponents = [
                    npc for npc in self._all_world_npcs(game)
                    if npc.alive and npc.world == game.player.world and npc.id != owner.id
                ]
                opponent = phase_rng.choice(opponents) if opponents else None
                opponent_power = self._npc_power(opponent) if opponent else captor_power * phase_rng.uniform(0.55, 1.25)
                won = phase_rng.random() < min(
                    0.92,
                    (captor_power + contribution * 0.45)
                    / (captor_power + contribution * 0.45 + opponent_power),
                )
                transfer = (
                    self._maybe_transfer_player_dependency(
                        game, owner, opponent, phase_rng, context="ghost_vassal_battle",
                    )
                    if not won and opponent else ""
                )
                game.history.append(HistoryRecord(
                    "SYS_GHOST_VASSAL_BATTLE", 1, game.player.age, "魂仆随战", None,
                    "victory" if won else "defeat",
                    f"{captor.get('name', '拘魂者')}卷入争斗，你被魂印强制召出参战；"
                    + ("合力压下了对手。" if won else "主仆皆负伤退走。")
                    + (f" {transfer}" if transfer else ""),
                    {
                        "ghost_contribution": contribution, "captor_power": captor_power,
                        "opponent_id": opponent.id if opponent else None,
                    },
                    ["system", "ghost", "controlled", "combat"],
                ))

    def ghost_parade_action(self, game_id: str, soul_id: str, action: str) -> dict[str, Any]:
        from .rules import combat_power
        from .runtime import decode_rng, encode_rng

        game = self._load(game_id)
        player = game.player
        if not player.alive:
            raise ValueError("此生已经结束")
        if not ghost_cultivation_active(player) or player.ghost_captor or is_possessed(player):
            raise ValueError("只有自由鬼修能够参与百鬼夜行")
        parade = game.ghost_parade
        if parade.get("status") != "active" or parade.get("world") != player.world \
                or parade.get("location_id") != player.location_id:
            raise ValueError("当前所在地没有正在发生的百鬼夜行")
        rng = decode_rng(game.seed, game.rng_state)
        if action == "participate":
            if parade.get("participated"):
                raise ValueError("本次百鬼夜行已经参悟过")
            parade["participated"] = True
            reduction = max(0.0, float(ghost_phase_two_config().get("parade", {}).get("participate_reduction_pp", 0.005)))
            before = player.ghost_soul_erosion_rate_pp
            player.ghost_soul_erosion_rate_pp = max(0.0, before - reduction)
            result, summary = "participated", f"你观百鬼执念流转，未来魂蚀率降低 {before-player.ghost_soul_erosion_rate_pp:.4f} 个百分点。"
        else:
            soul = next((row for row in parade.get("souls", []) if row.get("id") == soul_id), None)
            if not soul:
                raise ValueError("这道游魂已经离开夜行")
            if action == "befriend":
                if soul.get("befriended"):
                    raise ValueError("本次百鬼夜行已经与这道游魂结交过")
                soul["befriended"] = True
                soul["affinity"] = min(100, float(soul.get("affinity", 0)) + rng.randint(8, 18))
                personality_bonus = 0.10 if soul.get("personality") in {"温和", "洒脱"} else -0.08 if soul.get("personality") in {"凶厉", "多疑"} else 0
                realm_bonus = max(-0.08, min(0.08, (player.realm_index - int(soul.get("realm_index", 0))) * 0.02))
                chance = max(0.05, min(0.75, 0.18 + soul["affinity"] / 200 + personality_bonus + realm_bonus))
                healed = rng.random() < chance
                reduction = float(ghost_phase_two_config().get("parade", {}).get("befriend_reduction_pp", 0.002)) if healed else 0
                player.ghost_soul_erosion_rate_pp = max(0.0, player.ghost_soul_erosion_rate_pp - reduction)
                result, summary = "befriended", f"你与{soul['name']}交换前尘，亲近有所增长" + (f"，魂蚀率降低 {reduction:.4f} 个百分点。" if healed else "。")
            elif action in {"fight", "capture"}:
                own = combat_power(player)
                chance = max(0.08, min(0.95, own / max(1.0, own + float(soul["combat_power"]))))
                combat_result, combat_summary = self._combat(game, {
                    "target_name": soul["name"], "target_power": float(soul["combat_power"]),
                    "target_realm_index": int(soul["realm_index"]), "target_layer": int(soul["layer"]),
                    "combat_type": "cultivator", "race": "human", "path": "ghost",
                    "capture": False, "kill_karma": False, "npc_id": soul.get("npc_id"),
                }, lethal=False, rng=rng)
                if combat_result != "victory":
                    result, summary = combat_result, f"{combat_summary} 你未能拘住{soul['name']}（战前估算 {chance:.0%}）。"
                else:
                    soul["defeated"] = True
                    result, summary = "victory", f"{combat_summary} 你击溃{soul['name']}的外层魂衣。"
                    if action == "capture":
                        soul["is_bound_soul"] = True
                        player.ghost_bound_souls.append(copy.deepcopy(soul))
                        parade["souls"].remove(soul)
                        player.milestones["ghost_souls_bound"] = int(player.milestones.get("ghost_souls_bound", 0)) + 1
                        result, summary = "captured", f"你击溃并拘住{soul['name']}；其姓名、修为、魂压与魂性被永久保存。"
            elif action == "bind":
                if not soul.get("defeated"):
                    raise ValueError("必须先在交锋中击溃这道游魂")
                soul["is_bound_soul"] = True
                player.ghost_bound_souls.append(copy.deepcopy(soul))
                parade["souls"].remove(soul)
                player.milestones["ghost_souls_bound"] = int(player.milestones.get("ghost_souls_bound", 0)) + 1
                result, summary = "captured", f"你将{soul['name']}收入魂册，其身份与魂性均被保留。"
            else:
                raise ValueError("未知的百鬼夜行行动")
        game.history.append(HistoryRecord(
            "SYS_GHOST_PARADE_ACTION", 1, player.age, "夜行抉择", action, result, summary,
            {"soul_id": soul_id}, ["action", "ghost", "parade"],
        ))
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def ghost_soul_action(self, game_id: str, soul_id: str, action: str, slot: str = "") -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not player.alive:
            raise ValueError("此生已经结束")
        if not ghost_phase_two_config().get("enabled", False) or not has_ghost_core(player):
            raise ValueError("只有鬼魂核心能够管理拘魂")
        soul = next((row for row in player.ghost_bound_souls if str(row.get("id")) == soul_id), None)
        if action == "equip":
            if is_possessed(player):
                raise ValueError("夺舍期间十魂全部沉寂，不能更换")
            if not soul or slot not in SOUL_SLOTS:
                raise ValueError("魂魄或魂位不存在")
            for occupied, equipped_id in list(player.ghost_soul_slots.items()):
                if equipped_id == soul_id:
                    player.ghost_soul_slots.pop(occupied, None)
            player.ghost_soul_slots[slot] = soul_id
            if len(player.ghost_soul_slots) == len(SOUL_SLOTS):
                player.milestones["ghost_ten_soul_slots"] = 1
            summary = f"{soul['name']}入驻{slot}，立即以该魂位规则生效。"
        elif action == "unequip":
            target_slot = slot or next((key for key, value in player.ghost_soul_slots.items() if value == soul_id), "")
            if target_slot not in player.ghost_soul_slots:
                raise ValueError("该魂魄没有入驻魂位")
            player.ghost_soul_slots.pop(target_slot)
            summary = f"你撤下了{target_slot}魂位，不消耗时间。"
        elif action == "release":
            if not soul:
                raise ValueError("魂册中没有这道魂魄")
            player.ghost_soul_slots = {key: value for key, value in player.ghost_soul_slots.items() if value != soul_id}
            player.ghost_bound_souls.remove(soul)
            summary = f"你解开魂印，放归{soul['name']}；此操作不可撤销。"
        else:
            raise ValueError("未知魂魄操作")
        game.history.append(HistoryRecord(
            "SYS_GHOST_SOUL_ACTION", 1, player.age, "十魂轮转", action, "success", summary,
            {"soul_id": soul_id, "slot": slot}, ["action", "ghost", "bound_soul"],
        ))
        game.updated_at = now_iso(); self.store.save(game)
        return self.present(game)

    def ghost_attachment_action(self, game_id: str, action: str, item_id: str = "") -> dict[str, Any]:
        game = self._load(game_id); player = game.player
        if not player.alive:
            raise ValueError("此生已经结束")
        if not ghost_cultivation_active(player) or player.ghost_captor or is_possessed(player):
            raise ValueError("当前魂体不能进行附灵")
        if action == "leave":
            if not player.ghost_attachment:
                raise ValueError("当前没有附着任何器物")
            name = player.ghost_attachment.get("name", "器物")
            player.ghost_attachment = None
            summary = f"你从{name}中逸出，恢复自由魂体。"
        elif action == "attach":
            item = next((row for row in player.inventory if row.id == item_id and row.quantity > 0), None)
            if not item:
                raise ValueError("行囊中没有该器物")
            quality = max(0.0, item.combat_bonus + item.hp_bonus + item.mp_bonus + item.opportunity_bonus * 100)
            if quality <= 0 and "ghost_vessel" not in item.tags and not any(key in item.name for key in ("器", "剑", "刀", "鼎", "炉", "珠", "灯", "匣", "舟")):
                raise ValueError("只能附着兵器、法器或魂器")
            player.ghost_attachment = {
                "item_id": item.id, "name": item.name, "spirit_name": f"{item.name}器灵·{player.name}",
                "erosion_growth_multiplier": (
                    float(item.erosion_growth_multiplier) if item.erosion_growth_multiplier != 1.0
                    else max(0.45, 0.92 - min(0.47, quality / 5000))
                ),
                "cultivation_efficiency_multiplier": (
                    float(item.cultivation_efficiency_multiplier) if item.cultivation_efficiency_multiplier != 1.0
                    else max(0.68, 0.94 - min(0.26, quality / 10000))
                ),
            }
            summary = f"你附入{item.name}成为器灵；仍可自由行动并随时离器。"
        else:
            raise ValueError("未知附灵操作")
        game.history.append(HistoryRecord(
            "SYS_GHOST_ATTACHMENT", 1, player.age, "附灵", action, "success", summary,
            {"item_id": item_id}, ["action", "ghost", "attachment"],
        ))
        game.updated_at = now_iso(); self.store.save(game)
        return self.present(game)

    def ghost_constraint_action(self, game_id: str, action: str) -> dict[str, Any]:
        from .rules import combat_power, max_hp, max_mp
        from .runtime import decode_rng, encode_rng

        game = self._load(game_id); player = game.player
        if not player.alive:
            raise ValueError("此生已经结束")
        if not player.ghost_captor:
            raise ValueError("当前并未受制于拘魂者")
        rng = decode_rng(game.seed, game.rng_state)
        captor = player.ghost_captor
        target_power = max(1.0, float(captor.get("combat_power", 1.0)))
        chance = max(0.05, min(0.9, combat_power(player) / (combat_power(player) + target_power)))
        if action == "wait":
            advance_player_age(player)
            self._advance_world_year(game, rng, [], encounters=False)
            if player.alive:
                self._advance_soul_erosion_time(game, 1)
            result, summary = "waited", "你在拘魂禁制中熬过一年，并随拘魂者一同行动。"
        elif action == "resist":
            if rng.random() < chance:
                captor_id = str(captor.get("npc_id") or captor.get("id", ""))
                captor_npc = self._find_npc(game, captor_id)
                if captor_npc:
                    captor_npc.affinity = float(
                        WORLD_SYSTEMS["relationship"].get("relationship_release_affinity", 0)
                    )
                player.ghost_captor = None
                result, summary = "escaped", f"你击破拘魂禁制，重获自由（胜算 {chance:.0%}）；双方好感重置为中立。"
            else:
                self._die(game, "反抗拘魂者失败，魂印崩碎，魂飞魄散", "SYS_GHOST_RESIST_FAILED")
                result, summary = "dead", f"反抗失败，魂体被禁制磨灭（胜算 {chance:.0%}）。"
        elif action == "possess":
            allowed, reason = can_possess(player, captor)
            if not allowed:
                raise ValueError(reason)
            if rng.random() < chance:
                captor_npc = self._find_npc(game, str(captor.get("npc_id") or captor.get("id", "")))
                host = enter_host_body(player, captor)
                if captor_npc:
                    captor_npc.alive = False
                    captor_npc.death_reason = f"被{player.name}反夺肉身，原神魂不复存在"
                player.hp = min(player.hp, max_hp(player)); player.mp = min(player.mp, max_mp(player))
                result, summary = "possessed", f"你反夺魂印，成功占据{host['name']}的肉身（胜算 {chance:.0%}）。"
            else:
                self._die(game, "夺舍拘魂者失败，神魂遭反噬而灭", "SYS_GHOST_POSSESSION_FAILED")
                result, summary = "dead", f"夺舍失败，神魂遭反噬而灭（胜算 {chance:.0%}）。"
        else:
            raise ValueError("未知受制行动")
        game.history.append(HistoryRecord(
            "SYS_GHOST_CONSTRAINT", 1, player.age, "拘魂禁制", action, result, summary,
            {"captor_id": captor.get("npc_id"), "chance": chance}, ["action", "ghost", "controlled"],
        ))
        game.rng_state = encode_rng(rng); game.updated_at = now_iso(); self.store.save(game)
        return self.present(game)

    def _capture_defeated_ghost(self, game: GameState, target: dict[str, Any], rng: random.Random) -> bool:
        player = game.player
        if not ghost_cultivation_active(player) or player.ghost_captor or is_possessed(player):
            return False
        if target.get("combat_type") not in {None, "cultivator"} or str(target.get("race", "human")) not in {"human", "demon", "immortal"}:
            return False
        base = float(ghost_phase_two_config().get("defeat_capture_chance", 0.45))
        personality = str(target.get("personality", ""))
        base += 0.15 if personality in {"凶厉", "多疑", "贪婪", "残酷"} else -0.12 if personality in {"仁厚", "温和"} else 0
        base += 0.10 if str(target.get("path", "")) in {"ghost", "demonic"} else 0
        capture_chance = max(0.05, min(0.90, base))
        if rng.random() >= capture_chance:
            return False
        player.hp = 1.0
        player.mp = max(0.0, player.mp)
        player.ghost_attachment = None
        player.ghost_captor = {
            "id": str(target.get("npc_id") or target.get("id") or f"captor_{game.seed}_{player.age}"),
            "npc_id": target.get("npc_id"), "name": str(target.get("target_name", "拘魂修士")),
            "realm_index": int(target.get("target_realm_index", player.realm_index)),
            "layer": int(target.get("target_layer", 1)), "path": str(target.get("path", "dao")),
            "race": str(target.get("race", "human")), "spirit_root": str(target.get("spirit_root", "none")),
            "combat_power": float(target.get("target_power", 1.0)),
            "main_technique_id": target.get("main_technique_id"),
            "location_id": player.location_id, "source": "defeat_capture", "followed_years": 0,
            "controlled_form": rng.choice(("拘魂", "法器器灵", "魂幡附庸")),
            "capture_chance": capture_chance, "affinity": float(target.get("affinity", 0)),
        }
        if player.ghost_captor["controlled_form"] == "法器器灵":
            player.milestones["ghost_became_others_attachment"] = 1
        game.history.append(HistoryRecord(
            "SYS_GHOST_CAPTURED", 1, player.age, "败亡拘魂", None, "controlled",
            f"{player.ghost_captor['name']}没有立刻灭杀你，而是以魂印拘束本魂；失败的反抗与夺舍都会真正魂飞魄散。",
            {
                "captor_id": player.ghost_captor["id"],
                "controlled_form": player.ghost_captor["controlled_form"],
            }, ["system", "ghost", "controlled", "negative"],
        ))
        return True

    def leave_possessed_body(self, game_id: str) -> dict[str, Any]:
        from .rules import max_hp, max_mp
        game = self._load(game_id); player = game.player
        if not player.alive:
            raise ValueError("此生已经结束")
        host = leave_host_body(player)
        player.hp = min(max(1.0, player.hp), max_hp(player)); player.mp = min(player.mp, max_mp(player))
        game.history.append(HistoryRecord(
            "SYS_POSSESSION_LEFT", 1, player.age, "离舍归魂", None, "left",
            f"你主动离开{host.get('name', '宿主')}；这具肉身永久毁去，已经消耗的夺舍次数不返还。",
            {"host_id": host.get("id"), "possession_count": player.possession_count},
            ["action", "ghost", "possession"],
        ))
        game.updated_at = now_iso(); self.store.save(game)
        return self.present(game)

    def _advance_soul_erosion_time(self, game: GameState, elapsed_years: int = 1) -> bool:
        completed_units = accumulate_soul_erosion_time(game.player, elapsed_years)
        return not completed_units or self._apply_soul_erosion_units(game, completed_units)

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

    def prepare_ghost_reincarnation(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not ghost_cultivation_active(player):
            raise ValueError(f"未启用【{GHOST_DLC_NAME}】或当前并非鬼修")
        if not player.alive or game.pending_event or game.active_trial or player.imprisonment or player.sealed_cultivation:
            raise ValueError("当前状态无法进入轮回")
        if not can_reincarnate(player):
            raise ValueError("只有抵达大境界最终瓶颈并将机缘修至圆满，方可入轮回")
        template = self.events_by_id.get("SYS_GHOST_REINCARNATION")
        if template is None:
            raise ValueError("轮回事件内容未加载")
        event = self._instantiate_event(
            template, game, random.Random(f"ghost-reincarnation:{game.seed}:{player.age}"),
        )
        source_count = int(player.ghost_reincarnation_imprints.get(str(player.realm_index), 0))
        highwater = (
            f"{REALMS[int(player.ghost_intrinsic_highwater_realm)].name}"
            f"{int(player.ghost_intrinsic_highwater_layer or 1)}层"
        )
        bonus = float(ghost_cultivation_config().get("reincarnation_bonus_per_mark", 0.05))
        event["body"] = (
            f"轮回门在你识海深处开启。继续后，你将舍去"
            f"{REALMS[player.realm_index].name}{player.layer}层修为并回到{REALMS[1].name}1层，"
            f"留下本境第 {source_count + 1} 枚轮回印记，使本境及以下道路的突破经验增加 {bonus:.0%}。\n\n"
            f"未用往生 {player.ghost_wangsheng_energy} 点将归零；魂蚀率保持 "
            f"{player.ghost_soul_erosion_rate_pp:.4f}%，既有魂伤不会恢复；"
            f"神识等级与已有神识经验将重置为初始的 1 级、0 经验；"
            f"本体成长最高水位仍为{highwater}，重新超过此前修为前不会再次获得境界来源的本源成长。"
            f"所有突破的最终有效概率仍封顶 98%。"
        )
        game.pending_event = event
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _complete_ghost_reincarnation(
        self, game: GameState, *, record_history: bool,
    ) -> dict[str, Any]:
        from .rules import max_hp, max_mp

        player = game.player
        transition = perform_reincarnation(player)
        source_realm = int(transition["source_realm"])
        source_layer = int(transition["source_layer"])
        source_label = str(transition["source_label"])
        key = str(source_realm)
        lost_wangsheng = int(transition["wangsheng_lost"])
        player.hp = min(player.hp, max_hp(player))
        player.mp = min(player.mp, max_mp(player))
        wangsheng_summary = (
            f"未用往生 {lost_wangsheng} 点尽数散失"
            if lost_wangsheng else "未用往生依当前规则没有损失"
        )
        summary = (
            f"你舍去{source_label}修为，重归练气一层；留下第 {transition['imprint_count']} "
            f"道本境轮回印记，{wangsheng_summary}。神识重归 1 级且经验清零；魂蚀与既有魂伤均未复原。"
        )
        transition["summary"] = summary
        if record_history:
            game.history.append(HistoryRecord(
                "SYS_GHOST_REINCARNATION", 2, player.age, "舍世入轮回", key, "reincarnated",
                summary,
                {
                    "source_realm": source_realm, "source_layer": source_layer,
                    "imprints": dict(player.ghost_reincarnation_imprints), "wangsheng_lost": lost_wangsheng,
                },
                ["system", "ghost", "reincarnation", "milestone"],
            ))
        return transition

    def reincarnate_ghost(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not ghost_cultivation_active(player):
            raise ValueError(f"未启用【{GHOST_DLC_NAME}】或当前并非鬼修")
        if not player.alive or game.pending_event or game.active_trial or player.imprisonment or player.sealed_cultivation:
            raise ValueError("当前状态无法进入轮回")
        self._complete_ghost_reincarnation(game, record_history=True)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _public_ghost_phase_two(self, game: GameState) -> dict[str, Any]:
        player = game.player
        effects = ghost_soul_effects(player)
        pressure, pressure_modifier = ghost_soul_pressure(player)
        by_id = {str(row.get("id")): row for row in player.ghost_bound_souls}
        def public_soul(raw: dict[str, Any] | None) -> dict[str, Any] | None:
            if not raw:
                return None
            result = copy.deepcopy(raw)
            trait = result.get("soul_trait") or {}
            trait_name = str(trait.get("name", ""))
            if trait_name in SOUL_TRAIT_RULES:
                trait["description"] = SOUL_TRAIT_RULES[trait_name]
                trait["rule"] = SOUL_TRAIT_RULES[trait_name]
                result["soul_trait"] = trait
            elif trait.get("generated"):
                reasons = validate_generated_soul_trait(trait)
                trait["valid"] = not reasons
                trait["invalid_reasons"] = reasons
                result["soul_trait"] = trait
            return result
        slots = [{
            "id": slot, "stat": stat, "stat_name": label,
            "soul_id": player.ghost_soul_slots.get(slot),
            "effect": round(effects.get(stat, 0.0), 6),
            "curve": "unbounded_diminishing" if stat in THREE_SOUL_STATS else "capped_saturation",
            "soul": public_soul(by_id.get(player.ghost_soul_slots.get(slot, ""))),
        } for slot, (stat, label) in SOUL_SLOTS.items()]
        parade = copy.deepcopy(game.ghost_parade)
        if parade and not parade.get("announced"):
            parade = {"status": "dormant", "announced": False}
        elif parade:
            parade["souls"] = [public_soul(row) for row in parade.get("souls", [])]
            parade["at_location"] = bool(
                parade.get("world") == player.world and parade.get("location_id") == player.location_id
            )
            try:
                parade["location_name"] = self.maps.location(
                    str(parade.get("world")), str(parade.get("location_id")),
                )["name"]
            except Exception:
                parade["location_name"] = str(parade.get("location_id", "未知"))
        attachable = [{
            "id": item.id, "name": item.name, "quantity": item.quantity,
        } for item in player.inventory if item.quantity > 0 and (
            item.combat_bonus + item.hp_bonus + item.mp_bonus + item.opportunity_bonus * 100 > 0
            or "ghost_vessel" in item.tags
            or any(key in item.name for key in ("器", "剑", "刀", "鼎", "炉", "珠", "灯", "匣", "舟"))
        )]
        state = "possessed" if is_possessed(player) else "controlled" if player.ghost_captor \
            else "attached" if player.ghost_attachment else "free"
        return {
            "enabled": bool(ghost_phase_two_config().get("enabled", False)), "state": state,
            "state_name": {"free": "自由魂体", "attached": "附灵器魂", "controlled": "受制拘魂", "possessed": "夺舍寄身"}[state],
            "slots": slots, "bound_souls": [public_soul(row) for row in player.ghost_bound_souls],
            "effects": {key: round(value, 6) for key, value in effects.items()},
            "pressure": round(pressure, 4), "pressure_modifier": round(pressure_modifier, 6),
            "parade": parade, "attachment": copy.deepcopy(player.ghost_attachment),
            "attachable_items": attachable, "captor": copy.deepcopy(player.ghost_captor),
            "host": copy.deepcopy(player.ghost_host_body),
            "possession_count": player.possession_count, "possession_limit": possession_limit(player),
            "souls_suspended": is_possessed(player),
        }

    def _public_map_with_ghost_parade(self, game: GameState, location_id: str) -> dict[str, Any]:
        data = self.maps.public_map(
            game.player.world, location_id, game.player.realm_index,
            WORLD_SYSTEMS["world_names"].get(game.player.world, game.player.world),
            lambda destination: self._monster_travel_multiplier(game.player, destination),
        )
        parade = game.ghost_parade
        if parade and parade.get("announced") and parade.get("world") == game.player.world:
            for location in data.get("locations", []):
                if location.get("id") == parade.get("location_id"):
                    location["ghost_parade"] = {
                        "status": parade.get("status"), "start_age": parade.get("start_age"),
                        "end_age": parade.get("end_age"), "label": "百鬼夜行",
                    }
        # V2 ground arrays are map fixtures rather than invisible status
        # bonuses. Publish a compact marker without copying their material
        # snapshots into every map row.
        for location in data.get("locations", []):
            arrays = [
                row for row in game.player.formation_ground_arrays
                if row.get("world") == game.player.world
                and row.get("location_id") == location.get("id")
            ]
            if arrays:
                location["ground_formations"] = [{
                    "id": str(row.get("id", "")), "name": str(row.get("name", "镇地阵")),
                    "owner_kind": str(row.get("owner_kind", "player")),
                    "owner_name": str(row.get("owner_name", game.player.name)),
                    "durability": round(float(row.get("durability", 0.0)), 1),
                } for row in arrays]
        return data

    def _public_ghost_system(self, game: GameState) -> dict[str, Any]:
        from .rules import raw_external_hp_bonus, raw_external_mp_bonus

        player = game.player
        if not has_ghost_core(player) or (not ghost_cultivation_config().get("enabled", False) and not is_possessed(player)):
            return {"available": False, "name": GHOST_DLC_NAME}
        if is_possessed(player):
            core = player.ghost_core_state or {}
            hp_reference = max(0.0, float(player.ghost_intrinsic_hp_reference or 0.0))
            mp_reference = max(0.0, float(player.ghost_intrinsic_mp_reference or 0.0))
            hp_current = max(0.0, float(player.ghost_intrinsic_hp_current or 0.0))
            mp_current = max(0.0, float(player.ghost_intrinsic_mp_current or 0.0))
            return {
                "available": True, "name": GHOST_DLC_NAME, "suspended": True,
                "suspension_reason": "夺舍期间鬼魂核心完全沉寂；魂蚀、往生、轮回、印记、十魂与魂压全部冻结。",
                "erosion_rate_pp": round(player.ghost_soul_erosion_rate_pp, 6),
                "wangsheng": player.ghost_wangsheng_energy,
                "intrinsic_hp": {"current": hp_current, "reference": hp_reference, "carry_ratio": hp_current / max(1e-12, hp_reference)},
                "intrinsic_mp": {"current": mp_current, "reference": mp_reference, "carry_ratio": mp_current / max(1e-12, mp_reference)},
                "can_spend_wangsheng": False, "can_reincarnate": False,
                "breakthrough_probability_cap": 0.98,
                "original_realm_index": int(core.get("realm_index", 0)),
                "phase_two": self._public_ghost_phase_two(game),
            }
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
            for index in range(1, len(REALMS))
        ]
        at_bottleneck = can_reincarnate(player)
        effective_marks = reincarnation_effective_marks(player, player.realm_index)
        total_imprints = sum(max(0, int(row["count"])) for row in imprints)
        integrity_ratio = min(hp_ratio, mp_ratio)
        probability_cap = min(
            0.98, max(0.005, float(config.get("reincarnation_final_probability_cap", 0.98))),
        )
        time_unit_years = max(1, int(WORLD_SYSTEMS["time_units"][str(player.realm_index)]))
        erosion_time_progress = max(0.0, min(
            0.999999999999, float(player.ghost_soul_erosion_time_progress),
        ))
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
                "highwater": (
                    f"{REALMS[int(player.ghost_intrinsic_highwater_realm)].name}"
                    f"{int(player.ghost_intrinsic_highwater_layer or 1)}层"
                ),
                "repeated_realm_growth_frozen": True,
            }
        return {
            "available": True,
            "name": GHOST_DLC_NAME,
            "erosion_rate_pp": round(player.ghost_soul_erosion_rate_pp, 6),
            "erosion_time": {
                "progress_ratio": round(erosion_time_progress, 8),
                "elapsed_equivalent_years": round(erosion_time_progress * time_unit_years, 6),
                "time_unit_years": time_unit_years,
                "remaining_equivalent_years": round((1.0 - erosion_time_progress) * time_unit_years, 6),
            },
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
            "suspended": False,
            "phase_two": self._public_ghost_phase_two(game),
        }

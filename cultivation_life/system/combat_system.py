from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from ..combat_traits import COMBAT_TRAIT_REGISTRY
from ..content_registry import MONSTER_BLOODLINE_SETTINGS
from .custom_lineage_system import evaluate_custom_lineage_rules
from ..models import Player, Technique
from .ghost_system import active_generated_soul_traits, active_soul_traits, ghost_soul_effects
from ..ghost_soul_traits import evaluate_generated_soul_traits
from ..monster_bloodline_traits import (
    BLOODLINE_TRAIT_REGISTRY, bloodline_grants_hook, bloodline_hook_names,
    bloodline_stat_modifiers,
)
from ..monster_bloodline_rules import evaluate_generated_traits
from .transformation_system import active_transformation_profile
from .monster_bloodline_system import active_bloodline_profile, bloodline_content_available
from ..monster_general_traits import (
    GENERAL_MONSTER_TRAIT_REGISTRY, active_general_monster_traits,
    general_monster_trait_modifiers,
)
from .formation_system import active_formation_profile, formation_round_effects


STAT_KEYS = ("might", "guard", "mobility", "sense", "sustain", "breach")
STAT_NAMES = {
    "might": "威能", "guard": "防护", "mobility": "身法",
    "sense": "神识", "sustain": "续航", "breach": "破法",
}


@dataclass
class BattleUnit:
    id: str
    name: str
    kind: str
    power: float
    realm_index: int
    path: str = "dao"
    integrity: float = 1.0
    persistent_field: str | None = None
    full_power: float | None = None


@dataclass
class CombatResolution:
    outcome: str
    result_grade: str
    objective: str
    mode: str
    rounds: list[dict[str, Any]]
    key_events: list[str]
    hp_loss_ratio: float
    mp_loss_ratio: float
    player_combat_state: float
    player_combat_state_max: float
    enemy_combat_state: float
    enemy_combat_state_max: float
    enemy_hp_ratio: float
    player_morale: float
    enemy_morale: float
    kill_ready: bool
    capture_ready: bool
    support_updates: list[dict[str, Any]]
    assessment: str
    battlefield_tags: list[str]
    natural_terrain: str
    artificial_conditions: list[str]
    player_stats: dict[str, float]
    enemy_stats: dict[str, float]
    active_transformations: list[dict[str, Any]]
    transformation_traits: list[str]
    bloodline_traits: list[str]
    general_monster_traits: list[str]
    death_prevented: bool
    retreat_impossible: bool
    player_roster: list[dict[str, Any]]
    enemy_roster: list[dict[str, Any]]
    formation_profile: dict[str, Any] | None = None
    enemy_formation_profile: dict[str, Any] | None = None
    formation_integrity_end: float | None = None
    enemy_formation_integrity_end: float | None = None
    formation_experience_gain: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PlayerCombatSystem:
    """Detailed, fully automatic combat used only when the player is present.

    Combat power seeds a six-dimensional profile.  Techniques, path, realm,
    objective, formation, terrain and independent support units then determine
    the actual exchanges.  No method in this class asks for mid-fight input.
    """

    PATH_FACTORS: dict[str, dict[str, float]] = {
        "dao": {},
        "demonic": {"might": 1.12, "guard": 0.94, "sustain": 1.10},
        "ghost": {"might": 0.96, "mobility": 0.94, "sense": 1.22, "sustain": 1.08},
        "monster": {"might": 1.06, "guard": 1.16, "sense": 0.86, "sustain": 1.18},
        "buddhist": {"might": 0.92, "guard": 1.18, "sense": 1.10, "sustain": 1.12},
        "confucian": {"might": 0.96, "sense": 1.14, "breach": 1.12},
    }
    ELEMENT_FACTORS: dict[str, dict[str, float]] = {
        "metal": {"might": 1.06, "breach": 1.10},
        "wood": {"guard": 1.03, "sustain": 1.10},
        "water": {"guard": 1.05, "mobility": 1.04, "sustain": 1.08},
        "fire": {"might": 1.10, "guard": 0.97},
        "earth": {"guard": 1.12, "sustain": 1.06},
        "wind": {"mobility": 1.14, "breach": 1.03},
        "thunder": {"might": 1.08, "breach": 1.12},
        "yin": {"sense": 1.09, "sustain": 1.06},
        "yang": {"guard": 1.06, "breach": 1.07},
        "five_elements": {key: 1.035 for key in STAT_KEYS},
    }
    NATURAL_TERRAINS = {"狭窄", "开阔", "险要"}
    ARTIFICIAL_CONDITIONS = {"禁空", "禁神识", "大阵"}
    TERRAIN_ALIASES = {
        "平原": "开阔", "沙漠": "开阔", "草原": "开阔", "海域": "开阔",
        "群岛": "险要", "山脉": "险要", "荒地": "险要", "尸地": "险要",
        "峡谷": "狭窄", "森林": "狭窄", "城镇": "狭窄",
        "神识压制": "禁神识", "护山大阵": "大阵",
    }
    TERRAIN_EFFECTS: dict[str, dict[str, float]] = {
        "狭窄": {"mobility": 0.90, "breach": 1.04},
        "开阔": {"mobility": 1.08},
        "险要": {"guard": 1.06, "mobility": 0.94, "sense": 0.97},
        "禁空": {"mobility": 0.88},
        "禁神识": {"sense": 0.86},
        "大阵": {},
    }
    # The existing quick-resolution boundary also defines a truly
    # overwhelming pursuit: at three times the player's active total power,
    # a lethal opponent can seal every route instead of letting the generic
    # post-defeat retreat text grant an effectively free escape.
    OVERWHELMING_RETREAT_RATIO = 1 / 3

    @staticmethod
    def _artifact_effect_active(
        effect: dict[str, Any], *, owner_realm_delta: int,
        natural_terrain: str, artificial_conditions: list[str],
    ) -> bool:
        conditions = list(map(str, effect.get("conditions", [])))
        checks = {
            "enemy_higher": owner_realm_delta < 0,
            "enemy_same_or_lower": owner_realm_delta >= 0,
            "terrain_open": natural_terrain == "开阔",
            "terrain_narrow": natural_terrain == "狭窄",
            "terrain_dangerous": natural_terrain == "险要",
            "artificial_field": bool(artificial_conditions),
        }
        return all(checks.get(condition, False) for condition in conditions)

    @classmethod
    def resolve(
        cls,
        player: Player,
        player_units: list[BattleUnit],
        target: dict[str, Any],
        lethal: bool,
        rng: Any,
        *,
        current_hp_ratio: float,
        current_mp_ratio: float,
        battlefield_tags: Iterable[str] = (),
        mana_cost_multiplier: float = 1.0,
    ) -> CombatResolution:
        objective = cls._objective(target, lethal)
        normalized = [cls.TERRAIN_ALIASES.get(str(tag), str(tag)) for tag in battlefield_tags]
        natural = next((tag for tag in normalized if tag in cls.NATURAL_TERRAINS), "开阔")
        artificial = list(dict.fromkeys(tag for tag in normalized if tag in cls.ARTIFICIAL_CONDITIONS))
        portable_formation = active_formation_profile(player)
        field_formation = target.get("allied_formation_profile", {})
        formation_profile = (
            dict(field_formation)
            if isinstance(field_formation, dict) and field_formation.get("active")
            and not portable_formation.get("active")
            else portable_formation
        )
        enemy_formation_profile = (
            dict(target.get("enemy_formation_profile", {}))
            if isinstance(target.get("enemy_formation_profile"), dict) else {}
        )
        formation_name = str(formation_profile.get("name", "")) if formation_profile.get("active") else None
        enemy_formation_name = (
            str(enemy_formation_profile.get("name", "")) if enemy_formation_profile.get("active") else None
        )
        for condition in formation_profile.get("artificial_conditions", []):
            if condition in cls.ARTIFICIAL_CONDITIONS and condition not in artificial:
                artificial.append(condition)
        for condition in enemy_formation_profile.get("artificial_conditions", []):
            if condition in cls.ARTIFICIAL_CONDITIONS and condition not in artificial:
                artificial.append(condition)
        tags = [natural, *artificial]
        enemy_units = cls._enemy_units(target)
        player_power_max = max(1.0, sum(unit.power for unit in player_units))
        player_power = max(1.0, sum(unit.power * unit.integrity for unit in player_units))
        enemy_power = max(1.0, sum(unit.power for unit in enemy_units))
        ratio = player_power / enemy_power
        assessment = cls._assessment(ratio)
        player_stats = cls._aggregate_stats(player_units, player=player, terrain_tags=tags)
        enemy_stats = cls._aggregate_stats(enemy_units, terrain_tags=tags)
        soul_effects = ghost_soul_effects(player)
        soul_traits = active_soul_traits(player)
        generated_soul_traits = active_generated_soul_traits(player)
        resolve_bonus = max(0.0, float(soul_effects.get("resolve", 0.0)))
        transformation = active_transformation_profile(player)
        for stat, multiplier in transformation["stat_multipliers"].items():
            player_stats[stat] *= multiplier
        transformation_traits = set(transformation["traits"])
        bloodline = active_bloodline_profile(player)
        bloodline_traits = set(bloodline["traits"])
        generated_bloodline_traits = list(bloodline.get("generated_traits", []))
        general_monster_traits = set(active_general_monster_traits(
            player, bloodline_available=bloodline_content_available(),
        ))

        def transformation_trait_name(trait_id: str) -> str:
            return COMBAT_TRAIT_REGISTRY.get(trait_id, {"name": trait_id})["name"]

        def bloodline_active(combat_hook: str) -> bool:
            return bloodline_grants_hook(bloodline_traits, combat_hook)

        def bloodline_name(combat_hook: str) -> str:
            return "与".join(bloodline_hook_names(bloodline_traits, combat_hook)) or combat_hook
        enemy_realm = max(unit.realm_index for unit in enemy_units)
        realm_delta = player.realm_index - enemy_realm
        artifact_effects = [
            effect for effect in target.get("natal_artifact_effects", [])
            if effect.get("generated_rules") or cls._artifact_effect_active(
                effect, owner_realm_delta=realm_delta,
                natural_terrain=natural, artificial_conditions=artificial,
            )
        ]
        enemy_artifact_effects = [
            effect for effect in target.get("enemy_artifact_effects", [])
            if effect.get("generated_rules") or cls._artifact_effect_active(
                effect, owner_realm_delta=-realm_delta,
                natural_terrain=natural, artificial_conditions=artificial,
            )
        ]
        artifact_generated_rules = [
            dict(rule) for effect in artifact_effects
            for rule in effect.get("generated_rules", []) if isinstance(rule, dict)
        ]
        enemy_artifact_generated_rules = [
            dict(rule) for effect in enemy_artifact_effects
            for rule in effect.get("generated_rules", []) if isinstance(rule, dict)
        ]
        artifact_traits: set[str] = set()
        for effect in artifact_effects:
            artifact_traits.update(str(trait) for trait in effect.get("traits", []))
            for stat, multiplier in effect.get("player_stat_multipliers", {}).items():
                if stat in player_stats:
                    player_stats[stat] *= max(0.0, float(multiplier))
            for stat, multiplier in effect.get("enemy_stat_multipliers", {}).items():
                if stat in enemy_stats:
                    enemy_stats[stat] *= max(0.0, float(multiplier))
        for effect in enemy_artifact_effects:
            # The same finite DSL is mirrored from the holder's perspective.
            for stat, multiplier in effect.get("player_stat_multipliers", {}).items():
                if stat in enemy_stats:
                    enemy_stats[stat] *= max(0.0, float(multiplier))
            for stat, multiplier in effect.get("enemy_stat_multipliers", {}).items():
                if stat in player_stats:
                    player_stats[stat] *= max(0.0, float(multiplier))
        if "crafted_sense_ward" in artifact_traits and "禁神识" in artificial:
            # The umbrella mold negates the standard 14% forbidden-sense field
            # penalty; its separate +5% sense multiplier remains meaningful.
            player_stats["sense"] /= float(cls.TERRAIN_EFFECTS["禁神识"]["sense"])

        player_debuffs = [dict(row) for row in target.get("player_debuffs", [])]
        debuffs_blocked = bool(player_debuffs and "player_debuff_immunity" in artifact_traits)
        if not debuffs_blocked:
            for debuff in player_debuffs:
                stat = str(debuff.get("stat", ""))
                if stat in player_stats:
                    multiplier = max(0.0, min(1.0, float(debuff.get("multiplier", 1.0))))
                    resistance = min(0.35, resolve_bonus * 0.8)
                    if "执念" in soul_traits:
                        resistance = min(0.55, resistance + 0.20)
                    player_stats[stat] *= 1.0 - (1.0 - multiplier) * (1.0 - resistance)
        enemy_buffs = []
        for raw_buff in target.get("enemy_buffs", []):
            buff = dict(raw_buff)
            stat = str(buff.get("stat", ""))
            multiplier = max(1.0, float(buff.get("multiplier", 1.0)))
            if stat not in enemy_stats or multiplier <= 1.0:
                continue
            buff.update(stat=stat, multiplier=multiplier)
            enemy_stats[stat] *= multiplier
            enemy_buffs.append(buff)
        _, triggered_general_traits = general_monster_trait_modifiers(
            general_monster_traits, natural_terrain=natural, artificial_conditions=artificial,
        )
        _, triggered_species_traits = bloodline_stat_modifiers(
            bloodline_traits, natural_terrain=natural, artificial_conditions=artificial,
        )
        dragon_pressure_active = "dragon_pressure" in transformation_traits and realm_delta >= 0
        higher_realm_damage_active = "higher_realm_damage_10" in transformation_traits and realm_delta < 0
        ancestral_guard_erosion = bloodline_active("same_or_lower_realm_guard_erosion") and realm_delta >= 0
        realm_pressure_resistance = bloodline_active("realm_pressure_resistance") and realm_delta < 0
        if ancestral_guard_erosion:
            enemy_stats["guard"] *= 0.92
        if bloodline_active("enemy_mobility_erosion"):
            enemy_stats["mobility"] *= 0.92
        gale_feathers_active = bloodline_active("open_terrain_breach_bonus") and natural == "开阔"
        if gale_feathers_active:
            player_stats["breach"] *= 1.10
        faceted_sense_active = bloodline_active("forbidden_sense_resistance") and "禁神识" in artificial
        if faceted_sense_active:
            player_stats["sense"] *= 0.94 / 0.86
        lucid_soul_active = "明识" in soul_traits and "禁神识" in artificial
        if lucid_soul_active:
            player_stats["sense"] *= 0.94 / 0.86
        earthroot_active = bloodline_active("rooted_terrain_guard_bonus") and natural in {"狭窄", "险要"}
        if earthroot_active:
            player_stats["guard"] *= 1.10
        if realm_delta > 0:
            cls._apply_realm_pressure(player_stats, realm_delta)
        elif realm_delta < 0:
            cls._apply_realm_pressure(enemy_stats, max(0, -realm_delta - int(realm_pressure_resistance)))
        cls._apply_objective(player_stats, objective)
        cls._apply_enemy_objective(enemy_stats, str(target.get("enemy_objective", "kill" if lethal else "test")))

        formation_integrity = (
            cls._clamp(0.0, 1.0, float(target.get("formation_initial_integrity", 1.0)))
            if formation_name else 0.0
        )
        enemy_formation_integrity = (
            cls._clamp(0.0, 1.0, float(target.get("enemy_formation_initial_integrity", 1.0)))
            if enemy_formation_name else 0.0
        )
        # Combat power is the battle durability pool. Character HP is only
        # converted from unabsorbed body damage after the fight.
        player_hp = cls._clamp(0.0, 1.0, player_power / player_power_max)
        player_mp = max(0.0, min(1.0, current_mp_ratio))
        mana_cost_multiplier = cls._clamp(0.60, 1.80, float(mana_cost_multiplier))
        enemy_hp = 1.0
        player_morale = 100.0
        enemy_morale = 85.0 if dragon_pressure_active else 100.0
        initial_hp = player_hp
        initial_mp = player_mp
        body_damage_ratio = 0.0
        core_power = max(1.0, next((unit.power for unit in player_units if unit.kind == "player"), player_power))
        rounds: list[dict[str, Any]] = []
        key_events: list[str] = []
        if mana_cost_multiplier >= 1.10:
            key_events.append(f"灵根驭气艰涩：战斗法力消耗为常人的 {mana_cost_multiplier:.0%}。")
        elif mana_cost_multiplier <= 0.90:
            key_events.append(f"灵根驭气精纯：战斗法力消耗降至常人的 {mana_cost_multiplier:.0%}。")
        if transformation["forms"]:
            names = "、".join(
                f"{form.name} {weight:.0%}"
                for form, weight in zip(transformation["forms"], transformation["weights"])
            )
            key_events.append(f"变身预案自动启用：{names}；六项属性按归一化权重融合。")
        if bloodline["id"]:
            key_events.append(f"血脉本相【{bloodline['name']}】生效；六维与固有特质作为本体能力参与结算。")
        if generated_bloodline_traits:
            key_events.append(f"{len(generated_bloodline_traits)}项复合族血规则已接入逐轮战斗结算。")
        if triggered_species_traits:
            names = "、".join(BLOODLINE_TRAIT_REGISTRY[trait_id]["name"] for trait_id in triggered_species_traits)
            key_events.append(f"已觉醒族血【{names}】随本体生效。")
        if triggered_general_traits:
            names = "、".join(GENERAL_MONSTER_TRAIT_REGISTRY[trait_id]["name"] for trait_id in triggered_general_traits)
            key_events.append(f"本体通用特质【{names}】生效；其数值低于 DLC 血脉特质。")
        if artifact_effects:
            names = "、".join(str(effect.get("name", "未知嵌材")) for effect in artifact_effects)
            key_events.append(f"本命法宝嵌材生效：{names}。")
        if enemy_artifact_effects:
            names = "、".join(str(effect.get("name", "未知神机")) for effect in enemy_artifact_effects)
            key_events.append(f"敌方持有的天工神机规则生效：{names}。")
        if debuffs_blocked:
            key_events.append("烛龙之息隔断时序侵蚀，敌方施加的属性削弱未能生效。")
        if dragon_pressure_active:
            pressure_name = transformation_trait_name("dragon_pressure")
            key_events.append(f"{pressure_name}锁定同境界及以下敌手：前两轮必定先手，敌方初始战意削弱 15%。")
        if ancestral_guard_erosion:
            key_events.append(f"{bloodline_name('same_or_lower_realm_guard_erosion')}侵蚀同境及以下敌手，敌方防护降低 8%。")
        if realm_pressure_resistance:
            key_events.append(f"{bloodline_name('realm_pressure_resistance')}生效，敌方境界压制按少一重大境界计算。")
        if bloodline_active("enemy_mobility_erosion"):
            key_events.append(f"{bloodline_name('enemy_mobility_erosion')}封住腾挪空间，敌方身法降低 8%。")
        if gale_feathers_active:
            key_events.append(f"{bloodline_name('open_terrain_breach_bonus')}借开阔天势俯冲，自身破法提高 10%。")
        if faceted_sense_active:
            key_events.append(f"{bloodline_name('forbidden_sense_resistance')}分担识海压力，禁神识惩罚由 14% 降至 6%。")
        if soul_traits:
            key_events.append(f"活跃魂性【{'、'.join(sorted(soul_traits))}】已接入逐轮规则结算。")
        if generated_soul_traits:
            key_events.append(f"{len(generated_soul_traits)}项百鬼夜行复合魂性已接入逐轮规则结算。")
        if lucid_soul_active:
            key_events.append("魂性【明识】守住灵台，禁神识惩罚由 14% 降至 6%。")
        if earthroot_active:
            key_events.append(f"{bloodline_name('rooted_terrain_guard_bonus')}接通地脉，自身防护提高 10%。")
        if realm_delta:
            key_events.append(
                f"{'你方' if realm_delta > 0 else '敌方'}凭大境界优势获得更高的威能上限与控制抗性。"
            )
        global_damage_multiplier = max(0.0, float(target.get("global_damage_multiplier", 1.0)))
        player_damage_multiplier = max(0.0, float(target.get("player_damage_multiplier", 1.0)))
        enemy_damage_multiplier = max(0.0, float(target.get("enemy_damage_multiplier", 1.0)))
        if global_damage_multiplier > 1.0:
            key_events.append("诸圣武神法覆盖战场，双方造成的战斗态势损耗提高 10%。")
        if player_damage_multiplier > 1.0:
            key_events.append("天庭通缉令生效，你方对通缉目标造成的战斗态势损耗提高 10%。")
        if enemy_damage_multiplier > 1.0:
            key_events.append("你正在天庭通缉名单中，敌方对你造成的战斗态势损耗提高 10%。")
        support_updates: dict[str, dict[str, Any]] = {}
        death_prevented = False
        vitality_surge_used = False
        undying_soul_used = False
        devouring_soul_stacks = 0
        counterforce_ready = False
        burst_used = False
        quick = ratio >= 3.0 or ratio <= cls.OVERWHELMING_RETREAT_RATIO
        max_rounds = 1 if quick else max(1, min(8, int(target.get("max_rounds", 5))))
        last_round_player_stats = dict(player_stats)
        last_round_enemy_stats = dict(enemy_stats)

        # Hunting retains its advertised strict preparation threshold, while the
        # exchanges and losses are still resolved through the detailed model.
        forced_outcome: str | None = None
        if target.get("combat_type") == "beast" and target.get("success_threshold") is not None:
            forced_outcome = "victory" if ratio > float(target["success_threshold"]) else "defeat"

        for round_no in range(1, max_rounds + 1):
            events: list[str] = []
            if "enemy_buff_dispel" in artifact_traits and enemy_buffs:
                buff = enemy_buffs.pop(0)
                enemy_stats[buff["stat"]] /= max(1.0, float(buff["multiplier"]))
                dispel_event = f"奢比尸珠扰乱天象，消除了敌方增益“{buff.get('name', STAT_NAMES[buff['stat']])}”。"
                events.append(dispel_event)
                key_events.append(f"第{round_no}轮，{dispel_event}")
            regen_event = ""
            if round_no == 1 and "first_round_full_state" in transformation_traits:
                player_hp = 1.0
            if round_no >= 4 and "round4_regen_10" in transformation_traits:
                before_regen = player_hp
                player_hp = min(1.0, player_hp + 0.10)
                if player_hp > before_regen:
                    regen_name = transformation_trait_name("round4_regen_10")
                    regen_event = f"{regen_name}令己方回复最大战斗态势的 {(player_hp - before_regen):.0%}。"
                    key_events.append(f"第{round_no}轮，{regen_event}")
            round_player_stats = dict(player_stats)
            round_enemy_stats = dict(enemy_stats)
            formation_effect = formation_round_effects(formation_profile, round_no, formation_integrity)
            enemy_formation_effect = formation_round_effects(
                enemy_formation_profile, round_no, enemy_formation_integrity,
            )
            for stat, multiplier in formation_effect["player_stat_multipliers"].items():
                round_player_stats[stat] *= multiplier
            for stat, multiplier in formation_effect["enemy_stat_multipliers"].items():
                round_enemy_stats[stat] *= multiplier
            # The enemy's matrix uses the same owner/opponent channels in the
            # opposite direction. Results are applied once and never fed back
            # into either matrix, preserving V1's non-recursive broadcast cap.
            for stat, multiplier in enemy_formation_effect["player_stat_multipliers"].items():
                round_enemy_stats[stat] *= multiplier
            for stat, multiplier in enemy_formation_effect["enemy_stat_multipliers"].items():
                round_player_stats[stat] *= multiplier
            if formation_effect["change_event"]:
                events.append(f"阵法变势：{formation_effect['change_event']}")
            if enemy_formation_effect["change_event"]:
                events.append(f"敌阵变势：{enemy_formation_effect['change_event']}")
            if devouring_soul_stacks:
                round_enemy_stats["guard"] *= 0.96 ** devouring_soul_stacks
                events.append(f"魂性【噬灵】已侵蚀敌方防护 {devouring_soul_stacks * 4}%。")
            counterforce_active = counterforce_ready
            counterforce_ready = False
            custom_start = evaluate_custom_lineage_rules(
                player, MONSTER_BLOODLINE_SETTINGS.get("custom_lineage", {}),
                phase="round_start", round_no=round_no, natural_terrain=natural,
                artificial_conditions=artificial, player_state=player_hp, enemy_state=enemy_hp,
                player_morale=player_morale, enemy_morale=enemy_morale,
            )
            for stat, multiplier in custom_start["player_stat_multipliers"].items():
                round_player_stats[stat] *= multiplier
            for stat, multiplier in custom_start["enemy_stat_multipliers"].items():
                round_enemy_stats[stat] *= multiplier
            if player_hp > 0:
                player_hp = min(1.0, player_hp + custom_start["player_state_delta"])
            if enemy_hp > 0:
                enemy_hp = min(1.0, enemy_hp + custom_start["enemy_state_delta"])
            player_morale = cls._clamp(0.0, 100.0, player_morale + custom_start["player_morale_delta"])
            enemy_morale = cls._clamp(0.0, 100.0, enemy_morale + custom_start["enemy_morale_delta"])
            events.extend(f"祖血规则【{event}】" for event in custom_start["events"])
            generated_start = evaluate_generated_traits(
                generated_bloodline_traits, trigger="round_start", context={
                    "round_no": round_no, "realm_delta": realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": player_hp, "enemy_state": enemy_hp, "player_mp": player_mp,
                    "player_morale": player_morale, "enemy_morale": enemy_morale,
                },
            )
            for stat, multiplier in generated_start["player_stat_multipliers"].items():
                round_player_stats[stat] *= multiplier
            for stat, multiplier in generated_start["enemy_stat_multipliers"].items():
                round_enemy_stats[stat] *= multiplier
            events.extend(f"族血共鸣【{event}】" for event in generated_start["events"])
            artifact_start = evaluate_generated_traits(
                artifact_generated_rules, trigger="round_start", context={
                    "round_no": round_no, "realm_delta": realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": player_hp, "enemy_state": enemy_hp, "player_mp": player_mp,
                    "player_morale": player_morale, "enemy_morale": enemy_morale,
                },
            )
            enemy_artifact_start = evaluate_generated_traits(
                enemy_artifact_generated_rules, trigger="round_start", context={
                    "round_no": round_no, "realm_delta": -realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": enemy_hp, "enemy_state": player_hp, "player_mp": 1.0,
                    "player_morale": enemy_morale, "enemy_morale": player_morale,
                },
            )
            for stat, multiplier in artifact_start["player_stat_multipliers"].items():
                round_player_stats[stat] *= multiplier
            for stat, multiplier in artifact_start["enemy_stat_multipliers"].items():
                round_enemy_stats[stat] *= multiplier
            for stat, multiplier in enemy_artifact_start["player_stat_multipliers"].items():
                round_enemy_stats[stat] *= multiplier
            for stat, multiplier in enemy_artifact_start["enemy_stat_multipliers"].items():
                round_player_stats[stat] *= multiplier
            events.extend(f"神机共鸣【{event}】" for event in artifact_start["events"])
            events.extend(f"敌方神机共鸣【{event}】" for event in enemy_artifact_start["events"])
            soul_start = evaluate_generated_soul_traits(
                generated_soul_traits, trigger="round_start", context={
                    "round_no": round_no, "realm_delta": realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": player_hp, "enemy_state": enemy_hp, "player_mp": player_mp,
                    "player_morale": player_morale, "enemy_morale": enemy_morale,
                },
            )
            for stat, multiplier in soul_start["player_stat_multipliers"].items():
                round_player_stats[stat] *= multiplier
            for stat, multiplier in soul_start["enemy_stat_multipliers"].items():
                round_enemy_stats[stat] *= multiplier
            events.extend(f"魂性共鸣【{event}】" for event in soul_start["events"])
            sustain_ratio = round_player_stats["sustain"] / max(1.0, player_power)
            sustain_state_factor = 0.90 + 0.10 * cls._clamp(0.50, 1.50, sustain_ratio)
            p_state = (0.42 + 0.40 * player_hp + 0.18 * player_mp) * sustain_state_factor
            e_state = 0.48 + 0.52 * enemy_hp
            p_init = round_player_stats["mobility"] * 0.58 + round_player_stats["sense"] * 0.42
            e_init = round_enemy_stats["mobility"] * 0.58 + round_enemy_stats["sense"] * 0.42
            if target.get("ambush") or target.get("preparation") == "ambushed":
                e_init *= 1.20 if round_no == 1 else 1.0
            if target.get("player_ambush"):
                p_init *= 1.20 if round_no == 1 else 1.0
            if "迅影" in soul_traits and round_no <= 2:
                p_init *= 1.12
            if round_no == 1 and natural == "开阔" and "airborne" in transformation_traits:
                p_init *= 1.08
            player_first = (
                True if dragon_pressure_active and round_no <= 2
                else p_init * cls._wave(rng, 0.96, 1.04) >= e_init
            )
            generated_initiative = evaluate_generated_traits(
                generated_bloodline_traits, trigger="initiative_resolved", context={
                    "round_no": round_no, "realm_delta": realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": player_hp, "enemy_state": enemy_hp, "player_mp": player_mp,
                    "player_morale": player_morale, "enemy_morale": enemy_morale,
                    "player_first": player_first,
                },
            )
            for stat, multiplier in generated_initiative["player_stat_multipliers"].items():
                round_player_stats[stat] *= multiplier
            for stat, multiplier in generated_initiative["enemy_stat_multipliers"].items():
                round_enemy_stats[stat] *= multiplier
            generated_dealt_multiplier = float(generated_initiative["dealt_multiplier"])
            generated_received_multiplier = float(generated_initiative["received_multiplier"])
            events.extend(f"族血共鸣【{event}】" for event in generated_initiative["events"])
            artifact_initiative = evaluate_generated_traits(
                artifact_generated_rules, trigger="initiative_resolved", context={
                    "round_no": round_no, "realm_delta": realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": player_hp, "enemy_state": enemy_hp, "player_mp": player_mp,
                    "player_morale": player_morale, "enemy_morale": enemy_morale,
                    "player_first": player_first,
                },
            )
            enemy_artifact_initiative = evaluate_generated_traits(
                enemy_artifact_generated_rules, trigger="initiative_resolved", context={
                    "round_no": round_no, "realm_delta": -realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": enemy_hp, "enemy_state": player_hp, "player_mp": 1.0,
                    "player_morale": enemy_morale, "enemy_morale": player_morale,
                    "player_first": not player_first,
                },
            )
            for stat, multiplier in artifact_initiative["player_stat_multipliers"].items():
                round_player_stats[stat] *= multiplier
            for stat, multiplier in artifact_initiative["enemy_stat_multipliers"].items():
                round_enemy_stats[stat] *= multiplier
            for stat, multiplier in enemy_artifact_initiative["player_stat_multipliers"].items():
                round_enemy_stats[stat] *= multiplier
            for stat, multiplier in enemy_artifact_initiative["enemy_stat_multipliers"].items():
                round_player_stats[stat] *= multiplier
            artifact_dealt_multiplier = float(artifact_initiative["dealt_multiplier"])
            artifact_received_multiplier = float(artifact_initiative["received_multiplier"])
            enemy_artifact_dealt_multiplier = float(enemy_artifact_initiative["dealt_multiplier"])
            enemy_artifact_received_multiplier = float(enemy_artifact_initiative["received_multiplier"])
            events.extend(f"神机共鸣【{event}】" for event in artifact_initiative["events"])
            events.extend(f"敌方神机共鸣【{event}】" for event in enemy_artifact_initiative["events"])
            soul_initiative = evaluate_generated_soul_traits(
                generated_soul_traits, trigger="initiative_resolved", context={
                    "round_no": round_no, "realm_delta": realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": player_hp, "enemy_state": enemy_hp, "player_mp": player_mp,
                    "player_morale": player_morale, "enemy_morale": enemy_morale,
                    "player_first": player_first,
                },
            )
            for stat, multiplier in soul_initiative["player_stat_multipliers"].items():
                round_player_stats[stat] *= multiplier
            for stat, multiplier in soul_initiative["enemy_stat_multipliers"].items():
                round_enemy_stats[stat] *= multiplier
            soul_dealt_multiplier = float(soul_initiative["dealt_multiplier"])
            soul_received_multiplier = float(soul_initiative["received_multiplier"])
            events.extend(f"魂性共鸣【{event}】" for event in soul_initiative["events"])

            if regen_event:
                events.append(regen_event)
            story_beats = target.get("story_beats", [])
            if round_no <= len(story_beats):
                events.append(f"剧情推进：{story_beats[round_no - 1]}")
            if round_no == 1 and formation_name:
                events.append(f"{formation_name}展开，阵势完整度 {formation_integrity:.0%}。")
            if round_no == 1 and enemy_formation_name:
                events.append(f"敌方{enemy_formation_name}展开，阵势完整度 {enemy_formation_integrity:.0%}。")
            if dragon_pressure_active and round_no <= 2:
                pressure_name = transformation_trait_name("dragon_pressure")
                events.append(f"{pressure_name}镇住敌方气机，本轮由你方强制取得先手。")
            usable_combat_techniques = [
                art for art in player.combat_techniques
                if not art.requires_immortal_power or player.immortal_power_converted
            ]
            burst = bool(
                usable_combat_techniques and player_mp >= 0.28
                and (round_no == 1 and objective == "kill" or enemy_hp <= 0.58 or player_hp <= 0.48)
            )
            burst_factor = 1.0
            if burst:
                burst_used = True
                art = max(usable_combat_techniques, key=lambda entry: entry.combat_bonus)
                burst_factor = 1.18
                cost = min(
                    player_mp,
                    max(0.07 + 0.008 * max(1, art.grade), art.immortal_power_cost if art.requires_immortal_power else 0)
                    * mana_cost_multiplier,
                )
                player_mp -= cost
                label = f"《{art.name}》"
                resource = "仙灵力" if art.requires_immortal_power else "法力"
                events.append(f"预案自动发动{label}，以 {cost:.0%} 最大{resource}换取本轮爆发。")

            player_round_might = 1.0
            enemy_round_might = 1.0
            if counterforce_active:
                player_round_might *= 1.12
                events.append(f"{bloodline_name('damage_taken_counterforce')}释放上轮积蓄的反震力，本轮威能提高 12%。")
            if player_first and bloodline_active("initiative_enemy_might_suppression"):
                enemy_round_might *= 0.92
                events.append(f"{bloodline_name('initiative_enemy_might_suppression')}扰乱敌方攻势，本轮敌方威能降低 8%。")
            if not player_first and bloodline_active("lost_initiative_guard_bonus"):
                round_player_stats["guard"] *= 1.12
                events.append(f"{bloodline_name('lost_initiative_guard_bonus')}预判敌方来势，本轮防护提高 12%。")
            if not player_first and "寒魄" in soul_traits:
                round_player_stats["guard"] *= 1.12
                events.append("魂性【寒魄】凝结护体，本轮防护提高 12%。")
            if round_no % 2 == 0 and "even_round_might_40" in artifact_traits:
                player_round_might *= 1.40
                events.append("强良之雷应合偶数轮天机，本轮己方威能提高 40%。")
            if round_no % 2 == 1 and "odd_round_enemy_might_down_40" in artifact_traits:
                enemy_round_might *= 0.60
                events.append("翕兹之电截断奇数轮气机，本轮敌方威能降低 40%。")
            p_attack = round_player_stats["might"] * player_round_might * p_state * burst_factor
            p_defense = round_player_stats["guard"] * (0.72 + 0.28 * player_hp)
            e_attack = round_enemy_stats["might"] * enemy_round_might * e_state
            e_defense = round_enemy_stats["guard"] * (0.72 + 0.28 * enemy_hp)
            p_breach = round_player_stats["breach"] / max(1.0, round_enemy_stats["guard"])
            e_breach = round_enemy_stats["breach"] / max(1.0, round_player_stats["guard"])
            control_chance = cls._clamp(
                0.10, 0.90,
                0.46 * round_player_stats["sense"] / max(1.0, round_enemy_stats["sense"])
                + (player.realm_index - max(unit.realm_index for unit in enemy_units)) * 0.04,
            )
            controlled = cls._roll(rng) < control_chance
            if controlled:
                e_attack *= 0.86
                events.append("神识压制奏效，敌方攻势出现短暂迟滞。")
                if bloodline_active("control_morale_shock"):
                    enemy_morale = max(0.0, enemy_morale - 4.0)
                    events.append(f"{bloodline_name('control_morale_shock')}随神识侵入梦境，敌方战意额外降低 4 点。")

            dealt = cls._clamp(
                0.045, 0.42,
                0.135 * (p_attack / max(1.0, e_defense)) ** 0.58
                * (0.88 + min(0.28, p_breach * 0.13)) * cls._wave(rng, 0.90, 1.10),
            )
            received = cls._clamp(
                0.035, 0.40,
                0.125 * (e_attack / max(1.0, p_defense)) ** 0.58
                * (0.88 + min(0.28, e_breach * 0.13)) * cls._wave(rng, 0.90, 1.10),
            )
            dealt *= global_damage_multiplier * player_damage_multiplier
            received *= global_damage_multiplier * enemy_damage_multiplier
            if player_first:
                dealt *= 1.05
                received *= 0.96
            else:
                dealt *= 0.97
                received *= 1.04
            if "damage_bonus_5" in transformation_traits:
                dealt *= 1.05
            if higher_realm_damage_active:
                dealt *= 1.10
            if enemy_hp <= 0.35 and bloodline_active("wounded_target_execution"):
                dealt *= 1.18
                events.append(f"{bloodline_name('wounded_target_execution')}锁定伤势，本轮伤害提高 18%。")
            if enemy_hp <= 0.35 and "凶魂" in soul_traits:
                dealt *= 1.15
                events.append("魂性【凶魂】追逐败势，本轮造成的损耗提高 15%。")

            if player_hp <= 0.40 and bloodline_active("low_state_damage_reduction"):
                received *= 0.88
                events.append(f"{bloodline_name('low_state_damage_reduction')}护住生机，本轮受到的伤害降低 12%。")

            if bloodline_active("per_round_damage_cap") and received > 0.24:
                received = 0.24
                events.append(f"{bloodline_name('per_round_damage_cap')}分散冲击，本轮态势损失被限制为 24%。")

            generated_before_damage = evaluate_generated_traits(
                generated_bloodline_traits, trigger="before_damage", context={
                    "round_no": round_no, "realm_delta": realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": player_hp, "enemy_state": enemy_hp, "player_mp": player_mp,
                    "player_morale": player_morale, "enemy_morale": enemy_morale,
                    "player_first": player_first, "controlled": controlled,
                },
            )
            dealt *= generated_dealt_multiplier * float(generated_before_damage["dealt_multiplier"])
            received *= generated_received_multiplier * float(generated_before_damage["received_multiplier"])
            if generated_before_damage["received_cap"] is not None:
                received = min(received, float(generated_before_damage["received_cap"]))
            events.extend(f"族血共鸣【{event}】" for event in generated_before_damage["events"])
            artifact_before_damage = evaluate_generated_traits(
                artifact_generated_rules, trigger="before_damage", context={
                    "round_no": round_no, "realm_delta": realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": player_hp, "enemy_state": enemy_hp, "player_mp": player_mp,
                    "player_morale": player_morale, "enemy_morale": enemy_morale,
                    "player_first": player_first, "controlled": controlled,
                },
            )
            enemy_artifact_before_damage = evaluate_generated_traits(
                enemy_artifact_generated_rules, trigger="before_damage", context={
                    "round_no": round_no, "realm_delta": -realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": enemy_hp, "enemy_state": player_hp, "player_mp": 1.0,
                    "player_morale": enemy_morale, "enemy_morale": player_morale,
                    "player_first": not player_first, "controlled": False,
                },
            )
            dealt *= (
                artifact_dealt_multiplier * float(artifact_before_damage["dealt_multiplier"])
                * enemy_artifact_received_multiplier
                * float(enemy_artifact_before_damage["received_multiplier"])
            )
            received *= (
                artifact_received_multiplier * float(artifact_before_damage["received_multiplier"])
                * enemy_artifact_dealt_multiplier
                * float(enemy_artifact_before_damage["dealt_multiplier"])
            )
            if artifact_before_damage["received_cap"] is not None:
                received = min(received, float(artifact_before_damage["received_cap"]))
            if enemy_artifact_before_damage["received_cap"] is not None:
                dealt = min(dealt, float(enemy_artifact_before_damage["received_cap"]))
            events.extend(f"神机共鸣【{event}】" for event in artifact_before_damage["events"])
            events.extend(f"敌方神机共鸣【{event}】" for event in enemy_artifact_before_damage["events"])
            soul_before_damage = evaluate_generated_soul_traits(
                generated_soul_traits, trigger="before_damage", context={
                    "round_no": round_no, "realm_delta": realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": player_hp, "enemy_state": enemy_hp, "player_mp": player_mp,
                    "player_morale": player_morale, "enemy_morale": enemy_morale,
                    "player_first": player_first, "controlled": controlled,
                },
            )
            dealt *= soul_dealt_multiplier * float(soul_before_damage["dealt_multiplier"])
            received *= soul_received_multiplier * float(soul_before_damage["received_multiplier"])
            dealt *= float(formation_effect["dealt_multiplier"])
            received *= float(enemy_formation_effect["dealt_multiplier"])
            events.extend(f"魂性共鸣【{event}】" for event in soul_before_damage["events"])

            if round_no == 1 and "first_round_full_state" in transformation_traits:
                received = 0.0
                guard_name = transformation_trait_name("first_round_full_state")
                events.append(f"{guard_name}生效：第一轮己方战斗态势锁定为最大值。")

            received_amount = received * player_power_max
            absorbed_amount, guard_event = cls._absorb_with_support(
                player_units, received_amount, support_updates,
            )
            if guard_event:
                events.append(guard_event)
                key_events.append(f"第{round_no}轮，{guard_event}")
            body_received_amount = max(0.0, received_amount - absorbed_amount)
            body_damage_ratio += body_received_amount / core_power * 0.46
            actual_received = 0.0 if round_no == 1 and "first_round_full_state" in transformation_traits else max(0.012, received)
            enemy_hp = max(0.0, enemy_hp - dealt)
            player_hp = max(0.0, player_hp - actual_received)
            if "噬灵" in soul_traits and dealt > 0 and devouring_soul_stacks < 3:
                devouring_soul_stacks += 1
            if actual_received >= 0.12 and bloodline_active("damage_taken_counterforce"):
                counterforce_ready = True
            base_cost = 0.025 + 0.025 * min(1.6, round_player_stats["might"] / max(1.0, player_power))
            player_mp = max(0.0, player_mp - min(0.12, base_cost * mana_cost_multiplier))
            if round_no % 2 == 0 and bloodline_active("even_round_mana_recovery"):
                restored_mp = min(0.03, 1.0 - player_mp)
                player_mp += restored_mp
                if restored_mp > 0:
                    events.append(f"{bloodline_name('even_round_mana_recovery')}应合潮汐，恢复 {restored_mp:.0%} 最大法力。")
            if natural == "开阔" and bloodline_active("open_terrain_mana_recovery"):
                restored_mp = min(0.02, 1.0 - player_mp)
                player_mp += restored_mp
                if restored_mp > 0:
                    events.append(f"{bloodline_name('open_terrain_mana_recovery')}借天地回气，恢复 {restored_mp:.0%} 最大法力。")
            if (
                not vitality_surge_used and 0 < player_hp <= 0.25
                and bloodline_active("wounded_vitality_surge")
            ):
                vitality_surge_used = True
                restored_hp = min(0.08, 1.0 - player_hp)
                restored_mp = min(0.06, 1.0 - player_mp)
                player_hp += restored_hp
                player_mp += restored_mp
                event = (
                    f"{bloodline_name('wounded_vitality_surge')}被重伤唤醒，恢复 "
                    f"{restored_hp:.0%} 态势与 {restored_mp:.0%} 法力；该能力不能挽回致命溃败。"
                )
                events.append(event)
                key_events.append(f"第{round_no}轮，{event}")
            if player_hp > 0 and bloodline_active("received_damage_reclamation"):
                reclaimed = min(0.04, actual_received * 0.20, 1.0 - player_hp)
                player_hp += reclaimed
                if reclaimed > 0:
                    events.append(f"{bloodline_name('received_damage_reclamation')}回收伤势，恢复 {reclaimed:.1%} 最大战斗态势。")
            sustain_restore = min(0.02, max(0.0, sustain_ratio - 1.0) * 0.04)
            if player_hp > 0 and sustain_restore > 0:
                restored_state = min(sustain_restore, 1.0 - player_hp)
                restored_mp = min(sustain_restore * 0.5, 1.0 - player_mp)
                player_hp += restored_state
                player_mp += restored_mp
                if restored_state > 0 or restored_mp > 0:
                    events.append(f"续航体系回稳，恢复 {restored_state:.1%} 战斗态势与 {restored_mp:.1%} 法力。")
            if player_hp > 0 and formation_effect["state_restore"] > 0:
                restored_state = min(float(formation_effect["state_restore"]), 1.0 - player_hp)
                restored_mp = min(float(formation_effect["mp_restore"]), 1.0 - player_mp)
                player_hp += restored_state
                player_mp += restored_mp
                if restored_state > 0 or restored_mp > 0:
                    events.append(f"阵中生流回返，恢复 {restored_state:.1%} 战斗态势与 {restored_mp:.1%} 法力。")
            if enemy_hp > 0 and enemy_formation_effect["state_restore"] > 0:
                restored_enemy = min(float(enemy_formation_effect["state_restore"]), 1.0 - enemy_hp)
                enemy_hp += restored_enemy
                if restored_enemy > 0:
                    events.append(f"敌阵生流回返，恢复敌方 {restored_enemy:.1%} 战斗态势。")
            if not undying_soul_used and 0 < player_hp <= 0.25 and "不灭" in soul_traits:
                undying_soul_used = True
                restored_state = min(0.08, 1.0 - player_hp)
                restored_mp = min(0.05, 1.0 - player_mp)
                player_hp += restored_state
                player_mp += restored_mp
                event = f"魂性【不灭】燃起残火，恢复 {restored_state:.0%} 战斗态势与 {restored_mp:.0%} 法力。"
                events.append(event)
                key_events.append(f"第{round_no}轮，{event}")
            morale_scale = 1.28 if objective == "repel" else 1.0
            enemy_morale = max(0.0, enemy_morale - dealt * 77 * morale_scale)
            if formation_effect["enemy_morale_loss"] > 0:
                enemy_morale = max(0.0, enemy_morale - float(formation_effect["enemy_morale_loss"]))
                events.append(f"杀势压阵，敌方额外损失 {formation_effect['enemy_morale_loss']:.1f} 点战意。")
            if "morale_drain_5" in transformation_traits:
                enemy_morale = max(0.0, enemy_morale - 5.0)
                morale_name = transformation_trait_name("morale_drain_5")
                events.append(f"{morale_name}侵蚀敌阵，本轮额外削弱敌方 5 点战意。")
            morale_loss = actual_received * 70 / (1.0 + resolve_bonus)
            morale_loss *= float(formation_effect["player_morale_loss_multiplier"])
            morale_loss += float(enemy_formation_effect["enemy_morale_loss"])
            enemy_morale_loss_multiplier = float(enemy_formation_effect["player_morale_loss_multiplier"])
            enemy_morale = min(100.0, enemy_morale + dealt * 77 * morale_scale * (1.0 - enemy_morale_loss_multiplier))
            if "执念" in soul_traits:
                morale_loss *= 0.75
            player_morale = max(0.0, player_morale - morale_loss)
            if "steadfast" in transformation_traits:
                player_morale = max(8.0, player_morale)
            if "执念" in soul_traits:
                player_morale = max(8.0, player_morale)
            generated_after_damage = evaluate_generated_traits(
                generated_bloodline_traits, trigger="after_damage", context={
                    "round_no": round_no, "realm_delta": realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": player_hp, "enemy_state": enemy_hp, "player_mp": player_mp,
                    "player_morale": player_morale, "enemy_morale": enemy_morale,
                    "player_first": player_first, "controlled": controlled,
                    "received": actual_received, "dealt": dealt,
                },
            )
            if player_hp > 0:
                player_hp = min(1.0, player_hp + generated_after_damage["player_state_restore"])
            player_mp = min(1.0, player_mp + generated_after_damage["player_mp_restore"])
            player_morale = cls._clamp(0.0, 100.0, player_morale + generated_after_damage["player_morale_delta"])
            enemy_morale = cls._clamp(0.0, 100.0, enemy_morale + generated_after_damage["enemy_morale_delta"])
            events.extend(f"族血共鸣【{event}】" for event in generated_after_damage["events"])
            artifact_after_damage = evaluate_generated_traits(
                artifact_generated_rules, trigger="after_damage", context={
                    "round_no": round_no, "realm_delta": realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": player_hp, "enemy_state": enemy_hp, "player_mp": player_mp,
                    "player_morale": player_morale, "enemy_morale": enemy_morale,
                    "player_first": player_first, "controlled": controlled,
                    "received": actual_received, "dealt": dealt,
                },
            )
            enemy_artifact_after_damage = evaluate_generated_traits(
                enemy_artifact_generated_rules, trigger="after_damage", context={
                    "round_no": round_no, "realm_delta": -realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": enemy_hp, "enemy_state": player_hp, "player_mp": 1.0,
                    "player_morale": enemy_morale, "enemy_morale": player_morale,
                    "player_first": not player_first, "controlled": False,
                    "received": dealt, "dealt": actual_received,
                },
            )
            if player_hp > 0:
                player_hp = min(1.0, player_hp + artifact_after_damage["player_state_restore"])
            if enemy_hp > 0:
                enemy_hp = min(1.0, enemy_hp + enemy_artifact_after_damage["player_state_restore"])
            player_mp = min(1.0, player_mp + artifact_after_damage["player_mp_restore"])
            player_morale = cls._clamp(
                0.0, 100.0, player_morale + artifact_after_damage["player_morale_delta"]
                + enemy_artifact_after_damage["enemy_morale_delta"],
            )
            enemy_morale = cls._clamp(
                0.0, 100.0, enemy_morale + artifact_after_damage["enemy_morale_delta"]
                + enemy_artifact_after_damage["player_morale_delta"],
            )
            events.extend(f"神机共鸣【{event}】" for event in artifact_after_damage["events"])
            events.extend(f"敌方神机共鸣【{event}】" for event in enemy_artifact_after_damage["events"])
            soul_after_damage = evaluate_generated_soul_traits(
                generated_soul_traits, trigger="after_damage", context={
                    "round_no": round_no, "realm_delta": realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": player_hp, "enemy_state": enemy_hp, "player_mp": player_mp,
                    "player_morale": player_morale, "enemy_morale": enemy_morale,
                    "player_first": player_first, "controlled": controlled,
                    "received": actual_received, "dealt": dealt,
                },
            )
            if player_hp > 0:
                player_hp = min(1.0, player_hp + soul_after_damage["player_state_restore"])
            player_mp = min(1.0, player_mp + soul_after_damage["player_mp_restore"])
            player_morale = cls._clamp(0.0, 100.0, player_morale + soul_after_damage["player_morale_delta"])
            enemy_morale = cls._clamp(0.0, 100.0, enemy_morale + soul_after_damage["enemy_morale_delta"])
            events.extend(f"魂性共鸣【{event}】" for event in soul_after_damage["events"])
            if player_hp <= 0 and "prevent_defeat_once" in transformation_traits and not death_prevented:
                death_prevented = True
                player_hp = 0.12
                player_morale = max(12.0, player_morale)
                revival_name = transformation_trait_name("prevent_defeat_once")
                event = f"{revival_name}在战斗态势归零时自行复苏，抵御了本场一次陨落。"
                events.append(event)
                key_events.append(f"第{round_no}轮，{event}")

            custom_end = evaluate_custom_lineage_rules(
                player, MONSTER_BLOODLINE_SETTINGS.get("custom_lineage", {}),
                phase="round_end", round_no=round_no, natural_terrain=natural,
                artificial_conditions=artificial, player_state=player_hp, enemy_state=enemy_hp,
                player_morale=player_morale, enemy_morale=enemy_morale,
            )
            if player_hp > 0:
                player_hp = min(1.0, player_hp + custom_end["player_state_delta"])
            if enemy_hp > 0:
                enemy_hp = min(1.0, enemy_hp + custom_end["enemy_state_delta"])
            player_morale = cls._clamp(0.0, 100.0, player_morale + custom_end["player_morale_delta"])
            enemy_morale = cls._clamp(0.0, 100.0, enemy_morale + custom_end["enemy_morale_delta"])
            events.extend(f"祖血规则【{event}】" for event in custom_end["events"])
            generated_end = evaluate_generated_traits(
                generated_bloodline_traits, trigger="round_end", context={
                    "round_no": round_no, "realm_delta": realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": player_hp, "enemy_state": enemy_hp, "player_mp": player_mp,
                    "player_morale": player_morale, "enemy_morale": enemy_morale,
                    "player_first": player_first, "controlled": controlled,
                    "received": actual_received, "dealt": dealt,
                },
            )
            if player_hp > 0:
                player_hp = min(1.0, player_hp + generated_end["player_state_restore"])
            player_mp = min(1.0, player_mp + generated_end["player_mp_restore"])
            player_morale = cls._clamp(0.0, 100.0, player_morale + generated_end["player_morale_delta"])
            enemy_morale = cls._clamp(0.0, 100.0, enemy_morale + generated_end["enemy_morale_delta"])
            events.extend(f"族血共鸣【{event}】" for event in generated_end["events"])
            artifact_end = evaluate_generated_traits(
                artifact_generated_rules, trigger="round_end", context={
                    "round_no": round_no, "realm_delta": realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": player_hp, "enemy_state": enemy_hp, "player_mp": player_mp,
                    "player_morale": player_morale, "enemy_morale": enemy_morale,
                    "player_first": player_first, "controlled": controlled,
                    "received": actual_received, "dealt": dealt,
                },
            )
            enemy_artifact_end = evaluate_generated_traits(
                enemy_artifact_generated_rules, trigger="round_end", context={
                    "round_no": round_no, "realm_delta": -realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": enemy_hp, "enemy_state": player_hp, "player_mp": 1.0,
                    "player_morale": enemy_morale, "enemy_morale": player_morale,
                    "player_first": not player_first, "controlled": False,
                    "received": dealt, "dealt": actual_received,
                },
            )
            if player_hp > 0:
                player_hp = min(1.0, player_hp + artifact_end["player_state_restore"])
            if enemy_hp > 0:
                enemy_hp = min(1.0, enemy_hp + enemy_artifact_end["player_state_restore"])
            player_mp = min(1.0, player_mp + artifact_end["player_mp_restore"])
            player_morale = cls._clamp(
                0.0, 100.0, player_morale + artifact_end["player_morale_delta"]
                + enemy_artifact_end["enemy_morale_delta"],
            )
            enemy_morale = cls._clamp(
                0.0, 100.0, enemy_morale + artifact_end["enemy_morale_delta"]
                + enemy_artifact_end["player_morale_delta"],
            )
            events.extend(f"神机共鸣【{event}】" for event in artifact_end["events"])
            events.extend(f"敌方神机共鸣【{event}】" for event in enemy_artifact_end["events"])
            soul_end = evaluate_generated_soul_traits(
                generated_soul_traits, trigger="round_end", context={
                    "round_no": round_no, "realm_delta": realm_delta,
                    "natural_terrain": natural, "artificial_conditions": artificial,
                    "player_state": player_hp, "enemy_state": enemy_hp, "player_mp": player_mp,
                    "player_morale": player_morale, "enemy_morale": enemy_morale,
                    "player_first": player_first, "controlled": controlled,
                    "received": actual_received, "dealt": dealt,
                },
            )
            if player_hp > 0:
                player_hp = min(1.0, player_hp + soul_end["player_state_restore"])
            player_mp = min(1.0, player_mp + soul_end["player_mp_restore"])
            player_morale = cls._clamp(0.0, 100.0, player_morale + soul_end["player_morale_delta"])
            enemy_morale = cls._clamp(0.0, 100.0, enemy_morale + soul_end["enemy_morale_delta"])
            events.extend(f"魂性共鸣【{event}】" for event in soul_end["events"])

            if formation_name and formation_integrity > 0:
                before_integrity = formation_integrity
                formation_integrity = max(
                    0.0,
                    formation_integrity
                    - actual_received * 0.34 * float(formation_effect["integrity_decay_multiplier"])
                    - float(formation_effect["integrity_extra_loss"]),
                )
                if formation_integrity > 0 and formation_effect["integrity_restore"] > 0:
                    formation_integrity = min(
                        1.0, formation_integrity + float(formation_effect["integrity_restore"]),
                    )
                if abs(formation_integrity - before_integrity) >= 0.005:
                    events.append(f"阵势完整度结算为 {formation_integrity:.0%}。")
                if formation_integrity < 0.50 and not any("阵势跌破" in event for row in rounds for event in row["events"]):
                    events.append("阵势完整度跌破 50%，预案收缩阵线维持核心加成。")
                    key_events.append(f"第{round_no}轮，{formation_name}受创后自动收缩阵线。")
            if enemy_formation_name and enemy_formation_integrity > 0:
                before_enemy_integrity = enemy_formation_integrity
                enemy_formation_integrity = max(
                    0.0,
                    enemy_formation_integrity
                    - dealt * 0.34 * float(enemy_formation_effect["integrity_decay_multiplier"])
                    - float(enemy_formation_effect["integrity_extra_loss"]),
                )
                if enemy_formation_integrity > 0 and enemy_formation_effect["integrity_restore"] > 0:
                    enemy_formation_integrity = min(
                        1.0, enemy_formation_integrity + float(enemy_formation_effect["integrity_restore"]),
                    )
                if abs(enemy_formation_integrity - before_enemy_integrity) >= 0.005:
                    events.append(f"敌阵完整度结算为 {enemy_formation_integrity:.0%}。")

            events.append(
                f"{'你方' if player_first else '敌方'}抢得先手；你方削去敌方 {dealt * enemy_power:.0f} 战斗态势，承受 {actual_received * player_power_max:.0f} 战斗态势损耗。"
            )
            last_round_player_stats = dict(round_player_stats)
            last_round_enemy_stats = dict(round_enemy_stats)
            rounds.append({
                "round": round_no,
                "initiative": "player" if player_first else "enemy",
                "events": events,
                "player_hp_ratio": round(player_hp, 4),
                "player_mp_ratio": round(player_mp, 4),
                "enemy_hp_ratio": round(enemy_hp, 4),
                "player_combat_state": round(player_power_max * player_hp, 1),
                "player_combat_state_max": round(player_power_max, 1),
                "enemy_combat_state": round(enemy_power * enemy_hp, 1),
                "enemy_combat_state_max": round(enemy_power, 1),
                "player_morale": round(player_morale, 1),
                "enemy_morale": round(enemy_morale, 1),
                "formation_integrity": round(formation_integrity, 4) if formation_name else None,
                "enemy_formation_integrity": (
                    round(enemy_formation_integrity, 4) if enemy_formation_name else None
                ),
            })
            if enemy_hp <= 0.12 or enemy_morale <= 8 or player_hp <= 0 or player_morale <= 5:
                break

        if quick and ratio >= 3.0:
            enemy_hp = min(enemy_hp, 0.08)
            enemy_morale = min(enemy_morale, 5.0)
            if rounds:
                rounds[-1]["enemy_hp_ratio"] = round(enemy_hp, 4)
                rounds[-1]["enemy_combat_state"] = round(enemy_power * enemy_hp, 1)
                rounds[-1]["enemy_morale"] = round(enemy_morale, 1)
        elif quick and ratio <= cls.OVERWHELMING_RETREAT_RATIO:
            player_morale = min(player_morale, 5.0)
            if lethal:
                if "prevent_defeat_once" in transformation_traits and not death_prevented:
                    death_prevented = True
                    player_hp = max(0.12, player_hp)
                    revival_name = transformation_trait_name("prevent_defeat_once")
                    key_events.append(
                        f"敌方封死全部退路后，{revival_name}替你承受了必死一击；这不是逃脱成功。"
                    )
                else:
                    player_hp = 0.0
            if rounds:
                rounds[-1]["player_hp_ratio"] = round(player_hp, 4)
                rounds[-1]["player_combat_state"] = round(player_power_max * player_hp, 1)
                rounds[-1]["player_morale"] = round(player_morale, 1)

        if forced_outcome:
            outcome = forced_outcome
        elif enemy_hp <= 0.12 or enemy_morale <= 8:
            outcome = "victory"
        elif player_hp <= 0 or player_morale <= 5:
            outcome = "defeat"
        else:
            player_score = (1 - enemy_hp) * 0.62 + player_hp * 0.25 + player_morale / 100 * 0.13
            enemy_score = (1 - player_hp) * 0.62 + enemy_hp * 0.25 + enemy_morale / 100 * 0.13
            margin = player_score - enemy_score
            if abs(margin) <= 0.035:
                outcome = "victory" if cls._roll(rng) < 0.50 else "defeat"
            else:
                outcome = "victory" if margin > 0 else "defeat"

        retreat_impossible = bool(
            lethal and outcome == "defeat"
            and ratio <= cls.OVERWHELMING_RETREAT_RATIO
        )
        if quick:
            key_events.insert(0, "双方综合差距超过三倍，预案自动采用快速结算。")
        if retreat_impossible:
            key_events.insert(
                1 if quick else 0,
                "敌方总战力达到你方三倍，已封死所有退路；逃脱预案必定失败。",
            )
        if burst_used and rounds:
            key_events.append(f"第{rounds[-1]['round']}轮前，战斗预案自动调度了高消耗术式。")
        if outcome == "victory":
            key_events.append("敌方战斗状态或战意跌破临界点，你方取得战场控制权。")
        else:
            key_events.append("预案判断继续纠缠的代价过高，自动转入脱离与保命流程。")

        speed_edge = last_round_player_stats["mobility"] / max(1.0, last_round_enemy_stats["mobility"])
        sense_edge = last_round_player_stats["sense"] / max(1.0, last_round_enemy_stats["sense"])
        decisive = ratio > 1.12 and (enemy_hp <= 0.46 or enemy_morale <= 22)
        pursuit = speed_edge * 0.55 + sense_edge * 0.30 + max(0, player.realm_index - enemy_realm) * 0.08
        escape_locked = "enemy_escape_lock" in artifact_traits
        kill_pursuit_threshold = cls._clamp(
            0.0, 2.0, float(target.get("kill_pursuit_threshold", 0.82)),
        )
        kill_ready = bool(
            outcome == "victory" and lethal
            and (escape_locked or (decisive and pursuit >= kill_pursuit_threshold))
        )
        capture_ready = bool(
            outcome == "victory" and objective == "capture" and (enemy_hp <= 0.58 or enemy_morale <= 25)
            and (
                escape_locked or sense_edge >= 0.90 or speed_edge >= 1.0
                or player.realm_index > enemy_realm
            )
        )
        if escape_locked and outcome == "victory":
            key_events.append("帝江之泪封闭空间退路，敌方无法从败势中遁逃。")
        if outcome == "victory":
            losses = max(0.0, initial_hp - player_hp)
            grade = "完胜" if losses < 0.08 else "胜利" if losses < 0.24 else "惨胜"
        elif retreat_impossible and death_prevented:
            grade = "涅槃生还"
        elif retreat_impossible:
            grade = "溃败"
        elif player_hp > 0.35:
            grade = "有序撤退"
        else:
            grade = "战败"

        return CombatResolution(
            outcome=outcome,
            result_grade=grade,
            objective=objective,
            mode="快速结算" if quick else "标准自动战斗",
            rounds=rounds,
            key_events=key_events[:4],
            hp_loss_ratio=round(cls._clamp(0.0, 0.68, body_damage_ratio), 4),
            mp_loss_ratio=round(max(0.0, initial_mp - player_mp), 4),
            player_combat_state=round(player_power_max * player_hp, 1),
            player_combat_state_max=round(player_power_max, 1),
            enemy_combat_state=round(enemy_power * enemy_hp, 1),
            enemy_combat_state_max=round(enemy_power, 1),
            enemy_hp_ratio=round(enemy_hp, 4),
            player_morale=round(player_morale, 1),
            enemy_morale=round(enemy_morale, 1),
            kill_ready=kill_ready,
            capture_ready=capture_ready,
            support_updates=list(support_updates.values()),
            assessment=assessment,
            battlefield_tags=tags,
            natural_terrain=natural,
            artificial_conditions=artificial,
            player_stats={key: round(value, 1) for key, value in last_round_player_stats.items()},
            enemy_stats={key: round(value, 1) for key, value in last_round_enemy_stats.items()},
            active_transformations=[
                {"id": form.id, "name": form.name, "weight": round(weight, 6)}
                for form, weight in zip(transformation["forms"], transformation["weights"])
            ],
            transformation_traits=list(transformation_traits),
            bloodline_traits=[*bloodline_traits, *(str(rule["id"]) for rule in generated_bloodline_traits)],
            general_monster_traits=list(general_monster_traits),
            death_prevented=death_prevented,
            retreat_impossible=retreat_impossible,
            player_roster=cls._public_roster(player_units),
            enemy_roster=cls._public_roster(enemy_units),
            formation_profile=(
                {
                    "name": formation_profile["name"], "metrics": dict(formation_profile.get("metrics", {})),
                    "change_mode": formation_profile.get("change_mode"),
                    "change_mode_name": formation_profile.get("change_mode_name"),
                    "core_node": formation_profile.get("core_node"),
                }
                if formation_profile.get("active") else None
            ),
            enemy_formation_profile=(
                {
                    "name": enemy_formation_profile["name"],
                    "metrics": dict(enemy_formation_profile.get("metrics", {})),
                    "change_mode": enemy_formation_profile.get("change_mode"),
                    "change_mode_name": enemy_formation_profile.get("change_mode_name"),
                    "core_node": enemy_formation_profile.get("core_node"),
                }
                if enemy_formation_profile.get("active") else None
            ),
            formation_integrity_end=(round(formation_integrity, 4) if formation_name else None),
            enemy_formation_integrity_end=(
                round(enemy_formation_integrity, 4) if enemy_formation_name else None
            ),
        )

    @staticmethod
    def _public_roster(units: list[BattleUnit]) -> list[dict[str, Any]]:
        kind_names = {
            "player": "玩家", "mechanical": "傀儡", "corpse": "炼尸",
            "living": "活傀", "companion": "同行者", "story_ally": "剧情盟友",
            "cultivator": "修士", "beast": "妖兽", "artifact": "器物",
            "formation": "阵势", "environment": "战场威胁",
        }
        result: list[dict[str, Any]] = []
        for unit in units:
            full_power = max(unit.power, float(unit.full_power or unit.power))
            result.append({
                "id": unit.id,
                "name": unit.name,
                "kind": unit.kind,
                "kind_name": kind_names.get(unit.kind, "战斗单位"),
                # ``power`` remains the public, intrinsic combat rating. The
                # smaller engaged value only describes how much of a scripted
                # NPC's attention is committed to the player's current front.
                "power": round(full_power, 1),
                "engaged_power": round(unit.power, 1),
                "commitment": round(min(1.0, unit.power / max(1.0, full_power)), 4),
                "integrity": round(unit.integrity, 4),
            })
        return result

    @classmethod
    def _enemy_units(cls, target: dict[str, Any]) -> list[BattleUnit]:
        raw = target.get("members") or [{
            "name": target.get("target_name", "未知对手"),
            "power": target.get("target_power", 1),
            "realm_index": target.get("target_realm_index", 0),
            "path": target.get("path", "monster" if target.get("combat_type") == "beast" else "dao"),
        }]
        total_raw = max(1.0, sum(max(0.0, float(row.get("power", 0))) for row in raw))
        displayed = max(1.0, float(target.get("target_power", total_raw)))
        scale = displayed / total_raw
        return [BattleUnit(
            id=str(row.get("npc_id") or f"enemy-{index}"),
            name=str(row.get("name", target.get("target_name", "未知对手"))),
            kind=str(row.get("kind", "beast" if target.get("combat_type") == "beast" else "cultivator")),
            power=max(1.0, float(row.get("power", 1)) * scale),
            realm_index=int(row.get("realm_index", target.get("target_realm_index", 0))),
            path=str(row.get("path", "monster" if target.get("combat_type") == "beast" else "dao")),
            full_power=float(row["full_power"]) if row.get("full_power") is not None else None,
        ) for index, row in enumerate(raw)]

    @classmethod
    def _aggregate_stats(
        cls,
        units: list[BattleUnit],
        *,
        player: Player | None = None,
        terrain_tags: list[str],
    ) -> dict[str, float]:
        stats = {key: 0.0 for key in STAT_KEYS}
        for unit in units:
            factors = {key: 1.0 for key in STAT_KEYS}
            cls._multiply(factors, cls.PATH_FACTORS.get(unit.path, {}))
            if player is not None and unit.kind == "player":
                bloodline = active_bloodline_profile(player)
                cls._multiply(factors, bloodline["stat_multipliers"])
                soul_effects = ghost_soul_effects(player)
                cls._multiply(factors, {
                    key: 1.0 + max(0.0, float(soul_effects.get(key, 0.0)))
                    for key in STAT_KEYS
                })
                natural = next((tag for tag in terrain_tags if tag in cls.NATURAL_TERRAINS), "开阔")
                artificial = [tag for tag in terrain_tags if tag in cls.ARTIFICIAL_CONDITIONS]
                bloodline_factors, _ = bloodline_stat_modifiers(
                    set(bloodline["traits"]), natural_terrain=natural, artificial_conditions=artificial,
                )
                cls._multiply(factors, bloodline_factors)
                general_traits = active_general_monster_traits(
                    player, bloodline_available=bloodline_content_available(),
                )
                general_factors, _ = general_monster_trait_modifiers(
                    general_traits, natural_terrain=natural, artificial_conditions=artificial,
                )
                cls._multiply(factors, general_factors)
            if unit.kind == "mechanical":
                cls._multiply(factors, {"might": 1.06, "guard": 1.15, "sense": 0.82, "breach": 1.10})
            elif unit.kind == "corpse":
                cls._multiply(factors, {"might": 0.94, "guard": 1.22, "mobility": 0.84, "sustain": 1.22})
            elif unit.kind == "living":
                cls._multiply(factors, {"might": 1.05, "sense": 1.12, "sustain": 0.94})
            elif unit.kind == "companion":
                cls._multiply(factors, {"sense": 1.04, "sustain": 1.04})
            for tag in terrain_tags:
                cls._multiply(factors, cls.TERRAIN_EFFECTS[tag])
            for key in STAT_KEYS:
                stats[key] += unit.power * factors[key] * max(0.0, unit.integrity)

        if player:
            techniques = [
                player.technique, player.support_technique, player.body_technique,
                player.divine_sense_technique, player.transformation_technique,
                *player.combat_techniques,
            ]
            total_power = max(1.0, sum(unit.power for unit in units))
            for technique in (entry for entry in techniques if entry):
                cls._apply_technique(stats, technique, total_power)
            body_bonus = min(0.22, max(0, player.body_training) * 0.0022)
            sense_bonus = min(0.28, max(0, player.divine_sense_rank) * 0.018)
            stats["guard"] *= 1 + body_bonus
            stats["sustain"] *= 1 + body_bonus * 0.8
            stats["sense"] *= 1 + sense_bonus
        return stats

    @classmethod
    def _apply_technique(cls, stats: dict[str, float], technique: Technique, total_power: float) -> None:
        weight = min(0.18, (0.010 + technique.grade * 0.006) * technique.level_multiplier)
        factors = cls.ELEMENT_FACTORS.get(technique.element, {})
        for key, factor in factors.items():
            stats[key] += total_power * weight * max(0.0, factor - 1.0)
        if technique.category == "body":
            stats["guard"] += total_power * weight
            stats["sustain"] += total_power * weight * 0.75
        elif technique.category == "divine_sense":
            stats["sense"] += total_power * weight * (
                1.0 + max(0.0, technique.divine_sense_bonus) * technique.level_multiplier
            )
        elif technique.category == "transformation":
            stats["might"] += total_power * weight * 0.65
            stats["sustain"] += total_power * weight * 0.65

    @staticmethod
    def _apply_objective(stats: dict[str, float], objective: str) -> None:
        if objective == "capture":
            stats["might"] *= 0.90
            stats["mobility"] *= 1.10
            stats["sense"] *= 1.14
        elif objective == "repel":
            stats["guard"] *= 1.06
            stats["breach"] *= 1.05
        elif objective == "kill":
            stats["might"] *= 1.07
            stats["sustain"] *= 0.97

    @staticmethod
    def _apply_enemy_objective(stats: dict[str, float], objective: str) -> None:
        if objective in {"capture", "rob"}:
            stats["might"] *= 0.94
            stats["sense"] *= 1.08
        elif objective in {"delay", "test"}:
            stats["guard"] *= 1.08
            stats["sustain"] *= 1.06
        elif objective == "kill":
            stats["might"] *= 1.05

    @staticmethod
    def _apply_realm_pressure(stats: dict[str, float], realm_gap: int) -> None:
        pressure = min(0.28, max(0, realm_gap) * 0.055)
        stats["might"] *= 1 + pressure
        stats["guard"] *= 1 + pressure * 0.82
        stats["sense"] *= 1 + pressure * 0.90
        stats["mobility"] *= 1 + pressure * 0.45

    @classmethod
    def _absorb_with_support(
        cls,
        units: list[BattleUnit],
        incoming: float,
        updates: dict[str, dict[str, Any]],
    ) -> tuple[float, str]:
        priority = {"corpse": 0, "mechanical": 1, "living": 2, "companion": 3}
        guards = sorted(
            (unit for unit in units if unit.kind in priority and unit.integrity > 0.05),
            key=lambda unit: (priority[unit.kind], -unit.power),
        )
        if not guards or incoming < 1.0:
            return 0.0, ""
        guard = guards[0]
        share = 0.48 if guard.kind == "corpse" else 0.36 if guard.kind == "mechanical" else 0.20
        absorbed = min(incoming * share, guard.power * guard.integrity)
        integrity_loss = absorbed / max(1.0, guard.power)
        before = guard.integrity
        guard.integrity = max(0.0, guard.integrity - integrity_loss)
        update = updates.setdefault(guard.id, {
            "id": guard.id, "name": guard.name, "kind": guard.kind,
            "field": guard.persistent_field, "before": round(before * 100, 1),
            "after": round(before * 100, 1), "destroyed": False,
        })
        update["after"] = round(guard.integrity * 100, 1)
        update["destroyed"] = guard.integrity <= 0.05
        kind_text = {"corpse": "炼尸", "mechanical": "机关傀儡", "living": "活傀", "companion": "同行者"}[guard.kind]
        ending = "并因此失去战斗能力" if update["destroyed"] else f"，完整度降至 {guard.integrity:.0%}"
        return absorbed, f"{kind_text}{guard.name}按护主预案承受主要攻势{ending}。"

    @classmethod
    def _formation_name(cls, player: Player) -> str | None:
        profile = active_formation_profile(player)
        return str(profile.get("name")) if profile.get("active") else None

    @staticmethod
    def _objective(target: dict[str, Any], lethal: bool) -> str:
        explicit = str(target.get("objective", ""))
        if explicit in {"kill", "capture", "repel"}:
            return explicit
        if target.get("capture") or target.get("action") == "capture":
            return "capture"
        if lethal:
            return "kill"
        return "repel"

    @staticmethod
    def _assessment(ratio: float) -> str:
        if ratio >= 2.5:
            return "碾压"
        if ratio >= 1.25:
            return "优势"
        if ratio >= 0.82:
            return "均势"
        if ratio >= 0.45:
            return "劣势"
        return "绝境"

    @staticmethod
    def _multiply(base: dict[str, float], changes: dict[str, float]) -> None:
        for key, factor in changes.items():
            base[key] *= factor

    @staticmethod
    def _clamp(low: float, high: float, value: float) -> float:
        return max(low, min(high, value))

    @staticmethod
    def _wave(rng: Any, low: float, high: float) -> float:
        return float(rng.uniform(low, high))

    @classmethod
    def _roll(cls, rng: Any) -> float:
        return cls._wave(rng, 0.0, 1.0)


def stat_comparison(resolution: CombatResolution) -> list[dict[str, Any]]:
    """Public six-stat comparison for a compact battle report."""
    return [{
        "id": key,
        "name": STAT_NAMES[key],
        "player": resolution.player_stats[key],
        "enemy": resolution.enemy_stats[key],
    } for key in STAT_KEYS]

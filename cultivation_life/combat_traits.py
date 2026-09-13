from __future__ import annotations

from typing import Final


# These identifiers belong to the transformation system.  Other progression
# systems must register their own traits instead of borrowing transformation
# names such as Phoenix rebirth or Asura battle intent.
COMBAT_TRAIT_REGISTRY: Final[dict[str, dict[str, str]]] = {
    "airborne": {"name": "垂天", "description": "鲲鹏、青鸾等飞行变化在开阔地形首轮更容易取得先手。"},
    "damage_bonus_5": {"name": "庚金杀伐", "description": "白虎变化造成的战斗态势损耗提高 5%。"},
    "dragon_pressure": {"name": "真龙威压", "description": "对同境及以下敌手前两轮强制先手，并削弱其战意。"},
    "first_round_full_state": {"name": "玄武镇界", "description": "第一轮己方战斗态势固定为最大值。"},
    "higher_realm_damage_10": {"name": "逆境杀心", "description": "阿修罗变化面对更高境界敌手时伤害提高 10%。"},
    "morale_drain_5": {"name": "修罗战意", "description": "阿修罗变化每轮额外削弱敌方 5 点战意。"},
    "prevent_defeat_once": {"name": "涅槃", "description": "凤凰变化在一次战斗中可避免一次致命溃败。"},
    "round4_regen_10": {"name": "朱焰回生", "description": "朱雀变化从第四轮起每轮恢复 10% 最大战斗态势。"},
    "steadfast": {"name": "镇元", "description": "麒麟、山岳猿变化令战意不易跌至溃败临界点。"},
}


def public_combat_trait(trait_id: str) -> dict[str, str]:
    definition = COMBAT_TRAIT_REGISTRY.get(trait_id, {"name": trait_id, "description": ""})
    return {"id": trait_id, **definition}

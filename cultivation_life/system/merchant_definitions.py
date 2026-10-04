"""Shared merchant commission definitions, independent of service implementations."""
KINDS = {"supply": "提交特定物品", "escort": "护送雇主", "bounty": "击杀悬赏修士",
         "recruit": "招募人手", "formation": "炼制阵法", "weapon": "炼制武器", "intel": "获取情报", "item": "获取道具", "spirit_manual": "寻访灵域残解", "talisman": "炼制符箓"}


POLICIES = {"economy": "重商兴利", "materials": "积储资材", "cultivation": "尊修育才"}
RANKS = ["成员", "使节", "特使"]
CROSS_ALLIANCES = {
    "xuanji": ("璇玑商盟", "spirit", ["spirit", "true_demon"]),
    "jiukun": ("九坤商盟", "phantom_underworld", ["phantom_underworld", "true_demon", "hell"]),
    "taiyuan": ("太元商盟", "celestial", ["celestial", "asura", "nether"]),
}
METRICS = {"growth": "生势", "kill": "杀势", "focus": "聚势", "balance": "均势", "cycle": "环势", "change": "变势"}
PROCUREMENT_KINDS = {"supply", "item", "formation", "weapon", "spirit_manual", "talisman"}

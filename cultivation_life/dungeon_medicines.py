"""Authored expedition prescriptions. All amounts are fixed by item identity."""

from .rules import add_item


def medicine_terms(item):
    family, grade = item.id.rsplit("_", 1)
    grade = int(grade)
    if family == "cavern_trace":
        return "trace", grade, 12 * (grade - 8)
    return "thunder", grade, (0.08 + 0.03 * (grade - 6))


def medicine_reason(player, item):
    effect, grade, _ = medicine_terms(item)
    if player.cultivation_suppression or player.sealed_cultivation or player.realm_index != grade:
        return "须以丹方所载的本境修为行功"
    if effect == "trace":
        if player.path != "dao" or player.world != "celestial" or not player.immortal_power_converted:
            return "须在仙界以道修仙灵力化开药力"
    elif item.id.startswith("cavern_blood_"):
        if player.path != "demonic":
            return "此丹须以魔功催动"
    elif player.path not in {"dao", "buddhist", "confucian"}:
        return "此丹须以道、佛或儒门功法催动"
    return ""


def consume(player, item):
    reason = medicine_reason(player, item)
    if reason:
        raise ValueError(reason)
    effect, _, amount = medicine_terms(item)
    if effect == "thunder" and player.next_thunder_damage_reduction >= amount:
        raise ValueError("体内已有同等或更强的护雷药力")
    from .rules import remove_item

    if not remove_item(player, item.id):
        raise ValueError("行囊中缺少此丹")
    if effect == "trace":
        add_item(player, "immortal_trace", amount)
        return f"炼化{item.name}，凝得 {amount} 道仙痕。"
    player.next_thunder_damage_reduction = amount
    return f"服下{item.name}，下次雷劫所受伤害减少 {amount:.0%}。"

"""Shared ground-array supply debit and original durability settlement."""
from ...models import HistoryRecord


def repair(game, array, supply_id, definition, quantity):
    if not definition or str(definition.get('world')) != str(array.get('world')):
        raise ValueError('这份修阵资源无法与当前界面的地脉相合')
    if type(quantity) is not int or not 1 <= quantity <= 10:
        raise ValueError('每次须使用1至10份修阵资源')
    held = int(game.player.formation_repair_supplies.get(supply_id, 0))
    if held < quantity:
        raise ValueError('持有的修阵资源不足')
    before = float(array.get('durability', 0.))
    if before >= 99.999:
        raise ValueError('镇地阵完整度已满，无需修复')
    game.player.formation_repair_supplies[supply_id] = held - quantity
    if held == quantity:
        game.player.formation_repair_supplies.pop(supply_id)
    array['durability'] = round(min(100., before + quantity * float(definition['repair_value'])), 4)
    array['last_repaired_year'] = game.player.age
    summary = f"你消耗{definition['name']} ×{quantity}，令“{array['name']}”完整度由 {before:.1f}% 恢复至 {array['durability']:.1f}%。"
    game.history.append(HistoryRecord('SYS_FORMATION_GROUND_REPAIR', 1, game.player.age, '修补阵基',
        array['id'], 'repaired', summary, dict(durability_before=before, durability_after=array['durability']),
        ['system', 'formation', 'ground_formation', 'repair']))
    return summary

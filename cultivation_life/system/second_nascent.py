"""Second souls use the detained NPC identity and actual inventory escrow."""
import copy
from ..combat_benchmarks import expected_combat_power
from ..rules import technique_scale
from .npc_techniques import equipped
from .soul_lifecycle import second_person, consume_second


def power(game):
    npc = second_person(game)
    if not npc:
        return 0.
    row = game.player.nascent_state['second']
    bonus = sum(t.combat_bonus * technique_scale(t) for _, t in equipped(game, npc))
    bonus += sum(item.get('combat_bonus', 0) for item in row['equipment'])
    return round((expected_combat_power(npc.realm_index, npc.layer) * .8 + bonus) * row['integrity'] / 100, 1)


def unit(game):
    from .combat_system import BattleUnit
    npc = second_person(game)
    if npc:
        row = game.player.nascent_state['second']
        return BattleUnit(npc.id, f'第二元婴·{npc.name}', 'second_nascent', power(game),
                         npc.realm_index, npc.path, row['integrity'] / 100, 'integrity')


def damage(game, updates):
    row = game.player.nascent_state.get('second')
    if not row:
        return
    for update in updates:
        if update.get('id') == row['id'] and update.get('field') == 'integrity':
            row['integrity'] = max(0., min(100., update['after']))
            if update.get('destroyed') or row['integrity'] <= 0:
                consume_second(game, '第二元婴在斗法中消散')
            break


def equip(game, identity):
    p = game.player
    row = p.nascent_state['second']
    item = next((i for i in p.inventory if i.id == identity), None)
    if not item or item.combat_bonus <= 0 or item.crafted_artifact_id:
        raise ValueError('请选择行囊中的普通战斗法器；本命及组合炼器不可转交')
    if identity == game.natal_artifact.get('item_id') or 'natal' in item.tags:
        raise ValueError('本命法器不可转交')
    if len(row['equipment']) >= 3:
        raise ValueError('第二元婴最多携带三件装备')
    raw = copy.deepcopy(item.to_dict())
    raw['quantity'] = 1
    row['equipment'].append(raw)
    item.quantity -= 1
    if not item.quantity:
        p.inventory.remove(item)

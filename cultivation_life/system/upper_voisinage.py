"""Small base-game cultivation provider for the three other upper worlds.

Only explicit player actions mutate mastery. Combat consumes a data-only source;
there are no annual/NPC hooks and no dependency on celestial doctrine generation.
"""
from dataclasses import asdict
from math import ceil

from ..content_registry import REALMS, CONTENT_DOCUMENTS
from ..models import HistoryRecord
from ..rules import opportunity_required, remove_item
from ..runtime import now_iso
from .cultivation_dependencies import ApertureDependencies

from .upper_voisinage_rules import (
    config as config,
    world_config as world_config,
    available as available,
    record as record,
    level as level,
    project as project,
    player_source as player_source,
    definitions,
)


def material_stock(player):
    key = world_config(player)['material_id']
    # Consume only the declared ordinary material, poorest quality first. Never
    # substitute a rare material, artifact or dynamically generated ingredient.
    return sorted((m for m in player.crafting_materials
                   if m.get('material_id') == key and not m.get('dynamic_definition')),
                  key=lambda m: (m.get('quality', 1), str(m.get('id', ''))))


def quote(player, rank, game=None):
    cfg, world = config(), world_config(player)
    material = next(m for m in CONTENT_DOCUMENTS['crafting.json']['materials'] if m['id'] == world['material_id'])
    from .upper_institutions import cultivation_discount
    discount = cultivation_discount(game) if game is not None else 0
    if game is not None and discount:
        from .institution_state import account
        discount = min(discount, account(game)['treasury'] / max(1, cfg['stone_costs'][rank - 1]))
    return dict(opportunity=ceil(opportunity_required(player) * cfg['opportunity_fractions'][rank - 1] * (1-discount)),
        stones=ceil(cfg['stone_costs'][rank - 1] * (1-discount)), discount=discount, material_id=material['id'], material_name=material['name'],
        subsidy=cfg['stone_costs'][rank - 1] - ceil(cfg['stone_costs'][rank - 1] * (1-discount)),
        materials=cfg['material_counts'][rank - 1],
        owned_materials=sum(m.get('material_id') == material['id'] and not m.get('dynamic_definition')
                            for m in player.crafting_materials),
        realm=cfg['realms'][rank - 1], realm_name=REALMS[cfg['realms'][rank - 1]].name)


def public_upper_voisinages(player, game=None):
    from .asura import active as asura_active
    if asura_active(player):
        return {'available': False}
    if not available(player):
        return {'available': False}
    world = world_config(player)
    stones = sum(i.quantity for i in player.inventory if i.id == 'spirit_stone')
    rows = []
    from . import monster_true_form, ghost_soul_form
    from .doctrine.voisinage_training import label
    for definition in definitions(player):
        rank = level(player, definition['id'])
        cost = quote(player, rank + 1, game) if rank < 13 else None
        reason = None
        if cost:
            if player.realm_index < cost['realm']:
                reason = f"须达到第 {cost['realm']} 阶修为"
            elif player.opportunity < cost['opportunity']:
                reason = '机缘不足'
            elif stones < cost['stones']:
                reason = '灵石不足'
            elif cost['owned_materials'] < cost['materials']:
                reason = '本界筑域材料不足，请在坊市炼器材料中寻找'
        reason = monster_true_form.training_reason(player, definition['id'], rank) or reason
        reason = ghost_soul_form.training_reason(player, definition['id'], rank) or reason
        rows.append(dict(id=definition['id'], name=definition['name'], description=definition['description'],
            true_form=bool(definition.get('true_form')),
            soul_form=bool(definition.get('soul_form')), label=label(rank) if rank else '尚未领悟',
            level=rank, active=record(player).get('active') == definition['id'], cost=cost,
            reason=reason, can_train=bool(cost) and not reason,
            field=asdict(project(definition, max(1, rank))),
            next_field=asdict(project(definition, rank + 1)) if rank and cost and not reason else None))
    true_form = monster_true_form.public(player)
    if true_form and not true_form['reason'] and not true_form['blueprint']:
        true_form['first_cost'] = quote(player, 1, game)
    return dict(available=True, world=player.world, title=world['title'], energy=world['energy'],
        description=world['description'], opportunity=player.opportunity, stones=stones, rows=rows,
        true_form=true_form, soul_form=ghost_soul_form.public(player, game))


def act(deps: ApertureDependencies, game_id, action, voisinage_id):
    game = deps._load(game_id)
    p = game.player
    from .asura import active as asura_active
    if asura_active(p):
        raise ValueError('修罗显圣开启时，请从八部本命修习魔域')
    if not available(p):
        raise ValueError('须在修罗、幽冥或轮回界达到第九阶修为')
    if (not p.alive or game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor
            or (game.guixu_state.get('player_session') or {}).get('trapped')
            or p.sealed_cultivation or p.cultivation_suppression):
        raise ValueError('当前状态无法修习邻域')
    from .possession_system import is_possessed
    if is_possessed(p):
        raise ValueError('寄身期间本魂邻域修行冻结')
    if action == 'soul_form_contemplate':
        return deps._soul_contemplate(game, voisinage_id)
    if action.startswith('soul_form_'):
        from .ghost_soul_form import configure
        summary = configure(p, action, voisinage_id)
        game.history.append(HistoryRecord('SYS_SOUL_FORM', 1, p.age, '照魂归真', action, 'completed', summary, {}, ['cultivation', 'voisinage']))
        game.updated_at = now_iso()
        deps.store.save(game)
        return deps.present(game)
    if action.startswith('true_form_'):
        from .monster_true_form import configure
        summary = configure(p, action, voisinage_id)
        game.history.append(HistoryRecord('SYS_TRUE_FORM', 1, p.age, '本相铸域', action, 'completed', summary, {}, ['cultivation', 'voisinage']))
        game.updated_at = now_iso()
        deps.store.save(game)
        return deps.present(game)
    row = next((r for r in public_upper_voisinages(p, game)['rows'] if r['id'] == voisinage_id), None)
    if not row:
        raise ValueError('只能修习或上阵本界邻域')
    if action == 'select':
        if not row['level']:
            raise ValueError('须先领悟该邻域')
        state = p.world_voisinages.setdefault(p.world, {})
        state['active'] = voisinage_id
        summary = f"已选定斗法采用【{row['name']}】，原有培养保留。"
    elif action == 'train':
        cost = row['cost']
        if not cost:
            raise ValueError('此邻域已修至至臻')
        if row['reason']:
            raise ValueError(row['reason'])
        if p.realm_index < cost['realm'] or p.opportunity < cost['opportunity']:
            raise ValueError('境界或机缘不足')
        if sum(i.quantity for i in p.inventory if i.id == 'spirit_stone') < cost['stones'] or len(material_stock(p)) < cost['materials']:
            raise ValueError('灵石或筑域材料不足')
        consumed = material_stock(p)[:cost['materials']]
        from .economy import organizations as finance
        finance.ensure_state(game)
        if cost['subsidy']:
            finance.register(game, 'upper', p.world, p.world)
            finance.procure(game, finance.key('upper', p.world), p.world, cost['subsidy'], '机构邻域修炼补贴')
        finance.transfer_value(game, 'player', f'background:{p.world}', cost['stones'], '邻域修炼支付')
        p.opportunity -= cost['opportunity']
        for material in consumed:
            p.crafting_materials.remove(material)
        state = p.world_voisinages.setdefault(p.world, {})
        state['progression_version'] = 2
        state.setdefault('levels', {})[voisinage_id] = row['level'] + 1
        if action == 'train' and row.get('true_form') and row['level'] + 1 == 13:
            state['true_form']['finalized'] = True
        if action == 'train' and row.get('soul_form') and row['level'] + 1 == 13:
            state['ghost_soul_form']['finalized'] = True
        state.setdefault('active', voisinage_id)
        from .doctrine.voisinage_training import label
        target = label(row['level'] + 1)
        summary = (f"【{row['name']}】修至 {target}，消耗机缘 {cost['opportunity']}、"
                   f"灵石 {cost['stones']}、{cost['material_name']} ×{cost['materials']}。")
    else:
        raise ValueError('未知本界邻域操作')
    game.history.append(HistoryRecord('SYS_UPPER_VOISINAGE', 1, p.age, world_config(p)['title'],
                                     action, 'completed', summary, {}, ['cultivation', 'voisinage']))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)

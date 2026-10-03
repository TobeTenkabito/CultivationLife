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

from .upper_voisinage_rules import (
    config as config,
    world_config as world_config,
    available as available,
    record as record,
    level as level,
    project as project,
    player_source as player_source,
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
    return dict(opportunity=ceil(opportunity_required(player) * cfg['opportunity_fractions'][rank - 1] * (1-discount)),
        stones=ceil(cfg['stone_costs'][rank - 1] * (1-discount)), discount=discount, material_id=material['id'], material_name=material['name'],
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
    for definition in world['fields']:
        rank = level(player, definition['id'])
        cost = quote(player, rank + 1, game) if rank < 9 else None
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
        rows.append(dict(id=definition['id'], name=definition['name'], description=definition['description'],
            level=rank, active=record(player).get('active') == definition['id'], cost=cost,
            reason=reason, can_train=bool(cost) and not reason,
            field=asdict(project(definition, max(1, rank))),
            next_field=asdict(project(definition, rank + 1)) if rank and cost else None))
    return dict(available=True, world=player.world, title=world['title'], energy=world['energy'],
        description=world['description'], opportunity=player.opportunity, stones=stones, rows=rows)


def act(engine, game_id, action, voisinage_id):
    game = engine._load(game_id)
    p = game.player
    from .asura import active as asura_active
    if asura_active(p):
        raise ValueError('修罗显圣开启时，请从八部本命修习魔域')
    if not available(p):
        raise ValueError('须在修罗、幽冥或轮回界达到第九阶修为')
    if (not p.alive or game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor
            or (game.guixu_state.get('player_session') or {}).get('trapped')):
        raise ValueError('当前状态无法修习邻域')
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
        if not row['cost']:
            raise ValueError('此邻域已修至九级')
        if row['reason']:
            raise ValueError(row['reason'])
        cost = row['cost']
        consumed = material_stock(p)[:cost['materials']]
        remove_item(p, 'spirit_stone', cost['stones'])
        p.opportunity -= cost['opportunity']
        for material in consumed:
            p.crafting_materials.remove(material)
        state = p.world_voisinages.setdefault(p.world, {})
        state.setdefault('levels', {})[voisinage_id] = row['level'] + 1
        state.setdefault('active', voisinage_id)
        summary = (f"【{row['name']}】修至 Lv{row['level'] + 1}，消耗机缘 {cost['opportunity']}、"
                   f"灵石 {cost['stones']}、{cost['material_name']} ×{cost['materials']}。")
    else:
        raise ValueError('未知本界邻域操作')
    game.history.append(HistoryRecord('SYS_UPPER_VOISINAGE', 1, p.age, world_config(p)['title'],
                                     action, 'completed', summary, {}, ['cultivation', 'voisinage']))
    game.updated_at = now_iso()
    engine.store.save(game)
    return engine.present(game)

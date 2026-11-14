"""Shared secret-art access and original material lookup; no commands."""
from ..content_registry import ITEM_CATALOG
from .possession_system import is_possessed


def blocked_reason(game):
    p = game.player
    if not p.alive:
        return '此生已经结束'
    if game.pending_event or game.active_trial:
        return '请先处理当前事件或劫数'
    if p.imprisonment or p.ghost_captor or is_possessed(p):
        return '拘禁、拘魂或寄身期间不能修习和施展补灵秘法'
    if game.guixu_state.get('player_session') or game.trial_site_state.get('active'):
        return '请先离开当前副本，再修习秘法'
    if p.cultivation_suppression or p.sealed_cultivation:
        return '请先解除修为压制或循原路返界，再修习补灵秘法'
    if p.world == 'celestial' and not p.immortal_power_converted:
        return '请先完成仙灵力转化'
    return ''


def materials(player, art):
    rows = []
    for item in player.inventory:
        definition = ITEM_CATALOG.get(item.id)
        if not definition or item.quantity < 1:
            continue
        tags = set(definition.tags)
        if not tags.intersection({'secret_art_core', 'secret_art_soul'}) or 'affinity:' + art['affinity'] not in tags:
            continue
        rank = next((int(t[6:]) for t in tags if t.startswith('realm:') and t[6:].isdigit()), 0)
        if rank >= art['material_realm']:
            kind = 'core' if 'secret_art_core' in tags else 'soul'
            rows.append(dict(id='item:' + item.id, name=definition.name, kind=kind, realm_index=rank, quantity=item.quantity))
    return sorted(rows, key=lambda row: (row['realm_index'], row['id']))



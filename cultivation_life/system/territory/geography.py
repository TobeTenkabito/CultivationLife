"""Shared geographic limits and contest arithmetic for local and foreign claims."""
from .rules import MAX_FACTIONS


def validate_claim(maps, world, book, identity, location, *, headquarters=None, existing=False, occupies_slot=True):
    site = maps.location(world, location)
    if not site or site.get('min_realm_index', 0) and location != headquarters:
        raise ValueError('有境界门槛的地图不能扩张、建据点或迁入；现有驻地保留')
    if identity in book.get(location, {}):
        return
    if existing:
        raise ValueError('当地没有己方影响力')
    if occupies_slot and len(book.get(location, {})) >= MAX_FACTIONS:
        raise ValueError('当地已有三个势力，须先移除一方影响力')
    if not any(identity in book.get(neighbor, {}) for neighbor, _ in maps._graphs[world][location]):
        raise ValueError('只能沿己方影响力边界连续扩张')


def contest_chance(own, enemy):
    return max(.15, min(.85, .5 + .12 * (own[0] - enemy[0]) + .015 * (own[1] - enemy[1])))


def change_claim(book, location, identity, action, *, policy='', won=True):
    row = book.setdefault(location, {}).setdefault(identity, dict(value=0., outpost=False, policy=''))
    if action == 'territory_policy':
        row['policy'] = policy
    elif action == 'build_outpost':
        row.update(outpost=True, value=max(50., row['value']))
    elif action == 'expand_influence':
        row['value'] = min(100., row['value'] + 20)
    elif action == 'territory_spar' and won:
        row['value'] = min(100., row['value'] + 12)
    return row

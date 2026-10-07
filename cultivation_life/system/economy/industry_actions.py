"""Authorized organization investment commands."""
from .ledger import transfer_value
from .state import ensure_regional_market

def invest(game, maps, kind):
    from .organizations import register
    from ..faction_geography import faction_site
    p = game.player
    entity = game.family if kind == 'family' else game.sects.get(p.faction_id) if kind == 'sect' else None
    if not entity or entity.extinct or entity.world != p.world or entity.kind == 'institution':
        raise ValueError('没有可经营的本界家族或宗门产业')
    authority = game.intrigue_state.get('factions', {}).get(f'{kind}:{entity.id}', {})
    if kind == 'sect' and not entity.founded_by_player and authority.get('controller_id') != 'player':
        raise ValueError('只有宗门执掌者可安排产业投资')
    if p.location_id != faction_site(entity)['id']:
        raise ValueError('请前往产业所在的组织驻地')
    row = register(game, kind, entity.id, p.world)
    level = row.get('industry_level', 0)
    if level >= 10:
        raise ValueError('产业扩建已达十级上限')
    ensure_regional_market(game, maps, p.world, p.location_id)
    market = game.economy_v2['markets'][f'{p.world}:{p.location_id}']
    multiplier = sum(r['price'] / r['reference'] for r in market['commodities'].values()) / max(1, len(market['commodities']))
    cost = max(1, round(10000 * (level + 1) ** 2 * multiplier))
    transfer_value(game, f'organization:{kind}:{entity.id}', f'background:{p.world}', cost, '组织产业扩建')
    row['industry_level'] = level + 1
    row['expense'] += cost

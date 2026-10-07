"""Local, read-only concentration estimates and enforceable market rights."""
from ...content_registry import ITEM_CATALOG
from .market_power import indicators
from .market_governance import POLICIES, active
from .enterprise_state import owner_allowed


def name(game, identity):
    if identity == 'player':
        return '本人经营'
    if identity.startswith('organization:'):
        _, kind, key = identity.split(':', 2)
        entity = game.family if kind == 'family' else game.sects.get(key)
        return entity.name if entity and entity.id == key else '原属组织'
    if identity.startswith('alliance:'):
        _, world, key = identity.split(':', 2)
        alliance = next((a for a in game.merchant_state.get('worlds', {}).get(world, []) if a['id'] == key), None)
        return alliance['name'] if alliance else '原属商盟'
    return '本地经营者'


def public(game, market, visible):
    rows = []
    for item, data in market.get('competition', {}).items():
        if item not in visible:
            continue
        leaders = indicators(game, market, item, data)
        leader = leaders[0] if leaders else dict(owner='', supply=0., purchase=0., storage=0., power=0.)
        rows.append(dict(item=item, name=ITEM_CATALOG[item].name, owner=name(game, leader['owner']),
            **{k:round(leader[k] * 100, 1) for k in ('supply', 'purchase', 'storage', 'power')},
            pressure=round(data['pressure'], 1), invested=data['invested'], added=data['added'],
            imported=market['commodities'][item].get('imported', False), history=list(data['history'])))
    claim = market.get('control')
    control = None
    if claim:
        control = dict(owner=name(game, f"organization:{claim['kind']}:{claim['id']}"), policy=claim['policy'],
            label=POLICIES[claim['policy']][0] if active(game, market) else '控制方离界或消亡，暂停上缴', received=claim['received'], since=claim['since'],
            can_manage=owner_allowed(game, claim['kind'], claim['id'], market['world']))
    return dict(rows=sorted(rows, key=lambda r:(-r['pressure'], -r['power'], r['item'])), control=control,
        policies=[dict(id=k, name=v[0], percent=v[1]) for k,v in POLICIES.items()])

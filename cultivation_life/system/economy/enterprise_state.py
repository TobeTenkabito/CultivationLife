"""Fixed-site property ownership, storage and the single authoritative payer."""
from .ledger import account, balance
from .enterprise_rules import capacity


def estates(game):
    return game.economy_v2.get('estates', {})


def owner_allowed(game, kind, identity, world):
    p = game.player
    if kind == 'player':
        return identity == game.id
    if kind == 'alliance':
        row = next((a for a in game.merchant_state.get('worlds', {}).get(world, []) if a['id'] == identity), None)
        return bool(row and row.get('player_owned'))
    entity = game.family if kind == 'family' else game.sects.get(identity) if kind == 'sect' else None
    if not entity or entity.id != identity or entity.world != world or entity.extinct or entity.kind == 'institution':
        return False
    record = game.intrigue_state.get('factions', {}).get(f'{kind}:{identity}', {})
    return kind == 'family' or entity.founded_by_player or record.get('controller_id') == 'player'


def payer(row):
    kind, identity = row['owner_kind'], row['owner_id']
    if kind == 'player':
        return f'estate:{row["id"]}'
    if kind == 'alliance':
        return f'alliance:{row["world"]}:{identity}'
    return f'organization:{kind}:{identity}'


def cash_ready(game, row):
    key = payer(row)
    if row['owner_kind'] == 'player':
        account(game, key)
    else:
        balance(game, key)  # Organization adoption happens at the command boundary.
    return key


def quantity(value, maximum=1000000):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError('数量须为正整数且不超过容量上限')
    return value


def used(row):
    job = row.get('job')
    return sum(row['stock'].values()) + (job['quantity'] if job else 0)


def put(row, item, number):
    if number < 0 or used(row) + number > capacity(row):
        raise ValueError('产业仓储容量不足，请先出货或扩建')
    row['stock'][item] = row['stock'].get(item, 0) + number


def take(row, item, number):
    if row['stock'].get(item, 0) < number:
        raise ValueError('产业仓库库存不足')
    row['stock'][item] -= number
    if not row['stock'][item]:
        del row['stock'][item]


def require_local(game, identity):
    row = estates(game).get(identity)
    p = game.player
    if not row or (row['world'], row['location']) != (p.world, p.location_id):
        raise ValueError('请亲赴该产业所在地办理')
    if not owner_allowed(game, row['owner_kind'], row['owner_id'], row['world']):
        raise ValueError('没有该产业的经营权限')
    return row


def encumbered(game, identity):
    for region in game.economy_v2.get('transport', {}).get('worlds', {}).values():
        for fleet in region['fleets'].values():
            for record in [fleet.get('cargo'), fleet.get('cross_trip'), fleet.get('trade_order')]:
                if record and identity in {record.get('source_estate'), record.get('target_estate')}:
                    return True
    return False


def log(row, age, message):
    row['history'].append([age, message])
    del row['history'][:-12]

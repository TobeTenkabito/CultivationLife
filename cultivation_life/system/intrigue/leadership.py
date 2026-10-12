"""Sect office eligibility. Appointment never changes ownership or voting rights."""

def candidates(game, record, members):
    entity = game.sects.get(record.get('id'))
    if record.get('kind') != 'sect' or not entity or entity.extinct:
        return {}
    guests = {row.get('npc_id') for row in record.get('guests', [])}
    guests.add(record.get('positions', {}).get('guest_elder'))
    prisoners = game.intrigue_state.get('npc_prisons', {})
    rows = {npc.id: npc.name for npc in members if npc.alive and npc.world == entity.world and npc.roster_state == 'active'
            and npc.id not in guests and npc.id not in prisoners}
    p = game.player
    if (p.alive and p.faction_id == entity.id and p.world == entity.world
            and not p.imprisonment and 'player' not in guests):
        rows['player'] = p.name
    return rows


def validate(game, record, members, target):
    if record.get('kind') != 'sect':
        raise ValueError('更换掌门仅适用于宗门')
    if (target == record.get('positions', {}).get('guest_elder')
            or any(row.get('npc_id') == target for row in record.get('guests', []))):
        raise ValueError('客卿长老不得担任掌门')
    eligible = candidates(game, record, members)
    if target not in eligible:
        raise ValueError('掌门须为同界、存活且未被关押的正式宗门成员')
    return eligible[target]


def appoint(game, record, members, target):
    name = validate(game, record, members, target)
    for office, holder in list(record['positions'].items()):
        if holder == target:
            record['positions'][office] = None
    record['positions']['leader'] = target
    if target == 'player':
        record['player_auto_office'] = None
    return name

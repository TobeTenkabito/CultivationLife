"""Prison eligibility and settlement share the original organization ledger."""
from ...content_registry import WORLD_SYSTEMS
from ...npc_custody import is_free
from ...spatial_people import accessible
from .prison_state import is_imprisoned


def _refresh_war_supply(game, identities):
    """Rebuild existing demand only for war sides affected by a custody change."""
    for war in game.wars:
        if war.get('status') not in {'active', 'peace_ready'}:
            continue
        for side in ('attacker', 'defender'):
            if identities.intersection(war.get('roster', {}).get(side, ())):
                row = war.get('logistics', {}).get('sides', {}).get(side)
                if row is not None:
                    from ..war.requirements import refresh
                    from ..war.logistics import need
                    refresh(game, war, side)
                    row['reference_need'] = need(game, war, side)


def advance_prison_year(game):
    """Settle one consumed world year, visiting only the original occupied prisons."""
    if not WORLD_SYSTEMS.get('intrigue_dlc', {}).get('enabled'):
        return
    state = game.intrigue_state
    index = state.get('npc_prisons', {})
    if not index:
        return
    released = set()
    for key in set(index.values()):
        record = state.get('factions', {}).get(key)
        if not record:
            continue
        remaining = []
        for row in record.get('prison', []):
            identity = str(row.get('prisoner_id', ''))
            if identity == 'player':
                remaining.append(row)
                continue
            row['sentence_remaining'] = max(0, int(row.get('sentence_remaining', 0)) - 1)
            if row['sentence_remaining']:
                remaining.append(row)
            elif index.get(identity) == key:
                index.pop(identity)
                released.add(identity)
        record['prison'] = remaining
    if released:
        _refresh_war_supply(game, released)


def release(game, record, npc_id):
    key = f"{record['kind']}:{record['id']}"
    index = game.intrigue_state.get('npc_prisons', {})
    row = next((r for r in record.get('prison', []) if str(r.get('prisoner_id')) == npc_id), None)
    if npc_id == 'player' or not row or index.get(npc_id) not in {None, key}:
        raise ValueError('目标不在本势力监狱')
    record['prison'] = [r for r in record['prison'] if str(r.get('prisoner_id')) != npc_id]
    index.pop(npc_id, None)
    _refresh_war_supply(game, {npc_id})
    record['fear'] = max(0.0, float(record.get('fear', 0)) - 3)
    return row


def imprisonment_error(game, record, npc):
    if record.get('kind') not in {'sect', 'family'}:
        return '仅宗门或家族可以监禁在册成员；外部人物请通过通缉令处理'
    if not npc or not is_free(npc):
        return '目标不是在册的自由存活成员；外部人物请通过通缉令处理'
    if npc.id == record.get('controller_id'):
        return '不能监禁当前控制者'
    if not accessible(game, npc):
        return '目标不在当前界面或处于无法接触的任务与空间中'
    if is_imprisoned(game, npc.id):
        return '目标已经被关押'
    return ''


def validate_imprisonment(game, record, members, npc_id):
    npc = next((n for n in members if n.id == npc_id), None)
    error = imprisonment_error(game, record, npc)
    if error:
        raise ValueError(error)
    return npc


def prison_terms(years, reason):
    if isinstance(years, bool) or not isinstance(years, int) or not 1 <= years <= 1000:
        raise ValueError('刑期须为 1–1000 年的整数')
    if not isinstance(reason, str):
        raise ValueError('请填写监禁事由')
    return years, reason.strip()[:40] or '违抗势力法令'


def imprison(game, record, members, npc_id, *, years=10, reason='', imprisoned_by='player'):
    npc = validate_imprisonment(game, record, members, npc_id)
    years, reason = prison_terms(years, reason)
    entry = dict(prisoner_id=npc.id, name=npc.name, faction_id=record['id'], kind=record['kind'],
                 sentence_remaining=years, sentence_years=years, reason=reason, imprisoned_by=imprisoned_by)
    record['prison'].append(entry)
    game.intrigue_state['npc_prisons'][npc.id] = f"{record['kind']}:{record['id']}"
    _refresh_war_supply(game, {npc.id})
    game.player.party[:] = [row for row in game.player.party if str(row.get('id')) != npc.id]
    npc.affinity = float(npc.affinity or 0) - 25
    record['fear'] = min(100.0, float(record.get('fear', 0)) + 12)
    record['unrest'] = min(100.0, float(record.get('unrest', 0)) + 7)
    return entry

"""Scenery events grant the existing personal secret ledger once, without payment."""
from ..soul_secret_content import STORIES
from ..soul_rules import SECRETS
from ..content_registry import REALMS
from .soul_lifecycle import record


def identity(row):
    if row['type'] != 'scenery' or row['address']['world'] != 'human' or row['address'].get('instance_id'):
        return None
    return next((key for key, tale in STORIES.items()
                 if row.get('content_id') == tale['building'] and row['address']['location_id'] == tale['location']), None)


def choices(row):
    key = identity(row)
    return [option('secret:main', STORIES[key]['title'])] if key else []


def option(key, text, reason=''):
    return dict(id=key, text=text, enabled=not reason, **({'disabled_reason': reason} if reason else {}))


def reason(game, key):
    p = game.player
    if key in p.nascent_state.get('known', []):
        return '已经掌握此秘法'
    if not p.alive or p.imprisonment or p.ghost_captor or game.active_trial:
        return '当前状态无法领悟传承'
    if p.cultivation_suppression or p.sealed_cultivation:
        return '请先解除修为压制或下界封印'
    if p.nascent_state.get('crisis'):
        return '请先处理神魂夺舍危机'
    if p.realm_index < SECRETS[key][1]:
        return f'须达到{REALMS[SECRETS[key][1]].name}才能领悟'
    return ''


def project(game, row, node):
    key = identity(row)
    if not key or node not in {'secret:main', 'secret:read', 'secret:result'}:
        return None
    tale = STORIES[key]
    if node == 'secret:main':
        body = tale['opening']
        actions = [option('secret:read', tale['investigate'])]
    elif node == 'secret:read':
        body = tale['discovery']
        why = reason(game, key)
        if why:
            body += '\n\n' + why + ('，重读不会重复获得奖励。' if key in game.player.nascent_state.get('known', []) else '。可以离开后再来，尚未领悟不会失去传承。')
        actions = [option('secret:learn', '领悟' + SECRETS[key][0], why)]
    else:
        body = tale['ending']
        actions = [option('secret:main', '重读这段传承')]
    actions.extend([option('back', '返回' + row['name']), option('leave', '离开' + row['name'])])
    return dict(title=row['name'] + ' · ' + tale['title'], body=body, choices=actions)


def act(game, row, choice):
    if choice != 'secret:learn':
        return choice
    key = identity(row)
    if not key:
        raise ValueError('此处没有该传承')
    why = reason(game, key)
    if why:
        raise ValueError(why)
    state = game.player.nascent_state
    state.setdefault('known', []).append(key)
    state['revision'] = state.get('revision', 0) + 1
    record(game, f'在{row["name"]}探索「{STORIES[key]["title"]}」，领悟{SECRETS[key][0]}。',
           dict(secret=key, building_id=row['id']))
    return 'secret:result'

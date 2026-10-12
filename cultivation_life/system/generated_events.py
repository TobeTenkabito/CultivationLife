"""Base-game generated events reuse the ordinary event effects and save transaction."""
from __future__ import annotations

import copy

from ..generated_event_generation import generate
from ..generated_event_schema import PREFIX, VERSION, decode_state, validate_record
from ..content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG, WORLD_SYSTEMS
from ..rules import max_hp, max_mp


def is_generated(event):
    return isinstance(event, dict) and isinstance(event.get('id'), str) and event['id'].startswith(PREFIX)


def prepare(game, reward_pools, location_name):
    state = decode_state(game.generated_event_state)
    if state.get('active') is not None:
        raise ValueError('请先完成已经发现的随机异闻')
    p = game.player
    if p.world not in WORLD_SYSTEMS['world_profiles'] or WORLD_SYSTEMS['world_profiles'][p.world]['tier'] <= 0:
        raise ValueError('当前空间尚不支持勘察异闻')
    sequence = state.get('sequence', 0) + 1
    pool = []
    for category, candidates in reward_pools.items():
        for row in candidates:
            kind = 'technique' if category == 'technique' else 'item'
            catalog = TECHNIQUE_CATALOG if kind == 'technique' else ITEM_CATALOG
            content_id = str(row['content_id'])
            if content_id in catalog:
                pool.append({'kind': kind, 'content_id': content_id,
                             'name': catalog[content_id].name, 'tier': int(row['tier'])})
    source = dict(world=p.world, location_id=p.location_id, instance_id=None,
                  realm_index=p.realm_index, layer=p.layer, location_name=location_name)
    record = generate(game.seed, sequence, source, pool)
    game.generated_event_state = dict(schema_version=VERSION, sequence=sequence,
                                     active=record, last_result=state.get('last_result'))
    return project(game, record)


def definition_for(game, event):
    """Resolve the saved authority, not effects or truth copied into a page."""
    state = decode_state(game.generated_event_state)
    record = state.get('active')
    if record is None or not is_generated(event) or event['id'] != record['id']:
        raise ValueError('随机异闻已经变化，请查看当前事件后再选择')
    validate_record(record)
    definition = {'id': record['id'], 'version': record['version'], 'title': record['title'],
                  'body': record['body'], 'tags': ['generated', 'exploration', f'world:{record["source"]["world"]}'],
                  'choices': []}
    for row in record['choices']:
        checks, effects = [], []
        if row['mp_cost']:
            checks.append({'path': 'player.mp_ratio', 'op': 'gte', 'value': row['mp_cost']})
            effects.append({'type': 'restore_mp', 'value': -row['mp_cost']})
        if row['id'] != 'leave':
            # Both routes use the same publicly stated safety gate; the
            # enabled state must not reveal which route has the hidden loss.
            risk = max(choice['hp_cost'] for choice in record['choices'])
            checks.append({'path': 'player.hp_ratio', 'op': 'gt', 'value': risk})
        if row['hp_cost']:
            effects.append({'type': 'damage', 'value': row['hp_cost'], 'reason': '异闻机关失衡'})
        if row['opportunity']:
            effects.append({'type': 'add_opportunity', 'value': row['opportunity']})
        if row['reward']:
            reward = row['reward']
            catalog = TECHNIQUE_CATALOG if reward['kind'] == 'technique' else ITEM_CATALOG
            if reward['content_id'] not in catalog:
                raise ValueError('随机异闻奖励定义不可用；原结果保留')
            effects.append({'type': 'learn_technique', 'technique_id': reward['content_id']}
                           if reward['kind'] == 'technique' else
                           {'type': 'add_item', 'item_id': reward['content_id'], 'quantity': 1})
        definition['choices'].append({'id': row['id'], 'text': row['text'], 'effects': effects,
                                      'conditions': {'all': checks} if checks else {},
                                      'disabled_reason': '所在地或状态已变化，或气血、法力不足',
                                      'result_text': row['result_text']})
    return definition


def project(game, record):
    event = dict(id=record['id'], title=record['title'], body=record['body'], choices=[])
    for row in record['choices']:
        enabled = choice_available(game, record, row['id'])
        event['choices'].append(dict(id=row['id'], text=row['text'], enabled=enabled,
                                     disabled_reason='所在地或状态已变化，或气血、法力不足'))
    return event


def choice_available(game, record, choice_id):
    if choice_id == 'leave':
        return True
    try:
        require_scene(game, record, choice_id)
    except ValueError:
        return False
    row = next(row for row in record['choices'] if row['id'] == choice_id)
    risk = max(row['hp_cost'] for row in record['choices'])
    return game.player.hp / max_hp(game.player) > risk and game.player.mp / max_mp(game.player) >= row['mp_cost']


def require_scene(game, record, choice_id):
    # If another authorized event in front of this one moved or detained the
    # player, dismissing a discovery must still be possible without rewards.
    if choice_id == 'leave':
        return
    p, source = game.player, record['source']
    instance = game.spatial_state.get('current') if p.world in {'lost', 'rift'} else None
    if (p.world, p.location_id, instance) != (source['world'], source['location_id'], source['instance_id']):
        raise ValueError('你已离开这处异闻所在地')
    if game.active_trial or p.imprisonment or p.ghost_captor:
        raise ValueError('当前状态不能处理随机异闻')


def finish(game, event, choice_id):
    record = game.generated_event_state['active']
    row = next(choice for choice in record['choices'] if choice['id'] == choice_id)
    result = dict(event_id=record['id'], template_id=record['template_id'],
                  choice_id=choice_id, signal=row['signal'])
    game.generated_event_state['last_result'] = result
    game.generated_event_state['active'] = None
    return copy.deepcopy(result)

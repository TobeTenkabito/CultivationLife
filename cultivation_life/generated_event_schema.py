"""Bounded saved generated events; no catalog loading or gameplay on decode."""
from __future__ import annotations

import copy
import math
import re

VERSION = 1
PREFIX = 'SYS_GENERATED_'
TEMPLATES = frozenset({'spring', 'array', 'casket', 'tablet', 'plant', 'lamp'})
SIGNALS = frozenset({'released', 'stabilized', 'preserved', 'damaged', 'left'})


def _require(condition):
    if not condition:
        raise ValueError('随机异闻记录无效；原存档保留')


def _text(value, limit=160):
    _require(isinstance(value, str) and 0 < len(value) <= limit)


def _number(value, low, high):
    _require(type(value) in {int, float} and math.isfinite(value) and low <= value <= high)


def validate_record(record):
    _require(isinstance(record, dict) and set(record) == {
        'id', 'version', 'sequence', 'source', 'template_id', 'variant',
        'title', 'body', 'choices',
    })
    if record['version'] != VERSION or type(record['version']) is not int:
        raise ValueError('随机异闻生成版本不受支持；原存档保留')
    _require(type(record['sequence']) is int and 1 <= record['sequence'] <= 10**12)
    _require(isinstance(record['id'], str) and re.fullmatch(
        rf'{PREFIX}{record["sequence"]}_[0-9a-f]{{16}}', record['id']))
    _require(record['template_id'] in TEMPLATES and type(record['variant']) is int and record['variant'] in {0, 1})
    _text(record['title'])
    _text(record['body'], 4000)
    source = record['source']
    _require(isinstance(source, dict) and set(source) == {
        'world', 'location_id', 'instance_id', 'realm_index', 'layer', 'location_name',
    })
    for key in ('world', 'location_id', 'location_name'):
        _text(source[key])
    _require(source['instance_id'] is None or isinstance(source['instance_id'], str))
    _require(type(source['realm_index']) is int and 0 <= source['realm_index'] <= 12)
    _require(type(source['layer']) is int and 1 <= source['layer'] <= 9)
    _require(isinstance(record['choices'], list) and len(record['choices']) == 3)
    _require({row.get('id') for row in record['choices'] if isinstance(row, dict)} == {'route_a', 'route_b', 'leave'})
    for choice in record['choices']:
        _require(isinstance(choice, dict) and set(choice) == {
            'id', 'text', 'hp_cost', 'mp_cost', 'opportunity', 'reward', 'result_text', 'signal',
        })
        _text(choice['text'], 500)
        _text(choice['result_text'], 1000)
        _number(choice['hp_cost'], 0, .25)
        _number(choice['mp_cost'], 0, .25)
        _number(choice['opportunity'], 0, 1000)
        _require(choice['signal'] in SIGNALS)
        reward = choice['reward']
        if reward is not None:
            _require(isinstance(reward, dict) and set(reward) == {'kind', 'content_id', 'name', 'tier'})
            _require(reward['kind'] in {'item', 'technique'})
            _text(reward['content_id'])
            _text(reward['name'])
            _require(type(reward['tier']) is int and 1 <= reward['tier'] <= 12)
    leave = next(row for row in record['choices'] if row['id'] == 'leave')
    _require(leave['hp_cost'] == leave['mp_cost'] == leave['opportunity'] == 0
             and leave['reward'] is None and leave['signal'] == 'left')


def decode_state(value):
    _require(isinstance(value, dict))
    if not value:
        return {}
    _require(set(value) == {'schema_version', 'sequence', 'active', 'last_result'})
    _require(type(value['schema_version']) is int and value['schema_version'] == VERSION)
    _require(type(value['sequence']) is int and 0 <= value['sequence'] <= 10**12)
    if value['active'] is not None:
        validate_record(value['active'])
        _require(value['active']['sequence'] == value['sequence'])
    result = value['last_result']
    if result is not None:
        _require(isinstance(result, dict) and set(result) == {'event_id', 'template_id', 'choice_id', 'signal'})
        _text(result['event_id'])
        _require(result['template_id'] in TEMPLATES and result['choice_id'] in {'route_a', 'route_b', 'leave'}
                 and result['signal'] in SIGNALS)
    return copy.deepcopy(value)

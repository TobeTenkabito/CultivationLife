"""Bounded save protocol for static, player-only trial sites (structure 10)."""
from __future__ import annotations

import copy
import math

VERSION = 1
PREFIX = 'SYS_TRIAL_SITE_'
TIER_ROWS = {
    1: (1, 2, 3, 4, 4, 5, 5),
    2: (1, 2, 3, 4, 5, 6, 6, 7, 7, 7, 8, 8, 8, 8),
    3: (1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 10, 10, 10, 11, 11, 11, 11, 12, 12, 12, 12, 12),
}
WORLD_TIERS = {'human': 1, 'demon': 1, 'spirit': 2, 'true_demon': 2,
               'monster_realm': 2, 'phantom_underworld': 2, 'hell': 2,
               'celestial': 3, 'asura': 3, 'nether': 3, 'reincarnation': 3}
REALM_ROWS = {world: TIER_ROWS[tier] for world, tier in WORLD_TIERS.items()}
KINDS = ('flow', 'cooling', 'seal', 'treasure', 'core')
SUBJECTS = ('炉纹', '灵泉', '灯座', '古碑', '石匣', '遗圃')


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('试境整数状态无效')


def numeric(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('试境数值状态无效')


def fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError('试境状态字段不匹配，原档保留')


def text(value, limit=300):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ValueError('试境文本状态无效')


def boolean(value):
    if type(value) is not bool:
        raise ValueError('试境开关状态无效')


def decode_state(value):
    if value == {}:
        return {}
    fields(value, 'version sites active')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('试境版本不受支持，原档保留')
    sites = value['sites']
    if not isinstance(sites, dict) or set(sites) - REALM_ROWS.keys():
        raise ValueError('试境界面状态无效')
    for world, site in sites.items():
        fields(site, 'id world location_id floors cleared')
        if site['world'] != world or site['id'] != 'trial:' + world:
            raise ValueError('试境归属不匹配')
        text(site['location_id'], 80)
        integer(site['cleared'], 0, len(REALM_ROWS[world]))
        if not isinstance(site['floors'], dict) or len(site['floors']) > len(REALM_ROWS[world]):
            raise ValueError('试境层记录无效')
        for key, floor in site['floors'].items():
            if key not in {str(n) for n in range(1, len(REALM_ROWS[world]) + 1)}:
                raise ValueError('试境层编号无效')
            fields(floor, 'id number realm layer base_power boss_name template nodes rewards index delta guard bonus supply cooling treasure field history attempts revision status result energy')
            integer(floor['number'], 1, len(REALM_ROWS[world]))
            integer(floor['realm'], 1, 12)
            if key != str(floor['number']) or floor['realm'] != REALM_ROWS[world][int(key) - 1]:
                raise ValueError('试境层境界不匹配')
            integer(floor['layer'], 1, 9)
            text(floor['id'], 100)
            if not floor['id'].startswith(PREFIX):
                raise ValueError('试境层身份无效')
            if not floor['id'].startswith(f"{PREFIX}{world}_{floor['number']}_"):
                raise ValueError('试境层身份与归属不匹配')
            text(floor['boss_name'], 80)
            integer(floor['template'], 0, 2)
            numeric(floor['base_power'], 1, 1e30)
            numeric(floor['delta'], -.3, .4)
            numeric(floor['energy'], 0, 1e6)
            integer(floor['index'], 0, 5)
            integer(floor['attempts'], 0, 1000000)
            integer(floor['revision'], 0, 2000000)
            for name in ('guard', 'bonus', 'supply', 'cooling', 'treasure', 'field'):
                boolean(floor[name])
            if floor['status'] not in {'exploring', 'ready', 'failed', 'won', 'claimed'}:
                raise ValueError('试境进度状态无效')
            if floor['status'] == 'exploring' and floor['index'] >= 5 or floor['status'] != 'exploring' and floor['index'] != 5:
                raise ValueError('试境节点与阶段不匹配')
            if floor['status'] == 'claimed' and int(key) > site['cleared']:
                raise ValueError('试境领奖进度不匹配')
            if int(key) <= site['cleared'] and floor['status'] != 'claimed':
                raise ValueError('试境通关记录不匹配')
            if not isinstance(floor['nodes'], list) or len(floor['nodes']) != 5:
                raise ValueError('试境必须有五个事件')
            for kind, node in zip(KINDS, floor['nodes']):
                fields(node, 'kind subject variant order')
                if node['kind'] != kind or node['subject'] not in SUBJECTS:
                    raise ValueError('试境事件模板无效')
                integer(node['variant'], 0, 3)
                if not isinstance(node['order'], list) or any(type(key) is not str for key in node['order']) or sorted(node['order']) != ['a', 'b', 'c']:
                    raise ValueError('试境选项顺序无效')
            if not isinstance(floor['history'], list) or len(floor['history']) != floor['index']:
                raise ValueError('试境选择记录无效')
            for entry in floor['history']:
                fields(entry, 'event_id choice_id summary')
                text(entry['event_id'], 130)
                if entry['choice_id'] not in {'a', 'b', 'c'}:
                    raise ValueError('试境选项记录无效')
                text(entry['summary'], 800)
            if [entry['event_id'] for entry in floor['history']] != [f"{floor['id']}_node_{n}" for n in range(1, floor['index'] + 1)]:
                raise ValueError('试境节点结算身份不匹配')
            if not isinstance(floor['rewards'], list) or len(floor['rewards']) != 2:
                raise ValueError('试境奖励记录无效')
            for reward in floor['rewards']:
                if 'roll' in reward:
                    from .generated_loot_schema import validate_reward
                    validate_reward(reward)
                else:
                    fields(reward, 'kind content_id name tier')
                if reward['kind'] not in {'item', 'technique'}:
                    raise ValueError('试境奖励类别无效')
                text(reward['content_id'], 120)
                text(reward['name'], 120)
                integer(reward['tier'], 1, floor['realm'])
            if floor['result'] is not None:
                fields(floor['result'], 'outcome summary')
                text(floor['result']['outcome'], 80)
                text(floor['result']['summary'], 20000)
        if set(str(n) for n in range(1, site['cleared'] + 1)) - site['floors'].keys():
            raise ValueError('试境已通过层记录缺失')
    active = value['active']
    if active is not None:
        fields(active, 'world floor')
        if active['world'] not in sites or str(active['floor']) not in sites[active['world']]['floors']:
            raise ValueError('试境活动层不存在')
        integer(active['floor'], 1, len(REALM_ROWS[active['world']]))
        if sites[active['world']]['floors'][str(active['floor'])]['status'] == 'claimed':
            raise ValueError('已领奖层不能保持挑战会话')
    return copy.deepcopy(value)

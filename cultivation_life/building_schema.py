"""Persistent building identities; no people, inventory or economic replicas."""
import copy
import json

TYPES = ('city', 'scenery', 'industry', 'artificiality', 'other')
OWNER_KINDS = {'none', 'player', 'npc', 'sect', 'family', 'alliance', 'background'}
STATES = {'intact', 'damaged', 'destroyed'}
CITY_POPULATIONS = ('cultivator', 'mortal', 'mixed')


def bind_context(game):
    game.player._building_context = game.building_state
    game.player._building_owner_id = game.id
    game.player._building_guixu_context = game.guixu_state
    game.player._building_trial_context = game.trial_site_state


def address(game):
    p = game.player
    instance = game.spatial_state.get('current') if p.world in {'lost', 'rift'} else None
    return dict(world=p.world, instance_id=instance, location_id=p.location_id)


def address_key(value):
    return json.dumps([value['world'], value.get('instance_id'), value['location_id']], separators=(',', ':'))


def decode_state(value):
    if not isinstance(value, dict):
        raise ValueError('建筑记录必须为对象')
    if not value:
        return {}
    if type(value.get('version')) is not int or value['version'] != 1 or type(value.get('sequence')) is not int or value['sequence'] < 0:
        raise ValueError('建筑记录版本或序号无效')
    records, cultivation = value.get('records'), value.get('cultivation')
    if not isinstance(records, dict) or len(records) > 1000 or not isinstance(cultivation, dict):
        raise ValueError('建筑名录无效或过大')
    for identity, row in records.items():
        if not isinstance(row, dict) or row.get('id') != identity or row.get('type') not in TYPES:
            raise ValueError('建筑身份或类型无效')
        if row.get('status') not in STATES or type(row.get('level')) is not int or not 1 <= row['level'] <= 3:
            raise ValueError('建筑状态或等级无效')
        if not isinstance(row.get('name'), str) or not 1 <= len(row['name']) <= 40:
            raise ValueError('建筑名称无效')
        place = row.get('address', {})
        if not isinstance(place, dict) or not isinstance(place.get('world'), str) or not isinstance(place.get('location_id'), str):
            raise ValueError('建筑地址缺失')
        if place.get('instance_id') is not None and not isinstance(place['instance_id'], str):
            raise ValueError('建筑实例无效')
        owner = row.get('owner', {})
        if not isinstance(owner, dict) or owner.get('kind') not in OWNER_KINDS:
            raise ValueError('建筑所有权无效')
        if owner['kind'] != 'none' and not isinstance(owner.get('id'), str):
            raise ValueError('建筑所有者编号缺失')
        users = row.get('users', [])
        if not isinstance(users, list) or len(users) > 64 or any(
            not isinstance(u, dict) or u.get('kind') not in OWNER_KINDS-{'none'} or not isinstance(u.get('id'), str)
            for u in users):
            raise ValueError('建筑使用权无效')
        if type(row.get('public', False)) is not bool:
            raise ValueError('建筑公开权限无效')
        if row['type'] == 'scenery' and row['status'] != 'intact':
            raise ValueError('自然景观不可摧毁')
        if row.get('subtype') == 'cave':
            if row['type'] != 'artificiality' or row.get('quality') not in {'self', 'professional'}:
                raise ValueError('洞府开辟品质无效')
            if type(row.get('invested')) is not int or row['invested'] < 0:
                raise ValueError('洞府历史投入无效')
        if row['type'] == 'city' and row.get('subtype') not in {'military', 'economic', 'comprehensive'}:
            raise ValueError('城市类型无效')
        if row['type'] == 'city':
            facilities=row.get('facilities',[])
            if (not isinstance(facilities,list) or len(facilities)>row['level'] or
                    any(not isinstance(k,str) or k not in {'exchange','works','watch'} for k in facilities) or len(set(facilities))!=len(facilities)):
                raise ValueError('城市公共设施无效')
            if row.get('population', 'mixed') not in CITY_POPULATIONS:
                raise ValueError('城市居民属性无效')
            if type(row.get('development', 0)) is not int or not 0 <= row.get('development', 0) <= 12:
                raise ValueError('城市发展进度无效')
    business=value.get('city_business',{})
    if not isinstance(business,dict) or len(business)>4096:raise ValueError('城市经营记录无效')
    for identity,used in business.items():
        if (not isinstance(identity,str) or not identity or not isinstance(used,dict) or set(used)!={'last_year','expense','income'}
                or any(type(n) is not int or not 0<=n<=10**24 for n in used.values())):
            raise ValueError('城市经营账无效')
    landscapes=value.get('landscape_usage',{})
    if not isinstance(landscapes,dict) or len(landscapes)>8192:raise ValueError('景色阅历记录无效')
    for identity,used in landscapes.items():
        if (not isinstance(identity,str) or not identity or not isinstance(used,dict) or set(used)!={'ending'}
                or not isinstance(used['ending'],str) or used['ending'] not in {'0:0','0:1','1:0','1:1'}):raise ValueError('景色初次结局无效')
    usage = value.get('city_usage', {})
    if not isinstance(usage, dict) or len(usage) > 4096:
        raise ValueError('城市活动记录无效')
    limits = dict(story=1, arena=3, arena_reward=1, govern_year=10**12)
    for identity, used in usage.items():
        if not isinstance(identity, str) or not isinstance(used, dict) or not set(used) <= set(limits):
            raise ValueError('城市活动记录身份无效')
        if any(type(n) is not int or not 0 <= n <= limits[key] for key, n in used.items()):
            raise ValueError('城市活动次数无效')
    visits = value.get('visit_usage', {})
    if not isinstance(visits, dict) or len(visits) > 8192:
        raise ValueError('建筑阅历记录无效或过大')
    for identity, used in visits.items():
        if (not isinstance(identity,str) or not identity or len(identity)>512 or not isinstance(used,dict)
                or set(used) != {'insight'} or type(used['insight']) is not int or used['insight'] != 1):
            raise ValueError('建筑领悟次数无效')
    for key, identity in cultivation.items():
        row = records.get(identity)
        if not row or row.get('subtype') != 'cave' or key != address_key(row['address']):
            raise ValueError('洞府聚气引用无效')
    scene = value.get('scene')
    if scene is not None:
        if not isinstance(scene, dict) or scene.get('kind') not in {'visit', 'construction', 'management'}:
            raise ValueError('建筑会话无效')
        if type(scene.get('revision')) is not int or not 1 <= scene['revision'] <= value['sequence']:
            raise ValueError('建筑会话序号无效')
        place = scene.get('address')
        if (not isinstance(scene.get('node'), str) or not isinstance(place, dict)
                or not isinstance(place.get('world'), str) or not isinstance(place.get('location_id'), str)
                or (place.get('instance_id') is not None and not isinstance(place['instance_id'], str))):
            raise ValueError('建筑事件节点无效')
        if scene['kind'] in {'visit', 'management'} and not isinstance(scene.get('building_id'), str):
            raise ValueError('建筑会话缺少建筑编号')
        if 'result_text' in scene and (not isinstance(scene['result_text'],str) or len(scene['result_text'])>100000):
            raise ValueError('建筑事件结果无效')
        if scene['kind'] == 'construction':
            nodes = {'main'} | {f'level:{n}' for n in (1,2,3)} | {
                f'plan:{n}:{quality}' for n in (1,2,3) for quality in ('self','professional')}
            city_nodes = {'main'} | {f'city:{kind}' for kind in ('military','economic','comprehensive')} | {
                f'city:{kind}:{population}' for kind in ('military','economic','comprehensive') for population in CITY_POPULATIONS}
            if scene.get('project')=='city':nodes=city_nodes
            elif scene.get('project')=='temple':nodes={'main'}
            if scene['node'] not in nodes or scene.get('project') not in {None, 'temple', 'city'}:
                raise ValueError('建筑施工节点无效')
    return copy.deepcopy(value)

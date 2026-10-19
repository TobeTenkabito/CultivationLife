"""Local building rules and read-only initial settlement definitions."""
import copy
from .building_schema import address_key
from .content_registry import WORLD_SYSTEMS


def config():
    return WORLD_SYSTEMS['building_system']


def ensure_state(game):
    if not game.building_state:
        game.building_state.update(version=1, sequence=0, records={}, cultivation={})
    return game.building_state


def initial_rows(place):
    if place['world'] in {'lost','rift'} or place.get('instance_id') is not None:
        return []
    result = []
    for category, kind in (('cities','city'), ('scenery','scenery')):
        for spec in config().get(category, {}).get(place['world'], []):
            if spec['location_id'] != place['location_id']:
                continue
            identity = f"{kind}:{place['world']}:{spec['id']}"
            row = dict(id=identity, name=spec['name'], type=kind, subtype=spec.get('subtype','landscape'),
                level=spec.get('level',1), status='intact', address=copy.deepcopy(place), public=True, users=[],
                owner=dict(kind='background' if kind=='city' else 'none',id=identity if kind=='city' else None),
                content_id=spec['id'])
            if kind=='city':
                row.update(population=spec['population'], development=0,
                    features=['defensive_array','restrictions'] if spec['population']=='cultivator' and row['level']>=2 else [])
            else:
                row['description']=spec['description']
            result.append(row)
    return result


def city_content(row):
    return next((spec for spec in config().get('cities', {}).get(row.get('address',{}).get('world'), [])
                 if spec['id']==row.get('content_id')), {})


def may_use(row, kind, identity):
    return (row.get('status') == 'intact' and
            (row.get('public', False) or row.get('owner') == dict(kind=kind, id=identity)
             or dict(kind=kind, id=identity) in row.get('users', [])))


def display_name(row):
    return row['name'] + ('遗址' if row['type'] == 'city' and row['status'] == 'destroyed' else '')


def describe(row):
    level = row['level']
    if row['type'] == 'city':
        size = ('城郭沿街巷铺展，规模尚不算大', '内外城坊相连，已是一座大城市', '城廓连绵，远近道路在这座大都市交汇')[level-1]
        character = {
            'military': ('守卒巡行城头，城门侧重防卫', '重门要塞层层设防，城防设施占据要地', '军垒拱卫四方，驻防区沿着城郭展开'),
            'economic': ('街边铺面开张，商旅在集市间往来', '货栈与坊市相接，各地商队带来不断的买卖', '商路云集，成片市坊与货栈呈现出繁盛市景'),
            'comprehensive': ('市坊与守备各据一隅，城中生活井然', '商旅、居民与守备共同撑起这座城池', '商贸街区、居住城坊与城防设施构成庞大的都市'),
        }[row['subtype']][level-1]
        if row['status'] == 'destroyed':
            return f"你来到{display_name(row)}。昔日的城郭如今只剩断垣残壁，旧道路仍通向城中。"
        defenses = '护城大阵笼罩城郭。' if 'defensive_array' in row.get('features',[]) else ''
        restrictions = '出入要道设有禁制。' if 'restrictions' in row.get('features',[]) else ''
        population = {'cultivator':'这是一座修士之城，行馆、静室与修行者的市坊相连。',
            'mortal':'这是一座凡人之城，未入道的居民靠日常劳作维持生计。',
            'mixed':'这是一座混居之城，修士与未入道的居民在各自的街坊生活。'}[row.get('population','mixed')]
        content=city_content(row)
        flavor = content.get('flavor','') if level>=content.get('level',1) else ''
        return f"你已经到了{display_name(row)}。{size}；{character}。{population}{flavor}{defenses}{restrictions}" + ('部分街区受损，尚待修复。' if row['status']=='damaged' else '')
    if row['status']=='destroyed':
        return f"你来到{row['name']}的旧址。建筑已经毁坏，原有设施停止使用，仍可在此勘看重建。"
    if row.get('subtype') == 'cave':
        craft = '岩壁与聚气布置由你亲手完成，略显朴拙' if row['quality']=='self' else '营造匠师细整了岩室与聚气布局，气息流转平稳'
        size = ('一间安静的石室依山开辟', '数间静室围绕聚气中枢布置', '内外静室与聚气阵室已有完整格局')[level-1]
        return f"你来到{display_name(row)}。{size}；{craft}。"
    if row.get('subtype') == 'temple':
        return (f"你来到{row['name']}。" + ('小院清静，檐下供着香炉', '殿堂渐具规模，香客沿庭院往来', '殿宇庄严，钟声越过层层院落')[level-1]
                + f"；此处已有约{int(row.get('followers',0))}位信众。")
    return f"你来到{display_name(row)}。{row.get('description', '')}"


def qi_multiplier(player):
    state = getattr(player, '_building_context', {})
    place = dict(world=player.world, instance_id=None, location_id=player.location_id)
    if (player.world in {'lost', 'rift'}
            or getattr(player, '_building_guixu_context', {}).get('player_session')
            or getattr(player, '_building_trial_context', {}).get('active')):
        return 1.0
    identity = state.get('cultivation', {}).get(address_key(place))
    row = state.get('records', {}).get(identity)
    if not row or row.get('address') != place or not may_use(row, 'player', getattr(player, '_building_owner_id', '')):
        return 1.0
    return 1.0 + float(config()['cave_bonus'][row['quality']][row['level']-1])

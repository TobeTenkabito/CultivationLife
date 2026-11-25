"""Authored places and keepsakes, compiled with the original building catalogue."""
from .definition_data import definition as _content_definition
import copy


# Each pair is distributed onto existing map addresses, never a new travel route.
CITY_SEEDS = _content_definition(__name__, "CITY_SEEDS")


# title, setting, first two actions, their discoveries, final actions, four endings.
SCENERY_SEEDS = _content_definition(__name__, "SCENERY_SEEDS")


def expand(config):
    """Compile deterministic native definitions; no runtime IDs or RNG."""
    from .soul_secret_content import scenery_seeds
    for world, seeds in CITY_SEEDS.items():
        for identity,name,location,kind,population,flavor,title,body,a,ar,b,br in seeds:
            config['cities'][world].append(dict(id=identity,name=name,location_id=location,subtype=kind,
                population=population,level=1,flavor=flavor,
                audience=f'{name}的值房向街开着窗。有人抱着旧册，有人提着刚买的菜，轮到谁便坐下慢慢说。'+flavor,
                rumor=flavor+'街上的人说起近来的小事，语气里有只有住在这里才会有的熟稔。',
                arena=f'{name}的试场设在远离民居的空地，台边备有止斗铃，胜负不许延伸到街巷。',
                story=dict(title=title,body=body,choices=[[a,ar],[b,br]])))
    for world, seeds in SCENERY_SEEDS.items():
        for identity,name,location,description,title,body,actions,discoveries,finals,endings,relic in seeds:
            config['scenery'][world].append(dict(id=identity,name=name,location_id=location,description=description,
                exploration=dict(title=title,body=body,actions=copy.deepcopy(actions),discoveries=copy.deepcopy(discoveries),
                    finals=copy.deepcopy(finals),endings=copy.deepcopy(endings),relic_id=f'landscape_{identity}' if relic else None)))
    config['scenery']['human'].extend(scenery_seeds())
    config['city_facilities'] = _content_definition(__name__, "expand_config_city_facilities")
    config['city_operation'] = dict(cost_units=600,receipt_units=dict(military=800,economic=1000,comprehensive=900),aid_units=300)


def relic_items():
    return [dict(id=f'landscape_{s[0]}',name=s[-1],description=f'在{s[1]}的「{s[4]}」中取得的独有纪念物。没有主动或被动属性，不是炼器材料。每处地点每人生最多取得一件；转赠、出售或遗失不补发。',tags=['quest','landscape_keepsake'])
            for rows in SCENERY_SEEDS.values() for s in rows if s[-1]]

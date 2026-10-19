"""Read projections over original estates, Buddhist sites and fixed buildings."""
from ..building_schema import address
from ..building_rules import initial_rows
from .buddhist.rules import buddhist_config
from .economy.enterprise_state import estates, owner_allowed
from .economy.enterprise_rules import KINDS


def rows_at(game,place):
    if place['world'] in {'lost','rift'} or place.get('instance_id') is not None:
        return []
    stored=game.building_state.get('records',{})
    result=[]
    for seed in initial_rows(place):
        row=stored.get(seed['id'],seed)
        # Content updates must not move a previously materialized settlement.
        if row['address']==place:result.append(row)
    identities={row['id'] for row in result}
    result.extend(row for row in stored.values() if row['address']==place and row['id'] not in identities)
    if buddhist_config().get('enabled'):
        site=game.buddhist_state.get('worlds',{}).get(place['world'],{}).get('sites',{}).get(place['location_id'],{})
        active=int(site.get('temple',0))
        level=active or int(site.get('temple_ruin_level',0))
        if level:
            result.append(dict(id=f"temple:{place['world']}:{place['location_id']}",name=('清修小庵','弘法禅院','庄严古刹')[level-1],
                type='artificiality',subtype='temple',level=level,status='intact' if active else 'destroyed',address=place,
                owner=dict(kind='player',id=game.id),users=[],public=False,followers=site.get('followers',0),
                dependency='official.buddhist-dharma'))
    for estate in estates(game).values():
        if estate['owner_kind']=='background' or (estate['world'],estate['location'])!=(place['world'],place['location_id']):
            continue
        permitted=owner_allowed(game,estate['owner_kind'],estate['owner_id'],estate['world'])
        result.append(dict(id='estate:'+estate['id'],name=KINDS[estate['kind']],type='industry',subtype=estate['kind'],
            level=int(estate['level']),status=estate.get('building_status','intact'),address=place,
            owner=dict(kind=estate['owner_kind'],id=estate['owner_id']),
            users=[dict(kind='player',id=game.id)] if permitted else [],public=False,source_id=estate['id'],
            description='此处正在经营。' if estate.get('enabled') else '此处暂未开工。'))
    return result


def local_rows(game):
    return rows_at(game,address(game))

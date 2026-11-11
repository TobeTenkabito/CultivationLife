"""Shared ordinary-world routes for original people; no authority or content rules."""
from ..relationship_records import find_person
from ..npc_custody import is_free
from ..spatial_people import instance_of


def routes(maps, people, destination, origin):
    result=[]
    for n in people:
        source=n.location_id or origin
        if source==destination:path,years=[source],0
        else:
            plan=maps.travel_plan(n.world,source,destination,n.realm_index)
            if plan.status!='ok':raise ValueError('实际参战成员没有合法的同界行军道路')
            path,years=list(plan.route),plan.years
        result.append(dict(person_id=n.id,origin=source,destination=destination,route=path,
                           years=years,remaining=years,phase='outbound' if years else 'stationed'))
    return result


def valid(game, unit, world):
    n=find_person(game,unit['person_id'])
    expected=unit['destination'] if unit['phase']=='stationed' else unit['origin']
    return n if (n and is_free(n) and n.world==world and n.location_id==expected
        and ('organization' not in unit or n.faction_id==unit['organization'])
        and not instance_of(game,n.id) and n.id not in game.intrigue_state.get('npc_prisons',{})) else None


def advance(game, unit, world):
    if unit['phase'] in {'home','lost'} or game.player.age<=unit['last_year']:return
    unit['last_year']=game.player.age
    if not valid(game,unit,world):unit['phase']='lost';return
    if unit['phase'] in {'outbound','returning'}:
        unit['remaining']=max(0,unit['remaining']-1)
        if not unit['remaining']:
            n=find_person(game,unit['person_id'])
            n.location_id=unit['destination']
            unit['phase']='home' if unit['phase']=='returning' else 'stationed'


def recall(game, maps, unit, world):
    if unit['phase'] in {'home','lost','returning'}:return
    npc=valid(game,unit,world)
    if not npc:unit['phase']='lost';return
    if unit['phase']=='outbound':
        elapsed=unit['years']-unit['remaining']
        # Original location remains the departure point until arrival. Retrace
        # the distance already covered before releasing this person.
        unit.update(destination=unit['origin'],remaining=elapsed,years=elapsed,
                    route=list(reversed(unit['route'])),phase='returning',last_year=game.player.age)
    else:
        journey=routes(maps,[npc],unit['home'],unit['home'])[0]
        unit.update(journey,phase='returning',last_year=game.player.age)
    if not unit['remaining']:unit['phase']='home'

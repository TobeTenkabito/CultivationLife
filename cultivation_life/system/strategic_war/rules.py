"""Pure capability and commitment queries. No implicit world preparation."""
from ...content_registry import RACE_DEFINITIONS
from ...npc_custody import is_free
from ...spatial_people import instance_of
from ...person_assignments import research_assignment
from ..faction_geography import faction_site

SIDES = ('attacker', 'defender')
WORLDS = {'spirit', 'true_demon'}
OPEN = {'mobilizing', 'active', 'armistice', 'settling'}


def organizations(game, world):
    pool = dict(game.sects)
    if game.family:
        pool[game.family.id] = game.family
    return [s for s in pool.values() if s.world == world and not s.extinct and s.kind in {'sect', 'family'}]


def ref(org):
    return {'kind': org.kind, 'id': org.id}


def committed_org(game, row, commitment):
    return next((o for o in organizations(game,row['world']) if ref(o)==commitment['org']
                 and o.allegiance_race==row[commitment['side']]),None)


def representatives(deps, game, row, commitment):
    org=committed_org(game,row,commitment)
    return [n for n in deps.members(game,org) if is_free(n) and n.world==row['world']
            and not instance_of(game,n.id) and not deps.imprisoned(game,n.id)] if org else []


def owns(deps, game, org):
    p = game.player
    if not p.alive or p.world != org.world or p.imprisonment or p.ghost_captor:
        return False
    if game.family and game.family.id == org.id:
        return bool(game.family.founded_by_player or deps.has_family_voice(game))
    return p.faction_id == org.id and deps.has_sect_voice(game)


def army(deps, game, org):
    # Also exclude rosters of legacy campaigns: one physical person, one task.
    occupied = {n for w in game.wars if w.get('status') in {'active', 'peace_ready', 'withdrawing'}
                for roster in w.get('roster', {}).values() for n in roster}
    people = {n.id: n for n in deps.members(game, org)}
    return sorted((n for n in people.values() if n.id not in occupied and is_free(n)
                   and n.world == org.world and not instance_of(game, n.id)
                   and not research_assignment(game, n.id) and not deps.imprisoned(game, n.id)),
                  key=lambda n: (-deps.power(n), n.id))[:24]


def local_races(world):
    return [r for r, definition in RACE_DEFINITIONS.items() if world in definition.get('worlds', [])]


def site(org):
    return faction_site(org, persist=False)['id']


def routes(deps, game, people, destination, origin):
    result=[]
    for n in people:
        source=n.location_id or origin
        if source==destination:
            path,years=[source],0
        else:
            plan=deps.maps.travel_plan(n.world,source,destination,n.realm_index)
            if plan.status!='ok':
                raise ValueError('实际参战成员没有合法的同界行军道路')
            path,years=list(plan.route),plan.years
        result.append(dict(person_id=n.id,origin=source,destination=destination,route=path,
                           years=years,remaining=years,phase='outbound' if years else 'stationed'))
    return result

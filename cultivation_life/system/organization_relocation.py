"""Same-world headquarters votes. Fixed assets and player addresses stay authoritative."""
import hashlib
from ..content_registry import RACE_DEFINITIONS, WORLD_SYSTEMS
from ..npc_custody import is_free
from ..person_assignments import research_assignment
from .faction_geography import faction_site
from .territory.rules import enabled
from .map_definition import MapContentError

def race_site(game,maps,world,identity):
    saved=game.economy_v2.get('organization_sites',{}).get('race_sites',{}).get(f'{world}:{identity}')
    if saved and maps.location(world,saved): return saved
    safe=[r for r in maps.worlds[world]['locations'] if not r.get('min_realm_index',0)]
    if not safe: raise ValueError('该界没有可用驻地')
    index=int.from_bytes(hashlib.sha256(f'{world}:{identity}'.encode()).digest()[:4],'big')%len(safe)
    return safe[index]['id']

def entity_for(game,kind,identity):
    return game.family if kind=='family' and game.family and game.family.id==identity else game.sects.get(identity) if kind=='sect' else None

def validate(game,maps,kind,identity,destination,*,world=None,influence_book=None):
    entity=entity_for(game,kind,identity)
    world=world or (entity.world if entity else game.player.world)
    if kind=='race':
        if identity not in RACE_DEFINITIONS or world not in RACE_DEFINITIONS[identity].get('worlds',[]): raise ValueError('该族在本界没有驻地')
        current=race_site(game,maps,world,identity)
    elif not entity or entity.extinct or entity.kind=='institution': raise ValueError('该组织不能迁址')
    else: current=faction_site(entity,persist=False)['id']
    try:site=maps.location(world,destination)
    except MapContentError as error:raise ValueError('迁址只能选择同界的主界面地点') from error
    if not site or site.get('min_realm_index',0): raise ValueError('迁址只能选择同界无境界门槛的地图')
    if current==destination: raise ValueError('目标就是现有驻地')
    if kind=='sect':
        from .territory.state import validate_projection
        if enabled(): validate_projection(game,maps,entity,destination,book=influence_book)
    return entity,world,current

def relocate(game,maps,kind,identity,destination,*,forced=False,world=None):
    if forced:
        # A peace settlement may evacuate to any safe same-world map. It cannot
        # jump to a gated map or copy fixed assets, even when no border remains.
        entity=entity_for(game,kind,identity)
        if not entity or entity.extinct: raise ValueError('目标宗门已不存在')
        world=entity.world;current=faction_site(entity,persist=False)['id']
        site=maps.location(world,destination)
        if not site or site.get('min_realm_index',0) or current==destination: raise ValueError('强制迁址目标无效')
    else: entity,world,current=validate(game,maps,kind,identity,destination,world=world)
    if kind=='race':
        game.economy_v2.setdefault('organization_sites',{}).setdefault('race_sites',{})[f'{world}:{identity}']=destination
    else:
        from .war.requirements import deployed_ids
        deployed={n for w in game.wars if w.get('status') in {'active','peace_ready'} for side in ('attacker','defender') for n in deployed_ids(w,side)}
        entity.location_id=destination
        for npc in entity.npcs:
            if is_free(npc) and npc.world==world and npc.id not in deployed and not research_assignment(game,npc.id) and npc.location_id in {None,current}:
                npc.location_id=destination
        # Remove geographic demand carry-over, retaining the original treasury.
        row=game.economy_v2.get('organizations',{}).get(f'organization:{kind}:{identity}')
        if row:
            for name in ('demand_credit','cultivation_support','maintenance_support','breakthrough_support','longevity_support'): row[name]={}
            row['supply_budget_credit']=0
        if kind=='sect' and enabled():
            from .territory.state import ensure
            book=ensure(game,maps,world)
            old=book.get(current,{}).get(identity)
            if old:
                foreign=[k for k in book.get(current,{}) if k!=identity and game.sects.get(k) and game.sects[k].location_id!=current]
                if len(foreign)>=3 or maps.location(world,current).get('min_realm_index',0):book[current].pop(identity,None)
                else:old['value']=min(60,old['value'])
    if enabled():
        from .territory.state import refresh_bonuses
        refresh_bonuses(game,world)
    return f'{maps.location(world,current)["name"]} → {maps.location(world,destination)["name"]}'

def candidates(game,kind,identity,world):
    from .war.requirements import deployed_ids
    deployed={n for w in game.wars if w.get('status') in {'active','peace_ready'} for side in ('attacker','defender') for n in deployed_ids(w,side)}
    entity=entity_for(game,kind,identity)
    if entity: return [n for n in entity.npcs if is_free(n) and n.world==world and n.id not in deployed and not research_assignment(game,n.id)]
    people={n.id:n for s in game.sects.values() for n in s.npcs}
    if game.family: people.update((n.id,n) for n in game.family.npcs)
    for source in (game.world_npcs,game.notable_npcs,game.relationship_npcs): people.update(source)
    return [n for n in people.values() if is_free(n) and n.world==world and n.race==identity and n.id not in deployed and not research_assignment(game,n.id)]

def base_vote(game,maps,kind,identity,destination,rng):
    from .organization_heritage import decision
    entity,world,current=validate(game,maps,kind,identity,destination)
    p=game.player
    if not p.alive or world!=p.world or (kind=='race' and (p.allegiance_race or p.race)!=identity) or (entity and not decision(game,entity)):
        raise ValueError('你没有该组织在本界的迁址决策权')
    threshold=(WORLD_SYSTEMS.get('intrigue_dlc',{}).get('decision_thresholds',{}) or {}).get(kind,8 if kind=='race' else 4 if kind=='sect' else 3)
    if kind=='race' and p.realm_index<threshold: raise ValueError('当前境界不足以提议种族迁址')
    ballots=[dict(id='player',name=p.name,vote=True)]
    for n in candidates(game,kind,identity,world):
        if n.realm_index>=threshold: ballots.append(dict(id=n.id,name=n.name,vote=rng.random()<max(.3,min(.85,.6+n.affinity/400))))
    yes=sum(r['vote'] for r in ballots);passed=yes>len(ballots)/2
    result=dict(kind=kind,identity=identity,world=world,source=current,target=destination,year=p.age,yes=yes,total=len(ballots),passed=passed,votes=ballots)
    if passed: result['message']=relocate(game,maps,kind,identity,destination)
    s=game.economy_v2.setdefault('organization_sites',{})
    s['votes']=(s.get('votes',[])+[result])[-20:]
    return result

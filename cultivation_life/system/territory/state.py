"""Bounded territorial holdings, with HQ and fixture floors derived from originals."""
from ..faction_geography import faction_site
from .rules import enabled

def state(game):
    return game.intrigue_state.setdefault('territory', dict(schema_version=1, holdings={}, adopted={}, history=[], ai_cursor=0))

def sects(game, world):
    return {s.id:s for s in game.sects.values() if s.world == world and not s.extinct and s.kind == 'sect'}

def array_owners(game, maps, world):
    from ..teleport_sites import arrays
    suppressed = game.intrigue_state.get('territory', {}).get('suppressed_arrays', {})
    return {loc:r['owner_id'] for loc,r in arrays(game,maps,world).items()
            if not suppressed.get(f'{world}:{loc}:{r["owner_id"]}')}

def snapshot(game, maps, world):
    """Read-only projection, including unadopted saves. No RNG or lazy state writes."""
    owners = sects(game,world)
    saved = game.intrigue_state.get('territory',{})
    book = {loc:{identity:dict(row) for identity,row in rows.items() if identity in owners}
            for loc,rows in saved.get('holdings',{}).get(world,{}).items() if maps.location(world,loc)}
    headquarters={identity:faction_site(s,persist=False)['id'] for identity,s in owners.items()}
    for identity,s in owners.items():
        loc = headquarters[identity]
        book.setdefault(loc,{}).setdefault(identity,dict(value=100.,outpost=False,policy=''))
    arrays = array_owners(game,maps,world)
    for loc,identity in arrays.items():
        site = maps.location(world,loc)
        if identity not in owners or not site or site.get('min_realm_index',0): continue
        if identity not in book.get(loc,{}) and world in saved.get('adopted',{}): continue
        book.setdefault(loc,{}).setdefault(identity,dict(value=40.,outpost=False,policy=''))
    for loc,rows in book.items():
        for identity,row in rows.items():
            floor = 100 if headquarters[identity] == loc else max(50 if row.get('outpost') else 0,40 if arrays.get(loc)==identity else 0)
            row['floor'] = floor
            row['array'] = arrays.get(loc)==identity
            row['value'] = min(100.,max(float(row.get('value',0)),floor))
    return {loc:rows for loc,rows in book.items() if rows}

def ensure(game,maps,world):
    if not enabled(): return {}
    s = state(game)
    if world not in s['adopted']:
        # Fixed arrays belong to their original owner, even if another sect is
        # founded or dissolved later. Adoption does not create or copy assets.
        from ..teleport_sites import arrays
        sites=game.economy_v2.setdefault('organization_sites',{}).setdefault('initial_arrays',{})
        for loc,row in arrays(game,maps,world).items():
            if maps.location(world,loc).get('teleport_array'):
                sites.setdefault(f'{world}:{loc}',row['owner_id'])
        s['holdings'][world] = snapshot(game,maps,world)
        s['adopted'][world] = game.player.age
    # HQ is an invariant; extinction is reflected before any further action.
    owners=sects(game,world); book=s['holdings'].setdefault(world,{})
    for loc in list(book):
        book[loc]={k:r for k,r in book[loc].items() if k in owners}
        if not book[loc]: del book[loc]
    for identity,entity in owners.items():
        loc=faction_site(entity)['id']
        book.setdefault(loc,{}).setdefault(identity,dict(value=100.,outpost=False,policy=''))['value']=100.
    return book

def note(game,message,world=None):
    s=state(game)
    s['history']=(s['history']+[dict(year=game.player.age,text=message,world=world or game.player.world)])[-40:]

def validate_projection(game,maps,entity,location,*,existing=False,book=None,occupies_slot=True):
    if not enabled(): raise ValueError('地方影响力须开启《明争暗斗：合纵连横》')
    if not entity or entity.extinct or entity.kind!='sect': raise ValueError('该势力不能投放宗门影响力')
    site=maps.location(entity.world,location)
    if not site or (site.get('min_realm_index',0) and location != entity.location_id):
        raise ValueError('有境界门槛的地图不能扩张、建据点或迁入；现有驻地保留')
    if book is None:book=snapshot(game,maps,entity.world)
    if entity.id in book.get(location,{}): return
    if existing: raise ValueError('当地没有己方影响力')
    # Existing co-located HQs are preserved. New discretionary claims still
    # cannot flood a capital and break capacity when that capital relocates.
    if occupies_slot and len(book.get(location,{}))>=3:
        raise ValueError('当地已有三个宗门，须先移除一方影响力')
    if not any(entity.id in book.get(neighbor,{}) for neighbor,_ in maps._graphs[entity.world][location]):
        raise ValueError('只能沿己方影响力边界连续扩张')

def clear_faction(game,identity):
    if not enabled(): return
    s=state(game)
    for book in s['holdings'].values():
        for loc in list(book):
            book[loc].pop(identity,None)
            if not book[loc]: del book[loc]
    refresh_bonuses(game)

def refresh_bonuses(game,world=None):
    """Derived production projection, refreshed only when geography changes."""
    if not enabled():return
    for row in game.economy_v2.get('organizations',{}).values():
        if row['kind']=='sect' and (world is None or row['world']==world):
            row['territory_production_bonus']=resource_bonus(game,row['world'],row['identity'])

def resource_bonus(game,world,identity):
    """Regional supply relationships improve existing production, capped at 20%."""
    if not enabled():return 0.
    from .rules import POLICIES, permits
    entity=game.sects.get(identity)
    if not entity or entity.extinct or entity.kind!='sect' or entity.world!=world:return 0.
    result=0.
    for location,rows in game.intrigue_state.get('territory',{}).get('holdings',{}).get(world,{}).items():
        if location==entity.location_id or identity not in rows:continue
        r=rows[identity];value=max(0,r['value']);total=sum(max(0,row['value']) for row in rows.values())
        policy=POLICIES.get(r.get('policy')) if permits(r.get('policy'),value) else None
        result+=.025*(value/100)*(value/max(1,total))*(policy['yield_factor'] if policy else 1)
    return min(.2,result)

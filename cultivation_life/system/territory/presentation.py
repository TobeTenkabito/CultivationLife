"""Read-only local geography and valid decision previews."""
from ...content_registry import WORLD_SYSTEMS, RACE_DEFINITIONS
from ..organization_heritage import decision
from ..organization_relocation import race_site, validate as validate_relocation
from .rules import enabled, band, POLICIES, permits, costs
from .state import snapshot, validate_projection, resource_bonus
from . import anchors

def augment(game,maps,data):
    world=game.player.world
    if WORLD_SYSTEMS['world_profiles'].get(world,{}).get('tier') not in {1,2,3}:
        return data  # Instance-local society never exposes outside geography.
    book=snapshot(game,maps,world) if enabled() or anchors.branches(game, world) else {}
    owners=anchors.owners(game, world)
    for loc in data['locations']:
        rows=book.get(loc['id'],{});total=sum(r['value'] for r in rows.values())
        loc['influences']=[dict(id=identity,name=owners[identity].name,value=round(r['value'],1),
            share=round(r['value']/max(1,total)*100,1),band=band(r['value']),outpost=bool(r.get('outpost')),
            headquarters=owners[identity].world==world and owners[identity].location_id==loc['id'],floor=r.get('floor',0),policy=r.get('policy',''),
            policy_name=POLICIES.get(r.get('policy'),{}).get('name','常态巡守'),owned=game.player.faction_id==identity or bool(game.family and game.family.id==identity))
            for identity,r in sorted(rows.items(),key=lambda pair:(-pair[1]['value'],pair[0]))]
    plans=[]
    for kind,entity in [('sect',game.sects.get(game.player.faction_id)),('family',game.family)]:
        if not entity or entity.extinct or entity.world!=world:continue
        can=decision(game,entity)
        candidates=[]
        for loc in data['locations']:
            try:validate_relocation(game,maps,kind,entity.id,loc['id'],influence_book=book)
            except ValueError:continue
            candidates.append(dict(id=loc['id'],name=loc['name']))
        plans.append(dict(kind=kind,id=entity.id,name=entity.name,current=entity.location_id,can_propose=can,destinations=candidates))
    race=game.player.allegiance_race or game.player.race
    if world in RACE_DEFINITIONS.get(race,{}).get('worlds',[]):
        plans.append(dict(kind='race',id=race,name=RACE_DEFINITIONS[race]['name'],current=race_site(game,maps,world,race),
                          can_propose=game.player.realm_index>=8,destinations=[dict(id=l['id'],name=l['name']) for l in data['locations'] if not l.get('min_realm_index',0) and l['id']!=race_site(game,maps,world,race)]))
    data['organization_relocation']=plans
    entity=game.sects.get(game.player.faction_id)
    if entity and (entity.world!=world or entity.extinct or entity.kind!='sect'):
        entity=None
    own=[];harassment=[]
    if enabled() and entity and entity.world==world and not entity.extinct and entity.kind=='sect':
        from .actions import construction_plan
        for loc in data['locations']:
            try:validate_projection(game,maps,entity,loc['id'],book=book,occupies_slot=False)
            except ValueError:pass
            else:harassment.append(loc['id'])
            try:validate_projection(game,maps,entity,loc['id'],book=book)
            except ValueError:continue
            row=book.get(loc['id'],{}).get(entity.id,{})
            own.append(dict(id=loc['id'],name=loc['name'],value=round(row.get('value',0),1),outpost=bool(row.get('outpost')),
                can_build=game.player.location_id==loc['id'] and not row.get('outpost'),
                construction=construction_plan(game,maps,entity,loc['id']) if game.player.location_id==loc['id'] else None,
                policies=[dict(id=p,name=d['name']) for p,d in POLICIES.items() if row and permits(p,row['value'])],
                rivals=[dict(id=k,name=owners[k].name) for k in book.get(loc['id'],{}) if k!=entity.id]))
    row=game.economy_v2.get('organizations',{}).get(f'organization:sect:{entity.id}',{}) if entity else {}
    data['territory']=dict(enabled=enabled(),owner_id=entity.id if entity else None,can_propose=bool(entity and entity.kind=='sect' and decision(game,entity)),
        locations=own,harassment_locations=harassment,policies=POLICIES,history=[r for r in game.intrigue_state.get('territory',{}).get('history',[]) if r['world']==world][-8:],
        upkeep_due=row.get('territory_due',0),upkeep_paid=row.get('territory_paid',0),income=row.get('territory_income',0),period_years=row.get('territory_years',0),production_bonus=resource_bonus(game,world,entity.id) if entity else 0.,action_fee=costs(world)['action'])
    return data

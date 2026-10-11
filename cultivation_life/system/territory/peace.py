"""Territorial objectives and peace settlements share the original war ledger."""
from .rules import enabled, TERMS
from .state import snapshot, ensure, state, sects, note

def targets(game,maps,world,identity):
    if not enabled():return []
    entity=game.sects.get(identity)
    if not entity or entity.extinct or entity.kind!='sect' or entity.world!=world:return []
    return [dict(id=loc,name=maps.location(world,loc)['name'],value=round(rows[identity]['value'],1),outpost=bool(rows[identity].get('outpost')),headquarters=loc==entity.location_id)
            for loc,rows in snapshot(game,maps,world).items() if identity in rows]

def evacuation(game,maps,entity,location):
    book=snapshot(game,maps,entity.world)
    safe=[r['id'] for r in maps.worlds[entity.world]['locations'] if r['id']!=location and not r.get('min_realm_index',0)
          and (entity.id in book.get(r['id'],{}) or len(book.get(r['id'],{}))<3)]
    if not safe:raise ValueError('本界没有符合容量限制的安全迁址目标')
    return min(safe,key=lambda loc:(entity.id not in book.get(loc,{}),len(book.get(loc,{})),loc))

def validate(game,maps,world,identity,term,location):
    if term not in TERMS or not enabled():raise ValueError('该地方条款须开启合纵连横 DLC')
    row=next((r for r in targets(game,maps,world,identity) if r['id']==location),None)
    if not row:raise ValueError('目标宗门在指定地图没有影响力')
    if term=='destroy_outpost' and not row['outpost']:raise ValueError('目标宗门在当地没有据点')
    if term=='remove_influence' and row['headquarters']:evacuation(game,maps,game.sects[identity],location)
    return row

def apply(game,maps,world,identity,term,location):
    row=validate(game,maps,world,identity,term,location)
    entity=game.sects[identity]
    book=ensure(game,maps,world)
    if term=='destroy_outpost':
        book[location][identity]['outpost']=False
        book[location][identity]['floor']=0
        message=f'{entity.name}在{row["name"]}的据点被捣毁'
    else:
        if row['headquarters']:
            from ..organization_relocation import relocate
            relocate(game,maps,'sect',identity,evacuation(game,maps,entity,location),forced=True)
        book[location].pop(identity,None)
        state(game).setdefault('suppressed_arrays',{})[f'{world}:{location}:{identity}']=True
        game.economy_v2.setdefault('organization_sites',{}).setdefault('retired_arrays',{})[f'{world}:{location}:{identity}']=True
        built=game.economy_v2.get('teleport_arrays',{}).get(f'{world}:{location}')
        if built and built.get('owner_id')==identity:game.economy_v2['teleport_arrays'].pop(f'{world}:{location}')
        message=f'{entity.name}退出{row["name"]}'+('，驻地强制迁移' if row['headquarters'] else '')
    note(game,message,world)
    from .state import refresh_bonuses
    refresh_bonuses(game,world)
    return message

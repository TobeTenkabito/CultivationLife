"""Shared-site organizations cannot each claim the whole local sales capacity."""
import math


def quota(game,market,owner,item,room):
    rows=game.economy_v2.get('organizations',{})
    peers=sum(e.world==market['world'] and e.location_id==market['location'] and not e.extinct and e.kind!='institution'
        and f'organization:{"family" if e is game.family else "sect"}:{e.id}' in rows
        for e in [*game.sects.values(),*([game.family] if game.family else [])])
    book=market.get('production_allocation',{})
    delivered=book.get('items',{}).get(item,{}) if book.get('year')==game.player.age else {}
    opening=room+sum(delivered.values())
    return max(0,min(room,math.floor(opening/max(1,peers))-delivered.get(owner,0)))


def record(game,market,owner,item,quantity):
    book=market.get('production_allocation',{})
    if book.get('year')!=game.player.age:
        book=dict(year=game.player.age,items={});market['production_allocation']=book
    allocations=book['items'].setdefault(item,{})
    allocations[owner]=allocations.get(owner,0)+quantity

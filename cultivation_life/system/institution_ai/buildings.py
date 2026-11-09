"""Explicit local institutional reconstruction authority; never a player move."""
from dataclasses import dataclass
from .rules import person_reason

@dataclass(frozen=True)
class BuildingActor:
    world:str
    location:str
    owner_kind:str
    owner_id:str
    person:str
    assignment:str

def authorized(game,row,actor):
    if not isinstance(actor,BuildingActor):return False
    if row['address']!=dict(world=actor.world,location_id=actor.location,instance_id=None):return False
    if row.get('subtype')=='temple':return False
    if person_reason(game,actor.person,actor.world,actor.location,assignment=actor.assignment):return False
    return row['owner']==dict(kind=actor.owner_kind,id=actor.owner_id)

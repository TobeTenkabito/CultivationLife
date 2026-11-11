"""Original qualified local recruits, shared by local and central appointment."""
from . import rules
from .. import institution_authority as authority
from ...relationship_records import find_person

def candidates(game,row):
    result=[]
    from ..war.occupancy import busy
    for entry in rules.eligible_people(game,row):
        npc=find_person(game,entry['id']);org=game.sects.get(npc.faction_id)
        if authority.responsibilities(game,npc.id) or org and busy(game,org,exclude_garrison=row['id'],individual_service=True):continue
        result.append(dict(entry,rate=rules.config().get('military',{}).get('annual_service',1000)*(1+max(0,npc.realm_index-9))))
    return result


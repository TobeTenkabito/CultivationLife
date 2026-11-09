"""Pure, bounded evaluations shared by institutions and optional content."""
import hashlib
import json
from ...relationship_records import find_person
from ...npc_custody import is_free
from ..faction_geography import person_site

POLICIES={'balanced':'均衡经营','supply':'补足供给','repair':'修缮优先','teaching':'传习优先'}

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()[:24]

def state(game):return game.economy_v2.get('institution_agendas',{})
def records(game):return state(game).get('scopes',{})
def record(game,key):return records(game).get(key,{})
def ensure(game,key):
    root=game.economy_v2.setdefault('institution_agendas',{'sequence':0,'scopes':{}})
    return root['scopes'].setdefault(key,dict(policy='balanced',limit=0,automatic=False,delegate=None,proposals=[],history=[],revision=0,last_observed=-1,last_tick=-1))

def person_reason(game,identity,world,location,*,assignment=None):
    npc=find_person(game,identity)
    if not npc or not npc.alive or not is_free(npc):return '原执行人死亡、缺席或受拘束'
    if identity in game.intrigue_state.get('npc_prisons',{}):return '原执行人正在接受机构拘管'
    if npc.world!=world or person_site(game,npc)!=location or getattr(npc,'instance_id',None):return '原执行人不在约定普通地点'
    from ...spatial_people import instance_of
    if instance_of(game,identity):return '原执行人处于独立空间'
    if any((n.get('npc_id') or n.get('id'))==identity for n in game.player.party):return '执行人正在随行'
    from ...person_assignments import research_assignment
    occupied=research_assignment(game,identity)
    if occupied and occupied.get('id')!=assignment:return '原人物已有其他任务占用'
    return ''

def priority(offer,policy):
    return int(offer.get('urgency',0))+ (30 if offer['category']==policy else 0)

def choose(offers,policy,budget):
    valid=[o for o in offers if not o.get('reason') and 0<o['budget']<=budget]
    return min(valid,key=lambda o:(-priority(o,policy),o['budget'],o['key'])) if valid else None


def proposals(offers,people,policy,budget,year):
    """Shared bounded proposal generation; content adapters supply original facts only."""
    pending=list(offers);result=[]
    for person in people[:3]:
        offer=choose(pending,policy,budget)
        if not offer:break
        result.append(dict(key=offer['key'],name=offer['name'],proposer=person,observed=year,
                           budget=offer['budget'],category=offer['category']))
        pending=[o for o in pending if o['key']!=offer['key']]
    return result

def contract_score(*,price,reference,reliability,ability,obligations,relation=0):
    """No random reroll; facts must come from the adapter's original records."""
    if price<0 or reference<=0 or ability<=0 or obligations:return None
    return round(min(40,40*price/reference)+max(0,min(40,reliability))+min(20,ability)+max(-10,min(10,relation)),2)

def token(game,scope,offers):
    return digest([scope,record(game,scope['id']),offers,game.player.age,game.player.world,game.player.location_id,
                   game.pending_event,game.active_trial])

"""NPC learning and slots refer to the existing person, never a combat clone."""
import copy
from ..content_registry import TECHNIQUE_CATALOG
from ..models import Technique
from ..npc_technique_schema import normalize
from ..rules import can_practice_technique
from .combat.npc_lifecycle import read


def levels(npc):
    return normalize(read(npc,'technique_levels',{}),read(npc,'main_technique_id'),read(npc,'main_technique_level',1),read(npc,'family_traits',{}))


def resolve(game, identity):
    t=TECHNIQUE_CATALOG.get(identity)
    if t:
        return copy.deepcopy(t)
    library=getattr(game,'authored_techniques',{})
    row=library.get('own',{}).get(identity) or library.get('inherited',{}).get(identity)
    if row:
        return Technique(**copy.deepcopy(row['technique']))
    definition=game.doctrine_state.get('definitions',{}).get(str(identity).split(':manual:')[0],{})
    row=next((r for r in definition.get('manuals',[]) if r['id']==identity),None)
    return Technique(**copy.deepcopy(row)) if row else None


def learn(npc, book, level=1, slot=None):
    from ..authored_technique_schema import integer
    integer(level,1,9,'人物功法等级')
    facts=levels(npc)
    facts[book.id]=max(facts.get(book.id,1),level)
    def write(key,value):
        if isinstance(npc,dict):npc[key]=value
        else:setattr(npc,key,value)
    write('technique_levels',facts)
    if slot=='main' or book.id==read(npc,'main_technique_id'):
        write('main_technique_id',book.id);write('main_technique_level',facts[book.id])
    elif slot:
        slots=dict(read(npc,'technique_slots',{}));slots[slot]=book.id;write('technique_slots',slots)
    if slot and (book.id.startswith('TECH_AUTHORED_') or read(npc,'family_traits',{}).get('authored_combat_bonuses',{}).get(slot)):
        from ..rules import technique_scale
        traits=read(npc,'family_traits',{})
        bonuses=traits.setdefault('authored_combat_bonuses',{})
        learned=copy.copy(book);learned.level=facts[book.id]
        bonus=learned.combat_bonus*technique_scale(learned) if book.id.startswith('TECH_AUTHORED_') else 0
        if bonus!=bonuses.get(slot,0):
            write('family_combat_bonus',read(npc,'family_combat_bonus',0)+(bonus-bonuses.get(slot,0)))
        bonuses[slot]=bonus
        write('family_traits',traits)


def equipped(game,npc):
    facts=levels(npc)
    slots={'main':read(npc,'main_technique_id'),**read(npc,'technique_slots',{})}
    result=[]
    for slot,identity in slots.items():
        if not identity or identity not in facts:continue
        book=resolve(game,identity)
        if not book or not can_practice_technique(read(npc,'spirit_root',''),book):continue
        if book.required_body_training>int(read(npc,'body_training',0) or 0):continue
        if book.requires_immortal_power and not (read(npc,'transcendence',{}) or {}).get('conversion',0):continue
        book.level=facts[identity];result.append((slot,book))
    return result


def public(game,npc):
    facts=levels(npc)
    rows=[]
    for identity,level in facts.items():
        t=resolve(game,identity)
        if t:rows.append(dict(id=identity,name=t.name,level=level))
    return rows

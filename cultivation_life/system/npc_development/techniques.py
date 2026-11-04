"""Advance learned techniques through the original NPC technique authority."""
import copy
from ..npc_techniques import levels,resolve,learn
from .upper import require_upper


def options(game,facts):
    return [dict(axis='technique:'+key,name=book.name,rank=level) for key,level in levels(facts).items()
            if (book:=resolve(game,key)) is not None]


def plan(game,target,facts,axis,batches,method):
    if target.kind=='puppet':raise ValueError('傀儡沿修为、淬体与凝识提升，活傀主修由传法配置')
    if facts['realm_index']>=9:require_upper(game,target,facts)
    key=axis[len('technique:'):];before=levels(facts).get(key,0);book=resolve(game,key)
    if not before or not book:raise ValueError('须先传授并掌握所选功法')
    if method=='family':raise ValueError('家族灌顶不用于功法研修')
    limit=9
    if method=='infuse':limit=min(limit,next((t.level for t in game.player.known_techniques if t.id==key),0))
    rounds=min(batches,max(0,limit-before))
    if not rounds:raise ValueError('已达功法九重或施教者掌握的上限')
    result=copy.deepcopy(facts)
    slot='main' if facts.get('main_technique_id')==key else next((s for s,k in facts.get('technique_slots',{}).items() if k==key),None)
    learn(result,book,before+rounds,slot=slot)
    return dict(axis=axis,label='研修'+book.name,batches=batches,rounds=rounds,gain=rounds,
        before=f'{book.name} {before}重',after=f'{book.name} {before+rounds}重',result=result,
        specialized_reference=sum(1000*(i+1) for i in range(before,before+rounds)))

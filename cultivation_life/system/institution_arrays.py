"""Institutional references to original fixed arrays; no second array inventory."""
from .institution_deliberation import book,ensure
from .formation_system import _ground_profile,ground_formation_power
from .formation.maintenance import repair
from ..content_registry import CONTENT_DOCUMENTS


def candidates(game,scope):
    return [a for a in game.player.formation_ground_arrays if a.get('world')==scope['world']
        and a.get('location_id')==scope['location'] and a.get('creator_id')==game.id
        and a.get('owner_kind')=='player' and a.get('owner_id')=='player']


def current(game,scope):
    return next((a for a in candidates(game,scope) if a['id']==book(scope)['guard']),None)


def bind(game,scope,identity):
    if identity and identity not in {a['id'] for a in candidates(game,scope)}:raise ValueError('须使用本人布在原府所在地的原镇地阵')
    ensure(scope)['guard']=identity or None


def maintain(game,scope,supply):
    a=current(game,scope)
    if not a:raise ValueError('原府阵位已经失效')
    d=next((d for d in CONTENT_DOCUMENTS.get('formations.json',{}).get('maintenance_resources',[]) if d['id']==supply),None)
    return repair(game,a,supply,d,1)


def defence(game,scope):
    a=current(game,scope)
    if not a:return 0
    return ground_formation_power(a,_ground_profile(game.player,a))


def wear(game,scope,amount=10):
    a=current(game,scope)
    if a:
        a['durability']=round(max(0,a['durability']-amount),4)
        a['battles']=a.get('battles',0)+1

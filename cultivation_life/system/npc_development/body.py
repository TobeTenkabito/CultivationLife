"""Explicit high-body specialization using the existing four combat projections."""
import copy
from ..combat.actor_state import has_body
from .. import divine_lights,wuyun,monster_body,ghost_body
from ..npc_body_attainments import rank
from ...ghost_body_content import IDS,NAMES
from .upper import require_upper


def catalog(facts):
    if wuyun.enabled_for(facts):return 'wuyun',wuyun.definitions()
    if monster_body.enabled_for(facts):return 'monster',monster_body.config()['mechanisms']
    if ghost_body.enabled_for(facts):
        return 'ghost',[dict(id=k,name=n,unlock_level=(i+1)*10) for i,(k,n) in enumerate(zip(IDS,NAMES))]
    return 'lights',divine_lights.definitions()


def options(facts):
    family,rows=catalog(facts)
    return [dict(axis=f'body_art:{family}:{r["id"]}',name=r.get('name',r['id']),
        unlock=r['unlock_level'],rank=rank(facts,family,r['id'],facts['immortal_body_level'])) for r in rows]


def plan(game,target,facts,axis,batches,method):
    require_upper(game,target,facts)
    if target.kind=='puppet':raise ValueError('傀儡沿淬体、凝识与能源培养，不修习人物肉身神通')
    if not has_body(facts):raise ValueError('当前没有可培养的实际肉身')
    if facts['realm_index']<9:raise ValueError('肉身精修须达到九阶')
    choice=next((r for r in options(facts) if r['axis']==axis),None)
    if not choice:raise ValueError('该肉身神通不属于目标当前道途或DLC未开启')
    if facts['immortal_body_level']<choice['unlock']:raise ValueError(f'高阶肉身须达到{choice["unlock"]}层')
    if method=='family':raise ValueError('家族灌顶不用于肉身精修')
    limit=10
    family,key=axis.split(':')[1:]
    if method=='infuse':
        if not has_body(game.player):raise ValueError('须以当前实际肉身施教')
        from ..possession_system import is_possessed
        teacher_family,_=catalog(game.player.ghost_host_body if is_possessed(game.player) else game.player)
        if teacher_family!=family:raise ValueError('施教者须掌握同类肉身神通')
        if family=='lights':levels=divine_lights.profile(game.player,player=True)[1]
        else:
            module={'wuyun':wuyun,'monster':monster_body,'ghost':ghost_body}[family]
            levels={r.id:r.level for r in module.profile(game.player,player=True)}
        limit=min(limit,levels.get(key,0))
    before=choice['rank'];rounds=min(batches,max(0,limit-before))
    if not rounds:raise ValueError('已达十重或施教者掌握的上限')
    after=before+rounds;result=copy.deepcopy(facts)
    result.setdefault('body_attainments',{}).setdefault(family,{})[key]=after
    return dict(axis=axis,label='精修'+choice['name'],batches=batches,rounds=rounds,gain=rounds,
        before=f'{choice["name"]} {before}重',after=f'{choice["name"]} {after}重',result=result,
        specialized_reference=sum(1000*(i+1) for i in range(before,after)))

"""Simplified NPC upper growth, reusing the original independent energy ledger."""
import copy
from math import ceil
from ...content_registry import WORLD_SYSTEMS
from ...npc_development_content import UPPER
from ..combat.npc_lifecycle import settle


def require_upper(game, target, facts):
    if target.kind=='puppet':
        if game.player.world not in UPPER.values():
            raise ValueError('高阶傀儡须在第三级普通界面培养')
    elif UPPER.get(facts.get('path')) != game.player.world:
        raise ValueError('高阶培养须在目标道途对应的上界进行')


def grow_ledger(game, target, before, result, conversion=None):
    """Settle old capacity first, then grow capacity without filling it."""
    if target.kind=='puppet':
        return
    previous=copy.deepcopy(before)
    previous['world']=game.player.world
    config=WORLD_SYSTEMS['transcendent_combat']
    state=settle(previous,game.player.age,config)
    if state is None and conversion is None:
        return
    if state is None:
        state=dict(version=1,conversion=0.,capacity=0.,current=0.,force_tier=1,
                   ward_tier=1,attack_cost=10.,ward_cost=0.,attainments={},voisinage_ids=[])
    stage=max(0,(result['realm_index']-9)*3+(result['layer']-1)//3)
    state['capacity']=max(float(state.get('capacity',0)),1000.*(1+stage))
    if conversion is not None:
        state['conversion']=conversion
        state['force_tier']=2 if conversion>0 else 1
    # The next interval uses the new capacity; no retroactive recovery.
    environment=config['npc_lifecycle']['environments'][game.player.world]
    state['lifecycle']=dict(at=game.player.age,world=game.player.world,
        rate=state['capacity']*state.get('conversion',0)*environment['recovery_per_year'])
    result['transcendence']=state


def conversion_plan(game,target,facts,batches):
    require_upper(game,target,facts)
    if target.kind=='puppet':raise ValueError('傀儡由合格能源或玩家元力驱动仙阶攻击，无需人物转化')
    if facts['realm_index']<9:raise ValueError('须先达到上境修为才能转化元力')
    before=float((facts.get('transcendence') or {}).get('conversion',0))
    rounds=min(batches,max(0,ceil((1-before)*5-1e-9)))
    if not rounds:raise ValueError('元力已完成转化')
    after=min(1.,round(before+rounds*.2,6))
    result=copy.deepcopy(facts)
    grow_ledger(game,target,facts,result,after)
    return dict(axis='conversion',label='转化元力',batches=batches,rounds=rounds,gain=after-before,
        before=f'元力转化 {before:.0%}',after=f'元力转化 {after:.0%}',result=result)

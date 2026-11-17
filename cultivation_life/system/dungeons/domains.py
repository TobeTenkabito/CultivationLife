"""Original finite domain grants follow the same NPC after an expedition ends."""
from ..combat.actor_state import read
from ..doctrine.voisinage_training import multiplier


def definitions(npc):
    origin=(read(npc,'family_traits',{}) or {}).get('dungeon_origin',{})
    rank=origin.get('domain_rank',0)
    if not rank:return []
    realm=origin['true_realm'];identity=read(npc,'id')
    return [dict(id=identity+':domain',name='至臻归藏道域' if rank==13 else '归藏灵域',
        attainment='dungeon_domain',required_level=1,strength=(1+(realm-9)*.8)*multiplier(rank),
        opening_cost=80.,upkeep_cost=40.,effect='strike',effect_cost=35.,effect_power=.2,max_investment=0.)]

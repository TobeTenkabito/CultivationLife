"""Read-only demonic body projection; combat receives only resolved snapshots."""
from ..content_registry import WORLD_SYSTEMS
from ..body_mechanism_content import build
from .combat.actor_state import read


def enabled_for(owner):
    return read(owner,'path')=='demonic' and bool(WORLD_SYSTEMS.get('asura_manifestation',{}).get('enabled'))


def definitions():return WORLD_SYSTEMS.get('asura_manifestation',{}).get('five_aggregates',[])


def profile(owner,*,player=False):
    if player:
        from .possession_system import is_possessed
        if is_possessed(owner):owner=owner.ghost_host_body;player=False
    if not enabled_for(owner):return ()
    record=owner.asura_cultivation if player else dict(body_level=read(owner,'immortal_body_level',0) or 0)
    level=record.get('body_level',0);ranks=record.get('aggregates',{})
    return tuple(build(row,ranks.get(row['id'],0) if player else min(10,level//5))
                 for row in definitions() if level>=row['unlock_level'])



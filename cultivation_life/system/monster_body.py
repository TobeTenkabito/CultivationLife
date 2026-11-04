"""Read-only ownership projection of the actual monster body."""
from ..content_registry import WORLD_SYSTEMS
from .npc_body_attainments import rank as trained_rank
from ..monster_body_content import build
from .combat.actor_state import read,has_body


def config():return WORLD_SYSTEMS.get('monster_body',{})


def enabled_for(owner):return read(owner,'path')=='monster' and bool(config().get('enabled'))


def record(owner):return owner.immortal_body.get('monster',{})


def active_level(owner,*,player=False):
    if player:
        from .possession_system import is_possessed
        if is_possessed(owner):owner=owner.ghost_host_body;player=False
        elif owner.spirit_state.get('mode')=='wandering' and not owner.spirit_state.get('body_intact'):return 0
    # Growth accounting retains the intact original body; battle mechanisms
    # below separately require the body currently occupied by the actor.
    if not enabled_for(owner) or (not player and not has_body(owner)):return 0
    return record(owner).get('level',0) if player else min(50,max(0,read(owner,'immortal_body_level',0) or 0))


def profile(owner,*,player=False):
    if player:
        from .possession_system import is_possessed
        if is_possessed(owner):owner=owner.ghost_host_body;player=False
    if not has_body(owner) or not enabled_for(owner):return ()
    data=record(owner) if player else dict(level=read(owner,'immortal_body_level',0) or 0)
    level=data.get('level',0);ranks=data.get('training',{})
    return tuple(build(row,ranks.get(row['id'],0) if player else trained_rank(owner,'monster',row['id'],level),data.get('reaction','auto'))
        for row in config().get('mechanisms',[]) if level>=row['unlock_level'])

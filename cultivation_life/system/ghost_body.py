"""Actual-body ghost projection; no progression or presentation side effects."""
from ..content_registry import WORLD_SYSTEMS
from .npc_body_attainments import rank as trained_rank
from ..ghost_body_content import IDS,build,validate_training
from .combat.actor_state import read,has_body


def enabled_for(owner):
    return read(owner,'path')=='ghost' and bool(WORLD_SYSTEMS.get('ghost_cultivation',{}).get('enabled'))


def profile(owner,*,player=False):
    if player:
        from .possession_system import is_possessed
        if is_possessed(owner):owner=owner.ghost_host_body;player=False
    if not has_body(owner) or not enabled_for(owner):return ()
    level=owner.immortal_body.get('level',0) if player else read(owner,'immortal_body_level',0) or 0
    training=validate_training(owner.immortal_body.get('ghost_training',{})) if player else {}
    return tuple(build(key,training.get(key,0) if player else trained_rank(owner,'ghost',key,level))
        for i,key in enumerate(IDS,1) if level>=i*10)

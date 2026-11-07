"""NPC soul state stays on the original actor; no replacement roster entry."""
from ..soul_rules import wandering
from ..content_registry import WORLD_SYSTEMS
from .combat.actor_state import read, _write


def escape_body(owner, now):
    if now is None or read(owner, 'realm_index', 0) < 4 or wandering(owner):
        return False
    rank = read(owner, 'realm_index', 0)
    _write(owner, 'spirit_state', dict(mode='wandering',body_intact=False,entered=now,
        deadline=now+WORLD_SYSTEMS['time_units'][str(rank)],
        address=dict(world=read(owner,'world'),location=read(owner,'location_id'),instance=None)))
    _write(owner,'body_training',0)
    _write(owner,'body_attainments',{})
    return True


def expired(owner, now):
    """Read the original soul deadline, retaining ghost and second-soul exemptions."""
    if not wandering(owner) or read(owner,'path') == 'ghost' or (read(owner,'custody') or {}).get('kind') == 'second_nascent':
        return False
    return now > read(owner,'spirit_state')['deadline']


def settle(owner, now):
    if expired(owner, now):
        _write(owner,'alive',False)
        _write(owner,'death_reason','神游超时，元婴消散')
    return read(owner,'alive',True)

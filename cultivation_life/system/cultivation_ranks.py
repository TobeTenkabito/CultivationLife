"""Independent cultivation, body and sense coordinates. No annual simulation."""

from ..cultivation_coordinates import (
    STARTS as STARTS,
    NAMES as NAMES,
    rank_for as rank_for,
    describe as describe,
    body_rank as body_rank,
    legacy_sense as legacy_sense,
)

from .npc_cultivation import (
    ensure_npc as ensure_npc,
    npc_voisinage_limit as npc_voisinage_limit,
    npc_golden_light as npc_golden_light,
)

def public_ranks(actor, *, player=False):
    from .combat.actor_state import read
    if not player:
        ensure_npc(actor)
    immortal = actor.immortal_body.get('level', 0) if player else read(actor, 'immortal_body_level', 0)
    if player:
        from .asura import enabled
        if enabled() and actor.path == 'demonic':
            immortal = max(immortal, actor.asura_cultivation.get('body_level', 0))
    return {'cultivation': describe(rank_for(read(actor, 'realm_index', 0), read(actor, 'layer', 1))),
            'body': describe(body_rank(read(actor, 'body_training', 0), immortal)),
            'sense': describe(read(actor, 'divine_sense_rank', 0))}


def mask_unrevealed(public, perception):
    if perception and not perception.get('revealed'):
        public['cultivation_ranks'] = {
            'cultivation': {'name': perception['realm_name']},
            'body': {'name': '未探明'}, 'sense': {'name': '未探明'}}
        for key in ('body_training', 'immortal_body_level', 'divine_sense_rank'):
            public[key] = None

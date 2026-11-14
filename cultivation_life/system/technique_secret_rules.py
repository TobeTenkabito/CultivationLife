"""Read-only, slot-bound secret benefits shared by quotes and settlements."""
from ..content_registry import ContentRegistry
from ..technique_requirements import combat_requirement_met, qi_levels


def catalog():
    return {r["id"]:r for r in ContentRegistry.loaded_documents["secret_arts.json"].get("technique_arts",[])}


def equipped(player, art):
    from ..content_registry import TECHNIQUE_CATALOG
    from ..technique_affinity import can_player_practice_technique
    original=TECHNIQUE_CATALOG.get(art['technique_id'])
    if original is None or not any(t.id==original.id for t in player.known_techniques):return None
    slots={'main':[player.technique], 'support':[player.support_technique], 'combat':player.combat_techniques}
    book=next((t for t in slots[art['slot']] if t and t.id==original.id),None)
    if (not book or player.realm_index<original.grade or not original.active_in(player.world)
            or not can_player_practice_technique(player,original)
            or original.requires_immortal_power and not player.immortal_power_converted
            or player.body_training<original.required_body_training):return None
    if art["slot"] == "combat" and not combat_requirement_met(original.combat_requirements, qi_levels(player)):
        return None
    return book


def bonus(player, effect):
    if not player.alive or player.cultivation_suppression or player.sealed_cultivation:return 0.
    from .possession_system import is_possessed
    if is_possessed(player):return 0.
    if not player.secret_art_state.get('manuals'):return 0.
    arts=catalog(); total=0.
    for identity, record in player.secret_art_state.get('manuals',{}).items():
        art=arts.get(identity)
        if (art and record.get('activated') and art['effect']==effect
                and art['realm']==player.realm_index and equipped(player,art)):
            total+=art['value']
    # Cost reductions cannot remove a resource price; probability keeps the
    # existing global cap at its original settlement, not here.
    return min(.25,total) if effect.endswith('discount') else total


def trial_stats(player, stats):
    """Apply once when a real major-tribulation snapshot is constructed."""
    for stat in ('guard','breach','sustain','sense'):
        stats[stat]*=1+min(.15,bonus(player,'trial_'+stat))


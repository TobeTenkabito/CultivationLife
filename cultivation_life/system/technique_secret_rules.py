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
    if (not book or player.realm_index<book.grade or not original.active_in(player.world)
            or not can_player_practice_technique(player,original)
            or book.requires_immortal_power and not player.immortal_power_converted
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


def trial_stats(player, stats, *, major=True):
    """Apply once when a real major-tribulation snapshot is constructed."""
    frost = frost_bonus(player, immortal=True)
    for stat in ('might','mobility','guard','breach','sustain','sense'):
        extra = bonus(player, 'major_bonus') if major and stat == 'guard' and 9 <= player.realm_index <= 11 else 0.
        specific=bonus(player,'trial_'+stat) if major else 0.
        stats[stat]*=1+min(.15,specific + extra + frost)


def frost_bonus(player, *, immortal=False):
    if not player.alive or player.cultivation_suppression or player.sealed_cultivation:return 0.
    from .possession_system import is_possessed
    if is_possessed(player):return 0.
    art=catalog().get('manual_frost_sky')
    if not art or not player.secret_art_state.get('manuals',{}).get(art['id'],{}).get('activated'):return 0.
    book=equipped(player,art)
    if not book or (book.level>=7)!=immortal:return 0.
    return .04 if immortal else art['value']


def major_probability_bonus(player):
    """Optional upper trials fall back to the original probability route."""
    extra = sum(bonus(player, 'trial_' + stat) for stat in ('guard','breach','sustain','sense')) if 9 <= player.realm_index <= 11 else 0.
    return bonus(player, 'major_bonus') + min(.15, extra)


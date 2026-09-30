"""Additive migration of declared institutions; never reroll people or politics."""
def migrate_institutions(game):
    from ..content_registry import FACTION_DEFINITIONS
    changed = False
    for key, definition in FACTION_DEFINITIONS.items():
        entity = game.sects.get(key)
        if definition.get('kind') != 'institution' or not entity:
            continue
        if entity.kind != 'institution':
            entity.kind = 'institution'
            changed = True
        player = game.player
        if player.faction_id == key:
            player.institution_affiliations.setdefault(key, {
                'joined_age': player.faction_join_age,
                'legacy_contribution': player.faction_contribution,
                'legacy_reward_preference': player.faction_reward_preference,
            })
            player.faction_id = None
            player.faction_join_age = None
            player.faction_contribution = 0
            player.faction_reward_preference = None
            changed = True
    return changed

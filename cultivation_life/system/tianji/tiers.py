"""Frozen template tier; world suppression and replica output do not reclassify it."""
from ...content_registry import WORLD_SYSTEMS


def artifact_force_tier(definition):
    if 'force_tier' in definition:
        return int(definition['force_tier'])
    threshold = WORLD_SYSTEMS['combat_expectations']['true_immortal']['value']
    return 2 if float(definition.get('base_combat_power', 0)) >= threshold else 1


def migrate_tiers(game):
    state = game.tianji_state
    if state.get('force_tiers_version') == 1:
        return False
    definitions = {d['id']: d for d in state.get('artifacts', [])}
    for d in definitions.values():
        d['force_tier'] = artifact_force_tier(d)
    for instance in game.player.crafted_artifacts:
        definition = definitions.get(instance.get('tianji', {}).get('definition_id'))
        if definition:
            instance['force_tier'] = definition['force_tier']
    state['force_tiers_version'] = 1
    return True

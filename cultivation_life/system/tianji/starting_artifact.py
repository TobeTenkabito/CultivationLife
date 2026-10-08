"""Initial-life transfer of one generated true body; never clones its holder."""
from ..crafting_system import store_crafted_artifact


def grant(game, bracket, rng, *, scale, available):
    if not available:
        raise ValueError('巧夺天工未启用')
    options = [r for r in game.tianji_state.get('artifacts', []) if (bracket - 1) * 20 < r['rank'] <= bracket * 20]
    if not options:
        raise ValueError('所选神机名次区间为空')
    definition = rng.choice(options)
    effects, persistent = scale(definition['effects'], 1.)
    p = game.player
    p.crafting_sequence += 1
    identity = f'tianji-start-{game.id}-{p.crafting_sequence}'
    artifact = dict(id=identity, name=definition['name'], mold_id=definition['mold_id'],
        mold_name='天工神机', quality='tianji_true', quality_name='真体', quality_multiplier=1.,
        creator_name=p.name, creator_id=game.id, created_year=p.age, materials=[], material_effects=[],
        actual_stats={'combat_power': definition['base_combat_power'], **persistent}, combat_effects=effects,
        anchor_value=max(1, round(definition['base_combat_power'] / 12)), is_natal=False,
        force_tier=definition.get('force_tier', 1), description='自定义开局携带的神机真体',
        tianji=dict(definition_id=definition['id'], kind='true_body', replica_ratio=1.))
    store_crafted_artifact(p, artifact)
    state = game.tianji_state
    state['holders'].pop(definition['id'], None)
    state['true_body_states'][definition['id']] = dict(status='player', holder_ref=identity)
    state['player_artifacts'].append(identity)
    state['knowledge'][definition['id']] = 4
    p.equipped_crafted_artifact_ids.append(identity)

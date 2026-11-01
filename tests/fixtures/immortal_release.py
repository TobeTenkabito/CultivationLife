"""Disposable release character; final commands still pay every real cost."""
from cultivation_life.rules import add_item, combat_power
from cultivation_life.system.immortal_artifacts import MATERIALS


def prepare_immortal_release(engine, identity):
    game = engine._load(identity)
    game.pending_event = None
    game.player.inventory.clear()
    add_item(game.player, 'starfall_blade')
    add_item(game.player, 'spirit_stone', 10**12)
    for key, _ in MATERIALS:
        add_item(game.player, key, 4 if key == MATERIALS[0][0] else 3)
    engine.store.save(game)
    engine.natal_artifact_action(identity, 'bind', 'starfall_blade')
    game = engine._load(identity)
    game.natal_artifact['refinement_count'] = 36
    engine.store.save(game)


def mark_immortal_release(engine, identity):
    game = engine._load(identity)
    assert game.natal_artifact['refinement_count'] == 37
    engine._immortal_release_baseline = (combat_power(game.player), game.player.age, game.rng_state)


def inspect_immortal_release(engine, identity):
    game = engine._load(identity)
    assert (combat_power(game.player), game.player.age, game.rng_state) == engine._immortal_release_baseline
    assert game.natal_artifact['immortal_grade'] == 1
    assert game.natal_artifact['force_tier'] == 2
    assert all(not any(i.id == key for i in game.player.inventory) for key, _ in MATERIALS)

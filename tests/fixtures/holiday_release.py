"""Disposable release-only battle fixture; never touches an existing user slot."""
import random


def holiday_battle(engine, game_id):
    game = engine._load(game_id)
    game.pending_event = None
    engine._combat(game, dict(target_name='节日演武', combat_type='beast', target_realm_index=1,
                             target_power=engine._player_battle_power(game)*1.2),
                   False, random.Random(321))
    engine.store.save(game)

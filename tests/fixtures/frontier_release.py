"""Battle in an explicitly created disposable native acceptance slot."""
import random


def frontier_battle(engine,game_id):
    game=engine._load(game_id)
    game.pending_event=None
    engine._combat(game,dict(target_name='荒原演武',combat_type='beast',
        target_realm_index=game.player.realm_index,target_power=engine._player_battle_power(game)*1.2),
        False,random.Random(322))
    engine.store.save(game)

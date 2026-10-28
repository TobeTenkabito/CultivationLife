"""Disposable acceptance only: award through the existing achievement evaluator."""
def earn_legend(engine, game_id):
    game=engine.store.load(game_id)
    game.player.born_rootless=True
    game.player.realm_index=8
    engine.achievements.evaluate(game,player_rank=1)
    assert 'cultivation_rootless_legend' in engine.achievements.metadata.read()['achievements']

"""Controlled characters for real browser and signed native verification only."""
def prepare(engine, identity):
    from cultivation_life.system.monster_civilizations import core
    game=engine._load(identity);game.pending_event=None;game.active_trial=None
    game.player.opportunity=10000
    game.player.location_id=core.config()['worlds'][game.player.world]['regions'][0]
    engine.store.save(game)


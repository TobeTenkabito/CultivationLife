"""Isolated character setup only; acceptance executes production API/buttons."""
def prepare_westward(engine, game_id):
    from cultivation_life.system.yaochi_rules import config
    from cultivation_life.models import SectNpc
    from cultivation_life.rules import add_item
    from cultivation_life.economy_content import material_id
    g = engine._load(game_id)
    g.pending_event = None
    g.player.location_id = config()['location_id']
    g.player.next_tribulation_age = None
    g.player.immortal_body.update(level=20, manuals=['jade_marrows'], active_manual='jade_marrows')
    g.yaochi_state.update(merit=2000, earned=2000)
    g.heavenly_court.update(player_merit=50, open_election=None)
    g.settings.update(silent_events=True, combat_popup=False, court_election_popup=False)
    add_item(g.player,'spirit_stone',10**9)
    add_item(g.player,material_id('celestial',4,'ore_conduct'),30)
    g.world_npcs['westward-release-teacher']=SectNpc('westward-release-teacher','澄明真人','散修',10,1,40,100000,
        spirit_root='supreme_metal',world='celestial',location_id=g.player.location_id)
    engine.store.save(g)

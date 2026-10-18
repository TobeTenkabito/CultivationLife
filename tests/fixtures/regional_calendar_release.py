"""Synthetic test saves only; real annual movement and real notification choices."""
from cultivation_life.rules import max_hp, max_mp


def prepare_regional_journey(engine, identity):
    game = engine._load(identity)
    p = game.player
    assert p.world == 'human' and p.location_id == 'wudi_plain'
    p.realm_index, p.layer, p.lifespan, p.next_tribulation_age = 4, 1, 10000, None
    p.hp, p.mp = max_hp(p), max_mp(p)
    game.pending_event = None
    game.settings.update(silent_events=False, guixu_event_popup=True)
    dungeon = next(d for d in engine._guixu_definitions().values() if d['world'] == 'human')
    cycle = game.guixu_state['cycles'][dungeon['id']]
    cycle.update(phase='closed', next_announce_age=p.age+1,
                 next_open_age=p.age+1+dungeon['announce_lead_years'])
    engine.store.save(game)


def inspect_regional_journey(engine, identity, finished=False):
    game = engine.store.load(identity)
    travel = [h for h in game.history if h.event_id == 'SYS_MAP_TRAVEL']
    assert travel
    if finished:
        assert game.player.location_id == 'lanjiang_steppe' and game.map_journey is None
        total = travel[-1].state_diff['total_years']
        assert sum(h.state_diff['years'] for h in travel) == total
    else:
        assert game.pending_event['id'] == 'EVT_GUIXU_ANNOUNCE'
        assert game.map_journey['completed'] == 1
    sim = game.world_simulation
    assert sim and sim['regions']['human']['year'] == game.player.age
    assert sim['regions']['celestial']['year'] < game.player.age
    assert 'organization:sect:taixuan' in game.economy_v2['organizations']
    return True

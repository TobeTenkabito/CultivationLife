"""Isolated upper-world snapshots; all gameplay uses the ordinary commands."""
import copy

from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.rules import add_item, add_technique_copy, learn_technique, max_hp, max_mp
from cultivation_life.system.buddhist_wish import ensure_wish

WORLDS = ('celestial', 'asura', 'nether', 'reincarnation')


def prepare_upper_teachings(engine, identity, world, path):
    assert world in WORLDS and path in {'buddhist', 'confucian'}
    game = engine._load(identity)
    player = game.player
    game.pending_event = game.active_trial = None
    game.settings['silent_events'] = True
    player.world = world  # Test snapshot only, never a runtime travel shortcut.
    player.location_id = engine.maps.default_location(world)
    player.path = path
    player.realm_index, player.layer = 9, 1
    player.lifespan = None
    player.next_tribulation_age = None
    player.immortal_power_converted = True
    player.immortal_conversion_stage = 5
    player.immortal_veins = {'9': 27, '10': 27, '11': 27, '12': 27}
    player.immortal_body['level'] = 20
    player.haoran_exp = 1_000_000
    player.hp, player.mp = max_hp(player), max_mp(player)
    add_item(player, 'spirit_stone', 2_000_000)
    engine._ensure_sage_state(game)
    if path == 'buddhist':
        engine._ensure_buddhist_state(game)
        ensure_wish(game)['value'] = 100
        from cultivation_life.system.buddhist.rules import set_dharma_karma
        set_dharma_karma(game, 48)
        art = copy.deepcopy(next(t for t in TECHNIQUE_CATALOG.values() if t.path == path))
        learn_technique(player, art)
    else:
        art = next(t for t in TECHNIQUE_CATALOG.values() if t.grade == 10)
        add_technique_copy(player, copy.deepcopy(art), level=WORLDS.index(world) + 2)
    engine.store.save(game)
    return game

"""Disposable release saves for independent secret-art UI and material checks."""
import random
from cultivation_life.rules import add_item, max_hp, max_mp


def prepare_secret_arts(engine, identity):
    game = engine._load(identity)
    p = game.player
    game.pending_event = game.active_trial = None
    p.realm_index, p.layer = 1, 1
    p.spirit_root, p.additional_roots = 'supreme_metal', []
    p.secret_art_state = {}
    p.cultivation_concealment = p.cultivation_suppression = None
    p.age, p.lifespan = 18, 200
    p.hp, p.mp = max_hp(p), max_mp(p)
    game.settings.update(silent_events=True, guixu_event_popup=False)
    p.inventory = []
    add_item(p, 'spirit_stone', 1000000)
    for item in ('secret_manual_water', 'secret_manual_fire', 'secret_core_water_4', 'secret_soul_fire_4'):
        add_item(p, item)
    engine.store.save(game)


def pending_secret_art_event(engine, identity):
    game = engine._load(identity)
    game.pending_event = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], game, random.Random(1))
    engine.store.save(game)


def inspect_secret_arts(engine, identity):
    game = engine._load(identity)
    assert game.player.spirit_root == 'supreme_metal'
    assert game.player.additional_roots == ['water']
    assert game.player.secret_art_state['arts']['root_water']['study_years'] == 5
    assert not any(i.id == 'secret_core_water_4' for i in game.player.inventory)
    assert not any(i.id == 'secret_manual_water' for i in game.player.inventory)
    assert game.player.age == 33

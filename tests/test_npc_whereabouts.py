import random

import pytest

from cultivation_life.content_registry import WORLD_NPC_TEMPLATES
from test_seeded_dungeons import act, discover, local


def test_fixed_starts_roads_party_and_reload(local):
    engine, game = local
    for key, template in WORLD_NPC_TEMPLATES.items():
        person = game.world_npcs[key]
        assert person.location_id == template.location_id
        assert engine.maps.location(person.world, person.location_id).get('min_realm_index', 0) <= person.realm_index
    npc = game.world_npcs['tuoba_lie']
    game._regional_single_person = npc.id
    npc.realm_index = 1
    origin = npc.location_id
    def year(g):
        g.player.age += 1
        engine._annual_world_npc_update(g, random.Random(g.player.age))
    game.player.party = [dict(id=npc.id)]
    for _ in range(10):
        year(game)
    assert npc.location_id == origin and npc.roaming_years == 0
    game.player.party = []
    for _ in range(2):
        year(game)
    engine.store.save(game)
    loaded = engine.store.load(game.id)
    loaded._regional_single_person = npc.id
    visited = []
    for _ in range(40):
        previous = npc.location_id
        year(game)
        year(loaded)
        assert loaded.world_npcs[npc.id].location_id == npc.location_id
        assert loaded.world_npcs[npc.id].roaming_years == npc.roaming_years
        if npc.location_id != previous:
            visited.append(npc.location_id)
            assert npc.location_id in dict(engine.maps.roaming_roads(npc.world, previous, npc.realm_index))
    assert visited


def test_location_letters_are_dated_and_coexist_with_expeditions(local):
    engine, game = local
    npc = game.world_npcs['xiang_zhili']
    projected = lambda data: next(n for n in data['world_npcs'] if n['id'] == npc.id)
    row = projected(engine.get_game(game.id))
    assert row['contact_location_id'] is None and 'location_id' not in row
    age = game.player.age
    def ask(when):
        return engine.dungeon_action(game.id, 'ask_location', dict(actor_id=npc.id, world=npc.world, expected_age=when))
    with pytest.raises(ValueError, match='过时'):
        ask(age-1)
    with pytest.raises(ValueError, match='未知交往方式'):
        engine.contact_action(game.id, npc.id, 'ask_location', expected_unit=age)
    assert engine.store.load(game.id).dungeon_state.get('mail', []) == []
    shown = ask(age)
    letter = shown['dungeons']['mail'][-1]
    assert letter['unread'] and letter['location_id'] == npc.location_id
    assert shown['player']['age'] == age and '界门古塞' in projected(shown)['contact_whereabouts']
    with pytest.raises(ValueError, match='已送至'):
        ask(age)
    saved = engine.store.load(game.id)
    saved.world_npcs[npc.id].location_id = 'muling_desert'
    saved.player.age += 1
    engine.store.save(saved)
    assert projected(engine.get_game(game.id))['contact_location_id'] == 'border_void_watch'
    next_view = ask(saved.player.age)
    first, second = next_view['dungeons']['mail']
    assert first == letter and second['location_id'] == 'muling_desert'
    engine.dungeon_action(game.id, 'read_mail', dict(mail_id=first['id']))
    discover(engine, saved)
    act(engine, saved, 'enter')
    after = engine.store.load(game.id)
    assert [m['unread'] for m in after.dungeon_state['mail']] == [False, True]
    assert after.dungeon_state['mail'][0]['body'] == first['body']


def test_missing_home_on_load_respects_actual_address_and_map_gate(local):
    engine, game = local
    missing = game.world_npcs['yan_qingshuang']
    missing.location_id = None
    missing.realm_index = 1
    away = game.world_npcs['tuoba_lie']
    away.location_id = 'frost_reed_marsh'
    below_gate = game.world_npcs['xiang_zhili']
    below_gate.location_id = None
    below_gate.realm_index = 1
    engine.store.save(game)
    loaded = engine._load(game.id)
    assert loaded.world_npcs[missing.id].location_id == 'frost_reed_marsh'
    assert loaded.world_npcs[away.id].location_id == away.location_id
    assert loaded.world_npcs[below_gate.id].location_id is None
    loaded._regional_single_person = below_gate.id
    loaded.player.age += 1
    engine._annual_world_npc_update(loaded, random.Random(22))
    person = loaded.world_npcs[below_gate.id]
    assert engine.maps.location(person.world, person.location_id).get('min_realm_index', 0) <= person.realm_index

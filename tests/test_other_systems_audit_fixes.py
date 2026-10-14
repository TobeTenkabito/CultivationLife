"""Real commands and persisted boundaries for the non-economy audit repairs."""
import copy
import json
import random
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import CONTENT_DOCUMENTS, GUIXU_TIDE_CONTENT, ITEM_CATALOG, REALMS, WORLD_SYSTEMS, ContentRegistry, ContentError
from cultivation_life.models import Player
from cultivation_life.rules import add_item, opportunity_required
from cultivation_life.system.crafting_system import crafting_material_definitions, make_crafting_material_instance
from cultivation_life.system.ghost.progression import can_reincarnate, perform_reincarnation
from cultivation_life.system.possession_system import enter_host_body

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def api(tmp_path_factory):
    from cultivation_life import server
    directory = tmp_path_factory.mktemp('other-system-fixes')
    engine = GameEngine(ROOT, directory / 'saves')
    class Handler(server.Handler):
        def log_message(self, *args): pass
    with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', directory):
        http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{http.server_port}'
        def act(identity, operation, status=200, **payload):
            request = Request(base + f'/api/games/{identity}/{operation}', method='POST',
                              data=json.dumps(payload).encode(),
                              headers={'Content-Type':'application/json', 'Origin':base})
            try:
                with urlopen(request, timeout=30) as response:
                    code, body = response.status, json.loads(response.read())
            except HTTPError as error:
                code, body = error.code, json.loads(error.read())
            assert code == status, (operation, code, body)
            return body
        try:
            yield engine, act
        finally:
            http.shutdown(); http.server_close(); thread.join(timeout=2)


def new_game(engine, path='dao', realm=3, layer=1):
    shown = engine.create_game('边界修复验收', 'mutated_yin' if path == 'ghost' else 'supreme_metal',
                               path, 8712, preset_id='core' if path == 'dao' else None,
                               start_world='celestial' if realm >= 9 else 'human')
    game = engine._load(shown['id'])
    game.pending_event = None
    game.player.realm_index, game.player.layer = realm, layer
    game.player.next_tribulation_age = None
    game.settings['silent_events'] = True
    engine.store.save(game)
    return game


def snapshot(engine, identity):
    engine.get_game(identity)
    engine._load(identity)  # Adopt services for any fixture boundary reconciled by presentation.
    return engine.store._path(identity).read_bytes()


def suppressed_ghost(engine):
    game = new_game(engine, 'ghost', 4, 5)
    game.player.opportunity = 321
    engine.store.save(game)
    engine.manage_secret_art(game.id, 'suppress', 'activate', 1, REALMS[1].layers)
    game = engine._load(game.id)
    game.player.opportunity = opportunity_required(game.player)
    engine.store.save(game)
    return game


def reincarnation_choices(engine):
    choices = engine.events_by_id['SYS_GHOST_REINCARNATION']['choices']
    commit = next(c['id'] for c in choices if any(e['type']=='ghost_reincarnate' for e in c.get('effects', [])))
    cancel = next(c['id'] for c in choices if not any(e['type']=='ghost_reincarnate' for e in c.get('effects', [])))
    return commit, cancel


@pytest.mark.parametrize('operation', ['ghost-reincarnation-prompt', 'ghost-reincarnate'])
def test_suppression_rejects_every_reincarnation_command_without_mutation(api, operation):
    engine, act = api
    game = suppressed_ghost(engine)
    shown = engine.get_game(game.id)
    assert not shown['ghost_system']['can_reincarnate']
    frozen = snapshot(engine, game.id)
    act(game.id, operation, status=400)
    assert engine.store._path(game.id).read_bytes() == frozen
    act(game.id, 'secret-art', art='suppress', action='cancel')
    restored = engine._load(game.id).player
    assert (restored.realm_index, restored.layer) == (4, 5)
    assert restored.opportunity == 321 + game.player.opportunity
    assert not restored.ghost_reincarnation_imprints


def test_saved_blocked_reincarnation_event_keeps_followup_and_can_cancel(api):
    engine, act = api
    game = suppressed_ghost(engine)
    commit, cancel = reincarnation_choices(engine)
    # A valid schema10 prompt created by the formerly unguarded command.
    event = engine._instantiate_event(engine.events_by_id['SYS_GHOST_REINCARNATION'], game, random.Random(21))
    reward = engine._prepare_treasure_reward_event(game, random.Random(22))
    event['_followup_event'] = copy.deepcopy(reward)
    game.pending_event = event
    engine.store.save(game)
    loaded = engine.get_game(game.id)
    assert next(c for c in loaded['pending_event']['choices'] if c['id']==commit)['enabled'] is False
    frozen = snapshot(engine, game.id)
    act(game.id, 'choice', status=400, choice_id=commit, event_id=event['id'])
    assert engine.store._path(game.id).read_bytes() == frozen
    result = act(game.id, 'choice', choice_id=cancel, event_id=event['id'])
    assert result['pending_event']['runtime'] == reward['runtime']
    act(game.id, 'choice', choice_id='pill', event_id=reward['id'])
    assert engine._load(game.id).pending_event is None
    frozen = snapshot(engine, game.id)
    act(game.id, 'choice', status=400, choice_id='pill', event_id=reward['id'])
    assert engine.store._path(game.id).read_bytes() == frozen


@pytest.mark.parametrize('state', ['sealed', 'possessed'])
def test_reset_rule_rejects_other_saved_rank_restore_states(state):
    player = Player('魂基', 'mutated_yin', path='ghost', realm_index=4, layer=REALMS[4].layers)
    player.opportunity = opportunity_required(player)
    if state == 'sealed':
        player.sealed_cultivation = {'realm_index':9, 'layer':1, 'origin_world':'reincarnation'}
    else:
        player.ghost_host_body, player.ghost_core_state = {'id':'host'}, {'name':'core'}
    before = copy.deepcopy(player.to_dict())
    assert not can_reincarnate(player)
    with pytest.raises(ValueError): perform_reincarnation(player)
    assert player.to_dict() == before


@pytest.mark.parametrize('operation', ['ghost-reincarnate', 'choice'])
def test_ordinary_reincarnation_still_discards_rank_once(api, operation):
    engine, act = api
    game = new_game(engine, 'ghost', 4, REALMS[4].layers)
    game.player.opportunity = opportunity_required(game.player)
    engine.store.save(game)
    if operation == 'choice':
        shown = act(game.id, 'ghost-reincarnation-prompt')
        act(game.id, 'choice', choice_id=reincarnation_choices(engine)[0], event_id=shown['pending_event']['id'])
    else:
        act(game.id, operation)
    saved = engine._load(game.id).player
    assert (saved.realm_index, saved.layer, saved.opportunity) == (1, 1, 0)
    assert saved.ghost_reincarnation_imprints == {'4':1}
    assert not saved.cultivation_suppression
    frozen = snapshot(engine, game.id)
    act(game.id, 'ghost-reincarnate', status=400)
    assert engine.store._path(game.id).read_bytes() == frozen


def guixu_recipe(engine, game, world):
    dungeon = next(d for d in GUIXU_TIDE_CONTENT['dungeons'] if d['world']==world)
    primary = next(ITEM_CATALOG[r['content_id']] for r in dungeon['treasure_pool']
                   if r['kind']=='item' and 'crafting_material' in ITEM_CATALOG[r['content_id']].tags)
    add_item(game.player, primary.id, 4)
    engine.store.save(game)
    payload = dict(mold_id='sword', primary_id=f'guixu:{primary.id}:0',
                   secondary_a_id=f'guixu:{primary.id}:1', secondary_b_id=f'guixu:{primary.id}:2',
                   quench_id=f'guixu:{primary.id}:3', allocations={'combat_power':20})
    return dungeon, primary, payload


@pytest.mark.parametrize('world', list(dict.fromkeys(d['world'] for d in GUIXU_TIDE_CONTENT['dungeons'])))
def test_carried_guixu_material_uses_source_rank_in_preview_and_forge(api, world):
    engine, act = api
    game = new_game(engine, realm=12)
    dungeon, primary, payload = guixu_recipe(engine, game, world)
    frozen = snapshot(engine, game.id)
    preview = act(game.id, 'crafting-preview', **payload)
    assert preview['scaling_realm_index'] == dungeon['max_entry_rank'][0]
    assert engine.store._path(game.id).read_bytes() == frozen
    act(game.id, 'crafting-forge', **payload)
    saved = engine._load(game.id)
    artifact = saved.player.crafted_artifacts[-1]
    assert artifact['scaling_realm_index'] == dungeon['max_entry_rank'][0]
    assert artifact['materials'][0]['origin_world'] == world
    assert not any(i.id==primary.id for i in saved.player.inventory)
    assert saved.player.crafting_sequence == 1


def ordinary_recipe(engine, game):
    definitions = crafting_material_definitions()
    rows = [make_crafting_material_instance(definitions[mid], random.Random(i), source='验收', origin_world='human')
            for i, mid in enumerate(['human_cold_iron']+['human_cold_spring_water']*3)]
    game.player.crafting_materials = rows
    payload = dict(mold_id='sword', primary_id=rows[0]['id'], secondary_a_id=rows[1]['id'],
                   secondary_b_id=rows[2]['id'], quench_id=rows[3]['id'], allocations={'combat_power':20})
    return rows, payload


def test_large_material_stack_has_bounded_choices_and_only_spends_selected_units(api):
    engine, act = api
    game = new_game(engine, realm=9)
    _, primary, payload = guixu_recipe(engine, game, 'human')
    add_item(game.player, primary.id, 100000 - 4)
    engine.store.save(game)
    rows = [row for row in engine._crafting_material_candidates(game.player) if row.get('inventory_item_id')==primary.id]
    assert len(rows)==4 and all(row['quantity']==100000 for row in rows)
    act(game.id, 'crafting-forge', **payload)
    saved = engine._load(game.id).player
    assert next(item.quantity for item in saved.inventory if item.id==primary.id)==99996
    assert len(saved.crafted_artifacts)==1
    rows = [row for row in engine._formation_candidates(saved, include_active=False, include_ground=False)
            if row.get('inventory_item_id')==primary.id]
    assert len(rows)==9
    slots = [row['id'] for row in rows]
    act(game.id, 'formation-save', name='堆叠材料九宫', slots=slots, activate=True)
    saved = engine._load(game.id).player
    assert len([row for row in saved.formation_active_bindings if row])==9
    assert next(item.quantity for item in saved.inventory if item.id==primary.id)==99987
    act(game.id, 'formation-deactivate')
    saved = engine._load(game.id).player
    assert next(item.quantity for item in saved.inventory if item.id==primary.id)==99996


@pytest.mark.parametrize('stored_tier', [None, 12])
def test_ordinary_material_uses_authoritative_grade_even_with_missing_or_wrong_snapshot(api, stored_tier):
    engine, act = api
    game = new_game(engine, realm=9)
    rows, payload = ordinary_recipe(engine, game)
    if stored_tier is None: rows[0].pop('acquired_tier')
    else: rows[0]['acquired_tier'] = stored_tier
    engine.store.save(game)
    frozen = snapshot(engine, game.id)
    assert act(game.id, 'crafting-preview', **payload)['scaling_realm_index'] == 1
    assert engine.store._path(game.id).read_bytes() == frozen
    act(game.id, 'crafting-forge', **payload)
    assert engine._load(game.id).player.crafted_artifacts[-1]['scaling_realm_index'] == 1


@pytest.mark.parametrize('plant,years,tier', [('golden_thunder_bamboo',99,1), ('golden_thunder_bamboo',100,2),
    ('golden_thunder_bamboo',999,2), ('golden_thunder_bamboo',1000,3), ('golden_thunder_bamboo',9999,3),
    ('golden_thunder_bamboo',10000,4), ('mystic_heaven_vine',10000,4), ('heaven_heart_lotus',10,1)])
def test_harvested_main_material_uses_growth_years_not_holder_rank(api, plant, years, tier):
    engine, act = api
    game = new_game(engine, realm=9)
    _, payload = ordinary_recipe(engine, game)
    item = engine._add_harvested_plant(game.player, plant, years)
    payload['primary_id'] = f'plant:{item.id}'
    engine.store.save(game)
    frozen = snapshot(engine, game.id)
    assert act(game.id, 'crafting-preview', **payload)['scaling_realm_index'] == tier
    assert engine.store._path(game.id).read_bytes() == frozen
    act(game.id, 'crafting-forge', **payload)
    saved = engine._load(game.id)
    assert saved.player.crafted_artifacts[-1]['scaling_realm_index'] == tier
    assert not any(i.id==item.id for i in saved.player.inventory)


@pytest.mark.parametrize('tier', [None, True, '9', 0, 13])
def test_invalid_primary_grade_cannot_fall_back_to_player_or_consume_materials(api, tier):
    engine, act = api
    game = new_game(engine, realm=9)
    _, payload = ordinary_recipe(engine, game)
    engine.store.save(game)
    mold, selected = engine._resolve_crafting_selection(game.player, payload)
    selected[0][1]['acquired_tier'] = tier
    frozen = snapshot(engine, game.id)
    with patch.object(engine, '_resolve_crafting_selection', return_value=(mold, selected)):
        act(game.id, 'crafting-forge', status=400, **payload)
    assert engine.store._path(game.id).read_bytes() == frozen


def trapped_game(engine, realm=1):
    game = new_game(engine, 'ghost', realm)
    dungeon = next(d for d in GUIXU_TIDE_CONTENT['dungeons'] if d['world']=='human')
    game.player.location_id = dungeon['entry_location_id']
    cycle = game.guixu_state['cycles'][dungeon['id']]
    engine._open_guixu_cycle(game, dungeon, cycle, random.Random(13))
    game.pending_event = None
    engine.store.save(game)
    with patch.object(engine, '_guixu_offer_team'):
        engine.guixu_action(game.id, 'enter', {'dungeon_id':dungeon['id']})
    game = engine._load(game.id)
    game.guixu_state['player_session']['remaining_days'] = 0
    engine._close_guixu_cycle(game, dungeon, game.guixu_state['cycles'][dungeon['id']], random.Random(13))
    game.pending_event = None
    game.player.ghost_soul_erosion_rate_pp = 1
    game.player.ghost_soul_erosion_time_progress = 0
    engine.store.save(game)
    return game


@pytest.mark.parametrize('realm', [1, 3])
def test_old_trapped_entry_accounts_for_exactly_one_year_of_erosion(api, realm):
    engine, act = api
    game = trapped_game(engine, realm)
    unit = WORLD_SYSTEMS['time_units'][str(realm)]
    age, rate = game.player.age, game.player.ghost_soul_erosion_rate_pp
    act(game.id, 'guixu-action', action='trapped_cultivate')
    saved = engine._load(game.id)
    assert saved.player.age == age + 1
    assert saved.player.ghost_soul_erosion_time_progress == pytest.approx((1/unit) % 1)
    assert (saved.player.ghost_soul_erosion_rate_pp > rate) == (unit == 1)


@pytest.mark.parametrize('operation,payload', [('guixu-action', {'action':'trapped_cultivate'}),
                                              ('advance', {'action':'cultivate','years':3})])
def test_trapped_training_stops_on_real_soul_death(api, operation, payload):
    engine, act = api
    game = trapped_game(engine)
    game.player.ghost_soul_erosion_rate_pp = 100
    engine.store.save(game)
    age = game.player.age
    act(game.id, operation, **payload)
    saved = engine._load(game.id)
    assert saved.player.age == age + 1
    assert not saved.player.alive
    assert '魂蚀' in saved.player.death_reason
    assert any(r.event_id=='SYS_GHOST_SOUL_DISPERSAL' for r in saved.history)


def test_trapped_batch_stops_when_host_dies_even_if_original_ghost_survives(api):
    engine, act = api
    game = trapped_game(engine, 4)
    host = dict(id='host', name='宿身', race='human', path='dao', spirit_root='supreme_metal',
                realm_index=3, layer=1, age=50, lifespan=51)
    enter_host_body(game.player, host)
    engine.store.save(game)
    age = game.player.age
    act(game.id, 'advance', action='rest', years=3)
    saved = engine._load(game.id)
    assert saved.player.age == age + 1
    assert saved.player.alive and saved.player.path=='ghost'
    assert saved.player.ghost_host_body is None


@pytest.mark.parametrize('rows', [[], [[0,True]], [[0,0]], [[1,1]], [[0,1],[100,1]], [[0,1],[0,2]]])
def test_catalog_rejects_ambiguous_plant_grade_rules(rows):
    document = copy.deepcopy(CONTENT_DOCUMENTS['crafting.json'])
    document['settings']['plant_tiers_by_years'] = rows
    with pytest.raises(ContentError): ContentRegistry._validate_crafting(document)

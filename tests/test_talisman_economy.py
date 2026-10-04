from cultivation_life.spatial_people import people
import copy
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.engine.actions.exploration import enter_scene
from cultivation_life.models import GameState
from cultivation_life.rules import add_item, has_item, max_mp, opportunity_required
from cultivation_life.runtime import encode_rng
from cultivation_life.system import spatial, talismans
from cultivation_life.talisman_content import catalog, local_catalog, WORLD_TIERS, DIMENSIONS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ready(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    gid = engine.create_game('符道验收', 'supreme_metal', 'dao', 1591, preset_id='core')['id']
    game = engine._load(gid)
    game.pending_event = game.active_trial = None
    game.player.lifespan = 100000
    add_item(game.player, 'spirit_stone', 10**12)
    game.player.mp = max_mp(game.player)
    engine.store.save(game)
    return engine, game


def recipe(game, tier=1):
    mats, methods = local_catalog(game)
    method = next(r for r in methods.values() if r['tier'] == tier)
    selected = [r for r in mats.values() if r['tier'] == tier][:2]
    return method, selected


def prepare(game):
    method, mats = recipe(game)
    game.player.talisman_methods.append(method['id'])
    for m in mats:
        add_item(game.player, m['id'], 5)
    return dict(method_id=method['id'], material1=mats[0]['id'], material2=mats[1]['id'], element='metal')


def test_catalog_all_world_tiers_and_seven_distinct_patterns():
    materials, methods = catalog()
    for world, (_, tiers) in WORLD_TIERS.items():
        for tier in tiers:
            rows = [r for r in methods.values() if r['world'] == world and r['tier'] == tier]
            assert len(rows) == 7
            assert sorted(len(r['strong']) for r in rows) == [1, 1, 1, 2, 2, 2, 3]
            assert len({tuple(r[d] for d in DIMENSIONS) for r in rows}) == 7
            assert all(r['name'].count('阶') == 1 for r in rows)
            assert len([r for r in materials.values() if r['world'] == world and r['tier'] == tier]) == 3


def test_failure_costs_experience_and_persisted_rng(ready, monkeypatch):
    e, g = ready
    payload = prepare(g)
    initial = copy.deepcopy(g)
    monkeypatch.setattr(talismans, 'success_chance', lambda *_: 0.)
    e.store.save(g)
    result = e.talisman_action(g.id, 'craft', payload)
    saved = e.store.load(g.id)
    assert not result['talismans']['rows']
    assert saved.player.art_experience['talisman'] > 0
    assert saved.player.mp < initial.player.mp
    assert has_item(saved.player, payload['material1'], 4) and not has_item(saved.player, payload['material1'], 5)
    assert saved.rng_state != initial.rng_state
    before = saved.to_dict()
    for _ in range(3):
        talismans.public(saved)
    assert saved.to_dict() == before


def test_experience_raises_chance_and_higher_tiers_are_harder(ready):
    _, g = ready
    novice = talismans.success_chance(g.player, 3)
    assert talismans.success_chance(g.player, 1) > novice
    g.player.art_experience['talisman'] = 50
    assert talismans.success_chance(g.player, 3) > novice
    g.player.art_experience['talisman'] = 10**8
    assert .9 < talismans.success_chance(g.player, 12) < 1


def test_cross_world_and_cross_tier_rejected_before_consumption(ready):
    _, g = ready
    payload = prepare(g)
    for material in ['talisman_demon_1_paper', 'talisman_human_2_paper']:
        add_item(g.player, material)
        before = g.to_dict()
        with pytest.raises(ValueError, match='同阶'):
            talismans.craft(g, dict(payload, material1=material))
        assert g.to_dict() == before
    g.player.world = 'demon'
    with pytest.raises(ValueError):
        talismans.craft(g, payload)


def test_quality_materials_effects_and_remaining_uses_affect_value(ready):
    _, g = ready
    method, mats = recipe(g)
    normal = talismans.product(method, mats, 'normal')
    perfect = talismans.product(method, mats, 'perfect')
    assert talismans.economic_value(perfect) > talismans.economic_value(normal)
    expensive = dict(normal, material_value=normal['material_value'] * 2)
    assert talismans.economic_value(expensive) > talismans.economic_value(normal)
    for dimension in DIMENSIONS:
        assert talismans.economic_value(dict(normal, **{dimension: normal[dimension] + 100})) > talismans.economic_value(normal)
    assert talismans.economic_value(dict(normal, uses=1)) < talismans.economic_value(normal)
    assert talismans.economic_value(dict(normal, uses=0)) == 0


def test_market_material_purchase_lock_and_both_sales(ready):
    e, g = ready
    e._refresh_world_market(g, random.Random(1))
    offer = next(r for r in g.market_offers if r['kind'] == 'talisman_material')
    e.store.save(g)
    result = e.buy_market_offer(g.id, offer['id'])
    assert any(r['id'] == offer['content_id'] for r in result['player']['inventory'])
    g = e._load(g.id)
    locked = next(r for r in g.market_offers if r['kind'] == 'talisman_material' and not r['sold'])
    locked['locked'] = True
    old = copy.deepcopy(locked)
    g.player.age += 1
    e._refresh_world_market(g, random.Random(2))
    assert old in g.market_offers
    method, mats = recipe(g)
    row = talismans.receive(g.player, talismans.product(method, mats, 'fine'))
    quote = talismans.sale_rows(g.player)[0]
    wallet = next(i.quantity for i in g.player.inventory if i.id == 'spirit_stone')
    e.store.save(g)
    result = e.talisman_action(g.id, 'sell', {'talisman_id': row['id']})
    assert not result['talismans']['rows']
    assert next(i['quantity'] for i in result['player']['inventory'] if i['id']=='spirit_stone') == wallet + quote['price']
    g = e._load(g.id)
    row = talismans.receive(g.player, talismans.product(method, mats, 'perfect'))
    g.auction_state = dict(status='black_market', world=g.player.world, location_id=g.player.location_id, lots=[], attendees=[])
    e.store.save(g)
    result = e.sell_black_market_asset(g.id, 'talisman', row['id'])
    assert not result['talismans']['rows']
    with pytest.raises(ValueError):
        e.sell_black_market_asset(g.id, 'talisman', row['id'])


def test_merchant_material_and_product_commission_deliver_exact_quote(ready):
    e, g = ready
    alliance = g.merchant_state['worlds']['human'][0]
    method, mats = recipe(g)
    for payload in [dict(kind='supply', material_category='talisman', definition_id=mats[0]['id'], quantity=3),
                    dict(kind='talisman', definition_id=method['id'], quantity=2, stars=3)]:
        quote = e._merchant_quote(g, alliance, payload)
        e._merchant_post(g, alliance, payload)
        order = g.merchant_state['posted'][-1]
        e._merchant_deliver_order(g, order)
        if payload['kind'] == 'supply':
            assert has_item(g.player, mats[0]['id'], 3)
        else:
            assert len(g.player.talismans) == 2
            for row in g.player.talismans:
                assert all(row[k] == v for k, v in quote['spec']['product'].items())
    board = e._merchant_board(g, alliance)
    assert any(t['kind'] == 'talisman' for t in board)
    assert any(t.get('material_category') == 'talisman' for t in board)


def test_merchant_handmade_delivery_requires_fresh_unused_talisman(ready):
    e, g = ready
    alliance = g.merchant_state['worlds']['human'][0]
    g.player.location_id = alliance['hq']
    e.store.save(g)
    e.merchant_action(g.id, 'join', {'alliance_id': alliance['id']})
    g = e._load(g.id)
    task = next(t for t in e._merchant_board(g, alliance) if t['kind'] == 'talisman' and t['stars'] == 1)
    e.merchant_action(g.id, 'accept', {'task_id': task['id']})
    g = e._load(g.id)
    method = catalog()[1][task['method_id']]
    mats = [r for r in catalog()[0].values() if r['world'] == 'human' and r['tier'] == method['tier']][:2]
    row = talismans.receive(g.player, talismans.product(method, mats, 'normal'))
    with pytest.raises(ValueError, match='亲自'):
        e._merchant_task_ready(g, g.merchant_state['active'])
    row['creator_id'] = g.id
    e.store.save(g)
    with patch.object(e, '_advance_world_year', return_value=True):
        e.merchant_action(g.id, 'work')
    assert not e._load(g.id).player.talismans


def test_rifts_hidden_before_nascent_multiple_and_decay_actual_failure(ready):
    e, g = ready
    rifts = [spatial.new_rift(g, random.Random(i), e.maps, controlled=True) for i in range(3)]
    assert not spatial.public(g)['rifts'] and spatial.public(g)['protection'] is None
    e.store.save(g)
    with pytest.raises(ValueError, match='元婴'):
        e.spatial_action(g.id, 'enter', {'target_id': rifts[0]['id']})
    g.player.realm_index = 4
    rifts[0]['kind'] = 'node'
    assert len(spatial.public(g)['rifts']) == 3
    assert spatial.public(g)['rifts'][0]['name'] == '空间节点'
    assert spatial.public(g)['rifts'][0]['passage_chance'] == .8
    g.player.age = rifts[0]['expires_age'] - 1
    assert spatial.rift_requirement(rifts[0], g.player.age) > 20
    e.store.save(g)
    assert not e.spatial_action(g.id, 'enter', {'target_id': rifts[0]['id']})['player']['alive']


def test_lost_resource_ceiling_lazy_stable_and_enforced(ready):
    e, g = ready
    scenes = [spatial.create_instance(g, random.Random(i), 'lost') for i in range(100)]
    assert {s['resource_ceiling'] for s in scenes} == {5, 6, 7, 8}
    scene = next(s for s in scenes if s['resource_ceiling'] == 5 and s['power_ceiling'] == 8)
    assert all(n['realm_index'] <= 5 for n in [n.to_dict() for n in people(g, scene)])
    rng = random.Random(8)
    enter_scene(e._exploration_dependencies(), g, scene, rng)
    g.player.realm_index, g.player.layer = 5, 9
    g.player.opportunity = opportunity_required(g.player) * 2
    g.rng_state = encode_rng(rng)
    e.store.save(g)
    assert max(r['tier'] for r in local_catalog(g)[0].values()) == 5
    assert GameState.from_dict(g.to_dict()).spatial_state == g.spatial_state
    for op in [lambda: e.advance(g.id, 'cultivate', 1), lambda: e.breakthrough(g.id)]:
        with pytest.raises(ValueError, match='资源稀薄'):
            op()
    # A higher-level visitor keeps their cultivation; only local progression stops.
    g.player.realm_index = 8
    e.store.save(g)
    assert e.get_game(g.id)['player']['realm_index'] == 8


def test_population_ceiling_is_independent_and_names_are_unique(ready):
    _, g = ready
    barren = None
    for seed in range(100):
        scene = spatial.create_instance(g, random.Random(seed), 'lost')
        rules = scene['population_rules']
        assert rules['npc_realm_ceiling'] <= scene['resource_ceiling'] <= scene['power_ceiling']
        assert max((n['realm_index'], n['layer']) for n in [n.to_dict() for n in people(g, scene)]) == (rules['npc_realm_ceiling'], 9)
        assert len({n['name'] for n in [n.to_dict() for n in people(g, scene)]}) == len([n.to_dict() for n in people(g, scene)])
        assert not any(char.isdigit() for n in [n.to_dict() for n in people(g, scene)] for char in n['name'])
        if scene['resource_ceiling'] == 8 and rules['abundance'] == 'barren':
            barren = scene
    assert barren and barren['population_rules']['npc_realm_ceiling'] < 8
    assert GameState.from_dict(g.to_dict()).spatial_state == g.spatial_state


def test_shared_names_reproducible_and_larger_than_old_pool():
    from cultivation_life.npc_names import person_name, SURNAMES, GIVEN_NAMES
    assert len(set(SURNAMES)) > 50 and len(set(GIVEN_NAMES)) > 80
    first, second = random.Random(59), random.Random(59)
    assert [person_name(first) for _ in range(50)] == [person_name(second) for _ in range(50)]
    used = set()
    for _ in range(500):
        name = person_name(first, used)
        assert name not in used
        used.add(name)


def test_instance_power_ceiling_rejects_excess_without_lowering_cultivation(ready):
    e, g = ready
    rng = random.Random(6)
    scene = spatial.create_instance(g, rng, 'lost')
    scene.update(power_ceiling=7, resource_ceiling=5)
    enter_scene(e._exploration_dependencies(), g, scene, rng)
    g.player.realm_index, g.player.layer = 6, 1
    e.store.save(g)
    view = e.get_game(g.id)
    assert view['player']['world'] == 'lost' and view['player']['realm_index'] == 6
    g = e._load(g.id)
    g.player.realm_index, g.player.layer = 7, 9
    e.store.save(g)
    assert e.get_game(g.id)['player']['world'] == 'lost'
    g = e._load(g.id)
    g.player.realm_index, g.player.layer = 8, 1
    e.store.save(g)
    view = e.get_game(g.id)
    assert view['player']['world'] == 'spirit' and view['player']['realm_index'] == 8
    assert not view['spatial']['inside']


def test_population_excess_is_rare_and_never_crosses_a_major_realm():
    from cultivation_life.system.spatial_population import generation_profile, initial_rank
    rng = random.Random(1591)
    profile = generation_profile(rng, power_ceiling=8, cultivation_ceiling=5, cultivation_layer=3)
    assert profile['npc_realm_ceiling'] == 5 and profile['npc_layer_ceiling'] == 9
    ranks = [initial_rank(rng, profile, i) for i in range(10000)]
    exceeded = [rank for rank in ranks if rank > (5, 3)]
    assert 350 < len(exceeded) < 650
    assert all(rank[0] == 5 and rank[1] <= 9 for rank in exceeded)
    late = generation_profile(random.Random(1591), 8, 5, 9)
    assert late['above_cultivation_chance'] == 0
    assert all(initial_rank(rng, late, i) <= (5, 9) for i in range(1000))


@pytest.mark.parametrize('path', ['dao', 'demonic', 'ghost', 'monster', 'confucian', 'buddhist'])
def test_lost_quick_start_all_paths_maps_and_training(ready, path):
    e, _ = ready
    view = e.create_game('失落开局', 'supreme_metal', path, 1591, preset_id='lost_world',
                         monster_species_id='serpent' if path == 'monster' else None)
    g = e._load(view['id'])
    assert g.player.path == path and g.player.world == 'lost' and g.player.realm_index == 3
    assert g.player.technique.path == path or path == 'dao'
    assert len(g.spatial_state['instances']) == 1 and not g.market_offers
    scene = spatial.current(g)
    assert len(scene['locations']) == 4 and len(scene['edges']) == 6
    assert view['map']['world_name'] == scene['name']
    sources = {'spirit', 'demon', 'monster', 'yin'}
    for place in scene['locations']:
        assert set(place['qi_concentrations']) == sources == set(place['qi_gain_efficiencies'])
        assert all(value > 0 for value in place['qi_concentrations'].values())
        assert place['description'] and place['themes'] and place['combat_terrain']
    for technique in scene['techniques']:
        assert technique['sources'] and all(source in sources for source in technique['sources'])
    previous_qi = sum(g.player.qi_experience.values())
    moved = e.spatial_action(g.id, 'move', {'target_id': scene['locations'][1]['id']})
    assert moved['spatial']['scene']['location_id'] == scene['locations'][1]['id']
    e.advance(g.id, 'cultivate', 1)
    loaded = e._load(g.id)
    assert sum(loaded.player.qi_experience.values()) > previous_qi
    assert spatial.current(loaded)['locations'] == scene['locations']
    if path == 'monster':
        spatial.guard(loaded, 'evolve_monster')


def test_lost_quick_start_requires_species_and_rejects_unknown_path(ready):
    e, _ = ready
    for path, message in [('monster', '种属'), ('invalid', '道途')]:
        with pytest.raises(ValueError, match=message):
            e.create_game('失落开局', 'supreme_metal', path, 1591, preset_id='lost_world')


def test_legacy_spatial_map_null_qi_is_safe_and_read_only(ready):
    e, g = ready
    scene = spatial.create_instance(g, random.Random(1591), 'lost')
    enter_scene(e._exploration_dependencies(), g, scene, random.Random(1))
    for place in scene['locations']:
        place['qi_gain_efficiencies'] = None
        place['qi_concentrations'] = {'spirit': None, 'demon': float('nan')}
    before = copy.deepcopy(g.to_dict())
    view = spatial.public(g)
    assert all(set(p['qi_gain_efficiencies'].values()) == {1.} for p in view['scene']['locations'])
    assert scene['locations'][0]['qi_gain_efficiencies'] is None
    assert spatial.current_qi(g) == dict.fromkeys(['spirit', 'demon', 'monster', 'yin'], 1.)
    assert before['spatial_state']['current'] == g.spatial_state['current']

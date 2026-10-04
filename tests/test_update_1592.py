"""Release contracts: soul occupancy, prices and isolated personal systems."""
import copy
import random
from pathlib import Path
from unittest.mock import Mock

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.rules import add_item
from cultivation_life.spatial_people import people, accessible
from cultivation_life.system import spatial, talismans
from cultivation_life.system.demonic.soul_risk import refinement_risk
from cultivation_life.system.spatial_capabilities import scope_key, site_key, PERSONAL_COMMANDS
from cultivation_life.engine.actions.exploration import enter_scene
from cultivation_life.talisman_content import catalog

ROOT = Path(__file__).resolve().parents[1]


def start(tmp_path, path='dao', lost=True):
    engine = GameEngine(ROOT, tmp_path)
    shown = engine.create_game('本地验收', 'supreme_metal', path, 1592,
                               preset_id='lost_world' if lost else 'core',
                               monster_species_id='serpent' if path == 'monster' else None)
    game = engine.store.load(shown['id'])
    game.player.path = path
    game.pending_event = game.active_trial = None
    game.player.lifespan = 100000
    add_item(game.player, 'spirit_stone', 10**10)
    engine.store.save(game)
    return engine, game


@pytest.mark.parametrize('realm', range(1, 13))
def test_safe_soul_capacity_and_exponential_excess(tmp_path, realm):
    e, g = start(tmp_path, 'demonic', False)
    p = g.player
    p.realm_index = realm
    p.foreign_souls = [dict(strength=10000, refined=False) for _ in range(realm-1)]
    rng = Mock()
    e._annual_demonic_update(g, rng)
    rng.random.assert_not_called()
    assert refinement_risk(p, {})['annual_chance'] == 0
    for excess, chance in enumerate([.025, .075, .175, .375, .775, .95], 1):
        p.foreign_souls.append(dict(strength=1, refined=False))
        risk = refinement_risk(p, {})
        assert risk['safe_capacity'] == realm-1
        assert risk['excess'] == excess and risk['annual_chance'] == chance
    p.foreign_souls.extend([dict(strength=1, refined=True)]*100)
    assert refinement_risk(p, {}) == risk


def test_materials_reduced_more_than_products_and_legacy_repriced():
    mats, recipes = catalog()
    for method in recipes.values():
        selected = [r for r in mats.values() if r['world'] == method['world'] and r['tier'] == method['tier']][:2]
        product = talismans.product(method, selected, 'normal')
        old_cost = sum(round(round(24*4.3**(r['tier']-1))*r['quality']) for r in selected)
        # Prior release used the paid material cost with the same effect premium.
        old_value = round(old_cost * (1+sum(product[d] for d in ('power','protection','assistance'))/100))
        assert product['material_value'] / old_cost < talismans.economic_value(product) / old_value < 1
        legacy = dict(product, material_value=old_cost)
        legacy.pop('pricing_version')
        assert talismans.economic_value(legacy) <= talismans.economic_value(product) + 2


def test_black_market_finished_talismans_freeze_stats_and_unique_ids(tmp_path):
    e, g = start(tmp_path, lost=False)
    g.auction_state = dict(status='black_market', world=g.player.world, location_id=g.player.location_id, lots=[], attendees=[])
    e.store.save(g)
    e.search_black_market(g.id, '符')
    saved = e.store.load(g.id)
    row = next(r for r in saved.auction_state['black_market_results'] if r['kind']=='talisman')
    quoted = copy.deepcopy(row['talisman_instance'])
    wallet = next(i.quantity for i in saved.player.inventory if i.id=='spirit_stone')
    e.buy_black_market_item(g.id, row['id'], 2)
    saved = e.store.load(g.id)
    assert len({r['id'] for r in saved.player.talismans}) == 2
    assert all({k:v for k,v in r.items() if k!='id'} == quoted for r in saved.player.talismans)
    assert next(i.quantity for i in saved.player.inventory if i.id=='spirit_stone') == wallet-row['price']*2


@pytest.mark.parametrize('path', ['dao','demonic','confucian','buddhist','ghost','monster'])
def test_lost_paths_restore_relationship_panel_and_authoritative_people(tmp_path, path):
    e, g = start(tmp_path, path)
    assert all(hasattr(e, name) for name in PERSONAL_COMMANDS)
    shown = e.get_game(g.id)
    assert 'relationship' in shown['spatial']['panels']
    assert len(shown['world_npcs']) == 9
    npc = people(g)[0]
    age = npc.age
    e.contact_action(g.id, npc.id, 'improve')
    g = e.store.load(g.id)
    assert people(g)[0].affinity > 0
    assert 'npcs' not in spatial.current(g)
    before = copy.deepcopy(g.rng_state)
    e.get_game(g.id)
    assert e.store.load(g.id).rng_state == before
    e.advance(g.id, 'rest', 1)
    g = e.store.load(g.id)
    assert people(g)[0].age == age+1
    assert GameState.from_dict(g.to_dict()).to_dict() == g.to_dict()


def test_lost_instances_cannot_contact_or_age_other_people(tmp_path):
    e, g = start(tmp_path)
    first = spatial.current(g)
    npc = people(g)[0]
    npc.affinity = 100
    e.store.save(g)
    e.contact_action(g.id, npc.id, 'friend')
    g = e.store.load(g.id)
    assert g.player.dao_friends[0]['id'] == npc.id
    age = people(g)[0].age
    second = spatial.create_instance(g, random.Random(7), 'lost')
    enter_scene(e._exploration_dependencies(), g, second, random.Random(7))
    assert not accessible(g, people(g, first)[0])
    e.store.save(g)
    with pytest.raises(ValueError):
        e.contact_action(g.id, npc.id, 'improve')
    with pytest.raises(ValueError):
        e.relationship_violence(g.id, 'friend', npc.id)
    e.advance(g.id, 'rest', 1)
    assert people(e.store.load(g.id), first)[0].age == age


def test_sage_lost_local_found_and_teach(tmp_path):
    e, g = start(tmp_path, 'confucian')
    combo = dict(classic='guliang', philosophy='mind', practice='statecraft', script='old_text')
    shown = e.sage_doctrine_action(g.id, 'found', dict(name='失落之学', combo=combo))
    assert shown['sage_system']['membership_id']
    g = e.store.load(g.id)
    outside = copy.deepcopy(g.sage_state['worlds']['human'])
    shown = e.advance(g.id, 'sage_preach', 1)
    assert shown['sage_system']['last_action']['years'] == 1
    assert e.store.load(g.id).sage_state['worlds']['human'] == outside


def test_buddhist_lost_temple_annual_and_instance_isolation(tmp_path):
    from cultivation_life.system.buddhist_system import site_state
    e, g = start(tmp_path, 'buddhist')
    e.buddhist_action(g.id, 'temple')
    g = e.store.load(g.id)
    first, location = scope_key(g), site_key(g)
    site = site_state(g.buddhist_state, first, location)
    assert site['temple'] == 1
    site['followers'] = 1000
    e.store.save(g)
    e.advance(g.id, 'rest', 1)
    g = e.store.load(g.id)
    assert g.buddhist_state['last_settlement']['income'] > 0
    frozen = copy.deepcopy(g.buddhist_state['worlds'][first])
    second = spatial.create_instance(g, random.Random(8), 'lost')
    enter_scene(e._exploration_dependencies(), g, second, random.Random(8))
    e.store.save(g)
    shown = e.get_game(g.id)
    assert shown['buddhist_system']['site']['temple'] == 0
    e.advance(g.id, 'rest', 1)
    assert e.store.load(g.id).buddhist_state['worlds'][first] == frozen

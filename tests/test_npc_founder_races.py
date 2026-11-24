"""NPC-founded organizations use actual loaded local races and preserve their identity."""
import copy
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.content_registry import RACE_DEFINITIONS
from cultivation_life.engine import GameEngine
from cultivation_life.engine.world import npcs
from cultivation_life.engine.composition.strategic_war import bind
from cultivation_life.system.race_faction_directory import unformed_factions
from cultivation_life.system.strategic_war.materialization import materialize


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def setup(tmp_path_factory):
    engine = GameEngine(ROOT, tmp_path_factory.mktemp('npc-founder-races')/'saves')
    games = {}
    for world in ('human', 'demon', 'spirit', 'true_demon', 'monster_realm', 'phantom_underworld', 'nether'):
        rank = 9 if world == 'nether' else 4 if world in {'human', 'demon'} else 7
        made = engine.create_game('族群建宗验收', 'supreme_metal', 'dao', 1411,
                                 custom_start=dict(world=world, realm_index=rank, layer=1))
        games[world] = engine._load(made['id'])
    return engine, games


@pytest.mark.parametrize('kind', ['sect', 'family'])
@pytest.mark.parametrize('world,race', [
    ('human', 'monster'), ('spirit', 'woodborn'), ('true_demon', 'blood_demon'),
    ('monster_realm', 'foxkin'), ('phantom_underworld', 'dreamfox'),
    ('nether', 'worldtree_descendant'),
])
def test_founder_and_allegiance_follow_loaded_local_race_and_survive_reload(setup, world, race, kind):
    engine, games = setup
    game = copy.deepcopy(games[world])
    if race not in RACE_DEFINITIONS:
        pytest.fail('This regression requires the normal loaded official race catalog')
    pool = [key for key, row in RACE_DEFINITIONS.items() if world in row.get('worlds', [])]
    rng = random.Random(1411)
    original_choice = rng.choice
    def choose(rows):
        if rows == ['sect', 'family']:
            return kind
        if rows == pool:
            return race
        return original_choice(rows)
    before = set(game.sects)
    listed = list(unformed_factions(game, world, race, include_presets=False))
    news = []
    with patch.object(rng, 'random', return_value=0), patch.object(rng, 'choice', side_effect=choose):
        engine._maybe_npc_found_power(game, rng, news)
    identity, = set(game.sects)-before
    org = game.sects[identity]
    founder = next(n for n in org.npcs if n.id == org.founder_npc_id)
    assert org.kind == kind and org.allegiance_race == founder.race == race
    if kind == 'sect' and engine._world_supports(world, 'races'):
        assert (org.id, org.name) == (listed[0]['id'], listed[0]['name'])
        shown = engine._public_race_system(game)['races'][race]['supported_factions']
        assert [r['active'] for r in shown if r['id'] == org.id] == [True]
    assert founder.faction_id == identity and founder.world == org.world == world
    assert len(org.npcs) == 3 and all(n.race in pool for n in org.npcs)
    assert org.location_id == founder.location_id and news
    engine.store.save(game)
    restored = engine._load(game.id).sects[identity]
    assert restored.allegiance_race == race
    assert next(n for n in restored.npcs if n.id == restored.founder_npc_id).race == race


@pytest.mark.parametrize('world', ['spirit', 'true_demon', 'nether'])
def test_unavailable_race_content_does_not_found_human_fallback_or_consume_rng(setup, monkeypatch, world):
    engine, games = setup
    game = copy.deepcopy(games[world])
    before = copy.deepcopy(game.to_dict())
    monkeypatch.setattr(npcs, 'RACE_DEFINITIONS', {})
    rng = random.Random(1411)
    rng_before = rng.getstate()
    news = []
    engine._maybe_npc_found_power(game, rng, news)
    assert game.to_dict() == before and rng.getstate() == rng_before and not news


def test_world_without_race_catalog_or_politics_preserves_native_default(setup):
    engine, games = setup
    game = copy.deepcopy(games['demon'])
    before = set(game.sects)
    rng = random.Random(1411)
    with patch.object(rng, 'random', return_value=0):
        engine._maybe_npc_found_power(game, rng, [])
    identity, = set(game.sects)-before
    org = game.sects[identity]
    assert org.allegiance_race == 'human'
    assert next(n for n in org.npcs if n.id == org.founder_npc_id).race == 'human'


@pytest.mark.parametrize('world', ['spirit', 'true_demon', 'monster_realm', 'phantom_underworld', 'nether'])
def test_race_directory_on_first_visit_and_after_reload(setup, world):
    engine, games = setup
    game = copy.deepcopy(games[world])
    before = set(game.sects), game.rng_state, copy.deepcopy(game.strategic_war_state)
    def seeded(view):
        return {race: [(r['id'], r['name']) for r in faction['supported_factions'] if r.get('origin') == 'seeded']
                for race, faction in view['races'].items()}
    first = seeded(engine._public_race_system(game))
    assert first and all(len(rows) == 2 for rows in first.values())
    assert len({identity for rows in first.values() for identity, _ in rows}) == 2 * len(first)
    assert (set(game.sects), game.rng_state, game.strategic_war_state) == before
    engine.store.save(game)
    assert seeded(engine.get_game(game.id)['race_system']) == first
    game.seed += 1
    assert seeded(engine._public_race_system(game)) != first


def test_mobilization_uses_directory_identity_and_extinct_sects_stay_gone(setup):
    engine, games = setup
    game = copy.deepcopy(games['spirit'])
    race = 'woodborn'
    listed = list(unformed_factions(game, 'spirit', race))
    deps, rng = bind(engine), random.Random(542)
    for entry in listed:
        org = materialize(deps, game, 'spirit', race, rng)
        assert (org.id, org.name, org.allegiance_race) == (entry['id'], entry['name'], race)
        assert org.npcs and game.strategic_war_state['materialized'][org.id]['paid'] > 0
    org.allegiance_race = 'seafolk'
    view = engine._public_race_system(game)['races']
    assert org.id not in {r['id'] for r in view[race]['supported_factions']}
    assert [r['active'] for r in view['seafolk']['supported_factions'] if r['id'] == org.id] == [True]
    for entry in listed:
        game.sects[entry['id']].extinct = True
    assert not list(unformed_factions(game, 'spirit', race))
    assert not engine._public_race_system(game)['races'][race]['supported_factions']

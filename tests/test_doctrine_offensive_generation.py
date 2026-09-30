"""A seed must offer an offensive path without rerolling its saved catalog."""
import copy
from unittest.mock import patch

import pytest

from cultivation_life.content_registry import CONTENT_DOCUMENTS
from cultivation_life.system.combat.contracts import VoisinageDefinition
from cultivation_life.system.doctrine.effects import ensure_offensive_doctrine, enrich_effects
from cultivation_life.system.doctrine.generation import generate
from cultivation_life.system.doctrine.provider import ensure
from scripts.calibrate_immortal_trials import fixture

CONFIG = CONTENT_DOCUMENTS['doctrines.json']
POWER = {r: 10 ** r for r in range(9, 13)}


def offensive(definition):
    return all(any(e.kind == 'strike' and e.target == 'enemy' and e.power > 0
                   for e in VoisinageDefinition(**stage['voisinage']).actions())
               for stage in definition['stages'][3:])


def strip_random_strikes(definitions):
    for definition in definitions.values():
        if definition['fixed']:
            continue
        for stage in definition['stages'][3:]:
            domain = stage['voisinage']
            domain['effect'] = 'seal'
            for effect in domain['effects']:
                if effect['kind'] == 'strike':
                    effect['kind'] = 'seal'


@pytest.mark.parametrize('seed', [0, 1, 2, 42, 7429, 903001, 2147483647])
def test_each_seed_has_a_random_offensive_path_from_first_unlock(seed):
    catalog = generate(seed, CONFIG, POWER)
    assert catalog['offensive_schema'] == 1
    assert any(offensive(d) for d in catalog['definitions'].values() if not d['fixed'])


def test_generation_repairs_the_all_nonoffensive_draw_without_replacing_books():
    captured = {}

    def force_no_random_strikes(definitions):
        enrich_effects(definitions)
        strip_random_strikes(definitions)
        captured.update(copy.deepcopy(definitions))

    with patch('cultivation_life.system.doctrine.effects.enrich_effects', force_no_random_strikes):
        catalog = generate(7429, CONFIG, POWER)
    definitions = catalog['definitions']
    changed = [k for k in definitions if definitions[k] != captured[k]]
    assert len(changed) == 1
    key = changed[0]
    assert not definitions[key]['fixed'] and offensive(definitions[key])
    for stage in captured[key]['stages'][3:]:
        new = definitions[key]['stages'][stage['level'] - 1]['voisinage']
        assert new['effects'][:-1] == stage['voisinage']['effects']
        stage['voisinage']['effects'].append(new['effects'][-1])
    assert definitions == captured  # Only one additive action per unlocked stage.
    before = copy.deepcopy(definitions)
    assert not ensure_offensive_doctrine(definitions, 7429, catalog['version'])
    assert definitions == before


def test_old_catalog_migration_is_deterministic_one_time_and_keeps_progress():
    game = fixture('three_corpses', field_rank=12, doctrine_level=8)
    game.doctrine_state.pop('offensive_schema')
    strip_random_strikes(game.doctrine_state['definitions'])
    original = copy.deepcopy(game)
    assert ensure(game)
    assert game.doctrine_state['player'] == original.doctrine_state['player']
    assert game.rng_state == original.rng_state
    assert game.active_trial == original.active_trial
    clone = copy.deepcopy(original)
    assert ensure(clone)
    assert clone.doctrine_state == game.doctrine_state
    assert any(offensive(d) for d in game.doctrine_state['definitions'].values() if not d['fixed'])
    with patch('cultivation_life.system.doctrine.effects.ensure_offensive_doctrine',
               side_effect=AssertionError('Catalog scan repeated on an ordinary access')):
        assert not ensure(game)


def test_existing_suitable_catalog_is_not_modified():
    catalog = generate(7429, CONFIG, POWER)
    before = copy.deepcopy(catalog['definitions'])
    assert not ensure_offensive_doctrine(catalog['definitions'], 7429, catalog['version'])
    assert catalog['definitions'] == before

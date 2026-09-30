import copy
from unittest.mock import patch

import pytest

from test_immortal_cultivation import prepared
from cultivation_life.models import Technique
from cultivation_life.rules import learn_technique, assign_technique, upgrade_known_technique
from cultivation_life.system.doctrine.fusion import compile_manual, manual_id
from cultivation_life.system.doctrine.provider import config
from cultivation_life.system.doctrine.progression import source


def ready(prepared):
    engine, game, _ = prepared
    d = next(d for d in game.doctrine_state['definitions'].values() if len(d['manuals']) >= 6)
    game.player.realm_index = 12
    for book in d['manuals']:
        learn_technique(game.player, Technique(**copy.deepcopy(book)))
    record = game.doctrine_state['player']
    record['progress'][d['id']] = {'level': 4, 'experience': 0}
    record['active'] = d['id']
    engine.store.save(game)
    return engine, game, d


def test_fusion_preserves_originals_is_stable_and_stronger_at_every_level(prepared):
    engine, game, d = ready(prepared)
    before = game.player.immortal_traces
    expected = compile_manual(game.seed, d, config()['words'])
    assert expected == compile_manual(game.seed, d, config()['words'])
    shown = engine.doctrine_action(game.id, 'fuse', d['id'])
    saved = engine.store.load(game.id)
    fused = next(t for t in saved.player.known_techniques if t.id == manual_id(d['id']))
    assert saved.player.immortal_traces == before - 24
    assert {b['id'] for b in d['manuals']} <= {t.id for t in saved.player.known_techniques}
    assert sum(t.id == fused.id for t in saved.player.known_techniques) == 1
    assert next(r for r in shown['doctrines']['rows'] if r['id'] == d['id'])['fusion']['total'] == len(d['manuals'])
    for level in range(1, 10):
        fused.level = level
        for book in d['manuals']:
            old = Technique(**{**book, 'level':level})
            for stat in ('combat_bonus','hp_bonus','mp_bonus','opportunity_bonus'):
                assert getattr(fused,stat)*fused.stat_multiplier(stat) > getattr(old,stat)*old.stat_multiplier(stat)
    with pytest.raises(ValueError, match='已经合练'):
        engine.doctrine_action(game.id, 'fuse', d['id'])


@pytest.mark.parametrize('missing', ['manual', 'realm', 'traces', 'converted', 'short'])
def test_fusion_rejects_missing_prerequisites_without_payment(prepared, missing):
    engine, game, d = ready(prepared)
    if missing == 'manual': game.player.known_techniques = [t for t in game.player.known_techniques if t.id != d['manuals'][-1]['id']]
    if missing == 'realm': game.player.realm_index = max(b['grade'] for b in d['manuals']) - 1
    if missing == 'traces': game.player.immortal_traces = 23
    if missing == 'converted': game.player.immortal_power_converted = False; game.player.immortal_conversion_stage = 0
    if missing == 'short': d = next(d for d in game.doctrine_state['definitions'].values() if len(d['manuals']) <= 5)
    engine.store.save(game)
    with pytest.raises(ValueError): engine.doctrine_action(game.id, 'fuse', d['id'])
    assert engine.store.load(game.id).player.immortal_traces == game.player.immortal_traces


def test_trace_paid_once_interruption_save_and_equipped_level_sync(prepared):
    engine, game, d = ready(prepared)
    engine.doctrine_action(game.id, 'fuse', d['id'])
    game = engine.store.load(game.id)
    record = game.doctrine_state['player']
    record['fusion_target'] = d['id']
    fused = next(t for t in game.player.known_techniques if t.id == manual_id(d['id']))
    assign_technique(game.player, copy.deepcopy(fused), 'main')
    traces = game.player.immortal_traces
    engine._begin_doctrine_action(game, 'doctrine_fusion_study', commit=True)
    engine._finish_doctrine_action(game, 'doctrine_fusion_study', 90)
    engine.store.save(game)
    game = engine._load(game.id)
    engine._begin_doctrine_action(game, 'doctrine_fusion_study', commit=True)
    engine._finish_doctrine_action(game, 'rest', 1000)
    assert game.doctrine_state['player']['fusion'][d['id']]['experience'] == 90
    engine._finish_doctrine_action(game, 'doctrine_fusion_study', 90)
    assert game.player.immortal_traces == traces - 8
    assert game.player.technique.level == 2
    assert next(t for t in game.player.known_techniques if t.id == fused.id).level == 2
    assert game.doctrine_state['player']['progress'][d['id']]['level'] == 4
    with pytest.raises(ValueError, match='仙痕参悟'): upgrade_known_technique(game.player, fused.id)
    # No doctrine annotations and no matching manual copies needed for Lv3.
    game.doctrine_state['player']['annotations'] = {}
    engine._begin_doctrine_action(game, 'doctrine_fusion_study', commit=True)
    engine._finish_doctrine_action(game, 'doctrine_fusion_study', 10000)
    assert game.player.technique.level == 3
    assert game.player.immortal_traces == traces - 8 - 12


def test_fusion_boost_is_selected_only_and_capped_by_doctrine_level(prepared):
    engine, game, d = ready(prepared)
    record, definitions = game.doctrine_state['player'], game.doctrine_state['definitions']
    base = source(record, definitions, 'celestial').voisinages[0]
    record['fusion'] = {d['id']:{'level':9,'experience':0}}
    boosted = source(record, definitions, 'celestial').voisinages[0]
    record['fusion'][d['id']]['level'] = 4
    assert source(record, definitions, 'celestial').voisinages[0] == boosted
    assert boosted != base and boosted.id == base.id
    assert boosted.name == '真·' + base.name
    assert {e.kind for e in boosted.actions()} == {e.kind for e in base.actions()}
    assert not source(record, definitions, 'spirit').voisinages
    record['progress'][d['id']]['level'] = 5
    record['origin'] = 'another'
    with pytest.raises(ValueError, match='非本源'): source(record, definitions, 'celestial')


def test_actual_study_dispatches_elapsed_action(prepared):
    engine, game, d = ready(prepared)
    engine.doctrine_action(game.id, 'fuse', d['id'])
    with patch.object(engine, 'advance', wraps=engine.advance) as advance:
        shown = engine.doctrine_action(game.id, 'study_fusion', d['id'])
    advance.assert_called_once_with(game.id, 'doctrine_fusion_study', 1)
    fused = next(r['fusion'] for r in shown['doctrines']['rows'] if r['id'] == d['id'])
    assert fused['level'] == 2 or fused['experience'] > 0

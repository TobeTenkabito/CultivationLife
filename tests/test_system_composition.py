"""Regressions for removing Tianji and intrigue from the engine MRO."""
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Player
from cultivation_life.storage import SaveStore
from cultivation_life.system import intrigue_system, tianji_system
from cultivation_life.system.intrigue.dependencies import IntrigueGovernanceDependencies
from cultivation_life.system.intrigue.governance import _intrigue_has_decision_authority


ROOT = Path(__file__).resolve().parents[1]


def test_engine_no_longer_inherits_tianji_or_intrigue():
    assert not {tianji_system.TianjiSystemMixin, intrigue_system.IntrigueSystemMixin} & set(GameEngine.__mro__)


@pytest.mark.parametrize('member,change,expected', [
    ('player', 'none', True), ('player', 'wrong_faction', False),
    ('player', 'wrong_world', False), ('player', 'dead', False),
    ('player', 'below_threshold', False), ('player', 'entity_missing', True),
    ('npc', 'none', True), ('npc', 'dead', False), ('npc', 'below_threshold', False),
    ('npc', 'prison', False), ('npc', 'missing', False),
])
def test_decision_authority_preserves_player_and_npc_boundaries(member, change, expected):
    unrelated = Mock(side_effect=AssertionError('Unexpected collaborator'))
    arguments = {field.name: unrelated for field in fields(IntrigueGovernanceDependencies)}
    game = GameState('authority', 7, Player('Player', 'none'), '', '')
    game.player.alive = change != 'dead'
    arguments.update(_get_PLAYER_ID=lambda: 'player', _intrigue_decision_threshold=lambda kind: 4)
    if member == 'player':
        entity = None if change == 'entity_missing' else SimpleNamespace(
            world='celestial' if change == 'wrong_world' else game.player.world)
        arguments.update(
            _intrigue_player_faction_id=lambda *args: 'other' if change == 'wrong_faction' else 'sect',
            _actual_player_realm=lambda player: (3 if change == 'below_threshold' else 4, 1),
            _intrigue_entity=lambda *args: entity,
        )
    else:
        npc = None if change == 'missing' else SimpleNamespace(
            id='npc', alive=change != 'dead', realm_index=3 if change == 'below_threshold' else 4)
        arguments.update(
            _intrigue_find_npc=lambda *args: npc,
            _intrigue_is_imprisoned=lambda *args: change == 'prison',
        )
    assert _intrigue_has_decision_authority(
        IntrigueGovernanceDependencies(**arguments), game, 'sect', 'sect', member,
    ) is expected
    unrelated.assert_not_called()


def test_engine_configuration_hooks_still_resolve_after_construction(tmp_path, monkeypatch):
    engine = GameEngine(ROOT, tmp_path)
    game = GameState('hooks', 7, Player('Player', 'none'), '', '')
    monkeypatch.setattr(tianji_system, 'tianji_content_available', lambda: False)
    assert engine._ensure_tianji_state(game) is False
    rules = {'enabled': False, 'artifact_count': 0}
    monkeypatch.setattr(tianji_system, 'tianji_config', lambda: rules)
    assert engine._tianji_config() is rules
    monkeypatch.setattr(tianji_system, '_tianji_effect_description', lambda effect: 'replacement description')
    assert engine._tianji_public_effect({'name': 'test'})['description'] == 'replacement description'
    monkeypatch.setattr(intrigue_system, 'intrigue_rules', lambda: {})
    assert engine._intrigue_enabled() is False
    monkeypatch.setattr(intrigue_system, 'intrigue_rules', lambda: {'decision_thresholds': {'sect': 7}})
    assert engine._intrigue_enabled() is True
    assert engine._intrigue_decision_threshold('sect') == 7


def test_bindings_keep_late_method_and_storage_replacements(tmp_path, monkeypatch):
    engine = GameEngine(ROOT, tmp_path / 'original')
    replacement = SaveStore(tmp_path / 'replacement')
    game = GameState('authority', 7, Player('Player', 'none'), '', '')
    monkeypatch.setattr(engine, 'store', replacement)
    monkeypatch.setattr(engine, '_load', lambda key: game)
    monkeypatch.setattr(engine, '_intrigue_decision_threshold', lambda kind: 4)
    monkeypatch.setattr(engine, '_intrigue_player_faction_id', lambda *args: 'sect')
    monkeypatch.setattr(engine, '_intrigue_entity', lambda *args: None)
    monkeypatch.setattr(engine, '_actual_player_realm', lambda player: (4, 1))
    assert engine._intrigue_has_decision_authority(game, 'sect', 'sect') is True
    monkeypatch.setattr(engine, '_intrigue_decision_threshold', lambda kind: 5)
    assert engine._intrigue_has_decision_authority(game, 'sect', 'sect') is False
    for deps in (engine._tianji_dependencies.forging, engine._intrigue_dependencies.governance):
        assert deps.store is replacement
        assert deps._load(game.id) is game


def test_subclass_overrides_and_super_calls_survive_composition(tmp_path):
    class Specialized(GameEngine):
        @staticmethod
        def _tianji_config():
            return {'specialized': True}

        def _intrigue_decision_threshold(self, kind):
            return super()._intrigue_decision_threshold(kind) + 1

    engine = Specialized(ROOT, tmp_path)
    assert engine._tianji_dependencies.generation._tianji_config() == {'specialized': True}
    assert engine._intrigue_dependencies.governance._intrigue_decision_threshold('sect') == (
        GameEngine._intrigue_decision_threshold(engine, 'sect') + 1
    )


def test_legacy_consumer_keeps_permission_checks_and_static_helpers():
    class Legacy(intrigue_system.IntrigueSystemMixin, tianji_system.TianjiSystemMixin):
        def _intrigue_decision_threshold(self, kind):
            return 4

        def _intrigue_player_faction_id(self, game, kind):
            return 'sect'

        def _intrigue_entity(self, game, kind, faction_id):
            return None

        def _actual_player_realm(self, player):
            return (4, 1)

    game = GameState('legacy', 7, Player('Player', 'none'), '', '')
    assert Legacy()._intrigue_has_decision_authority(game, 'sect', 'sect') is True
    assert Legacy._tianji_tag_similarity({'metal': 2}, {'metal': 1}) == 0.5

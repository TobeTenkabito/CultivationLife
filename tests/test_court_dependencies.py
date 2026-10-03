from dataclasses import fields
from pathlib import Path
from unittest.mock import Mock

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Player
from cultivation_life.storage import SaveStore
from cultivation_life.system.court.dependencies import CourtLifecycleDependencies
from cultivation_life.system.court.lifecycle import _court_pay_stipend
from cultivation_life.system.heavenly_court_system import HeavenlyCourtSystemMixin
from cultivation_life.system.court_governance import CourtGovernanceMixin
from cultivation_life.system.court_lifecycle import CourtLifecycleMixin
from cultivation_life.system.yaochi_system import YaochiMixin, config
from tools.check_module_dependencies import violations


ROOT = Path(__file__).resolve().parents[1]


def test_engine_does_not_inherit_court_or_yaochi_gameplay():
    assert not {HeavenlyCourtSystemMixin, CourtGovernanceMixin, CourtLifecycleMixin,
                YaochiMixin} & set(GameEngine.__mro__)


def test_court_stipend_can_run_without_an_engine():
    unrelated = Mock(side_effect=AssertionError('Unexpected collaborator'))
    arguments = {field.name: unrelated for field in fields(CourtLifecycleDependencies)}
    arguments['_court_config'] = lambda: {'grade_stipends': {'9': 17}}
    game = GameState('stipend', 7, Player('Player', 'none'), '', '')
    game.heavenly_court = {'player_grade': 9}
    _court_pay_stipend(CourtLifecycleDependencies(**arguments), game)
    assert game.heavenly_court['stipend_total'] == 17
    assert next(item.quantity for item in game.player.inventory if item.id == 'spirit_stone') == 17
    unrelated.assert_not_called()


def test_court_bindings_follow_late_overrides_and_replaced_storage(tmp_path, monkeypatch):
    engine = GameEngine(ROOT, tmp_path / 'original')
    replacement = SaveStore(tmp_path / 'replacement')
    monkeypatch.setattr(engine, 'store', replacement)
    monkeypatch.setattr(engine, '_court_config', lambda: {'grade_stipends': {'9': 23}})
    monkeypatch.setattr(engine, '_load', lambda key: 'replacement game')
    assert engine._dependencies.court_state.store is replacement
    assert engine._dependencies.court_yaochi.store is replacement
    assert engine._dependencies.court_yaochi._load('save') == 'replacement game'
    game = GameState('stipend', 7, Player('Player', 'none'), '', '')
    game.heavenly_court = {'player_grade': 9}
    engine._court_pay_stipend(game)
    assert game.heavenly_court['stipend_total'] == 23


def test_legacy_yaochi_mixin_still_supports_an_independent_consumer(tmp_path):
    class Legacy(YaochiMixin):
        def __init__(self):
            self.store = SaveStore(tmp_path)
        def _load(self, key):
            return self.store.load(key)
        def present(self, game):
            return game.yaochi_state

    host = Legacy()
    game = GameState('yaochi', 7, Player('Player', 'supreme_metal', world='celestial', realm_index=9), '', '')
    game.player.location_id = config()['location_id']
    game.yaochi_state = {'merit': 10000}
    host.store.save(game)
    result = host.yaochi_action(game.id, 'exchange_stones')
    assert result['merit'] < 10000
    saved = host.store.load(game.id)
    assert saved.yaochi_state == result
    assert any(item.id == 'spirit_stone' and item.quantity > 0 for item in saved.player.inventory)


@pytest.mark.parametrize('area,target', [
    ('state', 'heavenly_court_system'), ('governance', 'court_governance'),
    ('lifecycle', 'court_lifecycle'), ('yaochi', 'yaochi_system'), ('state', 'court.wiring'),
])
def test_court_algorithms_cannot_import_facades_or_wiring(area, target):
    source, destination = f'cultivation_life.system.court.{area}', f'cultivation_life.system.{target}'
    assert violations([(source, destination, 9)]) == [dict(source=source, target=destination, line=9)]

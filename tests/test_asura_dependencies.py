"""Asura commands run independently and preserve late engine overrides."""
from pathlib import Path
from unittest.mock import Mock

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.engine.actions import asura as actions
from cultivation_life.engine.dependencies import AsuraActionDependencies, AsuraTrialDependencies
from cultivation_life.engine.progression import asura_trials
from cultivation_life.models import GameState, Player
from cultivation_life.storage import SaveStore
from cultivation_life.system.asura_system import AsuraSystemMixin


ROOT = Path(__file__).resolve().parents[1]


def isolated_game():
    game = GameState('isolated', 42, Player('Isolated', 'supreme_metal', path='demonic'), '', '')
    p = game.player
    p.world, p.realm_index, p.body_training, p.opportunity = 'asura', 9, 100, 100000
    p.asura_cultivation.update(conversion=5, body_level=0, souls=1000)
    return game


def test_asura_command_can_run_without_an_engine(tmp_path):
    game = isolated_game()
    store = SaveStore(tmp_path)
    unrelated = Mock(side_effect=AssertionError('Unexpected trial dependency'))
    deps = AsuraActionDependencies(
        _load=lambda game_id: game,
        present=lambda game: {'body_level': game.player.asura_cultivation['body_level']},
        _asura_cultivate=lambda *args: actions._asura_cultivate(deps, *args),
        _spend_asura_souls=actions._spend_asura_souls,
        queue_trial=unrelated, start_trial=unrelated, _get_store=lambda: store,
    )
    result = actions.asura_action(deps, game.id, 'train_body')
    saved = store.load(game.id)
    assert result == {'body_level': 1}
    assert saved.player.opportunity == 94000
    assert saved.history[-1].event_id == 'SYS_ASURA_CULTIVATION'
    unrelated.assert_not_called()


def test_trial_queue_uses_only_its_declared_dependencies():
    game = isolated_game()
    game.active_trial = {'kind': 'asura_conversion', 'stage': 1, 'event_ids': ['trial']}
    events = {'trial': {'id': 'trial', 'body': 'original'}}
    instantiate = Mock(side_effect=lambda event, game, rng: event)
    unrelated = Mock(side_effect=AssertionError('Unexpected combat dependency'))
    deps = AsuraTrialDependencies(lambda: events, instantiate, unrelated, unrelated)
    asura_trials.queue(deps, game)
    assert game.pending_event == events['trial']
    assert game.pending_event is not events['trial']
    instantiate.assert_called_once_with(events['trial'], game, None)
    unrelated.assert_not_called()


def test_asura_callbacks_and_store_follow_overrides_after_construction(tmp_path, monkeypatch):
    engine = GameEngine(ROOT, tmp_path / 'original')
    replacement = SaveStore(tmp_path / 'replacement')
    game = isolated_game()
    replacement.save(game)
    monkeypatch.setattr(engine, 'store', replacement)
    cultivate = Mock(return_value='overridden cultivation')
    present = Mock(return_value={'overridden': True})
    monkeypatch.setattr(engine, '_asura_cultivate', cultivate)
    monkeypatch.setattr(engine, 'present', present)
    assert engine.asura_action(game.id, 'train_body') == {'overridden': True}
    cultivate.assert_called_once()
    assert cultivate.call_args.args[1] == 'train_body'
    assert replacement.load(game.id).history[-1].summary == 'overridden cultivation'
    assert not (tmp_path / 'original' / f'{game.id}.json').exists()


def test_trial_bindings_follow_event_and_method_replacement(tmp_path, monkeypatch):
    engine = GameEngine(ROOT, tmp_path)
    game = isolated_game()
    game.active_trial = {'event_ids': ['replacement']}
    monkeypatch.setattr(engine, 'events_by_id', {'replacement': {'body': 'new event'}})
    instantiate = Mock(return_value={'id': 'new pending event'})
    monkeypatch.setattr(engine, '_instantiate_event', instantiate)
    engine._dependencies.asura_actions.queue_trial(game)
    assert game.pending_event == {'id': 'new pending event'}
    instantiate.assert_called_once_with({'body': 'new event'}, game, None)


def test_subclass_soul_spending_override_remains_effective(tmp_path):
    class DiscountEngine(GameEngine):
        @staticmethod
        def _spend_asura_souls(state, cost):
            state['souls'] -= cost / 2

    engine = DiscountEngine(ROOT, tmp_path)
    game = isolated_game()
    game.player.asura_cultivation.update(route='asura', level=1, domain_name='Test domain')
    engine.store.save(game)
    engine.asura_action(game.id, 'train_route')
    assert engine.store.load(game.id).player.asura_cultivation['souls'] == 970


def test_legacy_mixin_adapter_still_supports_existing_consumers(tmp_path):
    class LegacyConsumer(AsuraSystemMixin):
        def __init__(self):
            self.store = SaveStore(tmp_path)

        def _load(self, game_id):
            return self.store.load(game_id)

        def present(self, game):
            return game.player.asura_cultivation['body_level']

    consumer = LegacyConsumer()
    game = isolated_game()
    consumer.store.save(game)
    assert consumer.asura_action(game.id, 'train_body') == 1
    assert consumer.store.load(game.id).player.opportunity == 94000


def test_insufficient_souls_does_not_change_state():
    state = {'souls': 5}
    with pytest.raises(ValueError):
        GameEngine._spend_asura_souls(state, 10)
    assert state == {'souls': 5}

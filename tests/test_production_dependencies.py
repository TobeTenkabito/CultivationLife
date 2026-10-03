"""Behavioral boundaries for composed economy, crafting and formations."""
import copy
import random
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Player
from cultivation_life.storage import SaveStore
from cultivation_life.runtime import decode_rng
from cultivation_life.system import crafting_system, formation_system, economy_system, exchange_system
from cultivation_life.system.economy.dependencies import ExchangeDependencies
from cultivation_life.system.economy.exchange import exchange_action
from cultivation_life.system.formation.dependencies import FormationLoadoutsDependencies
from cultivation_life.system.formation.loadouts import _activate_loadout
from tools.check_module_dependencies import violations

ROOT = Path(__file__).resolve().parents[1]


def test_engine_no_longer_inherits_production_or_exchange():
    removed = {crafting_system.CraftingSystemMixin, formation_system.FormationSystemMixin,
               economy_system.EconomySystemMixin, exchange_system.ExchangeSystemMixin}
    assert not removed & set(GameEngine.__mro__)


def exchange_fixture(tmp_path):
    game = GameState('exchange', 41, Player('Trader', 'none'), '', '')
    game.player.location_id = 'venue'
    game.player.crafting_materials = [{'id': 'paid'}, {'id': 'kept'}]
    game.exchange_state = {
        'status': 'open', 'world': game.player.world, 'location_id': 'venue', 'alias': 'Alias',
        'offers': [{'id': 'offer', 'completed': False, 'demands': [{'definition_id': 'ore', 'quantity': 1}],
                    'demand_value': 10, 'reward': {'id': 'reward', 'name': 'Reward'},
                    'npc_alias': 'NPC', 'substitution_attempted': False}],
    }
    store = SaveStore(tmp_path)
    store.save(game)
    unrelated = Mock(side_effect=AssertionError('Unexpected capability'))
    values = {field.name: unrelated for field in fields(ExchangeDependencies)}
    values.update(_load=store.load, _get_store=lambda: store, decode_rng=decode_rng, present=lambda game: game.exchange_state,
                  _exchange_materials=lambda game: [{'id': 'paid', 'definition_id': 'ore',
                                                      'value': 10, 'quantity': 1, 'kind': 'crafting'}])
    return game, store, ExchangeDependencies(**values), unrelated


def test_exchange_independent_contract_consumes_once_and_rejects_repeat(tmp_path):
    game, store, deps, unrelated = exchange_fixture(tmp_path)
    payload = {'offer_id': 'offer', 'materials': [{'id': 'paid', 'quantity': 1}]}
    result = exchange_action(deps, game.id, 'trade', payload)
    assert result['offers'][0]['completed'] is True
    assert [row['id'] for row in store.load(game.id).player.crafting_materials] == ['kept', 'reward']
    before = store.load(game.id).to_dict()
    with pytest.raises(ValueError, match='已经结束'):
        exchange_action(deps, game.id, 'trade', payload)
    assert store.load(game.id).to_dict() == before
    unrelated.assert_not_called()


@pytest.mark.parametrize('selected', [
    [{'id': 'paid', 'quantity': 2}],
    [{'id': 'paid', 'quantity': 1}, {'id': 'paid', 'quantity': 1}],
    [{'id': 'paid', 'quantity': True}],
    [{'id': 'missing', 'quantity': 1}],
])
def test_invalid_exchange_keeps_inventory_and_rng_unchanged(tmp_path, selected):
    game, store, deps, unrelated = exchange_fixture(tmp_path)
    before = store.load(game.id).to_dict()
    with pytest.raises(ValueError):
        exchange_action(deps, game.id, 'trade', {'offer_id': 'offer', 'materials': selected})
    assert store.load(game.id).to_dict() == before
    unrelated.assert_not_called()


def test_failed_activation_restores_extracted_material_and_previous_state():
    player = Player('Array', 'none')
    player.formation_materials = [{'id': 'first'}, {'id': 'second'}]
    player.active_formation_id = 'previous'
    player.formation_profile_cache = {'previous': True}
    before = copy.deepcopy(player.to_dict())
    unrelated = Mock(side_effect=AssertionError('Unexpected capability'))
    values = {field.name: unrelated for field in fields(FormationLoadoutsDependencies)}
    candidates = [{'id': 'first', 'definition_id': 'wood'}, {'id': 'second', 'definition_id': 'fire'}]

    def extract(player, candidate):
        if candidate['id'] == 'second':
            raise ValueError('Interrupted after extracting the first material')
        player.formation_materials.pop(0)
        return dict(candidate)

    values.update(_formation_candidates=lambda *args, **kwargs: candidates,
                  _release_active_formation=formation_system.FormationSystemMixin._release_active_formation,
                  _extract_candidate=extract)
    with pytest.raises(ValueError, match='Interrupted'):
        _activate_loadout(FormationLoadoutsDependencies(**values), player,
                          {'id': 'next', 'slots': ['wood', 'fire'] + [None] * 7})
    assert player.to_dict() == before
    unrelated.assert_not_called()


def test_legacy_crafting_optional_tianji_hooks_can_appear_and_disappear():
    class Legacy(crafting_system.CraftingSystemMixin):
        @staticmethod
        def _crafting_material_defs():
            return {}

    host = Legacy()
    game = GameState('hooks', 42, Player('Player', 'none'), '', '')
    kwargs = dict(tier=1, market_name='Market', location_id='place')
    host._append_crafting_market_offers(game, random.Random(1), [], **kwargs)
    hook = Mock()
    host._append_tianji_market_offers = hook
    offers = []
    host._append_crafting_market_offers(game, random.Random(1), offers, **kwargs)
    hook.assert_called_once_with(game, offers, **kwargs)
    del host._append_tianji_market_offers
    host._append_crafting_market_offers(game, random.Random(1), [], **kwargs)
    bought = Mock()
    host._tianji_material_bought = bought
    instance = {'id': 'material', 'name': 'Ore', 'state': 'Good'}
    host._buy_crafting_material_offer(game, {'market_name': 'Market', 'material_instance': instance}, 12)
    bought.assert_called_once_with(game, instance)
    assert game.player.crafting_materials == [instance]
    assert game.player.crafting_materials[0] is not instance


def test_composed_systems_keep_live_resources_and_rule_hooks(tmp_path, monkeypatch):
    engine = GameEngine(ROOT, tmp_path / 'original')
    replacement = SaveStore(tmp_path / 'replacement')
    maps = SimpleNamespace(location=lambda world, key: {'id': key, 'name': 'Replacement'})
    monkeypatch.setattr(engine, 'store', replacement)
    monkeypatch.setattr(engine, 'maps', maps)
    monkeypatch.setattr(engine, '_load', lambda key: 'replacement game')
    for deps in (engine._economy_dependencies.black_market, engine._exchange_dependencies,
                 engine._crafting_dependencies.forging, engine._formation_dependencies.ground):
        assert deps.store is replacement
        assert deps._load('save') == 'replacement game'
    assert engine._formation_dependencies.ground.maps is maps
    monkeypatch.setattr(exchange_system, 'EXCHANGE_VENUES', {'human': 'new-venue'})
    assert engine._exchange_location('human')['id'] == 'new-venue'
    monkeypatch.setattr(crafting_system, 'crafting_config', lambda: {'settings': {'custom': True}})
    assert engine._crafting_rules() == {'custom': True}
    monkeypatch.setattr(formation_system, 'formation_config', lambda: {'settings': {'custom': True}})
    assert engine._formation_rules() == {'custom': True}
    monkeypatch.setattr(formation_system, 'formation_alpha', lambda player: 0.75)
    assert engine._formation_dependencies.loadouts.formation_alpha(None) == 0.75


def test_subclass_super_dispatch_and_static_release_compatibility(tmp_path, monkeypatch):
    class Specialized(GameEngine):
        def _crafting_material_candidates(self, player):
            return super()._crafting_material_candidates(player) + [{'id': 'custom'}]

    engine = Specialized(ROOT, tmp_path)
    player = Player('Player', 'none')
    assert engine._crafting_dependencies.materials._crafting_material_candidates(player) == [{'id': 'custom'}]
    release = Mock()
    monkeypatch.setattr(formation_system.FormationSystemMixin, '_release_bindings', release)
    engine._release_active_formation(player)
    release.assert_called_once_with(player, [])


@pytest.mark.parametrize('source,target', [
    ('economy.exchange', 'exchange_system'),
    ('crafting.materials', 'crafting_system'),
    ('crafting.forging', 'crafting.wiring'),
    ('formation.loadouts', 'formation_system'),
    ('formation.ground', 'formation.wiring'),
])
def test_production_algorithms_cannot_reverse_import_facades_or_wiring(source, target):
    source = 'cultivation_life.system.' + source
    target = 'cultivation_life.system.' + target
    assert violations([(source, target, 9)]) == [{'source': source, 'target': target, 'line': 9}]

"""Command-level soul loadouts, escrow and replenished-depletion boundaries."""
import copy
import random
from unittest.mock import patch

import pytest

from test_survival_settlement import base, ready, attach_second
from test_soul_lifecycle import act
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.models import Item
from cultivation_life.system import soul_lifecycle as life


@pytest.mark.parametrize('slot', ['support', 'combat'])
def test_existing_main_book_can_be_assigned_to_requested_slot(ready, slot):
    engine, game = ready
    npc = attach_second(game)
    book = copy.deepcopy(TECHNIQUE_CATALOG['TECH_BASIC_QI'])
    book.level = 5
    game.player.known_techniques = [book]
    npc.main_technique_id = book.id
    npc.main_technique_level = 7
    npc.technique_levels = {book.id: 7}
    engine.store.save(game)
    act(engine, game, 'technique', id=book.id, slot=slot)
    after = engine.store.load(game.id)
    learned = life.second_person(after)
    assert learned.technique_slots.get(slot) == book.id
    assert learned.main_technique_level == learned.technique_levels[book.id] == 7
    assert after.player.known_techniques[0].level == 5


def test_missing_book_definition_rejects_stale_configuration_cleanly(ready):
    engine, game = ready
    npc = attach_second(game)
    npc.technique_levels['TECH_REMOVED_TEST'] = 3
    engine.store.save(game)
    engine.get_game(game.id)
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='功法'):
        act(engine, game, 'technique', id='TECH_REMOVED_TEST', slot='support')
    assert engine.store._path(game.id).read_bytes() == before


def test_second_rescue_rearms_depletion_after_replenishing_soul(ready):
    engine, game = ready
    attach_second(game)
    game.player.soul_energy = 0
    game.player.nascent_state['depleted'] = True
    engine._die(game, '魂伤复发', 'SYS_TEST_SOUL', survival_stage='spirit_failed')
    assert game.player.alive and game.player.soul_energy > 0
    engine.store.save(game)
    game = engine.store.load(game.id)
    game.player.soul_energy = 0
    rng = random.Random(1)
    with patch.object(rng, 'randrange', return_value=1) as roll:
        life.resolve_energy(game, rng, engine._die)
        life.resolve_energy(game, rng, engine._die)
        assert roll.call_count == 1
    assert game.player.nascent_state.get('crisis') == 'possession'


@pytest.mark.parametrize('quantity', [1, 2])
@pytest.mark.parametrize('return_action', ['unequip', 'dismiss', 'rescue'])
def test_equipment_escrow_updates_attachment_in_same_command(ready, quantity, return_action):
    engine, game = ready
    attach_second(game)
    item = Item('audit-soul-vessel', '寄魂古剑', quantity=quantity, combat_bonus=20, tags=['artifact'])
    game.player.inventory.append(item)
    game.player.path = 'ghost'
    engine.store.save(game)
    engine.ghost_attachment_action(game.id, 'attach', item.id)
    act(engine, game, 'equip', id=item.id)
    after = engine.store.load(game.id)
    assert bool(after.player.ghost_attachment) is (quantity > 1)
    assert sum(i.quantity for i in after.player.inventory if i.id == item.id) == quantity - 1
    assert len(after.player.nascent_state['second']['equipment']) == 1
    if return_action == 'rescue':
        engine._die(after, '寄魂斗法失败', 'SYS_TEST_SOUL', survival_stage='spirit_failed')
        assert after.player.alive
        engine.store.save(after)
    else:
        act(engine, after, return_action, index=0)
    returned = engine.store.load(game.id)
    assert sum(i.quantity for i in returned.player.inventory if i.id == item.id) == quantity
    assert bool(returned.player.ghost_attachment) is (quantity > 1 and return_action != 'rescue')


@pytest.mark.parametrize('identity,slot', [(None,'main'), ({},'main'), ([],'support'),
                                         ('TECH_BASIC_QI',{}), ('TECH_BASIC_QI',[])])
def test_invalid_technique_payload_is_rejected_without_writes(ready, identity, slot):
    engine, game = ready
    attach_second(game)
    game.player.known_techniques = [copy.deepcopy(TECHNIQUE_CATALOG['TECH_BASIC_QI'])]
    engine.store.save(game)
    engine.get_game(game.id)
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='功法'):
        act(engine, game, 'technique', id=identity, slot=slot)
    assert engine.store._path(game.id).read_bytes() == before


def test_empty_stack_cannot_create_second_equipment(ready):
    engine, game = ready
    attach_second(game)
    game.player.inventory.append(Item('audit-empty-gear', '已耗尽法器', quantity=0, combat_bonus=20))
    engine.store.save(game)
    engine.get_game(game.id)
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        act(engine, game, 'equip', id='audit-empty-gear')
    assert engine.store._path(game.id).read_bytes() == before

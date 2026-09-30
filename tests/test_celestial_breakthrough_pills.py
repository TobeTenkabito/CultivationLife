"""Real shop, inventory and breakthrough flow for celestial probability aids."""
from unittest.mock import patch

import pytest

from test_immortal_cultivation import prepared
from cultivation_life.content_registry import ITEM_CATALOG, WORLD_SYSTEMS
from cultivation_life.rules import add_item, breakthrough_opportunity_required
from cultivation_life.system.yaochi_system import offers, commission_reward


def pills(realm):
    return [row for row in WORLD_SYSTEMS['yaochi']['breakthrough_pills'] if row['realm'] == realm]


@pytest.mark.parametrize('realm', range(9, 13))
@pytest.mark.parametrize('layer', [1, 3, 6])
def test_three_pills_can_be_bought_stacked_and_consumed(prepared, realm, layer):
    engine, game, _ = prepared
    p = game.player
    p.realm_index, p.layer = realm, layer
    p.immortal_veins[str(realm)] = layer * 3
    p.opportunity = breakthrough_opportunity_required(p)
    p.location_id = WORLD_SYSTEMS['yaochi']['location_id']
    selected = pills(realm)
    total = sum(row['price'] for row in selected)
    game.yaochi_state['merit'] = total
    engine.store.save(game)
    assert len(selected) == 3
    assert total <= commission_reward(p, WORLD_SYSTEMS['yaochi']['commissions'][0])
    available = {row['id'] for row in offers(game)}
    all_pills = {row['id'] for row in WORLD_SYSTEMS['yaochi']['breakthrough_pills']}
    assert available & all_pills == {row['id'] for row in selected}
    for row in selected:
        engine.yaochi_action(game.id, 'buy', row['id'])
        shown = engine.use_item(game.id, row['id'])
    assert shown['breakthrough']['chance']['aid_bonus'] == pytest.approx(.4)
    assert shown['breakthrough']['chance']['final'] <= .98
    assert engine.store.load(game.id).yaochi_state['merit'] == 0
    # Stacking the same medicine again cannot consume the spare dose.
    saved = engine.store.load(game.id)
    add_item(saved.player, selected[0]['id'])
    engine.store.save(saved)
    with pytest.raises(ValueError, match='同一种'):
        engine.use_item(game.id, selected[0]['id'])
    with patch.object(engine, '_breakthrough_chance', return_value={'final': 1}):
        result = engine.immortal_action(game.id, 'breakthrough')
    assert result['player']['layer'] == layer + 1
    assert not engine.store.load(game.id).player.active_breakthrough_aids


@pytest.mark.parametrize('case', ['veins', 'money', 'realm', 'world', 'major', 'sealed'])
def test_pill_rejects_unqualified_player_without_consumption(prepared, case):
    engine, game, _ = prepared
    p = game.player
    p.immortal_veins['9'] = 3
    pill = pills(9)[0]['id']
    add_item(p, pill)
    if case == 'veins': p.immortal_veins['9'] = 2
    if case == 'money': p.opportunity = 17999
    if case == 'realm': p.realm_index = 10
    if case == 'world': p.world = 'asura'
    if case == 'major': p.layer, p.immortal_veins['9'] = 9, 27
    if case == 'sealed': p.sealed_cultivation = {'realm_index': 10, 'layer': 1, 'world': 'celestial'}
    engine.store.save(game)
    with pytest.raises(ValueError):
        engine.use_item(game.id, pill)
    saved = engine.store.load(game.id).player
    assert next(i.quantity for i in saved.inventory if i.id == pill) == 1
    assert not saved.active_breakthrough_aids


def test_failed_attempt_uses_all_prepared_pills_once(prepared):
    engine, game, _ = prepared
    game.player.layer = 3
    game.player.immortal_veins['9'] = 9
    for row in pills(9): add_item(game.player, row['id'])
    engine.store.save(game)
    for row in pills(9): engine.use_item(game.id, row['id'])
    with patch.object(engine, '_breakthrough_chance', return_value={'final': 0}):
        shown = engine.immortal_action(game.id, 'breakthrough')
    assert shown['player']['layer'] == 3
    shown = engine.get_game(game.id)
    assert shown['breakthrough']['chance']['aid_bonus'] == 0
    assert not engine.store.load(game.id).player.active_breakthrough_aids


def test_quick_start_doctrine_is_an_actual_catalog_entry(prepared):
    engine, game, _ = prepared
    shown = engine.present(game)['doctrines']
    assert len(shown['rows']) == 25
    starter = next(r for r in shown['rows'] if r['id'] == 'celestial:primordial')
    assert starter['learned'] and starter['manuals']
    assert starter['level'] == 0 and len(starter['stages']) == 1
    assert all(ITEM_CATALOG[row['id']].breakthrough_scope.startswith('minor:')
               for row in WORLD_SYSTEMS['yaochi']['breakthrough_pills'])

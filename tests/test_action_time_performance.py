"""Performance boundaries: exact low-price orders, real cash and NPC history."""
import copy
import math
import random
from unittest.mock import patch

import pytest

from test_economy_network import economy, cash
from cultivation_life.models import GameState
from cultivation_life.system.economy import basket_production, basket_trade, caravans
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.economy.resource_access import site_profile, _site_profile
from cultivation_life.content_registry import WORLD_SYSTEMS


@pytest.mark.parametrize('reference', [0.5, 2, 6, 100])
@pytest.mark.parametrize('allow_loss', [False, True])
@pytest.mark.parametrize('owner_funds', [0, -1])
def test_raw_order_keeps_original_wage_rounding_and_cash_boundary(economy, reference, allow_loss, owner_funds):
    engine, game = economy
    market = game.economy_v2['markets']['human:' + game.player.location_id]
    item = 'econ_human_1_ore_structure'
    row = market['commodities'][item]
    row.update(stock=100, reference=reference, target=100, initial_target=100)
    source = 'organization:sect:tianjian'
    transfer_value(game, source, 'background:human', balance(game, source), 'test empty workshop treasury')
    game.intrigue_state['factions']['sect:tianjian']['resources'] = owner_funds
    # This captures the established integer search, especially receipts of 0–3
    # where ceil(70% wage) can make the profitability check non-monotonic.
    low, high = 0, 4
    while low < high:
        count = (low + high + 1) // 2
        receipt = basket_trade.quote(row, 'sell', count)['total']
        wage = math.ceil(receipt * .70)
        if owner_funds >= 0 and wage <= receipt and (allow_loss or receipt >= wage * 1.05):
            low = count
        else:
            high = count - 1
    total = cash(game)
    made, profit = basket_production.produce(game, market, source, item, 4, allow_loss=allow_loss)
    assert made == low
    assert row['stock'] == 100 + made
    assert cash(game) == total and balance(game, source) == owner_funds + profit
    if owner_funds < 0:
        assert made == 0
        with pytest.raises(ValueError):
            GameState.from_dict(game.to_dict())
    else:
        assert GameState.from_dict(game.to_dict())


def test_site_metadata_cache_observes_current_world_cap_and_has_bounded_size():
    world = 'human'
    location = next(f'site-{i}' for i in range(100)
                    if site_profile(world, f'site-{i}', 'mine') != _site_profile(world, f'site-{i}', 'mine', 8))
    old = site_profile(world, location, 'mine')
    with patch.dict(WORLD_SYSTEMS['world_profiles'][world], tier=2):
        assert site_profile(world, location, 'mine') == _site_profile(world, location, 'mine', 8)
        assert site_profile(world, location, 'mine') != old
    assert site_profile(world, location, 'mine') == old
    for i in range(300):
        site_profile(world, f'bounded-{i}', 'farm')
    assert _site_profile.cache_info().currsize <= 256


def test_title_projection_can_read_old_rank_without_mutating_npc(economy):
    engine, game = economy
    sect = game.sects['tianjian']
    npc = next(n for n in sect.npcs if n.alive and n.title not in {'宗主', '掌门'})
    npc.title = '门人'
    npc.realm_index = 2
    old_title = engine._dynamic_sect_title(npc, sect)
    npc.realm_index = 3
    snapshot = copy.deepcopy(npc.to_dict())
    assert engine._dynamic_sect_title(npc, sect, realm_index=2) == old_title
    assert engine._dynamic_sect_title(npc, sect) != old_title
    assert npc.to_dict() == snapshot


def test_annual_npcs_keep_history_without_projecting_titles_for_every_person(economy):
    engine, game = economy
    population = sum(n.alive for s in game.sects.values() for n in s.npcs)
    with patch.object(engine, '_dynamic_sect_title', wraps=engine._dynamic_sect_title) as titles:
        engine._annual_sect_update(game, random.Random(33))
    assert titles.call_count < population
    for call in titles.call_args_list:
        if 'realm_index' in call.kwargs:
            assert isinstance(call.kwargs['realm_index'], int)
    assert GameState.from_dict(game.to_dict())


def test_original_candidate_set_and_quantity_order_keep_lowest_financed_batch(economy):
    engine, game = economy
    fleet = next(iter(game.economy_v2['transport']['worlds']['human']['fleets'].values()))
    owner = caravans.owner_sites(game, engine.maps, fleet)
    # The true quote wrapper observes normal source/target prices and funds;
    # even an empty wallet must still settle the original local markets.
    snapshot = game.player.to_dict()
    with patch.object(caravans, 'quote', wraps=caravans.quote) as quoting:
        result = caravans._candidate(game, engine.maps, owner, fleet)
    assert result is None and game.player.to_dict() == snapshot
    buys = [call for call in quoting.call_args_list if call.args[1] == 'buy']
    assert buys and all(call.args[2] <= fleet['capacity'] for call in buys)

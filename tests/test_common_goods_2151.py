"""Restricted acquisition, genuine weak talismans, real inputs and finite budgets."""
import copy
import random

import pytest

from test_secret_art_training import ready
from cultivation_life.content_registry import ITEM_CATALOG, MARKET_GOODS, SECRET_MATERIAL_GOODS, restricted_acquisition
from cultivation_life.common_talisman_content import SLOTS, price, product
from cultivation_life.economy_content import specification, material_id, product_id, inputs
from cultivation_life.rules import add_item, has_item, max_hp, max_mp
from cultivation_life.system import talismans
from cultivation_life.system.economy import basket_production, basket_rules
from cultivation_life.system.economy.state import local_market, commodity_catalog, ensure_market
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system.economy.demand_profiles import rates
from cultivation_life.talisman_content import WORLD_TIERS, catalog as artisan_catalog


def test_all_attribute_remains_have_only_explicit_channels():
    ids = {r['content_id'] for r in SECRET_MATERIAL_GOODS}
    assert len(ids) == 216
    assert ids.isdisjoint(r['content_id'] for r in MARKET_GOODS)
    for identity in ids:
        assert restricted_acquisition('item', identity)
        assert all(identity not in commodity_catalog(world) for world in WORLD_TIERS)


def test_each_world_has_three_usable_lower_power_talismans_per_supported_grade():
    materials, methods = artisan_catalog()
    found = []
    for world, (_, grades) in WORLD_TIERS.items():
        for grade in grades:
            for slot, (_, dimension) in SLOTS.items():
                identity = product_id(world, grade, slot)
                spec = specification(identity)
                assert spec['use'] == 'talisman'
                assert any(g['content_id'] == identity and g['world'] == world for g in MARKET_GOODS)
                ordinary = product(identity, world, grade, slot, ITEM_CATALOG[identity].name)
                artisan = talismans.product(methods[f'talisman_{world}_{grade}_{dimension}'],
                    [materials[k] for k in inputs(world, grade, slot)], 'poor')
                assert 0 < ordinary[dimension] < artisan[dimension]
                assert ordinary['uses'] == 3 < artisan['uses']
                assert sum(ordinary[d] > 0 for d in ('power','protection','assistance')) == 1
                assert price(grade) >= sum(materials[k]['base_value'] for k in inputs(world, grade, slot)) * 2
                assert basket_rules.purpose(identity) == 'general'
                found.append(identity)
    assert len(found) == 138 and len(set(found)) == 138
    assert all(sum(rates(rank).values()) == pytest.approx(.113) for rank in range(13))


@pytest.mark.parametrize('kind', ['core', 'soul'])
def test_black_market_can_actually_buy_restricted_remains(ready, kind):
    engine, game = ready
    identity = f'secret_{kind}_water_4'
    game.auction_state = dict(id='remains', status='black_market', world='human',
        location_id=game.player.location_id, black_market_results=[])
    add_item(game.player, 'spirit_stone', 1000000)
    before = next((i.quantity for i in game.player.inventory if i.id == identity), 0)
    engine.store.save(game)
    shown = engine.search_black_market(game.id, '^水属')
    row = next(r for r in shown['auction_system']['black_market_results'] if r['content_id'] == identity)
    engine.buy_black_market_item(game.id, row['id'])
    assert has_item(engine.store.load(game.id).player, identity, before+1)


@pytest.mark.parametrize('kind', ['core', 'soul'])
def test_exchange_actually_trades_and_prevents_replay(ready, kind):
    from cultivation_life.system.crafting_system import make_crafting_material_instance
    engine, game = ready
    rng = random.Random(2151)
    engine._schedule_exchange(game, rng)
    engine._open_exchange(game, rng)
    game.player.location_id = game.exchange_state['location_id']
    game.exchange_state['alias'] = '青笠客'
    offer = next(r for r in game.exchange_state['offers'] if r.get('reward_kind') == 'secret_material'
                 and 'secret_art_'+kind in ITEM_CATALOG[r['item_id']].tags)
    demand = offer['demands'][0]
    selected = []
    for _ in range(demand['quantity']):
        item = make_crafting_material_instance(engine._crafting_material_defs()[demand['definition_id']], rng,
            source='测试', origin_world='human')
        game.player.crafting_materials.append(item)
        selected.append(dict(id=item['id'], quantity=1))
    prior = next((i.quantity for i in game.player.inventory if i.id == offer['item_id']), 0)
    engine.store.save(game)
    payload = dict(offer_id=offer['id'], materials=selected)
    engine.exchange_action(game.id, 'trade', payload)
    assert has_item(engine.store.load(game.id).player, offer['item_id'], prior+1)
    with pytest.raises(ValueError, match='结束'):
        engine.exchange_action(game.id, 'trade', payload)


def test_legacy_stock_cannot_be_produced_or_bought_and_depot_merchant_exclude_it(ready):
    from cultivation_life.system.economy.basket_trade import quote
    engine, game = ready
    market = local_market(game)
    key = 'secret_core_water_4'
    market['commodities'][key] = dict(stock=100., target=120., initial_target=120., reference=1080,
        price=1080., tier=4, production=0., consumption=0., volume=0, history=[])
    assert basket_production.recipe(market, key) is None
    assert key not in [i for rows in basket_rules.index(market, rebuild=True).values() for i in rows]
    assert not any(r['id'] == key for r in engine._merchant_items('human'))
    engine.store.save(game)
    shown = engine.get_game(game.id)
    current = engine.store.load(game.id)
    market = local_market(current)
    bill = quote(market['commodities'][key], 'buy', 1)
    before = current.to_dict()
    with pytest.raises(ValueError, match='标准商品'):
        engine.trade_local_market(game.id, dict(item_id=key, side='buy', quantity=1,
            market_id=market['id'], revision=market['revision'], total=bill['total']))
    assert engine.store.load(game.id).to_dict() == before


def test_unpack_toggle_consume_sell_real_talisman_and_reject_second_unpack(ready):
    engine, game = ready
    identity = product_id('human', 4, 'talisman_protection')
    add_item(game.player, identity)
    engine.store.save(game)
    experience = copy.deepcopy(game.player.art_experience)
    engine.use_item(game.id, identity)
    saved = engine.store.load(game.id)
    row = next(r for r in saved.player.talismans if r['method_id'] == identity)
    assert not has_item(saved.player, identity) and not row['enabled'] and row['uses'] == 3
    assert saved.player.art_experience == experience and not row.get('creator_id')
    assert talismans.read(saved.player, 'protection') == 0
    talismans.act(saved, 'toggle', dict(talisman_id=row['id']))
    assert talismans.read(saved.player, 'protection') == 16
    snapshot = copy.deepcopy(saved.to_dict())
    assert talismans.read(saved.player, 'protection') == 16 and saved.to_dict() == snapshot
    full_value = talismans.economic_value(row)
    assert talismans.consume(saved.player, 'protection') == 16
    assert row['uses'] == 2 and talismans.economic_value(row) < full_value
    assert talismans.sale_rows(saved.player)[-1]['price'] <= price(4)*.25*2/3
    engine.store.save(saved)
    with pytest.raises(ValueError, match='物品不存在'):
        engine.use_item(game.id, identity)


def test_standard_recipe_consumes_real_inputs_and_preserves_money(ready):
    engine, game = ready
    market = local_market(game)
    identity = product_id('human', 4, 'talisman_power')
    recipe = basket_production.recipe(market, identity)
    assert recipe == inputs('human', 4, 'talisman_power')
    market['commodities'][identity]['stock'] = 0
    for key in recipe:
        market['commodities'][key]['stock'] = 1000
    prior = {k:r['stock'] for k,r in market['commodities'].items()}
    money = balance(game, 'player') + sum(r['balance'] for r in game.economy_v2['accounts'].values())
    count, _ = basket_production.produce(game, market, 'background:human', identity, 2)
    assert count == 2
    for key, n in recipe.items():
        assert market['commodities'][key]['stock'] == prior[key] - count*n
    assert balance(game, 'player') + sum(r['balance'] for r in game.economy_v2['accounts'].values()) == money
    market['commodities'][next(iter(recipe))]['stock'] = 0
    assert basket_production.produce(game, market, 'background:human', identity, 2) == (0,0)


def test_existing_markets_adopt_zero_stock_without_rewriting_owned_items(ready):
    engine, game = ready
    market = local_market(game)
    identity = product_id('human', 4, 'talisman_power')
    market['commodities'].pop(identity)
    market['goods_policy'] = 1
    bag = copy.deepcopy(game.player.inventory)
    funds = sum(r['balance'] for r in game.economy_v2['accounts'].values())
    ensure_market(game, engine.maps)
    assert market['commodities'][identity]['stock'] == 0 and market['goods_policy'] == 2
    assert game.player.inventory == bag
    assert sum(r['balance'] for r in game.economy_v2['accounts'].values()) == funds


def test_generic_core_is_weak_usable_same_grade_and_shares_annual_medicine_cap(ready):
    from cultivation_life.content_registry import WORLD_SYSTEMS
    engine, game = ready
    key = material_id('human', 4, 'core_energy')
    add_item(game.player, key, 2)
    add_item(game.player, product_id('human', 4, 'cultivation'))
    game.player.opportunity = 0
    engine.store.save(game)
    engine.use_item(game.id, key)
    saved = engine.store.load(game.id)
    assert saved.player.opportunity == WORLD_SYSTEMS['common_core_effects']['opportunity'][3]
    assert has_item(saved.player, key)
    for identity in (key, product_id('human', 4, 'cultivation')):
        with pytest.raises(ValueError, match='本年'):
            engine.use_item(game.id, identity)


def test_common_healing_is_weaker_than_named_medicine(ready):
    engine, game = ready
    game.player.hp, game.player.mp = max_hp(game.player)/2, max_mp(game.player)/2
    add_item(game.player, product_id('human', 4, 'healing'))
    engine.store.save(game)
    engine.use_item(game.id, product_id('human', 4, 'healing'))
    saved = engine.store.load(game.id)
    assert saved.player.hp == pytest.approx(max_hp(saved.player)*.62)
    assert saved.player.mp == pytest.approx(max_mp(saved.player)*.56)


@pytest.mark.parametrize('role,field', [('core_blood','hp'), ('core_soul','mp')])
def test_fixed_core_restores_current_value_without_growing_maximum(ready, role, field):
    from cultivation_life.content_registry import WORLD_SYSTEMS
    engine, game = ready
    key = material_id('human', 4, role)
    add_item(game.player, key)
    game.player.hp = game.player.mp = 0
    before = max_hp(game.player), max_mp(game.player)
    engine.store.save(game)
    engine.use_item(game.id, key)
    saved = engine.store.load(game.id)
    assert (max_hp(saved.player), max_mp(saved.player)) == before
    assert getattr(saved.player, field) == WORLD_SYSTEMS['common_core_effects'][field][3]


def test_common_ores_fill_original_slots_consume_real_quantities_and_are_very_weak(ready):
    engine, game = ready
    ids = [material_id('human', 4, role) for role in ('ore_structure','ore_conduct','ore_store')]
    for key, quantity in zip(ids, (1,2,1)):
        add_item(game.player, key, quantity)
    payload = dict(mold_id='sword', primary_id=f'common:{ids[0]}:0',
        secondary_a_id=f'common:{ids[1]}:0', secondary_b_id=f'common:{ids[1]}:1',
        quench_id=f'common:{ids[2]}:0', allocations={'combat_power':10})
    engine.store.save(game)
    before = engine.store.load(game.id).to_dict()
    preview = engine.preview_crafting(game.id, payload)
    assert engine.store.load(game.id).to_dict() == before
    # Remove only material multipliers to compare identical rank, mold, budget and quality.
    from unittest.mock import patch
    candidates = engine._crafting_material_candidates(game.player)
    plain = copy.deepcopy(candidates)
    for row in plain:
        if row['id'].startswith('common:'):
            row['role_effects'] = {}
    with patch.object(engine, '_crafting_material_candidates', return_value=plain):
        benchmark = engine.preview_crafting(game.id, payload)
    assert preview['designed_stats']['combat_power'] == pytest.approx(
        benchmark['designed_stats']['combat_power'] * .00625, abs=.0001)
    shown = engine.forge_crafted_artifact(game.id, payload)
    saved = engine.store.load(game.id)
    assert all(not has_item(saved.player, key) for key in ids)
    assert shown['crafting_system']['artifacts'][-1]['actual_stats']['combat_power'] < benchmark['theoretical_stats']['normal']['combat_power']*.01
    with pytest.raises(ValueError, match='不存在|选择'):
        engine.forge_crafted_artifact(game.id, payload)


def test_dynamic_auction_bands_cover_each_world_once_and_support_twelve_ranks():
    from cultivation_life.system.economy.auctions import auction_bands
    assert auction_bands('human') == [[1,2],[3,4],[5]]
    assert auction_bands('spirit') == [[1,2,3],[4,5,6],[7,8]]
    assert auction_bands('celestial') == [list(range(1,5)), list(range(5,9)), list(range(9,13))]
    for world in WORLD_TIERS:
        bands = auction_bands(world)
        flat = [r for band in bands for r in band]
        assert flat == list(range(1,max(flat)+1))
    with pytest.raises(KeyError):
        auction_bands('unknown-world')


def high_auction(engine, game):
    engine._schedule_auction(game, random.Random(2151))
    game.auction_state.update(auction_class=3, class_name='高级', rank_band=[5], entry_fee=500,
        location_id=game.player.location_id, location_name='测试会场')
    engine._open_auction(game, random.Random(2151))
    engine.store.save(game)


def test_high_auction_charges_player_once_and_preserves_cash_and_clock(ready):
    engine, game = ready
    high_auction(engine, game)
    before = engine.store.load(game.id)
    state = before.auction_state
    assert all(row['tier'] == 5 for row in state['lots'])
    assert all(not restricted_acquisition(r['kind'], r['content_id']) for r in state['lots'])
    total = balance(before,'player') + sum(r['balance'] for r in before.economy_v2['accounts'].values())
    funds = balance(before,'player')
    with pytest.raises(ValueError, match='入场费'):
        engine.place_auction_bid(game.id, state['lots'][0]['id'])
    assert engine.store.load(game.id).to_dict() == before.to_dict()
    engine.choose_auction_identity(game.id, '青龙公子')
    after = engine.store.load(game.id)
    assert balance(after,'player') == funds-500
    assert balance(after,'player') + sum(r['balance'] for r in after.economy_v2['accounts'].values()) == total
    assert after.player.age == before.player.age and after.auction_state['entry_paid']
    engine.choose_auction_identity(game.id, '朱雀公主')
    assert balance(engine.store.load(game.id),'player') == funds-500
    assert len([h for h in engine.store.load(game.id).history if h.event_id == 'SYS_AUCTION_ENTRY']) == 1


def test_high_auction_insufficient_money_and_invalid_alias_are_atomic(ready):
    engine, game = ready
    high_auction(engine, game)
    game = engine.store.load(game.id)
    next(i for i in game.player.inventory if i.id == 'spirit_stone').quantity = 499
    engine.store.save(game)
    before = engine.store.load(game.id).to_dict()
    for alias in ('青龙公子','不合法身份'):
        with pytest.raises(ValueError):
            engine.choose_auction_identity(game.id, alias)
        assert engine.store.load(game.id).to_dict() == before


def test_cached_reference_prices_match_original_median_and_are_bounded():
    from cultivation_life.content_registry import LIMITED_TRADE_GOODS
    from cultivation_life.system.economy_system import _listed_price
    grouped = {}
    for row in (*MARKET_GOODS, *LIMITED_TRADE_GOODS):
        grouped.setdefault((row['kind'],row['content_id']),[]).append(row['price'])
    for key, values in grouped.items():
        expected = sorted(values)[len(values)//2]
        assert _listed_price(*key,id(MARKET_GOODS),id(LIMITED_TRADE_GOODS)) == expected
    assert _listed_price.cache_info().currsize <= 4096

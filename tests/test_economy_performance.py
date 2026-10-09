"""Selection ties and affordability boundaries must survive faster algorithms."""
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.system.economy import caravans, basket_trade, basket_production, state
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.economy.pricing import total_price

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('stock,quantity,buy,sell', [
    (100, 24, 2614, 1767),
    (1000, 24, 840, 672),
    (0, 24, 5263, 3559),
    (0, 1000, 297006, 40015),
    (500, 1000, 179525, 28000),
])
def test_integrated_quotes_preserve_floors_ceilings_and_crossing_prices(stock, quantity, buy, sell):
    assert total_price(100, stock, quantity, 100, 'buy') == buy
    assert total_price(100, stock, quantity, 100, 'sell') == sell


@pytest.mark.parametrize('count', [0, 5, 12, 13, 500])
def test_top_twelve_preserves_stock_and_identity_ties(count):
    rng = random.Random(901)
    source = {'commodities': {}}
    target = {'commodities': {}}
    for number in range(count):
        item = f'good-{number:04d}'
        price = rng.randint(1, 10)
        source['commodities'][item] = dict(price=price, stock=rng.randint(0, 5), target=10)
        if number % 7:
            target['commodities'][item] = dict(price=price * rng.randint(1, 3))
    # Original policy: price ratio first, with stable source-stock and ID ties.
    goods = sorted(source['commodities'], key=lambda k: (
        source['commodities'][k]['stock'] / source['commodities'][k]['target'], k), reverse=True)
    expected = sorted((k for k in goods if k in target['commodities']), key=lambda k: (
        target['commodities'][k]['price'] / source['commodities'][k]['price']), reverse=True)[:12]
    assert caravans._candidate_items(source, target) == expected
    # A different destination price must take effect immediately.
    if target['commodities']:
        winner = next(iter(target['commodities']))
        target['commodities'][winner]['price'] = 10**6
        assert caravans._candidate_items(source, target)[0] == winner


@pytest.mark.parametrize('side', ['buy', 'sell'])
def test_affordability_is_maximal_at_cash_boundaries(side):
    rng = random.Random(31)
    for _ in range(120):
        row = dict(reference=rng.choice([1, 7, 100, 10**8]),
                   stock=rng.choice([0, 1, 100, 10000]), target=rng.choice([1, 100, 1000]))
        wanted = rng.choice([0, 1, 2, 24, 1000, 1000000])
        funds = rng.choice([0, 1, 10, 10000, 10**12])
        count = basket_trade.affordable(row, side, wanted, funds)
        assert 0 <= count <= wanted
        if count:
            assert basket_trade.quote(row, side, count)['gross'] <= funds
        if count < wanted:
            assert basket_trade.quote(row, side, count+1)['gross'] > funds
    row = dict(reference=100, stock=100, target=100)
    bill = basket_trade.quote(row, side, 1000)['gross']
    assert basket_trade.affordable(row, side, 1000, bill-1) < 1000
    with patch.object(basket_trade, 'quote', wraps=basket_trade.quote) as quoting:
        assert basket_trade.affordable(row, side, 1000, bill) == 1000
    assert quoting.call_count == 1


def test_candidate_computes_guard_once_for_all_goods_and_refreshes_each_call(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    game = engine._load(engine.create_game('商路算法验收', 'supreme_metal', 'dao', 315,
                                           preset_id='true_immortal')['id'])
    fleet = next(iter(game.economy_v2['transport']['worlds'][game.player.world]['fleets'].values()))
    alliance = caravans.owner_sites(game, engine.maps, fleet)
    game.player.age += 1
    state.advance_economy(game)
    # A guard benchmark can change when loaded DLC/content changes. It is shared
    # only inside this selection, never cached across commands or save files.
    with patch.object(caravans, 'guard_required', wraps=caravans.guard_required) as guard:
        caravans._candidate(game, engine.maps, alliance, fleet)
        assert guard.call_count == 1
        caravans._candidate(game, engine.maps, alliance, fleet)
        assert guard.call_count == 2


@pytest.mark.parametrize('units', [1, 3])
def test_internal_production_cannot_spend_future_sales_to_fund_raw_inputs(tmp_path, units):
    engine = GameEngine(ROOT, tmp_path)
    game = engine._load(engine.create_game('生产资金边界', 'supreme_metal', 'dao', 315,
                                           preset_id='nascent')['id'])
    market = state.local_market(game)
    item = 'foundation_pill'
    material = next(iter(basket_production.recipe(market, item)))
    raw = market['commodities'][material]
    market['commodities'] = {item: market['commodities'][item], material: raw}
    raw.update(stock=1000, reference=100, target=100)
    # ceil(reference * .45 / 100) yields the requested real recipe ratio.
    market['commodities'][item].update(stock=0, reference=units*100/.45-.01, target=100)
    assert basket_production.recipe(market, item) == {material: units}
    funds = basket_trade.quote(raw, 'buy', 5*units)['gross']
    source = 'background:human'
    transfer_value(game, source, 'world:human', balance(game, source)-funds, '隔离当期生产资金')
    original = raw['stock']
    produced, _ = basket_production.produce(game, market, source, item, 10)
    assert produced == 5
    assert raw['stock'] == original-5*units
    assert market['commodities'][item]['stock'] == 5
    assert balance(game, source) >= 0

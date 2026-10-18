"""Remote receipts settle once without advancing a remote society."""
import copy
import pytest
from test_regional_calendar import regional
from cultivation_life.engine.world import regions
from cultivation_life.regional_context import CalendarGame
from cultivation_life.system.economy import deferred
from cultivation_life.system.economy.deferred_settlement import apply
from cultivation_life.system.economy.ledger import account, balance, transfer_value
from cultivation_life.models import GameState


def test_remote_money_is_escrowed_and_not_given_twice(regional):
    _, game = regional
    source, target = 'background:human', 'background:spirit'
    old = balance(game, source), game.economy_v2['accounts'][target]['balance']
    transfer_value(game, source, target, 123, '测试跨界入账')
    assert balance(game, source) == old[0]-123
    assert game.economy_v2['accounts'][target]['balance'] == old[1]
    assert balance(game, 'regional:escrow:spirit') == 123
    view = CalendarGame(game, 'spirit', game.player.age)
    apply(view, 'spirit', game.player.age)
    assert game.economy_v2['accounts'][target]['balance'] == old[1]+123
    assert balance(game, 'regional:escrow:spirit') == 0
    saved = copy.deepcopy(game.to_dict())
    apply(view, 'spirit', game.player.age)
    assert game.to_dict() == saved


def test_unfunded_remote_payment_advances_and_preserves_debt(regional):
    _, game = regional
    key = 'background:spirit'
    game.economy_v2['accounts'][key]['balance'] = 10
    account(game, 'test:carrier')
    transfer_value(game, key, 'test:carrier', 100, '远方付款垫付')
    assert balance(game, 'test:carrier') == 100
    assert game.economy_v2['accounts'][key]['balance'] == 10
    view = CalendarGame(game, 'spirit', game.player.age)
    apply(view, 'spirit', game.player.age)
    book = deferred.state(game)
    assert (book['advanced'], book['repaid'], book['debts'][key]) == (100, 10, 90)
    restored = GameState.from_dict(game.to_dict())
    view = CalendarGame(restored, 'spirit', restored.player.age)
    apply(view, 'spirit', restored.player.age)
    assert balance(restored, 'test:carrier') == 100
    assert deferred.state(restored)['debts'][key] == 90


def test_local_insufficient_payment_remains_rejected(regional):
    _, game = regional
    key = 'background:human'
    game.economy_v2['accounts'][key]['balance'] = 10
    account(game, 'test:carrier')
    with pytest.raises(ValueError):
        transfer_value(game, key, 'test:carrier', 100, '本地不能透支')
    assert balance(game, key) == 10 and balance(game, 'test:carrier') == 0


def test_all_remote_years_stay_frozen_with_cross_obligations(regional):
    engine, game = regional
    initial = {w:r['year'] for w,r in game.world_simulation['regions'].items()}
    game.heavens_state['generation_enabled'] = True
    for _ in range(10):
        game.player.age += 1
        regions.advance(engine._dependencies.regions, game, [])
    assert all(r['year'] == (game.player.age if w == 'human' else initial[w])
               for w,r in game.world_simulation['regions'].items())


def test_remote_trade_does_not_settle_stock_until_entry(regional):
    engine, game = regional
    from cultivation_life.system.economy.freight_trade import market
    target = market(game, engine.maps, 'spirit', game.sects['taixuan'].location_id)
    item = next(iter(target['commodities']))
    row = target['commodities'][item]
    old = row['stock']
    assert deferred.market_change(game, target, item, 7, gross=200, fee=10, direction='in')
    assert row['stock'] == old
    apply(CalendarGame(game, 'spirit', game.player.age), 'spirit', game.player.age)
    assert row['stock'] == old+7


def test_frozen_task_and_society_resume_together(tmp_path):
    import random
    from cultivation_life.engine import GameEngine
    from test_regional_calendar import ROOT
    from regional_scenario import prepare, check, canonical
    engine = GameEngine(ROOT, tmp_path/'saves')
    with deferred.posting():
        game = prepare(engine, fixed_routes=True)
    game.player.world = 'celestial'  # Disposable initial observation.
    initial = copy.deepcopy(game)
    campaign = copy.deepcopy(game.heavens_state['runtime']['campaign'])
    orders = copy.deepcopy(game.merchant_state['posted'])
    fleets = copy.deepcopy(game.economy_v2['transport']['worlds']['spirit'])
    for year in range(12):
        game.player.age += 1
        engine._advance_world_year(game, random.Random(120+year), [], encounters=False)
        if year == 9:
            game.diplomacy_unit += 1
            engine._advance_wars_unit(game, random.Random(222))
    assert game.heavens_state['runtime']['campaign'] == campaign
    assert game.merchant_state['posted'] == orders
    assert game.economy_v2['transport']['worlds']['spirit'] == fleets
    assert all(r['year']==initial.player.age for w,r in game.world_simulation['regions'].items() if w!='celestial')
    assert any(w.get('deferred_units') for w in game.wars)
    regions.synchronize(engine._dependencies.regions, game, ['human'])
    assert game.heavens_state['runtime']['campaign'] != campaign
    assert all(not w.get('deferred_units') for w in game.wars if w['world']=='human')
    check(game)
    before = canonical(game)
    regions.synchronize(engine._dependencies.regions, game, ['human'])
    assert canonical(game) == before
    assert canonical(GameState.from_dict(game.to_dict())) == before


def test_remote_sale_pays_once_even_when_remote_market_is_empty(regional):
    engine, game = regional
    from cultivation_life.system.economy.freight_trade import market, sell
    target = market(game, engine.maps, 'spirit', game.sects['taixuan'].location_id)
    item = next(iter(target['commodities']))
    cash = 'market:'+target['id']
    game.economy_v2['accounts'][cash]['balance'] = 0
    fleet = dict(id='receipt-test', world='human', delivered=0)
    account(game, 'caravan:receipt-test')
    trip = dict(item=item, quantity=3, revenue=0)
    original = copy.deepcopy(target)
    sell(game, fleet, trip, target)
    received = balance(game, 'caravan:receipt-test')
    assert received > 0 and trip['quantity']==0 and fleet['delivered']==3
    assert target == original
    view = CalendarGame(game, 'spirit', game.player.age)
    apply(view, 'spirit', game.player.age)
    assert balance(game, 'caravan:receipt-test') == received
    assert target['commodities'][item]['stock'] == original['commodities'][item]['stock']+3
    before = copy.deepcopy(game.to_dict())
    apply(view, 'spirit', game.player.age)
    assert game.to_dict() == before


def test_unknown_remote_account_cannot_create_money(regional):
    _, game = regional
    before = copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError):
        transfer_value(game, 'alliance:spirit:missing', 'player', 100, '无效付款')
    assert game.to_dict() == before


def test_advance_and_repayment_conserve_cash_after_explicit_issuance(regional):
    from test_economy_network import cash
    _, game = regional
    source = 'background:spirit'
    game.economy_v2['accounts'][source]['balance'] = 10
    account(game, 'test:carrier')
    initial = cash(game)-game.economy_v2.get('issued', 0)
    transfer_value(game, source, 'test:carrier', 100, '垫款对账')
    assert cash(game)-game.economy_v2['issued'] == initial
    apply(CalendarGame(game, 'spirit', game.player.age), 'spirit', game.player.age)
    transfer_value(game, 'background:human', source, 90, '后续实款')
    apply(CalendarGame(game, 'spirit', game.player.age), 'spirit', game.player.age)
    assert cash(game)-game.economy_v2['issued'] == initial
    assert deferred.state(game)['advanced'] == deferred.state(game)['repaid'] == 100
    assert not deferred.state(game)['debts'] and balance(game, 'test:carrier') == 100


@pytest.mark.parametrize('damage', ['duplicate', 'delta', 'goods', 'arrival', 'units'])
def test_corrupt_deferred_records_are_rejected(regional, damage):
    _, game = regional
    transfer_value(game, 'background:human', 'background:spirit', 10, '收据校验')
    value = game.to_dict()
    sim = value['world_simulation']
    if damage == 'duplicate':
        sim['deferred']['pending']['spirit'] *= 2
    elif damage == 'delta':
        sim['deferred']['cash_delta']['background:spirit'] += 1
    elif damage == 'goods':
        sim['deferred']['goods_issued']['spirit:item'] = float('nan')
    elif damage == 'arrival':
        sim['arrivals'] = {'person': dict(world='spirit', year=game.player.age, entered=game.player.age+1)}
    else:
        sim['society_units'] = {'spirit': [dict(year=game.player.age, unit=1)]*2}
    with pytest.raises(ValueError):
        GameState.from_dict(value)


@pytest.mark.parametrize('registry', ['world', 'relationship', 'family'])
def test_returned_original_person_replays_missing_life_once(regional, registry):
    from cultivation_life.regional_context import calendar_scope
    from cultivation_life.system.combat.npc_lifecycle import move_world
    from cultivation_life.content_registry import WORLD_SYSTEMS
    engine, game = regional
    npc = next(n for n in game.world_npcs.values() if n.world == 'human' and n.alive)
    if registry != 'world':
        del game.world_npcs[npc.id]
        if registry == 'relationship':
            game.relationship_npcs[npc.id] = npc
        else:
            from cultivation_life.models import SectState
            game.family = SectState('return-family', '返乡家族', 'human', [npc], kind='family')
    original = npc.age
    npc.lifespan = original+2
    config = WORLD_SYSTEMS.get('transcendent_combat', {})
    with calendar_scope(game, 'human', game.player.age):
        move_world(npc, 'spirit', game.player.age, config)
    for _ in range(4):
        game.player.age += 1
        regions.advance(engine._dependencies.regions, game, [])
    assert npc.age == original and npc.alive
    with calendar_scope(game, 'human', game.player.age):
        move_world(npc, 'human', game.player.age, config)
    regions.synchronize(engine._dependencies.regions, game, ['human'])
    assert npc.age == original+2 and not npc.alive and '寿元' in npc.death_reason
    from cultivation_life.relationship_records import find_person
    assert find_person(game, npc.id, include_inactive=True) is npc
    saved = copy.deepcopy(game.to_dict())
    regions.synchronize(engine._dependencies.regions, game, ['human'])
    assert game.to_dict() == saved


def test_remote_notice_is_read_only_and_only_for_remote(regional):
    from cultivation_life.regional_context import remote_notice
    _, game = regional
    before = copy.deepcopy(game.to_dict())
    assert not remote_notice(game, 'human')
    assert '暂无法得到确切进度' in remote_notice(game, 'spirit')
    assert game.to_dict() == before


def test_personal_catchup_ascension_cannot_repeat_already_aged_years(regional):
    from unittest.mock import patch
    from cultivation_life.regional_context import calendar_scope
    from cultivation_life.system.combat.npc_lifecycle import move_world
    from cultivation_life.content_registry import WORLD_SYSTEMS
    engine, game = regional
    npc = next(n for n in game.world_npcs.values() if n.world == 'human' and n.alive)
    npc.realm_index=5; npc.layer=3; npc.path='dao'; npc.lifespan=None
    npc.cultivation_progress=100000
    original = npc.age
    config = WORLD_SYSTEMS.get('transcendent_combat', {})
    with calendar_scope(game, 'human', game.player.age):
        move_world(npc, 'spirit', game.player.age, config)
    for _ in range(4):
        game.player.age += 1
        regions.advance(engine._dependencies.regions, game, [])
    with calendar_scope(game, 'human', game.player.age):
        move_world(npc, 'human', game.player.age, config)
    with patch.object(engine, '_npc_breakthrough_probability', return_value=1):
        regions.synchronize(engine._dependencies.regions, game, ['human'])
        assert npc.world == 'spirit' and npc.age == original+1
        regions.synchronize(engine._dependencies.regions, game, ['spirit'])
    assert npc.age == original+4
    snapshot = copy.deepcopy(game.to_dict())
    regions.synchronize(engine._dependencies.regions, game, ['human', 'spirit'])
    assert game.to_dict() == snapshot


@pytest.mark.parametrize('seed', [17, 20261018, 87654])
def test_many_remote_payments_partial_entries_and_reload_conserve_cash(regional, seed):
    import random
    from test_economy_network import cash
    _, game = regional
    game.economy_v2['accounts']['background:spirit']['balance'] = 0
    initial = cash(game)-game.economy_v2.get('issued', 0)
    rng = random.Random(seed)
    wallets = ['background:human', 'background:spirit', 'background:demon', 'player']
    for step in range(60):
        source, target = rng.sample(wallets, 2)
        amount = rng.randint(1, 500)
        if source in {'background:human', 'player'}:
            amount = min(amount, balance(game, source))
        transfer_value(game, source, target, amount, '混合资金交割')
        if step % 3 == 0:
            world = rng.choice(['human', 'spirit', 'demon'])
            apply(CalendarGame(game, world, game.player.age), world, game.player.age)
        if step % 7 == 0:
            game = GameState.from_dict(game.to_dict())
        book = deferred.state(game)
        assert cash(game)-game.economy_v2.get('issued', 0) == initial
        assert book['advanced']-book['repaid'] == sum(book['debts'].values())+sum(
            r['amount'] for rows in book['pending'].values() for r in rows if r['kind']=='debit')
        for world, rows in book['pending'].items():
            credits = sum(r['amount'] for r in rows if r['kind']=='credit')
            assert game.economy_v2['accounts'].get('regional:escrow:'+world, {}).get('balance', 0) == credits
    for world in ('human', 'spirit', 'demon'):
        apply(CalendarGame(game, world, game.player.age), world, game.player.age)
    before = copy.deepcopy(game.to_dict())
    for world in ('human', 'spirit', 'demon'):
        apply(CalendarGame(game, world, game.player.age), world, game.player.age)
    assert game.to_dict() == before


def test_family_recruitment_cannot_repeat_in_player_and_regional_hooks(regional):
    import random
    from cultivation_life.models import SectState
    from cultivation_life.content_registry import WORLD_SYSTEMS
    engine, game = regional
    interval = int(WORLD_SYSTEMS['family']['recruitment_interval_years'])
    game.player.age += interval-game.player.age % interval
    npc = copy.deepcopy(game.sects['tianjian'].npcs[0])
    npc.id='family-audit-member';npc.lifespan=None
    game.family = SectState('family-audit','验收家族','human',[npc],kind='family')
    engine._annual_offspring_and_family_update(game, random.Random(5))
    first = game.family.to_dict()
    engine._annual_offspring_and_family_update(game, random.Random(6))
    assert game.family.to_dict() == first


def test_period_end_cannot_run_a_remote_faction_decision(regional):
    import random
    from unittest.mock import patch
    engine, game = regional
    candidates = [s for s in game.sects.values() if s.kind!='institution' and not s.extinct
                  and not s.founded_by_player and s.id!=game.player.faction_id]
    chosen = next(s for s in candidates if s.world=='spirit')
    game.intrigue_state['ai_cursor'] = candidates.index(chosen)-1
    game.diplomacy_unit = 3
    before = copy.deepcopy(chosen.to_dict())
    with patch.object(engine, '_intrigue_enabled', return_value=True):
        engine._advance_intrigue_unit(game, random.Random(45))
    assert chosen.to_dict() == before
    assert game.world_simulation['faction_units']['spirit'][-1]['faction']==chosen.id
    assert game.world_simulation['regions']['spirit']['year']==game.world_simulation['base_year']


def test_full_year_and_action_unit_leave_other_societies_unchanged(regional):
    import random
    from test_regional_calendar import projection
    engine, game = regional
    regions.synchronize(engine._dependencies.regions, game, regions.worlds())
    before = {w:copy.deepcopy(projection(game,w)) for w in regions.worlds() if w!='human'}
    rng = random.Random(20261018)
    for year in range(9):
        game.player.age += 1
        engine._advance_world_year(game, rng, [], encounters=False)
        if year % 3 == 2:
            engine._advance_diplomacy_unit(game, rng)
            engine._advance_intrigue_unit(game, rng)
    for world, original in before.items():
        assert projection(game, world) == original, world


@pytest.mark.parametrize('mixed_clocks', [False, True])
def test_same_year_entry_drains_action_units_once_in_chronological_order(regional, mixed_clocks):
    from unittest.mock import patch
    engine, game = regional
    if mixed_clocks:
        game.player.age += 2
    regions.synchronize(engine._dependencies.regions, game, ['spirit'])
    year = game.player.age
    game.world_simulation['society_units'] = {'spirit':[dict(year=year, unit=3), dict(year=year, unit=6)]}
    game.world_simulation['faction_units'] = {'spirit':[dict(year=year, unit=3, faction='taixuan')]}
    seen = []
    old = game.economy_v2['accounts']['background:spirit']['balance']
    transfer_value(game, 'background:human', 'background:spirit', 123, '同年行动前入账')
    def pressure(view, rng, news):
        assert balance(view, 'background:spirit') == old+123
        seen.append(('pressure', view.player.age, view.diplomacy_unit))
    def faction(deps, view, rng, identity, news):
        seen.append((identity, view.player.age, view.diplomacy_unit))
    with patch.object(engine, '_pressure_weak_npc_powers', side_effect=pressure), patch(
            'cultivation_life.system.intrigue.runtime.advance_npc_faction', side_effect=faction):
        regions.synchronize(engine._dependencies.regions, game, ['spirit', 'demon'] if mixed_clocks else ['spirit'])
        regions.synchronize(engine._dependencies.regions, game, ['spirit'])
    assert seen == [('pressure', year, 3), ('taixuan', year, 3), ('pressure', year, 6)]
    assert not game.world_simulation['society_units']['spirit']
    assert not game.world_simulation['faction_units']['spirit']

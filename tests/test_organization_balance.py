"""Cash conservation, optional spending, and viable aggregate organization finance."""
import copy
from pathlib import Path
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.system.economy import organizations as finance
from cultivation_life.system.economy.ledger import balance,transfer_value
from cultivation_life.system.economy.organization_production import annual_upkeep
from cultivation_life.system.economy.state import advance_economy
from test_organization_economy import total_cash
from test_family_expansion import family_game
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def setup(tmp_path):
    engine=GameEngine(ROOT,tmp_path)
    g=engine._load(engine.create_game('盈余验收','supreme_metal','dao',315,preset_id='core')['id'])
    g.pending_event=None
    entity=next(s for s in g.sects.values() if s.world=='human' and s.kind=='sect' and not s.extinct)
    return engine,g,finance.register(g,'sect',entity.id,entity.world)

def test_old_savings_and_losses_do_not_trigger_variable_expense(setup):
    _,g,row=setup;key=finance.key(row['kind'],row['identity'])
    transfer_value(g,'background:human',key,100000,'既存储蓄')
    before=copy.deepcopy(g.to_dict())
    assert finance.operating_services(g,row,-1000)==0
    assert finance.operating_services(g,row,0)==0
    assert balance(g,key)==100000 and row['expense']==0
    assert g.rng_state==before['rng_state']

def test_optional_services_preserve_reserve_and_do_not_create_debt(setup):
    _,g,row=setup;key=finance.key(row['kind'],row['identity'])
    row['expected_upkeep']=1000
    reserve=int(1000*.65*3)
    transfer_value(g,'background:human',key,reserve+70,'周转金')
    before=total_cash(g)
    assert finance.operating_services(g,row,10000)==70
    assert balance(g,key)==reserve
    assert total_cash(g)==before and row['shortfall']==0
    assert not g.family_state.get('debt')
    assert GameState.from_dict(g.to_dict()).economy_v2==g.economy_v2

def test_nothing_can_be_paid_from_empty_treasury(setup):
    _,g,row=setup;before=total_cash(g)
    assert finance.operating_services(g,row,100000)==0
    assert total_cash(g)==before

def test_unpaid_expansion_does_not_lock_out_recovery_production(setup):
    from cultivation_life.system.economy.industry import settle_industry
    engine,g,row=setup;entity=g.sects[row['identity']]
    row['industry_level']=3
    assert balance(g,finance.key('sect',entity.id))==0
    settle_industry(g,engine.maps,entity,row,1)
    assert row['industry_utilization']==0
    before=total_cash(g)
    assert finance.produce(g,engine.maps,entity,row)>0
    assert total_cash(g)==before

def test_industry_maintenance_cannot_take_basic_care_reserve(setup):
    from cultivation_life.system.economy.industry import settle_industry
    engine,g,row=setup;entity=g.sects[row['identity']];key=finance.key('sect',entity.id)
    row.update(industry_level=10,expected_upkeep=1000)
    transfer_value(g,'background:human',key,1950,'三年基本养护')
    before=total_cash(g)
    settle_industry(g,engine.maps,entity,row,1)
    assert row['industry_utilization']==0 and balance(g,key)==1950
    assert total_cash(g)==before

def organization_estate(setup,kind='farm'):
    from cultivation_life.system.economy.enterprise_acquisition import acquire
    engine,g,row=setup;source=finance.key(row['kind'],row['identity'])
    row['expected_upkeep']=1000
    transfer_value(g,'background:human',source,1000000,'产权经营周转金')
    estate=acquire(g,engine.maps,'human',g.player.location_id,kind,'sect',row['identity'],source,4)
    estate.update(auto_buy=True,buy_limit=10**12,auto_sell=False)
    return engine,g,row,estate

def test_estate_receipt_recovers_actual_costs_across_owned_estates_before_services(setup):
    from cultivation_life.system.economy.enterprise_operations import start_job,advance_estates,market_trade
    from cultivation_life.system.economy.enterprise_market import market_at
    from cultivation_life.system.economy.enterprise_acquisition import acquire
    from cultivation_life.system.economy.enterprise_state import take,put
    engine,g,row,farm=organization_estate(setup)
    start_job(g,engine.maps,farm)
    job=copy.deepcopy(farm['job']);g.player.age=job['finish'];advance_estates(g,engine.maps)
    assert row['estate_cost_credit']>0
    credit=row['estate_cost_credit'];key=finance.key('sect',row['identity'])
    shop=acquire(g,engine.maps,'human',g.player.location_id,'shop','sect',row['identity'],key,4)
    take(farm,job['item'],job['quantity']);put(shop,job['item'],job['quantity'])
    market=market_at(g,engine.maps,shop);before=total_cash(g);cash_before=balance(g,key)
    bill=market_trade(g,shop,market,job['item'],job['quantity'],'sell')
    surplus=max(0,bill['total']-credit)
    assert surplus>0 and row['income']==surplus
    assert row['operating_paid']>0 and row['operating_paid']<bill['total']*.4
    assert balance(g,key)==cash_before+bill['total']-row['operating_paid']
    assert row['estate_cost_credit']==0 and row['supply_budget_credit']>0
    assert total_cash(g)==before
    assert GameState.from_dict(g.to_dict()).economy_v2==g.economy_v2

def test_real_estate_spread_loss_never_charged_as_operating_profit(setup):
    from cultivation_life.system.economy.enterprise_operations import market_trade
    from cultivation_life.system.economy.enterprise_market import market_at
    engine,g,row,estate=organization_estate(setup,'shop')
    market=market_at(g,engine.maps,estate);item='dew_grass_seed';before=total_cash(g)
    buy=market_trade(g,estate,market,item,10,'buy')
    sale=market_trade(g,estate,market,item,10,'sell')
    assert buy['total']>sale['total']
    assert row['estate_cost_credit']==buy['total']-sale['total']
    assert row['income']==0 and not row.get('operating_paid',0)
    assert total_cash(g)==before

def test_family_can_cover_care_and_keep_a_construction_budget(tmp_path):
    engine=GameEngine(ROOT,tmp_path);g=family_game(engine)
    g.family.npcs[0].realm_index=4
    finance.ensure_organizations(g,engine.maps);key=finance.key('family',g.family.id)
    earned=incurred=0
    for _ in range(100):
        g.player.age+=1;advance_economy(g);finance.advance_organizations(g,engine.maps)
        row=g.economy_v2['organizations'][key];earned+=row['income'];incurred+=row['expense']
    assert earned>incurred>0 and not g.family_state.get('debt')
    assert balance(g,key)>row['expected_upkeep']*3
    engine.store.save(g);assert engine.store.load(g.id).economy_v2==g.economy_v2

def test_high_realm_care_is_more_than_low_realm_and_world_growth_is_bounded():
    assert annual_upkeep({8:1},2)>annual_upkeep({4:1},2)>annual_upkeep({4:1},1)
    # A high-world resident does not inherit the 25x production multiplier as
    # mandatory care; this leaves room for long-term construction budgets.
    assert annual_upkeep({10:1},3)<annual_upkeep({10:1},1)*10

@pytest.mark.parametrize('world,rank',[('human',4),('spirit',8),('celestial',10)])
def test_controlled_faction_can_save_for_real_projects_over_century(tmp_path,world,rank):
    engine=GameEngine(ROOT,tmp_path)
    g=engine._load(engine.create_game('事务预算','supreme_metal','dao',315,custom_start=dict(world=world,realm_index=rank))['id'])
    g.pending_event=None
    entity=next(s for s in g.sects.values() if s.world==world and s.kind=='sect' and not s.extinct)
    entity.founded_by_player=True;entity.founder_player_id=g.id;g.player.faction_id=entity.id
    finance.ensure_organizations(g,engine.maps)
    key=finance.key('sect',entity.id);rng=copy.deepcopy(g.rng_state);address=(g.player.world,g.player.location_id)
    incurred=earned=0
    for _ in range(100):
        g.player.age+=1;advance_economy(g);finance.advance_organizations(g,engine.maps)
        row=g.economy_v2['organizations'][key];incurred+=row['expense'];earned+=row['income']
    assert earned>incurred>0
    assert balance(g,key)>=row['expected_upkeep']*3
    assert g.rng_state==rng and address==(g.player.world,g.player.location_id)
    before=copy.deepcopy(g.economy_v2);finance.advance_organizations(g,engine.maps)
    assert g.economy_v2==before

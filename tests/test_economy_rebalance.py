"""Conservation and aggregate-basket boundaries, independent of NPC simulation."""
import copy
import math
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.system.economy import basket_rules, basket_production, basket_consumption, organizations, depot
from cultivation_life.system.economy.state import local_market, settle_market, advance_economy
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.economy.rewards import grant
from cultivation_life.system.war import logistics, requirements, supply, stationing

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def economy(tmp_path):
    engine=GameEngine(ROOT,tmp_path)
    game=engine._load(engine.create_game('消费重平衡','supreme_metal','dao',7701,preset_id='nascent')['id'])
    game.pending_event=None
    return engine,game


def cash(game):
    return balance(game,'player')+sum(r['balance'] for r in game.economy_v2['accounts'].values())+sum(r.get('resources',0) for r in game.intrigue_state['factions'].values())+sum(r['reserves'] for rows in game.merchant_state.get('worlds',{}).values() for r in rows)+game.heavenly_court.get('treasury',0)+sum(r['treasury'] for r in game.upper_institutions.values())


def test_actual_consumption_no_topup_or_growth_issuance(economy):
    engine,game=economy;market=local_market(game)
    dealer='market:'+market['id']
    transfer_value(game,dealer,'background:human',balance(game,dealer),'清空经销商')
    before=cash(game);stock=sum(r['stock'] for r in market['commodities'].values())
    game.player.age+=100
    with patch.object(basket_consumption,'produce',return_value=(0,0)):
        advance_economy(game)
    assert cash(game)==before and game.economy_v2.get('issued',0)==0
    assert market['terminal_consumed'] > 0 and market['household_spending'] > 0
    assert sum(r['stock'] for r in market['commodities'].values()) < stock
    # Funds come from actual purchases, not an unconditional opening reset.
    assert balance(game,dealer)==market['household_spending']-market['fees']
    saved=copy.deepcopy(game.to_dict())
    assert not settle_market(game,market) and game.to_dict()==saved
    assert GameState.from_dict(saved).economy_v2==game.economy_v2


def test_recipe_inputs_conserve_real_stock_and_cash(economy):
    engine,game=economy;market=local_market(game)
    entity=game.sects['tianjian'];row=organizations.register(game,'sect',entity.id,'human')
    source=depot.treasury(game,entity)
    transfer_value(game,'background:human',source,100000,'作坊预算')
    item='foundation_pill';inputs=basket_production.recipe(market,item)
    assert inputs
    market['commodities'][item]['stock']=0
    before={k:r['stock'] for k,r in market['commodities'].items()};money=cash(game)
    n,net=basket_production.produce(game,market,source,item,2,allow_loss=True)
    assert n==2
    assert market['commodities'][item]['stock']==before[item]+n
    for k,units in inputs.items():assert market['commodities'][k]['stock']==before[k]-n*units
    assert cash(game)==money
    for k in inputs:market['commodities'][k]['stock']=0
    saved=copy.deepcopy(game.to_dict())
    assert basket_production.produce(game,market,source,item,2,allow_loss=True)==(0,0)
    assert game.to_dict()==saved


def test_finished_talismans_and_elixirs_cannot_be_extracted(economy):
    _,game=economy;market=local_market(game)
    assert not basket_rules.is_raw('iron_skin_talisman')
    assert not basket_rules.is_raw('golden_core_dew')
    assert basket_production.recipe(market,'iron_skin_talisman')
    assert basket_rules.is_raw('dew_grass_seed')
    assert basket_rules.is_raw('talisman_nether_9_jade')
    assert not basket_rules.is_raw('talisman_nether_9_paper')
    from cultivation_life.system.economy.enterprise_rules import recipes
    from cultivation_life.system.economy.state import commodity_catalog
    for world,profile in WORLD_SYSTEMS['world_profiles'].items():
        if profile['tier']>0:
            assert basket_rules.is_raw(recipes(world,commodity_catalog(world))['mine']['output'])


def test_deployed_and_research_members_keep_supplies_but_stop_working(economy):
    engine,game=economy;entity=game.sects['tianjian'];war=prepared_war(engine,game)
    row=organizations.register(game,'sect',entity.id,'human')
    war['roster']['attacker']=[n.id for n in entity.npcs]
    assert organizations.produce(game,engine.maps,entity,row)==0
    assert row['labor_capacity']==0 and sum(row['workforce'].values())>0
    war['deployment']={'attacker':.5}
    with patch('cultivation_life.person_assignments.research_assignment',return_value=True):
        assert organizations.produce(game,engine.maps,entity,row)==0
        assert row['labor_capacity']==0
    war['escaped']['attacker']=war['roster']['attacker'][:1]
    organizations.produce(game,engine.maps,entity,row)
    assert row['labor_capacity']>0


def test_member_depot_consumption_preserves_reserved_requests(economy):
    engine,game=economy;entity=game.sects['tianjian'];market=local_market(game)
    row=organizations.register(game,'sect',entity.id,'human')
    row['workforce']={'1':10}
    stock=depot.ensure(game,entity);item=basket_rules.candidates(market,'training:1')[0]
    stock['stock']['item:'+item]=20
    from cultivation_life.system.economy.organization_consumption import consume
    before=cash(game)
    consume(game,market,entity,row,100,0)
    assert stock['stock']['item:'+item]<20 and row['supplies_consumed']>0
    assert cash(game)==before and balance(game,depot.treasury(game,entity))==0


def test_paid_cultivation_bonus_is_capped_and_free_base_survives(economy):
    import random
    engine,game=economy
    npc=copy.deepcopy(game.sects['tianjian'].npcs[-1]);npc.realm_index=1;npc.layer=1;npc.cultivation_progress=0
    base=copy.deepcopy(npc);paid=copy.deepcopy(npc);over=copy.deepcopy(npc)
    engine._advance_npc_cultivation(base,random.Random(19),world_age=game.player.age)
    engine._advance_npc_cultivation(paid,random.Random(19),world_age=game.player.age,support=1)
    engine._advance_npc_cultivation(over,random.Random(19),world_age=game.player.age,support=100)
    assert base.cultivation_progress>0
    assert paid.cultivation_progress==pytest.approx(base.cultivation_progress*1.1)
    assert over.cultivation_progress==paid.cultivation_progress


def test_funded_reward_and_personal_statement_reconcile(economy):
    _,game=economy;before=cash(game)
    source='background:human';old=balance(game,source)
    paid=grant(game,46,'委托实付')
    from cultivation_life.system.economy.personal import public_personal
    assert paid==46 and balance(game,source)==old-46 and cash(game)==before
    assert public_personal(game)['other_change']==0


def test_hostility_settlement_uses_original_treasury_and_cannot_mint(economy):
    from cultivation_life.engine.world.hostility import _settlement_payment
    _,game=economy;organizations.register(game,'sect','tianjian','human')
    source='organization:sect:tianjian';before=cash(game)
    transfer_value(game,'background:human',source,23,'和解备款')
    assert _settlement_payment(game,'sect','tianjian',500)==23
    assert _settlement_payment(game,'sect','tianjian',500)==0
    assert balance(game,source)==0 and cash(game)==before


def test_index_bounded_and_invalidates_on_goods_added(economy):
    _,game=economy;market=local_market(game)
    cached=basket_rules.index(market)
    assert basket_rules.index(market) is cached
    product=copy.deepcopy(market['commodities']['foundation_pill'])
    market['commodities']['test_added_item']=product
    assert basket_rules.index(market) is not cached
    assert all('test_added_item' not in keys for keys in basket_rules.index(market).values())
    assert 'basket_index' not in market


def test_stable_fractional_demand_batch_and_split_match(economy):
    _,game=economy
    market=local_market(game);product=market['commodities']['green_bamboo_sword']
    product.update(stock=5000.,target=100.,initial_target=100.)
    market['commodities']={'green_bamboo_sword':product}
    batch=copy.deepcopy(game);split=copy.deepcopy(game)
    with patch.object(basket_consumption,'produce',return_value=(0,0)):
        basket_consumption.settle(batch,local_market(batch),100)
        for _ in range(100):basket_consumption.settle(split,local_market(split),1)
    a,b=local_market(batch),local_market(split)
    assert a['terminal_consumed']==b['terminal_consumed']==80
    assert a['commodities']['green_bamboo_sword']['stock']==b['commodities']['green_bamboo_sword']['stock']
    assert abs(a['household_spending']-b['household_spending'])<=100  # Integer bill rounding.


def test_small_battle_baskets_keep_prepaid_fraction(economy):
    engine,game=economy;war=prepared_war(engine,game)
    row=war['logistics']['sides']['attacker']
    row['realm_groups']={'1':1}
    market=game.economy_v2['markets'][f"{row['world']}:{row['location']}"]
    row['items']={}
    for group in requirements.physical(game,war,'attacker'):
        item=requirements.suitable(market,group)[0]
        row['items'][item]=row['items'].get(item,0)+10
    source=supply.wallet(war,'attacker')
    transfer_value(game,'background:human',source,10000,'试验能源')
    supply.consume_battle(game,war,'attacker');first=sum(row['consumed_items'].values())
    supply.consume_battle(game,war,'attacker')
    assert sum(row['consumed_items'].values())==first
    assert all(-1<n<=0 for n in row['demand_credit'].values())


@pytest.mark.parametrize('years',[1,100,500,1000])
def test_basket_work_bounded_by_groups_not_elapsed_years(economy,years):
    _,game=economy;market=local_market(game)
    basket_rules.index(market)
    groups=len(basket_rules.index(market))
    with patch.object(basket_consumption,'purchase',wraps=basket_consumption.purchase) as buying:
        basket_consumption.settle(game,market,years)
    assert buying.call_count <= 2*groups <= 168
    assert len(game.economy_v2['ledger'])<=80


def prepared_war(engine,game):
    for identity in ('tianjian','wanmo'):
        entity=game.sects[identity];organizations.register(game,'sect',identity,entity.world)
        transfer_value(game,'background:human',depot.treasury(game,entity),1000000,'真实军费')
    return engine._start_war(game,'sect','tianjian','wanmo',initiated_by_player=True)


def test_war_roster_grades_cash_and_price_independent_duration(economy):
    engine,game=economy;war=prepared_war(engine,game)
    row=war['logistics']['sides']['attacker']
    market=game.economy_v2['markets'][f"{row['world']}:{row['location']}"]
    groups=requirements.refresh(game,war,'attacker')
    assert sum(groups.values())==len(war['roster']['attacker'])
    for group in requirements.physical(game,war,'attacker'):
        rank=int(group.split(':')[1])
        assert all(market['commodities'][k]['tier']>=rank for k in requirements.suitable(market,group))
    duration=supply.turns(game,war,'attacker')
    for product in market['commodities'].values():product['price']*=20
    assert supply.turns(game,war,'attacker')==duration
    old=copy.deepcopy(row['realm_groups'])
    war['escaped']['attacker'].append(war['roster']['attacker'][0])
    assert sum(requirements.refresh(game,war,'attacker').values())==sum(old.values())-1
    assert GameState.from_dict(game.to_dict())


def test_mobilization_scope_changes_both_power_members_and_requirements(economy):
    engine,game=economy;war=prepared_war(engine,game)
    full=engine._available_warriors(game,war,'attacker')
    requirements.refresh(game,war,'attacker');before=sum(requirements.physical(game,war,'attacker').values())
    war['deployment']={'attacker':.5}
    half=engine._available_warriors(game,war,'attacker')
    requirements.refresh(game,war,'attacker')
    assert len(half)==math.ceil(len(full)/2)
    assert sum(requirements.physical(game,war,'attacker').values())<before


def test_stationing_is_elapsed_year_and_idempotent(economy):
    engine,game=economy;war=prepared_war(engine,game);before=cash(game)
    game.player.age+=100;stationing.advance(game)
    row=war['logistics']['sides']['attacker'];paid=row['stationing_paid']
    assert paid>0 and cash(game)==before
    stationing.advance(game);assert row['stationing_paid']==paid
    assert GameState.from_dict(game.to_dict())


def test_stationing_fraction_matches_split_and_batch(economy):
    engine,game=economy;war=prepared_war(engine,game)
    batch=copy.deepcopy(game);split=copy.deepcopy(game)
    batch.player.age+=1000;stationing.advance(batch)
    for _ in range(1000):
        split.player.age+=1;stationing.advance(split)
    for side in ('attacker','defender'):
        a=batch.wars[-1]['logistics']['sides'][side]
        b=split.wars[-1]['logistics']['sides'][side]
        assert a['stationing_paid']==b['stationing_paid']
        assert a['stationing_credit']==pytest.approx(b['stationing_credit'],abs=1e-9)


def test_all_immortal_units_and_actual_long_action_are_100(economy):
    engine,game=economy
    assert max(WORLD_SYSTEMS['time_units'].values())==100
    for rank in range(9,13):assert WORLD_SYSTEMS['time_units'][str(rank)]==100


def test_legacy_logistics_queries_do_not_adopt_or_charge(economy):
    engine,game=economy;war=prepared_war(engine,game)
    for row in war['logistics']['sides'].values():row.pop('realm_groups')
    snapshot=copy.deepcopy(game.to_dict())
    logistics.public(game,war,'attacker')
    assert game.to_dict()==snapshot


def test_minimum_grade_combines_mortals_and_cultivators(economy):
    engine,game=economy;war=prepared_war(engine,game)
    war['logistics']['sides']['attacker']['realm_groups']={'0':2,'1':3}
    physical=requirements.physical(game,war,'attacker')
    for category,rate in requirements.SHARES.items():
        assert physical[f'{category}:1']==pytest.approx((2*basket_rules.REALM_WEIGHTS[0]+3)*rate)


def test_departed_roster_member_does_not_remain_deployed(economy):
    engine,game=economy;war=prepared_war(engine,game)
    before=engine._available_warriors(game,war,'attacker')
    before[0].world='spirit'
    assert len(engine._available_warriors(game,war,'attacker'))==len(before)-1
    assert sum(requirements.refresh(game,war,'attacker').values())==len(before)-1


def test_old_schema10_adopts_without_retroactive_consumption(economy):
    engine,game=economy
    from cultivation_life.system.economy.enterprise_acquisition import acquire
    from cultivation_life.system.economy.enterprise_operations import start_job
    transfer_value(game,'background:human','player',100000,'产权测试资金')
    row=acquire(game,engine.maps,game.player.world,game.player.location_id,'farm','player',game.id,'player',game.player.realm_index)
    transfer_value(game,'background:human',f'estate:{row["id"]}',1000,'已付款批次资金')
    row['auto_buy']=True;start_job(game,engine.maps,row)
    original_job=copy.deepcopy(row['job'])
    game.economy_v2.pop('consumption_policy');game.economy_v2.pop('policy_year')
    before=cash(game);stocks=copy.deepcopy(local_market(game)['commodities'])
    game.player.age+=800
    from cultivation_life.system.economy.state import ensure_state
    ensure_state(game);organizations.advance_organizations(game,engine.maps)
    assert cash(game)==before and local_market(game)['commodities']==stocks
    assert row['last_year']==game.player.age and row['arrears']==0 and row['job']==original_job
    assert game.version==10

"""Native material counts, real multi-input chains, paid needs and title rights."""
import copy
import math
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.content_registry import ITEM_CATALOG, MARKET_GOODS, WORLD_SYSTEMS
from cultivation_life.economy_content import ROLES, TEMPLATES, WORLD_MATERIALS, specification, material_id, product_id, inputs
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, SectNpc
from cultivation_life.rules import add_item, has_item
from cultivation_life.system.economy import basket_rules, basket_production, basket_consumption, organizations, depot
from cultivation_life.system.economy.state import local_market, commodity_catalog, ensure_state, ensure_regional_market
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.economy.organization_consumption import consume, apply_longevity
from cultivation_life.system.economy.demand_profiles import SHARES, USES, rates
from cultivation_life.system.economy.resource_access import site_profile, permits, public_allowance
from cultivation_life.system.economy.enterprise_acquisition import acquire
from cultivation_life.system.economy.enterprise_operations import start_job, advance_estates
from cultivation_life.system.economy.enterprise_rules import recipes
from cultivation_life.system.war.requirements import suitable

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def economy(tmp_path):
    engine=GameEngine(ROOT,tmp_path)
    game=engine._load(engine.create_game('商品闭环验收','supreme_metal','dao',315,preset_id='nascent')['id'])
    game.pending_event=None
    return engine,game


def cash(game):
    return (balance(game,'player')+sum(r['balance'] for r in game.economy_v2['accounts'].values())
        +sum(r.get('resources',0) for r in game.intrigue_state['factions'].values())
        +sum(r['reserves'] for rows in game.merchant_state.get('worlds',{}).values() for r in rows)
        +game.heavenly_court.get('treasury',0)+sum(r['treasury'] for r in game.upper_institutions.values()))


@pytest.mark.parametrize('world',WORLD_MATERIALS)
def test_each_world_has_its_own_nine_per_grade_and_all_roles_have_sinks(world):
    cap={1:5,2:8,3:12}[WORLD_SYSTEMS['world_profiles'][world]['tier']]
    native=commodity_catalog(world)
    raw=[k for k in native if specification(k) and specification(k)['raw']]
    assert len(raw)==cap*9
    assert all(specification(k)['world']==world for k in raw)
    for grade in range(1,cap+1):
        assert {specification(k)['role'] for k in raw if native[k]['tier']==grade}==set(ROLES)
        used=set()
        for template in TEMPLATES:
            item=product_id(world,grade,template)
            market=dict(world=world,commodities={k:dict(tier=r['tier'],reference=r['base_price']) for k,r in native.items()})
            ingredients=basket_production.recipe(market,item)
            assert ingredients==inputs(world,grade,template)
            assert 1<=len(ingredients)<=3
            assert all(k in raw and native[k]['tier']==grade for k in ingredients)
            used.update(specification(k)['role'] for k in ingredients)
            assert not basket_rules.is_raw(item)
        assert used==set(ROLES)
    assert all(basket_rules.is_raw(k) and basket_rules.purpose(k) is None for k in raw)


def test_material_names_are_differentiated_and_total_is_882():
    materials=[i for i in ITEM_CATALOG if specification(i) and specification(i)['raw']]
    assert len(materials)==882
    assert len({ITEM_CATALOG[i].name for i in materials})==882
    assert all(not specification(g['content_id']) or g['world'] not in {'lost','rift'} for g in MARKET_GOODS)


def test_realm_profiles_reflect_finite_lifespan_and_bottlenecks():
    assert all(sum(row)==100 for row in SHARES)
    assert rates(4)['longevity']>rates(4)['artifact']
    assert rates(5)['breakthrough']>rates(4)['breakthrough']
    assert rates(5)['longevity']>rates(5)['artifact']
    assert all(rates(r)['longevity']==0 for r in range(6,13))
    assert all(rates(r)['artifact']==max(rates(r).values()) for r in range(7,13))
    assert all(rates(r)['artifact']>sum(rates(r)[u] for u in ('healing','cultivation','longevity','breakthrough'))
               for r in range(7,13))
    assert all(sum(rates(r).values())==pytest.approx(.113) for r in range(13))


def test_multi_input_production_consumes_every_real_ingredient_once(economy):
    engine,game=economy;market=local_market(game)
    item=product_id('human',4,'longevity');ingredients=basket_production.recipe(market,item)
    market['commodities'][item]['stock']=0
    before={k:r['stock'] for k,r in market['commodities'].items()};money=cash(game)
    made,_=basket_production.produce(game,market,'background:human',item,3)
    assert made==3 and market['commodities'][item]['stock']==3
    for key,n in ingredients.items():assert market['commodities'][key]['stock']==before[key]-made*n
    assert cash(game)==money
    market['commodities'][next(iter(ingredients))]['stock']=0
    saved=copy.deepcopy(game.to_dict())
    assert basket_production.produce(game,market,'background:human',item,1)==(0,0)
    assert game.to_dict()==saved


def test_purpose_baskets_do_not_consume_raw_cores_and_can_change_goods(economy):
    _,game=economy;market=local_market(game)
    core=material_id('human',4,'core_soul')
    assert core not in [k for keys in basket_rules.purpose_index(market).values() for k in keys]
    group='artifact:4'
    first=basket_rules.purpose_candidates(market,group,limit=1,rotation=0)
    second=basket_rules.purpose_candidates(market,group,limit=1,rotation=1)
    assert first!=second
    previous=market['commodities'][core]['stock']
    with patch.object(basket_consumption,'produce',return_value=(0,0)):
        basket_consumption.settle(game,market,100)
    assert market['commodities'][core]['stock']==previous
    assert all(len(keys)<=2 for keys in [basket_rules.purpose_candidates(market,g) for g in basket_rules.purpose_index(market)])


def test_war_equivalence_rejects_longevity_breakthrough_and_raws(economy):
    _,game=economy;market=local_market(game)
    medical=suitable(market,'medical:4');repair=suitable(market,'material:4')
    assert medical and repair
    assert all(basket_rules.purpose(i)=='healing' for i in medical)
    assert all(basket_rules.purpose(i)=='repair' for i in repair)
    assert not any(basket_rules.is_raw(i) for i in (*medical,*repair))
    assert product_id('human',4,'longevity') not in medical
    assert product_id('human',4,'breakthrough') not in medical
    assert all(market['commodities'][i]['tier'] in {4,5} for i in (*medical,*repair))


def test_only_paid_longevity_grants_bounded_idempotent_lifespan(economy):
    _,game=economy;entity=game.sects['tianjian'];market=local_market(game)
    row=organizations.register(game,'sect',entity.id,'human')
    row.update(workforce={'4':1},last_year=game.player.age)
    npc=SectNpc('longevity-test','寿元验收','弟子',4,1,1000,1200)
    entity.npcs=[npc]
    held=depot.ensure(game,entity)
    held['stock']['item:'+product_id('human',4,'longevity')]=1000
    consume(game,market,entity,row,100,0)
    before=npc.lifespan;apply_longevity(game,npc,'sect',entity.id)
    assert before<npc.lifespan<=before+150
    once=npc.lifespan;apply_longevity(game,npc,'sect',entity.id)
    assert npc.lifespan==once
    for _ in range(100):
        game.player.age+=1;row['last_year']=game.player.age
        row['longevity_support']={'4':5.};apply_longevity(game,npc,'sect',entity.id)
    assert npc.economic_lifespan_bonus==150 and npc.lifespan==before+150
    row['longevity_support']={};npc.economic_provision_year=None
    apply_longevity(game,npc,'sect',entity.id)
    assert npc.lifespan==before+150
    restored=GameState.from_dict(game.to_dict()).sects[entity.id].npcs[0]
    assert restored.economic_lifespan_bonus==150


@pytest.mark.parametrize('kind',['farm','mine','hunt'])
def test_native_resource_title_is_local_and_upgrade_cannot_reroll_it(economy,kind):
    engine,game=economy
    transfer_value(game,'background:human','player',100000,'产权资金')
    row=acquire(game,engine.maps,game.player.world,game.player.location_id,kind,'player',game.id,'player',game.player.realm_index)
    profile=site_profile(row['world'],row['location'],kind)
    assert len(profile)==2
    options=recipes(row['world'],commodity_catalog(row['world']))
    target=next(k for k,r in options.items() if r['output']==profile[0])
    row['recipe']=target;row['auto_buy']=True
    transfer_value(game,'background:human',f'estate:{row["id"]}',100000,'原料工钱')
    if kind in {'mine','hunt'}:row['reserve']=4
    money=cash(game);start_job(game,engine.maps,row)
    assert cash(game)==money and row['job']['item']==profile[0]
    if kind in {'mine','hunt'}:assert row['reserve']==0
    row['level']=5
    assert site_profile(row['world'],row['location'],kind)==profile
    forbidden=next(r for r in options.values() if r['kind']==kind and specification(r['output']) and r['output'] not in profile)
    assert not permits(row,forbidden)
    game.player.age=row['job']['finish'];advance_estates(game,engine.maps)
    assert row['stock'][profile[0]]==4
    if kind in {'mine','hunt'}:
        with pytest.raises(ValueError,match='储量不足'):start_job(game,engine.maps,row)
    assert GameState.from_dict(game.to_dict())


def test_private_title_reduces_public_share_without_borrowing_private_reserves(economy):
    engine,game=economy;market=local_market(game)
    item=site_profile('human',market['location'],'mine')[0]
    before=public_allowance(game,market,item)
    transfer_value(game,'background:human','player',100000,'产权资金')
    row=acquire(game,engine.maps,'human',market['location'],'mine','player',game.id,'player',4)
    after=public_allowance(game,market,item)
    assert after<before
    market['commodities'][item]['stock']=0
    reserve=row['reserve']
    made,_=basket_production.produce(game,market,'background:human',item,100000)
    assert made<=after and row['reserve']==reserve
    assert public_allowance(game,market,item)==after-made
    assert basket_production.produce(game,market,'background:human',item,100000)==(0,0)


def test_schema10_adopts_new_catalog_from_zero_without_charging_old_years(economy):
    engine,game=economy;market=local_market(game)
    market['commodities']={k:r for k,r in market['commodities'].items() if not specification(k)}
    market.pop('goods_policy');game.economy_v2.pop('demand_policy')
    money=cash(game);old=copy.deepcopy(market['commodities']);game.player.age+=1000
    ensure_state(game);ensure_regional_market(game,engine.maps,market['world'],market['location'])
    assert cash(game)==money and market['commodities'].items()>=old.items()
    assert all(r['stock']==0 for k,r in market['commodities'].items() if specification(k))
    assert market['last_year']==game.player.age and game.version==10
    assert GameState.from_dict(game.to_dict())


def test_black_market_remains_independent_material_fallback(economy):
    engine,game=economy;item=material_id('human',4,'core_soul')
    game.auction_state.update(status='black_market',world='human',location_id=game.player.location_id,location_name='黑市验收')
    transfer_value(game,'background:human','player',100000,'黑市预算')
    market=local_market(game);market['commodities'][item]['stock']=0
    engine.store.save(game)
    view=engine.search_black_market(game.id,ITEM_CATALOG[item].name)
    offer=next(r for r in view['auction_system']['black_market_results'] if r['content_id']==item)
    before=engine.store.load(game.id);money=cash(before)
    engine.buy_black_market_item(game.id,offer['id'],3)
    after=engine.store.load(game.id)
    assert has_item(after.player,item,3) and cash(after)==money
    assert local_market(after)['commodities'][item]['stock']==0


def test_manual_standard_alchemy_requires_real_complete_recipe_and_native_world(economy):
    engine,game=economy;item=product_id('human',4,'longevity');required=inputs('human',4,'longevity')
    for key,number in required.items():add_item(game.player,key,number)
    game.player.mp=1e6;engine.store.save(game)
    original=engine.store._path(game.id).read_bytes()
    incomplete=[dict(item_id=next(iter(required)),quantity=1)]
    with pytest.raises(ValueError,match='完整'):engine.refine_pill(game.id,item,incomplete)
    assert engine.store._path(game.id).read_bytes()==original
    with pytest.raises(ValueError,match='不能炼制'):engine.refine_pill(game.id,product_id('demon',4,'longevity'),incomplete)
    engine.refine_pill(game.id,item,[dict(item_id=k,quantity=n) for k,n in required.items()])
    after=engine.store.load(game.id)
    assert all(not has_item(after.player,k) for k in required)
    assert after.history[-1].event_id=='SYS_ALCHEMY'


def test_player_longevity_is_capped_and_low_grade_cannot_feed_high_realm(economy):
    engine,game=economy;item=product_id('human',4,'longevity')
    add_item(game.player,item,40);add_item(game.player,product_id('human',1,'longevity'))
    initial=game.player.lifespan;game.economy_v2['personal']['longevity_used']=145
    engine.store.save(game)
    engine.use_item(game.id,item)
    after=engine.store.load(game.id)
    assert after.player.lifespan==initial+5 and after.economy_v2['personal']['longevity_used']==150
    saved=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError,match='上限'):engine.use_item(game.id,item)
    with pytest.raises(ValueError,match='同阶'):engine.use_item(game.id,product_id('human',1,'longevity'))
    assert engine.store._path(game.id).read_bytes()==saved


@pytest.mark.parametrize('years',[1,100,1000])
def test_warm_settlement_does_not_enumerate_catalog_or_elapsed_years(economy,years):
    _,game=economy;market=local_market(game)
    groups=basket_rules.purpose_index(market)
    with patch.object(basket_rules,'index',wraps=basket_rules.index) as indexing,\
         patch.object(basket_consumption,'purchase',wraps=basket_consumption.purchase) as buying:
        basket_consumption.settle(game,market,years)
    assert buying.call_count<=2*len(groups)<=192
    assert len(market['basket_credit'])<=96 and len(game.economy_v2['ledger'])<=80
    assert GameState.from_dict(game.to_dict())


def test_background_households_batch_five_years_while_orgs_settle_each_year(economy):
    engine,game=economy;market=local_market(game);start=game.player.age
    from cultivation_life.system.economy.state import settle_market
    with patch.object(basket_consumption,'settle',wraps=basket_consumption.settle) as baskets:
        for _ in range(4):
            game.player.age+=1;settle_market(game,market)
        assert baskets.call_count==0 and market['household_year']==start
        game.player.age+=1;settle_market(game,market)
        assert baskets.call_count==1 and baskets.call_args.args[2]==5
        assert market['household_year']==game.player.age
        organizations.advance_organizations(game,engine.maps)
        assert all(r['last_year']==game.player.age for r in game.economy_v2['organizations'].values())
        before=copy.deepcopy(game.to_dict());settle_market(game,market)
        assert game.to_dict()==before


@pytest.mark.parametrize('funds',[0,1,10,100,1000,10000])
def test_multi_input_background_batch_finds_maximum_from_real_cash(economy,funds):
    _,game=economy;market=local_market(game);source='background:human'
    item=product_id('human',2,'breakthrough');market['commodities'][item]['stock']=0
    required=inputs('human',2,'breakthrough')
    transfer_value(game,source,'world:human',balance(game,source)-funds,'限定原料资金')
    from cultivation_life.system.economy.basket_trade import quote
    desired=9
    expected=max([0]+[n for n in range(1,desired+1)
        if sum(quote(market['commodities'][k],'buy',n*q)['total'] for k,q in required.items())<=funds])
    before=cash(game);made,_=basket_production.produce(game,market,source,item,desired)
    assert made==expected and cash(game)==before


def test_standard_account_fast_transfer_keeps_ledgers_and_rejects_shadows(economy):
    _,game=economy;source='background:human';destination='world:human'
    before=copy.deepcopy(game.economy_v2['accounts']);money=cash(game)
    transfer_value(game,source,destination,17,'实际转账')
    after=game.economy_v2['accounts']
    assert after[source]['balance']==before[source]['balance']-17
    assert after[source]['expense']==before[source]['expense']+17
    assert after[destination]['balance']==before[destination]['balance']+17
    assert after[destination]['income']==before[destination]['income']+17
    assert game.economy_v2['ledger'][-1]['amount']==17 and cash(game)==money
    # An ordinary account named player must never mask the actual bag wallet.
    game.economy_v2['accounts']['player']=dict(balance=123,income=0,expense=0)
    transfer_value(game,source,'player',13,'真实玩家行囊')
    assert game.economy_v2['accounts']['player']['balance']==123


def test_high_realm_org_can_save_actual_profit_for_one_artifact(economy):
    engine,game=economy;entity=game.sects['tianjian']
    entity.world='spirit';entity.location_id=next(iter(engine.maps._locations['spirit']))
    npc=entity.npcs[0];npc.world='spirit';npc.realm_index=7;entity.npcs=[npc]
    row=organizations.register(game,'sect',entity.id,'spirit')
    row.update(workforce={'7':1},expected_upkeep=442)
    ensure_regional_market(game,engine.maps,'spirit',entity.location_id)
    market=game.economy_v2['markets'][f'spirit:{entity.location_id}']
    source=depot.treasury(game,entity)
    from cultivation_life.system.economy import organization_consumption
    real_purchase=organization_consumption.purchase
    bought=[]
    def production(*args,**kwargs):
        transfer_value(game,'background:spirit',source,120000,'已实收测试经营利润')
        return 120000
    def buying(*args,**kwargs):
        number,cost=real_purchase(*args,**kwargs)
        if number and basket_rules.purpose(args[3])=='artifact':bought.append((args[3],number,cost))
        return number,cost
    before=cash(game)
    with patch.object(organizations,'produce',side_effect=production),\
         patch.object(organization_consumption,'purchase',side_effect=buying),\
         patch('cultivation_life.system.economy.estate_management.invest_surplus'):
        # Small groups need to save through several intermittent supply bills.
        # Thirty real years is below one upper-realm action interval.
        for _ in range(30):
            game.player.age+=1
            row.update(income=0,expense=0,shortfall=0,produced=0,benefit_due=0,benefit_paid=0)
            organizations.settle_faction(game,engine.maps,row,1)
            row['last_year']=game.player.age
            assert row['supply_budget_credit']<=max(0,balance(game,source)-int(442*.65*3))
    assert bought and all(market['commodities'][i]['tier']==7 for i,n,c in bought)
    assert cash(game)==before


def test_purpose_index_recovers_from_replacement_at_same_catalog_size(economy):
    _,game=economy;market=local_market(game);group='longevity:4'
    item=basket_rules.purpose_candidates(market,group,limit=1)[0]
    market['commodities']['unknown-test-item']=market['commodities'].pop(item)
    assert item not in basket_rules.purpose_candidates(market,group)

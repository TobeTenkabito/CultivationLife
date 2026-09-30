import copy
import random

import pytest

from test_immortal_cultivation import prepared
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.system.yaochi_system import offers, config, commission_reward, lock_price


def pool(e, g):
    g.player.location_id=config()['location_id']
    g.yaochi_state['merit']=100000
    e.store.save(g)


def cabinet(g, office='sun', player=False):
    c=g.heavenly_court
    c['offices']={k:None for k in c['offices']}
    official=next(o for o in c['officials'].values() if o.get('source')=='court_pool')
    key='player' if player else official['id']
    c['offices'][office]=dict(holder_id=key,holder_name='试政星君',start_unit=0,end_unit=100,votes=20)
    c.update(unit=1,open_election=None)
    return key


def test_lock_freezes_goods_and_price_across_refresh_reload_and_purchase(prepared):
    e,g,_=prepared;pool(e,g)
    book=offers(g)[0];fee=lock_price(book)
    shown=e.yaochi_action(g.id,'lock',book['id'])
    assert shown['yaochi']['merit']==100000-fee
    for _ in range(3):
        g=e._load(g.id);g.player.age+=100;e.store.save(g)
        row=next(o for o in e.get_game(g.id)['yaochi']['shop'] if o['id']==book['id'])
        assert row['locked'] and row['price']==book['price']
        assert len([o for o in offers(g) if o['kind']=='doctrine'])==5
    with pytest.raises(ValueError,match='已经锁定'):e.yaochi_action(g.id,'lock',book['id'])
    e.yaochi_action(g.id,'buy',book['id']);saved=e._load(g.id)
    assert not saved.yaochi_state['locked_offers']
    assert saved.yaochi_state['merit']==100000-fee-book['price']


def test_lock_limits_no_charge_on_reject_and_unlock_no_refund(prepared):
    e,g,_=prepared;pool(e,g);books=offers(g)[:5]
    for b in books[:3]:e.yaochi_action(g.id,'lock',b['id'])
    balance=e._load(g.id).yaochi_state['merit']
    with pytest.raises(ValueError,match='名额'):e.yaochi_action(g.id,'lock',books[3]['id'])
    assert e._load(g.id).yaochi_state['merit']==balance
    e.yaochi_action(g.id,'unlock',books[0]['id'])
    assert e._load(g.id).yaochi_state['merit']==balance
    with pytest.raises(ValueError,match='常驻'):e.yaochi_action(g.id,'lock','great_sun_divine_light')
    with pytest.raises(ValueError):e.yaochi_action(g.id,'lock','not_a_book')


def test_old_jobs_orders_and_balances_keep_their_original_terms(prepared):
    e,g,_=prepared;pool(e,g)
    book=offers(g)[0]
    g.yaochi_state.update(job=dict(name='旧委托',years=100,progress=100,reward=77),
                         orders=[dict(id='old',offer=copy.deepcopy(book),price=19,ready_age=g.player.age)])
    e.store.save(g)
    e.yaochi_action(g.id,'claim_job');e.yaochi_action(g.id,'claim_order','old')
    assert e._load(g.id).yaochi_state['merit']==100077


def test_reward_and_price_progression_has_bounded_training_burdens(prepared):
    _,g,_=prepared;cfg=config()
    for realm,reward in zip(range(9,13),[400,1200,2400,4000]):
        g.player.realm_index=realm;g.player.layer=1
        assert commission_reward(g.player,cfg['commissions'][0])==reward
        g.player.layer=9
        assert commission_reward(g.player,cfg['commissions'][0])==round(reward*1.4)
    assert cfg['manual_prices'][0]/400==.5
    assert cfg['materials'][-1]['price']*40/4000==5
    assert cfg['merit_per_court_merit']>0 and cfg['stones_per_merit']<1000


def test_one_npc_can_legislate_and_issue_policy_once_per_unit(prepared):
    e,g,_=prepared;cabinet(g);rng=random.Random(4)
    before=g.heavenly_court['player_support']
    messages=e._court_govern(g,rng)
    c=g.heavenly_court
    assert len(messages)==2 and c['laws']['wide_domain']
    assert c['active_decrees'][0]['id']=='levy'
    assert c['last_vote']['total']==1 and c['last_vote']['passed']
    assert c['player_support']==before
    snapshot=copy.deepcopy(c);state=rng.getstate()
    assert e._court_govern(g,rng)==[] and c==snapshot and rng.getstate()==state
    e.store.save(g);loaded=e._load(g.id)
    assert e._court_govern(loaded,rng)==[]


def test_automatic_repeal_cooldown_and_player_abstention(prepared):
    e,g,_=prepared;key=cabinet(g,'mercury');c=g.heavenly_court
    c['laws'].update(traveling_palace=True,immortal_twofold=True,wide_domain=True)
    e._court_govern(g,random.Random(1))
    assert c['laws']['wide_domain'] is False
    cabinet(g,'sun');c['unit']=2
    e._court_govern(g,random.Random(1))
    assert c['laws']['wide_domain'] is False
    c['unit']=10;c['laws']['wide_domain']=False
    c['offices']['moon']=dict(holder_id='player',holder_name=g.player.name,start_unit=0,end_unit=100)
    c['pledges']=[dict(kind='law',id='wide_domain',deadline_unit=100)]
    _,_=e._court_vote_law(g,'wide_domain',True,random.Random(1),actor_id=key)
    assert c['last_vote']['abstain']==1 and not c['last_vote']['passed']
    assert len(c['pledges'])==1


def test_policy_costs_slots_expiry_and_no_player_resource_substitution(prepared):
    e,g,_=prepared;cabinet(g);c=g.heavenly_court
    c.update(treasury=0,authority=0)
    before=copy.deepcopy(g.player.inventory)
    assert e._court_govern(g,random.Random(1))==[]
    assert c['treasury']==0 and c['authority']==0 and g.player.inventory==before
    c.update(unit=2,treasury=10000,authority=100)
    c['active_decrees']=[dict(id='relief',name='赈济令',expires_unit=5)]
    e._court_govern(g,random.Random(1))
    assert len(c['active_decrees'])==1


def test_empty_or_player_only_cabinet_does_not_take_over_player(prepared):
    e,g,_=prepared;cabinet(g,player=True)
    assert e._court_govern(g,random.Random(1))==[]
    g.heavenly_court['unit']=2;g.heavenly_court['offices']['sun']=None
    assert e._court_govern(g,random.Random(1))==[]


def test_actual_unit_tick_runs_governance_but_reading_does_not(prepared):
    e,g,_=prepared;g.heavenly_court['player_grade']=9
    e._advance_heavenly_court_unit(g,random.Random(9))
    assert g.heavenly_court['governance_log']
    e.store.save(g);before=copy.deepcopy(g.heavenly_court)
    e.get_game(g.id);e.get_game(g.id)
    assert e._load(g.id).heavenly_court==before


def test_expired_and_dead_seats_are_retired(prepared):
    e,g,_=prepared;key=cabinet(g);c=g.heavenly_court
    c['offices']['sun']['end_unit']=0
    e._court_retire_unavailable(g)
    assert c['offices']['sun'] is None
    key=cabinet(g);c['officials'][key]['source']='npc'
    e._court_retire_unavailable(g)
    assert c['offices']['sun'] is None and key not in c['officials']

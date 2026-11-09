"""Adversarial original-state tests for the 1.1 adapters and base contracts."""
import copy,json
from unittest.mock import patch
import pytest
from test_immortal_cultivation import prepared
from test_yaochi_westward import pool
from test_earth_temple import village,build
from test_yaochi_fair import leased,cmd as garden_cmd
from test_westward_ventures import npc,seats,training_offer
from cultivation_life.models import GameState
from cultivation_life.rules import add_item
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.system import westward_management as management,westward_contracts as contracts,yaochi_garden as garden,yaochi_tenders as tenders,court_strategy
from cultivation_life.system.institution_ai import runtime,rules
from cultivation_life.system.economy.ledger import balance,transfer_value
from cultivation_life.system.economy.state import local_market
from cultivation_life.system.westward_finance import YAOCHI
from cultivation_life.person_assignments import research_assignment

def contract_cmd(e,gid,action,value=''):
    data=e.get_game(gid)['yaochi']['contracts']
    return e.yaochi_action(gid,action,data['token']+'|'+value)

def management_cmd(e,gid,action,**kw):
    row=e.get_game(gid)['yaochi']['management'][0]
    return e.yaochi_action(gid,'management',json.dumps(dict(action=action,scope=row['id'],token=row['token'],**kw)))

def test_contract_real_escrow_three_deliveries_and_no_replay(pool):
    e,gid=pool;leased(e,gid);g=e._load(gid);before=balance(g,YAOCHI)
    contract_cmd(e,gid,'contract_open','garden');g=e._load(gid);r=contracts.current(g)
    assert balance(g,YAOCHI)==before-r['funded']
    with pytest.raises(ValueError):contract_cmd(e,gid,'contract_deliver')
    for i in range(3):
        g=e._load(gid);r=contracts.current(g);g.player.age=r['next']
        # Isolated fixture goods; actual command must remove these original estate units.
        garden.estate(g)['stock'][r['item']]=r['quantity'];e.store.save(g)
        g=e._load(gid);r=contracts.current(g);stock=local_market(g)['commodities'][r['item']]['stock'];item=r['item'];quantity=r['quantity']
        old=contracts.token(g);contract_cmd(e,gid,'contract_deliver');g=e._load(gid)
        assert local_market(g)['commodities'][item]['stock']==stock+quantity and not garden.estate(g)['stock']
        saved=e.store._path(gid).read_bytes()
        with pytest.raises(ValueError):e.yaochi_action(gid,'contract_deliver',old+'|')
        assert e.store._path(gid).read_bytes()==saved
    r=contracts.state(g)['history'][-1];assert r['paid']==r['funded'] and balance(g,r['wallet'])==0
    assert GameState.from_dict(g.to_dict()).economy_v2==g.economy_v2

@pytest.mark.parametrize('cause',['missing','expired','ruin','disabled','foreign'])
def test_contract_failure_preserves_original_accounts_and_goods(pool,cause):
    e,gid=pool;leased(e,gid);contract_cmd(e,gid,'contract_open','garden');g=e._load(gid);r=contracts.current(g)
    g.player.age=r['next'];garden.estate(g)['stock'][r['item']]=r['quantity']
    if cause=='missing':garden.estate(g)['stock'].clear()
    elif cause=='expired':g.player.age=garden.lease(g)['until']
    elif cause=='ruin':garden.estate(g).update(building_status='destroyed',building_destroyed_age=g.player.age,enabled=False,entrusted=False,auto_buy=False,auto_sell=False)
    elif cause=='foreign':g.player.location_id='jade_capital'
    before=copy.deepcopy(g.to_dict())
    with patch.dict(WORLD_SYSTEMS['yaochi_westward'],enabled=cause!='disabled'):
        with pytest.raises(ValueError):contracts.command(g,'contract_deliver',contracts.token(g)+'|')
    assert g.to_dict()==before

def test_cancel_refunds_only_remaining_and_cannot_reopen_same_window(pool):
    e,gid=pool;leased(e,gid);contract_cmd(e,gid,'contract_open','garden');g=e._load(gid);r=copy.deepcopy(contracts.current(g));cash=balance(g,YAOCHI)
    contract_cmd(e,gid,'contract_cancel');g=e._load(gid)
    assert balance(g,YAOCHI)==cash+r['funded'] and balance(g,r['wallet'])==0
    with pytest.raises(ValueError):contract_cmd(e,gid,'contract_cancel')
    with pytest.raises(ValueError,match='额度'):contract_cmd(e,gid,'contract_open','garden')

def test_temple_actual_person_budget_pause_refund_and_disabled_recovery(village):
    e,gid=village;build(e,gid);n=npc(e,gid);g=e._load(gid);scope=management.scopes(g,e.maps)[0]
    offer=management.offers(g,e.maps,scope)[0]
    management_cmd(e,gid,'institution_start',offer=offer['key'],person=n);g=e._load(gid)
    job=rules.record(g,scope['id'])['job'];assert research_assignment(g,n)['id']==job['id']
    # Execution uses the original local NPC; the player stays unchanged.
    address=(g.player.world,g.player.location_id);g.player.age+=1;management.advance(g,e.maps)
    assert job['progress']==1 and (g.player.world,g.player.location_id)==address
    g.world_npcs[n].location_id='jade_capital';cash=balance(g,job['wallet']);g.player.age+=1;management.advance(g,e.maps)
    assert job['progress']==1 and job['blocked'] and balance(g,job['wallet'])==cash
    e.store.save(g)
    with patch.dict(WORLD_SYSTEMS['yaochi_westward'],enabled=False):management_cmd(e,gid,'institution_cancel')
    g=e._load(gid);receipt=rules.record(g,scope['id'])['history'][-1]
    assert receipt['funded']==receipt['spent']+receipt['refunded'] and not research_assignment(g,n)

def test_temple_complete_consumes_real_market_goods_once(village):
    e,gid=village;build(e,gid);n=npc(e,gid);g=e._load(gid);scope=management.scopes(g,e.maps)[0];offer=management.offers(g,e.maps,scope)[0]
    job=runtime.start(g,scope,offer,n,adapter=management);market=local_market(g);stock={k:market['commodities'][k]['stock'] for k in offer['materials']}
    from cultivation_life.system.earth_temple_rules import state
    for _ in range(job['years']):g.player.age+=1;management.advance(g,e.maps)
    assert not rules.record(g,scope['id']).get('job') and state(g)['allowance']==400
    from cultivation_life.system.economy.market_power import normalize
    for key,num in offer['materials'].items():
        assert market['commodities'][key]['stock']==stock[key]-num
        buyers=market['competition'][key]['buyers']
        assert normalize(g,job['source']) in buyers and job['wallet'] not in buyers
    saved=copy.deepcopy(g.to_dict());management.advance(g,e.maps);assert g.to_dict()==saved

def test_npc_tender_real_funds_original_person_and_expiry_releases(pool):
    e,gid=pool;leased(e,gid);garden_cmd(e,gid,'garden_close');g=e._load(gid)
    from cultivation_life.system.economy.organizations import register
    org=next(s for s in g.sects.values() if s.world=='celestial' and s.kind=='sect' and not s.extinct)
    n=org.npcs[0];n.world='celestial';n.location_id=g.player.location_id;n.realm_index=12;n.layer=1
    row=register(g,'sect',org.id,'celestial');row['expected_upkeep']=0;source='organization:sect:'+org.id
    transfer_value(g,'background:celestial',source,10**12,'隔离验收机构原款')
    e.store.save(g);g=e._load(gid);ranked=tenders.bids(g);assert ranked[0]['id']==n.id
    before=balance(g,source);player=balance(g,'player');garden_cmd(e,gid,'garden_lease');g=e._load(gid);l=garden.lease(g)
    assert l['operator']==n.id and balance(g,'player')==player and balance(g,source)<before
    assert research_assignment(g,n.id)['id']==garden.identity()
    assert e.get_game(gid)['yaochi']['garden']['estate'] is None
    assert GameState.from_dict(g.to_dict()).economy_v2==g.economy_v2
    # An original paid batch or ruined estate cannot trap an expired operator.
    g.player.age=l['until'];row=garden.estate(g);row['arrears']=balance(g,l['wallet'])+100
    tenders.advance(g,e.maps);assert not garden.lease(g) and not research_assignment(g,n.id)
    assert row['arrears']==0 and balance(g,l['wallet'])==balance(g,l['deposit_wallet'])==0

def test_fair_credentials_one_use_and_original_lifetime(pool):
    e,gid=pool;g=e._load(gid)
    from cultivation_life.system.westward_fair_benefits import credential,consume
    fair=g.yaochi_state.setdefault('westward',{}).setdefault('fair',{})
    fair['entries']=[dict(id='proof',kind='supply',status='won',cycle=g.player.age//500)]
    assert credential(g,'supply');consume(g,'proof','长期供货扩额');assert not credential(g,'supply')
    with pytest.raises(ValueError):consume(g,'proof','再次扩额')

def test_court_real_npc_proposal_readonly_budget_and_no_duplicate_year(pool):
    e,gid=pool;g=e._load(gid);g.player.location_id='jade_capital';e.store.save(g);e.get_game(gid)
    seats(e,gid);training_offer(e,gid);g=e._load(gid);who='public-scholar'
    g.heavenly_court['officials'][who]=dict(id=who,name=g.world_npcs[who].name,source='npc',grade=2)
    before=copy.deepcopy(g.to_dict());court_strategy.public(g);assert g.to_dict()==before
    from cultivation_life.regional_context import CalendarGame
    court_strategy.advance(CalendarGame(g,'celestial',g.player.age-1),e.maps);assert not court_strategy.state(g).get('npc_proposals')
    court_strategy.advance(CalendarGame(g,'celestial',g.player.age),e.maps);assert court_strategy.state(g)['npc_proposals']
    saved=copy.deepcopy(g.to_dict());court_strategy.advance(g,e.maps);assert g.to_dict()==saved
    assert 1<=len(court_strategy.state(g)['npc_proposals'])<=3
    assert all(g.heavenly_court['officials'][p['person']]['source']=='npc' for p in court_strategy.state(g)['npc_proposals'])

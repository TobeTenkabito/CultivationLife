"""Real transfers, finite physical supply, ownership, visibility and command paths."""
import copy
import random
from pathlib import Path
from unittest.mock import Mock

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.system.economy import depot, organizations
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.economy.state import ensure_regional_market
from cultivation_life.system.faction_geography import faction_site
from cultivation_life.system.war import logistics, supply

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    engine=GameEngine(ROOT,tmp_path)
    game=engine._load(engine.create_game('军需验收','supreme_metal','dao',7701,preset_id='nascent')['id'])
    game.pending_event=None
    game.player.faction_id='tianjian'
    for identity in ('tianjian','wanmo'):
        entity=game.sects[identity]
        organizations.register(game,'sect',identity,entity.world)
        transfer_value(game,'background:human',depot.treasury(game,entity),100000,'验收实际拨款')
    return engine,game


def cash(game):
    return sum(r['balance'] for r in game.economy_v2['accounts'].values())+sum(r.get('resources',0) for r in game.intrigue_state['factions'].values())


def war(setup):
    engine,game=setup
    return engine._start_war(game,'sect','tianjian','wanmo',initiated_by_player=True)


def test_purchase_consumption_and_raid_conserve_actual_items(setup):
    engine,game=setup
    for entity in [game.sects[k] for k in ('tianjian','wanmo')]:
        ensure_regional_market(game,engine.maps,entity.world,entity.location_id)
    before=cash(game)
    w=war(setup)
    assert cash(game)==before
    assert any(r['items'] for r in w['logistics']['sides'].values())
    markets=copy.deepcopy(game.economy_v2['markets'])
    row=w['logistics']['sides']['attacker'];quantities=dict(row['items'])
    supply.consume(game,w,'attacker',logistics.need(game,w,'attacker'),'测试消耗')
    assert game.economy_v2['markets']==markets  # Consumption returns no goods or money.
    assert sum(row['items'].values())<sum(quantities.values())
    beforeitems={k:sum(r['items'].get(k,0) for r in w['logistics']['sides'].values()) for k in set().union(*(r['items'] for r in w['logistics']['sides'].values()))}
    supply.raid(game,w,'attacker',logistics.need(game,w,'attacker'))
    assert all(sum(r['items'].get(k,0) for r in w['logistics']['sides'].values())<=n for k,n in beforeitems.items())
    assert cash(game)==before
    assert GameState.from_dict(game.to_dict()).economy_v2==game.economy_v2


def test_intelligence_read_only_and_snapshot_not_live(setup):
    engine,game=setup;w=war(setup)
    before=copy.deepcopy(game.to_dict())
    view=logistics.public(game,w,'attacker')
    assert view['attacker']['known'] and not view['defender']['known']
    assert view['defender']['balance'] is None and not view['defender']['items']
    assert game.to_dict()==before
    logistics.strategy(game,engine.maps,w,'attacker','scout',Mock(random=lambda:0))
    snapshot=logistics.public(game,w,'attacker')['defender']['snapshot']
    supply.consume(game,w,'defender',1000,'消耗')
    assert logistics.public(game,w,'attacker')['defender']['snapshot']==snapshot
    assert all(r['known'] for r in logistics.public(game,w,None).values())
    with pytest.raises(ValueError,match='本轮'):logistics.strategy(game,engine.maps,w,'attacker','scout',random.Random(1))


def test_no_funds_no_supply_severe_penalty_and_no_attacking_preference(setup):
    engine,game=setup
    for e in [game.sects[k] for k in ('tianjian','wanmo')]:
        transfer_value(game,depot.treasury(game,e),'background:human',balance(game,depot.treasury(game,e)),'清空验收预算')
    assert not logistics.ready_to_attack(game,'sect','tianjian','human')
    w=war(setup);logistics.begin_round(game,engine.maps,w,random.Random(1))
    assert logistics.factor(w,'attacker')==.25 and w['morale']['attacker']==75
    assert not supply.total(game,w,'attacker')


def test_depot_request_waits_approval_escrows_and_collects_once(setup):
    engine,game=setup;e=game.sects['tianjian'];game.player.location_id=faction_site(e)['id']
    row=depot.ensure(game,e)
    key=next(k for k,v in depot.catalog('human').items() if v['kind']=='item' and v['tier']==1)
    depot.purchase(game,engine.maps,e,key,3)
    engine.store.save(game)
    def command(action,**kwargs):
        g=engine._load(game.id);revision=depot.find(g,g.sects[e.id])['revision']
        return engine.fleet_action(game.id,dict(action=action,owner_id=e.id,revision=revision,**kwargs))
    command('depot_request',item=key,quantity=1)
    g=engine._load(game.id);request=depot.find(g,g.sects[e.id])['requests'][0];senior=depot.seniors(g,g.sects[e.id])[0]
    senior.affinity=100;engine.store.save(g)
    before=engine.store.load(game.id).to_dict()
    with pytest.raises(ValueError,match='行动单位'):command('depot_review',request_id=request['id'],approver_id=senior.id)
    assert engine.store.load(game.id).to_dict()==before
    g=engine._load(game.id);g.diplomacy_unit+=1;engine.store.save(g)
    command('depot_review',request_id=request['id'],approver_id=senior.id)
    g=engine._load(game.id);r=depot.find(g,g.sects[e.id]);assert r['stock'][key]==2 and r['requests'][0]['reserved']==1
    command('depot_collect',request_id=request['id'])
    before=engine.store.load(game.id).to_dict()
    with pytest.raises(ValueError,match='不能重复'):command('depot_collect',request_id=request['id'])
    assert engine.store.load(game.id).to_dict()==before


@pytest.mark.parametrize('damage',['negative','unknown_world','escrow','coverage'])
def test_corrupt_save_rejected_without_mutation(setup,damage):
    _,game=setup;w=war(setup);r=depot.ensure(game,game.sects['tianjian']);raw=game.to_dict()
    if damage=='negative':raw['wars'][-1]['logistics']['sides']['attacker']['items']['bad']=-1
    elif damage=='unknown_world':raw['wars'][-1]['logistics']['sides']['attacker']['world']='void'
    elif damage=='coverage':raw['wars'][-1]['logistics']['sides']['attacker']['coverage']=float('nan')
    else:next(iter(raw['economy_v2']['depots'].values()))['stock']['item:bad']=10001
    before=copy.deepcopy(raw)
    with pytest.raises(ValueError,match='经济存档'):GameState.from_dict(raw)
    assert raw==before


def test_coalition_redistributes_unfunded_share_and_keeps_pool_address(setup):
    engine,game=setup;w=war(setup)
    w['coalitions']['attacker']=[{'id':'tianjian'},{'id':'wanmo'}]
    poor=game.sects['tianjian'];rich=game.sects['wanmo']
    transfer_value(game,depot.treasury(game,poor),'background:human',balance(game,depot.treasury(game,poor)),'无力承担')
    row=w['logistics']['sides']['attacker'];address=(row['world'],row['location'])
    old=row['contributions'].get(rich.id,0)
    assert logistics.replenish(game,engine.maps,w,'attacker',5000)==5000
    assert row['contributions'][rich.id]-old==5000
    # A different nearest headquarters does not relocate existing inventory.
    from unittest.mock import patch
    with patch.object(logistics,'front',return_value=('human',rich.location_id,5)):
        logistics.replenish(game,engine.maps,w,'attacker',0)
    assert (row['world'],row['location'])==address


def test_expedition_real_purchase_front_attribution_gate_cost_and_refund(setup):
    from cultivation_life.system.economy import campaign_finance as finance
    engine,game=setup;entity=game.sects['tianjian']
    ensure_regional_market(game,engine.maps,'human',entity.location_id)
    market=game.economy_v2['markets'][f'human:{entity.location_id}']
    beforecash=cash(game);stock=sum(v['stock'] for v in market['commodities'].values())
    assert finance.prepare(game,engine.maps,'lanjiang_gate','attacker',entity.id,'human',entity.location_id,10000,quantity=5)
    assert sum(v['stock'] for v in market['commodities'].values())==stock-5
    assert cash(game)==beforecash
    target=next(r['id'] for r in engine.maps.worlds['human']['locations'] if r['id']!=entity.location_id)
    ensure_regional_market(game,engine.maps,'human',target)
    front=game.economy_v2['markets'][f'human:{target}'];old=market.get('war_income',0)
    assert finance.settle(game,engine.maps,'lanjiang_gate','attacker',2000,'human',target,portal_scale=2)==1
    book=game.economy_v2['campaigns']['campaign:lanjiang_gate:attacker']
    assert book['extra']==2200 and 0<front['war_income']<=420
    assert market['war_income']==old and cash(game)==beforecash
    assert balance(game,'campaign:lanjiang_gate:attacker')==5800
    for product in front['commodities'].values():product['stock']=0
    old=front['war_income']
    finance.settle(game,engine.maps,'lanjiang_gate','attacker',2200,'human',target,portal_scale=2,finished=True)
    assert front['war_income']==old and book['extra']==2400
    assert not balance(game,'campaign:lanjiang_gate:attacker') and book['refunded']
    assert cash(game)==beforecash
    assert GameState.from_dict(game.to_dict()).economy_v2==game.economy_v2

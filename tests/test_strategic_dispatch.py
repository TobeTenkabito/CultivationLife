"""Real command transactions and bounded multi-organization deployments."""
import copy
import random
from unittest.mock import patch

import pytest

from test_strategic_war import engine, scenario, api, snapshot
from cultivation_life.engine.composition.strategic_war import bind
from cultivation_life.models import GameState
from cultivation_life.system.strategic_war import lifecycle, dispatch
from cultivation_life.system.strategic_war.presentation import public
from cultivation_life.system.war.occupancy import busy
from cultivation_life.system.war import logistics, requirements
from cultivation_life.system.economy import depot
from cultivation_life.system.economy.ledger import balance


def reserve_game(engine):
    g,row=scenario(engine)
    g.player.faction_id='taixuan';g.sects['taixuan'].founded_by_player=True
    lifecycle.commit(bind(engine),g,row,g.sects['taixuan'])
    row['commanders']['attacker']=dict(person_id='player',name=g.player.name,expires=g.player.age+100,votes=3,electorate=3)
    g.player.age+=1;lifecycle.advance(bind(engine),g,random.Random(641))
    reasons=[]
    for org in g.sects.values():
        if org.world!=row['world'] or org.allegiance_race!=row['attacker'] or busy(g,org):continue
        for child in g.wars:
            if child.get('strategic_war_id')!=row['id'] or child['location_id']==org.location_id:continue
            try:dispatch.plan(bind(engine),g,row,child,org)
            except ValueError as error:reasons.append((org.id,str(error)));continue
            return g,row,child,org
    raise AssertionError(reasons)


def command(row,child,org,cost,seq=1):
    return dict(action='dispatch',war_id=row['id'],campaign_id=child['id'],org_id=org.id,org_kind=org.kind,
                expected_cost=cost,expected_revision=row['revision'],command_seq=seq,command_id=f'dispatch-{seq}')


def test_real_dispatch_requires_commander_current_quote_and_idle_whole_org(api):
    e,post=api;g,row,child,org=reserve_game(e);e.store.save(g)
    shown=e.get_game(g.id)['war_system']['strategic']['wars'][0]
    choice=next(o for c in shown['campaigns'] if c['id']==child['id'] for o in c['dispatch_choices'] if o['id']==org.id)
    data=command(row,child,org,choice['cost'])
    before=snapshot(e,g.id)
    post(g.id,'strategic-war',status=400,**{**data,'expected_cost':choice['cost']+1})
    assert e.store._path(g.id).read_bytes()==before
    post(g.id,'strategic-war',**data)
    saved=e._load(g.id);original=next(w for w in saved.wars if w['id']==child['id'])
    assert org.id in {r['id'] for r in original['coalitions']['attacker']}
    assert original['reinforcements'][-1]['paid']==choice['cost']
    before=snapshot(e,g.id)
    post(g.id,'strategic-war',status=400,**data)
    assert e.store._path(g.id).read_bytes()==before
    other=next(w for w in saved.wars if w.get('strategic_war_id')==row['id'] and w['id']!=child['id'])
    row=saved.strategic_war_state['wars'][0]
    post(g.id,'strategic-war',status=400,**command(row,other,org,choice['cost'],2))
    assert e.store._path(g.id).read_bytes()==before
    # Actual authority revocation is checked even with a fresh revision.
    saved.player.faction_id=None;e.store.save(saved);before=snapshot(e,g.id)
    post(g.id,'strategic-war',status=400,**command(row,other,org,choice['cost'],2))
    assert e.store._path(g.id).read_bytes()==before


@pytest.mark.parametrize('phase',['marching','engaged','returning'])
def test_busy_even_with_spare_members_or_finished_battle(engine,phase):
    g,row,c,org=reserve_game(engine)
    source=next(w for w in g.wars if w.get('strategic_war_id')==row['id'] and w['id']!=c['id'])
    occupied=g.sects[source['attacker_id']]
    source['campaign_phase']=phase
    if phase=='returning':source['status']='withdrawing'
    source['roster']['attacker']=source['roster']['attacker'][:1]
    before=copy.deepcopy(g.to_dict())
    with pytest.raises(ValueError,match='闲置'):
        dispatch.send(bind(engine),g,row,c,occupied)
    assert g.to_dict()==before


def test_multi_vs_multi_uses_original_people_and_no_money_or_power_before_arrival(engine):
    g,row,c,org=reserve_game(engine);deps=bind(engine)
    # An isolated engaged-front fixture; existing people already occupy their
    # recorded destination. This is not a runtime transport entry.
    for rows in c['journeys'].values():
        for j in rows:
            j.update(remaining=0,phase='stationed');deps.find_person(g,j['person_id']).location_id=c['location_id']
    for cargo in c['cargo_journeys'].values():cargo.update(remaining=0,phase='stationed')
    c['campaign_phase']='engaged'
    if len(c['coalitions']['defender'])<2:
        from cultivation_life.system.strategic_war.materialization import materialize
        defender=materialize(deps,g,row['world'],row['defender'],random.Random(18))
        lifecycle.commit(deps,g,row,defender)
        dispatch.send(deps,g,row,c,defender)
    existing=[n.id for n in deps.members(g,org)]
    cash_before=balance(g,depot.treasury(g,org));front_before=balance(g,logistics.wallet(c,'attacker'))
    due=c['next_battle_age'];cost=dispatch.send(deps,g,row,c,org)
    r=c['reinforcements'][-1]
    assert balance(g,depot.treasury(g,org))==cash_before-cost
    assert balance(g,r['wallet'])==cost
    assert balance(g,logistics.wallet(c,'attacker'))==front_before
    assert c['next_battle_age']==due
    assert len(c['coalitions']['attacker'])>=2 and len(c['coalitions']['defender'])>=2
    assert set(existing).intersection(c['roster']['attacker'])
    assert not set(existing).intersection(n.id for n in engine._available_warriors(g,c,'attacker'))
    assert lifecycle._journey(deps,g,c)  # New, distant reserves do not freeze the existing front.
    assert balance(g,r['wallet'])==cost
    # A save/load retains the same original identities, escrow and route.
    restored=GameState.from_dict(g.to_dict())
    assert next(w for w in restored.wars if w['id']==c['id'])['reinforcements']==c['reinforcements']
    for _ in range(max(r['cargo']['years'],max(j['years'] for j in c['journeys']['attacker']))+1):
        g.player.age+=1;lifecycle._journey(deps,g,c)
    assert r['delivered'] and balance(g,r['wallet'])==0
    assert balance(g,logistics.wallet(c,'attacker'))==front_before+cost
    assert set(existing).intersection(n.id for n in engine._available_warriors(g,c,'attacker'))
    before=copy.deepcopy(g.to_dict());lifecycle._journey(deps,g,c)
    assert g.to_dict()==before


def test_unarrived_cash_returns_only_after_actual_return_once(engine):
    g,row,c,org=reserve_game(engine);deps=bind(engine)
    opening=balance(g,depot.treasury(g,org));cost=dispatch.send(deps,g,row,c,org)
    r=c['reinforcements'][-1]
    assert r['cargo']['years']>2
    for _ in range(2):g.player.age+=1;lifecycle._journey(deps,g,c)
    lifecycle.withdraw(g,c)
    assert r['cargo']['remaining']==2
    assert balance(g,depot.treasury(g,org))==opening-cost
    g.player.age+=1;lifecycle._journey(deps,g,c)
    assert balance(g,depot.treasury(g,org))==opening-cost
    g.player.age+=1;lifecycle._journey(deps,g,c)
    assert balance(g,depot.treasury(g,org))==opening and r['refunded'] and not r['delivered']
    before=balance(g,logistics.wallet(c,'attacker'))
    for _ in range(3):g.player.age+=1;lifecycle._journey(deps,g,c)
    assert balance(g,depot.treasury(g,org))==opening
    assert balance(g,logistics.wallet(c,'attacker'))==before


def test_original_org_recall_does_not_withdraw_allies_or_allow_transfer(engine):
    g,row,c,org=reserve_game(engine);deps=bind(engine)
    dispatch.send(deps,g,row,c,org)
    leader=g.sects[c['attacker_id']]
    dispatch.recall(g,c,leader)
    assert c['status']=='active' and c['campaign_phase']!='returning'
    assert all(j['phase']=='returning' for j in c['journeys']['attacker'] if c['roster_owner'][j['person_id']]==leader.id)
    assert all(j['phase'] in {'outbound','stationed'} for j in c['journeys']['attacker'] if c['roster_owner'][j['person_id']]==org.id)
    assert busy(g,leader) and busy(g,org)
    with pytest.raises(ValueError,match='重复'):
        dispatch.recall(g,c,leader)
    assert dispatch.recall(g,c,org)
    lifecycle.receipt(g,row,c)
    assert c['status']=='withdrawing'


def test_ordinary_campaign_entry_cannot_steal_strategic_ally(engine):
    g,row,c,org=reserve_game(engine);dispatch.send(bind(engine),g,row,c,org)
    other=next(o for o in g.sects.values() if o.world=='spirit' and o.id not in {c['attacker_id'],c['defender_id'],org.id})
    before=copy.deepcopy(g.to_dict())
    with pytest.raises(ValueError,match='战略战役'):
        engine._start_war(g,'sect',org.id,other.id,initiated_by_player=True)
    assert g.to_dict()==before


def test_npc_dispatch_is_bounded_and_respects_player_mandate(engine):
    g,row,c,org=reserve_game(engine)
    assert not busy(g,org)  # Player commander keeps manual control of reserves.
    assert any(w.get('reinforcements') for w in g.wars)  # Opposing NPC commander actually sends reserves.
    row['commanders']['attacker']=dict(person_id=row['commitments'][0]['representative'],expires=g.player.age+100)
    row.get('dispatch_ages',{}).pop('attacker',None)
    dispatch.auto_dispatch(bind(engine),g,row)
    assert busy(g,org)
    before=copy.deepcopy(g.to_dict());dispatch.auto_dispatch(bind(engine),g,row)
    assert g.to_dict()==before


def test_funds_and_capacity_rejections_are_readonly(engine):
    g,row,c,org=reserve_game(engine)
    for commitment in row['commitments']:
        if commitment['org']['id']==org.id:commitment['budget']=0
    before=copy.deepcopy(g.to_dict())
    with pytest.raises(ValueError,match='军费'):
        dispatch.send(bind(engine),g,row,c,org)
    assert g.to_dict()==before
    c['roster']['attacker']=['capacity']*48
    with pytest.raises(ValueError,match='名册已满'):
        dispatch.plan(bind(engine),g,row,c,org)


def test_commander_projection_is_readonly_and_hides_transports(engine):
    g,row,c,org=reserve_game(engine);before=copy.deepcopy(g.to_dict())
    projection=public(bind(engine),g)
    assert g.to_dict()==before
    import json
    assert 'wallet' not in json.dumps(projection) and 'person_id' not in json.dumps(projection)
    assert any(o['id']==org.id for w in projection['wars'] for c in w['campaigns'] for o in c['dispatch_choices'])


def test_corrupt_duplicate_escrow_cannot_load(engine):
    g,row,c,org=reserve_game(engine);dispatch.send(bind(engine),g,row,c,org)
    c['reinforcements'].append(copy.deepcopy(c['reinforcements'][-1]))
    with pytest.raises(ValueError,match='增援'):
        g.to_dict()


def test_defeated_org_only_rejoins_after_full_return_and_with_remaining_budget(engine):
    g,row,child,_=reserve_game(engine);deps=bind(engine)
    org=g.sects[child['defender_id']]
    commitment=next(c for c in row['commitments'] if c['org']['id']==org.id)
    other=next(w for w in g.wars if w.get('strategic_war_id')==row['id'] and w['id']!=child['id'])
    other['next_battle_age']=g.player.age+10000;row['deadline_age']=g.player.age+10000
    child.update(status='peace_ready',winner='attacker')
    lifecycle.receipt(g,row,child)
    score=row['score']
    with pytest.raises(ValueError,match='闲置'):
        dispatch.plan(deps,g,row,other,org)
    with patch.object(dispatch,'auto_dispatch'):
        for _ in range(3000):
            if child['status']=='ended':break
            g.player.age+=1;lifecycle.advance(deps,g,random.Random(51))
    assert child['status']=='ended' and child['logistics']['refunded'] and not busy(g,org)
    before_budget=dispatch.remaining_budget(g,row,commitment)
    cost=dispatch.send(deps,g,row,other,org)
    assert 0<cost<=before_budget<=commitment['budget']
    assert dispatch.remaining_budget(g,row,commitment)==before_budget-cost
    assert row['score']==score and len(row['campaigns'])==2  # Historical objective never reopens.


def test_tail_reinforcement_actually_attacks_and_org_hold_does_not_hold_allies(engine):
    g,row,c,org=reserve_game(engine);deps=bind(engine)
    dispatch.send(deps,g,row,c,org)
    for rows in c['journeys'].values():
        for j in rows:
            j.update(remaining=0,phase='stationed');deps.find_person(g,j['person_id']).location_id=c['location_id']
    c['campaign_phase']='engaged'
    c['org_stances']={c['attacker_id']:'hold'}
    from cultivation_life.system.war import combat
    seen=[]
    def resolution(attackers,defenders,*args,**kwargs):
        seen.extend(n.id for n,power in attackers)
        return None
    with patch.object(combat,'resolve_npc_engagement',side_effect=resolution):
        engine._resolve_field_attack(g,c,'attacker',random.Random(9))
    assert seen and all(c['roster_owner'][n]==org.id for n in seen)


def test_unreachable_route_rejects_before_any_asset_or_identity_change(engine):
    from types import SimpleNamespace
    g,row,c,org=reserve_game(engine);deps=bind(engine)
    before=copy.deepcopy(g.to_dict())
    with patch.object(deps.maps,'travel_plan',return_value=SimpleNamespace(status='blocked')):
        with pytest.raises(ValueError,match='道路'):
            dispatch.send(deps,g,row,c,org)
    assert g.to_dict()==before


def test_same_site_reserve_can_join_without_calling_travel_to_self(engine):
    g,row,c,org=reserve_game(engine);deps=bind(engine)
    # Initial-placement fixture for an idle organization already at this front.
    org.location_id=c['location_id']
    for n in org.npcs:n.location_id=c['location_id']
    with patch.object(deps.maps,'travel_plan',side_effect=AssertionError('Self-travel must not be requested')):
        dispatch.send(deps,g,row,c,org)
    r=c['reinforcements'][-1]
    assert r['cargo']['years']==0
    lifecycle._journey(deps,g,c)
    assert r['delivered'] and balance(g,r['wallet'])==0

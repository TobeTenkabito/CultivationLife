"""Release audit: live mandates, physical custody and conserved settlements."""
import copy
import random

import pytest

from test_strategic_war import engine, api, own_campaign, snapshot
from test_strategic_dispatch import reserve_game
from cultivation_life.engine.composition.strategic_war import bind
from cultivation_life.system.strategic_war import lifecycle, dispatch, politics
from cultivation_life.system.strategic_war.presentation import public
from cultivation_life.system.economy import depot
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.war import logistics


def test_release_fixture_drives_original_public_dispatch_and_recall(engine):
    import runpy
    from pathlib import Path
    fixture=runpy.run_path(str(Path(__file__).parent/'fixtures/strategic_war_release.py'))
    made=engine.create_game('成品夹具验收','supreme_metal','dao',641,
                           custom_start=dict(world='spirit',realm_index=8,layer=1))
    fixture['prepare_strategic_release'](engine,made['id'])
    state=engine.get_game(made['id'])['war_system']['strategic'];row=state['wars'][0]
    child=next(c for c in row['campaigns'] if c['org'] and c['org']['id']=='taixuan' and c['dispatch_choices'])
    choice=child['dispatch_choices'][0]
    result=engine.strategic_war_action(made['id'],dict(action='dispatch',war_id=row['id'],campaign_id=child['id'],
        org_id=choice['id'],org_kind=choice['kind'],expected_cost=choice['cost'],expected_revision=row['revision'],
        command_id='release-fixture-dispatch',command_seq=state['command_seq']))
    fixture['inspect_strategic_release'](engine,made['id'])
    state=result['war_system']['strategic'];row=state['wars'][0]
    engine.strategic_war_action(made['id'],dict(action='withdraw',war_id=row['id'],campaign_id=child['id'],
        org_id='taixuan',org_kind='sect',expected_revision=row['revision'],command_id='release-fixture-recall',
        command_seq=state['command_seq']))
    fixture['inspect_strategic_release'](engine,made['id'])


def test_changed_political_support_revokes_commander_before_any_action(api):
    e,post=api;g,row,c,org=reserve_game(e)
    g.sects['taixuan'].allegiance_race=row['defender']
    e.store.save(g)
    assert not politics.player_commander(bind(e),g,row)
    shown=public(bind(e),g)['wars'][0]
    assert not shown['player_commander'] and not any(c['dispatch_choices'] for c in shown['campaigns'])
    before=snapshot(e,g.id)
    post(g.id,'strategic-war',status=400,action='stance',stance='advance',war_id=row['id'],
         expected_revision=row['revision'],command_id='revoked-political-mandate',command_seq=1)
    assert e.store._path(g.id).read_bytes()==before
    lifecycle._elect(bind(e),g,row)
    assert row['commanders'].get('attacker',{}).get('person_id')!='player'


def test_departed_representative_cannot_vote_for_old_organization(engine):
    g,row,c,org=reserve_game(engine);deps=bind(engine)
    commitment=next(c for c in row['commitments'] if c['side']=='defender')
    person=deps.find_person(g,commitment['representative'])
    for group in g.sects.values():group.npcs[:]=[n for n in group.npcs if n.id!=person.id]
    g.world_npcs[person.id]=person;person.faction_id=None
    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(row,'commitments',[commitment])
        assert politics.opposing_reply(deps,g,row,'defender',True)['total']==0


def test_imprisoned_marching_person_never_moves_or_rejoins_front(engine):
    g,row,c,org=reserve_game(engine);deps=bind(engine)
    j=next(j for rows in c['journeys'].values() for j in rows if j['phase']=='outbound')
    n=deps.find_person(g,j['person_id']);origin=n.location_id
    g.intrigue_state.setdefault('npc_prisons',{})[n.id]=dict(years_remaining=10)
    assert deps.imprisoned(g,n.id)
    j['remaining']=1;g.player.age+=1;lifecycle._journey(deps,g,c)
    assert n.location_id==origin and j['phase']=='lost'


def test_refund_rounding_only_pays_real_contributors(engine):
    g,row,c,reserve=reserve_game(engine)
    others=[o for o in g.sects.values() if o.world==row['world'] and o.id not in {c['attacker_id'],c['defender_id'],reserve.id}]
    leader=g.sects[c['attacker_id']];second=others[0]
    c['coalitions']['attacker']=[dict(id=o.id,role='leader' if o is leader else 'ally') for o in (leader,second,reserve)]
    side=c['logistics']['sides']['attacker'];side['items']={};side['contributions']={leader.id:1,second.id:1}
    wallet=logistics.wallet(c,'attacker')
    if balance(g,wallet):transfer_value(g,wallet,'background:spirit',balance(g,wallet),'验收夹具清空原托管')
    transfer_value(g,'background:spirit',wallet,3,'验收夹具真实出资余额')
    for s in ('attacker','defender'):c['logistics']['sides'][s]['items']={}
    before=balance(g,depot.treasury(g,reserve))
    logistics.refund(g,c)
    assert balance(g,depot.treasury(g,reserve))==before
    assert balance(g,wallet)==0


def test_returned_supplies_go_to_actual_return_site_once(engine):
    g,row,c=own_campaign(engine);deps=bind(engine)
    leader=g.sects[c['attacker_id']];cargo=c['cargo_journeys']['attacker']
    for rows in c['journeys'].values():
        for j in rows:
            j.update(phase='stationed',remaining=0);deps.find_person(g,j['person_id']).location_id=c['location_id']
    for cargo_row in c['cargo_journeys'].values():cargo_row.update(phase='stationed',remaining=0)
    c['campaign_phase']='engaged'
    side=c['logistics']['sides']['attacker'];side['location']=c['location_id']
    item=next(iter(g.economy_v2['markets'][f"spirit:{side['location']}"]['commodities']))
    # Three existing physical pieces in the original pool, no cash conversion.
    side['items']={item:3};stock=depot.ensure(g,leader);opening=stock['stock'].get('item:'+item,0)
    lifecycle.withdraw(g,c)
    assert side['return_location']==cargo['origin']
    assert stock['stock'].get('item:'+item,0)==opening
    for _ in range(3000):
        g.player.age+=1
        if lifecycle._journey(deps,g,c):break
    logistics.refund(g,c)
    assert stock['stock'].get('item:'+item,0)==opening+3 and side['items'][item]==0
    before=copy.deepcopy(g.to_dict());logistics.refund(g,c)
    assert g.to_dict()==before


@pytest.mark.parametrize('relocated',[False,True])
def test_full_depot_retries_original_return_after_parent_history_is_gone(engine,relocated):
    from cultivation_life.system.war.stationing import advance as annual_finance
    g,row,c=own_campaign(engine);deps=bind(engine)
    owner=g.sects[c['attacker_id']]
    stock=depot.ensure(g,owner)
    side=c['logistics']['sides']['attacker']
    item=next(iter(side['items']), 'spirit_stone')
    stock['stock']={'item:'+item:10000};side['items']={item:3}
    lifecycle.armistice(g,row,'验收原路撤军')
    for _ in range(3000):
        g.player.age+=1;lifecycle.advance(deps,g,random.Random(641))
        if c['status']=='ended':break
    assert c['status']=='ended' and c['logistics']['refunded']
    assert side['items'][item]==3 and side['location']==owner.location_id
    g.strategic_war_state['wars']=[]
    engine.store.save(g);g=engine._load(g.id)
    c=next(w for w in g.wars if w['id']==c['id'])
    owner=g.sects[c['attacker_id']];stock=depot.ensure(g,owner);side=c['logistics']['sides']['attacker']
    stock['stock']['item:'+item]-=2
    money=balance(g,depot.treasury(g,owner))
    if relocated:
        from cultivation_life.content_registry import CONTENT_DOCUMENTS
        owner.location_id=next(p['id'] for p in CONTENT_DOCUMENTS['maps.json']['worlds'][owner.world]['locations']
                               if p['id']!=side['location'])
    g.player.age+=1;annual_finance(g)
    assert side['items'][item]==(3 if relocated else 1)
    assert stock['stock']['item:'+item]==(9998 if relocated else 10000)
    assert balance(g,depot.treasury(g,owner))==money
    before=copy.deepcopy(g.to_dict());annual_finance(g)
    assert g.to_dict()==before


@pytest.mark.parametrize('residual',['goods','cash','escrow'])
def test_history_cleanup_preserves_unsettled_assets(engine,residual):
    g,row,c,org=reserve_game(engine);dispatch.send(bind(engine),g,row,c,org)
    g.strategic_war_state['wars']=[]
    c.update(status='ended');c['logistics']['refunded']=True
    for s in c['logistics']['sides'].values():s['items']={}
    if residual=='goods':c['logistics']['sides']['attacker']['items']={'spirit_stone':1}
    elif residual=='cash':
        transfer_value(g,'background:spirit',logistics.wallet(c,'attacker'),1,'验收夹具保留原款')
    else:assert balance(g,c['reinforcements'][-1]['wallet'])>0
    lifecycle.compact(g)
    assert any(w['id']==c['id'] for w in g.wars)


def test_dead_roster_is_not_projected_as_living_reinforcements(engine):
    g,row,c,org=reserve_game(engine);deps=bind(engine)
    for j in c['journeys']['attacker']:deps.find_person(g,j['person_id']).alive=False
    shown=next(w for w in public(deps,g)['wars'][0]['campaigns'] if w['id']==c['id'])
    assert all(o['count']==0 and o['phase']=='lost' for o in shown['coalitions']['attacker'])

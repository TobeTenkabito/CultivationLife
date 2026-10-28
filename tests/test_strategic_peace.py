"""Real war contracts, original organization assets and consent boundaries."""
import copy
import random
from dataclasses import replace
from unittest.mock import patch

import pytest

from test_strategic_war import engine, api, snapshot, scenario, own_campaign
from cultivation_life.engine.composition.strategic_war import bind
from cultivation_life.models import GameState
from cultivation_life.race_diplomacy import relations_for
from cultivation_life.system.strategic_war import lifecycle, peace, willingness
from cultivation_life.system.strategic_war.presentation import public
from cultivation_life.system.strategic_war.materialization import materialize
from cultivation_life.system.territory import state as territory
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system.economy import depot
from cultivation_life.content_registry import WORLD_SYSTEMS


def finished(engine, winner='attacker'):
    g,row,child=own_campaign(engine)
    for c in row['commitments']:
        org=next(o for o in lifecycle.organizations(g,row['world']) if o.id==c['org']['id'])
        g.intrigue_state['factions'][depot.treasury(g,org).removeprefix('organization:')]['resources']=100000
        c['budget']=20000
    for w in g.wars:
        if w.get('strategic_war_id')==row['id']:
            w.update(status='peace_ready',winner=winner,battles=3)
            lifecycle.receipt(g,row,w)
    return g,row,child


def offer_command(engine,g,row,term='reparations'):
    bundle=peace.package(bind(engine),g,row,'attacker',term)
    return dict(action='offer_peace',term=term,expected_total=sum(d['amount'] for d in bundle['demands']),
                expected_quote=bundle['quote_key'],war_id=row['id'],expected_revision=row['revision'],
                command_id='peace-1',command_seq=1)


def test_one_real_pair_can_launch_and_score_is_normalized(engine):
    g,row=scenario(engine);deps=bind(engine)
    loser=materialize(deps,g,row['world'],'woodborn',random.Random(9))
    lifecycle.commit(deps,g,row,g.sects['taixuan']);lifecycle.commit(deps,g,row,loser)
    lifecycle._launch(deps,g,row)
    assert row['status']=='active' and len(row['campaigns'])==1
    child=next(w for w in g.wars if w['id']==row['campaigns'][0])
    child.update(status='peace_ready',winner='attacker',battles=3)
    lifecycle.receipt(g,row,child)
    assert row['score']==100


def test_long_march_does_not_expire_before_assembly(engine):
    g,row,c=own_campaign(engine);deps=bind(engine)
    for child in g.wars:
        if child.get('strategic_war_id')!=row['id']:continue
        child['next_battle_age']=g.player.age+110
        for j in [j for js in child['journeys'].values() for j in js]+list(child['cargo_journeys'].values()):
            j.update(phase='outbound',years=100,remaining=100)
    row['deadline_age']=g.player.age+310
    for _ in range(65):
        g.player.age+=1;lifecycle.advance(deps,g,random.Random(5))
    assert row['status']=='active' and all(not w['battles'] for w in g.wars if w.get('strategic_war_id')==row['id'])
    assert all(w['campaign_phase']=='marching' for w in g.wars if w.get('strategic_war_id')==row['id'])


def test_completed_objectives_leave_negotiation_window(engine):
    g,row,_=finished(engine);g.player.age+=1
    lifecycle.advance(bind(engine),g,random.Random(6))
    assert row['status']=='active' and row['objectives_done_age']==g.player.age
    assert not row.get('treaty')


def test_result_reparations_http_real_treasuries_once_and_no_income(api):
    e,post=api;g,row,_=finished(e);e.store.save(g)
    command=offer_command(e,g,row)
    demands=peace.quote(bind(e),g,row,'attacker','reparations')
    assert demands
    parties={d['payer']['id'] for d in demands}|{a['receiver']['id'] for d in demands for a in d['allocations']}
    original={depot.treasury(g,g.sects[k]):balance(g,depot.treasury(g,g.sects[k])) for k in parties}
    reports={k:(v.get('income'),v.get('turnover')) for k,v in g.economy_v2['organizations'].items()}
    inventory=copy.deepcopy(g.player.inventory)
    with patch.object(e,'_vote_probability',return_value=1.):
        result=post(g.id,'strategic-war',**command)
    saved=e._load(g.id);actual=saved.strategic_war_state['wars'][0]
    assert actual['treaty']['total']==command['expected_total'] and actual['status']=='armistice'
    own_received=sum(a['amount'] for d in demands for a in d['allocations'] if a['receiver']['id']==g.player.faction_id)
    assert own_received>peace.war_losses(g,row,'attacker')
    assert '谢谢老板' in {r['name'] for r in result['new_achievements']}
    assert saved.player.milestones['profitable_war_reparations']==1
    for account,value in original.items():
        change=sum(sum(a['amount'] for a in d['allocations'] if account.endswith(':'+a['receiver']['id']))
                   -(d['amount'] if account.endswith(':'+d['payer']['id']) else 0) for d in demands)
        assert balance(saved,account)==value+change
    assert saved.player.inventory==inventory
    assert reports=={k:(v.get('income'),v.get('turnover')) for k,v in saved.economy_v2['organizations'].items()}
    before=snapshot(e,g.id);post(g.id,'strategic-war',status=400,**command)
    assert e.store._path(g.id).read_bytes()==before


def test_cash_quote_changes_fail_without_rng_or_payment(api):
    e,post=api;g,row,_=finished(e);command=offer_command(e,g,row)
    d=peace.quote(bind(e),g,row,'attacker','reparations')[0]
    g.intrigue_state['factions'][f"{d['payer']['kind']}:{d['payer']['id']}"]['resources']=0
    e.store.save(g);before=snapshot(e,g.id)
    post(g.id,'strategic-war',status=400,**command)
    assert e.store._path(g.id).read_bytes()==before


@pytest.mark.parametrize('term',['reparations','heavy_reparations','economic_rights','destroy_outpost','remove_influence'])
def test_no_victory_has_no_unbacked_demands(engine,term):
    g,row,_=own_campaign(engine)
    with pytest.raises(ValueError):peace.quote(bind(engine),g,row,'attacker',term)


@pytest.mark.parametrize('reply',['accept','reject'])
def test_enemy_offer_requires_player_consent_and_can_reply_http(api,reply):
    e,post=api;g,row,_=finished(e,'defender');deps=bind(e)
    offer=peace.propose(deps,g,row,'defender','reparations')
    assert offer['status']=='pending' and not row.get('treaty')
    before_cash=balance(g,'organization:sect:taixuan');e.store.save(g)
    assert e.get_game(g.id)['war_system']['strategic']['wars'][0]['can_reply']
    post(g.id,'strategic-war',action='reply_peace',reply=reply,war_id=row['id'],
         expected_revision=row['revision'],command_seq=1,command_id='reply')
    saved=e._load(g.id);row=saved.strategic_war_state['wars'][0]
    if reply=='accept':
        assert row['status']=='armistice' and balance(saved,'organization:sect:taixuan')<before_cash
    else:
        assert row['status']=='active' and balance(saved,'organization:sect:taixuan')==before_cash


def test_expired_or_cross_world_reply_cannot_pay(api):
    e,post=api;g,row,_=finished(e,'defender');offer=peace.propose(bind(e),g,row,'defender','reparations')
    for wrong_world in (True,False):
        trial=copy.deepcopy(g)
        if wrong_world:trial.player.world='true_demon'
        else:trial.player.age=offer['expires']
        e.store.save(trial);before=snapshot(e,g.id)
        post(g.id,'strategic-war',status=400,action='reply_peace',reply='accept',war_id=row['id'],
             expected_revision=row['revision'],command_seq=1,command_id='bad-reply')
        assert e.store._path(g.id).read_bytes()==before


def test_long_truce_sets_actual_calendar_and_survives_roundtrip(engine):
    g,row,_=finished(engine)
    offer=peace.propose(bind(engine),g,row,'attacker','long_truce')
    assert offer['status']=='accepted'
    assert relations_for(g)['human|woodborn']['truce_until_age']==g.player.age+3000
    assert GameState.from_dict(g.to_dict()).strategic_war_state==g.strategic_war_state


@pytest.mark.parametrize('term',['destroy_outpost','remove_influence'])
def test_territory_terms_use_real_battle_site_and_original_relocation(engine,monkeypatch,term):
    monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'],'enabled',True)
    g,row,c=finished(engine);loser=g.sects[c['defender_id']];old_location=loser.location_id
    territory.ensure(g,engine.maps,row['world'])[old_location][loser.id]['outpost']=True
    before_player=(g.player.world,g.player.location_id);ids=[n.id for n in loser.npcs]
    offer=peace.propose(bind(engine),g,row,'attacker',term)
    assert offer['status']=='accepted'
    book=territory.snapshot(g,engine.maps,row['world'])
    if term=='destroy_outpost':assert not book[old_location][loser.id]['outpost'] and loser.location_id==old_location
    else:assert loser.id not in book.get(old_location,{}) and loser.location_id!=old_location
    assert ids==[n.id for n in loser.npcs] and (g.player.world,g.player.location_id)==before_player
    assert GameState.from_dict(g.to_dict())


def test_disabled_dlc_never_offers_territorial_terms(engine,monkeypatch):
    g,row,_=finished(engine);monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'],'enabled',False)
    assert not {'destroy_outpost','remove_influence'} & {o['term'] for o in public(bind(engine),g)['wars'][0]['peace_options']}


def economic_fixture(engine):
    from cultivation_life.system.economy.enterprise_acquisition import acquire
    g,row,c=finished(engine);loser=g.sects[c['defender_id']]
    source=depot.treasury(g,loser)
    g.intrigue_state['factions'][source.removeprefix('organization:')]['resources']=10**9
    asset=acquire(g,engine.maps,row['world'],loser.location_id,'farm',source.split(':')[1],loser.id,source,8)
    return g,row,c,asset


def test_economic_treaty_preserves_unique_stock_place_and_pending_job(api):
    e,post=api;g,row,c,asset=economic_fixture(e)
    old=copy.deepcopy(asset);e.store.save(g)
    command=offer_command(e,g,row,'economic_rights')
    with patch.object(e,'_vote_probability',return_value=1.):post(g.id,'strategic-war',**command)
    saved=e._load(g.id);asset=saved.economy_v2['estates'][asset['id']]
    assert asset['owner_id']==c['attacker_id'] and not asset['enabled']
    assert all(asset[k]==old[k] for k in ('id','world','location','stock','reserve','job'))
    actual=next(w for w in saved.wars if w['id']==c['id'])
    assert actual['economic_transfers'][0]['estates']==[asset['id']]
    assert saved.strategic_war_state['wars'][0]['treaty']['results']


def test_asset_quote_rejects_changed_ownership_without_partial_effect(api):
    e,post=api;g,row,c,asset=economic_fixture(e);command=offer_command(e,g,row,'economic_rights')
    asset.update(owner_kind='sect',owner_id='taixuan');e.store.save(g);before=snapshot(e,g.id)
    post(g.id,'strategic-war',status=400,**command)
    assert e.store._path(g.id).read_bytes()==before


def test_will_factors_follow_assignment_balance_supplies_and_casualties(engine):
    g,row,c=own_campaign(engine);deps=bind(engine);org=g.sects[c['defender_id']]
    # Comparable forces keep each loss visible after integer percentage rounding.
    deps=replace(deps,power=lambda npc:100)
    before=copy.deepcopy(g.to_dict());first=willingness.evaluate(deps,g,row)
    assert before==g.to_dict()
    commit=next(r for r in row['commitments'] if r['org']['id']==org.id)
    g.intrigue_state['factions']['sect:'+org.id]['resources']=0
    c['logistics']['sides']['defender']['items']={}
    for identity in commit['will_baseline']:
        n=deps.find_person(g,identity)
        if n:n.wounds=4
    after=willingness.evaluate(deps,g,row)
    assert after[org.id]['supply']<first[org.id]['supply']
    assert after[org.id]['casualties']>first[org.id]['casualties']
    for n in org.npcs:n.alive=False
    lost=willingness.evaluate(deps,g,row)
    assert lost[org.id]['task']<first[org.id]['task'] and lost[org.id]['alliance']<first[org.id]['alliance']


def test_low_will_is_passive_only_for_npcs_and_no_retreat_before_fighting(engine):
    g,row,c=own_campaign(engine)
    for commitment in row['commitments']:commitment['willingness']=10
    g.player.age+=10;willingness.advance(bind(engine),g,row)
    assert c['status']=='active' and not c.get('withdrawn_orgs')
    assert 'taixuan' not in c['passive_orgs'] and c['defender_id'] in c['passive_orgs']


def test_actual_personal_battle_at_site_and_cooldown_via_http(api):
    e,post=api;g,row,c=own_campaign(e)
    c['campaign_phase']='engaged';g.player.location_id=c['location_id']
    for side,journeys in c['journeys'].items():
        for j in journeys:
            j.update(phase='stationed',remaining=0);bind(e).find_person(g,j['person_id']).location_id=c['location_id']
    e.store.save(g)
    assert e.get_game(g.id)['war_system']['strategic']['wars'][0]['campaigns'][0]['can_participate']
    with patch.object(e,'_resolve_player_war_round',wraps=e._resolve_player_war_round) as resolver:
        post(g.id,'strategic-war',action='participate_round',war_id=row['id'],campaign_id=c['id'],expected_revision=row['revision'],command_seq=1,command_id='personal')
        assert resolver.call_count==1
    saved=e._load(g.id);actual=next(w for w in saved.wars if w['id']==c['id'])
    assert actual['battles']==1 and actual['last_personal_age']==g.player.age
    assert any('玩家参战' in log['title'] for log in actual['logs'])
    before=snapshot(e,g.id)
    post(g.id,'strategic-war',status=400,action='participate_round',war_id=row['id'],campaign_id=c['id'],expected_revision=row['revision']+1,command_seq=2,command_id='personal-again')
    assert e.store._path(g.id).read_bytes()==before


def test_map_markers_follow_original_campaign_and_remove_after_return(engine):
    from cultivation_life.system.war.map_markers import markers
    g,row,c=own_campaign(engine);names={o.id:o.name for o in g.sects.values()}
    for phase,status in [('marching','active'),('engaged','active'),('returning','withdrawing')]:
        c.update(campaign_phase=phase,status=status)
        marker=next(r for r in markers(g,names)[c['location_id']] if r['id']==c['id'])
        assert marker['phase']==phase and marker['strategic_war_id']==row['id']
    c.update(status='ended',campaign_phase='home')
    assert not any(r['id']==c['id'] for rows in markers(g,names).values() for r in rows)
    g.player.world='human'
    assert not markers(g,names)


def test_reparations_cover_booked_losses_without_counting_principal_twice(engine):
    g,row,_=finished(engine)
    for child in g.wars:
        if child.get('strategic_war_id')==row['id']:
            book=child['logistics']['sides']['attacker']
            book.update(destroyed=10000,captured_loss=2000,mobilization_paid=3000,stationing_paid=5000,
                        purchased=10**8,mobilized=10**9,spent=8000,transport_loss=2000)
    assert peace.war_losses(g,row,'attacker')==40000
    normal=peace.quote(bind(engine),g,row,'attacker','reparations')
    heavy=peace.quote(bind(engine),g,row,'attacker','heavy_reparations')
    assert sum(d['compensation'] for d in normal)==40000
    assert sum(d['compensation'] for d in heavy)==80000
    assert sum(d['amount'] for d in normal)>40000
    assert sum(d['amount'] for d in heavy)>sum(d['amount'] for d in normal)
    assert all(sum(a['amount'] for a in d['allocations'])==d['amount'] for d in heavy)


def test_unaffordable_claim_is_disclosed_without_unbacked_debt(engine):
    g,row,_=finished(engine)
    for child in g.wars:
        if child.get('strategic_war_id')==row['id']:
            child['logistics']['sides']['attacker']['destroyed']=10**9
    bundle=peace.package(bind(engine),g,row,'attacker','heavy_reparations')
    assert bundle['shortfall']>0 and bundle['claimed']>sum(d['amount'] for d in bundle['demands'])
    assert all(d['amount']<=90000 for d in bundle['demands'])


def test_calendar_truce_survives_many_units_and_blocks_independent_allies(engine):
    from cultivation_life.world_state import race_pair
    g,row,c=finished(engine);peace.propose(bind(engine),g,row,'attacker','long_truce')
    attacker,defender=c['attacker_id'],c['defender_id']
    assert g.sect_relations[race_pair(attacker,defender)]['truce_until_age']==g.player.age+3000
    for child in g.wars:
        if child.get('strategic_war_id')!=row['id']:continue
        for js in child['journeys'].values():
            for j in js:j.update(phase='home',remaining=0)
        for cargo in child['cargo_journeys'].values():cargo.update(phase='home',remaining=0)
        child.update(status='ended',campaign_phase='home')
    row['status']='ended'
    g.diplomacy_unit+=1000;g.player.age+=200
    with pytest.raises(ValueError,match='和约停战期'):
        engine._start_war(g,'sect',attacker,defender,initiated_by_player=True)
    independent=copy.deepcopy(c);independent.pop('strategic_war_id');independent['defender_id']='unrelated'
    independent['coalitions']['defender']=[dict(id='unrelated')]
    g.sect_relations[race_pair(attacker,'unrelated')]=dict(truce_until_age=g.player.age+2000)
    before=copy.deepcopy(independent)
    with pytest.raises(ValueError,match='盟军'):
        engine._add_war_participant(g,independent,'attacker',attacker,'taixuan')
    assert independent==before


@pytest.mark.parametrize('context',['ordinary','no_supplies','fake_parent','active_parent'])
def test_finished_child_cannot_restart_independent_war_before_total_treaty(engine,context):
    from cultivation_life.world_state import race_pair
    g,row,c=finished(engine)
    for child in g.wars:
        if child.get('strategic_war_id')!=row['id']:continue
        for js in child['journeys'].values():
            for j in js:j.update(phase='home',remaining=0)
        for cargo in child['cargo_journeys'].values():cargo.update(phase='home',remaining=0)
        child.update(status='ended',campaign_phase='home')
    g.sect_relations[race_pair(c['attacker_id'],c['defender_id'])]=dict(status='neutral')
    assert row['status']=='active' and not row.get('treaty')
    kwargs=({'prepare_supplies':False} if context=='no_supplies' else
            {'strategic_war_id':'fake'} if context=='fake_parent' else
            {'strategic_war_id':row['id']} if context=='active_parent' else {})
    with pytest.raises(ValueError,match='种族战争'):
        engine._start_war(g,'sect',c['attacker_id'],c['defender_id'],initiated_by_player=True,**kwargs)

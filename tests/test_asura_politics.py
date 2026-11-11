"""Original fiscal disputes, NPC decisions, political relationships and attacks."""
import copy
import json
import pytest
from test_asura_governorship import setup, assigned, construct, command
from cultivation_life.models import GameState
from cultivation_life.system import institution_authority as authority, institution_petitions as petitions
from cultivation_life.system import asura_court, asura_factions, buildings
from cultivation_life.system.asura_governorship import rules, politics, disputes, management, presentation
from cultivation_life.system.institution_ai import rules as agendas, runtime
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system.building_destruction import destroy


def prepare(e,g,*,build=True):
    g,row=assigned(e,g)
    if build:g=construct(e,g,row);row=rules.offices(g)[0]
    king=g.upper_institutions['asura']['court']['holders']['5']
    candidates=[n for n in g.sects[rules.COURT].npcs if n.id!=king][:3]
    for n in candidates:n.location_id=row['location'];n.realm_index=9
    e.store.save(g)
    return g,row,candidates


def act(e,g,row,operation,kind=None,choice=None):
    latest=e._load(g.id);scope=authority.records(latest)[row['id']]
    case=next((c for c in petitions.book(scope).get('active',[]) if c['kind']==kind),None)
    return command(e,g,'petition',office=row['id'],operation=operation,case=case['id'] if case else None,choice=choice)[0]


def current(g,kind):
    return next(c for c in petitions.book(rules.offices(g)[0])['active'] if c['kind']==kind)


def test_budget_real_npc_king_approves_once_without_teleport_or_mint(setup):
    e,g=setup;g,row,_=prepare(e,g,build=False)
    g=act(e,g,row,'observe');claim=current(g,'budget');amount=claim['evidence']['amount']
    g=act(e,g,row,'resolve','budget','submit');g=act(e,g,row,'endorse','budget','approve')
    row=rules.offices(g)[0];money=balance(g,rules.SOURCE);place=g.player.location_id
    g.player.age+=1;management.advance(g,e.maps)
    assert balance(g,row['wallet'])==amount and balance(g,rules.SOURCE)==money-amount
    assert g.player.location_id==place and rules.building(g,row) is None
    receipt=petitions.book(row)['history'][-1]
    assert receipt['decision']=='approve' and receipt['pledge']['choice']=='approve'
    saved=copy.deepcopy(g.to_dict());management.advance(g,e.maps);assert g.to_dict()==saved
    assert GameState.from_dict(g.to_dict()).economy_v2==g.economy_v2


def test_remittance_is_original_money_and_broken_pledge_persists(setup):
    e,g=setup;g,row,people=prepare(e,g)
    g=act(e,g,row,'observe');g=act(e,g,row,'endorse','remittance','half')
    cash=balance(g,row['wallet']);treasury=balance(g,rules.SOURCE);amount=current(g,'remittance')['evidence']['amount']
    g=act(e,g,row,'resolve','remittance','pay');row=rules.offices(g)[0]
    assert balance(g,row['wallet'])==cash-amount and balance(g,rules.SOURCE)==treasury+amount
    assert row['returned']==amount
    assert any(politics.state(g)['people'][n.id]['bonds']['player']<0 for n in people)
    saved=copy.deepcopy(g.to_dict());presentation.public(g);asura_factions.public(g,rules.court(g));assert saved==g.to_dict()
    serial=petitions.book(row)['sequence'];g=act(e,g,row,'observe')
    assert petitions.book(rules.offices(g)[0])['sequence']==serial


def test_staff_dispute_uses_original_person_and_rechecks_departure(setup):
    e,g=setup;g,row,people=prepare(e,g);g=act(e,g,row,'observe');case=current(g,'personnel')
    candidate=next(n for n in people if n.id==case['evidence']['candidate'])
    saved=e.store.load(g.id);next(n for n in saved.sects[rules.COURT].npcs if n.id==candidate.id).location_id='ten_thousand_battle_city';e.store.save(saved)
    before=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError,match='离场'):act(e,g,row,'resolve','personnel','appoint')
    assert e.store._path(g.id).read_bytes()==before
    g=act(e,g,row,'resolve','personnel','alternative');row=rules.offices(g)[0]
    assert row['people']==[case['evidence']['alternative']]
    assert sum(n.id==row['people'][0] for n in g.sects[rules.COURT].npcs)==1


def test_project_dispute_cancels_original_escrow_without_resetting_work(setup):
    e,g=setup;g,row,people=prepare(e,g);row['people']=[people[0].id]
    destroy(g,rules.building(g,row),source='war')
    scope=management.scopes(g,e.maps)[0];offer=management.offers(g,e.maps,scope)[0]
    job=runtime.start(g,scope,offer,people[0].id,adapter=management)
    people[0].location_id='ten_thousand_battle_city';g.player.age+=1;management.advance(g,e.maps);e.store.save(g)
    left=balance(g,job['wallet']);cash=balance(g,row['wallet'])
    g=act(e,g,row,'observe');g=act(e,g,row,'resolve','performance','cancel');row=rules.offices(g)[0]
    assert balance(g,row['wallet'])==cash+left and balance(g,job['wallet'])==0
    assert not agendas.record(g,row['id']).get('job')
    receipt=agendas.record(g,row['id'])['history'][-1]
    assert receipt['funded']==receipt['spent']+receipt['refunded']
    assert rules.building(g,row)['status']=='destroyed'


def test_access_is_original_permission_revocation_removes_incumbent_access(setup):
    e,g=setup;g,row,_=prepare(e,g);g=act(e,g,row,'observe')
    g=act(e,g,row,'resolve','access','restrict');row=rules.offices(g)[0];building=rules.building(g,row)
    assert not building['public'] and buildings.can_enter(g,building)
    assert building['owner']==row['owner'] and not building['users']
    authority.revoke(g,row)
    assert not buildings.can_enter(g,building)


def test_tenure_requires_real_receipt_and_keeps_original_liabilities(setup):
    e,g=setup;g,row,_=prepare(e,g);g.player.age=row['expires']-50;e.store.save(g)
    g=act(e,g,row,'observe');g=act(e,g,row,'resolve','tenure','submit')
    row=rules.offices(g)[0];options=disputes.choices(g,row,current(g,'tenure'))
    assert next(o for o in options if o['id']=='approve')['reason']
    g=act(e,g,row,'resolve','remittance','half');row=rules.offices(g)[0]
    expiry=row['expires'];wallet=balance(g,row['wallet']);g.player.age+=1;management.advance(g,e.maps)
    assert row['expires']==expiry+500 and balance(g,row['wallet'])==wallet
    assert not any(c['kind']=='tenure' for c in petitions.book(row)['active'])
    assert GameState.from_dict(g.to_dict()).economy_v2==g.economy_v2


def test_player_king_cannot_self_approve_while_in_province(setup):
    e,g=setup;g,row,people=prepare(e,g,build=False)
    authority.relinquish(g,row,'player');authority.nominate(g,row,people[0].id,500)
    authority.assume(g,row,people[0].id,'asura',row['location'])
    asura_court.change_rank(g,rules.court(g),5)
    g.player.age+=1;management.advance(g,e.maps);e.store.save(g)
    assert current(g,'budget')['status']=='submitted'
    with pytest.raises(ValueError,match='权限'):act(e,g,row,'resolve','budget','approve')
    g.player.location_id='ten_thousand_battle_city';e.store.save(g)
    before=balance(g,rules.SOURCE);g=act(e,g,row,'resolve','budget','approve')
    assert balance(g,rules.SOURCE)<before and balance(g,row['wallet'])>0


def test_disabled_stale_and_malformed_requests_cannot_change_money(setup,monkeypatch):
    e,g=setup;g,row,_=prepare(e,g);g=act(e,g,row,'observe');case=current(g,'remittance')
    payload=dict(action='petition',office=row['id'],operation='resolve',case=case['id'],choice='pay',token=rules.token(e._load(g.id)))
    g=act(e,g,row,'endorse','remittance','pay');before=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError):e.upper_institution_action(g.id,'governorship',json.dumps(payload))
    assert e.store._path(g.id).read_bytes()==before
    for bad in ([],{},True):
        with pytest.raises(ValueError):command(e,g,'petition',office=row['id'],operation=bad)
        assert e.store._path(g.id).read_bytes()==before
    monkeypatch.setattr(politics,'enabled',lambda:False)
    with pytest.raises(ValueError,match='停用'):act(e,g,row,'resolve','remittance','pay')
    money=balance(g,row['wallet']);g=act(e,g,row,'withdraw','remittance')
    assert balance(g,row['wallet'])==money


def test_expiry_foreign_years_and_lost_authority_never_mint(setup):
    from cultivation_life.regional_context import CalendarGame
    e,g=setup;g,row,_=prepare(e,g);g=act(e,g,row,'observe');row=rules.offices(g)[0]
    deadline=current(g,'access')['deadline'];snapshot=copy.deepcopy(g.to_dict())
    management.advance(CalendarGame(g,'celestial',deadline),e.maps)
    assert g.to_dict()==snapshot
    authority.revoke(g,row);e.store.save(g)
    with pytest.raises(ValueError,match='权限'):act(e,g,row,'resolve','access','restrict')
    money=balance(g,row['wallet']);g.player.age=deadline;management.advance(g,e.maps)
    assert not petitions.book(row)['active'] and balance(g,row['wallet'])==money


@pytest.mark.parametrize('corrupt',['kind','amount','deadline','duplicate','bond'])
def test_forged_persistent_cases_and_bonds_rejected(setup,corrupt):
    e,g=setup;g,row,_=prepare(e,g);g=act(e,g,row,'observe');doc=g.to_dict()
    scope=doc['economy_v2']['administrations'][row['id']];case=scope['petitions']['active'][0]
    if corrupt=='kind':case['kind']='fake'
    if corrupt=='amount':case['evidence']['amount']=True
    if corrupt=='deadline':case['deadline']=case['opened']
    if corrupt=='duplicate':scope['petitions']['active'].append(copy.deepcopy(case))
    if corrupt=='bond':doc['upper_institutions']['asura']['court']['factions']['politics']=dict(last_unit=0,people={'forged':dict(bonds={'player':999},career={},deeds=[])})
    with pytest.raises(ValueError):GameState.from_dict(doc)


def test_actual_roles_drive_factions_and_power_alone_never_forces_rebellion(setup):
    e,g=setup;state=rules.court(g);asura_court.change_rank(g,state,5)
    npc=g.sects[rules.COURT].npcs[-1];state['court']['offices']['marshal']=npc.id
    assert politics.faction(g,npc.id)[0]=='war_hosts'
    for row in state['court']['factions']['rows']:row.update(external=70,loyalty=0)
    for _ in range(8):state['unit']+=1;asura_factions.tick(g,state,asura_court.people(g))
    assert state['court']['challenge'] is None
    view=asura_factions.public(g,state)
    assert sum(r['external'] for r in view['rows'])==pytest.approx(100)
    assert 'politics' not in view and all('bonds' not in p for p in view['members'])
    asura_court.change_rank(g,state,1);state['unit']+=1;asura_factions.tick(g,state,asura_court.people(g))
    assert politics.state(g)['last_unit']==state['unit']


def test_role_switching_cannot_farm_patronage_and_renewal_uses_this_term(setup):
    e,g=setup;g,row,people=prepare(e,g)
    for _ in range(12):
        politics.appointment(g,people[0].id,'player','staff',row['id'])
        politics.appointment(g,people[0].id,'player','marshal','court-office:marshal')
    assert politics.state(g)['people'][people[0].id]['bonds']['player']==4
    g=act(e,g,row,'observe');g=act(e,g,row,'resolve','remittance','pay');row=rules.offices(g)[0]
    assert disputes.completed(g,row)==1
    row['expires']+=500
    assert disputes.completed(g,row)==0


def test_disabled_expiry_keeps_original_pledge_consequences(setup,monkeypatch):
    e,g=setup;g,row,people=prepare(e,g);g=act(e,g,row,'observe');g=act(e,g,row,'endorse','remittance','pay')
    row=rules.offices(g)[0];deadline=current(g,'remittance')['deadline'];money=balance(g,row['wallet'])
    monkeypatch.setattr(politics,'enabled',lambda:False)
    g.player.age=deadline;management.advance(g,e.maps)
    assert balance(g,row['wallet'])==money and not petitions.book(row)['active']
    assert all(politics.state(g)['people'][n.id]['bonds']['player']==-6 for n in people)


def test_future_case_is_not_resolved_during_historical_catchup(setup):
    from cultivation_life.regional_context import CalendarGame
    e,g=setup;g,row,_=prepare(e,g,build=False);g=act(e,g,row,'observe');g=act(e,g,row,'resolve','budget','submit')
    row=rules.offices(g)[0];snapshot=copy.deepcopy(g.to_dict())
    disputes.advance(CalendarGame(g,'asura',g.player.age-1),row)
    assert g.to_dict()==snapshot


def test_instance_and_ownership_changes_refuse_original_case(setup):
    from cultivation_life.system.asura_governorship.actions import settle
    e,g=setup;g,row,_=prepare(e,g);g=act(e,g,row,'observe');case=current(g,'access')
    for field,value in [('map_journey',{'fixture':True}),('trial_site_state',{'active':{'fixture':True}}),('guixu_state',{'player_session':{'fixture':True}})]:
        probe=copy.deepcopy(g);setattr(probe,field,value)
        with pytest.raises(ValueError,match='普通地图'):
            settle(probe,dict(action='petition',office=row['id'],operation='resolve',case=case['id'],choice='restrict',token=rules.token(probe)))
    row=rules.offices(g)[0];building=rules.building(g,row);building['owner']=dict(kind='background',id='original-new-owner');e.store.save(g)
    before=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError,match='产权'):act(e,g,row,'resolve','access','restrict')
    assert e.store._path(g.id).read_bytes()==before


def test_npc_appropriation_respects_original_limited_budget(setup):
    e,g=setup;g,row,_=prepare(e,g,build=False);g=act(e,g,row,'observe');g=act(e,g,row,'resolve','budget','submit')
    row=rules.offices(g)[0];rules.court(g)['treasury']=1000
    g.player.age+=1;management.advance(g,e.maps)
    assert balance(g,row['wallet'])==100 and balance(g,rules.SOURCE)==900
    receipt=petitions.book(row)['history'][-1]
    assert receipt['evidence']['paid']==100 and receipt['evidence']['amount']>100
    snapshot=copy.deepcopy(g.to_dict());management.advance(g,e.maps);assert g.to_dict()==snapshot


def test_original_faction_preferences_change_valid_decisions_but_never_bypass_facts(setup):
    e,g=setup;g,row,_=prepare(e,g);g=act(e,g,row,'observe');row=rules.offices(g)[0];case=current(g,'access')
    roster=g.sects[rules.COURT].npcs
    military=next(n for n in roster if politics.faction(g,n.id)[0]=='war_hosts')
    civic=next(n for n in roster if politics.faction(g,n.id)[0]=='free_cities')
    options=disputes.choices(g,row,case)
    assert petitions.choose(options,budget=0,preferred=politics.preference(g,military.id,'access',case['evidence']))=='restrict'
    assert petitions.choose(options,budget=0,preferred=politics.preference(g,civic.id,'access',case['evidence']))=='open'
    authority.revoke(g,row)
    assert petitions.choose(disputes.choices(g,row,case),budget=10**12,preferred='restrict') is None

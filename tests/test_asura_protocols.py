"""Adversarial original-command tests for the completed provincial expansion."""
import copy,json,hashlib
import pytest
from test_asura_governorship import setup,assigned,construct,command
from test_asura_military import prepared,support,order,advance
from cultivation_life.models import GameState
from cultivation_life.system.asura_governorship import rules,protocols,politics,military,settlement
from cultivation_life.system import institution_deliberation as council,institution_garrisons as troops,institution_authority as authority,institution_mandates as mandates
from cultivation_life.system.economy.ledger import balance
from cultivation_life.person_assignments import research_assignment


def act(e,g,op,**kw):return command(e,g,'protocol',office=rules.offices(g)[0]['id'],operation=op,**kw)[0]


def local_people(g,row,count=3):
    people=[n for n in g.sects[rules.COURT].npcs if n.id!=military.king_id(g) and not research_assignment(g,n.id)][:count]
    for n in people:n.location_id=row['location'];n.realm_index=9
    return people


def test_base_decisions_are_finite_and_cosign_original_people():
    offers=[dict(key='repair',category='repair',budget=10,urgency=70),dict(key='supply',category='supply',budget=20,urgency=60)]
    assert council.cosign(offers,['n1','n1','n2'],'balanced',10)=={'repair':['n1','n2']}
    assert council.cosign(offers,['n1'],'balanced',9)=={}
    assert council.decide([dict(id='approve',cost=100,priority=80),dict(id='reject',priority=30)],budget=99)=='reject'


def test_inquiry_paid_real_years_defence_recovery_and_roundtrip(setup):
    e,g=setup;g,row=assigned(e,g);g=construct(e,g,row);row=rules.offices(g)[0]
    reviewer=local_people(g,row)[0];e.store.save(g)
    cash=balance(g,row['wallet']);purse=balance(g,'player')
    g=act(e,g,'divert',amount=30000);row=rules.offices(g)[0];case=council.book(row)['cases'][0]
    assert balance(g,row['wallet'])==cash-30000 and balance(g,'player')==purse+30000
    g=act(e,g,'investigate',case=case['id'],person=reviewer.id);row=rules.offices(g)[0];case=council.book(row)['cases'][0]
    assert research_assignment(g,reviewer.id)['id']==case['id']
    snapshot=copy.deepcopy(g.to_dict())
    assert protocols.public(g,row)['cases'][0]['reviewer_name']==reviewer.name
    assert g.to_dict()==snapshot
    from cultivation_life.system.asura_governorship.court_affairs import advance as audit
    audit(g,row);assert case['progress']==0
    for _ in range(10):g.player.age+=1;audit(g,row)
    assert case['stage']=='defence' and case['spent']==10000 and not research_assignment(g,reviewer.id)
    e.store.save(g);g=act(e,g,'defend',case=case['id'],choice='contest')
    g.player.location_id=military.CAPITAL;e.store.save(g);g=act(e,g,'judge',case=case['id'])
    row=rules.offices(g)[0];assert row['status']=='handover'
    g.player.location_id=row['location'];e.store.save(g)
    g=act(e,g,'restitute',case=case['id'],amount=10000)
    with pytest.raises(ValueError):act(e,g,'restitute',case=case['id'],amount=30000)
    g=act(e,g,'restitute',case=case['id'],amount=20000);row=rules.offices(g)[0]
    assert not council.book(row)['cases'] and balance(g,row['wallet'])==cash-10000
    assert row['status']=='handover';GameState.from_dict(g.to_dict())
    with pytest.raises(ValueError):act(e,g,'restitute',case=case['id'],amount=1)


def test_reviewer_absence_pauses_and_disabled_dlc_retains_debt(setup,monkeypatch):
    e,g=setup;g,row=assigned(e,g);authority.fund(g,row,rules.SOURCE,100000)
    n=local_people(g,row)[0];e.store.save(g)
    g=act(e,g,'divert',amount=1000);row=rules.offices(g)[0];c=council.book(row)['cases'][0]
    g=act(e,g,'investigate',case=c['id'],person=n.id);row=rules.offices(g)[0];c=council.book(row)['cases'][0]
    from cultivation_life.relationship_records import find_person
    find_person(g,n.id).location_id=military.CAPITAL
    g.player.age+=1;protocols.advance(g,e.maps,row);assert c['progress']==0
    monkeypatch.setattr(rules,'enabled',lambda:False);e.store.save(g)
    with pytest.raises(ValueError):act(e,g,'case_cancel',case=c['id'])
    g=act(e,g,'restitute',case=c['id'],amount=1000);assert not council.book(rules.offices(g)[0])['cases']


def test_three_original_signatures_actual_treasury_and_no_replay(setup):
    e,g=setup;g,row=assigned(e,g);local_people(g,row);e.store.save(g)
    g=act(e,g,'pressure',amount=1000);row=rules.offices(g)[0];c=council.book(row)['cases'][0]
    assert len(set(c['participants']))>=3
    g.player.location_id=military.CAPITAL;e.store.save(g);before=balance(g,rules.SOURCE)
    g=act(e,g,'pressure_decide',case=c['id'],choice='approve');row=rules.offices(g)[0]
    assert balance(g,rules.SOURCE)==before-1000 and balance(g,row['wallet'])==1000
    with pytest.raises(ValueError):act(e,g,'pressure_decide',case=c['id'],choice='approve')


def test_patronage_needs_actual_bond_and_cooldown(setup):
    e,g=setup;g,row=assigned(e,g);n=local_people(g,row)[0];politics.remember(g,n.id,'player',20,'原履约',row['id']);e.store.save(g)
    g=act(e,g,'patronage',person=n.id,choice='blood_clans')
    assert politics.faction(g,n.id)[0]=='blood_clans';GameState.from_dict(g.to_dict())
    with pytest.raises(ValueError):act(e,g,'patronage',person=n.id,choice='war_hosts')


def test_unpaid_original_case_holds_permissions_across_resignation(setup):
    e,g=setup;g,row=assigned(e,g);authority.fund(g,row,rules.SOURCE,10000);e.store.save(g)
    g=act(e,g,'divert',amount=1000);row=rules.offices(g)[0];c=council.book(row)['cases'][0]
    assert not authority.effective(g,row)
    with pytest.raises(ValueError):rules.require_handover(g)
    authority.relinquish(g,row,'player')
    with pytest.raises(ValueError,match='原未清责任'):authority.nominate(g,row,'player',500)
    e.store.save(g);g=act(e,g,'restitute',case=c['id'],amount=1000);row=rules.offices(g)[0]
    authority.nominate(g,row,'player',500)
    assert row['status']=='appointed'


def test_suspended_governor_can_raise_actual_army_without_erasing_debt(setup):
    e,g,row,people=prepared(setup,1);support(g,row);e.store.save(g)
    g=act(e,g,'divert',amount=1000);row=rules.offices(g)[0]
    assert not authority.effective(g,row)
    g=order(e,g,row,'rebel');row=rules.offices(g)[0]
    assert military.conflict(row)['status']=='raised' and row['status']=='handover'
    assert council.book(row)['cases'][0]['amount']==1000
    GameState.from_dict(g.to_dict())


def test_original_npc_king_funds_local_inquiry_and_overdue_verdict(setup):
    e,g=setup;g,row=assigned(e,g);authority.fund(g,row,rules.SOURCE,1000)
    people=local_people(g,row);e.store.save(g)
    g=act(e,g,'divert',amount=1000);row=rules.offices(g)[0];c=council.book(row)['cases'][0]
    from cultivation_life.relationship_records import find_person
    from cultivation_life.system.asura_governorship.court_affairs import advance as audit
    sovereign=find_person(g,military.king_id(g));sovereign.location_id=row['location']
    original=balance(g,rules.SOURCE);place=g.player.location_id
    g.player.age+=1;audit(g,row);assert c['stage']=='open' and c['spent']==0
    sovereign.location_id=military.CAPITAL
    for _ in range(11):g.player.age+=1;audit(g,row)
    assert c['stage']=='defence' and c['progress']==10 and c['spent']==10000
    assert c['reviewer'] in {n.id for n in people} and g.player.location_id==place
    assert balance(g,rules.SOURCE)==original-10000 and balance(g,row['wallet'])==0
    g.player.age=c['deadline'];audit(g,row)
    assert c['stage']=='judged' and row['status']=='handover' and c['amount']-c['paid']==1000
    GameState.from_dict(g.to_dict())


def test_four_charters_and_central_money_returns_to_original_source(setup):
    e,g,row,people=prepared(setup,1)
    for funding in ('central','local'):
        for appointments in ('central','local'):
            mandates.configure(row,funding,appointments)
            assert council.book(row)['mandate']==dict(funding=funding,appointments=appointments)
    treasury=balance(g,rules.SOURCE);local=balance(g,row['wallet']);old=balance(g,troops.state(row)['wallet'])
    troops.provision(g,row,9999,source=rules.SOURCE)
    assert balance(g,rules.SOURCE)==treasury-9999
    snapshot=copy.deepcopy(row)
    with pytest.raises(ValueError):troops.provision(g,row,10**15,source=rules.SOURCE)
    assert row==snapshot
    troops.recall(g,e.maps,row);g.player.age+=1;troops.advance(g,e.maps,row)
    assert balance(g,rules.SOURCE)==treasury and balance(g,row['wallet'])==local+old
    GameState.from_dict(g.to_dict())


def test_local_cannot_override_central_appointments(setup):
    e,g,row,_=prepared(setup,1);n=local_people(g,row)[0]
    mandates.configure(row,'central','central');e.store.save(g)
    with pytest.raises(ValueError,match='中央'):order(e,g,row,'enlist',person=n.id)
    with pytest.raises(ValueError,match='中央'):order(e,g,row,'provision',amount=1)
    with pytest.raises(ValueError):act(e,g,'central_pay',amount=1)


def test_rotation_keeps_old_guard_until_actual_colocation(setup):
    e,g,row,people=prepared(setup,1);old=people[0].id;n=local_people(g,row)[0];e.store.save(g)
    g=order(e,g,row,'dispatch',destination=military.CAPITAL);row=rules.offices(g)[0]
    advance(g,e,row,max(u['remaining'] for u in troops.active(row)));e.store.save(g)
    g=act(e,g,'relief',target=old,person=n.id)
    with pytest.raises(ValueError):act(e,g,'relief_finish')
    g=act(e,g,'relief_send');row=rules.offices(g)[0]
    assert old in {u['person_id'] for u in troops.stationed(g,row,military.CAPITAL)}
    advance(g,e,row,max(u['remaining'] for u in troops.active(row)));e.store.save(g)
    closing=copy.deepcopy(g);closing_row=rules.offices(closing)[0]
    troops.recall(closing,e.maps,closing_row)
    for _ in range(max(u['remaining'] for u in troops.active(closing_row))+1):
        closing.player.age+=1;troops.advance(closing,e.maps,closing_row)
    authority.relinquish(closing,closing_row,'player')
    assert council.book(closing_row)['rotation']['stage']=='cancelled'
    GameState.from_dict(closing.to_dict())
    g=act(e,g,'relief_finish');row=rules.offices(g)[0]
    assert council.book(row)['rotation']['stage']=='relieved'
    assert next(u for u in troops.active(row) if u['person_id']==old)['phase']=='returning'


def test_relocation_leaves_old_building_and_uses_actual_arrival(setup):
    e,g=setup;g,row=assigned(e,g);g=construct(e,g,row);row=rules.offices(g)[0];old=copy.deepcopy(rules.building(g,row))
    g,_=command(e,g,'return',office=row['id']);row=rules.offices(g)[0]
    city=next(c for c in rules.cities(g) if c['id']!=row['city_id'])
    g.player.location_id=military.CAPITAL;e.store.save(g);g=act(e,g,'move_request',destination=city['id'])
    with pytest.raises(ValueError,match='抵达'):act(e,g,'move_complete')
    g.player.location_id=city['address']['location_id'];e.store.save(g);g=act(e,g,'move_complete');row=rules.offices(g)[0]
    assert row['city_id']==city['id'] and rules.building(g,row) is None
    assert g.building_state['records'][old['id']]==old
    assert balance(g,row['wallet'])==0;GameState.from_dict(g.to_dict())


def test_stale_protocol_request_no_second_debit(setup):
    e,g=setup;g,row=assigned(e,g);authority.fund(g,row,rules.SOURCE,10000);e.store.save(g)
    g=e._load(g.id);payload=json.dumps(dict(action='protocol',office=row['id'],token=rules.token(g),operation='divert',amount=1000))
    e.upper_institution_action(g.id,'governorship',payload)
    snapshot=hashlib.sha256(e.store._path(g.id).read_bytes()).digest()
    with pytest.raises(ValueError):e.upper_institution_action(g.id,'governorship',payload)
    assert hashlib.sha256(e.store._path(g.id).read_bytes()).digest()==snapshot


def test_crown_succession_does_not_capture_provincial_property(setup):
    e,g,row,people=prepared(setup,1)
    old=military.king_id(g);governor=local_people(g,row,1)[0];row['holder']=row['controller']=governor.id
    before=copy.deepcopy(row['owner']);wallet=balance(g,row['wallet'])
    settlement.succession(g,old,'player')
    assert council.book(row)['recognition']==old and council.book(row)['cases'][0]['kind']=='integration'
    assert row['owner']==before and row['holder']==governor.id and balance(g,row['wallet'])==wallet
    GameState.from_dict(g.to_dict())
    # Real original king transition and original-command provincial acceptance.
    from cultivation_life.system.asura_court import change_rank
    change_rank(g,rules.court(g),5);e.store.save(g)
    c=next(c for c in council.book(row)['cases'] if c['kind']=='integration')
    source=balance(g,rules.SOURCE)
    g=act(e,g,'integrate',case=c['id'],amount=1000000);row=rules.offices(g)[0]
    assert council.book(row)['recognition']=='player' and row['holder']==governor.id
    assert balance(g,rules.SOURCE)==source-1000000 and balance(g,row['wallet'])==wallet+1000000
    with pytest.raises(ValueError):act(e,g,'integrate',case=c['id'],amount=1000000)


def test_alliance_escrow_real_armies_and_break_refund(setup):
    e,g,row,_=prepared(setup,1)
    people=local_people(g,row,2);governor,guard=people
    city=next(c for c in rules.cities(g) if c['id']!=row['city_id'])
    other=authority.create(g,identity='asura-prefecture:'+city['id'],provider=rules.ID,name='盟府',world='asura',location=city['address']['location_id'],owner=row['owner'],source=rules.SOURCE,building_id='office:ally',city_id=city['id'])
    governor.location_id=guard.location_id=other['location']
    authority.nominate(g,other,governor.id,500);authority.assume(g,other,governor.id,'asura',other['location'])
    authority.fund(g,other,rules.SOURCE,10**8);troops.enlist(g,other,guard.id,1000);troops.provision(g,other,10**7)
    politics.remember(g,governor.id,'player',20,'已有共同履约',other['id'])
    g.player.location_id=other['location']
    from cultivation_life.rules import add_item
    add_item(g.player,'spirit_stone',100000);e.store.save(g)
    purse=balance(g,'player');g=act(e,g,'ally',target=other['id'],amount=30000)
    row=rules.offices(g)[0];c=council.book(row)['cases'][0]
    assert balance(g,c['facts']['wallet'])==30000 and balance(g,'player')==purse-30000
    GameState.from_dict(g.to_dict())
    with pytest.raises(ValueError):act(e,g,'ally_march',case=c['id'])
    g.player.location_id=row['location'];support(g,row);e.store.save(g)
    g=order(e,g,row,'rebel');row=rules.offices(g)[0];allied=settlement.allies(g,row)
    assert len(allied)==1 and allied[0]['controller']==governor.id and allied[0]['status']=='handover'
    assert troops.active(allied[0])[0]['destination']==other['location']
    from cultivation_life.relationship_records import find_person
    from cultivation_life.system.asura_governorship import military_combat
    ally_governor=find_person(g,governor.id);original=ally_governor.location_id
    ally_governor.location_id=military.CAPITAL
    assert governor.id not in {n.id for n in military_combat.defenders(g,row,military.CAPITAL,military)}
    ally_governor.location_id=original
    from cultivation_life.system.asura_governorship import management
    g.player.age+=1;management.advance(g,e.maps)
    assert settlement.allies(g,row)[0]['controller']==governor.id
    e.store.save(g)
    g=act(e,g,'ally_march',case=c['id']);row=rules.offices(g)[0]
    assert troops.active(settlement.allies(g,row)[0])[0]['phase']=='outbound'
    g=act(e,g,'ally_break',case=c['id']);row=rules.offices(g)[0]
    assert not settlement.allies(g,row) and balance(g,c['facts']['wallet'])==0 and balance(g,'player')==purse
    GameState.from_dict(g.to_dict())
    with pytest.raises(ValueError):act(e,g,'ally_break',case=c['id'])


def test_bound_array_uses_original_nodes_repair_and_withdrawal(setup):
    e,g=setup;g,row=assigned(e,g);g=construct(e,g,row)
    from cultivation_life.system.formation_system import formation_material_definitions,make_formation_material_instance
    definitions=formation_material_definitions()
    material=[d for d in definitions.values() if d['world']=='asura'][:3]
    instances=[make_formation_material_instance(d,source='隔离验收',origin_world='asura') for d in material]
    g.player.formation_materials.extend(instances);e.store.save(g)
    e.save_formation(g.id,dict(name='府署原阵',slots=[r['id'] for r in instances]+[None]*6,activate=True))
    e.deploy_ground_formation(g.id,'player');g=e.store.load(g.id);array=g.player.formation_ground_arrays[0]
    g=act(e,g,'guard_bind',target=array['id']);row=rules.offices(g)[0]
    from cultivation_life.system import institution_arrays as arrays
    assert arrays.current(g,row) is g.player.formation_ground_arrays[0]
    before=arrays.defence(g,row);assert before>0
    arrays.wear(g,row);assert arrays.current(g,row)['durability']==90
    from cultivation_life.content_registry import CONTENT_DOCUMENTS
    supply=next(d for d in CONTENT_DOCUMENTS['formations.json']['maintenance_resources'] if d['world']=='asura')
    g.player.formation_repair_supplies[supply['id']]=1;e.store.save(g)
    g=act(e,g,'guard_repair',target=supply['id']);assert not g.player.formation_repair_supplies.get(supply['id'])
    e.withdraw_ground_formation(g.id,array['id']);g=e.store.load(g.id);row=rules.offices(g)[0]
    assert arrays.current(g,row) is None and arrays.defence(g,row)==0
    GameState.from_dict(g.to_dict())

"""Actual people, finite money, roads and crown transfer under hostile requests."""
import copy
import json
import pytest
from test_asura_governorship import setup,assigned,construct,command
from cultivation_life.models import GameState
from cultivation_life.system.asura_governorship import rules,military as m,management
from cultivation_life.system import institution_garrisons as troops,institution_authority as authority
from cultivation_life.system.economy.ledger import balance
from cultivation_life.person_assignments import research_assignment


def recruit(e,g,count=2):
    row=rules.offices(g)[0]
    people=[n for n in g.sects[rules.COURT].npcs if n.id!=m.king_id(g)][:count]
    for n in people:n.location_id=row['location'];n.realm_index=max(9,n.realm_index)
    e.store.save(g)
    for n in people:g,_=command(e,g,'military',office=row['id'],operation='enlist',person=n.id)
    g,_=command(e,g,'military',office=row['id'],operation='provision',amount=10**8)
    return g,rules.offices(g)[0],people


def prepared(setup,count=2):
    e,g=setup;g,row=assigned(e,g);g=construct(e,g,row)
    g,row,people=recruit(e,g,count)
    return e,g,row,people


def order(e,g,row,op,**kw):return command(e,g,'military',office=row['id'],operation=op,**kw)[0]


def support(g,row):
    from cultivation_life.system.asura_governorship import politics
    for u in troops.active(row):politics.remember(g,u['person_id'],'player',20,'真实履约测试',row['id'])


def advance(g,e,row,years):
    for _ in range(years):g.player.age+=1;m.advance(g,e.maps,row)


def test_combined_defence_includes_seventh_high_realm_guard(setup,monkeypatch):
    from cultivation_life.system.asura_governorship import military_combat as battle
    e,g,row,allies=prepared(setup,1)
    guards=[n for s in g.sects.values() for n in s.npcs
            if n.id not in {allies[0].id,m.king_id(g)}][:7]
    assert len(guards)==7
    guards[-1].realm_index=12
    offices=[row,dict(id='defence-one'),dict(id='defence-two')]
    monkeypatch.setattr(rules,'offices',lambda game:offices)
    monkeypatch.setattr(troops,'stationed',lambda game,scope,location:
        [dict(person_id=n.id) for n in (guards[:6] if scope['id']=='defence-one' else guards[6:])])
    defending=battle.defenders(g,row,row['location'],m)
    assert {n.id for n in defending}=={n.id for n in guards}
    assert guards[-1] in defending


def test_local_defeat_does_not_recall_unengaged_other_garrison(setup,monkeypatch):
    from types import SimpleNamespace
    from cultivation_life.system.asura_governorship import military_combat as battle
    e,g,row,allies=prepared(setup,1)
    guards=[n for s in g.sects.values() for n in s.npcs if n.id not in {allies[0].id,m.king_id(g)}][:2]
    other=dict(id='split-defence',world='asura',garrison=dict(units=[
        dict(person_id=guards[0].id,phase='stationed'),dict(person_id=guards[1].id,phase='stationed')]))
    support(g,row);m.raise_banner(g,row,'player')
    monkeypatch.setattr(rules,'offices',lambda game:[row,other])
    monkeypatch.setattr(battle,'defenders',lambda *args:[guards[0]])
    monkeypatch.setattr(battle,'resolve_local_engagement',lambda *args,**kwargs:SimpleNamespace(outcome='victory'))
    moved=[]
    monkeypatch.setattr(troops.movement,'recall',lambda game,maps,unit,world:moved.append(unit['person_id']))
    monkeypatch.setattr(authority,'log',lambda *args:None)
    battle.skirmish(g,e.maps,row,row['location'],m)
    assert moved==[guards[0].id]
    assert guards[1].id not in moved


def test_garrison_is_original_occupied_and_views_are_pure(setup):
    e,g,row,people=prepared(setup)
    assert len(troops.active(row))==2
    assert all(research_assignment(g,n.id)['id']=='garrison:'+row['id'] for n in people)
    before=copy.deepcopy(g.to_dict());m.public(g,row);m.public(g,row)
    assert g.to_dict()==before
    assert GameState.from_dict(g.to_dict()).economy_v2==g.economy_v2
    with pytest.raises(ValueError):order(e,g,row,'enlist',person=people[0].id)
    from cultivation_life.system.war.occupancy import busy
    assert busy(g,g.sects[rules.COURT])
    with pytest.raises(ValueError):command(e,g,'staff',office=row['id'],person=people[0].id)


def test_route_arrival_once_and_original_funds_conserved(setup):
    e,g,row,people=prepared(setup)
    source=g.player.location_id;units,journeys,cost=troops.plan(g,e.maps,row,m.CAPITAL)
    assert cost>0 and max(j['years'] for j in journeys)>0
    g=order(e,g,row,'dispatch',destination=m.CAPITAL);row=rules.offices(g)[0]
    assert g.player.location_id==source and not troops.stationed(g,row,m.CAPITAL)
    old=balance(g,troops.state(row)['wallet']);rates=sum(u['rate'] for u in troops.active(row))
    advance(g,e,row,1);assert balance(g,troops.state(row)['wallet'])==old-rates
    snapshot=copy.deepcopy(g.to_dict());m.advance(g,e.maps,row);assert g.to_dict()==snapshot
    advance(g,e,row,max(u['remaining'] for u in troops.active(row)))
    assert len(troops.stationed(g,row,m.CAPITAL))==2
    assert all(g.sects[rules.COURT].npcs[[n.id for n in g.sects[rules.COURT].npcs].index(n.id)].location_id==m.CAPITAL for n in people)
    e.store.save(g);g=order(e,g,row,'recall');row=rules.offices(g)[0]
    advance(g,e,row,max(u['remaining'] for u in troops.active(row))+1)
    assert not troops.active(row)
    root=troops.state(row);assert root['paid']==root['spent']+root['returned'] and root['returned']>0
    snapshot=copy.deepcopy(g.to_dict());m.advance(g,e.maps,row);assert g.to_dict()==snapshot


def test_interrupted_march_retraces_elapsed_distance(setup):
    e,g,row,_=prepared(setup,1)
    g=order(e,g,row,'dispatch',destination=m.CAPITAL);row=rules.offices(g)[0]
    advance(g,e,row,1);e.store.save(g);g=order(e,g,row,'recall');row=rules.offices(g)[0]
    u=troops.active(row)[0];assert u['remaining']==1 and u['phase']=='returning'
    assert research_assignment(g,u['person_id'])
    advance(g,e,row,1);assert not troops.active(row)


def test_atomic_insufficient_budget_forged_destination_and_stale_token(setup):
    e,g,row,_=prepared(setup,1)
    snapshot=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError):order(e,g,row,'dispatch',destination='celestial')
    assert snapshot==e.store._path(g.id).read_bytes()
    payload=dict(action='military',operation='recall',office=row['id'],token=rules.token(g))
    g=order(e,g,row,'provision',amount=100)
    snapshot=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError):e.upper_institution_action(g.id,'governorship',json.dumps(payload))
    assert snapshot==e.store._path(g.id).read_bytes()


def test_orders_have_justified_delay_refusal_and_real_dispatch(setup):
    e,g,row,_=prepared(setup,1)
    m.issue(g,row,m.CAPITAL);e.store.save(g)
    g=order(e,g,row,'respond',choice='delay');row=rules.offices(g)[0]
    assert m.state(row)['order']['status']=='delayed'
    with pytest.raises(ValueError):order(e,g,row,'respond',choice='delay')
    g=order(e,g,row,'respond',choice='refuse');row=rules.offices(g)[0]
    assert m.state(row)['order']['status']=='refused'
    assert row['holder']=='player' and not m.fighting(row)
    g=order(e,g,row,'respond',choice='comply');row=rules.offices(g)[0]
    assert m.state(row)['order']['status']=='accepted'
    assert not troops.stationed(g,row,row['location'])
    advance(g,e,row,max(u['remaining'] for u in troops.active(row)))
    assert m.state(row)['order']['status']=='fulfilled'


def test_rebellion_requires_actual_support_and_not_a_free_crown(setup):
    e,g,row,_=prepared(setup)
    with pytest.raises(ValueError):order(e,g,row,'rebel')
    king=m.king_id(g);support(g,row);e.store.save(g)
    g=order(e,g,row,'rebel');row=rules.offices(g)[0]
    assert row['status']=='handover' and row['controller']=='player' and row['holder'] is None
    assert m.king_id(g)==king and m.fighting(row)
    with pytest.raises(ValueError):order(e,g,row,'claim')
    with pytest.raises(ValueError):e.upper_institution_action(g.id,'blood_duel')
    with pytest.raises(ValueError):command(e,g,'resign',office=row['id'])
    g=order(e,g,row,'standdown');row=rules.offices(g)[0]
    assert m.conflict(row)['status']=='withdrawn' and m.king_id(g)==king
    assert row['status']=='handover'


def at_capital(e,g,row):
    support(g,row);e.store.save(g);g=order(e,g,row,'rebel');row=rules.offices(g)[0]
    g=order(e,g,row,'dispatch',destination=m.CAPITAL);row=rules.offices(g)[0]
    advance(g,e,row,max(u['remaining'] for u in troops.active(row)))
    # Test placement of player only; production military commands never move them.
    g.player.location_id=m.CAPITAL;e.store.save(g)
    return g,row


def test_crown_needs_real_resistance_outcome_and_single_receipt(setup,monkeypatch):
    e,g,row,_=prepared(setup);g,row=at_capital(e,g,row)
    # Remove available guards from this isolated battlefield, not the old king.
    for n in g.sects[rules.COURT].npcs:
        if n.id!=m.king_id(g) and n.id not in {u['person_id'] for u in troops.active(row)}:n.location_id=row['location']
    e.store.save(g);g=order(e,g,row,'assault');row=rules.offices(g)[0]
    old=m.king_id(g);assert old!='player' and m.CAPITAL in m.conflict(row)['controlled']
    with pytest.raises(ValueError):order(e,g,row,'assault')
    # Inject only combat outcome to audit the crown transaction independently.
    monkeypatch.setattr(e,'_combat',lambda *args:('stalemate','未决'))
    g=order(e,g,row,'claim');row=rules.offices(g)[0];assert m.king_id(g)==old
    g.player.age+=10;e.store.save(g)
    monkeypatch.setattr(e,'_combat',lambda *args:('victory','原斗法胜出'))
    g=order(e,g,row,'claim');row=rules.offices(g)[0]
    assert m.king_id(g)=='player' and m.conflict(row)['status']=='won'
    assert g.upper_institutions['asura']['rank']==5
    assert sum(v=='player' for v in rules.court(g)['court']['holders'].values())==1
    with pytest.raises(ValueError):order(e,g,row,'claim')
    assert row['controller']=='player' and row['holder'] is None


def test_absent_king_and_departed_troops_cannot_give_remote_victory(setup):
    e,g,row,_=prepared(setup);g,row=at_capital(e,g,row)
    m.conflict(row)['controlled']=[m.CAPITAL]
    king=next(n for n in g.sects[rules.COURT].npcs if n.id==m.king_id(g));king.location_id=row['location'];e.store.save(g)
    with pytest.raises(ValueError,match='旧王'):order(e,g,row,'claim')
    for u in troops.active(row):
        n=next(n for n in g.sects[rules.COURT].npcs if n.id==u['person_id']);n.location_id=row['location']
    e.store.save(g)
    with pytest.raises(ValueError):order(e,g,row,'claim')


def test_disabled_content_keeps_expense_and_allows_real_return(setup,monkeypatch):
    e,g,row,_=prepared(setup);g=order(e,g,row,'dispatch',destination=m.CAPITAL);row=rules.offices(g)[0]
    advance(g,e,row,1);e.store.save(g)
    monkeypatch.setattr(m,'enabled',lambda:False)
    with pytest.raises(ValueError):order(e,g,row,'provision',amount=1000)
    g=order(e,g,row,'recall');row=rules.offices(g)[0]
    advance(g,e,row,2);assert not troops.active(row) and troops.state(row)['spent']>0


@pytest.mark.parametrize('attack',['duplicate','cash','time','player','campaign'])
def test_forged_persistent_records_rejected(setup,attack):
    e,g,row,_=prepared(setup);payload=g.to_dict();scope=payload['economy_v2']['administrations'][row['id']]
    if attack=='duplicate':scope['garrison']['units'].append(copy.deepcopy(scope['garrison']['units'][0]))
    elif attack=='cash':scope['garrison']['paid']+=1
    elif attack=='time':scope['garrison']['units'][0]['remaining']=-1
    elif attack=='player':scope['garrison']['units'][0]['person_id']='player'
    else:scope['asura_military']['conflict']={'status':'won'}
    with pytest.raises(ValueError):GameState.from_dict(payload)


def test_actual_high_domain_cannot_be_overridden_by_headcount():
    import random
    from dataclasses import asdict
    from test_domain_combat import voisinage,state
    from cultivation_life.models import SectNpc
    from cultivation_life.system.combat.npc_battle import resolve_local_engagement
    from cultivation_life.system.npc_strength import power
    # Use actual original cultivation strength, not an invented army multiplier.
    weak=[SectNpc('weak-'+str(i),'低阶部众','',8,1,1000,None) for i in range(6)]
    strong=SectNpc('strong','高阶修士','',9,1,1000,None,transcendence=state())
    before=strong.transcendence['current']
    result=resolve_local_engagement([(n,power(n)) for n in weak],[(strong,power(strong))],
        {'voisinages':[asdict(voisinage())]},random.Random(3))
    assert result.outcome in {'defeat','stalemate'} # finite-round resistance is not an army victory
    assert strong.transcendence['current']<before
    assert result.rounds


@pytest.mark.parametrize('seed',[1,5,17])
def test_large_cultivation_gap_beats_six_real_lower_units(seed):
    import random
    from cultivation_life.models import SectNpc
    from cultivation_life.system.npc_strength import power
    from cultivation_life.system.combat.npc_battle import resolve_local_engagement
    weak=[SectNpc('weak-'+str(i),'低阶部众','',8,1,1000,None) for i in range(6)]
    high=SectNpc('high','高阶修士','',12,9,1000,None)
    result=resolve_local_engagement([(n,power(n)) for n in weak],[(high,power(high))],{},random.Random(seed))
    assert result.outcome=='defeat'


def test_actual_crown_combat_writes_original_report_and_resources(setup):
    e,g,row,_=prepared(setup);g,row=at_capital(e,g,row)
    m.conflict(row)['controlled']=[m.CAPITAL];e.store.save(g)
    old=m.king_id(g);before=copy.deepcopy(g.player.transcendence)
    g=order(e,g,row,'claim');row=rules.offices(g)[0]
    assert g.last_combat_report and g.last_combat_report['rounds']
    assert m.state(row)['last_battle']==g.player.age
    assert g.player.transcendence!=before or g.player.hp<g.last_combat_report.get('player_start_hp',float('inf'))
    assert m.king_id(g)==old or m.conflict(row)['status']=='won'


def test_npc_refusal_enforcement_marches_original_commander_and_can_take_abdication(setup):
    from cultivation_life.system.asura_court import change_rank
    from cultivation_life.system.asura_governorship import politics
    e,g=setup;g,row=assigned(e,g);g=construct(e,g,row);row=rules.offices(g)[0]
    authority.relinquish(g,row,'player');change_rank(g,rules.court(g),5)
    candidates=[n for n in g.sects[rules.COURT].npcs if n.id!=m.king_id(g)][:2]
    chief,soldier=candidates
    for n in candidates:n.location_id=row['location']
    authority.nominate(g,row,chief.id,500);authority.assume(g,row,chief.id,'asura',row['location'])
    troops.enlist(g,row,soldier.id,1000);troops.provision(g,row,10**8)
    politics.remember(g,soldier.id,chief.id,20,'原提拔及履约支持',row['id']);m.ensure(row)
    g.player.location_id=m.CAPITAL;e.store.save(g)
    g=order(e,g,row,'order',destination=m.CAPITAL);row=rules.offices(g)[0]
    m.answer(g,e.maps,row,'refuse');e.store.save(g)
    g=order(e,g,row,'press');row=rules.offices(g)[0]
    assert row['holder'] is None and row['controller']==chief.id
    advance(g,e,row,1);assert m.fighting(row) and m.conflict(row)['claimant']==chief.id
    advance(g,e,row,1)
    assert all(u['phase']=='outbound' for u in troops.active(row))
    assert find_local(g,chief.id).location_id==row['location']
    advance(g,e,row,max(u['remaining'] for u in troops.active(row)))
    assert find_local(g,chief.id).location_id==m.CAPITAL
    e.store.save(g);g=order(e,g,row,'abdicate');row=rules.offices(g)[0]
    assert m.king_id(g)==chief.id and m.conflict(row)['status']=='won'
    assert g.upper_institutions['asura']['rank']==0


def find_local(g,identity):
    from cultivation_life.relationship_records import find_person
    return find_person(g,identity)


def test_missing_funds_future_year_and_foreign_region_do_not_advance(setup):
    from cultivation_life.regional_context import CalendarGame
    e,g,row,_=prepared(setup)
    root=troops.state(row)
    from cultivation_life.system.economy.ledger import transfer_value
    amount=balance(g,root['wallet']);transfer_value(g,root['wallet'],row['wallet'],amount,'隔离测试原预算退回');root['returned']+=amount
    e.store.save(g);snapshot=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError,match='经费'):order(e,g,row,'dispatch',destination=m.CAPITAL)
    assert snapshot==e.store._path(g.id).read_bytes()
    before=copy.deepcopy(g.to_dict());troops.advance(g,e.maps,row);assert g.to_dict()==before
    future=CalendarGame(g,'asura',g.player.age-10);m.advance(future,e.maps,row);assert g.to_dict()==before
    foreign=CalendarGame(g,'celestial',g.player.age+1);troops.advance(foreign,e.maps,row);assert g.to_dict()==before
    advance(g,e,row,3);assert not troops.active(row) # shortfall at home releases original people


def test_occupied_or_dead_person_never_teleports_and_invalidates_force(setup):
    e,g,row,people=prepared(setup,1);g=order(e,g,row,'dispatch',destination=m.CAPITAL);row=rules.offices(g)[0]
    person=find_local(g,people[0].id);person.alive=False
    origin=person.location_id;advance(g,e,row,1)
    assert person.location_id==origin and not troops.active(row)
    assert not research_assignment(g,person.id)
    assert troops.state(row)['returned']>0


def test_npc_king_can_issue_and_enforce_real_order_without_ui_calls(setup):
    e,g,row,_=prepared(setup,2)
    # Actual capital guard shortage, with two original provincial retainers.
    for n in g.sects[rules.COURT].npcs:
        if n.id!=m.king_id(g) and n.id not in {u['person_id'] for u in troops.active(row)}:n.location_id=row['location']
    g.player.age+=100;m.advance(g,e.maps,row)
    assert m.state(row)['order']['status']=='issued'
    assert m.state(row)['order']['issuer']==m.king_id(g)
    m.answer(g,e.maps,row,'refuse')
    g.player.age=m.state(row)['order']['deadline']+m.config()['order_years'];m.advance(g,e.maps,row)
    assert row['status']=='handover' and row['holder'] is None
    assert m.state(row)['order']['status']=='enforced'


def test_actual_calendar_advances_base_garrison_once(setup):
    e,g,row,_=prepared(setup,1);before=balance(g,troops.state(row)['wallet'])
    e.store.save(g);e.advance(g.id,'rest',1)
    loaded=e.store.load(g.id);scope=rules.offices(loaded)[0];root=troops.state(scope)
    assert loaded.player.age>g.player.age and root['last_year']>g.player.age
    assert root['spent']>0 and balance(loaded,root['wallet'])<before
    assert root['paid']==root['spent']+root['returned']+balance(loaded,root['wallet'])


def test_disabled_npc_uprising_finishes_original_handover(setup,monkeypatch):
    from cultivation_life.system.asura_governorship import politics
    e,g=setup;g,row=assigned(e,g);g=construct(e,g,row);row=rules.offices(g)[0]
    authority.relinquish(g,row,'player')
    chief,soldier=[n for n in g.sects[rules.COURT].npcs if n.id!=m.king_id(g)][:2]
    for n in (chief,soldier):n.location_id=row['location']
    authority.nominate(g,row,chief.id,500);authority.assume(g,row,chief.id,'asura',row['location'])
    troops.enlist(g,row,soldier.id,1000);troops.provision(g,row,10**8)
    politics.remember(g,soldier.id,chief.id,20,'原履约支持',row['id'])
    m.raise_banner(g,row,chief.id);assert m.fighting(row)
    monkeypatch.setattr(m,'enabled',lambda:False)
    advance(g,e,row,3)
    assert m.conflict(row)['status']=='withdrawn' and row['status']=='vacant'
    assert not troops.active(row) and troops.state(row)['returned']>0


def test_king_cannot_attack_departure_address_of_marching_commander(setup):
    from cultivation_life.system.asura_court import change_rank
    from cultivation_life.system.asura_governorship import politics
    e,g=setup;g,row=assigned(e,g);g=construct(e,g,row);row=rules.offices(g)[0]
    authority.relinquish(g,row,'player');change_rank(g,rules.court(g),5)
    chief,soldier=g.sects[rules.COURT].npcs[:2]
    for n in (chief,soldier):n.location_id=row['location']
    authority.nominate(g,row,chief.id,500);authority.assume(g,row,chief.id,'asura',row['location'])
    troops.enlist(g,row,soldier.id,1000);troops.provision(g,row,10**8)
    politics.remember(g,soldier.id,chief.id,20,'原履约支持',row['id']);m.raise_banner(g,row,chief.id)
    troops.dispatch(g,e.maps,row,m.CAPITAL);e.store.save(g)
    assert m.public(g,row) is not None # actual king at the original provincial site
    with pytest.raises(ValueError,match='行军'):order(e,g,row,'pacify')


def test_initial_year_is_not_a_previous_battle(monkeypatch):
    from types import SimpleNamespace
    from cultivation_life.system.asura_governorship.military_combat import cooldown
    monkeypatch.setattr(m,'config',lambda:dict(battle_years=10))
    game=SimpleNamespace(player=SimpleNamespace(age=0));row={'asura_military':{'last_battle':-1}}
    cooldown(game,row,m)
    row['asura_military']['last_battle']=0;game.player.age=5
    with pytest.raises(ValueError):cooldown(game,row,m)
    game.player.age=10;cooldown(game,row,m)


def test_unaffiliated_legacy_war_member_cannot_be_recruited(setup):
    e,g=setup;g,row=assigned(e,g);g=construct(e,g,row);row=rules.offices(g)[0]
    npc=next(n for n in g.sects[rules.COURT].npcs if n.id!=m.king_id(g));npc.location_id=row['location'];npc.faction_id=None
    g.wars.append(dict(id='legacy-test',status='active',roster={'attacker':[npc.id]}))
    snapshot=copy.deepcopy(g.to_dict())
    with pytest.raises(ValueError,match='旧战役'):troops.enlist(g,row,npc.id,1000)
    assert g.to_dict()==snapshot

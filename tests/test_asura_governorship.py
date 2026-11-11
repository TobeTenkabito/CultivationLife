"""Original appointments, public property, finite funds and stale command attacks."""
import copy
import json
from pathlib import Path
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.system import institution_authority as authority
from cultivation_life.system.asura_governorship import rules,actions,management,presentation
from cultivation_life.system.institution_ai import rules as agendas,runtime
from cultivation_life.system.economy.ledger import balance,transfer_value
from cultivation_life.system.economy.state import ensure_regional_market
from cultivation_life.system.building_destruction import destroy
from cultivation_life.system.building_assets import local_rows
from cultivation_life.person_assignments import research_assignment

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    e=GameEngine(ROOT,tmp_path)
    made=e.create_game('外任对抗','supreme_metal','demonic',371,preset_id='asura_upper')
    e.upper_institution_action(made['id'],'join')
    g=e._load(made['id']);g.pending_event=None;g.active_trial=None
    state=g.upper_institutions['asura']
    from cultivation_life.system.asura_court import change_rank
    change_rank(g,state,1)
    state.update(earned=100,regard=60,treasury=10**12)
    e.store.save(g)
    return e,g


def command(e,g,action,**payload):
    current=e._load(g.id)
    result=e.upper_institution_action(g.id,'governorship',json.dumps(dict(action=action,token=rules.token(current),**payload)))
    return e.store.load(g.id),result


def assigned(e,g):
    city=rules.cities(g)[0]
    g,_=command(e,g,'request',city=city['id'])
    row=rules.offices(g)[0]
    # Isolated test placement; production appointment never changes any address.
    g.player.location_id=row['location'];g.pending_event=None
    ensure_regional_market(g,e.maps,'asura',row['location'])
    e.store.save(g)
    g,_=command(e,g,'assume',office=row['id'])
    return g,rules.offices(g)[0]


def fund_fixture(e,g,row):
    authority.fund(g,row,rules.SOURCE,10**11)
    e.store.save(g)


def construct(e,g,row):
    fund_fixture(e,g,row)
    current=e._load(g.id);row=rules.offices(current)[0];q=actions.bill(current,row)
    assert not q['reason'],q
    return command(e,g,'build',office=row['id'],quote=q['token'],total=q['total'])[0]


def test_appointment_never_moves_or_mints_and_views_pure(setup):
    e,g=setup;before=g.player.location_id;funds=balance(g,rules.SOURCE)
    g,_=command(e,g,'request',city=rules.cities(g)[0]['id'])
    row=rules.offices(g)[0]
    assert g.player.location_id==before and row['status']=='appointed'
    assert balance(g,row['wallet'])==0 and balance(g,rules.SOURCE)==funds
    assert rules.building(g,row) is None
    snapshot=copy.deepcopy(g.to_dict())
    presentation.public(g);presentation.public(g)
    assert g.to_dict()==snapshot
    with pytest.raises(ValueError,match='亲赴'):
        command(e,g,'assume',office=row['id'])
    assert GameState.from_dict(g.to_dict()).economy_v2==g.economy_v2


def test_real_building_costs_stale_price_and_ownership(setup):
    e,g=setup;g,row=assigned(e,g);fund_fixture(e,g,row)
    g=e._load(g.id);row=rules.offices(g)[0];q=actions.bill(g,row)
    before=balance(g,row['wallet']);market=g.economy_v2['markets']['asura:'+row['location']]
    stocks={k:market['commodities'][k]['stock'] for k in q['materials']}
    snapshot=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError,match='报价'):
        command(e,g,'build',office=row['id'],quote=q['token'],total=q['total']+1)
    assert e.store._path(g.id).read_bytes()==snapshot
    g,_=command(e,g,'build',office=row['id'],quote=q['token'],total=q['total'])
    row=rules.offices(g)[0];building=rules.building(g,row)
    assert building['owner']==row['owner'] and building['owner']['kind']=='sect'
    assert building['status']=='intact' and building in local_rows(g)
    assert before-balance(g,row['wallet'])==q['total']
    for k,n in q['materials'].items():
        assert g.economy_v2['markets']['asura:'+row['location']]['commodities'][k]['stock']==stocks[k]-n
    with pytest.raises(ValueError):command(e,g,'build',office=row['id'],quote=q['token'],total=q['total'])


def test_revocation_invalidates_old_ui_but_preserves_assets(setup):
    e,g=setup;g,row=assigned(e,g);g=construct(e,g,row);row=rules.offices(g)[0]
    payload=dict(action='donate',office=row['id'],amount=1,token=rules.token(g))
    money=balance(g,row['wallet']);authority.revoke(g,row);e.store.save(g)
    assert row['controller']=='player' and row['holder'] is None
    with pytest.raises(ValueError,match='已变化'):
        e.upper_institution_action(g.id,'governorship',json.dumps(payload))
    with pytest.raises(ValueError,match='授权'):
        command(e,g,'donate',office=row['id'],amount=1)
    g,_=command(e,g,'resign',office=row['id']);row=rules.offices(g)[0]
    assert row['status']=='vacant' and balance(g,row['wallet'])==money and rules.building(g,row)['status']=='intact'


def test_original_npc_project_escrow_and_expiry_handover(setup):
    e,g=setup;g,row=assigned(e,g);g=construct(e,g,row);row=rules.offices(g)[0]
    npc=g.sects[rules.COURT].npcs[-1];npc.location_id=row['location'];npc.realm_index=9
    assert npc.id in {p['id'] for p in rules.eligible_people(g,row)}
    row['people']=[npc.id]
    destroy(g,rules.building(g,row),source='war')
    scope=management.scopes(g,e.maps)[0];offer=management.offers(g,e.maps,scope)[0]
    job=runtime.start(g,scope,offer,npc.id,adapter=management)
    assert research_assignment(g,npc.id)['id']==job['id']
    cash=balance(g,job['wallet']);saved=copy.deepcopy(g.to_dict())
    management.public(g);assert g.to_dict()==saved
    npc.location_id='ten_thousand_battle_city';g.player.age+=1;management.advance(g,e.maps)
    assert job['progress']==0 and balance(g,job['wallet'])==cash
    npc.location_id=row['location']
    for _ in range(10):g.player.age+=1;management.advance(g,e.maps)
    receipt=agendas.record(g,row['id'])['history'][-1]
    assert receipt['status']=='completed' and receipt['funded']==receipt['spent']+receipt['refunded']
    assert rules.building(g,row)['status']=='intact'
    assert GameState.from_dict(g.to_dict()).economy_v2==g.economy_v2
    g.player.age=row['expires'];management.advance(g,e.maps)
    assert row['status']=='handover' and row['controller']=='player'


def test_disabled_dlc_allows_only_accountable_handover(setup,monkeypatch):
    e,g=setup;g,row=assigned(e,g);fund_fixture(e,g,row)
    monkeypatch.setattr(rules,'enabled',lambda:False)
    with pytest.raises(ValueError,match='停用'):command(e,g,'build',office=row['id'])
    before=balance(g,rules.SOURCE);cash=balance(g,row['wallet'])
    g,_=command(e,g,'return',office=row['id'])
    assert balance(g,row['wallet'])==0 and balance(g,rules.SOURCE)==before+cash
    g,_=command(e,g,'resign',office=row['id'])
    assert rules.offices(g)[0]['status']=='vacant'


@pytest.mark.parametrize('amount',[True,-1,0,'100',10**16])
def test_invalid_money_no_mutation(setup,amount):
    e,g=setup;g,row=assigned(e,g);before=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError):command(e,g,'donate',office=row['id'],amount=amount)
    assert e.store._path(g.id).read_bytes()==before


def test_expired_cannot_renew_by_duplicate_appointment_or_leave(setup):
    e,g=setup;g,row=assigned(e,g)
    g.player.location_id='ten_thousand_battle_city';e.store.save(g)
    with pytest.raises(ValueError,match='交接'):e.upper_institution_action(g.id,'leave')
    g.player.location_id=row['location']
    g.player.age=row['expires'];e.store.save(g)
    with pytest.raises(ValueError,match='授权'):command(e,g,'donate',office=row['id'],amount=1)


def test_schema_rejects_duplicate_wallet_and_office_corruption(setup):
    e,g=setup;g,row=assigned(e,g)
    document=g.to_dict();document['economy_v2']['administrations'][row['id']]['wallet']='background:asura'
    with pytest.raises(ValueError,match='公款'):GameState.from_dict(document)


def test_vacant_throne_cannot_issue_appointments(setup):
    e,g=setup;g.upper_institutions['asura']['court']['holders']['5']=None;e.store.save(g)
    before=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError,match='修罗王'):command(e,g,'request',city=rules.cities(g)[0]['id'])
    assert e.store._path(g.id).read_bytes()==before


def test_private_city_is_not_a_crown_charter(setup):
    from cultivation_life.building_rules import ensure_state
    e,g=setup;city=copy.deepcopy(rules.cities(g)[0]);city['owner']=dict(kind='player',id=g.id)
    ensure_state(g)['records'][city['id']]=city;e.store.save(g)
    with pytest.raises(ValueError,match='许可'):command(e,g,'request',city=city['id'])
    assert not rules.offices(e.store.load(g.id))


def test_malformed_request_and_remote_authority_cannot_mutate(setup):
    e,g=setup;g,row=assigned(e,g);snapshot=e.store._path(g.id).read_bytes()
    for data in (dict(office=[]),dict(action={}),dict(person=[]),dict(action='management',payload=[])):
        payload=dict(action='donate',office=row['id'],amount=1,token=rules.token(e._load(g.id)))
        payload.update(data)
        with pytest.raises(ValueError):e.upper_institution_action(g.id,'governorship',json.dumps(payload))
        assert e.store._path(g.id).read_bytes()==snapshot
    g.player.world='celestial';e.store.save(g)
    with pytest.raises(ValueError):command(e,g,'donate',office=row['id'],amount=1)
    assert presentation.public(g) is None


def test_central_office_cannot_duplicate_provincial_responsibility(setup):
    from cultivation_life.system.asura_court import change_rank
    e,g=setup;g,row=assigned(e,g)
    npc=g.sects[rules.COURT].npcs[-1];row['people']=[npc.id]
    authority.relinquish(g,row,'player')
    authority.nominate(g,row,npc.id,500)
    g.player.location_id='ten_thousand_battle_city';change_rank(g,g.upper_institutions['asura'],5)
    e.store.save(g)
    with pytest.raises(ValueError,match='地方任职'):
        e.upper_institution_action(g.id,'appoint','treasury:'+npc.id)


def test_promotion_clears_pending_appointment_and_death_preserves_public_cash(setup):
    from cultivation_life.system.asura_court import change_rank
    e,g=setup;g,_=command(e,g,'request',city=rules.cities(g)[0]['id']);row=rules.offices(g)[0]
    change_rank(g,g.upper_institutions['asura'],5)
    assert row['status']=='vacant' and row['nominee'] is None
    npc=g.sects[rules.COURT].npcs[-1]
    authority.nominate(g,row,npc.id,500)
    authority.assume(g,row,npc.id,row['world'],row['location'])
    authority.fund(g,row,rules.SOURCE,1000)
    npc.alive=False;g.player.age+=1;management.advance(g,e.maps)
    assert row['status']=='vacant' and balance(g,row['wallet'])==1000
    assert GameState.from_dict(g.to_dict()).economy_v2==g.economy_v2


def test_king_appoints_funds_and_recalls_original_npc(setup):
    from cultivation_life.system.asura_court import change_rank
    e,g=setup;change_rank(g,g.upper_institutions['asura'],5)
    npc=g.sects[rules.COURT].npcs[-1];npc.realm_index=9
    city=rules.cities(g)[0];npc.location_id=city['address']['location_id'];e.store.save(g)
    g,_=command(e,g,'appoint',city=city['id'],person=npc.id);row=rules.offices(g)[0]
    assert row['status']=='appointed' and g.player.location_id=='ten_thousand_battle_city'
    original=balance(g,rules.SOURCE)
    g,_=command(e,g,'fund',office=row['id'],amount=1000);row=rules.offices(g)[0]
    assert balance(g,rules.SOURCE)==original-1000 and balance(g,row['wallet'])==1000
    g.player.age+=1;management.advance(g,e.maps);e.store.save(g)
    assert row['holder']==npc.id
    g,_=command(e,g,'revoke',office=row['id']);row=rules.offices(g)[0]
    assert row['status']=='handover'
    g.player.age+=1;management.advance(g,e.maps)
    assert row['status']=='vacant' and balance(g,row['wallet'])==1000

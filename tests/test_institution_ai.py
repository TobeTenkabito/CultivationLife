"""Base institutions work without DLC; adversarial budgets, people and receipts."""
import copy
from pathlib import Path
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.system.institution_ai import base,rules,runtime,commands
from cultivation_life.system.economy import organizations,depot
from cultivation_life.system.economy.state import ensure_regional_market
from cultivation_life.system.economy.ledger import balance,transfer_value
from cultivation_life.person_assignments import research_assignment
from cultivation_life.regional_context import CalendarGame

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def setup(tmp_path):
    e=GameEngine(ROOT,tmp_path);g=e._load(e.create_game('机构对抗','supreme_metal','dao',315,preset_id='core')['id'])
    faction=next(s for s in g.sects.values() if s.world=='human' and s.kind=='sect' and not s.extinct)
    g.pending_event=None;g.player.faction_id=faction.id;g.player.location_id=faction.location_id;faction.founded_by_player=True
    for n in faction.npcs:n.location_id=faction.location_id
    row=organizations.register(g,'sect',faction.id,'human');row['expected_upkeep']=0
    ensure_regional_market(g,e.maps,'human',faction.location_id)
    transfer_value(g,'background:human','organization:sect:'+faction.id,100000,'隔离验收原款')
    depot.ensure(g,faction)['stock'].clear()
    scope=next(s for s in base.scopes(g,e.maps) if s['identity']==faction.id)
    return e,g,scope

def begin(e,g,scope):
    offer=next(o for o in base.offers(g,e.maps,scope) if not o['reason'] and o['kind']=='supply')
    person=next(n for n in scope['people'] if not rules.person_reason(g,n,scope['world'],scope['location']))
    return runtime.start(g,scope,offer,person)

def test_original_goods_cash_person_and_roundtrip(setup):
    e,g,scope=setup;offer=base.offers(g,e.maps,scope)
    before=copy.deepcopy(g.to_dict());commands.public(g,e.maps,base);assert g.to_dict()==before
    job=begin(e,g,scope);assert research_assignment(g,job['person'])['id']==job['id']
    market=g.economy_v2['markets']['human:'+scope['location']];key=job['offer']['target'];item=next(iter(job['offer']['materials']))
    stock=market['commodities'][item]['stock'];count=job['offer']['quantity']
    for _ in range(job['years']):
        g.player.age+=1;runtime.advance(g,e.maps,base)
    row=rules.record(g,scope['id']);assert not row.get('job')
    receipt=row['history'][-1]
    assert receipt['funded']==receipt['spent']+receipt['refunded']
    assert market['commodities'][item]['stock']==stock-count
    buyers=market['competition'][item]['buyers']
    assert scope['payer'] in buyers and job['wallet'] not in buyers
    assert depot.find(g,base.entity_for(g,scope))['stock'][key]==count
    assert GameState.from_dict(g.to_dict()).economy_v2==g.economy_v2

def test_duplicate_year_and_npc_double_booking(setup):
    e,g,scope=setup;job=begin(e,g,scope);before=copy.deepcopy(g.to_dict())
    runtime.advance(g,e.maps,base);snapshot=copy.deepcopy(g.to_dict());runtime.advance(g,e.maps,base)
    assert g.to_dict()==snapshot and job['progress']==0
    with pytest.raises(ValueError):begin(e,g,scope)

def test_leaving_does_not_teleport_or_pay(setup):
    e,g,scope=setup;job=begin(e,g,scope)
    from cultivation_life.relationship_records import find_person
    n=find_person(g,job['person']);n.location_id='elsewhere';cash=balance(g,job['wallet'])
    g.player.age+=1;runtime.advance(g,e.maps,base)
    assert job['progress']==0 and job['blocked'] and balance(g,job['wallet'])==cash and n.location_id=='elsewhere'

@pytest.mark.parametrize('bad',[None,True,-1,'100',10**20])
def test_invalid_budget_rejected_atomically(setup,bad):
    e,g,scope=setup;data=next(r for r in commands.public(g,e.maps,base) if r['id']==scope['id'])
    before=copy.deepcopy(g.to_dict())
    with pytest.raises(ValueError):commands.command(g,e.maps,dict(action='institution_configure',scope=scope['id'],token=data['token'],policy='supply',limit=bad,automatic=False),base)
    # Command boundary is copy-on-write; no fiscal or actor mutation is permitted.
    assert g.player.to_dict()==before['player'] and g.economy_v2['accounts']==before['economy_v2']['accounts']

def test_foreign_region_does_not_advance_original_job(setup):
    e,g,scope=setup;job=begin(e,g,scope)
    runtime.advance(CalendarGame(g,'celestial',g.player.age+10),e.maps,base)
    assert job['progress']==0 and job['last_year']==job['started']
    row=rules.record(g,scope['id']);row.update(delegate=job['person'],automatic=True)
    runtime.advance(CalendarGame(g,'celestial',g.player.age+11),e.maps,base)
    assert row['delegate']==job['person'] and row['automatic']


def test_dlc_disabled_base_proposals_and_authorized_auto_work(setup):
    from unittest.mock import patch
    from cultivation_life.content_registry import WORLD_SYSTEMS
    e,g,scope=setup;person=scope['people'][0]
    data=next(r for r in commands.public(g,e.maps,base) if r['id']==scope['id'])
    commands.command(g,e.maps,dict(action='institution_configure',scope=scope['id'],token=data['token'],policy='supply',limit=100000,automatic=True,person=person),base)
    with patch.dict(WORLD_SYSTEMS['yaochi_westward'],enabled=False):runtime.advance(g,e.maps,base)
    row=rules.record(g,scope['id']);assert row['job']['automatic'] and row['job']['source']==scope['payer']
    assert row['job']['funded']<=row['limit'] and row['job']['person']==person


@pytest.mark.parametrize('cause',['dissolved','expired'])
def test_lost_authority_or_expiry_refunds_original_source_once(setup,cause):
    e,g,scope=setup;job=begin(e,g,scope);left=balance(g,job['wallet']);before=balance(g,scope['payer'])
    if cause=='dissolved':base.entity_for(g,scope).extinct=True;g.player.age+=1
    else:g.player.age=job['deadline']
    runtime.advance(g,e.maps,base)
    assert not rules.record(g,scope['id']).get('job') and balance(g,scope['payer'])==before+left
    assert not research_assignment(g,job['person'])
    saved=copy.deepcopy(g.to_dict());runtime.advance(g,e.maps,base);assert g.to_dict()==saved


@pytest.mark.parametrize('field',['funded','spent','progress'])
def test_forged_persistent_job_rejected(setup,field):
    e,g,scope=setup;job=begin(e,g,scope);job[field]=10**15
    with pytest.raises(ValueError):GameState.from_dict(g.to_dict())


@pytest.mark.parametrize('policy',[[],{},False,None])
def test_malformed_policy_is_domain_rejection(setup,policy):
    e,g,scope=setup;data=next(r for r in commands.public(g,e.maps,base) if r['id']==scope['id'])
    with pytest.raises(ValueError):commands.command(g,e.maps,dict(action='institution_configure',scope=scope['id'],token=data['token'],policy=policy,limit=0,automatic=False),base)


def test_original_institution_prisoner_cannot_be_delegated(setup):
    e,g,scope=setup;person=scope['people'][0];g.intrigue_state.setdefault('npc_prisons',{})[person]={'holder':'original'}
    assert rules.person_reason(g,person,scope['world'],scope['location'])

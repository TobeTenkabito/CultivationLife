import copy
import random
from pathlib import Path
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc
from cultivation_life.runtime import encode_rng
from cultivation_life.system.economy.organizations import welfare
from cultivation_life.system.economy.organization_accounts import register, key
from cultivation_life.system.economy.ledger import transfer_value

ROOT=Path(__file__).resolve().parents[1]
@pytest.fixture
def setup(tmp_path):
    e=GameEngine(ROOT,tmp_path/'saves')
    made=e.create_game('独立职务','supreme_metal','dao',300,custom_start=dict(world='human',realm_index=4,sect='new',sect_name='听松宗'))
    g=e._load(made['id']);sect=g.sects[g.player.faction_id]
    low=SectNpc('office_low','知微','弟子',1,1,20,200,world='human',faction_id=sect.id)
    high=SectNpc('office_high','守真','长老',5,1,200,1000,world='human',faction_id=sect.id)
    sect.npcs.extend([low,high]);record=e._ensure_intrigue_faction(g,'sect',sect.id)
    e.store.save(g)
    return e,g,sect,record,low,high


def test_controller_appoints_low_member_and_self_without_transferring_control(setup):
    e,g,sect,r,low,high=setup
    e.intrigue_personnel_action(g.id,'sect','appoint',low.id,'leader')
    loaded=e._load(g.id);row=e._ensure_intrigue_faction(loaded,'sect',sect.id)
    assert row['positions']['leader']==low.id and row['controller_id']=='player'
    assert not e._intrigue_has_decision_authority(loaded,'sect',sect.id,low.id)
    e.intrigue_personnel_action(g.id,'sect','appoint','player','leader')
    assert e._ensure_intrigue_faction(e._load(g.id),'sect',sect.id)['positions']['leader']=='player'


@pytest.mark.parametrize('guest_source',['guests','position'])
@pytest.mark.parametrize('route',['direct','vote'])
def test_guest_cannot_be_leader_even_if_in_member_roster(setup,guest_source,route):
    e,g,sect,r,low,high=setup
    if guest_source=='guests':r['guests'].append({'npc_id':low.id,'name':low.name,'defense_required':True,'offense_opt_in':False})
    else:r['positions']['guest_elder']=low.id
    e.store.save(g);e._load(g.id);before=e.store.load(g.id).to_dict()
    with pytest.raises(ValueError,match='客卿长老不得担任掌门'):
        if route=='direct':e.intrigue_personnel_action(g.id,'sect','appoint',low.id,'leader')
        else:e.intrigue_propose_resolution(g.id,'sect','replace_leader',low.id,True)
    assert e.store.load(g.id).to_dict()==before
    section=next(s for s in e.get_game(g.id)['intrigue_system']['sections'] if s['kind']=='sect')
    assert low.id not in {c['id'] for c in section['leader_candidates']}


@pytest.mark.parametrize('seed,expected',[(1,'passed'),(2,'rejected')])
def test_decision_member_votes_to_replace_leader_without_control(setup,seed,expected):
    e,g,sect,r,low,high=setup
    sect.founded_by_player=False;sect.founder_player_id=None
    for npc in sect.npcs:
        npc.realm_index=1
    high.realm_index=5
    e._ensure_intrigue_faction(g,'sect',sect.id)
    g.rng_state=encode_rng(random.Random(seed));e.store.save(g)
    with pytest.raises(ValueError,match='控制权'):e.intrigue_personnel_action(g.id,'sect','appoint',low.id,'leader')
    view=e.intrigue_propose_resolution(g.id,'sect','replace_leader',low.id,True)
    resolution=view['intrigue_system']['resolutions'][0]
    assert resolution['result']==expected
    assert {v['id'] for v in resolution['votes']}=={'player',high.id}
    loaded=e._load(g.id);record=e._ensure_intrigue_faction(loaded,'sect',sect.id)
    assert record['controller_id']==high.id
    assert (record['positions']['leader']==low.id)==(expected=='passed')


@pytest.mark.parametrize('tier,realm,founder',[('control',1,True),('decision',4,False),('ordinary',1,False)])
@pytest.mark.parametrize('leader',[False,True])
def test_dividend_tier_plus_independent_office(setup,tier,realm,founder,leader):
    e,g,sect,r,low,high=setup
    g.player.realm_index=realm;sect.founded_by_player=founder
    r['controller_id']='player' if founder else high.id
    r['positions']['leader']='player' if leader else low.id
    row=register(g,'sect',sect.id,'human')
    transfer_value(g,'background:human',key('sect',sect.id),1000000,'测试实际资金')
    row.update(income=100000,expense=10000,expected_upkeep=1000,shortfall=0)
    welfare(g,sect)
    rate=round({'control':.15,'decision':.08,'ordinary':.03}[tier]+(.04 if leader else 0),2)
    assert row['dividend_rate']==rate
    assert row['dividend_paid']==int((100000-10000-100)*rate)
    e.store.save(g);assert e.store.load(g.id).economy_v2['organizations'][key('sect',sect.id)]['dividend_rate']==rate


def test_invalid_guest_leader_gets_no_bonus_and_is_cleared(setup):
    e,g,sect,r,low,high=setup
    r['positions']['leader']='player';r['positions']['guest_elder']='player'
    row=register(g,'sect',sect.id,'human');row.update(income=100000,expense=0)
    welfare(g,sect);assert row['dividend_rate']==.15
    assert e._ensure_intrigue_faction(g,'sect',sect.id)['positions']['leader'] is None


def test_ordinary_leader_cannot_appoint_or_vote(setup):
    e,g,sect,r,low,high=setup
    sect.founded_by_player=False;g.player.realm_index=1;r['positions']['leader']='player';e.store.save(g)
    with pytest.raises(ValueError,match='控制权'):e.intrigue_personnel_action(g.id,'sect','appoint',low.id,'leader')
    with pytest.raises(ValueError,match='决策权'):e.intrigue_propose_resolution(g.id,'sect','replace_leader',low.id,True)

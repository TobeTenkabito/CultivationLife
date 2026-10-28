"""Real commands, original treasuries, membership clocks and finite task rewards."""
import copy
import random
from pathlib import Path
from unittest.mock import patch
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc
from cultivation_life.rules import add_item, has_item
from cultivation_life.soul_rules import rebellion_chance
from cultivation_life.system.sect_tasks import state, tasks
from cultivation_life.system.sect_tasks.finance import salaries, wallet
from cultivation_life.system.sect_tasks.presentation import public
from cultivation_life.system.economy import depot
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system.economy.organization_accounts import register
from cultivation_life.system.faction_geography import faction_site

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def ready(tmp_path):
    e=GameEngine(ROOT,tmp_path/'saves')
    g=e._load(e.create_game('宗门任务验收','supreme_metal','dao',321,preset_id='core')['id'])
    g.pending_event=None;p=g.player;p.realm_index=4;p.layer=1;p.lifespan=10000
    sect=next(s for s in g.sects.values() if s.world=='human' and s.kind=='sect' and not s.extinct)
    p.faction_id=sect.id;p.faction_join_age=p.age;p.location_id=faction_site(sect)['id']
    p.faction_contribution=1000;add_item(p,'spirit_stone',100000)
    sect.npcs=[SectNpc('sect-high','高阶门人','长老',5,1,80,10000,world='human',faction_id=sect.id),
               SectNpc('sect-low','低阶门人','弟子',1,1,20,10000,world='human',faction_id=sect.id)]
    finance=register(g,'sect',sect.id,'human');state.ensure(g,sect)
    row=state.record(g,sect);row['resources']=100000;row['positions']['leader']='player'
    state.ensure(g,sect)['influence']={'player':100,'sect-high':100,'sect-low':100}
    e.store.save(g)
    return e,g,sect,finance


def act(e,g,action,**payload):
    current=e.store.load(g.id);sect=current.sects[current.player.faction_id]
    return e.sect_task_action(g.id,dict(action=action,owner_id=sect.id,revision=state.snapshot(current,sect)['revision'],**payload))


@pytest.mark.parametrize('control,chance',[(100,0),(50,0),(49,.007),(25,.175),(0,.35)])
def test_rebellion_scale(control,chance):
    assert rebellion_chance(control)==pytest.approx(chance)


def test_ordinary_catalog_and_read_only_projection(ready):
    e,g,sect,_=ready
    assert state.ordinary('human')
    before=g.to_dict()
    for _ in range(3):assert public(g)['owner_id']==sect.id
    assert g.to_dict()==before


def test_salary_high_first_low_rank_gets_paid_no_refill_on_reload(ready):
    e,g,sect,finance=ready
    row=state.record(g,sect);row['resources']=190
    salaries(g,sect,finance)
    board=state.snapshot(g,sect)
    assert [r['id'] for r in board['salaries']]==['sect-high','player','sect-low']
    assert [r['paid'] for r in board['salaries']]==[180,10,0]
    assert board['unpaid_members']==2 and row['unrest']>0
    assert balance(g,wallet(g,'sect-high'))==180
    e.store.save(g);loaded=e.store.load(g.id);before=loaded.to_dict()
    salaries(loaded,loaded.sects[sect.id],loaded.economy_v2['organizations'][depot.treasury(g,sect)])
    assert loaded.to_dict()==before
    g.player.age+=1;row['resources']=10000
    salaries(g,sect,finance)
    assert board['salaries'][-1]['paid']>=20


@pytest.mark.parametrize('mode',['leave','ascend','dead','other','historical'])
def test_only_current_player_sect_settles(ready,mode):
    e,g,sect,finance=ready
    if mode=='leave':g.player.faction_id=None
    elif mode=='ascend':g.player.world='spirit'
    elif mode=='dead':g.player.alive=False
    elif mode=='other':sect=next(s for s in g.sects.values() if s.kind=='sect' and s.id!=sect.id)
    else:
        from cultivation_life.regional_context import CalendarGame
        g=CalendarGame(g,'human',g.player.age-1)
    root=getattr(g,'_game',g);before=root.to_dict()
    salaries(g,sect,finance,100);tasks.advance(g,e.maps,sect)
    assert root.to_dict()==before


def test_return_does_not_replay_missed_years(ready):
    e,g,sect,finance=ready
    salaries(g,sect,finance)
    g.player.world='spirit';g.player.age+=100
    salaries(g,sect,finance,100)
    g.player.world='human';salaries(g,sect,finance,100)
    assert next(r for r in state.snapshot(g,sect)['salaries'] if r['id']=='player')['minimum']==125


def test_donation_is_actual_cash_and_cannot_arbitrage(ready):
    e,g,sect,_=ready
    before=balance(g,'player');cash=state.record(g,sect)['resources'];points=g.player.faction_contribution
    result=act(e,g,'donate',amount=100)
    current=e.store.load(g.id)
    assert balance(current,'player')==before-100
    assert state.record(current,current.sects[sect.id])['resources']==cash+100
    assert current.player.faction_contribution==points+5
    assert result['faction']['task_board']['influence']==101


def test_redeem_quota_stale_page_and_real_stock(ready):
    e,g,sect,_=ready
    limit=state.limit(g)
    act(e,g,'redeem',item='spirit_stone',quantity=limit)
    before=e.store.load(g.id).to_dict()
    with pytest.raises(ValueError,match='额度'):
        act(e,g,'redeem',item='spirit_stone',quantity=1)
    with pytest.raises(ValueError,match='过期'):
        e.sect_task_action(g.id,dict(action='donate',owner_id=sect.id,revision=0,amount=100))
    assert e.store.load(g.id).to_dict()==before
    current=e.store.load(g.id);current.diplomacy_unit+=1;e.store.save(current)
    act(e,g,'redeem',item='spirit_stone',quantity=1)


def test_material_task_completes_once_from_actual_bag(ready):
    e,g,sect,_=ready
    key=next(iter(state.ordinary('human')));good=state.ordinary('human')[key]
    task=tasks.publish(g,sect,'sect-high','material',key)
    add_item(g.player,good['id'],1);e.store.save(g)
    points=g.player.faction_contribution
    act(e,g,'complete',task_id=task['id'])
    current=e.store.load(g.id);board=state.snapshot(current,current.sects[sect.id])
    assert board['tasks'][0]['completer']=='player'
    assert current.player.faction_contribution==points+task['reward']
    assert depot.find(current,current.sects[sect.id])['stock'][key]==1
    before=current.to_dict()
    with pytest.raises(ValueError):act(e,g,'complete',task_id=task['id'])
    assert e.store.load(g.id).to_dict()==before


def test_npc_pays_real_salary_for_player_commission(ready):
    e,g,sect,finance=ready
    salaries(g,sect,finance)
    goods=sorted(state.ordinary('human').items(),key=lambda r:r[1]['price'])
    key,good=goods[0];task=tasks.publish(g,sect,'player','material',key)
    npc=sect.npcs[0];cash=balance(g,wallet(g,npc.id))
    success=tasks.npc_complete(g,e.maps,sect,task,npc)
    assert success
    assert has_item(g.player,good['id'])
    assert balance(g,wallet(g,npc.id))<cash
    assert state.contribution(g,sect,npc.id)==task['reward']


def test_closed_recruitment_and_minimum_permissions(ready):
    e,g,sect,_=ready
    act(e,g,'recruitment',enabled=False)
    current=e.store.load(g.id)
    from cultivation_life.system.economy.estate_management import recruitment_ready
    assert not recruitment_ready(current,current.sects[sect.id])
    from cultivation_life.system.sect_membership import recruiting
    current.player.faction_id=None
    assert recruiting(current,sect.id)
    current.player.faction_id=sect.id;current.player.world='spirit'
    assert recruiting(current,sect.id)
    act(e,g,'minimum',realm=5)
    with pytest.raises(ValueError,match='境界'):act(e,g,'publish',kind='material',item=next(iter(state.ordinary('human'))),quantity=1)


def test_dismissal_reduces_unrest_escalates_later_crisis(ready):
    e,g,sect,finance=ready
    row=state.record(g,sect);row['unrest']=45;row['resources']=0
    salaries(g,sect,finance);e.store.save(g)
    before=row['unrest']
    act(e,g,'dismiss',successor='sect-high')
    current=e.store.load(g.id);board=state.snapshot(current,current.sects[sect.id])
    assert board['dismissals']==1
    assert state.record(current,current.sects[sect.id])['unrest']==before-25
    with pytest.raises(ValueError):act(e,g,'dismiss',successor='player')


def test_actual_donation_then_full_payroll_unlocks_rescue_once(ready):
    e,g,sect,finance=ready
    state.record(g,sect)['resources']=0
    salaries(g,sect,finance)
    assert state.snapshot(g,sect)['arrears']>0
    e.store.save(g)
    result=act(e,g,'donate',amount=50000)
    assert '我养你啊' not in {r['name'] for r in result['new_achievements']}
    g=e._load(g.id);sect=g.sects[sect.id];g.player.age+=1
    salaries(g,sect,register(g,'sect',sect.id,'human'))
    assert state.snapshot(g,sect)['arrears']==0
    e.store.save(g)
    assert '我养你啊' in {r['name'] for r in e.get_game(g.id)['new_achievements']}
    assert '我养你啊' not in {r['name'] for r in e.get_game(g.id)['new_achievements']}


def test_three_real_financial_dismissals_need_same_membership(ready):
    e,g,sect,finance=ready
    last=None
    for index,successor in enumerate(('sect-high','player','sect-high')):
        g=e._load(g.id);sect=g.sects[sect.id]
        g.player.age+=1;g.pending_event=None
        board=state.ensure(g,sect)
        board['arrears']=100;board['salary_year']=g.player.age
        state.record(g,sect)['unrest']=40
        e.store.save(g)
        last=act(e,g,'dismiss',successor=successor)
        assert ('铁打的弟子，流水的掌门' in {r['name'] for r in last['new_achievements']}) == (index==2)


@pytest.mark.parametrize('interruption',['left','crossed','new_membership'])
def test_payroll_donation_does_not_award_after_membership_or_world_break(ready,interruption):
    from cultivation_life.models import HistoryRecord
    e,g,sect,finance=ready
    state.record(g,sect)['resources']=0
    salaries(g,sect,finance);e.store.save(g)
    act(e,g,'donate',amount=50000)
    g=e._load(g.id);sect=g.sects[sect.id];g.player.age+=1
    if interruption=='new_membership':g.player.faction_join_age=g.player.age
    else:
        identity='SYS_PLAYER_LEAVE_FACTION' if interruption=='left' else 'SYS_CROSS_WORLD'
        g.history.append(HistoryRecord(identity,1,g.player.age,'中断',sect.id,'left','中断',{},[]))
    salaries(g,sect,register(g,'sect',sect.id,'human'))
    assert state.snapshot(g,sect)['arrears']==0
    assert not g.player.milestones.get('rescued_sect_payroll')


def test_old_task_load_preserves_followup_and_rejects_stale_submission(ready):
    e,g,sect,_=ready
    legacy=e.events_by_id['EVT_FACTION_COMMON_PATROL_001']
    g.pending_event=e._instantiate_event(legacy,g,random.Random(1))
    follow=e._prepare_treasure_reward_event(g,random.Random(3))
    g.pending_event['_followup_event']=follow;e.store.save(g)
    view=e.get_game(g.id)
    assert view['pending_event']['id']==follow['id']
    with pytest.raises(ValueError):e.choose(g.id,'careful',event_id=legacy['id'])
    assert e.store.load(g.id).pending_event['id']==follow['id']


def test_crisis_conflict_departure_and_dissolution(ready):
    e,g,sect,finance=ready
    row=state.record(g,sect);row['resources']=0;row['unrest']=39
    salaries(g,sect,finance)
    assert state.snapshot(g,sect)['notices'][-1]['kind']=='conflict'
    g.player.age+=1;row['unrest']=69
    salaries(g,sect,finance)
    assert len(sect.npcs)==1 and state.snapshot(g,sect)['notices'][-1]['kind']=='departure'
    assert e._find_npc(g,'sect-high').alive
    g.player.age+=1;row['unrest']=94
    salaries(g,sect,finance)
    assert state.snapshot(g,sect)['dissolve_pending']
    e._annual_sect_update(g,random.Random(2))
    assert sect.extinct and g.player.faction_id is None
    assert g.pending_event['id'].startswith('EVT_SECT_FINANCE_')


def start_war(e,g,sect):
    enemy=next(s for s in g.sects.values() if s.world==sect.world and s.kind=='sect' and s.id!=sect.id)
    enemy.npcs=[SectNpc('task-opponent','敌宗修士','长老',4,2,50,10000,world=sect.world,faction_id=enemy.id),
                SectNpc('task-distant','远阶修士','长老',8,1,80,10000,world=sect.world,faction_id=enemy.id)]
    return e._start_war(g,'sect',sect.id,enemy.id,initiated_by_player=True)


def test_war_task_uses_real_roster_and_combat_at_front(ready):
    e,g,sect,_=ready
    war=start_war(e,g,sect)
    task=tasks.publish(g,sect,'sect-high','mobilize',war_id=war['id'])
    assert [n.id for n in tasks.opponents(g,sect,war['id'])]==['task-opponent']
    e.store.save(g)
    if g.player.location_id!=war['location_id']:
        with pytest.raises(ValueError,match='地图'):act(e,g,'complete',task_id=task['id'])
    g.player.location_id=war['location_id'];e.store.save(g)
    act(e,g,'complete',task_id=task['id'])
    current=e.store.load(g.id)
    assert current.last_combat_report
    assert state.snapshot(current,current.sects[sect.id])['tasks'][0]['status'] in {'completed','failed'}


def test_mobilization_is_capped_one_battle_only(ready):
    e,g,sect,_=ready
    from cultivation_life.system.war import logistics
    war=start_war(e,g,sect)
    for _ in range(7):
        state.ensure(g,sect)['influence']['player']=100
        task=tasks.publish(g,sect,'player','mobilize',war_id=war['id'])
        assert tasks.npc_complete(g,e.maps,sect,task,sect.npcs[0])
    assert war['sect_mobilization']['attacker']==.10
    logistics.begin_round(g,e.maps,war,random.Random(1))
    assert war['sect_mobilization_round']['attacker']==.10
    assert 'sect_mobilization' not in war
    boosted=logistics.factor(war,'attacker')
    war['battles']+=1
    assert logistics.factor(war,'attacker')==pytest.approx(boosted/1.1)
    logistics.begin_round(g,e.maps,war,random.Random(2))
    assert 'attacker' not in war['sect_mobilization_round']


def test_mobilization_does_not_apply_after_leaving(ready):
    e,g,sect,_=ready
    from cultivation_life.system.war import logistics
    war=start_war(e,g,sect)
    task=tasks.publish(g,sect,'player','mobilize',war_id=war['id'])
    assert tasks.npc_complete(g,e.maps,sect,task,sect.npcs[0])
    g.player.faction_id=None
    logistics.begin_round(g,e.maps,war,random.Random(1))
    assert 'attacker' not in war['sect_mobilization_round']


def test_expel_preserves_original_person_and_closes_their_tasks(ready):
    e,g,sect,_=ready
    key=next(iter(state.ordinary('human')))
    tasks.publish(g,sect,'sect-low','material',key)
    e.store.save(g)
    act(e,g,'expel',npc_id='sect-low')
    current=e.store.load(g.id);npc=e._find_npc(current,'sect-low')
    assert npc.alive and npc.faction_id is None and npc.realm_index==1
    assert not any(n.id==npc.id for n in current.sects[sect.id].npcs)
    assert state.snapshot(current,current.sects[sect.id])['tasks'][0]['status']=='cancelled'


def test_old_depot_claim_shares_limit_and_high_price_allows_one_item(ready):
    e,g,sect,_=ready
    from cultivation_life.sect_board_rules import claim
    claim(g,sect,state.limit(g)*10,1)
    with pytest.raises(ValueError,match='额度'):claim(g,sect,1,1)
    e.store.save(g)
    with pytest.raises(ValueError,match='额度'):act(e,g,'redeem',item='spirit_stone',quantity=1)
    g.diplomacy_unit+=1
    claim(g,sect,10,1)


def test_annual_entry_does_not_touch_other_boards(ready):
    e,g,sect,_=ready
    from cultivation_life.system.economy.organizations import advance_organizations
    from cultivation_life.system.economy.state import advance_economy
    g.player.age+=1
    advance_economy(g);advance_organizations(g,e.maps)
    assert state.snapshot(g,sect)['salary_year']==g.player.age
    assert all('task_board' not in state.record(g,s) for s in g.sects.values() if s.id!=sect.id)
    before=copy.deepcopy(state.snapshot(g,sect))
    g.player.faction_id=None;g.player.age+=1
    advance_economy(g);advance_organizations(g,e.maps)
    assert state.snapshot(g,sect)==before


def test_mortal_disciple_can_donate_and_receive_minimum(ready):
    e,g,sect,finance=ready
    g.player.realm_index=0
    salaries(g,sect,finance)
    assert next(r for r in state.snapshot(g,sect)['salaries'] if r['id']=='player')['minimum']==5
    e.store.save(g)
    act(e,g,'donate',amount=100)


def test_dead_player_and_imprisoned_member_cannot_process_tasks(ready):
    e,g,sect,_=ready
    key=next(iter(state.ordinary('human')))
    task=tasks.publish(g,sect,'player','material',key)
    g.intrigue_state.setdefault('npc_prisons',{})['sect-high']=f'sect:{sect.id}'
    assert not tasks.npc_complete(g,e.maps,sect,task,sect.npcs[0])
    with pytest.raises(ValueError,match='在押'):tasks.publish(g,sect,'sect-high','material',key)
    g.player.alive=False;e.store.save(g)
    with pytest.raises(ValueError):act(e,g,'donate',amount=100)


def test_dissolution_releases_original_prison_and_preserves_deployed_address(ready):
    e,g,sect,finance=ready
    row=state.record(g,sect);board=state.ensure(g,sect)
    row['prison']=[dict(prisoner_id='sect-high',sentence_remaining=20)]
    g.intrigue_state.setdefault('npc_prisons',{})['sect-high']=f'sect:{sect.id}'
    board['dissolve_pending']=True
    state.event(g,sect,'dissolution','长期欠薪，山门解散。')
    npc=sect.npcs[0];address=(npc.world,npc.location_id)
    e._annual_sect_update(g,random.Random(2))
    assert 'sect-high' not in g.intrigue_state['npc_prisons']
    assert e._find_npc(g,npc.id).alive and npc.faction_id is None
    assert (npc.world,npc.location_id)==address

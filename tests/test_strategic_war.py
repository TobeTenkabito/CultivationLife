"""Isolated political war lifecycle, original assets and atomic commands."""
import copy
import json
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.engine.composition.strategic_war import bind
from cultivation_life.models import GameState
from cultivation_life.race_diplomacy import relations_for
from cultivation_life.system.strategic_war import lifecycle
from cultivation_life.system.strategic_war.presentation import public
from cultivation_life.person_assignments import research_assignment
from cultivation_life.world_state import race_pair
from cultivation_life.system.strategic_war.materialization import materialize
from test_other_systems_audit_fixes import api, snapshot

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def engine(tmp_path_factory):
    return GameEngine(ROOT, tmp_path_factory.mktemp('strategic-war')/'saves')


def scenario(engine):
    made=engine.create_game('种族战争验收','supreme_metal','dao',641,
                            custom_start=dict(world='spirit',realm_index=8,layer=1))
    g=engine._load(made['id'])
    g.player.next_tribulation_age=None
    g.player.lifespan=None
    row=lifecycle.start(bind(engine),g,'human','woodborn')
    relations_for(g)[race_pair('human','woodborn')]=dict(status='war',affinity=-75)
    return g,row


def test_world_relations_never_guess_or_copy_legacy(engine):
    g,_=scenario(engine)
    g.race_relations['human|monster']=dict(status='war')
    relations_for(g,'true_demon')['human|monster']=dict(status='neutral')
    assert relations_for(g,'spirit')['human|monster']['status']=='alliance'
    assert relations_for(g,'true_demon')['human|monster']['status']=='neutral'
    assert g.race_relations['human|monster']==dict(status='war')
    restored=GameState.from_dict(g.to_dict())
    assert restored.strategic_war_state==g.strategic_war_state


def test_multiple_real_campaigns_calendar_receipts_and_return(engine):
    g,row=scenario(engine)
    deps=bind(engine);rng=random.Random(641)
    g.player.age+=1
    lifecycle.advance(deps,g,rng)
    assert row['status']=='active'
    assert len(row['campaigns'])==2
    children=[w for w in g.wars if w.get('strategic_war_id')==row['id']]
    ids=[n for w in children for ns in w['roster'].values() for n in ns]
    assert len(ids)==len(set(ids))
    assert all(research_assignment(g,n) for n in ids)
    before=copy.deepcopy(g.to_dict());state=rng.getstate()
    engine._advance_wars_unit(g,rng)
    assert g.to_dict()==before and rng.getstate()==state
    first_due=min(w['next_battle_age'] for w in children)
    while g.player.age<first_due-1:
        g.player.age+=1;lifecycle.advance(deps,g,rng)
    assert all(w['battles']==0 for w in children)
    g.player.age+=1;lifecycle.advance(deps,g,rng)
    assert any(w['battles'] for w in children)
    for _ in range(3000):
        if row['status']=='ended':break
        g.player.age+=1;lifecycle.advance(deps,g,rng)
    assert row['status']=='ended'
    assert all(w['status']=='ended' and w['logistics']['refunded'] for w in children)
    score=row['score'];saved=copy.deepcopy(g.to_dict())
    for w in children:lifecycle.receipt(g,row,w)
    assert row['score']==score and g.to_dict()==saved
    assert not any(research_assignment(g,n) for n in ids)
    for w in children:
        for side,js in w['journeys'].items():
            for j in js:
                n=deps.find_person(g,j['person_id'])
                if n and n.alive and j['phase']=='home':assert n.location_id==j['origin']
        assert all(r['mobilized']<=w['budget_caps'][s] for s,r in w['logistics']['sides'].items())
    engine.store.save(g)
    assert engine._load(g.id).strategic_war_state==g.strategic_war_state


def test_readonly_projection_and_stale_commands_preserve_save(engine):
    g,row=scenario(engine);engine.store.save(g)
    before=engine.store._path(g.id).read_bytes()
    projected=public(bind(engine),g)
    assert engine.store._path(g.id).read_bytes()==before
    assert 'receipts' not in projected['wars'][0]
    with pytest.raises(ValueError,match='态势已变化'):
        engine.strategic_war_action(g.id,dict(action='offer_peace',war_id=row['id'],expected_revision=-1,command_id='stale',command_seq=1))
    assert engine.store._path(g.id).read_bytes()==before


def test_no_war_has_no_rng_or_state_work(engine):
    g,_=scenario(engine);g.strategic_war_state={}
    before=copy.deepcopy(g.to_dict());rng=random.Random(6);state=rng.getstate()
    lifecycle.advance(bind(engine),g,rng)
    assert before==g.to_dict() and rng.getstate()==state


def own_campaign(engine):
    g,row=scenario(engine)
    g.player.faction_id='taixuan';g.sects['taixuan'].founded_by_player=True
    lifecycle.commit(bind(engine),g,row,g.sects['taixuan'])
    g.player.age+=1;lifecycle.advance(bind(engine),g,random.Random(641))
    engine.store.save(g)
    return g,row,next(w for w in g.wars if w.get('strategic_war_id')==row['id'] and w['attacker_id']=='taixuan')


def test_real_commands_only_control_own_org_and_monotonic_replay(api):
    e,post=api;g,row,c=own_campaign(e)
    base=dict(war_id=row['id'],expected_revision=row['revision'],command_id='hold-local',command_seq=1,
              action='campaign_stance',campaign_id=c['id'],org_id='taixuan',org_kind='sect',stance='hold')
    shown=post(g.id,'strategic-war',**base)
    saved=e._load(g.id)
    assert next(w for w in saved.wars if w['id']==c['id'])['org_stances']==dict(taixuan='hold')
    assert saved.strategic_war_state['command_seq']==1
    before=e.store._path(g.id).read_bytes()
    post(g.id,'strategic-war',status=400,**base)
    assert e.store._path(g.id).read_bytes()==before
    bad={**base,'command_id':'global-command','command_seq':2,'action':'stance','expected_revision':row['revision']+1}
    post(g.id,'strategic-war',status=400,**bad)
    assert e.store._path(g.id).read_bytes()==before
    # Pruned receipt IDs cannot replay below the sequence watermark.
    changed=e._load(g.id);changed.strategic_war_state['commands']=[];e.store.save(changed)
    before=e.store._path(g.id).read_bytes()
    post(g.id,'strategic-war',status=400,**base)
    assert e.store._path(g.id).read_bytes()==before
    assert 'journeys' not in json.dumps(shown['war_system'])


def test_commit_requires_current_displayed_treasury_quote(api):
    e,post=api;g,row=scenario(e)
    g.player.faction_id='taixuan';g.sects['taixuan'].founded_by_player=True;e.store.save(g)
    before=snapshot(e,g.id)
    choice=e.get_game(g.id)['war_system']['strategic']['wars'][0]['commit_choices'][0]
    data=dict(action='commit',war_id=row['id'],expected_revision=row['revision'],command_id='approve-cost',command_seq=1,
              org_id=choice['id'],org_kind=choice['kind'])
    post(g.id,'strategic-war',status=400,expected_budget=choice['budget']+1,**data)
    assert e.store._path(g.id).read_bytes()==before
    post(g.id,'strategic-war',expected_budget=choice['budget'],**data)
    assert e._load(g.id).strategic_war_state['wars'][0]['commitments'][0]['budget']==choice['budget']


def test_one_campaign_loss_does_not_end_parent_and_no_economic_score_reward(engine):
    g,row,c=own_campaign(engine)
    from cultivation_life.system.economy.ledger import balance
    treasury=balance(g,'organization:sect:taixuan')
    c.update(status='peace_ready',winner='defender')
    lifecycle.receipt(g,row,c)
    assert row['status']=='active' and row['score']==-50
    assert balance(g,'organization:sect:taixuan')==treasury
    assert c['status']=='withdrawing' and not c['logistics'].get('refunded')
    # Loading a withdrawing strategic relation must not manufacture a new war.
    before=len(g.wars);engine._ensure_wars(g)
    assert len(g.wars)==before


def test_dead_army_does_not_teleport_remaining_convoy_home(engine):
    g,row,c=own_campaign(engine)
    cargo=c['cargo_journeys']['attacker']
    cargo.update(phase='outbound',years=10,remaining=5)
    for people in c['journeys'].values():
        for journey in people:
            bind(engine).find_person(g,journey['person_id']).alive=False
    lifecycle.withdraw(g,c)
    assert cargo['remaining']==5
    g.player.age+=1
    assert not lifecycle._journey(bind(engine),g,c)
    assert cargo['remaining']==4 and not c['logistics'].get('refunded')


def test_stationing_retains_old_independent_peace_clock(engine):
    from cultivation_life.system.war.stationing import advance
    g,row,c=own_campaign(engine)
    c.pop('strategic_war_id');c['status']='peace_ready'
    original=copy.deepcopy(c['logistics']['sides'])
    g.player.age+=1;advance(g)
    assert c['logistics']['sides']==original


def test_loading_during_march_preserves_original_array_without_free_repairs(engine):
    g,row,c=own_campaign(engine)
    person=c['roster']['attacker'][0]
    j=next(j for j in c['journeys']['attacker'] if j['person_id']==person)
    j.update(phase='outbound',years=10,remaining=10)
    array=g.npc_formations[person]
    array['durability']=31.
    original=copy.deepcopy(array)
    engine.store.save(g)
    engine.get_game(g.id)
    restored=engine._load(g.id).npc_formations[person]
    assert restored['slots']==original['slots'] and restored['name']==original['name']
    assert restored['durability']==31.


def test_materialization_has_finite_local_provenance_and_no_player_site(engine):
    g,_=scenario(engine)
    org=materialize(bind(engine),g,'spirit','woodborn',random.Random(4))
    assert org and org.location_id!=g.player.location_id
    source=g.strategic_war_state['materialized'][org.id]
    assert source['source']==f'market:spirit:{org.location_id}' and source['paid']>0
    from cultivation_life.system.economy.ledger import balance
    assert balance(g,'organization:sect:'+org.id)==source['paid']
    assert all(n.faction_id==org.id and n.location_id==org.location_id for n in org.npcs)
    # Loaded identity is never rolled a second time.
    restored=GameState.from_dict(g.to_dict())
    before=copy.deepcopy(restored.sects[org.id].to_dict())
    materialize(bind(engine),restored,'spirit','woodborn',random.Random(4))
    assert restored.sects[org.id].to_dict()==before


def test_missing_content_pauses_attacks_but_keeps_exit(engine,monkeypatch):
    g,row,c=own_campaign(engine)
    monkeypatch.setattr(lifecycle,'local_races',lambda world:[])
    initial=c['battles']
    for _ in range(3000):
        g.player.age+=1;lifecycle.advance(bind(engine),g,random.Random(9))
        if row['status']=='ended':break
    assert c['battles']==initial and row['status']=='ended'
    assert c['logistics']['refunded']


def test_calendar_segmentation_is_identical_and_legacy_unit_never_replays(engine):
    g,row,c=own_campaign(engine)
    first=copy.deepcopy(g);second=copy.deepcopy(g)
    def run(game,chunks):
        rng=random.Random(71)
        for count in chunks:
            for _ in range(count):
                game.player.age+=1;lifecycle.advance(bind(engine),game,rng)
        return game.to_dict(),rng.getstate()
    assert run(first,[100])==run(second,[10]*10)


def test_all_military_entries_reject_managed_instant_battle(api):
    e,post=api;g,row,c=own_campaign(e)
    before=snapshot(e,g.id)
    for action in ('round','participate_round','conquest','call_allies','resupply'):
        post(g.id,'war-action',status=400,war_id=c['id'],action=action)
        assert e.store._path(g.id).read_bytes()==before
    post(g.id,'war-peace',status=400,war_id=c['id'],term='white_peace')
    assert e.store._path(g.id).read_bytes()==before


def test_declaration_uses_existing_real_council_entry_and_never_race_army(api):
    e,post=api
    g,_=scenario(e);g.strategic_war_state={};relations_for(g)['human|woodborn']['status']='neutral'
    e.store.save(g)
    with patch.object(e,'_intrigue_enabled',return_value=False),patch.object(e,'_vote_probability',return_value=1.):
        result=e.propose_race_diplomacy(g.id,'woodborn','war')
    saved=e._load(g.id)
    assert len(saved.strategic_war_state['wars'])==1
    assert not saved.wars and relations_for(saved)['human|woodborn']['status']=='war'
    assert result['war_system']['strategic']['wars'][0]['status']=='mobilizing'


def test_schema_rejects_unknown_world(engine):
    g,_=scenario(engine);document=g.to_dict()
    document['strategic_war_state']['wars'][0]['world']='missing'
    with pytest.raises(ValueError,match='界面'):
        GameState.from_dict(document)


def test_completed_history_is_bounded_before_save_not_only_next_declaration(engine):
    g,row=scenario(engine)
    cases=[]
    for i in range(21):
        case=copy.deepcopy(row);case.update(id=f'case-{i}',status='ended');cases.append(case)
    g.strategic_war_state['wars']=cases
    lifecycle.compact(g)
    assert len(g.strategic_war_state['wars'])==20
    assert GameState.from_dict(g.to_dict())


def test_legacy_decisive_case_preserves_actual_demand_and_settles_once(api):
    e,post=api;g,_=scenario(e)
    org=materialize(bind(e),g,'spirit','woodborn',random.Random(8))
    child=e._start_war(g,'sect','taixuan',org.id,initiated_by_player=True)
    child.update(kind='race',attacker_id='human',defender_id='woodborn',status='peace_ready',winner='defender',war_score=-30.,battles=3)
    child['coalitions']={s:[dict(id=r,role='leader',joined_unit=0,called_by=None)] for s,r in [('attacker','human'),('defender','woodborn')]}
    child['roster_owner']={n:r for s,r in [('attacker','human'),('defender','woodborn')] for n in child['roster'][s]}
    g.strategic_war_state={}
    g.race_relations['human|woodborn']=dict(status='war',affinity=-75)
    del relations_for(g)['human|woodborn']
    child['peace_offer']=e._generate_ai_peace_offer(g,child,'defender')
    victim=next(d['target_id'] for d in child['peace_offer']['demands'] if d['term']=='execute')
    e.store.save(g);snapshot(e,g.id)
    shown=e.get_game(g.id)['war_system']['strategic']
    assert shown['legacy_wars'][0]['terms']
    with patch.object(e,'_vote_probability',return_value=1.):
        post(g.id,'strategic-war',action='settle_legacy',legacy_id=child['id'],expected_battles=3,
             expected_status='peace_ready',command_id='settle-original',command_seq=1)
    restored=e._load(g.id)
    ended=next(w for w in restored.wars if w['id']==child['id'])
    assert ended['status']=='ended' and ended['logistics']['refunded']
    assert not bind(e).find_person(restored,victim).alive
    assert restored.race_relations['human|woodborn']['adopted_world']=='spirit'
    assert not restored.strategic_war_state.get('wars')
    before=snapshot(e,g.id)
    post(g.id,'strategic-war',status=400,action='settle_legacy',legacy_id=child['id'],expected_battles=3,
         expected_status='peace_ready',command_id='settle-again',command_seq=2)
    assert e.store._path(g.id).read_bytes()==before


def test_unknown_legacy_relation_needs_explicit_one_world_adoption(api):
    e,post=api;g,_=scenario(e);g.strategic_war_state={}
    del relations_for(g)['human|woodborn']
    g.race_relations['human|woodborn']=dict(status='alliance',affinity=80)
    e.store.save(g);before=snapshot(e,g.id)
    assert relations_for(e._load(g.id)).get('human|woodborn') is None
    post(g.id,'strategic-war',action='adopt_relation',relation_key='human|woodborn',command_id='adopt-one-world',command_seq=1)
    restored=e._load(g.id)
    assert relations_for(restored)['human|woodborn']['status']=='alliance'
    assert relations_for(restored,'true_demon').get('human|woodborn') is None
    before=snapshot(e,g.id)
    post(g.id,'strategic-war',status=400,action='adopt_relation',relation_key='human|woodborn',command_id='adopt-twice',command_seq=2)
    assert e.store._path(g.id).read_bytes()==before


def test_abroad_player_cannot_read_or_command_original_world_war(api):
    e,post=api;g,row,c=own_campaign(e)
    # Initial-state fixture representing someone already abroad; this does not
    # provide or exercise a runtime movement shortcut.
    document=g.to_dict();document['player']['world']='true_demon'
    document['player']['location_id']=next(r['id'] for r in e.maps.worlds['true_demon']['locations'] if not r.get('min_realm_index'))
    abroad=GameState.from_dict(document);e.store.save(abroad)
    before=snapshot(e,g.id)
    assert not e.get_game(g.id)['war_system']['strategic']['wars']
    post(g.id,'strategic-war',status=400,action='withdraw',war_id=row['id'],expected_revision=row['revision'],
         command_id='abroad-command',command_seq=1,campaign_id=c['id'],org_id='taixuan',org_kind='sect')
    assert e.store._path(g.id).read_bytes()==before


def test_parent_capacity_stays_under_256_kib_with_full_log_windows(engine):
    g,row=scenario(engine)
    rows=[]
    for i in range(22):
        w=copy.deepcopy(row);w.update(id=f'capacity-{i}',status='active' if i<2 else 'ended')
        for _ in range(80):lifecycle.note(g,w,'战役结算','甲'*160)
        w['commitments']=[dict(org={'kind':'sect','id':f'capacity-org-{j}'},side='attacker' if j<6 else 'defender',
                               budget=10**12,representative=f'capacity-person-{j}',approved_age=g.player.age) for j in range(12)]
        rows.append(w)
    g.strategic_war_state['wars']=rows
    lifecycle.compact(g)
    assert len(json.dumps(g.strategic_war_state,ensure_ascii=False).encode())<256*1024
    assert GameState.from_dict(g.to_dict())

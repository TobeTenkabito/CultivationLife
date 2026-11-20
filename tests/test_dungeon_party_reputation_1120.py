"""Persisted dungeon ranks, outside parties, lethal choices and reputation effects."""
import copy
import json
import random
from pathlib import Path
import pytest
from test_seeded_dungeons import local,discover,act
from test_dungeon_rank_ecology import force_quality,loaded
from cultivation_life.models import SectNpc,GameState
from cultivation_life.relationship_records import find_person
from cultivation_life.rules import max_hp,max_mp
from cultivation_life.reputation import record
from cultivation_life.system.dungeons.generation import generate
from cultivation_life.system.dungeons.encounters import can_slay
from cultivation_life.system.dungeons.ecology import stage


def companion(game,key='outside',rank=4):
    npc=SectNpc(id=key,name='同行道友',title='散修',realm_index=rank,layer=1,age=30,lifespan=1000,
        world=game.player.world,location_id=game.player.location_id,affinity=100,encountered_player=True)
    game.world_npcs[key]=npc;game.player.party.append({'id':key})
    return npc


@pytest.mark.parametrize('quality',['ordinary','rare'])
@pytest.mark.parametrize('realm,layer',[(1,1),(1,13),(3,7),(3,9),(4,1),(5,9)])
def test_generated_population_obeys_whole_realm_boundaries(local,monkeypatch,quality,realm,layer):
    engine,game=local;force_quality(monkeypatch,quality)
    game.player.realm_index=realm;game.player.layer=layer
    for seed in range(12):
        game.seed=seed
        site=generate(game,engine.maps.location(game.player.world,game.player.location_id),0,0)
        for role in site['roles'].values():
            if quality=='ordinary':
                assert role['realm']==realm and abs(stage(realm,role['layer'])-stage(realm,layer))<=2
            else:assert abs(role['realm']-realm)<=1
            if role['purpose']=='assassinate':assert (role['realm'],role['layer'])>=(realm,layer)
        assert site==generate(game,engine.maps.location(game.player.world,game.player.location_id),0,0)


def test_sealed_reference_does_not_force_high_assassins_into_ordinary_site(local,monkeypatch):
    engine,game=local;force_quality(monkeypatch,'ordinary')
    game.player.realm_index=1;game.player.layer=3
    game.player.cultivation_suppression={'realm_index':4,'layer':9}
    for seed in range(10):
        game.seed=seed;site=generate(game,engine.maps.location(game.player.world,game.player.location_id),0,0)
        assert site['reference']==[1,3] and site['realm']==1
        assert all(r['realm']==1 and r['purpose']!='assassinate' for r in site['roles'].values())


def test_known_invitee_motive_checks_true_rank_under_suppression(local,monkeypatch):
    from cultivation_life.dungeon_schema import empty
    from cultivation_life.system.dungeons.people import invite
    engine,game=local;game.player.realm_index=1;game.player.layer=3
    game.player.cultivation_suppression={'realm_index':4,'layer':9}
    game.dungeon_state=empty();npc=companion(game,rank=2)
    site=generate(game,engine.maps.location(game.player.world,game.player.location_id),0,0)
    class AssassinDraw(random.Random):
        def choice(self,values):
            return 'assassinate' if isinstance(values,tuple) and 'assassinate' in values else super().choice(values)
    monkeypatch.setattr('cultivation_life.system.dungeons.generation.stream',lambda *args:AssassinDraw(7))
    role=invite(game,site,npc.id)
    assert role['purpose']=='observe' and npc.realm_index==2


def test_outside_party_enters_as_same_person_and_survives_exit(local):
    engine,game=local
    npc=companion(game,rank=1)  # Established allies bypass new-stranger recruitment.
    engine.store.save(game);discover(engine,game)
    before=set(engine.store.load(game.id).world_npcs)
    view=act(engine,game,'enter')['dungeons']['session'];saved,site=loaded(engine,game)
    assert site['party']==[npc.id] and view['party_count']==2
    assert site['roles'][npc.id]['npc_id']==npc.id and site['roles'][npc.id]['ledger']['outside_party']
    assert set(saved.world_npcs)==before and find_person(saved,npc.id).realm_index==1
    for r in site['roles'].values():r['offer_step']=99
    engine.store.save(saved)
    for _ in range(4):act(engine,game,'choose',choice='bypass')
    saved,site=loaded(engine,game)
    assert npc.id in site['party'] and any(r['id']==npc.id for r in saved.player.party)
    act(engine,game,'exit');saved,site=loaded(engine,game)
    assert any(r['id']==npc.id for r in saved.player.party) and find_person(saved,npc.id).alive
    assert GameState.from_dict(saved.to_dict()).dungeon_state==saved.dungeon_state


@pytest.mark.parametrize('problem',['remote','dead','held'])
def test_unavailable_outside_party_is_not_teleported_or_copied(local,problem):
    engine,game=local;npc=companion(game)
    if problem=='remote':npc.location_id='border_void_watch'
    elif problem=='dead':npc.alive=False
    else:npc.roster_state='held';npc.custody={'holder_id':'someone_else','kind':'prisoner'}
    original=(npc.world,npc.location_id,npc.alive)
    engine.store.save(game);discover(engine,game);act(engine,game,'enter')
    saved,site=loaded(engine,game)
    assert npc.id not in site['party'] and npc.id not in site['roles']
    same=find_person(saved,npc.id,include_inactive=True)
    assert (same.world,same.location_id,same.alive)==original


@pytest.mark.parametrize('kind',['trace','cache','hazard','seal','contact','conflict','core'])
def test_every_scene_exposes_an_attackable_present_actor(local,kind):
    engine,game=local;discover(engine,game)
    saved,site=loaded(engine,game);site['nodes'][0]['kind']=kind
    engine.store.save(saved);view=act(engine,game,'enter')['dungeons']['session']
    saved,site=loaded(engine,game);actor=site['roles'][site['nodes'][0]['actor']]
    assert actor['known'] and can_slay(saved,site,actor)
    assert next(p for p in view['people'] if p['id']==actor['id'])['can_slay']
    assert actor['npc_id'] is None


@pytest.mark.parametrize('pending',['join','conflict','settlement','guardian','ambush',None])
def test_attack_is_real_lethal_combat_and_does_not_double_claim(local,pending):
    engine,game=local;npc=companion(game);engine.store.save(game)
    discover(engine,game);act(engine,game,'enter')
    saved,site=loaded(engine,game);enemy=next(r for r in site['roles'].values() if not r['existing'])
    enemy.update(realm=1,true_realm=1,layer=1,power_factor=.1,known=True,state='observed',purpose='seek')
    enemy['ledger']['supporters']=[]
    for r in site['roles'].values():r['offer_step']=99
    site['nodes'][0].update(kind='trace',actor=enemy['id'])
    site['pending']=dict(kind=pending,actor=enemy['id']) if pending else None
    if pending=='conflict':site['pending']['other']=next(k for k in site['roles'] if k not in {enemy['id'],npc.id})
    engine.store.save(saved);revision=site['revision'];infamy=saved.player.infamy
    act(engine,game,'slay',actor_id=enemy['id'])
    saved,site=loaded(engine,game)
    assert saved.last_combat_report and site['step']==0 and not site['claims']
    assert not find_person(saved,enemy['id'],include_inactive=True).alive
    assert site['roles'][enemy['id']]['state']=='dead' and saved.player.infamy>infamy
    assert npc.id in site['party'] and find_person(saved,npc.id).alive
    before=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError,match='过期'):
        engine.dungeon_action(game.id,'slay',dict(dungeon_id=site['id'],revision=revision,actor_id=enemy['id']))
    with pytest.raises(ValueError,match='在场'):act(engine,game,'slay',actor_id=enemy['id'])
    assert engine.store._path(game.id).read_bytes()==before
    act(engine,game,'choose',choice='seize');saved,site=loaded(engine,game)
    assert len(site['claims'])==1 and site['step']==1


def test_attack_remote_or_unseen_blueprint_id_is_rejected(local):
    engine,game=local;discover(engine,game);act(engine,game,'enter')
    saved,site=loaded(engine,game);role=next(r for r in site['roles'].values() if not r['known'])
    before=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError,match='在场'):act(engine,game,'slay',actor_id=role['id'])
    assert engine.store._path(game.id).read_bytes()==before


def test_attack_outside_companion_uses_death_and_party_consequences(local):
    engine,game=local;npc=companion(game,rank=1);engine.store.save(game)
    discover(engine,game);act(engine,game,'enter');act(engine,game,'slay',actor_id=npc.id)
    saved,site=loaded(engine,game)
    assert not find_person(saved,npc.id,include_inactive=True).alive
    assert npc.id not in site['party'] and all(r['id']!=npc.id for r in saved.player.party)
    assert saved.player.infamy>0 and site['roles'][npc.id]['state']=='dead'


def test_mortal_outside_companion_preserves_actual_rank(local):
    engine,game=local;npc=companion(game,rank=0);engine.store.save(game)
    discover(engine,game);act(engine,game,'enter');saved,site=loaded(engine,game)
    assert site['roles'][npc.id]['realm']==0 and npc.id in site['party']
    assert find_person(saved,npc.id).realm_index==0


PUNITIVE={('EVT_FAME_ALARM_001','intimidate'),('EVT_FAME_ALARM_001','appease'),
    ('EVT_TWO_REALMS_003','bargain_six'),('EVT_MOTHER_BORER_002','seize_tool'),
    ('EVT_MA_LIANG_006','steal_lamp'),('EVT_MA_LIANG_009','bind_both')}


def test_reviewed_fixed_events_only_punish_explicit_wrongdoing():
    found=set()
    for path in (Path(__file__).resolve().parents[1]/'content').glob('*events.json'):
        data=json.loads(path.read_text(encoding='utf-8'))
        for event in data.get('events',[]) if isinstance(data,dict) else data:
            for choice in event.get('choices',[]):
                if any(e.get('type')=='add_infamy' for e in choice.get('effects',[])):
                    found.add((event['id'],choice['id']))
    assert found==PUNITIVE


@pytest.mark.parametrize('event_id,choice,delta',[
    ('EVT_REALM_COMMON_MORTAL_01','study',1),('EVT_REALM_COMMON_FOUNDATION_01','mediate',3),
    ('EVT_REALM_COMMON_INTEGRATION_01','law',12),('EVT_MASTER_TEACHING_001','combat',2),
    ('EVT_MA_LIANG_001','hide',-20),('EVT_SECT_FIRST_WARNING_001','acknowledge',0)])
def test_real_event_load_and_submit_changes_renown_not_infamy(local,event_id,choice,delta):
    engine,game=local;game.player.infamy=120
    record(game.player,'test-existing-achievement',100,'既有事迹')
    event=engine.events_by_id[event_id]
    game.pending_event=engine._instantiate_event(event,game,random.Random(4))
    engine.store.save(game)
    view=engine.get_game(game.id)
    assert any(c['id']==choice and c['enabled'] for c in view['pending_event']['choices'])
    before=engine.store.load(game.id).player.renown
    engine.choose(game.id,choice,event_id=event_id)
    saved=engine.store.load(game.id)
    assert saved.player.infamy==120 and saved.player.renown-before==pytest.approx(delta)
    with pytest.raises(ValueError):engine.choose(game.id,choice,event_id=event_id)


def test_reconciliation_reduces_infamy_only_and_keeps_other_scopes(local):
    engine,game=local;game.player.infamy=120;game.player.infamy_by_scope['spirit']=55
    record(game.player,'test-renowned',100,'既有事迹')
    engine.store.save(game);before=engine.get_game(game.id)['player']['renown']
    engine.advance(game.id,'befriend_neighbors')
    saved=engine.store.load(game.id)
    assert 0<=saved.player.infamy<120 and saved.player.renown==before
    assert saved.player.infamy_by_scope['spirit']==55 and saved.player.age==game.player.age
    frozen=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):engine.advance(game.id,'befriend_neighbors')
    assert engine.store._path(game.id).read_bytes()==frozen

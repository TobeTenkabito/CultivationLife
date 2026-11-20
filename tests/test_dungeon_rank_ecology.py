"""Rank distribution, frozen rewards and every persisted recruitment entry."""
import copy
import pytest
from test_seeded_dungeons import local, discover, act
from cultivation_life.models import GameState
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system.dungeons import generation
from cultivation_life.system.dungeons.ecology import appearance_depth, floor
from cultivation_life.system.dungeons.people import candidates, materialize
from cultivation_life.system.dungeons.runtime import invite_tick


def force_quality(monkeypatch, quality):
    cfg=copy.deepcopy(generation.config())
    for profile in cfg['profiles'].values():
        profile['weights']=[int(q==quality) for q in ('ordinary','rare','epic','legendary')]
    monkeypatch.setattr(generation,'config',lambda:cfg)
    return cfg


def novice(engine,game):
    game.player.realm_index=1;game.player.layer=3
    game.player.hp=max_hp(game.player);game.player.mp=max_mp(game.player)
    engine.store.save(game)


def loaded(engine,game):
    saved=engine.store.load(game.id)
    return saved,next(iter(saved.dungeon_state['instances'].values()))


@pytest.mark.parametrize('quality,rank',[('ordinary',1),('rare',2),('epic',4),('legendary',5)])
def test_novice_rewards_and_population_are_separate(local,monkeypatch,quality,rank):
    engine,game=local;novice(engine,game);force_quality(monkeypatch,quality)
    location=engine.maps.location(game.player.world,game.player.location_id)
    assert location['id']=='wudi_plain'
    high=0
    for seed in range(24):
        game.seed=seed
        site=generation.generate(game,location,0,0)
        rewards=[n['reward'] for n in site['nodes']]+site['expedition']['bonuses']
        assert site['realm']==rank and all(r['realm']==rank for r in rewards)
        people=list(site['roles'].values())
        assert sum(r['realm']<=2 for r in people)>len(people)//2
        assert people[0]['realm']==1
        high+=sum(r['realm']>=4 for r in people)
        for i,node in enumerate(site['nodes']):
            depth=min(3,i*4//len(site['nodes']))
            actor=site['roles'][node['actor']]
            assert appearance_depth(site,actor)<=depth
            for key in actor['ledger']['supporters']:
                assert appearance_depth(site,site['roles'][key])<=depth
            if depth<2:assert actor['realm']<=2
        if quality in {'epic','legendary'}:
            assert people[-1]['realm']==rank
        if quality=='legendary':
            assert people[-1]['true_realm']==6 and people[-1]['realm']==5
        assert site==generation.generate(game,location,0,0)
    assert (high>0) if quality in {'epic','legendary'} else high==0


@pytest.mark.parametrize('quality',['ordinary','rare','epic','legendary'])
def test_world_floors_map_caps_and_assassin_rank(local,monkeypatch,quality):
    engine,game=local;cfg=force_quality(monkeypatch,quality)
    for world,ceiling in cfg['ceilings'].items():
        game.player.world=world;game.player.location_id=engine.maps.default_location(world)
        game.player.realm_index=floor(world);game.player.layer=5
        profile=cfg['profiles'][world+':'+game.player.location_id]
        site=generation.generate(game,engine.maps.location(world,game.player.location_id),0,0)
        expected=ceiling if quality=='legendary' else min(profile['cap'],profile['realm']+1) if quality=='epic' else min(profile['cap'],profile['realm']+int(quality=='rare'),floor(world)+int(quality=='rare'))
        assert site['realm']==expected
        assert all(1<=r['realm']<=ceiling for r in site['roles'].values())
        assert all((r['realm'],r['layer'])>=(game.player.realm_index,game.player.layer)
                   for r in site['roles'].values() if r['purpose']=='assassinate')
        assert all(n['reward']['realm']<9 for n in site['nodes']) if ceiling<9 else True


@pytest.mark.parametrize('quality,rank',[('ordinary',1),('rare',2)])
def test_advanced_player_in_low_map_still_gets_map_capped_rewards(local,monkeypatch,quality,rank):
    engine,game=local;cfg=force_quality(monkeypatch,quality)
    scope=next(k for k,p in cfg['profiles'].items() if k.startswith('human:') and p['realm']==1 and p['cap']==2)
    location=engine.maps.location('human',scope.split(':',1)[1])
    site=generation.generate(game,location,0,0)
    assert game.player.realm_index==4 and site['realm']==rank
    assert all(n['reward']['realm']==rank for n in site['nodes'])


@pytest.mark.parametrize('kind,choice,leave',[('join','accept','decline'),('settlement','ask_join','part')])
def test_stale_high_rank_join_is_disabled_and_rejected_atomically(local,kind,choice,leave):
    engine,game=local;novice(engine,game);discover(engine,game);act(engine,game,'enter')
    saved,site=loaded(engine,game);role=next(iter(site['roles'].values()))
    role.update(realm=4,true_realm=4,layer=9,known=True,state='contact',purpose='heal',resolve=0,desire=0,trust=100)
    site['pending']=dict(kind=kind,actor=role['id'])
    engine.store.save(saved)
    before=engine.store._path(game.id).read_bytes()
    choices={c['id']:c for c in engine.get_game(game.id)['dungeons']['session']['choices']}
    assert not choices[choice]['enabled'] and choices[leave]['enabled']
    with pytest.raises(ValueError,match='一个大境界'):act(engine,game,'choose',choice=choice)
    assert engine.store._path(game.id).read_bytes()==before
    act(engine,game,'choose',choice=leave)
    saved,site=loaded(engine,game)
    assert role['id'] not in site['party'] and role['id'] not in saved.world_npcs


def test_known_high_rank_person_cannot_be_invited_or_mutated(local):
    engine,game=local;novice(engine,game);discover(engine,game)
    saved,site=loaded(engine,game);role=next(iter(site['roles'].values()))
    role.update(realm=4,true_realm=4,layer=9)
    npc=materialize(saved,site,role)
    assert npc.id not in {n.id for n in candidates(saved)}
    engine.store.save(saved);engine.get_game(game.id)
    before=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):act(engine,game,'invite',actor_id=npc.id)
    assert engine.store._path(game.id).read_bytes()==before


@pytest.mark.parametrize('rank',[1,2])
def test_near_rank_team_accept_still_uses_original_person(local,rank):
    engine,game=local;novice(engine,game);discover(engine,game);act(engine,game,'enter')
    saved,site=loaded(engine,game);role=next(iter(site['roles'].values()))
    role.update(realm=rank,true_realm=rank,known=True,state='contact')
    site['pending']=dict(kind='join',actor=role['id']);engine.store.save(saved)
    act(engine,game,'choose',choice='accept')
    saved,site=loaded(engine,game)
    assert site['party']==[role['id']] and saved.world_npcs[role['id']].realm_index==rank


def test_high_rank_contact_passes_by_and_new_state_roundtrips(local):
    engine,game=local;novice(engine,game);discover(engine,game);act(engine,game,'enter')
    saved,site=loaded(engine,game);role=next(iter(site['roles'].values()))
    for r in site['roles'].values():r['offer_step']=99
    role.update(realm=4,true_realm=4,layer=9)
    site['nodes'][0].update(kind='contact',mechanism='contact',actor=role['id'])
    engine.store.save(saved)
    view=act(engine,game,'choose',choice='seize')['dungeons']['session']
    saved,site=loaded(engine,game)
    assert site['step']==1 and not site['pending'] and not site['party']
    assert site['roles'][role['id']]['state']=='observed'
    assert any(p['status']=='各自行动' for p in view['people'])
    assert role['id'] not in saved.world_npcs
    assert GameState.from_dict(saved.to_dict()).dungeon_state==saved.dungeon_state


def test_invitation_frozen_with_near_rank_sender_and_no_materialization(local,monkeypatch):
    engine,game=local;novice(engine,game);cfg=force_quality(monkeypatch,'legendary')
    monkeypatch.setitem(WORLD_SYSTEMS['seeded_dungeons'],'invitation_chance',10)
    cfg['invitation_chance']=10
    before=set(game.world_npcs)
    invite_tick(game,engine.maps)
    mail=game.dungeon_state['mail'][-1]
    site=game.dungeon_state['instances'][mail['dungeon_id']]
    assert site['roles'][mail['sender_id']]['realm']==1 and site['quality']=='legendary'
    assert set(game.world_npcs)==before
    engine.store.save(game);frozen=copy.deepcopy(game.dungeon_state)
    for _ in range(3):engine.get_game(game.id)
    assert engine.store.load(game.id).dungeon_state==frozen


def test_outer_conflict_and_join_queue_exclude_distant_strong_cultivator(local):
    engine,game=local;novice(engine,game);discover(engine,game);act(engine,game,'enter')
    saved,site=loaded(engine,game);a,strong,b,*rest=site['roles'].values()
    a.update(realm=1,true_realm=1);strong.update(realm=4,true_realm=4,offer_step=0)
    b.update(realm=2,true_realm=2)
    for r in [a,b,*rest]:r['offer_step']=99
    site['nodes'][0].update(kind='conflict',mechanism='conflict',actor=a['id'])
    engine.store.save(saved)
    act(engine,game,'choose',choice='seize')
    saved,site=loaded(engine,game)
    assert site['pending']['kind']=='conflict' and site['pending']['other']!=strong['id']
    site['pending']=None;site['nodes'][0]['kind']='trace';engine.store.save(saved)
    act(engine,game,'choose',choice='bypass')
    saved,site=loaded(engine,game)
    assert site['pending'] is None and strong['id'] not in site['party']

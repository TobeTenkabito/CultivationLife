"""Persisted public command acceptance tests for the replacement expedition."""
import copy
import json
from pathlib import Path
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Player
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.content_registry import WORLD_SYSTEMS, ACTIONS
from cultivation_life.system.dungeons.generation import generate, config
from cultivation_life.system.dungeons.people import pressures
from cultivation_life.dungeon_schema import decode

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def local(tmp_path):
    engine=GameEngine(ROOT,tmp_path/'saves')
    game=engine.store.load(engine.create_game('探境验收','heavenly','dao',342,preset_id='core')['id'])
    game.player.realm_index=4;game.player.layer=9
    game.player.hp=max_hp(game.player);game.player.mp=max_mp(game.player)
    game.settings['silent_events']=True
    engine.store.save(game)
    return engine,game


def discover(engine,game):
    state=engine.get_game(game.id)['dungeons']
    return engine.dungeon_action(game.id,'discover',dict(world=state['world'],location_id=state['location_id'],slot=state['used']))


def act(engine,game,action,**extra):
    saved=engine.store.load(game.id);state=saved.dungeon_state
    site=state['instances'][state['active']] if state.get('active') else list(state['instances'].values())[-1]
    return engine.dungeon_action(game.id,action,dict(dungeon_id=site['id'],revision=site['revision'],**extra))


def test_replacement_seed_freeze_zero_time_and_cooldown(local):
    engine,game=local
    assert 'treasure' not in ACTIONS
    with pytest.raises(ValueError,match='替代'):engine.advance(game.id,'treasure')
    view=discover(engine,game)
    assert view['dungeons']['sites'][0]['quality']=='未探明'
    frozen=copy.deepcopy(engine.store.load(game.id).dungeon_state)
    for _ in range(3):engine.get_game(game.id)
    assert engine.store.load(game.id).dungeon_state==frozen
    assert not engine.store.load(game.id).relationship_npcs
    act(engine,game,'enter')
    site=engine.get_game(game.id)['dungeons']['session']
    old=dict(dungeon_id=site['id'],revision=site['revision'],choice='bypass')
    engine.dungeon_action(game.id,'choose',old)
    with pytest.raises(ValueError,match='过期'):engine.dungeon_action(game.id,'choose',old)
    act(engine,game,'exit')
    saved=engine.store.load(game.id)
    assert saved.player.age==game.player.age
    assert saved.dungeon_state['ready_age']==game.player.age+WORLD_SYSTEMS['time_units']['4']
    discover(engine,game)
    with pytest.raises(ValueError,match='行动单位'):act(engine,game,'enter')


def test_map_caps_and_world_legendary_generation_receipts(local,monkeypatch):
    engine,game=local;scope=game.player.world+':'+game.player.location_id
    cfg=copy.deepcopy(config())
    cfg['profiles'][scope]['weights']=[0,0,0,1]
    monkeypatch.setattr('cultivation_life.system.dungeons.generation.config',lambda:cfg)
    for _ in range(2):discover(engine,game)
    # Exhausted legendary weight falls back to ordinary generation, never quota overflow.
    cfg['profiles'][scope]['weights']=[1,0,0,1]
    discover(engine,game)
    state=engine.store.load(game.id).dungeon_state
    assert len(state['legends']['human'])==2
    assert sum(s['quality']=='legendary' for s in state['instances'].values())==2
    for _ in range(cfg['profiles'][scope]['slots']-3):discover(engine,game)
    with pytest.raises(ValueError,match='用尽'):discover(engine,game)
    assert all(n['reward']['realm']==5 for s in state['instances'].values() if s['quality']=='legendary' for n in s['nodes'])
    for site in state['instances'].values():
        if site['quality']=='legendary':
            guard=site['roles'][site['nodes'][-1]['actor']]
            assert guard['true_realm']>site['realm'] and guard['realm']==5
    assert len({n['text'] for s in state['instances'].values() for n in s['nodes']})==len(state['text_fingerprints'])


def test_hidden_intentions_and_join_log_identity_roundtrip(local):
    engine,game=local;discover(engine,game);act(engine,game,'enter')
    for _ in range(8):
        saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][saved.dungeon_state['active']]
        view=engine.get_game(game.id)['dungeons']
        public=json.dumps(view,ensure_ascii=False)
        for forbidden in ('assassinate','purpose','resolve','true_realm','power_factor','offer_step'):
            assert forbidden not in public
        if site['pending'] and site['pending']['kind']=='join':break
        act(engine,game,'choose',choice='bypass')
    else:pytest.fail('seed should encounter a join request')
    role=site['roles'][site['pending']['actor']]
    assert role['npc_id'] is None
    view=act(engine,game,'choose',choice='accept')
    assert any('加入队伍' in l['text'] for l in view['dungeons']['session']['logs'])
    saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][site['id']]
    original=site['roles'][role['id']]['npc_id']
    assert original in saved.world_npcs
    assert GameState.from_dict(saved.to_dict()).dungeon_state==saved.dungeon_state
    with pytest.raises(ValueError,match='副本'):engine.advance(game.id,'rest')
    act(engine,game,'exit')
    saved=engine.store.load(game.id)
    assert original in saved.world_npcs
    assert saved.dungeon_state['instances'][site['id']]['roles'][role['id']]['state']=='left'


def test_actual_reward_and_stale_click_cannot_duplicate(local):
    engine,game=local;discover(engine,game);act(engine,game,'enter')
    awarded=False
    for _ in range(20):
        saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][saved.dungeon_state['active']]
        pending=site['pending']
        if pending:
            choice='decline' if pending['kind']=='join' else 'fight' if pending['kind']!='conflict' else 'support_actor'
        else:choice='seize'
        token=dict(dungeon_id=site['id'],revision=site['revision'],choice=choice)
        view=engine.dungeon_action(game.id,'choose',token)
        after=engine.store.load(game.id)
        if after.dungeon_state['instances'][site['id']]['claims']:
            awarded=True
            before=after.player.to_dict()
            with pytest.raises(ValueError,match='过期'):engine.dungeon_action(game.id,'choose',token)
            assert engine.store.load(game.id).player.to_dict()==before
            break
        if not view['dungeons']['active']:break
    assert awarded


def test_old_infamy_values_never_become_renown(local):
    _,game=local;raw=game.player.to_dict();raw.pop('infamy');raw.pop('infamy_by_scope')
    raw.update(fame=135,fame_by_world={'human':135,'spirit':7,'rift:abc':8})
    p=Player.from_dict(raw)
    assert p.infamy==135 and p.infamy_by_scope['rift:abc']==8
    renown=p.renown;p.infamy=99999
    assert p.renown==renown and not p.renown_records
    assert 'fame' not in p.to_dict()
    with pytest.raises(ValueError,match='冲突'):Player.from_dict({**raw,'infamy':1})


def test_assassin_generation_floor_and_irreducible_intent(local):
    engine,game=local
    found=[]
    for seed in range(20):
        game.seed=seed
        site=generate(game,engine.maps.location(game.player.world,game.player.location_id),0,0)
        for role in site['roles'].values():
            if role['purpose']=='assassinate':
                found.append(role['id'])
                assert (role['realm'],role['layer']) >= (game.player.realm_index,game.player.layer)
                role['trust']=100;site['agreements'][role['id']]=1
                assert pressures(game,site,role)['intent']>=85
    assert found



def test_invalid_active_reference_rejected(local):
    engine,game=local;discover(engine,game)
    state=engine.store.load(game.id).dungeon_state;state['active']='missing'
    with pytest.raises(ValueError):decode(state)


def test_complete_route_real_combat_claim_and_exit(local,monkeypatch):
    engine,game=local
    from cultivation_life.rules import add_item
    from cultivation_life.system.dungeons.rewards import equipment_anchor
    # Route settlement uses a prepared adventurer; success must not depend on
    # the removed combat-power-to-HP fallback of a randomly acquired relic.
    add_item(game.player,equipment_anchor(game.player.realm_index,game.player.world).id)
    game.player.body_training=48
    game.player.hp=max_hp(game.player);game.player.mp=max_mp(game.player)
    add_item(game.player,'healing_pill',12);engine.store.save(game)
    discover(engine,game)
    # Exercise real combat and the complete reward/study lifecycle with a
    # controlled opposition, independently of the seed's population balance.
    prepared=engine.store.load(game.id)
    for site in prepared.dungeon_state['instances'].values():
        for role in site['roles'].values():
            role.update(realm=3,true_realm=3,layer=1,power_factor=.9,purpose='seek')
    engine.store.save(prepared);act(engine,game,'enter')
    for _ in range(35):
        saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][saved.dungeon_state['active']]
        if site['step']==len(site['nodes']) and not site['pending']:break
        if saved.player.hp<max_hp(saved.player)*.7:
            engine.use_item(game.id,'healing_pill')
            continue
        pending=site['pending']
        choice={'join':'decline','conflict':'support_actor','settlement':'part','guardian':'fight','ambush':'fight'}[pending['kind']] if pending else 'seize'
        result=act(engine,game,'choose',choice=choice)
        assert result['dungeons']['active'],result.get('last_combat_report')
    else:pytest.fail('route did not terminate')
    assert site['nodes'][-1]['reward']['id'] in site['claims']
    assert saved.last_combat_report
    manuals=saved.dungeon_state['manuals']
    assert manuals
    act(engine,game,'exit')
    key=next(iter(manuals))
    engine.dungeon_action(game.id,'learn',{'manual_id':key})
    saved=engine.store.load(game.id)
    assert any(t.id==key for t in saved.player.known_techniques)
    with pytest.raises(ValueError,match='已学习'):engine.dungeon_action(game.id,'learn',{'manual_id':key})
    assert saved.player.age==game.player.age
    saved.player.opportunity=100000
    engine.store.save(saved)
    engine.dungeon_action(game.id,'study',{'manual_id':key})
    prepared=engine.store.load(game.id);job=prepared.dungeon_state['manuals'][key]['study']
    assert job and prepared.player.opportunity<100000
    for _ in range(2):engine.get_game(game.id)
    assert engine.store.load(game.id).dungeon_state['manuals'][key]['study']==job
    monkeypatch.setattr(engine,'_advance_world_year',lambda *args,**kwargs:True)
    monkeypatch.setattr(engine,'_select_event',lambda *args,**kwargs:None)
    engine.advance(game.id,'dungeon_study',10)
    studied=engine.store.load(game.id)
    assert studied.dungeon_state['manuals'][key]['level']==2
    assert studied.dungeon_state['manuals'][key]['study'] is None
    assert studied.player.age-prepared.player.age==job['required']
    with pytest.raises(ValueError,match='选择'):engine.advance(game.id,'dungeon_study',1)


def test_invitation_created_on_real_time_not_get_and_declining_keeps_slot(local,monkeypatch):
    engine,game=local
    cfg=copy.deepcopy(config());cfg['invitation_chance']=10
    monkeypatch.setattr('cultivation_life.system.dungeons.runtime.config',lambda:cfg)
    for _ in range(2):engine.get_game(game.id)
    assert not engine.store.load(game.id).dungeon_state
    # Isolate unrelated yearly incidents, preserving the real advance/save command.
    monkeypatch.setattr(engine,'_advance_world_year',lambda *args,**kwargs:True)
    monkeypatch.setattr(engine,'_select_event',lambda *args,**kwargs:None)
    engine.advance(game.id,'rest',1)
    saved=engine.store.load(game.id);state=saved.dungeon_state
    assert len(state['mail'])==1
    mail=state['mail'][0];site=state['instances'][mail['dungeon_id']]
    blueprint=copy.deepcopy(site['nodes'])
    engine.dungeon_action(game.id,'read_mail',{'mail_id':mail['id']})
    assert not engine.get_game(game.id)['dungeons']['unread']
    engine.dungeon_action(game.id,'decline_invite',dict(dungeon_id=site['id'],revision=site['revision']))
    saved=engine.store.load(game.id)
    assert saved.dungeon_state['instances'][site['id']]['nodes']==blueprint
    assert saved.dungeon_state['maps'][site['world']+':'+site['location_id']]==[site['id']]


def test_two_realm_caps_are_independent_and_lower_world_immortal_has_finite_domain(local,monkeypatch):
    engine,game=local
    cfg=copy.deepcopy(config())
    for world in ('human','spirit','celestial'):
        game.player.world=world;game.player.location_id=engine.maps.default_location(world)
        scope=world+':'+game.player.location_id;cfg['profiles'][scope]['weights']=[0,0,0,1]
    monkeypatch.setattr('cultivation_life.system.dungeons.generation.config',lambda:cfg)
    from cultivation_life.system.dungeons.people import materialize,domains
    from cultivation_life.system.combat.contracts import resolve_capabilities,voisinage_definitions
    game.player.world='spirit';game.player.location_id=engine.maps.default_location('spirit')
    site=generate(game,engine.maps.location('spirit',game.player.location_id),0,0)
    strongest=list(site['roles'].values())[-1]
    assert strongest['true_realm']==9 and strongest['realm']==8 and strongest['layer']==9
    assert not game.relationship_npcs
    npc=materialize(game,site,strongest)
    definitions=voisinage_definitions({'voisinages':domains(site)})
    caps=resolve_capabilities(npc.transcendence,definitions)
    assert caps.current==1200 and caps.voisinages and npc.realm_index==8
    assert materialize(game,site,strongest) is npc
    assert all(n['reward']['realm']==8 for n in site['nodes'])
    game.player.world='celestial';game.player.location_id=engine.maps.default_location('celestial')
    next_site=generate(game,engine.maps.location('celestial',game.player.location_id),0,0)
    assert next_site['quality']=='legendary' and all(n['reward']['realm']==12 for n in next_site['nodes'])


def test_downward_immortal_uses_original_finite_resources_in_real_command(local,monkeypatch):
    engine,game=local
    game.player.realm_index=8;game.player.layer=9;game.player.world='spirit';game.player.location_id=engine.maps.default_location('spirit')
    game.player.hp=max_hp(game.player);game.player.mp=max_mp(game.player);engine.store.save(game)
    cfg=copy.deepcopy(config());cfg['profiles']['spirit:'+game.player.location_id]['weights']=[0,0,0,1]
    monkeypatch.setattr('cultivation_life.system.dungeons.generation.config',lambda:cfg)
    discover(engine,game);act(engine,game,'enter')
    saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][saved.dungeon_state['active']]
    role=list(site['roles'].values())[-1]
    role.update(known=True,state='hostile')
    site['pending']=dict(kind='guardian',actor=role['id']);engine.store.save(saved)
    act(engine,game,'choose',choice='fight')
    saved=engine.store.load(game.id)
    npc=saved.world_npcs[role['id']]
    assert npc.realm_index==8 and npc.family_traits['dungeon_origin']['true_realm']==9
    assert 0<=npc.transcendence['current']<1200
    assert saved.player.age==game.player.age and saved.last_combat_report


def test_explicit_invite_reuses_original_person_and_letter(local):
    engine,game=local
    npc=next(n for sect in game.sects.values() if sect.world=='human' for n in sect.npcs if n.alive)
    npc.location_id=game.player.location_id;npc.encountered_player=True;npc.affinity=100
    engine.store.save(game);discover(engine,game)
    act(engine,game,'invite',actor_id=npc.id)
    saved=engine.store.load(game.id);site=list(saved.dungeon_state['instances'].values())[0]
    assert site['roles'][npc.id]['npc_id']==npc.id and site['roles'][npc.id]['existing']
    assert npc.id not in saved.relationship_npcs
    assert saved.dungeon_state['mail'][-1]['sender_id']==npc.id
    with pytest.raises(ValueError,match='已经邀请'):act(engine,game,'invite',actor_id=npc.id)


def test_invited_person_unavailable_before_entry_is_not_copied(local):
    from cultivation_life.relationship_records import find_person
    engine,game=local
    npc=next(n for sect in game.sects.values() if sect.world=='human' for n in sect.npcs if n.alive)
    npc.location_id=game.player.location_id;npc.encountered_player=True;npc.affinity=100
    engine.store.save(game);discover(engine,game);act(engine,game,'invite',actor_id=npc.id)
    saved=engine.store.load(game.id);site=list(saved.dungeon_state['instances'].values())[0]
    site['roles'][npc.id]['state']='invited'
    original=find_person(saved,npc.id);original.alive=False
    engine.store.save(saved)
    view=act(engine,game,'enter')
    saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][saved.dungeon_state['active']]
    assert site['roles'][npc.id]['state']=='missing' and npc.id not in site['party']
    assert not find_person(saved,npc.id).alive
    assert npc.id not in saved.world_npcs and npc.id not in saved.relationship_npcs
    assert any('没有按约出现' in row['text'] for row in view['dungeons']['session']['logs'])
    act(engine,game,'exit')


def test_real_betrayal_only_exposes_after_attack(local):
    from cultivation_life.system.dungeons.people import materialize
    engine,game=local;discover(engine,game);act(engine,game,'enter')
    saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][saved.dungeon_state['active']]
    role=next(iter(site['roles'].values()))
    role.update(purpose='assassinate',resolve=95,realm=4,layer=9,true_realm=4,
                preparation=100,trust=100,caution=0,state='joined',known=True)
    materialize(saved,site,role);site['party']=[role['id']];site['agreements'][role['id']]=1
    engine.store.save(saved)
    before=engine.get_game(game.id)['dungeons']['session']
    assert not before['people'][0]['exposed']
    assert 'assassinate' not in json.dumps(before)
    after=act(engine,game,'choose',choice='bypass')['dungeons']['session']
    exposed=next(r for r in after['people'] if r['id']==role['id'])
    assert exposed['exposed'] and exposed['state']=='hostile' and after['party_count']==1
    assert any('封住你的退路' in row['text'] for row in after['logs'])
    with pytest.raises(ValueError,match='争斗'):act(engine,game,'exit')


def test_support_weaker_side_real_combat_grants_bounded_share_and_gratitude(local):
    from cultivation_life.relationship_records import find_person
    engine,game=local;discover(engine,game);act(engine,game,'enter')
    saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][saved.dungeon_state['active']]
    a,b=list(site['roles'].values())[:2]
    for index,role in enumerate((a,b)):
        role.update(realm=1,layer=index+1,true_realm=1,purpose='observe',trust=50,
                    preparation=0,resolve=0,desire=0,known=True,state='contact',power_factor=.5 if index==0 else 1.5)
    site['pending']=dict(kind='conflict',actor=a['id'],other=b['id'])
    trust=a['trust'];engine.store.save(saved)
    act(engine,game,'choose',choice='support_actor')
    saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][site['id']]
    assert saved.last_combat_report and len(site['claims'])==2
    assert site['roles'][a['id']]['trust']==trust+25
    assert find_person(saved,a['id']).affinity==trust+25
    assert any('另一份' in row['text'] for row in site['logs'])
    assert saved.player.age==game.player.age

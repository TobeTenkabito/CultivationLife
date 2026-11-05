"""Actual NPC development commands retain Debug isolation and ordinary boundaries."""
import copy
from pathlib import Path

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.debug.runtime import Runtime, atomic_json
from cultivation_life.debug.commands import build_registry
from cultivation_life.debug.registry import CommandError
from cultivation_life.debug.engine_adapter import SessionEngine
from cultivation_life.debug.client import DebugClient
from cultivation_life.models import GameState
from cultivation_life.rules import add_item
from cultivation_life.relationship_records import find_person
from test_npc_development_special_areas import make_game, enter_guixu, enter_rift
from test_debug_console import environment, api_environment

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    engine=GameEngine(ROOT,tmp_path/'normal');g=make_game(engine)
    manager=Runtime(ROOT,tmp_path/'debug',engine.store);sid=manager.start(g.id)['session_id']
    return engine,manager,sid,g.id


def write(manager,sid,args,key='once',command='npc development'):
    return manager.execute(command,arguments=args,session_id=sid,
        expected_revision=manager.load(sid)['revision'],request_key=key)


def test_inspection_is_pure_and_lists_actual_quotes_and_energy(setup):
    e,m,sid,gid=setup
    before=m._path(sid).read_bytes();source=e.store._path(gid).read_bytes()
    for _ in range(2):
        value=m.execute('npc development inspect',session_id=sid)['data']
        n=next(n for n in value['view']['targets'] if n['id']=='outside-student')
        assert n['portrait'] and any(q['can_train'] for q in n['quotes'])
        energy=next(n['energy'] for n in value['view']['targets'] if n['kind']=='puppet')
        assert energy['current']==47 and energy['replacements']
    assert m._path(sid).read_bytes()==before and e.store._path(gid).read_bytes()==source


@pytest.mark.parametrize('fails',[False,True])
def test_preview_discards_preparation_writes_even_on_failure(setup,monkeypatch,fails):
    e,m,sid,gid=setup;before=m._path(sid).read_bytes();source=e.store._path(gid).read_bytes()
    def prepare(engine,identity,payload=None):
        g=engine.store.load(identity);g.player.opportunity+=100;engine.store.save(g)
        if fails:raise ValueError('injected preview failure')
        return {'targets':[]}
    monkeypatch.setattr(SessionEngine,'npc_development',prepare)
    if fails:
        with pytest.raises(RuntimeError):m.execute('npc development inspect',session_id=sid)
    else:m.execute('npc development inspect',session_id=sid)
    assert m._path(sid).read_bytes()==before and e.store._path(gid).read_bytes()==source


def test_growth_matches_normal_command_replays_and_restores_snapshot(setup,tmp_path):
    e,m,sid,gid=setup;source=e.store._path(gid).read_bytes()
    m.execute('snapshot create npc_before',session_id=sid)
    before=copy.deepcopy(m.load(sid)['current']);revision=m.load(sid)['revision']
    args=dict(action='train',kind='npc',target_id='outside-student',axis='body',method='infuse',batches=1)
    result=write(m,sid,args)
    after=copy.deepcopy(m.load(sid)['current']);saved=GameState.from_dict(copy.deepcopy(after['game']))
    assert find_person(saved,'outside-student').body_training==20
    normal=GameEngine(ROOT,tmp_path/'comparison');normal.store.save(GameState.from_dict(copy.deepcopy(before['game'])))
    normal.npc_development(gid,{**args,'revision':normal.npc_development(gid)['revision']})
    expected=normal.store.load(gid)
    assert saved.player.opportunity==expected.player.opportunity
    assert find_person(saved,'outside-student').to_dict()==find_person(expected,'outside-student').to_dict()
    replay=m.execute('npc development',arguments=args,session_id=sid,expected_revision=revision,request_key='once')
    assert replay['replayed'] and m.load(sid)['current']==after
    with pytest.raises(CommandError,match='revision conflict'):
        m.execute('npc development',arguments=args,session_id=sid,expected_revision=revision,request_key='stale')
    assert m.load(sid)['current']==after
    with pytest.raises(RuntimeError):write(m,sid,args|{'revision':'stale-game-revision'},'stale-game')
    assert m.load(sid)['current']==after
    m.execute('snapshot restore npc_before',session_id=sid)
    assert m.load(sid)['current']==before and e.store._path(gid).read_bytes()==source


def test_teaching_energy_replacement_and_supply_use_original_owners(setup):
    e,m,sid,gid=setup;source=e.store._path(gid).read_bytes()
    write(m,sid,dict(action='teach',kind='prisoner',target_id='held',content_id='TECH_BASIC_QI'),'teach')
    write(m,sid,dict(action='charge',kind='puppet',target_id='machine',source='spare:saved-energy'),'energy')
    write(m,sid,dict(setting='puppet_supply',enabled=False),'supply','setting set')
    g=GameState.from_dict(m.load(sid)['current']['game'])
    assert find_person(g,'held',include_inactive=True).technique_levels['TECH_BASIC_QI']==1
    puppet=g.player.puppets[0]
    assert puppet['operating_energy']==23
    assert any(row['durability']==47 for row in puppet['energy_spares'])
    assert not g.player.combat_plan['puppet_supply']
    assert not m.execute('npc development inspect',session_id=sid)['data']['supply_enabled']
    assert e.store._path(gid).read_bytes()==source


@pytest.mark.parametrize('area',['guixu','lost','secluded'])
def test_debug_respects_dungeon_world_and_instance_guards(setup,area):
    e,m,sid,gid=setup;g=e.store.load(gid)
    g=enter_guixu(e,g) if area=='guixu' else enter_rift(e,g,area)
    sid=m.start(gid)['session_id'];before=copy.deepcopy(m.load(sid)['current']);source=e.store._path(gid).read_bytes()
    shown=m.execute('npc development inspect',session_id=sid)['data']['view']
    assert next(n for n in shown['targets'] if n['id']=='outside-student')['reason']
    for args in [dict(action='train',kind='prisoner',target_id='held',axis='body',method='infuse',batches=1),
                 dict(action='teach',kind='npc',target_id='outside-student',content_id='TECH_BASIC_QI'),
                 dict(action='charge',kind='puppet',target_id='machine',source='spare:saved-energy')]:
        with pytest.raises((CommandError,RuntimeError)):write(m,sid,args,key=args['action'])
        assert m.load(sid)['current']==before
    assert e.store._path(gid).read_bytes()==source


@pytest.mark.parametrize('path,world',[('dao','celestial'),('demonic','asura'),('monster','nether'),('ghost','reincarnation')])
def test_upper_growth_and_voisinage_use_same_transcendence_record(setup,path,world):
    e,m,sid,gid=setup
    # Explicit isolated fixture editing; no source save or progression bypass in commands.
    session=m.load(sid);g=GameState.from_dict(session['current']['game'])
    g.player.world=world;g.player.path=path;g.player.realm_index=12;g.player.layer=1
    g.player.location_id=e.maps.default_location(world);g.player.immortal_power_converted=True
    n=find_person(g,'outside-student');n.world=world;n.location_id=g.player.location_id
    n.path=path;n.realm_index=9;n.layer=8;n.body_training=100;n.immortal_body_level=0
    n.transcendence=dict(conversion=1.,capacity=1000.,current=123.,force_tier=2,attack_cost=10.)
    for axis in ('body','cultivation','domain'):add_item(g.player,f'npc_training_{path}_{axis}_3',5)
    session['current']['game']=g.to_dict();atomic_json(m._path(sid),session)
    for axis in ('cultivation','body','domain'):
        write(m,sid,dict(action='train',kind='npc',target_id=n.id,axis=axis,method='material',batches=1),axis)
    saved=GameState.from_dict(m.load(sid)['current']['game']);n=find_person(saved,n.id)
    assert n.layer==9 and n.immortal_body_level==2 and n.transcendence['current']==123
    view=m.execute('npc development inspect',session_id=sid)['data']['view']
    assert any(d['rank'] for d in next(row for row in view['targets'] if row['id']==n.id)['domains'])


@pytest.mark.parametrize('bad',[{'batches':True},{'batches':2},{'method':'family'},{'kind':'remote'},
    {'source':{}},{'teleport':True},{'revision':3},{'action':'set_realm'}])
def test_typed_discovery_rejects_forged_inputs(bad):
    args=dict(action='train',kind='npc',target_id='student',axis='body',method='infuse',batches=1)
    with pytest.raises(CommandError):build_registry().structured('npc development',args|bad)


def test_agent_discovers_same_typed_commands(monkeypatch):
    client=DebugClient()
    monkeypatch.setattr(client,'call',lambda *args,**kwargs:{'catalog':build_registry().catalog()})
    tools={row['name']:row for row in client.tools()}
    action=tools['cultivation_npc_development'];inspect=tools['cultivation_npc_development_inspect']
    assert inspect['annotations']['readOnlyHint']
    assert not action['annotations']['readOnlyHint']
    assert {'expected_revision','request_key','session_id'}<=set(action['inputSchema']['required'])
    assert action['inputSchema']['properties']['arguments']['properties']['batches']['enum']==[1,5,10,None]


def test_isolated_http_window_reads_and_trains_without_touching_source(environment,api_environment):
    e,_,_,_=environment;request,_=api_environment;g=make_game(e)
    status,result=request('/api/debug/command',{'command':'debug start','game_id':g.id})
    assert status==200,result
    sid=result['data']['session_id'];source=e.store._path(g.id).read_bytes()
    status,before=request('/api/debug/command',{'command':'debug status','session_id':sid})
    for _ in range(2):
        status,view=request(f'/api/games/{g.id}/npc-development',session_id=sid)
        assert status==200,view
    status,after=request('/api/debug/command',{'command':'debug status','session_id':sid})
    assert before==after
    status,result=request(f'/api/games/{g.id}/npc-development',dict(action='train',kind='npc',
        target_id='outside-student',axis='body',method='infuse',batches=1,revision=view['revision']),session_id=sid)
    assert status==200,result
    assert request('/api/games/another-game/npc-development',session_id=sid)[0]==400
    assert e.store._path(g.id).read_bytes()==source

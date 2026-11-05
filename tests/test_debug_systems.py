"""Detect branch/parameter omissions beyond route coverage; exercise real copies."""
import ast
import copy
from pathlib import Path

import pytest

from cultivation_life.debug.capabilities import BY_OPERATION
from cultivation_life.debug.commands import build_registry
from cultivation_life.debug.engine_adapter import SessionEngine
from cultivation_life.debug.registry import CommandError
from cultivation_life.debug.runtime import Runtime
from cultivation_life.models import GameState
from test_debug_console import environment, api_environment
from test_monster_body import ready_monster
from test_ghost_body import ready_ghost
from test_asura_manifestation import ready as ready_asura, route
from test_economy_network import economy, cash
from test_trial_sites import local as trial_local

ROOT=Path(__file__).resolve().parents[1]


def write(m,sid,command,args,key='test'):
    return m.execute(command,session_id=sid,arguments=args,
        expected_revision=m.load(sid)['revision'],request_key=key)


def test_http_payload_fields_are_exposed_by_typed_capabilities():
    tree=ast.parse((ROOT/'cultivation_life/server.py').read_text(encoding='utf-8-sig'))
    for node in ast.walk(tree):
        if not isinstance(node,ast.If) or not isinstance(node.test,ast.Compare):continue
        if ast.unparse(node.test.left)!='operation':continue
        try:operation=ast.literal_eval(node.test.comparators[0])
        except (ValueError,TypeError):continue
        if not isinstance(operation,str) or operation not in BY_OPERATION:continue
        keys=set()
        for stmt in node.body:
            for call in ast.walk(stmt):
                if (isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute)
                    and ast.unparse(call.func.value)=='payload' and call.func.attr=='get'
                    and call.args and isinstance(call.args[0],ast.Constant)):
                    keys.add(call.args[0].value)
        assert keys<={a.name for a in BY_OPERATION[operation].arguments},(operation,keys)


@pytest.mark.parametrize('operation,files',[
    ('upper-voisinage',['system/upper_voisinage.py','system/monster_true_form.py',
        'system/ghost_soul_form.py','system/monster_body_training.py','system/ghost_body_training.py']),
    ('asura',['engine/actions/asura.py']),
    ('aperture-action',['system/immortal_aperture.py']),
])
def test_high_system_action_branches_are_not_missing_from_enums(operation,files):
    actions=set()
    for filename in files:
        for node in ast.walk(ast.parse((ROOT/'cultivation_life'/filename).read_text(encoding='utf-8-sig'))):
            if (isinstance(node,ast.Compare) and isinstance(node.left,ast.Name)
                and node.left.id=='action' and isinstance(node.ops[0],ast.Eq)
                and isinstance(node.comparators[0],ast.Constant)):
                actions.add(node.comparators[0].value)
    choices=next(a.choices for a in BY_OPERATION[operation].arguments if a.name=='action')
    assert actions<=set(choices),actions-set(choices)


def test_spatial_social_actions_are_all_exposed():
    cap=BY_OPERATION['spatial-action'];choices=set(cap.arguments[0].choices)
    assert {'join_sect','leave_sect','study_sect','join_family','leave_family','study_family'}<=choices


@pytest.mark.parametrize('operation,filename',[
    ('fleet-action','economy/network_actions.py'),('fleet-action','economy/trade_orders.py'),
    ('fleet-action','economy/enterprise_actions.py'),('fleet-action','economy/depot.py'),
    ('fleet-action','economy/market_governance.py'),('fleet-action','economy/headquarters.py'),
    ('fleet-action','organization_heritage.py'),('family-action','family_system.py'),
    ('merchant-action','merchant_system.py'),('merchant-action','merchant_commission_system.py'),
    ('trial-site-action','trial_sites.py'),('sect-task','sect_tasks/actions.py'),
    ('soul','soul_actions.py'),('civilizations-action','monster_civilizations/actions.py'),
])
def test_delegated_payload_fields_are_not_silently_omitted(operation,filename):
    fields=set()
    for node in ast.walk(ast.parse((ROOT/'cultivation_life/system'/filename).read_text(encoding='utf-8-sig'))):
        if (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and ast.unparse(node.func.value)=='payload'
            and node.args and isinstance(node.args[0],ast.Constant)):
            fields.add(node.args[0].value)
        elif (isinstance(node,ast.Subscript) and isinstance(node.value,ast.Name) and node.value.id=='payload'
              and isinstance(node.slice,ast.Constant)):
            fields.add(node.slice.value)
    assert fields<={a.name for a in BY_OPERATION[operation].arguments}


@pytest.mark.parametrize('pointer',[None,'/combat_plan','/soul','/authored_techniques','/upper_voisinages'])
def test_public_inspection_is_pure(environment,pointer):
    e,m,sid,gid=environment;before=m._path(sid).read_bytes();source=e.store._path(gid).read_bytes()
    sections=m.execute('game inspect',session_id=sid)['data']['view']['sections']
    if pointer and pointer[1:] not in sections:
        # Absent sections are rejected, never silently redirected to another system.
        with pytest.raises((RuntimeError,CommandError)):m.execute('game inspect',session_id=sid,arguments={'pointer':pointer})
    else:
        result=m.execute('game inspect',session_id=sid,arguments={'pointer':pointer})
        assert result['type']=='preview' and result['data']['prepared'] is False
    assert m._path(sid).read_bytes()==before and e.store._path(gid).read_bytes()==source


@pytest.mark.parametrize('fails',[False,True])
def test_inspection_discards_engine_preparation_even_on_failure(environment,monkeypatch,fails):
    e,m,sid,gid=environment;before=m._path(sid).read_bytes();source=e.store._path(gid).read_bytes()
    def prepare(engine,identity):
        g=engine.store.load(identity);g.player.opportunity+=987;engine.store.save(g)
        if fails:raise ValueError('injected')
        return {'section':{'prepared':True}}
    monkeypatch.setattr(SessionEngine,'get_game',prepare)
    if fails:
        with pytest.raises(RuntimeError):m.execute('game inspect',session_id=sid)
    else:assert m.execute('game inspect /section',session_id=sid)['data']['view']=={'prepared':True}
    assert m._path(sid).read_bytes()==before and e.store._path(gid).read_bytes()==source


@pytest.mark.parametrize('kind',['monster','ghost'])
def test_real_high_body_growth_costs_replay_stale_and_snapshot(request,tmp_path,kind):
    e,g=request.getfixturevalue('ready_'+kind)
    if kind=='monster':g.player.immortal_body['monster']={'level':9};e.store.save(g)
    m=Runtime(ROOT,tmp_path/'debug',e.store);sid=m.start(g.id)['session_id']
    source=e.store._path(g.id).read_bytes();before=copy.deepcopy(m.load(sid)['current'])
    m.execute('snapshot create before_growth',session_id=sid)
    args={'action':kind+'_body_train','expected_level':9};revision=m.load(sid)['revision']
    result=write(m,sid,'upper voisinage',args)
    p=GameState.from_dict(copy.deepcopy(m.load(sid)['current']['game'])).player
    assert (p.immortal_body['monster']['level'] if kind=='monster' else p.immortal_body['level'])==10
    assert p.opportunity<before['game']['player']['opportunity'] and p.age==g.player.age
    state=copy.deepcopy(m.load(sid)['current'])
    assert m.execute('upper voisinage',session_id=sid,arguments=args,expected_revision=revision,request_key='test')['data']==result['data']
    with pytest.raises(RuntimeError):write(m,sid,'upper voisinage',args,'stale-level')
    assert m.load(sid)['current']==state
    m.execute('snapshot restore before_growth',session_id=sid)
    assert m.load(sid)['current']==before and e.store._path(g.id).read_bytes()==source


def test_real_asura_plan_and_combat_supply(ready_asura,tmp_path):
    e,g=ready_asura;route(g.player,name='kinnara',level=9);e.store.save(g)
    m=Runtime(ROOT,tmp_path/'debug',e.store);sid=m.start(g.id)['session_id'];source=e.store._path(g.id).read_bytes()
    write(m,sid,'asura action',{'action':'set_field_plan','target_id':'opening:2','expected_level':9})
    assert m.load(sid)['current']['game']['player']['asura_cultivation']['discipline_plan']['opening']==2
    before=copy.deepcopy(m.load(sid)['current'])
    with pytest.raises(RuntimeError):write(m,sid,'asura action',{'action':'set_field_plan','target_id':'opening:1','expected_level':8},'stale-plan')
    assert m.load(sid)['current']==before
    write(m,sid,'setting set',{'setting':'manual_combat_plan','enabled':True},'manual')
    write(m,sid,'combat plan',{'puppet_supply':False},'supply')
    assert not m.load(sid)['current']['game']['player']['combat_plan']['puppet_supply']
    assert e.store._path(g.id).read_bytes()==source


def test_actual_inheritance_uses_existing_aperture_entry(tmp_path):
    from cultivation_life.engine import GameEngine
    from test_spirit_inheritance import prepared
    e=GameEngine(ROOT,tmp_path/'saves');g,book=prepared(e,'asura','demonic')
    g.player.asura_cultivation.update(conversion=5,souls=10000,route='yaksha',level=4,domain_rank=4,domain_power=7,domain_name='本命')
    e.store.save(g);m=Runtime(ROOT,tmp_path/'debug',e.store);sid=m.start(g.id)['session_id']
    source=e.store._path(g.id).read_bytes()
    write(m,sid,'aperture action',{'action':'inherit','manual_id':book.id})
    saved=GameState.from_dict(copy.deepcopy(m.load(sid)['current']['game']))
    assert saved.player.asura_cultivation['domain_rank']==4
    assert saved.player.asura_cultivation['spirit_inheritance'] and e.store._path(g.id).read_bytes()==source


def test_catalog_gets_are_isolated_and_foreign_identity_is_rejected(environment,api_environment,tmp_path):
    request,_=api_environment;e,_,_,gid=environment;source=e.store._path(gid).read_bytes()
    status,result=request('/api/debug/command',{'command':'debug start','game_id':gid});assert status==200
    sid=result['data']['session_id'];m=Runtime(ROOT,tmp_path/'data'/'debug',e.store);before=m._path(sid).read_bytes()
    for path in ['/api/fleet-goods','/api/visual-assets','/api/authored-lineages','/api/domain-styles?id='+gid]:
        status,result=request(path,session_id=sid);assert status==200,(path,result)
    assert request('/api/domain-styles?id=foreign',session_id=sid)[0]==400
    assert request('/api/domain-styles?id='+gid+'&id=foreign',session_id=sid)[0]==400
    assert request('/api/fleet-goods/extra',session_id=sid)[0]==400
    assert request('/api/ui-preferences',{'pixel_theme':'dark'},session_id=sid)[0]==400
    assert m._path(sid).read_bytes()==before and e.store._path(gid).read_bytes()==source


def test_actual_fleet_order_and_estate_configuration_use_original_assets(economy,tmp_path):
    from cultivation_life.system.economy.enterprise_view import public_estates
    e,g=economy;m=Runtime(ROOT,tmp_path/'debug',e.store);sid=m.start(g.id)['session_id']
    source=e.store._path(g.id).read_bytes()
    def saved():return GameState.from_dict(copy.deepcopy(m.load(sid)['current']['game']))
    initial_cash=cash(g)
    write(m,sid,'fleet action',{'action':'create'},'fleet')
    fleet=next(f for f in saved().economy_v2['transport']['worlds']['human']['fleets'].values() if f['player_controlled'])
    dest=next(key for key in e.maps._locations['human'] if key!=g.player.location_id)
    args=dict(action='order_configure',fleet_id=fleet['id'],mode='once',kind='local',destination=dest,
        item='dew_grass_seed',quantity=1,buy_limit=10**12,sell_limit=0)
    write(m,sid,'fleet action',args,'order')
    order=saved().economy_v2['transport']['worlds']['human']['fleets'][fleet['id']]['trade_order']
    assert order['quantity']==1 and order['sell_limit']==0 and order['mode']=='once'
    offer=next(o for o in public_estates(saved(),e.maps)['offers'] if o['kind']=='farm')
    write(m,sid,'fleet action',dict(action='estate_buy',kind='farm',cost=offer['cost']),'buy')
    identity=f'human:{g.player.location_id}:farm';row=saved().economy_v2['estates'][identity]
    args=dict(action='estate_configure',estate_id=identity,revision=row['revision'],recipe=row['recipe'],
        enabled=False,auto_buy=True,auto_sell=False,batches=1,buy_limit=10**12,sell_limit=0,
        reserve_cash=125,expense_limit=999,sale_quota=17)
    write(m,sid,'fleet action',args,'configure');row=saved().economy_v2['estates'][identity]
    assert row['reserve_cash']==125 and row['sale_quota']==17 and not row['enabled']
    before=copy.deepcopy(m.load(sid)['current'])
    with pytest.raises(RuntimeError):write(m,sid,'fleet action',args,'stale-estate')
    assert m.load(sid)['current']==before and cash(saved())==initial_cash
    assert e.store._path(g.id).read_bytes()==source


def test_trial_choice_command_checks_event_and_revision_then_releases_busy_state(trial_local,tmp_path):
    from cultivation_life.system import trial_sites
    e,g=trial_local;m=Runtime(ROOT,tmp_path/'debug',e.store);sid=m.start(g.id)['session_id']
    source=e.store._path(g.id).read_bytes()
    write(m,sid,'trial site',dict(action='enter',world='human',floor=1),'enter')
    for index in range(5):
        state=copy.deepcopy(m.load(sid)['current']);game=GameState.from_dict(copy.deepcopy(state['game']))
        _,floor=trial_sites.current(game);_,_,outcomes=trial_sites.situation(floor)
        key=min(outcomes,key=lambda k:(outcomes[k][2],outcomes[k][3].get('treasure') is False))
        args=dict(action='choose',floor_id=floor['id'],revision=floor['revision'],event_id=game.pending_event['id'],choice_id=key)
        with pytest.raises(RuntimeError):write(m,sid,'trial site',{**args,'event_id':'stale-event'},f'bad-{index}')
        assert m.load(sid)['current']==state
        write(m,sid,'trial site',args,f'choose-{index}')
    state=m.load(sid)['current'];assert state['game']['pending_event'] is None
    assert state['game']['player']['age']==g.player.age
    assert e.store._path(g.id).read_bytes()==source


def test_new_schema_rejects_unreviewed_actions_and_malformed_parameters():
    registry=build_registry()
    for name,args in [('upper voisinage',{'action':'teleport_anywhere'}),
                      ('upper voisinage',{'action':'ghost_body_train','expected_level':True}),
                      ('teleport action',{'action':'construct','owner_id':123}),
                      ('intrigue resolution',{'kind':'sect','resolution_type':'x','years':-1}),
                      ('combat plan',{'puppet_supply':'false'})]:
        with pytest.raises(CommandError):registry.structured(name,args)

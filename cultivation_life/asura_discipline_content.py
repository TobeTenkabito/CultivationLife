"""Authored eightfold techniques and prebattle plans, without game or save IO."""
from dataclasses import asdict
from math import isfinite
from .system.combat.field_contracts import FieldDiscipline,MODES,PARAMETERS

ROUTES=('deva','naga','yaksha','gandharva','mahoraga','kinnara','garuda','asura')
STYLES=(('balanced','均衡'),('aggressive','强攻'),('steady','稳守'))


def build(state,config):
    route=state.get('route');row=config.get('field_disciplines',{}).get(route)
    if row is None:return None
    plan=state.get('discipline_plan',{})
    if not isinstance(plan,dict) or set(plan)-{'mode','opening'}:raise ValueError('八部权能预案无效')
    level=state.get('level',1)
    branch=next((i for i,b in enumerate(state.get('branches',{}).get(route,[])) if b['id']==state.get('branch')),0)
    policy=STYLES[branch%3][0]
    params=dict(row.get('parameters',{}));strength=.5+.0625*(state.get('branch_level',1)-1)
    for key,change in row.get('branch_modifiers',[{}, {}, {}])[branch%3].items():
        params[key]=round(params.get(key,PARAMETERS[row['kind']][key])+change*strength,8)
    return FieldDiscipline(id='asura:'+route,name=row['name'],kind=row['kind'],level=level,
        names=tuple(a['name'] for a in row['abilities']),mode=plan.get('mode','auto'),
        opening=plan.get('opening',0),policy=policy,parameters=params)


def validate(config):
    if not config:return
    rows=config.get('field_disciplines',{})
    if set(rows)!=set(ROUTES):raise ValueError('八部须分别声明本命权能')
    kinds=[]
    for route,row in rows.items():
        if set(row)-{'kind','name','abilities','parameters','branch_modifiers'}:raise ValueError('未知八部权能配置')
        abilities=row['abilities'];kinds.append(row['kind'])
        if len(abilities)!=3 or [a['level'] for a in abilities]!=[2,4,7] or len({a['id'] for a in abilities})!=3:
            raise ValueError('本命权能须按2／4／7级分别解锁')
        if any(set(a)!={'id','name','level','description'} or not isinstance(a['description'],str) or not a['description'] for a in abilities):
            raise ValueError('本命权能说明无效')
        mods=row.get('branch_modifiers',[{}, {}, {}])
        if len(mods)!=3 or mods[0]:raise ValueError('分支须声明均衡、强攻、稳守三种取舍')
        if any(not isinstance(m,dict) or set(m)-set(PARAMETERS[row['kind']]) or
               any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) for v in m.values()) for m in mods):
            raise ValueError('分支权能修正必须为已知参数的有限数值')
        for i in range(3):
            for branch_level in (1,9):
                state=dict(route=route,level=9,branch_level=branch_level,branch=f'b:{i}',
                    branches={route:[{'id':f'b:{j}'} for j in range(3)]})
                build(state,config)
    if len(set(kinds))!=8:raise ValueError('八部不得共用同一主机制')


def public(state,config):
    d=build(state,config)
    if d is None:return None
    row=config['field_disciplines'][state['route']]
    return dict(id=d.id,name=d.name,kind=d.kind,level=d.level,mode=d.mode,opening=d.opening,
        parameters=d.parameters,metrics=metrics(d),policy=d.policy,policy_name=dict(STYLES)[d.policy],
        abilities=[dict(a,unlocked=d.level>=a['level']) for a in row['abilities']],
        modes=[dict(id=mode,name=name,level=level,unlocked=d.level>=level) for mode,level,name in MODES[d.kind]])


def metrics(d):
    p=d.parameters
    if d.kind=='restoration_charge':return [f'实际恢复的{p["gain"]:.1%}转为天威，上限{p["capacity"]:.1%}；天罚门槛{p["threshold"]:.1%}，单次最多消费{p["release"]:.1%}。']
    if d.kind=='pressure_bond':return [f'潮缚基础增压{p["pressure"]:.1%}；索元额外耗费{p["surcharge"]:.1%}，存续{p["lifetime"]}轮；决堤门槛{p["threshold"]:.1%}。']
    if d.kind=='hunter':return [f'食煞回复本场可用元力容量的{p["restore"]:.1%}；均衡猎弱、强攻猎强、稳守优先肉身受损者。']
    if d.kind=='echo':return [f'反调继承自身基础施权强度的{p["scale"]:.1%}；断弦基础强度{p["rupture"]:.1%}，继续受实际威能修正。']
    if d.kind=='interdict':return [f'封锁真实命中留下{p["imprint"]}枚禁印，锁术消耗{p["marks"]}枚，印记存续{p["lifetime"]}轮；短封至多延续{p["duration"]}轮，解除后另有{p["interval"]}轮刷新间隔。']
    if d.kind=='melody':return [f'旋律基础强度{p["power"]:.1%}，转调另付{p["switch_cost"]:g}元力；每轮最多推进一曲，群奏受本域实际覆盖限制。']
    if d.kind=='field_breaker':return [f'啄界将{p["fraction"]:.1%}杀伤用于稳固损耗；断域门槛{p["threshold"]:.1%}，短封后另有{p["interval"]}轮刷新间隔。']
    return [f'歃血以标准施权费用折算{p["body_cost"]:.1%}真实肉身，随实际费用变化；俱灭另扣{p["aoe_cost"]:.1%}肉身，伤害继承{p["aoe_scale"]:.1%}，两项均不可自祭致死。',
        f'自动预案仅在肉身高于{p["auto_health"]:.1%}且元力低于可用容量{p["auto_energy"]:.1%}时优先血祭；也可手动选用血祭或只付元力。']


def select_plan(state,config,target,expected_level):
    if type(expected_level) is not int or expected_level!=state.get('level',1):raise ValueError('本命等级已变化，请刷新后重新选择')
    d=build(state,config)
    if d is None:raise ValueError('须先确定八部本命')
    action,sep,value=str(target).partition(':')
    if not sep or action not in {'mode','opening'}:raise ValueError('权能预案选项无效')
    plan=dict(state.get('discipline_plan',{}))
    if action=='mode':plan['mode']=value
    else:
        if d.kind!='melody' or d.level<2:raise ValueError('此本命尚不能选择三奏起曲')
        if value not in {'0','1','2'}:raise ValueError('起曲选项无效')
        plan['opening']=int(value)
    draft=dict(state,discipline_plan=plan)
    try:build(draft,config)
    except ValueError as error:raise ValueError('权能预案尚未解锁或选项无效') from error
    state['discipline_plan']=plan
    return '八部领域权能预案已保存；入战后冻结，不消耗精魂、机缘、时间或随机序列。'

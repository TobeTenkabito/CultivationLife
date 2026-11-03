"""Finite field-discipline descriptors and bounded battle-local memories."""
from dataclasses import dataclass,field
from math import isfinite

PARAMETERS={
    'restoration_charge':dict(gain=.65,capacity=.6,threshold=.14,release=.24,ordinary=.06),
    'pressure_bond':dict(pressure=.12,surcharge=.2,consume=.25,threshold=.25,bonus=.65,lifetime=2),
    'hunter':dict(restore=.1),
    'echo':dict(scale=.85,rupture=.24),
    'interdict':dict(imprint=2,marks=2,lifetime=3,duration=1,interval=2),
    'melody':dict(switch_cost=12.,power=.18),
    'field_breaker':dict(strain=.12,fraction=.45,threshold=.25,duration=1,interval=2),
    'blood':dict(body_cost=.045,auto_health=.55,auto_energy=.5,aoe_cost=.09,aoe_scale=.8),
}
MODES={
    'restoration_charge':(('auto',1,'自动'),('heal',1,'自疗蓄势'),('guardian',4,'优先护世'),('judgment',7,'优先天罚')),
    'pressure_bond':(('auto',1,'自动'),('suppress',1,'持续镇压'),('burst',7,'优先决堤')),
    'hunter':(('auto',1,'自动'),('focus',2,'集中猎首'),('ambush',4,'留招追命')),
    'echo':(('auto',1,'自动'),('cleanse',1,'优先净心'),('echo',4,'优先反调'),('rupture',7,'优先断弦')),
    'interdict':(('auto',1,'自动'),('seal',1,'积累禁印'),('technique',4,'封功'),('artifact',4,'封器'),('voisinage',7,'闭域')),
    'melody':(('auto',1,'自动应变'),('cycle',2,'按序轮奏'),('shift',4,'优先转调')),
    'field_breaker':(('auto',1,'自动'),('strike',1,'直接杀伤'),('strain',2,'优先啄界'),('break',4,'优先断域'),('pursue',7,'留招摧巢')),
    'blood':(('auto',1,'自动'),('mana',1,'只付元力'),('blood',2,'优先血祭'),('annihilate',7,'优先俱灭')),
}


@dataclass(frozen=True)
class FieldDiscipline:
    id: str
    name: str
    kind: str
    level: int
    names: tuple[str,...]
    mode: str='auto'
    opening: int=0
    policy: str='balanced'
    parameters: dict=field(default_factory=dict)

    def __post_init__(self):
        if any(not isinstance(v,str) or not 1<=len(v)<=64 for v in (self.id,self.name)):
            raise ValueError('Invalid field discipline identity')
        if self.kind not in PARAMETERS or type(self.level) is not int or not 1<=self.level<=9:
            raise ValueError('Invalid field discipline kind or level')
        if not isinstance(self.names,(list,tuple)) or len(self.names)!=3 or any(not isinstance(n,str) or not 1<=len(n)<=32 for n in self.names):
            raise ValueError('A field discipline requires three named abilities')
        if self.mode not in {m for m,level,_ in MODES[self.kind] if level<=self.level}:
            raise ValueError('Field discipline plan is locked or unknown')
        if type(self.opening) is not int or not 0<=self.opening<=2 or self.opening and (self.kind!='melody' or self.level<2):
            raise ValueError('Invalid melody opening')
        if self.policy not in {'balanced','aggressive','steady'}:raise ValueError('Unknown field discipline branch policy')
        if not isinstance(self.parameters,dict) or set(self.parameters)-set(PARAMETERS[self.kind]):
            raise ValueError('Unknown field discipline parameter')
        params={**PARAMETERS[self.kind],**self.parameters}
        integers={'imprint','marks','lifetime','duration','interval'}
        for key,value in params.items():
            maximum=8 if key in integers else 10000 if key=='switch_cost' else 1
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or not 0<value<=maximum:
                raise ValueError('Invalid field discipline parameter')
            if key in integers and type(value) is not int:raise ValueError('Field duration and counts require integers')
        if self.kind=='field_breaker' and params['threshold']>.5:raise ValueError('Field strain threshold exceeds the actual scale')
        if self.kind=='pressure_bond' and max(params['pressure'],params['consume'],params['threshold'])>.85:
            raise ValueError('Pressure threshold exceeds the actual scale')
        object.__setattr__(self,'names',tuple(self.names))
        object.__setattr__(self,'parameters',params)


def discipline(value):
    return value if value is None or isinstance(value,FieldDiscipline) else FieldDiscipline(**value)


def validate_memory(memory,units):
    if not isinstance(memory,dict):raise ValueError('Invalid field memory')
    floats={'charge'}
    ints={'melody','notes','melody_round','chorus','blood_round','ordinary_round','record_round'}
    maps={'marks','cooldowns','breaks'}
    if set(memory)-floats-ints-maps-{'hunt','echo'}:raise ValueError('Unknown field memory')
    if memory and set(memory)!=floats|ints|maps|{'hunt','echo'}:raise ValueError('Incomplete field memory')
    for key in floats:
        v=memory.get(key,0)
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or not 0<=v<=1:raise ValueError('Invalid stored field charge')
    for key in ints:
        v=memory.get(key,0);limit=2 if key=='melody' else 7 if key=='notes' else 1 if key=='chorus' else 10**9
        if type(v) is not int or not 0<=v<=limit:raise ValueError('Invalid field round memory')
    if memory.get('hunt') is not None and memory['hunt'] not in units:raise ValueError('Unknown hunted target')
    for key in maps:
        rows=memory.get(key,{})
        if not isinstance(rows,dict) or len(rows)>len(units) or set(rows)-set(units):raise ValueError('Unbounded field target memory')
        for row in rows.values():
            if key=='marks':
                if not isinstance(row,dict) or set(row)!={'count','expires'} or type(row['count']) is not int or not 0<=row['count']<=8:
                    raise ValueError('Invalid field imprint')
                value=row['expires']
            else:value=row
            if type(value) is not int or not 0<=value<=10**9:raise ValueError('Invalid field target deadline')
    echo=memory.get('echo',{})
    if not isinstance(echo,dict):raise ValueError('Invalid heard action memory')
    if echo:
        if not isinstance(echo,dict) or set(echo)!={'kind','restriction','source'} or echo['source'] not in units:
            raise ValueError('Invalid heard action')
        if echo['kind'] not in {'strike','suppress','seal','restrict','isolate','restore_body','restore_spirit','restore_field'}:
            raise ValueError('Unknown heard effect')
        if echo['restriction'] not in {None,'technique','artifact','support','communication','supply','voisinage','ordinary'}:
            raise ValueError('Unknown heard restriction')
        if (echo['kind'] in {'restrict','isolate'})!=(echo['restriction'] is not None):raise ValueError('Heard effect and restriction disagree')


def validate_leases(controls,debts,units):
    if not isinstance(controls,dict) or set(controls)-{'technique','artifact','voisinage'}:raise ValueError('Invalid timed control')
    for row in controls.values():
        if not isinstance(row,dict) or set(row)!={'source','expires','attempt'} or row['source'] not in units or type(row['attempt']) is not bool:
            raise ValueError('Invalid timed control owner')
        if type(row['expires']) is not int or not 1<=row['expires']<=10**9:raise ValueError('Invalid timed control deadline')
    if not isinstance(debts,dict) or len(debts)>len(units) or set(debts)-set(units):raise ValueError('Invalid field cost obligations')
    for row in debts.values():
        if not isinstance(row,dict) or set(row)!={'ratio','expires'}:raise ValueError('Invalid field cost obligation')
        value=row['ratio']
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or not 0<value<=1:
            raise ValueError('Invalid field cost ratio')
        if type(row['expires']) is not int or not 1<=row['expires']<=10**9:raise ValueError('Invalid field cost deadline')

"""Round eligibility and causal action allowances; no content or persistence IO."""
from dataclasses import dataclass, field, asdict
from math import isfinite

CHANNELS = frozenset({'ward','seal_resist','heal_preserve','heal_bonus','extra','erosion','silence',
    'authority','critical','critical_extra','free','exploit','restore_state','restore_energy',
    'state_guard','evade','retaliate_heal','retaliate_suppress','retaliate_seal','retaliate_power',
    'retaliate_choice','retaliate_spirit','retaliate_field','retaliate_technique','retaliate_artifact',
    'retaliate_support','retaliate_supply','retaliate_voisinage','release_cost','exchange_threshold',
    'recovery_bonus','split','forget','death_restore','karma_threshold','karma_power'})
REACTION_KINDS=('heal','spirit','field','suppress','seal','technique','artifact','support','supply','voisinage')
MAX_EXTRA_ACTIONS = 8


@dataclass(frozen=True)
class BodyMechanism:
    id: str
    name: str
    effects: dict = field(default_factory=dict)
    priority: int = 0
    chance: float = 1.
    requires: tuple[str, ...] = ()
    level: int = 0

    def __post_init__(self):
        if not isinstance(self.id,str) or not 1<=len(self.id)<=64 or not isinstance(self.name,str) or not 1<=len(self.name)<=64:
            raise ValueError('Invalid body mechanism identity')
        if type(self.priority) is not int or not 0<=self.priority<=100 or type(self.level) is not int or not 0<=self.level<=10:
            raise ValueError('Invalid body mechanism priority or training')
        if isinstance(self.chance,bool) or not isinstance(self.chance,(int,float)) or not isfinite(self.chance) or not 0<=self.chance<=1:
            raise ValueError('Invalid body mechanism probability')
        if not isinstance(self.effects,dict) or not self.effects or set(self.effects)-CHANNELS:
            raise ValueError('Unknown body mechanism output')
        for k,v in self.effects.items():
            upper=8 if k in {'extra','critical_extra'} else len(REACTION_KINDS) if k=='retaliate_choice' else 2 if k in {'ward','critical'} else 1
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or not 0<=v<=upper:
                raise ValueError('Invalid body mechanism output value')
            if k in {'extra','critical_extra','retaliate_choice'} and int(v)!=v:raise ValueError('Action allowances and choices must be integers')
        if not isinstance(self.requires,(list,tuple)) or len(self.requires)>8 or any(not isinstance(k,str) for k in self.requires):
            raise ValueError('Invalid mechanism dependencies')
        object.__setattr__(self,'requires',tuple(self.requires))
        object.__setattr__(self,'effects',dict(self.effects))


def mechanisms(caps):
    """Explicit neutral descriptors take precedence over the existing light projection."""
    if caps.body_mechanisms:return caps.body_mechanisms
    d=caps.divine_lights;levels=caps.divine_light_levels
    # Adapter for existing schema-12 battle snapshots and the public five-light API.
    specs=(('kun','坤元缃光',{'ward':2,'seal_resist':d.get('kun_resist',0)},1),
           ('zhen','震合缥光',{'heal_preserve':1,'heal_bonus':d.get('zhen_heal',0)},1),
           ('kan','坎道玄光',{'extra':1},d.get('kan',0)),
           ('li','离上朱光',{'erosion':d.get('li',0)},1),
           ('qian','乾古素光',{'silence':1},d.get('qian',0)))
    return tuple(BodyMechanism(k,n,e,i*10,c,level=levels.get(k,0))
                 for i,(k,n,e,c) in enumerate(specs) if d.get(k))


def validate_mechanisms(rows):
    if not isinstance(rows,(list,tuple)) or len(rows)>32:raise ValueError('Invalid body mechanism list')
    parsed=tuple(r if isinstance(r,BodyMechanism) else BodyMechanism(**r) for r in rows)
    if sum(r.effects.get('extra',0)+r.effects.get('critical_extra',0) for r in parsed)>MAX_EXTRA_ACTIONS:
        raise ValueError('Excessive declared action budget')
    if len(parsed)>32 or len({r.id for r in parsed})!=len(parsed):raise ValueError('Duplicate or excessive body mechanisms')
    by_id={r.id:r for r in parsed};done=set()
    def visit(key,chain):
        if key in chain:raise ValueError('Cyclic body mechanism dependencies')
        if key not in by_id:raise ValueError('Unknown body mechanism dependency')
        if key in done:return
        for parent in by_id[key].requires:visit(parent,chain|{key})
        done.add(key)
    for key in by_id:visit(key,set())
    return parsed


@dataclass
class ActionAllowance:
    source: str = ''
    requires_critical: bool = False
    free: bool = False
    spent: bool = False
    slot: int = 0
    requires_evade: bool = False
    ready: bool = True
    target: str = ''
    chain: tuple = ()


def enter(chain, owner, mechanism):
    """A mechanism may enter each causal branch once, independently per actor."""
    pair=(owner,mechanism)
    return None if pair in chain else (*chain,pair)


class BodyRound:
    def __init__(self,units,rng,first_side):
        self.rng=rng
        self.records={};self.raw={};self.effective={};self.muted={};self.allowances={}
        self.critical_completed=set();self.events=[]
        self.order=sorted(units,key=lambda k:(units[k].unit.side!=first_side,-units[k].unit.power,k))
        def roll(p):
            if p<=0:return False,None
            if p>=1:return True,None
            if rng is None:raise ValueError('Body mechanisms require explicit battle RNG')
            v=rng.random();return v<p,v
        for key in self.order:
            rows=validate_mechanisms(mechanisms(units[key].unit.capabilities));records={}
            def evaluate(row):
                if row.id in records:return records[row.id]
                parents=[evaluate(next(r for r in rows if r.id==parent)) for parent in row.requires]
                eligible=units[key].fighting and all(r['triggered'] for r in parents)
                exchange=None
                if 'exchange_threshold' in row.effects:
                    cap=units[key].unit.capabilities
                    capacity=cap.usable_capacity if cap.usable_capacity is not None else cap.capacity
                    ratio=units[key].current/capacity if capacity>0 else 1
                    opponents=[]
                    for other in self.order:
                        c=units[other].unit.capabilities
                        limit=c.usable_capacity if c.usable_capacity is not None else c.capacity
                        if (units[other].fighting and units[other].unit.side!=units[key].unit.side and limit>0
                                and (cap.reachable_ids is None or other in cap.reachable_ids)):
                            if ratio<units[other].current/limit:opponents.append(other)
                    preferred=[k for k in cap.target_ids if k in opponents] or opponents
                    eligible=eligible and not units[key].exchange_used and capacity>0 and ratio<row.effects['exchange_threshold'] and bool(preferred)
                    if eligible:
                        target=preferred[0];c=units[target].unit.capabilities
                        limit=c.usable_capacity if c.usable_capacity is not None else c.capacity
                        exchange=dict(target=target,own_ratio=ratio,other_ratio=units[target].current/limit)
                triggered,value=roll(row.chance) if eligible else (False,None)
                auxiliary={}
                if exchange:auxiliary['exchange']=exchange
                if triggered:
                    for channel in ('seal_resist',):
                        if channel in row.effects:
                            yes,v=roll(row.effects[channel]);auxiliary[channel]={'success':yes,'roll':v,'probability':row.effects[channel]}
                    # Conditional hit/target facts are evaluated when the event exists.
                    # Eligibility remains in the raw round plan for silence/amplification.
                records[row.id]=dict(id=row.id,name=row.name,level=row.level,priority=row.priority,
                    probability=row.chance,roll=value,triggered=triggered,eligible=eligible,
                    requires=list(row.requires),effects=dict(row.effects),auxiliary=auxiliary)
                return records[row.id]
            for row in sorted(rows,key=lambda r:(r.priority,r.id)):evaluate(row)
            self.records[key]=records
            raw={}
            for row in records.values():
                if row['triggered']:
                    for channel,value in row['effects'].items():raw[channel]=raw.get(channel,0)+value
            self.raw[key]=raw;self.effective[key]=dict(raw)
        # All raw rolls and dependency-derived values exist before any silence is applied.
        for key in self.order:
            for row in self.records[key].values():
                if not row['effects'].get('silence'):continue
                source=self.muted.get(key)
                if source:
                    self.events.append(dict(kind='silence_blocked',owner=key,source=source,mechanism=row['id']))
                else:
                    targets=[k for k in self.order if units[k].fighting and units[k].unit.side!=units[key].unit.side]
                    if row['triggered']:
                        for target in targets:self.muted.setdefault(target,key)
                    self.events.append(dict(kind='silence',owner=key,success=row['triggered'],
                        probability=row['probability'],roll=row['roll'],targets=targets,mechanism=row['id']))
        for key,records in self.records.items():
            if key in self.muted:self.effective[key]={}
            allowances=[ActionAllowance()]
            for row in records.values():
                row['suppressed_by']=self.muted.get(key)
                if not row['triggered'] or key in self.muted:continue
                outputs=row['effects'];p=outputs.get('free',0)
                free=p>=1 or bool(outputs.get('extra') and p>0 and self.rng.random()<p)
                allowances.extend(ActionAllowance(source=row['id'],free=free,chain=((key,row['id']),))
                                  for _ in range(int(outputs.get('extra',0))))
            for index,token in enumerate(allowances):token.slot=index
            if len(allowances)>MAX_EXTRA_ACTIONS+1:raise ValueError('Excessive round action budget')
            self.allowances[key]=allowances

    def value(self,key,channel,*,raw=False):
        return (self.raw if raw else self.effective).get(key,{}).get(channel,0.)

    def triggered_count(self,key):return sum(r['triggered'] for r in self.records.get(key,{}).values())

    def amplification(self,owner,target,*,raw=False):
        return self.value(owner,'exploit',raw=raw)*self.triggered_count(target)

    def resisted(self,key):
        return key not in self.muted and any(r['triggered'] and r['auxiliary'].get('seal_resist',{}).get('success')
                                             for r in self.records.get(key,{}).values())

    def take(self,key):
        for token in self.allowances[key]:
            if token.ready and not token.spent and (not token.requires_critical or key in self.critical_completed):
                token.spent=True;return token
        return None

    def pending(self,owners):
        return any(t.ready and not t.spent and (not t.requires_critical or k in self.critical_completed)
                   for k,rows in self.allowances.items() if k in owners for t in rows)

    def complete(self,key,critical,chain=()):
        if critical:self.critical_completed.add(key)
        if not critical or key in self.muted:return
        for row in self.records.get(key,{}).values():
            path=enter(chain,key,row['id'])
            if row['triggered'] and row['effects'].get('critical_extra') and path is not None:
                for _ in range(int(row['effects']['critical_extra'])):
                    p=row['effects'].get('free',0)
                    free=p>=1 or p>0 and self.rng.random()<p
                    self.allowances[key].append(ActionAllowance(source=row['id'],free=free,
                        slot=len(self.allowances[key]),chain=path))

    def evade(self,key,source,slot,chain=()):
        if key in self.muted:return None
        for row in self.records.get(key,{}).values():
            p=row['effects'].get('evade',0);path=enter(chain,key,row['id'])
            if p and row['triggered'] and path is not None:
                v=self.rng.random() if p<1 else None
                return dict(success=v is None or v<p,roll=v,probability=p,chain=path)
        return None

    def arm_reaction(self,key,source,chain=()):
        if key in self.muted:return False
        for row in self.records.get(key,{}).values():
            path=enter(chain,key,row['id'])
            if row['triggered'] and row['effects'].get('retaliate_power') and path is not None:
                self.allowances[key].append(ActionAllowance(source=row['id'],free=True,
                    requires_evade=True,target=source,slot=len(self.allowances[key]),chain=path))
                return True
        return False

    def channel(self,key,channel,chain=()):
        if key in self.muted:return None
        return next(((r,enter(chain,key,r['id'])) for r in self.records.get(key,{}).values()
                     if r['triggered'] and r['effects'].get(channel) and enter(chain,key,r['id']) is not None),None)

    def report(self):
        return dict(raw=self.records,effective=self.effective,raw_trigger_counts={k:self.triggered_count(k) for k in self.records},
                    silenced_by=dict(self.muted),actions={k:[asdict(t) for t in rows] for k,rows in self.allowances.items()})

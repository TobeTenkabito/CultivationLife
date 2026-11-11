"""Shared finite decisions, co-signatures and institutional case records."""
import copy
from .institution_ai.rules import choose


def decide(options, *, budget, preference=None):
    offers=[dict(key=o['id'],category='decision',budget=o.get('cost',0),
        urgency=o.get('priority',0)+(20 if o['id']==preference else 0),reason=o.get('reason','')) for o in options]
    selected=choose(offers,'balanced',budget,allow_zero=True)
    return selected['key'] if selected else None


def cosign(offers, people, policy, budget):
    """Adapters supply verified original people and actual needs, never votes."""
    result={}
    for person in list(dict.fromkeys(people))[:8]:
        choice=choose(offers,policy,budget,allow_zero=True)
        if choice:result.setdefault(choice['key'],[]).append(person)
    return result


def book(scope):
    return scope.get('protocols',dict(sequence=0,cases=[],history=[],
        mandate=dict(funding='local',appointments='local'),rotation=None,relocation=None,guard=None,recognition=None))


def ensure(scope):return scope.setdefault('protocols',book(scope))


def open_case(scope,kind,actor,subject,now,*,amount=0,facts=None,years=100):
    state=ensure(scope)
    if len(state['cases'])>=(9 if kind=='integration' else 8) or any(c['kind']==kind and c['subject']==subject for c in state['cases']):
        raise ValueError('须先收束同类原案或现有八项事务')
    state['sequence']+=1
    c=dict(id=f"{scope['id']}:protocol:{state['sequence']}",kind=kind,actor=actor,subject=subject,
        opened=now,deadline=now+years,stage='open',participants=[actor],reviewer=None,
        amount=amount,paid=0,spent=0,progress=0,last_tick=now,facts=copy.deepcopy(facts or {}),result='')
    state['cases'].append(c);scope['revision']+=1
    return c


def find(scope,identity):
    c=next((c for c in book(scope)['cases'] if c['id']==identity),None)
    if not c:raise ValueError('原案已结或不属于本府')
    return c


def close(scope,case,stage,result):
    state=ensure(scope)
    if case not in state['cases']:raise ValueError('原案已经结清')
    case.update(stage=stage,result=result)
    state['cases'].remove(case);state['history']=(state['history']+[copy.deepcopy(case)])[-24:]
    scope['revision']+=1

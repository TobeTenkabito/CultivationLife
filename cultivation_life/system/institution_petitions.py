"""Bounded, content-independent petitions and accountable endorsements.

Adapters provide original facts and execute effects through their authoritative
systems. This book holds references and receipts, never money or NPC replicas.
"""
import copy


def book(scope):
    return scope.get('petitions', {})


def ensure(scope):
    return scope.setdefault('petitions',dict(sequence=0,observed={},active=[],history=[],last_tick=-1))


def open_case(scope, *, kind, period, now, deadline, actor, evidence, witnesses):
    root=ensure(scope)
    if (len(root['active'])>=6 or root['observed'].get(kind,-1)>=period
            or any(c['kind']==kind for c in root['active'])):
        return None
    root['sequence']+=1;root['observed'][kind]=period
    row=dict(id=scope['id']+':petition:'+str(root['sequence']),kind=kind,actor=actor,
        opened=now,deadline=deadline,status='open',evidence=copy.deepcopy(evidence),
        witnesses=copy.deepcopy(witnesses),pledge=None,decision=None,result='',closed=None)
    root['active'].append(row);scope['revision']+=1
    return row


def find(scope, identity, now):
    row=next((c for c in book(scope).get('active',[]) if c['id']==identity),None)
    if not row:raise ValueError('原事项已结束或不属于本机构')
    if now<row['opened']:raise ValueError('尚未到原事项提出时间')
    if now>=row['deadline']:raise ValueError('原事项已逾期，须交接案卷')
    return row


def submit(scope, case):
    if case['status']!='open':raise ValueError('已呈交，不得重复请示')
    case['status']='submitted';scope['revision']+=1


def endorse(scope, case, actor, choice):
    if case['pledge']:raise ValueError('此案已有具名担保，不得覆盖或反复改押')
    case['pledge']=dict(actor=actor,choice=choice);scope['revision']+=1


def close(scope, case, *, now, status, decision, result):
    root=ensure(scope)
    if case not in root['active']:raise ValueError('原事项已结案')
    case.update(status=status,decision=decision,result=result,closed=now)
    root['active'].remove(case);root['history']=(root['history']+[copy.deepcopy(case)])[-24:]
    scope['revision']+=1


def choose(choices, *, budget, preferred=None):
    """Deterministic, bounded NPC deliberation; invalid facts never become votes."""
    from .institution_ai.rules import choose as choose_offer
    offers=[dict(key=c['id'],budget=c.get('cost',0),reason=c.get('reason'),category='deliberation',
                 urgency=c.get('priority',0)+(20 if c['id']==preferred else 0)) for c in choices]
    selected=choose_offer(offers,'balanced',budget,allow_zero=True)
    return selected['key'] if selected else None

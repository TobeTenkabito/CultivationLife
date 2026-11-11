"""Asura interests and personal patronage, derived from original careers/deeds."""
from . import rules
from .. import institution_authority as authority
from ..asura_court_finance import people, present
from ...npc_custody import is_free


def config():return rules.config().get('politics',{})
def enabled():return rules.enabled() and bool(config().get('enabled'))
def state(game):return rules.court(game).get('court',{}).get('factions',{}).get('politics',{})


def faction(game, identity):
    alignment=state(game).get('people',{}).get(identity,{}).get('alignment')
    if alignment:return alignment['group'],'具名转投与实际履约'
    court=rules.court(game).get('court',{})
    office=next((k for k,v in court.get('offices',{}).items() if v==identity),None)
    if office:return {'treasury':'free_cities','marshal':'war_hosts','ritual':'blood_clans'}[office], '现任中枢官职'
    career=state(game).get('people',{}).get(identity,{}).get('career',{})
    if career and max(career.values())>0:return max(sorted(career),key=career.get),'实际任职与履约经历'
    rank=next((int(k) for k,v in court.get('holders',{}).items() if v==identity),0)
    if rank:return ('war_hosts' if rank<=2 else 'blood_clans'),'现有爵位职责'
    return 'free_cities','未持爵廷臣与地方事务'


def preference(game, identity, kind, evidence):
    group,_=faction(game,identity)
    preferred=config().get('preferences',{}).get(kind,{}).get(group)
    if kind=='personnel':
        for option,key in [('appoint','candidate'),('alternative','alternative')]:
            if evidence.get(key) and faction(game,evidence[key])[0]==group:return option
        if preferred=='alternative' and not evidence.get('alternative'):return 'decline'
    return preferred


def challenge_restraint(game, identity):
    if not enabled():return 0
    return max(0,state(game).get('people',{}).get(identity,{}).get('bonds',{}).get('player',0))//5


def remember(game, identity, actor, change, reason, reference, career=None, *, settlement=False):
    if (not enabled() and not settlement) or identity=='player':return
    from ...relationship_records import find_person
    npc=find_person(game,identity)
    if not npc or not npc.alive:return
    root=rules.court(game)['court']['factions'].setdefault('politics',dict(people={},last_unit=-1))
    if identity not in root['people'] and len(root['people'])>=64:return
    row=root['people'].setdefault(identity,dict(bonds={},career={},deeds=[]))
    if actor in row['bonds'] or len(row['bonds'])<8:
        row['bonds'][actor]=max(-100,min(100,row['bonds'].get(actor,0)+change))
    if career:row['career'][career]=min(100,row['career'].get(career,0)+1)
    row['deeds']=(row['deeds']+[dict(year=game.player.age,actor=actor,change=change,reason=reason,reference=reference)])[-8:]


def appointment(game, identity, actor, office, reference):
    period=game.player.age//config().get('period_years',100)
    prior=state(game).get('people',{}).get(identity,{})
    if identity and prior.get('appointed_period',-1)<period:
        remember(game,identity,actor,4,'原任职正式登记',reference,
                 {'treasury':'free_cities','marshal':'war_hosts','ritual':'blood_clans','staff':'free_cities','governor':'blood_clans'}[office])
        row=state(game).get('people',{}).get(identity)
        if row is not None:row['appointed_period']=period


def outcome(game, scope, case, decision, *, actor):
    if case['status']=='obsolete':return
    if case['status'] in {'resolved','rejected'}:
        for witness in case['witnesses']:
            support=witness['choice']==decision
            remember(game,witness['id'],actor,4 if support else -2,
                     '原案裁决采纳其主张' if support else '原案裁决未采纳其主张',case['id'],witness['faction'],settlement=True)
    pledge=case.get('pledge')
    if pledge:
        fulfilled=pledge['choice']==decision and case['status']=='resolved'
        for witness in case['witnesses']:
            remember(game,witness['id'],pledge['actor'],6 if fulfilled else -6,
                     '具名担保兑现' if fulfilled else '具名担保未兑现',case['id'],settlement=True)


def summary(game):
    court=rules.court(game).get('court',{});roster=people(game)
    from ...relationship_records import find_person
    for scope in rules.offices(game):
        for identity in scope['people']+[scope['holder']]:
            npc=find_person(game,identity) if identity and identity!='player' else None
            if npc:roster[npc.id]=npc
    factions=config().get('factions',{})
    weights={k:5 for k in factions};sources={k:[] for k in factions};members=[]
    king=court.get('holders',{}).get('5')
    for n in roster.values():
        if not present(n) or not is_free(n) or n.id==king:continue
        group,basis=faction(game,n.id)
        if group not in weights:continue
        rank=next((int(k) for k,v in court.get('holders',{}).items() if v==n.id),0)
        role=5 if n.id in court.get('offices',{}).values() else 0
        provincial=4 if any(authority.effective(game,r,n.id) for r in rules.offices(game)) else 0
        record=state(game).get('people',{}).get(n.id,{})
        credit=min(6,max(0,record.get('bonds',{}).get(king,0))//4)
        weight=1+rank+role+provincial+credit;weights[group]+=weight
        sources[group].append(f'{n.name}：爵位{rank}、中枢{role}、地方{provincial}、履约支持{credit}')
        bonds=record.get('bonds',{});patron=max(bonds,key=bonds.get) if bonds else None
        patron=patron if patron and bonds[patron]>=12 else None
        # Only personal ties to the player are disclosed, not the private graph.
        members.append(dict(id=n.id,name=n.name,faction=group,basis=basis,
            support=bonds.get('player',0),patron=patron=='player',weight=weight))
    values={k:5+85*v/sum(weights.values()) for k,v in weights.items()} if weights else {}
    for _ in range(3):
        excess=sum(max(0,v-70) for v in values.values());values={k:min(70,v) for k,v in values.items()}
        room=[k for k,v in values.items() if v<70]
        if excess and room:
            for k in room:values[k]+=excess/len(room)
    return values,sources,members


def tick(game, royal):
    if not enabled():return
    root=royal['court']['factions'].setdefault('politics',dict(people={},last_unit=-1))
    if root['last_unit']>=royal['unit']:return
    root['last_unit']=royal['unit']
    values,_,_=summary(game)
    for row in royal['court']['factions']['rows']:row['external']=values[row['id']]
    royal['court']['factions']['pressure']=0

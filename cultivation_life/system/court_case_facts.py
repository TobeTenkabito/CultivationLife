"""Inspection leads derive only from original appointments, cargo and receipts."""
from ..relationship_records import find_person
from .court_bureau_rules import state, jobs, digest, HOME

KIN = ('dao_companion', 'master', 'disciples', 'offspring')

def relation(game, identity):
    for key in KIN:
        rows=getattr(game.player,key,None) or []
        if isinstance(rows,dict):rows=[rows]
        if any(str(r.get('npc_id') or r.get('id'))==identity for r in rows):return key
    return ''

def source(game, case):
    if case['kind']=='conflict':
        return next((a for a in state(game).get('appointments',[]) if a['id']==case['source']),None)
    return next((j for j in jobs(game) if j['id']==case['source']),None)

def facts(game, case):
    row=source(game,case)
    if not row:return dict(missing=True,summary='原凭据已失效，不能作不利裁定',fault=False,owed={})
    if case['kind']=='conflict':
        active=state(game).get('staff',{}).get(row['person'])==row['office']
        return dict(missing=False,relation=row['relation'],active=active,person=row['person'],
            fault=active,owed={},summary='任命时存在已登记亲属／师承关系；关系本身不证明贪污。'+('任命仍有效，须回避。' if active else '原任命已经交接解除。'))
    receipt=row.get('receipt',{})
    difference=receipt.get('reserved',0)-sum(receipt.get(k,0) for k in ('purchase','labor','engineering','refunded'))
    diverted={}
    for item,n in row.get('diversion',{}).get('goods',{}).items():
        left=n-row.get('restitution',{}).get(item,0)
        if left>0:diverted[item]=left
    if case['kind']=='procurement':
        return dict(missing=False,owed=diverted,difference=difference,
            emergency=bool(row.get('diversion',{}).get('shortage')),fault=bool(diverted or difference),
            summary=f'原收支差额 {difference} 灵石；改拨后尚欠原交付点 {sum(diverted.values())} 件实物。',
            receipt=receipt,diversion=row.get('diversion'))
    excused=bool(row.get('closure_obstruction'))
    return dict(missing=False,owed={},late=row.get('closed',0)>=row['deadline'],
        excused=excused,fault=not excused and bool(row.get('cancelled')),
        summary=('原交接记录存在客观阻碍：'+row['closure_obstruction'] if excused else '原差事逾期且未完成；尚不能据此认定故意虚报。'),
        progress=row['progress'],years=row['years'],receipt=receipt)

def leads(game):
    known={c['key'] for c in state(game).get('inquiries',[])};out=[]
    for row in jobs(game):
        if row['status']!='closed' or row['kind']=='audit':continue
        receipt=row.get('receipt',{})
        mismatch=receipt.get('reserved',0)!=sum(receipt.get(k,0) for k in ('purchase','labor','engineering','refunded'))
        kinds=[]
        if row.get('diversion') or mismatch:kinds.append(('procurement','采购短交与用途核查'))
        if row.get('cancelled') and row.get('closed',0)>=row['deadline']:kinds.append(('neglect','地方履约失职核查'))
        for kind,title in kinds:
            out.append(dict(kind=kind,source=row['id'],subject=row['person'],name=title+' · '+row['name'],
                location=row['location'],key=kind+':'+row['id']))
    for row in state(game).get('appointments',[]):
        if row.get('relation'):
            out.append(dict(kind='conflict',source=row['id'],subject='player',name='任命利益冲突核查 · '+row['name'],
                location=HOME,key='conflict:'+row['id']))
    for row in out:
        row['facts']=facts(game,row);row['token']=digest(row)
    return [r for r in out if r['key'] not in known]

def restriction(game, identity):
    row=state(game).get('restrictions',{}).get(identity,{})
    return '监察处分期间不得新接公务或任命；可申诉复核' if row.get('until',0)>game.player.age else ''

def record_appointment(game, npc, office):
    rows=state(game).setdefault('appointments',[])
    rows.append(dict(id='appointment-'+str(len(rows)+1),person=npc.id,name=npc.name,office=office,
        age=game.player.age,relation=relation(game,npc.id)))

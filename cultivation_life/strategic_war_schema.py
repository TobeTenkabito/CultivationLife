"""Structure 10 additive war state. No implicit migration or unknown-world fallback."""
def validate_state(state, campaigns=()):
    for child in campaigns:
        if child.get('strategic_war_id'):
            validate_dispatches(child)
    if not isinstance(state,dict):
        raise ValueError('战略战争状态必须为对象')
    if not state:return
    validate_local_councils(state)
    wars=state.get('wars',[])
    if not isinstance(wars,list) or len(wars)>22:
        raise ValueError('战略战争记录超出容量')
    statuses={'mobilizing','active','armistice','settling','ended'}
    seen=set();active=0
    for w in wars:
        if (not isinstance(w,dict) or not isinstance(w.get('id'),str) or w['id'] in seen
                or w.get('world') not in {'spirit','true_demon'} or w.get('status') not in statuses):
            raise ValueError('战略战争身份、界面或阶段无效')
        seen.add(w['id']);active+=w['status']!='ended'
        for field in ('revision','start_age','last_age'):
            if type(w.get(field)) is not int or w[field]<0:
                raise ValueError('战略战争时钟或修订号无效')
        for field,cap in [('commitments',12),('objectives',2),('campaigns',2),('logs',80)]:
            if not isinstance(w.get(field),list) or len(w[field])>cap:
                raise ValueError('战略战争明细超出容量')
        if not isinstance(w.get('receipts'),dict) or len(w['receipts'])>2:
            raise ValueError('战略战争回执无效')
        if not isinstance(w.get('commanders'),dict) or set(w['commanders'])-{'attacker','defender'}:
            raise ValueError('战略战争统帅无效')
        for c in w['commitments']:
            if (not isinstance(c,dict) or c.get('side') not in {'attacker','defender'}
                    or c.get('org',{}).get('kind') not in {'sect','family'}
                    or not isinstance(c.get('org',{}).get('id'),str)
                    or type(c.get('budget')) is not int or c['budget']<0):
                raise ValueError('战略战争组织承诺无效')
            if (type(c.get('willingness',70)) is not int or not 0<=c.get('willingness',70)<=100
                    or not isinstance(c.get('will_baseline',{}),dict) or len(c.get('will_baseline',{}))>24
                    or any(not isinstance(k,str) or type(v) is not int or not 0<=v<=4 for k,v in c.get('will_baseline',{}).items())):
                raise ValueError('组织战意或原伤亡基线无效')
        validate_peace(w)
        if not isinstance(w.get('score'),(int,float)) or not -100<=w['score']<=100:
            raise ValueError('战略战争态势无效')
    if active>2 or len(wars)-active>20:
        raise ValueError('战略战争数量超出容量')
    if type(state.get('command_seq',0)) is not int or state.get('command_seq',0)<0:
        raise ValueError('战略战争命令序号无效')
    if not isinstance(state.get('commands',[]),list) or len(state.get('commands',[]))>64:
        raise ValueError('战略战争命令回执无效')


def validate_local_councils(state):
    def mapping(value, limit):
        return (isinstance(value, dict) and len(value) <= limit
                and all(isinstance(k, str) and 0 < len(k) <= 160 for k in value))

    support = state.get('directory_support', {})
    councils = state.get('local_councils', {})
    if not mapping(support, 32) or not mapping(councils, 32):
        raise ValueError('族议界面记录无效')
    for rows in support.values():
        if not mapping(rows, 256) or any(not isinstance(v, str) or not 0 < len(v) <= 100 for v in rows.values()):
            raise ValueError('山门盟书无效')
    for races in councils.values():
        if not mapping(races, 128):
            raise ValueError('本界议簿无效')
        for book in races.values():
            if not isinstance(book, dict):
                raise ValueError('族议案卷无效')
            for field, cap in [('places', 6), ('grievances', 5), ('sessions', None), ('used_at', None)]:
                rows = book.get(field, {})
                if not mapping(rows, 256) or any(type(v) is not int or v < 0 or cap is not None and v > cap for v in rows.values()):
                    raise ValueError('分席或议期记录无效')
            if (sum(book.get('places', {}).values()) > 6 or type(book.get('awarded', 0)) is not int
                    or book.get('awarded', 0) < 0 or not isinstance(book.get('counter', ''), str)):
                raise ValueError('荐额总数或起始年份无效')
            recent = book.get('recent', [])
            if not isinstance(recent, list) or len(recent) > 3:
                raise ValueError('族会议案超出容量')
            for meeting in recent:
                if (not isinstance(meeting, dict) or not isinstance(meeting.get('summary'), str)
                        or not isinstance(meeting.get('ballots'), list) or len(meeting['ballots']) > 256
                        or any(not isinstance(b, dict) or type(b.get('yes')) is not bool or
                               not all(isinstance(b.get(k), str) for k in ('id', 'name', 'reason')) for b in meeting['ballots'])):
                    raise ValueError('各宗回函无效')


def validate_dispatches(child):
    rows=child.get('reinforcements',[])
    if not isinstance(rows,list) or len(rows)>10:
        raise ValueError('战役增援超出容量')
    seen=set()
    for r in rows:
        side=r.get('side');org=r.get('org',{});cargo=r.get('cargo',{})
        if (side not in {'attacker','defender'} or org.get('kind') not in {'sect','family'}
                or not isinstance(org.get('id'),str) or org['id'] in seen
                or r.get('wallet')!=f"war-supply:{child['id']}:{side}:reserve:{org['id']}"
                or type(r.get('paid')) is not int or r['paid']<0
                or type(r.get('delivered')) is not bool or type(r.get('refunded')) is not bool
                or cargo.get('phase') not in {'outbound','stationed','returning','home'}):
            raise ValueError('战役增援身份或托管无效')
        seen.add(org['id'])
        if any(type(cargo.get(k)) is not int or cargo[k]<0 for k in ('years','remaining','departed_age')):
            raise ValueError('战役增援行程无效')
    for side in ('attacker','defender'):
        if len(child.get('coalitions',{}).get(side,[]))>6 or len(child.get('roster',{}).get(side,[]))>48:
            raise ValueError('战役联军超出容量')


def validate_peace(w):
    for field in ('peace_proposal','treaty'):
        p=w.get(field)
        if p is None:continue
        if (not isinstance(p,dict) or p.get('side') not in {'attacker','defender'}
                or p.get('term') not in {'white_peace','long_truce','reparations','heavy_reparations','destroy_outpost','remove_influence','economic_rights'}
                or type(p.get('age')) is not int or p['age']<0
                or not isinstance(p.get('demands'),list) or len(p['demands'])>12
                or type(p.get('total')) is not int or p['total']<0):
            raise ValueError('战争和约无效')
        seen=set()
        for d in p['demands']:
            if (not isinstance(d,dict) or type(d.get('amount')) is not int or d['amount']<=0
                    or any(not isinstance(d.get(k),dict) or d[k].get('kind') not in {'sect','family'}
                           or not isinstance(d[k].get('id'),str) for k in ('payer','receiver'))
                    or d['payer']==d['receiver'] or d['payer']['id'] in seen):
                raise ValueError('战争赔款义务无效')
            seen.add(d['payer']['id'])
            allocations=d.get('allocations',[dict(receiver=d['receiver'],amount=d['amount'])])
            if (not isinstance(allocations,list) or not 1<=len(allocations)<=6
                    or any(not isinstance(a,dict) or type(a.get('amount')) is not int or a['amount']<=0
                           or not isinstance(a.get('receiver'),dict) or a['receiver'].get('kind') not in {'sect','family'}
                           or not isinstance(a['receiver'].get('id'),str) or a['receiver']['id']==d['payer']['id'] for a in allocations)
                    or sum(a['amount'] for a in allocations)!=d['amount']
                    or len({a['receiver']['id'] for a in allocations})!=len(allocations)):
                raise ValueError('战争赔款分配无效')
        if sum(d['amount'] for d in p['demands'])!=p['total'] or (p['term']=='white_peace' and p['demands']):
            raise ValueError('战争赔款总额不符')
        if type(p.get('truce_years',1000)) is not int or p.get('truce_years',1000) not in {50,150,1000,3000}:
            raise ValueError('和约停战年限无效')
        if not isinstance(p.get('effects',[]),list) or len(p.get('effects',[]))>1:
            raise ValueError('和约实物条款超出范围')
        for effect in p.get('effects',[]):
            if (not isinstance(effect,dict) or effect.get('term')!=p['term']
                    or effect.get('term') not in {'destroy_outpost','remove_influence','economic_rights'}
                    or effect.get('campaign_id') not in w['campaigns']
                    or not isinstance(effect.get('location'),str)
                    or any(not isinstance(effect.get(k),dict) or effect[k].get('kind') not in {'sect','family'}
                           or not isinstance(effect[k].get('id'),str) for k in ('payer','receiver'))):
                raise ValueError('和约目标归属无效')
        if field=='peace_proposal' and (p.get('status') not in {'pending','accepted','rejected','expired'}
                or type(p.get('expires')) is not int or p['expires']<p['age']):
            raise ValueError('和谈提案期限无效')

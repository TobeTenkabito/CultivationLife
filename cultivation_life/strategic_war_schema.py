"""Structure 10 additive war state. No implicit migration or unknown-world fallback."""
def validate_state(state, campaigns=()):
    for child in campaigns:
        if child.get('strategic_war_id'):
            validate_dispatches(child)
    if not isinstance(state,dict):
        raise ValueError('战略战争状态必须为对象')
    if not state:return
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
        if not isinstance(w.get('score'),(int,float)) or not -100<=w['score']<=100:
            raise ValueError('战略战争态势无效')
    if active>2 or len(wars)-active>20:
        raise ValueError('战略战争数量超出容量')
    if type(state.get('command_seq',0)) is not int or state.get('command_seq',0)<0:
        raise ValueError('战略战争命令序号无效')
    if not isinstance(state.get('commands',[]),list) or len(state.get('commands',[]))>64:
        raise ValueError('战略战争命令回执无效')


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

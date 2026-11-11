"""Strict validation for generic petition references, bounded facts and receipts."""
def validate(root, scope):
    def need(ok):
        if not ok:raise ValueError('机构争议案卷无效，原存档已保留')
    def word(v):return isinstance(v,str) and 0<len(v)<=1024
    def number(v):return type(v) is int and 0<=v<=10**24
    need(isinstance(root,dict) and number(root.get('sequence')))
    need(type(root.get('last_tick',-1)) is int and -1<=root.get('last_tick',-1)<=10**24)
    observed=root.get('observed');need(isinstance(observed,dict) and len(observed)<=16)
    need(all(word(k) and number(v) for k,v in observed.items()))
    active,history=root.get('active'),root.get('history')
    need(isinstance(active,list) and len(active)<=6 and isinstance(history,list) and len(history)<=24)
    ids=set();kinds=set()
    for row in active+history:
        need(isinstance(row,dict))
        need(all(word(row.get(k)) for k in ('id','kind','actor')))
        identity=row['id'];prefix=scope+':petition:'
        need(identity.startswith(prefix) and identity[len(prefix):].isdigit())
        need(0<int(identity[len(prefix):])<=root['sequence'] and identity not in ids);ids.add(identity)
        need(number(row.get('opened')) and number(row.get('deadline')) and row['deadline']>row['opened'])
        need(row.get('decision') is None or word(row['decision']))
        need(isinstance(row.get('result'),str) and len(row['result'])<=2048)
        if row in active:
            need(row.get('status') in {'open','submitted'} and row.get('closed') is None)
            need(row['kind'] not in kinds);kinds.add(row['kind'])
        else:
            need(row.get('status') in {'resolved','rejected','withdrawn','expired','obsolete'})
            need(number(row.get('closed')) and row['closed']>=row['opened'])
        evidence=row.get('evidence');need(isinstance(evidence,dict) and len(evidence)<=16)
        need(all(word(k) and (v is None or type(v) is bool or number(v) or word(v)) for k,v in evidence.items()))
        witnesses=row.get('witnesses');need(isinstance(witnesses,list) and len(witnesses)<=3)
        seen=set()
        for witness in witnesses:
            need(isinstance(witness,dict) and all(word(witness.get(k)) for k in ('id','name','faction','choice','reason')))
            need(witness['id'] not in seen);seen.add(witness['id'])
        pledge=row.get('pledge')
        need(pledge is None or isinstance(pledge,dict) and word(pledge.get('actor')) and word(pledge.get('choice')))

"""Institutional mandate/case references, with no content registry dependency."""
def validate(scope,accounts=None,occupied=None):
    root=scope.get('protocols')
    if root is None:return
    def need(ok):
        if not ok:raise ValueError('机构议政、军权或交接凭据无效，原存档已保留')
    def number(v):return type(v) is int and 0<=v<=10**24
    def reference(v):return isinstance(v,str) and 0<len(v)<=512
    need(isinstance(root,dict) and set(root)=={'sequence','cases','history','mandate','rotation','relocation','guard','recognition'})
    need(number(root['sequence']))
    mandate=root['mandate'];need(isinstance(mandate,dict) and set(mandate)=={'funding','appointments'})
    need(all(isinstance(v,str) and v in {'central','local'} for v in mandate.values()))
    need(root['guard'] is None or reference(root['guard']))
    need(root['recognition'] is None or reference(root['recognition']))
    seen=set()
    for key,limit in [('cases',9),('history',24)]:
        need(isinstance(root[key],list) and len(root[key])<=limit)
        for c in root[key]:
            need(isinstance(c,dict) and set(c)=={'id','kind','actor','subject','opened','deadline','stage','participants','reviewer','amount','paid','spent','progress','last_tick','facts','result'})
            need(all(reference(c[k]) for k in ('id','kind','actor','subject','stage')) and c['id'].startswith(scope['id']+':protocol:') and c['id'] not in seen)
            seen.add(c['id']);need(c['reviewer'] is None or reference(c['reviewer']))
            if key=='cases' and c['stage']=='reviewing':
                need(reference(c['reviewer']) and c['reviewer']!=c['subject'])
                if occupied is not None:
                    need(c['reviewer'] not in occupied);occupied.add(c['reviewer'])
            need(all(number(c[k]) for k in ('opened','deadline','amount','paid','spent','progress','last_tick')) and c['deadline']>c['opened'] and c['paid']<=c['amount'])
            need(c['stage'] in {'open','proposed','reviewing','defence','judged','active','fulfilled','breached','cancelled','rejected','expired'})
            need(isinstance(c['participants'],list) and 1<=len(c['participants'])<=8 and all(reference(p) for p in c['participants']) and len(set(c['participants']))==len(c['participants']))
            facts=c['facts'];need(isinstance(facts,dict) and len(facts)<=24 and all(reference(k) and (v is None or type(v) in (str,int,bool)) for k,v in facts.items()))
            if 'suspends_authority' in facts:need(type(facts['suspends_authority']) is bool)
            if 'review_source' in facts:need(isinstance(facts['review_source'],str) and facts['review_source'] in {scope['wallet'],scope['source']})
            if 'review_issuer' in facts:need(reference(facts['review_issuer']))
            need(isinstance(c['result'],str) and len(c['result'])<=4000)
            if c['kind']=='alliance':
                wallet=facts.get('wallet')
                need(reference(wallet) and wallet=='institution-pact:'+c['id'] and reference(facts.get('office')) and type(facts.get('war')) is str)
                if accounts is not None:
                    need(wallet in accounts)
                    need(accounts[wallet]['balance']==(c['amount']-c['paid'] if key=='cases' else 0))
            if scope.get('provider')=='asura-governorship':need(c['kind'] in {'pressure','patronage','audit','alliance','integration'})
    rotation=root['rotation']
    if rotation is not None:
        need(isinstance(rotation,dict) and set(rotation)=={'outgoing','incoming','stage','ordered','issuer'})
        need(all(reference(rotation[k]) for k in ('outgoing','incoming','issuer')) and rotation['outgoing']!=rotation['incoming'])
        need(isinstance(rotation['stage'],str) and rotation['stage'] in {'awaiting','relieved','cancelled'} and number(rotation['ordered']))
    move=root['relocation']
    if move is not None:
        need(isinstance(move,dict) and set(move)=={'city','location','requested','deadline','stage','issuer','holder'})
        need(all(reference(move[k]) for k in ('city','location','issuer','holder')) and isinstance(move['stage'],str) and move['stage'] in {'approved','completed','cancelled'})
        need(number(move['requested']) and number(move['deadline']) and move['deadline']>move['requested'])

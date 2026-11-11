"""Optional DLC history validation, independent of runtime content loading."""
def validate(root):
    def need(ok):
        if not ok:raise ValueError('修罗派系履历无效，原存档已保留')
    def word(v):return isinstance(v,str) and 0<len(v)<=1024
    need(isinstance(root,dict) and type(root.get('last_unit')) is int and root['last_unit']>=-1)
    rows=root.get('people');need(isinstance(rows,dict) and len(rows)<=64)
    for identity,row in rows.items():
        need(word(identity) and isinstance(row,dict))
        if 'alignment' in row:
            a=row['alignment'];need(isinstance(a,dict) and set(a)=={'group','patron','since'})
            need(isinstance(a['group'],str) and a['group'] in {'blood_clans','war_hosts','free_cities'} and word(a['patron']) and type(a['since']) is int and a['since']>=0)
        if 'appointed_period' in row:need(type(row['appointed_period']) is int and row['appointed_period']>=0)
        bonds,career,deeds=row.get('bonds'),row.get('career'),row.get('deeds')
        need(isinstance(bonds,dict) and len(bonds)<=8)
        need(all(word(k) and type(v) is int and -100<=v<=100 for k,v in bonds.items()))
        need(isinstance(career,dict) and len(career)<=3)
        need(all(k in {'blood_clans','war_hosts','free_cities'} and type(v) is int and 0<=v<=100 for k,v in career.items()))
        need(isinstance(deeds,list) and len(deeds)<=8)
        for deed in deeds:
            need(isinstance(deed,dict) and all(word(deed.get(k)) for k in ('actor','reason','reference')))
            need(type(deed.get('year')) is int and deed['year']>=0 and type(deed.get('change')) is int and -100<=deed['change']<=100)


def validate_cases(scope):
    if scope.get('provider')!='asura-governorship':return
    def need(ok):
        if not ok:raise ValueError('修罗地方案卷证据无效，原存档已保留')
    def word(v):return isinstance(v,str) and 0<len(v)<=512
    def integer(v):return type(v) is int and 0<=v<=10**24
    root=scope.get('petitions',{})
    for case in root.get('active',[])+root.get('history',[]):
        kind=case['kind'];e=case['evidence']
        need(kind in {'budget','remittance','personnel','performance','access','tenure'})
        need(word(e.get('source')) and word(e.get('description')))
        target_valid=e.get('target')==scope['building_id'] or case in root.get('history',[]) and isinstance(e.get('target'),str) and e['target'].startswith('office:'+scope['id'])
        if kind=='budget':need(target_valid and integer(e.get('amount')) and e['amount']>0 and integer(e.get('total')) and e['total']>=e['amount'])
        if 'paid' in e:need(kind=='budget' and integer(e['paid']) and 0<e['paid']<=e['amount'])
        if kind=='remittance':need(integer(e.get('amount')) and e['amount']>0 and integer(e.get('reserve')))
        if kind=='personnel':
            need(word(e.get('candidate')) and word(e.get('candidate_name')))
            need(e.get('alternative') is None or word(e['alternative']) and word(e.get('alternative_name')) and e['alternative']!=e['candidate'])
        if kind=='performance':need(word(e.get('target')) and integer(e.get('spent')) and integer(e.get('deadline')))
        if kind=='access':need(target_valid and type(e.get('public')) is bool)
        if kind=='tenure':need(integer(e.get('expires')) and integer(e.get('completed')))
        for witness in case['witnesses']:need(witness['faction'] in {'blood_clans','war_hosts','free_cities'})

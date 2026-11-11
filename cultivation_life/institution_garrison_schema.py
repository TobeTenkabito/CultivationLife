"""Original-person garrisons and prepaid service receipts, no content imports."""
def validate(scope,accounts,occupied):
    row=scope.get('garrison')
    if row is None:return
    def need(ok):
        if not ok:raise ValueError('驻军、行程或军费记录无效，原存档已保留')
    def integer(v):return type(v) is int and 0<=v<=10**24
    need(isinstance(row,dict))
    need(row.get('wallet')=='garrison:'+scope['id'] and row['wallet'] in accounts)
    need(all(integer(row.get(k)) for k in ('paid','spent','returned','last_year','shortfall')))
    need(row['paid']==row['spent']+row['returned']+accounts[row['wallet']]['balance'])
    units=row.get('units');need(isinstance(units,list) and len(units)<=6)
    seen=set()
    for u in units:
        need(isinstance(u,dict))
        for k in ('person_id','origin','destination','home'):need(isinstance(u.get(k),str) and 0<len(u[k])<=512)
        need(u['person_id']!='player' and u['person_id'] not in seen);seen.add(u['person_id'])
        need(u.get('organization') is None or isinstance(u['organization'],str))
        need(u.get('phase') in {'stationed','outbound','returning','home','lost'})
        need(all(integer(u.get(k)) for k in ('years','remaining','last_year','rate')))
        need(u['remaining']<=u['years'] and u['rate']>0 and u['home']==scope['location'])
        need(isinstance(u.get('route'),list) and 1<=len(u['route'])<=128 and all(isinstance(p,str) and p for p in u['route']))
        if u['phase']=='stationed':need(u['remaining']==0)
        if u['phase'] not in {'home','lost'}:
            need(u['person_id'] not in occupied);occupied.add(u['person_id'])

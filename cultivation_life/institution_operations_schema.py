"""Finite public operating receipts and original consignment escrow."""


def validate(row,accounts):
    value=row.get('operations')
    if value is None:return
    def need(ok):
        if not ok:raise ValueError('机构经营或供货凭证无效，原存档已保留')
    def number(v):return type(v) is int and 0<=v<=10**24
    fields={'income','expense','salary','settlements','deliveries','sequence','last_signed','last_training','last_reward','last_performance','term_baseline','policy','contract'}
    need(isinstance(value,dict) and set(value)==fields)
    need(all(number(value[k]) for k in fields-{'policy','contract'}))
    need(value['salary']<=value['income'] and isinstance(value['policy'],str) and value['policy'] in {'reserve','tribute','garrison'})
    need(value['term_baseline']<=value['settlements']+value['deliveries'])
    c=value['contract']
    if c is None:return
    need(isinstance(c,dict))
    need(all(number(c.get(k)) for k in ('quantity','price','periods','interval','started','next','deadline','funded','paid','completed','fee','service_percent')))
    need(c['service_percent']<=100)
    need(0<c['quantity']<=1000 and 1<=c['periods']<=3 and c['interval']>0 and c['fee']<c['price'])
    need(c['completed']<=c['periods'] and c['paid']==c['completed']*c['price'] and c['funded']==c['periods']*c['price'])
    need(c.get('world')==row['world'] and c.get('location')==row['location'])
    need(all(isinstance(c.get(k),str) and c[k] for k in ('id','item','source','wallet','supplier','status')))
    need(c['id']==row['id']+':supply:'+str(value['sequence']))
    need(c['source']=='market:'+row['world']+':'+row['location'] and c['source'] in accounts)
    need(c['wallet']=='institution-contract:'+c['supplier']+':'+c['id'] and c['wallet'] in accounts)
    need(c['status'] in {'active','completed','cancelled'} and number(c.get('refunded',0)))
    need(c['funded']==c['paid']+c.get('refunded',0)+accounts[c['wallet']]['balance'])
    if c['status']!='active':need(accounts[c['wallet']]['balance']==0)
    if c['status']=='completed':need(c['completed']==c['periods'])
    receipts=c.get('receipts');need(isinstance(receipts,list) and len(receipts)==c['completed'])
    previous=c['started']
    for r in receipts:
        need(isinstance(r,dict) and number(r.get('year')) and r['year']>=previous+c['interval'])
        need(r.get('quantity')==c['quantity'] and r.get('paid')==c['price'])
        previous=r['year']

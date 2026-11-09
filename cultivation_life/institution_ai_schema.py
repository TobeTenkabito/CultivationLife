"""Strict optional agenda validation, independent of runtime and DLC content."""
def validate(value,accounts):
    def need(condition):
        if not condition:raise ValueError('机构事务存档无效，原文件已保留')
    def number(v):return type(v) is int and 0<=v<=10**18
    need(isinstance(value,dict) and number(value.get('sequence')) and isinstance(value.get('scopes'),dict))
    need(len(value['scopes'])<=2000)
    used=set();delegates=set();wallets=set()
    for key,row in value['scopes'].items():
        need(isinstance(key,str) and isinstance(row,dict))
        need(row.get('policy') in {'balanced','supply','repair','teaching'} and number(row.get('limit')) and type(row.get('automatic')) is bool)
        need(type(row.get('last_observed')) is int and row['last_observed']>=-1 and number(row.get('revision')))
        need(type(row.get('last_tick',-1)) is int and row.get('last_tick',-1)>=-1)
        need(isinstance(row.get('proposals'),list) and len(row['proposals'])<=3 and isinstance(row.get('history'),list) and len(row['history'])<=12)
        if row.get('provider'):need(isinstance(row['provider'],str) and 0<len(row['provider'])<=64)
        if row.get('delegate'):
            need(isinstance(row['delegate'],str) and row['delegate'] not in delegates);delegates.add(row['delegate'])
        jobs=([row['job']] if row.get('job') else [])+row['history']
        for job in jobs:
            need(isinstance(job,dict) and job.get('scope')==key and job.get('status') in {'active','completed','cancelled'})
            need(job.get('phase')=='institution' and isinstance(job.get('offer'),dict))
            need(isinstance(job.get('id'),str) and isinstance(job.get('provider'),str) and type(job.get('automatic')) is bool)
            need(isinstance(job.get('blocked'),str) and isinstance(job['offer'].get('kind'),str) and isinstance(job['offer'].get('key'),str))
            need(isinstance(job['offer'].get('materials'),dict) and all(isinstance(k,str) and number(n) for k,n in job['offer']['materials'].items()))
            need(all(number(job.get(k)) for k in ('started','last_year','deadline','years','progress','funded','spent','wages')))
            need(job['years']>0 and job['progress']<=job['years'] and job['spent']<=job['funded'] and job['wages']<=job['spent'])
            need(job['last_year']>=job['started'] and job['deadline']>job['started'])
            need(isinstance(job.get('person'),str) and isinstance(job.get('source'),str) and isinstance(job.get('world'),str) and isinstance(job.get('location'),str))
            wallet=job.get('wallet');need(isinstance(wallet,str) and wallet.startswith('institution-project:') and wallet in accounts)
            need(wallet not in wallets);wallets.add(wallet)
            need(number(job['offer'].get('wage')) and number(job['offer'].get('budget')))
            if job['status']=='active':
                need(job['person'] not in used);used.add(job['person'])
                need(job['funded']==job['spent']+accounts[wallet]['balance'])
            else:need(number(job.get('refunded')) and job['funded']==job['spent']+job['refunded'] and accounts[wallet]['balance']==0)


def validate_contracts(value,accounts):
    def need(condition):
        if not condition:raise ValueError('分期契约存档无效，原文件已保留')
    def number(v):return type(v) is int and 0<=v<=10**18
    need(isinstance(value,dict))
    need(number(value.get('sequence',0)) and number(value.get('last_cycle',0)))
    history=value.get('history',[]);need(isinstance(history,list) and len(history)<=12)
    rows=history+([value['active']] if value.get('active') else []);used=set()
    for r in rows:
        need(isinstance(r,dict) and r.get('status') in {'active','completed','cancelled'})
        need(all(number(r.get(k)) for k in ('quantity','price','periods','interval','started','next','deadline','funded','paid','completed')))
        need(0<r['quantity'] and 0<r['price'] and 1<=r['periods']<=3 and r['interval']>0)
        need(0<=r['completed']<=r['periods'] and r['paid']==r['completed']*r['price'] and r['funded']==r['periods']*r['price'])
        need(r.get('source_kind') in {'estate','inventory'} and r.get('world')=='celestial' and isinstance(r.get('location'),str))
        need(isinstance(r.get('item'),str) and isinstance(r.get('source'),str) and r['source'] in accounts)
        wallet=r.get('wallet');need(isinstance(wallet,str) and wallet.startswith('institution-contract:') and wallet in accounts and wallet not in used);used.add(wallet)
        need(isinstance(r.get('receipts'),list) and len(r['receipts'])==r['completed'])
        refunded=r.get('refunded',0);need(number(refunded) and r['funded']==r['paid']+refunded+accounts[wallet]['balance'])
        if r['status']!='active':need(accounts[wallet]['balance']==0)
        if r['status']=='completed':need(r['completed']==r['periods'])
    if value.get('active'):need(value['active']['status']=='active')

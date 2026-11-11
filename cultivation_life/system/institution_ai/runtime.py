"""One agenda, original people, one escrow, and actual regional years."""
import copy
from .rules import ensure,record,state,person_reason,choose,proposals
from ..economy.ledger import account,balance,transfer_value
from ...regional_context import ordinary_year,region

def close(game,scope,row,job,status,message):
    left=balance(game,job['wallet'])
    transfer_value(game,job['wallet'],job['source'],left,'机构事务未耗原款退回')
    job.update(status=status,closed=game.player.age,refunded=left,result=message)
    row['history']=(row['history']+[copy.deepcopy(job)])[-12:]
    row.pop('job',None);row['revision']+=1

def start(game,scope,offer,person,*,automatic=False,adapter=None):
    row=ensure(game,scope['id'])
    row['provider']=scope['provider']
    if row.get('job'):raise ValueError('此机构已有在办事务')
    if offer.get('reason'):raise ValueError(offer['reason'])
    if person not in scope['people']:raise ValueError('此人不具备本机构执行资格')
    if blocked:=person_reason(game,person,scope['world'],scope['location'],assignment='institution-delegate:'+scope['id']):raise ValueError(blocked)
    if offer['budget']>scope['available']:raise ValueError('原府库不足，或将侵占基本维护准备金')
    if automatic and offer['budget']>row.get('limit',0):raise ValueError('超过已授权的单项预算，须请示')
    root=state(game);serial=root['sequence']+1
    wallet=f'institution-project:{game.id}:{serial}';account(game,wallet)
    transfer_value(game,scope['payer'],wallet,offer['budget'],'机构项目唯一预算托管')
    root['sequence']=serial
    job=dict(id='institution-job:'+str(serial),world=scope['world'],location=scope['location'],scope=scope['id'],
        provider=scope['provider'],person=person,source=scope['payer'],wallet=wallet,offer=copy.deepcopy(offer),
        status='active',phase='institution',started=game.player.age,last_year=game.player.age,deadline=game.player.age+max(100,offer['years']*4),
        years=offer['years'],progress=0,funded=offer['budget'],spent=0,wages=0,blocked='',automatic=automatic)
    row['job']=job;row['revision']+=1
    if adapter and hasattr(adapter,'on_start'):adapter.on_start(game,scope,job)
    row['proposals']=[p for p in row['proposals'] if p['key']!=offer['key']]
    return job

def advance(game,maps,adapter):
    if not ordinary_year(game):return
    now=game.player.age;world=region(game) or game.player.world
    all_scopes={s['id']:s for s in adapter.scopes(game,maps)}
    scopes={key:s for key,s in all_scopes.items() if s['world']==world}
    # Dissolved scopes cannot expose local controls. Close their original liability once.
    for key,row in list(state(game).get('scopes',{}).items()):
        job=row.get('job')
        if job and job['provider']==adapter.ID and job['world']==world and key not in scopes and job['last_year']<now:
            close(game,None,row,job,'cancelled','原机构、产权或职责失效，未耗原款退回原付款人。')
            row.update(delegate=None,automatic=False)
        if row.get('provider')==adapter.ID and key not in all_scopes:
            row.update(delegate=None,automatic=False)
    for scope in scopes.values():
        row=record(game,scope['id']);job=row.get('job')
        if row and row.get('last_tick',-1)>=now:continue
        if row:row['last_tick']=now
        if row and not scope['controlled']:
            row.update(delegate=None,automatic=False)
        if job and job['last_year']<now:
            job['last_year']=now
            blocked=person_reason(game,job['person'],job['world'],job['location'],assignment=job['id'])
            if not blocked and job['person'] not in scope['people']:blocked='原任职或执行资格已经变化'
            if now>=job['deadline']:
                close(game,scope,row,job,'cancelled','项目逾期自动交接，未耗原款退原付款人。')
                continue
            if not blocked:blocked=adapter.validate(game,maps,scope,job)
            job['blocked']=blocked
            if not blocked:
                if job['progress']<job['years']:
                    wage=job['offer']['wage']
                    if balance(game,job['wallet'])<wage:job['blocked']='原劳务托管不足，暂停请示';continue
                    transfer_value(game,job['wallet'],'background:'+world,wage,'机构原执行人实际年度劳务')
                    job['wages']+=wage;job['spent']+=wage;job['progress']+=1
                if job['progress']==job['years']:
                    try:
                        result=adapter.deliver(game,maps,scope,job)
                    except ValueError as error:
                        job['blocked']=str(error)
                    else:
                        close(game,scope,row,job,'completed',result)
        # Observe at most once per 25 ordinary years. Reading the UI does not propose.
        if now//25<=row.get('last_observed',-1):continue
        offers=adapter.offers(game,maps,scope)
        eligible=[n for n in scope['people'] if not person_reason(game,n,world,scope['location'],assignment='institution-delegate:'+scope['id'])]
        if not offers or not eligible:continue
        row=ensure(game,scope['id']);row['last_observed']=now//25;row['last_tick']=now;row['provider']=scope['provider']
        proposer=row.get('delegate') if row.get('delegate') in eligible else eligible[0]
        row['proposals']=proposals(offers,[proposer]*3,row['policy'],scope['available'],now)
        from ..institution_deliberation import cosign
        signatures=cosign(offers,eligible,row['policy'],scope['available'])
        for proposal in row['proposals']:proposal['supporters']=signatures.get(proposal['key'],[])
        row['revision']+=1
        if row.get('job'):continue
        if scope['controlled']:
            if not row.get('automatic') or not row.get('delegate'):continue
            cap=min(scope['available'],row['limit']);person=row['delegate']
        else:
            cap=min(scope['available'],scope['automatic_budget']);person=proposer
        selected=choose(offers,row['policy'],cap)
        if selected:
            start(game,scope,selected,person,automatic=scope['controlled'],adapter=adapter)

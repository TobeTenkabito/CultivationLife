"""Original regional years and MapCatalog journeys for bound court officers."""
from ..content_registry import WORLD_SYSTEMS
from ..relationship_records import find_person
from .court_bureau_rules import state, active, personal, reason, officer_reason
from .faction_geography import person_site
from .economy.ledger import transfer_value
from .court_bureau_travel import route

def work_reason(game):
    if blocked:=reason(game):return blocked
    from . import court_inspection as inspection
    if inspection.active(game):return inspection.work_reason(game)
    s=state(game);review=s.get('review')
    job=next((j for j in active(game) if review and j['id']==review['job']),None) if review else personal(game)
    if not job:return '没有本人正在办理或复核的公务'
    if game.player.age>=job['deadline']:return '公务已逾期，请办理交接'
    if game.player.location_id!=job['location']:return '须亲临'+job['place_name']+'办理；请沿原地图前往'
    if review:
        if job['phase']!='ready':return '属员尚未完成现场工作'
        npc=find_person(game,job['person'])
        if blocked:=officer_reason(game,npc,assigned=True):return blocked
        if person_site(game,npc)!=job['location']:return '原属员已离开交付现场'
    elif job['offer'].get('operation'):
        from .court_enforcement import action_reason
        if blocked:=action_reason(game,job):return blocked
    elif job['kind']=='patrol':
        if not any(h.event_id=='SYS_MAP_TRAVEL' and h.age>=job['started'] and h.result=='arrived'
            and h.state_diff.get('from')==job['origin'] and h.state_diff.get('to')==job['location'] for h in game.history):
            return '巡检须实际沿原地图走完指定道路，传送不算巡查'
    return ''

def begin_work(game):
    if blocked:=work_reason(game):raise ValueError(blocked)
    from .court_inspection import current_work
    row=current_work(game) or state(game).get('review') or personal(game)
    left=row['years']-row['progress']
    if left<=0:raise ValueError('实际工时已足，请验收交付')
    return left

def finish_work(game,elapsed,unit):
    from . import court_inspection as inspection
    row=state(game).get('review') or personal(game)
    if inspection.active(game):inspection.finish(game,elapsed)
    elif row:
        row['progress']=min(row['years'],row['progress']+elapsed)
        if 'wallet' in row:
            transfer_value(game,row['wallet'],'background:celestial',elapsed*1000,'本人公务实际履约劳务')
            row['spent']+=elapsed*1000
            if row['progress']>=row['years']:row['phase']='ready'
    westward=game.yaochi_state.setdefault('westward',{})
    units,westward['settlement_years']=divmod(westward.get('settlement_years',0)+elapsed,unit)
    return units

def year_step(game,maps):
    from ..regional_context import region, ordinary_year
    from .westward_rules import enabled
    if (region(game) or game.player.world)!='celestial' or not ordinary_year(game):return
    now=game.player.age
    for job in active(game):
        if job['phase']=='evacuating':
            if job['last_year']<now:
                job['last_year']=now
                from .court_enforcement import advance_evacuation
                advance_evacuation(game,maps,job)
            continue
        if job['person']=='player' or job['last_year']>=now:continue
        job['last_year']=now
        # Disabled content pauses service, but an already requested return remains possible.
        if not enabled() and job['phase']!='homeward':continue
        npc=find_person(game,job['person'])
        blocked=officer_reason(game,npc,assigned=True)
        if blocked:job['blocked']=blocked;continue
        leg=job.get('leg');expected=leg['origin'] if job['phase'] in {'outbound','homeward'} else job['location']
        if person_site(game,npc)!=expected:job['blocked']='原人物已离开约定地点，暂停且不移动替身';continue
        job['blocked']=''
        if job['phase'] in {'outbound','homeward'}:
            if maps.travel_plan('celestial',leg['origin'],leg['destination'],npc.realm_index).status!='ok':
                job['blocked']='原道路或修为资格已经变化';continue
            leg['progress']+=1
            if leg['progress']>=leg['years']:
                from .combat.npc_lifecycle import settle
                settle(npc,now,WORLD_SYSTEMS.get('transcendent_combat',{}))
                npc.location_id=leg['destination']
                if job['phase']=='homeward':job['phase']='handover'
                else:job['phase']='work'
        elif job['phase']=='work':
            job['progress']+=1
            if job['progress']>=job['years']:job['phase']='ready'
        else:continue
        transfer_value(game,job['wallet'],'background:celestial',1000,'属员公务实际差旅与劳务')
        job['spent']+=1000

def recall(game,maps,job):
    if job['phase']=='evacuating':raise ValueError('伤者正在实际转运，须先抵达并交接，不能撤销已走行程')
    if job['phase'] in {'homeward','handover'}:raise ValueError('已在返程或等待交接，不可重置路程')
    npc=find_person(game,job['person'])
    if blocked:=officer_reason(game,npc,assigned=True):raise ValueError(blocked)
    here=person_site(game,npc)
    if here==job['home']:
        job['phase']='handover';job.pop('leg',None)
    else:
        leg=route(maps,game,npc,here,job['home'])
        from .economy.ledger import balance
        if balance(game,job['wallet'])<leg['years']*1000:raise ValueError('原返程预留不足，须先恢复原道路再交接')
        job.update(phase='homeward',leg=leg)
    state(game).pop('review',None)

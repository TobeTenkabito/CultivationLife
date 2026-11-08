"""Local warrants, original combatants and paid physical casualty evacuation."""
from ..content_registry import WORLD_SYSTEMS
from ..economy_content import product_id
from ..npc_custody import is_free, kill_person
from ..relationship_records import find_person
from ..person_assignments import research_assignment
from ..spatial_people import instance_of
from ..runtime import decode_rng, encode_rng
from .court_bureau_rules import state, jobs, officer_reason
from .faction_geography import person_site
from .building_assets import local_rows
from .economy.ledger import transfer_value
from .court_bureau_travel import route

def safe_destination(game,dest):
    from ..building_rules import initial_rows
    address=dict(world='celestial',instance_id=None,location_id=dest)
    rows=[game.building_state.get('records',{}).get(r['id'],r) for r in initial_rows(address) if r['type']=='city']
    return any(r.get('public') and r['status']=='intact' for r in rows)

def person_reason(game,npc,*,job=None):
    if not npc or not is_free(npc) or npc.world!='celestial' or instance_of(game,npc.id):return '原人物已失效、受控或不在仙界普通地点'
    if npc.id in game.intrigue_state.get('npc_prisons',{}):return '原人物正在机构监禁中，巡天职司没有越权释放许可'
    held=research_assignment(game,npc.id)
    if held and (not job or held['id']!=job['id']):return '原人物已有其他任务占用'
    if any((r.get('npc_id') or r.get('id'))==npc.id for r in game.player.party):return '同行人物须先解除同行安排'
    return ''

def offers(game,maps):
    place=game.player.location_id;out=[]
    seen={j['offer'].get('target') for j in jobs(game) if j['offer'].get('operation')=='bounty'}
    for identity in game.heavenly_court.get('wanted_ids',[]):
        npc=find_person(game,identity)
        if identity in seen or person_reason(game,npc) or person_site(game,npc)!=place:continue
        out.append(dict(operation='bounty',target=identity,location=place,name='持令讨伐 · '+npc.name,
            materials={},coins=0,years=5,target_state=[npc.realm_index,npc.layer,npc.wounds],
            detail='核验现行天庭通缉令，实际准备五年后在场交锋。击退或致命讨伐由你选择；可能负伤、逃脱或阵亡。'))
    # Only actual locally observable people; no remote scan exposes a patient's whereabouts.
    candidates={**game.world_npcs,**game.notable_npcs}
    candidates.update({k:n for k in game.heavenly_court.get('officials',{}) if (n:=find_person(game,k))})
    for npc in sorted(candidates.values(),key=lambda n:n.id):
        if npc.wounds<2 or person_site(game,npc)!=place or person_reason(game,npc):continue
        if npc.id in game.heavenly_court.get('wanted_ids',[]):continue
        destinations=[]
        for edge in maps.worlds['celestial']['routes']:
            if place not in (edge['from'],edge['to']):continue
            dest=edge['to'] if edge['from']==place else edge['from']
            if not safe_destination(game,dest):continue
            try:leg=route(maps,game,npc,place,dest)
            except ValueError:continue
            destinations.append(leg)
        if not destinations:continue
        leg=min(destinations,key=lambda r:(r['years'],r['destination']))
        item=product_id('celestial',max(9,npc.realm_index),'healing')
        out.append(dict(operation='rescue',target=npc.id,location=place,name='救治转运 · '+npc.name,
            materials={item:1},coins=0,years=1,evacuation=leg,target_state=[npc.realm_index,npc.layer,npc.wounds],
            detail='实购对应阶疗伤丹，现场救护一年，再沿原道路转运至'+maps.location('celestial',leg['destination'])['name']+'。自然恢复不冻结；没有原伤者不生成救援。'))
        if len(out)>=16:break
    return out

def action_reason(game,job):
    operation=job['offer'].get('operation');npc=find_person(game,job['offer']['target'])
    if not operation:return ''
    if job.get('operation_done'):return ''
    if blocked:=person_reason(game,npc,job=job):return blocked
    if person_site(game,npc)!=job['location']:return '原目标已离开案发地点，须交接旧案后重新核实'
    if operation=='bounty' and npc.id not in game.heavenly_court.get('wanted_ids',[]):return '原通缉令已撤销，不得继续讨伐'
    if job['person']!='player':
        actor=find_person(game,job['person'])
        if blocked:=officer_reason(game,actor,assigned=True):return blocked
        if person_site(game,actor)!=job['location']:return '执行属员尚未实际到场'
    return ''

def fight(deps,game,job,mode):
    if job['offer'].get('operation')!='bounty' or job.get('battle'):raise ValueError('本案不允许再次交锋，失败须交接，不重抽战果')
    if job['phase']!='ready' or job['progress']<job['years']:raise ValueError('须先完成实际巡查准备')
    if game.player.location_id!=job['location']:raise ValueError('须亲临现场指挥交战')
    if blocked:=action_reason(game,job):raise ValueError(blocked)
    if mode not in {'repel','kill'}:raise ValueError('须明确击退或致命讨伐')
    npc=find_person(game,job['offer']['target']);rng=decode_rng(game.seed,game.rng_state)
    if job['person']=='player':
        from .mentorship_advanced import battle_target
        target=battle_target(npc,deps._npc_power);target.update(court_authorized=True,objective=mode)
        result,summary=deps._combat(game,target,mode=='kill',rng)
        success=(result=='victory' if mode=='repel' else not npc.alive)
        report=dict(result=result,summary=summary,target=npc.id,mode=mode,killed=not npc.alive)
    else:
        from .combat.npc_battle import resolve_local_engagement
        from .doctrine.provider import battle_sources
        actor=find_person(game,job['person'])
        outcome=resolve_local_engagement([(actor,deps._npc_power(actor))],[(npc,deps._npc_power(npc))],
            WORLD_SYSTEMS.get('transcendent_combat',{}),rng,now=game.player.age,
            sources=battle_sources(game,{actor.id:actor,npc.id:npc}),attacker_objective=mode,defender_objective='kill')
        for person in (actor,npc):
            if person.id in outcome.killed and not person.alive:kill_person(game,person.id,'巡天持令交战中陨落')
        success=actor.alive and (outcome.outcome=='victory' if mode=='repel' else npc.id in outcome.killed and not npc.alive)
        outcome_name={'victory':'获胜','defeat':'败退','stalemate':'相持'}.get(outcome.outcome,'交锋结束')
        report=dict(result=outcome.outcome,target=npc.id,mode=mode,killed=npc.id in outcome.killed,
            rounds=list(outcome.rounds),summary=f'原属员实际交锋{len(outcome.rounds)}轮：{outcome_name}；击退、镇压、逃脱和真实死亡分别保留。')
    game.rng_state=encode_rng(rng);job['battle']=report;job['operation_done']=success
    if not success:job['phase']='failed'
    return report['summary']+(' 请核验交付本案。' if success else ' 本案未达成目标，不发公务报酬，须返回交接。')

def evacuate(game,maps,job):
    if job['offer'].get('operation')!='rescue' or job.get('evacuation'):raise ValueError('救援已经启动或不是救援案')
    if job['phase']!='ready' or job['progress']<job['years']:raise ValueError('须先完成现场救护工时')
    if game.player.location_id!=job['location']:raise ValueError('须到现场核验伤者与转运安排')
    if blocked:=action_reason(game,job):raise ValueError(blocked)
    npc=find_person(game,job['offer']['target']);dest=job['offer']['evacuation']['destination']
    if not safe_destination(game,dest):raise ValueError('原接收城市已损毁或不再公开，不能转运')
    leg=route(maps,game,npc,job['location'],dest)
    if job['person']!='player':
        escort=find_person(game,job['person']);escort_leg=route(maps,game,escort,job['location'],dest)
        leg['years']=max(leg['years'],escort_leg['years'])
    if leg['years']>job['offer']['evacuation']['years']:raise ValueError('原转运路线耗时已变化，请交接后重新备款')
    item=next(iter(job['offer']['materials']))
    if job['cargo'].get(item,0)<1:raise ValueError('原救护药物不足')
    treated=min(1,npc.wounds)
    if treated:
        from .combat.npc_lifecycle import relieve_wounds
        relieve_wounds(npc,1);job['cargo'][item]-=1
        if not job['cargo'][item]:job['cargo'].pop(item)
    job.update(evacuation=leg,treated=treated,phase='evacuating')
    return f'原伤势实际减轻{treated}级；按原道路转运{leg["years"]}年，抵达前不能结案。'

def evacuation_reason(game,maps,job):
    npc=find_person(game,job['offer']['target']);leg=job['evacuation']
    if not safe_destination(game,leg['destination']):return '原接收城市已损毁或不再公开，暂停转运'
    if blocked:=person_reason(game,npc,job=job):return blocked
    people=[npc]
    if job['person']!='player':
        escort=find_person(game,job['person'])
        if blocked:=officer_reason(game,escort,assigned=True):return blocked
        people.append(escort)
    if any(person_site(game,n)!=leg['origin'] or maps.travel_plan('celestial',leg['origin'],leg['destination'],n.realm_index).status!='ok' for n in people):
        return '原转运人物、地点或通行资格变化，暂停且不搬动替身'
    return ''

def advance_evacuation(game,maps,job):
    if blocked:=evacuation_reason(game,maps,job):job['blocked']=blocked;return
    leg=job['evacuation'];people=[find_person(game,job['offer']['target'])]
    if job['person']!='player':people.append(find_person(game,job['person']))
    job['blocked']='';leg['progress']+=1
    transfer_value(game,job['wallet'],'background:celestial',1000,'救援实际转运劳务');job['spent']+=1000
    if leg['progress']>=leg['years']:
        from .combat.npc_lifecycle import settle
        for person in people:
            settle(person,game.player.age,WORLD_SYSTEMS.get('transcendent_combat',{}));person.location_id=leg['destination']
        job.update(location=leg['destination'],place_name=maps.location('celestial',leg['destination'])['name'],phase='ready',operation_done=True)

def abort_reason(game,maps,job):
    if job['phase']!='evacuating':return '没有在途转运'
    leg=job['evacuation']
    if game.player.location_id!=leg['origin']:return '须亲临原转运保管地点处理失效案卷'
    if not evacuation_reason(game,maps,job):return '原伤者、护送属员与道路仍可继续转运，不能重置已走行程'
    return ''

def abort(game,maps,job):
    if blocked:=abort_reason(game,maps,job):raise ValueError(blocked)
    job.update(phase='failed',evacuation_aborted=True)
    return '转运条件已经失效，保留原人物地点与已耗路费；本案不发报酬，须按原公物交接流程结清。'

def delivery(game,job):
    if not job.get('operation_done'):raise ValueError('须完成实际讨伐或救援转运，工时足额不等于任务完成')
    if job['offer']['operation']=='bounty':return '原持令交战已经核验；不把击退或镇压冒记为死亡。'
    npc=find_person(game,job['offer']['target'])
    if person_reason(game,npc,job=job) or person_site(game,npc)!=job['location']:raise ValueError('原获救者不在交接现场，不能凭转运文字结案')
    return f'原伤者已实际抵达{job["place_name"]}；救护减轻{job.get("treated",0)}级伤势，身份与原资源保留。'

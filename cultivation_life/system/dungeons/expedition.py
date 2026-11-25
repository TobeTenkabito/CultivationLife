"""Frozen branch, contract and evidence definitions; no offscreen person inventories."""
from ...definition_data import definition as _content_definition
from ...rules import combat_power, expected_combat_power, max_hp, max_mp, remove_item
from . import prose
from .ecology import appearance_depth, close_realms
from .prose_expansion import EPIC_RESULTS, LEGENDARY_RESULTS, RUMORS, DEPARTURES, TREASURES


ESCAPE_ROUTES = _content_definition(__name__, "ESCAPE_ROUTES")


def blueprint(site, rng, reward_factory):
    nodes=site['nodes'];roles=site['roles']
    routes={n['id']:dict(destination=min(len(nodes)-1,i+rng.randint(2,3)),
        direction=rng.choice(ESCAPE_ROUTES),cost=round(rng.uniform(.04,.08),3))
        for i,n in enumerate(nodes[:-2])}
    goals={}
    for key,role in roles.items():
        target=rng.choice(nodes)['reward']['id']
        desires={n['reward']['id']:rng.randint(15,50) for n in nodes}
        desires[target]=role['desire']
        goals[key]=dict(target=target,desires=desires,fulfilled=False,work=0,seen_power=0.)
        role['ledger']['representative']=site['quality'] in {'epic','legendary'} and bool(role['sect_id'])
        role['ledger']['supporters']=[]
    if site['quality'] in {'epic','legendary'}:
        for role in roles.values():
            role['ledger']['supporters']=[r['id'] for r in roles.values()
                if r['sect_id'] and r['sect_id']==role['sect_id'] and r['id']!=role['id']
                and close_realms(r['realm'],role['realm'])
                and appearance_depth(site,r)<=appearance_depth(site,role)][:2]
    facts=[]
    if site['quality'] in {'epic','legendary'}:
        for i in range(2):
            a,b=rng.sample(list(roles),2)
            if i==0 and site['quality']=='legendary':
                a=next(reversed(roles));b=rng.choice([key for key in roles if key!=a])
            rivals=[key for key in roles if roles[key]['sect_id']!=roles[a]['sect_id']]
            if rivals:b=rng.choice(rivals)
            fact_id=site['id']+':news:'+str(i)
            facts.append(dict(id=fact_id,actors=[a,b],direction=rng.choice(('东','西','南','北')),
                occurred=1+i*2,reported=2+i*2,verified=4+i*2,
                result=rng.choice(EPIC_RESULTS if site['quality']=='epic' else LEGENDARY_RESULTS),
                mistaken=rng.random()<.4,
                scope=rng.choice(('person','sect')),winner=rng.choice((a,b)),
                treasure=dict(id=fact_id+':background',name=rng.choice(TREASURES))))
            facts[-1]['rumor']=rng.choice(RUMORS).format(direction=facts[-1]['direction'])
            if not any(roles[k]['ledger'].get('domain_rank') for k in (a,b)):
                facts[-1]['result']=facts[-1]['result'].replace('强横灵域','凌厉剑光')
    return dict(version=2,routes=routes,route_choices=[],goals=goals,contracts={},
        bonuses=[reward_factory(i) for i in range(2)],bonus_claims=[],facts=facts,evidence={},
        settlements=[],performance=dict(wins=0,helped=0,escapes=0))


def current_desire(site,role):
    goal=site.get('expedition',{}).get('goals',{}).get(role['id'])
    if not goal:return role['desire']
    node=site['nodes'][min(site['step'],len(site['nodes'])-1)]
    value=goal['desires'].get(node['reward']['id'],role['desire'])
    if goal['target'] in site['claims']:value=max(value,goal['desires'][goal['target']])
    return value


def witnessed(game,site,observers):
    """Only a real fight reveals the player's performance to present witnesses."""
    ex=site.get('expedition')
    if not ex:return
    for key in set(observers):
        if key in ex['goals']:ex['goals'][key]['seen_power']=combat_power(game.player)


def observe(site,role,metric,text,low,high,log):
    # These intervals describe the visible behaviour, not hidden intention +/- noise.
    role['ledger'].setdefault('evidence',{})[metric]=dict(low=low,high=high,step=site['step'],text=text)
    if metric=='desire' and site['step']<len(site['nodes']):
        target=site['nodes'][site['step']]['reward']['id']
        role['ledger'].setdefault('treasure_evidence',{})[target]=dict(low=low,high=high,step=site['step'],text=text)
    role['ledger'].setdefault('observed',{})[metric]=round((low+high)/2)
    role['clues'].append(dict(step=site['step'],text=text))
    log(site,role['name']+text,actors=[role['id']])


def conduct(game,site,role,log):
    ex=site.get('expedition');goal=ex and ex['goals'].get(role['id'])
    if not goal:return False
    goal['work']+=1
    purpose=role['purpose'];current=site['nodes'][min(site['step'],len(site['nodes'])-1)]['reward']
    if purpose=='seek' and current['id']==goal['target']:
        observe(site,role,'desire','指着眼前的'+current['name']+'反复追问归属。',65,90,log)
    elif purpose in {'rescue','escort'} and goal['work']==2:
        observe(site,role,'caution','沿路寻找同门留下的记号，并反复核查退路。',50,80,log)
    elif purpose=='heal' and goal['work']==1:
        observe(site,role,'caution','服下一小包药粉，面色仍有些苍白。',45,75,log)
    elif purpose=='observe' and goal['work']==2:
        observe(site,role,'preparation','询问你先前如何破阵，在玉简中记下几笔。',35,65,log)
    # Completion is private. All exits give ambiguous visible accounts.
    target_node=next(n for n in site['nodes'] if n['reward']['id']==goal['target'])
    passed_target=any(h['id']==target_node['id'] and h['choice']=='bypass' for h in site['node_history'])
    completed=(purpose=='seek' and passed_target or
        purpose=='heal' and ex['contracts'].get(role['id'],{}).get('state')=='fulfilled' or
        purpose in {'escort','rescue'} and goal['work']>=4 or
        purpose=='observe' and goal['seen_power']>0 and goal['work']>=3)
    if completed and purpose!='assassinate':
        goal['fulfilled']=True
        role.update(state='left',left_step=site['step'])
        site['party'].remove(role['id'])
        log(site,role['name']+prose.variant(role['id'],DEPARTURES),actors=[role['id']])
        return True
    return False


def news(site,log,label):
    ex=site.get('expedition')
    if not ex:return False
    for fact in ex['facts']:
        step=site['step'];level=ex['evidence'].get(fact['id'],0)
        stage=3 if step>=fact['verified'] and site['depth']>=2 else 2 if step>=fact['reported'] else 1 if step>=fact['occurred'] else 0
        direction=fact['direction'];occurred=fact['occurred']
        if 'space' in site:
            from .trails import bearing,here
            space=site['space'];echo=space['echoes'].get(fact['id'])
            if not echo:continue
            at,occurred=echo;step=space['turn'];direction=bearing(space,here(site),at)
            stage=3 if here(site)==at and space['turn']>occurred else 2 if space['turn']>occurred else 1
        if stage<=level:continue
        a,b=[site['roles'][k] for k in fact['actors']]
        if stage==1:
            text=fact.get('rumor') or f"听说在{fact['direction']}方有灵力波动，杀气重重，想来是有不得了的人物在交手。"
            if 'space' in site:text=f'听说{direction}有两股灵力相撞，余波震得山石簌簌作响。'
            kind,source='听说','不明来历的传言'
        elif stage==2:
            if 'treasure' in fact:
                winner=site['roles'][fact['winner']]
                reported=next(r for r in (a,b) if r['id']!=winner['id']) if fact['mistaken'] else winner
                subject=f"{label(a)}与{label(b)}" if fact['scope']=='person' else f"由{label(a)}领衔的一方与{label(b)}所代表的一方"
                text=f"据说{subject}争夺{fact['treasure']['name']}，{fact['result']}。宝物随后落入{reported['sect_name']}一方手中。"
            else:
                reported=b if fact['mistaken'] else a
                text=f"据说{label(reported)}所代表的门派在与另一方争夺阵枢时，{fact['result']}。"
            kind,source='据说','撤离修士转述'
        else:
            sides=f"{a['sect_name']}与{b['sect_name']}" if a['sect_id']!=b['sect_id'] else a['sect_name']+'的两支队伍'
            text=f"你在交手处看见残破阵旗与战痕，确认{sides}曾在此交锋。"
            if 'treasure' in fact:
                winner=site['roles'][fact['winner']]
                text+=f"侧廊中，{winner['sect_name']}修士当面接过{fact['treasure']['name']}，随后合拢护阵，将宝物带向其阵地。"
                if fact['mistaken'] and level==2:text+='先前关于宝物归属的说法已由此次目击修正。'
                kind,source='实证','现场战痕与宝物交接'
            else:
                kind,source='实证','现场战痕'
        log(site,text,kind,actors=fact['actors'] if stage==2 else (),source=source)
        site['logs'][-1].update(fact_id=fact['id'],occurred_step=occurred,received_step=step,
            supersedes=next((r['id'] for r in reversed(site['logs'][:-1]) if r.get('fact_id')==fact['id']),None))
        ex['evidence'][fact['id']]=stage
        if stage==3 and level==2 and fact['mistaken'] and 'treasure' not in fact:
            log(site,'一名伤者指着阵旗，称先前传话时认错了归属，原先的归属说法已撤回。','据说',source='伤者转述')
            site['logs'][-1].update(fact_id=fact['id'],occurred_step=occurred,received_step=step,
                supersedes=site['logs'][-2]['id'])
    return True


def bargain(game,site,role,choice,log):
    ex=site.get('expedition')
    if not ex or role['id'] not in site['party'] or site['pending']:raise ValueError('当前无法交涉')
    contract=ex['contracts'].get(role['id'])
    if choice=='promise':
        if contract:raise ValueError('已有交付记录，不能重置约定')
        # One real restorative item, consumed on delivery. No simulated NPC bag.
        ex['contracts'][role['id']]=dict(state='promised',item_id=None,step=site['step'])
        log(site,'你答应给'+role['name']+'一份可当场服用的恢复药物，对方答应助你辨认一处阵势。',actors=[role['id']])
    elif choice=='deliver':
        if not contract or contract['state']!='promised':raise ValueError('没有待交付约定')
        item=next((i for i in game.player.inventory if i.quantity>0 and 'dungeon_restorative' in i.tags),None)
        if not item:raise ValueError('行囊中没有可交付的探境恢复药物')
        if not remove_item(game.player,item.id):raise ValueError('原药物已不在行囊')
        from ...relationship_records import find_person
        from ..combat.npc_lifecycle import relieve_wounds
        npc=find_person(game,role['npc_id'])
        if npc:relieve_wounds(npc,1)
        contract.update(state='fulfilled',item_id=item.id)
        role['trust']=min(100,role['trust']+18);site['preparations']+=1
        node=site['nodes'][min(site['step'],len(site['nodes'])-1)]
        if node['id'] not in site['branches']:site['branches'].append(node['id'])
        log(site,role['name']+'当面服下你交付的'+item.name+'，随后指出阵势的薄弱处；这次交易已经履行。',actors=[role['id']])
        observe(site,role,'trust','如约指出阵眼，并在你核实后退开。',65,85,log)
    elif choice=='break':
        if not contract or contract['state']!='promised':raise ValueError('没有可撤回的约定')
        contract['state']='broken';role['trust']=max(0,role['trust']-25)
        log(site,'你撤回交药约定，'+role['name']+'收起了原本指向阵眼的手。',actors=[role['id']])
    else:raise ValueError('未知交涉选择')


def escape_chance(game,site,enemies):
    strength=sum(expected_combat_power(r['realm'],r['layer'])*r['power_factor'] for r in enemies)
    ratio=combat_power(game.player)/max(1,strength)
    health=max(.1,game.player.hp/max(1,max_hp(game.player)))
    preparation=min(.2,site['preparations']*.025)
    blockage=min(.2,len(enemies)*.04+max(r['preparation'] for r in enemies)*.001)
    return max(.03,min(.95,.45*ratio*health+preparation-blockage))


def detour(game,site,log):
    ex=site.get('expedition');node=site['nodes'][site['step']]
    route=ex and ex['routes'].get(node['id'])
    if not route or node['id'] not in site['branches']:raise ValueError('尚未探明可用侧路')
    cost=max_mp(game.player)*route['cost']
    if game.player.mp<cost:raise ValueError('法力不足以护身穿越侧路')
    game.player.mp-=cost
    ex['route_choices'].append(dict(node=node['id'],destination=route['destination']))
    site['node_history'].append(dict(id=node['id'],choice='detour'))
    site['step']=route['destination']
    log(site,'你从'+route['direction']+'穿行，绕过了正路上的争夺。')

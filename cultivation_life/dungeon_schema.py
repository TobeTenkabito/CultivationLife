"""Versioned local expedition records. Validation never generates content."""
import copy
import math

VERSION = 1
QUALITIES = ('ordinary', 'rare', 'epic', 'legendary')
PURPOSES = ('seek', 'heal', 'escort', 'rescue', 'observe', 'assassinate')
WORLD_IDS = {'human','spirit','demon','true_demon','phantom_underworld','hell',
             'monster_realm','celestial','asura','nether','reincarnation'}


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('副本整数超出有效范围')


def finite(value, low=0, high=1e30):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('副本数值无效')


def fields(row, required, optional=()):
    if not isinstance(row, dict) or set(row) - set(required) - set(optional) or set(required) - set(row):
        raise ValueError('副本记录字段无效')


def empty():
    return dict(version=VERSION, maps={}, legends={}, instances={}, active=None, mail=[],
                ready_age=0., invite_marks={}, text_fingerprints=[], manuals={})


def decode(value):
    if value == {}:
        return {}
    fields(value, empty())
    if value['version'] != VERSION:
        raise ValueError('不支持的副本结构，保留原记录')
    for key in ('maps','legends','instances','invite_marks','manuals'):
        if not isinstance(value[key],dict):raise ValueError('副本映射无效')
    finite(value['ready_age'])
    if not isinstance(value['mail'],list) or not isinstance(value['text_fingerprints'],list) or len(value['text_fingerprints'])>160000:
        raise ValueError('副本信件或文本记录无效')
    if len(value['instances']) > 10000 or len(value['mail']) > 20000:
        raise ValueError('副本记录数量超限')
    for identity, row in value['instances'].items():
        fields(row, {'id','world','location_id','name','quality','realm','layer','ceiling','theme',
            'terrain','conditions','slot','seed','reference','roles','nodes','status','revision','step',
            'depth','logs','party','claims','pending','entered','unit','preparations','agreements',
            'revealed','last_result','node_history','branches','initiator'}, {'expedition','space'})
        if row['id'] != identity or row['world'] not in WORLD_IDS or row['quality'] not in QUALITIES:
            raise ValueError('副本身份或界面无效')
        integer(row['realm'],1,12);integer(row['ceiling'],1,12);integer(row['layer'],1,13)
        integer(row['revision'],0,100000);integer(row['step'],0,10000);integer(row['slot'],0,99)
        integer(row['seed'],0,2**32-1)
        if len(row['reference'])!=2:raise ValueError('副本生成修为快照无效')
        integer(row['reference'][0],0,12);integer(row['reference'][1],1,13)
        finite(row['unit']);integer(row['depth'],0,100)
        if row['status'] not in {'open','active','closed'} or not isinstance(row['entered'],bool):
            raise ValueError('副本生命周期无效')
        if not isinstance(row['roles'],dict) or len(row['roles'])>34 or not 4<=len(row['nodes'])<=32:
            raise ValueError('副本角色或节点超限')
        if row['step']>len(row['nodes']):raise ValueError('副本探索位置越界')
        if row['status']=='active' and (not row['entered'] or row['unit']<=0):raise ValueError('入境记录缺失')
        person_ids=[]
        for key, role in row['roles'].items():
            fields(role, {'id','name','sect_id','sect_name','realm','layer','true_realm','path','purpose',
                'desire','resolve','preparation','trust','caution','npc_id','existing','state','known',
                'clues','target','story','power_factor','joined_step','left_step','revealed','materialized',
                'ledger','offer_step'})
            if key != role['id'] or role['purpose'] not in PURPOSES:raise ValueError('副本角色目的无效')
            for metric in ('desire','resolve','preparation','trust','caution'):finite(role[metric],0,100)
            for metric in ('realm','true_realm'):integer(role[metric],0 if role['existing'] else 1,12)
            integer(role['layer'],1,13)
            finite(role['power_factor'],.1,10)
            if role['materialized'] != bool(role['npc_id']):raise ValueError('人物实例化引用不一致')
            if role['npc_id']:person_ids.append(role['npc_id'])
            if not isinstance(role['clues'],list) or len(role['clues'])>100:raise ValueError('人物观察线索无效')
            for clue in role['clues']:
                fields(clue,{'step','text'});integer(clue['step'],0,100)
                if not isinstance(clue['text'],str):raise ValueError('线索文本无效')
            if role['state'] not in {'unseen','contact','invited','joined','left','missing','hostile','dead','declined','observed'}:
                raise ValueError('副本队员状态无效')
            validate_observations(row,role)
        if len(person_ids)!=len(set(person_ids)):raise ValueError('同一人物不能重复出现')
        if row['pending'] is not None:
            pending=row['pending'];fields(pending,{'kind','actor'}, {'other','aftermath','snared','intercepted','pursuers'})
            if pending['kind'] not in {'join','ambush','guardian','conflict','settlement'} or pending['actor'] not in row['roles']:
                raise ValueError('副本待处理交互无效')
            if 'intercepted' in pending and (pending['kind']!='ambush' or pending['intercepted'] is not True):raise ValueError('追击拦截无效')
            if 'snared' in pending and (not pending.get('intercepted') or pending['snared'] is not True):raise ValueError('伏阵拦截无效')
            if 'pursuers' in pending:
                group=pending['pursuers']
                if not pending.get('intercepted') or not isinstance(group,list) or not group or any(k not in row['roles'] or k==pending['actor'] for k in group) or len(group)!=len(set(group)):raise ValueError('追兵名单无效')
            if pending['kind']=='conflict' and (pending.get('other') not in row['roles'] or pending['other']==pending['actor']):
                raise ValueError('副本争夺双方无效')
            if pending['kind']=='settlement' and 'expedition' not in row:raise ValueError('善后缺少对应会话')
        if len(row['party']) != len(set(row['party'])) or any(k not in row['roles'] for k in row['party']):
            raise ValueError('副本队伍引用无效')
        if any(row['roles'][k]['state'] != 'joined' for k in row['party']):
            raise ValueError('副本同行状态冲突')
        if not isinstance(row['logs'],list) or len(row['logs'])>2000:raise ValueError('副本日志无效')
        for log in row['logs']:
            fields(log, {'id','step','kind','place','text','source','actors'}, {'fact_id','occurred_step','received_step','supersedes'})
            if log['kind'] not in {'实证','据说','听说'}:raise ValueError('副本证据等级无效')
        if 'expedition' in row:validate_expedition(row)
        if 'space' in row:validate_space(row)
        for node in row['nodes']:
            fields(node, {'id','kind','variant','text','risk','reward','actor','direction'}, {'mechanism'})
            if 'mechanism' in node and node['mechanism'] not in {'fractured','resonant','volatile','cache','trail','contact','conflict'}:
                raise ValueError('探索机制无效')
            if node['kind'] not in {'seal','trace','contact','conflict','hazard','cache','core'}:
                raise ValueError('副本节点类型无效')
            finite(node['risk'],0,1)
            if node['actor'] not in row['roles']:raise ValueError('节点人物引用无效')
        for reward in all_rewards(row):
            fields(reward,{'id','kind','name','realm','fused'}, {'book','item','items'})
            integer(reward['realm'],1,12)
            if reward['realm']!=row['realm'] or reward['kind'] not in {'technique','artifact','pill','resource','fixed'}:raise ValueError('奖励品阶或类型无效')
            if row['quality']=='legendary' and reward['realm']!=row['ceiling']:raise ValueError('传奇奖励不能受地图降阶')
            if reward['kind']=='technique':
                from .technique_effect_schema import validate_effect
                book=reward.get('book',{})
                if book.get('grade')!=reward['realm'] or book.get('level')!=1 or not book.get('id','').startswith(reward['id']+':'):
                    raise ValueError('传承原始配方无效')
                validate_effect(book.get('combat_effect'))
            elif reward['kind']=='fixed':
                items=reward.get('items')
                if not isinstance(items,list) or len(items)!=1:raise ValueError('封藏物品无效')
                fields(items[0],{'id','quantity'});integer(items[0]['quantity'],1,1)
                if not isinstance(items[0]['id'],str) or not items[0]['id']:raise ValueError('封藏物品缺少名录编号')
            elif reward['kind']=='resource':
                if not isinstance(reward.get('items'),list) or not 1<=len(reward['items'])<=3:raise ValueError('资源预算无效')
                for item in reward['items']:
                    fields(item,{'id','quantity'});integer(item['quantity'],1,1000)
                    if not isinstance(item['id'],str) or not (item['id'].startswith(('natal_', 'universal_manual_')) or item['id']=='immortal_trace'):
                        raise ValueError('资源定义无效')
            elif reward.get('item',{}).get('id')!=reward['id']:raise ValueError('遗物身份无效')
            if reward['kind'] in {'artifact','pill'}:
                for key in ('recovery_hp_limit','recovery_mp_limit'):
                    if reward['item'].get(key) is not None:finite(reward['item'][key],0,1e30)
        if len(row['claims']) != len(set(row['claims'])):raise ValueError('副本奖励回执重复')
        if set(row['claims'])-{r['id'] for r in all_rewards(row)}:raise ValueError('副本奖励回执无来源')
        if identity not in value['maps'].get(row['world']+':'+row['location_id'],[]):raise ValueError('副本缺少地图次数登记')
        if row['quality']=='legendary' and identity not in value['legends'].get(row['world'],[]):raise ValueError('传奇缺少生成次数登记')
    for scope, ids in value['maps'].items():
        if not isinstance(scope,str) or not isinstance(ids,list) or len(ids)!=len(set(ids)):
            raise ValueError('地图副本登记无效')
        if any(k not in value['instances'] or scope != value['instances'][k]['world']+':'+value['instances'][k]['location_id'] for k in ids):
            raise ValueError('地图副本引用无效')
    for world, ids in value['legends'].items():
        if world not in WORLD_IDS or len(ids)!=len(set(ids)) or any(k not in value['instances'] or
                value['instances'][k]['world']!=world or value['instances'][k]['quality']!='legendary' for k in ids):
            raise ValueError('传奇生成回执无效')
    active=value['active']
    if active is not None and (active not in value['instances'] or value['instances'][active]['status']!='active'):
        raise ValueError('副本会话引用无效')
    if any(r['status']=='active' and k!=active for k,r in value['instances'].items()):
        raise ValueError('存在多个活动副本')
    for mail in value['mail']:
        fields(mail, {'id','dungeon_id','sender','sender_id','title','body','unread','status','age'})
        if mail['dungeon_id'] not in value['instances'] or type(mail['unread']) is not bool:
            raise ValueError('副本信件引用无效')
    active_studies=0
    recipes={r['book']['id']:r['book'] for row in value['instances'].values() for r in all_rewards(row)
        if r['kind']=='technique' and r['id'] in row['claims']}
    for key,manual in value['manuals'].items():
        fields(manual,{'book','fused','acquired','learned','level','study'})
        if key not in recipes or manual['book']!=recipes[key] or manual['acquired'] is not True or type(manual['learned']) is not bool:
            raise ValueError('所得传承缺少原始领取凭据')
        integer(manual['level'],1,9)
        if manual['study']:
            active_studies+=1;job=manual['study']
            fields(job,{'required','elapsed','paid','level','world'})
            finite(job['required'],1);finite(job['elapsed'],0,job['required'])
            if job['level']!=manual['level'] or job['world'] not in WORLD_IDS or not manual['learned']:
                raise ValueError('传承参悟任务无效')
            fields(job['paid'],{'years','opportunity','traces'})
            for n in job['paid'].values():finite(n)
    if active_studies>1:raise ValueError('不能同时参悟多部传承')
    return copy.deepcopy(value)


def validate_space(site):
    space=site['space'];size=len(site['nodes'])
    fields(space,{'coords','positions','turn','visited','cleared','snares','spent','chase','echoes'}, {'wards'})
    integer(space['turn'],0,100000)
    coords=space['coords']
    if not isinstance(coords,list) or len(coords)!=size:raise ValueError('副本地图大小无效')
    for pair in coords:
        if not isinstance(pair,list) or len(pair)!=2:raise ValueError('副本节点坐标无效')
        for n in pair:integer(n,-32,32)
    if len(set(map(tuple,coords)))!=size:raise ValueError('副本节点坐标重复')
    if any(max(abs(x-y) for x,y in zip(a,b))!=1 for a,b in zip(coords,coords[1:])):raise ValueError('主路断开')
    for key in ('visited','cleared','spent','wards'):
        seq=space.get(key,[])
        if not isinstance(seq,list) or len(seq)>size:raise ValueError('副本足迹无效')
        for n in seq:integer(n,0,size-1)
        if len(set(seq))!=len(seq):raise ValueError('副本足迹重复')
    if not isinstance(space['positions'],dict) or set(space['positions'])-set(site['roles']):raise ValueError('副本人物位置无效')
    for pos in space['positions'].values():integer(pos,0,size-1)
    if not isinstance(space['snares'],dict) or any(k not in {str(i) for i in range(size)} or owner not in site['roles'] for k,owner in space['snares'].items()):raise ValueError('副本伏阵无效')
    facts={f['id'] for f in site.get('expedition',{}).get('facts',[])}
    if not isinstance(space['echoes'],dict) or set(space['echoes'])-facts:raise ValueError('副本战痕无效')
    for echo in space['echoes'].values():
        if not isinstance(echo,list) or len(echo)!=2:raise ValueError('副本战痕位置无效')
        point,turn=echo
        integer(point,0,size-1);integer(turn,0,space['turn'])
    if space['chase'] is not None:
        chase=space['chase'];fields(chase,{'hunters','round'})
        if site['status']!='active' or site['pending'] or not isinstance(chase['hunters'],list) or not chase['hunters'] or set(chase['hunters'])-set(space['positions']):raise ValueError('追逐人物无效')
        integer(chase['round'],0,space['turn'])


def all_rewards(site):
    return [n['reward'] for n in site['nodes']]+site.get('expedition',{}).get('bonuses',[])


def validate_observations(site,role):
    ledger=role['ledger'];metrics={'desire','preparation','trust','caution'}
    fields(ledger,(),{'domain_rank','representative','supporters','observed','evidence','treasure_evidence','conduct_step','outside_party','encounter_step'})
    if 'outside_party' in ledger and (type(ledger['outside_party']) is not bool or not role['existing']):raise ValueError('外界队友须引用原人物')
    if 'encounter_step' in ledger:integer(ledger['encounter_step'],0,len(site['nodes']))
    if 'conduct_step' in ledger:integer(ledger['conduct_step'],0,len(site['nodes']))
    if 'domain_rank' in ledger:integer(ledger['domain_rank'],0,13)
    if 'representative' in ledger and type(ledger['representative']) is not bool:raise ValueError('代表标记无效')
    supporters=ledger.get('supporters',[])
    if not isinstance(supporters,list) or len(supporters)>2 or len(supporters)!=len(set(supporters)) or role['id'] in supporters:
        raise ValueError('局部支持名单无效')
    if any(k not in site['roles'] for k in supporters):raise ValueError('局部支持人物引用无效')
    observed=ledger.get('observed',{})
    if not isinstance(observed,dict):raise ValueError('观察指标记录无效')
    for metric,value in observed.items():
        if metric not in metrics:raise ValueError('观察指标无效')
        finite(value,0,100)
    targets={n['reward']['id'] for n in site['nodes']}
    for field,allowed in (('evidence',metrics),('treasure_evidence',targets)):
        evidence=ledger.get(field,{})
        if not isinstance(evidence,dict) or set(evidence)-allowed:raise ValueError('观察来源无效')
        for row in evidence.values():
            fields(row,{'low','high','step','text'});finite(row['low'],0,100);finite(row['high'],row['low'],100)
            integer(row['step'],0,len(site['nodes']))
            if not isinstance(row['text'],str):raise ValueError('观察说明无效')


def validate_expedition(site):
    ex=site['expedition'];nodes={n['id']:i for i,n in enumerate(site['nodes'])}
    fields(ex,{'version','routes','route_choices','goals','contracts','bonuses','bonus_claims','facts','evidence','settlements','performance'})
    if ex['version']!=2:raise ValueError('不支持的副本分支结构')
    for key in ('routes','goals','contracts','evidence','performance'):
        if not isinstance(ex[key],dict):raise ValueError('副本分支映射无效')
    for key in ('route_choices','bonuses','bonus_claims','facts','settlements'):
        if not isinstance(ex[key],list) or len(ex[key])>100:raise ValueError('副本分支记录无效')
    if len(ex['bonuses'])!=2 or len(ex['facts'])>2:raise ValueError('副本额外预算无效')
    for key,route in ex['routes'].items():
        fields(route,{'destination','direction','cost'})
        if key not in nodes:raise ValueError('侧路来源无效')
        integer(route['destination'],nodes[key]+1,len(nodes)-1);finite(route['cost'],0,1)
    for choice in ex['route_choices']:
        fields(choice,{'node','destination'})
        if choice['node'] not in ex['routes'] or choice['destination']!=ex['routes'][choice['node']]['destination']:
            raise ValueError('侧路回执无来源')
    reward_ids={n['reward']['id'] for n in site['nodes']}
    if set(ex['goals'])-set(site['roles']):raise ValueError('目的人物引用无效')
    for goal in ex['goals'].values():
        fields(goal,{'target','desires','fulfilled','work','seen_power'})
        if goal['target'] not in reward_ids or set(goal['desires'])!=reward_ids or type(goal['fulfilled']) is not bool:
            raise ValueError('目标机缘无效')
        for n in goal['desires'].values():finite(n,0,100)
        integer(goal['work'],0,100);finite(goal['seen_power'])
    for key,contract in ex['contracts'].items():
        fields(contract,{'state','item_id','step'})
        if key not in site['roles'] or contract['state'] not in {'promised','fulfilled','broken'}:raise ValueError('交付约定无效')
        integer(contract['step'],0,len(nodes))
        if (contract['state']=='fulfilled')!=bool(contract['item_id']):raise ValueError('交付回执缺少原物品')
    if len(ex['bonus_claims'])!=len(set(ex['bonus_claims'])) or set(ex['bonus_claims'])-set(site['claims']):
        raise ValueError('报答回执不一致')
    if set(ex['bonus_claims'])-{r['id'] for r in ex['bonuses']}:raise ValueError('报答超出冻结预算')
    ids=set()
    for fact in ex['facts']:
        fields(fact,{'id','actors','direction','occurred','reported','verified','result','mistaken'}, {'treasure','winner','scope','rumor'})
        if 'rumor' in fact and (not isinstance(fact['rumor'],str) or not 1<=len(fact['rumor'])<=300):
            raise ValueError('副本远方风声格式无效')
        if fact['id'] in ids or len(fact['actors'])!=2 or set(fact['actors'])-set(site['roles']):raise ValueError('传闻关联无效')
        ids.add(fact['id'])
        if any(k in fact for k in ('treasure','winner','scope')):
            if not all(k in fact for k in ('treasure','winner','scope')):raise ValueError('争夺事实缺少归属')
            fields(fact['treasure'],{'id','name'})
            if fact['treasure']['id']!=fact['id']+':background' or not isinstance(fact['treasure']['name'],str):raise ValueError('背景宝物标识无效')
            if fact['winner'] not in fact['actors'] or fact['scope'] not in {'person','sect'}:raise ValueError('背景争夺归属无效')
        for k in ('occurred','reported','verified'):integer(fact[k],0,len(nodes))
        if not fact['occurred']<=fact['reported']<=fact['verified'] or type(fact['mistaken']) is not bool:raise ValueError('传闻时序无效')
    if set(ex['evidence'])-ids:raise ValueError('证据没有来源')
    for level in ex['evidence'].values():integer(level,1,3)
    fields(ex['performance'],{'wins','helped','escapes'})
    for n in ex['performance'].values():integer(n,0,100)
    if any(k not in site['roles'] for k in ex['settlements']) or len(set(ex['settlements']))!=len(ex['settlements']):raise ValueError('善后回执无效')

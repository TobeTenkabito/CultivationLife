"""Allowlisted evidence projection. Hidden motives and future nodes never leave here."""
import copy
from ...rules import combat_power, max_mp
from ...cultivation_coordinates import rank_for
from .generation import config
from .runtime import require_actor
from .people import power, opposition, team_reason

QUALITY_NAMES={'ordinary':'普通','rare':'稀有','epic':'史诗','legendary':'传奇'}
STATES={'contact':'请求同行','invited':'已发来邀请','joined':'同行中','left':'已离队',
    'missing':'失去联系','hostile':'已翻脸','dead':'已陨落','declined':'已谢绝','observed':'各自行动'}
REALMS=('凡人','练气','筑基','结丹','元婴','化神','炼虚','合体','大乘','真仙','金仙','太乙','大罗')


def public_logs(rows,site=None):
    """Remove obsolete commentary from old logs without editing saved evidence."""
    obsolete=('你无法确认其现状。','你无法确认其去向。','其所述来意尚不能证实。',
              '口头约定并不能保证对方守约。','先前关于胜负与死伤的说法仍无法实证。',
              '你并不知晓其全部打算。','眼前的破阵痕迹与早先传讯中的说法相互出入。')
    result=copy.deepcopy(rows)
    for row in result:
        for sentence in obsolete:
            row['text']=row['text'].replace(sentence,'')
        if site:
            subjects={}
            for key in row['actors']:
                role=site['roles'].get(key)
                if role:subjects['person:'+key]='修士 · '+role['name']
            fact=next((f for f in site.get('expedition',{}).get('facts',[]) if f['id']==row.get('fact_id')),None)
            keys=(fact['actors'] if fact and row['kind']!='听说' else row['actors'])
            for key in keys:
                role=site['roles'].get(key)
                if role and role['sect_id']:subjects['sect:'+role['sect_id']]='势力 · '+role['sect_name']
            row['subjects']=[dict(id=k,label=v) for k,v in subjects.items()]
    return result


def person(game,site,role):
    clues=role['clues']; seen=len(clues);observed=role['ledger'].get('observed',{})
    ratio=power(game,role)/max(1,combat_power(game.player))
    gap=rank_for(role['realm'],role['layer'])-rank_for(game.player.realm_index,game.player.layer)
    # Behaviour observations are deliberately not the solver's intention/desire.
    # A bar without sufficient evidence is unknown, never an exact hidden score.
    bars=[dict(label='境界差距',value=gap,min=min(-36,gap),max=max(36,gap),display=f'{gap:+d}阶',source='接触时所显修为'),
          dict(label='战力对照',value=round(ratio*100),min=0,max=max(200,round(ratio*100)),display=f'约为你的 {ratio:.1f} 倍',source='外显气息估计'),
          dict(label='夺宝意向',value=observed.get('desire'),min=0,max=100,
               display='待观察' if 'desire' not in observed else f"约 {observed['desire']} / 100",source='对遗物的关注表现'),
          dict(label='准备迹象',value=observed.get('preparation'),min=0,max=100,
               display='未探明' if 'preparation' not in observed else f"约 {observed['preparation']} / 100",source='沿途符记、探路与守望表现'),
          dict(label='合作表现',value=observed.get('trust'),min=0,max=100,
               display='未探明' if 'trust' not in observed else f"约 {observed['trust']} / 100",source='同行中的警戒交接与相互照应'),
          dict(label='履约记录',value=10 if role['id'] in site['agreements'] else 0,min=0,max=100,
               display='已有口头约定' if role['id'] in site['agreements'] else '尚未约定',source='双方当面约定的内容')]
    bars.insert(5,dict(label='戒备迹象',value=observed.get('caution'),min=0,max=100,
        display='未探明' if 'caution' not in observed else f"约 {observed['caution']} / 100",source='以可见警戒行为估计'))
    metrics={'夺宝意向':'desire','准备迹象':'preparation','合作表现':'trust','戒备迹象':'caution'}
    for bar in bars:
        evidence=role['ledger'].get('evidence',{}).get(metrics.get(bar['label']))
        if evidence:
            bar.update(low=evidence['low'],high=evidence['high'],observed_step=evidence['step'],
                display=f"{evidence['low']}–{evidence['high']} / 100",source=f"第 {evidence['step']} 处观察：{evidence['text']}")
    if site['step']<len(site['nodes']):
        node=site['nodes'][site['step']]
        bars[2]['label']='夺宝意向 · '+(node['reward']['name'] if node['id'] in site['branches'] else '眼前遗物')
        observed_target=role['ledger'].get('treasure_evidence',{}).get(node['reward']['id'])
        if not observed_target:
            bars[2].update(value=None,display='尚无针对此物的线索',source='留意其对此物的言语与举止')
            for key in ('low','high','observed_step'):bars[2].pop(key,None)
    treasure_bars=[]
    for node in site['nodes']:
        reward=node['reward'];e=role['ledger'].get('treasure_evidence',{}).get(reward['id'])
        if node['id'] not in site['branches'] and reward['id'] not in site['claims']:continue
        treasure_bars.append(dict(id=reward['id'],label='夺宝意向 · '+reward['name'],value=round((e['low']+e['high'])/2) if e else None,
            min=0,max=100,display=f"{e['low']}–{e['high']} / 100" if e else '尚无针对此物的线索',
            source=f"第 {e['step']} 处：{e['text']}" if e else '未观察到相关行为'))
    contract=site.get('expedition',{}).get('contracts',{}).get(role['id'])
    can_trade=bool(site.get('expedition') and role['id'] in site['party'] and not site['pending'])
    support=[r for r in opposition(game,site,role) if r['known']]
    from .encounters import can_slay
    return dict(id=role['id'],name=role['name'],sect=role['sect_name'],
        realm=REALMS[role['realm']]+f" {role['layer']} 层",status=STATES[role['state']],state=role['state'],
        story=role['story'],clues=copy.deepcopy(clues[-5:]),bars=bars,treasure_bars=treasure_bars,
        comparison=dict(rank=rank_for(role['realm'],role['layer']),power=round(power(game,role))),
        squad=dict(count=len(support),power=round(sum(power(game,r) for r in support)),
            rank=max((rank_for(r['realm'],r['layer']) for r in support),default=rank_for(role['realm'],role['layer']))) if len(support)>1 else None,
        representative=bool(role['ledger'].get('representative')),
        contract=copy.deepcopy(contract),can_trade=can_trade,can_slay=can_slay(game,site,role),
        can_deliver=can_trade and any(i.quantity>0 and 'dungeon_restorative' in i.tags for i in game.player.inventory),
        exposed=role['revealed'],can_pact=role['id'] in site['party'] and role['id'] not in site['agreements'] and not site['pending'])


def public(game,maps):
    state=game.dungeon_state;p=game.player;scope=p.world+':'+p.location_id
    profile=config()['profiles'].get(scope)
    reason=''
    try:require_actor(game)
    except ValueError as error:reason=str(error)
    ids=state.get('maps',{}).get(scope,[])
    active=state.get('instances',{}).get(state.get('active'))
    from ...rules import passive_inventory
    result=dict(active=bool(active),available=not reason,reason=reason,world=p.world,location_id=p.location_id,
        resonating_relic_id=next((i.id for i in passive_inventory(p) if 'dungeon_relic' in i.tags),None),
        used=len(ids),limit=profile['slots'] if profile else 0,ready_in=max(0,state.get('ready_age',0)-p.age),
        sites=[],session=None,mail=copy.deepcopy(state.get('mail',[])),
        unread=sum(m['unread'] for m in state.get('mail',[])),manuals=[],invitees=[],archives=[])
    result['archives']=[dict(id=s['id'],name=s['name'],logs=public_logs(s['logs'],s))
        for s in state.get('instances',{}).values() if s['entered'] and s['status']=='closed']
    if not active and not reason:
        from .people import candidates
        result['invitees']=[dict(id=n.id,name=n.name) for n in candidates(game)]
    for key in ids:
        site=state['instances'][key]
        # Quality is learned on entry. Discovery and invitations reveal no roster,
        # strength ceiling, conflict stage, seed or frozen reward table.
        result['sites'].append(dict(id=key,name=site['name'],revision=site['revision'],status=site['status'],
            quality=QUALITY_NAMES[site['quality']] if site['entered'] else '未探明',
            can_enter=site['status']=='open' and not active and not reason and result['ready_in']==0))
    for key,row in state.get('manuals',{}).items():
        from .study import quote
        from ...technique_description import generated
        from .rewards import learning_reason
        learn_reason=learning_reason(game,row)
        result['manuals'].append(dict(id=key,name=row['book']['name'],grade=REALMS[row['book']['grade']],
            level=row['level'],learned=row['learned'],fused=row['fused'],description=generated(row['book']),
            can_learn=not learn_reason and not active and not reason,learn_reason=learn_reason,
            study=copy.deepcopy(row['study']),quote=quote(game,row)))
    if active:
        if 'space' not in active:
            from .topography import restore_map
            active=copy.deepcopy(active);restore_map(active)
        site=active;pending=site['pending'];choices=[]
        if pending:
            kind=pending['kind']
            if kind=='join':choices=[('accept','接受同行'),('decline','谢绝同行')]
            elif kind=='conflict':choices=[('support_actor','援助'+site['roles'][pending['actor']]['name']),('support_other','援助'+site['roles'][pending['other']]['name']),('flee','趁乱脱身')]
            elif kind=='settlement':choices=[('part','分道离开'),('ask_join','提议继续同行')]
            else:choices=[('fight','迎战'),('flee','尝试脱身')]
        elif site['step']<len(site['nodes']):choices=[('survey','耗费法力勘察'),('seize','接近并争取机缘'),('bypass','绕开此处')]
        current=site['nodes'][site['step']] if site['step']<len(site['nodes']) else None
        route=site.get('expedition',{}).get('routes',{}).get(current['id']) if current else None
        from .scenes import TACTICS, tactic
        if not pending and current and current['id'] in site['branches']:
            for key in TACTICS:
                spec=tactic(current,key)
                if spec:choices.append((key,f'{spec[3]}（法力 {max_mp(p)*spec[1]:g}）'))
        if not pending and route and current['id'] in site['branches']:choices.append(('detour','沿'+route['direction']+'绕行'))
        space=site.get('space')
        if space:
            if space['chase'] or (not pending and site['step'] in space['cleared']):choices=[]
            if pending and pending.get('intercepted'):
                from .formations import local_field
                choices=[('fight','启阵迎敌' if pending.get('snared') and local_field(game) else '迎战追兵')]
        from .rewards import cache_clue
        result['session']=dict(id=site['id'],revision=site['revision'],name=site['name'],
            quality=QUALITY_NAMES[site['quality']],place=('入口','外围','深处','核心')[min(3,site['depth'])],
            text=site['last_result'] if pending or (space and space['chase']) or not current else current['text']+cache_clue(current),
            choices=[dict(id=k,label=v,enabled=not reason and not(k in {'accept','ask_join'} and
                (len(site['party'])>=config()['max_team']-1 or team_reason(game,site['roles'][pending['actor']])))
                and not(k=='survey' and current and current['id'] in site['branches'])
                and not(k in TACTICS and p.mp<max_mp(p)*TACTICS[k][1])) for k,v in choices],
            can_exit=not reason and not (space and space['chase']) and (not pending or pending['kind']=='join'),
            party_count=len(site['party'])+1,team_limit=config()['max_team'],
            people=[person(game,site,r) for r in site['roles'].values() if r['known'] and r['state']!='unseen'],
            logs=public_logs(site['logs'],site),acquired=len(site['claims']),
            preparation=min(100,site['preparations']*10),
            player_comparison=dict(rank=rank_for(p.realm_index,p.layer),power=round(combat_power(p))),
            hp=p.hp,mp=p.mp)
        if space:
            from .perception import view
            session=result['session'];session['map']=view(game,site)
            if space['chase']:session['text']='身后遁光紧逼，选择方位遁行。'
            elif not pending and site['step'] in space['cleared']:session['text']='你认出方才留下的足迹。可在这里布阵，或沿岔路继续探查。'
    return result

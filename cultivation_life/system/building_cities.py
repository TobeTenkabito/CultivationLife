"""City-specific zero-year activities with persistent, identity-bound reward caps."""
from ..building_schema import address
from ..building_rules import config, city_content, describe, ensure_state
from ..content_registry import REALMS, WORLD_SYSTEMS
from ..rules import expected_combat_power, max_hp, max_mp
from ..runtime import decode_rng, encode_rng
from ..models import HistoryRecord
from . import building_projects as projects


def option(identity,text,reason=''):
    return dict(id=identity,text=text,enabled=not reason,**({'disabled_reason':reason} if reason else {}))


def usage(game,row):
    return game.building_state.get('city_usage',{}).get(row['id'],{})


def record(game,row):
    return ensure_state(game).setdefault('city_usage',{}).setdefault(row['id'],{})


def rank(row):
    tier=WORLD_SYSTEMS['world_profiles'][row['address']['world']]['tier']
    return min(WORLD_SYSTEMS['world_profiles'][row['address']['world']]['npc_realm_cap'],
               {1:1,2:5,3:9}[tier]+row['level']-1)


def story(row):
    return city_content(row).get('story',dict(title='新城的第一张告示',
        body='新城的商户与住户都希望知道街道、仓栈和静室将如何分区。众人请你把最初的约定写清楚。',
        choices=[['分清公共道路与各户用地','新告示写清了边界与通行，搬来的人终于知道该如何与邻人相处。'],
                 ['召集住户共同核对街坊图','几处容易混淆的界线被重新标注。新城的秩序从可查的约定开始，而不是从谁先占住门口开始。']]))


def arena_reason(game,row):
    if usage(game,row).get('arena',0)>=config()['city_arena_attempts']:return '此城三次试场机会已经用尽，不因重建刷新'
    if game.player.realm_index==0:return '尚未入道，不能参加修士试法'
    if game.player.hp<max_hp(game.player)*.3 or game.player.mp<max_mp(game.player)*.25:return '请先离城调息，恢复气血与法力'
    return ''


def project(game,row,node):
    content=city_content(row)
    title=row['name']
    choices=[]
    if node=='main':
        body=describe(row)
        choices=[option('city:audience','拜访城府'),option('city:rumor','坊巷见闻'),
                 option('city:story',story(row)['title']),option('city:arena','参加演武')]
        if projects.owns(game,row):choices.extend([option('city:govern','办理城务'),option('city:develop','发展城池')])
        choices.append(option('management','勘看城防与营造'))
    elif node=='city:audience':
        title+=' · 城府'
        body=content.get('audience','新城值房的案上摊着街坊图与工料册，来往居民把问题逐条记下，等待你安排次序。')
        choices=[option('city:audience:listen','旁听议事'),option('back','返回城中')]
    elif node=='city:audience:listen':
        body=content.get('audience','你与值守人员逐项核对城内公共事务。')+'\n\n众人把分歧记入案卷，暂不作无凭的承诺。你离开值房时，案前已经让出位置给下一位来客。'
        choices=[option('city:audience','返回城府'),option('back','返回城中')]
    elif node=='city:rumor':
        title+=' · 坊巷'
        body=content.get('rumor','新铺正在挂起招牌，早到的住户彼此认路，街头谈论的多是明日的生计。')
        choices=[option('back','返回城中')]
    elif node=='city:story':
        tale=story(row);title+=' · '+tale['title'];body=tale['body']
        reason='此城逸事奖励已经领取；读档、重建和跨界均不重置' if usage(game,row).get('story') else ''
        body+='\n\n此番取舍只能获得一次感悟。'
        choices=[option(f'city:resolve:{i}',text,reason) for i,(text,_) in enumerate(tale['choices'])]
        choices.append(option('back','返回城中'))
    elif node.startswith('city:result:'):
        index=node.rsplit(':',1)[1]
        if index not in {'0','1'}:return None
        index=int(index);tale=story(row)
        title+=' · '+tale['title'];body=tale['choices'][index][1]+'\n\n这段经历已经留在你的阅历中，不能再次领取感悟。'
        choices=[option('back','返回城中')]
    elif node=='city:arena':
        attempts=usage(game,row).get('arena',0)
        body=content.get('arena','新城试场以点到为止，台下已经备好收束余波的护栏。')
        body+=f"\n\n对手按本城{REALMS[rank(row)].name}试法规格出阵。已用{attempts}/3次机会，首次胜出可获一次感悟。实际消耗气血、法力，不推进年份。"
        choices=[option('city:fight','登台试法',arena_reason(game,row)),option('back','返回城中')]
    elif node=='city:arena:result':
        body=game.building_state['scene'].get('result_text','试法已结束。')
        choices=[option('city:arena','返回试场'),option('back','返回城中')]
    elif node in {'city:govern','city:develop'}:
        purpose=node.split(':')[1];bill=projects.quote(game,purpose,row)
        target=config()['city_development'][row['level']-1] if row['level']<3 else 0
        body=(f"此城为{projects.USES[row['subtype']]}、{projects.POPULATIONS[row.get('population','mixed')]}，"
              f"现为{row['level']}级，治理进度{row.get('development',0)}/{target}。\n\n")
        body+=('每个真实年份可办理一次街坊、仓栈与公共设施的治理，完成后进度增加一。' if purpose=='govern' else '扩建只提升一级，需要完成本级治理并支付下一级全部工料。')
        body+='\n\n'+projects.bill_text(bill)
        choices=[option('city:commit:'+bill['token'],'确认办理' if purpose=='govern' else '确认扩建',bill['reason']),option('back','返回城中')]
    else:return None
    choices.append(option('leave','离开'+row['name']))
    return dict(title=title,body=body,choices=choices)


def construction(game,node):
    if node=='main':
        return dict(title='择地筑城',body='你在此地选定城址。新城从一级起步，先决定城池的用途。',
            choices=[option('city:'+kind,name) for kind,name in projects.USES.items()]+[option('leave','暂不筑城')])
    parts=node.split(':')
    if parts[0]!='city':return None
    if len(parts)==2:
        return dict(title='城中居民',body=f'新城采用{projects.USES[parts[1]]}布局。你准备如何安排居民街坊？',
            choices=[option(node+':'+kind,name) for kind,name in projects.POPULATIONS.items()]+[option('back','重新选择用途'),option('leave','暂不筑城')])
    if len(parts)!=3 or parts[1] not in projects.USES or parts[2] not in projects.POPULATIONS:return None
    bill=projects.quote(game,'city')
    return dict(title='一级新城营造',body=f"城名：{game.player.name[:30]}城；{projects.USES[parts[1]]}，{projects.POPULATIONS[parts[2]]}。\n\n"
        '只使用行囊中真实持有的本界材料，不自动购料。建成后须逐年治理，才能继续扩建。\n\n'+projects.bill_text(bill),
        choices=[option('city:build:'+bill['token'],'确认筑城',bill['reason']),option('city:'+parts[1],'返回居民选择'),option('leave','暂不筑城')])


def build(game,scene):
    _,kind,population=scene['node'].split(':')
    bill=projects.quote(game,'city');projects.pay(game,bill,'一级城市营造工料')
    place=address(game)
    from ..building_schema import address_key
    identity=f"city:player:{game.id}:{address_key(place)}"
    row=dict(id=identity,name=game.player.name[:30]+'城',type='city',subtype=kind,population=population,
        level=1,development=0,status='intact',address=place,owner=dict(kind='player',id=game.id),
        users=[],public=True,features=[])
    ensure_state(game)['records'][identity]=row
    game.history.append(HistoryRecord('SYS_CITY_FOUNDATION',1,game.player.age,'筑城',identity,'completed',
        f"在原地建成一级{row['name']}。",dict(cost=bill['coins'],materials=bill['materials']),['building','city']))
    scene.update(kind='visit',building_id=identity);scene.pop('project',None)


def act(deps,game,row,choice):
    if choice.startswith('city:resolve:'):
        if usage(game,row).get('story'):raise ValueError('此城逸事已经完成')
        index=int(choice.rsplit(':',1)[1])
        if index not in (0,1):raise ValueError('未知取舍')
        record(game,row)['story']=1
        amount=REALMS[rank(row)].opportunity_base*config()['city_story_opportunity_fraction']
        gained=deps.opportunity(game.player,amount)
        game.history.append(HistoryRecord('SYS_CITY_STORY',1,game.player.age,story(row)['title'],choice,'completed',
            story(row)['choices'][index][1],dict(city_id=row['id'],opportunity=gained),['building','city']))
        return 'city:result:'+str(index)
    if choice=='city:fight':
        reason=arena_reason(game,row)
        if reason:raise ValueError(reason)
        counter=record(game,row);counter['arena']=counter.get('arena',0)+1
        rng=decode_rng(game.seed,game.rng_state)
        target=dict(target_name=row['name']+'试场守擂者',target_power=expected_combat_power(rank(row),1),
            target_realm_index=rank(row),target_layer=1,combat_type='cultivator',action='spar',
            enemy_objective='repel',max_rounds=6,path='dao')
        result,text=deps.combat(game,target,False,rng)
        game.rng_state=encode_rng(rng)
        if result=='victory' and not counter.get('arena_reward'):
            counter['arena_reward']=1
            amount=REALMS[rank(row)].opportunity_base*config()['city_arena_opportunity_fraction']
            gained=deps.opportunity(game.player,amount)
            text+=f'\n\n本城首次胜出，机缘感悟实得{gained:.1f}，此后不再发放。'
        game.building_state['scene']['result_text']=text
        return 'city:arena:result'
    if choice.startswith('city:commit:'):
        purpose=game.building_state['scene']['node'].split(':')[1]
        bill=projects.quote(game,purpose,row)
        projects.pay(game,bill,'城市治理工料' if purpose=='govern' else '城市扩建工料')
        original=projects.persist(game,row)
        if purpose=='govern':
            original['development']=original.get('development',0)+1
            record(game,row)['govern_year']=game.player.age
        else:
            original.update(level=original['level']+1,development=0)
            if original.get('population')=='cultivator':original['features']=['defensive_array','restrictions']
        return 'main'
    return choice

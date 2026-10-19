"""Map-bound buildings and zero-year branching visits; original assets stay authoritative."""
import copy
from dataclasses import dataclass
from typing import Callable

from ..building_schema import TYPES, address, address_key
from ..building_rules import config, may_use, describe, display_name, qi_multiplier, ensure_state
from ..content_registry import WORLD_SYSTEMS
from ..models import HistoryRecord
from ..runtime import now_iso
from ..rules import remove_item
from .buddhist.rules import buddhist_config, buddhist_active
from .building_assets import rows_at, local_rows
from . import building_cities as cities, building_projects as projects, building_destruction as destruction
from . import building_visits as visits
from . import building_exploration as exploration


@dataclass(frozen=True)
class BuildingDependencies:
    load: Callable
    save: Callable
    present: Callable
    temple_action: Callable
    opportunity: Callable
    combat: Callable


def state(game):
    return ensure_state(game)


def is_event(event):
    return bool(event and str(event.get('id','')).startswith('SYS_BUILDING_'))


def require_available(game):
    p = game.player
    if not p.alive or p.imprisonment or p.ghost_captor or game.active_trial:
        raise ValueError('当前状态不能出入建筑')
    if p.world in {'lost','rift'} or game.guixu_state.get('player_session') or game.trial_site_state.get('active'):
        raise ValueError('当前不在可开辟建筑的普通地图')
    if game.map_journey:
        raise ValueError('请先结束当前远行')
    if game.buddhist_state.get('assembly'):
        raise ValueError('请先结束法会')


def find(game, identity):
    return next((row for row in local_rows(game) if row['id']==identity),None)


def scene_valid(game):
    scene = game.building_state.get('scene')
    if not scene or scene['address'] != address(game):
        return False
    try:
        require_available(game)
    except ValueError:
        return False
    row=find(game,scene.get('building_id')) if scene['kind']!='construction' else None
    return scene['kind']=='construction' or bool(row and (scene['kind']=='management' or may_use(row,'player',game.id)))


def _choice(identity,text,reason=''):
    return dict(id=identity,text=text,enabled=not reason,**({'disabled_reason':reason} if reason else {}))


def quote(game, level, quality):
    place = address(game)
    old = next((r for r in local_rows(game) if r.get('subtype')=='cave' and r['owner']==dict(kind='player',id=game.id)),None)
    if old and old['status']=='destroyed':return 0,'旧洞府已毁坏，请先原址重建'
    if old and (level<old['level'] or (old['quality']=='professional' and quality=='self')):
        return 0,'不能降低已有洞府的等级或品质'
    total = int(config()['cave_prices'][quality][level-1])*int(WORLD_SYSTEMS['world_profiles'][place['world']]['tier'])
    cost = total-int((old or {}).get('invested',0))
    if cost<=0:
        return 0,'已有洞府不低于此规格'
    funds = sum(i.quantity for i in game.player.inventory if i.id=='spirit_stone')
    return cost, '' if funds>=cost else f'需要{cost}灵石'


def management(game,row,node):
    title=display_name(row)+' · 勘看建筑'
    body=describe(row)
    if node=='main':
        body+='\n\n所有者：'+('你' if projects.owns(game,row) else '无主景观' if row['type']=='scenery' else '当地原产权所有者')+'。'
        if row['status']=='destroyed':
            bill=projects.quote(game,'rebuild',row)
            choices=[_choice('rebuild','勘验原址重建',bill['reason'] if '权限' in bill['reason'] else '')]
        else:
            body+=f"\n此处防御参照战力约{projects.defense(row):,.0f}。" if row['type']!='scenery' else ''
            choices=[_choice('destroy','拆除或强行摧毁',projects.demolition_reason(game,row))]
        if may_use(row,'player',game.id):choices.append(_choice('back','返回建筑'))
    elif node=='destroy':
        body+='\n\n确认后建筑立即停止使用，不返还工料、不补发物资、不结算人物死亡。城市保留原名遗址。'
        if not projects.owns(game,row):body+='强行破坏须达到城防战力，并消耗最大法力的四分之一。'
        token=projects.quote(game,'rebuild',row)['token']
        choices=[_choice('destroy:'+token,'确认摧毁',projects.demolition_reason(game,row)),_choice('back','返回勘看')]
    elif node=='rebuild':
        bill=projects.quote(game,'rebuild',row)
        body+='\n\n城市、寺庙从一级重建；洞府与产业修复原规格。活动次数、所有权和原实物账目均保留。\n\n'+projects.bill_text(bill)
        choices=[_choice('rebuild:'+bill['token'],'确认重建',bill['reason']),_choice('back','返回勘看')]
    else:return None
    choices.append(_choice('leave','离开此地'))
    return dict(title=title,body=body,choices=choices)


def event(game):
    if not scene_valid(game):
        return None
    scene = game.building_state['scene']
    node = scene['node']
    projected=None
    if scene['kind']=='construction' and scene.get('project')=='city':projected=cities.construction(game,node)
    elif scene['kind']=='management':projected=management(game,find(game,scene['building_id']),node)
    elif scene['kind']=='visit' and find(game,scene['building_id'])['type']=='city':
        projected=cities.project(game,find(game,scene['building_id']),node)
    elif scene['kind']=='visit':
        projected=visits.project(game,find(game,scene['building_id']),node)
    if projected is not None:
        return dict(id=f"SYS_BUILDING_{scene['revision']}",**projected)
    choices = []
    if scene['kind']=='construction':
        title,body='开辟洞府','你在此地勘看山势，准备开辟一处固定洞府。请选择规模。'
        if scene.get('project')=='temple':
            if not buddhist_active(game):return None
            existing=next((r for r in local_rows(game) if r.get('subtype')=='temple'),None)
            if existing:return None
            price=int(buddhist_config()['temples'][1]['cost'])*buddhist_config()['temple_tier_scale']**(int(WORLD_SYSTEMS['world_profiles'][game.player.world]['tier'])-1)
            funds=sum(i.quantity for i in game.player.inventory if i.id=='spirit_stone')
            title,body='修建寺庙',f'你准备在此地修建一座清修小庵，供信众礼佛。需支付{price}灵石。'
            choices=[_choice('confirm','确认修建','灵石不足' if funds<price else '')]
        elif node=='main':
            choices=[_choice(f'level:{n}',f'{n}级洞府') for n in (1,2,3)]
        elif node.startswith('level:'):
            level=int(node.split(':')[1]);body=f'你选择了{level}级洞府，准备如何开辟？'
            for quality,label in [('self','自行开辟'),('professional','委托营造匠师')]:
                price,reason=quote(game,level,quality)
                bonus=config()['cave_bonus'][quality][level-1]
                choices.append(_choice(f'plan:{level}:{quality}',f'{label} · {price}灵石 · 气收益+{bonus:.0%}',reason))
            choices.append(_choice('back','重新选择规模'))
        elif node.startswith('plan:'):
            _,raw,quality=node.split(':');level=int(raw);price,reason=quote(game,level,quality)
            body=f"开辟{level}级洞府，{'自行布置' if quality=='self' else '委托本地营造匠师'}，需支付{price}灵石。确认后洞府固定在此地。"
            choices=[_choice('confirm','确认开辟',reason),_choice(f'level:{level}','返回选择开辟方式')]
        else:
            return None
        choices.append(_choice('leave','暂不修建'))
    else:
        row=find(game,scene['building_id']);title=display_name(row)
        body=describe(row)
        if node=='main':
            choices=visits.choices(row)+[_choice('details','察看此处')]
            if row.get('subtype')=='cave':
                choices += [_choice('qi','察看聚气布置'),_choice('renovate','整修洞府')]
            elif row.get('subtype')=='temple' and buddhist_active(game):
                choices += [_choice('temple','主持寺院'),_choice('blessings','察看加持')]
            if row['type']!='scenery':choices.append(_choice('management','勘看建筑与重建'))
        elif node=='details':
            body += '\n\n' + ('这处产业的经营情况与原产业账目一致。' if row['type']=='industry' else '此处的产权与使用许可独立登记，离开后仍留在原地。')
            choices=[_choice('back','返回')]
        elif node=='qi' and row.get('subtype')=='cave':
            bonus=config()['cave_bonus'][row['quality']][row['level']-1]
            body += f'\n\n此处聚气使本地图原有气收益提高{bonus:.0%}，不增加气种，不与其他洞府叠加。修炼仍须离开建筑，按原年份结算。'
            choices=[_choice('back','返回洞府')]
        elif node=='temple' and row.get('subtype')=='temple' and buddhist_active(game):
            level=row['level'];cfg=buddhist_config()
            price=(int(cfg['temples'][level+1]['cost'])*cfg['temple_tier_scale']**(int(WORLD_SYSTEMS['world_profiles'][game.player.world]['tier'])-1)) if level<3 else 0
            funds=sum(i.quantity for i in game.player.inventory if i.id=='spirit_stone')
            body += f"\n\n信众与业德沿用原佛门网络。{'寺院已达三级。' if level==3 else f'扩建下一级需要{price}灵石。'}"
            choices=[_choice('temple:upgrade','扩建寺院','寺院已达三级' if level==3 else '灵石不足' if funds<price else ''),_choice('back','返回寺院')]
        elif node=='blessings' and row.get('subtype')=='temple' and buddhist_active(game):
            selected=game.buddhist_state.get('worlds',{}).get(game.player.world,{}).get('blessings',[])
            body+='\n\n请择一项加持查看。'
            choices=[_choice('blessing:'+key,spec['name']+(' · 已启用' if key in selected else '')) for key,spec in buddhist_config()['blessings'].items()]
            choices.append(_choice('back','返回寺院'))
        elif node.startswith('blessing:') and row.get('subtype')=='temple' and buddhist_active(game):
            key=node.split(':',1)[1];spec=buddhist_config()['blessings'].get(key)
            if not spec:return None
            selected=game.buddhist_state['worlds'][game.player.world]['blessings']
            enabled=key in selected;blocked='' if enabled or (game.buddhist_state.get('dharma_karma',0)>0 and len(selected)<3) else '须正业力且最多三项加持'
            body+=f"\n\n{spec['name']}：每年基础业德消耗{spec['upkeep']}，实际供养沿原信众规模结算。"
            choices=[_choice('toggle:'+key,'停用此加持' if enabled else '启用此加持',blocked),_choice('blessings','返回加持名录')]
        else:return None
        choices.append(_choice('leave','离开'+title))
    return dict(id=f"SYS_BUILDING_{scene['revision']}",title=title,body=body+'\n\n你决定：',choices=choices)


def prepare(game):
    """Reconcile only this session; the caller preserves earned followups."""
    projected=event(game)
    if game.building_state.get('scene') and projected is None:
        game.building_state.pop('scene',None)
    return projected


def navigate(game, scene, node):
    s=state(game);s['sequence']+=1
    scene.update(node=node,revision=s['sequence'])
    s['scene']=scene
    game.pending_event=event(game)
    if game.pending_event is None:
        raise ValueError('建筑事件已失效')


def temple_change(deps, game, scene, command, payload, next_node):
    following=game.pending_event.get('_followup_event')
    previous=game.pending_event
    game.pending_event=None
    try:
        deps.temple_action(game,command,payload)
        if scene.get('project')=='temple':
            scene.update(kind='visit',building_id=f'temple:{game.player.world}:{game.player.location_id}')
            scene.pop('project',None)
        navigate(game,scene,next_node)
        if following:game.pending_event['_followup_event']=following
    except Exception:
        game.pending_event=previous
        raise


def _construct(game, scene):
    _,raw,quality=scene['node'].split(':');level=int(raw)
    price,reason=quote(game,level,quality)
    if reason:raise ValueError(reason)
    place=address(game)
    old=next((r for r in local_rows(game) if r.get('subtype')=='cave' and r['owner']==dict(kind='player',id=game.id)),None)
    identity=old['id'] if old else f'cave:{game.id}:{address_key(place)}'
    if not remove_item(game.player,'spirit_stone',price):raise ValueError('灵石不足')
    from .economy.local_market import operator_account
    from .economy.ledger import record_external
    record_external(game,'player',operator_account(game,place['world'],place['location_id']),price,
                    '洞府营造委托' if quality=='professional' else '洞府开辟资材')
    row=dict(id=identity,type='artificiality',subtype='cave',name=(old or {}).get('name','清修洞府'),
        level=level,quality=quality,status='intact',address=place,owner=dict(kind='player',id=game.id),
        users=copy.deepcopy((old or {}).get('users',[])),public=False,invested=int((old or {}).get('invested',0))+price)
    state(game)['records'][identity]=row
    state(game)['cultivation'][address_key(place)]=identity
    game.history.append(HistoryRecord('SYS_BUILDING_CONSTRUCTION',1,game.player.age,'开辟洞府',None,'completed',
        f"在原地完成{level}级洞府，实付{price}灵石。",dict(building_id=identity,cost=price),['building']))
    scene.update(kind='visit',building_id=identity)
    navigate(game,scene,'main')


def action(deps: BuildingDependencies, game_id, action, building_id='', event_id=None, choice_id=''):
    game=deps.load(game_id)
    require_available(game)
    if action in {'enter','construct','temple-plan','city-plan','manage'}:
        if game.pending_event or game.building_state.get('scene'):
            raise ValueError('请先处理当前事件或离开建筑')
        if action in {'enter','manage'}:
            row=find(game,building_id)
            if not row:raise ValueError('建筑不在当前位置或依赖未开启')
            if action=='enter' and not may_use(row,'player',game.id):raise ValueError('没有使用权，请先联系所有者')
            scene=dict(kind='visit' if action=='enter' else 'management',building_id=row['id'],address=address(game))
            if action=='enter' and row.get('subtype')=='cave':state(game)['cultivation'][address_key(address(game))]=row['id']
        else:
            scene=dict(kind='construction',address=address(game))
            if action=='temple-plan':
                if not buddhist_active(game) or any(r.get('subtype')=='temple' for r in local_rows(game)):
                    raise ValueError('当前不能新建寺庙')
                scene['project']='temple'
            elif action=='city-plan':scene['project']='city'
        navigate(game,scene,'main')
    elif action=='choose':
        projected=event(game)
        if not projected or not is_event(game.pending_event) or event_id != projected['id'] or event_id != game.pending_event['id']:
            raise ValueError('建筑事件已经变化，请重新查看')
        offered=next((c for c in projected['choices'] if c['id']==choice_id),None)
        if not offered or not offered['enabled']:raise ValueError((offered or {}).get('disabled_reason','此处没有提供该选项'))
        scene=state(game)['scene']
        if choice_id=='leave':
            game.building_state.pop('scene',None)
            game.pending_event=game.pending_event.get('_followup_event')
        elif choice_id=='confirm' and scene['kind']=='construction':
            if scene.get('project')=='temple':
                temple_change(deps,game,scene,'temple',{},'main')
            else:
                following=game.pending_event.get('_followup_event')
                _construct(game,scene)
                if following:game.pending_event['_followup_event']=following
        elif choice_id=='renovate':
            following=game.pending_event.get('_followup_event')
            scene['kind']='construction';navigate(game,scene,'main')
            if following:game.pending_event['_followup_event']=following
        elif choice_id=='management' or scene['kind']=='management':
            following=game.pending_event.get('_followup_event')
            row=find(game,scene['building_id'])
            node=choice_id
            if choice_id.startswith('destroy:'):
                destruction.destroy(game,row);node='main'
            elif choice_id.startswith('rebuild:'):
                destruction.rebuild(game,row,deps.temple_action);node='main'
            elif choice_id=='back':
                if scene['node']=='main':scene['kind']='visit'
                node='main'
            elif choice_id=='management':scene['kind']='management';node='main'
            navigate(game,scene,node)
            if following:game.pending_event['_followup_event']=following
        elif choice_id.startswith('city:build:'):
            following=game.pending_event.get('_followup_event')
            cities.build(game,scene);navigate(game,scene,'main')
            if following:game.pending_event['_followup_event']=following
        elif scene['kind']=='visit' and find(game,scene['building_id'])['type']=='city':
            following=game.pending_event.get('_followup_event')
            node=cities.act(deps,game,find(game,scene['building_id']),choice_id)
            navigate(game,scene,'main' if node=='back' else node)
            if following:game.pending_event['_followup_event']=following
        elif choice_id.startswith(('visit:','explore:')):
            following=game.pending_event.get('_followup_event')
            row=find(game,scene['building_id'])
            node=exploration.act(game,row,choice_id) if choice_id.startswith('explore:') else visits.act(deps,game,row,choice_id)
            navigate(game,scene,node)
            if following:game.pending_event['_followup_event']=following
        elif choice_id=='temple:upgrade' or choice_id.startswith('toggle:'):
            temple_change(deps,game,scene,'temple' if choice_id=='temple:upgrade' else 'blessing',
                          {} if choice_id=='temple:upgrade' else dict(blessing=choice_id.split(':',1)[1]),
                          'temple' if choice_id=='temple:upgrade' else 'blessings')
        else:
            following=game.pending_event.get('_followup_event')
            navigate(game,scene,'main' if choice_id=='back' else choice_id)
            if following:game.pending_event['_followup_event']=following
    else:raise ValueError('未知建筑操作')
    game.updated_at=now_iso();deps.save(game)
    return deps.present(game)


def public(game):
    reason=''
    try:require_available(game)
    except ValueError as error:reason=str(error)
    rows=[]
    for row in local_rows(game):
        rows.append(dict(id=row['id'],name=display_name(row),type=row['type'],subtype=row.get('subtype'),level=row['level'],
            status=row['status'],owner=copy.deepcopy(row['owner']),can_enter=may_use(row,'player',game.id) and not reason,
            description=describe(row),dependency=row.get('dependency')))
    return dict(types=list(TYPES),rows=rows,can_construct=not reason and not game.pending_event,
        can_build_city=not reason and not game.pending_event,
        can_establish_temple=not reason and not game.pending_event and buddhist_active(game) and not any(r.get('subtype')=='temple' for r in rows),
        blocked_reason=reason,inside=bool(game.building_state.get('scene')),qi_multiplier=qi_multiplier(game.player))


def attach_overview(game, map_data):
    """Current-world read projection, never a simulated player relocation."""
    current = address(game)
    for place in map_data.get('locations', []):
        target = dict(world=map_data['world'], instance_id=None, location_id=place['id'])
        place['buildings'] = [dict(id=row['id'], name=display_name(row), type=row['type'],
            subtype=row.get('subtype'), level=row['level'], status=row['status'], description=describe(row),
            population=row.get('population'), population_name=projects.POPULATIONS.get(row.get('population')),
            use_name=projects.USES.get(row.get('subtype')), owned=projects.owns(game,row),
            can_enter=target == current and may_use(row, 'player', game.id),
            access=may_use(row, 'player', game.id)) for row in rows_at(game, target)]

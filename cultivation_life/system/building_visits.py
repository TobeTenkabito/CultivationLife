"""Local narrative visits; rewards never manufacture stock, people or time."""
from ..definition_data import definition as _content_definition
from ..building_rules import config, describe, ensure_state
from ..content_registry import REALMS, WORLD_SYSTEMS
from ..models import HistoryRecord
from .economy.enterprise_rules import capacity
from .economy.enterprise_state import require_local
from . import building_exploration as exploration
from . import soul_secret_stories as secret_stories




SCENERY = _content_definition(__name__, "SCENERY")

WORK = _content_definition(__name__, "WORK")

TEMPLE = _content_definition(__name__, "TEMPLE")


def category(row):
    if row['type'] == 'scenery': return 'scenery'
    if row['type'] == 'industry': return 'industry'
    if row.get('subtype') == 'temple': return 'temple'
    return None


def option(identity, text, reason=''):
    return dict(id=identity, text=text, enabled=not reason, **({'disabled_reason':reason} if reason else {}))


def choices(row):
    kind = category(row)
    labels = {'scenery': [('trail','循迹探幽'),('weather','静观天候'),('traces','寻访旧迹')],
        'industry': [('work','走访'+row['name']),('ledger','查点经营实况'),('lesson','请教经营心得')],
        'temple': [('bell','听钟问禅'),('pilgrims','香客见闻'),('lesson','一盏灯的问答')]}
    actions=[option('visit:'+key, label) for key,label in labels.get(kind, [])]
    if kind=='scenery' and exploration.content(row):
        actions.insert(0,option('explore:main',exploration.content(row)['title']))
    return secret_stories.choices(row) + actions


def tale(row, activity):
    kind = category(row)
    if kind == 'scenery': return SCENERY.get(activity)
    if kind == 'temple': return TEMPLE.get(activity)
    if kind == 'industry' and activity == 'work': return WORK.get(row['subtype'])
    if kind == 'industry' and activity == 'lesson':
        return ('簿册以外的功夫', f"离开{row['name']}的作业处，管事问起你方才见到的细节。许多事情在簿上只占一行，真正做起来却不能省略。",
            [('请教哪一步最不可省', '管事把方才见到的工序重新串起，指出最容易因赶工忽略的地方。你记下这些具体的分寸，不再把结果当成理所当然。'),
             ('询问如何传给后来人', '你与管事讨论怎样留下可核对的记录，以及哪些地方仍须亲眼察看。这份经验成了后来人可以接续的功夫。')])
    return None


def claimed(game, row):
    return game.building_state.get('visit_usage', {}).get(row['id'], {}).get('insight') == 1


def project(game, row, node):
    if node.startswith('secret:'):return secret_stories.project(game,row,node)
    if node.startswith('explore:'):return exploration.project(game,row,node)
    if not node.startswith('visit:') or not category(row): return None
    parts = node.split(':')
    result = len(parts) == 5 and parts[1:3] == ['result','resolve']
    if result:
        activity, raw = parts[3:]
        if raw not in {'0','1'}: return None
    elif len(parts) == 2:
        activity = parts[1]
    else: return None
    if row['type'] == 'industry':
        original = require_local(game, row['source_id'])
        if activity == 'ledger' and not result:
            job = original['job']
            status = (f"在制批次预计于{job['finish']}岁年末完工。" if job else '当前没有在制批次。')
            body = (f"你在{row['name']}的簿房核对原账。仓中实物共{sum(original['stock'].values())}份，"
                f"仓储容量{capacity(original)}份。{status}本次查账没有提货、注资或改变生产安排。")
            return dict(title=row['name']+' · 经营实况',body=body,
                choices=[option('back','返回产业'),option('leave','离开'+row['name'])])
    entry = tale(row, activity)
    if not entry: return None
    title, body, branches = entry
    if result:
        body = branches[int(raw)][1]
        if activity == 'lesson': body += '\n\n此处的这番领悟已记入阅历，不会再次获得机缘。'
        actions = [option('back','返回'+row['name'])]
    else:
        reason = '此处心得已经领悟，原址重建也不重置' if activity == 'lesson' and claimed(game,row) else ''
        if activity == 'lesson': body += '\n\n这番心得只能领悟一次。'
        actions = [option(f'visit:resolve:{activity}:{i}',text,reason) for i,(text,_) in enumerate(branches)]
        actions.append(option('back','返回'+row['name']))
    actions.append(option('leave','离开'+row['name']))
    return dict(title=row['name']+' · '+title,body=describe(row)+'\n\n'+body,choices=actions)


def act(deps, game, row, choice):
    if choice.startswith('secret:'):return secret_stories.act(game,row,choice)
    if not choice.startswith('visit:resolve:'): return choice
    _,_,activity,raw = choice.split(':')
    entry = tale(row, activity)
    if not entry or raw not in {'0','1'}: raise ValueError('此处没有该探索分支')
    if row['type'] == 'industry': require_local(game, row['source_id'])
    if activity == 'lesson':
        if claimed(game,row): raise ValueError('此处心得已经领悟')
        ensure_state(game).setdefault('visit_usage',{}).setdefault(row['id'],{})['insight'] = 1
        tier = WORLD_SYSTEMS['world_profiles'][row['address']['world']]['tier']
        rank = min(WORLD_SYSTEMS['world_profiles'][row['address']['world']]['npc_realm_cap'], {1:1,2:5,3:9}[tier])
        gained = deps.opportunity(game.player, REALMS[rank].opportunity_base * config()['visit_insight_opportunity_fraction'])
        game.history.append(HistoryRecord('SYS_BUILDING_INSIGHT',1,game.player.age,entry[0],choice,'completed',
            entry[2][int(raw)][1],dict(building_id=row['id'],opportunity=gained),['building','visit']))
    return 'visit:result:resolve:'+activity+':'+raw

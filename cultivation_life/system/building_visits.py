"""Local narrative visits; rewards never manufacture stock, people or time."""
from ..building_rules import config, describe, ensure_state
from ..content_registry import REALMS, WORLD_SYSTEMS
from ..models import HistoryRecord
from .economy.enterprise_rules import capacity
from .economy.enterprise_state import require_local
from . import building_exploration as exploration
from . import soul_secret_stories as secret_stories


SCENERY = {
    'trail': ('循迹探幽', '一条不显眼的小径绕过眼前景物，旧足迹到转折处便淡了。远处另有较平缓的去路。',
        [('沿小径慢行', '你沿旧足迹走出小径。回头一看，来路藏在坡后，方才立足的地方只露出一角。'),
         ('在开阔处远眺', '你在开阔处站定，顺着来路望去。远处几段高低错落的坡脊，此刻才看分明。')]),
    'weather': ('静观天候', '风向变了，云影从脚边慢慢移开。方才还在暗处的一角，转眼已沐着天光。',
        [('停步听风', '你收住脚步，任远近的声响渐渐分明。风过之后，四周又恢复原来的安静。'),
         ('记下光影变化', '你把眼前的明暗、纹理和远近记在心里。等到转身离开，景色已与来时略有不同。')]),
    'traces': ('寻访旧迹', '景物间留着一处经年磨损的刻痕，字迹多已模糊。附近还有后来访客留下的浅浅标记。',
        [('辨认旧刻', '你侧身借光，勉强认出一个“归”字。下半行剥落得厉害，指腹摸过去，石面已平。'),
         ('只观其形，不动旧物', '你顺着刻痕看去，起笔处凿得深，收笔处已叫风磨平。临走时，你拂去了字缝里的浮土。')]),
}

WORK = {
    'farm': ('药畦里的分寸', '药畦边两种长势各不相同：一处枝叶繁茂，一处根茎更为紧实。管事说，栽培最难的是按时节分清轻重。',
        [('沿畦辨认生长差异', '管事拨开两株药草根边的土。叶色浅的那株反倒根须饱满，你蹲下来，又细看了一遍。'),
         ('听管事讲留种的取舍', '管事把麻绳系在几株壮苗上：“这几株留种，到采药那天也让它们站着。”')]),
    'mine': ('矿道前的木尺', '支架边放着一柄旧木尺。两道矿纹相交处看似富集，承力的岩层却更薄，现场的标记刻意绕开了它。',
        [('核对支架与岩纹', '你循着木尺留下的记号辨认受力处，明白多开一尺未必多得一分，稳住旧道才有下一次开采。'),
         ('询问为何保留薄层', '管事把可采与不可采的界线指给你看。木尺末端抵着一道细缝：“再往里凿，头顶这层就撑不住了。”')]),
    'hunt': ('猎场的界标', '林地边的界标分出巡护与狩猎区域。管事正在核对足迹，几处幼兽活动的地方被另作了记号。',
        [('辨认足迹与巡护标记', '大蹄印旁跟着几行小印。你放轻脚步，在界标处折了回来。'),
         ('听取停猎区域的缘由', '管事指给你看界标背面的幼蹄记号。待这一窝长成，巡山的人才会把标记刮去。')]),
    'alchemy': ('丹坊的火候簿', '案上一本旧簿写满不同批次的火候。两次看似相近的投料，记录的温度与收火时刻却不相同。',
        [('对照两次收火记录', '两炉用的都是同一味药，后一批根茎细，收火也早了些。你把那两行批注又看了一遍。'),
         ('请管事解释废丹记录', '那一页沾着烟灰。管事指着“再添一炷香”几个字道：“多的就是这一炷香，开炉时全焦了。”')]),
    'forge': ('器坊的淬火声', '锻台旁两块试样留着不同的断口。管事将断口迎着光，指给你看淬火后留下的细纹。',
        [('察看试样断口', '你循着纹理比较韧脆，听出锻声与材料之间的细小差别。你刚把试样放回台边，隔壁的锤声又响了。'),
         ('听管事解释返工缘由', '管事说起一次不能勉强交付的器胚。你记住了先认材性、再谈成器的道理。')]),
    'shop': ('货栈里的两张签', '同样的货名挂着两张签，一张记入库，一张记交割。账房拈起一张签：“这批只约好了日子，库里还没有。”',
        [('对照货签的去向', '你顺着货签核对入库、留存与交付的次序。入库那一栏还空着，等脚夫把货抬进门，才轮到掌柜落笔。'),
         ('听账房讲一次错签', '账房翻出一张旧签。货号错了一笔，正字就写在旁边，下面还有当日经手人的小印。')]),
}

TEMPLE = {
    'bell': ('钟声出檐', '檐下的钟声才歇，廊间仍有回响。值堂人把木槌归位，等最后一声余韵消散才开口。',
        [('听钟至静', '你等到余音不再，才发现院内的脚步与风声从未停过。值堂人微微颔首，没有再添一句解释。'),
         ('问钟声为何留有间隔', '值堂人说，声与声之间也要容人听见。你与他静坐片刻，随后让出廊下的位置。')]),
    'pilgrims': ('香客的旧愿', '两位香客一人想求来日顺遂，一人只想把旧事说完。知客搬来两只蒲团，请他们坐下慢慢说。',
        [('听知客接引来人', '后一位香客几次开口，又低下头去。知客给他续了茶，坐在一旁，直到他把那桩旧事说完。'),
         ('留出安静的席位', '你移开挡路的蒲团，让后来的人也能入座。一位老人扶着你的手坐下，把沾了泥的鞋小心拢到蒲团边。')]),
    'lesson': ('一盏灯的问答', '一盏旧灯需要添油，另一盏刚被点亮。值堂人问你：若只记得灯火好看，却从不问油从何来，可算明白这座寺院？',
        [('先问供养，再谈明灯', '你问灯油是谁添的。值堂人指了指门外：“卖油的施主送来半瓮，小沙弥每晚提着它走一圈。”'),
         ('从两盏灯的不同处作答', '你指给他看，旧灯的火苗已舔到灯芯根上。值堂人将油壶递给你，你接过来，把那盏灯添满。')]),
}


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

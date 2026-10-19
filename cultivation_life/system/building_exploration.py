"""Authored, two-stage landscape tales; the first ending fixes the unique find."""
from ..building_rules import config, ensure_state
from ..content_registry import ITEM_CATALOG
from ..models import HistoryRecord
from ..rules import add_item


def content(row):
    return next((s.get('exploration') for s in config()['scenery'].get(row['address']['world'],[])
        if s['id']==row.get('content_id')),None)


def option(identity,text):
    return dict(id=identity,text=text,enabled=True)


def project(game,row,node):
    tale=content(row)
    if not tale or not node.startswith('explore:'):return None
    parts=node.split(':');body='';choices=[]
    seen=game.building_state.get('landscape_usage',{}).get(row['id'])
    if node=='explore:main':
        body=tale['body']
        if seen:body+='\n\n这段往事已经留在阅历中。重访可以重看其他取舍，不会改写初次结局或再得遗物。'
        choices=[option('explore:route:'+str(i),t) for i,t in enumerate(tale['actions'])]
    elif len(parts)==3 and parts[1]=='route' and parts[2] in {'0','1'}:
        body=tale['discoveries'][int(parts[2])]
        choices=[option('explore:finish:'+parts[2]+':'+str(i),t) for i,t in enumerate(tale['finals'])]
    elif len(parts)==4 and parts[1]=='result' and parts[2] in {'0','1'} and parts[3] in {'0','1'}:
        body=tale['endings'][int(parts[3])]
        if tale.get('relic_id') and parts[3]=='1':
            body+='\n\n'+ITEM_CATALOG[tale['relic_id']].name+'只会在首次结局选择带走时取得一次；重访不补发。'
        choices=[option('explore:main','再听这段往事')]
    else:return None
    choices.extend([option('back','返回'+row['name']),option('leave','离开'+row['name'])])
    return dict(title=row['name']+' · '+tale['title'],body=body,choices=choices)


def act(game,row,choice):
    if not choice.startswith('explore:finish:'):return choice
    _,_,route,ending=choice.split(':')
    tale=content(row)
    if not tale or route not in {'0','1'} or ending not in {'0','1'}:raise ValueError('未知景色结局')
    used=ensure_state(game).setdefault('landscape_usage',{})
    if row['id'] not in used:
        relic=tale.get('relic_id') if ending=='1' else None
        if relic:add_item(game.player,relic,1)
        used[row['id']]=dict(ending=route+':'+ending)
        game.history.append(HistoryRecord('SYS_LANDSCAPE_STORY',1,game.player.age,tale['title'],choice,'completed',
            tale['endings'][int(ending)],dict(building_id=row['id'],relic_id=relic),['building','landscape']))
    return 'explore:result:'+route+':'+ending

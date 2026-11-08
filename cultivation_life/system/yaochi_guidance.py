"""A real local teacher occupies one ten-year service, with no trace bonus."""
from ..content_registry import ACTIONS
from ..relationship_records import find_person
from ..rules import opportunity_multiplier
from .yaochi_rules import commission_reward
from .yaochi_antiquity import companion_reason,people
from .westward_rules import project

def teacher_reason(game,n,order=None):
    if blocked:=companion_reason(game,n,dict(id='guidance:'+order['id']) if order else None):return blocked
    if n.path!='dao' or (n.realm_index,n.layer)<=(game.player.realm_index,game.player.layer):return '讲师须为修为高于本人的原道修人物'
    return ''

def quote(game,blocked):
    candidates=[n for n in people(game) if not teacher_reason(game,n)]
    n=min(candidates,key=lambda n:(n.realm_index,n.layer,n.id)) if candidates else None
    fee=commission_reward(game.player,dict(reward=400))
    expected=sum(ACTIONS['cultivate']['opportunity'])/2*opportunity_multiplier(game.player)*100
    return dict(id='guidance',kind='guidance',name='清修讲席',mark='讲',years=10,price=fee,materials={},
        teacher=n.id if n else None,teacher_name=n.name if n else '当前没有合资格在场讲师',
        realm=game.player.realm_index,layer=game.player.layer,
        reason=blocked or ('' if n else '须有当面、自由、空闲且修为更高的原道修讲师'),
        description='本人接受十年指导，按每年实际有效功法效率结算机缘；不附送普通仙痕判定。',
        benefit=f'当前约 {expected:,.1f} 机缘',comparison='不刷新师门次数、香火额度或原专修进度；讲师与本人同时占用')

def target_reason(game,row):
    if row.get('kind')!='guidance':return ''
    if (game.player.realm_index,game.player.layer)!=(row['realm'],row['layer']):return '本人境层已变化，请结清原讲席后重新预约'
    if row['progress']>=row['years']:return ''
    return teacher_reason(game,find_person(game,row['teacher']),row)

def active(game):return bool(project(game) and project(game)['kind']=='guidance')

def annual_gain(game):
    return sum(ACTIONS['cultivate']['opportunity'])/2*opportunity_multiplier(game.player)*10

def record_gain(game,gain):
    row=project(game)
    if row and row['kind']=='guidance':row['opportunity_delivered']=row.get('opportunity_delivered',0)+gain

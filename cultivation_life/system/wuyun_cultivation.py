"""Paid five-aggregate actions and presentation, separate from combat projection."""
from ..content_registry import CONTENT_DOCUMENTS
from .wuyun import enabled_for,definitions,profile


def training_reason(game):
    from .cultivation_guard import cultivation_blocked
    p=game.player
    if not enabled_for(p) or p.world!='asura' or p.realm_index<9:return '须开启修罗道途并在修罗界达到修罗境'
    if cultivation_blocked(game):return '请先处理当前事件、劫战或拘束'
    if p.sealed_cultivation or p.cultivation_suppression:return '修为受压制，不能锻炼魔躯或修炼五蕴'
    if game.map_journey:return '请先完成当前旅行'
    if game.guixu_state.get('player_session'):return '请先离开归墟'
    runtime=game.heavens_state.get('runtime')
    if runtime:
        from .heavens.state import active_task
        if active_task(runtime):return '请先结束诸天亲自任务'
    if p.asura_cultivation.get('conversion',0)<5:return '须先完成五重煞元转化'
    return ''


def quote(row,rank):
    base=CONTENT_DOCUMENTS['doctrines.json']['cultivation']['vein_opportunity_base']
    return dict(souls=row['cost']['souls']*(rank+1),
                opportunity=base*row['cost']['opportunity_multiplier']*(rank+1))


def public(game):
    p=game.player;owned={r.id:r for r in profile(p,player=True)};reason=training_reason(game);rows=[]
    for row in definitions():
        mechanism=owned.get(row['id']);rank=mechanism.level if mechanism else 0
        bill=quote(row,rank) if rank<10 else {}
        blocked='魔躯尚未达到解锁层数' if mechanism is None else reason
        if not blocked and rank>=10:blocked='已修炼至十重'
        if not blocked and (p.asura_cultivation.get('souls',0)<bill.get('souls',0) or p.opportunity<bill.get('opportunity',0)):
            blocked='精魂或机缘不足'
        rows.append(dict(id=row['id'],name=row['name'],unlock_level=row['unlock_level'],unlocked=mechanism is not None,
                         level=rank,max_level=10,cost=bill,can_train=not blocked,reason=blocked,
                         probability=mechanism.chance if mechanism else row['chance']['base'],
                         effects=dict(mechanism.effects) if mechanism else {}))
    return rows


def train(game,key,expected_level):
    reason=training_reason(game)
    if reason:raise ValueError(reason)
    row=next((r for r in definitions() if r['id']==key),None)
    owned={r.id:r for r in profile(game.player,player=True)}
    if row is None or key not in owned:raise ValueError('此蕴尚未解锁')
    rank=owned[key].level
    if type(expected_level) is not int or expected_level!=rank:raise ValueError('五蕴修炼等级已变化，请刷新后再修炼')
    if rank>=10:raise ValueError('此蕴已达十重上限')
    bill=quote(row,rank);p=game.player;s=p.asura_cultivation
    if s.get('souls',0)<bill['souls'] or p.opportunity<bill['opportunity']:raise ValueError('修炼五蕴的精魂或机缘不足')
    s['souls']-=bill['souls'];p.opportunity-=bill['opportunity']
    s.setdefault('aggregates',{})[key]=rank+1
    return f"{row['name']}修炼至{rank+1}重，实付{bill['souls']}精魂、{bill['opportunity']:g}机缘。"

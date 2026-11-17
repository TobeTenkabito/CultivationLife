"""Paid, time-bearing growth for acquired complete manuals; no menu-time gains."""
from ...content_registry import WORLD_SYSTEMS
from ...rules import can_player_practice_technique
from ...models import HistoryRecord


def active(game):
    return next(((key,row) for key,row in game.dungeon_state.get('manuals',{}).items() if row.get('study')), (None,None))


def quote(game,row):
    grade=row['book']['grade'];level=row['level']
    return dict(years=int(WORLD_SYSTEMS['time_units'][str(grade)])*(level+1),
        opportunity=50*grade*(level+1),traces=20*(level+1) if grade>=9 and row['book']['path']=='dao' else 0)


def permitted(game,row):
    p=game.player
    book=next((b for b in p.known_techniques if b.id==row['book']['id']),None)
    if not row['learned'] or not book or row['level']>=9:raise ValueError('须先学会此传承，且尚未达到九级')
    if p.sealed_cultivation or p.cultivation_suppression or p.realm_index<book.grade or not can_player_practice_technique(p,book):
        raise ValueError('当前修为或道途不满足参悟要求')
    if book.grade>=9 and p.path=='dao' and not p.immortal_power_converted:raise ValueError('仙灵力尚未转化')


def start(game,key):
    if active(game)[0]:raise ValueError('已有传承正在参悟，请先完成')
    row=game.dungeon_state.get('manuals',{}).get(key)
    if not row:raise ValueError('未取得此传承')
    permitted(game,row);bill=quote(game,row);p=game.player
    if p.opportunity<bill['opportunity'] or p.immortal_traces<bill['traces']:raise ValueError('参悟所需机缘或仙痕不足')
    p.opportunity-=bill['opportunity'];p.immortal_traces-=bill['traces']
    row['study']=dict(required=bill['years'],elapsed=0,paid=bill,level=row['level'],world=p.world)


def begin(game):
    key,row=active(game)
    if not row:raise ValueError('请先选择所得传承并支付参悟代价')
    permitted(game,row)
    if row['study']['world']!=game.player.world:raise ValueError('请返回开始参悟的界面继续')
    return row['study']['required']-row['study']['elapsed']


def finish(game,elapsed):
    key,row=active(game)
    if not row:return
    job=row['study'];job['elapsed']=min(job['required'],job['elapsed']+max(0,elapsed))
    if job['elapsed']<job['required'] or not game.player.alive:return
    try:permitted(game,row)
    except ValueError:return  # Time already passed; preserve paid work until eligible again.
    row['level']+=1;row['study']=None
    from ...technique_evolution import evolve as evolve_technique
    p=game.player
    for book in [*p.known_techniques,p.technique,p.support_technique,p.body_technique,p.divine_sense_technique,p.transformation_technique,*p.combat_techniques]:
        if book and book.id==key:book.level=row['level'];evolve_technique(book)
    game.history.append(HistoryRecord(key,1,p.age,'参悟副本传承','dungeon_study','completed',
        f"《{row['book']['name']}》参悟至 Lv{row['level']}；道域修习与道祖称号另依自身造诣取得。",{},['dungeon','technique']))

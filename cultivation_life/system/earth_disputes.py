"""Local case lifecycle, one personal promise, fixed windows and real-year execution."""
import copy
from ..earth_dispute_content import CASES
from .earth_temple_rules import state, temple, local_reason, reason, occupied_reason
from .earth_temple_facilities import fingerprint
from .earth_dispute_facts import sources, stale_reason
from .earth_dispute_effects import options, quote, settle


def current(game, identity=None):
    book=state(game,identity).get('cases',{})
    return book.get('reports',{}).get(book.get('active'))


def access(game, case=None, recovery=False):
    blocked=local_reason(game,recovery=True)
    if blocked: return blocked
    if recovery: return ''
    if blocked:=reason(game): return blocked
    # Repairing a ruined host follows the existing original-site rebuild right.
    if case and case['kind']=='rebuild': return ''
    return local_reason(game)


def work_reason(game):
    case=current(game)
    if not case: return '没有本人正在办理的地方争议'
    if blocked:=access(game,case): return blocked
    if game.player.age>=case['until']: return '本期履约期限已过，请撤回并登记结果'
    return ''


def begin_work(game):
    if blocked:=work_reason(game): raise ValueError(blocked)
    case=current(game)
    if case['stage'] not in {'investigate','execute'} or case['progress']>=case['years']:
        raise ValueError('本段工时已足，请核对证据、选择方案或复核交付')
    return min(case['years']-case['progress'],case['until']-game.player.age)


def close(game,case,outcome):
    case['stage']='closed'; case['outcome']=outcome; case['closed_at']=game.player.age
    book=state(game)['cases']; book.pop('active',None)
    book.setdefault('history',[]).append(dict(name=CASES[case['kind']]['name'],year=game.player.age,outcome=outcome))
    del book['history'][:-12]
    return outcome


def command(game,maps,action,target):
    s=state(game); book=s.get('cases',{}); case=current(game)
    if action=='earth_case_report':
        if blocked:=local_reason(game,recovery=True) or reason(game) or occupied_reason(game): raise ValueError(blocked)
        window=game.player.age//500
        if book.get('window')!=window:
            book=s['cases']=dict(window=window,reports={},history=book.get('history',[]))
        added=0
        for kind,source in sources(game,maps).items():
            if kind in book['reports'] or access(game,dict(kind=kind)): continue
            report=dict(source,id=fingerprint([temple(game)['id'],window,kind]),kind=kind,stage='reported',
                        registered=game.player.age,until=(window+1)*500)
            if kind=='road': report['delay']=5
            book['reports'][kind]=report; added+=1
        if not added: raise ValueError('本期没有新的可登记来报；已拒绝或结案的同类事项不会重开')
        return f'登记{added}项本地来报。本期截止世界历{(window+1)*500}年，尚未许诺，不自动承担责任。道路塌方从登记时生效。'
    if action in {'earth_case_accept','earth_case_decline'}:
        report=next((r for r in book.get('reports',{}).values() if r['id']==target),None)
        if not report or report['stage']!='reported': raise ValueError('来报已经变化，请重新选择')
        if blocked:=access(game,report,recovery=action=='earth_case_decline'): raise ValueError(blocked)
        if occupied_reason(game): raise ValueError(occupied_reason(game))
        if action=='earth_case_decline': return close(game,report,'未许诺前婉拒；不扣信任，不改变原对象及道路事实。')
        if game.player.age>=report['until']: raise ValueError('本期来报已过期，请重新登记新一期')
        if blocked:=stale_reason(game,report): raise ValueError(blocked)
        report.update(stage='investigate',progress=0,years=5,started=game.player.age)
        book['active']=report['kind']
        return '开始本地调查与协商，须实际办理5年；尚未选择执行方案，不扣物资。'
    if not case: raise ValueError('没有正在办理的地方争议')
    if blocked:=access(game,case,recovery=action=='earth_case_cancel'): raise ValueError(blocked)
    if action=='earth_case_cancel':
        vanished=bool(stale_reason(game,case))
        loss=5 if case.get('plan') and not vanished else 0
        s['trust']=max(0,s['trust']-loss)
        return close(game,case,f"{'原事由或权限变化，撤回失效事项' if vanished else '撤回地方争议'}；信任-{loss}，已耗年份不返还，未交付物资不扣。")
    if game.player.age>=case['until']: raise ValueError('本期履约期限已过，请撤回并登记结果')
    if action=='earth_case_prepare':
        if case['stage']!='investigate' or case['progress']<5: raise ValueError('须完成5年实际调查')
        if blocked:=stale_reason(game,case): raise ValueError(blocked)
        case['stage']='decide'
        return '原对象与权限已经核验。请比较实际成本、执行年份与地方后果，选定后才构成承诺。'
    if action not in {'earth_case_plan','earth_case_resolve'}: raise ValueError('未知争议操作')
    parts=target.split(':')
    if len(parts)!=2: raise ValueError('请重新取得当前方案报价')
    plan=quote(game,case,parts[0])
    if parts[1]!=plan['token']: raise ValueError('原对象或方案报价已经变化，请刷新后重试')
    if plan['reason']: raise ValueError(plan['reason'])
    if action=='earth_case_plan':
        if case['stage']!='decide': raise ValueError('须完成调查并核对证据后才能许诺')
        if game.player.age+plan['years']>=case['until']: raise ValueError('本期剩余时间不足以完成所选方案')
        case.update(stage='execute',plan=plan['id'],progress=0,years=plan['years'])
        return f"许诺采用{plan['name']}，须本人实际执行{plan['years']}年。工料不预扣，复核时按实时原报价确认交付；撤诺通常损失5信任。"
    if case['stage']!='execute' or case['progress']<case['years'] or case['plan']!=plan['id']:
        raise ValueError('原方案实际工时尚未完成，不可提前或换案交付')
    receipt=settle(game,case,plan)
    change=plan['trust']; s['trust']=max(0,min(100,s['trust']+change))
    case['receipt']=dict(option=plan['name'],bill=copy.deepcopy(plan['bill']),extra=copy.deepcopy(plan['extra']),trust=change)
    return close(game,case,f"{plan['name']}已复核：{receipt} 本庙信任{change:+}。不另发助修额度、功德或功勋，旧香火期限保持。")


def public(game,maps):
    s=state(game); book=s.get('cases',{}); active=current(game)
    readable=not local_reason(game,recovery=True)
    rows=[]
    for kind,spec in CASES.items():
        case=book.get('reports',{}).get(kind)
        entry=dict(id=kind,**spec,case=None)
        if case:
            entry['case']=copy.deepcopy(case)
            entry['reason']=access(game,case) or ('本期来报已过期' if game.player.age>=case['until'] else '') or (stale_reason(game,case) if readable and case['stage']=='reported' else '')
        rows.append(entry)
    detail=copy.deepcopy(active)
    if detail:
        detail.update(name=CASES[detail['kind']]['name'],reason=work_reason(game),
                      cancel_reason=access(game,detail,recovery=True),stale=stale_reason(game,detail) if readable else '')
        detail['options']=options(game,detail) if readable and detail['stage'] in {'decide','execute'} else []
    return dict(window=game.player.age//500,until=(game.player.age//500+1)*500,rows=rows,active=detail,
                history=copy.deepcopy(book.get('history',[])),
                report_reason=local_reason(game,recovery=True) or reason(game) or occupied_reason(game),
                occupied=occupied_reason(game),local=readable)

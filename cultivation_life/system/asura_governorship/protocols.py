"""One original affairs selector for expanded Asura casework and military charters."""
import copy
from . import rules,court_affairs,charters,settlement
from .. import institution_deliberation as council,institution_arrays as arrays
from ...content_registry import CONTENT_DOCUMENTS
from ...relationship_records import find_person

COURT={'pressure','pressure_decide','patronage','divert','audit_open','investigate','defend','judge','restitute','case_cancel'}
CHARTER={'charter','central_enlist','central_pay','relief','relief_send','relief_finish','relief_cancel','move_request','move_complete','guard_bind','guard_repair'}
SETTLEMENT={'ally','ally_march','ally_break','negotiate','integrate'}
CLEANUP={'restitute','case_cancel','ally_break','relief_cancel','defend'}


def command(game,maps,row,p):
    op=p.get('operation')
    if not isinstance(op,str) or any(p.get(k) is not None and not isinstance(p[k],str) for k in ('case','target','choice','person','destination')):raise ValueError('府署议政字段无效')
    if (not rules.enabled() or not rules.config().get('completion')) and op not in CLEANUP:raise ValueError('专属扩展停用，仅可交接原责任')
    if not (rules.king(game) or 'player' in (row['holder'],row['controller'],row['nominee']) or any(c['actor']=='player' or c['subject']=='player' for c in council.book(row)['cases'])):raise ValueError('没有本府议政或原案当事人权限')
    if op in COURT:return court_affairs.command(game,row,op,p)
    if op in CHARTER:return charters.command(game,maps,row,op,p)
    if op in SETTLEMENT:return settlement.command(game,maps,row,op,p)
    raise ValueError('未知府署议政事务')


def public(game,row):
    mine='player' in (row['holder'],row['controller'],row['nominee']) or any('player' in (c['actor'],c['subject']) for c in council.book(row)['cases'])
    if not mine and not rules.king(game):return None
    cfg=rules.config().get('completion',{})
    state=copy.deepcopy(council.book(row));local=rules.local(game,row)
    def name(identity):
        if identity=='player':return game.player.name
        person=find_person(game,identity) if identity else None
        return person.name if person else '原当事人'
    for case in state['cases']+state['history']:
        case['subject_name']=name(case['subject'])
        case['participant_names']=[name(i) for i in case['participants']]
        case['reviewer_name']=name(case['reviewer']) if case['reviewer'] else None
    if state['rotation']:
        state['rotation']['outgoing_name']=name(state['rotation']['outgoing'])
        state['rotation']['incoming_name']=name(state['rotation']['incoming'])
    if state['relocation']:
        state['relocation']['city_name']=next((c['name'] for c in rules.cities(game) if c['id']==state['relocation']['city']),'原许可新址')
    cleanup={'restitute':'监察追责 · 实际退赔','case_cancel':'联合议政 · 撤回原案','ally_break':'地方盟约 · 解约退还担保','relief_cancel':'轮调接防 · 召回接防人','defend':'监察追责 · 当事人申辩'}
    state['operations']=cfg['operations'] if rules.enabled() and cfg else cleanup
    capital=game.player.location_id==court_affairs.CAPITAL
    central=rules.king(game) and capital
    allowed=set()
    if mine and local:
        allowed|={'pressure','patronage','divert','investigate','defend','restitute','guard_bind','guard_repair','ally_march'}
        if state['mandate']['appointments']=='local':allowed|={'relief','relief_send','relief_finish','relief_cancel'}
    if mine:allowed|={'ally','ally_break','case_cancel','move_complete','negotiate'}
    if mine and capital:allowed|={'move_request','pressure_decide','judge','patronage'}
    if central:allowed|={'charter','central_enlist','central_pay','audit_open','pressure_decide','judge','relief','relief_send','relief_finish','relief_cancel'}
    if rules.king(game) and local:allowed|={'investigate','integrate','negotiate'}
    state['operations']={k:v for k,v in state['operations'].items() if k in allowed}
    from .military import candidates
    state['people']=candidates(game,row) if local or rules.king(game) else []
    if local or capital:
        from ..institution_ai.rules import person_reason
        from ..asura_court_finance import people
        known={p['id'] for p in state['people']}
        state['people'] += [dict(id=n.id,name=n.name) for n in people(game).values() if n.id not in known and not person_reason(game,n.id,'asura',game.player.location_id)]
        if local:
            for case in state['cases']:
                reviewer=case['reviewer']
                if reviewer and reviewer not in {n['id'] for n in state['people']} and not person_reason(game,reviewer,'asura',row['location'],assignment=case['id']):
                    state['people'].append(dict(id=reviewer,name=name(reviewer)))
    state['arrays']=[dict(id=a['id'],name=a['name']) for a in arrays.candidates(game,row)] if local else []
    state['supplies']=[dict(id=d['id'],name=d['name']) for d in CONTENT_DOCUMENTS.get('formations.json',{}).get('maintenance_resources',[]) if d['world']=='asura' and game.player.formation_repair_supplies.get(d['id'],0)>0] if local else []
    state['units']=[dict(id=u['person_id'],name=name(u['person_id'])) for u in row.get('garrison',{}).get('units',[]) if u['phase'] not in {'home','lost'}]
    state['offices']=[dict(id=r['id'],name=r['name']) for r in rules.offices(game) if r is not row]
    state['cities']=[dict(id=c['id'],name=c['name']) for c in rules.cities(game) if c['id']!=row['city_id'] and rules.legal_city(game,c)]
    state['recognized']=charters.recognized(game,row)
    state['defence']=arrays.defence(game,row) if local else None
    return state


def advance(game,maps,row):
    if game.player.age<row['appointed'] or any(h['year']>game.player.age for h in row['history']):return
    court_affairs.advance(game,row);settlement.advance(game,maps,row)

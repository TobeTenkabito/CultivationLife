"""One personal schedule and the original fractional action-unit clock."""
from .westward_rules import record


def occupied(game):
    return bool(record(game).get('purple_east',{}).get('work') or record(game).get('antiquity',{}).get('active') or
                game.heavenly_court.get('projects',{}).get('work'))


def other_work(game):
    s=record(game);b=game.heavenly_court.get('bureaus',{});earth=s.get('earth',{})
    ledgers=[earth,*earth.get('branches',{}).values()]
    return bool(s.get('project') or game.yaochi_state.get('job') or b.get('review')
        or any(j['status']=='active' and j['person']=='player' for j in b.get('jobs',[]))
        or any(c['status']=='active' for c in b.get('inquiries',[]))
        or any(e['status']=='active' for e in s.get('fair',{}).get('entries',[]))
        or any(l.get('duty') or l.get('works') or l.get('cases',{}).get('active') for l in ledgers))


def finish_clock(game, elapsed, unit):
    s=game.yaochi_state.setdefault('westward',{})
    count,s['settlement_years']=divmod(s.get('settlement_years',0)+elapsed,unit)
    return count

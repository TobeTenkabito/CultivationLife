"""Registered civic obstruction costs only ordinary personal map travel, never teleport."""
from .earth_temple_rules import ledgers
from .westward_rules import enabled


def delay(game,route):
    if not enabled() or game.player.world!='celestial': return 0
    edges={frozenset((a,b)) for a,b in zip(route,route[1:])}
    found={}
    for ledger in ledgers(game):
        case=ledger.get('cases',{}).get('reports',{}).get('road')
        if case and game.player.age<case['until'] and frozenset(case['edge']) in edges:
            edge=frozenset(case['edge']); found[edge]=max(found.get(edge,0),case.get('delay',0))
    return sum(found.values())


def project(game,view):
    for row in view.get('locations',[]):
        extra=delay(game,row.get('route_ids',[]))
        if extra and row.get('travel_status')=='ok':
            row['travel_years']+=extra
            row['warning']=(row.get('warning','')+f' 地方道路受损，本次普通远行额外{extra}年。').strip()
    return view

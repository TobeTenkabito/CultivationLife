"""Read-only primary identity from authoritative appointment/temple records."""
from .westward_rules import record

def temple_ledgers(game):
    s=record(game).get('earth',{})
    return [s,*s.get('branches',{}).values()] if s.get('temple_id') else []

def offices(game):
    c=game.heavenly_court
    return [key for key,row in c.get('offices',{}).items() if row and row.get('holder_id')=='player'
            and row.get('end_unit',c.get('unit',0)+1)>c.get('unit',0)]

def official(game):
    return bool(game.heavenly_court.get('bureaus',{}).get('office') or offices(game))

def primary(game):
    if official(game):return 'xuan'
    if any(s.get('active') for s in temple_ledgers(game)):return 'earth'
    return 'free'

def public_service(game,building):
    """A public duty is allowed without faith while fulfilling a voted protocol."""
    r=game.heavenly_court.get('projects',{}).get('current') or {}
    return bool(building and building.get('public') and r.get('status')=='approved'
                and r.get('offer',{}).get('policy')=='service' and r['offer']['target']==building['id'])

def join_reason(game):
    return '须先在主庙交接地仙主持；入编期间不使用香火助修' if any(s.get('active') for s in temple_ledgers(game)) else ''


"""Bounded, read-only round-end presentation of the player's frozen manuals.

No eligibility evaluation: a sufficient balance does not promise a future cast.
The scheduler remains the only authority for preparation, payment and effects.
"""
import json

from ...combat_costs import technique_cost


def player_loadout(dispatch):
    state = dispatch.battle.units.get('player')
    if state is None:
        return None  # Background NPC battles do not acquire player UI payloads.
    result = []
    for book in state.unit.capabilities.technique_effects[:7]:
        runtime = dispatch.catalog if book['effect']['version'] == 3 else dispatch
        key = json.dumps(['player', book['id']], ensure_ascii=False, separators=(',', ':'))
        record = runtime.records[key]
        effect = book['effect']
        if runtime is dispatch:
            resource, capacity, balance = 'energy', runtime.capacities['player'], state.current
            pending = any(p['remaining'] > 0 and p['expires'] >= runtime.round for p in record['packets'])
        else:
            resource, _, balance = runtime.pool('player', book)
            capacity = runtime.capacities[key]
            pending = any(p['share'] > 1e-12 and p['expires'] >= runtime.round for p in record['packets'])
        cost = technique_cost(book, capacity)
        terms = book.get('cost_model')
        pricing = ('fixed' if terms['grade'] < terms['realm'] else
                   'proportional' if terms['grade'] == terms['realm'] else 'mixed') if terms else 'recorded'
        result.append(dict(id=book['id'], name=book['name'], level=book['level'],
            resource=resource, cost=cost, pricing=pricing, used=record['used'], limit=effect['uses'],
            cooldown=max(0, record['last_cast'] + effect['cooldown'] + 1 - runtime.round) if record['used'] else 0,
            pending=pending, prepared=bool(record.get('opportunity')), affordable=balance + 1e-12 >= cost,
            paid=record['paid'], refunded=record['refunded']))
    return result


def presentation(dispatch, report):
    """Enrich copied event rows; never expose an opponent's unplayed loadout."""
    books = {**dispatch.books, **(dispatch.catalog.books if dispatch.catalog else {})}
    for event in report['events']:
        key = json.dumps([event['owner'], event['technique']], ensure_ascii=False, separators=(',', ':'))
        item = books.get(key)
        if item:
            owner, book = item
            event['name'] = book['name']
            if event['event'] in {'paid', 'refunded'}:
                event['resource'] = (dispatch.catalog.pool(owner, book)[0]
                                     if book['effect']['version'] == 3 else 'energy')
            elif event['event'] in {'absorbed', 'restored', 'guard'} or (
                    event['event'] in {'strike', 'breach'} and book['effect']['version'] == 3):
                event['measure'] = 'unit_state_ratio'
    loadout = player_loadout(dispatch)
    if loadout is not None:
        report['player_loadout'] = loadout
    return report

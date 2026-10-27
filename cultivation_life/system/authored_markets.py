"""Only inherited books enter existing fairs; all original location/cost guards remain."""
import hashlib
from .authored_techniques import local_books, market_offers, template
from .npc_techniques import learn, levels
from ..rules import can_practice_technique


def permitted(game, row):
    return row.get('kind')=='authored_technique' and row.get('content_id') in local_books(game)


def append_fair(game, candidates):
    state=game.auction_state
    offers=[r for r in market_offers(game,'fair-') if not state.get('rank_band') or r['tier'] in state['rank_band']]
    if not offers:return
    # Fixed selection for this actual fair; reopening the UI never rerolls stock.
    start=game.auction_sequence%len(offers)
    selected=(offers[start:]+offers[:start])[:2]
    for row in selected:
        price=row['price']
        state['lots'].append(dict(row,id=state['id']+'-'+row['id'],start_price=price,current_bid=price,
            rated_price=price,maximum_bid=price*5,current_bidder='npc',current_bidder_name='传承行商',seller='npc',closed=False))
    persons={n.id:n for n in candidates}
    for i,attendee in enumerate(state['attendees']):
        row=dict(offers[(start+i)%len(offers)],id='private-'+attendee['id']+'-'+offers[(start+i)%len(offers)]['content_id'])
        attendee['trade_offers'].append(row)
        npc=persons.get(attendee['id']);book=template(game,row['content_id'])
        # The merchant's actual newly instantiated offering establishes knowledge;
        # reuse existing levels if the same person offers it at a later fair.
        if npc and npc.realm_index>=book.grade and can_practice_technique(npc.spirit_root,book):
            known=levels(npc)
            level=known.get(book.id,1+hashlib.sha256(f'{game.seed}:{npc.id}:{book.id}'.encode()).digest()[0]%9)
            slot=book.authored_buffs[0]['slot'] if book.authored_buffs else 'main'
            learn(npc,book,level,slot)

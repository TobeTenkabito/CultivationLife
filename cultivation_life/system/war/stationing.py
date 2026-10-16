"""Small elapsed-year encampment services, distinct from actual battle baskets."""
from ..economy.ledger import balance, transfer_value
from .logistics import entities
from .supply import return_items


def advance(game):
    for war in game.wars:
        if (war.get('strategic_war_id') and war.get('status')=='ended'
                and war.get('campaign_phase')=='home' and war.get('logistics',{}).get('refunded')):
            # Returned goods can outlive both a full depot and parent history.
            # Retry only the original, completed physical delivery; no cash refund.
            cargo=list(war.get('cargo_journeys',{}).values())+[r['cargo'] for r in war.get('reinforcements',[])]
            if game.player.age>war.get('end_age',game.player.age) and cargo and all(c['phase']=='home' for c in cargo):
                for side,row in war['logistics']['sides'].items():
                    if row.get('return_location')==row.get('location') and row.get('return_location') and any(n>0 for n in row['items'].values()):
                        return_items(game,war,side,entities(game,war,side))
            continue
        if (not war.get('logistics') or (war.get('status')!='active' and not (
                war.get('strategic_war_id') and war.get('status') in {'peace_ready','withdrawing'}))):
            continue
        for side,row in war['logistics']['sides'].items():
            previous=row.get('stationing_year',game.player.age)
            years=max(0,game.player.age-previous)
            row['stationing_year']=game.player.age
            if not years:continue
            # Budget captured when actual combat requirements are refreshed.
            due=round(years*row.get('reference_need',40)*.001+row.get('stationing_credit',0.),9)
            charge=int(due);row['stationing_credit']=due-charge
            source=f'war-supply:{war["id"]}:{side}'
            paid=min(charge,balance(game,source))
            destination=f'background:{row["world"]}'
            transfer_value(game,source,destination,paid,'驻军营地日常后勤服务（按实际年数）')
            row['stationing_paid']=row.get('stationing_paid',0)+paid
            row['stationing_shortfall']=charge-paid

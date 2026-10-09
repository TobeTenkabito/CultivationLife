"""Small elapsed-year encampment services, distinct from actual battle baskets."""
from ..economy.ledger import balance, transfer_value


def advance(game):
    for war in game.wars:
        if war.get('status') != 'active' or not war.get('logistics'):
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

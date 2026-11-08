"""Shared seven-office majority ballot, distinct from the 49 electoral seats."""


def player_ballot(court, holders, rng, persuasion=0., pledges=None):
    pledges=pledges or {}
    votes=[dict(holder=key,yes=key=='player' or rng.random()<
                min(1.,.48+court['player_support']/500+persuasion+(.15 if key in pledges else 0))) for key in holders]
    yes=sum(v['yes'] for v in votes)
    return dict(yes=yes,no=len(votes)-yes,abstain=0,total=len(votes),passed=yes>len(votes)//2,votes=votes)

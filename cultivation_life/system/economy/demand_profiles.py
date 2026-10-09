"""Eight end uses, thirteen realm profiles; totals keep the old welfare scale."""
USES = ('healing', 'cultivation', 'longevity', 'breakthrough', 'repair', 'artifact', 'energy', 'general')
# Percent of requested pieces, not of cash: rare high-grade artifacts remain
# subject to the existing welfare envelope and actual stock.
SHARES = (
    (22,30,0,0,15,8,20,5),
    (15,37,0,22,8,5,10,3),
    (14,33,3,25,8,6,9,2),
    (13,28,10,23,8,8,8,2),
    (12,18,28,20,6,6,8,2),
    (10,12,25,35,5,5,6,2),
    (10,25,0,25,8,20,10,2),
    (8,15,0,15,6,46,8,2),
    (6,14,0,14,6,50,8,2),
    (6,13,0,13,6,52,8,2),
    (6,12,0,12,6,54,8,2),
    (6,11,0,11,6,56,8,2),
    (6,10,0,10,6,58,8,2),
)
TOTAL_RATE = .113


def rates(rank):
    return {use: TOTAL_RATE*share/100 for use,share in zip(USES, SHARES[rank])}

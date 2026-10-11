from ...content_registry import WORLD_SYSTEMS

POLICIES = {
    'stewardship': dict(name='安土养民', minimum=70, maximum=100, decay=.65, upkeep=.85, yield_factor=1),
    'extraction': dict(name='节制采办', minimum=50, maximum=90, decay=1.15, upkeep=1.15, yield_factor=1.15),
    'patrol': dict(name='巡边固守', minimum=30, maximum=70, decay=.55, upkeep=1.2, yield_factor=.9),
    'conciliation': dict(name='结交乡老', minimum=0, maximum=50, decay=.7, upkeep=.8, yield_factor=.8),
}
DECAY_PER_YEAR = .12
MAX_FACTIONS = 3
TERMS = {'remove_influence', 'destroy_outpost'}
COSTS = {
    1: dict(action=1000, outpost=10000, grade=2, spar_realm=3),
    2: dict(action=50000, outpost=500000, grade=6, spar_realm=6),
    3: dict(action=1600000, outpost=16000000, grade=9, spar_realm=9),
}

def costs(world):
    return COSTS[WORLD_SYSTEMS['world_profiles'][world]['tier']]

def enabled():
    return bool(WORLD_SYSTEMS.get('intrigue_dlc',{}).get('enabled'))

def band(value):
    return next(name for threshold, name in [(90,'中枢地区'),(70,'核心地区'),(50,'战略要地'),(30,'边缘地区'),(0,'缓冲地区')] if value >= threshold)

def permits(policy, value):
    p = POLICIES.get(policy)
    return bool(p and p['minimum'] <= value <= p['maximum'])

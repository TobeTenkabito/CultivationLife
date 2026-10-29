"""Reviewed peer-world pairs and costs, independent of registry and game state."""
GROUPS = (('human', 'demon'), ('spirit', 'true_demon', 'monster_realm', 'phantom_underworld', 'hell'),
          ('celestial', 'asura', 'nether', 'reincarnation'))
TIERS = {world: tier for tier, worlds in enumerate(GROUPS, 1) for world in worlds}
ENDPOINTS = dict(human='wudi_plain', demon='red_marrow_city', spirit='hundred_race_city',
    true_demon='abyss_city', monster_realm='myriad_beast_city', phantom_underworld='nine_tail_dream_city',
    hell='yin_market_capital', celestial='jade_capital', asura='ten_thousand_battle_city',
    nether='world_tree_crown', reincarnation='karma_city')
WORLD_NAMES = dict(human='人界', demon='魔界', spirit='灵界', true_demon='真魔界', monster_realm='妖界',
                   phantom_underworld='幻冥界', hell='地狱界', celestial='仙界', asura='修罗界', nether='幽冥界', reincarnation='轮回界')
SITE_NAMES = dict(human='无棣原', demon='赤髓城', spirit='百族天城', true_demon='渊极城', monster_realm='万兽天城',
                  phantom_underworld='九尾梦城', hell='阴市都', celestial='玉京仙都', asura='万战魔城', nether='界树天冠', reincarnation='因果天城')


def peers(world):
    return tuple(other for other in GROUPS[TIERS[world]-1] if other != world) if world in TIERS else ()


def paired(source, destination):
    return destination in peers(source)


def profile(world):
    tier = TIERS[world]
    scale = (1, 50, 1600)[tier-1]
    minimum, maximum = ((3, 5), (6, 8), (9, 12))[tier-1]
    return dict(tier=tier, scale=scale, grade=(2, 6, 9)[tier-1], minimum=minimum, maximum=maximum,
                npc_minimum=1 if tier == 1 else minimum, annual=100*scale, build_cost=10000*scale,
                working_cash=10000*scale, war_budget=30000*scale, transfer=10000*scale)


def target(owner_id, destination=None):
    return f'outpost:{owner_id}' + (f':{destination}' if destination else '')


def target_for(owner_id, source, destination):
    return target(owner_id) if {source, destination} == {'human', 'demon'} else target(owner_id, destination)


def target_owner(value):
    return value.split(':')[1]


def target_destination(value, source):
    parts = value.split(':')
    if len(parts) == 3:
        return parts[2]
    return peers(source)[0] if source in {'human', 'demon'} else None

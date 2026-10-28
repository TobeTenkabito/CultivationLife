"""Read causal achievement evidence without preparing people, regions or resources."""


def soul_story(game, kind, history_index=None):
    rows = (history_index or {}).get('SYS_SOUL', ()) if history_index is not None else (
        r for r in game.history if r.event_id == 'SYS_SOUL')
    if kind in {'body_destroyed', 'second_rescued'}:
        return any(r.state_diff.get(kind) is True for r in rows)
    if kind != 'account_recovered' or not game.player.alive or not game.player.ghost_host_body:
        return False
    host = game.player.ghost_host_body
    loss = None
    matching = None
    for row in game.history:
        if row.event_id == 'SYS_SOUL' and row.state_diff.get('body_destroyed'):
            if loss is None:
                loss = row.state_diff.get('lost_realm')
        elif row.event_id == 'SYS_CAPTIVE_ACTION' and row.result == 'possessed':
            target = row.state_diff.get('target_id')
            matching = loss if target and target in {host.get('id'), host.get('npc_id')} else None
            loss = None
    source = game.player.cultivation_suppression or game.player.sealed_cultivation or {}
    rank = source.get('realm_index', game.player.realm_index)
    return matching is not None and rank >= matching


def family_line_preserved(game):
    family = game.family
    if (not family or family.extinct or family.kind != 'family'
            or family.world != game.player.world
            or family.heritage.get('line_successor') != 'player'
            or not family.heritage.get('rename_available')):
        return False
    return any(r.event_id == 'SYS_FAMILY_LINE_SUCCESSION' and r.result == 'succeeded'
               and r.choice_id == family.id and r.state_diff.get('successor') == 'player'
               for r in game.history)


def homecoming(game):
    from .content_registry import WORLD_SYSTEMS
    profiles = WORLD_SYSTEMS['world_profiles']
    origins = set()
    ascensions = {'SYS_CELESTIAL_ASCENSION_COMPLETE', 'SYS_ASURA_ASCENSION_COMPLETE',
                  'SYS_MONSTER_NETHER_ASCENSION', 'SYS_DEMONIC_ASCENSION', 'EVT_SPIRIT_CROSSING_003'}
    for row in game.history:
        worlds = row.state_diff.get('world')
        if (row.event_id in ascensions and row.result in {'ascended', 'entered_spirit_realm'}
                and isinstance(worlds, list) and len(worlds) == 2
                and worlds[0] in profiles and worlds[1] in profiles
                and profiles[worlds[0]]['tier'] < profiles[worlds[1]]['tier']):
            origins.add(worlds[0])
        elif (row.event_id == 'SYS_CROSS_WORLD' and row.state_diff.get('mode') == 'sealed_descent'
              and row.choice_id in origins and row.result == f'returned_{row.choice_id}'):
            return True
    return False


def three_sect_leaders(game):
    p = game.player
    sect = game.sects.get(p.faction_id)
    if not p.alive or not sect or sect.extinct or sect.world != p.world or sect.kind != 'sect':
        return False
    count = 0
    for row in game.history:
        if row.event_id == 'SYS_PLAYER_LEAVE_FACTION' and row.choice_id == sect.id:
            count = 0
        if (row.event_id == 'SYS_SECT_LEADER_DISMISSED' and row.result == 'dismissed'
                and row.state_diff.get('sect_id') == sect.id
                and row.state_diff.get('joined_age') == p.faction_join_age):
            count += 1
    return count >= 3


def inherited_technique(game, minimum):
    from .system import authored_techniques as author
    if not author.enabled():
        return False
    source = game.authored_techniques.get('source_id')
    if not source or source == game.id:
        return False
    inherited = author.definitions(game, 'inherited')
    return any(t.level >= minimum and t.id in inherited and inherited[t.id].get('origin') == source
               for t in game.player.known_techniques)

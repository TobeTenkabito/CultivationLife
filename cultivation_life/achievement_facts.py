"""Achievement evidence over existing identities; no preparation, RNG or simulation."""


def _people(game):
    # Match relationship_records.find_person's precedence without N roster scans.
    people = dict(game.relationship_npcs)
    if game.family and game.family.extinct:
        people.update((npc.id, npc) for npc in game.family.npcs)
    for sect in reversed(tuple(game.sects.values())):
        people.update((npc.id, npc) for npc in sect.npcs)
    for registry in (game.notable_npcs, game.world_npcs):
        people.update(registry)
    if game.family and not game.family.extinct:
        people.update((npc.id, npc) for npc in game.family.npcs)
    people.update(game.inactive_npcs)
    return people


def _sect_leader(game, sect, people):
    record = game.intrigue_state.get('factions', {}).get(f'sect:{sect.id}', {})
    positions = record.get('positions', {})
    if 'leader' in positions:
        identity = positions['leader']
        npc = people.get(identity)
    else:
        # Before political offices are adopted, the original roster owns titles.
        npc = next((n for n in sect.npcs if n.title in {'掌门', '宗主'} and n.alive), None)
        identity = npc.id if npc else None
    guests = {row.get('npc_id') for row in record.get('guests', [])}
    guests.add(positions.get('guest_elder'))
    return identity if (
        npc and not sect.extinct and sect.kind == 'sect'
        and npc.alive and npc.world == sect.world and npc.roster_state == 'active'
        and (npc.faction_id == sect.id or any(n.id == identity for n in sect.npcs))
        and identity not in guests and identity not in game.intrigue_state.get('npc_prisons', {})
    ) else None


def leader_sect_before_capture(game, identity):
    """Read the office or its original custody provenance, never a name match."""
    people = _people(game)
    npc = people.get(identity)
    if npc and npc.roster_state == 'held':
        return next((o['leader_sect_id'] for o in npc.roster_origin if o.get('leader_sect_id')), None)
    return next((sect.id for sect in game.sects.values()
                 if _sect_leader(game, sect, people) == identity), None)


def descendants_lead_sects(game, minimum):
    descendants = {row['id'] for row in game.player.offspring if row.get('id')}
    if not descendants:
        return False
    people = _people(game)
    # Parent IDs extend the genealogy; names and generic clan membership do not.
    pending = list(people.values())
    while pending:
        found = [npc for npc in pending
                 if descendants.intersection(npc.family_traits.get('parents', ()))]
        if not found:
            break
        descendants.update(npc.id for npc in found)
        pending = [npc for npc in pending if npc.id not in descendants]
    leaders = {_sect_leader(game, sect, people) for sect in game.sects.values()}
    return len(leaders & descendants) >= minimum


def family_kin_all_fallen(game):
    family = game.family
    if not family or not game.player.alive:
        return False
    people = _people(game)
    members = {npc.id: npc for npc in family.npcs}
    for npc in game.inactive_npcs.values():
        if any(o.get('container') == 'family' and o.get('id') == family.id for o in npc.roster_origin):
            members[npc.id] = npc
    kin = {identity: people.get(identity, npc) for identity, npc in members.items()
           if npc.family_traits.get('kin', npc.title in {'始祖', '族长', '族人', '嫡系后人', '族老'})
           and not npc.family_traits.get('expelled')}
    membership = game.family_state.get('membership')
    player_kin = (family.founded_by_player and family.founder_player_id == game.id
                  or (bool(membership.get('kin')) if membership else True))
    if player_kin:
        for child in game.player.offspring:
            if child.get('id') and not child.get('family_traits', {}).get('expelled'):
                kin[child['id']] = people.get(child['id'], child)
    def fallen(person):
        read = person.get if isinstance(person, dict) else lambda key, default=None: getattr(person, key, default)
        reason = read('death_reason') or ''
        return not read('alive', True) and (
            reason in {'势力征伐中阵亡', '势力大战中陨落', '仙域斗法中陨落'}
            or reason.startswith('与') and reason.endswith('斗法时陨落')
            or reason.startswith('遭') and reason.endswith('截杀')
            or reason.startswith('被') and reason.endswith('击杀夺宝')
            or reason.startswith('执行对') and reason.endswith('的通缉令时反遭灭杀')
        )
    return bool(kin) and all(fallen(person) for person in kin.values())


def record_corpse_campaign(game, war_id, roster, rounds):
    if not war_id or not rounds or game.player.milestones.get('former_leader_corpse_campaign'):
        return
    war = next((row for row in game.wars if row.get('id') == war_id), None)
    if (not war or war.get('world') != game.player.world or war.get('kind') != 'sect'
            or war.get('status') not in {'active', 'peace_ready'}):
        return
    participants = {war.get('attacker_id'), war.get('defender_id')}
    participants.update(row.get('id') for rows in war.get('coalitions', {}).values() for row in rows)
    participants.update(war.get('roster_owner', {}).values())
    deployed = {row['id'] for row in roster if row.get('kind') == 'corpse'
                and row.get('engaged_power', row.get('power', 0)) > 0 and row.get('integrity', 1) > 0}
    if any(puppet.get('id') in deployed and puppet.get('type') == 'corpse'
           and puppet.get('former_leader_sect_id')
           and puppet.get('former_leader_sect_id') in participants
           for puppet in game.player.puppets):
        game.player.milestones['former_leader_corpse_campaign'] = 1

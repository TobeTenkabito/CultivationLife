"""Whole-organization campaign occupancy, shared by every military entry."""


def require_ordinary_entry(store, game_id, war_id):
    # Reject a frontier command before ordinary load preparation can adopt
    # markets or rewrite unrelated state in an otherwise rejected request.
    game = store.load(game_id)
    if any(w.get('id') == war_id and w.get('outpost_id') for w in game.wars):
        raise ValueError('驻地战役须通过诸天开拓原军令入口办理')


def participant_ids(war):
    return {war.get('attacker_id'), war.get('defender_id')} | {
        r['id'] for rows in war.get('coalitions', {}).values() for r in rows
    } | set(war.get('roster_owner', {}).values())


def organization(game, identity):
    return game.family if game.family and game.family.id == identity else game.sects.get(identity)


def busy(game, org, *, managed_only=False):
    members = {n.id for n in org.npcs}
    for war in game.wars:
        if managed_only and not (war.get('strategic_war_id') or war.get('outpost_id')):
            continue
        unfinished = war.get('status') in {'active', 'peace_ready', 'withdrawing'} or any(
            j.get('phase') not in {'home', 'lost'}
            for rows in war.get('journeys', {}).values() for j in rows)
        if not unfinished:
            continue
        if org.id in participant_ids(war):
            return True
        if any(members.intersection(roster) for roster in war.get('roster', {}).values()):
            return True
        if war.get('kind') == 'race' and org.world == war.get('world') and org.allegiance_race in participant_ids(war):
            return True
    return False

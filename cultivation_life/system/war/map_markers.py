"""Read-only actual campaign locations, distinct from political race identities."""
def markers(game, names):
    result = {}
    for w in game.wars:
        if (w.get('kind') != 'sect' or w.get('world') != game.player.world
                or w.get('status') not in {'active','peace_ready','withdrawing'} or not w.get('location_id')):
            continue
        phase = w.get('campaign_phase','engaged')
        result.setdefault(w['location_id'],[]).append(dict(
            id=w['id'], strategic_war_id=w.get('strategic_war_id'), phase=phase,
            attacker=names.get(w['attacker_id'],'原组织'),defender=names.get(w['defender_id'],'原组织'),
            attacker_orgs=len(w.get('coalitions',{}).get('attacker',[])) or 1,
            defender_orgs=len(w.get('coalitions',{}).get('defender',[])) or 1,
            battles=w.get('battles',0)))
    return result

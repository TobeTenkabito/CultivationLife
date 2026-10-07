from __future__ import annotations
from .dependencies import CourtLifecycleDependencies


def _court_conflicts(deps: CourtLifecycleDependencies, law_id):
    return [other for group in deps._court_config()['law_conflicts']
            if law_id in group for other in group if other != law_id]


def _court_normalize(deps: CourtLifecycleDependencies, game):
    court = game.heavenly_court
    if court.get('experience_version') == 2:
        return False
    unit = int(court['unit'])
    for holder in court['offices'].values():
        if holder:
            holder['end_unit'] = max(int(holder.get('end_unit', unit)),
                                     int(holder.get('start_unit', unit)) + 14)
    # Old promises did not record whether the player was elected. They cannot
    # safely establish a debt in the new rules, so grandfather them out.
    court['pledges'] = []
    court['election_queue'] = []
    election = court.get('open_election')
    if election and court['offices'].get(election['office_id']):
        court['open_election'] = None
    for group in deps._court_config()['law_conflicts']:
        active = [key for key in group if court['laws'].get(key)]
        if len(active) > 1:
            keep = max(active, key=lambda key: court.get('law_changed_at', {}).get(key, -1))
            for key in active:
                court['laws'][key] = key == keep
    deps._court_prune_decrees(court)
    court['experience_version'] = 2
    return True


def _court_prune_decrees(deps: CourtLifecycleDependencies, court):
    definitions = {row['id']: row for row in deps._court_config()['decrees']}
    court['active_decrees'] = [row for row in court['active_decrees']
        if row['id'] in definitions
        and (not definitions[row['id']].get('requires_law')
             or court['laws'].get(definitions[row['id']]['requires_law']))
        and not court['laws'].get(definitions[row['id']].get('forbidden_law'))]
    slots = deps._court_config()['base_decree_slots'] + int(court['laws'].get('assistant_officials', False))
    court['active_decrees'] = court['active_decrees'][-slots:]


def _court_finish_unattended(deps: CourtLifecycleDependencies, game, rng):
    """Continuing life or disabling notices abstains without spending time."""
    court = game.heavenly_court
    if not court:
        return
    for _ in range(7):
        election = court.get('open_election')
        if election:
            election['candidates'] = [key for key in election['candidates'] if key != 'player']
            election.pop('campaign_pledges', None)
            if not election['candidates']:
                court['open_election'] = None
            else:
                for attempt in range(50):
                    success, _ = deps._court_resolve_election_round(game, rng, 'none', '')
                    if success:
                        break
        if not court.get('election_queue'):
            break
        deps._court_open_next_queued_election(game, rng)


def _court_schedule_elections(deps: CourtLifecycleDependencies, game, rng):
    court = game.heavenly_court
    # One vacant chair is offered each unit. Occupied chairs are never put
    # up for election until their individual full term has elapsed.
    if court.get('open_election'):
        return
    vacancy = next((key for key, holder in court['offices'].items() if not holder), None)
    if vacancy:
        deps._court_open_election(game, vacancy, rng)


def _court_pay_stipend(deps: CourtLifecycleDependencies, game):
    # Politics can tick after a partial action; the yearly fiscal clock pays once.
    grade = game.heavenly_court['player_grade']
    annual = deps._court_config()['grade_stipends'][str(grade)] / 100
    return f'天庭{grade}品俸禄基准每年 {annual:g} 灵石，按实际年数与府库余额结算。'


def private_combat(target, wanted_ids):
    """Only voluntary, unauthorized cultivator combat violates protection."""
    ids = {str(target.get('npc_id', '')), *(str(n.get('npc_id', '')) for n in target.get('members', []))}
    return (target.get('combat_type') == 'cultivator'
            and not target.get('court_authorized') and not target.get('player_defending')
            and not target.get('execution') and not ids.intersection(wanted_ids))

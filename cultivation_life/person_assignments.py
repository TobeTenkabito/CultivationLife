"""Read-only identity occupancy shared by ordinary people and civilian travel."""


def research_assignments(game):
    runtime = game.heavens_state.get('runtime') or {}
    rows = ([runtime['sea_echo']] if runtime.get('sea_echo') else []) + list(runtime.get('contacts', {}).values())
    return [(echo, echo[key]) for echo in rows for key in ('mission', 'freight', 'migration') if echo.get(key)]


def assignment_person(echo, row):
    return row.get('person_id', echo['visitor_id'])


def deployment_assignment(game, identity, *, exclude_war=None):
    for row in game.heavens_state.get('runtime', {}).get('outposts', {}).values():
        unit = next((u for u in row['units'] if u['person_id'] == identity and u['phase'] not in {'home', 'lost'}), None)
        if unit and (not exclude_war or unit.get('war_id') != exclude_war):
            return {**unit, 'observed': True, 'outpost_id': row['id']}
    for war in game.wars:
        if war.get("id") == exclude_war or not (war.get("strategic_war_id") or war.get('outpost_id')) or war.get("status") not in {"active", "peace_ready", "withdrawing"}:
            continue
        for journeys in war.get("journeys", {}).values():
            for row in journeys:
                if row["person_id"] == identity and row["phase"] not in {"home", "lost"}:
                    return {**row, "war_id": war["id"]}
    campaign = game.heavens_state.get('runtime', {}).get('campaign')
    if campaign:
        unit = next((u for u in campaign['units'] if u['person_id'] == identity and u['phase'] not in {'home', 'lost'}), None)
        if unit:
            return unit
    row = game.heavens_state.get('runtime', {}).get('frontier')
    return row if row and row['status'] == 'active' and row['person_id'] == identity else None


def research_assignment(game, identity, *, exclude_war=None):
    # Compatibility accessor: old consumers must also respect military occupancy.
    deployment = deployment_assignment(game, identity, exclude_war=exclude_war)
    if deployment:
        return deployment
    for key in ('ruins', 'mirror'):
        survey = game.heavens_state.get('runtime', {}).get(key, {}).get('survey')
        if survey and survey['status'] == 'active' and survey['person_id'] == identity:
            return survey
    return next((mission for echo, mission in research_assignments(game)
                 if assignment_person(echo, mission) == identity and mission['status'] == 'active'), None)


def in_transit(game, identity):
    mission = research_assignment(game, identity)
    return bool(mission and mission['phase'] in {'gathering', 'outbound', 'transport', 'returning', 'homeward', 'local_outbound', 'local_return', 'campaign'})


def require_unassigned(game, identity):
    if deployment_assignment(game, identity):
        raise ValueError('此人已有先遣部署，结束前不能另行安排关系或同行职责')
    if research_assignment(game, identity):
        raise ValueError('此人已有访学行程，返乡前不能另行安排关系或同行职责')


def route_occupied(game, source, destination, *, exclude=None):
    from .system.heavens.definitions import default_site
    from .regional_context import task_active
    # A personal crossing that already reserved the lane keeps it when an NPC
    # finishes studying and queues its return during that same world year.
    runtime = game.heavens_state.get('runtime') or {}
    for task in runtime.get('tasks', []):
        if task['status'] not in {'reserved', 'running', 'paused'} or task['action'] not in {'visit_depart', 'visit_return'}:
            continue
        from .system.heavens.definitions import VISIT_DESTINATIONS
        a, b = default_site(task['target_id']).world, default_site(VISIT_DESTINATIONS[task['target_id']]).world
        if task['action'] == 'visit_return':
            a, b = b, a
        if (source, destination) == (a, b):
            return exclude != game.id
    for echo, mission in research_assignments(game):
        if assignment_person(echo, mission) == exclude or mission['status'] != 'active' or mission['phase'] in {'studying', 'settling'}:
            continue
        # A suspended foreign trip retains its person and escrow, but cannot
        # reserve a live lane forever and prevent entry into its owning world.
        # On entry it resumes behind any already reserved personal crossing.
        if not task_active(game, default_site(echo['id']).world):
            continue
        a, b = default_site(echo['id']).world, default_site(mission['destination']).world
        if mission['phase'] == 'returning':
            a, b = b, a
        if (source, destination) == (a, b):
            return True
    return False


def outpost_lane_holder(game, *, eligible=None, source=None, destination=None):
    """One civilian frontier lane; suspended foreign trips do not block entry."""
    from .regional_context import task_active
    from .system.heavens.outpost_definitions import is_target, ENDPOINTS
    from .npc_custody import is_free
    from .relationship_records import find_person
    runtime = game.heavens_state.get('runtime', {})
    def matches(row):
        return not source or {row.get('source'), row.get('destination')} == {source, destination}
    if any(is_target(t.get('target_id')) and t['action'] in {'outpost_depart', 'outpost_return'}
           and t['status'] in {'reserved', 'running', 'paused'}
           and matches(runtime.get('outposts', {}).get(t['target_id'], {})) for t in runtime.get('tasks', [])):
        return game.id
    candidates = []
    for row in runtime.get('outposts', {}).values():
        if not matches(row):
            continue
        for unit in row['units']:
            world = row['source'] if unit['phase'] == 'outbound' else row['destination']
            npc = find_person(game, unit['person_id'], include_inactive=True)
            if (unit['phase'] in {'outbound', 'returning'} and task_active(game, world) and npc and is_free(npc)
                    and (npc.world, npc.location_id) == (world, ENDPOINTS[world])
                    and npc.id not in game.intrigue_state.get('npc_prisons', {})
                    and (eligible is None or eligible(row, unit, npc))):
                candidates.append(unit)
    return min(candidates, key=lambda u: (-bool(u['progress']), u['wallet']))['person_id'] if candidates else None

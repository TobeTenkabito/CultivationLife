"""Read-only identity occupancy shared by ordinary people and civilian travel."""


def research_assignments(game):
    runtime = game.heavens_state.get('runtime') or {}
    rows = ([runtime['sea_echo']] if runtime.get('sea_echo') else []) + list(runtime.get('contacts', {}).values())
    return [(echo, echo[key]) for echo in rows for key in ('mission', 'freight', 'migration') if echo.get(key)]


def assignment_person(echo, row):
    return row.get('person_id', echo['visitor_id'])


def research_assignment(game, identity):
    for key in ('ruins', 'mirror'):
        survey = game.heavens_state.get('runtime', {}).get(key, {}).get('survey')
        if survey and survey['status'] == 'active' and survey['person_id'] == identity:
            return survey
    return next((mission for echo, mission in research_assignments(game)
                 if assignment_person(echo, mission) == identity and mission['status'] == 'active'), None)


def in_transit(game, identity):
    mission = research_assignment(game, identity)
    return bool(mission and mission['phase'] in {'outbound', 'returning'})


def require_unassigned(game, identity):
    if research_assignment(game, identity):
        raise ValueError('此人已有访学行程，返乡前不能另行安排关系或同行职责')


def route_occupied(game, source, destination, *, exclude=None):
    from .system.heavens.definitions import default_site
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
        a, b = default_site(echo['id']).world, default_site(mission['destination']).world
        if mission['phase'] == 'returning':
            a, b = b, a
        if (source, destination) == (a, b):
            return True
    return False

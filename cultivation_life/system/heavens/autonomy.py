"""Bounded civilian discovery after the authoritative ordinary NPC year."""
from hashlib import sha256

from . import mirror, ruins, survey
from .definitions import RUINS_ID, MIRROR_ID


def year_step(deps, game):
    state = game.heavens_state
    runtime = state.get('runtime')
    if (not runtime or survey.occupied(game) or not state['generation_enabled']
            or game.player.world in {'lost', 'rift'}):
        return
    year = runtime['processed_years'] + 1
    window = year // 100
    if window < 1 or window <= runtime.get('survey_discovery_window', 0):
        return
    if not deps.get_definitions().generation_available:
        return
    # One opportunity per elapsed century, including empty or unsuccessful windows.
    # No replay of missed centuries and no consumption of either existing RNG stream.
    runtime['survey_discovery_window'] = window
    raw = sha256(f'{game.seed}:heavens:resident-survey:v1:{window}'.encode()).digest()
    if int.from_bytes(raw[:8], 'big') >= 2**62:
        return
    routes = [target for target in (RUINS_ID, MIRROR_ID) if not survey.get(game, target)]
    # Both unassigned destinations use the same civilian qualifications; scan
    # the real roster once. An undiscovered mirror needs a local witness.
    candidates = deps.survey_candidates(game, autonomous=True, target=routes[0]) if routes else []
    choices = {target: [person for person in candidates if target != MIRROR_ID or runtime.get('mirror')
                       or deps.resolve_person(game, person['id']).location_id == 'muling_desert']
               for target in routes}
    identities = sorted({person['id'] for rows in choices.values() for person in rows})
    if not identities:
        return
    identity = identities[int.from_bytes(raw[8:16], 'big') % len(identities)]
    npc = deps.resolve_person(game, identity)
    routes = [target for target, rows in choices.items() if any(p['id'] == identity for p in rows)]
    local = [target for target in routes if npc.location_id == (
        'muling_desert' if target == MIRROR_ID else 'wudi_plain')]
    options = local or routes
    target = options[int.from_bytes(raw[16:24], 'big') % len(options)]
    scene = survey.scene_for(game, target)
    if target == RUINS_ID:
        scene = scene or ruins.create(deps, game, known=False, year=year)
        deps.prepare_ruins(game, scene)
    else:
        scene = scene or mirror.create(deps, game, known=False, year=year)
        deps.prepare_mirror(game, scene)
    scene['survey'] = survey.assignment(npc, year)
    scene['survey'].update(autonomous=True, introduced=False)
    survey.reveal(deps, game, year=year, target=target)

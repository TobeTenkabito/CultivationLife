"""Bounded civilian discovery after the authoritative ordinary NPC year."""
from hashlib import sha256

from . import ruins, survey


def year_step(deps, game):
    state = game.heavens_state
    runtime = state.get('runtime')
    if (not runtime or survey.get(game) or not state['generation_enabled']
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
    candidates = deps.survey_candidates(game, autonomous=True)
    if not candidates:
        return
    identity = candidates[int.from_bytes(raw[8:16], 'big') % len(candidates)]['id']
    npc = deps.resolve_person(game, identity)
    scene = ruins.get(game) or ruins.create(deps, game, known=False, year=year)
    deps.prepare_ruins(game, scene)
    scene['survey'] = survey.assignment(npc, year)
    scene['survey'].update(autonomous=True, introduced=False)
    survey.reveal(deps, game, year=year)

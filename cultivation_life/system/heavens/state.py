"""Save-local M1 facts; deterministic construction, never called by a view."""
from dataclasses import asdict
from hashlib import sha256

from .schema import initial_state


def initialize(game, *, enabled=True):
    if not game.heavens_state:
        game.heavens_state = initial_state()
    state = game.heavens_state
    state['generation_enabled'] = enabled
    if enabled and 'runtime' not in state:
        state['runtime'] = dict(epoch_age=game.player.age, processed_years=0, last_year_key=0,
            last_discovery_window=-1, rng_counter=0, next_task_seq=1,
            unit_credit={'numerator': 0, 'denominator': 1}, sea_echo=None,
            tasks=[], history=[], notifications=[], pause_requested=False, pause_on_opportunity=False)
    return state


def record(game, text):
    runtime = game.heavens_state['runtime']
    runtime['history'].append({'year': runtime['processed_years'], 'text': text})
    runtime['history'] = runtime['history'][-128:]


def create_echo(deps, game):
    state = game.heavens_state
    runtime = state['runtime']
    if runtime['sea_echo'] is not None:
        return runtime['sea_echo']
    definition = asdict(deps.get_definitions().sea_echo)
    identity = 'heavens-' + sha256(f'{game.id}:{game.seed}:sea_echo:visitor:v1'.encode()).hexdigest()[:24]
    # Creation is explicit and uses the existing authoritative NPC container.
    deps.create_visitor(game, identity)
    runtime['sea_echo'] = dict(id='sea_echo', definition=definition,
        origin_year=runtime['processed_years'], visitor_id=identity,
        arrived_at=runtime['processed_years'], record_id='karma_city_old_copy',
        cycle=0, observed_cycle=-1, history_checked=False, exchanged=False,
        maintained=False, maintenance_started=False, applications_used=0,
        reward_base=None, reward_claimed=0.0, application=None, project_stones=0)
    state['definition_versions']['sea_echo'] = definition['revision']
    record(game, '法则天海的潮汐与接引碑旧记不合；本地访学者观澜散人持有一份旧抄录。')
    return runtime['sea_echo']


def phase(runtime, echo):
    definition = echo['definition']
    elapsed = runtime['processed_years'] - echo['origin_year']
    cycle, offset = divmod(elapsed, definition['period_years'])
    cutoff = definition['window_years'] + (definition['extension_years'] if echo['maintained'] and cycle == echo['cycle'] else 0)
    return cycle, offset, cutoff


def active_task(runtime):
    return next((task for task in runtime['tasks'] if task['status'] in {'reserved', 'running', 'paused'}), None)


def visible_notice(game, text):
    runtime = game.heavens_state['runtime']
    if any(row['id'] == 'sea_echo' for row in runtime['notifications']):
        return
    echo = runtime['sea_echo']
    _, offset, cutoff = phase(runtime, echo)
    runtime['notifications'].append(dict(id='sea_echo', text=text,
        expires_at=runtime['processed_years'] + min(600, max(0, cutoff - offset))))
    runtime['notifications'] = runtime['notifications'][-3:]
    if game.heavens_state['watch'] and runtime['pause_on_opportunity']:
        runtime['pause_requested'] = True

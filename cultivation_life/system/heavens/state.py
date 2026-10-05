"""Save-local M1 facts; deterministic construction, never called by a view."""
from dataclasses import asdict
from hashlib import sha256

from .schema import initial_state
from .definitions import ContactSite, default_site


def contacts(runtime):
    if not runtime:
        return []
    return ([runtime['sea_echo']] if runtime['sea_echo'] else []) + list(runtime.get('contacts', {}).values())


def get_echo(runtime, target_id='sea_echo'):
    if not runtime:
        return None
    return runtime['sea_echo'] if target_id == 'sea_echo' else runtime.get('contacts', {}).get(target_id)


def echo_site(echo):
    return ContactSite(**echo['site']) if echo.get('site') else default_site(echo['id'])


def site_for(deps, game, target_id):
    echo = get_echo(game.heavens_state.get('runtime'), target_id)
    return echo_site(echo) if echo else deps.get_definitions().site(target_id)


def current_site(deps, game):
    # Existing definitions remain authoritative after a content revision.
    saved = next((echo_site(echo) for echo in contacts(game.heavens_state.get('runtime'))
                  if echo_site(echo).world == game.player.world), None)
    return saved or next((site for site in deps.get_definitions().contact_sites if site.world == game.player.world), None)


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


def record(game, text, *, year=None):
    runtime = game.heavens_state['runtime']
    runtime['history'].append({'year': runtime['processed_years'] if year is None else year, 'text': text})
    runtime['history'] = runtime['history'][-128:]


def create_echo(deps, game, target_id='sea_echo'):
    state = game.heavens_state
    runtime = state['runtime']
    existing = get_echo(runtime, target_id)
    if existing is not None:
        return existing
    site = deps.get_definitions().site(target_id)
    if site is None:
        raise ValueError('诸天对象不可见或不存在')
    definition = asdict(deps.get_definitions().sea_echo)
    identity = 'heavens-' + sha256(f'{game.id}:{game.seed}:{target_id}:visitor:v1'.encode()).hexdigest()[:24]
    # Creation is explicit and uses the existing authoritative NPC container.
    deps.create_visitor(game, identity, site)
    echo = dict(id=target_id, definition=definition, site=asdict(site),
        origin_year=runtime['processed_years'], visitor_id=identity,
        arrived_at=runtime['processed_years'], record_id=site.record_id,
        cycle=0, observed_cycle=-1, history_checked=False, exchanged=False,
        maintained=False, maintenance_started=False, applications_used=0,
        reward_base=None, reward_claimed=0.0, application=None, project_stones=0)
    if target_id == 'sea_echo':
        runtime['sea_echo'] = echo
    else:
        runtime.setdefault('contacts', {})[target_id] = echo
    state['definition_versions'][target_id] = definition['revision']
    record(game, f'{site.name}出现可求证的现象；本地访学者{site.visitor_name}持有一份合法旧抄录。')
    return echo


def phase(runtime, echo):
    definition = echo['definition']
    elapsed = runtime['processed_years'] - echo['origin_year']
    cycle, offset = divmod(elapsed, definition['period_years'])
    cutoff = definition['window_years'] + (definition['extension_years'] if echo['maintained'] and cycle == echo['cycle'] else 0)
    return cycle, offset, cutoff


def active_task(runtime):
    return next((task for task in runtime['tasks'] if task['status'] in {'reserved', 'running', 'paused'}), None)


def visible_notice(game, text, target_id='sea_echo'):
    runtime = game.heavens_state['runtime']
    if any(row['id'] == target_id for row in runtime['notifications']):
        return
    echo = get_echo(runtime, target_id)
    _, offset, cutoff = phase(runtime, echo)
    runtime['notifications'].append(dict(id=target_id, text=text,
        expires_at=runtime['processed_years'] + min(600, max(0, cutoff - offset))))
    runtime['notifications'] = runtime['notifications'][-3:]
    if game.heavens_state['watch'] and runtime['pause_on_opportunity']:
        runtime['pause_requested'] = True

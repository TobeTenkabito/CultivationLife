"""One explicit hook after the existing ordinary or isolated world year."""
from dataclasses import dataclass
from hashlib import sha256

from .state import create_echo, phase, record, visible_notice, contacts, echo_site, current_site, get_echo

PARTICIPATION = (.02, .02, .02, .02, .08, .12, .16, .24, .32, .45, .65, .80, .90)


@dataclass(frozen=True, slots=True)
class YearContext:
    key: int
    activity: str = 'world'
    unit_years: int = 1
    unit_finished: bool = False
    supports_pause: bool = False


def year_step(deps, game, context: YearContext):
    state = game.heavens_state
    runtime = state.get('runtime')
    if runtime is None:
        return
    if context.key <= runtime['last_year_key']:
        return
    if context.key != runtime['last_year_key'] + 1:
        raise ValueError('诸天年度序号不连续')
    runtime['last_year_key'] = context.key
    runtime['processed_years'] += 1
    state['revision'] += 1
    now = runtime['processed_years']
    runtime['notifications'] = [row for row in runtime['notifications'] if row['expires_at'] > now]
    for echo in contacts(runtime):
        cycle, _offset, _cutoff = phase(runtime, echo)
        if cycle != echo['cycle']:
            echo.update(cycle=cycle, maintained=False, maintenance_started=False,
                        applications_used=0, reward_base=None, reward_claimed=0.0, application=None)
            record(game, f'{echo_site(echo).name}进入下一周期。旧记和合法抄录仍在，应用前须重新体察当期现象。')
        # Existing tasks still close when generation is switched off.
    deps.reconcile_tasks(game)
    window = now // 100 - 1
    if window <= runtime['last_discovery_window']:
        return
    runtime['last_discovery_window'] = window
    if not state['generation_enabled'] or not deps.get_definitions().generation_available:
        return
    facts = deps.read_actor_facts(game)
    site = current_site(deps, game)
    if not facts['can_discover'] or site is None or get_echo(runtime, site.id) is not None:
        return
    # Counter-based SHA-256 stream, independent of all old RNG consumers.
    counter = runtime['rng_counter']
    raw = sha256(f'{game.seed}:heavens:perception:v1:{counter}'.encode()).digest()
    runtime['rng_counter'] += 1
    draw = int.from_bytes(raw[:8], 'big') / 2**64
    if draw < PARTICIPATION[min(12, facts['true_realm'])]:
        create_echo(deps, game, site.id)
        visible_notice(game, f'{site.name}出现可求证的线索，可留在本地体察或继续原有修行。', site.id)


def take_pause(game):
    runtime = game.heavens_state.get('runtime')
    if not runtime or not runtime['pause_requested']:
        return False
    runtime['pause_requested'] = False
    game.heavens_state['revision'] += 1
    return bool(runtime['pause_on_opportunity'] and game.heavens_state['watch'] and runtime['notifications'] and game.player.alive and not game.pending_event)

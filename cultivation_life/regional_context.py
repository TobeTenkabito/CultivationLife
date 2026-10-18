"""Non-persistent settlement views over the one authoritative game and player.

Only the calendar is projected. Locations, people, treasuries and inventories
remain the original objects. A view is never a save or a second resource pool.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Collection
from typing import cast
from .regional_ports import RegionSynchronizationPort

_calendar = ContextVar('regional_calendar', default=None)


@contextmanager
def calendar_scope(game, world, year, *, person=None):
    active = game.__dict__.setdefault('_regional_active', {})
    if world in active:
        raise ValueError('地区年度不可重入')
    active[world] = year
    token = _calendar.set((game, world, year, person))
    try:
        yield
    finally:
        _calendar.reset(token)
        del active[world]


def before_departure(destination, npc=None):
    current = _calendar.get()
    if current:
        game, _, year, replaying = current
        identity = npc.get('id') if isinstance(npc, dict) else getattr(npc, 'id', None)
        if identity and game.world_simulation:
            # Original identity moves once. Destination catch-up must not age
            # the arrival during years before its actual departure.
            sim = game.world_simulation
            source = npc.get('world') if isinstance(npc, dict) else npc.world
            previous = sim['people'].get(identity, sim['regions'].get(source, {}).get('year', year))
            pending = sim.get('arrivals', {}).get(identity)
            # During personal replay, only years through this actual move have
            # been consumed. A future arrival reservation is not an aged year.
            first = year if replaying == identity else min(previous, pending['year']) if pending else previous
            sim['people'][identity] = year if replaying == identity else max(previous, year)
            if destination in sim['regions'] and (first < year or sim['regions'][destination]['year'] > year):
                sim.setdefault('arrivals', {})[identity] = dict(world=destination, year=first, entered=year)

class CalendarPlayer:
    def __init__(self, player, year):
        object.__setattr__(self, '_player', player)
        object.__setattr__(self, '_year', year)

    @property
    def age(self):
        return self._year

    def __getattr__(self, name):
        return getattr(self._player, name)

    def __setattr__(self, name, value):
        if name in {'age', 'world', 'location_id'}:
            raise ValueError('地方结算不能移动玩家或修改玩家年龄')
        setattr(self._player, name, value)


class CalendarGame:
    def __init__(self, game, world, year):
        object.__setattr__(self, '_game', game)
        object.__setattr__(self, '_region_world', world)
        object.__setattr__(self, 'player', CalendarPlayer(game.player, year))

    def __getattr__(self, name):
        return getattr(self._game, name)

    def __setattr__(self, name, value):
        setattr(self._game, name, value)


def region(game):
    return getattr(game, '_region_world', None)


def includes(game, world):
    return region(game) is None or region(game) == world


def historical(game):
    return isinstance(game, CalendarGame) and game.player.age < game._game.player.age


def annual_person(game, npc):
    """A migrated or multiply indexed original person ages only once per year."""
    if not includes(game, npc.world) or not task_active(game, npc.world):
        return False
    if game.world_simulation:
        years = game.world_simulation.setdefault('people', {})
        replaying = getattr(game, '_regional_single_person', None) == npc.id
        if not replaying and years.get(npc.id, -1) >= game.player.age:
            return False
        years[npc.id] = max(years.get(npc.id, -1), game.player.age)
    return True


def synchronize(game, worlds: Collection[str], *, entering: bool = False) -> None:
    """Explicit mutation boundaries call the engine-bound scheduler, never previews."""
    callback = cast(RegionSynchronizationPort[object] | None, getattr(game, '_synchronize_regions', None))
    if callback and game.world_simulation:
        root = game._game if isinstance(game, CalendarGame) else game
        selected = worlds if entering else set(worlds) & {region(game) or game.player.world}
        callback(root, selected, end=game.player.age)


def adoption_year(game):
    return game.player.age if region(game) else max(game.player.age, game.economy_v2['last_year'])


def current(game, world):
    """Endpoint-only systems may touch only a society caught up to this year."""
    if region(game):
        return includes(game, world)
    clocks = game.world_simulation.get('regions', {})
    return not clocks or clocks.get(world, {}).get('year') == game.player.age


def task_active(game, world):
    """A task has one owning society; contact with another never wakes it."""
    return not game.world_simulation or world == (region(game) or game.player.world)


def task_year(game):
    runtime = game.heavens_state['runtime']
    return max(0, game.player.age-runtime['epoch_age']) if region(game) else runtime['processed_years']+1


def remote_notice(game, world):
    """Read-only information delay; never claims an uncomputed outcome."""
    if not task_active(game, world):
        return '跨界信息流通不易，暂无法得到确切进度。以下为最后收到的消息，抵达当地后可核实后续情况。'
    return ''


def ordinary_year(game):
    """Preserve survey/upkeep's existing exclusion of player instance years."""
    from bisect import bisect_right
    spans = game.world_simulation.get('space_years', [])
    year = game.player.age
    index = bisect_right(spans, [year, float('inf')])-1
    return index < 0 or spans[index][1] < year

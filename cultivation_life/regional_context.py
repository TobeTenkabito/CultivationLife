"""Non-persistent settlement views over the one authoritative game and player.

Only the calendar is projected. Locations, people, treasuries and inventories
remain the original objects. A view is never a save or a second resource pool.
"""
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
    if not includes(game, npc.world):
        return False
    if region(game) is not None:
        years = game.world_simulation.setdefault('people', {})
        if years.get(npc.id, -1) >= game.player.age:
            return False
        years[npc.id] = game.player.age
    return True


def synchronize(game, worlds):
    """Explicit mutation boundaries call the engine-bound scheduler, never previews."""
    callback = getattr(game, '_synchronize_regions', None)
    if callback and game.world_simulation and region(game) is None:
        callback(game, worlds)


def adoption_year(game):
    return game.player.age if region(game) else max(game.player.age, game.economy_v2['last_year'])


def current(game, world):
    """Endpoint-only systems may touch only a society caught up to this year."""
    if region(game):
        return includes(game, world)
    clocks = game.world_simulation.get('regions', {})
    return not clocks or clocks.get(world, {}).get('year') == game.player.age

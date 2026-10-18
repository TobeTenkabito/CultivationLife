"""Lazy regional years on original state, committed by the enclosing save command.

No yearly deepcopy or regional save exists. The locked command owns its loaded
working game and atomically commits calendars, people, goods and task receipts.
Only explicitly selected regions advance; cross-world tasks never expand scope.
"""
import random
from ...content_registry import WORLD_SYSTEMS
from ...regional_context import CalendarGame, calendar_scope
from ...runtime import encode_rng, decode_rng
from ...system.economy import state, caravans, organizations


def worlds():
    return {w for w, p in WORLD_SYSTEMS['world_profiles'].items() if p['tier'] > 0}


def attach(host, game):
    game._synchronize_regions = lambda working, targets, **options: synchronize(host, working, targets, **options)


def ensure(host, game, *, baseline=None):
    attach(host, game)
    if game.world_simulation:
        return False
    start = game.player.age if baseline is None else baseline
    state.ensure_state(game)
    host._ensure_merchant(game)
    game.world_simulation = dict(version=1, base_year=start, regions={
        w:dict(year=start, initialized=False, merchant_year=start,
               rng=encode_rng(random.Random(f'regional:v1:{game.seed}:{w}')))
        for w in sorted(worlds())}, people={}, revision=0, recent=[])
    return True


def dependencies(host, game):
    return []


def important_worlds(game):
    return {game.player.world} & worlds()


def closure(host, game, targets):
    return sorted(set(targets) & worlds())


def initialize_region(host, game, world):
    clock = game.world_simulation['regions'][world]
    if clock['initialized']:
        return
    view = CalendarGame(game, world, clock['year'])
    # Adoption at the baseline creates no historical income and resurrects none.
    organizations.ensure_organizations(view, host.maps)
    caravans.ensure_caravans(view, host.maps, _world=world, _linked=False)
    clock['initialized'] = True


def catch_up_arrivals(host, game, world, news):
    """Late-recorded migrants replay only their original personal years."""
    clock = game.world_simulation['regions'][world]
    pending = game.world_simulation.get('arrivals', {})
    for identity, arrival in list(pending.items()):
        if arrival['world'] != world or clock['year'] < arrival.get('entered', arrival['year']):
            continue
        for year in range(arrival['year']+1, clock['year']+1):
            rng = random.Random(f'regional-arrival:{game.seed}:{identity}:{year}')
            view = CalendarGame(game, world, year)
            object.__setattr__(view, '_regional_single_person', identity)
            with calendar_scope(game, world, year, person=identity):
                news.extend(host._annual_world_npc_update(view, rng))
                from ...relationship_records import find_person
                if find_person(game, identity, include_inactive=True) is None:
                    news.extend(host._annual_offspring_and_family_update(view, rng))
        if pending.get(identity) is arrival:
            del pending[identity]


def tick(host, game, world, year, news):
    clock = game.world_simulation['regions'][world]
    assert year == clock['year'] + 1
    catch_up_arrivals(host, game, world, news)
    view = CalendarGame(game, world, year)
    rng = decode_rng(game.seed, clock['rng'])
    with calendar_scope(game, world, year):
        from ...system.economy.deferred_settlement import apply
        apply(view, world, year)
        state.advance_economy(view)
        caravans.advance_caravans(view, host.maps)
        organizations.advance_organizations(view, host.maps)
        news.extend(host._annual_sect_update(view, rng, personal=False))
        news.extend(host._annual_world_npc_update(view, rng))
        news.extend(host._annual_offspring_and_family_update(view, rng))
        host._annual_relationship_update(view, rng)
        host._advance_guixu_calendar(view, rng, news)
        from ...system.war.stationing import advance as stationing
        stationing(view)
        host._advance_strategic_wars(view, rng)
        host._dependencies.heavens.advance_researchers(view)
        settle_pending_units(host, game, world, year, news, rng=rng)
        from ...system.monster_civilizations.core import advance_year
        advance_year(view)
        from ...system.intrigue.custody import advance_prison_year
        advance_prison_year(view)
    clock.update(year=year, rng=encode_rng(rng))


def settle_pending_units(host, game, world, year, news, *, rng=None):
    """Replay due action units in actual order, including same-year reentry."""
    sim = game.world_simulation
    events = []
    for kind, key in ((1, 'society_units'), (2, 'faction_units')):
        rows = sim.get(key, {}).get(world, [])
        due = [row for row in rows if row['year'] <= year]
        if due:
            sim[key][world] = [row for row in rows if row['year'] > year]
            events.extend((row['year'], row['unit'], kind, row) for row in due)
    for war in game.wars:
        if war['world'] != world:
            continue
        rows = war.get('deferred_units', [])
        due = [row for row in rows if row['year'] <= year]
        if due:
            war['deferred_units'] = [row for row in rows if row['year'] > year]
            events.extend((row['year'], row['unit'], 0, war) for row in due)
    if not events:
        return
    own_rng = rng is None
    rng = rng or decode_rng(game.seed, sim['regions'][world]['rng'])
    from contextlib import nullcontext
    from ...system.war.lifecycle import _advance_wars_unit
    from ...system.intrigue.runtime import advance_npc_faction
    scope = nullcontext() if world in getattr(game, '_regional_active', {}) else calendar_scope(game, world, year)
    with scope:
        for at, unit, kind, record in sorted(events, key=lambda row:row[:3]):
            view = CalendarGame(game, world, at)
            object.__setattr__(view, 'diplomacy_unit', unit)
            if kind == 0:
                news.extend(_advance_wars_unit(host._dependencies.war.lifecycle, view, rng, campaigns=[record]))
            elif kind == 1:
                host._pressure_weak_npc_powers(view, rng, news)
            else:
                advance_npc_faction(host._dependencies.intrigue.runtime, view, rng, record['faction'], news)
    if own_rng:
        sim['regions'][world]['rng'] = encode_rng(rng)


def synchronize(host, game, targets, *, end=None, news=None, _origin=False):
    ensure(host, game)
    end = game.player.age if end is None else end
    if end > game.player.age:
        raise ValueError('不能结算尚未发生的年份')
    active = getattr(game, '_regional_active', {})
    selected = [w for w in closure(host, game, targets) if w not in active]
    if not selected:
        return
    clocks = game.world_simulation['regions']
    for world in selected:
        initialize_region(host, game, world)
        catch_up_arrivals(host, game, world, news if news is not None else [])
    start = min(clocks[w]['year'] for w in selected)
    if start >= end:
        from ...system.economy.deferred_settlement import apply
        for world in selected:
            apply(CalendarGame(game, world, end), world, end)
            settle_pending_units(host, game, world, end, news if news is not None else [])
        for world in selected:
            apply(CalendarGame(game, world, end), world, end)
        return
    messages = news if news is not None else []
    for year in range(start + 1, end + 1):
        selected = [w for w in closure(host, game, targets) if w not in active]
        for world in selected:
            initialize_region(host, game, world)
            if clocks[world]['year'] < year - 1:
                synchronize(host, game, [world], end=year-1, news=messages)
            if clocks[world]['year'] < year:
                tick(host, game, world, year, messages)
        added = [w for w in closure(host, game, targets) if w not in active and clocks[w]['year'] < year]
        if added:
            synchronize(host, game, added, end=year, news=messages)
    sim = game.world_simulation
    from ...system.economy.deferred_settlement import apply
    for world in selected:
        catch_up_arrivals(host, game, world, messages)
        apply(CalendarGame(game, world, end), world, end)
        settle_pending_units(host, game, world, end, messages)
    for world in selected:
        apply(CalendarGame(game, world, end), world, end)
    sim['revision'] += 1
    sim['recent'].append(dict(worlds=selected, start=start, end=end))
    del sim['recent'][:-16]


def advance(host, game, news):
    ensure(host, game, baseline=game.player.age - 1)
    if game.player.world in {'lost', 'rift'}:
        spans = game.world_simulation.setdefault('space_years', [])
        year = game.player.age
        if spans and spans[-1][1] == year-1:
            spans[-1][1] = year
        elif not spans or spans[-1][1] < year:
            spans.append([year, year])
    previous = game.pending_event
    synchronize(host, game, important_worlds(game), news=news)
    if previous is None and game.pending_event is not None:
        game._regional_notice = game.pending_event
        game.pending_event = None

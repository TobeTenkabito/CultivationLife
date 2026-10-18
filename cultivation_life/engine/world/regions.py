"""Lazy regional years on original state, committed by the enclosing save command.

No yearly deepcopy or regional save exists. The locked command owns its loaded
working game and atomically commits calendars, people, goods and task receipts.
Connected regions advance in chronological, stable order before external tasks.
"""
import random
from ...content_registry import WORLD_SYSTEMS
from ...regional_context import CalendarGame
from ...runtime import encode_rng, decode_rng
from ...system.economy import state, caravans, organizations


def worlds():
    return {w for w, p in WORLD_SYSTEMS['world_profiles'].items() if p['tier'] > 0}


def attach(host, game):
    game._synchronize_regions = lambda working, targets: synchronize(host, working, targets)


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
    """Conservative causal edges, including possible native NPC ascension.

Human NPCs can ascend during a deferred interval. These native destinations
must share a clock, otherwise arrival would rewrite an already simulated past.
This explicit cost replaces the prototype's unsupported-migration assertion.
"""
    known = worlds()
    edges = []
    for path in ('dao', 'demonic', 'monster', 'ghost', 'buddhist', 'sage'):
        target = host._ascension_destination(path)
        if target in known:
            edges.append({'human', target})
    for home, alliances in game.merchant_state.get('worlds', {}).items():
        for alliance in alliances:
            if alliance.get('cross_world'):
                edges.append({home, alliance.get('home_world', home), *alliance.get('linked_worlds', [])} & known)
    for route in game.economy_v2.get('network', {}).get('routes', {}).values():
        edges.append({route['home'], route['branch']})
    for home, transport in game.economy_v2.get('transport', {}).get('worlds', {}).items():
        for fleet in transport['fleets'].values():
            trip = fleet.get('cross_trip')
            if trip:
                edges.append({home, trip['destination'], *trip.get('path', [])} & known)
    return edges


def important_worlds(game):
    known = worlds()
    result = {game.player.world} & known
    if game.family:
        result.add(game.family.world)
    result.update(n.world for n in game.relationship_npcs.values() if n.alive)
    for row in [game.player.master, game.player.dao_companion, *game.player.dao_friends,
                *game.player.disciples, *game.player.concubines, *game.player.offspring]:
        if row and row.get('alive', True) and row.get('world') in known:
            result.add(row['world'])
    for order in game.merchant_state.get('posted', []):
        if order['status'] in {'open', 'working'}:
            result.update({order['world'], order['source_world']} & known)
    for war in game.wars:
        waiting_goods = any(n > 0 for side in war.get('logistics', {}).get('sides', {}).values()
                            for n in side.get('items', {}).values())
        if war['status'] in {'active', 'peace_ready', 'withdrawing'} or waiting_goods:
            result.add(war['world'])
            result.update(s['world'] for s in war.get('logistics', {}).get('sides', {}).values() if s.get('world') in known)
    for war in game.strategic_war_state.get('wars', []):
        if isinstance(war, dict) and war.get('status') not in {'ended', 'completed', 'cancelled'}:
            result.add(war['world'])
    runtime = game.heavens_state.get('runtime', {})
    # Civilian discovery can select an original human resident at the next
    # century window. Its life/finance clock must precede that selection;
    # an existing survey also keeps its departure society current.
    if game.player.world not in {'lost', 'rift'} and runtime and (game.heavens_state.get('generation_enabled') or
                    any(runtime.get(key, {}).get('survey', {}).get('status') == 'active'
                        for key in ('ruins', 'mirror') if isinstance(runtime.get(key), dict))):
        result.add('human')
    campaign = runtime.get('campaign')
    frontier = runtime.get('frontier')
    if (campaign and campaign.get('status') not in {'idle', 'withdrawn', 'completed'}) or (frontier and frontier.get('status') == 'active'):
        result.update({'human', 'demon', 'spirit'})
    # Existing research/migration/site tasks can touch several upper-world
    # authorities. Keep their endpoint societies live until their task closes.
    if runtime.get('sea_echo') or runtime.get('contacts'):
        result.update({'celestial', 'asura', 'nether', 'reincarnation'})
    result.update(game.upper_institutions)
    if game.heavenly_court:
        result.add('celestial')
    return result & known


def closure(host, game, targets):
    selected = set(targets) & worlds()
    edges = dependencies(host, game)
    while True:
        previous = set(selected)
        for edge in edges:
            if selected & edge:
                selected.update(edge)
        if selected == previous:
            return sorted(selected)


def initialize_region(host, game, world):
    clock = game.world_simulation['regions'][world]
    if clock['initialized']:
        return
    view = CalendarGame(game, world, clock['year'])
    # Adoption at the baseline creates no historical income and resurrects none.
    organizations.ensure_organizations(view, host.maps)
    caravans.ensure_caravans(view, host.maps, _world=world, _linked=False)
    clock['initialized'] = True


def tick(host, game, world, year, news):
    clock = game.world_simulation['regions'][world]
    assert year == clock['year'] + 1
    view = CalendarGame(game, world, year)
    rng = decode_rng(game.seed, clock['rng'])
    state.advance_economy(view)
    caravans.advance_caravans(view, host.maps)
    organizations.advance_organizations(view, host.maps)
    news.extend(host._annual_sect_update(view, rng, personal=False))
    news.extend(host._annual_world_npc_update(view, rng))
    host._advance_guixu_calendar(view, rng, news)
    from ...system.monster_civilizations.core import advance_year
    advance_year(view)
    from ...system.intrigue.custody import advance_prison_year
    advance_prison_year(view)
    clock.update(year=year, rng=encode_rng(rng))


def synchronize(host, game, targets, *, end=None, news=None):
    ensure(host, game)
    end = game.player.age if end is None else end
    if end > game.player.age:
        raise ValueError('不能结算尚未发生的年份')
    selected = closure(host, game, targets)
    if not selected:
        return
    clocks = game.world_simulation['regions']
    for world in selected:
        initialize_region(host, game, world)
    start = min(clocks[w]['year'] for w in selected)
    if start >= end:
        return
    messages = news if news is not None else []
    for year in range(start + 1, end + 1):
        for world in selected:
            if clocks[world]['year'] < year:
                tick(host, game, world, year, messages)
    sim = game.world_simulation
    sim['revision'] += 1
    sim['recent'].append(dict(worlds=selected, start=start, end=end))
    del sim['recent'][:-16]


def advance(host, game, news):
    ensure(host, game, baseline=game.player.age - 1)
    previous = game.pending_event
    synchronize(host, game, important_worlds(game), news=news)
    if previous is None and game.pending_event is not None:
        game._regional_notice = game.pending_event
        game.pending_event = None

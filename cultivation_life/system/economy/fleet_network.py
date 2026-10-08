"""Fleet ownership and regional treasuries. No player or individual NPC movement."""
from ...content_registry import WORLD_SYSTEMS, REALMS
from ...rules import expected_combat_power
from .ledger import account, balance, transfer_value


def alliance_at(game, world, identity):
    rows = game.merchant_state.get('worlds', {}).get(world, [])
    return next((a for a in rows if a['id'] == identity), None) or next((a for a in rows if a.get('network_id') == identity), None)


def member_of(game, alliance):
    member = game.merchant_state.get('membership') or {}
    issuer = alliance_at(game, member.get('world'), member.get('alliance_id'))
    return bool(issuer and alliance and issuer.get('network_id', issuer['id']) == alliance.get('network_id', alliance['id'])
                and (member['world'] == alliance['world'] or alliance['cross_world']))


def owner_key(fleet):
    kind = fleet.get('owner_kind', 'alliance')
    identity = fleet.get('owner_id', fleet['alliance_id'])
    if kind == 'alliance':
        return f'alliance:{fleet["world"]}:{identity}'
    if kind in {'sect', 'family'}:
        return f'organization:{kind}:{identity}'
    return 'player' if fleet.get('player_controlled') else f'background:{fleet["world"]}'


def fleet_limit(kind, alliance=None):
    return 3 * (1 + len(alliance['offices'])) if kind == 'alliance' and alliance else {'sect': 2, 'family': 1, 'independent': 1}.get(kind, 0)


def active_fleets(game, world, kind, identity):
    rows = game.economy_v2.get('transport', {}).get('worlds', {}).get(world, {}).get('fleets', {})
    return [f for f in rows.values() if f['status'] != 'retired'
            and f.get('owner_kind', 'alliance') == kind and f.get('owner_id', f['alliance_id']) == identity]


def guard_required(world):
    tier = max(1, int(WORLD_SYSTEMS['world_profiles'][world]['tier']))
    return max(100, round(expected_combat_power(tier + 1, 1) * 2))


def new_fleet(game, region, world, identity, kind, location, name, *, identifier=None, player=False):
    if identifier is None:
        region['sequence'] = region.get('sequence', 0) + 1
        identifier = f'{world}:fleet:{region["sequence"]}'
    fleet = dict(id=identifier, alliance_id=identity if kind == 'alliance' else '',
        owner_kind=kind, owner_id=identity, player_controlled=player, pledged=False,
        world=world, name=name, location=location, status='waiting', capacity=24,
        investment=0, profit=0, dividends=0, voyages=0, delivered=0, lost=0,
        loss_streak=0, idle_years=0, cargo=None, operating_costs=0,
        guard_power=guard_required(world) if kind == 'alliance' else 0,
        next_departure=max(game.player.age, game.economy_v2['last_year']) + 1,
        last_result='等待出资与本地商机')
    region['fleets'][identifier] = fleet
    account(game, f'caravan:{identifier}')
    return fleet


def ensure_network(game, maps):
    """Adoption preserves IDs, cargo, cash and RNG; funding occurs on annual ticks."""
    transport = game.economy_v2['transport']
    changed = False
    for world, region in transport['worlds'].items():
        if region.get('ownership_version') == 2:
            continue
        region.update(ownership_version=2, sequence=0)
        for fleet in region['fleets'].values():
            fleet.update(owner_kind='alliance', owner_id=fleet['alliance_id'], player_controlled=False,
                         pledged=False, guard_power=guard_required(world))
        for alliance in game.merchant_state['worlds'][world]:
            # Three initial fleets per alliance; later expansion remains financed.
            for index in (2, 3):
                new_fleet(game, region, world, alliance['id'], 'alliance', alliance['hq'],
                          f'{alliance["name"]}第{index}商队', identifier=f'{world}:{alliance["id"]}:{index}')
        sites = [r['id'] for r in maps.worlds[world]['locations'] if not r.get('min_realm_index')]
        for index in range(3):
            new_fleet(game, region, world, f'free-{index}', 'independent', sites[index % len(sites)], f'散修行商第{index + 1}队')
        changed = True
    return changed


def owner_sites(game, maps, fleet):
    world, kind = fleet['world'], fleet.get('owner_kind', 'alliance')
    if kind == 'alliance':
        return alliance_at(game, world, fleet['alliance_id'])
    if kind in {'sect', 'family'}:
        entity = game.family if kind == 'family' else game.sects.get(fleet['owner_id'])
        if not entity or entity.extinct or entity.world != world:
            return None
    sites = [r['id'] for r in maps.worlds[world]['locations'] if not r.get('min_realm_index')]
    return dict(hq=fleet['location'], offices=[dict(location_id=s) for s in sites[:8]], reserves=balance(game, owner_key(fleet)))


def seed_organization_fleets(game, maps, world, region):
    from .organizations import register
    from ..faction_geography import faction_site
    if game.player.age >= region.get('next_expansion', game.economy_v2['base_year'] + 10):
        region['next_expansion'] = game.player.age + 10
        for alliance in game.merchant_state['worlds'].get(world, []):
            if (not alliance.get('player_owned') and alliance['reserves'] >= 100000
                    and len(active_fleets(game, world, 'alliance', alliance['id'])) < fleet_limit('alliance', alliance)):
                new_fleet(game, region, world, alliance['id'], 'alliance', alliance['hq'], f'{alliance["name"]}新设商队')
        independent = [f for f in region['fleets'].values() if f.get('owner_kind') == 'independent' and f['status'] != 'retired' and not f.get('player_controlled')]
        if len(independent) < 3:
            sites = [r['id'] for r in maps.worlds[world]['locations'] if not r.get('min_realm_index')]
            new_fleet(game, region, world, f'free-{region.get("sequence", 0) + 1}', 'independent',
                      sites[region.get('sequence', 0) % len(sites)], '新来散修行商')
        # Keep a small graveyard, not centuries of empty fleet objects/accounts.
        retired = [f for f in region['fleets'].values() if f['status'] == 'retired' and not f.get('cross_trip')]
        for fleet in retired[:-24]:
            cash = f'caravan:{fleet["id"]}'
            if balance(game, cash) == 0:
                del region['fleets'][fleet['id']]
                del game.economy_v2['accounts'][cash]
                escrow = f'freight:{fleet["id"]}'
                if escrow in game.economy_v2['accounts'] and balance(game, escrow) == 0:
                    del game.economy_v2['accounts'][escrow]
    for entity in [*game.sects.values(), *([game.family] if game.family else [])]:
        if entity.extinct or entity.kind == 'institution' or entity.world != world:
            continue
        kind = 'family' if entity is game.family else 'sect'
        mark = f'{kind}:{entity.id}'
        if mark in region.setdefault('adopted_organizations', []):
            continue
        register(game, kind, entity.id, world)
        if balance(game, f'organization:{kind}:{entity.id}') < 10000:
            continue
        region['adopted_organizations'].append(mark)
        existing = len(active_fleets(game, world, kind, entity.id))
        for index in range(max(0, fleet_limit(kind) - existing)):
            new_fleet(game, region, world, entity.id, kind, faction_site(entity)['id'], f'{entity.name}商队{index + 1}')


def route_key(identity, first, second):
    return '|'.join([identity, *sorted([first, second])])


def routes(game):
    return game.economy_v2.get('network', {}).get('routes', {})


def ensure_routes(game):
    if not game.merchant_state.get('worlds'):
        return False  # Independent-space starts have no adopted merchant society yet.
    if 'network' in game.economy_v2:
        return False
    network = game.economy_v2['network'] = dict(last_year=max(game.player.age, game.economy_v2['last_year']), routes={})
    for world, alliances in game.merchant_state['worlds'].items():
        for alliance in alliances:
            if not alliance['cross_world'] or alliance['home_world'] != world:
                continue
            for destination in alliance['linked_worlds']:
                if destination != world and alliance_at(game, destination, alliance['id']):
                    key = route_key(alliance['id'], world, destination)
                    network['routes'][key] = dict(alliance_id=alliance['id'], home=world, branch=destination,
                        open=True, built=True, maintenance=0, paid=0, shortfall=0, last_year=network['last_year'])
    return True


def route_open(game, alliance, destination):
    return bool(route_path(game, alliance, destination))


def qualified_site(game, alliance):
    if not alliance:
        return False
    if alliance['world'] == alliance['home_world']:
        return (WORLD_SYSTEMS['world_profiles'][alliance['world']]['tier'] >= 2
                and alliance.get('chief_realm', 0) >= 8)
    cap = int(WORLD_SYSTEMS['world_profiles'][alliance['world']]['npc_realm_cap'])
    return alliance['leader']['realm_index'] >= cap - 1 and alliance['leader'].get('alive', True)


def route_path(game, alliance, destination):
    """Read-only shortest open physical path; network identity is not a passage."""
    if not alliance or destination not in alliance['linked_worlds'] or not alliance_at(game, destination, alliance.get('network_id', alliance['id'])):
        return []
    if destination == alliance['world']:
        return [destination]
    network = game.economy_v2.get('network')
    if network is None:
        return [alliance['world'], destination]  # Legacy adoption.
    home = alliance['home_world']
    identity = alliance.get('network_id', alliance['id'])
    headquarters = alliance_at(game, home, identity)
    if not qualified_site(game, headquarters) or not qualified_site(game, alliance):
        return []
    queue, seen = [[alliance['world']]], {alliance['world']}
    for path in queue:
        for route in sorted(routes(game).values(), key=lambda r: route_key(r['alliance_id'], r['home'], r['branch'])):
            if route['alliance_id'] != identity or not route['open'] or path[-1] not in {route['home'], route['branch']}:
                continue
            other = route['branch'] if path[-1] == route['home'] else route['home']
            if other in seen or not qualified_site(game, alliance_at(game, other, identity)):
                continue
            if other == destination:
                return [*path, other]
            seen.add(other)
            queue.append([*path, other])
    return []


def leg_years(first, second):
    return 3 + abs(WORLD_SYSTEMS['world_profiles'][first]['tier'] - WORLD_SYSTEMS['world_profiles'][second]['tier'])


def maintenance_cost(game, maps, world, location):
    from .state import ensure_regional_market
    ensure_regional_market(game, maps, world, location)
    return maintenance_quote(game, world, location)


def maintenance_quote(game, world, location):
    goods = game.economy_v2['markets'].get(f'{world}:{location}', {}).get('commodities', {}).values()
    rows = [r for r in goods if not r.get('imported')]
    multiplier = sum(r['price'] / r['reference'] for r in rows) / len(rows) if rows else 1
    tier = WORLD_SYSTEMS['world_profiles'][world]['tier']
    return max(1, round(25000 * tier ** 2 * multiplier))


def advance_network(game, maps):
    ensure_routes(game)
    if 'network' not in game.economy_v2:
        return
    network = game.economy_v2['network']
    if game.player.age <= network['last_year']:
        return
    network['last_year'] = game.player.age
    for route in routes(game).values():
        endpoint = alliance_at(game, route['home'], route['alliance_id'])
        home = alliance_at(game, endpoint['home_world'], route['alliance_id']) if endpoint else None
        region = game.economy_v2.get('transport', {}).get('worlds', {}).get(home['world']) if home else None
        years = max(0, game.player.age - max(route['last_year'], region['last_year'])) if region else 0
        route['last_year'] = game.player.age
        if not years:
            continue
        branch = alliance_at(game, route['branch'], route['alliance_id'])
        if not home or not branch:
            route['open'] = False
            continue
        cost = maintenance_cost(game, maps, home['world'], home['hq'])
        source = f'alliance:{home["world"]}:{home["id"]}'
        if not route['open']:
            # Closed years accrue no bill. AI only repairs previously built links,
            # retaining two years' network upkeep after the repair payment.
            count = sum(r['alliance_id'] == route['alliance_id'] for r in routes(game).values())
            if (not home.get('player_owned') and (route.get('built') or route['paid'])
                    and qualified_site(game, home) and qualified_site(game, endpoint) and qualified_site(game, branch)
                    and balance(game, source) >= cost * (1 + 2 * count)):
                transfer_value(game, source, f'background:{home["world"]}', cost, '商盟恢复逆灵通道')
                route.update(open=True, built=True, shortfall=0, maintenance=cost)
            continue
        due = cost * years
        paid = min(due, balance(game, source))
        transfer_value(game, source, f'background:{home["world"]}', paid, '逆灵通道年度原料维护')
        route.update(built=True, maintenance=cost, paid=route['paid'] + paid, shortfall=due - paid)
        if paid < due:
            route['open'] = False


def leader_record(game, identity, title, realm, *, world=None):
    """A newly contracted local officer, never a copied player or existing NPC."""
    from ...models import SectNpc
    return SectNpc(identity, title, '盟务主事', realm, REALMS[realm].layers, 100, None, world=world or game.player.world).to_dict()

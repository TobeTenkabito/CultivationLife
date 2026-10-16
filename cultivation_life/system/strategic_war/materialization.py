"""Finite first encounters with names from the existing faction directory."""
from ...content_registry import RACE_SYSTEMS, RACE_DEFINITIONS
from ...models import SectState
from ..economy.state import ensure_regional_market
from ..economy.organization_accounts import register, key
from ..economy.ledger import balance, transfer_value
from .rules import organizations, local_races


def materialize(deps, game, world, race, rng):
    if race not in local_races(world):
        return None
    # Lifetime bound: an extinct or encountered organization never gets erased
    # or rerolled to make room. Chunked cold storage is a separate later phase.
    if sum(o.founded_by_npc for o in game.sects.values()) >= 12:
        return None
    raw = next((r for r in RACE_SYSTEMS.get('faction_presets', {}).get(race, [])
                if r.get('world') == world and r['id'] not in game.sects), None)
    if not raw:
        serial = 1 + len(game.strategic_war_state.get('materialized',{}))
        raw = dict(id=f'levy-{world}-{race}-{serial}', world=world,
                   name=f"{RACE_DEFINITIONS[race]['name']}·{rng.choice(['青崖','栖霞','归云','照夜'])}家族{serial}", kind='family')
    forbidden = {o.location_id for o in organizations(game, world)
                 if o.founded_by_player or o.id == game.player.faction_id or o is game.family}
    if game.player.world == world:
        forbidden.add(game.player.location_id)
    forbidden.update(e['location'] for e in game.economy_v2.get('estates', {}).values()
                     if e.get('owner_kind') == 'player' and e.get('world') == world)
    safe = [s for s in deps.maps.worlds[world]['locations'] if not s.get('min_realm_index', 0) and s['id'] not in forbidden]
    if not safe:
        return None
    location = rng.choice(safe)['id']
    ensure_regional_market(game, deps.maps, world, location)
    source = f'market:{world}:{location}'
    grant = min(balance(game, source)//100, 1000000)
    if grant <= 0:
        return None
    org = SectState(raw['id'], raw['name'], world, [], kind=raw.get('kind','sect'),
                    path=raw.get('path','dao'), allegiance_race=race, location_id=location, founded_by_npc=True)
    for _ in range(6):
        person = deps.recruit(org, game.player.age, rng)
        if person:
            person.location_id, person.faction_id = location, org.id
    if not org.npcs:
        return None
    org.founder_npc_id = org.npcs[0].id
    game.sects[org.id] = org
    # Dynamic families in game.sects keep the existing canonical sect treasury;
    # later joining the family uses the existing alias handover transaction.
    register(game, 'sect', org.id, world)
    transfer_value(game, source, key('sect', org.id), grant, '当地宗族组织首次成资，扣原市场有限周转金')
    game.strategic_war_state.setdefault('materialized', {})[org.id] = dict(
        world=world, location=location, source=source, paid=grant, age=game.player.age)
    return org

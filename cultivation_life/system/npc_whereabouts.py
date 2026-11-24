"""Annual local movements and dated answers to a player's letters."""
import random

from ..content_registry import CONTENT_DOCUMENTS, WORLD_NPC_TEMPLATES
from ..dungeon_schema import empty
from ..npc_custody import is_free
from ..person_assignments import research_assignment
from .faction_geography import person_site


def can_roam(game, npc):
    if (not is_free(npc) or npc.custody or npc.faction_id or npc.world in {'lost', 'rift'}
            or npc.id in game.intrigue_state.get('npc_prisons', {})
            or any(r.get('id') == npc.id for r in game.player.party)):
        return False
    active = game.dungeon_state.get('active')
    site = game.dungeon_state.get('instances', {}).get(active, {})
    if any(r.get('npc_id') == npc.id and r['state'] in {'joined', 'hostile'}
           for r in site.get('roles', {}).values()):
        return False
    return not research_assignment(game, npc.id)


def settle_year(game, npc, roads):
    if npc.id not in WORLD_NPC_TEMPLATES and npc.id not in game.notable_npcs:
        return
    if not can_roam(game, npc):
        npc.roaming_years = 0
        return
    if not npc.location_id:
        # An unplaced independent person first acquires a real stop on the local calendar.
        if person_site(game, npc):
            return
        places = CONTENT_DOCUMENTS['maps.json']['worlds'].get(npc.world, {}).get('locations', ())
        allowed = [s['id'] for s in places if npc.realm_index >= s.get('min_realm_index', 0)]
        if allowed:
            npc.location_id = random.Random(f'first-stop:{game.seed}:{npc.id}:{npc.world}').choice(allowed)
        npc.roaming_years = 0
        return
    npc.roaming_years += 1
    # Stable for this stay, including after reloading or replaying a regional year.
    start = npc.age - npc.roaming_years
    rng = random.Random(f'roam:{game.seed}:{npc.id}:{npc.world}:{npc.location_id}:{start}')
    rest = rng.randint(2, 5)
    if npc.roaming_years <= rest:
        return
    neighbors = roads(npc.world, npc.location_id, npc.realm_index)
    if neighbors:
        dest, years = rng.choice(neighbors)
        if npc.roaming_years >= rest + years:
            npc.location_id = dest
            npc.roaming_years = 0


def map_entry(world, site):
    locations = CONTENT_DOCUMENTS['maps.json']['worlds'].get(world, {}).get('locations', ())
    return next((s for s in locations if s['id'] == site), {})


def map_name(world, site):
    return map_entry(world, site).get('name')


def reply_index(game):
    return {(m['sender_id'], m['world']): m for m in game.dungeon_state.get('mail', ())
            if m['status'] == 'whereabouts'}


def last_reply(game, npc, replies=None):
    if replies is not None:
        return replies.get((npc.id, npc.world))
    return next((m for m in reversed(game.dungeon_state.get('mail', ()))
                 if m['status'] == 'whereabouts' and m['sender_id'] == npc.id and m['world'] == npc.world), None)


def knowledge(game, npc, available, replies=None):
    if not available or not is_free(npc) or npc.custody or npc.id in game.intrigue_state.get('npc_prisons', {}):
        return None, '行踪未明'
    site = person_site(game, npc)
    if site and site == game.player.location_id:
        return site, f'当面所见 · {map_name(npc.world, site) or "就在此地"}'
    reply = last_reply(game, npc, replies)
    if reply:
        site = reply['location_id']
        return site, f'{reply["age"]:g} 岁时回信 · {map_name(npc.world, site) or "尚在途中"}'
    return None, '行踪未明'


def letter_reason(game, npc, blocked, replies=None):
    if blocked:
        return blocked
    if game.player.world in {'lost', 'rift'} or game.map_journey or game.dungeon_state.get('active') or game.guixu_state.get('player_session'):
        return '待回到当地，再寄传书'
    reply = last_reply(game, npc, replies)
    return '本年回信已送至信箱' if reply and reply['age'] == game.player.age else ''


def send_reply(game, identity, world, expected_age):
    from ..models import SectNpc
    from ..relationship_records import find_person
    from ..spatial_people import contact_blocked
    if type(expected_age) not in (int, float) or expected_age != game.player.age or world != game.player.world:
        raise ValueError('这封传书已过时，请重新寄信')
    if not isinstance(identity, str) or not identity:
        raise ValueError('请选择收信人')
    npc = find_person(game, identity, include_inactive=True)
    if not npc:
        raw = next((r['npc'] for r in game.encounter_npc_cache if (r.get('npc') or {}).get('id') == identity), None)
        npc = SectNpc.from_dict(raw) if raw else None
    if not npc:
        raise ValueError('此人已不在已知人物名册中')
    reason = letter_reason(game, npc, contact_blocked(game, npc))
    if reason:
        raise ValueError(reason)
    site = person_site(game, npc)
    name = map_name(npc.world, site)
    age = game.player.age
    body = f'来信已收。我眼下在{name}落脚。道友若途经此地，可来寻我。' if name else '来信已收。眼下尚无定所，待我落脚，道友再来信相询。'
    if not game.dungeon_state:
        game.dungeon_state = empty()
    mail = game.dungeon_state['mail']
    if len(mail) >= 20000:
        raise ValueError('信箱已满')
    mail.append(dict(id=f'whereabouts:{npc.world}:{npc.id}:{age}', sender=npc.name, sender_id=npc.id,
                     status='whereabouts', world=npc.world, location_id=site if name else None,
                     title='答道友问行踪', body=body, unread=True, age=age))

"""Player selection and deterministic, once-only original-person NPC preparation."""
import hashlib
import random
from functools import lru_cache

from ..duel_technique_schema import LIMIT, validate_ids
from ..content_registry import TECHNIQUE_CATALOG, restricted_acquisition
from ..rules import can_player_practice_technique, can_practice_technique, combat_requirement_met, qi_levels
from .combat.actor_state import read, _write


def player_reason(player, book):
    if book.category != 'spiritual':
        return '只有已装备的普通战斗功法可选入斗法'
    if not book.active_in(player.world):
        return '此功法在当前界面不生效'
    if not can_player_practice_technique(player, book):
        return '灵根条件不符'
    if book.doctrine_id and player.realm_index < book.grade:
        return '境界尚不足以配置此道统功法'
    if player.body_training < book.required_body_training:
        return '炼体条件不足'
    if book.requires_immortal_power and not player.immortal_power_converted:
        return '尚未完成仙灵力转化'
    if not combat_requirement_met(book.combat_requirements, qi_levels(player)):
        return '气等级不足，战斗功法当前失效'
    return ''


def select(player, identity, *, remove=False):
    chosen = validate_ids(player.duel_technique_ids)
    if remove:
        if identity not in chosen:
            raise ValueError('这部功法未选入斗法')
        chosen.remove(identity)
    else:
        book = next((t for t in player.combat_techniques if t.id == identity), None)
        if book is None:
            raise ValueError('须先成功装备为战斗功法，才能选入斗法')
        if reason := player_reason(player, book):
            raise ValueError(reason)
        if identity in chosen:
            raise ValueError('这部功法已经选入斗法')
        if len(chosen) >= LIMIT:
            raise ValueError('最多装备7部斗法功法，请先移出一部')
        chosen.append(identity)
    player.duel_technique_ids = chosen


def player_books(player):
    selected = validate_ids(player.duel_technique_ids)
    equipped = {t.id: t for t in player.combat_techniques}
    return [equipped[key] for key in selected if key in equipped and not player_reason(player, equipped[key])]


def npc_eligible(npc, book):
    # Some scripted combat actors have no recorded affinity. They can use
    # unconditional neutral books, but must never gain an invented root.
    try:
        root_allowed = can_practice_technique(read(npc, 'spirit_root', ''), book)
    except KeyError:
        root_allowed = False
    return (book.category == 'spiritual' and 1 <= book.grade <= read(npc, 'realm_index', read(npc, 'target_realm_index', 0))
            and book.active_in(read(npc, 'world', ''))
            and root_allowed
            and book.required_body_training <= (read(npc, 'body_training', 0) or 0)
            and (not book.requires_immortal_power or (read(npc, 'transcendence') or {}).get('conversion', 0) >= 1))


def target_count(rank, rng):
    if rank <= 0:
        return 0
    if rank >= 6:
        return LIMIT
    floor = 5 if rank == 5 else 3 if rank == 4 else 1
    probability = {1: .18, 2: .32, 3: .48, 4: .65, 5: .85}[rank]
    return floor + sum(rng.random() < probability for _ in range(LIMIT - floor))


@lru_cache(maxsize=512)
def _pool(catalog_id, world, root, rank, body, converted):
    facts = dict(world=world, spirit_root=root, realm_index=rank, body_training=body,
                 transcendence={'conversion': 1 if converted else 0})
    return tuple(t.id for t in TECHNIQUE_CATALOG.values()
                 if not restricted_acquisition('technique', t.id) and t.element != 'sex' and npc_eligible(facts, t))


def ensure_npc(npc, *, game=None):
    """Only at session/encounter/battle preparation, never in a readonly projector."""
    existing = read(npc, 'duel_technique_ids')
    if existing is not None:
        validate_ids(existing)
        return False
    identity = read(npc, 'id') or read(npc, 'npc_id')
    if not identity or read(npc, 'kind') in {'artifact', 'formation', 'environment', 'mechanical', 'corpse', 'beast', 'puppet'}:
        return False
    rank = int(read(npc, 'realm_index', read(npc, 'target_realm_index', 0)))
    # Existing identities anchor the stream; seeing another person or battling
    # in another order never consumes game.rng_state or changes this person's draw.
    rng = random.Random(int.from_bytes(hashlib.sha256(('duel-v1:' + str(identity)).encode()).digest(), 'big'))
    count = target_count(rank, rng)
    from .npc_techniques import levels, resolve
    facts = levels(npc)
    preferred = [read(npc, 'technique_slots', {}).get('combat'), *facts]
    chosen = []
    for key in preferred:
        book = resolve(game, key) if game is not None and key else TECHNIQUE_CATALOG.get(key)
        if key and key not in chosen and book and npc_eligible(npc, book) and len(chosen) < count:
            chosen.append(key)
    candidates = list(_pool(id(TECHNIQUE_CATALOG), read(npc, 'world', ''), read(npc, 'spirit_root', ''), rank,
                            read(npc, 'body_training', 0) or 0, (read(npc, 'transcendence') or {}).get('conversion', 0) >= 1))
    rng.shuffle(candidates)
    candidates.sort(key=lambda key: (TECHNIQUE_CATALOG[key].path == read(npc, 'path', 'dao'),
                                     TECHNIQUE_CATALOG[key].grade), reverse=True)
    for key in candidates:
        if len(chosen) >= count:
            break
        if key not in chosen:
            chosen.append(key)
    for key in chosen:
        facts.setdefault(key, 1)
    _write(npc, 'technique_levels', facts)
    _write(npc, 'duel_technique_ids', chosen)
    return True


def npc_books(game, npc):
    from .npc_techniques import resolve, levels
    selected = validate_ids(read(npc, 'duel_technique_ids'), uninitialized=True) or []
    facts = levels(npc)
    books = []
    for key in selected:
        book = resolve(game, key)
        if key in facts and book and npc_eligible(npc, book):
            book.level = facts[key]
            books.append(book)
    return books


def prepare_visible(game):
    """Freeze already exposed local contacts before time/commands can change rank."""
    from ..spatial_people import accessible
    people = [*(game.family.npcs if game.family else []), *game.world_npcs.values(), *game.notable_npcs.values()]
    people.extend(npc for sect in game.sects.values() if sect.kind == 'institution' and sect.world == game.player.world
                  for npc in sect.npcs)
    from ..relationship_records import find_person
    for row in [game.player.master, game.player.dao_companion, *game.player.dao_friends,
                *game.player.disciples, *game.player.disciple_requests, *game.player.concubines, *game.player.prisoners]:
        if row and (person := find_person(game, row.get('id'), include_inactive=True)) is not None:
            people.append(person)
    if game.player.concubine_status:
        person = find_person(game, game.player.concubine_status.get('owner_id'), include_inactive=True)
        if person is not None:
            people.append(person)
    if game.player.world in {'lost', 'rift'}:
        from ..spatial_people import people as scene_people
        people.extend(scene_people(game))
    if game.player.faction_id in game.sects:
        people.extend(game.sects[game.player.faction_id].npcs)
    people.extend(row['npc'] for row in game.encounter_npc_cache if row.get('seen_count', 0))
    changed, seen = False, set()
    for npc in people:
        key = read(npc, 'id')
        if key in seen or read(npc, 'duel_technique_ids') is not None or not read(npc, 'alive', True):
            continue
        if read(npc, 'world') != game.player.world or not accessible(game, npc):
            continue
        from ..person_assignments import deployment_assignment
        deployment = deployment_assignment(game, key)
        if deployment and not deployment.get('observed', False):
            continue
        seen.add(key)
        changed = ensure_npc(npc, game=game) or changed
    return changed


def public(player):
    selected = validate_ids(player.duel_technique_ids)
    rows, seen = [], set()
    for book in player.combat_techniques:
        if book.id in seen:
            continue
        seen.add(book.id)
        reason = player_reason(player, book)
        rows.append(dict(id=book.id, name=book.name, level=book.level, selected=book.id in selected,
                         active=not reason, reason=reason, description=book.description,
                         has_effect=bool(book.combat_effect)))
    return dict(limit=LIMIT, selected=list(selected), candidates=rows)

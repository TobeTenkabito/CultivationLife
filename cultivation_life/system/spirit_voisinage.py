"""Lower-world adaptations. Their catalog never enters ordinary gift/market pools."""
from dataclasses import replace

from ..content_registry import WORLD_SYSTEMS
from ..models import Technique
from ..rules import learn_technique, add_technique_copy, expected_combat_power
from .combat.contracts import CapabilitySource, VoisinageDefinition
from .doctrine.generation import rng_for


def secondary(world):
    return WORLD_SYSTEMS['world_profiles'].get(world, {}).get('tier') == 2


def catalog(game):
    from .doctrine.provider import ensure
    ensure(game, celestial_context=True)
    worlds = [w for w in WORLD_SYSTEMS['world_profiles'] if secondary(w)]
    result = {}
    for key, definition in game.doctrine_state['definitions'].items():
        base = definition['manuals'][0]
        book = Technique(id='spirit:' + key, name=base['name'] + '·灵域残解',
            path=base.get('path', 'dao'), element=base.get('element', 'neutral'), grade=6,
            hp_bonus=.12, mp_bonus=.18, combat_bonus=expected_combat_power(6, 1) * .04, opportunity_bonus=.12,
            spirit_voisinage_id=key, effective_worlds=worlds,
            sources=base.get('sources', {'spirit': 1}))
        result[book.id] = book
    return result


def offers(game, venue, period):
    if not secondary(game.player.world):
        return []
    rng = rng_for(game.seed, 1, f'spirit-manual:{game.player.world}:{venue}:{period}')
    books = list(catalog(game).values())
    # The draw belongs to a venue opening, never to a search expression.
    return rng.sample(books, rng.choice([0, 0, 1, 1, 2]))


def grant(game, book_id, level=1):
    book = catalog(game).get(book_id)
    if not book:
        raise ValueError('这枚灵域玉简已经失传')
    book.level = max(1, min(9, int(level)))
    known = next((t for t in game.player.known_techniques if t.id == book_id), None)
    if known:
        add_technique_copy(game.player, book, level=book.level)
    else:
        learn_technique(game.player, book)
    return book


def diminished(value):
    """Less than half a tenth of the original; costs use the tiny imitation pool."""
    fields = []
    for field in value.voisinages:
        fields.append(replace(field, id='spirit:' + field.id, name=field.name + '·灵域',
            strength=field.strength * .04, strength_per_level=field.strength_per_level * .04,
            stability=(field.stability if field.stability is not None else field.strength) * .04,
            incursion=(field.incursion if field.incursion is not None else field.strength) * .04,
            authority=(field.authority if field.authority is not None else field.strength) * .04,
            authority_reference=field.authority_reference * .04,
            opening_cost=12, upkeep_cost=4, effect_cost=4, max_investment=2,
            extra_target_cost=0, max_targets=1,
            features=tuple({**f, 'value': f.get('value', 0) * .04} for f in field.features)))
    return CapabilitySource(tuple(fields), value.attainments)


def player_source(game):
    from .immortal_aperture import lower_world, spirit_books, true_realm
    from .doctrine.progression import source
    if not lower_world(game.player):
        return CapabilitySource()
    books = spirit_books(game.player)
    if books:
        book = next((t for t in books if t.id == game.player.spirit_voisinage_manual), books[0])
        catalog(game)
        definition = game.doctrine_state['definitions'].get(book.spirit_voisinage_id)
        if definition:
            level = min(9, book.level)
            field = VoisinageDefinition(**definition['stages'][level - 1]['voisinage'])
            return diminished(CapabilitySource((field,), {book.spirit_voisinage_id: level}))
    if true_realm(game.player) < 9:
        return CapabilitySource()
    record = game.doctrine_state.get('player', {})
    return diminished(source(record, game.doctrine_state.get('definitions', {}), 'celestial'))


def npc_source(game, npc):
    from .combat.npc_lifecycle import read, _write
    import hashlib
    if not secondary(read(npc, 'world')) or not 6 <= read(npc, 'realm_index', 0) <= 8:
        return CapabilitySource()
    identity = str(read(npc, 'id', ''))
    seed = int.from_bytes(hashlib.blake2s(('spirit-book:' + identity).encode(), digest_size=4).digest(), 'big')
    if not identity or seed % 100 >= 3:
        return CapabilitySource()
    books = list(catalog(game).values())
    book = books[(seed // 100) % len(books)]
    state = read(npc, 'transcendence')
    if state is None:
        state = dict(version=1, capacity=0, current=0, conversion=0, resource_link='independent')
        _write(npc, 'transcendence', state)
    state.setdefault('spirit_manual', book.id)
    definition = game.doctrine_state['definitions'][book.spirit_voisinage_id]
    field = VoisinageDefinition(**definition['stages'][3]['voisinage'])
    return diminished(CapabilitySource((field,), {book.spirit_voisinage_id: 4}))

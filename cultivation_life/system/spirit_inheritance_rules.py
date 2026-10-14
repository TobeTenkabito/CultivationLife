"""Pure inheritance plans and bounded local field templates; no save/RNG hooks."""
from dataclasses import replace
from math import ceil, isfinite

from ..content_registry import WORLD_SYSTEMS, CONTENT_DOCUMENTS
from .spirit_sources import definition as source_definition, origin, celestial_definition

AXES = ('stability', 'incursion', 'authority')
EFFECTS = {'strike', 'suppress', 'seal', 'restrict', 'isolate',
           'restore_body', 'restore_spirit', 'restore_field'}
FEATURES = {'fortify', 'opening', 'retaliate', 'sacrifice', 'frugal', 'shelter', 'execution'}
SUFFIXES = {'asura': '魔域', 'nether': '幽域', 'reincarnation': '轮回域'}


def mode(player):
    if player.realm_index < 9:
        return None
    if player.world == 'celestial':
        return 'celestial'
    if player.world not in SUFFIXES:
        return None
    if (player.world == 'asura' and player.path == 'demonic'
            and WORLD_SYSTEMS.get('asura_manifestation', {}).get('enabled')):
        return 'eightfold'
    if player.world == 'nether' and player.path == 'monster' and CONTENT_DOCUMENTS.get('monster_true_forms.json'):
        return 'monster'
    if player.world == 'reincarnation' and player.path == 'ghost' and WORLD_SYSTEMS.get('ghost_cultivation', {}).get('enabled'):
        return 'ghost'
    return 'native'


def key(world, doctrine_id):
    return f'inherited:{world}:{doctrine_id}'


def discount(level):
    return .04 * max(0, min(5, int(level) - 4))


def discounted(cost, level):
    result = dict(cost)
    reduction = discount(level)
    for name in ('opportunity', 'stones', 'traces', 'souls'):
        if name in result:
            result[name] = ceil(result[name] * (1 - reduction))
    result['inheritance_discount'] = reduction
    return result


def plan(game, manual_id):
    book = next((t for t in game.player.known_techniques if t.id == manual_id
                 and t.spirit_voisinage_id), None)
    if not book or book.id != 'spirit:' + book.spirit_voisinage_id:
        raise ValueError('须选择本人已学的灵域残解')
    if book.level < 4:
        raise ValueError('灵域残解须合参至 Lv4 才能承接')
    definition = source_definition(game, book.spirit_voisinage_id)
    if not definition or not definition.get('manuals') or len(definition.get('stages', [])) < 4:
        raise ValueError('原传承目录无效，原记录保留')
    field = definition['stages'][3].get('voisinage')
    if not field:
        raise ValueError('原传承缺少初成领域')
    current_mode = mode(game.player)
    if not current_mode:
        raise ValueError('须亲至三级界面并达到第九阶修为')
    world = game.player.world
    identity = key(world, definition['id'])
    if current_mode == 'celestial':
        saved = definition['id'] in game.doctrine_state.get('player', {}).get('spirit_inheritances', {})
    elif current_mode == 'eightfold':
        saved = 'spirit_inheritance' in game.player.asura_cultivation
    elif current_mode in {'monster', 'ghost'}:
        saved = game.player.world_voisinages.get(world, {}).get('spirit_bindings')
    else:
        saved = identity in game.player.world_voisinages.get(world, {}).get('spirit_inheritances', {})
    if saved:
        raise ValueError('此承接已经完成，原培养保留')
    if current_mode == 'celestial' and not game.player.immortal_power_converted:
        raise ValueError('须先完成仙灵力转化')
    if current_mode == 'eightfold':
        state = game.player.asura_cultivation
        if not state.get('route'):
            raise ValueError('须先完成八部肉身融合')
        if state.get('conversion', 0) < 5:
            raise ValueError('须先完成五重煞元转化')
    target_id = None
    if current_mode == 'monster':
        from .monster_true_form import validate, identity as form_identity
        target_id = form_identity(validate(game.player))
    if current_mode == 'ghost':
        from .ghost_soul_form import validate, identity as form_identity
        target_id = form_identity(validate(game.player))
    celestial = (definition if origin(definition['id']) == 'celestial' else celestial_definition(definition)) if current_mode == 'celestial' else None
    return dict(mode=current_mode, id=identity, manual_id=book.id, doctrine_id=definition['id'],
                origin_world=origin(definition['id']), target_id=target_id, celestial_definition=celestial,
                source_name=definition['name'], source_level=book.level,
                name=field['name'] + ('·' + SUFFIXES[world] if world in SUFFIXES else ''),
                template=template(field), upper_manual=celestial['manuals'][0] if celestial else None)


def template(field):
    weights = [float(field[axis]) for axis in AXES]
    if any(not isfinite(v) or v <= 0 for v in weights):
        raise ValueError('原传承威能无效')
    total = sum(weights)
    kinds = list(dict.fromkeys(e['kind'] for e in field.get('effects', []) if e.get('kind') in EFFECTS))
    if not kinds:
        kinds = [field['effect']] if field.get('effect') in EFFECTS else []
    if not kinds:
        raise ValueError('原传承权能无效')
    first = next((f for f in field.get('features', []) if f.get('kind') in FEATURES), None)
    result = dict(zip(AXES, [v * 3 / total for v in weights]))
    result['effects'] = kinds[:2]
    result['feature'] = {'kind': first['kind'], 'value': min(.15, max(0, float(first['value'])))} if first else None
    return result


def record(plan):
    return {name: plan[name] for name in ('id', 'manual_id', 'doctrine_id', 'source_name', 'source_level', 'name', 'template', 'origin_world')} | {'version': 1}


def valid(data, world):
    """Reject unsupported records without rebuilding or changing their snapshots."""
    try:
        t = data['template']
        weights = [float(t[a]) for a in AXES]
        feature = t.get('feature')
        return (data['version'] == 1 and data['origin_world'] == origin(data['doctrine_id']) and data['origin_world'] is not None
                and data['id'] == key(world, data['doctrine_id'])
                and data['manual_id'] == 'spirit:' + data['doctrine_id']
                and 4 <= data['source_level'] <= 9 and bool(data['name'])
                and all(isfinite(v) and v > 0 for v in weights) and sum(weights) <= 3.000001
                and 1 <= len(t['effects']) <= 2 and set(t['effects']) <= EFFECTS
                and (feature is None or feature['kind'] in FEATURES
                     and isfinite(feature['value']) and 0 <= feature['value'] <= .15))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def definitions(player):
    result = []
    for data in player.world_voisinages.get(player.world, {}).get('spirit_inheritances', {}).values():
        if valid(data, player.world):
            result.append(dict(id=data['id'], name=data['name'], description=f"承接{data['source_name']}，原残解 Lv{data['source_level']}；依本界规则培养。",
                               inherited=True, **data['template']))
    return result


def asura_field(player, field):
    data = player.asura_cultivation.get('spirit_inheritance')
    if not data or not valid(data, 'asura'):
        return field
    from .combat.contracts import VoisinageEffect
    t = data['template']
    effects = tuple(VoisinageEffect(k, field.effect_cost, .2,
                   target='self' if k.startswith('restore_') else 'enemy',
                   restriction='technique' if k == 'restrict' else 'support' if k == 'isolate' else None)
                   for k in t['effects'])
    return replace(field, **{a: field.strength * t[a] for a in AXES},
                   effect=effects[0].kind, effects=effects,
                   features=(t['feature'],) if t['feature'] else ())


def study_years(game, doctrine_id, target):
    definition = game.doctrine_state['definitions'][doctrine_id]
    base = definition['stages'][target - 1]['years']
    saved = game.doctrine_state.get('player', {}).get('spirit_inheritances', {}).get(doctrine_id)
    if saved and valid(saved, 'celestial') and target <= 4:
        return ceil(base * (1 - .1 - discount(saved['source_level'])))
    return base

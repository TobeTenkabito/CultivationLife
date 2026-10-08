"""Soul identity, authored choices and deterministic previews; no world hooks."""
import copy
import hashlib

from ..content_registry import CONTENT_DOCUMENTS, WORLD_SYSTEMS
from .possession_system import is_possessed

ROUTES = {'guard': '守念', 'sever': '断执', 'transmute': '化愿'}


def catalog():
    return CONTENT_DOCUMENTS.get('ghost_soul_forms.json', {}) if WORLD_SYSTEMS.get('ghost_cultivation', {}).get('enabled') else {}


def stored(player):
    return player.world_voisinages.get('reincarnation', {}).get('ghost_soul_form')


def require(player):
    if not catalog() or player.path != 'ghost' or player.world != 'reincarnation' or player.realm_index < 9:
        raise ValueError('照魂须启用百鬼夜行，以九阶以上本魂身在轮回界')
    if is_possessed(player) or player.ghost_captor:
        raise ValueError('寄身或被拘期间，本魂修行冻结')
    # Voluntary attachment remains legal; it grants no special exemption or bonus.


def identity(data):
    payload = ':'.join(str(data[k]) for k in ('origin_owner_id', 'cause', 'route', 'blueprint_version'))
    return 'soul-form:' + hashlib.sha256(payload.encode()).hexdigest()[:24]


def validate(player):
    require(player)
    data = stored(player)
    if not isinstance(data, dict) or data.get('schema_version') != 1 or data.get('blueprint_version') != 1:
        raise ValueError('魂相版本待校验，原记录保留')
    if not data.get('origin_owner_id') or data.get('blueprint_id') != identity(data) or data.get('confirmed') is not True:
        raise ValueError('魂相身份待校验，原记录保留')
    template = catalog()['forms'].get(data.get('cause', '') + '.' + data.get('route', ''))
    if not template:
        raise ValueError('魂因或道路无效，原记录保留')
    aux, feature = data.get('secondary'), data.get('feature')
    if aux is not None and (aux not in template['secondary_choices'] or not data.get('secondary_locked')):
        raise ValueError('魂相辅权能记录无效')
    if feature is not None and (feature not in template['feature_choices'] or not data.get('feature_locked')):
        raise ValueError('魂痕记录无效')
    if data.get('offered_candidates') != template['feature_choices']:
        raise ValueError('魂痕候选版本待校验')
    rank = player.world_voisinages['reincarnation'].get('levels', {}).get(data['blueprint_id'], 0)
    if (rank >= 5 and aux is None) or (rank >= 9 and feature is None) or (rank >= 13 and not data.get('finalized')):
        raise ValueError('魂相阶段记录不完整')
    return data


def definition(player):
    if stored(player) is None:
        return None
    try:
        data = validate(player)
        row = copy.deepcopy(catalog()['forms'][data['cause'] + '.' + data['route']])
        row.update(id=data['blueprint_id'], soul_form=True, secondary=data['secondary'], feature=data['feature'])
        return row
    except (ValueError, KeyError, TypeError, OverflowError):
        return None


def evidence(game):
    """Bounded real milestones only; no reconstructed or fabricated biography."""
    rows = []
    seen = set()
    for h in reversed(game.history):
        if 'milestone' not in h.tags or h.event_id in seen:
            continue
        seen.add(h.event_id)
        rows.append(dict(ref=f'history:{h.event_id}:{h.age}', text=h.summary, title=h.title))
        if len(rows) == 12:
            break
    for realm, count in sorted(game.player.ghost_reincarnation_imprints.items()):
        if count:
            rows.append(dict(ref=f'imprint:{realm}', title='真实轮回印记', text=f'第 {realm} 阶轮回 {count} 次'))
    return rows


def public(player, game=None):
    if not catalog() or player.path != 'ghost':
        return None
    result = dict(title='照魂归真', reason=None, blueprint=copy.deepcopy(stored(player)), routes=ROUTES,
                  causes=catalog()['causes'], forms=catalog()['forms'], evidence=evidence(game) if game else [], level=0)
    result['contemplation'] = copy.deepcopy(player.world_voisinages.get('reincarnation', {}).get('contemplation'))
    try:
        require(player)
        if stored(player) is not None:
            data = validate(player)
            result['level'] = player.world_voisinages['reincarnation'].get('levels', {}).get(data['blueprint_id'], 0)
    except (ValueError, KeyError, TypeError) as error:
        result['reason'] = str(error)
    return result


def confirm(game, cause, route):
    p = game.player
    require(p)
    if stored(p) is not None or cause + '.' + route not in catalog()['forms']:
        raise ValueError('魂相已确认或所选魂因道路无效')
    row = catalog()['forms'][cause + '.' + route]
    data = dict(schema_version=1, blueprint_version=1, origin_owner_id=game.id, cause=cause, route=route,
                confirmed=True, secondary=None, secondary_locked=False, feature=None, feature_locked=False,
                offered_candidates=list(row['feature_choices']), finalized=False,
                evidence_refs=[e['ref'] for e in evidence(game)])
    data['blueprint_id'] = identity(data)
    p.world_voisinages.setdefault('reincarnation', {})['ghost_soul_form'] = data
    return f'沿{ROUTES[route]}凝定【{row["name"]}】。蓝图永久确认；领悟仍需正常付费，不赠送元力。'


def configure(player, action, choice):
    data = validate(player)
    row = catalog()['forms'][data['cause'] + '.' + data['route']]
    rank = player.world_voisinages['reincarnation'].get('levels', {}).get(data['blueprint_id'], 0)
    if action == 'soul_form_secondary':
        options = {effect_key(e): e for e in row['secondary_choices']}
        if rank != 4 or data['secondary_locked'] or choice not in options:
            raise ValueError('须在 初成四层时从合法候选铭定一次辅权能')
        data.update(secondary=copy.deepcopy(options[choice]), secondary_locked=True)
        return '辅权能已铭定，化境起生效。'
    if action == 'soul_form_feature':
        if rank != 8 or data['feature_locked'] or choice not in data['offered_candidates']:
            raise ValueError('须在 化境四层时从固定候选铭定一次魂痕')
        data.update(feature=choice, feature_locked=True)
        return '魂痕已铭定，大成起生效。'
    raise ValueError('未知魂相操作')


def effect_key(effect):
    return effect['kind'] + (':' + effect['restriction'] if effect.get('restriction') else '')


def training_reason(player, key, rank):
    row = definition(player)
    if row and row['id'] == key:
        data = stored(player)
        if rank == 4 and not data['secondary_locked']:
            return '请先铭定辅权能，再进入化境'
        if rank == 8 and not data['feature_locked']:
            return '请先铭定魂痕，再进入大成'

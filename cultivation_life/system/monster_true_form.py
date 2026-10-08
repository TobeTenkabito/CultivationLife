"""Personal, immutable-origin blueprints; no RNG, economy or combat hooks."""
import copy
import hashlib
import json
import re

from ..content_registry import CONTENT_DOCUMENTS, MONSTER_SPECIES, MONSTER_EVOLUTIONS, MONSTER_BLOODLINE_SETTINGS
from .custom_lineage_system import normalize_rules

TUNINGS = {'balanced': ('守中', (0, 0, 0)), 'ward': ('固本', (.1, -.1, 0)),
           'assault': ('争衡', (-.1, .1, 0))}


def catalog():
    return CONTENT_DOCUMENTS.get('monster_true_forms.json', {}).get('forms', {}) if MONSTER_SPECIES else {}


def stored(player):
    return player.world_voisinages.get('nether', {}).get('true_form')


def origin(player):
    if not catalog() or player.path != 'monster':
        raise ValueError('须启用万妖归宗并以妖修本源修行')
    if player.world != 'nether' or player.realm_index < 9:
        raise ValueError('本相仅在幽冥界九阶以上苏醒，离界保留蓝图与修习')
    species = player.monster_species_id
    node = MONSTER_EVOLUTIONS.get(player.monster_evolution_id, {})
    if species not in catalog() or node.get('species') != species or int(node.get('realm_index', 0)) > player.realm_index:
        raise ValueError('本源种属或进化血脉无效，原蓝图保留')
    match = re.fullmatch(r'.+_NETHER_(TRUE|SELF)_([1-4])', node.get('id', ''))
    if not match:
        raise ValueError('待确认高阶血脉：先完成真灵返祖，或自成血脉并补刻祖谱')
    route = 'ancestral' if match[1] == 'TRUE' else 'self'
    lineage = species + ':ancestral'
    snapshot = []
    if route == 'self':
        data = player.monster_custom_lineage
        if not isinstance(data, dict) or not data.get('id') or data['id'] != player.monster_custom_lineage_id or data.get('founder_species_id') != species:
            raise ValueError('自成血脉祖谱尚未有效确认，无法铸域')
        stage = int(match[2])
        if data.get('finalized_stage', 0) < stage or not data.get('rules'):
            raise ValueError('当前祖谱阶段尚未确认')
        cfg = MONSTER_BLOODLINE_SETTINGS['custom_lineage']
        snapshot, _ = normalize_rules(data['rules'], cfg, slots=int(cfg['rule_slots'][str(stage)]), budget=int(data.get('spent_points', 0)))
        lineage = data['id']
    return dict(origin_species_id=species, route=route, lineage_id=lineage, lineage_rules=snapshot)


def identity(data):
    payload = {k: data[k] for k in ('origin_species_id', 'route', 'lineage_id', 'primary', 'lineage_rules')}
    return 'true-form:' + hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def tunings(data):
    if data['route'] == 'ancestral':
        return TUNINGS
    tags = {r['effect'] for r in data['lineage_rules']}
    # A finite permission projection only. The original lineage rules still
    # execute once in their own provider; no rule is copied into this domain.
    allowed = {'balanced'}
    if tags & {'might', 'breach', 'damage', 'mobility'}:
        allowed.add('assault')
    if tags & {'guard', 'sustain', 'restore_hp', 'restore_mp', 'sense'}:
        allowed.add('ward')
    return {k:v for k,v in TUNINGS.items() if k in allowed}


def validate(player):
    context = origin(player)
    data = stored(player)
    if not isinstance(data, dict) or data.get('schema_version') != 1 or data.get('blueprint_version') != 1:
        raise ValueError('本相蓝图版本或内容无效，原记录保留')
    if any(data.get(k) != context[k] for k in ('origin_species_id', 'route', 'lineage_id')):
        raise ValueError('本相原始血脉与当前身份不符，原记录保留')
    effects = catalog()[context['origin_species_id']]['effects']
    allowed = effects if context['route'] == 'self' else effects[:1]
    if data.get('primary') not in allowed or not data.get('primary_locked'):
        raise ValueError('本相主权能或锁定记录无效')
    # Self lineage may only grow by appending; the confirmed snapshot never changes.
    snapshot = data.get('lineage_rules')
    if not isinstance(snapshot, list) or context['lineage_rules'][:len(snapshot)] != snapshot or (context['route'] == 'self' and not snapshot):
        raise ValueError('本相祖谱快照已失效')
    if data.get('blueprint_id') != identity(data):
        raise ValueError('本相蓝图编号校验失败')
    aux = data.get('secondary')
    if aux is not None and (aux not in effects or aux == data['primary'] or not data.get('secondary_locked')):
        raise ValueError('本相辅权能无效')
    tuning = data.get('tuning')
    if tuning is not None and (tuning not in tunings(data) or not data.get('tuning_locked')):
        raise ValueError('本相调校无效')
    rank = player.world_voisinages['nether'].get('levels', {}).get(data['blueprint_id'], 0)
    if (rank >= 5 and aux is None) or (rank >= 9 and tuning is None) or (rank >= 13 and not data.get('finalized')):
        raise ValueError('本相阶段锁定记录不完整')
    return data


def definition(player):
    if stored(player) is None:
        return None
    try:
        data = validate(player)
    except (ValueError, TypeError, KeyError, OverflowError):
        return None
    row = copy.deepcopy(catalog()[data['origin_species_id']])
    row.update(id=data['blueprint_id'], true_form=True, effects=[data['primary']], secondary=data.get('secondary'), tuning=data.get('tuning'))
    return row


def public(player):
    if not catalog() or player.path != 'monster':
        return None
    result = dict(title='本相铸域', reason=None, blueprint=copy.deepcopy(stored(player)), choices=[], tunings={k:v[0] for k,v in TUNINGS.items()})
    try:
        context = origin(player)
        template = catalog()[context['origin_species_id']]
        result.update(name=template['name'], description=template['description'], route=context['route'])
        result['preview'] = copy.deepcopy(template)
        result['choices'] = template['effects'] if context['route'] == 'self' else template['effects'][:1]
        result['secondary_choices'] = template['effects']
        result['tunings'] = {k:v[0] for k,v in tunings(context).items()}
        if stored(player) is not None:
            data = validate(player)
            result['tunings'] = {k:v[0] for k,v in tunings(data).items()}
            result['level'] = player.world_voisinages['nether'].get('levels', {}).get(data['blueprint_id'], 0)
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        result['reason'] = str(error) or '本相记录无效，原始记录保留'
    return result


def configure(player, action, choice):
    context = origin(player)
    if action == 'true_form_confirm':
        if stored(player) is not None:
            raise ValueError('本相已确认，不能重铸或覆盖原记录')
        template = catalog()[context['origin_species_id']]
        if choice not in (template['effects'] if context['route'] == 'self' else template['effects'][:1]):
            raise ValueError('所选主权能不属于本源允许范围')
        data = dict(context, schema_version=1, blueprint_version=1, primary=choice,
                    primary_locked=True, secondary=None, secondary_locked=False,
                    tuning=None, tuning_locked=False, finalized=False)
        data['blueprint_id'] = identity(data)
        player.world_voisinages.setdefault('nether', {})['true_form'] = data
        return '本相蓝图已确认。尚未领悟，不增加元力；请依报价修习至一级。'
    data = validate(player)
    rank = player.world_voisinages['nether'].get('levels', {}).get(data['blueprint_id'], 0)
    if action == 'true_form_secondary':
        if rank != 4 or data['secondary_locked']:
            raise ValueError('辅权能须在初成四层后、进入化境前铭定一次')
        if choice not in catalog()[context['origin_species_id']]['effects'] or choice == data['primary']:
            raise ValueError('辅权能须选本源的另一项权能')
        data.update(secondary=choice, secondary_locked=True)
        return '辅权能已铭定，修至化境后生效，不增加每轮动作次数。'
    if action == 'true_form_tuning':
        if rank != 8 or data['tuning_locked'] or choice not in tunings(data):
            raise ValueError('归真调校须在化境四层后择定一次')
        data.update(tuning=choice, tuning_locked=True)
        return '归真方向已锁定，大成起生效；至臻修成时完成本相归真。'
    raise ValueError('未知本相铸域操作')


def training_reason(player, key, rank):
    row = definition(player)
    if not row or row['id'] != key:
        return None
    data = stored(player)
    if rank == 4 and not data['secondary_locked']:
        return '请先铭定辅权能，再进入化境'
    if rank == 8 and not data['tuning_locked']:
        return '请先择定归真方向，再进入大成'
    return None

"""Paid specialization construction and explicit use of original repair/training services."""
import copy
import hashlib
import json
import math

from ..earth_temple_content import FACILITIES
from ..content_registry import CONTENT_DOCUMENTS, ITEM_CATALOG
from .earth_temple_rules import state, temple, slots, local_reason, occupied_reason
from . import building_projects as construction
from .building_assets import local_rows


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:24]


def bill(game, kind):
    cost = construction.temple_facility_cost('celestial', kind)
    held = {i.id:i.quantity for i in game.player.inventory}
    missing = held.get('spirit_stone',0) < cost['coins'] or any(held.get(k,0)<n for k,n in cost['materials'].items())
    return dict(cost, reason='灵石或工程材料不足' if missing else '')


def works_reason(game, slot, kind):
    if blocked := local_reason(game) or occupied_reason(game):
        return blocked
    current = slots(game)
    if slot not in (0,1) or kind not in (*FACILITIES, None):
        return '未知专项设施或设施位'
    if current[slot] == kind:
        return '此设施位无需改建'
    if kind and kind in current:
        return '同一座庙不能重复建设同类专项设施'
    return bill(game, kind)['reason']


def start_works(game, target):
    parts = target.split(':')
    if len(parts) != 2 or parts[0] not in {'0','1'}:
        raise ValueError('请重新选择专项设施位')
    slot, kind = int(parts[0]), None if parts[1] == 'remove' else parts[1]
    if blocked := works_reason(game, slot, kind):
        raise ValueError(blocked)
    cost, current = bill(game, kind), slots(game)
    construction.pay(game, cost, '土地庙专项营造')
    old = current[slot]
    current[slot] = None
    temple(game)['temple_facilities'] = current
    state(game)['works'] = dict(slot=slot, kind=kind, old=old, progress=0,
        years=20 if kind else 10, started=game.player.age, paid=copy.deepcopy(cost))
    return f"开始{'改建' if old else '营造'}{FACILITIES[kind]['name'] if kind else '空置设施位'}。原设施已停用拆解，工料已投入；本人须在此施工，取消不退费也不复原旧设施。"


def finish_works(game):
    s = state(game)
    order = s.get('works')
    if not order or order['progress'] < order['years']:
        raise ValueError('专项营造尚未完成实际工时')
    current = slots(game)
    if current[order['slot']] is not None or order['kind'] and order['kind'] in current:
        raise ValueError('原设施位已经变化，请退出并重新核对')
    current[order['slot']] = order['kind']
    temple(game)['temple_facilities'] = current
    s.pop('works')
    return f"{FACILITIES[order['kind']]['name'] if order['kind'] else '设施位清理'}竣工；未发放香火或个人成长。"


def _watch(game):
    definitions = CONTENT_DOCUMENTS.get('formations.json', {}).get('maintenance_resources', [])
    for array in game.player.formation_ground_arrays:
        if (array.get('owner_kind') != 'player' or array.get('owner_id') != 'player'
                or array.get('creator_id') != game.id or array.get('world') != 'celestial'
                or array.get('location_id') != game.player.location_id or array.get('durability',100) >= 99.999):
            continue
        for definition in definitions:
            if definition.get('world') != 'celestial':
                continue
            qty = min(10, max(1, math.ceil((100-array['durability']) / definition['repair_value'])))
            held = game.player.formation_repair_supplies.get(definition['id'], 0)
            yield dict(kind='watch', target_id=array['id'], supply=definition['id'], quantity=qty,
                title=array['name'], result=f"完整度 {array['durability']:g}% → {min(100,array['durability']+qty*definition['repair_value']):g}%",
                cost=f"{definition['name']} ×{qty}（持有{held}）", reason='持有的修阵资源不足' if held<qty else '',
                stamp=fingerprint([array,definition,held]))


def _care(game):
    for row in local_rows(game):
        if row['status'] != 'destroyed' or row.get('subtype') == 'temple':
            continue  # Buddhist sites keep their original path-specific operator.
        quoted = construction.quote(game, 'rebuild', row)
        if not construction.owns(game, row) and not (row['type']=='city' and row.get('public')):
            continue
        result = ('按原规则重建为一级城，发展与公共设施清空；权属及旧领取记录保留'
                  if row['type'] == 'city' else '原址重建；原权属、旧次数与库存保留')
        yield dict(kind='care', target_id=row['id'], title=row['name'], result=result,
            cost=construction.bill_text(quoted), reason=quoted['reason'], stamp=fingerprint([row,quoted]))


def _teach(game):
    from .npc_development.targets import candidates
    from .npc_development.service import quote
    for target in candidates(game):
        if target.kind != 'npc' or target.person is None or not set(target.relations)&{'弟子','后代','族人','道侣'}:
            continue
        try:
            quoted = quote(game, 'npc', target.identity, 'cultivation', 'infuse', 1, _target=target)
        except ValueError:
            continue
        # The original presentation lazily derives other axes (e.g. sense rank).
        # Bind this cultivation offer to its actual price/growth, not those caches.
        quoted_facts = {k:v for k,v in quoted.items() if k != 'result'}
        quoted_facts['growth'] = {k:quoted['result'].get(k) for k in
                                  ('realm_index','layer','lifespan','immortal_cultivation')}
        yield dict(kind='teach', target_id=target.identity, title=target.person.name,
            result=f"{quoted['label']}：{quoted['before']} → {quoted['after']}",
            cost=f"原培养机缘 {quoted['opportunity']:g}", reason=quoted['reason'], stamp=fingerprint(quoted_facts))


def services(game, blocked=''):
    if local_reason(game):
        return []
    result = []
    for kind, provider in [('watch',_watch),('care',_care),('teach',_teach)]:
        if kind not in slots(game):
            continue
        for i, row in enumerate(provider(game)):
            if i >= 24:
                break
            row['id'] = fingerprint(row)
            row['reason'] = blocked or row['reason']
            result.append(row)
    return result


def execute(game, token, blocked):
    if blocked:
        raise ValueError(blocked)
    row = next((r for r in services(game) if r['id'] == token), None)
    if not row:
        raise ValueError('专项对象或原报价已变化，请刷新后重试')
    if row['reason']:
        raise ValueError(row['reason'])
    if row['kind'] == 'watch':
        from .formation.maintenance import repair
        array = next(a for a in game.player.formation_ground_arrays if a['id']==row['target_id'])
        definition = next(d for d in CONTENT_DOCUMENTS['formations.json']['maintenance_resources'] if d['id']==row['supply'])
        summary = repair(game, array, row['supply'], definition, row['quantity'])
    elif row['kind'] == 'care':
        from .building_destruction import rebuild
        building = next(b for b in local_rows(game) if b['id']==row['target_id'])
        rebuild(game, building, None)
        summary = f"{building['name']}已沿原工程结算重建。"
    else:
        from .npc_development.service import apply
        summary = apply(game, 'npc', row['target_id'], 'cultivation', 'infuse', 1)
    state(game)['duty'] = dict(kind=row['kind'], special=True, target_id=row['target_id'],
        started=game.player.age, stage='service', progress=0, years=100, plan='special', receipt=summary)
    return summary + ' 实际服务已经交付，后续由本人履行100年公共巡护／养护／讲习，验收后才取得本庙香火。取消不撤销已交付成果、不退原支出。'


def public(game, service_reason):
    current = slots(game)
    return dict(slots=current, works=copy.deepcopy(state(game).get('works')),
        cancel_reason=local_reason(game, recovery=True),
        options=[dict(id=kind or 'remove', name=FACILITIES[kind]['name'] if kind else '拆除并空置',
            purpose=FACILITIES[kind]['purpose'] if kind else '拆下原设施；工料不返还。',
            years=20 if kind else 10, cost=bill(game,kind),
            recipe=[dict(name=ITEM_CATALOG[k].name,needed=n,owned=sum(i.quantity for i in game.player.inventory if i.id==k))
                    for k,n in bill(game,kind)['materials'].items()],
            reasons=[works_reason(game,slot,kind) for slot in (0,1)]) for kind in [*FACILITIES,None]],
        services=services(game, service_reason))

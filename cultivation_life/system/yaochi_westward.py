"""Yaochi personal projects: authoritative quotes, paid years and one-time delivery."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from fractions import Fraction

from ..content_registry import ITEM_CATALOG
from ..models import HistoryRecord
from ..rules import add_item, remove_item
from ..runtime import decode_rng, encode_rng, now_iso
from . import westward_finance as funds
from .westward_rules import config, enabled, record, project, adopt_merit, merit_balance
from .yaochi_rules import config as pool_config, offers, grant
from .immortal_cultivation import body_manual, body_recipe, body_probability, rules
from .immortal_body_system import _divine_training_reason, quantity
from .immortal_training import settle_body, settle_light
from .divine_lights import definitions, profile, recipe
from .cultivation_guard import cultivation_blocked


def reason(game, *, cancelling=False):
    p = game.player
    if p.world != 'celestial' or p.location_id != pool_config()['location_id']:
        return '须亲临仙界瑶池办理；外出期间专修暂停'
    if (cultivation_blocked(game) or p.nascent_state.get('crisis') or
            game.map_journey or game.guixu_state.get('player_session')):
        return '请先处理事件、旅行或拘束，再办理瑶池专修'
    from .earth_temple_rules import reason as actor_reason
    if blocked := actor_reason(game, recovery=True):
        return blocked
    if cancelling:
        return ''
    from .westward_activity import occupied
    if occupied(game):return '请先交接访古或项目议政的本人事务'
    from .earth_temple_rules import pending
    if pending(game) or game.yaochi_state.get('job'):
        return '请先完成或退出庙务，交付瑶池委托，再办理专修'
    bureaus=game.heavenly_court.get('bureaus',{})
    if bureaus.get('review') or any(c['status']=='active' for c in bureaus.get('inquiries',[])) or any(j['person']=='player' and j['status']=='active' for j in bureaus.get('jobs',[])):
        return '请先完成或交接本人当前职司公务'
    if not enabled():
        return '《瑶池西望：紫气东来》尚未启用'
    if p.path != 'dao' or p.realm_index < 9:
        return '道修达到真仙境界后开放瑶池专修'
    if not p.immortal_power_converted:
        return '须先完成仙灵力转化'
    return _divine_training_reason(game)


def _signature(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()[:24]


def _facts(game):
    p = game.player
    return dict(age=p.age, world=p.world, location=p.location_id, realm=p.realm_index,
                layer=p.layer, body=p.immortal_body, training=p.body_training,
                sequence=record(game).get('sequence', 0), merit=game.yaochi_state.get('merit', 0),
                court=merit_balance(game), adopted='merit_account' in game.heavenly_court,
                inventory=[(i.id, i.quantity) for i in p.inventory])


def _material_value(game, materials):
    catalog = {o['id']: o for o in offers(game) if o['kind'] == 'item'}
    return sum(Fraction(catalog[key]['price'] * n, catalog[key]['quantity']) for key, n in materials.items())


def quotes(game):
    """No initialization, RNG, reservations or resource writes on presentation."""
    p, cfg = game.player, config()
    if not enabled() or p.path != 'dao' or p.realm_index < 9:
        return []
    base = reason(game) or ('请先完成或退出当前专修' if project(game) else '')
    rows = [dict(id='trace', kind='trace', name='澄心池', mark='澄', years=cfg['trace_years'],
                 price=cfg['trace_price'], materials={}, reason=base,
                 description=f"凝聚 {cfg['trace_reward']} 道仙痕，按实际修持年数积累。",
                 benefit=f"{cfg['trace_reward']} 仙痕", comparison='专修期间不获得普通闭关机缘')]
    from .yaochi_guidance import quote as guidance_quote
    rows.append(guidance_quote(game,base))
    manual = body_manual(p)
    body_reason = base
    if not body_reason:
        if p.body_training < rules()['body']['required_training']:
            body_reason = '炼体须先达到一百层'
        elif not manual:
            body_reason = '须先取得并选用仙躯功法'
        elif p.immortal_body.get('level', 0) >= rules()['body']['max_level']:
            body_reason = '仙躯已达五十层'
    materials = body_recipe(p) if manual and p.immortal_body.get('level', 0) < 50 else {}
    fee = math.ceil(_material_value(game, materials) * Fraction(str(cfg['body_fee_rate']))) if materials else 0
    rows.append(dict(id='body', kind='body', name='玉液池', mark='玉', years=cfg['body_years'],
                     price=fee, materials=materials, reason=body_reason,
                     level=p.immortal_body.get('level', 0), manual=manual['id'] if manual else None,
                     failures=p.immortal_body.get('failures', 0),
                     chance=min(1, body_probability(p) + cfg['body_chance_bonus']),
                     description='以完整仙药配方淬体，成功率增加15个百分点，保留失败保底。',
                     benefit=f"{min(1, body_probability(p) + cfg['body_chance_bonus']):.0%} 成功率",
                     comparison=f"普通淬体 {body_probability(p):.0%} · 原入口无需十年工时"))
    _, levels = profile(p, player=True)
    for light in definitions():
        key = light['id']
        level = levels.get(key, 0)
        materials = {k: math.ceil(n * Fraction(str(cfg['light_material_rate']))) for k, n in recipe(light, level).items()} if level < 10 else {}
        blocked = base or (f"仙躯{light['unlock_level']}层解锁" if key not in levels else
                           '已达十重' if level >= 10 else '')
        rows.append(dict(id=f'light_{key}', kind='light', name=light['name'], mark='光',
                         years=cfg['light_years'], price=0, materials=materials, reason=blocked,
                         key=key, level=level, body_level=p.immortal_body.get('level', 0),
                         description='五光坛凝炼：消耗下一重七成资材，逐项向上取整。',
                         benefit=f"第 {level + 1} 重" if level < 10 else '已圆满',
                         comparison='原即时修炼仍可用；此处以百年工时节省材料'))
    facts = _facts(game)
    for row in rows:
        row['token'] = _signature(dict(facts=facts, quote=row))
        row['court_price'] = (row['price'] + 39) // 40
        row['recipe'] = [dict(id=k, name=ITEM_CATALOG[k].name, needed=n, owned=quantity(p, k))
                         for k, n in row['materials'].items()]
        missing = any(r['owned'] < r['needed'] for r in row['recipe'])
        row['start_reason'] = row['reason'] or ('所需资材不足，可先按目标备料' if missing else '')
        row['merit_reason'] = row['start_reason'] or funds.payment_reason(game, row['price'], 'merit')
        row['court_reason'] = row['start_reason'] or funds.payment_reason(game, row['price'], 'court')
        supply = _supplies(game, row['materials'])
        row['supply'] = supply
        row['supply_merit_reason'] = row['reason'] or ('行囊资材已足够' if not supply['items'] else '') or funds.payment_reason(game, supply['price'], 'merit')
        if not row['supply_merit_reason'] and supply['price'] * 250 > _pool_balance(game):
            row['supply_merit_reason'] = '瑶池采购资金不足'
        row['supply_court_reason'] = row['reason'] or ('行囊资材已足够' if not supply['items'] else '') or funds.payment_reason(game, supply['price'], 'court')
    return rows


def _pool_balance(game):
    return funds.balance(game, funds.YAOCHI) if funds.YAOCHI in game.economy_v2.get('accounts', {}) else 0


def _supplies(game, materials):
    catalog = {o['id']: o for o in offers(game) if o['kind'] == 'item'}
    items, price = [], 0
    for key, needed in materials.items():
        missing = max(0, needed - quantity(game.player, key))
        if missing:
            offer = catalog[key]
            packs = math.ceil(missing / offer['quantity'])
            items.append(dict(id=key, packs=packs, quantity=packs * offer['quantity'],
                              name=offer['name'], price=offer['price'] * packs))
            price += offer['price'] * packs
    return dict(items=items, price=price, court_price=(price + 39) // 40)


def _new_order(game):
    state = game.yaochi_state.setdefault('westward', {})
    state['sequence'] = state.get('sequence', 0) + 1
    return dict(id=str(state['sequence']), world='celestial', location=pool_config()['location_id'],
                opened_age=game.player.age, progress=0)


def _current_quote(game, token):
    quote = next((r for r in quotes(game) if r['token'] == token), None)
    if quote is None:
        raise ValueError('修持目标或报价已变化，请刷新后重新选择')
    return quote


def _project_token(row):
    return _signature(row)


def _current_project(game, token):
    row = project(game)
    if not row or _project_token(row) != token:
        raise ValueError('专修记录已经变化，请刷新后重试')
    return row


def _target_reason(game, row):
    p = game.player
    if row['kind']=='guidance':
        from .yaochi_guidance import target_reason
        return target_reason(game,row)
    if row['kind'] == 'body':
        manual = body_manual(p)
        if (p.immortal_body.get('level', 0) != row['level'] or
                p.immortal_body.get('failures', 0) != row['failures'] or
                not manual or manual['id'] != row['manual'] or
                p.body_training < rules()['body']['required_training']):
            return '仙躯或功法已变化，请退出本次专修后重新预约'
    if row['kind'] == 'light':
        _, levels = profile(p, player=True)
        if levels.get(row['key']) != row['level']:
            return '神光资格或等级已变化，请退出本次专修后重新预约'
    return ''


def begin_practice(game):
    blocked = reason(game)
    row = project(game)
    if blocked:
        raise ValueError(blocked)
    if not row or row['progress'] >= row['years']:
        raise ValueError('请先预约专修，或结清已完成项目')
    if blocked := _target_reason(game, row):
        raise ValueError(blocked)
    return row['years'] - row['progress']


def finish_practice(game, elapsed, time_unit):
    row = project(game)
    if not row:
        return 0
    # The advance command owns actual years, interruptions and all world ticks.
    row['progress'] = min(row['years'], row['progress'] + max(0, elapsed))
    if row['kind'] == 'trace':
        due = row['trace_reward'] * row['progress'] // row['years']
        game.player.immortal_traces += due - row.get('delivered', 0)
        row['delivered'] = due
    state = game.yaochi_state['westward']
    units, state['settlement_years'] = divmod(state.get('settlement_years', 0) + max(0, elapsed), time_unit)
    return units


def action(deps, game, command, token, amount):
    if type(amount) is not int or amount != 1:
        raise ValueError('专修事务每次只办理一份')
    cancelling = command == 'westward_cancel'
    if blocked := reason(game, cancelling=cancelling):
        raise ValueError(blocked)
    if command == 'westward_adopt':
        if 'merit_account' in game.heavenly_court:
            raise ValueError('功德账本已经确认，无须重复办理')
        adopt_merit(game)
        summary = f'确认现有功德权益：可用 {merit_balance(game)}，官品资历保持不变。'
    elif command in {'westward_start_merit', 'westward_start_court', 'westward_supply_merit', 'westward_supply_court'}:
        if any(r['status']=='active' for r in record(game).get('fair',{}).get('entries',[])):raise ValueError('请先完成或退出仙会赛事')
        quote = _current_quote(game, token)
        currency = 'court' if command.endswith('_court') else 'merit'
        supplying = command.startswith('westward_supply')
        blocked = quote[f'supply_{currency}_reason' if supplying else f'{currency}_reason']
        if blocked:
            raise ValueError(blocked)
        order = _new_order(game)
        if supplying:
            supply = quote['supply']
            funds.reserve(game, order, supply['price'], currency)
            funds.close(game, order, 1, 1)
            funds.finance.procure(game, funds.YAOCHI, 'celestial', supply['price'] * 250, '瑶池按目标采购实际缺口')
            catalog = {o['id']: o for o in offers(game) if o['kind'] == 'item'}
            for item in supply['items']:
                grant(game, catalog[item['id']], item['packs'])
            summary = '按目标备料完成：' + '、'.join(f"{r['name']}×{r['quantity']}" for r in supply['items']) + '。整份采购余料留在行囊。'
        else:
            funds.reserve(game, order, quote['price'], currency)
            for key, n in quote['materials'].items():
                if not remove_item(game.player, key, n):
                    raise ValueError('材料已变化，请刷新报价')
            order.update({k: copy.deepcopy(quote[k]) for k in ('kind', 'name', 'years', 'materials')})
            for key in ('level', 'manual', 'failures', 'chance', 'key', 'body_level','teacher','teacher_name','realm','layer'):
                if key in quote:
                    order[key] = quote[key]
            if order['kind'] == 'trace':
                order.update(trace_reward=config()['trace_reward'], delivered=0)
            game.yaochi_state['westward']['project'] = order
            summary = f"预约{order['name']}，须亲自在瑶池修持{order['years']}年；资材已托管，离开后暂停。"
    elif command in {'westward_work', 'westward_claim', 'westward_cancel'}:
        order = _current_project(game, token)
        if command == 'westward_work':
            begin_practice(game)
            return deps.advance(game.id, 'yaochi_practice', 1)
        if command == 'westward_claim':
            if order['progress'] < order['years']:
                raise ValueError('实际修持年数尚未完成')
            if blocked := _target_reason(game, order):
                raise ValueError(blocked)
            if order['kind'] == 'body':
                rng = decode_rng(game.seed, game.rng_state)
                summary = settle_body(game.player, rng, order['chance'])
                game.rng_state = encode_rng(rng)
            elif order['kind'] == 'light':
                settle_light(game.player, order['key'], order['level'])
                summary = f"{order['name']}凝炼至第{order['level'] + 1}重，托管资材已消耗。"
            elif order['kind']=='guidance':
                summary=f"清修讲席已结清，实际指导累计入账{order.get('opportunity_delivered',0):.1f}机缘；原师门额度与仙痕不变。"
            else:
                summary = f"澄心池专修结清，{order['delivered']}道仙痕已按实际工时入账。"
            funds.close(game, order, order['years'], order['years'])
        else:
            refund = funds.close(game, order, order['progress'], order['years'])
            for key, n in order['materials'].items():
                add_item(game.player, key, n)
            summary = f"退出{order['name']}，按未使用工时退还{refund}{'功勋' if order['currency'] == 'merit' else '功德'}，尚未结算的托管药材／资材已返还；已完成工时不返还。"
        state = game.yaochi_state['westward']
        state['last_result'] = summary
        state.pop('project')
    else:
        raise ValueError('未知瑶池专修事务')
    game.history.append(HistoryRecord('SYS_YAOCHI_WESTWARD', 1, game.player.age,
                                     '瑶池专修', command, 'completed', summary, {}, ['yaochi', 'cultivation']))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def public(game):
    row = project(game)
    visible = bool((enabled() and game.player.path == 'dao' and game.player.realm_index >= 9) or row)
    if not visible:
        return dict(available=False)
    view = copy.deepcopy(row) if row else None
    if view:
        view.update(token=_project_token(row), reason=reason(game) or _target_reason(game, row),
                    cancel_reason=reason(game, cancelling=True),
                    refund=row['paid'] * (row['years'] - row['progress']) // row['years'])
    return dict(available=True, enabled=enabled(), reason=reason(game),
                adopted='merit_account' in game.heavenly_court, merit=merit_balance(game),
                qualification=game.heavenly_court.get('player_merit', 0), budget=funds.budget(game),
                project=view, services=quotes(game), last_result=record(game).get('last_result', ''))

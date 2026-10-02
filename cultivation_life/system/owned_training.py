"""Deterministic, resource-funded training for owned bodies; independent of DLC."""
import copy
from ..content_registry import REALMS
from ..rules import max_mp, divine_sense_level
from .cultivation_ranks import rank_for, describe

AXES = {'cultivation': '培养修为', 'body': '培养炼体', 'sense': '培养神识'}


def facts(target):
    row = copy.deepcopy(target)
    # Old saves receive stable independent coordinates, never inferred repeatedly.
    from .asura import body_facts
    if row.get('body_training') is None:
        row.update(body_facts(row))
    row['realm_index'] = int(row.get('realm_index') or 0)
    row['layer'] = int(row.get('layer') or 1)
    row['immortal_body_level'] = int(row.get('immortal_body_level') or 0)
    row['divine_sense_rank'] = (int(row['divine_sense_rank']) if row.get('divine_sense_rank') is not None
                                else rank_for(row['realm_index'], row['layer']))
    return row


def realm_name(row):
    r, l = int(row.get('realm_index', 0)), int(row.get('layer', 1))
    name = REALMS[r].name
    if row.get('path') == 'demonic' and r >= 9:
        name = ('修罗', '非天', '罗睺', '摩诃')[r - 9]
    return f'{name} {l}层'


def status(row, axis):
    if axis == 'cultivation':
        return realm_name(row)
    if axis == 'body':
        return f"普通炼体 {int(row.get('body_training', 0))}/100层 · 高阶肉身 {int(row.get('immortal_body_level', 0))}层"
    return f"神识 {describe(row['divine_sense_rank'])['name']}（{row['divine_sense_rank']}阶）"


def quote(player, target, axis, batches=1):
    if axis not in AXES or type(batches) is not int or batches not in (1, 5, 10):
        raise ValueError('培养方向或轮数无效；可选择1、5、10轮')
    row = facts(target)
    before = status(row, axis)
    cost, mp, rounds, gain = 0.0, 0.0, 0, 0
    for _ in range(batches):
        realm = max(0, min(12, int(row.get('realm_index', 0))))
        delta = 0
        if axis == 'cultivation':
            for _ in range(min(3, 1 + max(0, player.realm_index - realm))):
                r, l = int(row.get('realm_index', 0)), int(row.get('layer', 1))
                if (r, l) >= (player.realm_index, player.layer):
                    break
                if l >= REALMS[r].layers:
                    r, l = r + 1, 1
                else:
                    l += 1
                row.update(realm_index=r, layer=l)
                delta += 1
            factor = 1.12 ** delta
        elif axis == 'body':
            normal = int(row['body_training'])
            if normal < min(100, player.body_training):
                delta = min(10, min(100, player.body_training) - normal)
                row['body_training'] = normal + delta
                factor = 1.025 ** delta
            elif normal >= 100:
                cap = max(int(player.immortal_body.get('level', 0)), int(player.asura_cultivation.get('body_level', 0)))
                delta = max(0, min(2, cap - int(row['immortal_body_level'])))
                row['immortal_body_level'] += delta
                factor = 1.12 ** delta
            else:
                factor = 1
        else:
            delta = max(0, min(8, divine_sense_level(player) - int(row['divine_sense_rank'])))
            row['divine_sense_rank'] += delta
            factor = 1.015 ** delta
        if not delta:
            break
        # Costs follow the target's tier, so a senior can efficiently train juniors.
        cost += max(1.0, REALMS[realm].opportunity_base * .015) * (1 - min(.35, max(0., float(target.get('breakthrough_bonus', 0)))))
        mp += max(1.0, max_mp(player) * .02)
        row['combat_power'] = round(max(1.0, float(row.get('combat_power', 1))) * factor, 1)
        rounds += 1
        gain += delta
    reason = '' if rounds else '已达玩家对应能力的培养上限'
    if rounds and (player.opportunity < round(cost, 2) or player.mp < round(mp, 2)):
        reason = '机缘或法力不足，可减少投入轮数'
    if rounds:
        row['breakthrough_bonus'] = 0.0
    row['realm_name'] = realm_name(row)
    return dict(axis=axis, label=AXES[axis], batches=batches, rounds=rounds, gain=gain,
                before=before, after=status(row, axis), opportunity=round(cost, 2), mp=round(mp, 2),
                power_before=float(target.get('combat_power', 0)), power_after=row.get('combat_power', 0),
                can_train=bool(rounds and not reason), reason=reason, result=row)


def public(player, target):
    return {axis: [{k: v for k, v in quote(player, target, axis, n).items() if k != 'result'}
                   for n in (1, 5, 10)] for axis in AXES}

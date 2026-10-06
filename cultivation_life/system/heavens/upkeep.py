"""Finite, prepaid facilities maintain a known node on the ordinary world clock."""
import copy

from .state import active_task, contacts, echo_site, get_echo, phase, record

LABELS = {'upkeep_start': '部署托管护持', 'upkeep_cancel': '终止托管护持'}


def deadline(echo, row):
    return echo['origin_year'] + row['cycle'] * echo['definition']['period_years'] + echo['definition']['window_years']


def quote(deps, game, action, target, options):
    runtime = game.heavens_state.get('runtime')
    echo = get_echo(runtime, target)
    if not echo:
        raise ValueError('须先登记当地诸天联系')
    row = echo.get('upkeep')
    if action == 'upkeep_cancel':
        if not row or row['status'] != 'active':
            raise ValueError('没有进行中的托管护持')
        return dict(years=0, costs={}, refundable=dict(stones=row['escrow']['total']-row['escrow']['spent']),
                    message='终止后续供能并退回未耗经费；已安装阵材、已耗经费与实付法力不退，当期维护名额不恢复。')
    facts = deps.read_actor_facts(game, target)
    if facts['blocked_reason'] or game.player.sealed_cultivation:
        raise ValueError(facts['blocked_reason'] or '须先解除修为封印')
    if active_task(runtime):
        raise ValueError('请先完成或取消当前亲自任务')
    if row:
        raise ValueError('每处联系仅可部署一次托管设施')
    cycle, offset, cutoff = phase(runtime, echo)
    if echo['observed_cycle'] != cycle or not echo['exchanged']:
        raise ValueError('须取得合法抄录并完成当期体察')
    if echo['maintenance_started']:
        raise ValueError('当期维护名额已由亲自维护或托管使用')
    duration = echo['definition']['maintain_years']
    if offset + duration >= cutoff:
        raise ValueError('当前窗口不足以完成全部护持年份')
    if options.get('material_id') not in {m['id'] for m in deps.quote_materials(game, target)}:
        raise ValueError('须提供一件本界闲置九阶普通阵材')
    total = echo['definition']['maintain_stones'] * 3 // 2
    mp = facts['max_mp'] * .05
    if facts['stones'] < total or facts['mp'] < mp:
        raise ValueError('部署所需灵石或法力不足')
    return dict(years=0, duration=duration, costs=dict(stones=total, mp=mp, material_id=options['material_id']),
                refundable={}, material_consumed=True, deadline=deadline(echo, dict(cycle=cycle)),
                message=f'预留 {total} 灵石，由阵材设施在 {duration} 个实际外界年中按进度供能；完成后取得本周期维护效果，不另占亲自任务或生成人物。',
                warning='与亲自维护共用当期名额和参悟收益上限。独立空间冻结供能且不补算；窗口到期或本人死亡即终止，未耗经费退回。')


def close(deps, game, echo, status, year):
    row = echo['upkeep']
    row.update(status=status, last_year=year)
    deps.refund_resources(game, row['escrow'])
    label = {'cancelled': '已主动终止', 'expired': '窗口已过期', 'failed': '本人此生结束'}[status]
    record(game, f'{echo_site(echo).name}的托管护持{label}，退回未耗经费 {row["escrow"]["refunded"]} 灵石；安装阵材与已耗投入保留。', year=year)


def execute(deps, game, action, target, options, proposal):
    runtime = game.heavens_state['runtime']
    echo = get_echo(runtime, target)
    if action == 'upkeep_cancel':
        close(deps, game, echo, 'cancelled', runtime['processed_years'])
    else:
        escrow = deps.reserve_resources(game, proposal['costs']['stones'], options['material_id'], proposal['costs']['mp'], target_id=target)
        material, escrow['material'] = escrow['material'], None
        echo['upkeep'] = dict(status='active', cycle=echo['cycle'], progress=0, duration=proposal['duration'],
                              started_at=runtime['processed_years'], last_year=runtime['processed_years'],
                              material=material, escrow=escrow)
        echo['maintenance_started'] = True
        record(game, f'{echo_site(echo).name}已部署有限托管护持，预留 {escrow["total"]} 灵石；本人可继续其他活动。')
    return {'message': '托管护持已更新'}


def reconcile(deps, game):
    runtime = game.heavens_state.get('runtime')
    if not runtime:
        return
    now = runtime['processed_years']
    for echo in contacts(runtime):
        row = echo.get('upkeep')
        if row and row['status'] == 'active':
            if not game.player.alive:
                close(deps, game, echo, 'failed', now)
            elif now >= deadline(echo, row):
                close(deps, game, echo, 'expired', now)


def year_step(deps, game):
    runtime = game.heavens_state.get('runtime')
    if not runtime or game.player.world in {'lost', 'rift'}:
        return
    year = runtime['processed_years'] + 1
    for echo in contacts(runtime):
        row = echo.get('upkeep')
        if not row or row['status'] != 'active' or row['last_year'] >= year:
            continue
        if not game.player.alive or year >= deadline(echo, row):
            close(deps, game, echo, 'failed' if not game.player.alive else 'expired', year)
            continue
        row['last_year'] = year
        row['progress'] += 1
        escrow = row['escrow']
        escrow['spent'] = escrow['total'] * row['progress'] // row['duration']
        if row['progress'] == row['duration']:
            row['status'] = 'completed'
            echo['maintained'] = True
            record(game, f'{echo_site(echo).name}的托管护持完成，本周期取得维护余韵与第二次参悟名额；仍共用原收益上限。', year=year)


def project(deps, game, target, *, detail=False):
    echo = get_echo(game.heavens_state.get('runtime'), target)
    row = echo.get('upkeep') if echo else None
    result = dict(target_id=target, status=row['status'] if row else 'unavailable')
    if row:
        result.update(copy.deepcopy(row), remaining=row['escrow']['total']-row['escrow']['spent']-row['escrow']['refunded'],
                      deadline=deadline(echo, row),
                      deadline_remaining=max(0, deadline(echo, row)-game.heavens_state['runtime']['processed_years']),
                      effective=bool(echo['maintained'] and row['cycle'] == echo['cycle']))
    if not detail:
        return result
    definition = echo['definition'] if echo else vars_definition(deps)
    result.update(materials=deps.quote_materials(game, target), actions=[], duration=definition['maintain_years'],
                  budget=definition['maintain_stones']*3//2, extension_years=definition['extension_years'])
    for action, label in LABELS.items():
        options = {'material_id': result['materials'][0]['id']} if action == 'upkeep_start' and result['materials'] else {'material_id': ''} if action == 'upkeep_start' else {}
        item = dict(action=action, target_id=target, label=label, options=options)
        try:
            item.update(quote(deps, game, action, target, options), enabled=True)
        except ValueError as exc:
            item.update(enabled=False, reason=str(exc))
        result['actions'].append(item)
    return result


def vars_definition(deps):
    from dataclasses import asdict
    return asdict(deps.get_definitions().sea_echo)

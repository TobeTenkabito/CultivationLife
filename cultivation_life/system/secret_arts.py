"""Personal secret-art training and root grafting through the common time ports."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable

from ..content_registry import ContentRegistry, ITEM_CATALOG, WORLD_SYSTEMS
from ..models import HistoryRecord
from ..rules import has_item, remove_item, player_affinities
from ..runtime import decode_rng, encode_rng, now_iso
from ..secret_art_content import AFFINITIES, definitions
from ..time_dependencies import ElapsedYearDependencies, TimeSettlementDependencies
from ..time_flow import advance_elapsed_year, settle_elapsed_time, completed_action_units, ACTION_TIME
from .possession_system import advance_player_age, is_possessed


@dataclass(frozen=True)
class SecretArtDependencies:
    load: Callable
    save: Callable
    present: Callable
    commit: Callable
    year: ElapsedYearDependencies
    settlement: TimeSettlementDependencies
    refresh_market: Callable
    compact_history: Callable


def catalog():
    return definitions(ContentRegistry.loaded_documents['secret_arts.json'])


def blocked_reason(game):
    p = game.player
    if not p.alive:
        return '此生已经结束'
    if game.pending_event or game.active_trial:
        return '请先处理当前事件或劫数'
    if p.imprisonment or p.ghost_captor or is_possessed(p):
        return '拘禁、拘魂或寄身期间不能修习和施展补灵秘法'
    if game.guixu_state.get('player_session') or game.trial_site_state.get('active'):
        return '请先离开当前副本，再修习秘法'
    if p.cultivation_suppression or p.sealed_cultivation:
        return '请先解除修为压制或循原路返界，再修习补灵秘法'
    if p.world == 'celestial' and not p.immortal_power_converted:
        return '请先完成仙灵力转化'
    return ''


def materials(player, art):
    rows = []
    for item in player.inventory:
        definition = ITEM_CATALOG.get(item.id)
        if not definition or item.quantity < 1:
            continue
        tags = set(definition.tags)
        if not tags.intersection({'secret_art_core', 'secret_art_soul'}) or 'affinity:' + art['affinity'] not in tags:
            continue
        rank = next((int(t[6:]) for t in tags if t.startswith('realm:') and t[6:].isdigit()), 0)
        if rank >= art['material_realm']:
            kind = 'core' if 'secret_art_core' in tags else 'soul'
            rows.append(dict(id='item:' + item.id, name=definition.name, kind=kind, realm_index=rank, quantity=item.quantity))
    return sorted(rows, key=lambda row: (row['realm_index'], row['id']))


def project(game):
    p = game.player
    state = p.secret_art_state
    reason = blocked_reason(game)
    rows = []
    owned = set(player_affinities(p))
    for art in catalog().values():
        progress = state.get('arts', {}).get(art['id'])
        studied = progress['study_years'] if progress else 0
        required = progress['study_required'] if progress else art['study_years']
        learned = studied >= required
        cast = progress.get('casting') if progress else None
        sources = materials(p, art) if learned and art['affinity'] not in owned and not cast else []
        study_reason = reason
        if not study_reason:
            if learned:
                study_reason = '此秘法已经修成'
            elif not progress and not has_item(p, art['manual_id']):
                study_reason = '尚未取得对应秘法玉简'
            elif not progress and not has_item(p, 'spirit_stone', art['study_stones']):
                study_reason = '修习所需灵石不足'
        cast_reason = reason or ('尚未修成此秘法' if not learned else '')
        if not cast_reason and art['affinity'] in owned:
            cast_reason = '已经拥有对应灵根'
        if not cast_reason and not cast and not sources:
            cast_reason = '缺少对应属性且达到境界要求的内丹或元神'
        rows.append(dict(art, builtin=False, category='补灵', affinity_name=AFFINITIES[art['affinity']],
                         acquired=bool(progress or has_item(p, art['manual_id'])),
                         acquisition_hint=f"寻找《{art['name']}玉简》：各界普通交易、黑市与游历所得均可能出现。取得后消耗真实年份与灵石修习。",
                         has_manual=has_item(p, art['manual_id']), learned=learned, study_progress=studied,
                         study_required=required, casting=copy.deepcopy(cast), materials=sources,
                         owned=art['affinity'] in owned, study_reason=study_reason, casting_reason=cast_reason,
                         status='已补全' if art['affinity'] in owned else '施术中' if cast else '已修成' if learned else '修习中' if progress else '待修习' if has_item(p, art['manual_id']) else '未获传承'))
    config = ContentRegistry.loaded_documents['secret_arts.json']
    return dict(library=rows, revision=state.get('revision', 0), operation_reason=reason,
                drop_rates=dict(core=config['core_drop_chance'], soul=config['soul_drop_chance']))


def _consume_material(p, art, identity):
    source = next((row for row in materials(p, art) if row['id'] == identity), None)
    if not source:
        raise ValueError('所选材料已失效，或其属性、境界不满足秘法要求')
    if not remove_item(p, identity[5:]):
        raise ValueError('所选内丹或元神已经不在行囊')
    return source


def execute(deps, game_id, art_id, action, *, revision, years=None, material_id=''):
    if not all(isinstance(value, str) for value in (art_id, action, material_id)):
        raise ValueError('秘术编号、操作与材料编号必须为文本')
    original = deps.load(game_id)
    if type(revision) is not int or revision != original.player.secret_art_state.get('revision', 0):
        raise ValueError('秘法页面已过期，请刷新后重新选择')
    art = catalog().get(art_id)
    if not art or action not in {'study', 'practice'}:
        raise ValueError('未知秘法或操作')
    if years is not None and (type(years) is not int or not 1 <= years <= 100):
        raise ValueError('每次秘法修持须为一至一百个实际年')
    if reason := blocked_reason(original):
        raise ValueError(reason)
    # Publish only after saving; a failed command cannot leak paid materials into the request cache.
    game = copy.deepcopy(original)
    p = game.player
    if not p.secret_art_state:
        p.secret_art_state = dict(schema_version=1, revision=0, arts={})
    state = p.secret_art_state
    row = state['arts'].get(art_id)
    if action == 'study':
        if row and row['study_years'] >= row['study_required']:
            raise ValueError('此秘法已经修成')
        if row is None:
            if not has_item(p, art['manual_id']):
                raise ValueError('尚未取得对应秘法玉简')
            if not has_item(p, 'spirit_stone', art['study_stones']):
                raise ValueError('修习所需灵石不足')
            remove_item(p, art['manual_id'])
            if art['study_stones']:
                remove_item(p, 'spirit_stone', art['study_stones'])
            row = dict(study_years=0, study_required=art['study_years'], casting=None)
            state['arts'][art_id] = row
        progress, required = row['study_years'], row['study_required']
    else:
        if not row or row['study_years'] < row['study_required']:
            raise ValueError('尚未修成此秘法')
        if art['affinity'] in player_affinities(p):
            raise ValueError('已经拥有对应灵根，不能重复施术')
        if not row['casting']:
            source = _consume_material(p, art, material_id)
            row['casting'] = dict(years=0, required=art['casting_years'], material_name=source['name'],
                                  material_id=source['id'], material_kind=source['kind'])
        elif material_id:
            raise ValueError('原材料已经投入，续行无需再次选择材料')
        progress, required = row['casting']['years'], row['casting']['required']
    remaining = required - progress
    planned = min(remaining, years if years is not None else int(WORLD_SYSTEMS['time_units'][str(p.realm_index)]))
    rng = decode_rng(game.seed, game.rng_state)
    start_age = p.age
    source_address = (p.world, p.location_id, game.spatial_state.get('current'))
    news = []
    for _ in range(planned):
        advance_player_age(p)
        proceed = advance_elapsed_year(deps.year, game, rng, news, encounters=False)
        if not p.alive or source_address != (p.world, p.location_id, game.spatial_state.get('current')):
            break
        if action == 'study':
            row['study_years'] += 1
        else:
            row['casting']['years'] += 1
        if not proceed or blocked_reason(game):
            break
    elapsed = p.age - start_age
    unit_years = int(WORLD_SYSTEMS['time_units'][str(original.player.realm_index)])
    settle_elapsed_time(deps.settlement, game, rng, news, action='rest',
                        units=completed_action_units(elapsed, unit_years), start_age=start_age,
                        elapsed_years=elapsed, policy=ACTION_TIME)
    completed = p.alive and not blocked_reason(game)
    if action == 'study':
        completed = completed and row['study_years'] >= required
        summary = f"修习《{art['name']}》经过 {elapsed} 年，进度 {row['study_years']}/{required} 年。"
    else:
        completed = completed and row['casting']['years'] >= required
        summary = f"施展《{art['name']}》经过 {elapsed} 年，进度 {row['casting']['years']}/{required} 年。"
        if completed:
            if art['affinity'] not in player_affinities(p):
                p.additional_roots.append(art['affinity'])
            row['casting'] = None
            summary += f" 后天{AFFINITIES[art['affinity']]}灵根已补全，原灵根资质与效率不变。"
    state['revision'] += 1
    if not completed:
        summary += ' 已完成进度与已投入材料保留。'
    game.history.append(HistoryRecord('SYS_SECRET_ART_TRAINING', 1, p.age, art['name'], art_id,
                                      'completed' if completed else 'interrupted', summary,
                                      dict(action=action, elapsed_years=elapsed), ['system', 'secret_art', 'root']))
    if p.world not in {'rift', 'lost'}:
        deps.refresh_market(game, rng)
    deps.compact_history(game)
    game.rng_state = encode_rng(rng)
    game.updated_at = now_iso()
    deps.save(game)
    deps.commit(game)
    return deps.present(game)

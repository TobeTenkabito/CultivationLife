"""Validated commands; elapsed work runs through the existing time ports."""
from dataclasses import dataclass
import hashlib
import json
from typing import Callable, Any
from ..soul_rules import SECRETS, PATH_QI, wandering, body_cap, soul_cap, assimilation_cost
from ..content_registry import REALMS
from ..models import Item, SectNpc
from ..rules import add_item, qi_level, qi_level_threshold, can_practice_technique
from ..relationship_records import find_person
from ..npc_custody import detain_person, kill_person
from . import soul_lifecycle as life
from . import second_nascent as second
from .npc_soul import expired as soul_expired
from .npc_techniques import learn, resolve, levels
from .possession_system import advance_player_age, is_possessed


@dataclass(frozen=True)
class SoulDependencies:
    year: Any
    settlement: Any
    die: Callable


def blocked(game):
    p = game.player
    return (not p.alive or game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor
            or p.cultivation_suppression or p.sealed_cultivation
            or p.world in {'lost', 'rift'} or game.guixu_state.get('player_session')
            or game.trial_site_state.get('active'))


def resistance_blocked(game):
    # Internal emergency defense neither cultivates nor leaves a prison/instance.
    return not game.player.alive or game.pending_event or game.active_trial


def require(game, revision, *, crisis=False):
    unavailable = resistance_blocked(game) if crisis else blocked(game)
    if unavailable:
        raise ValueError('请先离开特殊区域，或处理事件、试炼、拘禁与修为封印')
    if type(revision) is not int or revision != game.player.nascent_state.get('revision', 0):
        raise ValueError('页面已过期，请刷新后再操作')
    if game.player.nascent_state.get('crisis') and not crisis:
        raise ValueError('请先处理神魂夺舍危机')


def captive_expiry(npc, now):
    if npc.lifespan is not None and npc.age >= npc.lifespan:
        return '寿元耗尽，无法继续炼化'
    if soul_expired(npc, now):
        return '神游超时，元婴消散'
    return None


def captive(game, identity):
    if not any(r.get('id') == identity for r in game.player.prisoners):
        raise ValueError('目标不在你的俘虏中')
    npc = find_person(game, identity, include_inactive=True)
    if (not npc or not npc.alive or npc.roster_state != 'held'
            or (npc.custody or {}).get('holder_id') != game.id
            or (npc.custody or {}).get('kind') != 'prisoner'):
        raise ValueError('原俘虏已不再可用')
    if npc.world != game.player.world:
        raise ValueError('俘虏不在当前世界，无法隔界炼化')
    reason = captive_expiry(npc, game.player.age)
    if reason:
        raise ValueError(reason)
    return npc


def conversion_quote(p, target):
    if target not in PATH_QI or target == p.path:
        raise ValueError('目标道途无效，不能转为妖修')
    cost = max(1, p.realm_index * 2)
    available = qi_level(p.qi_experience.get(PATH_QI[target], 0))
    ratio = min(1., available / cost)
    stage = sum(r.layers for r in REALMS[:p.realm_index]) + p.layer - 1
    remaining = int(stage * ratio)
    rank = 0
    while rank < len(REALMS) - 1 and remaining >= REALMS[rank].layers:
        remaining -= REALMS[rank].layers
        rank += 1
    return dict(qi=PATH_QI[target], cost=cost, available=available, rank=rank, realm_name=REALMS[rank].name, layer=remaining+1)


def conversion_token(game, target):
    """Bind confirmation to the actual source and resources, without storing a ticket."""
    p = game.player
    snapshot = dict(game=game.id, target=target, address=life.address(game),
                    path=p.path, rank=p.realm_index, layer=p.layer, age=p.age,
                    opportunity=p.opportunity, qi=p.qi_experience.get(PATH_QI[target], 0),
                    spirit=p.spirit_state, possessed=bool(p.ghost_host_body),
                    learned='path_' + target in p.nascent_state.get('known', []),
                    has_book=any(t.path == target for t in p.known_techniques),
                    revision=p.nascent_state.get('revision', 0))
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def execute(deps, game, action, payload, rng):
    p = game.player
    require(game, payload.get('revision'), crisis=action == 'resist')
    state = p.nascent_state
    identity = payload.get('id')
    if action == 'study':
        if identity not in SECRETS:
            raise ValueError('未知秘法')
        from ..soul_secret_content import acquisition_hint
        raise ValueError('秘法须通过风景探索剧情获得：' + acquisition_hint(identity))
    elif action == 'leave':
        if p.realm_index < 4 or is_possessed(p):
            raise ValueError('元婴期起可离体；寄身者请先使用原离舍入口')
        if p.soul_energy < 10:
            raise ValueError('元婴离体需要10点神魂能量')
        life.leave_body(game)
        p.soul_energy -= 10
    elif action == 'leave_host':
        from .possession_system import leave_host_body
        leave_host_body(p)
        life.leave_body(game, destroyed=True)
    elif action == 'return':
        if not wandering(p) or not p.spirit_state['body_intact']:
            raise ValueError('没有可归还的完整肉身')
        if p.spirit_state['address'] != life.address(game):
            raise ValueError('必须沿正常移动途径回到肉身所在地点与空间实例')
        p.spirit_state = {}
        life.record(game, '元婴归体，恢复普通状态。')
    elif action == 'convert':
        if 'path_' + str(identity) not in state.get('known', []):
            raise ValueError('尚未掌握目标道途的转换秘法')
        if not any(t.path == identity for t in p.known_techniques):
            raise ValueError('须学会至少一门目标道途功法')
        if is_possessed(p):
            raise ValueError('寄身期间须先离舍再转道')
        quote = conversion_quote(p, identity)
        if payload.get('quote') != conversion_token(game, identity):
            raise ValueError('转修预览已过期，请重新发动秘法并确认当前代价')
        p.qi_experience[quote['qi']] = qi_level_threshold(max(0, quote['available']-quote['cost']))
        p.realm_index, p.layer, p.path = quote['rank'], quote['layer'], identity
        p.opportunity = 0.
        p.awaiting_major_breakthrough = p.awaiting_minor_breakthrough = False
        p.active_breakthrough_aids = []
        life.record(game, f'转修新道途，消耗{quote["qi"]}气等级{min(quote["available"],quote["cost"])}；修为调整为{REALMS[p.realm_index].name}第{p.layer}层。')
    elif action == 'resist':
        if state.get('crisis') != 'possession':
            raise ValueError('当前没有夺舍危机')
        state.pop('crisis')
        chance = min(.9, .35 + p.divine_sense_rank * .025)
        if rng.random() >= chance:
            deps.die(game, '神魂枯竭后未能抵御邪魂夺舍', 'SYS_SOUL_POSSESSION', survival_stage='spirit_failed')
        else:
            life.record(game, '成功击退夺舍邪魂；神魂仍需调息恢复。')
    elif action == 'refine':
        if p.realm_index < 4:
            raise ValueError('本尊须达到元婴期才能炼化第二元婴')
        if 'second_nascent' not in state.get('known', []) or state.get('second'):
            raise ValueError('须习得第二元婴秘法，且当前没有第二元婴')
        npc = captive(game, identity)
        if npc.realm_index < 4:
            raise ValueError('俘虏尚未凝结元婴')
        row = state.get('refining')
        if row and row['id'] != identity:
            raise ValueError('请先完成或取消当前俘虏的炼化')
        if p.soul_energy < 15:
            raise ValueError('每年炼化需要15点神魂能量')
        row = state.setdefault('refining', dict(id=identity, years=0))
        p.soul_energy -= 15
        # Exactly one real year per continuation; events interrupt after paid work.
        from ..time_flow import advance_elapsed_year, settle_elapsed_time, completed_action_units, ACTION_TIME
        start = p.age
        origin = life.address(game)
        advance_player_age(p)
        advance_elapsed_year(deps.year, game, rng, [], encounters=False)
        retained = (npc.alive and npc.roster_state == 'held'
                    and (npc.custody or {}).get('holder_id') == game.id
                    and (npc.custody or {}).get('kind') == 'prisoner'
                    and npc.world == p.world
                    and any(r.get('id') == identity for r in p.prisoners)
                    and state.get('refining') is row and life.address(game) == origin)
        if retained and (reason := captive_expiry(npc, p.age)):
            kill_person(game, npc.id, reason)
            state.pop('refining', None)
            retained = False
        if p.alive and not retained:
            state.pop('refining', None)
            life.record(game, '俘虏或施术地点发生变化，炼化中断；本年时间与神魂已经消耗。')
        elif p.alive and (p.realm_index < 4 or state.get('crisis')):
            life.record(game, '本尊跌出元婴境界或陷入神魂危机，炼化中断并保留此前进度；本年时间与神魂已经消耗。')
        elif p.alive:
            row['years'] += 1
            if row['years'] >= 3:
                detain_person(game, npc.to_dict(), SectNpc, kind='second_nascent')
                p.prisoners[:] = [r for r in p.prisoners if r.get('id') != npc.id]
                npc.spirit_state = dict(mode='wandering', body_intact=False, entered=p.age,
                    deadline=p.age + life.unit_years(p), address=life.address(game))
                state['second'] = dict(id=npc.id, due=p.age+life.unit_years(p), interval=life.unit_years(p),
                                       integrity=100., control=100., age_year=p.age, auto=True, equipment=[])
                state.pop('refining')
                life.record(game, f'炼化完成，{npc.name}成为第二元婴，继承其原修为。')
        settle_elapsed_time(deps.settlement, game, rng, [], action='rest',
            units=completed_action_units(p.age-start, life.unit_years(p)), start_age=start, policy=ACTION_TIME)
    elif action == 'cancel_refine':
        state.pop('refining', None)
    elif action in {'assimilate', 'auto', 'equip', 'unequip', 'technique', 'dismiss'}:
        npc = life.second_person(game)
        if not npc:
            raise ValueError('没有可用的第二元婴')
        row = state['second']
        if action == 'assimilate':
            cost = assimilation_cost(npc.realm_index)
            if p.soul_energy < cost:
                raise ValueError('神魂能量不足以同化')
            p.soul_energy -= cost
            row['due'] = p.age + row['interval']
            row['integrity'] = min(100., row['integrity']+20)
            row['control'] = min(100., row.get('control', 100.)+20)
        elif action == 'auto':
            row['auto'] = not row['auto']
        elif action == 'equip':
            second.equip(game, identity)
        elif action == 'unequip':
            index = payload.get('index')
            if type(index) is not int or not 0 <= index < len(row['equipment']):
                raise ValueError('装备已经变动，请刷新')
            add_item(p, Item.from_dict(row['equipment'].pop(index)))
        elif action == 'technique':
            book = next((t for t in p.known_techniques if t.id == identity), None)
            if book is None and isinstance(identity, str) and identity in levels(npc):
                book = resolve(game, identity)
                if book is not None:
                    book.level = levels(npc)[identity]
            slot = payload.get('slot')
            if not isinstance(slot, str) or slot not in {'main', 'support', 'combat', 'body', 'sense', 'transformation'} or not book:
                raise ValueError('功法或栏目无效')
            if book.grade > npc.realm_index or not can_practice_technique(npc.spirit_root, book):
                raise ValueError('第二元婴的修为或灵根不符合功法要求')
            allowed = {'body': 'body', 'divine_sense': 'sense', 'transformation': 'transformation'}
            if book.category in allowed:
                valid_slot = slot == allowed[book.category]
            else:
                valid_slot = slot in {'main', 'support', 'combat'}
            if not valid_slot or book.required_body_training > int(npc.body_training or 0):
                raise ValueError('功法栏目或炼体条件不符')
            learn(npc, book, book.level, slot)
        else:
            life.consume_second(game, '本尊主动散去第二元婴')
    else:
        raise ValueError('未知神魂操作')
    life.resolve_energy(game, rng, deps.die)
    state['revision'] = state.get('revision', 0) + 1

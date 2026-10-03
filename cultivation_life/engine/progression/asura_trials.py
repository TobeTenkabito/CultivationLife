"""Resumable Asura fusion and lethal breakthrough trials."""
import copy
from dataclasses import replace

from ...content_registry import WORLD_SYSTEMS
from ...rules import combat_power, max_hp, max_mp, public_player
from ...system import asura
from ...system.combat.trials import dump_battle, load_battle, run_batch
from ...system.combat.voisinages import VoisinageBattle
from ...system.combat_system import BattleUnit, PlayerCombatSystem
from ...system.immortal_aperture import commit_energy, ensure_aperture
from ..combat_capabilities import bind_capabilities
from ..dependencies import AsuraTrialDependencies

KINDS = {'asura_conversion', 'asura_fusion', 'asura_breakthrough'}


def queue(deps: AsuraTrialDependencies, game):
    trial = game.active_trial
    event_id = trial['event_ids'][0]
    event = copy.deepcopy(deps.events_by_id[event_id])
    if trial.get('battle_state'):
        event['body'] += f' 已交战 {trial["battle_state"]["round"]} 轮，双方损耗与控制均已保存。'
    game.pending_event = deps._instantiate_event(event, game, None)


def start(deps: AsuraTrialDependencies, game, kind, *, bodies=None, route=None):
    if not asura.active(game.player) or kind not in KINDS - {'asura_conversion'}:
        raise ValueError('当前不能引发修罗劫战')
    p = game.player
    game.active_trial = dict(kind=kind, event_ids=['EVT_ASURA_FUSION' if kind == 'asura_fusion' else 'EVT_ASURA_BREAKTHROUGH'],
        old_label=public_player(p)['realm_name'], source_realm=p.realm_index, target_realm=p.realm_index + 1,
        power=combat_power(p), bodies=bodies or [], route=route)
    p.joint_companion_breakthrough = None
    initialize(game)
    queue(deps, game)


def initialize(game):
    p, trial = game.player, game.active_trial
    fusion = trial['kind'] == 'asura_fusion'
    specs = [(b['name'], b['power'] / trial['power'], False) for b in trial['bodies']] if fusion else {
        9: [('心魔', 1., False)],
        10: [('心魔', 1., True), ('域外天魔', .8, False)],
        11: [('心魔', 1.5, True), ('域外天魔', 1., True)],
    }[p.realm_index]
    members = [dict(name=name, power=trial['power'] * ratio, realm_index=p.realm_index, layer=p.layer,
                    path=p.path, kind='environment') for name, ratio, field in specs]
    target = dict(target_name='凝练肉身' if fusion else '心魔天魔劫', target_power=sum(b['power'] for b in members),
        target_realm_index=p.realm_index, target_layer=p.layer, combat_type='trial',
        objective='capture' if fusion else 'kill', enemy_objective='kill', members=members)
    units = [BattleUnit('player', p.name, 'player', trial['power'], p.realm_index, p.path,
                       integrity=min(1., p.hp / max_hp(p)))]
    binding = bind_capabilities(game, units, target, WORLD_SYSTEMS['transcendent_combat'])
    original = binding.battle
    own = original.units['player'].unit.capabilities
    copied = asura.source(p, cap=8)
    actors = []
    for key, state in original.units.items():
        actor = state.unit
        if key != 'player':
            index = int(key.split('-')[-1])
            has_field = specs[index][2]
            if fusion:
                body = trial['bodies'][index]
                tier = 2 if int(body.get('immortal_body_level') or 0) > 0 else 1
                caps = replace(actor.capabilities, capacity=own.capacity, current=own.current,
                    usable_capacity=own.usable_capacity, force_tier=tier, ward_tier=tier,
                    voisinages=(), semantic_rules=())
            else:
                caps = replace(own, voisinages=copied.voisinages if has_field else (),
                    attainments=copied.attainments if has_field else {},
                    semantic_rules=copied.semantic_rules if has_field else (),
                    investment=own.investment if has_field else 0)
            actor = replace(actor, capabilities=caps)
        actors.append(actor)
    battle = VoisinageBattle(actors)
    battle.escape_forbidden_sides = frozenset({'player', 'enemy'})
    stats = {side: PlayerCombatSystem._aggregate_stats(roster, player=p if side == 'player' else None, terrain_tags=['开阔'])
             for side, roster in (('player', units), ('enemy', PlayerCombatSystem._enemy_units(target)))}
    if not fusion:
        # Snapshot all six actual ordinary attributes, including the player's
        # existing cultivation, and scale every opponent by the declared ratio.
        total_ratio = sum(ratio for _, ratio, _ in specs)
        stats['enemy'] = {k: v * total_ratio for k, v in stats['player'].items()}
    trial['battle_state'] = dict(mode=trial['kind'], round=0, mp_ratio=min(1., p.mp / max_mp(p)), stats=stats)
    trial['snapshot'] = dump_battle(battle)
    trial['target'] = target


def resolve(deps: AsuraTrialDependencies, game, step, rng):
    trial, p = game.active_trial, game.player
    if not trial or trial.get('kind') not in KINDS or not asura.enabled():
        raise ValueError('当前没有修罗劫战')
    s = p.asura_cultivation
    if trial['kind'] == 'asura_conversion':
        stage = trial['stage']
        if step != 'asura_conversion' or stage != s.get('conversion', 0) + 1:
            raise ValueError('煞元转化顺序不符')
        s['conversion'] = stage
        ensure_aperture(p)
        # One-time conversion releases the newly converted fifth, rather than
        # refilling all resources whenever the interface is opened.
        ledger = p.immortal_aperture
        ledger['current'] = min(ledger['capacity'], ledger['current'] + ledger['capacity'] / 5)
        game.active_trial = None
        return 'trial_completed', f'煞元转化第 {stage}/5 重完成。'
    if step != 'asura_battle':
        raise ValueError('劫战步骤不匹配')
    battle = load_battle(trial['snapshot'])
    before = battle.units['player'].body
    state = trial['battle_state']
    result, rounds = run_batch(battle, state, rng)
    own = battle.units['player']
    p.hp = max(0, min(max_hp(p), p.hp + (own.body - before) * max_hp(p)))
    p.mp = min(p.mp, max_mp(p) * state['mp_ratio'])
    commit_energy(p, own.current)
    trial['snapshot'] = dump_battle(battle)
    previous = (game.last_combat_report or {}).get('rounds', []) if state['round'] > len(rounds) else []
    game.last_combat_report = dict(title='八部融合' if trial['kind'] == 'asura_fusion' else '无法无天劫',
        target_name=trial['target']['target_name'], result=result, outcome=result,
        result_grade={'victory':'战胜劫相','defeat':'身死道消','ongoing':'交战未歇'}[result],
        objective='capture' if trial['kind'] == 'asura_fusion' else 'kill', mode='修罗劫战',
        rounds=(previous + rounds)[-72:], total_rounds=state['round'], key_events=[],
        player_stats=state['stats']['player'], enemy_stats=state['stats']['enemy'],
        stat_comparison=[dict(key=k, name=n, player=state['stats']['player'][k], enemy=state['stats']['enemy'][k])
                         for k,n in [('might','威能'),('guard','防护'),('mobility','身法'),('sense','神识'),('sustain','续航'),('breach','破法')]],
        player_roster=[dict(name=p.name,power=own.unit.power,kind_name='玩家')],
        enemy_roster=[dict(name=b.unit.name,power=b.unit.power,kind_name='劫相') for b in battle.units.values() if b.unit.side=='enemy'],
        age=p.age, battlefield_tags=['开阔'], natural_terrain='开阔', artificial_conditions=[],
        player_combat_state=own.unit.power*own.vitality, player_combat_state_max=own.unit.power,
        enemy_combat_state=battle.totals['enemy']*(1-battle.ordinary_loss('enemy')), enemy_combat_state_max=battle.totals['enemy'],
        player_morale=own.morale, enemy_morale=100, enemy_hp_ratio=1-battle.ordinary_loss('enemy'),
        assessment='双方禁止逃跑，无轮数上限', capability_updates=battle.updates())
    if result == 'ongoing':
        queue(deps, game)
        return 'trial_step_success', f'已连续交战 {state["round"]} 轮，战斗尚未结束。'
    game.active_trial = None
    if result == 'defeat':
        deps._die(game, '陨落于修罗劫战', 'SYS_ASURA_TRIAL_FAILED')
        return 'dead', '未能镇压劫相，身死道消。'
    if trial['kind'] == 'asura_fusion':
        route = trial['route']
        ids = {b['id'] for b in trial['bodies']}
        s['bodies'] = [b for b in s['bodies'] if b['id'] not in ids]
        s.update(route=route, level=1, domain_rank=1, domain_power=0,
                 domain_name=rng.choice(asura.config()['branch_prefixes']) + asura.ROUTE_NAMES[route] + '魔域',
                 inherited_power=sum(b['power'] for b in trial['bodies']))
        return 'trial_completed', f'凝身入{asura.ROUTE_NAMES[route]}部，永久继承肉身战力 {s["inherited_power"]:.0f}。'
    deps._complete_major_breakthrough(game, rng, trial['old_label'])
    return 'trial_completed', '心魔与天魔尽灭，破境成功。'

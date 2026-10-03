"""Celestial trial application boundary: authored opponents, snapshots and save writes."""
import copy
from dataclasses import asdict, replace

from ...content_registry import WORLD_SYSTEMS
from ...models import HistoryRecord
from ...rules import combat_power, expected_combat_power, max_hp, max_mp, public_player
from ...system.doctrine.provider import player_record, config
from ...system.doctrine.progression import source
from ...system.doctrine.voisinage_training import rank, label, base_multiplier
from ...system.combat.contracts import VoisinageDefinition, VoisinageEffect
from ...system.combat.trials import dump_battle, load_battle, run_batch
from ...system.combat_system import PlayerCombatSystem, BattleUnit
from ...system.combat_adapter import bind_capabilities
from ..dependencies import ImmortalTrialDependencies

KINDS = {'human_decline', 'heaven_decline', 'three_corpses', 'voisinage_backlash'}
TITLES = {'human_decline': '人五衰', 'heaven_decline': '天五衰', 'three_corpses': '斩三尸',
          'voisinage_backlash': '道统反噬'}
EVENTS = {kind: f'EVT_IMMORTAL_TRIAL_{kind.upper()}' for kind in KINDS}


def chosen_field(game, key=None, *, cap=None):
    record = copy.deepcopy(player_record(game))
    key = key or record.get('active')
    record['active'] = key
    if cap is not None:
        training = record.setdefault('voisinage_training', {}).setdefault(key, {})
        training['rank'] = min(cap, rank(training))
    fields = source(record, game.doctrine_state.get('definitions', {}), 'celestial',
                    training_gain=config()['cultivation']['voisinage_training_gain']).voisinages
    return fields[0] if fields else None


def heaven_field(strength, *, name='天域'):
    return VoisinageDefinition('trial:heaven', name, 'heaven', 1, strength, 80, 45,
        'strike', 35, .24, stability=strength, incursion=strength, authority=100,
        max_targets=1, effects=(VoisinageEffect('strike', 35, .24, defense='ward'),))


def state_for(field=None):
    return dict(capacity=10000, current=10000, conversion=1, force_tier=2, attack_cost=10,
                voisinage_ids=[field.id] if field else [], attainments={field.attainment: 9} if field else {})


def target_for(game, trial):
    p, kind = game.player, trial['kind']
    definitions = []
    if kind == 'three_corpses':
        field = trial.get('corpse_field')
        field = VoisinageDefinition(**field) if field else None
        if field:
            field = replace(field, id='trial:superego', attainment='superego', name='超我尸·' + field.name)
            definitions.append(asdict(field))
        members = [dict(name=f'{p.name}·{name}', power=trial['power'] * ratio, realm_index=p.realm_index, layer=p.layer,
                        path=p.path, kind='environment', transcendence=state_for(field if i == 2 else None))
                   for i, (name, ratio) in enumerate(zip(('自我尸', '本我尸', '超我尸'), (.38, .42, .60)))]
    else:
        field = None
        strength = 0
        if kind == 'heaven_decline':
            strength = 235
        elif kind == 'voisinage_backlash':
            # A fixed trial of this tradition, not an enemy which scales with
            # extra tempering. Defensive preparation can overtake the backlash.
            original = game.doctrine_state['definitions'][trial['doctrine_id']]['stages'][
                player_record(game)['progress'][trial['doctrine_id']]['level'] - 1]['voisinage']
            factors = {5: 1.12, 9: 1.20, 13: 1.42}
            # The attained perfection bonus rewards surviving this trial;
            # it must not strengthen the trial before that reward is earned.
            strength = original['stability'] * base_multiplier(trial['target_rank']) * factors[trial['target_rank']]
        if strength:
            field = heaven_field(strength, name='大道同化·天域' if kind == 'voisinage_backlash' else '天五衰·天域')
            definitions.append(asdict(field))
        power = expected_combat_power(p.realm_index, 9) * (1.15 if kind == 'heaven_decline' else 1.0)
        members = [dict(name='天道', power=power, realm_index=p.realm_index, layer=p.layer,
                        kind='environment', path='dao', transcendence=state_for(field))]
    return dict(target_name=f'{p.name}的三尸' if kind == 'three_corpses' else TITLES[kind], target_power=sum(m['power'] for m in members), members=members,
                target_realm_index=p.realm_index, target_layer=p.layer, combat_type='trial',
                objective='kill', enemy_objective='kill', voisinages=definitions)


def queue(deps: ImmortalTrialDependencies, game, *, ongoing=False):
    trial = game.active_trial
    event = copy.deepcopy(deps.events_by_id[EVENTS[trial['kind']]])
    event['body'] += (' 已连续交战 ' + str(trial['battle_state']['round']) + ' 轮；所有损耗与控制均已保存，继续不会重置战斗。'
                      if ongoing else ' 出战邻域已锁定：' + trial.get('field_name', '未装备邻域') + '。')
    # Use the ordinary event presenter; choices remain validated against content.
    game.pending_event = deps._instantiate_event(event, game, None)


def start(deps: ImmortalTrialDependencies, game, kind, *, doctrine_id=None):
    if kind not in KINDS:
        raise ValueError('未知仙境劫难')
    p, record = game.player, player_record(game)
    key = doctrine_id or record.get('active')
    selected = chosen_field(game, key)
    trial = dict(kind=kind, major=kind != 'voisinage_backlash', old_label=public_player(p)['realm_name'],
                 source_realm=p.realm_index, target_realm=p.realm_index + 1, step_index=0,
                 event_ids=[EVENTS[kind]], lethal=True, doctrine_id=key,
                 field_name=selected.name if selected else '未装备邻域', power=combat_power(p))
    if kind == 'voisinage_backlash':
        if not selected:
            raise ValueError('未激发邻域不能引发道统反噬')
        trial['target_rank'] = rank(record.get('voisinage_training', {}).get(key, {})) + 1
    if kind == 'three_corpses':
        copied = chosen_field(game, key, cap=8)
        trial['corpse_field'] = asdict(copied) if copied else None
    game.active_trial = trial
    p.joint_companion_breakthrough = None
    queue(deps, game)


def initialize(game, trial):
    p = game.player
    target = target_for(game, trial)
    # No friends, spouses, disciples or puppets may enter an inner tribulation.
    units = [BattleUnit('player', p.name, 'player', combat_power(p), p.realm_index, p.path,
                       integrity=min(1, max(.001, p.hp / max_hp(p))))]
    record = player_record(game)
    old = record.get('active')
    record['active'] = trial['doctrine_id']
    try:
        binding = bind_capabilities(game, units, target, WORLD_SYSTEMS['transcendent_combat'])
    finally:
        record['active'] = old
    battle = binding.battle
    if trial['kind'] == 'three_corpses':
        # The copy has the same resource budget, not an inexhaustible reservoir.
        own = battle.units['player'].unit.capabilities
        for key, state in battle.units.items():
            if key != 'player':
                state.unit = replace(state.unit, capabilities=replace(state.unit.capabilities,
                    capacity=own.capacity, current=own.current, usable_capacity=own.usable_capacity,
                    investment=own.investment if key == 'enemy-2' else 0,
                    investment_limit=own.investment_limit if key == 'enemy-2' else None))
                state.current = own.current
    stats = {side: PlayerCombatSystem._aggregate_stats(roster, player=p if side == 'player' else None,
                                                       terrain_tags=['开阔'])
             for side, roster in (('player', units), ('enemy', PlayerCombatSystem._enemy_units(target)))}
    trial['battle_state'] = dict(mode=trial['kind'], round=0, mp_ratio=min(1, p.mp / max_mp(p)), stats=stats)
    trial['snapshot'] = dump_battle(battle)
    trial['target'] = target
    return battle


def resolve(deps: ImmortalTrialDependencies, game, step, rng):
    trial = game.active_trial
    if not trial or trial.get('kind') not in KINDS or step != 'immortal_battle':
        raise ValueError('当前没有对应的仙境劫战')
    battle = load_battle(trial['snapshot']) if 'snapshot' in trial else initialize(game, trial)
    if trial['kind'] == 'three_corpses':
        for state in battle.units.values():
            if state.unit.side == 'enemy' and state.unit.name in {'自我尸', '本我尸', '超我尸'}:
                state.unit = replace(state.unit, name=f'{game.player.name}·{state.unit.name}')
    state = trial['battle_state']
    before_body = battle.units['player'].body
    result, rounds = run_batch(battle, state, rng)
    p = game.player
    own = battle.units['player']
    p.hp = max(0, min(max_hp(p), p.hp + (own.body - before_body) * max_hp(p)))
    p.mp = min(p.mp, max_mp(p) * state['mp_ratio'])
    from ...system.immortal_aperture import commit_energy
    if p.transcendence is None:
        commit_energy(p, own.current)
    elif own.unit.capabilities.resource_link == 'legacy_mp':
        p.mp = own.current
    else:
        p.transcendence['current'] = own.current
    trial['snapshot'] = dump_battle(battle)
    previous = (game.last_combat_report or {}).get('rounds', []) if state['round'] > len(rounds) else []
    report = dict(title=TITLES[trial['kind']], target_name=f'{p.name}的三尸' if trial['kind'] == 'three_corpses' else TITLES[trial['kind']], result=result,
        outcome=result, result_grade={'victory':'渡劫成功','defeat':'劫中陨落','ongoing':'交战未歇'}[result],
        objective='kill' if trial['kind'] == 'three_corpses' else 'survive', mode='仙境劫战',
        rounds=(previous + rounds)[-72:], total_rounds=state['round'], key_events=[],
        player_stats=state['stats']['player'], enemy_stats=state['stats']['enemy'],
        stat_comparison=[dict(key=k, name=n, player=state['stats']['player'][k], enemy=state['stats']['enemy'][k])
                         for k,n in [('might','威能'),('guard','防护'),('mobility','身法'),('sense','神识'),('sustain','续航'),('breach','破法')]],
        age=p.age, assessment='五轮生存考验' if trial['kind'] != 'three_corpses' else '必须斩灭全部三尸',
        player_roster=[{'name':p.name,'power':battle.units['player'].unit.power,'kind_name':'玩家'}],
        enemy_roster=[{'name':s.unit.name,'power':s.unit.power,'kind_name':'劫相'} for s in battle.units.values() if s.unit.side=='enemy'],
        battlefield_tags=['开阔'], natural_terrain='开阔', artificial_conditions=[],
        player_combat_state=own.unit.power*own.vitality, player_combat_state_max=own.unit.power,
        enemy_combat_state=battle.totals['enemy']*(1-battle.ordinary_loss('enemy')),
        enemy_combat_state_max=battle.totals['enemy'], player_morale=own.morale, enemy_morale=100,
        enemy_hp_ratio=1-battle.ordinary_loss('enemy'), capability_updates=battle.updates())
    game.last_combat_report = report
    if result == 'ongoing':
        queue(deps, game, ongoing=True)
        return 'trial_step_success', f'三尸尚未尽灭，已交战 {state["round"]} 轮；继续交战不会补满任何资源。'
    game.active_trial = None
    if result == 'defeat':
        reason = '冲击至臻时被道统同化' if trial.get('target_rank') == 13 else f'未能渡过{TITLES[trial["kind"]]}'
        deps._die(game, reason, 'SYS_IMMORTAL_TRIAL_FAILED')
        report['result'] = 'dead'
        return 'dead', reason + '，身死道消。'
    if trial['kind'] == 'voisinage_backlash':
        player_record(game).setdefault('voisinage_training', {}).setdefault(trial['doctrine_id'], {})['rank'] = trial['target_rank']
        message = f'以邻域对抗天域存活五轮，修至{label(trial["target_rank"])}。'
    else:
        deps._complete_major_breakthrough(game, rng, trial['old_label'])
        message = '三尸已全部斩灭，证得大罗。' if trial['kind']=='three_corpses' else f'在{TITLES[trial["kind"]]}中存活五轮，破境成功。'
    report['key_events'].append(message)
    game.history.append(HistoryRecord('SYS_IMMORTAL_TRIAL', 1, p.age, TITLES[trial['kind']], None,
                                     'success', message, {}, ['system','trial','cultivation']))
    return 'trial_completed', message

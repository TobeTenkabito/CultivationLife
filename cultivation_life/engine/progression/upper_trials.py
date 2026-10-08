"""Player-snapshot monster/ghost trials, independent from domain cultivation."""
import copy
from dataclasses import dataclass, replace
from typing import Callable

from ...content_registry import WORLD_SYSTEMS, CONTENT_DOCUMENTS
from ...rules import combat_power, max_hp, max_mp, public_player
from ...system.combat_system import BattleUnit, PlayerCombatSystem
from ...system.combat_adapter import bind_capabilities
from ...system.combat.voisinages import VoisinageBattle
from ...system.combat.trials import dump_battle, load_battle, run_batch
from ...system.upper_voisinage_rules import player_source
from ...system.immortal_aperture import commit_energy
from ...system import ghost_soul_form
from ...system.possession_system import is_possessed

KINDS = {'monster_upper', 'ghost_upper'}
TITLES = {'monster_upper': ('蜕形劫', '祖性劫', '万象劫'), 'ghost_upper': ('辨魂劫', '前尘劫', '轮回劫')}
NAMES = {'monster_upper': (('血脉劫相',), ('祖性劫相',), ('本相劫身', '万象劫主')),
         'ghost_upper': (('伪我劫相',), ('前尘劫主',), ('生相', '灭相'))}


@dataclass(frozen=True)
class Dependencies:
    events: Callable
    instantiate: Callable
    die: Callable
    complete: Callable
    monster_complete: Callable


def eligible(p):
    if is_possessed(p) or p.realm_index not in {9, 10, 11}:
        return False
    return ((p.path == 'ghost' and p.world == 'reincarnation' and bool(ghost_soul_form.catalog())) or
            (p.path == 'monster' and p.world == 'nether' and bool(CONTENT_DOCUMENTS.get('monster_true_forms.json'))))


def queue(deps, game):
    t = game.active_trial
    event = copy.deepcopy(deps.events()[t['event_ids'][0]])
    event['title'] = t['title']
    event['body'] += f"\n当前选定邻域：{t['field_name']}。已交战 {t['battle_state']['round']} 轮。损耗连续保存，续战不补满资源。"
    game.pending_event = deps.instantiate(event, game, None)


def start(deps, game, kind, *, evolution=None, lineage=None):
    p = game.player
    if kind not in KINDS or not eligible(p) or kind != p.path + '_upper' or game.active_trial:
        raise ValueError('当前无法引发此道途劫难')
    stage = p.realm_index - 9
    source = player_source(p, cap=8)
    names = NAMES[kind][stage]
    if kind == 'monster_upper' and stage == 1 and '_SELF_' in str(p.monster_evolution_id):
        names = ('新脉劫相',)
    power = combat_power(p)
    members = [dict(name=name, power=power, realm_index=p.realm_index, layer=p.layer, path=p.path, kind='environment') for name in names]
    target = dict(target_name=TITLES[kind][stage], target_power=power*len(names), members=members,
                  target_realm_index=p.realm_index, target_layer=p.layer, combat_type='trial', objective='kill', enemy_objective='kill')
    units = [BattleUnit('player', p.name, 'player', power, p.realm_index, p.path, integrity=min(1., p.hp/max_hp(p)))]
    original = bind_capabilities(game, units, target, WORLD_SYSTEMS['transcendent_combat']).battle
    own = original.units['player'].unit.capabilities
    actors = []
    for key, state in original.units.items():
        actor = state.unit
        if key != 'player':
            fields = tuple(replace(f, id=f'{key}:{f.id}', attainment=f'{key}:{f.attainment}', name=f'{actor.name}·{f.name}') for f in source.voisinages) if stage else ()
            actor = replace(actor, capabilities=replace(own, voisinages=fields,
                attainments={f.attainment: 9 for f in fields}, semantic_rules=(),
                investment=own.investment if fields else 0))
        actors.append(actor)
    battle = VoisinageBattle(actors)
    battle.escape_forbidden_sides = frozenset({'player', 'enemy'})
    stats = PlayerCombatSystem._aggregate_stats(units, player=p, terrain_tags=['开阔'])
    state = dict(mode='upper_final' if stage == 2 else 'upper_endurance', round=0,
                 mp_ratio=min(1., p.mp/max_mp(p)), stats={'player':stats, 'enemy':{k:v*len(names) for k,v in stats.items()}})
    p.joint_companion_breakthrough = None
    game.active_trial = dict(kind=kind, major=True, lethal=True, old_label=public_player(p)['realm_name'],
        source_realm=p.realm_index, target_realm=p.realm_index+1, title=TITLES[kind][stage],
        field_name=' / '.join(f.name for f in own.voisinages) or '未装备邻域',
        event_ids=['EVT_UPPER_FINAL' if stage == 2 else 'EVT_UPPER_ENDURANCE'],
        snapshot=dump_battle(battle), battle_state=state, target=target,
        evolution=copy.deepcopy(evolution), lineage=copy.deepcopy(lineage))
    queue(deps, game)


def resolve(deps, game, step, rng):
    t, p = game.active_trial, game.player
    if not t or t.get('kind') not in KINDS or step != 'upper_battle':
        raise ValueError('当前没有对应妖鬼劫战')
    if not eligible(p) or p.realm_index != t['source_realm']:
        raise ValueError('劫战资格发生变化，请恢复原道途与 DLC')
    battle = load_battle(t['snapshot'])
    before = battle.units['player'].body
    state = t['battle_state']
    result, rounds = run_batch(battle, state, rng)
    own = battle.units['player']
    p.hp = max(0, min(max_hp(p), p.hp+(own.body-before)*max_hp(p)))
    p.mp = min(p.mp, max_mp(p)*state['mp_ratio'])
    commit_energy(p, own.current)
    t['snapshot'] = dump_battle(battle)
    previous = (game.last_combat_report or {}).get('rounds', []) if state['round'] > len(rounds) else []
    final = state['mode'] == 'upper_final'
    report = dict(title=t['title'], target_name=t['title'], result=result, outcome=result,
        result_grade={'victory':'渡劫成功','defeat':'劫中陨落','ongoing':'交战未歇'}[result],
        objective='kill' if final else 'survive', mode='妖鬼劫战', age=p.age,
        assessment='击杀全部劫相，无轮数上限' if final else '存活完整五轮即可过关，无需击杀',
        rounds=(previous+rounds)[-72:], total_rounds=state['round'], key_events=[],
        player_stats=state['stats']['player'], enemy_stats=state['stats']['enemy'],
        stat_comparison=[dict(key=k,name=n,player=state['stats']['player'][k],enemy=state['stats']['enemy'][k]) for k,n in
            [('might','威能'),('guard','防护'),('mobility','身法'),('sense','神识'),('sustain','续航'),('breach','破法')]],
        player_roster=[dict(name=p.name,power=own.unit.power,kind_name='玩家')],
        enemy_roster=[dict(name=s.unit.name,power=s.unit.power,kind_name='劫相') for s in battle.units.values() if s.unit.side=='enemy'],
        player_combat_state=own.unit.power*own.vitality, player_combat_state_max=own.unit.power,
        enemy_combat_state=battle.totals['enemy']*(1-battle.ordinary_loss('enemy')), enemy_combat_state_max=battle.totals['enemy'],
        enemy_hp_ratio=1-battle.ordinary_loss('enemy'), player_morale=own.morale, enemy_morale=100,
        battlefield_tags=['开阔'], natural_terrain='开阔', artificial_conditions=[], capability_updates=battle.updates())
    game.last_combat_report = report
    if result == 'ongoing':
        queue(deps, game)
        return 'trial_step_success', f'已交战 {state["round"]} 轮，损耗保存，请继续迎劫。'
    game.active_trial = None
    if result == 'defeat':
        deps.die(game, f'陨落于{t["title"]}', 'SYS_UPPER_TRIAL_FAILED')
        return 'dead', f'未能渡过{t["title"]}，身死道消。'
    if t.get('evolution'):
        deps.monster_complete(game, t['evolution'], t.get('lineage'), rng)
    else:
        deps.complete(game, rng, t['old_label'])
    summary = f'{t["title"]}已过，破境成功。'
    report['key_events'].append(summary)
    return 'trial_completed', summary


def soul_resolve(game, step):
    t = game.active_trial
    if not t or t.get('kind') != 'soul_contemplation' or not step.startswith('soul_'):
        raise ValueError('当前没有照魂试炼')
    if step == 'soul_cancel':
        game.active_trial = None
        return 'resolved', '暂不定性，保留本魂与前尘；已用参悟时间不返还。'
    route = step.removeprefix('soul_')
    summary = ghost_soul_form.confirm(game, t['cause'], route)
    game.active_trial = None
    return 'resolved', summary

"""Resumable trial rounds, using shared coverage/effects and six-stat damage.

Five-round endurance and unlimited lethal duels have different victory rules.
The batch size limits one request's work, never the battle's duration. Snapshots
contain only bounded actor state; they do not consult or advance the NPC world.
"""
from dataclasses import asdict
import copy

from .contracts import Combatant, CombatCapabilities, VoisinageDefinition
from .voisinages import VoisinageBattle
from .ordinary import exchange_damage


def dump_battle(battle):
    return {'units': [asdict(s.unit) for s in battle.units.values()],
            'states': {key: {k: copy.deepcopy(v) for k, v in vars(s).items() if k != 'unit'}
                       for key, s in battle.units.items()}, 'dominated': dict(battle._dominated)}


def load_battle(snapshot):
    units = []
    for raw in snapshot['units']:
        row = copy.deepcopy(raw)
        caps = row.pop('capabilities')
        caps['voisinages'] = tuple(VoisinageDefinition(**d) for d in caps['voisinages'])
        units.append(Combatant(**row, capabilities=CombatCapabilities(**caps)))
    battle = VoisinageBattle(units)
    for key, values in snapshot['states'].items():
        for name, value in values.items():
            setattr(battle.units[key], name, copy.deepcopy(value))
    battle._dominated = dict(snapshot['dominated'])
    return battle


def run_batch(battle, state, rng, *, batch_size=24):
    """Return victory/defeat/ongoing, and at most batch_size real round rows."""
    battle.set_objectives('kill', 'kill')
    rows = []
    endurance = state['mode'] != 'three_corpses'
    only_fields = state['mode'] == 'voisinage_backlash'
    player = battle.units['player']
    for _ in range(batch_size):
        n = state.get('round', 0) + 1
        if endurance:
            # The Dao's manifestation reforms. Damaging it never shortens the
            # five rounds, nor creates a kill, captive, loot or social relation.
            for s in battle.units.values():
                if s.unit.side == 'enemy':
                    s.vitality = s.body = 1
                    s.suppressed = s.escaped = False
                    s.pressure = s.field_strain = 0
                    s.controls.clear()
                    s.current = s.unit.capabilities.capacity
        frame = battle.begin_round(n, player_condition=player.vitality, enemy_condition=1,
                                   player_mp=state['mp_ratio'], enemy_mp=1)
        dealt = received = 0
        initiative = 'voisinage'
        if not only_fields and player.fighting:
            # Incapacitation is not a kill. A living, free caster must still
            # possess a valid attack before finishing an immobilized corpse.
            if not endurance and battle._available('player'):
                for key, victim in battle.units.items():
                    if victim.unit.side == 'enemy' and (0 < victim.vitality <= .12 or victim.suppressed):
                        if battle.attack_tier(player) >= victim.unit.capabilities.ward_tier:
                            battle.attack_tier(player, pay=True)
                            battle._lose(key, victim.vitality)
                            victim.suppressed = False
                            frame.events.append(f'你以可用的主战手段彻底斩灭{victim.unit.name}。')
            stats = copy.deepcopy(state['stats'])
            for side in ('player', 'enemy'):
                for stat, factor in frame.stat_factors.get(side, {}).items():
                    stats[side][stat] *= factor
            p, e = stats['player'], stats['enemy']
            enemy_condition = max(.05, 1 - battle.ordinary_loss('enemy'))
            p_condition = max(.05, player.vitality) * (.65 + .35 * state['mp_ratio'])
            p_condition *= .6 + .4 * player.morale / 100
            first = p['mobility'] + p['sense'] >= e['mobility'] + e['sense']
            initiative = 'player' if first else 'enemy'
            dealt = exchange_damage(p['might'] * p_condition, e['guard'] * (.72 + .28 * enemy_condition),
                                    p['breach'] / max(1, e['guard']), rng.uniform(.9, 1.1),
                                    coefficient=.135, minimum=.045, maximum=.42)
            received = exchange_damage(e['might'] * enemy_condition, p['guard'] * (.72 + .28 * player.vitality),
                                       e['breach'] / max(1, p['guard']), rng.uniform(.9, 1.1),
                                       coefficient=.125, minimum=.035, maximum=.4)
            # The actual golden-body passive helps withstand heavenly decay.
            if player.unit.capabilities.ward_tier >= 2:
                received *= .75
            dealt *= 1.05 if first else .97
            received *= .96 if first else 1.04
            dealt, received = battle.ordinary_damage(dealt, received)
            if frame.ordinary_player:
                state['mp_ratio'] = max(0, state['mp_ratio'] - .035)
            frame.events.append(f'本轮普通交锋：敌方态势损耗 {dealt:.1%}，己方态势损耗 {received:.1%}。')
        battle.finish_round(player_mp=state['mp_ratio'], enemy_mp=1)
        state['round'] = n
        rows.append({'round': n, 'initiative': initiative if frame.ordinary else 'voisinage',
                     'events': list(frame.events), 'player_hp_ratio': max(0, player.vitality),
                     'enemy_hp_ratio': max(0, 1 - battle.ordinary_loss('enemy')),
                     'player_mp_ratio': state['mp_ratio'], 'player_morale': player.morale,
                     'enemy_morale': 100, 'voisinage': battle.report(),
                     'player_combat_state': player.unit.power * player.vitality,
                     'player_combat_state_max': player.unit.power,
                     'enemy_combat_state': battle.totals['enemy'] * max(0, 1 - battle.ordinary_loss('enemy')),
                     'enemy_combat_state_max': battle.totals['enemy']})
        if not player.fighting or player.body <= 0:
            return 'defeat', rows
        if endurance and n >= 5:
            return 'victory', rows
        if not endurance and battle.enemy_killed():
            return 'victory', rows
    return 'ongoing', rows

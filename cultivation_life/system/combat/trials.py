"""Resumable trial rounds, using shared coverage/effects and six-stat damage.

Five-round endurance and unlimited lethal duels have different victory rules.
The batch size limits one request's work, never the battle's duration. Snapshots
contain only bounded actor state; they do not consult or advance the NPC world.
"""
from dataclasses import asdict
import copy
from math import isfinite

from .contracts import Combatant, CombatCapabilities, VoisinageDefinition,ResourceSupply,VoisinageSeal
from .voisinages import VoisinageBattle
from .ordinary import exchange_damage
from .field_contracts import validate_memory,validate_leases


def dump_battle(battle):
    return {'units': [asdict(s.unit) for s in battle.units.values()],
            'objectives':dict(battle.objectives),'contest_ratio':battle.contest_ratio,
            'supplies':[asdict(s) for s in battle.supplies], 'seals':[asdict(s) for s in battle.seals],
            'applied_seals':sorted(battle._applied_seals),
            'death_exempt':sorted(battle._death_exempt),
            **({'semantic_runtime': battle.semantics.dump()} if battle.semantics else {}),
            **({'technique_runtime': battle.techniques.dump()} if battle.techniques else {}),
            **({'semantic_environment': dict(battle._semantic_environment)} if battle.semantics else {}),
            'states': {key: {k: copy.deepcopy(v) for k, v in vars(s).items() if k != 'unit'}
                       for key, s in battle.units.items()}, 'dominated': dict(battle._dominated),
            'escape_forbidden_sides': sorted(battle.escape_forbidden_sides)}


def load_battle(snapshot):
    units = []
    for raw in snapshot['units']:
        row = copy.deepcopy(raw)
        caps = row.pop('capabilities')
        caps['voisinages'] = tuple(VoisinageDefinition(**d) for d in caps['voisinages'])
        units.append(Combatant(**row, capabilities=CombatCapabilities(**caps)))
    battle = VoisinageBattle(units,contest_ratio=snapshot.get('contest_ratio',1.25),
        supplies=tuple(ResourceSupply(**r) for r in snapshot.get('supplies',())),
        seals=tuple(VoisinageSeal(**r) for r in snapshot.get('seals',())))
    objectives=snapshot.get('objectives',{'player':'kill','enemy':'kill'})
    if not isinstance(objectives,dict) or set(objectives)!={'player','enemy'}:
        raise ValueError('Invalid battle objectives')
    battle.set_objectives(objectives['player'],objectives['enemy'])
    applied=snapshot.get('applied_seals',[])
    if (not isinstance(applied,list) or any(type(i) is not int or not 0<=i<len(battle.seals) for i in applied)
            or len(set(applied))!=len(applied)):
        raise ValueError('Invalid applied seal snapshot')
    battle._applied_seals=set(applied)
    exempt=snapshot.get('death_exempt',[])
    if not isinstance(exempt,list) or any(not isinstance(k,str) or k not in battle.units for k in exempt) or len(set(exempt))!=len(exempt):
        raise ValueError('Invalid nonlethal unit snapshot')
    battle._death_exempt=frozenset(exempt)
    for key, values in snapshot['states'].items():
        for field in ('mana_current','supply_mp_spent'):
            value=values.get(field,0.)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or value<0:
                raise ValueError('Invalid battle mana snapshot')
        if values.get('mana_current',0)>battle.units[key].unit.capabilities.mana_capacity:
            raise ValueError('Battle mana exceeds capacity')
        charge=values.get('operating_energy')
        initial=battle.units[key].unit.capabilities.operating_energy
        if charge is not None and (isinstance(charge,bool) or not isinstance(charge,(int,float)) or not isfinite(charge)
                                   or initial is None or not 0<=charge<=initial):
            raise ValueError('Invalid operating energy snapshot')
        if initial is not None and charge is None:
            raise ValueError('Missing operating energy snapshot')
        validate_memory(values.get('field_memory',{}),battle.units)
        validate_leases(values.get('timed_controls',{}),values.get('field_debts',{}),battle.units)
        recovery=values.get('release_recovery_round',0)
        if type(recovery) is not int or not 0<=recovery<=1000000000:
            raise ValueError('Invalid release recovery round')
        credit=values.get('karma_spent',0.)
        history=values.get('last_attack_targets')
        if (isinstance(credit,bool) or not isinstance(credit,(int,float)) or not isfinite(credit) or not 0<=credit<1
                or type(values.get('death_observed',False)) is not bool):
            raise ValueError('Invalid body event snapshot')
        if history is not None:
            if (not isinstance(history,(list,tuple)) or any(not isinstance(k,str) or k not in battle.units for k in history)
                    or len(set(history))!=len(history)):
                raise ValueError('Invalid attack target history')
        for name, value in values.items():
            setattr(battle.units[key], name, tuple(value) if name=='last_attack_targets' and value is not None else copy.deepcopy(value))
    battle._dominated = dict(snapshot['dominated'])
    battle.escape_forbidden_sides = frozenset(snapshot.get('escape_forbidden_sides', ()))
    if snapshot.get('semantic_runtime'):
        if battle.semantics is None:
            raise ValueError('Semantic snapshot has no rules')
        battle.semantics.restore(snapshot['semantic_runtime'])
        battle._semantic_environment = dict(snapshot.get('semantic_environment', {}))
        from ...combat_semantics import FACTS
        if any(key not in FACTS or not key.startswith('environment.') or type(value) is not FACTS[key][0]
               for key, value in battle._semantic_environment.items()):
            raise ValueError('Invalid semantic environment snapshot')
    if battle.techniques:
        if 'technique_runtime' not in snapshot:
            raise ValueError('Missing paid technique runtime snapshot')
        battle.techniques.restore(snapshot['technique_runtime'])
    elif 'technique_runtime' in snapshot:
        raise ValueError('Technique runtime has no owning capabilities')
    return battle


def run_batch(battle, state, rng, *, batch_size=24):
    """Return victory/defeat/ongoing, and at most batch_size real round rows."""
    battle.set_objectives('capture' if state['mode'] == 'asura_fusion' else 'kill', 'kill')
    battle.escape_forbidden_sides = battle.escape_forbidden_sides | (
        {'enemy', 'player'} if state['mode'].startswith(('asura_', 'upper_')) else {'enemy'})
    # Old snapshots may contain a living manifestation which escaped. Bring
    # it back without restoring any health or resources; escape is not a kill.
    for unit in battle.units.values():
        if unit.unit.side == 'enemy':
            unit.escaped = False
    rows = []
    asura_trial = state['mode'] in {'asura_fusion', 'asura_breakthrough', 'upper_final', 'upper_endurance'}
    fusion = state['mode'] == 'asura_fusion'
    endurance = state['mode'] not in {'three_corpses', 'asura_fusion', 'asura_breakthrough', 'upper_final'}
    only_fields = state['mode'] == 'voisinage_backlash'
    battle._death_exempt=frozenset(k for k,s in battle.units.items() if endurance and s.unit.side=='enemy')
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
                    s.current = battle._usable_energy(s)
                    s.death_observed=False
        scores={side:state['stats'][side]['mobility']+state['stats'][side]['sense'] for side in ('player','enemy')}
        frame = battle.begin_round(n, player_condition=player.vitality, enemy_condition=1,
                                   player_mp=state['mp_ratio'], enemy_mp=1,rng=rng,
                                   first_side='player' if scores['player']>=scores['enemy'] else 'enemy')
        state['mp_ratio']=battle.mp_ratio('player',state['mp_ratio'])
        dealt = received = 0
        initiative = 'voisinage'
        exchange = None
        if not only_fields and player.fighting:
            # Incapacitation is not a kill. A living, free caster must still
            # possess a valid attack before finishing an immobilized corpse.
            if not endurance and battle._available('player'):
                for key, victim in battle.units.items():
                    if victim.unit.side == 'enemy' and (0 < victim.vitality <= .12 or victim.suppressed):
                        if battle.attack_tier(player) >= battle.ward_tier(key):
                            battle.attack_tier(player, pay=True)
                            battle._lose(key, victim.vitality)
                            battle._drain_body_events()
                            victim.suppressed = False
                            frame.events.append(f'你以可用的主战手段彻底斩灭{victim.unit.name}。')
            stats = copy.deepcopy(state['stats'])
            semantic_factors = battle.semantic_ordinary_start()
            state['mp_ratio'] = battle.mp_ratio('player', state['mp_ratio'])
            for side in ('player', 'enemy'):
                for stat, factor in frame.stat_factors.get(side, {}).items():
                    stats[side][stat] *= factor
                for stat, factor in semantic_factors[side].items():
                    stats[side][stat] *= factor
            p, e = stats['player'], stats['enemy']
            enemy_condition = max(.05, 1 - battle.ordinary_loss('enemy'))
            p_condition = max(.05, player.vitality) * (.65 + .35 * state['mp_ratio'])
            enemy_condition *= e['sustain'] / max(1., state['stats']['enemy']['sustain'])
            p_condition *= p['sustain'] / max(1., state['stats']['player']['sustain'])
            p_condition *= .6 + .4 * player.morale / 100
            first = p['mobility'] + p['sense'] >= e['mobility'] + e['sense']
            if frame.divine_first is not None:first=frame.divine_first=='player'
            semantic_factors = battle.semantic_initiative(first)
            for side in ('player', 'enemy'):
                for stat, factor in semantic_factors[side].items():
                    stats[side][stat] *= factor
            initiative = 'player' if first else 'enemy'
            dealt = exchange_damage(p['might'] * p_condition, e['guard'] * (.72 + .28 * enemy_condition),
                                    p['breach'] / max(1, e['guard']), rng.uniform(.9, 1.1),
                                    coefficient=.135, minimum=.045, maximum=.42)
            received = exchange_damage(e['might'] * enemy_condition, p['guard'] * (.72 + .28 * player.vitality),
                                       e['breach'] / max(1, p['guard']), rng.uniform(.9, 1.1),
                                       coefficient=.125, minimum=.035, maximum=.4)
            # The actual golden-body passive helps withstand heavenly decay.
            if battle.ward_tier('player') >= 2:
                received *= .75
            dealt *= 1.05 if first else .97
            received *= .96 if first else 1.04
            before = [player.unit.power*player.vitality,
                      battle.totals['enemy']*(1-battle.ordinary_loss('enemy'))]
            dealt, received = battle.ordinary_damage(dealt, received)
            state['mp_ratio']=battle.mp_ratio('player',state['mp_ratio'])
            if frame.ordinary:
                exchange = dict(opening=before, before=before,
                    after=[player.unit.power*player.vitality,
                           battle.totals['enemy']*(1-battle.ordinary_loss('enemy'))],
                    actors={'player': frame.ordinary_player, 'enemy': frame.ordinary_enemy})
            if frame.ordinary_player:
                state['mp_ratio'] = max(0, state['mp_ratio'] - .035)
            frame.events.append(f'本轮普通交锋：敌方态势损耗 {dealt:.1%}，己方态势损耗 {received:.1%}。')
        battle.finish_round(player_mp=state['mp_ratio'], enemy_mp=1)
        state['mp_ratio']=battle.mp_ratio('player',state['mp_ratio'])
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
        if exchange is not None:
            rows[-1]['ordinary_exchange'] = exchange
        if asura_trial and player.suppressed and player.body > 0:
            # Suppression alone is not a lethal victory. An actual opponent
            # with a sufficient attack tier must execute the immobilized body.
            for key, attacker in battle.units.items():
                if attacker.unit.side != 'enemy' or not attacker.fighting:
                    continue
                if battle.attack_tier(attacker) >= battle.ward_tier('player'):
                    battle.attack_tier(attacker, pay=True)
                    battle._lose('player', player.vitality)
                    player.body = 0
                    battle._drain_body_events()
                    rows[-1]['events'].append('劫相击杀了被镇压的肉身。')
                    rows[-1].update(player_hp_ratio=0, player_combat_state=0, voisinage=battle.report())
                    break
        if (not asura_trial and not player.fighting) or player.body <= 0 or player.vitality <= 0:
            return 'defeat', rows
        if fusion and all(s.vitality <= 0 or s.body <= 0 or s.suppressed for s in battle.units.values() if s.unit.side == 'enemy'):
            return 'victory', rows
        if endurance and n >= 5:
            return 'victory', rows
        if not endurance and battle.enemy_killed():
            return 'victory', rows
    return 'ongoing', rows

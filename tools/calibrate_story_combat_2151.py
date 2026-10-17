"""Replay every base scripted combat choice through the real story adapter."""
import argparse
import copy
import json
import os
from pathlib import Path
import random
import shutil
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=24)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='story-calibration-') as directory:
        shutil.copytree(ROOT/'content', Path(directory)/'content')
        os.environ['CULTIVATION_APP_ROOT'] = directory
        from cultivation_life.content_registry import STORY_COMBAT_SCENARIOS, WORLD_SYSTEMS, REALMS
        from cultivation_life.models import Player, GameState
        from cultivation_life.rules import combat_power, max_hp, max_mp, combat_root_mana_cost_multiplier
        from cultivation_life.engine.engine_event_runtime import _resolve_story_combat_check, _story_unit_full_power
        from cultivation_life.engine.engine_combat_runtime import _player_combat_units
        from cultivation_life.engine.combat_capabilities import bind_capabilities
        from cultivation_life.system.combat_system import PlayerCombatSystem
        from scripts.release_evidence import inputs_digest
        realm_ids = {r.id:i for i,r in enumerate(REALMS)}
        rows = []
        for path in sorted((ROOT/'content').glob('*events*.json')):
            doc = json.loads(path.read_text(encoding='utf-8'))
            for event in doc if isinstance(doc,list) else doc.get('events', []):
                if event['id'] not in STORY_COMBAT_SCENARIOS:
                    continue
                intended = next((t[6:] for t in event.get('tags',[]) if t.startswith('realm:')), None)
                if intended is None:
                    intended = ('foundation' if 'BLOOD_RIVER' in event['id'] else
                        'core' if 'CORPSE_MOON' in event['id'] else
                        'nascent' if 'RIFT_BEAST' in event['id'] else
                        'void' if 'BLACK_SUN' in event['id'] else
                        'integration' if 'FALLEN_STAR' in event['id'] else 'mahayana')
                rank = realm_ids[intended]
                for choice in event['choices']:
                    for effect in choice.get('effects', []):
                        check = next((c for c in effect.get('checks',[]) if c.get('stat')=='combat_power'), None)
                        if not check:
                            continue
                        power = float(check['value'])
                        # As in the existing Luo calibrator, the flat rating is
                        # an offline independent variable, never a player grant.
                        p = Player('剧情数值样本', 'supreme_metal', realm_index=rank, layer=7,
                            world='human' if rank<=5 else 'spirit', body_training=100 if rank>=6 else 0,
                            divine_sense_rank=rank*3+2)
                        p.hp, p.mp = max_hp(p), max_mp(p)
                        p.outer_king_fixed_combat_power = power-combat_power(p)
                        assert p.outer_king_fixed_combat_power>=0, (event['id'], power)
                        game = GameState('calibration', 2151, p, '', '')
                        captured = {}
                        def capture(_game,target,_lethal,_rng):
                            captured.update(target)
                            return 'victory',''
                        deps = SimpleNamespace(_combat=capture,_story_unit_full_power=_story_unit_full_power,
                                               _public_party=lambda game:[])
                        _resolve_story_combat_check(deps, effect, game,
                            {'id':event['id'],'_choice_id':choice['id']},random.Random(0))
                        units = _player_combat_units(deps, game, captured)
                        results = {}
                        for mp in (1,.7):
                            wins = 0
                            for seed in range(args.samples):
                                replay, target, team = copy.deepcopy((game,captured,units))
                                player = replay.player
                                player.mp = max_mp(player)*mp
                                phases = bind_capabilities(replay,team,target,WORLD_SYSTEMS['transcendent_combat']).battle
                                result = PlayerCombatSystem.resolve(player,team,target,False,random.Random(seed),
                                    current_hp_ratio=1,current_mp_ratio=mp,
                                    battlefield_tags=[target['natural_terrain'],*target['artificial_conditions']],
                                    mana_cost_multiplier=combat_root_mana_cost_multiplier(player,rank,7),phases=phases)
                                wins += result.outcome in {'victory','victory_controlled'}
                            results[str(mp)] = dict(wins=wins,battles=args.samples,win_rate=wins/args.samples)
                        row = dict(event=event['id'],choice=choice['id'],rank=rank,recommendation=power,
                            target_power=captured['target_power'],enemy_full_power=[m['full_power'] for m in captured['members']],
                            results=results)
                        rows.append(row)
                        print(json.dumps(row,ensure_ascii=False),flush=True)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(dict(source_sha256=inputs_digest(ROOT),samples=args.samples,rows=rows,
            assumptions='Base story adapter + real capability binding and battle resolver. Fixed rating probe, same authored allies/terrain/seals/choice exclusions, full HP and full/70% MP. Not a claim that rating alone overrides equipment, resource gates or domains.'),
            ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()

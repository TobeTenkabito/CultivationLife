"""Compare first-majority and further-seat elections with seeded simulations."""
import copy
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life.engine import GameEngine


def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        engine = GameEngine(ROOT, Path(directory))
        game = engine.store.load(engine.create_game('选举校准', 'supreme_metal', 'dao', 1520,
                                                  preset_id='true_immortal')['id'])
        original = copy.deepcopy(game.heavenly_court)
        results = []
        for controls, tickets in [(0,0),(3,0),(4,0),(6,0),(4,8),(6,12)]:
            won = rounds = 0
            for seed in range(500):
                game.heavenly_court = copy.deepcopy(original)
                game.history = []
                court = game.heavenly_court
                court['player_grade'] = 4
                for key in list(court['offices'])[:controls]:
                    court['offices'][key] = dict(holder_id='player',holder_name='选举校准',start_unit=0,end_unit=14)
                rng = random.Random(seed)
                engine._court_open_election(game, 'mercury', rng)
                court['open_election']['yaochi_seats'] = [s['id'] for s in court['seats'][:tickets]]
                for _ in range(3):
                    rounds += 1
                    done, _ = engine._court_resolve_election_round(game, rng, 'none', '')
                    if done:
                        break
                won += court['offices']['mercury']['holder_id'] == 'player'
            results.append(dict(held=controls, pledged_votes=tickets, samples=500,
                                win_rate=won/500, mean_rounds=rounds/500))
        print(json.dumps(results, ensure_ascii=False, indent=2))
        assert results[0]['win_rate'] >= .75 and results[1]['win_rate'] >= .75
        assert results[2]['win_rate'] < results[1]['win_rate']
        assert results[4]['win_rate'] > results[2]['win_rate']


if __name__ == '__main__':
    main()

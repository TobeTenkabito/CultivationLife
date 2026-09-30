"""Compare vein budgets with direct cultivation and trace income, including pity.

No advancement or NPC simulation is needed. Temporary saves never touch user data.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life.content_registry import ACTIONS, REALMS, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.rules import opportunity_multiplier
from cultivation_life.system.doctrine.cultivation import vein_cost, immortal_breakthrough_cost
from cultivation_life.system.immortal_cultivation import rules


def expected_attempts(probability, pity_step):
    survival = 1.0
    result = 0.0
    failures = 0
    while survival > 0:
        result += survival
        survival *= 1 - min(1.0, probability + failures * pity_step)
        failures += 1
    return result


def budgets(realm, cfg):
    total = {'opportunity': 0.0, 'traces': 0.0}
    for opened in range(cfg['veins_per_realm']):
        attempts = expected_attempts(cfg['vein_success_rates'][opened // cfg['veins_per_layer']], cfg['vein_pity_step'])
        for resource, cost in vein_cost(realm, opened, cfg).items():
            total[resource] += attempts * cost
    return total


def main():
    cfg = rules()
    with tempfile.TemporaryDirectory() as directory:
        engine = GameEngine(ROOT, Path(directory))
        made = engine.create_game('仙脉校准', 'supreme_metal', 'dao', 1511, preset_id='true_immortal')
        player = engine._load(made['id']).player
        annual_gain = sum(ACTIONS['cultivate']['opportunity']) / 2 * opportunity_multiplier(player)
        rows = []
        for realm in range(9, 13):
            totals = budgets(realm, cfg)
            trace_years = totals['traces'] / cfg['trace_gain_chance']
            rows.append(dict(realm=REALMS[realm].name,
                             first=vein_cost(realm, 0, cfg)['opportunity'],
                             last=vein_cost(realm, 26, cfg)['opportunity'],
                             expected_opportunity=round(totals['opportunity']),
                             expected_traces=round(totals['traces'], 1),
                             cultivation_years=round(totals['opportunity'] / annual_gain),
                             trace_years=round(trace_years),
                             opportunity_to_trace_time=round(totals['opportunity'] / annual_gain / trace_years, 3),
                             old_breakthrough_base=REALMS[realm].opportunity_base,
                             breakthrough_first=immortal_breakthrough_cost(realm, 1, cfg),
                             breakthrough_last=immortal_breakthrough_cost(realm, 9, cfg)))
        first_veins = sum(vein_cost(9, n, cfg)['opportunity'] for n in range(3))
        manual_fee = immortal_breakthrough_cost(9, 1, cfg)
        expected_opening = first_veins * expected_attempts(cfg['vein_success_rates'][0], cfg['vein_pity_step'])
        first_layer = dict(three_veins_once=first_veins, manual_fee=manual_fee,
                           total_once=first_veins + manual_fee,
                           expected_veins_plus_one_breakthrough=round(expected_opening + manual_fee),
                           user_reported_income_per_action=18000,
                           user_income_actions_once=(first_veins + manual_fee) / 18000,
                           note='开脉期望含失败及保底，手动冲关只计成功一次；仙痕另计')
        print(json.dumps(dict(reference='真仙开局原有配置，四境使用同一效率作比较；不含初始余额、事件、额外产出及突破费用',
                              direct_opportunity_per_year=round(annual_gain, 3),
                              true_immortal_action_years=WORLD_SYSTEMS['time_units']['9'],
                              first_layer=first_layer, rows=rows), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

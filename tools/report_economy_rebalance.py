"""Offline catalog audit, fixed-roster economic stress and bounded work timings."""
import copy
import argparse
import json
import statistics
import sys
import tempfile
import time
from unittest.mock import patch
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.content_registry import WORLD_SYSTEMS, ITEM_CATALOG
from cultivation_life.economy_content import specification
from cultivation_life.system.economy import state, organizations, basket_rules, basket_production, basket_consumption
from cultivation_life.system.economy.ledger import balance


def total(game):
    return balance(game,'player')+sum(r['balance'] for r in game.economy_v2['accounts'].values())+sum(r.get('resources',0) for r in game.intrigue_state['factions'].values())+sum(r['reserves'] for rows in game.merchant_state.get('worlds',{}).values() for r in rows)+game.heavenly_court.get('treasury',0)+sum(r['treasury'] for r in game.upper_institutions.values())


def war_sample(engine, seed):
    from cultivation_life.system.war import logistics, requirements, supply
    from cultivation_life.system.economy.ledger import transfer_value
    g=engine._load(engine.create_game('会战成本','supreme_metal','dao',seed,preset_id='nascent')['id'])
    g.pending_event=None
    for identity in ('tianjian','wanmo'):
        organizations.register(g,'sect',identity,'human')
        transfer_value(g,'background:human',f'organization:sect:{identity}',100000,'开战样本资金')
    treasury_before=balance(g,'organization:sect:tianjian')
    war=engine._start_war(g,'sect','tianjian','wanmo',initiated_by_player=True)
    row=war['logistics']['sides']['attacker']
    for _ in range(4):
        requirements.refresh(g,war,'attacker');logistics.replenish(g,engine.maps,war,'attacker')
        supply.consume_battle(g,war,'attacker')
    actual=row['mobilization_paid']+row['spent']
    return dict(seed=seed,battles=4,deployed=sum(row['realm_groups'].values()),
        reference_per_battle=logistics.need(g,war,'attacker'),
        actual_consumed_value=actual,starting_treasury=100000,ratio=round(actual/100000,4),
        treasury_cash_committed=treasury_before-balance(g,'organization:sect:tianjian'),
        unspent_goods_value=round(supply.goods_value(g,row)),
        war_cash_remaining=balance(g,supply.wallet(war,'attacker')),
        unspent_supply_value=supply.total(g,war,'attacker'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'build/economy-diversity')
    parser.add_argument('--skip-actions',action='store_true',help='Use the isolated replay benchmark for real-action timings')
    options=parser.parse_args()
    output=options.output_dir.resolve();output.mkdir(parents=True,exist_ok=True)
    audit=[];timings={};stress=[];actions=[];wars=[]
    with tempfile.TemporaryDirectory() as tmp:
        engine=GameEngine(ROOT,Path(tmp))
        original=engine._load(engine.create_game('数值验收','supreme_metal','dao',315,preset_id='nascent')['id'])
        for world in original.economy_v2['worlds']:
            catalog=state.commodity_catalog(world)
            market=dict(commodities={k:dict(tier=r['tier'],reference=r['base_price']) for k,r in catalog.items()})
            for item,good in catalog.items():
                recipe=basket_production.recipe(market,item)
                audit.append(dict(world=world,id=item,name=good['name'],grade=good['tier'],category=basket_rules.kind(item),
                    reference=good['base_price'],inputs=recipe,
                    supply=('猎场／公共丹源' if specification(item) and specification(item)['role'] and specification(item)['role'].startswith('core_') else '采掘／种植') if recipe=={} else '消耗实物原料加工' if recipe else '初始存量／玩法获取',
                    fallback='本界黑市按原有流通资格保底；药田商品沿用种植来源'))
        for years in (1,100,500,1000):
            samples=[];calls=[]
            for _ in range(9):
                g=copy.deepcopy(original);m=state.local_market(g);basket_rules.index(m)
                with patch.object(basket_consumption,'purchase',wraps=basket_consumption.purchase) as buying:
                    start=time.perf_counter();basket_consumption.settle(g,m,years);samples.append((time.perf_counter()-start)*1000)
                    calls.append(buying.call_count)
            timings[str(years)]=dict(median_ms=round(statistics.median(samples),3),max_orders=max(calls))
            assert max(calls)<=192 and statistics.median(samples)<=50
        assert timings['1000']['median_ms'] <= timings['1']['median_ms']*3
        for seed in (315,7701,9003):
            g=engine._load(engine.create_game('稳态压力','supreme_metal','dao',seed,preset_id='nascent')['id'])
            g.pending_event=None
            opening=total(g);start=time.perf_counter()
            for years in range(1,5001):
                # Real organization finance is an annual world-clock entry.
                # Hold the roster fixed to isolate money/stock circulation;
                # never invent a century's historical dealer transactions.
                g.player.age+=1;state.advance_economy(g);organizations.advance_organizations(g,engine.maps)
                if years not in {200,1000,5000}:continue
                assert total(g)==opening+g.economy_v2.get('issued',0)
                assert GameState.from_dict(g.to_dict()).economy_v2==g.economy_v2
                assert len(json.dumps(g.economy_v2,ensure_ascii=False).encode())<=512*1024
                assert not any(r['shortfall'] for r in g.economy_v2['organizations'].values())
                m=state.local_market(g)
                stress.append(dict(seed=seed,years=years,ms=round((time.perf_counter()-start)*1000,2),
                    issued=g.economy_v2.get('issued',0),consumed=m.get('terminal_consumed',0),
                    household_spending=m.get('household_spending',0),stock_min=round(min(r['stock'] for r in m['commodities'].values()),4),
                    stock_max=round(max(r['stock'] for r in m['commodities'].values()),4),
                    organizations=len(g.economy_v2['organizations']),shortfalls=sum(bool(r['shortfall']) for r in g.economy_v2['organizations'].values()),
                    save_bytes=len(json.dumps(g.economy_v2,ensure_ascii=False).encode())))
                print(f'seed={seed} years={years}: conservation and reload passed',flush=True)
                (output/'stress-checkpoints.json').write_text(json.dumps(dict(performance=timings,stress=stress),ensure_ascii=False,indent=2),encoding='utf8')
        # Real controller, loading, all yearly NPC phases and saving; only the
        # unrelated popup interruption is disabled to complete the 100 years.
        for seed in (() if options.skip_actions else (315,7701,9003)):
            made=engine.create_game('百年行动验收','supreme_metal','dao',seed,preset_id='true_immortal')
            g=engine._load(made['id']);g.pending_event=None;g.player.next_tribulation_age=None
            g.settings['silent_events']=True;g.heavenly_court['open_election']=None
            engine.store.save(g);start=time.perf_counter()
            with patch.object(engine,'_advance_guixu_calendar',return_value=False):
                engine.advance(g.id,'rest',1)
            final=engine.store.load(g.id)
            assert final.player.age-g.player.age==100
            actions.append(dict(seed=seed,years=100,ms=round((time.perf_counter()-start)*1000,2)))
            print(f'real 100-year action seed={seed}: passed',flush=True)
        if actions:assert statistics.median(r['ms'] for r in actions)<=5000
        for seed in (315,7701,9003):
            wars.append(war_sample(engine,seed))
    result=dict(catalog=audit,realm_weights={str(r):round(w,4) for r,w in enumerate(basket_rules.REALM_WEIGHTS)},
                performance=timings,stress=stress,real_actions=actions,war_samples=wars,
                scope='压力为固定名册经济；real_actions 使用真实百年休息控制器和年度 NPC 流程；war_samples 固定名册四场后勤')
    (output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 商品供给审计（当前本体目录）','','此表由 `python tools/report_economy_rebalance.py` 离线生成；不参与年度结算。品阶和参照价来自权威目录，受限特殊来源不加入普通商品。黑市流通范围、搜索、溢价和批量购买沿用原规则。药田十年草等商业补充品仍通过原种植入口供应。','','| 界面 | 商品编号 | 名称 | 品阶 | 用途类别 | 参照价 | 常规来源／实物投入 |','|---|---|---|---:|---|---:|---|']
    for row in audit:
        inputs='；'.join(f'{k} ×{n}' for k,n in (row['inputs'] or {}).items())
        lines.append(f"| {row['world']} | {row['id']} | {row['name']} | {row['grade']} | {row['category']} | {row['reference']} | {row['supply']}{'：'+inputs if inputs else ''} |")
    (ROOT/'docs/economy-supply-catalog.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(performance=timings,real_actions=actions,war_samples=wars,catalog_rows=len(audit)),ensure_ascii=False,indent=2))


if __name__=='__main__':main()

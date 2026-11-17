"""Summarize completed, source-matched paired command acceptance runs."""
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.release_evidence import inputs_digest


def summarize(rows):
    returns=[r for r in rows if r['returned']]
    def median(values):return round(statistics.median(values),4) if values else None
    return dict(runs=len(rows),returned=sum(r['returned'] for r in rows),dead=sum(not r['alive'] for r in rows),
        wandering=sum(r['wandering'] for r in rows),captured=sum(r['captured'] for r in rows),
        crisis=sum(r['crisis'] for r in rows),core=sum(r['core'] and r['returned'] for r in rows),
        fused_core=sum(r['fused_core'] and r['returned'] for r in rows),
        median_claims_on_return=median([r['claims'] for r in returns]),
        median_cultivation_units_on_return=median([r['opportunity_action_units'] for r in returns if r['opportunity_action_units'] is not None]),
        median_power_change_on_return=median([r['power_gain']/r['starting_power'] for r in returns]),
        learned=sum(r['learned'] for r in returns),max_materialized=max(r['generated_people'] for r in rows))


def main():
    folder=ROOT/'build/reviews/seeded-dungeons'
    source=inputs_digest(ROOT)
    if '--shards' in sys.argv:
        shards=[json.loads((folder/f'closed-{offset}.json').read_text(encoding='utf-8')) for offset in range(12)]
        assert all(b['complete'] and b['source']==b['final_source']==source and len(b['rows'])==32 for b in shards)
        for offset in (0,3,6,9):
            group=shards[offset:offset+3]
            batch=dict(source=source,final_source=source,complete=True,seconds=max(b['seconds'] for b in group),
                worker_seconds=[b['seconds'] for b in group],protocol=group[0]['protocol'],
                rows=[r for b in group for r in b['rows']],baselines=[r for b in group for r in b['baselines']])
            (folder/f'verified-{offset}.json').write_text(json.dumps(batch,ensure_ascii=False,indent=2),encoding='utf-8')
    batches=[json.loads((folder/f'verified-{offset}.json').read_text(encoding='utf-8')) for offset in (0,3,6,9)]
    assert all(b['complete'] and b['source']==b['final_source']==source for b in batches)
    rows=[r for b in batches for r in b['rows']];baselines=[r for b in batches for r in b['baselines']]
    assert len(rows)==384 and len(baselines)==24
    keys={(tuple(r['build']),r['seed'],r['quality'],r['policy']) for r in rows}
    assert len(keys)==len(rows)
    units=json.loads((ROOT/'content/world.json').read_text(encoding='utf-8'))['systems']['time_units']
    assert all(r['cooldown']==units[str(r['build'][1])] for r in rows)
    by_quality={q:summarize([r for r in rows if r['quality']==q]) for q in ('ordinary','rare','epic','legendary')}
    by_policy={p:summarize([r for r in rows if r['policy']==p]) for p in ('edge','deep','core','aid')}
    strata=[dict(quality=q,policy=p,**summarize([r for r in rows if r['quality']==q and r['policy']==p]))
        for q in by_quality for p in by_policy]
    builds=[dict(build=list(build),quality=q,**summarize([r for r in rows if tuple(r['build'])==build and r['quality']==q]))
        for build in dict.fromkeys(tuple(r['build']) for r in rows) for q in by_quality]
    summary=dict(source=source,total=summarize(rows),baselines=len(baselines),by_quality=by_quality,
        by_policy=by_policy,strata=strata,builds=builds,seconds=[b['seconds'] for b in batches])
    expert=json.loads((folder/'expert.json').read_text(encoding='utf-8'))
    assert expert['complete'] and expert['source']==expert['final_source']==source and len(expert['rows'])==4
    summary['mature_build']=summarize(expert['rows'])
    summary['mature_build_baselines']=len(expert['baselines'])
    (folder/'playthrough-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    labels={'ordinary':'普通','rare':'稀有','epic':'史诗','legendary':'传奇','edge':'外围撤离','deep':'谨慎深入','core':'直取核心','aid':'结伴援弱'}
    lines=['# 副本实战分层验收','',f'代码输入 SHA-256：`{source}`。','',
        '384 次正式命令探索，12 种角色配置，每种配置两份配对种子、四品质、四策略；24 次真实修炼作为各自基线。',
        '品质分层强制抽样；战斗、逃亡、生存、库存、学习、装备、存档与响应准备均使用正式入口。仅省略无关展示面板的拷贝，等价性另有命令与存档对照测试。',
        '每个品质和策略组合有 24 次记录。配对样本用于比较玩法与排错，不将其直接写成自然生成概率或玩家总体死亡率。',
        '收益列只统计正常返回者；机缘折算包含实际服药，功法在满足资格后实际学习和装备。仙痕、材料和待学真传另保留原始数量，不折成虚构价格。',
        '核心列要求实际领取核心并正常返回；转入元婴、生魂或被俘的结果分别记录。','','| 品质 | 策略 | 正常返回 | 死亡 | 游魂 | 被俘 | 元婴危机 | 核心带出 | 合练核心 | 修炼单位中位数 |','| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in strata:
        lines.append(f"| {labels[r['quality']]} | {labels[r['policy']]} | {r['returned']}/{r['runs']} | {r['dead']} | {r['wandering']} | {r['captured']} | {r['crisis']} | {r['core']} | {r['fused_core']} | {r['median_cultivation_units_on_return']} |")
    mature=summary['mature_build']
    lines+=['','## 成熟构筑补验','',
        '另有大罗九层、至臻邻域、炼体 100、仙躯 50、同阶两部 Lv.9 主辅功法及两件同阶商品装备的独立配置。两份种子分别跑直取核心和结伴援弱，原敌人、战斗与宝物均保留实际生成结果。',
        f"4 次传奇探索正常返回 {mature['returned']} 次，带出且学会合练核心 {mature['fused_core']} 次，死亡 {mature['dead']} 次，游魂 {mature['wandering']} 次。另跑两次真实修炼作基线。明细见 `expert.json`。",'',
        '逐角色原始战斗、操作序列、战力变化、所得和角色实例数见同目录 `verified-0/3/6/9.json`；聚合数据见 `playthrough-summary.json`。']
    (folder/'playthrough-summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(source=source,total=summary['total'],by_quality=by_quality),ensure_ascii=False))


if __name__=='__main__':main()

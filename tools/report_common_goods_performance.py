"""Report measured release impact separately from exact cache-only equivalence."""
import json
import pstats
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    folder = root/'build/common-goods-performance'
    baseline, uncached, final = [json.loads((folder/name).read_text(encoding='utf-8')) for name in
        ('baseline-2150.json','uncached-2151.json','final-2151.json')]
    assert uncached['source_sha256'] == final['source_sha256']
    rows = []
    def economic_work(label, world):
        stats = pstats.Stats(str(folder/f'{label}-{world}.prof')).stats
        values = [v for k,v in stats.items() if '/economy/' in k[0].replace('\\','/')]
        return dict(calls=sum(v[1] for v in values),self_ms=round(sum(v[2] for v in values)*1000,2))
    for old, raw, new in zip(baseline['scenarios'],uncached['scenarios'],final['scenarios'],strict=True):
        assert old['world'] == raw['world'] == new['world']
        assert old['years'] == raw['years'] == new['years']
        assert raw['full_state_sha256'] == new['full_state_sha256'], 'Cache changed simulated output'
        rows.append(dict(world=new['world'],action=new['action'],years=new['years'],
            baseline_ms=old['median_ms'],uncached_ms=raw['median_ms'],final_ms=new['median_ms'],
            update_percent=round((new['median_ms']/old['median_ms']-1)*100,2),
            cache_reduction_percent=round((1-new['median_ms']/raw['median_ms'])*100,2),
            baseline_cpu_ms=old['median_cpu_ms'],final_cpu_ms=new['median_cpu_ms'],
            baseline_rows=old['commodity_rows'],final_rows=new['commodity_rows'],
            original_markets_retained=True,cache_full_state_equal=True,
            final_max_sample_rss_mib=max(r['rss_mib'] for r in new['samples'])))
        rows[-1]['baseline_economy_profile'] = economic_work(baseline['label'],new['world'])
        rows[-1]['final_economy_profile'] = economic_work(final['label'],new['world'])
    report = dict(version=final['version'],source_sha256=final['source_sha256'],
        baseline_source_sha256=baseline['source_sha256'],runs=final['runs'],scenarios=rows,
        environment=final.get('environment',{}),
        caveats='Wall time is noisy. Fixed original saves retain old restricted stocks and adopt new zero-stock definitions. 2.15.0 and 2.15.1 intentionally differ in goods and auction rules; only cache-on/off is required to match full simulated state. Profiles are not timing samples. No physical Android timing claim.')
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines = ['# v2.15.1 时间性能实测','',f"最终生产源码：`{report['source_sha256']}`。每场景三次真实操作，中位数；剖析另跑不混入计时。",
        '', '| 场景 | 年数 | 2.15.0(ms) | 2.15.1未缓存(ms) | 最终(ms) | 更新耗时变化 |',
        '|---|---:|---:|---:|---:|---:|']
    for r in rows:
        lines.append(f"| {r['world']} / {r['action']} | {r['years']} | {r['baseline_ms']:.2f} | {r['uncached_ms']:.2f} | {r['final_ms']:.2f} | {r['update_percent']:+.2f}% |")
    lines += ['', '缓存开关三场景完整结算状态逐字段哈希一致，仅排除墙钟updated_at；包含人物、现金、原库存、产业、货运、RNG、历史与实际时钟。',
        '', '所有比较复用原2.15.0隔离快照，不删除旧库存，不修改用户存档。采样包括控制器、年度经济与人物、读写及展示；只屏蔽可选归墟通知中断。',
        '', '计时有主机噪声，百分比不是跨机器承诺；商品与拍卖规则变化会有预期状态差异，不能用它声称跨版本全状态相等。原始样本、CPU、进程常驻内存及独立剖析见同目录JSON和prof文件。']
    (folder/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == '__main__': main()

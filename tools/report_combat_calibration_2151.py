"""Summarize reproducible combat probes and birth ratios for release review."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.release_evidence import inputs_digest


def main():
    folder = ROOT/'build/combat-calibration-2151'
    read = lambda name:json.loads((folder/name).read_text(encoding='utf-8'))
    current = inputs_digest(ROOT)
    modes = {}
    for mode in ('base','dlc'):
        final = read(f'final-{mode}.json')
        assert final['source_sha256']==current
        assert len(final['rows'])==37
        before, after = read(f'quick-before-{mode}.json'),read(f'quick-after-{mode}.json')
        assert after['source_sha256']==current
        starts=[]
        for old,new in zip(before['rows'],after['rows'],strict=True):
            assert (old['preset'],old['selected_path'])==(new['preset'],new['selected_path'])
            old_ratio,new_ratio=old['power']/old['standard'],new['power']/new['standard']
            assert new_ratio+.001>=old_ratio,(mode,new['preset'],old_ratio,new_ratio)
            starts.append(dict(preset=new['preset'],path=new['selected_path'],old_power=old['power'],
                new_power=new['power'],old_standard=old['standard'],new_standard=new['standard'],
                old_ratio=round(old_ratio,4),new_ratio=round(new_ratio,4)))
        modes[mode]=dict(battles=sum(p['battles'] for r in final['rows'] for p in r['profiles'].values()),
            stages=[dict(rank=r['rank'],name=r['realm'],layer=r['layer'],standard=r['old_standard'],
                win_rates={k:v['win_rate'] for k,v in r['profiles'].items()}) for r in final['rows']],quick_starts=starts)
    old_story,new_story=read('story-before.json'),read('story-after.json')
    assert new_story['source_sha256']==current
    changed=0
    stories=[]
    for old,new in zip(old_story['rows'],new_story['rows'],strict=True):
        assert (old['event'],old['choice'])==(new['event'],new['choice'])
        assert new['recommendation']>=old['recommendation']
        changed+=new['recommendation']!=old['recommendation']
        for mp in ('1','0.7'):
            assert new['results'][mp]['win_rate']+.05>=old['results'][mp]['win_rate']
        stories.append(dict(event=new['event'],choice=new['choice'],old=old['recommendation'],
            new=new['recommendation'],target=new['target_power'],results=new['results']))
    report=dict(version='2.15.1',source_sha256=current,modes=modes,story_choices=len(stories),
        changed_story_choices=changed,story_battles=sum(r['battles'] for row in stories for r in row['results'].values()),
        stories=stories,assumptions=[read('final-base.json')['assumptions'],new_story['assumptions'],
            'DLC benchmark bonuses remain additive and unchanged. Ordinary DLC probes intentionally omit all DLC gear, soul, bloodline and domain bonuses; they are not complete DLC builds.'])
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# v2.15.1 战力模拟验收','',f'最终生产源码：`{current}`。',
        '',f"最终本体／全DLC各{modes['base']['battles']:,}场。各37个阶段点、六道途、三种灵根、三档功法配置、24种子。",
        '', '| 境界／层 | 标准（本体） | 低熟练三门胜率 | 普通三门胜率 | 高熟练九门胜率 |',
        '|---|---:|---:|---:|---:|']
    for row in modes['base']['stages']:
        wins=row['win_rates']
        lines.append(f"| {row['name']}／{row['layer']} | {row['standard']:,.0f} | {wins['basic']:.1%} | {wins['normal']:.1%} | {wins['advanced']:.1%} |")
    lines += ['',f'真实开局本体与全DLC各{len(modes["base"]["quick_starts"])}种（含失落六道途），相对境界标准的原战力比值均未降低。',
        '',f'{len(stories)}个剧情选项，{changed}项调高，满／七成法力共{report["story_battles"]:,}场；相同探针的成功率没有降低超过5个百分点。',
        '', '普通六维样本没有装备、军团、特殊传承或领域加成，不等同于完整玩家配置或无限功法收集上限。全DLC普通探针仍不添加扩展养成，不能以其胜率宣称全DLC玩法难度已覆盖。剧情探针使用独立固定战力变量，并保留真实队友、封印、地形和选项差异，不能替代资源与物品条件。',
        '', '配置与复现入口见 docs/combat-calibration-2151.md；详细前后开局、每阶段与剧情数据见配套report.json。']
    (folder/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(source_sha256=current,base_battles=modes['base']['battles'],dlc_battles=modes['dlc']['battles'],
        quick_starts_per_mode=len(modes['base']['quick_starts']),story_choices=len(stories),changed=changed),ensure_ascii=False))


if __name__=='__main__':main()

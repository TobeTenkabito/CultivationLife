"""Offline A/B of the next-round release cost using actual upper-trial settlement."""
import argparse,copy,hashlib,json,sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cultivation_life.content_registry import WORLD_SYSTEMS
from scripts.calibrate_upper_breakthroughs import prepare,sample,variants


def compare(*,samples=8,seed_offset=9000,world_seeds=(930211,930212),max_rounds=960):
    source=copy.deepcopy(WORLD_SYSTEMS['monster_body']);cases=[];summaries=[]
    for enabled in (False,True):
        body=copy.deepcopy(source)
        row=next(r for r in body['mechanisms'] if r['id']=='feixue')
        row['effects']['release_recovery']=dict(base=int(enabled),growth=0)
        with patch.dict(WORLD_SYSTEMS,monster_body=body):
            for profile in ('ready','peak'):
                for catalog in ('base','dynamic'):
                    rows=[]
                    for world_seed in world_seeds:
                        for variant in variants('monster',catalog):
                            trial,meta=prepare('monster',11,profile,variant,world_seed)
                            for seed in range(seed_offset,seed_offset+samples):
                                result=sample(trial,seed,max_rounds)
                                rows.append(dict(recovery=enabled,catalog=catalog,**meta,**result))
                    cases.extend(rows);counts=Counter(r['outcome'] for r in rows)
                    summary=dict(recovery=enabled,catalog=catalog,profile=profile,cases=len(rows),
                        outcomes=dict(counts),success_rate=counts['victory']/len(rows),
                        unresolved_rate=counts['ongoing']/len(rows))
                    summaries.append(summary);print(json.dumps(summary,ensure_ascii=False),flush=True)
    assert WORLD_SYSTEMS['monster_body']==source
    config={k:copy.deepcopy(WORLD_SYSTEMS[k]) for k in ('monster_body','upper_voisinages','asura_manifestation')}
    digest=hashlib.sha256(json.dumps(config,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return dict(config_sha256=digest,config=config,samples=samples,seed_offset=seed_offset,
        world_seeds=list(world_seeds),max_rounds=max_rounds,summary=summaries,cases=cases)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--samples',type=int,default=8);p.add_argument('--seed-offset',type=int,default=9000)
    p.add_argument('--world-seeds',type=int,nargs='+',default=[930211,930212])
    p.add_argument('--max-rounds',type=int,default=960)
    p.add_argument('--output',type=Path,default=ROOT/'build/feixue-recovery-comparison.json')
    a=p.parse_args()
    if not 1<=a.samples<=1024 or a.max_rounds<1 or a.seed_offset<0:p.error('Positive sampling budgets and nonnegative seeds are required')
    result=compare(samples=a.samples,seed_offset=a.seed_offset,world_seeds=a.world_seeds,max_rounds=a.max_rounds)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


if __name__=='__main__':main()

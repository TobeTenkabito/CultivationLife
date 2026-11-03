"""Run the exact declared 3.5.0 selection, binding all evidence to final source."""
import argparse,json,os,subprocess,sys,xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cultivation_life.version import BASE_GAME_VERSION
from scripts.body_ui_release_scope import TESTS,BROWSERS,SCOPE
from scripts.release_evidence import inputs_digest,file_digest,require

def main():
    p=argparse.ArgumentParser();p.add_argument('--workers',type=int,default=2);a=p.parse_args()
    require(1<=a.workers<=4,'Bound workers to 1–4')
    tag=BASE_GAME_VERSION.replace('.','');before=inputs_digest(ROOT)
    shards=[TESTS[i::a.workers] for i in range(a.workers)]
    jobs=[(f'related-tests-{i}',['-m','pytest',*s,'-q','--tb=short',f'--junitxml=build/scoped-{tag}-{i}.xml']) for i,s in enumerate(shards)]
    jobs += [(name,[f'tools/{name}.py']) for name in ('check_world_transition_contract','check_module_dependencies','check_documentation')]
    jobs += [(name,[f'tests/{name}.py']) for name in BROWSERS]
    jobs.append(('save-transfer',['-m','pytest','tests/test_save_transfer.py','-q']))
    def run(job):
        name,args=job;path=ROOT/f'build/{name}-{tag}.log'
        with path.open('w',encoding='utf8') as f:
            code=subprocess.call([sys.executable,'-X','utf8',*args],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,env=os.environ|{'CULTIVATION_BROWSER_LOW_MEMORY':'0'})
        require(code==0,f'{name} failed: {path}')
        require(inputs_digest(ROOT)==before,'Source changed during acceptance')
        print(name+' passed',flush=True)
        return dict(name=name,log=path.relative_to(ROOT).as_posix(),log_sha256=file_digest(path),status='passed')
    with ThreadPoolExecutor(max_workers=a.workers) as pool:runs=list(pool.map(run,jobs))
    combined=ET.Element('testsuites')
    for i in range(a.workers):
        for suite in ET.parse(ROOT/f'build/scoped-{tag}-{i}.xml').getroot().iter('testsuite'):combined.append(suite)
    ET.ElementTree(combined).write(ROOT/f'build/scoped-{tag}.xml',encoding='utf8',xml_declaration=True)
    doc=dict(version=BASE_GAME_VERSION,inputs_sha256=before,profile='body-ui',scope=SCOPE,tests=shards,runs=runs)
    (ROOT/f'build/scoped-{tag}.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':main()

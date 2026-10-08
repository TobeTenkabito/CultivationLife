"""Explicit user-requested domain/upstream scope, bound to final release inputs."""
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.release_evidence import inputs_digest, require
from cultivation_life.version import BASE_GAME_VERSION

TESTS=['tests/test_release_260.py','tests/test_release_251.py','tests/test_upper_voisinages.py',
       'tests/test_immortal_trials.py','tests/test_asura_manifestation.py',
       'tests/test_ghost_reincarnation_dlc.py','tests/test_monster_bloodline_system.py',
       'tests/test_release_212.py','tests/test_module_dependencies.py']


def main():
    tag=BASE_GAME_VERSION.replace('.','');before=inputs_digest(ROOT);runs=[]
    jobs=[('related-tests',['-m','pytest',*TESTS,'-q','--tb=short',f'--junitxml=build/scoped-{tag}.xml'])]
    jobs += [(name,[f'tools/{name}.py']) for name in ['check_world_transition_contract','check_module_dependencies','check_documentation']]
    jobs += [(name,[f'tests/{name}.py']) for name in ['browser_release_260','browser_release_251','browser_events_212']]
    for name,args in jobs:
        log=ROOT/f'build/{name}-{tag}.log'
        with log.open('w',encoding='utf-8') as stream:
            code=subprocess.call([sys.executable,'-X','utf8',*args],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        require(code==0,f'{name} failed; see {log}')
        require(inputs_digest(ROOT)==before,'Release source changed during checks')
        runs.append(dict(name=name,log=str(log.relative_to(ROOT)),status='passed'))
        print(name+' passed',flush=True)
    (ROOT/f'build/scoped-{tag}.json').write_text(json.dumps(dict(version=BASE_GAME_VERSION,inputs_sha256=before,
        scope='User-requested related and upstream tests only; not full repository regression',tests=TESTS,runs=runs),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()

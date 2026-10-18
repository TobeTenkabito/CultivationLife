"""Supplemental user-requested rift audit, bound to final release inputs."""
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cultivation_life.version import BASE_GAME_VERSION
from scripts.release_evidence import inputs_digest,file_digest,require


def main():
    tag=BASE_GAME_VERSION.replace('.','')
    digest=inputs_digest(ROOT)
    files=['tests/test_regional_rifts.py','tests/browser_regional_rifts.py']
    sources={f:file_digest(ROOT/f) for f in files}
    jobs=[('rifts-audit',['-m','pytest',files[0],'-q','--tb=short',f'--junitxml=build/rifts-{tag}.xml']),
          ('rifts-browser',[files[1]])]
    logs={}
    for name,args in jobs:
        path=f'build/release-{tag}/{name}.log'
        with (ROOT/path).open('w',encoding='utf8') as stream:
            result=subprocess.run([sys.executable,'-X','utf8',*args],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        require(result.returncode==0,f'{name} failed: {path}')
        text=(ROOT/path).read_text(encoding='utf-8-sig')
        require('passed' in text and 'FAILED' not in text and 'Traceback' not in text,f'Audit output incomplete: {path}')
        logs[path]=file_digest(ROOT/path)
        print(name+' passed',flush=True)
    require(inputs_digest(ROOT)==digest,'Sources changed during supplemental audit')
    require(all(file_digest(ROOT/f)==value for f,value in sources.items()),'Audit tests changed')
    xml=f'build/rifts-{tag}.xml';logs[xml]=file_digest(ROOT/xml)
    suites=list(ET.parse(ROOT/xml).getroot().iter('testsuite'))
    require(suites and all(int(s.get('failures',0))+int(s.get('errors',0))==0 for s in suites),'Rift regressions failed')
    browser='build/regional-rifts-browser/result.json';logs[browser]=file_digest(ROOT/browser)
    data=json.loads((ROOT/browser).read_text(encoding='utf8'))
    require(data['source_sha256']==digest and data['status']=='passed' and len(data['cases'])==2,'Rift browser incomplete')
    receipt=dict(version=BASE_GAME_VERSION,inputs_sha256=digest,status='passed',tests=sum(int(s.get('tests',0)) for s in suites),
                 test_sources=sources,logs=logs,browser=data)
    (ROOT/f'build/rifts-{tag}-verification.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()

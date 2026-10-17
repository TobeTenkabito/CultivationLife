"""Only the six upstream engine regressions relevant to calibrated starts/story."""
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.release_evidence import inputs_digest,file_digest,require
from cultivation_life.version import BASE_GAME_VERSION


def main():
    before = inputs_digest(ROOT)
    log = ROOT/'build/combat-engine-upstream-2151.log'
    xml = ROOT/'build/combat-engine-upstream-2151.xml'
    with log.open('w',encoding='utf-8') as stream:
        code = subprocess.call([sys.executable,'-X','utf8','-m','pytest','tests/test_engine.py',
            '-k','quick_start or story_checks_combine or fixed_story_combat_floors','-q','--tb=short',
            f'--junitxml={xml}'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    require(code==0 and inputs_digest(ROOT)==before,'Upstream combat regression failed/source changed')
    suites = list(ET.parse(xml).getroot().iter('testsuite'))
    tests = sum(int(s.get('tests',0)) for s in suites)
    require(tests==6 and all(int(s.get('failures',0))+int(s.get('errors',0))==0 for s in suites),
            'Six focused upstream tests required')
    receipt = dict(version=BASE_GAME_VERSION,inputs_sha256=before,tests=tests,status='passed',
        test_source_sha256=file_digest(ROOT/'tests/test_engine.py'),log_sha256=file_digest(log),
        xml_sha256=file_digest(xml))
    (ROOT/'build/combat-engine-upstream-2151.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print('Six focused upstream quick-start/story tests passed')


if __name__=='__main__':main()

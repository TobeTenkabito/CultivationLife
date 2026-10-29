"""Retest two obsolete browser expectations without borrowing other sources.

Only the added directory tile and completed responsive-frame expectations are eligible. Every
declared regression shard and every other real browser must already pass on
the exact final EXE input digest. Original failure evidence stays published.
"""
import copy
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cultivation_life.version import BASE_GAME_VERSION
from scripts.release_evidence import inputs_digest,file_digest,require,validate_evidence
from scripts.verify_scoped_release import HEAVENS_TESTS,HEAVENS_BROWSERS


def main():
    version=BASE_GAME_VERSION;tag=version.replace('.','');before=inputs_digest(ROOT)
    evidence=json.loads((ROOT/f'build/exe-{tag}-verification.json').read_text(encoding='utf-8'))
    validate_evidence(ROOT,version,evidence)
    runner_name=f'build/scoped-run-{tag}-accepted.log'
    runner=(ROOT/runner_name).read_text(encoding='utf-8')
    expected='browser_heavens_navigation'
    corrected=['browser_heavens_navigation','browser_deferred_upper_panels']
    require(f'RuntimeError: {expected} failed;' in runner,'Original runner has not finished with the declared navigation-only failure')
    gate_names=['check_world_transition_contract','check_module_dependencies','check_documentation']
    names=[f'related-tests-{i}' for i in range(3)]+gate_names+[n for n in HEAVENS_BROWSERS if n not in corrected]
    require(all(name+' passed' in runner for name in names),'Other final-source regressions or browsers remain incomplete')
    original_name=f'build/{expected}-{tag}.original.log'
    original=(ROOT/original_name).read_text(encoding='utf-8')
    require('AssertionError' in original and 'count()==1' in original.replace(' ',''),'Original failure is not the retired one-entry expectation')
    attempts=[];combined=ET.Element('testsuites');total=0
    for i in range(3):
        xml=f'build/scoped-{tag}-{i}.xml';log=f'build/related-tests-{i}-{tag}.log'
        suites=list(ET.parse(ROOT/xml).getroot().iter('testsuite'))
        require(suites and all(int(s.get('failures',0))==0 and int(s.get('errors',0))==0 for s in suites),'Regression shard failed; browser-only reconciliation cannot replace tests')
        attempts.append(dict(xml=xml,log=log,xml_sha256=file_digest(ROOT/xml),log_sha256=file_digest(ROOT/log)))
        for suite in suites:
            total+=int(suite.get('tests',0));combined.append(copy.deepcopy(suite))
    upper_original=f'build/browser_deferred_upper_panels-{tag}.original.log'
    text=(ROOT/upper_original).read_text(encoding='utf-8')
    require('TimeoutError' in text and 'element is not visible' in text and 'data-panel-target' in text,'Unexpected original responsive-navigation failure')
    retests=[]
    for name in corrected:
        retest_name=f'build/{name}-{tag}-retest.log'
        with (ROOT/retest_name).open('w',encoding='utf-8') as stream:
            code=subprocess.call([sys.executable,'-X','utf8',f'tests/{name}.py'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        require(code==0,f'Corrected real browser failed: {name}')
        require(inputs_digest(ROOT)==before,'Final release inputs changed during navigation retest')
        source=f'tests/{name}.py';original_name=f'build/{name}-{tag}.original.log'
        retests.append(dict(name=name,exit_code=code,original_log=original_name,original_log_sha256=file_digest(ROOT/original_name),
                retest_log=retest_name,retest_log_sha256=file_digest(ROOT/retest_name),
                test_source=source,test_source_sha256=file_digest(ROOT/source)))
    report=dict(kind='browser-only',inputs_sha256=before,
                reason='All final-source regression shards passed. The old navigation browser expected one directory tile; the implemented outpost entry adds a second. The deferred upper-panel browser selected a desktop control before responsive resize frames completed; it now waits two real animation frames before choosing the visible control. Both complete browsers are rerun with real clicks. No production code or regression result is replaced.',
                original_runner=dict(log=runner_name,log_sha256=file_digest(ROOT/runner_name)),original_runs=attempts,
                browser_retests=retests,final_test_sources={p:file_digest(ROOT/p) for p in HEAVENS_TESTS+[f'tests/{n}.py' for n in HEAVENS_BROWSERS]})
    report_name=f'build/regression-reconciliation-{tag}.json'
    (ROOT/report_name).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    runs=[]
    for name in [f'related-tests-{i}' for i in range(3)]+gate_names+HEAVENS_BROWSERS:
        log=f'build/{name}-{tag}-retest.log' if name in corrected else f'build/{name}-{tag}.log'
        runs.append(dict(name=name,status='passed',log=log,log_sha256=file_digest(ROOT/log)))
    ET.ElementTree(combined).write(ROOT/f'build/scoped-{tag}.xml',encoding='utf-8',xml_declaration=True)
    receipt=dict(version=version,inputs_sha256=before,profile='heavens',regression_scope='standard',
        scope='Heavens, contacts, skins, navigation and related upstream regressions; not full repository regression. Two browser fixture expectations corrected and fully retested; original failures retained.',
        tests=[HEAVENS_TESTS[i::3] for i in range(3)],runs=runs,
        reconciliation=report_name,reconciliation_sha256=file_digest(ROOT/report_name))
    (ROOT/f'build/scoped-{tag}.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Final-source scoped release verified: {total} regressions; both corrected browsers passed; original failures retained',flush=True)


if __name__=='__main__':main()

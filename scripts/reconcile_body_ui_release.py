"""Replace only the obsolete 3.4.0 version fixture with its complete real retest.

All production inputs and every other original result must match final source.
The original failure and logs remain immutable and referenced in the manifest.
"""
import copy,json,subprocess,sys,xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cultivation_life.version import BASE_GAME_VERSION
from scripts.body_ui_release_scope import TESTS,BROWSERS,SCOPE
from scripts.release_evidence import inputs_digest,file_digest,require,validate_evidence

def main():
    require(BASE_GAME_VERSION=='3.5.0','This reconciliation is exclusively the 3.5.0 version fixture')
    tag='350';before=inputs_digest(ROOT);module='tests/test_base_game_version.py'
    exe=json.loads((ROOT/'build/exe-350-verification.json').read_text(encoding='utf8'));validate_evidence(ROOT,BASE_GAME_VERSION,exe)
    runner='build/body350-release-checks.log';text=(ROOT/runner).read_text(encoding='utf8')
    require('RuntimeError: related-tests-0 failed:' in text,'Original runner must have finished')
    gates=['check_world_transition_contract','check_module_dependencies','check_documentation']
    others=['related-tests-1',*gates,*BROWSERS,'save-transfer']
    pending=[name for name in others if name+' passed' not in text]
    require(set(pending)<=set(BROWSERS)|{'save-transfer'},'Other regression shards or engineering gates failed')
    def finish_pending(name):
        log=f'build/{name}-350.log';proof=f'build/body-ui-resumed-{name}-350.json'
        if (ROOT/proof).exists():
            saved=json.loads((ROOT/proof).read_text(encoding='utf8'))
            require(saved['inputs_sha256']==before and saved['log_sha256']==file_digest(ROOT/log),'Resumed evidence changed')
            return saved
        require(not (ROOT/log).exists(),'Only unstarted jobs cancelled by the original executor may be resumed')
        args=['-m','pytest','tests/test_save_transfer.py','-q'] if name=='save-transfer' else [f'tests/{name}.py']
        with (ROOT/log).open('w',encoding='utf8') as f:
            code=subprocess.call([sys.executable,'-X','utf8',*args],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        require(code==0 and inputs_digest(ROOT)==before,f'Resumed job failed or production changed: {name}')
        saved=dict(name=name,status='passed',inputs_sha256=before,log=log,log_sha256=file_digest(ROOT/log))
        (ROOT/proof).write_text(json.dumps(saved,indent=2),encoding='utf8')
        print(name+' passed',flush=True);return saved
    with ThreadPoolExecutor(max_workers=2) as pool:resumed=list(pool.map(finish_pending,pending))
    originals=[];cases=[];replaced=[];failures=[]
    for i in (0,1):
        xml=f'build/scoped-350-{i}.xml';log=f'build/related-tests-{i}-350.log'
        originals.append(dict(xml=xml,log=log,xml_sha256=file_digest(ROOT/xml),log_sha256=file_digest(ROOT/log)))
        for case in ET.parse(ROOT/xml).iter('testcase'):
            if case.find('failure') is not None or case.find('error') is not None:failures.append(case)
            (replaced if 'test_base_game_version' in case.get('classname','').split('.') else cases).append(copy.deepcopy(case))
    require(len(failures)==1 and failures[0].get('name')=='test_stable_version_preserves_public_label_and_numeric_windows_metadata','Only the declared version expectation may be corrected')
    detail=failures[0].find('failure').get('message','')+(failures[0].find('failure').text or '')
    require('3.5.0' in detail and '3.4.0' in detail,'Unexpected original failure')
    require(all(c.find('failure') is None and c.find('error') is None for c in cases),'Other regression results cannot be replaced')
    xml='build/base-version-350-retest.xml';log='build/base-version-350-retest.log'
    with (ROOT/log).open('w',encoding='utf8') as f:
        code=subprocess.call([sys.executable,'-X','utf8','-m','pytest',module,'-q','--junitxml='+xml],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
    require(code==0 and inputs_digest(ROOT)==before,'Complete version module retest failed or production source changed')
    retested=list(ET.parse(ROOT/xml).iter('testcase'))
    keys=lambda rows:{(c.get('classname'),c.get('name')) for c in rows}
    require(keys(replaced)==keys(retested),'The complete original version module must be rerun without dropping cases')
    require(all(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in retested),'Retest must entirely pass')
    cases+=copy.deepcopy(retested)
    combined=ET.Element('testsuites');suite=ET.SubElement(combined,'testsuite',name='body-ui-final-reconciled',tests=str(len(cases)),failures='0',errors='0',skipped='0')
    for case in cases:suite.append(case)
    ET.ElementTree(combined).write(ROOT/'build/scoped-350.xml',encoding='utf8',xml_declaration=True)
    report=dict(kind='corrected-version-fixture',inputs_sha256=before,replaced_module=module,
        reason='The public version and numeric metadata assertions still expected 3.4.0/(3,4,0). Only these two test literals were updated to the authorized 3.5.0/(3,5,0). The complete module was rerun. No production input, other test result or original failure record was replaced.',
        original_runner=dict(log=runner,log_sha256=file_digest(ROOT/runner)),original_runs=originals,
        resumed_jobs=resumed,
        retest_xml=xml,retest_xml_sha256=file_digest(ROOT/xml),retest_log=log,retest_log_sha256=file_digest(ROOT/log),
        final_test_sources={p:file_digest(ROOT/p) for p in TESTS+[f'tests/{n}.py' for n in BROWSERS]})
    path='build/regression-reconciliation-350.json';(ROOT/path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    runs=[dict(name='related-tests-0-reconciled',status='passed',log=path,log_sha256=file_digest(ROOT/path))]
    for name in others:
        logfile=f'build/{name}-350.log';runs.append(dict(name=name,status='passed',log=logfile,log_sha256=file_digest(ROOT/logfile)))
    receipt=dict(version=BASE_GAME_VERSION,inputs_sha256=before,profile='body-ui',scope=SCOPE,tests=[TESTS[::2],TESTS[1::2]],runs=runs,reconciliation=path,reconciliation_sha256=file_digest(ROOT/path))
    (ROOT/'build/scoped-350.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print(f'Final source verified: {len(cases)} related regressions; complete version module retested; original failure retained')
if __name__=='__main__':main()

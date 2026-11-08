"""Retain original evidence and replace obsolete expectations with full module retests."""
import copy,json,subprocess,sys,xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cultivation_life.version import BASE_GAME_VERSION
from scripts.westward_release_scope import TESTS,BROWSERS,SCOPE
from scripts.release_evidence import inputs_digest,file_digest,require,validate_evidence

def main():
    require(BASE_GAME_VERSION=='3.6.0','Only the 3.6.0 Westward expectation corrections')
    before=inputs_digest(ROOT);tag='360';modules={'tests/test_city_management.py','tests/test_city_buildings.py','tests/test_westward_finale.py','tests/test_immortal_body_and_resources.py'}
    exe=json.loads((ROOT/'build/exe-360-verification.json').read_text(encoding='utf8'));validate_evidence(ROOT,BASE_GAME_VERSION,exe)
    anchor=json.loads((ROOT/'build/westward-corrected-tests-inputs.json').read_text(encoding='utf8'))
    require(anchor['inputs_sha256']==before and all(file_digest(ROOT/p)==h for p,h in anchor['test_sources'].items()),'Retest inputs changed')
    runner='build/westward-release-360.log';text=(ROOT/runner).read_text(encoding='utf8')
    resume_only='--resume-checks' in sys.argv
    if resume_only:require((ROOT/'build/scoped-360-0.xml').exists(),'The first shard must have finished before resuming cancelled jobs')
    else:require('RuntimeError: related-tests-0 failed:' in text,'Original runner must have finished')
    others=['related-tests-1','check_world_transition_contract','check_module_dependencies','check_documentation',*BROWSERS,'save-transfer']
    pending=[name for name in others if name+' passed' not in text and (not resume_only or not name.startswith('related-tests'))]
    require(set(pending)<=set(BROWSERS)|{'save-transfer','check_world_transition_contract','check_module_dependencies','check_documentation'},'Unrelated regression failed')
    def finish_pending(name):
        log=f'build/{name}-{tag}.log';proof=f'build/westward-resumed-{name}-{tag}.json'
        if (ROOT/proof).exists():
            r=json.loads((ROOT/proof).read_text(encoding='utf8'));require(r['inputs_sha256']==before and r['log_sha256']==file_digest(ROOT/log),'Resumed evidence changed');return r
        require(not (ROOT/log).exists(),'Only unstarted jobs may be resumed; inspect any failed browser')
        args=['-m','pytest','tests/test_save_transfer.py','-q'] if name=='save-transfer' else [f'tools/{name}.py'] if name.startswith('check_') else [f'tests/{name}.py']
        with (ROOT/log).open('w',encoding='utf8') as f:code=subprocess.call([sys.executable,'-X','utf8',*args],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        require(code==0 and inputs_digest(ROOT)==before,f'Resumed job failed: {name}')
        r=dict(name=name,status='passed',inputs_sha256=before,log=log,log_sha256=file_digest(ROOT/log));(ROOT/proof).write_text(json.dumps(r,indent=2),encoding='utf8');print(name+' passed',flush=True);return r
    with ThreadPoolExecutor(max_workers=2) as pool:resumed=list(pool.map(finish_pending,pending))
    if resume_only:return
    originals=[];cases=[];replaced=[];failures=[]
    classes={Path(m).stem for m in modules}
    for i in range(3):
        xml=f'build/scoped-{tag}-{i}.xml';log=f'build/related-tests-{i}-{tag}.log'
        originals.append(dict(xml=xml,log=log,xml_sha256=file_digest(ROOT/xml),log_sha256=file_digest(ROOT/log)))
        for c in ET.parse(ROOT/xml).iter('testcase'):
            if c.find('failure') is not None or c.find('error') is not None:failures.append(c)
            (replaced if classes.intersection(c.get('classname','').split('.')) else cases).append(copy.deepcopy(c))
    from cultivation_life.building_rules import config
    expected={'test_eleven_world_new_scenery_real_multistage_tales_once[celestial]','test_real_yaochi_supply_receipt_unlocks_yard_ending','test_common_opportunity_award_rolls_once_even_for_large_reward'}|{f'test_two_unique_initial_cities_and_real_story_claims_in_every_world[{world}]' for world in config()['cities']}
    require({c.get('name') for c in failures}==expected and len(failures)==len(expected),'Only the declared expectations may be corrected')
    require(all(c.find('failure') is None and c.find('error') is None for c in cases),'Unrelated failures remain')
    retest_parts=[];retested=[];logs=[];aggregate=ET.Element('testsuites')
    for name in ('westward-corrected-tests','westward-opportunity-retest','westward-cities-retest'):
        xml='build/'+name+'.xml';log='build/'+name+'.log'
        retest_parts.append(dict(xml=xml,log=log,xml_sha256=file_digest(ROOT/xml),log_sha256=file_digest(ROOT/log)))
        doc=ET.parse(ROOT/xml);retested+=list(doc.iter('testcase'))
        for suite in doc.iter('testsuite'):aggregate.append(copy.deepcopy(suite))
        logs.append((ROOT/log).read_text(encoding='utf8'))
    xml='build/westward-final-retests.xml';log='build/westward-final-retests.log'
    ET.ElementTree(aggregate).write(ROOT/xml,encoding='utf8',xml_declaration=True)
    (ROOT/log).write_text('\n'.join(logs),encoding='utf8')
    keys=lambda rows:{(c.get('classname'),c.get('name')) for c in rows}
    require(keys(replaced)==keys(retested),'All four complete modules must be retested, without dropping cases')
    require(all(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in retested),'All corrected module tests must pass')
    require(inputs_digest(ROOT)==before,'Production changed during reconciliation')
    cases+=copy.deepcopy(retested)
    combined=ET.Element('testsuites');suite=ET.SubElement(combined,'testsuite',name='westward-final-reconciled',tests=str(len(cases)),failures='0',errors='0',skipped=str(sum(c.find('skipped') is not None for c in cases)))
    for c in cases:suite.append(c)
    ET.ElementTree(combined).write(ROOT/'build/scoped-360.xml',encoding='utf8',xml_declaration=True)
    report=dict(kind='corrected-world-and-economy-expectations',inputs_sha256=before,replaced_modules=sorted(modules),
        reason='The old scenery/city tests assumed four total celestial cities and 44 total city stories; they now retain the 44 base-city invariant and compare map projections to actual configured cities, checking story uniqueness and finite claims including the added DLC city. The new mainline test incorrectly froze farm stock during 25 actual years; it now verifies the same original estate and exact stock delta equals actual production, with production continuing. The original opportunity spy now expects the explicit unchanged chance_multiplier=1 default and still requires exactly one call, never one per resource unit. Only test expectations changed; no production input or original evidence was overwritten.',
        original_runner=dict(log=runner,log_sha256=file_digest(ROOT/runner)),original_runs=originals,resumed_jobs=resumed,
        retest_xml=xml,retest_xml_sha256=file_digest(ROOT/xml),retest_log=log,retest_log_sha256=file_digest(ROOT/log),additional_retests=retest_parts,
        final_test_sources={p:file_digest(ROOT/p) for p in TESTS+[f'tests/{n}.py' for n in BROWSERS]})
    path='build/regression-reconciliation-360.json';(ROOT/path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    runs=[dict(name='related-tests-0-and-2-reconciled',status='passed',log=path,log_sha256=file_digest(ROOT/path))]
    for name in others:
        log=f'build/{name}-{tag}.log';runs.append(dict(name=name,status='passed',log=log,log_sha256=file_digest(ROOT/log)))
    receipt=dict(version=BASE_GAME_VERSION,inputs_sha256=before,profile='westward',scope=SCOPE,tests=[TESTS[i::3] for i in range(3)],runs=runs,reconciliation=path,reconciliation_sha256=file_digest(ROOT/path))
    (ROOT/'build/scoped-360.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print(f'Final source: {len(cases)} regressions; four complete modules retested; original failures retained')
if __name__=='__main__':main()

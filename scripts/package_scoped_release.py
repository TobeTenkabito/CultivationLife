"""Package a explicitly scoped release without borrowing full-suite evidence."""
import json
import re
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.release_evidence import inputs_digest,file_digest,require,validate_evidence
from scripts.android_provenance import validate_apk_inputs
from cultivation_life.version import BASE_GAME_VERSION as VERSION
from cultivation_life.save_schema import SAVE_SCHEMA_VERSION


def main():
    tag=VERSION.replace('.','')
    scoped=json.loads((ROOT/f'build/scoped-{tag}.json').read_text(encoding='utf-8'))
    require(scoped['version']==VERSION and scoped['inputs_sha256']==inputs_digest(ROOT),'Scoped tests do not match final sources')
    require(all(r['status']=='passed' for r in scoped['runs']),'Scoped checks incomplete')
    reconciliation = None
    if scoped.get('reconciliation'):
        report = ROOT/scoped['reconciliation']
        require(file_digest(report)==scoped['reconciliation_sha256'],'Regression reconciliation changed')
        reconciliation=json.loads(report.read_text(encoding='utf-8'))
        require(reconciliation['inputs_sha256']==scoped['inputs_sha256'],'Retested regression sources mismatch')
        require(all(file_digest(ROOT/name)==digest for name,digest in reconciliation['final_test_sources'].items()),'Regression test sources changed after acceptance')
        for attempt in reconciliation['original_runs']:
            require(all(file_digest(ROOT/attempt[key])==attempt[key+'_sha256'] for key in ('xml','log')),'Original regression evidence changed')
        require(all(file_digest(ROOT/reconciliation[key])==reconciliation[key+'_sha256'] for key in ('retest_xml','retest_log')),'Corrected module retest evidence changed')
    suites=list(ET.parse(ROOT/f'build/scoped-{tag}.xml').getroot().iter('testsuite'))
    require(suites and all(int(s.get('failures',0))==0 and int(s.get('errors',0))==0 for s in suites),'Related regressions failed')
    tests=sum(int(s.get('tests',0)) for s in suites)
    regression=dict(collected=tests,skipped=sum(int(s.get('skipped',0)) for s in suites),failures=0,errors=0)
    regression['passed']=regression['collected']-regression['skipped']
    transfer=(ROOT/f'build/save-transfer-{tag}.log').read_text(encoding='utf-8-sig')
    extra=re.search(r'(\d+) passed',transfer)
    require(extra is not None and 'failed' not in transfer.lower() and 'ERROR' not in transfer,'Save transfer smoke tests failed')
    transfer_in_regression = bool(reconciliation and reconciliation.get('replaced_module')=='tests/test_save_transfer.py') or any('tests/test_save_transfer.py' in shard for shard in scoped['tests'])
    if not transfer_in_regression:tests+=int(extra[1])
    evidence=json.loads((ROOT/f'build/exe-{tag}-verification.json').read_text(encoding='utf-8'))
    validate_evidence(ROOT,VERSION,evidence)
    native=json.loads((ROOT/f'build/android-{tag}-scoped.json').read_text(encoding='utf-8'))
    require(native.get('version')==VERSION,'Native version mismatch')
    apk=ROOT/'android/app/build/outputs/apk/release/app-release.apk'
    require(native['apk_sha256']==file_digest(apk) and native['signed'] and native['status']=='passed','Native/signature evidence invalid')
    for logfile in native['logs']:
        log=(ROOT/logfile).read_text(encoding='utf-8-sig')
        require('status=passed' in log and 'status=failed' not in log,'Native scope failed')
        require(file_digest(ROOT/logfile)==native['log_hashes'][logfile],'Native evidence changed')
    with zipfile.ZipFile(apk) as archive:
        provenance=validate_apk_inputs(ROOT,archive)
        require(archive.testzip() is None,'APK integrity check failed')
        require(all(f'lib/{abi}/libpython3.13.so' in archive.namelist() for abi in ('arm64-v8a','x86_64')),'Android ABI missing')
    if scoped.get('profile')=='economy':
        required={f'build/android-{phase}-{orientation}-{tag}.log'
                  for phase in ('economy-trust','economy-enterprises','economy-network') for orientation in ('portrait','landscape')}
        require(set(native['logs'])==required,'Native economic scope incomplete')
        require(native.get('sdk')=='31','Android 12 native acceptance required')
        require((ROOT/'android/app/build/reports/lint-results-release.txt').read_text().strip()=='No issues found.','Android lint required')
        metadata=(ROOT/f'build/android-metadata-{tag}.log').read_text(encoding='utf-8')
        current_code=int(re.search(r'versionCode (\d+)',(ROOT/'android/app/build.gradle').read_text(encoding='utf-8'))[1])
        require(f"versionCode='{current_code}'" in metadata and f"versionName='{VERSION}-android.{current_code}'" in metadata and "sdkVersion:'31'" in metadata and 'application-debuggable' not in metadata,'APK metadata mismatch')
        require('Verifies' in (ROOT/f'build/android-signature-{tag}.log').read_text(encoding='utf-8'),'Signature evidence missing')
    if scoped.get('profile')=='bugfix':
        required={f'build/android-{phase}-{orientation}-{tag}.log' for phase in ('audit-fixes','economy-trust') for orientation in ('portrait','landscape')}
        require(set(native['logs'])==required and native.get('sdk')=='31','Native bugfix scope incomplete')
        require(native.get('test_apk_sha256')==file_digest(ROOT/'android/app/build/outputs/apk/androidTest/release/app-release-androidTest.apk'),'Native test artifact changed after acceptance')
        require(all('followup_fixes_scope' in (ROOT/name).read_text(encoding='utf-8-sig') for name in native['logs'] if 'audit-fixes' in name),'Current native followup coverage missing')
        require((ROOT/'android/app/build/reports/lint-results-release.txt').read_text().strip()=='No issues found.','Android lint required')
        require('Verifies' in (ROOT/f'build/android-signature-{tag}.log').read_text(encoding='utf-8'),'Signature evidence missing')
        metadata=(ROOT/f'build/android-metadata-{tag}.log').read_text(encoding='utf-8')
        current_code=int(re.search(r'versionCode (\d+)',(ROOT/'android/app/build.gradle').read_text(encoding='utf-8'))[1])
        require(f"versionCode='{current_code}'" in metadata and f"versionName='{VERSION}-android.{current_code}'" in metadata and "sdkVersion:'31'" in metadata and 'application-debuggable' not in metadata,'APK metadata mismatch')
    if scoped.get('profile')=='regional':
        rift_audit=json.loads((ROOT/f'build/rifts-{tag}-verification.json').read_text(encoding='utf8'))
        require(rift_audit['version']==VERSION and rift_audit['inputs_sha256']==inputs_digest(ROOT)
                and rift_audit['status']=='passed','Matched spatial rift/node audit required')
        require(all(file_digest(ROOT/name)==digest for name,digest in (rift_audit['test_sources']|rift_audit['logs']).items()),
                'Spatial rift/node audit evidence changed')
        tests+=rift_audit['tests']
        regional_exe=json.loads((ROOT/f'build/regional-exe-{tag}.json').read_text(encoding='utf8'))
        require(regional_exe['inputs_sha256']==inputs_digest(ROOT) and regional_exe['exe_sha256']==file_digest(ROOT/'dist/launcher.exe')
                and {r['with_dlc'] for r in regional_exe['cases'] if r['status']=='passed'}=={False,True},'Regional EXE acceptance missing')
        required={f'build/android-{phase}-{orientation}-{tag}.log' for phase in ('regional-calendar','economy-network') for orientation in ('portrait','landscape')}
        require(set(native['logs'])==required and native.get('sdk')=='31','Native regional scope incomplete')
        require(native.get('test_apk_sha256')==file_digest(ROOT/'android/app/build/outputs/apk/androidTest/release/app-release-androidTest.apk'),'Native test artifact changed')
        require(all('regional_calendar_scope' in (ROOT/n).read_text(encoding='utf-8-sig') for n in required if 'regional-calendar' in n),'Native travel acceptance missing')
        require((ROOT/'android/app/build/reports/lint-results-release.txt').read_text().strip()=='No issues found.','Android lint required')
        require('Verifies' in (ROOT/f'build/android-signature-{tag}.log').read_text(encoding='utf-8'),'Signature evidence missing')
        performance=json.loads((ROOT/'build/regional-calendar-performance/report.json').read_text(encoding='utf-8'))
        require(performance['source_sha256']==inputs_digest(ROOT) and performance['version']==VERSION and performance['years']==100 and performance['repeats']>=3
                and performance['resume_state_equal'] and performance['settlement_checks']
                and len(performance['runs'])>=9 and all(r['repeat_and_reload_equal'] and r['supply_conserved'] for r in performance['runs']),
                'Matched hundred-year frozen-task/reload/conservation benchmark required')
        web_performance=json.loads((ROOT/'build/web-regional-performance/report.json').read_text(encoding='utf-8'))
        require(web_performance['source_sha256']==inputs_digest(ROOT) and web_performance['version']==VERSION
                and web_performance['status']=='passed' and web_performance['repeats']>=3
                and web_performance.get('full_state_equal') is True,'Matched real Web benchmark and full-state equivalence required')
        require(all(web_performance['medians']['current'][a] < web_performance['medians']['baseline'][a]
                    for a in ('1','2')),'Both real hundred-year actions must improve')
        require(len(web_performance['runs'])>=9 and all(len(r['dlcs'])==10 and len(r['rows'])==2
                and all(x['years']==100 for x in r['rows']) for r in web_performance['runs']), 'Web scope incomplete')
        require(all(r['version']==('2.16.1' if r['label']=='baseline' else VERSION)
                    for r in web_performance['runs'] if r['label'] in {'baseline','current'}), 'Wrong routing optimization comparison versions')
        for repeat in range(web_performance['repeats']):
            old=next(r for r in web_performance['runs'] if r['label']=='baseline' and r['repeat']==repeat)
            new=next(r for r in web_performance['runs'] if r['label']=='current' and r['repeat']==repeat)
            require(all(a.get('state_sha256') and a['state_sha256']==b.get('state_sha256') for a,b in zip(old['rows'],new['rows'])),
                    'Web optimization must preserve the complete business state after each century')
    if scoped.get('profile') in {'naming', 'natal', 'teachings', 'common-techniques', 'secret-arts', 'common-goods'}:
        natal = scoped['profile'] == 'natal'
        teachings = scoped['profile'] == 'teachings'
        common = scoped['profile'] == 'common-techniques'
        secret = scoped['profile'] == 'secret-arts'
        goods = scoped['profile'] == 'common-goods'
        phases = ('common-goods',) if goods else ('secret-arts','common-techniques') if secret else ('common-techniques',) if common else ('upper-teachings',) if teachings else ('content-naming','natal-materials') if natal else ('content-naming','strategic-war')
        required={f'build/android-{phase}-{orientation}-{tag}.log' for phase in phases for orientation in ('portrait','landscape')}
        require(set(native['logs'])==required and native.get('sdk')=='31','Native naming/war scope incomplete')
        require(native.get('test_apk_sha256')==file_digest(ROOT/'android/app/build/outputs/apk/androidTest/release/app-release-androidTest.apk'),'Native test artifact changed after acceptance')
        for name in native['logs']:
            marker='common_goods_scope' if goods else ('secret_arts_scope' if 'secret-arts' in name else 'common_techniques_scope') if secret else 'common_techniques_scope' if common else 'upper_teachings_scope' if teachings else 'content_naming_scope' if 'content-naming' in name else 'natal_materials_scope' if natal else 'strategic_war_scope'
            require(marker in (ROOT/name).read_text(encoding='utf-8-sig'),'Current native naming/war coverage missing')
        require((ROOT/'android/app/build/reports/lint-results-release.txt').read_text().strip()=='No issues found.','Android lint required')
        require('Verifies' in (ROOT/f'build/android-signature-{tag}.log').read_text(encoding='utf-8'),'Signature evidence missing')
        metadata=(ROOT/f'build/android-metadata-{tag}.log').read_text(encoding='utf-8')
        current_code=int(re.search(r'versionCode (\d+)',(ROOT/'android/app/build.gradle').read_text(encoding='utf-8'))[1])
        require(f"versionCode='{current_code}'" in metadata and f"versionName='{VERSION}-android.{current_code}'" in metadata and "sdkVersion:'31'" in metadata and 'application-debuggable' not in metadata,'APK metadata mismatch')
    if scoped.get('profile') == 'architecture':
        phases={'upper':'upper_scope','upper-teachings':'upper_teachings_scope',
            'natal-materials':'natal_materials_scope','asura':'asura_scope',
            'regional-calendar':'regional_calendar_scope','organizations':'organizations_scope',
            'audit-fixes':'audit_fixes_scope'}
        required={f'build/android-{phase}-{orientation}-{tag}.log' for phase in phases for orientation in ('portrait','landscape')}
        require(set(native['logs'])==required and native.get('sdk')=='31','Native character architecture scope incomplete')
        require(native.get('test_apk_sha256')==file_digest(ROOT/'android/app/build/outputs/apk/androidTest/release/app-release-androidTest.apk'),'Native test artifact changed')
        for phase,marker in phases.items():
            for orientation in ('portrait','landscape'):
                require(marker in (ROOT/f'build/android-{phase}-{orientation}-{tag}.log').read_text(encoding='utf-8-sig'),'Native character architecture marker missing')
        require((ROOT/'android/app/build/reports/lint-results-release.txt').read_text().strip()=='No issues found.','Android lint required')
        require('Verifies' in (ROOT/f'build/android-signature-{tag}.log').read_text(encoding='utf-8'),'Signature evidence missing')
        metadata=(ROOT/f'build/android-metadata-{tag}.log').read_text(encoding='utf-8')
        current_code=int(re.search(r'versionCode (\d+)',(ROOT/'android/app/build.gradle').read_text(encoding='utf-8'))[1])
        require(f"versionCode='{current_code}'" in metadata and f"versionName='{VERSION}-android.{current_code}'" in metadata and "sdkVersion:'31'" in metadata and 'application-debuggable' not in metadata,'APK metadata mismatch')
        architecture=json.loads((ROOT/'build/architecture-stage3/verification.json').read_text(encoding='utf-8'))
        require(architecture['status']=='passed' and architecture['inputs_sha256']==inputs_digest(ROOT), 'Architecture equivalence evidence differs from final source')
        require(architecture['algorithm_bodies']==119 and architecture['checkpoints']==413 and architecture['protected_files_unchanged'], 'Incomplete architecture equivalence/protected file evidence')
        require(all(file_digest(ROOT/name)==digest for name,digest in architecture['log_hashes'].items()), 'Architecture evidence changed')
    if scoped.get('profile') in {'buildings','building-visits'}:
        visits=scoped['profile']=='building-visits'
        phase='building-visits' if visits else 'buildings'
        required={f'build/android-{name}-{orientation}-{tag}.log' for name in (phase,'economy-enterprises') for orientation in ('portrait','landscape')}
        require(set(native['logs'])==required and native.get('sdk')=='31','Native building scope incomplete')
        require(native.get('test_apk_sha256')==file_digest(ROOT/'android/app/build/outputs/apk/androidTest/release/app-release-androidTest.apk'),'Native test APK changed')
        require(all('buildings_scope' in (ROOT/n).read_text(encoding='utf-8-sig') for n in required if '/android-buildings-' in n),'Native city/building acceptance missing')
        require(all(c.get('buildings_verified') for c in evidence['cases']),'Actual compiled building commands required with and without DLC')
        if visits:
            require(all(c.get('city_management_verified') for c in evidence['cases']),'Actual compiled city management and authored landscapes required')
            require(all('city_management_scope' in (ROOT/n).read_text(encoding='utf-8-sig') for n in required if '/android-building-visits-' in n),'Native management and landscape scope missing')
            require(all(c.get('building_visits_verified') for c in evidence['cases']),'Actual compiled visit branches required with and without DLC')
            require(all('building_visits_scope' in (ROOT/n).read_text(encoding='utf-8-sig') for n in required if '/android-building-visits-' in n),'Native visit scope missing')
        require((ROOT/'android/app/build/reports/lint-results-release.txt').read_text().strip()=='No issues found.','Android lint required')
        require('Verifies' in (ROOT/f'build/android-signature-{tag}.log').read_text(encoding='utf-8'),'Signature evidence missing')
        metadata=(ROOT/f'build/android-metadata-{tag}.log').read_text(encoding='utf-8')
        code=int(re.search(r'versionCode (\d+)',(ROOT/'android/app/build.gradle').read_text(encoding='utf-8'))[1])
        require(f"versionCode='{code}'" in metadata and f"versionName='{VERSION}-android.{code}'" in metadata and "sdkVersion:'31'" in metadata and 'application-debuggable' not in metadata,'APK metadata mismatch')
        selected={name for shard in scoped['tests'] for name in shard}
        if visits:
            from scripts.verify_scoped_release import BUILDING_VISIT_TESTS
            require(selected==set(BUILDING_VISIT_TESTS),'Building visit domain selection incomplete')
            require('browser_building_visits' in {r['name'] for r in scoped['runs']},'Four-theme visit browser required')
        else:require(selected=={p.relative_to(ROOT).as_posix() for p in (ROOT/'tests').rglob('test_*.py')},'Building feature release requires the complete repository test selection')
        require({'browser_buildings','browser_city_buildings','browser_economy_enterprises','browser_events_212'}<={r['name'] for r in scoped['runs']},'Building feature browsers incomplete')
        performance=json.loads((ROOT/'build/building-performance.json').read_text(encoding='utf-8'))
        if visits:require(all(r.get('visit_claims')==r['buildings'] and r.get('landscape_claims')==r['buildings'] and r.get('city_books')==r['buildings'] for r in performance['rows']),'Building visits performance must include persistent claim and finance records')
        require(performance.get('source_sha256')==inputs_digest(ROOT) and performance.get('version')==VERSION and all(r['economy_identical'] for r in performance['rows']),'Matched building performance/conservation evidence required')
    if scoped.get('profile')=='soul-lifecycle':
        from scripts.verify_scoped_release import SOUL_TESTS
        require(all(c.get('hunt_verified') for c in evidence['cases']),'Hunt compiled assets required')
        require(all(c.get('soul_verified') for c in evidence['cases']),'Soul compiled acceptance required with and without DLC')
        require(all(c.get('holiday_verified') for c in evidence['cases']),'Holiday compiled acceptance required with and without DLC')
        require(all(c.get('frontier_verified') for c in evidence['cases']),'Frontier compiled acceptance required with and without DLC')
        require(all(c.get('tide_verified') for c in evidence['cases']),'Tide achievement and two-theme compiled acceptance required')
        require({'browser_tide_theme','browser_themes_139','browser_desktop_navigation','browser_secret_art_training'}<={r['name'] for r in scoped['runs']},'Theme/navigation/secret browser acceptance required')
        require({'browser_frontier_skins','browser_release_301'}<={r['name'] for r in scoped['runs']},'Gun/swimwear and wardrobe entry browser acceptance required')
        require({name for shard in scoped['tests'] for name in shard}==set(SOUL_TESTS),'Soul related selection incomplete')
        require({'browser_soul_lifecycle','browser_swimwear_skins','browser_holiday_skins','browser_sect_tasks','browser_authored_techniques','browser_events_212'}<={r['name'] for r in scoped['runs']},'Soul/holiday/sect browser acceptance incomplete')
        required={f'build/android-soul-lifecycle-{o}-{tag}.log' for o in ('portrait','landscape')}
        require(set(native['logs'])==required and native.get('sdk')=='31','Soul Android 12 native scope incomplete')
        require(native.get('test_apk_sha256')==file_digest(ROOT/'android/app/build/outputs/apk/androidTest/release/app-release-androidTest.apk'),'Soul native test APK changed')
        require(all('hunt_beasts_scope' in (ROOT/n).read_text(encoding='utf-8-sig') for n in required),'Hunt native marker missing')
        require(all('soul_lifecycle_scope' in (ROOT/n).read_text(encoding='utf-8-sig') for n in required),'Soul native marker missing')
        require(all('holiday_skin_scope' in (ROOT/n).read_text(encoding='utf-8-sig') for n in required),'Holiday native marker missing')
        require(all('frontier_skin_scope' in (ROOT/n).read_text(encoding='utf-8-sig') for n in required),'Gun/swimwear native marker missing')
        require(all('tide_theme_scope' in (ROOT/n).read_text(encoding='utf-8-sig') for n in required),'Tide/two-theme native marker missing')
        require((ROOT/'android/app/build/reports/lint-results-release.txt').read_text().strip()=='No issues found.','Android lint required')
        require('Verifies' in (ROOT/f'build/android-signature-{tag}.log').read_text(encoding='utf-8'),'Signature evidence missing')
    if scoped.get('profile')=='authored':
        from scripts.verify_scoped_release import AUTHORED_TESTS, AUTHORED_BROWSERS
        require(all(c.get('authored_verified') for c in evidence['cases']),'3.1.0 compiled acceptance required with and without DLC')
        require({name for shard in scoped['tests'] for name in shard}==set(AUTHORED_TESTS),'3.1.0 related selection incomplete')
        require(set(AUTHORED_BROWSERS)<={r['name'] for r in scoped['runs']},'3.1.0 real browser acceptance incomplete')
        required={f'build/android-authored-{o}-{tag}.log' for o in ('portrait','landscape')}
        require(set(native['logs'])==required and native.get('sdk')=='31','3.1.0 native scope incomplete')
        require(native.get('test_apk_sha256')==file_digest(ROOT/'android/app/build/outputs/apk/androidTest/release/app-release-androidTest.apk'),'3.1.0 native test APK changed')
        require(all('authored_scope' in (ROOT/n).read_text(encoding='utf-8-sig') for n in required),'3.1.0 native marker missing')
        require((ROOT/'android/app/build/reports/lint-results-release.txt').read_text().strip()=='No issues found.','Android lint required')
        require('Verifies' in (ROOT/f'build/android-signature-{tag}.log').read_text(encoding='utf-8'),'Signature evidence missing')
        metadata=(ROOT/f'build/android-metadata-{tag}.log').read_text(encoding='utf-8')
        code=int(re.search(r'versionCode (\d+)',(ROOT/'android/app/build.gradle').read_text(encoding='utf-8'))[1])
        require(f"versionCode='{code}'" in metadata and f"versionName='{VERSION}-android.{code}'" in metadata and "sdkVersion:'31'" in metadata and 'application-debuggable' not in metadata,'APK metadata mismatch')
    if scoped.get('profile')=='update301':
        from scripts.verify_scoped_release import UPDATE301_TESTS, UPDATE301_BROWSERS
        require(all(c.get('update301_verified') for c in evidence['cases']),'3.0.1 compiled acceptance required with and without DLC')
        require({name for shard in scoped['tests'] for name in shard}==set(UPDATE301_TESTS),'3.0.1 related selection incomplete')
        require(set(UPDATE301_BROWSERS)<={r['name'] for r in scoped['runs']},'3.0.1 real browser acceptance incomplete')
        required={f'build/android-update301-{o}-{tag}.log' for o in ('portrait','landscape')}
        require(set(native['logs'])==required and native.get('sdk')=='31','3.0.1 native scope incomplete')
        require(native.get('test_apk_sha256')==file_digest(ROOT/'android/app/build/outputs/apk/androidTest/release/app-release-androidTest.apk'),'3.0.1 native test APK changed')
        require(all('update301_scope' in (ROOT/n).read_text(encoding='utf-8-sig') for n in required),'3.0.1 native marker missing')
        require((ROOT/'android/app/build/reports/lint-results-release.txt').read_text().strip()=='No issues found.','Android lint required')
        require('Verifies' in (ROOT/f'build/android-signature-{tag}.log').read_text(encoding='utf-8'),'Signature evidence missing')
        metadata=(ROOT/f'build/android-metadata-{tag}.log').read_text(encoding='utf-8')
        code=int(re.search(r'versionCode (\d+)',(ROOT/'android/app/build.gradle').read_text(encoding='utf-8'))[1])
        require(f"versionCode='{code}'" in metadata and f"versionName='{VERSION}-android.{code}'" in metadata and "sdkVersion:'31'" in metadata and 'application-debuggable' not in metadata,'APK metadata mismatch')
    if scoped.get('profile')=='visual':
        selected={name for shard in scoped['tests'] for name in shard}
        if scoped.get('regression_scope') == 'alpha6-focused':
            from scripts.verify_scoped_release import VISUAL_ALPHA6_TESTS
            require(selected==set(VISUAL_ALPHA6_TESTS),'Focused alpha.6 selection incomplete')
            require('not full repository regression' in scoped.get('scope',''),'Focused scope must be declared')
            require('browser_home_scenes' in {r['name'] for r in scoped['runs']},'Home scene browser required')
            require(all(c.get('home_scenes_verified') for c in evidence['cases']),'Compiled home scenes with/without DLC required')
            require(all('home_scenes_scope' in (ROOT/n).read_text(encoding='utf-8-sig') for n in native['logs']),'Native home scene acceptance required')
        elif scoped.get('regression_scope') == 'alpha5-focused':
            from scripts.verify_scoped_release import VISUAL_ALPHA5_TESTS
            require(selected==set(VISUAL_ALPHA5_TESTS),'Focused alpha.5 selection incomplete')
            require('not full repository regression' in scoped.get('scope',''),'Focused scope must be declared')
            require('browser_path_characters' in {r['name'] for r in scoped['runs']},'Three-path browser required')
            require(all(c.get('path_characters_verified') for c in evidence['cases']),'Compiled path characters with/without DLC required')
            require(all('path_character_scope' in (ROOT/n).read_text(encoding='utf-8-sig') for n in native['logs']),'Native three-path acceptance required')
        elif scoped.get('regression_scope') == 'alpha4-focused':
            from scripts.verify_scoped_release import VISUAL_ALPHA4_TESTS
            require(selected==set(VISUAL_ALPHA4_TESTS),'Focused alpha.4 selection incomplete')
            require('not full repository regression' in scoped.get('scope',''),'Focused scope must be declared')
            require({'browser_monster_release','browser_monster_flora_visuals'}<={r['name'] for r in scoped['runs']},'Monster browser acceptance required')
            require(all(c.get('monster_visuals_verified') for c in evidence['cases']),'Compiled monster assets with/without DLC required')
            require(all('monster_visual_scope' in (ROOT/n).read_text(encoding='utf-8-sig') for n in native['logs']),'Native monster appearance/action acceptance required')
        elif scoped.get('regression_scope') == 'alpha3-focused':
            from scripts.verify_scoped_release import VISUAL_ALPHA3_TESTS
            require(selected==set(VISUAL_ALPHA3_TESTS), 'Focused alpha.3 domain/upstream selection incomplete')
            require('not full repository regression' in scoped.get('scope',''), 'Focused scope must be declared')
        else:
            require(selected=={p.relative_to(ROOT).as_posix() for p in (ROOT/'tests').rglob('test_*.py')},'Visual release requires full regression selection')
            if VERSION=='3.0.0':
                require({'browser_monster_aquatic_visuals','browser_monster_fox_visuals','browser_monster_insect_visuals','browser_monster_serpent_visuals','browser_monster_turtle_visuals'}<={r['name'] for r in scoped['runs']},'Stable monster DLC-disable browser coverage incomplete')
                require({'browser_monster_release','browser_monster_flora_visuals','browser_path_characters','browser_asura_characters','browser_home_scenes','browser_spell_domains','browser_asura_prison','browser_trial_variants'}<={r['name'] for r in scoped['runs']},'Stable visual browser coverage incomplete')
                require(all(all(c.get(k) for k in ('monster_visuals_verified','path_characters_verified','home_scenes_verified','domain_ink_verified')) for c in evidence['cases']),'Stable compiled visual coverage incomplete')
                require(all(all(marker in (ROOT/n).read_text(encoding='utf-8-sig') for marker in ('monster_visual_scope','path_character_scope','home_scenes_scope','domain_ink_scope')) for n in native['logs']),'Stable native visual coverage incomplete')
        require({'browser_visual_release','browser_pixel_ui','browser_themes_139','browser_events_212','browser_building_visits'}<={r['name'] for r in scoped['runs']},'Visual/legacy browsers incomplete')
        require(all(c.get('visual_ui_verified') for c in evidence['cases']),'Actual compiled optional UI required with and without DLC')
        require(all(c.get('dlc_visual_verified') for c in evidence['cases']),'Compiled DLC image ownership and disabled fallback required')
        require(all(c.get('visual_additions_verified') and c.get('domain_replay_verified') for c in evidence['cases']),'Compiled NPC and domain editor acceptance required')
        require(all(c.get('protagonist_static_verified') for c in evidence['cases']),'Compiled selected protagonist redraws required')
        require({'browser_npc_art','browser_voisinage_editor','browser_domain_replay','browser_combat_replay','browser_combat_groups'}<={r['name'] for r in scoped['runs']},'Social art and domain editor browsers incomplete')
        required={f'build/android-visual-ui-{orientation}-{tag}.log' for orientation in ('portrait','landscape')}
        require(set(native['logs'])==required and native.get('sdk')=='31','Android 12 visual native scope incomplete')
        require(native.get('test_apk_sha256')==file_digest(ROOT/'android/app/build/outputs/apk/androidTest/release/app-release-androidTest.apk'),'Native visual test APK changed')
        require(all('visual_ui_scope' in (ROOT/n).read_text(encoding='utf-8-sig') for n in required),'Native visual marker missing')
        require(all(all(marker in (ROOT/n).read_text(encoding='utf-8-sig') for marker in ['visual_additions_scope','domain_replay_scope','protagonist_static_scope']) for n in required),'Native NPC, domain and selected protagonist marker missing')
        require((ROOT/'android/app/build/reports/lint-results-release.txt').read_text().strip()=='No issues found.','Android lint required')
        require('Verifies' in (ROOT/f'build/android-signature-{tag}.log').read_text(encoding='utf-8'),'Signature evidence missing')
        metadata=(ROOT/f'build/android-metadata-{tag}.log').read_text(encoding='utf-8')
        code=int(re.search(r'versionCode (\d+)',(ROOT/'android/app/build.gradle').read_text(encoding='utf-8'))[1])
        require(f"versionCode='{code}'" in metadata and f"versionName='{VERSION}-android.{code}'" in metadata and "sdkVersion:'31'" in metadata and 'application-debuggable' not in metadata,'APK metadata mismatch')
    if scoped.get('profile')=='combat-alpha':
        from scripts.verify_scoped_release import COMBAT_ALPHA_TESTS
        selected={name for shard in scoped['tests'] for name in shard}
        require(selected==set(COMBAT_ALPHA_TESTS),'Focused combat/DLC regressions incomplete')
        require({'browser_alpha2_dlc_fixes','browser_combat_replay','browser_combat_groups','browser_events_212'}<={r['name'] for r in scoped['runs']},'Focused combat/DLC browser evidence incomplete')
        require(all(c.get('combat_alpha_verified') and c.get('dlc_fixes_verified') for c in evidence['cases']),'Compiled combat/DLC acceptance required with and without DLC')
        required={f'build/android-combat-alpha-{o}-{tag}.log' for o in ('portrait','landscape')}
        require(set(native['logs'])==required and native.get('sdk')=='31','Android 12 focused combat scope incomplete')
        require(native.get('test_apk_sha256')==file_digest(ROOT/'android/app/build/outputs/apk/androidTest/release/app-release-androidTest.apk'),'Native combat test APK changed')
        require(all('combat_alpha_scope' in (ROOT/n).read_text(encoding='utf-8-sig') for n in required),'Native combat/DLC marker missing')
        require((ROOT/'android/app/build/reports/lint-results-release.txt').read_text().strip()=='No issues found.','Android lint required')
        require('Verifies' in (ROOT/f'build/android-signature-{tag}.log').read_text(encoding='utf-8'),'Signature evidence missing')
        metadata=(ROOT/f'build/android-metadata-{tag}.log').read_text(encoding='utf-8')
        code=int(re.search(r'versionCode (\d+)',(ROOT/'android/app/build.gradle').read_text(encoding='utf-8'))[1])
        require(f"versionCode='{code}'" in metadata and f"versionName='{VERSION}-android.{code}'" in metadata and "sdkVersion:'31'" in metadata and 'application-debuggable' not in metadata,'APK metadata mismatch')
    dlcs={p.parent.name:json.loads(p.read_text(encoding='utf-8'))['version'] for p in (ROOT/'dlc').glob('*/manifest.json')}
    base=dict(base_version=VERSION,save_schema=SAVE_SCHEMA_VERSION,compatible_save_schemas=[SAVE_SCHEMA_VERSION],
              incompatible_save_schemas=f'1–{SAVE_SCHEMA_VERSION-1}; no migration',dlc_versions=dlcs,
              validation_scope=scoped['scope'],tests=tests,runs=scoped['runs'],
              regression=regression,save_transfer_smoke_tests=int(extra[1]),
              save_transfer_smoke_in_regression=transfer_in_regression,
              save_transfer_log=f'build/save-transfer-{tag}.log',inputs_sha256=inputs_digest(ROOT))
    if reconciliation is not None:base['regression_reconciliation']=reconciliation
    if scoped.get('profile') == 'architecture':
        base['architecture']=architecture
    if scoped.get('profile') == 'regional':
        base['performance']=performance
        base['web_performance']=web_performance
        base['rift_audit']=rift_audit
    if scoped.get('profile') in {'buildings','building-visits'}:base['performance']=performance
    if scoped.get('profile') == 'common-goods':
        upstream=json.loads((ROOT/'build/combat-engine-upstream-2151.json').read_text(encoding='utf-8'))
        require(upstream['inputs_sha256']==base['inputs_sha256'] and upstream['status']=='passed'
                and upstream['test_source_sha256']==file_digest(ROOT/'tests/test_engine.py')
                and upstream['log_sha256']==file_digest(ROOT/'build/combat-engine-upstream-2151.log')
                and upstream['xml_sha256']==file_digest(ROOT/'build/combat-engine-upstream-2151.xml'),
                'Focused upstream combat evidence must match final tests and sources')
        tests+=upstream['tests'];base['tests']=tests;base['combat_upstream']=upstream
        performance=json.loads((ROOT/'build/common-goods-performance/report.json').read_text(encoding='utf-8'))
        require(performance['version']==VERSION and performance['source_sha256']==base['inputs_sha256'],
                'Performance evidence must match final release inputs')
        require(len(performance['scenarios'])==3 and performance['runs']>=3
                and all(r['cache_full_state_equal'] for r in performance['scenarios']),
                'Matched action performance and cache state equivalence required')
        base['performance']=performance
        combat=json.loads((ROOT/'build/combat-calibration-2151/report.json').read_text(encoding='utf-8'))
        require(combat['source_sha256']==base['inputs_sha256'] and combat['version']==VERSION,
                'Combat calibration must match final release inputs')
        base['combat_calibration']=dict(source_sha256=combat['source_sha256'],
            battles={mode:data['battles'] for mode,data in combat['modes'].items()},
            story_choices=combat['story_choices'],changed_story_choices=combat['changed_story_choices'])
    exe=ROOT/'dist/launcher.exe';named=ROOT/f'dist/浮生问道-v{VERSION}.exe';shutil.copyfile(exe,named)
    win=dict(base,platform='Windows',exe_sha256=file_digest(exe),with_and_without_dlc_verified=True)
    try:shutil.copyfile(exe,ROOT/'launcher.exe');win['root_launcher_updated']=True
    except PermissionError:win['root_launcher_updated']=False
    manifest=ROOT/f'dist/release-{VERSION}.json';manifest.write_text(json.dumps(win,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    output=ROOT/f'dist/浮生问道-v{VERSION}-Windows.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        z.write(exe,'launcher.exe');z.write(manifest,manifest.name)
        z.writestr('game_config.txt','Debug=False\n')
        if scoped.get('profile') == 'architecture':
            z.write(ROOT/'build/architecture-stage3/verification.json',f'architecture-{VERSION}.json')
        for name in ['README.md','CHANGELOG.md','AGENTS.md']:z.write(ROOT/name,name)
        if scoped.get('profile') == 'regional':
            z.write(ROOT/'build/regional-calendar-performance/report.json',f'performance-{VERSION}.json')
            z.write(ROOT/'build/web-regional-performance/report.json',f'web-performance-{VERSION}.json')
        if scoped.get('profile') == 'common-goods':
            z.write(ROOT/'build/common-goods-performance/report.md',f'performance-{VERSION}.md')
            z.write(ROOT/'build/combat-calibration-2151/report.md',f'combat-calibration-{VERSION}.md')
            z.write(ROOT/'build/combat-calibration-2151/report.json',f'combat-calibration-{VERSION}.json')
        for name in ['scripts/debug_agent.py','cultivation_life/__init__.py','cultivation_life/version.py',
                     'cultivation_life/debug/__init__.py','cultivation_life/debug/agent.py','cultivation_life/debug/client.py']:
            z.write(ROOT/name,name)
        for folder in ['docs','dlc','mods']:
            for p in sorted((ROOT/folder).rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.pyo'}:z.write(p,p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as z:require(z.testzip() is None,'Windows archive damaged')
    target=ROOT/f'dist/浮生问道-v{VERSION}-Android12.apk';shutil.copyfile(apk,target)
    code=int(re.search(r'versionCode (\d+)',(ROOT/'android/app/build.gradle').read_text(encoding='utf-8'))[1])
    android=dict(base,platform='Android 12',android_version=f'{VERSION}-android.{code}',version_code=code,
                 apk_sha256=file_digest(apk),native=native,physical_device_tested=False)
    am=ROOT/f'dist/release-{VERSION}-android.{code}.json';am.write_text(json.dumps(android,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with zipfile.ZipFile(ROOT/f'dist/浮生问道-v{VERSION}-Android12.zip','w',zipfile.ZIP_DEFLATED) as z:
        z.write(target,target.name);z.write(am,am.name);z.write(ROOT/'android/README.md','README.md')
        if scoped.get('profile') == 'architecture':
            z.write(ROOT/'build/architecture-stage3/verification.json',f'architecture-{VERSION}.json')
        if scoped.get('profile') == 'regional':
            z.write(ROOT/'build/regional-calendar-performance/report.json',f'performance-{VERSION}.json')
            z.write(ROOT/'build/web-regional-performance/report.json',f'web-performance-{VERSION}.json')
        if scoped.get('profile') == 'common-goods':
            z.write(ROOT/'build/common-goods-performance/report.md',f'performance-{VERSION}.md')
            z.write(ROOT/'build/combat-calibration-2151/report.md',f'combat-calibration-{VERSION}.md')
            z.write(ROOT/'build/combat-calibration-2151/report.json',f'combat-calibration-{VERSION}.json')
    if scoped.get('profile') in {'teachings','visual','combat-alpha','update301','authored'}:
        updates=[('guixu-tide','归墟之潮'),('tianji-artifacts','巧夺天工')] if scoped['profile']=='combat-alpha' else [('guixu-tide','归墟之潮')] if scoped['profile']=='visual' else [('buddhist-dharma','诸法无我'),('sage-way','圣人之道')]
        if scoped['profile']=='authored':updates=[('authored-techniques','著经立道')]
        if scoped['profile']=='update301':updates=[('monster-civilizations','万灵争衡')]
        if scoped.get('regression_scope')=='alpha4-focused':updates.append(('monster-bloodlines','万妖归宗'))
        if scoped.get('regression_scope')=='alpha5-focused':updates=[('ghost-reincarnation','百鬼夜行'),('sage-way','圣人之道'),('buddhist-dharma','诸法无我')]
        if scoped.get('regression_scope')=='alpha6-focused':updates=[]
        for package, title in updates:
            version = dlcs[package]
            destination = ROOT / f'dist/{title}-v{version}.zip'
            with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
                for p in sorted((ROOT/'dlc'/package).rglob('*')):
                    if p.is_file() and '__pycache__' not in p.parts:
                        z.write(p,p.relative_to(ROOT).as_posix())
                note='docs/alpha2-release.md' if scoped['profile']=='combat-alpha' else 'docs/visual-assets.md' if scoped['profile']=='visual' else 'docs/upper-teachings.md'
                if scoped['profile']=='authored':note='docs/authored-techniques.md'
                if scoped['profile']=='update301':note='docs/release-301.md'
                if package=='monster-bloodlines':note='docs/alpha4-release.md'
                if scoped.get('regression_scope')=='alpha5-focused':note='docs/alpha5-release.md'
                z.write(ROOT/note,note)
                z.writestr('安装说明.txt',f'配套本体 v{VERSION}，仅支持结构 {SAVE_SCHEMA_VERSION}。解压至游戏根目录，覆盖对应 dlc/{package} 文件夹；重启生效。旧本体需先升级；Android 请安装同版签名 APK。用户开关与存档不会被本包覆盖。\n')
                z.writestr('release.json',json.dumps(dict(base_version=VERSION,dlc=package,version=version,inputs_sha256=base['inputs_sha256']),ensure_ascii=False,indent=2))
            with zipfile.ZipFile(destination) as z:
                require(z.testzip() is None,'DLC archive damaged')
    print(json.dumps(dict(version=VERSION,tests=tests,windows=str(output),android=str(target)),ensure_ascii=False))


if __name__=='__main__':main()

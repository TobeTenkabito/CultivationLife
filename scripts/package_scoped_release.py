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
    suites=list(ET.parse(ROOT/f'build/scoped-{tag}.xml').getroot().iter('testsuite'))
    require(suites and all(int(s.get('failures',0))==0 and int(s.get('errors',0))==0 for s in suites),'Related regressions failed')
    tests=sum(int(s.get('tests',0)) for s in suites)
    transfer=(ROOT/f'build/save-transfer-{tag}.log').read_text(encoding='utf-8-sig')
    extra=re.search(r'(\d+) passed',transfer)
    require(extra is not None and 'failed' not in transfer.lower() and 'ERROR' not in transfer,'Save transfer smoke tests failed')
    tests+=int(extra[1])
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
    dlcs={p.parent.name:json.loads(p.read_text(encoding='utf-8'))['version'] for p in (ROOT/'dlc').glob('*/manifest.json')}
    base=dict(base_version=VERSION,save_schema=SAVE_SCHEMA_VERSION,compatible_save_schemas=[10],
              incompatible_save_schemas='1–9; no migration',dlc_versions=dlcs,
              validation_scope=scoped['scope'],tests=tests,runs=scoped['runs'],
              save_transfer_log=f'build/save-transfer-{tag}.log',inputs_sha256=inputs_digest(ROOT))
    if scoped.get('profile') == 'regional':
        base['performance']=performance
        base['web_performance']=web_performance
        base['rift_audit']=rift_audit
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
        if scoped.get('profile') == 'regional':
            z.write(ROOT/'build/regional-calendar-performance/report.json',f'performance-{VERSION}.json')
            z.write(ROOT/'build/web-regional-performance/report.json',f'web-performance-{VERSION}.json')
        if scoped.get('profile') == 'common-goods':
            z.write(ROOT/'build/common-goods-performance/report.md',f'performance-{VERSION}.md')
            z.write(ROOT/'build/combat-calibration-2151/report.md',f'combat-calibration-{VERSION}.md')
            z.write(ROOT/'build/combat-calibration-2151/report.json',f'combat-calibration-{VERSION}.json')
    if scoped.get('profile') == 'teachings':
        for package, title in [('buddhist-dharma','诸法无我'),('sage-way','圣人之道')]:
            version = dlcs[package]
            destination = ROOT / f'dist/{title}-v{version}.zip'
            with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
                for p in sorted((ROOT/'dlc'/package).rglob('*')):
                    if p.is_file() and '__pycache__' not in p.parts:
                        z.write(p,p.relative_to(ROOT).as_posix())
                z.write(ROOT/'docs/upper-teachings.md','docs/upper-teachings.md')
                z.writestr('安装说明.txt',f'配套本体 v{VERSION}，仅支持结构 10。解压至游戏根目录，覆盖对应 dlc/{package} 文件夹；重启生效。旧本体需先升级；Android 请安装同版签名 APK。用户开关与存档不会被本包覆盖。\n')
                z.writestr('release.json',json.dumps(dict(base_version=VERSION,dlc=package,version=version,inputs_sha256=base['inputs_sha256']),ensure_ascii=False,indent=2))
            with zipfile.ZipFile(destination) as z:
                require(z.testzip() is None,'DLC archive damaged')
    print(json.dumps(dict(version=VERSION,tests=tests,windows=str(output),android=str(target)),ensure_ascii=False))


if __name__=='__main__':main()

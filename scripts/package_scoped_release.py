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
    apk=ROOT/'android/app/build/outputs/apk/release/app-release.apk'
    require(native['apk_sha256']==file_digest(apk) and native['signed'] and native['status']=='passed','Native/signature evidence invalid')
    for logfile in native['logs']:
        log=(ROOT/logfile).read_text(encoding='utf-8-sig')
        require('status=passed' in log and 'status=failed' not in log,'Native scope failed')
        require(file_digest(ROOT/logfile)==native['log_hashes'][logfile],'Native evidence changed')
    with zipfile.ZipFile(apk) as archive:
        provenance=validate_apk_inputs(ROOT,archive)
    dlcs={p.parent.name:json.loads(p.read_text(encoding='utf-8'))['version'] for p in (ROOT/'dlc').glob('*/manifest.json')}
    base=dict(base_version=VERSION,save_schema=SAVE_SCHEMA_VERSION,compatible_save_schemas=[10],
              incompatible_save_schemas='1–9; no migration',dlc_versions=dlcs,
              validation_scope=scoped['scope'],tests=tests,runs=scoped['runs'],
              save_transfer_log=f'build/save-transfer-{tag}.log',inputs_sha256=inputs_digest(ROOT))
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
    print(json.dumps(dict(version=VERSION,tests=tests,windows=str(output),android=str(target)),ensure_ascii=False))


if __name__=='__main__':main()

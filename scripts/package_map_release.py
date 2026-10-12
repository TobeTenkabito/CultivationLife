"""Package the exact map-only release after scoped source and native acceptance."""
import hashlib,io,json,re,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cultivation_life.version import BASE_GAME_VERSION as VERSION
from cultivation_life.save_schema import SAVE_SCHEMA_VERSION
from scripts.release_evidence import require,validate_evidence
from scripts.map_release_evidence import validate,digest
from scripts.android_provenance import validate_apk_inputs
from scripts.package_windows import AGENT_FILES

def main():
 r=validate(ROOT,VERSION);rid=VERSION.replace('.','');exe=ROOT/'dist/launcher.exe';exe_receipt=json.loads((ROOT/f'build/exe-{rid}-verification.json').read_text(encoding='utf8'));validate_evidence(ROOT,VERSION,exe_receipt)
 apk=ROOT/'android/app/build/outputs/apk/release/app-release.apk';apk_sha=digest(apk);native=json.loads((ROOT/f'build/android-native-{rid}-verification.json').read_text(encoding='utf8'))
 require(native.get('inputs_sha256')==r['inputs_sha256'] and native.get('apk_sha256')==apk_sha,'Native evidence is stale')
 require({x['orientation'] for x in native.get('phases',[])}=={'portrait','landscape'} and all(x.get('passed') and x.get('phase')=='maps-2131' for x in native['phases']),'Both native map orientations must pass')
 for row in native['phases']:
  text=(ROOT/'build'/row['log']).read_text(encoding='utf8');require('status=passed' in text and 'status=failed' not in text and 'Process crashed' not in text and digest(ROOT/'build'/row['log'])==row['sha256'],'Changed or bad native evidence')
 require(apk_sha in (ROOT/f'build/android-installed-sha256-{rid}.log').read_text(),'Installed APK differs from release')
 signature=(ROOT/f'build/android-signature-{rid}.log').read_text();require('Verifies' in signature,'Signed APK signature verification required')
 code=int(re.search(r'versionCode (\d+)',(ROOT/'android/app/build.gradle').read_text())[1]);android_version=f'{VERSION}-android.{code}'
 metadata=(ROOT/f'build/android-metadata-{rid}.log').read_text();require(f"versionCode='{code}'" in metadata and f"versionName='{android_version}'" in metadata and "sdkVersion:'31'" in metadata and 'application-debuggable' not in metadata,'APK metadata mismatch')
 require((ROOT/'android/app/build/reports/lint-results-release.txt').read_text().strip()=='No issues found.','Android lint required')
 with zipfile.ZipFile(apk) as z:
  provenance=validate_apk_inputs(ROOT,z);require(z.testzip() is None,'APK integrity check failed')
  require(all(f'lib/{abi}/libpython3.13.so' in z.namelist() for abi in ['arm64-v8a','x86_64']),'Missing Android ABI')
  with zipfile.ZipFile(io.BytesIO(z.read('assets/game-assets.zip'))) as assets:
   for name in ['web/map-scene.js','web/map-atlas.js','web/map-layouts.js','content/maps.json']:require(assets.read(name)==(ROOT/name).read_bytes(),'Map assets changed: '+name)
   require(not any(n.startswith('data/') for n in assets.namelist()),'User data included in APK')
 versions={p.parent.name:json.loads(p.read_text(encoding='utf8'))['version'] for p in (ROOT/'dlc').glob('*/manifest.json')}
 shared=dict(base_version=VERSION,save_schema=SAVE_SCHEMA_VERSION,inputs_sha256=r['inputs_sha256'],dlc_versions=versions,full_repository_regression=False,validation_scope='User-authorized map, routes, territory, transport, transition and UI checks',passed_tests=r['passed_tests'],browser_cases=r['browser_cases'],worlds=11,validation_receipt='map-release-2131.json')
 dist=ROOT/'dist';dist.mkdir(exist_ok=True);exe_bytes=exe.read_bytes();named=dist/f'浮生问道-v{VERSION}.exe';named.write_bytes(exe_bytes)
 try:(ROOT/'launcher.exe').write_bytes(exe_bytes);root_updated=True
 except PermissionError:root_updated=False
 win_manifest=dist/f'release-{VERSION}.json';win_manifest.write_text(json.dumps(dict(shared,platform='Windows',exe_sha256=digest(exe),root_launcher_updated=root_updated),ensure_ascii=False,indent=2),encoding='utf8')
 windows=dist/f'浮生问道-v{VERSION}-Windows.zip'
 with zipfile.ZipFile(windows,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  z.write(named,'launcher.exe');z.write(win_manifest,win_manifest.name);z.write(ROOT/'build/map-release-2131.json','verification/map-release-2131.json');z.write(ROOT/'build'/f'exe-{rid}-verification.json',f'verification/exe-{rid}-verification.json')
  for name in ['README.md','CHANGELOG.md','AGENTS.md',*AGENT_FILES]:z.write(ROOT/name,name)
  for p in (ROOT/'docs').glob('*.md'):z.write(p,p.relative_to(ROOT).as_posix())
  z.write(ROOT/'docs/world-transition-state-contract.json','docs/world-transition-state-contract.json');z.writestr('game_config.txt','Debug=False\n')
  for folder in ['dlc','mods']:
   for p in (ROOT/folder).rglob('*'):
    if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.pyc','.pyo']:z.write(p,p.relative_to(ROOT).as_posix())
 with zipfile.ZipFile(windows) as z:
  require(z.testzip() is None and hashlib.sha256(z.read('launcher.exe')).hexdigest()==digest(exe),'Windows archive differs from tested executable')
  require(not any('data/saves' in n or 'ui_preferences.json' in n for n in z.namelist()),'User files included in Windows archive')
 target=dist/f'浮生问道-v{VERSION}-Android12.apk';target.write_bytes(apk.read_bytes())
 am=dist/f'release-{android_version}.json';am.write_text(json.dumps(dict(shared,platform='Android',android_version=android_version,version_code=code,apk_sha256=apk_sha,native_phases=2,native_cases=88,tested_android='Android 12 API 31 x86_64 emulator',physical_device_tested=False,included_abis=['arm64-v8a','x86_64']),ensure_ascii=False,indent=2),encoding='utf8')
 android=dist/f'浮生问道-v{VERSION}-Android12.zip'
 with zipfile.ZipFile(android,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for p,name in [(target,target.name),(am,am.name),(ROOT/'android/README.md','安卓说明.md'),(ROOT/'CHANGELOG.md','CHANGELOG.md'),(ROOT/'docs/maps-2131.md','立体地图说明.md'),(ROOT/'android/app/src/main/mobile/NOTICE.txt','NOTICE.txt'),(ROOT/'build/map-release-2131.json','verification/map-release-2131.json'),(ROOT/'build'/f'android-native-{rid}-verification.json',f'verification/android-native-{rid}-verification.json')]:z.write(p,name)
 with zipfile.ZipFile(android) as z:require(z.testzip() is None and hashlib.sha256(z.read(target.name)).hexdigest()==apk_sha,'Android archive integrity/hash mismatch')
 validate_evidence(ROOT,VERSION,exe_receipt);validate(ROOT,VERSION)
 print(json.dumps(dict(version=VERSION,tests=r['passed_tests'],browser_cases=r['browser_cases'],windows=str(windows),android=str(android),apk=str(target)),ensure_ascii=False))
if __name__=='__main__':main()

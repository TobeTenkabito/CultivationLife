"""Publish the exact signed APK after release and Android 12 checks."""
import hashlib
import io
import json
import re
import runpy
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.android_css import compile_css
from scripts.release_evidence import require
VERSION = runpy.run_path(str(ROOT / 'cultivation_life/version.py'))['BASE_GAME_VERSION']
RELEASE_ID = VERSION.replace('.', '')
VERSION_CODE = int(re.search(r'versionCode (\d+)', (ROOT/'android/app/build.gradle').read_text(encoding='utf-8'))[1])
ANDROID_VERSION = f'{VERSION}-android.{VERSION_CODE}'

def main():
    def log(name):
        return (ROOT/'build'/name).read_text(encoding='utf-8', errors='replace')
    tests = log(f'release-{RELEASE_ID}-tests.log')
    passed = re.search(r'(\d+) passed in', tests)
    require(bool(passed) and 'failed' not in tests and 'ERROR' not in tests, 'Full regression suite must pass')
    for name in (f'android-experience-{RELEASE_ID}.log', f'android-institutions-{RELEASE_ID}.log', f'android-governance-{RELEASE_ID}.log', f'android-economy-{RELEASE_ID}.log', f'android-upper-{RELEASE_ID}.log', f'android-trials-{RELEASE_ID}.log', f'android-save-transfer-{RELEASE_ID}.log', f'android-initial-{RELEASE_ID}.log', f'android-immortal-{RELEASE_ID}.log', f'android-minor-{RELEASE_ID}.log', f'android-tutorial-{RELEASE_ID}.log'):
        require('status=passed' in log(name) and 'status=failed' not in log(name), name)
    require('status=passed' in log(f'android-bulk-{RELEASE_ID}.log') and 'status=failed' not in log(f'android-bulk-{RELEASE_ID}.log'), 'Android bulk checks must pass')
    require('status=passed' in log(f'android-upper-voisinage-{RELEASE_ID}.log') and 'status=failed' not in log(f'android-upper-voisinage-{RELEASE_ID}.log'), 'Android upper voisinage checks must pass')
    require('roundtrip passed' in log(f'save-crossplatform-{RELEASE_ID}.log'), 'Cross-platform save roundtrip must pass')
    require('status=passed' in log(f'android-fusion-{RELEASE_ID}.log') and 'status=failed' not in log(f'android-fusion-{RELEASE_ID}.log'), 'Android fusion checks must pass')
    for orientation in ('portrait', 'landscape'):
        result = log(f'android-asura-{orientation}-{RELEASE_ID}.log')
        require('status=passed' in result and 'status=failed' not in result, f'Android Asura {orientation} checks must pass')
    require('Verifies' in log(f'android-signature-{RELEASE_ID}.log'), 'Android APK signature must verify')
    metadata = log(f'android-metadata-{RELEASE_ID}.log')
    require(f"versionCode='{VERSION_CODE}'" in metadata and f"versionName='{ANDROID_VERSION}'" in metadata, 'Android version metadata must match the release')
    require("sdkVersion:'31'" in metadata and 'application-debuggable' not in metadata, 'Android APK must target the expected minimum SDK and be non-debuggable')
    require((ROOT/'android/app/build/reports/lint-results-release.txt').read_text(encoding='utf-8').strip() == 'No issues found.', 'Android release lint must pass')
    require('Quick-start regression passed' in log(f'quick-start-ui-{RELEASE_ID}.log'), 'Quick-start UI checks must pass')
    source = ROOT/'android/app/build/outputs/apk/release/app-release.apk'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    require(digest in log(f'android-installed-sha256-{RELEASE_ID}.log').lower(), 'APK hash must match the installed and tested APK')
    with zipfile.ZipFile(source) as apk:
        require(apk.testzip() is None, 'APK ZIP integrity check failed')
        for abi in ('arm64-v8a', 'x86_64'):
            require(f'lib/{abi}/libpython3.13.so' in apk.namelist(), f'Missing Python library for {abi}')
        with zipfile.ZipFile(io.BytesIO(apk.read('assets/game-assets.zip'))) as assets:
            require(assets.read('web/app.js') == (ROOT/'web/app.js').read_bytes(), 'Packaged web/app.js differs from source')
            require(assets.read('web/npc-contacts.js') == (ROOT/'web/npc-contacts.js').read_bytes(), 'Packaged web/npc-contacts.js differs from source')
            require(assets.read('web/map-directory.js') == (ROOT/'web/map-directory.js').read_bytes(), 'Packaged web/map-directory.js differs from source')
            require(assets.read('web/npc-contacts.css') == compile_css((ROOT/'web/npc-contacts.css').read_text(encoding='utf-8')).encode('utf-8'), 'Packaged NPC stylesheet differs from compiled source')
            for name in ('web/upper-institution-panel.js', 'web/upper-voisinage-panel.js', 'web/immortal-economy-panel.js', 'web/ui-panels.js', 'web/asura-panel.js', 'web/asura-meridians.js', 'web/meridian-atlas.js', 'web/meridian-atlas.css', 'web/assets/asura-anatomy.png', 'web/assets/immortal-anatomy.png', 'web/asura-panel.css', 'web/puppet-workshop.js', 'web/handbook-content.js', 'web/doctrine-panel.css', 'web/tutorial.js', 'web/tutorial-steps.js', 'web/tutorial-content.js', 'web/tutorial.css', 'web/index.html', 'web/combat-plan-panel.js', 'web/doctrine-panel.js', 'web/immortal-aperture-panel.js', 'web/theme-manager.js', 'web/theme-composition.js', 'content/crafting.json', 'content/formations.json', 'content/techniques.json', 'content/market.json', 'content/factions.json', 'content/doctrines.json', 'content/maps.json', 'content/items.json', 'content/world.json'):
                expected = (ROOT/name).read_bytes()
                if name.endswith('.css'):
                    expected = compile_css(expected.decode('utf-8')).encode('utf-8')
                if name == 'web/index.html':
                    expected = expected.decode('utf-8').replace('</head>', '<link rel="stylesheet" href="/android/mobile.css"></head>').replace('</body>', '<script src="/android/mobile.js"></script></body>').encode('utf-8')
                require(assets.read(name) == expected, name)
            require(assets.read('web/save-transfer.js') == (ROOT/'web/save-transfer.js').read_bytes(), 'Packaged save-transfer script differs from source')
            for theme in 'abcdef':
                require(f'web/themes/{theme}.css' in assets.namelist(), f'Missing theme {theme}')
            manifests = [n for n in assets.namelist() if n.startswith('dlc/') and n.endswith('/manifest.json')]
            require(len(manifests) == len(list((ROOT/'dlc').glob('*/manifest.json'))), 'Packaged DLC manifest count differs from source')
            dlcs = {n.split('/')[1]: json.loads(assets.read(n))['version'] for n in manifests}
            require(not any(n.startswith('data/') for n in assets.namelist()), 'Player data must not be included in the APK')
    target = ROOT/f'dist/浮生问道-v{VERSION}-Android12.apk'
    shutil.copy2(source, target)
    report = ROOT/f'dist/release-{ANDROID_VERSION}.json'
    manifest = {
        'base_version': VERSION, 'android_version': ANDROID_VERSION, 'version_code': VERSION_CODE,
        'application_id': 'com.fusheng.wendao', 'min_sdk': 31, 'target_sdk': 31,
        'included_abis': ['arm64-v8a', 'x86_64'], 'tested_android': 'Android 12 / API 31',
        'tested_abi': 'x86_64', 'physical_device_tested': False,
        'apk': target.name, 'apk_sha256': digest, 'apk_bytes': target.stat().st_size,
        'dlc_versions': dlcs, 'themes': list('abcdef'), 'save_schema': 5,
        'save_import_export': True, 'offline': True, 'release_debuggable': False,
        'validation': ['Six-theme portrait and landscape: independent Asura panels and puppet workshop, perspective contour illustrations, 27 live meridian nodes, DLC colors, native vein opening and power acquisition, back and persistence verified', 'Base upper-world voisinages without Asura DLC: native acquisition, nine-level growth, six-theme UI, persisted selection and energy verified', 'Independent voisinage and ordinary action budgets, paid ordinary execution and bulk merit purchases verified; six-theme Android bulk controls and persisted quantities verified', 'Fourteen-unit nonblocking elections, exclusive laws, salary, preview-only peers, expandable six-theme collections and unbounded Yaochi experience verified', 'Institution classification, legacy affiliation, six-theme map and institutional contacts verified', f'{passed.group(1)} Python regressions passed',
                       'Signed Android 12 six-theme doctrine fusion, trace study and true voisinage verified',
                       'Per-seed offensive tradition guarantee and migration; trial enemy escape forbidden; great-attainment layers two to four widened; perfected axes +25%; unchanged backlash and capped superego; multi-world calibration documented',
                       'Android 12 six-theme categorized sect contacts, saved interaction, stock lock across refresh and autonomous NPC cabinet verified',
                       'Android 12 six-theme Yaochi economy, gold tempering, timed single-use pass and persistence verified',
                       'Android 12 three upper worlds: six themes, DLC routing, finite reserves and native ordinary breakthrough verified',
                       'Android 12 six-theme voisinage stages, backlash and trial persistence verified',
                       'Android 12 six-theme live guided controls, deterministic practice/master/sect, persisted progress and native back verified',
                       'Android 12 six-theme manual battle plans, lower-world MP and return conversion, method-first teleport verified',
                       'Immortal meridians, manual realm gate, six themes, intrinsic resource bars and body level20 verified on signed APK',
                       'Signed Android 12 APK: six themes, native clipboard, >10MB save, reversed segments, confirmation and lossless restore',
                       'Windows to signed Android 12 to Windows: all JSON fields preserved',
                       'Six themes, real action, native back; signature and metadata verified',
                       'Android release lint: no issues found'],
    }
    report.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    archive = ROOT/f'dist/浮生问道-v{VERSION}-Android12.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for path, name in [(target,target.name), (report,report.name), (ROOT/'android/README.md','安卓说明.md'),
                           (ROOT/'docs/three-corpses-1512.md','三尸复测与合练.md'),
                           (ROOT/'docs/immortal-vein-balance.md','仙脉费用校准.md'),
                           (ROOT/'docs/upper-voisinages-1522.md','三界邻域说明.md'), (ROOT/'docs/experience-1520.md','修行与天庭体验更新.md'), (ROOT/'docs/institutions-1513.md','机构势力说明.md'), (ROOT/'CHANGELOG.md','CHANGELOG.md'), (ROOT/'android/app/src/main/mobile/NOTICE.txt','NOTICE.txt')]:
            package.write(path, name)
    with zipfile.ZipFile(archive) as package:
        require(package.testzip() is None, 'Release ZIP integrity check failed')
    print(json.dumps({'apk':str(target), 'bytes':target.stat().st_size, 'sha256':digest,
                      'archive':str(archive)}, ensure_ascii=False))

if __name__ == '__main__':
    main()

"""Publish the exact signed APK after release and Android 12 checks."""
import hashlib
import io
import json
import re
import shutil
import zipfile
from pathlib import Path
from android_css import compile_css

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.52.0'
ANDROID_VERSION = VERSION + '-android.20'

def main():
    def log(name):
        return (ROOT/'build'/name).read_text(encoding='utf-8', errors='replace')
    tests = log('release-1520-tests.log')
    passed = re.search(r'(\d+) passed in', tests)
    assert passed and 'failed' not in tests
    for name in ('android-experience-1520.log', 'android-institutions-1520.log', 'android-governance-1520.log', 'android-economy-1520.log', 'android-upper-1520.log', 'android-trials-1520.log', 'android-save-transfer-1520.log', 'android-initial-1520.log', 'android-immortal-1520.log', 'android-minor-1520.log', 'android-tutorial-1520.log'):
        assert 'status=passed' in log(name) and 'status=failed' not in log(name), name
    assert 'roundtrip passed' in log('save-crossplatform-1520.log')
    assert 'status=passed' in log('android-fusion-1520.log') and 'status=failed' not in log('android-fusion-1520.log')
    assert 'Verifies' in log('android-signature-1520.log')
    metadata = log('android-metadata-1520.log')
    assert "versionCode='20'" in metadata and f"versionName='{ANDROID_VERSION}'" in metadata
    assert "sdkVersion:'31'" in metadata and 'application-debuggable' not in metadata
    assert (ROOT/'android/app/build/reports/lint-results-release.txt').read_text(encoding='utf-8').strip() == 'No issues found.'
    source = ROOT/'android/app/build/outputs/apk/release/app-release.apk'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest in log('android-installed-sha256-1520.log').lower()
    with zipfile.ZipFile(source) as apk:
        assert apk.testzip() is None
        for abi in ('arm64-v8a', 'x86_64'):
            assert f'lib/{abi}/libpython3.13.so' in apk.namelist()
        with zipfile.ZipFile(io.BytesIO(apk.read('assets/game-assets.zip'))) as assets:
            assert assets.read('web/app.js') == (ROOT/'web/app.js').read_bytes()
            assert assets.read('web/npc-contacts.js') == (ROOT/'web/npc-contacts.js').read_bytes()
            assert assets.read('web/map-directory.js') == (ROOT/'web/map-directory.js').read_bytes()
            assert assets.read('web/npc-contacts.css') == compile_css((ROOT/'web/npc-contacts.css').read_text(encoding='utf-8')).encode('utf-8')
            for name in ('web/immortal-economy-panel.js', 'web/ui-panels.js', 'web/handbook-content.js', 'web/doctrine-panel.css', 'web/tutorial.js', 'web/tutorial-steps.js', 'web/tutorial-content.js', 'web/tutorial.css', 'web/index.html', 'web/combat-plan-panel.js', 'web/doctrine-panel.js', 'web/immortal-aperture-panel.js', 'web/theme-manager.js', 'web/theme-composition.js', 'content/crafting.json', 'content/formations.json', 'content/techniques.json', 'content/market.json', 'content/factions.json', 'content/doctrines.json', 'content/maps.json', 'content/items.json', 'content/world.json'):
                expected = (ROOT/name).read_bytes()
                if name.endswith('.css'):
                    expected = compile_css(expected.decode('utf-8')).encode('utf-8')
                if name == 'web/index.html':
                    expected = expected.decode('utf-8').replace('</head>', '<link rel="stylesheet" href="/android/mobile.css"></head>').replace('</body>', '<script src="/android/mobile.js"></script></body>').encode('utf-8')
                assert assets.read(name) == expected, name
            assert assets.read('web/save-transfer.js') == (ROOT/'web/save-transfer.js').read_bytes()
            for theme in 'abcdef':
                assert f'web/themes/{theme}.css' in assets.namelist()
            manifests = [n for n in assets.namelist() if n.startswith('dlc/') and n.endswith('/manifest.json')]
            assert len(manifests) == 7
            dlcs = {n.split('/')[1]: json.loads(assets.read(n))['version'] for n in manifests}
            assert not any(n.startswith('data/') for n in assets.namelist())
    target = ROOT/f'dist/浮生问道-v{VERSION}-Android12.apk'
    shutil.copy2(source, target)
    report = ROOT/f'dist/release-{ANDROID_VERSION}.json'
    manifest = {
        'base_version': VERSION, 'android_version': ANDROID_VERSION, 'version_code': 20,
        'application_id': 'com.fusheng.wendao', 'min_sdk': 31, 'target_sdk': 31,
        'included_abis': ['arm64-v8a', 'x86_64'], 'tested_android': 'Android 12 / API 31',
        'tested_abi': 'x86_64', 'physical_device_tested': False,
        'apk': target.name, 'apk_sha256': digest, 'apk_bytes': target.stat().st_size,
        'dlc_versions': dlcs, 'themes': list('abcdef'), 'save_schema': 5,
        'save_import_export': True, 'offline': True, 'release_debuggable': False,
        'validation': ['Fourteen-unit nonblocking elections, exclusive laws, salary, preview-only peers, expandable six-theme collections and unbounded Yaochi experience verified', 'Institution classification, legacy affiliation, six-theme map and institutional contacts verified', f'{passed.group(1)} Python regressions passed',
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
                           (ROOT/'docs/experience-1520.md','修行与天庭体验更新.md'), (ROOT/'docs/institutions-1513.md','机构势力说明.md'), (ROOT/'CHANGELOG.md','CHANGELOG.md'), (ROOT/'android/app/src/main/mobile/NOTICE.txt','NOTICE.txt')]:
            package.write(path, name)
    with zipfile.ZipFile(archive) as package:
        assert package.testzip() is None
    print(json.dumps({'apk':str(target), 'bytes':target.stat().st_size, 'sha256':digest,
                      'archive':str(archive)}, ensure_ascii=False))

if __name__ == '__main__':
    main()

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
VERSION = '1.48.1'
ANDROID_VERSION = VERSION + '-android.13'

def main():
    def log(name):
        return (ROOT/'build'/name).read_text(encoding='utf-8', errors='replace')
    tests = log('release-1481-tests.log')
    passed = re.search(r'(\d+) passed in', tests)
    assert passed and 'failed' not in tests
    for name in ('android-save-transfer-1481.log', 'android-initial-1481.log', 'android-immortal-1481.log', 'android-minor-1481.log', 'android-tutorial-1481.log'):
        assert 'status=passed' in log(name) and 'status=failed' not in log(name), name
    assert 'roundtrip passed' in log('save-crossplatform-1481.log')
    assert 'Verifies' in log('android-signature-1481.log')
    metadata = log('android-metadata-1481.log')
    assert "versionCode='13'" in metadata and f"versionName='{ANDROID_VERSION}'" in metadata
    assert "sdkVersion:'31'" in metadata and 'application-debuggable' not in metadata
    assert (ROOT/'android/app/build/reports/lint-results-release.txt').read_text(encoding='utf-8').strip() == 'No issues found.'
    source = ROOT/'android/app/build/outputs/apk/release/app-release.apk'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest in log('android-installed-sha256-1481.log').lower()
    with zipfile.ZipFile(source) as apk:
        assert apk.testzip() is None
        for abi in ('arm64-v8a', 'x86_64'):
            assert f'lib/{abi}/libpython3.13.so' in apk.namelist()
        with zipfile.ZipFile(io.BytesIO(apk.read('assets/game-assets.zip'))) as assets:
            assert assets.read('web/app.js') == (ROOT/'web/app.js').read_bytes()
            for name in ('web/tutorial.js', 'web/tutorial-steps.js', 'web/tutorial-content.js', 'web/tutorial.css', 'web/index.html', 'web/combat-plan-panel.js', 'web/doctrine-panel.js', 'web/immortal-aperture-panel.js', 'web/theme-manager.js', 'web/theme-composition.js', 'content/doctrines.json', 'content/maps.json', 'content/items.json', 'content/world.json'):
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
        'base_version': VERSION, 'android_version': ANDROID_VERSION, 'version_code': 13,
        'application_id': 'com.fusheng.wendao', 'min_sdk': 31, 'target_sdk': 31,
        'included_abis': ['arm64-v8a', 'x86_64'], 'tested_android': 'Android 12 / API 31',
        'tested_abi': 'x86_64', 'physical_device_tested': False,
        'apk': target.name, 'apk_sha256': digest, 'apk_bytes': target.stat().st_size,
        'dlc_versions': dlcs, 'themes': list('abcdef'), 'save_schema': 5,
        'save_import_export': True, 'offline': True, 'release_debuggable': False,
        'validation': [f'{passed.group(1)} Python regressions passed',
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
                           (ROOT/'CHANGELOG.md','CHANGELOG.md'), (ROOT/'android/app/src/main/mobile/NOTICE.txt','NOTICE.txt')]:
            package.write(path, name)
    with zipfile.ZipFile(archive) as package:
        assert package.testzip() is None
    print(json.dumps({'apk':str(target), 'bytes':target.stat().st_size, 'sha256':digest,
                      'archive':str(archive)}, ensure_ascii=False))

if __name__ == '__main__':
    main()

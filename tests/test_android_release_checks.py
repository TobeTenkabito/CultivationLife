"""Release gates must reject bad evidence even under python -O and -OO."""
import hashlib
import io
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts import package_android


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def release_inputs(tmp_path):
    build = tmp_path / 'build'
    build.mkdir()
    (tmp_path / 'dist').mkdir()
    rid = package_android.RELEASE_ID
    logs = {f'release-{rid}-tests.log': '1574 passed in 268.76s',
            f'heavens-ui-{rid}.log': '1980 dossier checks passed',
            f'heavens-knowledge-ui-{rid}.log': 'Knowledge UI passed:',
            f'heavens-workbench-ui-{rid}.log': 'real isolated execution and snapshot restore passed',
            f'save-crossplatform-{rid}.log': 'roundtrip passed',
            f'android-signature-{rid}.log': 'Verifies',
            f'android-metadata-{rid}.log': (
                f"versionCode='{package_android.VERSION_CODE}' "
                f"versionName='{package_android.ANDROID_VERSION}' sdkVersion:'31'"),
            f'quick-start-ui-{rid}.log': 'Quick-start regression passed',
            f'start-layout-ui-{rid}.log': 'Start layout passed'}
    phases = ('heavens-portrait', 'heavens-landscape', 'experience', 'institutions', 'governance', 'economy', 'upper', 'trials',
              'save-transfer', 'initial', 'immortal', 'minor', 'tutorial', 'bulk',
              'upper-voisinage', 'fusion', 'asura-portrait', 'asura-landscape',
              'debug-console-portrait', 'debug-console-landscape',
              'start-layout-portrait', 'start-layout-landscape', 'spatial-talisman-portrait', 'spatial-talisman-landscape')
    logs.update({f'android-{phase}-{rid}.log': 'status=passed' for phase in phases})
    logs.update({f'android-{phase}-{orientation}-{rid}.log': 'status=passed'
                 for phase in ('custom-start', 'war-logistics', 'economy-governance', 'economy-enterprises', 'economy-expansion')
                 for orientation in ('portrait', 'landscape')})
    for name, content in logs.items():
        (build / name).write_text(content, encoding='utf-8')
    lint = tmp_path / 'android/app/build/reports/lint-results-release.txt'
    lint.parent.mkdir(parents=True)
    lint.write_text('No issues found.', encoding='utf-8')
    apk = tmp_path / 'android/app/build/outputs/apk/release/app-release.apk'
    apk.parent.mkdir(parents=True)
    assets = io.BytesIO()
    with zipfile.ZipFile(assets, 'w') as archive:
        archive.writestr('web/app.js', b'outdated web content')
    with zipfile.ZipFile(apk, 'w') as archive:
        for abi in ('arm64-v8a', 'x86_64'):
            archive.writestr(f'lib/{abi}/libpython3.13.so', b'test library')
        archive.writestr('assets/game-assets.zip', assets.getvalue())
    (build / f'android-installed-sha256-{rid}.log').write_text(
        hashlib.sha256(apk.read_bytes()).hexdigest(), encoding='utf-8')
    (tmp_path / 'web').mkdir()
    (tmp_path / 'web/app.js').write_text('current web content', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('optimization', ['', '-O', '-OO'])
@pytest.mark.parametrize('failure,expected', [
    ('suite', 'Full regression suite must pass'),
    ('collection', 'Full regression suite must pass'),
    ('phase', 'android-experience-'),
    ('heavens', 'Heavens portrait must pass'),
    ('heavens-browser', 'Eleven-world UI acceptance must pass'),
    ('heavens-workbench', 'Heavens workbench UI must pass'),
    ('suite-uppercase', 'Full regression suite must pass'),
    ('debug-console', 'Android Debug console portrait checks must pass'),
    ('start-layout', 'Android start layout portrait checks must pass'),
    ('start-browser', 'Start layout UI checks must pass'),
    ('spatial-talisman', 'Android spatial talisman portrait checks must pass'),
    ('signature', 'Android APK signature must verify'),
    ('hash', 'APK hash must match'),
    ('asset', 'Packaged web/app.js differs from source'),
])
def test_bad_release_inputs_cannot_publish(release_inputs, optimization, failure, expected):
    root = release_inputs
    rid = package_android.RELEASE_ID
    corruptions = {
        'heavens-workbench': (f'heavens-workbench-ui-{rid}.log', 'Traceback: workbench failed'),
        'heavens': (f'android-heavens-portrait-{rid}.log', 'status=failed'),
        'heavens-browser': (f'heavens-ui-{rid}.log', '1980 dossier checks\nTraceback'),
        'suite-uppercase': (f'release-{rid}-tests.log', '1574 passed in 268.76s\nFAILED: batch errors'),
        'suite': (f'release-{rid}-tests.log', '1 failed, 1574 passed in 268.76s'),
        'collection': (f'release-{rid}-tests.log', '1574 passed in 268.76s\nERROR collecting tests'),
        'phase': (f'android-experience-{rid}.log', 'status=passed\nstatus=failed'),
        'debug-console': (f'android-debug-console-portrait-{rid}.log', 'status=failed'),
        'start-layout': (f'android-start-layout-portrait-{rid}.log', 'status=failed'),
        'start-browser': (f'start-layout-ui-{rid}.log', 'Traceback: failed'),
        'spatial-talisman': (f'android-spatial-talisman-portrait-{rid}.log', 'status=failed'),
        'signature': (f'android-signature-{rid}.log', 'DOES NOT VERIFY'),
        'hash': (f'android-installed-sha256-{rid}.log', 'wrong binary'),
    }
    if failure in corruptions:
        name, content = corruptions[failure]
        (root / 'build' / name).write_text(content, encoding='utf-8')
    script = (
        'import sys; from pathlib import Path; '
        'from scripts import package_android; '
        'package_android.ROOT = Path(sys.argv[1]); package_android.main()'
    )
    result = subprocess.run(
        [sys.executable, *([optimization] if optimization else []), '-c', script, str(root)],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=20,
    )
    assert result.returncode != 0
    assert f'RuntimeError: {expected}' in result.stderr
    assert not list((root / 'dist').iterdir())

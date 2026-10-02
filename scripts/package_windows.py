"""Package v1.53 Windows only after tests, six-theme UI and isolated EXE checks."""
import hashlib
import json
import re
import runpy
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = runpy.run_path(str(ROOT/'cultivation_life/version.py'))['BASE_GAME_VERSION']
RELEASE_ID = VERSION.replace('.', '')


def main():
    def log(name):
        return (ROOT/'build'/name).read_text(encoding='utf-8', errors='replace')
    test_log = log(f'release-{RELEASE_ID}-tests.log')
    passed = re.search(r'(\d+) passed in', test_log)
    assert passed and 'failed' not in test_log and 'ERROR' not in test_log, 'Full regression suite must pass'
    exe_log = log(f'exe-{RELEASE_ID}-verification.log')
    assert exe_log.count('EXE verified:') == 2 and 'Traceback' not in exe_log
    for check in ('asura-court', 'asura', 'handbook', 'quick-start', 'puppet'):
        result = log(f'{check}-ui-{RELEASE_ID}.log')
        assert 'passed' in result and 'Traceback' not in result, check
    exe = ROOT/'dist/launcher.exe'
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    manifest = {
        'base_version': VERSION,
        'platform': 'Windows',
        'exe_sha256': digest,
        'dlc_versions': {p.parent.name: json.loads(p.read_text(encoding='utf-8-sig'))['version']
                         for p in sorted((ROOT/'dlc').glob('*/manifest.json'))},
        'themes': list('abcdef'),
        'save_schema': 5,
        'validation': [
            f'{passed.group(1)} automated regression tests passed',
            'Six independent Asura entrances and base puppet workshop; original three-head six-arm SVG with 27 live meridian nodes; DLC entrance colors and six-theme portrait/landscape layout verified',
            'Puppet component tiers across eleven worlds, independent cultivation/body/sense, crafting and eightfold shape matching verified',
            'Silent ambient events retain manual interactions and periodic lightning trials; batch owned training and six-theme controls verified',
            'Base-game NPC royal seats, adjacent nonlethal blood duels, strength assessments, challenge grace and cooldowns, old-save migration verified',
            'Royal policies, appointments, wages, works and decrees use real treasury and elapsed-time settlement',
            'Court browser actions and persistence verified in six themes at desktop, portrait and landscape widths; no JavaScript errors',
            'Asura DLC soul purification, random semantic power and six-theme mobile UI verified',
            'Handbook DLC combinations, six themes, search and filters verified without save mutation',
            'Ten quick starts, real advancement and reload verified, including three native upper worlds and mandatory monster genus',
            'Exact packaged executable verified in isolated directories with and without all optional DLC, including base court coronation and NPC appointment',
        ],
        'android_release': 'Not included in this Windows release',
    }
    named = ROOT/f'dist/浮生问道-v{VERSION}.exe'
    shutil.copy2(exe, named)
    try:
        shutil.copy2(exe, ROOT/'launcher.exe')
        manifest['root_launcher_updated'] = True
    except PermissionError:
        # An existing game may still be running. Publish the new package
        # without terminating the user's process or risking their live save.
        manifest['root_launcher_updated'] = False
    manifest_path = ROOT/f'dist/release-{VERSION}.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    archive = ROOT/f'dist/浮生问道-v{VERSION}-Windows.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        package.write(exe, 'launcher.exe')
        package.write(manifest_path, manifest_path.name)
        for file in ('README.md', 'CHANGELOG.md'):
            package.write(ROOT/file, file)
        for path in sorted((ROOT/'docs').glob('*.md')):
            package.write(path, path.relative_to(ROOT).as_posix())
        package.writestr('game_config.txt', 'Debug=False\n')
        for directory in ('dlc', 'mods'):
            for path in sorted((ROOT/directory).rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts and path.suffix not in {'.pyc', '.pyo'}:
                    package.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(archive) as package:
        assert package.testzip() is None
        assert hashlib.sha256(package.read('launcher.exe')).hexdigest() == digest
        assert package.read('game_config.txt') == b'Debug=False\n'
        assert not any('data/saves' in name or 'ui_preferences.json' in name for name in package.namelist())
        assert 'dlc/asura-manifestation/manifest.json' in package.namelist()
    assert hashlib.sha256(named.read_bytes()).hexdigest() == digest
    if manifest['root_launcher_updated']:
        assert hashlib.sha256((ROOT/'launcher.exe').read_bytes()).hexdigest() == digest
    print(json.dumps(dict(version=VERSION, tests=int(passed.group(1)), exe_sha256=digest,
                          archive=str(archive), bytes=archive.stat().st_size), ensure_ascii=False))


if __name__ == '__main__':
    main()

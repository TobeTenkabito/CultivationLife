"""Package Windows only after regression, UI and artifact-bound EXE checks."""
import hashlib
import json
import re
import runpy
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.release_evidence import require, validate_evidence
from cultivation_life.save_schema import SAVE_SCHEMA_VERSION
VERSION = runpy.run_path(str(ROOT/'cultivation_life/version.py'))['BASE_GAME_VERSION']
RELEASE_ID = VERSION.replace('.', '')
AGENT_FILES = ('scripts/debug_agent.py', 'cultivation_life/__init__.py', 'cultivation_life/version.py',
               'cultivation_life/debug/__init__.py', 'cultivation_life/debug/agent.py',
               'cultivation_life/debug/client.py')


def main():
    def log(name):
        return (ROOT/'build'/name).read_text(encoding='utf-8', errors='replace')
    test_log = log(f'release-{RELEASE_ID}-tests.log')
    passed = re.search(r'(\d+) passed in', test_log)
    require(bool(passed) and 'failed' not in test_log and 'ERROR' not in test_log, 'Full regression suite must pass')
    exe_log = log(f'exe-{RELEASE_ID}-verification.log')
    require(exe_log.count('EXE verified:') == 2 and 'Traceback' not in exe_log, 'Both EXE checks must pass')
    for check in ('asura-court', 'asura', 'handbook', 'quick-start', 'puppet',
                  'start-layout', 'tutorial', 'spatial', 'debug-console'):
        result = log(f'{check}-ui-{RELEASE_ID}.log')
        require('passed' in result and 'Traceback' not in result, f'UI check must pass: {check}')
    evidence_file = ROOT / f'build/exe-{RELEASE_ID}-verification.json'
    require(evidence_file.is_file(), 'Missing verification receipt; run verify_release_exe.py')
    evidence = json.loads(evidence_file.read_text(encoding='utf-8'))
    validate_evidence(ROOT, VERSION, evidence)
    exe = ROOT/'dist/launcher.exe'
    executable = exe.read_bytes()
    digest = hashlib.sha256(executable).hexdigest()
    require(digest == evidence['exe_sha256'], 'Executable changed during packaging')
    manifest = {
        'base_version': VERSION,
        'platform': 'Windows',
        'exe_sha256': digest,
        'inputs_sha256': evidence['inputs_sha256'],
        'dlc_versions': {p.parent.name: json.loads(p.read_text(encoding='utf-8-sig'))['version']
                         for p in sorted((ROOT/'dlc').glob('*/manifest.json'))},
        'themes': list('abcdef'),
        'save_schema': SAVE_SCHEMA_VERSION,
        'validation': [
            f'{passed.group(1)} automated regression tests passed',
            'Six-theme start layout, live tutorial, quick starts, spatial/talisman/royal gameplay, debug console, Asura, handbook and puppet UI checks passed',
            'Exact executable hash verified in isolated directories with and without optional DLC',
            'Release inputs match the fingerprint recorded by EXE verification',
        ],
        'android_release': 'Not included in this Windows release',
    }
    named = ROOT/f'dist/浮生问道-v{VERSION}.exe'
    named.write_bytes(executable)
    try:
        (ROOT/'launcher.exe').write_bytes(executable)
        manifest['root_launcher_updated'] = True
    except PermissionError:
        # An existing game may still be running. Publish the new package
        # without terminating the user's process or risking their live save.
        manifest['root_launcher_updated'] = False
    manifest_path = ROOT/f'dist/release-{VERSION}.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    archive = ROOT/f'dist/浮生问道-v{VERSION}-Windows.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        package.writestr('launcher.exe', executable)
        package.write(manifest_path, manifest_path.name)
        for file in ('README.md', 'CHANGELOG.md'):
            package.write(ROOT/file, file)
        for file in AGENT_FILES:
            package.write(ROOT/file, file)
        for path in sorted((ROOT/'docs').glob('*.md')):
            package.write(path, path.relative_to(ROOT).as_posix())
        package.writestr('game_config.txt', 'Debug=False\n')
        for directory in ('dlc', 'mods'):
            for path in sorted((ROOT/directory).rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts and path.suffix not in {'.pyc', '.pyo'}:
                    package.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(archive) as package:
        require(package.testzip() is None, 'Archive integrity check failed')
        require(hashlib.sha256(package.read('launcher.exe')).hexdigest() == digest, 'Packaged EXE hash mismatch')
        require(package.read('game_config.txt') == b'Debug=False\n', 'Release must disable debug mode')
        for file in AGENT_FILES:
            require(package.read(file) == (ROOT/file).read_bytes(), f'Agent client differs from source: {file}')
        require(not any('data/saves' in name or 'ui_preferences.json' in name for name in package.namelist()),
                'Player data must not be packaged')
        require('dlc/asura-manifestation/manifest.json' in package.namelist(), 'Missing Asura DLC')
    require(hashlib.sha256(named.read_bytes()).hexdigest() == digest, 'Named EXE hash mismatch')
    if manifest['root_launcher_updated']:
        require(hashlib.sha256((ROOT/'launcher.exe').read_bytes()).hexdigest() == digest, 'Root EXE hash mismatch')
    validate_evidence(ROOT, VERSION, evidence)
    print(json.dumps(dict(version=VERSION, tests=int(passed.group(1)), exe_sha256=digest,
                          archive=str(archive), bytes=archive.stat().st_size), ensure_ascii=False))


if __name__ == '__main__':
    main()

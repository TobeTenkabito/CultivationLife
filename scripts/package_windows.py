import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
version = '1.39.3'
test_log = (ROOT / 'build/release-1393-tests.log').read_text(encoding='utf-8', errors='replace')
passed = re.search(r'(\d+) passed in', test_log)
assert passed and 'failed' not in test_log, 'Wait for successful full regression suite'
exe_log = (ROOT / 'build/exe-1393-verification.log').read_text(encoding='utf-8', errors='replace')
assert exe_log.count('EXE verified:') == 2 and 'Traceback' not in exe_log
for file in ['browser-character-1393.log']:
    log = (ROOT / 'build' / file).read_text(encoding='utf-8', errors='replace')
    assert 'passed' in log and 'Traceback' not in log, file
exe = ROOT / 'dist/launcher.exe'
digest = hashlib.sha256(exe.read_bytes()).hexdigest()
manifest = {
    'base_version':version,
    'exe_sha256':digest,
    'dlc_versions':{path.parent.name:json.loads(path.read_text(encoding='utf-8-sig'))['version']
                    for path in sorted((ROOT/'dlc').glob('*/manifest.json'))},
    'validation':[f'{passed.group(1)} automated regressions passed',
                  'Six themes, four browser widths and five populated character lists: geometry and game-state isolation passed',
                  'Packaged EXE with and without DLC: theme assets, appearance API persistence, startup, commission previews and Debug gating passed'],
    'save_schema':5,
}
manifest_path = ROOT / f'dist/release-{version}.json'
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
named = ROOT / f'dist/浮生问道-v{version}.exe'
shutil.copy2(exe, named)
shutil.copy2(exe, ROOT/'launcher.exe')
archive = ROOT / f'dist/浮生问道-v{version}-Windows.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as package:
    for path, name in [(exe,'launcher.exe'),(manifest_path,manifest_path.name),
                       (ROOT/'README.md','README.md'),(ROOT/'CHANGELOG.md','CHANGELOG.md'),(ROOT/'android/README.md','android/README.md')]:
        package.write(path, name)
    package.writestr('game_config.txt', 'Debug=False\n')
    for directory in ('dlc','mods'):
        for path in sorted((ROOT/directory).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in {'.pyc','.pyo'}:
                package.write(path, path.relative_to(ROOT).as_posix())
with zipfile.ZipFile(archive) as package:
    assert package.testzip() is None
    assert hashlib.sha256(package.read('launcher.exe')).hexdigest() == digest
    assert package.read('game_config.txt') == b'Debug=False\n'
    assert not any('data/saves' in name or 'ui_preferences.json' in name for name in package.namelist())
assert hashlib.sha256((ROOT/'launcher.exe').read_bytes()).hexdigest() == digest
assert hashlib.sha256(named.read_bytes()).hexdigest() == digest
print(json.dumps({'version':version,'tests':int(passed.group(1)), 'exe_sha256':digest,
                  'archive':str(archive), 'bytes':archive.stat().st_size}, ensure_ascii=False))

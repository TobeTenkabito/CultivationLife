"""Bind a signed APK to the complete inputs used by its Gradle build."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

from scripts.release_evidence import require


ASSET = 'assets/game-build.json'
DIRECTORIES = ('cultivation_life', 'content', 'web', 'dlc', 'android/app/src/main')
FILES = ('android/app/build.gradle', 'android/build.gradle', 'android/settings.gradle',
         'android/gradle.properties', 'scripts/prepare_android_assets.py',
         'scripts/android_css.py', 'scripts/android_provenance.py')


def input_hashes(root: Path) -> dict[str, str]:
    paths = [root / name for name in FILES]
    for directory in DIRECTORIES:
        paths.extend(p for p in (root / directory).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix not in {'.pyc', '.pyo'})
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths))}


def build_record(root: Path, staged_python: Path) -> dict:
    inputs = input_hashes(root)
    # This runs after Gradle Sync, before Python compilation and asset merging.
    staged = {p.relative_to(staged_python).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (staged_python / 'cultivation_life').rglob('*.py')}
    expected = {name: digest for name, digest in inputs.items()
                if name.startswith('cultivation_life/') and name.endswith('.py')}
    require(staged == expected, 'Staged Android Python sources differ from current source')
    return {'schema_version': 1, 'inputs': inputs}


def validate_apk_inputs(root: Path, apk: zipfile.ZipFile) -> dict:
    require(ASSET in apk.namelist(), 'Missing Android build provenance; rebuild the APK')
    record = json.loads(apk.read(ASSET))
    require(isinstance(record, dict) and record.get('schema_version') == 1,
            'Invalid Android build provenance')
    require(record.get('inputs') == input_hashes(root),
            'Android release inputs changed; rebuild and retest the APK')
    # Detect an incomplete/stale Python payload as well as a stale input receipt.
    with zipfile.ZipFile(io.BytesIO(apk.read('assets/chaquopy/app.imy'))) as python:
        names = set(python.namelist())
        expected = {name for name in record['inputs']
                    if name.startswith('cultivation_life/') and name.endswith('.py')}
        actual = {name[:-1] if name.endswith('.pyc') else name for name in names
                  if name.startswith('cultivation_life/') and name.endswith(('.py', '.pyc'))}
        require(actual == expected, 'Packaged Android Python module inventory differs from source')
    return record

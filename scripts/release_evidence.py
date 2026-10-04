"""Bind executable verification to the binary and the inputs being released."""
import hashlib
from pathlib import Path


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs_digest(root: Path) -> str:
    paths = [root / 'launcher.py', root / 'build/launcher.spec', root / 'scripts/debug_agent.py']
    for directory in ('cultivation_life', 'content', 'web', 'dlc', 'mods'):
        paths.extend(path for path in (root / directory).rglob('*') if path.is_file()
                     and '__pycache__' not in path.parts and path.suffix not in {'.pyc', '.pyo'})
    digest = hashlib.sha256()
    for path in sorted(set(paths)):
        digest.update(path.relative_to(root).as_posix().encode('utf-8') + b'\0')
        digest.update(bytes.fromhex(file_digest(path)))
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def validate_evidence(root: Path, version: str, evidence: dict) -> None:
    require(evidence.get('schema_version') == 1 and evidence.get('base_version') == version,
            'Executable verification receipt has an incompatible version')
    require(evidence.get('exe_sha256') == file_digest(root / 'dist/launcher.exe'),
            'Executable changed after verification; rerun verify_release_exe.py')
    require(evidence.get('inputs_sha256') == inputs_digest(root),
            'Release inputs changed after verification; rerun tests and EXE verification')
    cases = evidence.get('cases', [])
    require(len(cases) == 2 and {case.get('with_dlc') for case in cases} == {False, True}
            and all(case.get('exe_sha256') == evidence['exe_sha256']
                    and case.get('base_version') == version for case in cases),
            'The same executable must pass verification with and without DLC')

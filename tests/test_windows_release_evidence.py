import json
import zipfile
import subprocess
import sys

import pytest

from scripts import package_windows, verify_release_exe
from scripts.release_evidence import file_digest, inputs_digest, validate_evidence
from cultivation_life.save_schema import SAVE_SCHEMA_VERSION


@pytest.fixture
def release(tmp_path):
    for directory in ('build', 'dist', 'web', 'dlc/asura-manifestation'):
        (tmp_path / directory).mkdir(parents=True)
    for name in ('launcher.py', 'build/launcher.spec', 'web/app.js', 'README.md', 'CHANGELOG.md'):
        (tmp_path / name).write_text('release fixture', encoding='utf-8')
    for name in package_windows.AGENT_FILES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((package_windows.ROOT / name).read_bytes())
    (tmp_path / 'dlc/asura-manifestation/manifest.json').write_text('{"version":"1.0.0"}')
    (tmp_path / 'dist/launcher.exe').write_bytes(b'verified executable fixture')
    version = package_windows.VERSION
    digest = file_digest(tmp_path / 'dist/launcher.exe')
    receipt = {'schema_version': 1, 'base_version': version, 'exe_sha256': digest,
               'inputs_sha256': inputs_digest(tmp_path),
               'cases': [{'with_dlc': enabled, 'exe_sha256': digest, 'base_version': version}
                         for enabled in (False, True)]}
    return tmp_path, receipt


def test_matching_verification_receipt_is_accepted(release):
    root, receipt = release
    validate_evidence(root, package_windows.VERSION, receipt)


@pytest.mark.parametrize('path', ['dist/launcher.exe', 'web/app.js', 'launcher.py', 'dlc/asura-manifestation/manifest.json'])
def test_changed_binary_or_inputs_invalidates_receipt(release, path):
    root, receipt = release
    (root / path).write_bytes(b'changed after verification')
    with pytest.raises(RuntimeError, match='changed'):
        validate_evidence(root, package_windows.VERSION, receipt)


def test_dlc_runs_must_verify_the_same_executable(release):
    root, receipt = release
    receipt['cases'][1]['exe_sha256'] = 'another binary'
    with pytest.raises(RuntimeError, match='same executable'):
        validate_evidence(root, package_windows.VERSION, receipt)


def write_success_logs(root):
    rid = package_windows.RELEASE_ID
    logs = {f'release-{rid}-tests.log': '1518 passed in 441.36s',
            f'exe-{rid}-verification.log': 'EXE verified: old binary\nEXE verified: old binary'}
    logs.update({f'{check}-ui-{rid}.log': 'passed'
                 for check in ('asura-court', 'asura', 'handbook', 'quick-start', 'puppet')})
    for name, text in logs.items():
        (root / 'build' / name).write_text(text)


def test_old_success_logs_cannot_authorize_packaging(release, monkeypatch):
    root, _receipt = release
    write_success_logs(root)
    monkeypatch.setattr(package_windows, 'ROOT', root)
    with pytest.raises(RuntimeError, match='receipt'):
        package_windows.main()
    assert not list((root / 'dist').glob('*.zip'))
    assert not (root / 'launcher.exe').exists()


def test_packaging_uses_the_verified_binary(release, monkeypatch):
    root, receipt = release
    write_success_logs(root)
    (root / f'build/exe-{package_windows.RELEASE_ID}-verification.json').write_text(json.dumps(receipt))
    monkeypatch.setattr(package_windows, 'ROOT', root)
    package_windows.main()
    archive, = (root / 'dist').glob('*.zip')
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.read('launcher.exe') == (root / 'dist/launcher.exe').read_bytes()
        manifest = json.loads(bundle.read(f'release-{package_windows.VERSION}.json'))
        assert manifest['exe_sha256'] == receipt['exe_sha256']
        assert manifest['inputs_sha256'] == receipt['inputs_sha256']
        assert manifest['save_schema'] == SAVE_SCHEMA_VERSION
        target = root / 'extracted'
        bundle.extractall(target)
    result = subprocess.run([sys.executable, str(target/'scripts/debug_agent.py'), '--help'],
                            cwd=target, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert not (target/'cultivation_life/engine').exists()


def test_verifier_writes_receipt_only_after_both_cases_pass(release, monkeypatch):
    root, receipt = release
    monkeypatch.setattr(verify_release_exe, 'ROOT', root)
    monkeypatch.setattr(verify_release_exe, 'verify', lambda enabled: receipt['cases'][int(enabled)])
    verify_release_exe.main()
    evidence_path = root / f'build/exe-{verify_release_exe.VERSION.replace(".", "")}-verification.json'
    validate_evidence(root, verify_release_exe.VERSION, json.loads(evidence_path.read_text()))

    def fail_second(enabled):
        if enabled:
            raise RuntimeError('DLC verification failed')
        return receipt['cases'][0]

    monkeypatch.setattr(verify_release_exe, 'verify', fail_second)
    with pytest.raises(RuntimeError, match='DLC verification failed'):
        verify_release_exe.main()
    assert not evidence_path.exists()

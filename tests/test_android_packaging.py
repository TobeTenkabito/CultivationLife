"""Migration contracts: packaged content parity, safe updates and CSS compatibility."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from android_css import compile_css


def test_android_css_preserves_local_color_cascade():
    css = ':root{--pine:#315c47;--gold:#aabbcc}.hp{--meter-color:var(--pine);background:color-mix(in srgb,var(--meter-color) 25%,transparent)}'
    result = compile_css(css)
    assert 'color-mix(' not in result
    assert '--pine-r:49' in result
    assert '--meter-color-r:var(--pine-r)' in result
    assert 'rgba(var(--meter-color-r)' in result
    for source in (ROOT / 'web').rglob('*.css'):
        assert 'color-mix(' not in compile_css(source.read_text(encoding='utf-8'))


def test_android_bundle_contains_complete_desktop_content(tmp_path):
    subprocess.run([sys.executable, str(ROOT/'scripts/prepare_android_assets.py'), str(tmp_path)], check=True)
    archive = tmp_path / 'game-assets.zip'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == (tmp_path/'game-assets.sha256').read_text()
    with zipfile.ZipFile(archive) as bundle:
        manifests = [n for n in bundle.namelist() if n.startswith('dlc/') and n.endswith('/manifest.json')]
        assert len(manifests) == 6
        for directory in ('content','dlc'):
            for path in (ROOT/directory).rglob('*.json'):
                assert bundle.read(path.relative_to(ROOT).as_posix()) == path.read_bytes()
        for theme in 'abcdef': assert f'web/themes/{theme}.css' in bundle.namelist()
        assert not any(name.startswith('data/') for name in bundle.namelist())
        assert b'/android/mobile.js' in bundle.read('web/index.html')
        assert len(bundle.read('web/android/fonts/WendaoSerif.woff2')) > 1000000


def test_android_runtime_uses_private_root_and_authenticated_api(tmp_path):
    assets = tmp_path/'assets'
    subprocess.run([sys.executable,str(ROOT/'scripts/prepare_android_assets.py'),str(assets)],check=True)
    # Run in a fresh process: content registry must be imported after root configuration.
    script = r'''
import json, sys, urllib.request, urllib.error
from pathlib import Path
sys.path.insert(0, sys.argv[1]);sys.path.insert(0, sys.argv[2])
import android_runtime
root, assets=Path(sys.argv[3]),Path(sys.argv[4])
session=android_runtime.start(root,assets/'game-assets.zip',(assets/'game-assets.sha256').read_text())
base,token=session.split('|')
try:
 urllib.request.urlopen(base+'/api/config')
 raise AssertionError('Missing authentication accepted')
except urllib.error.HTTPError as e: assert e.code==403
headers={'Cookie':'cultivation_session='+token}
config=json.load(urllib.request.urlopen(urllib.request.Request(base+'/api/config',headers=headers)))
assert config['debug'] is False
assert len(config['extensions'])==6
assert config['base_game']['version']=='1.41.2'
from cultivation_life import server
assert server.PERSISTENCE_ROOT==root/'game'
assert server.WEB_ROOT==root/'game/web'
assert android_runtime.start(root,'ignored','ignored')==session
try:
 urllib.request.urlopen(urllib.request.Request(base+'/api/config',headers={**headers,'Origin':'http://evil.invalid'}))
 raise AssertionError('Foreign origin accepted')
except urllib.error.HTTPError as e: assert e.code==403
android_runtime._httpd.shutdown()
'''
    subprocess.run([sys.executable,'-c',script,str(ROOT),str(ROOT/'android/app/src/main/python'),
                    str(tmp_path/'private'),str(assets)],check=True)

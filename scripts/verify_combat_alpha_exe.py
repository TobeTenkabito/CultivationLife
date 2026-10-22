"""Focused compiled alpha.2 acceptance; never reuse full-repository evidence."""
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life.engine import GameEngine
from cultivation_life.version import BASE_GAME_VERSION as VERSION
from scripts.browser_navigation import set_theme
from scripts.release_evidence import inputs_digest,file_digest,require
from browser_alpha2_dlc_fixes import verify


def run(enabled):
    out=ROOT/f'build/alpha2-exe-{enabled}';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='alpha2-exe-',dir=ROOT/'build',ignore_cleanup_errors=True) as directory:
        folder=Path(directory).resolve()
        require(folder.is_relative_to((ROOT/'build').resolve()),'Invalid isolated EXE path')
        shutil.copy2(ROOT/'dist/launcher.exe',folder/'launcher.exe')
        if enabled:
            shutil.copytree(ROOT/'dlc',folder/'dlc',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        process=subprocess.Popen([str(folder/'launcher.exe'),'--port',str(port),'--no-browser'],cwd=folder,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for _ in range(150):
                try:
                    with urllib.request.urlopen(base+'/api/config',timeout=1) as response:config=json.load(response)
                    break
                except OSError:time.sleep(.3)
            else:raise AssertionError('Compiled server failed to start')
            assert config['base_game']['version']==VERSION
            assert len(config['extensions'])==(len(list((ROOT/'dlc').glob('*/manifest.json'))) if enabled else 0)
            fixture=GameEngine(ROOT,folder/'data/saves')
            with sync_playwright() as pw:
                browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=960),reduced_motion='reduce')
                page.add_init_script('delete Array.prototype.at; delete Array.prototype.findLast;')
                errors=[];requests=[]
                page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
                page.goto(base);page.wait_for_function('!!configData && !!window.CombatReplay');page.evaluate('GameThemes.ready')
                for i,theme in enumerate('abdf'):
                    set_theme(page,theme)
                    made=page.evaluate("api('/api/games',{method:'POST',body:JSON.stringify({name:'Alpha2成品验收',spirit_root:'heavenly',path:'dao',seed:622,preset_id:'core'})})")
                    verify(page,fixture,made['id'],out,'true_body' if i%2 else 'replica',enabled)
                private=page.request.get(base+'/extension-assets/official.guixu-tide/visual/icons/treasure.guixu_canghai_equipment_01.png')
                assert private.status==(200 if enabled else 404)
                assert not errors,errors
                if not enabled:assert not any('/extension-assets/' in p for p in requests)
                browser.close()
            return dict(with_dlc=enabled,base_version=VERSION,exe_sha256=file_digest(folder/'launcher.exe'),combat_alpha_verified=True,dlc_fixes_verified=True)
        finally:
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
            process.wait(timeout=20)


def main():
    before=inputs_digest(ROOT)
    cases=[run(False),run(True)]
    require(before==inputs_digest(ROOT),'Source changed during EXE checks')
    result=dict(schema_version=1,base_version=VERSION,inputs_sha256=before,exe_sha256=file_digest(ROOT/'dist/launcher.exe'),cases=cases)
    (ROOT/f'build/exe-{VERSION.replace(".","")}-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Same compiled EXE: four themes, true/replica intelligence, Guixu use, combat CG and DLC-off fallback passed')


if __name__=='__main__':main()

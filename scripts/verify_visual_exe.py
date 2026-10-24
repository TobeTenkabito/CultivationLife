"""Actual compiled UI acceptance in disposable installations, with/without DLC."""
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
from cultivation_life.version import BASE_GAME_VERSION as VERSION
from cultivation_life.engine import GameEngine
from fixtures.visual_release import prepare_visual_release
from browser_visual_release import verify
from fixtures.visual_additions import prepare_visual_additions, prepare_domain_battle
from domain_replay_acceptance import verify as verify_domains
from visual_additions_acceptance import verify as verify_additions
from browser_pixel_ui import verify_details
from scripts.release_evidence import inputs_digest,file_digest,require


def run(with_dlc):
    output=ROOT/f'build/visual-exe-{with_dlc}';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='visual-exe-',dir=ROOT/'build',ignore_cleanup_errors=True) as temporary:
        folder=Path(temporary).resolve()
        assert folder.is_relative_to((ROOT/'build').resolve())
        shutil.copy2(ROOT/'dist/launcher.exe',folder/'launcher.exe')
        if with_dlc:shutil.copytree(ROOT/'dlc',folder/'dlc',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        process=subprocess.Popen([str(folder/'launcher.exe'),'--port',str(port),'--no-browser'],cwd=folder,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for _ in range(150):
                try:
                    with urllib.request.urlopen(base+'/api/config',timeout=1) as response:config=json.load(response)
                    break
                except OSError:time.sleep(.3)
            else:raise AssertionError('Compiled server did not start')
            assert config['base_game']['version']==VERSION
            assert len(config['extensions'])==(len(list((ROOT/'dlc').glob('*/manifest.json'))) if with_dlc else 0)
            assert all(row['status']=='loaded' for row in config['extensions'])
            with sync_playwright() as pw:
                browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=960),reduced_motion='reduce')
                errors=[];requests=[]
                page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
                page.goto(base);page.wait_for_function('typeof configData!=="undefined" && !!configData');page.evaluate('GameThemes.ready')
                made=page.evaluate("api('/api/games',{method:'POST',body:JSON.stringify({name:'成品像素验收',spirit_root:'heavenly',path:'dao',seed:322,preset_id:'core'})})")
                assert made['trial_site']['enabled']==with_dlc
                fixture=GameEngine(ROOT,folder/'data/saves');prepare_visual_release(fixture,made['id'])
                assert not any('/assets/pixel/' in p and '.png' in p for p in requests)
                verify(page,made['id'],output)
                page.set_viewport_size(dict(width=1440,height=960));page.goto(base);page.wait_for_function('typeof configData!=="undefined" && !!configData')
                added=page.evaluate("api('/api/games',{method:'POST',body:JSON.stringify({name:'新增外观验收',spirit_root:'heavenly',path:'demonic',gender:'female',seed:323,preset_id:'core'})})")
                prepare_visual_additions(fixture,added['id'])
                verify_additions(page,added['id'],output)
                page.locator('#ve-close').click()
                from unittest.mock import patch
                with patch('cultivation_life.runtime.persistence_root', return_value=folder):
                    prepare_domain_battle(fixture,added['id'],'mutual')
                verify_domains(page,added['id'],output)
                for path in ('dao','demonic'):
                    for gender in ('male','female'):
                        hero=page.evaluate("args=>api('/api/games',{method:'POST',body:JSON.stringify({name:'新版主角验收',spirit_root:'heavenly',seed:326,...args})})",dict(path=path,gender=gender,preset_id='demonic_core' if path=='demonic' else 'core'))
                        page.evaluate('async id=>loadGame(id)',hero['id'])
                        for width,height in [(1440,960),(390,844),(320,740)]:
                            verify_details(page,output,gender,width,height,path)
                monster_file='/extension-assets/official.monster-bloodlines/visual/flora/flora-nascent-world-shared-actions.png'
                assert page.request.get(base+monster_file).status==(200 if with_dlc else 404)
                if with_dlc:
                    from browser_monster_release import verify as verify_monsters
                    page.goto(base);page.wait_for_function('typeof configData!=="undefined" && !!configData')
                    monster=page.evaluate("api('/api/games',{method:'POST',body:JSON.stringify({name:'成品妖修验收',spirit_root:'supreme_water',path:'monster',monster_species_id:'flora',start_world:'monster_realm',seed:4190})})")
                    verify_monsters(page,fixture,monster['id'],output,all_forms=False)
                private='/extension-assets/official.guixu-tide/visual/icons/treasure.guixu_canghai_equipment_01.png'
                for package,kind in [('ghost-reincarnation','ghost'),('sage-way','confucian'),('buddhist-dharma','buddhist')]:
                    asset=f'/extension-assets/official.{package}/visual/characters/{kind}-hero-female-portrait.png'
                    assert page.request.get(base+asset).status==(200 if with_dlc else 404)
                if with_dlc:
                    from browser_path_characters import verify as verify_paths
                    page.goto(base);page.wait_for_function('typeof configData!=="undefined" && !!configData')
                    path_game=page.evaluate("api('/api/games',{method:'POST',body:JSON.stringify({name:'三道成品验收',spirit_root:'heavenly',path:'dao',seed:510,preset_id:'core'})})")
                    verify_paths(page,fixture,path_game['id'],output)
                image=page.request.get(base+private)
                assert image.status==(200 if with_dlc else 404)
                assert not errors,errors
                if not with_dlc:assert not any('/extension-assets/' in p for p in requests)
                browser.close()
            print(f'Compiled optional UI passed: DLC={with_dlc}',flush=True)
            return dict(with_dlc=with_dlc,base_version=VERSION,exe_sha256=file_digest(folder/'launcher.exe'),visual_ui_verified=True,dlc_visual_verified=True,visual_additions_verified=True,domain_replay_verified=True,protagonist_static_verified=True,monster_visuals_verified=True,path_characters_verified=True)
        finally:
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
            process.wait(timeout=20)
            time.sleep(.5)


def main():
    before=inputs_digest(ROOT)
    cases=[run(False),run(True)]
    require(before==inputs_digest(ROOT),'Source changed during EXE acceptance')
    evidence=dict(schema_version=1,base_version=VERSION,inputs_sha256=before,exe_sha256=file_digest(ROOT/'dist/launcher.exe'),cases=cases)
    (ROOT/f'build/exe-{VERSION.replace(".","")}-verification.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Compiled optional visual UI: actual original commands, four themes, desktop/mobile, with/without DLC passed')


if __name__=='__main__':main()

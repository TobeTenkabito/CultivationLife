"""Verify each exclusive monster DLC combination against the same built binary."""
import json,os,shutil,socket,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.release_evidence import file_digest,inputs_digest
from cultivation_life.version import BASE_GAME_VERSION

def run():
    before=inputs_digest(ROOT);digest=file_digest(ROOT/'dist/launcher.exe');cases=[]
    for enabled in [('monster-bloodlines',),('monster-civilizations',)]:
        with tempfile.TemporaryDirectory(prefix='civilizations-exe-',dir=ROOT/'build') as folder:
            folder=Path(folder).resolve();assert folder.is_relative_to((ROOT/'build').resolve())
            shutil.copy2(ROOT/'dist/launcher.exe',folder/'launcher.exe')
            for package in enabled:shutil.copytree(ROOT/'dlc'/package,folder/'dlc'/package)
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            process=subprocess.Popen([str(folder/'launcher.exe'),'--port',str(port),'--no-browser'],cwd=folder,creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                base=f'http://127.0.0.1:{port}'
                def request(route,data=None):
                    req=urllib.request.Request(base+route,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
                    with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
                for retry in range(120):
                    try:cfg=request('/api/config');break
                    except OSError:time.sleep(.2)
                else:raise AssertionError('EXE did not start')
                assert cfg['base_game']['version']==BASE_GAME_VERSION
                assert all(p['status']=='loaded' for p in cfg['extensions']) and len(cfg['extensions'])==1
                game=request('/api/games',dict(name='独立万灵验收',spirit_root='supreme_earth',path='dao',seed=2100,custom_start=dict(world='human',realm_index=4)))
                view=request(f'/api/games/{game["id"]}/civilizations-view',{})
                assert view['available']==('monster-civilizations' in enabled)
                if view['available']:
                    result=request(f'/api/games/{game["id"]}/civilizations-action',dict(action='observe',expected_revision=0))
                    assert result['monster_civilizations']['revision']==1
                    view=request(f'/api/games/{game["id"]}/civilizations-view',{})
                    assert sum(r['known'] for r in view['regions'])==1
                cases.append(dict(packages=enabled,status='passed',exe_sha256=digest))
            finally:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True);process.wait(timeout=15)
                time.sleep(1)
    assert before==inputs_digest(ROOT) and digest==file_digest(ROOT/'dist/launcher.exe')
    receipt=ROOT/f'build/civilizations-exe-{BASE_GAME_VERSION.replace(".","")}.json'
    receipt.write_text(json.dumps(dict(inputs_sha256=before,exe_sha256=digest,cases=cases),indent=2),encoding='utf-8')
    print('Exclusive monster DLC EXE matrix passed: I only, II only; original verification covers neither and both')

if __name__=='__main__':run()

"""Real packaged HTTP travel; only generated disposable saves are authored."""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def verify_regional_calendar(base, folder, with_dlc):
    def post(identity, endpoint, **payload):
        url='/api/games' if identity is None else f'/api/games/{identity}/{endpoint}'
        with urlopen(Request(base+url,data=json.dumps(payload).encode(),
                     headers={'Content-Type':'application/json'},method='POST'),timeout=90) as response:
            return json.load(response)
    made=post(None,'',name='地区成品验收',spirit_root='none',path='dao',seed=20261018)
    identity=made['id'];path=folder/'data/saves'/f'{identity}.json'
    raw=json.loads(path.read_bytes());p=raw['player'];start=p['age']
    p.update(realm_index=4,layer=1,lifespan=10000,next_tribulation_age=None)
    raw['pending_event']=None
    raw['settings'].update(silent_events=False,guixu_event_popup=True)
    if with_dlc:
        from cultivation_life.content_registry import GUIXU_TIDE_CONTENT
        dungeon=next(d for d in GUIXU_TIDE_CONTENT['dungeons'] if d['world']=='human')
        raw['guixu_state']['cycles'][dungeon['id']].update(phase='closed',next_announce_age=start+1,
            next_open_age=start+1+dungeon['announce_lead_years'])
    path.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf8')
    shown=post(identity,'map-travel',destination='lanjiang_steppe')
    first=json.loads(path.read_bytes())
    if with_dlc:
        assert first['pending_event']['id']=='EVT_GUIXU_ANNOUNCE' and first['map_journey']['completed']==1
        with urlopen(base+f'/api/games/{identity}',timeout=90) as response:
            shown=json.load(response)
        before=path.read_bytes()
        try:post(identity,'map-travel',destination='lanjiang_steppe')
        except HTTPError as error:assert error.code==400
        else:raise AssertionError('Pending event permitted travel')
        assert path.read_bytes()==before
    for _ in range(20):
        raw=json.loads(path.read_bytes())
        if raw['player']['location_id']=='lanjiang_steppe':break
        event=shown['pending_event']
        if event:
            choice=next(c['id'] for c in event['choices'] if c.get('enabled',True))
            shown=post(identity,'choice',choice_id=choice,event_id=event['id'])
        else:shown=post(identity,'map-travel',destination='lanjiang_steppe')
    raw=json.loads(path.read_bytes())
    assert raw['player']['location_id']=='lanjiang_steppe' and raw['map_journey'] is None
    travel=[h for h in raw['history'] if h['event_id']=='SYS_MAP_TRAVEL']
    assert raw['player']['age']-start==travel[-1]['state_diff']['total_years']
    assert raw['world_simulation']['regions']['human']['year']==raw['player']['age']
    assert raw['world_simulation']['regions']['celestial']['year']<raw['player']['age']
    assert 'organization:sect:tianjian' in raw['economy_v2']['organizations']
    assert raw['world_simulation']['regions']['spirit']['year'] < raw['player']['age']
    assert 'organization:sect:taixuan' not in raw['economy_v2']['organizations']
    print('Regional EXE scope passed: original annual finance, frozen upper region, real travel and retained time')


def main():
    import shutil, socket, subprocess, sys, tempfile, time
    from pathlib import Path
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
    from scripts.release_evidence import inputs_digest, file_digest
    from cultivation_life.version import BASE_GAME_VERSION
    before=inputs_digest(root);digest=file_digest(root/'dist/launcher.exe');cases=[]
    for with_dlc in (False,True):
        with tempfile.TemporaryDirectory(prefix='regional-exe-',dir=root/'build') as folder:
            folder=Path(folder).resolve();assert folder.is_relative_to((root/'build').resolve())
            shutil.copy2(root/'dist/launcher.exe',folder/'launcher.exe')
            if with_dlc:shutil.copytree(root/'dlc',folder/'dlc')
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            process=subprocess.Popen([str(folder/'launcher.exe'),'--port',str(port),'--no-browser'],cwd=folder,creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                base=f'http://127.0.0.1:{port}'
                for _ in range(120):
                    try:
                        with urlopen(base+'/api/config',timeout=1) as response:config=json.load(response)
                        break
                    except OSError:time.sleep(.2)
                else:raise AssertionError('EXE did not start')
                assert config['base_game']['version']==BASE_GAME_VERSION
                verify_regional_calendar(base,folder,with_dlc)
                cases.append(dict(with_dlc=with_dlc,status='passed'))
            finally:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                process.wait(timeout=15);time.sleep(.4)
    assert inputs_digest(root)==before and file_digest(root/'dist/launcher.exe')==digest
    (root/f'build/regional-exe-{BASE_GAME_VERSION.replace(".", "")}.json').write_text(json.dumps(dict(
        version=BASE_GAME_VERSION,inputs_sha256=before,exe_sha256=digest,cases=cases),indent=2),encoding='utf8')


if __name__=='__main__':main()

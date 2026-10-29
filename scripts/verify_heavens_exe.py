"""Actual compiled cross-world commands and original people, with/without DLC."""
import json
import runpy
import urllib.request
import urllib.error
from pathlib import Path


def verify_heavens(base,with_dlc,folder):
    from cultivation_life.engine import GameEngine
    root=Path(__file__).resolve().parents[1]
    fixture=runpy.run_path(str(root/'tests/fixtures/heavens_release.py'))
    engine=GameEngine(root,folder/'data/saves')
    def request(path,data=None):
        req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=240) as response:return json.load(response)
    for asset in ('heavens-outposts.js','heavens-panel.js','npc-contacts.js','historical-effects.js'):
        with urllib.request.urlopen(base+'/'+asset) as response:assert response.read()==(root/'web'/asset).read_bytes()
    for source,rank in [('spirit',8),('celestial',12)]:
        made=request('/api/games',dict(name='诸天成品验收',spirit_root='supreme_metal',path='dao',seed=7330,
                                      custom_start=dict(world=source,realm_index=rank,layer=1)))
        identity=made['id'];meta=fixture['prepare_heavens'](engine,identity);path='/api/games/'+identity
        view=request(path)
        def act(action,options=None):
            nonlocal view
            request(path+'/heavens-command',dict(command_seq=view['heavens']['next_command_seq'],
                expected_revision=view['heavens']['revision'],action=action,target_id=meta['id'],options=options or {}))
            view=request(path)
        def row():return next(r for r in view['heavens']['outposts'] if r['id']==meta['id'])
        assert len(view['heavens']['outposts'])==(4 if rank==8 else 3)
        assert row()['terms']==meta['terms'] and row()['conquest']['authorized'] is False
        act('outpost_military_authorize');act('outpost_depart')
        assert fixture['inspect_heavens'](engine,identity,meta)
        act('outpost_develop')
        for _ in range(3):act('outpost_invest')
        act('outpost_war_start',dict(person_id=meta['people'][1],rival_id=meta['enemy_id']))
        for _ in range(30):
            if row()['conquest']['war']['phase']=='engaged':break
            act('outpost_wait')
        else:raise AssertionError('Compiled original worker did not reach battlefield')
        assert not next(a for a in row()['conquest']['actions'] if a['action']=='outpost_war_fight')['enabled']
        g=engine.store.load(identity);war=g.wars[-1]
        assert g.world_npcs[meta['people'][1]].location_id==meta['site']
        assert war['logistics']['sides']['attacker']['mobilized']==meta['terms']['war_budget']
        act('outpost_war_stop')
        from cultivation_life.system.heavens import outpost_conquest as conquest,outpost_runtime as runtime
        for _ in range(30):
            g=engine.store.load(identity)
            if conquest.current(g,runtime.get(g,meta['id'])) is None:break
            act('outpost_wait')
        else:raise AssertionError('Compiled original worker did not return')
        act('outpost_return')
        assert fixture['inspect_heavens'](engine,identity,meta,returned=True)
        assert request(path)['player']['world']==source
        print(f'EXE heavens verified: DLC={with_dlc}, {source}, original staff, military, real crossing, development, scaled budget, local roundtrip and paid return',flush=True)

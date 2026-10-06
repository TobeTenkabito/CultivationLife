"""Carry the same live campaign through DLC removal and restoration."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from test_heavens_settlement import local, site, ready, military, occupation


def main():
    output = ROOT/'build/heavens-m3-profile-reload'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        workdir = Path(folder)
        bundle = military.__wrapped__(ready.__wrapped__(site.__wrapped__(local.__wrapped__(workdir/'source'))))
        game = occupation(bundle)
        game.player.realm_index = 4
        source = workdir/'original.json'
        source.write_text(json.dumps(game.to_dict(), ensure_ascii=False), encoding='utf-8')
        app = workdir/'base'
        shutil.copytree(ROOT/'content', app/'content')
        code = '''import json, sys
from pathlib import Path
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.content_registry import EXTENSION_REPORT
from cultivation_life.system.heavens import campaign
original = GameState.from_dict(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
engine = GameEngine(Path.cwd(), Path(sys.argv[3]))
engine.store.save(original)
engine._load(original.id)
loaded = engine.store.load(original.id)
assert campaign.get(loaded)['units'] == campaign.get(original)['units']
assert campaign.get(loaded)['settlement'] == campaign.get(original)['settlement']
deps = engine._dependencies.heavens
state = loaded.heavens_state
engine.heavens_command(loaded.id, state['command_seq']+1, state['revision'], 'campaign_wait', 'lanjiang_gate', {})
after = engine.store.load(original.id)
assert after.player.age == loaded.player.age+1
assert {u['person_id'] for u in campaign.get(after)['units']} == {u['person_id'] for u in campaign.get(original)['units']}
GameState.from_dict(after.to_dict())
Path(sys.argv[2]).write_text(json.dumps(after.to_dict(), ensure_ascii=False), encoding='utf-8')
active = [r['id'] for r in EXTENSION_REPORT if r['status']=='loaded']
assert len(active) == int(sys.argv[4]), active
print(json.dumps(dict(loaded=active, same_identities=True, real_annual_resume=True)), flush=True)
'''
        rows = []
        for name, root, expected in [('removed', app, 0), ('restored', ROOT, 8)]:
            destination = workdir/(name+'.json')
            env = {**os.environ, 'CULTIVATION_APP_ROOT':str(root), 'PYTHONIOENCODING':'utf-8'}
            result = subprocess.run([sys.executable, '-u', '-c', code, str(source), str(destination),
                                     str(workdir/(name+'-saves')), str(expected)], cwd=ROOT, env=env,
                                    capture_output=True, text=True, encoding='utf-8')
            (output/(name+'.log')).write_text(result.stdout+result.stderr, encoding='utf-8')
            rows.append(dict(profile=name, exit_code=result.returncode))
            if result.returncode:
                print(result.stderr); raise SystemExit(result.returncode)
            source = destination
        (output/'report.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print('Same campaign: all official DLCs -> base-only -> restored, real annual steps passed')


if __name__ == '__main__':
    main()

"""Whole remote calendar, save/reload, hashes and actual goods on production paths."""
import copy
import json
import os
import random
import subprocess
import sys

from test_regional_calendar import ROOT, regional
from regional_scenario import prepare, check, canonical
from cultivation_life.models import GameState
from cultivation_life.engine.world import regions


def test_full_campaign_freight_war_and_order_resume_without_double_payment(tmp_path):
    from cultivation_life.engine import GameEngine
    engine=GameEngine(ROOT,tmp_path/'saves')
    initial=prepare(engine)
    a,b=copy.deepcopy(initial),copy.deepcopy(initial)
    for game in (a,b):
        for year in range(12):
            game.player.age+=1
            engine._advance_world_year(game,random.Random(100+year),[],encounters=False)
            if year == 9:
                game.diplomacy_unit += 1
                engine._advance_wars_unit(game, random.Random(909))
            check(game)
            if game is b and year==5:
                raw=game.to_dict()
                restored=GameState.from_dict(raw)
                # Reload all persistent authorities in place for the next step.
                game.__dict__.clear();game.__dict__.update(restored.__dict__)
        before=canonical(game)
        regions.synchronize(engine,game,regions.important_worlds(game))
        assert canonical(game)==before
    assert canonical(a)==canonical(b)


def test_new_process_hash_order_and_midpoint_resume_match(regional,tmp_path):
    engine,game=regional
    regions.synchronize(engine,game,regions.worlds())
    source=tmp_path/'source.json'
    source.write_text(json.dumps(game.to_dict(),ensure_ascii=False),encoding='utf8')
    script='''
import json,sys
from pathlib import Path
sys.path[:0]=[sys.argv[1],str(Path(sys.argv[1])/'tests')]
from cultivation_life.engine import GameEngine
from cultivation_life.engine.world import regions
from cultivation_life.models import GameState
from regional_scenario import canonical
engine=GameEngine(Path(sys.argv[1]),Path(sys.argv[2])/'isolated')
g=GameState.from_dict(json.loads(Path(sys.argv[2]).read_text(encoding='utf8')))
for i in range(6):
 g.player.age+=1
 regions.synchronize(engine,g,regions.worlds())
 if i==2 and sys.argv[4]=='reload':g=GameState.from_dict(g.to_dict())
Path(sys.argv[3]).write_text(json.dumps(canonical(g),ensure_ascii=False,sort_keys=True),encoding='utf8')
'''
    # SaveStore needs a directory alongside, not nested inside the source file.
    script=script.replace("Path(sys.argv[2])/'isolated'", "Path(sys.argv[2]).parent/('isolated-'+sys.argv[4])")
    results=[]
    for hashseed,mode in [('123','continuous'),('789','reload')]:
        output=tmp_path/(mode+'.json')
        subprocess.run([sys.executable,'-c',script,str(ROOT),str(source),str(output),mode],
                       check=True,env=os.environ|{'PYTHONHASHSEED':hashseed},capture_output=True,timeout=180)
        results.append(json.loads(output.read_text(encoding='utf8')))
    assert results[0]==results[1]

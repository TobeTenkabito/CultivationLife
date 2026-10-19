"""Paired real-year actions: empty, one cave and a large building registry."""
import copy
import hashlib
import itertools
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.building_schema import address, address_key
from cultivation_life.building_rules import qi_multiplier
from cultivation_life.version import BASE_GAME_VERSION
from scripts.release_evidence import inputs_digest


def main():
    fingerprint=inputs_digest(ROOT)
    result=[]
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        game=engine._load(engine.create_game('建筑计时','heavenly','dao',317,preset_id='core')['id'])
        game.pending_event=None
        game.settings.update(silent_events=True,guixu_event_popup=False)
        game.player.next_tribulation_age=None
        original=copy.deepcopy(game.to_dict())
        places=engine.maps.worlds[game.player.world]['locations']
        economics=None
        for count in (0,1,128):
            samples=[]
            for repeat in range(4):
                game=GameState.from_dict(original)
                if count:
                    state=game.building_state
                    state.update(version=1,sequence=0,records={},cultivation={})
                    for i in range(count):
                        place=address(game) if i==0 else dict(world=game.player.world,instance_id=None,location_id=places[i%len(places)]['id'])
                        key=f'bench-{i}'
                        state['records'][key]=dict(id=key,name='山间洞府',type='artificiality',subtype='cave',
                            level=1,quality='professional',status='intact',owner=dict(kind='player',id=game.id),
                            users=[],public=False,invested=800,address=place)
                    state['cultivation'][address_key(address(game))]='bench-0'
                engine.store.save(game)
                sequence=itertools.count()
                def fresh_id():
                    return uuid.UUID(bytes=hashlib.blake2s(str(next(sequence)).encode(),digest_size=16).digest())
                with patch('uuid.uuid4',side_effect=fresh_id):
                    started=time.perf_counter();engine.advance(game.id,'rest',1)
                    elapsed=(time.perf_counter()-started)*1000
                final=engine.store.load(game.id)
                economic=copy.deepcopy(final.economy_v2)
                if economics is None:economics=economic
                assert economic==economics,'Building registry changed actual economic settlement'
                assert final.player.age>original['player']['age']
                if repeat:samples.append(elapsed)
            started=time.perf_counter()
            for _ in range(100000):qi_multiplier(final.player)
            lookup_us=(time.perf_counter()-started)*10
            result.append(dict(buildings=count,action_median_ms=round(statistics.median(samples),2),
                qi_lookup_us=round(lookup_us,2),economy_identical=True))
    output=ROOT/'build/building-performance.json'
    assert inputs_digest(ROOT)==fingerprint,'Sources changed during performance acceptance'
    output.write_text(json.dumps(dict(version=BASE_GAME_VERSION,source_sha256=fingerprint,scenario='same save, one real rest action, 1 warmup + 3 samples',
        note='End-to-end includes save validation and map rendering; not a before-feature benchmark.',rows=result),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':main()

"""Deterministic blueprint budget audit; does not invent a combat survival rate."""
import copy
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cultivation_life.models import Player
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.system.dungeons import generation
from cultivation_life.dungeon_schema import all_rewards,decode,empty


def main():
    cfg=copy.deepcopy(generation.config());rows=[]
    for world,ceiling in cfg['ceilings'].items():
        profiles=[(key,value) for key,value in cfg['profiles'].items() if key.startswith(world+':')]
        profiles.sort(key=lambda pair:(pair[1]['realm'],pair[1]['cap'],pair[0]))
        path={'demon':'demonic','true_demon':'demonic','asura':'demonic','hell':'ghost',
            'phantom_underworld':'monster','nether':'monster','reincarnation':'ghost','monster_realm':'monster'}.get(world,'dao')
        for quality in generation.QUALITIES:
            stats=Counter();grades=set();largest_relic=0;fused=0
            for scope,profile in (profiles[0],profiles[-1]):
                local_cfg=copy.deepcopy(cfg);local_cfg['profiles'][scope]['weights']=[int(q==quality) for q in generation.QUALITIES]
                location=scope.split(':',1)[1]
                player=Player(name='预算样本',spirit_root='heavenly',path=path,world=world,location_id=location,realm_index=ceiling,layer=9)
                with patch.object(generation,'config',lambda:local_cfg):
                    for seed in range(40):
                        game=SimpleNamespace(seed=seed,player=player,sects={},dungeon_state={})
                        site=generation.generate(game,dict(id=location,name=location),0,0)
                        state=empty();state['instances'][site['id']]=site;state['maps'][scope]=[site['id']]
                        if quality=='legendary':state['legends'][world]=[site['id']]
                        decode(state)
                        assert all(not r['materialized'] for r in site['roles'].values())
                        for reward in all_rewards(site):
                            stats[reward['kind']]+=1;grades.add(reward['realm'])
                            if reward['kind']=='artifact':largest_relic=max(largest_relic,reward['item']['combat_bonus'])
                            if reward['kind']=='pill':assert reward['item'].get('permanent_intrinsic_hp_bonus',0)==0
                        fused+=int(site['nodes'][-1]['reward']['fused'])
                        if quality=='legendary':assert {r['realm'] for r in all_rewards(site)}=={ceiling}
                        else:assert site['realm']<=profile['cap']
            rows.append(dict(world=world,quality=quality,blueprints=80,reward_grades=sorted(grades),
                reward_kinds=dict(stats),core_fused=fused,core_fused_rate=fused/80,
                max_relic_combat_bonus=largest_relic,simultaneous_relics=1,permanent_pill_growth=0))
    output=ROOT/'build/reviews/seeded-dungeons/balance.json';output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(dict(seed_range=[0,39],blueprints=sum(r['blueprints'] for r in rows),
        note='生成预算样本；不等同于到达核心或存活带出概率。两端地图各 40 种子，含未领取的报答预算。',rows=rows),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(blueprints=sum(r['blueprints'] for r in rows),worlds=len(cfg['ceilings']),output=str(output)),ensure_ascii=False))


if __name__=='__main__':main()

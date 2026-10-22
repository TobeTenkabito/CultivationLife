"""Actual bloodline panel selections against an isolated HTTP game server."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import MONSTER_EVOLUTIONS, REALMS
from cultivation_life.rules import opportunity_required, qi_level_threshold
from scripts.browser_navigation import navigation_locator, reveal_subpage

CASES=[('fox','FOX_MYSTIC','FOX_MOUNTAIN_KING','FOX_ILLUSION_LORD','FOX_MYSTIC_5','mountain'),
       ('turtle','TURTLE_STONE','TURTLE_IRON_MOUNTAIN','TURTLE_SHELL_SOVEREIGN','TURTLE_MOUNTAIN_5','mountain'),
       ('insect','INSECT_GOLD','INSECT_VIOLET_ARMOR','INSECT_HUNDRED_FORM','INSECT_ARMOR_5','mountain'),
       ('aquatic','AQUATIC_KOI','AQUATIC_GOLDEN_LEAPER','AQUATIC_SEA_SOVEREIGN','AQUATIC_KOI_5','thunder'),
       ('flora','FLORA_IRON_THORN','FLORA_BLAZE_THORN','FLORA_THORN_SOVEREIGN','FLORA_THORN_5','flame')]

def ancestry(key):
    parents=MONSTER_EVOLUTIONS[key]['parents']
    return (ancestry(parents[0]) if parents else [])+[key]

def prepare(engine,identity,key,adaptations):
    g=engine.store.load(identity);p=g.player
    p.monster_evolution_id=key;p.monster_evolution_history=ancestry(key)
    p.realm_index=MONSTER_EVOLUTIONS[key]['realm_index'];p.layer=REALMS[p.realm_index].layers
    p.awaiting_major_breakthrough=True;p.opportunity=opportunity_required(p)
    p.monster_adaptations=adaptations;p.qi_experience['monster']=qi_level_threshold(4)
    engine.store.save(g)

def main():
    output=ROOT/'build/monster-branches/browser';output.mkdir(parents=True,exist_ok=True)
    errors=[];completed=[]
    with tempfile.TemporaryDirectory() as directory:
        engine=GameEngine(ROOT,Path(directory)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(directory)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for width,height in [(1440,1000),(390,844)]:
                        page=browser.new_page(viewport=dict(width=width,height=height))
                        page.on('pageerror',lambda e:errors.append(str(e)))
                        page.goto(f'http://127.0.0.1:{http.server_port}')
                        page.wait_for_selector('#custom-start')
                        for species,parent,core,lord,deity,adapt in CASES:
                            identity=page.evaluate("""async s=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'五族分支验收',spirit_root:'supreme_water',path:'monster',seed:4160,start_world:'monster_realm',monster_species_id:s})});return g.id;}""",species)
                            prepare(engine,identity,parent,[])
                            page.evaluate('async id=>loadGame(id)',identity)
                            navigation_locator(page,'[data-panel-target=bloodline]').click()
                            card=page.locator('.bloodline-candidate').filter(has=page.get_by_text(MONSTER_EVOLUTIONS[core]['name'],exact=True))
                            reveal_subpage(page,card)
                            assert 'locked' in card.get_attribute('class')
                            assert card.locator('.missing').count()>0
                            before=engine.store.load(identity).to_dict()
                            refused=page.request.post(f'http://127.0.0.1:{http.server_port}/api/games/{identity}/monster-evolve',data={'evolution_id':core})
                            assert not refused.ok
                            assert engine.store.load(identity).to_dict()==before
                            prepare(engine,identity,parent,[adapt])
                            page.evaluate('async id=>loadGame(id)',identity)
                            reveal_subpage(page,card)
                            card.get_by_role('button',name='选择进化',exact=True).click()
                            page.wait_for_function('(id)=>!busy&&game.player.monster_evolution_id===id',arg=core)
                            assert engine.store.load(identity).player.realm_index==3
                            for current,target in [(core,lord),(lord,deity)]:
                                prepare(engine,identity,current,[adapt])
                                page.evaluate('async id=>loadGame(id)',identity)
                                selected=page.locator('.bloodline-candidate').filter(has=page.get_by_text(MONSTER_EVOLUTIONS[target]['name'],exact=True))
                                reveal_subpage(page,selected)
                                selected.get_by_role('button',name='选择进化',exact=True).click()
                                page.wait_for_function('(id)=>!busy&&game.player.monster_evolution_id===id',arg=target)
                            snapshot=engine.store.load(identity).player.monster_evolution_history
                            page.reload();page.wait_for_selector('#custom-start')
                            page.evaluate('async id=>loadGame(id)',identity)
                            navigation_locator(page,'[data-panel-target=bloodline]').click()
                            assert engine.store.load(identity).player.monster_evolution_history==snapshot
                            assert page.locator('#bloodline-card').evaluate('n=>n.scrollWidth<=n.clientWidth+1')
                            page.locator('#bloodline-card').screenshot(path=str(output/f'{species}-{width}.png'))
                            page.locator('#bloodline-toggle').click()
                            completed.append(dict(species=species,width=width,core=core,deity=deity))
                        page.close()
                    browser.close()
            finally:
                http.shutdown();http.server_close()
    assert not errors,errors
    (output/'validation.json').write_text(json.dumps(dict(status='passed',cases=completed,errors=errors),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Five origins: locked HTTP refusal, 30 real evolution clicks, reload, desktop/mobile passed')

if __name__=='__main__':main()

"""Actual Android process restarts reload all six DLC, offline saves survive."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from android_cdp import AndroidPage


def restart(page):
    page.evaluate('showStart();document.querySelector("#start-extension-manager").open=true')
    page.tap('#start-extension-manager .android-restart')
    page.wait('!document.querySelector("#game-confirm-backdrop").classList.contains("hidden")')
    page.tap('#game-confirm-accept')
    page.close()
    time.sleep(1)
    return AndroidPage(page.serial).connect()


def main(serial):
    state=json.loads((ROOT/'build/android-acceptance/state.json').read_text(encoding='utf-8'))
    page=AndroidPage(serial).connect()
    gid=state['id']
    def digest():
        return page.command('shell','run-as',page.package,'sha256sum',f'files/game/data/saves/{gid}.json').split()[0]
    original=digest()
    page.evaluate('''(async()=>{for(const e of configData.extensions)await api('/api/extensions/'+e.id,{method:'POST',body:JSON.stringify({enabled:false})})})()''')
    page=restart(page)
    config=page.evaluate('configData')
    assert len(config['extensions'])==6
    assert all(e['status']=='disabled' for e in config['extensions']),config['extensions']
    assert not config['monster_species']
    assert digest()==original
    print('All six DLC disabled through a real native app restart; saves unchanged',flush=True)
    page.evaluate('''(async()=>{for(const e of configData.extensions)await api('/api/extensions/'+e.id,{method:'POST',body:JSON.stringify({enabled:true})})})()''')
    page=restart(page)
    config=page.evaluate('configData')
    assert all(e['status']=='loaded' for e in config['extensions']),config['extensions']
    assert config['monster_species']
    assert digest()==original
    page.evaluate(f'loadGame({json.dumps(gid)})')
    systems=page.evaluate('({guixu:game.guixu_tide.available,tianji:game.tianji_artifacts.available,intrigue:game.intrigue_system.enabled,sage:game.sage_system.available})')
    assert systems['guixu'] and systems['tianji'] and systems['intrigue'],systems
    # Confucian and monster starts exercise DLC-specific state on the Android interpreter.
    sage=page.evaluate('''(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'杏坛行者',path:'confucian',spirit_root:'supreme_wood',preset_id:'confucian_core',seed:2207})});const s=await api('/api/games/'+g.id+'/sage-doctrine',{method:'POST',body:JSON.stringify({action:'join',doctrine_id:'sage-human-righteous'})});return {available:s.sage_system.available,doctrines:s.sage_system.doctrines.length}})()''')
    assert sage['available'] and sage['doctrines']>=2,sage
    monster=page.evaluate('''(async()=>{const species=Object.keys(configData.monster_species)[0];const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'山海异客',path:'monster',spirit_root:'supreme_metal',monster_species_id:species,seed:17})});return {path:g.player.path,bloodline:g.monster_bloodline}})()''')
    assert monster['path']=='monster' and monster['bloodline'],monster
    ghost=page.evaluate('''(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'黄泉来客',path:'ghost',spirit_root:'supreme_metal',start_world:'hell',seed:29})});return {path:g.player.path,available:g.ghost_system.available}})()''')
    assert ghost['path']=='ghost' and ghost['available'],ghost
    print('Six DLC re-enabled; Guixu, Tianji, Intrigue, Sage doctrine, monster bloodline and ghost APIs passed',flush=True)
    page.command('shell','cmd','connectivity','airplane-mode','enable')
    page.command('shell','svc','wifi','disable')
    try:
        page.close()
        page.command('shell','am','force-stop',page.package)
        page.command('shell','am','start','-n',page.package+'/com.fusheng.wendao.MainActivity')
        page=AndroidPage(serial).connect()
        page.evaluate(f'loadGame({json.dumps(gid)})')
        assert page.evaluate('game.player.name')=='安卓问道'
        assert page.evaluate('document.documentElement.dataset.theme')=='f'
        assert page.evaluate('document.fonts.check("16px \'Wendao Serif\'")')
        page.screenshot(ROOT/'build/android-acceptance/offline.png')
        assert digest()==original
        assert not page.errors,page.errors
    finally:
        page.command('shell','cmd','connectivity','airplane-mode','disable')
        page.command('shell','svc','wifi','enable')
        page.close()
    print('Android 12 offline cold start, bundled font, theme and save persistence passed',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--serial',required=True)
    main(parser.parse_args().serial)

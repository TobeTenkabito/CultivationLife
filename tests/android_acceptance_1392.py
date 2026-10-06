"""Run against our isolated Android 12 AVD, never a connected user device."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from android_cdp import AndroidPage


def main(serial):
    output=ROOT/'build/android-acceptance'
    output.mkdir(exist_ok=True)
    page=AndroidPage(serial).connect()
    assert page.command('shell','getprop','ro.build.version.sdk')=='31'
    config=page.evaluate('configData')
    assert config['base_game']['version']=='1.39.2'
    assert len(config['extensions'])==6,config['extensions']
    print('Android 12 startup, base version and six DLC loaded',flush=True)
    for theme in 'abdf':
        page.tap(f'[data-theme-picker=start] [data-theme-choice={theme}]')
        page.wait(f'document.documentElement.dataset.theme === "{theme}"')
        page.evaluate('GameThemes.saved')
        assert page.evaluate('document.documentElement.dataset.theme')==theme
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),theme
        page.evaluate('scrollTo(0,0)')
        page.screenshot(output/f'{theme}-start.png')
    gid=page.evaluate('''(async()=>{const created=await api('/api/games',{method:'POST',body:JSON.stringify({name:'安卓问道',spirit_root:'supreme_metal',path:'dao',seed:1392,preset_id:'core'})});render(created);return created.id})()''')
    for theme in 'abdf':
        # Independent lives keep random deaths and forced story choices from
        # determining which later presentation can be exercised.
        gid=page.evaluate(f'''(async()=>{{const created=await api('/api/games',{{method:'POST',body:JSON.stringify({{name:'安卓问道',spirit_root:'supreme_metal',path:'dao',seed:{1500+ord(theme)}}})}});render(created);return created.id}})()''')
        page.tap('#theme-open')
        page.wait('document.querySelector("#theme-dialog").open')
        page.tap(f'[data-theme-picker=dialog] [data-theme-choice={theme}]')
        page.wait(f'document.documentElement.dataset.theme === "{theme}"')
        page.evaluate('GameThemes.saved')
        page.evaluate('AndroidUI.back()')
        assert page.evaluate('document.documentElement.dataset.theme')==theme
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),theme
        assert page.evaluate('getComputedStyle(document.querySelector("#hud-hp")).display !== "none"'),theme
        page.evaluate('scrollTo(0,0)')
        page.screenshot(output/f'{theme}-game.png')
        age=page.evaluate('game.player.world_age')
        page.tap('#cultivate-action')
        page.wait(f'!busy && game.player.world_age > {age}')
        panels=page.evaluate('''(()=>{const errors=[];for(const b of document.querySelectorAll('[data-panel-target]')){
          const card=document.getElementById(b.dataset.panelTarget+'-card');
          if(card&&!card.classList.contains('hidden')&&!b.disabled){UtilityPanels.open(b.dataset.panelTarget);
            if(!card.classList.contains('panel-open'))errors.push(b.dataset.panelTarget);UtilityPanels.close(b.dataset.panelTarget);}}
          return errors;})()''')
        assert not panels,(theme,panels)
        page.tap('[data-panel-target=merchant]')
        page.wait('document.querySelector("#merchant-card").classList.contains("panel-open")')
        page.screenshot(output/f'{theme}-merchant.png')
        page.command('shell','input','keyevent','4')
        page.wait('!document.querySelector(".panel-open")')
        print(f'Theme {theme}: live touch action, all panels, merchant and Android back passed',flush=True)
    # Pause/rotate/resume retains the same WebView and game.
    before=page.evaluate('JSON.stringify(game)')
    page.command('shell','input','keyevent','3')
    page.command('shell','am','start','-n',page.package+'/com.fusheng.wendao.MainActivity')
    assert page.evaluate('JSON.stringify(game)')==before
    page.command('shell','settings','put','system','accelerometer_rotation','0')
    page.command('shell','settings','put','system','user_rotation','1')
    time.sleep(1)
    assert page.evaluate('JSON.stringify(game)')==before
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.screenshot(output/'f-landscape.png')
    page.command('shell','settings','put','system','user_rotation','0')
    time.sleep(.5)
    # Save deletion uses the same confirmation UI on device.
    second=page.evaluate('''(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'待删旅人',spirit_root:'supreme_metal',path:'dao',seed:1393})});showStart();return g.id})()''')
    selector=f'[data-save-id="{second}"] .save-delete'
    page.wait(f'document.querySelector({json.dumps(selector)})')
    page.tap(selector);page.command('shell','input','keyevent','4')
    page.wait('document.querySelector("#game-confirm-backdrop").classList.contains("hidden")')
    page.tap(selector);page.tap('#game-confirm-accept')
    page.wait(f'!busy && !document.querySelector({json.dumps(selector)})')
    assert page.evaluate(f'(async()=> (await api("/api/games")).games.some(g=>g.id==={json.dumps(gid)}))()')
    assert not page.errors,page.errors
    (output/'state.json').write_text(json.dumps({'id':gid,'before':json.loads(before),'extensions':config['extensions']},ensure_ascii=False),encoding='utf-8')
    page.close()
    # A genuine process death: theme, saves and DLC state must survive.
    page.command('shell','am','force-stop',page.package)
    page.command('shell','am','start','-n',page.package+'/com.fusheng.wendao.MainActivity')
    page=AndroidPage(serial).connect()
    assert page.evaluate('document.documentElement.dataset.theme')=='f'
    page.evaluate(f'loadGame({json.dumps(gid)})')
    assert page.evaluate('game.player.world_age')==json.loads(before)['player']['world_age']
    assert page.evaluate('game.player.name')=='安卓问道'
    assert not page.errors,page.errors
    page.close()
    print('Android 12 four-theme acceptance, save deletion/cancel, background, rotation and cold restart passed',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--serial',required=True)
    main(parser.parse_args().serial)

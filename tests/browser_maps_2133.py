"""Real map pages: eleven worlds, four themes, touch/desktop and future locations."""
import copy,json,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import WORLD_SYSTEMS
from scripts.release_evidence import inputs_digest
from scripts.browser_navigation import navigation_locator
from playwright.sync_api import sync_playwright
WORLDS=[w for w,p in WORLD_SYSTEMS['world_profiles'].items() if p['tier']>0]
def touch_drag(page,x,y,dx,dy,pinch=False):
 cdp=page.context.new_cdp_session(page)
 points=[dict(x=x,y=y,id=1)] if not pinch else [dict(x=x-35,y=y,id=1),dict(x=x+35,y=y,id=2)]
 cdp.send('Input.dispatchTouchEvent',dict(type='touchStart',touchPoints=points))
 for i in range(1,11):
  t=i/10
  points=[dict(x=x+dx*t,y=y+dy*t,id=1)] if not pinch else [dict(x=x-35-dx*t,y=y-dy*t,id=1),dict(x=x+35+dx*t,y=y+dy*t,id=2)]
  cdp.send('Input.dispatchTouchEvent',dict(type='touchMove',touchPoints=points));page.wait_for_timeout(20)
 cdp.send('Input.dispatchTouchEvent',dict(type='touchEnd',touchPoints=[]));cdp.detach();page.wait_for_timeout(100)
def align_view(page):
 page.locator('.atlas-viewport').evaluate("v=>{const p=v.closest('.utility-panel'),h=p.querySelector(':scope > .section-title').getBoundingClientRect();p.scrollTop+=v.getBoundingClientRect().top-h.bottom-14;}")
 return page.locator('.atlas-viewport').bounding_box()
def pan_and_check(page,mobile,flat=False):
 box=align_view(page);page.wait_for_function("(()=>{const e=document.querySelector('#map-atlas .current .atlas-dot');return e&&e.getBoundingClientRect().width>0;})()");page.wait_for_timeout(80);box=page.locator('.atlas-viewport').bounding_box();shape=page.locator('#map-atlas .atlas-viewport svg');probe=shape.locator('.current .atlas-dot')
 before=probe.evaluate('e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}}')
 if '--debug' in sys.argv:
  page.evaluate("""()=>{window.__pointerLog=[];for(const type of ['pointerdown','pointermove','pointerup','pointercancel','lostpointercapture','click','auxclick'])document.addEventListener(type,e=>__pointerLog.push({type,x:e.clientX,y:e.clientY,button:e.button,target:e.target.outerHTML?.slice(0,180),open:document.querySelector('#map-card').className}),true);}""")
 orientation=shape.get_attribute('data-orientation');selected=page.locator('#map-atlas .atlas-detail').get_attribute('data-selected-location')
 x=box['x']+box['width']*.35;y=box['y']+min(90,box['height']*.3);dx=62;dy=38
 if mobile:touch_drag(page,x,y,dx,dy)
 else:
  page.mouse.move(x,y);page.mouse.down(button='middle');page.mouse.move(x+dx,y+dy,steps=10);page.mouse.up(button='middle');page.wait_for_timeout(120)
 after=probe.evaluate('e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}}')
 if after is None:
  print('PAN VANISHED',box,page.evaluate('({events:window.__pointerLog,cls:document.querySelector("#map-card").className,point:document.elementFromPoint(100,200)?.outerHTML.slice(0,180),pan:document.querySelector(".atlas-scene")?.dataset.panX})'),flush=True);page.screenshot(path=str(ROOT/'build/pan-vanished-2133.png'));raise AssertionError('Map marker vanished during drag')
 assert abs((after['x']-before['x'])-dx)<2 and abs((after['y']-before['y'])-dy)<2,(box,before,after,page.evaluate('p=>document.elementFromPoint(p.x,p.y)?.outerHTML.slice(0,400)',dict(x=x,y=y)))
 assert shape.get_attribute('data-orientation')==orientation,'Pan changed map angle'
 assert page.locator('#map-atlas .atlas-detail').get_attribute('data-selected-location')==selected,'Pan selected a location'
 assert page.locator('.atlas-viewport').evaluate('v=>v.scrollWidth<=v.clientWidth+2&&v.scrollHeight<=v.clientHeight+2'),'Map still needs scrollbars'
 # Move the current marker to the center through an actual gesture, not a locate call.
 cx=box['x']+box['width']/2;cy=box['y']+box['height']/2
 dx=cx-(after['x']+after['width']/2);dy=cy-(after['y']+after['height']/2)
 if mobile:touch_drag(page,x,y,dx,dy)
 else:
  page.mouse.move(x,y);page.mouse.down(button='middle');page.mouse.move(x+dx,y+dy,steps=10);page.mouse.up(button='middle');page.wait_for_timeout(120)
 centered=probe.evaluate('e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}}')
 assert abs(centered['x']+centered['width']/2-cx)<2 and abs(centered['y']+centered['height']/2-cy)<2,'Cannot manually pan to center'
 return shape
def main():
 output=ROOT/'build/maps-2133';output.mkdir(exist_ok=True);rows=[];fingerprint=inputs_digest(ROOT)
 with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
  engine=GameEngine(ROOT,Path(directory)/'saves')
  class Quiet(server.Handler):
   def log_message(self,*args):pass
  with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(directory)):
   http=ThreadingHTTPServer(('127.0.0.1',0),Quiet);threading.Thread(target=http.serve_forever,daemon=True).start()
   try:
    with sync_playwright() as pw:
     browser=pw.chromium.launch()
     for world in (['demon'] if '--debug' in sys.argv else WORLDS[:1] if '--smoke' in sys.argv or '--touch-smoke' in sys.argv or '--land-smoke' in sys.argv else WORLDS):
      tier=WORLD_SYSTEMS['world_profiles'][world]['tier'];rank=4 if tier==1 else 7 if tier==2 else 9
      identity=engine.create_game('山海地图验收','supreme_earth','dao',2133,custom_start=dict(world=world,realm_index=rank))['id']
      g=engine.store.load(identity);g.pending_event=None;g.settings['silent_events']=True;g.settings['combat_popup']=False;engine.store.save(g)
      for theme in ('b' if '--debug' in sys.argv else 'a' if '--smoke' in sys.argv or '--touch-smoke' in sys.argv else 'abdf'):
       sizes=[(1440,1100)] if '--debug' in sys.argv else [(915,412)] if '--land-smoke' in sys.argv else [(412,915)] if '--touch-smoke' in sys.argv else [(1440,1100)] if '--smoke' in sys.argv else [(1440,1100),(412,915) if theme in 'ab' else (915,412)]
       for width,height in sizes:
        page=browser.new_page(viewport=dict(width=width,height=height),has_touch=width<1000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(f'http://127.0.0.1:{http.server_port}');
        try:page.wait_for_function('configData && !busy',timeout=60000)
        except Exception:
         print('Startup diagnostic',world,theme,width,errors,page.evaluate('({config:!!configData,busy,toast:document.querySelector("#toast")?.textContent})'),flush=True);raise
        page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click();page.evaluate('async id=>loadGame(id)',identity)
        navigation_locator(page,'[data-panel-target=map]').click();page.locator('#map-view-tabs button',has_text='可视地图').click();page.wait_for_selector('.atlas-scene')
        page.wait_for_function("document.querySelector('.atlas-scene').dataset.artworkState==='ready'")
        assert page.locator('[data-world-artwork]').get_attribute('data-world-artwork')==world
        assert f'/assets/maps/{world}.svg' in page.locator('.scene-authored-landscape').get_attribute('href')
        assert page.locator('.atlas-scene [data-atlas-location]').count()==len(engine.maps.worlds[world]['locations'])
        assert page.locator('[data-atlas-road]').count()==len(engine.maps.worlds[world]['routes'])
        assert len(set(page.locator('[data-shore-kind]').evaluate_all("els=>els.map(e=>e.dataset.shoreKind)")))>=3
        assert page.locator('.scene-marine-patch').count()>=8
        assert page.locator('[data-island-size="2"]').count()>=1
        assert page.locator('[data-island-size="1"]').count()>=1
        before=engine.store._path(identity).read_bytes()
        original=page.locator('.atlas-scene').get_attribute('data-yaw')
        pan_and_check(page,width<1000)
        # Rebuilding the selected location must retain the moved view.
        pan=page.locator('.atlas-scene').get_attribute('data-pan-x')
        page.evaluate('renderMap(game.map,game.auction_system)')
        assert page.locator('.atlas-scene').get_attribute('data-pan-x')==pan
        page.locator('[aria-label="复位地图视角"]').click()
        if width>=1000:
         box=align_view(page);x=box['x']+box['width']*.4;y=box['y']+50
         page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+65,y+45,steps=10);page.mouse.up();page.wait_for_timeout(100)
         assert page.locator('.atlas-scene').get_attribute('data-yaw')!=original
         page.locator('[aria-label="复位地图视角"]').click()
         box=align_view(page);x=box['x']+box['width']*.4;y=box['y']+70;z=float(page.locator('.atlas-scene').get_attribute('data-zoom'))
         page.mouse.move(x,y);page.mouse.wheel(0,-150);page.wait_for_timeout(120)
         assert float(page.locator('.atlas-scene').get_attribute('data-zoom'))>z
        else:
         box=align_view(page);x=box['x']+box['width']*.5;y=box['y']+90
         orientation=page.locator('.atlas-scene').get_attribute('data-orientation')
         touch_drag(page,x,y,28,12,pinch=True)
         assert float(page.locator('.atlas-scene').get_attribute('data-zoom'))>1
         assert page.locator('.atlas-scene').get_attribute('data-orientation')!=orientation
        page.locator('[aria-label="复位地图视角"]').click()
        page.locator('[aria-label="向右旋转地图"]').click();assert page.locator('.atlas-scene').get_attribute('data-yaw')!=original
        page.locator('[aria-label="复位地图视角"]').click();assert page.locator('.atlas-scene').get_attribute('data-yaw')==original
        initial_zoom=page.locator('.atlas-scene').get_attribute('data-zoom');page.locator('[aria-label="放大地图"]').click();assert page.locator('.atlas-scene').get_attribute('data-zoom')!=initial_zoom
        page.locator('[aria-label="复位地图视角"]').click();page.locator('[aria-label="定位当前地域"]').click()
        assert page.locator('.atlas-scene .current .atlas-dot').evaluate("e=>{const r=e.getBoundingClientRect(),p=e.closest('.utility-panel').getBoundingClientRect(),h=e.closest('.utility-panel').querySelector(':scope > .section-title').getBoundingClientRect();return r.bottom>h.bottom && r.top<Math.min(p.bottom,innerHeight)}")
        centered=page.locator('.atlas-scene .current .atlas-dot').bounding_box();box=page.locator('.atlas-viewport').bounding_box()
        assert abs(centered['x']+centered['width']/2-box['x']-box['width']/2)<2
        assert abs(centered['y']+centered['height']/2-box['y']-box['height']/2)<2
        current=engine.store.load(identity).player.location_id
        dest=next(n for n in engine.maps.worlds[world]['locations'] if n['id']!=current and not n.get('min_realm_index'))['id']
        page.locator('[aria-label="地图地点"]').select_option(dest);assert page.locator('#map-atlas .atlas-detail').get_attribute('data-selected-location')==dest
        expected=engine.maps.travel_plan(world,current,dest,rank).route;assert page.locator('.scene-road.route').count()==len(expected)-1
        page.locator('[data-atlas-mode=flat]').click();assert page.locator('.atlas-viewport svg').count()==1 and not page.locator('.atlas-scene').count()
        pan_and_check(page,width<1000,flat=True)
        page.locator('[data-atlas-mode="3d"]').click();assert page.locator('.atlas-scene').count()==1
        assert page.locator('#map-card').evaluate('el=>el.scrollWidth<=el.clientWidth+2')
        assert engine.store._path(identity).read_bytes()==before,'Map input changed authoritative state'
        page.screenshot(path=str(output/f'{world}-{theme}-{width}.png'))
        page.locator('.atlas-scene').screenshot(path=str(output/f'{world}-{theme}-{width}-scene.png'))
        # Append a location without any scene metadata and retain the existing roads.
        fallback=page.evaluate("""()=>{const m=structuredClone(game.map),p=structuredClone(m.locations[0]);p.id='future_location';p.name='新增山海';p.current=false;delete p.atlas;m.locations.push(p);m.roads.push({from:m.current,to:p.id,years:3});const a=MapScene.layout(m),b=MapScene.layout(m);MapAtlas.render(m,game,()=>{},()=>false);return {same:a===b,count:a.nodes.length};}""")
        assert fallback['same'];assert page.locator('[data-atlas-location=future_location]').count()==1
        assert page.locator('[data-atlas-road]').count()==len(engine.maps.worlds[world]['routes'])+1
        assert engine.store._path(identity).read_bytes()==before
        if world=='human' and theme=='a' and width==1440:
         # Actual failed local image request must retain the complete map.
         page.evaluate("""()=>{MapArtworkData.art_failure={...MapArtworkData.human,url:'/assets/maps/missing-artwork.svg'};const m=structuredClone(game.map);m.world='art_failure';MapAtlas.render(m,game,()=>{},()=>false);}""")
         page.wait_for_function("document.querySelector('.atlas-scene').dataset.artworkState==='fallback'")
         assert page.locator('[data-atlas-location]').count()==len(engine.maps.worlds[world]['locations'])
         assert page.locator('[data-atlas-road]').count()==len(engine.maps.worlds[world]['routes'])
         assert engine.store._path(identity).read_bytes()==before
        page.evaluate('renderMap(game.map,game.auction_system)')
        if world=='human' and theme=='f' and width==915:
         age=engine.store.load(identity).player.age
         page.locator('#map-atlas .atlas-detail [data-atlas-unavailable]').click();page.wait_for_function('!busy')
         actual=engine.store.load(identity);assert actual.player.world==world and actual.player.age>age
        assert not errors,errors
        rows.append(dict(world=world,theme=theme,width=width,height=height,locations=len(engine.maps.worlds[world]['locations']),render_ms=float(page.locator('.atlas-scene').get_attribute('data-render-ms'))));print('Map verified',world,theme,width,flush=True)
        page.close()
     browser.close()
   finally:http.shutdown();http.server_close()
 assert fingerprint==inputs_digest(ROOT),'Release source changed during browser verification'
 (output/'report.json').write_text(json.dumps(dict(inputs_sha256=fingerprint,cases=rows,passed=True),ensure_ascii=False,indent=2),encoding='utf8')
 print('Maps 2.13.3 browser passed:',len(rows),'cases, all roads, immutable state, camera, planar mode and future locations')
if __name__=='__main__':main()

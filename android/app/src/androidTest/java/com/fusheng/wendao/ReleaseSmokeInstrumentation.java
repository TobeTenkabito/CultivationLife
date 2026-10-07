package com.fusheng.wendao;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebView;
import org.json.JSONObject;
import org.json.JSONTokener;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Separate, same-signed test APK. No test hooks or remote debugging in release. */
public class ReleaseSmokeInstrumentation extends Instrumentation {
    private Bundle arguments;
    private Activity activity;
    private WebView web;

    @Override public void onCreate(Bundle args) { arguments=args; start(); }

    private WebView findWeb(View node) {
        if (node instanceof WebView) return (WebView)node;
        if (node instanceof ViewGroup) {
            ViewGroup group=(ViewGroup)node;
            for (int i=0;i<group.getChildCount();i++) {
                WebView found=findWeb(group.getChildAt(i)); if (found!=null) return found;
            }
        }
        return null;
    }

    private Object js(String expression) throws Exception {
        CountDownLatch done=new CountDownLatch(1);
        AtomicReference<String> result=new AtomicReference<>();
        runOnMainSync(() -> web.evaluateJavascript(expression,value->{result.set(value);done.countDown();}));
        if (!done.await(30,TimeUnit.SECONDS)) throw new AssertionError("JavaScript callback timed out");
        return new JSONTokener(result.get()).nextValue();
    }

    private Object async(String expression) throws Exception {
        js("window.__releaseProbe={pending:true};(async()=>{try{window.__releaseProbe={value:await ("+expression+")};}catch(e){window.__releaseProbe={error:String(e.stack||e)};}})();true");
        long deadline=System.currentTimeMillis()+60000;
        while(System.currentTimeMillis()<deadline) {
            JSONObject result=new JSONObject((String)js("JSON.stringify(window.__releaseProbe)"));
            if(result.has("error")) throw new AssertionError(result.getString("error"));
            if(!result.optBoolean("pending",false)) return result.opt("value");
            Thread.sleep(100);
        }
        throw new AssertionError("Async probe timed out: "+expression);
    }

    private void check(boolean condition,String message) { if(!condition) throw new AssertionError(message); }

    private void waitForJs(String condition, String message) throws Exception {
        waitForJs(condition, message, 15110);
    }

    private void waitForJs(String condition, String message, long timeoutMs) throws Exception {
        long deadline=System.currentTimeMillis()+timeoutMs;
        while(System.currentTimeMillis()<deadline) {
            if(Boolean.TRUE.equals(js(condition))) return;
            Thread.sleep(100);
        }
        throw new AssertionError(message);
    }

    /** Tap the actual input and send text through Android's IME InputConnection. */
    private void enterCommissionNumber(String label, String value) throws Exception {
        String selector=JSONObject.quote(".merchant-metrics input[aria-label='"+label+"']");
        js("window.__imeField=document.querySelector("+selector+");__imeField.scrollIntoView({block:'center'});true");
        Thread.sleep(350);
        JSONObject point=new JSONObject((String)js("JSON.stringify((()=>{const r=__imeField.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2,width:innerWidth}})())"));
        int[] origin=new int[2];
        runOnMainSync(()->web.getLocationOnScreen(origin));
        float scale=web.getWidth()/(float)point.getDouble("width");
        float x=origin[0]+(float)point.getDouble("x")*scale, y=origin[1]+(float)point.getDouble("y")*scale;
        long now=android.os.SystemClock.uptimeMillis();
        for(int action:new int[]{android.view.MotionEvent.ACTION_DOWN,android.view.MotionEvent.ACTION_UP}) {
            android.view.MotionEvent event=android.view.MotionEvent.obtain(now,android.os.SystemClock.uptimeMillis(),action,x,y,0);
            sendPointerSync(event);event.recycle();
        }
        waitForJs("document.activeElement===__imeField",label+": tap did not focus input");
        AtomicReference<Boolean> keyboard=new AtomicReference<>(false);
        long keyboardDeadline=System.currentTimeMillis()+10000;
        while(!keyboard.get() && System.currentTimeMillis()<keyboardDeadline) {
            runOnMainSync(()->keyboard.set(web.getRootWindowInsets().isVisible(android.view.WindowInsets.Type.ime())));
            Thread.sleep(150);
        }
        if(!keyboard.get()) capture("commission-keyboard-failure");
        check(keyboard.get(),label+": soft keyboard not visible");
        int length=((Number)js("__imeField.value.length")).intValue();
        AtomicReference<Boolean> committed=new AtomicReference<>(false);
        AtomicReference<android.view.inputmethod.InputConnection> connection=new AtomicReference<>();
        runOnMainSync(()->{
            android.view.inputmethod.EditorInfo info=new android.view.inputmethod.EditorInfo();
            connection.set(web.onCreateInputConnection(info));
        });
        android.view.inputmethod.InputConnection input=connection.get();
        check(input!=null,label+": no input connection");
        android.os.Handler inputHandler=input.getHandler();
        if(inputHandler==null) inputHandler=web.getHandler();
        CountDownLatch edited=new CountDownLatch(1);
        AtomicReference<Throwable> editError=new AtomicReference<>();
        inputHandler.post(()->{
            try {
                input.beginBatchEdit();
                boolean selected=input.setSelection(0,length);
                committed.set(selected && input.commitText(value,1));
                input.endBatchEdit();
            } catch(Throwable error) { editError.set(error); }
            finally { edited.countDown(); }
        });
        check(edited.await(10,TimeUnit.SECONDS) && editError.get()==null,label+": IME dispatch failed: "+editError.get());
        check(committed.get(),label+": IME rejected input");
        waitForJs("__imeField.value==="+JSONObject.quote(value),label+": wrong entered value");
        Thread.sleep(450);
        check(Boolean.TRUE.equals(js("document.activeElement===__imeField")),label+": quote stole focus");
    }

    private void tapSelector(String selector) throws Exception {
        String quoted=JSONObject.quote(selector);
        // Observe before tutorial capture handlers intercept the intended click.
        js("window.__releaseNativeTap=false;window.addEventListener('click',event=>{const target=document.querySelector("+quoted+");window.__releaseNativeTap=!!target&&target.contains(event.target);},{once:true,capture:true});document.querySelector("+quoted+").scrollIntoView({block:'center'});true");
        Thread.sleep(300);
        // Center within the panel's usable content, below its sticky heading.
        // Window centering can put controls underneath that heading in landscape.
        js("(()=>{const target=document.querySelector("+quoted+"),panel=target.closest('.utility-panel.panel-open');if(!panel)return;const box=panel.getBoundingClientRect(),heading=panel.querySelector(':scope > .section-title')?.getBoundingClientRect(),r=target.getBoundingClientRect(),top=Math.max(box.top,heading?.bottom||box.top)+8,bottom=Math.min(box.bottom,innerHeight)-8;if(bottom>top+20)panel.scrollTop+=(r.top+r.bottom)/2-(top+bottom)/2;})();true");
        Thread.sleep(150);
        String locate="(()=>{const target=document.querySelector("+quoted+");if(!target)return {ready:false};const r=target.getBoundingClientRect();for(const [fx,fy] of [[.5,.5],[.25,.25],[.75,.25],[.25,.75],[.75,.75]]){const x=r.left+r.width*fx,y=r.top+r.height*fy,hit=document.elementFromPoint(x,y);if(!target.disabled&&hit&&target.contains(hit))return {ready:true,x,y,width:innerWidth};}return {ready:false,rect:r.toJSON(),panel:target.closest('.utility-panel')?.className,hit:document.elementFromPoint(r.left+r.width/2,r.top+r.height/2)?.outerHTML};})()";
        waitForJs("("+locate+").ready===true", "Native target not clickable: "+selector+": "+js("JSON.stringify("+locate+")"));
        JSONObject point=new JSONObject((String)js("JSON.stringify("+locate+")"));
        int[] origin=new int[2];runOnMainSync(()->web.getLocationOnScreen(origin));
        float scale=web.getWidth()/(float)point.getDouble("width");
        float x=origin[0]+(float)point.getDouble("x")*scale,y=origin[1]+(float)point.getDouble("y")*scale;
        long now=android.os.SystemClock.uptimeMillis();
        for(int action:new int[]{android.view.MotionEvent.ACTION_DOWN,android.view.MotionEvent.ACTION_UP}) {
            android.view.MotionEvent event=android.view.MotionEvent.obtain(now,android.os.SystemClock.uptimeMillis(),action,x,y,0);
            try {
                event.setSource(android.view.InputDevice.SOURCE_TOUCHSCREEN);
                check(getUiAutomation().injectInputEvent(event,false), "Native input injection failed: "+selector);
            } finally { event.recycle(); }
        }
        // Android input injection returns before WebView dispatches the DOM click.
        // Let it arrive before a following tap scrolls a still-hidden panel.
        // Animated WebViews may never become idle. Wait for the actual click
        // with a deadline instead of blocking the instrumentation indefinitely.
        waitForJs("window.__releaseNativeTap===true", "Native click missing: "+selector);
        Thread.sleep(250);
    }

    private void python(String code) {
        com.chaquo.python.Python.getInstance().getModule("builtins").callAttr("exec",code,
            com.chaquo.python.Python.getInstance().getModule("builtins").callAttr("dict"));
    }
    private String assetText(String name) throws Exception {
        try(java.io.InputStream input=getContext().getAssets().open(name)) {
            java.io.ByteArrayOutputStream buffer=new java.io.ByteArrayOutputStream();
            byte[] chunk=new byte[8192];int length;
            while((length=input.read(chunk))!=-1) buffer.write(chunk,0,length);
            return new String(buffer.toByteArray(),StandardCharsets.UTF_8);
        }
    }

    private void capture(String name) throws Exception {
        android.util.Log.i("ReleaseSmoke", "Capture start: " + name);
        if(!Boolean.TRUE.equals(js("!!window.TutorialGuide && TutorialGuide.isGuiding()"))) js("scrollTo(0,0)");
        async("document.fonts.ready");
        CountDownLatch frame=new CountDownLatch(1);
        runOnMainSync(()->web.postVisualStateCallback(System.nanoTime(),new WebView.VisualStateCallback(){
            @Override public void onComplete(long id) { web.invalidate();frame.countDown(); }
        }));
        check(frame.await(15,TimeUnit.SECONDS),"WebView frame did not settle");
        Thread.sleep(500);
        android.util.Log.i("ReleaseSmoke", "Capture bitmap: " + name);
        Bitmap bitmap=getUiAutomation().takeScreenshot();
        File root=new File(getTargetContext().getExternalFilesDir(null),"verification");
        check(root.isDirectory() || root.mkdirs(),"Screenshot directory unavailable: "+root);
        try(FileOutputStream out=new FileOutputStream(new File(root,name+".png"))) {
            bitmap.compress(Bitmap.CompressFormat.PNG,100,out);
        }
        bitmap.recycle();
        android.util.Log.i("ReleaseSmoke", "Capture complete: " + name);
    }

    @Override public void onStart() {
        Bundle result=new Bundle();
        try {
            activity=startActivitySync(new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            if("portrait".equals(arguments.getString("orientation"))) runOnMainSync(()->activity.setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_PORTRAIT));
            if("landscape".equals(arguments.getString("orientation"))) runOnMainSync(()->activity.setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE));
            long deadline=System.currentTimeMillis()+60000;
            while(web==null && System.currentTimeMillis()<deadline) {
                runOnMainSync(()->web=findWeb(activity.findViewById(android.R.id.content)));
                Thread.sleep(150);
            }
            check(web!=null,"Release WebView did not start");
            while(!Boolean.TRUE.equals(js("typeof configData!=='undefined' && !!configData && !!window.AndroidUI")) && System.currentTimeMillis()<deadline) Thread.sleep(150);
            async("GameThemes.ready");
            String baseVersion=getTargetContext().getPackageManager().getPackageInfo(getTargetContext().getPackageName(),0).versionName.split("-android")[0];
            check(Boolean.TRUE.equals(js("configData.base_game.version==="+JSONObject.quote(baseVersion)+" && !configData.debug && configData.extensions.length===8 && configData.extensions.every(e=>e.status==='loaded')")),"Version, release mode or DLC mismatch: installed="+baseVersion+" config="+js("JSON.stringify({version:configData?.base_game?.version,debug:configData?.debug,extensions:configData?.extensions})"));
            SharedPreferences marker=getTargetContext().getSharedPreferences("release-verification",0);
            String phase=arguments.getString("phase","initial");
            // These two legacy phases verify base-game fallback without the optional Asura DLC.
            if(phase.equals("upper-voisinage") || phase.equals("upper")) python("from cultivation_life.system.asura import config\nconfig()['enabled']=False");
            if(phase.equals("start-layout")) {
                js("document.querySelector('#new-game-button').click();true");
                waitForJs("!document.querySelector('#start-screen').classList.contains('hidden')", "Start screen visible");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=start] [data-theme-choice="+theme+"]').click();true");
                    async("GameThemes.saved"); Thread.sleep(400);
                    check(Boolean.TRUE.equals(js("document.documentElement.scrollWidth<=innerWidth+1 && document.querySelector('#start-screen [data-tutorial-open] svg')!==null")), "Start layout theme "+theme);
                    tapSelector("#start-screen [data-tutorial-open]");
                    waitForJs("document.querySelector('#tutorial-dialog').open", "Start tutorial opens");
                    runOnMainSync(()->activity.onBackPressed());
                    waitForJs("!document.querySelector('#tutorial-dialog').open", "Native back closes start tutorial");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('.quick-start-button').length===configData.quick_starts.length && Array.from(document.querySelectorAll('.quick-start-group')).every(e=>e.tagName==='DETAILS')")), "Compact groups retain all presets");
                    tapSelector(".quick-start-group:nth-child(3)>summary");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('.quick-start-group')[2].open && document.querySelector('[data-preset-id=buddhist_void]').textContent.includes('佛修 DLC')")), "Expand group and Buddhist DLC badge");
                    tapSelector(".quick-start-group:nth-child(3)>summary");
                }
                js("document.querySelector('[data-preset-id=buddhist_void]').closest('details').open=true;true");
                tapSelector("[data-preset-id=buddhist_void]");
                waitForJs("!busy && game?.player.path==='buddhist' && !document.querySelector('#game-screen').classList.contains('hidden')", "Native Buddhist quick start");
                check(Boolean.TRUE.equals(js("document.querySelector('#action-card [data-tutorial-open] svg')!==null")), "Tutorial icon survives game rendering");
                capture("start-layout");
                js("document.querySelector('#new-game-button').click();document.querySelector('[data-preset-id=lost_world]').closest('details').open=true;true");
                check(Boolean.TRUE.equals(js("document.querySelector('[data-preset-id=lost_world]').disabled")), "Lost start requires path");
                js("(()=>{const p=document.querySelector('[data-quick-path]');p.value='monster';p.dispatchEvent(new Event('change'));})()");
                check(Boolean.TRUE.equals(js("document.querySelector('[data-preset-id=lost_world]').disabled && !document.querySelector('[data-quick-species]').hidden")), "Lost monster start requires species");
                js("(()=>{const s=document.querySelector('[data-quick-species]');s.value='serpent';s.dispatchEvent(new Event('change'));})()");
                tapSelector("[data-preset-id=lost_world]");
                waitForJs("!busy && game?.player.world==='lost' && game.player.path==='monster'", "Native lost monster start");
                tapSelector("[data-panel-target=map]");
                check(Boolean.TRUE.equals(js("game.map.locations.length===4 && game.map.locations.every(l=>Object.values(l.qi_concentrations).every(v=>Number.isFinite(v)&&v>0)) && document.querySelectorAll('#map-locations .map-location').length===4")), "Generated lost maps and finite qi");
                capture("lost-quick-start");
            } else if(phase.equals("spatial-talisman")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'符道地图验收',spirit_root:'supreme_metal',path:'dao',preset_id:'core',seed:1591})});return g.id;})()");
                python("from cultivation_life import server\nfrom cultivation_life.rules import add_item,max_mp\nfrom cultivation_life.system import spatial\nfrom cultivation_life.runtime import encode_rng\nimport random\ng=server.ENGINE._load("+JSONObject.quote(id)+")\ng.pending_event=g.active_trial=None\nadd_item(g.player,'spirit_stone',10**12)\nadd_item(g.player,'talisman_human_1_paper',10)\nadd_item(g.player,'talisman_human_1_ink',10)\ng.player.mp=max_mp(g.player)\nfor i in range(3): spatial.new_rift(g,random.Random(i),server.ENGINE.maps,controlled=True)\ng.rng_state=encode_rng(random.Random(1))\nserver.ENGINE.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.spatial.rifts.length===0 && !document.querySelector('.spatial-rift')")),"Rifts hidden before Nascent Soul");
                python("from cultivation_life import server\ng=server.ENGINE._load("+JSONObject.quote(id)+")\ng.player.realm_index=4\nserver.ENGINE.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                tapSelector("[data-panel-target=talisman]");
                js("(()=>{const s=document.querySelector('#talisman-content [aria-label=符箓阶数]');s.value='1';s.dispatchEvent(new Event('change'));})()");
                tapSelector("#talisman-content details button");
                waitForJs("!busy && game.talismans.methods[0].learned","Native learn recipe");
                tapSelector("#talisman-content .exploration-grid > button");
                waitForJs("!busy && game.talismans.rows.length===1","Native talisman crafting");
                check(Boolean.TRUE.equals(js("game.talismans.rows[0].tier===1 && !!game.talismans.rows[0].quality && game.talismans.skill.experience>0")),"Tier, quality and experience");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-choice="+theme+"]').click();true");async("GameThemes.saved");
                    tapSelector("[data-panel-target=map]");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('#map-locations .map-location .spatial-rift').length===3 && !document.querySelector('#map-card > #spatial-panel')")),"Rifts inside map locations");
                    tapSelector("[data-panel-target=talisman]");
                    check(Boolean.TRUE.equals(js("(()=>{const r=document.querySelector('#talisman-card').getBoundingClientRect();return r.left>=0 && r.right<=innerWidth+1 && !document.querySelector('#inventory-card #talisman-content')})()")),"Native talisman layout "+theme);
                }
                tapSelector("[data-panel-target=market]");
                tapSelector("#talisman-market-offers .market-buy:not([disabled])");
                waitForJs("!busy && game.market.talisman_material_offers.some(r=>r.sold)","Native material purchase");
                tapSelector("#market-talisman-sellables button");
                waitForJs("!busy && game.talismans.rows.length===0","Native talisman sale");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.talismans.rows.length===0 && game.talismans.skill.experience>0")),"Talisman persistence");
                python("from cultivation_life import server\ng=server.ENGINE._load("+JSONObject.quote(id)+")\ng.auction_state=dict(status='black_market',world=g.player.world,location_id=g.player.location_id,lots=[],attendees=[])\nserver.ENGINE.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                js("UtilityPanels.open('auction');document.querySelector('#black-market-pattern').value='符';true");
                tapSelector("#black-market-search-form button");
                waitForJs("!busy && game.auction_system.black_market_results.some(r=>r.kind==='talisman')","Native finished talisman search");
                js("(()=>{const r=Array.from(document.querySelectorAll('#black-market-results .auction-lot')).find(r=>r.textContent.includes('成品符箓'));r.querySelector('button').id='native-finished-talisman-buy';})()");
                tapSelector("#native-finished-talisman-buy");
                waitForJs("!busy && game.talismans.rows.length===1","Native finished talisman purchase");
                String lostId=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'本地交往验收',spirit_root:'supreme_metal',path:'demonic',preset_id:'lost_world',seed:1592})});return g.id;})()");
                async("loadGame("+JSONObject.quote(lostId)+")");
                tapSelector("[data-panel-target=relationship]");
                tapSelector("#npc-contacts .contact-directory button");
                tapSelector("[data-contact-action=improve]");
                waitForJs("!busy && game.world_npcs.some(n=>n.affinity>0)","Native local NPC interaction");
                check(Boolean.TRUE.equals(js("game.demonic_system.soul_refinement_risk.safe_capacity===2 && game.spatial.panels.includes('relationship')")),"Native soul capacity and isolated capabilities");
                capture("spatial-talisman");
                result.putString("spatial_talisman_scope","Native learn/craft/buy/sell, black-market finished purchase, lost local NPC interaction and soul capacity, tier/quality/experience, four-theme left panel, Nascent Soul visibility, multiple rifts inside map locations and persistence");
            } else if(phase.equals("heavens")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'诸界验收',preset_id:'core',seed:200})});return g.id;})()");
                python("from cultivation_life import server\nfrom cultivation_life.system.heavens.incident_definitions import ALL_INCIDENTS as INCIDENTS\nfrom cultivation_life.system.heavens.state import initialize\nfrom cultivation_life.rules import max_hp,max_mp,add_item\ng=server.ENGINE.store.load('"+id+"')\ninitialize(g)\ng.player.world='human'\ng.player.location_id='lanjiang_steppe'\ng.player.realm_index=2\ng.player.lifespan=None\ng.player.next_tribulation_age=999999\ng.player.hp=max_hp(g.player)\ng.player.mp=max_mp(g.player)\nadd_item(g.player,'spirit_stone',10000)\ng.settings['silent_events']=True\ng.heavens_state['runtime']['incidents']={d.id:dict(stage='surveyed',choice=None,opened_at=0,closed_at=None,remaining=0,base=0.0,claimed=0.0) for d in INCIDENTS}\ng.heavens_state['definition_versions'].update({d.id:1 for d in INCIDENTS})\nserver.ENGINE.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                tapSelector("[data-panel-target=heavens]");
                check(Boolean.TRUE.equals(js("!!document.querySelector('#strategy-dock [data-panel-target=heavens]') && !document.querySelector('.left-dock [data-panel-target=heavens]')")),"Heavens belongs to social dock");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('#theme-open').click();true");
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click();true");
                    async("GameThemes.saved");
                    js("document.querySelector('[data-close-dialog=theme-dialog]').click();true");
                    for(String category:new String[]{"worlds","anomalies","frontier"}) {
                    for(String world:new String[]{"human","spirit","demon","true_demon","monster_realm","phantom_underworld","hell","celestial","asura","nether","reincarnation"}) {
                        js("document.querySelector('#heavens-primary-"+category+"').click();true");
                        js("(()=>{const s=document.querySelector('[aria-label=选择界域]');s.value='"+world+"';s.dispatchEvent(new Event('change'));document.querySelector('.heavens-destination').click();return true;})()");
                        check(Boolean.TRUE.equals(js("(()=>{const c=document.querySelector('#heavens-card').getBoundingClientRect(),b=document.querySelector('#heavens-body').getBoundingClientRect(),x=document.querySelector('#heavens-toggle').getBoundingClientRect();return c.top>=0 && c.bottom<=innerHeight+1 && b.height>=140 && x.top>=0 && x.bottom<=innerHeight;})()")),"Heavens visible reading area "+theme+" "+world);
                        for(String tab:new String[]{"record","response","aftermath"}) {
                            js("document.querySelector('[data-heavens-tab="+tab+"]').click();true");
                            check(Boolean.TRUE.equals(js("(()=>{const b=document.querySelector('#heavens-detail-body');return b.scrollWidth<=b.clientWidth+1 && document.documentElement.scrollWidth<=innerWidth+1 && b.querySelectorAll('[data-heavens-action]').length<=1 && !!b.querySelector('p') && Array.from(b.querySelectorAll('select,[data-heavens-action]')).every(e=>e.getBoundingClientRect().height>=44);})()")),"Heavens dossier "+theme+" "+world+" "+tab);
                        }
                    }
                }
                }

                js("document.querySelector('#heavens-primary-worlds').click();true");
                js("(()=>{const s=document.querySelector('[aria-label=选择界域]');s.value='human';s.dispatchEvent(new Event('change'));document.querySelector('.heavens-destination').click();document.querySelector('[data-heavens-tab=response]').click();const c=document.querySelector('[aria-label=界域处理方案]');c.value='incident_seal';c.dispatchEvent(new Event('change'));return true;})()");
                tapSelector("[data-heavens-action=incident_seal]");
                waitForJs("!document.querySelector('#game-confirm-backdrop').classList.contains('hidden')","Heavens preview");
                tapSelector("#game-confirm-cancel");
                check(Boolean.TRUE.equals(js("game.heavens.incidents.find(r=>r.id==='human_beacon').stage==='surveyed'")),"Heavens cancelled preview is pure");
                tapSelector("[data-heavens-action=incident_seal]");
                tapSelector("#game-confirm-accept");
                waitForJs("!busy && game.heavens.incidents.find(r=>r.id==='human_beacon').stage==='treated'","Heavens native real-year action");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.heavens.incidents.length===11 && game.heavens.incidents.find(r=>r.id==='human_beacon').choice==='incident_seal'")),"Heavens persisted outcome");
                capture("heavens");
                result.putString("heavens_scope","Eleven worlds, four themes, independent dossiers, bounded buttons, native touch preview/cancel/commit and persisted result");
            } else if(phase.equals("debug-console")) {
                check(Boolean.TRUE.equals(js("!!document.querySelector('#debug-console-open') && typeof AndroidGame.requestDebugMode==='function' && typeof AndroidGame.exportDebugBundle==='function'")), "Console available and native capabilities");
                js("location.reload();true"); Thread.sleep(800);
                // Reload has the same startup budget as the initial WebView.
                waitForJs("typeof configData!=='undefined' && configData?.console_available===true && !!document.querySelector('#debug-console-open')", "Debug console enabled",60000);
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'Debug Console Verification',preset_id:'core',seed:5701})});await loadGame(g.id);return g.id;})()");
                python("from cultivation_life import server\nfrom pathlib import Path\np=server.ENGINE.store.directory / ("+JSONObject.quote(id)+"+'.json')\nserver._console_source_bytes=p.read_bytes()");
                js("AndroidGame.requestDebugMode();true"); waitForJs("!busy && document.querySelector('#debug-console').open", "Native console opening and help loaded");
                for(String command:new String[]{"debug start","player set spirit_stones 1234567","player set breakthrough_chance 1","snapshot create baseline","player set realm_index 4","player set layer 7","snapshot restore baseline","tianji reveal all","game view /tianji_artifacts","capability list"}) {
                    js("document.querySelector('#debug-console-input').value="+JSONObject.quote(command)+";document.querySelector('#debug-console form').requestSubmit();true");
                    waitForJs("!busy && !document.querySelector('#debug-console-input').disabled", "Command completed: "+command);
                    check(Boolean.TRUE.equals(js("!document.querySelector('#debug-console-output pre:last-child')?.classList.contains('debug-error')")), "Command result: "+command);
                }
                check(Boolean.TRUE.equals(js("game.player.inventory.find(x=>x.id==='spirit_stone').quantity===1234567 && !!sessionStorage.getItem('cultivation-debug-session')")), "Isolated resource mutation");
                tapSelector("#debug-heavens>summary");
                tapSelector("#debug-heavens .debug-actions button:nth-child(1)");
                waitForJs("!busy && !document.querySelector('#debug-heavens-target').disabled && document.querySelector('#debug-heavens-action').options.length>0", "Heavens workbench loaded");
                check(Boolean.TRUE.equals(js("document.querySelector('#debug-heavens-target').options.length>=6")), "Heavens target discovery");
                js("(()=>{window.__heavensWatch=game.heavens.watch;const s=document.querySelector('#debug-heavens-target');s.value='configuration';s.dispatchEvent(new Event('change'));const a=document.querySelector('#debug-heavens-action');a.value='1';a.dispatchEvent(new Event('change'));return true;})()");
                tapSelector("#debug-heavens .debug-actions button:nth-child(2)");
                waitForJs("!busy && !document.querySelector('#debug-heavens .debug-actions button:nth-child(3)').disabled", "Heavens preview ready");
                tapSelector("#debug-heavens .debug-actions button:nth-child(3)");
                waitForJs("!busy && game.heavens.watch!==__heavensWatch && !document.querySelector('#debug-heavens-target').disabled", "Heavens isolated native commit");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-choice="+theme+"]').click();true");
                    check(Boolean.TRUE.equals(js("(()=>{const r=document.querySelector('#debug-console').getBoundingClientRect();return r.left>=0 && r.right<=innerWidth+1 && !!document.querySelector('#debug-session-banner').textContent;})()")), "Console geometry theme "+theme);
                    check(Boolean.TRUE.equals(js("(()=>{const r=document.querySelector('#debug-heavens');return r.scrollWidth<=r.clientWidth+1 && Array.from(r.querySelectorAll('select,button')).every(e=>e.getBoundingClientRect().height>=44);})()")), "Heavens workbench geometry "+theme);
                }
                // Exercise the real SAF result handlers with a deterministic test URI.
                File debugFile=new File(getTargetContext().getExternalFilesDir(null),"verification/debug-export.json");
                debugFile.getParentFile().mkdirs();
                if(debugFile.exists()) check(debugFile.delete(),"Clear previous debug export fixture");
                Intent debugDocument=new Intent().setData(android.net.Uri.fromFile(debugFile));
                android.content.IntentFilter exportFilter=new android.content.IntentFilter(Intent.ACTION_CREATE_DOCUMENT);
                exportFilter.addCategory(Intent.CATEGORY_OPENABLE);exportFilter.addDataType("application/json");
                ActivityMonitor exportMonitor=addMonitor(exportFilter,new ActivityResult(Activity.RESULT_OK,debugDocument),true);
                async("(async()=>{const r=await fetch('/api/debug/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command:'repro export',session_id:sessionStorage.getItem('cultivation-debug-session')})});const v=await r.json();window.__debugExportText=v.data.download.content;AndroidGame.exportDebugBundle(__debugExportText);return true;})()");
                long exportDeadline=System.currentTimeMillis()+30000;
                while((!debugFile.isFile() || debugFile.length()==0) && System.currentTimeMillis()<exportDeadline) Thread.sleep(100);
                removeMonitor(exportMonitor);
                check(debugFile.isFile() && debugFile.length()>0,"Native debug document export");
                waitForJs("document.querySelector('#debug-console-output').textContent.includes('复现包已保存')", "Native debug export completed");
                JSONObject debugBundle=new JSONObject(new String(java.nio.file.Files.readAllBytes(debugFile.toPath()),StandardCharsets.UTF_8));
                check(debugBundle.getString("format").equals("CultivationLife.debug.v1"),"Native exported bundle format");
                check(!debugBundle.getJSONObject("export_environment").isNull("build_sha256"),"Android source-build fingerprint");
                String oldSession=(String)js("sessionStorage.getItem('cultivation-debug-session')");
                android.content.IntentFilter importFilter=new android.content.IntentFilter(Intent.ACTION_OPEN_DOCUMENT);
                importFilter.addCategory(Intent.CATEGORY_OPENABLE);importFilter.addDataType("application/json");
                ActivityMonitor importMonitor=addMonitor(importFilter,new ActivityResult(Activity.RESULT_OK,debugDocument),true);
                js("AndroidGame.importDebugBundle();true");
                waitForJs("!busy && sessionStorage.getItem('cultivation-debug-session')!=="+JSONObject.quote(oldSession),"Native debug import creates a new isolated session");
                removeMonitor(importMonitor);
                capture("debug-console");
                runOnMainSync(()->activity.onBackPressed());
                waitForJs("!document.querySelector('#debug-console').open", "Native back closes console");
                async("mutate(`/api/games/${game.id}/advance`,{action:'rest',years:1})");
                python("from cultivation_life import server\np=server.ENGINE.store.directory / ("+JSONObject.quote(id)+"+'.json')\nassert p.read_bytes()==server._console_source_bytes");
                python("from android_runtime import set_debug_mode\nset_debug_mode(False)");
                check(((Number)async("fetch(`/api/games/${game.id}`,{headers:DebugConsole.headers(`/api/games/${game.id}`)}).then(r=>r.status)")).intValue()==200, "Legacy config does not disconnect isolated session");
                js("sessionStorage.removeItem('cultivation-debug-session');true");
                result.putString("debug_scope","Isolated source and achievements, resource and probability commands, snapshots, four themes, native document callbacks, source fingerprint, native back and config-independent isolated session");
            } else if(phase.equals("custody")) {
                python(assetText("npc_custody_release.py"));
            } else if(phase.equals("asura")) {
                String novice=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'人界门槛验收',spirit_root:'supreme_metal',path:'demonic',seed:1562})});await loadGame(g.id);return g.id;})()");
                check(Boolean.TRUE.equals(js("!game.asura.available && Array.from(document.querySelectorAll('[data-panel-target^=asura-]')).every(n=>n.classList.contains('hidden')) && !document.querySelector('[data-chapter=dlc-asura]')")),"Asura content hidden before upper realm");
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'魔脉分屏验收',preset_id:'asura_upper',seed:1560})});return g.id;})()");
                python("from cultivation_life import server\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.player.asura_cultivation.update(conversion=5,body_level=20,souls=10000,route='garuda',level=9,domain_rank=8,domain_name='验收翼域',vein_pity={'9:1':100})\ng.player.opportunity=1e12\ng.pending_event=None\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                tapSelector("[data-panel-target=asura-veins]");
                check(Boolean.TRUE.equals(js("document.querySelectorAll('.asura-meridian-figure .atlas-anatomy image').length===1 && document.querySelector('.asura-meridian-figure .atlas-anatomy image').getAttribute('href')==='/assets/asura-anatomy.png' && document.querySelectorAll('.asura-vein-node').length===27 && !document.querySelector('.asura-tabs')")),"Independent Asura figure and panels");
                check(Boolean.TRUE.equals(async("new Promise(resolve=>{const i=new Image();i.onload=()=>resolve(i.naturalWidth===1122&&i.naturalHeight===1402);i.onerror=()=>resolve(false);i.src='/assets/asura-anatomy.png'})")),"Packaged Asura contour artwork loads");
                tapSelector(".asura-meridian-figure [data-vein='4']");
                check(Boolean.TRUE.equals(js("document.querySelector('.asura-meridian-figure [data-vein=\"4\"]').getAttribute('aria-pressed')==='true' && document.querySelector('.asura-meridian-figure .atlas-selected-name').textContent.includes('绛魄府')")),"Native meridian selection and name");
                tapSelector("#asura-veins-content .asura-action");
                waitForJs("!busy && game.asura.opened===1","Native magic vein opening");
                tapSelector("[data-panel-target=asura-powers]");
                waitForJs("document.querySelector('#asura-powers-card').classList.contains('panel-open')","Native powers panel opening");
                tapSelector("#asura-powers-content .asura-action");
                waitForJs("!busy && game.asura.powers.length===1","Native supernatural power");
                for(int count=2;count<=3;count++) {
                    tapSelector("[data-asura-action=learn_power]");
                    waitForJs("!busy && game.asura.powers.length==="+count,"Learn additional power");
                }
                js("window.__oldAsuraPowers=JSON.stringify(game.asura.powers);window.__oldAsuraSouls=game.asura.souls;true");
                tapSelector("[data-asura-action=lock_power]");
                waitForJs("!busy && game.asura.power_reroll.locked_ids.length===1","Native attribute lock");
                tapSelector("[data-asura-action=reroll_power]");
                waitForJs("!busy && game.asura.souls===__oldAsuraSouls-200","Whole-set reroll fee");
                check(Boolean.TRUE.equals(js("(()=>{const old=JSON.parse(__oldAsuraPowers);return game.asura.powers.every((r,i)=>(JSON.stringify(r)===JSON.stringify(old[i]))===(i===0));})()")),"Locked attribute preserved; all other attributes rerolled");
                check(Boolean.TRUE.equals(js("game.player.opportunity_unbounded && game.player.opportunity>game.player.opportunity_required && game.asura.meridians.breakthrough_cost===18000")),"Asura reserve and immortal-scale fee");

                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    for(String panel:new String[]{"asura-conversion","asura-body","asura-veins","asura-route","asura-domain","asura-powers","puppet-workshop"}) {
                        tapSelector("[data-panel-target="+panel+"]");
                        waitForJs("document.querySelector('#"+panel+"-card').classList.contains('panel-open')","Native panel tap: "+panel+theme);
                        check(Boolean.TRUE.equals(js("(()=>{const e=document.querySelector('#"+panel+"-card');return e.scrollWidth<=e.clientWidth+1})()")),"Independent panel overflow "+panel+theme+": "+js("JSON.stringify((()=>{const e=document.querySelector('#"+panel+"-card');return {scroll:e.scrollWidth,client:e.clientWidth}})())"));
                    }
                    check(Boolean.TRUE.equals(js("getComputedStyle(document.querySelector('[data-panel-target=asura-veins]')).color!==getComputedStyle(document.querySelector('[data-panel-target=captive]')).color")),"DLC/base entrance color distinction");
                    tapSelector("[data-panel-target=asura-veins]");
                    js("document.querySelector('#asura-veins-card').scrollTop=0;true");
                    check(Boolean.TRUE.equals(js("(()=>{const r=document.querySelector('.asura-meridian-figure svg').getBoundingClientRect();return r.width>100&&r.width<innerWidth&&r.height>100})()")),"Magic vein illustration size");
                    capture("asura-veins-"+arguments.getString("orientation")+"-"+theme+"-1562");
                    sendKeyDownUpSync(android.view.KeyEvent.KEYCODE_BACK);waitForJs("!document.querySelector('.utility-panel.panel-open')","Native independent panel back");
                }
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.asura.opened===1 && game.asura.powers.length===3 && game.asura.power_reroll.locked_ids.length===1")),"Asura changes persist");
                result.putString("asura_scope","Six themes, seven independent panels, new 27-node three-head six-arm figure, native opening and power, DLC colors, native back and persistence");
            } else if(phase.equals("upper-voisinage")) {
                for(String world:new String[]{"asura","nether","reincarnation"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'三界修域验收',preset_id:'"+world+"_upper',monster_species_id:'serpent',seed:1560})});if(!g.upper_institution.local||g.player.realm_index!==9||!g.upper_voisinages.rows[0].active)throw Error('Upper preset mismatch');return g.id;})()");
                    python("from cultivation_life import server\nfrom cultivation_life.rules import opportunity_required,max_hp,max_mp,add_item\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\np=g.player\np.world="+JSONObject.quote(world)+"\np.path={'asura':'demonic','nether':'monster','reincarnation':'ghost'}[p.world]\nfrom cultivation_life.system.upper_institutions import definition\np.location_id=definition(g)['location']\np.world_voisinages={}\np.opportunity=opportunity_required(p)\np.hp=max_hp(p)\np.mp=max_mp(p)\np.immortal_aperture['current']=0\nadd_item(p,'spirit_stone',1000000)\ng.pending_event=None\ng.heavenly_court['open_election']=None\ne.store.save(g)");
                    async("loadGame("+JSONObject.quote(id)+")");
                    tapSelector("[data-panel-target=upper-voisinage]");
                    tapSelector("#upper-voisinage-content details summary");
                    tapSelector("#upper-voisinage-content details button");
                    waitForJs("!busy && game.upper_voisinages.rows[0].level===1 && game.upper_voisinages.rows[0].active","Native domain acquisition");
                    tapSelector("#upper-voisinage-content details button:last-child");
                    waitForJs("!busy && game.upper_voisinages.rows[0].level===2","Native domain training");
                    js("UtilityPanels.open('upper-institution');true");
                    if(world.equals("asura")) {
                        js("Array.from(document.querySelectorAll('#upper-institution-content button')).find(b=>b.textContent==='登记效力').dataset.nativeJoin='true'");
                        tapSelector("[data-native-join]");
                    } else {
                        tapSelector("#upper-institution-content [data-section=identity] summary");
                        tapSelector("#upper-institution-content [data-section=identity] button");
                    }
                    waitForJs("!busy&&game.upper_institution.joined","Native institution enrollment");
                    if(world.equals("asura")) {
                        tapSelector("#upper-institution-content .court-tabs button:nth-child(4)");
                        js("Array.from(document.querySelectorAll('#upper-institution-content button')).find(b=>b.textContent==='接取委托').dataset.nativeJob='true'");
                        tapSelector("[data-native-job]");
                    } else {
                        tapSelector("#upper-institution-content [data-section=jobs] summary");
                        tapSelector("#upper-institution-content [data-section=jobs] button");
                    }
                    waitForJs("!busy&&game.upper_institution.job!==null","Native institution commission");
                    for(String theme:new String[]{"a","b","d","f"}) {
                        js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                        for(String panel:new String[]{"upper-voisinage","immortal-aperture","upper-institution"}) {
                            js("UtilityPanels.open('"+panel+"');true");
                            check(Boolean.TRUE.equals(js("(()=>{const e=document.querySelector('#"+panel+"-card');return !e.classList.contains('hidden')&&e.scrollWidth<=e.clientWidth+1})()")),"Upper voisinage panel overflow "+world+theme);
                        }
                        js("UtilityPanels.open('upper-voisinage');true");capture("upper-voisinage-"+world+"-"+theme+"-1562");
                    }
                    js("UtilityPanels.open('immortal-aperture');true");tapSelector("#immortal-aperture-content button");
                    waitForJs("!busy && game.aperture.current>0","Native energy refinement");
                    async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("game.upper_voisinages.rows[0].level===2&&game.aperture.current>0")),"Upper cultivation persisted");
                }
                check(Boolean.TRUE.equals(js("TutorialHandbook.build(configData,game).some(c=>c.id==='upper-voisinages')")),"Upper domain handbook missing");
                result.putString("upper_voisinage_scope","Three worlds, four themes, native ninth-realm presets, institution enrollment/commissions, acquisition/training/refinement and persisted domains; handbook available");
            } else if(phase.equals("bulk")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'批量兑换验收',preset_id:'true_immortal',seed:1521})});return g.id;})()");
                python("from cultivation_life import server\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.heavenly_court['open_election']=None\ng.player.location_id='expanse_celestial_8'\ng.yaochi_state['merit']=100000\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    js("UtilityPanels.open('yaochi');window.__bulkOffer=game.yaochi.shop.find(o=>o.kind==='item'&&o.quantity>1);window.__bulkBalance=game.yaochi.merit;window.__bulkCount=(game.player.inventory.find(i=>i.id===__bulkOffer.id)||{quantity:0}).quantity;document.querySelector('[data-offer-id=\"'+__bulkOffer.id+'\"]').dataset.bulkTest='true';true");
                    js("(()=>{const q=document.querySelector('[data-bulk-test] input');q.value='0';q.dispatchEvent(new Event('input',{bubbles:true}));})()");
                    check(Boolean.TRUE.equals(js("document.querySelector('[data-bulk-test] button').disabled")),"Zero quantity rejected");
                    js("(()=>{const q=document.querySelector('[data-bulk-test] input');q.value='7';q.dispatchEvent(new Event('input',{bubbles:true}));})()");
                    check(Boolean.TRUE.equals(js("!document.querySelector('[data-bulk-test] button').disabled && document.querySelector('[data-bulk-test] .yaochi-purchase-total').textContent.includes((__bulkOffer.price*7).toLocaleString('zh-CN'))")),"Bulk cost preview");
                    check(Boolean.TRUE.equals(js("document.querySelector('#yaochi-card').scrollWidth<=document.querySelector('#yaochi-card').clientWidth+1")),"Bulk panel overflow "+theme);
                    capture("bulk-"+theme+"-1521");
                    tapSelector("[data-bulk-test] button");
                    waitForJs("!busy && game.yaochi.merit===__bulkBalance-__bulkOffer.price*7","Bulk purchase charged");
                    async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("game.player.inventory.find(i=>i.id===__bulkOffer.id).quantity===__bulkCount+__bulkOffer.quantity*7")),"Bulk inventory persisted");
                }
                result.putString("bulk_scope","Six themes, quantity validation, total preview, native purchase taps and exact persisted quantities");
            } else if(phase.equals("experience")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'体验安卓验收',preset_id:'true_immortal',seed:1520})});return g.id;})()");
                python("from cultivation_life import server\nfrom cultivation_life.models import Technique\nfrom cultivation_life.rules import learn_technique\nimport copy,random\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.player.location_id='expanse_celestial_8'\ng.heavenly_court['player_grade']=4\ng.yaochi_state['experience']=200\ng.yaochi_state['job']={'name':'验收委托','years':100,'progress':100,'reward':400}\nfor d in g.doctrine_state['definitions'].values():\n learn_technique(g.player,Technique(**copy.deepcopy(d['manuals'][0])))\n g.doctrine_state['player']['progress'][d['id']]={'level':4,'experience':0}\ng.doctrine_state['player']['active']=next(iter(g.doctrine_state['definitions']))\ne._court_open_election(g,'sun',random.Random(1))\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                js("window.__experienceAge=game.player.age;true");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    for(String panel:new String[]{"doctrine","voisinage","daomen"}) {
                        js("UtilityPanels.open('"+panel+"');true");
                        check(Boolean.TRUE.equals(js("document.querySelectorAll('#"+panel+"-content .doctrine-compact').length===25 && document.querySelector('#"+panel+"-card').scrollWidth<=document.querySelector('#"+panel+"-card').clientWidth+1")),"Compact collection "+panel+theme);
                        tapSelector("#"+panel+"-content .doctrine-compact > summary");
                        check(Boolean.TRUE.equals(js("document.querySelector('#"+panel+"-content .doctrine-compact').open")),"Native expand "+panel);
                        tapSelector("#"+panel+"-content .doctrine-compact > summary");
                    }
                    capture("experience-"+theme+"-1520");
                }
                tapSelector("#daomen-content .doctrine-compact > summary");
                js("document.querySelector('#daomen-content .doctrine-compact button').dataset.experienceSearch='true';true");
                tapSelector("[data-experience-search]");waitForJs("!busy && game.doctrines.rows.some(r=>r.peer_preview)","Peer preview");
                check(Boolean.TRUE.equals(js("game.player.age===__experienceAge && game.doctrines.rows.every(r=>!r.peers.length)")),"Preview time and roster");
                tapSelector("#daomen-content .peer-preview button");waitForJs("!busy && game.doctrines.rows.some(r=>r.peers.length===1)","Retain peer");
                check(Boolean.TRUE.equals(js("game.player.age===__experienceAge")),"Retain does not age");
                js("UtilityPanels.open('yaochi');Array.from(document.querySelectorAll('#yaochi-content button')).find(b=>b.textContent==='交付并领取功勋').dataset.experienceClaim='true';true");
                tapSelector("[data-experience-claim]");waitForJs("!busy && game.yaochi.experience.level===2 && game.yaochi.experience.multiplier===1.1","Yaochi experience");
                js("UtilityPanels.open('settings');true");tapSelector("#setting-court-election");
                waitForJs("!busy && game.settings.court_election_popup===false && !game.heavenly_court.election","Quiet elections");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.settings.court_election_popup===false && game.player.age===__experienceAge && game.yaochi.experience.level===2")),"Experience persistence");
                result.putString("experience_scope","Six themes, 25 compact collections and native expansion, preview/retain without aging, Yaochi experience claim, election opt-out and persistence");
            } else if(phase.equals("institutions")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'机构安卓验收',preset_id:'true_immortal',seed:1520})});return g.id;})()");
                python("from cultivation_life import server\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.heavenly_court['open_election']=None\ng.player.location_id='expanse_celestial_8'\ng.sects['yaochi'].kind='sect'\ng.player.faction_id='yaochi'\ng.player.faction_contribution=231\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.player.faction_id===null && game.player.institution_affiliations.yaochi.legacy_contribution===231 && game.faction.available.every(f=>!['heavenly_court','yaochi'].includes(f.id))")),"Institution migration and sect exclusion");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    js("UtilityPanels.open('map');Array.from(document.querySelectorAll('#map-view-tabs button')).find(b=>b.textContent==='活动与据点').click();Array.from(document.querySelectorAll('.map-directory-filters button')).find(b=>b.textContent==='势力驻地').click();true");
                    check(Boolean.TRUE.equals(js("['天庭','瑶池'].every(name=>Array.from(document.querySelectorAll('.map-directory-entry')).some(r=>r.querySelector('strong').textContent===name && r.textContent.includes('机构驻地')))")),"Institution map classification "+theme);
                    js("UtilityPanels.open('relationship');Array.from(document.querySelectorAll('.contact-filters button')).find(b=>b.textContent==='机构人物').click();true");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('.contact-person').length===6 && document.querySelector('.contact-detail').textContent.includes('机构往来') && document.querySelector('#relationship-card').scrollWidth<=document.querySelector('#relationship-card').clientWidth+1")),"Institution contacts layout "+theme);
                    capture("institutions-"+theme+"-1520");
                    js("UtilityPanels.open('yaochi');true");
                    check(Boolean.TRUE.equals(js("document.querySelector('#yaochi-content').textContent.includes('旧制贡献 231')")),"Legacy contribution record");
                }
                js("UtilityPanels.open('relationship');window.__institutionTarget=document.querySelector('.contact-person[aria-pressed=true]').dataset.npcId;window.__institutionAffinity=game.world_npcs.find(n=>n.id===__institutionTarget).affinity;true");
                tapSelector("[data-contact-action=improve]");
                waitForJs("!busy && game.world_npcs.some(n=>n.id===__institutionTarget && n.affinity>__institutionAffinity)","Institution contact action");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.world_npcs.some(n=>n.id===__institutionTarget && n.contact_source==='institution' && n.affinity>__institutionAffinity)")),"Institution contact persistence");
                result.putString("institutions_scope","Six themes, institution map identity and contacts, actual affinity action, migrated contribution and sect exclusion");
            } else if(phase.equals("fusion")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'真传安卓验收',preset_id:'true_immortal',seed:1520})});return g.id;})()");
                python("from cultivation_life import server\nfrom cultivation_life.models import Technique\nfrom cultivation_life.rules import learn_technique\nimport copy\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.heavenly_court['open_election']=None\ng.player.realm_index=12\ng.player.immortal_traces=1000\ng.player.next_tribulation_age=None\nd=next(d for d in g.doctrine_state['definitions'].values() if len(d['manuals'])>=6)\nfor b in d['manuals']: learn_technique(g.player,Technique(**copy.deepcopy(b)))\nr=g.doctrine_state['player']\nr['progress'][d['id']]={'level':4,'experience':0}\nr['active']=d['id']\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                js("UtilityPanels.open('doctrine');document.querySelector('[data-fusion-id]').closest('details').open=true;true");
                tapSelector("[data-fusion-id] button:not([disabled])");
                waitForJs("game.doctrines.rows.some(r=>r.fusion && r.fusion.level===1)","Fusion creation");
                check(Boolean.TRUE.equals(js("game.player.immortal_traces===976 && game.doctrines.voisinages.some(v=>v.name.startsWith('真·'))")),"True voisinage and trace payment");
                tapSelector("[data-fusion-id] button:not([disabled])");
                waitForJs("game.doctrines.rows.some(r=>r.fusion && (r.fusion.level>1 || r.fusion.experience>0))","Fusion study advances real time");
                python("from cultivation_life import server\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.heavenly_court['open_election']=None\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    js("UtilityPanels.open('doctrine');document.querySelector('[data-fusion-id]').scrollIntoView({block:'center'});true");
                    check(Boolean.TRUE.equals(js("document.querySelector('#doctrine-card').scrollWidth<=document.querySelector('#doctrine-card').clientWidth+1")),"Fusion layout "+theme);
                    capture("fusion-"+theme+"-1520");
                    js("UtilityPanels.close('doctrine');UtilityPanels.open('yaochi');true");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('#yaochi-content optgroup').length===26 && game.yaochi.shop.filter(o=>o.id.startsWith('daluo_breakthrough_')).length===3")),"Grouped catalog and realm pills");
                    js("UtilityPanels.close('yaochi');true");
                }
                result.putString("fusion_scope","Real fusion/study, single trace payment, true voisinage persistence, four themes and grouped catalog");
            } else if(phase.equals("governance")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'故人议政验收',preset_id:'true_immortal',seed:1520})});return g.id;})()");
                python("import random\nfrom cultivation_life import server\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.heavenly_court['open_election']=None\ng.heavenly_court['player_grade']=9\ng.player.location_id='expanse_celestial_8'\ng.yaochi_state['merit']=100000\ng.player.faction_id=next(s.id for s in g.sects.values() if s.world=='celestial' and not s.extinct and s.npcs)\ne._advance_heavenly_court_unit(g,random.Random(9))\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    for(String panel:new String[]{"yaochi","heavenly-court","relationship"}) {
                        js("UtilityPanels.open('"+panel+"');true");
                        check(Boolean.TRUE.equals(js("(()=>{const e=document.querySelector('#"+panel+"-card');return !e.classList.contains('hidden')&&e.scrollWidth<=e.clientWidth+1})()")),"Governance panel overflow: "+theme+panel);
                        capture("governance-"+panel+"-"+theme+"-1520");
                    }
                }
                js("UtilityPanels.open('yaochi');window.__lockedBook=game.yaochi.shop.find(o=>o.can_lock).id;true");
                tapSelector("#yaochi-content .doctrine-book > button");
                waitForJs("game.yaochi.locked_count===1","Lock rotating stock");
                python("from cultivation_life import server\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\ng.player.age+=300\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.yaochi.shop.some(o=>o.id===window.__lockedBook&&o.locked)")),"Stock lock reload");
                tapSelector("#yaochi-content .doctrine-book .yaochi-purchase button");
                waitForJs("game.yaochi.locked_count===0","Purchase releases lock");
                js("UtilityPanels.open('heavenly-court');true");
                check(Boolean.TRUE.equals(js("document.querySelector('.court-governance').textContent.includes('主持天庭议政')")),"Autonomous government record");
                js("UtilityPanels.open('relationship');Array.from(document.querySelectorAll('.contact-filters button')).find(b=>b.textContent==='宗门同道').click();true");
                check(Boolean.TRUE.equals(js("document.querySelectorAll('.contact-person').length>0 && document.querySelectorAll('.contact-action').length===10 && !document.querySelector('#npc-contacts select')")),"Sect contact directory");
                js("window.__contactId=document.querySelector('.contact-person').dataset.npcId;true");
                tapSelector("[data-contact-action=improve]");
                waitForJs("document.querySelector('[data-contact-action=improve]').textContent.includes('本行动单位已与此人交流')","Actual contact interaction");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.faction.roster.some(n=>n.id===window.__contactId&&n.contact_actions.improve.includes('已与此人交流'))")),"Contact persistence");
                result.putString("governance_scope","Six themes, paid stock lock across refresh, purchase, automatic NPC government, categorized sect contact actions and persistence");
            } else if(phase.equals("economy-caravans")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'商队经营验收',preset_id:'core',seed:213})});return g.id;})()");
                python("from cultivation_life import server\nfrom cultivation_life.system.economy import state,caravans\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\ng.player.location_id=g.merchant_state['worlds']['human'][0]['hq']\nfor _ in range(50):\n g.player.age+=1\n state.advance_economy(g)\n caravans.advance_caravans(g,e.maps)\ng.pending_event=None\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                js("UtilityPanels.open('merchant');true");
                tapSelector(".merchant-alliance button");
                waitForJs("!busy && !!game.merchant_system.membership","Native merchant join");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    js("UtilityPanels.open('merchant');document.querySelector('.merchant-caravans').open=false;true");
                    tapSelector(".merchant-caravans summary");
                    check(Boolean.TRUE.equals(js("document.querySelector('.caravan-row').innerText.includes('周转资金') && game.merchant_system.alliances[0].caravans[0].voyages>0")),"Native freight accounts");
                    check(Boolean.TRUE.equals(js("document.querySelector('#merchant-card').scrollWidth<=document.querySelector('#merchant-card').clientWidth+1")),"Native caravan width");
                    capture("caravans-merchant-"+theme+"-"+arguments.getString("orientation","portrait"));
                    js("UtilityPanels.open('map');true");tapSelector("#map-view-tabs button[aria-controls=map-economy]");
                    js("document.querySelector('.economy-freight').open=false;true");tapSelector(".economy-freight summary");
                    check(Boolean.TRUE.equals(js("game.map.economy.freight_in+game.map.economy.freight_out>0 && document.querySelector('#map-card').scrollWidth<=document.querySelector('#map-card').clientWidth+1")),"Native local freight");
                    capture("caravans-map-"+theme+"-"+arguments.getString("orientation","portrait"));
                    async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("!busy && game.merchant_system.alliances[0].caravans[0].detail")),"Freight reload");
                }
                result.putString("caravan_scope","Four themes, native join and disclosure, same-world freight, map activity, persistence");
            } else if(phase.equals("economy-v2")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'本地经济验收',preset_id:'core',seed:213})});return g.id;})()");
                python("from cultivation_life import server\nfrom cultivation_life.rules import add_item\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.pending_event=None\nadd_item(g.player,'spirit_stone',100000000)\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    js("UtilityPanels.open('map');true");
                    tapSelector("#map-view-tabs button[aria-controls=map-economy]");
                    check(Boolean.TRUE.equals(js("document.querySelector('#map-economy').offsetHeight>0 && document.querySelector('#map-card').scrollWidth<=document.querySelector('#map-card').clientWidth+1")),"Market layout: "+theme);
                    js("window.__econRevision=game.map.economy.revision;window.__econItem=document.querySelector('.economy-good [data-trade=buy]:not(:disabled)').closest('.economy-good').dataset.itemId;true");
                    tapSelector(".economy-good [data-trade=buy]:not(:disabled)");
                    waitForJs("!busy && game.map.economy.revision>window.__econRevision","Native market purchase");
                    check(Boolean.TRUE.equals(js("game.map.economy.rows.find(r=>r.id===window.__econItem).held>0")),"Purchase inventory");
                    js("window.__econRevision=game.map.economy.revision;document.querySelector('.economy-good[data-item-id=\"'+window.__econItem+'\"] [data-trade=sell]').id='native-economic-sale';true");
                    tapSelector("#native-economic-sale");
                    waitForJs("!busy && game.map.economy.revision>window.__econRevision","Native market sale");
                    async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("game.map.economy.turnover>0 && !busy")),"Economic persistence");
                    capture("economy-v2-"+theme+"-"+arguments.getString("orientation","portrait"));
                }
                result.putString("economy_v2_scope","Four themes, native market tab and buy/sell taps, no overflow, persistence");
            } else if(phase.equals("economy")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'瑶池金光验收',preset_id:'true_immortal',seed:1520})});return g.id;})()");
                python("from cultivation_life import server\nfrom cultivation_life.rules import add_item\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.heavenly_court['open_election']=None\ng.player.location_id='expanse_celestial_8'\ng.player.immortal_body['level']=20\ng.yaochi_state['merit']=100000\nadd_item(g.player,'great_sun_divine_light',8)\nadd_item(g.player,'spirit_stone',100000)\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    for(String panel:new String[]{"golden-light","yaochi"}) {
                        js("UtilityPanels.open('"+panel+"');true");
                        check(Boolean.TRUE.equals(js("(()=>{const e=document.querySelector('#"+panel+"-card');return !e.classList.contains('hidden') && e.scrollWidth<=e.clientWidth+1})()")),"New panel overflow: "+theme+panel);
                        capture("economy-"+panel+"-"+theme+"-1520");
                    }
                }
                js("UtilityPanels.open('golden-light');true");tapSelector("#golden-light-content button");
                waitForJs("game.golden_light.rank===2 && game.golden_light.resistance===.02","Golden light tempering");
                js("UtilityPanels.open('yaochi');true");tapSelector("#yaochi-content [data-offer-id=great_sun_divine_light] button");
                waitForJs("game.yaochi.merit===99980","Merit shop purchase");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.golden_light.rank===2 && game.yaochi.merit===99980")),"Gold and merit persistence");
                python("from cultivation_life import server\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.player.location_id='ascension_terrace'\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");js("UtilityPanels.open('map');true");
                check(Boolean.TRUE.equals(js("document.querySelector('.teleport-route select')===null && document.querySelector('.teleport-methods').textContent.includes('伪造')")),"Method-first forged teleport");
                tapSelector(".teleport-controls > button:nth-of-type(2)");
                waitForJs("game.map.teleport.temporary.status==='pending'","Temporary pass application");
                python("from cultivation_life import server\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.player.age+=100\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");js("UtilityPanels.open('map');Array.from(document.querySelectorAll('.teleport-methods button')).find(b=>b.textContent==='持临时通行证').click();true");
                tapSelector(".teleport-route button");waitForJs("game.player.location_id!=='ascension_terrace'","Temporary pass teleport");
                result.putString("economy_scope","Six themes, real gold tempering and merit shop taps, persistence, forged method and delayed single-use pass");
            } else if(phase.equals("upper")) {
                for(String world:new String[]{"asura","nether","reincarnation"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'三界验收',spirit_root:'supreme_metal',path:'dao',seed:1520})});return g.id;})()");
                    python("from cultivation_life import server\nfrom cultivation_life.rules import opportunity_required\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\np=g.player\np.world="+JSONObject.quote(world)+"\np.path={'asura':'demonic','nether':'monster','reincarnation':'ghost'}[p.world]\np.realm_index=9\np.layer=1\np.lifespan=None\np.location_id=e.maps.normalize_location(p.world,None)\np.opportunity=opportunity_required(p)*3\ng.pending_event=None\ne.store.save(g)");
                    async("loadGame("+JSONObject.quote(id)+")");
                    for(String theme:new String[]{"a","b","d","f"}) {
                        js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                        check(Boolean.TRUE.equals(js("!game.player.opportunity_unbounded && !document.querySelector('#opportunity-text').textContent.includes('无尽') && document.querySelector('#upper-progression-note').textContent.includes(game.player.world==='nether'?'血脉进化':'普通修行')")),"Upper progression routing: "+world+theme);
                        check(Boolean.TRUE.equals(js("(()=>{const e=document.querySelector('#upper-progression-note');return e.scrollWidth<=e.clientWidth+1})()")),"Upper progression overflow");
                        capture("upper-"+world+"-"+theme+"-1520");
                    }
                    if(!world.equals("nether")) {
                        tapSelector("#breakthrough-action");waitForJs("!busy && game.player.opportunity<game.player.opportunity_required","Ordinary breakthrough did not resolve");
                        async("loadGame("+JSONObject.quote(id)+")");
                        check(Boolean.TRUE.equals(js("game.player.layer<=2 && game.player.realm_index===9")),"Ordinary breakthrough persistence");
                    }
                }
                check(Boolean.TRUE.equals(js("TutorialHandbook.build(configData,game).some(c=>c.id==='roots') && TutorialHandbook.build(configData,game).some(c=>c.id==='upper-worlds')")),"Missing upper/root handbook");
                result.putString("upper_scope","Three worlds, four themes, finite opportunity, DLC routing, native breakthrough and persistence, root handbook");
            } else if(phase.equals("trials")) {
                python("from cultivation_life.system.doctrine.voisinage_training import multiplier,base_multiplier\nassert [round(multiplier(n),2) for n in (8,9,10,11,12,13)]==[2.54,2.76,3.06,3.36,3.66,4.55]\nassert round(base_multiplier(13),2)==3.64");
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'天域培养验收',preset_id:'true_immortal',seed:7429})});return g.id;})()");
                python("from cultivation_life import server\nfrom cultivation_life.models import Technique\nimport copy\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.heavenly_court['open_election']=None\ng.player.opportunity=1e12\ng.player.immortal_traces=100000\ng.player.combat_plan={'manual':True,'stance':'guard','investment':40}\nd=next(iter(g.doctrine_state['definitions'].values()))\nk=d['id']\ng.player.known_techniques.append(Technique(**copy.deepcopy(d['manuals'][0])))\nr=g.doctrine_state['player']\nr['progress'][k]={'level':4,'experience':0}\nr['active']=k\nr['voisinage_training'][k]={'rank':4,'stability':10}\ng.player.immortal_aperture['current']=g.player.immortal_aperture['capacity']\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    js("UtilityPanels.open('voisinage');document.querySelector('#voisinage-content .doctrine-compact').open=true;true");Thread.sleep(500);
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('.voisinage-stages>span').length===4 && document.querySelector('#voisinage-content').textContent.includes('初成4层') && document.querySelector('#voisinage-card').scrollWidth<=document.querySelector('#voisinage-card').clientWidth+1")),"Trial stage layout: "+theme);
                    capture("trials-"+theme+"-1520");
                    sendKeyDownUpSync(android.view.KeyEvent.KEYCODE_BACK);
                }
                js("UtilityPanels.open('voisinage');Array.from(document.querySelectorAll('#voisinage-content button')).find(b=>b.textContent.includes('引动反噬')).setAttribute('data-trial-start','true');true");
                tapSelector("[data-trial-start]");
                waitForJs("!busy && game.pending_event?.id==='EVT_IMMORTAL_TRIAL_VOISINAGE_BACKLASH'","Backlash did not start");
                js("UtilityPanels.close('voisinage');true");
                async("mutate('/api/games/'+game.id+'/choice',{choice_id:'fight'})");
                check(Boolean.TRUE.equals(js("game.last_combat_report.result==='victory' && game.last_combat_report.total_rounds===5 && game.doctrines.voisinages.some(f=>f.cultivation.rank===5)")),"Five-round backlash victory");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.last_combat_report.total_rounds===5 && game.doctrines.voisinages.some(f=>f.cultivation.rank===5)")),"Trial persistence");
                check(Boolean.TRUE.equals(js("TutorialHandbook.build(configData,game).some(c=>c.id==='immortal-trials' && JSON.stringify(c).includes('战前准备') && !JSON.stringify(c).includes('复制'))")),"Missing trial handbook");
                capture("trials-victory-1520");
                result.putString("trials_scope","Six themes; native training tap and back; five-round field-only backlash; real growth and reload persistence; unlimited three-corpses handbook");
            } else if(phase.equals("tutorial")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("showStart();document.querySelector('[data-theme-picker=start] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'亲手问道',spirit_root:'supreme_wood',path:'dao',seed:1520,tutorial_enabled:true})});return g.id;})()");
                    async("loadGame("+JSONObject.quote(id)+")");js("window.__tutorialAge=game.player.age");
                    for(int i=0;i<32;i++) {
                        String step=(String)js("game.tutorial.guide.step");
                        check(Boolean.TRUE.equals(js("TutorialGuide.isGuiding()")),"Guide missing: "+step);
                        if(step.equals("gain")) {
                            sendKeyDownUpSync(android.view.KeyEvent.KEYCODE_BACK);
                            waitForJs("!busy && !game.tutorial.enabled && !TutorialGuide.isGuiding()","Native back did not pause");
                            tapSelector("#action-card [data-tutorial-open]");waitForJs("document.querySelector('#tutorial-dialog').open","Guide menu missing");
                            tapSelector("#tutorial-start");waitForJs("!busy && game.tutorial.enabled && TutorialGuide.isGuiding()","Resume failed");
                            check(Boolean.TRUE.equals(js("game.tutorial.guide.step==='gain'")),"Resume lost step");
                        }
                        if(step.equals("practice") || step.equals("join")) capture("guide-"+theme+"-"+step+"-1520");
                        check(Boolean.TRUE.equals(js("(()=>{const r=document.querySelector('.tutorial-coach').getBoundingClientRect();return r.right<=innerWidth+1 && r.bottom<=innerHeight+1;})()")),"Coach outside viewport: "+step);
                        if(Boolean.TRUE.equals(js("!document.querySelector('#guide-next').hidden"))) tapSelector("#guide-next");
                        else {
                            if(step.equals("mentor_choice")) tapSelector("[data-guide-choice=guide_accept]");
                            else {
                                check(Boolean.TRUE.equals(js("(()=>{document.querySelectorAll('[data-native-guide-target]').forEach(n=>n.removeAttribute('data-native-guide-target'));const target=Array.from(document.querySelectorAll(TutorialSteps[game.tutorial.guide.step].target)).find(n=>{const r=n.getBoundingClientRect();return r.width>0&&r.height>0&&!n.closest('.hidden')&&(game.tutorial.guide.step!=='join'||n.dataset.factionId===document.querySelector('#guide-sect-select').value);});if(!target||target.disabled)return false;target.setAttribute('data-native-guide-target','true');return true;})()")),"Missing live target: "+step);
                                tapSelector("[data-native-guide-target]");
                            }
                        }
                        waitForJs("!busy && (game.tutorial.guide.step!=="+JSONObject.quote(step)+" || game.tutorial.guide.completed)","Real tap did not advance: "+theme+" "+step);
                        check(Boolean.TRUE.equals(js("game.player.age===__tutorialAge")),"Teaching advanced time");
                    }
                    python("from cultivation_life import server\ng=server.ENGINE.store.load("+JSONObject.quote(id)+")\nassert g.player.master['realm_index']==3\nassert g.player.faction_id in g.sects\nassert g.player.tutorial_state['guide_completed']\nassert len([h for h in g.history if h.event_id=='SYS_TUTORIAL_MENTOR'])==2");
                    async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("!TutorialGuide.isGuiding() && game.faction.member && game.player.age===__tutorialAge")),"Guide completion persistence");
                }
                result.putString("tutorial_scope","Six themes; live native taps with spotlight and arrows; deterministic cultivation, treasure, technique, master and sect; native back pause/resume; no elapsed time; reload persistence");
            } else if(phase.equals("save-transfer")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'安卓长卷验收',spirit_root:'supreme_wood',path:'buddhist',seed:1450})});return g.id;})()");
                python("from cultivation_life import server\nimport json,copy\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.player.realm_index=4\ng.player.layer=1\ng.player.age=330\ng.player.lifespan=2000\nd=g.to_dict()\nt=d['history'][0]\nd['history']=[{**copy.deepcopy(t),'age':i,'summary':f'第{i}年，修士于山门往返、闭关、游历，记录功法与人间事。'*8,'state_diff':{'npc_id':f'npc_{i%1000}','opportunity':i*3.2}} for i in range(12000)]\nraw=json.dumps(d,ensure_ascii=False,indent=2)\nassert len(raw.encode())>10000000\ne.store._path(g.id).write_text(raw,encoding='utf-8')\nserver._transfer_test_original=d");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("showStart();document.querySelector('[data-theme-picker=start] [data-theme-choice="+theme+"]').click()");
                    async("GameThemes.saved");
                    async("SaveTransfer.exportSave("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("!SaveTransfer.isWorking() && document.querySelector('#transfer-code').value.startsWith('FSWDP1.')")),"Large export did not split");
                    js("window.__segments=[]");
                    while(true) {
                        tapSelector("#transfer-copy");
                        waitForJs("document.querySelector('#transfer-status').textContent.includes('已复制')","Native copy failed");
                        waitForJs("AndroidGame.readSaveCode()===document.querySelector('#transfer-code').value","Clipboard content did not match the current segment");
                        js("__segments.push(AndroidGame.readSaveCode())");
                        if(Boolean.TRUE.equals(js("document.querySelector('#transfer-next').disabled"))) break;
                        js("window.__previousSegment=document.querySelector('#transfer-code').value");
                        tapSelector("#transfer-next");
                        waitForJs("document.querySelector('#transfer-code').value!==__previousSegment","Segment navigation did not complete");
                    }
                    js("document.querySelector('#transfer-close').click();SaveTransfer.openImport()");
                    int count=((Number)js("__segments.length")).intValue();
                    for(int i=count-1;i>=0;i--) {
                        check(Boolean.TRUE.equals(js("AndroidGame.copySaveCode(__segments["+i+"])")),"Native clipboard write failed");
                        tapSelector("#transfer-paste");
                        waitForJs("document.querySelector('#transfer-code').value===__segments["+i+"]","Native paste changed text");
                        tapSelector("#transfer-preview");
                        waitForJs("!SaveTransfer.isWorking() && !document.querySelector('#transfer-status').textContent.startsWith('已粘贴')","Import preview stalled");
                    }
                    check(Boolean.TRUE.equals(js("document.querySelector('#transfer-status').textContent.includes('校验通过')")),"Large preview failed: "+js("document.querySelector('#transfer-status').textContent"));
                    check(Boolean.TRUE.equals(js("document.querySelector('#transfer-import').disabled")),"Overwrite not confirmed");
                    check(Boolean.TRUE.equals(js("document.querySelector('#save-transfer-dialog').scrollWidth<=document.querySelector('#save-transfer-dialog').clientWidth+1")),"Dialog overflow");
                    capture("save-import-"+theme+"-1450");
                    tapSelector("#transfer-replace-check");tapSelector("#transfer-import");
                    // Restoring >10MB and refreshing the accumulated save list is
                    // a file operation, not a short interactive state change.
                    waitForJs("!SaveTransfer.isWorking() && document.querySelector('#transfer-status').textContent.includes('已恢复')","Large save restore failed",60000);
                    python("from cultivation_life import server\nimport json\nassert json.loads(server.ENGINE.store._path("+JSONObject.quote(id)+").read_bytes())==server._transfer_test_original");
                    js("document.querySelector('#transfer-close').click()");
                }
                String incoming=assetText("from-windows.txt");
                js("window.__windowsCode="+JSONObject.quote(incoming));
                String imported=(String)async("(async()=>{const payload=await SaveCode.decode(__windowsCode);const p=await api('/api/save-transfer/preview',{method:'POST',body:JSON.stringify({payload})});const r=await api('/api/save-transfer/import',{method:'POST',body:JSON.stringify({payload,existing_hash:p.existing_hash})});return r.id;})()");
                String outgoing=(String)async("(async()=>{const r=await api('/api/save-transfer/export',{method:'POST',body:JSON.stringify({id:"+JSONObject.quote(imported)+"})});return SaveCode.encode(r.payload);})()");
                File output=new File(getTargetContext().getExternalFilesDir(null),"verification/from-android-"+baseVersion.replace(".", "")+".txt");
                try(FileOutputStream stream=new FileOutputStream(output)) { stream.write(outgoing.getBytes(StandardCharsets.UTF_8)); }
                result.putString("transfer_scope","Six themes; native clipboard; >10MB JSON; reversed chunks; confirmed replacement; Windows to Android import and return export");
            } else if(phase.equals("immortal")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'仙脉仙躯验收',preset_id:'true_immortal',seed:1470})});return g.id;})()");
                python("from cultivation_life import server\nfrom cultivation_life.rules import add_item,max_hp,max_mp\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.active_trial=None\ng.heavenly_court['open_election']=None\ng.player.next_tribulation_age=None\ng.player.opportunity=10**9\ng.player.immortal_traces=10000\ng.player.immortal_vein_pity={'9:1':100,'9:2':100,'9:3':100}\nadd_item(g.player,'spirit_stone',10**8)\ng.player.hp=max_hp(g.player)*.6\ng.player.mp=max_mp(g.player)*.6\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("document.querySelector('[data-panel-target=voisinage]').classList.contains('hidden') && !document.querySelector('[data-panel-target=immortal-body]').classList.contains('hidden')")),"Immortal entry gates");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");
                    async("GameThemes.saved");
                    js("UtilityPanels.close('immortal-body');UtilityPanels.open('immortal-veins');document.querySelector('.meridian-figure').scrollIntoView({block:'center'});true");
                    check(Boolean.TRUE.equals(async("new Promise(resolve=>{const i=new Image();i.onload=()=>resolve(i.naturalWidth===1122&&i.naturalHeight===1402);i.onerror=()=>resolve(false);i.src='/assets/immortal-anatomy.png'})")),"Packaged immortal contour artwork loads");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('.meridian-node .atlas-node-disc').length===27 && document.querySelector('#immortal-veins-card').scrollWidth<=document.querySelector('#immortal-veins-card').clientWidth+1")),"Meridian layout: "+theme);
                    check(Boolean.TRUE.equals(js("getComputedStyle(document.querySelector('#hud-hp .hud-track i')).backgroundImage.includes('linear-gradient') && document.querySelector('#hud-power').textContent.includes('仙痕')")),"Intrinsic resource and trace HUD: "+theme);
                    capture("immortal-meridians-"+theme);
                    js("UtilityPanels.close('immortal-veins');UtilityPanels.open('immortal-body');true");
                    check(Boolean.TRUE.equals(js("game.doctrines.immortal_body.level===1 && document.querySelector('#immortal-body-card').scrollWidth<=document.querySelector('#immortal-body-card').clientWidth+1")),"Body prerequisites: "+theme);
                    capture("immortal-body-"+theme);
                    js("UtilityPanels.close('immortal-body');UtilityPanels.open('immortal-aperture');true");
                    check(Boolean.TRUE.equals(js("game.aperture.current===300 && document.querySelector('.aperture-orb')!==null && document.querySelector('#hud-mp').title.includes('转化')")),"Aperture reservoir: "+theme);
                    capture("immortal-aperture-"+theme);
                    js("UtilityPanels.close('immortal-aperture');true");
                }
                js("UtilityPanels.close('immortal-body');UtilityPanels.open('immortal-veins');true");
                for(int n=1;n<=3;n++) {
                    tapSelector("#immortal-veins-content button");
                    waitForJs("game.doctrines.veins.opened==="+n,"Tap to open vein "+n);
                    check(Boolean.TRUE.equals(js("game.player.layer===1")),"Veins auto-promoted realm");
                }
                python("from cultivation_life import server\nfrom cultivation_life.rules import add_item\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.player.body_training=100\ng.player.immortal_body={'level':19,'failures':100}\ng.player.location_id='expanse_celestial_8'\ng.yaochi_state['merit']=10000\nadd_item(g.player,'immortal_jade_herb',1000)\nadd_item(g.player,'nine_leaf_immortal_lingzhi',1000)\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                async("mutate('/api/games/'+game.id+'/immortal-action',{action:'buy_body_manual',supply_id:'jade_marrows'})");
                js("UtilityPanels.close('immortal-veins');UtilityPanels.open('immortal-body');true");
                tapSelector("#immortal-body-content button:last-child");
                waitForJs("game.doctrines.immortal_body.level===20 && game.doctrines.immortal_body.golden_light","Body level20 golden light");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.doctrines.immortal_body.level===20 && game.player.immortal_traces>0 && !game.player.inventory.some(i=>i.id==='immortal_trace')")),"Immortal save persistence");
                capture("immortal-golden-light");
                result.putString("immortal_scope","Six themes, meridian circles, hidden voisinage entry, intrinsic bars, trace counter, actual tap opening three veins without automatic realm promotion, immortal body level20 and persistence");
            } else if(phase.equals("minor")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'邻域预案验收',preset_id:'true_immortal',seed:1471})});return g.id;})()");
                python("from cultivation_life import server\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.heavenly_court['open_election']=None\ng.player.layer=4\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.aperture.capacity===2000 && game.aperture.current===300")),"Stage capacity must conserve current");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    async("mutate('/api/games/'+game.id+'/settings',{setting:'manual_combat_plan',enabled:true})");
                    int investment=37+"abdf".indexOf(theme);
                    js("(()=>{UtilityPanels.open('combat-plan');const n=document.querySelector('[aria-label=每轮追加仙力]');n.value='"+investment+"';return true;})()");
                    check(Boolean.TRUE.equals(js("!document.querySelector('[data-panel-target=combat-plan]').classList.contains('hidden') && document.querySelector('#combat-plan-card').scrollWidth<=document.querySelector('#combat-plan-card').clientWidth+1")),"Manual plan layout");
                    tapSelector("#combat-plan-content button[type=submit]");waitForJs("!busy && game.combat_plan.investment==="+investment,"Saved plan");capture("minor-plan-"+theme);
                    js("UtilityPanels.open('map');true");
                    check(Boolean.TRUE.equals(js("!document.querySelector('[aria-label=传送目的地]')")),"Destination opened before method choice");
                    js("Array.from(document.querySelectorAll('.teleport-methods button')).find(b=>b.textContent.includes('暗杀')).click();true");
                    check(Boolean.TRUE.equals(js("document.querySelector('[aria-label=传送目的地]').options.length>0")),"Missing remote destinations");
                    capture("minor-teleport-"+theme);
                    python("from cultivation_life import server\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.player.world='spirit'\ng.player.location_id=e.maps.default_location('spirit')\ng.player.sealed_cultivation={'realm_index':9,'layer':4}\ng.player.realm_index=8\ne.store.save(g)");
                    async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("game.player.resource_kind==='mana' && !document.querySelector('#hud-mp .hud-values strong').textContent.endsWith('%') && document.querySelector('#mp-meter').classList.contains('blue')")),"Lower-world MP");
                    python("from cultivation_life import server\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.player.world='celestial'\ng.player.location_id=e.maps.default_location('celestial')\ng.player.realm_index=9\ng.player.sealed_cultivation=None\ne.store.save(g)");
                    async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("document.querySelector('#hud-mp .hud-values strong').textContent.endsWith('%') && document.querySelector('#mp-meter').classList.contains('purple')")),"Returned immortal conversion");
                    async("mutate('/api/games/'+game.id+'/settings',{setting:'manual_combat_plan',enabled:false})");
                    check(Boolean.TRUE.equals(js("document.querySelector('[data-panel-target=combat-plan]').classList.contains('hidden') && game.combat_plan.investment==="+investment)),"Automatic plan visibility/persistence");
                }
                result.putString("minor_scope","Six themes: stage reservoir, saved manual plan native tap, lower MP and return conversion, method-first assassination destination selector");
            } else if(phase.equals("npc-social")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'血脉长存档验收',spirit_root:'supreme_water',path:'monster',monster_species_id:'serpent',seed:1440})});return g.id;})()");
                com.chaquo.python.Python.getInstance().getModule("builtins").callAttr("exec",
                    "from cultivation_life import server\nfrom cultivation_life.system.monster_bloodline_system import grant_random_species_bloodline_trait\nfrom cultivation_life.system.possession_system import advance_player_age\nimport random\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.player.realm_index=4\ng.player.layer=1\ng.player.lifespan=2000\nrng=random.Random(1440)\nfor _ in range(310):\n advance_player_age(g.player)\n e._annual_sect_update(g,rng)\n e._annual_world_npc_update(g,rng)\ng.pending_event=None\ng.active_trial=None\ngrant_random_species_bloodline_trait(g.player,rng)\ne.store.save(g)",
                    com.chaquo.python.Python.getInstance().getModule("builtins").callAttr("dict"));
                async("loadGame("+JSONObject.quote(id)+")");
                js("UtilityPanels.open('bloodline')");
                Thread.sleep(500);
                tapSelector("#bloodline-card .bloodline-detail summary");
                waitForJs("document.querySelector('#bloodline-card .bloodline-detail').open","Bloodline tap did not open description");
                check(Boolean.TRUE.equals(js("document.querySelector('#bloodline-card .bloodline-detail p').textContent.length>8")),"Empty bloodline rules");
                capture("bloodline-tap-1440");
                js("UtilityPanels.close('bloodline');window.__beforeAge=game.player.age");
                long started=System.nanoTime();
                async("(async()=>{await mutate('/api/games/'+game.id+'/advance',{action:'rest',years:1});return true})()");
                result.putString("long_save_action_ms",String.valueOf((System.nanoTime()-started)/1000000));
                check(Boolean.TRUE.equals(js("game.player.age>__beforeAge && game.player.realm_index===4")),"Long save action failed");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.player.age>__beforeAge")),"Long save progress not persisted");
                capture("long-save-1440");
            } else if(phase.equals("commission")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'输入法委托验收',preset_id:'core',seed:1412})});return g.id;})()");
                // Test APK only: place this newly created test character at its alliance HQ.
                com.chaquo.python.Python.getInstance().getModule("builtins").callAttr("exec",
                    "from cultivation_life import server\nfrom cultivation_life.rules import add_item\ng=server.ENGINE._load("+JSONObject.quote(id)+")\ng.player.location_id=g.merchant_state['worlds']['human'][0]['hq']\nadd_item(g.player,'spirit_stone',10**12)\nserver.ENGINE.store.save(g)",
                    com.chaquo.python.Python.getInstance().getModule("builtins").callAttr("dict"));
                async("loadGame("+JSONObject.quote(id)+")");
                async("mutate('/api/games/'+game.id+'/merchant-action',{action:'join',alliance_id:game.merchant_system.alliances[0].id})");
                js("UtilityPanels.open('merchant');const form=document.querySelector('.merchant-post');form.parentElement.open=true;const kind=form.querySelector('[aria-label=委托类型]');kind.value='formation';kind.dispatchEvent(new Event('change'));true");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");
                    async("GameThemes.saved");
                    enterCommissionNumber("杀势最低要求","0.25");
                    enterCommissionNumber("杀势最高要求","99.75");
                    waitForJs("!document.querySelector('.merchant-post button[type=submit]').disabled","No valid commission quote: "+theme);
                    capture("commission-ime-"+theme);
                }
                js("document.querySelector('.merchant-post button[type=submit]').click()");
                waitForJs("game.merchant_system.posted.length===1 && !busy","Commission was not published");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.merchant_system.posted[0].spec.requirements.kill===0.25 && game.merchant_system.posted[0].spec.maxima.kill===99.75")),"Saved bounds differ from IME input");
                capture("commission-published");
            } else if(phase.equals("quickstart")) {
                try(java.io.InputStream input=getContext().getAssets().open("quick_start_regression.js")) {
                    java.io.ByteArrayOutputStream buffer=new java.io.ByteArrayOutputStream();
                    byte[] chunk=new byte[4096];int length;
                    while((length=input.read(chunk))!=-1) buffer.write(chunk,0,length);
                    js(new String(buffer.toByteArray(),StandardCharsets.UTF_8));
                }
                for(String preset:new String[]{"demonic_void","core","void","ghost_void","monster_void","confucian_void","buddhist_void"}) {
                    async("QuickStartProbe.run('"+preset+"')");
                    if(preset.equals("demonic_void")) capture("quickstart-demonic-void");
                }
            } else if(phase.equals("world")) {
                async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'山河界壁验收',spirit_root:'supreme_metal',path:'dao',seed:1410,preset_id:'core'})});render(g);return g.id;})()");
                check(Boolean.TRUE.equals(js("game.map.locations.some(p=>p.factions && p.factions.length>0)")),"Missing faction map addresses");
                try(java.io.InputStream input=getContext().getAssets().open("world_update_layout.js")) {
                    java.io.ByteArrayOutputStream buffer=new java.io.ByteArrayOutputStream();
                    byte[] chunk=new byte[4096];int length;
                    while((length=input.read(chunk))!=-1) buffer.write(chunk,0,length);
                    js(new String(buffer.toByteArray(),StandardCharsets.UTF_8));
                }
                String before=(String)js("JSON.stringify(game)");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");
                    async("GameThemes.saved");
                    for(String panel:new String[]{"map","growth"}) {
                        js("WorldUpdateProbe.mount('"+panel+"')");Thread.sleep(1100);
                        String failures=(String)js("JSON.stringify(WorldUpdateProbe.check('"+panel+"'))");
                        check("[]".equals(failures),theme+" / "+panel+": "+failures);
                        capture("world-1410-"+panel+"-"+theme);
                        js("document.querySelector('#player-details-dialog').close();UtilityPanels.close('map')");
                    }
                }
                check(before.equals(js("JSON.stringify(game)")),"World rendering changed game state");
            } else if(phase.equals("family")) {
                async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'家族归墟验收',spirit_root:'supreme_metal',path:'dao',seed:1400,preset_id:'core'})});render(g);return g.id;})()");
                check(Boolean.TRUE.equals(js("game.player.inventory.some(i=>i.id==='heroic_progeny_elixir' && i.quantity===1)")),"Missing starter elixir");
                async("(async()=>{await mutate('/api/games/'+game.id+'/use-item',{item_id:'heroic_progeny_elixir'});return true})()");
                check(Boolean.TRUE.equals(js("game.player.guaranteed_progeny && !game.player.inventory.some(i=>i.id==='heroic_progeny_elixir')")),"Elixir consumption failed");
                try(java.io.InputStream input=getContext().getAssets().open("family_guixu_layout.js")) {
                    java.io.ByteArrayOutputStream buffer=new java.io.ByteArrayOutputStream();
                    byte[] chunk=new byte[4096];int length;
                    while((length=input.read(chunk))!=-1) buffer.write(chunk,0,length);
                    js(new String(buffer.toByteArray(),StandardCharsets.UTF_8));
                }
                String before=(String)js("JSON.stringify(game)");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");
                    async("GameThemes.saved");
                    for(String panel:new String[]{"family","offer","guixu"}) {
                        js("FamilyGuixuProbe.mount('"+panel+"')");Thread.sleep(1100);
                        String failures=(String)js("JSON.stringify(FamilyGuixuProbe.check('"+panel+"'))");
                        check("[]".equals(failures),theme+" / "+panel+": "+failures);
                        if(panel.equals("family")) {
                            js("(()=>{const c=document.querySelector('#family-card'),r=c.querySelector('.family-member');c.scrollTop+=r.getBoundingClientRect().top-c.getBoundingClientRect().top-110;})()");
                            capture("family-1400-"+theme);
                        }
                        js("UtilityPanels.close('"+(panel.equals("family")?"family":"guixu")+"')");
                    }
                }
                check(before.equals(js("JSON.stringify(game)")),"Family rendering changed game state");
            } else if(phase.equals("characters")) {
                async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'人物布局验收',spirit_root:'supreme_metal',path:'dao',seed:1393,preset_id:'core'})});render(g);return g.id;})()");
                try(java.io.InputStream input=getContext().getAssets().open("character_layout.js")) {
                    java.io.ByteArrayOutputStream buffer=new java.io.ByteArrayOutputStream();
                    byte[] chunk=new byte[4096];int length;
                    while((length=input.read(chunk))!=-1) buffer.write(chunk,0,length);
                    js(new String(buffer.toByteArray(),StandardCharsets.UTF_8));
                }
                String before=(String)js("JSON.stringify(game)");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");
                    async("GameThemes.saved");
                    for(String panel:new String[]{"faction","world-npc","family","relationship","sage"}) {
                        js("CharacterLayoutProbe.mount('"+panel+"')");Thread.sleep(1100);
                        String failures=(String)js("JSON.stringify(CharacterLayoutProbe.check('"+panel+"'))");
                        check("[]".equals(failures),theme+" / "+panel+": "+failures);
                        if(panel.equals("faction")) {
                            js("(()=>{const c=document.querySelector('#faction-card'),r=document.querySelector('#faction-roster');c.scrollTop+=r.getBoundingClientRect().top-c.getBoundingClientRect().top-110;})()");
                            capture("sect-1400-"+theme);
                        }
                        js("UtilityPanels.close('"+panel+"')");
                    }
                }
                check(before.equals(js("JSON.stringify(game)")),"Character rendering changed game state");
            } else if(phase.equals("upgrade")) {
                String id=marker.getString("id",null);
                check(id!=null,"Missing upgrade verification save");
                check("f".equals(js("document.documentElement.dataset.theme")),"Theme lost during upgrade");
                async("loadGame("+JSONObject.quote(id)+")");
                check(marker.getString("age","").equals(String.valueOf(js("String(game.player.world_age)"))),"Progress lost during upgrade");
                check("安卓发行验收".equals(js("game.player.name")),"Wrong save after upgrade");
                async("document.fonts.ready");
                check(Boolean.TRUE.equals(js("document.fonts.check(\"16px 'Wendao Serif'\")")),"Offline font unavailable");
                capture("release-offline-upgrade");
            } else {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'安卓发行验收',spirit_root:'supreme_metal',path:'dao',seed:1392,preset_id:'core'})});render(g);return g.id;})()");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('#theme-open').click();document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");
                    async("GameThemes.saved");
                    js("AndroidUI.back()");
                    check(theme.equals(js("document.documentElement.dataset.theme")),"Release theme failed: "+theme);
                    check(Boolean.TRUE.equals(js("document.documentElement.scrollWidth<=innerWidth+1")),"Release overflow: "+theme);
                    capture("release-"+theme);
                }
                async("(async()=>{await mutate('/api/games/'+game.id+'/advance',{action:'cultivate',years:1});return true})()");
                check(Boolean.TRUE.equals(js("game.player.world_age>260")),"Release action did not advance");
                marker.edit().putString("id",id).putString("age",String.valueOf(js("String(game.player.world_age)"))).commit();
                js("UtilityPanels.open('map')");
                runOnMainSync(()->activity.onBackPressed());Thread.sleep(200);
                check(Boolean.TRUE.equals(js("!document.querySelector('.panel-open')")),"Native back did not close map");
                capture("release-action");
            }
            result.putString("status","passed");result.putString("phase",phase);
            result.putString("scope",BuildConfig.DEBUG ? "Debug test APK, Android 12, isolated developer verification" : "Signed release APK, Android 12, offline upgrade preservation and four themes");
            finish(Activity.RESULT_OK,result);
        } catch(Throwable failure) {
            android.util.Log.e("ReleaseVerification","Verification failed",failure);
            try {
                result.putString("guide_debug", (String)js("JSON.stringify((()=>{const n=document.querySelector('[data-native-guide-target]'),r=n?.getBoundingClientRect();return {step:game?.tutorial?.guide?.step,target:n?.outerHTML,rect:r,coach:document.querySelector('.tutorial-coach')?.getBoundingClientRect(),hit:r?document.elementFromPoint(r.left+r.width/2,r.top+r.height/2)?.outerHTML:null,dialog:Array.from(document.querySelectorAll('dialog[open]')).map(d=>d.id)};})())"));
                capture("failure-1520");
            } catch(Throwable ignored) { /* Screenshot assertions must not mask the original failure. */ }
            result.putString("status","failed");result.putString("error",failure.toString());
            finish(Activity.RESULT_CANCELED,result);
        }
    }
}

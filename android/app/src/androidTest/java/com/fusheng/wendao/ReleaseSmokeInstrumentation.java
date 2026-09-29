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
        long deadline=System.currentTimeMillis()+15000;
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
        js("document.querySelector("+quoted+").scrollIntoView({block:'center'});true");
        Thread.sleep(300);
        JSONObject point=new JSONObject((String)js("JSON.stringify((()=>{const r=document.querySelector("+quoted+").getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2,width:innerWidth}})())"));
        int[] origin=new int[2];runOnMainSync(()->web.getLocationOnScreen(origin));
        float scale=web.getWidth()/(float)point.getDouble("width");
        float x=origin[0]+(float)point.getDouble("x")*scale,y=origin[1]+(float)point.getDouble("y")*scale;
        long now=android.os.SystemClock.uptimeMillis();
        for(int action:new int[]{android.view.MotionEvent.ACTION_DOWN,android.view.MotionEvent.ACTION_UP}) {
            android.view.MotionEvent event=android.view.MotionEvent.obtain(now,android.os.SystemClock.uptimeMillis(),action,x,y,0);
            sendPointerSync(event);event.recycle();
        }
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
        js("scrollTo(0,0)");
        async("document.fonts.ready");
        CountDownLatch frame=new CountDownLatch(1);
        runOnMainSync(()->web.postVisualStateCallback(System.nanoTime(),new WebView.VisualStateCallback(){
            @Override public void onComplete(long id) { web.invalidate();frame.countDown(); }
        }));
        check(frame.await(15,TimeUnit.SECONDS),"WebView frame did not settle");
        Thread.sleep(500);
        Bitmap bitmap=getUiAutomation().takeScreenshot();
        File root=new File(getTargetContext().getExternalFilesDir(null),"verification");
        check(root.isDirectory() || root.mkdirs(),"Screenshot directory unavailable: "+root);
        try(FileOutputStream out=new FileOutputStream(new File(root,name+".png"))) {
            bitmap.compress(Bitmap.CompressFormat.PNG,100,out);
        }
        bitmap.recycle();
    }

    @Override public void onStart() {
        Bundle result=new Bundle();
        try {
            activity=startActivitySync(new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            if("portrait".equals(arguments.getString("orientation"))) runOnMainSync(()->activity.setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_PORTRAIT));
            long deadline=System.currentTimeMillis()+60000;
            while(web==null && System.currentTimeMillis()<deadline) {
                runOnMainSync(()->web=findWeb(activity.findViewById(android.R.id.content)));
                Thread.sleep(150);
            }
            check(web!=null,"Release WebView did not start");
            while(!Boolean.TRUE.equals(js("typeof configData!=='undefined' && !!configData && !!window.AndroidUI")) && System.currentTimeMillis()<deadline) Thread.sleep(150);
            async("GameThemes.ready");
            check(Boolean.TRUE.equals(js("configData.base_game.version==='1.47.1' && !configData.debug && configData.extensions.length===7 && configData.extensions.every(e=>e.status==='loaded')")),"Version, release mode or DLC mismatch");
            SharedPreferences marker=getTargetContext().getSharedPreferences("release-verification",0);
            String phase=arguments.getString("phase","initial");
            if(phase.equals("save-transfer")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'安卓长卷验收',spirit_root:'supreme_wood',path:'buddhist',seed:1450})});return g.id;})()");
                python("from cultivation_life import server\nimport json,copy\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.player.realm_index=4\ng.player.layer=1\ng.player.age=330\ng.player.lifespan=2000\nd=g.to_dict()\nt=d['history'][0]\nd['history']=[{**copy.deepcopy(t),'age':i,'summary':f'第{i}年，修士于山门往返、闭关、游历，记录功法与人间事。'*8,'state_diff':{'npc_id':f'npc_{i%1000}','opportunity':i*3.2}} for i in range(12000)]\nraw=json.dumps(d,ensure_ascii=False,indent=2)\nassert len(raw.encode())>10000000\ne.store._path(g.id).write_text(raw,encoding='utf-8')\nserver._transfer_test_original=d");
                for(String theme:new String[]{"a","b","c","d","e","f"}) {
                    js("showStart();document.querySelector('[data-theme-picker=start] [data-theme-choice="+theme+"]').click()");
                    async("GameThemes.saved");
                    async("SaveTransfer.exportSave("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("!SaveTransfer.isWorking() && document.querySelector('#transfer-code').value.startsWith('FSWDP1.')")),"Large export did not split");
                    js("window.__segments=[]");
                    while(true) {
                        tapSelector("#transfer-copy");
                        waitForJs("document.querySelector('#transfer-status').textContent.includes('已复制')","Native copy failed");
                        check(Boolean.TRUE.equals(js("AndroidGame.readSaveCode()===document.querySelector('#transfer-code').value")),"Clipboard truncation");
                        js("__segments.push(AndroidGame.readSaveCode())");
                        if(Boolean.TRUE.equals(js("document.querySelector('#transfer-next').disabled"))) break;
                        tapSelector("#transfer-next");
                    }
                    js("document.querySelector('#transfer-close').click();SaveTransfer.openImport()");
                    int count=((Number)js("__segments.length")).intValue();
                    for(int i=count-1;i>=0;i--) {
                        check(Boolean.TRUE.equals(js("AndroidGame.copySaveCode(__segments["+i+"])")),"Native clipboard write failed");
                        tapSelector("#transfer-paste");
                        waitForJs("document.querySelector('#transfer-code').value===__segments["+i+"]","Native paste changed text");
                        tapSelector("#transfer-preview");
                        waitForJs("!SaveTransfer.isWorking()","Import preview stalled");
                    }
                    check(Boolean.TRUE.equals(js("document.querySelector('#transfer-status').textContent.includes('校验通过')")),"Large preview failed");
                    check(Boolean.TRUE.equals(js("document.querySelector('#transfer-import').disabled")),"Overwrite not confirmed");
                    check(Boolean.TRUE.equals(js("document.querySelector('#save-transfer-dialog').scrollWidth<=document.querySelector('#save-transfer-dialog').clientWidth+1")),"Dialog overflow");
                    capture("save-import-"+theme+"-1450");
                    tapSelector("#transfer-replace-check");tapSelector("#transfer-import");
                    waitForJs("!SaveTransfer.isWorking() && document.querySelector('#transfer-status').textContent.includes('已恢复')","Restore failed");
                    python("from cultivation_life import server\nimport json\nassert json.loads(server.ENGINE.store._path("+JSONObject.quote(id)+").read_bytes())==server._transfer_test_original");
                    js("document.querySelector('#transfer-close').click()");
                }
                String incoming=assetText("from-windows.txt");
                js("window.__windowsCode="+JSONObject.quote(incoming));
                String imported=(String)async("(async()=>{const payload=await SaveCode.decode(__windowsCode);const p=await api('/api/save-transfer/preview',{method:'POST',body:JSON.stringify({payload})});const r=await api('/api/save-transfer/import',{method:'POST',body:JSON.stringify({payload,existing_hash:p.existing_hash})});return r.id;})()");
                String outgoing=(String)async("(async()=>{const r=await api('/api/save-transfer/export',{method:'POST',body:JSON.stringify({id:"+JSONObject.quote(imported)+"})});return SaveCode.encode(r.payload);})()");
                File output=new File(getTargetContext().getExternalFilesDir(null),"verification/from-android-1471.txt");
                try(FileOutputStream stream=new FileOutputStream(output)) { stream.write(outgoing.getBytes(StandardCharsets.UTF_8)); }
                result.putString("transfer_scope","Six themes; native clipboard; >10MB JSON; reversed chunks; confirmed replacement; Windows to Android import and return export");
            } else if(phase.equals("immortal")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'仙脉仙躯验收',preset_id:'true_immortal',seed:1470})});return g.id;})()");
                python("from cultivation_life import server\nfrom cultivation_life.rules import add_item,max_hp,max_mp\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.active_trial=None\ng.heavenly_court['open_election']=None\ng.player.next_tribulation_age=None\ng.player.opportunity=10**9\ng.player.immortal_traces=10000\ng.player.immortal_vein_pity={'9:1':100,'9:2':100,'9:3':100}\nadd_item(g.player,'spirit_stone',10**8)\ng.player.hp=max_hp(g.player)*.6\ng.player.mp=max_mp(g.player)*.6\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("document.querySelector('[data-panel-target=voisinage]').classList.contains('hidden') && !document.querySelector('[data-panel-target=immortal-body]').classList.contains('hidden')")),"Immortal entry gates");
                for(String theme:new String[]{"a","b","c","d","e","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");
                    async("GameThemes.saved");
                    js("UtilityPanels.close('immortal-body');UtilityPanels.open('immortal-veins');document.querySelector('.meridian-figure').scrollIntoView({block:'center'});true");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('.meridian-node circle').length===27 && document.querySelector('#immortal-veins-card').scrollWidth<=document.querySelector('#immortal-veins-card').clientWidth+1")),"Meridian layout: "+theme);
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
                python("from cultivation_life import server\nfrom cultivation_life.rules import add_item\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.player.body_training=100\ng.player.immortal_body={'level':19,'failures':100}\nadd_item(g.player,'immortal_jade_herb',1000)\nadd_item(g.player,'nine_leaf_immortal_lingzhi',1000)\ne.store.save(g)");
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
                for(String theme:new String[]{"a","b","c","d","e","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    async("mutate('/api/games/'+game.id+'/settings',{setting:'manual_combat_plan',enabled:true})");
                    js("UtilityPanels.open('combat-plan');const n=document.querySelector('[aria-label=每轮追加仙力]');n.value='37';true");
                    check(Boolean.TRUE.equals(js("!document.querySelector('[data-panel-target=combat-plan]').classList.contains('hidden') && document.querySelector('#combat-plan-card').scrollWidth<=document.querySelector('#combat-plan-card').clientWidth+1")),"Manual plan layout");
                    tapSelector("#combat-plan-content button[type=submit]");waitForJs("!busy && game.combat_plan.investment===37","Saved plan");capture("minor-plan-"+theme);
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
                    check(Boolean.TRUE.equals(js("document.querySelector('[data-panel-target=combat-plan]').classList.contains('hidden') && game.combat_plan.investment===37")),"Automatic plan visibility/persistence");
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
                for(String theme:new String[]{"a","b","c","d","e","f"}) {
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
                for(String theme:new String[]{"a","b","c","d","e","f"}) {
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
                for(String theme:new String[]{"a","b","c","d","e","f"}) {
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
                for(String theme:new String[]{"a","b","c","d","e","f"}) {
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
                for(String theme:new String[]{"a","b","c","d","e","f"}) {
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
            result.putString("scope","Signed release APK, Android 12, offline upgrade preservation and six themes");
            finish(Activity.RESULT_OK,result);
        } catch(Throwable failure) {
            android.util.Log.e("ReleaseVerification","Verification failed",failure);
            result.putString("status","failed");result.putString("error",failure.toString());
            finish(Activity.RESULT_CANCELED,result);
        }
    }
}

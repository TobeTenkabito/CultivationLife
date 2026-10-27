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
        enterNumericField(".merchant-metrics input[aria-label='"+label+"']", label, value);
    }

    private void enterNumericField(String field, String label, String value) throws Exception {
        revealSubpage(field);
        String selector=JSONObject.quote(field);
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

    private void revealSubpage(String selector) throws Exception {
        String quoted=JSONObject.quote(selector);
        // Select owning subpages using real native taps before the target itself.
        for (int depth=0; depth<8; depth++) {
            boolean hidden=Boolean.TRUE.equals(js("(()=>{const node=document.querySelector("+quoted+");let hidden=null;for(let n=node;n;n=n.parentElement)if(n.hasAttribute('data-page-hidden'))hidden=n;if(!hidden)return false;let host=hidden.parentElement;while(host&&!host.querySelector(':scope>.panel-page-tabs'))host=host.parentElement;if(!host)return false;const tab=[...host.querySelector(':scope>.panel-page-tabs').children].find(b=>b.dataset.subpage===hidden.dataset.pageName);if(!tab)return false;document.querySelectorAll('[data-native-subpage]').forEach(n=>n.removeAttribute('data-native-subpage'));tab.setAttribute('data-native-subpage','1');return true;})()"));
            if (!hidden) break;
            tapSelector("[data-native-subpage]");
        }
    }

    private void waitForPanelReady(String selector) throws Exception {
        String quoted=JSONObject.quote(selector);
        waitForJs("(()=>{const panel=document.querySelector("+quoted+");if(!panel||!panel.classList.contains('panel-open')||panel.classList.contains('hidden')||panel.classList.contains('theme-feedback-active'))return false;const style=getComputedStyle(panel);return style.visibility==='visible'&&Number(style.opacity)===1&&panel.clientWidth>0;})()",
                  "Native panel did not settle: "+selector,60000);
    }

    private void waitForNativeFrame() throws Exception {
        CountDownLatch frame=new CountDownLatch(1);
        runOnMainSync(()->web.postVisualStateCallback(System.nanoTime(),new WebView.VisualStateCallback(){
            @Override public void onComplete(long id) {
                web.invalidate();
                web.postOnAnimation(()->web.postOnAnimation(frame::countDown));
            }
        }));
        check(frame.await(30,TimeUnit.SECONDS),"Native input frame did not settle");
    }

    private void tapSelector(String selector) throws Exception {
        String quoted=JSONObject.quote(selector);
        if(selector.contains("data-panel-target") || selector.equals("#battle-report-open")) {
            String group=(String)js("document.querySelector("+quoted+")?.dataset.navigationGroup||''");
            if(!group.isEmpty()) {
                if(Boolean.TRUE.equals(js("document.querySelector('#navigation-menu').open"))) {
                    String tab="[data-navigation-tab='"+group+"']";
                    if(!Boolean.TRUE.equals(js("document.querySelector("+JSONObject.quote(tab)+").getAttribute('aria-selected')==='true' || (()=>{const e=document.querySelector("+quoted+");return e && !e.closest('[hidden]') && e.getClientRects().length>0;})()"))) tapSelector(tab);
                } else tapSelector("[data-navigation-category='"+group+"']");
                waitForJs("document.querySelector('#navigation-menu').open","Navigation directory did not open");
            }
        }
        revealSubpage(selector);
        waitForJs("!document.documentElement.classList.contains('theme-switching')","Native theme did not settle",60000);
        String owner=(String)js("document.querySelector("+quoted+")?.closest('.utility-panel')?.id||''");
        if(!owner.isEmpty())waitForPanelReady("#"+owner);
        // Active parallel details are already expanded by the user's tab selection.
        if (selector.contains("summary") && Boolean.TRUE.equals(js("(()=>{const n=document.querySelector("+quoted+");return n?.tagName==='SUMMARY'&&n.parentElement.hasAttribute('data-page-name')&&n.parentElement.open;})()"))) return;
        // Observe before tutorial capture handlers intercept the intended click.
        js("window.__releaseNativeTap=false;window.__releaseNativeDownId='';window.__releaseNativeEvents=[];window.__releaseNativeRecord=e=>__releaseNativeEvents.push({type:e.type,time:performance.now(),x:e.clientX,y:e.clientY,target:e.target.outerHTML?.slice(0,300)});window.addEventListener('pointerdown',event=>{window.__releaseNativeRecord(event);window.__releaseNativeDownId=event.target.closest('[data-atlas-location]')?.dataset.atlasLocation||'';},{once:true,capture:true});window.addEventListener('pointerup',window.__releaseNativeRecord,{once:true,capture:true});window.addEventListener('click',event=>{window.__releaseNativeRecord(event);const target=document.querySelector("+quoted+"),node=target?.closest('[data-atlas-location]');window.__releaseNativeTap=!!target&&(target.contains(event.target)||(node&&node.dataset.atlasLocation===window.__releaseNativeDownId&&event.target.closest('svg')===target.closest('svg')));},{once:true,capture:true});document.querySelector("+quoted+").scrollIntoView({block:'center'});true");
        Thread.sleep(300);
        // Center within the panel's usable content, below its sticky heading.
        // Window centering can put controls underneath that heading in landscape.
        js("(()=>{const target=document.querySelector("+quoted+"),panel=target.closest('.utility-panel.panel-open');if(!panel)return;const box=panel.getBoundingClientRect(),heading=panel.querySelector(':scope > .section-title')?.getBoundingClientRect(),r=target.getBoundingClientRect(),top=Math.max(box.top,heading?.bottom||box.top)+8,bottom=Math.min(box.bottom,innerHeight)-8;if(bottom>top+20)panel.scrollTop+=(r.top+r.bottom)/2-(top+bottom)/2;})();true");
        Thread.sleep(150);
        waitForNativeFrame();
        String locate="(()=>{const target=document.querySelector("+quoted+");if(!target)return {ready:false};const r=target.getBoundingClientRect();for(const [fx,fy] of [[.5,.5],[.25,.25],[.75,.25],[.25,.75],[.75,.75]]){const x=r.left+r.width*fx,y=r.top+r.height*fy,hit=document.elementFromPoint(x,y);if(!target.disabled&&hit&&target.contains(hit))return {ready:true,x,y,width:innerWidth};}return {ready:false,rect:r.toJSON(),panel:target.closest('.utility-panel')?.className,hit:document.elementFromPoint(r.left+r.width/2,r.top+r.height/2)?.outerHTML?.slice(0,1200)};})()";
        waitForJs("("+locate+").ready===true", "Native target not clickable: "+selector+": "+js("JSON.stringify("+locate+")"));
        JSONObject point=new JSONObject((String)js("JSON.stringify("+locate+")"));
        int[] origin=new int[2];runOnMainSync(()->web.getLocationOnScreen(origin));
        float scale=web.getWidth()/(float)point.getDouble("width");
        float x=origin[0]+(float)point.getDouble("x")*scale,y=origin[1]+(float)point.getDouble("y")*scale;
        // Android's input command uses InputManager directly. UiAutomation's
        // synchronous DOWN first flushes window transactions, which can change
        // cold-start insets after these screen coordinates have been measured.
        long now=android.os.SystemClock.uptimeMillis();
        String nativeOutput;
        try(java.io.InputStream input=new android.os.ParcelFileDescriptor.AutoCloseInputStream(
                getUiAutomation().executeShellCommand("input touchscreen -d 0 tap "+Float.toString(x)+" "+Float.toString(y)))) {
            java.io.ByteArrayOutputStream output=new java.io.ByteArrayOutputStream();
            byte[] chunk=new byte[1024];int count;
            while((count=input.read(chunk))!=-1)output.write(chunk,0,count);
            nativeOutput=new String(output.toByteArray(),StandardCharsets.UTF_8);
        }
        long nativeTapMs=android.os.SystemClock.uptimeMillis()-now;
        check(!nativeOutput.contains("Error"),"Native input command failed: "+nativeOutput);
        // Android input injection returns before WebView dispatches the DOM click.
        // Let it arrive before a following tap scrolls a still-hidden panel.
        // Animated WebViews may never become idle. Wait for the actual click
        // with a deadline instead of blocking the instrumentation indefinitely.
        try {
            waitForJs("window.__releaseNativeTap===true", "Native click missing: "+selector+": "+point);
        } catch (AssertionError failure) {
            throw new AssertionError(failure.getMessage()+" native="+x+","+y+" web="+web.getWidth()+"x"+web.getHeight()+" origin="+origin[0]+","+origin[1]+" nativeTapMs="+nativeTapMs+" nativeScroll="+web.getScrollY()+" windowFocus="+web.hasWindowFocus()+" viewport="+js("JSON.stringify({width:visualViewport.width,height:visualViewport.height,scale:visualViewport.scale,offsetTop:visualViewport.offsetTop,offsetLeft:visualViewport.offsetLeft,scrollY,events:window.__releaseNativeEvents,rect:document.querySelector("+quoted+")?.getBoundingClientRect(),active:document.activeElement?.outerHTML?.slice(0,300)})"),failure);
        }
        Thread.sleep(250);
    }


    private void dragMapNative() throws Exception {
        String before=(String)js("document.querySelector('.atlas-scene').dataset.orientation");
        js("(()=>{const v=document.querySelector('.atlas-scene-viewport'),p=v.closest('.utility-panel'),h=p.querySelector(':scope > .section-title').getBoundingClientRect();p.scrollTop+=v.getBoundingClientRect().top-h.bottom-16;})()");
        Thread.sleep(150);
        JSONObject point=new JSONObject((String)js("JSON.stringify((()=>{const v=document.querySelector('.atlas-scene-viewport').getBoundingClientRect(),h=document.querySelector('#map-card > .section-title').getBoundingClientRect(),top=Math.max(v.top,h.bottom)+24,bottom=Math.min(v.bottom,innerHeight-110),x=v.left+35,y=top+8;return {x,y,toX:x+Math.min(120,v.width*.35),toY:y+Math.max(40,(bottom-y)*.75),width:innerWidth};})())"));
        int[] origin=new int[2];runOnMainSync(()->web.getLocationOnScreen(origin));
        float scale=web.getWidth()/(float)point.getDouble("width");
        long down=android.os.SystemClock.uptimeMillis();
        for(int i=0;i<=14;i++) {
            int action=i==0?android.view.MotionEvent.ACTION_DOWN:i==14?android.view.MotionEvent.ACTION_UP:android.view.MotionEvent.ACTION_MOVE;
            float t=i/14f,x=origin[0]+(float)(point.getDouble("x")+(point.getDouble("toX")-point.getDouble("x"))*t)*scale,y=origin[1]+(float)(point.getDouble("y")+(point.getDouble("toY")-point.getDouble("y"))*t)*scale;
            android.view.MotionEvent event=android.view.MotionEvent.obtain(down,android.os.SystemClock.uptimeMillis(),action,x,y,0);
            try {event.setSource(android.view.InputDevice.SOURCE_TOUCHSCREEN);check(getUiAutomation().injectInputEvent(event,true),"Native map gesture injection");} finally {event.recycle();}
            Thread.sleep(25);
        }
        waitForJs("document.querySelector('.atlas-scene').dataset.orientation!=="+JSONObject.quote(before),"Native drag must rotate freely");
    }

    private void panMapNative(boolean pinch) throws Exception {
        String before=(String)js("document.querySelector('#map-atlas .atlas-viewport svg').dataset.panX");
        String orientation=(String)js("document.querySelector('#map-atlas .atlas-viewport svg').dataset.orientation || ''");
        double zoom=((Number)js("Number(document.querySelector('#map-atlas .atlas-viewport svg').dataset.zoom)")).doubleValue();
        js("(()=>{const v=document.querySelector('.atlas-viewport'),p=v.closest('.utility-panel'),h=p.querySelector(':scope > .section-title').getBoundingClientRect();p.scrollTop+=v.getBoundingClientRect().top-h.bottom-16;})()");
        JSONObject q=new JSONObject((String)js("JSON.stringify((()=>{const v=document.querySelector('.atlas-viewport').getBoundingClientRect(),h=document.querySelector('#map-card > .section-title').getBoundingClientRect(),top=Math.max(v.top,h.bottom)+24,bottom=Math.min(v.bottom,innerHeight-110),e=document.querySelector('#map-atlas .current .atlas-dot').getBoundingClientRect();return {x:v.left+v.width*.4,y:top+20,dx:Math.min(80,v.width*.22),dy:Math.max(12,Math.min(40,(bottom-top-20)*.5)),width:innerWidth,probeX:e.x,probeY:e.y};})())"));
        int[] origin=new int[2];runOnMainSync(()->web.getLocationOnScreen(origin));
        float scale=web.getWidth()/(float)q.getDouble("width");long down=android.os.SystemClock.uptimeMillis();
        int count=pinch?2:1;
        android.view.MotionEvent.PointerProperties[] props=new android.view.MotionEvent.PointerProperties[count];
        for(int p=0;p<count;p++){props[p]=new android.view.MotionEvent.PointerProperties();props[p].id=p;props[p].toolType=android.view.MotionEvent.TOOL_TYPE_FINGER;}
        for(int step=0;step<=16;step++){
            float t=Math.min(1,Math.max(0,(step-1)/14f));
            android.view.MotionEvent.PointerCoords[] coords=new android.view.MotionEvent.PointerCoords[count];
            for(int p=0;p<count;p++){
                coords[p]=new android.view.MotionEvent.PointerCoords();
                double x=q.getDouble("x")+(pinch?(p==0?-1:1)*(35+25*t):q.getDouble("dx")*t);
                double y=q.getDouble("y")+(pinch?(p==0?-1:1)*12*t:q.getDouble("dy")*t);
                coords[p].x=origin[0]+(float)x*scale;coords[p].y=origin[1]+(float)y*scale;coords[p].pressure=1;coords[p].size=.1f;
            }
            int action=step==0?android.view.MotionEvent.ACTION_DOWN:step==16?android.view.MotionEvent.ACTION_UP:pinch&&step==1?android.view.MotionEvent.ACTION_POINTER_DOWN|(1<<android.view.MotionEvent.ACTION_POINTER_INDEX_SHIFT):pinch&&step==15?android.view.MotionEvent.ACTION_POINTER_UP|(1<<android.view.MotionEvent.ACTION_POINTER_INDEX_SHIFT):android.view.MotionEvent.ACTION_MOVE;
            int pointerCount=pinch&&(step==0||step==16)?1:count;
            android.view.MotionEvent event=android.view.MotionEvent.obtain(down,android.os.SystemClock.uptimeMillis(),action,pointerCount,props,coords,0,0,1,1,0,0,android.view.InputDevice.SOURCE_TOUCHSCREEN,0);
            try{check(getUiAutomation().injectInputEvent(event,true),"Native map pan/pinch injection");}finally{event.recycle();}
            Thread.sleep(25);
        }
        Thread.sleep(200);
        if(pinch){
            check(((Number)js("Number(document.querySelector('#map-atlas .atlas-viewport svg').dataset.zoom)")).doubleValue()>zoom,"Native pinch increases projection zoom");
            check(!orientation.equals(js("document.querySelector('#map-atlas .atlas-viewport svg').dataset.orientation || ''")),"Native two-finger twist rotates");
        }else{
            check(!before.equals(js("document.querySelector('#map-atlas .atlas-viewport svg').dataset.panX")),"Native finger must move view center");
            check(orientation.equals(js("document.querySelector('#map-atlas .atlas-viewport svg').dataset.orientation || ''")),"Single finger pans without changing angle");
            JSONObject p=new JSONObject((String)js("JSON.stringify((()=>{const r=document.querySelector('#map-atlas .current .atlas-dot').getBoundingClientRect();return {x:r.x,y:r.y};})())"));
            check(Math.abs(p.getDouble("x")-q.getDouble("probeX")-q.getDouble("dx"))<3 && Math.abs(p.getDouble("y")-q.getDouble("probeY")-q.getDouble("dy"))<3,"Native marker follows finger pixels");
        }
    }

    private void openEconomicDetails(String selector) throws Exception {
        if(Boolean.TRUE.equals(js("!!document.querySelector('.economy-overview') && !document.querySelector('.economy-overview').open"))) tapSelector(".economy-overview > summary");
        if(Boolean.TRUE.equals(js("!document.querySelector("+JSONObject.quote(selector)+").open"))) tapSelector(selector+" > summary");
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
        if(!name.startsWith("failure-")&&!Boolean.TRUE.equals(js("!!window.TutorialGuide && TutorialGuide.isGuiding()"))) js("scrollTo(0,0)");
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
            check(bitmap.compress(Bitmap.CompressFormat.PNG,100,out),"Native screenshot encoding");
            out.getFD().sync();
        }
        bitmap.recycle();
        android.util.Log.i("ReleaseSmoke", "Capture complete: " + name);
    }

    private void chooseBuilding(String prefix) throws Exception {
        String old=(String)js("game.pending_event.id");
        check(Boolean.TRUE.equals(js("(()=>{const p="+JSONObject.quote(prefix)+",i=game.pending_event.choices.findIndex(c=>c.id===p||c.id.startsWith(p));if(i<0||game.pending_event.choices[i].enabled===false)return false;document.querySelectorAll('[data-native-building-choice]').forEach(n=>n.removeAttribute('data-native-building-choice'));document.querySelectorAll('#event-choices button')[i].setAttribute('data-native-building-choice','1');return true;})()")),"Building choice unavailable: "+prefix);
        tapSelector("[data-native-building-choice]");
        waitForJs("!busy && game.pending_event?.id!=="+JSONObject.quote(old),"Native building choice did not settle: "+prefix,60000);
    }

    private void verifyBuildingVisits(Bundle result) throws Exception {
        String fixture=assetText("building_visits_release.py");
        for(String theme:new String[]{"a","b","d","f"}) {
            String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'山河原生游历',spirit_root:'heavenly',path:'dao',preset_id:'core',seed:2171})});return g.id;})()");
            python(fixture+"\nfrom cultivation_life import server\nprepare_visits(server.ENGINE,"+JSONObject.quote(id)+")");
            async("loadGame("+JSONObject.quote(id)+")");
            js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click();true");async("GameThemes.saved");
            Object age=js("game.player.age");
            tapSelector("[data-panel-target=map]");tapSelector("#map-view-tabs [aria-controls=map-locations]");
            tapSelector("#map-locations [data-building-action=temple-plan]");waitForJs("!busy&&game.buildings.inside","Native temple plan");chooseBuilding("confirm");chooseBuilding("leave");
            tapSelector("[data-panel-target=map]");tapSelector("#map-view-tabs [aria-controls=map-locations]");
            check(Boolean.TRUE.equals(js("document.querySelectorAll('#map-locations .current .building-row').length===3")),"Native text gazetteer entries");
            js("document.querySelector('#map-locations .current .building-overview').scrollIntoView({block:'start'});true");
            capture("building-visits-list-"+theme+"-"+arguments.getString("orientation","portrait"));
            tapSelector("#map-locations .current .building-row[data-building-id^='city:'] .building-title strong");
            check(Boolean.TRUE.equals(js("document.querySelector('#map-locations .current .building-row[data-building-id^=\"city:\"]').open")),"Native illustrated detail expanded");
            check(Boolean.TRUE.equals(async("(async()=>{const im=new Image();im.src='/assets/building-gazetteer-2171.png';await im.decode();return im.width===1536&&im.height===1024;})()")),"Native building atlas asset loaded");
            capture("building-visits-detail-"+theme+"-"+arguments.getString("orientation","portrait"));
            tapSelector("#map-locations .current .building-row[data-building-id^='estate:'] [data-building-action=enter]");waitForJs("!busy&&game.buildings.inside","Native industry visit");
            chooseBuilding("visit:ledger");chooseBuilding("back");chooseBuilding("visit:work");chooseBuilding("visit:resolve:work:0");chooseBuilding("back");
            chooseBuilding("visit:lesson");chooseBuilding("visit:resolve:lesson:1");chooseBuilding("back");chooseBuilding("visit:lesson");
            check(Boolean.TRUE.equals(js("!game.pending_event.choices[0].enabled&&!game.pending_event.choices[1].enabled")),"Native industry insight once");
            python(assetText("building_cities_release.py")+"\nfrom cultivation_life import server\nbuilding_followup(server.ENGINE,"+JSONObject.quote(id)+")");chooseBuilding("leave");
            check(Boolean.TRUE.equals(js("game.pending_event.id==='EVT_SECT_FIRST_WARNING_001'")),"Native earned followup survives visit");
            tapSelector("#event-choices button");waitForJs("!busy&&!game.pending_event","Native followup submitted");
            tapSelector("[data-panel-target=map]");tapSelector("#map-view-tabs [aria-controls=map-locations]");
            tapSelector("#map-locations .current .building-row[data-building-id^='temple:'] [data-building-action=enter]");waitForJs("!busy&&game.buildings.inside","Native temple visit");
            for(String activity:new String[]{"bell","pilgrims","lesson"}) {chooseBuilding("visit:"+activity);chooseBuilding("visit:resolve:"+activity+":0");chooseBuilding("back");}
            chooseBuilding("visit:lesson");check(Boolean.TRUE.equals(js("!game.pending_event.choices[0].enabled")),"Native temple insight once");chooseBuilding("leave");
            python(fixture+"\nfrom cultivation_life import server\nscenic_visit(server.ENGINE,"+JSONObject.quote(id)+")");async("loadGame("+JSONObject.quote(id)+")");
            String before=(String)js("JSON.stringify([game.player.age,game.player.hp,game.player.mp,game.player.opportunity,game.player.inventory])");
            tapSelector("[data-panel-target=map]");tapSelector("#map-view-tabs [aria-controls=map-locations]");
            tapSelector("#map-locations .current .building-row[data-building-id^='scenery:'] [data-building-action=enter]");waitForJs("!busy&&game.buildings.inside","Native scenic exploration");
            for(String activity:new String[]{"trail","weather","traces"}) {chooseBuilding("visit:"+activity);chooseBuilding("visit:resolve:"+activity+":1");chooseBuilding("back");}
            chooseBuilding("leave");
            check(before.equals(js("JSON.stringify([game.player.age,game.player.hp,game.player.mp,game.player.opportunity,game.player.inventory])")),"Native scenery grants no resources");
            check(age.equals(js("game.player.age")),"Native visits consume no years");
            check(Boolean.TRUE.equals(js("!busy&&!document.querySelector('[data-action=cultivate]').disabled&&document.documentElement.scrollWidth<=innerWidth+2")),"Native busy recovery and narrow layout");
            python(fixture+"\nfrom cultivation_life import server\ninspect_visits(server.ENGINE,"+JSONObject.quote(id)+")");
        }
        verifyCityManagement(result);
        result.putString("building_visits_scope","Four themes, text gazetteer and illustrated details, native scenery/industry/temple branches, two bounded insight claims, original books, earned followup and zero-year menus");
    }

    private void verifyCityManagement(Bundle result) throws Exception {
        String fixture=assetText("city_management_release.py");
        for(String theme:new String[]{"a","b","d","f"}) {
            String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'城市经营原生验收',spirit_root:'heavenly',path:'dao',preset_id:'core',seed:2172})});return g.id;})()");
            python(fixture+"\nfrom cultivation_life import server\nprepare_city_management(server.ENGINE,"+JSONObject.quote(id)+")");
            async("loadGame("+JSONObject.quote(id)+")");
            js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click();true");async("GameThemes.saved");
            tapSelector("[data-panel-target=map]");tapSelector("#map-view-tabs [aria-controls=map-locations]");
            tapSelector("#map-locations [data-building-action=city-plan]");waitForJs("!busy&&game.buildings.inside","Native city plan");
            chooseBuilding("city:economic");chooseBuilding("city:economic:mixed");chooseBuilding("city:build:");
            chooseBuilding("civic:main");chooseBuilding("civic:facilities");chooseBuilding("civic:exchange");chooseBuilding("civic:commit:");
            chooseBuilding("civic:settle");check(Boolean.TRUE.equals(js("!game.pending_event.choices[0].enabled")),"Native first year cannot collect");chooseBuilding("leave");
            Object age=js("game.player.age");tapSelector("[data-action=rest]");
            waitForJs("!busy&&game.player.age>"+age,"Native real rest year",60000);
            tapSelector("[data-panel-target=map]");tapSelector("#map-view-tabs [aria-controls=map-locations]");
            tapSelector("#map-locations .current [data-building-id^='city:player:'] [data-building-action=enter]");waitForJs("!busy&&game.buildings.inside","Native owned city entry");
            chooseBuilding("civic:main");chooseBuilding("civic:settle");chooseBuilding("civic:commit:");
            capture("city-management-"+theme+"-"+arguments.getString("orientation","portrait"));
            chooseBuilding("civic:settle");check(Boolean.TRUE.equals(js("!game.pending_event.choices[0].enabled")),"Native city income once per real year");chooseBuilding("leave");
            python(fixture+"\nfrom cultivation_life import server\nlandscape_management(server.ENGINE,"+JSONObject.quote(id)+")");async("loadGame("+JSONObject.quote(id)+")");
            tapSelector("[data-panel-target=map]");tapSelector("#map-view-tabs [aria-controls=map-locations]");
            tapSelector("#map-locations .current [data-building-id='scenery:human:reed_letter'] [data-building-action=enter]");waitForJs("!busy&&game.buildings.inside","Native authored scenery");
            chooseBuilding("explore:main");chooseBuilding("explore:route:0");chooseBuilding("explore:finish:0:1");
            capture("landscape-story-"+theme+"-"+arguments.getString("orientation","portrait"));
            chooseBuilding("explore:main");chooseBuilding("explore:route:1");chooseBuilding("explore:finish:1:1");chooseBuilding("leave");
            check(Boolean.TRUE.equals(js("!busy&&document.documentElement.scrollWidth<=innerWidth+2")),"Native city/story narrow layout and recovery");
            python(fixture+"\nfrom cultivation_life import server\ninspect_city_management(server.ENGINE,"+JSONObject.quote(id)+")");
        }
        result.putString("city_management_scope","Four themes: actual city foundation, facility cost, real rest year, original-account income once, authored landscape branches, persistent first ending and one unique keepsake");
    }

    private void verifyBuildings(Bundle result) throws Exception {
        String fixture=assetText("building_cities_release.py");
        for(String theme:new String[]{"a","b","d","f"}) {
            String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'城郭原生验收',spirit_root:'supreme_metal',path:'dao',preset_id:'core',seed:2170})});return g.id;})()");
            python(fixture+"\nfrom cultivation_life import server\nprepare_buildings(server.ENGINE,"+JSONObject.quote(id)+")");
            async("loadGame("+JSONObject.quote(id)+")");
            js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click();true");async("GameThemes.saved");
            Object age=js("game.player.age");
            tapSelector("[data-panel-target=map]");tapSelector("#map-view-tabs [aria-controls=map-locations]");
            tapSelector("#map-locations [data-building-action=city-plan]");waitForJs("!busy&&game.buildings.inside","Native city plan");
            chooseBuilding("city:military");chooseBuilding("city:military:mixed");
            if(theme.equals("a")) {
                python(fixture+"\nfrom cultivation_life import server\nshortage_buildings(server.ENGINE,"+JSONObject.quote(id)+")");
                tapSelector("#event-choices button");waitForJs("!busy&&!game.pending_event.choices[0].enabled","Native stale ore recovery");
                check(Boolean.TRUE.equals(js("document.querySelector('#event-choices button').disabled")),"Unavailable construction remains disabled");
                python(fixture+"\nfrom cultivation_life import server\nshortage_buildings(server.ENGINE,"+JSONObject.quote(id)+",True)");
                async("loadGame("+JSONObject.quote(id)+")");
            }
            chooseBuilding("city:build:");
            check(Boolean.TRUE.equals(js("game.buildings.rows.some(r=>r.type==='city'&&r.owner.kind==='player'&&r.level===1)")),"Native city starts at one");
            chooseBuilding("city:govern");chooseBuilding("city:commit:");chooseBuilding("city:govern");
            check(Boolean.TRUE.equals(js("!game.pending_event.choices[0].enabled")),"Native yearly government cap");chooseBuilding("back");
            chooseBuilding("city:story");chooseBuilding("city:resolve:0");chooseBuilding("back");
            capture("buildings-city-"+theme+"-"+arguments.getString("orientation","portrait"));
            chooseBuilding("management");chooseBuilding("destroy");chooseBuilding("destroy:");chooseBuilding("leave");
            tapSelector("[data-panel-target=map]");tapSelector("#map-view-tabs [aria-controls=map-atlas]");
            check(Boolean.TRUE.equals(js("Array.from(document.querySelectorAll('#map-atlas .building-row')).some(n=>n.dataset.buildingId.startsWith('city:player:')&&n.textContent.includes('遗址'))")),"Native named city ruins on overview");
            capture("buildings-ruins-"+theme+"-"+arguments.getString("orientation","portrait"));
            tapSelector("#map-atlas .building-row[data-building-id^='city:player:'] [data-building-action=manage]");
            waitForJs("!busy&&game.buildings.inside","Native ruin inspection");chooseBuilding("rebuild");chooseBuilding("rebuild:");chooseBuilding("back");
            chooseBuilding("city:story");check(Boolean.TRUE.equals(js("!game.pending_event.choices[0].enabled")),"Native rebuild cannot reset story reward");
            python(fixture+"\nfrom cultivation_life import server\nbuilding_followup(server.ENGINE,"+JSONObject.quote(id)+")");
            chooseBuilding("leave");
            check(Boolean.TRUE.equals(js("game.pending_event.id==='EVT_SECT_FIRST_WARNING_001'")),"Native earned followup retained");
            tapSelector("#event-choices button");waitForJs("!busy&&!game.pending_event","Native real followup submit");
            check(age.equals(js("game.player.age")),"Native building menus must not advance years");
            check(Boolean.TRUE.equals(js("!document.querySelector('[data-action=cultivate]').disabled && document.documentElement.scrollWidth<=innerWidth+2")),"Native busy recovery and layout");
            python(fixture+"\nfrom cultivation_life import server\ninspect_buildings(server.ENGINE,"+JSONObject.quote(id)+")");
        }
        int count=0;
        for(String world:new String[]{"human","spirit","demon","true_demon","monster_realm","phantom_underworld","hell","celestial","asura","nether","reincarnation"}) {
            int rank=(world.equals("human")||world.equals("demon"))?3:(world.equals("celestial")||world.equals("asura")||world.equals("nether")||world.equals("reincarnation"))?9:6;
            String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'十一界城事',spirit_root:'supreme_metal',path:'dao',seed:2170,custom_start:{world:"+JSONObject.quote(world)+",realm_index:"+rank+"}})});return g.id;})()");
            for(int index=0;index<2;index++) {
                python(fixture+"\nfrom cultivation_life import server\nvisit_initial_city(server.ENGINE,"+JSONObject.quote(id)+","+index+")");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.map.locations.flatMap(p=>p.buildings).filter(r=>r.type==='city').length===2")),"Two initial cities in "+world);
                tapSelector("[data-panel-target=map]");tapSelector("#map-view-tabs [aria-controls=map-locations]");
                tapSelector("#map-locations .map-location.current [data-building-action=enter]");waitForJs("!busy&&game.buildings.inside","Native initial city entry");
                chooseBuilding("city:rumor");chooseBuilding("back");chooseBuilding("city:story");chooseBuilding("city:resolve:1");chooseBuilding("back");chooseBuilding("city:story");
                check(Boolean.TRUE.equals(js("!game.pending_event.choices[0].enabled")),"Initial city reward limited in "+world);
                chooseBuilding("leave");count++;
            }
        }
        check(count==22,"Native eleven-world city coverage");
        result.putString("buildings_scope","22 city stories, four themes, real city construction and original inventory, stale material recovery, yearly government cap, named ruins, identity-preserving rebuild, bounded rewards and earned event followup; zero menu years");
    }

    private void runSoulLifecycle(Bundle result) throws Exception {
        String id=(String)async("api('/api/games',{method:'POST',body:JSON.stringify({name:'身魂原生验收',spirit_root:'supreme_metal',path:'dao',seed:320,preset_id:'core'})}).then(g=>g.id)");
        python(assetText("soul_release.py")+"\nfrom cultivation_life import server\nprepare_soul(server.ENGINE,"+JSONObject.quote(id)+")");
        async("loadGame("+JSONObject.quote(id)+")");
        tapSelector(".hud-identity");
        tapSelector("[data-soul-action=leave]");waitForJs("!busy&&game.soul.mode==='神游'","Soul leave");
        tapSelector("[data-soul-action=return]");waitForJs("!busy&&game.soul.mode==='普通'","Soul return");
        check(Boolean.TRUE.equals(js("document.querySelectorAll('#soul-details progress').length===2")),"Two personal energy bars");
        tapSelector("[data-close-dialog=player-details-dialog]");tapSelector("[data-panel-target=secret-art]");
        tapSelector("#soul-secrets [data-soul-action=study]");waitForJs("!busy&&game.soul.secrets[0].known","Second soul secret");
        tapSelector("#secret-art-toggle");tapSelector("[data-panel-target=nascent]");waitForPanelReady("#nascent-card");
        for(int count=1;count<=3;count++) {
            tapSelector("#nascent-content [data-soul-action=refine]");
            waitForJs("!busy&&(!!game.soul.second||game.soul.refining?.years==="+count+")","Real captive refinement");
        }
        check(Boolean.TRUE.equals(js("game.soul.second.id==='release-nascent'")),"Original captive identity");
        js("(()=>{const b=document.querySelector('[data-soul-action=equip]');b.parentElement.querySelector('select').value='release-soul-sword';return true;})()");
        tapSelector("[data-soul-action=equip]");waitForJs("!busy&&game.soul.second.equipment.length===1","Actual equipment transfer");
        for(String theme:new String[]{"a","b","d","f"}) {
            tapSelector("#nascent-toggle");tapSelector("#theme-open");tapSelector("[data-theme-picker=dialog] [data-theme-choice="+theme+"]");async("GameThemes.saved");tapSelector("[data-close-dialog=theme-dialog]");
            tapSelector("[data-panel-target=nascent]");waitForPanelReady("#nascent-card");
            check(Boolean.TRUE.equals(js("document.querySelector('#nascent-card').scrollWidth<=document.querySelector('#nascent-card').clientWidth+2")),"Soul panel fits native screen");
            capture("soul-lifecycle-"+theme+"-"+arguments.getString("orientation"));
        }
        tapSelector("[data-soul-action=unequip]");waitForJs("!busy&&game.soul.second.equipment.length===0","Equipment returned once");
        result.putString("soul_lifecycle_scope","Real personal energy bars, leave/return, secret study, original captive three-year refinement, equipment delivery/return and four themes; signed native portrait/landscape");
    }

    private void runAuthored(Bundle result) throws Exception {
        String id=(String)async("api('/api/games',{method:'POST',body:JSON.stringify({name:'创法原生验收',spirit_root:'supreme_metal',path:'dao',seed:310,preset_id:'core'})}).then(g=>g.id)");
        python("from cultivation_life import server\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\ng.pending_event=None\nfor t in g.player.known_techniques:t.level=9\ne.store.save(g)");
        async("loadGame("+JSONObject.quote(id)+")");
        tapSelector("[data-panel-target=authored]");waitForPanelReady("#authored-card");
        js("(()=>{const n=document.querySelector('[data-authored-input=name]');n.value='原生回澜经';n.dispatchEvent(new Event('input',{bubbles:true}));const c=document.querySelector('[data-authored-input=category]');c.value='support';c.dispatchEvent(new Event('change',{bubbles:true}));return true;})()");
        tapSelector("[data-author-add-buff]");
        js("(()=>{let s=document.querySelectorAll('.at-buff select')[1];s.value='from_round';s.dispatchEvent(new Event('change'));s=document.querySelectorAll('.at-buff select')[2];s.value='restore';s.dispatchEvent(new Event('change'));let n=document.querySelectorAll('.at-buff input')[2];n.value='3';n.dispatchEvent(new Event('input'));return true;})()");
        waitForJs("!document.querySelector('[data-author-create]').disabled","Authoring quote");
        tapSelector("[data-author-create]");waitForJs("!busy&&AuthoredTechniques.ready()&&game.authored_techniques.books.length===1","Authoring committed");
        tapSelector("[data-author-manual]");waitForJs("!busy&&AuthoredTechniques.ready()&&game.authored_techniques.revision===2","Paid manual committed");
        tapSelector("[data-author-upgrade]");waitForJs("!busy&&AuthoredTechniques.ready()&&game.authored_techniques.books[0].level===2","Manual upgrade committed");
        check(Boolean.TRUE.equals(js("document.querySelector('.at-book').textContent.includes('第3轮起')")),"Simple delayed effect is readable");
        for(String theme:new String[]{"a","b","d","f"}) {
            tapSelector("#authored-toggle");tapSelector("#theme-open");tapSelector("[data-theme-picker=dialog] [data-theme-choice="+theme+"]");async("GameThemes.saved");tapSelector("[data-close-dialog=theme-dialog]");
            tapSelector("[data-panel-target=authored]");waitForPanelReady("#authored-card");
            check(Boolean.TRUE.equals(js("document.querySelector('#authored-card').scrollWidth<=document.querySelector('#authored-card').clientWidth+2")),"Authoring panel fits native screen");
            capture("authored-"+theme+"-"+arguments.getString("orientation"));
        }
        tapSelector("#authored-toggle");tapSelector("#theme-open");
        if(!Boolean.TRUE.equals(js("document.querySelector('#theme-dialog [data-pixel-setting]').checked")))tapSelector("#theme-dialog [data-pixel-setting]");
        async("GameThemes.saved");tapSelector("[data-close-dialog=theme-dialog]");
        tapSelector("[data-panel-target=relationship]");waitForPanelReady("#relationship-card");
        js("(()=>{const n=document.querySelector('#npc-contacts input[type=search]');n.value='顾长庚';n.dispatchEvent(new Event('input',{bubbles:true}));return true;})()");
        tapSelector(".contact-person");waitForJs("!!document.querySelector('.contact-detail .npc-art-figure')","Native NPC figure");
        check(Boolean.TRUE.equals(js("['.contact-detail','.contact-hero'].every(s=>{const n=document.querySelector(s);return n.scrollWidth<=n.clientWidth+1})")),"Contact figure and text stay in frame");
        capture("authored-contact-"+arguments.getString("orientation"));tapSelector("#relationship-toggle");
        js("showStart();true");waitForJs("[...document.querySelector('#authored-lineage').options].some(o=>o.value==="+JSONObject.quote(id)+")","Current lineage selector");
        js("document.querySelector('#authored-lineage').value="+JSONObject.quote(id)+";document.querySelector('#new-game-form input[name=name]').value='原生继承验收';true");
        tapSelector("#new-game-form button[type=submit]");waitForJs("!busy&&game?.player.name==='原生继承验收'","New native playthrough",60000);
        check(Boolean.TRUE.equals(js("game.authored_techniques.books.length===1&&!game.authored_techniques.books[0].own&&game.authored_techniques.books[0].level===0")),"Inherited definition does not grant learned book");
        result.putString("authored_scope","Real create, simple round-three effect, paid manual, upgrade, one-generation new game; four themes and NPC art/text containment in native portrait/landscape");
    }

    private void runUpdate301(Bundle result) throws Exception {
        String id=(String)async("api('/api/games',{method:'POST',body:JSON.stringify({name:'换装原生验收',spirit_root:'supreme_metal',path:'dao',gender:'female',seed:301,custom_start:{world:'spirit',realm_index:7}})}).then(g=>g.id)");
        python("from cultivation_life import server\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\ng.pending_event=None\ne.store.save(g)");
        async("loadGame("+JSONObject.quote(id)+")");
        python("from cultivation_life import server\nserver._skin301_before=server.ENGINE.store.load("+JSONObject.quote(id)+").to_dict()");
        tapSelector("#theme-open");
        if(!Boolean.TRUE.equals(js("document.querySelector('#theme-dialog [data-pixel-setting]').checked")))tapSelector("#theme-dialog [data-pixel-setting]");
        async("GameThemes.saved");tapSelector("[data-close-dialog=theme-dialog]");
        for(String theme:new String[]{"a","b","d","f"}) {
            tapSelector("#theme-open");tapSelector("[data-theme-picker=dialog] [data-theme-choice="+theme+"]");async("GameThemes.saved");tapSelector("[data-close-dialog=theme-dialog]");
            tapSelector(".hud-identity");tapSelector("#character-skins summary");
            tapSelector("[data-skin-id='actor.path.dao-nascent-hero-female']");
            waitForJs("!busy&&game.player.character_skins.selected==='actor.path.dao-nascent-hero-female'&&document.querySelector('.pixel-details-art canvas').dataset.actor==='actor.path.dao-nascent-hero-female'","Native earlier unlocked skin and rendered figure");
            check(Boolean.TRUE.equals(js("document.querySelector('#player-details-dialog').scrollWidth<=document.querySelector('#player-details-dialog').clientWidth+2")),"Native skin gallery fits screen");
            capture("skins-301-"+theme+"-"+arguments.getString("orientation"));
            tapSelector("[data-skin-id='']");waitForJs("!busy&&!game.player.character_skins.selected","Native automatic skin restored");
            tapSelector("#character-skins summary");tapSelector("[data-close-dialog=player-details-dialog]");
        }
        python("from cultivation_life import server\na=server._skin301_before\nb=server.ENGINE.store.load("+JSONObject.quote(id)+").to_dict()\nfor row in (a,b):\n row.pop('updated_at',None)\n row['player'].pop('character_skins',None)\nassert a==b");
        check(Boolean.TRUE.equals(async("api('/api/visual-assets').then(c=>c.assets['base.character_manifest'].character_forms.length===8)")),"Native eight base forms registered");
        String monster=(String)async("api('/api/games',{method:'POST',body:JSON.stringify({name:'万灵原生验收',spirit_root:'supreme_earth',path:'monster',seed:301,monster_species_id:'fox',custom_start:{world:'monster_realm',realm_index:7}})}).then(g=>g.id)");
        python("from cultivation_life import server\ne=server.ENGINE\ng=e._load("+JSONObject.quote(monster)+")\ng.pending_event=None\ng.player.opportunity=999999\ne.store.save(g)");
        async("loadGame("+JSONObject.quote(monster)+")");tapSelector("[data-panel-target=civilizations]");
        waitForJs("!!document.querySelector('.mc-region')","Native redesigned atlas loaded");
        tapSelector("[data-civilization-action=observe]");waitForJs("!busy&&!!document.querySelector('.mc-species')","Native actual ecology observation");
        check(Boolean.TRUE.equals(js("document.querySelector('#civilizations-card').scrollWidth<=document.querySelector('#civilizations-card').clientWidth+2")),"Native ecology panel fits screen");
        capture("ecology-301-"+arguments.getString("orientation"));
        result.putString("update301_scope","Four-theme actual skin selection, earlier form, rendered figure, unchanged gameplay, eight base forms and real ecology observation; native portrait/landscape");
    }

    private void runVisualUi(Bundle result) throws Exception {
        String id=(String)async("api('/api/games',{method:'POST',body:JSON.stringify({name:'新版原生验收',spirit_root:'heavenly',path:'dao',seed:322,preset_id:'core'})}).then(g=>g.id)");
        python(assetText("visual_release.py")+"\nfrom cultivation_life import server\nprepare_visual_release(server.ENGINE,"+JSONObject.quote(id)+")");
        async("loadGame("+JSONObject.quote(id)+")");
        js("window.__visualBefore=JSON.stringify(game);true");
        tapSelector("#theme-open");
        if(!Boolean.TRUE.equals(js("document.querySelector('#theme-dialog [data-pixel-setting]').checked")))tapSelector("#theme-dialog [data-pixel-setting]");
        async("GameThemes.saved");tapSelector("[data-close-dialog=theme-dialog]");
        waitForJs("!!PixelLibrary.catalog","Native asset catalog");
        check(Boolean.TRUE.equals(js("JSON.stringify(game)===__visualBefore")),"New view must not change gameplay state");
        tapSelector("[data-panel-target=inventory]");tapSelector("[data-pixel-item=guixu_canghai_equipment_01]");
        waitForJs("document.querySelector('.pixel-item-sheet .pixel-bag-art img')?.naturalWidth===32","Native extension-owned bitmap loaded");
        check(Boolean.TRUE.equals(js("document.querySelector('.pixel-item-sheet .pixel-bag-art img').getAttribute('src').startsWith('/extension-assets/official.guixu-tide/')")),"Native DLC image must come from its own pack");
        tapSelector(".pixel-item-sheet>header button");tapSelector("#inventory-toggle");
        for(String theme:new String[]{"a","b","d","f"}) {
            tapSelector("#theme-open");tapSelector("[data-theme-picker=dialog] [data-theme-choice="+theme+"]");async("GameThemes.saved");tapSelector("[data-close-dialog=theme-dialog]");
            tapSelector("[data-panel-target=inventory]");
            waitForJs("!document.querySelector('#pixel-inventory').hidden","Native new inventory");
            check(Boolean.TRUE.equals(js("document.querySelectorAll('[data-pixel-item]').length===game.player.inventory.length && document.querySelector('#inventory-card').scrollWidth<=document.querySelector('#inventory-card').clientWidth+2")),"Native bag layout and complete inventory");
            tapSelector("[data-pixel-item=healing_pill]");
            check(Boolean.TRUE.equals(js("!!document.querySelector('.pixel-item-sheet[open] .item-use') && document.querySelector('.pixel-item-sheet[open]').scrollWidth<=document.querySelector('.pixel-item-sheet[open]').clientWidth+2")),"Native item detail sheet");
            capture("visual-bag-"+theme+"-"+arguments.getString("orientation"));
            tapSelector(".pixel-item-sheet>header button");tapSelector("#inventory-toggle");
        }
        tapSelector("[data-panel-target=inventory]");tapSelector("[data-pixel-item=healing_pill]");js("window.__visualHp=game.player.hp;window.__visualQty=game.player.inventory.find(i=>i.id==='healing_pill').quantity;true");tapSelector(".pixel-item-sheet .item-use");
        waitForJs("!busy&&game.player.hp>__visualHp","Native original healing command");
        check(Boolean.TRUE.equals(js("game.player.inventory.find(i=>i.id==='healing_pill').quantity===__visualQty-1&&!document.querySelector('.pixel-item-sheet').open")),"Native exact item consumption and sheet close");tapSelector("#inventory-toggle");
        tapSelector("[data-panel-target=natal-artifact]");
        check(Boolean.TRUE.equals(js("document.querySelector('.pixel-natal-art img').dataset.asset==='gear.umbrella'")),"Native true natal shape");
        tapSelector(".natal-slot.slot-0");tapSelector(".natal-material-choice");waitForJs("!busy&&!!game.natal_artifact.slots[0].material_id","Native pixel material socket");
        check(Boolean.TRUE.equals(js("!!document.querySelector('.natal-slot.slot-0 img').getAttribute('src')")),"Native material icon");
        tapSelector(".natal-slot.slot-0");waitForJs("!busy&&!game.natal_artifact.slots[0].material_id","Native exact material return");tapSelector("#natal-artifact-toggle");
        tapSelector(".hud-identity");waitForJs("!document.querySelector('.pixel-natal-on-actor').hidden","Native character natal visual");capture("visual-character-"+arguments.getString("orientation"));tapSelector("[data-close-dialog=player-details-dialog]");
        js("window.__visualBuildingAge=game.player.age;true");tapSelector("#pixel-scenery-toggle");
        tapSelector("#pixel-buildings [data-building-action=enter]:not(:disabled)");
        waitForJs("!busy&&!!game.buildings.inside&&!document.querySelector('#pixel-scenery-drawer').open","Native home building entrance closes drawer");
        check(Boolean.TRUE.equals(js("document.querySelector('#event-card').getBoundingClientRect().height>=200")),"Native event retains readable height on short landscape");
        capture("visual-home-event-"+arguments.getString("orientation"));chooseBuilding("leave");
        check(Boolean.TRUE.equals(js("!game.buildings.inside&&game.player.age===__visualBuildingAge")),"Native home building visit is zero-year");
        for(String world:new String[]{"human","demon","spirit","true_demon","monster_realm","phantom_underworld","hell","celestial","asura","nether","reincarnation"}) {
            int rank=(world.equals("human")||world.equals("demon"))?4:(world.equals("celestial")||world.equals("asura")||world.equals("nether")||world.equals("reincarnation"))?9:7;
            String mapId=(String)async("api('/api/games',{method:'POST',body:JSON.stringify({name:'原生山河',spirit_root:'supreme_metal',path:'dao',seed:322,custom_start:{world:"+JSONObject.quote(world)+",realm_index:"+rank+"}})}).then(g=>g.id)");async("loadGame("+JSONObject.quote(mapId)+")");
            js("window.__visualMapBefore=JSON.stringify(game);true");tapSelector("#pixel-scenery-toggle");
            waitForJs("document.querySelector('#pixel-home .pixel-background')?.naturalWidth===768","Native home realm painting loaded");
            check(Boolean.TRUE.equals(js("document.querySelector('#pixel-home .pixel-background').getAttribute('src').endsWith('/"+world+".png')")),"Native correct home realm art");
            js("window.__visualCamera=document.querySelector('.pixel-world-plane').style.transform;true");tapSelector(".pixel-world-tools [aria-label='放大绘景']");
            check(Boolean.TRUE.equals(js("document.querySelector('.pixel-world-plane').style.transform!==__visualCamera&&JSON.stringify(game)===__visualMapBefore")),"Native bounded home camera is read only");capture("visual-home-"+world+"-"+arguments.getString("orientation"));tapSelector("#pixel-scenery-drawer .pixel-drawer-heading button");
            tapSelector("[data-panel-target=map]");tapSelector("#map-view-tabs [aria-controls=map-atlas]");
            check(Boolean.TRUE.equals(js("!!document.querySelector('[data-atlas-mode]')&&!document.querySelector('#map-atlas .pixel-background')")),"Native original node atlas retained in new UI");tapSelector("#map-toggle");
        }
        tapSelector("#theme-open");tapSelector("#theme-dialog [data-pixel-setting]");async("GameThemes.saved");tapSelector("[data-close-dialog=theme-dialog]");
        tapSelector("[data-panel-target=inventory]");
        check(Boolean.TRUE.equals(js("document.querySelector('#pixel-inventory').hidden&&!document.querySelector('#inventory-list').hidden&&document.querySelectorAll('#inventory-list .item').length===game.player.inventory.length")),"Native restored legacy inventory");tapSelector("#inventory-toggle");
        runVisualAdditions(result);
        runMonsterVisuals(result);
        runPathCharacters(result);
        runHomeScenes(result);
        result.putString("visual_ui_scope","Four themes, native portrait/landscape clicks, extension-owned bitmap, original healing and exact material return, true natal character/slots, eleven home paintings, bounded immutable camera, original node atlas and legacy fallback; alpha.3 social portraits, domain editor and real domain battle replay");
    }

    private void runVisualAdditions(Bundle result) throws Exception {
        String id=(String)async("api('/api/games',{method:'POST',body:JSON.stringify({name:'新增外观原生验收',spirit_root:'heavenly',path:'demonic',gender:'female',seed:323,preset_id:'core'})}).then(g=>g.id)");
        python(assetText("visual_additions.py")+"\nfrom cultivation_life import server\nprepare_visual_additions(server.ENGINE,"+JSONObject.quote(id)+")");
        async("loadGame("+JSONObject.quote(id)+")");
        tapSelector("#theme-open");
        if(!Boolean.TRUE.equals(js("document.querySelector('#theme-dialog [data-pixel-setting]').checked")))tapSelector("#theme-dialog [data-pixel-setting]");
        async("GameThemes.saved");tapSelector("[data-close-dialog=theme-dialog]");
        js("window.__additionsBefore=JSON.stringify(game);true");
        waitForJs("document.querySelector('#npc-event-art img')?.naturalWidth>0","Native social figure");
        tapSelector(".npc-event-person");waitForJs("document.querySelector('#npc-art-dialog img')?.naturalWidth>0","Native NPC card");
        capture("alpha3-npc-"+arguments.getString("orientation"));tapSelector("#npc-art-dialog header button");
        tapSelector(".hud-identity");waitForJs("document.querySelector('.pixel-details-art canvas')?.dataset.actor==='actor.human.demonic.female'","Native demonic player figure");
        check(Boolean.TRUE.equals(js("document.querySelector('.pixel-portrait').src.includes('demonic-female')")),"Native demonic avatar");
        tapSelector("[data-close-dialog=player-details-dialog]");tapSelector("[data-panel-target=settings]");tapSelector("[data-voisinage-editor]");
        waitForJs("VoisinageEditor.status().ready","Native domain editor");
        check(Boolean.TRUE.equals(js("VoisinageEditor.status().previewActor==='demonic-female'&&document.querySelectorAll('#ve-pattern option').length===18")),"Native preview identity and path-gated styles");
        check(Boolean.TRUE.equals(js("DomainFields.catalog.length===30&&DomainFields.catalog.every(r=>!!DomainMotifs.bitmap(DomainFields.compose({outline:r.id,pattern:r.id,palette:'#98baca',density:75,control:'rings'},'native-ink')))")),"Native thirty outline assets decoded and tinted");
        result.putString("domain_ink_scope","Thirty base/DLC outline bitmaps decoded and tinted; eighteen lawful demonic choices; flowing clock saved through native editor and replay");
        js("for(const [key,value] of [['outline','time'],['pattern','time'],['color-hex','#98baca']]){const e=document.querySelector('#ve-'+key);e.value=value;e.dispatchEvent(new Event('input',{bubbles:true}));}true");
        tapSelector("#ve-save");waitForJs("!VoisinageEditor.status().busy&&document.querySelector('#ve-status').textContent.includes('已保存')","Native appearance save");
        check(Boolean.TRUE.equals(js("document.querySelector('#voisinage-editor').scrollWidth<=document.querySelector('#voisinage-editor').clientWidth+1")),"Native editor overflow");
        capture("alpha3-editor-"+arguments.getString("orientation"));tapSelector("#ve-close");
        tapSelector("[data-voisinage-editor]");waitForJs("VoisinageEditor.status().ready","Native appearance reopen");
        check(Boolean.TRUE.equals(js("VoisinageEditor.status().draft.palette==='#98baca'&&VoisinageEditor.status().draft.pattern==='time'&&JSON.stringify(game)===__additionsBefore")),"Native persisted appearance and no game mutation");
        tapSelector("#ve-close");tapSelector("#settings-toggle");
        python(assetText("visual_additions.py")+"\nfrom cultivation_life import server\nprepare_domain_battle(server.ENGINE,"+JSONObject.quote(id)+",'mutual')");
        async("loadGame("+JSONObject.quote(id)+")");tapSelector("#battle-report-open");
        waitForJs("CombatReplay.diagnostics().active&&!document.querySelector('[data-combat-replay]').disabled","Native domain battle ready");
        js("window.__domainBefore=JSON.stringify(game);true");
        check(Boolean.TRUE.equals(js("CombatReplay.diagnostics().domainStages.some(s=>s.phase==='effect')&&game.last_combat_report.visual.domains.player.palette==='#98baca'")),"Native domain phases and saved custom color");
        js("for(const s of CombatReplay.diagnostics().domainStages)CombatReplay.seek((s.start+s.end)/2);const s=CombatReplay.diagnostics().domainStages.find(s=>s.phase==='control');CombatReplay.seek(s.start+.8);true");
        capture("alpha3-domain-"+arguments.getString("orientation"));
        check(Boolean.TRUE.equals(js("document.querySelector('#battle-report-card').scrollWidth<=document.querySelector('#battle-report-card').clientWidth+1")),"Native domain battle overflow");
        js("CombatReplay.seek(CombatReplay.diagnostics().duration);true");
        check(Boolean.TRUE.equals(js("Math.abs(document.querySelector('[data-combat-meter=hero] progress').value-game.last_combat_report.player_combat_state)<.01&&Math.abs(document.querySelector('[data-combat-meter=npc] progress').value-game.last_combat_report.enemy_combat_state)<.01")),"Native domain final authoritative state");
        tapSelector("[data-combat-replay]");tapSelector("#battle-report-toggle");
        check(Boolean.TRUE.equals(js("!CombatReplay.diagnostics().active&&!CombatReplay.diagnostics().raf&&JSON.stringify(game)===__domainBefore")),"Native domain replay no mutation and disposal");
        result.putString("domain_replay_scope","Real mutual domination battle, open/control/effects/release, custom appearance, final state, native replay and disposal");
        result.putString("visual_additions_scope","Demonic female avatar/figure, real NPC card, thirteen-component editor with identity, custom color, save/reopen and no game state changes");
        for(String path:new String[]{"dao","demonic"})for(String gender:new String[]{"male","female"}) {
            String hero=(String)async("api('/api/games',{method:'POST',body:JSON.stringify({name:'新版主角原生验收',spirit_root:'heavenly',path:"+JSONObject.quote(path)+",gender:"+JSONObject.quote(gender)+",seed:326,preset_id:"+JSONObject.quote(path.equals("demonic")?"demonic_core":"core")+"})}).then(g=>g.id)");
            async("loadGame("+JSONObject.quote(hero)+")");
            js("window.__heroBefore=JSON.stringify(game);true");tapSelector(".hud-identity");
            waitForJs("document.querySelector('.pixel-details-art canvas')?.dataset.actor==="+JSONObject.quote("actor.human."+path+"."+gender),"Native selected static figure");
            check(Boolean.TRUE.equals(async("(async()=>{const c=document.querySelector('.pixel-details-art canvas'),p=document.querySelector('.pixel-portrait'),b=await VisualAssets.load(c.dataset.actor+'.figure'),e=document.createElement('canvas');e.width=256;e.height=288;e.getContext('2d').drawImage(b,0,0);const a=c.getContext('2d').getImageData(0,0,c.width,c.height).data,d=e.getContext('2d').getImageData(0,0,256,288).data;return c.width===256&&c.height===288&&a.every((v,i)=>v===d[i])&&p.naturalWidth===128&&p.src.includes('-static-portrait.png')&&JSON.stringify(game)===__heroBefore})()")),"Native new source pixels and avatar");
            capture("alpha3-static-"+path+"-"+gender+"-"+arguments.getString("orientation"));
            tapSelector("[data-close-dialog=player-details-dialog]");
        }
        result.putString("protagonist_static_scope","All four selected Dao/Demonic male/female 256x288 static figures pixel-equal, 128x128 portraits, native detail clicks and no state writes");
    }


    private void runHomeScenes(Bundle result) throws Exception {
        String fixture=assetText("home_scenes.py");
        String id=(String)async("api('/api/games',{method:'POST',body:JSON.stringify({name:'主页原生验收',spirit_root:'mutated_yin',path:'ghost',seed:606})}).then(g=>g.id)");
        python("from cultivation_life import server\ng=server.ENGINE.store.load("+JSONObject.quote(id)+")\ng.settings.update(silent_events=True,combat_popup=False)\nserver.ENGINE.store.save(g)");
        async("loadGame("+JSONObject.quote(id)+")");
        boolean compact=Boolean.TRUE.equals(js("document.documentElement.dataset.pixelDrawer==='true'"));
        if(compact)tapSelector("#pixel-scenery-toggle");
        waitForJs("!!document.querySelector('.pixel-world-view')","Home painting ready");
        js("window.__homeBefore=JSON.stringify(game);true");
        for(String mode:new String[]{"influence","events","caravans","buildings","terrain"}) {
            tapSelector("[data-home-map-mode="+mode+"]");
            check(Boolean.TRUE.equals(js("document.querySelector('.pixel-world-view').dataset.mode==='"+mode+"'")),"Native home mode "+mode);
        }
        check(Boolean.TRUE.equals(js("JSON.stringify(game)===__homeBefore&&document.documentElement.scrollWidth<=innerWidth+1")),"Native map read only and fits");
        String destination=(String)js("game.map.locations.find(p=>!p.current&&p.travel_status==='ok').id");
        js("(()=>{const s=document.querySelector('select[aria-label=\"浏览绘景地域\"]');s.value="+JSONObject.quote(destination)+";s.dispatchEvent(new Event('change'));return true})()");
        tapSelector(".home-map-travel");waitForJs("!busy&&game.map.current==="+JSONObject.quote(destination),"Native home travel",30000);
        python(fixture+"\nfrom cultivation_life import server\nthunder(server.ENGINE,"+JSONObject.quote(id)+")");async("loadGame("+JSONObject.quote(id)+")");
        waitForJs("!document.querySelector('#event-cinematic').hidden&&!document.querySelector('#event-cinematic canvas').hidden","Native event scene");
        check(Boolean.TRUE.equals(js("document.querySelector('#action-card').getClientRects().length===0&&document.documentElement.scrollWidth<=innerWidth+1")),"Native event layout");
        tapSelector("#event-choices button");waitForJs("!busy&&game.trial.step===2","Native thunder submission");
        waitForJs("document.querySelector('.event-cinematic-caption').textContent.includes('已结算')","Native settled CG");
        capture("alpha6-thunder-"+arguments.getString("orientation"));
        tapSelector("#event-cinematic button:last-child");check(Boolean.TRUE.equals(js("!EventScenes.inspect().frame")),"Native CG disposal");
        for(int i=0;i<2;i++){tapSelector("#event-choices button");waitForJs("!busy","Native next thunder");}
        check(Boolean.TRUE.equals(js("!game.trial.active&&document.querySelector('#action-card').getClientRects().length>0")),"Native trial completed");
        python(fixture+"\nfrom cultivation_life import server\nmirrors(server.ENGINE,"+JSONObject.quote(id)+")");async("loadGame("+JSONObject.quote(id)+")");tapSelector("#battle-report-open");
        waitForJs("CombatReplay.diagnostics().active&&!document.querySelector('[data-combat-replay]').disabled","Native mirror replay",30000);
        check(Boolean.TRUE.equals(js("for(let t=0;t<=CombatReplay.diagnostics().duration;t+=.5)CombatReplay.seek(t);true")),"Native complete mirror timeline");
        js("CombatReplay.seek(2);true");check(Boolean.TRUE.equals(js("CombatReplay.diagnostics().teams.npc.length===3&&CombatReplay.diagnostics().teams.npc.every(n=>n.id===CombatReplay.diagnostics().actors.hero.id&&ActorVariants.valid(n.visualVariant))")),"Native three mirror actors");
        capture("alpha6-mirrors-"+arguments.getString("orientation"));tapSelector("#battle-report-toggle");
        result.putString("home_scenes_scope","Five map views, original travel, three real thunder choices, bounded CG disposal and three derived player actors; responsive native clicks");
    }

    private void runPathCharacters(Bundle result) throws Exception {
        String fixture=assetText("path_characters.py");
        String id=(String)async("api('/api/games',{method:'POST',body:JSON.stringify({name:'三道原生验收',spirit_root:'heavenly',path:'dao',seed:510,preset_id:'core'})}).then(g=>g.id)");
        python(fixture+"\nimport json\nfrom cultivation_life import server\nserver._release_path_cases=json.dumps(path_character_cases())");
        org.json.JSONArray cases=new org.json.JSONArray(com.chaquo.python.Python.getInstance().getModule("cultivation_life.server").get("_release_path_cases").toString());
        check(cases.length()==6,"Three-path native cases");
        for(int i=0;i<cases.length();i++) {
            JSONObject form=cases.getJSONObject(i);
            python(fixture+"\nimport json\nfrom cultivation_life import server\nprepare_path_character(server.ENGINE,"+JSONObject.quote(id)+",json.loads("+JSONObject.quote(form.toString())+"))");
            async("loadGame("+JSONObject.quote(id)+")");
            waitForJs("game.player.visual_actor==="+JSONObject.quote(form.getString("static"))+"&&document.querySelector('.pixel-portrait')?.naturalWidth===128","Native path avatar");
            if(Boolean.TRUE.equals(js("document.querySelector('#battle-report-card').getClientRects().length>0")))tapSelector("#battle-report-toggle");
            js("window.__pathBefore=JSON.stringify(game);true");tapSelector(".hud-identity");
            waitForJs("document.querySelector('.pixel-details-art canvas')?.dataset.actor==="+JSONObject.quote(form.getString("static")),"Native path detail");
            tapSelector("[data-close-dialog=player-details-dialog]");tapSelector("#battle-report-open");
            waitForJs("CombatReplay.diagnostics().active&&!document.querySelector('[data-combat-replay]').disabled","Native path battle",30000);
            for(double at:new double[]{0,1.5,2.1,3,10000}) {
                js("CombatReplay.seek("+at+");true");
                check(Boolean.TRUE.equals(js("CombatReplay.diagnostics().actors.hero.id==="+JSONObject.quote(form.getString("combat"))+"&&CombatReplay.diagnostics().actors.npc.id==="+JSONObject.quote(form.getString("npc"))+"&&CombatReplay.diagnostics().decodedBytes<64*1024*1024")),"Native hero and enemy path actors");
            }
            capture("alpha5-"+form.getString("combat")+"-"+arguments.getString("orientation"));tapSelector("#battle-report-toggle");
            tapSelector("[data-panel-target=relationship]");
            js("(()=>{const s=document.querySelector('#npc-contacts input[type=search]');s.value='三道同道';s.dispatchEvent(new Event('input',{bubbles:true}));return true})()");
            tapSelector(".contact-person");tapSelector(".npc-art-contact-figure");
            waitForJs("(()=>{const im=document.querySelector('#npc-art-dialog .npc-art-figure');return im?.complete&&im.naturalWidth===256&&im.src.includes("+JSONObject.quote(form.getString("npc"))+")})()","Native NPC card");
            tapSelector("#npc-art-dialog button");tapSelector("#relationship-toggle");
            check(Boolean.TRUE.equals(js("JSON.stringify(game)===__pathBefore&&CombatReplay.diagnostics().cache===0")),"Native path views read only");
        }
        result.putString("path_character_scope","Six heroes and six NPCs: real portrait/detail/card taps, settled battle actors, cache disposal, no state writes; ghost red female selected");
    }

    private void runMonsterVisuals(Bundle result) throws Exception {
        String fixture=assetText("monster_visuals.py");
        String id=(String)async("api('/api/games',{method:'POST',body:JSON.stringify({name:'八族原生验收',spirit_root:'supreme_water',path:'monster',monster_species_id:'flora',start_world:'monster_realm',seed:4190})}).then(g=>g.id)");
        python(fixture+"\nimport json\nfrom cultivation_life import server\nselected={}\nfor c in monster_visual_cases():\n    stage='high' if c['realm']>=7 else 'low'\n    if stage=='low' and c['realm']>1:continue\n    selected.setdefault((c['species'],stage),c)\nserver._release_monster_cases=json.dumps(list(selected.values()))");
        org.json.JSONArray cases=new org.json.JSONArray(com.chaquo.python.Python.getInstance().getModule("cultivation_life.server").get("_release_monster_cases").toString());
        check(cases.length()==16,"Eight species low/high native cases");
        for(int i=0;i<cases.length();i++) {
            JSONObject form=cases.getJSONObject(i);
            python(fixture+"\nimport json\nfrom cultivation_life import server\nprepare_monster_visual(server.ENGINE,"+JSONObject.quote(id)+",json.loads("+JSONObject.quote(form.toString())+"))");
            async("loadGame("+JSONObject.quote(id)+")");
            waitForJs("game.player.visual_actor==="+JSONObject.quote(form.getString("static"))+"&&document.querySelector('.pixel-portrait')?.naturalWidth===128","Native monster avatar");
            if(Boolean.TRUE.equals(js("document.querySelector('#battle-report-card').getClientRects().length>0")))tapSelector("#battle-report-toggle");
            js("window.__monsterBefore=JSON.stringify(game);true");
            tapSelector(".hud-identity");
            waitForJs("document.querySelector('.pixel-details-art canvas')?.dataset.actor==="+JSONObject.quote(form.getString("static")),"Native realm figure");
            tapSelector("[data-close-dialog=player-details-dialog]");tapSelector("#battle-report-open");
            waitForJs("CombatReplay.diagnostics().active&&!document.querySelector('[data-combat-replay]').disabled","Native monster action atlas",30000);
            for(double at:new double[]{0,1.5,2.1,3,10000}) {
                js("CombatReplay.seek("+at+");true");
                check(Boolean.TRUE.equals(js("CombatReplay.diagnostics().actors.hero.id==="+JSONObject.quote(form.getString("combat"))+"&&CombatReplay.diagnostics().decodedBytes<64*1024*1024")),"Native exact monster combat identity and bounded memory");
            }
            check(Boolean.TRUE.equals(js("JSON.stringify(game)===__monsterBefore")),"Monster replay is read only");
            if(i==0||i==cases.length()-1)capture("alpha4-monster-"+i+"-"+arguments.getString("orientation"));
            tapSelector("#battle-report-toggle");
            check(Boolean.TRUE.equals(js("CombatReplay.diagnostics().cache===0")),"Native monster cache disposal");
        }
        python(fixture+"\nfrom cultivation_life import server\nprepare_monster_evolution(server.ENGINE,"+JSONObject.quote(id)+")");
        async("loadGame("+JSONObject.quote(id)+")");
        check(Boolean.TRUE.equals(js("game.player.visual_actor==='actor.monster.flora-spirit-shared'")),"Native pre-evolution appearance");
        tapSelector("[data-panel-target=bloodline]");
        js("[...document.querySelectorAll('.bloodline-candidate')].find(n=>n.textContent.includes('万灵古树')).querySelector('button').setAttribute('data-native-evolve','1');true");
        tapSelector("[data-native-evolve]");
        waitForJs("!busy&&game.player.visual_actor==='actor.monster.flora-tree-lord-shared'","Native real evolution updates portrait");
        tapSelector("#bloodline-toggle");
        result.putString("monster_visual_scope","Eight species low/high figures and action atlases, actual evolution click changes appearance, immutable replay and cache disposal; native orientation");
    }

    private void runCombatAlpha(Bundle result) throws Exception {
        String fixture=assetText("alpha2_release.py");
        for(String theme:new String[]{"a","b","d","f"}) {
            String kind=(theme.equals("a")||theme.equals("d"))?"true_body":"replica";
            String id=(String)async("api('/api/games',{method:'POST',body:JSON.stringify({name:'原生交锋验收',spirit_root:'heavenly',path:'dao',seed:622,preset_id:'core'})}).then(g=>g.id)");
            python(fixture+"\nfrom cultivation_life import server\nserver._alpha2_expected=prepare_alpha2(server.ENGINE,"+JSONObject.quote(id)+","+JSONObject.quote(kind)+")");
            async("loadGame("+JSONObject.quote(id)+")");
            tapSelector("#theme-open");tapSelector("[data-theme-picker=dialog] [data-theme-choice="+theme+"]");
            if(Boolean.TRUE.equals(js("document.querySelector('#theme-dialog [data-pixel-setting]').checked")))tapSelector("#theme-dialog [data-pixel-setting]");
            async("GameThemes.saved");tapSelector("[data-close-dialog=theme-dialog]");
            tapSelector("[data-panel-target=inventory]");
            check(Boolean.TRUE.equals(js("game.player.inventory.find(i=>i.id==='guixu_canghai_equipment_01').description.includes('HP上限 +18')&&game.player.inventory.find(i=>i.id==='guixu_canghai_consumable_01').description.includes('21.50%')")),"Native Guixu factual descriptions");
            tapSelector("#inventory-list [data-item-id=guixu_canghai_consumable_01] .item-use");
            waitForJs("!busy&&game.player.inventory.find(i=>i.id==='guixu_canghai_consumable_01').quantity===1","Native original Guixu consumption");
            capture("alpha2-items-"+theme+"-"+arguments.getString("orientation"));tapSelector("#inventory-toggle");
            tapSelector("#theme-open");tapSelector("#theme-dialog [data-pixel-setting]");async("GameThemes.saved");tapSelector("[data-close-dialog=theme-dialog]");
            tapSelector("[data-panel-target=relationship]");
            check(Boolean.TRUE.equals(js("NpcContacts.open(game.world_npcs.find(n=>n.name==='验收持宝道友').id)")),"Native select actual holder");
            AtomicReference<Throwable> confirmError=new AtomicReference<>();
            android.accessibilityservice.AccessibilityServiceInfo serviceInfo=getUiAutomation().getServiceInfo();
            serviceInfo.flags|=android.accessibilityservice.AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;
            getUiAutomation().setServiceInfo(serviceInfo);
            Thread confirmation=new Thread(()->{
                try {
                    long until=System.currentTimeMillis()+20000;
                    while(System.currentTimeMillis()<until) {
                        android.view.accessibility.AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();
                        if(root!=null) {
                            java.util.List<android.view.accessibility.AccessibilityNodeInfo> buttons=root.findAccessibilityNodeInfosByViewId("android:id/button1");
                            if(!buttons.isEmpty()&&buttons.get(0).performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK))return;
                        }
                        Thread.sleep(100);
                    }
                    throw new AssertionError("Native combat confirmation did not appear");
                } catch(Throwable error) {confirmError.set(error);}
            },"alpha2-native-confirm");
            confirmation.start();tapSelector("[data-contact-action=slay]");confirmation.join(22000);
            check(!confirmation.isAlive()&&confirmError.get()==null,"Native combat confirmation failed: "+confirmError.get());
            waitForJs("!busy&&!!game.last_combat_report&&CombatReplay.diagnostics().active&&!document.querySelector('[data-combat-replay]').disabled","Native real combat CG",60000);
            python(fixture+"\nfrom cultivation_life import server\ninspect_alpha2(server.ENGINE,server._alpha2_expected)\nserver._alpha2_saved=server.ENGINE.store._path("+JSONObject.quote(id)+").read_bytes()");
            js("CombatReplay.seek(10000);true");
            check(Boolean.TRUE.equals(js("CombatReplay.diagnostics().defeat!==null&&CombatReplay.diagnostics().decodedBytes<67108864&&document.querySelector('#battle-report-card').scrollWidth<=document.querySelector('#battle-report-card').clientWidth+1")),"Native defeat, memory budget and layout");
            capture("alpha2-defeat-"+theme+"-"+arguments.getString("orientation"));
            tapSelector("[data-combat-replay]");Thread.sleep(300);tapSelector("#battle-report-toggle");
            check(Boolean.TRUE.equals(js("!CombatReplay.diagnostics().active&&!CombatReplay.diagnostics().raf&&CombatReplay.diagnostics().cache===0")),"Native CG disposal");
            python("from cultivation_life import server\nassert server.ENGINE.store._path("+JSONObject.quote(id)+").read_bytes()==server._alpha2_saved");
            tapSelector("#relationship-toggle");
        }
        String group=(String)async("api('/api/games',{method:'POST',body:JSON.stringify({name:'原生群战验收',spirit_root:'heavenly',path:'dao',seed:772,preset_id:'core'})}).then(g=>g.id)");
        python(fixture+"\nfrom cultivation_life import server\nprepare_alpha2_group(server.ENGINE,"+JSONObject.quote(group)+")");async("loadGame("+JSONObject.quote(group)+")");
        tapSelector("#battle-report-open");
        waitForJs("CombatReplay.diagnostics().active&&!document.querySelector('[data-combat-replay]').disabled","Native group CG",60000);
        js("CombatReplay.seek(10000);true");
        check(Boolean.TRUE.equals(js("CombatReplay.diagnostics().participants.length===6&&CombatReplay.diagnostics().defeat.side==='hero'&&CombatReplay.diagnostics().teams.hero.every(m=>m.mode==='defeat')&&CombatReplay.diagnostics().decodedBytes<100663296")),"Native three-per-side true group defeat");
        capture("alpha2-group-"+arguments.getString("orientation"));tapSelector("#battle-report-toggle");
        result.putString("combat_alpha_scope","Four themes: actual native Guixu consumption and descriptions, true and replica holder combat +1 to Lv5, original combat settlement, single and 3v3 CG defeat, replay read-only, bounded decode and disposal; portrait/landscape, not full repository");
    }

    @Override public void onStart() {
        Bundle result=new Bundle();
        File dlcPreferences=null;byte[] previousDlcPreferences=null;
        try {
            String requested=arguments.getString("phase","initial");
            if(requested.startsWith("civilizations-")) {
                dlcPreferences=new File(getTargetContext().getFilesDir(),"game/data/extension_preferences.json");
                if(dlcPreferences.isFile())previousDlcPreferences=java.nio.file.Files.readAllBytes(dlcPreferences.toPath());
                File directory=dlcPreferences.getParentFile();check(directory.isDirectory()||directory.mkdirs(),"Test preference directory");
                JSONObject enabled=new JSONObject();
                enabled.put("official.monster-bloodlines",requested.equals("civilizations-i-only"));
                enabled.put("official.monster-civilizations",requested.equals("civilizations-ii-only"));
                JSONObject document=new JSONObject();document.put("schema_version",1);document.put("enabled",enabled);
                java.nio.file.Files.write(dlcPreferences.toPath(),document.toString().getBytes(StandardCharsets.UTF_8));
            }
            if(requested.equals("trial-sites-disabled")) {
                dlcPreferences=new File(getTargetContext().getFilesDir(),"game/data/extension_preferences.json");
                if(dlcPreferences.isFile())previousDlcPreferences=java.nio.file.Files.readAllBytes(dlcPreferences.toPath());
                File directory=dlcPreferences.getParentFile();check(directory.isDirectory()||directory.mkdirs(),"Trial preference directory");
                JSONObject enabled=new JSONObject();enabled.put("official.trial-sites",false);
                JSONObject document=new JSONObject();document.put("schema_version",1);document.put("enabled",enabled);
                java.nio.file.Files.write(dlcPreferences.toPath(),document.toString().getBytes(StandardCharsets.UTF_8));
            }
            // Establish the native input connection before measuring the page.
            // Its first connection can resize SystemUI insets in a cold emulator.
            check(getUiAutomation()!=null,"Native automation connection unavailable");
            activity=startActivitySync(new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            if("portrait".equals(arguments.getString("orientation"))) runOnMainSync(()->activity.setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_PORTRAIT));
            if("landscape".equals(arguments.getString("orientation"))) runOnMainSync(()->activity.setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE));
            long deadline=System.currentTimeMillis()+60000;
            while(web==null && System.currentTimeMillis()<deadline) {
                runOnMainSync(()->web=findWeb(activity.findViewById(android.R.id.content)));
                Thread.sleep(150);
            }
            check(web!=null,"Release WebView did not start");
            // Give page loading its own deadline after Python and the WebView
            // are ready; don't misreport a cold-load timeout as a version mismatch.
            waitForJs("typeof configData!=='undefined' && !!configData?.base_game && !!window.AndroidUI",
                      "Release page configuration did not load",120000);
            async("GameThemes.ready");
            String baseVersion=getTargetContext().getPackageManager().getPackageInfo(getTargetContext().getPackageName(),0).versionName.split("-android")[0];
            check(Boolean.TRUE.equals(js("configData.base_game.version==="+JSONObject.quote(baseVersion)+" && !configData.debug && configData.extensions.some(e=>e.id==='official.monster-civilizations') && configData.extensions.every(e=>e.status==='loaded'"+((requested.startsWith("civilizations-")||requested.equals("trial-sites-disabled"))?"||e.status==='disabled'":"")+")")),"Version, release mode or DLC mismatch: installed="+baseVersion+" config="+js("JSON.stringify({version:configData?.base_game?.version,debug:configData?.debug,extensions:configData?.extensions})"));
            SharedPreferences marker=getTargetContext().getSharedPreferences("release-verification",0);
            String phase=arguments.getString("phase","initial");
            // These two legacy phases verify base-game fallback without the optional Asura DLC.
            if(phase.equals("upper-voisinage") || phase.equals("upper")) python("from cultivation_life.system.asura import config\nconfig()['enabled']=False");
            if(phase.equals("soul-lifecycle")) {
                runSoulLifecycle(result);
            } else if(phase.equals("authored")) {
                runAuthored(result);
            } else if(phase.equals("update301")) {
                runUpdate301(result);
            } else if(phase.equals("combat-alpha")) {
                runCombatAlpha(result);
            } else if(phase.equals("visual-ui")) {
                runVisualUi(result);
            } else if(phase.equals("home-scenes")) {
                tapSelector("#theme-open");
                if(!Boolean.TRUE.equals(js("document.querySelector('#theme-dialog [data-pixel-setting]').checked")))tapSelector("#theme-dialog [data-pixel-setting]");
                async("GameThemes.saved");tapSelector("[data-close-dialog=theme-dialog]");
                runHomeScenes(result);
            } else if(phase.equals("maps-2131") || phase.equals("maps-2132") || phase.equals("maps-2133")) {
                int mapCases=0;
                for(String world:new String[]{"human","demon","spirit","true_demon","monster_realm","phantom_underworld","hell","celestial","asura","nether","reincarnation"}) {
                    int rank=(world.equals("human")||world.equals("demon"))?4:(world.equals("celestial")||world.equals("asura")||world.equals("nether")||world.equals("reincarnation"))?9:7;
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'立体山海原生验收',spirit_root:'supreme_earth',path:'dao',seed:2131,custom_start:{world:"+JSONObject.quote(world)+",realm_index:"+rank+"}})});return g.id;})()");
                    python("from cultivation_life import server\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.settings['silent_events']=True\ng.settings['combat_popup']=False\ne.store.save(g)");
                    async("loadGame("+JSONObject.quote(id)+")");
                    for(String theme:(phase.equals("maps-2132") || phase.equals("maps-2133")) && !world.equals("human")?new String[]{"a"}:new String[]{"a","b","d","f"}) {
                        js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click();UtilityPanels.close('map');true");async("GameThemes.saved");
                        tapSelector("[data-panel-target=map]");tapSelector("#map-view-tabs [aria-controls=map-atlas]");tapSelector("[data-atlas-mode='3d']");
                        if(phase.equals("maps-2132") || phase.equals("maps-2133")) {waitForJs("document.querySelector('.atlas-scene').dataset.artworkState==='ready'","Independent SVG artwork loaded");check(Boolean.TRUE.equals(js("document.querySelector('[data-world-artwork]').dataset.worldArtwork==="+JSONObject.quote(world))),"Correct realm artwork");}
                        check(Boolean.TRUE.equals(js("document.querySelectorAll('.atlas-scene [data-atlas-location]').length===game.map.locations.length && document.querySelectorAll('[data-atlas-road]').length===game.map.roads.length")),"All real locations and roads are visible");
                        python("from cultivation_life import server\nserver._maps_native_before=server.ENGINE.store._path("+JSONObject.quote(id)+").read_bytes()");
                        String yaw=(String)js("document.querySelector('.atlas-scene').dataset.yaw");tapSelector("[aria-label='向右旋转地图']");
                        check(!yaw.equals(js("document.querySelector('.atlas-scene').dataset.yaw")),"Native map rotation");
                        tapSelector("[aria-label='复位地图视角']");check(yaw.equals(js("document.querySelector('.atlas-scene').dataset.yaw")),"Native camera reset");
                        tapSelector("[aria-label='放大地图']");check(Boolean.TRUE.equals(js("Number(document.querySelector('.atlas-scene').dataset.zoom)>1")),"Native zoom");tapSelector("[aria-label='复位地图视角']");
                        if(phase.equals("maps-2132")) {dragMapNative();tapSelector("[aria-label='复位地图视角']");}
                        if(phase.equals("maps-2133")) {panMapNative(false);panMapNative(true);tapSelector("[aria-label='复位地图视角']");}
                        String destination=(String)js("game.map.locations.find(n=>!n.current && !n.min_realm_index).id");tapSelector("[data-atlas-location="+JSONObject.quote(destination)+"] .atlas-dot");
                        check(Boolean.TRUE.equals(js("document.querySelector('#map-atlas .atlas-detail').dataset.selectedLocation==="+JSONObject.quote(destination)+" && document.querySelectorAll('.scene-road.route').length===game.map.locations.find(n=>n.id==="+JSONObject.quote(destination)+").route_ids.length-1")),"Native selection highlights authoritative itinerary");
                        tapSelector("[data-atlas-mode=flat]");check(Boolean.TRUE.equals(js("!document.querySelector('.atlas-scene') && !!document.querySelector('#map-atlas svg')")),"Native planar fallback");if(phase.equals("maps-2133"))panMapNative(false);tapSelector("[data-atlas-mode='3d']");
                        js("(()=>{window.__mapFuture=JSON.parse(JSON.stringify(game.map));const p=JSON.parse(JSON.stringify(__mapFuture.locations[0]));p.id='native-future';p.name='新生山海';p.current=false;delete p.atlas;__mapFuture.locations.push(p);__mapFuture.roads.push({from:__mapFuture.current,to:p.id,years:3});MapAtlas.render(__mapFuture,game,()=>{},()=>false);return true;})()");
                        check(Boolean.TRUE.equals(js("!!document.querySelector('[data-atlas-location=native-future]') && document.querySelectorAll('[data-atlas-road]').length===game.map.roads.length+1")),"Native new-location fallback");
                        js("renderMap(game.map,game.auction_system);busy=true;MapAtlas.syncBusy();true");check(Boolean.TRUE.equals(js("document.querySelector('#map-atlas .atlas-detail [data-atlas-unavailable]').disabled")),"Map remains disabled while busy");js("busy=false;MapAtlas.syncBusy();true");
                        python("from cultivation_life import server\nassert server.ENGINE.store._path("+JSONObject.quote(id)+").read_bytes()==server._maps_native_before");
                        tapSelector("[aria-label='定位当前地域']");check(Boolean.TRUE.equals(js("(()=>{const e=document.querySelector('.atlas-scene .current .atlas-dot'),r=e.getBoundingClientRect(),p=e.closest('.utility-panel'),h=p.querySelector(':scope > .section-title').getBoundingClientRect();return r.bottom>h.bottom && r.top<Math.min(p.getBoundingClientRect().bottom,innerHeight);})()")),"Native locate reveals current marker below sticky heading");if(phase.equals("maps-2133"))check(Boolean.TRUE.equals(js("(()=>{const e=document.querySelector('.atlas-scene .current .atlas-dot').getBoundingClientRect(),v=document.querySelector('.atlas-viewport').getBoundingClientRect();return Math.abs(e.x+e.width/2-v.x-v.width/2)<3 && Math.abs(e.y+e.height/2-v.y-v.height/2)<3;})()")),"Native locate truly centers marker");check(Boolean.TRUE.equals(js("document.querySelector('#map-card').scrollWidth<=document.querySelector('#map-card').clientWidth+2")),"Native map remains inside panel");
                        capture(phase+"-"+world+"-"+theme+"-"+arguments.getString("orientation","portrait"));mapCases++;
                    }
                    if(world.equals("human")) {
                        js("window.__mapAge=game.player.age;window.__mapOrigin=game.player.world;true");
                        tapSelector("#map-atlas .atlas-detail [data-atlas-unavailable]");waitForJs("!busy && game.player.age>__mapAge","Native map travel must consume time",60000);
                        check(Boolean.TRUE.equals(js("game.player.world===__mapOrigin")),"Same-world map travel retains world");
                    }
                    js("UtilityPanels.close('map');true");
                }
                result.putInt("maps_cases",mapCases);
                result.putString("maps_scope","Eleven worlds and four themes; independent SVG artwork, unrestricted native drag, rotation, zoom, reset, selection, true routes, planar fallback, future locations, immutable saves, busy guard and actual travel");
            } else if(phase.startsWith("civilizations-")) {
                boolean second=phase.equals("civilizations-ii-only"), first=phase.equals("civilizations-i-only");
                check(Boolean.TRUE.equals(js("configData.extensions.some(e=>e.id==='official.monster-civilizations'&&e.status==='loaded')==="+second+"&&configData.extensions.some(e=>e.id==='official.monster-bloodlines'&&e.status==='loaded')==="+first)),"Independent package loading");
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'独立万灵验收',spirit_root:'supreme_earth',path:'monster',monster_species_id:'fox',seed:2100,custom_start:{world:'human',realm_index:4}})});return g.id;})()");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.monster_civilizations.available==="+second+" && game.monster_civilizations.ui_available==="+second)),"Independent atlas availability");
                if(second) {
                    tapSelector("[data-panel-target=civilizations]");waitForJs("!!document.querySelector('.mc-region')","Independent atlas load");
                    tapSelector("[data-civilization-action=observe]");waitForJs("!!document.querySelector('.mc-species') && !busy","Independent real observation");
                }
                result.putString("civilizations_matrix_scope","Signed native actual restart with original loader and user preference switches: "+phase);
            } else if(phase.equals("trial-sites-disabled")) {
                String id=(String)async("api('/api/games',{method:'POST',body:JSON.stringify({name:'试境关闭验收',spirit_root:'heavenly',path:'dao',seed:341,preset_id:'core'})}).then(g=>g.id)");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("configData.extensions.some(e=>e.id==='official.trial-sites' && e.status==='disabled') && !game.trial_site.enabled && document.querySelector('[data-panel-target=trial-site]').classList.contains('hidden') && document.querySelector('#trial-site-card').classList.contains('hidden')")),"Actual disabled DLC shortcut and gameplay");
                check(Boolean.TRUE.equals(async("api('/api/games/'+game.id+'/trial-site-action',{method:'POST',body:JSON.stringify({action:'enter',world:'human',floor:1})}).then(()=>false).catch(()=>true)")),"Disabled DLC rejects actual trial RPC");
                result.putString("trial_sites_disabled_scope","Actual preference file and restart disable the package, shortcut, panel and command");
            } else if(phase.equals("trial-sites")) {
                for(String world:new String[]{"human","spirit","celestial","demon","true_demon","monster_realm","phantom_underworld","hell","asura","nether","reincarnation"}) {
                    String id=(String)async("api('/api/games',{method:'POST',body:JSON.stringify({name:'试境原生验收',spirit_root:'heavenly',path:'dao',seed:341,preset_id:'core'})}).then(g=>g.id)");
                    python("from cultivation_life import server\nfrom cultivation_life.system import trial_sites\nfrom cultivation_life.rules import max_hp,max_mp\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.player.world="+JSONObject.quote(world)+"\ng.player.realm_index="+(world.equals("celestial")?"9":"3")+"\ng.player.layer=1\ng.player.immortal_power_converted=True\ng.player.opportunity=0\ng.settings['silent_events']=True\ng.settings['combat_popup']=False\ng.player.location_id=trial_sites.bound_site(g,e.maps,g.player.world)['location_id']\ng.player.hp=max_hp(g.player)\ng.player.mp=max_mp(g.player)\ne.store.save(g)");
                    async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("game.trial_site.enabled && game.trial_site.available && !document.querySelector('[data-panel-target=trial-site]').classList.contains('hidden')")),"DLC shortcut: "+world);
                    check(Boolean.TRUE.equals(js("game.trial_site.can_enter")),"Trial availability: "+world+" "+js("JSON.stringify({reason:game.trial_site.unavailable_reason,pending:game.pending_event,trial:game.trial})"));
                    js("window.__trialAge=game.player.age;UtilityPanels.open('trial-site');true");
                    waitForJs("getComputedStyle(document.querySelector('#trial-site-card')).opacity==='1'","Trial panel transition");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('.trial-site-floor').length===game.trial_site.total && !!document.querySelector('.trial-progress') && document.documentElement.scrollWidth<=innerWidth+1")),"Visual layers: "+world);
                    tapSelector("[data-trial-action=enter]");waitForJs("!busy && game.trial_site.active","Trial enter");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('.trial-mechanism').length===5")),"Five mechanisms");
                    tapSelector("[data-trial-choice=pause]");waitForJs("!busy && !game.trial_site.active","Trial pause");
                    tapSelector("[data-trial-action=enter]");waitForJs("!busy && game.trial_site.active","Trial resume");
                    for(int n=0;n<5;n++) {tapSelector("[data-trial-choice=c]");waitForJs("!busy","Trial choice");}
                    check(Boolean.TRUE.equals(js("game.trial_site.session.status==='ready' && !!document.querySelector('.trial-guardian-card')")),"Guardian projection");
                    capture("trial-sites-"+world+"-"+arguments.getString("orientation","portrait"));
                    tapSelector("[data-trial-action=fight]");waitForJs("!busy && game.trial_site.session.status==='won'","Trial combat");
                    tapSelector("[data-trial-action=claim]");waitForJs("!busy && game.trial_site.cleared===1","Trial reward");
                    check(Boolean.TRUE.equals(js("game.player.age===window.__trialAge && !game.trial_site.active")),"Zero-time settlement");
                }
                result.putString("trial_sites_scope","Eleven worlds, native taps, visual layer map, five choices, pause/resume, combat, rewards and zero time");
            } else if(phase.equals("market-release")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'新版市场安装包验收',spirit_root:'supreme_earth',path:'dao',seed:315,custom_start:{world:'human',realm_index:4}})});return g.id;})()");
                python("from cultivation_life import server\nfrom cultivation_life.rules import add_item\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\ng.pending_event=None\nadd_item(g.player,'spirit_stone',100000000)\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("!game.monster_civilizations.ui_available && document.querySelector('[data-panel-target=civilizations]').classList.contains('hidden')")),"Non-monster DLC entry must be hidden");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    tapSelector("[data-panel-target=market]");
                    tapSelector("[data-market-view=local]");
                    js("window.__search=document.querySelector('[aria-label=\"查找本地商品\"]');__search.value='矿|草|丹';__search.dispatchEvent(new Event('input',{bubbles:true}));true");
                    js("(()=>{const s=document.querySelector('[aria-label=匹配方式]');s.value='pattern';s.dispatchEvent(new Event('change'));})()");
                    waitForJs("document.querySelector('.economy-search-feedback').textContent.startsWith('找到')","APK worker regex did not complete");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('.economy-good').length>0 && Array.from(document.querySelectorAll('.economy-good b')).every(n=>/矿|草|丹/u.test(n.textContent))")),"APK regex results mismatch");
                    js("__search.value='[';__search.dispatchEvent(new Event('input',{bubbles:true}));true");
                    waitForJs("document.querySelector('.economy-search-feedback').textContent.includes('正则表达式无效')","APK regex error recovery");
                    js("__search.value='矿|草|丹';__search.dispatchEvent(new Event('input',{bubbles:true}));true");
                    waitForJs("document.querySelector('.economy-search-feedback').textContent.startsWith('找到')","APK search did not recover");
                    check(Boolean.TRUE.equals(js("document.querySelector('#market-card').scrollWidth<=document.querySelector('#market-card').clientWidth+1")),"APK market overflow");
                    capture("market-release-"+theme+"-"+arguments.getString("orientation","portrait"));
                    js("window.__marketRevision=game.map.economy.revision;window.__marketItem=document.querySelector('.economy-good [data-trade=buy]:not(:disabled)').closest('.economy-good').dataset.itemId;window.__marketStock=game.map.economy.rows.find(r=>r.id===__marketItem).stock;true");
                    tapSelector(".economy-good [data-trade=buy]:not(:disabled)");
                    waitForJs("!busy && game.map.economy.revision>__marketRevision && game.map.economy.rows.find(r=>r.id===__marketItem).stock===__marketStock-1","APK actual purchase");
                    tapSelector("[data-panel-target=map]");
                    tapSelector("#map-view-tabs button[aria-controls=map-economy]");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('#local-market-content').length===1 && !!document.querySelector('#map-economy #local-market-content') && document.querySelector('[aria-label=\"查找本地商品\"]').value==='矿|草|丹'")),"APK shared market state");
                }
                String monster=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'新版灵纹验收',spirit_root:'supreme_earth',path:'monster',monster_species_id:'fox',seed:315,custom_start:{world:'human',realm_index:4}})});return g.id;})()");
                async("loadGame("+JSONObject.quote(monster)+")");
                check(Boolean.TRUE.equals(js("game.monster_civilizations.ui_available && !document.querySelector('[data-panel-target=civilizations]').classList.contains('hidden')")),"Monster DLC entry missing");
                tapSelector("[data-panel-target=civilizations]");
                waitForJs("!!document.querySelector('.mc-tabs')","Packaged atlas load");
                check(Boolean.TRUE.equals(js("getComputedStyle(document.querySelector('.mc-tabs button'),'::before').width==='5px'")),"Packaged DLC seal stylesheet missing");
                capture("market-release-dlc-"+arguments.getString("orientation","portrait"));
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("document.querySelector('[data-panel-target=civilizations]').classList.contains('hidden') && !document.querySelector('#civilizations-card').classList.contains('panel-open')")),"APK path switch leaves expansion open");
                result.putString("market_release_scope","New signed APK: four themes, actual native market taps and purchases, regex Worker/error recovery, shared map inventory, path visibility and distinct DLC stylesheet");
            } else if(phase.equals("economic-force")) {
                python(assetText("economic-force-272.py"));
                result.putString("economic_force_scope","1666 packaged catalog entries; fresh and stale schema-10 equipment actual damage against golden light in all eleven worlds");
            } else if(phase.equals("civilizations")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'万灵原生验收',spirit_root:'supreme_earth',path:'monster',monster_species_id:'fox',seed:2100,custom_start:{world:'monster_realm',realm_index:7}})});return g.id;})()");
                    python(assetText("civilizations-2100.py")+"\nfrom cultivation_life import server\nprepare(server.ENGINE,"+JSONObject.quote(id)+")");
                    async("loadGame("+JSONObject.quote(id)+")");
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click();UtilityPanels.close('civilizations');true");async("GameThemes.saved");
                    tapSelector("[data-panel-target=civilizations]");
                    waitForJs("!!document.querySelector('.mc-region')","Atlas did not load");
                    tapSelector("[data-civilization-action=observe]");
                    waitForJs("!!document.querySelector('.mc-species') && !busy","Observation did not complete");
                    tapSelector("[data-civilization-action=protect]");waitForJs("!busy","Protection stayed busy");
                    waitForJs("document.querySelector('#civilizations-content').textContent.includes('现有护育安排')","Protection view not refreshed");
                    String currentRegion=(String)js("document.querySelector('.mc-region').dataset.region");
                    String otherRegion=(String)js("Array.from(document.querySelector('[aria-label=栖地记录]').options).find(o=>o.value!=="+JSONObject.quote(currentRegion)+").value");
                    python("from cultivation_life import server\nserver._mc_picker_before=server.ENGINE.store._path("+JSONObject.quote(id)+").read_bytes()");
                    tapSelector("[data-civilization-region="+JSONObject.quote(otherRegion)+"]");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('.mc-region').length===1 && !document.querySelector('[data-civilization-action=observe]')")),"Remote report must not expose local action");
                    tapSelector("[data-civilization-region="+JSONObject.quote(currentRegion)+"]");
                    check(Boolean.TRUE.equals(js("!!document.querySelector('.mc-region.current')")),"Current habitat report not restored");
                    python("from cultivation_life import server\nassert server.ENGINE.store._path("+JSONObject.quote(id)+").read_bytes()==server._mc_picker_before");
                    tapSelector("[data-civilization-tab=clans]");
                    js("document.querySelector('[aria-label=新氏族名称]').value='青丘原生氏';true");
                    tapSelector("[data-civilization-action=found]");
                    waitForJs("document.querySelector('.mc-clan-tree')?.textContent.includes('青丘原生氏') && !busy","Clan founding did not complete");
                    check(Boolean.TRUE.equals(js("document.querySelector('.mc-clan-tree').firstElementChild.classList.contains('current')")),"Own clan controls should come first");
                    check(Boolean.TRUE.equals(js("document.documentElement.scrollWidth<=innerWidth+1")),"Atlas mobile overflow");
                    capture("civilizations-clan-"+theme+"-"+arguments.getString("orientation","portrait"));
                    tapSelector("[data-civilization-tab=journal]");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('.mc-timeline li').length>0")),"Known journal empty");
                    tapSelector("[data-civilization-tab=ecology]");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('#civilizations-content svg').length>0")),"Ecology visualization missing");
                    capture("civilizations-ecology-"+theme+"-"+arguments.getString("orientation","portrait"));
                }
                result.putString("civilizations_scope","Four themes, native portrait/landscape real observation, protection, interactive habitat selection without movement or save writes, first-position own clan, founding, known journal and discovery-limited visual ecology");
            } else if(phase.equals("territory")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'地方原生验收',spirit_root:'supreme_earth',path:'dao',seed:2110,custom_start:{world:'human',realm_index:4,sect:'new',sect_name:'验收宗'}})});return g.id;})()");
                    python(assetText("territory-2110.py")+"\nfrom cultivation_life import server\nprepare(server.ENGINE,"+JSONObject.quote(id)+")");
                    async("loadGame("+JSONObject.quote(id)+")");
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click();UtilityPanels.close('map');true");async("GameThemes.saved");
                    tapSelector("[data-panel-target=map]");
                    check(Boolean.TRUE.equals(js("document.querySelector('#map-atlas').classList.contains('hidden')")),"Native text map should open separately");
                    tapSelector("#map-view-tabs [aria-controls=map-atlas]");
                    waitForJs("!!document.querySelector('#map-atlas svg') && !document.querySelector('#map-atlas').classList.contains('hidden')","Native road atlas did not load");
                    String destination=(String)js("game.map.current");
                    python("from cultivation_life import server\nserver._territory_native_before=server.ENGINE.store._path("+JSONObject.quote(id)+").read_bytes()");
                    tapSelector("[data-atlas-location="+JSONObject.quote(destination)+"]");
                    python("from cultivation_life import server\nassert server.ENGINE.store._path("+JSONObject.quote(id)+").read_bytes()==server._territory_native_before");
                    tapSelector("[data-atlas-view=decisions]");tapSelector("[data-organization-action=build_outpost]");
                    waitForJs("!busy && game.map.territory.locations.some(r=>r.outpost)","Native paid outpost did not complete");
                    python(assetText("territory-2110.py")+"\nfrom cultivation_life import server\nassert_outpost(server.ENGINE,"+JSONObject.quote(id)+")");
                    js("document.querySelector('[aria-label=地方政策]').value='patrol';true");
                    tapSelector("[data-organization-action=territory_policy]");waitForJs("!busy && game.map.locations.find(r=>r.current).influences.some(r=>r.owned && r.policy==='patrol')","Native policy vote failed");
                    capture("territory-map-"+theme+"-"+arguments.getString("orientation","portrait"));
                    tapSelector(".atlas-relocations>summary");js("document.querySelector('.atlas-relocation-form select').value="+JSONObject.quote(destination)+";true");
                    tapSelector(".atlas-relocation-form button");waitForJs("!busy && game.map.locations.find(r=>r.current).influences.some(r=>r.owned && r.headquarters)","Native headquarters vote failed");
                    python(assetText("territory-2110.py")+"\nfrom cultivation_life import server\nassert_relocated(server.ENGINE,"+JSONObject.quote(id)+")");
                    python("from cultivation_life import server\nserver._territory_native_before=server.ENGINE.store._path("+JSONObject.quote(id)+").read_bytes()");
                    for(String view:new String[]{"decisions","influence"}) {
                        tapSelector("[data-panel-target=intrigue]");
                        tapSelector("[data-territory-entry="+view+"]");
                        check(Boolean.TRUE.equals(js("document.querySelector('[data-atlas-view="+view+"]').getAttribute('aria-pressed')==='true' && !document.querySelector('#map-atlas').classList.contains('hidden') && document.querySelector('#map-locations').classList.contains('hidden')")),"Native DLC shortcut opened wrong subpage");
                    }
                    tapSelector("[data-atlas-display=list]");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('.atlas-region-meter progress').length>0")),"Native influence list missing");
                    capture("territory-list-"+theme+"-"+arguments.getString("orientation","portrait"));
                    python("from cultivation_life import server\nassert server.ENGINE.store._path("+JSONObject.quote(id)+").read_bytes()==server._territory_native_before");
                    check(Boolean.TRUE.equals(js("document.documentElement.scrollWidth<=innerWidth+1")),"Native territory atlas overflow");
                    async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("game.map.locations.find(r=>r.current).influences.some(r=>r.owned && r.value===100)")),"Native relocated headquarters did not persist");
                }
                result.putString("territory_scope","Four themes, independent atlas subpage, real SVG taps and two DLC shortcuts without state writes, influence list, local material outpost, policy majority, same-world relocation and persistence");
            } else if(phase.equals("organizations")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'势力原生验收',spirit_root:'supreme_earth',path:'dao',seed:290,custom_start:{world:'human',realm_index:4,sect:'new',sect_name:'验收宗'}})});return g.id;})()");
                    python(assetText("organizations-290.py")+"\nfrom cultivation_life import server\nprepare(server.ENGINE,"+JSONObject.quote(id)+")");
                    async("loadGame("+JSONObject.quote(id)+")");
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click();UtilityPanels.close('faction');true");async("GameThemes.saved");
                    tapSelector("[data-panel-target=faction]");tapSelector("#faction-card .organization-heritage > summary");
                    tapSelector("[data-heritage-action=heritage_learn]");waitForJs("!busy && game.faction.heritage.books[0].learned","Native free study");
                    tapSelector("#faction-card .organization-heritage > summary");tapSelector("[data-heritage-action=heritage_copy]");waitForJs("!busy","Native paid jade slip");
                    tapSelector("#faction-card .organization-heritage > summary");js("document.querySelector('.organization-heritage select').value='TECH_HUMAN_HERITAGE_2';true");
                    tapSelector("[data-heritage-action=heritage_add]");waitForJs("!busy && game.faction.heritage.books.length===2","Native inheritance donation");
                    tapSelector("#faction-card .organization-depot > summary");tapSelector("[data-depot-action=depot_request]");waitForJs("!busy && game.faction.contribution===9","Native contribution reservation");
                    tapSelector("#faction-card .organization-depot > summary");tapSelector("[data-depot-action=depot_cancel]");waitForJs("!busy && game.faction.contribution===10","Native contribution refund");
                    js("UtilityPanels.close('map');true");tapSelector("[data-panel-target=map]");tapSelector(".teleport-controls > summary");tapSelector("[data-teleport-build]");tapSelector("#game-confirm-accept");waitForJs("!busy && !!game.map.teleport.origin","Native owner-funded array construction");
                    capture("organizations-array-"+theme+"-"+arguments.getString("orientation","portrait"));
                    python(assetText("organizations-290.py")+"\nfrom cultivation_life import server\nactivities(server.ENGINE,"+JSONObject.quote(id)+",'scheduled')");async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("document.querySelector('[data-navigation-category=economy]').classList.contains('navigation-notice')")),"Activity category reminder");
                    tapSelector("[data-navigation-category=common]");check(Boolean.TRUE.equals(js("document.querySelectorAll('#navigation-current-events [data-navigation-shortcut]').length===2")),"Automatic common activities");
                    tapSelector("#navigation-current-events [data-navigation-shortcut=auction]");check(Boolean.TRUE.equals(js("document.querySelector('#auction-title').textContent.includes('预告')")),"Auction notice real click");
                    python(assetText("organizations-290.py")+"\nfrom cultivation_life import server\nactivities(server.ENGINE,"+JSONObject.quote(id)+",'open')");async("loadGame("+JSONObject.quote(id)+")");
                    tapSelector("[data-navigation-category=common]");tapSelector("#navigation-current-events [data-navigation-shortcut=exchange]");check(Boolean.TRUE.equals(js("document.querySelector('#exchange-description').textContent.includes('剩余')")),"Exchange event real click");
                    python(assetText("organizations-290.py")+"\nfrom cultivation_life import server\nactivities(server.ENGINE,"+JSONObject.quote(id)+",'closed')\nclan(server.ENGINE,"+JSONObject.quote(id)+")");async("loadGame("+JSONObject.quote(id)+")");
                    tapSelector("[data-navigation-category=common]");check(Boolean.TRUE.equals(js("!document.querySelector('#navigation-current-events')")),"Expired shortcuts disappear");tapSelector("#navigation-close");
                    js("UtilityPanels.close('family');true");tapSelector("[data-panel-target=family]");tapSelector("[data-family*='join']:not(:disabled)");waitForJs("!busy && game.family.exists && game.family.player_member_type==='外姓修士'","Native outsider clan admission");
                    python(assetText("organizations-290.py")+"\nfrom cultivation_life import server\nsucceed(server.ENGINE,"+JSONObject.quote(id)+")");async("loadGame("+JSONObject.quote(id)+")");
                    enterNumericField("[data-family-name]","承宗更名","原生本家仙族");
                    runOnMainSync(()->((android.view.inputmethod.InputMethodManager)activity.getSystemService(android.content.Context.INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(web.getWindowToken(),0));js("document.activeElement.blur();true");Thread.sleep(400);
                    tapSelector("[data-family*='rename']");waitForJs("!busy && !game.family.can_rename","Native once-only clan rename");async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("game.family.player_member_type==='本家' && !document.querySelector('[data-family-name]') && document.documentElement.scrollWidth<=innerWidth+1")),"Succession and responsive persistence");
                    capture("organizations-family-"+theme+"-"+arguments.getString("orientation","portrait"));
                    python("from cultivation_life import server\ng=server.ENGINE._load("+JSONObject.quote(id)+")\nassert g.family.name=='原生本家仙族'\nassert g.economy_v2['teleport_arrays']\nassert any(i.technique_id=='TECH_HUMAN_HERITAGE_1' for i in g.player.inventory)");
                }
                result.putString("organizations_scope","Four themes, actual free learning, paid copy, decision donation, contribution refund, array confirmation, temporary activity lifecycle, outsider clan join, succession and one rename");
            } else if(phase.equals("navigation")) {
                async("GameNavigation.ready");
                if("landscape".equals(arguments.getString("orientation"))) check(Boolean.TRUE.equals(async("fetch('/api/ui-preferences').then(r=>r.json()).then(p=>p.navigation.pins.includes('spirit-voisinage'))")),"Navigation pin survives process restart and new server origin");
                for(String theme:new String[]{"a","b","d","f"}) {
                    for(int rank:new int[]{1,4}) {
                        js("document.querySelector('#new-game-button').click();window.__navigationOld=game?.id;document.querySelector('[data-theme-picker=start] [data-theme-choice="+theme+"]').click();document.querySelector('#custom-start').open=true;true");
                        async("GameThemes.saved");
                        js("document.querySelector('#custom-root').value='otherworld';document.querySelector('#custom-path').value='dao';document.querySelector('#custom-path').dispatchEvent(new Event('change'));document.querySelector('#custom-world').value='spirit';document.querySelector('#custom-world').dispatchEvent(new Event('change'));document.querySelector('#custom-realm').value='8';document.querySelector('#custom-realm').dispatchEvent(new Event('change'));document.querySelector('#custom-tendency').value='strike';document.querySelector('#custom-domain-rank').value='"+rank+"';true");
                        tapSelector("#custom-start-submit");
                        waitForJs("!busy && game && game.id!==window.__navigationOld","Navigation custom creation",60000);
                        check(Boolean.TRUE.equals(js("document.querySelectorAll('[data-navigation-category]').length===6 && document.documentElement.scrollWidth<=innerWidth+1 && [...document.querySelectorAll('#navigation-bar button')].every(b=>b.getBoundingClientRect().height>=44)")),"Six stationary touch targets");
                        tapSelector("[data-panel-target=spirit-voisinage]");
                        check(Boolean.TRUE.equals(js("document.querySelector('#spirit-voisinage-card').classList.contains('panel-open') && document.querySelector('#spirit-voisinage-content').textContent.includes('Lv"+rank+"') && game.aperture.available==="+(rank>=4?"true":"false"))),"Lower-world study and level-four gate");
                        tapSelector("[data-navigation-category=practice]");
                        if(!Boolean.TRUE.equals(js("document.querySelector('[data-navigation-pin=spirit-voisinage]').getAttribute('aria-pressed')==='true'"))) tapSelector("[data-navigation-pin=spirit-voisinage]");
                        tapSelector("[data-navigation-tab=common]");
                        check(Boolean.TRUE.equals(js("!!document.querySelector('[data-navigation-shortcut=spirit-voisinage]')")),"Common field pin");
                        runOnMainSync(()->activity.onBackPressed());
                        waitForJs("!document.querySelector('#navigation-menu').open && document.querySelector('#spirit-voisinage-card').classList.contains('panel-open')","Back closes directory only");
                        tapSelector("[data-navigation-category=worlds]");
                        enterNumericField("#navigation-search","查找地图","地图");
                        runOnMainSync(()->((android.view.inputmethod.InputMethodManager)activity.getSystemService(android.content.Context.INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(web.getWindowToken(),0));
                        js("document.activeElement.blur();true");Thread.sleep(400);
                        tapSelector("[data-panel-target=map]");
                        check(Boolean.TRUE.equals(js("document.querySelector('#navigation-search').value==='地图'")),"Actual search result selected without clearing filter");
                        check(Boolean.TRUE.equals(js("document.querySelector('#map-card').classList.contains('panel-open') && document.querySelector('#map-current').textContent==='当前：'+game.map.current_name")),"Fresh deferred map");
                        for(String category:new String[]{"common","practice","craft","economy","people","worlds"}) {
                            tapSelector(Boolean.TRUE.equals(js("document.querySelector('#navigation-menu').open"))?"[data-navigation-tab="+category+"]":"[data-navigation-category="+category+"]");
                            check(Boolean.TRUE.equals(js("document.querySelector('#navigation-menu').scrollWidth<=document.querySelector('#navigation-menu').clientWidth+1")),"Directory overflow: "+category);
                        }
                        capture("navigation-"+theme+"-"+rank+"-"+arguments.getString("orientation","portrait"));
                        tapSelector("#navigation-close");
                        async("GameNavigation.saved");
                        async("loadGame(game.id)");
                        tapSelector("[data-navigation-category=common]");
                        check(Boolean.TRUE.equals(js("!!document.querySelector('[data-navigation-shortcut=spirit-voisinage]')")),"Pin persists after reload");
                        tapSelector("#navigation-close");
                    }
                }
                result.putString("navigation_scope","Four themes, native lower-world Lv1/Lv4 creation, six categories, pin, search, Back and fresh map");
            } else if(phase.equals("economy-handbook")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'资粮百科验收',preset_id:'nether_upper',monster_species_id:'serpent',seed:270})});await loadGame(g.id);return g.id;})()");
                python("from cultivation_life import server\ne=server.ENGINE\nserver._handbook_release_snapshot=e.store._path("+JSONObject.quote(id)+").read_bytes()");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click();true");async("GameThemes.saved");
                    js("UtilityPanels.open('settings');true");
                    for(String chapter:new String[]{"economic-materials","economic-recipes","economic-demand","economic-estates","economic-war"}) {
                        tapSelector("[data-chapter="+chapter+"] summary");
                        check(Boolean.TRUE.equals(js("document.querySelector('[data-chapter="+chapter+"]').open && document.querySelector('#settings-card').scrollWidth<=document.querySelector('#settings-card').clientWidth+2")),"Economic handbook overflow: "+theme+chapter);
                        tapSelector("[data-chapter="+chapter+"] summary");
                    }
                    check(Boolean.TRUE.equals(js("!['分桶','缓存','代表商品','后台循环'].some(w=>JSON.stringify(TutorialHandbook.build(configData,game).filter(c=>c.id.startsWith('economic-'))).includes(w))")),"Internal economy vocabulary visible");
                    capture("economy-handbook-270-"+theme);
                    js("UtilityPanels.close('settings');true");
                }
                python("from cultivation_life import server\ne=server.ENGINE\nassert e.store._path("+JSONObject.quote(id)+").read_bytes()==server._handbook_release_snapshot");
                js("showStart();true");tapSelector("#achievement-open");
                waitForJs("!document.querySelector('#achievement-screen').classList.contains('hidden') && document.querySelector('#achievement-groups').textContent.includes('本相初铭')","Upper achievements not displayed");
                check(Boolean.TRUE.equals(js("['万战称王','五阀有席','奉愿神使','照魂见我','八部立命','魔域至臻'].every(n=>document.querySelector('#achievement-groups').textContent.includes(n)) && achievementCatalog.achievements.find(r=>r.id==='monster_true_form_confirmed').source.id==='official.monster-bloodlines'")),"Achievement source or institution entries mismatch");
                check(Boolean.TRUE.equals(js("document.querySelector('#achievement-screen').scrollWidth<=document.querySelector('#achievement-screen').clientWidth+2")),"Achievement mobile overflow");
                result.putString("economy_handbook_scope","Five player-facing economy chapters, four themes, native reading taps, unchanged save/RNG/time, real upper achievement list and DLC sources");
            } else if(phase.equals("soul-forms")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'照魂原生验收',preset_id:'reincarnation_upper',seed:260})});return g.id;})()");
                // Resume an already elapsed contemplation, avoiding unrelated yearly incidents in the UI fixture.
                python("from cultivation_life import server\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.player.world_voisinages.setdefault('reincarnation',{})['contemplation']={'cause':'life_death','elapsed':100,'required':100}\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                tapSelector("[data-panel-target=upper-voisinage]");
                tapSelector("[data-soul-form] button");
                waitForJs("!busy && game.pending_event?.id==='EVT_SOUL_CONTEMPLATION'","Soul contemplation event");
                js("UtilityPanels.close('upper-voisinage');true");
                tapSelector("#event-choices button:first-child");
                waitForJs("!busy && !!game.upper_voisinages.soul_form.blueprint","Native soul confirmation");
                tapSelector("[data-panel-target=upper-voisinage]");
                tapSelector("#upper-voisinage-content > details:last-of-type summary");
                tapSelector("#upper-voisinage-content > details:last-of-type button:last-child");
                waitForJs("!busy && game.upper_voisinages.soul_form.level===1","Native soul learning");
                tapSelector("#upper-voisinage-content > details:last-of-type button:first-of-type");
                waitForJs("!busy && game.upper_voisinages.rows[game.upper_voisinages.rows.length-1].active","Native soul selection");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click();true");async("GameThemes.saved");
                    check(Boolean.TRUE.equals(js("document.querySelector('#upper-voisinage-card').scrollWidth<=document.querySelector('#upper-voisinage-card').clientWidth+1")),"Soul mobile overflow");
                    capture("soul-260-"+theme);
                }
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.upper_voisinages.soul_form.level===1")),"Soul reload");
                python("from cultivation_life import server\nfrom cultivation_life.rules import opportunity_required\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\ng.player.layer=9\ng.player.opportunity=opportunity_required(g.player)\ng.player.awaiting_major_breakthrough=True\ne.store.save(g)\ne.breakthrough(g.id)");
                async("loadGame("+JSONObject.quote(id)+")");
                js("UtilityPanels.close('upper-voisinage');true");
                tapSelector("#event-choices button:first-child");
                waitForJs("!busy && !!game.last_combat_report && !game.active_trial","Native survival trial result");
                check(Boolean.TRUE.equals(js("game.last_combat_report.objective==='survive' && game.last_combat_report.total_rounds<=5")),"Survival objective");
                result.putString("soul_scope","Four themes, real event choice, paid cultivation, selection/reload and survival trial; resumed elapsed contemplation fixture");
            } else if(phase.equals("custom-start-eligibility")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    for(int realm:new int[]{8,9}) {
                        js("document.querySelector('#new-game-button').click();window.__customOld=game?.id;document.querySelector('[data-theme-picker=start] [data-theme-choice="+theme+"]').click();document.querySelector('#custom-start').open=true;true");
                        async("GameThemes.saved");
                        String world=realm==8?"spirit":"celestial";
                        js("document.querySelector('#custom-root').value='otherworld';document.querySelector('#custom-path').value='dao';document.querySelector('#custom-path').dispatchEvent(new Event('change'));document.querySelector('#custom-world').value='"+world+"';document.querySelector('#custom-world').dispatchEvent(new Event('change'));document.querySelector('#custom-realm').value='"+realm+"';document.querySelector('#custom-realm').dispatchEvent(new Event('change'));document.querySelector('#custom-body').value='0';true");
                        tapSelector("#custom-start-submit");
                        waitForJs("!busy && game && game.id!==window.__customOld && game.player.realm_index==="+realm,"Native eligible custom creation",60000);
                        String id=(String)js("game.id");
                        python("from cultivation_life import server\ng=server.ENGINE.store.load("+JSONObject.quote(id)+")\np=g.player\nassert p.immortal_power_converted == "+(realm==9?"True":"False")+"\nassert p.body_training == 0\nassert not p.body_technique.requires_immortal_power or p.immortal_power_converted\nassert p.body_technique.required_body_training <= p.body_training");
                        async("loadGame("+JSONObject.quote(id)+")");
                        check(Boolean.TRUE.equals(js("game.player.immortal_power_converted==="+(realm==9?"true":"false")+" && document.documentElement.scrollWidth<=innerWidth+2")),"Native custom conversion and reload");
                    }
                }
                result.putString("custom_eligibility_scope","Four themes, native Mahayana/true-immortal creation, zero body training, conversion qualification and reload");
            } else if(phase.equals("release-2130")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('#new-game-button').click();window.__presetOld=game?.id;document.querySelector('[data-theme-picker=start] [data-theme-choice="+theme+"]').click();document.querySelector('#custom-start').open=true;document.querySelector('#custom-realm').value='4';document.querySelector('#custom-realm').dispatchEvent(new Event('change'));document.querySelector('#custom-sect').value='new';document.querySelector('#custom-sect').dispatchEvent(new Event('change'));document.querySelector('#custom-sect-name').value='原生听松宗';document.querySelector('#custom-family').value='new';document.querySelector('#custom-family').dispatchEvent(new Event('change'));document.querySelector('#custom-family-name').value='原生听松家';true");
                    async("GameThemes.saved");
                    File preset=new File(getTargetContext().getExternalFilesDir(null),"verification/start-preset-2130.json");
                    preset.getParentFile().mkdirs();if(preset.exists())check(preset.delete(),"Clear preset fixture");
                    Intent document=new Intent().setData(android.net.Uri.fromFile(preset));
                    android.content.IntentFilter exportFilter=new android.content.IntentFilter(Intent.ACTION_CREATE_DOCUMENT);exportFilter.addCategory(Intent.CATEGORY_OPENABLE);exportFilter.addDataType("application/json");
                    ActivityMonitor exporting=addMonitor(exportFilter,new ActivityResult(Activity.RESULT_OK,document),true);
                    tapSelector("#custom-preset-export");
                    long presetDeadline=System.currentTimeMillis()+20000;
                    while((!preset.isFile()||preset.length()==0)&&System.currentTimeMillis()<presetDeadline)Thread.sleep(100);
                    removeMonitor(exporting);check(preset.length()>0,"Preset export document");
                    JSONObject exported=new JSONObject(new String(java.nio.file.Files.readAllBytes(preset.toPath()),StandardCharsets.UTF_8));
                    check(exported.getString("format").equals("wendao-custom-start"),"Preset file format");
                    check(exported.getJSONObject("payload").getJSONObject("custom_start").getString("sect_name").equals("原生听松宗"),"Preset export values");
                    exported.put("test_padding",new String(new char[180000]).replace('\0','x'));
                    java.nio.file.Files.write(preset.toPath(),exported.toString().getBytes(StandardCharsets.UTF_8));
                    js("document.querySelector('#custom-sect-name').value='待恢复';true");
                    android.content.IntentFilter importFilter=new android.content.IntentFilter(Intent.ACTION_OPEN_DOCUMENT);importFilter.addCategory(Intent.CATEGORY_OPENABLE);importFilter.addDataType("application/json");
                    ActivityMonitor importing=addMonitor(importFilter,new ActivityResult(Activity.RESULT_OK,document),true);
                    tapSelector("#custom-preset-import");
                    waitForJs("document.querySelector('#custom-sect-name').value==='原生听松宗'","Chunked preset restore");removeMonitor(importing);
                    tapSelector("#custom-start-submit");waitForJs("!busy&&game&&game.id!==__presetOld&&game.faction.name==='原生听松宗'","Actual preset creation",60000);
                    String id=(String)js("game.id");
                    python("from cultivation_life import server\nserver._preset_nav_before=server.ENGINE.store._path("+JSONObject.quote(id)+").read_bytes()");
                    for(String panel:new String[]{"faction","family","relationship","inventory","transformation","captive","merchant"}) {
                        tapSelector("[data-panel-target="+panel+"]");
                        int count=((Number)js("document.querySelector('#"+panel+"-card .panel-page-tabs')?.children.length||0")).intValue();
                        check(count>0,"Parallel subpage tabs: "+panel);
                        for(int i=0;i<count;i++) {
                            tapSelector("#"+panel+"-card .panel-page-tabs>button:nth-child("+(i+1)+")");
                            check(Boolean.TRUE.equals(js("document.querySelector('#"+panel+"-card .panel-page-tabs').querySelectorAll('[aria-selected=true]').length===1")),"Single active tab");
                        }
                        check(Boolean.TRUE.equals(js("document.querySelector('#"+panel+"-card').scrollWidth<=document.querySelector('#"+panel+"-card').clientWidth+1")),"Subpage overflow: "+panel);
                    }
                    python("from cultivation_life import server\nassert server.ENGINE.store._path("+JSONObject.quote(id)+").read_bytes()==server._preset_nav_before");
                    tapSelector("[data-panel-target=intrigue]");
                    js("(()=>{const s=document.querySelector('.intrigue-sect [aria-label=掌门候选人]');s.value=[...s.options].find(o=>o.value!=='player').value;window.__leader=s.value;})();true");
                    tapSelector(".intrigue-sect .intrigue-position button");waitForJs("!busy&&game.intrigue_system.sections.find(s=>s.kind==='sect').positions.find(p=>p.id==='leader').holder_id===__leader","Native leader appointment");
                    check(Boolean.TRUE.equals(js("game.intrigue_system.sections.find(s=>s.kind==='sect').control_authority")),"Appointment preserves control");
                    capture("release-2130-"+theme+"-"+arguments.getString("orientation","portrait"));
                }
                result.putString("release_2130_scope","Four themes, real native preset document export/import with chunked 180K file, actual creation, seven parallel panels and leader appointment without authority transfer");
            } else if(phase.equals("custom-start")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('#new-game-button').click();window.__customOld=game?.id;document.querySelector('[data-theme-picker=start] [data-theme-choice="+theme+"]').click();document.querySelector('#custom-start').open=true;true");
                    async("GameThemes.saved");
                    js("document.querySelectorAll('#custom-inventory button').forEach(n=>n.click());true");
                    js("document.querySelector('#custom-realm').value='3';document.querySelector('#custom-realm').dispatchEvent(new Event('change'));document.querySelector('#custom-sense').value='23';document.querySelector('#custom-sect').value='new';document.querySelector('#custom-sect').dispatchEvent(new Event('change'));document.querySelector('#custom-sect-name').value='原生青玉宗';document.querySelector('#custom-item-search').value='spirit_stone';document.querySelector('#custom-item-search').dispatchEvent(new Event('input'));document.querySelector('#custom-item').value='spirit_stone';document.querySelector('#custom-quantity').value='1000000';true");
                    tapSelector("#custom-add-item");
                    enterNumericField("#custom-sense", "自定义神识", "23");
                    enterNumericField("#custom-bag-spirit_stone", "行囊数量", "1000000");
                    runOnMainSync(()->((android.view.inputmethod.InputMethodManager)activity.getSystemService(android.content.Context.INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(web.getWindowToken(),0));
                    js("document.activeElement.blur();true");Thread.sleep(400);
                    check(Boolean.TRUE.equals(js("document.querySelector('#custom-bag-spirit_stone').value==='1000000' && document.documentElement.scrollWidth<=innerWidth+1")),"Custom bag and responsive layout");
                    capture("custom-start-"+theme+"-"+arguments.getString("orientation","portrait"));
                    tapSelector("#custom-start-submit");
                    waitForJs("!busy && game && game.id!==window.__customOld && game.faction.name==='原生青玉宗'","Native custom creation",60000);
                    check(Boolean.TRUE.equals(js("game.player.divine_sense.level===23 && document.querySelector('#divine-sense').textContent.includes('筑基中期')")),"Independent sense display");
                    check(Boolean.TRUE.equals(js("game.faction.join_age===game.player.age")),"Initial faction admission age");
                    tapSelector("[data-panel-target=faction]");
                    tapSelector("[data-organization=sect]>summary");
                    js("document.querySelector('[data-organization=sect] input').value='100000';true");
                    tapSelector("[data-organization=sect] [data-org-business=organization_fund]");
                    waitForJs("!busy && game.faction.finance.balance===100000","Native organizational funding");
                    js("document.querySelector('[data-organization=sect]').open=true;true");
                    tapSelector("[data-organization=sect] [data-org-business=create]");
                    waitForJs("!busy && game.fleet_network.fleets.some(f=>f.player_controlled&&f.owner_kind==='sect')","Native organization caravan");
                    js("document.querySelector('[data-organization=sect]').open=true;document.querySelector('#enterprise-panel-sect').open=true;document.querySelector('#enterprise-panel-sect select[aria-label=购置产业]').value='farm';true");
                    tapSelector("#enterprise-panel-sect [data-estate-action=buy]");
                    waitForJs("!busy && game.map.economy.enterprises.owned.length>0","Native organizational deed");
                    js("document.querySelector('[data-organization=sect]').open=true;document.querySelector('#enterprise-panel-sect').open=true;document.querySelector('#enterprise-panel-sect [data-estate-id]').open=true;true");
                    tapSelector("#enterprise-panel-sect [data-estate-action=entrust]");
                    waitForJs("!busy && game.map.economy.enterprises.owned[0].entrusted","Native steward commission");
                    async("loadGame(game.id)");
                    check(Boolean.TRUE.equals(js("game.map.economy.enterprises.owned[0].entrusted && game.player.divine_sense.level===23")),"Native commission and sense reload");
                }
            } else if(phase.equals("start-layout")) {
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
                waitForJs("!busy && game?.player.path==='buddhist' && !document.querySelector('#game-screen').classList.contains('hidden')", "Native Buddhist quick start",60000);
                check(Boolean.TRUE.equals(js("document.querySelector('#action-card [data-tutorial-open] svg')!==null")), "Tutorial icon survives game rendering");
                capture("start-layout");
                js("document.querySelector('#new-game-button').click();document.querySelector('[data-preset-id=lost_world]').closest('details').open=true;true");
                check(Boolean.TRUE.equals(js("document.querySelector('[data-preset-id=lost_world]').disabled")), "Lost start requires path");
                js("(()=>{const p=document.querySelector('[data-quick-path]');p.value='monster';p.dispatchEvent(new Event('change'));})()");
                check(Boolean.TRUE.equals(js("document.querySelector('[data-preset-id=lost_world]').disabled && !document.querySelector('[data-quick-species]').hidden")), "Lost monster start requires species");
                js("(()=>{const s=document.querySelector('[data-quick-species]');s.value='serpent';s.dispatchEvent(new Event('change'));})()");
                tapSelector("[data-preset-id=lost_world]");
                waitForJs("!busy && game?.player.world==='lost' && game.player.path==='monster'", "Native lost monster start",60000);
                tapSelector("[data-panel-target=map]");
                check(Boolean.TRUE.equals(js("game.map.locations.length===4 && game.map.locations.every(l=>Object.values(l.qi_concentrations).every(v=>Number.isFinite(v)&&v>0)) && document.querySelectorAll('#map-locations .map-location').length===4")), "Generated lost maps and finite qi");
                capture("lost-quick-start");
                tapSelector("[data-panel-target=faction]");
                tapSelector("#faction-card .spatial-society .exploration-row > button:not([disabled]):last-child");
                waitForJs("!busy && !!game.spatial.scene.joined_sect", "Lost native sect membership");
                tapSelector("[data-panel-target=family]");
                tapSelector("#family-card .spatial-society .exploration-row > button");
                waitForJs("!busy && game.spatial.scene.society.families[0].here", "Lost native family site");
                tapSelector("#family-card .spatial-society .exploration-row > button");
                waitForJs("!busy && game.spatial.scene.society.families[0].joined", "Lost native family membership");
                capture("lost-family-native");
                tapSelector("#family-toggle");
                tapSelector("[data-action=rest]");
                waitForJs("!busy && game.pending_event && game.pending_event.id.startsWith('EVT_WANDER_SHARED_')", "Lost native shared event");
                tapSelector("#event-choices button:last-child");
                waitForJs("!busy && !game.pending_event", "Lost native event completion");
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
                check(Boolean.TRUE.equals(js("GameNavigation.isCompact() && !!document.querySelector('#navigation-grid [data-panel-target=heavens][data-navigation-group=worlds]') && !document.querySelector('.left-dock [data-panel-target=heavens]')")),"Heavens belongs to Android worlds category");
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
                    python("from cultivation_life import server\nfrom cultivation_life.rules import opportunity_required,max_hp,max_mp,add_item\ne=server.ENGINE\ng=e.store.load("+JSONObject.quote(id)+")\np=g.player\np.world="+JSONObject.quote(world)+"\np.path={'asura':'demonic','nether':'monster','reincarnation':'ghost'}[p.world]\nfrom cultivation_life.system.upper_institutions import definition\np.location_id=definition(g)['location']\np.world_voisinages={}\np.opportunity=opportunity_required(p)\np.hp=max_hp(p)\np.mp=max_mp(p)\np.immortal_aperture['current']=0\nadd_item(p,'spirit_stone',1000000)\ng.pending_event=None\nif g.heavenly_court: g.heavenly_court['open_election']=None\ne.store.save(g)");
                    async("loadGame("+JSONObject.quote(id)+")");
                    tapSelector("[data-panel-target=upper-voisinage]");
                    tapSelector("#upper-voisinage-content > details summary");
                    tapSelector("#upper-voisinage-content > details button");
                    waitForJs("!busy && game.upper_voisinages.rows[0].level===1 && game.upper_voisinages.rows[0].active","Native domain acquisition");
                    tapSelector("#upper-voisinage-content > details button:last-child");
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
                            waitForPanelReady("#"+panel+"-card");
                            check(Boolean.TRUE.equals(js("(()=>{const e=document.querySelector('#"+panel+"-card');return !e.classList.contains('hidden')&&e.scrollWidth<=e.clientWidth+1})()")),"Upper voisinage panel overflow "+world+theme);
                        }
                        js("UtilityPanels.open('upper-voisinage');true");capture("upper-voisinage-"+world+"-"+theme+"-1562");
                    }
                    js("UtilityPanels.open('immortal-aperture');true");tapSelector("#immortal-aperture-content button");
                    waitForJs("!busy && game.aperture.current>0","Native energy refinement");
                    async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("game.upper_voisinages.rows[0].level===2&&game.aperture.current>0")),"Upper cultivation persisted");
                }
                String trueFormId=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'本相铸域原生验收',preset_id:'nether_upper',monster_species_id:'avian',seed:251})});await loadGame(g.id);return g.id;})()");
                tapSelector("[data-panel-target=upper-voisinage]");
                waitForJs("!!document.querySelector('[data-true-form-action=true_form_confirm]')","True form preview");
                double trueFormEnergy=((Number)js("game.aperture.current")).doubleValue();
                tapSelector("[data-true-form-action=true_form_confirm]");
                waitForJs("!busy && !!game.upper_voisinages.true_form.blueprint","Native blueprint confirmation");
                check(((Number)js("game.aperture.current")).doubleValue()==trueFormEnergy,"Blueprint must not refill energy");
                tapSelector("#upper-voisinage-content > details:last-of-type summary");
                tapSelector("#upper-voisinage-content > details:last-of-type button:last-child");
                waitForJs("!busy && game.upper_voisinages.true_form.level===1","Native true form learning");
                tapSelector("#upper-voisinage-content > details:last-of-type button:first-of-type");
                waitForJs("!busy && game.upper_voisinages.rows[game.upper_voisinages.rows.length-1].active","Native true form selection");
                capture("true-form-251");
                async("loadGame("+JSONObject.quote(trueFormId)+").then(()=>true)");
                check(Boolean.TRUE.equals(js("game.upper_voisinages.true_form.level===1")),"True form survives reload");
                String ghostBirthId=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'魂契开局原生验收',preset_id:'ghost_void',seed:251})});return g.id;})()");
                python("from cultivation_life import server\np=server.ENGINE.store.load("+JSONObject.quote(ghostBirthId)+").player\nassert p.ghost_bound_souls and p.ghost_soul_slots and p.ghost_wangsheng_energy>0");
                result.putString("true_form_scope","Native preview, immutable confirmation, paid cultivation, selection, reload and ghost attained birth passed");
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
                    waitForPanelReady("#relationship-card");
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
            } else if(phase.equals("war-logistics")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'军需验收',preset_id:'core',seed:419})});return g.id;})()");
                    python("from cultivation_life import server\nfrom cultivation_life.system.economy import depot, organizations\nfrom cultivation_life.system.economy.ledger import transfer_value\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.player.realm_index=4\ng.player.faction_id='tianjian'\ng.player.faction_contribution=10\ng.player.location_id=g.sects['tianjian'].location_id\nfor identity in ('tianjian','wanmo'):\n x=g.sects[identity]\n organizations.register(g,'sect',identity,x.world)\n transfer_value(g,'background:human',depot.treasury(g,x),1000000,'原生军需验收')\ne._start_war(g,'sect','tianjian','wanmo',initiated_by_player=True)\nx=g.sects['tianjian']\nm=g.economy_v2['markets']['human:'+x.location_id]\nk=next(k for k,v in depot.catalog('human').items() if v['kind']=='item' and v['tier']<=5 and m['commodities'].get(v['id'],{}).get('stock',0)>=3)\ndepot.purchase(g,e.maps,x,k,3)\nfor n in depot.seniors(g,x):n.affinity=100\ne.store.save(g)");
                    async("loadGame("+JSONObject.quote(id)+")");
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    if(Boolean.TRUE.equals(js("!document.querySelector('#war-card').classList.contains('panel-open')")))tapSelector("[data-panel-target=war]");
                    check(Boolean.TRUE.equals(js("document.querySelector('.war-supply-card').parentElement.textContent.includes('敌情未明')")),"Enemy supplies hidden");
                    tapSelector("[data-war-strategy=scout]");waitForJs("!busy && document.querySelector('[data-war-strategy=scout]').disabled","Native scouting charged once");
                    check(Boolean.TRUE.equals(js("document.querySelector('#war-card').scrollWidth<=document.querySelector('#war-card').clientWidth+2")),"War responsive layout");
                    capture("war-logistics-"+theme+"-"+arguments.getString("orientation","portrait"));
                    tapSelector("[data-panel-target=faction]");tapSelector("#faction-card .organization-depot > summary");tapSelector("[data-depot-action=depot_request]");waitForJs("!busy","Native requisition");
                    if(Boolean.TRUE.equals(js("!document.querySelector('#faction-card .organization-depot').open")))tapSelector("#faction-card .organization-depot > summary");
                    check(Boolean.TRUE.equals(js("document.querySelector('[data-depot-action=depot_review]').disabled")),"Early approval blocked");
                    python("from cultivation_life import server\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\ng.diplomacy_unit+=1\ne.store.save(g)");async("loadGame("+JSONObject.quote(id)+")");
                    if(Boolean.TRUE.equals(js("!document.querySelector('#faction-card .organization-depot').open")))tapSelector("#faction-card .organization-depot > summary");
                    tapSelector("[data-depot-action=depot_review]");waitForJs("!busy","Native elder approval");
                    if(Boolean.TRUE.equals(js("!document.querySelector('#faction-card .organization-depot').open")))tapSelector("#faction-card .organization-depot > summary");
                    tapSelector("[data-depot-action=depot_collect]");waitForJs("!busy && document.querySelector('#faction-card .organization-depot').textContent.includes('已领取')","Native collection");
                    String cid=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'仙元验收',preset_id:'true_immortal',seed:9921})});return g.id;})()");
                    python("from cultivation_life import server\ne=server.ENGINE\ng=e._load("+JSONObject.quote(cid)+")\ng.pending_event=None\ng.heavenly_court['open_election']=None\ng.player.immortal_conversion_stage=0\ng.player.immortal_power_converted=False\ng.player.opportunity=100\ne.store.save(g)");async("loadGame("+JSONObject.quote(cid)+")");
                    tapSelector("[data-panel-target=immortal-conversion]");tapSelector("#immortal-conversion-card button[data-doctrine-action=convert]");
                    waitForJs("!busy && game.player.immortal_conversion_stage===1","Native opportunity conversion");
                    check(Boolean.TRUE.equals(js("document.querySelector('#immortal-conversion-card button[data-doctrine-action=convert]').disabled")),"Insufficient opportunity blocked");
                    capture("conversion-"+theme+"-"+arguments.getString("orientation","portrait"));
                    String aid=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'煞元验收',preset_id:'asura_upper',seed:9922})});return g.id;})()");
                    python("from cultivation_life import server\ne=server.ENGINE\ng=e._load("+JSONObject.quote(aid)+")\ng.pending_event=None\ng.active_trial=None\ng.player.asura_cultivation['conversion']=0\ng.player.opportunity=100\ne.store.save(g)");async("loadGame("+JSONObject.quote(aid)+")");
                    tapSelector("[data-panel-target=asura-conversion]");tapSelector("[data-asura-action=convert]");waitForJs("!busy && game.asura.conversion===1","Native paid Asura conversion");
                    check(Boolean.TRUE.equals(js("document.querySelector('[data-asura-action=convert]').disabled")),"Asura opportunity checked");

                }
                result.putString("war_logistics_scope","Four themes, hidden enemy stock, real scout and delayed approval/collection, paid conversion, narrow layouts");
            } else if(phase.equals("economy-governance")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'商势验收',preset_id:'core',seed:419})});return g.id;})()");
                    python("from cultivation_life import server\nfrom cultivation_life.system.economy.ledger import transfer_value\nfrom cultivation_life.system.faction_geography import faction_site\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.player.realm_index=4\ng.player.next_tribulation_age=None\ng.player.faction_id='tianjian'\ng.sects['tianjian'].founded_by_player=True\ntransfer_value(g,'background:human','player',10000000,'验收资本')\nr=e._war_relation(g,'sect','tianjian','wanmo')\ne._set_diplomatic_relation(g,r,'war','tianjian','wanmo','sect',-75)\ng.wars[-1].update(war_score=100,battles=2,controller='player',status='peace_ready')\ng.player.location_id=faction_site(g.sects['wanmo'])['id']\ne.store.save(g)");
                    async("loadGame("+JSONObject.quote(id)+")");
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    tapSelector("[data-panel-target=war]");
                    if(Boolean.TRUE.equals(js("!document.querySelector('.war-card').open")))tapSelector(".war-card > summary");
                    js("document.querySelector('.war-peace-form select').value='economic_rights';true");
                    tapSelector(".war-peace-form button[type=submit]");
                    waitForJs("!busy && game.war_system.wars.some(w=>w.economic_transfers?.length)","Native economic peace");
                    tapSelector("[data-panel-target=map]");tapSelector("#map-view-tabs button[aria-controls=map-economy]");openEconomicDetails("#market-governance");
                    js("document.querySelector('[aria-label=市税经营方针]').value='reinvest';true");tapSelector("[data-governance=market_policy]");
                    waitForJs("!busy && game.map.economy.competition.control.policy==='reinvest'","Native fiscal policy");
                    openEconomicDetails("#market-governance");tapSelector("[data-governance=market_relief]");waitForJs("!busy","Native competition funding");
                    python("from cultivation_life import server\nfrom cultivation_life.system.economy.market_power import record_trade\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\nm=g.economy_v2['markets'][g.player.world+':'+g.player.location_id]\ni=next(iter(m['commodities']))\nm['commodities'][i]['stock']=0\nrecord_trade(g,m,i,'player','buy',100000)\nm['competition'][i]['pressure']=16\ne.store.save(g)\ne.advance(g.id,'rest',1)\ng=e._load(g.id)\ng.pending_event=None\ne.store.save(g)");
                    async("loadGame("+JSONObject.quote(id)+")");openEconomicDetails("#market-governance");
                    check(Boolean.TRUE.equals(js("game.map.economy.competition.rows.some(r=>r.added>0)&&document.querySelector('#map-card').scrollWidth<=document.querySelector('#map-card').clientWidth+2")),"Paid competition and narrow layout");
                    tapSelector(".competition-card");capture("economy-governance-"+theme+"-"+arguments.getString("orientation","portrait"));
                    async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("game.map.economy.competition.control.policy==='reinvest'&&!busy")),"Native governance persistence");
                }
                result.putString("economy_governance_scope","Four themes, native peace, fee policy, real funding, paid annual supply, layout and reload");
            } else if(phase.equals("economy-enterprises")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'实业验收',preset_id:'core',seed:419})});return g.id;})()");
                    python("from cultivation_life import server\nfrom cultivation_life.system.economy.ledger import transfer_value\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.player.realm_index=2\ng.player.next_tribulation_age=None\ntransfer_value(g,'background:human','player',100000000,'验收资本')\ne.store.save(g)");
                    async("loadGame("+JSONObject.quote(id)+")");
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    tapSelector("[data-panel-target=map]");tapSelector("#map-view-tabs button[aria-controls=map-economy]");
                    openEconomicDetails("#enterprise-panel");
                    js("document.querySelector('[aria-label=购置产业]').value='mine';true");
                    tapSelector("[data-estate-action=buy]");
                    waitForJs("!busy && game.map.economy.enterprises.owned.length===1","Native estate title");
                    tapSelector("#map-view-tabs button[aria-controls=map-locations]");tapSelector(".map-directory-link.estate");tapSelector(".map-directory-entry.estate button");
                    tapSelector("[data-estate-action=fund]");
                    waitForJs("!busy && game.map.economy.enterprises.owned[0].cash===10000","Native working capital");
                    openEconomicDetails("#enterprise-panel");tapSelector("[data-estate-id] > summary");
                    tapSelector("[data-estate-action=start]");
                    waitForJs("!busy && !!game.map.economy.enterprises.owned[0].job","Native paid production");
                    openEconomicDetails("#enterprise-panel");tapSelector("[data-estate-id] > summary");
                    check(Boolean.TRUE.equals(js("document.querySelector('[data-estate-action=start]').disabled && document.querySelector('#map-card').scrollWidth<=document.querySelector('#map-card').clientWidth+2")),"Production duplicate disabled and layout");
                    js("document.querySelector('[data-estate-action=start]').scrollIntoView({block:'center'});true");
                    capture("enterprises-estate-"+theme+"-"+arguments.getString("orientation","portrait"));
                    python("from cultivation_life import server\ne=server.ENGINE\ne.advance("+JSONObject.quote(id)+",'rest',2)\ng=e._load("+JSONObject.quote(id)+")\ng.pending_event=None\ne.store.save(g)");
                    async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("game.map.economy.enterprises.owned[0].produced===4")),"Production from actual annual command");
                    tapSelector("[data-panel-target=merchant]");tapSelector("#fleet-network-content > details:first-child > summary");tapSelector("[data-fleet-action=create]");
                    waitForJs("!busy && game.fleet_network.fleets.some(f=>f.player_controlled)","Native operating fleet");
                    tapSelector("#trade-orders-panel > summary");tapSelector("[data-order-fleet] > summary");
                    js("document.querySelector('[aria-label=订单执行方式]').value='repeat';document.querySelector('[aria-label=订单商品]').value='dew_grass_seed';true");
                    tapSelector("[data-fleet-action=order_configure]");
                    waitForJs("!busy && game.fleet_network.fleets.some(f=>f.trade_order?.mode==='repeat')","Native standing order saved");
                    tapSelector("#trade-orders-panel > summary");tapSelector("[data-order-fleet] > summary");tapSelector("[data-fleet-action=order_dispatch]");
                    waitForJs("!busy && game.fleet_network.fleets.some(f=>f.player_controlled&&f.status==='travelling')","Native actual dispatch");
                    tapSelector("#trade-orders-panel > summary");tapSelector("[data-order-fleet] > summary");
                    check(Boolean.TRUE.equals(js("document.querySelector('[data-fleet-action=order_dispatch]').disabled && document.querySelector('#merchant-card').scrollWidth<=document.querySelector('#merchant-card').clientWidth+2")),"Duplicate freight disabled and layout");
                    js("document.querySelector('[data-fleet-action=order_dispatch]').scrollIntoView({block:'center'});true");
                    capture("enterprises-orders-"+theme+"-"+arguments.getString("orientation","portrait"));
                    async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("!busy && game.fleet_network.fleets.some(f=>f.player_controlled&&f.status==='travelling'&&f.trade_order.mode==='repeat')")),"Native order persistence");
                }
                result.putString("enterprise_scope","Four themes, native title/funding/production/order/dispatch, authoritative years, duplicate disabling, layout and reload");
            } else if(phase.equals("economy-expansion")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'迁盟验收',preset_id:'core',seed:419})});return g.id;})()");
                    python("from cultivation_life import server\nfrom cultivation_life.system.economy.ledger import transfer_value\nfrom cultivation_life.system.economy import caravans\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.player.realm_index=2\ng.player.next_tribulation_age=None\ntransfer_value(g,'background:human','player',1000000000,'验收资本')\ndef act(action,**args):\n global g\n e.store.save(g)\n e.fleet_action(g.id,dict(action=action,**args))\n g=e._load(g.id)\nact('create')\nfree=[f['id'] for f in g.economy_v2['transport']['worlds']['human']['fleets'].values() if f['owner_kind']=='independent' and not f['player_controlled']]\nfor key in free[:2]:\n g.player.location_id=g.economy_v2['transport']['worlds']['human']['fleets'][key]['location']\n act('pledge',fleet_id=key)\nact('found')\ng.player.world='spirit'\ng.player.realm_index=8\ng.player.location_id=g.merchant_state['worlds']['spirit'][0]['hq']\ncaravans.ensure_caravans(g,e.maps)\nfree=[f['id'] for f in g.economy_v2['transport']['worlds']['spirit']['fleets'].values() if f['owner_kind']=='independent']\nfor key in free[:3]:\n g.player.location_id=g.economy_v2['transport']['worlds']['spirit']['fleets'][key]['location']\n act('pledge',fleet_id=key)\ne.store.save(g)");
                    async("loadGame("+JSONObject.quote(id)+")");
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    js("UtilityPanels.close('merchant');true");tapSelector("[data-panel-target=merchant]");
                    tapSelector("#fleet-network-content > details:nth-child(2) > summary");
                    tapSelector("[data-fleet-action=relocate]");
                    waitForJs("!busy && game.fleet_network.main_hq","Native HQ relocation");
                    tapSelector("#fleet-network-content > details:nth-child(3) > summary");
                    tapSelector("[data-fleet-action=build_passage]");
                    waitForJs("!busy && game.fleet_network.destinations.some(d=>d.open)","Native passage construction");
                    python("from cultivation_life import server\nfrom cultivation_life.system.economy.network_actions import home_alliance\nfrom cultivation_life.system.economy.fleet_network import active_fleets\nfrom cultivation_life.system.economy.ledger import transfer_value\nfrom cultivation_life.system.economy.state import ensure_regional_market\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\nh=home_alliance(g)\nf=active_fleets(g,'spirit','alliance',h['id'])[0]\nf['location']=h['hq']\ntransfer_value(g,'background:spirit','caravan:'+f['id'],10000000,'验收运输')\nf['investment']+=10000000\nensure_regional_market(g,e.maps,'spirit',h['hq'])\nfor row in g.economy_v2['markets']['spirit:'+h['hq']]['commodities'].values():\n row['stock']=row['target']*3\ne.store.save(g)");
                    async("loadGame("+JSONObject.quote(id)+")");
                    tapSelector("#fleet-network-content > details:nth-child(4) > summary");
                    tapSelector("[data-fleet-action=cross_dispatch]");
                    waitForJs("!busy && game.fleet_network.fleets.some(f=>f.cross_trip)","Native freight dispatch");
                    python("from cultivation_life import server\nfrom cultivation_life.system.economy import cross_freight\nfrom cultivation_life.system.economy.fleet_network import routes\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\nf=next(f for f in g.economy_v2['transport']['worlds']['spirit']['fleets'].values() if f.get('cross_trip'))\nfor r in routes(g).values():\n if r['alliance_id'].startswith('player-'): r['open']=False\ng.player.age=f['cross_trip']['arrival']\ncross_freight.advance_freight(g,e.maps,f,{})\ne.store.save(g)");
                    async("loadGame("+JSONObject.quote(id)+")");
                    tapSelector("#fleet-network-content > details:first-child > summary");
                    tapSelector("[data-fleet-action=cross_recall]");
                    waitForJs("!busy && game.fleet_network.fleets.some(f=>f.cross_trip?.phase==='return')","Native stranded freight recall");
                    tapSelector("#fleet-network-content > details:nth-child(3) > summary");
                    tapSelector("[data-fleet-action=build_passage]");
                    waitForJs("!busy && game.fleet_network.destinations.some(d=>d.open)","Native passage repair");
                    tapSelector("#fleet-network-content > details:nth-child(4) > summary");
                    check(Boolean.TRUE.equals(js("document.querySelector('#merchant-card').scrollWidth<=document.querySelector('#merchant-card').clientWidth+1")),"Expansion panel width");
                    capture("economy-expansion-"+theme+"-"+arguments.getString("orientation","portrait"));
                    async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("game.fleet_network.main_hq && game.fleet_network.fleets.some(f=>f.cross_trip?.phase==='return')")),"Expansion persistence");
                }
                result.putString("economy_expansion_scope","Four themes, native relocation, passage build, dispatch, recall, repair, layout and persistence");
            } else if(phase.equals("content-naming")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'命名兼容原生验收',spirit_root:'supreme_metal',path:'dao',seed:61983,preset_id:'nascent'})});return g.id;})()");
                    python(assetText("content_naming_release.py")+"\nfrom cultivation_life import server\nprepare_content_naming_release(server.ENGINE,"+JSONObject.quote(id)+")");
                    async("loadGame("+JSONObject.quote(id)+")");
                    js("document.documentElement.dataset.theme="+JSONObject.quote(theme)+";true");
                    tapSelector(".hud-identity");
                    if(Boolean.TRUE.equals(js("!document.querySelector('.technique-library').open"))) tapSelector(".technique-library > summary");
                    check(Boolean.TRUE.equals(js("game.player.known_techniques.some(t=>t.id==='TECH_YELLOW_COURT_INNER'&&t.name==='黄庭内景经'&&t.level===5)")),"Legacy technique identity and level");
                    check(Boolean.TRUE.equals(js("document.querySelector('#known-technique-list').textContent.includes('成功夺舍次数上限 +1')")),"Special effect remains readable under new title");
                    js("Array.from(document.querySelectorAll('#known-technique-list .known-technique')).find(n=>n.textContent.includes('黄庭内景经')).querySelector('.technique-upgrade').id='release-naming-upgrade';true");
                    tapSelector("#release-naming-upgrade");
                    waitForJs("!busy && game.player.known_techniques.some(t=>t.id==='TECH_YELLOW_COURT_INNER'&&t.level===6)","Original manual consumed by native upgrade");
                    capture("content-naming-technique-"+theme+"-"+arguments.getString("orientation","portrait"));
                    tapSelector("[data-close-dialog=player-details-dialog]");
                    tapSelector("[data-panel-target=inventory]");
                    waitForJs("document.querySelector('#inventory-list').textContent.includes('离照玄晶')","Renamed inventory rendered");
                    check(Boolean.TRUE.equals(js("game.player.inventory.some(i=>i.id==='radiant_flame_crystal'&&i.quantity===7) && game.player.inventory.some(i=>i.id==='custom-naming-sword'&&i.name==='婴神太虚录')")),"Original stock and custom name preserved");
                    js("Array.from(document.querySelectorAll('#inventory-list .item')).find(n=>n.textContent.includes('英姿神武口服液')).querySelector('.item-use').id='release-naming-use';true");
                    tapSelector("#release-naming-use");
                    waitForJs("!busy && game.player.guaranteed_progeny && !game.player.inventory.some(i=>i.id==='qilin_blessing_elixir')","Renamed starter medicine native use");
                    capture("content-naming-inventory-"+theme+"-"+arguments.getString("orientation","portrait"));
                    python(assetText("content_naming_release.py")+"\nfrom cultivation_life import server\ninspect_content_naming_release(server.ENGINE,"+JSONObject.quote(id)+")");
                    tapSelector("#inventory-toggle");
                }
                result.putString("content_naming_scope","Four themes; original saved IDs, fixed catalog labels, custom names, native manual upgrade and starter use, exact stock and no time charge");
            } else if(phase.equals("regional-calendar")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'远行原生验收',spirit_root:'none',path:'dao',seed:20261018})});return g.id;})()");
                    python(assetText("regional_calendar_release.py")+"\nfrom cultivation_life import server\nprepare_regional_journey(server.ENGINE,"+JSONObject.quote(id)+")");
                    async("loadGame("+JSONObject.quote(id)+")");
                    js("document.documentElement.dataset.theme="+JSONObject.quote(theme)+";true");
                    tapSelector("[data-panel-target=map]");waitForPanelReady("#map-card");
                    tapSelector(".map-travel[data-destination=lanjiang_steppe]");
                    waitForJs("!busy && game.pending_event?.id==='EVT_GUIXU_ANNOUNCE'","Native Guixu travel interruption",60000);
                    check(Boolean.TRUE.equals(js("document.querySelector('.map-travel[data-destination=lanjiang_steppe]').disabled")),"Pending event disables travel");
                    python(assetText("regional_calendar_release.py")+"\nfrom cultivation_life import server\ninspect_regional_journey(server.ENGINE,"+JSONObject.quote(id)+")");
                    async("loadGame("+JSONObject.quote(id)+")");
                    for(int step=0;step<20;step++) {
                        if(Boolean.TRUE.equals(js("game.player.location_id==='lanjiang_steppe'")))break;
                        if(Boolean.TRUE.equals(js("!!game.pending_event"))) {
                            if(Boolean.TRUE.equals(js("document.querySelector('#map-card').classList.contains('panel-open')")))tapSelector("#map-toggle");
                            tapSelector("#event-choices button:not([disabled])");waitForJs("!busy","Native notification submit",60000);
                        } else {
                            if(Boolean.TRUE.equals(js("!document.querySelector('#map-card').classList.contains('panel-open')")))tapSelector("[data-panel-target=map]");
                            waitForPanelReady("#map-card");
                            check(Boolean.TRUE.equals(js("document.querySelector('.map-travel[data-destination=lanjiang_steppe]').textContent.includes('继续')")),"Native remaining journey label");
                            capture("regional-continue-"+theme+"-"+arguments.getString("orientation","portrait"));
                            tapSelector(".map-travel[data-destination=lanjiang_steppe]");waitForJs("!busy","Native continuation",60000);
                        }
                    }
                    python(assetText("regional_calendar_release.py")+"\nfrom cultivation_life import server\ninspect_regional_journey(server.ENGINE,"+JSONObject.quote(id)+",True)");
                    if(Boolean.TRUE.equals(js("document.querySelector('#map-card').classList.contains('panel-open')")))tapSelector("#map-toggle");
                }
                result.putString("regional_calendar_scope","Real Guixu interruption and choices, reloaded saved progress, disabled travel and exact total years, original regional finance; four themes");
            } else if(phase.equals("building-visits")) {
                verifyBuildingVisits(result);
            } else if(phase.equals("buildings")) {
                verifyBuildings(result);
            } else if(phase.equals("common-goods")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'商品原生验收',spirit_root:'supreme_metal',path:'dao',seed:2151,preset_id:'nascent'})});return g.id;})()");
                    python(assetText("common_goods_release.py")+"\nfrom cultivation_life import server\nprepare_common_goods(server.ENGINE,"+JSONObject.quote(id)+")");
                    async("loadGame("+JSONObject.quote(id)+")");
                    js("document.documentElement.dataset.theme="+JSONObject.quote(theme)+";true");
                    tapSelector("[data-panel-target=auction]");
                    waitForPanelReady("#auction-card");
                    check(Boolean.TRUE.equals(js("document.querySelector('#auction-title').textContent.includes('高级') && game.auction_system.entry_due===500")),"Native fixed high auction tier and fee");
                    python(assetText("common_goods_release.py")+"\nfrom cultivation_life import server\ncommon_goods_wallet(server.ENGINE,"+JSONObject.quote(id)+",499)");
                    tapSelector("#auction-identities button:first-child");
                    waitForJs("!busy && game.auction_system.spirit_stones===499","Native stale fee refusal recovered");
                    check(Boolean.TRUE.equals(js("[...document.querySelectorAll('#auction-identities button')].every(b=>b.disabled) && !game.auction_system.entry_paid")),"Insufficient entry disabled and unpaid");
                    python(assetText("common_goods_release.py")+"\nfrom cultivation_life import server\ncommon_goods_wallet(server.ENGINE,"+JSONObject.quote(id)+",100000)");
                    async("loadGame("+JSONObject.quote(id)+")");
                    tapSelector("#auction-identities button:first-child");
                    waitForJs("!busy && game.auction_system.entry_paid && game.auction_system.spirit_stones===99500","Native entry actual payment");
                    tapSelector("#auction-identities button:nth-child(2)");
                    waitForJs("!busy","Native identity change");
                    check(Boolean.TRUE.equals(js("game.auction_system.spirit_stones===99500")),"No repeated entry fee");
                    capture("common-goods-auction-"+theme+"-"+arguments.getString("orientation","portrait"));
                    tapSelector("#auction-toggle");tapSelector("[data-panel-target=inventory]");
                    js("window.__coreHP=game.player.hp;[...document.querySelectorAll('#inventory-list .item')].find(r=>r.textContent.includes('赤兽血丹')).querySelector('.item-use').setAttribute('data-native-core','1');true");
                    tapSelector("[data-native-core]");
                    waitForJs("!busy && !game.player.inventory.some(i=>i.id==='econ_human_4_core_blood')","Native fixed core consumption");
                    check(Boolean.TRUE.equals(js("game.player.hp===window.__coreHP+400")),"Native core heals fixed current HP");
                    js("[...document.querySelectorAll('#inventory-list .item')].find(r=>r.textContent.includes('护身符')).querySelector('.item-use').setAttribute('data-native-unpack','1');true");
                    tapSelector("[data-native-unpack]");
                    waitForJs("!busy && game.talismans.rows.length>0","Native real talisman conversion");
                    tapSelector("#inventory-toggle");tapSelector("[data-panel-target=talisman]");
                    js("[...document.querySelectorAll('#talisman-content button')].find(b=>b.textContent==='启用').setAttribute('data-native-enable','1');true");
                    tapSelector("[data-native-enable]");
                    waitForJs("!busy && game.talismans.rows.some(r=>r.enabled && r.uses===3)","Native weak finite talisman toggle");
                    capture("common-goods-talisman-"+theme+"-"+arguments.getString("orientation","portrait"));
                    tapSelector("#talisman-toggle");tapSelector("[data-panel-target=crafting]");
                    js("(()=>{const values={'mold':'sword','primary':'common:econ_human_4_ore_structure:0','secondary-a':'common:econ_human_4_ore_conduct:0','secondary-b':'common:econ_human_4_ore_conduct:1','quench':'common:econ_human_4_ore_store:0'};for(const [k,v] of Object.entries(values))document.querySelector('#crafting-'+k).value=v;document.querySelectorAll('#crafting-allocations input').forEach(i=>i.value='0');document.querySelector('#crafting-allocations input[data-stat=combat_power]').value='10';document.querySelector('#crafting-name').value='通用矿材验收';return true;})()");
                    tapSelector("#crafting-preview");
                    waitForJs("!busy && !!document.querySelector('#crafting-preview-result button')","Native original ore forge preview");
                    tapSelector("#crafting-preview-result button");tapSelector("#game-confirm-accept");
                    waitForJs("!busy && game.crafting_system.artifacts.some(a=>a.name==='通用矿材验收')","Native four-unit actual forge");
                    python(assetText("common_goods_release.py")+"\nfrom cultivation_life import server\ninspect_common_goods(server.ENGINE,"+JSONObject.quote(id)+")");
                    waitForPanelReady("#crafting-card");
                    check(Boolean.TRUE.equals(js("document.querySelector('#crafting-card').scrollWidth<=document.querySelector('#crafting-card').clientWidth+2")),"Native forge fits");
                    capture("common-goods-forge-"+theme+"-"+arguments.getString("orientation","portrait"));
                    tapSelector("#crafting-toggle");
                }
                result.putString("common_goods_scope","Fixed current HP, finite weak talisman, four real common-ore units, fixed auction entry once and stale-insufficient recovery; four themes");
            } else if(phase.equals("secret-arts")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'秘术原生验收',spirit_root:'supreme_metal',path:'dao',seed:2150})});return g.id;})()");
                    python(assetText("secret_arts_release.py")+"\nfrom cultivation_life import server\nprepare_secret_arts(server.ENGINE,"+JSONObject.quote(id)+")");
                    async("loadGame("+JSONObject.quote(id)+")");
                    js("document.documentElement.dataset.theme="+JSONObject.quote(theme)+";true");
                    tapSelector("[data-panel-target=secret-art]");
                    if(Boolean.TRUE.equals(js("getComputedStyle(document.querySelector('#secret-art-back')).display!=='none' && document.querySelector('#secret-art-card').dataset.secretView==='detail'"))) tapSelector("#secret-art-back");
                    js("document.querySelector('#secret-art-search').value='';document.querySelector('#secret-art-search').dispatchEvent(new Event('input',{bubbles:true}));true");
                    tapSelector("#secret-tab-known");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('#secret-art-library .secret-art-entry').length===4")),"Only acquired native secret arts appear");
                    tapSelector("#secret-tab-potential");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('#secret-art-library .secret-art-entry').length===6 && !document.querySelector('.secret-art-command')")),"Potential arts guide without unowned action buttons");
                    tapSelector("#secret-tab-known");
                    capture("secret-arts-catalog-"+theme+"-"+arguments.getString("orientation","portrait"));
                    js("document.querySelector('#secret-art-search').value='玄水';document.querySelector('#secret-art-search').dispatchEvent(new Event('input',{bubbles:true}));true");
                    tapSelector("[data-secret-art=root_water]");
                    check(Boolean.TRUE.equals(js("document.querySelector('.secret-art-facts').textContent.includes('不限')")),"Secret arts have no rank gate");
                    tapSelector(".secret-art-command");
                    waitForJs("!busy && game.secret_arts.library.find(a=>a.id==='root_water').learned","Native independent learning");
                    js("document.querySelector('#secret-art-material').value='item:secret_core_water_4';true");
                    tapSelector(".secret-art-command");
                    waitForJs("!busy && game.player.additional_roots.includes('water')","Native actual timed root grafting");
                    python(assetText("secret_arts_release.py")+"\nfrom cultivation_life import server\ninspect_secret_arts(server.ENGINE,"+JSONObject.quote(id)+")");
                    capture("secret-arts-completed-"+theme+"-"+arguments.getString("orientation","portrait"));
                    if(Boolean.TRUE.equals(js("getComputedStyle(document.querySelector('#secret-art-back')).display!=='none'"))) tapSelector("#secret-art-back");
                    js("document.querySelector('#secret-art-search').value='离火';document.querySelector('#secret-art-search').dispatchEvent(new Event('input',{bubbles:true}));true");
                    tapSelector("[data-secret-art=root_fire]");
                    python(assetText("secret_arts_release.py")+"\nfrom cultivation_life import server\npending_secret_art_event(server.ENGINE,"+JSONObject.quote(id)+")");
                    tapSelector(".secret-art-command");
                    waitForJs("!busy && !!game.pending_event","Native stale secret-art page recovered");
                    check(Boolean.TRUE.equals(js("document.querySelector('.secret-art-command').disabled && !game.secret_arts.library.find(a=>a.id==='root_fire').study_progress")),"Stale native study has no charge or progress");
                    tapSelector("#secret-art-toggle");
                    tapSelector("#event-choices button:first-child");
                    waitForJs("!busy && !game.pending_event","Native event completed");
                    tapSelector("[data-panel-target=secret-art]");
                      waitForPanelReady("#secret-art-card");
                    check(Boolean.TRUE.equals(js("!document.querySelector('.secret-art-command').disabled && document.querySelector('#secret-art-card').scrollWidth<=document.querySelector('#secret-art-card').clientWidth+2")),"Native secret-art state recovered and fits");
                    tapSelector("#secret-art-toggle");
                }
                result.putString("secret_arts_scope","Independent source/time/resource settlement, low-rank learning, exact material consumption, stale-event recovery and bounded catalog; four themes");
            } else if(phase.equals("common-techniques")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'通用功法原生验收',spirit_root:'supreme_metal',path:'dao',seed:2144,preset_id:'core'})});return g.id;})()");
                    python(assetText("common_techniques_release.py")+"\nfrom cultivation_life import server\nprepare_common_techniques(server.ENGINE,"+JSONObject.quote(id)+")");
                    async("loadGame("+JSONObject.quote(id)+")");
                    js("document.documentElement.dataset.theme="+JSONObject.quote(theme)+";true");
                    tapSelector("[data-panel-target=market]");
                    check(Boolean.TRUE.equals(js("!document.querySelector('.market-buy[data-offer-id=old-rare-art]')")),"Rare art excluded from native shelf");
                    js("window.__shopBefore=game.market.spirit_stones;game.market.offers.push({id:'old-rare-art',kind:'technique',name:'旧坊市传承',price:100,tier_name:'练气',description:'旧页面',compatible:true,sold:false,locked:false,market_group:'general'});renderMarket(game.market);true");
                    tapSelector(".market-buy[data-offer-id=old-rare-art]");
                    waitForJs("!busy && !game.market.offers.some(o=>o.id==='old-rare-art')","Stale native shelf recovered");
                    check(Boolean.TRUE.equals(js("game.market.spirit_stones===window.__shopBefore")),"Rejected rare purchase never charged");
                    tapSelector(".market-buy[data-offer-id=ordinary-art]");
                    waitForJs("!busy && game.player.known_techniques.some(t=>t.id==='TECH_OPEN_SONGCHUANG_METAL_COMBAT')","Native ordinary art purchase");
                    check(Boolean.TRUE.equals(js("game.market.spirit_stones===window.__shopBefore-100")),"Ordinary native purchase charged once");
                    tapSelector("#market-toggle");
                    tapSelector(".hud-identity");
                    if(Boolean.TRUE.equals(js("!document.querySelector('.technique-library').open"))) tapSelector(".technique-library > summary");
                    check(Boolean.TRUE.equals(js("document.querySelector('#known-technique-list .known-technique:first-child .technique-equip').disabled && document.querySelector('#known-technique-list').textContent.includes('金、水（须全部具备）')")),"All-root native gate");
                    tapSelector("[data-close-dialog=player-details-dialog]");
                    tapSelector("[data-panel-target=inventory]");
                    js("Array.from(document.querySelectorAll('#inventory-card .item')).find(e=>e.textContent.includes(game.player.inventory.find(i=>i.id==='jinque_water').name)).querySelector('.item-use').id='common-root-use';true");
                    tapSelector("#common-root-use");
                    waitForJs("!busy && game.player.additional_roots.includes('water')","Native root supplement");
                    tapSelector("#inventory-toggle");
                    tapSelector(".hud-identity");
                    if(Boolean.TRUE.equals(js("!document.querySelector('.technique-library').open"))) tapSelector(".technique-library > summary");
                    tapSelector("#known-technique-list .known-technique:first-child .technique-equip");
                    waitForJs("!busy && game.player.technique?.id==='TECH_OPEN_SONGCHUANG_METAL_WATER_MAIN'","Native combined-root equip");
                    tapSelector("#known-technique-list .known-technique:first-child .technique-upgrade");
                    waitForJs("!busy && game.player.technique.level===2","Native real manual consumption and upgrade");
                    capture("common-techniques-upgrade-"+theme+"-"+arguments.getString("orientation","portrait"));
                    python(assetText("common_techniques_release.py")+"\nfrom cultivation_life import server\nlose_common_technique_root(server.ENGINE,"+JSONObject.quote(id)+")");
                    async("loadGame("+JSONObject.quote(id)+")");
                    if(!Boolean.TRUE.equals(js("document.querySelector('#player-details-dialog').open"))) tapSelector(".hud-identity");
                    js("document.querySelector('#technique-list').closest('details').querySelector('summary').id='common-config-summary';true");
                    if(Boolean.TRUE.equals(js("!document.querySelector('#technique-list').closest('details').open"))) tapSelector("#common-config-summary");
                    check(Boolean.TRUE.equals(js("game.player.technique_slots.main.root_requirement_met===false && document.querySelector('#technique-list').textContent.includes('当前失效')")),"Root loss disables original art without deleting it");
                    check(Boolean.TRUE.equals(js("document.querySelector('#player-details-dialog').scrollWidth<=document.querySelector('#player-details-dialog').clientWidth+2")),"Bounded native combined-root UI");
                    capture("common-techniques-root-lost-"+theme+"-"+arguments.getString("orientation","portrait"));
                    tapSelector("[data-close-dialog=player-details-dialog]");
                }
                result.putString("common_techniques_scope","All-root eligibility, real root item/equip/upgrade, stale shop rejection/recovery and ordinary purchase, root-loss disable without losing books; four themes");
            } else if(phase.equals("upper-teachings")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    String buddhist=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'上界愿力原生验收',spirit_root:'supreme_wood',path:'buddhist',seed:2143,preset_id:'core'})});return g.id;})()");
                    String sage=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'上界教化原生验收',spirit_root:'supreme_wood',path:'confucian',seed:2143,preset_id:'core'})});return g.id;})()");
                    for(String world:new String[]{"celestial","asura","nether","reincarnation"}) {
                        python(assetText("upper_teachings_release.py")+"\nfrom cultivation_life import server\nprepare_upper_teachings(server.ENGINE,"+JSONObject.quote(buddhist)+","+JSONObject.quote(world)+",'buddhist')");
                        async("loadGame("+JSONObject.quote(buddhist)+")");
                        js("document.documentElement.dataset.theme="+JSONObject.quote(theme)+";true");
                        tapSelector("[data-panel-target=buddhist-wish]");
                        check(Boolean.TRUE.equals(js("game.buddhist_system.wish.value===100 && !!game.buddhist_system.wish.blocked && game.player.layer===1")),"Upper wish retained, direct nirvana unavailable");
                        check(Boolean.TRUE.equals(js("document.querySelector('#buddhist-wish-content button').disabled && document.querySelector('#buddhist-wish-card').scrollWidth<=document.querySelector('#buddhist-wish-card').clientWidth+2")),"Upper wish disabled and bounded");
                        capture("upper-teachings-"+world+"-wish-"+theme+"-"+arguments.getString("orientation","portrait"));
                        tapSelector("[data-panel-target=buddhist]");
                        tapSelector(".dharma-blessing");
                        waitForJs("!busy && game.buddhist_system.blessings[0].selected","Native upper local blessing");
                        python(assetText("upper_teachings_release.py")+"\nfrom cultivation_life import server\nprepare_upper_teachings(server.ENGINE,"+JSONObject.quote(sage)+","+JSONObject.quote(world)+",'confucian')");
                        async("loadGame("+JSONObject.quote(sage)+")");
                        tapSelector("[data-panel-target=sage]");
                        check(Boolean.TRUE.equals(js("game.sage_system.teaching_available && game.sage_system.world==="+JSONObject.quote(world))),"Current upper teaching world");
                        tapSelector("#sage-doctrine-list .sage-doctrine > button");
                        waitForJs("!busy && !!game.sage_system.membership_id","Native join original local doctrine");
                        check(Boolean.TRUE.equals(js("document.querySelectorAll('.sage-action-card').length===3")),"Three upper teaching actions");
                        tapSelector("[data-panel-target=sage-inner-outer]");
                        tapSelector("#sage-manual-list .sage-inner-outer-action[data-available='1']");
                        tapSelector("#game-confirm-accept");
                        waitForJs("!busy && game.player.haoran_exp>1000000","Native upper classic real grade and gain");
                        check(Boolean.TRUE.equals(js("document.querySelector('#sage-outer-list .sage-outer-card:first-child button').disabled")),"Upper direct outer advancement disabled");
                        js("window.__upperOpportunityBefore=game.player.opportunity;true");
                        tapSelector("#sage-outer-list .sage-outer-card:last-child button");
                        tapSelector("#game-confirm-accept");
                        waitForJs("!busy && game.player.opportunity>window.__upperOpportunityBefore && game.player.layer===1","Native upper outer opportunity without advancement");
                        check(Boolean.TRUE.equals(js("document.querySelector('#sage-inner-outer-card').scrollWidth<=document.querySelector('#sage-inner-outer-card').clientWidth+2")),"Upper sage bounded panel");
                        capture("upper-teachings-"+world+"-sage-"+theme+"-"+arguments.getString("orientation","portrait"));
                    }
                    python(assetText("upper_teachings_release.py")+"\nfrom cultivation_life import server\ng=prepare_upper_teachings(server.ENGINE,"+JSONObject.quote(buddhist)+",'celestial','buddhist')\ng.player.immortal_veins={}\nserver.ENGINE.store.save(g)");
                    async("loadGame("+JSONObject.quote(buddhist)+")");
                    tapSelector("[data-panel-target=buddhist-wish]");
                    check(Boolean.TRUE.equals(js("document.querySelector('#buddhist-wish-content button').disabled && game.buddhist_system.wish.value===100")),"Upper native nirvana remains disabled without spending wish");
                }
                result.putString("upper_teachings_scope","Both DLCs, four upper worlds, wish retained and direct advancement disabled; native local blessing, join school, upper classics and outer opportunity; four themes");
            } else if(phase.equals("natal-materials")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'十一界镶材原生验收',spirit_root:'supreme_metal',path:'dao',seed:2142,preset_id:'core'})});return g.id;})()");
                    python(assetText("natal_materials_release.py")+"\nfrom cultivation_life import server\nprepare_natal_materials_release(server.ENGINE,"+JSONObject.quote(id)+")");
                    async("loadGame("+JSONObject.quote(id)+")");
                    js("document.documentElement.dataset.theme="+JSONObject.quote(theme)+";true");
                    tapSelector("[data-panel-target=natal-artifact]");
                    tapSelector(".natal-slot.slot-0");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('.natal-material-choice').length===3")),"Owned materials only");
                    tapSelector("[data-material-id=natal_human_pine_metal]");
                    waitForJs("!busy && game.natal_artifact.slots[0].material_id==='natal_human_pine_metal'","Native socket ownership transfer");
                    capture("natal-materials-socket-"+theme+"-"+arguments.getString("orientation","portrait"));
                    tapSelector(".natal-slot.slot-0");
                    waitForJs("!busy && !game.natal_artifact.slots[0].material_id","Native exact material return");
                    tapSelector(".natal-slot.slot-0");
                    js("(()=>{const s=document.querySelector('[aria-label=镶材范围]');s.value='all';s.dispatchEvent(new Event('change'));return true;})()");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('.natal-material-choice').length===24 && document.querySelector('.natal-material-pages button').disabled")),"Bounded catalog page");
                    tapSelector(".natal-material-pages button:last-child");
                    check(Boolean.TRUE.equals(js("document.querySelector('.natal-material-pages span').textContent.startsWith('2 /')")),"Native catalog paging");
                    js("(()=>{const s=document.querySelector('[aria-label=搜索镶材]');s.value='烛龙母金';s.dispatchEvent(new Event('input'));return true;})()");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('.natal-material-choice').length===1 && document.querySelector('.natal-material-choice').disabled && document.querySelector('.natal-material-choice').textContent.includes('幽冥界')")),"Origin shown and high tier unavailable");
                    check(Boolean.TRUE.equals(js("Array.from(document.querySelectorAll('.natal-material-grid')).every(e=>e.scrollWidth<=e.clientWidth+1)")),"Material picker width");
                    capture("natal-materials-catalog-"+theme+"-"+arguments.getString("orientation","portrait"));
                    python(assetText("natal_materials_release.py")+"\nfrom cultivation_life import server\ninspect_natal_materials_release(server.ENGINE,"+JSONObject.quote(id)+")");
                    tapSelector("#natal-artifact-toggle");
                }
                result.putString("natal_materials_scope","Eleven-world catalog, four themes, native socket and exact unsocket, owned source filtering, bounded pages and higher-tier rejection");
            } else if(phase.equals("strategic-war")) {
                for(String theme:new String[]{"a","b","d","f"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'联军调度原生验收',spirit_root:'supreme_metal',path:'dao',seed:641,custom_start:{world:'spirit',realm_index:8,layer:1}})});return g.id;})()");
                    python(assetText("strategic_war_release.py")+"\nfrom cultivation_life import server\nprepare_strategic_release(server.ENGINE,"+JSONObject.quote(id)+")");
                    async("loadGame("+JSONObject.quote(id)+")");
                    js("document.documentElement.dataset.theme="+JSONObject.quote(theme)+";true");
                    tapSelector("[data-panel-target=war]");
                    js("Array.from(document.querySelectorAll('#strategic-war-panel [role=tab]')).find(b=>b.textContent==='战役').id='release-strategy-tab';window.__strategyCampaign=game.war_system.strategic.wars[0].campaigns.find(c=>c.org?.id==='taixuan'&&c.dispatch_choices.length);true");
                    check(Boolean.TRUE.equals(js("!!__strategyCampaign")),"Actual idle reserve available");
                    tapSelector("#release-strategy-tab");
                    String campaign=(String)js("__strategyCampaign.id");
                    tapSelector("[data-campaign-id='"+campaign+"']");
                    js("window.__strategyReserve=document.querySelector('#strategic-war-panel select[aria-label=选择闲置宗门]').value;true");
                    tapSelector("#strategic-war-panel .strategy-dispatch button");
                    waitForJs("!busy && game.war_system.strategic.wars[0].campaigns.find(c=>c.id==="+JSONObject.quote(campaign)+").coalitions.attacker.some(o=>o.id===__strategyReserve)","Native original reserve dispatched");
                    python(assetText("strategic_war_release.py")+"\nfrom cultivation_life import server\ninspect_strategic_release(server.ENGINE,"+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("document.querySelectorAll('#strategic-war-panel .strategy-army').length===2 && document.querySelector('#strategic-war-panel').scrollWidth<=document.querySelector('#strategic-war-panel').clientWidth+2")),"Native coalition cards and layout");
                    capture("strategic-war-"+theme+"-"+arguments.getString("orientation","portrait"));
                    js("Array.from(document.querySelectorAll('#strategic-war-panel button')).find(b=>b.textContent==='本部固守').id='release-strategy-hold';true");
                    tapSelector("#release-strategy-hold");waitForJs("!busy","Native local stance command");
                    js("Array.from(document.querySelectorAll('#strategic-war-panel button')).find(b=>b.textContent==='撤回本组织').id='release-strategy-withdraw';true");
                    tapSelector("#release-strategy-withdraw");waitForJs("!busy","Native original organization recall");
                    python(assetText("strategic_war_release.py")+"\nfrom cultivation_life import server\ninspect_strategic_release(server.ENGINE,"+JSONObject.quote(id)+")\ng=server.ENGINE._load("+JSONObject.quote(id)+")\nw=next(w for w in g.wars if w['id']==server.ENGINE._strategic_release_info['campaign'])\nassert 'taixuan' in w['withdrawn_orgs'] and w['org_stances']['taixuan']=='hold'");
                    tapSelector("#war-toggle");
                }
                result.putString("strategic_war_scope","Four themes; actual native idle dispatch, original escrow, multi-organization campaign, local hold/recall and ally continuation");
            } else if(phase.equals("audit-fixes")) {
                for(String auditCase:new String[]{"return","training","work"}) {
                    String world=auditCase.equals("work")?"nether":"spirit";
                    int realm=auditCase.equals("work")?9:8;
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'边界修复原生验收',spirit_root:'supreme_metal',path:'dao',seed:8712,custom_start:{world:"+JSONObject.quote(world)+",realm_index:"+realm+",layer:1}})});return g.id;})()");
                    String setup=assetText("audit_fixes_release.py")+"\nfrom cultivation_life import server\nprepare_audit_fixes(server.ENGINE,"+JSONObject.quote(id)+","+JSONObject.quote(auditCase)+")";
                    if(auditCase.equals("return"))setup+="\nserver.ENGINE.manage_secret_art("+JSONObject.quote(id)+",'suppress','activate',1,1)";
                    python(setup);
                    async("loadGame("+JSONObject.quote(id)+")");
                    if(auditCase.equals("return")) {
                        tapSelector("#cross-world-action");waitForJs("!busy && game.player.world==='human'","Native suppressed descent");
                        tapSelector("[data-panel-target=secret-art]");
                        tapSelector("#secret-art-library [data-secret-art=suppress]");
                        check(Boolean.TRUE.equals(js("document.querySelector('#secret-suppress-cancel').getClientRects().length>0 && document.querySelector('#secret-suppress-cancel').disabled")),"Cannot cancel before returning");
                        tapSelector("#secret-art-toggle");tapSelector("#cross-world-action");
                        waitForJs("!busy && game.player.world==='spirit'","Native original return");
                        tapSelector("[data-panel-target=secret-art]");tapSelector("#secret-suppress-cancel");
                        waitForJs("!busy && !game.player.cultivation_suppression","Native restore true rank");
                        python(assetText("audit_fixes_release.py")+"\nfrom cultivation_life import server\ninspect_audit_fixes(server.ENGINE,"+JSONObject.quote(id)+",'return')");
                        tapSelector("#secret-art-toggle");
                    } else if(auditCase.equals("training")) {
                        tapSelector("[data-panel-target=captive]");tapSelector("#captive-list .owned-training summary");tapSelector("#captive-list .owned-training button");
                        waitForJs("!busy && game.demonic_system.prisoners[0].realm_index>=6","Native captive breakthrough");
                        python(assetText("audit_fixes_release.py")+"\nfrom cultivation_life import server\ninspect_audit_fixes(server.ENGINE,"+JSONObject.quote(id)+",'training')");
                        capture("audit-training-"+arguments.getString("orientation","portrait"));
                        tapSelector("#captive-list .captive-tools button");
                        waitForJs("!busy && game.demonic_system.prisoners.length===0","Native captive release");
                        python(assetText("audit_fixes_release.py")+"\nfrom cultivation_life import server\ninspect_audit_fixes(server.ENGINE,"+JSONObject.quote(id)+",'training')");
                        tapSelector("#captive-toggle");
                    } else {
                        js("window.__auditStartAge=game.player.age;true");tapSelector("[data-panel-target=upper-institution]");
                        tapSelector("#upper-institution-card [data-section=jobs] summary");
                        js("Array.from(document.querySelectorAll('#upper-institution-card button')).find(b=>b.textContent==='继续履约').id='audit-work-button';true");
                        tapSelector("#audit-work-button");
                        waitForJs("!busy && game.upper_institution.job.progress===100","Native remaining institution work",120000);
                        check(Boolean.TRUE.equals(js("game.player.age-__auditStartAge===60")),"Only sixty remaining years consumed");
                        capture("audit-work-"+arguments.getString("orientation","portrait"));
                        tapSelector("#upper-institution-toggle");
                    }
                }
                for(String followupCase:new String[]{"guard","production","supply"}) {
                    String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'修复汇总原生验收',spirit_root:'supreme_metal',path:'dao',seed:888,custom_start:{world:'human',realm_index:4,layer:1}})});return g.id;})()");
                    python(assetText("followup_fixes_release.py")+"\nfrom cultivation_life import server\nprepare_followup(server.ENGINE,"+JSONObject.quote(id)+","+JSONObject.quote(followupCase)+")");
                    if(followupCase.equals("guard")) {
                        async("(async()=>{const id="+JSONObject.quote(id)+";let g=await api('/api/games/'+id);const post=(op,p)=>api('/api/games/'+id+'/'+op,{method:'POST',body:JSON.stringify(p)});const slots=g.formation_system.materials.filter(r=>r.source_kind==='formation_material').slice(0,3).map(r=>r.id);await post('formation-save',{name:'原生护山',slots,activate:true});await post('formation-ground-deploy',{owner_kind:'sect'});g=await api('/api/games/'+id);const destination=g.map.organization_relocation.find(r=>r.kind==='sect').destinations[0].id;await post('organization-action',{kind:'sect',owner_id:'followup_org',action:'relocate',location_id:destination});await post('map-travel',{destination});return true;})()");
                        python(assetText("followup_fixes_release.py")+"\nfrom cultivation_life import server\nprepare_guard_defense(server.ENGINE,"+JSONObject.quote(id)+")");
                        async("loadGame("+JSONObject.quote(id)+")");
                        tapSelector("#event-choices button:nth-child(2)");
                        waitForJs("!busy && !game.pending_event","Native remote guard resolves without borrowing old materials");
                    } else {
                        if(followupCase.equals("supply"))async("api('/api/games/"+id+"/intrigue-resolution',{method:'POST',body:JSON.stringify({kind:'sect',resolution_type:'declare_war',target_id:'tianjian'})})");
                        async("loadGame("+JSONObject.quote(id)+")");
                        tapSelector("[data-panel-target=intrigue]");
                        js("(()=>{const f=document.querySelector('.intrigue-sect .intrigue-resolution-form');f.querySelector('select').value='imprison_member';f.querySelector('select').dispatchEvent(new Event('change'));f.querySelector('input[type=number]').value='500';return true;})()");
                        tapSelector(".intrigue-sect .intrigue-resolution-form button");
                        waitForJs("!busy && game.intrigue_system.sections.some(s=>s.prison.some(p=>p.prisoner_id==='followup_member'))","Native legal imprisonment vote");
                        tapSelector("#intrigue-toggle");
                        if(followupCase.equals("production")) {
                            tapSelector("[data-action=rest]");
                            waitForJs("!busy && game.faction.finance.labor_capacity===0","Native jailed member has no production labor",120000);
                        } else async("(async()=>{const g=await api('/api/games/"+id+"');const w=g.war_system.wars.find(w=>w.attacker_id==='followup_org');return api('/api/games/"+id+"/war-action',{method:'POST',body:JSON.stringify({war_id:w.id,action:'round'})});})()");
                    }
                    python(assetText("followup_fixes_release.py")+"\nfrom cultivation_life import server\ninspect_followup(server.ENGINE,"+JSONObject.quote(id)+","+JSONObject.quote(followupCase)+")");
                    capture("audit-followup-"+followupCase+"-"+arguments.getString("orientation","portrait"));
                }
                for(String[] branch:new String[][]{{"celestial","dao"},{"asura","dao"},{"nether","dao"},{"reincarnation","dao"},{"asura","demonic"},{"nether","monster"},{"reincarnation","ghost"}}) {
                    String id=(String)async("(async()=>{const path="+JSONObject.quote(branch[1])+";const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'传承原生验收',spirit_root:path==='ghost'?'mutated_yin':'supreme_metal',path,seed:591,monster_species_id:path==='monster'?'serpent':null,custom_start:{world:"+JSONObject.quote(branch[0])+",realm_index:9,layer:1}})});return g.id;})()");
                    python(assetText("followup_fixes_release.py")+"\nfrom cultivation_life import server\nprepare_followup(server.ENGINE,"+JSONObject.quote(id)+",'inheritance')");
                    async("loadGame("+JSONObject.quote(id)+")");
                    tapSelector("[data-panel-target=immortal-aperture]");
                    tapSelector("#immortal-aperture-content > details > summary");
                    check(Boolean.TRUE.equals(js("!document.querySelector('[data-inheritance-action]').disabled")),"Native legal inheritance available");
                    tapSelector("[data-inheritance-action]");
                    waitForJs("!busy && Array.from(document.querySelectorAll('[data-inheritance-action]')).some(b=>b.disabled)","Native inherited branch persisted");
                    python(assetText("followup_fixes_release.py")+"\nfrom cultivation_life import server\ninspect_followup(server.ENGINE,"+JSONObject.quote(id)+",'inheritance')");
                    capture("audit-inheritance-"+branch[0]+"-"+branch[1]+"-"+arguments.getString("orientation","portrait"));
                    tapSelector("#immortal-aperture-toggle");
                }
                result.putString("audit_fixes_scope","Original return, lifespan and remaining work; real imprisonment vote, jailed production and military consumption, fixed-site guard and seven inheritance branches");
                result.putString("followup_fixes_scope","v2.13.6: production, supply, original guard materials and seven native inheritance branches");
            } else if(phase.equals("economy-trust")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'托管原生验收',preset_id:'core',seed:419})});return g.id;})()");
                python(assetText("economy_trust_release.py")+"\nfrom cultivation_life import server\nprepare_economy_trust(server.ENGINE,"+JSONObject.quote(id)+")");
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("game.family.finance.settlement_years===5 && game.family.finance.annual_income===game.family.finance.income/5 && game.family.finance.annual_expense===game.family.finance.expense/5")),"Native annual finance period");
                tapSelector("[data-panel-target=family]");
                tapSelector("#family-card .organization-finance summary");
                check(Boolean.TRUE.equals(js("document.querySelector('#family-card .organization-finance').innerText.includes('年度收入') && document.querySelector('#family-card .organization-finance').innerText.includes('本期成交额')")),"Native distinct income and turnover");
                tapSelector("#family-card .organization-business > summary");
                tapSelector("#family-card [data-fleet-id='human:release-trust-guard'] [data-org-business=guard]");
                waitForJs("!busy && game.fleet_network.fleets.find(f=>f.id==='human:release-trust-guard').guard_power>0","Native organization guard payment");
                check(Boolean.TRUE.equals(js("document.querySelector('#family-card [data-fleet-id=\"human:release-trust-guard\"] [data-org-business=guard]').disabled")),"Native full guards stay disabled");
                tapSelector("[data-panel-target=settings]");
                tapSelector("#setting-economy-trust");
                waitForJs("!busy && game.settings.economy_trust","Native trust enable");
                tapSelector("#settings-toggle");
                tapSelector("[data-action=rest]");
                waitForJs("!busy && game.map.economy.enterprises.owned.some(r=>r.trust_managed)","Native real annual trust settlement",60000);
                js("window.__paidTrustJob=JSON.stringify(game.map.economy.enterprises.owned.find(r=>r.kind==='mine').job);true");
                tapSelector("[data-panel-target=settings]");
                tapSelector("#setting-economy-trust");
                waitForJs("!busy && !game.settings.economy_trust","Native trust disable");
                check(Boolean.TRUE.equals(js("game.map.economy.enterprises.owned.every(r=>!r.trust_managed&&!r.enabled) && JSON.stringify(game.map.economy.enterprises.owned.find(r=>r.kind==='mine').job)===__paidTrustJob")),"Native restores plan and retains paid work");
                capture("economy-trust-"+arguments.getString("orientation","portrait"));
                async("loadGame("+JSONObject.quote(id)+")");
                check(Boolean.TRUE.equals(js("!game.settings.economy_trust && !busy")),"Native trust save reload");
                result.putString("economy_trust_scope","Annual five-year accounting, distinct turnover, real organization guard tap, trust on/off, real time and paid-job preservation");
            } else if(phase.equals("economy-network")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'四轮商路验收',preset_id:'core',seed:419})});return g.id;})()");
                python("from cultivation_life import server\nfrom cultivation_life.system.economy.ledger import transfer_value\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.player.realm_index=2\ntransfer_value(g,'background:human','player',10000000,'验收资本')\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                tapSelector("[data-panel-target=merchant]");
                tapSelector("#fleet-network-content > details:first-child > summary");
                tapSelector("#fleet-network-content [data-fleet-action=create]");
                waitForJs("!busy && game.fleet_network.fleets.some(f=>f.player_controlled)","Native independent fleet creation");
                tapSelector("#fleet-network-content > details:first-child > summary");
                tapSelector("#fleet-network-content [data-fleet-action=guard]");
                waitForJs("!busy && game.fleet_network.fleets.some(f=>f.player_controlled&&f.guard_power>0)","Native guard hiring");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    js("UtilityPanels.close('personal-economy');true");
                    tapSelector("[data-panel-target=personal-economy]");
                    waitForJs("getComputedStyle(document.querySelector('#personal-economy-card')).opacity==='1'","Native personal account open");
                    check(Boolean.TRUE.equals(js("document.querySelector('#personal-economy-content').innerText.includes('委派商队护卫') && document.querySelector('#personal-economy-card').scrollWidth<=document.querySelector('#personal-economy-card').clientWidth+1")),"Native personal statement");
                    capture("network-personal-"+theme+"-"+arguments.getString("orientation","portrait"));
                    tapSelector("[data-panel-target=merchant]");
                    js("document.querySelector('#fleet-network-content > details').open=false;window.__fleetCash=game.fleet_network.fleets.find(f=>f.player_controlled).cash;true");
                    tapSelector("#fleet-network-content > details:first-child > summary");
                    tapSelector("#fleet-network-content [data-fleet-action=fund]");
                    waitForJs("!busy && game.fleet_network.fleets.find(f=>f.player_controlled).cash===window.__fleetCash+5000","Native caravan funding");
                    tapSelector("#fleet-network-content > details:first-child > summary");
                    check(Boolean.TRUE.equals(js("document.querySelector('#merchant-card').scrollWidth<=document.querySelector('#merchant-card').clientWidth+1")),"Native network layout");
                    capture("network-fleet-"+theme+"-"+arguments.getString("orientation","portrait"));
                    async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("!busy && game.fleet_network.fleets.find(f=>f.player_controlled).cash===window.__fleetCash+5000")),"Native fleet persistence");
                }
                result.putString("network_scope","Four themes, personal accounts, independent creation, paid guards, fleet funding, no overflow and persistence");
            } else if(phase.equals("economy-organizations")) {
                String id=(String)async("(async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'组织财政验收',preset_id:'core',seed:315})});return g.id;})()");
                python("from cultivation_life import server\nfrom cultivation_life.models import SectState,SectNpc\nfrom cultivation_life.rules import add_item\nfrom cultivation_life.system.economy import organizations as f\ne=server.ENGINE\ng=e._load("+JSONObject.quote(id)+")\ng.pending_event=None\ng.player.realm_index=5\ng.player.lifespan=None\ng.player.next_tribulation_age=None\ng.player.faction_id=next(s.id for s in g.sects.values() if s.world=='human' and s.kind=='sect')\nn=SectNpc('fiscal_heir','沈宁','族人',4,1,100,1000,world='human')\ng.family=SectState('native_family','沈氏','human',[n],kind='family',founded_by_player=True,founder_player_id=g.id)\nadd_item(g.player,'spirit_stone',10000)\nf.ensure_organizations(g)\ng.player.age+=1\nf.advance_organizations(g,e.maps)\ne.store.save(g)");
                async("loadGame("+JSONObject.quote(id)+")");
                for(String theme:new String[]{"a","b","d","f"}) {
                    js("document.querySelector('[data-theme-picker=dialog] [data-theme-choice="+theme+"]').click()");async("GameThemes.saved");
                    js("UtilityPanels.open('family');window.__familyCash=game.family.ledger.resources;document.querySelector('[data-family-funds]').value='1000';Array.from(document.querySelectorAll('[data-family]')).find(b=>JSON.parse(b.dataset.family).action==='fund').id='native-family-fund';true");
                    tapSelector("#native-family-fund");
                    waitForJs("!busy && game.family.ledger.resources===window.__familyCash+1000","Native family treasury transfer");
                    tapSelector("#family-card .organization-finance summary");
                    check(Boolean.TRUE.equals(js("document.querySelector('#family-card .organization-finance').innerText.includes('驻地产出') && document.querySelector('#family-card').scrollWidth<=document.querySelector('#family-card').clientWidth+1")),"Native family finance");
                    capture("organizations-family-"+theme+"-"+arguments.getString("orientation","portrait"));
                    js("UtilityPanels.open('faction');true");tapSelector("#faction-card .organization-finance summary");
                    check(Boolean.TRUE.equals(js("document.querySelector('#faction-card .organization-finance').innerText.includes('福利实付') && document.querySelector('#faction-card').scrollWidth<=document.querySelector('#faction-card').clientWidth+1")),"Native sect finance");
                    capture("organizations-sect-"+theme+"-"+arguments.getString("orientation","portrait"));
                    async("loadGame("+JSONObject.quote(id)+")");
                    check(Boolean.TRUE.equals(js("!busy && game.family.ledger.resources===window.__familyCash+1000")),"Native treasury persistence");
                }
                result.putString("organization_scope","Four themes, native family funding, real local production, sect finance, no overflow and persistence");
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
                check(Boolean.TRUE.equals(js("game.player.inventory.some(i=>i.id==='qilin_blessing_elixir' && i.quantity===1)")),"Missing starter elixir");
                async("(async()=>{await mutate('/api/games/'+game.id+'/use-item',{item_id:'qilin_blessing_elixir'});return true})()");
                check(Boolean.TRUE.equals(js("game.player.guaranteed_progeny && !game.player.inventory.some(i=>i.id==='qilin_blessing_elixir')")),"Elixir consumption failed");
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
            if(dlcPreferences!=null){if(previousDlcPreferences!=null)java.nio.file.Files.write(dlcPreferences.toPath(),previousDlcPreferences);else java.nio.file.Files.deleteIfExists(dlcPreferences.toPath());}
            finish(Activity.RESULT_OK,result);
        } catch(Throwable failure) {
            try { result.putString("combat_debug",(String)js("JSON.stringify({diagnostics:CombatReplay.diagnostics(),visual:game?.last_combat_report?.visual,pixel:PixelLibrary.active(),loading:document.querySelector('[data-combat-status]')?.textContent,hidden:document.hidden})")); } catch(Throwable ignored) {}
            try { result.putString("preset_status",(String)js("document.querySelector('.custom-preset-bar [role=status]')?.textContent||''")); } catch(Throwable ignored) {}
            android.util.Log.e("ReleaseVerification","Verification failed",failure);
            try {
                result.putString("guide_debug", (String)js("JSON.stringify((()=>{const n=document.querySelector('[data-native-guide-target]'),r=n?.getBoundingClientRect();return {step:game?.tutorial?.guide?.step,target:n?.outerHTML?.slice(0,1200),rect:r,coach:document.querySelector('.tutorial-coach')?.getBoundingClientRect(),hit:r?document.elementFromPoint(r.left+r.width/2,r.top+r.height/2)?.outerHTML?.slice(0,1200):null,dialog:Array.from(document.querySelectorAll('dialog[open]')).map(d=>d.id)};})())"));
                result.putString("action_debug",(String)js("JSON.stringify({world:game?.player?.world,busy,pending:game?.pending_event?.id,theme:document.documentElement.dataset.theme,viewport:[innerWidth,innerHeight],scroll:[scrollX,scrollY],cross:document.querySelector('#cross-world-action')?.getBoundingClientRect(),click:window.__releaseNativeTap})"));
                capture("failure-1520");
            } catch(Throwable ignored) { /* Screenshot assertions must not mask the original failure. */ }
            result.putString("status","failed");result.putString("error",failure.toString().substring(0,Math.min(6000,failure.toString().length())));
            try{if(dlcPreferences!=null){if(previousDlcPreferences!=null)java.nio.file.Files.write(dlcPreferences.toPath(),previousDlcPreferences);else java.nio.file.Files.deleteIfExists(dlcPreferences.toPath());}}catch(Exception restore){result.putString("restore_error",restore.toString());}
            finish(Activity.RESULT_CANCELED,result);
        }
    }
}

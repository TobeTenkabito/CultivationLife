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
            long deadline=System.currentTimeMillis()+60000;
            while(web==null && System.currentTimeMillis()<deadline) {
                runOnMainSync(()->web=findWeb(activity.findViewById(android.R.id.content)));
                Thread.sleep(150);
            }
            check(web!=null,"Release WebView did not start");
            while(!Boolean.TRUE.equals(js("typeof configData!=='undefined' && !!configData && !!window.AndroidUI")) && System.currentTimeMillis()<deadline) Thread.sleep(150);
            async("GameThemes.ready");
            check(Boolean.TRUE.equals(js("configData.base_game.version==='1.41.1' && !configData.debug && configData.extensions.length===6 && configData.extensions.every(e=>e.status==='loaded')")),"Version, release mode or DLC mismatch");
            SharedPreferences marker=getTargetContext().getSharedPreferences("release-verification",0);
            String phase=arguments.getString("phase","initial");
            if(phase.equals("quickstart")) {
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

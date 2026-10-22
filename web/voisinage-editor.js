(() => {
  'use strict';
  const triggers=document.querySelectorAll('[data-voisinage-editor]');if(!triggers.length)return;
  const dialog=document.createElement('dialog');dialog.id='voisinage-editor';dialog.className='appearance-dialog voisinage-editor';dialog.setAttribute('aria-labelledby','ve-title');
  dialog.innerHTML=`<div class="dialog-heading"><div><p class="eyebrow">邻域外观</p><h2 id="ve-title">邻域编辑器</h2></div><button type="button" id="ve-close">关闭</button></div>
    <p class="muted">自由搭配你的邻域。外观不改变能力与战斗效果，本机各存档共用。</p>
    <canvas id="ve-canvas" width="960" height="540" aria-label="左侧主角与右侧NPC的邻域预览"></canvas>
    <p id="ve-palette-label" class="muted"></p>
    <fieldset id="ve-fields"><legend>主角搭配</legend><div class="ve-grid">
    <label>轮廓<select id="ve-outline"></select></label><label>内部意象<select id="ve-pattern"></select></label>
    <div class="ve-color-field"><label for="ve-palette">主角颜色</label><div class="ve-color-inputs"><input id="ve-palette" type="color" aria-label="选择主角邻域颜色"><input id="ve-color-hex" type="text" aria-label="主角颜色 HEX 色值" aria-describedby="ve-color-help" maxlength="7" spellcheck="false" autocomplete="off"></div><small id="ve-color-help">点击色块自由取色，或输入 #RRGGBB。</small></div><label>控制样式<select id="ve-control"></select></label>
    <label class="ve-density">内部质感 <output id="ve-density-label"></output><input id="ve-density" type="range" min="20" max="100" step="1"></label></div></fieldset>
    <div class="ve-tools"><label>预览情境<select id="ve-scene"><option value="single">仅看主角场域</option><option value="overlap" selected>双域交叠</option><option value="control">双向控制示意</option></select></label><button type="button" id="ve-next">模拟下一次遭遇</button><button type="button" id="ve-motion">暂停动画</button></div>
    <p class="muted">NPC 每次遭遇从淡色库随机取色，本次预览内保持不变。保存后用于新战斗的邻域回放；历史战报保留当时外观。</p>
    <div class="ve-footer"><span id="ve-status" role="status"></span><button type="button" id="ve-cancel">取消</button><button type="button" id="ve-save">保存搭配</button></div>`;
  document.body.append(dialog);const $=s=>dialog.querySelector(s);
  let draft={...VoisinageAppearance.defaults},npc,renderer,ready=false,busy=false,token=0,raf=0,time=2.8,last=0,lastPaint=0,paused=false,frames=0;
  let scriptsPromise,previewActor='dao-male',actorLabel='主角';
  function scripts(){if(!scriptsPromise)scriptsPromise=Promise.all(['/voisinage-fields.js?v=alpha3','/voisinage-controls.js','/voisinage-preview.js?v=alpha3'].map(src=>new Promise((resolve,reject)=>{const el=document.createElement('script');el.src=src;el.onload=resolve;el.onerror=()=>{el.remove();reject(Error('编辑器组件加载失败，请重新打开'));};document.head.append(el);}))).catch(e=>{scriptsPromise=null;throw e;});return scriptsPromise;}
  function stop(){cancelAnimationFrame(raf);raf=0;last=0;}
  function draw(){if(!ready||!dialog.open)return;renderer.paint(draft,npc,time,$('#ve-scene').value);frames++;
    $('#ve-density-label').textContent=draft.density+'%';$('#ve-palette-label').textContent='左侧：'+actorLabel+' · '+draft.palette.toUpperCase()+'　／　右侧：NPC · '+DomainFields.palettes.find(p=>p.id===npc.palette).name;
  }
  function tick(now){if(!dialog.open||document.hidden||paused)return;if(!last)last=now;time+=Math.min(.1,(now-last)/1000);last=now;if(now-lastPaint>=50){draw();lastPaint=now;}raf=requestAnimationFrame(tick);}
  function animate(){stop();$('#ve-motion').textContent=paused?'播放动画':'暂停动画';if(!paused&&dialog.open&&!document.hidden)raf=requestAnimationFrame(tick);}
  function next(){npc=VoisinageAppearance.createEncounter([{pattern:'star',outline:'star',control:'stars',density:65}])[0];draw();}
  function populate(){
    for(const key of ['outline','pattern','control']){
      const rows=key==='control'?DomainControlEffects.catalog:DomainFields.catalog;
      $('#ve-'+key).replaceChildren(...rows.map(row=>{const option=document.createElement('option');option.value=row.id;option.textContent=row.name;return option;}));
    }
  }
  async function open(){if(dialog.open)return;const own=++token;ready=false;dialog.showModal();$('#ve-status').textContent='正在读取外观设置…';$('#ve-save').disabled=true;$('#ve-fields').disabled=true;
    try{
      const [saved]=await Promise.all([fetch('/api/ui-preferences').then(r=>{if(!r.ok)throw Error('外观设置读取失败，请关闭后重试');return r.json();}),scripts()]);
      const actor=window.VisualAssets?.actor(typeof game==='undefined'?null:game?.player);
      previewActor=actor?actor.replace('actor.human.','').replace('.','-'):'dao-male';actorLabel=actor?'主角':'外观示意人物';
      const assets=await VoisinagePreview.load(previewActor);if(own!==token||!dialog.open)return;
      renderer=VoisinagePreview.create($('#ve-canvas'),assets);populate();draft={...VoisinageAppearance.defaults,...saved.voisinage_appearance};
      draft.palette=DomainFields.colorHex(draft.palette);
      for(const [key,value] of Object.entries(draft))$('#ve-'+key).value=value;
      $('#ve-color-hex').value=draft.palette.toUpperCase();colorValidity(true);
      ready=true;paused=saved.reduced_motion===true||matchMedia('(prefers-reduced-motion: reduce)').matches;time=2.8;next();draw();animate();
      $('#ve-status').textContent='修改后点击“保存搭配”。';$('#ve-save').disabled=false;$('#ve-fields').disabled=false;
    }catch(e){if(own===token&&dialog.open)$('#ve-status').textContent=e.message;}
  }
  for(const key of ['outline','pattern','palette','control','density'])$('#ve-'+key).addEventListener('input',()=>{
    if(!ready||busy)return;draft[key]=key==='density'?Number($('#ve-'+key).value):$('#ve-'+key).value;$('#ve-status').textContent='有尚未保存的修改。';draw();
    if(key==='palette'){$('#ve-color-hex').value=draft.palette.toUpperCase();colorValidity(true);}
  });
  function colorValidity(valid){
    $('#ve-color-hex').setAttribute('aria-invalid',String(!valid));$('#ve-save').disabled=!valid||busy;
    $('#ve-color-help').textContent=valid?'点击色块自由取色，或输入 #RRGGBB。':'请输入完整的六位色值，例如 #89CDBB。';
  }
  $('#ve-color-hex').addEventListener('input',()=>{
    if(!ready||busy)return;const value=$('#ve-color-hex').value,valid=/^#[0-9a-f]{6}$/i.test(value);colorValidity(valid);
    if(!valid)return;draft.palette=value.toLowerCase();$('#ve-palette').value=draft.palette;$('#ve-status').textContent='有尚未保存的修改。';draw();
  });
  $('#ve-scene').onchange=draw;$('#ve-next').onclick=()=>{if(ready)next();};$('#ve-motion').onclick=()=>{if(ready){paused=!paused;animate();}};
  $('#ve-close').onclick=$('#ve-cancel').onclick=()=>dialog.close();
  $('#ve-save').onclick=async()=>{
    if(!ready||busy||$('#ve-color-hex').getAttribute('aria-invalid')==='true')return;busy=true;const own=token,snapshot={...draft};$('#ve-save').disabled=true;$('#ve-fields').disabled=true;$('#ve-status').textContent='正在保存…';
    try{const response=await fetch('/api/ui-preferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({voisinage_appearance:snapshot})});
      if(!response.ok)throw Error('保存失败，搭配尚未保存，请重试');await response.json();if(own===token)$('#ve-status').textContent='搭配已保存，下次打开仍会保留。';
    }catch(e){if(own===token)$('#ve-status').textContent=e.message;}
    finally{busy=false;if(own===token){$('#ve-save').disabled=false;$('#ve-fields').disabled=false;}}
  };
  dialog.addEventListener('close',()=>{token++;ready=false;stop();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();else if(ready&&dialog.open)animate();});
  triggers.forEach(b=>b.addEventListener('click',()=>{if(!busy)open();}));
  window.VoisinageEditor={open,status:()=>({open:dialog.open,ready,busy,frames,paused,previewActor,draft:{...draft},npc:npc?{...npc}:null})};
  if(new URLSearchParams(location.search).get('voisinage-editor')==='1')open();
})();

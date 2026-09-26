/* One live game tree, six presentations. Theme changes never call game actions. */
(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const root = document.documentElement;
  const themes = [
    {id:'a', name:'松烟书院', caption:'页首状态 · 温纸松绿', motto:'这一程，向道而行。', bg:'#F9F6ED', ink:'#315C47', symbol:'砚'},
    {id:'b', name:'月下观星', caption:'星月修行 · 深靛月金', motto:'天地辽阔，道在此身。', bg:'#172632', ink:'#DEC58B', symbol:'月'},
    {id:'c', name:'青玉留白', caption:'清晰卡片 · 瓷青留白', motto:'从容选择，步步精进。', bg:'#E8F0EC', ink:'#28644F', symbol:'玉'},
    {id:'d', name:'丹砂金阙', caption:'三栏铭牌 · 玄漆赤铜', motto:'道心不移，各证其途。', bg:'#2C2925', ink:'#DAB677', symbol:'印'},
    {id:'e', name:'江山行卷', caption:'山水行旅 · 底部状态', motto:'一程山水，一程修行。', bg:'#F5F6EE', ink:'#315F49', symbol:'山'},
    {id:'f', name:'竹简纪年', caption:'卷首命籍 · 双页纪事', motto:'凡所经历，皆入此卷。', bg:'#F4E9D2', ink:'#52624A', symbol:'卷'},
  ];
  const motionQuery = matchMedia('(prefers-reduced-motion: reduce)');
  const narrowQuery = matchMedia('(max-width: 1000px)');
  let preferences = {theme:root.dataset.theme || 'a', reduced_motion:root.dataset.motion === 'reduced'};
  let revision = 0, saveQueue = Promise.resolve(), current = null, feedbackTimer = null;
  const stage = document.createElement('section'); stage.className = 'theme-play-area';
  stage.setAttribute('aria-label','修行与生平纪事');
  const action = $('#action-card'), history = $('.history-card');
  action.before(stage); stage.append(action,history);
  const core = document.createElement('div'); core.id = 'cultivation-core';
  $('#cultivate-action').before(core); core.append($('#cultivate-action'));
  const ring = document.createElement('div'); ring.className = 'cultivation-orbit'; ring.setAttribute('aria-hidden','true');
  ring.innerHTML = '<svg viewBox="0 0 300 300"><circle class="orbit-track" cx="150" cy="150" r="142"/><circle class="orbit-value" cx="150" cy="150" r="142" pathLength="100" transform="rotate(-90 150 150)"/></svg><i class="orbit-star"></i>';
  core.prepend(ring);
  const scenery = document.createElement('div'); scenery.id = 'main-scenery'; scenery.className = 'theme-scenery';
  scenery.innerHTML = '<div class="landscape-title-mask"><div class="landscape-title-track"><span>一程山水，一程修行。</span><span aria-hidden="true">一程山水，一程修行。</span></div></div><p>天地有期，此身有道。</p>';
  const art = '<svg class="theme-landscape" viewBox="0 0 800 240" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><g class="scenery-mountains"><path opacity=".12" d="M0 190Q80 135 105 165L190 58 215 86 260 24Q305 100 343 123L400 70 454 133Q488 70 530 40L579 100 632 80Q724 120 800 159V240H0Z"/><path opacity=".2" d="M0 220Q60 162 106 183Q172 85 223 143L267 112Q320 175 372 175L410 126 440 148Q500 107 555 168Q620 130 680 172Q730 150 800 184V240H0Z"/><path opacity=".18" d="M0 227Q80 202 147 221T300 214Q397 200 472 220T680 213T800 218V240H0Z"/></g><g class="scenery-stars">'+Array.from({length:18},(_,i)=>`<circle cx="${45+(i*137)%700}" cy="${12+(i*47)%185}" r="${i%3===0?2:1}" style="--star-delay:${-i*.43}s"/>`).join('')+'</g><path class="scenery-moon" d="M650 30A35 35 0 1 0 697 78A36 36 0 0 1 650 30Z"/></svg>';
  scenery.insertAdjacentHTML('afterbegin',art);
  $('.start-theme-art').innerHTML = art;
  const hud = document.createElement('section'); hud.id='player-hud'; hud.setAttribute('aria-label','人物与当前资源');
  hud.innerHTML = '<button class="hud-identity" type="button" aria-haspopup="dialog"><span class="hud-avatar" aria-hidden="true">修</span><span class="hud-identity-copy"><span><strong id="hud-name"></strong><b id="hud-realm"></b></span><small id="hud-age"></small><small id="hud-power"></small></span><span class="hud-details-label">人物详情 ›</span></button><div class="hud-resources"></div><p id="hud-notice" class="hidden"></p>';
  const resources = hud.querySelector('.hud-resources');
  for (const [key,label] of [['opportunity','机缘'],['hp','气血 HP'],['mp','法力 MP']]) {
    const b=document.createElement('button');b.type='button';b.id=`hud-${key}`;b.className=`hud-resource hud-${key}`;b.setAttribute('aria-haspopup','dialog');
    b.innerHTML='<span class="hud-meter-heading"><span class="hud-meter-label"></span><b class="hud-percent"></b></span><span class="hud-values"><strong></strong><small></small></span><span class="hud-track" role="progressbar"><i></i></span><span class="hud-resource-warning"></span>';
    b.querySelector('.hud-meter-label').textContent=label;
    resources.append(b);
  }
  $('#player-details-content').append($('.character-card'));
  function openDialog(id) { const d=$(`#${id}`); if(!d.open)d.showModal(); }
  hud.addEventListener('click', e=>{if(e.target.closest('button'))openDialog('player-details-dialog');});
  // Opportunity moves into the lunar core in B, so bind its action independently.
  const opportunity = hud.querySelector('#hud-opportunity');
  opportunity.addEventListener('click',e=>{e.stopPropagation();openDialog('player-details-dialog');});
  $('#theme-open').onclick=()=>openDialog('theme-dialog');
  document.querySelectorAll('[data-close-dialog]').forEach(b=>b.addEventListener('click',()=>$(`#${b.dataset.closeDialog}`).close()));
  for(const id of ['theme-dialog','player-details-dialog']) {
    const dialog=$(`#${id}`);
    dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});
  }
  const closeDialogs=()=>document.querySelectorAll('.appearance-dialog[open]').forEach(d=>d.close());
  function reflow() {
    const theme=preferences.theme;
    const focus=document.activeElement;
    const restore=focus&&hud.contains(focus);
    if(theme==='b') core.insertBefore(opportunity,$('#cultivate-action'));
    else resources.prepend(opportunity);
    if(theme==='a'||theme==='b') action.prepend(hud);
    else if(theme==='e'&&!narrowQuery.matches) stage.append(hud);
    else stage.prepend(hud);
    if(theme==='e')stage.insertBefore(scenery,action);else scenery.remove();
    window.ThemeComposition?.arrange(theme);
    if(restore&&focus.isConnected)focus.focus({preventScroll:true});
  }
  function cache() { try{localStorage.setItem('cultivation-appearance',JSON.stringify(preferences));}catch(_){} }
  function apply() {
    root.classList.add('theme-switching');
    root.dataset.theme=preferences.theme;
    root.dataset.motion=preferences.reduced_motion?'reduced':'full';
    const theme=themes.find(t=>t.id===preferences.theme);
    $('#theme-open').textContent=`主题 · ${theme.name}`;
    document.querySelectorAll('[data-theme-choice]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.themeChoice===preferences.theme)));
    document.querySelectorAll('[data-motion-setting]').forEach(i=>i.checked=preferences.reduced_motion);
    $('.theme-motto').textContent=theme.motto;
    reflow();cache();
    void root.offsetWidth;
    requestAnimationFrame(()=>root.classList.remove('theme-switching'));
    window.dispatchEvent(new CustomEvent('game:theme-change',{detail:{...preferences}}));
  }
  function save(patch) {
    revision++; preferences={...preferences,...patch};apply();
    const state={...preferences};
    const status=$('.theme-save-status');status.textContent='正在保存外观偏好…';
    saveQueue=saveQueue.catch(()=>{}).then(async()=>{
      const response=await fetch('/api/ui-preferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(state)});
      if(!response.ok)throw new Error('外观已切换，但偏好保存失败，请稍后重试。');
      if(state.theme===preferences.theme&&state.reduced_motion===preferences.reduced_motion)status.textContent='外观偏好已保存，下次启动仍会保留。';
    }).catch(error=>{status.textContent=error.message;const t=$('#toast');t.textContent=error.message;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),3500);});
    return saveQueue;
  }
  document.querySelectorAll('[data-theme-picker]').forEach(container=>{
    for(const t of themes){const b=document.createElement('button');b.type='button';b.dataset.themeChoice=t.id;b.className='theme-choice';b.setAttribute('aria-pressed','false');b.style.setProperty('--choice-bg',t.bg);b.style.setProperty('--choice-ink',t.ink);
      b.innerHTML=`<span class="theme-choice-art" aria-hidden="true"><i>${t.symbol}</i></span><span><b>${t.id.toUpperCase()} · ${t.name}</b><small>${t.caption}</small></span><span class="theme-chosen" aria-hidden="true">✓</span>`;
      b.addEventListener('click',()=>save({theme:t.id}));container.append(b);}
  });
  document.querySelectorAll('[data-motion-setting]').forEach(i=>i.addEventListener('change',()=>save({reduced_motion:i.checked})));
  const dlc={guixu:'guixu','ghost-soul':'ghost','ghost-attachment':'ghost','ghost-parade':'ghost',sage:'sage','sage-inner-outer':'sage',bloodline:'bloodline',intrigue:'intrigue',tianji:'tianji'};
  for(const [name,family] of Object.entries(dlc)){const b=$(`[data-panel-target="${name}"]`);if(b){b.dataset.dlc=family;b.title=`${b.title} · DLC`;}}
  const precise=value=>Number.isFinite(Number(value))?Number(value).toLocaleString('zh-CN',{maximumFractionDigits:2}):'—';
  function compact(value){value=Number(value);if(!Number.isFinite(value))return '—';if(Math.abs(value)>=1e12)return precise(value/1e12)+'万亿';if(Math.abs(value)>=1e8)return precise(value/1e8)+'亿';if(Math.abs(value)>=1e6)return precise(value/1e4)+'万';return precise(value);}
  function resource(key,now,max,label) {
    const node=key==='opportunity'?opportunity:$(`#hud-${key}`);
    const ratio=Number(max)>0?Math.max(0,Math.min(1,Number(now)/Number(max))):0;
    const percent=Number.isFinite(ratio)?Math.round(ratio*1000)/10:0;
    node.querySelector('.hud-meter-label').textContent=label;
    node.querySelector('.hud-percent').textContent=`${percent}%`;
    node.querySelector('.hud-values strong').textContent=compact(now);
    node.querySelector('.hud-values small').textContent=`/ ${compact(max)}`;
    const exact=`${label}：${precise(now)} / ${precise(max)}，${percent}%`;
    node.title=exact;node.setAttribute('aria-label',exact+'，查看人物详情');
    const bar=node.querySelector('.hud-track');bar.setAttribute('aria-label',label);bar.setAttribute('aria-valuemin','0');bar.setAttribute('aria-valuemax',String(Math.max(0,Number(max)||0)));bar.setAttribute('aria-valuenow',String(Math.max(0,Math.min(Number(max)||0,Number(now)||0))));bar.setAttribute('aria-valuetext',exact);
    node.style.setProperty('--progress',`${percent}%`);node.style.setProperty('--ratio',String(percent));
    const low=key==='hp'&&Number(now)>0&&ratio<.25;node.classList.toggle('low',low);node.querySelector('.hud-resource-warning').textContent=low?'气血偏低':'';
    if(key==='opportunity')ring.querySelector('.orbit-value').style.strokeDasharray=`${percent} 100`;
  }
  function reduced(){return preferences.reduced_motion||motionQuery.matches;}
  function feedback(target=history) {
    if(reduced())return;
    clearTimeout(feedbackTimer);
    document.querySelectorAll('.theme-feedback-active').forEach(n=>n.classList.remove('theme-feedback-active'));
    void target.offsetWidth;target.classList.add('theme-feedback-active');
    core.classList.add('cultivation-pulse');
    feedbackTimer=setTimeout(()=>{target.classList.remove('theme-feedback-active');core.classList.remove('cultivation-pulse');},900);
  }
  function render(data) {
    const previous=current;current=data;
    const p=data.player;
    document.body.classList.add('in-game');
    $('#theme-entry').classList.add('hidden');
    $('#hud-name').textContent=p.name;$('.hud-avatar').textContent=p.name.slice(0,1);
    $('#hud-realm').textContent=p.realm_name;
    $('#hud-age').textContent=`${p.age} 岁 · ${p.lifespan==null?'寿元无尽':`寿元 ${precise(p.lifespan)} 年`} · ${p.world_name} / ${p.location_name}`;
    $('#hud-power').textContent=`战斗力 ${compact(p.combat_power)} · ${p.path_name}`;
    $('#hud-power').title=`战斗力 ${precise(p.combat_power)} · 组队战力 ${precise(p.battle_power||p.combat_power)}`;
    resource('opportunity',p.opportunity,p.opportunity_required,'机缘');resource('hp',p.hp,p.max_hp,'气血 HP');resource('mp',p.mp,p.max_mp,p.resource_name&&p.resource_name!=='MP'?p.resource_name:'法力 MP');
    hud.classList.toggle('immortal-resource',p.resource_kind==='immortal');
    const notices=[];
    if(Number(p.hp)>0&&Number(p.hp)/Math.max(1,Number(p.max_hp))<.25)notices.push('气血偏低，请留意行动风险');
    if(p.lifespan!=null&&p.lifespan-p.age<=Number(p.time_unit_years||1)*2&&p.alive)notices.push(`寿元余 ${Math.max(0,p.lifespan-p.age)} 年`);
    if(data.tribulation?.next_age!=null&&data.tribulation.years_remaining<=Number(p.time_unit_years||1)*2)notices.push(`雷劫将至：${data.tribulation.years_remaining} 年后`);
    if(data.pending_event)notices.push('有待回应的事件');
    $('#hud-notice').textContent=notices.join(' · ');$('#hud-notice').classList.toggle('hidden',!notices.length);
    if(data.pending_event)closeDialogs();
    window.ThemeComposition?.render(data);
    if(previous?.id===data.id&&(previous.player.world_age??previous.player.age)!==(p.world_age??p.age))feedback();
  }
  function showStart(){current=null;closeDialogs();document.body.classList.remove('in-game');$('#theme-entry').classList.remove('hidden');}
  narrowQuery.addEventListener('change',reflow);
  motionQuery.addEventListener('change',()=>{if(reduced())document.querySelectorAll('.theme-feedback-active,.cultivation-pulse').forEach(n=>n.classList.remove('theme-feedback-active','cultivation-pulse'));});
  document.addEventListener('visibilitychange',()=>root.dataset.paused=String(document.hidden));
  window.addEventListener('game:panel-open',e=>{if(preferences.theme==='f')feedback(e.detail.target);});
  apply();
  const initialRevision=revision;
  const ready=fetch('/api/ui-preferences').then(r=>{if(!r.ok)throw new Error();return r.json();}).then(saved=>{if(revision===initialRevision){preferences={theme:themes.some(t=>t.id===saved.theme)?saved.theme:'a',reduced_motion:saved.reduced_motion===true};apply();}}).catch(()=>{});
  window.GameThemes={render,showStart,ready,get preferences(){return {...preferences};},get saved(){return saveQueue;}};
})();

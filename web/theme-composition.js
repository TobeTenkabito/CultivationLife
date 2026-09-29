/* Compositions transcribed from the approved R3 SVGs, with live game content. */
(() => {
  'use strict';
  const $=s=>document.querySelector(s), root=document.documentElement;
  const stage=$('.theme-play-area'), action=$('#action-card'), core=$('#cultivation-core');
  const hud=$('#player-hud'), identity=$('.hud-identity'), resources=$('.hud-resources');
  resources.addEventListener('click',e=>{if(e.target.closest('button')){e.stopPropagation();if(!$('#player-details-dialog').open)$('#player-details-dialog').showModal();}});
  const primary=$('.primary-actions'), folds=$('.action-folds'), history=$('.history-card');
  const orbit=$('.cultivation-orbit svg'), ns='http://www.w3.org/2000/svg';
  const ticks=document.createElementNS(ns,'g');ticks.setAttribute('class','orbit-ticks');
  for(let i=0;i<36;i++){const angle=i*Math.PI/18,r=i%3?148:154,line=document.createElementNS(ns,'line');for(const [key,value] of Object.entries({x1:150+143*Math.cos(angle),y1:150+143*Math.sin(angle),x2:150+r*Math.cos(angle),y2:150+r*Math.sin(angle)}))line.setAttribute(key,String(value));ticks.append(line);}orbit.prepend(ticks);
  let current=null, units=1, selected='daily', dispatch=null;
  const world=document.createElement('div');world.className='brand-world';
  world.innerHTML='<b></b><small></small>';$('.brand').append(world);
  const nav=document.createElement('div');nav.className='action-navigation';
  nav.innerHTML='<div class="action-tabs" role="tablist" aria-label="修行行动"><button type="button" role="tab" id="tab-daily" data-action-tab="daily" aria-controls="daily-actions" aria-selected="true">日常修行</button><button type="button" role="tab" id="tab-living" data-action-tab="living" aria-controls="living-actions" aria-selected="false" tabindex="-1">历练与生计</button><button type="button" role="tab" id="tab-combat" data-action-tab="combat" aria-controls="combat-actions" aria-selected="false" tabindex="-1">斗法与狩猎</button></div><label class="action-units">行动单位 <span><button type="button" data-unit-step="-1" aria-label="减少行动单位">−</button><input id="action-units" type="number" min="1" max="10" value="1" aria-label="行动单位数量"><button type="button" data-unit-step="1" aria-label="增加行动单位">+</button></span></label>';
  primary.before(nav);primary.id='daily-actions';primary.setAttribute('role','tabpanel');primary.setAttribute('aria-labelledby','tab-daily');
  [...folds.children].forEach((d,i)=>{d.id=i?'combat-actions':'living-actions';d.open=true;d.setAttribute('role','tabpanel');d.setAttribute('aria-labelledby',i?'tab-combat':'tab-living');});
  const extras=document.createElement('div');extras.className='special-actions actions';primary.after(extras);
  for(const id of ['sense-breakthrough-action','spirit-crossing-action','cross-world-action','cross-world-secondary-action'])extras.append($('#'+id));
  const dock=document.createElement('div');dock.className='secondary-actions';
  const rest=primary.querySelector('[data-action=rest]'), neighbors=primary.querySelector('[data-action=befriend_neighbors]');
  const details=document.createElement('button');details.type='button';details.className='composition-details';details.textContent='人物详情 ›';details.onclick=()=>$('#player-details-dialog').showModal();
  const historyArea=document.createElement('div');historyArea.className='journal-area';history.before(historyArea);historyArea.append(history);
  const letter=document.createElement('aside');letter.className='journal-letter';
  letter.innerHTML='<i class="letter-seal" aria-hidden="true">信</i><div class="letter-copy"><p class="letter-eyebrow">坊市见闻</p><h3></h3><p class="letter-summary"></p></div><button type="button">阅读已收录纪事 ›</button>';
  historyArea.append(letter);
  const letterDialog=document.createElement('dialog');letterDialog.className='appearance-dialog journal-dialog';
  letterDialog.setAttribute('aria-labelledby','journal-dialog-title');
  letterDialog.innerHTML='<div class="dialog-heading"><h2 id="journal-dialog-title"></h2><button type="button">返回</button></div><p class="journal-date"></p><p class="journal-text"></p>';
  document.body.append(letterDialog);letterDialog.querySelector('button').onclick=()=>letterDialog.close();
  letter.querySelector('button').onclick=()=>{if(dispatch){letterDialog.querySelector('h2').textContent=dispatch.title;letterDialog.querySelector('.journal-date').textContent=`${dispatch.age} 岁`;letterDialog.querySelector('.journal-text').textContent=dispatch.summary;letterDialog.showModal();}};
  const tools=document.createElement('div');tools.className='journal-controls';tools.innerHTML='<button type="button" data-journal="all" aria-pressed="true">全部</button><button type="button" data-journal="self" aria-pressed="false">仅自己</button><button type="button" data-journal="filter" aria-expanded="false" aria-controls="history-filters">筛选</button><button type="button" data-journal="expand" aria-expanded="false">展开纪事</button>';
  history.querySelector('.section-title').append(tools);
  tools.onclick=e=>{const b=e.target.closest('[data-journal]');if(!b)return;
    const mode=b.dataset.journal;
    if(mode==='filter'){const open=history.classList.toggle('filters-open');b.setAttribute('aria-expanded',String(open));}
    else if(mode==='expand'){const open=history.classList.toggle('history-expanded');b.setAttribute('aria-expanded',String(open));b.textContent=open?'收起纪事':'展开纪事';}
    else {history.querySelectorAll('#history-filters input').forEach(i=>{i.checked=mode==='all'||i.value==='self';i.dispatchEvent(new Event('change',{bubbles:true}));});tools.querySelectorAll('[aria-pressed]').forEach(n=>n.setAttribute('aria-pressed',String(n===b)));}
  };
  const footer=document.createElement('footer');footer.className='theme-signature';footer.innerHTML='<span></span><small></small>';stage.after(footer);
  const names={a:['松烟书院','页首状态带 · 常看信息与行动同处一屏'],b:['月下观星','机缘入月轮 · 血蓝置于行动上缘'],c:['青玉留白','身份页签与状态卡 · 当前值清晰呈现'],d:['丹砂金阙','人物铭牌与三栏仪表'],e:['江山行卷','山水行旅 · 底部独立状态带'],f:['竹简纪年','卷首命籍 · 左页修行，右页纪事']};
  for(const [node,glyph] of [[$('#cultivate-action'),'修'],[$('#body-train-action'),'体'],[$('#sense-train-action'),'识'],[rest,'息'],[neighbors,'缘']]){
    const emblem=document.createElement('i');emblem.className='action-emblem';emblem.setAttribute('aria-hidden','true');emblem.textContent=glyph;node.prepend(emblem);
    const time=document.createElement('small');time.className='action-duration';node.append(time);
    const cta=document.createElement('em');cta.className='action-cta';node.append(cta);
  }
  // The E scenery is detached while another theme is active; keep its original reference via the manager on reflow.
  function selectTab(tab){selected=tab;action.dataset.selectedCategory=tab;
    nav.querySelectorAll('[role=tab]').forEach(b=>{const on=b.dataset.actionTab===tab;b.setAttribute('aria-selected',String(on));b.tabIndex=on?0:-1;});
    primary.hidden=tab!=='daily';folds.hidden=tab==='daily';[...folds.children].forEach(d=>d.hidden=d.id!==tab+'-actions');
    dock.hidden=tab!=='daily';arrange(root.dataset.theme);
  }
  nav.querySelectorAll('[role=tab]').forEach(b=>b.onclick=()=>selectTab(b.dataset.actionTab));
  nav.querySelector('.action-tabs').onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const keys=['daily','living','combat'];let i=keys.indexOf(selected);i=e.key==='Home'?0:e.key==='End'?2:(i+(e.key==='ArrowRight'?1:2))%3;selectTab(keys[i]);nav.querySelector(`[data-action-tab=${keys[i]}]`).focus();};
  function updateTimes(){const years=Number(current?.player?.time_unit_years||1)*units;
    document.querySelectorAll('.action-duration').forEach(n=>n.textContent=root.dataset.theme==='e'?`${years} 年`:`本次耗时 ${years} 年`);
    $('#action-units').value=units;nav.querySelector('[data-unit-step="-1"]').disabled=units<=1;nav.querySelector('[data-unit-step="1"]').disabled=units>=10;
    $('#action-units').title='1–10 个行动单位；重大事件会提前中断行动';
  }
  $('#action-units').onchange=e=>{units=Math.max(1,Math.min(10,Math.trunc(Number(e.target.value)||1)));updateTimes();};
  nav.querySelectorAll('[data-unit-step]').forEach(b=>b.onclick=()=>{units=Math.max(1,Math.min(10,units+Number(b.dataset.unitStep)));updateTimes();});
  function arrange(theme){
    // These are separate compositions; no theme inherits A's card layout.
    hud.prepend(identity);hud.append(resources);resources.prepend($('#hud-opportunity'));
    primary.prepend(core);primary.append(rest,neighbors);dock.remove();details.remove();
    action.insertBefore(nav,primary);action.insertBefore(resources,primary);hud.append(resources);
    if(theme==='a')action.prepend(hud);
    else if(theme==='b'){
      action.prepend(hud);core.prepend($('#hud-opportunity'));action.append(core,details);
    }else if(theme==='d'){
      action.prepend(hud);nav.after(resources);dock.append(rest,neighbors);primary.after(dock);dock.hidden=selected!=='daily';
    }else if(theme==='e')stage.append(hud);
    else stage.prepend(hud);
    if(theme==='b'&&selected!=='daily') {core.classList.add('core-summary');action.append(core);}else core.classList.remove('core-summary');
    const landscape=$('#main-scenery');
    if(landscape&&!landscape.dataset.originalArt){landscape.dataset.originalArt='true';landscape.innerHTML='<img class="original-landscape" src="/themes/landscape.svg" alt=""><p class="landscape-eyebrow">山中无历日</p><div class="landscape-title-mask"><div class="landscape-title-track"><span>一程山水，一程修行。</span><span aria-hidden="true">一程山水，一程修行。</span></div></div><p class="landscape-place"></p><small class="landscape-date"></small>';}
    $('#cultivate-action .action-cta').textContent=theme==='e'||theme==='f'?'→':'入定修炼 →';
    for(const n of [$('#body-train-action'),$('#sense-train-action'),rest,neighbors])n.querySelector('.action-cta').textContent=theme==='d'&&![rest,neighbors].includes(n)?'开始修行 →':theme==='c'?'选择 →':['e','f'].includes(theme)?'→':'›';
    footer.firstElementChild.textContent=`${theme.toUpperCase()} / ${names[theme][0]}`;footer.lastElementChild.textContent=names[theme][1];
    if(current)updateWorld();
    updateTimes();
  }
  function updateWorld(){const p=current.player;world.querySelector('b').textContent=`${p.world_name} / ${p.location_name}`;world.querySelector('small').textContent=`第 ${p.world_age??p.age} 年 · ${p.realm_name}`;
    const power=$('#hud-power'),base=power.textContent.split(' · ')[0];
    power.textContent=([...(['a','b'].includes(root.dataset.theme)?[base,p.spirit_root_display||p.spirit_root_name,p.path_name]:[base]), `仙痕 ${Number(p.immortal_traces||0).toLocaleString('zh-CN')}`]).filter(Boolean).join(' · ');
    $('#hud-age').textContent=`${p.age} 岁 · ${p.lifespan==null?'寿元无尽':`寿元 ${p.lifespan} 年`}`;
    const place=$('.landscape-place'),date=$('.landscape-date');if(place)place.textContent=`${p.location_name}外，远山依旧，万事徐来。`;if(date)date.textContent=world.querySelector('small').textContent;
  }
  function render(data){current=data;updateWorld();updateTimes();
    $('#hud-mp').classList.toggle('immortal-resource',data.player.resource_kind==='immortal');
    dispatch=(data.history||[]).find(r=>/商盟|委托|拍卖|交换|坊市/.test(r.title))||(data.history||[])[0]||null;
    letter.querySelector('h3').textContent=dispatch?.title||'此卷待续';letter.querySelector('.letter-summary').textContent=dispatch?.summary||'这一程的见闻，将随你的经历收录于此。';letter.querySelector('button').disabled=!dispatch;
    if(data.pending_event&&letterDialog.open)letterDialog.close();
  }
  window.ThemeComposition={arrange,render,get units(){return units;}};
  selectTab('daily');updateTimes();
})();

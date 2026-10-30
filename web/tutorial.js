/* Real controls remain in place. The guide observes clicks, never clones a control. */
(() => {
  const $=s=>document.querySelector(s), dialog=$('#tutorial-dialog');
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;};
  let data=null,send=null,working=false,startEnabled=false,currentKey='',focus=null,frame=0,preparing=false,selectedSect='',duration=null;
  let interfaceGuide=null;
  try{startEnabled=localStorage.getItem('wendao-tutorial-next-life')==='true';}catch(_){}
  const handbook=$('#tutorial-handbook');
  const handbookTools=node('div',null,'handbook-tools'),edition=node('p',null,'handbook-edition');
  const searchLabel=node('label','查找你遇到的问题','handbook-search-label'),search=node('input');
  search.type='search';search.placeholder='搜索：飞升、魔气、愿力、阵法、存档……';search.id='handbook-search';search.maxLength=100;
  searchLabel.htmlFor=search.id;
  const categories=node('div',null,'handbook-categories');categories.setAttribute('role','group');categories.setAttribute('aria-label','百科章节分类');
  const matches=node('p',null,'handbook-matches');matches.setAttribute('role','status');
  handbookTools.append(edition,searchLabel,search,categories,matches);handbook.before(handbookTools);
  let handbookCategory='全部',handbookRows=[],handbookConfig={},handbookScope='';
  const currentHandbookScope=()=>JSON.stringify([data?.id,data?.asura?.available,data?.player?.realm_index,data?.player?.world]);
  function filterHandbook(){
    const words=search.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    let count=0;
    for(const row of handbookRows){
      row.element.hidden=(handbookCategory!=='全部'&&row.chapter.category!==handbookCategory)||!words.every(w=>row.text.includes(w));
      if(!row.element.hidden)count++;
      row.element.open=words.length? !row.element.hidden:row.expanded;
    }
    for(const b of categories.children)b.setAttribute('aria-pressed',String(b.textContent===handbookCategory));
    matches.textContent=count?`找到 ${count} / ${handbookRows.length} 章 · 点击标题展开`:'没有匹配章节。可换个关键词或切回“全部”；未加载 DLC 的专属章节不会显示。';
  }
  function resetHandbookFilter(){search.value='';handbookCategory='全部';filterHandbook();}
  function renderHandbook(config){
    handbookConfig=config;handbookScope=currentHandbookScope();
    const opened=new Set(handbookRows.filter(r=>r.expanded).map(r=>r.chapter.id));
    const chapters=TutorialHandbook.build(config,data);
    if(handbookCategory!=='全部'&&!chapters.some(c=>c.category===handbookCategory))handbookCategory='全部';
    handbook.replaceChildren();categories.replaceChildren();handbookRows=[];
    const loaded=(config.extensions||[]).filter(e=>e.status==='loaded'&&e.kind==='dlc');
    const hasMods=(config.extensions||[]).some(e=>e.status==='loaded'&&e.kind==='mod');
    edition.textContent=`本体 v${config.base_game?.version||'—'} · ${loaded.length?`已加载 ${loaded.length} 个 DLC`:hasMods?'未加载 DLC，另有 MOD':'纯本体规则'}。`+
      (loaded.length?`当前：${loaded.map(e=>e.name).join('、')}。`:'')+
      ((config.extensions||[]).some(e=>e.next_enabled!=null)?' 开关有待重启改动，本百科仍按当前已加载内容显示。':'')+
      ' 可按分类或关键词检索；高阶修行章节随当前角色进境开放。';
    for(const category of ['全部',...new Set(chapters.map(c=>c.category))]){
      const b=node('button',category);b.type='button';b.onclick=()=>{handbookCategory=category;filterHandbook();};categories.append(b);
    }
    chapters.forEach((c,i)=>{
      const d=node('details'),body=node('div',null,'tutorial-copy');d.dataset.chapter=c.id;
      const summary=node('summary');summary.append(node('span',`${String(i+1).padStart(2,'0')} · ${c.category}`,'handbook-chapter-meta'),node('span',c.title));d.append(summary);
      body.append(node('p',c.lead,'tutorial-lead'));
      if(c.table){
        const wrap=node('div',null,'handbook-table-wrap'),table=node('table');table.append(node('caption',c.table.caption));
        const head=node('thead'),hr=node('tr');for(const label of c.table.headers){const th=node('th',label);th.scope='col';hr.append(th);}head.append(hr);table.append(head);
        const tbody=node('tbody');for(const cells of c.table.rows){const tr=node('tr');cells.forEach((text,index)=>{const cell=node(index?'td':'th',text);if(!index)cell.scope='row';tr.append(cell);});tbody.append(tr);}table.append(tbody);wrap.append(table);body.append(wrap);
      }
      for(const [title,...ps] of c.sections){body.append(node('h3',title));ps.forEach(p=>body.append(node('p',p)));}
      d.append(body);handbook.append(d);
      const row={element:d,chapter:c,text:JSON.stringify(c).toLocaleLowerCase(),expanded:opened.has(c.id)};handbookRows.push(row);
      d.addEventListener('toggle',()=>{if(!search.value.trim())row.expanded=d.open;});
    });
    filterHandbook();
  }
  search.addEventListener('input',filterHandbook);
  renderHandbook({});
  const root=node('div',null,'tutorial-tour');root.hidden=true;
  root.innerHTML='<svg class="tutorial-shade" aria-hidden="true"><path fill-rule="evenodd"/></svg><div class="tutorial-focus" aria-hidden="true"></div><svg class="tutorial-arrow" aria-hidden="true"><defs><marker id="tutorial-arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z"/></marker></defs><path marker-end="url(#tutorial-arrowhead)"/></svg><section class="tutorial-coach" role="region" aria-label="操作引导"><small id="guide-progress"></small><h2 id="guide-title"></h2><p id="guide-copy" aria-live="polite"></p><p id="guide-hint"></p><div><button id="guide-pause" type="button">暂停引导</button><button id="guide-next" type="button">明白了，继续</button></div></section>';
  document.body.append(root);
  const coach=root.querySelector('.tutorial-coach'), outline=root.querySelector('.tutorial-focus');
  const interfaceShortcut=node('button','先认识新版界面');interfaceShortcut.type='button';interfaceShortcut.id='guide-interface-start';
  coach.querySelector('#guide-pause').before(interfaceShortcut);
  const sectSelect=node('select');sectSelect.id='guide-sect-select';sectSelect.setAttribute('aria-label','引荐宗门');sectSelect.hidden=true;
  coach.querySelector('#guide-hint').before(sectSelect);
  sectSelect.onchange=()=>{selectedSect=sectSelect.value;currentKey='';draw();};
  const steps=window.TutorialSteps;
  function guideInfo(){
    if(!interfaceGuide)return data?.tutorial.guide;
    if(!interfaceGuide.active)return null;
    return {active:true,index:interfaceGuide.index,total:interfaceGuide.keys.length,step:interfaceGuide.keys[interfaceGuide.index],
      blocked:!data?.player.alive?'此生已结束，可在另一个角色中体验界面导览。':data?.tutorial.guide.blocked||(data?.pending_event||!$('#prison-card').classList.contains('hidden')?'请先暂停导览，处理眼前的事件或困境，再从新手教程继续。':''),admissions:[]};
  }
  const definition=g=>interfaceGuide?window.TutorialInterface.resolve(g.step):steps[g.step];
  function clearViews(){
    window.GameNavigation?.close({restoreFocus:false});
    document.querySelectorAll('dialog[open]').forEach(d=>d.close());
    document.querySelectorAll('.utility-panel.panel-open').forEach(n=>UtilityPanels.close(n.id.replace(/-card$/,'')));
  }
  function startInterface(){
    if(!data||working)return;
    stop();
    if(!interfaceGuide)interfaceGuide={id:data.id,index:0,keys:window.TutorialInterface.keys(),active:true};
    interfaceGuide.active=true;
    clearViews();
    draw();
  }
  function visible(selector){return [...document.querySelectorAll(selector)].filter(n=>{const r=n.getBoundingClientRect();return r.width>0&&r.height>0&&!n.closest('.hidden');});}
  function stop(){root.hidden=true;focus=null;currentKey='';observer.disconnect();}
  async function act(action,extra={}){
    if(working)return;
    if(interfaceGuide){
      if(action==='disable')interfaceGuide.active=false;
      else if(action==='guide_next'){
        if(guideInfo()?.blocked)return;
        if(interfaceGuide.index===interfaceGuide.keys.length-1){interfaceGuide=null;if(data?.tutorial.guide.active)clearViews();}
        else interfaceGuide.index++;
      }
      currentKey='';draw();return;
    }
    if(!send)return;working=true;draw();try{await send({action,step:data?.tutorial.guide.step,...extra});}finally{working=false;draw();}
  }
  function context(step){
    if(interfaceGuide){if(guideInfo().step!=='ui_scenery')window.PixelHome?.closeDrawer();step.prepare?.();}
    const entry=document.querySelector(step.target)?.dataset.panelTarget;
    if(entry&&!interfaceGuide)window.GameNavigation?.reveal(entry);
    if(['handbook','ui_handbook'].includes(guideInfo()?.step))resetHandbookFilter();
    if(step.context==='details'){if(!$('#player-details-dialog').open)$('#player-details-dialog').showModal();}
    else if(['living','daily'].includes(step.context))$(`#tab-${step.context}`).click();
    else if(step.context&&!$(`#${step.context}-card`).classList.contains('panel-open'))UtilityPanels.open(step.context);
    if(!interfaceGuide&&['equip','art_result'].includes(data.tutorial.guide.step))$('.technique-library').open=true;
  }
  function skippable(g){return (g.step==='equip'&&!g.art)||(['meet','mentor_choice'].includes(g.step)&&g.mentor_reason)||(g.step==='join'&&(data.faction.member||!g.admissions.length));}
  function layout(){frame=0;if(root.hidden)return;
    const coachScroll=coach.scrollTop;
    const w=innerWidth,h=innerHeight,pad=8,r=focus?.getBoundingClientRect();
    const x=r?Math.max(pad,r.left-5):w/2,y=r?Math.max(pad,r.top-5):h/3;
    const right=r?Math.min(w-pad,r.right+5):x,bottom=r?Math.min(h-pad,r.bottom+5):y;
    const a=Math.max(0,right-x),b=Math.max(0,bottom-y);
    outline.style.cssText=`left:${x}px;top:${y}px;width:${a}px;height:${b}px;display:${r?'block':'none'}`;
    root.querySelector('.tutorial-shade').setAttribute('viewBox',`0 0 ${w} ${h}`);
    root.querySelector('.tutorial-shade path').setAttribute('d',`M0 0H${w}V${h}H0Z M${x} ${y}V${bottom}H${right}V${y}Z`);
    const cw=Math.min(350,w-24);coach.style.width=cw+'px';coach.style.maxHeight=(h-24)+'px';let ch=coach.getBoundingClientRect().height;
    let cx=Math.max(12,Math.min(w-cw-12,x)),cy=bottom+22;
    if(w>780&&right+cw+30<w){cx=right+22;cy=Math.max(12,Math.min(y,h-ch-12));}
    else if(cy+ch>h-12){cy=y-ch-22;if(cy<12)cy=h-ch-12;}
    cy=Math.max(12,cy);
    // Narrow WebViews may have room for neither the full coach above nor below.
    // Keep the live target touchable; the explanation can scroll in its own box.
    if(r&&cx<right&&cx+cw>x&&cy<bottom&&cy+ch>y){
      const above=y-34,below=h-bottom-34,room=Math.max(above,below);
      if(room>=100){coach.style.maxHeight=room+'px';ch=coach.getBoundingClientRect().height;cy=below>=above?bottom+22:y-ch-22;}
    }
    coach.style.left=cx+'px';coach.style.top=cy+'px';
    coach.scrollTop=coachScroll;
    const svg=root.querySelector('.tutorial-arrow');svg.setAttribute('viewBox',`0 0 ${w} ${h}`);
    const tx=Math.min(w-12,Math.max(12,x+a/2)),ty=cy>=bottom?bottom+2:y-2;
    const sx=Math.min(cx+cw-20,Math.max(cx+20,tx)),sy=cy>=bottom?cy-3:cy+ch+3;
    svg.querySelector(':scope > path').setAttribute('d',r?`M${sx} ${sy} Q${sx} ${(sy+ty)/2} ${tx} ${ty}`:'');
  }
  function schedule(){if(!root.hidden&&!frame)frame=requestAnimationFrame(layout);}
  const observer=new ResizeObserver(schedule);
  function uiCompleted(step,hit){
    if(interfaceGuide)return !!definition(guideInfo()).complete?.(hit);
    if(['identity','arts_identity'].includes(step))return $('#player-details-dialog').open;
    if(['close_identity','close_arts'].includes(step))return !$('#player-details-dialog').open;
    if(['living','travel_tab'].includes(step))return $('#action-card').dataset.selectedCategory==='living';
    if(step==='library')return $('.technique-library').open;
    if(step==='handbook')return hit.parentNode.open;
    const panels={bag:'inventory',relationships:'relationship',faction:'faction',map:'map',settings:'settings',close_bag:'inventory',close_relationships:'relationship',close_faction:'faction',close_map:'map'};
    const panel=panels[step];return panel&&$(`#${panel}-card`).classList.contains('panel-open')!==step.startsWith('close_');
  }
  function draw(){
    if(duration){duration[0].textContent=duration[1];duration=null;}
    const enabled=data?!!data.tutorial.enabled:startEnabled;
    if(!working)$('#tutorial-enabled').checked=enabled;$('#tutorial-enabled').disabled=working||!!data?.tutorial.guide.completed;
    $('#tutorial-toggle-description').textContent=data?'暂停会保留操作进度、师承和宗门。':'开启后，下一个新角色将开始界面操作引导。';
    $('#tutorial-progress').textContent=data?`操作引导 · ${data.tutorial.guide.index+1}/${data.tutorial.guide.total}`:'跟着箭头，亲手问道';
    $('#tutorial-heading').textContent='新手操作教程';
    $('#tutorial-interface-start').disabled=!data||working;
    $('#tutorial-interface-start').textContent=interfaceGuide?'继续新版界面导览':'新版界面导览';
    $('#tutorial-start').textContent=data?.tutorial.guide.completed?'修行实践已完成':'开始／继续修行实践';
    $('#tutorial-status').textContent=!data?'进入一段人生后，即可开启新版界面导览。':interfaceGuide&&!interfaceGuide.active?'界面导览已暂停，点击上方入口可续接；刷新页面后可从头重看。':'';
    $('#tutorial-start').disabled=working||!!data?.tutorial.guide.completed;$('#tutorial-handbook-open').disabled=!data;
    document.querySelectorAll('[data-tutorial-open]').forEach(b=>{
      const status=data?(data.tutorial.guide.completed?'已完成':enabled?'引导中':'已暂停'):'跟随引导，亲手问道';
      b.querySelector('.tutorial-entry-status').textContent=status;
      b.setAttribute('aria-label',`新手教程：${status}`);
    });
    const g=guideInfo();if(!g?.active||dialog.open){stop();return;}
    const step=definition(g);if(!step){stop();return;}
    const key=data.id+':'+g.step,changed=currentKey!==key;
    if(changed&&!g.blocked){preparing=true;try{context(step);}finally{preparing=false;}}
    const targets=g.blocked?[]:visible(step.target);
    sectSelect.hidden=g.step!=='join'||!g.admissions.length;
    if(!sectSelect.hidden){if(!g.admissions.some(s=>s.id===selectedSect))selectedSect=g.admissions[0].id;
      sectSelect.replaceChildren(...g.admissions.map(s=>{const o=node('option',s.name);o.value=s.id;return o;}));sectSelect.value=selectedSect;
    }
    focus=targets.find(n=>g.step==='join'&&n.dataset.factionId===selectedSect)||targets[0]||null;
    const dialogs=[...document.querySelectorAll('dialog[open]')];
    const parent=focus?.closest('dialog[open]')||dialogs[dialogs.length-1]||document.body;
    if(root.parentNode!==parent)parent.append(root);
    root.hidden=false;currentKey=key;root.dataset.step=g.step;root.dataset.mode=interfaceGuide?'interface':'practice';
    interfaceShortcut.hidden=!!interfaceGuide||g.step!=='welcome';
    $('#guide-progress').textContent=`${g.index+1} / ${g.total} · ${interfaceGuide?'新版界面导览':'操作引导'}`;$('#guide-title').textContent=step.title;
    $('#guide-copy').textContent=g.blocked||(typeof step.text==='function'?step.text(g,data):step.text);
    const canNext=step.read||skippable(g);$('#guide-next').hidden=!canNext||!!g.blocked;$('#guide-next').disabled=working;
    $('#guide-next').textContent=g.step==='ui_finish'?'完成界面导览':g.step==='finish'?'完成引导，开始问道':'明白了，继续';$('#guide-pause').disabled=working;
    $('#guide-hint').textContent=working?'正在保存这一步…':g.blocked?'暂停后可处理眼前的事情。':!focus&&!canNext?'当前控件暂不可用，可暂停后处理当前状态，再续接引导。':canNext?'看清高亮的位置后，点继续。':'请亲自点击箭头指向的控件。';
    observer.disconnect();if(focus)observer.observe(focus);
    if(g.step==='practice'&&focus?.querySelector('.action-duration')){const label=focus.querySelector('.action-duration');duration=[label,label.textContent];label.textContent='教学演练 · 不耗岁月';}
    if(changed)coach.scrollTop=0;
    if(changed&&focus)focus.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});layout();
  }
  function open(){stop();if(!dialog.open)dialog.showModal();draw();}
  $('#tutorial-close').onclick=()=>{dialog.close();draw();};
  $('#tutorial-interface-start').onclick=startInterface;interfaceShortcut.onclick=startInterface;
  $('#tutorial-enabled').onchange=e=>{if(data){interfaceGuide=null;act(e.target.checked?'enable':'disable');}else{startEnabled=e.target.checked;try{localStorage.setItem('wendao-tutorial-next-life',String(startEnabled));}catch(_){}draw();}};
  $('#tutorial-start').onclick=async()=>{interfaceGuide=null;currentKey='';if(!data){startEnabled=true;try{localStorage.setItem('wendao-tutorial-next-life','true');}catch(_){}dialog.close();draw();return;}clearViews();if(!data.tutorial.enabled)await act('enable');draw();};
  $('#tutorial-handbook-open').onclick=async()=>{interfaceGuide=null;if(data?.tutorial.enabled)await act('disable');dialog.close();UtilityPanels.open('settings');$('#tutorial-handbook').scrollIntoView({block:'start'});draw();};
  $('#guide-pause').onclick=()=>act('disable');$('#guide-next').onclick=()=>act('guide_next');
  document.querySelectorAll('[data-tutorial-open]').forEach(b=>b.onclick=open);$('#setting-tutorial-open').onclick=open;
  document.addEventListener('click',event=>{
    if(preparing||root.hidden||root.contains(event.target))return;
    const g=guideInfo(),step=g&&definition(g);if(!g?.active||!step)return;
    const hit=visible(step.target).find(n=>n===event.target||n.contains(event.target));
    if(working||g.blocked||!hit){event.preventDefault();event.stopImmediatePropagation();return;}
    if(step.action||step.event||step.join){
      event.preventDefault();event.stopImmediatePropagation();if(skippable(g))return;
      if(step.event){const choice=event.target.closest('[data-guide-choice]');if(choice)act(choice.dataset.guideChoice);}
      else if(step.join)act('guide_join',{target_id:hit.dataset.factionId});
      else act(step.action,g.step==='equip'?{target_id:g.art.id}:{});
    }else if(step.click||step.input){
      if(g.step==='library'&&$('.technique-library').open)event.preventDefault();
      if(['handbook','ui_handbook'].includes(g.step)&&hit.parentNode.open)event.preventDefault();
      // Native WebView may run microtasks between capture and target listeners.
      // Wait for the entire click/default action before setting global busy state.
      setTimeout(()=>{if(guideInfo()?.step===g.step&&uiCompleted(g.step,hit))act('guide_next');},0);
    }else{event.preventDefault();event.stopImmediatePropagation();}
  },true);
  document.addEventListener('input',event=>{
    const g=guideInfo(),step=g&&definition(g);
    if(interfaceGuide&&g?.active&&!g.blocked&&step?.input&&event.target.matches(step.target)&&uiCompleted(g.step,event.target))act('guide_next');
  });
  document.addEventListener('keydown',e=>{if(root.hidden)return;if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();act('disable');}else if(e.key==='Tab'){
    const candidates=[...(focus?[focus,...focus.querySelectorAll('button,input,select,summary')]:[]),...coach.querySelectorAll('button')].filter(n=>!n.disabled&&!n.hidden&&(n.matches('button,input,select,summary')||n.tabIndex>=0));
    if(candidates.length){e.preventDefault();const index=candidates.indexOf(document.activeElement);candidates[(index+(e.shiftKey?-1:1)+candidates.length)%candidates.length].focus({preventScroll:true});}
  }},true);
  document.addEventListener('cancel',e=>{if(!root.hidden){e.preventDefault();act('disable');}},true);
  document.addEventListener('close',()=>{if(guideInfo()?.active&&!preparing)queueMicrotask(draw);},true);
  function reflow(){if(guideInfo()?.active&&!dialog.open){currentKey='';draw();}else schedule();}
  addEventListener('resize',()=>requestAnimationFrame(reflow));addEventListener('game:theme-change',()=>requestAnimationFrame(reflow));addEventListener('scroll',event=>{if(event.target!==coach)schedule();},true);
  window.TutorialGuide={enabledForNewGame:()=>startEnabled,reset(){interfaceGuide=null;data=null;send=null;stop();dialog.close();renderHandbook(handbookConfig);draw();},
    configure:renderHandbook,render(value,callback){if(data?.id!==value.id)interfaceGuide=null;data=value;send=callback;if(currentHandbookScope()!==handbookScope)renderHandbook(handbookConfig);draw();},open,isGuiding:()=>!root.hidden,pause:()=>act('disable'),
    showChapter(id){resetHandbookFilter();UtilityPanels.open('settings');const row=handbookRows.find(r=>r.chapter.id===id);if(row){row.element.open=true;row.expanded=true;row.element.scrollIntoView({block:'start'});}}
  };
  draw();
})();

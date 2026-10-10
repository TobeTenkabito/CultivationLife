/* One directory for the existing controls; preferences contain no game state. */
(() => {
  const groups = {
    common: {name:'常用', mark:'常', panels:['settings','extension','battle-report']},
    practice: {name:'修行', mark:'修', panels:['doctrine','immortal-conversion','immortal-veins','combat-plan','immortal-aperture','spirit-voisinage','asura-conversion','asura-body','asura-veins','asura-route','asura-domain','asura-powers','upper-voisinage','golden-light','immortal-body','voisinage','buddhist-wish','secret-art','transformation','bloodline','ghost-soul','sage-inner-outer']},
    craft: {name:'百艺', mark:'艺', panels:['inventory','spirit-field','puppet-workshop','captive','crafting','formation','talisman','natal-artifact','tianji']},
    economy: {name:'经营', mark:'营', panels:['personal-economy','market','merchant','auction','exchange','faction','intrigue','upper-institution','heavenly-court','war']},
    people: {name:'同道', mark:'缘', panels:['relationship','world-npc','ranking','family','race','buddhist','sage','ghost-attachment','ghost-parade','yaochi','daomen']},
    worlds: {name:'诸界', mark:'界', panels:['map','heavens','guixu','world-route']},
  };
  const defaults=['inventory','map','market','relationship','faction','personal-economy'];
  const entries=new Map(), tabs=[], shortcuts=[];
  let dialog, grid, common, search, heading, hint, category='common', bar, initialized=false;
  let pins=defaults, recent=[];
  let revision=0, saveQueue=Promise.resolve();
  try {
    const saved=JSON.parse(localStorage.getItem('wendao-navigation-v1'));
    if(Array.isArray(saved?.pins))pins=[...new Set(saved.pins.filter(x=>typeof x==='string'))].slice(0,8);
    if(Array.isArray(saved?.recent))recent=[...new Set(saved.recent.filter(x=>typeof x==='string'))].slice(0,4);
  } catch (_) {}
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;};
  const eligible=row=>!!row&&!row.button.classList.contains('hidden')&&!row.button.classList.contains('spatial-unavailable');
  const keywords={settings:'存档 百科 教程 主题 设置',inventory:'行囊 玉简 合参 背包',map:'地图 旅行 地点'};
  const title=row=>row.button.querySelector('small')?.textContent||row.button.title;
  function save(){
    revision++;
    const snapshot={pins:[...pins],recent:[...recent]};
    try{localStorage.setItem('wendao-navigation-v1',JSON.stringify(snapshot));}catch(_) {}
    saveQueue=saveQueue.catch(()=>{}).then(async()=>{
      const response=await fetch('/api/ui-preferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({navigation:snapshot})});
      if(!response.ok)throw new Error('Navigation preference save failed');
    }).catch(()=>{});
  }
  function remember(id){recent=[id,...recent.filter(x=>x!==id)].slice(0,4);save();}
  function close({restoreFocus=true}={}){
    if(!dialog?.open)return false;
    dialog.close();
    if(restoreFocus)bar.querySelector(`[data-navigation-category="${category}"]`)?.focus({preventScroll:true});
    return true;
  }
  function activate(id){
    const row=entries.get(id);if(!eligible(row)||row.button.disabled)return;
    close({restoreFocus:false});row.button.click();
  }
  function shortcut(id){
    const row=entries.get(id), b=el('button');b.type='button';b.dataset.navigationShortcut=id;
    b.className='navigation-shortcut';
    b.append(el('span',row.button.querySelector('span')?.textContent),el('small',title(row)));
    b.disabled=row.button.disabled;b.onclick=()=>activate(id);shortcuts.push({button:b,id});return b;
  }
  function renderCommon(){
    common.replaceChildren();shortcuts.length=0;
    const activities=[...entries].filter(([,row])=>eligible(row)&&row.button.dataset.activityState);
    if(activities.length){
      const section=el('section'),list=el('div',null,'navigation-shortcuts');section.id='navigation-current-events';
      section.append(el('h3','当前限时活动'));
      for(const [id,row] of activities){const b=shortcut(id);b.append(el('small',row.button.dataset.activityState));list.append(b);}
      section.append(list);common.append(section);
    }
    for(const [label,ids] of [['常用入口',pins],['最近打开',recent.filter(x=>!pins.includes(x))]]){
      const visible=ids.filter(id=>eligible(entries.get(id)));
      if(!visible.length)continue;
      const section=el('section'), list=el('div',null,'navigation-shortcuts');
      section.append(el('h3',label));visible.forEach(id=>list.append(shortcut(id)));section.append(list);common.append(section);
    }
    common.append(el('p','点功能旁的星标即可加入常用，最多八项。常用与最近记录保存在本机。','navigation-note'));
  }
  function filter(){
    const words=search.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    common.hidden=category!=='common'||words.length>0;
    heading.textContent=words.length?'查找功能':groups[category].name;
    let count=0;
    for(const [id,row] of entries){
      const available=eligible(row);
      row.wrapper.hidden=!available||(!words.length&&row.group!==category)||!words.every(w=>`${title(row)} ${row.button.title} ${groups[row.group].name} ${keywords[id]||''}`.toLocaleLowerCase().includes(w));
      row.pin.hidden=id==='battle-report';
      row.pin.setAttribute('aria-pressed',String(pins.includes(id)));
      row.pin.textContent=pins.includes(id)?'★':'☆';
      row.pin.setAttribute('aria-label',`${pins.includes(id)?'移出常用':'加入常用'}：${title(row)}`);
      if(!row.wrapper.hidden)count++;
    }
    tabs.forEach(b=>b.setAttribute('aria-selected',String(!words.length&&b.dataset.navigationTab===category)));
    hint.textContent=words.length?(count?`找到 ${count} 项功能`:'没有匹配的已开放功能，可换个关键词。'):'';
  }
  function refresh(){
    if(!initialized)return;
    for(const [id,row] of entries){
      row.button.classList.toggle('navigation-active',id!=='battle-report'&&document.getElementById(`${id}-card`)?.classList.contains('panel-open'));
    }
    for(const row of shortcuts){const source=entries.get(row.id);row.button.disabled=!eligible(source)||source.button.disabled;row.button.querySelector('small').textContent=title(source);}
    if(dialog.open){renderCommon();filter();}
    for(const button of bar.children){
      const key=button.dataset.navigationCategory;
      const notice=[...entries.values()].some(row=>row.group===key&&eligible(row)&&(row.button.classList.contains('notice')||row.button.classList.contains('merchant-notice')));
      button.classList.toggle('navigation-notice',notice);
      button.setAttribute('aria-expanded',String(dialog.open&&category===key));
    }
  }
  function open(key='common'){
    if(!initialized||!groups[key]||document.querySelector('#game-screen.hidden'))return;
    category=key;search.value='';renderCommon();filter();
    if(!dialog.open)dialog.showModal();refresh();
    dialog.querySelector(`[data-navigation-tab="${key}"]`)?.focus({preventScroll:true});
  }
  function reveal(id){const row=entries.get(id);if(eligible(row))open(row.group);}
  function init(){
    if(initialized)return;
    const original=[...document.querySelectorAll('.strategy-dock [data-panel-target],#battle-report-open')];
    dialog=el('dialog',null,'navigation-menu');dialog.id='navigation-menu';dialog.setAttribute('aria-labelledby','navigation-heading');
    const header=el('header',null,'navigation-heading'), copy=el('div');
    heading=el('h2','常用');heading.id='navigation-heading';copy.append(el('small','修行百事 · 按需展开'),heading);
    const dismiss=el('button','返回','navigation-dismiss');dismiss.type='button';dismiss.id='navigation-close';dismiss.onclick=()=>close();header.append(copy,dismiss);
    const categoryTabs=el('div',null,'navigation-tabs');categoryTabs.setAttribute('role','tablist');categoryTabs.setAttribute('aria-label','功能分类');
    bar=el('nav',null,'navigation-bar');bar.id='navigation-bar';bar.setAttribute('aria-label','游戏功能分类');
    for(const [key,group] of Object.entries(groups)){
      const b=el('button');b.type='button';b.dataset.navigationCategory=key;b.setAttribute('aria-haspopup','dialog');b.setAttribute('aria-controls','navigation-menu');
      b.append(el('span',group.mark),el('small',group.name));b.onclick=()=>open(key);bar.append(b);
      const tab=el('button',group.name);tab.type='button';tab.dataset.navigationTab=key;tab.setAttribute('role','tab');tab.onclick=()=>{category=key;search.value='';filter();refresh();};categoryTabs.append(tab);tabs.push(tab);
    }
    const label=el('label',null,'navigation-search');search=el('input');search.type='search';search.id='navigation-search';search.maxLength=80;search.placeholder='搜索功能，例如：灵域、坊市、存档';search.setAttribute('aria-label','搜索已开放功能');search.oninput=filter;label.append(search);
    const body=el('div',null,'navigation-body');common=el('div');grid=el('nav',null,'strategy-dock navigation-grid');grid.id='strategy-dock';grid.setAttribute('aria-label','已开放功能');hint=el('p',null,'navigation-note');hint.setAttribute('role','status');
    for(const button of original){
      const id=button.dataset.panelTarget||'battle-report';
      const group=Object.keys(groups).find(key=>groups[key].panels.includes(id));
      if(!group)throw new Error(`Navigation category missing: ${id}`);
      const wrapper=el('div',null,'navigation-entry'),pin=el('button');pin.type='button';pin.className='navigation-pin';pin.dataset.navigationPin=id;
      pin.onclick=()=>{if(pins.includes(id))pins=pins.filter(x=>x!==id);else if(pins.length<8)pins.push(id);else{hint.textContent='常用已有八项，请先取消一个星标。';return;}save();renderCommon();filter();};
      button.dataset.navigationGroup=group;button.addEventListener('click',()=>{remember(id);close({restoreFocus:false});});
      wrapper.append(button,pin);grid.append(wrapper);entries.set(id,{button,wrapper,pin,group});
    }
    document.querySelectorAll('.strategy-dock').forEach(n=>n.remove());
    body.append(common,grid,hint);dialog.append(header,categoryTabs,label,body);
    document.querySelector('#game-screen').append(bar,dialog);
    pins=pins.filter(id=>entries.has(id));recent=recent.filter(id=>entries.has(id));initialized=true;
    dialog.addEventListener('close',()=>{document.body.classList.remove('navigation-open');refresh();});
    dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)close();}});
    dialog.addEventListener('keydown',event=>{if(event.key==='ArrowRight'||event.key==='ArrowLeft'){
      const index=tabs.indexOf(document.activeElement);if(index<0)return;event.preventDefault();const next=tabs[(index+(event.key==='ArrowRight'?1:tabs.length-1))%tabs.length];next.click();next.focus();
    }});
    const observer=new MutationObserver(()=>document.body.classList.toggle('navigation-open',dialog.open));observer.observe(dialog,{attributes:true,attributeFilter:['open']});
    refresh();
  }
  const initialRevision=revision;
  const ready=fetch('/api/ui-preferences').then(r=>{if(!r.ok)throw new Error();return r.json();}).then(saved=>{
    if(revision!==initialRevision||!saved.navigation)return;
    pins=saved.navigation.pins;recent=saved.navigation.recent;
    if(initialized){pins=pins.filter(id=>entries.has(id));recent=recent.filter(id=>entries.has(id));refresh();}
  }).catch(()=>{});
  window.GameNavigation={init,open,close,reveal,refresh,ready,get saved(){return saveQueue;},isOpen:()=>!!dialog?.open};
})();

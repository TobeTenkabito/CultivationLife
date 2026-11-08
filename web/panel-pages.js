/* Parallel subpages reuse original nodes and handlers; UI state stays outside saves. */
(() => {
  const selected=new Map(), pages=new Map();let identity;let mounted=new WeakMap();let pagers=new WeakMap();
  const q=s=>document.querySelector(s), children=n=>[...(n?.children||[])].filter(n=>!n.matches('.panel-page-tabs,.list-pagination'));
  const title=n=>n.querySelector(':scope > summary,:scope > h3,:scope > h4,:scope > .market-stock-heading h3')?.textContent?.split(' · ')[0]?.trim();
  function mount(id,host,groups){
    if(!host)return;
    groups=groups.map(([name,nodes])=>[name,nodes.filter(n=>n&&!n.classList.contains('hidden')&&!n.hidden)]).filter(([,ns])=>ns.length);
    const cached=mounted.get(host);
    if(cached&&cached.id===id&&cached.groups.length===groups.length&&groups.every(([name,ns],i)=>name===cached.groups[i][0]&&ns.length===cached.groups[i][1].length&&ns.every((n,j)=>n===cached.groups[i][1][j])))return;
    mounted.set(host,{id,groups});
    host.querySelector(':scope > .panel-page-tabs')?.remove();
    if(!groups.length)return;
    let active=selected.get(id);if(!groups.some(([name])=>name===active))active=groups[0][0];selected.set(id,active);
    const nav=document.createElement('nav');nav.className='panel-page-tabs';nav.setAttribute('aria-label',host.closest('[aria-label]')?.getAttribute('aria-label')+'子页');nav.setAttribute('role','tablist');
    const choose=(name,focus=false)=>{selected.set(id,name);groups.forEach(([key,ns],i)=>{const on=key===name;ns.forEach(n=>{n.dataset.pageName=key;n.toggleAttribute('data-page-hidden',!on);n.setAttribute('role','tabpanel');if(n.tagName==='DETAILS')n.open=on;});const b=nav.children[i];b.setAttribute('aria-selected',String(on));b.tabIndex=on?0:-1;if(on&&focus)b.focus();});window.dispatchEvent(new CustomEvent('game:subpage-open',{detail:{id,name}}));};
    groups.forEach(([name,nodes],i)=>{const b=document.createElement('button');b.type='button';b.textContent=name;b.dataset.subpage=name;window.DlcControls?.page(b,nodes);b.setAttribute('role','tab');b.onclick=()=>choose(name);b.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const j=e.key==='Home'?0:e.key==='End'?groups.length-1:(i+(e.key==='ArrowLeft'?-1:1)+groups.length)%groups.length;choose(groups[j][0],true);}};nav.append(b);});
    const heading=host.querySelector(':scope > .section-title');if(heading)heading.after(nav);else host.prepend(nav);choose(active);
  }
  function auto(id,host,nodes,names={}){const grouped=new Map();for(const n of nodes){const name=names[n.id]||title(n)||'概览';if(!grouped.has(name))grouped.set(name,[]);grouped.get(name).push(n);}mount(id,host,[...grouped]);}
  // Keep the actual rows/handlers and current authoritative quotes. Paging is read-only.
  function paginate(list,options={}){
    if(!list)return;
    let {key=list.id,label='条目',size,reset=false,items,activeIndex}=options;
    const rows=[...list.children].filter(n=>(!items||n.matches(items))&&!n.matches('.empty,.muted,.list-pagination')&&!n.hidden&&!n.classList.contains('hidden'));
    size=(typeof size==='function'?size():size)|| (innerHeight<550?1:innerWidth<=600?2:4);
    let pager=pagers.get(list);
    if(!pager){
      const nav=document.createElement('nav');nav.className='list-pagination';nav.setAttribute('aria-label',`${label}分页`);
      const prev=document.createElement('button'),next=document.createElement('button'),status=document.createElement('span');
      prev.type=next.type='button';prev.textContent='上一页';next.textContent='下一页';
      status.setAttribute('role','status');status.setAttribute('aria-live','polite');
      nav.append(prev,status,next);pager={nav,prev,next,status,page:pages.get(key)||0,key};pagers.set(list,pager);
    }
    pager.options=options;
    if(items){if(pager.nav.parentElement!==list){const heading=list.querySelector(':scope>h3');if(heading)heading.after(pager.nav);else list.prepend(pager.nav);}}
    else if(pager.nav.nextElementSibling!==list)list.before(pager.nav);
    if(pager.key!==key){pager.page=pages.get(key)||0;pager.key=key;}
    if(reset)pager.page=0;
    if(Number.isInteger(activeIndex)&&activeIndex>=0)pager.page=Math.floor(activeIndex/size);
    const total=Math.max(1,Math.ceil(rows.length/size));pager.page=Math.min(pager.page,total-1);
    function show(page){
      pager.page=page;if(key)pages.set(key,page);
      rows.forEach((n,i)=>{n.toggleAttribute('data-list-page-hidden',Math.floor(i/size)!==page);n.dataset.listPage=String(Math.floor(i/size));});
      pager.status.textContent=`${page+1} / ${total} 页 · 共 ${rows.length} 项`;
      pager.prev.disabled=page===0;pager.next.disabled=page===total-1;
      pager.nav.hidden=rows.length<=size;
    }
    pager.prev.onclick=()=>show(Math.max(0,pager.page-1));pager.next.onclick=()=>show(Math.min(total-1,pager.page+1));
    list.classList.add('paginated-list');show(pager.page);
  }
  function refreshLists(){
    const ids=['market-offers','training-market-offers','material-market-offers','puppet-market-offers','talisman-market-offers',
      'market-plant-sellables','market-talisman-sellables','formation-material-library','formation-ground-list','formation-loadout-list',
      'crafting-material-library','crafting-blueprint-list','captive-list','puppet-list','foreign-soul-list','ranking-list','world-npc-list',
      'faction-roster-list','concubine-list','dao-companion-list','dao-friend-list','party-list','high-affinity-list','low-affinity-list',
      'transformation-materials','transformation-stored','transformation-known','ghost-attachment-list','ghost-parade-list',
      'war-list','auction-lots','auction-attendees','auction-sellables','black-market-offers','known-technique-list','technique-list','battle-round-list','save-list','tianji-ranking'];
    for(const id of ids){const list=q('#'+id);if(list)paginate(list,{label:list.closest('section,article,details')?.querySelector('h3,h2,summary')?.textContent?.trim()||'条目'});}
    document.querySelectorAll('.inventory-category').forEach(list=>paginate(list,{key:'inventory:'+title(list),items:'.item',label:title(list)}));
    document.querySelectorAll('.mentorship-roster,.merchant-task-list').forEach((list,i)=>paginate(list,{key:list.closest('[id]')?.id+':'+list.className+':'+i}));
    document.querySelectorAll('#family-content section').forEach((list,i)=>{if(list.querySelector(':scope>.family-member,:scope>.family-other'))paginate(list,{key:'family:'+title(list)+i,items:'.family-member,.family-other',label:title(list)});});
  }
  function refresh(saveId){
    if(saveId&&identity!==saveId){identity=saveId;selected.clear();pages.clear();mounted=new WeakMap();document.querySelectorAll('.list-pagination').forEach(n=>n.remove());pagers=new WeakMap();}
    const faction=q('#faction-content');if(faction){const summary=q('#faction-summary');auto('faction',faction,[...children(summary),...children(faction).filter(n=>n!==summary)],{'faction-description':'概览','sect-task-board':'任务','faction-dispatch':'差遣','faction-rewards':'岁禄','faction-roster':'门人','faction-diplomacy-detail':'外交'});}
    const family=q('#family-content');if(family)auto('family',family,children(family).flatMap(n=>n.matches('.family-management')?children(n):[n]));
    const rel=q('#relationship-card');if(rel)auto('relationship',rel,children(rel).filter(n=>!n.matches('.section-title')),{'npc-contacts':'故人笺'});
    for(const id of ['transformation','captive']){const host=q('#'+id+'-card');if(host)auto(id,host,children(host).filter(n=>!n.matches('.section-title')),{'transformation-note':'本相','transformation-combined':'本相'});}
    const market=q('#market-content');if(market)auto('market-shelves',market,children(market).filter(n=>n.matches('section')),{'immortal-market-content':'上界坊市'});
    for(const id of ['formation','crafting']){const host=q('#'+id+'-card');if(host)auto(id,host,children(host).filter(n=>n.matches('section,.formation-layout')),{'formation-layout':'布阵推演'});}
    const bag=q('#inventory-list');if(bag)auto('inventory',bag,children(bag));
    const merchant=q('#merchant-card');if(merchant){const network=q('#fleet-network-content'),content=q('#merchant-content');auto('merchant',merchant,[content,...children(network)],{'merchant-content':'商盟与委托'});
      const alliances=children(content).filter(n=>n.matches('.merchant-alliance'));const rest=children(content).filter(n=>!n.matches('.merchant-alliance,.merchant-membership'));
      mount('merchant-alliances',content,[...alliances.map(n=>[title(n)||'商盟',[n]]),['往来记录',rest]]);}
    refreshLists();
  }
  window.PanelPages={refresh,mount,paginate,refreshLists};
  window.addEventListener('game:panel-open',()=>refresh());
  window.addEventListener('resize',()=>document.querySelectorAll('.paginated-list').forEach(list=>{const pager=pagers.get(list);if(pager)paginate(list,{...pager.options,reset:false});}));
  window.addEventListener('game:subpage-open',({detail})=>{if(detail.id==='formation'&&detail.name==='布阵推演')window.dispatchEvent(new Event('resize'));});
})();

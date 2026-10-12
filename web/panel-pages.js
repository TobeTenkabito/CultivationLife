/* Parallel subpages reuse original nodes and handlers; UI state stays outside saves. */
(() => {
  const selected=new Map();let identity;let mounted=new WeakMap();
  const q=s=>document.querySelector(s), children=n=>[...(n?.children||[])].filter(n=>!n.matches('.panel-page-tabs'));
  const title=n=>n.querySelector(':scope > summary,:scope > h3,:scope > h4')?.textContent?.split(' · ')[0]?.trim();
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
    const choose=(name,focus=false)=>{selected.set(id,name);groups.forEach(([key,ns],i)=>{const on=key===name;ns.forEach(n=>{n.dataset.pageName=key;n.toggleAttribute('data-page-hidden',!on);n.setAttribute('role','tabpanel');if(n.tagName==='DETAILS')n.open=on;});const b=nav.children[i];b.setAttribute('aria-selected',String(on));b.tabIndex=on?0:-1;if(on&&focus)b.focus();});};
    groups.forEach(([name],i)=>{const b=document.createElement('button');b.type='button';b.textContent=name;b.dataset.subpage=name;b.setAttribute('role','tab');b.onclick=()=>choose(name);b.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const j=e.key==='Home'?0:e.key==='End'?groups.length-1:(i+(e.key==='ArrowLeft'?-1:1)+groups.length)%groups.length;choose(groups[j][0],true);}};nav.append(b);});
    const heading=host.querySelector(':scope > .section-title');if(heading)heading.after(nav);else host.prepend(nav);choose(active);
  }
  function auto(id,host,nodes,names={}){const grouped=new Map();for(const n of nodes){const name=names[n.id]||title(n)||'概览';if(!grouped.has(name))grouped.set(name,[]);grouped.get(name).push(n);}mount(id,host,[...grouped]);}
  function refresh(saveId){
    if(saveId&&identity!==saveId){identity=saveId;selected.clear();mounted=new WeakMap();}
    const faction=q('#faction-content');if(faction){const summary=q('#faction-summary');auto('faction',faction,[...children(summary),...children(faction).filter(n=>n!==summary)],{'faction-description':'概览','faction-dispatch':'差遣','faction-rewards':'岁禄','faction-roster':'门人','faction-diplomacy-detail':'外交'});}
    const family=q('#family-content');if(family)auto('family',family,children(family).flatMap(n=>n.matches('.family-management')?children(n):[n]));
    const rel=q('#relationship-card');if(rel)auto('relationship',rel,children(rel).filter(n=>!n.matches('.section-title')),{'npc-contacts':'故人笺'});
    for(const id of ['transformation','captive']){const host=q('#'+id+'-card');if(host)auto(id,host,children(host).filter(n=>!n.matches('.section-title')),{'transformation-note':'本相','transformation-combined':'本相'});}
    const bag=q('#inventory-list');if(bag)auto('inventory',bag,children(bag));
    const merchant=q('#merchant-card');if(merchant){const network=q('#fleet-network-content'),content=q('#merchant-content');auto('merchant',merchant,[content,...children(network)],{'merchant-content':'商盟与委托'});
      const alliances=children(content).filter(n=>n.matches('.merchant-alliance'));const rest=children(content).filter(n=>!n.matches('.merchant-alliance,.merchant-membership'));
      mount('merchant-alliances',content,[...alliances.map(n=>[title(n)||'商盟',[n]]),['往来记录',rest]]);}
  }
  window.PanelPages={refresh,mount};
  window.addEventListener('game:panel-open',()=>refresh());
})();

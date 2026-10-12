/* Selecting the authoritative road graph never moves the player. */
(() => {
  const layouts=new Map();let selected=null,world=null,gameId=null,faction='',zoom=1,view='influence',display='map',lastRender=null,lockRule=()=>true;
  let scene=null,sceneMode='3d';const cameras=new Map();
  const camera=()=>{if(!cameras.has(world))cameras.set(world,{yaw:-.2,pitch:.64,zoom:1});return cameras.get(world);};
  const el=(tag,text,cls='')=>{const n=document.createElement(tag);n.className=cls;if(text!=null)n.textContent=text;return n;};
  const svg=(tag,a={})=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(a).forEach(([k,v])=>n.setAttribute(k,v));return n;};
  let factionColors=new Map();
  const palette=['#387C92','#BF6338','#7861AC','#4D8550','#B54976','#9C852B','#3563B0','#A44135','#407F77','#865632','#AD57A0','#607539'];
  const color=id=>factionColors.get(id)||'#698080';
  const roadKey=(a,b)=>[a,b].sort().join(':');
  const button=(text,action,cls='')=>{const b=el('button',text,cls);b.type='button';b.onclick=action;return b;};
  function open(next='influence',location=null){
    if(!lastRender)return;
    view=['influence','decisions'].includes(next)?next:'influence';
    if(location&&lastRender[0].locations.some(r=>r.id===location))selected=location;
    render(...lastRender);
  }
  function authority(t){
    if(!t?.enabled)return '尚未启用“明争暗斗：合纵连横”。可在扩展设置中启用，按设置提示生效后查看地方影响。';
    if(!t.owner_id)return '你尚未加入本界的宗门。可以查看各宗地方影响；加入宗门并取得决策权后，才能提出地方议案。';
    if(!t.can_propose)return '你在本门暂无决策权，仍可查看地方形势与政策。取得本门议事资格后，才能提出地方议案。';
    return '你可提出本门地方议案，须经有权成员多数表决通过；费用与资材由本门府库承担。';
  }
  function bands(host){
    const box=el('div',null,'atlas-bands');box.setAttribute('aria-label','影响力层级');
    [['中枢','90–100'],['核心','70–90'],['战略','50–70'],['边缘','30–50'],['缓冲','0–30']].forEach(([name,range])=>{const badge=el('div');badge.append(el('strong',name),el('small',range));box.append(badge);});host.append(box);
  }
  function regionList(host,map,choose){
    const list=el('div',null,'atlas-region-list');
    const places=map.locations.filter(p=>!faction||(p.influences||[]).some(r=>r.id===faction));
    for(const p of places){const card=el('article',null,`atlas-region${p.id===selected?' selected':''}`);card.append(button(`${p.name}${p.current?' · 当前':''}`,()=>choose(p.id),'atlas-region-name'));
      for(const r of p.influences||[]){const row=el('div',null,'atlas-region-meter');row.style.setProperty('--sect-color',color(r.id));const meter=el('progress');meter.max=100;meter.value=r.value;meter.setAttribute('aria-label',`${p.name} · ${r.name}影响力 ${r.value}`);row.append(el('span',`${r.name}${r.owned?' · 本门':''}`),el('strong',`${r.value} · ${r.band}`),meter);card.append(row);}
      if(!(p.influences||[]).length)card.append(el('small',p.min_realm_index?'境界禁地 · 禁止新扩张':'暂无宗门影响','muted'));list.append(card);
    }if(!places.length)list.append(el('p','本界暂无该宗门的地方影响。','muted'));host.append(list);
  }
  function layout(map){
    const key=map.world+':'+map.locations.map(n=>n.id).join(',')+':'+(map.roads||[]).map(r=>roadKey(r.from,r.to)).sort().join(',');
    if(layouts.has(key))return layouts.get(key);
    const preset=window.MapLayouts?.[map.world], nodes=new Map();
    map.locations.forEach((n,i)=>{const p=preset?.points[n.id]||[80+(i%6)*160,80+Math.floor(i/6)*125];nodes.set(n.id,{id:n.id,x:p[0],y:p[1]});});
    const roads=new Set((preset?.roads||[]).map(([a,b])=>roadKey(a,b)));
    const links=(map.roads||[]).filter(r=>!roads.has(roadKey(r.from,r.to)));
    const result={nodes,roads,links};if(layouts.size>=24)layouts.delete(layouts.keys().next().value);layouts.set(key,result);return result;
  }
  function render(map,state,send,locked){
    const host=document.querySelector('#map-atlas');if(!host)return;const previousScroll=host.querySelector('.atlas-viewport');const savedScroll=previousScroll?[previousScroll.scrollLeft,previousScroll.scrollTop]:[0,0];scene?.dispose();scene=null;lastRender=[map,state,send,locked];lockRule=locked;if(world!==map.world||gameId!==state.id){if(gameId!==state.id)cameras.clear();world=map.world;gameId=state.id;selected=map.current;faction='';zoom=1;view='influence';display='map';}if(!map.locations.some(n=>n.id===selected))selected=map.current;
    const ids=[...new Set(map.locations.flatMap(n=>(n.influences||[]).map(r=>r.id)))].sort();
    factionColors=new Map(ids.map((id,i)=>[id,i<palette.length?palette[i]:`hsl(${(i*137.508)%360} 62% ${40+Math.floor(i/palette.length)%3*10}%)`]));
    host.replaceChildren();host.classList.add('map-atlas');const places=new Map(map.locations.map(n=>[n.id,n])),topology=layout(map),points=topology.nodes,bar=el('div',null,'atlas-toolbar');bar.append(el('strong',map.territory?'山川形势 · 宗门影响':'山川形势'));
    const select=el('select');select.setAttribute('aria-label','地图地点');map.locations.forEach(n=>{const o=el('option',n.name);o.value=n.id;select.append(o);});select.value=selected;select.onchange=()=>{selected=select.value;render(map,state,send,locked);};bar.append(select);
    if(map.territory?.enabled){const filter=el('select');filter.setAttribute('aria-label','影响力宗门');const all=el('option','各方影响');all.value='';filter.append(all);const factions=new Map(map.locations.flatMap(n=>(n.influences||[]).map(r=>[r.id,r.name])));factions.forEach((name,id)=>{const o=el('option',name);o.value=id;filter.append(o);});filter.value=faction;filter.onchange=()=>{faction=filter.value;render(map,state,send,locked);};bar.append(filter);}
    if(view==='influence'&&display==='map')[['−',()=>{if(sceneMode==='3d'){camera().zoom=Math.max(.65,camera().zoom-.2);}else zoom=Math.max(1,zoom-.5);}],['＋',()=>{if(sceneMode==='3d'){camera().zoom=Math.min(2.4,camera().zoom+.2);}else zoom=Math.min(3,zoom+.5);}]].forEach(([name,act])=>{const b=button(name,()=>{act();render(map,state,send,locked);});b.setAttribute('aria-label',name==='＋'?'放大地图':'缩小地图');bar.append(b);});host.append(bar);
    if(map.territory){const nav=el('nav',null,'atlas-view-tabs');nav.setAttribute('aria-label','地方影响功能');for(const [id,name] of [['influence','势力分布'],['decisions','政策与决议']]){const b=button(name,()=>open(id));b.dataset.atlasView=id;b.setAttribute('aria-pressed',String(view===id));nav.append(b);}host.append(nav);
      if(!map.territory.enabled)host.append(el('p',authority(map.territory),'atlas-access'));
    }
    const choose=id=>{selected=id;render(map,state,send,locked);};
    if(view==='influence'){
    if(map.territory?.enabled){const modes=el('div',null,'atlas-display-tabs');for(const [id,name] of [['map','地图'],['list','地区列表']]){const b=button(name,()=>{display=id;render(map,state,send,locked);});b.dataset.atlasDisplay=id;b.setAttribute('aria-pressed',String(display===id));modes.append(b);}host.append(modes);}
    if(display==='list'&&map.territory?.enabled)regionList(host,map,choose);else{
    const modeBar=el('div',null,'atlas-display-tabs');modeBar.setAttribute('aria-label','地图投影');for(const [id,name]of [['3d','立体地图'],['flat','平面地图']]){const b=button(name,()=>{sceneMode=id;render(map,state,send,locked);});b.dataset.atlasMode=id;b.setAttribute('aria-pressed',String(sceneMode===id));modeBar.append(b);}host.append(modeBar);
    if(sceneMode==='3d'&&window.MapScene?.supports(map)){
      const viewport=el('div',null,'atlas-viewport');host.append(viewport);scene=MapScene.mount(viewport,map,{selected,faction,color,camera:camera(),onSelect:choose});
      const controls=el('div',null,'atlas-scene-controls');for(const [name,action,label]of [['↶',()=>scene?.rotate(-.16),'向左旋转地图'],['↷',()=>scene?.rotate(.16),'向右旋转地图'],['复位',()=>scene?.reset(),'复位地图视角'],['定位当前',()=>scene?.locate(),'定位当前地域']]){const b=button(name,action);b.setAttribute('aria-label',label);controls.append(b);}controls.append(el('small','拖动空白处转动视角，点选地域查看行程。','muted'));host.append(controls);
      viewport.scrollLeft=savedScroll[0];viewport.scrollTop=savedScroll[1];
    }else{
    const viewport=el('div',null,'atlas-viewport'),drawing=svg('svg',{viewBox:'0 0 1000 710',role:'group','aria-label':`${map.world_name}道路与势力图`});drawing.style.width=`${zoom*100}%`;drawing.style.minWidth=zoom>1?'600px':'';drawing.append(svg('path',{d:'M0 630 Q180 430 330 630 T650 650 T1000 600 V710 H0Z',class:'atlas-mountains'}));
    for(const edge of map.roads||[]){const a=points.get(edge.from),b=points.get(edge.to);if(a&&b&&topology.roads.has(roadKey(edge.from,edge.to)))drawing.append(svg('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,class:'atlas-road'}));}
    for(const place of map.locations){const p=points.get(place.id),influences=(place.influences||[]).filter(r=>!faction||r.id===faction),description=influences.map(r=>`${r.name} ${r.value}，${r.band}`).join('；'),g=svg('g',{transform:`translate(${p.x},${p.y})`,class:`atlas-node${place.current?' current':''}${place.id===selected?' selected':''}`,role:'button',tabindex:'0','aria-label':`${place.name}${place.current?'，当前位置':''}${place.min_realm_index?'，有境界门槛':''}${description?'，'+description:''}`,'data-atlas-location':place.id});const title=svg('title');title.textContent=`${place.name}${description?'：'+description:''}`;g.append(title);if(influences.length)g.append(svg('circle',{r:41,fill:color(influences[0].id),'fill-opacity':.08+influences[0].value/500,stroke:'none'}));influences.slice(0,3).forEach((r,i)=>g.append(svg('circle',{r:25+i*7,fill:'none',stroke:color(r.id),'stroke-width':6,'stroke-opacity':.35+r.value/160})));g.append(svg('circle',{r:13,class:'atlas-dot'}));const icon=svg('text',{y:5,'text-anchor':'middle',class:'atlas-seal'});icon.textContent=place.current?'你':place.min_realm_index?'禁':(place.factions||[]).length?'府':(place.wars||[]).length?'战':'·';g.append(icon);const label=svg('text',{y:55,'text-anchor':'middle',class:'atlas-label'});label.textContent=place.name;g.append(label);if(influences.length){const value=svg('text',{y:73,'text-anchor':'middle',class:'atlas-value'});const r=influences.find(r=>r.owned)||influences[0];value.textContent=`${r.owned?'本门 ':''}${r.value}`;g.append(value);}g.onclick=()=>choose(place.id);g.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();choose(place.id);}};drawing.append(g);}
    viewport.append(drawing);host.append(viewport);
    if(topology.links.length){const links=el('div',null,'atlas-road-links'),markers=new Map();links.append(el('small','同号路标相连'));topology.links.forEach((edge,i)=>{const a=places.get(edge.from),b=places.get(edge.to);if(!a||!b)return;links.append(button(`〔${i+1}〕${a.name} ↔ ${b.name}`,()=>choose(selected===a.id?b.id:a.id)));for(const id of [a.id,b.id]){if(!markers.has(id))markers.set(id,[]);markers.get(id).push(i+1);}});for(const [id,numbers] of markers){const p=points.get(id),badge=svg('text',{x:p.x,y:p.y-26,'text-anchor':'middle',class:'atlas-route-number'});badge.textContent=`〔${numbers.join('·')}〕`;drawing.append(badge);}host.append(links);}
    }
    if(map.territory?.enabled)bands(host);
    }
    if(map.territory?.enabled){const legend=el('div',null,'atlas-factions');legend.setAttribute('aria-label','宗门颜色图例');const factions=new Map(map.locations.flatMap(n=>(n.influences||[]).map(r=>[r.id,r.name])));factions.forEach((name,id)=>{const b=button(name,()=>{faction=faction===id?'':id;render(map,state,send,locked);});b.style.setProperty('--sect-color',color(id));b.setAttribute('aria-pressed',String(faction===id));legend.append(b);});host.append(legend);}
    }
    const place=places.get(selected),detail=el('section',null,'atlas-detail');detail.dataset.selectedLocation=selected;const heading=el('div',null,'atlas-place-heading');heading.append(el('h3',place.name),el('span',place.current?'当前所在':`行程 ${place.travel_years} 年`));detail.append(heading,el('p',place.description||'山川之间，商旅往来。','muted'));
    const travel=el('button',place.current?'已在此地':'查看行程并前往');travel.type='button';travel.dataset.atlasUnavailable=place.current||place.travel_status!=='ok'?'1':'0';travel.disabled=place.current||locked()||place.travel_status!=='ok';travel.onclick=()=>document.querySelector(`#map-locations .map-travel[data-destination="${CSS.escape(place.id)}"]`)?.click();detail.append(travel);
    for(const r of place.influences||[]){const row=el('div',null,'atlas-influence');row.style.setProperty('--sect-color',color(r.id));const meter=el('progress');meter.max=100;meter.value=r.value;meter.setAttribute('aria-label',`${r.name}影响力 ${r.value}`);row.append(el('strong',`${r.name}${r.owned?' · 本门':''}`),el('span',`${r.value} · ${r.band}`),meter,el('small',`当地占比 ${r.share}% · ${r.headquarters?'驻地':r.outpost?'据点':'地方经营'} · ${r.policy_name}`));detail.append(row);}
    if(map.territory?.enabled&&!(place.influences||[]).length)detail.append(el('p','尚无宗门在此经营地方影响。','muted'));
    if(map.territory&&view==='decisions'){detail.append(el('p',authority(map.territory),'atlas-access'));if(map.territory.enabled&&map.territory.owner_id)decisions(detail,map,place,send,locked);else{const b=button('提议地方决议',()=>{});b.disabled=true;detail.append(b);}}
    host.append(detail);if(view==='decisions'||!map.territory)relocations(host,map,send,locked);
  }
  function decisions(host,map,place,send,locked){
    const t=map.territory,plan=t.locations.find(r=>r.id===place.id),box=el('details',null,'atlas-decisions');box.open=true;box.append(el('summary','地方议事与经营'),el('p',`最近${t.period_years || 0}年地方经营收入 ${Math.round(t.income).toLocaleString()} 灵石；维护实付 ${Math.round(t.upkeep_paid).toLocaleString()} / 应付 ${Math.round(t.upkeep_due).toLocaleString()}。行动劳务 ${t.action_fee.toLocaleString()} 灵石，由府库支付。`,'muted'));box.append(el('p','直接投放会令当地他宗关系下降；论道无论胜负都会增进两宗关系。边界袭扰不占经营名额，但会恶化关系。','muted'));const controls=el('div',null,'atlas-actions');
    const act=(text,action,extra={},disabled=false)=>{const b=el('button',text);b.type='button';const unavailable=disabled||!t.can_propose;b.dataset.atlasUnavailable=unavailable?'1':'0';b.disabled=locked()||unavailable;b.dataset.organizationAction=action;b.onclick=()=>send({kind:'sect',owner_id:t.owner_id,location_id:place.id,action,...extra});controls.append(b);return b;};
    if(plan){
      act('议决投放 · 影响 +20','expand_influence',{},plan.value>=100);
      if(plan.can_build&&plan.construction){
        const cost=plan.construction;box.append(el('p',`新建据点：施工与补购预计 ${cost.total.toLocaleString()} 灵石；${cost.materials.map(r=>`${r.name} ×${r.quantity}`).join('、')}。据点保底 50。`));
        if(!cost.can_build)box.append(el('p',cost.stock_available?'府库灵石不足以支付施工与补购。':'当地资材不足，请先补充资材。','muted'));
        act('议决新建据点','build_outpost',{},!cost.can_build);
      }else if(!plan.outpost){
        act('议决新建据点','build_outpost',{},true);box.append(el('p','新建据点需要亲赴所选地域，使用当地资材。','muted'));
      }
      if(plan.policies.length){
        const select=el('select');select.setAttribute('aria-label','地方政策');plan.policies.forEach(r=>{const o=el('option',r.name);o.value=r.id;select.append(o);});
        const current=(place.influences||[]).find(r=>r.id===t.owner_id)?.policy;if(plan.policies.some(r=>r.id===current))select.value=current;
        controls.append(select);const b=act('议决地方政策','territory_policy');b.onclick=()=>send({kind:'sect',owner_id:t.owner_id,location_id:place.id,action:'territory_policy',policy:select.value});
      }else box.append(el('p','本门尚未在此经营影响，先投放或建据点，才能选择地方政策。','muted'));
    }
    else box.append(el('p',place.min_realm_index?'此地有境界门槛，禁止扩张和建据点。':'须与己方已有影响力地点相邻；无驻地地区至多容纳三个宗门。','muted'));
    const rivals=(place.influences||[]).filter(r=>r.id!==t.owner_id);if(rivals.length){const select=el('select');select.setAttribute('aria-label','地方交涉宗门');rivals.forEach(r=>{const o=el('option',r.name);o.value=r.id;select.append(o);});controls.append(select);for(const [text,action] of [['议决论道比试','territory_spar'],['议决边界袭扰','territory_harass'],['宣战 · 移除当地影响','territory_war']]){const b=act(text,action,{},action==='territory_harass'?!t.harassment_locations.includes(place.id):action==='territory_spar'&&!plan);b.onclick=()=>send({kind:'sect',owner_id:t.owner_id,location_id:place.id,action,rival_id:select.value,goal:'remove_influence'});}const b=act('宣战 · 捣毁据点','territory_war',{},!rivals.some(r=>r.outpost));b.onclick=()=>send({kind:'sect',owner_id:t.owner_id,location_id:place.id,action:'territory_war',rival_id:select.value,goal:'destroy_outpost'});}box.append(controls);host.append(box);
  }
  function relocations(host,map,send,locked){
    if(!map.organization_relocation?.length)return;const box=el('details',null,'atlas-relocations');box.append(el('summary','驻地迁移议事'),el('p','迁址须经有权成员多数表决，只能迁入本界无境界门槛的地域。门人按实际状态迁居；产业、库存和传送阵留在原地。你仍留在当前地图。','muted'));
    for(const plan of map.organization_relocation){const form=el('form',null,'atlas-relocation-form');form.append(el('strong',plan.name));const select=el('select');select.setAttribute('aria-label',`${plan.name}迁址目标`);plan.destinations.forEach(r=>{const o=el('option',r.name);o.value=r.id;select.append(o);});const b=el('button','提议迁址');b.type='submit';b.dataset.atlasUnavailable=!plan.can_propose||!plan.destinations.length?'1':'0';b.disabled=locked()||!plan.can_propose||!plan.destinations.length;b.dataset.organizationAction='relocate';form.append(select,b);form.onsubmit=e=>{e.preventDefault();send({action:'relocate',kind:plan.kind,owner_id:plan.id,location_id:select.value});};box.append(form);}host.append(box);
  }
  function syncBusy(){document.querySelectorAll('#map-atlas [data-atlas-unavailable]').forEach(b=>b.disabled=lockRule()||b.dataset.atlasUnavailable==='1');}
  window.MapAtlas={render,syncBusy,open,pauseScene:()=>scene?.pause()};
})();

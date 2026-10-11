/* Selecting the authoritative road graph never moves the player. */
(() => {
  const layouts=new Map();let selected=null,world=null,gameId=null,faction='',zoom=1,view='influence',display='map',lastRender=null,lockRule=()=>true;
  const el=(tag,text,cls='')=>{const n=document.createElement(tag);n.className=cls;if(text!=null)n.textContent=text;return n;};
  const svg=(tag,a={})=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(a).forEach(([k,v])=>n.setAttribute(k,v));return n;};
  const colors=['#477e81','#ad7650','#78719a','#649063','#b26b78','#8c854e','#547caa'];
  const color=id=>{let n=0;for(const c of id)n=(n*31+c.charCodeAt(0))>>>0;return colors[n%colors.length];};
  const button=(text,action,cls='')=>{const b=el('button',text,cls);b.type='button';b.onclick=action;return b;};
  function open(next='influence',location=null){
    if(!lastRender)return;
    view=['influence','decisions','guide'].includes(next)?next:'influence';
    if(location&&lastRender[0].locations.some(r=>r.id===location))selected=location;
    render(...lastRender);
  }
  function authority(t){
    if(!t?.enabled)return '尚未启用“明争暗斗：合纵连横”。可在扩展设置中启用，按设置提示生效后查看地方影响。';
    if(!t.owner_id)return '你尚未加入本界的宗门。可以查看各宗地方影响；加入宗门并取得决策权后，才能提出地方议案。';
    if(!t.can_propose)return '你在本门暂无决策权，仍可查看地方形势与政策。取得本门议事资格后，才能提出地方议案。';
    return '你可提出本门地方议案，须经有权成员多数表决通过；费用与资材由本门府库承担。';
  }
  function guide(host,t){
    const box=el('section',null,'atlas-guide');box.append(el('h3','地方影响如何经营'),el('p',authority(t),'atlas-access'));
    const bands=el('div',null,'atlas-bands');
    for(const [name,range] of [['中枢地区','90–100'],['核心地区','70–不足90'],['战略要地','50–不足70'],['边缘地区','30–不足50'],['缓冲地区','不足30']]){const r=el('div');r.append(el('strong',name),el('small',range));bands.append(r);}box.append(bands);
    box.append(el('p','驻地固定 100，宗门传送阵保底 40，据点保底 50。新地必须紧邻己方已有影响的地域；非驻地地区至多容纳三宗，名额已满须先让一方退出。有境界门槛的地域禁止新扩张，已有山门保持原驻地影响。'));
    const policies=el('div',null,'atlas-policy-cards');
    const descriptions={stewardship:'减少巡守开支，稳固地方关系。',extraction:'加强采办收益，但养护投入与影响衰退有所增加。',patrol:'重在维持影响，巡守开支较高，采办收益略有减少。',conciliation:'节省养护投入，减缓影响衰退，采办收益有所减少。'};
    for(const [id,p] of Object.entries(t?.policies||{})){const card=el('article');card.append(el('h4',p.name),el('small',`适用影响 ${p.minimum}–${p.maximum}`),el('p',descriptions[id]||'按当地形势施行。'));policies.append(card);}box.append(policies);
    box.append(el('p','在“政策与决议”中选择地域，提出投放、建据点、比试或边界袭扰。政策只能用于适用影响范围；本门尚未经营的地域，需先投放或建立据点。'),el('p','地方经营会消耗府库，也影响当地资源获取；同地相对影响越大，所得份额越大。外交或战斗长老可以减缓影响衰退。每次修行或旅行结束后，查看该段岁月的收支与最新形势。'));
    host.append(box);
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
    const key=`${map.world}:${map.locations.map(n=>n.id).join(',')}:${map.roads?.length}`;if(layouts.has(key))return layouts.get(key);
    const nodes=map.locations.map((n,i)=>({id:n.id,x:500+300*Math.cos(i*2.4),y:360+250*Math.sin(i*2.4)})),index=new Map(nodes.map(n=>[n.id,n]));
    // Bounded, cached presentation work; never part of a yearly settlement.
    for(let tick=0;tick<160;tick++){
      const force=new Map(nodes.map(n=>[n.id,{x:0,y:0}]));
      for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){const a=nodes[i],b=nodes[j],dx=a.x-b.x,dy=a.y-b.y,d=Math.max(25,Math.hypot(dx,dy)),f=30000/(d*d*d);force.get(a.id).x+=dx*f;force.get(a.id).y+=dy*f;force.get(b.id).x-=dx*f;force.get(b.id).y-=dy*f;}
      for(const edge of map.roads||[]){const a=index.get(edge.from),b=index.get(edge.to);if(!a||!b)continue;const dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy)),f=(d-150)*.015;force.get(a.id).x+=dx/d*f;force.get(a.id).y+=dy/d*f;force.get(b.id).x-=dx/d*f;force.get(b.id).y-=dy/d*f;}
      nodes.forEach(n=>{const f=force.get(n.id);n.x=Math.max(75,Math.min(925,n.x+Math.max(-8,Math.min(8,f.x))));n.y=Math.max(65,Math.min(635,n.y+Math.max(-8,Math.min(8,f.y))));});
    }layouts.set(key,index);return index;
  }
  function render(map,state,send,locked){
    const host=document.querySelector('#map-atlas');if(!host)return;lastRender=[map,state,send,locked];lockRule=locked;if(world!==map.world||gameId!==state.id){world=map.world;gameId=state.id;selected=map.current;faction='';zoom=1;view='influence';display='map';}if(!map.locations.some(n=>n.id===selected))selected=map.current;
    host.replaceChildren();host.classList.add('map-atlas');const places=new Map(map.locations.map(n=>[n.id,n])),points=layout(map),bar=el('div',null,'atlas-toolbar');bar.append(el('strong',map.territory?'山川形势 · 宗门影响':'山川形势'));
    const select=el('select');select.setAttribute('aria-label','地图地点');map.locations.forEach(n=>{const o=el('option',n.name);o.value=n.id;select.append(o);});select.value=selected;select.onchange=()=>{selected=select.value;render(map,state,send,locked);};bar.append(select);
    if(map.territory?.enabled){const filter=el('select');filter.setAttribute('aria-label','影响力宗门');const all=el('option','各方影响');all.value='';filter.append(all);const factions=new Map(map.locations.flatMap(n=>(n.influences||[]).map(r=>[r.id,r.name])));factions.forEach((name,id)=>{const o=el('option',name);o.value=id;filter.append(o);});filter.value=faction;filter.onchange=()=>{faction=filter.value;render(map,state,send,locked);};bar.append(filter);}
    if(view==='influence'&&display==='map')[['−',()=>zoom=Math.max(1,zoom-.5)],['＋',()=>zoom=Math.min(3,zoom+.5)]].forEach(([name,act])=>{const b=button(name,()=>{act();render(map,state,send,locked);});b.setAttribute('aria-label',name==='＋'?'放大地图':'缩小地图');bar.append(b);});host.append(bar);
    if(map.territory){const nav=el('nav',null,'atlas-view-tabs');nav.setAttribute('aria-label','地方影响功能');for(const [id,name] of [['influence','势力分布'],['decisions','政策与决议'],['guide','机制说明']]){const b=button(name,()=>open(id));b.dataset.atlasView=id;b.setAttribute('aria-pressed',String(view===id));nav.append(b);}host.append(nav);
      if(!map.territory.enabled)host.append(el('p',authority(map.territory),'atlas-access'));
      if(view==='guide'){guide(host,map.territory);return;}
    }
    const choose=id=>{selected=id;render(map,state,send,locked);};
    if(view==='influence'){
    if(map.territory?.enabled){const modes=el('div',null,'atlas-display-tabs');for(const [id,name] of [['map','地图'],['list','地区列表']]){const b=button(name,()=>{display=id;render(map,state,send,locked);});b.dataset.atlasDisplay=id;b.setAttribute('aria-pressed',String(display===id));modes.append(b);}host.append(modes);}
    if(display==='list'&&map.territory?.enabled)regionList(host,map,choose);else{
    const viewport=el('div',null,'atlas-viewport'),drawing=svg('svg',{viewBox:'0 0 1000 710',role:'group','aria-label':`${map.world_name}道路与势力图`});drawing.style.width=`${zoom*100}%`;drawing.style.minWidth=zoom>1?'600px':'';drawing.append(svg('path',{d:'M0 630 Q180 430 330 630 T650 650 T1000 600 V710 H0Z',class:'atlas-mountains'}));
    for(const edge of map.roads||[]){const a=points.get(edge.from),b=points.get(edge.to);if(a&&b)drawing.append(svg('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,class:'atlas-road'}));}
    for(const place of map.locations){const p=points.get(place.id),influences=(place.influences||[]).filter(r=>!faction||r.id===faction),description=influences.map(r=>`${r.name} ${r.value}，${r.band}`).join('；'),g=svg('g',{transform:`translate(${p.x},${p.y})`,class:`atlas-node${place.current?' current':''}${place.id===selected?' selected':''}`,role:'button',tabindex:'0','aria-label':`${place.name}${place.current?'，当前位置':''}${place.min_realm_index?'，有境界门槛':''}${description?'，'+description:''}`,'data-atlas-location':place.id});const title=svg('title');title.textContent=`${place.name}${description?'：'+description:''}`;g.append(title);if(influences.length)g.append(svg('circle',{r:41,fill:color(influences[0].id),'fill-opacity':.08+influences[0].value/500,stroke:'none'}));influences.slice(0,3).forEach((r,i)=>g.append(svg('circle',{r:25+i*7,fill:'none',stroke:color(r.id),'stroke-width':6,'stroke-opacity':.35+r.value/160})));g.append(svg('circle',{r:13,class:'atlas-dot'}));const icon=svg('text',{y:5,'text-anchor':'middle',class:'atlas-seal'});icon.textContent=place.current?'你':place.min_realm_index?'禁':(place.factions||[]).length?'府':(place.wars||[]).length?'战':'·';g.append(icon);const label=svg('text',{y:55,'text-anchor':'middle',class:'atlas-label'});label.textContent=place.name;g.append(label);if(influences.length){const value=svg('text',{y:73,'text-anchor':'middle',class:'atlas-value'});const r=influences.find(r=>r.owned)||influences[0];value.textContent=`${r.owned?'本门 ':''}${r.value}`;g.append(value);}g.onclick=()=>choose(place.id);g.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();choose(place.id);}};drawing.append(g);}
    viewport.append(drawing);host.append(viewport);host.append(el('p',map.territory?.enabled?'彩环表示宗门影响，环越深影响越强。驻地固定 100，传送阵保底 40，据点保底 50。':'道路表示实际连接；“你”为当前位置，“府”为势力驻地，“禁”为有境界门槛的地域。','atlas-legend'));
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
  window.MapAtlas={render,syncBusy,open};
})();

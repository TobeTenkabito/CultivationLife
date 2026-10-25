/* Public map projections only. Commands are bound to the existing travel boundary. */
(() => {
  'use strict';
  const modes=[['terrain','山河'],['influence','势力'],['events','时令'],['caravans','商旅'],['buildings','营造']];
  const tones=['#d8a66e','#8dbab3','#b39bd0','#cf9298','#a7bc7c','#88add1'];
  const node=(tag,text,cls='')=>{const n=document.createElement(tag);n.className=cls;if(text!=null)n.textContent=text;return n;};
  const color=id=>{let h=0;for(const c of String(id))h=(h*31+c.charCodeAt(0))>>>0;return tones[h%tones.length];};
  let state=null,mapView=null,mode='terrain',key='',selected=null,toolbar=null,details=null,go=null,travel=null,locked=()=>true;
  function art(row){
    if(row.type==='scenery')return null;
    let kind=['cave','temple','farm','mine','hunt','alchemy','forge','shop'].includes(row.subtype)?row.subtype:row.type==='city'?'city':'industry';
    const industry=['farm','mine','hunt','alchemy','forge','shop'].includes(kind);
    if(industry&&row.status==='destroyed')kind='industry';
    const stage=row.status==='destroyed'?'ruin':String(Math.max(1,Math.min(industry?5:3,Number(row.level)||1)));
    return `/assets/pixel/buildings/${kind}-${stage}.png`;
  }
  function events(data){
    const entries=new Map((data.map?.locations||[]).map(p=>[p.id,[]]));
    const add=(id,text)=>entries.get(id)?.push(text);
    for(const [row,name]of [[data.auction_system,'拍卖会'],[data.exchange_system,'交换会']])if(row?.available)
      add(row.location_id,`${name} · ${row.status==='scheduled'?`${row.actions_until_open}个时间单位后开幕`:row.status==='black_market'?'散场黑市':'正在举行'}`);
    for(const p of data.map?.locations||[]){
      if(p.ghost_parade)add(p.id,`百鬼夜行 · ${p.ghost_parade.status==='active'?'正在发生':`第 ${p.ghost_parade.start_age} 年开启`}`);
      for(const w of p.wars||[])add(p.id,`${w.attacker} / ${w.defender} · ${({marching:'集结',engaged:'交锋',returning:'撤军'})[w.phase]||w.phase}`);
    }
    return entries;
  }
  function fleets(){return (state?.map?.economy?.caravans||[]).filter(f=>f.status!=='retired');}
  function fleetText(f){const year=Number(state.map.economy.year??state.player.world_age??state.player.age);return `${f.name} · ${({waiting:'候货',travelling:'在途',selling:'待售',stranded:'受阻'})[f.status]||'运输'}${f.arrival!=null?` · 预计余 ${Math.max(0,f.arrival-year)} 年`:''}`;}
  function ensure(){
    if(toolbar)return;
    toolbar=node('nav',null,'home-map-modes');toolbar.setAttribute('aria-label','主界面地图视图');
    for(const [id,label]of modes){const b=node('button',label);b.type='button';b.dataset.homeMapMode=id;b.onclick=()=>{mode=id;refresh();describe(state,selected);};toolbar.append(b);}
    document.querySelector('.pixel-scene').prepend(toolbar);
    details=node('section',null,'home-map-detail');details.setAttribute('aria-label','所选地域情报');document.querySelector('.pixel-local').append(details);
  }
  function refresh(){
    if(!state?.map||!mapView)return;
    ensure();const markers=new Map(),lines=[],visibleEvents=events(state),locations=state.map.locations;
    for(const p of locations){
      if(mode==='influence'){
        const r=(p.influences||[]).slice().sort((a,b)=>b.value-a.value)[0],f=(p.factions||[])[0];
        if(r||f)markers.set(p.id,{color:color((r||f).id|| (r||f).name),label:r?`${r.name} ${r.value}`:f.name,detail:(p.influences||[]).map(x=>`${x.name}：${x.value} · ${x.band}`).join('；')});
      }else if(mode==='events'&&visibleEvents.get(p.id)?.length)markers.set(p.id,{color:'#cba56e',label:`${visibleEvents.get(p.id).length} 项活动`,detail:visibleEvents.get(p.id).join('；')});
      else if(mode==='buildings'&&p.buildings?.length){const b=p.buildings.find(r=>r.type==='city')||p.buildings[0];markers.set(p.id,{art:art(b),label:`${p.buildings.length} 处 · ${b.status==='destroyed'?'遗址':b.type==='scenery'?'景色':`${b.level}级`}`,detail:p.buildings.map(b=>b.name).join('、')});}
    }
    if(mode==='caravans')for(const f of fleets()){
      const valid=new Set(locations.map(p=>p.id)),route=(f.route||[]).filter(id=>valid.has(id));
      for(let i=1;i<route.length;i++)lines.push({from:route[i-1],to:route[i]});
      const year=Number(state.map.economy.year??state.player.age),progress=f.arrival!=null?Math.max(0,Math.min(1,(year-f.departure)/Math.max(1,f.arrival-f.departure))):0;
      const id=route.length>1?route[Math.min(route.length-1,Math.floor(progress*(route.length-1)))]:f.location_id;
      if(valid.has(id)){const old=markers.get(id);markers.set(id,{color:'#e1c276',label:old?'多支商队':f.name,detail:[old?.detail,fleetText(f)].filter(Boolean).join('；')});}
    }
    if(mode==='terrain'&&selected){const p=locations.find(p=>p.id===selected);for(let i=1;i<(p?.route_ids||[]).length;i++)lines.push({from:p.route_ids[i-1],to:p.route_ids[i]});}
    mapView.project(state.map,mode,markers,lines);
    toolbar.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.homeMapMode===mode)));
  }
  function describe(data,id){
    if(!data?.map||data.map.world!==data.player.world)return;
    state=data;selected=id||data.map.current;ensure();
    const p=data.map.locations.find(p=>p.id===selected);details.replaceChildren();if(!p)return;
    const title=node('h4',modes.find(r=>r[0]===mode)[1]+' · '+p.name);details.append(title);
    const rows=mode==='influence'?(p.influences||[]).map(r=>`${r.name} · 影响 ${r.value} · ${r.band} · 占比 ${r.share}%`):mode==='events'?events(data).get(p.id):mode==='caravans'?fleets().filter(f=>f.location_id===p.id||(f.route||[]).includes(p.id)).map(fleetText):mode==='buildings'?(p.buildings||[]).map(b=>`${b.name} · ${b.status==='destroyed'?'遗址':b.status==='damaged'?'受损 · ':''}${b.type==='scenery'?'景色':`${b.level}级`}`):[];
    if(mode==='influence'&&!rows.length)rows.push(...(p.factions||[]).map(r=>`${r.name} · 驻地`));
    for(const text of rows)details.append(node('p',text));
    if(mode!=='terrain'&&!rows.length)details.append(node('p','此地暂无已公开的相关记录。','muted'));
    if(mode==='caravans')details.append(node('small','仅列当地可见商队，进度按已过游戏年份估算。'));
    if(mode==='buildings')for(const b of p.buildings||[]){const src=art(b);if(!src)continue;const img=node('img',null,'home-building-preview');img.src=src;img.alt=`${b.name} · ${b.status==='destroyed'?'遗址':`${b.level}级`}`;img.classList.toggle('damaged',b.status==='damaged');details.append(img);}
    if(!p.current){details.append(node('p',`${(p.route_names||[]).join(' → ')} · ${p.travel_years} 年`,'home-map-route'));if(p.warning)details.append(node('p',p.warning,'home-map-warning'));if(p.travel_progress)details.append(node('small',`已走 ${p.travel_progress.completed}/${p.travel_progress.total} 年；更换目的地会放弃原行程。`));}
    go=node('button',p.current?'已在此地':p.travel_status==='lethal'?'强行前往（必死）':`${p.travel_progress?'继续前往':'前往此地'} · ${p.travel_years} 年`,'home-map-travel');go.type='button';go.dataset.destination=p.id;go.onclick=()=>{if(!go.disabled)travel?.(p.id);};details.append(go);syncBusy();refresh();
  }
  function syncBusy(){if(go){const p=state?.map?.locations.find(p=>p.id===go.dataset.destination);go.disabled=!p||p.current||!['ok','lethal'].includes(p.travel_status)||locked();}}
  function render(data,view){
    state=data;mapView=view;if(!data?.map||!view)return;
    const next=`${data.id}:${data.map.world}:${data.map.instance_id||''}`;if(key!==next){key=next;mode='terrain';selected=data.map.current;}
    if(!data.map.locations.some(p=>p.id===selected))selected=data.map.current;
    describe(data,selected);
  }
  window.HomeMapModes=Object.freeze({render,describe,syncBusy,art,events,bind(fn,lock){travel=fn;locked=lock;syncBusy();}});
})();

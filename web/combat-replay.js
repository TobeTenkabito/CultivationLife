/* Read-only projection of settled combat phases. No game actions or writes. */
(() => {
  'use strict';
  const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x));
  const mix=(a,b,t)=>a+(b-a)*t;
  const tail=list=>list?.[list.length-1];
  const between=(t,a,b)=>{const x=clamp((t-a)/(b-a));return x*x*(3-2*x);};
  let catalogPromise=null,current=null,context=null,revision=0,raf=0,observer=null;
  let intersection=null,onscreen=true;
  const extensionCatalogs=new Map();
  let clock=0,last=0,painted=-Infinity,playing=false,speed=2,media=matchMedia('(prefers-reduced-motion: reduce)');
  const root=document.getElementById('battle-animation');
  const canvas=root.querySelector('canvas'),status=root.querySelector('[data-combat-status]');
  const replay=root.querySelector('[data-combat-replay]'),pause=root.querySelector('[data-combat-pause]');
  replay.append(VisualAssets.icon('replay'));pause.append(VisualAssets.icon('pause'));
  let pauseIcon='pause';
  const reduced=()=>document.documentElement.dataset.motion==='reduced'||media.matches;
  const visible=()=>current?.open&&window.PixelLibrary?.active()&&!document.hidden;
  function hash(value){let n=2166136261;for(const c of value)n=Math.imul(n^c.charCodeAt(0),16777619);return n>>>0;}
  function build(report,A,natalIcon){
    const visual=report.visual,hero=visual?.hero,npc=visual?.enemy;
    if(![1,2].includes(visual?.schema_version)||A.actors[hero]?.role!=='hero'||!(A.actors[npc]?.role==='npc'||npc===hero&&ActorVariants.valid(visual.teams?.npc?.[0]?.visual_variant))||!report.rounds?.length||report.rounds.length>72)return null;
    const teams=visual.schema_version===2?visual.teams:{
      hero:[{id:'player',asset:hero,name:report.player_roster?.[0]?.name??'你',kind:'player',weight:1}],
      npc:[{id:'enemy',asset:npc,name:report.target_name??'对手',kind:'cultivator',weight:1}]};
    if(!teams||!['hero','npc'].every(side=>Array.isArray(teams[side])&&teams[side].length>0&&teams[side].length<=3&&
      teams[side].every((member,i)=>A.actors[member.asset]&&
        (A.actors[member.asset].role==='npc'||side==='hero'&&i===0&&member.asset===hero||side==='npc'&&member.asset===hero&&ActorVariants.valid(member.visual_variant))&&
        (!member.gender||!A.actors[member.asset].sex||member.gender===A.actors[member.asset].sex)&&
        typeof member.name==='string'&&member.name.length<=64&&Number.isFinite(member.weight)&&member.weight>0)))return null;
    const ordinary=report.rounds.filter(r=>r.ordinary_exchange&&['player','enemy'].includes(r.initiative));
    const hasDomains=report.rounds.some(row=>CombatDomains.facts(row,visual));
    if(!ordinary.length&&!hasDomains)return null;
    const maxima={hero:Number(report.player_combat_state_max),npc:Number(report.enemy_combat_state_max)};
    if(!Object.values(maxima).every(v=>Number.isFinite(v)&&v>0))return null;
    const firstDomain=CombatDomains.facts(report.rounds[0],visual);
    const opening=firstDomain?firstDomain.opening.map((v,i)=>v*maxima[i?'npc':'hero']):ordinary[0]?.ordinary_exchange.opening;
    if(!Array.isArray(opening)||opening.length!==2||!opening.every(Number.isFinite))return null;
    const initial={hero:opening[0],npc:opening[1]};
    const rounds=[],events=[],checkpoints=[],domains=[];
    let start=.5,seed=hash(JSON.stringify([visual,report.age,report.rounds]));
    const choose=list=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return list[(seed>>>0)%list.length];};
    for(const [rowIndex,row] of report.rounds.entries()){
      const phases=CombatDomains.stages(row,visual,start);
      const release=()=>{
        if(!phases.length)return;
        const next=CombatDomains.facts(report.rounds[rowIndex+1]??{},visual);
        const leaving=phases[0].a.fields.filter(f=>!next?.fields.some(n=>n.owner===f.owner&&n.voisinage_id===f.voisinage_id));
        if(leaving.length){domains.push({...tail(phases),releasing:leaving.map(f=>f.owner),phase:'release',label:'收域',start,end:start+1.2});start+=1.2;}
      };
      domains.push(...phases);
      if(phases.length){
        const a=phases[0].a;
        checkpoints.push({t:start,values:{hero:a.opening[0]*maxima.hero,npc:a.opening[1]*maxima.npc}});
        start=tail(phases).end;
        checkpoints.push({t:start,values:{hero:a.after[0]*maxima.hero,npc:a.after[1]*maxima.npc}});
      }
      const exchange=row.ordinary_exchange;
      if(!exchange||!['player','enemy'].includes(row.initiative)){
        release();
        checkpoints.push({t:start,values:{hero:Number(row.player_combat_state),npc:Number(row.enemy_combat_state)}});
        continue;
      }
      const ordinaryStart=start;
      if(![exchange.opening,exchange.before,exchange.after].every(a=>Array.isArray(a)&&a.length===2&&a.every(Number.isFinite)))return null;
      checkpoints.push({t:start,values:{hero:exchange.before[0],npc:exchange.before[1]}});
      start+=.3;
      for(const side of row.initiative==='player'?['hero','npc']:['npc','hero']){
        if(exchange.actors?.[side==='hero'?'player':'enemy']===false)continue;
        const target=side==='hero'?'npc':'hero',index=target==='hero'?0:1;
        const loss=Math.max(0,exchange.before[index]-exchange.after[index]);
        const totalWeight=teams[side].reduce((n,member)=>n+member.weight,0);
        let assigned=0;
        for(const [actorIndex,member] of teams[side].entries()){
          const actor=A.actors[member.asset],targetIndex=(row.round-1+actorIndex)%teams[target].length;
          const defender=A.actors[teams[target][targetIndex].asset];
          const action=actor.attack_action ?? (actor.role!=='hero'?actor.faction:choose(actor.faction==='dao'
            ?(visual.natal_item_id||visual.natal_mold_id?['dragon','treasure']:['dragon'])
            :(defender.creature?['blast','shadows']:['blast','shadows','melee'])));
          const spec=A.actions[action];if(!spec)return null;
          const contacts=spec.contacts.map(t=>start+t);
          const r={index:rounds.length,number:row.round,side,actorIndex,targetIndex,guard:loss===0,action,name:spec.name,start,contacts,
            end:start+Math.max(spec.duration,tail(spec.contacts)+2.15),duration:spec.duration};
          rounds.push(r);
          contacts.forEach((t,i)=>events.push({t,round:r.index,side,guard:r.guard,name:r.name,
            value:mix(exchange.before[index],exchange.after[index],(assigned+member.weight*(i+1)/contacts.length)/totalWeight),target}));
          assigned+=member.weight;
          start=r.end+.2;
        }
      }
      if(phases.length){
        domains.push({...tail(phases),phase:'ordinary',label:'邻域维持 · 普通交锋',start:ordinaryStart,end:start});
        release();
      }
      checkpoints.push({t:start,values:{hero:Number(row.player_combat_state),npc:Number(row.enemy_combat_state)}});
      start+=.35;
    }
    if(!rounds.length&&!domains.length)return null;
    const lastRow=tail(report.rounds),lastRound=tail(rounds);
    let defeat=null,finisher=null;
    let outcome=report.outcome??({killed:'victory',captured:'victory',victory:'victory',victory_escape:'victory',dead:'defeat',defeat:'defeat',defeat_survived:'defeat'}[report.result]);
    if(['dead','defeat','defeat_survived','controlled','defeat_trapped'].includes(report.result))outcome='defeat';
    if(lastRow.ordinary_exchange&&['victory','defeat'].includes(outcome)&&!(outcome==='victory'&&report.objective==='survive')){
      const side=outcome==='victory'?'npc':'hero',id=side==='hero'?hero:npc;
      const clip=A.actors[id].animations.defeat;
      const winner=side==='hero'?'npc':'hero',source=[...rounds].reverse().find(r=>r.side===winner);
      if(clip&&source){
        let contactRound=lastRound;
        if(lastRound.side!==winner){
          // A visual coda reuses an authorised winning attack. It is not another
          // ordinary exchange, health event, initiative change or game action.
          const spec=A.actions[source.action],begin=lastRound.end+.2;
          finisher={...source,number:lastRound.number,start:begin,contacts:spec.contacts.map(t=>begin+t),
            end:begin+spec.duration,presentationOnly:true,guard:false};
          contactRound=finisher;
        }
        const at=tail(contactRound.contacts)+.2;
        const defeated=teams[side].map(member=>A.actors[member.asset].animations.defeat);
        defeat={side,start:at,duration:Math.max(...defeated.map(group=>group?.duration??0))};
        if(!finisher)tail(checkpoints).t=at;
        start=Math.max(contactRound.end,at+defeat.duration)+.35;
      }
    }
    // Field-only stages have no attack animation; their final authoritative
    // state is a checkpoint, not ordinary damage attributed to a visual hit.
    const final={hero:Number(report.player_combat_state),npc:Number(report.enemy_combat_state)};
    if(!Object.values(final).every(Number.isFinite))return null;
    checkpoints.push({t:defeat?.start??start,values:final});
    const operations=[...events.map(e=>({t:e.t,values:{[e.target]:e.value}})),...checkpoints].sort((a,b)=>a.t-b.t);
    const mode=teams.hero.length>1||teams.npc.length>1?'group':'single';
    const battlefield=A.battlefields?.[mode]?.[report.natural_terrain]??null;
    const conditions=(report.artificial_conditions??[]).filter(name=>['禁空','禁神识','大阵'].includes(name)).slice(0,3);
    return {hero,npc,heroDomainAction:A.actors[hero].domain_action,teams,teamCounts:visual.team_counts??{hero:1,npc:1},battlefield,conditions,rounds,events,operations,initial,maxima,natalIcon,defeat,finisher,
      domains,domainSettings:visual.domains??{},mixed:report.rounds.some(row=>row.voisinage),duration:start+.4};
  }
  function sample(plan,time){
    time=clamp(time,0,plan.duration);
    const r=plan.rounds.find(r=>time>=r.start&&time<r.end)??
      (plan.finisher&&time>=plan.finisher.start&&time<plan.finisher.end?plan.finisher:null);
    const teams=Object.fromEntries(['hero','npc'].map(side=>[side,plan.teams[side].map((member,slot)=>({
      id:member.asset,unitId:member.id,name:member.name,visualVariant:member.visual_variant,side,slot,mode:'idle',local:time%4,dir:side==='hero'?1:-1}))]));
    const actors={hero:teams.hero[0],npc:teams.npc[0]};
    let phase=time>=plan.duration?'战报回放结束':'调息回位';
    if(r){
      const a=teams[r.side][r.actorIndex],d=teams[r.side==='hero'?'npc':'hero'][r.targetIndex],lastHit=tail(r.contacts.filter(t=>t<=time));
      a.mode=a.id===plan.hero?r.action:'attack';a.local=Math.min(time-r.start,r.duration);a.round=r;
      if(r.guard){
        const first=r.contacts[0];d.mode='brace';
        d.local=time<=first?1.85*clamp((time-r.start-.15)/(first-r.start-.15)):1.85+time-(lastHit??first);
        d.contacts=r.contacts;d.round=r;
        if(time>=tail(r.contacts)+2.15){d.mode='idle';d.local=time%4;}
      }else if(lastHit!==undefined){d.mode='hit';d.local=.55+time-lastHit;d.contacts=r.contacts;d.round=r;if(d.local>2.4){d.mode='idle';d.local=time%4;}}
      phase=r.presentationOnly?`交锋收势 · ${a.name} · ${r.name}`:`第 ${r.number} 轮 · ${a.name} · ${r.name}`;
    }
    if(plan.defeat&&time>=plan.defeat.start){
      for(const fallen of teams[plan.defeat.side]){
        fallen.mode='defeat';fallen.local=Math.min(time-plan.defeat.start,plan.defeat.duration);
      }
      phase=plan.defeat.side==='hero'?'你方失利 · 伏地收势':'敌方失利 · 伏地收势';
      if(time>=plan.duration)phase='战报回放结束';
    }
    const domain=CombatDomains.state(plan,time);
    if(domain){
      if(!r)phase=`第 ${domain.number} 轮 · ${domain.label}`;
      if(['open','effect'].includes(domain.phase)){
        const owners=new Set(domain.phase==='effect'?domain.a.effects.map(e=>e.owner):domain.a.fields.map(f=>f.owner));
        for(const side of ['hero','npc'])for(const a of teams[side])if(owners.has(a.unitId)){
          a.mode=a.id===plan.hero?(plan.heroDomainAction??(a.id.startsWith('demonic')?'blast':'dragon')):'attack';a.local=Math.min(1.6,domain.local);
        }
      }
    }
    const health={...plan.initial};
    for(const op of plan.operations){if(op.t>time)break;Object.assign(health,op.values);}
    for(const k of ['hero','npc'])health[k]=clamp(health[k],0,plan.maxima[k]);
    return {time,domain,round:r??null,actors,teams,phase,health,landed:plan.events.filter(e=>e.t<=time)};
  }
  function timer(A){return {clamp,mix,between,sample,spring(age){
    if(age<0)return {shield:0,body:0,strain:0,energy:0};
    const p=A.physics,at=clamp((1.85+age)*p.config.sample_rate,0,p.samples.length-1),i=Math.floor(at),j=Math.min(i+1,p.samples.length-1);
    return Object.fromEntries(p.columns.map((name,k)=>[name,mix(p.samples[i][k],p.samples[j][k],at-i)]));
  }};}
  function paint(){
    if(!context)return;
    const began=performance.now();
    const state=context.renderer.render(context.scene,context.plan,clock,{shake:!reduced()});
    if(status.textContent!==state.phase)status.textContent=state.phase;
    for(const key of ['hero','npc']){
      const meter=root.querySelector(`[data-combat-meter=${key}]`),max=context.plan.maxima[key],value=state.health[key];
      const progress=meter.querySelector('progress'),output=meter.querySelector('output');
      if(progress.max!==max)progress.max=max;if(progress.value!==value)progress.value=value;
      const text=`${Math.round(value).toLocaleString()} / ${Math.round(max).toLocaleString()}`;
      if(output.textContent!==text)output.textContent=text;
    }
    const finished=clock>=context.plan.duration;
    const round=state.domain?.number??state.round?.number??tail(context.plan.rounds.filter(r=>r.start<=clock))?.number??0;
    const marker=`${round}:${finished}`;
    if(context.round!==marker){document.querySelectorAll('#battle-round-progress>span').forEach((node,i)=>{node.className=i+1<round||finished?'complete':i+1===round?'active':'future';});context.round=marker;}
    pause.setAttribute('aria-pressed',String(!playing));pause.title=playing?'暂停回放':'继续回放';pause.setAttribute('aria-label',pause.title);
    const next=playing?'pause':'play';if(next!==pauseIcon){pause.replaceChildren(VisualAssets.icon(next));pauseIcon=next;}
    context.samples.push(performance.now()-began);if(context.samples.length>64)context.samples.shift();
  }
  function stopFrame(){cancelAnimationFrame(raf);raf=0;last=0;}
  function tick(now){
    raf=0;if(!context||!visible()||!onscreen||!playing)return;
    if(last)clock=Math.min(context.plan.duration,clock+Math.min(.1,(now-last)/1000)*speed);
    last=now;
    if(now-painted>=50||clock>=context.plan.duration){painted=now;paint();}
    if(clock>=context.plan.duration){playing=false;paint();return;}
    raf=requestAnimationFrame(tick);
  }
  function resume(){if(context&&visible()&&onscreen&&playing&&!raf)raf=requestAnimationFrame(tick);}
  function dispose(){
    revision++;stopFrame();observer?.disconnect();observer=null;
    intersection?.disconnect();intersection=null;onscreen=true;
    if(context){context.renderer.dispose(context.scene);context=null;}
    canvas.width=canvas.height=0;playing=false;root.hidden=true;
  }
  async function mount(){
    dispose();if(!visible())return;
    const token=revision,report=current.report;
    if(!report?.visual)return;
    root.hidden=false;status.textContent='准备战报画面';pause.disabled=replay.disabled=true;
    let renderer=null,scene=null;
    try{
      catalogPromise??=fetch('/assets/pixel/combat/manifest.json').then(r=>{if(!r.ok)throw Error('combat assets');return r.json();}).catch(e=>{catalogPromise=null;throw e;});
      // Optional style vocabulary must not take down ordinary battle playback.
      const [base,items]=await Promise.all([catalogPromise,PixelLibrary.ensure(),DomainFields.ensure().catch(()=>null)]);
      let A=base;
      const identities=new Set([report.visual.hero,report.visual.enemy,...Object.values(report.visual.teams||{}).flat().map(m=>m.asset)]);
      const extraCatalogs=Object.values(items?.assets || {}).filter(row=>row.combat_actors?.some(id=>identities.has(id)));
      for(const extraCatalog of extraCatalogs){
        const key=extraCatalog.file+':'+extraCatalog.sha256;
        if(!extensionCatalogs.has(key))extensionCatalogs.set(key,fetch(extraCatalog.file).then(r=>{if(!r.ok)throw Error('Extension combat assets');return r.json();}).catch(e=>{extensionCatalogs.delete(key);throw e;}));
        while(extensionCatalogs.size>4)extensionCatalogs.delete(extensionCatalogs.keys().next().value);
        const extra=await extensionCatalogs.get(key);
        const actors=Object.fromEntries(Object.entries(extra.actors||{}).filter(([id])=>extraCatalog.combat_actors.includes(id)&&!A.actors[id]));
        const actions=Object.fromEntries(Object.entries(extra.actions||{}).filter(([id])=>!A.actions[id]));
        A={...A,actors:{...A.actors,...actors},actions:{...A.actions,...actions}};
      }
      if(token!==revision||!visible())return;
      const v=report.visual,item=items?.items[v.natal_item_id],asset=item||items?.molds[v.natal_mold_id];
      const natalIcon=items?.assets[asset]?.file;
      const plan=build(report,A,natalIcon);if(!plan){root.hidden=true;return;}
      const T=timer(A);renderer=window.createDuelRenderer(A,T,window.createCombatBeasts(A,T));
      scene=renderer.create(canvas);scene.multi=plan.teams.hero.length>1||plan.teams.npc.length>1;scene.battlefield=plan.battlefield;context={renderer,scene,plan,samples:[]};
      await renderer.prepare(plan);
      if(token!==revision||!visible()){renderer.dispose(scene);return;}
      const resize=()=>{if(context?.scene!==scene)return;renderer.resize(scene,Math.min(1000,Math.max(240,root.clientWidth)));paint();};
      resize();observer=new ResizeObserver(resize);observer.observe(root);
      intersection=new IntersectionObserver(entries=>{onscreen=entries[0].isIntersecting&&entries[0].intersectionRatio>.01;stopFrame();resume();},{root:document.getElementById('battle-report-card'),threshold:[0,.01]});
      intersection.observe(canvas);
      for(const side of ['hero','npc']){
        const list=root.querySelector(`[data-combat-lineup=${side}]`);
        list.replaceChildren(...plan.teams[side].map(member=>{
          const label=document.createElement('span');label.textContent=member.name;label.dataset.unit=member.id;return label;
        }));
        if(plan.teamCounts[side]>plan.teams[side].length){const count=document.createElement('small');count.textContent=`${plan.teams[side].length} / ${plan.teamCounts[side]}`;list.append(count);}
      }
      clock=0;playing=!reduced();pause.disabled=replay.disabled=false;paint();resume();
    }catch(error){
      renderer?.dispose(scene);if(token===revision){context=null;root.hidden=true;}
    }
  }
  function sync(report,open){
    if(!open||!PixelLibrary.active()||!report?.visual||!Array.isArray(report.rounds)||report.rounds.length>72||
      !report.rounds.some(row=>(row.ordinary_exchange&&['player','enemy'].includes(row.initiative))||CombatDomains.facts(row,report.visual))){
      current={report,open,key:null};dispose();return false;
    }
    const key=report?JSON.stringify([report.age,report.title,report.result,report.rounds,report.visual]):'';
    const same=current?.key===key,wasOpen=current?.open;current={report,open,key};
    if(!same||!wasOpen||!context)mount();
    return true;
  }
  replay.onclick=()=>{if(!context)return;clock=0;last=0;playing=true;paint();resume();};
  pause.onclick=()=>{if(!context)return;playing=!playing;stopFrame();paint();resume();};
  root.querySelector('select').onchange=e=>{speed=Number(e.target.value);};
  document.addEventListener('visibilitychange',()=>{
    stopFrame();
    if(!document.hidden&&current?.open&&!context&&PixelLibrary.active()&&current.report?.visual)mount();
    else resume();
  });
  function appearance(){
    if(!PixelLibrary.active()){
      dispose();document.querySelectorAll('#battle-round-progress>span').forEach(node=>{node.className='complete';});return;
    }
    if(reduced()){playing=false;stopFrame();if(context)paint();}
    if(current?.open&&!context)mount();
  }
  function bodyBounds(){
    if(!context?.scene.motion)return null;
    const s=context.scene;
    return Object.fromEntries(['hero','npc'].map(side=>{
      const v=s.motion[side],r=v.group.rects[v.index],dir=v.dir*(v.group.facing??1);
      const x=[r[4]-v.anchor[0],r[4]+r[2]-v.anchor[0]].map(x=>v.x+x*dir*s.scale);
      return [side,[Math.min(...x),v.y+(r[5]-v.anchor[1])*s.scale,Math.max(...x),v.y+(r[5]+r[3]-v.anchor[1])*s.scale]];
    }));
  }
  function participantBounds(){
    if(!context?.scene.motion)return [];
    const s=context.scene;
    return s.motion.participants.map(v=>{
      const r=v.group.rects[v.index],dir=v.dir*(v.group.facing??1);
      const x=[r[4]-v.anchor[0],r[4]+r[2]-v.anchor[0]].map(x=>v.x+x*dir*s.scale);
      return {side:v.side,unitId:v.unitId,id:v.id,mode:v.mode,bounds:[Math.min(...x),v.y+(r[5]-v.anchor[1])*s.scale,Math.max(...x),v.y+(r[5]+r[3]-v.anchor[1])*s.scale]};
    });
  }
  media.addEventListener('change',appearance);
  window.addEventListener('game:theme-change',appearance);
  window.addEventListener('pagehide',()=>{dispose();current=null;});
  window.CombatReplay=Object.freeze({sync,close(){if(current)current.open=false;dispose();},build,sample,
    diagnostics:()=>({active:!!context,playing,onscreen,raf:!!raf,cache:context?.renderer.cacheSize()??0,
      decodedBytes:context?.renderer.decodedBytes()??0,time:clock,duration:context?.plan.duration??0,
      domain:context?sample(context.plan,clock).domain:null,domainStages:context?.plan.domains.map(({start,end,phase,number})=>({start,end,phase,number}))??[],
      rounds:context?.plan.rounds.length??0,defeat:context?.plan.defeat??null,
      actors:context?sample(context.plan,clock).actors:null,teams:context?sample(context.plan,clock).teams:null,bounds:bodyBounds(),participants:participantBounds(),
      battlefield:context?.plan.battlefield??null,conditions:context?.plan.conditions??[],
      viewport:context?[context.scene.width,context.scene.height]:null,renderMs:context?[...context.samples]:[]}),
    seek(time){if(context){clock=clamp(time,0,context.plan.duration);paint();}}});
})();

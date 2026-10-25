/* Finite event CG: presentation observes choices; it never submits or settles them. */
(() => {
  'use strict';
  const el=(tag,text,cls='')=>{const n=document.createElement(tag);n.className=cls;if(text!=null)n.textContent=text;return n;};
  const root=el('section',null,'event-cinematic paper');root.id='event-cinematic';root.hidden=true;root.setAttribute('aria-label','渡劫演绎');
  const canvas=el('canvas');canvas.width=576;canvas.height=324;canvas.setAttribute('role','img');canvas.setAttribute('aria-label','当前人物渡劫动画');
  const caption=el('p',null,'event-cinematic-caption'),bar=el('div',null,'event-cinematic-controls');
  const play=el('button','重播'),pause=el('button','暂停'),close=el('button','收起动画');for(const b of [play,pause,close])b.type='button';
  bar.append(caption,play,pause,close);root.append(canvas,bar);document.querySelector('#event-card').before(root);
  const c=canvas.getContext('2d'),variants=ActorVariants.create(),media=matchMedia('(prefers-reduced-motion: reduce)');
  let context=null,key='',hiddenKey='',revision=0,raf=0,clock=0,last=0,drawn=-1,playing=false,background=null,backgroundPromise=null;
  const enabled=()=>document.documentElement.dataset.visual==='pixel'&&document.body.classList.contains('in-game');
  const reduced=()=>media.matches||document.documentElement.dataset.motion==='reduced';
  const choices=new Map(),choiceKey='cultivation.trial-visuals.v1';
  try{const saved=JSON.parse(sessionStorage.getItem(choiceKey)||'[]');if(Array.isArray(saved))for(const row of saved.slice(-32))if(Array.isArray(row)&&typeof row[0]==='string'&&row[0].length<8192&&TribulationEffects.catalog.some(v=>v.id===row[1]))choices.set(row[0],row[1]);}catch(_){}
  function variant(spec){
    const pool=TribulationEffects.catalog.filter(v=>v.kind===spec.style);if(!pool.length)return null;
    if(pool.some(v=>v.id===choices.get(spec.key)))return choices.get(spec.key);
    const a=new Uint32Array(1),limit=Math.floor(4294967296/pool.length)*pool.length;
    do{crypto.getRandomValues(a);}while(a[0]>=limit);
    const id=pool[a[0]%pool.length].id;choices.set(spec.key,id);while(choices.size>32)choices.delete(choices.keys().next().value);
    try{sessionStorage.setItem(choiceKey,JSON.stringify([...choices]));}catch(_){}return id;
  }
  function descriptor(data){
    const event=data?.pending_event,trial=data?.trial;if(!event||!trial?.active)return null;
    const id=event.id,kind=trial.kind;
    let style=null,mirror=null;
    if(/^EVT_PERIODIC_THUNDER_00[123]$/.test(id))style='thunder';
    else if(/^EVT_(CELESTIAL|ASURA|REINCARNATION)_ASCENSION_00[1-9]$/.test(id))style=[3,6,9].includes(Number(id.slice(-3)))?'thunder':'ascension';
    else if(/^EVT_BREAKTHROUGH_HEAVENLY_00[1-5]$/.test(id))style='thunder';
    else if(id==='EVT_HEAVENLY_DEMON_TRIBULATION_001'){style='mirror';mirror='heavenly_demon';}
    else if(id==='EVT_IMMORTAL_TRIAL_THREE_CORPSES'){style='mirror';mirror='three_corpses';}
    else if(id==='EVT_ASURA_BREAKTHROUGH'){style='mirror';mirror='heart_demon';}
    else if(/^EVT_BREAKTHROUGH_TRADITIONAL_00[1-3]$/.test(id))style='ascension';
    if(!style)return null;
    return {id,gameId:data.id,actor:VisualAssets.actor(data.player),title:event.title,style,mirror,step:trial.step||1,
      hp:data.player.hp,mp:data.player.mp,key:JSON.stringify([data.id,id,kind,trial.step,data.player.age,event.body])};
  }
  function loadBackground(){if(!backgroundPromise)backgroundPromise=new Promise(resolve=>{const img=new Image();img.onload=()=>{background=img;resolve(img);};img.onerror=()=>resolve(null);img.src='/assets/pixel/effects/tribulation-storm.png';});return backgroundPromise;}
  function stop(){cancelAnimationFrame(raf);raf=0;playing=false;last=0;pause.textContent='继续';}
  function dispose(){stop();revision++;context=null;key='';root.hidden=true;c.clearRect(0,0,576,324);variants.dispose();}
  function draw(time){
    if(!context)return;const spec=context.spec,w=576,h=324;c.clearRect(0,0,w,h);c.imageSmoothingEnabled=false;
    if(background)c.drawImage(background,0,0,w,h);else{c.fillStyle='#1f353c';c.fillRect(0,0,w,h);}
    const settled=!!spec.settled,base=spec.style==='mirror'?180:288;
    const strike=TribulationEffects.back(c,spec,time,base);
    const figure=context.figure;
    const body=(ctx,x,y,scale=1)=>{if(figure)ctx.drawImage(figure,x-96*scale,y-216*scale,192*scale,216*scale);};
    if(spec.style==='mirror'){
      const ids=spec.mirror==='three_corpses'?['corpse_self','corpse_primal','corpse_superego']:[spec.mirror];
      ids.forEach((id,i)=>variants.draw(c,ctx=>body(ctx,350+i*66,275-i*14,.66),id,time));
    }
    const recoil=strike*3;body(c,base,289+recoil);
    TribulationEffects.front(c,spec,time,base);
    canvas.dataset.phase=settled?(time<1.3?'gather':time<2.1?'strike':'settle'):'gather';canvas.dataset.actor=spec.actor||'';canvas.dataset.style=spec.style;
    canvas.dataset.variant=spec.variant||'';
  }
  function tick(now){raf=0;if(!playing||!context||root.hidden||!enabled())return;if(document.hidden){last=0;return;}
    if(last)clock=Math.min(4,clock+(now-last)/1000);last=now;
    if(clock-drawn>=.05||clock===4){draw(clock);drawn=clock;}
    if(clock<4)raf=requestAnimationFrame(tick);else stop();
  }
  function start(){if(!context)return;stop();clock=0;drawn=-1;playing=true;pause.textContent='暂停';draw(0);raf=requestAnimationFrame(tick);}
  async function show(spec){
    spec={...spec,variant:variant(spec)};
    stop();const ticket=++revision;context=null;root.hidden=false;canvas.hidden=true;caption.textContent='正在展开劫象…';
    const [figure]=await Promise.all([spec.actor?VisualAssets.load(spec.actor+'.figure'):Promise.resolve(null),loadBackground()]);
    if(ticket!==revision||!enabled())return;
    context={spec,figure};canvas.hidden=false;caption.textContent=spec.settled?`${spec.title} · ${spec.dead?'劫中陨落':'本关已结算'} · 气血 ${Math.round(spec.hp)} → ${Math.round(spec.afterHp)}`:`${spec.title} · 劫象将至，请选择应对`;
    if(reduced()){clock=spec.settled?4:0;draw(clock);pause.textContent='继续';}else start();
  }
  function render(data){
    if(!enabled()){dispose();return;}
    const spec=descriptor(data);
    if(!spec){if(context?.spec.settled&&context.spec.gameId===data?.id)return;dispose();return;}
    if(spec.key===key)return;key=spec.key;if(hiddenKey===key)return;show(spec);
  }
  play.onclick=start;pause.onclick=()=>{if(playing)stop();else{if(clock>=4)clock=0;playing=true;last=0;pause.textContent='暂停';raf=requestAnimationFrame(tick);}};
  close.onclick=()=>{hiddenKey=key;dispose();};
  document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(raf);raf=0;last=0;}else if(playing&&context&&!root.hidden)raf=requestAnimationFrame(tick);});
  window.addEventListener('game:theme-change',()=>{if(!enabled())dispose();else if(reduced()&&context){stop();draw(context.spec.settled?4:0);}});
  window.EventScenes=Object.freeze({render,dispose,capture:descriptor,settled(before,after){if(!before||before.gameId!==after.id||!enabled())return;key=descriptor(after)?.key||before.key;show({...before,settled:true,dead:!after.player.alive,afterHp:after.player.hp});},
    inspect:()=>({playing,frame:raf,phase:canvas.dataset.phase,actor:canvas.dataset.actor,style:canvas.dataset.style,variant:canvas.dataset.variant,key,open:!root.hidden})});
})();

/* Settled domain facts only. No actions, timers, game RNG or storage. */
(() => {
  'use strict';
  const clamp=v=>Math.max(0,Math.min(1,v)),TAU=Math.PI*2;
  const labels={strike:'杀伤',suppress:'镇压',seal:'封锁传讯与支援',restrict:'禁制',isolate:'隔离',restore_body:'修复肉身',restore_spirit:'稳定心神',restore_field:'修复邻域'};
  const validPair=v=>Array.isArray(v)&&v.length===2&&v.every(x=>Number.isFinite(x)&&x>=0&&x<=1.001);
  function facts(row,visual){
    const a=row.voisinage?.animation;
    if(a?.version!==1||!Array.isArray(a.fields)||!a.fields.length||a.fields.length>64||!validPair(a.opening)||!validPair(a.after))return null;
    if(!Array.isArray(a.effects)||a.effects.length>512||!Array.isArray(a.interventions)||a.interventions.length>512)return null;
    if(a.effects.some(e=>!labels[e.kind]||typeof e.owner!=='string'||typeof e.target!=='string'))return null;
    try{for(const f of a.fields){if(!visual.domains?.[f.owner]||!Array.isArray(f.targets)||!Array.isArray(f.protects))return null;DomainFields.compose(visual.domains[f.owner],f.owner);}}catch(_){return null;}
    return a;
  }
  function stages(row,visual,start){
    const a=facts(row,visual);if(!a)return [];
    const phases=[['open',1.4,'展开／维持'],['contest',1.5,'覆盖相持'],['control',1.5,'支配判定']];
    if(a.interventions.length)phases.push(['intervene',1.4,'特殊能力介入']);
    if(a.effects.length)phases.push(['effect',2.2,[...new Set(a.effects.map(e=>labels[e.kind]))].join(' · ')]);
    return phases.map(([phase,duration,label])=>{const segment={start,end:start+duration,number:row.round,phase,label,a,row};start+=duration;return segment;});
  }
  function state(plan,time){
    const s=plan.domains?.find(s=>time>=s.start&&time<s.end);if(!s)return null;
    return {...s,local:time-s.start,settings:plan.domainSettings};
  }
  const noise=(x,y)=>(Math.sin(x*1.3+Math.sin(y*.7)*2)+Math.cos(y*1.7+x*.3)+2)/4;
  function draw(c,scene,motion,domain,time,front){
    if(!domain)return;
    const {a,phase,local,settings,row}=domain;
    const parts=motion.participants;
    const byId=new Map(parts.map(p=>[p.unitId,p]));
    // A trial manifestation may use an explicit ID instead of enemy-0.
    // Match only an unambiguous single participant on each side.
    for(const side of ['player','enemy']){
      const actual=Object.entries(row.voisinage.participants??{}).filter(([,p])=>p.side===side);
      const displayed=parts.filter(p=>p.side===(side==='player'?'hero':'npc'));
      if(actual.length===1&&displayed.length===1)byId.set(actual[0][0],displayed[0]);
    }
    const scaleX=scene.width/960,scaleY=scene.height/540;
    c.save();c.scale(scaleX,scaleY);
    const path=(pts,color,width=1,alpha=1)=>{c.save();c.strokeStyle=color;c.lineWidth=width;c.globalAlpha=alpha;c.beginPath();pts.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.stroke();c.restore();};
    const faded=phase==='release'?1-clamp(local/(domain.end-domain.start)):phase==='open'?.2+.8*clamp(local/1.2):1;
    const visibleFields=phase==='ordinary'?row.voisinage.fields:a.fields;
    const fields=visibleFields.filter(f=>byId.has(f.owner)).slice(0,6).map(f=>{
      const actor=byId.get(f.owner),appearance=DomainFields.compose(settings[f.owner],f.owner);
      const x=actor.x/scaleX,dir=actor.side==='hero'?1:-1;
      const maintained=(phase==='open'&&f.sustained_rounds>1)||(phase==='release'&&!domain.releasing?.includes(f.owner));
      const opacity=maintained?1:faded;
      return {...f,appearance,light:appearance.light,dir,x,opacity,cx:480+(dir===1?-90:90),cy:280,rx:340*(.6+.4*opacity),ry:205*(.6+.4*opacity)};
    });
    if(!front)for(const f of fields){
      const style=f.appearance;
      // Coarse pixel field retains visible edges and a translucent interior.
      for(let y=30;y<510;y+=6)for(let x=0;x<960;x+=6){
        const d=DomainFields.distance(f,x,y,time,style);if(d>1.04)continue;
        const n=noise(x*.013+time*.1,y*.018-time*.12),p=DomainFields.pattern(style,x,y,time,n);
        const rim=Math.exp(-Math.abs(d-.96)*23);
        c.fillStyle=`rgba(${style.color.join(',')},${((.09+.17*n+.12*p)*clamp((1.04-d)*9)+rim*.22)*style.density/100*f.opacity})`;
        c.fillRect(x,y,6,6);
      }
    }
    for(const f of fields)DomainFields.decorations({c,f,g:f,time,opacity:f.opacity,front,edge:true,noise,stroke:path});
    const relations=['open','contest'].includes(phase)?{}:phase==='control'?a.relations:(row.voisinage.relations??{});
    function bind(f,target,t){
      const v=byId.get(target);if(!v)return;
      c.save();c.translate(v.x/scaleX,v.y/scaleY);c.scale(scene.scale/scaleX,scene.scale/scaleY);c.translate(0,-433);
      const stroke=(pts,field,w=2,alpha=1)=>{path(pts,'#10282f',w+3,alpha*.85*field.opacity);path(pts,field.appearance.controlColor,w,alpha*field.opacity);path(pts,field.appearance.controlCore,.8,alpha*.9*field.opacity);};
      if(!DomainControlEffects.draw(f.appearance.control,{c,f,target:0,time:t,front,stroke})){
        for(let i=0;i<3;i++){const pts=[],r=[57,51,60][i]+20*(1-clamp(t));for(let j=0;j<=40;j++){const angle=(front?0:Math.PI)+j/40*Math.PI;pts.push([Math.cos(angle)*r,[325,369,411][i]+Math.sin(angle)*11]);}stroke(pts,f,front?3:1.6,front?.95:.5);}
      }
      c.restore();
    }
    for(const [target,relation] of Object.entries(relations??{}))if(relation.relation==='dominated'){
      const f=fields.find(f=>f.owner===relation.attacker);if(f)bind(f,target,phase==='control'?local:2+local);
    }
    if(front&&phase==='intervene')for(const e of a.interventions){
      const v=byId.get(e.target);if(!v)continue;
      const x=v.x/scaleX,y=(v.y-85*scene.scale)/scaleY,pts=[],p=clamp(local/1.4);
      for(let j=0;j<=48;j++){const angle=j/48*TAU;pts.push([x+Math.cos(angle)*(55+25*p),y+Math.sin(angle)*85]);}
      path(pts,'#10282f',5,Math.sin(p*Math.PI)*.8);path(pts,'#e3f8ed',2.3,Math.sin(p*Math.PI));
    }
    if(front&&phase==='effect')for(const e of a.effects){
      const f=fields.find(f=>f.owner===e.owner),v=byId.get(e.target);if(!f||!v)continue;
      const x=v.x/scaleX,y=(v.y-85*scene.scale)/scaleY,p=clamp(local/2.2),alpha=Math.sin(p*Math.PI);
      if(['seal','restrict','isolate'].includes(e.kind)){bind(f,e.target,local);continue;}
      if(e.kind==='strike'){
        const palette=[`rgb(${f.appearance.color.join(',')})`,f.light,f.appearance.controlCore];
        for(let i=0;i<8;i++){
          const z=i*TAU/8+time*.3,r=110*(1-p)+12,pts=[];
          for(let j=0;j<=24;j++){const u=j/24,a=z+Math.sin(u*Math.PI)*.45;pts.push([x+Math.cos(a)*r*(1-u),y+Math.sin(a)*r*(1-u)]);}
          SpellEffects.glow(c,pts,palette,2.2,alpha*.7);
        }
        SpellEffects.burst(c,x,y,1,palette,local-1.25);
      }else{
        const restore=e.kind.startsWith('restore_'),palette=[`rgb(${f.appearance.color.join(',')})`,f.light,f.appearance.controlCore];
        for(let i=0;i<5;i++){
          const r=restore?25+p*50+i*8:85-p*55+i*6;
          SpellEffects.arc(c,x,y+(i-2)*22,r,r*.3,time+i,time+i+TAU,palette,alpha*.55,1.6);
        }
        for(let i=0;i<18;i++){
          const q=(p+i/18)%1,z=i*2.39996,px=x+Math.cos(z)*48,py=y+55-q*110;
          SpellEffects.glow(c,[[px,py],[px+Math.sin(z+q)*8,py+(restore?15:-15)]],palette,1.4,alpha*Math.sin(q*Math.PI));
        }
      }
    }
    c.restore();
  }
  window.CombatDomains=Object.freeze({facts,stages,state,draw});
})();

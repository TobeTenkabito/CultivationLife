/* Four-second, deterministic cinematic layers; never decides a trial result. */
(() => {
  'use strict';
  const TAU=Math.PI*2,clamp=x=>Math.max(0,Math.min(1,x));
  const catalog=[
    {id:'forked-storm',kind:'thunder',name:'苍霆裂穹',palette:['#354986','#91bdff','#eaf7ff'],aura:['#79629b','#e8c99d','#fff2c8'],tint:'#172d5530'},
    {id:'violet-net',kind:'thunder',name:'紫霄雷网',palette:['#61478b','#d3a4fa','#faf0ff'],aura:['#465280','#9bb6e7','#f0efff'],tint:'#4e285638'},
    {id:'gold-lances',kind:'thunder',name:'金阙劫矛',palette:['#866241','#f6ce87','#fff8d6'],aura:['#896956','#e9c1a5','#fff2df'],tint:'#72543038'},
    {id:'cloud-stairs',kind:'ascension',name:'云阶问天',palette:['#506589','#b4d0ea','#f0f8ff'],aura:['#79629b','#e8c99d','#fff2c8'],tint:'#b4bfc445'},
    {id:'lotus-sky',kind:'ascension',name:'莲华开天',palette:['#806180','#e3b6d4','#fff2e6'],aura:['#667a88','#cfdfce','#f3fff3'],tint:'#89748b45'},
    {id:'heaven-gate',kind:'ascension',name:'天门照影',palette:['#87764c','#f1dca0','#fff8e2'],aura:['#5a7890','#a1cfdd','#edffff'],tint:'#a49b6840'}
  ].map(row=>Object.freeze(row));
  const look=spec=>catalog.find(r=>r.id===spec.variant&&r.kind===spec.style)||catalog.find(r=>r.kind===spec.style)||catalog[0];
  function pulse(t){return Math.max(0,1-Math.abs(t-1.68)/.43);}
  function bolt(x0,y0,x1,y1,seed){return Array.from({length:18},(_,i)=>{const u=i/17,n=Math.sin(i*127.1+seed*311.7)*43758.5453,jitter=(n-Math.floor(n))*2-1;return[x0+(x1-x0)*u+jitter*17*Math.sin(Math.PI*u),y0+(y1-y0)*u];});}
  function back(c,spec,t,x){
    const v=look(spec),blue=v.palette,gold=v.aura;
    c.save();c.fillStyle='#10183065';c.fillRect(0,0,576,324);
    c.fillStyle=v.tint;c.fillRect(0,0,576,324);
    const settled=!!spec.settled,charge=settled?clamp(t/1.2)*(1-clamp((t-1.5)/.9)):.35+.1*Math.sin(t*.7);
    const shade=c.createRadialGradient(x,80,10,x,80,210);shade.addColorStop(0,`rgba(156,190,255,${charge*.28})`);shade.addColorStop(1,'#677db000');c.fillStyle=shade;c.fillRect(0,0,576,250);
    // Layered spirals drift in the painted clouds; no block-shaped cloud stand-ins.
    for(let k=0;k<5;k++){
      const points=[];for(let j=0;j<=64;j++){const a=j/64*TAU*1.5+t*.12+k*.7,r=12+j*1.4+k*6;points.push([288+Math.cos(a)*r,73+Math.sin(a)*r*.28]);}
      SpellEffects.glow(c,points,blue,.7,.12+charge*.16);
    }
    for(let j=0;j<34;j++){const y=(j*37+t*38)%300,xx=(j*71+Math.sin(j)*30)%576;
      SpellEffects.glow(c,[[xx,y],[xx-3,y+11]],blue,.55,.13);}
    for(let j=0;j<4;j++)SpellEffects.arc(c,x,283,48+j*11,10+j*3,t*.3+j,t*.3+j+5.5,gold,.22+charge*.2,1);
    if(v.id==='violet-net')for(let j=0;j<3;j++){
      SpellEffects.arc(c,x,65,66+j*30,20+j*8,t*.12+j,t*.12+j+TAU,blue,.2+charge*.35,1.2);
      for(let k=0;k<6;k++){const a=k*TAU/6+t*.12;SpellEffects.glow(c,[[x+Math.cos(a)*60,65+Math.sin(a)*18],[x+Math.cos(a)*135,65+Math.sin(a)*42]],blue,.8,charge*.35);}
    }
    if(v.id==='gold-lances')for(let j=-2;j<=2;j++)SpellEffects.glow(c,[[x+j*52,25],[x+j*47,58],[x+j*41,86]],blue,2,charge*.6);
    if(v.kind==='ascension'){
      const q=spec.settled?clamp(t/2):.2,alpha=.3+q*.3;
      if(v.id==='cloud-stairs')for(let j=0;j<9;j++){
        const y=240-j*22,half=64-j*4;
        SpellEffects.glow(c,[[x-half,y+8],[x-half,y],[x+half,y],[x+half,y+8]],gold,1.5,alpha*(.3+j*.075));
      }
      if(v.id==='heaven-gate')for(let j=0;j<3;j++){
        const half=100-j*20,top=30+j*14;
        SpellEffects.glow(c,[[x-half,247],[x-half,top+20],[x,top],[x+half,top+20],[x+half,247]],gold,2.3-j*.4,alpha);
      }
      if(v.id==='lotus-sky')for(let j=0;j<12;j++){
        const a=j*TAU/12+t*.08,pts=[];for(let k=0;k<=36;k++){const z=k/36*TAU,u=Math.sin(z)*12,w=(1-Math.cos(z))*40;pts.push([x+Math.cos(a)*w-Math.sin(a)*u,108+Math.sin(a)*w*.6+Math.cos(a)*u]);}
        SpellEffects.glow(c,pts,blue,1.4,alpha);
      }
    }
    if(settled&&t>2.2&&!spec.dead){
      const strength=Math.sin(clamp((t-2.2)/2)*Math.PI)*.3;
      for(let j=0;j<9;j++){const dx=(j-4)*13;SpellEffects.glow(c,[[x+dx,282],[x+dx*1.1,140],[x+dx*.3,20]],gold,3,strength);}
    }
    c.restore();return spec.style==='thunder'&&settled?pulse(t):0;
  }
  function front(c,spec,t,x){
    const v=look(spec),blue=v.palette,gold=v.aura;
    const hit=spec.settled&&spec.style==='thunder'?pulse(t):0;
    if(hit>0){
      if(v.id==='forked-storm'){
        const points=bolt(x-34,28,x,126,spec.step*3);
        SpellEffects.glow(c,points,blue,5,hit);
        for(let j=0;j<6;j++){
          const at=points[3+j*2],sign=j%2?1:-1,end=[x+sign*(48+j*9),145+j*13];
          SpellEffects.glow(c,bolt(...at,...end,j+spec.step),blue,1.3,hit*.75);
        }
      }else if(v.id==='violet-net'){
        for(let j=0;j<5;j++){
          const a=Math.PI+j*Math.PI/4,sx=x+Math.cos(a)*130,sy=77+Math.sin(a)*42;
          SpellEffects.glow(c,bolt(sx,sy,x+(j-2)*23,145+Math.abs(j-2)*20,j+spec.step),blue,2.4,hit*.8);
        }
        for(let j=0;j<3;j++)SpellEffects.arc(c,x,122+j*26,50+j*16,15,0,TAU,blue,hit*.65,1.5);
      }else{
        for(let j=-2;j<=2;j++){
          const sx=x+j*55,ex=x+j*22,ey=126+Math.abs(j)*17;
          SpellEffects.glow(c,[[sx,20],[sx+j*3,72],[ex,ey],[ex-7,ey-15],[ex+7,ey-15],[ex,ey]],blue,2.7,hit*.8);
          SpellEffects.glow(c,bolt(sx,55,ex,ey,j+9),blue,.8,hit*.7);
        }
      }
      const shattered=spec.dead||spec.afterHp<spec.hp;
      for(let j=0;j<7;j++){
        const a=Math.PI+j*Math.PI/7,b=a+Math.PI/8;
        SpellEffects.arc(c,x,213,66+(shattered?t*4:0),89,a,b,gold,hit*.85,2);
      }
      SpellEffects.burst(c,x,130,.8,blue,t-1.6,false);
    }
    if(spec.settled&&t>1.6){
      const q=clamp((t-1.6)/1.5),fade=(1-q)**.7;
      for(let j=0;j<3;j++)SpellEffects.arc(c,x,285,(18+q*140+j*10),5+q*25+j*3,0,TAU,blue,fade*.55,1.5);
      for(let j=0;j<24;j++){
        const a=j*2.39996,r=20+q*100,px=x+Math.cos(a)*r,py=260+Math.sin(a)*r*.35-q*60;
        SpellEffects.glow(c,[[px,py],[px+Math.cos(a)*6,py-8]],spec.dead?blue:gold,1,fade*.65);
      }
    }
    if(spec.style==='ascension'&&spec.settled){
      const q=clamp(t/3),alpha=Math.sin(q*Math.PI)*.65;
      for(let j=0;j<5;j++)SpellEffects.arc(c,x,285-q*155+j*20,40+j*8,9+j*2,t*.6,t*.6+TAU,gold,alpha,1.4);
      if(v.id==='lotus-sky')for(let j=-3;j<=3;j++){
        const pts=[];for(let k=0;k<=40;k++){const z=k/40*TAU;pts.push([x+j*16+Math.sin(z)*20,283-(1-Math.cos(z))*(22+q*15)+Math.abs(j)*3]);}
        SpellEffects.glow(c,pts,blue,1.7,alpha);
      }
      if(v.id==='heaven-gate')for(let j=0;j<16;j++){
        const y=(j*29-t*36+600)%250;SpellEffects.glow(c,[[x-92,y],[x-92,y-9],[x+92,y-9],[x+92,y]],gold,.65,alpha*.25);
      }
    }
  }
  window.TribulationEffects=Object.freeze({back,front,pulse,catalog:Object.freeze(catalog)});
})();

/* Layered finite spell choreography, sampled from settled contact times. */
(() => {
  'use strict';
  const TAU=Math.PI*2,clamp=x=>Math.max(0,Math.min(1,x)),mix=(a,b,t)=>a+(b-a)*t;
  const colors={dao:['#399cb9','#a3f4ed','#efffff'],demonic:['#893362','#ff8074','#ffe7b2'],
    ghost:['#7860bd','#80dbd9','#e6efff'],confucian:['#477d92','#e5c98c','#fff8d9'],
    buddhist:['#cb8a42','#f8cf8a','#fff6d5'],mechanical:['#367b97','#74d9ec','#fff1b5'],
    corpse:['#594777','#bb8abe','#dbebd4'],monster:['#41956d','#a4e7ab','#f2f6d5']};
  const family=actor=>actor.faction==='companion'?'dao':actor.faction==='asura'?'demonic':actor.faction;
  function palette(actor){
    const custom=actor.spell_palette;
    if(Array.isArray(custom)&&custom.length===3&&custom.every(c=>/^#[0-9a-f]{6}$/i.test(c)))return custom;
    return colors[family(actor)]||colors.monster;
  }
  function path(c,pts,color,width=1,alpha=1){
    if(alpha<=0)return;c.save();c.globalAlpha=clamp(alpha);c.strokeStyle=color;c.lineWidth=width;c.lineCap='round';c.lineJoin='round';c.beginPath();
    pts.forEach(([x,y],i)=>i?c.lineTo(Math.round(x),Math.round(y)):c.moveTo(Math.round(x),Math.round(y)));c.stroke();c.restore();
  }
  function glow(c,pts,p,width,alpha){path(c,pts,p[0],width*4,alpha*.16);path(c,pts,p[1],width*1.8,alpha*.55);path(c,pts,p[2],Math.max(.65,width*.48),alpha*.88);}
  function arc(c,x,y,rx,ry,a,b,p,alpha=1,width=1){glow(c,Array.from({length:49},(_,i)=>{const z=mix(a,b,i/48);return[x+Math.cos(z)*rx,y+Math.sin(z)*ry];}),p,width,alpha);}
  function petal(c,x,y,r,a,p,alpha){
    glow(c,Array.from({length:25},(_,i)=>{const z=i/24*TAU,u=Math.sin(z)*r*.38,v=(Math.cos(z)-1)*r;return[x+u*Math.cos(a)-v*Math.sin(a),y+u*Math.sin(a)+v*Math.cos(a)];}),p,1,alpha);
  }
  function haze(c,x,y,r,p,alpha){
    if(alpha<=0)return;c.save();c.globalAlpha=clamp(alpha);
    const g=c.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,p[2]);g.addColorStop(.18,p[1]+'99');g.addColorStop(.6,p[0]+'40');g.addColorStop(1,p[0]+'00');
    c.fillStyle=g;c.fillRect(x-r,y-r,r*2,r*2);c.restore();
  }
  function burst(c,x,y,k,p,age,guard=false){
    if(age<0||age>.7)return;const q=age/.7,fade=(1-q)**1.5;
    // Colored corona, expanding rings and fragments remain beneath the alpha cap.
    if(p.every(v=>v.startsWith('#')))haze(c,x,y,(24+q*80)*k,p,fade*.6);
    arc(c,x,y,(8+q*52)*k,(15+q*47)*k,0,TAU,p,fade,2*k);
    arc(c,x,y,(4+q*35)*k,(7+q*30)*k,-q,TAU-q,p,fade*.7,k);
    for(let j=0;j<24;j++){const a=j*2.39996,r=(7+q*(32+j%6*7))*k,len=(5+10*(1-q))*k;
      glow(c,[[x+Math.cos(a)*r,y+Math.sin(a)*r*.8],[x+Math.cos(a)*(r+len),y+Math.sin(a)*(r+len)*.8+q*q*7*k]],p,j%4? k:2*k,fade*.7);}
    if(!guard)for(let j=0;j<6;j++)petal(c,x,y,(8+q*24)*k,j*TAU/6+q,p,fade*.5);
  }
  function draw(s,m,state,{context,projectClip,natal,image}){
    const r=state.round;if(!r||!m.attacker)return;
    if(window.HistoricalEffects?.draw(s,m,state,{context,projectClip,image}))return;
    if(window.ChristmasEffects?.draw(s,m,state,{context,projectClip,image}))return;
    if(window.TideEffects?.draw(s,m,state,{context,projectClip,image}))return;
    if(window.FrontierEffects?.draw(s,m,state,{context,projectClip}))return;
    if(window.HolidayEffects?.draw(s,m,state,{context,projectClip}))return;
    const a=m.attacker,k=s.scale,dir=a.dir,p=palette(a.actor),local=state.time-r.start;
    const front=context(s.front),rear=context(s.rear),c=context(s.projectile),origin=a.hand,x=m.contact,y=m.hitY;
    const first=r.contacts[0],charge=clamp(local/.65)*(1-clamp((state.time-(first-.65))/.45));
    const theme=family(a.actor),action=r.action;
    // Converging arcs, light filaments and motes precede the existing release pose.
    if(charge>0){
      haze(rear,...origin,64*k,p,charge*.22);
      for(let j=0;j<3;j++)arc(rear,a.x,a.y-3*k,(35+j*13)*k,(8+j*4)*k,local*.5+j,local*.5+j+5.5,p,charge*.5,k);
      for(let j=0;j<4;j++){const radius=(18+j*7)*(1-.4*clamp(local))*k,z=local*(j%2?-1.8:1.3)+j;
        arc(rear,...origin,radius,radius*.65,z,z+4.4,p,charge*.7,1.2*k);}
      for(let j=0;j<22;j++){const q=(j*.137+local*.65)%1,z=j*2.39996+local*.4,rr=(9+44*(1-q))*k;
        glow(front,[[origin[0]+Math.cos(z)*rr,origin[1]+Math.sin(z)*rr*.7],[origin[0]+Math.cos(z)*(rr-7*k),origin[1]+Math.sin(z)*(rr-7*k)*.7]],p,k,charge*q*.8);}
      if(theme==='buddhist')for(let j=0;j<8;j++)petal(rear,...origin,22*k,j*TAU/8+local*.2,p,charge*.65);
    }
    for(const [index,contact] of r.contacts.entries()){
      const age=state.time-contact,launch=contact-.85,q=clamp((state.time-launch)/.85),decay=clamp(1-age/.46);
      if(action==='melee'||action==='quadruped'){
        if(age>=-.18&&age<.35){for(let j=0;j<3;j++)arc(c,x-dir*12*k,y,(28+j*12)*k,(17+j*7)*k,-1.4+age*2,1.3+age*2,p,decay/(1+j*.5),2*k);}
      }else if(state.time>=launch&&age<.46){
        const head=age<0?mix(origin[0],x,q):x+dir*110*k*(1-decay),cy=mix(origin[1],y,q),length=Math.max(90*k,Math.min(240*k,Math.abs(head-origin[0])+20*k));
        const flame=theme==='demonic',ghost=theme==='ghost'||action==='shadows',lotus=theme==='buddhist';
        projectClip(c,m,s,()=>{
          c.save();c.beginPath();if(dir>0)c.rect(origin[0],0,s.width-origin[0],s.height);else c.rect(0,0,origin[0],s.height);c.clip();
          haze(c,head-dir*22*k,cy,65*k,p,decay*.38);
          for(let j=0;j<24;j++){
            const u=((j*.618+local*.3)%1),px=head-dir*u*length,py=cy+Math.sin(j*2.4+local*2)*(14+u*22)*k;
            glow(c,[[px-dir*(8+u*12)*k,py],[px,py-Math.sin(j)*4*k]],p,j%5?k:2*k,decay*(1-u)*.65);
          }
          // Several entwined streams form an actual volume rather than a moving icon.
          for(let j=0;j<9;j++){
            const pts=[];for(let i=0;i<=32;i++){const u=i/32,envelope=Math.sin(u*Math.PI),z=u*11-local*8+j*TAU/9;
              const spread=(flame?28:ghost?32:20)*k;
              pts.push([head-dir*(1-u)*length,cy+Math.sin(z)*spread*envelope+(j-4)*k*envelope]);}
            glow(c,pts,p,j%3?1.3*k:2.7*k,decay*(.35+.45*q));
          }
          if(action==='dragon'){
            const spine=[];for(let j=0;j<=32;j++){const u=j/32;spine.push([head-dir*(1-u)*length,cy+Math.sin(u*9-local*5)*10*k*(1-u)]);}
            glow(c,spine,p,5*k,decay*.8);
            for(const sign of [-1,1])glow(c,[[head-dir*18*k,cy],[head-dir*30*k,cy+sign*18*k],[head-dir*43*k,cy+sign*24*k]],p,2*k,decay);
            // Separate sword and spiral variants use the same real impact clock.
            if((r.number||0)%3===1)for(let j=0;j<5;j++){
              const py=cy+(j-2)*14*k,px=head-dir*(15+Math.abs(j-2)*14)*k;
              glow(c,[[px-dir*48*k,py-5*k],[px,py],[px-dir*48*k,py+5*k]],p,1.7*k,decay*.8);
            }
            else for(let j=0;j<3;j++)arc(c,head-dir*(30+j*42)*k,cy,8*k,(24+j*5)*k,local+j,local+j+5.4,p,decay*.6,1.2*k);
          }else if(lotus){for(let j=0;j<7;j++)petal(c,head-dir*18*k,cy,16*k,j*TAU/7+local,p,decay*.8);}
          else if(ghost){for(let j=0;j<3;j++){const px=head-dir*(15+j*20)*k,py=cy+Math.sin(local*4+j*2)*13*k;
            arc(c,px,py,7*k,12*k,-2.8,.8,p,decay*.7,2*k);glow(c,[[px,py+6*k],[px-dir*20*k,py+18*k],[px-dir*35*k,py+8*k]],p,2*k,decay*.6);}}
          else if(theme==='confucian'){
            for(let j=0;j<5;j++)glow(c,[[head-dir*(20+j*9)*k,cy-15*k],[head-dir*(8+j*9)*k,cy-10*k],[head-dir*j*9*k,cy+10*k]],p,k,decay*.8);
          }else if(theme==='mechanical'){
            for(let j=0;j<4;j++)arc(c,head-dir*j*18*k,cy,(5+j*2)*k,(9+j*4)*k,0,TAU,p,decay*.65,k);
          }else if(flame){for(let j=0;j<7;j++){
            const px=head-dir*j*12*k,z=Math.sin(local*7+j)*14*k;
            glow(c,[[px-dir*20*k,cy+z],[px,cy-z*.4],[px-dir*10*k,cy+z*.6]],p,2*k,decay*.6);}}
          else{for(let j=0;j<5;j++){const z=(j-2)*6*k;glow(c,[[head-dir*(35+j%2*12)*k,cy+z],[head-dir*8*k,cy+z*.4],[head,cy]],p,k,decay*.7);}}
          if(action==='treasure'){
            arc(c,head-dir*18*k,cy,25*k,25*k,0,TAU,p,decay*.8,2*k);
            for(let j=0;j<8;j++)petal(c,head-dir*18*k,cy,18*k,j*TAU/8+local*.8,p,decay*.6);
            if(natal){c.save();c.globalAlpha=decay;c.drawImage(natal,head-dir*18*k-9*k,cy-9*k,18*k,18*k);c.restore();}
          }
          c.restore();
        });
      }
      burst(front,x,y,k,p,age,r.guard);
    }
  }
  window.SpellEffects=Object.freeze({draw,burst,glow,arc,palette});
})();

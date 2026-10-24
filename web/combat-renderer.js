/* Runtime renderer promoted from the approved duel study; no settlement ports. */
(() => {
  'use strict';
  function createDuelRenderer(A,T,extension={}){
  const {clamp,between,mix}=T,TAU=Math.PI*2;
  const cache=new Map(),pending=new Map(),maxCache=36;
  const abort=new AbortController();
  let disposed=false;
  const layers=['background','hero','npc','rear','front','projectile','energy','stage','domainRear','domainFront'];
  const make=()=>document.createElement('canvas');
  const context=c=>c.getContext('2d',{willReadFrequently:true});
  function load(path){
    if(cache.has(path)){const im=cache.get(path);cache.delete(path);cache.set(path,im);return Promise.resolve(im);}
    if(pending.has(path))return pending.get(path);
    const p=fetch(path,{signal:abort.signal}).then(r=>{if(!r.ok)throw Error('Missing image: '+path);return r.blob();})
      .then(blob=>createImageBitmap(blob)).then(im=>{
        if(disposed){im.close();return null;}cache.set(path,im);
        while(cache.size>maxCache){const key=cache.keys().next().value;cache.get(key).close();cache.delete(key);}return im;
      }).finally(()=>pending.delete(path));
    pending.set(path,p);return p;
  }
  function line(c,a,b,color,width=1){
    const count=Math.max(1,Math.ceil(Math.max(Math.abs(a[0]-b[0]),Math.abs(a[1]-b[1]))));
    c.fillStyle=color;for(let i=0;i<=count;i++)c.fillRect(Math.round(mix(a[0],b[0],i/count)),Math.round(mix(a[1],b[1],i/count)),width,width);
  }
  function ring(c,x,y,rx,ry,color,start=0,end=TAU,width=1){
    let last=null;const count=Math.max(12,Math.ceil((end-start)*Math.max(rx,ry)));
    for(let i=0;i<=count;i++){const a=mix(start,end,i/count),p=[x+rx*Math.cos(a),y+ry*Math.sin(a)];if(last)line(c,last,p,color,width);last=p;}
  }
  function cap(c,max=180){const d=c.getImageData(0,0,c.canvas.width,c.canvas.height);for(let i=3;i<d.data.length;i+=4)d.data[i]=Math.min(max,d.data[i]);c.putImageData(d,0,0);}
  function create(canvas){const s={canvas};for(const k of layers)s[k]=make();return s;}
  function resize(s,available){
    const zoom=available>=960?2:1,w=Math.floor(available/zoom);
    const scale=s.multi?(w<340?.5:w<440?.625:.75):(w<280?.375:w<340?.5:w<440?.625:.75);
    const h=s.multi?Math.ceil(515*scale+50):(w<340?220:w<440?258:300);
    s.width=w;s.height=h;s.zoom=zoom;s.scale=scale;
    s.ground=s.battlefield?.ground_ratio!=null?Math.round(h*s.battlefield.ground_ratio):h-25;
    s.canvas.width=w*zoom;s.canvas.height=h*zoom;s.canvas.style.width=w*zoom+'px';s.canvas.style.height=h*zoom+'px';
    for(const k of layers){s[k].width=w;s[k].height=h;context(s[k]).imageSmoothingEnabled=false;}
  }
  function info(v){
    const actor=A.actors[v.id],g=actor.animations[v.mode];if(!g)throw Error('Unbound duel clip '+v.id+'/'+v.mode);
    const duration=g.duration,index=Math.min(g.frames-1,Math.floor(clamp(v.local,0,duration)*A.fps+1e-7));
    return {...v,group:g,index,actor,frame:g.poses[index],anchor:g.poses[index].anchor??A.anchor};
  }
  function barrier(v,s,state){
    const first=v.contacts?.[0]??Infinity,last=v.contacts?.[v.contacts.length-1]??Infinity;
    const age=state.time-first,begin=v.round?.start??Infinity;
    const opacity=v.mode==='brace'?between(state.time,begin+.3,Math.min(first-.1,begin+1.1))*(1-between(state.time,last+.9,last+1.65)):0;
    const force={shield:0,body:0,strain:0};
    for(const t of v.contacts??[]){const p=T.spring(state.time-t);for(const k of Object.keys(force))force[k]+=p[k];}
    const shape=v.actor.guard_shape??{cx:4,cy:-86,rx:70,ry:94};
    const rx=shape.rx*s.scale*opacity,ry=shape.ry*s.scale*opacity;
    const cx=v.x+v.dir*shape.cx*s.scale,cy=v.y+shape.cy*s.scale;
    return {...force,opacity,rx,ry,cx,cy,age,
      contact:cx+v.dir*(rx-force.shield*1.7*s.scale)};
  }
  function geometry(s,state){
    const teams=Object.fromEntries(['hero','npc'].map(side=>[side,state.teams[side].map((v,i)=>{
      const ratio=s.multi?[.31,.15,.23][i]:(A.actors[v.id].home_ratio??(side==='hero'?.24:.76));
      const home=s.multi?(side==='hero'?ratio:1-ratio):ratio;
      return info({...v,x:Math.round(s.width*home),y:s.ground-(s.multi?i*135*s.scale:0)});
    })]));
    const hero=teams.hero[0],npc=teams.npc[0],participants=[...teams.hero,...teams.npc];
    for(const v of participants)v.barrier=barrier(v,s,state);
    for(const v of participants){
      const rect=v.group.rects[v.index],dir=v.dir*(v.group.facing??1);
      const edges=[rect[4]-v.anchor[0],rect[4]+rect[2]-v.anchor[0]].map(x=>x*dir*s.scale);
      v.x=clamp(v.x,8-Math.min(...edges),s.width-8-Math.max(...edges));
    }
    const r=state.round;
    let contact=null,attacker=null,defender=null,hitY=s.ground-85*s.scale;
    if(r){
      attacker=teams[r.side][r.actorIndex];defender=teams[r.side==='hero'?'npc':'hero'][r.targetIndex];
      const hit=defender.actor.hit_offset??[23,-85];
      hitY=defender.y+hit[1]*s.scale;
      contact=r.guard?defender.barrier.contact:defender.x-attacker.dir*hit[0]*s.scale;
      if(r.action==='melee'){
        const local=state.time-r.start;
        let close=between(local,.8,1.72)*(1-between(local,3.7,5.1));
        const tip=attacker.frame.point??[190,161],reach=(tip[0]-attacker.anchor[0])*s.scale;
        hitY=defender.y+(tip[1]-256)*s.scale;
        if(r.guard&&defender.barrier.opacity>.1){
          const b=defender.barrier,a=Math.asin(clamp((hitY-b.cy)/b.ry,-.95,.95));
          contact=b.cx+defender.dir*(b.rx*Math.cos(a)-b.shield*1.7*s.scale*Math.exp(-(a*a)/.24));
        }
        const goal=contact-attacker.dir*reach;
        attacker.x=Math.round(mix(attacker.x,goal,close));
      }
    }
    const motion={hero,npc,teams,participants,attacker,defender,contact,hitY};
    extension.geometry?.(s,motion,state);
    for(const v of participants){
      const rect=v.group.rects[v.index],dir=v.dir*(v.group.facing??1);
      const edges=[rect[4]-v.anchor[0],rect[4]+rect[2]-v.anchor[0]].map(x=>x*dir*s.scale);
      v.x=clamp(v.x,4-Math.min(...edges),s.width-4-Math.max(...edges));
      v.y=clamp(v.y,4-(rect[5]-v.anchor[1])*s.scale,s.height-4-(rect[5]+rect[3]-v.anchor[1])*s.scale);
      const p=v.actor.release_point;
      v.hand=[v.x+v.dir*(p[0]-v.anchor[0])*s.scale,v.y+(p[1]-v.anchor[1])*s.scale];
    }
    return motion;
  }
  function drawBody(c,v,s){
    const im=cache.get(v.group.sheet);if(!im)throw Error('Atlas not ready: '+v.group.sheet);
    c.save();c.translate(Math.round(v.x),v.y);c.scale(v.dir*(v.group.facing??1),1);c.imageSmoothingEnabled=false;
    const [cw,ch]=v.group.cell??v.actor.cell??A.cell;
    const rect=v.group.rects?.[v.index]??[v.index%8*cw,Math.floor(v.index/8)*ch,cw,ch,0,0];
    c.drawImage(im,rect[0],rect[1],rect[2],rect[3],
      (rect[4]-v.anchor[0])*s.scale,(rect[5]-v.anchor[1])*s.scale,rect[2]*s.scale,rect[3]*s.scale);c.restore();
  }
  function projectClip(c,m,s,draw){
    c.save();c.beginPath();if(m.attacker.dir===1)c.rect(0,0,Math.ceil(m.contact)+1,s.height);
    else c.rect(Math.floor(m.contact),0,s.width-Math.floor(m.contact),s.height);
    c.clip();draw();c.restore();
  }
  function flightBitmap(c,im,source,head,length,contact,dir,y,height,opacity=1){
    // Crop the leading end after contact; do not shrink or pass the target.
    const consumed=clamp(dir*(head-contact),0,length),remaining=length-consumed;
    if(remaining<=0)return;
    c.save();c.globalAlpha*=opacity;c.translate(Math.round(head),Math.round(y));c.scale(dir,1);c.imageSmoothingEnabled=false;
    c.drawImage(im,source.x,source.y,source.w*(remaining/length),source.h,
      -length,-height/2,remaining,height);c.restore();
  }
  function rune(c,x,y,size,color){
    const p=(a,b)=>[x+a*size,y+b*size];
    line(c,p(-4,-8),p(4,-8),color);line(c,p(4,-8),p(4,8),color);
    line(c,p(4,8),p(-4,8),color);line(c,p(-4,8),p(-4,-8),color);
    for(const [a,b,d,e] of [[0,-6,0,-1],[-2,-3,2,-3],[-2,0,2,2],[2,2,-2,4],[-2,4,2,6]])line(c,p(a,b),p(d,e),color);
  }
  function guard(s,v,t){
    const b=v.barrier;if(b.opacity<.01)return;
    if(extension.guard?.(s,v,t,{context,line,ring})===true)return;
    const rear=context(s.rear),front=context(s.front),factor=s.scale;
    if((v.actor.energy_effect || ['companion','corpse','mechanical'].includes(v.actor.faction))){
      const color=v.actor.energy_color,accent=v.actor.faction==='corpse'?'#51405f':v.actor.faction==='mechanical'?'#ede1bd':'#d5f0da';
      for(const [c,back] of [[rear,true],[front,false]]){
        c.save();c.globalAlpha=(back?.28:.62)*b.opacity;
        const start=back?Math.PI/2:-Math.PI/2;
        for(let band=0;band<3;band++){
          const inset=band*3*factor;
          ring(c,b.cx,b.cy,Math.max(0,b.rx-inset),Math.max(0,b.ry-inset),band===1?accent:color,start,start+Math.PI);
        }
        c.restore();
      }
      front.save();front.globalAlpha=.65*b.opacity;
      for(let i=0;i<8;i++){
        const theta=t*.45+i*TAU/8;
        const x=b.cx+Math.cos(theta)*(b.rx-6*factor),y=b.cy+Math.sin(theta)*(b.ry-6*factor);
        if(v.actor.faction==='mechanical'){
          const dx=Math.cos(theta)*4*factor,dy=Math.sin(theta)*4*factor;
          line(front,[x-dx,y-dy],[x+dx,y+dy],accent,Math.max(1,Math.round(2*factor)));
        }else if(i%2===0)rune(front,x,y,.6*factor,color);
        else ring(front,x,y,2*factor,2*factor,accent);
      }
      if(b.age>=0&&b.age<.6){
        const p=b.age/.6;front.globalAlpha=.72*(1-p);
        ring(front,b.contact,b.cy,(4+16*p)*factor,(9+31*p)*factor,accent);
        for(let j=0;j<5;j++){
          const theta=-1.1+j*.55;
          line(front,[b.contact-v.dir*3*factor,b.cy],
            [b.contact+v.dir*(10+18*p)*factor*Math.cos(theta),b.cy+Math.sin(theta)*(14+25*p)*factor],color);
        }
      }
      front.restore();return;
    }
    if(v.actor.faction==='dao'){
      front.save();front.globalAlpha=.62*b.opacity;
      const x=b.contact;
      ring(front,b.cx,b.cy,b.rx,b.ry,'#79baa8',v.dir>0?-1.4:Math.PI-1.4,v.dir>0?1.4:Math.PI+1.4);
      for(let i=-1;i<=1;i++)rune(front,x-v.dir*5*factor,b.cy+i*32*factor,factor,'#8ac8b6');
      front.restore();
    }else{
      rear.save();front.save();rear.globalAlpha=.5*b.opacity;front.globalAlpha=.6*b.opacity;
      for(let j=0;j<9;j++){
        const start=t*.8+j*TAU/9,end=start+.7,c=Math.cos(start+.35)*v.dir>0?front:rear;
        let prev=null;for(let i=0;i<30;i++){
          const a=mix(start,end,i/29),bend=b.shield*1.7*factor*Math.exp(-(Math.atan2(Math.sin(a),Math.cos(a))**2)/.24);
          const p=[b.cx+v.dir*(b.rx*Math.cos(a)-bend),b.cy+b.ry*Math.sin(a)];
          if(prev)line(c,prev,p,j%4?'#26212c':'#854050',j%3?2:3);prev=p;
        }
      }rear.restore();front.restore();
    }
  }
  function aura(c,v,s,t){
    c.save();c.globalAlpha=.55;
    const color=v.actor.faction==='dao'?'#73bfc4':'#642c43';
    const x=v.hand[0],y=v.hand[1];
    for(let j=0;j<3;j++)ring(c,x,y,(10+j*4)*s.scale,(6+j*3)*s.scale,color,t*2+j*2,t*2+j*2+1.8,1);
    c.restore();
  }
  function supportEffects(s,m,state){
    const a=m.attacker,kind=a.actor.faction;
    if(!a.actor.energy_effect&&!['companion','corpse','mechanical'].includes(kind))return false;
    const r=state.round,local=state.time-r.start,k=s.scale,dir=a.dir,c=context(s.projectile),front=context(s.front);
    const hit=r.contacts[0]-r.start,launch=1.25,origin=a.hand;
    const color=a.actor.energy_color,light=a.actor.energy_effect?'#f3e8f7':kind==='companion'?'#def2d4':kind==='corpse'?'#c2abc8':'#f0d9a0';
    const charge=between(local,.4,1.1)*(1-between(local,1.3,1.7));
    front.save();front.globalAlpha=.65*charge;
    for(let j=0;j<3;j++){
      const theta=local*(kind==='corpse'?-2:2)+j*TAU/3;
      const radius=(24-j*5)*(1-.5*between(local,.5,1.2))*k;
      ring(front,...origin,radius,radius*.65,color,theta,theta+Math.PI*1.45);
      if(kind==='mechanical'){
        for(let tooth=0;tooth<8;tooth++){
          const angle=theta+tooth*TAU/8;
          line(front,[origin[0]+Math.cos(angle)*radius,origin[1]+Math.sin(angle)*radius*.65],
            [origin[0]+Math.cos(angle)*(radius+3*k),origin[1]+Math.sin(angle)*(radius*.65+3*k)],light);
        }
      }else if(j!==1)rune(front,origin[0]+Math.cos(theta)*radius,origin[1]+Math.sin(theta)*radius*.65,.55*k,light);
    }
    for(let j=0;j<16;j++){
      const age=(local*.8+j*.137)%1,theta=j*2.39996+local;
      const radius=(11+27*(1-age))*k;
      const x=origin[0]+Math.cos(theta)*radius,y=origin[1]+Math.sin(theta)*radius*.6;
      front.globalAlpha=.55*charge*age;
      line(front,[x,y],[x+Math.cos(theta)*4*k,y+Math.sin(theta)*3*k],j%3?color:light);
    }
    front.restore();
    if(local<launch||local>hit+.5)return true;
    const length=(kind==='mechanical'?58:kind==='corpse'?82:105)*k;
    const progress=between(local,launch,hit),consumed=clamp((local-hit)/.5);
    const head=local<=hit?mix(origin[0],m.contact,progress):m.contact+dir*length*consumed;
    const cy=mix(origin[1],m.hitY,progress),tail=head-dir*length;
    projectClip(c,m,s,()=>{
      c.save();c.beginPath();
      if(dir>0)c.rect(origin[0],0,s.width-origin[0],s.height);else c.rect(0,0,origin[0],s.height);
      c.clip();
      const bands=kind==='corpse'?9:7;
      for(let band=0;band<bands;band++){
        let prev=null;
        for(let j=0;j<=48;j++){
          const u=j/48,x=mix(tail,head,u);
          const envelope=Math.sin(u*Math.PI),radius=(kind==='mechanical'?10:14)*k;
          const wave=Math.sin(u*13-local*13+band*TAU/bands);
          const y=cy+wave*radius*envelope+(band-(bands-1)/2)*1.2*k*envelope;
          c.globalAlpha=(band%3?.4:.68)*(1-consumed*.3);
          if(prev)line(c,prev,[x,y],band%3?color:light,band%3===0&&kind==='corpse'?2:1);
          prev=[x,y];
        }
      }
      if(kind==='mechanical')for(let j=0;j<4;j++){
        const x=head-dir*j*14*k;
        c.globalAlpha=.6*(1-j/5);
        ring(c,x,cy,(4+j)*k,(9+j*4)*k,j%2?light:color,-Math.PI/2,Math.PI/2);
      }
      if(kind==='companion'){
        c.globalAlpha=.7;
        for(let j=0;j<4;j++){
          const angle=local*5+j*TAU/4;
          const x=head-dir*13*k,y=cy;
          line(c,[x,y],[x-dir*16*k+Math.cos(angle)*6*k,y+Math.sin(angle)*12*k],light);
        }
      }
      if(kind==='corpse')for(let j=0;j<5;j++){
        const x=head-dir*(8+j*13)*k,y=cy+Math.sin(j*1.7+local*9)*8*k;
        c.globalAlpha=.45*(1-j/6);rune(c,x,y,.5*k,j%2?light:color);
      }
      c.restore();
    });
    return true;
  }
  function effects(s,m,state){
    const r=state.round;if(!r)return;
    if(extension.effects?.(s,m,state,{context,line,ring,projectClip,between,mix,clamp})===true){impact(s,m,state);return;}
    if(supportEffects(s,m,state)){impact(s,m,state);return;}
    const c=context(s.projectile),a=m.attacker,scale=s.scale,dir=a.dir;
    const local=state.time-r.start,cy=m.hitY,x=m.contact,origin=a.hand;
    if(local>.45&&local<1.8)aura(context(s.front),a,s,local);
    projectClip(c,m,s,()=>{
      if(['dragon','blast','shadows'].includes(r.action)){
        c.beginPath();
        if(dir>0)c.rect(Math.floor(origin[0]),0,s.width-Math.floor(origin[0]),s.height);
        else c.rect(0,0,Math.ceil(origin[0])+1,s.height);
        c.clip();
      }
      if(r.action==='treasure'){
        const im=cache.get(planSeal),progress=between(local,1.5,2.35),fade=1-between(local,2.35,2.8);
        if(im&&local>=.7&&local<=2.8){
          const fx=mix(origin[0],x-dir*8*scale,between(local,.7,1.5));
          const fy=mix(24*scale,cy,progress),size=(22+22*between(local,.7,1.5))*scale;
          c.save();c.globalAlpha=fade;c.drawImage(im,Math.round(fx-size/2),Math.round(fy-size/2),size,size);c.restore();
        }
      }else if(r.action==='dragon'){
        const launch=1.6,hit=2.35,length=152*scale;
        if(local>=launch&&local<=hit+.62){
          const head=local<=hit?mix(origin[0]+dir*8,x,between(local,launch,hit)):
            x+dir*length*clamp((local-hit)/.62);
          const index=Math.floor(local*12)%4,im=cache.get(A.dragon);
          const y=mix(origin[1],cy,between(local,launch,hit));
          flightBitmap(c,im,{x:index*192,y:0,w:192,h:96},head,length,x,dir,y,76*scale,.8);
        }
      }else if(r.action==='blast'){
        const launch=1.85,hit=2.35,length=135*scale;
        if(local>=.65&&local<2.9){
          const seal=cache.get(planSeal),fx=origin[0]+dir*5,fy=origin[1]-18*scale;
          c.save();c.globalAlpha=.8;c.imageSmoothingEnabled=false;c.drawImage(seal,Math.round(fx-14*scale),Math.round(fy-14*scale),28*scale,28*scale);c.restore();
        }
        if(local>=launch&&local<hit+.55){
          const head=local<=hit?mix(origin[0],x,between(local,launch,hit)):x+dir*length*(local-hit)/.55;
          const tail=head-dir*length,centerY=mix(origin[1]-18*scale,cy,between(local,launch,hit));c.save();c.globalAlpha=.67;
          for(let b=0;b<7;b++){
            const y=centerY+(b-3)*2*scale,p1=[tail,y+Math.sin(local*12+b)*2],p2=[head,y];
            line(c,p1,p2,b%3?'#29202c':'#7d334c',b%3?2:1);
          }c.restore();
        }
      }else if(r.action==='shadows'){
        const im=cache.get(A.shadow);
        for(let i=0;i<3;i++){
          const launch=1.8+i*.3,hit=2.55+i*.4,length=80*scale;
          if(local<launch||local>hit+.38)continue;
          const head=local<=hit?mix(origin[0],x,between(local,launch,hit)):x+dir*length*(local-hit)/.38;
          const y=mix(origin[1],cy+(i-1)*13*scale,between(local,launch,hit));
          flightBitmap(c,im,{x:0,y:0,w:128,h:80},head,length,x,dir,y,50*scale,.66);
        }
      }else if(r.action==='dao'){
        if(local<.4||local>2.8)return;
        c.save();c.globalAlpha=.7*between(local,.4,.9)*(1-between(local,2.25,2.8));
        for(let i=0;i<3;i++){
          const theta=-Math.PI/2+i*TAU/3,fly=between(local,1.15+i*.05,1.85+i*.05),close=between(local,1.98,2.2);
          const start=[origin[0]+Math.cos(theta)*19*scale,origin[1]+Math.sin(theta)*25*scale];
          const end=[x-dir*(14+(i===1?15:0))*scale,cy+[-23,0,23][i]*scale];
          const p=[mix(mix(start[0],end[0],fly),x-dir,close),mix(mix(start[1],end[1],fly),cy,close)];
          rune(c,...p,scale,i===1?'#b2d4c0':'#619f8d');
          if(local>1.85)line(c,p,[x,cy],'#82c2ad');
        }c.restore();
      }else if(r.action==='demonic'){
        if(local<1.25||local>3.25)return;
        const tip=between(local,1.25,2.05)*(1-between(local,2.4,3.2));
        const gap=x-origin[0];c.save();c.globalAlpha=.68*(1-between(local,3,3.25));
        for(let band=0;band<2;band++){
          let prev=null;
          for(let i=0;i<=90;i++){
            const u=i/90*tip,v=1-u;
            const p=[v*v*v*origin[0]+3*v*v*u*(origin[0]+gap*.25)+3*v*u*u*(origin[0]+gap*.75)+u*u*u*x,
              v*v*v*origin[1]+3*v*v*u*(s.ground-8)+3*v*u*u*(s.ground-8)+u*u*u*cy
                +Math.sin(u*15-local*9+band)*3*Math.sin(u*Math.PI)+(band-.5)*5*Math.sin(u*Math.PI)];
            if(prev){line(c,prev,p,'#25212c',3);line(c,[prev[0],prev[1]+1],[p[0],p[1]+1],band?'#8b4457':'#63394d');}prev=p;
          }
        }c.restore();
      }else if(r.action==='melee'){
        if(local>.65&&local<3.65)aura(context(s.front),a,s,local);
        for(let i=0;i<r.contacts.length;i++){
          const age=state.time-r.contacts[i];if(age<-.12||age>.16)continue;
          c.save();c.globalAlpha=.6*(1-between(age,0,.16));
          ring(c,x-dir*11*scale,cy,25*scale,16*scale,'#82334a',dir>0?-1.1:Math.PI-1.1,dir>0?1.1:Math.PI+1.1,2);c.restore();
        }
      }
    });
    impact(s,m,state);
  }
  function impact(s,m,state){
    const r=state.round,a=m.attacker,scale=s.scale,cy=m.hitY,x=m.contact;
    const impact=context(s.front);
    for(const time of r.contacts){
      const age=state.time-time;if(age<0||age>.48)continue;
      const p=age/.48;impact.save();impact.globalAlpha=.67*(1-p);
      const color=r.guard?'#a5c2b0':a.actor.energy_color??(a.actor.faction==='dao'?'#92d5e5':'#b35063');
      ring(impact,x,cy,(5+18*p)*scale,(7+28*p)*scale,color,0,TAU,1);
      ring(impact,x-a.dir*2*scale,cy,(3+12*p)*scale,(4+21*p)*scale,'#e5edd8',-.7,2.2,1);
      if(p<.35){
        impact.globalAlpha=.8*(1-p/.35);
        line(impact,[x-10*scale,cy],[x+10*scale,cy],'#eef4de',2);
        line(impact,[x,cy-13*scale],[x,cy+13*scale],'#eef4de',2);
      }
      impact.globalAlpha=.67*(1-p);
      for(let i=0;i<12;i++){
        const theta=i*2.39996,d=(4+29*p)*scale;
        const px=x+Math.cos(theta)*d,py=cy+Math.sin(theta)*d+8*p*p;
        line(impact,[px,py],[px+Math.cos(theta)*4*scale,py+Math.sin(theta)*4*scale],color,1);
      }
      impact.restore();
    }
  }
  let planSeal=A.seal;
  async function prepare(plan){
    planSeal=plan.natalIcon||A.seal;
    const needed=[plan.battlefield?.file??A.terrace,A.dragon,planSeal,A.shadow];
    for(const side of ['hero','npc'])for(const [slot,member] of plan.teams[side].entries()){
      const id=member.asset,actor=A.actors[id];
      const moves=actor.role==='hero'?[...new Set(plan.rounds.filter(r=>r.side===side&&r.actorIndex===slot).map(r=>r.action))]:['attack'];
      if(plan.domains?.length)moves.push(actor.role==='hero'?(actor.domain_action??(id.startsWith('demonic')?'blast':'dragon')):'attack');
      for(const mode of ['idle','hit','brace',...moves])needed.push(actor.animations[mode].sheet);
      if(plan.defeat?.side===side)needed.push(actor.animations.defeat.sheet);
    }
    // Keep only the current duel's resources; do not decode the whole roster.
    for(const key of [...cache.keys()])if(!needed.includes(key)){cache.get(key).close();cache.delete(key);}
    if(new Set(needed).size>maxCache)throw Error('Combat resource count exceeds bound');
    for(const path of new Set(needed)){if(disposed)return;await load(path);}
    if([...cache.values()].reduce((n,im)=>n+im.width*im.height*4,0)>96*1024*1024)throw Error('Combat decode budget exceeded');
    return needed;
  }
  function render(s,plan,time,options={}){
    const state=T.sample(plan,time),m=geometry(s,state);s.state=state;s.motion=m;
    for(const k of layers)context(s[k]).clearRect(0,0,s.width,s.height);
    const bg=context(s.background),terrace=cache.get(plan.battlefield?.file??A.terrace);
    bg.fillStyle='#bed1cb';bg.fillRect(0,0,s.width,s.height);
    if(terrace){
      bg.imageSmoothingEnabled=false;
      if(s.multi&&plan.battlefield){
        const factor=Math.max(s.width/terrace.width,s.height/terrace.height);
        const width=s.width/factor,height=s.height/factor;
        const left=(terrace.width-width)/2;
        const top=clamp(terrace.height*plan.battlefield.horizon-s.height*.28/factor,0,terrace.height-height);
        bg.drawImage(terrace,Math.round(left),Math.round(top),Math.round(width),Math.round(height),0,0,s.width,s.height);
      }else if(s.multi){
        // Keep every rank on the terrace, not standing on the distant sky.
        const sourceHorizon=Math.round(terrace.height*.73),horizon=Math.round(s.height*.32);
        bg.drawImage(terrace,0,0,terrace.width,sourceHorizon,0,0,s.width,horizon);
        bg.drawImage(terrace,0,sourceHorizon,terrace.width,terrace.height-sourceHorizon,0,horizon,s.width,s.height-horizon);
      }else bg.drawImage(terrace,0,0,s.width,s.height);
    }
    const ground=context(s.stage);
    if(state.domain){ground.fillStyle='#06192248';ground.fillRect(0,0,s.width,s.height);}
    for(const condition of plan.conditions){
      ground.save();ground.globalAlpha=.18;
      if(condition==='大阵'){
        const cx=s.width/2,cy=s.height*.76,rx=s.width*.39,ry=s.height*.16;
        ring(ground,cx,cy,rx,ry,'#a78859');ring(ground,cx,cy,rx*.84,ry*.84,'#c3aa78');
        for(let i=0;i<8;i++){const angle=i*TAU/8;rune(ground,cx+Math.cos(angle)*rx,cy+Math.sin(angle)*ry,s.scale*.65,'#a78859');}
      }else if(condition==='禁空'){
        const y=Math.round(s.height*.11);
        line(ground,[8,y],[s.width-8,y],'#8a869b');
        for(let i=1;i<6;i++)rune(ground,s.width*i/6,y,s.scale*.6,'#81778f');
      }else{
        for(let i=0;i<3;i++)ring(ground,s.width*(i+1)/4,s.height*.45,18*s.scale,30*s.scale,'#808ba3',time*.25+i,time*.25+i+Math.PI);
      }
      ground.restore();
    }
    for(const v of [...m.participants].sort((a,b)=>a.y-b.y)){
      const c=context(s.stage);c.save();c.globalAlpha=.18;ring(c,v.x,v.y,22*s.scale,3*s.scale,'#243c3b',0,TAU,2);c.restore();
      drawBody(context(s[v.side]),v,s);
      if(options.effects!==false)guard(s,v,time);
    }
    if(options.effects!==false){effects(s,m,state);
      window.CombatDomains?.draw(context(s.domainRear),s,m,state.domain,time,false);
      window.CombatDomains?.draw(context(s.domainFront),s,m,state.domain,time,true);
    }
    // Smoke behind bodies is occluded; energy opacity stays capped after composition.
    const rear=context(s.rear);rear.globalCompositeOperation='destination-out';rear.drawImage(s.hero,0,0);rear.drawImage(s.npc,0,0);rear.globalCompositeOperation='source-over';
    const energy=context(s.energy);for(const key of ['rear','projectile','front'])energy.drawImage(s[key],0,0);
    cap(energy);
    const out=context(s.canvas);out.imageSmoothingEnabled=false;out.setTransform(s.zoom,0,0,s.zoom,0,0);
    out.clearRect(0,0,s.width,s.height);out.drawImage(s.background,0,0);
    let offset=0;
    if(options.shake!==false){
      const age=state.time-(state.landed[state.landed.length-1]?.t??-Infinity);
      if(age>=0&&age<.18)offset=Math.round(Math.sin(age*150)*2*(1-age/.18));
    }
    out.save();out.translate(offset,0);for(const k of ['stage','domainRear','hero','npc','domainFront','energy'])out.drawImage(s[k],0,0);out.restore();
    out.setTransform(1,0,0,1,0,0);s.cameraOffset=offset;return state;
  }
  function dispose(s){
    if(disposed)return;
    disposed=true;abort.abort();for(const im of cache.values())im.close();cache.clear();pending.clear();
    if(s){for(const key of layers){s[key].width=s[key].height=0;}s.canvas.width=s.canvas.height=0;s.state=s.motion=null;}
  }
  return {create,resize,prepare,render,dispose,cacheSize:()=>cache.size,geometry,
    decodedBytes:()=>[...cache.values()].reduce((n,im)=>n+im.width*im.height*4,0)};
  }
  window.createDuelRenderer=createDuelRenderer;
})();



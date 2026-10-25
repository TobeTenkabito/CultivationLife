/* Target-bound, front/back control choreography. No capability or settlement ports. */
(() => {
  'use strict';
  const TAU=Math.PI*2,clamp=n=>Math.max(0,Math.min(1,n)),ease=n=>{n=clamp(n);return n*n*(3-2*n);};
  function draw(m,{c,f,target:x,time:t,front,stroke},active){
    const q=ease(t/.95),alpha=active?Math.sin(clamp((t-2)/2.4)*Math.PI):.9;
    if(active&&(t<=2||t>=4.4))return true;
    const p=(pts,w=2,a=1)=>stroke(pts.map(([dx,y])=>[x+dx,y]),f,w,a*alpha);
    const curve=(fn,n=40,w=2,a=.8)=>p(Array.from({length:n+1},(_,i)=>fn(i/n)),w,a);
    const oval=(cx,y,rx,ry,a=.8)=>curve(u=>{const z=(front?0:Math.PI)+u*Math.PI;return[cx+Math.cos(z)*rx,y+Math.sin(z)*ry];},40,2,a);
    const gem=(px,y,r=5)=>p([[px,y-r],[px+r,y],[px,y+r],[px-r,y],[px,y-r]],1.8,.9);
    const radius=68+32*(1-q);
    function chain(from,to,count=13){
      for(let i=0;i<count;i++){
        const u=i/(count-1),px=from[0]+(to[0]-from[0])*u,py=from[1]+(to[1]-from[1])*u+Math.sin(u*Math.PI)*10*(1-q);
        curve(v=>[px+Math.cos(v*TAU)*4,py+Math.sin(v*TAU)*6],14,1.5,.85);
      }
    }
    function gate(px,base,width,height){
      const top=base-height*q;
      p([[px-width,base],[px-width,top],[px+width,top],[px+width,base]],2.6,.8);
      p([[px-width-6,top-6],[px+width+6,top-6]],2,.7);
      for(const sign of [-1,1])p([[px+sign*width*.35,base],[px+sign*width*.35,top]],1.5,.65);
    }
    function blade(px,y,angle){
      const transform=([dx,dy])=>[px+dx*Math.cos(angle)-dy*Math.sin(angle),y+dx*Math.sin(angle)+dy*Math.cos(angle)];
      p([[-4,23],[-4,-15],[0,-30],[4,-15],[4,23],[-4,23]].map(transform),1.7,.9);
      p([[-10,16],[10,16]].map(transform),2,.9);
    }
    if(m==='anchors'){
      const nodes=front?[[-87,448],[87,448]]:[[-63,300],[63,300]];
      for(const [px,py] of nodes){gem(px,py,9);chain([px,py],[Math.sign(px)*(42+22*(1-q)),front?397:337]);}
      oval(0,366,radius*.8,19,.6);
    }else if(m==='weight'){
      if(!front){for(let j=0;j<3;j++){const top=282+j*12-45*(1-q);p([[-80+j*10,top+30],[-32,top],[0,top+12],[34,top-5],[80-j*10,top+30]],3,.7);}}
      else for(let j=0;j<5;j++){const y=315+j*28+Math.sin(t*.65+j)*2;oval(0,y,72-j*5,9,.6);}
      for(const sign of [-1,1])p([[sign*82,305],[sign*82,433],[sign*63,420]],2,.7);
    }else if(m==='tide'){
      for(let j=0;j<5;j++){
        const y=444-j*27*q;
        curve(u=>{const a=(front?0:Math.PI)+u*Math.PI;return[Math.cos(a)*(radius-j*3),y+Math.sin(a)*16+Math.sin(a*4-t*1.3+j)*4];},54,2.2,.7);
      }
      if(front)for(let j=0;j<12;j++){const z=j*2.4+t*.15;gem(Math.cos(z)*64,438-((t*17+j*13)%120),2);}
    }else if(m==='blades'){
      for(let j=0;j<8;j++){const z=j*TAU/8+t*.13;if((Math.sin(z)>=0)!==front)continue;
        blade(Math.cos(z)*radius,350+Math.sin(z)*45-45*(1-q),Math.cos(z)*.18);
      }oval(0,431,radius+4,18,.65);
    }else if(m==='judgment'){
      if(!front){p([[0,275],[0,321]],3,.9);p([[-67,298],[0,311],[67,324]],3,.9);
        for(const sign of [-1,1]){const y=311+sign*13;chain([sign*61,y],[sign*61,y+38],6);p([[sign*61-14,y+38],[sign*61,y+45],[sign*61+14,y+38]],2,.9);}}
      for(const sign of [-1,1])chain([sign*88,front?450:302],[sign*48,front?398:344]);
      oval(0,356,53+20*(1-q),12,.85);oval(0,421,58,11,.85);
      if(front){p([[-40,371],[-40,387],[40,387],[40,371]],3,.85);gem(0,383,7);}
    }else if(m==='wheel'){
      if(!front){for(let j=0;j<3;j++)curve(u=>[Math.cos(u*TAU)*(77+j*5),359+Math.sin(u*TAU)*(83+j*5)],72,1.5,.6);
        for(let j=0;j<12;j++){const z=j*TAU/12+t*.12;p([[Math.cos(z)*69,359+Math.sin(z)*75],[Math.cos(z)*88,359+Math.sin(z)*94]],2,.65);}}
      else for(let j=-2;j<=2;j++)curve(u=>[j*24+Math.sin(u*TAU)*12,444-(1-Math.cos(u*TAU))*35*q],36,2,.75);
    }else if(m==='ferry'){
      oval(0,440,86,16,.8);
      for(let j=0;j<6;j++){const z=j*TAU/6+t*.18;if((Math.sin(z)>=0)!==front)continue;
        const px=Math.cos(z)*radius,y=335+Math.sin(z)*37+Math.sin(t+j)*4;
        curve(u=>[px+Math.cos(u*TAU)*7,y+Math.sin(u*TAU)*12],28,2,.8);
        curve(u=>[px+Math.sin(u*5+t)*4,y+12+u*35],20,1.5,.7);
        p([[px,y+45],[px*.45,410]],1.4,.6);
      }
    }else if(m==='abyss'){
      for(let j=0;j<5;j++)curve(u=>{const z=(front?0:Math.PI)+u*Math.PI+t*.05;const r=radius+8-j*9;return[Math.cos(z)*r,438-j*19*q+Math.sin(z)*17];},50,2.2,.8-j*.08);
      for(let j=0;j<12;j++){const z=j*TAU/12+t*.2;if((Math.sin(z)>=0)!==front)continue;
        const r=85-((t*10+j*7)%42);p([[Math.cos(z)*r,420+Math.sin(z)*25],[Math.cos(z)*(r-9),428+Math.sin(z)*18]],2,.7);}
    }else if(m==='chess'){
      if(!front){for(let j=-3;j<=3;j++){p([[-84,421+j*8],[84,421+j*8]],1,.65);p([[j*25-12,393],[j*25+12,449]],1,.65);}}
      for(let j=0;j<6;j++){const z=j*TAU/6;if((Math.sin(z)>=0)!==front)continue;const px=Math.cos(z)*radius,base=419+Math.sin(z)*26;
        oval(px,base-25*q,11,5,.95);p([[px-9,base],[px-9,base-24*q],[px+9,base-24*q],[px+9,base]],2,.7);
        p([[px,base-24*q],[px*.5,345]],1.5,.6);}
    }else if(m==='vines'){
      for(let j=0;j<4;j++)curve(u=>{const a=(front?0:Math.PI)+u*Math.PI;return[Math.cos(a)*(radius-10),445-j*30*q+Math.sin(a)*17];},50,3,.75);
      for(const sign of [-1,1])curve(u=>[sign*(50+Math.sin(u*8+t*.6)*10),446-u*139*q],48,2.4,.8);
      if(front)for(let j=0;j<8;j++){const px=(j%2?1:-1)*(52+Math.sin(t*.6+j)*5),y=432-j*15*q;p([[px,y],[px+(j%2?12:-12),y-12],[px,y-7]],1.8,.75);}
    }else if(m==='totems'){
      for(let j=0;j<5;j++){const z=j*TAU/5;if((Math.sin(z)>=0)!==front)continue;const px=Math.cos(z)*radius,base=432+Math.sin(z)*17;
        gate(px,base,8,100);for(let k=0;k<3;k++)gem(px,base-(25+k*24)*q,5);}
      oval(0,437,radius,19,.8);
    }else if(m==='edict'){
      for(const sign of [-1,1]){const px=sign*radius;if(front){p([[px-7,307],[px+7,307],[px+7,435],[px-7,435],[px-7,307]],2.5,.9);
        for(let j=0;j<8;j++)p([[px-5,320+j*13],[px+(j%2?1:5),320+j*13]],1,.8);}
        else curve(u=>[px+Math.sin(u*TAU+t*.3)*5,300+u*135],40,3,.7);}
      if(front)for(let j=0;j<3;j++)p([[-radius,337+j*36],[radius,337+j*36]],1.7,.5);
    }else if(m==='gears'){
      for(let j=0;j<6;j++){const z=j*TAU/6+t*.12;if((Math.sin(z)>=0)!==front)continue;const px=Math.cos(z)*radius,y=363+Math.sin(z)*68;
        curve(u=>{const a=u*TAU+t*(j%2?-.4:.4),r=13+(Math.floor(u*24)%2)*4;return[px+Math.cos(a)*r,y+Math.sin(a)*r];},96,1.8,.85);
        p([[px,y],[px*.55,365+(y-365)*.55]],2,.75);gem(px,y,4);}
    }else if(m==='gates'){
      for(let j=0;j<9;j++){const z=j*TAU/9;if((Math.sin(z)>=0)!==front)continue;
        gate(Math.cos(z)*radius,426+Math.sin(z)*21,9,100+(j%3)*9);}
      oval(0,441,radius+8,17,.7);
    }else return false;
    return true;
  }
  window.DomainControlMotifs=Object.freeze({draw});
})();

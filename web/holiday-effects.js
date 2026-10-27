/* Costume-only choreography sampled from the existing settled attack clock. */
(() => {
  'use strict';
  const TAU=Math.PI*2,clamp=x=>Math.max(0,Math.min(1,x)),mix=(a,b,t)=>a+(b-a)*t;
  function snow(c,x,y,r,spin){
    c.save();c.translate(x,y);c.rotate(spin);c.strokeStyle='#e9fdff';c.lineWidth=Math.max(.8,r/8);
    c.beginPath();
    for(let i=0;i<6;i++){
      const a=i*TAU/6,dx=Math.cos(a),dy=Math.sin(a);
      c.moveTo(0,0);c.lineTo(dx*r,dy*r);
      for(const sign of [-1,1]){c.moveTo(dx*r*.58,dy*r*.58);c.lineTo(dx*r*.35-sign*dy*r*.25,dy*r*.35+sign*dx*r*.25);}
    }
    c.stroke();c.fillStyle='#90d9ff';c.fillRect(-r*.15,-r*.15,r*.3,r*.3);c.restore();
  }
  function pumpkin(c,x,y,r,spin){
    c.save();c.translate(x,y);c.rotate(spin);c.lineWidth=Math.max(.7,r/9);
    c.fillStyle='#ee812d';c.strokeStyle='#8b3f38';
    for(const off of [-.34,.34,0]){c.beginPath();c.ellipse(off*r,0,r*.58,r*.75,0,0,TAU);c.fill();c.stroke();}
    c.fillStyle='#678b59';c.fillRect(-r*.12,-r*.98,r*.25,r*.3);
    c.fillStyle='#382348';c.beginPath();c.moveTo(-r*.6,-r*.06);c.lineTo(-r*.23,-r*.3);c.lineTo(-r*.15,r*.05);c.closePath();c.fill();
    c.beginPath();c.moveTo(r*.6,-r*.06);c.lineTo(r*.23,-r*.3);c.lineTo(r*.15,r*.05);c.closePath();c.fill();
    c.beginPath();c.moveTo(-r*.4,r*.25);c.lineTo(0,r*.48);c.lineTo(r*.4,r*.25);c.stroke();c.restore();
  }
  function candy(c,x,y,r,spin,index){
    c.save();c.translate(x,y);c.rotate(spin);c.fillStyle=index%2?'#cb8bea':'#ffd179';
    for(const sign of [-1,1]){c.beginPath();c.moveTo(sign*r*.55,0);c.lineTo(sign*r*1.15,-r*.55);c.lineTo(sign*r*1.15,r*.55);c.closePath();c.fill();}
    c.fillStyle=index%2?'#8555be':'#e78440';c.fillRect(-r*.6,-r*.45,r*1.2,r*.9);
    c.strokeStyle='#fff1d5';c.lineWidth=Math.max(1,r*.16);c.beginPath();c.moveTo(-r*.3,-r*.4);c.lineTo(r*.2,r*.4);c.moveTo(r*.15,-r*.4);c.lineTo(r*.6,r*.3);c.stroke();c.restore();
  }
  function bat(c,x,y,r,spin,flap){
    c.save();c.translate(x,y);c.rotate(spin);c.scale(1,.55+.45*flap);
    c.fillStyle='#35234c';c.strokeStyle='#cf89f1';c.lineWidth=Math.max(.8,r*.055);
    c.beginPath();c.moveTo(0,-r*.18);
    for(const d of [1,-1]){
      c.bezierCurveTo(d*r*.4,-r*.9,d*r*1.25,-r*.75,d*r*1.6,-r*.3);
      c.quadraticCurveTo(d*r*.9,-r*.45,d*r*.88,r*.3);
      c.quadraticCurveTo(d*r*.5,-r*.05,d*r*.38,r*.48);
      c.lineTo(0,r*.16);c.lineTo(0,-r*.18);
    }
    c.fill();c.stroke();c.fillStyle='#6c397e';c.beginPath();c.ellipse(0,0,r*.19,r*.42,0,0,TAU);c.fill();
    c.beginPath();c.moveTo(-r*.18,-r*.2);c.lineTo(-r*.22,-r*.55);c.lineTo(0,-r*.32);c.lineTo(r*.22,-r*.55);c.lineTo(r*.18,-r*.2);c.fill();
    c.fillStyle='#ffbb7c';c.fillRect(-r*.13,-r*.2,r*.08,r*.08);c.fillRect(r*.05,-r*.2,r*.08,r*.08);c.restore();
  }
  function halo(c,x,y,r,p,alpha){
    c.save();c.globalAlpha=clamp(alpha);
    const g=c.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,p[2]+'cc');g.addColorStop(.24,p[1]+'88');g.addColorStop(.6,p[0]+'40');g.addColorStop(1,p[0]+'00');
    c.fillStyle=g;c.fillRect(x-r,y-r,2*r,2*r);c.restore();
  }
  function ribbon(c,points,p,width,alpha){
    c.save();c.lineJoin='round';c.lineCap='round';
    for(const [color,w,opacity] of [[p[0],width*5,.12],[p[1],width*2,.45],[p[2],width*.5,.85]]){
      c.strokeStyle=color;c.lineWidth=w;c.globalAlpha=clamp(alpha*opacity);c.beginPath();
      points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.stroke();
    }c.restore();
  }
  function ring(c,x,y,rx,ry,angle,p,alpha,width){
    ribbon(c,Array.from({length:49},(_,i)=>{const z=i/48*TAU,dx=Math.cos(z)*rx,dy=Math.sin(z)*ry;return[x+dx*Math.cos(angle)-dy*Math.sin(angle),y+dx*Math.sin(angle)+dy*Math.cos(angle)];}),p,width,alpha);
  }
  function theme(actor){return ['christmas','halloween','halloween-bats'].includes(actor?.holiday_effect)?actor.holiday_effect:null;}
  function draw(s,m,state,{context,projectClip}){
    const style=theme(m.attacker?.actor),r=state.round;
    if(!style||!r)return false;
    const k=s.scale,a=m.attacker,o=a.hand,t=state.time,x=m.contact,y=m.hitY;
    const back=context(s.rear),front=context(s.front),flight=context(s.projectile);
    const ice=style==='christmas',bats=style==='halloween-bats';
    const palette=ice?['#3189d6','#87e9ff','#f3ffff']:bats?['#582a8d','#c879e8','#ffdfba']:['#934ed0','#ff9b42','#fff1bd'];
    const particle=(c,px,py,size,angle,i,alpha)=>{
      c.save();c.globalAlpha=clamp(alpha);
      if(ice)snow(c,px,py,size,angle);
      else if(bats)bat(c,px,py,size,Math.sin(angle)*.25,(Math.sin(t*18+i*2)+1)/2);
      else if(i%5===0)pumpkin(c,px,py,size*1.2,angle*.25);
      else candy(c,px,py,size*.8,angle,i);
      c.restore();
    };
    const charge=clamp((t-r.start)/.45)*(1-clamp((t-r.contacts[0]+.85)/.35));
    if(charge>0){
      halo(back,...o,95*k,palette,charge*.65);
      ring(back,...o,58*k,34*k,t*.8,palette,charge*.8,2*k);
      ring(back,...o,42*k,55*k,-t*.8,palette,charge*.6,1.2*k);
      if(ice)particle(back,...o,32*k,t*.7,0,charge*.85);
      for(let i=0;i<16;i++){
        const z=i*2.39996+(t-r.start)*1.8,rad=(32+i%4*11)*k;
        particle(back,o[0]+Math.cos(z)*rad,o[1]+Math.sin(z)*rad*.7,(5+i%4*2)*k,z,i,charge*.9);
      }
    }
    for(const contact of r.contacts){
      const age=t-contact,q=clamp((age+.85)/.85);
      if(age>=-.85&&age<0)projectClip(flight,m,s,()=>{
        const head=[mix(o[0],x,q),mix(o[1],y,q)];
        halo(flight,...head,76*k,palette,.7);
        for(let j=0;j<5;j++){
          const pts=[];
          for(let i=0;i<=32;i++){
            const u=Math.max(0,q-.42)+Math.min(q,.42)*i/32,z=i/32*8-t*9+j*TAU/5;
            pts.push([mix(o[0],x,u),mix(o[1],y,u)+Math.sin(z)*Math.sin(i/32*Math.PI)*(28+j*4)*k]);
          }ribbon(flight,pts,palette,(j%2?2:3)*k,.8);
        }
        for(let i=0;i<30;i++){
          const u=q-i*.018;if(u<0)continue;
          const bend=Math.sin(u*Math.PI),px=mix(o[0],x,u),py=mix(o[1],y,u)+Math.sin(i*2.4+t*5)*bend*38*k;
          particle(flight,px,py,(bats?9+i%4*3:6+i%4*2)*k,t*2+i,i,1-i/38);
        }
        // Large readable leading motif; flapping bats replace every pumpkin/candy in the male style.
        particle(flight,...head,(bats?24:30)*k,t*2,0,1);
        if(ice){ring(flight,...head,41*k,41*k,t,palette,.85,1.5*k);particle(flight,...head,22*k,-t*3,1,.9);}
      });
      if(age>=0&&age<=1.05){
        const u=age/1.05,fade=(1-u)**1.4,expand=1-(1-u)**3;
        halo(back,x,y,(65+expand*100)*k,palette,fade*.8);
        ring(front,x,y,(15+expand*105)*k,(24+expand*82)*k,u*.4,palette,fade,3*k);
        ring(front,x,y,(8+expand*80)*k,(12+expand*112)*k,-u*.5,palette,fade*.8,1.6*k);
        if(ice)particle(front,x,y,(40+expand*30)*k,u,0,fade*.8);
        for(let i=0;i<36;i++){
          const z=i*2.39996,rad=(10+expand*(50+i%6*14))*k;
          const px=x+Math.cos(z)*rad,py=y+Math.sin(z)*rad*.75+u*u*34*k;
          ribbon(front,[[x+Math.cos(z)*rad*.5,y+Math.sin(z)*rad*.4],[px,py]],palette,1.3*k,fade*.65);
          particle(front,px,py,(bats?8+i%4*2:5+i%4*2)*k,z+u*3,i,fade);
        }
      }
    }
    return true;
  }
  window.HolidayEffects=Object.freeze({draw,theme});
})();

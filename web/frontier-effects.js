/* Pure cosmetic revolver shot, sampled from the existing settled contact clock. */
(() => {
  'use strict';
  const TAU=Math.PI*2,clamp=x=>Math.max(0,Math.min(1,x)),mix=(a,b,t)=>a+(b-a)*t;
  function stroke(c,points,color,width,alpha=1){
    c.save();c.globalAlpha=clamp(alpha);c.strokeStyle=color;c.lineWidth=width;c.lineCap='round';
    c.beginPath();points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.stroke();c.restore();
  }
  function glow(c,x,y,r,alpha){
    c.save();c.globalAlpha=clamp(alpha);
    const g=c.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,'#fffbe4');
    g.addColorStop(.2,'#ffd480aa');g.addColorStop(.6,'#e7803233');g.addColorStop(1,'#e7803200');
    c.fillStyle=g;c.fillRect(x-r,y-r,r*2,r*2);c.restore();
  }
  function draw(s,m,state,{context,projectClip}){
    if(m.attacker?.actor.cast_effect!=='revolver'||!state.round)return false;
    const k=s.scale,a=m.attacker,[ox,oy]=a.hand,dir=a.dir,t=state.time;
    const shot=context(s.projectile),front=context(s.front),rear=context(s.rear);
    for(const contact of state.round.contacts){
      const fired=t-(contact-.1),age=t-contact;
      // The painted release pose starts 100 ms before contact; no homing orb or magic charge.
      if(fired>=0&&fired<.18){
        const fade=1-fired/.18;
        glow(rear,ox,oy,65*k,fade*.8);
        front.save();front.translate(ox,oy);front.scale(dir,1);front.globalAlpha=fade;
        front.fillStyle='#ffb53f';front.beginPath();front.moveTo(0,-4*k);
        for(const [x,y]of [[18,-15],[15,-4],[54,0],[15,4],[18,15],[0,4]])front.lineTo(x*k,y*k);
        front.closePath();front.fill();
        front.fillStyle='#fffbed';front.beginPath();front.moveTo(0,-3*k);front.lineTo(35*k,0);front.lineTo(0,3*k);front.fill();front.restore();
      }
      if(fired>=0&&age<0){
        const q=clamp(fired/.1),x=mix(ox,m.contact,q),y=mix(oy,m.hitY,q);
        projectClip(shot,m,s,()=>{
          const tail=Math.max(0,q-.38),line=[[mix(ox,m.contact,tail),mix(oy,m.hitY,tail)],[x,y]];
          stroke(shot,line,'#e8a253',7*k,.35);stroke(shot,line,'#fff3c2',2*k);
          glow(shot,x,y,10*k,.65);
        });
      }
      if(fired>=0&&fired<.65){
        const q=fired/.65;
        // Revolvers retain spent cases in the cylinder; only powder smoke is emitted.
        for(let i=0;i<5;i++){
          rear.save();rear.globalAlpha=(1-q)*.18;rear.fillStyle='#c6bba7';
          rear.beginPath();rear.ellipse(ox+dir*(8+q*(24+i*4))*k,oy-(q*25+Math.sin(i*2)*5)*k,
            (3+q*(12+i*2))*k,(3+q*9)*k,i*.4,0,TAU);rear.fill();rear.restore();
        }
      }
      if(age>=0&&age<.6){
        const q=age/.6,fade=(1-q)**2,x=m.contact,y=m.hitY;
        glow(rear,x,y,(22+q*55)*k,fade*.8);
        front.save();front.globalAlpha=fade;front.strokeStyle='#ffdf9b';front.lineWidth=2*k;
        front.beginPath();front.ellipse(x,y,(5+q*48)*k,(8+q*58)*k,0,0,TAU);front.stroke();front.restore();
        for(let i=0;i<22;i++){
          const z=i*2.39996,rad=(8+q*(25+i%5*12))*k,tail=rad-(5+(1-q)*12)*k;
          stroke(front,[[x+Math.cos(z)*tail,y+Math.sin(z)*tail],[x+Math.cos(z)*rad,y+Math.sin(z)*rad]],
            i%3?'#ffd78a':'#fff7dc',(i%3?1:2)*k,fade);
        }
      }
    }
    return true;
  }
  window.FrontierEffects=Object.freeze({draw});
})();

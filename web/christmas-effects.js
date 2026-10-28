/* Painted snow animation; all phases follow the settled contact clock. */
(() => {
  'use strict';
  const sheet='/assets/pixel/holiday/christmas-keyframes.png';
  const sheetFor=actor=>actor?.holiday_effect==='christmas'?sheet:undefined;
  const clamp=x=>Math.max(0,Math.min(1,x)),mix=(a,b,t)=>a+(b-a)*t;
  const phases=[['charge',-1.9,-.7,0],['travel',-.7,0,4],['impact',0,.45,8],['dissipate',.45,1.2,12]];
  function sample(age){
    const phase=phases.find(([,a,b])=>age>=a&&age<b);if(!phase)return null;
    const [name,a,b,offset]=phase,q=(age-a)/(b-a),frame=q*4,index=Math.min(3,Math.floor(frame));
    return {phase:name,q,index:offset+index,next:offset+Math.min(3,index+1),blend:frame%1};
  }
  function paint(c,im,index,x,y,width,dir,alpha){
    const w=im.width/4,h=im.height/4,height=width*h/w;
    c.save();c.globalAlpha=clamp(alpha);c.translate(x,y);c.scale(dir,1);c.imageSmoothingEnabled=true;
    c.drawImage(im,index%4*w,Math.floor(index/4)*h,w,h,-width*.5,-height*.5,width,height);c.restore();
  }
  function draw(s,m,state,{context,projectClip,image}){
    if(!sheetFor(m.attacker?.actor)||!state.round)return false;
    const im=image?.(sheet);if(!im)return false; // Retain the existing snow choreography as fallback.
    const a=m.attacker,[ox,oy]=a.hand,k=s.scale;
    for(const contact of state.round.contacts){
      const f=sample(state.time-contact);if(!f)continue;
      let x=m.contact,y=m.hitY,width=360*k,alpha=1;
      if(f.phase==='charge'){
        x=ox;y=oy;width=mix(95,230,f.q)*k;alpha=clamp(f.q*5);
      }else if(f.phase==='travel'){
        const q=f.q*f.q*(3-2*f.q);
        x=mix(ox,m.contact,q);y=mix(oy,m.hitY,q);width=mix(210,310,q)*k;
      }else if(f.phase==='dissipate'){
        y+=f.q*20*k;alpha=(1-f.q)**.7;
      }
      y=Math.min(y,(s.ground??Infinity)-width*.75*.39);
      const c=context(f.phase==='charge'?s.rear:f.phase==='travel'?s.projectile:s.front);
      const render=()=>{
        paint(c,im,f.index,x,y,width,a.dir,alpha*(1-f.blend));
        paint(c,im,f.next,x,y,width,a.dir,alpha*f.blend);
      };
      if(f.phase==='travel')projectClip(c,m,s,render);else render();
    }
    return true;
  }
  window.ChristmasEffects=Object.freeze({draw,sample,sheet,sheetFor});
})();

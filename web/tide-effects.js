/* Painted fluid keyframes, sampled only from the settled combat contact clock. */
(() => {
  'use strict';
  const sheet='/assets/pixel/tide/water-keyframes.png';
  const clamp=x=>Math.max(0,Math.min(1,x)),mix=(a,b,t)=>a+(b-a)*t;
  // Four genuinely different paintings per phase. No independent animation timer.
  const phases=[['charge',-1.15,-.6,0],['travel',-.6,0,4],
    ['impact',0,.4,8],['dissipate',.4,.95,12]];
  function sample(age){
    const phase=phases.find(([,start,end])=>age>=start&&age<end);
    if(!phase)return null;
    const [name,start,end,offset]=phase,q=(age-start)/(end-start),frame=q*4;
    return {phase:name,q,index:offset+Math.min(3,Math.floor(frame)),
      next:Math.min(15,offset+Math.floor(frame)+1),blend:frame%1};
  }
  function paint(c,im,index,x,y,width,dir,alpha){
    const w=im.width/4,h=im.height/4,height=width*h/w;
    c.save();c.globalAlpha=clamp(alpha);c.translate(x,y);c.scale(dir,1);
    c.imageSmoothingEnabled=true;
    // Right-hand crest/contact and water baseline share one stable atlas anchor.
    c.drawImage(im,index%4*w,Math.floor(index/4)*h,w,h,-width*.72,-height*.55,width,height);
    c.restore();
  }
  function draw(s,m,state,{context,projectClip,image}){
    if(m.attacker?.actor.cast_effect!=='tidal_wave'||!state.round)return false;
    const im=image?.(sheet);if(!im)return true;
    const a=m.attacker,[ox,oy]=a.hand,k=s.scale;
    for(const contact of state.round.contacts){
      const age=state.time-contact,frame=sample(age);if(!frame)continue;
      let x=m.contact,y=m.hitY,width=340*k,alpha=1;
      if(frame.phase==='charge'){
        x=ox;y=oy;width=mix(100,220,frame.q)*k;alpha=clamp(frame.q*4);
      }else if(frame.phase==='travel'){
        x=mix(ox,m.contact,frame.q);y=mix(oy,m.hitY,frame.q);width=mix(220,340,frame.q)*k;
      }else if(frame.phase==='dissipate')alpha=1-frame.q;
      // Low creatures have a lower hit point: keep the painted water base above
      // the battlefield floor instead of letting its lower half fall off-canvas.
      y=Math.min(y,(s.ground??Infinity)-width*.75*.41);
      const c=context(frame.phase==='travel'?s.projectile:s.front);
      const render=()=>{
        // Crossfades soften transitions; each fluid silhouette is separately painted.
        paint(c,im,frame.index,x,y,width,a.dir,alpha*(1-frame.blend));
        paint(c,im,frame.next,x,y,width,a.dir,alpha*frame.blend);
      };
      if(frame.phase==='travel')projectClip(c,m,s,render);else render();
    }
    return true;
  }
  window.TideEffects=Object.freeze({draw,sample,sheet});
})();

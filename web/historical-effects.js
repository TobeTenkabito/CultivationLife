/* Painted costume spells; pure sampling of the existing combat contact clock. */
(() => {
  'use strict';
  const specs=Object.freeze({
    nobunaga_command:{sheet:'/assets/pixel/historical/nobunaga-fx.png',width:350},
    seimei_lunar:{sheet:'/assets/pixel/historical/seimei-fx.png',width:330},
    diaochan_phoenix:{sheet:'/assets/pixel/diaochan/diaochan-fx.png',width:380}
  });
  const clamp=x=>Math.max(0,Math.min(1,x)),mix=(a,b,t)=>a+(b-a)*t;
  const phases=[['charge',-1.4,-.65,0],['travel',-.65,0,3],
    ['impact',0,.42,6],['dissipate',.42,1.1,9]];
  const sheetFor=actor=>specs[actor?.cast_effect]?.sheet;
  function sample(age){
    const phase=phases.find(([,start,end])=>age>=start&&age<end);
    if(!phase)return null;
    const [name,start,end,offset]=phase,q=(age-start)/(end-start),f=q*3,i=Math.min(2,Math.floor(f));
    return {phase:name,q,index:offset+i,next:offset+Math.min(2,i+1),blend:f%1};
  }
  function paint(c,im,index,x,y,width,dir,alpha){
    const w=im.width/4,h=im.height/3,height=width*h/w;
    c.save();c.globalAlpha=clamp(alpha);c.translate(x,y);c.scale(dir,1);
    c.imageSmoothingEnabled=true;
    c.drawImage(im,index%4*w,Math.floor(index/4)*h,w,h,-width*.5,-height*.5,width,height);
    c.restore();
  }
  function draw(s,m,state,{context,projectClip,image}){
    const spec=specs[m.attacker?.actor.cast_effect];
    if(!spec||!state.round)return false;
    const im=image?.(spec.sheet);
    // A missing optional effect falls back to the existing spell instead of hiding attacks.
    if(!im)return false;
    const a=m.attacker,[ox,oy]=a.hand,k=s.scale;
    for(const contact of state.round.contacts){
      const frame=sample(state.time-contact);if(!frame)continue;
      let x=m.contact,y=m.hitY,width=spec.width*k,alpha=1;
      if(frame.phase==='charge'){
        x=ox;y=oy;width=mix(100,200,frame.q)*k;alpha=clamp(frame.q*5);
      }else if(frame.phase==='travel'){
        const q=frame.q*frame.q*(3-2*frame.q);
        x=mix(ox,m.contact,q);y=mix(oy,m.hitY,q);width=mix(180,spec.width*.8,q)*k;
      }else if(frame.phase==='dissipate')alpha=1-frame.q;
      y=Math.min(y,(s.ground??Infinity)-width*.75*.4);
      const c=context(frame.phase==='charge'?s.rear:frame.phase==='travel'?s.projectile:s.front);
      const render=()=>{
        paint(c,im,frame.index,x,y,width,a.dir,alpha*(1-frame.blend));
        paint(c,im,frame.next,x,y,width,a.dir,alpha*frame.blend);
      };
      if(frame.phase==='travel')projectClip(c,m,s,render);else render();
    }
    return true;
  }
  window.HistoricalEffects=Object.freeze({draw,sample,sheetFor});
})();

/* Authored manual accents, driven only by settled paid receipts. */
(() => {
  'use strict';
  const kinds={TECH_LINLAN_DEMON:'wind',TECH_HUNDRED_THOUSAND_FROST:'frost'};
  function paid(row,owner){
    const events=row?.voisinage?.technique_effects?.events;
    if(!Array.isArray(events))return [];
    return [...new Set(events.filter(e=>e.owner===owner&&e.event==='paid'&&Number.isFinite(e.amount)&&e.amount>0)
      .map(e=>kinds[e.technique]).filter(Boolean))].slice(0,2);
  }
  function draw(c,s,m,state){
    const r=state.round;if(!r?.techniqueFx?.length||r.presentationOnly)return;
    const actor=m.participants.find(a=>a.side===r.side&&a.slot===r.actorIndex);
    if(!actor)return;
    const age=state.time-r.start;if(age<0||age>2.4)return;
    const reduced=document.documentElement.dataset.motion==='reduced'||matchMedia('(prefers-reduced-motion: reduce)').matches;
    const phase=reduced?.5:age/2.4,scale=s.scale;
    c.save();c.translate(actor.x,actor.y-85*scale);c.scale(scale,scale);
    c.globalAlpha=.55*(reduced?1:Math.sin(Math.PI*Math.min(1,age/2.4)));c.lineWidth=2;
    for(const kind of r.techniqueFx){
      if(kind==='wind'){
        for(let i=0;i<3;i++){
          c.save();c.rotate((reduced?0:phase*2)+i*Math.PI*2/3);
          c.strokeStyle=i===1?'#b495dc':'#70d8c8';c.beginPath();c.ellipse(0,0,55+i*12,85+i*8,0,.2,2.8);c.stroke();c.restore();
        }
        c.fillStyle='#91d9cf';
        for(const side of [-1,1]){c.beginPath();c.ellipse(side*42,-25,8,12,0,0,Math.PI*2);c.fill();c.beginPath();c.moveTo(side*42,-12);c.lineTo(side*65,65);c.lineTo(side*22,65);c.closePath();c.fill();}
      }else{
        c.strokeStyle='#8dd9f1';c.beginPath();c.ellipse(0,62,80,22,0,0,Math.PI*2);c.stroke();
        for(let i=0;i<10;i++){
          const a=i*Math.PI/5+(reduced?0:phase*.35);c.save();c.translate(Math.cos(a)*73,Math.sin(a)*44);c.rotate(a+Math.PI/2);
          c.fillStyle=i%2?'#c6f4ff':'#7bc2eb';c.beginPath();c.moveTo(0,-31);c.lineTo(4,-8);c.lineTo(0,7);c.lineTo(-4,-8);c.closePath();c.fill();
          c.strokeStyle='#dffaff';c.beginPath();c.moveTo(-7,7);c.lineTo(7,7);c.moveTo(0,7);c.lineTo(0,17);c.stroke();c.restore();
        }
      }
    }
    c.restore();
  }
  window.TechniqueFx={paid,draw};
})();

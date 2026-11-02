/* Body-born wisps only. No gameplay, fetch, RNG, timers or persistent state. */
window.DivineLightVisuals = (() => {
  'use strict';
  const rows = [
    {id:'kun',name:'坤元缃光',color:'#e5b75b',glow:'#c59a45',period:8.4},
    {id:'zhen',name:'震合缥光',color:'#70c8b0',glow:'#a0ddce',period:7.7},
    {id:'kan',name:'坎道玄光',color:'#667da9',glow:'#a7b9d8',period:10.2},
    {id:'li',name:'离上朱光',color:'#e98270',glow:'#efb296',period:7.1},
    {id:'qian',name:'乾古素光',color:'#eee9dc',glow:'#9daeb8',period:11.3}
  ];
  const ids=value=>rows.filter(row=>Array.isArray(value)&&value.length<=5&&value.includes(row.id)).map(row=>row.id);
  const clamp=x=>Math.max(0,Math.min(1,x));
  const smooth=x=>{x=clamp(x);return x*x*(3-2*x);};
  let serial=0;

  // An open, rising curl around the body. Depth selects its compositing layer.
  function point(index,u,box,time=0,portrait=false) {
    const turn=index*1.39+u*5.1;
    const breath=Math.sin(time*.48+index*1.7)*.012;
    const radius=box.w*((portrait?.43:.40)+Math.sin(u*Math.PI)*.055+breath);
    const sway=Math.sin(u*6.4+index*.9+time*.22)*box.w*.025;
    return {x:box.x+Math.cos(turn)*radius+sway,
      y:box.y+box.h*(.44-u*.88)+Math.sin(turn)*box.h*.035,
      depth:Math.sin(turn),u};
  }
  function frontFade(u,portrait=false) {
    return 1-smooth((u-(portrait?.36:.62))/(portrait?.20:.17));
  }
  function strip(c,a,b,width,color,alpha) {
    if(alpha<=.001)return;
    const dx=b.x-a.x,dy=b.y-a.y,length=Math.hypot(dx,dy)||1;
    const nx=-dy/length*width,ny=dx/length*width;
    c.globalAlpha=alpha;c.fillStyle=color;c.beginPath();
    c.moveTo(a.x+nx,a.y+ny);c.lineTo(b.x+nx,b.y+ny);
    c.lineTo(b.x-nx,b.y-ny);c.lineTo(a.x-nx,a.y-ny);c.closePath();c.fill();
  }
  function draw(c,lights,box,time,front,muted=false) {
    const selected=ids(lights);if(!selected.length)return;
    const density=Math.min(1,1.75/Math.sqrt(selected.length));
    const strength=Math.min(1,density*1.2)*(muted?.22:1)*(box.opacity??1);
    c.save();
    for(const [index,row] of rows.entries()) {
      if(!selected.includes(row.id))continue;
      for(let strand=0;strand<2;strand++) {
        const head=(time/row.period+index*.173+strand*.5)%1;
        const tail=.24,steps=30;
        for(let step=0;step<steps;step++) {
          const s=step/steps,u=head-tail+s*tail,next=u+tail/steps;
          if(u<0||next>1)continue;
          const a=point(index,u,box,time),b=point(index,next,box,time);
          if(((a.depth+b.depth)>=0)!==front)continue;
          const taper=Math.sin(Math.PI*(s+.5/steps));
          const life=smooth(u/.13)*(1-smooth((u-.78)/.22));
          const veil=front?frontFade(u):.74;
          const alpha=life*veil*taper*strength*(.83+.17*Math.sin(time*.65+index));
          const width=Math.max(.45,box.w*.009)*Math.pow(taper,.7);
          strip(c,a,b,width*3.2,row.glow,alpha*.14);
          strip(c,a,b,width*1.65,row.color,alpha*.32);
          strip(c,a,b,width*.95,row.color,alpha*.95);
        }
      }
    }
    c.restore();
  }

  const ns='http://www.w3.org/2000/svg';
  const svgNode=(tag,attrs={})=>{const n=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);return n;};
  function segments(index,portrait) {
    const parts=[];let current=null,distance=0,previous=null;
    for(let i=0;i<=96;i++) {
      const p=point(index,i/96,{x:50,y:56,w:94,h:108},0,portrait);
      if(previous)distance+=Math.hypot(p.x-previous.x,p.y-previous.y);
      const front=p.depth>=0;
      if(!current||current.front!==front) {
        current={front,start:distance,points:previous?[previous,p]:[p]};parts.push(current);
      }else current.points.push(p);
      previous=p;
    }
    return {parts,length:distance};
  }
  function mount(host,value) {
    if(!host)return;
    const selected=ids(value),key=selected.join(',');
    if(host.dataset.divineLights===key)return;
    host.querySelectorAll(':scope>.divine-light-orbits').forEach(n=>n.remove());
    host.dataset.divineLights=key;host.classList.toggle('divine-light-host',!!selected.length);
    if(!selected.length)return;
    const portrait=host.matches('.pixel-portrait-frame,.npc-art-avatar,.npc-light-portrait,.npc-event-participants button');
    const ticket=++serial,density=Math.min(1,1.75/Math.sqrt(selected.length));
    for(const front of [false,true]) {
      const svg=svgNode('svg',{viewBox:'0 0 100 112',preserveAspectRatio:'none','aria-hidden':'true'});
      svg.classList.add('divine-light-orbits',front?'divine-light-front':'divine-light-rear');
      const defs=svgNode('defs');svg.append(defs);
      for(const [index,row] of rows.entries()) {
        if(!selected.includes(row.id))continue;
        const gradientId=`divine-wisp-${ticket}-${index}-${Number(front)}`;
        const gradient=svgNode('linearGradient',{id:gradientId,gradientUnits:'userSpaceOnUse',x1:0,y1:104,x2:0,y2:8});
        for(const [offset,opacity] of [[0,0],[.13,.8],[.35,1],[.50,front?.48:.85],[front?(portrait?.61:.80):.93,0],[1,0]])
          gradient.append(svgNode('stop',{offset,'stop-color':row.color,'stop-opacity':opacity}));
        defs.append(gradient);
        const group=svgNode('g',{opacity:density*(front?.88:.82)});
        if(front)group.dataset.light=row.id;
        const geometry=segments(index,portrait),travel=geometry.length/2;
        group.style.setProperty('--light-period',row.period/2+'s');
        group.style.setProperty('--light-offset',(-index*1.37)+'s');
        group.style.setProperty('--light-travel',travel.toFixed(3)+'px');
        for(const part of geometry.parts.filter(p=>p.front===front)) {
          const d=part.points.map((p,i)=>(i?'L':'M')+p.x.toFixed(2)+' '+p.y.toFixed(2)).join(' ');
          for(const glow of [true,false]) {
            const path=svgNode('path',{d,fill:'none',stroke:`url(#${gradientId})`,
              'stroke-width':glow?'5.2':'1.05','stroke-linecap':'round','stroke-linejoin':'round',
              opacity:glow?'.10':'.94','stroke-dasharray':`${travel*.25} ${travel*.75}`});
            path.style.setProperty('--light-start',part.start.toFixed(3)+'px');group.append(path);
          }
        }
        svg.append(group);
      }
      svg.dataset.names=rows.filter(row=>selected.includes(row.id)).map(row=>row.name).join('、');host.append(svg);
    }
  }
  function visibility(){document.documentElement.toggleAttribute('data-lights-paused',document.hidden);}
  document.addEventListener('visibilitychange',visibility);visibility();
  return Object.freeze({ids,draw,mount,names:value=>rows.filter(row=>ids(value).includes(row.id)).map(row=>row.name)});
})();

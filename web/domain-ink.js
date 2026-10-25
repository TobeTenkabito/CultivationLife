/* Authored hollow contours, animated from replay time; no world-state ports. */
(() => {
  'use strict';
  const TAU=Math.PI*2;
  // Staggered perspective beds: dense small blooms at the horizon, larger ones nearby.
  const flowers=Array.from({length:5},(_,depth)=>{
    const count=25-depth*3;
    return Array.from({length:count},(_,column)=>{
      const seed=depth*37+column,step=1.92/count;
      return {root:-.96+(column+.5+Math.sin(seed*2.4)*.19)*step,
        base:[-.05,.20,.45,.70,.98][depth]+Math.sin(seed*1.7)*.026,
        height:[.22,.30,.40,.54,.72][depth]*(1+Math.sin(seed*3.1)*.09),
        depth,seed};
    });
  }).flat();
  function flowerPose(index,time){
    const p=flowers[index],phase=p.root*2.3+p.depth*.65;
    const wind=p.height*(.045*Math.sin(time*.85+phase)+.013*Math.sin(time*1.33+p.seed));
    return {...p,wind,turn:Math.sin(time*.17+phase)*.11};
  }
  function clockPose(time){return {outer:time*.08,inner:-time*.12,hand:time*.42,slow:time*.09};}
  function draw({c,style:s,g,time:t,world,line,front,opacity}){
    const image=DomainMotifs.bitmap(s);if(!image)return false;
    const mode=s.scene.motion,alpha=opacity*(.50+.18*(s.density??65)/100);
    const curve=(fn,n=64,w=1,a=.4)=>line(Array.from({length:n+1},(_,i)=>world(...fn(i/n))),w,a);
    if(front)return true; // All architectural strokes stay behind the actors.
    c.save();c.globalAlpha=alpha;c.imageSmoothingEnabled=true;
    if(mode==='flowers'){
      // Each plant is independent; the lower stem never leaves its root.
      for(let j=0;j<flowers.length;j++){
        const p=flowerPose(j,t),bottom=world(p.root,p.base),height=g.ry*p.height,width=height*image.width/image.height;
        c.globalAlpha=alpha*(.58+p.depth*.105);
        const neck=.53,headH=height*neck,stemH=height-headH;
        const wind=p.wind*g.rx;
        // Narrow strips bend the stem quadratically, with zero displacement at ground.
        for(let k=0;k<12;k++){
          const u=k/12,v=(k+1)/12,sy=image.height*(neck+(1-neck)*u),sh=image.height*(1-neck)/12;
          const bend=wind*Math.max(0,(.80-u)/.80)**2;
          c.drawImage(image,0,sy,image.width,sh,bottom[0]-width/2+bend,bottom[1]-stemH+stemH*u,width,stemH*(v-u)+.4);
        }
        // Blossom rotates gently about its neck, which follows the bent stem.
        c.save();c.translate(bottom[0]+wind,bottom[1]-stemH);c.rotate(p.turn);
        c.drawImage(image,0,0,image.width,image.height*neck,-width/2,-headH,width,headH+.4);c.restore();
      }
    }else{
      const width=g.rx*1.88,height=g.ry*1.82;
      const drift=mode==='drift'?Math.sin(t*.24)*g.rx*.018:0;
      c.translate(g.cx+drift,g.cy-g.ry*.06);
      if(mode==='bloom'||mode==='pulse'){const q=1+Math.sin(t*.65)*.018;c.scale(q,q);}
      if(mode==='wheel')c.rotate(t*.026);
      // Strip displacement is continuous, bounded, and sampled directly at the playhead.
      for(let j=0;j<32;j++){
        const v=j/32,sy=Math.floor(v*image.height),end=Math.floor((j+1)/32*image.height);
        let dx=0,dy=0;
        if(['tide','flame','drift','scroll'].includes(mode))dx=Math.sin(v*TAU*1.5+t*(mode==='flame'?.95:.45))*g.rx*.012;
        if(['sway','wings','lantern'].includes(mode))dx=Math.sin(t*.6+v*.7)*g.rx*.025*(1-v)**2;
        if(mode==='fold')dx=Math.sin(t*.4+Math.floor(v*4))*g.rx*.009;
        if(mode==='palace')dy=Math.sin(t*.35)*g.ry*.015;
        if(mode==='blades')dy=Math.sin(t*.6)*g.ry*.035;
        c.drawImage(image,0,sy,image.width,end-sy,-width/2+dx,-height/2+v*height+dy,width,height/32+.35);
      }
    }
    c.restore();
    if(mode==='clock'){
      const p=clockPose(t),face=s.scene.clock||[.5,.5,.2];
      const width=g.rx*1.88,height=g.ry*1.82;
      const cx=g.cx+(face[0]-.5)*width,cy=g.cy-g.ry*.06+(face[1]-.5)*height,radius=width*face[2];
      const dial=(a,r)=>[cx+Math.cos(a)*radius*r,cy+Math.sin(a)*radius*r];
      // Moving rings/hands are separate from Zhulong's authored outline.
      for(let k=0;k<60;k++){
        const a=k*TAU/60+p.outer,r=k%5===0?.95:.90;
        line([dial(a,.83),dial(a,r)],k%5===0?1.7:.8,.5);
      }
      for(let k=0;k<8;k++)line(Array.from({length:25},(_,j)=>dial(p.inner+k*TAU/8+j/24*.45,.72)),1.4,.4);
      for(const [a,r]of [[p.hand,.74],[p.slow,.52]])line([dial(a,-.1),dial(a,r)],2,.7);
    }else if(mode==='orbit'){
      for(let j=0;j<7;j++){
        const a=t*(.10+j*.009)+j*TAU/7,[x,y]=world(Math.cos(a)*(.42+(j%3)*.13),Math.sin(a)*(.4+(j%2)*.23)-.05);
        c.save();c.fillStyle=s.light;c.globalAlpha=opacity*.6;c.fillRect(x-1.5,y-1.5,3,3);c.restore();
      }
    }else if(mode==='lightning'){
      for(let j=0;j<4;j++){
        const x=-.65+j*.43,p=.25+.25*Math.sin(t*.85+j);
        line([world(x,-.75),world(x+.08,-.30),world(x-.04,-.30),world(x+.1,.37)],1.8,p);
      }
    }
    if(mode==='tide'||mode==='flowers')for(let j=0;j<3;j++)curve(u=>[-.95+u*1.9,.66+j*.10+Math.sin(u*14-t*.8+j)*.025],64,1,.22);
    for(let j=0;j<12;j++){
      const down=['snow','palace','scroll'].includes(mode),v=(j*.618+t*.035)%1;
      const [x,y]=world(-.86+(j*.371%1)*1.72,down?-.85+v*1.7:.85-v*1.7);
      c.save();c.fillStyle=s.light;c.globalAlpha=opacity*.22;c.fillRect(x,y,2,mode==='snow'?2:1);c.restore();
    }
    return true;
  }
  window.DomainInk=Object.freeze({draw,flowerPose,clockPose});
})();

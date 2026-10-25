/* Geometry recipes shared by optional packages; package names/ownership stay in data. */
(() => {
  'use strict';
  const TAU=Math.PI*2;
  const scenes=new Map(),tints=new Map();
  async function prepare(rows,resolve=file=>file){
    let bytes=0;
    const art=(rows||[]).filter(r=>{
      const a=r.scene;if(!a)return false;
      const owned=r.owner?a.file.startsWith('/extension-assets/'+r.owner+'/'):a.file.startsWith('/assets/pixel/domains/');
      const size=a.size?.[0]*a.size?.[1]*4;
      if(!owned||!Number.isFinite(size)||size<=0||size>2*1024*1024||bytes+size>32*1024*1024)return false;
      bytes+=size;return true;
    }).slice(0,32);
    const active=new Set(art.map(r=>r.scene.file+'?v='+r.scene.sha256));
    for(const key of scenes.keys())if(!active.has(key))scenes.delete(key);
    for(const key of tints.keys())if(![...active].some(url=>key.startsWith(url+'|')))tints.delete(key);
    await Promise.all(art.map(row=>{
      const a=row.scene,key=a.file+'?v='+a.sha256;
      if(scenes.has(key))return scenes.get(key).ready;
      const entry={image:null,ready:null};scenes.set(key,entry);
      entry.ready=new Promise(done=>{
        const im=new Image();let timer;
        const finish=ok=>{clearTimeout(timer);im.onload=im.onerror=null;entry.image=ok?im:null;
          if(!ok&&scenes.get(key)===entry)scenes.delete(key);done();};
        im.onload=()=>finish(im.naturalWidth===a.size[0]&&im.naturalHeight===a.size[1]);
        im.onerror=()=>finish(false);timer=setTimeout(()=>finish(false),4000);
        im.src=resolve(a.file)+'?v='+a.sha256;
      });return entry.ready;
    }));
  }
  function painted(s){
    if(!s.scene)return null;
    const url=s.scene.file+'?v='+s.scene.sha256,im=scenes.get(url)?.image;
    if(!im)return null;
    const view=s.scene.view||[0,0,im.width,im.height];
    const key=url+'|'+view.join(',')+'|'+s.color.join(',');if(tints.has(key))return tints.get(key);
    const layer=document.createElement('canvas');layer.width=view[2];layer.height=view[3];
    const ctx=layer.getContext('2d');ctx.drawImage(im,...view,0,0,layer.width,layer.height);
    if(s.scene.ink){
      // Only authored strokes have alpha; the enclosed interiors stay empty.
      // Reinforce faint antialiased strokes once per cached tint. Exact-position
      // passes keep alpha-zero pixels empty and work in offline file previews
      // without reading pixels from a file-origin (tainted) canvas.
      for(const strength of [.8,.5]){
        ctx.globalAlpha=strength;ctx.drawImage(im,...view,0,0,layer.width,layer.height);
      }
      ctx.globalAlpha=1;
      ctx.globalCompositeOperation='source-in';
      ctx.fillStyle='rgb('+s.color.map(v=>Math.round(v+(255-v)*.84)).join(',')+')';
      ctx.fillRect(0,0,layer.width,layer.height);
      tints.set(key,layer);while(tints.size>8)tints.delete(tints.keys().next().value);
      return layer;
    }
    // Colour changes preserve the painted iron/stone luminance and original alpha.
    ctx.globalCompositeOperation='color';ctx.globalAlpha=.65;ctx.fillStyle='rgb('+s.color.join(',')+')';ctx.fillRect(0,0,layer.width,layer.height);
    ctx.globalCompositeOperation='destination-in';ctx.globalAlpha=1;ctx.drawImage(im,...view,0,0,layer.width,layer.height);
    // Feather the cropped lower edge into the field, not a rectangular backdrop.
    const fade=ctx.createLinearGradient(0,layer.height*.78,0,layer.height);
    fade.addColorStop(0,'#fff');fade.addColorStop(1,'#fff0');ctx.fillStyle=fade;ctx.fillRect(0,0,layer.width,layer.height);
    tints.set(key,layer);while(tints.size>8)tints.delete(tints.keys().next().value);
    return layer;
  }
  function pattern(s,x,y,t,n){
    const k=s.waves,z=t*s.speed,rad=Math.hypot(x-450,(y-280)*1.4);
    const flame=['flame','war-wheel','chains'].includes(s.motif);
    const a=flame?y*.055+Math.sin(x*.035+z*.4)*3+z*.9:rad*.035+Math.atan2(y-280,x-450)*k*.3-z*.25;
    return (.5+.5*Math.sin(a+n*3))**(s.motif==='rift'?14:5);
  }
  function draw({c,style:s,g,time:t,world,line,front,opacity}){
    const m=s.motif;
    const curve=(fn,count=56,w=1.5,a=.4)=>line(Array.from({length:count+1},(_,i)=>world(...fn(i/count))),w,a);
    const oval=(x,y,rx,ry,angle=0,a=.4,w=1.4)=>curve(u=>{const z=u*TAU,dx=Math.cos(z)*rx,dy=Math.sin(z)*ry;return[x+dx*Math.cos(angle)-dy*Math.sin(angle),y+dx*Math.sin(angle)+dy*Math.cos(angle)];},48,w,a);
    function petal(x,y,r,angle,a=.45){
      curve(u=>{const z=u*TAU,dx=Math.sin(z)*r*.42,dy=(Math.cos(z)-1)*r*.65;return[x+dx*Math.cos(angle)-dy*Math.sin(angle),y+dx*Math.sin(angle)+dy*Math.cos(angle)];},30,1.7,a);
    }
    function bloom(x,y,r,n=8){for(let j=0;j<n;j++)petal(x,y,r,j*TAU/n+t*.03);oval(x,y,r*.2,r*.3,0,.7);}
    function waves(){for(let j=0;j<7;j++)curve(u=>[-1+u*2,.05+j*.12+Math.sin(u*15-t*.5+j)*.035],64,j%3?1:2,.3);}
    function mountains(){for(let k=0;k<3;k++)curve(u=>[-1+2*u,-.25+k*.25-Math.abs(Math.sin(u*14+k))* (.3-k*.05)],80,1.7,.3+k*.07);}
    function palace(x=0,y=.55,scale=1){
      for(let k=0;k<3;k++){const w=(.62-k*.16)*scale,h=y-k*.22*scale;
        line([world(x-w,h),world(x-w*.5,h-.035*scale),world(x,h-.16*scale),world(x+w*.5,h-.035*scale),world(x+w,h)],2,.62);
        for(const sign of [-1,1])line([world(x+sign*w*.68,h),world(x+sign*w*.68,h+.19*scale)],1.7,.45);
      }curve(u=>[x+(u-.5)*1.1*scale,y+.2*scale],20,2,.4);
    }
    function flame(x,y,r,seed){
      curve(u=>{const z=u*TAU,dx=Math.sin(z)*r*(.55+.2*Math.cos(z*3+t)),dy=Math.cos(z)*r*1.6;return[x+dx+Math.sin(z*2+t*.8+seed)*r*.25,y+dy];},40,1.7,.5);
      curve(u=>[x+Math.sin(u*8+t+seed)*r*.25,y+r-u*r*2],26,1,.5);
    }
    if(m==='flame'){
      for(let j=0;j<11;j++)flame(-.88+j*.176,.65-(j%3)*.12,.12+(j%3)*.025,j);
      waves();
    }else if(m==='rift'){
      for(let j=0;j<5;j++){const x=-.7+j*.35;curve(u=>[x+Math.sin(u*12+j)*.045+(u-.5)*.18,-.85+u*1.7],32,2.5,.66);
        for(let b=0;b<3;b++)line([world(x+(b-1)*.02,-.45+b*.35),world(x+.16,-.55+b*.35),world(x+.21,-.35+b*.35)],1,.35);}
      oval(0,0,.76,.72,.12,.25);
    }else if(m==='grove'){
      for(const sign of [-1,1]){curve(u=>[sign*(.65-.16*Math.sin(u*2)),.9-u*1.6],60,3,.5);
        for(let j=0;j<6;j++){const y=.6-j*.25,x=sign*(.65-.16*Math.sin((j+1)*.3));curve(u=>[x+sign*u*.26,y-u*.24],20,1.6,.5);petal(x+sign*.2,y-.2,.16,sign*.8);}}
      bloom(0,.7,.16,7);
    }else if(m==='peaks'||m==='mountain-sea'){
      mountains();if(m==='mountain-sea'){waves();oval(.2,-.5,.18,.28,0,.5);}else for(let j=0;j<4;j++)curve(u=>[-.65+j*.4+u*.09,-.5+u*.75],24,3,.32);
    }else if(m==='lantern'||m==='procession'){
      if(m==='procession')waves();
      for(let j=0;j<(m==='procession'?12:6);j++){
        const x=-.82+(j%6)*.32,y=-.65+Math.floor(j/6)*.7+Math.sin(t*.3+j)*.05;
        oval(x,y,.055,.11,0,.65);oval(x,y,.025,.11,0,.48);
        line([world(x,y+.11),world(x+.02*Math.sin(t+j),y+.26)],1.5,.55);
        line([world(x-.045,y-.11),world(x+.045,y-.11)],2,.6);
      }
    }else if(m==='river'){
      for(let j=0;j<8;j++)curve(u=>[-1+u*2,-.6+j*.19+Math.sin(u*9-t*.35+j)*.12],72,j%2?1:3,.32);
      for(let j=0;j<5;j++)flame(-.72+j*.36,.38,.065,j);
    }else if(m==='scroll'){
      for(const sign of [-1,1]){curve(u=>[sign*.7+Math.sin(u*TAU)*.025,-.65+u*1.35],40,3,.55);oval(sign*.7,-.65,.055,.055,0,.6);}
      for(let j=0;j<8;j++)curve(u=>[-.58+u*1.16,-.52+j*.14+Math.sin(u*TAU+t*.2)*.025],36,1.2,.3);
      mountains();
    }else if(m==='lotus-palace'){
      palace(0,.2,.65);for(let j=-3;j<=3;j++)petal(0,.85,.55,j*.32,.55);oval(0,.78,.7,.15,0,.5);
    }else if(m==='war-wheel'){
      for(let k=0;k<3;k++)oval(0,0,.45+k*.13,.62+k*.12,t*.06,.4,1.7);
      for(let j=0;j<12;j++){const a=j*TAU/12+t*.06;line([world(Math.cos(a)*.43,Math.sin(a)*.6),world(Math.cos(a)*.72,Math.sin(a)*.89)],2,.55);}
      waves();
    }else if(m==='palace'){
      palace();for(const sign of [-1,1])palace(sign*.7,.65,.3);
      for(let j=0;j<8;j++)oval(Math.cos(j*TAU/8)*.75,Math.sin(j*TAU/8)*.75,.04,.06,0,.7);
    }else if(m==='chains'){
      const image=painted(s),weight=(.5-.5*Math.cos(t*.65));
      if(!front){
        const density=Math.max(0,Math.min(100,s.density??65))/100;
        c.save();c.globalAlpha=opacity*(s.scene?.ink ? .40+.18*density : .16+.20*density);
        if(image){
          // A continuous two-part mapping lowers the gate without a duplicate silhouette.
          const x=g.cx-g.rx*1.08,y=g.cy-g.ry*1.08,w=g.rx*2.16,h=g.ry*2.16;
          const cut=Math.round(image.height*.65),split=h*.65+weight*g.ry*.045;
          c.drawImage(image,0,0,image.width,cut,x,y,w,split);
          c.drawImage(image,0,cut,image.width,image.height-cut,x,y+split,w,h-split);
        }else{
          // Optional bitmap failure retains empty architectural contours, never a panel.
          line([world(-.4,.34),world(-.4,-.82),world(.4,-.82),world(.4,.34)],1.5,.35);
          line([world(0,-.82),world(0,.34)],2,.45);
        }
        c.restore();
      }
      // Weighted chain links sit at the margins; foreground remains below the actors.
      if(!s.scene?.ink)for(const sign of [-1,1])for(let j=0;j<17;j++){
        const u=j/16,nx=sign*(.95-u*.27)+Math.sin(t*.45+u*2)*.008;
        const ny=-.7+u*1.65,[x,y]=world(nx,ny);
        c.save();c.translate(x,y);c.rotate(-sign*.24);
        c.globalAlpha=opacity*(front?.10:.28);c.strokeStyle='#12191f';c.lineWidth=5;
        c.beginPath();c.ellipse(0,0,j%2?2:4,7,0,0,TAU);c.stroke();
        c.strokeStyle=s.light;c.lineWidth=1;c.globalAlpha*=.6;c.stroke();c.restore();
      }
      for(let j=0;j<(front?16:42);j++){
        const u=(j*.618033+t*(.025+(j%4)*.006))%1;
        const x=-.95+(j*.371%1)*1.9+Math.sin(t*.3+j)*.018,y=-.96+u*1.92;
        const [px,py]=world(x,y);c.save();c.globalAlpha=opacity*(front?.20:.32);
        c.fillStyle=s.light;c.fillRect(px,py,j%3?1:2,2);c.restore();
      }
    }else if(m==='star-beast'){
      for(let k=0;k<3;k++)curve(u=>[Math.cos(u*TAU+t*.04)*(.78-k*.12),Math.sin(u*TAU+t*.04)*(.45+k*.14)],72,1,.4);
      const pts=[[-.65,.35],[-.5,-.25],[-.15,-.4],[.3,-.25],[.62,-.55],[.5,.12],[.7,.6],[.3,.3],[-.15,.5],[-.65,.35]];
      line(pts.map(p=>world(...p)),2,.6);for(const [x,y]of pts)oval(x,y,.018,.026,0,.8);
    }else if(m==='wings'){
      for(const sign of [-1,1])for(let j=0;j<9;j++)curve(u=>[sign*(.05+u*(.8-j*.045)),.25-u*.6+Math.sin(u*Math.PI)*(-.4+j*.065)],42,2,.5);
      oval(0,-.3,.1,.18,0,.55);
    }else if(m==='flowers'){
      waves();for(let j=0;j<7;j++){
        const root=-.83+j*.275,base=.94,height=.39+Math.sin(j)*.08;
        const wind=.052*Math.sin(t*.8+j*.63)+.018*Math.sin(t*1.27+j*1.8);
        const x=root+wind,y=base-height+Math.abs(wind)*.16;
        curve(u=>[root+wind*u*u,base-height*u+Math.abs(wind)*u*u*.16],32,1.6,.6);
        for(let k=0;k<9;k++){
          const angle=k*TAU/9+t*.075+j*.3,flutter=.035*Math.sin(t*1.6+j+k*.7);
          curve(u=>{const a=angle+u*.8+flutter*Math.sin(u*Math.PI),r=u*(.12+flutter*.3);return[x+Math.cos(a)*r,y+Math.sin(a)*r*.6-.055*Math.sin(u*Math.PI)];},25,1.5,.6);
          const a=angle+.5;curve(u=>[x+Math.cos(a)*u*.155,y+Math.sin(a)*u*.09-.035*Math.sin(u*Math.PI)],20,1,.5);
        }
        oval(x,y,.018,.023,wind,.7);
      }
    }else if(m==='six-gates'){
      for(let j=0;j<6;j++){const a=j*TAU/6+t*.04,x=Math.cos(a)*.58,y=Math.sin(a)*.66;
        oval(x,y,.14,.22,a,.6,2);oval(x,y,.1,.17,a,.4);line([world(x*.72,y*.72),world(x*.3,y*.3)],1.5,.4);}
      oval(0,0,.21,.3,0,.7,2);oval(0,0,.79,.9,0,.35);
    }
    // Slow motes tie the authored motif to the filled field without obscuring actors.
    if(!front&&m!=='chains')for(let j=0;j<24;j++){
      const a=j*2.399+s.phase+t*.025,r=.25+(j%7)*.09,[x,y]=world(Math.cos(a)*r,Math.sin(a)*r);
      c.save();c.globalAlpha=opacity*.28;c.fillStyle=s.light;c.fillRect(Math.round(x),Math.round(y),2+(j%3),2);c.restore();
    }
  }
  window.DomainMotifs=Object.freeze({pattern,draw,prepare,bitmap:painted});
})();

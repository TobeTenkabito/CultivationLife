/* Editor-only preview. No combat resolution or game-state dependencies. */
(() => {
  'use strict';
  const W=960,H=540,BW=320,BH=180,TAU=Math.PI*2;
  const clamp=v=>Math.max(0,Math.min(1,v)),smooth=v=>{v=clamp(v);return v*v*(3-2*v);};
  const grid=Float32Array.from({length:16384},(_,i)=>{let n=Math.imul(i+193,374761393);n=Math.imul(n^(n>>>13),1274126177);return ((n^(n>>>16))>>>0)/4294967295;});
  function noise(x,y){const ix=Math.floor(x),iy=Math.floor(y),fx=smooth(x-ix),fy=smooth(y-iy),at=(a,b)=>grid[(b&127)*128+(a&127)];return (at(ix,iy)*(1-fx)+at(ix+1,iy)*fx)*(1-fy)+(at(ix,iy+1)*(1-fx)+at(ix+1,iy+1)*fx)*fy;}
  const loaded=new Map();
  function load(actor='dao-male'){
    if(!['dao-male','dao-female','demonic-male','demonic-female'].includes(actor))actor='dao-male';
    if(loaded.has(actor))return loaded.get(actor);
    const image=src=>new Promise((resolve,reject)=>{const im=new Image();im.onload=()=>resolve(im);im.onerror=()=>reject(Error('预览素材加载失败'));im.src=src;});
    const promise=Promise.all([fetch('/assets/pixel/combat/manifest.json').then(r=>{if(!r.ok)throw Error('人物清单加载失败');return r.json();}),image('/assets/pixel/combat/terrace.png')]).then(async([manifest,background])=>{
      const actors=await Promise.all([actor,'dao-female'].map(async id=>{const clip=manifest.actors[id].animations.idle;return {id,clip,image:await image('/'+clip.sheet.replace(/^\//,''))};}));return {manifest,background,actors};
    }).catch(e=>{loaded.delete(actor);throw e;});loaded.set(actor,promise);return promise;
  }
  function create(canvas,assets){const c=canvas.getContext('2d'),layer=document.createElement('canvas');layer.width=BW;layer.height=BH;const lc=layer.getContext('2d'),pixels=lc.createImageData(BW,BH);
    function path(points,color,width=1,alpha=1){c.save();c.strokeStyle=color;c.lineWidth=width;c.globalAlpha=alpha;c.beginPath();points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.stroke();c.restore();}
    const stroke=(pts,f,w=2.5,a=1)=>{path(pts,'#10282f',w+3,.85*a);path(pts,f.appearance.controlColor,w,a);path(pts,f.appearance.controlCore,.85,.9*a);};
    function binding(f,target,time,front){
      if(DomainControlEffects.draw(f.appearance.control,{c,f,target,time,front,stroke}))return;
      const settle=smooth(time/.9),pulse=.86+.10*Math.sin(time*2.4);
      if(!front){c.save();const shade=c.createRadialGradient(target,363,20,target,363,98);shade.addColorStop(0,'#071d2840');shade.addColorStop(.65,'#071d282b');shade.addColorStop(1,'#071d2800');c.fillStyle=shade;c.fillRect(target-100,265,200,196);c.restore();}
      const radii=[57,51,60],ys=[325,369,411];
      for(let i=0;i<3;i++){const q=smooth((time-i*.12)/.85),rx=radii[i]+(1-q)*30,points=[],start=front?0:Math.PI;
        for(let j=0;j<=40;j++){const a=start+j/40*Math.PI;points.push([target+Math.cos(a)*rx,ys[i]+Math.sin(a)*11]);}stroke(points,f,front?3:1.7,(front?pulse:.5)*(.35+.65*q));
        if(front){const a=((time*.17+i*.29)%1)*Math.PI;c.fillStyle=f.appearance.controlCore;c.fillRect(target+Math.cos(a)*rx-2,ys[i]+Math.sin(a)*11-2,4,4);
          for(const sign of [-1,1]){const x=target+sign*rx,y=ys[i],r=4.5;stroke([[x,y-r],[x+r,y],[x,y+r],[x-r,y],[x,y-r]],f,1.8,.95);}}
      }
      if(front)for(const sign of [-1,1])stroke([[target+sign*57,325],[target+sign*65,345],[target+sign*51,369],[target+sign*68,391],[target+sign*60,411]],f,1.7,.58+.15*settle);
    }
    function paint(settings,npc,time,mode){
      const appearances=[DomainFields.compose(settings,'player'),DomainFields.compose(npc,'npc-preview')];
      const fields=appearances.map((appearance,i)=>({id:i?'gold':'cyan',appearance,light:appearance.light,dir:i?-1:1,cx:i?577:385,cy:286,rx:354,ry:183,x:i?680:280}));
      const active=mode==='single'?[fields[0]]:fields;
      c.imageSmoothingEnabled=false;c.drawImage(assets.background,0,0,W,H);c.fillStyle='#06192266';c.fillRect(0,0,W,H);
      for(const f of active){const style=f.appearance;
        for(let py=0;py<BH;py++)for(let px=0;px<BW;px++){
          const x=px*3,y=py*3,k=(py*BW+px)*4,d=DomainFields.distance(f,x,y,time,style),p=pixels.data;
          if(d>1.15){p[k+3]=0;continue;}
          const n=noise(x*.013+time*f.dir*.1+style.phase,y*.018-time*.12),fine=noise(x*.047+n*2,y*.043+time*.2);
          const river=DomainFields.pattern(style,x,y,time,n),inner=clamp((1.04-d)*9),rim=Math.exp(-Math.abs(d-.96)*23),lum=.72+n*.32+river*.35+rim*.22;
          p[k]=Math.min(255,style.color[0]*lum);p[k+1]=Math.min(255,style.color[1]*lum);p[k+2]=Math.min(255,style.color[2]*lum);
          p[k+3]=Math.min(200,((.08+.23*n+.16*river+.05*fine)*inner+rim*(.10+.23*n))*255*style.density/100);
        }
        lc.putImageData(pixels,0,0);c.drawImage(layer,0,0,W,H);
        DomainFields.decorations({c,f,g:f,time,opacity:1,front:false,edge:true,noise,stroke:path});
      }
      if(mode==='control'){binding(fields[1],280,time,false);binding(fields[0],680,time,false);}
      for(let i=0;i<2;i++){
        const a=assets.actors[i],clip=a.clip,index=Math.min(clip.frames-1,Math.floor((time%clip.duration)*assets.manifest.fps)),r=clip.rects[index],anchor=clip.poses[index].anchor||assets.manifest.anchor;
        c.save();c.translate(fields[i].x,433);c.scale((i?-1:1)*(clip.facing||1),1);const scale=.95;
        c.drawImage(a.image,r[0],r[1],r[2],r[3],(r[4]-anchor[0])*scale,(r[5]-anchor[1])*scale,r[2]*scale,r[3]*scale);c.restore();
      }
      for(const f of active)DomainFields.decorations({c,f,g:f,time,opacity:1,front:true,edge:true,noise,stroke:path});
      if(mode==='control'){binding(fields[1],280,time,true);binding(fields[0],680,time,true);}
    }
    return {paint};
  }
  window.VoisinagePreview=Object.freeze({load,create});
})();

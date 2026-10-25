"""Inspect actual canvas pixels, not just declarations or animation formulas."""
def verify_outline(page, identity):
    result=page.evaluate('''id=>{
      const canvas=document.createElement('canvas');canvas.width=960;canvas.height=540;
      const c=canvas.getContext('2d'),g={cx:480,cy:270,rx:340,ry:205};
      const style=color=>DomainFields.compose({outline:id,pattern:id,palette:color,control:'rings',density:75},'ink-check');
      function render(time,color='#91bfc9',front=false){
        c.clearRect(0,0,960,540);const appearance=style(color);
        DomainFields.decorations({c,f:{appearance},g,time,front,opacity:1,stroke:(points,color,width,alpha)=>{
          c.save();c.strokeStyle=color;c.lineWidth=width;c.globalAlpha=alpha;c.beginPath();
          points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.stroke();c.restore();
        }});return canvas.toDataURL();
      }
      const a=render(1),same=render(1),b=render(4),tinted=render(1,'#d5a0a0');
      const pixels=c.getImageData(0,0,960,540).data;let visible=0,bright=0;
      for(let i=3;i<pixels.length;i+=4){if(pixels[i])visible++;if(pixels[i]>200)bright++;}
      const outside=c.getImageData(0,0,80,540).data.every((v,i)=>i%4!==3||v===0);
      render(1,'#91bfc9',true);
      const noForeground=c.getImageData(0,0,960,395).data.every((v,i)=>i%4!==3||v===0);
      let localMotion=true;
      if(id==='time'){
        render(1);const face=Array.from(c.getImageData(425,240,100,100).data).join(',');
        render(4);localMotion=face!==Array.from(c.getImageData(425,240,100,100).data).join(',');
      }
      if(id==='ghost-shore'){
        // Render one actual blossom without field clipping/ripples. Its stem endpoint stays put.
        const flower=DomainInk.flowerPose(88,1);
        const paint=t=>{c.clearRect(0,0,960,540);DomainInk.draw({c,style:style('#91bfc9'),g,time:t,world:(x,y)=>x===flower.root&&y===flower.base?[480,450]:[-10000,-10000],line:()=>{},front:false,opacity:1});};
        paint(1);const root=Array.from(c.getImageData(474,444,12,6).data).join(','),head=Array.from(c.getImageData(410,290,140,130).data).join(',');
        paint(4);localMotion=root===Array.from(c.getImageData(474,444,12,6).data).join(',')&&head!==Array.from(c.getImageData(410,290,140,130).data).join(',');
      }
      return {loaded:!!DomainMotifs.bitmap(style('#91bfc9')),deterministic:a===same,animated:a!==b,tinted:a!==tinted,
        visible:visible>100,transparent:visible/(960*540)<.42&&bright/visible<.02,outside,noForeground,localMotion};
    }''',identity)
    assert all(result.values()),(identity,result)
    return result

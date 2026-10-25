/* Pure visual components. No combat state, RNG, assets or capability grants. */
(() => {
  'use strict';
  const TAU=Math.PI*2,clamp=v=>Math.max(0,Math.min(1,v)),ease=v=>{v=clamp(v);return v*v*(3-2*v);};
  const catalog=[
    {id:'rings',name:'三重束纹',note:'已采用：三道束纹环绕人物，节点收紧。'},
    {id:'talismans',name:'符箓围禁',note:'四枚符箓环行，符文亮起后向目标收拢。'},
    {id:'stars',name:'星轨牵缚',note:'星点依次连成牵引线，外侧星芒向内归位。'},
    {id:'lotus',name:'莲瓣合禁',note:'莲瓣从足下升起，前后合拢，保留人物轮廓。'},
    {id:'pillars',name:'四柱锁界',note:'四枚法柱落定，脚下连线锁合；柱印向下归位。'},
    {id:'crystal',name:'晶棱凝禁',note:'晶棱由下向上凝成，折线闭合；不表示附加冻结。'}
  ].map(row=>Object.freeze({...row,semantics:['domination','seal'],status:'approved'}));
  function register(rows){for(const row of rows||[])if(row.motif&&!catalog.some(r=>r.id===row.id))catalog.push(Object.freeze({...row}));}
  function draw(id,ctx,active=false){
    const {c,f,target:x,time:t,front,stroke}=ctx;
    if(!catalog.some(row=>row.id===id)||id==='rings')return false;
    const custom=catalog.find(row=>row.id===id);
    if(custom.motif)return DomainControlMotifs.draw(custom.motif,ctx,active);
    const pulse=active?Math.sin(clamp((t-2)/2.4)*Math.PI):0;
    if(active&&(t<=2||t>=4.4))return true;
    const q=ease(t/.95),a=active?pulse:.88;
    const p=(pts,width=2,alpha=1)=>stroke(pts,f,width,alpha*a);
    const polygon=(pts,alpha=.09)=>{
      c.save();c.beginPath();pts.forEach(([px,py],i)=>i?c.lineTo(px,py):c.moveTo(px,py));c.closePath();
      c.fillStyle=f.light;c.globalAlpha=alpha*a;c.fill();c.restore();p([...pts,pts[0]],2);
    };
    const diamond=(px,py,r=5)=>polygon([[px,py-r],[px+r,py],[px,py+r],[px-r,py]],.24);
    const ellipse=(cx,cy,rx,ry,start=0,end=TAU,width=1.8,alpha=.7)=>{
      const pts=[];for(let i=0;i<=48;i++){const z=start+(end-start)*i/48;pts.push([cx+Math.cos(z)*rx,cy+Math.sin(z)*ry]);}p(pts,width,alpha);
    };
    if(!front&&!active){
      c.save();const gradient=c.createRadialGradient(x,365,25,x,365,101);gradient.addColorStop(0,'#071d2835');gradient.addColorStop(1,'#071d2800');
      c.fillStyle=gradient;c.fillRect(x-101,264,202,202);c.restore();
    }
    if(id==='talismans'){
      if(active){
        for(const sign of [-1,1]){const px=x+sign*(98-27*ease((t-2)/2.4));diamond(px,338,9);p([[px,351],[px-sign*9,370],[px,389]],2.5);}
      }else{
        ellipse(x,366,76+(1-q)*24,46,front?0:Math.PI,front?Math.PI:TAU,1.2,.55);
        for(let i=0;i<4;i++){
          const theta=t*.22+i*TAU/4,depth=Math.sin(theta);if((depth>=0)!==front)continue;
          const px=x+Math.cos(theta)*(76+(1-q)*24),py=356+depth*42;
          polygon([[px-10,py-25],[px+10,py-25],[px+10,py+23],[px,py+30],[px-10,py+23]],.17);
          p([[px-5,py-16],[px+5,py-16],[px,py-8],[px-4,py-3],[px+5,py+4],[px-4,py+10],[px+4,py+16]],1.5);
          p([[px,py-20],[px,py+18]],1,.65);
          if(front)diamond(px,py-29,3);
        }
      }
    }else if(id==='stars'){
      const grow=1+(1-q)*.35,nodes=[[-74,306],[-28,287],[35,298],[77,336],[60,411],[-3,442],[-70,402]].map(([dx,y],i)=>[x+dx*grow,y+Math.sin(t*.65+i)*2]);
      if(active){
        nodes.forEach(([px,py],i)=>{const k=1.3-.3*ease((t-2)/2.4);diamond(x+(px-x)*k,365+(py-365)*k,6);});
      }else{
        const pairs=front?[[0,6],[6,5],[5,4],[4,3],[6,3]]:[[0,1],[1,2],[2,3],[0,2]];
        for(const [i,j] of pairs){p([nodes[i],nodes[j]],1.8,front?.85:.5);
          const k=(t*.3+i*.17)%1;diamond(nodes[i][0]+(nodes[j][0]-nodes[i][0])*k,nodes[i][1]+(nodes[j][1]-nodes[i][1])*k,2);}
        nodes.forEach(([px,py],i)=>{if((i>=3||i===0)!==front)return;diamond(px,py,6);p([[px-9,py],[px+9,py]],1);p([[px,py-9],[px,py+9]],1);});
      }
    }else if(id==='lotus'){
      if(active){
        const u=ease((t-2)/2.4);for(const sign of [-1,1]){
          p([[x+sign*(100-25*u),419],[x+sign*(93-20*u),375],[x+sign*(68-10*u),310]],2.5);
          diamond(x+sign*(68-10*u),310,5);
        }
      }else{
        const count=front?3:4;
        for(let i=0;i<count;i++){
          const spread=(i-(count-1)/2),tipX=x+spread*(front?44:36)*(1.35-.35*q),baseY=front?445:426;
          const tipY=baseY-(front?91:120)*(.35+.65*q)+Math.sin(t*.7+i)*2;
          const baseX=x+spread*23,points=[];
          // Two curved edges form a petal, not a solid screen over the body.
          for(let j=0;j<=20;j++){const u=j/20;points.push([baseX*(1-u)+tipX*u-23*Math.sin(Math.PI*u),baseY*(1-u)+tipY*u]);}
          for(let j=20;j>=0;j--){const u=j/20;points.push([baseX*(1-u)+tipX*u+23*Math.sin(Math.PI*u),baseY*(1-u)+tipY*u]);}
          polygon(points,front?.055:.045);p([[baseX,baseY],[tipX,tipY]],1,.4);
        }
        ellipse(x,438,82,17,front?0:Math.PI,front?Math.PI:TAU,2,.85);
      }
    }else if(id==='pillars'){
      const posts=front?[[-66,447],[66,447]]:[[-49,420],[49,420]];
      if(active){for(const sign of [-1,1]){const px=x+sign*68,py=298+ease((t-2)/2.4)*104;diamond(px,py,9);p([[px-12,py-12],[px,py-19],[px+12,py-12]],2);}}
      else{
        for(const [dx,base] of posts){const px=x+dx*(1.3-.3*q),top=base-131-(1-q)*32;
          polygon([[px-7,base],[px-7,top+10],[px,top],[px+7,top+10],[px+7,base]],.13);
          p([[px-13,base],[px+13,base]],3);diamond(px,top+20,5);
          for(let j=0;j<3;j++)p([[px-3,top+43+j*23],[px+3,top+47+j*23]],1.3,.8);
        }
        p([[x-66,447],[x,458],[x+66,447]],front?2:1,front?.9:.15);
        if(!front)p([[x-49,420],[x,407],[x+49,420]],2,.6);
        else p([[x-66,447],[x-49,420],[x+49,420],[x+66,447]],1.2,.5);
      }
    }else if(id==='crystal'){
      if(active){const k=ease((t-2)/2.4);for(const sign of [-1,1]){const px=x+sign*(96-24*k);p([[px,428],[px+sign*9,392],[px,353],[px-sign*14,323]],3);diamond(px-sign*14,323,5);}}
      else{
        const shards=front?[[-65,365],[-32,399],[28,389],[67,349]]:[[-50,314],[43,307]];
        shards.forEach(([dx,top],i)=>{
          const px=x+dx,base=front?446:423,y=base-(base-top)*q,w=front?13:18;
          polygon([[px-w,base],[px-w*1.4,y+30],[px,y],[px+w*.8,y+24],[px+w,base]],.085);
          p([[px-w,base],[px,y+32],[px,y],[px+w*.8,y+24]],1,.7);
        });
        if(front)p([[x-76,432],[x-35,447],[x+8,439],[x+42,451],[x+80,427]],2.3,.9);
      }
    }
    return true;
  }
  window.DomainControlEffects=Object.freeze({get catalog(){return Object.freeze([...catalog]);},register,draw});
})();

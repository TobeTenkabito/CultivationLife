(() => {
  'use strict';
  window.createCombatBeasts=function(A,T){
  const {between,mix,clamp}=T;
  const colors={avian:'#91cbd5',quadruped:'#c5b88c',insect:'#9abc70'};
  const style=v=>v.actor.beast_style??v.id;
  const launches={avian:[1.15,1.85],insect:[1.15,2.15]};
  for(const kind of Object.keys(colors))A.actors[kind].energy_color=colors[kind];
  function geometry(s,m,state){
    const r=state.round;if(!r||!m.attacker.actor.creature)return;
    const v=m.attacker,t=state.time-r.start,dir=v.dir;
    if(style(v)==='avian'){
      v.y-=Math.round(62*s.scale*between(t,.7,1.15)*(1-between(t,2.55,3.5)));
    }else if(style(v)==='quadruped'){
      const g=v.actor.animations.attack,i=Math.round(A.actions.quadruped.contacts[0]*A.fps);
      const point=g.poses[i].point,anchor=g.poses[i].anchor;
      const reach=(point[0]-anchor[0])*s.scale,goal=m.contact-dir*reach;
      const forward=clamp((t-1.05)/1),back=clamp((t-2.85)/1),progress=forward*(1-back);
      v.x=Math.round(mix(v.x,goal,progress));
      const contactLift=Math.max(0,(v.y-m.hitY)/s.scale+(point[1]-anchor[1]));
      let lift=0;
      if(t>=1.05&&t<=2.05)lift=4*30*forward*(1-forward)+contactLift*forward;
      else if(t<2.65&&t>2.05)lift=contactLift*(1-clamp((t-2.05)/.6))**2;
      v.y-=Math.round(lift*s.scale);
    }
  }
  function guard(s,v,t,{context,line,ring}){
    if(!v.actor.creature||!colors[style(v)])return false;
    const b=v.barrier,c=context(s.front),rear=context(s.rear),k=s.scale,dir=v.dir;
    const color=colors[style(v)];c.save();rear.save();c.globalAlpha=b.opacity*.58;rear.globalAlpha=b.opacity*.3;
    const edge=(a)=>[b.cx+dir*(b.rx*Math.cos(a)-b.shield*1.7*k*Math.exp(-a*a/.24)),b.cy+b.ry*Math.sin(a)];
    if(style(v)==='avian'){
      for(let j=0;j<5;j++){
        const a=-1.1+j*.5,p=edge(a),q=edge(a+.22);
        line(c,p,q,color,1);line(c,q,[q[0]-dir*8*k,q[1]+3*k],'#c3dce0');
      }
    }else if(style(v)==='quadruped'){
      let prev=null;for(let j=0;j<=45;j++){
        const a=mix(-1.2,1.2,j/45),p=edge(a);if(prev)line(c,prev,p,'#b6c5bf');prev=p;
      }
      for(let j=0;j<7;j++){
        const x=v.x+(j-3)*12*k,shift=Math.sin(t*3+j)*2;
        line(rear,[x,s.ground-2],[x-dir*(5+shift)*k,s.ground-(5+j%3*3)*k],color,1);
      }
    }else{
      const x=b.contact-dir*3*k,y=b.cy;
      line(c,[x-dir*10*k,y-21*k],[x+dir*2*k,y+16*k],color,2);
      line(c,[x-dir*10*k,y+20*k],[x+dir*2*k,y-16*k],'#c1b57e',2);
      ring(c,b.cx,b.cy,b.rx,b.ry,color,dir>0?-1:Math.PI-1,dir>0?1:Math.PI+1,1);
    }
    c.restore();rear.restore();return true;
  }
  function effects(s,m,state,{context,line,ring,projectClip}){
    const a=m.attacker;if(!a?.actor.creature||!colors[style(a)])return false;
    const r=state.round,t=state.time-r.start,k=s.scale,dir=a.dir,c=context(s.projectile),x=m.contact,cy=m.hitY;
    projectClip(c,m,s,()=>{
      if(style(a)==='quadruped'){
        const age=state.time-r.contacts[0];if(age<0||age>.2)return;
        c.save();c.globalAlpha=.64*(1-between(age,0,.2));
        for(let j=0;j<3;j++)line(c,[x-dir*(13+j*3)*k,cy-14*k+j*6*k],[x,cy+8*k+j*6*k],j===1?'#e0d9b5':'#b9c6c3',1);
        c.restore();return;
      }
      const duration=style(a)==='avian'?.3:.26,length=(style(a)==='avian'?40:30)*k;
      for(let j=0;j<r.contacts.length;j++){
        const hit=r.contacts[j]-r.start,launch=launches[style(a)][j];
        if(t<launch||t>hit+duration)continue;
        const origin=a.hand,travel=between(t,launch,hit);
        const head=t<=hit?mix(origin[0],x,travel):x+dir*length*clamp((t-hit)/duration);
        const centerY=mix(origin[1],cy,travel),tail=head-dir*length;
        c.save();c.globalAlpha=.66;
        c.beginPath();if(dir>0)c.rect(Math.floor(origin[0]),0,s.width,s.height);else c.rect(0,0,Math.ceil(origin[0])+1,s.height);c.clip();
        for(let band=0;band<3;band++){
          let prev=null;
          for(let i=0;i<=38;i++){
            const u=i/38,arc=Math.sin(u*Math.PI)*(style(a)==='avian'?18:25)*k*(j%2?-1:1);
            const p=[mix(tail,head,u),centerY+arc+(band-1)*2*k];
            if(prev)line(c,prev,p,band===1?colors[style(a)]:style(a)==='avian'?'#b8e0df':'#b6bd83',1);prev=p;
          }
        }c.restore();
      }
    });
    return true;
  }
  return {geometry,guard,effects};
  };
})();



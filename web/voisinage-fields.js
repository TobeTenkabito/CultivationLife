/* Authored visual vocabulary; stable identities, no game RNG or mechanics. */
(() => {
  'use strict';
  const TAU=Math.PI*2;
  const catalog=[
    {id:'mist',name:'烟霞流岚',theme:'烟霞',power:2.6,waves:5,ripple:.055,skew:0,control:'talismans',hues:[163,185],note:'柔软云缘 · 层叠流岚 · 云纹舒卷'},
    {id:'star',name:'周天星垣',theme:'星辰',power:2,waves:8,ripple:.012,skew:0,control:'stars',hues:[240,265],note:'双层星弧 · 星尘薄幕 · 星轨缓转'},
    {id:'frost',name:'寒玉霜华',theme:'霜雪',power:3.3,waves:8,ripple:.025,skew:0,control:'crystal',hues:[198,218],note:'折晶边缘 · 霜雾冰纹 · 雪晶缓降'},
    {id:'lotus',name:'净莲宝华',theme:'净莲',power:2.3,waves:6,ripple:.048,skew:0,control:'lotus',hues:[318,345],note:'瓣形柔缘 · 澄光水纹 · 莲瓣浮升'},
    {id:'sword',name:'青锋剑境',theme:'剑意',power:2.7,waves:4,ripple:.025,skew:.12,control:'rings',hues:[172,191],note:'斜向锋缘 · 清气丝纹 · 剑影列阵'},
    {id:'seal',name:'玉印禁垣',theme:'镇封',power:3.8,waves:4,ripple:.012,skew:0,control:'pillars',hues:[37,51],note:'规整断缘 · 层叠经纬 · 印纹成序'},
    {id:'water',name:'沧溟回澜',theme:'流水',power:2.2,waves:7,ripple:.065,skew:0,control:'rings',note:'回澜波缘 · 多层潮线 · 漩涡缓转'},
    {id:'mountain',name:'叠嶂仙山',theme:'山岳',power:3,waves:5,ripple:.09,skew:0,control:'pillars',note:'叠嶂折缘 · 远近山影 · 山间流霭'},
    {id:'wood',name:'扶桑灵木',theme:'青木',power:2.4,waves:3,ripple:.09,skew:-.06,control:'lotus',note:'树冠曲缘 · 舒展枝脉 · 灵叶飘升'},
    {id:'thunder',name:'九霄雷章',theme:'雷霆',power:2.6,waves:10,ripple:.055,skew:0,control:'talismans',note:'折电棱缘 · 分岔雷纹 · 低频流光'},
    {id:'moon',name:'望月清辉',theme:'太阴',power:2,waves:2,ripple:.05,skew:0,control:'stars',note:'圆璧双缘 · 盈亏月相 · 桂影垂辉'},
    {id:'void',name:'太虚折境',theme:'虚空',power:1.45,waves:4,ripple:.035,skew:.16,control:'crystal',note:'菱形折缘 · 悬浮折面 · 错层虚线'},
    {id:'time',name:'烛时之轮',theme:'岁序',power:2,waves:12,ripple:.012,skew:0,control:'rings',note:'晷轮刻缘 · 烛龙盘轮 · 内外时环缓转'}
  ];
  function hash(text){let h=2166136261;for(const ch of String(text)){h^=ch.charCodeAt(0);h=Math.imul(h,16777619);}return h>>>0;}
  function rgb(h,s,l){const a=s*Math.min(l,1-l),f=n=>{const k=(n+h/30)%12;return Math.round(255*(l-a*Math.max(-1,Math.min(k-3,9-k,1))));};return [f(0),f(8),f(4)];}
  const css=v=>'rgb('+v.join(',')+')';
  const palettes=[['rose','淡玫',350],['peach','浅杏',22],['gold','柔金',43],['lime','浅芽',80],['green','淡翠',137],['jade','浅碧',164],['cyan','天青',185],['blue','雾蓝',212],['indigo','浅靛',239],['violet','淡紫',270],['lilac','浅藤',298],['pink','藕粉',325]].map(([id,name,hue])=>Object.freeze({id,name,hue}));
  function colorRGB(palette){
    if(typeof palette==='string'&&/^#[0-9a-f]{6}$/i.test(palette))return [1,3,5].map(i=>parseInt(palette.slice(i,i+2),16));
    const preset=palettes.find(p=>p.id===palette);if(!preset)throw Error('Unknown palette');return rgb(preset.hue,.40,.59);
  }
  function colorHex(palette){return '#'+colorRGB(palette).map(v=>v.toString(16).padStart(2,'0')).join('');}
  function build(theme,identity,palette='jade'){const row=catalog.find(r=>r.id===theme),color=palettes.find(p=>p.id===palette);if(!row)throw Error('Unknown visual theme');
    const base=colorRGB(palette),tint=amount=>css(base.map(v=>Math.round(v+(255-v)*amount)));
    const h=hash('voisinage-art-v1|'+theme+'|'+identity),hue=color?.hue;
    return {...row,identity:String(identity),seed:h,phase:(h%360)*Math.PI/180,
      palette:color?color.id:colorHex(palette),outline:row.id,count:14+(h>>>9)%5,color:base,light:color?css(rgb(hue,.55,.83)):tint(.60),
      controlColor:color?css(rgb(hue,.7,.67)):tint(.30),controlCore:color?css(rgb(hue,.66,.91)):tint(.85),speed:.82+((h>>>14)%37)/100};
  }
  function compose(settings,identity='player'){
    const style=build(settings.pattern,identity,settings.palette),outline=catalog.find(r=>r.id===settings.outline);
    if(!outline)throw Error('Unknown outline');
    for(const k of ['power','waves','ripple','skew'])style[k]=outline[k];
    return {...style,outline:outline.id,outlinePhase:(hash('voisinage-art-v1|'+outline.id+'|'+identity)%360)*Math.PI/180,control:settings.control,density:settings.density};
  }
  function radius(style,a,t){const cs=Math.cos(a),sn=Math.sin(a),base=(Math.abs(cs)**style.power+Math.abs(sn)**style.power)**(-1/style.power);
    let wave=Math.sin(a*style.waves+(style.outlinePhase??style.phase)+(style.outline==='mist'?t*.14:0));
    if(style.outline==='frost')wave=1-4*Math.abs(((a/TAU*8+8)%1)-.5);
    if(style.outline==='water')wave=Math.sin(a*7+(style.outlinePhase??style.phase)-t*.24)*.65+Math.sin(a*11+t*.17)*.35;
    if(style.outline==='mountain'||style.outline==='thunder')wave=1-4*Math.abs(((a/TAU*style.waves+10)%1)-.5);
    if(style.outline==='wood')wave=Math.cos(a*3+(style.outlinePhase??style.phase))*.65+Math.sin(a*7)*.35;
    if(style.outline==='moon')wave=Math.cos(a*2);
    if(style.outline==='void')wave=Math.cos(a*4);
    if(style.outline==='time')wave=Math.cos(a*12);
    return base*(1+style.ripple*wave);
  }
  function distance(g,x,y,t,style){const ny=(y-g.cy)/g.ry,nx=(x-g.cx)/g.rx-style.skew*ny,a=Math.atan2(ny,nx);
    return Math.hypot(nx,ny)/radius(style,a,t);
  }
  function point(g,style,a,t,scale=1){const r=radius(style,a,t)*scale,nx=Math.cos(a)*r,ny=Math.sin(a)*r;
    return [g.cx+(nx+style.skew*ny)*g.rx,g.cy+ny*g.ry];}
  function pattern(style,x,y,t,n){const z=t*style.speed;
    if(style.id==='mist')return (.5+.5*Math.sin(y*.055+x*.008+n*8-z*.45))**3;
    if(style.id==='star')return (.5+.5*Math.sin(Math.hypot(x-440,(y-260)*1.6)*.045+n*4-z*.14))**6;
    if(style.id==='frost')return (.5+.5*Math.sin(x*.035+y*.048+n*2-z*.08))**10;
    if(style.id==='lotus')return (.5+.5*Math.sin(Math.hypot(x-430,(y-450)*2)*.07+n*2-z*.5))**5;
    if(style.id==='sword')return (.5+.5*Math.sin(x*.035+y*.07+n-z*.8))**16;
    if(style.id==='water')return (.5+.5*Math.sin(y*.09+Math.sin(x*.018-z*.25)*1.8+n*3-z*.65))**5;
    if(style.id==='mountain')return (.5+.5*Math.sin(y*.055+Math.abs(Math.sin(x*.016+n))*5+n*2))**8;
    if(style.id==='wood')return (.5+.5*Math.sin(x*.045+Math.sin(y*.018+z*.12)*2+n*3))**10;
    if(style.id==='thunder')return (.5+.5*Math.sin(x*.043+y*.032+Math.abs(Math.sin(y*.07))*3+n))**24*(.75+.25*Math.sin(z*.8));
    if(style.id==='moon')return (.5+.5*Math.sin(Math.hypot((x-410)*.8,y-230)*.055+n-z*.18))**8;
    if(style.id==='void')return (.5+.5*Math.sin((Math.abs(x-420)+Math.abs(y-280)*1.7)*.045+n*2-z*.22))**18;
    if(style.id==='time')return (.5+.5*Math.sin(Math.hypot(x-420,y-280)*.075+n*.8-z*.26))**12;
    return Math.max((.5+.5*Math.sin(x*.045+n*.5))**20,(.5+.5*Math.sin(y*.07+n*.5-z*.1))**20);
  }
  function decorations({c,f,g,time:t,opacity,front,edge,noise,stroke}){
    const style=f.appearance;if(opacity<.015)return;
    const path=(points,width=1,alpha=.35)=>stroke(points,style.light,width,alpha*opacity);
    const dot=(x,y,r=3,alpha=.8)=>{path([[x-r,y],[x+r,y]],1,alpha);path([[x,y-r],[x,y+r]],1,alpha);};
    // Every decoration is clipped to its own independent field boundary.
    c.save();c.beginPath();for(let j=0;j<=120;j++){const p=point(g,style,j/120*TAU,t,.985);j?c.lineTo(...p):c.moveTo(...p);}c.closePath();c.clip();
    if(front){c.beginPath();c.rect(0,395,960,145);c.clip();}
    const factor=front?.16:1;
    const world=(nx,ny)=>[g.cx+(nx+style.skew*ny)*g.rx,g.cy+ny*g.ry];
    const line=(points,w=1,a=.4)=>path(points,w,a*factor);
    if(style.id==='mist'){
      for(let i=0;i<11;i++){
        const pts=[],base=-.77+i*.15;
        for(let j=0;j<=60;j++){const nx=-1.08+j/60*2.16,ny=base+Math.sin(nx*5+t*.20+i*.71)*.065+Math.sin(nx*11-i)*.025;pts.push(world(nx,ny));}
        line(pts,i%3===0?2.5:1,.19);
        line(pts.map(([x,y])=>[x,y+4]),.7,.16);
      }
      for(let i=0;i<5;i++){
        const center=world(-.68+i*.33,-.45+(i%3)*.35),pts=[];
        for(let j=0;j<54;j++){const a=j/53*TAU*1.3,r=3+j*.68;pts.push([center[0]+Math.cos(a+t*.08)*r,center[1]+Math.sin(a+t*.08)*r*.36]);}line(pts,1.5,.22);
      }
    }else if(style.id==='star'){
      for(let k=0;k<3;k++){
        const pts=[],tilt=(k-1)*.35;
        for(let j=0;j<=90;j++){const a=j/90*TAU;pts.push(world(Math.cos(a)*(.72-k*.12),Math.sin(a)*(.37+k*.15)+Math.cos(a)*tilt));}line(pts,1.1,.38);
      }
      const nodes=[];for(let i=0;i<style.count;i++){
        const u=noise(i*5+style.phase,8),v=noise(i*7+style.phase,41),pos=world((u*2-1)*.9,(v*2-1)*.85);nodes.push(pos);
        if(!front)dot(...pos,i%4===0?5:2,.55+.2*Math.sin(t*.6+i));
        if(i>0&&i%4!==0)line([nodes[i-1],pos],.8,.23);
      }
    }else if(style.id==='frost'){
      for(let i=0;i<style.count;i++){
        const nx=(noise(i*4,style.phase+6)*1.8-.9),ny=((i*.618+t*.018)%1)*1.8-.9,[x,y]=world(nx,ny),r=8+(i%4)*5;
        for(let arm=0;arm<6;arm++){
          const a=arm/6*TAU+.1*Math.sin(t*.2),end=[x+Math.cos(a)*r,y+Math.sin(a)*r];line([[x,y],end],1.2,.43);
          const bx=x+Math.cos(a)*r*.58,by=y+Math.sin(a)*r*.58;
          line([[bx+Math.cos(a+2.4)*r*.32,by+Math.sin(a+2.4)*r*.32],[bx,by],[bx+Math.cos(a-2.4)*r*.32,by+Math.sin(a-2.4)*r*.32]],.8,.42);
        }
      }
    }else if(style.id==='lotus'){
      // A broad, translucent flower trace belongs to the field, not the target binding.
      const base=world(0,.88);
      for(let i=-3;i<=3;i++){
        const tip=world(i*.22,-.30+Math.abs(i)*.15),pts=[];
        for(let j=0;j<=30;j++){const u=j/30;pts.push([base[0]*(1-u)+tip[0]*u-43*Math.sin(Math.PI*u),base[1]*(1-u)+tip[1]*u]);}
        for(let j=30;j>=0;j--){const u=j/30;pts.push([base[0]*(1-u)+tip[0]*u+43*Math.sin(Math.PI*u),base[1]*(1-u)+tip[1]*u]);}line(pts,1.5,.28);
      }
      for(let i=0;i<style.count;i++){
        const ny=.9-((i*.618+t*.023)%1)*1.8,nx=noise(i*8,style.phase)*1.8-.9,[x,y]=world(nx,ny);
        line([[x-7,y],[x-4,y-7],[x+6,y-12],[x+7,y-4],[x-7,y]],1.2,.48);
      }
    }else if(style.id==='sword'){
      for(let i=0;i<style.count;i++){
        const nx=(i%6)/5*1.8-.9,ny=-.7+Math.floor(i/6)*.65+Math.sin(t*.38+i)*.025,[x,y]=world(nx,ny);
        c.save();c.translate(x,y);c.rotate(-.43);
        line([[-3,30],[-3,-23],[0,-39],[3,-23],[3,30],[-3,30]],1.1,.48);
        line([[-10,20],[10,20]],1.3,.5);line([[0,30],[0,39]],2,.55);c.restore();
      }
      for(let k=0;k<7;k++){const pts=[];for(let j=0;j<32;j++)pts.push(world(-1.2+j*.075,-.85+k*.28-j*.026));line(pts,.7,.17);}
    }else if(style.id==='water'){
      for(let k=0;k<10;k++){
        const pts=[];for(let j=0;j<=72;j++){const nx=-1.1+j/72*2.2,ny=-.77+k*.17+Math.sin(nx*6-t*.42+k*.67)*.055;pts.push(world(nx,ny));}
        line(pts,k%3===0?2:1,.32);line(pts.map(([x,y])=>[x,y+5]),.7,.17);
      }
      for(let k=0;k<4;k++){
        const pts=[],cx=-.62+k*.41,cy=-.48+(k%2)*.78;
        for(let j=0;j<76;j++){const a=j/75*TAU*1.6+t*.16,r=.012+j*.002;pts.push(world(cx+Math.cos(a)*r,cy+Math.sin(a)*r*.45));}line(pts,1.6,.47);
      }
    }else if(style.id==='mountain'){
      for(let k=0;k<4;k++){
        const pts=[],offset=-.6+k*.28;
        for(let j=0;j<=24;j++){const nx=-1.12+j/24*2.24,ny=offset+(j%2?-.16:.09)+noise(j*3,k*5+style.phase)*.18;pts.push(world(nx,ny));}
        c.save();c.globalAlpha=opacity*factor*.045;c.fillStyle=style.light;c.beginPath();pts.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.lineTo(...world(1.12,1));c.lineTo(...world(-1.12,1));c.closePath();c.fill();c.restore();
        line(pts,k===3?2:1.3,.24+k*.07);
        const fog=[];for(let j=0;j<60;j++){const nx=-1.1+j/59*2.2;fog.push(world(nx,offset+.19+Math.sin(nx*5+t*.16+k)*.035));}line(fog,3,.11);
      }
    }else if(style.id==='wood'){
      const leaf=(nx,ny,angle,size=.055)=>{const pts=[];for(let j=0;j<=20;j++){const a=j/20*TAU,u=Math.cos(a)*size,v=Math.sin(a)*size*.35;pts.push(world(nx+u*Math.cos(angle)-v*Math.sin(angle),ny+u*Math.sin(angle)+v*Math.cos(angle)));}line(pts,1.4,.48);};
      for(const sign of [-1,1]){
        const trunk=[];for(let j=0;j<=40;j++){const ny=.85-j/40*1.6,nx=sign*(.48+.10*Math.sin(ny*2+t*.08));trunk.push(world(nx,ny));}line(trunk,2,.42);
        for(let k=0;k<6;k++){
          const ny=.62-k*.23,nx=sign*(.48+.10*Math.sin(ny*2+t*.08)),tip=nx-sign*(.20+(k%2)*.10),pts=[];
          for(let j=0;j<=20;j++){const u=j/20;pts.push(world(nx+(tip-nx)*u,ny-.20*u-.04*Math.sin(u*Math.PI)));}line(pts,1.4,.4);leaf(tip,ny-.2,sign*.7);leaf(nx+(tip-nx)*.6,ny-.08,-sign*.6,.04);
        }
      }
      for(let i=0;i<12;i++)leaf(noise(i*8,style.phase)*1.7-.85+.035*Math.sin(t*.4+i),.9-((i*.618+t*.035)%1)*1.8,t*.25+i,.035);
    }else if(style.id==='thunder'){
      for(let k=0;k<7;k++){
        const pts=[];for(let j=0;j<=10;j++){const ny=-.9+j*.18,nx=-.85+k*.28+(noise(j*4+k,style.phase)*2-1)*.085;pts.push(world(nx,ny));}
        const glow=.27+.16*(.5+.5*Math.sin(t*.85+k));line(pts,1.8,glow);line(pts,5,.055);
        for(const j of [3,6]){const [x,y]=pts[j],sign=j===3?1:-1;line([[x,y],[x+sign*16,y-13],[x+sign*30,y-10],[x+sign*43,y-29]],1.1,glow*.7);}
      }
    }else if(style.id==='moon'){
      for(let k=0;k<5;k++){
        const [x,y]=world(-.68+k*.34,-.50+Math.abs(k-2)*.14),r=k===2?34:21,pts=[];
        for(let j=0;j<=64;j++){const a=j/64*TAU;pts.push([x+Math.cos(a)*r,y+Math.sin(a)*r]);}line(pts,1.4,.48);
        if(k!==2){const crescent=[];for(let j=0;j<=40;j++){const a=-Math.PI/2+j/40*Math.PI;crescent.push([x+Math.cos(a)*r*(k<2?.38:-.38),y+Math.sin(a)*r]);}line(crescent,1.3,.54);}
        const halo=[];for(let j=0;j<=64;j++){const a=j/64*TAU;halo.push([x+Math.cos(a)*(r+6),y+Math.sin(a)*(r+6)]);}line(halo,.7,.22);
      }
      for(let k=0;k<13;k++){
        const nx=-.86+k*.143,ny=-.05+((k*.381+t*.025)%1)*.70;line([world(nx,ny-.12),world(nx,ny+.15)],1,.20+.08*Math.sin(t*.5+k));
        if(!front)dot(...world(nx,ny+.16),2,.25);
      }
    }else if(style.id==='void'){
      for(let k=0;k<9;k++){
        const cx=(k%3-1)*.58+.025*Math.sin(t*.22+k),cy=(Math.floor(k/3)-1)*.58,r=.18+(k%3)*.025;
        const corners=[world(cx,cy-r),world(cx+r,cy),world(cx,cy+r),world(cx-r,cy)];
        for(let j=0;j<4;j++){const a=corners[j],b=corners[(j+1)%4];line([a,[a[0]+(b[0]-a[0])*.78,a[1]+(b[1]-a[1])*.78]],1.6,.44);}
        line([corners[0],corners[2]],.7,.18);line([corners[1],corners[3]],.7,.18);
        line([corners[0].map((v,i)=>v+(i?7:12)),corners[1].map((v,i)=>v+(i?7:12)),corners[2].map((v,i)=>v+(i?7:12))],.8,.22);
      }
    }else if(style.id==='time'){
      const [cx,cy]=world(0,-.04),r=Math.min(g.rx*.62,g.ry*.84),phase=style.phase;
      const dial=(a,scale)=>[cx+Math.cos(a)*r*scale,cy+Math.sin(a)*r*scale];
      // Zhulong coils around the age wheel; the dragon is a field motif.
      for(const scale of [.76,.55]){
        const pts=[];for(let j=0;j<=120;j++)pts.push(dial(j/120*TAU,scale));line(pts,scale===1?1.8:1,.30);
      }
      for(let i=0;i<48;i++){
        const a=i/48*TAU+t*.025+phase;line([dial(a,.79),dial(a,i%4===0?.90:.84)],i%4===0?1.7:.8,i%4===0?.55:.28);
      }
      for(let k=0;k<6;k++){
        const a=k/6*TAU-t*.045+phase,pts=[];
        for(let j=0;j<=24;j++)pts.push(dial(a+j/24*.6,.60));line(pts,2,.42);
        line([dial(a,.57),dial(a,.64)],1.4,.5);
        if(k%2===0)line([dial(a,.48),dial(a+.11,.39),dial(a+.22,.48)],1.3,.32);
      }
      const start=-Math.PI*.35+t*.012,span=TAU*.87;
      const body=(u,side=0)=>dial(start+span*u,.97+.022*Math.sin(u*TAU*2+t*.17)+side*.075*(1-u*.92));
      const outer=[],inner=[];
      for(let j=0;j<=144;j++){outer.push(body(j/144,1));inner.push(body(j/144,-1));}
      const ribbon=[...outer,...inner.slice().reverse()];
      c.save();c.fillStyle=style.light;c.globalAlpha=opacity*factor*.13;c.beginPath();ribbon.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.closePath();c.fill();c.restore();
      line(outer,2.2,.66);line(inner,1.7,.52);
      for(let j=1;j<38;j++){
        const u=j/38,w=.014*(1-u*.6);
        line([body(u-w,.7),body(u,0),body(u+w,.7)],1,.43);
        line([body(u-w,-.65),body(u,0),body(u+w,-.65)],.8,.32);
        if(j%2===0)line([body(u-w,1),body(u,2),body(u+w,1)],1.2,.52);
      }
      const head=body(0),angle=start-Math.PI/2,scale=r/150;
      const hp=([x,y])=>[head[0]+(x*Math.cos(angle)-y*Math.sin(angle))*scale,head[1]+(x*Math.sin(angle)+y*Math.cos(angle))*scale];
      const hline=(pts,w=1.5,a=.7)=>line(pts.map(hp),w,a);
      const skull=[[-19,-11],[-4,-16],[8,-12],[15,-7],[31,-7],[36,-2],[29,5],[12,6],[2,14],[-17,11],[-19,-11]];
      c.save();c.fillStyle=style.light;c.globalAlpha=opacity*factor*.19;c.beginPath();skull.map(hp).forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.closePath();c.fill();c.restore();
      hline(skull,2,.78);hline([[13,1],[29,1],[34,-1]],1.2,.65);
      hline([[-10,-12],[-19,-26],[-32,-30],[-27,-20]],1.7,.75);
      hline([[-19,-26],[-16,-34]],1.2,.65);
      hline([[-4,-14],[-5,-27],[-15,-37]],1.5,.65);
      hline([[-5,-27],[2,-32]],1,.60);
      hline([[-15,8],[-28,14],[-23,3]],1.4,.6);
      hline([[26,4],[39,14],[54,12],[61,4+Math.sin(t*.3)*3]],1.2,.58);
      hline([[24,-5],[36,-15],[50,-16],[55,-23]],1,.46);
      hline([[10,9],[16,21],[8,29],[3,18],[-3,16]],1.3,.62);
      hline([[1,-8],[7,-10],[12,-7]],1.8,.90);
      hline([[7,-8],[7,-5]],2,.92);
      for(let k=0;k<8;k++){
        const a=k/8*TAU+t*.035,scale=.18+((k*.37+t*.018)%1)*.28;
        line([dial(a,scale),dial(a-.08,scale-.045)],1,.28);
      }
    }else{
      for(let i=0;i<5;i++)line([world(-.82,-.66+i*.33),world(.82,-.66+i*.33)],.9,.25);
      for(let i=0;i<7;i++)line([world(-.8+i*.267,-.76),world(-.8+i*.267,.76)],.9,.22);
      for(let i=0;i<9;i++){
        const [x,y]=world((i%3-1)*.51,(Math.floor(i/3)-1)*.56),r=17+2*Math.sin(t*.3+i);
        line([[x-r,y-r],[x+r,y-r],[x+r,y+r],[x-r,y+r],[x-r,y-r]],1.5,.48);
        line([[x-9,y-8],[x+9,y-8],[x,y],[x-7,y+7],[x+9,y+7]],1.5,.56);line([[x,y-12],[x,y+12]],1,.5);
      }
    }
    c.restore();
    if(front||!edge)return;
    for(let arc=0;arc<12;arc++){
      const pts=[],start=arc/12*TAU,span=style.outline==='seal'?.36:.44;
      for(let j=0;j<=20;j++)pts.push(point(g,style,start+span*j/20,t));
      path(pts,style.outline==='frost'?1.8:1.4,.53);
      if(style.outline==='star'||style.outline==='seal'){const pos=point(g,style,start,t);dot(...pos,style.outline==='star'?4:3,.7);}
      if(style.outline==='star')path(pts.map(([x,y])=>[g.cx+(x-g.cx)*.97,g.cy+(y-g.cy)*.97]),.7,.3);
      if(style.outline==='moon'||style.outline==='void')path(pts.map(([x,y])=>[g.cx+(x-g.cx)*.95,g.cy+(y-g.cy)*.95]),.9,.34);
    }
    if(style.outline==='time'){
      const ring=[];for(let j=0;j<=120;j++)ring.push(point(g,style,j/120*TAU,t,.95));path(ring,1,.30);
      for(let i=0;i<48;i++){
        const a=i/48*TAU;path([point(g,style,a,t,.95),point(g,style,a,t,i%4===0?.89:.925)],i%4===0?1.6:.8,i%4===0?.58:.32);
      }
    }
  }
  window.DomainFields=Object.freeze({catalog:Object.freeze(catalog.map(Object.freeze)),palettes:Object.freeze(palettes),colorHex,build,compose,distance,pattern,decorations});
})();

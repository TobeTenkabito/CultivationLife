/* The chart draws only the locations, trails and signs in the player's reading. */
window.DungeonAtlas = (() => {
  const marks = {
    here: 'M12 2l7 17-7-4-7 4z',
    入口: 'M3 5h18M5 8h14M7 8v12m10-12v12M5 20h4m6 0h4',
    外围: 'M3 19l6-10 4 6 3-5 5 9z',
    深处: 'M2 19l7-11 3 4 4-8 6 15zM9 8l1 6',
    核心: 'M12 2l9 10-9 10-9-10zM12 7l4 5-4 5-4-5z',
    岔路: 'M3 15h12c5 0 6-6 1-7-1-4-7-5-9 0-4-1-6 2-5 4m3 6h9m2 0h3'
  };
  const key = (x,y) => x+','+y;
  const landscapes=new Set(['water','mountain','fire','frost','fort','shadow','grove','ruins']);
  function signArt(marks){
    if(marks.some(m=>m.includes(' · 阵势 ')))return 'ward';
    if(marks.includes('暗阵'))return 'snare';
    if(marks.some(m=>['争斗','斗法','余波'].includes(m)))return 'clash';
    if(marks.some(m=>/^\d+人$/.test(m)||m==='追兵'))return 'tracks';
    return '';
  }
  function illustration(art){
    const img=document.createElement('img');
    img.className='atlas-illustration';img.alt='';
    img.src='/assets/dungeon/'+art+'.png';
    return img;
  }
  const svg = tag => document.createElementNS('http://www.w3.org/2000/svg',tag);
  function icon(type) {
    const node=svg('svg'),path=svg('path');
    node.setAttribute('viewBox','0 0 24 24');
    node.setAttribute('aria-hidden','true');
    path.setAttribute('d',marks[type]||marks['岔路']);
    node.append(path);
    return node;
  }
  function render(pane,map,el,moveButton,initialKey,remember) {
    const chart=el('div',undefined,'atlas-chart');
    if(landscapes.has(map.landscape)){
      chart.style.setProperty('--atlas-landscape',`url("/assets/dungeon/${map.landscape}.jpg")`);
    }
    const viewport=el('div',undefined,'atlas-viewport');
    const stage=el('div',undefined,'atlas-stage'), plot=el('div',undefined,'atlas-plot');
    const trails=svg('svg');
    trails.setAttribute('class','atlas-trails');
    trails.setAttribute('aria-hidden','true');
    trails.setAttribute('viewBox','0 0 100 100');
    trails.setAttribute('preserveAspectRatio','none');
    plot.append(trails);
    stage.append(plot);viewport.append(stage);
    const north=el('span','北','atlas-north');north.setAttribute('aria-hidden','true');
    const reading=map.chasing?'追逐 · 第 '+(map.round+1)+' 步':'神识 '+map.sense+' 阶';
    const status=el('span',undefined,'atlas-status');
    status.classList.toggle('chasing',map.chasing);
    chart.append(viewport,north,status);
    const here=map.cells.find(c=>c.here);
    const coords=new Map(map.cells.map(c=>[key(c.x,c.y),c]));
    const open=new Set(map.directions.filter(d=>d.open).map(d=>d.name));
    const paths=map.routes.map(([[x,y],[u,v]])=>{
      const a=coords.get(key(x,y)),b=coords.get(key(u,v)),path=svg('path');
      path.setAttribute('class',a.here||b.here?'near':a.visited&&b.visited?'walked':'distant');
      trails.append(path);
      return {a,b,path,bend:.12*Math.cos(3*x-y+u+2*v)};
    });
    const detail=el('div',undefined,'atlas-detail');detail.setAttribute('aria-live','polite');
    const nodes=new Map();
    function select(cell) {
      const id=key(cell.x,cell.y);
      remember(id);
      nodes.forEach((b,k)=>b.setAttribute('aria-pressed',String(k===id)));
      const location=cell.here?'你在此处':cell.direction||'远处';
      const text=el('div',undefined,'atlas-description');
      text.append(el('strong',location+' · '+(cell.area||'雾中岔路')));
      const clues=[...cell.marks,cell.omen].filter(Boolean);
      if(clues.length)text.append(el('small',clues.join(' · ')));
      else if(cell.here&&open.size)text.append(el('small','点选相邻岔路，查看去向。'));
      detail.replaceChildren(text);
      const art=signArt(cell.marks);
      if(art)detail.prepend(illustration(art));
      if(cell.direction)detail.append(moveButton(cell.direction,open.has(cell.direction)));
    }
    for(const cell of map.cells){
      const id=key(cell.x,cell.y), b=el('button',undefined,'atlas-node');
      b.type='button';
      b.dataset.coord=id;
      if(cell.direction)b.dataset.bearing=cell.direction;
      b.classList.toggle('here',cell.here);b.classList.toggle('visited',cell.visited);
      b.classList.toggle('fogged',!cell.area&&!cell.visited);
      const seal=el('span',undefined,'atlas-seal');
      const art=signArt(cell.marks);
      seal.append(art&&!cell.here?illustration(art):icon(cell.here?'here':cell.area));b.append(seal);
      const title=[cell.here?'你在此处':cell.direction,cell.area||'岔路',...cell.marks,cell.omen].filter(Boolean).join(' · ');
      b.title=title;b.setAttribute('aria-label',title);
      const signs=el('span',undefined,'atlas-signs');
      const symbols=new Map();
      for(const m of cell.marks){
        if(m.includes(' · 阵势 '))symbols.set('阵','ward');
        else if(m==='暗阵')symbols.set('伏','danger');
        else if(m==='追兵')symbols.set('追','danger');
        else if(['争斗','斗法','余波'].includes(m))symbols.set(m==='余波'?'波':'战','danger');
        else if(/^\d+人$/.test(m))symbols.set(m,'people');
      }
      symbols.forEach((kind,label)=>signs.append(el('i',label,'atlas-sign '+kind)));
      signs.setAttribute('aria-hidden','true');b.append(signs);
      if(cell.here)b.append(el('span','你','atlas-here-label'));
      else if(cell.direction)b.append(el('span',cell.direction,'atlas-bearing'));
      b.onclick=()=>select(cell);
      nodes.set(id,b);plot.append(b);
    }
    const legend=el('div',undefined,'atlas-legend');
    for(const [style,label] of [['here','你的位置'],['visited','已至'],['unknown','待探']]){
      const entry=el('span');entry.append(el('i',undefined,style),document.createTextNode(label));legend.append(entry);
    }
    pane.append(chart,legend,detail);
    const controls=el('div',undefined,'atlas-camera-controls');
    const returnToPlayer=el('button','归位','atlas-camera-button');
    returnToPlayer.type='button';returnToPlayer.hidden=true;
    controls.append(returnToPlayer);
    let overview=false;
    if(map.mastery===4){
      const toggle=el('button','展开全境','atlas-camera-button');toggle.type='button';
      toggle.setAttribute('aria-pressed','false');
      toggle.onclick=()=>{
        overview=!overview;toggle.textContent=overview?'返回近景':'展开全境';
        toggle.setAttribute('aria-pressed',String(overview));reset();
      };
      controls.append(toggle);
    }
    chart.append(controls);
    viewport.tabIndex=0;
    viewport.setAttribute('role','region');
    const xs=map.cells.map(c=>c.x),ys=map.cells.map(c=>c.y);
    const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
    const clamp=(v,min,max)=>Math.max(min,Math.min(v,max));
    const offsetX=(x,y)=>.12*Math.sin(7*x+5*y+1);
    const offsetY=(x,y)=>.12*Math.cos(4*x-11*y);
    let cx=here.x,cy=here.y,stepX=80,stepY=80;
    function paint(){
      if(!viewport.clientWidth||!viewport.clientHeight)return;
      viewport.dataset.camera=overview?'overview':'local';
      viewport.setAttribute('aria-label',overview?'全境舆图':'境内近景，拖动或按方向键环顾，Home 键归位');
      status.textContent=(overview?'全境':cx===here.x&&cy===here.y?'脚下近景':'环顾')+' · '+reading;
      stage.style.minWidth=overview?((maxX-minX)*48+88)+'px':'';
      stage.style.minHeight=overview?((maxY-minY)*48+75)+'px':'';
      const w=stage.clientWidth,h=stage.clientHeight;
      // The near view always uses local distances, independent of the extent of discovery.
      stepY=clamp((Math.min(w,h)-36)/2.85,46,142);
      stepX=clamp((w-74)/2.75,stepY,stepY*1.55);
      const pts=new Map(),zone=new Set();
      const fullStep=Math.min((w-88)/Math.max(1,maxX-minX+.24),(h-75)/Math.max(1,maxY-minY+.24));
      const ox=overview?(minX+maxX)/2:cx+offsetX(here.x,here.y);
      const oy=overview?(minY+maxY)/2:cy+offsetY(here.x,here.y);
      chart.style.setProperty('--atlas-bg-x',clamp(50-cx*4,15,85)+'%');
      chart.style.setProperty('--atlas-bg-y',clamp(50-cy*4,15,85)+'%');
      trails.setAttribute('viewBox','0 0 '+w+' '+h);
      for(const c of map.cells){
        const id=key(c.x,c.y),b=nodes.get(id);
        const px=w/2+(overview?fullStep:stepX)*(c.x+offsetX(c.x,c.y)-ox);
        const py=h/2+(overview?fullStep:stepY)*(c.y+offsetY(c.x,c.y)-oy);
        pts.set(id,[px,py]);
        const visible=overview||(Math.abs(c.x-cx)<=1.35&&Math.abs(c.y-cy)<=1.35&&px>=20&&px<=w-20&&py>=20&&py<=h-20);
        if(visible)zone.add(id);
        b.hidden=!visible;b.style.left=px+'px';b.style.top=py+'px';
      }
      for(const {a,b,path,bend} of paths){
        const ka=key(a.x,a.y),kb=key(b.x,b.y);
        const aIn=zone.has(ka),bIn=zone.has(kb);
        path.style.display=aIn||bIn?'':'none';
        if(!aIn&&!bIn)continue;
        let [ax,ay]=pts.get(ka),[bx,by]=pts.get(kb);
        // Carry a confirmed trail into the mist without drawing its distant endpoint.
        if(!aIn){ax=bx+(ax-bx)*.58;ay=by+(ay-by)*.58;}
        if(!bIn){bx=ax+(bx-ax)*.58;by=ay+(by-ay)*.58;}
        const qx=(ax+bx)/2-(by-ay)*bend,qy=(ay+by)/2+(bx-ax)*bend;
        path.setAttribute('d',`M ${ax} ${ay} Q ${qx} ${qy} ${bx} ${by}`);
        path.classList.toggle('into-mist',aIn!==bIn);
      }
      returnToPlayer.hidden=overview||(cx===here.x&&cy===here.y);
    }
    function reset(){cx=here.x;cy=here.y;select(here);paint();viewport.scrollTo(0,0);}
    function pan(x,y){
      cx=clamp(x,minX,maxX);cy=clamp(y,minY,maxY);
      if(nodes.get(key(here.x,here.y)).getAttribute('aria-pressed')!=='true')select(here);
      paint();
    }
    returnToPlayer.onclick=reset;
    let drag=null;
    viewport.onpointerdown=e=>{
      if(overview||!e.isPrimary||e.button!==0||e.target.closest('button'))return;
      drag={x:e.clientX,y:e.clientY,cx,cy};viewport.setPointerCapture(e.pointerId);
    };
    viewport.onpointermove=e=>{
      if(drag&&e.isPrimary)pan(drag.cx+(drag.x-e.clientX)/stepX,drag.cy+(drag.y-e.clientY)/stepY);
    };
    viewport.onlostpointercapture=()=>{drag=null;};
    viewport.onkeydown=e=>{
      if(e.target!==viewport||overview)return;
      const vector={ArrowUp:[0,-1],ArrowDown:[0,1],ArrowLeft:[-1,0],ArrowRight:[1,0]}[e.key];
      if(vector){e.preventDefault();pan(cx+vector[0],cy+vector[1]);}
      else if(e.key==='Home'){e.preventDefault();reset();}
    };
    legend.append(el('span','拖动环顾','atlas-pan-hint'));
    select(coords.get(initialKey)||here);
    const observer=new ResizeObserver(paint);
    observer.observe(viewport);
    return observer;
  }
  return {render};
})();

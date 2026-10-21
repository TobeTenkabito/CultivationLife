/* The home painting is not the route atlas. Its camera never changes the game. */
(() => {
  'use strict';
  const images=new Map();
  const el=(tag,text,cls='')=>{const n=document.createElement(tag);n.className=cls;if(text!=null)n.textContent=text;return n;};
  function entry(world){return PixelLibrary.catalog?.maps[world];}
  async function landscape(world){
    await PixelLibrary.ensure();
    const asset=PixelLibrary.catalog?.assets[entry(world)?.asset];
    if(!asset||!PixelLibrary.active())return null;
    if(!images.has(world))images.set(world,new Promise(resolve=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>resolve(null);i.src=asset.file;}));
    return images.get(world);
  }
  function mount(host,map,{onSelect}){
    const data=entry(map.world),asset=PixelLibrary.catalog?.assets[data?.asset];
    if(!asset)return null;
    const view=el('div',null,'pixel-world-view');view.tabIndex=0;view.setAttribute('aria-label',map.world_name+'所在地绘景');
    const plane=el('div',null,'pixel-world-plane'),image=el('img',null,'pixel-background');
    image.alt=map.world_name+'山河绘景';image.src=asset.file;image.draggable=false;plane.append(image);view.append(plane);
    const labels=el('div',null,'pixel-world-labels');view.append(labels);
    const tools=el('div',null,'pixel-world-tools');tools.setAttribute('role','toolbar');tools.setAttribute('aria-label','绘景视野');
    const select=el('select');select.setAttribute('aria-label','浏览绘景地域');
    for(const p of map.locations){const option=el('option',p.name+(p.id===map.current?' · 所在地':''));option.value=p.id;select.append(option);}
    const current=el('span',map.current_name,'pixel-world-location');
    const heading=el('div',null,'pixel-world-heading');heading.append(el('small',map.world_name+' · 当前所在'),current);
    view.append(heading,tools);host.replaceChildren(view);
    let selected=map.current,camera={x:0,y:0,z:1},disposed=false,ready=false,dragged=false,pointer=null;
    const buttons=new Map();
    for(const place of map.locations){
      const anchor=data.places[place.id];if(!anchor)continue;
      const b=el('button',place.name,'pixel-world-place');b.type='button';b.dataset.pixelLocation=place.id;
      b.title=place.name+(place.id===map.current?' · 当前所在':'');b.classList.toggle('current',place.id===map.current);
      b.onclick=()=>{if(!dragged)choose(place.id);};labels.append(b);buttons.set(place.id,b);
    }
    const fitScale=()=>Math.min(view.clientWidth/768,view.clientHeight/576,1);
    function paint(){
      if(disposed||!view.clientWidth)return;
      const w=view.clientWidth,h=view.clientHeight;
      camera.x=Math.round(Math.max(w-768*camera.z-60,Math.min(60,camera.x)));
      camera.y=Math.round(Math.max(h-576*camera.z-40,Math.min(40,camera.y)));
      if(768*camera.z<w)camera.x=Math.round((w-768*camera.z)/2);
      if(576*camera.z<h)camera.y=Math.round((h-576*camera.z)/2);
      plane.style.transform=`translate(${camera.x}px,${camera.y}px) scale(${camera.z})`;
      view.dataset.scale=String(camera.z);
      const occupied=[heading,tools].map(n=>n.getBoundingClientRect()),bounds=view.getBoundingClientRect();
      const overlap=(a,b)=>a.left<b.right+6&&a.right>b.left-6&&a.top<b.bottom+5&&a.bottom>b.top-5;
      const ordered=[...buttons].sort(([a],[b])=>Number(b===selected||b===map.current)-Number(a===selected||a===map.current));
      for(const [id,b]of ordered){const p=data.places[id];b.style.left=Math.round(camera.x+p.x*7.68*camera.z)+'px';b.style.top=Math.round(camera.y+p.y*5.76*camera.z)+'px';
        b.setAttribute('aria-pressed',String(id===selected));
        const r=b.getBoundingClientRect(),show=(p.major||id===selected||id===map.current||camera.z>=1)&&r.left>=bounds.left+5&&r.right<=bounds.right-5&&r.top>=bounds.top+5&&r.bottom<=bounds.bottom-5&&!occupied.some(other=>overlap(r,other));
        b.style.visibility=show?'visible':'hidden';if(show)occupied.push(r);
      }
      minus.disabled=camera.z<=fitScale()+.001;plus.disabled=camera.z>=2;
    }
    function center(id,z=camera.z){const p=data.places[id];if(!p)return;camera.z=z;camera.x=view.clientWidth/2-p.x*7.68*z;camera.y=view.clientHeight/2-p.y*5.76*z;paint();}
    function choose(id){if(!map.locations.some(p=>p.id===id))return;selected=id;select.value=id;center(id);paint();onSelect(id);}
    function zoom(direction){
      const levels=[fitScale(),.5,1,2].filter(z=>z>=fitScale()).sort((a,b)=>a-b);
      const next=direction>0?levels.find(z=>z>camera.z+.001):levels.slice().reverse().find(z=>z<camera.z-.001);
      if(next==null)return;const x=view.clientWidth/2,y=view.clientHeight/2,old=camera.z;camera.z=next;camera.x=x-(x-camera.x)*next/old;camera.y=y-(y-camera.y)*next/old;paint();
    }
    function tool(symbol,title,fn){const b=el('button');b.type='button';b.title=title;b.setAttribute('aria-label',title);b.append(VisualAssets.icon(symbol));b.onclick=fn;tools.append(b);return b;}
    const minus=tool('minus','缩小绘景',()=>zoom(-1)),plus=tool('plus','放大绘景',()=>zoom(1));
    tool('panel','查看全幅绘景',()=>{camera={x:0,y:0,z:fitScale()};paint();});
    tool('locate','返回所在地',()=>{selected=map.current;select.value=selected;center(selected,view.clientWidth<400?.5:1);onSelect(selected);});
    tools.append(select);select.value=selected;select.onchange=()=>choose(select.value);
    view.onpointerdown=e=>{if(e.target.closest('button,select')||e.button!==0)return;dragged=false;pointer={id:e.pointerId,x:e.clientX,y:e.clientY,originX:e.clientX,originY:e.clientY};view.setPointerCapture(e.pointerId);};
    view.onpointermove=e=>{if(pointer?.id!==e.pointerId)return;dragged||=Math.hypot(e.clientX-pointer.originX,e.clientY-pointer.originY)>5;camera.x+=e.clientX-pointer.x;camera.y+=e.clientY-pointer.y;pointer.x=e.clientX;pointer.y=e.clientY;paint();};
    view.onpointerup=view.onpointercancel=()=>{pointer=null;dragged=false;};
    view.onkeydown=e=>{if(e.target!==view||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(e.key))return;e.preventDefault();if(e.key==='Home')center(map.current);else{camera.x+=e.key==='ArrowLeft'?40:e.key==='ArrowRight'?-40:0;camera.y+=e.key==='ArrowUp'?40:e.key==='ArrowDown'?-40:0;paint();}};
    const observer=new ResizeObserver(()=>{if(!view.clientWidth)return;if(!ready){ready=true;center(map.current,view.clientWidth<400?.5:1);}else paint();});observer.observe(view);
    return {select:choose,dispose(){disposed=true;observer.disconnect();pointer=null;image.removeAttribute('src');}};
  }
  window.PixelMap=Object.freeze({mount,landscape,entry});
})();

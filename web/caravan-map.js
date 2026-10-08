/* Observable local traffic on a topology map; locations never imply remote stock. */
(() => {
  const ns='http://www.w3.org/2000/svg';
  const svgNode=(tag,attrs={})=>{const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);return e;};
  const node=(tag,text,cls='')=>{const e=document.createElement(tag);e.textContent=text;e.className=cls;return e;};
  const status={waiting:'候货',travelling:'在途',selling:'待售',stranded:'受阻',retired:'已解散'};
  function render(root,market,map){
    const fleets=(market.caravans||[]).filter(f=>f.status!=='retired');if(!fleets.length)return;
    const places=new Map((map?.locations||[]).map(p=>[p.id,p.name]));
    const current=market.market_id.slice(market.market_id.indexOf(':')+1);
    const ids=new Set([current]);fleets.forEach(f=>{(f.route||[]).forEach(id=>{if(places.has(id))ids.add(id);});if(places.has(f.location_id))ids.add(f.location_id);});
    const outside=[...ids].filter(id=>id!==current).sort();const positions=new Map([[current,[350,225]]]);
    outside.forEach((id,i)=>{const a=-Math.PI/2+2*Math.PI*i/outside.length;positions.set(id,[350+245*Math.cos(a),225+155*Math.sin(a)]);});
    const box=node('section','','caravan-atlas'),header=node('div','','caravan-atlas-heading');
    header.append(node('strong','商路行旅图'),node('span',`${fleets.length} 支可见商队 · 第 ${market.year} 年`));
    const svg=svgNode('svg',{viewBox:'0 0 700 450',role:'img','aria-label':'本地商队路线与行程示意图'});
    const detail=node('div','选择商队标记或下方名录，查看行程。','caravan-map-detail');detail.setAttribute('aria-live','polite');
    const list=node('div','','caravan-map-roster');const links=new Map();
    const focus=(fleet)=>{
      svg.querySelectorAll('[data-fleet]').forEach(n=>n.classList.toggle('selected',n.dataset.fleet===fleet.id));
      list.querySelectorAll('button').forEach(n=>n.setAttribute('aria-pressed',String(n.dataset.fleet===fleet.id)));
      detail.replaceChildren(node('strong',fleet.name),node('p',`${status[fleet.status]||'跨界运输'} · ${fleet.destination?`${fleet.origin} → ${fleet.destination}`:fleet.location}`),
        node('small',fleet.arrival!=null?`预计第 ${fleet.arrival} 年抵达 · ${Math.max(0,fleet.arrival-market.year)} 年后`:'留驻当地，等待下一次运输'));
    };
    fleets.forEach(f=>{
      const route=(f.route||[]).filter(id=>positions.has(id));
      for(let i=1;i<route.length;i++){const a=positions.get(route[i-1]),b=positions.get(route[i]);const key=[route[i-1],route[i]].sort().join('|');if(links.has(key))continue;links.set(key,true);svg.append(svgNode('path',{d:`M${a} L${b}`,class:'caravan-route'}));}
    });
    positions.forEach(([x,y],id)=>{const g=svgNode('g',{class:`caravan-place${id===current?' current':''}`});g.append(svgNode('circle',{cx:x,cy:y,r:id===current?25:15}));const label=svgNode('text',{x,y:y+38,'text-anchor':'middle'});label.textContent=places.get(id)||market.name;g.append(label);svg.append(g);});
    fleets.forEach((fleet,index)=>{
      const route=(fleet.route||[]).filter(id=>positions.has(id));
      let point=positions.get(fleet.location_id)||positions.get(current);
      if(route.length>1){const progress=Math.min(1,Math.max(0,(market.year-fleet.departure)/Math.max(1,fleet.arrival-fleet.departure)));const part=progress*(route.length-1),i=Math.min(route.length-2,Math.floor(part)),t=part-i;const a=positions.get(route[i]),b=positions.get(route[i+1]);point=[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t];}
      const [x,y]=point;const offset=(index%5-2)*12;
      const marker=svgNode('g',{transform:`translate(${x+offset} ${y-22-Math.floor(index%10/5)*20})`,class:'caravan-marker',tabindex:0,role:'button','aria-label':`${fleet.name} · ${status[fleet.status]||'运输'}`});marker.dataset.fleet=fleet.id;
      marker.append(svgNode('circle',{r:13}));const text=svgNode('text',{'text-anchor':'middle',y:4});text.textContent=String(index+1);marker.append(text);marker.onclick=()=>focus(fleet);marker.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();focus(fleet);}};svg.append(marker);
      const button=node('button',`${index+1} · ${fleet.name} · ${status[fleet.status]||'运输'}`);button.type='button';button.dataset.fleet=fleet.id;button.onclick=()=>focus(fleet);list.append(button);
    });
    box.append(header,svg,node('p','节点为商路示意；沿线位置按本次运输已过时间估算。跨界行程仅展示当地可见记录。','muted'),detail,list);root.append(box);
  }
  window.CaravanMap={render};
})();

/* Region-bound building projection; commands always validate the real address. */
(() => {
  let state, send, locked = () => true;
  const el = (tag, text, cls = '') => { const n = document.createElement(tag); n.className = cls; if (text != null) n.textContent = text; return n; };
  function icon(name) {
    const node=el('img');node.src=`/assets/building-icons/${name}.svg`;node.alt='';node.setAttribute('aria-hidden','true');return node;
  }
  function command(text, payload, unavailable = false) {
    const b = el('button', null, 'building-command'); b.append(icon(payload.action==='enter'?'log-in':payload.action==='manage'?'hammer':'plus'),el('span',text));
    b.type = 'button'; b.dataset.atlasUnavailable = unavailable ? '1' : '0';
    b.title=text;b.setAttribute('aria-label',text);
    b.dataset.buildingAction = payload.action; b.disabled = unavailable || locked(); b.onclick = event => {event.preventDefault();event.stopPropagation();send(payload);}; return b;
  }
  function building(row,place) {
    const item=el('details',null,'building-row');item.dataset.buildingId=row.id;item.dataset.status=row.status;
    const kind=['cave','temple'].includes(row.subtype)?row.subtype:row.type;
    const summary=el('summary',null,'building-entry-heading');
    const body=el('div',null,'building-copy'),head=el('div',null,'building-title');
    head.append(el('strong',row.name),el('span',row.status==='destroyed'?'遗址待建':row.status==='damaged'?'受损':row.type==='scenery'?'山河旧景':'完好','building-status'));
    const category={city:'城池',scenery:'景色',industry:'产业',cave:'洞府',temple:'佛寺',other:'建筑'}[kind]||'建筑';
    const meta=[category,row.type==='scenery'?'自然景观':`${row.level}级`,row.use_name,row.population_name].filter(Boolean);
    body.append(head,el('p',meta.join(' · '),'building-meta'));
    summary.append(body);
    const actions=el('div',null,'building-row-actions');
    if(place.current){
      if(row.status!=='destroyed')actions.append(command(row.type==='scenery'?'观景':'进入',{action:'enter',building_id:row.id},!row.can_enter));
      if(row.type!=='scenery')actions.append(command(row.status==='destroyed'?'重建':'营造',{action:'manage',building_id:row.id}));
    }else actions.append(el('span','需亲赴此地','building-remote'));
    summary.append(actions,icon('chevron-down'));item.append(summary);
    const detail=el('div',null,'building-detail'),art=el('div',null,'building-art');art.dataset.kind=kind;art.setAttribute('aria-hidden','true');
    const copy=el('div',null,'building-detail-copy');copy.append(el('p',row.description,'building-description'));
    copy.append(el('small',row.status==='destroyed'?'保留原址与原产权':row.type==='scenery'?'公开游览':row.owned?'自有 · 使用权在手':row.access?'对外开放':'尚无使用许可','building-access'));
    detail.append(art,copy);item.append(detail);return item;
  }
  function listing(host,place){
    const rows=place.buildings||[],list=el('div',null,'building-list');
    for(const row of rows)list.append(building(row,place));
    if(!rows.length)list.append(el('p','山川尚静，此处未有登记建筑。','building-empty'));
    host.append(list);
    if(!place.current)return;
    const footer=el('div',null,'building-workshop'),controls=el('div',null,'building-actions');
    footer.append(el('span','当地营造','building-workshop-title'));
    controls.append(command(rows.some(r=>r.subtype==='cave'&&r.access)?'整修洞府':'开辟洞府',{action:'construct'},!state.buildings.can_construct));
    controls.append(command('筑城',{action:'city-plan'},!state.buildings.can_build_city));
    if(state.buildings.can_establish_temple)controls.append(command('修建寺庙',{action:'temple-plan'}));
    footer.append(controls);host.append(footer);
    if(state.buildings.blocked_reason)host.append(el('p',state.buildings.blocked_reason,'building-blocked'));
  }
  function region(host, place) {
    if (!state?.buildings || ['lost','rift'].includes(state.map.world)) return;
    const rows=place.buildings||[],section=el('section',null,'atlas-buildings');section.setAttribute('aria-label','此地建筑');
    const heading=el('div',null,'building-heading');heading.append(el('h4','此地建筑'),el('span',`${rows.length}处`,'building-count'));section.append(heading);
    listing(section,place);host.append(section);
  }
  function marker(drawing, place) {
    if (!place.buildings?.length) return;
    const node = drawing.querySelector(`[data-atlas-location="${CSS.escape(place.id)}"]`); if (!node) return;
    const make = (tag, attrs) => { const n = document.createElementNS('http://www.w3.org/2000/svg', tag); Object.entries(attrs || {}).forEach(([k,v]) => n.setAttribute(k,v)); return n; };
    const badge = make('g', {class:'atlas-building-marker', transform:'translate(-51 -27)', 'data-building-count':place.buildings.length});
    const title = make('title'); title.textContent = place.buildings.map(r => r.name).join('、');
    const text = make('text', {x:19, y:2, 'text-anchor':'middle'}); text.textContent = `筑${place.buildings.length}`;
    badge.append(title, make('rect', {x:0,y:-14,width:38,height:23,rx:3}), text); node.append(badge);
  }
  function overview(host, place) {
    if (!state?.buildings || ['lost','rift'].includes(state.map.world)) return;
    const rows=place.buildings||[];if(!rows.length&&!place.current)return;
    const box=el('details',null,'building-overview');box.open=place.current;
    const heading=el('summary');heading.append(el('span','此地建筑'),el('span',`${rows.length}处`,'building-count'),icon('chevron-down'));box.append(heading);
    listing(box,place);
    host.append(box);
  }
  window.BuildingPanel = {bind:(data, command, lock) => {state=data;send=command;locked=lock;}, region, marker, overview};
})();

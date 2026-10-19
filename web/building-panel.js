/* Region-bound building projection; commands always validate the real address. */
(() => {
  let state, send, locked = () => true;
  const names = {city:'城', scenery:'景', industry:'业', artificiality:'筑', other:'其他', cave:'洞府', temple:'寺庙'};
  const el = (tag, text, cls = '') => { const n = document.createElement(tag); n.className = cls; if (text != null) n.textContent = text; return n; };
  function command(text, payload, unavailable = false) {
    const b = el('button', text); b.type = 'button'; b.dataset.atlasUnavailable = unavailable ? '1' : '0';
    b.dataset.buildingAction = payload.action; b.disabled = unavailable || locked(); b.onclick = () => send(payload); return b;
  }
  function region(host, place) {
    if (!state?.buildings || ['lost','rift'].includes(state.map.world)) return;
    const rows = place.buildings || [], section = el('section', null, 'atlas-buildings');
    section.setAttribute('aria-label', '此地建筑');
    const heading = el('div', null, 'building-heading'); heading.append(el('h4', '此地建筑'), el('span', String(rows.length), 'building-count')); section.append(heading);
    if (!rows.length) section.append(el('p', '此地尚无已登记的建筑。', 'muted'));
    for (const row of rows) {
      const item = el('article', null, 'building-row'); item.dataset.buildingId = row.id;
      const kind = row.subtype === 'cave' || row.subtype === 'temple' ? row.subtype : row.type;
      const seal = el('span', names[kind] || names.other, 'building-seal'); seal.dataset.kind = kind;
      const body = el('div', null, 'building-copy'), title = el('div', null, 'building-title');
      title.append(el('strong', row.name), el('small', `${row.level}级 · ${row.status === 'intact' ? '完好' : row.status === 'damaged' ? '受损' : '遗址'}`));
      if(row.population_name)title.append(el('small',`${row.use_name} · ${row.population_name}`,'building-city-kind'));
      body.append(title, el('p', row.description), el('small', row.status==='destroyed'?'原址待建':row.type==='scenery'?'自然景色':row.owned?'自有建筑':row.access ? '可自由进入' : '须联系所有者取得许可', 'muted'));
      item.append(seal, body);
      if (place.current){const actions=el('div',null,'building-row-actions');
        if(row.status!=='destroyed')actions.append(command(row.type==='scenery'?'观景':'进入', {action:'enter', building_id:row.id}, !row.can_enter));
        if(row.type!=='scenery')actions.append(command(row.status==='destroyed'?'重建':'营造', {action:'manage', building_id:row.id}));
        item.append(actions);}
      else item.append(el('small', '需亲赴此地', 'building-remote muted'));
      section.append(item);
    }
    if (place.current) {
      const controls = el('div', null, 'building-actions');
      controls.append(command(rows.some(r => r.subtype === 'cave' && r.access) ? '整修洞府' : '开辟洞府', {action:'construct'}, !state.buildings.can_construct));
      controls.append(command('筑城', {action:'city-plan'}, !state.buildings.can_build_city));
      if (state.buildings.can_establish_temple) controls.append(command('修建寺庙', {action:'temple-plan'}));
      section.append(controls);
      if (state.buildings.blocked_reason) section.append(el('p', state.buildings.blocked_reason, 'muted'));
    }
    host.append(section);
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
    box.append(el('summary',`建筑 · ${rows.length}`));
    const list=el('ul');
    for(const row of rows){const line=el('li'),label=el('span',`${names[row.subtype]||names[row.type]} · ${row.name} · ${row.level}级`);
      label.title=row.description;line.append(label);
      if(place.current){const actions=el('div',null,'building-row-actions');
        if(row.status!=='destroyed')actions.append(command(row.type==='scenery'?'观景':'进入',{action:'enter',building_id:row.id},!row.can_enter));
        if(row.type!=='scenery')actions.append(command(row.status==='destroyed'?'重建':'营造',{action:'manage',building_id:row.id}));line.append(actions);}
      list.append(line);
    }
    if(rows.length)box.append(list);
    if(place.current){const controls=el('div',null,'building-actions');controls.append(command(rows.some(r=>r.subtype==='cave'&&r.access)?'整修洞府':'开辟洞府',{action:'construct'},!state.buildings.can_construct));
      controls.append(command('筑城',{action:'city-plan'},!state.buildings.can_build_city));
      if(state.buildings.can_establish_temple)controls.append(command('修建寺庙',{action:'temple-plan'}));box.append(controls);}
    host.append(box);
  }
  window.BuildingPanel = {bind:(data, command, lock) => {state=data;send=command;locked=lock;}, region, marker, overview};
})();

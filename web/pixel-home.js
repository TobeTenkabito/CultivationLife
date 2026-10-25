/* Optional C composition: move original controls, project only already-public data. */
(() => {
  'use strict';
  const $ = s => document.querySelector(s), root = document.documentElement;
  const stage = $('.theme-play-area'), action = $('#action-card'), hud = $('#player-hud');
  const scene = document.createElement('section');
  scene.id = 'pixel-home'; scene.hidden = true; scene.setAttribute('aria-label', '山海图志');
  scene.innerHTML = `<figure class="pixel-scene"><div class="pixel-landscape"><img class="pixel-background" alt="" hidden></div>
    <figcaption><span id="pixel-place-summary"></span><button type="button" id="pixel-open-map">行程与势力 <span aria-hidden="true">↗</span></button></figcaption></figure>
    <aside class="pixel-local"><header><small id="pixel-world"></small><h3 id="pixel-place-name">一隅山河</h3><p id="pixel-place-tags"></p></header>
    <section><h4>天地气息</h4><dl id="pixel-qi"></dl></section>
    <section><h4>当地建筑 <span id="pixel-building-count"></span></h4><ul id="pixel-buildings"></ul></section>
    <p id="pixel-location-description"></p></aside>`;
  stage.insertBefore(scene, action);
  const workbench=document.createElement('div');workbench.className='pixel-workbench';
  scene.append(workbench);workbench.append(scene.querySelector('.pixel-local'));
  const eventPanels=['event-card','prison-card'].map(id=>{const node=$('#'+id),anchor=document.createComment(id+' original position');node.before(anchor);return {node,anchor};});
  const drawer = document.createElement('dialog');
  drawer.id = 'pixel-scenery-drawer'; drawer.className = 'appearance-dialog pixel-drawer';
  drawer.setAttribute('aria-labelledby','pixel-drawer-title');
  drawer.innerHTML = '<header class="pixel-drawer-heading"><div><small>山海图志</small><h2 id="pixel-drawer-title">此地绘景</h2></div><button type="button" aria-label="收起绘景" title="收起绘景"></button></header><div class="pixel-drawer-content"></div>';
  drawer.querySelector('button').append(VisualAssets.icon('close'));
  drawer.querySelector('button').onclick = () => drawer.close();
  document.body.append(drawer);
  const toggle = document.createElement('button');
  toggle.id = 'pixel-scenery-toggle'; toggle.type = 'button'; toggle.className = 'pixel-scenery-toggle'; toggle.hidden = true;
  toggle.title = '展开山海绘景'; toggle.setAttribute('aria-label','展开山海绘景');
  toggle.setAttribute('aria-haspopup','dialog'); toggle.setAttribute('aria-controls',drawer.id); toggle.setAttribute('aria-expanded','false');
  toggle.append(VisualAssets.icon('panel')); $('.brand').append(toggle);
  const portrait = document.createElement('img');
  portrait.className = 'pixel-portrait'; portrait.alt = ''; portrait.hidden = true;
  $('.hud-identity').prepend(portrait);
  const details = $('#player-details-dialog'), detailsContent = $('#player-details-content');
  const figure = document.createElement('figure');
  figure.className = 'pixel-details-art'; figure.hidden = true;
  const figureCanvas = document.createElement('canvas');
  figureCanvas.width = 256; figureCanvas.height = 288; figureCanvas.setAttribute('role','img');
  figure.append(figureCanvas);
  const natalFigure=document.createElement('img');natalFigure.className='pixel-natal-on-actor pixel-item-icon';natalFigure.alt='本命法宝';natalFigure.hidden=true;figure.append(natalFigure);
  const summary = document.createElement('div'); summary.className = 'pixel-character-summary';
  const characterHead = detailsContent.querySelector('.character-head');
  const characterRealm = detailsContent.querySelector('.realm');
  characterHead.before(summary); summary.append(characterHead,characterRealm,figure);
  const figureContext = figureCanvas.getContext('2d');
  let figureIdentity = null, figureRevision = 0;
  let current = null, revision = 0, drawerMode = false, layoutFrame = null;
  let painted=null,paintedKey='',browsing=null;
  const active = () => root.dataset.visual === 'pixel';
  async function updateFigure() {
    const identity = active() ? VisualAssets.actor(current?.player) : null;
    const natal=current?.natal_artifact;
    if(identity&&details.open&&natal?.bound)PixelLibrary.bind(natalFigure,{id:natal.item_id,crafted_artifact_id:natal.crafted_artifact_id},current);
    else {natalFigure.hidden=true;natalFigure.removeAttribute('src');}
    figureCanvas.setAttribute('aria-label',`${current?.player?.name || '人物'}的像素立绘`);
    if (!identity || identity !== figureIdentity) {
      figureRevision++; figureIdentity = null;
      figure.hidden = true; detailsContent.classList.remove('has-pixel-figure');
      figureContext.clearRect(0,0,figureCanvas.width,figureCanvas.height); delete figureCanvas.dataset.actor;
    }
    if (!identity || !details.open || identity === figureIdentity) return;
    const ticket = ++figureRevision;
    const bitmap = await VisualAssets.load(identity + '.figure');
    if (ticket !== figureRevision || !details.open || !active() || VisualAssets.actor(current?.player) !== identity || !bitmap) return;
    figureContext.clearRect(0,0,figureCanvas.width,figureCanvas.height);
    figureContext.imageSmoothingEnabled = false;
    figureContext.drawImage(bitmap,0,0);
    figureIdentity = identity; figureCanvas.dataset.actor = identity;
    figure.hidden = false; detailsContent.classList.add('has-pixel-figure');
  }
  new MutationObserver(updateFigure).observe(details,{attributes:true,attributeFilter:['open']});
  function placement() {
    if(active())stage.prepend(hud);
    drawerMode = active() && (matchMedia('(max-width:900px)').matches || window.GameNavigation?.isCompact());
    root.dataset.pixelDrawer = String(!!drawerMode);
    toggle.hidden = !drawerMode || !current;
    toggle.disabled = !$('#event-card').classList.contains('hidden') || !$('#prison-card').classList.contains('hidden');
    if (drawerMode) {
      const host = drawer.querySelector('.pixel-drawer-content');
      if (scene.parentNode !== host) host.append(scene);
      if(action.parentNode!==stage)hud.after(action);
      for(const {node}of eventPanels)stage.insertBefore(node,action);
    } else {
      if (drawer.open) drawer.close();
      if (active()) hud.after(scene);
      if(active()) {workbench.append(action);for(const {node}of eventPanels)stage.insertBefore(node,scene);}
      else {if(action.parentNode!==stage)stage.insertBefore(action,$('.journal-area'));for(const {node,anchor}of eventPanels)anchor.after(node);}
    }
    const cinematic=$('#event-cinematic');if(active()&&cinematic)hud.after(cinematic);
  }
  function arrange() {
    scene.hidden = !active();
    updateFigure();
    placement();
    if (!active()) {revision++; scene.dataset.assetKey = ''; portrait.hidden = true; portrait.removeAttribute('src');clearPainting();return;}
    hud.append($('.hud-resources')); $('.hud-resources').append($('#hud-opportunity'));
    $('.primary-actions').prepend($('#cultivation-core'));
    for (const name of ['rest', 'befriend_neighbors']) $('.primary-actions').append($(`[data-action=${name}]`));
    $('.secondary-actions')?.remove();
    $('#cultivation-core').classList.remove('core-summary');
    document.querySelectorAll('.primary-actions .action-cta').forEach(node => node.textContent = '›');
    $('.theme-signature span').textContent = '山海图志';
    if (current) update();
  }
  function fillList(node, rows, create) {
    node.replaceChildren(...rows.map(create));
  }
  function clearPainting() {
    painted?.dispose();painted=null;paintedKey='';
    const fallback=document.createElement('img');fallback.className='pixel-background';fallback.alt='';fallback.hidden=true;
    $('.pixel-landscape').replaceChildren(fallback);
  }
  function describe(id) {
    browsing=id;
    const compatible=current.map?.world===current.player.world;
    const location=compatible?current.map?.locations?.find(row=>row.id===id):null,local=compatible&&id===current.map?.current;
    $('#pixel-world').textContent=(current.player.world_name||'未知界面')+(compatible?(local?' · 此间行止':' · 远方见闻'):'');
    $('#pixel-place-name').textContent=location?.name||current.player.location_name||'所在未明';
    $('#pixel-place-tags').textContent=(location?.themes||[]).join(' · ');
    $('#pixel-location-description').textContent=location?.description||'';
    $('#pixel-qi').parentElement.hidden=!local;
    const buildings=location?.buildings||[];
    $('#pixel-building-count').textContent=buildings.length?String(buildings.length):'';
    fillList($('#pixel-buildings'),buildings,row=>{
      const node=document.createElement('li'),note=document.createElement('small');
      const entrance=local?window.BuildingPanel?.entrance(row.id):null;
      if(entrance)node.append(entrance);
      else {const title=document.createElement('b');title.textContent=row.name;node.append(title);}
      note.textContent=row.status==='destroyed'?'遗址':local?[row.use_name||({city:'城池',scenery:'景色',industry:'产业',artificiality:'建筑'})[row.type],row.type==='scenery'?'':`${row.level}级`].filter(Boolean).join(' · '):'需亲赴此地';
      node.append(note);return node;
    });
    if(!buildings.length){const li=document.createElement('li');li.textContent='此地暂无建筑记录';$('#pixel-buildings').append(li);}
    window.HomeMapModes?.describe(current,id);
  }
  async function update() {
    const p = current.player;
    $('#pixel-place-summary').textContent = `第 ${p.world_age ?? p.age} 年 · ${p.path_name || ''}`;
    const qi = p.qi_environment?.display || [];
    fillList($('#pixel-qi'), qi, row => {
      const wrap = document.createElement('div'), label = document.createElement('dt'), value = document.createElement('dd');
      label.textContent = row.name; value.textContent = Number(row.concentration).toLocaleString('zh-CN', {maximumFractionDigits:2});
      wrap.append(label, value); return wrap;
    });
    const mapKey=`${current.id}:${p.world}:${current.map?.current}`;
    if(paintedKey&&paintedKey!==mapKey)clearPainting();
    describe(paintedKey===mapKey&&browsing?browsing:current.map?.current);
    const mapButton = $('[data-panel-target=map]');
    $('#pixel-open-map').disabled = !mapButton || mapButton.disabled;
    const identity = VisualAssets.actor(p);
    const showArt = !drawerMode || drawer.open;
    const assetKey = `${active()}:${mapKey}:${identity}:${showArt}`;
    // Avoid reloading/clearing images on each normal game response.
    if (scene.dataset.assetKey === assetKey) return;
    const ticket = ++revision;
    scene.dataset.assetKey = assetKey;
    scene.dataset.art = 'text';
    portrait.hidden = true;
    const landscape = active() && showArt ? await PixelMap.landscape(p.world) : null;
    if (ticket !== revision || !active()) return;
    if(landscape&&current.map){
      if(paintedKey!==mapKey){clearPainting();painted=PixelMap.mount($('.pixel-landscape'),current.map,{onSelect:describe});paintedKey=mapKey;}
      window.HomeMapModes?.render(current,painted);
      scene.dataset.art='illustrated';
    }else if(showArt)clearPainting();
    if (!identity) return;
    const head = await VisualAssets.load(identity + '.portrait');
    if (ticket !== revision || !active()) return;
    if (head) {portrait.src = head.src; portrait.hidden = false;}
  }
  toggle.onclick = () => {if (!active() || !drawerMode || !current) return; drawer.showModal(); toggle.setAttribute('aria-expanded','true'); update();};
  drawer.addEventListener('close', () => toggle.setAttribute('aria-expanded','false'));
  drawer.addEventListener('click', event => {if (event.target !== drawer) return; const r = drawer.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) drawer.close();});
  $('#pixel-open-map').onclick = () => {if (drawer.open) drawer.close(); const button = $('[data-panel-target=map]'); if (button && !button.disabled){button.click();window.MapDirectory?.openTerritory('influence',browsing);}};
  window.addEventListener('resize', () => {cancelAnimationFrame(layoutFrame); layoutFrame = requestAnimationFrame(() => {placement(); if (active() && current) update();});});
  window.PixelHome = Object.freeze({arrange,closeDrawer(){if(drawer.open)drawer.close();},render(data) {current = data; placement(); updateFigure(); if (active()) {window.HomeMapModes?.render(data,painted);update();}}});
  arrange();
})();

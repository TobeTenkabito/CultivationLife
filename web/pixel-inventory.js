/* Move the original item controls; never reproduce their commands or eligibility. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id), enabled=()=>PixelLibrary.active();
  const text=(tag,value,cls='')=>{const node=document.createElement(tag);node.textContent=value;node.className=cls;return node;};
  const compactQuantity=new Intl.NumberFormat('zh-CN',{notation:'compact',maximumFractionDigits:1});
  let state=null,rows=new Map(),groups=[],selected=null,category='全部物品',saveId=null,currentRow=null,originalParent=null;
  const shell=document.createElement('section');shell.id='pixel-inventory';shell.hidden=true;
  shell.innerHTML='<nav class="pixel-bag-categories" aria-label="行囊分类"></nav><section class="pixel-bag-collection"><header><h3>袖里乾坤</h3><small class="pixel-bag-count"></small></header><div class="pixel-bag-tools"><input type="search" placeholder="寻找物品" aria-label="搜索行囊"><select aria-label="行囊分类"></select><select aria-label="物品排序"><option value="category">按分类</option><option value="name">按名称</option><option value="quantity">按数量</option></select></div><div class="pixel-bag-grid"></div><p class="pixel-bag-empty" hidden>没有符合条件的物品</p></section><aside class="pixel-bag-detail" aria-label="物品详情"></aside>';
  $('inventory-list').after(shell);
  const sheet=document.createElement('dialog');sheet.className='appearance-dialog pixel-item-sheet';sheet.setAttribute('aria-label','物品详情');
  sheet.innerHTML='<header><h3>物品详情</h3><button type="button" aria-label="关闭物品详情" title="关闭">×</button></header><div class="pixel-bag-detail"></div>';
  document.body.append(sheet);sheet.querySelector('button').onclick=()=>sheet.close();
  sheet.querySelector('button').replaceChildren(VisualAssets.icon('close'));
  sheet.addEventListener('click',event=>{if(event.target!==sheet)return;const r=sheet.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)sheet.close();});
  sheet.addEventListener('click',event=>{if(event.target.closest('.item button'))sheet.close();},true);
  sheet.addEventListener('close',()=>{const button=[...shell.querySelectorAll('[data-pixel-item]')].find(b=>b.dataset.pixelItem===selected);if(button?.isConnected)button.focus({preventScroll:true});});
  const mobile=()=>matchMedia('(max-width:800px)').matches||!!window.GameNavigation?.isCompact();
  const search=shell.querySelector('input'),categorySelect=shell.querySelector('select[aria-label="行囊分类"]'),sort=shell.querySelector('[aria-label="物品排序"]');
  function reset(){if(currentRow&&originalParent?.isConnected)originalParent.append(currentRow);currentRow=null;originalParent=null;}
  function inspect(key,expand=false){
    reset();selected=key;
    const row=rows.get(key);const item=state?.player.inventory.find(i=>i.id===key);
    const desktop=shell.querySelector('.pixel-bag-detail'),detail=expand&&mobile()?sheet.querySelector('.pixel-bag-detail'):desktop;
    desktop.replaceChildren();if(detail!==desktop)detail.replaceChildren();
    shell.querySelectorAll('[data-pixel-item]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.pixelItem===key)));
    if(!row||!item){if(sheet.open)sheet.close();return;}
    const artifact=(state.crafting_system?.artifacts||[]).find(a=>a.id===item.crafted_artifact_id);
    const status=item.is_natal_artifact||artifact?.is_natal?'本命':artifact?.tianji?(artifact.equipped?'当前神机':'未激活'):artifact||item.combat_bonus>0?'随身生效':'';
    const art=document.createElement('div');art.className='pixel-bag-art';art.append(PixelLibrary.image(item,state,128));
    detail.append(text('small',status,'pixel-item-status'),art,text('h3',item.name),text('p',`持有 ${Number(item.quantity).toLocaleString('zh-CN')} 件`,'muted'));
    if(artifact){const facts=document.createElement('dl');facts.className='pixel-item-stats';
      for(const [key,value]of Object.entries(artifact.actual_stats||{})){if(!value)continue;const line=document.createElement('div');line.append(text('dt',state.crafting_system.stat_names[key]||key),text('dd','+'+(['combat_power','max_hp','max_mp'].includes(key)?Number(value).toLocaleString('zh-CN',{maximumFractionDigits:1}):Number(value*100).toLocaleString('zh-CN',{maximumFractionDigits:1})+'%')));facts.append(line);}detail.append(facts);
    }
    originalParent=row.parentElement;currentRow=row;detail.append(row);
    if(expand&&mobile()&&!sheet.open)sheet.showModal();
  }
  function draw(){
    if(!state||!enabled())return;
    const query=search.value.trim().toLocaleLowerCase();
    let entries=state.player.inventory.filter(i=>(category==='全部物品'||groups.find(g=>g.ids.includes(i.id))?.name===category)&&i.name.toLocaleLowerCase().includes(query));
    if(sort.value==='name')entries=entries.slice().sort((a,b)=>a.name.localeCompare(b.name,'zh-CN'));
    if(sort.value==='quantity')entries=entries.slice().sort((a,b)=>b.quantity-a.quantity);
    const grid=shell.querySelector('.pixel-bag-grid');grid.replaceChildren();
    for(const item of entries){
      const button=document.createElement('button');button.type='button';button.className='pixel-item-tile';button.dataset.pixelItem=item.id;
      const artifact=(state.crafting_system?.artifacts||[]).find(a=>a.id===item.crafted_artifact_id);
      const rank=(item.tags||[]).find(t=>t.startsWith('realm:'));
      const marker=item.is_natal_artifact||artifact?.is_natal?'本命':(item.tags||[]).some(t=>['secret_art_core','secret_art_soul'].includes(t))&&rank?rank.split(':')[1]+'级':'';
      if(marker)button.append(text('small',marker,'pixel-item-marker'));
      const quantity=text('small','×'+compactQuantity.format(Number(item.quantity)),'pixel-item-quantity');quantity.title=Number(item.quantity).toLocaleString('zh-CN');
      button.append(quantity,PixelLibrary.image(item,state),text('span',item.name,'pixel-item-name'));
      if(artifact){const peers=state.crafting_system.artifacts.filter(a=>a.name===artifact.name);button.append(text('small',peers.length>1?artifact.mold_name+' · 实例 '+(peers.indexOf(artifact)+1):artifact.mold_name,'pixel-item-instance'));}
      button.onclick=()=>inspect(item.id,true);grid.append(button);
    }
    shell.querySelector('.pixel-bag-count').textContent=entries.length+' 类物品';shell.querySelector('.pixel-bag-empty').hidden=entries.length>0;
    shell.querySelectorAll('[data-bag-category]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.bagCategory===category)));categorySelect.value=category;
    if(!entries.some(i=>i.id===selected))selected=entries[0]?.id;
    inspect(selected,sheet.open&&mobile());
  }
  function render(data){
    reset();state=data;
    if(saveId!==data.id){saveId=data.id;category='全部物品';selected=null;search.value='';if(sheet.open)sheet.close();}
    shell.hidden=!enabled();$('inventory-list').hidden=enabled();
    if(!enabled()){if(sheet.open)sheet.close();return;}
    rows=new Map([...$('inventory-list').querySelectorAll('.item[data-item-id]')].map(row=>[row.dataset.itemId,row]));
    groups=[...$('inventory-list').querySelectorAll('.inventory-category')].map(node=>({name:node.querySelector('h3').textContent.split(' · ')[0],ids:[...node.querySelectorAll('.item')].map(r=>r.dataset.itemId)}));
    if(category!=='全部物品'&&!groups.some(g=>g.name===category))category='全部物品';
    const nav=shell.querySelector('nav');nav.replaceChildren();categorySelect.replaceChildren();
    for(const group of [{name:'全部物品',ids:data.player.inventory.map(i=>i.id)},...groups]){const button=text('button',group.name);button.type='button';button.dataset.bagCategory=group.name;button.append(text('small',group.ids.length));button.onclick=()=>{category=group.name;draw();};nav.append(button);categorySelect.add(new Option(group.name,group.name));}
    draw();
  }
  search.oninput=draw;sort.onchange=draw;categorySelect.onchange=()=>{category=categorySelect.value;draw();};
  window.addEventListener('game:theme-change',()=>{reset();if(state)render(state);});
  window.addEventListener('game:visual-ready',()=>{if(state&&enabled())draw();});
  window.addEventListener('game:panel-open',event=>{if(event.detail.name!=='inventory'&&sheet.open)sheet.close();});
  window.addEventListener('resize',()=>{if(sheet.open&&!mobile()){sheet.close();inspect(selected);}});
  window.PixelInventory=Object.freeze({reset,render});
})();

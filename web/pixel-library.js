/* Reviewed semantic mappings. Images and metadata load only in the optional view. */
(() => {
  'use strict';
  let manifest=null, pending=null;
  const bound=new Map();
  const active=()=>document.documentElement.dataset.visual==='pixel';
  function ensure(){
    if(!active())return Promise.resolve(null);
    if(!pending)pending=fetch('/api/visual-assets').then(r=>{if(!r.ok)throw new Error('assets');return r.json();}).then(value=>{
      manifest=value;refresh();window.dispatchEvent(new Event('game:visual-ready'));return value;
    }).catch(()=>null);
    return pending;
  }
  function resolve(item={},state={}){
    if(!manifest)return null;
    const artifact=(state.crafting_system?.artifacts||[]).find(row=>row.id===item.crafted_artifact_id);
    let id=artifact ? manifest.molds[artifact.mold_id]||'gear.other' : manifest.items[item.id||item.item_id];
    const tags=item.tags||[];
    if(!id && item.plant_id)id=manifest.plants[item.plant_id];
    if(!id && item.definition_id)id=manifest.crafting_materials[item.definition_id];
    if(!id){
      if(item.technique_id||tags.includes('technique_manual'))id='item.technique_manual';
      else if(tags.includes('secret_art_manual'))id='item.secret_manual';
      else if(tags.includes('root_manual'))id='item.root_book';
      else if(tags.includes('secret_art_core'))id='item.elemental_core';
      else if(tags.includes('secret_art_soul'))id='item.primordial_soul';
      else if(tags.includes('seed'))id='item.seed';
      else if(tags.includes('spirit_plant'))id='item.herb';
      else if(tags.includes('equipment')||tags.includes('artifact'))id='gear.other';
      else id='extra.unknown';
    }
    return manifest.assets[id]?{id,...manifest.assets[id]}:null;
  }
  function paint(image,item,state){
    const asset=active()?resolve(item,state):null;
    if(!asset){image.hidden=true;image.removeAttribute('src');return;}
    image.dataset.asset=asset.id;
    image.hidden=false;
    if(image.getAttribute('src')!==asset.file)image.src=asset.file;
    image.onerror=()=>{image.hidden=true;image.removeAttribute('src');image.dataset.imageFailed='true';};
  }
  function bind(image,item,state={}){if(!manifest)bound.set(image,{item,state});paint(image,item,state);if(active())ensure();return image;}
  function image(item,state={},size=64){const node=document.createElement('img');node.className='pixel-item-icon';node.alt='';node.width=node.height=size;node.loading='lazy';return bind(node,item,state);}
  function refresh(){for(const [node,value]of bound){if(node.isConnected)paint(node,value.item,value.state);}if(manifest)bound.clear();if(!active())document.querySelectorAll('.pixel-item-icon').forEach(node=>{node.hidden=true;node.removeAttribute('src');});}
  window.addEventListener('game:theme-change',()=>{if(active())ensure();refresh();});
  window.PixelLibrary=Object.freeze({active,ensure,resolve,image,bind,get catalog(){return manifest;}});
  if(active())ensure();
})();

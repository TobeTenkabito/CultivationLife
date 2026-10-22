/* Read-only social illustration of already-public people. No save fields or gameplay ports. */
window.NpcArt = (() => {
  'use strict';
  const pack=window.NpcArtCatalog, reserved=new Set(pack.reserved_fixed_ids);
  const own=(object,key)=>Object.prototype.hasOwnProperty.call(object,key);
  const active=()=>document.documentElement.dataset.visual==='pixel';
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  let data=null,people=new Map(),dialog=null,selectedEvent='',eventKey='';
  function validForm(n){
    return n && n.id && n.name && n.identity_known!==false && !n.ghost_host_body && !n.ghost_attachment &&
      !n.host_body && !n.possession && !n.transformed &&
      !(n.lineage_race&&n.lineage_race!==n.race) &&
      !n.transformation_loadouts?.[n.transformation_technique?.id]?.active?.length;
  }
  function select(n){
    if(!validForm(n))return null;
    if(own(pack.fixed,n.id)){
      const key=pack.fixed[n.id],a=pack.actors[key];
      return n.race===a.race&&n.path===a.path&&n.gender===a.gender?key:null;
    }
    // A pending named redesign must never silently acquire a generic face.
    if(reserved.has(n.id)||n.race!=='human'||!['dao','demonic'].includes(n.path)||!['male','female'].includes(n.gender)||!(n.age>=18))return null;
    const pool=pack.pools[`human.${n.path}.${n.gender}`];if(!pool?.length)return null;
    // Stable identity hash, independent of ordering, world, page and game RNG.
    let hash=2166136261;for(const c of String(n.id)){hash=Math.imul(hash^c.codePointAt(0),16777619)>>>0;}
    return pool[hash%pool.length];
  }
  function resolve(n){return n&&people.get(n.id)||n;}
  function image(n,kind,onFailure){
    const key=active()?select(n):null;if(!key)return null;
    const img=el('img',undefined,`npc-art-${kind}`);img.alt=`${n.name}${kind==='portrait'?'头像':'立绘'}`;
    const asset=pack.actors[key][kind];
    [img.width,img.height]=asset.size;
    img.dataset.art=key;img.loading='lazy';img.decoding='async';img.style.visibility='hidden';
    img.onload=()=>{img.style.visibility='visible';};
    img.onerror=()=>{img.hidden=true;img.removeAttribute('src');onFailure?.();};
    img.src=pack.base+asset.file;return img;
  }
  function context(value){
    data=value;people=new Map();if(dialog?.open)dialog.close();
    const p=value.player||{};
    const rows=[p.master,...(p.disciples||[]),...(p.disciple_requests||[]),value.dao_companion,
      ...(value.dao_friends||[]),...(value.concubine_system?.concubines||[]),
      ...(value.faction?.roster||[]).filter(n=>!n.is_player),...(value.world_npcs||[])];
    for(const row of rows)if(row?.id&&row.name)people.set(row.id,row);
  }
  function open(person){
    const n=resolve(person);if(!active()||!select(n))return;
    if(!dialog){
      dialog=el('dialog',undefined,'npc-art-dialog');dialog.id='npc-art-dialog';dialog.setAttribute('aria-labelledby','npc-art-title');
      dialog.addEventListener('keydown',event=>{if(event.key==='Escape')event.stopPropagation();});
      dialog.addEventListener('close',()=>dialog.replaceChildren());document.body.append(dialog);
    }
    dialog.replaceChildren();
    const head=el('header',undefined,'npc-art-heading'),title=el('h2',n.name);title.id='npc-art-title';
    const close=el('button','关闭');close.type='button';close.onclick=()=>dialog.close();head.append(title,close);
    const body=el('div',undefined,'npc-art-profile'),figure=image(n,'figure'),facts=el('div');
    if(figure)body.append(figure);
    for(const text of [n.title,[n.realm_name,n.path_name,n.race_name,n.gender_name].filter(Boolean).join(' · '),
      n.status,n.relationship,n.affinity==null?'':`好感 ${Number(n.affinity).toFixed(0)}`])if(text)facts.append(el('p',text));
    // These labels come only from the public row; no fresh remote whereabouts are inferred.
    if(n.world===null||n.perceived_alive===false)facts.append(el('p','依已有记录展示；当前去向与可交往状态以名册为准。','muted'));
    body.append(facts);dialog.append(head,body);dialog.showModal();
  }
  function avatar(row,person){
    const n=resolve(person);if(!active()||!select(n))return;
    const b=el('button',undefined,'npc-art-avatar');b.type='button';b.setAttribute('aria-label',`查看${n.name}的人物卡`);
    const img=image(n,'portrait',()=>b.remove());b.append(img);b.onclick=()=>open(n);row.prepend(b);
  }
  function selfAvatar(row,player,openDetails){
    const key=active()?window.VisualAssets?.actor(player):null;if(!key)return;
    const b=el('button',undefined,'npc-art-avatar');b.type='button';
    b.setAttribute('aria-label','查看自己的人物详情');b.setAttribute('aria-haspopup','dialog');
    b.setAttribute('aria-controls','player-details-dialog');b.onclick=openDetails;row.prepend(b);
    window.VisualAssets.load(key+'.portrait').then(bitmap=>{
      if(!b.isConnected)return;
      if(!bitmap||!active()){b.remove();return;}
      const img=el('img',undefined,'npc-art-portrait');img.alt=`${player.name}头像`;
      img.width=img.height=48;img.dataset.art=key;img.onerror=()=>b.remove();img.src=bitmap.src;b.append(img);
    });
  }
  function contactPortrait(button,n){
    const img=image(n,'portrait',()=>button.classList.remove('npc-art-person'));
    if(img){button.classList.add('npc-art-person');button.prepend(img);}
  }
  function contactFigure(header,n){
    if(!active()||!select(n))return;
    const seal=header.querySelector('.contact-seal'),b=el('button',undefined,'npc-art-contact-figure');
    b.type='button';b.setAttribute('aria-label',`查看${n.name}的人物卡`);
    const img=image(n,'figure',()=>{b.remove();if(seal)seal.hidden=false;});
    if(seal)seal.hidden=true;b.append(img);b.onclick=()=>open(n);header.prepend(b);
  }
  function event(value){
    const body=document.querySelector('#event-body');if(!body)return;
    let layout=document.querySelector('#npc-event-layout'),stage=document.querySelector('#npc-event-art');
    if(!layout){layout=el('div');layout.id='npc-event-layout';stage=el('aside');stage.id='npc-event-art';body.before(layout);layout.append(stage,body);}
    stage.replaceChildren();stage.hidden=true;layout.classList.remove('has-npc-art');
    if(!active()||!value||value.id==='SYS_POST_BATTLE_POSSESSION')return;
    const runtime=value.runtime||{},ids=[runtime.npc_id,...(runtime.members||[]).map(n=>n.npc_id),...(pack.event_participants[value.id]||[])];
    const participants=[...new Set(ids.filter(Boolean))].map(id=>people.get(id)).filter(n=>n&&select(n));
    if(!participants.length)return;
    const key=`${data?.id}:${value.id}:${participants.map(n=>n.id).join(',')}`;
    if(key!==eventKey){eventKey=key;selectedEvent=participants[0].id;}
    const n=participants.find(n=>n.id===selectedEvent)||participants[0];
    const b=el('button',undefined,'npc-event-person');b.type='button';b.setAttribute('aria-label',`查看${n.name}的人物卡`);
    const figure=image(n,'figure',()=>{if(stage.contains(figure)){stage.hidden=true;layout.classList.remove('has-npc-art');}});
    b.append(figure,el('span',n.name));b.onclick=()=>open(n);stage.append(b);
    if(participants.length>1){
      const nav=el('nav',undefined,'npc-event-participants');nav.setAttribute('aria-label','在场人物');
      for(const p of participants){const pick=el('button');pick.type='button';pick.title=p.name;pick.setAttribute('aria-label',p.name);pick.setAttribute('aria-pressed',String(p.id===n.id));pick.append(image(p,'portrait'));pick.onclick=()=>{selectedEvent=p.id;event(value);};nav.append(pick);}stage.append(nav);
    }
    stage.hidden=false;layout.classList.add('has-npc-art');
  }
  function close(){if(dialog?.open)dialog.close();}
  window.addEventListener('pagehide',()=>{close();people.clear();data=null;});
  return Object.freeze({context,select,image,avatar,selfAvatar,contactPortrait,contactFigure,event,open,close});
})();

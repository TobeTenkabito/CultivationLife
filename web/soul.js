/* All writes carry the displayed revision; presentation never settles time. */
window.SoulPanel=(()=>{
  let game,send,pending=false;
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const personal=el('section',undefined,'soul-panel');personal.id='soul-details';
  document.querySelector('#player-details-content').append(personal);
  const library=el('section',undefined,'soul-panel');library.id='soul-secrets';
  document.querySelector('#secret-art-card').append(library);
  async function run(action,extra){if(pending)return;const revision=game.soul.revision;pending=true;draw();try{await send({action,revision,...extra});}finally{pending=false;draw();}}
  function button(text,action,extra={},disabled=false){const b=el('button',text);b.type='button';b.dataset.soulAction=action;b.disabled=pending||game.soul.blocked||disabled;b.onclick=()=>run(action,extra);return b;}
  function choose(host,rows,text,action,extra={}){const w=el('div',undefined,'soul-actions'),s=el('select');for(const r of rows){const o=el('option',r.name);o.value=r.id;s.append(o);}const b=button(text,action,{},!rows.length);b.onclick=()=>run(action,{id:s.value,...extra});w.append(s,b);host.append(w);}
  function draw(){
    if(!game?.soul)return;const s=game.soul;
    personal.replaceChildren(el('h3',`身魂 · ${s.mode}`));const meters=el('div',undefined,'soul-grid');
    for(const [key,name]of [['body','体魄能量'],['soul','神魂能量']]){const m=el('div',undefined,'soul-meter'),p=el('progress');p.max=s[key].maximum;p.value=s[key].current;p.setAttribute('aria-label',name);m.append(el('span',`${name} ${Math.round(p.value)} / ${p.max}`),p);meters.append(m);}
    personal.append(meters,el('p','炼体提升体魄上限，神识提升神魂上限；调息恢复两项能量。肉身已毁时无法恢复体魄。','soul-note'));
    if(s.mode==='神游')personal.append(el('p',`战力降至35%，机缘效率+25%，天劫与雷劫伤害+75%。${s.remaining===null?'鬼修无离体期限。':`离体期限剩余 ${s.remaining} 年；超时本魂消散。`}`,'soul-warning'));
    if(s.stagnant)personal.append(el('p','道基永久受损：本世修为无法再精进。','soul-warning'));
    const a=el('div',undefined,'soul-actions');
    if(s.crisis)a.append(button(`抵御夺舍 · 成功率 ${Math.round(s.resistance_chance*100)}%`,'resist'));
    else{if(s.can_leave)a.append(button('元婴离体 · 神魂−10','leave'));if(s.possessed)a.append(button('离舍归魂 · 宿身将毁去','leave_host'));if(s.spirit.body_intact)a.append(button('归还原肉身','return'));}personal.append(a);
    if(s.mode==='神游')personal.append(el('p','夺舍：进入「俘虏」选择不高于自身境界的活俘虏。失败可能陨落；可提前研习阴魂续命诀并掌握鬼道功法，以转修鬼道续存。','soul-note'));
    const c=el('details');c.append(el('summary','道途转换'));
    for(const r of s.conversions){const card=el('div',undefined,'soul-card');card.append(el('strong',r.name),el('p',`消耗${r.cost}级对应气（现有${r.available}级）。不足时按比例折损修为，转换后：${r.realm_name}，第${r.layer}层。`),button('转修'+r.name,'convert',{id:r.id},!r.learned||!r.has_book||!!s.crisis));if(!r.learned||!r.has_book)card.append(el('p','需对应转换秘法及至少一门该道途功法。','soul-note'));c.append(card);}personal.append(c);
    library.replaceChildren(el('h3','身魂秘法'));const books=el('div',undefined,'soul-grid');
    for(const r of s.secrets){const card=el('div',undefined,'soul-card');card.append(el('strong',r.name),el('p',r.known?'已掌握':`研习消耗 ${r.price} 灵石 · ${r.realm_name}起`),button(r.known?'已掌握':'研习','study',{id:r.id},r.known||!r.eligible||!!s.crisis));books.append(card);}library.append(books);
    const known=s.secrets.find(r=>r.id==='second_nascent')?.known;
    document.querySelector('[data-panel-target="nascent"]').classList.toggle('hidden',!known);
    document.querySelector('#nascent-card').classList.toggle('hidden',!known);
    const host=document.querySelector('#nascent-content');host.replaceChildren();host.className='soul-panel';
    const h=el('div',undefined,'soul-hero');h.append(el('h3',s.second?`第二元婴 · ${s.second.name}`:'一身双魂'),el('p','以三年持续炼化提取元婴，每年消耗15神魂。第二元婴保留原主修为，独立参战。本尊须达到元婴且寿元未尽；神游失败后，仍存活且控制力≥50的第二元婴才可承接本魂。剧情、天劫与雷劫等特殊死亡不能承接。'));host.append(h);
    if(!s.second){if(s.refining){h.append(el('p',`炼化进度 ${s.refining.years} / 3 年`));host.append(button('继续炼化一年','refine',{id:s.refining.id}),button('取消炼化','cancel_refine'));}else choose(host,s.captives,'炼化一年','refine');return;}
    const n=s.second;h.append(el('p',`${n.realm} · 第${n.layer}层 ｜ 战力 ${Math.round(n.power)} ｜ 完整度 ${Math.round(n.integrity)}% ｜ 控制力 ${Math.round(n.control)} / 100`),el('p',`每${n.interval}年同化消耗${n.cost}神魂；下次：${n.due}岁。每次同化恢复20控制力；未同化每期降低2；下期未同化的反噬概率 ${(n.next_rebellion_chance*100).toFixed(1)}%。控制力不低于50时无反噬，降至0时为35%。`,'soul-warning'));
    h.append(el('p',`元婴年龄 ${n.age}岁 ｜ ${n.lifespan===null?'炼虚以上，不受寿元限制':`寿元 ${n.lifespan}岁 · 剩余 ${Math.max(0,n.lifespan-n.age)}年`}`));
    const upkeep=el('div',undefined,'soul-actions');upkeep.append(button(`立即同化 · −${n.cost}`,'assimilate'),button(n.auto?'自动同化：开':'自动同化：关','auto'));host.append(upkeep,el('h3','功法配置'));
    const learned=[...new Map([...s.techniques,...n.books].map(t=>[t.id,{...t,name:`${t.name} Lv.${t.level}`}])).values()];
    for(const [slot,label]of Object.entries({main:'主修',support:'辅修',combat:'杀伐',body:'炼体',sense:'神识',transformation:'变化'})){host.append(el('p',`${label}：${learned.find(t=>t.id===n.slots[slot])?.name||'未配置'}`));choose(host,learned,`配置${label}`,'technique',{slot});}
    host.append(el('h3','装备 · 最多三件'));n.equipment.forEach((item,index)=>host.append(button(`取回 ${item.name}`,'unequip',{index})));choose(host,s.equipment,'交付装备','equip');
    const more=el('details');more.append(el('summary','散去元婴'),el('p','第二元婴永久消失，装备返还；不再提供替死保护。'),button('永久散去第二元婴','dismiss'));host.append(more);
  }
  return {render(data,command){game=data;send=command;draw();}};
})();

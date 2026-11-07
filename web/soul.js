/* All writes carry the displayed revision; presentation never settles time. */
window.SoulPanel=(()=>{
  let game,send,pending=false,activation=null;
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const personal=el('section',undefined,'soul-panel');personal.id='soul-details';
  document.querySelector('#player-details-content').append(personal);
  async function run(action,extra){if(pending)return;const revision=game.soul.revision;pending=true;draw();try{await send({action,revision,...extra});}finally{pending=false;draw();}}
  function button(text,action,extra={},disabled=false){const b=el('button',text);b.type='button';b.dataset.soulAction=action;const unavailable=action==='resist'?!game.soul.can_resist:game.soul.blocked||!!game.soul.crisis;b.dataset.available=pending||unavailable||(action==='refine'&&!game.soul.can_refine)||disabled?'0':'1';b.disabled=b.dataset.available==='0';b.onclick=()=>run(action,extra);return b;}
  function secretArts(s){
    return [{id:'soul_leave',soul:true,name:'元婴离体',acquired:s.leave_unlocked,category:'离体',seal:'魂',
      status:s.leave_unlocked?(s.mode==='神游'?'神游中':'已解锁'):'未解锁',hint:'元婴期自动解锁',
      description:'元婴离开肉身，进入神游状态。原肉身留在原处，返回后可在人物详情中归体。'},
      ...s.secrets.map(r=>({id:'soul_'+r.id,soul:true,secret:r,acquired:r.known,name:r.name,
        category:r.id==='second_nascent'?'双魂':'转修',seal:r.id==='second_nascent'?'婴':'转',
        status:r.known?'已掌握':'探索传承',hint:`${r.realm_name}起 · 风景探索`,
        description:r.id==='second_nascent'?'炼化俘虏中的元婴及以上修士，提取第二元婴。可独立参战、配置功法与装备，须定期消耗神魂同化。':'掌握此秘法与对应道途功法后，点击发动秘法可预览代价，再确认转修。'}))];
  }
  function secretDetail(host,row){
    const s=game.soul,r=row.secret,leave=row.id==='soul_leave';
    const facts=el('dl',undefined,'secret-art-facts');
    const entries=leave?[['解锁境界','元婴期 · 自动解锁'],['施术消耗','10 点神魂能量'],['神游效果','战力降至35% · 机缘效率+25%'],['离体风险','天劫与雷劫伤害+75%'],['离体期限','非鬼修最多一个时间单位，逾期本魂消散；鬼修不限']]:[['修习境界',r.realm_name+'起'],['传承线索',r.acquisition_hint],['掌握状态',r.known?'已掌握':'尚未领悟']];
    for(const [label,value]of entries)facts.append(el('dt',label),el('dd',value));host.append(facts);
    if(!leave){
      if(!r.known){host.append(el('p','前往线索中的风景建筑，探索往事并领悟传承。','secret-art-objective'));return;}
      if(r.id==='second_nascent'){host.append(el('p','已掌握，可从「婴」入口管理第二元婴。','secret-art-complete'));return;}
      const target=s.conversions.find(c=>'path_'+c.id===r.id);
      if(!target){host.append(el('p','你当前已在此道途，无须再次转修。','secret-art-complete'));return;}
      const why=s.blocked?'当前状态无法施展秘法':s.crisis?'请先处理神魂夺舍危机':s.possessed?'寄身期间须先离舍再转道':!target.has_book?'须先掌握至少一门目标道途功法':'';
      const key=`${game.id}:${target.quote}`;
      const activated=activation===key;
      const activate=el('button',activated?'收起转修预览':'发动秘法','secret-art-command');
      activate.type='button';activate.dataset.soulActivate=r.id;
      activate.dataset.available=pending||why?'0':'1';activate.disabled=activate.dataset.available==='0';
      activate.onclick=()=>{activation=activated?null:key;host.replaceChildren();secretDetail(host,row);};host.append(activate);
      if(why)host.append(el('p',why,'secret-art-reason'));
      if(activated&&!why){const card=el('div',undefined,'soul-card');card.dataset.soulConversion=target.id;
        const qi={spirit:'灵气',demon:'魔气',yin:'阴气'}[target.qi]||target.qi;
        card.append(el('h4','转修'+target.name),el('p',`消耗${target.cost}级${qi}（现有${target.available}级）。不足时按比例折损修为；转修后：${target.realm_name}，第${target.layer}层。`),el('p','确认后机缘清零；转换道途不会移动所在地。','soul-warning'),button('确认转修'+target.name,'convert',{id:target.id,quote:target.quote}));host.append(card);
      }
      return;
    }
    const reason=s.blocked?'当前状态无法施展秘法':s.crisis?'请先抵御夺舍':!s.leave_unlocked?'元婴期自动解锁':s.possessed?'请先离舍归魂':s.mode==='神游'?'已处于神游':s.soul.current<10?'神魂能量不足':!s.can_leave?'当前无法离体':null;
    const b=button('元婴离体 · 神魂−10','leave',{},!!reason);
    b.className='secret-art-command';b.title=reason||'';b.disabled=b.disabled||(typeof busy!=='undefined'&&busy);host.append(b);
    if(reason)host.append(el('p',reason,'secret-art-reason'));
  }
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
    else{if(s.possessed)a.append(button('离舍归魂 · 宿身将毁去','leave_host'));if(s.spirit.body_intact)a.append(button('归还原肉身','return'));}personal.append(a);
    if(s.mode==='神游')personal.append(el('p','夺舍：进入「俘虏」选择不高于自身境界的活俘虏。失败可能陨落；可提前研习阴魂续命诀并掌握鬼道功法，以转修鬼道续存。','soul-note'));
    window.SecretArtPanel?.setSoulArts(secretArts(s),secretDetail);
    const known=s.secrets.find(r=>r.id==='second_nascent')?.known;
    document.querySelector('[data-panel-target="nascent"]').classList.toggle('hidden',!known);
    document.querySelector('#nascent-card').classList.toggle('hidden',!known);
    const host=document.querySelector('#nascent-content');host.replaceChildren();host.className='soul-panel';
    const h=el('div',undefined,'soul-hero');h.append(el('h3',s.second?`第二元婴 · ${s.second.name}`:'一身双魂'),el('p','以三年持续炼化提取元婴，每年消耗15神魂。第二元婴保留原主修为，独立参战。本尊须达到元婴且寿元未尽；神游失败后，仍存活且控制力≥50的第二元婴才可承接本魂。剧情、天劫与雷劫等特殊死亡不能承接。'));host.append(h);
    if(!s.second&&!s.can_refine)host.append(el('p','本尊须达到元婴期才能开始或继续炼化。已掌握的秘法及炼化进度保留。','soul-warning'));
    if(!s.second){if(s.refining){h.append(el('p',`炼化进度 ${s.refining.years} / 3 年`));host.append(button('继续炼化一年','refine',{id:s.refining.id}),button('取消炼化','cancel_refine'));}else choose(host,s.captives,'炼化一年','refine');return;}
    const n=s.second;h.append(el('p',`${n.realm} · 第${n.layer}层 ｜ 战力 ${Math.round(n.power)} ｜ 完整度 ${Math.round(n.integrity)}% ｜ 控制力 ${Math.round(n.control)} / 100`),el('p',`每${n.interval}年同化消耗${n.cost}神魂；下次：${n.due}岁。每次同化恢复20控制力；未同化每期降低2；下期未同化的反噬概率 ${(n.next_rebellion_chance*100).toFixed(1)}%。控制力不低于50时无反噬，降至0时为35%。`,'soul-warning'));
    h.append(el('p',`元婴年龄 ${n.age}岁 ｜ ${n.lifespan===null?'炼虚以上，不受寿元限制':`寿元 ${n.lifespan}岁 · 剩余 ${Math.max(0,n.lifespan-n.age)}年`}`));
    const upkeep=el('div',undefined,'soul-actions');upkeep.append(button(`立即同化 · −${n.cost}`,'assimilate'),button(n.auto?'自动同化：开':'自动同化：关','auto'));host.append(upkeep,el('h3','功法配置'));
    const learned=[...new Map([...s.techniques,...n.books].map(t=>[t.id,{...t,name:`${t.name} Lv.${t.level}`}])).values()];
    for(const [slot,label]of Object.entries({main:'主修',support:'辅修',combat:'杀伐',body:'炼体',sense:'神识',transformation:'变化'})){host.append(el('p',`${label}：${learned.find(t=>t.id===n.slots[slot])?.name||'未配置'}`));choose(host,learned,`配置${label}`,'technique',{slot});}
    host.append(el('h3','装备 · 最多三件'));n.equipment.forEach((item,index)=>host.append(button(`取回 ${item.name}`,'unequip',{index})));choose(host,s.equipment,'交付装备','equip');
    const more=el('details');more.append(el('summary','散去元婴'),el('p','第二元婴永久消失，装备返还；不再提供替死保护。'),button('永久散去第二元婴','dismiss'));host.append(more);
  }
  window.addEventListener('game:panel-open',()=>{if(activation!==null){activation=null;draw();}});
  return {render(data,command){if(data!==game)activation=null;game=data;send=command;draw();}};
})();

/* Independent dialog: no parent-panel hydration, no mutation during selection. */
(() => {
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  let game=null,env=null,dialog=null,data=null,selected='',generation=0,axis='cultivation',specialization='',domain='',method='material',batches=1;
  function reset(){generation++;dialog?.close();data=null;selected='';game=null;}
  function context(value,ports){if(game&&game.id!==value.id)reset();game=value;env=ports;if(dialog?.open)refresh();}
  function create(){
    if(dialog)return;
    dialog=el('dialog',null,'npc-development-dialog');dialog.id='npc-development-dialog';dialog.setAttribute('aria-labelledby','npc-development-title');
    dialog.addEventListener('keydown',e=>{if(e.key==='Escape')e.stopPropagation();});
    dialog.addEventListener('close',()=>generation++);document.body.append(dialog);
  }
  function header(){const h=el('header'),title=el('h2','NPC培养');title.id='npc-development-title';const close=el('button','关闭');close.type='button';close.onclick=()=>dialog.close();h.append(title,close);return h;}
  async function open(id='',kind='npc'){
    if(!game||!env)return;create();selected=id?`${kind}:${id}`:'';
    dialog.replaceChildren(header(),el('p','正在读取培养资料……'));if(!dialog.open)dialog.showModal();await refresh();
  }
  async function refresh(){
    const token=++generation,id=game.id;
    try{
      const result=await env.api(`/api/games/${id}/npc-development`);
      await window.PixelLibrary?.ensure(true);
      if(token!==generation||game?.id!==id||!dialog.open)return;
      data=result;if(!selected&&result.targets.length)selected=`${result.targets[0].kind}:${result.targets[0].id}`;paint();
    }catch(e){if(token===generation&&dialog.open)dialog.replaceChildren(header(),el('p',e.message));}
  }
  function choose(label,rows,value,change){const wrap=el('label',label),node=el('select');node.setAttribute('aria-label',label);
    for(const [key,name] of rows)node.add(new Option(name,key));node.value=value;node.onchange=()=>change(node.value);wrap.append(node);return wrap;}
  function paint(){
    dialog.replaceChildren(header());
    const layout=el('div',null,'npc-development-layout'),list=el('nav',null,'npc-development-list'),detail=el('section',null,'npc-development-detail');
    list.setAttribute('aria-label','培养对象');layout.append(list,detail);dialog.append(layout);
    for(const n of data.targets){
      const b=el('button',null,'npc-development-person');b.type='button';b.dataset.targetId=n.id;b.setAttribute('aria-pressed',String(selected===`${n.kind}:${n.id}`));
      const img=n.portrait&&window.NpcArt?.image(n.portrait,'portrait',null,true);if(img)b.append(img);
      const text=el('span',n.name);text.append(el('small',n.relations.join(' · ')));b.append(text);b.onclick=()=>{selected=`${n.kind}:${n.id}`;paint();};list.append(b);
    }
    if(!data.targets.length){detail.append(el('p','暂无可培养对象。已有的后代、弟子、道侣、俘虏或傀儡会出现在这里。'));return;}
    const n=data.targets.find(r=>`${r.kind}:${r.id}`===selected);
    if(!n){detail.append(el('p','此人当前不具备培养关系，或已离开培养名册。'));return;}
    const profile=el('div',null,'npc-development-profile'),art=el('div',null,'npc-development-art'),info=el('div');
    const figure=n.portrait&&window.NpcArt?.image(n.portrait,'figure',null,true);
    if(figure){const b=el('button');b.type='button';b.setAttribute('aria-label',`查看${n.name}完整立绘`);b.append(figure);b.onclick=()=>window.NpcArt.open(n.portrait,true);art.append(b);}
    else art.append(el('p','暂无适用形象','muted'));
    info.append(el('h3',n.name),el('p',[n.realm_name,n.path_name].filter(Boolean).join(' · ')),el('p',n.relations.join(' / ')));
    if(n.facts)info.append(el('p',`普通炼体 ${n.facts.body_training??'未明'} · 高阶肉身 ${n.facts.immortal_body_level} · 神识 ${n.facts.divine_sense_rank??'未明'}`));
    if(n.combat_power!=null)info.append(el('p',`自身战力 ${n.combat_power.toLocaleString('zh-CN')}`));
    if(n.energy){
      info.append(el('p',`${n.energy.name} · ${n.energy.force_tier>=2?'仙级':'凡级'}能源`),el('p',`能源耐久 ${n.energy.current} / ${n.energy.capacity} · ${n.energy.operation.compatible?`自供出手消耗 ${n.energy.action_cost}`:n.energy.operation.reason}`));
      info.append(el('p',n.energy.supply?`玩家供能已开启：能源不足时，凡阶攻击垫付5 MP${n.energy.immortal_attack_cost?`，仙阶攻击垫付${n.energy.immortal_attack_cost}元力`:''}。`:'玩家供能已关闭：能源不足则降为可自供的凡阶攻击，仍不足就停手。'));
      const pick=el('select');pick.setAttribute('aria-label','更换能源');
      for(const r of n.energy.replacements){const option=new Option(`${r.name} · 耐久${r.durability}/100 · ${r.reason||`每次${r.cost}`} · ${r.key.startsWith('spare:')?'已卸下':`行囊×${r.quantity}`}`,r.key);option.disabled=!r.allowed;pick.add(option);}
      const first=n.energy.replacements.find(r=>r.allowed);if(first)pick.value=first.key;
      const charge=el('button','更换能源');charge.id='npc-development-charge';charge.type='button';
      const validate=()=>{const r=n.energy.replacements.find(r=>r.key===pick.value);charge.disabled=!!n.reason||!r?.allowed||env.busy()||(r.key.startsWith('bag:')&&r.id===n.energy.source_id&&n.energy.current===100);};
      pick.onchange=validate;validate();charge.onclick=()=>submit(n,{action:'charge',source:pick.value});
      info.append(pick,charge,el('p','优先自供，不双重扣费；低一阶耗20、低两阶耗60、低三阶不能驱动；高一阶耗2、高两阶耗1、更高耗0.5。仙阶能源不能用于凡阶傀儡。卸下的能源保留剩余耐久。'));
    }else if(n.facts)info.append(el('p',`元力转化 ${Math.round(n.facts.conversion*100)}%`));
    profile.append(art,info);detail.append(profile);
    if(n.reason){detail.append(el('p',n.reason,'npc-development-reason'));return;}
    const controls=el('div',null,'npc-development-controls');detail.append(controls);
    controls.append(choose('培养方向',[['cultivation','修为'],['body','肉身'],['sense','神识'],['conversion','元力转化'],['technique','传授功法'],['technique_growth','研修功法'],['domain','邻域'],['body_art','肉身精修']],axis,v=>{axis=v;paint();}));
    let quoteAxis=axis;
    if(axis==='body_art'||axis==='domain'){
      const rows=axis==='body_art'?(n.specializations||[]):(n.domains||[]);
      let choice=axis==='body_art'?specialization:domain;
      if(!rows.some(r=>r.axis===choice))choice=rows[0]?.axis||axis;
      if(axis==='body_art')specialization=choice;else domain=choice;
      quoteAxis=choice;
      if(axis==='domain'){
        const d=rows.find(r=>r.axis===choice),b=el('button',d?.active?'已启用':'启用所选邻域');b.id='npc-domain-activate';b.type='button';
        b.disabled=!d?.rank||d.active||env.busy();b.onclick=()=>submit(n,{action:'activate_domain',axis:choice});detail.append(b);
      }
      controls.append(choose(axis==='body_art'?'肉身神通':'邻域传承',rows.map(r=>[r.axis,r.name+(r.unlock?` · 肉身${r.unlock}层解锁 · 当前${r.rank}重`:'' )]),choice,v=>{if(axis==='body_art')specialization=v;else domain=v;paint();}));
      detail.append(el('p',axis==='body_art'?'每轮精修一重，最高十重；保留天生造诣，肉身成长不会降低已学神通。仅能修习当前道途已开启的体系。':'每轮提升一阶，须先完成元力转化；培养所选传承后自动启用。仙界本源一旦确定，其他道统最多四阶。'));
    }
    if(axis==='technique_growth'){
      const rows=n.learned_techniques||[];
      if(!rows.some(r=>r.axis===specialization))specialization=rows[0]?.axis||axis;
      quoteAxis=specialization;
      controls.append(choose('研修功法',rows.map(r=>[r.axis,`${r.name} · ${r.rank}重`]),specialization,v=>{specialization=v;paint();}));
      detail.append(el('p','每轮一重，最高九重；机缘施教不能超过你对这部功法的掌握。专材研修不需要玩家重复消耗机缘。'));
    }
    if(axis==='technique'){
      const pick=el('select');pick.setAttribute('aria-label','传授功法');for(const t of n.techniques)pick.add(new Option(t.name,t.id));
      const b=el('button','传授所选功法');b.type='button';b.disabled=!n.techniques.length||env.busy();
      b.onclick=()=>submit(n,{action:'teach',content_id:pick.value});detail.append(pick,b,el('p','须满足目标的灵根、肉身与功法条件。已掌握的功法不会重复授予。'));return;
    }
    controls.append(choose('培养方式',[['material','NPC专材'],['infuse','机缘培养']],method,v=>{method=v;paint();}),
      choose('培养轮数',[[1,'1轮'],[5,'5轮'],[10,'10轮']],String(batches),v=>{batches=Number(v);paint();}));
    const q=n.quotes.find(q=>q.axis===quoteAxis&&q.method===method&&q.batches===batches);
    const note=el('div',null,'npc-development-quote');note.setAttribute('aria-live','polite');detail.append(note);
    if(q?.before)note.append(el('p',`${q.before} → ${q.after} · 实际 ${q.rounds} 轮`));
    if(q?.material_id)note.append(el('p',`${q.material_name}：需要 ${q.material_count}，持有 ${q.material_owned}`),el('p','不额外消耗玩家机缘。可在合法界面的坊市、交易和丹材探宝中取得。'));
    else if(q?.opportunity!=null)note.append(el('p',`机缘 ${q.opportunity} · 法力 ${q.mp} · 即时培养`));
    if(q?.reason)note.append(el('p',q.reason,'npc-development-reason'));
    const train=el('button','执行培养');train.id='npc-development-submit';train.type='button';train.disabled=!q?.can_train||env.busy();
    train.onclick=()=>submit(n,{action:'train',axis:quoteAxis,method,batches});detail.append(train,el('p',data.note,'muted'));
  }
  async function submit(n,payload){
    if(env.busy())return;
    dialog.querySelectorAll('.npc-development-layout button,.npc-development-layout select').forEach(n=>n.disabled=true);
    await env.mutate(`/api/games/${game.id}/npc-development`,{...payload,kind:n.kind,target_id:n.id,revision:data.revision});
    if(dialog.open)await refresh();
  }
  function link(parent,id,kind='npc'){
    const b=el('button','培养');b.type='button';b.className='npc-development-open';b.onclick=()=>open(id,kind);parent.append(b);return b;
  }
  document.querySelector('[data-panel-target="npc-development"]')?.addEventListener('click',()=>open());
  window.NpcDevelopment={context,open,reset,link};
})();

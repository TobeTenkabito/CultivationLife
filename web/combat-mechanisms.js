/* Read-only C layout. Round-end receipts are never inferred from animation hits. */
(() => {
  'use strict';
  const root=document.getElementById('battle-mechanisms');
  const strip=root.querySelector('[data-technique-strip]'),timeline=root.querySelector('[data-mechanism-timeline]');
  const select=root.querySelector('select'),caption=root.querySelector('[data-mechanism-caption]');
  const phase=root.querySelector('[data-mechanism-phase]');
  const mobile=matchMedia('(max-width: 640px)');
  const labels={prepared:'准备运转',paid:'实际支付',strike:'追加攻势',breach:'破法兑现',absorbed:'护持承伤',guard:'守御减损',
    restored:'恢复态势',refunded:'实付返还',cleanse:'净除减益',mobility:'步势变换',expired:'待用消散',interrupted:'运转中断'};
  const prices={fixed:'固定费用',proportional:'比例费用',mixed:'比例＋固定',recorded:'战前费用'};
  const amount=n=>Number.isFinite(n)?Number(n.toPrecision(4)).toLocaleString('zh-CN'):'—';
  const resource=k=>({mana:'MP',energy:'元力'}[k]??'资源（单位未记录）');
  const element=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  let report=null,rows=[],books=[],selection=null,roundIndex=0,confirmed=true,marker='',key='',clockPlan=null;
  const effects=row=>row?.voisinage?.technique_effects;
  const events=row=>(effects(row)?.events??[]).filter(e=>e.round===row.round);
  function stateText(b){
    const parts=[];
    if(b.pending)parts.push('效果待用');
    if(b.prepared)parts.push('已准备');
    if(b.used>=b.limit)parts.push('次数用尽');
    else if(b.cooldown>0)parts.push(`距可再触发 ${b.cooldown} 轮`);
    else if(!b.affordable)parts.push(`${resource(b.resource)}不足`);
    else parts.push('等待触发条件');
    return parts.join(' · ');
  }
  function eventText(e){
    const name=labels[e.event]??'机制记录';
    if(e.event==='paid'||e.event==='refunded')return `${name} ${amount(e.amount)} ${resource(e.resource)}`;
    if(e.measure==='unit_state_ratio'&&Number.isFinite(e.amount))return `${name} · 受效单位态势 ${amount(e.amount*100)}%`;
    // Legacy breach/mobility budgets are not HP or a universal state ratio.
    return name;
  }
  function cell(title,content,cls=''){
    const box=element('div',null,`mechanism-cell ${cls}`);box.append(element('small',title));
    if(Array.isArray(content)&&content.length){
      const list=element('ul');for(const value of content)list.append(element('li',value));box.append(list);
    }else box.append(element('p',typeof content==='string'?content:title==='此前记录'?'暂无此前记录':'本轮未记录触发','muted'));
    return box;
  }
  function lane(name,subtitle,past,present,next,cls=''){
    const row=element('article',null,`mechanism-lane ${cls}`),head=element('div',null,'mechanism-label');
    head.append(element('b',name),element('small',subtitle));
    row.append(head,cell('此前记录',past),cell(confirmed?'本轮 · 已确认':'本轮 · 演绎中',present,'mechanism-current'),cell('轮末状态',next));
    timeline.append(row);
  }
  function render(){
    if(!report||!rows.length)return;
    const row=rows[roundIndex],snapshot=effects(row)?.player_loadout;
    const recorded=rows.some(r=>Array.isArray(effects(r)?.player_loadout));
    if(!recorded){
      const seen=new Map();
      for(const r of rows.slice(0,roundIndex+(confirmed?1:0)))for(const e of events(r)){
        if(e.owner==='player'&&!seen.has(e.technique))seen.set(e.technique,{id:e.technique,name:e.name??'已记录功法'});
      }
      books=[...seen.values()].slice(0,7);
      if(selection&&!books.some(b=>b.id===selection))selection=null;
    }
    select.value=String(roundIndex);
    caption.textContent=confirmed?'费用与效果取自本轮结算；点选功法查看，重复点选返回全部。':'当前轮演绎中；费用与效果在轮末确认，点选功法可查看此前记录。';
    const oldFocus=strip.contains(document.activeElement)?document.activeElement.dataset.book:null;
    strip.replaceChildren();
    for(let i=0;i<(recorded?7:books.length);i++){
      const b=books[i];
      if(!b){const empty=element('div',null,'combat-technique empty');empty.append(element('small',`0${i+1}`),element('span','未装配'));strip.append(empty);continue;}
      const button=element('button',null,'combat-technique');button.type='button';button.dataset.book=b.id;
      button.setAttribute('aria-pressed',String(selection===b.id));button.setAttribute('aria-controls','combat-mechanism-timeline');
      const status=confirmed?snapshot?.find(s=>s.id===b.id):null;
      button.append(element('small',`0${i+1} · ${prices[b.pricing]??'费用未记录'}`),element('b',b.name),
        element('span',status?stateText(status):recorded?'本场装配':'已记录触发'),element('small',Number.isFinite(b.cost)?`单次 ${amount(b.cost)} ${resource(b.resource)}`:'历史费用未记录'));
      button.onclick=()=>{selection=selection===b.id?null:b.id;render();};strip.append(button);
      if(oldFocus===b.id)button.focus({preventScroll:true});
    }
    timeline.replaceChildren();
    for(const b of books.filter(b=>!selection||b.id===selection)){
      const previous=rows.slice(0,roundIndex).flatMap(r=>events(r).filter(e=>e.owner==='player'&&e.technique===b.id));
      const now=events(row).filter(e=>e.owner==='player'&&e.technique===b.id),s=snapshot?.find(s=>s.id===b.id);
      lane(b.name,b.level?`第 ${b.level} 重`:'等级未记录',previous.slice(-3).map(e=>`第 ${e.round} 轮 · ${eventText(e)}`),
        confirmed?now.map(eventText):'等待本轮结算记录',confirmed&&s?
          [stateText(s),`已用 ${s.used} / ${s.limit} 次`,`累计实付 ${amount(s.paid)} · 返还 ${amount(s.refunded)} ${resource(s.resource)}`]:
          confirmed?'此战报未记录状态':'轮末确认后显示');
    }
    // Only opponents/allies with actual recorded events appear; no hidden loadouts or balances.
    const visible=confirmed?events(row).filter(e=>e.owner!=='player'&&e.event!=='prepared'):[];
    const participants=row.voisinage?.participants??{};
    const others=[...new Set(visible.map(e=>e.owner))];
    for(const owner of others){
      lane(participants[owner]?.name??'参战者','本轮已见功法',[],visible.filter(e=>e.owner===owner).map(e=>`《${e.name??'已见功法'}》${eventText(e)}`),'未展示未使用的功法','observed-lane');
    }
    const field=row.voisinage;
    if(field?.fields?.length||field?.animation?.fields?.length){
      const names=(field.fields?.length?field.fields:field.animation.fields).map(f=>f.name??'邻域');
      const domainEvents=(field.animation?.effects??[]).map(e=>{
        const kind={strike:'杀伤',suppress:'镇压',seal:'封锁',restrict:'禁制',isolate:'隔离',restore_body:'修复肉身',restore_spirit:'稳定心神',restore_field:'修复邻域'}[e.kind]??'施权';
        return `${participants[e.owner]?.name??'施域者'} → ${participants[e.target]?.name??'目标'} · ${kind}`;
      });
      const relations=Object.entries(field.relations??{}).map(([id,r])=>`${participants[id]?.name??'参战者'} · ${{dominated:'庇护被突破',contested:'邻域相持',pressed:'承压但仍有庇护'}[r.relation]??'未受侵夺'}`);
      lane('邻域交锋',names.join(' · '),'沿原场域与支配关系',confirmed?(domainEvents.length?domainEvents:'本轮无施权效果记录'):'展开、相持与施权随战场时钟推进',
        confirmed?[...relations,`施权记录 ${field.animation?.effects?.length??0} · 介入记录 ${field.animation?.interventions?.length??0}`]:'本轮尚在演绎','domain-lane');
    }
    if(!timeline.childElementCount)timeline.append(element('p','此轮没有可展示的功法机制记录；原始过程可在下方逐轮演算中查看。','mechanism-empty'));
    if(!recorded&&!books.length)strip.append(element('p','此战报未记录七部功法装配，保留已记录的交锋与邻域事实。','muted'));
  }
  function sync(value,open){
    root.hidden=!open||!value?.rounds?.length;
    if(root.hidden)return;
    const next=JSON.stringify(value);
    if(key===next)return;
    key=next;report=value;rows=value.rounds.slice(-72);clockPlan=null;marker='';selection=null;
    books=rows.find(r=>Array.isArray(effects(r)?.player_loadout))?.voisinage.technique_effects.player_loadout??[];
    if(mobile.matches)selection=books[0]?.id??null;
    select.replaceChildren(...rows.map((r,i)=>{const option=element('option',`第 ${r.round} 轮`);option.value=String(i);return option;}));
    roundIndex=rows.length-1;confirmed=true;phase.textContent='轮末记录';render();
  }
  function advance(time,state,plan){
    if(root.hidden||!report)return;
    clockPlan=plan;
    const windows=plan.mechanismFrames??[];
    const active=windows.find(w=>time>=w.start&&time<w.end)??[...windows].reverse().find(w=>time>=w.start)??windows[0];
    if(!active)return;
    const index=rows.findIndex(r=>r.round===active.number);if(index<0)return;
    const done=time+1e-6>=active.settled||time>=plan.duration;
    const label=time>=plan.duration?'回放结束':done?`第 ${active.number} 轮 · 轮末确认`:state.domain?`邻域 · ${state.domain.label}`:state.phase;
    if(phase.textContent!==label)phase.textContent=label;
    const next=`${index}:${done}`;if(next===marker)return;marker=next;
    roundIndex=index;confirmed=done;render();
  }
  select.onchange=()=>{
    roundIndex=Number(select.value);confirmed=true;marker='';
    if(!clockPlan||!window.CombatReplay?.inspectRound(rows[roundIndex].round)){phase.textContent='轮末记录';render();}
  };
  mobile.addEventListener('change',()=>{if(mobile.matches&&!selection){selection=books[0]?.id??null;if(!root.hidden)render();}});
  window.CombatMechanisms=Object.freeze({sync,advance});
})();

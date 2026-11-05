/* The workbench selects ordinary quotes and invokes Registry commands only. */
window.DebugNpcDevelopment = (() => {
  'use strict';
  function create({execute, getSession, getCatalog}) {
    const el = window.GameUi.identifiedElement;
    const root=el('details',null,'debug-npc-development');root.append(el('summary','NPC培养调试 · 成长与能源'));
    root.append(el('p','在独立副本中检查人物、培养报价及受限原因。正式资格与费用照常生效；可用控制台快照恢复现场。'));
    const fields=el('div',null,'debug-npc-fields'),controls={};
    for(const [key,label] of Object.entries({target:'培养对象',action:'调试操作',axis:'培养方向',method:'培养方式',batches:'培养轮数',book:'传授功法',source:'更换能源'})){
      const wrap=el('label',label),select=el('select',null,`debug-npc-${key}`);
      select.setAttribute('aria-label',`调试${label}`);wrap.append(select);fields.append(wrap);controls[key]=select;
    }
    const profile=el('div',null,'debug-npc-profile'),status=el('pre',null,'debug-npc-status');status.setAttribute('role','status');
    const actions=el('div');actions.className='debug-actions';
    const refresh=el('button','读取培养对象','debug-npc-read'),apply=el('button','在副本执行','debug-npc-apply'),supply=el('button','切换傀儡供能','debug-npc-supply');
    for(const b of [refresh,apply,supply]){b.type='button';actions.append(b);}
    root.append(fields,profile,status,actions);
    let data=null,revision=null,generation=0,working=false;
    const target=()=>data?.view.targets[Number(controls.target.value)];
    function fill(control,rows,previous=control.value){
      control.replaceChildren();for(const row of rows){const option=new Option(row.label,row.value);option.disabled=!!row.disabled;control.add(option);}
      control.value=rows.some(r=>r.value===previous)?previous:rows.find(r=>!r.disabled)?.value||rows[0]?.value||'';
    }
    function visible(key,on){controls[key].parentElement.hidden=!on;}
    function invalidate(){
      generation++;data=null;revision=null;Object.values(controls).forEach(c=>c.disabled=true);
      apply.disabled=supply.disabled=true;profile.replaceChildren();status.textContent='请读取培养对象；副本变化后须重新读取。';
    }
    function render(){
      const n=target(),action=controls.action.value;profile.replaceChildren();apply.disabled=true;
      for(const key of ['axis','method','batches','book','source'])visible(key,false);
      if(!n){status.textContent='当前没有培养对象。可在副本中沿正常收徒、家族或御傀流程建立关系。';return;}
      profile.append(el('b',`${n.name} · ${n.relations.join(' / ')}`));
      const art=n.portrait&&window.NpcArt?.image(n.portrait,'portrait',null,true);if(art)profile.prepend(art);
      if(n.energy)profile.append(el('p',`${n.energy.name} · 耐久 ${n.energy.current}/${n.energy.capacity} · ${n.energy.operation.reason||`出手耗能 ${n.energy.action_cost}`}`));
      const labels={cultivation:'修为',body:'肉身',sense:'神识',conversion:'元力转化',domain:'邻域（默认）'};
      for(const option of [...(n.specializations||[]),...(n.domains||[]),...(n.learned_techniques||[])])labels[option.axis]=option.name;
      let reason=n.reason||'',detail=data.view.note;
      if(action==='train'){
        for(const key of ['axis','method','batches'])visible(key,true);
        fill(controls.axis,[...new Set(n.quotes.map(q=>q.axis))].map(axis=>({value:axis,label:labels[axis]||axis})));
        const q=n.quotes.find(q=>q.axis===controls.axis.value&&q.method===controls.method.value&&q.batches===Number(controls.batches.value));
        reason=reason||(!q?.can_train?(q?.reason||'当前没有可用报价'):'');
        if(q)detail=[q.before&&`${q.before} → ${q.after}`,q.material_id?`${q.material_name}：需要 ${q.material_count}，持有 ${q.material_owned}`:`机缘 ${q.opportunity??0} · 法力 ${q.mp??0}`,data.view.note].filter(Boolean).join('\n');
      }else if(action==='teach'){
        visible('book',true);fill(controls.book,n.techniques.map(t=>({value:t.id,label:t.name})));
        if(!n.techniques.length)reason=reason||'没有可传授的新功法';
        detail='目标灵根、肉身与转化条件由正式传法入口再次校验。';
      }else if(action==='activate_domain'){
        visible('axis',true);fill(controls.axis,(n.domains||[]).map(d=>({value:d.axis,label:`${d.name} · ${d.rank}阶${d.active?' · 已启用':''}`,disabled:!d.rank||d.active})));
        const d=(n.domains||[]).find(d=>d.axis===controls.axis.value);
        if(!d?.rank||d.active)reason=reason||'须先培养可启用的邻域';
      }else if(action==='charge'){
        visible('source',true);fill(controls.source,(n.energy?.replacements||[]).map(r=>({value:r.key,label:`${r.name} · 耐久${r.durability}/100${r.reason?' · '+r.reason:''}`,disabled:!r.allowed})));
        const r=n.energy?.replacements.find(r=>r.key===controls.source.value);
        if(!r?.allowed)reason=reason||'当前没有合法能源可更换';
        else if(r.key.startsWith('bag:')&&r.id===n.energy.source_id&&n.energy.current===100)reason=reason||'当前能源已满';
        detail='原能源卸下后保留剩余耐久，仙阶能源不能安装到凡阶傀儡。';
      }else reason=reason||'请选择已登记的调试操作';
      status.textContent=[reason||'当前报价可执行；提交时仍会复核。',detail].filter(Boolean).join('\n');
      apply.disabled=working||!!reason;
    }
    async function read(){
      if(working)return;if(!getSession()){invalidate();status.textContent='请先创建调试副本。';return;}
      const token=++generation,session=getSession();working=true;refresh.disabled=true;apply.disabled=supply.disabled=true;
      try{
        const result=await execute('npc development inspect',null,{arguments:{}},true);
        if(!result||session!==getSession()||token!==generation){invalidate();return;}
        data=result.data;revision=result.revision;
        const args=getCatalog().find(c=>c.name==='npc development')?.arguments||[];
        const choices=key=>(args.find(a=>a.name===key)?.enum||[]).filter(v=>v!==null);
        const names={train:'培养成长',teach:'传授功法',activate_domain:'启用邻域',charge:'更换能源',infuse:'机缘培养',material:'NPC专材'};
        fill(controls.target,data.view.targets.map((n,i)=>({value:String(i),label:`${n.name} · ${n.kind}`})));
        for(const key of ['action','method','batches'])fill(controls[key],choices(key).map(v=>({value:String(v),label:names[v]||`${v}轮`})));
        Object.values(controls).forEach(c=>c.disabled=false);
        supply.textContent=data.supply_enabled?'关闭玩家傀儡供能':'开启玩家傀儡供能';supply.disabled=false;
      }finally{working=false;refresh.disabled=false;if(data)render();}
    }
    async function submit(command,args){
      if(working||!data)return;working=true;apply.disabled=supply.disabled=true;Object.values(controls).forEach(c=>c.disabled=true);
      const request_key=Array.from(crypto.getRandomValues(new Uint32Array(4)),n=>n.toString(16)).join('-');
      try{await execute(command,null,{arguments:args,expected_revision:revision,request_key});}
      finally{working=false;invalidate();await read();}
    }
    refresh.onclick=read;for(const control of Object.values(controls))control.onchange=render;
    apply.onclick=()=>{
      if(apply.disabled)return;const n=target();if(!n)return;
      const action=controls.action.value,args={action,kind:n.kind,target_id:n.id};
      if(action==='train')Object.assign(args,{axis:controls.axis.value,method:controls.method.value,batches:Number(controls.batches.value)});
      if(action==='teach')args.content_id=controls.book.value;
      if(action==='activate_domain')args.axis=controls.axis.value;
      if(action==='charge')args.source=controls.source.value;
      submit('npc development',args);
    };
    supply.onclick=()=>{if(data&&!supply.disabled)submit('setting set',{setting:'puppet_supply',enabled:!data.supply_enabled});};
    invalidate();return {element:root,invalidate};
  }
  return {create};
})();

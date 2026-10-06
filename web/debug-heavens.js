/* Registry-backed heavens workbench. It never changes the ordinary save. */
window.DebugHeavens = (() => {
  'use strict';
  function create({execute, hasSession}) {
    const el=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
    const root=el('details');root.id='debug-heavens';
    root.append(el('summary','诸天调试 · 状态与行动'));
    const hint=el('p','先创建调试副本，再读取诸天。选定目标后可查看限制、预览投入并执行；仍遵循地点、修为和事件暂停规则。');
    const fields=el('div');fields.className='debug-heavens-fields';
    const target=el('select'),action=el('select');target.id='debug-heavens-target';action.id='debug-heavens-action';
    for(const [label,control] of [['诸天目标',target],['诸天行动',action]]){const field=el('label',label);field.append(control);fields.append(field);}
    const detail=el('p'),quote=el('pre');quote.id='debug-heavens-quote';quote.setAttribute('role','status');
    const advanced=el('details');advanced.append(el('summary','行动参数'));
    const options=el('textarea');options.id='debug-heavens-options';options.setAttribute('aria-label','诸天行动参数 JSON');options.rows=3;advanced.append(options);
    const actions=el('div');actions.className='debug-actions';
    const refresh=el('button','读取诸天'),preview=el('button','预览行动'),apply=el('button','在副本执行');
    for(const b of [refresh,preview,apply]){b.type='button';actions.append(b);}
    let view=null,rows=[],snapshotRevision=null,previewed=null,choiceVersion=0;
    const invalidate=()=>{choiceVersion++;view=null;previewed=null;snapshotRevision=null;target.disabled=true;action.disabled=true;preview.disabled=true;apply.disabled=true;quote.textContent='状态尚未读取，或副本已发生变化，请重新读取。';};
    function selected(){return rows[Number(action.value)];}
    function renderAction(){
      choiceVersion++;
      const row=selected();previewed=null;apply.disabled=true;preview.disabled=!row?.enabled;
      options.value=JSON.stringify(row?.options||{},null,2);
      detail.textContent=row ? (row.enabled ? `${row.label} · ${row.action} · 预计 ${row.years||0} 年` : row.reason||'当前不可用') : '此目标当前没有可办理的行动。';
      quote.textContent='预览后可在独立副本执行。';
    }
    function renderActions(){
      rows=[];const seen=new Set();
      function walk(value){
        if(!value||typeof value!=='object')return;
        if(Array.isArray(value)){value.forEach(walk);return;}
        if(value.action&&value.label&&value.target_id===target.value){
          const key=JSON.stringify([value.action,value.target_id,value.options]);
          if(!seen.has(key)){seen.add(key);rows.push(value);}
        }
        Object.values(value).forEach(walk);
      }
      if(target.value==='configuration'){
        for(const [key,label] of [['generation_enabled','发现新联系'],['watch','关注通知'],['pause_on_opportunity','见闻暂停']]){
          rows.push({action:'configure',label:`${view[key]?'关闭':'开启'}${label}`,options:{[key]:!view[key]},enabled:true});
        }
      }else{
        walk(view);
        const task=(view.tasks||[]).find(t=>t.id===target.value&&['reserved','running','paused'].includes(t.status));
        if(task)for(const [key,label] of [['resume','继续任务'],['cancel','取消任务']])rows.push({action:key,label,target_id:task.id,options:{},enabled:true});
      }
      action.replaceChildren();rows.forEach((row,i)=>{const option=el('option',`${row.label}${row.enabled?'':' · 不可用'}`);option.value=i;action.append(option);});
      action.disabled=!rows.length;renderAction();
    }
    async function read(){
      if(!hasSession()){invalidate();quote.textContent='请先使用“创建调试副本”。';return;}
      const previous=target.value;
      const result=await execute('heavens inspect',null,{arguments:{}},true);
      if(!result)return;
      view=result.data.view;snapshotRevision=result.revision;
      const targets=new Map([['configuration','诸天偏好']]);
      for(const row of [...(view.incidents||[]),...(view.anomalies||[]),...(view.conflicts||[]),...(view.sites||[]),...(view.omens||[]),view.mirror,view.ruins,view.frontier,view.campaign]){
        if(row?.id)targets.set(row.id,`${row.world_name?row.world_name+' · ':''}${row.name||row.id}`);
      }
      for(const task of view.tasks||[])if(['reserved','running','paused'].includes(task.status))targets.set(task.id,`进行中 · ${task.action}`);
      target.replaceChildren();for(const [id,name] of targets){const option=el('option',name);option.value=id;target.append(option);}
      target.value=targets.has(previous)?previous:(view.incidents||[]).find(r=>r.current)?.id||'configuration';target.disabled=false;
      await readTarget();
    }
    async function readTarget(){
      if(!view)return;
      target.disabled=true;action.disabled=true;preview.disabled=true;apply.disabled=true;
      if(target.value!=='configuration'&&!(view.tasks||[]).some(t=>t.id===target.value)){
        const result=await execute('heavens inspect',null,{arguments:{target_id:target.value}},true);
        if(!result){invalidate();return;}view=result.data.view;snapshotRevision=result.revision;
      }
      target.disabled=false;renderActions();
    }
    function payload(){
      const row=selected();if(!row)throw new Error('请先选择行动。');
      const result={action:row.action,options:JSON.parse(options.value)};
      if(row.target_id)result.target_id=row.target_id;
      return result;
    }
    refresh.onclick=read;target.onchange=readTarget;action.onchange=renderAction;
    options.oninput=()=>{choiceVersion++;previewed=null;apply.disabled=true;};
    preview.onclick=async()=>{
      try{
        const args=payload(),version=choiceVersion,result=await execute('heavens preview',null,{arguments:args});
        if(!result||version!==choiceVersion){apply.disabled=true;return;}
        previewed=args;snapshotRevision=result.revision;
        const q=result.data;quote.textContent=`预计 ${q.years||0} 年\n投入：${JSON.stringify(q.costs||{})}\n${q.message||q.warning||'执行仍会核对当前条件；遇事件暂停。'}`;apply.disabled=false;
      }catch(error){quote.textContent=error.message;apply.disabled=true;}
    };
    apply.onclick=async()=>{
      if(!previewed)return;
      const args=previewed;apply.disabled=true;
      const requestKey=Array.from(crypto.getRandomValues(new Uint32Array(4)),n=>n.toString(16)).join('-');
      const result=await execute('heavens act',null,{arguments:args,expected_revision:snapshotRevision,request_key:requestKey});
      if(result)await read();else invalidate();
    };
    root.append(hint,fields,detail,advanced,quote,actions);invalidate();
    return {element:root,invalidate};
  }
  return {create};
})();

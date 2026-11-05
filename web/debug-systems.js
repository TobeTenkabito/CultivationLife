/* Registry-driven access to every reviewed gameplay capability. */
window.DebugSystems = (() => {
  'use strict';
  function create({execute, getSession, getCatalog}) {
    const el = (tag, text, id) => { const n=document.createElement(tag);if(text)n.textContent=text;if(id)n.id=id;return n; };
    const root=el('details',null,'debug-systems');root.append(el('summary','功能调试 · 全部系统'));
    root.append(el('p','准备副本后选择功能并填写参数。必填项标有 *；可选项留空使用原默认值。人物、材料和修订号从下方系统数据读取。所有执行仍遵守正式资格与费用。'));
    const search=el('input',null,'debug-system-search');search.type='search';search.placeholder='筛选命令，例如 upper、soul、fleet';search.setAttribute('aria-label','筛选调试功能');
    const command=el('select',null,'debug-system-command');command.setAttribute('aria-label','调试功能');
    const description=el('p'),fields=el('div',null,'debug-system-fields');
    const section=el('select',null,'debug-system-section');section.setAttribute('aria-label','查看系统数据');
    const view=el('pre',null,'debug-system-view'),status=el('p',null,'debug-system-status');status.setAttribute('role','status');
    const actions=el('div');actions.className='debug-actions';
    const prepare=el('button','准备副本并读取功能','debug-system-prepare'),inspect=el('button','只读检查系统','debug-system-inspect'),apply=el('button','在副本执行','debug-system-apply');
    for(const b of [prepare,inspect,apply]){b.type='button';actions.append(b);}
    root.append(search,command,description,fields,actions,status,section,view);
    let capabilities=[],revision=null,working=false,generation=0,controls=[];
    const selected=()=>getCatalog().find(c=>c.name===command.value);
    function invalidate(){generation++;revision=null;apply.disabled=inspect.disabled=true;status.textContent='副本尚未准备或已变化，请重新读取。';view.textContent='';}
    function render(){
      fields.replaceChildren();controls=[];const row=selected(),cap=capabilities.find(c=>c.command===command.value);
      description.textContent=row?`${row.usage}\n${cap?.dlc||'本体'}${cap?.content_available===false?' · DLC未开启':''}${cap?.shortcut?' · 调试捷径':''}`:'没有匹配的功能。';
      for(const arg of row?.arguments||[]){
        const required=row.input_schema.required.includes(arg.name),types=Array.isArray(arg.type)?arg.type:[arg.type];
        let input;
        if(arg.enum||types.includes('boolean')){
          input=el('select');input.add(new Option(required?'请选择':'默认（不提交）',''));
          for(const value of (arg.enum||[true,false]).filter(v=>v!==null)) input.add(new Option(String(value),JSON.stringify(value)));
        }else if(types.includes('object')||types.includes('array')){
          input=el('textarea');input.rows=3;input.placeholder=types.includes('array')?'JSON 数组':'JSON 对象';
        }else{input=el('input');input.type=types.includes('number')||types.includes('integer')?'number':'text';
          if(input.type==='number'){input.step=types.includes('integer')?'1':'any';if(arg.minimum!==undefined)input.min=arg.minimum;if(arg.maximum!==undefined)input.max=arg.maximum;}}
        input.id=`debug-system-arg-${arg.name}`;input.setAttribute('aria-label',arg.name);input.required=required;
        const label=el('label',arg.name+(required?' *':''));label.append(input);fields.append(label);
        if(arg.properties||arg.items){const hint=el('details'),summary=el('summary','参数结构');hint.append(summary,el('pre',JSON.stringify(row.input_schema.properties[arg.name],null,2)));label.append(hint);}
        controls.push({arg,input,required,types});
      }
      apply.textContent=row?.type==='preview'?'只读预览操作':'在副本执行';
      apply.disabled=working||revision===null||!row||cap?.content_available===false;
    }
    function filter(){
      const previous=command.value;command.replaceChildren();
      for(const c of capabilities.filter(c=>`${c.command} ${c.operation} ${c.dlc||''}`.toLowerCase().includes(search.value.toLowerCase())))command.add(new Option(c.command,c.command));
      if([...command.options].some(o=>o.value===previous))command.value=previous;render();
    }
    async function read(){
      if(working)return;if(!getSession()){status.textContent='请先创建调试副本。';return;}
      working=true;prepare.disabled=true;apply.disabled=inspect.disabled=true;const session=getSession();
      try{
        const state=await execute('debug status',null,{},true);
        if(!state||session!==getSession())return;
        const result=await execute('game view',null,{arguments:{},expected_revision:state.revision,request_key:crypto.randomUUID()},true);
        if(!result||session!==getSession())return;
        const token=generation,metadata=await execute('capability list',null,{},true);
        if(!metadata||session!==getSession()||token!==generation)return;
        capabilities=metadata.data.covered;revision=metadata.revision;
        const previous=section.value;section.replaceChildren();
        for(const key of result.data.view.sections)section.add(new Option(key,'/'+key));
        if([...section.options].some(o=>o.value===previous))section.value=previous;
        status.textContent='副本已准备。只读检查不保存临时整理；若出现新生成的编号，请先用 game view 提交该状态。';
        filter();inspect.disabled=false;
      }finally{working=false;prepare.disabled=false;render();}
    }
    async function inspectSection(){
      if(working||revision===null)return;working=true;inspect.disabled=apply.disabled=true;
      const token=generation,session=getSession();
      try{
        const result=await execute('game inspect',null,{arguments:{pointer:section.value},expected_revision:revision},true);
        if(result&&token===generation&&session===getSession())view.textContent=JSON.stringify(result.data.view,null,2);
        else invalidate();
      }finally{working=false;inspect.disabled=revision===null;render();}
    }
    async function run(){
      if(working||revision===null)return;const row=selected();if(!row)return;
      const args={};
      try{
        for(const {arg,input,required,types} of controls){
          if(!input.reportValidity())return;if(input.value===''){if(required)throw Error('请填写 '+arg.name);continue;}
          args[arg.name]=(arg.enum||types.includes('boolean')||types.includes('array')||types.includes('object'))?JSON.parse(input.value):
            types.includes('string')?input.value:Number(input.value);
        }
      }catch(error){status.textContent='参数错误：'+error.message;return;}
      working=true;apply.disabled=inspect.disabled=true;
      try{
        const request={arguments:args,expected_revision:revision};
        if(row.type!=='preview'&&row.type!=='query')request.request_key=crypto.randomUUID();
        const result=await execute(row.name,null,request,false);
        if(result){view.textContent=JSON.stringify(result.data,null,2);status.textContent='操作已完成。写入后请重新准备副本再执行下一项。';}
        else invalidate();
      }finally{working=false;inspect.disabled=revision===null;render();}
    }
    search.oninput=filter;command.onchange=render;prepare.onclick=read;inspect.onclick=inspectSection;apply.onclick=run;
    invalidate();return {element:root,invalidate};
  }
  return {create};
})();

(() => {
  const el = (tag, text, cls='') => { const node=document.createElement(tag); if(text!=null)node.textContent=text; node.className=cls; return node; };
  const number = value => Number(value || 0).toLocaleString('zh-CN', {maximumFractionDigits:2});
  const statNames = {combat_power:'战斗力',max_hp:'气血',max_mp:'法力',opportunity_efficiency:'机缘效率',body_training_efficiency:'炼体效率',divine_sense_efficiency:'神识效率',tribulation_reduction:'渡劫减伤',breakthrough_bonus:'突破加成'};
  window.MerchantCommissionForm = (system, alliance, act, canUse, preview) => {
    const details=el('details'); details.append(el('summary','发布委托'));
    const form=el('form',null,'merchant-post'); details.append(form);
    const field=(name,input) => { const label=el('label',name); label.append(input); input.setAttribute('aria-label',name); form.append(label); return input; };
    const options=(select,rows) => { select.replaceChildren(); rows.forEach(row=>{const option=el('option',row.name);option.value=row.id;select.append(option);}); };
    const kind=field('委托类型',el('select')); options(kind,Object.entries(system.kinds).map(([id,name])=>({id,name})));
    const world=field('目标界面',el('select'));
    const category=field('材料分类',el('select')); options(category,[{id:'crafting',name:'炼器材料'},{id:'formation',name:'阵法材料'}]);
    const material=field('所需材料或道具',el('select'));
    const target=field('悬赏目标',el('select'));
    const tier=field('原材料等级',el('select'));
    const mold=field('炼器模具',el('select')); options(mold,system.molds || []);
    const stars=field('星级',el('select')); options(stars,[1,2,3,4,5].map(i=>({id:i,name:'★'.repeat(i)})));
    const quantity=field('材料或道具数量',el('input')); quantity.type='number';quantity.min=1;quantity.max=99;quantity.value=1;quantity.required=true;
    const metrics=el('fieldset',null,'merchant-metrics'); metrics.append(el('legend','阵法六维最低要求（0表示不限）'));
    const metricInputs={};
    Object.entries(system.metric_names || {}).forEach(([id,name])=>{const label=el('label',name),input=el('input');input.type='number';input.min=0;input.max=100;input.step='.01';input.value=0;input.setAttribute('aria-label',`${name}最低要求`);label.append(input);metrics.append(label);metricInputs[id]=input;});
    metrics.append(el('p','原料等级决定工坊可承接范围；六维相互制约，单维上限不能保证同时达到。成品沿用九宫真实材料和阵法效果。','muted'));
    form.append(metrics);
    const principal=field('悬赏本金',el('input'));principal.type='number';principal.min=1;principal.max=1e15;principal.required=true;
    const quoteText=el('p','请选择委托条件，获取商盟报价。','merchant-quote');quoteText.setAttribute('aria-live','polite');
    const overview=el('section',null,'merchant-product-preview');overview.setAttribute('aria-live','polite');
    const refresh=el('button','查看报价与成品概览');refresh.type='button';
    const submit=el('button','支付并发布委托');submit.type='submit';
    form.append(quoteText,overview,refresh,submit);
    let quoted=null, requestSequence=0, timer=null;
    const enableSubmit=enabled=>{submit.disabled=!enabled;submit.dataset.merchantUnavailable=enabled?'0':'1';};enableSubmit(false);
    const data=()=>({alliance_id:alliance.id,kind:kind.value,source_world:world.value,material_category:category.value,
      definition_id:material.value,target_id:target.value,material_tier:Number(tier.value),mold_id:mold.value,
      stars:Number(stars.value),quantity:['supply','item'].includes(kind.value)?Number(quantity.value):1,metrics:Object.fromEntries(Object.entries(metricInputs).map(([key,input])=>[key,Number(input.value)]))});
    const showOverview=result=>{
      overview.replaceChildren();const spec=result.spec;if(!spec)return;
      overview.append(el('h4','预计成品概览'));
      if(result.kind==='formation'){
        overview.append(el('p',`${spec.material_tier}阶原料 · ${spec.profile.occupied_count}个阵位 · 稳定性：${spec.profile.stability} · 阵心：${spec.profile.core_node.name}`));
        const table=el('table'),head=el('tr');['六维','要求','预计成品','工坊单维上限'].forEach(text=>head.append(el('th',text)));table.append(head);
        Object.entries(system.metric_names).forEach(([key,name])=>{const row=el('tr');[name,number(spec.requirements[key]),number(spec.profile.metrics[key]),number(spec.limits[key])].forEach(text=>row.append(el('td',text)));table.append(row);metricInputs[key].max=spec.limits[key];});overview.append(table);
        overview.append(el('p',spec.profile.effects.join('；')));
        overview.append(el('p',`使用阵材：${spec.materials.map(row=>row.name).join('、')}。交付阵法预设与每个阵位所需的独立材料；实际启用效果随阵法造诣变化。`));
      }else{
        overview.append(el('p',`${spec.material_tier}阶主材 · ${spec.mold.name} · ${spec.quality_name}验收标准`));
        overview.append(el('p',Object.entries(spec.stats).filter(([,value])=>value).map(([key,value])=>`${statNames[key] || key} +${['combat_power','max_hp','max_mp'].includes(key)?number(value):number(value*100)+'%'}`).join('；')));
        overview.append(el('p',spec.mold.rule.description));
        overview.append(el('p',`配方：${spec.materials.map(row=>`${row.name}（${row.acquired_tier}阶）`).join('、')}。辅材与淬火料不高于主材等级；加价不额外增幅属性。`));
        spec.material_effects.forEach(row=>overview.append(el('p',`${row.name}：${row.description}`)));
      }
    };
    const requestQuote=async(resetPrice=false)=>{
      const sequence=++requestSequence;quoted=null;enableSubmit(false);quoteText.textContent='商盟正在核算委托条件…';overview.replaceChildren();
      const payload=data();if(!resetPrice && principal.value)payload.principal=Number(principal.value);
      try{
        const result=await preview(payload);
        if(sequence!==requestSequence || !form.isConnected)return;
        quoted=result;principal.min=result.minimum;principal.value=result.principal;
        delete quoteText.dataset.error;
        quoteText.textContent=`${result.route_description}。本金 ${number(result.principal)} + 手续费 ${number(result.fee)} = ${number(result.total)}灵石。接单后预计 ${number(result.years)}年；最迟发布后 ${number(result.years*4)}年取消并退还全部本金。接单失败退回全部本金及50%手续费。`;
        showOverview(result);enableSubmit(canUse);
      }catch(error){if(sequence===requestSequence && form.isConnected){quoteText.textContent=error.message;quoteText.dataset.error='1';}}
    };
    const changed=(resetPrice=true)=>{requestSequence++;quoted=null;enableSubmit(false);overview.replaceChildren();clearTimeout(timer);timer=setTimeout(()=>{if(form.isConnected)requestQuote(resetPrice);},250);};
    const show=(input,visible)=>{input.parentElement.hidden=!visible;input.disabled=!visible;input.dataset.merchantUnavailable=visible?'0':'1';};
    const refreshChoices=()=>{
      const source=alliance.catalog.find(row=>row.world===world.value);
      const list=kind.value==='item'?source?.items:category.value==='formation'?source?.formation_materials:source?.materials;
      options(material,list || []);options(target,(source?.targets || []).map(row=>({id:row.id,name:`${row.name} · ${row.realm} · 战力${number(row.power)}`})));
      options(tier,(kind.value==='formation'?source?.formation_tiers:source?.weapon_tiers || []).map(value=>({id:value,name:`${value}阶`})));Object.values(metricInputs).forEach(input=>{input.value=0;input.max=100;});changed();
    };
    const refreshKind=()=>{
      const previous=world.value,procurement=['supply','item','formation','weapon'].includes(kind.value);
      options(world,alliance.catalog.map(row=>({id:row.world,name:row.world_name})));
      if([...world.options].some(row=>row.value===previous))world.value=previous;else world.value=alliance.world;
      show(category,kind.value==='supply');show(material,['supply','item'].includes(kind.value));show(quantity,['supply','item'].includes(kind.value));
      show(target,kind.value==='bounty');show(tier,['formation','weapon'].includes(kind.value));show(mold,kind.value==='weapon');
      metrics.hidden=kind.value!=='formation';Object.values(metricInputs).forEach(input=>{input.disabled=metrics.hidden;input.dataset.merchantUnavailable=metrics.hidden?'1':'0';});refreshChoices();
    };
    kind.onchange=refreshKind;world.onchange=refreshChoices;category.onchange=refreshChoices;
    tier.onchange=()=>{Object.values(metricInputs).forEach(input=>{input.value=0;input.max=100;});changed();};
    [material,target,mold,stars,quantity,...Object.values(metricInputs)].forEach(input=>input.oninput=()=>changed());
    principal.oninput=()=>changed(false);refresh.onclick=()=>requestQuote(!principal.value);
    form.onsubmit=event=>{event.preventDefault();if(!quoted || submit.disabled)return;const payload={...data(),principal:quoted.principal,preview_token:quoted.preview_token};enableSubmit(false);act({action:'post',...payload});};
    refreshKind();return details;
  };
})();

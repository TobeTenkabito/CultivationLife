(() => {
  const ui = {selected:'conceal', page:0, search:'', filter:'all', mode:'known', system:null, mutate:null, soulArts:[], soulDetail:null};
  const $ = id => document.getElementById(id);
  const node = (tag, text, cls) => { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; };
  function rows() {
    const s=ui.system || {};
    return [
      {id:'conceal',name:'显露修为',builtin:true,category:'敛息',status:s.concealment?.active?'运转中':'自带秘法',description:'收敛自身气机，显露指定的较低修为。真实属性与神识等级保持不变。'},
      {id:'suppress',name:'压制真实修为',builtin:true,category:'封修',status:s.suppression?.active?'运转中':'自带秘法',description:'暂时压低实际生效修为，境界属性与行动条件随之改变；解除后恢复原道果。'},
      ...(s.library || []), ...ui.soulArts
    ];
  }
  function select(id) {
    const target=rows().find(r=>r.id===id);
    if(target)ui.mode=target.builtin||target.acquired?'known':'potential';
    ui.selected=id;
    $('secret-art-card').dataset.secretView='detail';
    draw();
  }
  function progress(host, label, value, total) {
    host.append(node('p',`${label} · ${value} / ${total} 年`,'secret-progress-label'));
    const meter=node('progress'); meter.max=total; meter.value=value; meter.setAttribute('aria-label',label);host.append(meter);
  }
  function command(button, row, action, extra={}) {
    button.dataset.available='1';
    button.onclick=()=>ui.mutate({art:row.id,action,revision:ui.system.revision,...extra});
  }
  function draw() {
    if(!ui.system)return;
    const all=rows(), query=ui.search.trim();
    const visible=all.filter(r=>ui.mode==='known' ? r.builtin||r.acquired : !r.builtin&&!r.acquired);
    const filtered=visible.filter(r=>(!query || (r.name+(r.affinity_name||'')).includes(query)) &&
      (ui.filter==='all' || ui.filter==='builtin' && r.builtin || ui.filter==='root' && !r.builtin&&!r.soul));
    const pages=Math.max(1,Math.ceil(filtered.length/6));ui.page=Math.max(0,Math.min(ui.page,pages-1));
    const host=$('secret-art-library');host.replaceChildren();
    filtered.slice(ui.page*6,ui.page*6+6).forEach(row=>{
      const b=node('button',undefined,'secret-art-entry');b.type='button';b.dataset.secretArt=row.id;
      b.classList.toggle('selected',row.id===ui.selected);b.setAttribute('aria-pressed',String(row.id===ui.selected));
      b.append(node('span',row.seal||row.affinity_name|| (row.id==='conceal'?'隐':'封'),'secret-art-seal'),node('strong',row.name),node('small',row.status),node('span',row.category,'secret-art-kind'));
      if(row.soul)b.append(node('span',row.hint,'secret-art-mini-progress'));
      else if(!row.builtin){const text=row.casting?`施术 ${row.casting.years}/${row.casting.required}年`:`修习 ${row.study_progress}/${row.study_required}年`;b.append(node('span',text,'secret-art-mini-progress'));}
      b.onclick=()=>select(row.id);host.append(b);
    });
    if(!filtered.length)host.append(node('p','未找到对应秘法','muted'));
    $('secret-page-label').textContent=`${ui.page+1} / ${pages} · ${filtered.length} 门`;
    $('secret-page-prev').disabled=ui.page===0;$('secret-page-next').disabled=ui.page>=pages-1;
    const row=visible.find(r=>r.id===ui.selected)||visible[0];
    $('secret-tab-known').setAttribute('aria-selected',String(ui.mode==='known'));
    $('secret-tab-potential').setAttribute('aria-selected',String(ui.mode==='potential'));
    if(!row){$('secret-art-detail-heading').replaceChildren(node('p','暂无新的秘法线索','muted'));$('secret-root-detail').replaceChildren();$('secret-conceal-detail').classList.add('hidden');$('secret-suppress-detail').classList.add('hidden');return;}
    ui.selected=row.id;
    const heading=$('secret-art-detail-heading');heading.replaceChildren(node('small',row.builtin?'天生自带 · 无须获取':`${row.soul?row.category:'补灵'}秘法 · ${row.status}`),node('h3',row.name),node('p',row.description));
    $('secret-conceal-detail').classList.toggle('hidden',row.id!=='conceal');
    $('secret-suppress-detail').classList.toggle('hidden',row.id!=='suppress');
    const detail=$('secret-root-detail');detail.replaceChildren();
    if(row.builtin)return;
    if(row.soul){ui.soulDetail(detail,row);return;}
    const facts=node('dl',undefined,'secret-art-facts');
    for(const [label,value] of [['修习境界','不限'],['传承玉简',`${row.name}玉简${row.has_manual?' · 已持有':''}`],['首次修习',`${row.study_required} 年 · ${row.study_stones} 灵石 · 玉简一份`],['补灵材料',`${row.material_realm}级及以上${row.affinity_name}属内丹或元神，任选一份`],['施术耗时',`${row.casting?.required||row.casting_years} 个实际年`]]){facts.append(node('dt',label),node('dd',value));}
    detail.append(facts);
    if(!row.acquired){
      detail.append(node('h4','取得线索'),node('p',row.acquisition_hint,'secret-art-objective'),
        node('p',`修成后可补全${row.affinity_name}灵根，拓宽对应功法的修行资格。原有灵根资质与效率保持。`,'muted'));
      return;
    }
    if(!row.learned){
      progress(detail,'修习进度',row.study_progress,row.study_required);
      const b=node('button',row.study_progress?'继续修习':'开始修习','secret-art-command');
      b.dataset.available=row.study_reason?'0':'1';b.disabled=!!row.study_reason;b.title=row.study_reason;
      if(!row.study_reason)command(b,row,'study',{years:Math.min(100,row.study_required-row.study_progress)});
      detail.append(b);if(row.study_reason)detail.append(node('p',row.study_reason,'secret-art-reason'));return;
    }
    if(row.owned){detail.append(node('p',`${row.affinity_name}灵根已经具备`,'secret-art-complete'));return;}
    let source;
    if(row.casting){progress(detail,'施术进度',row.casting.years,row.casting.required);detail.append(node('p',`已投入：${row.casting.material_name}`,'muted'));}
    else{
      source=node('select');source.id='secret-art-material';source.setAttribute('aria-label','补灵材料');
      (row.materials||[]).forEach(m=>{const o=node('option',`${m.name} ×${m.quantity}`);o.value=m.id;source.append(o);});
      if(!source.options.length){const o=node('option','暂无符合条件的材料');o.value='';source.append(o);}detail.append(source);
    }
    const b=node('button',row.casting?'继续补灵':'施术补灵','secret-art-command');
    b.dataset.available=row.casting_reason?'0':'1';b.disabled=!!row.casting_reason;b.title=row.casting_reason;
    b.onclick=()=>ui.mutate({art:row.id,action:'practice',revision:ui.system.revision,
      years:Math.max(1,Math.min(100,(row.casting?.required||row.casting_years)-(row.casting?.years||0))),material_id:row.casting?'':source.value});
    detail.append(b);if(row.casting_reason)detail.append(node('p',row.casting_reason,'secret-art-reason'));
  }
  window.SecretArtPanel={render(system,mutate){ui.system=system;ui.mutate=mutate;draw();},select,
    setSoulArts(arts,renderDetail){
      const previous=ui.soulArts.find(r=>r.id===ui.selected),current=arts.find(r=>r.id===ui.selected);
      // Keep the studied art in view when it moves from potential to acquired.
      if(previous&&current&&previous.acquired!==current.acquired)ui.mode=current.acquired?'known':'potential';
      ui.soulArts=arts;ui.soulDetail=renderDetail;draw();
    }};
  $('secret-art-search').oninput=e=>{ui.search=e.target.value;ui.page=0;draw();};
  $('secret-art-filter').onchange=e=>{ui.filter=e.target.value;ui.page=0;draw();};
  $('secret-page-prev').onclick=()=>{ui.page--;draw();};
  $('secret-page-next').onclick=()=>{ui.page++;draw();};
  $('secret-art-back').onclick=()=>{$('secret-art-card').dataset.secretView='catalog';};
  for(const mode of ['known','potential'])$('secret-tab-'+mode).onclick=()=>{ui.mode=mode;ui.page=0;ui.search='';ui.filter='all';$('secret-art-search').value='';$('secret-art-filter').value='all';$('secret-art-card').dataset.secretView='catalog';draw();};
})();

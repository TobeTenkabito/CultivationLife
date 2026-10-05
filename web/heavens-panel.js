(() => {
  let current, ctx, pending, selectionRequest=0, loadingKey=null, loadError=null;
  let ui={page:'home',target:null,section:null,chamber:0,historyPage:0}, renderedKey='';
  const node = (tag, text, cls) => {const el=document.createElement(tag);if(text!=null)el.textContent=text;if(cls)el.className=cls;return el;};
  function button(label, action, disabled=false) {const b=node('button',label);b.type='button';b.disabled=disabled;b.onclick=action;return b;}
  async function selectSite(target_id) {
    const id=current.id, request=++selectionRequest, key=`${id}:${current.heavens.revision}:${target_id}`;
    if(loadingKey===key)return;
    loadingKey=key;loadError=null;
    try {
      const view=await ctx.api(`/api/games/${id}/heavens-view`,{method:'POST',body:JSON.stringify({view:'known',target_id})});
      if(current.id!==id || request!==selectionRequest || ui.target!==target_id)return;
      if(view.revision<current.heavens.revision){loadingKey=null;render(current,ctx);return;}
      current.heavens=view;loadingKey=null;render(current,ctx);
    } catch(error) {
      if(current.id===id && request===selectionRequest){loadingKey=null;loadError=error.message;render(current,ctx);}
    }
  }
  async function send(payload) {
    if(ctx.busy())return;
    pending={id:current.id,payload};
    try {await ctx.command(pending.id,payload);pending=null;}
    catch(error) {
      if(error.status && error.status<500){pending=null;try{await ctx.refresh();}catch{/* Keep the current view until the next successful query. */}}
      ctx.toast(error.message);
    }
    render(current,ctx);
  }
  async function propose(action, target_id, options={}) {
    if(ctx.busy() || pending)return;
    const id=current.id;
    try {
      const quote=await ctx.api(`/api/games/${id}/heavens-preview`,{method:'POST',body:JSON.stringify({action,target_id,options})});
      if(current.id!==id)return;
      const payload={command_seq:current.heavens.next_command_seq,expected_revision:quote.revision,action,target_id,options};
      const costs=quote.costs||{},refund=quote.refundable||{};
      const text=[`耗时 ${quote.years||0} 年；不会获得普通修炼机缘。`,
        costs.stones?`托管 ${costs.stones.toLocaleString()} 灵石，按实际进度支出。`:'',
        costs.material_id?(quote.material_consumed?'开始施工即消耗所选阵材，取消不退还。':'托管所选阵材，完成时消耗；取消退还未耗阵材。'):'',
        costs.mp?`立即消耗 ${costs.mp.toLocaleString()} 法力，不退还。`:'',
        refund.stones!=null?`可退还 ${refund.stones.toLocaleString()} 灵石。`:'',
        quote.reward_stones?`完成后获 ${quote.reward_stones.toLocaleString()} 灵石；从合作项目现有资金预留，取消或失败退回项目。每份旧录仅履约一次。`:'',
        action==='attune'?'登记后，下一次普通修炼在原奖励上获得有限增益；登记本身不发放奖励。':'',
        quote.warning||'',
        '遇到事件会暂停；已耗时间和投入不会返还。'].filter(Boolean).join('\n');
      ctx.confirm({title:'确认诸天行动',body:text,onConfirm:()=>{if(current.id===id)send(payload);}});
    } catch(error) {ctx.toast(error.message);}
  }
  const activeTask=h=>(h.tasks||[]).find(t=>['reserved','running','paused'].includes(t.status));
  const anomaly=h=>[h.mirror,h.ruins].find(a=>a?.inside);
  const amount=n=>Number(n||0).toLocaleString(undefined,{maximumFractionDigits:1});
  function go(page,target=null,section=null) {
    ++selectionRequest;loadingKey=null;loadError=null;
    ui={...ui,page,target,section};render(current,ctx);
    document.querySelector('#heavens-body h3')?.focus({preventScroll:true});
  }
  function openTarget(target) {
    if(['mirror_field','causal_ruins'].includes(target))go('anomalies',target);
    else if(current.heavens.sites.some(s=>s.id===target))go('worlds',target);
    else go('home',target);
  }
  function title(host,name,subtitle) {
    const h=node('h3',name,'heavens-title');h.tabIndex=-1;host.append(h);
    if(subtitle)host.append(node('p',subtitle,'heavens-lead'));
  }
  function tabs(host,rows,selected,onSelect,label,kind='section') {
    const nav=node('div',null,`heavens-tabs heavens-${kind}`);nav.setAttribute('role','tablist');nav.setAttribute('aria-label',label);
    rows.forEach(([id,text])=>{
      const b=button(text,()=>onSelect(id));b.dataset.heavensTab=id;b.setAttribute('role','tab');
      b.id=`heavens-${kind}-${id}`;b.setAttribute('aria-selected',String(id===selected));b.tabIndex=id===selected||(!rows.some(row=>row[0]===selected)&&id===rows[0][0])?0:-1;
      b.setAttribute('aria-controls',kind==='primary'?'heavens-body':'heavens-detail-body');
      b.onkeydown=event=>{
        const keys=['ArrowLeft','ArrowRight','Home','End'];if(!keys.includes(event.key))return;event.preventDefault();
        let index=rows.findIndex(row=>row[0]===id);index=event.key==='Home'?0:event.key==='End'?rows.length-1:(index+(event.key==='ArrowLeft'?-1:1)+rows.length)%rows.length;
        onSelect(rows[index][0]);document.getElementById(`heavens-${kind}-${rows[index][0]}`)?.focus();
      };
      nav.append(b);
    });host.append(nav);
  }
  function subview(host,rows,fallback,renderView) {
    const section=rows.some(row=>row[0]===ui.section)?ui.section:fallback;
    tabs(host,rows,section,id=>{ui.section=id;render(current,ctx);document.getElementById(`heavens-section-${id}`)?.focus();},'当前对象内容');
    const body=node('div',null,'heavens-detail-body');body.id='heavens-detail-body';body.setAttribute('role','tabpanel');body.setAttribute('aria-labelledby',`heavens-section-${section}`);
    host.append(body);renderView(body,section);
  }
  function badge(text){return node('span',text,'heavens-badge');}
  function empty(host,name,text){const box=node('div',null,'heavens-empty');box.append(node('span','·','heavens-empty-mark'),node('h4',name),node('p',text));host.append(box);}
  function tile(host,{name,description,status,glyph,onClick}) {
    const b=button('',onClick);b.className='heavens-destination';b.setAttribute('aria-label',`查看${name}`);
    const icon=node('span',glyph,'heavens-glyph'),copy=node('span',null,'heavens-destination-copy');icon.setAttribute('aria-hidden','true');
    copy.append(node('strong',name),node('small',description),badge(status));b.append(icon,copy,node('span','›','heavens-forward'));host.append(b);
  }
  function back(host,label,page){const b=button(`‹ ${label}`,()=>go(page));b.className='heavens-back';host.append(b);}
  function renderActions(host,rows,materials=[]) {
    const list=node('div',null,'heavens-actions');
    for(const row of rows){
      const box=node('article',null,'heavens-action'),info=node('div'),options={...row.options};
      const costs=[];if(row.years!=null)costs.push(`${row.years} 年`);if(row.costs?.stones)costs.push(`${amount(row.costs.stones)} 灵石`);if(row.costs?.mp)costs.push(`${amount(row.costs.mp)} 法力`);if(row.material_consumed)costs.push('消耗一件阵材');
      info.append(node('h4',row.label),node('small',row.enabled?costs.join(' · '):row.reason));
      if(row.reward_stones)info.append(node('small',`履约酬劳 ${amount(row.reward_stones)} 灵石`));
      if(['maintain','mirror_isolate','ruins_replace'].includes(row.action)&&materials.length){
        const select=node('select');select.setAttribute('aria-label',row.action==='maintain'?'维护阵材':row.action==='ruins_replace'?'替换阵芯所用阵材':`第 ${Number(options.chamber)+1} 处隔断阵材`);
        for(const m of materials){const option=node('option',m.name||m.material_id);option.value=m.id;select.append(option);}
        select.disabled=!row.enabled||Boolean(pending);select.onchange=()=>{options.material_id=select.value;};info.append(select);
      }
      const b=button(row.label,()=>propose(row.action,row.target_id,options),!row.enabled||Boolean(pending));b.dataset.heavensAction=row.action;
      if(['ruins_take','mirror_assault'].includes(row.action))b.classList.add('heavens-danger');
      box.append(info,b);list.append(box);
    }host.append(list);
  }
  function render(data,context) {
    const changed=current?.id!==data.id;
    current=data;ctx=context;
    if(changed){pending=null;loadingKey=null;loadError=null;++selectionRequest;const inside=anomaly(data.heavens);ui={page:inside?'anomalies':'home',target:inside?.id||null,section:null,chamber:0,historyPage:0};}
    const host=document.getElementById('heavens-content'),h=data.heavens;if(!host||!h)return;
    const dock=document.querySelector('[data-panel-target="heavens"]'),notices=(h.notifications||[]).length;
    if(dock){dock.classList.toggle('has-notice',notices>0);dock.title=notices?`诸天 · ${notices} 条新见闻`:'诸天';dock.querySelector('small').textContent=notices?'新见闻':'诸天';}
    const key=`${ui.page}:${ui.target}:${ui.section}:${ui.chamber}:${ui.historyPage}`,scroll=key===renderedKey?document.getElementById('heavens-body')?.scrollTop||0:0;renderedKey=key;
    host.replaceChildren();
    const navigation=node('div',null,'heavens-navigation');
    tabs(navigation,[['home','见闻'],['worlds','诸界'],['anomalies','异象'],['journey','行程']],ui.page,id=>go(id), '诸天导航','primary');
    const settings=button('偏好',()=>go('settings'));settings.className='heavens-preferences';settings.setAttribute('aria-label','诸天偏好');settings.setAttribute('aria-pressed',String(ui.page==='settings'));navigation.append(settings);host.append(navigation);
    if(pending){const box=node('div',null,'heavens-retry');box.setAttribute('role','status');box.append(node('small','上次提交尚未确认，可安全重试。'),button('重试上次提交（不会重复扣费）',()=>send(pending.payload)));host.append(box);}
    const task=activeTask(h);
    if(task&&ui.page!=='journey'){const strip=button(`进行中 · ${task.progress}/${task.duration} 年 · 查看行程 ›`,()=>go('journey'));strip.className='heavens-task-strip';host.append(strip);}
    const body=node('div',null,'heavens-body');body.id='heavens-body';body.dataset.heavensView=ui.page;body.setAttribute('role','tabpanel');
    if(ui.page!=='settings')body.setAttribute('aria-labelledby',`heavens-primary-${ui.page}`);else body.setAttribute('aria-label','诸天偏好');
    host.append(body);
    if(ui.page==='home')renderHome(body,h);
    if(ui.page==='worlds')renderWorlds(body,h);
    if(ui.page==='anomalies')renderAnomalies(body,h);
    if(ui.page==='journey')renderJourney(body,h);
    if(ui.page==='settings')renderSettings(body,h);
    body.scrollTop=scroll;
  }
  function renderHome(host,h) {
    const omen=(h.omens||[]).find(row=>row.id===ui.target);
    if(omen){
      back(host,'返回见闻','home');title(host,omen.name,`人界 · ${omen.location_name}`);
      const text=node('blockquote',omen.glimpse,'heavens-finding');host.append(text);
      if(omen.studied){host.append(badge('已对照'),node('p',omen.finding));const b=button('查看相关异象',()=>openTarget(omen.anomaly_id));b.className='heavens-link';host.append(b);}
      else {host.append(node('small',omen.remaining?`征兆仍可核对 · 余 ${omen.remaining} 年`:'此次征兆已消退，旧见闻仍保留。'));renderActions(host,omen.actions);}
      return;
    }
    title(host,'一隅见闻','从亲历的征兆出发，逐步认识诸界。');
    const local=h.sites.find(row=>row.current),inside=anomaly(h);
    if(inside){const b=button(`返回${inside.name} · 当前所在 ›`,()=>openTarget(inside.id));b.className='heavens-task-strip';host.append(b);}
    else if(local){const b=button(`前往${local.name.split(' · ')[0]}的联系档案 ›`,()=>openTarget(local.id));b.className='heavens-task-strip';host.append(b);}
    if(!h.generation_enabled){host.append(node('p','新联系发现已关闭，已有认识仍保留。','heavens-lead'),button('调整发现偏好',()=>go('settings')));}
    const notices=h.notifications||[];
    for(const notice of notices){const row=node('article',null,'heavens-notice');row.append(node('p',notice.text));const controls=node('div',null,'heavens-inline');controls.append(button('查看线索',()=>openTarget(notice.id)),button('忽略此通知',()=>propose('dismiss',notice.id)));row.append(controls);host.append(row);}
    if(h.omens?.length){const list=node('div',null,'heavens-directory');for(const row of h.omens)tile(list,{name:row.name,description:`人界 · ${row.location_name}`,status:row.studied?'已对照':row.remaining?'待求证':'旧见闻',glyph:'闻',onClick:()=>openTarget(row.id)});host.append(list);}
    else if(!notices.length)empty(host,'尚无新的本地见闻','在平日修行和游历中留意气机、旧石与风沙。低阶也可能察觉征兆；是否深入，取决于已有线索和自身修为。');
    const footer=node('div',null,'heavens-home-links');footer.append(button('查阅诸界联系 ›',()=>go('worlds')),button('寻找异象入口 ›',()=>go('anomalies')));host.append(footer);
  }
  function renderWorlds(host,h) {
    const selected=h.sites.find(row=>row.id===ui.target);
    if(!selected){
      title(host,'诸界联系','选一处地点，查看当地认识与可参与的事务。');
      const list=node('div',null,'heavens-directory');
      for(const site of h.sites)tile(list,{name:site.name,description:site.world_name,status:site.current?'当前界面':site.known?'已有档案':'尚未登记',glyph:({celestial:'仙',asura:'修',nether:'幽',reincarnation:'轮'})[site.world],onClick:()=>openTarget(site.id)});
      host.append(list);return;
    }
    back(host,'返回诸界','worlds');title(host,selected.name,`${selected.world_name} · 亲自参与需抵达当地，并具备未压制的九阶以上修为。`);
    if(h.target_id!==selected.id){
      if(loadError){host.append(node('p',loadError),button('重新读取档案',()=>{loadError=null;selectSite(selected.id);render(current,ctx);}));}
      else {const p=node('p','正在读取联系档案…');p.setAttribute('role','status');host.append(p);if(!loadingKey)selectSite(selected.id);}
      return;
    }
    const e=h.echo;
    if(e){const facts=node('div',null,'heavens-facts');facts.append(badge(e.remaining?`第 ${e.cycle+1} 周期 · 余 ${e.remaining} 年`:`下周期尚需 ${e.next_cycle_in} 年`),badge(`${e.evidence.length} 份求证记录`));host.append(facts);}
    subview(host,[['research','求证'],['cooperate','往来'],['practice','参悟']],'research',(body,section)=>{
      if(section==='research'){
        if(e?.evidence.length){const list=node('ol',null,'heavens-evidence');for(const line of e.evidence)list.append(node('li',line.replace(/^E\d\s/,'')));body.append(list);}
        if(e?.inscriptions.length)body.append(node('small',`旧碑两段记录早于首次登记 ${e.origin_year-e.inscriptions[0]} 年、${e.origin_year-e.inscriptions[1]} 年。`));
      }
      if(section==='cooperate'){
        if(e)body.append(node('p',`${e.visitor.name} · ${e.visitor.available?'在场，可提出合作':'暂不能履约'}`),node('small',`研究项目实有 ${amount(e.project_stones)} 灵石。${e.correspondence_completed?'旧录校订已履约。':''}`));
        else body.append(node('p','先完成当地体察，再与访学者对照认识。'));
      }
      if(section==='practice'&&e)body.append(node('p',`本周期实际增益 ${amount(e.reward_claimed)}${e.reward_base?' · 上限基准 '+amount(e.reward_base):''}`),node('small','登记后在当地正常修炼时应用，维护后的再次参悟共用周期上限。'));
      const allowed={research:['observe','check_history'],cooperate:['exchange','correspond'],practice:['attune','maintain']}[section];
      renderActions(body,(h.actions||[]).filter(row=>allowed.includes(row.action)),h.materials||[]);
      if(section==='practice'&&h.registered_application?.target_id===selected.id)renderApplication(body,h.registered_application);
    });
  }
  function renderAnomalies(host,h) {
    const entries=[h.mirror,h.ruins].filter(Boolean),selected=entries.find(row=>row.id===ui.target);
    if(!selected){
      title(host,'异象行旅','从真实地点进入一处异象，沿原路返回。每处机关与所得都将保留。');
      const list=node('div',null,'heavens-directory');
      for(const row of entries)tile(list,{name:row.name,description:row.entry,status:row.inside?'身处其中':row.known?'可重访':'元婴起可进入',glyph:row.id==='mirror_field'?'镜':'因',onClick:()=>openTarget(row.id)});
      host.append(list);return;
    }
    back(host,'返回异象','anomalies');
    const box=node('section',null,'heavens-object');if(selected.id==='mirror_field')box.dataset.mirror='field';else box.dataset.ruins='field';
    host.append(box);const heading=node('div',null,'heavens-object-heading');title(heading,selected.name);box.append(heading);
    const leave=selected.actions.find(row=>row.action.endsWith('_leave'));if(leave){const b=button(leave.label,()=>propose(leave.action,leave.target_id),!leave.enabled||Boolean(pending));b.className='heavens-exit';heading.append(b);}
    box.append(node('p',`${selected.entry} · ${selected.inside?'身处其中':selected.known?'可重访':'元婴起可进入'}`,'heavens-lead'));
    if(leave&&!leave.enabled)box.append(node('small',leave.reason));
    if(!selected.inside){box.append(node('p',selected.description));renderActions(box,selected.actions.filter(row=>row.action.endsWith('_enter')));return;}
    if(selected.id==='mirror_field')renderMirror(box,selected);else renderRuins(box,selected);
  }
  function renderMirror(host,m) {
    if(!m.probed){host.append(node('blockquote','镜纹随施术明灭。先低耗试探，确认机关的收集规律。','heavens-finding'));renderActions(host,m.actions.filter(row=>row.action==='mirror_probe'));return;}
    const facts=node('div',null,'heavens-facts');facts.append(badge(`镜储 ${amount(m.stored_mana)} / ${amount(m.mana_capacity)}`),badge(`已解开 ${m.chambers.filter(c=>c.opened).length} / 3`));host.append(facts);
    const meter=node('meter');meter.min=0;meter.max=m.mana_capacity;meter.value=m.stored_mana;meter.setAttribute('aria-label','当前镜储');host.append(meter);
    const choices=m.chambers.map(c=>[String(c.index),`${['一','二','三'][c.index]} · ${c.opened?'已解开':c.isolated?'已隔断':'机关'}`]);
    tabs(host,choices,String(ui.chamber),id=>{ui.chamber=Number(id);render(current,ctx);document.getElementById(`heavens-chamber-${id}`)?.focus();},'选择镜律机关','chamber');
    const chamber=m.chambers[ui.chamber],body=node('div',null,'heavens-detail-body');body.id='heavens-detail-body';body.dataset.mirrorChamber=String(chamber.index);body.setAttribute('role','tabpanel');body.setAttribute('aria-labelledby',`heavens-chamber-${chamber.index}`);host.append(body);
    if(chamber.opened){body.append(node('p',chamber.reward?`已领取：${chamber.reward}`:'已取得镜律规律记录。'));body.append(node('small','此处机关已解开，重访不会重复领取所得。'));}
    else {body.append(node('p',chamber.isolated?'此处联系已隔断，后续施术不再供给这处机关。':'可投入法力破解、消耗阵材隔断，或按当前战斗预案强攻。'));renderActions(body,m.actions.filter(row=>row.options.chamber===String(chamber.index)),m.materials);}
    if(chamber.guardian)body.append(node('small',`已遭遇 ${chamber.guardian.encounters} 次；守护快照与损伤保留。`));
    const rules=node('details',null,'heavens-notes');rules.append(node('summary','查阅收集规律与痕迹'),node('p','登记施术实付法力的 25% 被收集；普通修炼和其他战斗不计入。隔断停止对应联系，守护强度最多增加 15%。'),node('small',`累计收集 ${amount(m.collected_mana)}；保留 ${m.traces.length} 条施术或施工痕迹。`));body.append(rules);
  }
  function renderRuins(host,r) {
    const status=node('div',null,`heavens-link-state${r.ward_active?'':' interrupted'}`);
    status.append(node('span','遗址机关'),node('span',r.ward_active?'⇄':'×'),node('span',r.contact?'赤髓城阵眼':'异界阵眼'));status.setAttribute('aria-label',r.ward_active?'两端回响连通':'阵眼失效，回响通信中断');host.append(status);
    subview(host,[['investigate','调查'],['core','阵芯'],['traces','痕迹']],'investigate',(body,section)=>{
      let actions;
      if(section==='investigate'){
        body.append(node('p',r.verified?'两端关联已查明。':r.observed?'已观察阵纹，可以继续查证。':'阵芯与异界阵纹同步明灭，尚未查证其来历。'));
        if(r.record_acquired)body.append(node('p','已取得回潮阵纹合法抄本与一件四阶阵材。'));
        if(r.contact)body.append(node('blockquote',`接触线索：${r.contact}`,'heavens-finding'));
        actions=[!r.observed&&'ruins_observe',!r.verified&&'ruins_verify',!r.record_acquired&&'ruins_read',!r.contact&&'ruins_contact'].filter(Boolean);
      } else if(section==='core'){
        const ownership=r.core.owner==='player'?'由你持有，可归还安装':r.core.acquisition?'已归还阵眼，不能再次领取':'由阵眼持有';
        body.append(node('h4','回潮阵芯'),node('p',ownership),node('small','唯一任务遗物，可用于对应阵眼；不能出售或炼化成通用战力。'),node('p',r.ward_active?r.replacement?'替代部件维持回响。':'阵芯维持回响。':'阵眼失效，回响通信中断。'));
        actions=r.core.owner==='player'?['ruins_return']:r.core.acquisition?[]:['ruins_replace','ruins_take'];
      } else {
        const stats=node('dl',null,'heavens-trace-stats');for(const [key,label] of [['local','未读残留'],['held','机关留档'],['sent','已送出']]){const col=node('div');col.append(node('dt',label),node('dd',r.traces[key]));stats.append(col);}body.append(stats);
        body.append(node('p',r.trace_rule||'可清理尚未读取的残留；已留档与送出的证据不能撤回。'));
        actions=['ruins_erase'];
      }
      renderActions(body,r.actions.filter(row=>actions.includes(row.action)),r.materials);
    });
  }
  function renderApplication(host,app){const row=node('article',null,'heavens-task');row.append(node('h4',app.name),node('p',`参悟已登记 · 剩余 ${app.remaining} 个实际修炼年`),button('取消参悟安排',()=>propose('cancel',app.target_id)));host.append(row);}
  function renderJourney(host,h) {
    title(host,'行程与纪要','查看亲自参与的事务，回顾已有认识。');
    subview(host,[['active','进行中'],['history','纪要']],'active',(body,section)=>{
      if(section==='history'){
        const rows=[...(h.history||[])].reverse(),size=12,pages=Math.max(1,Math.ceil(rows.length/size));ui.historyPage=Math.min(ui.historyPage,pages-1);
        if(!rows.length){empty(body,'尚无纪要','亲历的征兆、求证与履约会记在这里。');return;}
        const list=node('ol',null,'heavens-timeline');for(const row of rows.slice(ui.historyPage*size,(ui.historyPage+1)*size)){const item=node('li');item.append(node('small',`登记后 ${row.year} 年`),node('p',row.text));list.append(item);}body.append(list);
        const pager=node('div',null,'heavens-inline');pager.append(button('上一页',()=>{ui.historyPage--;render(current,ctx);},ui.historyPage===0),node('small',`${ui.historyPage+1} / ${pages}`),button('下一页',()=>{ui.historyPage++;render(current,ctx);},ui.historyPage===pages-1));body.append(pager);return;
      }
      const task=activeTask(h);
      if(task){
        const names={mirror_field:'镜律场域',causal_ruins:'因果遗址',sand_glimmer:'沙中重影',stone_resonance:'旧石回声'},name=h.sites.find(s=>s.id===task.target_id)?.name||names[task.target_id]||'诸天研究';
        const row=node('article',null,'heavens-task');row.append(node('h4',name),node('p',`当前任务：${task.progress} / ${task.duration} 年`));const progress=node('progress');progress.max=task.duration;progress.value=task.progress;progress.setAttribute('aria-label','任务进度');row.append(progress);
        const controls=node('div',null,'heavens-inline');controls.append(button('继续任务',()=>propose('resume',task.id),Boolean(pending)),button('取消任务',()=>propose('cancel',task.id),Boolean(pending)),button('查看对象',()=>openTarget(task.target_id)));row.append(controls,node('small','取消前会显示可退还的未耗投入，已付法力与已耗材料不退。'));body.append(row);
      }
      if(h.registered_application)renderApplication(body,h.registered_application);
      if(!task&&!h.registered_application)empty(body,'暂无进行中的行程','可从一条见闻、一处联系或一座异象开始。');
    });
  }
  function renderSettings(host,h) {
    title(host,'诸天偏好','按自己的修行节奏，选择是否接收新线索。');
    for(const [key,label,value,description] of [
      ['generation_enabled','允许发现新的诸天联系',h.generation_enabled,'关闭后，已有地点、认识与任务继续保留。'],
      ['watch','显示诸天机会通知',h.watch,'关闭后仍记录实际见闻，可在纪要中回顾。'],
      ['pause_on_opportunity','发现机会后暂停',h.pause_on_opportunity,'在完整修行单位结束时停下，途中旅行和专属活动照常进行。']]){
      const row=node('label',null,'heavens-setting'),copy=node('span'),input=node('input');input.type='checkbox';input.checked=value;input.setAttribute('aria-label',label);
      input.disabled=Boolean(pending)||(!h.generation_available&&key==='generation_enabled')||(key==='pause_on_opportunity'&&h.year==null);
      input.onchange=()=>send({command_seq:h.next_command_seq,expected_revision:h.revision,action:'configure',target_id:null,options:{[key]:input.checked}});
      copy.append(node('strong',label),node('small',description));row.append(copy,input);host.append(row);
    }
  }
  window.HeavensPanel={render,openTarget};
})();

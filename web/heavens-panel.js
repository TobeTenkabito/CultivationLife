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
        costs.material_id&&action!=='freight_start'?(quote.material_consumed?'开始施工即消耗所选阵材，取消不退还。':'托管所选阵材，完成时消耗；取消退还未耗阵材。'):'',
        costs.mp?`立即消耗 ${costs.mp.toLocaleString()} 法力，不退还。`:'',
        refund.stones!=null?`可退还 ${refund.stones.toLocaleString()} 灵石。`:'',
        quote.reward_stones?`完成后获 ${quote.reward_stones.toLocaleString()} 灵石；从合作项目现有资金预留，取消或失败退回项目。每份旧录仅履约一次。`:'',
        quote.return_fare?`其中 ${quote.return_fare.toLocaleString()} 灵石专用于返程，抵达后继续保留。申请机会仅有一次，取消启程也会结束本次许可。`:'',
        quote.message||'',
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
    else if(target==='lanjiang_frontier')go('frontier',target);
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
      b.setAttribute('aria-controls',kind==='primary'?'heavens-body':kind==='chamber'?'heavens-chamber-body':'heavens-detail-body');
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
  function renderActions(host,rows,materials=[],people=[]) {
    const list=node('div',null,'heavens-actions');
    for(const row of rows){
      const box=node('article',null,'heavens-action'),info=node('div'),options={...row.options};
      const costs=[];if(row.years!=null)costs.push(`${row.years} 年`);if(row.costs?.stones)costs.push(`${amount(row.costs.stones)} 灵石`);if(row.costs?.mp)costs.push(`${amount(row.costs.mp)} 法力`);if(row.material_consumed)costs.push('消耗一件阵材');
      info.append(node('h4',row.label),node('small',row.enabled?costs.join(' · '):row.reason));
      if(row.reward_stones)info.append(node('small',`履约酬劳 ${amount(row.reward_stones)} 灵石`));
      if(['maintain','upkeep_start','mirror_isolate','mirror_repair','ruins_replace','freight_start'].includes(row.action)&&materials.length){
        const select=node('select');select.setAttribute('aria-label',row.action==='freight_start'?'托运阵材':row.action==='mirror_repair'?'修补镜阵所用阵材':['maintain','upkeep_start'].includes(row.action)?'维护阵材':row.action==='ruins_replace'?'替换阵芯所用阵材':`第 ${Number(options.chamber)+1} 处隔断阵材`);
        for(const m of materials){const option=node('option',m.name||m.material_id);option.value=m.id;select.append(option);}
        select.disabled=!row.enabled||Boolean(pending);select.onchange=()=>{options.material_id=select.value;};info.append(select);
      }
      if(['migration_start','survey_start'].includes(row.action)&&people.length){
        const select=node('select');select.setAttribute('aria-label',row.action==='survey_start'?'勘察居民':'迁居居民');
        for(const person of people){const option=node('option',`${person.name} · 交情 ${person.affinity}`);option.value=person.id;select.append(option);}
        select.disabled=!row.enabled||Boolean(pending);select.onchange=()=>{options.person_id=select.value;};info.append(select);
      }
      const b=button(row.label,()=>propose(row.action,row.target_id,options),!row.enabled||Boolean(pending));b.dataset.heavensAction=row.action;
      if(['ruins_take','mirror_assault','mirror_release'].includes(row.action))b.classList.add('heavens-danger');
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
    tabs(navigation,[['home','见闻'],['worlds','诸界'],['anomalies','异象'],['journey','行程'],['frontier','战局']],ui.page,id=>go(id), '诸天导航','primary');
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
    if(ui.page==='frontier')window.HeavensFrontier.render(body,h.frontier,ui,{node,title,tile,back,subview,renderActions,empty,go});
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
    back(host,'返回诸界','worlds');title(host,selected.name,ui.section==='freight'?'物资委托 · 实物交接，循路承运':ui.section==='mission'?'同道回访 · 本人出行，循约返乡':ui.section==='visit'?'个人访学 · 往返许可与现场对照':`${selected.world_name} · 亲自参与需抵达当地，并具备未压制的九阶以上修为。`);
    if(h.target_id!==selected.id){
      if(loadError){host.append(node('p',loadError),button('重新读取档案',()=>{loadError=null;selectSite(selected.id);render(current,ctx);}));}
      else {const p=node('p','正在读取联系档案…');p.setAttribute('role','status');host.append(p);if(!loadingKey)selectSite(selected.id);}
      return;
    }
    const e=h.echo;
    if(e&&!['visit','mission','freight'].includes(ui.section)){const facts=node('div',null,'heavens-facts');facts.append(badge(e.remaining?`第 ${e.cycle+1} 周期 · 余 ${e.remaining} 年`:`下周期尚需 ${e.next_cycle_in} 年`),badge(`${e.evidence.length} 份求证记录`));host.append(facts);}
    subview(host,[['research','求证'],['cooperate','往来'],['visit','访学'],['mission','同道'],['freight','运材'],['practice','参悟']],'research',(body,section)=>{
      if(section==='freight'){renderFreight(body,h.freight);return;}
      if(section==='mission'){renderMission(body,h.mission);return;}
      if(section==='visit'){
        const v=h.visit;
        if(!v){empty(body,'尚无访学路线','先在当地登记诸天联系。');return;}
        const labels={unavailable:'等待申请',preparing:'启程途中',visiting:'异界访学',returned:'已经返乡',cancelled:'申请已结束',failed:'行程已结束'};
        body.append(node('h4',v.destination_name),node('p','完成旧录校订后，可申请一次个人访学。通道仅容本人，同行队伍和俘虏须事先安置。'));
        const route=node('ol',null,'heavens-visit-route');route.setAttribute('aria-label','访学行程');
        for(const text of ['启程 · 2 年','实地研读 · 4 年','返程 · 2 年'])route.append(node('li',text));
        body.append(route,badge(labels[v.status]),node('p',`往返共 4,000 灵石；研读不另收费。${v.return_fare?`返程已预留 ${amount(v.return_fare)} 灵石。`:''}`));
        if(v.finding)body.append(node('p',v.finding,'heavens-visit-finding'));
        if(v.status==='visiting')body.append(node('small','可提前返程。若离开接待地点，须自行回到该处续办；行程不会自动传送角色。'));
        const task=activeTask(h);
        if(task&&task.target_id===selected.id&&task.action.startsWith('visit_')){
          body.append(node('p',`当前步骤 ${task.progress} / ${task.duration} 年`),button('继续访学行程',()=>go('journey')));
        }else{
          const allowed=v.status==='visiting'?['visit_study','visit_return']:v.status==='unavailable'?['visit_depart']:[];
          renderActions(body,(h.actions||[]).filter(row=>allowed.includes(row.action)&&!(row.action==='visit_study'&&v.studied)));
        }
        return;
      }
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
      if(section==='practice')body.append(button('查看托管护持',()=>go('journey',selected.id,'upkeep')));
      if(section==='practice'&&h.registered_application?.target_id===selected.id)renderApplication(body,h.registered_application);
    });
  }
  function renderFreight(host,f) {
    if(!f){empty(host,'尚无物资委托','先与当地人物建立合作。');return;}
    host.append(node('h4',`${f.name} · 承运`),node('p',`交货地点：${f.destination_name}`));
    if(f.status==='unavailable'){
      host.append(node('p','同道完成研读并返乡后，可委托运送一件本界九阶普通阵材。每处联系仅接收一次，使用背包中的原物资。'));
      const route=node('ol',null,'heavens-visit-route');route.setAttribute('aria-label','运材路线');
      for(const text of ['去程 · 2 年','抵达交货','返乡 · 2 年'])route.append(node('li',text));
      host.append(route,node('p','这是研究供材捐赠，交货后原物资归当地项目。项目预留 4,000 往返路费及 3,000 定额补贴；补贴并非市价收购款，交货后在出发地领取。'));
    }else{
      const owners={carrier:'承运人携带',destination:'目的地研究库存',depot:'出发地托存，待领取',player:'已经取回',lost:'随承运人遗失'};
      host.append(node('p',f.material.name||f.material.material_id,'heavens-visit-finding'),badge(owners[f.cargo_owner]));
      host.append(node('p',`${f.phase==='outbound'?'去程':'返程'} ${f.progress} / 2 年 · ${{active:'进行中',completed:'已返乡',cancelled:'已撤销',failed:'已终止'}[f.status]}`));
      host.append(node('small',`路费已耗 ${amount(f.spent)} · 尚存经费 ${amount(f.remaining)} · 退回项目 ${amount(f.refunded)} 灵石`));
      if(f.delivered)host.append(node('p',f.claimed?'3,000 灵石供材报酬已领取。':'已交货：3,000 灵石供材报酬待在出发地领取。'));
      if(f.blocked_reason)host.append(node('p',f.blocked_reason,'heavens-visit-finding'));
    }
    if(f.status==='unavailable'||f.status==='active')host.append(node('small','普通世界年度推进行程，独立空间冻结。陨落时未交物资遗失；交货后不可撤回。'));
    renderActions(host,f.actions.filter(a=>f.status==='unavailable'?a.action==='freight_start':a.action==='mission_wait'||a.action==='freight_cancel'&&f.status==='active'&&f.phase==='outbound'||a.action==='freight_collect'&&(f.cargo_owner==='depot'||f.reward_available)),f.materials);
  }
  function renderMission(host,m) {
    if(!m){empty(host,'尚无回访约定','先与当地人物建立合作。');return;}
    const status={unavailable:'待约请',active:'行程中',completed:'已经返乡',cancelled:'行程已撤销',failed:'行程已终止'},phase={outbound:'去程',studying:'当地研读',returning:'返乡'};
    host.append(node('h4',m.name),node('p',`回访地点：${m.destination_name}`),badge(status[m.status]));
    if(m.status==='unavailable')host.append(node('p','亲自研读后，可约请原合作人物回访。项目预留 6,000 灵石，承担去程 2 年、研读 4 年和返程 2 年的开销。'));
    else {
      host.append(node('p',`${phase[m.phase]} · ${m.progress} / ${m.duration} 年`));
      if(m.status==='active'){const progress=node('progress');progress.max=m.duration;progress.value=m.progress;progress.setAttribute('aria-label','同道行程进度');host.append(progress);}
      host.append(node('small',`项目已支 ${amount(m.spent)} · 尚存 ${amount(m.remaining)} · 退回 ${amount(m.refunded)} 灵石`));
      if(m.blocked_reason)host.append(node('p',m.blocked_reason,'heavens-visit-finding'));
      if(m.studied)host.append(node('p','本人已取得现场对照记录；已有认识与人物经历继续保留。'));
      if(m.status==='active'&&m.phase==='studying')host.append(node('small','可在接待地点通过人物名册交往。研读结束后会自行返程。'));
    }
    if(m.status==='active')host.append(node('small','世界年度会推进行程，也可逐年等候；身处独立空间时，外界行程暂停。'));
    renderActions(host,m.actions.filter(row=>m.status==='unavailable'?row.action==='mission_start':m.status==='active'&&row.action!=='mission_start'));
  }
  function renderAnomalies(host,h) {
    const entries=[h.mirror,h.ruins].filter(Boolean),selected=entries.find(row=>row.id===ui.target);
    if(!selected){
      title(host,'异象行旅','从真实地点进入一处异象，沿原路返回。每处机关与所得都将保留。');
      const list=node('div',null,'heavens-directory');
      for(const row of entries)tile(list,{name:row.name,description:row.entry,status:row.inside?'身处其中':row.capacity_pending?'已知入口':row.known?'可重访':'元婴起可进入',glyph:row.id==='mirror_field'?'镜':'因',onClick:()=>openTarget(row.id)});
      host.append(list);return;
    }
    back(host,'返回异象','anomalies');
    const box=node('section',null,'heavens-object');if(selected.id==='mirror_field')box.dataset.mirror='field';else box.dataset.ruins='field';
    host.append(box);const heading=node('div',null,'heavens-object-heading');title(heading,selected.name);box.append(heading);
    const leave=selected.actions.find(row=>row.action.endsWith('_leave'));if(leave){const b=button(leave.label,()=>propose(leave.action,leave.target_id),!leave.enabled||Boolean(pending));b.className='heavens-exit';heading.append(b);}
    box.append(node('p',`${selected.entry} · ${selected.inside?'身处其中':selected.capacity_pending?'已知入口':selected.known?'可重访':'元婴起可进入'}`,'heavens-lead'));
    if(leave&&!leave.enabled)box.append(node('small',leave.reason));
    if(!selected.inside){
      const entry=body=>{body.append(node('p',selected.description));if(selected.capacity_pending)body.append(node('p','你尚未入场，镜储上限将在首次亲自入场时按当时法力上限的 25% 固定；之后重访不再改变。'));renderActions(body,selected.actions.filter(row=>row.action.endsWith('_enter')));};
      if(selected.known&&selected.survey)subview(box,[['entrance','入口'],...(selected.id==='mirror_field'&&selected.probed?[['pact','守约']]:[]),['survey','同勘']],'entrance',(body,section)=>section==='survey'?renderSurvey(body,selected):section==='pact'?renderMirrorPact(body,selected):entry(body));
      else entry(box);
      return;
    }
    if(selected.id==='mirror_field')renderMirror(box,selected);else renderRuins(box,selected);
  }
  function renderMirror(host,m) {
    subview(host,[['mechanisms','机关'],['pact','守约'],['survey','同勘']],'mechanisms',(body,section)=>section==='survey'?renderSurvey(body,m):section==='pact'?renderMirrorPact(body,m):renderMirrorMechanisms(body,m));
  }
  function renderMirrorPact(host,m) {
    const p=m.pact,labels={repairing:'修补中',kept:'守约生效',released:'已解除',cancelled:'已取消',failed:'未能完成'};
    host.dataset.mirrorPact=p?.status||'available';
    title(host,'修补与守约',p?labels[p.status]:'镜纹留下了一条无需强攻的交换条件。');
    host.append(node('p','守护机关允许以修补换取规律抄录，条件是保留第一、第二处材料核心。抄录与第三处机关共用同一份记录，不另发机缘或物品。'));
    if(!p){
      host.append(node('p','低耗试探之后、三处机关尚未被解开、隔断或强攻之前，可安装一件人界四阶普通阵材，修补 3 年；不额外施法。'));
    }else{
      host.append(node('p',`已安装：${p.material.name||p.material.material_id}。阵材与已耗工时不退，每处场域只接受一次修补。`));
      if(p.status==='repairing'){
        const task=(current.heavens.tasks||[]).find(t=>t.id===p.task_id);
        if(task)host.append(node('p',`实际修补 ${task.progress} / ${task.duration} 年`),button('查看任务与续做',()=>go('journey')));
      }else if(p.status==='kept')host.append(node('p','规律记录已取得，两处核心仍留在场域。离开和重访不会解除这项约定。','heavens-finding'));
      else if(p.status==='released')host.append(node('p','已有记录保留，两处核心永久关闭低耗破解与材料隔断许可；可到机关页按真实战斗规则强攻。'));
      else host.append(node('p','本次修补未取得记录，已安装阵材保留。原机关探索仍可继续，不再受理第二次修补约定。'));
    }
    host.append(node('small','解除守约须在场明确确认，之后只能强攻核心；不退修补投入，也不重置已有机关与镜储。'));
    if(!m.inside)host.append(node('p','此处可查阅已知约定；继续操作须从入口页亲自重返场域。'));
    renderActions(host,m.actions.filter(a=>!p?a.action==='mirror_repair':p.status==='kept'&&a.action==='mirror_release'),m.materials);
  }
  function renderMirrorMechanisms(host,m) {
    if(m.survey?.shared)host.append(node('p',m.survey.benefit));
    if(!m.probed){host.append(node('blockquote','镜纹随施术明灭。先低耗试探，确认机关的收集规律。','heavens-finding'));renderActions(host,m.actions.filter(row=>row.action==='mirror_probe'));return;}
    const facts=node('div',null,'heavens-facts');facts.append(badge(`镜储 ${amount(m.stored_mana)} / ${amount(m.mana_capacity)}`),badge(`已解开 ${m.chambers.filter(c=>c.opened).length} / 3`));host.append(facts);
    if(m.pact?.status==='kept')host.append(node('p','守约期间保留两处材料核心；约定详情及解除入口位于“守约”页。'));
    const meter=node('meter');meter.min=0;meter.max=m.mana_capacity;meter.value=m.stored_mana;meter.setAttribute('aria-label','当前镜储');host.append(meter);
    const choices=m.chambers.map(c=>[String(c.index),`${['一','二','三'][c.index]} · ${c.opened?'已解开':c.isolated?'已隔断':'机关'}`]);
    tabs(host,choices,String(ui.chamber),id=>{ui.chamber=Number(id);render(current,ctx);document.getElementById(`heavens-chamber-${id}`)?.focus();},'选择镜律机关','chamber');
    const chamber=m.chambers[ui.chamber],body=node('div',null,'heavens-detail-body');body.id='heavens-chamber-body';body.dataset.mirrorChamber=String(chamber.index);body.setAttribute('role','tabpanel');body.setAttribute('aria-labelledby',`heavens-chamber-${chamber.index}`);host.append(body);
    if(chamber.opened){body.append(node('p',chamber.reward?`已领取：${chamber.reward}`:'已取得镜律规律记录。'));body.append(node('small','此处机关已解开，重访不会重复领取所得。'));}
    else if(m.pact?.status==='kept'&&chamber.index<2){body.append(node('p','这处核心依约保留，仍由场域持有。'),button('查看守约',()=>go('anomalies',m.id,'pact')));}
    else {body.append(node('p',m.pact?.status==='released'&&chamber.index<2?'约定已解除，此处只能按当前战斗预案强攻；原守护状态继续保留。':chamber.isolated?'此处联系已隔断，后续施术不再供给这处机关。':'可投入法力破解、消耗阵材隔断，或按当前战斗预案强攻。'));renderActions(body,m.actions.filter(row=>row.options.chamber===String(chamber.index)),m.materials);}
    if(chamber.guardian)body.append(node('small',`已遭遇 ${chamber.guardian.encounters} 次；守护快照与损伤保留。`));
    const rules=node('details',null,'heavens-notes');rules.append(node('summary','查阅收集规律与痕迹'),node('p','登记施术实付法力的 25% 被收集；普通修炼和其他战斗不计入。隔断停止对应联系，守护强度最多增加 15%。'),node('small',`累计收集 ${amount(m.collected_mana)}；保留 ${m.traces.length} 条施术或施工痕迹。`));body.append(rules);
  }
  function renderRuins(host,r) {
    const status=node('div',null,`heavens-link-state${r.ward_active?'':' interrupted'}`);
    status.append(node('span','遗址机关'),node('span',r.ward_active?'⇄':'×'),node('span',r.contact?'赤髓城阵眼':'异界阵眼'));status.setAttribute('aria-label',r.ward_active?'两端回响连通':'阵眼失效，回响通信中断');host.append(status);
    subview(host,[['investigate','调查'],['core','阵芯'],['traces','痕迹'],['survey','同勘']],'investigate',(body,section)=>{
      if(section==='survey'){renderSurvey(body,r);return;}
      let actions;
      if(section==='investigate'){
        body.append(node('p',r.verified?'两端关联已查明。':r.observed?'已观察阵纹，可以继续查证。':'阵芯与异界阵纹同步明灭，尚未查证其来历。'));
        if(r.record_acquired)body.append(node('p','已取得回潮阵纹合法抄本与一件四阶阵材。'));
        else if(r.survey?.shared)body.append(node('p','已交换勘察笔记，亲自读取缩短为 3 年。'));
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
  function renderSurvey(host,r) {
    const s=r.survey;if(!s)return;
    const place=s.exit||(r.id==='mirror_field'?'穆陵沙漠':'无棣原');
    host.dataset.survey=s.status;
    if(s.status==='unmet'){empty(host,'尚未遇到同行者','可继续亲自调查，在场域中留意真实来访者。');return;}
    if(s.status==='unavailable'){
      title(host,'结伴同勘','邀一位相熟居民自行观察、抄录，归来后当面交流。');
      host.append(node('p',`先亲自踏勘，再返回${place}邀约。可选择人界自由、无其他职责、交情至少 20 的四至五阶居民；每座异象安排一次，同时进行一项。`));
      const route=node('ol',null,'heavens-visit-route');route.setAttribute('aria-label','勘察安排');
      for(const text of ['赴约 · 外界 2 年','观察与抄录 · 空间 8 年','原路退出 · 空间 1 年'])route.append(node('li',text));
      host.append(route);
      if(!s.candidates.length)host.append(node('small','目前没有符合条件的相熟居民。'));
    }else{
      title(host,s.name,({active:'正在勘察',completed:`已返回${place}`,cancelled:s.autonomous?'自行结束探访':'邀约已撤销',failed:'勘察已终止'})[s.status]);
      if(s.autonomous)host.append(node('p',`自行探访 · 交情 ${s.affinity??0}`),node('small','对方自行发现旧路并出发。交换笔记或商请返程须当面相谈且交情至少 20，可前往交往页增进了解。'));
      if(s.autonomous&&(current.world_npcs||[]).some(n=>n.id===s.person_id&&n.perceived_alive))host.append(button('前往交往页交流',()=>{
        if(window.NpcContacts?.open(s.person_id))window.UtilityPanels?.open('relationship');
      }));
      const phase=({outbound:s.autonomous?'寻访旧路':'赴约',studying:'观察与抄录',returning:'原路退出'})[s.phase];
      host.append(node('p',`${phase} · ${s.progress} / ${s.duration} 年`));
      const progress=node('progress');progress.max=s.duration;progress.value=s.progress;progress.setAttribute('aria-label','勘察阶段进度');host.append(progress);
      host.append(node('p',s.shared?`已当面交换笔记，${s.benefit}`:s.learned?`本人已有完整笔记，可在场域内或${place}当面交换。`:s.observed?'本人已完成观察，正在整理笔记。':'本人尚未完成观察。'));
      if(s.blocked_reason)host.append(node('p',s.blocked_reason,'heavens-visit-finding'));
    }
    host.append(node('small','入场后只随同一场域的空间年度行动；你离开时内部冻结，外界年月不补算。本人会真实衰老，笔记不会自动交给你。'));
    renderActions(host,s.actions.filter(a=>s.status==='unavailable'?a.action==='survey_start':a.action==='survey_share'&&s.learned&&!s.shared||s.status==='active'&&(a.action==='survey_wait'||a.action==='survey_recall'&&s.phase!=='returning')),[],s.candidates);
  }
  function renderApplication(host,app){const row=node('article',null,'heavens-task');row.append(node('h4',app.name),node('p',`参悟已登记 · 剩余 ${app.remaining} 个实际修炼年`),button('取消参悟安排',()=>propose('cancel',app.target_id)));host.append(row);}
  function renderMigration(host,h) {
    const selected=(h.migrations||[]).find(m=>m.target_id===ui.target);
    if(!selected){
      const list=node('div',null,'heavens-directory');
      for(const m of h.migrations||[])tile(list,{name:m.name+'的接引',description:`迁往 ${m.destination_name}`,status:({unavailable:'一次民用名额',active:'正在迁居',completed:'已经定居',cancelled:'已撤销',failed:'已终止'})[m.status],glyph:'居',onClick:()=>go('journey',m.target_id,'migration')});
      host.append(node('p','选择出发地，查看真实居民与接引安排。接引是长期迁居，没有自动返乡。'),list);return;
    }
    host.append(button('‹ 返回接引目录',()=>go('journey',null,'migration')));
    if(h.target_id!==selected.target_id){
      if(loadError)host.append(node('p',loadError),button('重新读取接引',()=>{loadError=null;selectSite(selected.target_id);render(current,ctx);}));
      else {host.append(node('p','正在读取接引安排…'));if(!loadingKey)selectSite(selected.target_id);}
      return;
    }
    const m=h.migration;
    if(!m)return;
    host.append(node('h4',m.name),node('p',`接引地点：${m.destination_name}`));
    if(m.status==='unavailable'){
      host.append(node('p','亲自研读确认目的地后，可在出发地或接引地资助一位原住地九阶以上居民迁居。双方交情至少 20；人物须自由且没有势力、关系、队伍或战事职责。'));
      const route=node('ol',null,'heavens-visit-route');route.setAttribute('aria-label','迁居安排');
      for(const text of ['通行 · 2 年','当地安置 · 1 年','长期居住'])route.append(node('li',text));
      host.append(route,node('p','项目承担 4,000 灵石，玩家不另交费。每处接引、每位居民均仅一次。迁走原合作人物，会影响出发地的后续合作。'));
      if(!m.candidates.length)host.append(node('small','目前没有可接洽的居民。可在出发地或接引地办理；居民须在出发地、已有交情并解除其他职责，路线也须开放。'));
    }else{
      host.append(node('h4',m.person_name),badge(({active:'迁居中',completed:'已经定居',cancelled:'已撤销',failed:'已终止'})[m.status]));
      host.append(node('p',`${m.phase==='outbound'?'通行':'当地安置'} · ${m.progress} / ${m.phase==='outbound'?2:1} 年`),node('small',`项目已耗 ${amount(m.spent)} · 预留 ${amount(m.remaining)} · 退回 ${amount(m.refunded)} 灵石`));
      if(m.blocked_reason)host.append(node('p',m.blocked_reason,'heavens-visit-finding'));
      if(m.status==='completed')host.append(node('p',m.alive?'安置已完成，行程占用已解除。可前往目的地通过人物名册继续交往；人物仍会经历正常成长与生死。':'安置记录仍保留，这位居民后来已经陨落。'));
    }
    renderActions(host,m.actions.filter(a=>m.status==='unavailable'?a.action==='migration_start':a.action==='mission_wait'||a.action==='migration_cancel'&&m.status==='active'&&m.phase==='outbound'),[],m.candidates);
  }
  function renderUpkeep(host,h) {
    const rows=h.upkeeps||[],selected=rows.find(u=>u.target_id===ui.target);
    const labels={unavailable:'可查看部署条件',active:'供能中',completed:'已完成',cancelled:'已终止',expired:'窗口已结束',failed:'已结清'};
    if(!selected){
      host.append(node('p','选择一处求道节点，为后续维护预留经费。设施只执行已授权的有限护持。'));
      const list=node('div',null,'heavens-directory');
      for(const u of rows)tile(list,{name:u.name,description:'当地阵材设施 · 有限供能',status:labels[u.status],glyph:'护',onClick:()=>go('journey',u.target_id,'upkeep')});
      host.append(list);return;
    }
    host.append(button('‹ 返回护持目录',()=>go('journey',null,'upkeep')));
    if(h.target_id!==selected.target_id){
      if(loadError)host.append(node('p',loadError),button('重新读取护持',()=>{loadError=null;selectSite(selected.target_id);render(current,ctx);}));
      else {host.append(node('p','正在读取护持安排…'));if(!loadingKey)selectSite(selected.target_id);}
      return;
    }
    const u=h.upkeep;if(!u)return;
    host.dataset.upkeep=u.status;
    title(host,selected.name,labels[u.status]);
    if(u.status==='unavailable'){
      host.append(node('p',`在当地完成当期体察并取得合法抄录后，可预留 ${amount(u.budget)} 灵石、一件本界九阶阵材及法力上限的 5%，由设施完成 ${u.duration} 个外界年的维护。`),node('p',`完成后取得本周期 ${u.extension_years} 年维护余韵与第二次参悟名额，仍共用原参悟收益上限。`));
    }else{
      host.append(node('p',`供能进度 ${u.progress} / ${u.duration} 年`));
      const bar=node('progress');bar.max=u.duration;bar.value=u.progress;bar.setAttribute('aria-label','护持供能进度');host.append(bar);
      host.append(node('p',`已耗 ${amount(u.escrow.spent)} · 托管尚存 ${amount(u.remaining)} · 已退 ${amount(u.escrow.refunded)} 灵石`),node('small',`已安装：${u.material.name||u.material.material_id}；部署法力与安装阵材不退还。`));
      if(u.status==='active')host.append(node('p',`距离本期护持截止尚有 ${u.deadline_remaining} 年；独立空间内度过的年份也计入期限。`));
      if(u.status==='completed')host.append(node('p',u.effective?'本周期维护已生效；亲自维护不会再增加名额或收益上限。':'此前护持已完成，维护余韵不跨周期延续。'));
    }
    host.append(node('small','每处联系仅一次部署，与亲自维护共用当期名额。外界年度供能，独立空间冻结且不补算；窗口过期或此生结束自动结清。可在任意地点终止后续托管，退回未耗经费。'));
    renderActions(host,u.actions.filter(a=>u.status==='unavailable'?a.action==='upkeep_start':u.status==='active'&&a.action==='upkeep_cancel'),u.materials);
  }
  function renderJourney(host,h) {
    title(host,'行程与纪要','查看亲自参与的事务，回顾已有认识。');
    subview(host,[['active','进行中'],['people','同道'],['cargo','货运'],['migration','迁居'],['upkeep','护持'],['history','纪要']],'active',(body,section)=>{
      if(section==='migration'){renderMigration(body,h);return;}
      if(section==='upkeep'){renderUpkeep(body,h);return;}
      if(section==='cargo'){
        const rows=h.freights||[];
        if(!rows.length){empty(body,'尚无货运委托','同道完成回访后，可在原联系的“运材”页登记一件阵材。');return;}
        const list=node('div',null,'heavens-directory');
        for(const f of rows)tile(list,{name:f.name+'的运材委托',description:f.destination_name,status:f.delivered?'已交货':f.status==='active'?'在途':'已结束',glyph:'运',onClick:()=>{openTarget(f.target_id);ui.section='freight';render(current,ctx);}});
        body.append(list);return;
      }
      if(section==='people'){
        const rows=h.missions||[];
        if(!rows.length){empty(body,'尚无同道行程','亲自完成一次跨界研读后，可在原联系的“同道”页约请回访。');return;}
        const list=node('div',null,'heavens-directory');
        for(const m of rows)tile(list,{name:m.name,description:m.destination_name,status:({active:'行程中',completed:'已返乡',cancelled:'已撤销',failed:'已终止'})[m.status],glyph:'访',onClick:()=>{openTarget(m.target_id);ui.section='mission';render(current,ctx);}});
        body.append(list);return;
      }
      if(section==='history'){
        const rows=[...(h.history||[])].reverse(),size=12,pages=Math.max(1,Math.ceil(rows.length/size));ui.historyPage=Math.min(ui.historyPage,pages-1);
        if(!rows.length){empty(body,'尚无纪要','亲历的征兆、求证与履约会记在这里。');return;}
        const list=node('ol',null,'heavens-timeline');for(const row of rows.slice(ui.historyPage*size,(ui.historyPage+1)*size)){const item=node('li');item.append(node('small',`登记后 ${row.year} 年`),node('p',row.text));list.append(item);}body.append(list);
        const pager=node('div',null,'heavens-inline');pager.append(button('上一页',()=>{ui.historyPage--;render(current,ctx);},ui.historyPage===0),node('small',`${ui.historyPage+1} / ${pages}`),button('下一页',()=>{ui.historyPage++;render(current,ctx);},ui.historyPage===pages-1));body.append(pager);return;
      }
      const task=activeTask(h);
      const facilities=(h.upkeeps||[]).filter(u=>u.status==='active');
      if(facilities.length)body.append(button(`${facilities.length} 处托管护持进行中 · 查看`,()=>go('journey',null,'upkeep')));
      const surveys=[h.ruins,h.mirror].filter(a=>a?.survey?.status==='active');
      for(const anomaly of surveys){const survey=anomaly.survey,row=node('article',null,'heavens-task');row.append(node('h4',`${survey.name} · ${anomaly.name}同勘`),node('p',survey.phase==='outbound'?'正在赴约入场。':'本人留在场域中，只随该空间年度行动。'),button('查看同勘',()=>{openTarget(anomaly.id);ui.section='survey';render(current,ctx);}));body.append(row);}
      const away=(h.visits||[]).filter(v=>v.status==='visiting');
      for(const v of away){const row=node('article',null,'heavens-task');row.append(node('h4',`访学 · ${v.destination_name}`),node('p',v.studied?'现场研读已完成，可循约返程。':'已抵达，可研读或提前返程。'),button('查看访学与返程',()=>{openTarget(v.target_id);ui.section='visit';render(current,ctx);}));body.append(row);}
      if(task){
        const names={mirror_field:'镜律场域',causal_ruins:'因果遗址',sand_glimmer:'沙中重影',stone_resonance:'旧石回声',lanjiang_frontier:'岚疆边情'},name=h.sites.find(s=>s.id===task.target_id)?.name||names[task.target_id]||'诸天研究';
        const row=node('article',null,'heavens-task');row.append(node('h4',name),node('p',`当前任务：${task.progress} / ${task.duration} 年`));const progress=node('progress');progress.max=task.duration;progress.value=task.progress;progress.setAttribute('aria-label','任务进度');row.append(progress);
        const controls=node('div',null,'heavens-inline');controls.append(button('继续任务',()=>propose('resume',task.id),Boolean(pending)),button('取消任务',()=>propose('cancel',task.id),Boolean(pending)),button('查看对象',()=>openTarget(task.target_id)));row.append(controls,node('small','取消前会显示可退还的未耗投入，已付法力与已耗材料不退。'));body.append(row);
      }
      if(h.registered_application)renderApplication(body,h.registered_application);
      if(!task&&!h.registered_application&&!away.length&&!surveys.length&&!facilities.length)empty(body,'暂无进行中的行程','可从一条见闻、一处联系或一座异象开始。');
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

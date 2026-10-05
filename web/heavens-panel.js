(() => {
  let current, ctx, pending, selectionRequest=0;
  const node = (tag, text, cls) => {const el=document.createElement(tag);if(text!=null)el.textContent=text;if(cls)el.className=cls;return el;};
  function button(label, action, disabled=false) {const b=node('button',label);b.type='button';b.disabled=disabled;b.onclick=action;return b;}
  async function selectSite(target_id) {
    if(ctx.busy() || pending)return;
    const id=current.id, request=++selectionRequest;
    try {
      const view=await ctx.api(`/api/games/${id}/heavens-view`,{method:'POST',body:JSON.stringify({view:'known',target_id})});
      if(current.id!==id || request!==selectionRequest || view.revision<current.heavens.revision)return;
      current.heavens=view;
      render(current,ctx);
    } catch(error) {ctx.toast(error.message);}
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
  function render(data,context) {
    current=data;ctx=context;
    if(pending && pending.id!==data.id)pending=null;
    const host=document.getElementById('heavens-content'), h=data.heavens;
    if(!host||!h)return;
    const dock=document.querySelector('[data-panel-target="heavens"]');
    const notices=(h.notifications||[]).length;
    if(dock){
      dock.classList.toggle('has-notice',notices>0);
      dock.title=notices?`诸天联系 · ${notices} 条新线索`:'诸天联系';
      dock.querySelector('small').textContent=notices?'新线索':'诸天';
    }
    host.replaceChildren();
    if(pending)host.append(button('重试上次提交（不会重复扣费）',()=>send(pending.payload)));
    const settings=node('div',null,'heavens-group');
    for(const [key,label,value] of [['generation_enabled','允许发现新的诸天联系',h.generation_enabled],['watch','显示诸天机会通知',h.watch],['pause_on_opportunity','发现机会后，在完整修行单位结束时停下',h.pause_on_opportunity]]) {
      const row=node('label'),input=node('input');input.type='checkbox';input.checked=value;
      input.disabled=Boolean(pending)||(!h.generation_available&&key==='generation_enabled')||(key==='pause_on_opportunity'&&h.year==null);
      input.onchange=()=>send({command_seq:h.next_command_seq,expected_revision:h.revision,action:'configure',target_id:null,options:{[key]:input.checked}});
      row.append(input,node('span',label));settings.append(row);
    }
    host.append(settings);
    if(h.mirror && (h.mirror.inside || data.player.world==='human' || h.mirror.known))renderMirror(host,h.mirror);
    if(h.sites?.length) {
      const group=node('div',null,'heavens-group'),select=node('select');select.setAttribute('aria-label','诸天联系地点');
      const placeholder=node('option','选择最高界面的联系地点');placeholder.value='';placeholder.disabled=true;select.append(placeholder);
      for(const site of h.sites){const option=node('option',`${site.world_name} · ${site.name}${site.known?' · 已登记':''}`);option.value=site.id;select.append(option);}
      select.value=h.sites.some(s=>s.id===h.target_id)?h.target_id:'';select.disabled=Boolean(pending);select.onchange=()=>selectSite(select.value);
      group.append(node('h3','四界诸天联系'),select,node('small','可查阅四界联系；亲自参与须抵达相应地点，并具备未压制的九阶以上修为。'));host.append(group);
    }
    for(const notice of h.notifications||[]) {const box=node('div',null,'heavens-group');box.append(node('p',notice.text),button('忽略此通知',()=>propose('dismiss',notice.id)));host.append(box);}
    const echo=h.echo;
    if(echo) {
      const box=node('div',null,'heavens-group');
      box.append(node('h3',echo.name),node('p',echo.remaining?`第 ${echo.cycle+1} 周期 · 窗口余量 ${echo.remaining} 年`:`本次窗口已结束，下周期尚需 ${echo.next_cycle_in} 年。`),node('p',echo.evidence.join(' · ')||'尚无可验证证据'),node('small',`${echo.visitor.name} · ${echo.visitor.available?'在场，可提出合作':'暂不能履约'}；已入研究账目 ${echo.project_stones.toLocaleString()} 灵石。`));
      if(echo.evidence.some(s=>s.startsWith('E2')))box.append(node('small',`旧碑两段记录早于首次登记 ${echo.origin_year-echo.inscriptions[0]} 年、${echo.origin_year-echo.inscriptions[1]} 年。`));
      if(echo.reward_base)box.append(node('small',`本周期实际增益 ${echo.reward_claimed.toFixed(1)}；上限基准 ${echo.reward_base.toLocaleString()}。维护后的再次参悟共用上限。`));
      if(echo.correspondence_completed)box.append(node('small','旧录校订已履约，酬劳已支付。'));
      host.append(box);
    } else host.append(node('p',h.reason));
    if(h.registered_application){const app=h.registered_application,box=node('div',null,'heavens-group');box.append(node('p',`${app.name}：参悟已登记，剩余 ${app.remaining} 个实际修炼年。`),button('取消参悟安排',()=>propose('cancel',app.target_id)));host.append(box);}
    const active=(h.tasks||[]).find(t=>['reserved','running','paused'].includes(t.status));
    if(active){const box=node('div',null,'heavens-group');box.append(node('p',`当前任务：${active.progress} / ${active.duration} 年`),button('继续任务',()=>propose('resume',active.id)),button(active.target_id==='mirror_field'?'取消任务（已付消耗不退）':'取消并退还未耗托管',()=>propose('cancel',active.id)));host.append(box);}
    const actions=node('div',null,'heavens-actions');
    for(const row of h.actions||[]) {
      const box=node('div',null,'heavens-group'),options={...row.options};
      if(row.action==='maintain'&&(h.materials||[]).length){const select=node('select');select.setAttribute('aria-label','维护阵材');for(const m of h.materials){const option=node('option',m.name||m.material_id);option.value=m.id;select.append(option);}select.onchange=()=>{options.material_id=select.value;};box.append(select);}
      box.append(button(row.label,()=>propose(row.action,row.target_id,options),!row.enabled||Boolean(pending)),node('small',row.enabled?`${row.years} 年${row.costs?.stones?' · '+row.costs.stones.toLocaleString()+' 灵石':''}${row.reward_stones?' · 完成酬劳 '+row.reward_stones.toLocaleString()+' 灵石':''}`:row.reason));actions.append(box);
    }
    host.append(actions);
    const history=node('details');history.append(node('summary','查看已知纪要'));
    for(const item of [...(h.history||[])].reverse())history.append(node('p',`登记后 ${item.year} 年：${item.text}`));
    host.append(history);
    if(pending)host.querySelectorAll('input,select').forEach(el=>{el.disabled=true;});
  }
  function renderMirror(host,m) {
    const box=node('section',null,'heavens-group');box.dataset.mirror='field';
    box.append(node('h3',m.name),node('p',`${m.entry} · ${m.inside?'身处场域':m.known?'可重访':'元婴起可亲自进入'}`),node('small',m.description));
    if(m.probed)box.append(node('p',`收集规律已查明 · 当前镜储 ${m.stored_mana.toFixed(1)}；累计收集 ${m.collected_mana.toFixed(1)} / ${m.mana_capacity.toFixed(1)}。`),node('small','登记施术实付法力的 25% 被收集；普通修炼和其他战斗不计入。隔断停止对应联系，守护强度最多增加 15%。'));
    if(m.record_acquired)box.append(node('p','已取得镜律规律记录。'));
    const actionRow=(row,parent)=>{
      const group=node('div',null,'heavens-group'),options={...row.options};
      if(row.action==='mirror_isolate'&&m.materials.length){const select=node('select');select.setAttribute('aria-label',`第 ${Number(options.chamber)+1} 处隔断阵材`);for(const material of m.materials){const option=node('option',material.name||material.material_id);option.value=material.id;select.append(option);}select.onchange=()=>{options.material_id=select.value;};group.append(select);}
      group.append(button(row.label,()=>propose(row.action,row.target_id,options),!row.enabled||Boolean(pending)),node('small',row.enabled?`${row.years} 年${row.costs?.mp?' · 实付 '+row.costs.mp.toLocaleString()+' 法力':''}${row.material_consumed?' · 消耗一件四阶阵材':''}`:row.reason));parent.append(group);
    };
    for(const row of m.actions.filter(a=>a.options.chamber==null))actionRow(row,box);
    for(const chamber of m.chambers||[]){const card=node('div',null,'heavens-group');card.dataset.mirrorChamber=String(chamber.index);card.append(node('h4',`第 ${chamber.index+1} 处机关 · ${chamber.opened?'已解开':chamber.isolated?'联系已隔断':'尚未解开'}`));if(chamber.reward)card.append(node('small',`已领取：${chamber.reward}`));if(chamber.guardian)card.append(node('small',`已遭遇 ${chamber.guardian.encounters} 次；守护强度已锁定，损伤保留。`));const actions=node('div',null,'heavens-actions');for(const row of m.actions.filter(a=>a.options.chamber===String(chamber.index)))actionRow(row,actions);card.append(actions);box.append(card);}
    if(m.traces?.length)box.append(node('small',`已保留 ${m.traces.length} 条施术或施工痕迹，退出不会抹除。`));
    host.append(box);
  }
  window.HeavensPanel={render};
})();

(() => {
  const el = (tag, text, className) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (className) n.className = className; return n; };
  const fmt = n => Number(n || 0).toLocaleString('zh-CN', {maximumFractionDigits: 2});
  let selectedTechnique = null;
  let submitting = false;
  window.BuddhistPanel = {render(system, mutate, context = {}) {
    const panel = document.querySelector('#buddhist-card');
    const dock = document.querySelector('[data-panel-target="buddhist"]');
    panel.classList.toggle('hidden', !system.available); dock.classList.toggle('hidden', !system.available);
    if (!system.available) { window.UtilityPanels?.close('buddhist'); return; }
    const body = document.querySelector('#buddhist-content'); body.replaceChildren();
    const locked = !!context.pending || !context.alive;
    const action = (label, operation, payload = {}, disabled = false) => {
      const button = el('button', label); button.type = 'button'; button.disabled = disabled || locked;
      button.onclick = async () => { if (submitting) return; submitting = true; button.disabled = true; try { await mutate({action: operation, ...payload}); } finally { submitting = false; if(button.isConnected) button.disabled = disabled || locked; } };
      return button;
    };
    const section = title => {const node = el('section'); node.append(el('h3', title)); body.append(node); return node;};
    const hero = el('div', undefined, 'dharma-hero');
    const lotus = el('div', '莲', 'dharma-seal'); lotus.setAttribute('aria-hidden', 'true');
    const intro = el('div'); intro.append(el('p', '众生为镜 · 诸法无我', 'eyebrow'), el('h3', '一处讲席，一方人间'), el('p', '弘法聚信，建寺留灯。业力往复，道途自择。', 'muted'));
    hero.append(lotus, intro); body.append(hero);
    const balance = section('此身业力');
    const value = el('strong', `${system.karma >= 0 ? '+' : ''}${fmt(system.karma)}`, 'dharma-number');
    balance.append(value);
    const meter = el('div', undefined, 'dharma-meter'); meter.setAttribute('role', 'meter'); meter.setAttribute('aria-label', '业力'); meter.setAttribute('aria-valuemin', '-100'); meter.setAttribute('aria-valuemax', '100'); meter.setAttribute('aria-valuenow', system.karma);
    const fill = el('i'); fill.style.left = `${Math.min(50, (system.karma + 100) / 2)}%`; fill.style.width = `${Math.abs(system.karma) / 2}%`; fill.className = system.karma < 0 ? 'negative' : 'positive';
    meter.append(fill, el('span', '', 'dharma-zero'), el('span', '', 'dharma-warning')); balance.append(meter);
    const ticks = el('div', undefined, 'dharma-ticks'); ticks.append(el('span', '−100'), el('span', '−25'), el('span', '0'), el('span', '+100')); balance.append(ticks);
    let status = system.karma < -25 ? `暂不能开坛。${system.grace_units > 0 ? `威名庇护还剩 ${fmt(system.grace_units)} 个时间单位。` : '威名庇护已失效。'}` : '威名庇护生效；个人恩怨、战争与地方通缉仍需应对。';
    if (system.karma < 0) status += ` 当前战斗六维 +${fmt(-system.karma * .2)}%。`;
    balance.append(el('p', status, system.karma < -25 ? 'dharma-alert' : 'muted'));
    const metrics = el('div', undefined, 'dharma-metrics');
    for (const [label, number] of [['本界信众',fmt(system.followers)],['每年业力开支',fmt(system.upkeep)],['有效威名',fmt(system.effective_fame)]]) {const box=el('div');box.append(el('small',label),el('strong',number));metrics.append(box);} balance.append(metrics);
    balance.append(el('p', `原始因果 ${fmt(system.raw_karma)} · 原始煞气 ${fmt(system.raw_sha)}；日常规则均按 0 结算，开坛时仍会形成问难。`, 'muted'));
    const blessings = section('世间加持'); blessings.append(el('p','正业力时最多选择三项，仅在选择的界面生效；业力耗尽会自动停用。', 'muted'));
    const cards=el('div',undefined,'dharma-blessings');
    const selectedCount=system.blessings.filter(x=>x.selected).length;
    system.blessings.forEach(row=>{const card=action('', 'blessing', {blessing:row.id}, !row.selected && (system.karma<=0 || selectedCount>=3));card.className=`dharma-blessing${row.selected?' selected':''}`;card.setAttribute('aria-pressed',String(row.selected));card.append(el('strong',row.name),el('p',row.description),el('small',`${row.selected?'已启用 · ':''}每年消耗 ${fmt(row.annual_cost)} 业力`));cards.append(card);});blessings.append(cards);
    const assembly = section('诸法无我 · 佛法大会');
    assembly.append(el('p', `三次行动间隔，依次开坛、论法、结会。预计到场 ${fmt(system.attendance)} 人 · 问难风险：${system.risk}。`, 'muted'));
    const permissions=el('div',undefined,'dharma-permissions');
    system.permissions.forEach(row=>{const item=el('div'); item.append(el('span',`${row.name} · ${row.intimidated?'高阶威慑 · 无许可也不敢干预':row.exempt?'身份或盟约许可':row.permitted?`许可至第 ${row.expires} 年`:'未获弘法许可'}`)); if(!row.permitted && !row.intimidated)item.append(action(`缴纳 ${fmt(row.fee)} 灵石`, 'permission', {authority:row.id})); permissions.append(item);});assembly.append(permissions);
    if(system.permissions.some(x=>!x.permitted && !x.intimidated))assembly.append(el('p','可以直接开坛，但未获许可的各势力可能分别干预、驱散信众至寺庙保底，甚至通缉。','dharma-alert'));
    if(system.assembly){
      const session=system.assembly; assembly.append(el('h4',`《${session.technique_name}》Lv.${session.level}`));
      const steps=el('ol',undefined,'dharma-stages');['开坛','论法','结会'].forEach((name,index)=>{const step=el('li',name);step.className=index<session.stage?'done':index===session.stage?'current':'';steps.append(step);});assembly.append(steps);
      const progress=el('progress');progress.max=3*session.unit_years;progress.value=session.stage*session.unit_years+session.stage_years;progress.setAttribute('aria-label','法会时间进度');assembly.append(progress);
      assembly.append(el('p',`第 ${session.started_age} 年开坛 · 已完成 ${session.stage}/3 场 · 当前评价 ${fmt(session.score)}`, 'muted'));
      for(const event of session.events)assembly.append(el('p',`第 ${event.stage} 场：评价 ${event.score>=0?'+':''}${fmt(event.score)}`,'muted'));
      const controls=el('div',undefined,'dharma-actions');controls.append(action(context.pending?'先处理当前事件':'继续法会','continue'),action('提前散会（按失利结算）','cancel'));assembly.append(controls);
    }else{
      const arts=el('div',undefined,'dharma-techniques');arts.setAttribute('role','group');arts.setAttribute('aria-label','选择讲授功法');
      if(!system.techniques.some(row=>row.id===selectedTechnique))selectedTechnique=system.techniques[0]?.id || null;
      const start=action('开坛弘法','start',{},!system.can_assemble || !selectedTechnique);
      start.onclick=async()=>{if(submitting||start.disabled)return;submitting=true;start.disabled=true;try{await mutate({action:'start',technique:selectedTechnique});}finally{submitting=false;if(start.isConnected)start.disabled=!system.can_assemble||!selectedTechnique||locked;}};
      system.techniques.forEach(row=>{const b=el('button',`${row.name} · Lv.${row.level}`);b.type='button';b.classList.toggle('selected',row.id===selectedTechnique);b.setAttribute('aria-pressed',String(row.id===selectedTechnique));b.onclick=()=>{selectedTechnique=row.id;arts.querySelectorAll('button').forEach(node=>{node.classList.toggle('selected',node===b);node.setAttribute('aria-pressed',String(node===b));});};arts.append(b);});
      if(!system.techniques.length)arts.append(el('p','先学习一门功法，再与众生分享所悟。','muted'));
      assembly.append(arts,el('p','讲授水平主要取决于功法等级；任一道统与类别的已学功法均可选用。','muted'),start);
    }
    const temples=section('香火版图');
    const local=el('div',undefined,'dharma-actions');local.append(el('p',`此地寺庙：${system.site.temple} 级`));if(system.temple_cost!==null)local.append(action(`升建寺庙 · ${fmt(system.temple_cost)} 灵石`, 'temple'));temples.append(local);
    temples.append(el('p','各地信众每年自然衰减，寺庙留下最低信众。异界香火仍会衰减，但不输送个人收益。','muted'));
    const list=el('div',undefined,'dharma-sites');system.sites.forEach(row=>{const card=el('div');card.append(el('strong',`${row.world_name} · ${row.name}`),el('p',`${row.temple} 级寺庙 · 信众 ${fmt(row.followers)} · 保底 ${row.floor}`),el('small',`年衰减 ${fmt(row.decay*100)}% · ${row.active?'本界香火':'异界 · 收益暂停'}`));list.append(card);});temples.append(list);
    const chronicle=section('弘法纪事');if(!system.history.length)chronicle.append(el('p','尚未留下弘法足迹。','muted'));system.history.slice().reverse().forEach(row=>chronicle.append(el('p',`第 ${row.age} 年 · ${row.text}`)));
    const route=section('两途皆可成道');route.append(el('p',system.route),el('p','人界飞升时，灵气经验不少于阴气经验则往灵界，否则往地狱界。随后分别通往仙界、轮回界；沿途保留佛修道统，并遵守原有飞升境界与劫关条件。','muted'));
  }};
})();

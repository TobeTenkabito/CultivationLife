/* Public projections only: actual people, prices and custody remain server-owned. */
(() => {
  const e=(...a)=>window.GameUi.element(...a),fmt=n=>Number(n||0).toLocaleString('zh-CN');
  const fraction=n=>{const [a,b]=String(n||0).split('/').map(Number);return (a/(b||1)).toLocaleString('zh-CN',{maximumFractionDigits:3});};
  const phases={outbound:'赴任途中',work:'现场办理',ready:'等待现场处置／验收',homeward:'循路返程',handover:'等待交接',evacuating:'伤者转运途中',failed:'未达成目标 · 待交接'};
  function render(root,data,dispatch,projects){
    if(!data?.available)return;
    const legacy=[...root.children],section=e('section',null,'court-bureaus');section.id='court-bureaus';
    root.append(section);
    const button=(text,action,target='',blocked='',primary=false)=>{
      const b=e('button',text,primary?'primary':'');b.type='button';b.dataset.bureauAction=action;b.dataset.bureauTarget=target;
      b.dataset.courtUnavailable=blocked?'1':'0';b.disabled=!!blocked;b.title=blocked||text;
      b.onclick=()=>dispatch({action:'bureau_'+action,target_id:data.token+(target?'|'+target:'')});return b;
    };
    const header=e('header',null,'bureau-heading'),office=data.offices.find(o=>o.id===data.office);
    header.append(e('small','玉京诸司 · 各守其责','bureau-eyebrow'),e('h3',office?office.name+' · '+(data.supervisor?'掌司':'在职'):'诸司任职'),
      e('p',data.leave?'告假中 · 旧承诺仍须交接':'以原官品任职，以实际履约考课。','muted'));
    const stats=e('dl',null,'bureau-stats');
    for(const [name,value] of [['原天庭府库',fmt(data.treasury)],['在办公务',data.jobs.length],['本司亲办',data.completed[data.office]||0],['属员名额',data.staff.length+' / 2']]){
      const box=e('div');box.append(e('dt',name),e('dd',value));stats.append(box);
    }section.append(header,stats);
    if(data.reason)section.append(e('p',data.reason,'bureau-notice'));
    if(data.last_result)section.append(e('p',data.last_result,'bureau-receipt'));
    const pages=e('div',null,'bureau-pages'),appointments=e('section'),duties=e('section'),staff=e('section'),history=e('section'),inspection=e('section');
    pages.append(appointments,duties,staff,history,inspection);section.append(pages);
    appointments.append(e('h4','选择职责'),e('p','任职不出售官品。七品起、亲自完成本司两项差事后，可申请主管空缺；调任须先交接公物和全部任务。','muted'));
    const grid=e('div',null,'bureau-grid');
    for(const o of data.offices){const card=e('article',null,'bureau-card');card.dataset.bureauOffice=o.id;
      const title=e('div',null,'bureau-card-title');title.append(e('span',o.mark,'bureau-seal'),e('h4',o.name));card.append(title,e('p',o.text),e('small',`基础现场工时 ${o.years} 年 · 旅行另计`),
        button(data.office===o.id?'当前任职':data.office?'交接并调任':'接受任职','join',o.id,data.join_reason||(data.office===o.id?'已任此职':''),true));grid.append(card);
    }appointments.append(grid);
    if(data.office){const actions=e('div',null,'bureau-actions');actions.append(button('申请主管','promote','',data.promote_reason||(data.supervisor?'已为主管':'')),
      button(data.leave?'销假':'请假',data.leave?'resume':'leave','',data.home_reason),button('交接离任','resign','',data.recovery_home_reason||(data.jobs.length?'须先交接全部公务':'')));appointments.append(actions);
      if(data.promote_reason)appointments.append(e('p',data.promote_reason,'muted'));}
    duties.append(e('h4','当前案卷'));
    if(!data.jobs.length)duties.append(e('p','暂无在办公务。下方差事按本人当前所在地的真实对象列出。','muted'));
    for(const j of data.jobs){const card=e('article',null,'bureau-current');card.dataset.bureauJob=j.id;
      card.append(e('small',`${j.person_name} · ${phases[j.phase]||j.phase}`,'bureau-eyebrow'),e('h4',j.name),
        e('p',`${j.place_name} · 现场 ${j.progress} / ${j.years} 年 · 截止 ${j.deadline} 年`));
      if(j.leg&&['outbound','homeward'].includes(j.phase))card.append(e('p',`实际路程 ${j.leg.progress} / ${j.leg.years} 年`));
      if(j.evacuation)card.append(e('p',`伤者实际转运 ${j.evacuation.progress} / ${j.evacuation.years} 年`));
      if(j.offer.detail)card.append(e('p',j.offer.detail,'bureau-notice'));
      if(j.offer.operation==='bounty')card.append(e('p',`接案时目标：${j.offer.target_state[0]}阶 ${j.offer.target_state[1]}层 · 临战仍按原人物当前状态结算`,'muted'));
      if(j.battle)card.append(e('p',j.battle.summary,'bureau-receipt'));
      const bar=e('progress');bar.max=j.years;bar.value=j.progress;bar.setAttribute('aria-label','公务实际进度');card.append(bar);
      card.append(e('p',`原款托管 ${fmt(j.remaining_cash)} 灵石 · 公物 ${Object.values(j.cargo).reduce((a,b)=>a+b,0)} 件 · 总功德 ${fraction(j.reward)}`,'muted'));
      if(j.blocked||j.expired)card.append(e('p',j.blocked||(j.expired?'本案已逾期，请交接，不能补领报酬':''),'bureau-notice'));
      const actions=e('div',null,'bureau-actions');
      const operationPending=j.offer.operation&&!j.operation_done;
      if(j.phase==='ready'&&operationPending){
        const blocked=data.reason||j.site_reason||j.operation_reason||(j.expired?'公务逾期':'');
        if(j.offer.operation==='bounty')actions.append(button('持令击退','fight',j.id+'~repel',blocked,true),button('致命讨伐 · 承担伤亡风险','fight',j.id+'~kill',blocked));
        else actions.append(button('核验救治并启动实际转运','evacuate',j.id,blocked,true));
      }
      if(j.person==='player'&&j.progress<j.years)actions.append(button('继续亲自履约','work','',data.work_reason|| (j.expired?'公务逾期':''),true));
      if(j.person!=='player'&&j.phase==='ready'&&!data.review&&!operationPending)actions.append(button('开始本人复核 · 5年','review',j.id,data.reason||j.site_reason||(j.expired?'公务逾期':''),true));
      if(data.review?.job===j.id){card.append(e('p',`本人复核 ${data.review.progress} / 5 年`));
        if(data.review.progress<5)actions.append(button('继续本人复核','work','',data.work_reason,true));
        actions.append(button('退出复核','cancel_review','',data.recovery_reason));}
      if(j.phase==='ready'&&!operationPending)actions.append(button('验收交付','claim',j.id,data.reason||j.site_reason||(j.person!=='player'&&(data.review?.job!==j.id||data.review.progress<5)?'须完成本人复核':'')||(j.expired?'公务逾期':''),true));
      const recovery=e('details');recovery.append(e('summary','返程与公物交接'),e('p','取消不返还已耗劳务与采购费用。未耗款退原府库，剩余公物当面移交原市场；在途属员须实际返程。','muted'));
      if(j.phase==='evacuating')recovery.append(button('处理转运失效','abort_rescue',j.id,data.recovery_reason||j.abort_reason));
      if(j.kind==='works'&&j.person==='player'&&!j.diversion)recovery.append(e('p','应急改拨会实际用于此地短缺，原合同仍欠交，后续须补交或接受监察处分。','bureau-notice'),button('确认应急改拨并留案','divert',j.id,data.reason||j.diversion_reason));
      if(j.person!=='player'&&j.phase!=='handover')recovery.append(button(j.phase==='homeward'?'正在返程':'召回属员','recall',j.id,data.recovery_reason||(j.phase==='homeward'?'已在返程，不可重置路程':'')));
      recovery.append(button('交接公物并结清','handover',j.id,j.handover_reason));card.append(actions,recovery);duties.append(card);
    }
    duties.append(e('h4','本地可办差事'),e('p','费用由原府库足额托管，采购使用原市场库存。报价、原对象或人员状态变化后须重新确认。','muted'));
    if(!data.offers.length)duties.append(e('p',data.office==='land'?'此地没有符合条件的公开城市遗址。':data.office==='works'?'缺少已知相邻市场的真实短缺与本地货源。':data.office==='audit'?'暂无待复核的已结公务案卷。':'任职后可查看本地可办差事。','muted'));
    const board=e('div',null,'bureau-grid');
    for(const offer of data.offers){const card=e('article',null,'bureau-card');card.dataset.bureauOffer=offer.token;
      card.append(e('h4',offer.name),e('p',`现场 ${offer.years} 年 · 采购 ${fmt(offer.purchase)} · 工程 ${fmt(offer.coins)} 灵石`));
      if(offer.detail)card.append(e('p',offer.detail,'muted'));
      if(offer.operation==='bounty')card.append(e('p',`目标：${offer.target_state[0]}阶 ${offer.target_state[1]}层 · 原伤势 ${offer.target_state[2]}级`,'bureau-price'));
      const label=e('label','执行者'),select=e('select');select.setAttribute('aria-label','公务执行者');
      for(const a of offer.executors){const option=e('option',a.name);option.value=a.id;select.append(option);}label.append(select);card.append(label);
      const detail=e('div');card.append(detail);
      const redraw=()=>{const a=offer.executors.find(x=>x.id===select.value);detail.replaceChildren(e('p',`预算 ${fmt(a.budget)} 灵石 · ${a.travel?`属员往返 ${a.travel} 年 · `:''}总功德 ${fraction(a.reward)}`,'bureau-price'),
        button(a.id==='player'?'落实预算并亲办':'落实预算并派遣','accept',offer.token+'~'+a.id,a.reason,true));if(a.reason)detail.append(e('small',a.reason,'muted'));};select.onchange=redraw;redraw();board.append(card);
    }duties.append(board,e('p','功德余量共同累计：'+fraction(data.remainder)+'。亲办不叠发仙痕、机缘或香火；属员取得原总额九成，主管实际复核后取得一成。','muted'));
    staff.append(e('h4','本司属员'),e('p','仅任命原天官名册中的真实人物。须在玉京当面办理；在办期间占用原人物，任务结束与公物交接后恢复自由调度。','muted'));
    for(const n of data.staff){const card=e('article',null,'bureau-card');card.append(e('h4',n.name),e('p',`所在地点：${n.location_name} · 公务功德 ${fraction(n.merit)}`),button('解除本司任命','release',n.id,data.recovery_home_reason||(data.jobs.some(j=>j.person===n.id)?'须先返回并交接公务':'')));if(n.reason)card.append(e('small',n.reason,'muted'));staff.append(card);}
    staff.append(e('h4','在场天官'));
    for(const n of data.candidates.filter(n=>!n.department)){const row=e('article',null,'bureau-person');row.append(e('strong',n.name),e('small',`${n.realm}阶`),button('任命为属员','appoint',n.id,data.home_reason||(!data.supervisor?'须先取得主管资格':'')||n.reason||(data.staff.length>=2?'两席已满':'')));staff.append(row);}
    if(!data.candidates.length)staff.append(e('p','此地没有可见的原天官人物。虚拟选举席位不能替代属员。','muted'));
    history.append(e('h4','近十二份履历'));
    for(const j of [...data.history].reverse()){const r=j.receipt,card=e('article',null,'bureau-card');card.append(e('h4',j.name),e('p',r?.result||'已归档'),e('small',`采购 ${fmt(r?.purchase)} · 劳务 ${fmt(r?.labor)} · 工程 ${fmt(r?.engineering)} · 退回 ${fmt(r?.refunded)} 灵石${j.audited?' · 已经御史复核':''}`));history.append(card);}
    if(!data.history.length)history.append(e('p','完成或交接公务后保留实际收支回执。','muted'));
    window.CourtInspection?.render(inspection,data,button);
    window.PanelPages.mount('court-bureau-pages',pages,[['任职', [appointments]],['差事',[duties]],['属员',[staff]],['监察',[inspection]],['履历',[history]]]);
    const council=window.WestwardVentures?.council(root,projects,dispatch);
    window.PanelPages.mount('court-bureau-root',root,[['天庭政务',legacy],['诸司任职',[section]],...(council?[['项目议政',[council]]]:[])]);
  }
  window.CourtBureaus={render};
})();

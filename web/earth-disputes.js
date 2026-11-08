/* Case facts and costs are server projections; tabs never register incidents. */
(() => {
  const e=(...a)=>window.GameUi.element(...a);
  function render(data,button){
    const d=data.disputes,root=e('section',null,'earth-disputes');
    const heading=e('header',null,'earth-case-heading');
    heading.append(e('small','六事听讼 · 各有所归','yaochi-eyebrow'),e('h4','地方来报'),
      e('p',`本期至世界历 ${d.until.toLocaleString('zh-CN')} 年。只登记可核验的本地事项；换页和读档不会重开旧案。`,'muted'));
    root.append(heading);
    const notice=e('details',null,'yaochi-materials');notice.append(e('summary','登记与承诺的边界'),
      e('p','登记只接收来报，不代你许诺。每类每庙每500年一期；道路塌方登记后会增加沿该路的普通远行耗时。未许诺可无损婉拒，拒绝不会消除道路损坏。'),
      e('p','调查5年后选择方案，再亲自执行。工料不预扣，最后复核按当前报价交付。许诺后主动撤回通常损失5信任；对象或权限失效可无罚撤回。信任影响原香火加持，结案不续期、不另发助修或功德功勋。','muted'));
    root.append(notice,button('核对并登记本期来报','earth_case_report','',d.report_reason,true));
    if(d.report_reason)root.append(e('p',d.report_reason,'yaochi-unavailable'));
    const a=d.active;
    if(a){
      const box=e('article',null,'earth-case-active');box.dataset.caseActive=a.kind;
      box.append(e('small',`正在办理 · ${a.title}`,'yaochi-eyebrow'),e('h4',a.name));
      const steps=e('ol',null,'earth-steps');
      ['调查协商','选择方案','本人执行','复核交付'].forEach((name,i)=>{const n=e('li',name);n.classList.toggle('current',i===(a.stage==='investigate'?0:a.stage==='decide'?1:a.progress<a.years?2:3));steps.append(n);});
      box.append(steps,e('p',a.evidence,'earth-case-evidence'));
      if(a.reason||a.stale)box.append(e('p',a.reason||a.stale,'yaochi-notice'));
      if(a.stage!=='decide'){
        box.append(e('p',`本段已办理 ${a.progress} / ${a.years} 年 · 本期截止 ${a.until} 年`));
        const p=e('progress');p.max=a.years;p.value=a.progress;p.setAttribute('aria-label','地方争议实际工时');box.append(p);
        if(a.progress<a.years)box.append(button('继续本人办理','earth_work','',a.reason,true));
        else if(a.stage==='investigate')box.append(button('核对证据并比较方案','earth_case_prepare','',a.reason||a.stale,true));
      }
      if(a.stage==='decide'||a.stage==='execute'&&a.progress>=a.years){
        const plans=e('div',null,'earth-case-plans');
        for(const p of a.options.filter(p=>a.stage==='decide'||p.id===a.plan)){
          const card=e('article');card.dataset.casePlan=p.id;
          card.append(e('h4',p.name),e('p',p.effect),e('strong',`${p.years} 年 · 信任 ${p.trust>=0?'+':''}${p.trust}`),e('p',p.cost,'earth-price'));
          const blocked=a.reason||p.reason||(a.stage==='decide'&&data.age+p.years>=a.until?'本期剩余时间不足':'');
          card.append(button(a.stage==='decide'?'承诺此方案':'按当前报价交付并结案',a.stage==='decide'?'earth_case_plan':'earth_case_resolve',p.id+':'+p.token,blocked,true));
          if(blocked)card.append(e('small',blocked,'yaochi-unavailable'));
          plans.append(card);
        }box.append(plans);
      }
      const exit=e('details',null,'yaochi-exit');exit.append(e('summary','撤回与失效处理'),e('p','未许诺不扣信任；已许诺主动撤回扣5信任，原对象或权限失效时免罚。已耗工时不返还。','muted'),button('撤回本案','earth_case_cancel','',a.cancel_reason));box.append(exit);root.append(box);
    }
    const grid=e('div',null,'earth-case-grid');
    for(const r of d.rows){
      const c=r.case,card=e('article',null,'earth-case-card');card.dataset.caseKind=r.id;
      const title=e('div',null,'earth-case-title');title.append(e('span',r.mark,'yaochi-seal'),e('h4',r.name));card.append(title);
      card.append(e('p',r.intro),e('small',c?`${c.title} · ${c.stage==='reported'?'待回应':c.stage==='closed'?'已归档':'办理中'}`:r.missing,'muted'));
      if(c?.stage==='reported'){
        const details=e('details');details.append(e('summary','查看已知事实'),e('p',c.evidence));card.append(details);
        const actions=e('div',null,'earth-case-actions');actions.append(button('受理调查','earth_case_accept',c.id,r.reason||d.occupied,true),button('婉拒来报','earth_case_decline',c.id,!d.local?'须亲赴本庙':d.occupied));card.append(actions);
      }else if(c?.stage==='closed')card.append(e('p',c.outcome,'earth-case-outcome'));
      grid.append(card);
    }root.append(grid);
    if(d.history.length){const archive=e('details',null,'yaochi-budget');archive.append(e('summary','近十二次处理记录'));for(const h of [...d.history].reverse())archive.append(e('p',`${h.year} 年 · ${h.name}｜${h.outcome}`));root.append(archive);}
    return root;
  }
  window.EarthDisputes={render};
})();

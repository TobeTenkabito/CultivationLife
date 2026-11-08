/* Evidence and review pages consume server-owned case projections. */
(() => {
  const e=(...a)=>window.GameUi.element(...a);
  const stages={evidence:'取证',decision:'拟议处置',review:'独立复核',execute:'待执行',closed:'已结案'};
  const actions=(...nodes)=>{const box=e('div',null,'bureau-actions');box.append(...nodes);return box;};
  function render(root,data,button){
    const view=data.inspection;if(!view)return;
    if(view.notice){root.append(e('p',view.notice,'bureau-notice'));return;}
    root.append(e('h4','察实情 · 明责任'),e('p','核账、现场查验与申辩各需五年，处置须由独立天官再复核五年。原官品、七曜和通缉权遵守原制度。','muted'));
    if(data.restriction)root.append(e('p',data.restriction,'bureau-notice'));
    for(const c of [...view.cases].reverse()){
      const card=e('article',null,'bureau-current');card.dataset.inquiry=c.id;
      card.append(e('small',c.status==='paused'?'暂缓 · 原卷保留':stages[c.stage],'bureau-eyebrow'),e('h4',c.name),
        e('p',c.facts.summary),e('small',`查验地点：${c.place_name} · 实际劳务 ${Number(c.spent).toLocaleString()} 灵石`));
      if(c.proposed)card.append(e('p',`处理意见：${c.verdicts.find(v=>v.id===c.proposed)?.name||'待核验'} · 复核人：${c.reviewer_name}`,'bureau-receipt'));
      const evidence=e('div',null,'bureau-evidence');
      for(const [key,title] of Object.entries(view.steps)){
        const row=e('div',null,c.evidence[key]?'bureau-evidence-done':'');
        row.append(e('strong',title),e('small',c.evidence[key]?`已核验 · ${c.evidence[key].age}年`:'尚待查验 · 五年'));
        if(c.evidence[key]?.attendance)row.append(e('small',c.evidence[key].attendance));
        if(c.evidence[key]){const proof=e('details');proof.append(e('summary','查看当时凭据'),e('p',c.evidence[key].facts.summary));
          const receipt=c.evidence[key].facts.receipt;if(receipt)proof.append(e('small',`原款 ${receipt.reserved.toLocaleString()} · 采购 ${receipt.purchase.toLocaleString()} · 劳务 ${receipt.labor.toLocaleString()} · 工程 ${receipt.engineering.toLocaleString()} · 退回 ${receipt.refunded.toLocaleString()} 灵石`));row.append(proof);}
        const place=key==='site'?c.location:view.home;
        if(c.status==='active'&&!c.evidence[key])row.append(button('开始查验','case_step',c.id+'~'+key,data.reason||(c.work?'请先完成当前步骤':'')||(view.location!==place?'须到对应取证地点':'')));
        evidence.append(row);
      }card.append(evidence);
      if(c.work){const bar=e('progress');bar.max=c.work.years;bar.value=c.work.progress;
        card.append(e('p',`${c.work.key==='review'?'独立复核':view.steps[c.work.key]} ${c.work.progress} / ${c.work.years} 年`),bar);
        if(c.status==='active')card.append(button('继续办理','work','',view.work_reason,true));}
      if(c.status==='active'&&['review','execute'].includes(c.stage)&&c.reviewer_reason)card.append(e('p',c.reviewer_reason,'bureau-notice'),button('交接失效复核并另请天官','case_reassign',c.id,data.home_reason));
      if(c.status==='active'&&['evidence','decision'].includes(c.stage)&&!c.work){
        const label=e('label','当事人说明'),select=e('select');select.setAttribute('aria-label','监察申辩');
        for(const [key,title] of Object.entries(view.defences)){const option=e('option',title);option.value=key;select.append(option);}
        select.value=c.defence||'acknowledge';label.append(select);card.append(label);
        const submit=button('登记说明','case_defend',c.id+'~'+select.value,data.reason||(view.location!==view.home?'须回玉京受理':''));
        // Rebuild this compact control on change without dispatching automatically.
        const wrap=e('div');wrap.append(submit);select.onchange=()=>wrap.replaceChildren(button('登记说明','case_defend',c.id+'~'+select.value,data.reason||(view.location!==view.home?'须回玉京受理':'')));
        card.append(wrap);
      }
      if(c.status==='active'&&Object.keys(c.facts.owed).length)card.append(button('从本人行囊补交欠货','case_restitution',c.id,data.reason||c.restitution_reason));
      if(c.status==='active'&&c.stage==='decision'){
        const choices=e('div',null,'bureau-grid');
        for(const v of c.verdicts){const choice=e('div',null,'bureau-verdict');choice.append(button((c.proposed===v.id?'已拟定 · ':'')+v.name,'case_propose',c.id+'~'+v.id,data.reason||(!c.defence?'请先登记说明':'')||v.reason));if(v.reason)choice.append(e('small',v.reason,'muted'));choices.append(choice);}card.append(choices);
        if(c.proposed){card.append(e('h4','选择独立复核人'));
          for(const n of c.reviewers){const row=e('div',null,'bureau-person');row.append(e('strong',n.name),button('请其复核','case_reviewer',c.id+'~'+n.id,data.reason||n.reason||(view.location!==view.home?'须回玉京':'')));if(n.reason)row.append(e('small',n.reason,'muted'));card.append(row);}
          if(!c.reviewers.length)card.append(e('p','玉京暂无独立原天官可当面接卷；不能生成替代裁判。','muted'));}
      }
      if(c.status==='active'&&c.stage==='execute')card.append(button('执行已复核处置','case_execute',c.id,data.reason||(view.location!==view.home?'须回玉京':''),true));
      if(c.status!=='paused'&&c.reviewed&&!c.appealed&&['execute','closed'].includes(c.stage))card.append(button('申请一次独立复核','case_appeal',c.id,data.home_reason));
      if(c.status==='active')card.append(actions(button('暂缓并交回未耗预算','case_cancel',c.id,data.recovery_reason)));
      if(c.status==='paused')card.append(button('续查原案','case_resume',c.id,data.home_reason||(view.active?'已有在查案件':'')));
      if(c.result)card.append(e('p',c.result,'bureau-receipt'));root.append(card);
    }
    root.append(e('h4','原记录中的待查线索'));
    for(const lead of view.leads){const card=e('article',null,'bureau-card');card.append(e('h4',lead.name),e('p',lead.facts.summary),button('登记调查 · 预留25000灵石','case_open',lead.token,data.home_reason||(data.office!=='audit'?'须正式任职御史台':'')||(view.active?'请先完成或暂缓当前调查':''),true));root.append(card);}
    if(!view.leads.length)root.append(e('p','暂无新的原始事实线索。正常履约、普通亲属关系和自然损毁不会被随机编成罪证。','muted'));
  }
  window.CourtInspection={render};
})();

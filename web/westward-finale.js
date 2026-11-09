/* Read-only chapter/identity projections; mutations use the original Yaochi API. */
(() => {
  const e=(...args)=>window.GameUi.element(...args),f=n=>Number(n||0).toLocaleString('zh-CN');
  function section(root,title,text){const s=e('section',null,'yaochi-gathering westward-finale');s.append(e('h3',title),e('p',text,'muted'));root.append(s);return s;}
  function button(label,action,target,why,dispatch){const b=e('button',label);b.type='button';b.dataset.finaleAction=action;b.disabled=!!why;b.title=why||label;b.onclick=()=>dispatch({action,target_id:target});return b;}
  function card(root,title){const c=e('article',null,'gather-card');c.append(e('h4',title));root.append(c);return c;}
  function identity(root,game,dispatch){
    const d=game.yaochi.identity;if(!d)return null;
    const s=section(root,'仙籍与功德','三途是职责与修行方式；真仙、金仙、太乙、大罗仍沿原境界成长。');
    const grid=e('div',null,'gather-grid');s.append(grid);
    for(const [id,name,text] of [['free','散仙','无常设编制，不依靠香火；访古、经营、仙会与紫气主线照常参与。'],['earth','地仙','在原庙主持护民并依当地香火助修；离庙暂停，主庙与分庙的额度不叠加。'],['xuan','玄仙','凭原职司或在任七曜席位确立编制；正式办差换取功德，私产不等于地仙主持。']]){
      const c=card(grid,name);c.classList.toggle('finale-current',id===d.primary);c.append(e('small',id===d.primary?'当前主身份':'职责选择','yaochi-eyebrow'),e('p',text));
    }
    const actions=e('div',null,'gather-actions');actions.append(button('登记原主庙神位','identity_register',d.token,d.register_reason,dispatch),button('交接并退隐散修','identity_retire',d.token,d.retire_reason,dispatch));s.append(actions);
    s.append(e('p',d.registration?'神位已登记，原主庙地址保留；不入编，不增设香火税。':'神位登记在玉京办理，须已有本人原主庙。','muted'));
    if(d.retire_reason)s.append(e('p',d.retire_reason,'muted'));
    s.append(e('p','奉建或恢复原庙主持即可转为地仙；在玉京按原资格接受四司任职可转为玄仙。入编前先交接主持，退隐不返工时、不重置期限。','yaochi-notice'));
    return s;
  }
  function relief(root,game,dispatch,buildingId){
    const r=game.yaochi?.relief;if(!r)return null;
    const s=section(root,'功德修缮','亲赴原址，修复本人受损的建筑与产业；产权、工料和原工程进度沿用现有规则。');
    {
      s.append(e('h4','功德私人修缮'),e('p',`可用功德 ${f(r.merit)} · 本期原服务承兑余款 ${f(r.budget.remaining)} 灵石。修缮与专修共用此额度。`,'muted'));
      if(!r.offers.length)s.append(e('p',r.reason||'亲赴本人受损城市、洞府、土地庙或产业，可查看原价修缮；工程材料仍由本人提供。','muted'));
      for(const row of r.offers.filter(row=>!buildingId||row.id===buildingId)){const c=card(s,row.name);c.append(e('p',`原工程 ${f(row.coins)} 灵石 · 功德 ${f(row.merit)} 承兑 ${f(row.subsidy)} · 本人补款 ${f(row.personal)}`),e('p',row.recipe.map(x=>`${x.name} ${f(x.held)} / ${f(x.needed)}`).join(' · ')||'无额外实物工程材料','muted'),button('按原报价重建','relief_rebuild',row.token,row.reason||r.reason,dispatch));if(row.reason)c.append(e('small',row.reason));}
    }
    return s;
  }
  function story(root,game,dispatch){
    const d=game.yaochi.purple_east;if(!d)return null;
    const r=d.state,w=r.work,blocked=d.reason;
    const s=section(root,'紫气东来','一处原仙府，一份共同案卷。三途从不同职责参与，最终去向由真实投入与公议决定。');
    s.dataset.purplePhase=r.phase||'unopened';
    const chapters=e('ol',null,'finale-chapters');
    const stages=['survey','dispute','hearing','implementation'];
    for(const [i,name] of ['紫气现世','利益分歧','瑶池定议','落地与后果'].entries()){
      const n=e('li');n.append(e('small',`第 ${i+1} 章`),e('strong',name));if(r.phase===stages[i])n.setAttribute('aria-current','step');if(r.phase==='complete'||stages.indexOf(r.phase)>i)n.classList.add('complete');chapters.append(n);
    }s.append(chapters);
    const b=(label,action,value='',why=blocked)=>button(label,'purple_'+action,d.token+'|'+value,why,dispatch);
    if(r.last_result)s.append(e('p',r.last_result,'yaochi-result'));
    if(blocked)s.append(e('p',blocked,'yaochi-notice'));
    if(!r.phase){const c=card(s,'瑶池西麓 · 紫宸古仙府');c.append(e('p','登记后，原聚落发展事务受扰二十年，原药田暂停新投产十年、在制延期十年。调查与处置由本人实际履约；维护照常，既有产权不变。'),e('p',d.deed?.cost?`瑶池机构须先实付 ${f(d.deed.cost)} 灵石购入原地块；不从个人账簿扣款。`:'使用本地既有原药田与原聚落。','muted'),b('登记异象并开始调查','start','',blocked||d.deed?.reason));return s;}
    s.append(e('h4',d.phase_name));
    if(w){const c=card(s,'本人正在履约');c.append(e('p',`实际工时 ${f(w.progress)} / ${f(w.years)} 年；事件中断后从原进度继续。`));const p=e('progress');p.max=w.years;p.value=w.progress;p.setAttribute('aria-label','主线实际工时');c.append(p,b(w.progress>=w.years?'提交本步成果':'继续实际履约',w.progress>=w.years?'submit':'work','',d.work_reason));
      const pause=e('details');pause.append(e('summary','暂停与备料'),e('p','暂停保留工时及已付工料，并解除协作者临时占用。恢复时重新检查人物在场与资格。','muted'),b('暂停本人工序','pause','',d.recovery_reason));c.append(pause);
      if(w.kind==='build'&&d.repair)c.append(e('p',`完工原价重建：${f(d.repair.coins)} 灵石${d.repair.reason?' · '+d.repair.reason:''}`,'muted'));
      return s;
    }
    if(r.paused_work){s.append(b('从原进度恢复','resume'));if(r.plan){const revise=e('details');revise.append(e('summary','同道失约或改变方案'),e('p','撤回原方案后可重新定议。已耗工料和本方案工时不返还，调查与护持成果保留。','muted'),b('放弃本方案并重新定议','replan'));s.append(revise);}return s;}
    if(r.phase==='dispute'){
      const grid=e('div',null,'gather-grid');s.append(grid);let c=card(grid,'实付疏导 · 5 年');c.append(e('p',`付 ${f(d.bill.coins)} 灵石及 ${d.bill.recipe.map(x=>`${x.name} ${x.needed} 份（持有 ${x.held}）`).join('、')}。提前解除本案的城市施工影响，其他水约不撤销。`),b('出资并疏导','mitigate','canal',blocked||d.bill.reason));
      c=card(grid,'轮值安置 · 15 年');c.append(e('p','投入更长的本人工时等待异象消退，原产业维护与合同期限照常。不征用其他人的物资。'),b('接受轮值安置','mitigate','wait'));
    }else if(r.phase==='hearing'){
      const p=d.proofs;s.append(e('p',`本案成果：地方护持 ${p.civic?'已完成':'未完成'} · 仙会获奖 ${p.fair?'已有':'未有'} · 原仙圃供货 ${p.garden?'已交付':'未交付'} · 公共修持议案 ${p.council?'已结项':'未结项'}`,'yaochi-notice'));
      if(!p.civic)s.append(b('参与公开护持 · 10 年','civic'));
      const grid=e('div',null,'gather-grid');s.append(grid);
      for(const row of d.plans){const c=card(grid,row.name);c.append(e('p',row.text),e('p',`定议质询 5 年；后续原址整理 ${row.years} 年，另付工料与原建筑重建价。`,'muted'));
        let target=row.id;const select=e('select');
        if(row.id==='shared'){select.setAttribute('aria-label','共同整理仙府的原同道');select.append(e('option','选择实际在场同道'));select.firstChild.value='';for(const n of d.candidates){const op=e('option',n.name);op.value=n.id;select.append(op);}c.append(select);}
        const choose=b('提交方案并听议','plan',target,blocked||row.reason||(!(p.fair||p.council||p.garden||p.civic)?'须先取得本案成果':''));
        if(row.id==='shared'){choose.disabled=true;select.onchange=()=>{choose.disabled=!!blocked||!select.value||!(p.fair||p.council||p.garden||p.civic);choose.onclick=()=>dispatch({action:'purple_plan',target_id:d.token+'|shared~'+select.value});};}
        c.append(choose);if(row.reason)c.append(e('small',row.reason));
      }
    }else if(r.phase==='implementation'){
      const c=card(s,d.plans.find(p=>p.id===r.plan)?.name||'按定议实施');c.append(e('p',`整理工料：${f(d.build_bill.coins)} 灵石，${d.build_bill.recipe.map(x=>`${x.name} ${x.needed} 份`).join('、')}；原建筑重建另需 ${f(d.repair?.coins)} 灵石。`),b('支付整理工料并开工','build','',blocked||d.build_bill.reason));const revise=e('details');revise.append(e('summary','调整方案'),e('p','重新定议须再付听议工时，原工时与费用不返还。','muted'),b('重新定议','replan'));s.append(revise);
    }else if(r.phase==='complete'){
      const c=card(s,'仙府已恢复，人生继续');c.append(e('p',d.plans.find(p=>p.id===r.plan)?.text),e('p',`原仙府记录已结清：世界历 ${f(r.completed)} 年。可在原地图建筑页使用仙府；真实产业、天庭职位与地方职责继续各自结算。`,'muted'));
    }
    return s;
  }
  window.WestwardFinale={identity,story,relief};
})();

/* Local projections; all travel, votes, money and outcomes are server-owned. */
(() => {
  const e=(...a)=>window.GameUi.element(...a),f=n=>Number(n||0).toLocaleString('zh-CN');
  const phase={survey:'拓碑调查',opening:'解开封禁',restoring:'原址整理',return:'返回瑶池归档',draft:'公示听议',rejected:'表决未通过',approved:'拨款待执行',executed:'待返回复核'};
  function shell(root,title,text){const s=e('section',null,'yaochi-gathering ventures');s.append(e('h3',title),e('p',text,'muted'));root.append(s);return s;}
  function card(root,title){const s=e('article',null,'gather-card');s.append(e('h4',title));root.append(s);return s;}
  function button(data,dispatch,blocked,label,action,value='',why=''){
    const b=e('button',label);b.type='button';b.dataset.ventureAction=action;b.dataset.ventureValue=value;
    b.disabled=!!(blocked||why);b.dataset.courtUnavailable=b.disabled?'1':'0';b.title=why||label;
    b.onclick=()=>dispatch({action,target_id:data.token+'|'+value});return b;
  }
  function progress(host,row){host.append(e('p',`实际工时 ${f(row.progress)} / ${f(row.years)} 年`));const p=e('progress');p.max=row.years;p.value=row.progress;p.setAttribute('aria-label','实际工时');host.append(p);}
  function antiquity(root,game,dispatch,blocked){
    const d=game.yaochi?.antiquity;if(!d||(!d.enabled&&!d.active))return null;
    const s=shell(root,'仙府访古','循原道路寻访三处旧府。拓碑、解禁、取舍，最后带着真实所得回瑶池归档。');
    const b=(label,a,v='',why=d.reason)=>button(d,dispatch,blocked,label,'antiquity_'+a,v,why);
    if(d.last_result)s.append(e('p',d.last_result,'bureau-notice'));
    if(d.reason)s.append(e('p',d.reason,'muted'));
    if(d.active){
      const r=d.active,site=d.sites.find(x=>x.id===r.key),c=card(s,site.name+' · '+phase[r.phase]);
      c.append(e('p',site.text),e('small',`原址：${site.place} · 工期按实际年份结算`));
      if(r.phase!=='return')progress(c,r);
      if(['survey','opening','restoring'].includes(r.phase)&&r.progress<r.years)c.append(b('继续原址办理','work','',d.work_reason));
      if(r.phase==='survey'&&r.progress>=r.years){
        c.append(e('p','独自解禁：8份四阶导灵矿材、2,000灵石；合作：4份阵材、2,000灵石，工时减半。合作取藏时本人得2份，另2份捐入本地公共市场。','muted'));
        c.append(e('p',`${d.opening.material_name}：持有 ${f(d.opening.held)} · 独研需8 / 合作需4`,'muted'));
        c.append(b(`独自研读 · ${site.years}年`,'open','study',d.work_reason||d.opening.reason));
        const select=e('select');select.setAttribute('aria-label','访古合作同道');
        d.candidates.forEach(n=>{const op=e('option',n.name);op.value=n.id;select.append(op);});c.append(select);
        const join=b('签约合作解禁','open','',d.work_reason||d.cooperative.reason||(!d.candidates.length?'须有在场、自由且境界不低于本人的同道':''));
        join.onclick=()=>dispatch({action:'antiquity_open',target_id:d.token+'|cooperate~'+select.value});c.append(join);
      }
      if(r.phase==='opening'&&r.progress>=r.years)c.append(e('p',site.choice),b('取藏 · '+site.reward,'choose','salvage',d.work_reason),b('保全静室 · 自费修复','choose','preserve',d.work_reason));
      if(r.phase==='restoring'&&r.progress>=r.years)c.append(e('p',`原营造报价：${f(d.repair?.coins)}灵石`),b('按原价修复仙府','rebuild','',d.work_reason||d.repair?.reason));
      if(r.phase==='return')c.append(e('p','请从原地图返回瑶池；归档后解锁后府线索。'),b('在瑶池归档','return','',d.recovery_reason||(game.player.location_id!==game.yaochi.location_id?'须亲临瑶池':'')));
      const exit=e('details');exit.append(e('summary','合作交接与退出'));
      if(r.companion)exit.append(b('解除合作并重选解禁方案','release','',d.recovery_reason));
      if(r.phase!=='return')exit.append(b('放弃此府 · 不返工料','abandon','',d.recovery_reason));c.append(exit);
    }
    const grid=e('div',null,'gather-grid');s.append(grid);
    d.sites.forEach((r,i)=>{const c=card(grid,`${['壹','贰','叁'][i]} · ${r.name}`);c.append(e('p',r.text),e('small',`${r.place} · ${['真仙','金仙','太乙','大罗'][r.realm-9]}起`),e('p',`取藏：${r.reward} ×4，或保全原址洞府。`));
      const why=d.reason||(d.active?'请先完成当前行程':r.record?'此府已有一次性记录':!r.local?'须亲临原址':game.player.realm_index<r.realm?'境界不足':i&&!d.sites[i-1].record?.returned?'须先完成前府归档':'');
      c.append(r.record?e('p',r.record.returned?'已归档 · 所得不重复发放':r.record.result||'调查记录保留','muted'):b('在原址登记调查','start',r.id,why));if(why&&!r.record)c.append(e('small',why,'muted'));
    });return s;
  }
  function council(root,d,dispatch){
    if(!d||(!d.enabled&&!d.current))return null;
    const s=shell(root,'七曜项目议政','在任七曜过半表决。每份方案绑定真实对象、工期和原府库预算，结项公开实物与收支回执。');
    const b=(label,a,v='',why=d.reason)=>button(d,dispatch,false,label,'council_'+a,v,why);
    s.append(e('p',`原府库 ${f(d.treasury)} 灵石 · 当前在任 ${d.holders.length} 席`,'venture-kicker'));
    if(d.authority)s.append(e('p',d.authority,'bureau-notice'));if(d.last_result)s.append(e('p',d.last_result,'muted'));
    const r=d.current;
    if(r){const c=card(s,r.offer.name+' · '+phase[r.status]);c.append(e('p',r.offer.benefit),e('p',`预算 ${f(r.offer.budget)} 灵石 · 截止世界历 ${f(r.deadline)}年`));
      if(d.work){progress(c,d.work);if(d.work.progress<d.work.years)c.append(b('继续实际办理','work','',d.work_reason));
        else {if(d.work.stage==='prepare')c.append(e('p',`表决时采购预算：${f(d.vote_offer?.budget)}灵石；按当前原市场报价实购。`));c.append(b(d.work.stage==='prepare'?'提交七曜表决':'提交本步成果',d.work.stage==='prepare'?'vote':'finish',d.work.stage==='prepare'?d.vote_offer?.token||'':'',d.work.stage==='prepare'?d.authority||d.vote_offer?.reason||(!d.vote_offer?'原目标已经失效':''):d.work_reason));}}
      if(r.status==='draft'){const details=e('details');details.append(e('summary','协商本案承诺 · 至多两席'),e('p','每次200灵石；承诺250年内完成并公开账目，逾期违约扣5支持。真实星君须当面接触，机构席位仅收文书。'));
        d.holders.filter(h=>h.holder!=='player').forEach(h=>details.append(b(h.name+(r.pledges[h.holder]?' · 已承诺':' · 会商'),'contact',h.holder,d.authority||(r.pledges[h.holder]||Object.keys(r.pledges).length>=2?'本案承诺已登记或已达上限':''))));c.append(details);}
      if(r.status==='approved'&&!d.work){c.append(e('p','请携原公物沿地图到交付现场。地仙协议须先公开原庙并完成一次新庙务。','muted'));if(r.offer.policy==='service')c.append(b('由庙主开放原庙使用','public'));c.append(b('开始现场执行','execute','',d.execute_reason));if(d.execute_reason)c.append(e('small',d.execute_reason,'muted'));}
      if(r.status==='executed'&&!d.work)c.append(b('在原提案地开始五年复核','review','',d.review_reason));
      if(r.attempts.length){const v=r.attempts.at(-1);c.append(e('p',`最近表决：赞成 ${v.yes} · 反对 ${v.no} · 在任 ${v.total}席`));}
      const exit=e('details');exit.append(e('summary','结清与撤案'),e('p','返回原提案地交接余货、退回未耗公款；已耗费用不退。'),b('交接撤案','cancel','',d.recovery_reason));c.append(exit);
    }
    if(!r||r.status==='rejected'){
      const grid=e('div',null,'gather-grid');s.append(grid);
      for(const [key,title] of Object.entries({training:'公共修持预算',repair:'地方修缮优先序',procurement:'公开采购规则',service:'地仙神位与服务协议'})){
        if(r&&r.offer.policy!==key)continue;
        const c=card(grid,title),rows=d.offers.filter(o=>o.policy===key);if(!rows.length){c.append(e('p','此地暂无符合条件的实际对象。前往有原人物、公共遗址、相邻缺货市场或自有土地庙的地点查看。','muted'));continue;}
        const select=e('select');select.setAttribute('aria-label',title+'目标');rows.forEach((o,i)=>{const op=e('option',o.name);op.value=i;select.append(op);});
        const desc=e('p'),price=e('p'),why=e('small',null,'muted'),submit=b(r?'修改并重新听议':'登记提案',r?'revise':'propose');
        const update=()=>{const o=rows[Number(select.value)];desc.textContent=o.benefit+' · 交付地：'+o.place;price.textContent=`预算 ${f(o.budget)}灵石 · 现场${o.years}年 + 复核5年`;why.textContent=d.authority||o.reason||(o.used&&!r?'本期已提案':'');submit.disabled=!!why.textContent;submit.dataset.courtUnavailable=submit.disabled?'1':'0';submit.onclick=()=>dispatch({action:r?'council_revise':'council_propose',target_id:d.token+'|'+o.token});};
        select.onchange=update;c.append(select,desc,price,why,submit);update();
      }
    }
    const history=e('details');history.append(e('summary','已归档项目与收支'));
    d.history.slice().reverse().forEach(r=>{const c=card(history,r.offer.name);c.append(e('p',r.status==='closed'?'履约复核完成':r.broken_promise?'逾期违约，支持度已扣除':'已交接撤案'));if(r.receipt)c.append(e('small',`采购 ${f(r.receipt.purchase)} · 劳务 ${f(r.receipt.labor)} · 工程 ${f(r.receipt.engineering)} · 退回 ${f(r.receipt.refunded)}`));});s.append(history);return s;
  }
  window.WestwardVentures={antiquity,council};
})();

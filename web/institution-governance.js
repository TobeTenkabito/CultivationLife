/* Shared base-game controls, embedded in original institution/building panels. */
(() => {
  const el=(...a)=>window.GameUi.element(...a),money=n=>Number(n||0).toLocaleString('zh-CN');
  function render(host,rows,dispatch,dlc=false){
    if(!rows?.length)return null;
    const root=el('section',null,'institution-governance');
    for(const r of rows){
      const box=el('details',null,'institution-sheet');box.dataset.institutionScope=r.id;
      const heading=el('summary');heading.append(el('strong',r.name),el('span',r.job?(r.job.blocked?'待请示':'履约中'):'经营安排','institution-badge'));box.append(heading);
      box.append(el('p',`可安排原款 ${money(r.available)} · 基本准备金 ${money(r.reserve)}`,'muted'));
      const send=(action,data={})=>dispatch({action,scope:r.id,token:r.token,...data});
      const button=(label,action,data={},disabled=false)=>{const b=el('button',label);b.type='button';b.dataset.institutionAction=action;b.disabled=!r.can_act||disabled;b.dataset.institutionUnavailable=b.disabled?'1':'0';if(dlc)b.dataset.dlc=typeof dlc==='string'?dlc:'yaochi-westward';b.onclick=()=>send(action,typeof data==='function'?data():data);return b;};
      if(r.job){
        const j=r.job,progress=el('progress');progress.max=j.years;progress.value=j.progress;
        box.append(el('h4',j.offer.name),progress,el('p',`实际工时 ${j.progress}/${j.years} 年 · 支出 ${money(j.spent)} / 托管 ${money(j.funded)}`),el('p',j.blocked||'原执行人按本地实际年份履约；离场或失去资格会暂停。','muted'));
        const extra=el('input');extra.type='number';extra.min='1';extra.max=String(r.available);extra.value='1000';extra.setAttribute('aria-label','追加项目原款');
        const actions=el('div',null,'institution-actions');actions.append(extra,button('追加授权','institution_fund',()=>({amount:Number(extra.value)})),button('交接项目','institution_cancel'));box.append(actions);
      }else{
        const controls=el('div',null,'institution-controls'),policy=el('select'),person=el('select'),limit=el('input'),automatic=el('input');
        for(const [id,name] of Object.entries({balanced:'均衡经营',supply:'补足供给',repair:'修缮优先',teaching:'传习优先'})){const o=el('option',name);o.value=id;policy.append(o);}policy.value=r.policy;policy.setAttribute('aria-label','机构经营方针');
        person.append(el('option','不驻任'));person.firstChild.value='';for(const n of r.people){const o=el('option',n.name);o.value=n.id;person.append(o);}person.value=r.delegate||'';person.setAttribute('aria-label','驻任执行人');
        limit.type='number';limit.min='0';limit.max='1000000000000000';limit.value=r.limit;limit.setAttribute('aria-label','单项代办预算');automatic.type='checkbox';automatic.checked=r.automatic;
        const label=el('label');label.append(automatic,document.createTextNode('预算内自动办理'));
        const field=(name,input)=>{const l=el('label',name,'institution-field');l.append(input);return l;};
        controls.append(field('经营方针',policy),field('驻任执行人',person),field('单项预算',limit),label,button('保存经营安排','institution_configure',()=>({policy:policy.value,person:person.value,limit:Number(limit.value),automatic:automatic.checked})));box.append(controls);
        for(const offer of r.offers){
          const card=el('article',null,'institution-offer');card.append(el('strong',offer.name),el('p',`预算 ${money(offer.budget)} · 工时 ${offer.years} 年`),el('small',offer.reason||'按当前实货报价预留原款；最终交付重新核验。','muted'));
          card.append(button('安排执行','institution_start',()=>({offer:offer.key,person:person.value||r.people[0]?.id}),!!offer.reason||!r.people.length));box.append(card);
        }
        if(!r.offers.length)box.append(el('p','当前没有需要办理的有效事项。','muted'));
      }
      if(r.proposals.length){const proposals=el('div',null,'institution-proposals');proposals.append(el('h4','原人员提议'));for(const p of r.proposals)proposals.append(el('p',`${p.name} · 观察于 ${p.observed} 年 · 预算 ${money(p.budget)}${p.supporters?.length?` · ${p.supporters.length}位原人员联署`:``}`));box.append(proposals);}
      const history=el('details');history.append(el('summary','履约与交接记录'));for(const j of [...r.history].reverse())history.append(el('p',`${j.offer.name}：${j.result}（支出 ${money(j.spent)}，退回 ${money(j.refunded)}）`));box.append(history);root.append(box);
    }
    host.append(root);return root;
  }
  window.InstitutionGovernance={render};
})();

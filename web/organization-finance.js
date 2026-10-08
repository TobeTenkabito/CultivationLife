(() => {
  const num = n => Number(n || 0).toLocaleString('zh-CN', {maximumFractionDigits: 1});
  window.renderOrganizationFinance = (root, data) => {
    if (!data) return;
    const section = document.createElement('details');
    section.className = 'doctrine-entry organization-finance';
    const title = document.createElement('summary');
    title.textContent = `财政账目 · 府库 ${num(data.balance)} 灵石`;
    section.append(title);
    const metrics = document.createElement('div');
    metrics.className = 'family-metrics';
    for (const [label, value] of [['最近结算收入', data.income], ['已付开支', data.expense], ['供养缺口', data.shortfall], ['福利应付', data.benefit_due], ['福利实付', data.benefit_paid]]) {
      const row = document.createElement('span'), name = document.createElement('small'), amount = document.createElement('b');
      name.textContent = label; amount.textContent = num(value); row.append(name, amount); metrics.append(row);
    }
    section.append(metrics);
    const note = document.createElement('p');
    note.className = 'muted';
    note.textContent = `按实际年数结算，府库不足时减少支付。${data.product ? `驻地产出：${data.product}，最近售出 ${num(data.produced)} 件。` : ''}`;
    section.append(note); root.append(section);
    if (data.industry_level !== undefined) {
      const industry = document.createElement('p');
      industry.textContent = `产业扩建 ${data.industry_level} / 10 级 · 门内聚合产能 ${num(data.labor_capacity)} / 年 · 基础供养 ${num(data.expected_upkeep)} / 年`;
      section.append(industry);
    }
  };
  window.renderOrganizationBusiness = (root, kind, organization, game, act) => {
    const depot=organization?.depot;
    if(!depot)return;
    const box=document.createElement('details');box.className='organization-business enterprise-panel';box.dataset.organization=kind;
    const title=document.createElement('summary');title.textContent='组织经营 · 府库、商队与产权';box.append(title);
    const note=document.createElement('p');note.textContent=depot.local?'在驻地办理，资金直接计入本组织府库。':'请前往组织驻地办理注资与商队申请；产权业务仍须身在产权所在地。';box.append(note);
    const controls=document.createElement('div');controls.className='estate-controls';
    const label=document.createElement('label');label.textContent='府库注资金额';const amount=document.createElement('input');amount.type='number';amount.min='1';amount.max='1000000000000';amount.value='10000';amount.setAttribute('aria-label','府库注资金额');label.append(amount);controls.append(label);
    const can=game.fleet_network?.can_act;
    const button=(text,action,payload,disabled=false)=>{const b=document.createElement('button');b.type='button';b.textContent=text;b.dataset.orgBusiness=action;b.dataset.unavailable=!can||disabled?'1':'0';b.disabled=b.dataset.unavailable==='1';b.onclick=()=>act({action,owner_kind:kind,...payload()});controls.append(b);};
    button('向府库注资','organization_fund',()=>({amount:Number(amount.value)}),!depot.local);
    button('申请组建商队','create',()=>({}),!depot.local);box.append(controls);
    for(const f of game.fleet_network?.fleets||[]){if(f.owner_kind!==kind||f.owner_id!==depot.owner_id)continue;const p=document.createElement('p');p.textContent=`${f.name} · ${f.location} · ${f.status==='travelling'?'运输中':f.status==='retired'?'已解散':'驻留'} · 护卫战力 ${num(f.guard_power)}`;box.append(p);}
    if(game.fleet_network)window.TradeOrdersPanel?.render(box,{...game.fleet_network,scope:kind,fleets:game.fleet_network.fleets.filter(f=>f.owner_kind===kind&&f.owner_id===depot.owner_id)},act);
    const data=game.map?.economy?.enterprises;
    if(data)window.EnterprisePanel?.render(box,{...data,scope:kind,owned:data.owned.filter(r=>r.owner_kind===kind)},act);
    root.append(box);
  };
})();

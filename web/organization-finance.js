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
    for (const [label, value] of [['年度收入', data.annual_income], ['年度支出', data.annual_expense], ['本期成交额', data.turnover], ['本期经营收入', data.income], ['本期已付开支', data.expense], ['经营养护实付', data.operating_paid], ['供养缺口', data.shortfall], ['福利应付', data.benefit_due], ['福利实付', data.benefit_paid], ['盈余分红', data.dividend_paid]]) {
      const row = document.createElement('span'), name = document.createElement('small'), amount = document.createElement('b');
      name.textContent = label; amount.textContent = value == null ? '待年度结算' : num(value); row.append(name, amount); metrics.append(row);
    }
    section.append(metrics);
    const note = document.createElement('p');
    note.className = 'muted';
    note.textContent = `按实际年数结算。优先基本养护，经营有盈余时再用于阵法、设施与事务劳务，并保留三年基本养护储备；资金不足时收缩额外开支。物资保障 ${Math.round((data.supply_coverage??1)*100)}%，累计实际消费 ${num(data.supplies_consumed)} 件。${data.product ? `驻地产出：${data.product}，最近售出 ${num(data.produced)} 件。` : ''}`;
    section.append(note); root.append(section);
    const period = document.createElement('p'); period.className='muted';
    period.textContent = `最近结算至第 ${data.last_year} 年，覆盖 ${data.settlement_years || '尚未记录'} 年；年度值为本期收支除以实际年数。成交额合计真实采购与销售，不含注资、分红或内部调拨；经营收入扣除生产工料，含实收税费、上供及商队利润分红，另列开支不重复扣工料。`;
    section.append(period);
    if(data.pending_income||data.pending_expense||data.pending_turnover){const pending=document.createElement('p');pending.textContent=`尚待下一次年度结算：经营收入 ${num(data.pending_income)} / 支出 ${num(data.pending_expense)} / 成交额 ${num(data.pending_turnover)}；均已实际交割，不混入上一期年度值。`;section.append(pending);}
    if (data.industry_level !== undefined) {
      const industry = document.createElement('p');
      industry.textContent = `产业扩建 ${data.industry_level} / 10 级 · 门内年产能力参考值 ${num(data.labor_capacity)} · 基础供养 ${num(data.expected_upkeep)} 灵石 / 年`;
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
    for(const f of game.fleet_network?.fleets||[]){
      if(f.owner_kind!==kind||f.owner_id!==depot.owner_id)continue;
      const row=document.createElement('section');row.className='merchant-order';row.dataset.fleetId=f.id;
      const p=document.createElement('p');p.textContent=`${f.name} · ${f.location} · ${f.status==='travelling'?'运输中':f.status==='retired'?'已解散':'驻留'} · 护卫战力 ${num(f.guard_power)} / ${num(f.guard_required)}`;row.append(p);
      if(f.can_order){
        const b=document.createElement('button');b.type='button';b.textContent=`委派护卫 · ${num(game.fleet_network.guard_cost)} 灵石（本人支付）`;b.dataset.orgBusiness='guard';
        b.disabled=!can||!f.can_guard||f.guard_power>=f.guard_required;
        b.dataset.unavailable=b.disabled?'1':'0';b.onclick=()=>act({action:'guard',fleet_id:f.id});row.append(b);
      }
      box.append(row);
    }
    if(game.fleet_network)window.TradeOrdersPanel?.render(box,{...game.fleet_network,scope:kind,fleets:game.fleet_network.fleets.filter(f=>f.owner_kind===kind&&f.owner_id===depot.owner_id)},act);
    const data=game.map?.economy?.enterprises;
    if(data)window.EnterprisePanel?.render(box,{...data,scope:kind,owned:data.owned.filter(r=>r.owner_kind===kind)},act);
    root.append(box);
  };
})();

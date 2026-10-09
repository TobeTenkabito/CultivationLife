/* Fixed-site deeds, production and storage in the existing atlas. */
(() => {
  const e=(tag,text)=>{const n=document.createElement(tag);n.textContent=text??'';return n;};
  const money=n=>Number(n||0).toLocaleString('zh-CN');
  function render(root,data,act) {
    if(!data?.available)return;
    const box=e('details');box.id=data.scope?'enterprise-panel-'+data.scope:'enterprise-panel';box.className='enterprise-panel';box.append(e('summary','本地产权与生产经营'));
    box.append(e('p','产业固定在本地图，周转金独立结算。原料实际入库后投产，成品在完工年入库；异地调货须由商队运输。'));
    const select=(parent,label,options,value)=>{const l=e('label',label),s=e('select');s.setAttribute('aria-label',label);for(const [v,t] of options){const o=e('option',t);o.value=v;s.append(o);}if(value!=null)s.value=value;l.append(s);parent.append(l);return s;};
    const input=(parent,label,value)=>{const l=e('label',label),n=e('input');n.type='number';n.min='0';n.step='1';n.value=value;n.setAttribute('aria-label',label);l.append(n);parent.append(l);return n;};
    const button=(parent,label,action,payload,disabled=false)=>{const b=e('button',label);b.type='button';b.dataset.estateAction=action;b.dataset.unavailable=!data.can_act||disabled?'1':'0';b.disabled=b.dataset.unavailable==='1';b.onclick=()=>act({action:'estate_'+action,...(typeof payload==='function'?payload():payload)});parent.append(b);return b;};
    const owners=[['player','本人'],['family','家族'],['sect','宗门'],['alliance','自建商盟']].filter(o=>!data.scope||o[0]===data.scope);
    const buy=e('section');buy.className='estate-controls';
    const owner=select(buy,'产权登记方',owners),kind=select(buy,'购置产业',data.offers.filter(o=>!o.occupied).map(o=>[o.kind,`${o.name} · ${money(o.cost)} 灵石`]));
    button(buy,'购置产权','buy',()=>({owner_kind:owner.value,kind:kind.value,cost:data.offers.find(o=>o.kind===kind.value)?.cost}),!kind.options.length);box.append(buy);
    for(const row of data.owned){
      const card=e('details');card.dataset.estateId=row.id;card.append(e('summary',`${row.name} · ${row.level} 级 · ${owners.find(x=>x[0]===row.owner_kind)?.[1]}`));
      card.append(e('p',`周转金 ${money(row.cash)} · 经营收入 ${money(row.income)} / 支出 ${money(row.expense)} · 欠费 ${money(row.arrears)}`),e('p',`仓储及在制占用 ${row.used} / ${row.capacity} 件 · 累计生产 ${row.produced} 件${row.kind==='mine'?` · 剩余矿藏 ${row.reserve} 件`:''}`));
      if(row.resources?.length)card.append(e('p',`本地资源：${row.resources.join('、')}；扩建提高容量，不改变天然品阶。${row.kind==='hunt'?` 剩余丹源 ${row.reserve} 件。`:''}`));
      if(row.job)card.append(e('p',`在制 ${row.job.quantity} 件 · 第 ${row.job.finish} 年完工（已扣原料与劳务）`));
      const base={estate_id:row.id,revision:row.revision},operation=(parent,label,action,payload={},disabled=false)=>button(parent,label,action,()=>({...base,...(typeof payload==='function'?payload():payload)}),disabled);
      operation(card,row.entrusted?'收回掌柜委托':'委托驻地掌柜经营','entrust',{enabled:!row.entrusted});
      if(row.entrusted)card.append(e('p','掌柜按当地需求安排采购、生产与销售，保留组织供养预算；资金或利润不足时暂停投产。'));
      const funds=e('div');funds.className='estate-controls';
      if(row.owner_kind==='player'){
        const amount=input(funds,'产业资金金额',10000);
        operation(funds,'注入周转金','fund',()=>({amount:Number(amount.value)}));operation(funds,'提取周转金','withdraw_cash',()=>({amount:Number(amount.value)}),!!row.arrears);
      }
      operation(funds,'结清欠费','pay_arrears',{},!row.arrears);operation(funds,`扩建 · ${money(row.upgrade_cost)}`,'upgrade',{cost:row.upgrade_cost},row.level>=5);card.append(funds);
      const production=e('div');production.className='estate-controls';
      const recipes=row.kind==='shop'?data.goods.filter(g=>g.can_buy).map(g=>[g.id,g.name]):data.recipes.filter(r=>r.kind===row.kind&&r.can_use&&r.estates.includes(row.id)).map(r=>[r.id,`${r.name}：${r.input_names} → ${r.output_name} ×${r.quantity} / ${r.years} 年`]);
      const recipe=select(production,row.kind==='shop'?'经营商品':'生产配方',recipes,row.recipe),batches=input(production,'每批生产份数',row.batches);
      batches.min='1';batches.max=String(row.level*4);
      const buyLimit=input(production,'最高采购均价',row.buy_limit),sellLimit=input(production,'最低销售均价',row.sell_limit);
      const quota=input(production,'每次结算自动出货上限',row.sale_quota);quota.max='1000000';
      const reserve=input(production,'自动经营保留灵石',row.reserve_cash),budget=input(production,'单次自动投产支出上限',row.expense_limit);
      card.append(e('p',`当前养护约 ${money(row.annual_maintenance)} 灵石 / 年；自动经营保留 ${money(row.operating_reserve)} 灵石。欠费暂停进货与投产，可销售库存清偿。`));
      const checks={};for(const [key,title] of [['enabled','持续经营'],['auto_buy','自动补足原料／进货'],['auto_sell','自动销售所选成品']]){const label=e('label',title),check=e('input');check.type='checkbox';check.checked=row[key];check.setAttribute('aria-label',title);label.append(check);production.append(label);checks[key]=check;}
      operation(production,'保存经营方案','configure',()=>({recipe:recipe.value,batches:Number(batches.value),buy_limit:Number(buyLimit.value),sell_limit:Number(sellLimit.value),sale_quota:Number(quota.value),reserve_cash:Number(reserve.value),expense_limit:Number(budget.value),...Object.fromEntries(Object.entries(checks).map(([k,v])=>[k,v.checked]))}),!recipes.length);
      if(row.kind!=='shop')operation(production,'开始一批生产','start',{},!!row.job||!!row.arrears||!row.recipe);card.append(production);
      const storage=e('details');storage.append(e('summary','仓储与交易'),e('p',row.stock.map(s=>`${s.name} ×${s.quantity}`).join('、')||'仓库暂无库存'));
      const controls=e('div');controls.className='estate-controls';const goods=select(controls,'仓储商品',data.goods.map(g=>[g.id,`${g.name} · 市场 ${g.stock} / 背包 ${g.held}`]));
      const qty=select(controls,'仓储数量',[['1','1 件'],['10','10 件'],['100','100 件']]);
      const stockPayload=()=>({item:goods.value,quantity:Number(qty.value)});
      operation(controls,'背包存入','deposit',stockPayload);operation(controls,'提取到背包','withdraw',stockPayload);
      const bill=e('p');const update=()=>{const q=data.goods.find(g=>g.id===goods.value)?.quotes[qty.value];bill.textContent=q?`采购含费 ${money(q.buy.total)} / 售出实得 ${money(q.sell.total)} 灵石`:'';};goods.onchange=update;qty.onchange=update;update();controls.append(bill);
      for(const [id,label,side] of [['purchase','从本地市场采购','buy'],['sell','向本地市场销售','sell']])operation(controls,label,id,()=>({...stockPayload(),market_revision:data.market_revision,total:data.goods.find(g=>g.id===goods.value)?.quotes[qty.value][side].total}));
      const target=select(controls,'本地调拨目标',data.owned.filter(r=>r.id!==row.id&&r.owner_kind===row.owner_kind).map(r=>[r.id,r.name]));
      operation(controls,'同地仓库调拨','move_stock',()=>({...stockPayload(),target_estate:target.value}),!target.options.length);storage.append(controls);card.append(storage);
      const deed=e('details');deed.append(e('summary','产权交接'));const to=select(deed,'受让产权方',owners.filter(o=>o[0]!==row.owner_kind));
      deed.append(e('p','交接前须清空库存、完成生产、结清欠费并撤销关联订单。矿藏储量不会因换主或重新购置恢复。'));
      operation(deed,`有偿转让 · ${money(row.release_price)}`,'transfer',()=>({owner_kind:to.value,cost:row.release_price}));operation(deed,`交回产权 · ${money(row.release_price)}`,'release',{cost:row.release_price});card.append(deed);
      const history=e('details');history.append(e('summary','近期生产记录'));for(const [year,text] of row.history)history.append(e('p',`第 ${year} 年 · ${text}`));card.append(history);box.append(card);
    }
    root.append(box);
  }
  window.EnterprisePanel={render,setBusy:busy=>document.querySelectorAll('[data-estate-action]').forEach(b=>b.disabled=busy||b.dataset.unavailable==='1')};
})();

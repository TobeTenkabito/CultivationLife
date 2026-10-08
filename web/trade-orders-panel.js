(() => {
  const e=(tag,text)=>{const n=document.createElement(tag);n.textContent=text??'';return n;};
  function render(root,system,act){
    const group=e('details');group.id=system.scope?'trade-orders-panel-'+system.scope:'trade-orders-panel';group.append(e('summary','指定商路与长期订单'),e('p','订单按真实库存和当时价格执行。长期同界订单售罄后付费空返，再次采购；跨界订单逐段交税往返。产业调货只装载源仓库存，满仓时余货留在商队。'));
    const fleets=system.fleets.filter(f=>f.can_order);
    if(!fleets.length)group.append(e('p','请前往本人领办商队驻地，或自建商盟的本界总部下达订单。'));
    for(const f of fleets){
      const card=e('details');card.dataset.orderFleet=f.id;card.append(e('summary',f.name));const order=f.trade_order||{};
      card.append(e('p',`当前：${{auto:'自动择货',hold:'暂停派新货',once:'单次订单',repeat:'长期订单'}[order.mode]} · ${f.last_result||f.status}`));
      const controls=e('div');controls.className='estate-controls';
      const select=(label,options,value)=>{const l=e('label',label),s=e('select');s.setAttribute('aria-label',label);for(const [v,t] of options){const o=e('option',t);o.value=v;s.append(o);}if(value!=null&&options.some(o=>o[0]===value))s.value=value;l.append(s);controls.append(l);return s;};
      const input=(label,value)=>{const l=e('label',label),n=e('input');n.type='number';n.min='0';n.step='1';n.value=String(value);n.setAttribute('aria-label',label);l.append(n);controls.append(l);return n;};
      const mode=select('订单执行方式',[['once','执行一次'],['repeat','长期往返'],['hold','暂停派货'],['auto','自动择货']],order.mode);
      const kind=select('商路类型',[['local','同界市场贸易'],['cross','跨界市场贸易'],['delivery','同界产业调货']],order.kind);
      const dest=select('商路目的地',[],null);function destinations(){const rows=kind.value==='cross'?(system.destinations||[]).filter(d=>d.open).map(d=>[d.world,d.name]):system.order_sites.filter(d=>d.id!==f.location_id).map(d=>[d.id,d.name]);dest.replaceChildren();for(const [v,t]of rows){const o=e('option',t);o.value=v;dest.append(o);}if(rows.some(r=>r[0]===order.destination))dest.value=order.destination;}kind.onchange=destinations;destinations();
      const item=select('订单商品',system.order_goods.map(g=>[g.id,g.name]),order.item),qty=input('订单数量',order.quantity||1);qty.min='1';qty.max=String(f.capacity);
      const high=input('最高买入均价',order.buy_limit??1000000),low=input('最低卖出均价',order.sell_limit??0);
      const back=select('返程指定商品',[['','自动择货'],...system.order_goods.map(g=>[g.id,g.name])],order.return_item);
      const source=select('调货源产业',system.order_estates.filter(r=>r.world===system.world&&r.location===f.location_id).map(r=>[r.id,r.name]),order.source_estate);
      const target=select('调货目标产业',system.order_estates.filter(r=>r.world===system.world&&r.location!==f.location_id).map(r=>[r.id,r.name]),order.target_estate);
      const button=(label,action,payload,disabled=false)=>{const b=e('button',label);b.type='button';b.dataset.fleetAction=action;b.dataset.merchantUnavailable=!system.can_act||disabled?'1':'0';b.disabled=b.dataset.merchantUnavailable==='1';b.onclick=()=>act({action,fleet_id:f.id,...payload()});controls.append(b);};
      button('保存商路订单','order_configure',()=>({mode:mode.value,kind:kind.value,destination:dest.value,item:item.value,quantity:Number(qty.value),buy_limit:Number(high.value),sell_limit:Number(low.value),return_item:back.value||null,source_estate:source.value,target_estate:target.value}));
      button('执行已存订单','order_dispatch',()=>({}),f.status!=='waiting'||!!f.cross_trip||!['once','repeat'].includes(order.mode));
      button('调整在途最低售价','order_limits',()=>({sell_limit:Number(low.value)}),!f.cargo&&!f.cross_trip);
      card.append(controls);group.append(card);
    }
    root.append(group);
  }
  window.TradeOrdersPanel={render};
})();

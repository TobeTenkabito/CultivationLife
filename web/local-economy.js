/* Local trade lives in the atlas. Rendering and navigation never submit actions. */
(() => {
  let search = '', selectedQuantity = '1', address = null;
  const el = (tag, text, cls='') => {
    const node = document.createElement(tag); node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  };
  const money = value => Number(value).toLocaleString('zh-CN', {maximumFractionDigits: 2});
  const setBusy = busy => document.querySelectorAll('#map-economy button[data-trade]').forEach(button => {
    button.disabled = busy || button.dataset.unavailable === '1';
  });
  function render(market, game, submit) {
    const root = document.querySelector('#map-economy'); root.replaceChildren();
    if (!market?.available) return;
    if (address !== market.market_id) { address = market.market_id; search = ''; }
    const head = el('div', null, 'economy-heading');
    head.append(el('h3', `${market.name} · 本地市场`), el('span', `世界历 ${market.year} 年`));
    const intro = el('p', '当地作坊供货、居民消费形成库存。大笔买卖会改变成交均价，坊市货架另为你保留精选商品。', 'muted');
    const metrics = el('div', null, 'economy-metrics');
    for (const [label, value] of [['累计成交',market.turnover],['收购资金',market.liquidity],['运营府库',market.operator_balance]]) {
      const cell = el('div'); cell.append(el('small',label), el('strong',money(value))); metrics.append(cell);
    }
    const macro = el('details', null, 'economy-world');
    macro.append(el('summary',`${market.world_name}经济 · 开局规模的 ${money(market.scale)} 倍`),
      el('p',`界面经济随岁月发展，接近 ${money(market.growth_cap)} 倍时逐渐放缓。物价水平 ${money(market.price_level)} 倍；黑市收入归本界府库，当前 ${money(market.world_treasury)} 灵石。`));
    const freight = el('details', null, 'economy-freight');
    freight.append(el('summary', `商队流通 · 累计到货 ${money(market.freight_in || 0)} / 发货 ${money(market.freight_out || 0)} 件`));
    (market.caravans || []).forEach(fleet => freight.append(el('p',
      `${fleet.name} · ${{waiting:'候货',travelling:'在途',selling:'待售',stranded:'受阻',retired:'已解散'}[fleet.status]} · ${fleet.destination ? `${fleet.origin} → ${fleet.destination}，预计第 ${fleet.arrival} 年抵达` : fleet.location}`)));
    if (!market.caravans?.length) freight.append(el('p', '当前没有涉及本地的商队运输。'));
    const tools = el('div',null,'economy-tools');
    const input = el('input'); input.type='search'; input.placeholder='查找商品'; input.setAttribute('aria-label','查找本地商品'); input.value=search;
    const quantity = el('select'); quantity.setAttribute('aria-label','本地市场交易数量');
    for (const value of ['1','10','100']) { const option=el('option',`每笔 ${value} 件`); option.value=value; quantity.append(option); }
    quantity.value=selectedQuantity; tools.append(input,quantity);
    const note = el('p',`交易手续费 ${Math.round(market.fee_rate*100)}%；买入显示含费总额，卖出显示扣费实得。收购价低于售价。`, 'muted');
    const list = el('div',null,'economy-goods');
    function draw() {
      list.replaceChildren();
      const wallet = game.market?.spirit_stones || 0, count=Number(selectedQuantity);
      const rows=market.rows.filter(row=>row.name.includes(search));
      rows.forEach(row=>{
        const card=el('article',null,'economy-good'); card.dataset.itemId=row.id;
        const title=el('div',null,'economy-heading'); title.append(el('b',row.name),el('span',`${row.trend} ${row.status}`));
        card.append(title,el('p',`现货 ${money(row.stock)} · 持有 ${money(row.held)} · 累计成交 ${money(row.volume)}`),
          el('small',`近期年均产出 ${money(row.production)} / 消费 ${money(row.consumption)}`, 'muted'));
        const actions=el('div',null,'economy-actions');
        for (const side of ['buy','sell']) {
          const bill=row.quotes[selectedQuantity][side];
          const button=el('button',`${side==='buy'?'买入':'卖出'} ${count} · ${money(bill.total)} 灵石`);
          button.type='button';button.dataset.trade=side;
          button.dataset.unavailable=String(!market.can_trade || (side==='buy' ? !row.can_buy || row.stock<count || wallet<bill.total : row.held<count || market.liquidity<bill.gross) ? 1 : 0);
          button.title=`手续费 ${money(bill.fee)} 灵石`;
          button.onclick=()=>submit({market_id:market.market_id,revision:market.revision,item_id:row.id,side,quantity:count,total:bill.total});
          actions.append(button);
        }
        card.append(actions);list.append(card);
      });
      if (!rows.length) list.append(el('p','没有符合条件的商品。','muted'));
      setBusy(document.body.classList.contains('busy'));
    }
    input.oninput=()=>{search=input.value;draw();};
    quantity.onchange=()=>{selectedQuantity=quantity.value;draw();};
    root.append(head,intro,metrics,freight,tools,note,list);draw();
  }
  window.LocalEconomy={render,setBusy};
})();

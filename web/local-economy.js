/* A single local market view moves between the atlas and market; no extra settlement. */
(() => {
  let search = '', regexMode = false, selectedQuantity = '1', address = null;
  let context = null, dirty = true, content = null, marketView = 'shelves';
  let worker = null, timeout = null, debounce = null, searchGeneration = 0;
  function cancelSearch() {
    searchGeneration++; worker?.terminate(); worker=null;
    clearTimeout(timeout); clearTimeout(debounce);
  }
  const el = (tag, text, cls='') => {
    const node = document.createElement(tag); node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  };
  const money = value => Number(value).toLocaleString('zh-CN', {maximumFractionDigits: 2});
  const setBusy = busy => document.querySelectorAll('#local-market-content button[data-trade], #local-market-content button[data-governance]').forEach(button => {
    button.disabled = busy || button.dataset.unavailable === '1';
  });
  function prepare(market, game, submit, enterpriseSubmit) {
    cancelSearch(); context = [market,game,submit,enterpriseSubmit]; dirty = true;
    const available = !!market?.available;
    document.querySelector('[data-market-view="local"]')?.classList.toggle('hidden',!available);
    if(!available && marketView==='local') selectMarket('shelves');
    if(content && content.parentElement && !content.parentElement.classList.contains('hidden') && content.closest('.panel-open')) attach(content.parentElement.id==='market-local'?'market':'map');
  }
  function attach(host) {
    const target = document.querySelector(host==='market'?'#market-local':'#map-economy');
    if(!target || !context)return;
    if(!content){content=el('div');content.id='local-market-content';}
    if(content.parentElement!==target) target.append(content);
    if(dirty){dirty=false;build(...context);}
  }
  function selectMarket(value) {
    marketView=value;
    document.querySelector('#market-content')?.classList.toggle('hidden',value!=='shelves');
    document.querySelector('#market-local')?.classList.toggle('hidden',value!=='local');
    document.querySelectorAll('[data-market-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.marketView===value)));
    if(value==='local')attach('market');
  }
  document.addEventListener('DOMContentLoaded',()=>document.querySelectorAll('[data-market-view]').forEach(b=>b.addEventListener('click',()=>selectMarket(b.dataset.marketView))));
  window.addEventListener('game:panel-open',({detail})=>{
    if(detail.name==='market' && marketView==='local')attach('market');
    if(detail.name==='map' && !document.querySelector('#map-economy')?.classList.contains('hidden'))attach('map');
  });
  function build(market, game, submit, enterpriseSubmit) {
    cancelSearch(); const root=content;
    const overviewOpen=address===`${game.id}:${market?.market_id}` && !!root.querySelector('.economy-overview')?.open;
    root.replaceChildren();
    if (!market?.available) return;
    if (address !== `${game.id}:${market.market_id}`) { address = `${game.id}:${market.market_id}`; search = ''; regexMode=false; }
    const head = el('div', null, 'economy-heading');
    head.append(el('h3', `${market.name} · 本地市场`), el('span', `世界历 ${market.year} 年`));
    const intro = el('p', '当地作坊供货、居民消费形成库存。市场成交额包含居民、组织与商队交易；本人产业收入请查看下方产业账目。大笔买卖会改变成交均价，坊市货架另为你保留精选商品。', 'muted');
    if (market.war_pressure) intro.append(' 当地战事正在压低生产并增加运输风险。');
    const metrics = el('div', null, 'economy-metrics');
    for (const [label, value] of [['全市场累计成交',market.turnover],['居民实付',market.household_spending||0],['实际消费件数',market.terminal_consumed||0],['收购资金',market.liquidity],['运营府库',market.operator_balance],['军需成交',market.war_income||0]]) {
      const cell = el('div'); cell.append(el('small',label), el('strong',money(value))); metrics.append(cell);
    }
    const macro = el('details', null, 'economy-world');
    macro.append(el('summary',`${market.world_name}发展潜力 · 开局的 ${money(market.scale)} 倍`),
      el('p',`发展潜力随岁月提升，接近 ${money(market.growth_cap)} 倍时逐渐放缓；实际生产与消费受资材和资金约束。物价水平 ${money(market.price_level)} 倍；黑市收入归本界府库，当前 ${money(market.world_treasury)} 灵石。`));
    const freight = el('details', null, 'economy-freight');
    freight.append(el('summary', `商队流通 · 累计到货 ${money(market.freight_in || 0)} / 发货 ${money(market.freight_out || 0)} 件`));
    window.CaravanMap?.render(freight,market,game.map);
    if (!market.caravans?.length) freight.append(el('p', '当前没有涉及本地的商队运输。'));
    if (market.suppliers?.length) freight.append(el('p', `近期已建模组织与商队的最大供给占比：${Math.round(market.suppliers[0].share * 100)}%。此比例不含背景作坊；新增产出和外来商队会稀释集中度。`));
    const tools = el('div',null,'economy-tools');
    const input = el('input'); input.type='search'; input.maxLength=80; input.placeholder='搜索商品名称'; input.setAttribute('aria-label','查找本地商品'); input.value=search;
    const regex=el('select');regex.setAttribute('aria-label','匹配方式');regex.append(new Option('名称','text'),new Option('表达式','pattern'));regex.value=regexMode?'pattern':'text';
    const searchButton=el('button','搜索');searchButton.type='button';searchButton.onclick=()=>{search=input.value;filter();};
    const feedback = el('p',null,'muted economy-search-feedback');feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');
    const quantity = el('select'); quantity.setAttribute('aria-label','本地市场交易数量');
    for (const value of ['1','10','100']) { const option=el('option',`每笔 ${value} 件`); option.value=value; quantity.append(option); }
    quantity.value=selectedQuantity; tools.append(input,searchButton,regex,quantity);
    const note = el('p',`交易手续费 ${Math.round(market.fee_rate*100)}%；买入显示含费总额，卖出显示扣费实得。收购价低于售价。`, 'muted');
    const list = el('div',null,'economy-goods');
    function draw(rows=market.rows.filter(row=>row.name.toLocaleLowerCase().includes(search.toLocaleLowerCase())),searching=false) {
      list.replaceChildren();
      list.setAttribute('aria-busy',String(searching));
      const wallet = game.market?.spirit_stones || 0, count=Number(selectedQuantity);
      rows.forEach(row=>{
        const card=el('article',null,'economy-good'); card.dataset.itemId=row.id;
        card.dataset.supply=row.status==='紧缺'?'scarce':row.status==='充足'?'surplus':'normal';
        const title=el('div',null,'economy-heading'); title.append(el('b',row.name),el('span',`${row.trend} ${row.status}`,'supply-badge'));
        card.append(title,el('p',`现货 ${money(row.stock)} · 持有 ${money(row.held)} · 累计成交 ${money(row.volume)}`),
          el('small',`近期年均产出 ${money(row.production)} / 消费 ${money(row.consumption)}`, 'muted'));
        const stock=el('progress');stock.max=2;stock.value=Math.min(2,row.stock_ratio||0);stock.setAttribute('aria-label',`${row.name}库存为常备需求的${Math.round((row.stock_ratio||0)*100)}%`);
        card.append(stock,el('small',`库存 / 常备需求 ${Math.round((row.stock_ratio||0)*100)}% · 单价 ${money(row.price)} 灵石 · 参考价 ${money(row.reference)}`,'supply-detail'));
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
      if (!rows.length && !searching) list.append(el('p','没有符合条件的商品。','muted'));
      setBusy(document.body.classList.contains('busy'));
    }
    function filter() {
      cancelSearch();feedback.textContent='';
      if(!regexMode || !search){draw();return;}
      draw([],true);feedback.textContent='正在检索…';
      const generation=searchGeneration;
      function fail(message){if(generation!==searchGeneration)return;cancelSearch();feedback.textContent=message;draw([]);}
      try {worker=new Worker('/local-market-search-worker.js');}
      catch(_){fail('当前环境无法使用正则搜索，请关闭正则后按名称查找。');return;}
      timeout=setTimeout(()=>fail('检索启动超时，请重新检索。'),3000);
      worker.onerror=()=>fail('检索无法启动，请关闭正则后按名称查找。');
      worker.onmessage=({data})=>{
        if(generation!==searchGeneration)return;
        if(data.ready){clearTimeout(timeout);timeout=setTimeout(()=>fail('表达式过于复杂，请缩小匹配范围后重试。'),250);worker.postMessage({pattern:search,names:market.rows.map(r=>r.name)});return;}
        if(data.error){fail(data.error);return;}
        cancelSearch();feedback.textContent=`找到 ${data.indices.length} 种商品`;draw(data.indices.map(i=>market.rows[i]));
      };
    }
    input.oninput=()=>{search=input.value;cancelSearch();if(regexMode){draw([],true);feedback.textContent='正在检索…';debounce=setTimeout(filter,180);}else filter();};
    regex.onchange=()=>{regexMode=regex.value==='pattern';filter();};
    quantity.onchange=()=>{selectedQuantity=quantity.value;filter();};
    const overview=el('details',null,'economy-overview');
    overview.open=overviewOpen;
    overview.append(el('summary','市场概况与经营'),metrics,macro,freight);
    renderCompetition(overview,market,enterpriseSubmit);
    window.EnterprisePanel?.render(overview,market.enterprises,enterpriseSubmit);
    root.append(head,intro,tools,feedback,note,overview,list);filter();
  }
  function renderCompetition(root,market,submit) {
    const data=market.competition;if(!data)return;
    const box=el('details',null,'competition-panel');box.id='market-governance';
    box.append(el('summary','市政与商势 · 产权、供给和竞争'));
    const claim=data.control;
    const hero=el('div',null,'market-control');
    hero.append(el('small','本地市税权'),el('h4',claim?.owner || '本地公共市场'),
      el('p',claim?`${claim.label} · 累计上缴 ${money(claim.received)} 灵石 · 第 ${claim.since} 年接管`:'手续费留用于本地运营与竞争扩产'));
    box.append(hero,el('p','商势按近期成交和本地产业仓储估算，背景产销以近五年规模计入。集中度达到 60% 且持续缺货时，本地基金出资扩产，竞争商队寻找有利可图的补货路线。进口商品只能等待实际运输。','muted'));
    const controls=el('div',null,'market-governance-controls');
    const button=(title,action,payload)=>{const b=el('button',title);b.type='button';b.dataset.governance=action;b.dataset.unavailable=market.can_trade?'0':'1';b.onclick=()=>submit({action,market_id:market.market_id,revision:market.revision,...payload()});controls.append(b);};
    if(claim?.can_manage){
      const label=el('label','市税经营方针'),select=el('select');select.setAttribute('aria-label','市税经营方针');
      for(const p of data.policies){const o=el('option',`${p.name} · 实收手续费上缴 ${p.percent}%`);o.value=p.id;select.append(o);}select.value=claim.policy;label.append(select);controls.append(label);
      button('调整经营方针','market_policy',()=>({policy:select.value}));
    }
    const label=el('label','竞争基金投入'),amount=el('input');amount.type='number';amount.min='1';amount.max='1000000000';amount.step='1';amount.value='1000';amount.setAttribute('aria-label','竞争基金投入');label.append(amount);controls.append(label);
    button('出资改善本地供给','market_relief',()=>({amount:Number(amount.value)}));box.append(controls);
    const list=el('div',null,'competition-grid');
    for(const row of data.rows){
      const card=el('article',null,'competition-card');card.dataset.commodity=row.item;
      const title=el('div',null,'economy-heading');title.append(el('b',row.name),el('span',row.pressure>=32?'竞争补货中':row.power>=60?'供给集中':'自由竞争'));card.append(title,el('small',`主要经营者 · ${row.owner}`));
      for(const [label,value] of [['供给份额',row.supply],['收购份额',row.purchase],['仓储份额',row.storage]]){
        const line=el('div',null,'competition-share');line.append(el('span',label),el('b',`${money(value)}%`));const bar=el('progress');bar.max=100;bar.value=value;bar.setAttribute('aria-label',`${row.name}${label}`);line.append(bar);card.append(line);
      }
      card.append(el('p',`竞争压力 ${money(row.pressure)} / 100 · 实付工料 ${money(row.invested)} · 已增供 ${money(row.added)} 件`));list.append(card);
    }
    if(!data.rows.length)list.append(el('p','成交后逐步形成商品商势记录。','muted'));
    box.append(list);root.append(box);
  }
  window.LocalEconomy={prepare,attach,setBusy};
})();

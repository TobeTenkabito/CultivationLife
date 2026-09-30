(() => {
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=n=>Number(n||0).toLocaleString('zh-CN');
  function render(game,trade,temper) {
    const golden=game.golden_light||{}, pool=game.yaochi||{};
    const blocked=!!game.pending_event||!game.player.alive||!!game.active_trial;
    const button=(label,action,disabled=false,dispatch=trade)=>{const b=el('button',label);b.type='button';b.disabled=blocked||disabled;b.onclick=()=>dispatch(action);return b;};
    for(const [id,data] of [['golden-light',golden],['yaochi',pool]]) {
      document.querySelector(`#${id}-card`).classList.toggle('hidden',!data.available);
      document.querySelector(`[data-panel-target="${id}"]`).classList.toggle('hidden',!data.available);
      if(!data.available)window.UtilityPanels?.close(id);
    }
    const light=document.querySelector('#golden-light-content');light.replaceChildren();
    if(golden.available) {
      light.append(el('h3',`${golden.stages[golden.rank-1].name} · 肉身邻域抵抗 ${Math.round(golden.resistance*100)}%`),el('p','护体金光随仙躯而生，削弱肉身承受的敌方邻域威能与持续压迫。此功效不增加自身邻域的稳固、侵夺或权能，也不消耗仙灵力。','muted'));
      const track=el('div',null,'voisinage-stages');
      golden.stages.forEach((s,i)=>{const n=el('span',s.name,i+1===golden.rank?'current':i+1<golden.rank?'completed':'');n.append(el('small',`${Math.round(s.resistance*100)}%`));track.append(n);});light.append(track);
      if(golden.next_name)light.append(el('p',`锤炼至${golden.next_name}：${golden.recipe.map(r=>`${r.name} ${fmt(r.owned)} / ${fmt(r.needed)}`).join(' · ')}`),el('p','资材可于瑶池功勋商店求取。备齐后在仙界锤炼，材料消耗后晋阶。','muted'),button('锤炼护体金光',{action:'temper_golden_light'},!golden.can_train,temper));
      else light.append(el('p','金光大圆满，肉身邻域抵抗已达上限。','doctrine-note'));
    }
    const root=document.querySelector('#yaochi-content');root.replaceChildren();if(!pool.available)return;
    root.append(el('h3',`瑶池功勋 ${fmt(pool.merit)}`),el('p','瑶池为仙界功勋往来的所在，天庭驻于玉京仙都。功勋与天庭功德分别记载。','muted'));
    if(!pool.local)root.append(el('p','须亲临「瑶池」办理委托和交易。可在地图查看路线与传送阵。','doctrine-note'),button('查看地图',{},false,()=>window.UtilityPanels.open('map')));
    const section=title=>{const s=el('section',null,'doctrine-entry');s.append(el('h3',title));root.append(s);return s;};
    const transact=(label,payload,disabled=false)=>button(label,payload,!pool.local||disabled);
    const jobs=section('接取委托');
    if(pool.job){const j=pool.job;jobs.append(el('p',`${j.name} · 履约 ${fmt(j.progress)} / ${fmt(j.years)} 年 · 报酬 ${fmt(j.reward)} 功勋`));jobs.append(transact(j.progress>=j.years?'交付并领取功勋':'继续履约',{action:j.progress>=j.years?'claim_job':'work'}));}
    else for(const j of pool.commissions)jobs.append(transact(j.name,{action:'accept',target_id:j.id}));
    jobs.append(el('p','接取后须实际履约；游历与等待不计入进度，中途遇事可处理后续做。','muted'));
    const shop=section('功勋商店');
    shop.append(el('p','道统传承、仙躯功法、淬体仙药与金光资材均以功勋兑换。普通坊市仍经营原有货物。','muted'));
    const grid=el('div',null,'doctrine-book-grid');
    for(const o of pool.shop){const row=el('section',null,'doctrine-book');row.dataset.offerId=o.id;row.append(el('h4',o.name),el('p',`数量 ${fmt(o.quantity)} · ${fmt(o.price)} 功勋`),transact(o.owned?'已掌握':'兑换',{action:'buy',target_id:o.id},o.owned||pool.merit<o.price));grid.append(row);}shop.append(grid);
    const orders=section('发布求取委托');
    orders.append(el('p','可求取本境界全部道统功法与仙家资材，不受商店当期传承名额限制。发布时预付功勋，含两成五撮合费；一个行动单位后交付，未领取物品代为保管。','muted'));
    const select=el('select');select.setAttribute('aria-label','求取资材');select.style.maxWidth='100%';
    for(const o of pool.commission_catalog){const op=el('option',`${o.name} · ${fmt(o.price)} 功勋`);op.value=o.id;select.append(op);}orders.append(select);
    const publish=transact('发布委托',{action:'publish'});publish.onclick=()=>trade({action:'publish',target_id:select.value});orders.append(publish);
    for(const o of pool.orders)orders.append(el('p',`${o.name} · ${o.ready?'已交付':`世界历 ${fmt(o.ready_age)} 年可领`}`),transact('领取委托物品',{action:'claim_order',target_id:o.id},!o.ready));
    const exchange=section('功勋兑换与天庭往来'), rate=pool.exchange;
    exchange.append(el('p',`1 功勋可换 ${fmt(rate.stones_per_merit)} 灵石；${fmt(rate.merit_per_court_merit)} 功勋可换 1 天庭功德。灵石不能换取功勋。`));
    const amount=el('input');amount.type='number';amount.min='1';amount.max='1000000';amount.step='1';amount.value='1';amount.setAttribute('aria-label','兑换份数');exchange.append(amount);
    for(const [label,action] of [['兑换灵石','exchange_stones'],['兑换天庭功德','exchange_court_merit']]){const b=transact(label,{action});b.onclick=()=>{if(amount.reportValidity())trade({action,amount:Number(amount.value)});};exchange.append(b);}
    exchange.append(transact(`联络天官 · ${fmt(rate.support_cost)} 功勋 / 支持度 +${rate.support_gain}`,{action:'support'},pool.merit<rate.support_cost));
    if(pool.votes.length){const votes=el('details');votes.append(el('summary',`本次天庭选举 · 每席 ${fmt(rate.vote_cost)} 功勋`),el('p','仅当已取得候选资格时可以议定支持。至多十二席，本次重投有效，选举结束后失效。','muted'));for(const v of pool.votes)votes.append(transact(`${v.name} · ${v.bought?'已议定':'议定一票'}`,{action:'buy_vote',target_id:v.id},v.bought||pool.merit<rate.vote_cost));exchange.append(votes);}
  }
  window.ImmortalEconomyPanel={render};
})();

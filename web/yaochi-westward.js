/* Presentation only. Quotes, eligibility, escrow and years belong to the server. */
(() => {
  const el = (...args) => window.GameUi.element(...args);
  const fmt = n => Number(n || 0).toLocaleString('zh-CN');
  let identity, currency = 'merit', light = 'light_kun';

  function hero(root, pool) {
    const h = el('header', null, 'yaochi-hero');
    const copy = el('div', null, 'yaochi-hero-copy');
    copy.append(el('small', '西望昆仑 · 云水之间', 'yaochi-eyebrow'), el('h3', '瑶池'),
      el('p', pool.westward?.available ? '澄心凝痕，玉液养身，五光归元。' : '仙家资材与功勋往来。'));
    const stats = el('dl', null, 'yaochi-balances');
    for (const [name, value] of [['瑶池功勋', pool.merit], ...(pool.westward?.adopted ? [['可用功德', pool.westward.merit]] : [])]) {
      const item = el('div'); item.append(el('dt', name), el('dd', fmt(value))); stats.append(item);
    }
    h.append(copy, stats); root.append(h);
  }

  function render(root, game, dispatch) {
    if (identity !== game.id) { identity = game.id; currency = 'merit'; light = 'light_kun'; }
    const data = game.yaochi.westward;
    if (!data?.available) return null;
    const section = el('section', null, 'yaochi-practice'); section.id = 'yaochi-practice';
    root.append(section);
    const button = (label, command, token, reason, cls = '') => {
      const b = el('button', label, cls); b.type = 'button'; b.disabled = !!reason;
      b.dataset.westwardAction = command; b.title = reason || label;
      b.onclick = () => dispatch({action: command, target_id: token || ''}); return b;
    };
    function draw() {
      section.replaceChildren();
      const heading = el('div', null, 'yaochi-practice-heading');
      const text = el('div'); text.append(el('h3', '瑶池专修'), el('p', '选择眼下需要的成长，工时与资材各有取舍。', 'muted'));
      const label = el('label', '支付方式'); const select = el('select'); select.setAttribute('aria-label', '专修支付方式');
      for (const [id, name] of [['merit', '瑶池功勋'], ['court', '天庭功德']]) {
        const op = el('option', name); op.value = id; select.append(op);
      }
      select.value = currency; select.onchange = () => { currency = select.value; draw(); };
      label.append(select); heading.append(text, label); section.append(heading);
      if (!data.enabled) section.append(el('p', '扩展已停用。已付项目保留，可在此退出并办理退款。', 'yaochi-notice'));
      else if (data.reason) section.append(el('p', data.reason, 'yaochi-notice'));
      if (!data.adopted && data.enabled) {
        const box = el('div', null, 'yaochi-entitlement');
        box.append(el('div', `功德资历 ${fmt(data.qualification)} · 确认后取得等额可用功德。消费不会降低官品考核资历。`),
          button('确认功德账本', 'westward_adopt', '', data.reason)); section.append(box);
      }
      if (data.last_result) { const result = el('p', data.last_result, 'yaochi-result'); result.setAttribute('role', 'status'); section.append(result); }
      if (data.project) {
        const p = data.project; const current = el('section', null, 'yaochi-current'); current.dataset.westwardProject = p.id;
        current.append(el('small', '当前专修', 'yaochi-eyebrow'), el('h4', p.name),
          el('p', `已修持 ${fmt(p.progress)} / ${fmt(p.years)} 年${p.kind === 'trace' ? ` · 已凝聚 ${fmt(p.delivered)} 仙痕` : p.kind === 'guidance' ? ` · ${p.teacher_name}指导 · 已入账 ${fmt(p.opportunity_delivered)} 机缘` : ''}`));
        const progress = el('progress'); progress.max = p.years; progress.value = p.progress; progress.setAttribute('aria-label', '实际专修进度'); current.append(progress);
        const actions = el('div', null, 'yaochi-project-actions');
        actions.append(button(p.progress >= p.years ? '完成专修' : `继续修持 · 最多 ${fmt(p.years - p.progress)} 年`,
          p.progress >= p.years ? 'westward_claim' : 'westward_work', p.token, p.reason, 'primary'));
        const exit = el('details', null, 'yaochi-exit'); exit.append(el('summary', '退出与退款'));
        exit.append(el('p', `现在退出退还 ${fmt(p.refund)} ${p.currency === 'court' ? '功德' : '功勋'}。已入账仙痕保留，尚未结算的托管药材与神光资材原数返还；已耗工时不返还。`, 'muted'),
          button('退出本次专修', 'westward_cancel', p.token, p.cancel_reason));
        current.append(actions, exit); if (p.reason) current.append(el('p', p.reason, 'yaochi-notice')); section.append(current);
      }
      if (!data.enabled) return;
      const grid = el('div', null, 'yaochi-service-grid');
      const card = row => {
        const node = el('article', null, 'yaochi-service'); node.dataset.service = row.id; node.dataset.kind = row.kind;
        const top = el('div', null, 'yaochi-service-heading');
        top.append(el('span', row.mark, 'yaochi-seal'), el('div'));
        top.lastChild.append(el('small', row.kind === 'light' ? '五光坛' : '专修道场'), el('h4', row.name)); node.append(top);
        if (row.kind === 'light') {
          const choices = el('select'); choices.setAttribute('aria-label', '五光坛神光');
          for (const r of data.services.filter(r => r.kind === 'light')) { const op = el('option', r.name); op.value = r.id; choices.append(op); }
          choices.value = row.id; choices.onchange = () => { light = choices.value; draw(); }; node.append(choices);
        } else node.append(el('div', row.kind === 'body' ? `仙躯 ${row.level} → ${row.level + 1} 层` : row.kind === 'guidance' ? `在场讲师 · ${row.teacher_name}` : '仙痕积累 · 按工时入账', 'yaochi-target'));
        node.append(el('p', row.description, 'yaochi-service-description'));
        const result = el('div', null, 'yaochi-service-benefit'); result.append(el('strong', row.benefit), el('span', `${row.years} 年实际工时`)); node.append(result);
        node.append(el('p', row.comparison, 'yaochi-comparison'));
        const quote = el('p', null, 'yaochi-price');
        quote.append(el('strong', row.price ? `${fmt(currency === 'court' ? row.court_price : row.price)} ${currency === 'court' ? '功德' : '功勋'}` : '不另收服务费'),
          el('small', row.price ? `功勋 ${fmt(row.price)} / 功德 ${fmt(row.court_price)}` : '自备配方资材即可'));
        node.append(quote);
        if (row.recipe.length) {
          const materials = el('details', null, 'yaochi-materials'); const missing = row.recipe.some(r => r.owned < r.needed);
          materials.open = missing; materials.append(el('summary', missing ? '资材不足 · 查看缺口与备料' : '资材齐备 · 查看配方'));
          const list = el('ul');
          for (const r of row.recipe) { const li = el('li'); li.classList.toggle('short', r.owned < r.needed); li.append(el('span', r.name), el('strong', `${fmt(r.owned)} / ${fmt(r.needed)}`)); list.append(li); }
          materials.append(list);
          if (row.supply.items.length) {
            const sum = currency === 'court' ? row.supply.court_price : row.supply.price;
            materials.append(el('p', `按原商品整份补齐缺口：${fmt(sum)} ${currency === 'court' ? '功德' : '功勋'}；余料留在行囊，备料后再预约。`, 'muted'),
              button('按目标备料', `westward_supply_${currency}`, row.token, row[`supply_${currency}_reason`]));
            if(row[`supply_${currency}_reason`]) materials.append(el('small', row[`supply_${currency}_reason`], 'yaochi-unavailable'));
          }
          node.append(materials);
        }
        const unavailable = row[`${currency}_reason`];
        const foot = el('div', null, 'yaochi-service-footer'); foot.append(button('预约专修', `westward_start_${currency}`, row.token, unavailable, 'primary'));
        if (unavailable) foot.append(el('small', unavailable, 'yaochi-unavailable')); node.append(foot); return node;
      };
      for (const row of data.services.filter(r => r.kind !== 'light')) grid.append(card(row));
      const choice = data.services.find(r => r.id === light) || data.services.find(r => r.kind === 'light'); if (choice) grid.append(card(choice));
      section.append(grid);
      const b = data.budget;
      const note = el('details', null, 'yaochi-budget'); note.append(el('summary', '功德资历与公共承兑额度'),
        el('p', `官品资历 ${fmt(data.qualification)} · 可用功德 ${fmt(data.merit)}。消费只扣可用余额。`),
        el('p', `本期尚可承兑 ${fmt(b.remaining)} 灵石标价的服务，世界历 ${fmt(b.ends)} 年进入下一期。功德支付须有实际经费；直接支付瑶池功勋不占此额度。`, 'muted'));
      section.append(note);
    }
    draw(); return section;
  }
  window.YaochiWestward = {hero, render};
})();

(() => {
  const el = (tag, text, cls) => { const node = document.createElement(tag); if (text != null) node.textContent = text; if (cls) node.className = cls; return node; };
  const fmt = value => Number(value || 0).toLocaleString('zh-CN', {maximumFractionDigits: 1});
  const effects = {strike: '仙域杀伤', suppress: '镇压', seal: '封禁收束'};
  function meter(value, maximum, label) {
    const bar = el('progress'); bar.max = Math.max(1, maximum); bar.value = value; bar.setAttribute('aria-label', label); return bar;
  }
  function render(data, act, options = {}) {
    const card = document.querySelector('#doctrine-card');
    const dock = document.querySelector('[data-panel-target="doctrine"]');
    card.classList.toggle('hidden', !data.available); dock.classList.toggle('hidden', !data.available);
    if (!data.available) { window.UtilityPanels?.close('doctrine'); return; }
    const content = document.querySelector('#doctrine-content'); content.replaceChildren();
    const blocked = options.pending || !options.alive;
    function button(text, payload, disabled = false) {
      const node = el('button', text); node.type = 'button'; node.disabled = disabled || blocked;
      node.onclick = () => act(payload); return node;
    }
    content.append(el('p', '仙界二十五道统 · Lv4 开域 · Lv5 归源 · Lv9 道成', 'doctrine-lead'));
    content.append(el('p', `可兼修多门，只有一个道统能越过 Lv4。修成当前阶段后才会揭示下一阶段。每次专修推进一个时间单位（${fmt(data.unit_years)} 年），至多修成一个道统等级。`, 'muted'));
    const conversion = el('section', null, 'doctrine-conversion');
    conversion.append(el('h3', '仙灵力转化'), el('p', `${data.conversion.stage}/5 阶段 · 可用容量 ${fmt(data.conversion.capacity)} · 当前 ${fmt(data.conversion.current)}`));
    if (!data.conversion.complete) {
      conversion.append(meter(data.conversion.progress, data.conversion.required, '本阶段转化积累'),
        el('p', `积累 ${fmt(data.conversion.progress)} / ${fmt(data.conversion.required)} 年；仙界环境提供转化所需本源，普通灵气不能替代。`, 'muted'),
        button('专修仙灵力转化', {action: 'convert'}));
    } else conversion.append(el('p', '仙元已成。消耗仙灵力不会使转化程度倒退。', 'muted'));
    content.append(conversion);
    const owned = el('section'); owned.append(el('h3', '已获传承'));
    const learned = data.rows.filter(row => row.learned);
    if (!learned.length) owned.append(el('p', '尚未获得道统功法。可先从下方仙界书市承接一门传承。', 'muted'));
    for (const row of learned) {
      const panel = el('section', null, 'doctrine-entry'); panel.dataset.doctrineId = row.id;
      panel.append(el('h4', `${row.name} · Lv${row.level}${row.origin ? ' · 本源归属' : ''}${row.active ? ' · 当前仙域' : ''}`), el('p', row.description));
      panel.append(el('p', `已获功法：${row.manuals.map(book => `《${book.name}》${book.grade_name} · 功法 Lv${book.level}`).join('；')}`, 'muted'));
      const next = row.stages.find(stage => stage.level === row.level + 1);
      if (next) panel.append(el('p', `下一阶段：Lv${next.level}「${next.title}」 · 需要${next.realm_name}`),
        meter(row.experience, next.years, `${row.name}修炼积累`), el('small', `${fmt(row.experience)} / ${fmt(next.years)} 年`));
      if (row.blocked) panel.append(el('p', '本源已归于另一道统，此门保留 Lv4 的修为与仙域。', 'doctrine-note'));
      const actions = el('div', null, 'doctrine-actions');
      actions.append(button('参悟此道统', {action: 'study', doctrine_id: row.id}, !row.can_train));
      if (row.level >= 4) actions.append(button(row.active ? '仙域已采用' : '采用此仙域', {action: 'activate', doctrine_id: row.id}, row.active));
      if (row.can_bind) {
        const origin = el('button', '确立本源并突破 Lv5'); origin.type = 'button'; origin.disabled = blocked;
        origin.onclick = () => options.confirm({title: '确立唯一的本源归属',
          body: `选择《${row.name}》后，只有此道统可以继续修至 Lv9；其他道统最多 Lv4。当前没有重塑本源的途径。`, confirmText: '归源于此道统',
          onConfirm: () => act({action: 'origin', doctrine_id: row.id, confirm_origin: true})});
        actions.append(origin);
      }
      panel.append(actions);
      const chapters = el('details'); chapters.append(el('summary', '已能参悟的篇章'));
      for (const stage of row.stages) {
        const chapter = el('section', null, 'doctrine-chapter');
        chapter.append(el('b', `Lv${stage.level} · ${stage.title}${stage.level > row.level ? '（待修）' : '（已成）'}`), el('p', stage.description));
        if (stage.domain) {
          const d = stage.domain;
          chapter.append(el('p', `权能篇 · ${stage.ability_name}`));
          chapter.append(el('p', `【${d.name}】稳固 ${fmt(d.stability)} · 侵夺 ${fmt(d.incursion)} · 权能 ${fmt(d.authority)} · ${effects[d.effect]}`),
            el('small', `展开 ${fmt(d.opening_cost)} / 维持 ${fmt(d.upkeep_cost)} / 施权 ${fmt(d.effect_cost)} 仙灵力 · 最多覆盖 ${d.max_targets} 个对象`));
          for (const text of stage.features) chapter.append(el('p', text, 'muted'));
        }
        chapters.append(chapter);
      }
      panel.append(chapters); owned.append(panel);
    }
    content.append(owned);
    const shop = el('section'); shop.append(el('h3', '仙界传承书市'), el('p', '取得任意一门相应功法，即可开始参悟其所属道统。重复购买获得功法玉简，可用于功法合参；道统等级与功法等级分别计算。', 'muted'));
    const books = el('div', null, 'doctrine-book-grid');
    for (const book of data.offers) {
      const entry = el('section', null, 'doctrine-book');
      entry.append(el('h4', `《${book.name}》`), el('p', `${book.doctrine_name} · ${book.grade_name} · ${book.origin}`),
        el('small', `机缘 +${fmt(book.stats.opportunity_bonus * 100)}% · 气血 +${fmt(book.stats.hp_bonus * 100)}% · 法力 +${fmt(book.stats.mp_bonus * 100)}% · 战力 +${fmt(book.stats.combat_bonus)}`),
        button(`${book.owned ? '再购玉简' : '承接传承'} · ${fmt(book.price)} 灵石`, {action: 'buy', manual_id: book.id}));
      books.append(entry);
    }
    shop.append(books); content.append(shop);
    const unknown = el('details'); unknown.append(el('summary', '仙界道统名录'));
    for (const row of data.rows.filter(row => !row.learned)) unknown.append(el('p', `${row.name}：${row.description}`));
    content.append(unknown);
  }

  function battleRound(round) {
    const data = round.domain;
    if (!data || (!(data.fields || []).length && !(round.events || []).some(text => text.includes('仙域')))) return null;
    const section = el('section', null, 'domain-round'); section.append(el('h4', '领域态势'));
    const names = id => data.participants?.[id]?.name || id || '无';
    const grid = el('div', null, 'domain-field-grid');
    for (const field of data.fields || []) {
      const box = el('section', null, `domain-field ${data.participants?.[field.owner]?.side === 'player' ? 'allied' : 'hostile'}`);
      box.append(el('b', `${names(field.owner)} · ${field.name || '未知领域'}`),
        el('p', `稳固 ${fmt(field.stability ?? field.strength)} · 侵夺 ${fmt(field.incursion ?? field.strength)} · 权能 ${field.authority == null ? '未明' : fmt(field.authority)}`),
        el('small', `庇护：${field.protects.map(names).join('、')} · 侵夺：${field.targets.map(names).join('、') || '无'}`),
        el('small', `剩余仙灵力 ${fmt(data.resources[field.owner])} · 持续 ${field.sustained_rounds || 1} 轮`));
      grid.append(box);
    }
    section.append(grid);
    for (const [id, row] of Object.entries(data.relations || {})) {
      if (!row.attacker) continue;
      const relation = {dominated: '庇护被突破', contested: '仙域相持', pressed: '承压但仍有庇护'}[row.relation] || '未受侵夺';
      const line = el('div', null, `domain-relation ${row.relation}`);
      line.append(el('span', `${names(row.attacker)} → ${names(id)}：${relation}`));
      const ratio = row.attack_strength / Math.max(1, row.attack_strength + row.defense_strength);
      const bar = el('div', null, 'domain-comparison'); bar.style.setProperty('--invasion-share', `${ratio * 100}%`);
      bar.setAttribute('role', 'img'); bar.setAttribute('aria-label', `侵夺 ${fmt(row.attack_strength)} 对稳固 ${fmt(row.defense_strength)}`);
      line.append(bar, el('small', `侵夺 ${fmt(row.attack_strength)} → 庇护稳固 ${fmt(row.defense_strength)}`)); section.append(line);
    }
    for (const [id, progress] of Object.entries(data.seal_progress || {})) section.append(el('small', `${names(id)} · 封禁收束 ${fmt(progress * 100)}%`));
    section.append(el('p', data.ordinary?.player || data.ordinary?.enemy ? '未受支配的战线继续常规交锋。' : '本轮由领域阶段结算。', 'muted'));
    return section;
  }
  window.DoctrinePanel = {render, battleRound};
})();

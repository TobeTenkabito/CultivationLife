(() => {
  const node = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };
  const fmt = n => Number(n || 0).toLocaleString('zh-CN', {maximumFractionDigits: 2});
  window.BuddhistWish = {render(system, game, mutate) {
    const panel = document.getElementById('buddhist-wish-card');
    const dock = document.querySelector('[data-panel-target="buddhist-wish"]');
    const root = document.getElementById('buddhist-wish-content');
    dock.classList.toggle('hidden', !system.available);
    panel.classList.toggle('hidden', !system.available);
    root.replaceChildren();
    if (!system.available) return;
    const wish = system.wish;
    const balance = node('section', null, 'wish-balance');
    balance.append(node('p', '心有所守，愿有所成', 'eyebrow'), node('strong', `${wish.value} / 100`, 'wish-number'));
    const meter = node('progress'); meter.max = 100; meter.value = wish.value; meter.setAttribute('aria-label', '愿力'); balance.append(meter);
    const benefits = node('div', null, 'wish-benefits');
    for (const [title, value] of [['基础突破概率', `${fmt(wish.value * .05)} 个百分点`], ['机缘获取效率', `+${fmt(wish.value * .2)}%`], ['雷劫伤害减免', `${fmt(wish.value * .1)}%`]]) {
      const cell = node('div'); cell.append(node('small', title), node('b', value)); benefits.append(cell);
    }
    balance.append(benefits); root.append(balance);
    const quiet = node('section', null, 'wish-section'); quiet.append(node('h3', '清净持守'));
    for (const [key, label] of [['kill', '未击杀修士'], ['concubine', '未新增侍妾'], ['entwine', '未缠绵共参']]) {
      const units = wish.quiet[key]; const row = node('div', null, 'wish-quiet');
      row.append(node('span', label), node('strong', `${fmt(units)} 个时间单位`), node('small', units >= 5 ? '此后每完整单位 +1' : `再持守 ${fmt(6 - units)} 个单位首次 +1`)); quiet.append(row);
    }
    quiet.append(node('p', '三项独立累计，从第六个完整时间单位起各 +1；防御击杀仍会中断“不杀生”，但不扣进攻杀人的愿力。', 'muted')); root.append(quiet);
    const nirvana = node('section', null, 'wish-section'); nirvana.append(node('h3', '一念涅槃'));
    nirvana.append(node('p', '消耗 100 愿力，直接提升一个小境界（一层），免除此关天劫；不跨大境界，不越过本界修为上限。此后三个时间单位，机缘获取效率额外 +100%。'));
    if (wish.nirvana_units > 0) nirvana.append(node('p', `涅槃加持中 · 尚余 ${fmt(wish.nirvana_units)} 个时间单位`, 'wish-active'));
    if (wish.blocked) nirvana.append(node('p', wish.blocked, 'muted'));
    const action = node('button', '消耗 100 愿力 · 涅槃'); action.type = 'button';
    action.disabled = wish.value < 100 || !!wish.blocked || !!system.assembly || !!game.pending_event || !!game.active_trial || !game.player.alive || !!game.player.imprisonment;
    action.onclick = async () => { if (action.disabled) return; action.disabled = true; try { await mutate({action:'nirvana'}); } finally { if (action.isConnected) action.disabled = false; } }; nirvana.append(action); root.append(nirvana);
    const rules = node('details', null, 'wish-section'); rules.append(node('summary', '善行与失守 · 查看愿力规则'));
    for (const text of ['释放俘虏 +1；招收弟子 +2。', '拷打俘虏 −1；主动进攻并击杀修士 −2。', '本人提出的宣战决议通过 −5。', '处死俘虏、弟子或侍妾 −5（弟子须战斗击杀）。', '突然袭击普通队友 −2；截杀同门 −10；截杀师傅或道侣 −30。', '同一场背叛按最严重的关系扣一次，不叠加普通击杀扣除。']) rules.append(node('p', text)); root.append(rules);
    const log = node('section', null, 'wish-section'); log.append(node('h3', '道心记事'));
    if (!wish.log.length) log.append(node('p', '愿从今日起。', 'muted'));
    wish.log.slice(-12).reverse().forEach(row => log.append(node('p', `第 ${row.age} 年 · ${row.reason} ${row.delta >= 0 ? '+' : ''}${row.delta} · 愿力 ${row.value}`)));
    root.append(log);
  }};
})();

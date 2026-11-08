/* The original building and server quotes own all costs, years and faith. */
(() => {
  const el = (...args) => window.GameUi.element(...args);
  const fmt = n => Number(n || 0).toLocaleString('zh-CN');
  function render(root, game, dispatch) {
    const d = game.yaochi.earth;
    if (!d?.available) return null;
    const section = el('section', null, 'earth-temple'); root.append(section);
    const button = (label, action, target = '', reason = '', primary = false) => {
      const b = el('button', label, primary ? 'primary' : ''); b.type = 'button';
      b.dataset.earthAction = action; if (target) b.dataset.earthTarget = target;
      b.disabled = !!reason; b.title = reason || label;
      b.onclick = () => dispatch({action, target_id: d.token + (target ? '|' + target : '')});
      return b;
    };
    const cost = (root, quote) => {
      root.append(el('p', `工料支出 · ${fmt(quote.coins)} 灵石`, 'earth-price'));
      const list = el('ul', null, 'earth-materials');
      for (const r of quote.recipe) {
        const li = el('li'); li.append(el('span', r.name), el('strong', `${fmt(r.owned)} / ${fmt(r.needed)}`));
        if (r.owned < r.needed) li.classList.add('short'); list.append(li);
      }
      root.append(list);
    };
    const head = el('header', null, 'earth-heading');
    const text = el('div'); text.append(el('small', '一方水土 · 一庙香火', 'yaochi-eyebrow'),
      el('h3', d.temple ? d.temple.name : '奉建土地庙'),
      el('p', d.temple ? `${d.city_name} · ${d.temple.status === 'intact' ? '庙宇完好' : '原庙待修'} · ${d.active ? '地仙主持' : '暂停主持'}${d.local ? ' · 本人在此' : ' · 异地只读'}` : '依托仙界本地凡人与混居城市，护民之后，香火助修。', 'muted'));
    head.append(text); section.append(head);
    if (d.last_result) { const p = el('p', d.last_result, 'yaochi-result'); p.setAttribute('role', 'status'); section.append(p); }
    if (d.reason) section.append(el('p', d.reason, 'yaochi-notice'));
    if (!d.temple) {
      const box = el('div', null, 'earth-foundation');
      const intro = el('div'); intro.append(el('h4', '从一座主庙开始'),
        el('p', '奉建不改变城市权属。信任初始为 50，完成护民后才取得助修额度；一座主庙，最多三座分庙。'),
        el('p', '建庙沿原即时营造规则收费。修士之城没有凡人供奉，不可奉建。', 'muted'));
      const materials = el('div'); cost(materials, d.build_cost); box.append(intro, materials); section.append(box);
      const list = el('div', null, 'earth-city-list');
      for (const c of d.cities) {
        const row = el('article'); row.append(el('h4', c.name), el('p', {mortal:'凡人之城', mixed:'混居之城',cultivator:'修士之城'}[c.population]));
        row.append(button('在此奉建', 'earth_build', c.id, c.reason, true));
        if (c.reason) row.append(el('small', c.reason, 'yaochi-unavailable')); list.append(row);
      }
      if (!d.cities.length) list.append(el('p', '此地没有可依托的城市。请由地图亲赴仙界凡人城或混居城。', 'muted'));
      section.append(list); return section;
    }
    const stats = el('dl', null, 'earth-stats');
    for (const [name, value, note] of [
      ['香火信任', `${fmt(d.trust)} / 100`, `有效时普通闭关 +${Math.round(d.potential_bonus*100)}%`],
      ['可用助修', `${fmt(d.allowance)} 年`, d.until ? `世界历 ${fmt(d.until)} 年截止` : '完成一轮护民后取得'],
      ['当前加持', `+${Math.round(d.bonus*100)}%`, d.bonus ? '原仙痕判定同步提高，仍只判一次' : '在原庙、额度有效时生效']]) {
      const item = el('div'); item.append(el('dt', name), el('dd', value), el('small', note)); stats.append(item);
    }
    section.append(stats);
    const toolbar = el('div', null, 'earth-toolbar');
    toolbar.append(button('在庙闭关 · 100 年', 'earth_cultivate', '', d.reason || (!d.allowance ? '请先完成护民，取得有效助修额度' : ''), true));
    if (d.temple.status !== 'intact') {
      const map = el('button', '前往地图 · 原址重建'); map.type = 'button'; map.onclick = () => window.UtilityPanels.open('map'); toolbar.append(map);
    }
    section.append(toolbar);
    if(d.disputes?.active){
      const notice=el('div',null,'yaochi-notice');notice.append(el('p',`待办地方争议：${d.disputes.active.name}。其他庙务须待本案完成或撤回。`));
      const view=el('button','查看当前争议');view.type='button';view.onclick=()=>section.querySelector('[data-subpage="地方争议"]').click();notice.append(view);section.append(notice);
    }
    if (d.facilities?.works) {
      const notice = el('div', null, 'yaochi-notice'); notice.append(el('p', `本庙正在专项营造：${d.facilities.works.progress} / ${d.facilities.works.years} 年。`));
      const view = el('button', '查看施工'); view.type = 'button'; view.onclick = () => section.querySelector('[data-subpage="专项设施"]').click(); notice.append(view); section.append(notice);
    }
    if (d.duty) {
      const task = d.duty, box = el('section', null, 'yaochi-current earth-current');
      const limit = task.stage === 'survey' ? 10 : task.years;
      box.append(el('small', '当前地方事务', 'yaochi-eyebrow'), el('h4', task.name));
      const steps = el('ol', null, 'earth-steps');
      for (const [i, label] of (task.special ? ['专项准备', '服务已交付', '亲自履约', '验收香火'] : ['实地勘查', '选择投入', '亲自履约', '验收香火']).entries()) {
        const li = el('li', label); li.classList.toggle('current', i === (task.stage === 'survey' ? (task.progress < 10 ? 0 : 1) : (task.progress < task.years ? 2 : 3))); steps.append(li);
      }
      box.append(steps, el('p', `已付实际工时 ${fmt(task.progress)} 年 · 本段目标 ${limit} 年 · 助修截止世界历 ${fmt(task.started+500)} 年`));
      if (task.special) box.append(el('p', task.receipt + ' 服务已交付，完成公共履约后可验收香火。', 'yaochi-result'));
      const progress = el('progress'); progress.max = limit; progress.value = task.progress; progress.setAttribute('aria-label', '地方事务实际工时'); box.append(progress);
      if (task.stage === 'survey' && task.progress === 10) {
        const plans = el('div', null, 'earth-plans');
        for (const p of task.plans) {
          const card = el('article'); card.append(el('h4', p.name), el('p', `累计 ${p.years} 年 · 还需 ${p.years-10} 年`)); cost(card, p);
          card.append(button('采用此方案', 'earth_plan', p.id, task.work_reason || p.reason, true));
          if (p.reason) card.append(el('small', p.reason, 'yaochi-unavailable')); plans.append(card);
        }
        box.append(plans, el('p', '两方案信任收益相同。节用方案多花 50 年，助修截止时间不延长。筹备后物资即投入使用，取消不退。', 'muted'));
      } else box.append(button(task.progress >= limit ? '验收本案' : `继续${task.stage === 'survey' ? '勘查' : '履约'} · 最多 ${limit-task.progress} 年`, task.progress >= limit ? 'earth_claim' : 'earth_work', '', task.work_reason, true));
      const exit = el('details', null, 'yaochi-exit'); exit.append(el('summary', '退出地方事务'),
        el('p', `已开始后退出损失 10 信任，已付工时与投入物资不退。当前退出损失 ${task.progress ? 10 : 0} 信任。`, 'muted'),
        button('退出本案', 'earth_cancel', '', task.cancel_reason)); box.append(exit); section.append(box);
    } else {
      section.append(el('h4', '地方事务'), el('p', '每案先勘查 10 年，再投入工料并履约。完成后取得至多 400 年本地助修；只换香火，不叠领功德功勋。', 'muted'));
      const grid = el('div', null, 'yaochi-service-grid earth-duties');
      for (const row of d.duties) {
        const card = el('article', null, 'yaochi-service');
        card.append(el('span', row.mark, 'yaochi-seal'), el('h4', row.name), el('p', row.description), el('strong', `验收信任 +${row.trust}`));
        const estimate = el('details', null, 'yaochi-materials'); estimate.append(el('summary', '接事前查看工料与时间'));
        estimate.append(el('p', `常规方案累计 100 年，工费 ${fmt(row.cost.coins)} 灵石；节用方案累计 150 年，工费与各项材料减半。`));
        for (const r of row.cost.recipe) estimate.append(el('p', `${r.name}：常规 ${fmt(r.needed)} / 节用 ${fmt(Math.ceil(r.needed/2))}，持有 ${fmt(r.owned)}`));
        estimate.append(el('p', '勘查已用年份计入总工期。后续择案才扣工料；退出不返已耗年份，已开始后信任减 10。', 'muted')); card.append(estimate);
        const footer = el('div', null, 'yaochi-service-footer'); footer.append(button('承接并勘查', 'earth_accept', row.id, row.reason, true));
        if (row.reason) footer.append(el('small', row.reason, 'yaochi-unavailable')); card.append(footer); grid.append(card);
      }
      section.append(grid);
    }
    const rules = el('details', null, 'yaochi-budget'); rules.append(el('summary', '香火规则与暂停主持'),
      el('p', '香火只加强本人在原庙所在地的普通闭关，不提高师门请教、丹药、瑶池专修或公务报酬。外出、庙城损毁、许可失效时停止加持；原址重建不会刷新额度。'),
      el('p', '期限从接事时起算 500 年。暂停、恢复、读档都不续期；已获得的修为保留。累计完成 '+fmt(d.completed)+' 案。', 'muted'),
      button(d.active ? '暂停本庙主持' : '恢复本庙主持', d.active ? 'earth_suspend' : 'earth_resume', '', d.duty || d.facilities?.works || d.disputes?.active ? '请先完成或退出当前事务' : d.active ? d.recovery_reason : d.resume_reason));
    section.append(rules);
    const localNodes = [...section.children].filter(n => n !== head);
    const facilities = window.EarthTempleFacilities.render(d, button); section.append(facilities);
    const network = el('section', null, 'earth-network'); network.append(el('h4', `一主三分 · 已立 ${d.network.length} / 4 庙`),
      el('p', '本人到哪座庙，便办理该庙事务。香火、截止年与设施各归原址；多庙不叠加个人加持。遗址仍占名额，旧庙须原址重建。', 'muted'));
    const sites = el('div', null, 'earth-network-grid');
    for (const s of d.network) {
      const card = el('article', null, `earth-network-site${s.local ? ' is-local' : ''}`); card.dataset.templeId=s.id;
      card.append(el('small', `${s.main ? '主庙' : '分庙'}${s.local ? ' · 本人在此' : ''}`, 'yaochi-eyebrow'), el('h4', s.name), el('p', s.location_name, 'muted'),
        el('p', `${s.status === 'intact' ? '完好' : '待修'} · ${s.active ? '主持中' : '已暂停'} · 信任 ${s.trust}`),
        el('p', `助修 ${s.allowance} 年${s.until ? ` · ${fmt(s.until)} 年截止` : ''}`));
      const names = s.facilities.filter(Boolean).map(k => d.facilities.options.find(o => o.id===k)?.name).join(' / ');
      card.append(el('small', names || '专项设施尚未营造', 'yaochi-unavailable'));
      if (s.pending) card.append(el('strong', `待办：${s.pending}`, 'earth-pending'));
      sites.append(card);
    }
    network.append(sites);
    const map = el('button', '查看地图 · 沿原道路前往'); map.type='button'; map.onclick=()=>window.UtilityPanels.open('map'); network.append(map);
    if (!d.local) {
      const expansion = el('section', null, 'earth-expansion'); expansion.append(el('h4', '在当前地域奉建分庙'),
        el('p', '须与一座完好、主持中且仍有城市许可的原庙有直接道路相连。本人亲自到场后，依托此地原凡人／混居城市奉建；不自动迁移或新造城市。', 'muted'));
      const materials=el('details',null,'yaochi-materials'); materials.append(el('summary', `分庙营造 · ${fmt(d.build_cost.coins)} 灵石及原矿材`)); cost(materials,d.build_cost); expansion.append(materials);
      for (const c of d.cities) { const entry=el('article',null,'earth-branch-candidate'); entry.append(el('h4',c.name), button('在此奉建分庙','earth_build',c.id,c.reason,true)); if(c.reason) entry.append(el('small',c.reason,'yaochi-unavailable')); expansion.append(entry); }
      if(!d.cities.length) expansion.append(el('p','当前地域没有原城市。可先沿地图的既有筑城入口建造凡人城或混居城，再奉建分庙。','muted'));
      network.append(expansion);
    }
    section.append(network);
    const cases=window.EarthDisputes.render({...d,age:game.player.age},button);section.append(cases);
    window.PanelPages?.mount('earth-temple',section,[['庙务',localNodes],['地方争议',[cases]],['专项设施',[facilities]],['庙域名录',[network]]]);
    return section;
  }
  window.EarthTemple = {render};
})();

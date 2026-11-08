/* All target quotes and completed services come from the original server authorities. */
(() => {
  const el = (...args) => window.GameUi.element(...args);
  const fmt = n => Number(n || 0).toLocaleString('zh-CN');
  function render(data, button) {
    const d = data.facilities, root = el('section', null, 'earth-facilities');
    root.append(el('h4', '两席营造 · 三途取舍'), el('p', '每庙两个专项设施位。施工需本人在场，旧设施开工即停用拆解；竣工后开放原址业务。', 'muted'));
    if (!data.local) root.append(el('p', '当前为异地只读。请沿原地图道路亲赴这座庙，再办理营造与专项事务。', 'yaochi-notice'));
    if (d.works) {
      const w = d.works, name = d.options.find(o => o.id === (w.kind || 'remove'))?.name || '专项营造';
      const box = el('section', null, 'yaochi-current earth-works');
      box.append(el('small', `第 ${w.slot+1} 席 · 正在施工`, 'yaochi-eyebrow'), el('h4', name), el('p', `已施工 ${w.progress} / ${w.years} 年 · 原设施已停用，工料已投入`));
      const bar = el('progress'); bar.max = w.years; bar.value = w.progress; bar.setAttribute('aria-label', '专项营造实际工时'); box.append(bar);
      box.append(button(w.progress >= w.years ? '验收竣工' : `继续施工 · 最多 ${w.years-w.progress} 年`, w.progress >= w.years ? 'earth_complete_works' : 'earth_work', '', data.reason, true));
      const exit = el('details', null, 'yaochi-exit'); exit.append(el('summary', '退出施工与后果'), el('p', '退出后此席保持空置。已付工料、已耗年份均不返还，拆解的旧设施不复原。', 'muted'), button('退出本次施工', 'earth_cancel_works', '', d.cancel_reason));
      box.append(exit); root.append(box);
    }
    const grid = el('div', null, 'earth-facility-grid');
    d.slots.forEach((installed, index) => {
      const spec = d.options.find(o => o.id === installed), card = el('article', null, 'earth-facility-slot'); card.dataset.facilitySlot = index;
      const reserved = d.works?.slot === index;
      card.append(el('small', `第 ${index+1} 席`, 'yaochi-eyebrow'), el('h4', reserved ? '施工中' : spec?.name || '留白待建'),
        el('p', reserved ? '工料已投入，待现场施工完毕后验收。' : spec?.purpose || '护境、民生、教化，择一奉建。', 'muted'));
      const details = el('details', null, 'earth-construction'); details.open = !installed && !reserved;
      details.append(el('summary', installed ? '改建或拆除' : '选择专项设施'));
      const select = el('select'); select.setAttribute('aria-label', `第${index+1}席专项设施`);
      for (const o of d.options) { const option = el('option', o.name); option.value = o.id; select.append(option); }
      select.value = d.options.find(o => !o.reasons[index])?.id || d.options.find(o => o.id !== installed && o.id !== 'remove')?.id || 'remove';
      const preview = el('div', null, 'earth-facility-quote');
      const draw = () => {
        const o = d.options.find(o => o.id === select.value); preview.replaceChildren();
        preview.append(el('p', o.purpose), el('strong', `${fmt(o.cost.coins)} 灵石 · ${o.years} 年`));
        const list = el('ul', null, 'earth-materials');
        for (const r of o.recipe) { const li = el('li'); li.append(el('span', r.name), el('strong', `${fmt(r.owned)} / ${fmt(r.needed)}`)); if (r.owned<r.needed) li.classList.add('short'); list.append(li); }
        preview.append(list, el('p', '开工即扣工料并拆下原设施；取消不退款、不复原。', 'muted'), button('确认投入并开工', 'earth_facility', `${index}:${o.id}`, o.reasons[index], true));
        if (o.reasons[index]) preview.append(el('small', o.reasons[index], 'yaochi-unavailable'));
      };
      select.onchange = draw; details.append(select, preview); draw(); card.append(details); grid.append(card);
    });
    root.append(grid);
    const heading = el('div', null, 'earth-service-intro'); heading.append(el('h4', '原址专项事务'),
      el('p', '先按原规则交付一次实际维护、重建或培养，再由本人履行百年公共事务。验收换本庙香火，不叠领功德功勋。原业务现在扣费并生效，退出后续履约不会撤回成果或退款。', 'muted')); root.append(heading);
    for (const kind of d.slots.filter(Boolean)) {
      const spec = d.options.find(o => o.id === kind), rows = d.services.filter(o => o.kind === kind);
      const box = el('article', null, 'earth-special-service'); box.dataset.facilityService = kind;
      box.append(el('h4', spec.name));
      if (!rows.length) box.append(el('p', data.reason || {watch:'此地没有需修复的自有镇地阵。可在原阵法窗口布阵、查看完整度和修阵资源。',care:'此地没有可按原权限修复的建筑遗址。建筑损毁后可在这里落实原址修缮。',teach:'此地没有当前可培养的弟子、后代、族人或道侣。人物须实际在场、自由且满足原培养条件。'}[kind], 'muted'));
      else {
        const select = el('select'); select.setAttribute('aria-label', `${spec.name}业务对象`);
        for (const row of rows) { const option = el('option', row.title); option.value = row.id; select.append(option); }
        const preview = el('div');
        const draw = () => { const row = rows.find(r => r.id === select.value); preview.replaceChildren();
          preview.append(el('p', row.result), el('p', row.cost, 'earth-price'), button('交付原业务并承接百年履约', 'earth_special', row.id, row.reason, true));
          if (row.reason) preview.append(el('small', row.reason, 'yaochi-unavailable'));
        }; select.onchange = draw; box.append(select, preview); draw();
      }
      root.append(box);
    }
    return root;
  }
  window.EarthTempleFacilities = {render};
})();

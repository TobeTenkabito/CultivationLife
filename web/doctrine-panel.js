(() => {
  const el = (tag, text, cls) => { const node = document.createElement(tag); if (text != null) node.textContent = text; if (cls) node.className = cls; return node; };
  const fmt = value => Number(value || 0).toLocaleString('zh-CN', {maximumFractionDigits: 1});
  const effects = {strike: '仙域杀伤', suppress: '镇压', seal: '封禁收束'};
  function meter(value, maximum, label) {
    const bar = el('progress'); bar.max = Math.max(1, maximum); bar.value = value; bar.setAttribute('aria-label', label); return bar;
  }
  function meridians(v) {
    const ns = 'http://www.w3.org/2000/svg';
    const svgNode = (tag, attrs = {}) => { const n = document.createElementNS(ns, tag); for(const [k,val] of Object.entries(attrs)) n.setAttribute(k, val); return n; };
    const figure = el('figure', null, 'meridian-figure');
    const svg = svgNode('svg', {viewBox:'0 0 360 540', role:'img', 'aria-label':`人体仙脉图：已开 ${v.opened} 条，本层需要 ${v.layer * v.per_layer} 条`});
    const title = svgNode('title'); title.textContent = '二十七仙脉 · 人体经络示意'; svg.append(title);
    svg.append(svgNode('path', {class:'meridian-body',d:'M167 91 C138 81 140 26 180 24 C220 26 222 81 193 91 L197 104 Q233 107 243 136 L268 203 L298 282 Q306 307 292 311 L276 290 L248 240 L232 186 L223 271 Q226 303 218 335 L215 417 L212 478 L233 505 Q238 518 211 515 L195 508 L189 418 L180 348 L171 418 L165 508 L149 515 Q122 518 127 505 L148 478 L145 417 L142 335 Q134 303 137 271 L128 186 L112 240 L84 290 L68 311 Q54 307 62 282 L92 203 L117 136 Q127 107 163 104 Z'}));
    const center = [[180,48],[180,78],[180,114],[180,149],[180,184],[180,219],[180,254],[180,288],[180,318]];
    const left = [[142,126],[123,159],[106,202],[88,251],[72,291],[157,340],[159,395],[157,454],[148,499]];
    const right = left.map(([x,y])=>[360-x,y]);
    for(const points of [center,left.slice(0,5),right.slice(0,5),[left[0],[145,205],[150,270],...left.slice(5)],[right[0],[215,205],[210,270],...right.slice(5)]]) svg.append(svgNode('polyline', {class:'meridian-channel',points:points.map(p=>p.join(',')).join(' ')}));
    center.forEach(([x,y],i)=>{
      [center[i],left[i],right[i]].forEach(([px,py],side)=>{
        const n=i*3+side, opened=n<v.opened, next=n===v.opened && n<v.layer*v.per_layer;
        const group=svgNode('g',{class:`meridian-node ${opened?'opened':next?'next':'sealed'}`,'data-vein':n+1});
        const label=svgNode('title');label.textContent=`第 ${n+1} 脉 · ${opened?'已贯通':next?'下一条可开':'未贯通'}`;
        const circle=svgNode('circle',{cx:px,cy:py,r:10});
        const text=svgNode('text',{x:px,y:py+3.5,'text-anchor':'middle'});text.textContent=n+1;
        group.append(label,circle,text);svg.append(group);
      });
    });
    figure.append(svg,el('figcaption','实心圆为已开仙脉，粗环为下一脉，空心圆为未开；每层三脉，开脉后需手动冲关。'));
    return figure;
  }
  function render(data, act, options = {}) {
    for (const name of ['doctrine', 'immortal-veins', 'immortal-body', 'voisinage', 'daomen']) {
      const visible = data.available && (name !== 'voisinage' || !!data.voisinages?.length);
      document.querySelector(`#${name}-card`).classList.toggle('hidden', !visible);
      document.querySelector(`[data-panel-target="${name}"]`).classList.toggle('hidden', !visible);
      if (!visible) window.UtilityPanels?.close(name);
    }
    if (!data.available) return;
    const content = document.querySelector('#doctrine-content'); content.replaceChildren();
    const veins = document.querySelector('#immortal-veins-content'); veins.replaceChildren();
    const voisinage = document.querySelector('#voisinage-content'); voisinage.replaceChildren();
    const daomen = document.querySelector('#daomen-content'); daomen.replaceChildren();
    const body = document.querySelector('#immortal-body-content'); body.replaceChildren();
    const blocked = options.pending || !options.alive;
    function button(text, payload, disabled = false, dispatch = act) {
      const node = el('button', text); node.type = 'button'; node.disabled = disabled || blocked;
      node.onclick = () => dispatch(payload); return node;
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
    veins.append(conversion);
    const v = data.veins;
    veins.append(el('h3', `${v.realm} · 第 ${v.layer} 层`), el('p', `已开仙脉 ${v.opened} / ${v.total} · 每层须开 ${v.per_layer} 条，再手动突破；第九层需本境 27 脉贯通。`),
      meter(v.opened, v.total, '本境仙脉'), el('p', `机缘 ${fmt(v.opportunity)} / 无尽 · 仙痕 ${fmt(v.traces)}`));
    veins.append(meridians(v));
    if (v.next_cost) veins.append(el('p', `下一脉：机缘 ${fmt(v.next_cost.opportunity)} · 仙痕 ${v.next_cost.traces}`),
      el('p', `本次成功率 ${fmt(v.chance*100)}% · 失败消耗本次资源，保底增加 ${fmt(v.pity_step*100)} 个百分点，成功后重置。`, 'muted'),
      button('尝试开启下一条仙脉', {action:'open_vein'}, !v.converted || v.opportunity < v.next_cost.opportunity || v.traces < v.next_cost.traces, options.immortal));
    if (v.ready) veins.append(el('p', `${v.requirement} 冲关需机缘 ${fmt(v.breakthrough_cost)}，本次成功率 ${fmt(v.breakthrough_chance*100)}%。`),
      button(v.major?'手动冲击下一大境界':'手动突破下一层', {action:'breakthrough'}, !v.can_breakthrough, options.immortal));
    veins.append(el('p', `每次实际获得机缘，有 ${fmt(v.trace_chance*100)}% 概率获得一道仙痕。仙痕是独立储量，显示于状态栏。`, 'muted'));
    const b = data.immortal_body;
    body.append(el('h3', `真仙之躯 · 第 ${b.level} 层`), el('p', `炼体 ${b.body_training} / ${b.required_training} 层 · ${b.body_training >= b.required_training ? '已具备淬炼根基' : '须先将炼体修至百层'}`),
      el('p', `护体金光：${b.golden_light ? '已解锁' : `第 ${b.golden_light_level} 层解锁`} · 冲击金仙须仙躯达到第 20 层。`, 'doctrine-note'),
      meter(b.level, b.golden_light ? b.max_level : b.golden_light_level, '仙躯修炼进度'),
      el('p', `仙躯增加本源气血 ${fmt(b.hp_bonus)}、本源法力 ${fmt(b.mp_bonus)}。护体金光以仙灵力维持，可抵御低阶攻击。`, 'muted'));
    const manuals = b.manuals.filter(m=>m.owned);
    if (!manuals.length) body.append(el('p', '尚未掌握仙躯功法。右侧「道门」可求取传承与淬体药材；旧炼体功法不能用于仙躯。'));
    for (const manual of manuals) body.append(button(`${b.manual === manual.id ? '当前修习：' : '改修：'}《${manual.name}》`, {action:'select_body_manual',supply_id:manual.id}, b.manual === manual.id, options.immortal));
    if(b.manual) {
      body.append(el('p', `下层配方：${b.recipe.map(r=>`${r.name} ${fmt(r.owned)} / ${fmt(r.needed)}`).join(' · ')}`),
        el('p', `成功率 ${fmt(b.chance*100)}% · 已失败 ${b.failures} 次 · 每次失败增加 ${fmt(b.pity_step*100)} 个百分点。失败消耗药材，换功法保留保底。`, 'muted'),
        button(b.level >= b.max_level ? '已达当前仙躯上限' : '以仙药淬炼下一层', {action:'train_body'}, !b.can_train, options.immortal));
    }
    const bodyShop=el('section',null,'doctrine-entry');bodyShop.append(el('h3','仙躯传承与仙药'));
    for(const manual of b.manuals) bodyShop.append(el('h4',`《${manual.name}》`),el('p',manual.description),button(manual.owned?'已掌握':`求取传承 · ${fmt(manual.price)} 灵石`,{action:'buy_body_manual',supply_id:manual.id},manual.owned,options.immortal));
    for(const supply of b.supplies) bodyShop.append(button(`${supply.name} ×${supply.quantity} · ${fmt(supply.price)} 灵石（持有 ${fmt(supply.owned)}）`,{action:'buy_body_supply',supply_id:supply.id},false,options.immortal));
    daomen.append(bodyShop);
    const owned = el('section'); owned.append(el('h3', '已获传承'));
    const learned = data.rows.filter(row => row.learned);
    if (!learned.length) owned.append(el('p', '尚未获得道统功法。前往右侧「道门」承接传承、访求同道。', 'muted'));
    for (const row of learned) {
      const panel = el('section', null, 'doctrine-entry'); panel.dataset.doctrineId = row.id;
      panel.append(el('h4', `${row.name} · Lv${row.level}${row.origin ? ' · 本源归属' : ''}${row.active ? ' · 当前仙域' : ''}`), el('p', row.description));
      panel.append(el('p', `已获功法：${row.manuals.map(book => `《${book.name}》${book.grade_name} · 功法 Lv${book.level}`).join('；')}`, 'muted'));
      const next = row.stages.find(stage => stage.level === row.level + 1);
      if (next) panel.append(el('p', `下一阶段：Lv${next.level}「${next.title}」 · 需要${next.realm_name}`),
        meter(row.experience, next.years, `${row.name}修炼积累`), el('small', `${fmt(row.experience)} / ${fmt(next.years)} 年`));
      if (next) panel.append(el('p', `功法门槛 Lv${next.level}（当前最高 Lv${row.manual_level}） · 本层注解${row.has_annotation ? '已取得，可反复参阅' : '尚缺，请访求道门'}`),
        el('p', `本次突破成功率 ${fmt(row.chance * 100)}% · 失败后增加 ${fmt(row.pity_step * 100)} 个百分点。`, 'doctrine-note'));
      if (row.blocked) panel.append(el('p', '本源已归于另一道统，此门保留 Lv4 的修为与仙域。', 'doctrine-note'));
      const actions = el('div', null, 'doctrine-actions');
      actions.append(button('参悟此道统', {action: 'study', doctrine_id: row.id}, !row.can_train));
      if (row.can_bind) {
        const origin = el('button', '确立本源并尝试 Lv5'); origin.type = 'button'; origin.disabled = blocked;
        origin.onclick = () => options.confirm({title: '确立唯一的本源归属',
          body: `选择《${row.name}》后，只有此道统可以继续修至 Lv9；其他道统最多 Lv4。本次成功率 ${fmt(row.chance * 100)}%，即使失败，本源归属仍然确定。当前没有重塑本源的途径。`, confirmText: '归源于此道统',
          onConfirm: () => act({action: 'origin', doctrine_id: row.id, confirm_origin: true})});
        actions.append(origin);
      }
      panel.append(actions);
      const chapters = el('details'); chapters.append(el('summary', '已能参悟的篇章'));
      for (const stage of row.stages) {
        const chapter = el('section', null, 'doctrine-chapter');
        chapter.append(el('b', `Lv${stage.level} · ${stage.title}${stage.level > row.level ? '（待修）' : '（已成）'}`), el('p', stage.description));
        if (stage.voisinage) {
          const d = stage.voisinage;
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
    voisinage.append(el('p', '每场斗法只采用一个邻域。道统提升基础威能，额外温养分别强化稳固、侵夺与权能，切换不会丢失培养。', 'muted'));
    if (!data.voisinages.length) voisinage.append(el('p', '尚未激发仙域，先将任一道统参悟至 Lv4。'));
    const axisNames = {stability:'稳固',incursion:'侵夺',authority:'权能'};
    for (const field of data.voisinages) {
      const entry = el('section', null, 'doctrine-entry');
      entry.append(el('h3', field.name), el('p', `${field.doctrine} · Lv${field.level}`),
        button(field.active ? '当前出战仙域' : '采用此仙域', {action:'activate',doctrine_id:field.id}, field.active));
      for (const axis of field.axes) {
        entry.append(el('p', `${axisNames[axis.id]} ${fmt(axis.value)} · 温养 ${axis.rank}/${axis.max}`),
          button(axis.rank >= axis.max ? `${axisNames[axis.id]}已温养圆满` : `温养${axisNames[axis.id]} · ${fmt(axis.cost.opportunity)} 机缘 / ${axis.cost.traces} 仙痕`,
            {action:'train_voisinage',doctrine_id:field.id,axis:axis.id}, axis.rank >= axis.max || !v.converted || v.opportunity < axis.cost.opportunity || v.traces < axis.cost.traces, options.immortal));
      }
      voisinage.append(entry);
    }
    daomen.append(el('p', '道统是大道的传承，道门是研习它的同道。名单随访求逐渐显现；注解永久保留，功法须先修至相应等级才能参悟道统。', 'muted'));
    for (const row of learned) {
      const entry = el('section', null, 'doctrine-entry'); entry.dataset.daomenId = row.id;
      entry.append(el('h3', row.name), el('p', `已结识同道 ${row.peers.length} · 访求积累 ${fmt(row.explore_progress)} / 100 年`),
        button(`访求同道 · ${fmt(data.explore_price)} 灵石`, {action:'explore',doctrine_id:row.id}, row.peers.length >= 9));
      for (const peer of row.peers) {
        const person = el('section', null, 'doctrine-chapter'); person.dataset.npcId = peer.id;
        person.append(el('b', `${peer.name} · 道统 Lv${peer.level}${peer.available ? '' : ' · 当前无法请教'}`));
        if (row.level < 9) person.append(button(row.has_annotation ? `Lv${row.level + 1} 注解已收录` : `求取 Lv${row.level + 1} 注解 · ${fmt(data.annotation_price * (row.level + 1))} 灵石`,
          {action:'annotation',doctrine_id:row.id,npc_id:peer.id}, !peer.available || row.has_annotation || peer.level <= row.level));
        for (const book of row.manuals.filter(b => b.level < 9 && b.level < peer.level)) person.append(button(`请教《${book.name}》至 Lv${book.level + 1} · ${fmt(data.annotation_price * (book.level + 1) ** 2)} 灵石`,
          {action:'teach_manual',doctrine_id:row.id,npc_id:peer.id,manual_id:book.id}, !peer.available));
        entry.append(person);
      }
      daomen.append(entry);
    }
    const shop = el('section'); shop.append(el('h3', '仙界传承书市'), el('p', '取得任意一门相应功法，即可开始参悟其所属道统。重复购买获得功法玉简，可用于功法合参；道统等级与功法等级分别计算。', 'muted'));
    const books = el('div', null, 'doctrine-book-grid');
    for (const book of data.offers) {
      const entry = el('section', null, 'doctrine-book');
      entry.append(el('h4', `《${book.name}》`), el('p', `${book.doctrine_name} · ${book.grade_name} · ${book.origin}`),
        el('small', `机缘 +${fmt(book.stats.opportunity_bonus * 100)}% · 气血 +${fmt(book.stats.hp_bonus * 100)}% · 法力 +${fmt(book.stats.mp_bonus * 100)}% · 战力 +${fmt(book.stats.combat_bonus)}`),
        button(`${book.owned ? '再购玉简' : '承接传承'} · ${fmt(book.price)} 灵石`, {action: 'buy', manual_id: book.id}));
      books.append(entry);
    }
    shop.append(books); daomen.append(shop);
    const unknown = el('details'); unknown.append(el('summary', '仙界道统名录'));
    for (const row of data.rows.filter(row => !row.learned)) unknown.append(el('p', `${row.name}：${row.description}`));
    daomen.append(unknown);
  }

  function battleRound(round) {
    const data = round.voisinage;
    if (!data || (!(data.fields || []).length && !(round.events || []).some(text => text.includes('仙域')))) return null;
    const section = el('section', null, 'voisinage-round'); section.append(el('h4', '领域态势'));
    const names = id => data.participants?.[id]?.name || id || '无';
    const grid = el('div', null, 'voisinage-field-grid');
    for (const field of data.fields || []) {
      const box = el('section', null, `voisinage-field ${data.participants?.[field.owner]?.side === 'player' ? 'allied' : 'hostile'}`);
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
      const line = el('div', null, `voisinage-relation ${row.relation}`);
      line.append(el('span', `${names(row.attacker)} → ${names(id)}：${relation}`));
      const ratio = row.attack_strength / Math.max(1, row.attack_strength + row.defense_strength);
      const bar = el('div', null, 'voisinage-comparison'); bar.style.setProperty('--invasion-share', `${ratio * 100}%`);
      bar.setAttribute('role', 'img'); bar.setAttribute('aria-label', `侵夺 ${fmt(row.attack_strength)} 对稳固 ${fmt(row.defense_strength)}`);
      line.append(bar, el('small', `侵夺 ${fmt(row.attack_strength)} → 庇护稳固 ${fmt(row.defense_strength)}`)); section.append(line);
    }
    for (const [id, progress] of Object.entries(data.seal_progress || {})) section.append(el('small', `${names(id)} · 封禁收束 ${fmt(progress * 100)}%`));
    section.append(el('p', data.ordinary?.player || data.ordinary?.enemy ? '未受支配的战线继续常规交锋。' : '本轮由领域阶段结算。', 'muted'));
    return section;
  }
  window.DoctrinePanel = {render, battleRound};
})();

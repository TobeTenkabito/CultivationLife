(() => {
  const el = (tag, text, cls) => { const node = document.createElement(tag); if (text != null) node.textContent = text; if (cls) node.className = cls; return node; };
  const fmt = value => Number(value || 0).toLocaleString('zh-CN', {maximumFractionDigits: 1});
  const effects = {strike: '仙域杀伤', suppress: '镇压', seal: '封锁退路、传讯与支援', restrict: '禁制力量', isolate: '隔离器物', restore_body: '修复肉身', restore_spirit: '稳定心神', restore_field: '修复邻域稳固'};
  const effectNames = d => (d.effects?.length ? d.effects.map(e => effects[typeof e === 'string' ? e : e.kind]) : [effects[d.effect]]).join('、');
  let collectionGame = null;
  const opened = new Set(), queries = new Map();
  function compact(key, title, detail) {
    const card = el('details', null, 'doctrine-entry doctrine-compact');
    card.open = opened.has(key); card.dataset.search = `${title} ${detail}`.toLowerCase();
    const summary = el('summary'), seal = el('span', title.slice(0,1), 'doctrine-seal'), text = el('span');
    text.append(el('b', title), el('small', detail)); summary.append(seal,text);card.append(summary);
    card.addEventListener('toggle',()=>{if(card.isConnected){if(card.open)opened.add(key);else opened.delete(key);}});
    return card;
  }
  function searchCollection(root, key, label) {
    const search = el('input'); search.type='search';search.placeholder=label;search.setAttribute('aria-label',label);
    search.className='doctrine-search';search.value=queries.get(key)||'';
    const filter=()=>{queries.set(key,search.value);for(const row of root.querySelectorAll(':scope > .doctrine-compact'))row.hidden=!row.dataset.search.includes(search.value.trim().toLowerCase());};
    search.oninput=filter;root.prepend(search);filter();
  }
  function meter(value, maximum, label) {
    const bar = el('progress'); bar.max = Math.max(1, maximum); bar.value = value; bar.setAttribute('aria-label', label); return bar;
  }
  function meridians(v) {
    return window.MeridianAtlas.render(v, 'immortal');
  }
  function render(data, act, options = {}) {
    const currentGame = typeof game !== 'undefined' ? game?.id : null;
    if(collectionGame!==currentGame){opened.clear();queries.clear();collectionGame=currentGame;}
    for (const name of ['doctrine', 'immortal-veins', 'immortal-body', 'voisinage', 'daomen']) {
      const visible = data.available && (name !== 'voisinage' || !!data.voisinages?.length);
      document.querySelector(`#${name}-card`).classList.toggle('hidden', !visible);
      document.querySelector(`[data-panel-target="${name}"]`).classList.toggle('hidden', !visible);
      if (!visible) window.UtilityPanels?.close(name);
    }
    const market = document.querySelector('#immortal-market-content'); market.replaceChildren(); market.classList.add('hidden');
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
    veins.append(el('h3', `${v.realm} · ${v.phase?.name || '仙脉'} · 第 ${v.layer} 层`), el('p', `已开仙脉 ${v.opened} / ${v.total} · 每层须开 ${v.per_layer} 条，再手动突破；第九层需本境 27 脉贯通。`),
      meter(v.opened, v.total, '本境仙脉'), el('p', `机缘 ${fmt(v.opportunity)} / 无尽 · 仙痕 ${fmt(v.traces)}`));
    veins.append(el('p', `仙脉累计增加本源：气血 +${fmt(v.intrinsic_total?.hp)} · 法力 +${fmt(v.intrinsic_total?.mp)}；本境每脉增加气血 ${fmt(v.intrinsic_per_vein?.hp)}、法力 ${fmt(v.intrinsic_per_vein?.mp)}。`, 'doctrine-note'));
    veins.append(meridians(v));
    if (!v.ready && (v.layer < 9 || v.realm_index !== 12)) veins.append(el('p', `本层三脉贯通后，手动冲关另需机缘 ${fmt(v.breakthrough_cost)}；请与开脉费用分别准备。`, 'doctrine-note'));
    if (v.next_cost) veins.append(el('p', `下一脉：机缘 ${fmt(v.next_cost.opportunity)} · 仙痕 ${v.next_cost.traces}`),
      el('p', `本次成功率 ${fmt(v.chance*100)}% · 失败消耗本次资源，保底增加 ${fmt(v.pity_step*100)} 个百分点，成功后重置。`, 'muted'),
      button('尝试开启下一条仙脉', {action:'open_vein'}, !v.converted || v.opportunity < v.next_cost.opportunity || v.traces < v.next_cost.traces, options.immortal));
    if (v.ready) veins.append(el('p', `${v.requirement} 冲关需机缘 ${fmt(v.breakthrough_cost)}。${v.trial ? v.trial + '；大境界以劫战结果决定，不再先掷基础成功率。' : `本次成功率 ${fmt(v.breakthrough_chance*100)}%。`}`),
      button(v.major?'手动冲击下一大境界':'手动突破下一层', {action:'breakthrough'}, !v.can_breakthrough, options.immortal));
    veins.append(el('p', `每次实际获得机缘，有 ${fmt(v.trace_chance*100)}% 概率获得一道仙痕。仙痕是独立储量，显示于状态栏。`, 'muted'));
    const b = data.immortal_body;
    body.append(el('h3', `真仙之躯 · 第 ${b.level} 层`), el('p', `炼体 ${b.body_training} / ${b.required_training} 层 · ${b.body_training >= b.required_training ? '已具备淬炼根基' : '须先将炼体修至百层'}`),
      el('p', `护体金光：${b.golden_light ? '已解锁' : `第 ${b.golden_light_level} 层解锁`} · 冲击金仙须仙躯达到第 20 层。`, 'doctrine-note'),
      meter(b.level, b.golden_light ? b.max_level : b.golden_light_level, '仙躯修炼进度'),
      el('p', `仙躯增加本源气血 ${fmt(b.hp_bonus)}、本源法力 ${fmt(b.mp_bonus)}。护体金光是仙躯被动防护，不消耗仙灵力，储量耗尽仍然有效。`, 'muted'));
    const manuals = b.manuals.filter(m=>m.owned);
    if (!manuals.length) body.append(el('p', '尚未掌握仙躯功法。右侧「瑶池」可用功勋求取传承与淬体药材；旧炼体功法不能用于仙躯。'));
    for (const manual of manuals) body.append(button(`${b.manual === manual.id ? '当前修习：' : '改修：'}《${manual.name}》`, {action:'select_body_manual',supply_id:manual.id}, b.manual === manual.id, options.immortal));
    if(b.manual) {
      body.append(el('p', `下层配方：${b.recipe.map(r=>`${r.name} ${fmt(r.owned)} / ${fmt(r.needed)}`).join(' · ')}`),
        el('p', `成功率 ${fmt(b.chance*100)}% · 已失败 ${b.failures} 次 · 每次失败增加 ${fmt(b.pity_step*100)} 个百分点。失败消耗药材，换功法保留保底。`, 'muted'),
        button(b.level >= b.max_level ? '已达当前仙躯上限' : '以仙药淬炼下一层', {action:'train_body'}, !b.can_train, options.immortal));
    }
    const owned = el('section'); owned.append(el('h3', '已获传承'));
    const learned = data.rows.filter(row => row.learned);
    if (!learned.length) owned.append(el('p', '尚未获得道统功法。前往「瑶池」取得传承，再去「道门」访求同道。', 'muted'));
    for (const row of learned) {
      const panel = compact(`doctrine:${row.id}`, `${row.name} · Lv${row.level}`, `${row.origin?'本源归属 · ':''}${row.active?'当前出战 · ':''}${row.fusion?.level?'真传已合 · ':''}功法 ${row.manuals.length} 部 · ${row.blocked?'本源受限':row.has_annotation?'已有下一层注解':'可展开查看修行条件'}`); panel.dataset.doctrineId = row.id;
      panel.append(el('h4', `${row.name} · Lv${row.level}${row.fusion?.level ? ' · 真传已合' : ''}${row.origin ? ' · 本源归属' : ''}${row.active ? ' · 当前仙域' : ''}`), el('p', row.description));
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
      if(row.fusion){
        const f=row.fusion, box=el('section',null,'doctrine-chapter');box.dataset.fusionId=row.id;
        box.append(el('b','合练传承'),el('p',`本门原始功法已集齐 ${f.owned} / ${f.total} 部。原功法保留，合练传承不计入收集数量。`));
        if(!f.level)box.append(el('p',`集齐并掌握全套、修为达到其中最高品阶后，可以消耗 ${fmt(f.cost)} 仙痕合练。`),button('合练全套传承',{action:'fuse',doctrine_id:row.id},!f.can_fuse));
        else {
          box.append(el('p',`《${f.name}》Lv${f.level} · 当前道统加持层级 ${f.effect_level}`),el('p','合练功法在道统内独立参悟，不用玉简与注解；道统升级仍需对应注解。加持随本门特色改善稳固、侵夺、施权、恢复或仙力消耗，以功法和道统中较低层级为限。','muted'));
          if(f.level<9)box.append(meter(f.experience,f.required,'合练功法参悟'),el('p',`参悟 ${fmt(f.experience)} / ${fmt(f.required)} 年 · 本层待付 ${fmt(f.cost)} 仙痕。中断保留积累，已付仙痕不重复收取。`),button('参悟合练功法',{action:'study_fusion',doctrine_id:row.id},!f.can_study));
          else box.append(el('p','合练功法已达 Lv9。'));
        }
        panel.append(box);
      }
      const chapters = el('details'); chapters.append(el('summary', '已能参悟的篇章'));
      for (const stage of row.stages) {
        const chapter = el('section', null, 'doctrine-chapter');
        chapter.append(el('b', `Lv${stage.level} · ${stage.title}${stage.level > row.level ? '（待修）' : '（已成）'}`), el('p', stage.description));
        if (stage.voisinage) {
          const d = stage.voisinage;
          chapter.append(el('p', `权能篇 · ${stage.ability_name}`));
          chapter.append(el('p', `【${d.name}】稳固 ${fmt(d.stability)} · 侵夺 ${fmt(d.incursion)} · 权能 ${fmt(d.authority)} · ${effectNames(d)}`),
            el('small', `展开 ${fmt(d.opening_cost)} / 维持 ${fmt(d.upkeep_cost)} / 施权 ${fmt(d.effect_cost)} 仙灵力 · 最多覆盖 ${d.max_targets} 个对象`));
          for (const text of stage.features) chapter.append(el('p', text, 'muted'));
        }
        chapters.append(chapter);
      }
      panel.append(chapters); owned.append(panel);
    }
    searchCollection(owned,'doctrine','搜索已获道统');
    content.append(owned);
    voisinage.append(el('p', '每场斗法只采用一个邻域。初成、化境、大成各四层，之后为不分层数的至臻。跨阶段须独自抵抗五轮天域，只结算邻域；冲击至臻可能被道统同化而亡。道统与温养共同影响实际威能，切换保留培养。', 'muted'));
    if (!data.voisinages.length) voisinage.append(el('p', '尚未激发仙域，先将任一道统参悟至 Lv4。'));
    const axisNames = {stability:'稳固',incursion:'侵夺',authority:'权能'};
    for (const field of data.voisinages) {
      const entry = compact(`field:${field.id}`, field.name, `${field.active?'当前出战 · ':''}${field.cultivation?.label||''} · ${field.doctrine} · ${effectNames(field)}`);entry.dataset.voisinageId=field.id;
      entry.append(el('h3', field.name), el('p', `${field.doctrine} · Lv${field.level}`),
        button(field.active ? '当前出战仙域' : '采用此仙域', {action:'activate',doctrine_id:field.id}, field.active));
      const growth = field.cultivation;
      if (growth) {
        const track = el('div', null, 'voisinage-stages');
        ['初成','化境','大成','至臻'].forEach((name, index) => {
          const stage = el('span', name, index === Math.floor((growth.rank-1)/4) ? 'current' : index*4 < growth.rank ? 'completed' : '');
          if (name === '至臻') stage.title = '至臻不分层数';
          else stage.append(el('small', index === Math.floor((growth.rank-1)/4) ? `${growth.layer} / 4 层` : '四层'));
          track.append(stage);
        });
        entry.append(track, el('h4', `培养境界 · ${growth.label}`));
        if (growth.cost) {
          entry.append(el('p', `下一层：${growth.next_label} · ${fmt(growth.cost.opportunity)} 机缘 / ${fmt(growth.cost.traces)} 仙痕`));
          if (growth.backlash) entry.append(el('p', growth.rank === 12 ? '至臻之劫：最强道统反噬，失败将被同化而亡。先温养稳固、补足仙灵力，再引劫。' : '跨阶段将引发道统反噬；须存活五轮，失败会陨落。', 'doctrine-note'));
          entry.append(button(growth.backlash ? `引动反噬 · 冲击${growth.next_label}` : `修炼至${growth.next_label}`,
            {action:'advance_voisinage',doctrine_id:field.id}, !v.converted || v.opportunity < growth.cost.opportunity || v.traces < growth.cost.traces, options.immortal));
        } else entry.append(el('p', '至臻已成，不再分层。大罗境兼具任一道统 Lv9，可获本体成就「道祖」。', 'doctrine-note'));
      }
      entry.append(el('p', `展开 ${fmt(field.opening_cost)} · 每轮维持 ${fmt(field.upkeep_cost)} · 覆盖目标 ${field.max_targets} · 基础投入上限 ${fmt(field.max_investment)}`, 'muted'),
        el('p', `邻域能力：${effectNames(field)}`, 'voisinage-abilities'));
      for (const axis of field.axes) {
        entry.append(el('p', `${axisNames[axis.id]} ${fmt(axis.value)} · 温养 ${axis.rank}/${axis.max}`),
          button(axis.rank >= axis.max ? `${axisNames[axis.id]}已温养圆满` : `温养${axisNames[axis.id]} · ${fmt(axis.cost.opportunity)} 机缘 / ${axis.cost.traces} 仙痕`,
            {action:'train_voisinage',doctrine_id:field.id,axis:axis.id}, axis.rank >= axis.max || !v.converted || v.opportunity < axis.cost.opportunity || v.traces < axis.cost.traces, options.immortal));
      }
      voisinage.append(entry);
    }
    searchCollection(voisinage,'voisinage','搜索邻域名称、道统或能力');
    daomen.append(el('p', '道统是大道的传承，道门是研习它的同道。寻访不消耗时间，先查看同道层次，确认结识才记入往来；注解永久保留，功法须先修至相应等级才能参悟道统。', 'muted'));
    for (const row of learned) {
      const entry = compact(`daomen:${row.id}`, row.name, `已结识 ${row.peers.length} 位 · ${row.peer_preview ? `访客 Lv${row.peer_preview.level} 待确认` : '展开寻访或请教'}`); entry.dataset.daomenId = row.id;
      entry.append(el('h3', row.name), el('p', `已结识同道 ${row.peers.length} / 9 · 寻访不消耗时间或灵石，确认结识才支付 ${fmt(data.explore_price)} 灵石。`),
        button('寻找同道 · 不消耗时间', {action:'explore',doctrine_id:row.id}, row.peers.length >= 9));
      if(row.peer_preview){const peer=row.peer_preview;const visit=el('section',null,'doctrine-chapter peer-preview');visit.append(el('b',`${peer.name} · 道统 Lv${peer.level}`),el('p','尚未结识；可继续寻访，替换当前访客。'),button(`结识这位同道 · ${fmt(data.explore_price)} 灵石`,{action:'retain_peer',doctrine_id:row.id,npc_id:peer.id},row.peers.length>=9),button('暂不结识',{action:'dismiss_peer',doctrine_id:row.id,npc_id:peer.id}));entry.append(visit);}
      for (const peer of row.peers) {
        const person = el('section', null, 'doctrine-chapter'); person.dataset.npcId = peer.id;
        person.append(el('b', `${peer.name} · 道统 Lv${peer.level}${peer.available ? '' : ' · 当前无法请教'}`));
        if (row.level < 9) person.append(button(row.has_annotation ? `Lv${row.level + 1} 注解已收录` : `求取 Lv${row.level + 1} 注解 · ${fmt(data.annotation_price * (row.level + 1))} 灵石`,
          {action:'annotation',doctrine_id:row.id,npc_id:peer.id}, !peer.available || row.has_annotation || peer.level <= row.level));
        for (const book of row.manuals.filter(b => !b.fused && b.level < 9 && b.level < peer.level)) person.append(button(`求取《${book.name}》Lv${book.level} 玉简（合参至 Lv${book.level + 1}） · ${fmt(data.annotation_price * (book.level + 1) ** 2)} 灵石`,
          {action:'teach_manual',doctrine_id:row.id,npc_id:peer.id,manual_id:book.id}, !peer.available));
        entry.append(person);
      }
      daomen.append(entry);
    }
    searchCollection(daomen,'daomen','搜索道门');
    const unknown = el('details'); unknown.append(el('summary', '仙界道统名录'));
    for (const row of data.rows) unknown.append(el('p', `${row.name} · ${row.learned ? '已获传承' : '未获传承'}：${row.description}`));
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
        el('small', `剩余元力 ${fmt(data.resources[field.owner])} · 持续 ${field.sustained_rounds || 1} 轮`),
        el('small', `权能：${effectNames(field)}`));
      grid.append(box);
    }
    section.append(grid);
    for (const [id, row] of Object.entries(data.relations || {})) {
      if (!row.attacker) continue;
      const relation = {dominated: '庇护被突破', contested: '邻域相持', pressed: '承压但仍有庇护'}[row.relation] || '未受侵夺';
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

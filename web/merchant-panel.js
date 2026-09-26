(() => {
  let taskStars = 1;
  const money = value => Number(value || 0).toLocaleString('zh-CN');
  const element = (tag, text, className = '') => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    node.className = className;
    return node;
  };
  function render(system, act) {
    const root = document.querySelector('#merchant-content');
    document.querySelector('#merchant-card').classList.remove('hidden');
    root.replaceChildren();
    const button = (label, action, payload = {}, disabled = false) => {
      const node = element('button', label);
      node.type = 'button'; node.disabled = disabled;
      node.dataset.merchantUnavailable = disabled ? '1' : '0';
      node.onclick = () => act({action, ...payload});
      return node;
    };
    const membership = system.membership;
    root.append(element('p', membership ? `${membership.title} · 本部影响力 ${money(membership.influence)}` : '尚未加入商盟。到总部或分部所在地图即可入盟；商盟身份与宗门、家族、种族身份独立。', 'merchant-membership'));
    const rules = element('details'); rules.append(element('summary', '身份与委托规则'));
    rules.append(element('p', '分部成员累计120影响力晋为使节，360晋为特使；600影响力并通过修为、实战考核后，可在总部调任使节。同界各分部共用影响力。总部直入成员不能直接升使节，须前往本界分部从成员历练。总部使节累计360总部影响力可升特使。'));
    rules.append(element('p', '任务按实际年数消耗时间，途中劫数会中断并保留进度。提交与炼制任务需实物；悬赏和护送会实战，招募及情报可能失败。跨界收集耗时为本界的15倍，委托超时退回全部本金，手续费不退。')); root.append(rules);
    const dock = document.querySelector('[data-panel-target="merchant"]');
    dock.classList.toggle('merchant-notice', !!system.notices?.length);
    dock.title = system.notices?.length ? `商盟 · ${system.notices.length}条传讯` : '商盟';
    if (system.notices?.length) {
      const notices = element('details', null, 'merchant-notices');
      notices.append(element('summary', `商盟传讯（${system.notices.length}）`));
      system.notices.slice(-6).reverse().forEach(row => notices.append(element('p', `第${row.age}年 · ${row.message}`)));
      notices.append(button('清除传讯', 'dismiss_notices')); root.append(notices);
    }
    if (system.active) {
      const task = system.active;
      const active = element('section', null, 'merchant-active');
      active.append(element('h3', `待完成 · ${'★'.repeat(task.stars)} ${task.name}`));
      active.append(element('p', `已投入 ${task.worked}/${task.years} 年；报酬：${money(task.reward.stones)} 灵石、材料 ${task.reward.materials} 件、机缘 ${task.reward.opportunity}、因果 -${task.reward.karma}、影响力 +${task.reward.influence}`));
      const requirements = {supply:`需交付 ${task.material_name} ×${task.quantity}`, weapon:`需在接取后亲自炼成基础战力至少 ${money(task.power * .1)} 的普通法宝（本命及神机不可交付）`, formation:`需 ${task.stars + 1} 件至少 ${Math.max(1, task.realm - 1)} 阶闲置阵材，交商盟工坊炼制`, bounty:`追捕目标战力 ${money(task.power)}，须成功击杀`, escort:`劫道者战力 ${money(task.power)}，你为防御方`, recruit:'招募结果受修为与已雇人手影响', intel:'情报搜集结果受修为与已雇人手影响'};
      active.append(element('p', requirements[task.kind]));
      const available = system.alliances.some(row => row.id === task.alliance_id && row.member && row.local_site);
      active.append(button('执行 / 继续任务', 'work', {alliance_id:task.alliance_id}, !available));
      active.append(button('放弃任务', 'abandon', {alliance_id:task.alliance_id}, !available)); root.append(active);
    }
    system.alliances.forEach(alliance => {
      const panel = element('section', null, 'merchant-alliance');
      panel.append(element('h3', `${alliance.name}${alliance.cross_world ? ' · 跨界商盟' : ''}`));
      panel.append(element('p', `${alliance.policy_name}（第${alliance.next_policy_age}年调整） · 势力 ${money(alliance.power)} · 资材 ${money(alliance.reserves)} · ${alliance.relation}`));
      panel.append(element('p', `本界总部：${alliance.hq_name} · 盟主 ${alliance.leader_name}（${alliance.leader_realm}）${alliance.cross_world ? `；总盟主 ${alliance.chief_name}（${alliance.chief_realm}），战力 ${money(alliance.chief_power)}` : ''}`));
      panel.append(element('p', `分部：${alliance.offices.map(row => `${row.name}〔${row.leader} · ${row.realm}〕`).join('、')}`));
      if (!membership) panel.append(button(alliance.local_site ? '加入商盟' : '前往上述据点后可入盟', 'join', {alliance_id:alliance.id}, !alliance.local_site));
      if (alliance.member) {
        const canUse = !!alliance.local_site;
        const tools = element('div', null, 'merchant-tools');
        tools.append(button('申请晋升', 'promote', {alliance_id:alliance.id}, !canUse || membership.rank >= 2 || membership.site === 'hq' && membership.rank === 0));
        tools.append(button('调往当地分部', 'transfer_branch', {alliance_id:alliance.id}, !canUse || alliance.local_site === 'hq' || !!system.active));
        tools.append(button('参加总部调任考核', 'hq_exam', {alliance_id:alliance.id}, alliance.local_site !== 'hq' || membership.site === 'hq' || membership.rank !== 2 || membership.influence < 600 || !!system.active));
        panel.append(tools);
        if (!canUse) panel.append(element('p', '请前往商盟据点办理委托和身份事务。', 'muted'));
        const board = element('details'); board.open = true;
        board.append(element('summary', '接取委托'));
        const stars = element('select'); stars.setAttribute('aria-label', '任务星级');
        for (let i = 1; i <= 5; i++) { const option = element('option', '★'.repeat(i)); option.value = i; option.selected = i === taskStars; stars.append(option); }
        const rows = element('div', null, 'merchant-task-list');
        const draw = () => {
          rows.replaceChildren();
          alliance.tasks.filter(task => task.stars === taskStars).forEach(task => {
            const row = element('div', null, 'merchant-task');
            row.append(element('strong', task.name));
            row.append(element('p', `${task.years}年 · ${money(task.reward.stones)}灵石 / ${task.reward.materials}材料 / ${task.reward.opportunity}机缘 / 因果 -${task.reward.karma} / 影响力 +${task.reward.influence}`));
            row.append(button('接取', 'accept', {alliance_id:alliance.id, task_id:task.id}, !canUse || !!system.active)); rows.append(row);
          });
        };
        stars.onchange = () => { taskStars = Number(stars.value); draw(); };
        draw(); board.append(stars, rows); panel.append(board);
        panel.append(postForm(system, alliance, act, canUse));
        if (alliance.destinations.length) {
          const passage = element('details'); passage.append(element('summary', '逆灵通道'));
          passage.append(element('p', '总部或分总部使节、特使可用。凭原签发总部身份在同盟异界总部付费往返，影响力仍归原任职地；人魔两界最多化神三层，妖界逆灵访客最多合体九层。返回承载足够的界面后恢复道果。'));
          alliance.destinations.forEach(destination => passage.append(button(`前往${destination.name} · ${money(destination.cost)}灵石`, 'passage', {alliance_id:alliance.id, destination:destination.id}, membership.site !== 'hq' || membership.rank < 1 || alliance.local_site !== 'hq' || !!system.active)));
          panel.append(passage);
        }
      }
      root.append(panel);
    });
    if (membership) root.append(button('退出商盟', 'leave', {}, !!system.active));
    root.append(element('h3', `我发布的委托 · 可用商路人手 ${system.hired_hands}`));
    if (!system.posted.length) root.append(element('p', '暂无发布记录。', 'muted'));
    [...system.posted].reverse().forEach(order => {
      const row = element('section', null, 'merchant-order');
      row.append(element('strong', `${'★'.repeat(order.stars)} ${order.name} · ${{open:'等待接取',working:'执行中',completed:'已完成',cancelled:'已取消并退款'}[order.status]}`));
      row.append(element('p', `本金 ${money(order.principal)} / 手续费 ${money(order.fee)} · 取消期限：第${order.deadline}年${order.cross_world ? ' · 跨界委托' : ''}`));
      if (order.status === 'working') {
        const progress = element('progress'); progress.max = 1; progress.value = order.progress;
        progress.setAttribute('aria-label', `${order.name}完成进度`); row.append(progress);
        row.append(element('p', `${order.worker} · ${Math.floor(order.progress * 100)}% · 预计第${order.finish_age}年完成${system.year >= order.finish_age ? '（已延期，期限内未完成将退款）' : ''}`));
      }
      if (order.delivery) row.append(element('p', order.delivery)); root.append(row);
    });
  }
  function postForm(system, alliance, act, canUse) {
    const details = element('details'); details.append(element('summary', '发布委托'));
    const form = element('form', null, 'merchant-post');
    const field = (label, input) => { const wrapper = element('label', label); wrapper.append(input); form.append(wrapper); input.setAttribute('aria-label', label); return input; };
    const kind = field('委托类型', element('select'));
    Object.entries(system.kinds).forEach(([id, name]) => { const option = element('option', name); option.value = id; kind.append(option); });
    const world = field('目标界面', element('select'));
    alliance.catalog.forEach(row => { const option = element('option', row.world_name); option.value = row.world; world.append(option); });
    const localWorld = alliance.world;
    if (localWorld) world.value = localWorld;
    const material = field('所需材料', element('select'));
    const target = field('悬赏目标', element('select'));
    const stars = field('星级', element('select'));
    for (let i=1;i<=5;i++) { const option = element('option', '★'.repeat(i)); option.value = i; stars.append(option); }
    const quantity = field('材料数量', element('input')); quantity.type = 'number'; quantity.min = 1; quantity.max = 99; quantity.value = 1;
    const principal = field('悬赏本金', element('input')); principal.type = 'number'; principal.min = 1; principal.max = 1e15; principal.required = true;
    const quote = element('p', null, 'merchant-quote');
    const refreshQuote = (reset = false) => {
      const definition = alliance.catalog.find(row => row.world === world.value)?.materials.find(row => row.id === material.value);
      const cross = world.value !== localWorld;
      const base = kind.value === 'supply' ? (definition?.value || 0) * Number(quantity.value) * 3 : 2000 * Number(stars.value) ** 3;
      const enemy = alliance.catalog.find(row => row.world === world.value)?.targets.find(row => row.id === target.value);
      const minimum = Math.max(100 * Number(stars.value), base, kind.value === 'bounty' ? Math.ceil((enemy?.power || 0) * 4) : 0) * (cross ? 4 : 1);
      principal.min = minimum; if (reset) principal.value = minimum;
      const value = Number(principal.value || 0), fee = Math.max(1, Math.ceil(value * (alliance.policy === 'economy' ? .06 : .1)));
      quote.textContent = `最低本金 ${money(minimum)}，手续费 ${money(fee)}，合计 ${money(value + fee)}灵石；接单后预计 ${Number(stars.value) * 3 * (cross ? 15 : 1)}年完成。无人完成将全额退回本金。`;
      material.disabled = kind.value !== 'supply' || !canUse; material.dataset.merchantUnavailable = material.disabled ? '1' : '0';
      target.disabled = kind.value !== 'bounty' || !canUse; target.dataset.merchantUnavailable = target.disabled ? '1' : '0';
      target.parentElement.hidden = kind.value !== 'bounty';
      material.parentElement.hidden = kind.value !== 'supply';
      quantity.parentElement.hidden = kind.value !== 'supply';
    };
    const refreshMaterials = () => {
      material.replaceChildren(); target.replaceChildren();
      alliance.catalog.find(row => row.world === world.value)?.materials.forEach(row => { const option = element('option', row.name); option.value = row.id; material.append(option); });
      alliance.catalog.find(row => row.world === world.value)?.targets.forEach(row => { const option = element('option', `${row.name} · ${row.realm} · 战力${money(row.power)}`); option.value = row.id; target.append(option); }); refreshQuote(true);
    };
    world.onchange = refreshMaterials;
    [kind, material, target, stars, quantity].forEach(input => input.onchange = () => refreshQuote(true));
    principal.oninput = () => refreshQuote(); refreshMaterials();
    const submit = element('button', '支付并发布委托'); submit.type = 'submit'; form.append(quote, submit);
    form.querySelectorAll('input,select,button').forEach(input => { if (!canUse) { input.disabled = true; input.dataset.merchantUnavailable = '1'; } });
    form.onsubmit = event => { event.preventDefault(); act({action:'post',alliance_id:alliance.id,kind:kind.value,source_world:world.value,definition_id:material.value,target_id:target.value,stars:Number(stars.value),quantity:Number(quantity.value),principal:Number(principal.value)}); };
    details.append(form); return details;
  }
  window.MerchantPanel = {render};
})();

(() => {
  let taskStars = 1;
  let taskCategory = 'crafting';
  const money = value => Number(value || 0).toLocaleString('zh-CN');
  const element = (tag, text, className = '') => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    node.className = className;
    return node;
  };
  function render(system, act, capabilities = {}) {
    const root = document.querySelector('#merchant-content');
    if (system.available === false) {
      document.querySelector('#merchant-card').classList.add('hidden');
      document.querySelector('[data-panel-target="merchant"]').classList.add('hidden');
      window.UtilityPanels?.close('merchant');
      return;
    }
    document.querySelector('[data-panel-target="merchant"]').classList.remove('hidden');
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
    rules.append(element('p', '分部成员累计120影响力晋为使节，360晋为特使；600影响力并通过修为、实战考核后，可在总部调任使节。同界各分部共用影响力。总部直入成员不能直接升使节，须前往本界分部从成员历练。总部使节累计360总部影响力可升特使。委托现金报酬由商盟储备支付，资金不足时实付减少。'));
    rules.append(element('p', '任务按实际年数消耗时间，途中劫数会中断并保留进度。提交与炼制任务需实物；悬赏和护送会实战，招募及情报可能失败。实物与人员事务须有本盟总部或分总部；情报可经其他商盟转讯，跨界收集耗时为本界的15倍。星级越高、承接修士境界越低，失败风险越高。无人接取超时退还本金；接单后失败退还全部本金及50%手续费（向上取整）。')); root.append(rules);
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
      const requirements = {talisman:`需接单后亲自炼制 ${task.material_name}，完整次数并停用后交付`,supply:`需交付 ${task.material_name} ×${task.quantity}`, weapon:`需在接取后亲自炼成基础战力至少 ${money(task.power * .1)} 的普通法宝（本命及神机不可交付）`, formation:`需 ${task.stars + 1} 件至少 ${Math.max(1, task.realm - 1)} 阶闲置阵材，交商盟工坊炼制`, bounty:`追捕目标战力 ${money(task.power)}，须成功击杀`, escort:`劫道者战力 ${money(task.power)}，你为防御方`, recruit:'招募结果受修为与已雇人手影响', intel:'情报搜集结果受修为与已雇人手影响'};
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
      const fleets = element('details', null, 'merchant-caravans');
      fleets.dataset.allianceId = alliance.id;
      fleets.append(element('summary', `商队经营 · ${(alliance.caravans || []).length} 支`));
      fleets.append(element('p', '商队用本盟资金采购实货，在本界据点之间运输、售货；只有实现利润才向商盟上缴。运价不足时会留驻，长期亏损会缩编或解散。'));
      (alliance.caravans || []).forEach(fleet => {
        const row = element('section', null, 'merchant-order caravan-row');
        row.dataset.caravanId = fleet.id;
        const status = {waiting:'留驻候货',travelling:'在途',selling:'抵达待售',stranded:'运输受阻',retired:'已解散'}[fleet.status];
        row.append(element('strong', `${fleet.name} · ${status}`),
          element('p', `运力 ${money(fleet.capacity)} 件 · 已发 ${money(fleet.voyages)} 趟${fleet.destination ? ` · ${fleet.origin} → ${fleet.destination} · 预计第 ${fleet.arrival} 年抵达` : ` · 驻 ${fleet.location}`}`));
        if (fleet.detail) {
          row.append(element('p', `周转资金 ${money(fleet.cash)} · 累计经营净收支 ${money(fleet.profit)} · 已上缴 ${money(fleet.dividends)} 灵石`),
            element('p', `已交付 ${money(fleet.delivered)} 件 · 途中损失 ${money(fleet.lost)} 件 · 留驻及扩编支出 ${money(fleet.operating_costs)} 灵石`),
            element('p', fleet.last_result));
          if (fleet.cargo) {
            const cargo = fleet.cargo;
            row.append(element('p', `${cargo.name} ×${cargo.quantity} · 本趟总成本 ${money(cargo.cost)} 灵石 · 启程时预估利润 ${money(cargo.expected_profit)} 灵石`),
              element('p', `路程 ${cargo.years}/${cargo.normal_years} 年 · 沿途运输 ${money(cargo.transport_cost)} / 传送费 ${money(cargo.array_fee)} 灵石 · 风险 ${Math.round(cargo.risk * 100)}%`));
          }
        } else row.append(element('p', '加入本界商盟后可查看货单与经营账目。', 'muted'));
        fleets.append(row);
      });
      panel.append(fleets);
      if (!membership) panel.append(button(alliance.local_site ? '加入商盟' : '前往上述据点后可入盟', 'join', {alliance_id:alliance.id}, !alliance.local_site));
      if(capabilities.debug){const grant=button('Debug：一键总部特使','',{},!!system.active);grant.classList.add('merchant-debug-hq');grant.onclick=()=>capabilities.debugGrant(alliance.id);panel.append(grant);}
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
        const materialCategory=element('select'); materialCategory.setAttribute('aria-label','提交任务材料分类');
        [{id:'crafting',name:'炼器材料'},{id:'formation',name:'阵法材料'},{id:'talisman',name:'符箓材料'}].forEach(row=>{const option=element('option',row.name);option.value=row.id;option.selected=row.id===taskCategory;materialCategory.append(option);});
        const draw = () => {
          rows.replaceChildren();
          alliance.tasks.filter(task => task.stars === taskStars && (task.kind!=='supply' || (task.material_category || 'crafting')===taskCategory)).forEach(task => {
            const row = element('div', null, 'merchant-task');
            row.append(element('strong', task.name));
            row.append(element('p', `${task.kind==='supply'?`需 ${task.material_name} ×${task.quantity} · `:''}${task.years}年 · ${money(task.reward.stones)}灵石 / ${task.reward.materials}材料 / ${task.reward.opportunity}机缘 / 因果 -${task.reward.karma} / 影响力 +${task.reward.influence}`));
            row.append(button('接取', 'accept', {alliance_id:alliance.id, task_id:task.id}, !canUse || !!system.active)); rows.append(row);
          });
        };
        stars.onchange = () => { taskStars = Number(stars.value); draw(); };
        materialCategory.onchange=()=>{taskCategory=materialCategory.value;draw();};
        draw(); board.append(stars, materialCategory, rows); panel.append(board);
        panel.append(window.MerchantCommissionForm(system, alliance, act, canUse, capabilities.preview));
        if(alliance.teleports?.length){const portals=element('section');portals.append(element('h4','本盟内部传送阵'));for(const dest of alliance.teleports)portals.append(button(`瞬息至${dest.name}`,'teleport',{alliance_id:alliance.id,destination:dest.id},!canUse));panel.append(portals);}
        if (alliance.destinations.length) {
          const passage = element('details'); passage.append(element('summary', '逆灵通道'));
          passage.append(element('p', '总部或分总部使节、特使可用。凭原签发总部身份在同盟异界总部付费往返，影响力仍归原任职地；修为受到目的界面的承载上限约束。'));
          alliance.destinations.forEach(destination => passage.append(button(`${destination.open ? '前往' : '通道关闭 · '}${destination.name} · ${money(destination.cost)}灵石`, 'passage', {alliance_id:alliance.id, destination:destination.id}, !destination.open || membership.site !== 'hq' || membership.rank < 1 || alliance.local_site !== 'hq' || !!system.active)));
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
      row.dataset.status = order.status;
      row.append(element('strong', `${'★'.repeat(order.stars)} ${order.name} · ${{open:'等待接取',working:'执行中',completed:'已完成',failed:'执行失败 · 已退款',cancelled:'已取消并退款'}[order.status]}`));
      row.append(element('p', `本金 ${money(order.principal)} / 手续费 ${money(order.fee)} · 取消期限：第${order.deadline}年${order.cross_world ? ' · 跨界委托' : ''}`));
      if (order.worker) {
        const progress = element('progress'); progress.max = 1; progress.value = order.progress;
        progress.setAttribute('aria-label', `${order.name}完成进度`); row.append(progress);
        row.append(element('p', `${order.worker}${order.worker_realm_name ? `（${order.worker_realm_name}）` : ''} · ${Math.floor(order.progress * 100)}%${order.status === 'working' ? ` · 预计第${order.finish_age}年完成` : ''}${order.failure_chance != null ? ` · 接单评估失败风险 ${Math.round(order.failure_chance * 100)}%` : ''}`));
      }
      if (order.refund_principal != null) row.append(element('p', `已退本金 ${money(order.refund_principal)} 灵石 + 手续费 ${money(order.refund_fee)} 灵石`, 'merchant-refund'));
      if (order.logs?.length) {
        const logs = element('details', null, 'merchant-progress-log'); logs.open = order.status === 'working' || order.status === 'failed';
        logs.append(element('summary', `执行日志 · ${order.logs.length}条`));
        order.logs.forEach(entry => logs.append(element('p', `第${entry.age}年 · ${entry.message}`)));
        row.append(logs);
      }
      if (order.delivery) row.append(element('p', order.delivery)); root.append(row);
      if(order.service_description) row.append(element('p',order.service_description));
      if(order.spec?.maxima) row.append(element('p',Object.entries(system.metric_names).map(([key,name])=>`${name} ${order.spec.requirements[key]}–${order.spec.maxima[key]}`).join(' / ')));
      if(order.spec){const saved=element('details');saved.append(element('summary','已确认成品概览'));saved.append(element('p',`${order.spec.material_tier}阶原料 · ${order.spec.mold?.name || '九宫阵法'}`));saved.append(element('p',order.kind==='formation'?Object.entries(order.spec.profile.metrics).map(([key,value])=>`${system.metric_names[key]} ${value}`).join(' / '):`战斗力 ${money(order.spec.stats.combat_power)} · 气血 ${money(order.spec.stats.max_hp)} · 法力 ${money(order.spec.stats.max_mp)}`));row.append(saved);}
    });
  }
  window.MerchantPanel = {render};
})();

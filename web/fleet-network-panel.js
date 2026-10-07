(() => {
  const node = (tag, text, cls = '') => { const e = document.createElement(tag); e.textContent = text ?? ''; e.className = cls; return e; };
  const money = n => Number(n || 0).toLocaleString('zh-CN');
  function render(statement, system, act) {
    const personal = document.querySelector('#personal-economy-content');
    personal.replaceChildren(node('h3', `现有灵石 ${money(statement.balance)}`),
      node('p', `自第 ${statement.since ?? 0} 年起 · 期初 ${money(statement.opening)} · 已记收入 ${money(statement.income)} · 已记支出 ${money(statement.expense)}`),
      node('p', `其他现金净变动 ${money(statement.other_change)}。旧玩法未逐笔记账的奖励与消耗计入此项；背包物品不计入现金资产。`, 'muted'));
    const records = node('details'); records.open = true; records.append(node('summary', '最近个人流水（最多 80 笔）'));
    for (const entry of statement.entries || []) records.append(node('p', `第 ${entry.year} 年 · ${entry.reason} · ${entry.destination === 'player' ? '+' : '−'}${money(entry.amount)}`));
    if (!statement.entries?.length) records.append(node('p', '尚无已记录的个人现金交易。'));
    personal.append(records);
    const root = document.querySelector('#fleet-network-content');
    root.replaceChildren();
    if (!system.fleets) return;
    const action = (text, id, payload = {}, unavailable = false) => {
      const b = node('button', text); b.type = 'button'; b.dataset.fleetAction = id;
      b.disabled = !system.can_act || unavailable; b.dataset.merchantUnavailable = b.disabled ? '1' : '0';
      b.onclick = () => act({action:id, ...payload}); return b;
    };
    const group = (title) => { const d = node('details'); d.append(node('summary', title)); root.append(d); return d; };
    const management = group('商队组建与经营');
    management.append(node('p', `初始周转金 ${money(system.capital)} 灵石。商盟每处据点最多 3 队，宗门 2 队、家族 1 队。独立商队需自行聘请护卫；护卫不足时劫掠风险明显上升。`));
    const tools = node('div', '', 'merchant-tools');
    for (const [kind, label] of [['independent','自建独立商队'],['alliance','向商盟申请'],['sect','向宗门申请'],['family','家族组建']]) {
      tools.append(action(label, 'create', {owner_kind:kind}, kind === 'alliance' ? !system.can_apply : kind === 'independent' && system.fleets.some(f => f.owner_kind === kind && f.player_controlled && f.status !== 'retired')));
    }
    management.append(tools);
    management.append(node('p', '组织执掌者可在驻地扩建产业，费用随当地原料价格变化，最高十级。战争会削弱产出，军需采购消耗真实库存与府库。'));
    management.append(action('扩建家族产业', 'industry', {owner_kind:'family'}), action('扩建宗门产业', 'industry', {owner_kind:'sect'}));
    for (const a of system.alliances || []) management.append(node('p', `${a.name}：${a.count} / ${a.capacity} 支商队`));
    for (const f of system.fleets.filter(f => f.owner_kind !== 'alliance' || f.player_controlled)) {
      const row = node('section', '', 'merchant-order'); row.dataset.fleetId = f.id;
      const status = {waiting:'留驻',travelling:'运输中',selling:'待售',stranded:'受阻',retired:'解散'}[f.status];
      row.append(node('strong', `${f.name} · ${f.pledged ? '已约定加盟' : status}`),
        node('p', `${f.location} · 载货 ${f.capacity} 件 · 护卫战力 ${money(f.guard_power)} / 建议 ${money(f.guard_required)}`));
      if (f.detail) row.append(node('p', `周转金 ${money(f.cash)} · 经营净收支 ${money(f.profit)} · ${f.last_result}`));
      if (f.cross_trip) row.append(node('p', `跨界运输 · ${{outbound:'去程',selling:'异界待售',return:'携款返航'}[f.cross_trip.phase]} · 预计第 ${f.cross_trip.arrival} 年抵达`));
      const unavailable = f.location_id !== system.location || f.status !== 'waiting' || !!f.cross_trip;
      if (f.player_controlled) row.append(action(`聘请足额护卫 · ${money(system.guard_cost)}`, 'guard', {fleet_id:f.id}, unavailable || f.guard_power >= f.guard_required), action(`追加周转金 · ${money(system.capital)}`, 'fund', {fleet_id:f.id}, unavailable));
      else if (f.owner_kind === 'independent') row.append(action(f.pledged ? '已招揽' : `招揽合作 · ${money(system.pledge_cost)}`, 'pledge', {fleet_id:f.id}, unavailable || f.pledged));
      management.append(row);
    }
    const alliance = group('自建商盟与分部');
    alliance.append(node('p', '自建商盟需要自己的独立商队及另两支已招揽商队，总部设在当前地图。三队存续且本界储备充足后，可在其他地图建设分部；每处增加三个名额。'));
    alliance.append(action(`在此成立商盟 · ${money(system.found_cost)}`, 'found', {}, system.has_home), action('向本界商盟注资', 'alliance_fund', {}, !system.owned), action(`在此建立分部 · ${money(system.branch_cost)}`, 'branch', {}, !system.owned));
    const passage = group('跨界分总部与逆灵通道');
    passage.append(node('p', '大乘道果及二级以上界面的自建总部，可在异界招揽三队建立分总部，并聘请至少本界倒数第二境界的坐镇修士。也可亲赴当地商盟总部，出资说服其加盟。通道另需巨额建设费，总部承担随原料价格变化的年费；资金不足会关闭。'));
    passage.append(action(`在此建立分总部 · ${money(system.hq_cost)}`, 'regional_hq', {}, !system.has_home || !!system.owned));
    if (system.has_home && !system.owned) for (const a of system.alliances || []) passage.append(action(`洽谈 ${a.name} 加盟`, 'affiliate', {alliance_id:a.id}));
    passage.append(node('p', `新建通道费用 ${money(system.passage_cost)} 灵石；重启按总部当前一年原料维护费支付。`));
    passage.append(action('建设 / 重启本地逆灵通道', 'build_passage', {}, !system.owned));
    for (const r of system.routes || []) {
      passage.append(node('p', `${r.home_name} ↔ ${r.branch_name} · ${r.open ? '开放' : '关闭 / 待建'} · 最近年维护费 ${money(r.maintenance)}`));
      if (system.owned && r.home === system.world) for (const f of system.fleets.filter(f => f.alliance_id === system.owned)) passage.append(action(`${f.name}：赴分总部贸易收款`, 'cross_dispatch', {fleet_id:f.id,destination:r.branch}, !r.open || f.status !== 'waiting' || !!f.cross_trip));
    }
    passage.append(node('p', '票款留在出发界面的商盟府库；只有总部派遣的商队实际抵达分总部、装款返航后，总部才收到汇款。', 'muted'));
  }
  window.FleetNetworkPanel = {render};
})();

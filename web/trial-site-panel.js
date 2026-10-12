/* One DLC panel and one navigation control; previews never submit a command. */
(() => {
  let state, send, isBusy = () => false, identity, selectedFloor;
  const names = {flow:'灵流回路', cooling:'冷却支路', seal:'封匣压力', treasure:'遗藏取舍', core:'守关阵枢'};
  const paths = {
    tower:'M8 28h32M12 28V14h24v14M9 14l15-9 15 9M17 28V18h14v10M12 5h24M16 5V1h16v4M20 18v10m8-10v10',
    flow:'M4 10h20m-6-5 6 5-6 5M28 26H8m6-5-6 5 6 5M4 18h28',
    cooling:'M18 2v32M4 10l28 16M4 26l28-16M14 6l4 4 4-4M14 30l4-4 4 4',
    seal:'M7 13h22v18H7zM12 13V8a6 6 0 0 1 12 0v5M18 20v5',
    treasure:'M3 12h30v19H3zM3 12l5-8h20l5 8M3 19h30M15 16h6v8h-6z',
    core:'M18 2 32 10v16l-14 8L4 26V10zM4 10l14 8 14-8M18 18v16',
    guardian:'M18 2 31 8v14c0 7-13 12-13 12S5 29 5 22V8zM12 15l6-4 6 4-6 9z',
    check:'M6 18l8 8L30 8', lock:'M8 16h20v16H8zM12 16V9a6 6 0 0 1 12 0v7',
    route:'M4 28c0-13 25 0 25-14 0-5-5-8-10-8M22 2l-3 4 3 4M4 26v5',
  };
  const node = (tag, text, cls = '') => {
    const el = document.createElement(tag); el.className = cls;
    if (text !== undefined) el.textContent = text;
    return el;
  };
  const icon = (name, cls = '') => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', name === 'tower' ? '0 0 48 34' : '0 0 36 36');
    svg.setAttribute('fill', 'none'); svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.5'); svg.setAttribute('stroke-linecap', 'round'); svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('class', `trial-icon ${cls}`);
    const path = document.createElementNS(svg.namespaceURI, 'path'); path.setAttribute('d', paths[name] || paths.core); svg.append(path); return svg;
  };
  const format = value => Math.round(Number(value || 0)).toLocaleString('zh-CN');
  function control(label, action, payload = {}, unavailable = false, cls = '') {
    const button = node('button', label, `trial-command ${cls}`); button.type = 'button';
    button.dataset.trialAction = action; button.dataset.unavailable = unavailable ? '1' : '0';
    button.disabled = unavailable || isBusy(); const id = state.id;
    button.onclick = () => send(`/api/games/${id}/trial-site-action`, {action, ...payload}); return button;
  }
  function meter(label, value, max, cls) {
    const box = node('div', undefined, `trial-meter ${cls}`), caption = node('div', undefined, 'trial-meter-caption');
    caption.append(node('span', label), node('b', `${format(value)} / ${format(max)}`));
    const track = node('div', undefined, 'trial-meter-track'), fill = node('span');
    fill.style.width = `${Math.max(0, Math.min(100, 100 * value / Math.max(1, max)))}%`;
    track.setAttribute('role', 'progressbar'); track.setAttribute('aria-label', label);
    track.setAttribute('aria-valuemin', '0'); track.setAttribute('aria-valuemax', String(max)); track.setAttribute('aria-valuenow', String(value));
    track.append(fill); box.append(caption, track); return box;
  }
  function hero(view) {
    const box = node('header', undefined, 'trial-hero');
    const art = node('div', undefined, 'trial-relic'); art.append(node('i', undefined, 'trial-orbit'), icon('tower'));
    const copy = node('div', undefined, 'trial-hero-copy'); copy.append(node('small', '万象试境 · 独立 DLC', 'trial-kicker'), node('h3', '探机关，问修持'));
    copy.append(node('p', `${view.world_name} · ${view.location_name}`), node('span', '五处异闻 / 一位守关者 / 探索零耗时', 'trial-subtitle'));
    const progress = node('div', undefined, 'trial-progress'); progress.style.setProperty('--trial-progress', `${360 * view.cleared / view.total}deg`);
    const center = node('div'); center.append(node('b', `${view.cleared}`), node('small', `/ ${view.total} 层`)); progress.append(center);
    progress.setAttribute('aria-label', `已通过 ${view.cleared}/${view.total} 层`); box.append(art, copy, progress); return box;
  }
  function floors(view, panel) {
    const box = node('section', undefined, 'trial-level-map'); box.append(node('h4', '试境层图'), node('p', '同境界逐层增强。点选层位查看，沿已解锁路径进入。', 'muted'));
    const grid = node('div', undefined, 'trial-site-floors');
    view.floors.forEach(floor => {
      const completed = floor.status === 'claimed', locked = !floor.unlocked;
      const button = node('button', undefined, `trial-site-floor ${completed ? 'complete' : locked ? 'locked' : 'reachable'}${selectedFloor === floor.number ? ' selected' : ''}`);
      button.type = 'button'; button.dataset.trialFloor = floor.number; button.setAttribute('aria-pressed', String(selectedFloor === floor.number));
      button.append(node('span', String(floor.number).padStart(2, '0'), 'trial-level-number'), icon(completed ? 'check' : locked ? 'lock' : 'tower'));
      button.append(node('b', floor.realm_name), node('small', `${floor.layer}层 · ${completed ? '已通过' : locked ? '待解锁' : '可续行'}`));
      button.onclick = () => { selectedFloor = floor.number; draw(); }; grid.append(button);
    }); box.append(grid); panel.append(box);
    const floor = view.floors.find(row => row.number === selectedFloor) || view.floors[0];
    const entry = node('section', undefined, 'trial-entry');
    entry.append(icon('route'), node('div', undefined, 'trial-entry-copy'));
    const copy = entry.lastChild; copy.append(node('h4', `第 ${floor.number} 层 · ${floor.realm_name}${floor.layer}层`));
    copy.append(node('p', floor.status === 'claimed' ? '此层已取得通行资格，奖励记录保留。' : !floor.unlocked ? '先通过前一层，才能探明此处守关者。' : '五个事件决定守关局势与遗藏，完成后进入自动交锋。'));
    if (state.player.location_id !== view.location_id) {
      const route = state.map?.locations?.find(row => row.id === view.location_id);
      copy.append(node('small', route ? `${(route.route_names || []).join(' → ')} · 预计 ${route.travel_years} 年` : '请循正常地图路线抵达此地'));
      const travel = node('button', '前往试境所在地', 'trial-command'); travel.type = 'button'; travel.dataset.trialTravel = 'true';
      const unavailable = !route || route.travel_status === 'lethal' || !!state.pending_event || !!state.imprisonment || !state.player.alive || !!state.guixu_tide?.session;
      travel.dataset.unavailable = unavailable ? '1' : '0'; travel.disabled = unavailable || isBusy();
      const id = state.id, destination = view.location_id; travel.onclick = () => send(`/api/games/${id}/map-travel`, {destination}); entry.append(travel);
    }
    entry.append(control(floor.status === 'unvisited' ? '开始探索' : '续行本层', 'enter', {world:view.world, floor:floor.number}, !view.can_enter || !floor.unlocked || floor.status === 'claimed', 'primary'));
    panel.insertBefore(entry, box); if (!view.can_enter) entry.append(node('p', view.unavailable_reason || '当前不能开始挑战', 'trial-unavailable'));
  }
  function route(session) {
    const track = node('ol', undefined, 'trial-mechanism-route'); track.setAttribute('aria-label', '五处机关探索进度');
    session.mechanisms.forEach((mechanism, index) => {
      const step = node('li', undefined, `trial-mechanism ${mechanism.status}`);
      const symbol = node('div', undefined, 'trial-mechanism-symbol'); symbol.append(icon(mechanism.kind));
      symbol.append(node('span', mechanism.status === 'done' ? '✓' : `${index + 1}`, 'trial-step-index'));
      step.append(symbol, node('b', names[mechanism.kind]), node('small', mechanism.status === 'done' ? '已处理' : mechanism.status === 'current' ? '当前异闻' : '未探明'));
      if (mechanism.summary) step.title = mechanism.summary; track.append(step);
    }); return track;
  }
  function rewards(session) {
    const grid = node('div', undefined, 'trial-reward-grid');
    session.rewards.forEach((reward, index) => {
      const tile = node('div', undefined, `trial-reward ${reward.preserved ? '' : 'damaged'}`);
      tile.append(icon('treasure'), node('small', index ? '关联遗藏' : '基础奖励'), node('b', reward.name), node('span', `${reward.tier}阶 · ${reward.preserved ? '通关可得' : '已损毁'}`)); grid.append(tile);
    }); return grid;
  }
  function readiness(session, panel) {
    const box = node('section', undefined, 'trial-guardian-card');
    const header = node('div', undefined, 'trial-guardian-heading'); header.append(icon('guardian'), node('div'));
    header.lastChild.append(node('small', '守关者'), node('h4', session.boss_name), node('span', `${session.realm_name}${session.layer}层 · 尝试 ${session.attempts} 次`)); box.append(header);
    const strength = node('div', undefined, 'trial-strength'); strength.append(node('span', '当前守关战力'), node('b', format(session.power)), node('small', `基准 ${format(session.base_power)} · ${(session.power_ratio * 100).toFixed(0)}%`));
    const track = node('div', undefined, 'trial-strength-track'), fill = node('span'); fill.style.width = `${Math.max(0, Math.min(100, (session.power_ratio - .7) / .7 * 100))}%`; track.append(fill); strength.append(track); box.append(strength);
    const conditions = node('div', undefined, 'trial-condition-grid');
    for (const [label, description, active] of [['阵甲',session.guard ? '供能保留 · 防护 ×1.20' : '供能已断',session.guard], ['余灵',session.bonus ? '威能 ×1.10' : '无增幅',session.bonus], ['遗藏',session.treasure ? '保持完好' : '已损毁',!session.treasure]]) {
      const tile = node('div', undefined, `trial-condition ${active ? 'active' : 'clear'}`); tile.append(node('small', label), node('b', description)); conditions.append(tile);
    }
    if (session.realm_name === '真仙' || ['金仙','太乙','大罗'].includes(session.realm_name)) {
      const tile = node('div', undefined, `trial-condition ${session.field ? 'active' : 'clear'}`); tile.append(node('small','邻域与防护'),node('b',session.field ? '守关域可展开' : '接点已封停'),node('small',session.golden_light ? '护体金光仍有效' : '无护体金光')); conditions.append(tile);
      box.append(meter('守关元力', session.energy, 1200, 'energy'));
    }
    box.append(conditions); panel.append(box); panel.append(rewards(session));
    panel.append(node('p', '交锋可能受创或死亡。邻域、金光与保命沿原战斗规则结算；倍率表示当前配置，不代表胜率。', 'trial-risk'));
    if (session.result) {
      const details = node('details', undefined, 'trial-battle-result'); details.append(node('summary', session.status === 'won' ? '守关成功 · 查看交锋记录' : '本次未通过 · 查看交锋记录'),node('p',session.result.summary)); panel.append(details);
    }
  }
  function sessionView(view, panel) {
    const session = view.session, header = node('div', undefined, 'trial-session-heading');
    header.append(node('h4', `第 ${session.number} 层 · ${session.realm_name}${session.layer}层`),node('span', `${session.event_index}/5 处机关已处理`)); panel.append(header, route(session));
    const resources = node('div', undefined, 'trial-player-resources'); resources.append(meter('气血', state.player.hp, state.player.max_hp, 'hp'),meter('法力',state.player.mp,state.player.max_mp,'mp')); panel.append(resources);
    const pending = state.pending_event;
    if (session.status === 'exploring' && pending?.id.startsWith('SYS_TRIAL_SITE_')) {
      const event = node('section', undefined, 'trial-site-event'); event.append(node('small', `异闻 ${session.event_index + 1} / 5`, 'trial-kicker'),node('h4',pending.title),node('p',pending.body,'trial-clue'));
      const choices = node('div', undefined, 'trial-site-choices');
      pending.choices.forEach(choice => {
        const button = node('button', undefined, choice.id === 'pause' ? 'trial-pause' : 'trial-choice'); button.type = 'button';
        button.dataset.trialChoice = choice.id; button.dataset.unavailable = choice.enabled === false ? '1' : '0';
        button.disabled = choice.enabled === false || isBusy(); button.title = choice.enabled === false ? choice.disabled_reason : '';
        if (choice.id !== 'pause') button.append(icon(session.mechanisms[session.event_index].kind));
        button.append(node('span',choice.text)); const id = state.id, eventId = pending.id;
        button.onclick = () => send(`/api/games/${id}/choice`, {choice_id:choice.id,event_id:eventId}); choices.append(button);
      }); event.append(choices); panel.append(event);
    } else {
      const payload = {floor_id:session.floor_id,revision:session.revision};
      if (session.event_index === 5) {
        readiness(session,panel); const actions = node('div',undefined,'trial-battle-actions');
        if (['ready','failed'].includes(session.status)) actions.append(control(session.status === 'failed' ? '再次挑战守关者' : '挑战守关者','fight',payload,!session.can_fight,'primary'));
        if (session.status === 'won') actions.append(control('领取本层奖励','claim',payload,!session.can_claim,'primary')); panel.append(actions);
      }
      panel.append(control('暂停离开，保留本层局势','pause',payload,!session.can_pause||!!state.pending_event,'trial-pause'));
    }
    if (session.known.length) {
      const facts = node('details',undefined,'trial-known'); facts.append(node('summary','已知机关与选择记录')); const list = node('ol'); session.known.forEach(text=>list.append(node('li',text))); facts.append(list); panel.append(facts);
    }
  }
  function draw() {
    const panel = document.querySelector('#trial-site-panel'), card = document.querySelector('#trial-site-card'); if (!panel || !card) return;
    const view = state?.trial_site; card.classList.toggle('hidden', !view?.enabled); panel.replaceChildren();
    if (!view?.enabled) { window.UtilityPanels?.close('trial-site'); return; }
    if (!view.available) { panel.append(icon('tower','trial-empty-icon'),node('h3','此境暂无试境入口'),node('p',view.unavailable_reason || '返回普通界面后可定位遗迹。')); return; }
    panel.append(hero(view));
    if (view.session) sessionView(view,panel); else floors(view,panel);
  }
  function open() { window.UtilityPanels?.open('trial-site'); draw(); document.querySelector('#trial-site-card')?.scrollTo({top:0,behavior:'instant'}); }
  function update(data, mutate, busy) {
    if (identity !== `${data.id}:${data.player.world}`) { identity = `${data.id}:${data.player.world}`; selectedFloor = null; }
    state=data;send=mutate;isBusy=busy;
    const view=data.trial_site; selectedFloor ??= Math.min((view?.cleared || 0)+1,view?.total || 1);
    if (view?.available && selectedFloor <= view.cleared) selectedFloor = Math.min(view.cleared + 1, view.total);
    const dock=document.querySelector('[data-panel-target="trial-site"]'); dock?.classList.toggle('hidden', !view?.enabled);
    if (dock) dock.disabled = isBusy();
    draw();
    let notice=document.querySelector('#trial-site-notice');
    if (!notice) {notice=node('div',undefined,'trial-site-notice');notice.id='trial-site-notice';document.querySelector('#event-card').before(notice);}
    notice.classList.toggle('hidden', !view?.active); notice.replaceChildren();
    if (view?.active) {
      if (view.blocked_session) notice.append(node('span','已有守关封锁仍未解除；重新启用万象试境后可续战。'));
      else {notice.append(icon('tower'),node('span',`万象试境 · 第 ${view.session.number} 层 · ${view.session.event_index}/5 机关`));const link=node('button','查看试境局势');link.type='button';link.onclick=open;notice.append(link);}
    }
  }
  function badge(location, container) {
    const view=state?.trial_site;if (!view?.enabled||!view.available||location.id!==view.location_id)return;
    const marker=node('button',`◇ 万象试境 · ${view.cleared}/${view.total} 层`,'trial-site-marker');marker.type='button';marker.dataset.trialSite=view.site_id;marker.onclick=open;container.append(marker);
  }
  function syncBusy() {
    document.querySelectorAll('#trial-site-panel [data-trial-action], #trial-site-panel [data-trial-choice], #trial-site-panel [data-trial-travel]').forEach(button=>{button.disabled=isBusy()||button.dataset.unavailable==='1';});
  }
  window.addEventListener('game:panel-open',event=>{if(event.detail.name==='trial-site'){draw();syncBusy();}});
  window.TrialSitePanel={update,badge,syncBusy};
})();

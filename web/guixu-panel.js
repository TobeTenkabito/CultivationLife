(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;',
  })[char]);
  const phaseNames = {closed:'沉寂', announced:'潮讯已现', open:'潮门开启'};
  const layerEdges = new Set(['outer:middle', 'middle:outer', 'middle:inner', 'inner:middle', 'inner:final', 'final:inner', 'inner:secret', 'secret:inner']);

  function button(label, action, payload = {}, disabled = false, kind = '') {
    const data = esc(JSON.stringify({action, ...payload}));
    return `<button type="button" data-guixu='${data}' class="${kind}" ${disabled ? 'disabled' : ''}>${esc(label)}</button>`;
  }

  function renderDungeon(row, act) {
    const entries = (row.round_entries || []).map(entry => (
      `<li><b>${esc(entry.name)}</b><small>${esc(entry.category)} · ${esc(entry.layer_id || '层位未定')} · ${esc(entry.resolution)}</small></li>`
    )).join('');
    return `<section class="guixu-dungeon ${row.phase === 'open' ? 'open' : ''}">
      <header><div><small>${esc(row.world === 'human' ? '人界' : '灵界')} · ${esc(row.entry_location_name)}</small><h3>${esc(row.name)}</h3></div><strong>${esc(phaseNames[row.phase] || row.phase)}</strong></header>
      <p>第 ${esc(row.cycle_index)} 届 · 下次预告 ${esc(row.next_announce_age)} 岁 · 开启 ${esc(row.next_open_age)} 岁 · 主池余 ${esc(row.pool_remaining)}/60</p>
      ${entries ? `<details><summary>本届六件宝物</summary><ul class="guixu-treasure-list">${entries}</ul></details>` : '<p class="muted">本届宝物尚未显潮。</p>'}
      ${button('踏入归墟', 'enter', {dungeon_id:row.id}, !row.can_enter, 'guixu-primary')}
    </section>`;
  }

  function renderSession(session) {
    const current = session.layer_id;
    const layers = (session.layers || []).map(layer => {
      const canMove = !layer.current && !layer.locked && layerEdges.has(`${current}:${layer.id}`);
      return button(layer.current ? `${layer.name}（当前）` : layer.name, 'move', {target_layer_id:layer.id}, !canMove, layer.current ? 'active' : '');
    }).join('');
    const actors = (session.actors || []).map(actor => {
      if (actor.status === 'recruited') return `<div class="guixu-actor"><div><b>${esc(actor.name)}</b><small>临时同行 · 战力 ${esc(actor.power)}</small></div></div>`;
      return `<div class="guixu-actor"><div><b>${esc(actor.name)}</b><small>${esc(actor.protected ? '与你关系深厚 · ' : '')}战力 ${esc(actor.power)}</small></div><div>
        ${button('夺宝战', 'fight', {actor_id:actor.actor_id, protected:!!actor.protected, actor_name:actor.name}, false, 'danger')}
        ${button('遁走', 'flee', {actor_id:actor.actor_id})}
        ${button('邀为队友', 'recruit', {actor_id:actor.actor_id})}
      </div></div>`;
    }).join('') || '<p class="muted">此层眼下不见其他修士。</p>';
    const treasures = (session.treasures || []).map(entry => `<div class="guixu-treasure">
      <div><b>${esc(entry.name)}</b><small>${esc(entry.resolution === 'held' ? `${entry.holder_name || '某修士'}持有` : '尚未被发现')}</small></div>
      ${entry.resolution === 'held' ? button('报价交换', 'negotiate', {actor_id:entry.holder_id, pool_entry_id:entry.pool_entry_id, treasure_name:entry.name}, false, 'trade') : ''}
    </div>`).join('') || '<p class="muted">这一层暂时没有显露的本届宝物。</p>';
    return `<section class="guixu-session">
      <div class="guixu-session-head"><div><p class="eyebrow">${esc(session.trapped ? 'TRAPPED' : 'EXPEDITION')}</p><h3>${esc(session.dungeon_name)}</h3></div><strong>${session.trapped ? '已被困' : `余 ${esc(session.remaining_days)} 天`}</strong></div>
      <div class="guixu-layers">${layers}</div>
      <div class="guixu-actions">${button('搜寻此层', 'search', {}, !!session.trapped, 'guixu-primary')}${button(`返回入口（${session.return_days}天）`, 'return', {}, !!session.trapped)}${session.trapped ? button('静修一年', 'trapped_cultivate', {}, false, 'guixu-primary') : ''}</div>
      <section><h4>本层宝物</h4>${treasures}</section>
      <section><h4>本层修士</h4>${actors}</section>
    </section>`;
  }

  function bind(root, act) {
    root.querySelectorAll('[data-guixu]').forEach(node => node.addEventListener('click', () => {
      const payload = JSON.parse(node.dataset.guixu);
      if (payload.action === 'fight' && payload.protected) {
        if (!window.confirm(`${payload.actor_name}与你关系深厚。确认发动致命夺宝战并永久断绝关系？`)) return;
        payload.confirm_betrayal = true;
      }
      if (payload.action === 'negotiate') {
        const value = window.prompt(`为“${payload.treasure_name}”报价多少下品灵石？`, '100');
        if (value === null) return;
        payload.offer_stones = Math.max(0, Number.parseInt(value, 10) || 0);
      }
      delete payload.protected;
      delete payload.actor_name;
      delete payload.treasure_name;
      act(payload);
    }));
  }

  function render(state, act) {
    const available = !!state?.available;
    document.querySelector('.guixu-dock-button')?.classList.toggle('hidden', !available);
    const panel = document.querySelector('#guixu-card');
    panel?.classList.toggle('hidden', !available);
    if (!available) {
      window.UtilityPanels?.close('guixu');
      return;
    }
    const root = document.querySelector('#guixu-content');
    const session = state.session;
    document.querySelector('#guixu-summary').textContent = session
      ? `${session.dungeon_name} · ${session.trapped ? '困守' : `余${session.remaining_days}天`}`
      : '每界一座大型周期副本';
    root.innerHTML = session
      ? renderSession(session)
      : `<div class="guixu-dungeon-grid">${(state.dungeons || []).map(row => renderDungeon(row, act)).join('')}</div>`;
    bind(root, act);
  }

  window.GuixuPanel = {render};
})();
